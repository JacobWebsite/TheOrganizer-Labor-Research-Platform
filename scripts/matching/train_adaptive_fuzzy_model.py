"""
Train and export the adaptive_fuzzy Splink model for deterministic matcher tier 5.

The model is trained on a representative sample of OSHA-to-F7 pairs,
then saved as JSON for fast loading at match-time (no per-batch EM training).

Usage:
    py scripts/matching/train_adaptive_fuzzy_model.py
    py scripts/matching/train_adaptive_fuzzy_model.py --sample-size 50000
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection

MODEL_OUTPUT = Path(__file__).resolve().parent / "models" / "adaptive_fuzzy_model.json"


def load_training_data(conn, sample_size=50000):
    """Load OSHA source records and F7 target records for training."""
    import pandas as pd

    print(f"Loading OSHA training sample ({sample_size:,} records)...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                establishment_id::text AS id,
                LOWER(COALESCE(estab_name, '')) AS name_normalized,
                UPPER(COALESCE(site_state, '')) AS state,
                UPPER(COALESCE(site_city, '')) AS city,
                COALESCE(site_zip, '') AS zip,
                COALESCE(naics_code, '') AS naics,
                COALESCE(site_address, '') AS street_address,
                estab_name AS original_name
            FROM osha_establishments
            WHERE estab_name IS NOT NULL AND site_state IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
        """, [sample_size])
        cols = ["id", "name_normalized", "state", "city", "zip", "naics", "street_address", "original_name"]
        df_source = pd.DataFrame(cur.fetchall(), columns=cols)

    print(f"  Source records: {len(df_source):,}")

    # Load F7 targets (all, filtered to states in source sample)
    states = df_source["state"].unique().tolist()
    print(f"Loading F7 targets for {len(states)} states...")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                employer_id::text AS id,
                name_standard AS name_normalized,
                UPPER(COALESCE(state, '')) AS state,
                UPPER(COALESCE(city, '')) AS city,
                COALESCE(zip, '') AS zip,
                COALESCE(naics, '') AS naics,
                COALESCE(street, '') AS street_address,
                employer_name AS original_name
            FROM f7_employers_deduped
            WHERE name_standard IS NOT NULL
              AND UPPER(COALESCE(state, '')) = ANY(%s)
        """, [states])
        df_target = pd.DataFrame(cur.fetchall(), columns=cols)

    print(f"  Target records: {len(df_target):,}")
    return df_source, df_target


def train_model(df_source, df_target):
    """Train the Splink model using EM and export to JSON."""
    from splink import DuckDBAPI, Linker
    from scripts.matching.splink_config import SCENARIOS

    cfg = SCENARIOS["adaptive_fuzzy"]
    settings = cfg["settings"]
    em_blocking = cfg["em_blocking"]

    print("Initializing Splink linker...")
    linker = Linker(
        [df_source, df_target],
        settings=settings,
        db_api=DuckDBAPI(),
        set_up_basic_logging=False,
    )

    print("Estimating u probabilities (random sampling)...")
    linker.training.estimate_u_using_random_sampling(max_pairs=5_000_000)

    for i, br in enumerate(em_blocking):
        print(f"EM pass {i+1}/{len(em_blocking)}: {br}")
        linker.training.estimate_parameters_using_expectation_maximisation(br)

    # Export model
    MODEL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    linker.misc.save_model_to_json(str(MODEL_OUTPUT), overwrite=True)
    print(f"\nModel saved to: {MODEL_OUTPUT}")
    print(f"  File size: {MODEL_OUTPUT.stat().st_size / 1024:.1f} KB")

    # Quick validation: predict on a small sample to check it works
    print("\nValidation: predicting on 1000-record sample...")
    small_source = df_source.head(1000)
    linker2 = Linker(
        [small_source, df_target],
        settings=str(MODEL_OUTPUT),
        db_api=DuckDBAPI(),
        set_up_basic_logging=False,
    )
    results = linker2.inference.predict(threshold_match_probability=0.70)
    df_results = results.as_pandas_dataframe()
    print(f"  Validation matches: {len(df_results):,}")
    if not df_results.empty:
        print(f"  Probability range: {df_results['match_probability'].min():.3f} - "
              f"{df_results['match_probability'].max():.3f}")
        print(f"  HIGH (>=0.85): {(df_results['match_probability'] >= 0.85).sum():,}")
        print(f"  MEDIUM (0.70-0.85): {((df_results['match_probability'] >= 0.70) & (df_results['match_probability'] < 0.85)).sum():,}")

    return linker


def main():
    parser = argparse.ArgumentParser(description="Train adaptive fuzzy Splink model")
    parser.add_argument("--sample-size", type=int, default=50000,
                        help="Number of OSHA records to use for training (default: 50000)")
    args = parser.parse_args()

    conn = get_connection()
    try:
        df_source, df_target = load_training_data(conn, sample_size=args.sample_size)
        train_model(df_source, df_target)
    finally:
        conn.close()

    print("\nDone. The deterministic matcher will now use this model for fuzzy tier 5.")


if __name__ == "__main__":
    main()
