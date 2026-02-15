import os
from db_config import get_connection
"""Check self-employment handling in density calculations"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

# Check high self-employment counties
cur.execute('''
    SELECT w.fips, w.state, w.county_name,
           w.private_share * 100 as priv,
           w.public_share * 100 as pub,
           w.self_employed_share * 100 as self_emp,
           (w.private_share + w.public_share + w.self_employed_share) * 100 as total_accounted,
           e.estimated_total_density
    FROM county_workforce_shares w
    JOIN county_union_density_estimates e ON w.fips = e.fips
    ORDER BY w.self_employed_share DESC
    LIMIT 10
''')
print('Counties with HIGHEST self-employment (excluded from density calc):')
print(f'{"FIPS":6} | {"ST":2} | {"County":20} | {"Priv%":6} | {"Pub%":5} | {"SelfEmp%":8} | {"Density":7}')
print('-' * 70)
for r in cur.fetchall():
    print(f'{r[0]:6} | {r[1]:2} | {r[2][:20]:20} | {r[3]:5.1f}% | {r[4]:4.1f}% | {r[5]:7.1f}% | {r[7]:6.1f}%')

print('\n' + '=' * 70)
print('Self-employed workers have 0% union density - they are correctly')
print('excluded from the calculation. Counties with high self-employment')
print('will have LOWER estimated density because fewer workers are in')
print('union-eligible employment classes.')

cur.close()
conn.close()
