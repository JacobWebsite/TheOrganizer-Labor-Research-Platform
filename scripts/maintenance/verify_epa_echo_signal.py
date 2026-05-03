"""
Verify EPA ECHO data is loaded, matched, and ready for downstream scoring.

Run after: load_epa_echo.py + seed_master_epa_echo.py.
Usage:
    py scripts/maintenance/verify_epa_echo_signal.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()
    print("=== EPA ECHO Signal Verification ===\n")

    print("1. Raw facility table:")
    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities")
    total = cur.fetchone()[0]
    print(f"   epa_echo_facilities rows:       {total:>10,}")
    if total == 0:
        print("\n   ERROR: epa_echo_facilities is empty. Run load_epa_echo.py first.")
        return

    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_active_flag = 'Y'")
    active = cur.fetchone()[0]
    print(f"   active facilities:              {active:>10,} ({100*active/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_inspection_count > 0")
    inspected = cur.fetchone()[0]
    print(f"   with inspections:               {inspected:>10,} ({100*inspected/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_formal_action_count > 0")
    formal = cur.fetchone()[0]
    print(f"   with formal enforcement:        {formal:>10,} ({100*formal/total:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM epa_echo_facilities WHERE fac_total_penalties > 0")
    penalized = cur.fetchone()[0]
    print(f"   with penalties:                 {penalized:>10,} ({100*penalized/total:.1f}%)")

    print("\n2. Matching to master_employers:")
    cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'epa_echo'")
    links = cur.fetchone()[0]
    print(f"   source_id links (epa_echo):     {links:>10,}")
    cur.execute("SELECT COUNT(DISTINCT master_id) FROM master_employer_source_ids WHERE source_system = 'epa_echo'")
    distinct_masters = cur.fetchone()[0]
    print(f"   distinct masters with EPA link: {distinct_masters:>10,}")
    cur.execute("SELECT COUNT(*) FROM master_employers WHERE source_origin = 'epa_echo'")
    epa_origin_masters = cur.fetchone()[0]
    print(f"   masters with epa_echo origin:   {epa_origin_masters:>10,} (created by seed)")

    print("\n3. Match-confidence distribution:")
    cur.execute(
        "SELECT match_confidence, COUNT(*) FROM master_employer_source_ids "
        "WHERE source_system = 'epa_echo' GROUP BY 1 ORDER BY 1 DESC"
    )
    for conf, n in cur.fetchall():
        print(f"   confidence={conf}: {n:,}")

    print("\n4. Top states by EPA-linked masters:")
    cur.execute(
        """
        SELECT m.state, COUNT(DISTINCT m.master_id) AS n
        FROM master_employer_source_ids sid
        JOIN master_employers m ON m.master_id = sid.master_id
        WHERE sid.source_system = 'epa_echo'
        GROUP BY m.state ORDER BY 2 DESC LIMIT 8
        """
    )
    for state, n in cur.fetchall():
        print(f"   {state or 'NULL':<6s} {n:>8,}")

    print("\n5. Beta states (NY/VA/OH) coverage:")
    for state in ("NY", "VA", "OH"):
        cur.execute(
            """
            SELECT
                COUNT(*) AS facilities,
                SUM(CASE WHEN fac_inspection_count > 0 THEN 1 ELSE 0 END) AS inspected,
                SUM(CASE WHEN fac_formal_action_count > 0 THEN 1 ELSE 0 END) AS enforced,
                SUM(fac_total_penalties)::numeric(14,0) AS penalty_total
            FROM epa_echo_facilities WHERE fac_state = %s AND fac_active_flag = 'Y'
            """,
            (state,),
        )
        f, i, e, p = cur.fetchone()
        print(f"   {state}: {f:,} active, {i:,} inspected, {e:,} enforced, ${(p or 0):,.0f} total penalties")

    print("\n6. Sample matched master employer (largest penalty):")
    cur.execute(
        """
        SELECT m.master_id, m.display_name, m.state, m.zip,
               ef.fac_inspection_count, ef.fac_formal_action_count,
               ef.fac_total_penalties, ef.fac_date_last_penalty
        FROM master_employer_source_ids sid
        JOIN epa_echo_facilities ef ON ef.registry_id = sid.source_id
        JOIN master_employers m ON m.master_id = sid.master_id
        WHERE sid.source_system = 'epa_echo' AND ef.fac_total_penalties > 0
        ORDER BY ef.fac_total_penalties DESC NULLS LAST
        LIMIT 5
        """
    )
    for row in cur.fetchall():
        print(f"   master {row[0]} | {row[1][:40]:<40s} | {row[2]:<3s} | "
              f"insp={row[4]} formal={row[5]} penalties=${row[6]:,.0f} last={row[7]}")
    conn.close()


if __name__ == "__main__":
    main()
