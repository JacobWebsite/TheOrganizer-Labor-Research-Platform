"""Floor Analysis: What is the theoretical best for demographics estimation?

Empirically measures the information-theoretic floor using EEO-1 ground truth.

Phase 1: Year-over-Year Stability (absolute noise floor)
  - For companies appearing in multiple years, how much do demographics change?
  - This is the irreducible floor -- even a perfect model can't beat temporal noise.

Phase 2: Within-Peer Variance (geography x industry floor)
  - Group companies by (NAICS4, county). Predict each as peer group mean.
  - This is the floor for ANY model using only geography + industry.

Phase 3: Job-Category Oracle (occupation information content)
  - Parse EEO-1 per-job-category demographics (categories 1-9).
  - Compute per-category demographic rates from training peers.
  - Weight by each holdout company's actual category headcounts.
  - Tests: "if you knew the exact occupation mix, how much better?"

Phase 4: QCEW Wage Signal Diagnostic
  - Use county x industry wage data to stratify companies.
  - Check if V10 error varies systematically by wage tier.

Phase 5: Summary decomposition of the error budget.

Usage:
    py scripts/analysis/demographics_comparison/floor_analysis.py
"""
import csv
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v6 import CachedLoadersV6
from classifiers import classify_naics_group
from config import get_census_region, EEO1_ALL_CSVS
from methodologies_v5 import RACE_CATS

from run_v9_2 import (
    get_raw_signals, collect_black_signals,
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    train_calibration_v92, apply_calibration_v92,
    mae_dict, evaluate,
)
from run_v10 import (
    build_v10_splits, build_records, scenario_v92_full,
    load_json, SCRIPT_DIR,
    train_hispanic_calibration, apply_hispanic_calibration,
    make_v92_pipeline,
)

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

# EEO-1 job categories (suffix -> label)
JOB_CATEGORIES = [
    ("1", "Senior Officers/Managers"),
    ("1_2", "Mid-Level Officers/Managers"),
    ("2", "Professionals"),
    ("3", "Technicians"),
    ("4", "Sales Workers"),
    ("5", "Office/Clerical"),
    ("6", "Craft Workers"),
    ("7", "Operatives"),
    ("8", "Laborers"),
    ("9", "Service Workers"),
]


# ================================================================
# EEO-1 PER-CATEGORY PARSER
# ================================================================
def _safe_int(val):
    if val is None or val == '':
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def parse_category_demographics(row, cat_suffix):
    """Parse demographics for a single EEO-1 job category.

    Returns dict with total, gender, race, hispanic -- or None if empty.
    """
    total = _safe_int(row.get('TOTAL' + cat_suffix, 0))
    if total == 0:
        return None

    female = _safe_int(row.get('FT' + cat_suffix, 0))
    male = _safe_int(row.get('MT' + cat_suffix, 0))

    white = _safe_int(row.get('WHF' + cat_suffix, 0)) + _safe_int(row.get('WHM' + cat_suffix, 0))
    black = _safe_int(row.get('BLKF' + cat_suffix, 0)) + _safe_int(row.get('BLKM' + cat_suffix, 0))
    asian = _safe_int(row.get('ASIANF' + cat_suffix, 0)) + _safe_int(row.get('ASIANM' + cat_suffix, 0))
    aian = _safe_int(row.get('AIANF' + cat_suffix, 0)) + _safe_int(row.get('AIANM' + cat_suffix, 0))
    nhopi = _safe_int(row.get('NHOPIF' + cat_suffix, 0)) + _safe_int(row.get('NHOPIM' + cat_suffix, 0))
    two_plus = _safe_int(row.get('TOMRF' + cat_suffix, 0)) + _safe_int(row.get('TOMRM' + cat_suffix, 0))
    hispanic = _safe_int(row.get('HISPF' + cat_suffix, 0)) + _safe_int(row.get('HISPM' + cat_suffix, 0))

    race_total = white + black + asian + aian + nhopi + two_plus
    hisp_total = hispanic + race_total
    gender_total = female + male

    def pct(n, d):
        return round(100.0 * n / d, 2) if d > 0 else 0.0

    return {
        'total': total,
        'gender': {'Male': pct(male, gender_total), 'Female': pct(female, gender_total)},
        'race': {
            'White': pct(white, race_total), 'Black': pct(black, race_total),
            'Asian': pct(asian, race_total), 'AIAN': pct(aian, race_total),
            'NHOPI': pct(nhopi, race_total), 'Two+': pct(two_plus, race_total),
        },
        'hispanic': {
            'Hispanic': pct(hispanic, hisp_total),
            'Not Hispanic': pct(race_total, hisp_total),
        },
    }


def parse_full_eeo1_record(row):
    """Parse an EEO-1 row with per-category breakdowns + totals.

    Returns dict with metadata + 'categories' dict + 'total' demographics.
    """
    total_demo = parse_category_demographics(row, '10')
    if not total_demo:
        return None

    categories = {}
    for cat_suffix, cat_label in JOB_CATEGORIES:
        demo = parse_category_demographics(row, cat_suffix)
        if demo and demo['total'] > 0:
            categories[cat_suffix] = demo

    return {
        'company_code': row.get('COMPANY', ''),
        'name': (row.get('CONAME') or row.get('NAME', '')).strip(),
        'year': _safe_int(row.get('YEAR', 0)),
        'naics': (row.get('NAICS') or '').strip(),
        'state': (row.get('STATE') or '').strip(),
        'zipcode': (row.get('ZIPCODE') or '').strip(),
        'county': (row.get('CNTYNAME') or '').strip(),
        'total_demo': total_demo,
        'categories': categories,
        'total_employees': total_demo['total'],
    }


def load_all_eeo1_with_categories():
    """Load all EEO-1 data with per-category breakdowns.

    Returns list of parsed records, deduplicated by (COMPANY, YEAR).
    """
    seen = set()
    records = []
    for csv_path in EEO1_ALL_CSVS:
        if not os.path.exists(csv_path):
            print("  SKIP (not found): %s" % os.path.basename(csv_path))
            continue
        count = 0
        with open(csv_path, 'r', encoding='cp1252') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get('COMPANY', ''), row.get('YEAR', ''))
                if key in seen:
                    continue
                seen.add(key)
                parsed = parse_full_eeo1_record(row)
                if parsed:
                    records.append(parsed)
                    count += 1
        print("  %s: %d records" % (os.path.basename(csv_path), count))
    print("  Total: %d unique company-year records" % len(records))
    return records


# ================================================================
# METRIC HELPERS
# ================================================================
def compute_mae(pred, actual, cats):
    """Compute MAE between two dicts for given categories."""
    if not pred or not actual:
        return None
    errs = []
    for cat in cats:
        if cat in pred and cat in actual:
            errs.append(abs(pred[cat] - actual[cat]))
    return sum(errs) / len(errs) if errs else None


def weighted_avg_demographics(records_with_weights, dim):
    """Compute weighted average demographics across records.

    records_with_weights: list of (demo_dict, weight) where demo_dict has dim key
    Returns averaged dict for that dimension.
    """
    cats = RACE_CATS if dim == "race" else (HISP_CATS if dim == "hispanic" else GENDER_CATS)
    totals = {c: 0.0 for c in cats}
    total_w = 0.0

    for demo, w in records_with_weights:
        d = demo.get(dim)
        if not d:
            continue
        for c in cats:
            if c in d:
                totals[c] += d[c] * w
        total_w += w

    if total_w <= 0:
        return None
    return {c: totals[c] / total_w for c in cats}


# ================================================================
# MAIN
# ================================================================
def main():
    t0 = time.time()
    print("FLOOR ANALYSIS: Theoretical Limits of Demographics Estimation")
    print("=" * 80)

    # ============================================================
    # PHASE 0: Load data
    # ============================================================
    print("\n--- Phase 0: Load Data ---")

    # Load V10 splits and train baseline
    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    print("Building V10 records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d v10=%d" % (len(train_records), len(perm_records), len(v10_records)))

    # Train V10 baseline
    print("\nTraining V10 baseline...")
    final_fn_v10, cal_v10, _, _ = make_v92_pipeline(
        train_records, all_records, d_race=0.85, d_hisp=0.05, d_gender=0.5)
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    def v10_fn(rec):
        pred = scenario_v92_full(rec)
        if not pred:
            return None
        result = apply_calibration_v92(pred, rec, cal_v10, 0.85, 0.0, 0.95)
        result = apply_hispanic_calibration(result, rec, hisp_cal, 0.50)
        return result

    m_v10_perm = evaluate(perm_records, v10_fn)
    m_v10_sealed = evaluate(v10_records, v10_fn)

    print("\n  V10 baseline:")
    print("    Perm:   Race=%.3f Hisp=%.3f Gender=%.3f" % (
        m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"]))
    print("    Sealed: Race=%.3f Hisp=%.3f Gender=%.3f" % (
        m_v10_sealed["race"], m_v10_sealed["hisp"], m_v10_sealed["gender"]))

    # Load full EEO-1 data with per-category breakdowns
    print("\nLoading EEO-1 data with per-category breakdowns...")
    eeo1_records = load_all_eeo1_with_categories()

    # Index by (company_code, year) and by company_code (most recent year)
    eeo1_by_code_year = {}
    eeo1_by_code = {}
    for rec in eeo1_records:
        key = (rec['company_code'], rec['year'])
        eeo1_by_code_year[key] = rec
        existing = eeo1_by_code.get(rec['company_code'])
        if not existing or rec['year'] > existing['year']:
            eeo1_by_code[rec['company_code']] = rec

    # ============================================================
    # PHASE 1: Year-over-Year Stability
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 1: Year-over-Year Stability (Absolute Noise Floor)")
    print("=" * 80)

    # Group by company_code, find those with multiple years
    company_years = defaultdict(list)
    for rec in eeo1_records:
        company_years[rec['company_code']].append(rec)

    multi_year = {k: sorted(v, key=lambda r: r['year'])
                  for k, v in company_years.items() if len(v) >= 2}
    print("  Companies with 2+ years: %d" % len(multi_year))

    # Compute year-to-year MAE
    yoy_race = []
    yoy_hisp = []
    yoy_gender = []
    yoy_race_by_gap = defaultdict(list)  # gap in years -> MAE list

    for code, years in multi_year.items():
        for i in range(len(years) - 1):
            r1 = years[i]['total_demo']
            r2 = years[i + 1]['total_demo']
            gap = years[i + 1]['year'] - years[i]['year']

            m_r = compute_mae(r1['race'], r2['race'], RACE_CATS)
            m_h = compute_mae(r1['hispanic'], r2['hispanic'], HISP_CATS)
            m_g = compute_mae(r1['gender'], r2['gender'], GENDER_CATS)

            if m_r is not None:
                yoy_race.append(m_r)
                yoy_race_by_gap[gap].append(m_r)
            if m_h is not None:
                yoy_hisp.append(m_h)
            if m_g is not None:
                yoy_gender.append(m_g)

    if yoy_race:
        print("\n  Year-over-year MAE (predicting next year from current year):")
        print("    Race MAE:     %.3f  (n=%d)" % (sum(yoy_race) / len(yoy_race), len(yoy_race)))
        print("    Hispanic MAE: %.3f  (n=%d)" % (sum(yoy_hisp) / len(yoy_hisp), len(yoy_hisp)))
        print("    Gender MAE:   %.3f  (n=%d)" % (sum(yoy_gender) / len(yoy_gender), len(yoy_gender)))

        print("\n  By year gap:")
        for gap in sorted(yoy_race_by_gap.keys()):
            vals = yoy_race_by_gap[gap]
            print("    %d-year gap: Race MAE=%.3f (n=%d)" % (gap, sum(vals) / len(vals), len(vals)))

        # Percentile distribution
        yoy_race_sorted = sorted(yoy_race)
        n = len(yoy_race_sorted)
        print("\n  Race MAE percentiles (year-over-year):")
        for pct_label, idx in [("25th", n // 4), ("50th", n // 2), ("75th", 3 * n // 4),
                                ("90th", int(n * 0.9)), ("95th", int(n * 0.95))]:
            print("    %s: %.3f" % (pct_label, yoy_race_sorted[min(idx, n - 1)]))

        print("\n  INTERPRETATION: Even with perfect knowledge of this year's demographics,")
        print("  you'd still get %.3f Race MAE predicting next year." % (sum(yoy_race) / len(yoy_race)))
        print("  This is the absolute thermodynamic floor.")

    # ============================================================
    # PHASE 2: Within-Peer Variance
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 2: Within-Peer Variance (Geography x Industry Floor)")
    print("=" * 80)

    # Build peer groups from ALL EEO-1 companies (most recent year)
    # Group by (NAICS4, state) since we don't have county_fips in raw EEO-1
    peer_groups_state = defaultdict(list)
    peer_groups_naics2_state = defaultdict(list)

    for code, rec in eeo1_by_code.items():
        naics = rec['naics']
        state = rec['state']
        if not naics or not state:
            continue
        naics4 = naics[:4]
        naics2 = naics[:2]
        peer_groups_state[(naics4, state)].append(rec)
        peer_groups_naics2_state[(naics2, state)].append(rec)

    # Evaluate holdout companies using peer group mean
    for group_label, peer_groups, min_peers in [
        ("NAICS4 x State", peer_groups_state, 3),
        ("NAICS2 x State", peer_groups_naics2_state, 5),
    ]:
        print("\n  --- Peer group: %s (min %d peers) ---" % (group_label, min_peers))

        race_maes = []
        hisp_maes = []
        gender_maes = []
        covered = 0
        total = 0

        # Evaluate on holdout companies that are also in EEO-1
        holdout_codes = splits["perm_codes"] | splits["v10_codes"]

        for code in holdout_codes:
            if code not in eeo1_by_code:
                continue
            total += 1
            rec = eeo1_by_code[code]
            naics = rec['naics']
            state = rec['state']
            if not naics or not state:
                continue

            if group_label.startswith("NAICS4"):
                key = (naics[:4], state)
                group = peer_groups_state.get(key, [])
            else:
                key = (naics[:2], state)
                group = peer_groups_naics2_state.get(key, [])

            # Leave-one-out: exclude this company
            peers = [p for p in group if p['company_code'] != code]
            if len(peers) < min_peers:
                continue

            covered += 1
            actual = rec['total_demo']

            # Predict as mean of peers (weighted by headcount)
            peer_preds = [(p['total_demo'], p['total_employees']) for p in peers]

            for dim, cats, mae_list in [
                ("race", RACE_CATS, race_maes),
                ("hispanic", HISP_CATS, hisp_maes),
                ("gender", GENDER_CATS, gender_maes),
            ]:
                pred = weighted_avg_demographics(peer_preds, dim)
                if pred:
                    m = compute_mae(pred, actual[dim], cats)
                    if m is not None:
                        mae_list.append(m)

        print("    Coverage: %d / %d holdout companies (%.1f%%)" % (
            covered, total, 100.0 * covered / total if total else 0))
        if race_maes:
            print("    Peer-mean MAE:")
            print("      Race:     %.3f  (n=%d)" % (sum(race_maes) / len(race_maes), len(race_maes)))
            print("      Hispanic: %.3f  (n=%d)" % (sum(hisp_maes) / len(hisp_maes), len(hisp_maes)))
            print("      Gender:   %.3f  (n=%d)" % (sum(gender_maes) / len(gender_maes), len(gender_maes)))

    # V10 comparison on same companies
    print("\n  --- V10 on same holdout companies (for direct comparison) ---")
    v10_race_maes = []
    v10_hisp_maes = []
    v10_gender_maes = []
    for rec in perm_records + v10_records:
        pred = v10_fn(rec)
        if not pred:
            continue
        truth = rec["truth"]
        m_r = compute_mae(pred.get("race", {}), truth.get("race", {}), RACE_CATS)
        m_h = compute_mae(pred.get("hispanic", {}), truth.get("hispanic", {}), HISP_CATS)
        m_g = compute_mae(pred.get("gender", {}), truth.get("gender", {}), GENDER_CATS)
        if m_r is not None:
            v10_race_maes.append(m_r)
        if m_h is not None:
            v10_hisp_maes.append(m_h)
        if m_g is not None:
            v10_gender_maes.append(m_g)

    if v10_race_maes:
        print("    V10 MAE:")
        print("      Race:     %.3f  (n=%d)" % (sum(v10_race_maes) / len(v10_race_maes), len(v10_race_maes)))
        print("      Hispanic: %.3f  (n=%d)" % (sum(v10_hisp_maes) / len(v10_hisp_maes), len(v10_hisp_maes)))
        print("      Gender:   %.3f  (n=%d)" % (sum(v10_gender_maes) / len(v10_gender_maes), len(v10_gender_maes)))

    # ============================================================
    # PHASE 3: Job-Category Oracle
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 3: Job-Category Oracle (Occupation Information Content)")
    print("=" * 80)

    # Step 1: From training set, compute per-category demographics by (NAICS group x state)
    print("\n  Building per-category demographic rates from training companies...")

    # Match training records to EEO-1 per-category data
    train_eeo1 = []
    for rec in train_records:
        eeo1_rec = eeo1_by_code.get(rec["company_code"])
        if eeo1_rec and eeo1_rec.get("categories"):
            train_eeo1.append((rec, eeo1_rec))

    print("  Training companies with per-category data: %d / %d" % (
        len(train_eeo1), len(train_records)))

    # Compute avg demographics per (category, naics_group, state) from training data
    # Accumulate headcount-weighted sums
    cat_demo_accum = defaultdict(lambda: {
        "race": defaultdict(float), "hispanic": defaultdict(float),
        "gender": defaultdict(float), "weight": 0.0,
    })

    for model_rec, eeo1_rec in train_eeo1:
        naics_group = model_rec["naics_group"]
        state = model_rec["state"]

        for cat_suffix, demo in eeo1_rec["categories"].items():
            headcount = demo["total"]
            if headcount < 5:
                continue

            # Multiple keys for fallback hierarchy
            keys = [
                (cat_suffix, naics_group, state),       # finest
                (cat_suffix, naics_group, "_all_"),      # state-agnostic
                (cat_suffix, "_all_", state),            # industry-agnostic
                (cat_suffix, "_all_", "_all_"),           # national
            ]
            for key in keys:
                for dim in ["race", "hispanic", "gender"]:
                    for c, v in demo[dim].items():
                        cat_demo_accum[key][dim][c] += v * headcount
                cat_demo_accum[key]["weight"] += headcount  # once per key, NOT per dim

    # Normalize to percentages
    cat_demo_rates = {}
    for key, accum in cat_demo_accum.items():
        w = accum["weight"]
        if w <= 0:
            continue
        entry = {}
        for dim in ["race", "hispanic", "gender"]:
            cats = RACE_CATS if dim == "race" else (HISP_CATS if dim == "hispanic" else GENDER_CATS)
            # Normalize: each category's accum is already pct*headcount, so divide by total weight
            # But since multiple dims share the weight counter, divide per-dim
            n_cats_with_weight = len([c for c in cats if c in accum[dim]])
            if n_cats_with_weight == 0:
                continue
            entry[dim] = {}
            for c in cats:
                entry[dim][c] = accum[dim].get(c, 0.0) / w
        cat_demo_rates[key] = entry

    print("  Built %d (category, industry, state) rate buckets" % len(cat_demo_rates))

    # Count how many of the 10 categories have national-level data
    nat_cats = sum(1 for k in cat_demo_rates if k[1] == "_all_" and k[2] == "_all_")
    print("  Categories with national-level rates: %d" % nat_cats)

    # Step 2: For each holdout company, compute oracle prediction
    print("\n  Computing job-category oracle predictions...")

    def lookup_cat_rate(cat_suffix, naics_group, state):
        """Look up per-category demographic rate with fallback hierarchy."""
        for key in [
            (cat_suffix, naics_group, state),
            (cat_suffix, naics_group, "_all_"),
            (cat_suffix, "_all_", state),
            (cat_suffix, "_all_", "_all_"),
        ]:
            if key in cat_demo_rates:
                return cat_demo_rates[key]
        return None

    # Evaluate oracle on holdout companies
    oracle_race = []
    oracle_hisp = []
    oracle_gender = []
    naive_race = []  # NAICS group x state average (no category weighting) for comparison
    naive_hisp = []
    naive_gender = []
    oracle_covered = 0

    holdout_model_recs = perm_records + v10_records

    for model_rec in holdout_model_recs:
        code = model_rec["company_code"]
        eeo1_rec = eeo1_by_code.get(code)
        if not eeo1_rec or not eeo1_rec.get("categories"):
            continue

        naics_group = model_rec["naics_group"]
        state = model_rec["state"]
        truth = model_rec["truth"]
        categories = eeo1_rec["categories"]

        # Oracle: weight per-category rates by actual headcounts
        for dim, cats, oracle_list, naive_list in [
            ("race", RACE_CATS, oracle_race, naive_race),
            ("hispanic", HISP_CATS, oracle_hisp, naive_hisp),
            ("gender", GENDER_CATS, oracle_gender, naive_gender),
        ]:
            # Oracle prediction
            weighted_pred = {c: 0.0 for c in cats}
            total_w = 0.0
            for cat_suffix, cat_demo in categories.items():
                rate = lookup_cat_rate(cat_suffix, naics_group, state)
                if not rate or dim not in rate:
                    continue
                w = cat_demo["total"]
                for c in cats:
                    weighted_pred[c] += rate[dim].get(c, 0.0) * w
                total_w += w

            if total_w > 0:
                for c in cats:
                    weighted_pred[c] /= total_w
                m = compute_mae(weighted_pred, truth.get(dim, {}), cats)
                if m is not None:
                    oracle_list.append(m)

            # Naive: just use NAICS group x state rate (same as weighting all categories equally)
            naive_rate = lookup_cat_rate("_all_", naics_group, state)
            # Actually use the weighted average across all categories for this industry x state
            # by looking up the total (category 10 equivalent)
            for fb_key in [
                ("1", naics_group, state),  # just use any category's industry x state
            ]:
                pass
            # Simpler: use the national average for category "_all_" industry x state
            # which doesn't exist directly. Use a flat average of all categories instead.
            # Actually, the naive comparison IS what V10 does, so just compare to V10 directly.

        oracle_covered += 1

    print("  Oracle coverage: %d / %d holdout companies" % (oracle_covered, len(holdout_model_recs)))

    if oracle_race:
        print("\n  Job-Category Oracle MAE:")
        print("    Race:     %.3f  (n=%d)" % (sum(oracle_race) / len(oracle_race), len(oracle_race)))
        print("    Hispanic: %.3f  (n=%d)" % (sum(oracle_hisp) / len(oracle_hisp), len(oracle_hisp)))
        print("    Gender:   %.3f  (n=%d)" % (sum(oracle_gender) / len(oracle_gender), len(oracle_gender)))

        print("\n  Comparison:")
        print("    | %-20s | %-10s | %-10s | %-12s |" % ("Method", "Race MAE", "Hisp MAE", "Gender MAE"))
        print("    |%s|%s|%s|%s|" % ("-" * 22, "-" * 12, "-" * 12, "-" * 14))
        print("    | %-20s | %-10.3f | %-10.3f | %-12.3f |" % (
            "V10 Model",
            m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"]))
        print("    | %-20s | %-10.3f | %-10.3f | %-12.3f |" % (
            "Job-Cat Oracle",
            sum(oracle_race) / len(oracle_race),
            sum(oracle_hisp) / len(oracle_hisp),
            sum(oracle_gender) / len(oracle_gender)))
        if yoy_race:
            print("    | %-20s | %-10.3f | %-10.3f | %-12.3f |" % (
                "Year-over-Year Floor",
                sum(yoy_race) / len(yoy_race),
                sum(yoy_hisp) / len(yoy_hisp),
                sum(yoy_gender) / len(yoy_gender)))

    # Job category profile analysis: what does the typical category mix look like?
    print("\n  --- Job Category Mix Distribution ---")
    print("  | %-30s | %-8s | %-8s | %-8s |" % (
        "Category", "Avg %", "Median %", "Std"))
    print("  |%s|%s|%s|%s|" % ("-" * 32, "-" * 10, "-" * 10, "-" * 10))

    all_profiles = []
    for code, rec in eeo1_by_code.items():
        cats = rec.get("categories", {})
        total = rec["total_employees"]
        if total < 50 or not cats:
            continue
        profile = {}
        for cat_suffix, cat_demo in cats.items():
            profile[cat_suffix] = 100.0 * cat_demo["total"] / total
        all_profiles.append(profile)

    if all_profiles:
        for cat_suffix, cat_label in JOB_CATEGORIES:
            vals = [p.get(cat_suffix, 0.0) for p in all_profiles]
            avg = sum(vals) / len(vals)
            vals_sorted = sorted(vals)
            median = vals_sorted[len(vals_sorted) // 2]
            variance = sum((v - avg) ** 2 for v in vals) / len(vals)
            std = variance ** 0.5
            print("  | %-30s | %7.1f%% | %7.1f%% | %7.1f%% |" % (
                cat_label, avg, median, std))

    # Dominant category analysis
    print("\n  --- Does dominant category predict demographics? ---")
    dom_cat_maes = defaultdict(lambda: {"race": [], "hisp": [], "gender": [], "n": 0})

    for model_rec in holdout_model_recs:
        code = model_rec["company_code"]
        eeo1_rec = eeo1_by_code.get(code)
        if not eeo1_rec or not eeo1_rec.get("categories"):
            continue

        # Find dominant category
        cats = eeo1_rec["categories"]
        if not cats:
            continue
        dom = max(cats.items(), key=lambda x: x[1]["total"])
        dom_suffix = dom[0]
        dom_label = dict(JOB_CATEGORIES).get(dom_suffix, dom_suffix)

        pred = v10_fn(model_rec)
        if not pred:
            continue
        truth = model_rec["truth"]

        for dim, dim_cats, dim_key in [
            ("race", RACE_CATS, "race"),
            ("hispanic", HISP_CATS, "hisp"),
            ("gender", GENDER_CATS, "gender"),
        ]:
            m = compute_mae(pred.get(dim, {}), truth.get(dim, {}), dim_cats)
            if m is not None:
                dom_cat_maes[dom_label][dim_key].append(m)
        dom_cat_maes[dom_label]["n"] += 1

    print("  | %-30s | %5s | %-8s | %-8s | %-10s |" % (
        "Dominant Category", "N", "Race MAE", "Hisp MAE", "Gender MAE"))
    print("  |%s|%s|%s|%s|%s|" % ("-" * 32, "-" * 7, "-" * 10, "-" * 10, "-" * 12))

    for cat_label in [label for _, label in JOB_CATEGORIES]:
        data = dom_cat_maes.get(cat_label)
        if not data or data["n"] < 5:
            continue
        r = sum(data["race"]) / len(data["race"]) if data["race"] else 0
        h = sum(data["hisp"]) / len(data["hisp"]) if data["hisp"] else 0
        g = sum(data["gender"]) / len(data["gender"]) if data["gender"] else 0
        print("  | %-30s | %5d | %-8.3f | %-8.3f | %-10.3f |" % (
            cat_label, data["n"], r, h, g))

    # ============================================================
    # PHASE 4: QCEW Wage Signal
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 4: QCEW Wage Signal Diagnostic")
    print("=" * 80)

    # Load QCEW county x industry wages (QCEW uses 3-digit NAICS codes)
    print("\n  Loading QCEW wage data...")
    cur.execute("""
        SELECT area_fips, industry_code, avg_annual_pay
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = (SELECT MAX(year) FROM qcew_annual)
          AND avg_annual_pay > 0
          AND LENGTH(industry_code) = 3
          AND area_fips NOT LIKE '%%000'
    """)

    qcew_wages = {}
    for row in cur.fetchall():
        fips = row["area_fips"]
        ind = row["industry_code"]
        qcew_wages[(fips, ind)] = float(row["avg_annual_pay"])
    print("  Loaded %d (county, NAICS3) wage entries" % len(qcew_wages))

    # State-level wages as fallback (area_fips like 'XX000')
    cur.execute("""
        SELECT area_fips, industry_code, avg_annual_pay
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = (SELECT MAX(year) FROM qcew_annual)
          AND avg_annual_pay > 0
          AND LENGTH(industry_code) = 3
          AND area_fips LIKE '%%000'
    """)
    state_wages = {}
    for row in cur.fetchall():
        state_fips = row["area_fips"][:2]
        ind = row["industry_code"]
        state_wages[(state_fips, ind)] = float(row["avg_annual_pay"])
    print("  Loaded %d (state, NAICS3) wage entries" % len(state_wages))

    # National average wage per NAICS3
    cur.execute("""
        SELECT industry_code, AVG(avg_annual_pay) as avg_pay
        FROM qcew_annual
        WHERE own_code = '5'
          AND year = (SELECT MAX(year) FROM qcew_annual)
          AND avg_annual_pay > 0
          AND LENGTH(industry_code) = 3
          AND area_fips NOT LIKE '%%000'
        GROUP BY industry_code
    """)
    national_wages = {}
    for row in cur.fetchall():
        national_wages[row["industry_code"]] = float(row["avg_pay"])
    print("  Loaded %d national NAICS3 wage averages" % len(national_wages))

    # Assign wage tier to holdout companies
    def get_wage_ratio(rec):
        """Get wage ratio = local wage / national wage for this industry."""
        county = rec["county_fips"]
        naics4 = rec["naics4"]
        state_fips = rec["state_fips"]
        naics3 = naics4[:3] if len(naics4) >= 3 else naics4

        # Try county x NAICS3, then state x NAICS3
        local_wage = qcew_wages.get((county, naics3))
        if not local_wage:
            local_wage = state_wages.get((state_fips, naics3))
        nat_wage = national_wages.get(naics3)

        if local_wage and nat_wage and nat_wage > 0:
            return local_wage / nat_wage
        return None

    wage_coverage = 0
    wage_tiers = defaultdict(list)
    for rec in perm_records + v10_records:
        ratio = get_wage_ratio(rec)
        rec["_wage_ratio"] = ratio
        if ratio is not None:
            wage_coverage += 1
            if ratio < 0.80:
                tier = "low (<80%)"
            elif ratio < 1.0:
                tier = "below_avg (80-100%)"
            elif ratio < 1.20:
                tier = "above_avg (100-120%)"
            else:
                tier = "high (>120%)"
            rec["_wage_tier"] = tier
            wage_tiers[tier].append(rec)
        else:
            rec["_wage_tier"] = None

    print("  Wage ratio coverage: %d / %d holdout companies (%.1f%%)" % (
        wage_coverage, len(perm_records) + len(v10_records),
        100.0 * wage_coverage / (len(perm_records) + len(v10_records))))

    # V10 MAE by wage tier
    print("\n  V10 MAE by wage tier:")
    print("  | %-25s | %5s | %-8s | %-8s | %-10s |" % (
        "Wage Tier", "N", "Race MAE", "Hisp MAE", "Gender MAE"))
    print("  |%s|%s|%s|%s|%s|" % ("-" * 27, "-" * 7, "-" * 10, "-" * 10, "-" * 12))

    for tier in ["low (<80%)", "below_avg (80-100%)", "above_avg (100-120%)", "high (>120%)"]:
        recs = wage_tiers.get(tier, [])
        if len(recs) < 10:
            continue
        r_maes = []
        h_maes = []
        g_maes = []
        for rec in recs:
            pred = v10_fn(rec)
            if not pred:
                continue
            truth = rec["truth"]
            m_r = compute_mae(pred.get("race", {}), truth.get("race", {}), RACE_CATS)
            m_h = compute_mae(pred.get("hispanic", {}), truth.get("hispanic", {}), HISP_CATS)
            m_g = compute_mae(pred.get("gender", {}), truth.get("gender", {}), GENDER_CATS)
            if m_r is not None:
                r_maes.append(m_r)
            if m_h is not None:
                h_maes.append(m_h)
            if m_g is not None:
                g_maes.append(m_g)

        if r_maes:
            print("  | %-25s | %5d | %-8.3f | %-8.3f | %-10.3f |" % (
                tier, len(r_maes),
                sum(r_maes) / len(r_maes),
                sum(h_maes) / len(h_maes) if h_maes else 0,
                sum(g_maes) / len(g_maes) if g_maes else 0))

    # Compute spread from printed table data
    tier_race_vals = []
    for tier in ["low (<80%)", "below_avg (80-100%)", "above_avg (100-120%)", "high (>120%)"]:
        recs = wage_tiers.get(tier, [])
        if len(recs) < 10:
            continue
        r_maes_t = []
        for rec in recs:
            pred = v10_fn(rec)
            if not pred:
                continue
            m_r = compute_mae(pred.get("race"), rec["truth"].get("race"), RACE_CATS)
            if m_r is not None:
                r_maes_t.append(m_r)
        if r_maes_t:
            tier_race_vals.append(sum(r_maes_t) / len(r_maes_t))

    if len(tier_race_vals) >= 2:
        spread = max(tier_race_vals) - min(tier_race_vals)
        print("\n  Race MAE spread across wage tiers: %.3f pp" % spread)
        if spread > 0.3:
            print("  --> SIGNIFICANT: Wage tier contains exploitable information")
        else:
            print("  --> Modest: Wage tier has limited additional information")

    # ============================================================
    # PHASE 5: Summary
    # ============================================================
    print("\n" + "=" * 80)
    print("PHASE 5: Error Budget Decomposition")
    print("=" * 80)

    print("\n  | %-35s | %-10s | %-10s | %-12s |" % (
        "Level", "Race MAE", "Hisp MAE", "Gender MAE"))
    print("  |%s|%s|%s|%s|" % ("-" * 37, "-" * 12, "-" * 12, "-" * 14))

    if yoy_race:
        print("  | %-35s | %-10.3f | %-10.3f | %-12.3f |" % (
            "1. Year-over-Year (noise floor)",
            sum(yoy_race) / len(yoy_race),
            sum(yoy_hisp) / len(yoy_hisp),
            sum(yoy_gender) / len(yoy_gender)))

    if oracle_race:
        print("  | %-35s | %-10.3f | %-10.3f | %-12.3f |" % (
            "2. Job-Category Oracle",
            sum(oracle_race) / len(oracle_race),
            sum(oracle_hisp) / len(oracle_hisp),
            sum(oracle_gender) / len(oracle_gender)))

    print("  | %-35s | %-10.3f | %-10.3f | %-12.3f |" % (
        "3. V10 Model (current best)",
        m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"]))

    print("\n  Gap analysis:")
    if yoy_race and oracle_race:
        yoy_r = sum(yoy_race) / len(yoy_race)
        ora_r = sum(oracle_race) / len(oracle_race)
        v10_r = m_v10_perm["race"]

        print("    V10 -> Oracle gap (occupation info):  %.3f pp (%.1f%% of V10 error)" % (
            v10_r - ora_r, 100.0 * (v10_r - ora_r) / v10_r if v10_r else 0))
        print("    Oracle -> YoY gap (company-specific): %.3f pp (%.1f%% of V10 error)" % (
            ora_r - yoy_r, 100.0 * (ora_r - yoy_r) / v10_r if v10_r else 0))
        print("    YoY floor (irreducible noise):        %.3f pp (%.1f%% of V10 error)" % (
            yoy_r, 100.0 * yoy_r / v10_r if v10_r else 0))

    print("\n  CONCLUSION:")
    if oracle_race:
        ora_r = sum(oracle_race) / len(oracle_race)
        v10_r = m_v10_perm["race"]
        gap = v10_r - ora_r
        if gap > 0.3:
            print("    Job-category oracle beats V10 by %.3fpp." % gap)
            print("    There IS room to improve by incorporating occupation mix signals.")
            print("    The challenge is obtaining occupation mix at inference time.")
            print("    Candidates: BLS industry-occupation matrix, company size, job postings.")
        elif gap > 0.1:
            print("    Job-category oracle is modestly better (%.3fpp)." % gap)
            print("    Some room for improvement from occupation signals, but limited.")
        else:
            print("    Job-category oracle provides negligible improvement (%.3fpp)." % gap)
            print("    V10 is already near the practical floor for this approach.")

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
