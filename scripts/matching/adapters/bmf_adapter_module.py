"""
IRS Business Master File (BMF) adapter for deterministic matching.

Provides load_unmatched(), load_all(), and write_legacy() functions
compatible with run_deterministic.py CLI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """
    Load IRS BMF nonprofits not yet matched in unified_match_log.

    Returns list of dicts with: id, name, state, city, zip, naics, ein, address
    """
    sql = """
        SELECT
            b.ein,
            b.org_name,
            b.state,
            b.city,
            b.zip_code
        FROM irs_bmf b
        LEFT JOIN unified_match_log uml
            ON uml.source_system = 'bmf'
            AND uml.source_id = b.ein
            AND uml.status = 'active'
        WHERE uml.id IS NULL
          AND b.org_name IS NOT NULL
          AND b.ein IS NOT NULL
    """

    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],           # ein
            "name": r[1],         # org_name
            "state": r[2],        # state
            "city": r[3],         # city
            "zip": r[4],          # zip_code
            "naics": None,        # IRS BMF doesn't have NAICS
            "ein": r[0],          # ein
            "address": None,      # IRS BMF doesn't have address
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL IRS BMF nonprofits (for re-matching)."""
    sql = """
        SELECT
            b.ein,
            b.org_name,
            b.state,
            b.city,
            b.zip_code
        FROM irs_bmf b
        WHERE b.org_name IS NOT NULL
          AND b.ein IS NOT NULL
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
            "naics": None,  # IRS BMF doesn't have NAICS
            "ein": r[0],
            "address": None,
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """
    Write IRS BMF matches to corporate_identifier_crosswalk.

    Updates crosswalk table with EIN for matched employers.
    """
    if not matches:
        return 0

    print(f"  Writing {len(matches):,} matches to corporate_identifier_crosswalk...")

    with conn.cursor() as cur:
        updated = 0

        for match in matches:
            f7_id = match['target_id']
            ein = match['source_id']

            # Upsert crosswalk: update EIN if row exists, otherwise insert
            cur.execute("""
                UPDATE corporate_identifier_crosswalk
                SET ein = COALESCE(ein, %s)
                WHERE f7_employer_id = %s AND ein IS NULL
            """, (ein, f7_id))
            if cur.rowcount == 0:
                # No existing row to update (or already has EIN) — insert if missing
                cur.execute("""
                    INSERT INTO corporate_identifier_crosswalk (f7_employer_id, ein)
                    SELECT %s, %s
                    WHERE EXISTS (
                        SELECT 1 FROM f7_employers_deduped WHERE employer_id = %s
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM corporate_identifier_crosswalk WHERE f7_employer_id = %s
                    )
                """, (f7_id, ein, f7_id, f7_id))

            if cur.rowcount > 0:
                updated += 1

        conn.commit()

    print(f"  Updated {updated:,} crosswalk rows")
    return updated
