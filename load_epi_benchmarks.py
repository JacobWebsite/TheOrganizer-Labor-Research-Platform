import pandas as pd
import psycopg2
import numpy as np

# State abbreviation mapping
state_abbrev = {
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

# Read the four key EPI files
data_dir = r"C:\Users\jakew\Downloads\EPI data public and private"

members_private = pd.read_csv(f'{data_dir}/Number of union members Private by state - Union membership - Time Series.csv')
members_public = pd.read_csv(f'{data_dir}/Number of union members Public by state- Union membership - Time Series.csv')
represented_private = pd.read_csv(f'{data_dir}/Number represented by a union Private by state - Union membership - Time Series.csv')
represented_public = pd.read_csv(f'{data_dir}/Number represented by a union Public by state - Union membership - Time Series.csv')

# Parse dates and sort descending (most recent first)
for df in [members_private, members_public, represented_private, represented_public]:
    df['date'] = pd.to_datetime(df['date'])
    df.sort_values('date', ascending=False, inplace=True)

# Get all state columns
states = [col for col in members_private.columns if col != 'date']

def get_most_recent_value(df, state_name):
    """Get the most recent non-null value for a state and its year"""
    for idx, row in df.iterrows():
        val = row.get(state_name)
        if pd.notna(val):
            year = row['date'].year
            return int(float(val)), year
    return None, None

# Connect to database
conn = psycopg2.connect(
    host="localhost",
    database="olms_multiyear",
    user="postgres",
    password="Juniordog33!"
)
cur = conn.cursor()

# Recreate table with year tracking for each field
cur.execute("""
DROP TABLE IF EXISTS epi_state_benchmarks CASCADE;
CREATE TABLE epi_state_benchmarks (
    state VARCHAR(2) PRIMARY KEY,
    state_name VARCHAR(50),
    -- Union Members (dues-paying)
    members_private INTEGER,
    members_private_year INTEGER,
    members_public INTEGER,
    members_public_year INTEGER,
    members_total INTEGER,
    -- Represented Workers (covered by CBA but may not be members)
    represented_private INTEGER,
    represented_private_year INTEGER,
    represented_public INTEGER,
    represented_public_year INTEGER,
    represented_total INTEGER,
    -- Calculated fields
    free_riders_private INTEGER GENERATED ALWAYS AS (represented_private - members_private) STORED,
    free_riders_public INTEGER GENERATED ALWAYS AS (represented_public - members_public) STORED,
    free_rider_rate_private DECIMAL(5,2) GENERATED ALWAYS AS (
        CASE WHEN represented_private > 0 
        THEN ROUND(100.0 * (represented_private - members_private) / represented_private, 2)
        ELSE 0 END
    ) STORED,
    free_rider_rate_public DECIMAL(5,2) GENERATED ALWAYS AS (
        CASE WHEN represented_public > 0 
        THEN ROUND(100.0 * (represented_public - members_public) / represented_public, 2)
        ELSE 0 END
    ) STORED,
    source VARCHAR(100) DEFAULT 'EPI Analysis of CPS-ORG',
    created_at TIMESTAMP DEFAULT NOW()
);
""")
conn.commit()

# Insert data for each state using most recent available year
inserted = 0
for state_name in states:
    state_code = state_abbrev.get(state_name)
    if not state_code:
        print(f"Skipping unknown state: {state_name}")
        continue
    
    mp, mp_year = get_most_recent_value(members_private, state_name)
    mpu, mpu_year = get_most_recent_value(members_public, state_name)
    rp, rp_year = get_most_recent_value(represented_private, state_name)
    rpu, rpu_year = get_most_recent_value(represented_public, state_name)
    
    # Calculate totals
    mt = (mp or 0) + (mpu or 0) if (mp or mpu) else None
    rt = (rp or 0) + (rpu or 0) if (rp or rpu) else None
    
    cur.execute("""
        INSERT INTO epi_state_benchmarks 
        (state, state_name, members_private, members_private_year, members_public, members_public_year, members_total,
         represented_private, represented_private_year, represented_public, represented_public_year, represented_total)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (state_code, state_name, mp, mp_year, mpu, mpu_year, mt, rp, rp_year, rpu, rpu_year, rt))
    inserted += 1

conn.commit()
print(f"Inserted {inserted} state records with most recent available data")

# Show results with year info
cur.execute("""
    SELECT state, state_name, 
           members_private, members_private_year,
           members_public, members_public_year,
           members_total,
           represented_private, represented_private_year,
           represented_public, represented_public_year,
           free_riders_public, free_rider_rate_public
    FROM epi_state_benchmarks 
    ORDER BY members_total DESC NULLS LAST
""")

print("\n=== ALL STATES - EPI BENCHMARKS (Most Recent Year Available) ===")
print(f"{'ST':<3} {'State Name':<22} {'Mem Priv':>10} {'Yr':>4} {'Mem Pub':>10} {'Yr':>4} {'Total':>10} {'Rep Priv':>10} {'Rep Pub':>10} {'FR Pub':>8} {'FR%':>6}")
print("-" * 130)
for row in cur.fetchall():
    state, name, mp, mp_yr, mpu, mpu_yr, mt, rp, rp_yr, rpu, rpu_yr, frp, frr = row
    print(f"{state:<3} {name[:22]:<22} {mp or 0:>10,} {mp_yr or '':>4} {mpu or 0:>10,} {mpu_yr or '':>4} {mt or 0:>10,} {rp or 0:>10,} {rpu or 0:>10,} {frp or 0:>8,} {frr or 0:>5.1f}%")

# Summary statistics
cur.execute("""
    SELECT 
        COUNT(*) as total_states,
        SUM(members_private) as total_private_members,
        SUM(members_public) as total_public_members,
        SUM(members_total) as total_all_members,
        SUM(represented_private) as total_private_represented,
        SUM(represented_public) as total_public_represented,
        SUM(free_riders_public) as total_public_free_riders,
        ROUND(AVG(free_rider_rate_public), 1) as avg_public_free_rider_rate
    FROM epi_state_benchmarks
""")
stats = cur.fetchone()
print(f"\n=== NATIONAL TOTALS ===")
print(f"States with data: {stats[0]}")
print(f"Total Private Sector Members: {stats[1]:,}")
print(f"Total Public Sector Members: {stats[2]:,}")
print(f"Total All Members: {stats[3]:,}")
print(f"Total Private Represented: {stats[4]:,}")
print(f"Total Public Represented: {stats[5]:,}")
print(f"Total Public Free Riders: {stats[6]:,}")
print(f"Avg Public Free Rider Rate: {stats[7]}%")

cur.close()
conn.close()
