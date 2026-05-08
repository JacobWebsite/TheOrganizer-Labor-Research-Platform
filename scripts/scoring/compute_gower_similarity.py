"""
Employer Similarity Engine (Gower Distance)
============================================
Finds the closest union and non-union employers for every employer using
Gower Distance -- a mixed-type distance metric that handles categorical,
numeric, binary, and hierarchical features with partial distance for NULLs.

Each employer gets up to 10 comparables: 5 closest union + 5 closest non-union.

Workflow:
  1. Ensure QCEW wage MV exists
  2. Create/refresh mv_employer_features (data-rich employers only)
  3. Two-pass Gower computation (union comparables, then non-union)
  4. Store top-5 per type in employer_comparables table

Run:
  py scripts/scoring/compute_gower_similarity.py                    # full run
  py scripts/scoring/compute_gower_similarity.py --dry-run          # first block only
  py scripts/scoring/compute_gower_similarity.py --skip-view        # reuse existing view
  py scripts/scoring/compute_gower_similarity.py --recreate-view    # force DROP + CREATE view
  py scripts/scoring/compute_gower_similarity.py --refresh-view     # just refresh view
"""
import sys
import os
import argparse
import time
import numpy as np
import pandas as pd
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection
from scripts.scoring._pipeline_lock import pipeline_lock
import psycopg2.extras


# ============================================================
# Feature weights
# ============================================================
FEATURE_WEIGHTS = {
    'naics_full':           3.0,   # Industry (5-tier hierarchical gradient)
    'employees_here_log':   2.0,   # Workforce size matters for organizing
    'employees_total_log':  1.0,   # Total company scale
    'state':                1.0,   # State labor law environment
    'city':                 0.5,   # Local geography (bonus)
    'company_type':         0.5,   # Minor structural factor
    'is_subsidiary':        1.0,   # Independent vs subsidiary
    'revenue_log':          1.0,   # Financial scale
    'company_age':          0.5,   # Maturity
    'osha_violation_rate':  1.0,   # Workplace safety signal
    'whd_violation_rate':   1.0,   # Wage compliance signal
    'is_federal_contractor': 1.0,  # Government oversight
    'bls_growth_pct':       1.0,   # Industry trajectory (was 0.5)
    'occupation_overlap':   1.5,   # BLS occupation overlap between industries
    'local_avg_pay':        1.0,   # QCEW local wage environment (NEW)
}

CATEGORICAL_FEATURES = ['state', 'city', 'company_type']
NUMERIC_FEATURES = ['employees_here_log', 'employees_total_log', 'revenue_log',
                     'company_age', 'osha_violation_rate', 'whd_violation_rate',
                     'bls_growth_pct', 'local_avg_pay']
BINARY_FEATURES = ['is_subsidiary', 'is_federal_contractor']
HIERARCHICAL_FEATURE = 'naics_full'
OCCUPATION_FEATURE = 'occupation_overlap'

# Max comparison pool per block (sample down if larger)
MAX_POOL_SIZE = 10000


# ============================================================
# Occupation overlap loading
# ============================================================

_occupation_overlap_cache = {}
_naics_bls_mapping_cache = {}


def load_occupation_overlap(conn):
    """Load pre-computed industry occupation overlap scores into a dict."""
    global _occupation_overlap_cache
    if _occupation_overlap_cache:
        return _occupation_overlap_cache
    cur = conn.cursor()
    try:
        cur.execute("SELECT industry_code_a, industry_code_b, overlap_score FROM industry_occupation_overlap")
        for row in cur.fetchall():
            _occupation_overlap_cache[(row[0], row[1])] = float(row[2])
    except Exception:
        pass  # Table may not exist yet
    return _occupation_overlap_cache


def load_naics_bls_mapping(conn):
    """Load NAICS -> BLS industry code mapping."""
    global _naics_bls_mapping_cache
    if _naics_bls_mapping_cache:
        return _naics_bls_mapping_cache
    cur = conn.cursor()
    try:
        cur.execute("SELECT naics_code, bls_industry_code FROM naics_to_bls_industry")
        for row in cur.fetchall():
            _naics_bls_mapping_cache[row[0]] = row[1]
    except Exception:
        pass
    return _naics_bls_mapping_cache


def get_bls_industry_for_naics(naics_code, naics_bls_map):
    """Map a NAICS code to BLS industry code via hierarchical prefix."""
    if not naics_code or naics_code in ('None', 'nan'):
        return None
    for length in [4, 3, 2]:
        prefix = naics_code[:length]
        if prefix in naics_bls_map:
            return naics_bls_map[prefix]
    return None


def get_occupation_overlap(naics_a, naics_b, overlap_map, naics_bls_map):
    """Get occupation overlap score between two NAICS codes."""
    bls_a = get_bls_industry_for_naics(naics_a, naics_bls_map)
    bls_b = get_bls_industry_for_naics(naics_b, naics_bls_map)
    if bls_a is None or bls_b is None:
        return None
    if bls_a == bls_b:
        return 1.0
    return overlap_map.get((bls_a, bls_b), overlap_map.get((bls_b, bls_a), 0.0))


# ============================================================
# Prerequisite: QCEW state-industry wages MV
# ============================================================

QCEW_MV_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_qcew_state_industry_wages AS
SELECT
    LEFT(area_fips, 2) AS state_fips,
    industry_code AS naics_2,
    year,
    SUM(total_annual_wages) / NULLIF(SUM(annual_avg_emplvl), 0) AS avg_annual_pay,
    SUM(annual_avg_emplvl) AS total_employment,
    COUNT(*) AS county_count
FROM qcew_annual
WHERE own_code = '5'
  AND agglvl_code = '74'
  AND annual_avg_emplvl > 0
  AND avg_annual_pay > 0
GROUP BY LEFT(area_fips, 2), industry_code, year
"""


def _ensure_qcew_mv(conn):
    """Create mv_qcew_state_industry_wages if it doesn't exist."""
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_matviews
        WHERE schemaname = 'public' AND matviewname = 'mv_qcew_state_industry_wages'
    """)
    if cur.fetchone()[0] == 0:
        print("  Creating mv_qcew_state_industry_wages...")
        cur.execute(QCEW_MV_SQL)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_qcew_siw_pk "
                    "ON mv_qcew_state_industry_wages (state_fips, naics_2, year)")
        conn.commit()
        print("  Done.")
    else:
        print("  mv_qcew_state_industry_wages exists.")


# ============================================================
# Step 1: Materialized view
# ============================================================
MV_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_employer_features AS
WITH
-- QCEW latest year benchmarks
qcew_latest AS (
    SELECT state_fips, naics_2, avg_annual_pay
    FROM mv_qcew_state_industry_wages
    WHERE year = (SELECT MAX(year) FROM mv_qcew_state_industry_wages)
),
-- State abbreviation -> FIPS mapping
fips AS (
    SELECT state_abbr, state_fips FROM state_fips_map
),
base AS (
    SELECT DISTINCT ON (me.master_id)
        me.master_id AS employer_id,
        me.canonical_name AS employer_name,
        CASE WHEN me.is_union = TRUE THEN 1 ELSE 0 END AS is_union,
        LEFT(me.naics, 2) AS naics_2,
        LEFT(me.naics, 4) AS naics_4,
        me.naics AS naics_full,
        me.state,
        me.city,
        -- company_type derived from flags
        CASE
            WHEN me.is_public = TRUE THEN 'public'
            WHEN me.is_nonprofit = TRUE THEN 'nonprofit'
            ELSE 'private'
        END AS company_type,
        -- subsidiary status from Mergent (if linked)
        CASE WHEN mg.subsidiary_status IS NOT NULL
             AND mg.subsidiary_status != 'Standalone' THEN 1 ELSE 0 END AS is_subsidiary,
        -- Employee counts: COALESCE master_employers > Mergent site > PPP estimate
        CASE WHEN COALESCE(mg.employees_site, 0) > 0
             THEN LN(1 + mg.employees_site) END AS employees_here_raw,
        CASE WHEN COALESCE(me.employee_count, mg.employees_all_sites, 0) > 0
             THEN LN(1 + COALESCE(me.employee_count, mg.employees_all_sites)) END AS employees_total_raw,
        -- Revenue from Mergent sales or 990 (via research)
        CASE WHEN COALESCE(mg.sales_amount, 0) > 0
             THEN LN(1 + mg.sales_amount) END AS revenue_raw,
        -- Company age from Mergent year_founded or master_employers.founded_year
        CASE WHEN COALESCE(mg.year_founded, me.founded_year) IS NOT NULL
                  AND COALESCE(mg.year_founded, me.founded_year) > 1800
             THEN (2026 - COALESCE(mg.year_founded, me.founded_year))::NUMERIC END AS company_age_raw,
        -- OSHA violation rate: count from linked OSHA matches
        CASE WHEN COALESCE(me.employee_count, mg.employees_site, 1) > 0
             THEN COALESCE(osha_agg.viol_count, 0)::NUMERIC
                  / GREATEST(COALESCE(me.employee_count, mg.employees_site, 1), 1)
             ELSE 0 END AS osha_viol_rate_raw,
        -- WHD violation rate: count from linked WHD matches
        CASE WHEN COALESCE(me.employee_count, mg.employees_site, 1) > 0
             THEN COALESCE(whd_agg.viol_count, 0)::NUMERIC
                  / GREATEST(COALESCE(me.employee_count, mg.employees_site, 1), 1)
             ELSE 0 END AS whd_viol_rate_raw,
        COALESCE(me.is_federal_contractor, FALSE)::INT AS is_federal_contractor,
        COALESCE(
            bip1.employment_change_pct,
            bip2.employment_change_pct
        ) AS bls_growth_raw,
        -- QCEW local wage benchmark (state + NAICS-2)
        qcew.avg_annual_pay AS local_avg_pay_raw
    FROM master_employers me
    -- Mergent data (if linked via master_employer_source_ids)
    LEFT JOIN master_employer_source_ids mesi_mg
        ON mesi_mg.master_id = me.master_id AND mesi_mg.source_system = 'mergent'
    LEFT JOIN mergent_employers mg
        ON mg.id::TEXT = mesi_mg.source_id
    -- OSHA violation counts via source linkage
    LEFT JOIN (
        SELECT mesi.master_id, COUNT(*) AS viol_count
        FROM master_employer_source_ids mesi
        JOIN osha_violations_detail ovd ON ovd.activity_nr::TEXT = mesi.source_id
        WHERE mesi.source_system = 'osha'
        GROUP BY mesi.master_id
    ) osha_agg ON osha_agg.master_id = me.master_id
    -- WHD violation counts via source linkage
    LEFT JOIN (
        SELECT mesi.master_id, COUNT(*) AS viol_count
        FROM master_employer_source_ids mesi
        JOIN whd_cases wcd ON wcd.case_id::TEXT = mesi.source_id
        WHERE mesi.source_system = 'whd'
        GROUP BY mesi.master_id
    ) whd_agg ON whd_agg.master_id = me.master_id
    -- BLS industry growth projections
    LEFT JOIN bls_industry_projections bip1
        ON bip1.matrix_code = LEFT(me.naics, 2) || '0000'
    LEFT JOIN bls_industry_projections bip2
        ON bip2.matrix_code = CASE LEFT(me.naics, 2)
               WHEN '31' THEN '31-330' WHEN '32' THEN '31-330' WHEN '33' THEN '31-330'
               WHEN '44' THEN '44-450' WHEN '45' THEN '44-450'
               WHEN '48' THEN '48-490' WHEN '49' THEN '48-490'
               ELSE NULL
           END
    -- QCEW local wage via state FIPS mapping
    LEFT JOIN fips f ON f.state_abbr = me.state
    LEFT JOIN qcew_latest qcew ON qcew.state_fips = f.state_fips
        AND qcew.naics_2 = LEFT(me.naics, 2)
    WHERE me.naics IS NOT NULL
      AND me.state IS NOT NULL
      -- Data richness filter: NAICS+state + at least 2 more features
      AND (
          (CASE WHEN me.city IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN me.employee_count IS NOT NULL AND me.employee_count > 0 THEN 1 ELSE 0 END)
          + (CASE WHEN COALESCE(mg.year_founded, me.founded_year) IS NOT NULL THEN 1 ELSE 0 END)
          + (CASE WHEN me.is_federal_contractor = TRUE THEN 1 ELSE 0 END)
      ) >= 2
)
SELECT
    employer_id,
    employer_name,
    is_union,
    naics_2,
    naics_4,
    naics_full,
    state,
    city,
    company_type,
    is_subsidiary,
    -- Min-max normalized numeric features
    (employees_here_raw - MIN(employees_here_raw) OVER())
        / NULLIF(MAX(employees_here_raw) OVER() - MIN(employees_here_raw) OVER(), 0)
        AS employees_here_log,
    (employees_total_raw - MIN(employees_total_raw) OVER())
        / NULLIF(MAX(employees_total_raw) OVER() - MIN(employees_total_raw) OVER(), 0)
        AS employees_total_log,
    (revenue_raw - MIN(revenue_raw) OVER())
        / NULLIF(MAX(revenue_raw) OVER() - MIN(revenue_raw) OVER(), 0)
        AS revenue_log,
    (company_age_raw - MIN(company_age_raw) OVER())
        / NULLIF(MAX(company_age_raw) OVER() - MIN(company_age_raw) OVER(), 0)
        AS company_age,
    (osha_viol_rate_raw - MIN(osha_viol_rate_raw) OVER())
        / NULLIF(MAX(osha_viol_rate_raw) OVER() - MIN(osha_viol_rate_raw) OVER(), 0)
        AS osha_violation_rate,
    (whd_viol_rate_raw - MIN(whd_viol_rate_raw) OVER())
        / NULLIF(MAX(whd_viol_rate_raw) OVER() - MIN(whd_viol_rate_raw) OVER(), 0)
        AS whd_violation_rate,
    is_federal_contractor,
    (bls_growth_raw - MIN(bls_growth_raw) OVER())
        / NULLIF(MAX(bls_growth_raw) OVER() - MIN(bls_growth_raw) OVER(), 0)
        AS bls_growth_pct,
    (local_avg_pay_raw - MIN(local_avg_pay_raw) OVER())
        / NULLIF(MAX(local_avg_pay_raw) OVER() - MIN(local_avg_pay_raw) OVER(), 0)
        AS local_avg_pay
FROM base
"""


def create_or_refresh_view(conn, force_recreate=False):
    """Create or refresh the mv_employer_features materialized view."""
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_matviews
        WHERE schemaname = 'public' AND matviewname = 'mv_employer_features'
    """)
    exists = cur.fetchone()[0] > 0

    if exists and not force_recreate:
        print("Refreshing mv_employer_features...")
        cur.execute("REFRESH MATERIALIZED VIEW mv_employer_features")
    else:
        if exists:
            print("Dropping old mv_employer_features (schema changed)...")
            cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_employer_features CASCADE")
            conn.commit()
        print("Creating mv_employer_features from master_employers...")
        cur.execute(MV_SQL)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mvef_eid ON mv_employer_features(employer_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mvef_union ON mv_employer_features(is_union)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_mvef_naics2_state ON mv_employer_features(naics_2, state)")

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM mv_employer_features")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM mv_employer_features WHERE is_union = 1")
    union_ct = cur.fetchone()[0]
    print(f"  Total: {total:,}  Union refs: {union_ct:,}  Non-union: {total - union_ct:,}")
    return total


def create_table(conn):
    """Create employer_comparables table with union/non-union type."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS employer_comparables CASCADE")
    cur.execute("""
        CREATE TABLE employer_comparables (
            id SERIAL PRIMARY KEY,
            employer_id BIGINT NOT NULL,
            comparable_employer_id BIGINT NOT NULL,
            comparable_type TEXT NOT NULL DEFAULT 'union'
                CHECK (comparable_type IN ('union', 'non_union')),
            rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
            gower_distance NUMERIC(6,4) NOT NULL,
            feature_breakdown JSONB,
            computed_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employer_id, comparable_employer_id, comparable_type)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparables_employer ON employer_comparables(employer_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparables_comparable ON employer_comparables(comparable_employer_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparables_employer_type ON employer_comparables(employer_id, comparable_type)")
    conn.commit()
    print("Table employer_comparables ready (master_id based, union + non_union).")


# ============================================================
# Gower distance computation (vectorized)
# ============================================================

def _prefix_ints(arr, level):
    """Convert NAICS string array to integer prefixes at given digit level.
    Returns -1 for entries shorter than level or invalid."""
    result = np.full(len(arr), -1, dtype=np.int64)
    for i, s in enumerate(arr):
        if s not in ('None', 'nan', '', 'NA') and len(s) >= level:
            try:
                result[i] = int(s[:level])
            except ValueError:
                pass
    return result


def compute_gower_chunk(target_df, comparison_df, k=5, overlap_map=None, naics_bls_map=None):
    """Compute Gower distance between each target row and all comparison rows.

    Returns:
        topk_indices: (n_targets, actual_k) - indices into comparison_df
        topk_distances: (n_targets, actual_k) - distances
        topk_breakdowns: list of list of dicts - per-feature distances
    """
    n_targets = len(target_df)
    n_comp = len(comparison_df)
    actual_k = min(k, n_comp)

    if actual_k == 0:
        return (np.zeros((n_targets, 0), dtype=int),
                np.zeros((n_targets, 0)),
                [[] for _ in range(n_targets)])

    all_features = list(FEATURE_WEIGHTS.keys())

    # Distance and weight accumulators: (n_targets, n_comp)
    dist_sum = np.zeros((n_targets, n_comp), dtype=np.float64)
    weight_sum = np.zeros((n_targets, n_comp), dtype=np.float64)
    feature_dists = {}

    for feat in all_features:
        w = FEATURE_WEIGHTS[feat]

        # Occupation overlap is virtual - no column in DataFrame
        if feat == OCCUPATION_FEATURE:
            t_vals = None
            u_vals = None
        elif feat == HIERARCHICAL_FEATURE:
            t_vals = None
            u_vals = None
        else:
            t_vals = target_df[feat].values
            u_vals = comparison_df[feat].values

        if feat == HIERARCHICAL_FEATURE:
            # 5-tier NAICS gradient using full codes:
            #   6-digit match = 0.0
            #   4/5-digit match = 0.2
            #   3-digit match = 0.4
            #   2-digit match = 0.4 (capped)
            #   different = 1.0
            t_naics = target_df['naics_full'].values.astype(str)
            u_naics = comparison_df['naics_full'].values.astype(str)

            d = np.ones((n_targets, n_comp), dtype=np.float64)

            # Apply gradient from coarsest to finest (finer overrides coarser)
            for level, dist_val in [(2, 0.4), (3, 0.4), (4, 0.2), (5, 0.2), (6, 0.0)]:
                t_p = _prefix_ints(t_naics, level)
                u_p = _prefix_ints(u_naics, level)
                t_has = (t_p >= 0)
                u_has = (u_p >= 0)
                match = (t_p[:, None] == u_p[None, :]) & t_has[:, None] & u_has[None, :]
                d[match] = dist_val

            # Valid if both have at least 2-digit NAICS
            t_valid = np.array([len(s) >= 2 and s not in ('None', 'nan', '') for s in t_naics])
            u_valid = np.array([len(s) >= 2 and s not in ('None', 'nan', '') for s in u_naics])
            valid_mask = np.outer(t_valid, u_valid)

            dist_sum += d * w * valid_mask
            weight_sum += w * valid_mask
            feature_dists[feat] = d

        elif feat in CATEGORICAL_FEATURES:
            t_cat = t_vals.astype(str)
            u_cat = u_vals.astype(str)

            t_mat = np.repeat(t_cat[:, np.newaxis], n_comp, axis=1)
            u_mat = np.repeat(u_cat[np.newaxis, :], n_targets, axis=0)

            d = (t_mat != u_mat).astype(np.float64)

            t_null = pd.isna(t_vals) | (t_cat == 'None') | (t_cat == 'nan')
            u_null = pd.isna(u_vals) | (u_cat == 'None') | (u_cat == 'nan')
            valid_mask = np.outer(~t_null, ~u_null)

            dist_sum += d * w * valid_mask
            weight_sum += w * valid_mask
            feature_dists[feat] = d

        elif feat in NUMERIC_FEATURES:
            t_num = pd.to_numeric(t_vals, errors='coerce')
            u_num = pd.to_numeric(u_vals, errors='coerce')

            t_mat = np.repeat(t_num[:, np.newaxis], n_comp, axis=1)
            u_mat = np.repeat(u_num[np.newaxis, :], n_targets, axis=0)

            d = np.abs(t_mat - u_mat)
            d = np.clip(d, 0, 1)

            t_valid = ~np.isnan(t_num)
            u_valid = ~np.isnan(u_num)
            valid_mask = np.outer(t_valid, u_valid)

            dist_sum += np.where(valid_mask, d * w, 0)
            weight_sum += w * valid_mask
            feature_dists[feat] = d

        elif feat == OCCUPATION_FEATURE:
            if overlap_map and naics_bls_map:
                # Vectorized occupation overlap via BLS code matrix lookup
                t_naics_occ = target_df['naics_4'].values.astype(str)
                u_naics_occ = comparison_df['naics_4'].values.astype(str)

                # Map each employer to a BLS industry code
                t_bls = [get_bls_industry_for_naics(n, naics_bls_map) for n in t_naics_occ]
                u_bls = [get_bls_industry_for_naics(n, naics_bls_map) for n in u_naics_occ]

                # Build index of unique BLS codes
                all_codes = sorted(set(c for c in t_bls + u_bls if c is not None))
                if all_codes:
                    code_to_idx = {c: i for i, c in enumerate(all_codes)}
                    nc = len(all_codes)

                    # Pre-compute overlap matrix for unique code pairs
                    olap_mat = np.zeros((nc, nc), dtype=np.float64)
                    for i_c in range(nc):
                        olap_mat[i_c, i_c] = 1.0
                        for j_c in range(i_c + 1, nc):
                            val = overlap_map.get((all_codes[i_c], all_codes[j_c]),
                                    overlap_map.get((all_codes[j_c], all_codes[i_c]), 0.0))
                            olap_mat[i_c, j_c] = val
                            olap_mat[j_c, i_c] = val

                    # Map employers to code indices (-1 for invalid)
                    t_idx = np.array([code_to_idx[c] if c is not None else -1 for c in t_bls])
                    u_idx = np.array([code_to_idx[c] if c is not None else -1 for c in u_bls])

                    valid_t = (t_idx >= 0)
                    valid_u = (u_idx >= 0)
                    valid_mask = np.outer(valid_t, valid_u)

                    # Fancy index into overlap matrix (use 0 for invalid, mask later)
                    t_safe = np.where(valid_t, t_idx, 0)
                    u_safe = np.where(valid_u, u_idx, 0)
                    overlap_vals = olap_mat[t_safe[:, None], u_safe[None, :]]
                    d = 1.0 - overlap_vals
                    d[~valid_mask] = 1.0
                else:
                    d = np.ones((n_targets, n_comp), dtype=np.float64)
                    valid_mask = np.zeros((n_targets, n_comp), dtype=bool)

                dist_sum += np.where(valid_mask, d * w, 0)
                weight_sum += w * valid_mask
                feature_dists[feat] = d
            else:
                feature_dists[feat] = np.ones((n_targets, n_comp), dtype=np.float64) * np.nan
                continue

        elif feat in BINARY_FEATURES:
            t_bin = pd.to_numeric(t_vals, errors='coerce').astype(float)
            u_bin = pd.to_numeric(u_vals, errors='coerce').astype(float)

            t_mat = np.repeat(t_bin[:, np.newaxis], n_comp, axis=1)
            u_mat = np.repeat(u_bin[np.newaxis, :], n_targets, axis=0)

            d = np.abs(t_mat - u_mat)

            t_valid = ~np.isnan(t_bin)
            u_valid = ~np.isnan(u_bin)
            valid_mask = np.outer(t_valid, u_valid)

            dist_sum += np.where(valid_mask, d * w, 0)
            weight_sum += w * valid_mask
            feature_dists[feat] = d

    # Final Gower distance
    gower = np.divide(dist_sum, weight_sum, out=np.ones_like(dist_sum), where=weight_sum > 0)

    # Get top-k nearest (lowest distance)
    if actual_k >= n_comp:
        topk_indices = np.argsort(gower, axis=1)[:, :actual_k]
    else:
        topk_indices = np.argpartition(gower, actual_k, axis=1)[:, :actual_k]

    topk_distances = np.zeros((n_targets, actual_k))
    topk_breakdowns = []

    for i in range(n_targets):
        idx = topk_indices[i]
        dists = gower[i, idx]
        sort_order = np.argsort(dists)
        topk_indices[i] = idx[sort_order]
        topk_distances[i] = dists[sort_order]

        breakdowns = []
        for j_rank in range(actual_k):
            j = topk_indices[i, j_rank]
            bd = {}
            for feat in all_features:
                fd = feature_dists[feat]
                val = fd[i, j]
                bd[feat] = round(float(val), 4) if not np.isnan(val) else None
            breakdowns.append(bd)
        topk_breakdowns.append(breakdowns)

    return topk_indices, topk_distances, topk_breakdowns


# ============================================================
# Comparison pass (reusable for union and non-union)
# ============================================================

def _process_block(block_targets, block_comp, comparable_type, block_label,
                   conn, cur, chunk_size, overlap_map, naics_bls_map):
    """Process one NAICS block: compare targets against comparison pool, insert results."""
    total_inserted = 0
    n_chunks = (len(block_targets) + chunk_size - 1) // chunk_size

    for chunk_idx in range(n_chunks):
        chunk_start = chunk_idx * chunk_size
        chunk_end = min(chunk_start + chunk_size, len(block_targets))
        chunk = block_targets.iloc[chunk_start:chunk_end]

        # Request k+3 to have margin for self-exclusion and dedup
        request_k = min(8, len(block_comp))
        topk_idx, topk_dist, topk_bd = compute_gower_chunk(
            chunk, block_comp, k=request_k,
            overlap_map=overlap_map, naics_bls_map=naics_bls_map
        )

        insert_rows = []
        for i in range(len(chunk)):
            target_eid = int(chunk.iloc[i]['employer_id'])
            seen = set()
            rank_num = 0
            for r in range(topk_idx.shape[1]):
                comp_idx = topk_idx[i, r]
                comp_eid = int(block_comp.iloc[comp_idx]['employer_id'])
                if comp_eid == target_eid:  # self-exclusion
                    continue
                if comp_eid in seen:
                    continue
                seen.add(comp_eid)
                rank_num += 1
                if rank_num > 5:
                    break
                distance = round(float(topk_dist[i, r]), 4)
                breakdown = json.dumps(topk_bd[i][r])
                insert_rows.append((target_eid, comp_eid, comparable_type,
                                    rank_num, distance, breakdown))

        # Dedup by (employer_id, comparable_employer_id, type)
        seen_triples = set()
        deduped = []
        for row in insert_rows:
            triple = (row[0], row[1], row[2])
            if triple not in seen_triples:
                seen_triples.add(triple)
                deduped.append(row)

        if deduped:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO employer_comparables
                   (employer_id, comparable_employer_id, comparable_type,
                    rank, gower_distance, feature_breakdown)
                   VALUES %s
                   ON CONFLICT (employer_id, comparable_employer_id, comparable_type) DO UPDATE
                   SET rank = EXCLUDED.rank,
                       gower_distance = EXCLUDED.gower_distance,
                       feature_breakdown = EXCLUDED.feature_breakdown,
                       computed_at = NOW()""",
                deduped, page_size=1000
            )
            conn.commit()
            total_inserted += len(deduped)

    return total_inserted


def _compute_pass(all_df, comparison_pool, comparable_type,
                  conn, cur, chunk_size, overlap_map, naics_bls_map,
                  max_pool_size=None, blocking='naics_2', dry_run=False):
    """Run one comparison pass with configurable blocking strategy.

    Args:
        all_df: DataFrame of ALL employers (targets for this pass)
        comparison_pool: DataFrame of employers to compare against
        comparable_type: 'union' or 'non_union'
        max_pool_size: Cap comparison pool per block (sample if larger)
        blocking: 'naics_2' or 'naics_3' -- which NAICS level to block on.
                  For naics_3: employers with only 2-digit NAICS fall back
                  to naics_2 blocks so they aren't excluded.
    """
    total_inserted = 0
    total_processed = 0
    total_employers = len(all_df)
    start_time = time.time()

    block_col = blocking  # 'naics_2' or 'naics_3'

    # For naics_3 blocking, we need a naics_3 column
    if blocking == 'naics_3':
        # Create naics_3 from naics_full (first 3 digits, or naics_2 if shorter)
        all_df = all_df.copy()
        comparison_pool = comparison_pool.copy()
        all_df['naics_3'] = all_df['naics_full'].apply(
            lambda x: str(x)[:3] if isinstance(x, str) and len(str(x)) >= 3
                      and str(x) not in ('None', 'nan', '') else None)
        comparison_pool['naics_3'] = comparison_pool['naics_full'].apply(
            lambda x: str(x)[:3] if isinstance(x, str) and len(str(x)) >= 3
                      and str(x) not in ('None', 'nan', '') else None)

        # Split: employers WITH naics_3 use fine blocking,
        #        employers with only naics_2 fall back to naics_2 blocking
        has_n3_targets = all_df[all_df['naics_3'].notna()]
        no_n3_targets = all_df[all_df['naics_3'].isna()]
        has_n3_comp = comparison_pool[comparison_pool['naics_3'].notna()]
        no_n3_comp = comparison_pool[comparison_pool['naics_3'].isna()]

        print(f"\n  --- {comparable_type.upper()} PASS (hybrid NAICS-3/NAICS-2 blocking) ---")
        print(f"  Targets: {total_employers:,}  Comparison pool: {len(comparison_pool):,}")
        print(f"  NAICS-3 targets: {len(has_n3_targets):,}  Fallback NAICS-2: {len(no_n3_targets):,}")

        # Pass A: NAICS-3 blocked (fine-grained)
        n3_comp_groups = has_n3_comp.groupby('naics_3')
        n3_comp_counts = {k: len(v) for k, v in n3_comp_groups}
        n3_target_groups = has_n3_targets.groupby('naics_3')
        n3_block_names = sorted(set(has_n3_targets['naics_3'].dropna().unique()))

        print(f"  NAICS-3 blocks: {len(n3_block_names)} (targets) / {len(n3_comp_counts)} (comparison)")

        for block_idx, n3 in enumerate(n3_block_names):
            block_targets = n3_target_groups.get_group(n3).reset_index(drop=True)

            if n3 not in n3_comp_counts:
                total_processed += len(block_targets)
                continue

            block_comp = n3_comp_groups.get_group(n3).reset_index(drop=True)

            # Also include naics_2-only comparison employers from same 2-digit sector
            n2 = n3[:2]
            n2_fallback = no_n3_comp[no_n3_comp['naics_2'] == n2]
            if len(n2_fallback) > 0:
                block_comp = pd.concat([block_comp, n2_fallback], ignore_index=True)

            if len(block_comp) < 3:
                total_processed += len(block_targets)
                continue

            if max_pool_size and len(block_comp) > max_pool_size:
                block_comp = block_comp.sample(n=max_pool_size, random_state=42).reset_index(drop=True)

            inserted = _process_block(
                block_targets, block_comp, comparable_type, f"NAICS-{n3}",
                conn, cur, chunk_size, overlap_map, naics_bls_map
            )
            total_inserted += inserted
            total_processed += len(block_targets)

            pct = 100 * total_processed / total_employers
            elapsed = time.time() - start_time
            eta = elapsed / max(total_processed, 1) * (total_employers - total_processed)
            print(f"  [{comparable_type}] NAICS-{n3}: {len(block_targets):,} x {len(block_comp):,} "
                  f"({pct:.1f}%) inserted={total_inserted:,}  ETA={eta / 60:.1f}min")

            if dry_run:
                print(f"  --dry-run: stopping {comparable_type} pass after first block")
                elapsed = time.time() - start_time
                print(f"  {comparable_type} pass (partial): {elapsed / 60:.1f}min, "
                      f"{total_inserted:,} rows, {total_processed:,} employers processed")
                return total_inserted

        # Pass B: NAICS-2 fallback for employers with only 2-digit NAICS
        if len(no_n3_targets) > 0:
            print(f"  --- Fallback: {len(no_n3_targets):,} targets with only NAICS-2 ---")
            n2_target_groups = no_n3_targets.groupby('naics_2')
            # For comparison, use ALL employers in the same NAICS-2 (both fine and coarse)
            all_comp_n2_groups = comparison_pool.groupby('naics_2')

            for n2 in sorted(set(no_n3_targets['naics_2'].dropna().unique())):
                block_targets = n2_target_groups.get_group(n2).reset_index(drop=True)
                if n2 not in {k: True for k in all_comp_n2_groups.groups}:
                    total_processed += len(block_targets)
                    continue
                block_comp = all_comp_n2_groups.get_group(n2).reset_index(drop=True)
                if len(block_comp) < 3:
                    total_processed += len(block_targets)
                    continue
                if max_pool_size and len(block_comp) > max_pool_size:
                    block_comp = block_comp.sample(n=max_pool_size, random_state=42).reset_index(drop=True)

                inserted = _process_block(
                    block_targets, block_comp, comparable_type, f"NAICS-{n2}(fb)",
                    conn, cur, chunk_size, overlap_map, naics_bls_map
                )
                total_inserted += inserted
                total_processed += len(block_targets)

                pct = 100 * total_processed / total_employers
                elapsed = time.time() - start_time
                eta = elapsed / max(total_processed, 1) * (total_employers - total_processed)
                print(f"  [{comparable_type}] NAICS-{n2}(fallback): {len(block_targets):,} x {len(block_comp):,} "
                      f"({pct:.1f}%) inserted={total_inserted:,}  ETA={eta / 60:.1f}min")

    else:
        # Simple NAICS-2 blocking (used for union pass)
        print(f"\n  --- {comparable_type.upper()} PASS (NAICS-2 blocking) ---")
        print(f"  Targets: {total_employers:,}  Comparison pool: {len(comparison_pool):,}")

        target_groups = all_df.groupby('naics_2')
        comp_groups = comparison_pool.groupby('naics_2')
        comp_counts = {k: len(v) for k, v in comp_groups}

        print(f"  NAICS-2 blocks with comparisons: {len(comp_counts)}")

        block_names = sorted(set(all_df['naics_2'].dropna().unique()))

        for block_idx, naics_2 in enumerate(block_names):
            block_targets = target_groups.get_group(naics_2).reset_index(drop=True)

            if naics_2 not in comp_counts:
                total_processed += len(block_targets)
                continue

            block_comp = comp_groups.get_group(naics_2).reset_index(drop=True)

            if len(block_comp) < 3:
                total_processed += len(block_targets)
                continue

            if max_pool_size and len(block_comp) > max_pool_size:
                block_comp = block_comp.sample(n=max_pool_size, random_state=42).reset_index(drop=True)

            inserted = _process_block(
                block_targets, block_comp, comparable_type, f"NAICS-{naics_2}",
                conn, cur, chunk_size, overlap_map, naics_bls_map
            )
            total_inserted += inserted
            total_processed += len(block_targets)

            pct = 100 * total_processed / total_employers
            elapsed = time.time() - start_time
            eta = elapsed / max(total_processed, 1) * (total_employers - total_processed)
            print(f"  [{comparable_type}] NAICS-{naics_2}: {len(block_targets):,} x {len(block_comp):,} "
                  f"({pct:.1f}%) inserted={total_inserted:,}  ETA={eta / 60:.1f}min")

            if dry_run:
                print(f"  --dry-run: stopping {comparable_type} pass after first block")
                break

    elapsed = time.time() - start_time
    print(f"  {comparable_type} pass complete: {elapsed / 60:.1f}min, "
          f"{total_inserted:,} rows, {total_processed:,} employers processed")
    return total_inserted


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Compute Gower similarity for employer comparables')
    parser.add_argument('--dry-run', action='store_true', help='Process first block only per pass')
    parser.add_argument('--chunk-size', type=int, default=2500, help='Rows per chunk (default 2500)')
    parser.add_argument('--refresh-view', action='store_true', help='Only refresh materialized view')
    parser.add_argument('--recreate-view', action='store_true', help='Force DROP + CREATE view')
    parser.add_argument('--skip-view', action='store_true', help='Skip view creation/refresh')
    parser.add_argument('--occ-weight', type=float, default=1.5, help='Occupation overlap feature weight')
    args = parser.parse_args()

    FEATURE_WEIGHTS['occupation_overlap'] = args.occ_weight

    conn = get_connection()
    cur = conn.cursor()

    with pipeline_lock(conn, 'gower_similarity'):
        _run(conn, cur, args)

    conn.close()
    print(f"\n{'=' * 70}")
    print("DONE")
    print(f"{'=' * 70}")


def _run(conn, cur, args):
    print("=" * 70)
    print("EMPLOYER SIMILARITY ENGINE (GOWER DISTANCE)")
    print("  5-tier NAICS gradient | QCEW wages | union + non-union comparables")
    print("=" * 70)

    # ============================================================
    # Step 0: Ensure prerequisite MVs
    # ============================================================
    print("\n=== Step 0: Prerequisites ===")
    _ensure_qcew_mv(conn)

    # ============================================================
    # Step 1: Materialized view
    # ============================================================
    if not args.skip_view:
        print("\n=== Step 1: Materialized view ===")
        create_or_refresh_view(conn, force_recreate=getattr(args, 'recreate_view', False))
        if args.refresh_view:
            print("View refreshed. Exiting (--refresh-view mode).")
            return

    # ============================================================
    # Step 2: Create table
    # ============================================================
    print("\n=== Step 2: Ensure table schema ===")
    create_table(conn)

    # ============================================================
    # Step 3: Load data
    # ============================================================
    print("\n=== Step 3: Loading feature data ===")
    df = pd.read_sql("SELECT * FROM mv_employer_features", conn)
    df = df.drop_duplicates(subset=['employer_id'], keep='first')
    print(f"  Total rows: {len(df):,}")

    union_pool = df[df['is_union'] == 1].copy().reset_index(drop=True)
    nonunion_pool = df[df['is_union'] == 0].copy().reset_index(drop=True)
    print(f"  Union references: {len(union_pool):,}")
    print(f"  Non-union targets: {len(nonunion_pool):,}")

    if len(union_pool) == 0:
        print("ERROR: No union references found. Aborting.")
        return

    # ============================================================
    # Step 3b: Load occupation overlap data
    # ============================================================
    print("\n=== Step 3b: Loading occupation overlap ===")
    overlap_map = load_occupation_overlap(conn)
    naics_bls_map = load_naics_bls_mapping(conn)
    print(f"  Overlap pairs: {len(overlap_map):,}")
    print(f"  NAICS->BLS mappings: {len(naics_bls_map):,}")
    if not overlap_map:
        print("  WARNING: No occupation overlap data. Skipping occupation_overlap feature.")

    # ============================================================
    # Step 4: Pass 1 - Union comparables
    # ============================================================
    print(f"\n=== Step 4: Union comparables (chunk_size={args.chunk_size}) ===")
    union_inserted = _compute_pass(
        all_df=df,
        comparison_pool=union_pool,
        comparable_type='union',
        conn=conn, cur=cur,
        chunk_size=args.chunk_size,
        overlap_map=overlap_map,
        naics_bls_map=naics_bls_map,
        max_pool_size=MAX_POOL_SIZE,  # cap at 10K per block
        blocking='naics_2',           # union employers mostly have 2-digit NAICS
        dry_run=args.dry_run,
    )

    # ============================================================
    # Step 5: Pass 2 - Non-union comparables
    # ============================================================
    print(f"\n=== Step 5: Non-union comparables (chunk_size={args.chunk_size}) ===")
    nonunion_inserted = _compute_pass(
        all_df=df,
        comparison_pool=nonunion_pool,
        comparable_type='non_union',
        conn=conn, cur=cur,
        chunk_size=args.chunk_size,
        overlap_map=overlap_map,
        naics_bls_map=naics_bls_map,
        max_pool_size=MAX_POOL_SIZE,  # cap at 10K per block
        blocking='naics_3',           # finer blocking (most have 6-digit NAICS)
        dry_run=args.dry_run,
    )

    # ============================================================
    # Step 6: Summary
    # ============================================================
    print("\n=== Step 6: Summary ===")

    cur.execute("""
        SELECT comparable_type,
               COUNT(*) AS rows,
               COUNT(DISTINCT employer_id) AS employers
        FROM employer_comparables
        GROUP BY comparable_type
        ORDER BY comparable_type
    """)
    print("\n  Rows by type:")
    for row in cur.fetchall():
        print(f"    {row[0]:12s}  {row[1]:>10,} rows  {row[2]:>10,} employers")

    cur.execute("""
        SELECT comparable_type,
               AVG(gower_distance) AS avg_dist,
               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gower_distance) AS median,
               MIN(gower_distance) AS min_dist,
               MAX(gower_distance) AS max_dist
        FROM employer_comparables
        GROUP BY comparable_type
    """)
    print("\n  Distance distribution by type:")
    print(f"    {'Type':12s} {'Avg':>8s} {'Median':>8s} {'Min':>8s} {'Max':>8s}")
    for row in cur.fetchall():
        print(f"    {row[0]:12s} {float(row[1]):.4f} {float(row[2]):.4f} "
              f"{float(row[3]):.4f} {float(row[4]):.4f}")

    total = union_inserted + nonunion_inserted
    print(f"\n  Total: {total:,} comparables inserted "
          f"({union_inserted:,} union + {nonunion_inserted:,} non-union)")


if __name__ == '__main__':
    main()
