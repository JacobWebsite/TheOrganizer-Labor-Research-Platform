"""
AFSCME New York Locals Analysis
Checks membership counts from OLMS and 990 data, handling known duplications:
- CSEA Regions 1-6 are duplicated counts (rolled up to CSEA Local 1000)
- DC37 locals may have duplicate LM filings
"""

import psycopg2
from collections import defaultdict

DB_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

# CSEA Regions 1-6 are duplicates of Local 1000 (CSEA main)
CSEA_REGION_LOCALS = ['1', '2', '3', '4', '5', '6']
CSEA_MAIN_LOCAL = '1000'

# DC37 locals list (for duplicate detection)
DC37_LOCALS = [
    95, 154, 205, 215, 253, 299, 371, 372, 374, 375, 376, 384, 389, 420, 436,
    461, 508, 768, 924, 957, 983, 1070, 1087, 1113, 1157, 1189, 1251, 1306,
    1320, 1321, 1322, 1359, 1407, 1455, 1482, 1501, 1502, 1503, 1505, 1506,
    1507, 1508, 1549, 1559, 1597, 1655, 1740, 1757, 1797, 1930, 1931, 2054,
    2507, 2627, 2906, 3005, 3333, 3599, 3621, 3652, 3778, 5911
]

DC37_MAIN_LOCAL = '37'


def get_afscme_ny_locals():
    """Get all AFSCME locals in NY from OLMS."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    query = """
        SELECT
            f_num,
            union_name,
            local_number,
            desig_name,
            city,
            members,
            yr_covered
        FROM unions_master
        WHERE aff_abbr = 'AFSCME'
          AND state = 'NY'
        ORDER BY members DESC NULLS LAST
    """

    cur.execute(query)
    rows = cur.fetchall()

    locals_data = []
    for row in rows:
        locals_data.append({
            'f_num': row[0],
            'union_name': row[1],
            'local_number': row[2],
            'desig_name': row[3].strip() if row[3] else '',
            'city': row[4] or '',
            'members': row[5] or 0,
            'yr_covered': row[6] or ''
        })

    conn.close()
    return locals_data


def get_csea_data():
    """Get CSEA and its regions specifically."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # CSEA main and regions
    query = """
        SELECT
            f_num,
            union_name,
            local_number,
            desig_name,
            members,
            yr_covered
        FROM unions_master
        WHERE (union_name ILIKE '%CSEA%' OR union_name ILIKE '%CIVIL SERVICE EMPLOYEES%')
          AND state = 'NY'
          AND aff_abbr = 'AFSCME'
        ORDER BY members DESC NULLS LAST
    """

    cur.execute(query)
    rows = cur.fetchall()

    conn.close()

    csea_data = []
    for row in rows:
        csea_data.append({
            'f_num': row[0],
            'union_name': row[1],
            'local_number': row[2],
            'desig_name': row[3].strip() if row[3] else '',
            'members': row[4] or 0,
            'yr_covered': row[5] or ''
        })

    return csea_data


def get_dc37_data():
    """Get DC37 and its locals."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # DC37 main council
    query = """
        SELECT
            f_num,
            union_name,
            local_number,
            desig_name,
            members,
            yr_covered
        FROM unions_master
        WHERE (union_name ILIKE '%DC 37%' OR union_name ILIKE '%DC37%'
               OR union_name ILIKE '%DISTRICT COUNCIL 37%'
               OR union_name ILIKE '%DIST COUN 37%')
          AND state = 'NY'
          AND aff_abbr = 'AFSCME'
        ORDER BY members DESC NULLS LAST
    """

    cur.execute(query)
    dc37_council = cur.fetchall()

    # Get locals that are part of DC37
    local_nums_str = ','.join([f"'{n}'" for n in DC37_LOCALS])
    query2 = f"""
        SELECT
            f_num,
            union_name,
            local_number,
            desig_name,
            members,
            yr_covered
        FROM unions_master
        WHERE aff_abbr = 'AFSCME'
          AND state = 'NY'
          AND local_number IN ({local_nums_str})
        ORDER BY local_number::integer
    """

    cur.execute(query2)
    dc37_locals = cur.fetchall()

    conn.close()

    return dc37_council, dc37_locals


def get_990_afscme_ny():
    """Get AFSCME NY data from Form 990 estimates."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'form_990_estimates'
        )
    """)
    if not cur.fetchone()[0]:
        conn.close()
        return []

    query = """
        SELECT
            organization_name,
            ein,
            dues_revenue,
            estimated_members,
            dues_rate_used,
            dues_rate_source
        FROM form_990_estimates
        WHERE org_type LIKE 'AFSCME%'
          AND (state = 'NY' OR organization_name ILIKE '%NEW YORK%'
               OR organization_name ILIKE '%NY%')
        ORDER BY estimated_members DESC NULLS LAST
    """

    cur.execute(query)
    rows = cur.fetchall()

    conn.close()

    data = []
    for row in rows:
        data.append({
            'name': row[0],
            'ein': row[1],
            'dues_revenue': float(row[2]) if row[2] else 0,
            'estimated_members': row[3] or 0,
            'dues_rate': float(row[4]) if row[4] else 0,
            'rate_source': row[5] or ''
        })

    return data


def get_employers_990_afscme_ny():
    """Get AFSCME-related employers from 990 data."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'employers_990'
        )
    """)
    if not cur.fetchone()[0]:
        conn.close()
        return []

    query = """
        SELECT
            name,
            ein,
            employee_count,
            total_revenue,
            city,
            state
        FROM employers_990
        WHERE state = 'NY'
        ORDER BY employee_count DESC NULLS LAST
        LIMIT 50
    """

    cur.execute(query)
    rows = cur.fetchall()

    conn.close()

    return rows


def analyze_duplicates(locals_data):
    """Identify potential duplicate filings."""
    by_local_number = defaultdict(list)

    for local in locals_data:
        if local['local_number']:
            by_local_number[local['local_number']].append(local)

    duplicates = {k: v for k, v in by_local_number.items() if len(v) > 1}
    return duplicates


def print_report(locals_data, csea_data, dc37_council, dc37_locals, form_990_data):
    """Print comprehensive analysis report."""

    print("\n" + "="*80)
    print("AFSCME NEW YORK LOCALS ANALYSIS")
    print("="*80)

    # Overall stats
    total_locals = len(locals_data)
    total_members_raw = sum(l['members'] for l in locals_data)

    print(f"\n{'OLMS Summary (Raw)':<40}")
    print("-"*50)
    print(f"  Total AFSCME NY records: {total_locals}")
    print(f"  Total members (raw): {total_members_raw:,}")

    # CSEA Analysis - look for Local 1000 and Locals 1-6 (regions)
    print(f"\n{'CSEA Analysis (Local 1000 = Main, Locals 1-6 = Regions)':<60}")
    print("-"*80)

    csea_main = None
    csea_regions = []

    for local in locals_data:
        if local['local_number'] == CSEA_MAIN_LOCAL:
            csea_main = local
        elif local['local_number'] in CSEA_REGION_LOCALS:
            csea_regions.append(local)

    if csea_main:
        print(f"  CSEA Main (Local 1000):")
        print(f"    F#: {csea_main['f_num']}")
        print(f"    Name: {csea_main['union_name']}")
        print(f"    City: {csea_main['city']}")
        print(f"    Members: {csea_main['members']:,}")

    if csea_regions:
        print(f"\n  CSEA Regions 1-6 (DUPLICATED - members already in Local 1000):")
        region_total = 0
        for r in sorted(csea_regions, key=lambda x: int(x['local_number']) if x['local_number'].isdigit() else 0):
            print(f"    Local {r['local_number']:<4} {r['city']:<20} {r['members']:>10,}")
            region_total += r['members']
        print(f"    {'-'*36}")
        print(f"    {'Region Total (DUPLICATE):':<24} {region_total:>10,}")
        print(f"\n  WARNING:  These {region_total:,} members should NOT be added to CSEA's {csea_main['members'] if csea_main else 0:,}")

    # DC37 Analysis
    print(f"\n{'DC37 Analysis':<40}")
    print("-"*50)

    dc37_main = None
    for d in dc37_council:
        print(f"  DC37 Council: {d[1][:50]}")
        print(f"    F#: {d[0]}, Members: {d[4] or 0:,}")
        if d[4] and d[4] > 50000:
            dc37_main = {'f_num': d[0], 'members': d[4]}

    print(f"\n  DC37 Locals Found in OLMS ({len(dc37_locals)} of {len(DC37_LOCALS)} expected):")
    dc37_locals_members = 0
    dc37_found_nums = set()
    for d in dc37_locals:
        local_num = d[2]
        members = d[4] or 0
        dc37_locals_members += members
        dc37_found_nums.add(local_num)
        if members > 1000:  # Only show larger ones
            print(f"    Local {local_num:<6} {d[1][:40]:<42} {members:>8,}")

    print(f"\n    DC37 locals total members: {dc37_locals_members:,}")

    # Check for missing DC37 locals
    missing_dc37 = set(str(n) for n in DC37_LOCALS) - dc37_found_nums
    if missing_dc37:
        print(f"\n  DC37 Locals NOT in OLMS ({len(missing_dc37)}):")
        for num in sorted(missing_dc37, key=lambda x: int(x) if x.isdigit() else 0)[:20]:
            print(f"    Local {num}")
        if len(missing_dc37) > 20:
            print(f"    ... and {len(missing_dc37) - 20} more")

    # Duplicate Analysis
    print(f"\n{'Duplicate Local Numbers':<40}")
    print("-"*50)

    duplicates = analyze_duplicates(locals_data)
    if duplicates:
        print(f"  Found {len(duplicates)} local numbers with multiple filings:")
        for local_num, entries in sorted(duplicates.items(), key=lambda x: sum(e['members'] for e in x[1]), reverse=True)[:15]:
            total = sum(e['members'] for e in entries)
            print(f"\n    Local {local_num} ({len(entries)} filings, {total:,} total members):")
            for e in entries:
                print(f"      {e['f_num']}: {e['union_name'][:40]:<42} {e['members']:>8,}")
    else:
        print("  No duplicate local numbers found")

    # Form 990 Data
    print(f"\n{'Form 990 AFSCME NY Data':<40}")
    print("-"*50)

    if form_990_data:
        for d in form_990_data[:15]:
            print(f"  {d['name'][:50]:<52}")
            print(f"    EIN: {d['ein']}, Est. Members: {d['estimated_members']:,}, Dues: ${d['dues_revenue']:,.0f}")
    else:
        print("  No Form 990 AFSCME NY data found")

    # Deduplicated Total Calculation
    print(f"\n{'='*80}")
    print("DEDUPLICATED MEMBERSHIP CALCULATION")
    print("="*80)

    # Start with all locals
    dedup_members = 0
    included = []
    excluded_csea_regions = []
    dc37_locals_included = []
    dc37_main_entry = None

    # Track what's been counted
    counted_f_nums = set()

    for local in locals_data:
        local_num = local['local_number']

        # Skip CSEA regions 1-6 (duplicates of Local 1000)
        if local_num in CSEA_REGION_LOCALS:
            excluded_csea_regions.append(local)
            continue

        # Track DC37 main vs locals
        if local_num == DC37_MAIN_LOCAL:
            dc37_main_entry = local
        elif local_num and local_num in [str(n) for n in DC37_LOCALS]:
            dc37_locals_included.append(local)

        if local['f_num'] not in counted_f_nums:
            dedup_members += local['members']
            counted_f_nums.add(local['f_num'])
            included.append(local)

    csea_region_members = sum(r['members'] for r in excluded_csea_regions)

    print(f"\n  Raw total: {total_members_raw:,}")
    print(f"\n  CSEA Region Adjustment:")
    print(f"    Excluded Locals 1-6: -{csea_region_members:,} ({len(excluded_csea_regions)} records)")

    # Check DC37 potential double-counting
    dc37_locals_members = sum(l['members'] for l in dc37_locals_included)
    dc37_main_members = dc37_main_entry['members'] if dc37_main_entry else 0

    print(f"\n  DC37 Analysis:")
    print(f"    DC37 Main (Local 37): {dc37_main_members:,}")
    print(f"    DC37 Locals filing separately: {dc37_locals_members:,} ({len(dc37_locals_included)} locals)")
    print(f"    990 Estimate for DC37: 128,571")

    if dc37_locals_members > 0:
        print(f"\n    WARNING:  DC37 locals ({dc37_locals_members:,}) may already be included in Local 37 ({dc37_main_members:,})")
        print(f"       If so, deduplicated DC37 total = {dc37_main_members:,} (not {dc37_main_members + dc37_locals_members:,})")

    print(f"\n  {'='*50}")
    print(f"  Deduplicated total (excluding CSEA regions): {dedup_members:,}")

    # If DC37 locals are duplicates, show that adjustment too
    fully_deduped = dedup_members - dc37_locals_members
    print(f"  If DC37 locals are also duplicates: {fully_deduped:,}")

    # Breakdown by type
    print(f"\n{'AFSCME NY Breakdown by Type':<40}")
    print("-"*80)

    csea_members = csea_main['members'] if csea_main else 0
    dc37_members = dc37_main_entry['members'] if dc37_main_entry else 0

    # Other AFSCME locals (not CSEA, not DC37, not regions)
    other_locals = []
    for local in locals_data:
        local_num = local['local_number']
        # Skip CSEA main and regions
        if local_num == CSEA_MAIN_LOCAL or local_num in CSEA_REGION_LOCALS:
            continue
        # Skip DC37 main
        if local_num == DC37_MAIN_LOCAL:
            continue
        # Skip DC37 locals
        if local_num and local_num in [str(n) for n in DC37_LOCALS]:
            continue
        other_locals.append(local)

    other_members = sum(l['members'] for l in other_locals)

    print(f"\n  Category                             Locals    Members")
    print(f"  {'-'*55}")
    print(f"  CSEA (Local 1000)                        1    {csea_members:>10,}")
    print(f"  CSEA Regions 1-6 (DUPLICATE)             6    {sum(r['members'] for r in excluded_csea_regions):>10,}  <- DO NOT COUNT")
    print(f"  DC37 (Local 37)                          1    {dc37_members:>10,}")
    print(f"  DC37 Locals (may be duplicate)          {len(dc37_locals_included):>2}    {dc37_locals_members:>10,}  <- CHECK IF DUPLICATE")
    print(f"  Other AFSCME NY locals                  {len(other_locals):>2}    {other_members:>10,}")
    print(f"  {'-'*55}")
    print(f"  TOTAL (conservative, no duplicates)          {csea_members + dc37_members + other_members:>10,}")
    print(f"  TOTAL (if DC37 locals separate)              {csea_members + dc37_members + dc37_locals_members + other_members:>10,}")

    # Show other locals
    if other_locals:
        print(f"\n  Other AFSCME NY Locals ({len(other_locals)}):")
        for local in sorted(other_locals, key=lambda x: x['members'], reverse=True)[:15]:
            print(f"    Local {local['local_number'] or 'N/A':<6} {local['city']:<20} {local['members']:>8,}")
        if len(other_locals) > 15:
            print(f"    ... and {len(other_locals) - 15} more")

    # Top 20 by membership
    print(f"\n{'Top 20 AFSCME NY Locals by Membership':<40}")
    print("-"*80)

    sorted_locals = sorted(locals_data, key=lambda x: x['members'], reverse=True)
    for i, local in enumerate(sorted_locals[:20], 1):
        local_num = local['local_number']
        flag = ""
        if local_num in CSEA_REGION_LOCALS:
            flag = " [CSEA REGION-DUP]"
        elif local_num and local_num in [str(n) for n in DC37_LOCALS]:
            flag = " [DC37 LOCAL]"
        print(f"  {i:>2}. {local['union_name'][:45]:<47} {local['members']:>10,}{flag}")
        print(f"      F#: {local['f_num']}, Local: {local['local_number'] or 'N/A'}, {local['city']}")


def main():
    print("Fetching AFSCME NY locals from OLMS...")
    locals_data = get_afscme_ny_locals()
    print(f"  Found {len(locals_data)} records")

    print("\nFetching CSEA data...")
    csea_data = get_csea_data()
    print(f"  Found {len(csea_data)} CSEA records")

    print("\nFetching DC37 data...")
    dc37_council, dc37_locals = get_dc37_data()
    print(f"  Found {len(dc37_council)} DC37 council records")
    print(f"  Found {len(dc37_locals)} DC37 locals")

    print("\nFetching Form 990 AFSCME data...")
    form_990_data = get_990_afscme_ny()
    print(f"  Found {len(form_990_data)} Form 990 records")

    print_report(locals_data, csea_data, dc37_council, dc37_locals, form_990_data)


if __name__ == '__main__':
    main()
