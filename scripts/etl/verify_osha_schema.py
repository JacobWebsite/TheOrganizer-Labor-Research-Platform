import os
"""Create indexes and verify OSHA schema"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
conn.autocommit = True
cur = conn.cursor()

print("Creating indexes...")

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
        print(f"  [OK] {idx_name}")
    except Exception as e:
        print(f"  [ERR] {e}")

print("\nVerifying tables...")
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name LIKE 'osha_%'
    ORDER BY table_name
""")

print("\n" + "="*50)
print("OSHA SCHEMA STATUS")
print("="*50)
for row in cur.fetchall():
    # Get column count
    cur.execute(f"SELECT COUNT(*) FROM information_schema.columns WHERE table_name = '{row[0]}'")
    col_count = cur.fetchone()[0]
    print(f"  [OK] {row[0]} ({col_count} columns)")

# Count indexes
cur.execute("""
    SELECT COUNT(*) FROM pg_indexes 
    WHERE tablename LIKE 'osha_%'
""")
idx_count = cur.fetchone()[0]
print(f"\nTotal indexes: {idx_count}")

cur.close()
conn.close()
print("\n" + "="*50)
print("PHASE 1 COMPLETE!")
print("="*50)
