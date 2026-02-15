"""
Employer Canonical Grouping regression tests.

Validates:
- employer_canonical_groups table exists and is populated
- Required columns on f7_employers_deduped
- Each group has exactly 1 canonical rep
- No signatory entries incorrectly grouped
- member_count matches actual member count
- consolidated_workers positive
- API endpoints registered
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db_config import get_connection


class TestEmployerGroupsSchema:
    """Verify schema exists."""

    def test_table_exists(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_name = 'employer_canonical_groups'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_f7_has_canonical_group_id(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_name = 'f7_employers_deduped'
                      AND column_name = 'canonical_group_id'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_f7_has_is_canonical_rep(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_name = 'f7_employers_deduped'
                      AND column_name = 'is_canonical_rep'
                """)
                assert cur.fetchone()[0] == 1
        finally:
            conn.close()

    def test_required_columns_on_groups_table(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                required = ['group_id', 'canonical_name', 'canonical_employer_id',
                            'member_count', 'consolidated_workers', 'is_cross_state']
                for col in required:
                    cur.execute("""
                        SELECT COUNT(*) FROM information_schema.columns
                        WHERE table_name = 'employer_canonical_groups'
                          AND column_name = %s
                    """, [col])
                    assert cur.fetchone()[0] == 1, f"Missing column: {col}"
        finally:
            conn.close()


class TestEmployerGroupsData:
    """Verify data integrity."""

    def test_has_minimum_groups(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM employer_canonical_groups")
                count = cur.fetchone()[0]
                assert count >= 1000, f"Expected >= 1000 groups, got {count}"
        finally:
            conn.close()

    def test_each_group_has_one_canonical_rep(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT g.group_id, COUNT(*) as rep_count
                    FROM employer_canonical_groups g
                    JOIN f7_employers_deduped e
                        ON e.canonical_group_id = g.group_id
                        AND e.is_canonical_rep = TRUE
                    GROUP BY g.group_id
                    HAVING COUNT(*) != 1
                """)
                bad = cur.fetchall()
                assert len(bad) == 0, f"{len(bad)} groups don't have exactly 1 canonical rep"
        finally:
            conn.close()

    def test_canonical_employer_id_matches_rep(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM employer_canonical_groups g
                    WHERE NOT EXISTS (
                        SELECT 1 FROM f7_employers_deduped e
                        WHERE e.employer_id = g.canonical_employer_id
                          AND e.is_canonical_rep = TRUE
                          AND e.canonical_group_id = g.group_id
                    )
                """)
                mismatches = cur.fetchone()[0]
                assert mismatches == 0, f"{mismatches} groups have mismatched canonical_employer_id"
        finally:
            conn.close()

    def test_member_count_matches_actual(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT g.group_id, g.member_count, COUNT(e.employer_id) as actual
                    FROM employer_canonical_groups g
                    LEFT JOIN f7_employers_deduped e ON e.canonical_group_id = g.group_id
                    GROUP BY g.group_id, g.member_count
                    HAVING g.member_count != COUNT(e.employer_id)
                    LIMIT 5
                """)
                bad = cur.fetchall()
                assert len(bad) == 0, f"{len(bad)} groups have mismatched member_count"
        finally:
            conn.close()

    def test_consolidated_workers_positive(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM employer_canonical_groups
                    WHERE consolidated_workers < 0
                """)
                negatives = cur.fetchone()[0]
                assert negatives == 0, f"{negatives} groups have negative consolidated_workers"
        finally:
            conn.close()

    def test_no_signatory_entries_grouped(self):
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM f7_employers_deduped
                    WHERE canonical_group_id IS NOT NULL
                      AND exclude_reason IN ('SAG_AFTRA_SIGNATORY', 'SIGNATORY_PATTERN')
                """)
                count = cur.fetchone()[0]
                assert count == 0, f"{count} signatory entries are incorrectly grouped"
        finally:
            conn.close()


class TestEmployerGroupsAPI:
    """Verify API endpoints are registered."""

    def test_related_filings_endpoint(self):
        import importlib
        from api.routers import employers
        importlib.reload(employers)
        routes = [r.path for r in employers.router.routes]
        assert "/api/employers/{employer_id}/related-filings" in routes

    def test_employer_groups_endpoint(self):
        import importlib
        from api.routers import employers
        importlib.reload(employers)
        routes = [r.path for r in employers.router.routes]
        assert "/api/admin/employer-groups" in routes
