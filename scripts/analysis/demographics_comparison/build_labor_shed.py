"""Build county-level labor shed demographics from LODES OD data.

For each work_county: where do commuters come FROM?
Weights origin counties' demographics by commuter count to produce
"labor shed demographics" -- what the commuter pool actually looks like.

This is different from WAC (all workers in the county) because it
accounts for where people commute from, not just where they work.

Output: labor_shed_demographics.json
  {county_fips: {race: {...}, hispanic: {...}, gender: {...}, ...}}

Usage:
    py scripts/analysis/demographics_comparison/build_labor_shed.py
"""
import csv
import gzip
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

LODES_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "New Data sources 2_27", "LODES_bulk_2022"
))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "labor_shed_demographics.json")


def load_county_demographics(cur):
    """Load all county demographics from cur_lodes_geo_metrics."""
    cur.execute("""
        SELECT county_fips,
               jobs_white, jobs_black, jobs_native, jobs_asian, jobs_pacific,
               jobs_two_plus_races,
               jobs_not_hispanic, jobs_hispanic,
               jobs_male, jobs_female,
               demo_total_jobs
        FROM cur_lodes_geo_metrics
    """)
    result = {}
    for row in cur.fetchall():
        fips = row["county_fips"]
        dt = float(row["demo_total_jobs"] or 0)
        if dt == 0:
            continue
        result[fips] = {
            "White": float(row["jobs_white"] or 0) / dt,
            "Black": float(row["jobs_black"] or 0) / dt,
            "AIAN": float(row["jobs_native"] or 0) / dt,
            "Asian": (float(row["jobs_asian"] or 0) + float(row["jobs_pacific"] or 0)) / dt,
            "Two+": float(row["jobs_two_plus_races"] or 0) / dt,
            "Hispanic": float(row["jobs_hispanic"] or 0) / dt,
            "Not Hispanic": float(row["jobs_not_hispanic"] or 0) / dt,
            "Male": float(row["jobs_male"] or 0) / dt,
            "Female": float(row["jobs_female"] or 0) / dt,
        }
    return result


def process_od_files():
    """Stream all OD main files. Returns work_county -> home_county -> job_count."""
    labor_shed = defaultdict(lambda: defaultdict(int))

    od_files = sorted([
        f for f in os.listdir(LODES_DIR)
        if "_od_main_" in f and f.endswith(".csv.gz")
    ])

    print("Found %d OD main files in %s" % (len(od_files), LODES_DIR))
    total_rows = 0

    for i, fname in enumerate(od_files):
        state = fname.split("_")[0].upper()
        fpath = os.path.join(LODES_DIR, fname)
        t0 = time.time()
        rows = 0

        with gzip.open(fpath, "rt", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            # Find column indices (avoid DictReader overhead on 100M+ rows)
            w_idx = header.index("w_geocode")
            h_idx = header.index("h_geocode")
            s_idx = header.index("S000")

            for row in reader:
                work_county = row[w_idx][:5]
                home_county = row[h_idx][:5]
                jobs = int(row[s_idx])
                labor_shed[work_county][home_county] += jobs
                rows += 1

        total_rows += rows
        elapsed = time.time() - t0
        print("  [%2d/%d] %s: %s rows (%.1fs)" % (
            i + 1, len(od_files), state, format(rows, ","), elapsed))

    print("\nTotal: %s rows across %d work counties" % (
        format(total_rows, ","), len(labor_shed)))
    return labor_shed


def compute_labor_shed_demographics(labor_shed, county_demos):
    """For each work_county, weight home counties' demographics by commuter count."""
    result = {}
    counties_without_demos = set()

    for work_county, home_counties in labor_shed.items():
        race_acc = defaultdict(float)
        hisp_acc = defaultdict(float)
        gender_acc = defaultdict(float)
        total_w = 0.0
        local_jobs = home_counties.get(work_county, 0)
        total_jobs = sum(home_counties.values())

        for home_county, job_count in home_counties.items():
            demos = county_demos.get(home_county)
            if not demos:
                counties_without_demos.add(home_county)
                continue

            w = float(job_count)
            total_w += w

            for cat in ["White", "Black", "AIAN", "Asian", "Two+"]:
                race_acc[cat] += w * demos[cat]
            for cat in ["Hispanic", "Not Hispanic"]:
                hisp_acc[cat] += w * demos[cat]
            for cat in ["Male", "Female"]:
                gender_acc[cat] += w * demos[cat]

        if total_w == 0:
            continue

        entry = {
            "race": {k: round(100.0 * v / total_w, 2) for k, v in race_acc.items()},
            "hispanic": {k: round(100.0 * v / total_w, 2) for k, v in hisp_acc.items()},
            "gender": {k: round(100.0 * v / total_w, 2) for k, v in gender_acc.items()},
            "total_commuters": int(total_w),
            "home_counties": len(home_counties),
            "pct_local": round(100.0 * local_jobs / total_jobs, 1) if total_jobs > 0 else 0,
        }
        result[work_county] = entry

    if counties_without_demos:
        print("  %d home counties had no LODES demographics (skipped)" %
              len(counties_without_demos))

    return result


def compare_wac_vs_labor_shed(county_demos, ls_demos):
    """Show how much WAC and labor shed diverge."""
    diffs_by_dim = defaultdict(list)

    for county_fips, ls in ls_demos.items():
        wac = county_demos.get(county_fips)
        if not wac:
            continue

        for cat in ["White", "Black", "Asian"]:
            wac_pct = wac[cat] * 100.0
            ls_pct = ls["race"].get(cat, 0)
            diffs_by_dim["race_" + cat].append(abs(ls_pct - wac_pct))

        wac_hisp = wac["Hispanic"] * 100.0
        ls_hisp = ls["hispanic"].get("Hispanic", 0)
        diffs_by_dim["hispanic"].append(abs(ls_hisp - wac_hisp))

        wac_female = wac["Female"] * 100.0
        ls_female = ls["gender"].get("Female", 0)
        diffs_by_dim["gender"].append(abs(ls_female - wac_female))

    print("\nWAC vs Labor Shed divergence:")
    print("  %-15s %8s %8s %8s %8s" % ("Dimension", "Mean", "Median", "P90", "Max"))
    for dim in sorted(diffs_by_dim.keys()):
        vals = sorted(diffs_by_dim[dim])
        n = len(vals)
        mean = sum(vals) / n
        median = vals[n // 2]
        p90 = vals[int(n * 0.9)]
        mx = vals[-1]
        print("  %-15s %7.1fpp %7.1fpp %7.1fpp %7.1fpp" % (dim, mean, median, p90, mx))

    # Most divergent counties
    county_max = {}
    for county_fips, ls in ls_demos.items():
        wac = county_demos.get(county_fips)
        if not wac:
            continue
        max_diff = 0
        for cat in ["White", "Black", "Asian"]:
            diff = abs(ls["race"].get(cat, 0) - wac[cat] * 100.0)
            max_diff = max(max_diff, diff)
        county_max[county_fips] = max_diff

    print("\n  Top 10 most divergent counties:")
    for fips, diff in sorted(county_max.items(), key=lambda x: -x[1])[:10]:
        ls = ls_demos[fips]
        print("    %s: %.1fpp max race diff, %s commuters from %d counties, %.0f%% local" % (
            fips, diff, format(ls["total_commuters"], ","),
            ls["home_counties"], ls["pct_local"]))


def main():
    t0 = time.time()
    print("=" * 78)
    print("LODES OD Labor Shed Demographics Builder")
    print("=" * 78)

    # Step 1: Load county demographics
    print("\nStep 1: Loading county demographics...")
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    county_demos = load_county_demographics(cur)
    print("  %d counties loaded" % len(county_demos))
    conn.close()

    # Step 2: Process OD files
    print("\nStep 2: Processing OD files (this takes ~10-15 minutes)...")
    labor_shed = process_od_files()

    # Step 3: Compute labor shed demographics
    print("\nStep 3: Computing labor shed demographics...")
    ls_demos = compute_labor_shed_demographics(labor_shed, county_demos)
    print("  %d work counties with labor shed demographics" % len(ls_demos))

    # Step 4: Compare
    print("\nStep 4: WAC vs Labor Shed comparison")
    compare_wac_vs_labor_shed(county_demos, ls_demos)

    # Step 5: Save
    print("\nSaving to %s..." % OUTPUT_PATH)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(ls_demos, f)
    size_mb = os.path.getsize(OUTPUT_PATH) / 1024 / 1024
    print("  %.1f MB written" % size_mb)

    elapsed = time.time() - t0
    print("\nDone in %.1f minutes." % (elapsed / 60))


if __name__ == "__main__":
    main()
