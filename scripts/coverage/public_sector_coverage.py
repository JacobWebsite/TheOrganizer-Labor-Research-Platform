import os
"""Analyze public sector union coverage against BLS/EPI benchmarks"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*80)
print('PUBLIC SECTOR UNION COVERAGE ANALYSIS')
print('='*80)

# First, understand what sector data we have
print('\n1. DATABASE STRUCTURE - Sector-Related Tables')
print('-'*80)

# Check union_sector table
cur.execute("SELECT * FROM union_sector ORDER BY sector_code")
print('\nUnion Sectors:')
for row in cur.fetchall():
    print(f"  {row['sector_code']}: {row['sector_name']} (Law: {row['governing_law']})")

# Check unions_master sector breakdown
print('\n2. UNIONS_MASTER BY SECTOR')
print('-'*80)
cur.execute('''
    SELECT sector, COUNT(*) as union_count, SUM(members) as total_members
    FROM unions_master
    WHERE sector IS NOT NULL
    GROUP BY sector
    ORDER BY SUM(members) DESC NULLS LAST
''')
for row in cur.fetchall():
    members = row['total_members'] or 0
    print(f"  {row['sector']}: {row['union_count']:,} unions, {members:,} members")

# Check F-7 employers by sector inference (NAICS-based)
print('\n3. F7 EMPLOYERS BY SECTOR (NAICS-based)')
print('-'*80)
cur.execute('''
    SELECT
        CASE
            WHEN naics = '92' THEN 'Public Administration'
            WHEN naics = '61' THEN 'Educational Services'
            WHEN naics = '62' THEN 'Healthcare/Social'
            WHEN employer_name ILIKE '%school%' OR employer_name ILIKE '%university%'
                 OR employer_name ILIKE '%college%' THEN 'Education (by name)'
            WHEN employer_name ILIKE '%city of%' OR employer_name ILIKE '%county of%'
                 OR employer_name ILIKE '%state of%' OR employer_name ILIKE '%township%'
                 THEN 'Government (by name)'
            ELSE 'Private/Other'
        END as sector_type,
        COUNT(*) as employers,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers
    FROM f7_employers_deduped
    GROUP BY 1
    ORDER BY 3 DESC
''')
for row in cur.fetchall():
    print(f"  {row['sector_type']:<25} | {row['employers']:>6} employers | {row['counted_workers']:>10,} workers")

# Check EPI union membership data
print('\n4. EPI UNION MEMBERSHIP DATA')
print('-'*80)
cur.execute('''
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'epi_union_membership'
    ORDER BY ordinal_position
    LIMIT 15
''')
print('Columns in epi_union_membership:')
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

# Get latest EPI data by sector
cur.execute('''
    SELECT DISTINCT sector FROM epi_union_membership
    WHERE sector IS NOT NULL
    ORDER BY sector
''')
epi_sectors = [r['sector'] for r in cur.fetchall()]
print(f'\nEPI Sectors: {epi_sectors[:10]}...')

# Get latest year's EPI data for public sector
print('\n5. EPI PUBLIC SECTOR DATA (Latest Year)')
print('-'*80)
cur.execute('''
    SELECT year, sector, state,
           union_members, covered_by_union, employed
    FROM epi_union_membership
    WHERE year = (SELECT MAX(year) FROM epi_union_membership)
      AND (sector ILIKE '%public%' OR sector ILIKE '%government%')
    ORDER BY union_members DESC NULLS LAST
    LIMIT 20
''')
for row in cur.fetchall():
    print(f"  {row['year']} | {row['sector']:<30} | {row['state']:<5} | {row['union_members']:>10,} members")

# National totals by sector type
print('\n6. EPI NATIONAL TOTALS BY SECTOR TYPE (Latest Year)')
print('-'*80)
cur.execute('''
    SELECT sector,
           SUM(union_members) as total_members,
           SUM(employed) as total_employed,
           ROUND(100.0 * SUM(union_members) / NULLIF(SUM(employed), 0), 1) as density
    FROM epi_union_membership
    WHERE year = (SELECT MAX(year) FROM epi_union_membership)
      AND state != 'United States'
    GROUP BY sector
    ORDER BY SUM(union_members) DESC NULLS LAST
''')
for row in cur.fetchall():
    members = row['total_members'] or 0
    employed = row['total_employed'] or 0
    density = row['density'] or 0
    print(f"  {row['sector']:<35} | {members:>12,} members | {employed:>12,} employed | {density:>5.1f}% density")

conn.close()
