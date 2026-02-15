import os
import psycopg2
import csv

from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

print('=' * 140)
print('COMPREHENSIVE PLATFORM COVERAGE VS EPI BENCHMARKS BY STATE')
print('Using Reconciled Data (~6.25M Private, Public Sector Breakdown)')
print('=' * 140)

# EPI 2024 Complete Benchmarks
epi_data = {
    'AK': {'private': 20385, 'public': 32000},
    'AL': {'private': 78538, 'public': 61000},
    'AR': {'private': 26025, 'public': 19000},
    'AZ': {'private': 65763, 'public': 52000},
    'CA': {'private': 1091677, 'public': 1283000},
    'CO': {'private': 104024, 'public': 103000},
    'CT': {'private': 113037, 'public': 156000},
    'DC': {'private': 17283, 'public': 21000},
    'DE': {'private': 12342, 'public': 25000},
    'FL': {'private': 215919, 'public': 246000},
    'GA': {'private': 88818, 'public': 86000},
    'HI': {'private': 63592, 'public': 84000},
    'IA': {'private': 51552, 'public': 41000},
    'ID': {'private': 21445, 'public': 21000},
    'IL': {'private': 382476, 'public': 352000},
    'IN': {'private': 188006, 'public': 82000},
    'KS': {'private': 43261, 'public': 40000},
    'KY': {'private': 117846, 'public': 38000},
    'LA': {'private': 34103, 'public': 34000},
    'MA': {'private': 228375, 'public': 266000},
    'MD': {'private': 110514, 'public': 214000},
    'ME': {'private': 37730, 'public': 39000},
    'MI': {'private': 402477, 'public': 178000},
    'MN': {'private': 197917, 'public': 179000},
    'MO': {'private': 147865, 'public': 85000},
    'MS': {'private': 38530, 'public': 20000},
    'MT': {'private': 25863, 'public': 30000},
    'NC': {'private': 63643, 'public': 44000},
    'ND': {'private': 10265, 'public': 8000},
    'NE': {'private': 24504, 'public': 38000},
    'NH': {'private': 27381, 'public': 35000},
    'NJ': {'private': 352849, 'public': 327000},
    'NM': {'private': 25697, 'public': 37000},
    'NV': {'private': 106416, 'public': 59000},
    'NY': {'private': 781226, 'public': 925000},
    'OH': {'private': 351676, 'public': 270000},
    'OK': {'private': 34430, 'public': 57000},
    'OR': {'private': 151290, 'public': 142000},
    'PA': {'private': 344832, 'public': 322000},
    'RI': {'private': 36660, 'public': 36000},
    'SC': {'private': 26931, 'public': 34000},
    'SD': {'private': 4965, 'public': 7000},
    'TN': {'private': 78333, 'public': 57000},
    'TX': {'private': 308806, 'public': 293000},
    'UT': {'private': 26912, 'public': 31000},
    'VA': {'private': 84702, 'public': 123000},
    'VT': {'private': 19683, 'public': 23000},
    'WA': {'private': 285629, 'public': 262000},
    'WI': {'private': 118440, 'public': 62000},
    'WV': {'private': 30972, 'public': 30000},
    'WY': {'private': 7136, 'public': 7000},
}

# Get reconciled PRIVATE sector by state (the 6.25M total)
cur.execute('''
    SELECT 
        state,
        COUNT(*) as employers,
        SUM(f7_reported_workers) as raw_workers,
        SUM(reconciled_workers) as reconciled_workers
    FROM v_f7_reconciled_private_sector
    WHERE state IS NOT NULL AND LENGTH(state) = 2
    GROUP BY state
''')
private_data = {}
for row in cur.fetchall():
    state, emp, raw, recon = row
    private_data[state] = {
        'employers': emp,
        'raw': int(raw or 0),
        'reconciled': int(recon or 0)
    }

# Get PUBLIC sector by state from the benchmarks table
cur.execute('''
    SELECT 
        state,
        olms_state_local_members,
        olms_federal_members,
        flra_federal_workers,
        data_quality_flag
    FROM public_sector_benchmarks
''')
public_data = {}
for row in cur.fetchall():
    state, olms_sl, olms_fed, flra, quality = row
    public_data[state] = {
        'olms_state_local': int(olms_sl or 0),
        'olms_federal': int(olms_fed or 0),
        'flra_federal': int(flra or 0),
        'quality': quality
    }

# Build comparison table
print('\n' + '=' * 160)
print('PRIVATE SECTOR COMPARISON')
print('=' * 160)
print('{:<5} {:>12} {:>14} {:>12} {:>8} | {:>12} {:>14} {:>12} {:>10}'.format(
    'St', 'EPI_Priv', 'Plat_Priv', 'Gap', 'Cov%', 'EPI_Pub', 'Plat_Pub', 'Pub_Gap', 'Quality'))
print('-' * 160)

results = []
tot_epi_priv = tot_epi_pub = tot_plat_priv = tot_plat_pub = 0

for state in sorted(epi_data.keys()):
    epi = epi_data[state]
    priv = private_data.get(state, {'employers': 0, 'raw': 0, 'reconciled': 0})
    pub = public_data.get(state, {'olms_state_local': 0, 'olms_federal': 0, 'flra_federal': 0, 'quality': ''})
    
    # Platform public = OLMS state/local + FLRA federal (using actual FLRA worker counts, not OLMS federal which is HQ-based)
    plat_pub = pub['olms_state_local'] + pub['flra_federal']
    
    priv_gap = priv['reconciled'] - epi['private']
    priv_cov = (priv['reconciled'] / epi['private'] * 100) if epi['private'] > 0 else 0
    pub_gap = plat_pub - epi['public']
    
    tot_epi_priv += epi['private']
    tot_epi_pub += epi['public']
    tot_plat_priv += priv['reconciled']
    tot_plat_pub += plat_pub
    
    results.append({
        'state': state,
        'epi_private': epi['private'],
        'epi_public': epi['public'],
        'plat_private': priv['reconciled'],
        'plat_public': plat_pub,
        'priv_coverage': priv_cov,
        'quality': pub['quality']
    })
    
    print('{:<5} {:>12,} {:>14,} {:>12,} {:>7.1f}% | {:>12,} {:>14,} {:>12,} {:<10}'.format(
        state, epi['private'], priv['reconciled'], priv_gap, priv_cov,
        epi['public'], plat_pub, pub_gap, pub['quality'] or ''))

print('-' * 160)
tot_priv_cov = (tot_plat_priv / tot_epi_priv * 100) if tot_epi_priv > 0 else 0
print('{:<5} {:>12,} {:>14,} {:>12,} {:>7.1f}% | {:>12,} {:>14,} {:>12,}'.format(
    'TOT', tot_epi_priv, tot_plat_priv, tot_plat_priv - tot_epi_priv, tot_priv_cov,
    tot_epi_pub, tot_plat_pub, tot_plat_pub - tot_epi_pub))

# Summary
print('\n' + '=' * 100)
print('SUMMARY')
print('=' * 100)
print('\nPRIVATE SECTOR (F-7 Reconciled):')
print('  EPI 2024 Benchmark:         {:>12,}'.format(tot_epi_priv))
print('  Platform Reconciled:        {:>12,}'.format(tot_plat_priv))
print('  Coverage:                   {:>12.1f}%'.format(tot_priv_cov))
print('  Gap:                        {:>12,}'.format(tot_plat_priv - tot_epi_priv))

print('\nPUBLIC SECTOR (OLMS State/Local + FLRA Federal):')
print('  EPI 2024 Benchmark:         {:>12,}'.format(tot_epi_pub))
print('  Platform Coverage:          {:>12,}'.format(tot_plat_pub))
print('  Coverage:                   {:>12.1f}%'.format((tot_plat_pub / tot_epi_pub * 100) if tot_epi_pub > 0 else 0))
print('  Gap:                        {:>12,}'.format(tot_plat_pub - tot_epi_pub))

print('\nNOTES:')
print('  - Private sector uses adjustment factors based on match type (35-55% of raw)')
print('  - Public sector uses OLMS state/local filings + FLRA actual federal worker counts')
print('  - OLMS federal members excluded (HQ-based, not worker location)')
print('  - Quality flags: OVERCOUNTED = platform > EPI, UNDERCOUNTED = platform < EPI')

# Save to CSV
with open(r'C:\Users\jakew\Downloads\platform_vs_epi_RECONCILED.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'EPI_Private', 'Platform_Private_Reconciled', 'Private_Coverage_Pct',
                     'EPI_Public', 'Platform_Public', 'Public_Quality_Flag'])
    for r in results:
        writer.writerow([r['state'], r['epi_private'], r['plat_private'], round(r['priv_coverage'], 1),
                        r['epi_public'], r['plat_public'], r['quality']])
    writer.writerow([])
    writer.writerow(['TOTALS', tot_epi_priv, tot_plat_priv, round(tot_priv_cov, 1),
                    tot_epi_pub, tot_plat_pub, ''])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\platform_vs_epi_RECONCILED.csv')

cur.close()
conn.close()
