"""
Splink probabilistic matching pipeline.

Matches employer records across data sources using Splink 4.x with DuckDB backend.
Only processes records that the deterministic pipeline failed to match.

Usage:
    py scripts/matching/splink_pipeline.py mergent_to_f7
    py scripts/matching/splink_pipeline.py gleif_to_f7
    py scripts/matching/splink_pipeline.py --all
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

from splink import Linker, DuckDBAPI

# Add parent for config imports
sys.path.insert(0, str(Path(__file__).parent))
from splink_config import (
    SCENARIOS,
    THRESHOLD_AUTO_ACCEPT,
    THRESHOLD_REVIEW,
)

DB_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def create_results_table(conn):
    """Create splink_match_results table if not exists."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS splink_match_results (
            id SERIAL PRIMARY KEY,
            scenario TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT,
            target_id TEXT NOT NULL,
            target_name TEXT,
            match_probability FLOAT NOT NULL,
            match_weight FLOAT,
            -- Per-column comparison levels
            name_comparison_level INTEGER,
            state_comparison_level INTEGER,
            city_comparison_level INTEGER,
            zip_comparison_level INTEGER,
            naics_comparison_level INTEGER,
            address_comparison_level INTEGER,
            -- Review status
            review_status TEXT DEFAULT 'pending',
            -- auto_accept (>=0.85), needs_review (0.70-0.85), rejected (<0.70)
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_smr_scenario ON splink_match_results(scenario)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_smr_source ON splink_match_results(source_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_smr_target ON splink_match_results(target_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_smr_prob ON splink_match_results(match_probability DESC)
    """)
    conn.commit()
    print("  splink_match_results table ready")


def load_self_dedup_data(conn, scenario_name):
    """Load F7 employer records for self-deduplication (single DataFrame)."""
    cfg = SCENARIOS[scenario_name]
    col_map = cfg["columns"]

    select_parts = ", ".join(f"{v} as {k}" for k, v in col_map.items())
    query = f"""
        SELECT {select_parts}
        FROM {cfg['source_table']}
        WHERE {col_map['name_normalized']} IS NOT NULL
          AND LENGTH({col_map['name_normalized']}) >= 3
    """

    print(f"  Loading {cfg['source_table']} for self-dedup...")
    df = pd.read_sql(query, conn)
    print(f"    {len(df):,} records loaded")

    # Ensure string ID
    df['id'] = df['id'].astype(str)

    # Clean NaN -> empty string for string columns
    str_cols = ['name_normalized', 'state', 'city', 'zip', 'naics', 'street_address', 'original_name']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna('')

    # Uppercase state
    if 'state' in df.columns:
        df['state'] = df['state'].str.upper()

    return df


def load_unmatched_data(conn, scenario_name):
    """Load unmatched records from source and target tables into DataFrames."""
    cfg = SCENARIOS[scenario_name]
    cur = conn.cursor()

    # Build source query - only records NOT in crosswalk
    source_cols = cfg["source_columns"]
    source_select = ", ".join(
        f"{v} as {k}" for k, v in source_cols.items()
    )
    source_query = f"""
        SELECT {source_select}
        FROM {cfg['source_table']} s
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.{cfg['crosswalk_source_col']} = s.{cfg['source_id']}
        )
        AND {cfg['source_columns']['name_normalized']} IS NOT NULL
        AND LENGTH({cfg['source_columns']['name_normalized']}) >= 3
    """

    # Build target query - only records NOT in crosswalk
    target_cols = cfg["target_columns"]
    target_select = ", ".join(
        f"{v} as {k}" for k, v in target_cols.items()
    )
    target_query = f"""
        SELECT {target_select}
        FROM {cfg['target_table']} t
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.{cfg['crosswalk_target_col']} = t.{cfg['target_id']}
        )
        AND {cfg['target_columns']['name_normalized']} IS NOT NULL
        AND LENGTH({cfg['target_columns']['name_normalized']}) >= 3
    """

    print(f"  Loading source ({cfg['source_table']})...")
    df_source = pd.read_sql(source_query, conn)
    print(f"    {len(df_source):,} unmatched source records")

    print(f"  Loading target ({cfg['target_table']})...")
    df_target = pd.read_sql(target_query, conn)
    print(f"    {len(df_target):,} unmatched target records")

    # Ensure string types for ID columns (Splink needs consistent types)
    df_source['id'] = df_source['id'].astype(str)
    df_target['id'] = df_target['id'].astype(str)

    # Clean NaN -> None for string columns
    str_cols = ['name_normalized', 'state', 'city', 'zip', 'naics', 'street_address', 'original_name']
    for col in str_cols:
        if col in df_source.columns:
            df_source[col] = df_source[col].fillna('')
        if col in df_target.columns:
            df_target[col] = df_target[col].fillna('')

    # Uppercase state for consistent matching
    if 'state' in df_source.columns:
        df_source['state'] = df_source['state'].str.upper()
    if 'state' in df_target.columns:
        df_target['state'] = df_target['state'].str.upper()

    return df_source, df_target


def run_splink_dedup(df, scenario_name):
    """Run Splink self-deduplication on a single DataFrame."""
    cfg = SCENARIOS[scenario_name]
    settings = cfg["settings"]
    em_blocking = cfg["em_blocking"]

    print(f"\n  Initializing Splink Linker (dedupe_only, DuckDB backend)...")
    db_api = DuckDBAPI()
    linker = Linker(
        [df],
        settings,
        db_api=db_api,
    )

    # Step 1: Estimate u probabilities
    print("  Estimating u probabilities (random sampling)...")
    start = time.time()
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
    print(f"    Done in {time.time()-start:.1f}s")

    # Step 2: EM training
    for i, br in enumerate(em_blocking):
        print(f"  EM training pass {i+1}/{len(em_blocking)}...")
        start = time.time()
        linker.training.estimate_parameters_using_expectation_maximisation(
            br, fix_u_probabilities=True
        )
        print(f"    Done in {time.time()-start:.1f}s")

    # Step 3: Predict
    print(f"\n  Predicting duplicate pairs...")
    start = time.time()
    results = linker.inference.predict(threshold_match_probability=THRESHOLD_REVIEW)
    df_results = results.as_pandas_dataframe()
    print(f"    {len(df_results):,} candidate pairs above {THRESHOLD_REVIEW} threshold in {time.time()-start:.1f}s")

    return df_results, linker


def run_splink_matching(df_source, df_target, scenario_name):
    """Run Splink probabilistic matching."""
    cfg = SCENARIOS[scenario_name]
    settings = cfg["settings"]
    em_blocking = cfg["em_blocking"]

    print(f"\n  Initializing Splink Linker (DuckDB backend)...")
    db_api = DuckDBAPI()
    linker = Linker(
        [df_source, df_target],
        settings,
        db_api=db_api,
    )

    # Step 1: Estimate u probabilities using random sampling
    print("  Estimating u probabilities (random sampling)...")
    start = time.time()
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
    print(f"    Done in {time.time()-start:.1f}s")

    # Step 2: Estimate m probabilities using EM with blocking rules
    for i, br in enumerate(em_blocking):
        print(f"  EM training pass {i+1}/{len(em_blocking)}...")
        start = time.time()
        linker.training.estimate_parameters_using_expectation_maximisation(
            br, fix_u_probabilities=True
        )
        print(f"    Done in {time.time()-start:.1f}s")

    # Step 3: Predict match probabilities
    print(f"\n  Predicting matches...")
    start = time.time()
    results = linker.inference.predict(threshold_match_probability=THRESHOLD_REVIEW)
    df_results = results.as_pandas_dataframe()
    print(f"    {len(df_results):,} candidate pairs above {THRESHOLD_REVIEW} threshold in {time.time()-start:.1f}s")

    return df_results, linker


def save_results(conn, df_results, scenario_name):
    """Save Splink results to database."""
    if len(df_results) == 0:
        print("  No results to save.")
        return 0, 0

    cfg = SCENARIOS[scenario_name]
    cur = conn.cursor()

    # Delete previous results for this scenario
    cur.execute("DELETE FROM splink_match_results WHERE scenario = %s", (scenario_name,))
    old_count = cur.rowcount
    if old_count > 0:
        print(f"  Cleared {old_count:,} previous results")

    # Map Splink output columns to our schema
    # Splink uses "id_l" and "id_r" for left/right record IDs
    inserted = 0
    auto_accepted = 0
    needs_review = 0

    for _, row in df_results.iterrows():
        prob = row.get('match_probability', 0)
        weight = row.get('match_weight', None)

        if prob >= THRESHOLD_AUTO_ACCEPT:
            status = 'auto_accept'
            auto_accepted += 1
        elif prob >= THRESHOLD_REVIEW:
            status = 'needs_review'
            needs_review += 1
        else:
            continue  # Skip below review threshold

        # Extract comparison levels (column names vary by scenario)
        name_level = _get_comparison_level(row, 'name_normalized')
        state_level = _get_comparison_level(row, 'state')
        city_level = _get_comparison_level(row, 'city')
        zip_level = _get_comparison_level(row, 'zip')
        naics_level = _get_comparison_level(row, 'naics')
        addr_level = _get_comparison_level(row, 'street_address')

        # Get names from the result
        source_name = row.get('original_name_l', row.get('name_normalized_l', ''))
        target_name = row.get('original_name_r', row.get('name_normalized_r', ''))

        cur.execute("""
            INSERT INTO splink_match_results
                (scenario, source_id, source_name, target_id, target_name,
                 match_probability, match_weight,
                 name_comparison_level, state_comparison_level,
                 city_comparison_level, zip_comparison_level,
                 naics_comparison_level, address_comparison_level,
                 review_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            scenario_name,
            str(row.get('id_l', '')),
            str(source_name) if source_name else None,
            str(row.get('id_r', '')),
            str(target_name) if target_name else None,
            float(prob),
            float(weight) if weight is not None else None,
            name_level, state_level, city_level, zip_level, naics_level, addr_level,
            status,
        ))
        inserted += 1

    conn.commit()
    print(f"\n  Saved {inserted:,} results:")
    print(f"    Auto-accept (>={THRESHOLD_AUTO_ACCEPT}): {auto_accepted:,}")
    print(f"    Needs review ({THRESHOLD_REVIEW}-{THRESHOLD_AUTO_ACCEPT}): {needs_review:,}")

    return auto_accepted, needs_review


def _get_comparison_level(row, col_name):
    """Extract comparison level from Splink result row."""
    # Splink names gamma columns as "gamma_{column_name}"
    gamma_col = f"gamma_{col_name}"
    if gamma_col in row.index:
        val = row[gamma_col]
        return int(val) if pd.notna(val) else None
    return None


def print_sample_matches(conn, scenario_name, limit=15):
    """Print sample high-probability matches for review."""
    cur = conn.cursor()
    cur.execute("""
        SELECT source_name, target_name, match_probability, review_status,
               name_comparison_level, state_comparison_level, city_comparison_level
        FROM splink_match_results
        WHERE scenario = %s
        ORDER BY match_probability DESC
        LIMIT %s
    """, (scenario_name, limit))

    rows = cur.fetchall()
    if not rows:
        print("  No matches to display.")
        return

    print(f"\n  Top {len(rows)} matches:")
    print(f"  {'Source':<40} {'Target':<40} {'Prob':>6} {'Status':<12} {'Name':>4} {'St':>2} {'Cty':>3}")
    print(f"  {'-'*40} {'-'*40} {'-'*6} {'-'*12} {'-'*4} {'-'*2} {'-'*3}")
    for row in rows:
        src = (row[0] or '')[:40]
        tgt = (row[1] or '')[:40]
        prob = row[2]
        status = row[3]
        name_lvl = row[4] if row[4] is not None else '-'
        state_lvl = row[5] if row[5] is not None else '-'
        city_lvl = row[6] if row[6] is not None else '-'
        print(f"  {src:<40} {tgt:<40} {prob:>6.3f} {status:<12} {name_lvl:>4} {state_lvl:>2} {city_lvl:>3}")


def run_scenario(scenario_name):
    """Run a complete Splink matching scenario."""
    print(f"\n{'='*70}")
    print(f"SPLINK MATCHING: {scenario_name}")
    print(f"{'='*70}")

    overall_start = time.time()
    cfg = SCENARIOS[scenario_name]
    is_dedup = cfg.get("link_type") == "dedupe_only"

    conn = get_conn()
    create_results_table(conn)

    if is_dedup:
        # Self-dedup: single DataFrame
        print(f"\n--- Loading data (self-dedup) ---")
        df = load_self_dedup_data(conn, scenario_name)

        if len(df) == 0:
            print("  No records to process. Skipping.")
            conn.close()
            return

        print(f"\n--- Running Splink (dedupe_only) ---")
        df_results, linker = run_splink_dedup(df, scenario_name)

        record_count = len(df)
    else:
        # Cross-source link: two DataFrames
        print(f"\n--- Loading data ---")
        df_source, df_target = load_unmatched_data(conn, scenario_name)

        if len(df_source) == 0 or len(df_target) == 0:
            print("  No unmatched records to process. Skipping.")
            conn.close()
            return

        print(f"\n--- Running Splink ---")
        df_results, linker = run_splink_matching(df_source, df_target, scenario_name)

        record_count = len(df_source) + len(df_target)

    if len(df_results) == 0:
        print("  No matches found above threshold.")
        conn.close()
        return

    # Save results
    print(f"\n--- Saving results ---")
    auto_accepted, needs_review = save_results(conn, df_results, scenario_name)

    # Show samples
    print_sample_matches(conn, scenario_name)

    # Summary stats
    elapsed = time.time() - overall_start
    print(f"\n--- Summary ---")
    print(f"  Scenario: {scenario_name}")
    if is_dedup:
        print(f"  Records: {record_count:,} (self-dedup)")
    else:
        print(f"  Source records: {len(df_source):,}")
        print(f"  Target records: {len(df_target):,}")
    print(f"  Matches found: {auto_accepted + needs_review:,}")
    print(f"    Auto-accept: {auto_accepted:,}")
    print(f"    Needs review: {needs_review:,}")
    print(f"  Total time: {elapsed:.1f}s")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Splink probabilistic matching pipeline")
    parser.add_argument("scenario", nargs="?", help="Scenario name (e.g., mergent_to_f7)")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for name in SCENARIOS:
            cfg = SCENARIOS[name]
            print(f"  {name}: {cfg['source_table']} -> {cfg['target_table']}")
        return

    if args.all:
        for name in SCENARIOS:
            run_scenario(name)
        return

    if not args.scenario:
        parser.print_help()
        return

    if args.scenario not in SCENARIOS:
        print(f"Unknown scenario: {args.scenario}")
        print(f"Available: {', '.join(SCENARIOS.keys())}")
        return

    run_scenario(args.scenario)


if __name__ == "__main__":
    main()
