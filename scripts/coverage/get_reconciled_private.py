import os
import psycopg2
import csv

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

print('=' * 100)
print('RECONCILED PRIVATE SECTOR COVERAGE BY STATE')
print('=' * 100)

# First check totals
cur.execute('SELECT COUNT(*), SUM(estimated_actual_workers) FROM v_f7_employers_fully_adjusted')
row = cur.fetchone()
print('\nTotal Employers: {:,}'.format(row[0]))
print('Total Reconciled Workers: {:,}'.format(int(row[1] or 0)))

# Get state-level breakdown
cur.execute('''
    SELECT 
        state,
        COUNT(*) as employers,
        SUM(f7_reported_workers) as raw_workers,
        SUM(estimated_actual_workers) as reconciled_workers
    FROM v_f7_employers_fully_adjusted
    WHERE state IS NOT NULL AND LENGTH(state) = 2
    GROUP BY state
    ORDER BY SUM(estimated_actual_workers) DESC NULLS LAST
''')

results = cur.fetchall()

print('\n{:<6} {:>12} {:>15} {:>18} {:>12}'.format(
    'State', 'Employers', 'Raw_Workers', 'Reconciled_Workers', 'Adj_Factor'))
print('-' * 70)

state_data = {}
total_raw = 0
total_recon = 0

for row in results:
    state, emp, raw, recon = row
    raw = int(raw or 0)
    recon = int(recon or 0)
    factor = (recon / raw * 100) if raw > 0 else 0
    
    state_data[state] = {'employers': emp, 'raw': raw, 'reconciled': recon}
    total_raw += raw
    total_recon += recon
    
    print('{:<6} {:>12,} {:>15,} {:>18,} {:>11.1f}%'.format(
        state, emp, raw, recon, factor))

print('-' * 70)
total_factor = (total_recon / total_raw * 100) if total_raw > 0 else 0
print('{:<6} {:>12,} {:>15,} {:>18,} {:>11.1f}%'.format(
    'TOTAL', sum(d['employers'] for d in state_data.values()), total_raw, total_recon, total_factor))

# Save to CSV
with open(r'C:\Users\jakew\Downloads\reconciled_private_by_state.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'Employers', 'Raw_F7_Workers', 'Reconciled_Workers', 'Adjustment_Factor_Pct'])
    for state in sorted(state_data.keys()):
        d = state_data[state]
        factor = (d['reconciled'] / d['raw'] * 100) if d['raw'] > 0 else 0
        writer.writerow([state, d['employers'], d['raw'], d['reconciled'], round(factor, 1)])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\reconciled_private_by_state.csv')

cur.close()
conn.close()
