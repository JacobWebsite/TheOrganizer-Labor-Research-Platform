"""
Targeted tests for weighted unified scorecard model.
"""
import pytest

from db_config import get_connection


def test_weighted_columns_exist():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT attname
                FROM pg_attribute
                WHERE attrelid = 'mv_unified_scorecard'::regclass
                  AND attnum > 0 AND NOT attisdropped
                """
            )
            cols = {r[0] for r in cur.fetchall()}
            for c in [
                "score_similarity",
                "score_industry_growth",
                "total_weight",
                "weighted_score",
                "score_tier",
                "score_tier_legacy",
            ]:
                assert c in cols, f"Missing column: {c}"
    finally:
        conn.close()


def test_weighted_score_formula_consistency():
    """weighted_score = LEAST(formula, thin_data_cap).

    R7-18 (2026-04-27): rows with `factors_available < 3 AND
    direct_factors_available = 0` (i.e., union_proximity-only modeled signal
    with no direct evidence) are capped at 7.0 to avoid 10/10 perfect-tens
    being driven by a single indirect factor. So weighted_score may be LOWER
    than the raw formula whenever the cap kicks in. This test mirrors the
    LEAST(...) wrap so capped rows aren't flagged as inconsistent.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mv_unified_scorecard
                WHERE weighted_score IS NOT NULL
                  AND ABS(
                    weighted_score
                    - LEAST(
                        ROUND(
                            (
                                COALESCE(score_anger * 3, 0)
                              + COALESCE(score_leverage * 4, 0)
                            )::numeric / NULLIF(
                                CASE WHEN score_anger IS NOT NULL THEN 3 ELSE 0 END
                              + CASE WHEN score_leverage IS NOT NULL THEN 4 ELSE 0 END,
                              0
                            ),
                            2
                          ),
                        CASE WHEN (
                            CASE WHEN score_osha IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_nlrb IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_whd IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_contracts IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_union_proximity IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_industry_growth IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_financial IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_size IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_similarity IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN has_research THEN 1 ELSE 0 END
                        ) < 3 AND (
                            CASE WHEN score_osha IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_nlrb IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_whd IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_contracts IS NOT NULL THEN 1 ELSE 0 END
                            + CASE WHEN score_financial IS NOT NULL THEN 1 ELSE 0 END
                        ) = 0
                        THEN 7.0::numeric
                        ELSE 10.0::numeric
                        END
                      )
                  ) > 0.02
                """
            )
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} rows violate weighted formula tolerance"
    finally:
        conn.close()


def test_similarity_populated_after_gower_overhaul():
    """After Gower overhaul (2026-04-01), score_similarity should be non-NULL
    for a significant portion of employers. The old test asserted similarity
    was NULL when proximity was strong, but that was a broken-pipeline artifact."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM mv_unified_scorecard
                WHERE score_similarity IS NOT NULL
                """
            )
            has_sim = cur.fetchone()[0]
            assert has_sim > 100000, f"Expected >100K with similarity, got {has_sim}"
    finally:
        conn.close()


def test_similarity_present_for_some_rows():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE score_union_proximity < 5) AS eligible,
                  COUNT(*) FILTER (WHERE score_union_proximity < 5 AND score_similarity IS NOT NULL) AS present
                FROM mv_unified_scorecard
                """
            )
            eligible, present = cur.fetchone()
            if eligible == 0:
                pytest.skip("No eligible rows for similarity scoring in current dataset")
            assert present > 0, "No rows have score_similarity where expected"
    finally:
        conn.close()


def test_unified_score_alias_matches_weighted_score():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mv_unified_scorecard
                WHERE ABS(COALESCE(weighted_score, 0) - COALESCE(unified_score, 0)) > 0.001
                """
            )
            bad = cur.fetchone()[0]
            assert bad == 0
    finally:
        conn.close()


def test_tier_values_are_new_model():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mv_unified_scorecard
                WHERE score_tier NOT IN ('Priority', 'Strong', 'Promising', 'Moderate', 'Low')
                """
            )
            bad = cur.fetchone()[0]
            assert bad == 0
    finally:
        conn.close()
