import os
from db_config import get_connection
"""Check remaining potential duplicates"""
import psycopg2
conn = get_connection()
cur = conn.cursor()

# Check remaining potential issues
print('=== Remaining Large Unions (not yet excluded) ===')
cur.execute('''
    SELECT latest_union_fnum, MAX(latest_union_name) as union_name,
           COUNT(*) as emp_count,
           SUM(latest_unit_size) as total,
           COUNT(DISTINCT latest_unit_size) as distinct_sizes
    FROM f7_employers_deduped
    WHERE exclude_reason IS NULL
      AND latest_union_fnum IS NOT NULL
    GROUP BY latest_union_fnum
    HAVING COUNT(*) > 10
       AND SUM(latest_unit_size) > 50000
    ORDER BY SUM(latest_unit_size) DESC
    LIMIT 15
''')
for row in cur.fetchall():
    print(f'{row[1][:45]:<45} | {row[2]:>4} emps | {row[3]:>9,} total | {row[4]:>3} sizes')

# Check if there are patterns with repeated worker counts
print()
print('=== Unions with Many Identical Worker Counts (potential duplicates) ===')
cur.execute('''
    WITH repeated AS (
        SELECT latest_union_fnum, latest_unit_size,
               COUNT(*) as repeat_count
        FROM f7_employers_deduped
        WHERE exclude_reason IS NULL
          AND latest_unit_size >= 100
        GROUP BY latest_union_fnum, latest_unit_size
        HAVING COUNT(*) >= 5
    )
    SELECT f.latest_union_fnum, MAX(f.latest_union_name) as union_name,
           r.latest_unit_size, r.repeat_count,
           r.latest_unit_size * (r.repeat_count - 1) as excess_workers
    FROM repeated r
    JOIN f7_employers_deduped f ON f.latest_union_fnum = r.latest_union_fnum
    WHERE f.exclude_reason IS NULL
    GROUP BY f.latest_union_fnum, r.latest_unit_size, r.repeat_count
    ORDER BY r.latest_unit_size * (r.repeat_count - 1) DESC
    LIMIT 20
''')
print(f'{"Union":<40} | {"Size":>8} | {"Repeats":>7} | {"Excess":>10}')
print('-'*75)
for row in cur.fetchall():
    print(f'{(row[1] or "?")[:40]:<40} | {row[2]:>8,} | {row[3]:>7} | {row[4]:>10,}')

conn.close()
