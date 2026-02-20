"""Export deduplicated NY employer-union list (v2 - collapsed).

One row per real employer, collapsed using canonical groups + fuzzy dedup.
Multi-employer agreements flagged separately. Public sector at the top.

employer_type values:
  PUBLIC_SECTOR         - Manual public-sector entries (NYSUT, CSEA, DC37, etc.)
  CANONICAL_GROUP       - Collapsed from canonical employer grouping
  SINGLE_EMPLOYER       - Ungrouped F7 employer, one location
  FUZZY_COLLAPSED       - Ungrouped 10K+ employers collapsed by name similarity
  MULTI_EMPLOYER_AGREEMENT - Industry-wide / signatory agreements (SAG-AFTRA, RAB, etc.)
  NLRB_ELECTION         - Unmatched NLRB election wins
  NLRB_VR               - Unmatched NLRB voluntary recognition

Sources:
1. f7_employers_deduped + canonical groups + mv_employer_data_sources
2. Manual employers (public sector at top)
3. NLRB election wins not matched to F7
4. NLRB VR not matched to F7
"""
import csv
import re
from collections import Counter, defaultdict
from db_config import get_connection

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    print("WARNING: rapidfuzz not installed -- skipping fuzzy dedup of large employers")

conn = get_connection()
cur = conn.cursor()

output_file = "ny_employers_deduped.csv"

# ── Patterns to detect multi-employer agreement filings ──
MULTI_EMPLOYER_PATTERNS = [
    r'\bmultiple companies\b',
    r'\bindependent contractors\b',
    r'(?:^|\s)various(?:\s|$)',               # city or name = "VARIOUS"
    r'\b\d{4}\b.*\b(?:code|agreement|agt\.?)\b',  # "2016 ... Code/Agreement/Agt"
    r'\bjoint policy\b',
    r'\bmaster agreement\b',
    r'\bgeneral agreement\b',
    r'\bcontractors agreement\b',
    r'\bbuilding (?:agreement|agt\.?)\b',
    r'\bwindow cleaners (?:agreement|agt\.?)\b',
    r'\bsuperintendent (?:agreement|agt\.?)\b',
    r'\bcommercials?\s+(?:and/or\s+)?(?:audio\s+)?commercials?\s+code\b',
    r'\bnational code of fair practice\b',
    r'\bamptp\b',
    r'\btv code\b',
    r'\brab\b.*\b(?:agreement|agt\.?)\b',
    r'\btruckers association\b.*\b(?:agreement|agt\.?)\b',
    r'@\s*multiple locations',
    r'\bmaster rab\b',
    r'\band its members\b',                   # "RAB and its members"
    r'\bsecurity officers owners\b',          # RAB security officers agreements
    r'\bapartment (?:building|house)\b.*\bagt\.?\b',
]
MULTI_EMPLOYER_RE = re.compile('|'.join(MULTI_EMPLOYER_PATTERNS), re.IGNORECASE)


def is_multi_employer(name):
    """Detect multi-employer agreement filings by name pattern."""
    return bool(name and MULTI_EMPLOYER_RE.search(name))


def normalize_union(name):
    """Normalize union name for dedup (strip N/A, a/w, affiliation suffixes)."""
    if not name:
        return ''
    n = name.upper().strip()
    n = re.sub(r'\s+N/A\b', '', n)
    n = re.sub(r',?\s*(?:AFFILIATED WITH|A/W)\s+.*', '', n)
    n = re.sub(r'\s*/\s*SEIU\b', '', n)
    n = re.sub(r',?\s+SEIU\b', '', n)
    n = re.sub(r'\s+-\s+SERVICE EMPLOYEES.*', '', n)
    return n.strip().rstrip(',').strip()


def dedup_union_names(names):
    """Deduplicate union name variants. Returns list of representative names."""
    if not names:
        return []
    groups = defaultdict(list)
    for name in names:
        norm = normalize_union(name)
        if norm:
            groups[norm].append(name)
    # Pick shortest variant per normalized group (tends to be cleanest)
    return [min(variants, key=len) for variants in groups.values()]


def build_sources_str(d):
    """Build comma-separated data source string from flag dict."""
    sources = ['F7']
    for flag, label in [('has_osha', 'OSHA'), ('has_nlrb', 'NLRB'), ('has_whd', 'WHD'),
                        ('has_990', '990'), ('has_sam', 'SAM'), ('has_sec', 'SEC'),
                        ('has_gleif', 'GLEIF'), ('has_mergent', 'Mergent')]:
        if d.get(flag):
            sources.append(label)
    return ', '.join(sources)


def merge_source_flags(members):
    """Merge data source flags across group members (OR logic)."""
    sources = ['F7']
    for flag, label in [('has_osha', 'OSHA'), ('has_nlrb', 'NLRB'), ('has_whd', 'WHD'),
                        ('has_990', '990'), ('has_sam', 'SAM'), ('has_sec', 'SEC'),
                        ('has_gleif', 'GLEIF'), ('has_mergent', 'Mergent')]:
        if any(m.get(flag) for m in members):
            sources.append(label)
    return ', '.join(sources)


def first_nonempty(members, key):
    """Return first non-empty value for key across members."""
    for m in members:
        if m.get(key):
            return m[key]
    return ''


def normalize_employer_name(name):
    """Normalize employer name for fuzzy matching."""
    if not name:
        return ''
    n = name.upper().strip()
    for suffix in [', INC.', ', INC', ' INC.', ' INC', ', LLC', ' LLC',
                   ', LP', ' LP', ', LTD', ' LTD', ' CORP.', ' CORP',
                   ' CORPORATION', ' COMPANY', ' COMPANIES', ' CO.', ' CO',
                   ' GROUP', ' HOLDINGS', ' ENTERPRISES', ' D/B/A']:
        if n.endswith(suffix):
            n = n[:-len(suffix)]
    return n.strip()


def fetchall_dicts(cursor):
    """Fetch all rows as list of dicts (works with regular or RealDictCursor)."""
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def single_row(d, employer_type='SINGLE_EMPLOYER'):
    """Convert a single F7 employer dict to an output row."""
    latest = d.get('latest_notice_date')
    return {
        'employer_name': d['employer_name'],
        'city': d.get('city') or '',
        'state': 'NY',
        'zip': d.get('zip') or '',
        'naics': d.get('naics') or '',
        'sector': d.get('effective_sector', 'Private'),
        'employer_type': employer_type,
        'workers': d.get('latest_unit_size'),
        'union_names': d.get('latest_union_name') or '',
        'union_count': 1 if d.get('latest_union_name') else 0,
        'affiliation': d.get('aff_abbr') or '',
        'latest_date': str(latest) if latest else '',
        'time_period': 'Current' if latest and str(latest) >= '2020' else 'Historical',
        'data_sources': build_sources_str(d),
        'source_count': d.get('source_count') or 0,
        'location_count': 1,
        'locations': d.get('city') or '',
        'canonical_group_id': d.get('canonical_group_id') or '',
        'ein': d.get('ein') or '',
        'is_public_company': 'Y' if d.get('is_public') else '',
        'is_federal_contractor': 'Y' if d.get('is_federal_contractor') else '',
        'primary_source': 'F7_OLMS',
        'employer_id': d['employer_id'],
    }


def collapse_rows(members, employer_type, canonical_name=None, group_id=None):
    """Collapse multiple F7 employer dicts into a single output row."""
    # Pick representative: prefer is_canonical_rep, else largest
    rep = next((m for m in members if m.get('is_canonical_rep')), None)
    if not rep:
        rep = max(members, key=lambda x: x.get('latest_unit_size') or 0)

    # Deduplicated union names
    raw_unions = [m['latest_union_name'] for m in members if m.get('latest_union_name')]
    clean_unions = dedup_union_names(raw_unions)

    # Distinct cities
    seen = set()
    cities = []
    for m in members:
        c = (m.get('city') or '').strip()
        if c and c.upper() not in seen:
            seen.add(c.upper())
            cities.append(c)

    total_workers = sum(m.get('latest_unit_size') or 0 for m in members)
    dates = [m['latest_notice_date'] for m in members if m.get('latest_notice_date')]
    latest_date = max(dates) if dates else None
    sectors = [m.get('effective_sector', 'Private') for m in members]
    sector = Counter(sectors).most_common(1)[0][0]

    return {
        'employer_name': canonical_name or rep['employer_name'],
        'city': rep.get('city') or '',
        'state': 'NY',
        'zip': rep.get('zip') or '',
        'naics': first_nonempty(members, 'naics') or '',
        'sector': sector,
        'employer_type': employer_type,
        'workers': total_workers,
        'union_names': ' | '.join(clean_unions),
        'union_count': len(clean_unions),
        'affiliation': first_nonempty(members, 'aff_abbr') or '',
        'latest_date': str(latest_date) if latest_date else '',
        'time_period': 'Current' if latest_date and str(latest_date) >= '2020' else 'Historical',
        'data_sources': merge_source_flags(members),
        'source_count': max((m.get('source_count') or 0) for m in members),
        'location_count': len(cities),
        'locations': ' | '.join(cities),
        'canonical_group_id': group_id or '',
        'ein': first_nonempty(members, 'ein') or '',
        'is_public_company': 'Y' if any(m.get('is_public') for m in members) else '',
        'is_federal_contractor': 'Y' if any(m.get('is_federal_contractor') for m in members) else '',
        'primary_source': 'F7_OLMS',
        'employer_id': rep['employer_id'],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 1. Pull all NY F7 employers with canonical group + data source info
# ══════════════════════════════════════════════════════════════════════════════
print("1. Pulling all NY F7 employers...")
cur.execute("""
    SELECT
        e.employer_id, e.employer_name, e.city, e.state, e.zip, e.naics,
        e.latest_unit_size, e.latest_notice_date,
        e.latest_union_name, e.latest_union_fnum,
        e.canonical_group_id, e.is_canonical_rep,
        ecg.canonical_name,
        um.aff_abbr,
        CASE
            WHEN um.sector IN ('PRIVATE', 'OTHER', 'RAILROAD_AIRLINE_RLA') THEN 'Private'
            WHEN um.sector IN ('PUBLIC_SECTOR', 'FEDERAL') THEN 'Public'
            ELSE 'Private'
        END AS effective_sector,
        ds.has_osha, ds.has_nlrb, ds.has_whd, ds.has_990,
        ds.has_sam, ds.has_sec, ds.has_gleif, ds.has_mergent,
        ds.source_count, ds.is_public, ds.is_federal_contractor, ds.ein
    FROM f7_employers_deduped e
    LEFT JOIN employer_canonical_groups ecg ON e.canonical_group_id = ecg.group_id
    LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num::text
    LEFT JOIN mv_employer_data_sources ds ON e.employer_id = ds.employer_id
    WHERE e.state = 'NY'
    ORDER BY e.latest_unit_size DESC NULLS LAST
""")
f7_all = fetchall_dicts(cur)
print(f"  {len(f7_all):,} F7 employers in NY")

# ── Separate multi-employer agreements from real employers ──
multi_emp = [d for d in f7_all if is_multi_employer(d['employer_name'])]
real_emp = [d for d in f7_all if not is_multi_employer(d['employer_name'])]
print(f"  {len(multi_emp):,} multi-employer agreements")
print(f"  {len(real_emp):,} real employers")

# ── Group by canonical_group_id ──
groups = defaultdict(list)
ungrouped = []
for d in real_emp:
    gid = d['canonical_group_id']
    if gid:
        groups[gid].append(d)
    else:
        ungrouped.append(d)

grouped_count = sum(len(v) for v in groups.values())
print(f"  {len(groups):,} canonical groups covering {grouped_count:,} employers")
print(f"  {len(ungrouped):,} ungrouped employers")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Collapse canonical groups into one row each
# ══════════════════════════════════════════════════════════════════════════════
print("\n2. Collapsing canonical groups...")
f7_rows = []

for gid, members in groups.items():
    canonical_name = members[0].get('canonical_name')
    f7_rows.append(collapse_rows(members, 'CANONICAL_GROUP',
                                 canonical_name=canonical_name, group_id=gid))

print(f"  {len(f7_rows):,} collapsed group rows")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Fuzzy dedup large ungrouped employers (>=10K workers)
# ══════════════════════════════════════════════════════════════════════════════
print("\n3. Fuzzy dedup for large ungrouped employers (>=10K workers)...")
large = [d for d in ungrouped if (d['latest_unit_size'] or 0) >= 10000]
small = [d for d in ungrouped if (d['latest_unit_size'] or 0) < 10000]
print(f"  {len(large):,} large ungrouped, {len(small):,} small ungrouped")

fuzzy_collapsed_count = 0
if HAS_RAPIDFUZZ and large:
    used = set()
    for i, emp in enumerate(large):
        if i in used:
            continue
        cluster = [emp]
        name_i = normalize_employer_name(emp['employer_name'])
        for j in range(i + 1, len(large)):
            if j in used:
                continue
            name_j = normalize_employer_name(large[j]['employer_name'])
            if fuzz.token_sort_ratio(name_i, name_j) >= 80:
                cluster.append(large[j])
                used.add(j)
        used.add(i)

        if len(cluster) > 1:
            row = collapse_rows(cluster, 'FUZZY_COLLAPSED')
            f7_rows.append(row)
            fuzzy_collapsed_count += len(cluster)
            print(f"    Collapsed {len(cluster)} rows: "
                  f"{row['employer_name'][:50]} -> {row['workers']:,} workers, "
                  f"{row['location_count']} locations")
        else:
            f7_rows.append(single_row(emp))
else:
    for emp in large:
        f7_rows.append(single_row(emp))

if fuzzy_collapsed_count:
    print(f"  Fuzzy-collapsed {fuzzy_collapsed_count} employer rows into fewer rows")

# Small ungrouped employers -- emit as-is
for d in small:
    f7_rows.append(single_row(d))

print(f"  Total F7 output rows: {len(f7_rows):,}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Multi-employer agreement rows (flagged, not collapsed)
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n4. {len(multi_emp):,} multi-employer agreement rows (flagged)")
multi_rows = [single_row(d, 'MULTI_EMPLOYER_AGREEMENT') for d in multi_emp]


# ══════════════════════════════════════════════════════════════════════════════
# 5. Manual employers (public sector at top of CSV)
# ══════════════════════════════════════════════════════════════════════════════
print("\n5. Pulling manual employers...")
cur.execute("""
    SELECT employer_name, city, state, union_name, affiliation, local_number,
           num_employees, recognition_type, recognition_date, naics_sector, sector
    FROM manual_employers WHERE state = 'NY'
    ORDER BY num_employees DESC NULLS LAST
""")
manual_raw = fetchall_dicts(cur)
print(f"  {len(manual_raw):,} manual employers")

public_rows = []
for d in manual_raw:
    is_pub = (d.get('sector') or '').upper() == 'PUBLIC'
    public_rows.append({
        'employer_name': d['employer_name'],
        'city': d.get('city') or '',
        'state': 'NY',
        'zip': '',
        'naics': d.get('naics_sector') or '',
        'sector': 'Public' if is_pub else 'Private',
        'employer_type': 'PUBLIC_SECTOR' if is_pub else 'SINGLE_EMPLOYER',
        'workers': d.get('num_employees'),
        'union_names': d.get('union_name') or '',
        'union_count': 1 if d.get('union_name') else 0,
        'affiliation': d.get('affiliation') or '',
        'latest_date': str(d['recognition_date']) if d.get('recognition_date') else '',
        'time_period': 'Current',
        'data_sources': 'Manual',
        'source_count': 1,
        'location_count': 1,
        'locations': d.get('city') or '',
        'canonical_group_id': '',
        'ein': '',
        'is_public_company': '',
        'is_federal_contractor': '',
        'primary_source': 'MANUAL',
        'employer_id': '',
    })


# ══════════════════════════════════════════════════════════════════════════════
# 6. Unmatched NLRB VR
# ══════════════════════════════════════════════════════════════════════════════
print("\n6. Pulling unmatched NLRB VR...")
cur.execute("""
    SELECT employer_name, unit_city, unit_state, union_name, extracted_affiliation,
           num_employees, date_voluntary_recognition
    FROM nlrb_voluntary_recognition
    WHERE unit_state = 'NY' AND matched_employer_id IS NULL
    ORDER BY num_employees DESC NULLS LAST
""")
vr_raw = fetchall_dicts(cur)
print(f"  {len(vr_raw):,} unmatched VR cases")

vr_rows = []
for d in vr_raw:
    vr_rows.append({
        'employer_name': d['employer_name'],
        'city': d.get('unit_city') or '',
        'state': 'NY',
        'zip': '',
        'naics': '',
        'sector': 'Private',
        'employer_type': 'NLRB_VR',
        'workers': d.get('num_employees'),
        'union_names': d.get('union_name') or '',
        'union_count': 1 if d.get('union_name') else 0,
        'affiliation': d.get('extracted_affiliation') or '',
        'latest_date': str(d['date_voluntary_recognition']) if d.get('date_voluntary_recognition') else '',
        'time_period': 'Current',
        'data_sources': 'NLRB_VR',
        'source_count': 1,
        'location_count': 1,
        'locations': d.get('unit_city') or '',
        'canonical_group_id': '',
        'ein': '',
        'is_public_company': '',
        'is_federal_contractor': '',
        'primary_source': 'NLRB_VR',
        'employer_id': '',
    })


# ══════════════════════════════════════════════════════════════════════════════
# 7. Unmatched NLRB election wins (deduped by employer+city)
# ══════════════════════════════════════════════════════════════════════════════
print("\n7. Pulling unmatched NLRB election wins...")
cur.execute("""
    SELECT
        p_emp.participant_name AS employer_name,
        p_emp.city, p_emp.state, p_emp.zip,
        MAX(e.eligible_voters) AS max_eligible,
        MAX(e.election_date) AS latest_election,
        COUNT(*) AS election_count,
        STRING_AGG(DISTINCT p_union.participant_name, ' | ') AS union_names
    FROM nlrb_elections e
    JOIN nlrb_participants p_emp ON e.case_number = p_emp.case_number
        AND p_emp.participant_type = 'Employer'
    LEFT JOIN nlrb_participants p_union ON e.case_number = p_union.case_number
        AND p_union.participant_type IN ('Petitioner', 'Labor Organization / Union 1')
    WHERE p_emp.state = 'NY'
        AND e.union_won = true
        AND p_emp.matched_employer_id IS NULL
    GROUP BY p_emp.participant_name, p_emp.city, p_emp.state, p_emp.zip
    ORDER BY max_eligible DESC NULLS LAST
""")
elec_raw = fetchall_dicts(cur)
print(f"  {len(elec_raw):,} unique unmatched election-win employers")

nlrb_rows = []
for d in elec_raw:
    unions_str = d.get('union_names') or ''
    union_list = [u.strip() for u in unions_str.split('|') if u.strip()]
    latest = d.get('latest_election')
    nlrb_rows.append({
        'employer_name': d['employer_name'],
        'city': d.get('city') or '',
        'state': 'NY',
        'zip': d.get('zip') or '',
        'naics': '',
        'sector': 'Private',
        'employer_type': 'NLRB_ELECTION',
        'workers': d.get('max_eligible'),
        'union_names': unions_str,
        'union_count': len(union_list),
        'affiliation': '',
        'latest_date': str(latest) if latest else '',
        'time_period': 'Current' if latest and str(latest) >= '2020' else 'Historical',
        'data_sources': f"NLRB_ELECTION (x{d['election_count']})",
        'source_count': 1,
        'location_count': 1,
        'locations': d.get('city') or '',
        'canonical_group_id': '',
        'ein': '',
        'is_public_company': '',
        'is_federal_contractor': '',
        'primary_source': 'NLRB_ELECTION',
        'employer_id': '',
    })


# ══════════════════════════════════════════════════════════════════════════════
# Assemble final CSV: public sector at top, then F7, multi, NLRB
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Assembling final output...")

# Sort F7 rows and multi rows by workers DESC
f7_rows.sort(key=lambda r: r.get('workers') or 0, reverse=True)
multi_rows.sort(key=lambda r: r.get('workers') or 0, reverse=True)

all_rows = public_rows + f7_rows + multi_rows + nlrb_rows + vr_rows

fieldnames = [
    'employer_name', 'city', 'state', 'zip', 'naics', 'sector', 'employer_type',
    'workers', 'union_names', 'union_count', 'affiliation',
    'latest_date', 'time_period', 'data_sources', 'source_count',
    'location_count', 'locations', 'canonical_group_id', 'ein',
    'is_public_company', 'is_federal_contractor', 'primary_source', 'employer_id',
]

print(f"Writing {len(all_rows):,} rows to {output_file}...")
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Done! {output_file}\n")

# ── Summary ──
print("=" * 60)
print("SUMMARY")
print("=" * 60)

print("\n--- By employer_type ---")
for k, v in Counter(r['employer_type'] for r in all_rows).most_common():
    print(f"  {k:<30} {v:>6,}")

print("\n--- By primary_source ---")
for k, v in Counter(r['primary_source'] for r in all_rows).most_common():
    print(f"  {k:<30} {v:>6,}")

print("\n--- By sector ---")
for k, v in Counter(r['sector'] for r in all_rows).most_common():
    print(f"  {k:<30} {v:>6,}")

print("\n--- By time_period ---")
for k, v in Counter(r['time_period'] for r in all_rows).most_common():
    print(f"  {k:<30} {v:>6,}")

print("\n--- Top 25 by workers ---")
for r in all_rows[:25]:
    w = r.get('workers') or 0
    t = r['employer_type']
    n = r['employer_name'][:55]
    lc = r.get('location_count', 1)
    loc_str = f" ({lc} loc)" if lc and lc > 1 else ""
    print(f"  {w:>10,}  [{t:<25}] {n}{loc_str}")

# Spot-check key employers
print("\n--- Spot checks ---")
for name_pat in ['Starbucks', 'Verizon', 'SAG-AFTRA', 'NYSUT', 'CSEA', 'DC 37',
                  'Joint Policy', 'RAB', 'South Shore']:
    matches = [r for r in all_rows if name_pat.lower() in r['employer_name'].lower()]
    if matches:
        print(f"\n  '{name_pat}' -> {len(matches)} row(s):")
        for m in matches[:3]:
            w = m.get('workers') or 0
            print(f"    {m['employer_type']:<25} {w:>8,} workers  "
                  f"{m['employer_name'][:50]}  loc={m.get('location_count', 1)}")
        if len(matches) > 3:
            print(f"    ... and {len(matches) - 3} more")

print(f"\nTotal rows: {len(all_rows):,}")

cur.close()
conn.close()
