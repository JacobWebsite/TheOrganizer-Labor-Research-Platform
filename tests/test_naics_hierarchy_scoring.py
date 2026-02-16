"""
Hierarchical NAICS similarity scoring tests (Phase 5.2).

Tests that the industry density factor uses a weighted blend of
national and state-level density, with NAICS digit-match similarity
as the blending weight (6-digit=1.0 down to 2-digit=0.25).

Run with: py -m pytest tests/test_naics_hierarchy_scoring.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.scoring.create_scorecard_mv import MV_SQL


@pytest.fixture(scope="module")
def db():
    from db_config import get_connection
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


def _sql_quote(value):
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def _run_factor2(db, naics_code, site_state, national_rows, state_rows):
    """Run the Factor 2 scoring logic in isolation using CTEs that mirror the MV."""
    national_values = ",\n".join(
        f"({_sql_quote(n2)}, {float(pct)})" for n2, pct in national_rows
    )
    state_values = ",\n".join(
        f"({int(year)}, {_sql_quote(state)}, {_sql_quote(industry_code)}, {float(estimated_density)})"
        for year, state, industry_code, estimated_density in state_rows
    ) if state_rows else "(2025, 'ZZ', '000000', 0.0)"

    sql = f"""
    WITH
    target AS (
        SELECT 1::bigint AS establishment_id,
               {_sql_quote(naics_code)}::text AS naics_code,
               {_sql_quote(site_state)}::text AS site_state
    ),
    v_naics_union_density AS (
        SELECT * FROM (VALUES
            {national_values}
        ) v(naics_2digit, union_density_pct)
    ),
    estimated_state_industry_density AS (
        SELECT * FROM (VALUES
            {state_values}
        ) s(year, state, industry_code, estimated_density)
    ),
    industry_density AS (
        SELECT naics_2digit, union_density_pct FROM v_naics_union_density
    ),
    state_industry_density AS (
        SELECT
            state,
            year,
            estimated_density::numeric AS estimated_density,
            regexp_replace(COALESCE(industry_code::text, ''), '[^0-9]', '', 'g') AS industry_code_norm
        FROM estimated_state_industry_density
    ),
    industry_density_blend AS (
        SELECT
            t.establishment_id,
            COALESCE(id.union_density_pct, 0)::numeric AS national_density_pct,
            sb.estimated_density AS state_density_pct,
            COALESCE(sb.naics_similarity, 0.0)::numeric AS naics_similarity,
            CASE
                WHEN sb.estimated_density IS NULL THEN COALESCE(id.union_density_pct, 0)::numeric
                ELSE
                    (COALESCE(id.union_density_pct, 0)::numeric * (1 - COALESCE(sb.naics_similarity, 0.0)::numeric))
                    + (sb.estimated_density * COALESCE(sb.naics_similarity, 0.0)::numeric)
            END AS blended_density_pct
        FROM target t
        LEFT JOIN industry_density id
            ON id.naics_2digit = LEFT(t.naics_code, 2)
        LEFT JOIN LATERAL (
            SELECT
                s.estimated_density,
                CASE
                    WHEN regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g') = '' THEN 0.0
                    WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 6
                     AND LENGTH(s.industry_code_norm) >= 6
                     AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 6) = LEFT(s.industry_code_norm, 6) THEN 1.0
                    WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 5
                     AND LENGTH(s.industry_code_norm) >= 5
                     AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 5) = LEFT(s.industry_code_norm, 5) THEN 0.85
                    WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 4
                     AND LENGTH(s.industry_code_norm) >= 4
                     AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 4) = LEFT(s.industry_code_norm, 4) THEN 0.65
                    WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 3
                     AND LENGTH(s.industry_code_norm) >= 3
                     AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 3) = LEFT(s.industry_code_norm, 3) THEN 0.45
                    WHEN LENGTH(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')) >= 2
                     AND LENGTH(s.industry_code_norm) >= 2
                     AND LEFT(regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g'), 2) = LEFT(s.industry_code_norm, 2) THEN 0.25
                    ELSE 0.0
                END AS naics_similarity
            FROM state_industry_density s
            WHERE s.state = t.site_state
            ORDER BY naics_similarity DESC, COALESCE(s.year, 0) DESC, s.industry_code_norm
            LIMIT 1
        ) sb ON TRUE
    )
    SELECT
        naics_similarity,
        blended_density_pct,
        CASE
            WHEN {_sql_quote(naics_code)}::text IS NULL THEN 2
            WHEN COALESCE(blended_density_pct, 0) > 20 THEN 10
            WHEN COALESCE(blended_density_pct, 0) > 10 THEN 8
            WHEN COALESCE(blended_density_pct, 0) > 5 THEN 5
            ELSE 2
        END AS score_industry_density
    FROM industry_density_blend
    """

    cur = db.cursor()
    cur.execute(sql)
    return cur.fetchone()


class TestNaicsHierarchy6Digit:
    """6-digit exact match should use full state density (similarity=1.0)."""

    def test_exact_match_uses_state_density(self, db):
        sim, blended, score = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "311111", 24.0)],
        )
        assert float(sim) == pytest.approx(1.0)
        assert float(blended) == pytest.approx(24.0)
        assert score == 10


class TestNaicsHierarchyPartialMatches:
    """Partial NAICS matches should produce correct similarity gradients."""

    def test_5digit_match(self, db):
        sim, _, _ = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "311112", 30.0)],
        )
        assert float(sim) == pytest.approx(0.85)

    def test_4digit_match(self, db):
        sim, _, _ = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "311199", 30.0)],
        )
        assert float(sim) == pytest.approx(0.65)

    def test_3digit_match(self, db):
        sim, _, _ = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "311999", 30.0)],
        )
        assert float(sim) == pytest.approx(0.45)

    def test_2digit_match(self, db):
        sim, _, _ = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "319999", 30.0)],
        )
        assert float(sim) == pytest.approx(0.25)

    def test_no_match_different_sector(self, db):
        sim, _, _ = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "721111", 30.0)],
        )
        assert float(sim) == pytest.approx(0.0)


class TestNaicsHierarchyNullNaics:
    """NULL NAICS code should get default score of 2."""

    def test_null_naics_returns_default(self, db):
        sim, blended, score = _run_factor2(
            db=db,
            naics_code=None,
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "311111", 24.0)],
        )
        assert score == 2


class TestNaicsHierarchyStateDensity:
    """State density should be used when available with exact NAICS match."""

    def test_state_density_used(self, db):
        sim, blended, score = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "NY", "311111", 22.5)],
        )
        assert float(sim) == pytest.approx(1.0)
        assert float(blended) == pytest.approx(22.5)
        assert score == 10


class TestNaicsHierarchyFallback:
    """When no state density available, fall back to national density."""

    def test_no_state_match_uses_national(self, db):
        sim, blended, score = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 12.0)],
            state_rows=[(2025, "CA", "311111", 22.5)],  # Different state
        )
        # No NY match -> similarity 0.0 -> pure national
        assert float(blended) == pytest.approx(12.0)
        assert score == 8

    def test_blend_weights_correctly(self, db):
        """5-digit match (sim=0.85) should blend 85% state + 15% national."""
        sim, blended, _ = _run_factor2(
            db=db,
            naics_code="311111",
            site_state="NY",
            national_rows=[("31", 10.0)],
            state_rows=[(2025, "NY", "311112", 20.0)],
        )
        assert float(sim) == pytest.approx(0.85)
        expected = 10.0 * (1 - 0.85) + 20.0 * 0.85  # 1.5 + 17.0 = 18.5
        assert float(blended) == pytest.approx(expected, abs=0.1)


class TestNaicsHierarchyMvIntegration:
    """Verify the MV has proper industry density after the blend integration."""

    def test_mv_has_non_default_density_scores(self, db):
        """At least some establishments should have score > 2."""
        cur = db.cursor()
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE score_industry_density > 2) as non_default,
                   COUNT(*) as total
            FROM mv_organizing_scorecard
        """)
        row = cur.fetchone()
        assert row[0] > 0, "Should have some non-default density scores"
        pct = row[0] / row[1] * 100
        assert pct > 50, f"Expected >50% non-default, got {pct:.1f}%"

    def test_density_score_range(self, db):
        cur = db.cursor()
        cur.execute("SELECT MIN(score_industry_density), MAX(score_industry_density) FROM mv_organizing_scorecard")
        min_s, max_s = cur.fetchone()
        assert min_s >= 2, "Minimum industry density score should be 2"
        assert max_s <= 10, "Maximum industry density score should be 10"


class TestMvSqlTokens:
    """Verify MV_SQL contains expected tokens after NAICS precompute refactor."""

    def test_has_naics_norm_precompute(self):
        assert "naics_norm" in MV_SQL

    def test_has_industry_density_blend(self):
        assert "industry_density_blend" in MV_SQL

    def test_has_left_join_lateral(self):
        assert "LEFT JOIN LATERAL" in MV_SQL or "left join lateral" in MV_SQL.lower()

    def test_has_all_similarity_weights(self):
        for weight in ["1.0", "0.85", "0.65", "0.45", "0.25"]:
            assert weight in MV_SQL, f"Missing similarity weight {weight}"

    def test_has_blended_density_pct(self):
        assert "blended_density_pct" in MV_SQL

    def test_no_redundant_regexp_in_lateral(self):
        """After precompute, the inner LATERAL should use tn.naics_norm, not the full regexp."""
        # Count occurrences of the full regexp pattern in the LATERAL block
        full_regexp = "regexp_replace(COALESCE(t.naics_code::text, ''), '[^0-9]', '', 'g')"
        # Should appear only in the state_industry_density CTE and the CROSS JOIN LATERAL definition
        # Not 10 times in the CASE ladder
        count = MV_SQL.count(full_regexp)
        assert count <= 2, f"Expected <= 2 occurrences of full regexp (precomputed), found {count}"
