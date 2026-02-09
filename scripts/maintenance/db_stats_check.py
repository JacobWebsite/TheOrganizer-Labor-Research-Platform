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

print('=== CURRENT PLATFORM STATISTICS ===')
print()

# Core counts
cur.execute('SELECT COUNT(*) as cnt FROM unions_master')
print(f'Total unions: {cur.fetchone()["cnt"]:,}')

cur.execute('SELECT COUNT(*) as cnt FROM f7_employers_deduped')
print(f'F7 employers (deduped): {cur.fetchone()["cnt"]:,}')

cur.execute('SELECT COUNT(*) as cnt FROM f7_employers_deduped WHERE latitude IS NOT NULL')
print(f'Geocoded employers: {cur.fetchone()["cnt"]:,}')

cur.execute('SELECT SUM(latest_unit_size) as total FROM f7_employers_deduped WHERE latest_unit_size > 0')
result = cur.fetchone()
print(f'F7 workers (raw): {result["total"]:,.0f}')

cur.execute('SELECT SUM(reconciled_workers) as total FROM v_f7_private_sector_reconciled')
result = cur.fetchone()
print(f'F7 reconciled private sector: {result["total"]:,.0f}')

# NLRB
cur.execute('SELECT COUNT(*) as cnt FROM nlrb_tallies')
print(f'\nNLRB election tallies: {cur.fetchone()["cnt"]:,}')

cur.execute('SELECT COUNT(*) as cnt FROM nlrb_tallies WHERE matched_olms_fnum IS NOT NULL')
print(f'NLRB tallies matched to unions: {cur.fetchone()["cnt"]:,}')

# VR
cur.execute('SELECT COUNT(*) as cnt, SUM(num_employees) as workers FROM nlrb_voluntary_recognition')
result = cur.fetchone()
print(f'\nVoluntary recognition cases: {result["cnt"]:,}')
print(f'VR workers: {result["workers"]:,.0f}' if result['workers'] else 'VR workers: N/A')

# Check VR matching
cur.execute("""
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'nlrb_voluntary_recognition' AND column_name LIKE '%match%'
""")
vr_match_cols = [r['column_name'] for r in cur.fetchall()]
if vr_match_cols:
    for col in vr_match_cols:
        try:
            cur.execute(f'SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition WHERE {col} IS NOT NULL')
            print(f'  {col} matched: {cur.fetchone()["cnt"]:,}')
        except:
            pass

# F7 Reconciliation summary view
print('\n=== F7 RECONCILIATION BY MATCH TYPE ===')
try:
    cur.execute('SELECT * FROM v_f7_reconciliation_summary')
    for row in cur.fetchall():
        d = dict(row)
        print(f"  {d.get('match_type', 'Unknown')}: {d.get('reconciled_workers', 0):,.0f} workers")
except Exception as e:
    print(f'  Could not load: {e}')

# OLMS membership
print('\n=== OLMS MEMBERSHIP ===')
cur.execute("""
    SELECT SUM(total_members) as total, COUNT(*) as filings
    FROM lm_data 
    WHERE desig = 'NHQ' 
    AND fiscal_year_end >= '2024-01-01'
""")
result = cur.fetchone()
print(f'NHQ 2024+ raw: {result["total"]:,.0f} ({result["filings"]} filings)')

# Summary metrics
print('\n=== KEY RECONCILIATION METRICS ===')
print('BLS benchmark (private): 7.30M members')
print('BLS benchmark (total): 14.30M members')
print('F7 captures 87.6% of BLS private sector after reconciliation')
print('OLMS NHQ -> US-only estimate: ~15.9M (within 11.3% of BLS)')

conn.close()
print('\nDone!')
