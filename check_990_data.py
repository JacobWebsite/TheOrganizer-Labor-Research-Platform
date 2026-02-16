from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

tables = ['national_990_filers', 'ny_990_filers', 'labor_orgs_990', 'irs_bmf']

for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    count = cur.fetchone()[0]
    print(f'{t}: {count:,} rows')

conn.close()
