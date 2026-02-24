"""
CorpWatch source adapter for deterministic matching.

Loads CorpWatch companies (US only, most_recent snapshot) not yet matched
to F7 employers, normalizes to the common input schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """Load CorpWatch US companies not yet matched in unified_match_log."""
    sql = """
        SELECT
            c.cw_id::text,
            c.company_name,
            c.ein,
            c.state,
            c.city,
            c.zip,
            c.sic_code
        FROM corpwatch_companies c
        LEFT JOIN unified_match_log uml
            ON uml.source_system = 'corpwatch'
            AND uml.source_id = c.cw_id::text
            AND uml.status = 'active'
        WHERE uml.id IS NULL
          AND c.company_name IS NOT NULL
          AND c.is_us = TRUE
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],           # cw_id as text
            "name": r[1],         # company_name
            "state": r[3],        # state
            "city": r[4],         # city
            "zip": r[5],          # zip
            "naics": None,        # CorpWatch has SIC, not NAICS
            "ein": r[2],          # ein
            "address": None,      # no street address in companies table
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL US CorpWatch companies (for re-matching)."""
    sql = """
        SELECT
            c.cw_id::text,
            c.company_name,
            c.ein,
            c.state,
            c.city,
            c.zip,
            c.sic_code
        FROM corpwatch_companies c
        WHERE c.company_name IS NOT NULL
          AND c.is_us = TRUE
    """
    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "state": r[3],
            "city": r[4],
            "zip": r[5],
            "naics": None,
            "ein": r[2],
            "address": None,
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """Write matches to corpwatch_f7_matches for backward compat.

    Uses ON CONFLICT DO UPDATE so re-runs can upgrade match quality.
    """
    if not matches:
        return 0

    from psycopg2.extras import execute_batch

    sql = """
        INSERT INTO corpwatch_f7_matches (cw_id, f7_employer_id, match_method, match_confidence)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (cw_id) DO UPDATE SET
            f7_employer_id = EXCLUDED.f7_employer_id,
            match_method = EXCLUDED.match_method,
            match_confidence = EXCLUDED.match_confidence
    """
    rows = [
        (int(m["source_id"]), m["target_id"], m["method"], m["score"])
        for m in matches
    ]
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()
    return len(rows)


SOURCE_SYSTEM = "corpwatch"
