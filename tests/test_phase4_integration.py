import pytest
from psycopg2.extras import RealDictCursor

from db_config import get_connection


def fetch_scalar(query, params=None, key="value"):
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return row[key] if row else None
    finally:
        conn.close()


class TestSECIntegration:
    def test_sec_companies_loaded(self):
        count = fetch_scalar("SELECT COUNT(*) AS value FROM sec_companies")
        assert count > 500000, f"Expected >500K SEC companies, got {count}"

    def test_sec_matches_exist(self):
        count = fetch_scalar(
            """
            SELECT COUNT(*) AS value
            FROM unified_match_log
            WHERE source_system IN ('sec', 'sec_edgar')
              AND status = 'active'
            """
        )
        assert count > 0, "No active SEC matches found"

    def test_sec_crosswalk_integration(self):
        count = fetch_scalar(
            """
            SELECT COUNT(*) AS value
            FROM corporate_identifier_crosswalk
            WHERE sec_cik IS NOT NULL
            """
        )
        assert count > 0, "No SEC CIKs in crosswalk"


class TestBLSDensity:
    def test_national_industry_density(self):
        count = fetch_scalar(
            """
            SELECT COUNT(DISTINCT industry_code) AS value
            FROM bls_national_industry_density
            WHERE year = 2024
            """
        )
        assert count == 9, f"Expected 9 industries, got {count}"

    def test_state_density(self):
        count = fetch_scalar(
            """
            SELECT COUNT(DISTINCT state) AS value
            FROM bls_state_density
            WHERE year = 2024
            """
        )
        assert count == 51, f"Expected 51 states, got {count}"

    def test_state_industry_estimates(self):
        count = fetch_scalar(
            """
            SELECT COUNT(*) AS value
            FROM estimated_state_industry_density
            WHERE year = 2024
            """
        )
        assert count == 459, f"Expected 459 estimates, got {count}"

    def test_foreign_key_integrity(self):
        count = fetch_scalar(
            """
            SELECT COUNT(*) AS value
            FROM information_schema.table_constraints
            WHERE table_name = 'estimated_state_industry_density'
              AND constraint_type = 'FOREIGN KEY'
            """
        )
        assert count >= 2, f"Expected at least 2 foreign keys, got {count}"


class TestOEWSIntegration:
    def test_matrix_loaded(self):
        count = fetch_scalar("SELECT COUNT(*) AS value FROM bls_industry_occupation_matrix")
        assert count > 60000, f"Expected >60K rows, got {count}"

    def test_unique_industries(self):
        count = fetch_scalar(
            """
            SELECT COUNT(DISTINCT industry_code) AS value
            FROM bls_industry_occupation_matrix
            """
        )
        assert count >= 420, f"Expected >=420 industries, got {count}"

    def test_unique_occupations(self):
        count = fetch_scalar(
            """
            SELECT COUNT(DISTINCT occupation_code) AS value
            FROM bls_industry_occupation_matrix
            """
        )
        assert count >= 800, f"Expected >=800 occupations, got {count}"

    def test_top_occupations_view(self):
        count = fetch_scalar(
            """
            SELECT COUNT(*) AS value
            FROM v_industry_top_occupations
            """
        )
        assert count > 0, "Expected v_industry_top_occupations to return rows"


class TestDataQuality:
    def test_no_orphan_sec_bmf_matches(self):
        orphans = fetch_scalar(
            """
            SELECT COUNT(*) AS value
            FROM unified_match_log uml
            LEFT JOIN f7_employers_deduped f7
                ON uml.target_id = f7.employer_id
            WHERE uml.status = 'active'
              AND uml.source_system IN ('sec', 'sec_edgar', 'bmf')
              AND f7.employer_id IS NULL
            """
        )
        assert orphans == 0, f"Found {orphans} orphan SEC/BMF matches"

    def test_precision_preservation(self):
        scale = fetch_scalar(
            """
            SELECT numeric_scale AS value
            FROM information_schema.columns
            WHERE table_name = 'bls_national_industry_density'
              AND column_name = 'total_employed_thousands'
            """
        )
        assert scale is not None and int(scale) >= 1, f"Expected decimal precision scale >=1, got {scale}"
