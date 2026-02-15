import psycopg2, os
from dotenv import load_dotenv

from db_config import get_connection
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

conn = get_connection()
cur = conn.cursor()

def run_query(label, sql, fetch_all=True):
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")
    try:
        cur.execute(sql)
        if cur.description and fetch_all:
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            if not rows:
                print("  (no rows)")
                return rows
            # Calculate column widths
            col_widths = []
            for i, c in enumerate(cols):
                max_w = len(str(c))
                for r in rows:
                    val = str(r[i]) if r[i] is not None else "NULL"
                    max_w = max(max_w, min(len(val), 120))
                col_widths.append(min(max_w, 120))
            # Header
            header = " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(cols))
            print(f"  {header}")
            print(f"  {'-' * len(header)}")
            for r in rows:
                line = " | ".join(
                    (str(r[i]) if r[i] is not None else "NULL").ljust(col_widths[i])[:120]
                    for i in range(len(cols))
                )
                print(f"  {line}")
            print(f"  ({len(rows)} rows)")
            return rows
    except Exception as e:
        print(f"  ERROR: {e}")
        conn.rollback()
        return []

# 1. What's in naics_detailed on F7?
run_query(
    "1. naics_detailed + naics_source distribution on f7_employers_deduped",
    """SELECT naics_detailed, naics_source, COUNT(*)
       FROM f7_employers_deduped
       WHERE naics_detailed IS NOT NULL
       GROUP BY naics_detailed, naics_source
       ORDER BY COUNT(*) DESC
       LIMIT 30"""
)

# 2. How many F7 have naics_detailed vs just naics?
run_query(
    "2. naics vs naics_detailed coverage (excluding exclude_from_counts)",
    """SELECT
         COUNT(*) as total,
         COUNT(naics) as has_naics,
         COUNT(naics_detailed) as has_naics_detailed,
         COUNT(CASE WHEN LENGTH(naics_detailed) >= 4 THEN 1 END) as has_4digit_plus,
         COUNT(CASE WHEN LENGTH(naics_detailed) >= 6 THEN 1 END) as has_6digit
       FROM f7_employers_deduped
       WHERE exclude_from_counts IS NOT TRUE"""
)

# 3. Sample a sector organizing target view
run_query(
    "3a. Columns of v_healthcare_hospitals_organizing_targets",
    """SELECT column_name, data_type FROM information_schema.columns
       WHERE table_name = 'v_healthcare_hospitals_organizing_targets'
       ORDER BY ordinal_position"""
)

run_query(
    "3b. Sample rows from v_healthcare_hospitals_organizing_targets (LIMIT 3)",
    """SELECT * FROM v_healthcare_hospitals_organizing_targets LIMIT 3"""
)

# 4. View definition
print(f"\n{'='*80}")
print(f"  4. View definition: v_healthcare_hospitals_organizing_targets")
print(f"{'='*80}")
try:
    cur.execute("SELECT pg_get_viewdef('v_healthcare_hospitals_organizing_targets'::regclass, true)")
    row = cur.fetchone()
    if row:
        print(row[0])
except Exception as e:
    print(f"  ERROR: {e}")
    conn.rollback()

# 5a. f7_industry_scores
run_query(
    "5a. Columns of f7_industry_scores",
    """SELECT column_name, data_type FROM information_schema.columns
       WHERE table_name = 'f7_industry_scores'
       ORDER BY ordinal_position"""
)

run_query(
    "5b. Sample rows from f7_industry_scores (LIMIT 5)",
    """SELECT * FROM f7_industry_scores LIMIT 5"""
)

run_query(
    "5c. Count of f7_industry_scores",
    """SELECT COUNT(*) FROM f7_industry_scores"""
)

# 5b. f7_federal_scores
run_query(
    "5d. Columns of f7_federal_scores",
    """SELECT column_name, data_type FROM information_schema.columns
       WHERE table_name = 'f7_federal_scores'
       ORDER BY ordinal_position"""
)

run_query(
    "5e. Sample rows from f7_federal_scores (LIMIT 5)",
    """SELECT * FROM f7_federal_scores LIMIT 5"""
)

run_query(
    "5f. Count of f7_federal_scores",
    """SELECT COUNT(*) FROM f7_federal_scores"""
)

cur.close()
conn.close()
print("\nDone.")
