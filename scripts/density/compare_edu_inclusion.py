import os
"""Compare national density estimates with vs without education/health."""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# BLS rates - WITH education/health included
BLS_RATES_WITH_EDU = {
    'agriculture_mining_share': 4.0,
    'construction_share': 10.3,
    'manufacturing_share': 7.8,
    'wholesale_share': 4.6,
    'retail_share': 4.0,
    'transportation_utilities_share': 16.2,
    'information_share': 6.6,
    'finance_share': 1.3,
    'professional_services_share': 2.0,
    'education_health_share': 8.1,  # INCLUDED
    'leisure_hospitality_share': 3.0,
    'other_services_share': 2.7,
}

# BLS rates - WITHOUT education/health (current)
BLS_RATES_NO_EDU = {
    'agriculture_mining_share': 4.0,
    'construction_share': 10.3,
    'manufacturing_share': 7.8,
    'wholesale_share': 4.6,
    'retail_share': 4.0,
    'transportation_utilities_share': 16.2,
    'information_share': 6.6,
    'finance_share': 1.3,
    'professional_services_share': 2.0,
    # education_health excluded
    'leisure_hospitality_share': 3.0,
    'other_services_share': 2.7,
}

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

# Get actual CPS density
cur.execute('SELECT state, private_density_pct, public_density_pct FROM v_state_density_latest')
actual_density = {row[0]: {'private': float(row[1]), 'public': float(row[2])} for row in cur.fetchall()}

# Get state industry shares
cur.execute('''
    SELECT state,
           agriculture_mining_share, construction_share, manufacturing_share,
           wholesale_share, retail_share, transportation_utilities_share,
           information_share, finance_share, professional_services_share,
           education_health_share, leisure_hospitality_share, other_services_share
    FROM state_industry_shares
''')

state_industry = {}
for row in cur.fetchall():
    state_industry[row[0]] = {
        'agriculture_mining_share': float(row[1] or 0),
        'construction_share': float(row[2] or 0),
        'manufacturing_share': float(row[3] or 0),
        'wholesale_share': float(row[4] or 0),
        'retail_share': float(row[5] or 0),
        'transportation_utilities_share': float(row[6] or 0),
        'information_share': float(row[7] or 0),
        'finance_share': float(row[8] or 0),
        'professional_services_share': float(row[9] or 0),
        'education_health_share': float(row[10] or 0),
        'leisure_hospitality_share': float(row[11] or 0),
        'other_services_share': float(row[12] or 0),
    }

def calc_expected(shares, bls_rates):
    total = sum(shares.get(k, 0) for k in bls_rates.keys())
    if total == 0:
        return 5.9
    expected = sum((shares.get(k, 0) / total) * rate for k, rate in bls_rates.items())
    return expected

def calc_multiplier(actual, expected):
    return actual / expected if expected > 0 else 1.0

print('=' * 70)
print('COMPARISON: WITH vs WITHOUT Education/Health in Private Sector')
print('=' * 70)
print()

# Calculate for each state
results_with = {}
results_without = {}

for state, pop in populations.items():
    shares = state_industry.get(state, {})
    actual = actual_density.get(state, {}).get('private', 5.9)

    exp_with = calc_expected(shares, BLS_RATES_WITH_EDU)
    exp_without = calc_expected(shares, BLS_RATES_NO_EDU)

    mult_with = calc_multiplier(actual, exp_with)
    mult_without = calc_multiplier(actual, exp_without)

    results_with[state] = {'expected': exp_with, 'multiplier': mult_with, 'actual': actual}
    results_without[state] = {'expected': exp_without, 'multiplier': mult_without, 'actual': actual}

# Population-weighted averages
def pop_weighted_avg(results, key):
    total = sum(populations[s] * results[s][key] for s in populations)
    return total / total_pop

avg_exp_with = pop_weighted_avg(results_with, 'expected')
avg_exp_without = pop_weighted_avg(results_without, 'expected')
avg_mult_with = pop_weighted_avg(results_with, 'multiplier')
avg_mult_without = pop_weighted_avg(results_without, 'multiplier')

print('POPULATION-WEIGHTED AVERAGES:')
print()
print('                          WITH Edu/Health    WITHOUT Edu/Health')
print('                          ---------------    ------------------')
print('Expected Private Density:     %.2f%%              %.2f%%' % (avg_exp_with, avg_exp_without))
print('Avg Climate Multiplier:       %.2fx               %.2fx' % (avg_mult_with, avg_mult_without))
print()

# Show top states comparison
print('TOP 5 STATES BY CLIMATE MULTIPLIER:')
print()
print('WITH Edu/Health:')
sorted_with = sorted(results_with.items(), key=lambda x: x[1]['multiplier'], reverse=True)[:5]
for state, data in sorted_with:
    print('  %s: expected=%.2f%%, actual=%.2f%%, multiplier=%.2fx' % (state, data['expected'], data['actual'], data['multiplier']))

print()
print('WITHOUT Edu/Health (current):')
sorted_without = sorted(results_without.items(), key=lambda x: x[1]['multiplier'], reverse=True)[:5]
for state, data in sorted_without:
    print('  %s: expected=%.2f%%, actual=%.2f%%, multiplier=%.2fx' % (state, data['expected'], data['actual'], data['multiplier']))

# Get workforce shares for total density calc
cur.execute('SELECT AVG(private_share), AVG(public_share) FROM state_workforce_shares')
row = cur.fetchone()
priv_share = float(row[0])
pub_share = float(row[1])

# Public sector density (unchanged)
pub_weighted = sum(populations[s] * actual_density[s]['public'] for s in populations if s in actual_density)
pub_avg = pub_weighted / total_pop

# Actual private (from CPS)
priv_actual = sum(populations[s] * actual_density[s]['private'] for s in populations if s in actual_density) / total_pop

print()
print('=' * 70)
print('NATIONAL DENSITY ESTIMATES')
print('=' * 70)
print()
print('ACTUAL (from CPS):')
print('  Private Sector:  %.2f%%' % priv_actual)
print('  Public Sector:   %.2f%%' % pub_avg)
print()
print('EXPECTED PRIVATE (industry-weighted):')
print('  With Edu/Health:    %.2f%%' % avg_exp_with)
print('  Without Edu/Health: %.2f%%' % avg_exp_without)
print('  Difference:         %.2f percentage points' % (avg_exp_with - avg_exp_without))
print()

# Total density calculation
total_with_edu = (priv_share * priv_actual) + (pub_share * pub_avg)
print('ESTIMATED TOTAL US DENSITY: %.2f%%' % total_with_edu)
print('BLS 2024 Reported:          10.0%%')
print()

print('KEY INSIGHT:')
print('  The BLS Education/Health density (8.1%%) includes BOTH private and')
print('  public sector workers. Many teachers, nurses, and hospital staff')
print('  are public employees already counted in public sector estimates.')
print()
print('  Including edu/health raises expected private density by ~%.1f%%,' % (avg_exp_with - avg_exp_without))
print('  which would LOWER climate multipliers (making strong union states')
print('  look less exceptional).')
print()
print('  Current approach (excluding edu/health) avoids potential double-counting')
print('  and better isolates truly private-sector industry effects.')

conn.close()
