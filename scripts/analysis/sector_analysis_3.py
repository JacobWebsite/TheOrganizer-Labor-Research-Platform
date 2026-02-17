import os
import psycopg2
from db_config import get_connection
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('CORRECTED SECTOR-SPECIFIC BLS COVERAGE')
print('='*70)

# BLS 2024 Benchmarks
BLS_PRIVATE = 7_300_000
BLS_PUBLIC = 7_025_000
BLS_TOTAL = BLS_PRIVATE + BLS_PUBLIC

# Get F-7 breakdown by sector
cur.execute("""
    SELECT 
        COALESCE(u.sector, 'UNKNOWN') as sector,
        COUNT(*) as employer_count,
        SUM(f.latest_unit_size) as total_workers
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.latest_union_fnum IS NOT NULL
    GROUP BY COALESCE(u.sector, 'UNKNOWN')
""")
f7_by_sector = {row['sector']: row['total_workers'] or 0 for row in cur.fetchall()}

print('\n### F-7 Data by Union Sector Classification ###')
for sector, workers in sorted(f7_by_sector.items(), key=lambda x: x[1], reverse=True):
    print(f'  {sector:<25}: {workers:>12,}')
print(f'  {"TOTAL":<25}: {sum(f7_by_sector.values()):>12,}')

# Categorize sectors
private_sectors = ['PRIVATE', 'RAILROAD_AIRLINE_RLA']  # RLA is private sector
public_sectors = ['PUBLIC_SECTOR', 'FEDERAL']
ambiguous = ['OTHER', 'UNKNOWN']

f7_private = sum(f7_by_sector.get(s, 0) for s in private_sectors)
f7_public = sum(f7_by_sector.get(s, 0) for s in public_sectors)
f7_ambiguous = sum(f7_by_sector.get(s, 0) for s in ambiguous)

print('\n### Categorized Totals ###')
print(f'  Private (PRIVATE + RLA):       {f7_private:>12,}')
print(f'  Public (PUBLIC_SECTOR + FED):  {f7_public:>12,}')
print(f'  Ambiguous (OTHER + UNKNOWN):   {f7_ambiguous:>12,}')

# Coverage calculations
print('\n' + '='*70)
print('SECTOR-SPECIFIC COVERAGE ANALYSIS')
print('='*70)

print('\n### Scenario 1: F-7 "PRIVATE" sector only ###')
print(f'  BLS Private Benchmark:  {BLS_PRIVATE:>12,}')
print(f'  F-7 Private Only:       {f7_private:>12,}')
print(f'  Coverage:               {100*f7_private/BLS_PRIVATE:>11.1f}%')

print('\n### Scenario 2: F-7 excluding clear public sector ###')
f7_excl_public = sum(f7_by_sector.values()) - f7_public
print(f'  BLS Private Benchmark:  {BLS_PRIVATE:>12,}')
print(f'  F-7 (excl public):      {f7_excl_public:>12,}')
print(f'  Coverage:               {100*f7_excl_public/BLS_PRIVATE:>11.1f}%')

print('\n### Scenario 3: Allocate "OTHER" and "UNKNOWN" ###')
# Assume 70% of ambiguous is private (conservative estimate)
private_share = 0.70
f7_adjusted_private = f7_private + (f7_ambiguous * private_share)
print(f'  BLS Private Benchmark:  {BLS_PRIVATE:>12,}')
print(f'  F-7 Adjusted Private:   {f7_adjusted_private:>12,.0f}')
print(f'  (includes 70% of ambiguous)')
print(f'  Coverage:               {100*f7_adjusted_private/BLS_PRIVATE:>11.1f}%')

# Public sector coverage
print('\n### Public Sector Coverage ###')
print(f'  BLS Public Benchmark:   {BLS_PUBLIC:>12,}')
print(f'  F-7 Public Sector:      {f7_public:>12,}')
print(f'  Coverage:               {100*f7_public/BLS_PUBLIC:>11.1f}%')
print('\n  Note: F-7 should NOT include public sector.')
print('  Public sector employers may be:')
print('  - Mixed public/private employers')
print('  - Private contractors to government')
print('  - Data classification issues')

# What's in the public sector F-7 data?
print('\n### Investigating Public Sector in F-7 ###')
cur.execute("""
    SELECT f.employer_name, f.latest_union_name, u.aff_abbr, f.latest_unit_size
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.sector IN ('FEDERAL', 'PUBLIC_SECTOR')
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 15
""")
print('\nTop "public sector" employers in F-7:')
for row in cur.fetchall():
    print(f"  {row['employer_name'][:45]}: {row['latest_unit_size'] or 0:,} ({row['aff_abbr']})")

print('\n' + '='*70)
print('SUMMARY: CORRECTED COVERAGE METRICS')
print('='*70)
print(f'''
┌────────────────────────────────────────────────────────────────────┐
│                    BLS vs PLATFORM COVERAGE                         │
├────────────────────────────────────────────────────────────────────┤
│  PRIVATE SECTOR:                                                    │
│    BLS Benchmark (2024):           {BLS_PRIVATE:>12,}                │
│    F-7 Private Only:               {f7_private:>12,}                │
│    Coverage:                       {100*f7_private/BLS_PRIVATE:>11.1f}%               │
├────────────────────────────────────────────────────────────────────┤
│  PUBLIC SECTOR:                                                     │
│    BLS Benchmark (2024):           {BLS_PUBLIC:>12,}                │
│    F-7 Public (anomalous):         {f7_public:>12,}                │
│    Coverage:                       {100*f7_public/BLS_PUBLIC:>11.1f}%               │
│    Note: F-7 is private-sector focused                              │
├────────────────────────────────────────────────────────────────────┤
│  TOTAL (with caveats):                                              │
│    BLS Total:                      {BLS_TOTAL:>12,}                │
│    F-7 Total:                      {sum(f7_by_sector.values()):>12,}                │
│    Coverage:                       {100*sum(f7_by_sector.values())/BLS_TOTAL:>11.1f}%               │
└────────────────────────────────────────────────────────────────────┘
''')

conn.close()
