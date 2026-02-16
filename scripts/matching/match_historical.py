"""
Match historical employers against OSHA/WHD for "what happened after union left" analysis.

Uses the deterministic matcher to find OSHA/WHD records for employers
whose union contracts have expired (is_historical=true / old notice dates).

Usage:
    py scripts/matching/match_historical.py
    py scripts/matching/match_historical.py --dry-run --limit 1000
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


def match_historical_to_osha(conn, dry_run=False, limit=None):
    """Find OSHA records for historical employers not already matched."""
    with conn.cursor() as cur:
        # Historical employers not yet matched to OSHA
        sql = """
            SELECT f.employer_id, f.employer_name, f.state, f.city,
                   f.name_standard, f.name_aggressive
            FROM f7_employers_deduped f
            LEFT JOIN osha_f7_matches m ON f.employer_id = m.f7_employer_id
            WHERE m.f7_employer_id IS NULL
              AND f.latest_notice_date < '2020-01-01'
              AND f.name_standard IS NOT NULL
        """
        if limit:
            sql += f" LIMIT {int(limit)}"

        cur.execute(sql)
        historical = cur.fetchall()
        print(f"Historical employers to match against OSHA: {len(historical):,}")

        if not historical:
            return 0

        # Match against OSHA using name_standard+state
        matched = 0
        run_id = f"hist-osha-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        for h in historical:
            h_eid, h_name, h_state, h_city, h_name_std, h_name_agg = h

            cur.execute("""
                SELECT establishment_id, estab_name
                FROM osha_establishments
                WHERE LOWER(TRIM(estab_name)) = %s
                  AND UPPER(site_state) = %s
                LIMIT 1
            """, [h_name_std, (h_state or "").upper()])
            match = cur.fetchone()

            if match and not dry_run:
                evidence = {
                    "historical_employer": h_name,
                    "osha_establishment": match[1],
                    "state": h_state,
                    "analysis_type": "post_union_departure",
                }
                cur.execute("""
                    INSERT INTO unified_match_log
                        (run_id, source_system, source_id, target_system, target_id,
                         match_method, match_tier, confidence_band, confidence_score,
                         evidence, status)
                    VALUES (%s, 'osha', %s, 'f7', %s, %s, 'deterministic', 'MEDIUM', 0.80, %s, 'active')
                    ON CONFLICT DO NOTHING
                """, [run_id, str(match[0]), str(h_eid), "HISTORICAL_NAME_STATE",
                      json.dumps(evidence)])
                matched += 1

                if matched % 500 == 0:
                    conn.commit()
                    print(f"  Matched {matched:,}...")

        if not dry_run:
            conn.commit()

        print(f"\nHistorical OSHA matches: {matched:,} / {len(historical):,}")
        return matched


def main():
    parser = argparse.ArgumentParser(description="Match historical employers to OSHA/WHD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, help="Limit employers to process")
    args = parser.parse_args()

    conn = get_connection()
    try:
        match_historical_to_osha(conn, args.dry_run, args.limit)
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
