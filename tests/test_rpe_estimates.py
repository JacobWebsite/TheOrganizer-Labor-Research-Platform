"""Tests for RPE workforce size estimation (Task 3-11)."""
import pytest
from db_config import get_connection


class TestCensusRpeRatios:
    """Verify census_rpe_ratios table has valid data."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_table_exists_and_has_rows(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM census_rpe_ratios")
            cnt = cur.fetchone()[0]
            assert cnt > 1000, f"Expected >1000 NAICS codes, got {cnt}"

    def test_has_multiple_naics_granularities(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT LENGTH(naics_code) AS digits, COUNT(*) AS cnt
                FROM census_rpe_ratios
                WHERE geo_level = 'national' OR geo_level IS NULL
                GROUP BY LENGTH(naics_code)
                ORDER BY digits
            """)
            rows = cur.fetchall()
            granularities = {r[0] for r in rows}
            assert 2 in granularities, "Missing 2-digit NAICS codes"
            assert 3 in granularities or 4 in granularities, "Missing 3 or 4-digit codes"

    def test_rpe_values_positive(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios WHERE rpe <= 0
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} NAICS codes with non-positive RPE"

    def test_rpe_range_reasonable(self):
        """National RPE should generally be between $1K and $100M per employee."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT MIN(rpe), MAX(rpe), AVG(rpe)
                FROM census_rpe_ratios
                WHERE geo_level = 'national' OR geo_level IS NULL
            """)
            row = cur.fetchone()
            min_rpe, max_rpe, avg_rpe = float(row[0]), float(row[1]), float(row[2])
            assert min_rpe > 1000, f"Min RPE too low: ${min_rpe:,.0f}"
            assert max_rpe < 100000000, f"Max RPE too high: ${max_rpe:,.0f}"
            assert 50000 < avg_rpe < 2000000, f"Avg RPE out of range: ${avg_rpe:,.0f}"

    def test_major_sectors_covered(self):
        """Major NAICS sectors should have RPE data (2 or 3-digit)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT naics_code FROM census_rpe_ratios
                WHERE LENGTH(naics_code) <= 3
                  AND (geo_level = 'national' OR geo_level IS NULL)
            """)
            codes = {r[0] for r in cur.fetchall()}
            # Census uses combined ranges: 31-33, 44-45, 48-49 at 3-digit level
            # Check that key sectors are covered (exact 2-digit or 3-digit prefix)
            expected_prefixes = ['23', '42', '51', '52', '54', '56', '62', '72',
                                 '31', '44', '48']  # 31x, 44x, 48x at 3-digit
            for prefix in expected_prefixes:
                found = any(c.startswith(prefix) for c in codes)
                assert found, f"Missing sector prefix: {prefix}"

    def test_employee_counts_positive(self):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE employee_count IS NULL OR employee_count <= 0
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} codes with invalid employee count"


class TestRpeGeoLevels:
    """Verify geographic RPE data from SUSB."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_geo_level_column_exists(self):
        """geo_level column should exist on census_rpe_ratios."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'census_rpe_ratios' AND column_name = 'geo_level'
            """)
            assert cur.fetchone()[0] == 1, "geo_level column missing"

    def test_all_three_geo_levels_present(self):
        """Should have national, state, and county rows."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT COALESCE(geo_level, 'national')
                FROM census_rpe_ratios
            """)
            levels = {r[0] for r in cur.fetchall()}
            assert 'national' in levels, "Missing national rows"
            assert 'state' in levels, "Missing state rows"
            assert 'county' in levels, "Missing county rows"

    def test_state_rows_have_valid_rpe(self):
        """State-level rows should have positive RPE values."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE geo_level = 'state' AND rpe <= 0
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} state rows with non-positive RPE"

    def test_county_rows_have_valid_rpe(self):
        """County-level rows should have positive RPE values."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE geo_level = 'county' AND rpe <= 0
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} county rows with non-positive RPE"

    def test_state_rows_have_state_code(self):
        """All state-level rows should have a 2-char state code."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE geo_level = 'state' AND (state IS NULL OR LENGTH(state) != 2)
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} state rows missing state code"

    def test_county_rows_have_county_fips(self):
        """All county-level rows should have a 5-char county FIPS."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE geo_level = 'county' AND (county_fips IS NULL OR LENGTH(county_fips) != 5)
            """)
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} county rows missing county FIPS"

    def test_state_rpe_count_exceeds_national(self):
        """State RPE should have more rows than national (states x NAICS)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE geo_level = 'state'
            """)
            state_cnt = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*) FROM census_rpe_ratios
                WHERE geo_level = 'national' OR geo_level IS NULL
            """)
            national_cnt = cur.fetchone()[0]
            assert state_cnt > national_cnt, (
                f"State count ({state_cnt}) should exceed national ({national_cnt})"
            )

    def test_state_index_exists(self):
        """Composite index on (state, naics_code) should exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'census_rpe_ratios'
                  AND indexname = 'idx_rpe_state_naics'
            """)
            assert cur.fetchone()[0] == 1, "idx_rpe_state_naics index missing"

    def test_county_index_exists(self):
        """Composite index on (county_fips, naics_code) should exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'census_rpe_ratios'
                  AND indexname = 'idx_rpe_county_naics'
            """)
            assert cur.fetchone()[0] == 1, "idx_rpe_county_naics index missing"

    def test_multiple_states_covered(self):
        """At least 40 states should have RPE data."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT state) FROM census_rpe_ratios
                WHERE geo_level = 'state'
            """)
            cnt = cur.fetchone()[0]
            assert cnt >= 40, f"Only {cnt} states with RPE data, expected >= 40"

    def test_multiple_counties_covered(self):
        """At least 1000 counties should have RPE data."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT county_fips) FROM census_rpe_ratios
                WHERE geo_level = 'county'
            """)
            cnt = cur.fetchone()[0]
            assert cnt >= 1000, f"Only {cnt} counties with RPE data, expected >= 1000"


class TestRpeNaicsCoverage:
    """Verify RPE NAICS codes match employer NAICS codes."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_high_coverage_rate(self):
        """Most employers with NAICS should find an RPE match."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM master_employers
                WHERE naics IS NOT NULL AND LENGTH(TRIM(naics)) >= 2
                  AND employee_count > 10
            """)
            total = cur.fetchone()[0]
            if total == 0:
                pytest.skip("No employers with NAICS + employee_count")

            cur.execute("""
                SELECT COUNT(*)
                FROM master_employers me
                WHERE me.naics IS NOT NULL AND LENGTH(TRIM(me.naics)) >= 2
                  AND me.employee_count > 10
                  AND EXISTS (
                      SELECT 1 FROM census_rpe_ratios r
                      WHERE r.rpe > 0
                        AND (r.naics_code = me.naics
                             OR r.naics_code = LEFT(me.naics, 4)
                             OR r.naics_code = LEFT(me.naics, 3)
                             OR r.naics_code = LEFT(me.naics, 2))
                  )
            """)
            covered = cur.fetchone()[0]
            pct = covered / total * 100
            assert pct > 80, f"RPE coverage only {pct:.1f}% ({covered}/{total})"


class TestRpeScorecardIntegration:
    """Verify RPE is integrated into unified scorecard."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_size_source_column_exists(self):
        """mv_unified_scorecard should have size_source column."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM pg_attribute
                WHERE attrelid = 'mv_unified_scorecard'::regclass
                  AND attname = 'size_source'
                  AND NOT attisdropped
            """)
            assert cur.fetchone()[0] == 1, "size_source column missing from mv_unified_scorecard"

    def test_size_source_values(self):
        """size_source should contain expected values."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT size_source, COUNT(*)
                FROM mv_unified_scorecard
                WHERE size_source IS NOT NULL
                GROUP BY size_source
                ORDER BY COUNT(*) DESC
            """)
            rows = cur.fetchall()
            sources = {r[0] for r in rows}
            # At minimum, company_size and f7_unit_size should be present
            assert 'company_size' in sources or 'f7_unit_size' in sources, (
                f"Expected standard size sources, got: {sources}"
            )

    def test_company_workers_populated(self):
        """company_workers should be populated for employers with size data."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM mv_unified_scorecard
                WHERE company_workers IS NOT NULL
            """)
            with_workers = cur.fetchone()[0]
            assert with_workers > 0, "No employers have company_workers populated"

    def test_rpe_estimate_count(self):
        """Check how many employers gained size from RPE (informational)."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM mv_unified_scorecard
                WHERE size_source = 'rpe_estimate'
            """)
            rpe_count = cur.fetchone()[0]
            # This is informational -- RPE may or may not have matches yet
            # depending on whether the MV has been rebuilt
            print(f"  RPE estimate employers: {rpe_count}")


class TestRpePayPerEmployee:
    """Verify pay_per_employee data quality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.conn = get_connection()
        yield
        self.conn.close()

    def test_pay_per_employee_reasonable(self):
        """Average pay per employee should be reasonable."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(pay_per_employee)
                FROM census_rpe_ratios
                WHERE pay_per_employee IS NOT NULL
            """)
            row = cur.fetchone()
            if row[0] is None:
                pytest.skip("No pay_per_employee data")
            avg_ppe = float(row[0])
            assert 20000 < avg_ppe < 200000, f"Avg pay/employee out of range: ${avg_ppe:,.0f}"
