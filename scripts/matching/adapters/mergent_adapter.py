"""
Mergent source adapter for deterministic matching.

Loads Mergent employers not yet matched to F7 employers,
normalizes to the common input schema.

Mergent has EIN for ~35% of records (Tier 1 eligible).
Uses DUNS as the source ID.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))


def load_unmatched(conn, limit=None):
    """Load Mergent employers not yet in mergent_f7_matches."""
    sql = """
        SELECT me.duns, me.company_name, me.state, me.city,
               me.zip, me.naics_primary, me.ein, me.street_address
        FROM mergent_employers me
        LEFT JOIN mergent_f7_matches m ON me.duns = m.duns
        WHERE m.duns IS NULL
          AND me.company_name IS NOT NULL
          AND me.duns IS NOT NULL
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "state": r[2],
            "city": r[3],
            "zip": r[4],
            "naics": r[5],
            "ein": r[6],
            "address": r[7],
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL Mergent employers (for re-matching)."""
    sql = """
        SELECT duns, company_name, state, city,
               zip, naics_primary, ein, street_address
        FROM mergent_employers
        WHERE company_name IS NOT NULL
          AND duns IS NOT NULL
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "state": r[2],
            "city": r[3],
            "zip": r[4],
            "naics": r[5],
            "ein": r[6],
            "address": r[7],
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """Write matches to mergent_f7_matches and update mergent_employers.

    Uses ON CONFLICT DO UPDATE so re-runs can upgrade match quality.
    Also writes back to matched_f7_employer_id on mergent_employers
    for backward compatibility with existing scoring/enrichment queries.
    """
    from psycopg2.extras import execute_batch

    # Insert into legacy match table
    sql_legacy = """
        INSERT INTO mergent_f7_matches
            (duns, f7_employer_id, match_method, match_confidence, score_eligible)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (duns) DO UPDATE SET
            f7_employer_id = EXCLUDED.f7_employer_id,
            match_method = EXCLUDED.match_method,
            match_confidence = EXCLUDED.match_confidence,
            score_eligible = EXCLUDED.score_eligible
    """
    rows = [
        (m["source_id"], m["target_id"], m["method"].upper(), m["score"],
         m["score"] >= 0.85 or m["method"].upper() in ("EIN_EXACT", "CROSSWALK", "CIK_BRIDGE"))
        for m in matches
    ]
    with conn.cursor() as cur:
        execute_batch(cur, sql_legacy, rows, page_size=1000)

    # Write back to mergent_employers for backward compat
    sql_writeback = """
        UPDATE mergent_employers
        SET matched_f7_employer_id = %s,
            match_method = %s,
            match_confidence = %s
        WHERE duns = %s
    """
    wb_rows = [
        (m["target_id"], m["method"].upper(), m["score"], m["source_id"])
        for m in matches
    ]
    with conn.cursor() as cur:
        execute_batch(cur, sql_writeback, wb_rows, page_size=1000)

    conn.commit()


SOURCE_SYSTEM = "mergent"
