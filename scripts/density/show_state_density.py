import os
from db_config import get_connection
"""Display union density rates for all states"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

cur.execute('''
    SELECT state, state_name,
           private_density_pct, private_year,
           public_density_pct, public_year, public_is_estimated,
           total_density_pct, total_year
    FROM v_state_density_latest
    ORDER BY state
''')

print('=' * 95)
print('STATE UNION DENSITY RATES (Latest Available Year)')
print('=' * 95)
print(f'{"State":5} | {"State Name":22} | {"Private":8} | {"Public":8} | {"Est?":4} | {"Total":8}')
print(f'{"-----":5} | {"----------------------":22} | {"--------":8} | {"--------":8} | {"----":4} | {"--------":8}')

for r in cur.fetchall():
    state = r[0] or ''
    name = (r[1] or '')[:22]
    priv = f'{r[2]:.1f}%' if r[2] else 'N/A'
    pub = f'{r[4]:.1f}%' if r[4] else 'N/A'
    est = '*' if r[6] else ''
    tot = f'{r[7]:.1f}%' if r[7] else 'N/A'
    print(f'{state:5} | {name:22} | {priv:>8} | {pub:>8} | {est:>4} | {tot:>8}')

print('=' * 95)
print('* = Estimated from total and private density (small CPS sample size)')

# Summary stats
cur.execute('''
    SELECT
        ROUND(AVG(private_density_pct), 1) as avg_private,
        ROUND(AVG(public_density_pct), 1) as avg_public,
        ROUND(AVG(total_density_pct), 1) as avg_total,
        COUNT(CASE WHEN public_is_estimated THEN 1 END) as estimated_count
    FROM v_state_density_latest
''')
r = cur.fetchone()
print(f'\nAverages: Private {r[0]}% | Public {r[1]}% | Total {r[2]}%')
print(f'Estimated public density: {r[3]} states')

cur.close()
conn.close()
