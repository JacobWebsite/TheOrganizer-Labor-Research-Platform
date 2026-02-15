import os
from db_config import get_connection
"""Reconcile public sector data sources"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*80)
print('PUBLIC SECTOR DATA RECONCILIATION')
print('='*80)

# Get totals from public_sector_benchmarks
print('\n1. TOTALS FROM PUBLIC_SECTOR_BENCHMARKS')
print('-'*80)
cur.execute('''
    SELECT
        SUM(olms_state_local_members) as olms_state_local,
        SUM(olms_federal_members) as olms_federal,
        SUM(flra_federal_workers) as flra_federal,
        SUM(epi_public_members) as epi_public
    FROM public_sector_benchmarks
    WHERE state != 'DC'
''')
row = cur.fetchone()
print(f'   OLMS State/Local Members: {row["olms_state_local"]:,}')
print(f'   OLMS Federal Members:     {row["olms_federal"]:,}')
print(f'   FLRA Federal Workers:     {row["flra_federal"]:,}')
print(f'   EPI Public Members:       {row["epi_public"]:,.0f}')

olms_total = (row['olms_state_local'] or 0) + (row['olms_federal'] or 0)
print(f'\n   OLMS Total (State/Local + Federal): {olms_total:,}')

# Compare to state_coverage_comparison
print('\n2. STATE_COVERAGE_COMPARISON - PLATFORM_PUBLIC')
print('-'*80)
cur.execute("SELECT SUM(platform_public) as total FROM state_coverage_comparison WHERE state != 'DC'")
scc_total = cur.fetchone()['total']
print(f'   Platform Public (excl DC): {scc_total:,}')

# Reconciliation
print(f'\n3. RECONCILIATION')
print('-'*80)
print(f'   public_sector_benchmarks OLMS total: {olms_total:,}')
print(f'   state_coverage_comparison platform:  {scc_total:,}')
print(f'   Difference: {scc_total - olms_total:,}')

# Top states comparison
print('\n4. TOP 15 STATES COMPARISON')
print('-'*80)
cur.execute('''
    SELECT s.state,
           s.platform_public,
           p.olms_state_local_members,
           p.olms_federal_members,
           p.flra_federal_workers,
           (COALESCE(p.olms_state_local_members, 0) + COALESCE(p.olms_federal_members, 0)) as olms_total,
           s.platform_public - (COALESCE(p.olms_state_local_members, 0) + COALESCE(p.olms_federal_members, 0)) as diff
    FROM state_coverage_comparison s
    LEFT JOIN public_sector_benchmarks p ON s.state = p.state
    ORDER BY s.platform_public DESC
    LIMIT 15
''')
print(f'{"State":<6} | {"Platform":>12} | {"OLMS S/L":>12} | {"OLMS Fed":>12} | {"FLRA":>10} | {"OLMS Tot":>12} | {"Diff":>10}')
print('-'*90)
for row in cur.fetchall():
    pp = row['platform_public'] or 0
    osl = row['olms_state_local_members'] or 0
    of = row['olms_federal_members'] or 0
    flra = row['flra_federal_workers'] or 0
    ot = row['olms_total'] or 0
    diff = row['diff'] or 0
    print(f"{row['state']:<6} | {pp:>12,} | {osl:>12,} | {of:>12,} | {flra:>10,} | {ot:>12,} | {diff:>10,}")

# Now check what makes up platform_public - is it just olms_state_local?
print('\n5. WHERE DOES PLATFORM_PUBLIC COME FROM?')
print('-'*80)

# Check if platform_public == olms_state_local_members
cur.execute('''
    SELECT s.state,
           s.platform_public,
           p.olms_state_local_members,
           s.platform_public - COALESCE(p.olms_state_local_members, 0) as diff
    FROM state_coverage_comparison s
    LEFT JOIN public_sector_benchmarks p ON s.state = p.state
    WHERE s.platform_public != COALESCE(p.olms_state_local_members, 0)
    ORDER BY ABS(s.platform_public - COALESCE(p.olms_state_local_members, 0)) DESC
    LIMIT 20
''')
results = cur.fetchall()
if results:
    print('States where platform_public != olms_state_local_members:')
    for row in results:
        print(f"   {row['state']}: platform={row['platform_public']:,}, olms_s/l={row['olms_state_local_members'] or 0:,}, diff={row['diff']:,}")
else:
    print('   platform_public == olms_state_local_members for all states!')

# Check the unions_master for public sector by state
print('\n6. UNIONS_MASTER PUBLIC SECTOR BY STATE (source of olms_state_local)')
print('-'*80)
cur.execute('''
    SELECT state,
           SUM(CASE WHEN sector = 'PUBLIC_SECTOR' THEN members ELSE 0 END) as state_local,
           SUM(CASE WHEN sector = 'FEDERAL' THEN members ELSE 0 END) as federal
    FROM unions_master
    WHERE sector IN ('PUBLIC_SECTOR', 'FEDERAL')
    GROUP BY state
    ORDER BY SUM(CASE WHEN sector = 'PUBLIC_SECTOR' THEN members ELSE 0 END) DESC
    LIMIT 10
''')
print(f'{"State":<6} | {"State/Local":>15} | {"Federal":>12}')
print('-'*40)
for row in cur.fetchall():
    sl = row['state_local'] or 0
    fed = row['federal'] or 0
    print(f"{row['state']:<6} | {sl:>15,} | {fed:>12,}")

# Check F7 employers contributing to public sector
print('\n7. F7 PUBLIC SECTOR SOURCES')
print('-'*80)
cur.execute('''
    SELECT
        CASE
            WHEN naics = '92' THEN 'NAICS 92 (Public Admin)'
            WHEN naics = '61' THEN 'NAICS 61 (Education)'
            WHEN employer_name ILIKE '%school%' THEN 'School (by name)'
            WHEN employer_name ILIKE '%university%' OR employer_name ILIKE '%college%' THEN 'Higher Ed (by name)'
            WHEN employer_name ILIKE '%city of%' THEN 'City (by name)'
            WHEN employer_name ILIKE '%county of%' THEN 'County (by name)'
            WHEN employer_name ILIKE '%state of%' THEN 'State (by name)'
            ELSE 'Other'
        END as category,
        COUNT(*) as employers,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
        SUM(latest_unit_size) as raw_workers
    FROM f7_employers_deduped
    WHERE naics IN ('92', '61')
       OR employer_name ILIKE '%school%'
       OR employer_name ILIKE '%university%'
       OR employer_name ILIKE '%college%'
       OR employer_name ILIKE '%city of%'
       OR employer_name ILIKE '%county of%'
       OR employer_name ILIKE '%state of%'
    GROUP BY 1
    ORDER BY 3 DESC
''')
f7_total = 0
for row in cur.fetchall():
    counted = row['counted_workers'] or 0
    f7_total += counted
    print(f"   {row['category']:<25} | {row['employers']:>6} emps | {counted:>10,} counted")
print(f'\n   F7 Total Public Sector: {f7_total:,}')

conn.close()
