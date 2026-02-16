import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

cur.execute('''
    SELECT organization_name, ein, dues_revenue, dues_rate_used, estimated_members, dues_rate_source
    FROM form_990_estimates
    WHERE org_type LIKE 'AFSCME%' OR org_type LIKE 'SEIU%'
    ORDER BY estimated_members DESC
''')

print('AFSCME/SEIU in Form 990 estimates:')
print('=' * 100)
for r in cur.fetchall():
    name, ein, dues, rate, members, source = r
    print(f'{name[:45]:<47} EIN: {ein:<12}')
    print(f'  Dues Revenue: ${float(dues):>14,.0f}')
    print(f'  Rate Used:    ${float(rate):>6.0f}/member')
    print(f'  Est Members:  {members:>10,}')
    print(f'  Source: {source[:80]}')
    print()

conn.close()
