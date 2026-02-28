"""
Phase 3: Employer Similarity Engine (Gower Distance)
=====================================================
Finds non-union employers most similar to unionized ones using Gower Distance,
a mixed-type distance metric that handles categorical + numeric + binary features
with partial distance for NULLs.

Workflow:
  1. Create/refresh materialized view mv_employer_features
  2. Load into pandas, split union refs vs non-union targets
  3. Compute pairwise Gower distances in vectorized numpy chunks
  4. Store top-5 nearest matches in employer_comparables table
  5. Update similarity_score on mergent_employers

Run:
  py scripts/scoring/compute_gower_similarity.py           # full run
  py scripts/scoring/compute_gower_similarity.py --dry-run  # first chunk only
  py scripts/scoring/compute_gower_similarity.py --skip-view # reuse existing view
  py scripts/scoring/compute_gower_similarity.py --refresh-view  # just refresh view
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
    'naics_4':              3.0,   # Industry is strongest predictor
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
    'bls_growth_pct':       0.5,   # Industry trajectory
    'occupation_overlap':   1.5,   # BLS occupation overlap between industries (Phase 5.4c)
}

CATEGORICAL_FEATURES = ['state', 'city', 'company_type']
NUMERIC_FEATURES = ['employees_here_log', 'employees_total_log', 'revenue_log',
                     'company_age', 'osha_violation_rate', 'whd_violation_rate',
                     'bls_growth_pct']
BINARY_FEATURES = ['is_subsidiary', 'is_federal_contractor']
HIERARCHICAL_FEATURE = 'naics_4'  # special handling
OCCUPATION_FEATURE = 'occupation_overlap'  # Phase 5.4c


# ============================================================
# Occupation overlap loading (Phase 5.4c)
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


def get_bls_industry_for_naics(naics_4, naics_bls_map):
    """Map a 4-digit NAICS code to BLS industry code via hierarchical prefix."""
    if not naics_4 or naics_4 in ('None', 'nan'):
        return None
    # Try exact 4-digit, then 3, then 2
    for length in [4, 3, 2]:
        prefix = naics_4[:length]
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
# Step 1: Materialized view
# ============================================================
MV_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_employer_features AS
WITH base AS (
    SELECT
        me.master_id AS employer_id,
        me.canonical_name AS employer_name,
        CASE WHEN me.is_union = TRUE THEN 1 ELSE 0 END AS is_union,
        LEFT(me.naics, 2) AS naics_2,
        LEFT(me.naics, 4) AS naics_4,
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
        -- Company age from Mergent year_founded
        CASE WHEN mg.year_founded IS NOT NULL AND mg.year_founded > 1800
             THEN (2026 - mg.year_founded)::NUMERIC END AS company_age_raw,
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
        ) AS bls_growth_raw
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
        JOIN whd_case_details wcd ON wcd.case_id::TEXT = mesi.source_id
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
    WHERE me.naics IS NOT NULL
      AND me.state IS NOT NULL
)
SELECT
    employer_id,
    employer_name,
    is_union,
    naics_2,
    naics_4,
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
        AS bls_growth_pct
FROM base
"""


def create_or_refresh_view(conn, force_recreate=False):
    """Create or refresh the mv_employer_features materialized view.

    If force_recreate is True or the view doesn't exist, does DROP + CREATE.
    Otherwise refreshes the existing MV.
    """
    cur = conn.cursor()
    # Check if view exists
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
    print(f"  Total: {total:,}  Union refs: {union_ct:,}  Targets: {total - union_ct:,}")
    return total


def create_table(conn):
    """Create employer_comparables table and add similarity_score column."""
    cur = conn.cursor()
    # Drop old table with FK to mergent_employers (if exists)
    cur.execute("DROP TABLE IF EXISTS employer_comparables CASCADE")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employer_comparables (
            id SERIAL PRIMARY KEY,
            employer_id BIGINT NOT NULL,
            comparable_employer_id BIGINT NOT NULL,
            rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 5),
            gower_distance NUMERIC(6,4) NOT NULL,
            feature_breakdown JSONB,
            computed_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(employer_id, comparable_employer_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparables_employer ON employer_comparables(employer_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_comparables_comparable ON employer_comparables(comparable_employer_id)")
    conn.commit()
    print("Table employer_comparables ready (master_id based).")


# ============================================================
# Gower distance computation (vectorized)
# ============================================================

def compute_gower_chunk(target_df, union_df, overlap_map=None, naics_bls_map=None):
    """Compute Gower distance between each target row and all union rows.

    Returns:
        top5_indices: (len(target_df), 5) - indices into union_df
        top5_distances: (len(target_df), 5) - distances
        top5_breakdowns: list of list of dicts - per-feature distances
    """
    n_targets = len(target_df)
    n_unions = len(union_df)

    # Pre-extract arrays for each feature type
    all_features = list(FEATURE_WEIGHTS.keys())
    weights = np.array([FEATURE_WEIGHTS[f] for f in all_features])

    # Initialize distance accumulator and weight accumulator
    # Shape: (n_targets, n_unions) for each
    dist_sum = np.zeros((n_targets, n_unions), dtype=np.float64)
    weight_sum = np.zeros((n_targets, n_unions), dtype=np.float64)

    # Per-feature distance storage for breakdown
    feature_dists = {}

    for feat in all_features:
        w = FEATURE_WEIGHTS[feat]

        # Occupation overlap is virtual - no column in DataFrame
        if feat == OCCUPATION_FEATURE:
            t_vals = None
            u_vals = None
        else:
            t_vals = target_df[feat].values
            u_vals = union_df[feat].values

        if feat == HIERARCHICAL_FEATURE:
            # NAICS hierarchical: exact 4-digit=0, same 2-digit=0.3, different=1.0
            t_naics4 = target_df['naics_4'].values.astype(str)
            u_naics4 = union_df['naics_4'].values.astype(str)
            t_naics2 = target_df['naics_2'].values.astype(str)
            u_naics2 = union_df['naics_2'].values.astype(str)

            # Build matrices
            # t_naics4[:, None] broadcasts to (n_targets, n_unions)
            t4_mat = np.repeat(t_naics4[:, np.newaxis], n_unions, axis=1)
            u4_mat = np.repeat(u_naics4[np.newaxis, :], n_targets, axis=0)
            t2_mat = np.repeat(t_naics2[:, np.newaxis], n_unions, axis=1)
            u2_mat = np.repeat(u_naics2[np.newaxis, :], n_targets, axis=0)

            d = np.ones((n_targets, n_unions), dtype=np.float64)
            d[t4_mat == u4_mat] = 0.0
            same2 = (t2_mat == u2_mat) & (t4_mat != u4_mat)
            d[same2] = 0.3

            # Check for valid (non-None/nan) NAICS
            t_valid = ~pd.isna(target_df['naics_4'].values)
            u_valid = ~pd.isna(union_df['naics_4'].values)
            valid_mask = np.outer(t_valid, u_valid)

            dist_sum += d * w * valid_mask
            weight_sum += w * valid_mask
            feature_dists[feat] = d

        elif feat in CATEGORICAL_FEATURES:
            t_cat = t_vals.astype(str)
            u_cat = u_vals.astype(str)

            t_mat = np.repeat(t_cat[:, np.newaxis], n_unions, axis=1)
            u_mat = np.repeat(u_cat[np.newaxis, :], n_targets, axis=0)

            d = (t_mat != u_mat).astype(np.float64)

            # Handle NULLs (represented as 'None' or 'nan')
            t_null = pd.isna(t_vals) | (t_cat == 'None') | (t_cat == 'nan')
            u_null = pd.isna(u_vals) | (u_cat == 'None') | (u_cat == 'nan')
            valid_mask = np.outer(~t_null, ~u_null)

            dist_sum += d * w * valid_mask
            weight_sum += w * valid_mask
            feature_dists[feat] = d

        elif feat in NUMERIC_FEATURES:
            t_num = pd.to_numeric(t_vals, errors='coerce')
            u_num = pd.to_numeric(u_vals, errors='coerce')

            t_mat = np.repeat(t_num[:, np.newaxis], n_unions, axis=1)
            u_mat = np.repeat(u_num[np.newaxis, :], n_targets, axis=0)

            d = np.abs(t_mat - u_mat)
            # Clamp to [0,1] since min-max normalized
            d = np.clip(d, 0, 1)

            t_valid = ~np.isnan(t_num)
            u_valid = ~np.isnan(u_num)
            valid_mask = np.outer(t_valid, u_valid)

            dist_sum += np.where(valid_mask, d * w, 0)
            weight_sum += w * valid_mask
            feature_dists[feat] = d

        elif feat == OCCUPATION_FEATURE:
            # Occupation overlap distance: 1 - overlap_score
            # Uses pre-computed industry_occupation_overlap table
            if overlap_map and naics_bls_map:
                t_naics = target_df['naics_4'].values.astype(str)
                u_naics = union_df['naics_4'].values.astype(str)
                d = np.ones((n_targets, n_unions), dtype=np.float64)
                valid_mask = np.ones((n_targets, n_unions), dtype=bool)

                for i in range(n_targets):
                    if t_naics[i] in ('None', 'nan', ''):
                        valid_mask[i, :] = False
                        continue
                    for j in range(n_unions):
                        if u_naics[j] in ('None', 'nan', ''):
                            valid_mask[i, j] = False
                            continue
                        overlap = get_occupation_overlap(t_naics[i], u_naics[j], overlap_map, naics_bls_map)
                        if overlap is not None:
                            d[i, j] = 1.0 - overlap
                        else:
                            valid_mask[i, j] = False

                dist_sum += np.where(valid_mask, d * w, 0)
                weight_sum += w * valid_mask
                feature_dists[feat] = d
            else:
                # No overlap data - skip this feature
                feature_dists[feat] = np.ones((n_targets, n_unions), dtype=np.float64) * np.nan
                continue

        elif feat in BINARY_FEATURES:
            t_bin = pd.to_numeric(t_vals, errors='coerce').astype(float)
            u_bin = pd.to_numeric(u_vals, errors='coerce').astype(float)

            t_mat = np.repeat(t_bin[:, np.newaxis], n_unions, axis=1)
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

    # Get top-5 nearest (lowest distance) for each target
    top5_indices = np.argpartition(gower, 5, axis=1)[:, :5]
    # Sort within the top 5
    top5_distances = np.zeros((n_targets, 5))
    top5_breakdowns = []

    for i in range(n_targets):
        idx = top5_indices[i]
        dists = gower[i, idx]
        sort_order = np.argsort(dists)
        top5_indices[i] = idx[sort_order]
        top5_distances[i] = dists[sort_order]

        # Build feature breakdown for this target's top-5
        breakdowns = []
        for j_rank in range(5):
            j = top5_indices[i, j_rank]
            bd = {}
            for feat in all_features:
                fd = feature_dists[feat]
                val = fd[i, j]
                bd[feat] = round(float(val), 4) if not np.isnan(val) else None
            breakdowns.append(bd)
        top5_breakdowns.append(breakdowns)

    return top5_indices, top5_distances, top5_breakdowns


def main():
    parser = argparse.ArgumentParser(description='Compute Gower similarity for employer comparables')
    parser.add_argument('--dry-run', action='store_true', help='Process first chunk only')
    parser.add_argument('--chunk-size', type=int, default=2500, help='Rows per chunk (default 2500)')
    parser.add_argument('--refresh-view', action='store_true', help='Only refresh materialized view')
    parser.add_argument('--recreate-view', action='store_true', help='Force DROP + CREATE view (needed after schema change)')
    parser.add_argument('--skip-view', action='store_true', help='Skip view creation/refresh')
    parser.add_argument('--occ-weight', type=float, default=1.5, help='Occupation overlap feature weight (default 1.5)')
    args = parser.parse_args()

    # Apply occupation weight from CLI
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
    print("PHASE 3: EMPLOYER SIMILARITY ENGINE (GOWER DISTANCE)")
    print("=" * 70)

    # ============================================================
    # Step 1: Materialized view
    # ============================================================
    if not args.skip_view:
        print("\n=== Step 1: Materialized view ===")
        create_or_refresh_view(conn, force_recreate=getattr(args, 'recreate_view', False))
        if args.refresh_view:
            print("View refreshed. Exiting (--refresh-view mode).")
            conn.close()
            return

    # ============================================================
    # Step 2: Create table
    # ============================================================
    print("\n=== Step 2: Ensure table schema ===")
    create_table(conn)

    # ============================================================
    # Step 3: BEFORE snapshot
    # ============================================================
    print("\n=== Step 3: BEFORE snapshot ===")
    cur.execute("""
        SELECT COUNT(*) FROM employer_comparables
    """)
    before_count = cur.fetchone()[0]
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE similarity_score IS NOT NULL) AS has_score,
            AVG(similarity_score) FILTER (WHERE similarity_score IS NOT NULL) AS avg_score
        FROM mergent_employers
        WHERE has_union IS NOT TRUE
    """)
    row = cur.fetchone()
    print(f"  employer_comparables rows: {before_count:,}")
    print(f"  Employers with similarity_score: {row[0]:,}  avg: {row[1] or 0:.4f}")

    # ============================================================
    # Step 4: Load data
    # ============================================================
    print("\n=== Step 4: Loading feature data ===")
    df = pd.read_sql("SELECT * FROM mv_employer_features", conn)
    # Deduplicate (BLS join can produce multiple rows per employer)
    df = df.drop_duplicates(subset=['employer_id'], keep='first')
    print(f"  Total rows: {len(df):,}")

    union_df = df[df['is_union'] == 1].copy().reset_index(drop=True)
    target_df = df[df['is_union'] == 0].copy().reset_index(drop=True)
    print(f"  Union references: {len(union_df):,}")
    print(f"  Non-union targets: {len(target_df):,}")

    if len(union_df) == 0:
        print("ERROR: No union references found. Aborting.")
        conn.close()
        return

    # ============================================================
    # Step 4b: Load occupation overlap data (Phase 5.4c)
    # ============================================================
    print("\n=== Step 4b: Loading occupation overlap ===")
    overlap_map = load_occupation_overlap(conn)
    naics_bls_map = load_naics_bls_mapping(conn)
    print(f"  Overlap pairs: {len(overlap_map):,}")
    print(f"  NAICS->BLS mappings: {len(naics_bls_map):,}")
    if not overlap_map:
        print("  WARNING: No occupation overlap data. Skipping occupation_overlap feature.")

    # ============================================================
    # Step 5: Compute Gower distances with NAICS-2 blocking
    # ============================================================
    # With 4.5M master_employers, pairwise is infeasible. We use NAICS-2
    # blocking: each target is compared only to union refs in the same
    # NAICS-2 sector. This reduces comparisons from ~600B to ~50M.
    print(f"\n=== Step 5: Computing Gower distances (NAICS-2 blocked, chunk_size={args.chunk_size}) ===")

    # Truncate existing data
    cur.execute("TRUNCATE employer_comparables")
    conn.commit()
    print("  Truncated employer_comparables")

    # Group union refs by NAICS-2 for blocking
    naics2_groups = union_df.groupby('naics_2')
    naics2_union_counts = {k: len(v) for k, v in naics2_groups}
    print(f"  NAICS-2 blocks with union refs: {len(naics2_union_counts)}")
    print(f"  Union refs per block: min={min(naics2_union_counts.values()):,}, "
          f"max={max(naics2_union_counts.values()):,}, "
          f"median={sorted(naics2_union_counts.values())[len(naics2_union_counts)//2]:,}")

    chunk_size = args.chunk_size
    total_inserted = 0
    total_targets_processed = 0
    start_time = time.time()

    # Process targets by NAICS-2 block
    target_naics2_groups = target_df.groupby('naics_2')
    block_names = sorted(set(target_df['naics_2'].dropna().unique()))

    for block_idx, naics_2 in enumerate(block_names):
        block_targets = target_naics2_groups.get_group(naics_2).reset_index(drop=True)

        # Get union refs in same NAICS-2
        if naics_2 in naics2_union_counts:
            block_union = naics2_groups.get_group(naics_2).reset_index(drop=True)
        else:
            # No union refs in this NAICS-2 — skip (these targets won't get comparables)
            total_targets_processed += len(block_targets)
            continue

        if len(block_union) < 3:
            # Too few union refs for meaningful comparison — skip
            total_targets_processed += len(block_targets)
            continue

        # Process this block's targets in chunks
        n_chunks = (len(block_targets) + chunk_size - 1) // chunk_size
        for chunk_idx in range(n_chunks):
            chunk_start = chunk_idx * chunk_size
            chunk_end = min(chunk_start + chunk_size, len(block_targets))
            chunk = block_targets.iloc[chunk_start:chunk_end]

            t0 = time.time()
            # Limit top-k to min(5, union refs in block)
            effective_k = min(5, len(block_union))
            top5_idx, top5_dist, top5_bd = compute_gower_chunk(chunk, block_union, overlap_map, naics_bls_map)
            elapsed = time.time() - t0

            # Prepare insert rows (dedup within each target's top-5)
            insert_rows = []
            for i in range(len(chunk)):
                target_eid = int(chunk.iloc[i]['employer_id'])
                seen_comparables = set()
                rank_num = 0
                for rank in range(effective_k):
                    union_row_idx = top5_idx[i, rank]
                    comparable_eid = int(block_union.iloc[union_row_idx]['employer_id'])
                    if comparable_eid in seen_comparables:
                        continue
                    seen_comparables.add(comparable_eid)
                    rank_num += 1
                    distance = round(float(top5_dist[i, rank]), 4)
                    breakdown = json.dumps(top5_bd[i][rank])
                    insert_rows.append((target_eid, comparable_eid, rank_num, distance, breakdown))

            # Deduplicate insert rows (same employer_id+comparable_employer_id)
            seen_pairs = set()
            deduped_rows = []
            for row in insert_rows:
                pair = (row[0], row[1])
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    deduped_rows.append(row)
            insert_rows = deduped_rows

            # Batch insert
            if insert_rows:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO employer_comparables
                       (employer_id, comparable_employer_id, rank, gower_distance, feature_breakdown)
                       VALUES %s
                       ON CONFLICT (employer_id, comparable_employer_id) DO UPDATE
                       SET rank = EXCLUDED.rank,
                           gower_distance = EXCLUDED.gower_distance,
                           feature_breakdown = EXCLUDED.feature_breakdown,
                           computed_at = NOW()""",
                    insert_rows,
                    page_size=1000
                )
                conn.commit()
                total_inserted += len(insert_rows)

            total_targets_processed += len(chunk)

        pct = 100 * total_targets_processed / len(target_df)
        elapsed_total = time.time() - start_time
        eta = elapsed_total / max(total_targets_processed, 1) * (len(target_df) - total_targets_processed)
        print(f"  Block NAICS-{naics_2}: {len(block_targets):,} targets x {len(block_union):,} union "
              f"({pct:.1f}%) inserted={total_inserted:,}  ETA={eta / 60:.1f}min")

        if args.dry_run:
            print("  --dry-run: stopping after first block")
            break

    total_elapsed = time.time() - start_time
    print(f"\n  Total computation time: {total_elapsed / 60:.1f} minutes")
    print(f"  Total rows inserted: {total_inserted:,}")
    print(f"  Total targets processed: {total_targets_processed:,}")

    # ============================================================
    # Step 6: Similarity scores now consumed directly from employer_comparables
    # by build_unified_scorecard.py and build_target_scorecard.py via master_id
    # ============================================================
    print("\n=== Step 6: Similarity data in employer_comparables (master_id based) ===")
    cur.execute("""
        SELECT COUNT(DISTINCT employer_id) FROM employer_comparables
    """)
    distinct_employers = cur.fetchone()[0]
    print(f"  {distinct_employers:,} employers have comparables")

    # ============================================================
    # Step 7: AFTER snapshot + verification
    # ============================================================
    print("\n=== Step 7: AFTER snapshot ===")
    cur.execute("SELECT COUNT(*) FROM employer_comparables")
    after_count = cur.fetchone()[0]
    print(f"  employer_comparables rows: {after_count:,}")

    cur.execute("""
        SELECT
            COUNT(*) AS total,
            AVG(gower_distance) AS avg_dist,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gower_distance) AS median_dist,
            PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY gower_distance) AS p5,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY gower_distance) AS p95,
            MIN(gower_distance) AS min_dist,
            MAX(gower_distance) AS max_dist
        FROM employer_comparables
    """)
    stats = cur.fetchone()
    print(f"\n  Distance distribution:")
    print(f"    Count:  {stats[0]:,}")
    print(f"    Mean:   {float(stats[1]):.4f}")
    print(f"    Median: {float(stats[2]):.4f}")
    print(f"    P5:     {float(stats[3]):.4f}")
    print(f"    P95:    {float(stats[4]):.4f}")
    print(f"    Min:    {float(stats[5]):.4f}")
    print(f"    Max:    {float(stats[6]):.4f}")

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE similarity_score IS NOT NULL) AS has_score,
            AVG(similarity_score) FILTER (WHERE similarity_score IS NOT NULL) AS avg_sim,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY similarity_score)
                FILTER (WHERE similarity_score IS NOT NULL) AS median_sim,
            MIN(similarity_score) FILTER (WHERE similarity_score IS NOT NULL) AS min_sim,
            MAX(similarity_score) FILTER (WHERE similarity_score IS NOT NULL) AS max_sim
        FROM mergent_employers
        WHERE has_union IS NOT TRUE
    """)
    sim_stats = cur.fetchone()
    print(f"\n  Similarity score distribution (non-union employers):")
    print(f"    Count:  {sim_stats[0]:,}")
    print(f"    Mean:   {float(sim_stats[1]):.4f}")
    print(f"    Median: {float(sim_stats[2]):.4f}")
    print(f"    Min:    {float(sim_stats[3]):.4f}")
    print(f"    Max:    {float(sim_stats[4]):.4f}")

    # Top 10 most similar non-union employers
    cur.execute("""
        SELECT m.id, m.company_name, m.state, m.naics_primary, m.similarity_score
        FROM mergent_employers m
        WHERE m.has_union IS NOT TRUE AND m.similarity_score IS NOT NULL
        ORDER BY m.similarity_score DESC
        LIMIT 10
    """)
    print(f"\n  Top 10 most similar non-union employers:")
    for row in cur.fetchall():
        print(f"    {row[4]:.4f}  {row[1][:50]:50s}  {row[2]}  NAICS={row[3]}")

    # Top 10 least similar
    cur.execute("""
        SELECT m.id, m.company_name, m.state, m.naics_primary, m.similarity_score
        FROM mergent_employers m
        WHERE m.has_union IS NOT TRUE AND m.similarity_score IS NOT NULL
        ORDER BY m.similarity_score ASC
        LIMIT 10
    """)
    print(f"\n  Top 10 least similar non-union employers:")
    for row in cur.fetchall():
        print(f"    {row[4]:.4f}  {row[1][:50]:50s}  {row[2]}  NAICS={row[3]}")

    # NAICS sector breakdown
    cur.execute("""
        SELECT LEFT(m.naics_primary, 2) AS sector,
               COUNT(*) AS cnt,
               AVG(m.similarity_score) AS avg_sim,
               MIN(m.similarity_score) AS min_sim,
               MAX(m.similarity_score) AS max_sim
        FROM mergent_employers m
        WHERE m.has_union IS NOT TRUE AND m.similarity_score IS NOT NULL
        GROUP BY LEFT(m.naics_primary, 2)
        ORDER BY avg_sim DESC
    """)
    print(f"\n  Similarity by NAICS 2-digit sector:")
    print(f"    {'Sector':8s} {'Count':>8s} {'Avg':>8s} {'Min':>8s} {'Max':>8s}")
    for row in cur.fetchall():
        print(f"    {row[0]:8s} {row[1]:>8,} {float(row[2]):.4f} {float(row[3]):.4f} {float(row[4]):.4f}")



if __name__ == '__main__':
    main()
