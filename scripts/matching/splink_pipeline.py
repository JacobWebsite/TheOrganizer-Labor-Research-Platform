"""
Splink probabilistic matching pipeline.

Matches employer records across data sources using Splink 4.x with DuckDB backend.
Writes output to both splink_match_results and unified_match_log.

Usage:
    py scripts/matching/splink_pipeline.py --scenario mergent_to_f7
    py scripts/matching/splink_pipeline.py mergent_to_f7
    py scripts/matching/splink_pipeline.py --all
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
from psycopg2.extras import Json, execute_batch
from splink import DuckDBAPI, Linker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from db_config import get_connection
from splink_config import SCENARIOS, THRESHOLD_AUTO_ACCEPT, THRESHOLD_REVIEW


def create_results_table(conn):
    """Create splink_match_results table if not exists."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS splink_match_results (
                id SERIAL PRIMARY KEY,
                scenario TEXT NOT NULL,
                source_id TEXT NOT NULL,
                source_name TEXT,
                target_id TEXT NOT NULL,
                target_name TEXT,
                match_probability FLOAT NOT NULL,
                match_weight FLOAT,
                name_comparison_level INTEGER,
                state_comparison_level INTEGER,
                city_comparison_level INTEGER,
                zip_comparison_level INTEGER,
                naics_comparison_level INTEGER,
                address_comparison_level INTEGER,
                review_status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_smr_scenario ON splink_match_results(scenario)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_smr_source ON splink_match_results(source_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_smr_target ON splink_match_results(target_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_smr_prob ON splink_match_results(match_probability DESC)"
        )
    conn.commit()
    print("  splink_match_results table ready")


def _infer_source_system(scenario_name, cfg):
    if cfg.get("source_system"):
        return cfg["source_system"]
    if scenario_name == "f7_self_dedup":
        return "f7"
    if scenario_name.endswith("_to_f7"):
        return scenario_name.replace("_to_f7", "")
    return scenario_name.split("_")[0]


def _classification(prob):
    if prob >= THRESHOLD_AUTO_ACCEPT:
        return "auto_accept", "HIGH", "active"
    if prob >= THRESHOLD_REVIEW:
        return "needs_review", "MEDIUM", "active"
    return "rejected", "LOW", "rejected"


def _get_comparison_level(row, col_name):
    gamma_col = f"gamma_{col_name}"
    if gamma_col in row.index:
        val = row[gamma_col]
        return int(val) if pd.notna(val) else None
    return None


def _extract_comparison_levels(row):
    levels = {}
    for col in row.index:
        if not col.startswith("gamma_"):
            continue
        val = row[col]
        if pd.isna(val):
            continue
        key = col.replace("gamma_", "")
        if key == "name_normalized":
            key = "name"
        levels[key] = int(val)
    return levels


def _register_run(conn, run_id, scenario_name, source_system):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO match_runs (run_id, scenario, started_at, source_system, method_type)
            VALUES (%s, %s, NOW(), %s, %s)
            ON CONFLICT (run_id) DO NOTHING
            """,
            [run_id, scenario_name, source_system, "probabilistic"],
        )
    conn.commit()


def _finalize_run(conn, run_id, total_source, high_count, medium_count, low_count):
    total_active = high_count + medium_count
    match_rate = round(total_active / max(total_source, 1) * 100, 2)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE match_runs
            SET completed_at = NOW(),
                total_source = %s,
                total_matched = %s,
                match_rate = %s,
                high_count = %s,
                medium_count = %s,
                low_count = %s
            WHERE run_id = %s
            """,
            [total_source, total_active, match_rate, high_count, medium_count, low_count, run_id],
        )
    conn.commit()


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

    df["id"] = df["id"].astype(str)
    str_cols = [
        "name_normalized",
        "state",
        "city",
        "zip",
        "naics",
        "street_address",
        "original_name",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("")

    if "state" in df.columns:
        df["state"] = df["state"].str.upper()

    return df


def load_unmatched_data(conn, scenario_name):
    """Load unmatched records from source and target tables into DataFrames."""
    cfg = SCENARIOS[scenario_name]

    source_cols = cfg["source_columns"]
    source_select = ", ".join(f"{v} as {k}" for k, v in source_cols.items())
    source_filters = []
    if cfg.get("source_unmatched_condition"):
        source_filters.append(cfg["source_unmatched_condition"].strip())
    elif cfg.get("crosswalk_source_col"):
        source_filters.append(
            f"""
            NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c
                WHERE c.{cfg['crosswalk_source_col']} = s.{cfg['source_id']}
            )
            """.strip()
        )
    source_filters.append(f"{cfg['source_columns']['name_normalized']} IS NOT NULL")
    source_filters.append(f"LENGTH({cfg['source_columns']['name_normalized']}) >= 3")
    source_where = " AND ".join(f"({f})" for f in source_filters)
    source_query = f"""
        SELECT {source_select}
        FROM {cfg['source_table']} s
        WHERE {source_where}
    """

    target_cols = cfg["target_columns"]
    target_select = ", ".join(f"{v} as {k}" for k, v in target_cols.items())
    target_filters = []
    if cfg.get("target_unmatched_condition"):
        target_filters.append(cfg["target_unmatched_condition"].strip())
    elif cfg.get("crosswalk_target_col"):
        target_filters.append(
            f"""
            NOT EXISTS (
                SELECT 1 FROM corporate_identifier_crosswalk c
                WHERE c.{cfg['crosswalk_target_col']} = t.{cfg['target_id']}
            )
            """.strip()
        )
    target_filters.append(f"{cfg['target_columns']['name_normalized']} IS NOT NULL")
    target_filters.append(f"LENGTH({cfg['target_columns']['name_normalized']}) >= 3")
    target_where = " AND ".join(f"({f})" for f in target_filters)
    target_query = f"""
        SELECT {target_select}
        FROM {cfg['target_table']} t
        WHERE {target_where}
    """

    print(f"  Loading source ({cfg['source_table']})...")
    df_source = pd.read_sql(source_query, conn)
    print(f"    {len(df_source):,} unmatched source records")

    print(f"  Loading target ({cfg['target_table']})...")
    df_target = pd.read_sql(target_query, conn)
    print(f"    {len(df_target):,} unmatched target records")

    df_source["id"] = df_source["id"].astype(str)
    df_target["id"] = df_target["id"].astype(str)

    str_cols = [
        "name_normalized",
        "state",
        "city",
        "zip",
        "naics",
        "street_address",
        "original_name",
    ]
    for col in str_cols:
        if col in df_source.columns:
            df_source[col] = df_source[col].fillna("")
        if col in df_target.columns:
            df_target[col] = df_target[col].fillna("")

    if "state" in df_source.columns:
        df_source["state"] = df_source["state"].str.upper()
    if "state" in df_target.columns:
        df_target["state"] = df_target["state"].str.upper()

    return df_source, df_target


def run_splink_dedup(df, scenario_name):
    """Run Splink self-deduplication on a single DataFrame."""
    cfg = SCENARIOS[scenario_name]
    settings = cfg["settings"]
    em_blocking = cfg["em_blocking"]

    print("\n  Initializing Splink Linker (dedupe_only, DuckDB backend)...")
    linker = Linker([df], settings, db_api=DuckDBAPI())

    print("  Estimating u probabilities (random sampling)...")
    start = time.time()
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
    print(f"    Done in {time.time() - start:.1f}s")

    for i, br in enumerate(em_blocking):
        print(f"  EM training pass {i + 1}/{len(em_blocking)}...")
        start = time.time()
        linker.training.estimate_parameters_using_expectation_maximisation(
            br, fix_u_probabilities=True
        )
        print(f"    Done in {time.time() - start:.1f}s")

    print("\n  Predicting duplicate pairs...")
    start = time.time()
    results = linker.inference.predict(threshold_match_probability=THRESHOLD_REVIEW)
    df_results = results.as_pandas_dataframe()
    print(f"    {len(df_results):,} candidate pairs in {time.time() - start:.1f}s")

    return df_results


def run_splink_matching(df_source, df_target, scenario_name):
    """Run Splink probabilistic matching."""
    cfg = SCENARIOS[scenario_name]
    settings = cfg["settings"]
    em_blocking = cfg["em_blocking"]

    print("\n  Initializing Splink Linker (DuckDB backend)...")
    linker = Linker([df_source, df_target], settings, db_api=DuckDBAPI())

    print("  Estimating u probabilities (random sampling)...")
    start = time.time()
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)
    print(f"    Done in {time.time() - start:.1f}s")

    for i, br in enumerate(em_blocking):
        print(f"  EM training pass {i + 1}/{len(em_blocking)}...")
        start = time.time()
        linker.training.estimate_parameters_using_expectation_maximisation(
            br, fix_u_probabilities=True
        )
        print(f"    Done in {time.time() - start:.1f}s")

    print("\n  Predicting matches...")
    start = time.time()
    results = linker.inference.predict(threshold_match_probability=THRESHOLD_REVIEW)
    df_results = results.as_pandas_dataframe()
    print(f"    {len(df_results):,} candidate pairs in {time.time() - start:.1f}s")

    return df_results


def save_results(conn, df_results, scenario_name, run_id, dry_run=False):
    """Save Splink results to splink_match_results and unified_match_log."""
    if len(df_results) == 0:
        print("  No results to save.")
        return 0, 0, 0

    cfg = SCENARIOS[scenario_name]
    source_system = _infer_source_system(scenario_name, cfg)

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    splink_rows = []
    unified_rows = []

    for _, row in df_results.iterrows():
        source_id = str(row.get("id_l", ""))
        target_id = str(row.get("id_r", ""))
        prob = float(row.get("match_probability") or 0.0)
        weight_raw = row.get("match_weight")
        weight = float(weight_raw) if pd.notna(weight_raw) else None

        review_status, confidence_band, status = _classification(prob)
        counts[confidence_band] += 1

        comparison_levels = _extract_comparison_levels(row)
        evidence = {
            "scenario": scenario_name,
            "match_probability": round(prob, 6),
            "match_weight": weight,
            "comparison_levels": comparison_levels,
        }

        source_name = row.get("original_name_l", row.get("name_normalized_l", ""))
        target_name = row.get("original_name_r", row.get("name_normalized_r", ""))

        splink_rows.append(
            (
                scenario_name,
                source_id,
                str(source_name) if source_name else None,
                target_id,
                str(target_name) if target_name else None,
                prob,
                weight,
                _get_comparison_level(row, "name_normalized"),
                _get_comparison_level(row, "state"),
                _get_comparison_level(row, "city"),
                _get_comparison_level(row, "zip"),
                _get_comparison_level(row, "naics"),
                _get_comparison_level(row, "street_address"),
                review_status,
            )
        )
        unified_rows.append(
            (
                run_id,
                source_system,
                source_id,
                "f7",
                target_id,
                "SPLINK_PROBABILISTIC",
                "probabilistic",
                confidence_band,
                prob,
                Json(evidence),
                status,
            )
        )

    if dry_run:
        print(
            f"\n  Dry run classification: HIGH={counts['HIGH']:,}, "
            f"MEDIUM={counts['MEDIUM']:,}, LOW={counts['LOW']:,}"
        )
        return counts["HIGH"], counts["MEDIUM"], counts["LOW"]

    with conn.cursor() as cur:
        cur.execute("DELETE FROM splink_match_results WHERE scenario = %s", (scenario_name,))
        execute_batch(
            cur,
            """
            INSERT INTO splink_match_results
                (scenario, source_id, source_name, target_id, target_name,
                 match_probability, match_weight,
                 name_comparison_level, state_comparison_level,
                 city_comparison_level, zip_comparison_level,
                 naics_comparison_level, address_comparison_level,
                 review_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            splink_rows,
            page_size=1000,
        )
        execute_batch(
            cur,
            """
            INSERT INTO unified_match_log
                (run_id, source_system, source_id, target_system, target_id,
                 match_method, match_tier, confidence_band, confidence_score,
                 evidence, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, source_system, source_id, target_id) DO NOTHING
            """,
            unified_rows,
            page_size=1000,
        )
    conn.commit()

    print(
        f"\n  Saved {len(splink_rows):,} results:"
        f"\n    HIGH (>= {THRESHOLD_AUTO_ACCEPT}): {counts['HIGH']:,}"
        f"\n    MEDIUM ({THRESHOLD_REVIEW}-{THRESHOLD_AUTO_ACCEPT}): {counts['MEDIUM']:,}"
        f"\n    LOW (< {THRESHOLD_REVIEW}): {counts['LOW']:,}"
    )
    return counts["HIGH"], counts["MEDIUM"], counts["LOW"]


def print_sample_matches(conn, scenario_name, limit=15):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_name, target_name, match_probability, review_status,
                   name_comparison_level, state_comparison_level, city_comparison_level
            FROM splink_match_results
            WHERE scenario = %s
            ORDER BY match_probability DESC
            LIMIT %s
            """,
            (scenario_name, limit),
        )
        rows = cur.fetchall()

    if not rows:
        print("  No matches to display.")
        return

    print(f"\n  Top {len(rows)} matches:")
    print(
        f"  {'Source':<40} {'Target':<40} {'Prob':>6} {'Status':<12} {'Name':>4} {'St':>2} {'Cty':>3}"
    )
    print(f"  {'-' * 40} {'-' * 40} {'-' * 6} {'-' * 12} {'-' * 4} {'-' * 2} {'-' * 3}")
    for row in rows:
        src = (row[0] or "")[:40]
        tgt = (row[1] or "")[:40]
        prob = row[2]
        status = row[3]
        name_lvl = row[4] if row[4] is not None else "-"
        state_lvl = row[5] if row[5] is not None else "-"
        city_lvl = row[6] if row[6] is not None else "-"
        print(f"  {src:<40} {tgt:<40} {prob:>6.3f} {status:<12} {name_lvl:>4} {state_lvl:>2} {city_lvl:>3}")


def run_scenario(scenario_name, dry_run=False):
    print(f"\n{'=' * 70}")
    print(f"SPLINK MATCHING: {scenario_name}")
    print(f"{'=' * 70}")

    overall_start = time.time()
    cfg = SCENARIOS[scenario_name]
    source_system = _infer_source_system(scenario_name, cfg)
    run_id = str(uuid.uuid4())
    is_dedup = cfg.get("link_type") == "dedupe_only"
    total_source = 0
    high = medium = low = 0

    conn = get_connection()
    try:
        create_results_table(conn)
        if not dry_run:
            _register_run(conn, run_id, scenario_name, source_system)

        if is_dedup:
            print("\n--- Loading data (self-dedup) ---")
            df = load_self_dedup_data(conn, scenario_name)
            total_source = len(df)
            if len(df) == 0:
                print("  No records to process. Skipping.")
                if not dry_run:
                    _finalize_run(conn, run_id, total_source, high, medium, low)
                return

            print("\n--- Running Splink (dedupe_only) ---")
            df_results = run_splink_dedup(df, scenario_name)
        else:
            print("\n--- Loading data ---")
            df_source, df_target = load_unmatched_data(conn, scenario_name)
            total_source = len(df_source)
            if len(df_source) == 0 or len(df_target) == 0:
                print("  No unmatched records to process. Skipping.")
                if not dry_run:
                    _finalize_run(conn, run_id, total_source, high, medium, low)
                return

            print("\n--- Running Splink ---")
            df_results = run_splink_matching(df_source, df_target, scenario_name)

        print("\n--- Saving results ---")
        high, medium, low = save_results(
            conn, df_results, scenario_name, run_id=run_id, dry_run=dry_run
        )
        if not dry_run:
            _finalize_run(conn, run_id, total_source, high, medium, low)
            print_sample_matches(conn, scenario_name)

        elapsed = time.time() - overall_start
        print("\n--- Summary ---")
        print(f"  Run ID: {run_id}")
        print(f"  Scenario: {scenario_name}")
        if is_dedup:
            print(f"  Records: {total_source:,} (self-dedup)")
        else:
            print(f"  Source records: {len(df_source):,}")
            print(f"  Target records: {len(df_target):,}")
        print(f"  Active matches: {high + medium:,}")
        print(f"    HIGH: {high:,}")
        print(f"    MEDIUM: {medium:,}")
        print(f"    LOW (rejected): {low:,}")
        print(f"  Total time: {elapsed:.1f}s")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Splink probabilistic matching pipeline")
    parser.add_argument("scenario_pos", nargs="?", help="Scenario name (e.g., mergent_to_f7)")
    parser.add_argument("--scenario", help="Scenario name (e.g., mergent_to_f7)")
    parser.add_argument("--all", action="store_true", help="Run all scenarios")
    parser.add_argument("--dry-run", action="store_true", help="Do not write results to database")
    parser.add_argument("--list", action="store_true", help="List available scenarios")
    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for name in SCENARIOS:
            cfg = SCENARIOS[name]
            src = cfg.get("source_table", "n/a")
            tgt = cfg.get("target_table", cfg.get("source_table", "n/a"))
            print(f"  {name}: {src} -> {tgt}")
        return

    if args.all:
        for name in SCENARIOS:
            run_scenario(name, dry_run=args.dry_run)
        return

    scenario_name = args.scenario or args.scenario_pos
    if not scenario_name:
        parser.print_help()
        return

    if scenario_name not in SCENARIOS:
        print(f"Unknown scenario: {scenario_name}")
        print(f"Available: {', '.join(SCENARIOS.keys())}")
        return

    run_scenario(scenario_name, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
