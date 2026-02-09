import os
"""
Hybrid approach: Industry-weighted for 10 industries, state rate for edu/health.

Formula:
  Private_Density = (10_Industry_Frac × Industry_Expected × Climate_Mult) +
                    (EduHealth_Frac × State_Private_Rate)

- 10 industries: Apply BLS rates + state climate multiplier
- Edu/Health: Use state CPS rate directly (already reflects state climate)
"""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# BLS rates for 10 private industries (excluding edu/health)
BLS_RATES = {
    'agriculture_mining_share': 4.0,
    'construction_share': 10.3,
    'manufacturing_share': 7.8,
    'wholesale_share': 4.6,
    'retail_share': 4.0,
    'transportation_utilities_share': 16.2,
    'information_share': 6.6,
    'finance_share': 1.3,
    'professional_services_share': 2.0,
    'leisure_hospitality_share': 3.0,
    'other_services_share': 2.7,
}

# Get state CPS private rates
cur.execute('SELECT state, private_density_pct FROM v_state_density_latest')
state_private_rate = {row[0]: float(row[1]) for row in cur.fetchall()}

# Get state climate multipliers
cur.execute('SELECT state, climate_multiplier FROM state_industry_density_comparison')
state_multipliers = {row[0]: float(row[1]) for row in cur.fetchall()}

# Get all county data
cur.execute('''
    SELECT i.fips, i.state, i.county_name,
           i.agriculture_mining_share, i.construction_share, i.manufacturing_share,
           i.wholesale_share, i.retail_share, i.transportation_utilities_share,
           i.information_share, i.finance_share, i.professional_services_share,
           i.education_health_share, i.leisure_hospitality_share, i.other_services_share,
           i.public_admin_share,
           COALESCE(e.industry_adjusted_private, 0)
    FROM county_industry_shares i
    LEFT JOIN county_union_density_estimates e ON i.fips = e.fips
    ORDER BY i.state, i.county_name
''')

results = []
for row in cur.fetchall():
    fips, state, county = row[0], row[1], row[2]
    shares = {
        'agriculture_mining_share': float(row[3] or 0),
        'construction_share': float(row[4] or 0),
        'manufacturing_share': float(row[5] or 0),
        'wholesale_share': float(row[6] or 0),
        'retail_share': float(row[7] or 0),
        'transportation_utilities_share': float(row[8] or 0),
        'information_share': float(row[9] or 0),
        'finance_share': float(row[10] or 0),
        'professional_services_share': float(row[11] or 0),
        'education_health_share': float(row[12] or 0),
        'leisure_hospitality_share': float(row[13] or 0),
        'other_services_share': float(row[14] or 0),
    }
    current_adjusted = float(row[16] or 0)  # index 16, not 15

    state_rate = state_private_rate.get(state, 5.9)
    climate_mult = state_multipliers.get(state, 1.0)
    edu_health_share = shares['education_health_share']

    # Calculate share of private workforce in 10 industries vs edu/health
    ten_industry_shares = {k: v for k, v in shares.items() if k in BLS_RATES}
    total_ten = sum(ten_industry_shares.values())
    total_private = total_ten + edu_health_share

    if total_private > 0:
        ten_frac = total_ten / total_private
        edu_frac = edu_health_share / total_private

        # Industry-weighted expected for 10 industries
        if total_ten > 0:
            ten_expected = sum((s / total_ten) * BLS_RATES[k] for k, s in ten_industry_shares.items())
        else:
            ten_expected = 5.9

        # Hybrid formula
        hybrid = (ten_frac * ten_expected * climate_mult) + (edu_frac * state_rate)
    else:
        hybrid = state_rate

    results.append({
        'fips': fips,
        'state': state,
        'county': county,
        'edu_health_pct': edu_health_share * 100,
        'current': current_adjusted,
        'hybrid': round(hybrid, 2),
        'diff': round(hybrid - current_adjusted, 2)
    })

# Summary statistics
print('=' * 75)
print('HYBRID APPROACH: Industry-weighted for 10 industries, state rate for edu/health')
print('=' * 75)
print()

avg_current = sum(r['current'] for r in results) / len(results)
avg_hybrid = sum(r['hybrid'] for r in results) / len(results)
avg_edu = sum(r['edu_health_pct'] for r in results) / len(results)

print('NATIONAL AVERAGES (3,144 counties):')
print('  Avg Edu/Health Share:     %.1f%%' % avg_edu)
print('  Current Method (excl):    %.2f%%' % avg_current)
print('  Hybrid Method:            %.2f%%' % avg_hybrid)
print('  Difference:               %+.2f%%' % (avg_hybrid - avg_current))
print()

# Sample high edu/health counties
print('SAMPLE: High Edu/Health Counties (>30%):')
print()
print('County                        State  Edu/Health  Current  Hybrid   Diff')
print('-' * 75)

high_edu = sorted([r for r in results if r['edu_health_pct'] > 30],
                  key=lambda x: -x['edu_health_pct'])[:10]
for r in high_edu:
    print('%-30s %-5s  %5.1f%%    %6.2f%%  %6.2f%%  %+5.2f%%' % (
        r['county'][:30], r['state'], r['edu_health_pct'],
        r['current'], r['hybrid'], r['diff']
    ))

print()
print('SAMPLE: Low Edu/Health Counties (<15%):')
print()
print('County                        State  Edu/Health  Current  Hybrid   Diff')
print('-' * 75)

low_edu = sorted([r for r in results if r['edu_health_pct'] < 15],
                 key=lambda x: x['edu_health_pct'])[:10]
for r in low_edu:
    print('%-30s %-5s  %5.1f%%    %6.2f%%  %6.2f%%  %+5.2f%%' % (
        r['county'][:30], r['state'], r['edu_health_pct'],
        r['current'], r['hybrid'], r['diff']
    ))

print()
print('FORMULA:')
print('  Hybrid = (10_Industry_Frac x Industry_Expected x Climate_Mult) +')
print('           (EduHealth_Frac x State_Private_Rate)')
print()
print('  Current method: All 10 industries weighted, edu/health excluded entirely')
print('  Hybrid method: 10 industries weighted, edu/health uses state CPS rate')

# Ask if user wants to apply this
print()
print('=' * 75)
print('This change would shift density estimates based on edu/health concentration.')
print('High edu/health areas would move toward state average.')
print('=' * 75)

conn.close()
