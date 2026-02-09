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
print('FINAL COVERAGE REPORT: PLATFORM vs EPI 2024 BY STATE')
print('Using 6.25M Private Sector Reconciliation Methodology')
print('=' * 140)

# Get private sector with FULL exclusion logic matching the 6.25M view
cur.execute('''
    WITH exclusion_flags AS (
        SELECT 
            v.employer_id,
            v.employer_name,
            v.state,
            v.affiliation,
            v.match_type,
            v.f7_reported_workers,
            v.estimated_actual_workers,
            e.latest_union_name,
            CASE WHEN v.affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'AFT') THEN true ELSE false END AS is_excluded_affiliation,
            CASE WHEN e.latest_union_name ILIKE ANY(ARRAY['%Government Employees%', '%Treasury Employees%', '%Teachers%']) THEN true ELSE false END AS is_excluded_union,
            CASE WHEN v.employer_name ILIKE ANY(ARRAY['%state of%', '%city of%', '%county of%', '%department of%', '%HUD/%', 'local %', '% local %', '%signator%', '%brotherhood%']) THEN true ELSE false END AS is_excluded_employer
        FROM v_f7_employers_fully_adjusted v
        JOIN f7_employers e ON v.employer_id = e.employer_id
    ),
    private_only AS (
        SELECT * FROM exclusion_flags
        WHERE NOT is_excluded_affiliation AND NOT is_excluded_union AND NOT is_excluded_employer
    ),
    reconciled AS (
        SELECT 
            state,
            employer_name,
            affiliation,
            match_type,
            MAX(f7_reported_workers) as max_raw,
            CASE
                WHEN match_type = 'NAME_INFERRED' THEN ROUND(MAX(f7_reported_workers) * 0.15)
                WHEN match_type = 'UNMATCHED' THEN ROUND(MAX(f7_reported_workers) * 0.35)
                ELSE MAX(estimated_actual_workers)
            END as reconciled_workers
        FROM private_only
        GROUP BY state, employer_name, affiliation, match_type
    )
    SELECT 
        state,
        COUNT(DISTINCT employer_name) as employers,
        SUM(max_raw) as raw_workers,
        SUM(reconciled_workers) as reconciled_workers
    FROM reconciled
    WHERE state IS NOT NULL AND LENGTH(state) = 2
    GROUP BY state
    ORDER BY SUM(reconciled_workers) DESC
''')

private_by_state = {}
total_raw = 0
total_reconciled = 0

for row in cur.fetchall():
    state, emp, raw, recon = row
    raw = int(raw or 0)
    recon = int(recon or 0)
    private_by_state[state] = {'employers': emp, 'raw': raw, 'reconciled': recon}
    total_raw += raw
    total_reconciled += recon

print('\n=== PRIVATE SECTOR (Reconciled ~6.25M methodology) ===')
print('Total Raw Workers: {:,}'.format(total_raw))
print('Total Reconciled: {:,}'.format(total_reconciled))

# Get public sector by state
cur.execute('''
    SELECT state, olms_state_local_members, flra_federal_workers
    FROM public_sector_benchmarks WHERE state IS NOT NULL
''')
public_by_state = {}
for row in cur.fetchall():
    state = row[0]
    olms_sl = int(row[1] or 0)
    flra = int(row[2] or 0)
    public_by_state[state] = {'olms_state_local': olms_sl, 'flra_federal': flra, 'total': olms_sl + flra}

# EPI 2024 benchmarks
epi = {
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

# Build comparison
print('\n' + '=' * 160)
print('{:<5} | {:>12} {:>12} {:>8} | {:>12} {:>12} {:>8} | {:>12} {:>12} {:>8}'.format(
    'St', 'EPI_Priv', 'Plat_Priv', 'Cov%', 'EPI_Pub', 'Plat_Pub', 'Cov%', 'EPI_Tot', 'Plat_Tot', 'Cov%'))
print('-' * 160)

results = []
for state in sorted(epi.keys()):
    e = epi[state]
    priv = private_by_state.get(state, {}).get('reconciled', 0)
    pub = public_by_state.get(state, {}).get('total', 0)
    
    epi_tot = e['private'] + e['public']
    plat_tot = priv + pub
    
    priv_cov = (priv / e['private'] * 100) if e['private'] > 0 else 0
    pub_cov = (pub / e['public'] * 100) if e['public'] > 0 else 0
    tot_cov = (plat_tot / epi_tot * 100) if epi_tot > 0 else 0
    
    results.append({
        'state': state,
        'epi_private': e['private'], 'plat_private': priv, 'priv_cov': priv_cov,
        'epi_public': e['public'], 'plat_public': pub, 'pub_cov': pub_cov,
        'epi_total': epi_tot, 'plat_total': plat_tot, 'tot_cov': tot_cov
    })
    
    print('{:<5} | {:>12,} {:>12,} {:>7.0f}% | {:>12,} {:>12,} {:>7.0f}% | {:>12,} {:>12,} {:>7.0f}%'.format(
        state, e['private'], priv, priv_cov, e['public'], pub, pub_cov, epi_tot, plat_tot, tot_cov))

# Totals
t_epi_priv = sum(r['epi_private'] for r in results)
t_epi_pub = sum(r['epi_public'] for r in results)
t_plat_priv = sum(r['plat_private'] for r in results)
t_plat_pub = sum(r['plat_public'] for r in results)

print('-' * 160)
print('{:<5} | {:>12,} {:>12,} {:>7.0f}% | {:>12,} {:>12,} {:>7.0f}% | {:>12,} {:>12,} {:>7.0f}%'.format(
    'TOT', t_epi_priv, t_plat_priv, t_plat_priv/t_epi_priv*100,
    t_epi_pub, t_plat_pub, t_plat_pub/t_epi_pub*100,
    t_epi_priv + t_epi_pub, t_plat_priv + t_plat_pub, (t_plat_priv + t_plat_pub)/(t_epi_priv + t_epi_pub)*100))

# Excluding DC
nodc = [r for r in results if r['state'] != 'DC']
t_epi_priv_nodc = sum(r['epi_private'] for r in nodc)
t_epi_pub_nodc = sum(r['epi_public'] for r in nodc)
t_plat_priv_nodc = sum(r['plat_private'] for r in nodc)
t_plat_pub_nodc = sum(r['plat_public'] for r in nodc)

print('\n' + '=' * 100)
print('FINAL SUMMARY (Excluding DC - distorted by national HQs)')
print('=' * 100)
print('\n{:<25} {:>15} {:>15} {:>12}'.format('Sector', 'EPI 2024', 'Platform', 'Coverage'))
print('-' * 70)
print('{:<25} {:>15,} {:>15,} {:>11.1f}%'.format('Private Sector', t_epi_priv_nodc, t_plat_priv_nodc, t_plat_priv_nodc/t_epi_priv_nodc*100))
print('{:<25} {:>15,} {:>15,} {:>11.1f}%'.format('Public Sector', t_epi_pub_nodc, t_plat_pub_nodc, t_plat_pub_nodc/t_epi_pub_nodc*100))
print('-' * 70)
print('{:<25} {:>15,} {:>15,} {:>11.1f}%'.format('TOTAL', t_epi_priv_nodc + t_epi_pub_nodc, 
      t_plat_priv_nodc + t_plat_pub_nodc, (t_plat_priv_nodc + t_plat_pub_nodc)/(t_epi_priv_nodc + t_epi_pub_nodc)*100))

# Save to CSV
with open(r'C:\Users\jakew\Downloads\FINAL_COVERAGE_BY_STATE.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'EPI_Private', 'Platform_Private', 'Private_Coverage_Pct',
                     'EPI_Public', 'Platform_Public', 'Public_Coverage_Pct',
                     'EPI_Total', 'Platform_Total', 'Total_Coverage_Pct'])
    for r in results:
        writer.writerow([r['state'], r['epi_private'], r['plat_private'], round(r['priv_cov'], 1),
                        r['epi_public'], r['plat_public'], round(r['pub_cov'], 1),
                        r['epi_total'], r['plat_total'], round(r['tot_cov'], 1)])
    writer.writerow([])
    writer.writerow(['TOTAL', t_epi_priv, t_plat_priv, round(t_plat_priv/t_epi_priv*100, 1),
                    t_epi_pub, t_plat_pub, round(t_plat_pub/t_epi_pub*100, 1),
                    t_epi_priv + t_epi_pub, t_plat_priv + t_plat_pub, 
                    round((t_plat_priv + t_plat_pub)/(t_epi_priv + t_epi_pub)*100, 1)])
    writer.writerow(['TOTAL_EXCL_DC', t_epi_priv_nodc, t_plat_priv_nodc, round(t_plat_priv_nodc/t_epi_priv_nodc*100, 1),
                    t_epi_pub_nodc, t_plat_pub_nodc, round(t_plat_pub_nodc/t_epi_pub_nodc*100, 1),
                    t_epi_priv_nodc + t_epi_pub_nodc, t_plat_priv_nodc + t_plat_pub_nodc, 
                    round((t_plat_priv_nodc + t_plat_pub_nodc)/(t_epi_priv_nodc + t_epi_pub_nodc)*100, 1)])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\FINAL_COVERAGE_BY_STATE.csv')

cur.close()
conn.close()
