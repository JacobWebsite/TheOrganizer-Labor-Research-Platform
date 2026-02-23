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
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mv_unified_scorecard
                WHERE total_weight > 0
                  AND ABS(
                    weighted_score
                    - (
                        (
                            COALESCE(score_union_proximity, 0) * 3
                          + COALESCE(score_size, 0) * 3
                          + COALESCE(score_nlrb, 0) * 3
                          + COALESCE(score_contracts, 0) * 2
                          + COALESCE(score_industry_growth, 0) * 2
                          + COALESCE(score_financial, 0) * 2
                          + COALESCE(score_osha, 0)
                          + COALESCE(score_whd, 0)
                        ) / total_weight::numeric
                      )
                  ) > 0.02
                """
            )
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} rows violate weighted formula tolerance"
    finally:
        conn.close()


def test_similarity_null_when_union_proximity_strong():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mv_unified_scorecard
                WHERE score_union_proximity >= 5
                  AND score_similarity IS NOT NULL
                """
            )
            bad = cur.fetchone()[0]
            assert bad == 0, f"{bad} rows have score_similarity despite strong union proximity"
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
