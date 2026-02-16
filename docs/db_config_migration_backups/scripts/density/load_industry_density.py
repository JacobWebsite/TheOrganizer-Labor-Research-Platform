import os
"""
Load BLS industry union density rates, state/county industry shares,
and calculate industry-weighted expected density vs actual CPS density.

Creates:
- bls_industry_density: 12 BLS industry union density rates
- state_industry_shares: State-level industry composition
- county_industry_shares: County-level industry composition
- state_industry_density_comparison: Expected vs actual with climate multiplier

Updates:
- county_union_density_estimates: Industry-adjusted private density
"""

import psycopg2
import pandas as pd
import sys
from pathlib import Path

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)

# BLS 2024 Industry Union Density Rates (from Table 3)
BLS_INDUSTRY_RATES = {
    'AGR_MIN': ('Agriculture, forestry, fishing, hunting, mining', 4.0),
    'CONST': ('Construction', 10.3),
    'MFG': ('Manufacturing', 7.8),
    'WHOLESALE': ('Wholesale trade', 4.6),
    'RETAIL': ('Retail trade', 4.0),
    'TRANS_UTIL': ('Transportation and utilities', 16.2),
    'INFO': ('Information', 6.6),
    'FINANCE': ('Financial activities', 1.3),
    'PROF_BUS': ('Professional and business services', 2.0),
    'EDU_HEALTH': ('Education and health services', 8.1),
    'LEISURE': ('Leisure and hospitality', 3.0),
    'OTHER': ('Other services', 2.7),
}

# Column mapping from Excel to database
COLUMN_MAP = {
    '% Industry | Agriculture, forestry, fishing and hunting, and mining, 2025 [Estimated]': 'agriculture_mining_share',
    '% Industry | Construction, 2025 [Estimated]': 'construction_share',
    '% Industry | Manufacturing, 2025 [Estimated]': 'manufacturing_share',
    '% Industry | Wholesale trade, 2025 [Estimated]': 'wholesale_share',
    '% Industry | Retail trade, 2025 [Estimated]': 'retail_share',
    '% Industry | Transportation and warehousing, and utilities, 2025 [Estimated]': 'transportation_utilities_share',
    '% Industry | Information, 2025 [Estimated]': 'information_share',
    '% Industry | Finance and insurance, and real estate, and rental and leasing, 2025 [Estimated]': 'finance_share',
    '% Industry | Professional, scientific, and management, and administrative, and waste management services, 2025 [Estimated]': 'professional_services_share',
    '% Industry | Educational services, and health care and social assistance, 2025 [Estimated]': 'education_health_share',
    '% Industry | Arts, entertainment, and recreation, and accommodation and food services, 2025 [Estimated]': 'leisure_hospitality_share',
    '% Industry | Other services, except public administration, 2025 [Estimated]': 'other_services_share',
    '% Industry | Public administration, 2025 [Estimated]': 'public_admin_share',
}

# Industry share columns to BLS rate mapping
# NOTE: Education/Health and Public Admin are EXCLUDED from private sector calculation
# because these workers are often public employees already captured in govt density
SHARE_TO_RATE = {
    'agriculture_mining_share': 'AGR_MIN',
    'construction_share': 'CONST',
    'manufacturing_share': 'MFG',
    'wholesale_share': 'WHOLESALE',
    'retail_share': 'RETAIL',
    'transportation_utilities_share': 'TRANS_UTIL',
    'information_share': 'INFO',
    'finance_share': 'FINANCE',
    'professional_services_share': 'PROF_BUS',
    # 'education_health_share': 'EDU_HEALTH',  # EXCLUDED - often public sector
    'leisure_hospitality_share': 'LEISURE',
    'other_services_share': 'OTHER',
}

# State FIPS to abbreviation mapping
STATE_FIPS = {
    1: 'AL', 2: 'AK', 4: 'AZ', 5: 'AR', 6: 'CA', 8: 'CO', 9: 'CT', 10: 'DE',
    11: 'DC', 12: 'FL', 13: 'GA', 15: 'HI', 16: 'ID', 17: 'IL', 18: 'IN',
    19: 'IA', 20: 'KS', 21: 'KY', 22: 'LA', 23: 'ME', 24: 'MD', 25: 'MA',
    26: 'MI', 27: 'MN', 28: 'MS', 29: 'MO', 30: 'MT', 31: 'NE', 32: 'NV',
    33: 'NH', 34: 'NJ', 35: 'NM', 36: 'NY', 37: 'NC', 38: 'ND', 39: 'OH',
    40: 'OK', 41: 'OR', 42: 'PA', 44: 'RI', 45: 'SC', 46: 'SD', 47: 'TN',
    48: 'TX', 49: 'UT', 50: 'VT', 51: 'VA', 53: 'WA', 54: 'WV', 55: 'WI',
    56: 'WY', 72: 'PR'
}


def create_tables(cur):
    """Create database tables for industry density analysis."""

    # BLS industry density rates
    cur.execute("""
        DROP TABLE IF EXISTS bls_industry_density CASCADE;
        CREATE TABLE bls_industry_density (
            industry_code VARCHAR(20) PRIMARY KEY,
            industry_name VARCHAR(100),
            union_density_pct DECIMAL(5,2),
            year INTEGER DEFAULT 2024,
            source VARCHAR(50) DEFAULT 'bls_union_membership'
        );
    """)

    # State industry shares
    cur.execute("""
        DROP TABLE IF EXISTS state_industry_shares CASCADE;
        CREATE TABLE state_industry_shares (
            state VARCHAR(2) PRIMARY KEY,
            state_name VARCHAR(50),
            state_fips INTEGER,
            agriculture_mining_share DECIMAL(8,6),
            construction_share DECIMAL(8,6),
            manufacturing_share DECIMAL(8,6),
            wholesale_share DECIMAL(8,6),
            retail_share DECIMAL(8,6),
            transportation_utilities_share DECIMAL(8,6),
            information_share DECIMAL(8,6),
            finance_share DECIMAL(8,6),
            professional_services_share DECIMAL(8,6),
            education_health_share DECIMAL(8,6),
            leisure_hospitality_share DECIMAL(8,6),
            other_services_share DECIMAL(8,6),
            public_admin_share DECIMAL(8,6),
            source VARCHAR(50) DEFAULT 'acs_2025_est'
        );
    """)

    # County industry shares
    cur.execute("""
        DROP TABLE IF EXISTS county_industry_shares CASCADE;
        CREATE TABLE county_industry_shares (
            fips VARCHAR(5) PRIMARY KEY,
            state VARCHAR(2) NOT NULL,
            county_name VARCHAR(100),
            agriculture_mining_share DECIMAL(8,6),
            construction_share DECIMAL(8,6),
            manufacturing_share DECIMAL(8,6),
            wholesale_share DECIMAL(8,6),
            retail_share DECIMAL(8,6),
            transportation_utilities_share DECIMAL(8,6),
            information_share DECIMAL(8,6),
            finance_share DECIMAL(8,6),
            professional_services_share DECIMAL(8,6),
            education_health_share DECIMAL(8,6),
            leisure_hospitality_share DECIMAL(8,6),
            other_services_share DECIMAL(8,6),
            public_admin_share DECIMAL(8,6),
            source VARCHAR(50) DEFAULT 'acs_2025_est'
        );
    """)

    # State comparison table
    cur.execute("""
        DROP TABLE IF EXISTS state_industry_density_comparison CASCADE;
        CREATE TABLE state_industry_density_comparison (
            state VARCHAR(2) PRIMARY KEY,
            state_name VARCHAR(50),
            -- Industry shares (from state_industry_shares)
            agriculture_mining_share DECIMAL(8,6),
            construction_share DECIMAL(8,6),
            manufacturing_share DECIMAL(8,6),
            wholesale_share DECIMAL(8,6),
            retail_share DECIMAL(8,6),
            transportation_utilities_share DECIMAL(8,6),
            information_share DECIMAL(8,6),
            finance_share DECIMAL(8,6),
            professional_services_share DECIMAL(8,6),
            education_health_share DECIMAL(8,6),
            leisure_hospitality_share DECIMAL(8,6),
            other_services_share DECIMAL(8,6),
            -- Calculations
            expected_private_density DECIMAL(5,2),
            actual_private_density DECIMAL(5,2),
            density_difference DECIMAL(5,2),
            climate_multiplier DECIMAL(5,3),
            interpretation VARCHAR(50)
        );
    """)

    print("Tables created successfully")


def load_bls_rates(cur):
    """Load BLS industry union density rates."""
    for code, (name, rate) in BLS_INDUSTRY_RATES.items():
        cur.execute("""
            INSERT INTO bls_industry_density (industry_code, industry_name, union_density_pct)
            VALUES (%s, %s, %s)
        """, (code, name, rate))

    print(f"Loaded {len(BLS_INDUSTRY_RATES)} BLS industry rates")


def load_state_industry(cur, file_path):
    """Load state industry shares from Excel."""
    df = pd.read_excel(file_path)

    # Rename columns
    df = df.rename(columns=COLUMN_MAP)

    loaded = 0
    for _, row in df.iterrows():
        fips = int(row['FIPS'])

        # Skip Puerto Rico
        if fips == 72:
            continue

        state = STATE_FIPS.get(fips)
        if not state:
            print(f"Warning: Unknown FIPS {fips}")
            continue

        state_name = row['Name']

        cur.execute("""
            INSERT INTO state_industry_shares (
                state, state_name, state_fips,
                agriculture_mining_share, construction_share, manufacturing_share,
                wholesale_share, retail_share, transportation_utilities_share,
                information_share, finance_share, professional_services_share,
                education_health_share, leisure_hospitality_share, other_services_share,
                public_admin_share
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            state, state_name, fips,
            row['agriculture_mining_share'], row['construction_share'], row['manufacturing_share'],
            row['wholesale_share'], row['retail_share'], row['transportation_utilities_share'],
            row['information_share'], row['finance_share'], row['professional_services_share'],
            row['education_health_share'], row['leisure_hospitality_share'], row['other_services_share'],
            row['public_admin_share']
        ))
        loaded += 1

    print(f"Loaded {loaded} state industry records")


def load_county_industry(cur, file_path):
    """Load county industry shares from Excel."""
    df = pd.read_excel(file_path)

    # Rename columns
    df = df.rename(columns=COLUMN_MAP)

    loaded = 0
    skipped_pr = 0

    for _, row in df.iterrows():
        fips = str(row['FIPS']).zfill(5)
        state_fips = int(fips[:2])

        # Skip Puerto Rico
        if state_fips == 72:
            skipped_pr += 1
            continue

        state = STATE_FIPS.get(state_fips)
        if not state:
            print(f"Warning: Unknown state FIPS {state_fips} for county {row['Name']}")
            continue

        county_name = row['Name']

        cur.execute("""
            INSERT INTO county_industry_shares (
                fips, state, county_name,
                agriculture_mining_share, construction_share, manufacturing_share,
                wholesale_share, retail_share, transportation_utilities_share,
                information_share, finance_share, professional_services_share,
                education_health_share, leisure_hospitality_share, other_services_share,
                public_admin_share
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            fips, state, county_name,
            row['agriculture_mining_share'], row['construction_share'], row['manufacturing_share'],
            row['wholesale_share'], row['retail_share'], row['transportation_utilities_share'],
            row['information_share'], row['finance_share'], row['professional_services_share'],
            row['education_health_share'], row['leisure_hospitality_share'], row['other_services_share'],
            row['public_admin_share']
        ))
        loaded += 1

    print(f"Loaded {loaded} county industry records (skipped {skipped_pr} PR)")


def calculate_expected_density(shares: dict, bls_rates: dict) -> float:
    """
    Calculate expected private sector density from industry shares.
    Excludes public administration and renormalizes shares.
    """
    from decimal import Decimal

    # Sum of private sector shares (excluding public admin)
    private_total = sum(float(shares.get(col, 0) or 0) for col in SHARE_TO_RATE.keys())

    if private_total == 0:
        return 5.9  # Fallback to overall private sector density

    expected = 0.0
    for col, rate_code in SHARE_TO_RATE.items():
        share = float(shares.get(col, 0) or 0)
        # Renormalize to exclude public admin
        normalized_share = share / private_total
        rate = float(bls_rates[rate_code])
        expected += normalized_share * rate

    return round(expected, 2)


def calculate_state_comparison(cur):
    """Calculate expected vs actual density for each state."""

    # Get BLS rates
    cur.execute("SELECT industry_code, union_density_pct FROM bls_industry_density")
    bls_rates = {row[0]: float(row[1]) for row in cur.fetchall()}

    # Get actual CPS private density by state
    cur.execute("""
        SELECT state, private_density_pct
        FROM v_state_density_latest
        WHERE private_density_pct IS NOT NULL
    """)
    actual_density = {row[0]: float(row[1]) for row in cur.fetchall()}

    # Get state industry shares
    cur.execute("SELECT * FROM state_industry_shares")
    columns = [desc[0] for desc in cur.description]

    for row in cur.fetchall():
        state_data = dict(zip(columns, row))
        state = state_data['state']
        state_name = state_data['state_name']

        # Calculate expected density
        expected = calculate_expected_density(state_data, bls_rates)
        actual = actual_density.get(state)

        if actual is None:
            print(f"Warning: No actual density for {state}")
            continue

        # Calculate climate multiplier and interpretation
        if expected > 0:
            multiplier = round(actual / expected, 3)
        else:
            multiplier = 1.0

        difference = round(actual - expected, 2)

        if multiplier >= 1.5:
            interpretation = 'STRONG'
        elif multiplier >= 1.0:
            interpretation = 'ABOVE_AVERAGE'
        elif multiplier >= 0.5:
            interpretation = 'BELOW_AVERAGE'
        else:
            interpretation = 'WEAK'

        cur.execute("""
            INSERT INTO state_industry_density_comparison (
                state, state_name,
                agriculture_mining_share, construction_share, manufacturing_share,
                wholesale_share, retail_share, transportation_utilities_share,
                information_share, finance_share, professional_services_share,
                education_health_share, leisure_hospitality_share, other_services_share,
                expected_private_density, actual_private_density,
                density_difference, climate_multiplier, interpretation
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            state, state_name,
            state_data['agriculture_mining_share'], state_data['construction_share'],
            state_data['manufacturing_share'], state_data['wholesale_share'],
            state_data['retail_share'], state_data['transportation_utilities_share'],
            state_data['information_share'], state_data['finance_share'],
            state_data['professional_services_share'], state_data['education_health_share'],
            state_data['leisure_hospitality_share'], state_data['other_services_share'],
            expected, actual, difference, multiplier, interpretation
        ))

    # Print summary
    cur.execute("""
        SELECT interpretation, COUNT(*),
               ROUND(AVG(climate_multiplier), 2) as avg_mult
        FROM state_industry_density_comparison
        GROUP BY interpretation
        ORDER BY avg_mult DESC
    """)
    print("\nState Climate Distribution:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} states (avg multiplier: {row[2]})")


def update_county_density_estimates(cur):
    """Update county private density using industry-weighted method."""

    # Get BLS rates
    cur.execute("SELECT industry_code, union_density_pct FROM bls_industry_density")
    bls_rates = {row[0]: float(row[1]) for row in cur.fetchall()}

    # Get state climate multipliers
    cur.execute("SELECT state, climate_multiplier FROM state_industry_density_comparison")
    state_multipliers = {row[0]: float(row[1]) for row in cur.fetchall()}

    # Add new columns if they don't exist
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'county_union_density_estimates'
                          AND column_name = 'industry_expected_private') THEN
                ALTER TABLE county_union_density_estimates
                ADD COLUMN industry_expected_private DECIMAL(5,2),
                ADD COLUMN state_climate_multiplier DECIMAL(5,3),
                ADD COLUMN industry_adjusted_private DECIMAL(5,2);
            END IF;
        END $$;
    """)

    # Get county industry shares
    cur.execute("SELECT * FROM county_industry_shares")
    columns = [desc[0] for desc in cur.description]

    updated = 0
    for row in cur.fetchall():
        county_data = dict(zip(columns, row))
        fips = county_data['fips']
        state = county_data['state']

        # Calculate expected private density from county industry mix
        expected = calculate_expected_density(county_data, bls_rates)

        # Apply state climate multiplier
        multiplier = state_multipliers.get(state, 1.0)
        adjusted_private = round(expected * multiplier, 2)

        # Update county estimates
        cur.execute("""
            UPDATE county_union_density_estimates
            SET industry_expected_private = %s,
                state_climate_multiplier = %s,
                industry_adjusted_private = %s,
                estimated_private_density = %s
            WHERE fips = %s
        """, (expected, multiplier, adjusted_private, adjusted_private, fips))

        updated += cur.rowcount

    print(f"Updated {updated} county private density estimates")

    # Recalculate total density using existing state rates in the table
    cur.execute("""
        UPDATE county_union_density_estimates c
        SET estimated_total_density = ROUND(
            COALESCE(private_share, 0) / 100.0 * COALESCE(industry_adjusted_private, estimated_private_density, 5.9) +
            COALESCE(federal_share, 0) / 100.0 * COALESCE(state_federal_rate, 23.0) +
            COALESCE(state_share, 0) / 100.0 * COALESCE(state_state_rate, 28.0) +
            COALESCE(local_share, 0) / 100.0 * COALESCE(state_local_rate, 41.0)
        , 1)
        WHERE industry_adjusted_private IS NOT NULL
    """)

    print("Recalculated total density for all counties")


def print_results(cur):
    """Print summary results."""

    print("\n" + "="*60)
    print("STATE INDUSTRY DENSITY COMPARISON")
    print("="*60)

    # Top 10 strongest union states
    print("\nTop 10 Strongest Union Culture (Actual > Expected):")
    cur.execute("""
        SELECT state, state_name, expected_private_density,
               actual_private_density, climate_multiplier
        FROM state_industry_density_comparison
        ORDER BY climate_multiplier DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row[0]} {row[1]:20} Expected: {row[2]:5.1f}%  Actual: {row[3]:5.1f}%  Mult: {row[4]:.2f}x")

    # Bottom 10 weakest union states
    print("\nBottom 10 Weakest Union Culture (Actual < Expected):")
    cur.execute("""
        SELECT state, state_name, expected_private_density,
               actual_private_density, climate_multiplier
        FROM state_industry_density_comparison
        ORDER BY climate_multiplier ASC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row[0]} {row[1]:20} Expected: {row[2]:5.1f}%  Actual: {row[3]:5.1f}%  Mult: {row[4]:.2f}x")

    # County summary
    print("\n" + "="*60)
    print("COUNTY DENSITY SUMMARY (INDUSTRY-ADJUSTED)")
    print("="*60)

    cur.execute("""
        SELECT
            COUNT(*) as counties,
            ROUND(AVG(industry_expected_private), 2) as avg_expected,
            ROUND(AVG(industry_adjusted_private), 2) as avg_adjusted,
            ROUND(MIN(industry_adjusted_private), 2) as min_adjusted,
            ROUND(MAX(industry_adjusted_private), 2) as max_adjusted
        FROM county_union_density_estimates
        WHERE industry_adjusted_private IS NOT NULL
    """)
    row = cur.fetchone()
    print(f"Counties with industry adjustment: {row[0]}")
    print(f"Average expected private density: {row[1]}%")
    print(f"Average adjusted private density: {row[2]}%")
    print(f"Range: {row[3]}% - {row[4]}%")

    # Top counties by adjusted private density
    print("\nTop 10 Counties by Adjusted Private Density:")
    cur.execute("""
        SELECT c.fips, c.county_name, c.state,
               c.industry_expected_private,
               c.state_climate_multiplier,
               c.industry_adjusted_private
        FROM county_union_density_estimates c
        WHERE c.industry_adjusted_private IS NOT NULL
        ORDER BY c.industry_adjusted_private DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row[0]} {row[1]:30} {row[2]} Expected: {row[3]:5.1f}%  x{row[4]:.2f} = {row[5]:5.1f}%")


def main():
    state_file = r'C:\Users\jakew\Downloads\state industry_New Project 6_Ranking_2026-02-05_11-47-33.xlsx'
    county_file = r'C:\Users\jakew\Downloads\county industry_New Project 6_Ranking_2026-02-05_11-46-52.xlsx'

    cur = conn.cursor()

    try:
        print("Step 1: Creating tables...")
        create_tables(cur)
        conn.commit()

        print("\nStep 2: Loading BLS industry rates...")
        load_bls_rates(cur)
        conn.commit()

        print("\nStep 3: Loading state industry shares...")
        load_state_industry(cur, state_file)
        conn.commit()

        print("\nStep 4: Loading county industry shares...")
        load_county_industry(cur, county_file)
        conn.commit()

        print("\nStep 5: Calculating state expected vs actual density...")
        calculate_state_comparison(cur)
        conn.commit()

        print("\nStep 6: Updating county density estimates...")
        update_county_density_estimates(cur)
        conn.commit()

        print_results(cur)

        print("\n[OK] All steps completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
