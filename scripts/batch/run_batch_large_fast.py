"""
Fast batch run: nlrb_to_f7 and osha_to_f7 matching.
Uses bulk-load + Python-side normalization for speed.
osha_to_f7 has 1M+ source records - uses streaming approach.
"""

import sys
import os
import re
import time
import psycopg2

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
from scripts.matching.normalizer import normalize_employer_name


def extract_street_number(address):
    """Extract street number from address string."""
    if not address:
        return ""
    # Remove ZIP codes
    clean_addr = re.sub(r'\b\d{5}(-\d{4})?\b', '', address)
    # Remove state abbreviations
    clean_addr = re.sub(r'\b[A-Z]{2}\b', '', clean_addr)
    # Remove city prefix
    clean_addr = re.sub(r'^[^,]+,\s*', '', clean_addr)
    # Find first number
    match = re.search(r'\b(\d+)\b', clean_addr)
    if match:
        return match.group(1)
    match = re.search(r'\b(\d+)\s+[A-Za-z]', address)
    return match.group(1) if match else ""


def fuzzy_name_sim(a, b):
    """Simple trigram similarity (Jaccard on character trigrams)."""
    if not a or not b:
        return 0.0
    a_set = set(a[i:i+3] for i in range(len(a) - 2))
    b_set = set(b[i:i+3] for i in range(len(b) - 2))
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


def build_f7_indexes(conn):
    """Build in-memory indexes for f7_employers_deduped target table."""
    print("  Loading F7 employers...")
    cur = conn.cursor()
    cur.execute("""
        SELECT employer_id, employer_name, employer_name_aggressive, state, city, street
        FROM f7_employers_deduped
    """)
    rows = cur.fetchall()
    print("  F7 records loaded: %d" % len(rows))

    print("  Building normalized index...")
    norm_index = {}
    for eid, ename, eagg, state, city, street in rows:
        norm = normalize_employer_name(ename, "standard").lower()
        if len(norm) >= 3:
            key = (norm, (state or "").upper())
            if key not in norm_index:
                norm_index[key] = []
            norm_index[key].append((eid, ename))

    print("  Building aggressive index...")
    agg_index = {}
    for eid, ename, eagg, state, city, street in rows:
        agg = normalize_employer_name(ename, "aggressive").lower()
        if len(agg) >= 3:
            key = (agg, (state or "").upper(), (city or "").upper().strip())
            if key not in agg_index:
                agg_index[key] = []
            agg_index[key].append((eid, ename))

    print("  Building address index...")
    addr_index = {}
    for eid, ename, eagg, state, city, street in rows:
        if street:
            street_num = extract_street_number(street)
            if street_num:
                key = (street_num, (state or "").upper(), (city or "").upper().strip())
                norm = normalize_employer_name(ename, "standard").lower()
                if key not in addr_index:
                    addr_index[key] = []
                addr_index[key].append((eid, ename, norm))

    print("  Indexes built: norm=%d, agg=%d, addr=%d" % (
        len(norm_index), len(agg_index), len(addr_index)))

    return norm_index, agg_index, addr_index


def run_nlrb_to_f7(conn, norm_index, agg_index, addr_index):
    """Match nlrb_participants to f7_employers_deduped."""
    print("=" * 60)
    print("Scenario: nlrb_to_f7")
    print("=" * 60)
    t0 = time.time()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, participant_name, state, city, address
        FROM nlrb_participants
        WHERE participant_type = 'Employer'
    """)
    sources = cur.fetchall()
    total = len(sources)
    print("  Source records (employer participants): %d" % total)

    matched_ids = set()
    results_norm = []
    results_addr = []
    results_agg = []

    for i, (sid, sname, state, city, addr) in enumerate(sources):
        state_upper = (state or "").upper()
        city_upper = (city or "").upper().strip()

        # Tier 2: Normalized
        norm = normalize_employer_name(sname, "standard").lower()
        if len(norm) >= 3:
            key = (norm, state_upper)
            if key in norm_index:
                t_id, t_name = norm_index[key][0]
                results_norm.append((sid, sname, t_id, t_name))
                matched_ids.add(sid)
                continue

        # Tier 3: Address
        if addr and city_upper:
            street_num = extract_street_number(addr)
            if street_num:
                key = (street_num, state_upper, city_upper)
                if key in addr_index:
                    for t_id, t_name, t_norm in addr_index[key]:
                        sim = fuzzy_name_sim(norm, t_norm)
                        if sim >= 0.3:
                            results_addr.append((sid, sname, t_id, t_name))
                            matched_ids.add(sid)
                            break
                    if sid in matched_ids:
                        continue

        # Tier 4: Aggressive + city
        agg = normalize_employer_name(sname, "aggressive").lower()
        if len(agg) >= 3 and city_upper:
            key = (agg, state_upper, city_upper)
            if key in agg_index:
                t_id, t_name = agg_index[key][0]
                if sid not in matched_ids:
                    results_agg.append((sid, sname, t_id, t_name))
                    matched_ids.add(sid)

        if (i + 1) % 5000 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print("  [nlrb_to_f7] %d / %d processed (%d matched, %.0f rec/s)" % (
                i + 1, total, len(matched_ids), rate))

    elapsed = time.time() - t0
    total_matched = len(matched_ids)
    match_rate = total_matched / total * 100 if total > 0 else 0

    print("")
    print("Results for nlrb_to_f7:")
    print("  Total source:    %d" % total)
    print("  Total matched:   %d" % total_matched)
    print("  Match rate:      %.1f%%" % match_rate)
    print("  Elapsed:         %.1f seconds" % elapsed)
    print("")
    print("  By tier:")
    print("    %-15s %d" % ("NORMALIZED", len(results_norm)))
    print("    %-15s %d" % ("ADDRESS", len(results_addr)))
    print("    %-15s %d" % ("AGGRESSIVE", len(results_agg)))
    print("")
    print("  Sample NORMALIZED matches:")
    for r in results_norm[:5]:
        print("    %s -> %s" % (r[1][:45], r[3][:45]))
    if results_addr:
        print("  Sample ADDRESS matches:")
        for r in results_addr[:5]:
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
        "by_tier": {
            "NORMALIZED": len(results_norm),
            "ADDRESS": len(results_addr),
            "AGGRESSIVE": len(results_agg),
        },
    }


def run_osha_to_f7(conn, norm_index, agg_index, addr_index):
    """Match osha_establishments to f7_employers_deduped. Streaming for 1M+ records."""
    print("=" * 60)
    print("Scenario: osha_to_f7")
    print("=" * 60)
    t0 = time.time()

    # Load all OSHA records (1M records fits in memory)
    print("  Loading OSHA establishments (this may take a moment)...")
    cur = conn.cursor()
    cur.execute("""
        SELECT establishment_id, estab_name, estab_name_normalized,
               site_state, site_city, site_address
        FROM osha_establishments
    """)
    all_rows = cur.fetchall()
    total = len(all_rows)
    cur.close()
    print("  Source records (osha_establishments): %d" % total)

    matched_count = 0
    tier_counts = {"NORMALIZED": 0, "ADDRESS": 0, "AGGRESSIVE": 0}
    samples = {"NORMALIZED": [], "ADDRESS": [], "AGGRESSIVE": []}
    processed = 0
    batch_size = 10000

    print("  Matching...")
    for batch_start in range(0, total, batch_size):
        rows = all_rows[batch_start:batch_start + batch_size]

        for sid, sname, snorm, state, city, addr in rows:
            state_upper = (state or "").upper()
            city_upper = (city or "").upper().strip()

            # Tier 2: Normalized
            norm = normalize_employer_name(sname, "standard").lower() if sname else ""
            if len(norm) >= 3:
                key = (norm, state_upper)
                if key in norm_index:
                    matched_count += 1
                    tier_counts["NORMALIZED"] += 1
                    if len(samples["NORMALIZED"]) < 5:
                        t_id, t_name = norm_index[key][0]
                        samples["NORMALIZED"].append((sname, t_name))
                    continue

            # Tier 3: Address
            if addr and city_upper:
                street_num = extract_street_number(addr)
                if street_num:
                    key = (street_num, state_upper, city_upper)
                    if key in addr_index:
                        found = False
                        for t_id, t_name, t_norm in addr_index[key]:
                            sim = fuzzy_name_sim(norm, t_norm)
                            if sim >= 0.3:
                                matched_count += 1
                                tier_counts["ADDRESS"] += 1
                                if len(samples["ADDRESS"]) < 5:
                                    samples["ADDRESS"].append((sname, t_name))
                                found = True
                                break
                        if found:
                            continue

            # Tier 4: Aggressive + city
            if sname and city_upper:
                agg = normalize_employer_name(sname, "aggressive").lower()
                if len(agg) >= 3:
                    key = (agg, state_upper, city_upper)
                    if key in agg_index:
                        matched_count += 1
                        tier_counts["AGGRESSIVE"] += 1
                        if len(samples["AGGRESSIVE"]) < 5:
                            t_id, t_name = agg_index[key][0]
                            samples["AGGRESSIVE"].append((sname, t_name))

        processed += len(rows)
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print("  [osha_to_f7] %d / %d processed (%d matched, %.0f rec/s)" % (
            processed, total, matched_count, rate))

    elapsed = time.time() - t0
    match_rate = matched_count / total * 100 if total > 0 else 0

    print("")
    print("Results for osha_to_f7:")
    print("  Total source:    %d" % total)
    print("  Total matched:   %d" % matched_count)
    print("  Match rate:      %.1f%%" % match_rate)
    print("  Elapsed:         %.1f seconds (%.1f minutes)" % (elapsed, elapsed / 60))
    print("")
    print("  By tier:")
    for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            print("    %-15s %d" % (tier, count))
    print("")
    for tier in ["NORMALIZED", "ADDRESS", "AGGRESSIVE"]:
        if samples[tier]:
            print("  Sample %s matches:" % tier)
            for s, t in samples[tier]:
                print("    %s -> %s" % ((s or "")[:45], (t or "")[:45]))
    print("")

    return {
        "total_source": total,
        "total_matched": matched_count,
        "match_rate": match_rate,
        "by_tier": tier_counts,
    }


def main():
    print("Connecting to database...")
    conn = psycopg2.connect(
        host="localhost",
        dbname="olms_multiyear",
        user="postgres",
        password="Juniordog33!"
    )
    print("Connected.")

    # Build F7 indexes (shared between both scenarios)
    norm_index, agg_index, addr_index = build_f7_indexes(conn)

    results = {}

    try:
        results["nlrb_to_f7"] = run_nlrb_to_f7(conn, norm_index, agg_index, addr_index)
    except Exception as e:
        print("ERROR in nlrb_to_f7: %s" % e)
        import traceback
        traceback.print_exc()
        conn.rollback()

    try:
        results["osha_to_f7"] = run_osha_to_f7(conn, norm_index, agg_index, addr_index)
    except Exception as e:
        print("ERROR in osha_to_f7: %s" % e)
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
            if count > 0:
                print("    %-15s %d" % (tier, count))

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
