"""
Comprehensive Database Audit for Labor Relations Research Platform
Read-only: no data modifications.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

def run_query(cur, sql, label=None):
    """Run a query and return results."""
    if label:
        print(f"\n{'='*80}")
        print(f"  {label}")
        print(f"{'='*80}")
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description] if cur.description else []
    return rows, cols

def print_table(rows, cols, max_col_width=50):
    """Pretty-print query results as a table."""
    if not rows:
        print("  (no rows)")
        return
    # Calculate column widths
    widths = [len(str(c)) for c in cols]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], min(len(str(val)), max_col_width))

    fmt = "  " + " | ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*[str(c)[:max_col_width] for c in cols]))
    print("  " + "-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(v)[:max_col_width] for v in row]))

def main():
    conn = get_connection()
    cur = conn.cursor()

    # =========================================================================
    # 1. ALL TABLES WITH ROW COUNTS
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT schemaname, relname AS table_name,
               n_live_tup AS estimated_rows
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        ORDER BY n_live_tup DESC
    """, "1. ALL TABLES WITH ROW COUNTS (estimated from pg_stat)")
    print_table(rows, cols)
    print(f"\n  Total tables: {len(rows)}")

    # =========================================================================
    # 2. ALL MATERIALIZED VIEWS WITH ROW COUNTS
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
        ORDER BY matviewname
    """)
    mat_views = [r[0] for r in rows]

    print(f"\n{'='*80}")
    print(f"  2. MATERIALIZED VIEWS WITH ROW COUNTS")
    print(f"{'='*80}")
    mv_results = []
    for mv in mat_views:
        cur.execute(f'SELECT COUNT(*) FROM "{mv}"')
        cnt = cur.fetchone()[0]
        mv_results.append((mv, cnt))
    mv_results.sort(key=lambda x: -x[1])
    print_table(mv_results, ['matview_name', 'row_count'])
    print(f"\n  Total materialized views: {len(mv_results)}")

    # =========================================================================
    # 3. ALL VIEWS
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT viewname FROM pg_views WHERE schemaname = 'public'
        ORDER BY viewname
    """)
    views = [r[0] for r in rows]

    print(f"\n{'='*80}")
    print(f"  3. REGULAR VIEWS")
    print(f"{'='*80}")
    view_results = []
    for v in views:
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{v}"')
            cnt = cur.fetchone()[0]
            view_results.append((v, cnt))
        except Exception as e:
            conn.rollback()
            view_results.append((v, f"ERROR: {e}"))
    view_results.sort(key=lambda x: -(x[1] if isinstance(x[1], int) else 0))
    print_table(view_results, ['view_name', 'row_count'])
    print(f"\n  Total views: {len(view_results)}")

    # =========================================================================
    # 4. MATCH RATES
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"  4. MATCH RATES")
    print(f"{'='*80}")

    match_queries = [
        ("OSHA -> F7 matches", "SELECT COUNT(*) FROM osha_f7_matches"),
        ("OSHA establishments total", "SELECT COUNT(*) FROM osha_establishments"),
        ("OSHA match rate", """
            SELECT ROUND(100.0 * (SELECT COUNT(*) FROM osha_f7_matches) /
                   NULLIF((SELECT COUNT(*) FROM osha_establishments), 0), 2) AS pct
        """),
        ("WHD total cases", "SELECT COUNT(*) FROM whd_cases"),
        ("WHD matched (matched_f7_employer_id IS NOT NULL)",
         "SELECT COUNT(*) FROM whd_cases WHERE matched_f7_employer_id IS NOT NULL"),
        ("WHD match rate", """
            SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE matched_f7_employer_id IS NOT NULL) /
                   NULLIF(COUNT(*), 0), 2) FROM whd_cases
        """),
        ("Mergent total", "SELECT COUNT(*) FROM mergent_employers"),
        ("Mergent matched (matched_f7_employer_id IS NOT NULL)",
         "SELECT COUNT(*) FROM mergent_employers WHERE matched_f7_employer_id IS NOT NULL"),
        ("Mergent match rate", """
            SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE matched_f7_employer_id IS NOT NULL) /
                   NULLIF(COUNT(*), 0), 2) FROM mergent_employers
        """),
        ("F7 employers total", "SELECT COUNT(*) FROM f7_employers_deduped"),
        ("Corporate crosswalk total", "SELECT COUNT(*) FROM corporate_identifier_crosswalk"),
        ("Crosswalk with GLEIF LEI", "SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE gleif_lei IS NOT NULL"),
        ("Crosswalk with Mergent DUNS", "SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE mergent_duns IS NOT NULL"),
        ("Crosswalk with SEC CIK", "SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE sec_cik IS NOT NULL"),
        ("Crosswalk with EIN", "SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE ein IS NOT NULL"),
        ("Crosswalk federal contractors", "SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE is_federal_contractor = true"),
        ("Employer comparables", "SELECT COUNT(*) FROM employer_comparables"),
    ]

    for label, sql in match_queries:
        try:
            cur.execute(sql)
            val = cur.fetchone()[0]
            print(f"  {label}: {val}")
        except Exception as e:
            conn.rollback()
            print(f"  {label}: ERROR - {e}")

    # Check 990 filers
    print("\n  --- 990 Filer Matching ---")
    try:
        cur.execute("SELECT COUNT(*) FROM national_990_filers")
        total_990 = cur.fetchone()[0]
        print(f"  990 filers total: {total_990}")
        # Check if there's an f7 link column
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'national_990_filers'
            AND column_name LIKE '%%f7%%' OR column_name LIKE '%%employer_id%%'
        """)
        f7_cols = cur.fetchall()
        if f7_cols:
            for (col,) in f7_cols:
                cur.execute(f"SELECT COUNT(*) FROM national_990_filers WHERE {col} IS NOT NULL")
                print(f"  990 with {col} IS NOT NULL: {cur.fetchone()[0]}")
        else:
            print("  990 filers: no F7 link column found")
    except Exception as e:
        conn.rollback()
        print(f"  990 filers: ERROR - {e}")

    # =========================================================================
    # 5. DATA QUALITY METRICS
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"  5. DATA QUALITY METRICS")
    print(f"{'='*80}")

    quality_queries = [
        ("F7 employers with NULL naics",
         "SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NULL"),
        ("F7 employers with naics populated",
         "SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NOT NULL"),
        ("F7 employers with NULL latitude",
         "SELECT COUNT(*) FROM f7_employers_deduped WHERE latitude IS NULL"),
        ("F7 employers with latitude populated",
         "SELECT COUNT(*) FROM f7_employers_deduped WHERE latitude IS NOT NULL"),
        ("F7 employers with NULL state",
         "SELECT COUNT(*) FROM f7_employers_deduped WHERE state IS NULL"),
        ("F7 employers with NULL city",
         "SELECT COUNT(*) FROM f7_employers_deduped WHERE city IS NULL"),
        ("Mergent employers with NULL naics_primary",
         "SELECT COUNT(*) FROM mergent_employers WHERE naics_primary IS NULL"),
        ("Mergent employers with NULL state",
         "SELECT COUNT(*) FROM mergent_employers WHERE state IS NULL"),
        ("Mergent with organizing_score",
         "SELECT COUNT(*) FROM mergent_employers WHERE organizing_score IS NOT NULL"),
        ("Mergent with nlrb_predicted_win_pct",
         "SELECT COUNT(*) FROM mergent_employers WHERE nlrb_predicted_win_pct IS NOT NULL"),
        ("Mergent with similarity_score",
         "SELECT COUNT(*) FROM mergent_employers WHERE similarity_score IS NOT NULL"),
        ("OSHA establishments with NULL naics_code",
         "SELECT COUNT(*) FROM osha_establishments WHERE naics_code IS NULL"),
        ("NLRB elections total",
         "SELECT COUNT(*) FROM nlrb_elections"),
        ("NLRB elections with outcome",
         "SELECT COUNT(*) FROM nlrb_elections WHERE election_outcome IS NOT NULL AND election_outcome != ''"),
        ("NLRB participants total",
         "SELECT COUNT(*) FROM nlrb_participants"),
    ]

    for label, sql in quality_queries:
        try:
            cur.execute(sql)
            print(f"  {label}: {cur.fetchone()[0]}")
        except Exception as e:
            conn.rollback()
            print(f"  {label}: ERROR - {e}")

    # Union hierarchy orphans
    print("\n  --- Union Hierarchy ---")
    try:
        cur.execute("SELECT COUNT(*) FROM union_hierarchy")
        print(f"  union_hierarchy total links: {cur.fetchone()[0]}")
        cur.execute("""
            SELECT COUNT(DISTINCT child_id) FROM union_hierarchy h
            WHERE NOT EXISTS (
                SELECT 1 FROM union_hierarchy p WHERE p.child_id = h.parent_id
            ) AND h.parent_id IS NOT NULL
        """)
        print(f"  Hierarchy entries referencing non-existent parents: {cur.fetchone()[0]}")
    except Exception as e:
        conn.rollback()
        print(f"  Union hierarchy: ERROR - {e}")

    # =========================================================================
    # 6. TABLES WITH 0 ROWS (DEAD TABLES)
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT relname AS table_name, n_live_tup AS estimated_rows
        FROM pg_stat_user_tables
        WHERE schemaname = 'public' AND n_live_tup = 0
        ORDER BY relname
    """, "6. TABLES WITH 0 ROWS (potentially dead)")
    print_table(rows, cols)
    print(f"\n  Total zero-row tables: {len(rows)}")

    # Double-check with actual counts for zero-row tables
    if rows:
        print("\n  Verifying with actual COUNT(*):")
        for (tbl, _) in rows:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{tbl}"')
                actual = cur.fetchone()[0]
                if actual > 0:
                    print(f"    {tbl}: actually has {actual} rows (pg_stat stale)")
                else:
                    print(f"    {tbl}: confirmed 0 rows")
            except Exception as e:
                conn.rollback()
                print(f"    {tbl}: ERROR - {e}")

    # =========================================================================
    # 7. LARGEST TABLES BY SIZE
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT
            relname AS table_name,
            pg_size_pretty(pg_total_relation_size(quote_ident(relname))) AS total_size,
            pg_total_relation_size(quote_ident(relname)) AS size_bytes,
            pg_size_pretty(pg_relation_size(quote_ident(relname))) AS data_size,
            pg_size_pretty(pg_total_relation_size(quote_ident(relname)) - pg_relation_size(quote_ident(relname))) AS index_size,
            n_live_tup AS estimated_rows
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(quote_ident(relname)) DESC
        LIMIT 30
    """, "7. TOP 30 LARGEST TABLES BY SIZE")
    print_table(rows, cols)

    # Total database size
    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"\n  Total database size: {cur.fetchone()[0]}")

    # =========================================================================
    # 8. INDEXES ON MAJOR TABLES
    # =========================================================================
    major_tables = [
        'f7_employers_deduped', 'osha_establishments', 'osha_f7_matches',
        'mergent_employers', 'whd_cases', 'nlrb_elections', 'nlrb_participants',
        'corporate_identifier_crosswalk', 'employer_comparables',
        'gleif_entities', 'gleif_ownership_links', 'union_hierarchy',
        'usaspending_recipients', 'qcew_annual_averages'
    ]

    print(f"\n{'='*80}")
    print(f"  8. INDEXES ON MAJOR TABLES")
    print(f"{'='*80}")

    for tbl in major_tables:
        try:
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = %s
                ORDER BY indexname
            """, (tbl,))
            idxs = cur.fetchall()
            print(f"\n  {tbl} ({len(idxs)} indexes):")
            for name, defn in idxs:
                # Shorten the definition for display
                short = defn.replace('CREATE INDEX ', '').replace('CREATE UNIQUE INDEX ', 'UNIQUE ')
                print(f"    - {short[:120]}")
        except Exception as e:
            conn.rollback()
            print(f"\n  {tbl}: ERROR - {e}")

    # =========================================================================
    # 9. SCORING DISTRIBUTION (Mergent)
    # =========================================================================
    rows, cols = run_query(cur, """
        WITH scored AS (
            SELECT
                CASE
                    WHEN organizing_score >= 30 THEN 'TOP'
                    WHEN organizing_score >= 25 THEN 'HIGH'
                    WHEN organizing_score >= 20 THEN 'MEDIUM'
                    ELSE 'LOW'
                END AS tier,
                organizing_score
            FROM mergent_employers
            WHERE organizing_score IS NOT NULL
        )
        SELECT tier, COUNT(*) AS count,
               ROUND(AVG(organizing_score)::numeric, 2) AS avg_score,
               MIN(organizing_score) AS min_score,
               MAX(organizing_score) AS max_score
        FROM scored
        GROUP BY tier
        ORDER BY CASE tier
            WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 END
    """, "9. SCORING DISTRIBUTION BY TIER")
    print_table(rows, cols)

    # =========================================================================
    # 10. GEOGRAPHIC COVERAGE
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT state, COUNT(*) AS employer_count
        FROM f7_employers_deduped
        WHERE state IS NOT NULL
        GROUP BY state
        ORDER BY COUNT(*) DESC
        LIMIT 15
    """, "10. TOP 15 STATES BY F7 EMPLOYER COUNT")
    print_table(rows, cols)

    # =========================================================================
    # 11. NAICS COVERAGE
    # =========================================================================
    rows, cols = run_query(cur, """
        SELECT naics, COUNT(*) AS cnt
        FROM f7_employers_deduped
        WHERE naics IS NOT NULL
        GROUP BY naics
        ORDER BY COUNT(*) DESC
        LIMIT 15
    """, "11. TOP 15 NAICS CODES IN F7")
    print_table(rows, cols)

    # =========================================================================
    # 12. REFERENCE TABLES
    # =========================================================================
    ref_tables = []
    cur.execute("""
        SELECT relname, n_live_tup FROM pg_stat_user_tables
        WHERE schemaname = 'public' AND relname LIKE 'ref_%%'
        ORDER BY relname
    """)
    ref_tables = cur.fetchall()

    print(f"\n{'='*80}")
    print(f"  12. REFERENCE TABLES")
    print(f"{'='*80}")
    print_table(ref_tables, ['table_name', 'estimated_rows'])

    # =========================================================================
    # 13. RECENT DATA FRESHNESS
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"  13. DATA FRESHNESS INDICATORS")
    print(f"{'='*80}")

    freshness_queries = [
        ("F7 latest filing year", "SELECT MAX(yr) FROM f7_employers_deduped"),
        ("OSHA latest inspection close date", "SELECT MAX(close_date) FROM osha_establishments"),
        ("WHD latest findings end date", "SELECT MAX(findings_end_date) FROM whd_cases"),
        ("NLRB latest election date", "SELECT MAX(election_date) FROM nlrb_elections"),
        ("QCEW latest year", "SELECT MAX(year) FROM qcew_annual_averages"),
    ]

    for label, sql in freshness_queries:
        try:
            cur.execute(sql)
            print(f"  {label}: {cur.fetchone()[0]}")
        except Exception as e:
            conn.rollback()
            print(f"  {label}: ERROR - {e}")

    # =========================================================================
    # 14. COLUMN INVENTORY FOR KEY TABLES
    # =========================================================================
    print(f"\n{'='*80}")
    print(f"  14. COLUMN INVENTORY FOR KEY TABLES")
    print(f"{'='*80}")

    key_tables = ['f7_employers_deduped', 'mergent_employers', 'osha_establishments',
                  'whd_cases', 'corporate_identifier_crosswalk']

    for tbl in key_tables:
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (tbl,))
        columns = cur.fetchall()
        print(f"\n  {tbl} ({len(columns)} columns):")
        for cname, dtype, nullable in columns:
            print(f"    {cname:<40} {dtype:<20} {'NULL' if nullable == 'YES' else 'NOT NULL'}")

    cur.close()
    conn.close()
    print(f"\n{'='*80}")
    print("  AUDIT COMPLETE")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()
