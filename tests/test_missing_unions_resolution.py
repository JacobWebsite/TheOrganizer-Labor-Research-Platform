"""
Tests for Phase C missing unions resolution.

Verifies that orphan union file numbers were reduced and CWA District 7
was resolved without losing any relation rows.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db_config import get_connection


@pytest.fixture(scope="module")
def db():
    conn = get_connection()
    yield conn
    conn.close()


def query_one(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    val = cur.fetchone()[0]
    cur.close()
    return val


def test_resolution_log_table_exists(db):
    """union_fnum_resolution_log table should exist with entries."""
    exists = query_one(db, """
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'union_fnum_resolution_log'
        ) AS e
    """)
    assert exists, "union_fnum_resolution_log table does not exist"

    count = query_one(db, "SELECT COUNT(*) FROM union_fnum_resolution_log")
    assert count > 0, "union_fnum_resolution_log has no entries"


def test_orphan_count_decreased(db):
    """Orphan file number count should be less than pre-resolution 166."""
    orphans = query_one(db, """
        SELECT COUNT(DISTINCT r.union_file_number)
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL
    """)
    assert orphans < 166, (
        f"Expected fewer than 166 orphan fnums after resolution, got {orphans}"
    )


def test_no_relation_rows_lost(db):
    """Total relation row count should be unchanged (119,445)."""
    total = query_one(db, "SELECT COUNT(*) FROM f7_union_employer_relations")
    assert total == 119445, (
        f"Expected 119,445 total relation rows (unchanged), got {total:,}"
    )


def test_cwa_district7_resolved(db):
    """Fnum 12590 (CWA District 7) should no longer be orphaned."""
    # 12590 should exist in unions_master now
    in_master = query_one(db, """
        SELECT EXISTS(
            SELECT 1 FROM unions_master WHERE f_num = '12590'
        ) AS e
    """)
    assert in_master, "Fnum 12590 should exist in unions_master after resolution"

    # Relations pointing to 12590 should NOT be orphaned
    orphan_12590 = query_one(db, """
        SELECT COUNT(*)
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL AND r.union_file_number = 12590
    """)
    assert orphan_12590 == 0, (
        f"Fnum 12590 still has {orphan_12590} orphaned relations"
    )


def test_cwa_successors_received_remaps(db):
    """CWA successor locals should have received remapped relations."""
    # At least some of the 5 known successors should have relations
    successors = [512497, 526792, 528302, 540383, 543920]
    total = query_one(db, """
        SELECT COUNT(*)
        FROM f7_union_employer_relations
        WHERE union_file_number = ANY(%s)
    """.replace("%s", "ARRAY[" + ",".join(str(s) for s in successors) + "]"))
    assert total >= 38, (
        f"Expected at least 38 relations remapped to CWA successors, got {total}"
    )


def test_resolution_log_has_all_categories(db):
    """Resolution log should cover all orphan fnums."""
    log_count = query_one(db, """
        SELECT COUNT(DISTINCT orphan_fnum) FROM union_fnum_resolution_log
    """)
    assert log_count >= 166, (
        f"Expected at least 166 distinct fnums in resolution log, got {log_count}"
    )


def test_orphan_workers_decreased(db):
    """Orphan worker count should be significantly less than 61,743."""
    workers = query_one(db, """
        SELECT COALESCE(SUM(r.bargaining_unit_size), 0)
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL
    """)
    # CWA District 7 alone was 38,192 workers, so should be ~23,551 now
    assert workers < 30000, (
        f"Expected orphan workers < 30,000 after CWA resolution, got {workers:,}"
    )
