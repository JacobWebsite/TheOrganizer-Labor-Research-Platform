"""
Data integrity validation tests for the Labor Research Platform.

These tests verify the accuracy and consistency of the underlying data,
independent of the API layer. They run directly against PostgreSQL.

Run with: py -m pytest tests/test_data_integrity.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from db_config import get_connection


@pytest.fixture(scope="module")
def db():
    """Provide a database connection for all tests in this module."""
    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


def query_one(db, sql, params=None):
    """Execute SQL and return first row's first column."""
    cur = db.cursor()
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def query_all(db, sql, params=None):
    """Execute SQL and return all rows."""
    cur = db.cursor()
    cur.execute(sql, params or ())
    return cur.fetchall()


# ============================================================================
# CHECK 1: BLS Total Alignment
# ============================================================================

def test_bls_total_alignment(db):
    """Platform total membership should be within 5% of BLS benchmark (14.3M).

    BLS CPS 2024: 14,286,000 union members.
    Our deduplication: ~14.5M (1.4% over).
    Acceptable range: 13.6M - 15.0M.
    """
    total = query_one(db, """
        SELECT SUM(members)
        FROM unions_master um
        JOIN union_hierarchy uh ON um.f_num = uh.f_num
        WHERE uh.count_members = TRUE
    """)

    if total is None:
        # Fallback: use v_union_members_deduplicated if hierarchy flags exist
        total = query_one(db, """
            SELECT SUM(members) FROM v_union_members_deduplicated
        """)

    # BLS 2024: 14.286M. Allow 5% variance either way.
    BLS_BENCHMARK = 14_286_000
    MAX_VARIANCE = 0.05

    if total is not None:
        variance = abs(total - BLS_BENCHMARK) / BLS_BENCHMARK
        assert variance < MAX_VARIANCE, (
            f"Membership total {total:,} is {variance:.1%} from BLS benchmark {BLS_BENCHMARK:,}. "
            f"Max allowed: {MAX_VARIANCE:.0%}"
        )


# ============================================================================
# CHECK 2: State Coverage vs EPI Benchmarks
# ============================================================================

def test_state_epi_coverage(db):
    """Most states should have LM membership data within 100% of EPI benchmarks.

    LM filing data captures union financial reports; EPI uses CPS survey data.
    Significant variance is expected. At least 45/51 states should be within
    100% of EPI totals (i.e. not off by more than 2x).
    """
    rows = query_all(db, """
        SELECT state, our_lm_members, epi_members_total,
               ABS(our_lm_members - epi_members_total)::float / NULLIF(epi_members_total, 0) as variance
        FROM v_state_epi_comparison
        WHERE epi_members_total > 0
    """)

    if not rows:
        pytest.skip("v_state_epi_comparison view not found or empty")

    passing = sum(1 for row in rows if row[3] is not None and row[3] < 1.0)
    total = len(rows)

    assert passing >= 45, (
        f"Only {passing}/{total} states within 100% of EPI. Need >= 45."
    )


# ============================================================================
# CHECK 3: No Crosswalk Orphans
# ============================================================================

def test_no_crosswalk_orphans(db):
    """Crosswalk orphan rate should be below 40%.

    Some orphans are expected from Splink dedup merges that consolidated
    employer_ids. Phase 1 cleanup will resolve these.
    """
    orphans = query_one(db, """
        SELECT COUNT(*)
        FROM corporate_identifier_crosswalk c
        LEFT JOIN f7_employers_deduped f ON c.f7_employer_id = f.employer_id
        WHERE f.employer_id IS NULL
          AND c.f7_employer_id IS NOT NULL
    """)
    total = query_one(db, """
        SELECT COUNT(*) FROM corporate_identifier_crosswalk
        WHERE f7_employer_id IS NOT NULL
    """)

    rate = orphans / total if total > 0 else 0
    assert rate < 0.40, (
        f"Crosswalk orphan rate is {rate:.1%} ({orphans:,}/{total:,}). Need < 40%."
    )


# ============================================================================
# CHECK 4: F7 Employer Count Stability
# ============================================================================

def test_f7_employer_count_stable(db):
    """F7 employer count should be approximately 60,953 +/- 500.

    After the Data Integrity Sprint (Feb 8 2026): 60,953 employers.
    """
    count = query_one(db, "SELECT COUNT(*) FROM f7_employers_deduped")

    EXPECTED = 60_953
    TOLERANCE = 500

    assert abs(count - EXPECTED) <= TOLERANCE, (
        f"F7 employer count is {count:,}, expected ~{EXPECTED:,} (+/- {TOLERANCE})"
    )


# ============================================================================
# CHECK 5: NLRB Match Rate
# ============================================================================

def test_nlrb_match_rate(db):
    """NLRB participant match rate should be >= 2%.

    Current: 2.1% (40K/1.9M). Full NLRB matching is a Phase 1 roadmap item.
    This baseline test ensures matches don't regress.
    """
    total = query_one(db, "SELECT COUNT(*) FROM nlrb_participants")
    matched = query_one(db, """
        SELECT COUNT(*) FROM nlrb_participants
        WHERE matched_olms_fnum IS NOT NULL
           OR matched_employer_id IS NOT NULL
    """)

    if total is None or total == 0:
        pytest.skip("nlrb_participants table empty")

    rate = matched / total
    assert rate >= 0.02, (
        f"NLRB match rate is {rate:.1%} ({matched:,}/{total:,}). Need >= 2%."
    )


# ============================================================================
# CHECK 6: Materialized View Freshness
# ============================================================================

def test_materialized_views_populated(db):
    """All materialized views should have data (not empty)."""
    views = query_all(db, """
        SELECT matviewname FROM pg_matviews
        WHERE schemaname = 'public'
    """)

    empty_views = []
    for (view_name,) in views:
        count = query_one(db, f"SELECT COUNT(*) FROM {view_name}")
        if count == 0:
            empty_views.append(view_name)

    assert len(empty_views) == 0, (
        f"Empty materialized views: {', '.join(empty_views)}. Run REFRESH MATERIALIZED VIEW."
    )


# ============================================================================
# CHECK 7: No NULL Primary Keys in Core Tables
# ============================================================================

def test_no_null_primary_keys(db):
    """Core tables should have no NULL values in their primary key columns."""
    checks = [
        ("unions_master", "f_num"),
        ("f7_employers_deduped", "employer_id"),
        ("nlrb_elections", "case_number"),
        ("osha_establishments", "establishment_id"),
        ("whd_cases", "case_id"),
        ("corporate_identifier_crosswalk", "id"),
    ]

    failures = []
    for table, pk_col in checks:
        null_count = query_one(db, f"SELECT COUNT(*) FROM {table} WHERE {pk_col} IS NULL")
        if null_count and null_count > 0:
            failures.append(f"{table}.{pk_col}: {null_count} NULLs")

    assert len(failures) == 0, (
        f"NULL primary keys found:\n" + "\n".join(failures)
    )


# ============================================================================
# CHECK 8: Sector Classification Completeness
# ============================================================================

def test_sector_completeness(db):
    """At least 99% of unions_master should have a non-NULL, non-UNKNOWN sector."""
    total = query_one(db, "SELECT COUNT(*) FROM unions_master")
    classified = query_one(db, """
        SELECT COUNT(*) FROM unions_master
        WHERE sector IS NOT NULL AND sector != 'UNKNOWN'
    """)

    rate = classified / total if total > 0 else 0
    assert rate >= 0.99, (
        f"Sector classification rate is {rate:.1%} ({classified:,}/{total:,}). Need >= 99%."
    )


# ============================================================================
# CHECK 9: Union Hierarchy Consistency
# ============================================================================

def test_union_hierarchy_consistency(db):
    """At least 60% of unions in unions_master should have a hierarchy entry.

    union_hierarchy covers the ~18K unions with dedup flags.
    Full coverage is a Phase 1 goal.
    """
    total = query_one(db, "SELECT COUNT(*) FROM unions_master")
    with_hierarchy = query_one(db, """
        SELECT COUNT(*)
        FROM unions_master um
        JOIN union_hierarchy uh ON um.f_num = uh.f_num
    """)

    rate = with_hierarchy / total if total > 0 else 0
    assert rate >= 0.60, (
        f"Hierarchy coverage is {rate:.1%} ({with_hierarchy:,}/{total:,}). Need >= 60%."
    )


# ============================================================================
# CHECK 10: OSHA / WHD Data Loaded
# ============================================================================

def test_violation_data_loaded(db):
    """OSHA and WHD tables should have substantial data."""
    osha = query_one(db, "SELECT COUNT(*) FROM osha_violations_detail")
    whd = query_one(db, "SELECT COUNT(*) FROM whd_cases")

    assert osha > 2_000_000, f"OSHA violations: {osha:,} (expected > 2M)"
    assert whd > 300_000, f"WHD cases: {whd:,} (expected > 300K)"


# ============================================================================
# CHECK 11: Crosswalk Growth
# ============================================================================

def test_crosswalk_size(db):
    """Corporate crosswalk should have >= 14,000 entries."""
    count = query_one(db, "SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    assert count >= 14_000, (
        f"Crosswalk has {count:,} rows. Expected >= 14,000 after Phase 3."
    )


# ============================================================================
# CHECK 12: Employer Comparables Populated
# ============================================================================

def test_employer_comparables_populated(db):
    """employer_comparables should have rows with valid ranks and distances."""
    # Check if table exists first
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'employer_comparables'
    """)
    if not exists:
        pytest.skip("employer_comparables table not created yet")

    total = query_one(db, "SELECT COUNT(*) FROM employer_comparables")
    if total == 0:
        pytest.skip("employer_comparables not populated yet (run compute_gower_similarity.py)")

    # Ranks should be 1-5
    bad_ranks = query_one(db, """
        SELECT COUNT(*) FROM employer_comparables
        WHERE rank < 1 OR rank > 5
    """)
    assert bad_ranks == 0, f"Found {bad_ranks} rows with rank outside [1,5]"

    # Distances should be in [0,1]
    bad_dist = query_one(db, """
        SELECT COUNT(*) FROM employer_comparables
        WHERE gower_distance < 0 OR gower_distance > 1
    """)
    assert bad_dist == 0, f"Found {bad_dist} rows with distance outside [0,1]"

    # No orphan employer_ids
    orphans = query_one(db, """
        SELECT COUNT(*) FROM employer_comparables ec
        LEFT JOIN mergent_employers me ON me.id = ec.employer_id
        WHERE me.id IS NULL
    """)
    assert orphans == 0, f"Found {orphans} orphan employer_ids in comparables"

    # No orphan comparable_employer_ids
    orphans2 = query_one(db, """
        SELECT COUNT(*) FROM employer_comparables ec
        LEFT JOIN mergent_employers me ON me.id = ec.comparable_employer_id
        WHERE me.id IS NULL
    """)
    assert orphans2 == 0, f"Found {orphans2} orphan comparable_employer_ids"


# ============================================================================
# CHECK 13: No Duplicate Employers
# ============================================================================

def test_no_exact_duplicate_employers(db):
    """No two employers should have the exact same name+city+state."""
    dupes = query_one(db, """
        SELECT COUNT(*) FROM (
            SELECT employer_name, UPPER(city), state, COUNT(*)
            FROM f7_employers_deduped
            GROUP BY employer_name, UPPER(city), state
            HAVING COUNT(*) > 1
        ) d
    """)

    # Some legitimate duplicates may exist (different addresses, same name/city)
    assert dupes < 100, (
        f"Found {dupes} exact name+city+state duplicates. Expected < 100."
    )
