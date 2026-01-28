"""Public Sector Coverage - Final Analysis"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*80)
print('PUBLIC SECTOR UNION COVERAGE - FINAL ANALYSIS')
print('='*80)

# BLS/EPI Benchmarks (2024)
EPI_PUBLIC_MEMBERS = 7_016_710
EPI_PRIVATE_MEMBERS = 7_228_771
print(f'\nBENCHMARKS (EPI 2024):')
print(f'  Public Sector Union Members:  {EPI_PUBLIC_MEMBERS:>12,}')
print(f'  Private Sector Union Members: {EPI_PRIVATE_MEMBERS:>12,}')

# Check unions_master columns
cur.execute('''
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'unions_master'
    ORDER BY ordinal_position
''')
cols = [r['column_name'] for r in cur.fetchall()]
print(f'\nunions_master columns: {cols[:15]}...')

# OLMS by sector - check unique unions
print('\n' + '='*80)
print('1. OLMS UNIONS_MASTER BY SECTOR')
print('='*80)
cur.execute('''
    SELECT sector,
           COUNT(DISTINCT f_num) as unique_unions,
           SUM(members) as total_members
    FROM unions_master
    WHERE sector IS NOT NULL
    GROUP BY sector
    ORDER BY SUM(members) DESC NULLS LAST
''')
print(f"{'Sector':<25} | {'Unique Unions':>12} | {'Total Members':>15}")
print('-'*60)
olms_by_sector = {}
for row in cur.fetchall():
    members = row['total_members'] or 0
    olms_by_sector[row['sector']] = members
    print(f"{row['sector']:<25} | {row['unique_unions']:>12,} | {members:>15,}")

# Calculate OLMS totals
olms_public = olms_by_sector.get('PUBLIC_SECTOR', 0) + olms_by_sector.get('FEDERAL', 0)
olms_private = olms_by_sector.get('PRIVATE', 0) + olms_by_sector.get('RAILROAD_AIRLINE_RLA', 0)
print(f"\n  OLMS Public Total (FEDERAL + PUBLIC_SECTOR): {olms_public:,}")
print(f"  OLMS Private Total (PRIVATE + RLA): {olms_private:,}")

# F7 employers coverage
print('\n' + '='*80)
print('2. F7 EMPLOYERS - WORKERS BY SECTOR')
print('='*80)
cur.execute('''
    SELECT
        CASE
            WHEN exclude_reason = 'FEDERAL_EMPLOYER' THEN 'Federal (excluded)'
            WHEN naics = '92' THEN 'Public Admin (NAICS 92)'
            WHEN naics = '61' THEN 'Education (NAICS 61)'
            WHEN employer_name ILIKE '%city of%' OR employer_name ILIKE '%county of%'
                 OR employer_name ILIKE '%state of%' OR employer_name ILIKE '%township%'
                 THEN 'State/Local Govt (by name)'
            WHEN employer_name ILIKE '%school%' OR employer_name ILIKE '%university%'
                 THEN 'Education (by name)'
            ELSE 'Private/Other'
        END as sector_type,
        COUNT(*) as employers,
        SUM(latest_unit_size) as raw_workers,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers
    FROM f7_employers_deduped
    GROUP BY 1
    ORDER BY 4 DESC
''')
f7_public = 0
f7_private = 0
for row in cur.fetchall():
    counted = row['counted_workers'] or 0
    raw = row['raw_workers'] or 0
    sector = row['sector_type']
    print(f"  {sector:<30} | {row['employers']:>6} emps | {counted:>10,} counted | {raw:>10,} raw")
    if 'Public' in sector or 'Education' in sector or 'Federal' in sector or 'Govt' in sector:
        f7_public += counted
    else:
        f7_private += counted

print(f"\n  F7 Public Sector Workers (counted): {f7_public:,}")
print(f"  F7 Private Sector Workers (counted): {f7_private:,}")

# Coverage Analysis
print('\n' + '='*80)
print('3. COVERAGE ANALYSIS')
print('='*80)

def assess_coverage(name, actual, benchmark):
    if benchmark == 0:
        return "N/A", 0
    pct = actual / benchmark * 100
    diff = (actual - benchmark) / benchmark * 100

    if abs(diff) <= 5:
        status = "TARGET (±5%)"
    elif abs(diff) <= 10:
        status = "ACCEPTABLE (±10%)"
    elif diff >= -15 and diff < -10:
        status = "ACCEPTABLE (<15% under)"
    elif diff > 10:
        status = "OVER - Check for duplicates"
    else:
        status = "NEEDS ATTENTION"

    print(f"\n  {name}:")
    print(f"    Actual:     {actual:>12,}")
    print(f"    Benchmark:  {benchmark:>12,}")
    print(f"    Coverage:   {pct:>11.1f}%")
    print(f"    Difference: {diff:>+10.1f}%")
    print(f"    Status:     {status}")
    return status, diff

# OLMS vs EPI
print("\n--- OLMS (Union Member Counts) vs EPI Benchmarks ---")
assess_coverage("PUBLIC SECTOR (OLMS vs EPI)", olms_public, EPI_PUBLIC_MEMBERS)
assess_coverage("PRIVATE SECTOR (OLMS vs EPI)", olms_private, EPI_PRIVATE_MEMBERS)

# F7 vs EPI
print("\n--- F7 (Employer Worker Counts, Deduplicated) vs EPI Benchmarks ---")
assess_coverage("PUBLIC SECTOR (F7 vs EPI)", f7_public, EPI_PUBLIC_MEMBERS)
assess_coverage("PRIVATE SECTOR (F7 vs EPI)", f7_private, EPI_PRIVATE_MEMBERS)

# State-by-state for public sector
print('\n' + '='*80)
print('4. STATE-BY-STATE PUBLIC SECTOR (EPI 2024 - Top 15)')
print('='*80)
cur.execute('''
    SELECT geo_name as state, value as members
    FROM epi_union_membership
    WHERE year = 2024
      AND demographic_group = 'Private/public sector'
      AND group_value = 'Public sector'
      AND measure = 'Number of union members'
      AND geo_type = 'state'
    ORDER BY value DESC
    LIMIT 15
''')
print(f"{'State':<20} | {'EPI Public Members':>15}")
print('-'*40)
for row in cur.fetchall():
    members = row['members'] or 0
    print(f"{row['state']:<20} | {members:>15,.0f}")

# Summary
print('\n' + '='*80)
print('5. SUMMARY')
print('='*80)
# Pre-calculate percentages
f7_private_pct = f7_private / EPI_PRIVATE_MEMBERS * 100
f7_public_pct = f7_public / EPI_PUBLIC_MEMBERS * 100

print(f'''
DATA SOURCES:
- EPI: 7.0M public sector, 7.2M private sector union members (2024)
- OLMS unions_master: Union membership by filing (may include historical)
- F7 employers: Worker counts at union-represented employers

KEY INSIGHT:
The OLMS unions_master "members" column shows much higher numbers than
BLS/EPI benchmarks. This is because OLMS data accumulates membership
counts across all filings/years, not just current membership.

For accurate BLS comparison, use F7 employer worker counts (deduplicated)
which represent actual workers covered by collective bargaining agreements.

CURRENT F7 COVERAGE (deduplicated):
- Private Sector: {f7_private:,} workers = {f7_private_pct:.1f}% of EPI benchmark
- Public Sector:  {f7_public:,} workers = {f7_public_pct:.1f}% of EPI benchmark
''')

conn.close()
