import os
from db_config import get_connection
"""Check F7 adjustment factors and match status breakdown"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*80)
print('F7 ADJUSTMENT FACTORS ANALYSIS')
print('='*80)

# Check f7_adjustment_factors structure
print('\n1. F7_ADJUSTMENT_FACTORS TABLE STRUCTURE')
print('-'*80)
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'f7_adjustment_factors'")
cols = [r['column_name'] for r in cur.fetchall()]
print(f'   Columns: {cols}')

cur.execute('SELECT * FROM f7_adjustment_factors LIMIT 10')
for row in cur.fetchall():
    print(f"   {dict(row)}")

# Check f7_employers_deduped columns
print('\n2. F7_EMPLOYERS_DEDUPED KEY COLUMNS')
print('-'*80)
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'f7_employers_deduped' ORDER BY ordinal_position")
cols = [r['column_name'] for r in cur.fetchall()]
print(f'   Columns: {cols}')

# Check match_status or similar column breakdown
print('\n3. F7_EMPLOYERS_DEDUPED BY EXCLUDE STATUS')
print('-'*80)
cur.execute('''
    SELECT
        exclude_from_counts,
        exclude_reason,
        COUNT(*) as employers,
        SUM(latest_unit_size) as raw_workers
    FROM f7_employers_deduped
    GROUP BY exclude_from_counts, exclude_reason
    ORDER BY exclude_from_counts, SUM(latest_unit_size) DESC
''')
print(f'{"Excluded":<10} | {"Reason":<30} | {"Employers":>10} | {"Workers":>15}')
print('-'*75)
total_included = 0
total_excluded = 0
for row in cur.fetchall():
    exc = row['exclude_from_counts']
    reason = row['exclude_reason'] or 'None'
    workers = row['raw_workers'] or 0
    if exc:
        total_excluded += workers
    else:
        total_included += workers
    print(f"{str(exc):<10} | {reason:<30} | {row['employers']:>10,} | {workers:>15,}")
print('-'*75)
print(f'   Total Included: {total_included:,}')
print(f'   Total Excluded: {total_excluded:,}')

# Private vs Public sector split
print('\n4. PRIVATE VS PUBLIC SECTOR (using NAICS/name patterns)')
print('-'*80)
cur.execute('''
    SELECT
        CASE
            WHEN naics IN ('92', '61') THEN 'Public (NAICS)'
            WHEN employer_name ILIKE ANY(ARRAY['%school%', '%university%', '%city of%', '%county of%', '%state of%', '%township%']) THEN 'Public (Name)'
            WHEN exclude_reason = 'FEDERAL_EMPLOYER' THEN 'Federal'
            ELSE 'Private'
        END as sector,
        SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
        SUM(latest_unit_size) as raw_workers,
        COUNT(*) as employers
    FROM f7_employers_deduped
    GROUP BY 1
    ORDER BY 2 DESC
''')
print(f'{"Sector":<20} | {"Counted":>15} | {"Raw":>15} | {"Employers":>10}')
print('-'*70)
private_counted = 0
for row in cur.fetchall():
    counted = row['counted_workers'] or 0
    raw = row['raw_workers'] or 0
    if row['sector'] == 'Private':
        private_counted = counted
    print(f"{row['sector']:<20} | {counted:>15,} | {raw:>15,} | {row['employers']:>10,}")

print(f'\n   PRIVATE SECTOR COUNTED (for update): {private_counted:,}')

# Current state_coverage_comparison
print('\n5. CURRENT STATE_COVERAGE_COMPARISON')
print('-'*80)
cur.execute("SELECT SUM(platform_private) as pp, SUM(epi_private) as ep FROM state_coverage_comparison WHERE state != 'DC'")
row = cur.fetchone()
print(f'   Current platform_private: {row["pp"]:,}')
print(f'   EPI private benchmark:    {row["ep"]:,}')
print(f'   Current coverage:         {row["pp"]/row["ep"]*100:.1f}%')
print(f'   New counted (private):    {private_counted:,}')
print(f'   New coverage would be:    {private_counted/row["ep"]*100:.1f}%')

conn.close()
