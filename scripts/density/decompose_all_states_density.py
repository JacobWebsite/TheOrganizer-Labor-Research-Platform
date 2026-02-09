import os
"""
Decompose Public Sector Union Density by Government Level for All States

Methodology:
1. Use national federal/state/local density rates as baseline (2024)
2. Calculate uniform multiplier k for each state such that:
   Public_Density = k × (fed_share × nat_fed + state_share × nat_state + local_share × nat_local)
3. Estimate: Fed_State = k × Nat_Fed, State_State = k × Nat_State, Local_State = k × Nat_Local

This assumes each state has a uniform "union premium" across government levels.
"""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# National Government Densities (2024 BLS/unionstats)
NAT_FED_DENSITY = 25.3
NAT_STATE_DENSITY = 27.8
NAT_LOCAL_DENSITY = 38.2

print("=" * 100)
print("DECOMPOSING PUBLIC SECTOR UNION DENSITY BY GOVERNMENT LEVEL - ALL STATES")
print("=" * 100)
print(f"\nNational Baseline (2024): Federal {NAT_FED_DENSITY}%, State {NAT_STATE_DENSITY}%, Local {NAT_LOCAL_DENSITY}%")

# Get all state data
cur.execute("""
    SELECT
        d.state,
        d.state_name,
        d.public_density_pct,
        d.private_density_pct,
        d.total_density_pct,
        d.public_is_estimated,
        w.federal_gov_share,
        w.state_gov_share,
        w.local_gov_share,
        w.public_share,
        w.private_share
    FROM v_state_density_latest d
    JOIN state_workforce_shares w ON d.state = w.state
    ORDER BY d.public_density_pct DESC NULLS LAST
""")

results = cur.fetchall()

print(f"\n{'State':5} | {'Public':7} | {'Est':3} | {'k':5} | {'Federal':8} | {'State':8} | {'Local':8} | {'Validation':10}")
print(f"{'-'*5} | {'-'*7} | {'-'*3} | {'-'*5} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*10}")

decomposed_data = []

for row in results:
    state = row[0]
    state_name = row[1]
    public_density = row[2]
    private_density = row[3]
    total_density = row[4]
    is_estimated = row[5]
    fed_share = float(row[6]) if row[6] else 0
    state_share = float(row[7]) if row[7] else 0
    local_share = float(row[8]) if row[8] else 0
    public_share = float(row[9]) if row[9] else 0
    private_share = float(row[10]) if row[10] else 0

    if not public_density or public_share == 0:
        continue

    # Calculate shares within public sector
    fed_share_of_public = fed_share / public_share if public_share > 0 else 0
    state_share_of_public = state_share / public_share if public_share > 0 else 0
    local_share_of_public = local_share / public_share if public_share > 0 else 0

    # Calculate weighted national baseline for this state's composition
    weighted_national = (
        fed_share_of_public * NAT_FED_DENSITY +
        state_share_of_public * NAT_STATE_DENSITY +
        local_share_of_public * NAT_LOCAL_DENSITY
    )

    # Calculate multiplier k
    k = float(public_density) / weighted_national if weighted_national > 0 else 0

    # Estimate decomposed densities
    est_fed = k * NAT_FED_DENSITY
    est_state = k * NAT_STATE_DENSITY
    est_local = k * NAT_LOCAL_DENSITY

    # Validate by recalculating total
    calc_total = (
        private_share * float(private_density) +
        fed_share * est_fed +
        state_share * est_state +
        local_share * est_local
    ) * 100  # Convert to percentage

    est_marker = "*" if is_estimated else ""

    print(f"{state:5} | {float(public_density):6.1f}% | {est_marker:3} | {k:5.2f} | {est_fed:7.1f}% | {est_state:7.1f}% | {est_local:7.1f}% | {calc_total:6.1f}% calc")

    decomposed_data.append({
        'state': state,
        'state_name': state_name,
        'public_density': float(public_density),
        'public_is_estimated': is_estimated,
        'multiplier': k,
        'est_federal': est_fed,
        'est_state': est_state,
        'est_local': est_local,
        'fed_share_of_public': fed_share_of_public,
        'state_share_of_public': state_share_of_public,
        'local_share_of_public': local_share_of_public
    })

print(f"\n* = Public density was estimated (small CPS sample)")

# Summary statistics
print("\n" + "=" * 100)
print("SUMMARY STATISTICS")
print("=" * 100)

# Sort by each metric
by_federal = sorted(decomposed_data, key=lambda x: x['est_federal'], reverse=True)
by_state = sorted(decomposed_data, key=lambda x: x['est_state'], reverse=True)
by_local = sorted(decomposed_data, key=lambda x: x['est_local'], reverse=True)
by_multiplier = sorted(decomposed_data, key=lambda x: x['multiplier'], reverse=True)

print("\nTop 10 States by FEDERAL Government Density:")
print(f"  {'State':5} | {'Fed Density':12} | {'Multiplier':10}")
for d in by_federal[:10]:
    print(f"  {d['state']:5} | {d['est_federal']:11.1f}% | {d['multiplier']:10.2f}x")

print("\nTop 10 States by STATE Government Density:")
print(f"  {'State':5} | {'State Density':13} | {'Multiplier':10}")
for d in by_state[:10]:
    print(f"  {d['state']:5} | {d['est_state']:12.1f}% | {d['multiplier']:10.2f}x")

print("\nTop 10 States by LOCAL Government Density:")
print(f"  {'State':5} | {'Local Density':13} | {'Multiplier':10}")
for d in by_local[:10]:
    print(f"  {d['state']:5} | {d['est_local']:12.1f}% | {d['multiplier']:10.2f}x")

print("\nBottom 10 States by LOCAL Government Density:")
print(f"  {'State':5} | {'Local Density':13} | {'Multiplier':10}")
for d in by_local[-10:]:
    print(f"  {d['state']:5} | {d['est_local']:12.1f}% | {d['multiplier']:10.2f}x")

# Averages
avg_fed = sum(d['est_federal'] for d in decomposed_data) / len(decomposed_data)
avg_state = sum(d['est_state'] for d in decomposed_data) / len(decomposed_data)
avg_local = sum(d['est_local'] for d in decomposed_data) / len(decomposed_data)
avg_k = sum(d['multiplier'] for d in decomposed_data) / len(decomposed_data)

print(f"\nState Averages (unweighted):")
print(f"  Federal:    {avg_fed:.1f}%")
print(f"  State:      {avg_state:.1f}%")
print(f"  Local:      {avg_local:.1f}%")
print(f"  Multiplier: {avg_k:.2f}x")

# Create table for database storage
print("\n" + "=" * 100)
print("CREATING DATABASE TABLE")
print("=" * 100)

cur.execute("""
    DROP TABLE IF EXISTS state_govt_level_density CASCADE;

    CREATE TABLE state_govt_level_density (
        state VARCHAR(2) PRIMARY KEY,
        state_name VARCHAR(50),
        public_density_pct DECIMAL(5,2),
        public_is_estimated BOOLEAN,
        multiplier DECIMAL(5,3),
        est_federal_density DECIMAL(5,2),
        est_state_density DECIMAL(5,2),
        est_local_density DECIMAL(5,2),
        fed_share_of_public DECIMAL(6,4),
        state_share_of_public DECIMAL(6,4),
        local_share_of_public DECIMAL(6,4),
        methodology VARCHAR(100) DEFAULT 'uniform_multiplier_from_national',
        national_fed_baseline DECIMAL(5,2) DEFAULT 25.3,
        national_state_baseline DECIMAL(5,2) DEFAULT 27.8,
        national_local_baseline DECIMAL(5,2) DEFAULT 38.2,
        created_at TIMESTAMP DEFAULT NOW()
    );

    COMMENT ON TABLE state_govt_level_density IS
        'Estimated union density by government level (federal/state/local) using uniform multiplier method';
""")

for d in decomposed_data:
    cur.execute("""
        INSERT INTO state_govt_level_density
            (state, state_name, public_density_pct, public_is_estimated, multiplier,
             est_federal_density, est_state_density, est_local_density,
             fed_share_of_public, state_share_of_public, local_share_of_public)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        d['state'], d['state_name'], d['public_density'], d['public_is_estimated'],
        round(d['multiplier'], 3),
        round(d['est_federal'], 2), round(d['est_state'], 2), round(d['est_local'], 2),
        round(d['fed_share_of_public'], 4), round(d['state_share_of_public'], 4),
        round(d['local_share_of_public'], 4)
    ))

conn.commit()
print(f"\nInserted {len(decomposed_data)} state records into state_govt_level_density table")

# Create a view for easy access
cur.execute("""
    DROP VIEW IF EXISTS v_state_density_by_govt_level CASCADE;

    CREATE VIEW v_state_density_by_govt_level AS
    SELECT
        g.state,
        g.state_name,
        d.private_density_pct,
        g.public_density_pct,
        g.public_is_estimated as public_density_is_estimated,
        g.est_federal_density,
        g.est_state_density,
        g.est_local_density,
        g.multiplier as union_premium_vs_national,
        d.total_density_pct,
        w.federal_gov_share * 100 as federal_workforce_pct,
        w.state_gov_share * 100 as state_workforce_pct,
        w.local_gov_share * 100 as local_workforce_pct,
        w.public_share * 100 as public_workforce_pct
    FROM state_govt_level_density g
    JOIN v_state_density_latest d ON g.state = d.state
    JOIN state_workforce_shares w ON g.state = w.state
    ORDER BY g.public_density_pct DESC;

    COMMENT ON VIEW v_state_density_by_govt_level IS
        'Complete state density breakdown including estimated federal/state/local government densities';
""")
conn.commit()
print("Created view v_state_density_by_govt_level")

cur.close()
conn.close()

print("\n" + "=" * 100)
print("COMPLETE")
print("=" * 100)
