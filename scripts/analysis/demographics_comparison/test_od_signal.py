"""Test LODES OD labor shed demographics as a V10 signal.

Loads labor_shed_demographics.json (built by build_labor_shed.py)
and tests whether labor shed demographics improve V10 predictions
when blended at various weights.

Usage:
    py scripts/analysis/demographics_comparison/test_od_signal.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v6 import CachedLoadersV6
from methodologies_v5 import RACE_CATS

from run_v9_2 import (
    apply_calibration_v92,
    evaluate,
)
from run_v10 import (
    build_v10_splits, build_records, scenario_v92_full, load_json, SCRIPT_DIR,
    train_hispanic_calibration, apply_hispanic_calibration, make_v92_pipeline,
)

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

LS_PATH = os.path.join(os.path.dirname(__file__), "labor_shed_demographics.json")


def load_labor_shed():
    """Load labor shed demographics JSON."""
    with open(LS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def blend_dicts(sources, cats):
    """Blend multiple source dicts with weights. sources = [(dict, weight), ...]"""
    available = [(d, w) for d, w in sources if d is not None]
    if not available:
        return None
    if len(available) == 1:
        return available[0][0]
    total_w = sum(w for _, w in available)
    if total_w <= 0:
        return None
    result = {}
    for cat in cats:
        result[cat] = sum(d.get(cat, 0.0) * w for d, w in available) / total_w
    return result


def main():
    t0 = time.time()
    print("=" * 80)
    print("V10 + LODES OD Labor Shed Signal Test")
    print("=" * 80)

    # Load labor shed
    if not os.path.exists(LS_PATH):
        print("ERROR: %s not found. Run build_labor_shed.py first." % LS_PATH)
        sys.exit(1)

    print("\nLoading labor shed demographics...")
    ls_data = load_labor_shed()
    print("  %d counties with labor shed data" % len(ls_data))

    # Load V10 splits and checkpoint
    print("Loading V10 splits and checkpoint...")
    splits = build_v10_splits()
    cp = load_json(os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json"))
    rec_lookup = {r["company_code"]: r for r in cp["all_records"]}

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)

    # Build records
    print("Building records...")
    all_companies = (splits["train_companies"]
                     + splits["perm_companies"]
                     + splits["v10_companies"])
    all_records = build_records(all_companies, rec_lookup, cl)
    train_records = [r for r in all_records if r["company_code"] in splits["train_codes"]]
    perm_records = [r for r in all_records if r["company_code"] in splits["perm_codes"]]
    v10_records = [r for r in all_records if r["company_code"] in splits["v10_codes"]]
    print("  train=%d perm=%d v10=%d" % (len(train_records), len(perm_records), len(v10_records)))

    # Attach labor shed data to records
    ls_coverage = 0
    for rec in all_records:
        county = rec.get("county_fips")
        if county and county in ls_data:
            rec["labor_shed"] = ls_data[county]
            ls_coverage += 1
        else:
            rec["labor_shed"] = None

    print("  Labor shed coverage: %d / %d (%.1f%%)" % (
        ls_coverage, len(all_records), 100.0 * ls_coverage / len(all_records)))

    # Show divergence stats for covered companies
    diffs = []
    for rec in all_records:
        ls = rec.get("labor_shed")
        if not ls:
            continue
        county = rec.get("county_fips")
        lodes = cl.get_lodes_race(county)
        if not lodes:
            continue
        for cat in RACE_CATS:
            wac_val = lodes.get(cat, 0)
            ls_val = ls["race"].get(cat, 0)
            diffs.append(abs(ls_val - wac_val))
    if diffs:
        diffs.sort()
        print("  WAC vs Labor Shed divergence for EEO-1 companies:")
        print("    Mean=%.1fpp Median=%.1fpp P90=%.1fpp Max=%.1fpp" % (
            sum(diffs) / len(diffs),
            diffs[len(diffs) // 2],
            diffs[int(len(diffs) * 0.9)],
            diffs[-1]))

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

    # V10 baseline metrics
    print("\n" + "=" * 80)
    print("V10 BASELINE")
    print("=" * 80)
    m_v10_perm = evaluate(perm_records, v10_fn)
    m_v10_sealed = evaluate(v10_records, v10_fn)
    print("  Perm:   Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"],
        m_v10_perm["p20"], m_v10_perm["p30"]))
    print("  Sealed: Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_sealed["race"], m_v10_sealed["hisp"], m_v10_sealed["gender"],
        m_v10_sealed["p20"], m_v10_sealed["p30"]))

    # ============================================================
    # TEST 1: Labor shed as standalone signal
    # ============================================================
    print("\n" + "=" * 80)
    print("TEST 1: Labor Shed as Standalone Signal")
    print("=" * 80)

    def ls_only_fn(rec):
        ls = rec.get("labor_shed")
        if not ls:
            return v10_fn(rec)  # fallback
        return {
            "race": ls["race"],
            "hispanic": ls["hispanic"],
            "gender": ls["gender"],
        }

    m_ls_perm = evaluate(perm_records, ls_only_fn)
    print("  Perm:   Race=%.3f Hisp=%.3f Gender=%.3f" % (
        m_ls_perm["race"], m_ls_perm["hisp"], m_ls_perm["gender"]))
    print("  (V10:   Race=%.3f Hisp=%.3f Gender=%.3f)" % (
        m_v10_perm["race"], m_v10_perm["hisp"], m_v10_perm["gender"]))

    # ============================================================
    # TEST 2: Blend labor shed with V10 at various weights
    # ============================================================
    print("\n" + "=" * 80)
    print("TEST 2: Labor Shed Blended with V10 (perm holdout)")
    print("=" * 80)
    print("  | %-6s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
        "LS Wt", "Race", "Hisp", "Gender", "P>20pp", "P>30pp"))
    print("  |%s|%s|%s|%s|%s|%s|" % (
        "-" * 8, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

    for ls_w in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        v10_w = 1.0 - ls_w

        def blended_fn(rec, _lw=ls_w, _vw=v10_w):
            v10_pred = v10_fn(rec)
            ls = rec.get("labor_shed")
            if not v10_pred:
                return ls if ls else None
            if not ls or _lw == 0:
                return v10_pred

            result = {}
            result["race"] = blend_dicts(
                [(v10_pred.get("race"), _vw), (ls["race"], _lw)], RACE_CATS)
            result["hispanic"] = blend_dicts(
                [(v10_pred.get("hispanic"), _vw), (ls["hispanic"], _lw)], HISP_CATS)
            result["gender"] = blend_dicts(
                [(v10_pred.get("gender"), _vw), (ls["gender"], _lw)], GENDER_CATS)
            return result

        m = evaluate(perm_records, blended_fn)
        notes = ""
        if ls_w == 0:
            notes = " (V10 baseline)"
        else:
            improvements = []
            if m["race"] < m_v10_perm["race"] - 0.001:
                improvements.append("race -%.3f" % (m_v10_perm["race"] - m["race"]))
            if m["hisp"] < m_v10_perm["hisp"] - 0.001:
                improvements.append("hisp -%.3f" % (m_v10_perm["hisp"] - m["hisp"]))
            if m["gender"] < m_v10_perm["gender"] - 0.001:
                improvements.append("gender -%.3f" % (m_v10_perm["gender"] - m["gender"]))
            if improvements:
                notes = " " + ", ".join(improvements)

        print("  | %-6.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% |%s" % (
            ls_w, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"], notes))

    # ============================================================
    # TEST 3: Same on sealed holdout at best weight
    # ============================================================
    print("\n" + "=" * 80)
    print("TEST 3: Best Weight on Sealed Holdout")
    print("=" * 80)

    # Test key weights on sealed holdout
    for ls_w in [0.05, 0.10, 0.15, 0.20]:
        v10_w = 1.0 - ls_w

        def blended_sealed_fn(rec, _lw=ls_w, _vw=v10_w):
            v10_pred = v10_fn(rec)
            ls = rec.get("labor_shed")
            if not v10_pred:
                return ls if ls else None
            if not ls or _lw == 0:
                return v10_pred

            result = {}
            result["race"] = blend_dicts(
                [(v10_pred.get("race"), _vw), (ls["race"], _lw)], RACE_CATS)
            result["hispanic"] = blend_dicts(
                [(v10_pred.get("hispanic"), _vw), (ls["hispanic"], _lw)], HISP_CATS)
            result["gender"] = blend_dicts(
                [(v10_pred.get("gender"), _vw), (ls["gender"], _lw)], GENDER_CATS)
            return result

        m = evaluate(v10_records, blended_sealed_fn)
        d_race = m["race"] - m_v10_sealed["race"]
        d_hisp = m["hisp"] - m_v10_sealed["hisp"]
        d_gender = m["gender"] - m_v10_sealed["gender"]
        print("  LS=%.2f  Race=%.3f(%+.3f) Hisp=%.3f(%+.3f) Gender=%.3f(%+.3f)" % (
            ls_w, m["race"], d_race, m["hisp"], d_hisp, m["gender"], d_gender))

    # ============================================================
    # TEST 4: Labor shed divergence analysis
    # ============================================================
    print("\n" + "=" * 80)
    print("TEST 4: Does High Divergence Predict Better Labor Shed Performance?")
    print("=" * 80)

    # Split perm holdout by divergence
    high_div = []
    low_div = []
    for rec in perm_records:
        ls = rec.get("labor_shed")
        if not ls:
            continue
        county = rec.get("county_fips")
        lodes_race = cl.get_lodes_race(county)
        if not lodes_race:
            continue

        # Max race category divergence between WAC and labor shed
        max_diff = 0
        for cat in RACE_CATS:
            diff = abs(ls["race"].get(cat, 0) - lodes_race.get(cat, 0))
            max_diff = max(max_diff, diff)

        if max_diff >= 3.0:  # 3pp+ divergence
            high_div.append(rec)
        else:
            low_div.append(rec)

    print("  High-divergence counties (>=3pp WAC/LS diff): %d companies" % len(high_div))
    print("  Low-divergence counties (<3pp WAC/LS diff):   %d companies" % len(low_div))

    if high_div:
        m_hd_v10 = evaluate(high_div, v10_fn)
        m_hd_ls10 = evaluate(high_div, lambda r: (
            _blend_v10_ls(r, v10_fn, 0.10)))
        m_hd_ls20 = evaluate(high_div, lambda r: (
            _blend_v10_ls(r, v10_fn, 0.20)))
        print("\n  High-divergence subgroup:")
        print("    V10:      Race=%.3f Hisp=%.3f Gender=%.3f" % (
            m_hd_v10["race"], m_hd_v10["hisp"], m_hd_v10["gender"]))
        print("    +LS 10%%:  Race=%.3f Hisp=%.3f Gender=%.3f" % (
            m_hd_ls10["race"], m_hd_ls10["hisp"], m_hd_ls10["gender"]))
        print("    +LS 20%%:  Race=%.3f Hisp=%.3f Gender=%.3f" % (
            m_hd_ls20["race"], m_hd_ls20["hisp"], m_hd_ls20["gender"]))

    if low_div:
        m_ld_v10 = evaluate(low_div, v10_fn)
        m_ld_ls10 = evaluate(low_div, lambda r: (
            _blend_v10_ls(r, v10_fn, 0.10)))
        print("\n  Low-divergence subgroup:")
        print("    V10:      Race=%.3f Hisp=%.3f Gender=%.3f" % (
            m_ld_v10["race"], m_ld_v10["hisp"], m_ld_v10["gender"]))
        print("    +LS 10%%:  Race=%.3f Hisp=%.3f Gender=%.3f" % (
            m_ld_ls10["race"], m_ld_ls10["hisp"], m_ld_ls10["gender"]))

    elapsed = time.time() - t0
    print("\nDone in %.1f minutes." % (elapsed / 60))
    conn.close()


def _blend_v10_ls(rec, v10_fn, ls_w):
    """Helper: blend V10 with labor shed at given weight."""
    v10_pred = v10_fn(rec)
    ls = rec.get("labor_shed")
    v10_w = 1.0 - ls_w
    if not v10_pred:
        return ls if ls else None
    if not ls:
        return v10_pred
    return {
        "race": blend_dicts(
            [(v10_pred.get("race"), v10_w), (ls["race"], ls_w)], RACE_CATS),
        "hispanic": blend_dicts(
            [(v10_pred.get("hispanic"), v10_w), (ls["hispanic"], ls_w)], HISP_CATS),
        "gender": blend_dicts(
            [(v10_pred.get("gender"), v10_w), (ls["gender"], ls_w)], GENDER_CATS),
    }


if __name__ == "__main__":
    main()
