"""
SEC EDGAR adapter for deterministic matching.

Provides load_unmatched(), load_all(), and write_legacy() functions
compatible with run_deterministic.py CLI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


def load_unmatched(conn, limit=None):
    """
    Load SEC companies not yet matched in unified_match_log.

    Returns list of dicts with: id, name, state, city, zip, naics, ein, address
    """
    sql = """
        SELECT
            s.cik::text,
            s.company_name,
            s.ein,
            s.state,
            s.sic_code
        FROM sec_companies s
        LEFT JOIN unified_match_log uml
            ON uml.source_system = 'sec_edgar'
            AND uml.source_id = s.cik::text
            AND uml.status = 'active'
        WHERE uml.id IS NULL
          AND s.company_name IS NOT NULL
    """

    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],           # cik
            "name": r[1],         # company_name
            "state": r[3],        # state
            "city": None,         # SEC doesn't have city
            "zip": None,          # SEC doesn't have zip
            "naics": None,        # SEC has SIC, not NAICS
            "ein": r[2],          # ein
            "address": None,      # SEC doesn't have address
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL SEC companies (for re-matching)."""
    sql = """
        SELECT
            s.cik::text,
            s.company_name,
            s.ein,
            s.state,
            s.sic_code
        FROM sec_companies s
        WHERE s.company_name IS NOT NULL
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
            "city": None,
            "zip": None,
            "naics": None,  # SEC has SIC, not NAICS
            "ein": r[2],
            "address": None,
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """
    Write SEC matches to corporate_identifier_crosswalk.

    Updates crosswalk table with sec_cik for matched employers.
    """
    if not matches:
        return 0

    print(f"  Writing {len(matches):,} matches to corporate_identifier_crosswalk...")

    with conn.cursor() as cur:
        updated = 0

        for match in matches:
            f7_id = match['target_id']
            cik = match['source_id']

            # Check if crosswalk row exists for this employer
            cur.execute("""
                SELECT id FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s
                LIMIT 1
            """, (f7_id,))

            existing = cur.fetchone()

            if existing:
                # Update existing row
                cur.execute("""
                    UPDATE corporate_identifier_crosswalk
                    SET sec_cik = %s,
                        ein = COALESCE(ein, (SELECT ein FROM sec_companies WHERE cik::text = %s))
                    WHERE f7_employer_id = %s
                """, (cik, cik, f7_id))
            else:
                # Insert new row
                cur.execute("""
                    INSERT INTO corporate_identifier_crosswalk (f7_employer_id, sec_cik, ein)
                    SELECT %s, %s, s.ein
                    FROM sec_companies s
                    WHERE s.cik::text = %s
                """, (f7_id, cik, cik))

            if cur.rowcount > 0:
                updated += 1

        conn.commit()

    print(f"  Updated {updated:,} crosswalk rows")
    return updated
