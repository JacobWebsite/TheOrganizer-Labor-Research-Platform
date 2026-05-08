"""
Build curated CPS ORG union density tables.

Reads `cps_org_raw` and produces sub-state, industry-cross, and time-series
density rollups that aren't available in the existing `bls_state_density`,
`unionstats_*`, or `msa_union_stats` tables.

Outputs (all curated tables drop+rebuild on every run):
  cur_cps_density_state           -- state x sector, pooled 2019-2024
  cur_cps_density_state_year      -- state x sector x year (time series)
  cur_cps_density_state_industry  -- state x sector x IND code (NEW capability)
  cur_cps_density_msa             -- MSA x sector, pooled (subset of msa_union_stats but with our pooling)
  cur_cps_density_msa_industry    -- MSA x sector x IND (NEW — killer feature)
  cur_cps_density_state_occ       -- state x sector x OCC2010 (NEW)

Density methodology (matches BLS Union Members Summary):
  - Universe: wage and salary workers age 16+ who answered the union question
    (UNION IN ('1','2'); excludes NIU=0 and rare covered-non-member=3)
  - Private wage: CLASSWKR='22'
  - Public wage:  CLASSWKR IN ('23','25','27','28')
  - Total wage:   CLASSWKR IN ('22','23','25','27','28')
  - Member: UNION='2'
  - Weight: EARNWT (4 implied decimals — divided by 10000)
  - Density = SUM(weight * member) / SUM(weight) * 100

Reliability: the BLS publishes an N>=50,000 employment threshold for state-level
density estimates. We mark cells with raw_n<30 as unreliable; downstream
consumers should treat these as suppressed.

Usage:
  py scripts/etl/cps_curate_density.py
  py scripts/etl/cps_curate_density.py --only state,msa_industry
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection  # noqa: E402


# CLASSWKR sector buckets (CPS codes)
SECTOR_CASE = """
    CASE
        WHEN classwkr = '22' THEN 'private'
        WHEN classwkr IN ('23','25','27','28') THEN 'public'
        ELSE NULL
    END
"""

# Common ORG / wage filter
WAGE_FILTER = """
    earnwt::numeric > 0
    AND \"union\" IN ('1','2')
    AND classwkr IN ('22','23','25','27','28')
"""


def _execute(conn, sql: str, label: str):
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  [{time.time()-t0:.1f}s] {label}")


def _row_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# 1. State pooled (validation target — should match bls_state_density 2024)
# ---------------------------------------------------------------------------
def build_state(conn):
    print("\n=== cur_cps_density_state ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_state CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_state AS
        WITH wage AS (
            SELECT statefip, year,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
        )
        SELECT statefip,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((statefip, sector), (statefip))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_density_state ON cur_cps_density_state (statefip, sector)", "index")
    print(f"  => {_row_count(conn, 'cur_cps_density_state'):,} rows")


# ---------------------------------------------------------------------------
# 2. State x year (time series)
# ---------------------------------------------------------------------------
def build_state_year(conn):
    print("\n=== cur_cps_density_state_year ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_state_year CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_state_year AS
        WITH wage AS (
            SELECT statefip, year::int AS year,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
        )
        SELECT statefip, year,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((statefip, year, sector), (statefip, year))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_density_state_year ON cur_cps_density_state_year (statefip, year, sector)", "index")
    print(f"  => {_row_count(conn, 'cur_cps_density_state_year'):,} rows")


# ---------------------------------------------------------------------------
# 3. State x industry (NEW capability — not in unionstats_industry)
# ---------------------------------------------------------------------------
def build_state_industry(conn):
    print("\n=== cur_cps_density_state_industry ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_state_industry CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_state_industry AS
        WITH wage AS (
            SELECT statefip, ind,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
              AND ind IS NOT NULL AND ind <> ''
        )
        SELECT statefip,
               ind,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((statefip, ind, sector), (statefip, ind))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_si_state ON cur_cps_density_state_industry (statefip, ind)", "index 1")
    _execute(conn, "CREATE INDEX idx_cur_cps_si_ind ON cur_cps_density_state_industry (ind, sector)", "index 2")
    print(f"  => {_row_count(conn, 'cur_cps_density_state_industry'):,} rows")


# ---------------------------------------------------------------------------
# 4. MSA pooled
# ---------------------------------------------------------------------------
def build_msa(conn):
    print("\n=== cur_cps_density_msa ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_msa CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_msa AS
        WITH wage AS (
            SELECT metfips,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
              AND metfips NOT IN ('00000', '99998', '99999')
              AND metfips IS NOT NULL
        )
        SELECT metfips,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((metfips, sector), (metfips))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_msa ON cur_cps_density_msa (metfips, sector)", "index")
    print(f"  => {_row_count(conn, 'cur_cps_density_msa'):,} rows")


# ---------------------------------------------------------------------------
# 5. MSA x industry (NEW — killer feature for sub-state organizing)
# ---------------------------------------------------------------------------
def build_msa_industry(conn):
    print("\n=== cur_cps_density_msa_industry ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_msa_industry CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_msa_industry AS
        WITH wage AS (
            SELECT metfips, ind,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
              AND metfips NOT IN ('00000', '99998', '99999')
              AND metfips IS NOT NULL
              AND ind IS NOT NULL AND ind <> ''
        )
        SELECT metfips, ind,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((metfips, ind, sector), (metfips, ind))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_msaind_msa ON cur_cps_density_msa_industry (metfips, ind)", "index 1")
    _execute(conn, "CREATE INDEX idx_cur_cps_msaind_ind ON cur_cps_density_msa_industry (ind, sector)", "index 2")
    print(f"  => {_row_count(conn, 'cur_cps_density_msa_industry'):,} rows")


# ---------------------------------------------------------------------------
# 6. State x occupation (NEW — for occupation-targeted organizing)
# ---------------------------------------------------------------------------
def build_state_occ(conn):
    print("\n=== cur_cps_density_state_occ ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_state_occ CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_state_occ AS
        WITH wage AS (
            SELECT statefip, occ2010,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
              AND occ2010 IS NOT NULL AND occ2010 <> ''
        )
        SELECT statefip, occ2010,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((statefip, occ2010, sector), (statefip, occ2010))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_so_state ON cur_cps_density_state_occ (statefip, occ2010)", "index 1")
    _execute(conn, "CREATE INDEX idx_cur_cps_so_occ ON cur_cps_density_state_occ (occ2010, sector)", "index 2")
    print(f"  => {_row_count(conn, 'cur_cps_density_state_occ'):,} rows")


# ---------------------------------------------------------------------------
# 7. County pooled (CPS COUNTY field is full 5-digit state+county FIPS;
#    Census suppresses COUNTY for households in counties below ~100K population
#    so coverage is only ~280 of 3,143 US counties — see CPS ORG Microdata note)
# ---------------------------------------------------------------------------
def build_county(conn):
    print("\n=== cur_cps_density_county ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_county CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_county AS
        WITH wage AS (
            SELECT statefip, county,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
              AND county IS NOT NULL AND county NOT IN ('00000', '0')
        )
        SELECT statefip, county,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((statefip, county, sector), (statefip, county))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_county ON cur_cps_density_county (county, sector)", "index")
    print(f"  => {_row_count(conn, 'cur_cps_density_county'):,} rows")


# ---------------------------------------------------------------------------
# 8. County x industry (NEW — only viable for very large counties: LA, NYC, etc.)
# ---------------------------------------------------------------------------
def build_county_industry(conn):
    print("\n=== cur_cps_density_county_industry ===")
    _execute(conn, "DROP TABLE IF EXISTS cur_cps_density_county_industry CASCADE", "drop old")
    _execute(conn, f"""
        CREATE TABLE cur_cps_density_county_industry AS
        WITH wage AS (
            SELECT statefip, county, ind,
                   {SECTOR_CASE} AS sector,
                   earnwt::numeric / 10000.0 AS w,
                   CASE WHEN "union" = '2' THEN 1 ELSE 0 END AS member
            FROM cps_org_raw
            WHERE {WAGE_FILTER}
              AND county IS NOT NULL AND county NOT IN ('00000', '0')
              AND ind IS NOT NULL AND ind <> ''
        )
        SELECT statefip, county, ind,
               COALESCE(sector, 'all') AS sector,
               COUNT(*)                            AS raw_n,
               ROUND(SUM(w)::numeric, 1)          AS weighted_workers,
               ROUND(SUM(w * member)::numeric, 1) AS weighted_members,
               ROUND((SUM(w * member) / NULLIF(SUM(w), 0) * 100)::numeric, 2) AS pct_member,
               '2019-2024'::text AS years_covered,
               (COUNT(*) < 30) AS unreliable
        FROM wage
        GROUP BY GROUPING SETS ((statefip, county, ind, sector), (statefip, county, ind))
    """, "create table")
    _execute(conn, "CREATE INDEX idx_cur_cps_ci_county ON cur_cps_density_county_industry (county, ind)", "index 1")
    _execute(conn, "CREATE INDEX idx_cur_cps_ci_ind ON cur_cps_density_county_industry (ind, sector)", "index 2")
    print(f"  => {_row_count(conn, 'cur_cps_density_county_industry'):,} rows")


BUILDERS = {
    "state":            build_state,
    "state_year":       build_state_year,
    "state_industry":   build_state_industry,
    "msa":              build_msa,
    "msa_industry":     build_msa_industry,
    "state_occ":        build_state_occ,
    "county":           build_county,
    "county_industry":  build_county_industry,
}


def parse_args():
    ap = argparse.ArgumentParser(description="Build curated CPS density tables")
    ap.add_argument("--only", default=None,
                    help="Comma-separated subset (default: all). "
                         f"Choices: {','.join(BUILDERS)}")
    return ap.parse_args()


def main():
    args = parse_args()
    if args.only:
        wanted = [s.strip() for s in args.only.split(",") if s.strip()]
        bad = [s for s in wanted if s not in BUILDERS]
        if bad:
            raise SystemExit(f"Unknown builders: {bad}. Valid: {list(BUILDERS)}")
        builders = [(k, BUILDERS[k]) for k in wanted]
    else:
        builders = list(BUILDERS.items())

    conn = get_connection()
    try:
        for name, fn in builders:
            fn(conn)
    finally:
        conn.close()
    print(f"\nDone. Built {len(builders)} curated CPS density table(s).")


if __name__ == "__main__":
    main()
