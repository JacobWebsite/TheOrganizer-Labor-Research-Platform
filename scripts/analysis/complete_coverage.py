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

print('=' * 160)
print('COMPLETE PLATFORM COVERAGE vs EPI 2024 - ALL SECTORS BY STATE')
print('=' * 160)

# EPI data
epi_data = {
    'AK': {'private': 20385, 'public': 32000}, 'AL': {'private': 78538, 'public': 61000},
    'AR': {'private': 26025, 'public': 19000}, 'AZ': {'private': 65763, 'public': 52000},
    'CA': {'private': 1091677, 'public': 1283000}, 'CO': {'private': 104024, 'public': 103000},
    'CT': {'private': 113037, 'public': 156000}, 'DC': {'private': 17283, 'public': 21000},
    'DE': {'private': 12342, 'public': 25000}, 'FL': {'private': 215919, 'public': 246000},
    'GA': {'private': 88818, 'public': 86000}, 'HI': {'private': 63592, 'public': 84000},
    'IA': {'private': 51552, 'public': 41000}, 'ID': {'private': 21445, 'public': 21000},
    'IL': {'private': 382476, 'public': 352000}, 'IN': {'private': 188006, 'public': 82000},
    'KS': {'private': 43261, 'public': 40000}, 'KY': {'private': 117846, 'public': 38000},
    'LA': {'private': 34103, 'public': 34000}, 'MA': {'private': 228375, 'public': 266000},
    'MD': {'private': 110514, 'public': 214000}, 'ME': {'private': 37730, 'public': 39000},
    'MI': {'private': 402477, 'public': 178000}, 'MN': {'private': 197917, 'public': 179000},
    'MO': {'private': 147865, 'public': 85000}, 'MS': {'private': 38530, 'public': 20000},
    'MT': {'private': 25863, 'public': 30000}, 'NC': {'private': 63643, 'public': 44000},
    'ND': {'private': 10265, 'public': 8000}, 'NE': {'private': 24504, 'public': 38000},
    'NH': {'private': 27381, 'public': 35000}, 'NJ': {'private': 352849, 'public': 327000},
    'NM': {'private': 25697, 'public': 37000}, 'NV': {'private': 106416, 'public': 59000},
    'NY': {'private': 781226, 'public': 925000}, 'OH': {'private': 351676, 'public': 270000},
    'OK': {'private': 34430, 'public': 57000}, 'OR': {'private': 151290, 'public': 142000},
    'PA': {'private': 344832, 'public': 322000}, 'RI': {'private': 36660, 'public': 36000},
    'SC': {'private': 26931, 'public': 34000}, 'SD': {'private': 4965, 'public': 7000},
    'TN': {'private': 78333, 'public': 57000}, 'TX': {'private': 308806, 'public': 293000},
    'UT': {'private': 26912, 'public': 31000}, 'VA': {'private': 84702, 'public': 123000},
    'VT': {'private': 19683, 'public': 23000}, 'WA': {'private': 285629, 'public': 262000},
    'WI': {'private': 118440, 'public': 62000}, 'WV': {'private': 30972, 'public': 30000},
    'WY': {'private': 7136, 'public': 7000}
}

# Get private sector reconciled
cur.execute('''
    WITH private_only AS (
        SELECT state, SUM(
            CASE
                WHEN affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'AFT') THEN 0
                WHEN match_type = 'NAME_INFERRED' THEN ROUND(f7_reported_workers * 0.15)
                WHEN match_type = 'UNMATCHED' THEN ROUND(f7_reported_workers * 0.35)
                ELSE estimated_actual_workers
            END) as reconciled
        FROM v_f7_employers_fully_adjusted
        WHERE state IS NOT NULL AND LENGTH(state) = 2
        GROUP BY state
    )
    SELECT state, reconciled FROM private_only
''')
private_data = {row[0]: int(row[1] or 0) for row in cur.fetchall()}

# Get public sector
cur.execute('''
    SELECT state, olms_state_local_members, flra_federal_workers
    FROM public_sector_benchmarks WHERE state IS NOT NULL
''')
public_data = {row[0]: int(row[1] or 0) + int(row[2] or 0) for row in cur.fetchall()}

# Build report
print('\n{:<5} {:>10} {:>10} {:>10} | {:>10} {:>10} {:>10} | {:>10} {:>10} {:>10}'.format(
    'St', 'EPI_Priv', 'Plat_Prv', 'Prv_Cov', 'EPI_Pub', 'Plat_Pub', 'Pub_Cov', 'EPI_Tot', 'Plat_Tot', 'Tot_Cov'))
print('-' * 120)

results = []
for state in sorted(epi_data.keys()):
    epi = epi_data[state]
    epi_tot = epi['private'] + epi['public']
    
    plat_priv = private_data.get(state, 0)
    plat_pub = public_data.get(state, 0)
    plat_tot = plat_priv + plat_pub
    
    priv_cov = (plat_priv / epi['private'] * 100) if epi['private'] > 0 else 0
    pub_cov = (plat_pub / epi['public'] * 100) if epi['public'] > 0 else 0
    tot_cov = (plat_tot / epi_tot * 100) if epi_tot > 0 else 0
    
    results.append({
        'state': state,
        'epi_private': epi['private'], 'epi_public': epi['public'], 'epi_total': epi_tot,
        'plat_private': plat_priv, 'plat_public': plat_pub, 'plat_total': plat_tot,
        'priv_cov': priv_cov, 'pub_cov': pub_cov, 'tot_cov': tot_cov
    })
    
    print('{:<5} {:>10,} {:>10,} {:>9.0f}% | {:>10,} {:>10,} {:>9.0f}% | {:>10,} {:>10,} {:>9.0f}%'.format(
        state, epi['private'], plat_priv, priv_cov,
        epi['public'], plat_pub, pub_cov,
        epi_tot, plat_tot, tot_cov))

# Totals
tot_epi_priv = sum(r['epi_private'] for r in results)
tot_epi_pub = sum(r['epi_public'] for r in results)
tot_epi = tot_epi_priv + tot_epi_pub
tot_plat_priv = sum(r['plat_private'] for r in results)
tot_plat_pub = sum(r['plat_public'] for r in results)
tot_plat = tot_plat_priv + tot_plat_pub

print('-' * 120)
print('{:<5} {:>10,} {:>10,} {:>9.0f}% | {:>10,} {:>10,} {:>9.0f}% | {:>10,} {:>10,} {:>9.0f}%'.format(
    'TOT', tot_epi_priv, tot_plat_priv, (tot_plat_priv/tot_epi_priv*100),
    tot_epi_pub, tot_plat_pub, (tot_plat_pub/tot_epi_pub*100),
    tot_epi, tot_plat, (tot_plat/tot_epi*100)))

# Excluding DC
nodc = [r for r in results if r['state'] != 'DC']
tot_epi_priv_nodc = sum(r['epi_private'] for r in nodc)
tot_epi_pub_nodc = sum(r['epi_public'] for r in nodc)
tot_plat_priv_nodc = sum(r['plat_private'] for r in nodc)
tot_plat_pub_nodc = sum(r['plat_public'] for r in nodc)

print('\n' + '=' * 100)
print('SUMMARY (Excluding DC)')
print('=' * 100)
print('\n{:<25} {:>15} {:>15} {:>12}'.format('Sector', 'EPI Benchmark', 'Platform', 'Coverage'))
print('-' * 70)
print('{:<25} {:>15,} {:>15,} {:>11.1f}%'.format('Private Sector', tot_epi_priv_nodc, tot_plat_priv_nodc, tot_plat_priv_nodc/tot_epi_priv_nodc*100))
print('{:<25} {:>15,} {:>15,} {:>11.1f}%'.format('Public Sector', tot_epi_pub_nodc, tot_plat_pub_nodc, tot_plat_pub_nodc/tot_epi_pub_nodc*100))
print('-' * 70)
print('{:<25} {:>15,} {:>15,} {:>11.1f}%'.format('TOTAL', tot_epi_priv_nodc + tot_epi_pub_nodc, 
      tot_plat_priv_nodc + tot_plat_pub_nodc, (tot_plat_priv_nodc + tot_plat_pub_nodc)/(tot_epi_priv_nodc + tot_epi_pub_nodc)*100))

# Save
with open(r'C:\Users\jakew\Downloads\COMPLETE_COVERAGE_BY_STATE.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'EPI_Private', 'Platform_Private', 'Private_Coverage_Pct',
                     'EPI_Public', 'Platform_Public', 'Public_Coverage_Pct',
                     'EPI_Total', 'Platform_Total', 'Total_Coverage_Pct'])
    for r in results:
        writer.writerow([r['state'], r['epi_private'], r['plat_private'], round(r['priv_cov'], 1),
                        r['epi_public'], r['plat_public'], round(r['pub_cov'], 1),
                        r['epi_total'], r['plat_total'], round(r['tot_cov'], 1)])
    writer.writerow([])
    writer.writerow(['TOTAL', tot_epi_priv, tot_plat_priv, round(tot_plat_priv/tot_epi_priv*100, 1),
                    tot_epi_pub, tot_plat_pub, round(tot_plat_pub/tot_epi_pub*100, 1),
                    tot_epi, tot_plat, round(tot_plat/tot_epi*100, 1)])
    writer.writerow(['TOTAL_EXCL_DC', tot_epi_priv_nodc, tot_plat_priv_nodc, round(tot_plat_priv_nodc/tot_epi_priv_nodc*100, 1),
                    tot_epi_pub_nodc, tot_plat_pub_nodc, round(tot_plat_pub_nodc/tot_epi_pub_nodc*100, 1),
                    tot_epi_priv_nodc + tot_epi_pub_nodc, tot_plat_priv_nodc + tot_plat_pub_nodc, 
                    round((tot_plat_priv_nodc + tot_plat_pub_nodc)/(tot_epi_priv_nodc + tot_epi_pub_nodc)*100, 1)])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\COMPLETE_COVERAGE_BY_STATE.csv')

cur.close()
conn.close()
