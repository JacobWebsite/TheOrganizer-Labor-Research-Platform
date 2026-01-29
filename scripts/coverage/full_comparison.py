import psycopg2
import csv

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

print('=' * 120)
print('COMPLETE PLATFORM COVERAGE VS EPI BENCHMARKS BY STATE')
print('=' * 120)

# EPI 2024 benchmarks (from earlier extraction)
epi_data = {
    'AL': {'total': 139913, 'private': 78538, 'public': 61000},
    'AK': {'total': 52866, 'private': 20385, 'public': 32000},
    'AZ': {'total': 118002, 'private': 65763, 'public': 52000},
    'AR': {'total': 45011, 'private': 26025, 'public': 19000},
    'CA': {'total': 2374726, 'private': 1091677, 'public': 1283000},
    'CO': {'total': 206583, 'private': 104024, 'public': 103000},
    'CT': {'total': 268956, 'private': 113037, 'public': 156000},
    'DE': {'total': 36907, 'private': 12342, 'public': 25000},
    'DC': {'total': 38336, 'private': 17283, 'public': 21000},
    'FL': {'total': 461826, 'private': 215919, 'public': 246000},
    'GA': {'total': 174826, 'private': 88818, 'public': 86000},
    'HI': {'total': 147386, 'private': 63592, 'public': 84000},
    'ID': {'total': 42589, 'private': 21445, 'public': 21000},
    'IL': {'total': 734841, 'private': 382476, 'public': 352000},
    'IN': {'total': 270109, 'private': 188006, 'public': 82000},
    'IA': {'total': 92643, 'private': 51552, 'public': 41000},
    'KS': {'total': 83279, 'private': 43261, 'public': 40000},
    'KY': {'total': 155911, 'private': 117846, 'public': 38000},
    'LA': {'total': 68216, 'private': 34103, 'public': 34000},
    'ME': {'total': 76405, 'private': 37730, 'public': 39000},
    'MD': {'total': 324134, 'private': 110514, 'public': 214000},
    'MA': {'total': 494867, 'private': 228375, 'public': 266000},
    'MI': {'total': 580656, 'private': 402477, 'public': 178000},
    'MN': {'total': 377255, 'private': 197917, 'public': 179000},
    'MS': {'total': 58902, 'private': 38530, 'public': 20000},
    'MO': {'total': 233080, 'private': 147865, 'public': 85000},
    'MT': {'total': 56321, 'private': 25863, 'public': 30000},
    'NE': {'total': 62149, 'private': 24504, 'public': 38000},
    'NV': {'total': 165047, 'private': 106416, 'public': 59000},
    'NH': {'total': 62262, 'private': 27381, 'public': 35000},
    'NJ': {'total': 680140, 'private': 352849, 'public': 327000},
    'NM': {'total': 62747, 'private': 25697, 'public': 37000},
    'NY': {'total': 1705864, 'private': 781226, 'public': 925000},
    'NC': {'total': 107594, 'private': 63643, 'public': 44000},
    'ND': {'total': 18151, 'private': 10265, 'public': 8000},
    'OH': {'total': 621419, 'private': 351676, 'public': 270000},
    'OK': {'total': 91623, 'private': 34430, 'public': 57000},
    'OR': {'total': 293022, 'private': 151290, 'public': 142000},
    'PA': {'total': 667157, 'private': 344832, 'public': 322000},
    'RI': {'total': 72247, 'private': 36660, 'public': 36000},
    'SC': {'total': 60947, 'private': 26931, 'public': 34000},
    'SD': {'total': 11597, 'private': 4965, 'public': 7000},
    'TN': {'total': 135565, 'private': 78333, 'public': 57000},
    'TX': {'total': 601661, 'private': 308806, 'public': 293000},
    'UT': {'total': 57715, 'private': 26912, 'public': 31000},
    'VT': {'total': 42451, 'private': 19683, 'public': 23000},
    'VA': {'total': 208129, 'private': 84702, 'public': 123000},
    'WA': {'total': 547944, 'private': 285629, 'public': 262000},
    'WV': {'total': 61079, 'private': 30972, 'public': 30000},
    'WI': {'total': 180486, 'private': 118440, 'public': 62000},
    'WY': {'total': 13916, 'private': 7136, 'public': 7000},
}

# Get reconciled private sector by state
cur.execute('''
    SELECT 
        state,
        COUNT(*) as employers,
        SUM(estimated_actual_workers) as reconciled_workers
    FROM v_f7_employers_fully_adjusted
    WHERE state IS NOT NULL AND LENGTH(state) = 2
    GROUP BY state
''')
private_data = {row[0]: {'employers': row[1], 'workers': int(row[2] or 0)} for row in cur.fetchall()}

# Check what public sector data we have - try federal_bargaining_units with state
print('\n--- Checking Public Sector Data Sources ---')

# Check if federal_bargaining_units has state info
cur.execute('''SELECT column_name FROM information_schema.columns 
               WHERE table_name = 'federal_bargaining_units' AND column_name LIKE '%state%' ''')
cols = cur.fetchall()
print('Federal bargaining units state columns:', [c[0] for c in cols])

# Check public_sector_employers
cur.execute('''
    SELECT state, COUNT(*), employer_type
    FROM public_sector_employers
    WHERE state IS NOT NULL
    GROUP BY state, employer_type
    ORDER BY COUNT(*) DESC
    LIMIT 10
''')
print('\nPublic sector employers sample:')
for row in cur.fetchall():
    print('  {} - {} ({})'.format(row[0], row[1], row[2]))

# Get federal bargaining units total by extracting state from activity/description
cur.execute('SELECT SUM(total_in_unit) FROM federal_bargaining_units WHERE total_in_unit IS NOT NULL')
federal_total = int(cur.fetchone()[0] or 0)
print('\nFederal bargaining units total: {:,} workers'.format(federal_total))

# Check unions_master for public sector by state (union HQ location)
cur.execute('''
    SELECT 
        state,
        SUM(CASE WHEN sector_revised = 'FEDERAL' THEN members ELSE 0 END) as federal_members,
        SUM(CASE WHEN sector_revised = 'PUBLIC_SECTOR' THEN members ELSE 0 END) as public_members
    FROM unions_master
    WHERE state IS NOT NULL AND LENGTH(state) = 2 AND members > 0
    GROUP BY state
    ORDER BY SUM(members) DESC
''')
public_by_state = {}
for row in cur.fetchall():
    state = row[0]
    public_by_state[state] = {
        'federal': int(row[1] or 0),
        'state_local': int(row[2] or 0),
        'total_public': int(row[1] or 0) + int(row[2] or 0)
    }

# Build comprehensive comparison
print('\n' + '=' * 150)
print('PRIVATE SECTOR: Platform Reconciled vs EPI Benchmark')
print('=' * 150)
print('{:<6} {:>12} {:>15} {:>12} {:>10} | {:>12} {:>15} {:>12}'.format(
    'State', 'EPI_Private', 'Plat_Private', 'Diff', 'Cov%', 'EPI_Public', 'Plat_Public*', 'Pub_Cov%'))
print('-' * 150)

results = []
for state in sorted(epi_data.keys()):
    epi = epi_data[state]
    plat_priv = private_data.get(state, {}).get('workers', 0)
    plat_pub = public_by_state.get(state, {}).get('total_public', 0)
    
    priv_diff = plat_priv - epi['private']
    priv_cov = (plat_priv / epi['private'] * 100) if epi['private'] > 0 else 0
    pub_cov = (plat_pub / epi['public'] * 100) if epi['public'] > 0 else 0
    
    results.append({
        'state': state,
        'epi_total': epi['total'],
        'epi_private': epi['private'],
        'epi_public': epi['public'],
        'plat_private': plat_priv,
        'plat_public': plat_pub,
        'priv_cov': priv_cov,
        'pub_cov': pub_cov
    })
    
    print('{:<6} {:>12,} {:>15,} {:>12,} {:>9.1f}% | {:>12,} {:>15,} {:>11.1f}%'.format(
        state, epi['private'], plat_priv, priv_diff, priv_cov,
        epi['public'], plat_pub, pub_cov))

# Totals
tot_epi_priv = sum(epi_data[s]['private'] for s in epi_data)
tot_epi_pub = sum(epi_data[s]['public'] for s in epi_data)
tot_plat_priv = sum(private_data.get(s, {}).get('workers', 0) for s in epi_data)
tot_plat_pub = sum(public_by_state.get(s, {}).get('total_public', 0) for s in epi_data)

print('-' * 150)
priv_cov = (tot_plat_priv / tot_epi_priv * 100) if tot_epi_priv > 0 else 0
pub_cov = (tot_plat_pub / tot_epi_pub * 100) if tot_epi_pub > 0 else 0
print('{:<6} {:>12,} {:>15,} {:>12,} {:>9.1f}% | {:>12,} {:>15,} {:>11.1f}%'.format(
    'TOTAL', tot_epi_priv, tot_plat_priv, tot_plat_priv - tot_epi_priv, priv_cov,
    tot_epi_pub, tot_plat_pub, pub_cov))

print('\n* Public sector note: Platform data is union HQ location from OLMS filings, not worker location')
print('  This creates significant distortion (e.g., DC shows inflated numbers due to national HQs)')

# Summary
print('\n' + '=' * 100)
print('COVERAGE SUMMARY')
print('=' * 100)
print('\nPRIVATE SECTOR:')
print('  EPI Benchmark:              {:>12,}'.format(tot_epi_priv))
print('  Platform Reconciled:        {:>12,}'.format(tot_plat_priv))
print('  Coverage:                   {:>12}'.format('{:.1f}%'.format(priv_cov)))

print('\nPUBLIC SECTOR:')
print('  EPI Benchmark:              {:>12,}'.format(tot_epi_pub))
print('  Platform (HQ-based):        {:>12,}'.format(tot_plat_pub))
print('  Coverage:                   {:>12}'.format('{:.1f}%'.format(pub_cov)))
print('  Federal (FLRA actual):      {:>12,}'.format(federal_total))

# Save to CSV
with open(r'C:\Users\jakew\Downloads\platform_vs_epi_by_state.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'EPI_Total', 'EPI_Private', 'EPI_Public',
                     'Platform_Private_Reconciled', 'Platform_Public_HQ',
                     'Private_Coverage_Pct', 'Public_Coverage_Pct', 'Notes'])
    for r in results:
        note = ''
        if r['state'] == 'DC':
            note = 'Public inflated - national HQs'
        elif r['priv_cov'] > 150:
            note = 'Private high - multi-employer effects'
        elif r['priv_cov'] < 50:
            note = 'Private gap'
        writer.writerow([r['state'], r['epi_total'], r['epi_private'], r['epi_public'],
                        r['plat_private'], r['plat_public'],
                        round(r['priv_cov'], 1), round(r['pub_cov'], 1), note])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\platform_vs_epi_by_state.csv')

cur.close()
conn.close()
