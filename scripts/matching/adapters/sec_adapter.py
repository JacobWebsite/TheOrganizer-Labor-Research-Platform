#!/usr/bin/env python3
"""
SEC EDGAR source adapter (stub).

This adapter only loads SEC source records for deterministic matching.
Matching and writeback logic is handled separately.
"""
import sys
from pathlib import Path

from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection


class SECAdapter:
    def __init__(self):
        self.source_system = "sec_edgar"
        self.target_system = "f7_employers_deduped"

    def load_unmatched(self, limit=None):
        """
        Load SEC companies not yet matched as active in unified_match_log.
        """
        conn = get_connection(cursor_factory=RealDictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'sec_companies'
                    """
                )
                columns = {row["column_name"] for row in cur.fetchall()}
                state_expr = self._state_expr(columns)
                naics_expr = "s.naics_code" if "naics_code" in columns else "NULL::text AS naics_code"

                if limit is not None:
                    cur.execute(
                        f"""
                        SELECT
                            s.cik::text AS source_id,
                            s.company_name,
                            s.ein,
                            {state_expr},
                            s.sic_code,
                            {naics_expr}
                        FROM sec_companies s
                        LEFT JOIN unified_match_log uml
                            ON uml.source_system = %s
                            AND uml.source_id = s.cik::text
                            AND uml.status = %s
                        WHERE uml.id IS NULL
                        LIMIT %s
                        """,
                        (self.source_system, "active", limit),
                    )
                else:
                    cur.execute(
                        f"""
                        SELECT
                            s.cik::text AS source_id,
                            s.company_name,
                            s.ein,
                            {state_expr},
                            s.sic_code,
                            {naics_expr}
                        FROM sec_companies s
                        LEFT JOIN unified_match_log uml
                            ON uml.source_system = %s
                            AND uml.source_id = s.cik::text
                            AND uml.status = %s
                        WHERE uml.id IS NULL
                        """,
                        (self.source_system, "active"),
                    )
                return cur.fetchall()
        finally:
            conn.close()

    def load_all(self, limit=None):
        """
        Load all SEC companies for full matching runs.
        """
        conn = get_connection(cursor_factory=RealDictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'sec_companies'
                    """
                )
                columns = {row["column_name"] for row in cur.fetchall()}
                state_expr = self._state_expr(columns)
                naics_expr = "s.naics_code" if "naics_code" in columns else "NULL::text AS naics_code"

                if limit is not None:
                    cur.execute(
                        f"""
                        SELECT
                            s.cik::text AS source_id,
                            s.company_name,
                            s.ein,
                            {state_expr},
                            s.sic_code,
                            {naics_expr}
                        FROM sec_companies s
                        LIMIT %s
                        """,
                        (limit,),
                    )
                else:
                    cur.execute(
                        f"""
                        SELECT
                            s.cik::text AS source_id,
                            s.company_name,
                            s.ein,
                            {state_expr},
                            s.sic_code,
                            {naics_expr}
                        FROM sec_companies s
                        """
                    )
                return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _state_expr(columns):
        has_state = "state" in columns
        has_soi = "state_of_incorporation" in columns
        if has_state and has_soi:
            return "COALESCE(s.state, s.state_of_incorporation) AS state"
        if has_state:
            return "s.state"
        if has_soi:
            return "s.state_of_incorporation AS state"
        return "NULL::text AS state"


    def write_legacy(self, conn, matches):
        """
        Write SEC matches to corporate_identifier_crosswalk.

        Updates crosswalk table with CIK for matched employers.
        Only updates rows where f7_employer_id exists (creates bridge).
        """
        if not matches:
            return 0

        print(f"  Writing {len(matches):,} matches to corporate_identifier_crosswalk...")

        with conn.cursor() as cur:
            # Get EIN from f7_employers_deduped for matched employers
            updated = 0
            for match in matches:
                f7_id = match['target_id']
                cik = match['source_id']

                # Insert or update crosswalk
                # Use f7_employer_id as key to link to employer, then backfill EIN if available
                cur.execute("""
                    -- First, get EIN from f7 employer
                    WITH employer_data AS (
                        SELECT employer_id, ein
                        FROM f7_employers_deduped
                        WHERE employer_id = %s
                    )
                    INSERT INTO corporate_identifier_crosswalk (f7_employer_id, sec_cik, ein)
                    SELECT employer_id, %s, ein
                    FROM employer_data
                    ON CONFLICT (f7_employer_id)
                    DO UPDATE SET
                        sec_cik = EXCLUDED.sec_cik,
                        ein = COALESCE(corporate_identifier_crosswalk.ein, EXCLUDED.ein)
                """, (f7_id, cik))

                updated += cur.rowcount

            conn.commit()

        print(f"  Updated {updated:,} crosswalk rows")
        return updated


if __name__ == "__main__":
    adapter = SECAdapter()
    sample = adapter.load_unmatched(limit=10)
    print(f"Unmatched SEC companies: {len(sample)}")
    if sample:
        print(sample[0])
