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
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from src.python.matching.name_normalization import normalize_name_aggressive


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

    # Build per-state index: state -> [(group_index, name_aggressive)]
    group_by_state = defaultdict(list)
    for idx, g in enumerate(groups):
        # Use canonical rep's name_aggressive
        canon_na = None
        for m in g['members']:
            if m['employer_id'] == g['canonical_employer_id']:
                canon_na = m['name_aggressive']
                break
        if not canon_na:
            canon_na = g['members'][0]['name_aggressive']

        if g['is_cross_state']:
            for st in (g['states'] or []):
                group_by_state[st].append((idx, canon_na))
        else:
            st = (g['state'] or '').upper()
            group_by_state[st].append((idx, canon_na))

    # Find ungrouped singletons
    singletons = [r for r in rows
                  if r['employer_id'] not in grouped_ids
                  and r['name_aggressive'] and r['name_aggressive'].strip()
                  and r.get('exclude_reason') not in SKIP_REASONS]

    merged = 0
    for r in singletons:
        na = r['name_aggressive']
        if len(na) <= 4:
            continue
        st = (r['state'] or '').upper().strip()

        best_ratio = 0
        best_idx = None

        for idx, canon_na in group_by_state.get(st, []):
            if len(canon_na) <= 4:
                continue
            ratio = fuzz.token_set_ratio(na, canon_na)
            if ratio >= min_ratio and ratio > best_ratio:
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
            SELECT e.employer_id, e.employer_name, e.name_aggressive, e.state,
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
    # Phase 0: Recompute name_aggressive in-memory with latest normalizer
    recomputed = 0
    for r in rows:
        old_na = r['name_aggressive']
        new_na = normalize_name_aggressive(r['employer_name'] or '')
        if new_na != old_na:
            recomputed += 1
        r['name_aggressive'] = new_na
    if recomputed:
        print(f"[group] Phase 0: recomputed {recomputed:,} name_aggressive values in-memory")

    # Phase 1: group by (name_aggressive, state)
    state_groups = defaultdict(list)
    for r in rows:
        na = r['name_aggressive']
        if not na or not na.strip():
            continue
        # Skip signatory patterns
        if r['exclude_reason'] in SKIP_REASONS:
            continue
        st = (r['state'] or '').upper().strip()
        key = (na, st)
        state_groups[key].append(r)

    # Only keep groups with 2+ members
    multi_groups = {k: v for k, v in state_groups.items() if len(v) >= 2}

    # Phase 2: cross-state merge
    cross_state_merged = set()  # keys already merged
    final_groups = []

    if not skip_cross_state:
        # Find name_aggressive values in 3+ states with same aff_abbr
        by_name = defaultdict(list)
        for (na, st), members in multi_groups.items():
            by_name[na].append((st, members))

        # Also include singletons for cross-state merging
        singleton_by_name = defaultdict(list)
        for (na, st), members in state_groups.items():
            if len(members) == 1:
                singleton_by_name[na].append((st, members))

        for na, state_member_list in by_name.items():
            # Combine with singletons for this name
            all_state_members = state_member_list + singleton_by_name.get(na, [])
            states = set(st for st, _ in all_state_members)
            if len(states) < min_states:
                continue

            # Check if they share the same aff_abbr
            all_members = []
            for _, members in all_state_members:
                all_members.extend(members)

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
            for st, _ in all_state_members:
                cross_state_merged.add((na, st))

    # Phase 3: remaining single-state groups
    for (na, st), members in multi_groups.items():
        if (na, st) in cross_state_merged:
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


def main():
    parser = argparse.ArgumentParser(description="Build canonical employer groups")
    parser.add_argument('--dry-run', action='store_true', help="Print stats without writing")
    parser.add_argument('--skip-cross-state', action='store_true', help="Skip cross-state merge")
    parser.add_argument('--min-states', type=int, default=2, help="Min states for cross-state merge")
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
        print(f"[group] Built {len(groups):,} groups")

        # Print stats
        print_stats(groups)

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

    finally:
        conn.close()


if __name__ == '__main__':
    main()
