import os
"""
Load State Union Density by Sector (Private/Public)

Source: unionstats.com (Hirsch/Macpherson union density data)
Format: CSV with geo, date, value columns

Usage: py scripts/load_state_sector_density.py
"""

import psycopg2
import pandas as pd
from pathlib import Path

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
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

print("=" * 80)
print("LOADING STATE UNION DENSITY BY SECTOR")
print("=" * 80)

# Create table
print("\n1. Creating state_sector_union_density table...")
cur.execute("""
    DROP TABLE IF EXISTS state_sector_union_density CASCADE;

    CREATE TABLE state_sector_union_density (
        id SERIAL PRIMARY KEY,
        state VARCHAR(2),
        state_name VARCHAR(50),
        sector VARCHAR(10),  -- 'private' or 'public'
        year INTEGER,
        density_pct DECIMAL(5,2),  -- Store as percentage (5.9 not 0.059)
        source VARCHAR(50) DEFAULT 'unionstats_csv',
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(state, sector, year)
    );

    CREATE INDEX idx_state_sector_density ON state_sector_union_density(state, sector, year);

    COMMENT ON TABLE state_sector_union_density IS
        'Union density by state and sector (private/public) from unionstats.com';
""")
conn.commit()
print("   Table created")

# File paths
private_csv = Path(r"C:\Users\jakew\Downloads\Share in a union private sector by state - Union membership - Cartogram.csv")
public_csv = Path(r"C:\Users\jakew\Downloads\Share in a union public sector by state - Union membership - Cartogram (2).csv")

def load_sector_data(filepath: Path, sector: str) -> int:
    """Load density data for a sector from CSV"""
    df = pd.read_csv(filepath)

    # Filter out "United States" rows (keep only state data)
    df = df[df['geo'] != 'United States'].copy()

    # Map state names to abbreviations
    df['state'] = df['geo'].map(STATE_MAPPING)

    # Check for unmapped states
    unmapped = df[df['state'].isna()]['geo'].unique()
    if len(unmapped) > 0:
        print(f"   Warning: Unmapped geo values: {unmapped}")

    # Drop rows without state mapping
    df = df.dropna(subset=['state'])

    # Parse year from date (format: YYYY-01-01)
    df['year'] = pd.to_datetime(df['date']).dt.year

    # Convert decimal to percentage
    df['density_pct'] = (df['value'] * 100).round(2)

    # Insert records
    records_inserted = 0
    for _, row in df.iterrows():
        try:
            cur.execute("""
                INSERT INTO state_sector_union_density
                    (state, state_name, sector, year, density_pct)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (state, sector, year) DO UPDATE
                SET density_pct = EXCLUDED.density_pct,
                    created_at = NOW()
            """, (
                row['state'],
                row['geo'],
                sector,
                int(row['year']),
                float(row['density_pct'])
            ))
            records_inserted += 1
        except Exception as e:
            print(f"   Error inserting {row['geo']} {row['year']}: {e}")

    conn.commit()
    return records_inserted

# Load private sector data
print("\n2. Loading private sector density data...")
private_count = load_sector_data(private_csv, 'private')
print(f"   Inserted {private_count} private sector records")

# Load public sector data
print("\n3. Loading public sector density data...")
public_count = load_sector_data(public_csv, 'public')
print(f"   Inserted {public_count} public sector records")

# Create summary view for latest data
print("\n4. Creating v_state_density_latest view...")
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
            state, state_name, density_pct, year
        FROM state_sector_union_density
        WHERE sector = 'public' AND year >= 2020  -- Last 5 years only
        ORDER BY state, year DESC
    )
    SELECT
        COALESCE(pr.state, pu.state) as state,
        COALESCE(pr.state_name, pu.state_name) as state_name,
        pr.density_pct as private_density_pct,
        pr.year as private_year,
        pu.density_pct as public_density_pct,
        pu.year as public_year
    FROM latest_private pr
    FULL OUTER JOIN latest_public pu ON pr.state = pu.state
    ORDER BY state;

    COMMENT ON VIEW v_state_density_latest IS
        'Latest union density by state (private and public sectors)';
""")
conn.commit()
print("   View created")

# Verify loaded data
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cur.execute("""
    SELECT sector, COUNT(*) as records, COUNT(DISTINCT state) as states,
           MIN(year) as min_year, MAX(year) as max_year,
           ROUND(AVG(density_pct), 2) as avg_density
    FROM state_sector_union_density
    GROUP BY sector
    ORDER BY sector
""")
print("\nSummary by sector:")
for row in cur.fetchall():
    print(f"  {row[0]:8} | {row[1]:5} records | {row[2]:2} states | years {row[3]}-{row[4]} | avg {row[5]}%")

# Sample latest data
print("\nSample of latest data (v_state_density_latest):")
cur.execute("""
    SELECT state, private_density_pct, private_year,
           public_density_pct, public_year
    FROM v_state_density_latest
    WHERE state IN ('NY', 'CA', 'TX', 'WI', 'SC')
    ORDER BY state
""")
print(f"  {'State':6} | {'Private':8} | {'Year':4} | {'Public':8} | {'Year':4}")
print(f"  {'-'*6} | {'-'*8} | {'-'*4} | {'-'*8} | {'-'*4}")
for row in cur.fetchall():
    priv = f"{row[1]:.1f}%" if row[1] else "N/A"
    pub = f"{row[3]:.1f}%" if row[3] else "N/A"
    print(f"  {row[0]:6} | {priv:>8} | {row[2] or 'N/A':>4} | {pub:>8} | {row[4] or 'N/A':>4}")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("COMPLETE!")
print("=" * 80)
print(f"""
Created:
  - state_sector_union_density (table): {private_count + public_count} records
  - v_state_density_latest (view): Latest density by state

Next steps:
  - API endpoints: /api/density/by-state and /api/density/by-state/{{state}}/history
""")
