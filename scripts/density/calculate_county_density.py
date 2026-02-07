"""
Calculate County Union Density Estimates

Methodology:
  County_Density = (Private_Share × State_Private_Density) +
                   (Fed_Share × State_Fed_Density) +
                   (State_Share × State_State_Density) +
                   (Local_Share × State_Local_Density)

Uses state-adjusted density rates from state_govt_level_density table.

Usage: py scripts/calculate_county_density.py
"""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

print("=" * 80)
print("CALCULATING COUNTY UNION DENSITY ESTIMATES")
print("=" * 80)

# Create estimates table
print("\n1. Creating county_union_density_estimates table...")
cur.execute("""
    DROP TABLE IF EXISTS county_union_density_estimates CASCADE;

    CREATE TABLE county_union_density_estimates (
        fips VARCHAR(5) PRIMARY KEY,
        state_fips VARCHAR(2) NOT NULL,
        county_fips VARCHAR(3) NOT NULL,
        state VARCHAR(2) NOT NULL,
        county_name VARCHAR(100),

        -- Estimated densities
        estimated_total_density DECIMAL(5,2),
        estimated_private_density DECIMAL(5,2),
        estimated_public_density DECIMAL(5,2),
        estimated_federal_density DECIMAL(5,2),
        estimated_state_density DECIMAL(5,2),
        estimated_local_density DECIMAL(5,2),

        -- Inputs used (for transparency)
        private_share DECIMAL(8,6),
        federal_share DECIMAL(8,6),
        state_share DECIMAL(8,6),
        local_share DECIMAL(8,6),
        public_share DECIMAL(8,6),

        -- State rates used
        state_private_rate DECIMAL(5,2),
        state_federal_rate DECIMAL(5,2),
        state_state_rate DECIMAL(5,2),
        state_local_rate DECIMAL(5,2),

        -- Metadata
        confidence_level VARCHAR(20),
        state_multiplier DECIMAL(5,3),
        methodology VARCHAR(100) DEFAULT 'state_density_county_composition',
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX idx_county_density_state ON county_union_density_estimates(state);
    CREATE INDEX idx_county_density_total ON county_union_density_estimates(estimated_total_density DESC);

    COMMENT ON TABLE county_union_density_estimates IS
        'Estimated union density by county using state rates × county workforce composition';
""")
conn.commit()
print("   Table created")

# Calculate estimates
print("\n2. Calculating density estimates...")

cur.execute("""
    SELECT
        cw.fips,
        cw.state_fips,
        cw.county_fips,
        cw.state,
        cw.county_name,
        cw.private_share,
        cw.federal_gov_share,
        cw.state_gov_share,
        cw.local_gov_share,
        cw.public_share,

        -- State densities
        sd.private_density_pct,
        sd.public_is_estimated,

        -- Government level densities (state-adjusted)
        gl.est_federal_density,
        gl.est_state_density,
        gl.est_local_density,
        gl.multiplier

    FROM county_workforce_shares cw
    JOIN v_state_density_latest sd ON cw.state = sd.state
    JOIN state_govt_level_density gl ON cw.state = gl.state
""")

rows = cur.fetchall()
print(f"   Processing {len(rows)} counties...")

inserted = 0
for row in rows:
    fips = row[0]
    state_fips = row[1]
    county_fips = row[2]
    state = row[3]
    county_name = row[4]
    private_share = float(row[5]) if row[5] else 0
    federal_share = float(row[6]) if row[6] else 0
    state_share = float(row[7]) if row[7] else 0
    local_share = float(row[8]) if row[8] else 0
    public_share = float(row[9]) if row[9] else 0

    state_private_rate = float(row[10]) if row[10] else 0
    state_public_is_estimated = row[11]

    state_federal_rate = float(row[12]) if row[12] else 0
    state_state_rate = float(row[13]) if row[13] else 0
    state_local_rate = float(row[14]) if row[14] else 0
    state_multiplier = float(row[15]) if row[15] else 0

    # Calculate total density
    private_component = private_share * state_private_rate
    federal_component = federal_share * state_federal_rate
    state_component = state_share * state_state_rate
    local_component = local_share * state_local_rate

    total_density = private_component + federal_component + state_component + local_component

    # Calculate public-only density (weighted average of gov levels)
    if public_share > 0:
        public_density = (federal_component + state_component + local_component) / public_share
    else:
        public_density = 0

    # Confidence level based on state data quality
    confidence = 'HIGH' if not state_public_is_estimated else 'MEDIUM'

    # Insert estimate
    cur.execute("""
        INSERT INTO county_union_density_estimates
            (fips, state_fips, county_fips, state, county_name,
             estimated_total_density, estimated_private_density, estimated_public_density,
             estimated_federal_density, estimated_state_density, estimated_local_density,
             private_share, federal_share, state_share, local_share, public_share,
             state_private_rate, state_federal_rate, state_state_rate, state_local_rate,
             confidence_level, state_multiplier)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        fips, state_fips, county_fips, state, county_name,
        round(total_density, 2),
        round(state_private_rate, 2),  # Private density = state rate (no county variation)
        round(public_density, 2) if public_share > 0 else None,
        round(state_federal_rate, 2),
        round(state_state_rate, 2),
        round(state_local_rate, 2),
        private_share, federal_share, state_share, local_share, public_share,
        state_private_rate, state_federal_rate, state_state_rate, state_local_rate,
        confidence, state_multiplier
    ))
    inserted += 1

conn.commit()
print(f"   Inserted {inserted} county estimates")

# Create summary view
print("\n3. Creating summary views...")
cur.execute("""
    DROP VIEW IF EXISTS v_county_density_summary CASCADE;

    CREATE VIEW v_county_density_summary AS
    SELECT
        e.fips,
        e.state,
        e.county_name,
        e.estimated_total_density,
        e.estimated_private_density,
        e.estimated_public_density,
        e.confidence_level,
        e.state_multiplier,
        w.public_share * 100 as public_workforce_pct,
        w.private_share * 100 as private_workforce_pct
    FROM county_union_density_estimates e
    JOIN county_workforce_shares w ON e.fips = w.fips
    ORDER BY e.estimated_total_density DESC;

    COMMENT ON VIEW v_county_density_summary IS
        'Summary of county density estimates with workforce composition';
""")

cur.execute("""
    DROP VIEW IF EXISTS v_state_county_comparison CASCADE;

    CREATE VIEW v_state_county_comparison AS
    SELECT
        e.state,
        gl.state_name,
        COUNT(*) as county_count,
        ROUND(AVG(e.estimated_total_density), 2) as avg_county_density,
        ROUND(MIN(e.estimated_total_density), 2) as min_county_density,
        ROUND(MAX(e.estimated_total_density), 2) as max_county_density,
        ROUND(STDDEV(e.estimated_total_density), 2) as stddev_density,
        sd.total_density_pct as state_total_density,
        gl.multiplier as state_multiplier
    FROM county_union_density_estimates e
    JOIN v_state_density_latest sd ON e.state = sd.state
    JOIN state_govt_level_density gl ON e.state = gl.state
    GROUP BY e.state, gl.state_name, sd.total_density_pct, gl.multiplier
    ORDER BY avg_county_density DESC;

    COMMENT ON VIEW v_state_county_comparison IS
        'Compare state-level density with county average';
""")
conn.commit()
print("   Views created")

# Verification
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

# Summary stats
cur.execute("""
    SELECT
        COUNT(*) as total_counties,
        ROUND(AVG(estimated_total_density), 2) as avg_density,
        ROUND(MIN(estimated_total_density), 2) as min_density,
        ROUND(MAX(estimated_total_density), 2) as max_density,
        COUNT(CASE WHEN confidence_level = 'HIGH' THEN 1 END) as high_confidence,
        COUNT(CASE WHEN confidence_level = 'MEDIUM' THEN 1 END) as medium_confidence
    FROM county_union_density_estimates
""")
row = cur.fetchone()
print(f"\nNational Summary:")
print(f"  Total counties: {row[0]}")
print(f"  Avg density: {row[1]}%")
print(f"  Min density: {row[2]}%")
print(f"  Max density: {row[3]}%")
print(f"  High confidence: {row[4]} counties")
print(f"  Medium confidence: {row[5]} counties")

# Check for invalid values
cur.execute("""
    SELECT COUNT(*) FROM county_union_density_estimates
    WHERE estimated_total_density < 0 OR estimated_total_density > 100
""")
invalid = cur.fetchone()[0]
print(f"\nInvalid density values (outside 0-100%): {invalid}")

# Top 10 highest density counties
cur.execute("""
    SELECT fips, state, county_name, estimated_total_density, estimated_public_density
    FROM county_union_density_estimates
    ORDER BY estimated_total_density DESC
    LIMIT 10
""")
print(f"\nTop 10 Highest Density Counties:")
print(f"  {'FIPS':6} | {'ST':2} | {'County':25} | {'Total':6} | {'Public':6}")
for row in cur.fetchall():
    pub = f"{row[4]:.1f}%" if row[4] else "N/A"
    print(f"  {row[0]:6} | {row[1]:2} | {row[2][:25]:25} | {row[3]:5.1f}% | {pub:>6}")

# Bottom 10 lowest density counties
cur.execute("""
    SELECT fips, state, county_name, estimated_total_density, estimated_public_density
    FROM county_union_density_estimates
    ORDER BY estimated_total_density ASC
    LIMIT 10
""")
print(f"\nBottom 10 Lowest Density Counties:")
print(f"  {'FIPS':6} | {'ST':2} | {'County':25} | {'Total':6} | {'Public':6}")
for row in cur.fetchall():
    pub = f"{row[4]:.1f}%" if row[4] else "N/A"
    print(f"  {row[0]:6} | {row[1]:2} | {row[2][:25]:25} | {row[3]:5.1f}% | {pub:>6}")

# Spot check known counties
cur.execute("""
    SELECT fips, state, county_name, estimated_total_density,
           private_share * 100 as priv_pct,
           public_share * 100 as pub_pct,
           state_multiplier
    FROM county_union_density_estimates
    WHERE fips IN ('36061', '17031', '06037', '48201', '04013')
    ORDER BY estimated_total_density DESC
""")
print(f"\nSpot Check (Manhattan, Cook, LA, Harris, Maricopa):")
print(f"  {'FIPS':6} | {'ST':2} | {'County':20} | {'Density':7} | {'Priv%':6} | {'Pub%':5} | {'k':5}")
for row in cur.fetchall():
    print(f"  {row[0]:6} | {row[1]:2} | {row[2][:20]:20} | {row[3]:6.1f}% | {row[4]:5.1f}% | {row[5]:4.1f}% | {row[6]:5.2f}")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("COMPLETE")
print("=" * 80)
