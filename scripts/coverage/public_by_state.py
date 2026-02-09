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

print('=' * 140)
print('PUBLIC SECTOR COVERAGE BY STATE - PLATFORM vs EPI')
print('=' * 140)

# EPI public sector benchmarks
epi_public = {
    'AK': 32000, 'AL': 61000, 'AR': 19000, 'AZ': 52000, 'CA': 1283000,
    'CO': 103000, 'CT': 156000, 'DC': 21000, 'DE': 25000, 'FL': 246000,
    'GA': 86000, 'HI': 84000, 'IA': 41000, 'ID': 21000, 'IL': 352000,
    'IN': 82000, 'KS': 40000, 'KY': 38000, 'LA': 34000, 'MA': 266000,
    'MD': 214000, 'ME': 39000, 'MI': 178000, 'MN': 179000, 'MO': 85000,
    'MS': 20000, 'MT': 30000, 'NC': 44000, 'ND': 8000, 'NE': 38000,
    'NH': 35000, 'NJ': 327000, 'NM': 37000, 'NV': 59000, 'NY': 925000,
    'OH': 270000, 'OK': 57000, 'OR': 142000, 'PA': 322000, 'RI': 36000,
    'SC': 34000, 'SD': 7000, 'TN': 57000, 'TX': 293000, 'UT': 31000,
    'VA': 123000, 'VT': 23000, 'WA': 262000, 'WI': 62000, 'WV': 30000,
    'WY': 7000
}

# Get public sector data from database
cur.execute('''
    SELECT 
        state,
        olms_state_local_members,
        olms_federal_members,
        flra_federal_workers,
        data_quality_flag
    FROM public_sector_benchmarks
    WHERE state IS NOT NULL
''')

public_data = {}
for row in cur.fetchall():
    state, olms_sl, olms_fed, flra, quality = row
    # Use OLMS state/local + FLRA federal (not OLMS federal which is HQ-based)
    olms_sl = int(olms_sl or 0)
    flra = int(flra or 0)
    public_data[state] = {
        'olms_state_local': olms_sl,
        'flra_federal': flra,
        'total': olms_sl + flra,
        'quality': quality
    }

# Print comparison
print('\n{:<6} {:>12} {:>14} {:>12} {:>10} {:>12}'.format(
    'State', 'EPI_Public', 'Plat_Public', 'Gap', 'Coverage', 'Quality'))
print('-' * 75)

comparison = []
tot_epi = 0
tot_plat = 0

for state in sorted(epi_public.keys()):
    epi = epi_public[state]
    pub = public_data.get(state, {'total': 0, 'quality': ''})
    plat = pub['total']
    gap = plat - epi
    cov = (plat / epi * 100) if epi > 0 else 0
    
    tot_epi += epi
    tot_plat += plat
    comparison.append({'state': state, 'epi': epi, 'platform': plat, 'coverage': cov, 'quality': pub['quality']})
    
    print('{:<6} {:>12,} {:>14,} {:>12,} {:>9.1f}% {:<12}'.format(
        state, epi, plat, gap, cov, pub['quality'] or ''))

print('-' * 75)
tot_cov = (tot_plat / tot_epi * 100) if tot_epi > 0 else 0
print('{:<6} {:>12,} {:>14,} {:>12,} {:>9.1f}%'.format('TOTAL', tot_epi, tot_plat, tot_plat - tot_epi, tot_cov))

# Excluding DC (heavily distorted)
tot_epi_nodc = tot_epi - epi_public['DC']
tot_plat_nodc = tot_plat - public_data.get('DC', {}).get('total', 0)
tot_cov_nodc = (tot_plat_nodc / tot_epi_nodc * 100) if tot_epi_nodc > 0 else 0

print('\n--- Excluding DC (national HQ effects) ---')
print('EPI (excl DC):      {:>12,}'.format(tot_epi_nodc))
print('Platform (excl DC): {:>12,}'.format(tot_plat_nodc))
print('Coverage:           {:>12.1f}%'.format(tot_cov_nodc))

# Count quality categories
quality_counts = {}
for c in comparison:
    q = c['quality'] or 'UNKNOWN'
    quality_counts[q] = quality_counts.get(q, 0) + 1

print('\n--- Quality Distribution ---')
for q, cnt in sorted(quality_counts.items()):
    print('{:<15}: {} states'.format(q, cnt))

# Save
with open(r'C:\Users\jakew\Downloads\public_sector_by_state.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'EPI_Public', 'Platform_Public', 'Gap', 'Coverage_Pct', 'Quality_Flag'])
    for c in comparison:
        writer.writerow([c['state'], c['epi'], c['platform'], c['platform'] - c['epi'], 
                        round(c['coverage'], 1), c['quality']])
    writer.writerow([])
    writer.writerow(['TOTAL', tot_epi, tot_plat, tot_plat - tot_epi, round(tot_cov, 1), ''])
    writer.writerow(['TOTAL_EXCL_DC', tot_epi_nodc, tot_plat_nodc, tot_plat_nodc - tot_epi_nodc, round(tot_cov_nodc, 1), ''])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\public_sector_by_state.csv')

cur.close()
conn.close()
