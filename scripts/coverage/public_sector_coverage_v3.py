import os
from db_config import get_connection
"""Analyze public sector - investigate data definitions"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*80)
print('PUBLIC SECTOR COVERAGE - DEEP ANALYSIS')
print('='*80)

# Check EPI measure names
print('\n1. EPI DATA - Understanding the measures')
print('-'*80)
cur.execute('''
    SELECT measure, geo_name, group_value, value
    FROM epi_union_membership
    WHERE year = 2024
      AND demographic_group = 'Private/public sector'
      AND geo_name = 'United States'
    ORDER BY group_value, measure
''')
print("EPI National 2024 - Private/Public Sector:")
for row in cur.fetchall():
    val = row['value'] or 0
    print(f"  {row['group_value']:<15} | {row['measure']:<45} | {val:>15,.0f}")

# Get proper EPI public sector numbers
print('\n2. EPI PUBLIC SECTOR - National Totals 2024')
print('-'*80)
cur.execute('''
    SELECT measure, value
    FROM epi_union_membership
    WHERE year = 2024
      AND demographic_group = 'Private/public sector'
      AND group_value = 'Public sector'
      AND geo_name = 'United States'
''')
epi_public = {}
for row in cur.fetchall():
    epi_public[row['measure']] = row['value']
    print(f"  {row['measure']:<50} | {row['value']:>15,.0f}")

# Extract the key metric
epi_public_members = epi_public.get('Number of union members', 0)
print(f"\n  EPI Public Sector Union Members: {epi_public_members:,.0f}")

# Now check OLMS unions - look at most recent filings only
print('\n3. OLMS - Most Recent Filings Analysis')
print('-'*80)
cur.execute('''
    SELECT sector,
           COUNT(DISTINCT f_num) as unique_unions,
           SUM(members) as total_members,
           AVG(members) as avg_members,
           MAX(rpt_year) as latest_year
    FROM unions_master
    WHERE sector IN ('FEDERAL', 'PUBLIC_SECTOR')
    GROUP BY sector
''')
olms_totals = {}
for row in cur.fetchall():
    olms_totals[row['sector']] = row['total_members'] or 0
    print(f"  {row['sector']:<15}: {row['unique_unions']:>6,} unions | {row['total_members']:>12,} members | avg {row['avg_members']:>8,.0f} | latest: {row['latest_year']}")

# Check if there's duplicate counting in unions_master
print('\n4. CHECKING FOR DUPLICATE UNION ENTRIES')
print('-'*80)
cur.execute('''
    SELECT f_num, union_name, sector, COUNT(*) as entry_count, SUM(members) as total_members
    FROM unions_master
    WHERE sector IN ('FEDERAL', 'PUBLIC_SECTOR')
    GROUP BY f_num, union_name, sector
    HAVING COUNT(*) > 1
    ORDER BY SUM(members) DESC
    LIMIT 10
''')
print("Unions with multiple entries:")
for row in cur.fetchall():
    print(f"  {row['f_num']}: {row['union_name'][:50]} ({row['entry_count']} entries, {row['total_members']:,} total)")

# Get deduplicated count (one entry per f_num)
print('\n5. DEDUPLICATED OLMS PUBLIC SECTOR')
print('-'*80)
cur.execute('''
    WITH latest_filing AS (
        SELECT DISTINCT ON (f_num)
            f_num, union_name, sector, members, rpt_year
        FROM unions_master
        WHERE sector IN ('FEDERAL', 'PUBLIC_SECTOR')
        ORDER BY f_num, rpt_year DESC
    )
    SELECT sector, COUNT(*) as unions, SUM(members) as members
    FROM latest_filing
    GROUP BY sector
''')
olms_dedup = {}
for row in cur.fetchall():
    olms_dedup[row['sector']] = row['members'] or 0
    print(f"  {row['sector']}: {row['unions']:,} unions, {row['members']:,} members")

olms_total_dedup = sum(olms_dedup.values())
print(f"\n  OLMS Public Total (deduplicated): {olms_total_dedup:,}")

# Compare with EPI
print('\n6. COVERAGE COMPARISON')
print('-'*80)
print(f"  EPI Public Sector Members (2024):    {epi_public_members:>12,.0f}")
print(f"  OLMS Public Sector (deduplicated):   {olms_total_dedup:>12,.0f}")
if epi_public_members > 0:
    coverage = olms_total_dedup / epi_public_members * 100
    diff = (olms_total_dedup - epi_public_members) / epi_public_members * 100
    print(f"\n  Coverage: {coverage:.1f}%")
    print(f"  Difference: {diff:+.1f}%")

    if abs(diff) <= 5:
        status = "TARGET (within ±5%)"
    elif abs(diff) <= 10:
        status = "ACCEPTABLE (within ±10%)"
    elif diff >= -15 and diff < -10:
        status = "ACCEPTABLE (within 15% under)"
    else:
        status = "NEEDS INVESTIGATION"
    print(f"  Status: {status}")

# F7 public sector workers
print('\n7. F7 PUBLIC SECTOR WORKERS (deduplicated)')
print('-'*80)
cur.execute('''
    SELECT
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as workers,
        COUNT(*) as employers
    FROM f7_employers_deduped
    WHERE naics IN ('92', '61')
       OR employer_name ILIKE '%school district%'
       OR employer_name ILIKE '%city of%'
       OR employer_name ILIKE '%county of%'
       OR employer_name ILIKE '%state of%'
''')
row = cur.fetchone()
f7_public = row['workers'] or 0
print(f"  F7 Public Sector Workers: {f7_public:,}")
print(f"  F7 Public Sector Employers: {row['employers']:,}")

# State-by-state comparison
print('\n8. STATE-BY-STATE ANALYSIS (Top 10)')
print('-'*80)
cur.execute('''
    SELECT geo_name as state, value as epi_members
    FROM epi_union_membership
    WHERE year = 2024
      AND demographic_group = 'Private/public sector'
      AND group_value = 'Public sector'
      AND measure = 'Number of union members'
      AND geo_type = 'state'
    ORDER BY value DESC
    LIMIT 15
''')
print(f"{'State':<20} | {'EPI Members':>12}")
print('-'*40)
for row in cur.fetchall():
    members = row['epi_members'] or 0
    print(f"{row['state']:<20} | {members:>12,.0f}")

conn.close()
