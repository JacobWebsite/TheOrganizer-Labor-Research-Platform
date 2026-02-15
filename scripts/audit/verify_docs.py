"""
Documentation Accuracy Audit - Round 2, Section 9
Verifies all table names and row counts mentioned in CLAUDE.md, README.md, and ROADMAP.md
against the actual database.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

def run_query(cur, sql):
    """Run a query and return scalar result."""
    try:
        cur.execute(sql)
        return cur.fetchone()[0]
    except Exception as e:
        return f"ERROR: {e}"

def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    print("=" * 80)
    print("DOCUMENTATION ACCURACY AUDIT - Database Verification")
    print("=" * 80)

    # ===== SECTION 1: Core table existence and row counts =====
    print("\n--- SECTION 1: Core Tables (CLAUDE.md) ---")

    core_tables = {
        'unions_master': 26665,
        'f7_employers_deduped': 113713,
        'nlrb_elections': 33096,
        'nlrb_participants': 1906542,
        'lm_data': 331238,
        'epi_state_benchmarks': 51,
        'manual_employers': 520,
    }

    for table, expected in core_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # mv_employer_search
    actual = run_query(cur, "SELECT COUNT(*) FROM mv_employer_search")
    status = "OK" if actual == 118015 else f"MISMATCH (expected 118,015)"
    print(f"  mv_employer_search: {actual:,} {status}")

    # ===== SECTION 2: Public Sector Tables =====
    print("\n--- SECTION 2: Public Sector Tables ---")
    ps_tables = {
        'ps_parent_unions': 24,
        'ps_union_locals': 1520,
        'ps_employers': 7987,
        'ps_bargaining_units': 438,
    }
    for table, expected in ps_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 3: OSHA Tables =====
    print("\n--- SECTION 3: OSHA Tables ---")
    osha_tables = {
        'osha_establishments': 1007217,
        'osha_violations_detail': 2245020,
        'osha_f7_matches': 138340,
    }
    for table, expected in osha_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 4: WHD Tables =====
    print("\n--- SECTION 4: WHD Tables ---")
    whd_tables = {
        'whd_cases': 363365,
        'mv_whd_employer_agg': 330419,
    }
    for table, expected in whd_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # WHD match count
    actual = run_query(cur, "SELECT COUNT(*) FROM whd_f7_matches")
    status = "OK" if actual == 24610 else f"MISMATCH (expected 24,610)"
    print(f"  whd_f7_matches: {actual:,} {status}")

    # ===== SECTION 5: Match Tables =====
    print("\n--- SECTION 5: Match Tables ---")
    match_tables = {
        'osha_f7_matches': 138340,
        'whd_f7_matches': 24610,
        'national_990_f7_matches': 14059,
        'sam_f7_matches': 11050,
        'nlrb_employer_xref': 179275,
        'employer_comparables': 269810,
    }
    for table, expected in match_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 6: SAM Tables =====
    print("\n--- SECTION 6: SAM Tables ---")
    actual = run_query(cur, "SELECT COUNT(*) FROM sam_entities")
    status = "OK" if actual == 826042 else f"MISMATCH (expected 826,042)"
    print(f"  sam_entities: {actual:,} {status}")

    # ===== SECTION 7: Additional Data Tables =====
    print("\n--- SECTION 7: Additional Data Tables ---")
    add_tables = {
        'epi_union_membership': 1420064,
        'employers_990_deduped': 1046167,
        'ar_disbursements_emp_off': 2813248,
        'ar_membership': 216508,
        'ar_disbursements_total': 216372,
        'ar_assets_investments': 304816,
    }
    for table, expected in add_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 8: Unified Employer Tables =====
    print("\n--- SECTION 8: Unified Employer Tables ---")
    uni_tables = {
        'unified_employers_osha': 100768,
        'osha_unified_matches': 42812,
    }
    for table, expected in uni_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 9: Corporate Hierarchy Tables =====
    print("\n--- SECTION 9: Corporate Hierarchy Tables ---")
    corp_tables = {
        'sec_companies': 517403,
        'gleif_us_entities': 379192,
        'gleif_ownership_links': 498963,
        'corporate_identifier_crosswalk': 25177,
        'corporate_hierarchy': 125120,
        'qcew_annual': 1943426,
        'qcew_industry_density': 7143,
        'f7_industry_scores': 121433,
        'federal_contract_recipients': 47193,
        'usaspending_f7_matches': 9305,
        'f7_federal_scores': 9305,
        'state_fips_map': 54,
    }
    for table, expected in corp_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 10: Web Scraper Tables =====
    print("\n--- SECTION 10: Web Scraper Tables ---")
    web_tables = {
        'web_union_profiles': 295,
        'web_union_employers': 160,
        'web_union_contracts': 120,
        'web_union_membership': 31,
        'web_union_news': 183,
        'scrape_jobs': 112,
    }
    for table, expected in web_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 11: Contract/Target Tables =====
    print("\n--- SECTION 11: Contract/Target Tables ---")
    contract_tables = {
        'ny_state_contracts': 51500,
        'nyc_contracts': 49767,
        'employers_990': 5942,
        'organizing_targets': 5428,
    }
    for table, expected in contract_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 12: Mergent Employer Tables =====
    print("\n--- SECTION 12: Mergent Employer Tables ---")
    mergent_tables = {
        'mergent_employers': 56426,
        'national_990_filers': 586767,
        'ny_990_filers': 47614,
    }
    for table, expected in mergent_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 13: Geography Tables =====
    print("\n--- SECTION 13: Geography Tables ---")
    geo_tables = {
        'cbsa_definitions': 935,
        'state_sector_union_density': 6191,
        'state_workforce_shares': 51,
        'state_govt_level_density': 51,
        'county_workforce_shares': 3144,
        'county_union_density_estimates': 3144,
    }
    for table, expected in geo_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 14: NY Sub-County Density Tables =====
    print("\n--- SECTION 14: NY Sub-County Density Tables ---")
    ny_tables = {
        'ny_county_density_estimates': 62,
        'ny_zip_density_estimates': 1826,
        'ny_tract_density_estimates': 5411,
    }
    for table, expected in ny_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 15: Industry Density Tables =====
    print("\n--- SECTION 15: Industry Density Tables ---")
    ind_tables = {
        'bls_industry_density': 12,
        'state_industry_shares': 51,
        'county_industry_shares': 3144,
        'state_industry_density_comparison': 51,
    }
    for table, expected in ind_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 16: NYC Employer Violations Tables =====
    print("\n--- SECTION 16: NYC Employer Violations Tables ---")
    nyc_tables = {
        'nyc_wage_theft_nys': 3281,
        'nyc_wage_theft_usdol': 431,
        'nyc_wage_theft_litigation': 54,
        'nyc_ulp_closed': 260,
        'nyc_ulp_open': 660,
        'nyc_local_labor_laws': 568,
        'nyc_discrimination': 111,
        'nyc_prevailing_wage': 46,
        'nyc_debarment_list': 210,
        'nyc_osha_violations': 3454,
    }
    for table, expected in nyc_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 17: GLEIF Raw Schema =====
    print("\n--- SECTION 17: GLEIF Raw Schema ---")
    gleif_tables = {
        'gleif.entity_statement': 5667010,
        'gleif.entity_identifiers': 6706686,
        'gleif.entity_addresses': 6706686,
        'gleif.ooc_statement': 5758526,
        'gleif.ooc_interests': 5748906,
        'gleif.person_statement': 2826102,
    }
    for table, expected in gleif_tables.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 18: Scorecard MV =====
    print("\n--- SECTION 18: Scorecard Materialized View ---")
    actual = run_query(cur, "SELECT COUNT(*) FROM mv_organizing_scorecard")
    status = "OK" if actual == 24841 else f"MISMATCH (expected 24,841)"
    print(f"  mv_organizing_scorecard: {actual:,} {status}")

    # ===== SECTION 19: Key metrics from MEMORY.md / user spec =====
    print("\n--- SECTION 19: Key Claimed Metrics ---")

    # Employer counts (current vs historical)
    actual_total = run_query(cur, "SELECT COUNT(*) FROM f7_employers_deduped")
    actual_current = run_query(cur, "SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical = false OR is_historical IS NULL")
    actual_historical = run_query(cur, "SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical = true")
    print(f"  F7 employers total: {actual_total:,} (claimed: 113,713)")
    print(f"  F7 employers current (non-historical): {actual_current:,} (claimed: ~60,953)")
    print(f"  F7 employers historical: {actual_historical:,} (claimed: ~52,760)")

    # Union count
    actual_unions = run_query(cur, "SELECT COUNT(*) FROM unions_master")
    print(f"  Unions (unions_master): {actual_unions:,} (claimed: ~26,688 in memory, 26,665 in CLAUDE.md)")

    # NLRB case count
    actual_nlrb_cases = run_query(cur, "SELECT COUNT(*) FROM nlrb_cases")
    print(f"  NLRB cases: {actual_nlrb_cases:,} (claimed: ~477K)")

    # OSHA establishments
    actual_osha = run_query(cur, "SELECT COUNT(*) FROM osha_establishments")
    print(f"  OSHA establishments: {actual_osha:,} (claimed: 1,007,217)")

    # Match rates
    print("\n  Match rates:")
    osha_match_rate = run_query(cur, """
        SELECT ROUND(100.0 * COUNT(DISTINCT f7_employer_id) /
            (SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical = false OR is_historical IS NULL), 1)
        FROM osha_f7_matches
    """)
    print(f"    OSHA match rate (F7 employers matched): {osha_match_rate}% (claimed: ~13.7% of OSHA estab / 47.3% of F7)")

    osha_estab_rate = run_query(cur, """
        SELECT ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM osha_establishments), 1)
        FROM osha_f7_matches
    """)
    print(f"    OSHA match rate (estab basis): {osha_estab_rate}%")

    whd_match_count = run_query(cur, "SELECT COUNT(DISTINCT f7_employer_id) FROM whd_f7_matches")
    whd_total_f7 = run_query(cur, "SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical = false OR is_historical IS NULL")
    print(f"    WHD matched F7 employers: {whd_match_count:,}")
    whd_rate = round(100.0 * whd_match_count / whd_total_f7, 1) if whd_total_f7 else 0
    print(f"    WHD match rate: {whd_rate}% (claimed: ~6.8%)")

    n990_match_count = run_query(cur, "SELECT COUNT(DISTINCT f7_employer_id) FROM national_990_f7_matches")
    n990_rate = round(100.0 * n990_match_count / whd_total_f7, 1) if whd_total_f7 else 0
    print(f"    990 matched F7 employers: {n990_match_count:,}")
    print(f"    990 match rate: {n990_rate}% (claimed: ~2.4%)")

    # ===== SECTION 20: NLRB total cases (audit report said 477,688) =====
    print("\n--- SECTION 20: NLRB Cases ---")
    nlrb_tables_check = {
        'nlrb_cases': 477688,
        'nlrb_filings': 498749,
        'nlrb_docket': 2046151,
        'nlrb_allegations': 715805,
    }
    for table, expected in nlrb_tables_check.items():
        actual = run_query(cur, f"SELECT COUNT(*) FROM {table}")
        status = "OK" if actual == expected else f"MISMATCH (expected {expected:,})"
        print(f"  {table}: {actual:,} {status}")

    # ===== SECTION 21: Check splink_match_results (should be dropped per CLAUDE.md) =====
    print("\n--- SECTION 21: Archived/Dropped Tables ---")
    actual_splink = run_query(cur, "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'splink_match_results'")
    if actual_splink == 0:
        print("  splink_match_results: DROPPED (CLAUDE.md says 'ARCHIVED' -- correct)")
    else:
        splink_rows = run_query(cur, "SELECT COUNT(*) FROM splink_match_results")
        print(f"  splink_match_results: STILL EXISTS with {splink_rows:,} rows (CLAUDE.md says ARCHIVED)")

    # ===== SECTION 22: Check for is_historical column =====
    print("\n--- SECTION 22: is_historical column existence ---")
    has_col = run_query(cur, """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'f7_employers_deduped' AND column_name = 'is_historical'
    """)
    print(f"  f7_employers_deduped.is_historical column exists: {'YES' if has_col > 0 else 'NO'}")

    # ===== SECTION 23: v_f7_employers_current view =====
    print("\n--- SECTION 23: v_f7_employers_current view ---")
    has_view = run_query(cur, """
        SELECT COUNT(*) FROM information_schema.views
        WHERE table_name = 'v_f7_employers_current'
    """)
    if has_view > 0:
        view_count = run_query(cur, "SELECT COUNT(*) FROM v_f7_employers_current")
        print(f"  v_f7_employers_current: EXISTS with {view_count:,} rows")
    else:
        print("  v_f7_employers_current: DOES NOT EXIST")

    # ===== SECTION 24: Count API endpoints =====
    print("\n--- SECTION 24: API Endpoint Count ---")
    print("  (Checked via file analysis -- see separate output)")

    # ===== SECTION 25: f7_employers_deduped primary key check =====
    print("\n--- SECTION 25: Primary Key Check ---")
    pk_check = run_query(cur, """
        SELECT COUNT(*) FROM information_schema.table_constraints
        WHERE table_name = 'f7_employers_deduped' AND constraint_type = 'PRIMARY KEY'
    """)
    print(f"  f7_employers_deduped has PRIMARY KEY: {'YES' if pk_check > 0 else 'NO'}")

    # ===== SECTION 26: Orphan check =====
    print("\n--- SECTION 26: Orphan Relations Check ---")
    orphan_count = run_query(cur, """
        SELECT COUNT(*) FROM f7_union_employer_relations r
        LEFT JOIN f7_employers_deduped e ON r.employer_id = e.employer_id
        WHERE e.employer_id IS NULL
    """)
    print(f"  Orphaned f7_union_employer_relations: {orphan_count:,} (should be 0)")

    # ===== SECTION 27: Total relations count =====
    print("\n--- SECTION 27: Total Relations ---")
    rel_count = run_query(cur, "SELECT COUNT(*) FROM f7_union_employer_relations")
    print(f"  f7_union_employer_relations: {rel_count:,} (CLAUDE.md mentions 119,832)")

    # ===== SECTION 28: MV count check =====
    print("\n--- SECTION 28: Materialized Views Count ---")
    mv_count = run_query(cur, """
        SELECT COUNT(*) FROM pg_matviews WHERE schemaname = 'public'
    """)
    print(f"  Public materialized views: {mv_count} (Audit report said 3, now should be 4 with mv_organizing_scorecard)")

    # ===== SECTION 29: Total table, view, MV counts =====
    print("\n--- SECTION 29: Object Counts ---")
    table_count = run_query(cur, """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    """)
    view_count = run_query(cur, """
        SELECT COUNT(*) FROM information_schema.views
        WHERE table_schema = 'public'
    """)
    print(f"  Public tables: {table_count} (audit report said 159)")
    print(f"  Public views: {view_count} (audit report said 187)")
    print(f"  Materialized views: {mv_count}")

    # ===== SECTION 30: README data source claims =====
    print("\n--- SECTION 30: README Data Source Claims ---")
    # README says F-7 = 63,118 employers but that was pre-orphan-fix
    actual_current_f7 = run_query(cur, "SELECT COUNT(*) FROM f7_employers_deduped WHERE is_historical = false OR is_historical IS NULL")
    print(f"  F-7 employers (current): {actual_current_f7:,} (README says 63,118)")

    # README says NLRB Participants = 30,399 unions
    actual_nlrb_part_unions = run_query(cur, "SELECT COUNT(DISTINCT labor_union) FROM nlrb_participants")
    print(f"  NLRB participants distinct unions: {actual_nlrb_part_unions:,} (README says 30,399)")

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
