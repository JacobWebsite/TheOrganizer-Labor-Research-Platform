"""
Corroborate low-confidence matches by comparing city/ZIP/NAICS between
source records and F7 employer records.

Matches in the 0.75-0.90 band that are currently score_eligible=FALSE
can be promoted to score_eligible=TRUE if they have sufficient
corroboration evidence (city match, ZIP match, NAICS match).

Corroboration scoring:
  - City match: +2 points
  - ZIP match (5-digit): +3 points
  - NAICS 2-digit match: +2 points
  - Threshold: >= 2 points -> promote to score_eligible=TRUE

Run:
    py scripts/matching/corroborate_matches.py                # dry-run
    py scripts/matching/corroborate_matches.py --commit       # apply promotions
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


PROMOTION_THRESHOLD = 2


def corroborate_osha(conn):
    """Compute corroboration scores for OSHA matches in the quarantine band."""
    sql = """
        SELECT m.id, m.establishment_id, m.f7_employer_id, m.match_confidence, m.match_method,
            (CASE WHEN UPPER(TRIM(oe.site_city)) = UPPER(TRIM(f7.city))
                  AND oe.site_city IS NOT NULL AND f7.city IS NOT NULL THEN 2 ELSE 0 END)
          + (CASE WHEN LEFT(oe.site_zip, 5) = LEFT(f7.zip, 5)
                  AND oe.site_zip IS NOT NULL AND f7.zip IS NOT NULL THEN 3 ELSE 0 END)
          + (CASE WHEN LEFT(oe.naics_code, 2) = LEFT(f7.naics, 2)
                  AND oe.naics_code IS NOT NULL AND f7.naics IS NOT NULL THEN 2 ELSE 0 END)
          AS corroboration_score
        FROM osha_f7_matches m
        JOIN osha_establishments oe ON oe.establishment_id = m.establishment_id
        JOIN f7_employers_deduped f7 ON f7.employer_id = m.f7_employer_id
        WHERE m.score_eligible = FALSE
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def corroborate_whd(conn):
    """Compute corroboration scores for WHD matches."""
    sql = """
        SELECT m.case_id AS id, m.case_id, m.f7_employer_id, m.match_confidence, m.match_method,
            (CASE WHEN UPPER(TRIM(wc.city)) = UPPER(TRIM(f7.city))
                  AND wc.city IS NOT NULL AND f7.city IS NOT NULL THEN 2 ELSE 0 END)
          + (CASE WHEN LEFT(wc.zip_code, 5) = LEFT(f7.zip, 5)
                  AND wc.zip_code IS NOT NULL AND f7.zip IS NOT NULL THEN 3 ELSE 0 END)
          + (CASE WHEN LEFT(wc.naics_code, 2) = LEFT(f7.naics, 2)
                  AND wc.naics_code IS NOT NULL AND f7.naics IS NOT NULL THEN 2 ELSE 0 END)
          AS corroboration_score
        FROM whd_f7_matches m
        JOIN whd_cases wc ON wc.case_id = m.case_id
        JOIN f7_employers_deduped f7 ON f7.employer_id = m.f7_employer_id
        WHERE m.score_eligible = FALSE
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def corroborate_sam(conn):
    """Compute corroboration scores for SAM matches."""
    sql = """
        SELECT m.uei AS id, m.uei, m.f7_employer_id, m.match_confidence, m.match_method,
            (CASE WHEN UPPER(TRIM(se.physical_city)) = UPPER(TRIM(f7.city))
                  AND se.physical_city IS NOT NULL AND f7.city IS NOT NULL THEN 2 ELSE 0 END)
          + (CASE WHEN LEFT(se.physical_zip, 5) = LEFT(f7.zip, 5)
                  AND se.physical_zip IS NOT NULL AND f7.zip IS NOT NULL THEN 3 ELSE 0 END)
          AS corroboration_score
        FROM sam_f7_matches m
        JOIN sam_entities se ON se.uei = m.uei
        JOIN f7_employers_deduped f7 ON f7.employer_id = m.f7_employer_id
        WHERE m.score_eligible = FALSE
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def corroborate_n990(conn):
    """Compute corroboration scores for 990 matches (limited: no city/zip on 990 filers)."""
    # 990 filers don't have city/zip in our schema, so corroboration is minimal
    # Just return empty - these stay as-is
    return []


def score_distribution(rows, threshold):
    """Analyze corroboration score distribution."""
    if not rows:
        return {"total": 0, "promotable": 0, "stay_demoted": 0, "by_score": {}}
    scores = [r[5] for r in rows]  # corroboration_score is index 5
    promotable = sum(1 for s in scores if s >= threshold)
    by_score = {}
    for s in scores:
        by_score[s] = by_score.get(s, 0) + 1
    return {
        "total": len(rows),
        "promotable": promotable,
        "stay_demoted": len(rows) - promotable,
        "by_score": dict(sorted(by_score.items())),
    }


def promote_matches(conn, table, pk_col, rows, threshold, commit=False):
    """Promote matches with corroboration >= threshold to score_eligible=TRUE."""
    promotable_ids = [r[0] for r in rows if r[5] >= threshold]
    if not promotable_ids or not commit:
        return len(promotable_ids)

    with conn.cursor() as cur:
        # Batch update
        from psycopg2.extras import execute_batch
        sql = f"UPDATE {table} SET score_eligible = TRUE WHERE {pk_col} = %s"
        execute_batch(cur, sql, [(pid,) for pid in promotable_ids], page_size=1000)
    conn.commit()
    return len(promotable_ids)


def main():
    parser = argparse.ArgumentParser(description="Corroborate quarantine-band matches")
    parser.add_argument("--commit", action="store_true", help="Apply promotions")
    parser.add_argument("--threshold", type=int, default=PROMOTION_THRESHOLD,
                        help="Corroboration score threshold for promotion (default: 2)")
    args = parser.parse_args()

    conn = get_connection()
    threshold = args.threshold

    print(f"=== Match Corroboration (threshold >= {threshold}) ===\n")

    # OSHA
    osha_rows = corroborate_osha(conn)
    osha_dist = score_distribution(osha_rows, threshold)
    print(f"  OSHA: {osha_dist['total']} in quarantine band")
    print(f"    Score distribution: {osha_dist['by_score']}")
    print(f"    Promotable: {osha_dist['promotable']}, Stay demoted: {osha_dist['stay_demoted']}")

    # WHD
    whd_rows = corroborate_whd(conn)
    whd_dist = score_distribution(whd_rows, threshold)
    print(f"  WHD:  {whd_dist['total']} in quarantine band")
    print(f"    Score distribution: {whd_dist['by_score']}")
    print(f"    Promotable: {whd_dist['promotable']}, Stay demoted: {whd_dist['stay_demoted']}")

    # SAM
    sam_rows = corroborate_sam(conn)
    sam_dist = score_distribution(sam_rows, threshold)
    print(f"  SAM:  {sam_dist['total']} in quarantine band")
    print(f"    Score distribution: {sam_dist['by_score']}")
    print(f"    Promotable: {sam_dist['promotable']}, Stay demoted: {sam_dist['stay_demoted']}")

    # 990 (minimal corroboration possible)
    n990_rows = corroborate_n990(conn)
    print(f"  990:  0 corroborated (no city/zip in schema)")

    total_promotable = osha_dist["promotable"] + whd_dist["promotable"] + sam_dist["promotable"]
    total_quarantine = osha_dist["total"] + whd_dist["total"] + sam_dist["total"]
    print(f"\n  TOTAL: {total_promotable}/{total_quarantine} matches promotable")

    if not args.commit:
        print("\nDRY RUN. Use --commit to apply promotions.")
        conn.close()
        return

    print("\nApplying promotions...")
    p1 = promote_matches(conn, "osha_f7_matches", "id", osha_rows, threshold, commit=True)
    p2 = promote_matches(conn, "whd_f7_matches", "case_id", whd_rows, threshold, commit=True)
    p3 = promote_matches(conn, "sam_f7_matches", "uei", sam_rows, threshold, commit=True)
    print(f"  OSHA: {p1} promoted")
    print(f"  WHD:  {p2} promoted")
    print(f"  SAM:  {p3} promoted")
    print(f"\n  Total promoted: {p1 + p2 + p3}")

    conn.close()


if __name__ == "__main__":
    main()
