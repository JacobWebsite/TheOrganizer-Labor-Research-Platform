"""
SAM source adapter for deterministic matching.

Loads SAM.gov entities not yet matched to F7 employers,
normalizes to the common input schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """Load SAM entities not yet in sam_f7_matches."""
    sql = """
        SELECT s.uei, s.legal_business_name, s.physical_state,
               s.physical_city, s.physical_zip,
               s.naics_primary, s.physical_address
        FROM sam_entities s
        LEFT JOIN sam_f7_matches m ON s.uei = m.uei
        WHERE m.uei IS NULL
          AND s.legal_business_name IS NOT NULL
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
            "ein": None,
            "address": r[6],
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL SAM entities."""
    sql = """
        SELECT uei, legal_business_name, physical_state,
               physical_city, physical_zip,
               naics_primary, physical_address
        FROM sam_entities
        WHERE legal_business_name IS NOT NULL
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
            "ein": None,
            "address": r[6],
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """Write matches back to sam_f7_matches for backward compat."""
    from psycopg2.extras import execute_batch
    sql = """
        INSERT INTO sam_f7_matches (uei, f7_employer_id, match_method, match_confidence, match_source)
        VALUES (%s, %s, %s, %s, 'DETERMINISTIC_V2')
        ON CONFLICT (uei) DO NOTHING
    """
    rows = [(m["source_id"], m["target_id"], m["method"], m["score"]) for m in matches]
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()


SOURCE_SYSTEM = "sam"
