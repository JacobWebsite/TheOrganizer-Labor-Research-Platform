import os
"""Calculate population-weighted national union density by sector."""

import psycopg2

populations = {
    'CA': 39431263, 'TX': 31290831, 'FL': 23372215, 'NY': 19867248, 'PA': 13078751,
    'IL': 12710158, 'OH': 11883304, 'GA': 11180878, 'NC': 11046024, 'MI': 10140459,
    'NJ': 9500851, 'VA': 8811195, 'WA': 7958180, 'AZ': 7582384, 'TN': 7227750,
    'MA': 7136171, 'IN': 6924275, 'MD': 6263220, 'MO': 6245466, 'WI': 5960975,
    'CO': 5957493, 'MN': 5793151, 'SC': 5478831, 'AL': 5157699, 'LA': 4597740,
    'KY': 4588372, 'OR': 4272371, 'OK': 4095393, 'CT': 3675069, 'UT': 3503613,
    'NV': 3267467, 'IA': 3241488, 'AR': 3088354, 'KS': 2970606, 'MS': 2943045,
    'NM': 2130256, 'NE': 2005465, 'ID': 2001619, 'WV': 1769979, 'HI': 1446146,
    'NH': 1409032, 'ME': 1405012, 'MT': 1137233, 'RI': 1112308, 'DE': 1051917,
    'SD': 924669, 'ND': 796568, 'AK': 740133, 'DC': 702250, 'VT': 648493,
    'WY': 587618
}

total_pop = sum(populations.values())

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

# Get state density and climate data
cur.execute('''
    SELECT v.state, v.private_density_pct, v.public_density_pct,
           s.climate_multiplier, s.interpretation
    FROM v_state_density_latest v
    LEFT JOIN state_industry_density_comparison s ON v.state = s.state
''')

state_data = {}
for row in cur.fetchall():
    state_data[row[0]] = {
        'private': float(row[1]) if row[1] else None,
        'public': float(row[2]) if row[2] else None,
        'multiplier': float(row[3]) if row[3] else 1.0,
        'climate': row[4] or 'UNKNOWN'
    }

# Group by climate
climate_groups = {'STRONG': [], 'ABOVE_AVERAGE': [], 'BELOW_AVERAGE': [], 'WEAK': []}
for state, pop in populations.items():
    data = state_data.get(state, {})
    climate = data.get('climate', 'UNKNOWN')
    if climate in climate_groups:
        climate_groups[climate].append((state, pop, data))

print('=' * 60)
print('EXPECTED US UNION DENSITY BY SECTOR')
print('=' * 60)
print()
print('Total US Population:', format(total_pop, ','))
print()

# Calculate weighted averages
priv_sum, priv_pop = 0, 0
pub_sum, pub_pop = 0, 0

for state, pop in populations.items():
    data = state_data.get(state, {})
    if data.get('private'):
        priv_sum += pop * data['private']
        priv_pop += pop
    if data.get('public'):
        pub_sum += pop * data['public']
        pub_pop += pop

priv_avg = priv_sum / priv_pop
pub_avg = pub_sum / pub_pop

print('POPULATION-WEIGHTED SECTOR DENSITY:')
print('  Private Sector:  %.2f%%' % priv_avg)
print('  Public Sector:   %.2f%%' % pub_avg)
print()

# Calculate total using workforce shares
cur.execute('SELECT AVG(private_share), AVG(public_share) FROM state_workforce_shares')
row = cur.fetchone()
priv_share = float(row[0])
pub_share = float(row[1])

total = (priv_share * priv_avg) + (pub_share * pub_avg)
print('WORKFORCE COMPOSITION (national avg):')
print('  Private sector workers: %.1f%%' % (priv_share*100))
print('  Public sector workers:  %.1f%%' % (pub_share*100))
print()
print('ESTIMATED TOTAL US DENSITY: %.2f%%' % total)
print('BLS 2024 Reported:          10.0%%')
print('Difference:                 %+.2f%%' % (total - 10.0))
print()

# Breakdown by climate
print('=' * 60)
print('BREAKDOWN BY STATE UNION CLIMATE')
print('=' * 60)
print()

for climate in ['STRONG', 'ABOVE_AVERAGE', 'BELOW_AVERAGE', 'WEAK']:
    states = climate_groups[climate]
    pop_total = sum(s[1] for s in states)
    pop_pct = pop_total / total_pop * 100

    priv_weighted = sum(s[1] * s[2].get('private', 0) for s in states if s[2].get('private'))
    priv_pop_c = sum(s[1] for s in states if s[2].get('private'))
    priv_avg_c = priv_weighted / priv_pop_c if priv_pop_c > 0 else 0

    pub_weighted = sum(s[1] * s[2].get('public', 0) for s in states if s[2].get('public'))
    pub_pop_c = sum(s[1] for s in states if s[2].get('public'))
    pub_avg_c = pub_weighted / pub_pop_c if pub_pop_c > 0 else 0

    state_list = ', '.join(sorted([s[0] for s in states]))

    print('%s (%d states, %.1f%% of US pop):' % (climate, len(states), pop_pct))
    print('  Private: %.2f%%  |  Public: %.2f%%' % (priv_avg_c, pub_avg_c))
    print('  States:', state_list)
    print()

conn.close()
