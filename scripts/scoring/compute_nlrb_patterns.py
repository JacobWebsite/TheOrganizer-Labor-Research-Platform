"""
Task 3.2: NLRB Historical Success Pattern Scoring

Analyzes 33K NLRB elections to learn which employer types vote "yes" most often,
then scores every mergent_employer by how well it matches winning patterns.

Creates reference tables:
  - ref_nlrb_industry_win_rates (NAICS 2-digit win rates)
  - ref_nlrb_size_win_rates (unit size bucket win rates)

Computes per-employer:
  - nlrb_success_score (0.0-1.0) based on state + industry + size patterns
  - nlrb_predicted_win_pct (weighted prediction)

Usage:
  py scripts/scoring/compute_nlrb_patterns.py [--dry-run]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

def create_reference_tables(cur):
    """Create NLRB pattern reference tables."""

    # --- Industry win rates ---
    print("\n[1/3] Building ref_nlrb_industry_win_rates...")
    cur.execute("DROP TABLE IF EXISTS ref_nlrb_industry_win_rates CASCADE")
    cur.execute("""
        CREATE TABLE ref_nlrb_industry_win_rates (
            naics_2 VARCHAR(2) PRIMARY KEY,
            total_elections INTEGER NOT NULL,
            union_wins INTEGER NOT NULL,
            win_rate_pct NUMERIC(5,1) NOT NULL,
            sample_quality VARCHAR(10) NOT NULL
        )
    """)

    # Use matched employers to get NAICS, plus fallback national average
    cur.execute("""
        INSERT INTO ref_nlrb_industry_win_rates (naics_2, total_elections, union_wins, win_rate_pct, sample_quality)
        SELECT
            LEFT(f.naics, 2) as naics_2,
            COUNT(DISTINCT e.id) as total_elections,
            SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
            ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / NULLIF(COUNT(DISTINCT e.id), 0), 1),
            CASE
                WHEN COUNT(DISTINCT e.id) >= 100 THEN 'high'
                WHEN COUNT(DISTINCT e.id) >= 30 THEN 'medium'
                ELSE 'low'
            END
        FROM nlrb_elections e
        JOIN nlrb_participants p ON p.case_number = e.case_number AND p.participant_type = 'Employer'
        JOIN f7_employers_deduped f ON f.employer_id = p.matched_employer_id
        WHERE e.union_won IS NOT NULL
          AND f.naics IS NOT NULL AND f.naics != ''
        GROUP BY LEFT(f.naics, 2)
        HAVING COUNT(DISTINCT e.id) >= 10
    """)

    # Add national average as fallback
    cur.execute("""
        INSERT INTO ref_nlrb_industry_win_rates (naics_2, total_elections, union_wins, win_rate_pct, sample_quality)
        SELECT 'US', COUNT(*), SUM(CASE WHEN union_won THEN 1 ELSE 0 END),
               ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / COUNT(*), 1), 'high'
        FROM nlrb_elections WHERE union_won IS NOT NULL
        ON CONFLICT (naics_2) DO NOTHING
    """)

    cur.execute("SELECT COUNT(*) FROM ref_nlrb_industry_win_rates")
    print(f"  -> {cur.fetchone()[0]} industry rows")

    # --- Size bucket win rates ---
    print("[2/3] Building ref_nlrb_size_win_rates...")
    cur.execute("DROP TABLE IF EXISTS ref_nlrb_size_win_rates CASCADE")
    cur.execute("""
        CREATE TABLE ref_nlrb_size_win_rates (
            size_bucket VARCHAR(20) PRIMARY KEY,
            min_employees INTEGER,
            max_employees INTEGER,
            total_elections INTEGER NOT NULL,
            union_wins INTEGER NOT NULL,
            win_rate_pct NUMERIC(5,1) NOT NULL
        )
    """)

    size_buckets = [
        ('1-10', 1, 10),
        ('11-25', 11, 25),
        ('26-50', 26, 50),
        ('51-100', 51, 100),
        ('101-250', 101, 250),
        ('251-500', 251, 500),
        ('501-1000', 501, 1000),
        ('1000+', 1001, 999999),
    ]

    for bucket, lo, hi in size_buckets:
        cur.execute("""
            INSERT INTO ref_nlrb_size_win_rates (size_bucket, min_employees, max_employees,
                                                  total_elections, union_wins, win_rate_pct)
            SELECT %s, %s, %s, COUNT(*),
                   SUM(CASE WHEN union_won THEN 1 ELSE 0 END),
                   ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / COUNT(*), 1)
            FROM nlrb_elections
            WHERE eligible_voters BETWEEN %s AND %s
              AND union_won IS NOT NULL
        """, (bucket, lo, hi, lo, hi))

    cur.execute("SELECT COUNT(*) FROM ref_nlrb_size_win_rates")
    print(f"  -> {cur.fetchone()[0]} size bucket rows")

    # Print summary
    print("\n  Industry win rates:")
    cur.execute("SELECT naics_2, total_elections, win_rate_pct, sample_quality FROM ref_nlrb_industry_win_rates ORDER BY total_elections DESC")
    for r in cur.fetchall():
        print(f"    NAICS {r[0]:>2}: {r[1]:>5} elections, {r[2]}% win rate ({r[3]})")

    print("\n  Size bucket win rates:")
    cur.execute("SELECT size_bucket, total_elections, win_rate_pct FROM ref_nlrb_size_win_rates ORDER BY min_employees")
    for r in cur.fetchall():
        print(f"    {r[0]:>10}: {r[1]:>5} elections, {r[2]}% win rate")


def compute_employer_scores(cur, dry_run=False):
    """Compute NLRB success prediction for every mergent employer."""

    print("\n[3/3] Computing per-employer NLRB success scores...")

    # Add columns if needed
    cur.execute("""
        ALTER TABLE mergent_employers
        ADD COLUMN IF NOT EXISTS nlrb_predicted_win_pct NUMERIC(5,1),
        ADD COLUMN IF NOT EXISTS nlrb_success_factors JSONB
    """)

    # BEFORE snapshot
    cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE nlrb_predicted_win_pct IS NOT NULL")
    before = cur.fetchone()[0]
    print(f"  BEFORE: {before:,} employers with nlrb_predicted_win_pct")

    # Load reference data into memory
    cur.execute("SELECT naics_2, win_rate_pct FROM ref_nlrb_industry_win_rates")
    industry_rates = {r[0]: float(r[1]) for r in cur.fetchall()}
    national_avg = industry_rates.get('US', 67.4)

    cur.execute("SELECT min_employees, max_employees, win_rate_pct FROM ref_nlrb_size_win_rates ORDER BY min_employees")
    size_rates = [(r[0], r[1], float(r[2])) for r in cur.fetchall()]

    cur.execute("SELECT state, win_rate_pct FROM ref_nlrb_state_win_rates")
    state_rates = {r[0]: float(r[1]) for r in cur.fetchall()}
    state_national = state_rates.get('US', 75.2)

    # Temporal trend bonus: recent years (2022+) have 75%+ win rates
    # vs historical 67%. Scale from 0 to +5 percentage points.
    TEMPORAL_BONUS = 5.0  # recent organizing wave bonus

    # Load all employers
    cur.execute("""
        SELECT id, state, naics_primary, employees_site
        FROM mergent_employers
        WHERE state IS NOT NULL
    """)
    employers = cur.fetchall()
    print(f"  Processing {len(employers):,} employers...")

    if dry_run:
        employers = employers[:100]
        print("  [DRY RUN: first 100 only]")

    # Weights for composite score
    W_STATE = 0.35
    W_INDUSTRY = 0.35
    W_SIZE = 0.20
    W_TREND = 0.10

    import json
    updates = []
    for emp_id, state, naics, emp_count in employers:
        factors = {}

        # 1. State component
        state_pct = state_rates.get(state, state_national)
        factors['state'] = {'value': state_pct, 'weight': W_STATE}

        # 2. Industry component
        naics_2 = naics[:2] if naics else None
        if naics_2 and naics_2 in industry_rates:
            ind_pct = industry_rates[naics_2]
            factors['industry'] = {'value': ind_pct, 'weight': W_INDUSTRY, 'naics_2': naics_2}
        else:
            ind_pct = national_avg
            factors['industry'] = {'value': ind_pct, 'weight': W_INDUSTRY, 'naics_2': 'US', 'fallback': True}

        # 3. Size component
        size_pct = national_avg  # default
        size_bucket = 'unknown'
        if emp_count and emp_count > 0:
            for lo, hi, rate in size_rates:
                if lo <= emp_count <= hi:
                    size_pct = rate
                    size_bucket = f"{lo}-{hi}" if hi < 999999 else f"{lo}+"
                    break
        factors['size'] = {'value': size_pct, 'weight': W_SIZE, 'bucket': size_bucket}

        # 4. Temporal trend (flat bonus reflecting 2022+ organizing wave)
        trend_pct = national_avg + TEMPORAL_BONUS
        factors['trend'] = {'value': trend_pct, 'weight': W_TREND}

        # Weighted composite
        predicted = (
            state_pct * W_STATE +
            ind_pct * W_INDUSTRY +
            size_pct * W_SIZE +
            trend_pct * W_TREND
        )
        predicted = max(0, min(100, round(predicted, 1)))

        factors_json = json.dumps(factors, default=str)
        updates.append((predicted, factors_json, emp_id))

    # Batch update
    from psycopg2.extras import execute_batch
    execute_batch(cur, """
        UPDATE mergent_employers
        SET nlrb_predicted_win_pct = %s,
            nlrb_success_factors = %s
        WHERE id = %s
    """, updates, page_size=2000)

    # AFTER snapshot
    cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE nlrb_predicted_win_pct IS NOT NULL")
    after = cur.fetchone()[0]
    print(f"  AFTER: {after:,} employers with nlrb_predicted_win_pct")

    # Distribution
    cur.execute("""
        SELECT
            ROUND(AVG(nlrb_predicted_win_pct), 1) as mean,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY nlrb_predicted_win_pct) as median,
            MIN(nlrb_predicted_win_pct) as min,
            MAX(nlrb_predicted_win_pct) as max,
            PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY nlrb_predicted_win_pct) as p5,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY nlrb_predicted_win_pct) as p95
        FROM mergent_employers
        WHERE nlrb_predicted_win_pct IS NOT NULL
    """)
    r = cur.fetchone()
    print(f"\n  Distribution: mean={r[0]}, median={r[1]}, range=[{r[2]}, {r[3]}], p5={r[4]}, p95={r[5]}")

    # Top 10 highest predicted
    print("\n  Top 10 highest predicted win %:")
    cur.execute("""
        SELECT company_name, state, naics_primary, employees_site, nlrb_predicted_win_pct
        FROM mergent_employers
        WHERE nlrb_predicted_win_pct IS NOT NULL
        ORDER BY nlrb_predicted_win_pct DESC LIMIT 10
    """)
    for r in cur.fetchall():
        print(f"    {r[0][:40]:<40} {r[1]} NAICS={r[2] or '?':<6} emp={r[3] or '?':>6} -> {r[4]}%")

    # Lowest 10
    print("\n  Bottom 10 lowest predicted win %:")
    cur.execute("""
        SELECT company_name, state, naics_primary, employees_site, nlrb_predicted_win_pct
        FROM mergent_employers
        WHERE nlrb_predicted_win_pct IS NOT NULL
        ORDER BY nlrb_predicted_win_pct ASC LIMIT 10
    """)
    for r in cur.fetchall():
        print(f"    {r[0][:40]:<40} {r[1]} NAICS={r[2] or '?':<6} emp={r[3] or '?':>6} -> {r[4]}%")

    # By state (avg predicted)
    print("\n  Avg predicted win % by state (top 10):")
    cur.execute("""
        SELECT state, ROUND(AVG(nlrb_predicted_win_pct), 1), COUNT(*)
        FROM mergent_employers
        WHERE nlrb_predicted_win_pct IS NOT NULL
        GROUP BY state ORDER BY 2 DESC LIMIT 10
    """)
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]}% ({r[2]:,} employers)")


def main():
    parser = argparse.ArgumentParser(description="Compute NLRB success pattern scores")
    parser.add_argument("--dry-run", action="store_true", help="Process first 100 only")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        create_reference_tables(cur)
        compute_employer_scores(cur, dry_run=args.dry_run)
        conn.commit()
        print("\n=== COMMITTED ===")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
