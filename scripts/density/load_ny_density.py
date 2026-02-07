#!/usr/bin/env python3
"""
Load NY sub-county workforce data and calculate union density estimates.

This script:
1. Loads NY workforce data at county, ZIP, and census tract levels
2. Applies industry-weighted private sector density using 10 BLS industries
3. Auto-calibrates climate multiplier to match CPS statewide private density
4. Calculates public density decomposed by government level
5. Stores results in database tables and exports to CSV

Methodology: Same as national county model (load_industry_density.py) -
10 private industries weighted by BLS rates, excludes edu/health and
public admin to avoid double-counting with public sector estimates.
Climate multiplier auto-derived from CPS target (12.4%).
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
from decimal import Decimal

# Database connection
DB_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

# BLS 2024 industry union density rates (for 10 private industries)
# Excludes education/health and public admin
BLS_RATES = {
    'agriculture_mining': 4.0,
    'construction': 10.3,
    'manufacturing': 7.8,
    'wholesale': 4.6,
    'retail': 4.0,
    'transportation_utilities': 16.2,
    'information': 6.6,
    'finance': 1.3,
    'professional_services': 2.0,
    'leisure_hospitality': 3.0,
    'other_services': 2.7,
}

# NY CPS statewide private sector density target (2025 data)
NY_TARGET_PRIVATE_DENSITY = 12.4

# NY public sector rates (from CPS / estimated)
NY_FEDERAL_RATE = 42.2
NY_STATE_RATE = 46.3
NY_LOCAL_RATE = 63.7

# Will be auto-calibrated at runtime
NY_CLIMATE_MULTIPLIER = None

# Column mappings from Excel files
INDUSTRY_COLS = {
    'agriculture_mining': '% Industry | Agriculture, forestry, fishing and hunting, and mining, 2025 [Estimated]',
    'construction': '% Industry | Construction, 2025 [Estimated]',
    'manufacturing': '% Industry | Manufacturing, 2025 [Estimated]',
    'wholesale': '% Industry | Wholesale trade, 2025 [Estimated]',
    'retail': '% Industry | Retail trade, 2025 [Estimated]',
    'transportation_utilities': '% Industry | Transportation and warehousing, and utilities, 2025 [Estimated]',
    'information': '% Industry | Information, 2025 [Estimated]',
    'finance': '% Industry | Finance and insurance, and real estate, and rental and leasing, 2025 [Estimated]',
    'professional_services': '% Industry | Professional, scientific, and management, and administrative, and waste management services, 2025 [Estimated]',
    'education_health': '% Industry | Educational services, and health care and social assistance, 2025 [Estimated]',
    'leisure_hospitality': '% Industry | Arts, entertainment, and recreation, and accommodation and food services, 2025 [Estimated]',
    'other_services': '% Industry | Other services, except public administration, 2025 [Estimated]',
    'public_admin': '% Industry | Public administration, 2025 [Estimated]',
}

CLASS_OF_WORKER_COLS = {
    'private_for_profit': '% Class of Worker | Private for-profit wage and salary workers, 2025 [Estimated]',
    'private_nonprofit': '% Class of Worker | Private not-for-profit wage and salary workers, 2025 [Estimated]',
    'local_govt': '% Class of Worker | Local government workers, 2025 [Estimated]',
    'state_govt': '% Class of Worker | State government workers, 2025 [Estimated]',
    'federal_govt': '% Class of Worker | Federal government workers, 2025 [Estimated]',
    'self_employed': '% Class of Worker | Self-employed in own not incorporated business workers, 2025 [Estimated]',
    'unpaid_family': '% Class of Worker | Unpaid family workers, 2025 [Estimated]',
}

# County file uses COUNT for NPO, not percentage
NPO_COUNT_COL = '# Class of Worker | Private not-for-profit wage and salary workers, 2025 [Estimated]'


def load_excel_data(filepath, level='tract'):
    """Load workforce data from Excel file."""
    df = pd.read_excel(filepath)

    # Rename columns for easier handling
    df = df.rename(columns={'FIPS': 'fips', 'Name': 'name'})

    # Convert FIPS to string and pad appropriately
    if level == 'county':
        df['fips'] = df['fips'].astype(str).str.zfill(5)
    elif level == 'zip':
        df['fips'] = df['fips'].astype(str).str.zfill(5)
    elif level == 'tract':
        df['fips'] = df['fips'].astype(str).str.zfill(11)

    return df


def normalize_npo_share(df, level):
    """
    Convert NPO count to percentage for county/ZIP files.
    Tract file already has percentage.
    """
    if level == 'tract':
        # Tract file has the correct column name with %
        return df

    # For county/ZIP, NPO is a count - need to calculate percentage
    # Total employed = sum of all class of worker shares (should be ~1.0)
    # But we need the raw count context

    # The issue is that we have % for all other workers but # for NPO
    # We can back-calculate: total_count = npo_count / npo_share
    # But we don't have npo_share directly

    # Alternative: Use the fact that all shares should sum to 1.0
    # npo_share = 1.0 - (sum of other shares)

    other_shares = ['private_for_profit', 'local_govt', 'state_govt',
                    'federal_govt', 'self_employed', 'unpaid_family']

    npo_share_col = CLASS_OF_WORKER_COLS['private_nonprofit']
    npo_count_col = NPO_COUNT_COL

    if npo_count_col in df.columns:
        # Calculate NPO share as remainder
        total_other = sum(df[CLASS_OF_WORKER_COLS[k]] for k in other_shares)
        df[npo_share_col] = 1.0 - total_other

        # Ensure non-negative
        df[npo_share_col] = df[npo_share_col].clip(lower=0)

        # Store the raw count for reference
        df['npo_count_raw'] = df[npo_count_col]

    return df


def calculate_private_expected(row):
    """
    Calculate expected private density for a single row (before multiplier).
    Uses 10 BLS private industries, renormalized to sum to 1.0.
    Excludes edu/health and public admin (captured in public sector).
    """
    ten_industry_shares = {}
    for ind in BLS_RATES.keys():
        ten_industry_shares[ind] = row[INDUSTRY_COLS[ind]]

    ten_industry_total = sum(ten_industry_shares.values())

    if ten_industry_total > 0:
        return sum(
            (ten_industry_shares[ind] / ten_industry_total) * BLS_RATES[ind]
            for ind in BLS_RATES.keys()
        )
    return 0


def calibrate_multiplier(county_df):
    """
    Auto-calibrate climate multiplier so average county private density = CPS target.

    1. Compute private_expected for all 62 counties (multiplier=1.0)
    2. Take simple average
    3. Multiplier = target / avg_expected
    """
    expected_values = []
    for _, row in county_df.iterrows():
        expected_values.append(calculate_private_expected(row))

    avg_expected = sum(expected_values) / len(expected_values) if expected_values else 1.0
    multiplier = NY_TARGET_PRIVATE_DENSITY / avg_expected if avg_expected > 0 else 1.0

    print(f"  Auto-calibration: avg county expected = {avg_expected:.4f}%")
    print(f"  Target private density = {NY_TARGET_PRIVATE_DENSITY}%")
    print(f"  Derived multiplier = {multiplier:.4f}x")

    return multiplier


def calculate_density_estimates(df, climate_multiplier):
    """
    Calculate union density estimates for each geography.

    Methodology:
    1. Calculate private class total (for-profit + nonprofit)
    2. Calculate government class total (fed + state + local)
    3. Calculate industry-weighted private density (10 BLS industries)
    4. Apply auto-calibrated climate multiplier
    5. Calculate public density with fed/state/local decomposition
    6. Calculate total density
    """
    results = []

    for _, row in df.iterrows():
        # Extract class of worker shares
        private_for_profit = row[CLASS_OF_WORKER_COLS['private_for_profit']]
        private_nonprofit = row[CLASS_OF_WORKER_COLS['private_nonprofit']]
        federal_share = row[CLASS_OF_WORKER_COLS['federal_govt']]
        state_share = row[CLASS_OF_WORKER_COLS['state_govt']]
        local_share = row[CLASS_OF_WORKER_COLS['local_govt']]
        self_employed = row[CLASS_OF_WORKER_COLS['self_employed']]
        unpaid_family = row[CLASS_OF_WORKER_COLS['unpaid_family']]

        # Extract industry shares (kept for reference/output)
        edu_health_share = row[INDUSTRY_COLS['education_health']]
        public_admin_share = row[INDUSTRY_COLS['public_admin']]

        # Step 1: Private class total
        private_class = private_for_profit + private_nonprofit

        # Step 2: Government class total
        govt_class = federal_share + state_share + local_share

        # Step 3: Calculate 10-industry shares (excluding edu/health and public admin)
        ten_industry_shares = {}
        for ind in BLS_RATES.keys():
            ten_industry_shares[ind] = row[INDUSTRY_COLS[ind]]

        ten_industry_total = sum(ten_industry_shares.values())

        # Step 4: Calculate industry-weighted private density
        # Same as national county model: 10 industries, renormalized, times multiplier
        if private_class > 0 and ten_industry_total > 0:
            private_expected = calculate_private_expected(row)
            private_density = private_expected * climate_multiplier
        else:
            private_expected = 0
            private_density = 0

        # Step 5: Calculate public sector density (decomposed by government level)
        federal_density = federal_share * NY_FEDERAL_RATE if federal_share > 0 else 0
        state_density = state_share * NY_STATE_RATE if state_share > 0 else 0
        local_density = local_share * NY_LOCAL_RATE if local_share > 0 else 0

        public_density = federal_density + state_density + local_density

        # Step 6: Calculate total density
        # Private workers contribute: private_class * private_density
        # Public density is already weighted by shares
        # Self-employed and unpaid family contribute 0%
        total_density = (private_class * private_density) + public_density

        # Build result record
        # private_in_public_industries set to 0 (removed from methodology, kept for schema compat)
        result = {
            'fips': row['fips'],
            'name': row['name'],
            # Class of worker inputs
            'private_for_profit_share': round(private_for_profit, 6),
            'private_nonprofit_share': round(private_nonprofit, 6),
            'federal_share': round(federal_share, 6),
            'state_share': round(state_share, 6),
            'local_share': round(local_share, 6),
            'self_employed_share': round(self_employed, 6),
            'unpaid_family_share': round(unpaid_family, 6),
            # Industry shares (key ones)
            'education_health_share': round(edu_health_share, 6),
            'public_admin_share': round(public_admin_share, 6),
            # Calculated adjustments
            'private_class_total': round(private_class, 6),
            'govt_class_total': round(govt_class, 6),
            'private_in_public_industries': 0,  # Removed from methodology
            'ten_industry_total': round(ten_industry_total, 6),
            # Density estimates
            'estimated_private_expected': round(private_expected, 4) if private_expected else None,
            'estimated_private_density': round(private_density, 2),
            'estimated_federal_density': round(federal_density, 4),
            'estimated_state_density': round(state_density, 4),
            'estimated_local_density': round(local_density, 4),
            'estimated_public_density': round(public_density, 2),
            'estimated_total_density': round(total_density, 2),
        }

        results.append(result)

    return pd.DataFrame(results)


def create_tables(conn):
    """Create database tables for NY density estimates."""
    cur = conn.cursor()

    # County table
    cur.execute("""
        DROP TABLE IF EXISTS ny_county_density_estimates CASCADE;
        CREATE TABLE ny_county_density_estimates (
            county_fips VARCHAR(5) PRIMARY KEY,
            county_name VARCHAR(100),

            -- Class of Worker shares
            private_for_profit_share DECIMAL(8,6),
            private_nonprofit_share DECIMAL(8,6),
            federal_share DECIMAL(8,6),
            state_share DECIMAL(8,6),
            local_share DECIMAL(8,6),
            self_employed_share DECIMAL(8,6),
            unpaid_family_share DECIMAL(8,6),

            -- Key industry shares
            education_health_share DECIMAL(8,6),
            public_admin_share DECIMAL(8,6),

            -- Calculated adjustments
            private_class_total DECIMAL(8,6),
            govt_class_total DECIMAL(8,6),
            private_in_public_industries DECIMAL(8,6),
            ten_industry_total DECIMAL(8,6),

            -- Density estimates
            estimated_private_expected DECIMAL(6,4),
            estimated_private_density DECIMAL(6,2),
            estimated_federal_density DECIMAL(6,4),
            estimated_state_density DECIMAL(6,4),
            estimated_local_density DECIMAL(6,4),
            estimated_public_density DECIMAL(6,2),
            estimated_total_density DECIMAL(6,2),

            -- Metadata
            data_source VARCHAR(20) DEFAULT 'county',
            methodology VARCHAR(100) DEFAULT 'industry_weighted_auto_calibrated'
        );
    """)

    # ZIP table
    cur.execute("""
        DROP TABLE IF EXISTS ny_zip_density_estimates CASCADE;
        CREATE TABLE ny_zip_density_estimates (
            zip_code VARCHAR(5) PRIMARY KEY,
            zip_name VARCHAR(150),

            -- Class of Worker shares
            private_for_profit_share DECIMAL(8,6),
            private_nonprofit_share DECIMAL(8,6),
            federal_share DECIMAL(8,6),
            state_share DECIMAL(8,6),
            local_share DECIMAL(8,6),
            self_employed_share DECIMAL(8,6),
            unpaid_family_share DECIMAL(8,6),

            -- Key industry shares
            education_health_share DECIMAL(8,6),
            public_admin_share DECIMAL(8,6),

            -- Calculated adjustments
            private_class_total DECIMAL(8,6),
            govt_class_total DECIMAL(8,6),
            private_in_public_industries DECIMAL(8,6),
            ten_industry_total DECIMAL(8,6),

            -- Density estimates
            estimated_private_expected DECIMAL(6,4),
            estimated_private_density DECIMAL(6,2),
            estimated_federal_density DECIMAL(6,4),
            estimated_state_density DECIMAL(6,4),
            estimated_local_density DECIMAL(6,4),
            estimated_public_density DECIMAL(6,2),
            estimated_total_density DECIMAL(6,2),

            -- Metadata
            data_source VARCHAR(20) DEFAULT 'zip',
            methodology VARCHAR(100) DEFAULT 'industry_weighted_auto_calibrated'
        );
    """)

    # Census tract table
    cur.execute("""
        DROP TABLE IF EXISTS ny_tract_density_estimates CASCADE;
        CREATE TABLE ny_tract_density_estimates (
            tract_fips VARCHAR(11) PRIMARY KEY,
            county_fips VARCHAR(5),
            tract_name VARCHAR(150),

            -- Class of Worker shares
            private_for_profit_share DECIMAL(8,6),
            private_nonprofit_share DECIMAL(8,6),
            federal_share DECIMAL(8,6),
            state_share DECIMAL(8,6),
            local_share DECIMAL(8,6),
            self_employed_share DECIMAL(8,6),
            unpaid_family_share DECIMAL(8,6),

            -- Key industry shares
            education_health_share DECIMAL(8,6),
            public_admin_share DECIMAL(8,6),

            -- Calculated adjustments
            private_class_total DECIMAL(8,6),
            govt_class_total DECIMAL(8,6),
            private_in_public_industries DECIMAL(8,6),
            ten_industry_total DECIMAL(8,6),

            -- Density estimates
            estimated_private_expected DECIMAL(6,4),
            estimated_private_density DECIMAL(6,2),
            estimated_federal_density DECIMAL(6,4),
            estimated_state_density DECIMAL(6,4),
            estimated_local_density DECIMAL(6,4),
            estimated_public_density DECIMAL(6,2),
            estimated_total_density DECIMAL(6,2),

            -- Metadata
            data_source VARCHAR(20) DEFAULT 'tract',
            methodology VARCHAR(100) DEFAULT 'industry_weighted_auto_calibrated'
        );

        CREATE INDEX idx_tract_county ON ny_tract_density_estimates(county_fips);
    """)

    conn.commit()
    cur.close()
    print("Created database tables")


def insert_county_data(conn, df):
    """Insert county density estimates into database."""
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO ny_county_density_estimates (
            county_fips, county_name,
            private_for_profit_share, private_nonprofit_share,
            federal_share, state_share, local_share,
            self_employed_share, unpaid_family_share,
            education_health_share, public_admin_share,
            private_class_total, govt_class_total, private_in_public_industries, ten_industry_total,
            estimated_private_expected, estimated_private_density,
            estimated_federal_density, estimated_state_density, estimated_local_density,
            estimated_public_density, estimated_total_density
        ) VALUES %s
    """

    values = [
        (
            row['fips'], row['name'],
            row['private_for_profit_share'], row['private_nonprofit_share'],
            row['federal_share'], row['state_share'], row['local_share'],
            row['self_employed_share'], row['unpaid_family_share'],
            row['education_health_share'], row['public_admin_share'],
            row['private_class_total'], row['govt_class_total'],
            row['private_in_public_industries'], row['ten_industry_total'],
            row['estimated_private_expected'], row['estimated_private_density'],
            row['estimated_federal_density'], row['estimated_state_density'],
            row['estimated_local_density'], row['estimated_public_density'],
            row['estimated_total_density']
        )
        for _, row in df.iterrows()
    ]

    execute_values(cur, insert_sql, values)
    conn.commit()
    cur.close()
    print(f"Inserted {len(values)} county records")


def insert_zip_data(conn, df):
    """Insert ZIP density estimates into database."""
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO ny_zip_density_estimates (
            zip_code, zip_name,
            private_for_profit_share, private_nonprofit_share,
            federal_share, state_share, local_share,
            self_employed_share, unpaid_family_share,
            education_health_share, public_admin_share,
            private_class_total, govt_class_total, private_in_public_industries, ten_industry_total,
            estimated_private_expected, estimated_private_density,
            estimated_federal_density, estimated_state_density, estimated_local_density,
            estimated_public_density, estimated_total_density
        ) VALUES %s
    """

    values = [
        (
            row['fips'], row['name'],
            row['private_for_profit_share'], row['private_nonprofit_share'],
            row['federal_share'], row['state_share'], row['local_share'],
            row['self_employed_share'], row['unpaid_family_share'],
            row['education_health_share'], row['public_admin_share'],
            row['private_class_total'], row['govt_class_total'],
            row['private_in_public_industries'], row['ten_industry_total'],
            row['estimated_private_expected'], row['estimated_private_density'],
            row['estimated_federal_density'], row['estimated_state_density'],
            row['estimated_local_density'], row['estimated_public_density'],
            row['estimated_total_density']
        )
        for _, row in df.iterrows()
    ]

    execute_values(cur, insert_sql, values)
    conn.commit()
    cur.close()
    print(f"Inserted {len(values)} ZIP records")


def insert_tract_data(conn, df):
    """Insert tract density estimates into database."""
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO ny_tract_density_estimates (
            tract_fips, county_fips, tract_name,
            private_for_profit_share, private_nonprofit_share,
            federal_share, state_share, local_share,
            self_employed_share, unpaid_family_share,
            education_health_share, public_admin_share,
            private_class_total, govt_class_total, private_in_public_industries, ten_industry_total,
            estimated_private_expected, estimated_private_density,
            estimated_federal_density, estimated_state_density, estimated_local_density,
            estimated_public_density, estimated_total_density
        ) VALUES %s
    """

    values = [
        (
            row['fips'], row['fips'][:5], row['name'],
            row['private_for_profit_share'], row['private_nonprofit_share'],
            row['federal_share'], row['state_share'], row['local_share'],
            row['self_employed_share'], row['unpaid_family_share'],
            row['education_health_share'], row['public_admin_share'],
            row['private_class_total'], row['govt_class_total'],
            row['private_in_public_industries'], row['ten_industry_total'],
            row['estimated_private_expected'], row['estimated_private_density'],
            row['estimated_federal_density'], row['estimated_state_density'],
            row['estimated_local_density'], row['estimated_public_density'],
            row['estimated_total_density']
        )
        for _, row in df.iterrows()
    ]

    execute_values(cur, insert_sql, values)
    conn.commit()
    cur.close()
    print(f"Inserted {len(values)} tract records")


def export_csv(df, filepath, level, climate_multiplier):
    """Export density estimates to CSV."""
    # Add methodology note columns
    df['methodology_note'] = 'Industry-weighted (10 BLS industries), auto-calibrated to CPS'
    df['ny_climate_multiplier'] = round(climate_multiplier, 4)
    df['fed_rate_applied'] = NY_FEDERAL_RATE
    df['state_rate_applied'] = NY_STATE_RATE
    df['local_rate_applied'] = NY_LOCAL_RATE

    df.to_csv(filepath, index=False)
    print(f"Exported {len(df)} {level} records to {filepath}")


def main():
    """Main execution function."""
    global NY_CLIMATE_MULTIPLIER

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(base_path, 'data')

    # Connect to database
    conn = psycopg2.connect(**DB_CONFIG)

    # Create tables
    create_tables(conn)

    # Load county data first for calibration
    print("\n=== Loading County Data for Calibration ===")
    county_df = load_excel_data(os.path.join(data_path, 'ny_county_workforce.xlsx'), 'county')
    county_df = normalize_npo_share(county_df, 'county')

    # Auto-calibrate climate multiplier from county data
    NY_CLIMATE_MULTIPLIER = calibrate_multiplier(county_df)

    # Process County data
    print("\n=== Processing County Data ===")
    county_results = calculate_density_estimates(county_df, NY_CLIMATE_MULTIPLIER)
    insert_county_data(conn, county_results)
    export_csv(county_results, os.path.join(data_path, 'ny_county_density.csv'), 'county', NY_CLIMATE_MULTIPLIER)

    # Process ZIP data
    print("\n=== Processing ZIP Data ===")
    zip_df = load_excel_data(os.path.join(data_path, 'ny_zip_workforce.xlsx'), 'zip')
    zip_df = normalize_npo_share(zip_df, 'zip')
    zip_results = calculate_density_estimates(zip_df, NY_CLIMATE_MULTIPLIER)
    insert_zip_data(conn, zip_results)
    export_csv(zip_results, os.path.join(data_path, 'ny_zip_density.csv'), 'zip', NY_CLIMATE_MULTIPLIER)

    # Process Tract data
    print("\n=== Processing Census Tract Data ===")
    tract_df = load_excel_data(os.path.join(data_path, 'ny_tract_workforce.xlsx'), 'tract')
    tract_results = calculate_density_estimates(tract_df, NY_CLIMATE_MULTIPLIER)
    insert_tract_data(conn, tract_results)
    export_csv(tract_results, os.path.join(data_path, 'ny_tract_density.csv'), 'tract', NY_CLIMATE_MULTIPLIER)

    # Print summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Climate multiplier: {NY_CLIMATE_MULTIPLIER:.4f}x (auto-calibrated)")

    print(f"\nCounty ({len(county_results)} records):")
    print(f"  Total density: min={county_results['estimated_total_density'].min():.2f}%, "
          f"max={county_results['estimated_total_density'].max():.2f}%, "
          f"mean={county_results['estimated_total_density'].mean():.2f}%")
    print(f"  Private density: min={county_results['estimated_private_density'].min():.2f}%, "
          f"max={county_results['estimated_private_density'].max():.2f}%, "
          f"mean={county_results['estimated_private_density'].mean():.2f}%")
    print(f"  Public density: min={county_results['estimated_public_density'].min():.2f}%, "
          f"max={county_results['estimated_public_density'].max():.2f}%, "
          f"mean={county_results['estimated_public_density'].mean():.2f}%")

    print(f"\nZIP ({len(zip_results)} records):")
    print(f"  Total density: min={zip_results['estimated_total_density'].min():.2f}%, "
          f"max={zip_results['estimated_total_density'].max():.2f}%, "
          f"mean={zip_results['estimated_total_density'].mean():.2f}%")
    print(f"  Private density: mean={zip_results['estimated_private_density'].mean():.2f}%")

    print(f"\nTract ({len(tract_results)} records):")
    print(f"  Total density: min={tract_results['estimated_total_density'].min():.2f}%, "
          f"max={tract_results['estimated_total_density'].max():.2f}%, "
          f"mean={tract_results['estimated_total_density'].mean():.2f}%")
    print(f"  Private density: mean={tract_results['estimated_private_density'].mean():.2f}%")

    # Top 5 counties by total density
    print("\n=== Top 5 Counties by Total Density ===")
    top_counties = county_results.nlargest(5, 'estimated_total_density')[
        ['name', 'estimated_total_density', 'estimated_private_density', 'estimated_public_density']
    ]
    for _, row in top_counties.iterrows():
        print(f"  {row['name']}: {row['estimated_total_density']:.1f}% total "
              f"({row['estimated_private_density']:.1f}% private, {row['estimated_public_density']:.1f}% public)")

    # NYC boroughs
    print("\n=== NYC Borough Density ===")
    nyc_fips = {'36005': 'Bronx', '36047': 'Kings/Brooklyn', '36061': 'Manhattan',
                '36081': 'Queens', '36085': 'Staten Island'}
    for fips, name in nyc_fips.items():
        borough = county_results[county_results['fips'] == fips]
        if len(borough) > 0:
            r = borough.iloc[0]
            print(f"  {name}: {r['estimated_total_density']:.1f}% total "
                  f"({r['estimated_private_density']:.1f}% private, {r['estimated_public_density']:.1f}% public)")

    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
