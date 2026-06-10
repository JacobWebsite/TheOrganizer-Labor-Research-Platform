"""
Regression test for mv_target_data_sources.source_count.

Fixes the 2026-05-11 / 2026-05-12 undercount bug where the SUM at
`scripts/scoring/build_target_data_sources.py:106-117` did NOT include
`has_f7`, `has_lda`, `has_epa_echo`, or `has_fec`, so masters that had any
of those source_systems had a `source_count` 1-3 lower than the true
distinct-source count. F7-only masters had source_count=0 and were
dropped from `mv_target_scorecard` entirely (since that MV filters on
`source_count >= 1`).

This test asserts the invariant:

    mv_target_data_sources.source_count
      == COUNT(DISTINCT source_system)
         FROM master_employer_source_ids
         WHERE master_id = mv_target_data_sources.master_id

for both a broad sample and several specific masters surfaced by the
original Codex /wrapup crosscheck (including 66727/66728, F7-only).

See: `Open Problems/mv_target_data_sources source_count undercount.md`
and commit ship/2026-05-12-target-data-sources-fix.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DISABLE_AUTH", "true")

import pytest
from db_config import get_connection
from psycopg2.extras import RealDictCursor


@pytest.fixture(scope="module")
def conn():
    c = get_connection()
    yield c
    c.close()


def _mv_exists(conn, mv_name: str) -> bool:
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = %s) AS e",
        (mv_name,),
    )
    return bool(cur.fetchone()["e"])


class TestTargetDataSourcesSourceCount:
    def test_mv_exists(self, conn):
        assert _mv_exists(conn, "mv_target_data_sources"), (
            "mv_target_data_sources must exist -- rebuild with "
            "`py scripts/scoring/build_target_data_sources.py`"
        )

    def test_codex_canary_masters_match_distinct_count(self, conn):
        """The five masters surfaced by Codex /wrapup on 2026-05-11.

        Before the fix:
          - 66727 / 66728 (F7-only): source_count = NULL (not in MV row
            with source_count=0)
          - 83745, 149496: source_count = 11 vs actual 14 (missing
            has_f7 + has_lda + has_epa_echo)
          - 87152: source_count = 11 vs actual 13 (missing has_f7 +
            has_lda)

        After the fix, all rows must report `delta = 0`.
        """
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT m.master_id,
                   tds.source_count AS mv_source_count,
                   (SELECT COUNT(DISTINCT source_system)
                      FROM master_employer_source_ids
                     WHERE master_id = m.master_id) AS actual_distinct
            FROM master_employers m
            LEFT JOIN mv_target_data_sources tds ON tds.master_id = m.master_id
            WHERE m.master_id IN (83745, 149496, 87152, 66727, 66728)
            ORDER BY m.master_id
            """
        )
        rows = cur.fetchall()
        assert len(rows) == 5, "Expected all 5 canary masters present"
        for row in rows:
            mv_sc = row["mv_source_count"]
            actual = row["actual_distinct"]
            assert mv_sc is not None, (
                f"master_id={row['master_id']} missing from "
                "mv_target_data_sources (likely F7-only filtered out)"
            )
            assert mv_sc == actual, (
                f"master_id={row['master_id']}: mv_source_count={mv_sc} "
                f"!= COUNT(DISTINCT source_system)={actual}"
            )

    def test_f7_only_master_has_source_count_one(self, conn):
        """An F7-only non-union master should have source_count=1 and
        be present in the MV (was source_count=0 / 'NULL via LEFT JOIN'
        before the fix)."""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT master_id, source_count, has_f7
            FROM mv_target_data_sources
            WHERE master_id IN (66727, 66728)
            ORDER BY master_id
            """
        )
        rows = cur.fetchall()
        assert len(rows) == 2, (
            "F7-only masters 66727/66728 must be in mv_target_data_sources "
            "(both have is_union=FALSE and data_quality_score >= 20)"
        )
        for row in rows:
            assert row["has_f7"] is True, (
                f"master {row['master_id']}: has_f7 must be True"
            )
            assert row["source_count"] == 1, (
                f"master {row['master_id']}: source_count must be 1 "
                f"(only has_f7), got {row['source_count']}"
            )

    def test_random_sample_matches_distinct_count(self, conn):
        """For a random 200-master sample, the MV's source_count must
        match COUNT(DISTINCT source_system) exactly. Catches future
        regressions if a new source_system is added without updating
        the SUM."""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            WITH sample AS (
              SELECT master_id
              FROM mv_target_data_sources
              ORDER BY md5(master_id::text)
              LIMIT 200
            ),
            actual AS (
              SELECT s.master_id,
                     COUNT(DISTINCT msi.source_system) AS actual_distinct
              FROM sample s
              LEFT JOIN master_employer_source_ids msi
                     ON msi.master_id = s.master_id
              GROUP BY s.master_id
            )
            SELECT tds.master_id,
                   tds.source_count AS mv_sc,
                   a.actual_distinct
            FROM mv_target_data_sources tds
            JOIN actual a ON a.master_id = tds.master_id
            WHERE tds.source_count IS DISTINCT FROM a.actual_distinct
            """
        )
        mismatches = cur.fetchall()
        assert mismatches == [], (
            f"Found {len(mismatches)} masters where source_count != "
            f"COUNT(DISTINCT source_system). First few: "
            f"{mismatches[:5]}"
        )

    def test_source_count_distribution_includes_14(self, conn):
        """After the fix, max source_count should be at least 14 (was
        capped at 12 before the fix because has_f7/has_lda/has_epa_echo
        were excluded). Includes has_fec too once that source has
        masters with >=12 other sources."""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT MAX(source_count) AS max_sc FROM mv_target_data_sources"
        )
        max_sc = cur.fetchone()["max_sc"]
        assert max_sc >= 14, (
            f"Max source_count={max_sc}; expected >= 14 after adding "
            "has_f7+has_lda+has_epa_echo+has_fec to the SUM. If <14, "
            "the build script may be missing some flags."
        )

    def test_flag_columns_exist(self, conn):
        """Verify the MV exposes the new flag columns added by the fix."""
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT attname FROM pg_attribute
            WHERE attrelid = 'mv_target_data_sources'::regclass
              AND attnum > 0 AND NOT attisdropped
            """
        )
        cols = {r["attname"] for r in cur.fetchall()}
        for flag in ("has_f7", "has_lda", "has_epa_echo", "has_fec"):
            assert flag in cols, (
                f"mv_target_data_sources missing flag column {flag!r}; "
                "rebuild with the 2026-05-12 fix to "
                "scripts/scoring/build_target_data_sources.py"
            )
