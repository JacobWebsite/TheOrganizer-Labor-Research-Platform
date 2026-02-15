"""
Fast batch run: mergent_to_990 and mergent_to_nlrb matching.
Uses bulk-load + Python-side normalization for correct matching.
"""

import sys
import os
import time
# Force unbuffered output
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)

import builtins
_orig_print = builtins.print
def print(*args, **kwargs):
    kwargs.setdefault('flush', True)
    _orig_print(*args, **kwargs)

sys.path.insert(0, r"C:\Users\jakew\Downloads\labor-data-project")
from db_config import get_connection
from scripts.matching.normalizer import normalize_employer_name


def run_mergent_to_990(conn):
    """Match mergent_employers to ny_990_filers."""
    print("=" * 60)
    print("Scenario: mergent_to_990")
    print("=" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # Load source
    cur.execute("""
        SELECT duns, company_name, ein, state, city
        FROM mergent_employers
    """)
    sources = cur.fetchall()
    total = len(sources)
    print("  Source records: %d" % total)

    # Load target
    cur.execute("""
        SELECT id, business_name, ein, state, city
        FROM ny_990_filers
    """)
    targets = cur.fetchall()
    print("  Target records (ny_990_filers): %d" % len(targets))

    # Build target indexes
    print("  Building indexes...")
    # EIN index
    ein_index = {}
    for t_id, t_name, t_ein, t_state, t_city in targets:
        if t_ein:
            ein_clean = t_ein.replace("-", "").strip()
            if len(ein_clean) == 9 and ein_clean.isdigit():
                key = (ein_clean, (t_state or "").upper())
                if key not in ein_index:
                    ein_index[key] = []
                ein_index[key].append((t_id, t_name))

    # Normalized name index
    norm_index = {}
    for t_id, t_name, t_ein, t_state, t_city in targets:
        norm = normalize_employer_name(t_name, "standard").lower()
        if len(norm) >= 3:
            key = (norm, (t_state or "").upper())
            if key not in norm_index:
                norm_index[key] = []
            norm_index[key].append((t_id, t_name))

    print("  EIN index entries: %d" % len(ein_index))
    print("  Normalized name index entries: %d" % len(norm_index))

    # Match
    print("  Matching...")
    matched_duns = set()
    results_ein = []
    results_norm = []

    for duns, name, ein, state, city in sources:
        state_upper = (state or "").upper()

        # Tier 1: EIN
        if ein:
            ein_clean = ein.replace("-", "").strip()
            if len(ein_clean) == 9 and ein_clean.isdigit():
                key = (ein_clean, state_upper)
                if key in ein_index:
                    t_id, t_name = ein_index[key][0]
                    results_ein.append((duns, name, t_id, t_name))
                    matched_duns.add(duns)
                    continue

        # Tier 2: Normalized name + state
        norm = normalize_employer_name(name, "standard").lower()
        if len(norm) >= 3:
            key = (norm, state_upper)
            if key in norm_index:
                t_id, t_name = norm_index[key][0]
                if duns not in matched_duns:
                    results_norm.append((duns, name, t_id, t_name))
                    matched_duns.add(duns)

    elapsed = time.time() - t0
    match_rate = len(matched_duns) / total * 100 if total > 0 else 0

    print("")
    print("Results for mergent_to_990:")
    print("  Total source:    %d" % total)
    print("  Total matched:   %d" % len(matched_duns))
    print("  Match rate:      %.1f%%" % match_rate)
    print("  Elapsed:         %.1f seconds" % elapsed)
    print("")
    print("  By tier:")
    print("    %-15s %d" % ("EIN", len(results_ein)))
    print("    %-15s %d" % ("NORMALIZED", len(results_norm)))
    print("")
    print("  Sample EIN matches:")
    for r in results_ein[:3]:
        print("    %s -> %s" % (r[1][:45], r[3][:45]))
    print("  Sample NORMALIZED matches:")
    for r in results_norm[:5]:
        print("    %s -> %s" % (r[1][:45], r[3][:45]))
    print("")

    return {
        "total_source": total,
        "total_matched": len(matched_duns),
        "match_rate": match_rate,
        "by_tier": {"EIN": len(results_ein), "NORMALIZED": len(results_norm)},
    }


def run_mergent_to_nlrb(conn):
    """Match mergent_employers to nlrb_participants."""
    print("=" * 60)
    print("Scenario: mergent_to_nlrb")
    print("=" * 60)
    t0 = time.time()
    cur = conn.cursor()

    # Load source
    cur.execute("""
        SELECT duns, company_name, state, city, street_address
        FROM mergent_employers
    """)
    sources = cur.fetchall()
    total = len(sources)
    print("  Source records: %d" % total)

    # Load target (employer participants only)
    cur.execute("""
        SELECT id, participant_name, state, city, address
        FROM nlrb_participants
        WHERE participant_type = 'Employer'
    """)
    targets = cur.fetchall()
    print("  Target records (nlrb employer participants): %d" % len(targets))

    # Build target indexes
    print("  Building indexes...")

    # Normalized name + state index
    norm_index = {}
    for t_id, t_name, t_state, t_city, t_addr in targets:
        norm = normalize_employer_name(t_name, "standard").lower()
        if len(norm) >= 3:
            key = (norm, (t_state or "").upper())
            if key not in norm_index:
                norm_index[key] = []
            norm_index[key].append((t_id, t_name, t_addr))

    # Aggressive name + city index for tier 4
    agg_index = {}
    for t_id, t_name, t_state, t_city, t_addr in targets:
        agg = normalize_employer_name(t_name, "aggressive").lower()
        if len(agg) >= 3:
            key = (agg, (t_state or "").upper(), (t_city or "").upper().strip())
            if key not in agg_index:
                agg_index[key] = []
            agg_index[key].append((t_id, t_name))

    print("  Normalized index entries: %d" % len(norm_index))
    print("  Aggressive index entries: %d" % len(agg_index))

    # Match
    print("  Matching...")
    matched_duns = set()
    results_norm = []
    results_agg = []

    for duns, name, state, city, street_addr in sources:
        state_upper = (state or "").upper()
        city_upper = (city or "").upper().strip()

        # Tier 2: Normalized
        norm = normalize_employer_name(name, "standard").lower()
        if len(norm) >= 3:
            key = (norm, state_upper)
            if key in norm_index:
                t_id, t_name, _ = norm_index[key][0]
                results_norm.append((duns, name, t_id, t_name))
                matched_duns.add(duns)
                continue

        # Tier 4: Aggressive + city
        agg = normalize_employer_name(name, "aggressive").lower()
        if len(agg) >= 3 and city_upper:
            key = (agg, state_upper, city_upper)
            if key in agg_index:
                t_id, t_name = agg_index[key][0]
                if duns not in matched_duns:
                    results_agg.append((duns, name, t_id, t_name))
                    matched_duns.add(duns)

    elapsed = time.time() - t0
    total_matched = len(matched_duns)
    match_rate = total_matched / total * 100 if total > 0 else 0

    print("")
    print("Results for mergent_to_nlrb:")
    print("  Total source:    %d" % total)
    print("  Total matched:   %d" % total_matched)
    print("  Match rate:      %.1f%%" % match_rate)
    print("  Elapsed:         %.1f seconds" % elapsed)
    print("")
    print("  By tier:")
    print("    %-15s %d" % ("NORMALIZED", len(results_norm)))
    print("    %-15s %d" % ("AGGRESSIVE", len(results_agg)))
    print("")
    print("  Sample NORMALIZED matches:")
    for r in results_norm[:5]:
        print("    %s -> %s" % (r[1][:45], r[3][:45]))
    if results_agg:
        print("  Sample AGGRESSIVE matches:")
        for r in results_agg[:5]:
            print("    %s -> %s" % (r[1][:45], r[3][:45]))
    print("")

    return {
        "total_source": total,
        "total_matched": total_matched,
        "match_rate": match_rate,
        "by_tier": {"NORMALIZED": len(results_norm), "AGGRESSIVE": len(results_agg)},
    }


def main():
    print("Connecting to database...")
    conn = get_connection()
    print("Connected.")

    results = {}

    try:
        results["mergent_to_990"] = run_mergent_to_990(conn)
    except Exception as e:
        print("ERROR in mergent_to_990: %s" % e)
        import traceback
        traceback.print_exc()
        conn.rollback()

    try:
        results["mergent_to_nlrb"] = run_mergent_to_nlrb(conn)
    except Exception as e:
        print("ERROR in mergent_to_nlrb: %s" % e)
        import traceback
        traceback.print_exc()
        conn.rollback()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, r in results.items():
        print("  %-25s %d / %d matched (%.1f%%)" % (
            name, r["total_matched"], r["total_source"], r["match_rate"]))
        for tier, count in r["by_tier"].items():
            print("    %-15s %d" % (tier, count))

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
