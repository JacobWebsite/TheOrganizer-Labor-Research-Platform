import os
from db_config import get_connection
"""
Load County Workforce Shares from CSV

Source: ACS county-level employment data (2025 estimates)
Records: ~3,222 counties (78 PR municipios excluded)

Usage: py scripts/load_county_workforce.py
"""

import psycopg2
import pandas as pd
from pathlib import Path

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("LOADING COUNTY WORKFORCE SHARES")
print("=" * 80)

# Create table
print("\n1. Creating county_workforce_shares table...")
cur.execute("""
    DROP TABLE IF EXISTS county_workforce_shares CASCADE;

    CREATE TABLE county_workforce_shares (
        fips VARCHAR(5) PRIMARY KEY,
        state_fips VARCHAR(2) NOT NULL,
        county_fips VARCHAR(3) NOT NULL,
        state VARCHAR(2) NOT NULL,
        county_name VARCHAR(100),
        private_share DECIMAL(8,6),
        private_forprofit_share DECIMAL(8,6),
        private_nonprofit_share DECIMAL(8,6),
        federal_gov_share DECIMAL(8,6),
        state_gov_share DECIMAL(8,6),
        local_gov_share DECIMAL(8,6),
        public_share DECIMAL(8,6),
        self_employed_share DECIMAL(8,6),
        source VARCHAR(50) DEFAULT 'acs_county_2025',
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX idx_county_workforce_state ON county_workforce_shares(state);
    CREATE INDEX idx_county_workforce_state_fips ON county_workforce_shares(state_fips);

    COMMENT ON TABLE county_workforce_shares IS
        'County-level workforce composition from ACS 2025 estimates';
""")
conn.commit()
print("   Table created")

# Load CSV
csv_path = Path(r"C:\Users\jakew\Downloads\All US Counties_New Project 3_Ranking_2026-02-05_10-56-07.csv")
print(f"\n2. Loading CSV from: {csv_path.name}")

df = pd.read_csv(csv_path)
print(f"   Raw records: {len(df)}")

# Column mapping
col_local = '% Class of Worker | Local government workers, 2025 [Estimated]'
col_state = '% Class of Worker | State government workers, 2025 [Estimated]'
col_federal = '% Class of Worker | Federal government workers, 2025 [Estimated]'
col_self_emp = '% Class of Worker | Self-employed in own not incorporated business workers, 2025 [Estimated]'
col_priv_profit = '% Class of Worker | Private for-profit wage and salary workers, 2025 [Estimated]'
col_priv_nonprofit = '% Class of Worker | Private not-for-profit wage and salary workers, 2025 [Estimated]'

# Parse state from Name column (e.g., "Abbeville County, SC" -> "SC")
df['state'] = df['Name'].str.extract(r', ([A-Z]{2})$')

# Exclude Puerto Rico
pr_count = len(df[df['state'] == 'PR'])
df = df[df['state'] != 'PR'].copy()
print(f"   Excluded {pr_count} Puerto Rico municipios")
print(f"   Counties to load: {len(df)}")

# Convert FIPS to 5-digit string
df['fips'] = df['FIPS'].astype(str).str.zfill(5)
df['state_fips'] = df['fips'].str[:2]
df['county_fips'] = df['fips'].str[2:]

# Parse county name (remove state suffix)
df['county_name'] = df['Name'].str.replace(r', [A-Z]{2}$', '', regex=True)

# Convert percentages to decimals
df['local_gov_share'] = df[col_local] / 100
df['state_gov_share'] = df[col_state] / 100
df['federal_gov_share'] = df[col_federal] / 100
df['self_employed_share'] = df[col_self_emp] / 100
df['private_forprofit_share'] = df[col_priv_profit] / 100
df['private_nonprofit_share'] = df[col_priv_nonprofit] / 100

# Calculate derived columns
df['private_share'] = df['private_forprofit_share'] + df['private_nonprofit_share']
df['public_share'] = df['federal_gov_share'] + df['state_gov_share'] + df['local_gov_share']

# Verify states exist in our state density tables
cur.execute("SELECT state FROM state_govt_level_density")
valid_states = {row[0] for row in cur.fetchall()}
df['has_state_data'] = df['state'].isin(valid_states)

missing_states = df[~df['has_state_data']]['state'].unique()
if len(missing_states) > 0:
    print(f"   Warning: Counties with missing state data: {missing_states}")
    df = df[df['has_state_data']].copy()
    print(f"   Counties after filtering: {len(df)}")

# Insert records
print("\n3. Inserting county records...")
inserted = 0
for _, row in df.iterrows():
    try:
        cur.execute("""
            INSERT INTO county_workforce_shares
                (fips, state_fips, county_fips, state, county_name,
                 private_share, private_forprofit_share, private_nonprofit_share,
                 federal_gov_share, state_gov_share, local_gov_share,
                 public_share, self_employed_share)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (fips) DO UPDATE SET
                private_share = EXCLUDED.private_share,
                federal_gov_share = EXCLUDED.federal_gov_share,
                state_gov_share = EXCLUDED.state_gov_share,
                local_gov_share = EXCLUDED.local_gov_share,
                public_share = EXCLUDED.public_share,
                created_at = NOW()
        """, (
            row['fips'],
            row['state_fips'],
            row['county_fips'],
            row['state'],
            row['county_name'],
            float(row['private_share']),
            float(row['private_forprofit_share']),
            float(row['private_nonprofit_share']),
            float(row['federal_gov_share']),
            float(row['state_gov_share']),
            float(row['local_gov_share']),
            float(row['public_share']),
            float(row['self_employed_share'])
        ))
        inserted += 1
    except Exception as e:
        print(f"   Error inserting {row['fips']}: {e}")

conn.commit()
print(f"   Inserted {inserted} counties")

# Verification
print("\n" + "=" * 80)
print("VERIFICATION")
print("=" * 80)

cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(DISTINCT state) as states,
           ROUND(AVG(private_share * 100), 1) as avg_private_pct,
           ROUND(AVG(public_share * 100), 1) as avg_public_pct
    FROM county_workforce_shares
""")
row = cur.fetchone()
print(f"\nSummary:")
print(f"  Total counties: {row[0]}")
print(f"  States represented: {row[1]}")
print(f"  Avg private share: {row[2]}%")
print(f"  Avg public share: {row[3]}%")

# Counties by state
cur.execute("""
    SELECT state, COUNT(*) as counties
    FROM county_workforce_shares
    GROUP BY state
    ORDER BY counties DESC
    LIMIT 10
""")
print(f"\nTop 10 states by county count:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} counties")

# Sample data
cur.execute("""
    SELECT fips, state, county_name,
           ROUND(private_share * 100, 1) as private_pct,
           ROUND(public_share * 100, 1) as public_pct,
           ROUND(federal_gov_share * 100, 1) as fed_pct,
           ROUND(local_gov_share * 100, 1) as local_pct
    FROM county_workforce_shares
    WHERE fips IN ('36061', '17031', '06037', '48201', '04013')
    ORDER BY fips
""")
print(f"\nSample counties (Manhattan, Cook, LA, Harris, Maricopa):")
print(f"  {'FIPS':6} | {'ST':2} | {'County':20} | {'Priv%':6} | {'Pub%':5} | {'Fed%':5} | {'Loc%':5}")
for row in cur.fetchall():
    print(f"  {row[0]:6} | {row[1]:2} | {row[2][:20]:20} | {row[3]:5.1f}% | {row[4]:4.1f}% | {row[5]:4.1f}% | {row[6]:4.1f}%")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("COMPLETE")
print("=" * 80)
