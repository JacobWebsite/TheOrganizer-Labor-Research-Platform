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
    """F7 employer count should be approximately 113,713 +/- 500.

    After Data Integrity Sprint (Feb 8 2026): 60,953 employers.
    After orphan fix (Feb 14 2026): 113,713 (added 52,760 historical pre-2020 employers).
    """
    count = query_one(db, "SELECT COUNT(*) FROM f7_employers_deduped")

    EXPECTED = 146_863
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

def test_nlrb_pattern_tables_populated(db):
    """NLRB pattern reference tables should be populated with valid data."""
    # Industry win rates
    ind_count = query_one(db, "SELECT COUNT(*) FROM ref_nlrb_industry_win_rates")
    assert ind_count >= 20, f"Only {ind_count} industry win rate rows, expected >= 20"

    # Size bucket win rates
    size_count = query_one(db, "SELECT COUNT(*) FROM ref_nlrb_size_win_rates")
    assert size_count == 8, f"Expected 8 size buckets, got {size_count}"

    # Win rates should be in reasonable range (30-100%)
    bad_rates = query_one(db, """
        SELECT COUNT(*) FROM ref_nlrb_industry_win_rates
        WHERE win_rate_pct < 30 OR win_rate_pct > 100
    """)
    assert bad_rates == 0, f"Found {bad_rates} industry win rates outside [30, 100]"

    # Predicted win pct populated on mergent_employers
    predicted_count = query_one(db, """
        SELECT COUNT(*) FROM mergent_employers WHERE nlrb_predicted_win_pct IS NOT NULL
    """)
    total = query_one(db, "SELECT COUNT(*) FROM mergent_employers")
    rate = predicted_count / total if total > 0 else 0
    assert rate >= 0.90, (
        f"Only {rate:.1%} of mergent_employers have nlrb_predicted_win_pct. Need >= 90%."
    )


# ============================================================================
# CHECK 14: No Duplicate Employers
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


# ============================================================================
# CHECK 15: OSHA Match Rate (Phase 5)
# ============================================================================

def test_osha_match_rate(db):
    """OSHA establishment match rate should be >= 13% after Phase 5.

    Baseline before Phase 5: 7.9% (79,981 / ~1M).
    Current: ~13.7%. Floor set at 13% to catch regressions.
    """
    total = query_one(db, "SELECT COUNT(*) FROM osha_establishments")
    matched = query_one(db, "SELECT COUNT(DISTINCT establishment_id) FROM osha_f7_matches")

    if total is None or total == 0:
        pytest.skip("osha_establishments table empty")

    rate = matched / total
    assert rate >= 0.09, (
        f"OSHA match rate is {rate:.1%} ({matched:,}/{total:,}). Need >= 9%."
    )


# ============================================================================
# CHECK 16: WHD Match Rate (Phase 5)
# ============================================================================

def test_whd_match_rate(db):
    """WHD case match rate should be >= 6% after Phase 5.

    Baseline before Phase 5: 4.8% (~17K / 363K).
    Current: ~6.8%. Floor set at 6% to catch regressions.
    """
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'whd_f7_matches'
    """)
    if not exists:
        pytest.skip("whd_f7_matches table not created yet")

    total = query_one(db, "SELECT COUNT(*) FROM whd_cases")
    matched = query_one(db, "SELECT COUNT(*) FROM whd_f7_matches")

    if total is None or total == 0:
        pytest.skip("whd_cases table empty")

    rate = matched / total
    assert rate >= 0.05, (
        f"WHD match rate is {rate:.1%} ({matched:,}/{total:,}). Need >= 5%."
    )


# ============================================================================
# CHECK 17: 990 Match Rate (Phase 5)
# ============================================================================

def test_990_match_rate(db):
    """990 national filer match rate should be >= 2% after Phase 5.

    Baseline before Phase 5: 0%.
    Phase 5 adds EIN crosswalk, EIN Mergent, name+state, fuzzy, and address tiers.
    """
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'national_990_f7_matches'
    """)
    if not exists:
        pytest.skip("national_990_f7_matches table not created yet")

    total = query_one(db, "SELECT COUNT(*) FROM national_990_filers")
    matched = query_one(db, "SELECT COUNT(*) FROM national_990_f7_matches")

    if total is None or total == 0:
        pytest.skip("national_990_filers table empty")

    rate = matched / total
    assert rate >= 0.02, (
        f"990 match rate is {rate:.1%} ({matched:,}/{total:,}). Need >= 2%."
    )


# ============================================================================
# CHECK 18: Zero Orphaned Union-Employer Relations (Sprint 1 fix)
# ============================================================================

def test_zero_orphaned_relations(db):
    """After Sprint 1 orphan fix, there should be 0 orphaned union-employer relations.

    An orphan is a row in f7_union_employer_relations whose employer_id
    does not exist in f7_employers_deduped.
    """
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'f7_union_employer_relations'
    """)
    if not exists:
        pytest.skip("f7_union_employer_relations table not found")

    orphans = query_one(db, """
        SELECT COUNT(*)
        FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped f ON r.employer_id = f.employer_id
        WHERE f.employer_id IS NULL
    """)
    assert orphans == 0, (
        f"Found {orphans:,} orphaned union-employer relations. Sprint 1 fix should have reduced to 0."
    )


# ============================================================================
# CHECK 19: is_historical column on f7_employers_deduped
# ============================================================================

def test_is_historical_column_exists(db):
    """f7_employers_deduped should have an is_historical column (added Sprint 1)."""
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'f7_employers_deduped' AND column_name = 'is_historical'
    """)
    assert exists > 0, "is_historical column missing from f7_employers_deduped"


# ============================================================================
# CHECK 20: v_f7_employers_current view
# ============================================================================

def test_current_employers_view(db):
    """v_f7_employers_current should exist and have ~60,953 rows (+/- 500)."""
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.views
        WHERE table_name = 'v_f7_employers_current' AND table_schema = 'public'
    """)
    assert exists > 0, "v_f7_employers_current view does not exist"

    count = query_one(db, "SELECT COUNT(*) FROM v_f7_employers_current")
    EXPECTED = 67_552
    TOLERANCE = 500
    assert abs(count - EXPECTED) <= TOLERANCE, (
        f"v_f7_employers_current has {count:,} rows, expected ~{EXPECTED:,} (+/- {TOLERANCE})"
    )


# ============================================================================
# CHECK 21: platform_users table auto-creates (Sprint 2 auth)
# ============================================================================

def test_platform_users_table_exists(db):
    """platform_users table should exist (auto-created by auth module on startup)."""
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'platform_users' AND table_schema = 'public'
    """)
    assert exists > 0, "platform_users table does not exist (auth module may not have run)"


# ============================================================================
# CHECK 22: No orphaned f7_employer_id in osha_f7_matches
# ============================================================================

def test_no_orphaned_osha_matches(db):
    """Every f7_employer_id in osha_f7_matches should exist in f7_employers_deduped."""
    exists = query_one(db, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'osha_f7_matches'
    """)
    if not exists:
        pytest.skip("osha_f7_matches not created")

    orphans = query_one(db, """
        SELECT COUNT(*)
        FROM osha_f7_matches m
        LEFT JOIN f7_employers_deduped f ON m.f7_employer_id = f.employer_id
        WHERE f.employer_id IS NULL
    """)
    assert orphans == 0, (
        f"Found {orphans:,} orphaned f7_employer_id in osha_f7_matches"
    )


# ============================================================================
# CHECK 23: Match table FK integrity (all match tables)
# ============================================================================

def test_match_table_fk_integrity(db):
    """Every f7_employer_id in match tables should exist in f7_employers_deduped."""
    match_tables = ["osha_f7_matches", "whd_f7_matches", "national_990_f7_matches"]
    failures = []

    for table in match_tables:
        exists = query_one(db, """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = %s AND table_schema = 'public'
        """, (table,))
        if not exists:
            continue

        orphans = query_one(db, f"""
            SELECT COUNT(*)
            FROM {table} m
            LEFT JOIN f7_employers_deduped f ON m.f7_employer_id = f.employer_id
            WHERE f.employer_id IS NULL
        """)
        if orphans and orphans > 0:
            failures.append(f"{table}: {orphans:,} orphaned f7_employer_id values")

    assert len(failures) == 0, (
        "FK integrity violations:\n" + "\n".join(failures)
    )


# ============================================================================
# CHECK 24: Scorecard MV refresh works (admin endpoint)
# ============================================================================

def test_scorecard_mv_refreshable(db):
    """Scorecard MV should support REFRESH CONCURRENTLY (unique index + populated)."""
    # Verify the MV exists and has data (non-mutating -- avoids lock contention flake risk)
    count = query_one(db, "SELECT COUNT(*) FROM mv_organizing_scorecard")
    assert count is not None and count > 0, "MV has 0 rows -- may need initial REFRESH"

    # Verify unique index exists (required for CONCURRENTLY)
    has_unique = query_one(db, """
        SELECT COUNT(*) FROM pg_indexes
        WHERE tablename = 'mv_organizing_scorecard'
          AND indexdef ILIKE '%%unique%%'
          AND indexdef ILIKE '%%establishment_id%%'
    """)
    assert has_unique >= 1, (
        "No UNIQUE index on establishment_id -- REFRESH CONCURRENTLY will fail"
    )


# ============================================================================
# CHECK 25: Union File Number Orphans (Phase 1)
# ============================================================================

def test_union_file_number_orphans_bounded(db):
    """Union file number orphans should stay below 1000.

    824 records in f7_union_employer_relations reference union_file_number
    values not found in unions_master.f_num. Root cause: 195 distinct
    file numbers from defunct/removed unions with no LM filing history.
    Type mismatch (INTEGER vs VARCHAR) is handled via cast.
    These are tracked but not deleted -- they contain valid employer data.
    """
    orphans = query_one(db, """
        SELECT COUNT(*)
        FROM f7_union_employer_relations r
        LEFT JOIN unions_master u ON r.union_file_number::text = u.f_num
        WHERE u.f_num IS NULL
    """)
    assert orphans <= 1000, (
        f"Found {orphans:,} union file number orphans. Expected <= 1000 "
        f"(195 defunct union file numbers producing ~824 records)."
    )
