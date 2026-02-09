"""
Integrate QCEW data with F7 employers.

QCEW is aggregated (industry x geography), NOT employer-level.
We use it for:
1. Industry density scoring: how many establishments per NAICS x county?
2. Employment concentration: location quotients
3. Validation: compare F7 counts with QCEW counts
4. Fill NAICS for F7 employers that lack it (via area_fips + industry matching)

Key tables:
- qcew_annual: loaded with 1.9M rows (2020-2023)
- f7_employers: 62K employers with naics, city, state, zip
- zip_geography: maps zip -> county FIPS (if available)
"""
import psycopg2
from psycopg2.extras import execute_values
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def check_zip_geography(conn):
    """Check if we have zip-to-county FIPS mapping."""
    cur = conn.cursor()
    # Check if zip_geography or similar table exists
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN ('zip_geography', 'zip_to_fips', 'zip_county', 'zip_codes')
    """)
    tables = [r[0] for r in cur.fetchall()]
    if tables:
        print(f"  ZIP geography tables: {tables}")
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            print(f"    {t}: {cur.fetchone()[0]:,} rows")
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{t}' ORDER BY ordinal_position LIMIT 10
            """)
            cols = [r[0] for r in cur.fetchall()]
            print(f"    Columns: {cols}")
    return tables


def create_qcew_industry_density(conn):
    """
    Create industry density table: NAICS x State -> establishment count, employment, wages.
    Uses state-level QCEW data (agglvl_code 70-75 for NAICS detail, 40-41 for supersector).
    """
    cur = conn.cursor()

    print("\n=== Creating QCEW Industry Density Table ===")

    # Build a state-level industry density view using latest year (2023)
    cur.execute("DROP TABLE IF EXISTS qcew_industry_density CASCADE")
    cur.execute("""
        CREATE TABLE qcew_industry_density AS
        SELECT
            LEFT(area_fips, 2) as state_fips,
            industry_code,
            agglvl_code,
            year,
            SUM(annual_avg_estabs) as total_establishments,
            SUM(annual_avg_emplvl) as total_employment,
            SUM(total_annual_wages) as total_wages,
            AVG(avg_annual_pay) as avg_pay,
            AVG(lq_annual_avg_emplvl) as avg_lq_employment,
            COUNT(*) as county_count
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = 2023
          AND annual_avg_estabs > 0
          AND LENGTH(area_fips) >= 2
        GROUP BY LEFT(area_fips, 2), industry_code, agglvl_code, year
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM qcew_industry_density")
    print(f"  Created {cur.fetchone()[0]:,} rows")

    # Create indexes
    cur.execute("CREATE INDEX idx_qid_state ON qcew_industry_density(state_fips)")
    cur.execute("CREATE INDEX idx_qid_naics ON qcew_industry_density(industry_code)")
    cur.execute("CREATE INDEX idx_qid_state_naics ON qcew_industry_density(state_fips, industry_code)")
    conn.commit()
    print("  Indexes created")

    return True


def create_state_fips_mapping(conn):
    """Create state abbreviation -> state FIPS mapping."""
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS state_fips_map CASCADE")
    cur.execute("""
        CREATE TABLE state_fips_map (
            state_abbr TEXT PRIMARY KEY,
            state_fips TEXT,
            state_name TEXT
        )
    """)

    mapping = [
        ('AL','01','Alabama'),('AK','02','Alaska'),('AZ','04','Arizona'),
        ('AR','05','Arkansas'),('CA','06','California'),('CO','08','Colorado'),
        ('CT','09','Connecticut'),('DE','10','Delaware'),('DC','11','District of Columbia'),
        ('FL','12','Florida'),('GA','13','Georgia'),('HI','15','Hawaii'),
        ('ID','16','Idaho'),('IL','17','Illinois'),('IN','18','Indiana'),
        ('IA','19','Iowa'),('KS','20','Kansas'),('KY','21','Kentucky'),
        ('LA','22','Louisiana'),('ME','23','Maine'),('MD','24','Maryland'),
        ('MA','25','Massachusetts'),('MI','26','Michigan'),('MN','27','Minnesota'),
        ('MS','28','Mississippi'),('MO','29','Missouri'),('MT','30','Montana'),
        ('NE','31','Nebraska'),('NV','32','Nevada'),('NH','33','New Hampshire'),
        ('NJ','34','New Jersey'),('NM','35','New Mexico'),('NY','36','New York'),
        ('NC','37','North Carolina'),('ND','38','North Dakota'),('OH','39','Ohio'),
        ('OK','40','Oklahoma'),('OR','41','Oregon'),('PA','42','Pennsylvania'),
        ('RI','44','Rhode Island'),('SC','45','South Carolina'),('SD','46','South Dakota'),
        ('TN','47','Tennessee'),('TX','48','Texas'),('UT','49','Utah'),
        ('VT','50','Vermont'),('VA','51','Virginia'),('WA','53','Washington'),
        ('WV','54','West Virginia'),('WI','55','Wisconsin'),('WY','56','Wyoming'),
        ('PR','72','Puerto Rico'),('VI','78','Virgin Islands'),('GU','66','Guam'),
    ]

    execute_values(cur, """
        INSERT INTO state_fips_map (state_abbr, state_fips, state_name) VALUES %s
    """, mapping)
    conn.commit()
    print(f"  State FIPS mapping: {len(mapping)} entries")
    return True


def analyze_f7_vs_qcew(conn):
    """Compare F7 employer counts with QCEW establishment counts by state x NAICS."""
    cur = conn.cursor()

    print("\n=== F7 vs QCEW Comparison ===")

    # F7 employers by state (with NAICS)
    cur.execute("""
        SELECT f.state, LEFT(f.naics, 2) as naics2, COUNT(*) as f7_count
        FROM f7_employers f
        WHERE f.naics IS NOT NULL AND f.naics != '' AND f.state IS NOT NULL
        GROUP BY f.state, LEFT(f.naics, 2)
        ORDER BY f7_count DESC
        LIMIT 20
    """)
    print("  Top 20 F7 state x NAICS2 groups:")
    for row in cur.fetchall():
        print(f"    {row[0]} NAICS-{row[1]}: {row[2]:,} employers")

    # Compare with QCEW
    print("\n  F7 vs QCEW by state (top 10 states):")
    cur.execute("""
        WITH f7_by_state AS (
            SELECT state, COUNT(*) as f7_employers,
                   COUNT(CASE WHEN naics IS NOT NULL AND naics != '' THEN 1 END) as f7_with_naics
            FROM f7_employers
            WHERE state IS NOT NULL
            GROUP BY state
        ),
        qcew_by_state AS (
            SELECT sfm.state_abbr as state,
                   SUM(qid.total_establishments) as qcew_estabs,
                   SUM(qid.total_employment) as qcew_employment
            FROM qcew_industry_density qid
            JOIN state_fips_map sfm ON sfm.state_fips = qid.state_fips
            WHERE qid.agglvl_code IN ('74','75')  -- County-level NAICS detail
            GROUP BY sfm.state_abbr
        )
        SELECT f.state, f.f7_employers, f.f7_with_naics,
               q.qcew_estabs, q.qcew_employment,
               CASE WHEN q.qcew_estabs > 0
                    THEN ROUND(100.0 * f.f7_employers / q.qcew_estabs, 2)
                    ELSE 0 END as f7_pct_of_qcew
        FROM f7_by_state f
        LEFT JOIN qcew_by_state q ON q.state = f.state
        ORDER BY f.f7_employers DESC
        LIMIT 10
    """)
    print(f"  {'State':<6} {'F7':>8} {'w/NAICS':>8} {'QCEW Est':>12} {'QCEW Empl':>12} {'F7/QCEW':>8}")
    for row in cur.fetchall():
        st, f7, fn, qe, qemp, pct = row
        qe = qe or 0
        qemp = qemp or 0
        print(f"  {st:<6} {f7:>8,} {fn:>8,} {qe:>12,} {qemp:>12,} {pct:>7.2f}%")


def create_employer_industry_scores(conn):
    """
    Create industry density scores for F7 employers using QCEW.
    This adds organizing-relevant metrics:
    - How many establishments in this NAICS x state?
    - What's the employment concentration (LQ)?
    - Average wages in this industry/state?
    """
    cur = conn.cursor()

    print("\n=== Creating F7 Industry Scores ===")

    cur.execute("DROP TABLE IF EXISTS f7_industry_scores CASCADE")

    # F7 NAICS is all 2-digit. QCEW level 74 uses 2-digit but with
    # hyphenated ranges: "31-33" (Manufacturing), "44-45" (Retail), "48-49" (Transport).
    # Create a mapping table to handle this.
    cur.execute("DROP TABLE IF EXISTS _naics2_qcew_map CASCADE")
    cur.execute("""
        CREATE TEMP TABLE _naics2_qcew_map AS
        SELECT DISTINCT f.naics as f7_naics, q.industry_code as qcew_code
        FROM (SELECT DISTINCT naics FROM f7_employers WHERE naics IS NOT NULL AND naics != '') f
        CROSS JOIN (SELECT DISTINCT industry_code FROM qcew_annual WHERE agglvl_code = '74' AND year = 2023) q
        WHERE f.naics = q.industry_code
           OR (q.industry_code LIKE '%-%'
               AND CAST(f.naics AS INTEGER) >= CAST(SPLIT_PART(q.industry_code, '-', 1) AS INTEGER)
               AND CAST(f.naics AS INTEGER) <= CAST(SPLIT_PART(q.industry_code, '-', 2) AS INTEGER))
    """)
    conn.commit()

    cur.execute("SELECT * FROM _naics2_qcew_map ORDER BY f7_naics")
    print("  NAICS mapping (F7 -> QCEW):")
    for r in cur.fetchall():
        print(f"    {r[0]} -> {r[1]}")

    cur.execute("""
        CREATE TABLE f7_industry_scores AS
        SELECT
            f.employer_id,
            f.employer_name as name,
            f.state,
            f.naics,
            -- 2-digit level density (from QCEW level 74 = county, NAICS sector)
            q2.total_establishments as naics2_establishments,
            q2.total_employment as naics2_employment,
            q2.total_wages as naics2_wages,
            q2.avg_pay as naics2_avg_pay,
            q2.avg_lq_employment as naics2_lq,
            q2.county_count as naics2_county_count,
            -- Computed scores
            CASE
                WHEN q2.total_establishments IS NOT NULL AND q2.total_establishments > 0
                THEN ROUND(LN(q2.total_establishments + 1)::numeric, 2)
                ELSE 0
            END as density_score,
            CASE
                WHEN q2.avg_lq_employment IS NOT NULL AND q2.avg_lq_employment > 1.0
                THEN ROUND(LEAST(q2.avg_lq_employment, 5.0)::numeric, 2)
                ELSE 0
            END as concentration_score,
            CASE
                WHEN q2.avg_pay IS NOT NULL AND q2.avg_pay > 0
                THEN ROUND(q2.avg_pay::numeric, 0)
                ELSE NULL
            END as industry_avg_pay
        FROM f7_employers f
        JOIN state_fips_map sm ON sm.state_abbr = f.state
        JOIN _naics2_qcew_map nm ON nm.f7_naics = f.naics
        LEFT JOIN qcew_industry_density q2
            ON q2.state_fips = sm.state_fips
            AND q2.industry_code = nm.qcew_code
            AND q2.agglvl_code = '74'
        WHERE f.naics IS NOT NULL AND f.naics != '' AND f.state IS NOT NULL
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM f7_industry_scores")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM f7_industry_scores WHERE naics2_establishments IS NOT NULL")
    matched = cur.fetchone()[0]

    print(f"  Created {total:,} rows ({matched:,} matched to QCEW = {100*matched/total:.1f}%)")

    # Create index
    cur.execute("CREATE INDEX idx_fis_employer ON f7_industry_scores(employer_id)")
    cur.execute("CREATE INDEX idx_fis_state ON f7_industry_scores(state)")
    conn.commit()

    # Summary
    print("\n  Score distribution (density_score):")
    cur.execute("""
        SELECT
            CASE
                WHEN density_score = 0 THEN '0 (no match)'
                WHEN density_score < 3 THEN '0-3 (low)'
                WHEN density_score < 6 THEN '3-6 (medium)'
                WHEN density_score < 9 THEN '6-9 (high)'
                ELSE '9+ (very high)'
            END as bucket,
            COUNT(*) as cnt
        FROM f7_industry_scores
        GROUP BY 1
        ORDER BY 1
    """)
    for row in cur.fetchall():
        print(f"    {row[0]:<20}: {row[1]:,}")

    print("\n  Top 10 industries by avg establishment density:")
    cur.execute("""
        SELECT naics,
               COUNT(*) as employers,
               ROUND(AVG(naics2_establishments)) as avg_estabs,
               ROUND(AVG(naics2_employment)) as avg_empl,
               ROUND(AVG(density_score), 1) as avg_density,
               ROUND(AVG(industry_avg_pay)) as avg_pay
        FROM f7_industry_scores
        WHERE naics2_establishments IS NOT NULL
        GROUP BY naics
        HAVING COUNT(*) >= 50
        ORDER BY avg_estabs DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        pay = row[5] or 0
        print(f"    NAICS {row[0]}: {row[1]:,} employers, avg {row[2]:,.0f} estabs, density={row[4]}, avg_pay=${pay:,.0f}")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    # Check for zip-to-FIPS mapping
    print("=== Checking data availability ===")
    zip_tables = check_zip_geography(conn)

    # Create state FIPS mapping
    create_state_fips_mapping(conn)

    # Create industry density table
    create_qcew_industry_density(conn)

    # Compare F7 with QCEW
    analyze_f7_vs_qcew(conn)

    # Create industry scores for F7 employers
    create_employer_industry_scores(conn)

    conn.close()
    print("\n=== QCEW Integration Complete ===")


if __name__ == "__main__":
    main()
