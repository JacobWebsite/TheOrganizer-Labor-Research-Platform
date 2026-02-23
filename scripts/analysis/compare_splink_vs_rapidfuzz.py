"""Compare Splink vs RapidFuzz batch matching on a 5K OSHA sample.

Runs both approaches on the same records and compares:
- Match count
- Overlap (same source->target pairs)
- Quality (name similarity distribution)
- Runtime

Usage:
    python scripts/analysis/compare_splink_vs_rapidfuzz.py
"""
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection
from psycopg2.extras import RealDictCursor


def get_osha_sample(conn, n=5000):
    """Get OSHA records not matched by tiers 1-4 (same as validate script)."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT e.establishment_id AS source_id,
               e.estab_name AS name_raw,
               e.estab_name_normalized AS name_normalized,
               e.site_state AS state, e.site_city AS city, e.site_zip AS zip,
               e.naics_code AS naics,
               COALESCE(e.site_address, '') AS street_address
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
    """Get F7 employer records (same query as deterministic_matcher)."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT employer_id AS id,
               COALESCE(name_aggressive, name_standard) AS name_normalized,
               UPPER(COALESCE(state, '')) AS state,
               UPPER(COALESCE(city, '')) AS city,
               COALESCE(zip, '') AS zip,
               COALESCE(naics, '') AS naics,
               COALESCE(street, '') AS street_address
        FROM f7_employers_deduped
        WHERE name_standard IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


# ============================================================================
# APPROACH 1: Splink (current pipeline)
# ============================================================================
def run_splink(source_records, target_records, model_path, min_sim=0.80):
    """Run Splink matching (replicates _fuzzy_batch_splink logic)."""
    try:
        import pandas as pd
        from splink import Linker, DuckDBAPI
        from rapidfuzz import fuzz as _rf_fuzz
    except ImportError as e:
        print(f"  Splink not available: {e}")
        return None

    source_data = []
    for r in source_records:
        name = r["name_normalized"] or ""
        state = (r["state"] or "").upper().strip()
        if not name or not state or len(name) < 3:
            continue
        source_data.append({
            "id": str(r["source_id"]),
            "name_normalized": name,
            "state": state,
            "city": (r["city"] or "").upper().strip(),
            "zip": (r["zip"] or "").strip()[:5],
            "naics": r["naics"] or "",
            "street_address": r["street_address"] or "",
        })

    target_data = []
    for r in target_records:
        target_data.append({
            "id": str(r["id"]),
            "name_normalized": r["name_normalized"] or "",
            "state": (r["state"] or "").upper().strip(),
            "city": (r["city"] or "").upper().strip(),
            "zip": (r["zip"] or "").strip()[:5],
            "naics": r["naics"] or "",
            "street_address": r["street_address"] or "",
        })

    df_source = pd.DataFrame(source_data)
    df_target = pd.DataFrame(target_data)

    print(f"  Splink: {len(df_source)} source, {len(df_target)} target")

    t0 = time.time()
    linker = Linker(
        [df_source, df_target],
        settings=str(model_path),
        db_api=DuckDBAPI(),
        set_up_basic_logging=False,
    )
    t_init = time.time() - t0

    t0 = time.time()
    df_matches = linker.inference.predict(
        threshold_match_probability=0.60
    ).as_pandas_dataframe()
    t_predict = time.time() - t0

    raw_count = len(df_matches)

    t0 = time.time()
    if len(df_matches) > 0:
        df_matches["name_sim"] = df_matches.apply(
            lambda r: _rf_fuzz.token_sort_ratio(
                str(r.get("name_normalized_l", "")),
                str(r.get("name_normalized_r", "")),
            ) / 100.0,
            axis=1,
        )
        df_matches = df_matches[df_matches["name_sim"] >= min_sim]
        df_matches = df_matches.sort_values("match_probability", ascending=False)
        df_matches = df_matches.drop_duplicates(subset=["id_l"], keep="first")
    t_filter = time.time() - t0

    results = {}
    if len(df_matches) > 0:
        for _, row in df_matches.iterrows():
            src_id = str(row["id_l"])
            tgt_id = str(row["id_r"])
            sim = row["name_sim"]
            prob = row["match_probability"]
            results[src_id] = {
                "target_id": tgt_id,
                "name_sim": sim,
                "prob": prob,
                "src_name": str(row.get("name_normalized_l", "")),
                "tgt_name": str(row.get("name_normalized_r", "")),
            }

    timing = {
        "init": t_init,
        "predict": t_predict,
        "filter": t_filter,
        "total": t_init + t_predict + t_filter,
        "raw_candidates": raw_count,
    }
    return results, timing


# ============================================================================
# APPROACH 2: RapidFuzz with SQL blocking
# ============================================================================
def run_rapidfuzz_blocked(source_records, target_records, min_sim=0.80):
    """RapidFuzz matching using same blocking rules as Splink model."""
    from rapidfuzz import fuzz as _rf_fuzz

    # Build target indexes for each blocking rule
    t0 = time.time()

    # Index 1: state + name[:3]
    idx_state_name3 = defaultdict(list)
    # Index 2: state + city
    idx_state_city = defaultdict(list)
    # Index 3: zip[:3] + name[:2]
    idx_zip3_name2 = defaultdict(list)

    for r in target_records:
        tid = str(r["id"])
        name = (r["name_normalized"] or "").upper().strip()
        state = (r["state"] or "").upper().strip()
        city = (r["city"] or "").upper().strip()
        zipcode = (r["zip"] or "").strip()[:5]

        entry = (tid, r["name_normalized"] or "")

        if state and name and len(name) >= 3:
            idx_state_name3[(state, name[:3])].append(entry)
        if state and city:
            idx_state_city[(state, city)].append(entry)
        if zipcode and len(zipcode) >= 3 and name and len(name) >= 2:
            idx_zip3_name2[(zipcode[:3], name[:2])].append(entry)

    t_index = time.time() - t0

    # Score candidates
    t0 = time.time()
    total_candidates = 0
    results = {}

    for r in source_records:
        name = r["name_normalized"] or ""
        state = (r["state"] or "").upper().strip()
        city = (r["city"] or "").upper().strip()
        zipcode = (r["zip"] or "").strip()[:5]
        src_id = str(r["source_id"])

        if not name or not state or len(name) < 3:
            continue

        name_upper = name.upper().strip()

        # Collect candidates from all blocking rules (deduplicated)
        candidate_ids = set()
        candidates = []

        # Block 1: state + name[:3]
        key1 = (state, name_upper[:3])
        for tid, tname in idx_state_name3.get(key1, []):
            if tid not in candidate_ids:
                candidate_ids.add(tid)
                candidates.append((tid, tname))

        # Block 2: state + city
        if city:
            key2 = (state, city)
            for tid, tname in idx_state_city.get(key2, []):
                if tid not in candidate_ids:
                    candidate_ids.add(tid)
                    candidates.append((tid, tname))

        # Block 3: zip[:3] + name[:2]
        if zipcode and len(zipcode) >= 3:
            key3 = (zipcode[:3], name_upper[:2])
            for tid, tname in idx_zip3_name2.get(key3, []):
                if tid not in candidate_ids:
                    candidate_ids.add(tid)
                    candidates.append((tid, tname))

        total_candidates += len(candidates)

        # Score all candidates
        best_sim = 0.0
        best_match = None
        for tid, tname in candidates:
            sim = _rf_fuzz.token_sort_ratio(name, tname) / 100.0
            if sim >= min_sim and sim > best_sim:
                best_sim = sim
                best_match = (tid, tname, sim)

        if best_match:
            results[src_id] = {
                "target_id": best_match[0],
                "name_sim": best_match[2],
                "src_name": name,
                "tgt_name": best_match[1],
            }

    t_score = time.time() - t0

    timing = {
        "index_build": t_index,
        "scoring": t_score,
        "total": t_index + t_score,
        "total_candidates": total_candidates,
        "avg_candidates_per_source": total_candidates / max(len(source_records), 1),
    }
    return results, timing


# ============================================================================
# Comparison
# ============================================================================
def compare_results(splink_results, rf_results):
    """Compare two sets of matching results."""
    splink_ids = set(splink_results.keys())
    rf_ids = set(rf_results.keys())

    both = splink_ids & rf_ids
    splink_only = splink_ids - rf_ids
    rf_only = rf_ids - splink_ids

    # Check if matches to SAME target
    same_target = 0
    diff_target = 0
    for sid in both:
        if splink_results[sid]["target_id"] == rf_results[sid]["target_id"]:
            same_target += 1
        else:
            diff_target += 1

    print(f"\n{'='*80}")
    print("COMPARISON: Splink vs RapidFuzz")
    print(f"{'='*80}")
    print(f"  Splink matches:    {len(splink_ids):>6}")
    print(f"  RapidFuzz matches: {len(rf_ids):>6}")
    print(f"  Both found:        {len(both):>6}")
    print(f"    Same target:     {same_target:>6}")
    print(f"    Diff target:     {diff_target:>6}")
    print(f"  Splink-only:       {len(splink_only):>6}")
    print(f"  RapidFuzz-only:    {len(rf_only):>6}")

    # Quality by similarity band
    def band_dist(results, label):
        bands = {"0.95+": 0, "0.90-0.94": 0, "0.85-0.89": 0, "0.80-0.84": 0}
        for r in results.values():
            sim = r["name_sim"]
            if sim >= 0.95:
                bands["0.95+"] += 1
            elif sim >= 0.90:
                bands["0.90-0.94"] += 1
            elif sim >= 0.85:
                bands["0.85-0.89"] += 1
            else:
                bands["0.80-0.84"] += 1
        total = len(results) or 1
        print(f"\n  {label} similarity bands:")
        for band, cnt in bands.items():
            print(f"    {band}: {cnt:>5} ({cnt/total*100:5.1f}%)")

    band_dist(splink_results, "Splink")
    band_dist(rf_results, "RapidFuzz")

    # Show Splink-only samples
    if splink_only:
        print(f"\n  Splink-only matches (sample, up to 10):")
        for sid in list(splink_only)[:10]:
            m = splink_results[sid]
            print(f"    {m['src_name'][:35]:35s} <-> {m['tgt_name'][:35]:35s} "
                  f"sim={m['name_sim']:.3f} prob={m.get('prob', 0):.4f}")

    # Show RapidFuzz-only samples
    if rf_only:
        print(f"\n  RapidFuzz-only matches (sample, up to 10):")
        for sid in list(rf_only)[:10]:
            m = rf_results[sid]
            print(f"    {m['src_name'][:35]:35s} <-> {m['tgt_name'][:35]:35s} "
                  f"sim={m['name_sim']:.3f}")

    # Show different-target matches
    if diff_target > 0:
        print(f"\n  Different target matches (sample, up to 10):")
        count = 0
        for sid in both:
            if splink_results[sid]["target_id"] != rf_results[sid]["target_id"]:
                s = splink_results[sid]
                r = rf_results[sid]
                print(f"    Source: {s['src_name'][:40]}")
                print(f"      Splink -> {s['tgt_name'][:35]:35s} sim={s['name_sim']:.3f}")
                print(f"      RFuzz  -> {r['tgt_name'][:35]:35s} sim={r['name_sim']:.3f}")
                count += 1
                if count >= 10:
                    break


def main():
    conn = get_connection()

    print("Loading OSHA sample (5,000 records not matched by tiers 1-4)...")
    osha_sample = get_osha_sample(conn, n=5000)
    print(f"Got {len(osha_sample)} OSHA records")

    print("\nLoading F7 targets...")
    f7_targets = get_f7_targets(conn)
    print(f"Got {len(f7_targets)} F7 targets")

    conn.close()

    # --- RapidFuzz approach ---
    print(f"\n{'='*80}")
    print("APPROACH 2: RapidFuzz with blocking")
    print(f"{'='*80}")
    rf_results, rf_timing = run_rapidfuzz_blocked(osha_sample, f7_targets, min_sim=0.80)
    print(f"  Matches: {len(rf_results)}")
    print(f"  Index build: {rf_timing['index_build']:.2f}s")
    print(f"  Scoring: {rf_timing['scoring']:.2f}s")
    print(f"  Total: {rf_timing['total']:.2f}s")
    print(f"  Total candidates evaluated: {rf_timing['total_candidates']:,}")
    print(f"  Avg candidates per source: {rf_timing['avg_candidates_per_source']:.1f}")

    # --- Splink approach ---
    print(f"\n{'='*80}")
    print("APPROACH 1: Splink (current pipeline)")
    print(f"{'='*80}")
    model_path = os.path.join(
        os.path.dirname(__file__), "..", "matching", "models", "adaptive_fuzzy_model.json"
    )
    splink_result = run_splink(osha_sample, f7_targets, model_path, min_sim=0.80)
    if splink_result is None:
        print("  Splink failed -- compare RapidFuzz results only")
        print(f"\n  RapidFuzz found {len(rf_results)} matches in {rf_timing['total']:.2f}s")
        return

    splink_results, splink_timing = splink_result
    print(f"  Matches: {len(splink_results)}")
    print(f"  Init: {splink_timing['init']:.2f}s")
    print(f"  Predict: {splink_timing['predict']:.2f}s")
    print(f"  Filter: {splink_timing['filter']:.2f}s")
    print(f"  Total: {splink_timing['total']:.2f}s")
    print(f"  Raw candidates (pre-filter): {splink_timing['raw_candidates']:,}")

    # --- Compare ---
    compare_results(splink_results, rf_results)

    # --- Timing summary ---
    print(f"\n{'='*80}")
    print("TIMING SUMMARY")
    print(f"{'='*80}")
    print(f"  Splink total:    {splink_timing['total']:>8.2f}s")
    print(f"  RapidFuzz total: {rf_timing['total']:>8.2f}s")
    if splink_timing['total'] > 0:
        speedup = splink_timing['total'] / rf_timing['total']
        print(f"  Speedup:         {speedup:>8.1f}x")


if __name__ == "__main__":
    main()
