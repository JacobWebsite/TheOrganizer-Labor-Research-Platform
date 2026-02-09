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

# Check union_hierarchy structure
print('=== UNION_HIERARCHY TABLE ===')
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'union_hierarchy'
    ORDER BY ordinal_position
""")
print('Columns:')
for row in cur.fetchall():
    print(f"  {row['column_name']}: {row['data_type']}")

cur.execute('SELECT COUNT(*) as cnt FROM union_hierarchy')
print(f"\nTotal rows: {cur.fetchone()['cnt']:,}")

cur.execute('SELECT * FROM union_hierarchy LIMIT 5')
print('\nSample rows:')
for row in cur.fetchall():
    print(dict(row))

# Check nlrb_union_xref
print('\n=== NLRB_UNION_XREF TABLE ===')
cur.execute('SELECT COUNT(*) as cnt FROM nlrb_union_xref')
print(f"Total rows: {cur.fetchone()['cnt']:,}")

cur.execute('SELECT * FROM nlrb_union_xref LIMIT 5')
print('Sample:')
for row in cur.fetchall():
    print(dict(row))

# Check SAG-AFTRA f_nums
print('\n=== SAG-AFTRA ANALYSIS ===')
cur.execute("""
    SELECT f_num, union_name, members 
    FROM unions_master 
    WHERE aff_abbr = 'SAGAFTRA'
    ORDER BY members DESC NULLS LAST
""")
print('SAG-AFTRA unions in OLMS:')
total_sagaftra = 0
for row in cur.fetchall():
    total_sagaftra += row['members'] or 0
    print(f"  {row['f_num']}: {row['union_name'][:50]} ({row['members'] or 0:,})")
print(f"Total SAG-AFTRA members: {total_sagaftra:,}")

# Check F-7 SAG-AFTRA employers not matched
print('\n=== F-7 SAG-AFTRA UNMATCHED ===')
cur.execute("""
    SELECT latest_union_name, COUNT(*) as emp_count, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped 
    WHERE latest_union_fnum IS NULL 
    AND (latest_union_name ILIKE '%sag-aftra%' OR latest_union_name ILIKE '%screen actors%')
    GROUP BY latest_union_name
    ORDER BY workers DESC NULLS LAST
""")
total_unmatched_workers = 0
for row in cur.fetchall():
    total_unmatched_workers += row['workers'] or 0
    print(f"  {row['latest_union_name'][:55]}: {row['emp_count']} emp, {row['workers'] or 0:,.0f} workers")
print(f"\nTotal unmatched SAG-AFTRA workers: {total_unmatched_workers:,}")

conn.close()
