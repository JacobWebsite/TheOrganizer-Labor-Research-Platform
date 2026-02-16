"""
WHD source adapter for deterministic matching.

Loads WHD cases not yet matched to F7 employers,
normalizes to the common input schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """Load WHD cases not yet in whd_f7_matches."""
    sql = """
        SELECT w.case_id, w.trade_name, w.state, w.city,
               w.zip_code, w.naics_code, w.street_address
        FROM whd_cases w
        LEFT JOIN whd_f7_matches m ON w.case_id = m.case_id
        WHERE m.case_id IS NULL
          AND w.trade_name IS NOT NULL
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
            "naics": str(r[5]) if r[5] else None,
            "ein": None,
            "address": r[6],
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL WHD cases."""
    sql = """
        SELECT case_id, trade_name, state, city,
               zip_code, naics_code, street_address
        FROM whd_cases
        WHERE trade_name IS NOT NULL
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
            "naics": str(r[5]) if r[5] else None,
            "ein": None,
            "address": r[6],
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """Write matches back to whd_f7_matches for backward compat."""
    from psycopg2.extras import execute_batch
    sql = """
        INSERT INTO whd_f7_matches (case_id, f7_employer_id, match_method, match_confidence, match_source)
        VALUES (%s, %s, %s, %s, 'DETERMINISTIC_V2')
        ON CONFLICT (case_id) DO NOTHING
    """
    rows = [(m["source_id"], m["target_id"], m["method"], m["score"]) for m in matches]
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()


SOURCE_SYSTEM = "whd"
