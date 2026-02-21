"""
Tests for search dedup: mv_employer_search should be deduplicated
and exclude historical employers.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db_config import get_connection


@pytest.fixture(scope="module")
def db():
    conn = get_connection()
    yield conn
    conn.close()


def test_search_mv_exists(db):
    """mv_employer_search materialized view should exist."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_matviews
        WHERE matviewname = 'mv_employer_search'
    """)
    assert cur.fetchone()[0] == 1, "mv_employer_search does not exist"


def test_search_mv_no_historical(db):
    """No historical F7 employers should appear in the search MV."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM mv_employer_search m
        JOIN f7_employers_deduped e ON m.canonical_id = e.employer_id
        WHERE m.source_type = 'F7'
          AND e.is_historical = TRUE
    """)
    count = cur.fetchone()[0]
    assert count == 0, f"Found {count} historical F7 rows in mv_employer_search"


def test_search_mv_no_duplicate_groups(db):
    """For any canonical_group_id, at most 1 row in MV."""
    cur = db.cursor()
    cur.execute("""
        SELECT canonical_group_id, COUNT(*) AS cnt
        FROM mv_employer_search
        WHERE source_type = 'F7'
          AND canonical_group_id IS NOT NULL
        GROUP BY canonical_group_id
        HAVING COUNT(*) > 1
    """)
    dupes = cur.fetchall()
    msg = ""
    if dupes:
        msg = (f"Found {len(dupes)} canonical groups with duplicate rows. "
               f"First: group_id={dupes[0][0]} count={dupes[0][1]}")
    assert len(dupes) == 0, msg


def test_search_mv_row_count_reasonable(db):
    """F7 rows in MV should be significantly less than total f7_employers_deduped."""
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM mv_employer_search WHERE source_type = 'F7'"
    )
    mv_f7 = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
    total_f7 = cur.fetchone()[0]

    ratio = mv_f7 / total_f7 if total_f7 > 0 else 0
    assert ratio < 0.70, (
        f"MV has {mv_f7:,} F7 rows out of {total_f7:,} total ({ratio:.1%}). "
        f"Expected < 70% after dedup + historical filtering."
    )


def test_search_mv_has_group_columns(db):
    """MV should have canonical_group_id, group_member_count, consolidated_workers."""
    cur = db.cursor()
    cur.execute("""
        SELECT attname
        FROM pg_attribute
        WHERE attrelid = 'mv_employer_search'::regclass
          AND attname IN (
              'canonical_group_id', 'group_member_count', 'consolidated_workers'
          )
          AND attnum > 0
          AND NOT attisdropped
    """)
    cols = {r[0] for r in cur.fetchall()}
    expected = {'canonical_group_id', 'group_member_count', 'consolidated_workers'}
    assert cols == expected, f"Missing columns: {expected - cols}"


def test_search_mv_unique_canonical_id(db):
    """canonical_id should be unique (required for REFRESH CONCURRENTLY)."""
    cur = db.cursor()
    cur.execute("""
        SELECT canonical_id, COUNT(*) AS cnt
        FROM mv_employer_search
        GROUP BY canonical_id
        HAVING COUNT(*) > 1
        LIMIT 5
    """)
    dupes = cur.fetchall()
    msg = ""
    if dupes:
        msg = (f"Found {len(dupes)} duplicate canonical_ids. "
               f"First: {dupes[0][0]} (count={dupes[0][1]})")
    assert len(dupes) == 0, msg


def test_search_mv_grouped_have_member_count(db):
    """Grouped F7 employers should have group_member_count > 1."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM mv_employer_search
        WHERE source_type = 'F7'
          AND canonical_group_id IS NOT NULL
          AND (group_member_count IS NULL OR group_member_count <= 1)
    """)
    bad = cur.fetchone()[0]
    assert bad == 0, (
        f"{bad} grouped employers have missing/invalid group_member_count"
    )
