import os
from db_config import get_connection
"""Create OSHA schema tables in PostgreSQL"""
import psycopg2

conn = get_connection()
conn.autocommit = True
cur = conn.cursor()

print("Creating OSHA tables...")

# Create tables one by one
tables = [
    # Core establishment data
    """
    CREATE TABLE IF NOT EXISTS osha_establishments (
        establishment_id VARCHAR(32) PRIMARY KEY,
        estab_name TEXT NOT NULL,
        site_address TEXT,
        site_city VARCHAR(100),
        site_state VARCHAR(2),
        site_zip VARCHAR(10),
        naics_code VARCHAR(10),
        sic_code VARCHAR(10),
        union_status VARCHAR(1),
        employee_count INTEGER,
        first_inspection_date DATE,
        last_inspection_date DATE,
        total_inspections INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    
    # Aggregated violations by type
    """
    CREATE TABLE IF NOT EXISTS osha_violation_summary (
        id SERIAL PRIMARY KEY,
        establishment_id VARCHAR(32) REFERENCES osha_establishments(establishment_id),
        violation_type VARCHAR(1),
        violation_count INTEGER,
        total_penalties NUMERIC(15,2),
        first_violation_date DATE,
        last_violation_date DATE
    )
    """,
    
    # Detailed violations (2012+)
    """
    CREATE TABLE IF NOT EXISTS osha_violations_detail (
        id SERIAL PRIMARY KEY,
        activity_nr BIGINT,
        establishment_id VARCHAR(32) REFERENCES osha_establishments(establishment_id),
        violation_type VARCHAR(1),
        issuance_date DATE,
        current_penalty NUMERIC(12,2),
        initial_penalty NUMERIC(12,2),
        standard VARCHAR(50),
        viol_desc TEXT
    )
    """,
    
    # Fatalities/injuries
    """
    CREATE TABLE IF NOT EXISTS osha_accidents (
        id SERIAL PRIMARY KEY,
        summary_nr BIGINT,
        establishment_id VARCHAR(32) REFERENCES osha_establishments(establishment_id),
        event_date DATE,
        is_fatality BOOLEAN,
        hospitalized INTEGER,
        amputation INTEGER,
        injury_count INTEGER,
        event_description TEXT
    )
    """,
    
    # Link to F-7 employers
    """
    CREATE TABLE IF NOT EXISTS osha_f7_matches (
        id SERIAL PRIMARY KEY,
        establishment_id VARCHAR(32) REFERENCES osha_establishments(establishment_id),
        f7_employer_id VARCHAR(32),
        match_method VARCHAR(20),
        match_confidence NUMERIC(3,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
]

for i, sql in enumerate(tables, 1):
    try:
        cur.execute(sql)
        table_name = sql.split('EXISTS')[1].split('(')[0].strip()
        print(f"  {i}. Created: {table_name}")
    except Exception as e:
        print(f"  {i}. Error: {e}")

print("\nCreating indexes...")

indexes = [
    "CREATE INDEX IF NOT EXISTS idx_osha_est_name ON osha_establishments(estab_name)",
    "CREATE INDEX IF NOT EXISTS idx_osha_est_state ON osha_establishments(site_state)",
    "CREATE INDEX IF NOT EXISTS idx_osha_est_naics ON osha_establishments(naics_code)",
    "CREATE INDEX IF NOT EXISTS idx_osha_est_union ON osha_establishments(union_status)",
    "CREATE INDEX IF NOT EXISTS idx_osha_est_last_insp ON osha_establishments(last_inspection_date)",
    "CREATE INDEX IF NOT EXISTS idx_osha_viol_est ON osha_violation_summary(establishment_id)",
    "CREATE INDEX IF NOT EXISTS idx_osha_viol_type ON osha_violation_summary(violation_type)",
    "CREATE INDEX IF NOT EXISTS idx_osha_detail_est ON osha_violations_detail(establishment_id)",
    "CREATE INDEX IF NOT EXISTS idx_osha_detail_activity ON osha_violations_detail(activity_nr)",
    "CREATE INDEX IF NOT EXISTS idx_osha_detail_date ON osha_violations_detail(issuance_date)",
    "CREATE INDEX IF NOT EXISTS idx_osha_acc_est ON osha_accidents(establishment_id)",
    "CREATE INDEX IF NOT EXISTS idx_osha_acc_fatal ON osha_accidents(is_fatality)",
    "CREATE INDEX IF NOT EXISTS idx_osha_f7_est ON osha_f7_matches(establishment_id)",
    "CREATE INDEX IF NOT EXISTS idx_osha_f7_emp ON osha_f7_matches(f7_employer_id)"
]

for idx_sql in indexes:
    try:
        cur.execute(idx_sql)
        idx_name = idx_sql.split('EXISTS')[1].split(' ON')[0].strip()
        print(f"  ✓ {idx_name}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

print("\nVerifying tables...")
cur.execute("""
    SELECT table_name, 
           (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as columns
    FROM information_schema.tables t
    WHERE table_schema = 'public' 
    AND table_name LIKE 'osha_%'
    ORDER BY table_name
""")

print("\n" + "="*50)
print("OSHA SCHEMA CREATED SUCCESSFULLY")
print("="*50)
for row in cur.fetchall():
    print(f"  ✓ {row[0]} ({row[1]} columns)")

cur.close()
conn.close()
print("\nPhase 1 complete! Ready for Phase 2 (Extract Establishments)")
