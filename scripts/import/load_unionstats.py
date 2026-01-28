"""
Load UnionStats State Density and Industry Density data into PostgreSQL
Database: olms_multiyear
"""

import os
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import time
import glob

# Configuration
PG_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

STATE_DIR = r'C:\Users\jakew\Downloads\labor-data-project\data\unionstats\state'
INDUSTRY_FILES = [
    r'C:\Users\jakew\Downloads\ind_2024.xlsx',
    # Add more years here if available
]

def get_pg_connection():
    return psycopg2.connect(**PG_CONFIG)

def load_state_density():
    """Load all state density files (1983-2024)"""
    print("\n" + "="*60)
    print("Loading State Union Density Data...")
    print("="*60)
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    # Find all state files
    state_files = glob.glob(os.path.join(STATE_DIR, 'state_*.xlsx'))
    print(f"Found {len(state_files)} state files")
    
    total_rows = 0
    
    for filepath in sorted(state_files):
        filename = os.path.basename(filepath)
        # Extract year from filename (handle "state_2024 (1).xlsx" format)
        year_str = filename.replace('state_', '').replace('.xlsx', '').replace(' (1)', '')
        try:
            year = int(year_str)
        except ValueError:
            print(f"  Skipping {filename} - can't parse year")
            continue
        
        try:
            # Read Excel file, skip header rows
            df = pd.read_excel(filepath, sheet_name=0, header=2)
            
            # Rename columns to standard names
            df.columns = ['state_census_code', 'state', 'sector', 'observations', 
                         'employment_thousands', 'members_thousands', 'covered_thousands',
                         'pct_members', 'pct_covered'] + list(df.columns[9:])
            
            # Keep only the columns we need
            df = df[['state_census_code', 'state', 'sector', 'observations',
                    'employment_thousands', 'members_thousands', 'covered_thousands',
                    'pct_members', 'pct_covered']].copy()
            
            # Drop rows where state is null
            df = df.dropna(subset=['state'])
            
            # Add year column
            df['year'] = year
            
            # Insert into PostgreSQL
            data = []
            for _, row in df.iterrows():
                data.append((
                    year,
                    int(row['state_census_code']) if pd.notna(row['state_census_code']) else None,
                    str(row['state']),
                    str(row['sector']),
                    int(row['observations']) if pd.notna(row['observations']) else None,
                    float(row['employment_thousands']) if pd.notna(row['employment_thousands']) else None,
                    float(row['members_thousands']) if pd.notna(row['members_thousands']) else None,
                    float(row['covered_thousands']) if pd.notna(row['covered_thousands']) else None,
                    float(row['pct_members']) if pd.notna(row['pct_members']) else None,
                    float(row['pct_covered']) if pd.notna(row['pct_covered']) else None
                ))
            
            insert_sql = """
                INSERT INTO unionstats_state (
                    year, state_census_code, state, sector, observations,
                    employment_thousands, members_thousands, covered_thousands,
                    pct_members, pct_covered
                ) VALUES %s
            """
            
            execute_values(pg_cursor, insert_sql, data)
            pg_conn.commit()
            
            total_rows += len(data)
            print(f"  {year}: {len(data)} rows loaded")
            
        except Exception as e:
            print(f"  ERROR loading {filename}: {e}")
            continue
    
    print(f"✓ State density loaded: {total_rows:,} total rows")
    pg_conn.close()
    return total_rows

def load_industry_density():
    """Load industry density files"""
    print("\n" + "="*60)
    print("Loading Industry Union Density Data...")
    print("="*60)
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    total_rows = 0
    
    for filepath in INDUSTRY_FILES:
        if not os.path.exists(filepath):
            print(f"  File not found: {filepath}")
            continue
            
        filename = os.path.basename(filepath)
        # Extract year from filename (e.g., "ind_2024.xlsx")
        year_str = filename.replace('ind_', '').replace('.xlsx', '').replace(' (1)', '')
        try:
            year = int(year_str)
        except ValueError:
            print(f"  Skipping {filename} - can't parse year")
            continue
        
        try:
            # Read Excel file, skip header rows
            df = pd.read_excel(filepath, sheet_name=0, header=2)
            
            # Rename columns
            df.columns = ['cic_code', 'industry', 'observations',
                         'employment_thousands', 'members_thousands', 'covered_thousands',
                         'pct_members', 'pct_covered'] + list(df.columns[8:])
            
            # Keep only the columns we need
            df = df[['cic_code', 'industry', 'observations',
                    'employment_thousands', 'members_thousands', 'covered_thousands',
                    'pct_members', 'pct_covered']].copy()
            
            # Drop rows where industry is null
            df = df.dropna(subset=['industry'])
            
            # Insert into PostgreSQL
            data = []
            for _, row in df.iterrows():
                # Determine if this is a sector header (CIC is null and industry is all caps)
                is_header = pd.isna(row['cic_code']) and str(row['industry']).isupper()
                
                data.append((
                    year,
                    int(row['cic_code']) if pd.notna(row['cic_code']) else None,
                    str(row['industry']),
                    int(row['observations']) if pd.notna(row['observations']) else None,
                    float(row['employment_thousands']) if pd.notna(row['employment_thousands']) else None,
                    float(row['members_thousands']) if pd.notna(row['members_thousands']) else None,
                    float(row['covered_thousands']) if pd.notna(row['covered_thousands']) else None,
                    float(row['pct_members']) if pd.notna(row['pct_members']) else None,
                    float(row['pct_covered']) if pd.notna(row['pct_covered']) else None,
                    is_header
                ))
            
            insert_sql = """
                INSERT INTO unionstats_industry (
                    year, cic_code, industry, observations,
                    employment_thousands, members_thousands, covered_thousands,
                    pct_members, pct_covered, is_sector_header
                ) VALUES %s
            """
            
            execute_values(pg_cursor, insert_sql, data)
            pg_conn.commit()
            
            total_rows += len(data)
            print(f"  {year}: {len(data)} rows loaded")
            
        except Exception as e:
            print(f"  ERROR loading {filename}: {e}")
            continue
    
    print(f"✓ Industry density loaded: {total_rows:,} total rows")
    pg_conn.close()
    return total_rows

def verify_load():
    """Verify data was loaded correctly"""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)
    
    pg_conn = get_pg_connection()
    pg_cursor = pg_conn.cursor()
    
    # State data
    pg_cursor.execute("SELECT COUNT(*) FROM unionstats_state")
    state_count = pg_cursor.fetchone()[0]
    
    pg_cursor.execute("SELECT MIN(year), MAX(year), COUNT(DISTINCT year) FROM unionstats_state")
    state_years = pg_cursor.fetchone()
    
    pg_cursor.execute("SELECT COUNT(DISTINCT state) FROM unionstats_state")
    state_states = pg_cursor.fetchone()[0]
    
    print(f"  unionstats_state: {state_count:,} rows")
    print(f"    Years: {state_years[0]} to {state_years[1]} ({state_years[2]} years)")
    print(f"    States: {state_states}")
    
    # Industry data
    pg_cursor.execute("SELECT COUNT(*) FROM unionstats_industry")
    ind_count = pg_cursor.fetchone()[0]
    
    if ind_count > 0:
        pg_cursor.execute("SELECT MIN(year), MAX(year), COUNT(DISTINCT year) FROM unionstats_industry")
        ind_years = pg_cursor.fetchone()
        
        pg_cursor.execute("SELECT COUNT(DISTINCT cic_code) FROM unionstats_industry WHERE cic_code IS NOT NULL")
        ind_codes = pg_cursor.fetchone()[0]
        
        print(f"  unionstats_industry: {ind_count:,} rows")
        print(f"    Years: {ind_years[0]} to {ind_years[1]} ({ind_years[2]} years)")
        print(f"    CIC codes: {ind_codes}")
    else:
        print(f"  unionstats_industry: {ind_count} rows")
    
    pg_conn.close()

def show_sample_queries():
    """Show useful sample queries"""
    print("\n" + "="*60)
    print("SAMPLE QUERIES")
    print("="*60)
    print("""
-- State density trends over time (New York)
SELECT year, sector, pct_members, pct_covered, employment_thousands
FROM unionstats_state
WHERE state = 'New York' AND sector = 'Total'
ORDER BY year;

-- Compare states in 2024
SELECT state, pct_members, members_thousands, employment_thousands
FROM unionstats_state
WHERE year = 2024 AND sector = 'Total'
ORDER BY pct_members DESC
LIMIT 10;

-- Industry density in 2024 (highest density)
SELECT industry, pct_members, members_thousands, employment_thousands
FROM unionstats_industry
WHERE year = 2024 AND cic_code IS NOT NULL
ORDER BY pct_members DESC
LIMIT 15;

-- Union density by sector headers
SELECT industry, pct_members, employment_thousands
FROM unionstats_industry
WHERE year = 2024 AND is_sector_header = true
ORDER BY pct_members DESC;
""")

if __name__ == "__main__":
    print("="*60)
    print("UNIONSTATS DATA LOADER")
    print("="*60)
    print(f"Target database: {PG_CONFIG['database']}")
    print(f"State data: {STATE_DIR}")
    print(f"Industry files: {len(INDUSTRY_FILES)}")
    
    start = time.time()
    
    try:
        state_rows = load_state_density()
        ind_rows = load_industry_density()
        verify_load()
        show_sample_queries()
        
        elapsed = time.time() - start
        print("\n" + "="*60)
        print(f"✓ ALL DATA LOADED SUCCESSFULLY in {elapsed:.1f}s")
        print(f"  Total rows: {state_rows + ind_rows:,}")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
