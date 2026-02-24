"""
Build canonical employer groups from f7_employers_deduped.

Groups employers by (name_aggressive, UPPER(state)) so that the same
real-world employer appearing as multiple rows (name variants, multiple
bargaining units, historical+current) gets one canonical representative.

Algorithm:
  1. Load all 113K rows from f7_employers_deduped
  2. Group by (name_aggressive, UPPER(state)) -- skip NULL/empty, skip signatories
  3. Cross-state merge: name_aggressive appearing in 3+ states with same aff_abbr
  4. Pick canonical rep per group + compute consolidated workers
  5. Write: TRUNCATE + rebuild (idempotent)

Usage:
  py scripts/matching/build_employer_groups.py [--dry-run] [--skip-cross-state] [--min-states N]
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from src.python.matching.name_normalization import (
    normalize_name_aggressive,
    normalize_name_standard,
)


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

DDL_TABLE = """
CREATE TABLE IF NOT EXISTS employer_canonical_groups (
    group_id        SERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    canonical_employer_id TEXT NOT NULL,
    state           TEXT,
    member_count    INT NOT NULL DEFAULT 0,
    consolidated_workers INT NOT NULL DEFAULT 0,
    is_cross_state  BOOLEAN NOT NULL DEFAULT FALSE,
    states          TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

DDL_COLUMNS = [
    """ALTER TABLE f7_employers_deduped
       ADD COLUMN IF NOT EXISTS canonical_group_id INT
       REFERENCES employer_canonical_groups(group_id)""",
    """ALTER TABLE f7_employers_deduped
       ADD COLUMN IF NOT EXISTS is_canonical_rep BOOLEAN NOT NULL DEFAULT FALSE""",
]

DDL_INDEXES = [
    """CREATE INDEX IF NOT EXISTS idx_f7_canonical_group
       ON f7_employers_deduped(canonical_group_id)
       WHERE canonical_group_id IS NOT NULL""",
    """CREATE INDEX IF NOT EXISTS idx_ecg_canonical_employer
       ON employer_canonical_groups(canonical_employer_id)""",
]


def ensure_schema(conn):
    """Create table + columns idempotently."""
    with conn.cursor() as cur:
        cur.execute(DDL_TABLE)
        for ddl in DDL_COLUMNS:
            cur.execute(ddl)
        for ddl in DDL_INDEXES:
            cur.execute(ddl)
    conn.commit()
    print("[schema] employer_canonical_groups table + columns ensured")


# ---------------------------------------------------------------------------
# Scoring for canonical rep selection
# ---------------------------------------------------------------------------

SKIP_REASONS = {'SAG_AFTRA_SIGNATORY', 'SIGNATORY_PATTERN'}

GENERIC_TOKENS = {
    "construction", "contractor", "contractors", "builders", "building",
    "service", "services", "equipment",
    # Phase 2.4 additions — directional/regional/descriptive words that produce
    # mega-merges when they are the *only* token left after aggressive normalisation
    "maintenance", "electric", "community", "national", "american",
    "general", "continental", "pacific", "pioneer", "metropolitan",
    "industrial", "commercial", "universal", "premier", "standard",
    "central", "southern", "northern", "western", "eastern", "midwest",
    "united", "international", "federal", "republic", "liberty",
    "heritage", "trinity", "alliance", "patriot", "cornerstone",
}

# Major US cities / geographic words that commonly appear as the sole
# aggressive-normalised employer name and cause unrelated employers to merge.
GEOGRAPHIC_TOKENS = {
    # cities from I8 problem groups
    "san diego", "cincinnati", "metropolitan", "portland", "sacramento",
    "pittsburgh", "cleveland", "memphis", "milwaukee", "oakland",
    "tucson", "omaha", "reno", "tulsa", "boise",
    # top-50 US cities that appear in employer names
    "houston", "chicago", "dallas", "phoenix", "detroit", "seattle",
    "denver", "atlanta", "miami", "boston", "charlotte", "nashville",
    "austin", "columbus", "indianapolis", "jacksonville", "louisville",
    "baltimore", "buffalo", "norfolk", "richmond", "tampa",
    "las vegas", "los angeles", "san francisco", "san antonio",
    "new orleans", "new york", "kansas city", "salt lake city",
    "st louis", "st paul", "fort worth", "long beach", "el paso",
    "santa fe", "santa cruz", "santa barbara", "santa rosa",
    # state / region names that also appear alone
    "california", "florida", "texas", "michigan", "ohio", "virginia",
    "georgia", "carolina", "colorado", "arizona", "oregon",
    "connecticut", "alabama", "tennessee", "missouri", "maryland",
    "wisconsin", "minnesota", "kentucky", "oklahoma", "arkansas",
    "mississippi", "nebraska", "montana", "hawaii", "alaska",
    "new england", "northwest", "southeast", "southwest", "northeast",
    "mid atlantic",
}

# Pre-split multi-word geographic tokens into a set of frozen tuples for
# efficient lookup.  Single-word entries stored in a separate set so we can
# do O(1) membership tests on both.
_GEO_SINGLE = set()
_GEO_MULTI = {}  # normalised multi-word string -> True
for _g in GEOGRAPHIC_TOKENS:
    _parts = _g.split()
    if len(_parts) == 1:
        _GEO_SINGLE.add(_g)
    else:
        _GEO_MULTI[_g] = True

SINGLE_INITIAL_GENERIC_RE = re.compile(
    r"^[a-z]\s+(construction|contractor|contractors|builders|building|service|services|equipment)$"
)

KNOWN_BRANDS = {
    "brand:healthcare_services_group": re.compile(
        r"\b(healthcare services group|health services group|hcsg)\b", re.IGNORECASE
    ),
    "brand:first_student": re.compile(r"\bfirst\s+student\b", re.IGNORECASE),
    # Phase 2.4 additions — consolidate fragmented multi-state chains
    "brand:aramark": re.compile(r"\b(aramark)\b", re.IGNORECASE),
    "brand:sodexo": re.compile(r"\b(sodexo|sdh)\b", re.IGNORECASE),
    "brand:alsco": re.compile(r"\b(alsco)\b", re.IGNORECASE),
    "brand:ameripride": re.compile(r"\b(ameripride)\b", re.IGNORECASE),
    "brand:compass_group": re.compile(r"\b(compass\s+group|compass)\b", re.IGNORECASE),
    "brand:starbucks": re.compile(r"\b(starbucks)\b", re.IGNORECASE),
    "brand:mv_transportation": re.compile(r"\b(mv\s+transportation)\b", re.IGNORECASE),
    "brand:waste_management": re.compile(r"\b(waste\s+management)\b", re.IGNORECASE),
    "brand:safeway": re.compile(r"\b(safeway)\b", re.IGNORECASE),
    "brand:unicco": re.compile(r"\b(unicco)\b", re.IGNORECASE),
    "brand:pepsico": re.compile(r"\b(pepsico|pepsi)\b", re.IGNORECASE),
    "brand:dhl": re.compile(r"\b(dhl)\b", re.IGNORECASE),
    "brand:abm": re.compile(r"\b(abm)\b", re.IGNORECASE),
    "brand:securitas": re.compile(r"\b(securitas)\b", re.IGNORECASE),
    "brand:loomis": re.compile(r"\b(loomis)\b", re.IGNORECASE),
}


def _norm_city(city):
    return (city or "").upper().strip()


def _is_known_brand_key(group_key):
    return bool(group_key and group_key.startswith("brand:"))


def _known_brand_key(name_standard):
    for key, pattern in KNOWN_BRANDS.items():
        if pattern.search(name_standard or ""):
            return key
    return None


def _is_generic_group_name(name_aggressive, employer_name_standard):
    """Return True if name_aggressive is too generic for state-only grouping.

    Generic names are forced into city+state grouping (Phase 1) so that
    unrelated employers sharing a city/directional name don't merge.
    """
    na = (name_aggressive or "").strip().lower()
    if not na:
        return False
    if _is_known_brand_key(na):
        return False

    toks = na.split()
    if SINGLE_INITIAL_GENERIC_RE.match(na):
        return True

    # Single token that is generic or a geographic name
    if len(toks) == 1 and (toks[0] in GENERIC_TOKENS or toks[0] in _GEO_SINGLE):
        return True

    # 1-2 tokens where every token is generic, geographic, or a single letter
    if len(toks) <= 2:
        generic_or_geo = GENERIC_TOKENS | _GEO_SINGLE
        if all(t in generic_or_geo or len(t) == 1 for t in toks):
            return True

    # Multi-word geographic name (e.g. "san diego", "las vegas", "new york")
    if na in _GEO_MULTI:
        return True

    # Two tokens where the full phrase is a known multi-word geo
    if len(toks) == 2 and na in _GEO_MULTI:
        return True  # already caught above, but explicit for clarity

    # Three tokens where first two are a multi-word geo + one generic
    if len(toks) == 3:
        first_two = f"{toks[0]} {toks[1]}"
        last_two = f"{toks[1]} {toks[2]}"
        if (first_two in _GEO_MULTI and (toks[2] in GENERIC_TOKENS or len(toks[2]) == 1)):
            return True
        if (last_two in _GEO_MULTI and (toks[0] in GENERIC_TOKENS or len(toks[0]) == 1)):
            return True

    std = (employer_name_standard or "").strip().lower()
    if re.match(
        r"^[a-z]\s+(construction|contractor|contractors|builders|building|service|services|equipment)\b",
        std,
    ):
        return True
    return False


def _rep_score(row):
    """Score a row for canonical rep selection. Higher = better."""
    score = 0
    if not row['is_historical']:
        score += 100
    if not row['exclude_from_counts']:
        score += 50
    unit = row['latest_unit_size'] or 0
    score += unit / 100.0
    if row['latest_notice_date']:
        score += 10
    return score


def _consolidated_workers(members):
    """Compute consolidated workers: SUM of MAX(unit_size) per distinct union.

    Handles same-union = MAX, different-unions = SUM correctly.
    """
    by_union = defaultdict(int)
    for m in members:
        fnum = m['latest_union_fnum'] or '__none__'
        size = m['latest_unit_size'] or 0
        by_union[fnum] = max(by_union[fnum], size)
    return sum(by_union.values())


def _fuzzy_post_merge(rows, groups, min_ratio=90):
    """Phase 4: Merge ungrouped singletons into existing groups via fuzzy name match.

    Uses token_set_ratio >= min_ratio (default 90) to find near-exact matches
    after normalization. Only merges singletons INTO existing groups.
    Skips names <= 4 chars (too short for reliable fuzzy matching).
    """
    from rapidfuzz import fuzz

    # Build set of grouped employer IDs
    grouped_ids = set()
    for g in groups:
        for m in g['members']:
            grouped_ids.add(m['employer_id'])

    # Build per-state index: state -> [(group_index, group_key, is_generic, city_set)]
    group_by_state = defaultdict(list)
    for idx, g in enumerate(groups):
        canon_key = None
        for m in g['members']:
            if m['employer_id'] == g['canonical_employer_id']:
                canon_key = m.get('group_key') or m['name_aggressive']
                break
        if not canon_key:
            canon_key = g['members'][0].get('group_key') or g['members'][0]['name_aggressive']

        is_generic = _is_generic_group_name(canon_key, g['canonical_name'])
        city_set = {_norm_city(m.get('city')) for m in g['members'] if _norm_city(m.get('city'))}

        if g['is_cross_state']:
            for st in (g['states'] or []):
                group_by_state[st].append((idx, canon_key, is_generic, city_set))
        else:
            st = (g['state'] or '').upper()
            group_by_state[st].append((idx, canon_key, is_generic, city_set))

    # Find ungrouped singletons
    singletons = [r for r in rows
                  if r['employer_id'] not in grouped_ids
                  and (r.get('group_key') or r['name_aggressive'])
                  and r.get('exclude_reason') not in SKIP_REASONS]

    merged = 0
    for r in singletons:
        group_key = (r.get('group_key') or r['name_aggressive'] or "").strip()
        if len(group_key) <= 4:
            continue
        st = (r['state'] or '').upper().strip()
        city = _norm_city(r.get('city'))
        row_is_generic = _is_generic_group_name(group_key, r.get('name_standard') or "")
        if row_is_generic and not city:
            continue

        best_ratio = 0
        best_idx = None

        for idx, canon_key, canon_is_generic, canon_city_set in group_by_state.get(st, []):
            if len(canon_key) <= 4:
                continue

            # Generic names require exact normalized key and city+state match.
            if row_is_generic or canon_is_generic:
                if not city or city not in canon_city_set:
                    continue
                if group_key != canon_key:
                    continue
                ratio = 100
            else:
                ratio = fuzz.token_set_ratio(group_key, canon_key)
                if ratio < min_ratio:
                    continue

            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx

        if best_idx is not None:
            g = groups[best_idx]
            g['members'].append(r)
            g['member_count'] += 1
            g['consolidated_workers'] = _consolidated_workers(g['members'])
            grouped_ids.add(r['employer_id'])
            merged += 1

    return merged


# ---------------------------------------------------------------------------
# Main algorithm
# ---------------------------------------------------------------------------

def load_employers(conn):
    """Load all f7_employers_deduped rows needed for grouping."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT e.employer_id, e.employer_name, e.name_aggressive, e.name_standard,
                   e.city, e.state, e.naics,
                   e.latest_union_fnum, e.latest_unit_size,
                   um.aff_abbr,
                   e.is_historical, e.exclude_from_counts, e.exclude_reason,
                   e.latest_notice_date
            FROM f7_employers_deduped e
            LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_groups(rows, skip_cross_state=False, min_states=2):
    """Group rows by (name_aggressive, UPPER(state)).

    Returns list of group dicts with members, canonical rep, etc.
    """
    # Phase 0: Recompute normalized names in-memory with latest normalizer
    recomputed = 0
    for r in rows:
        std = normalize_name_standard(r['employer_name'] or '')
        old_na = r['name_aggressive']
        new_na = normalize_name_aggressive(r['employer_name'] or '')
        brand_key = _known_brand_key(std)
        group_key = brand_key or new_na

        if new_na != old_na:
            recomputed += 1
        r['name_standard'] = std
        r['name_aggressive'] = new_na
        r['group_key'] = group_key
        r['is_generic_group_name'] = _is_generic_group_name(group_key, std)
    if recomputed:
        print(f"[group] Phase 0: recomputed {recomputed:,} name_aggressive values in-memory")

    # Phase 1: group by normalized key + geography.
    # Generic keys require city+state; non-generic keys use state.
    state_groups = defaultdict(list)
    for r in rows:
        group_key = r.get('group_key')
        if not group_key or not group_key.strip():
            continue
        # Skip signatory patterns
        if r['exclude_reason'] in SKIP_REASONS:
            continue
        st = (r['state'] or '').upper().strip()
        if r.get('is_generic_group_name'):
            city = _norm_city(r.get('city'))
            if city:
                key = (group_key, st, city)
            else:
                key = (group_key, st, f"__NO_CITY__:{r['employer_id']}")
        else:
            key = (group_key, st, None)
        state_groups[key].append(r)

    # Only keep groups with 2+ members
    multi_groups = {k: v for k, v in state_groups.items() if len(v) >= 2}

    # Phase 2: cross-state merge
    cross_state_merged = set()  # keys already merged
    final_groups = []

    if not skip_cross_state:
        # Find name_aggressive values in 3+ states with same aff_abbr
        by_name = defaultdict(list)
        for (group_key, st, geo_key), members in multi_groups.items():
            by_name[group_key].append((st, geo_key, members))

        # Also include singletons for cross-state merging
        singleton_by_name = defaultdict(list)
        for (group_key, st, geo_key), members in state_groups.items():
            if len(members) == 1:
                singleton_by_name[group_key].append((st, geo_key, members))

        for group_key, state_member_list in by_name.items():
            if _is_generic_group_name(group_key, group_key):
                continue
            # Combine with singletons for this name
            all_state_members = state_member_list + singleton_by_name.get(group_key, [])
            states = set(st for st, _, _ in all_state_members if st)
            if len(states) < min_states:
                continue

            # Check if they share the same aff_abbr
            all_members = []
            for _, _, members in all_state_members:
                all_members.extend(members)

            if not _is_known_brand_key(group_key):
                affs = set(m['aff_abbr'] for m in all_members if m['aff_abbr'])
                if len(affs) != 1:
                    continue

            # Create cross-state group
            canonical = max(all_members, key=_rep_score)
            workers = _consolidated_workers(all_members)
            sorted_states = sorted(states)

            final_groups.append({
                'canonical_name': canonical['employer_name'],
                'canonical_employer_id': canonical['employer_id'],
                'state': None,  # multi-state
                'member_count': len(all_members),
                'consolidated_workers': workers,
                'is_cross_state': True,
                'states': sorted_states,
                'members': all_members,
            })

            # Mark these keys as merged
            for st, geo_key, _ in all_state_members:
                cross_state_merged.add((group_key, st, geo_key))

    # Phase 3: remaining single-state groups
    for (group_key, st, geo_key), members in multi_groups.items():
        if (group_key, st, geo_key) in cross_state_merged:
            continue

        canonical = max(members, key=_rep_score)
        workers = _consolidated_workers(members)

        final_groups.append({
            'canonical_name': canonical['employer_name'],
            'canonical_employer_id': canonical['employer_id'],
            'state': st or None,
            'member_count': len(members),
            'consolidated_workers': workers,
            'is_cross_state': False,
            'states': [st] if st else [],
            'members': members,
        })

    # Phase 4: Fuzzy post-merge (merge singletons into existing groups)
    merged = _fuzzy_post_merge(rows, final_groups)
    if merged:
        print(f"[group] Phase 4: fuzzy-merged {merged:,} singletons into existing groups")

    return final_groups


# ---------------------------------------------------------------------------
# NAICS-based group validation (post-processing)
# ---------------------------------------------------------------------------

# 2-digit NAICS -> super-sector label
NAICS_SUPER_SECTORS = {}
for _codes, _label in [
    ({31, 32, 33}, "Manufacturing"),
    ({42, 44, 45}, "Trade"),
    ({48, 49}, "Transport/Warehouse"),
    ({51, 52, 53, 54, 55, 56}, "Services"),
    ({61, 62}, "Healthcare/Education"),
    ({71, 72}, "Entertainment/Food"),
    ({21, 23}, "Construction/Mining"),
    ({11}, "Agriculture"),
    ({22}, "Utilities"),
    ({81}, "Other Services"),
    ({92}, "Government"),
]:
    for _c in _codes:
        NAICS_SUPER_SECTORS[_c] = _label


def _naics_to_super_sector(naics_code):
    """Map a NAICS code (string or int) to its super-sector label, or None."""
    if not naics_code:
        return None
    try:
        code_2 = int(str(naics_code)[:2])
    except (ValueError, TypeError):
        return None
    return NAICS_SUPER_SECTORS.get(code_2)


def _split_groups_by_naics(groups, min_group_size=5, dominance_threshold=0.80):
    """Split groups where members span multiple unrelated NAICS super-sectors.

    For each group with ``min_group_size``+ members that have NAICS data:
    - If one super-sector accounts for ``dominance_threshold``+ of members -> keep
    - Otherwise -> split into sub-groups by super-sector

    Members with NULL NAICS stay in the largest sub-group.

    Returns (new_groups, split_count) where new_groups replaces the input list.
    """
    new_groups = []
    split_count = 0

    for g in groups:
        members = g['members']
        if len(members) < min_group_size:
            new_groups.append(g)
            continue

        # Map members to super-sectors
        sector_map = defaultdict(list)  # sector_label -> [member]
        null_members = []
        for m in members:
            ss = _naics_to_super_sector(m.get('naics'))
            if ss is None:
                null_members.append(m)
            else:
                sector_map[ss].append(m)

        # If no NAICS data at all, keep group as-is
        if not sector_map:
            new_groups.append(g)
            continue

        total_with_naics = sum(len(v) for v in sector_map.values())
        # Check for dominant sector
        dominant = max(sector_map.items(), key=lambda kv: len(kv[1]))
        if len(dominant[1]) / total_with_naics >= dominance_threshold:
            new_groups.append(g)
            continue

        # Split: create one sub-group per super-sector
        split_count += 1
        sorted_sectors = sorted(sector_map.items(), key=lambda kv: -len(kv[1]))

        # Assign null-NAICS members to the largest sector sub-group
        sorted_sectors[0] = (sorted_sectors[0][0],
                             sorted_sectors[0][1] + null_members)

        for sector_label, sector_members in sorted_sectors:
            if len(sector_members) < 2:
                # Singletons after split don't form groups — skip them
                continue
            canonical = max(sector_members, key=_rep_score)
            workers = _consolidated_workers(sector_members)
            new_groups.append({
                'canonical_name': canonical['employer_name'],
                'canonical_employer_id': canonical['employer_id'],
                'state': g['state'],
                'member_count': len(sector_members),
                'consolidated_workers': workers,
                'is_cross_state': g['is_cross_state'],
                'states': g['states'],
                'members': sector_members,
            })

    return new_groups, split_count


def write_groups(conn, groups, dry_run=False):
    """Write groups to DB: TRUNCATE + rebuild."""
    if dry_run:
        print(f"[dry-run] Would write {len(groups)} groups")
        total_members = sum(g['member_count'] for g in groups)
        cross_state = sum(1 for g in groups if g['is_cross_state'])
        print(f"[dry-run] Total grouped employers: {total_members}")
        print(f"[dry-run] Cross-state groups: {cross_state}")
        top5 = sorted(groups, key=lambda g: g['member_count'], reverse=True)[:5]
        for g in top5:
            print(f"  {g['canonical_name']} ({g['state'] or 'multi'}): "
                  f"{g['member_count']} members, {g['consolidated_workers']} workers")
        return

    with conn.cursor() as cur:
        # Clear old data -- MUST clear f7 FK refs first, then delete groups
        # (DO NOT use TRUNCATE CASCADE -- it cascades to f7_employers_deduped!)
        cur.execute("UPDATE f7_employers_deduped SET canonical_group_id = NULL, is_canonical_rep = FALSE")
        cur.execute("DELETE FROM employer_canonical_groups")
        cur.execute("ALTER SEQUENCE employer_canonical_groups_group_id_seq RESTART WITH 1")

        for g in groups:
            cur.execute("""
                INSERT INTO employer_canonical_groups
                    (canonical_name, canonical_employer_id, state,
                     member_count, consolidated_workers, is_cross_state, states)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING group_id
            """, [
                g['canonical_name'], g['canonical_employer_id'],
                g['state'], g['member_count'], g['consolidated_workers'],
                g['is_cross_state'], g['states'],
            ])
            group_id = cur.fetchone()[0]

            # Update members
            member_ids = [m['employer_id'] for m in g['members']]
            cur.execute("""
                UPDATE f7_employers_deduped
                SET canonical_group_id = %s, is_canonical_rep = FALSE
                WHERE employer_id = ANY(%s)
            """, [group_id, member_ids])

            # Mark canonical rep
            cur.execute("""
                UPDATE f7_employers_deduped
                SET is_canonical_rep = TRUE
                WHERE employer_id = %s
            """, [g['canonical_employer_id']])

    conn.commit()
    print(f"[write] Wrote {len(groups)} groups to employer_canonical_groups")


def print_stats(groups):
    """Print summary statistics."""
    total_members = sum(g['member_count'] for g in groups)
    cross_state = sum(1 for g in groups if g['is_cross_state'])
    cs_members = sum(g['member_count'] for g in groups if g['is_cross_state'])
    workers = sum(g['consolidated_workers'] for g in groups)

    print(f"\n--- Canonical Grouping Stats ---")
    print(f"Total groups:             {len(groups):,}")
    print(f"Total grouped employers:  {total_members:,}")
    print(f"Cross-state groups:       {cross_state:,} ({cs_members:,} employers)")
    print(f"Single-state groups:      {len(groups) - cross_state:,}")
    print(f"Consolidated workers:     {workers:,}")

    # Size distribution
    sizes = defaultdict(int)
    for g in groups:
        mc = g['member_count']
        if mc >= 10:
            sizes['10+'] += 1
        elif mc >= 5:
            sizes['5-9'] += 1
        elif mc >= 3:
            sizes['3-4'] += 1
        else:
            sizes['2'] += 1

    print(f"\nGroup size distribution:")
    for label in ['2', '3-4', '5-9', '10+']:
        print(f"  {label}: {sizes.get(label, 0):,} groups")

    # Top 10
    top = sorted(groups, key=lambda g: g['member_count'], reverse=True)[:10]
    print(f"\nTop 10 groups by member count:")
    for g in top:
        state_label = ','.join(g['states'][:3]) if g['is_cross_state'] else (g['state'] or '??')
        if g['is_cross_state'] and len(g['states']) > 3:
            state_label += f"+{len(g['states'])-3}"
        print(f"  {g['canonical_name'][:50]:<50} {state_label:<15} "
              f"{g['member_count']:>4} members  {g['consolidated_workers']:>8,} workers")


def validate_groups(groups, max_mixed_naics=75):
    """Run post-build validation checks. Returns True if all checks pass."""
    from rapidfuzz import fuzz

    print("\n--- Validation Checks ---")
    ok = True

    # 1. Count groups with mixed 2-digit NAICS (>3 distinct codes)
    mixed_naics_groups = []
    for g in groups:
        naics_codes = set()
        for m in g['members']:
            n = m.get('naics')
            if n:
                try:
                    naics_codes.add(int(str(n)[:2]))
                except (ValueError, TypeError):
                    pass
        if len(naics_codes) > 3:
            mixed_naics_groups.append((g, len(naics_codes)))
    mixed_naics_groups.sort(key=lambda x: -x[1])

    print(f"[validate] Groups with >3 distinct NAICS sectors: {len(mixed_naics_groups)}")
    if mixed_naics_groups:
        for g, cnt in mixed_naics_groups[:10]:
            state = ','.join(g['states'][:3]) if g['is_cross_state'] else (g['state'] or '??')
            print(f"  {g['canonical_name'][:45]:<45} {state:<10} "
                  f"{g['member_count']:>4} members  {cnt} NAICS sectors")
    if len(mixed_naics_groups) > max_mixed_naics:
        print(f"  WARN: {len(mixed_naics_groups)} mixed-NAICS groups > threshold {max_mixed_naics}")
        ok = False

    # 2. Count groups where canonical_name doesn't match any member well
    poor_name_groups = []
    for g in groups:
        canon = g['canonical_name'] or ""
        best = 0
        for m in g['members']:
            ratio = fuzz.token_sort_ratio(canon, m.get('employer_name') or "")
            if ratio > best:
                best = ratio
        if best < 80:
            poor_name_groups.append((g, best))
    print(f"[validate] Groups with poor canonical name match (<80): {len(poor_name_groups)}")
    if poor_name_groups:
        for g, score in poor_name_groups[:5]:
            print(f"  {g['canonical_name'][:50]:<50} best_ratio={score}")

    # 3. Top 10 largest groups for manual review
    top = sorted(groups, key=lambda g: g['member_count'], reverse=True)[:10]
    print(f"\n[validate] Top 10 largest groups:")
    for g in top:
        state = ','.join(g['states'][:3]) if g['is_cross_state'] else (g['state'] or '??')
        if g['is_cross_state'] and len(g['states']) > 3:
            state += f"+{len(g['states'])-3}"
        # Collect NAICS super-sectors
        sectors = set()
        for m in g['members']:
            ss = _naics_to_super_sector(m.get('naics'))
            if ss:
                sectors.add(ss)
        sector_str = ','.join(sorted(sectors)[:3]) if sectors else 'no NAICS'
        print(f"  {g['canonical_name'][:45]:<45} {state:<15} "
              f"{g['member_count']:>4} members  [{sector_str}]")

    if ok:
        print("\n[validate] All checks passed.")
    else:
        print("\n[validate] Some checks FAILED — review output above.")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Build canonical employer groups")
    parser.add_argument('--dry-run', action='store_true', help="Print stats without writing")
    parser.add_argument('--skip-cross-state', action='store_true', help="Skip cross-state merge")
    parser.add_argument('--min-states', type=int, default=2, help="Min states for cross-state merge")
    parser.add_argument('--validate', action='store_true', help="Run post-build validation checks")
    parser.add_argument('--skip-naics-split', action='store_true', help="Skip NAICS-based group splitting")
    args = parser.parse_args()

    conn = get_connection()
    try:
        # Ensure schema
        ensure_schema(conn)

        # Load employers
        print("[load] Loading f7_employers_deduped...")
        rows = load_employers(conn)
        print(f"[load] Loaded {len(rows):,} employers")

        # Build groups
        print("[group] Building canonical groups...")
        groups = build_groups(rows,
                             skip_cross_state=args.skip_cross_state,
                             min_states=args.min_states)
        print(f"[group] Built {len(groups):,} groups (pre-NAICS split)")

        # NAICS-based group splitting
        if not args.skip_naics_split:
            groups, split_count = _split_groups_by_naics(groups)
            if split_count:
                print(f"[group] NAICS split: {split_count} groups split by sector "
                      f"-> {len(groups):,} groups total")

        # Print stats
        print_stats(groups)

        # Validate
        if args.validate:
            valid = validate_groups(groups)

        # Write
        write_groups(conn, groups, dry_run=args.dry_run)

        if not args.dry_run:
            # Verify
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM employer_canonical_groups")
                gc = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE canonical_group_id IS NOT NULL")
                ec = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE is_canonical_rep = TRUE")
                rc = cur.fetchone()[0]
                print(f"\n[verify] Groups: {gc:,}, Grouped employers: {ec:,}, Canonical reps: {rc:,}")

        if args.validate and not valid:
            sys.exit(1)

    finally:
        conn.close()


if __name__ == '__main__':
    main()
