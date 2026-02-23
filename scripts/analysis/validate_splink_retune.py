"""Validate retuned Splink model on a sample of OSHA records.

Runs the Splink tier on 5,000 OSHA records and compares:
1. Match count and rate vs old model
2. Quality of matches by similarity band
3. False positive check on 0.80-0.84 band
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def get_osha_sample(conn, n=5000):
    """Get a sample of OSHA records that are NOT already matched by tiers 1-4."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT e.establishment_id AS source_id,
               e.estab_name AS name_raw,
               e.estab_name_normalized AS name_normalized,
               e.site_state AS state, e.site_city AS city, e.site_zip AS zip,
               e.naics_code AS naics,
               '' AS street_address
        FROM osha_establishments e
        WHERE e.estab_name_normalized IS NOT NULL
          AND e.site_state IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_match_log u
              WHERE u.source_id = e.establishment_id::text
                AND u.source_system = 'osha'
                AND u.status = 'active'
                AND u.match_method IN (
                    'EIN_EXACT', 'NAME_CITY_STATE_EXACT',
                    'NAME_STATE_EXACT', 'NAME_AGGRESSIVE_STATE'
                )
          )
        ORDER BY random()
        LIMIT %s
    """, (n,))
    rows = cur.fetchall()
    cur.close()
    return rows


def get_f7_targets(conn):
    """Get F7 employer records for Splink matching."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT employer_id AS id,
               employer_name AS name_raw,
               name_standard AS name_normalized, state, city, zip, naics,
               street AS street_address
        FROM f7_employers_deduped
        WHERE name_standard IS NOT NULL
          AND state IS NOT NULL
          AND NOT is_historical
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def run_splink_test(source_records, target_records, model_path, min_sim=0.80):
    """Run Splink matching and return results."""
    try:
        import pandas as pd
        from splink import Linker, DuckDBAPI
        from rapidfuzz import fuzz as _rf_fuzz
    except ImportError as e:
        print(f"Missing dependency: {e}")
        return None

    # Build DataFrames
    source_data = []
    for r in source_records:
        source_data.append({
            "id": str(r["source_id"]),
            "name_normalized": r["name_normalized"] or "",
            "state": r["state"] or "",
            "city": r["city"] or "",
            "zip": (r["zip"] or "")[:5],
            "naics": r["naics"] or "",
            "street_address": r["street_address"] or "",
        })

    target_data = []
    for r in target_records:
        target_data.append({
            "id": str(r["id"]),
            "name_normalized": r["name_normalized"] or "",
            "state": r["state"] or "",
            "city": r["city"] or "",
            "zip": (r["zip"] or "")[:5],
            "naics": r["naics"] or "",
            "street_address": r["street_address"] or "",
        })

    df_source = pd.DataFrame(source_data)
    df_target = pd.DataFrame(target_data)

    print(f"  Source records: {len(df_source)}")
    print(f"  Target records: {len(df_target)}")

    linker = Linker(
        [df_source, df_target],
        settings=str(model_path),
        db_api=DuckDBAPI(),
        set_up_basic_logging=False,
    )

    t0 = time.time()
    df_matches = linker.inference.predict(
        threshold_match_probability=0.60
    ).as_pandas_dataframe()
    elapsed = time.time() - t0
    print(f"  Splink predict: {elapsed:.1f}s, raw candidates: {len(df_matches)}")

    if len(df_matches) == 0:
        return pd.DataFrame()

    # Apply name similarity floor
    df_matches["name_sim"] = df_matches.apply(
        lambda r: _rf_fuzz.token_sort_ratio(
            str(r.get("name_normalized_l", "")),
            str(r.get("name_normalized_r", "")),
        ) / 100.0,
        axis=1,
    )
    before_filter = len(df_matches)
    df_matches = df_matches[df_matches["name_sim"] >= min_sim]
    print(f"  After name floor ({min_sim}): {len(df_matches)} (filtered {before_filter - len(df_matches)})")

    # Deduplicate: keep best per source
    df_matches = df_matches.sort_values("match_probability", ascending=False)
    df_matches = df_matches.drop_duplicates(subset=["id_l"], keep="first")
    print(f"  After dedup: {len(df_matches)}")

    return df_matches


def analyze_results(df_matches, label):
    """Print match quality analysis."""
    if df_matches is None or len(df_matches) == 0:
        print(f"\n{label}: No matches found.")
        return

    print(f"\n{'='*80}")
    print(f"{label}: {len(df_matches)} matches")
    print(f"{'='*80}")

    # Sim band distribution
    bands = {
        "0.95+": df_matches[df_matches["name_sim"] >= 0.95],
        "0.90-0.94": df_matches[(df_matches["name_sim"] >= 0.90) & (df_matches["name_sim"] < 0.95)],
        "0.85-0.89": df_matches[(df_matches["name_sim"] >= 0.85) & (df_matches["name_sim"] < 0.90)],
        "0.80-0.84": df_matches[(df_matches["name_sim"] >= 0.80) & (df_matches["name_sim"] < 0.85)],
    }

    print("\nSimilarity Band Distribution:")
    for band_name, band_df in bands.items():
        pct = len(band_df) / len(df_matches) * 100 if len(df_matches) > 0 else 0
        print(f"  {band_name}: {len(band_df):>5} ({pct:5.1f}%)")

    # Match probability distribution
    print(f"\nMatch Probability Stats:")
    print(f"  Mean:   {df_matches['match_probability'].mean():.4f}")
    print(f"  Median: {df_matches['match_probability'].median():.4f}")
    print(f"  Min:    {df_matches['match_probability'].min():.4f}")
    print(f"  Max:    {df_matches['match_probability'].max():.4f}")

    # Sample matches from each band
    print("\nSample Matches:")
    for band_name, band_df in bands.items():
        if len(band_df) == 0:
            continue
        print(f"\n  --- {band_name} ---")
        sample = band_df.sample(min(5, len(band_df)))
        for _, row in sample.iterrows():
            src = row.get("name_normalized_l", "?")[:40]
            tgt = row.get("name_normalized_r", "?")[:40]
            prob = row["match_probability"]
            sim = row["name_sim"]
            st = row.get("state_l", "?")
            print(f"  {src:40s} <-> {tgt:40s}  sim={sim:.3f} prob={prob:.4f} {st}")


def main():
    conn = get_connection()

    print("Loading OSHA sample (5,000 records not matched by tiers 1-4)...")
    osha_sample = get_osha_sample(conn, n=5000)
    print(f"Got {len(osha_sample)} OSHA records")

    print("\nLoading F7 targets (current, non-historical)...")
    f7_targets = get_f7_targets(conn)
    print(f"Got {len(f7_targets)} F7 targets")

    model_dir = os.path.join(os.path.dirname(__file__), "..", "matching", "models")

    # Test retuned model
    retuned_path = os.path.join(model_dir, "adaptive_fuzzy_model.json")
    print(f"\n--- Testing RETUNED model ---")
    retuned_results = run_splink_test(osha_sample, f7_targets, retuned_path, min_sim=0.80)
    analyze_results(retuned_results, "RETUNED MODEL (v2)")

    # Test original model for comparison
    original_path = os.path.join(model_dir, "adaptive_fuzzy_model_v1_original.json")
    if os.path.exists(original_path):
        print(f"\n--- Testing ORIGINAL model ---")
        original_results = run_splink_test(osha_sample, f7_targets, original_path, min_sim=0.80)
        analyze_results(original_results, "ORIGINAL MODEL (v1)")

        # Compare
        if retuned_results is not None and original_results is not None:
            print(f"\n{'='*80}")
            print("COMPARISON")
            print(f"{'='*80}")
            print(f"  Original matches: {len(original_results)}")
            print(f"  Retuned matches:  {len(retuned_results)}")
            if len(original_results) > 0:
                ratio = len(retuned_results) / len(original_results)
                print(f"  Ratio: {ratio:.2f}x")

    conn.close()


if __name__ == "__main__":
    main()
