import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('CORRECTED PRIVATE SECTOR COVERAGE (EXCLUDING FEDERAL)')
print('='*70)

BLS_PRIVATE = 7_300_000

# Current F-7 by revised sector
print('\n### 1. Current F-7 by Sector (Before Correction) ###')
cur.execute("""
    SELECT 
        COALESCE(u.sector_revised, 'UNKNOWN') as sector,
        SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.latest_union_fnum IS NOT NULL
    GROUP BY COALESCE(u.sector_revised, 'UNKNOWN')
    ORDER BY workers DESC
""")
sectors = {}
for row in cur.fetchall():
    sectors[row['sector']] = row['workers'] or 0
    print(f"  {row['sector']:<25}: {row['workers'] or 0:>12,}")

# Current calculation
private_current = sectors.get('PRIVATE', 0) + sectors.get('RAILROAD_AIRLINE_RLA', 0)
print(f'\n  Current PRIVATE+RLA:        {private_current:>12,}')
print(f'  Coverage vs BLS:            {100*private_current/BLS_PRIVATE:>11.1f}%')

# CORRECTED: Exclude FEDERAL entirely from private sector calculation
print('\n### 2. CORRECTED Coverage (Excluding FEDERAL) ###')
print('''
F-7 is NLRA (private sector) filing. FEDERAL sector should NOT be included:
- VA, USPS, DOD, Coast Guard are FSLMRA (different law)
- These are data anomalies, not legitimate F-7 filings
''')

federal_workers = sectors.get('FEDERAL', 0)
public_sector = sectors.get('PUBLIC_SECTOR', 0)

print(f'  FEDERAL to exclude:         {federal_workers:>12,}')
print(f'  PUBLIC_SECTOR to exclude:   {public_sector:>12,}')

# Strictly private
strict_private = sectors.get('PRIVATE', 0) + sectors.get('RAILROAD_AIRLINE_RLA', 0)
print(f'\n  STRICT PRIVATE (PRIVATE+RLA only):')
print(f'    Workers:                  {strict_private:>12,}')
print(f'    BLS Benchmark:            {BLS_PRIVATE:>12,}')
print(f'    Coverage:                 {100*strict_private/BLS_PRIVATE:>11.1f}%')

# With MIXED (SEIU 70% private)
mixed_private = int(sectors.get('MIXED_PUBLIC_PRIVATE', 0) * 0.70)
private_with_mixed = strict_private + mixed_private
print(f'\n  PRIVATE + MIXED (70% of SEIU):')
print(f'    Workers:                  {private_with_mixed:>12,}')
print(f'    Coverage:                 {100*private_with_mixed/BLS_PRIVATE:>11.1f}%')

# With OTHER (mostly private)
other_workers = sectors.get('OTHER', 0)
private_full = private_with_mixed + other_workers
print(f'\n  PRIVATE + MIXED + OTHER:')
print(f'    Workers:                  {private_full:>12,}')
print(f'    Coverage:                 {100*private_full/BLS_PRIVATE:>11.1f}%')

# Summary table
print('\n### 3. SUMMARY ###')
print(f'''
+----------------------------------------------------------+
|  CORRECTED BLS COVERAGE (Excluding Federal/Public)       |
+----------------------------------------------------------+
|  Metric                    |  Workers    |  Coverage     |
+----------------------------------------------------------+
|  BLS Private Benchmark     | {BLS_PRIVATE:>10,}  |    100.0%     |
+----------------------------------------------------------+
|  PRIVATE + RLA (strict)    | {strict_private:>10,}  |    {100*strict_private/BLS_PRIVATE:>5.1f}%     |
|  + MIXED (70% SEIU)        | {private_with_mixed:>10,}  |    {100*private_with_mixed/BLS_PRIVATE:>5.1f}%     |
|  + OTHER                   | {private_full:>10,}  |    {100*private_full/BLS_PRIVATE:>5.1f}%     |
+----------------------------------------------------------+
|  EXCLUDED (not private):                                 |
|    FEDERAL (VA, USPS, etc) | {federal_workers:>10,}  |   (anomaly)   |
|    PUBLIC_SECTOR           | {public_sector:>10,}  |   (anomaly)   |
+----------------------------------------------------------+
''')

# Check what's in UNKNOWN
print('\n### 4. UNKNOWN Sector Analysis ###')
cur.execute("""
    SELECT f.latest_union_name, COUNT(*) as cnt, SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector_revised IS NULL OR u.sector_revised = 'UNKNOWN'
    GROUP BY f.latest_union_name
    ORDER BY workers DESC NULLS LAST
    LIMIT 10
""")
print('Top unions in UNKNOWN sector:')
for row in cur.fetchall():
    print(f"  {row['latest_union_name'][:50]}: {row['workers'] or 0:,}")

conn.close()
print('\n' + '='*70)
