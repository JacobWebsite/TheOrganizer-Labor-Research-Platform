import os
import psycopg2
from db_config import get_connection
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('SECTOR ANALYSIS: F-7 PUBLIC SECTOR CONTAMINATION CHECK')
print('='*70)

# 1. Check what unions appear in F-7 data
print('\n### 1. Top Unions in F-7 Data by Worker Count ###')
cur.execute("""
    SELECT 
        f.latest_union_fnum,
        f.latest_union_name,
        u.aff_abbr,
        u.sector,
        COUNT(*) as employer_count,
        SUM(f.latest_unit_size) as total_workers
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.latest_union_fnum IS NOT NULL
    GROUP BY f.latest_union_fnum, f.latest_union_name, u.aff_abbr, u.sector
    ORDER BY total_workers DESC NULLS LAST
    LIMIT 30
""")
print(f'{"Union":<40} {"Aff":<10} {"Sector":<15} {"Employers":>10} {"Workers":>12}')
print('-'*90)
for row in cur.fetchall():
    name = (row['latest_union_name'] or 'Unknown')[:40]
    aff = row['aff_abbr'] or 'N/A'
    sector = row['sector'] or 'N/A'
    print(f"{name:<40} {aff:<10} {sector:<15} {row['employer_count']:>10,} {row['total_workers'] or 0:>12,}")

# 2. Check for known public sector unions in F-7
print('\n### 2. Public Sector Unions in F-7 (SHOULD BE MINIMAL) ###')
public_affiliations = ['AFGE', 'AFSCME', 'AFT', 'NTEU', 'NFFE', 'NATCA', 'IAFF', 'NEA', 'NFOP']

cur.execute("""
    SELECT 
        u.aff_abbr,
        u.sector,
        COUNT(*) as employer_count,
        SUM(f.latest_unit_size) as total_workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr IN ('AFGE', 'AFSCME', 'AFT', 'NTEU', 'NFFE', 'NATCA', 'IAFF', 'NEA', 'NFOP')
    GROUP BY u.aff_abbr, u.sector
    ORDER BY total_workers DESC NULLS LAST
""")
print(f'{"Affiliation":<15} {"Sector":<15} {"Employers":>10} {"Workers":>12}')
print('-'*55)
public_total = 0
for row in cur.fetchall():
    print(f"{row['aff_abbr']:<15} {row['sector'] or 'N/A':<15} {row['employer_count']:>10,} {row['total_workers'] or 0:>12,}")
    public_total += row['total_workers'] or 0
print(f"\nTotal public sector in F-7: {public_total:,}")

# 3. Check postal unions in F-7
print('\n### 3. Postal Unions in F-7 ###')
cur.execute("""
    SELECT 
        u.aff_abbr,
        COUNT(*) as employer_count,
        SUM(f.latest_unit_size) as total_workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr IN ('APWU', 'NALC', 'NPMHU', 'NRLCA')
    GROUP BY u.aff_abbr
    ORDER BY total_workers DESC NULLS LAST
""")
postal_total = 0
for row in cur.fetchall():
    print(f"  {row['aff_abbr']}: {row['employer_count']:,} employers, {row['total_workers'] or 0:,} workers")
    postal_total += row['total_workers'] or 0
print(f"Total postal in F-7: {postal_total:,}")

# 4. Check federal employers in F-7
print('\n### 4. Federal/Government Employers in F-7 ###')
cur.execute("""
    SELECT employer_name, latest_union_name, latest_unit_size
    FROM f7_employers_deduped
    WHERE employer_name ILIKE '%federal%'
       OR employer_name ILIKE '%government%'
       OR employer_name ILIKE '%dept of%'
       OR employer_name ILIKE '%department of%'
       OR employer_name ILIKE '%u.s. %'
       OR employer_name ILIKE '%united states%'
       OR employer_name ILIKE '%postal%'
       OR employer_name ILIKE '%veterans%'
    ORDER BY latest_unit_size DESC NULLS LAST
    LIMIT 20
""")
print('Government/federal employers found:')
gov_total = 0
for row in cur.fetchall():
    print(f"  {row['employer_name'][:50]}: {row['latest_unit_size'] or 0:,}")
    gov_total += row['latest_unit_size'] or 0

# 5. Summary by sector
print('\n### 5. F-7 Workers by Union Sector ###')
cur.execute("""
    SELECT 
        COALESCE(u.sector, 'UNKNOWN') as sector,
        COUNT(*) as employer_count,
        SUM(f.latest_unit_size) as total_workers
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.latest_union_fnum IS NOT NULL
    GROUP BY COALESCE(u.sector, 'UNKNOWN')
    ORDER BY total_workers DESC NULLS LAST
""")
print(f'{"Sector":<25} {"Employers":>12} {"Workers":>15}')
print('-'*55)
for row in cur.fetchall():
    print(f"{row['sector']:<25} {row['employer_count']:>12,} {row['total_workers'] or 0:>15,}")

conn.close()
print('\n' + '='*70)
