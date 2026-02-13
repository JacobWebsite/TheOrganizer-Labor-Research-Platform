import os
"""Show final target summary with funding data."""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

# Check current target scores with funding
cur.execute('''
    SELECT employer_name, city, industry_category,
           employee_count, ny_state_contract_count, ny_state_contract_total,
           priority_score, priority_tier
    FROM organizing_targets
    ORDER BY priority_score DESC
    LIMIT 25
''')

print('=' * 70)
print('TOP 25 AFSCME NY ORGANIZING TARGETS')
print('=' * 70)
for i, row in enumerate(cur.fetchall(), 1):
    name, city, industry, emp_cnt, contracts, funding, score, tier = row
    emp_str = f'{emp_cnt} employees' if emp_cnt else 'unknown size'
    funding_str = f'${float(funding)/1e6:.1f}M' if funding else '$0'
    print(f'{i:2}. [{tier}] {name[:50]}')
    print(f'       {city} | {industry or "Unknown"} | {emp_str}')
    print(f'       {contracts or 0} NY State contracts ({funding_str}) | Score: {score}')
    print()

# Tier summary
cur.execute('''
    SELECT priority_tier, COUNT(*),
           SUM(COALESCE(ny_state_contract_total, 0)),
           SUM(COALESCE(employee_count, 0))
    FROM organizing_targets
    GROUP BY priority_tier
    ORDER BY CASE priority_tier
        WHEN 'TOP' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END
''')
print('=' * 70)
print('TARGET TIER SUMMARY')
print('=' * 70)
print(f'{"Tier":<10} {"Count":<10} {"Total Funding":<20} {"Total Employees"}')
print('-' * 70)
for tier, cnt, funding, employees in cur.fetchall():
    funding_str = f'${float(funding)/1e6:.1f}M' if funding else '$0'
    emp_str = f'{employees:,}' if employees else '0'
    print(f'{tier:<10} {cnt:<10} {funding_str:<20} {emp_str}')

# Industry breakdown
cur.execute('''
    SELECT industry_category, COUNT(*),
           COUNT(*) FILTER (WHERE priority_tier IN ('TOP', 'HIGH')) as top_high,
           SUM(COALESCE(ny_state_contract_total, 0)) as total_funding
    FROM organizing_targets
    WHERE industry_category IS NOT NULL
    GROUP BY industry_category
    ORDER BY top_high DESC
''')
print()
print('=' * 70)
print('TARGETS BY INDUSTRY')
print('=' * 70)
print(f'{"Industry":<25} {"Total":<10} {"TOP/HIGH":<10} {"Funding"}')
print('-' * 70)
for industry, total, top_high, funding in cur.fetchall():
    funding_str = f'${float(funding)/1e6:.1f}M' if funding else '$0'
    print(f'{industry:<25} {total:<10} {top_high:<10} {funding_str}')

cur.close()
conn.close()
