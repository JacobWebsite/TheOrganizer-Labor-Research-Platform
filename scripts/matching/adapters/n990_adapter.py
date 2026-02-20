"""
990 source adapter for deterministic matching.

Loads national 990 filers not yet matched to F7 employers,
normalizes to the common input schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """Load 990 filers not yet in national_990_f7_matches."""
    sql = """
        SELECT n.id, n.business_name, n.state, n.city,
               n.zip_code, n.ntee_code, n.ein, n.street_address
        FROM national_990_filers n
        LEFT JOIN national_990_f7_matches m ON n.id = m.n990_id
        WHERE m.n990_id IS NULL
          AND n.business_name IS NOT NULL
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
    """Load ALL 990 filers."""
    sql = """
        SELECT id, business_name, state, city,
               zip_code, ntee_code, ein, street_address
        FROM national_990_filers
        WHERE business_name IS NOT NULL
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
    """Write matches back to national_990_f7_matches for backward compat.

    Uses ON CONFLICT DO UPDATE so re-runs can upgrade match quality.
    Targets the unique index on n990_id.
    """
    from psycopg2.extras import execute_batch
    # Two overlapping unique constraints: PK(f7_employer_id, ein) + UNIQUE(n990_id).
    # Use DO NOTHING here; rebuild_legacy_tables.py produces the correct final state from UML.
    sql = """
        INSERT INTO national_990_f7_matches (n990_id, ein, f7_employer_id, match_method, match_confidence, match_source)
        VALUES (%s, %s, %s, %s, %s, 'DETERMINISTIC_V2')
        ON CONFLICT DO NOTHING
    """
    # Deduplicate by (f7_employer_id, ein) to avoid within-batch conflicts
    seen = set()
    rows = []
    for m in matches:
        ein = m.get("evidence", {}).get("ein") or ""
        key = (m["target_id"], ein)
        if key not in seen:
            seen.add(key)
            rows.append((m["source_id"], ein, m["target_id"], m["method"], m["score"]))
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()


SOURCE_SYSTEM = "990"
