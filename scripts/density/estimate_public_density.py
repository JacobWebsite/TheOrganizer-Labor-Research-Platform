"""
Estimate Missing Public Sector Union Density

For 25 states that have no recent (2020+) public sector union density data,
we estimate public density using:
- Total union density (public + private combined)
- Private sector density (already loaded)
- Workforce shares (% of workforce in public vs private sector)

Formula:
  Total_Density = (Private_Share × Private_Density) + (Public_Share × Public_Density)

  Solving for Public_Density:
  Public_Density = (Total_Density - (Private_Share × Private_Density)) / Public_Share

Usage: py scripts/estimate_public_density.py
"""

import psycopg2
import pandas as pd
from pathlib import Path
from decimal import Decimal

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

# State name to abbreviation mapping
STATE_MAPPING = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
    'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
    'District of Columbia': 'DC', 'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI',
    'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME',
    'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE',
    'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM',
    'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH',
    'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI',
    'South Carolina': 'SC', 'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX',
    'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA',
    'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'
}

ABBREV_TO_NAME = {v: k for k, v in STATE_MAPPING.items()}

print("=" * 80)
print("ESTIMATING MISSING PUBLIC SECTOR UNION DENSITY")
print("=" * 80)

# ============================================================================
# STEP 1: Create state_workforce_shares table and load data
# ============================================================================
print("\n1. Creating state_workforce_shares table...")

cur.execute("""
    DROP TABLE IF EXISTS state_workforce_shares CASCADE;

    CREATE TABLE state_workforce_shares (
        state VARCHAR(2) PRIMARY KEY,
        state_name VARCHAR(50),
        public_share DECIMAL(8,6),   -- e.g., 0.166288 = 16.63%
        private_share DECIMAL(8,6),
        self_employed_share DECIMAL(8,6),
        federal_gov_share DECIMAL(8,6),
        state_gov_share DECIMAL(8,6),
        local_gov_share DECIMAL(8,6),
        source VARCHAR(50) DEFAULT 'acs_cps',
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX idx_workforce_shares_state ON state_workforce_shares(state);

    COMMENT ON TABLE state_workforce_shares IS
        'Public/private workforce shares by state from ACS/CPS data';
""")
conn.commit()
print("   Table created")

# Load workforce shares CSV
workforce_csv = Path(r"C:\Users\jakew\Downloads\labor-data-project\state_workforce_public_private_shares.csv")
df_workforce = pd.read_csv(workforce_csv)

print(f"   Loading {len(df_workforce)} workforce share records...")
records_inserted = 0
for _, row in df_workforce.iterrows():
    state_name = row['State']
    state_abbr = STATE_MAPPING.get(state_name)

    if state_abbr is None:
        print(f"   Warning: Skipping unmapped state: {state_name}")
        continue

    cur.execute("""
        INSERT INTO state_workforce_shares
            (state, state_name, public_share, private_share, self_employed_share,
             federal_gov_share, state_gov_share, local_gov_share)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (state) DO UPDATE SET
            public_share = EXCLUDED.public_share,
            private_share = EXCLUDED.private_share,
            self_employed_share = EXCLUDED.self_employed_share,
            federal_gov_share = EXCLUDED.federal_gov_share,
            state_gov_share = EXCLUDED.state_gov_share,
            local_gov_share = EXCLUDED.local_gov_share,
            created_at = NOW()
    """, (
        state_abbr,
        state_name,
        float(row['Public_Share']),
        float(row['Private_Share']),
        float(row['Self_Employed_Share']),
        float(row['Federal_Gov']),
        float(row['State_Gov']),
        float(row['Local_Gov'])
    ))
    records_inserted += 1

conn.commit()
print(f"   Inserted {records_inserted} workforce share records")

# ============================================================================
# STEP 2: Load total density data
# ============================================================================
print("\n2. Loading total (combined) density data...")

total_csv = Path(r"C:\Users\jakew\Downloads\Share in a union public and private sector - Union membership - Cartogram.csv")
df_total = pd.read_csv(total_csv)

# Filter out "United States" rows (keep only state data)
df_total = df_total[df_total['geo'] != 'United States'].copy()

# Map state names to abbreviations
df_total['state'] = df_total['geo'].map(STATE_MAPPING)

# Check for unmapped states
unmapped = df_total[df_total['state'].isna()]['geo'].unique()
if len(unmapped) > 0:
    print(f"   Warning: Unmapped geo values: {unmapped}")

# Drop rows without state mapping
df_total = df_total.dropna(subset=['state'])

# Parse year from date (format: YYYY-01-01)
df_total['year'] = pd.to_datetime(df_total['date']).dt.year

# Convert decimal to percentage
df_total['density_pct'] = (df_total['value'] * 100).round(2)

# Insert total density records
total_inserted = 0
for _, row in df_total.iterrows():
    try:
        cur.execute("""
            INSERT INTO state_sector_union_density
                (state, state_name, sector, year, density_pct, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (state, sector, year) DO UPDATE
            SET density_pct = EXCLUDED.density_pct,
                source = EXCLUDED.source,
                created_at = NOW()
        """, (
            row['state'],
            row['geo'],
            'total',
            int(row['year']),
            float(row['density_pct']),
            'unionstats_csv'
        ))
        total_inserted += 1
    except Exception as e:
        print(f"   Error inserting {row['geo']} {row['year']}: {e}")

conn.commit()
print(f"   Inserted {total_inserted} total density records")

# ============================================================================
# STEP 3: Calculate estimated public density for missing states
# ============================================================================
print("\n3. Calculating estimated public density...")

# Find states missing public density for 2020+
cur.execute("""
    WITH states_with_public AS (
        SELECT DISTINCT state
        FROM state_sector_union_density
        WHERE sector = 'public' AND year >= 2020 AND source != 'estimated_from_total'
    )
    SELECT DISTINCT t.state, t.state_name, t.year
    FROM state_sector_union_density t
    LEFT JOIN states_with_public swp ON t.state = swp.state
    WHERE t.sector = 'total'
      AND t.year >= 2020
      AND swp.state IS NULL
    ORDER BY t.state, t.year
""")
missing_states_years = cur.fetchall()
print(f"   Found {len(missing_states_years)} state-year combinations missing public density")

# Calculate estimates
estimates_inserted = 0
estimates_skipped = 0

for state, state_name, year in missing_states_years:
    # Get total density for this state-year
    cur.execute("""
        SELECT density_pct FROM state_sector_union_density
        WHERE state = %s AND year = %s AND sector = 'total'
    """, (state, year))
    result = cur.fetchone()
    if not result:
        estimates_skipped += 1
        continue
    total_density = float(result[0])

    # Get private density for this state-year
    cur.execute("""
        SELECT density_pct FROM state_sector_union_density
        WHERE state = %s AND year = %s AND sector = 'private'
    """, (state, year))
    result = cur.fetchone()
    if not result:
        estimates_skipped += 1
        continue
    private_density = float(result[0])

    # Get workforce shares for this state
    cur.execute("""
        SELECT public_share, private_share FROM state_workforce_shares
        WHERE state = %s
    """, (state,))
    result = cur.fetchone()
    if not result:
        estimates_skipped += 1
        continue
    public_share = float(result[0])
    private_share = float(result[1])

    # Calculate: Public_Density = (Total - Private_Share × Private) / Public_Share
    # Note: densities are in percentage (0-100), shares are decimal (0-1)
    # Formula: total_pct = private_share * private_pct + public_share * public_pct
    # Rearranged: public_pct = (total_pct - private_share * private_pct) / public_share

    if public_share <= 0:
        estimates_skipped += 1
        continue

    estimated_public = (total_density - private_share * private_density) / public_share

    # Validate estimate is reasonable (0-100%)
    if estimated_public < 0 or estimated_public > 100:
        print(f"   Warning: Unreasonable estimate for {state} {year}: {estimated_public:.1f}% (skipping)")
        estimates_skipped += 1
        continue

    # Insert estimate
    cur.execute("""
        INSERT INTO state_sector_union_density
            (state, state_name, sector, year, density_pct, source)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (state, sector, year) DO UPDATE
        SET density_pct = EXCLUDED.density_pct,
            source = EXCLUDED.source,
            created_at = NOW()
    """, (
        state,
        state_name,
        'public',
        year,
        round(estimated_public, 2),
        'estimated_from_total'
    ))
    estimates_inserted += 1

conn.commit()
print(f"   Inserted {estimates_inserted} estimated public density records")
print(f"   Skipped {estimates_skipped} records (missing data or unreasonable estimates)")

# ============================================================================
# STEP 4: Update the view to show estimated flag
# ============================================================================
print("\n4. Updating v_state_density_latest view...")

cur.execute("""
    DROP VIEW IF EXISTS v_state_density_latest CASCADE;

    CREATE OR REPLACE VIEW v_state_density_latest AS
    WITH latest_private AS (
        SELECT DISTINCT ON (state)
            state, state_name, density_pct, year
        FROM state_sector_union_density
        WHERE sector = 'private'
        ORDER BY state, year DESC
    ),
    latest_public AS (
        SELECT DISTINCT ON (state)
            state, state_name, density_pct, year,
            (source = 'estimated_from_total') as is_estimated
        FROM state_sector_union_density
        WHERE sector = 'public'
        ORDER BY state, year DESC
    ),
    latest_total AS (
        SELECT DISTINCT ON (state)
            state, density_pct as total_density_pct, year as total_year
        FROM state_sector_union_density
        WHERE sector = 'total'
        ORDER BY state, year DESC
    )
    SELECT
        COALESCE(pr.state, pu.state, t.state) as state,
        COALESCE(pr.state_name, pu.state_name) as state_name,
        pr.density_pct as private_density_pct,
        pr.year as private_year,
        pu.density_pct as public_density_pct,
        pu.year as public_year,
        COALESCE(pu.is_estimated, false) as public_is_estimated,
        t.total_density_pct,
        t.total_year
    FROM latest_private pr
    FULL OUTER JOIN latest_public pu ON pr.state = pu.state
    FULL OUTER JOIN latest_total t ON COALESCE(pr.state, pu.state) = t.state
    ORDER BY state;

    COMMENT ON VIEW v_state_density_latest IS
        'Latest union density by state (private, public, total) with estimation flag';
""")
conn.commit()
print("   View updated")

# ============================================================================
# VERIFICATION
# ============================================================================
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

# Summary by sector
cur.execute("""
    SELECT sector, COUNT(*) as records, COUNT(DISTINCT state) as states,
           MIN(year) as min_year, MAX(year) as max_year,
           ROUND(AVG(density_pct), 2) as avg_density
    FROM state_sector_union_density
    GROUP BY sector
    ORDER BY sector
""")
print("\nSummary by sector:")
print(f"  {'Sector':10} | {'Records':7} | {'States':6} | {'Years':10} | {'Avg %':6}")
print(f"  {'-'*10} | {'-'*7} | {'-'*6} | {'-'*10} | {'-'*6}")
for row in cur.fetchall():
    print(f"  {row[0]:10} | {row[1]:7} | {row[2]:6} | {row[3]}-{row[4]:4} | {row[5]:5.1f}%")

# States with public density coverage
cur.execute("""
    SELECT
        COUNT(*) as total_states,
        COUNT(CASE WHEN public_density_pct IS NOT NULL THEN 1 END) as with_public,
        COUNT(CASE WHEN public_is_estimated THEN 1 END) as estimated
    FROM v_state_density_latest
""")
row = cur.fetchone()
print(f"\nPublic density coverage:")
print(f"  Total states: {row[0]}")
print(f"  With public density: {row[1]}")
print(f"  Estimated: {row[2]}")
print(f"  Direct measurement: {row[1] - row[2]}")

# Sample of estimated states
cur.execute("""
    SELECT state, private_density_pct, public_density_pct, public_is_estimated, total_density_pct
    FROM v_state_density_latest
    WHERE public_is_estimated = true
    ORDER BY state
    LIMIT 10
""")
print("\nSample of estimated public density (first 10):")
print(f"  {'State':6} | {'Private':8} | {'Public':8} | {'Total':8} | {'Est':4}")
print(f"  {'-'*6} | {'-'*8} | {'-'*8} | {'-'*8} | {'-'*4}")
for row in cur.fetchall():
    priv = f"{row[1]:.1f}%" if row[1] else "N/A"
    pub = f"{row[2]:.1f}%" if row[2] else "N/A"
    tot = f"{row[4]:.1f}%" if row[4] else "N/A"
    est = "Yes" if row[3] else "No"
    print(f"  {row[0]:6} | {priv:>8} | {pub:>8} | {tot:>8} | {est:>4}")

# Validate estimates are reasonable
cur.execute("""
    SELECT state, density_pct as public_pct
    FROM state_sector_union_density
    WHERE sector = 'public' AND source = 'estimated_from_total'
      AND (density_pct < 0 OR density_pct > 80)
""")
invalid = cur.fetchall()
if invalid:
    print(f"\nWarning: {len(invalid)} estimates outside 0-80% range:")
    for row in invalid:
        print(f"  {row[0]}: {row[1]:.1f}%")
else:
    print("\n\nAll estimates within reasonable 0-80% range")

# For states WITH direct public data, compare calculated vs actual
print("\n" + "=" * 80)
print("VALIDATION: Comparing formula vs direct measurement (2025)")
print("=" * 80)

cur.execute("""
    SELECT
        t.state,
        t.density_pct as total,
        p.density_pct as private,
        pub.density_pct as public_actual,
        ROUND(
            (t.density_pct - (w.private_share * p.density_pct)) / w.public_share,
            2
        ) as public_calculated,
        ROUND(
            pub.density_pct - (t.density_pct - (w.private_share * p.density_pct)) / w.public_share,
            2
        ) as diff
    FROM state_sector_union_density t
    JOIN state_sector_union_density p ON t.state = p.state AND t.year = p.year AND p.sector = 'private'
    JOIN state_sector_union_density pub ON t.state = pub.state AND t.year = pub.year AND pub.sector = 'public' AND pub.source = 'unionstats_csv'
    JOIN state_workforce_shares w ON t.state = w.state
    WHERE t.sector = 'total' AND t.year = 2025
    ORDER BY ABS(pub.density_pct - (t.density_pct - (w.private_share * p.density_pct)) / w.public_share) DESC
    LIMIT 15
""")

results = cur.fetchall()
if results:
    print(f"\n{'State':6} | {'Total':7} | {'Private':8} | {'Pub Act':8} | {'Pub Calc':9} | {'Diff':6}")
    print(f"{'-'*6} | {'-'*7} | {'-'*8} | {'-'*8} | {'-'*9} | {'-'*6}")
    for row in results:
        print(f"{row[0]:6} | {row[1]:6.1f}% | {row[2]:7.1f}% | {row[3]:7.1f}% | {row[4]:8.1f}% | {row[5]:+5.1f}%")
else:
    print("\nNo states with both direct public measurement and total data for validation")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("COMPLETE!")
print("=" * 80)
print(f"""
Created:
  - state_workforce_shares (table): {records_inserted} records
  - state_sector_union_density: Added {total_inserted} 'total' records
  - state_sector_union_density: Added {estimates_inserted} estimated 'public' records
  - v_state_density_latest (view): Updated with public_is_estimated flag

Next steps:
  - Update API endpoint /api/density/by-state to include is_estimated flag
  - UI can show asterisk or different styling for estimated values
""")
