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
print('REFINED PLATFORM COVERAGE - EXCLUDING PUBLIC SECTOR UNIONS FROM PRIVATE F-7 DATA')
print('=' * 140)

# Get private sector WITH exclusions for public sector unions (matching the 6.25M logic)
cur.execute('''
    WITH private_only AS (
        SELECT 
            state,
            employer_id,
            f7_reported_workers,
            affiliation,
            match_type,
            estimated_actual_workers,
            CASE
                -- Exclude known public sector affiliations
                WHEN affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'AFT', 'AFSCME', 'NEA', 'SEIU') 
                     AND affiliation NOT IN ('SEIU')  -- SEIU has both private and public
                THEN 0
                -- Apply adjustment factors
                WHEN match_type = 'NAME_INFERRED' THEN ROUND(f7_reported_workers * 0.15)
                WHEN match_type = 'UNMATCHED' THEN ROUND(f7_reported_workers * 0.35)
                ELSE estimated_actual_workers
            END as reconciled_workers
        FROM v_f7_employers_fully_adjusted
        WHERE state IS NOT NULL AND LENGTH(state) = 2
    )
    SELECT 
        state,
        COUNT(*) as employers,
        SUM(f7_reported_workers) as raw_workers,
        SUM(reconciled_workers) as reconciled_workers
    FROM private_only
    GROUP BY state
    ORDER BY SUM(reconciled_workers) DESC
''')

results = cur.fetchall()

print('\n{:<6} {:>12} {:>15} {:>18}'.format('State', 'Employers', 'Raw_Workers', 'Reconciled'))
print('-' * 55)

state_private = {}
total_raw = 0
total_recon = 0

for row in results:
    state, emp, raw, recon = row
    raw = int(raw or 0)
    recon = int(recon or 0)
    state_private[state] = {'employers': emp, 'raw': raw, 'reconciled': recon}
    total_raw += raw
    total_recon += recon
    print('{:<6} {:>12,} {:>15,} {:>18,}'.format(state, emp, raw, recon))

print('-' * 55)
print('{:<6} {:>12,} {:>15,} {:>18,}'.format('TOTAL', sum(d['employers'] for d in state_private.values()), total_raw, total_recon))

# Now compare to EPI
print('\n\n' + '=' * 140)
print('COMPARISON: PLATFORM PRIVATE (RECONCILED) vs EPI PRIVATE')
print('=' * 140)

epi_private = {
    'AK': 20385, 'AL': 78538, 'AR': 26025, 'AZ': 65763, 'CA': 1091677,
    'CO': 104024, 'CT': 113037, 'DC': 17283, 'DE': 12342, 'FL': 215919,
    'GA': 88818, 'HI': 63592, 'IA': 51552, 'ID': 21445, 'IL': 382476,
    'IN': 188006, 'KS': 43261, 'KY': 117846, 'LA': 34103, 'MA': 228375,
    'MD': 110514, 'ME': 37730, 'MI': 402477, 'MN': 197917, 'MO': 147865,
    'MS': 38530, 'MT': 25863, 'NC': 63643, 'ND': 10265, 'NE': 24504,
    'NH': 27381, 'NJ': 352849, 'NM': 25697, 'NV': 106416, 'NY': 781226,
    'OH': 351676, 'OK': 34430, 'OR': 151290, 'PA': 344832, 'RI': 36660,
    'SC': 26931, 'SD': 4965, 'TN': 78333, 'TX': 308806, 'UT': 26912,
    'VA': 84702, 'VT': 19683, 'WA': 285629, 'WI': 118440, 'WV': 30972,
    'WY': 7136
}

print('\n{:<6} {:>12} {:>15} {:>12} {:>10}'.format('State', 'EPI_Private', 'Plat_Private', 'Gap', 'Coverage'))
print('-' * 60)

comparison = []
tot_epi = 0
tot_plat = 0

for state in sorted(epi_private.keys()):
    epi = epi_private[state]
    plat = state_private.get(state, {}).get('reconciled', 0)
    gap = plat - epi
    cov = (plat / epi * 100) if epi > 0 else 0
    
    tot_epi += epi
    tot_plat += plat
    comparison.append({'state': state, 'epi': epi, 'platform': plat, 'coverage': cov})
    
    print('{:<6} {:>12,} {:>15,} {:>12,} {:>9.1f}%'.format(state, epi, plat, gap, cov))

print('-' * 60)
tot_cov = (tot_plat / tot_epi * 100) if tot_epi > 0 else 0
print('{:<6} {:>12,} {:>15,} {:>12,} {:>9.1f}%'.format('TOTAL', tot_epi, tot_plat, tot_plat - tot_epi, tot_cov))

# Excluding DC
print('\n--- Excluding DC (national HQ effects) ---')
tot_epi_nodc = tot_epi - epi_private['DC']
tot_plat_nodc = tot_plat - state_private.get('DC', {}).get('reconciled', 0)
tot_cov_nodc = (tot_plat_nodc / tot_epi_nodc * 100) if tot_epi_nodc > 0 else 0
print('EPI (excl DC):      {:>12,}'.format(tot_epi_nodc))
print('Platform (excl DC): {:>12,}'.format(tot_plat_nodc))
print('Coverage:           {:>12.1f}%'.format(tot_cov_nodc))

# Save
with open(r'C:\Users\jakew\Downloads\private_sector_by_state_REFINED.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['State', 'EPI_Private', 'Platform_Reconciled', 'Gap', 'Coverage_Pct'])
    for c in comparison:
        writer.writerow([c['state'], c['epi'], c['platform'], c['platform'] - c['epi'], round(c['coverage'], 1)])
    writer.writerow([])
    writer.writerow(['TOTAL', tot_epi, tot_plat, tot_plat - tot_epi, round(tot_cov, 1)])
    writer.writerow(['TOTAL_EXCL_DC', tot_epi_nodc, tot_plat_nodc, tot_plat_nodc - tot_epi_nodc, round(tot_cov_nodc, 1)])

print('\nSaved to: C:\\Users\\jakew\\Downloads\\private_sector_by_state_REFINED.csv')

cur.close()
conn.close()
