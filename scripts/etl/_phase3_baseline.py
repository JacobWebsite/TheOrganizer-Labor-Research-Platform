import os
from db_config import get_connection
"""Phase 3 baseline stats - what QCEW and USASpending could improve."""
import psycopg2

conn = get_connection()
cur = conn.cursor()

# NAICS gap analysis
print("=== F7 NAICS GAPS ===")
cur.execute("""
    SELECT naics_source, COUNT(*)
    FROM f7_employers_deduped
    GROUP BY naics_source
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print(f"  {row[0] or 'NULL'}: {row[1]:,}")

cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NULL OR naics = ''")
print(f"\n  No NAICS at all: {cur.fetchone()[0]:,}")

cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE naics_source = 'NONE'")
print(f"  naics_source = NONE: {cur.fetchone()[0]:,}")

# Government contract scoring
print("\n=== GOVERNMENT CONTRACT SCORING ===")
# Check if govt contract tables exist
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_name LIKE '%contract%' OR table_name LIKE '%govt%' OR table_name LIKE '%federal%'
    ORDER BY table_name
""")
tables = cur.fetchall()
if tables:
    for t in tables:
        print(f"  Table: {t[0]}")
else:
    print("  No contract-related tables found")

# Check scoring views
cur.execute("""
    SELECT table_name FROM information_schema.views
    WHERE table_name LIKE '%contract%' OR table_name LIKE '%score%'
    ORDER BY table_name
""")
views = cur.fetchall()
if views:
    print("\n  Contract/Score views:")
    for v in views:
        print(f"    {v[0]}")

# Check if there's existing contract data
for tbl in ['ny_state_contracts', 'nyc_contracts']:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"\n  {tbl}: {cur.fetchone()[0]:,} rows")
    except Exception:
        conn.rollback()

# Check mergent for existing contract data
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE ny_state_contracts > 0) as has_ny_contracts,
        COUNT(*) FILTER (WHERE ny_state_contract_value > 0) as has_ny_value
    FROM mergent_employers
""")
r = cur.fetchone()
print(f"\n  Mergent with NY state contracts: {r[0]:,}")
print(f"  Mergent with NY contract value: {r[1]:,}")

# Crosswalk current state for reference
print("\n=== CROSSWALK CURRENT STATE ===")
cur.execute('SELECT match_tier, COUNT(*) FROM corporate_identifier_crosswalk GROUP BY 1 ORDER BY 2 DESC')
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,}")
cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk')
print(f"  TOTAL: {cur.fetchone()[0]:,}")

# How many F7 employers have EIN through the crosswalk?
cur.execute("""
    SELECT COUNT(DISTINCT f7_employer_id)
    FROM corporate_identifier_crosswalk
    WHERE f7_employer_id IS NOT NULL AND ein IS NOT NULL
""")
print(f"\n  F7 employers with EIN via crosswalk: {cur.fetchone()[0]:,}")

conn.close()
