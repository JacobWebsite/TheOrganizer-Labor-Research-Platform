"""Check discovered_employers table status"""
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Get summary stats
cur.execute('''
SELECT
    source_type,
    COUNT(*) as count,
    SUM(num_employees) as total_workers
FROM discovered_employers
GROUP BY source_type
ORDER BY count DESC
''')
print('DISCOVERED EMPLOYERS BY SOURCE:')
for row in cur.fetchall():
    workers = row['total_workers'] or 0
    print(f"  {row['source_type']}: {row['count']} events, {workers:,} workers")

cur.execute('SELECT COUNT(*), SUM(num_employees) FROM discovered_employers')
row = cur.fetchone()
print(f"\nTOTAL: {row['count']} events, {row['sum']:,} workers")

print('\nNEW 2024 EXPANDED RECORDS:')
cur.execute('''
SELECT employer_name, city, state, union_name, num_employees, recognition_type
FROM discovered_employers
WHERE source_type = 'DISCOVERY_2024_EXPANDED'
ORDER BY num_employees DESC
''')
for row in cur.fetchall():
    print(f"  {row['employer_name'][:40]:<40} | {row['state']:>2} | {row['union_name'][:25]:<25} | {row['num_employees']:>5} | {row['recognition_type']}")

print('\nBY RECOGNITION TYPE:')
cur.execute('''
SELECT recognition_type, COUNT(*) as count, SUM(num_employees) as workers
FROM discovered_employers
GROUP BY recognition_type
ORDER BY count DESC
''')
for row in cur.fetchall():
    workers = row['workers'] or 0
    print(f"  {row['recognition_type']:<20} {row['count']:>3} events, {workers:>7,} workers")

print('\nBY AFFILIATION:')
cur.execute('''
SELECT affiliation, COUNT(*) as count, SUM(num_employees) as workers
FROM discovered_employers
GROUP BY affiliation
ORDER BY workers DESC NULLS LAST
''')
for row in cur.fetchall():
    workers = row['workers'] or 0
    print(f"  {row['affiliation']:<15} {row['count']:>3} events, {workers:>7,} workers")

cur.close()
conn.close()
