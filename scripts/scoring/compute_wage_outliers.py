"""
Compute QCEW wage outlier flags for employers.

Compares employer wage data (from 990, WHD, PPP, or research) against
QCEW local industry averages (state + NAICS-2). Flags low-wage outliers
and computes a wage_outlier_score (0-10).

Creates/refreshes the table `employer_wage_outliers`.

Run:     py scripts/scoring/compute_wage_outliers.py
Refresh: py scripts/scoring/compute_wage_outliers.py --refresh
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from scripts.scoring._pipeline_lock import pipeline_lock


# Step 1: Aggregate QCEW county data to state + NAICS-2 level
QCEW_STATE_NAICS_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_qcew_state_industry_wages AS
SELECT
    LEFT(area_fips, 2) AS state_fips,
    industry_code AS naics_2,
    year,
    SUM(total_annual_wages) / NULLIF(SUM(annual_avg_emplvl), 0) AS avg_annual_pay,
    SUM(annual_avg_emplvl) AS total_employment,
    COUNT(*) AS county_count
FROM qcew_annual
WHERE own_code = '5'          -- private sector
  AND agglvl_code = '74'      -- county + NAICS 2-digit
  AND annual_avg_emplvl > 0
  AND avg_annual_pay > 0
GROUP BY LEFT(area_fips, 2), industry_code, year
"""

QCEW_INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_qcew_siw_pk ON mv_qcew_state_industry_wages (state_fips, naics_2, year)",
    "CREATE INDEX IF NOT EXISTS idx_mv_qcew_siw_year ON mv_qcew_state_industry_wages (year)",
]

# Step 2: Build employer wage outlier table
OUTLIER_TABLE_SQL = """
DROP TABLE IF EXISTS employer_wage_outliers CASCADE;
CREATE TABLE employer_wage_outliers (
    master_id       BIGINT PRIMARY KEY,
    employer_name   TEXT,
    state           TEXT,
    naics           TEXT,
    naics_2         TEXT,
    -- Employer wage proxy
    wage_source     TEXT,               -- '990', 'whd', 'ppp', 'research'
    employer_annual_pay NUMERIC,        -- estimated annual pay per employee
    -- QCEW benchmark
    qcew_avg_annual_pay NUMERIC,        -- local industry average
    qcew_employment     INTEGER,        -- local industry employment
    -- Comparison
    wage_ratio      NUMERIC,            -- employer / QCEW (1.0 = on par)
    is_low_wage_outlier BOOLEAN DEFAULT FALSE,  -- >20% below
    wage_outlier_score  NUMERIC(4,2),   -- 0-10 (higher = more below average)
    created_at      TIMESTAMP DEFAULT NOW()
)
"""

OUTLIER_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_ewo_state ON employer_wage_outliers (state)",
    "CREATE INDEX IF NOT EXISTS idx_ewo_naics2 ON employer_wage_outliers (naics_2)",
    "CREATE INDEX IF NOT EXISTS idx_ewo_low_wage ON employer_wage_outliers (master_id) WHERE is_low_wage_outlier",
    "CREATE INDEX IF NOT EXISTS idx_ewo_score ON employer_wage_outliers (wage_outlier_score DESC NULLS LAST)",
]

# Step 3: Populate from multiple wage sources, pick best available
POPULATE_SQL = """
WITH
-- State FIPS lookup
fips AS (
    SELECT state_abbr, state_fips FROM state_fips_map
),
-- QCEW benchmarks: latest year, state + NAICS-2
qcew AS (
    SELECT state_fips, naics_2, avg_annual_pay, total_employment
    FROM mv_qcew_state_industry_wages
    WHERE year = (SELECT MAX(year) FROM mv_qcew_state_industry_wages)
),
-- 990 wage proxy: total_expenses / total_employees
-- (expenses approximates labor cost better than revenue)
wage_990 AS (
    SELECT DISTINCT ON (me.master_id)
        me.master_id AS master_id,
        '990' AS wage_source,
        (COALESCE(f.total_expenses, f.total_revenue)::numeric / NULLIF(f.total_employees, 0)) AS annual_pay_est
    FROM master_employers me
    JOIN national_990_filers f ON f.ein = me.ein
    WHERE me.ein IS NOT NULL
      AND f.total_employees > 0
      AND COALESCE(f.total_expenses, f.total_revenue) > 0
    ORDER BY me.master_id, f.total_employees DESC
),
-- Research wage proxy: revenue_per_employee_found
wage_research AS (
    SELECT
        mesi.master_id,
        'research' AS wage_source,
        rse.revenue_per_employee_found AS annual_pay_est
    FROM master_employer_source_ids mesi
    JOIN research_score_enhancements rse ON rse.employer_id = mesi.source_id
    WHERE mesi.source_system = 'f7'
      AND rse.revenue_per_employee_found IS NOT NULL
      AND rse.revenue_per_employee_found > 0
),
-- Combine: pick best wage source per employer (prefer 990 > research)
best_wage AS (
    SELECT DISTINCT ON (master_id)
        master_id, wage_source, annual_pay_est
    FROM (
        SELECT master_id, wage_source, annual_pay_est FROM wage_990
        UNION ALL
        SELECT master_id, wage_source, annual_pay_est FROM wage_research
    ) all_wages
    WHERE annual_pay_est > 1000   -- sanity: at least $1K/yr
      AND annual_pay_est < 10000000  -- cap at $10M (outlier protection)
    ORDER BY master_id,
             CASE wage_source
                 WHEN '990' THEN 1
                 WHEN 'ppp' THEN 2
                 WHEN 'research' THEN 3
                 ELSE 4
             END
)
INSERT INTO employer_wage_outliers
    (master_id, employer_name, state, naics, naics_2,
     wage_source, employer_annual_pay,
     qcew_avg_annual_pay, qcew_employment,
     wage_ratio, is_low_wage_outlier, wage_outlier_score)
SELECT
    me.master_id AS master_id,
    me.display_name AS employer_name,
    me.state,
    me.naics,
    LEFT(me.naics, 2) AS naics_2,
    bw.wage_source,
    ROUND(bw.annual_pay_est::numeric, 2) AS employer_annual_pay,
    ROUND(q.avg_annual_pay::numeric, 2) AS qcew_avg_annual_pay,
    q.total_employment::integer AS qcew_employment,
    ROUND((bw.annual_pay_est / NULLIF(q.avg_annual_pay, 0))::numeric, 4) AS wage_ratio,
    -- Low-wage outlier: >20% below local industry average
    (bw.annual_pay_est / NULLIF(q.avg_annual_pay, 0)) < 0.80 AS is_low_wage_outlier,
    -- Score: 0-10 (higher = further below average)
    -- On par or above = 0, 10% below = 3, 20% below = 5, 30%+ below = 8-10
    ROUND(LEAST(10, GREATEST(0,
        CASE
            WHEN bw.annual_pay_est >= q.avg_annual_pay THEN 0
            WHEN bw.annual_pay_est >= q.avg_annual_pay * 0.90 THEN 3
            WHEN bw.annual_pay_est >= q.avg_annual_pay * 0.80 THEN 5
            WHEN bw.annual_pay_est >= q.avg_annual_pay * 0.70 THEN 7
            WHEN bw.annual_pay_est >= q.avg_annual_pay * 0.60 THEN 8
            ELSE 10
        END
    ))::numeric, 2) AS wage_outlier_score
FROM master_employers me
JOIN best_wage bw ON bw.master_id = me.master_id
JOIN fips f ON f.state_abbr = me.state
JOIN qcew q ON q.state_fips = f.state_fips AND q.naics_2 = LEFT(me.naics, 2)
WHERE me.naics IS NOT NULL
  AND me.state IS NOT NULL
  AND LENGTH(me.naics) >= 2
  AND q.avg_annual_pay > 0
"""


def _print_stats(cur):
    cur.execute("SELECT COUNT(*) FROM employer_wage_outliers")
    total = cur.fetchone()[0]
    print(f"  Total employers with wage comparison: {total:,}")

    if total == 0:
        return

    cur.execute("SELECT COUNT(*) FROM employer_wage_outliers WHERE is_low_wage_outlier")
    low = cur.fetchone()[0]
    print(f"  Low-wage outliers (>20%% below avg): {low:,} ({100.0 * low / total:.1f}%%)")

    cur.execute("""
        SELECT wage_source, COUNT(*) AS cnt
        FROM employer_wage_outliers
        GROUP BY wage_source
        ORDER BY cnt DESC
    """)
    print("\n  Wage source distribution:")
    for row in cur.fetchall():
        pct = 100.0 * row[1] / total
        print(f"    {str(row[0]):12s}: {row[1]:>10,} ({pct:5.1f}%)")

    cur.execute("""
        SELECT
            ROUND(MIN(wage_ratio)::numeric, 3),
            ROUND(AVG(wage_ratio)::numeric, 3),
            ROUND(MAX(wage_ratio)::numeric, 3)
        FROM employer_wage_outliers
        WHERE wage_ratio IS NOT NULL
    """)
    mn, avg, mx = cur.fetchone()
    print(f"\n  Wage ratio (employer/QCEW): min={mn}, avg={avg}, max={mx}")

    cur.execute("""
        SELECT
            ROUND(AVG(wage_outlier_score)::numeric, 2),
            COUNT(*) FILTER (WHERE wage_outlier_score >= 5),
            COUNT(*) FILTER (WHERE wage_outlier_score >= 7)
        FROM employer_wage_outliers
    """)
    avg_score, cnt_5, cnt_7 = cur.fetchone()
    print(f"  Outlier score: avg={avg_score}, >=5: {cnt_5:,}, >=7: {cnt_7:,}")

    # Union vs non-union breakdown
    cur.execute("""
        SELECT me.is_union, COUNT(*) AS cnt,
               COUNT(*) FILTER (WHERE ewo.is_low_wage_outlier) AS low_wage_cnt
        FROM employer_wage_outliers ewo
        JOIN master_employers me ON me.master_id = ewo.master_id
        GROUP BY me.is_union
    """)
    print("\n  Union vs non-union:")
    for row in cur.fetchall():
        label = "Union" if row[0] else "Non-union"
        print(f"    {label:12s}: {row[1]:>10,} total, {row[2]:>8,} low-wage")


def build(conn):
    cur = conn.cursor()

    # Step 1: Create QCEW state+industry MV
    print("Creating mv_qcew_state_industry_wages...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_qcew_state_industry_wages CASCADE")
    conn.commit()
    t0 = time.time()
    cur.execute(QCEW_STATE_NAICS_SQL)
    conn.commit()
    for idx in QCEW_INDEX_SQL:
        cur.execute(idx)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM mv_qcew_state_industry_wages")
    print(f"  {cur.fetchone()[0]:,} state+NAICS-2+year rows ({time.time() - t0:.1f}s)")

    # Step 2: Create outlier table
    print("\nCreating employer_wage_outliers table...")
    cur.execute(OUTLIER_TABLE_SQL)
    conn.commit()

    # Step 3: Populate
    print("Computing wage comparisons...")
    t0 = time.time()
    cur.execute(POPULATE_SQL)
    conn.commit()
    print(f"  Done ({time.time() - t0:.1f}s)")

    # Indexes
    for idx in OUTLIER_INDEX_SQL:
        cur.execute(idx)
    conn.commit()

    # Stats
    print("\nVerification:")
    _print_stats(cur)


def refresh(conn):
    """Refresh by dropping and rebuilding."""
    build(conn)


def main():
    parser = argparse.ArgumentParser(description="Compute QCEW wage outlier flags")
    parser.add_argument("--refresh", action="store_true", help="Rebuild from scratch")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    try:
        with pipeline_lock(conn, 'wage_outliers'):
            build(conn)
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
