import os
import psycopg2
import csv

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

print('=' * 120)
print('REFINED PLATFORM COVERAGE VS EPI BENCHMARKS BY STATE')
print('=' * 120)

# First, understand the v_f7_private_sector_reconciled structure better
print('\n=== Private Sector Reconciliation (6.25M Total) ===')
cur.execute('SELECT SUM(reconciled_workers) FROM v_f7_private_sector_reconciled')
print('Total reconciled private sector: {:,}'.format(int(cur.fetchone()[0] or 0)))

# Check if we can break down by state - look at the underlying data
cur.execute('''
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'v_f7_private_sector_reconciled'
''')
print('Columns:', [row[0] for row in cur.fetchall()])

# Let me check the f7_employers_deduped with adjustment factors applied differently
# The summary shows 6.25M but the view shows 10.4M - need to understand why

# Check v_f7_reconciled_private_sector for state breakdown
print('\n=== v_f7_reconciled_private_sector ===')
cur.execute('''
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'v_f7_reconciled_private_sector'
''')
print('Columns:', [row[0] for row in cur.fetchall()])

# Get the view definition
cur.execute('''
    SELECT pg_get_viewdef('v_f7_reconciled_private_sector'::regclass, true)
''')
print('\nView definition (truncated):')
defn = cur.fetchone()[0][:500]
print(defn)

# Check public_sector_benchmarks for all states
print('\n\n=== PUBLIC SECTOR BENCHMARKS BY STATE ===')
cur.execute('''
    SELECT 
        state,
        state_name,
        epi_public_members,
        olms_state_local_members,
        olms_federal_members,
        flra_federal_workers,
        estimated_gap,
        data_quality_flag
    FROM public_sector_benchmarks
    ORDER BY state
''')

print('{:<5} {:<20} {:>15} {:>15} {:>12} {:>12} {:>12} {:<12}'.format(
    'St', 'State', 'EPI_Public', 'OLMS_StLocal', 'OLMS_Fed', 'FLRA_Fed', 'Gap', 'Quality'))
print('-' * 120)

results = []
for row in cur.fetchall():
    state, name, epi_pub, olms_sl, olms_fed, flra_fed, gap, quality = row
    epi_pub = int(epi_pub or 0)
    olms_sl = int(olms_sl or 0)
    olms_fed = int(olms_fed or 0)
    flra_fed = int(flra_fed or 0)
    gap = int(gap or 0)
    
    results.append({
        'state': state,
        'state_name': name,
        'epi_public': epi_pub,
        'olms_state_local': olms_sl,
        'olms_federal': olms_fed,
        'flra_federal': flra_fed,
        'gap': gap,
        'quality': quality
    })
    
    print('{:<5} {:<20} {:>15,} {:>15,} {:>12,} {:>12,} {:>12,} {:<12}'.format(
        state, name[:20], epi_pub, olms_sl, olms_fed, flra_fed, gap, quality or ''))

# Check v_public_sector_state_recon for more detail
print('\n\n=== v_public_sector_state_recon ===')
cur.execute('''
    SELECT column_name FROM information_schema.columns 
    WHERE table_name = 'v_public_sector_state_recon'
''')
cols = [row[0] for row in cur.fetchall()]
print('Columns:', cols)

if cols:
    cur.execute('SELECT * FROM v_public_sector_state_recon LIMIT 5')
    for row in cur.fetchall():
        print(row)

cur.close()
conn.close()
