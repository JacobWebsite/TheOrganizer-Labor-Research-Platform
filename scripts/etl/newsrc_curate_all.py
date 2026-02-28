"""
Build curated (typed, aggregated) tables from raw TEXT landing tables.

Each curated table has proper types, normalized keys (FIPS, NAICS, EIN),
and is ready for joining to master employers and scorecards.

Tables created:
  1. cur_form5500_sponsor_rollup   -- one row per sponsor EIN (latest year)
  2. cur_ppp_employer_rollup       -- one row per borrower name+state
  3. cur_usaspending_recipient_rollup -- one row per recipient UEI or name+state
  4. cur_cbp_geo_naics             -- county/state x NAICS establishment counts
  5. cur_lodes_geo_metrics         -- county-level workforce profile
  6. cur_abs_geo_naics             -- state/county x NAICS firm demographics
  7. cur_acs_workforce_demographics -- geo x industry x occupation x demographic workforce profile

Usage:
  python scripts/etl/newsrc_curate_all.py
  python scripts/etl/newsrc_curate_all.py --only form5500
  python scripts/etl/newsrc_curate_all.py --only cbp,lodes,acs
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


def _execute(conn, sql: str, label: str) -> None:
    """Execute SQL with timing output."""
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    elapsed = time.time() - t0
    print(f"  [{elapsed:.1f}s] {label}")


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = %s) AS e",
            [table_name],
        )
        return cur.fetchone()[0]


def _row_count(conn, table_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# 1. Form 5500 sponsor rollup
# ---------------------------------------------------------------------------
def build_form5500(conn):
    print("\n=== cur_form5500_sponsor_rollup ===")
    if not _table_exists(conn, "newsrc_form5500_all"):
        print("  [skip] newsrc_form5500_all does not exist")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_form5500_sponsor_rollup CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_form5500_sponsor_rollup AS
        WITH parsed AS (
            SELECT
                NULLIF(TRIM(spons_dfe_ein), '')                          AS sponsor_ein,
                UPPER(TRIM(NULLIF(sponsor_dfe_name, '')))                AS sponsor_name,
                UPPER(TRIM(NULLIF(spons_dfe_mail_us_state, '')))         AS sponsor_state,
                NULLIF(TRIM(spons_dfe_mail_us_city), '')                 AS sponsor_city,
                NULLIF(TRIM(spons_dfe_mail_us_zip), '')                  AS sponsor_zip,
                NULLIF(TRIM(business_code), '')                          AS naics_code,
                EXTRACT(YEAR FROM form_plan_year_begin_date::DATE)::INT  AS plan_year,
                NULLIF(TRIM(tot_active_partcp_cnt), '')::INT             AS active_participants,
                NULLIF(TRIM(tot_act_rtd_sep_benef_cnt), '')::INT         AS total_participants_beneficiaries,
                CASE WHEN UPPER(TRIM(collective_bargain_ind)) IN ('1','Y','YES','TRUE')
                     THEN TRUE ELSE FALSE END                            AS has_collective_bargaining,
                NULLIF(TRIM(contrib_emplrs_cnt), '')::INT                AS contributing_employers_cnt,
                NULLIF(TRIM(type_pension_bnft_code), '')                 AS pension_benefit_code,
                NULLIF(TRIM(type_welfare_bnft_code), '')                 AS welfare_benefit_code
            FROM newsrc_form5500_all
            WHERE NULLIF(TRIM(spons_dfe_ein), '') IS NOT NULL
        ),
        yearly_agg AS (
            SELECT
                sponsor_ein,
                MAX(sponsor_name)       AS sponsor_name,
                MAX(sponsor_state)      AS sponsor_state,
                MAX(sponsor_city)       AS sponsor_city,
                MAX(sponsor_zip)        AS sponsor_zip,
                MAX(naics_code)         AS naics_code,
                plan_year,
                COUNT(*)                AS plan_count,
                SUM(COALESCE(active_participants, 0))               AS total_active_participants,
                SUM(COALESCE(total_participants_beneficiaries, 0))  AS total_participants_beneficiaries,
                BOOL_OR(has_collective_bargaining)                   AS has_collective_bargaining,
                MAX(contributing_employers_cnt)                      AS max_contributing_employers,
                BOOL_OR(pension_benefit_code IS NOT NULL AND pension_benefit_code != '')  AS has_pension,
                BOOL_OR(welfare_benefit_code IS NOT NULL AND welfare_benefit_code != '')  AS has_welfare
            FROM parsed
            GROUP BY sponsor_ein, plan_year
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY sponsor_ein ORDER BY plan_year DESC) AS rn,
                   MIN(plan_year) OVER (PARTITION BY sponsor_ein) AS earliest_plan_year,
                   MAX(plan_year) OVER (PARTITION BY sponsor_ein) AS latest_plan_year,
                   COUNT(*) OVER (PARTITION BY sponsor_ein)       AS years_filed
            FROM yearly_agg
        )
        SELECT
            sponsor_ein,
            sponsor_name,
            sponsor_state,
            sponsor_city,
            sponsor_zip,
            naics_code,
            latest_plan_year,
            earliest_plan_year,
            years_filed,
            plan_count,
            total_active_participants,
            total_participants_beneficiaries,
            has_collective_bargaining,
            max_contributing_employers,
            has_pension,
            has_welfare
        FROM ranked
        WHERE rn = 1
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_f5500_ein ON cur_form5500_sponsor_rollup (sponsor_ein)", "index ein")
    _execute(conn, "CREATE INDEX idx_cur_f5500_name_st ON cur_form5500_sponsor_rollup (sponsor_name, sponsor_state)", "index name+state")

    cnt = _row_count(conn, "cur_form5500_sponsor_rollup")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# 2. PPP employer rollup
# ---------------------------------------------------------------------------
def build_ppp(conn):
    print("\n=== cur_ppp_employer_rollup ===")
    if not _table_exists(conn, "newsrc_ppp_public_raw"):
        print("  [skip] newsrc_ppp_public_raw does not exist")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_ppp_employer_rollup CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_ppp_employer_rollup AS
        WITH parsed AS (
            SELECT
                UPPER(TRIM(NULLIF(borrowername, '')))       AS borrower_name,
                UPPER(TRIM(NULLIF(borrowerstate, '')))      AS borrower_state,
                UPPER(TRIM(NULLIF(borrowercity, '')))       AS borrower_city,
                TRIM(NULLIF(borrowerzip, ''))                AS borrower_zip,
                TRIM(NULLIF(loannumber, ''))                 AS loan_number,
                NULLIF(TRIM(initialapprovalamount), '')::NUMERIC   AS initial_amount,
                NULLIF(TRIM(currentapprovalamount), '')::NUMERIC   AS current_amount,
                NULLIF(TRIM(undisbursedamount), '')::NUMERIC       AS undisbursed,
                NULLIF(TRIM(forgivenessamount), '')::NUMERIC       AS forgiveness_amount,
                NULLIF(TRIM(dateapproved), '')::DATE                AS date_approved,
                NULLIF(TRIM(forgivenessdate), '')::DATE            AS forgiveness_date,
                NULLIF(TRIM(jobsreported), '')::INT                AS jobs_reported,
                TRIM(NULLIF(franchisename, ''))              AS franchise_name,
                TRIM(NULLIF(naicscode, ''))                  AS naics_code,
                TRIM(NULLIF(businesstype, ''))               AS business_type,
                TRIM(NULLIF(loanstatus, ''))                 AS loan_status
            FROM newsrc_ppp_public_raw
            WHERE NULLIF(TRIM(borrowername), '') IS NOT NULL
        )
        SELECT
            borrower_name,
            borrower_state,
            MAX(borrower_city)           AS borrower_city,
            MAX(borrower_zip)            AS borrower_zip,
            COUNT(*)                     AS loan_count,
            SUM(COALESCE(initial_amount, 0))   AS total_initial_amount,
            SUM(COALESCE(current_amount, 0))   AS total_current_amount,
            SUM(COALESCE(undisbursed, 0))      AS total_undisbursed,
            SUM(COALESCE(forgiveness_amount, 0)) AS total_forgiveness_amount,
            SUM(COALESCE(jobs_reported, 0))    AS total_jobs_reported,
            MIN(date_approved)           AS earliest_date_approved,
            MAX(date_approved)           AS latest_date_approved,
            MAX(franchise_name)          AS franchise_name,
            MAX(naics_code)              AS naics_code,
            MAX(business_type)           AS business_type,
            BOOL_OR(loan_status = 'Paid in Full')           AS any_paid_in_full,
            BOOL_OR(forgiveness_amount IS NOT NULL AND forgiveness_amount > 0) AS any_forgiven
        FROM parsed
        GROUP BY borrower_name, borrower_state
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_ppp_name_st ON cur_ppp_employer_rollup (borrower_name, borrower_state)", "index name+state")

    cnt = _row_count(conn, "cur_ppp_employer_rollup")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# 3. USAspending recipient rollup
# ---------------------------------------------------------------------------
def build_usaspending(conn):
    print("\n=== cur_usaspending_recipient_rollup ===")
    if not _table_exists(conn, "newsrc_usaspending_contracts_raw"):
        print("  [skip] newsrc_usaspending_contracts_raw does not exist")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_usaspending_recipient_rollup CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_usaspending_recipient_rollup AS
        WITH parsed AS (
            SELECT
                TRIM(NULLIF(recipient_uei, ''))                        AS recipient_uei,
                UPPER(TRIM(NULLIF(recipient_name, '')))                AS recipient_name,
                UPPER(TRIM(NULLIF(recipient_state_code, '')))          AS recipient_state,
                UPPER(TRIM(NULLIF(recipient_city_name, '')))           AS recipient_city,
                TRIM(NULLIF(recipient_zip_4_code, ''))                 AS recipient_zip,
                TRIM(NULLIF(naics_code, ''))                           AS naics_code,
                TRIM(NULLIF(naics_description, ''))                    AS naics_description,
                NULLIF(TRIM(action_date_fiscal_year), '')::INT         AS fiscal_year,
                NULLIF(TRIM(federal_action_obligation), '')::NUMERIC   AS obligation_amount,
                NULLIF(TRIM(total_outlayed_amount_for_overall_award), '')::NUMERIC AS outlayed_amount,
                TRIM(NULLIF(recipient_parent_name, ''))                AS parent_name,
                TRIM(NULLIF(recipient_parent_uei, ''))                 AS parent_uei
            FROM newsrc_usaspending_contracts_raw
            WHERE NULLIF(TRIM(recipient_name), '') IS NOT NULL
        ),
        -- Group by UEI when available, else by name+state
        keyed AS (
            SELECT *,
                   COALESCE(recipient_uei, recipient_name || '|' || COALESCE(recipient_state, '')) AS group_key
            FROM parsed
        )
        SELECT
            MAX(recipient_uei)           AS recipient_uei,
            MAX(recipient_name)          AS recipient_name,
            MAX(recipient_state)         AS recipient_state,
            MAX(recipient_city)          AS recipient_city,
            MAX(recipient_zip)           AS recipient_zip,
            MAX(naics_code)              AS naics_code,
            MAX(naics_description)       AS naics_description,
            MAX(parent_name)             AS parent_name,
            MAX(parent_uei)              AS parent_uei,
            COUNT(*)                                       AS contract_count,
            SUM(COALESCE(obligation_amount, 0))            AS total_obligated,
            SUM(COALESCE(outlayed_amount, 0))              AS total_outlayed,
            ARRAY_AGG(DISTINCT fiscal_year ORDER BY fiscal_year) FILTER (WHERE fiscal_year IS NOT NULL) AS fiscal_years,
            MIN(fiscal_year)                               AS earliest_fy,
            MAX(fiscal_year)                               AS latest_fy
        FROM keyed
        GROUP BY group_key
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_usasp_uei ON cur_usaspending_recipient_rollup (recipient_uei)", "index uei")
    _execute(conn, "CREATE INDEX idx_cur_usasp_name_st ON cur_usaspending_recipient_rollup (recipient_name, recipient_state)", "index name+state")

    cnt = _row_count(conn, "cur_usaspending_recipient_rollup")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# 4. CBP geo x NAICS
# ---------------------------------------------------------------------------
def build_cbp(conn):
    print("\n=== cur_cbp_geo_naics ===")
    if not _table_exists(conn, "newsrc_cbp2023_raw"):
        print("  [skip] newsrc_cbp2023_raw does not exist")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_cbp_geo_naics CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_cbp_geo_naics AS
        SELECT
            TRIM(NULLIF(st, ''))                      AS state_fips,
            TRIM(NULLIF(county, ''))                   AS county_fips,
            TRIM(NULLIF(naics2017, ''))                AS naics,
            TRIM(NULLIF(naics2017_label, ''))          AS naics_label,
            TRIM(NULLIF(geotype, ''))                  AS geo_type,
            TRIM(NULLIF(year, ''))                     AS data_year,
            NULLIF(TRIM(estab), '')::INT               AS establishment_count,
            NULLIF(TRIM(emp), '')::INT                 AS employment,
            NULLIF(TRIM(payann), '')::BIGINT           AS annual_payroll,
            CASE WHEN NULLIF(TRIM(emp), '')::INT > 0
                 THEN ROUND(NULLIF(TRIM(payann), '')::NUMERIC / NULLIF(TRIM(emp), '')::INT / 52, 2)
                 ELSE NULL END                         AS avg_weekly_wage,
            TRIM(NULLIF(empszes, ''))                  AS emp_size_class,
            TRIM(NULLIF(empszes_label, ''))            AS emp_size_label
        FROM newsrc_cbp2023_raw
        WHERE NULLIF(TRIM(estab), '') IS NOT NULL
          AND TRIM(COALESCE(emp_f, '')) NOT IN ('S', 'D', 'G', 'N')
          AND (TRIM(NULLIF(geotype, '')) IN ('01','02','03') OR TRIM(NULLIF(geotype, '')) IS NULL)
          AND TRIM(COALESCE(empszes, '')) IN ('001', '')
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_cbp_st_naics ON cur_cbp_geo_naics (state_fips, naics)", "index state+naics")
    _execute(conn, "CREATE INDEX idx_cur_cbp_county ON cur_cbp_geo_naics (state_fips, county_fips, naics)", "index county+naics")

    cnt = _row_count(conn, "cur_cbp_geo_naics")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# 5. LODES geo metrics (county-level)
# ---------------------------------------------------------------------------
def build_lodes(conn):
    print("\n=== cur_lodes_geo_metrics ===")
    wac_ok = _table_exists(conn, "newsrc_lodes_wac_2022")
    xwalk_ok = _table_exists(conn, "newsrc_lodes_xwalk_2022")
    if not wac_ok or not xwalk_ok:
        print(f"  [skip] missing tables: wac={wac_ok}, xwalk={xwalk_ok}")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_lodes_geo_metrics CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_lodes_geo_metrics AS
        WITH wac_county AS (
            -- Map census block (w_geocode) to county via crosswalk
            SELECT
                SUBSTRING(w.w_geocode, 1, 2) AS state_fips,
                SUBSTRING(w.w_geocode, 1, 5) AS county_fips,
                SUM(NULLIF(w.c000, '')::INT)   AS total_jobs,
                -- Earnings tiers
                SUM(NULLIF(w.ce01, '')::INT)   AS jobs_earn_1250_or_less,
                SUM(NULLIF(w.ce02, '')::INT)   AS jobs_earn_1251_to_3333,
                SUM(NULLIF(w.ce03, '')::INT)   AS jobs_earn_3334_plus,
                -- Age tiers
                SUM(NULLIF(w.ca01, '')::INT)   AS jobs_age_29_or_younger,
                SUM(NULLIF(w.ca02, '')::INT)   AS jobs_age_30_to_54,
                SUM(NULLIF(w.ca03, '')::INT)   AS jobs_age_55_plus,
                -- Top industry sectors
                SUM(NULLIF(w.cns01, '')::INT)  AS jobs_agriculture,
                SUM(NULLIF(w.cns02, '')::INT)  AS jobs_mining,
                SUM(NULLIF(w.cns03, '')::INT)  AS jobs_utilities,
                SUM(NULLIF(w.cns04, '')::INT)  AS jobs_construction,
                SUM(NULLIF(w.cns05, '')::INT)  AS jobs_manufacturing,
                SUM(NULLIF(w.cns06, '')::INT)  AS jobs_wholesale,
                SUM(NULLIF(w.cns07, '')::INT)  AS jobs_retail,
                SUM(NULLIF(w.cns08, '')::INT)  AS jobs_transport_warehouse,
                SUM(NULLIF(w.cns09, '')::INT)  AS jobs_information,
                SUM(NULLIF(w.cns10, '')::INT)  AS jobs_finance_insurance,
                SUM(NULLIF(w.cns11, '')::INT)  AS jobs_real_estate,
                SUM(NULLIF(w.cns12, '')::INT)  AS jobs_prof_scientific,
                SUM(NULLIF(w.cns13, '')::INT)  AS jobs_management,
                SUM(NULLIF(w.cns14, '')::INT)  AS jobs_admin_waste,
                SUM(NULLIF(w.cns15, '')::INT)  AS jobs_education,
                SUM(NULLIF(w.cns16, '')::INT)  AS jobs_healthcare,
                SUM(NULLIF(w.cns17, '')::INT)  AS jobs_arts_entertainment,
                SUM(NULLIF(w.cns18, '')::INT)  AS jobs_accommodation_food,
                SUM(NULLIF(w.cns19, '')::INT)  AS jobs_other_services,
                SUM(NULLIF(w.cns20, '')::INT)  AS jobs_public_admin
            FROM newsrc_lodes_wac_2022 w
            WHERE LENGTH(TRIM(w.w_geocode)) >= 5
            GROUP BY SUBSTRING(w.w_geocode, 1, 2), SUBSTRING(w.w_geocode, 1, 5)
        )
        SELECT
            wc.*,
            CASE WHEN wc.total_jobs > 0
                 THEN ROUND(wc.jobs_earn_3334_plus::NUMERIC / wc.total_jobs, 4)
                 ELSE NULL END AS pct_high_earning,
            CASE WHEN wc.total_jobs > 0
                 THEN ROUND(wc.jobs_manufacturing::NUMERIC / wc.total_jobs, 4)
                 ELSE NULL END AS pct_manufacturing,
            CASE WHEN wc.total_jobs > 0
                 THEN ROUND(wc.jobs_healthcare::NUMERIC / wc.total_jobs, 4)
                 ELSE NULL END AS pct_healthcare
        FROM wac_county wc
        WHERE wc.total_jobs > 0
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_lodes_county ON cur_lodes_geo_metrics (county_fips)", "index county")
    _execute(conn, "CREATE INDEX idx_cur_lodes_state ON cur_lodes_geo_metrics (state_fips)", "index state")

    cnt = _row_count(conn, "cur_lodes_geo_metrics")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# 6. ABS geo x NAICS (demographics)
# ---------------------------------------------------------------------------
def build_abs(conn):
    print("\n=== cur_abs_geo_naics ===")
    if not _table_exists(conn, "newsrc_abs_raw"):
        print("  [skip] newsrc_abs_raw does not exist")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_abs_geo_naics CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_abs_geo_naics AS
        SELECT
            TRIM(NULLIF(geo_id, ''))                   AS geo_id,
            -- Extract state FIPS from GEO_ID (e.g. "0400000US01" -> "01")
            CASE WHEN geo_id LIKE '%%US%%'
                 THEN RIGHT(TRIM(geo_id), 2)
                 ELSE NULL END                          AS state_fips,
            TRIM(NULLIF(naics2022, ''))                 AS naics,
            TRIM(NULLIF(naics2022_label, ''))           AS naics_label,
            TRIM(NULLIF(abs_dataset, ''))               AS abs_dataset,
            TRIM(NULLIF(abs_geo_level, ''))             AS geo_level,
            TRIM(NULLIF(abs_vintage, ''))               AS vintage,
            -- Owner demographics (abscbo dataset)
            TRIM(NULLIF(owner_sex, ''))                 AS owner_sex,
            TRIM(NULLIF(owner_race, ''))                AS owner_race,
            TRIM(NULLIF(owner_eth, ''))                 AS owner_ethnicity,
            TRIM(NULLIF(owner_vet, ''))                 AS owner_veteran,
            -- Firm demographics (abscs/abscb/absmcb datasets)
            TRIM(NULLIF(sex, ''))                       AS sex,
            TRIM(NULLIF(race_group, ''))                AS race_group,
            TRIM(NULLIF(eth_group, ''))                 AS eth_group,
            TRIM(NULLIF(vet_group, ''))                 AS vet_group,
            -- Firm count (different column per dataset type)
            COALESCE(
                NULLIF(TRIM(firmpdemp), ''),
                NULLIF(TRIM(ownpdemp), '')
            )::INT                                      AS firm_count,
            TRIM(NULLIF(name, ''))                      AS geo_name
        FROM newsrc_abs_raw
        WHERE COALESCE(NULLIF(TRIM(firmpdemp), ''), NULLIF(TRIM(ownpdemp), '')) IS NOT NULL
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_abs_state_naics ON cur_abs_geo_naics (state_fips, naics)", "index state+naics")
    _execute(conn, "CREATE INDEX idx_cur_abs_dataset ON cur_abs_geo_naics (abs_dataset)", "index dataset")

    cnt = _row_count(conn, "cur_abs_geo_naics")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# 7. ACS workforce demographics
# ---------------------------------------------------------------------------
def build_acs(conn):
    print("\n=== cur_acs_workforce_demographics ===")
    if not _table_exists(conn, "newsrc_acs_occ_demo_profiles"):
        print("  [skip] newsrc_acs_occ_demo_profiles does not exist")
        return

    _execute(conn, "DROP TABLE IF EXISTS cur_acs_workforce_demographics CASCADE", "drop old")
    _execute(conn, """
        CREATE TABLE cur_acs_workforce_demographics AS
        SELECT
            statefip                        AS state_fips,
            met2013                         AS metro_cbsa,
            SUBSTR(indnaics, 1, 4)          AS naics4,
            occsoc                          AS soc_code,
            sex,
            race,
            hispan                          AS hispanic,
            age_bucket,
            educ                            AS education,
            classwkr                        AS worker_class,
            SUM(weighted_count)             AS weighted_workers,
            COUNT(*)                        AS raw_cell_count
        FROM newsrc_acs_occ_demo_profiles
        GROUP BY 1,2,3,4,5,6,7,8,9,10
    """, "create table")

    _execute(conn, "CREATE INDEX idx_cur_acs_state ON cur_acs_workforce_demographics (state_fips)", "index state")
    _execute(conn, "CREATE INDEX idx_cur_acs_state_naics ON cur_acs_workforce_demographics (state_fips, naics4)", "index state+naics")
    _execute(conn, "CREATE INDEX idx_cur_acs_state_metro ON cur_acs_workforce_demographics (state_fips, metro_cbsa)", "index state+metro")

    cnt = _row_count(conn, "cur_acs_workforce_demographics")
    print(f"  => {cnt:,} rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
BUILDERS = {
    "form5500": build_form5500,
    "ppp": build_ppp,
    "usaspending": build_usaspending,
    "cbp": build_cbp,
    "lodes": build_lodes,
    "abs": build_abs,
    "acs": build_acs,
}


def parse_args():
    ap = argparse.ArgumentParser(description="Build curated tables from raw sources")
    ap.add_argument("--only", default=None, help="Comma-separated list of tables to build (e.g. form5500,cbp)")
    return ap.parse_args()


def main():
    args = parse_args()
    targets = list(BUILDERS.keys())
    if args.only:
        targets = [t.strip() for t in args.only.split(",")]
        unknown = set(targets) - set(BUILDERS.keys())
        if unknown:
            raise SystemExit(f"Unknown targets: {unknown}. Valid: {list(BUILDERS.keys())}")

    conn = get_connection()
    try:
        for name in targets:
            BUILDERS[name](conn)
    finally:
        conn.close()

    print(f"\nDone. Built {len(targets)} curated table(s).")


if __name__ == "__main__":
    main()
