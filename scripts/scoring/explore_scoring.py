"""Explore current scoring infrastructure in olms_multiyear."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# 1. F7 employer columns
print("=" * 80)
print("1. F7_EMPLOYERS_DEDUPED COLUMNS")
print("=" * 80)
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    ORDER BY ordinal_position
""")
rows = cur.fetchall()
for r in rows:
    print(f"  {r[0]:40s} {r[1]}")
print(f"  Total columns: {len(rows)}")

# 2. Mergent employer columns
print("\n" + "=" * 80)
print("2. MERGENT_EMPLOYERS COLUMNS")
print("=" * 80)
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'mergent_employers'
    ORDER BY ordinal_position
""")
rows = cur.fetchall()
for r in rows:
    print(f"  {r[0]:40s} {r[1]}")
print(f"  Total columns: {len(rows)}")

# 3. Sample F7 employer with OSHA match
print("\n" + "=" * 80)
print("3. SAMPLE F7 EMPLOYERS WITH OSHA MATCHES")
print("=" * 80)
try:
    cur.execute("""
        SELECT f.employer_id, f.employer_name, f.city, f.state, f.naics,
               m.establishment_id, m.match_tier, m.match_score
        FROM f7_employers_deduped f
        JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
        LIMIT 5
    """)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    print(f"  Columns: {cols}")
    for r in rows:
        print(f"  {r}")
    if not rows:
        print("  (no rows)")
except Exception as e:
    print(f"  ERROR: {e}")
    conn.rollback()

# 4. Count F7 employers with OSHA matches
print("\n" + "=" * 80)
print("4. F7 EMPLOYERS WITH OSHA MATCHES (COUNT)")
print("=" * 80)
try:
    cur.execute("SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches")
    print(f"  Count: {cur.fetchone()[0]}")
except Exception as e:
    print(f"  ERROR: {e}")
    conn.rollback()

# 5. v_naics_union_density view
print("\n" + "=" * 80)
print("5. V_NAICS_UNION_DENSITY VIEW")
print("=" * 80)
cur.execute("""
    SELECT COUNT(*) FROM information_schema.views
    WHERE table_name = 'v_naics_union_density'
""")
exists = cur.fetchone()[0]
print(f"  View exists: {bool(exists)}")
if exists:
    try:
        cur.execute("SELECT * FROM v_naics_union_density LIMIT 10")
        cols = [d[0] for d in cur.description]
        print(f"  Columns: {cols}")
        for r in cur.fetchall():
            print(f"  {r}")
    except Exception as e:
        print(f"  ERROR: {e}")
        conn.rollback()
else:
    print("  (view does not exist)")

# 6. epi_state_benchmarks
print("\n" + "=" * 80)
print("6. EPI_STATE_BENCHMARKS")
print("=" * 80)
try:
    cur.execute("SELECT * FROM epi_state_benchmarks LIMIT 5")
    cols = [d[0] for d in cur.description]
    print(f"  Columns: {cols}")
    for r in cur.fetchall():
        print(f"  {r}")
except Exception as e:
    print(f"  ERROR: {e}")
    conn.rollback()

# 7. Existing score columns on F7
print("\n" + "=" * 80)
print("7. SCORE COLUMNS ON F7_EMPLOYERS_DEDUPED")
print("=" * 80)
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    AND column_name LIKE '%%score%%'
""")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  {r[0]}")
else:
    print("  (none found)")

# 8. All tables with score/priority columns
print("\n" + "=" * 80)
print("8. ALL TABLES WITH SCORE/PRIORITY COLUMNS")
print("=" * 80)
cur.execute("""
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE (column_name LIKE '%%score%%' OR column_name LIKE '%%priority%%')
    AND table_schema = 'public'
    ORDER BY table_name, column_name
""")
rows = cur.fetchall()
for r in rows:
    print(f"  {r[0]:45s} {r[1]}")
print(f"  Total: {len(rows)}")

cur.close()
conn.close()
print("\nDone.")
