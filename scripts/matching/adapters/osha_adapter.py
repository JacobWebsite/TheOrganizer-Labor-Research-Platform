"""
OSHA source adapter for deterministic matching.

Loads OSHA establishments not yet matched to F7 employers,
normalizes to the common input schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """Load OSHA establishments not yet in osha_f7_matches."""
    sql = """
        SELECT o.establishment_id, o.estab_name, o.site_state, o.site_city,
               o.site_zip, o.naics_code, o.site_address
        FROM osha_establishments o
        LEFT JOIN osha_f7_matches m ON o.establishment_id = m.establishment_id
        WHERE m.establishment_id IS NULL
          AND o.estab_name IS NOT NULL
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
            "state": r[2],
            "city": r[3],
            "zip": r[4],
            "naics": r[5],
            "ein": None,  # OSHA doesn't have EIN
            "address": r[6],
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL OSHA establishments (for re-matching)."""
    sql = """
        SELECT establishment_id, estab_name, site_state, site_city,
               site_zip, naics_code, site_address
        FROM osha_establishments
        WHERE estab_name IS NOT NULL
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
            "state": r[2],
            "city": r[3],
            "zip": r[4],
            "naics": r[5],
            "ein": None,
            "address": r[6],
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """Write matches back to osha_f7_matches for backward compat.

    Uses ON CONFLICT DO UPDATE so re-runs can upgrade match quality.
    """
    from psycopg2.extras import execute_batch
    sql = """
        INSERT INTO osha_f7_matches (establishment_id, f7_employer_id, match_method, match_confidence)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (establishment_id) DO UPDATE SET
            f7_employer_id = EXCLUDED.f7_employer_id,
            match_method = EXCLUDED.match_method,
            match_confidence = EXCLUDED.match_confidence
    """
    rows = [(m["source_id"], m["target_id"], m["method"], m["score"]) for m in matches]
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()


SOURCE_SYSTEM = "osha"
