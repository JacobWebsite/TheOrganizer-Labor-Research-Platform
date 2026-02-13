"""
Check federal contract coverage for OSHA organizing targets.
Queries crosswalk columns, sample data, and coverage gaps.
"""
import sys, time
sys.path.insert(0, r"C:\Users\jakew\Downloads\labor-data-project")
from db_config import get_connection

def run_query(cur, label, sql, timeout_sec=30):
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    t0 = time.time()
    try:
        cur.execute(f"SET statement_timeout = '{timeout_sec}s'")
        cur.execute(sql)
        rows = cur.fetchall()
        elapsed = time.time() - t0
        cols = [d[0] for d in cur.description]
        print(f"  Columns: {cols}")
        print(f"  Rows returned: {len(rows)}  ({elapsed:.1f}s)")
        for r in rows:
            print(f"    {r}")
        return rows
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR after {elapsed:.1f}s: {e}")
        cur.execute("ROLLBACK")
        return None

def main():
    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    # 1. Crosswalk columns
    run_query(cur, "1) corporate_identifier_crosswalk columns",
        """SELECT column_name
           FROM information_schema.columns
           WHERE table_name = 'corporate_identifier_crosswalk'
           ORDER BY ordinal_position""")

    # 2. Sample federal contractor rows
    run_query(cur, "2) Sample crosswalk rows with federal contractor data",
        """SELECT f7_employer_id, is_federal_contractor, federal_obligations, federal_contract_count
           FROM corporate_identifier_crosswalk
           WHERE is_federal_contractor = TRUE
           LIMIT 5""")

    # 3. OSHA target contract coverage
    run_query(cur, "3) OSHA targets with federal contract data",
        """SELECT
               COUNT(DISTINCT ot.establishment_id) as total_targets,
               COUNT(DISTINCT CASE WHEN c.is_federal_contractor THEN ot.establishment_id END) as with_federal,
               COUNT(DISTINCT CASE WHEN me.score_govt_contracts > 0 THEN ot.establishment_id END) as with_mergent_score
           FROM v_osha_organizing_targets ot
           LEFT JOIN osha_f7_matches ofm ON ot.establishment_id = ofm.establishment_id
           LEFT JOIN corporate_identifier_crosswalk c ON ofm.f7_employer_id = c.f7_employer_id AND c.is_federal_contractor = TRUE
           LEFT JOIN mergent_employers me ON ot.establishment_id = me.osha_establishment_id AND me.score_govt_contracts > 0""",
        timeout_sec=60)

    # 4. v_osha_organizing_targets columns related to contracts/matching
    run_query(cur, "4) v_osha_organizing_targets contract/match columns",
        """SELECT column_name FROM information_schema.columns
           WHERE table_name = 'v_osha_organizing_targets'
           AND (column_name LIKE '%%contract%%' OR column_name LIKE '%%match%%'
                OR column_name LIKE '%%f7%%' OR column_name LIKE '%%employer%%')
           ORDER BY column_name""")

    # 5. NLRB coverage (may be slow - 30s timeout)
    run_query(cur, "5) OSHA targets with NLRB data (30s timeout)",
        """SELECT
               COUNT(DISTINCT ot.establishment_id) as total_targets,
               COUNT(DISTINCT CASE WHEN np.case_number IS NOT NULL THEN ot.establishment_id END) as with_nlrb
           FROM v_osha_organizing_targets ot
           LEFT JOIN nlrb_participants np ON np.participant_name ILIKE CONCAT('%%', LEFT(ot.estab_name, 15), '%%')
               AND np.participant_type = 'Employer'""",
        timeout_sec=30)

    cur.close()
    conn.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
