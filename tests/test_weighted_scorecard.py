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
    """Allowed tiers: Priority/Strong/Promising/Moderate/Low + Speculative.

    Speculative added 2026-05-06 (P0 #5) for the thin-data 85+ subset
    that was previously hidden inside 'Promising'.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM mv_unified_scorecard
                WHERE score_tier NOT IN
                  ('Priority', 'Strong', 'Promising', 'Moderate', 'Low', 'Speculative')
                """
            )
            bad = cur.fetchone()[0]
            assert bad == 0
    finally:
        conn.close()


def test_promising_no_longer_dominated_by_thin_data():
    """P0 #5 regression guard: 'Promising' must require direct factors.

    Before the 2026-05-06 split, 87% of 'Promising' rows had 0 direct
    factors (just modeled signals). After the split, every 'Promising'
    row must have direct_factors_available >= 1.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM mv_unified_scorecard
                WHERE score_tier = 'Promising' AND direct_factors_available < 1
                """
            )
            thin_promising = cur.fetchone()[0]
            assert thin_promising == 0, (
                f"{thin_promising} 'Promising' rows have 0 direct factors — "
                f"these belong in 'Speculative' per P0 #5"
            )
    finally:
        conn.close()


def test_speculative_tier_is_thin_data_only():
    """Symmetric guard: every 'Speculative' row should have 0 direct factors."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM mv_unified_scorecard
                WHERE score_tier = 'Speculative' AND direct_factors_available > 0
                """
            )
            with_direct = cur.fetchone()[0]
            assert with_direct == 0, (
                f"{with_direct} 'Speculative' rows have direct factors — "
                f"these should be in 'Strong' or 'Promising'"
            )
    finally:
        conn.close()


def test_promising_enforcement_rate_high_after_split():
    """P0 #5 fix outcome: 'Promising' (now scored-only) should have
    high enforcement rate (>= 50%). Before the split it was 9.8% because
    thin-data noise diluted the real signals."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE
                        COALESCE(score_osha, 0) > 0
                        OR COALESCE(score_nlrb, 0) > 0
                        OR COALESCE(score_whd, 0) > 0
                    ) AS with_enf
                FROM mv_unified_scorecard
                WHERE score_tier = 'Promising'
                """
            )
            row = cur.fetchone()
            total = row[0] if isinstance(row, tuple) else row["total"]
            with_enf = row[1] if isinstance(row, tuple) else row["with_enf"]
            if total == 0:
                return  # MV may be empty in CI
            rate = with_enf / total
            assert rate >= 0.5, (
                f"Promising enforcement rate {rate:.1%} below 50% — "
                f"the split may not have purged thin-data rows correctly"
            )
    finally:
        conn.close()
