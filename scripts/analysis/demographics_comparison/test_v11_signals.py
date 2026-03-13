"""Test V11 signal candidates against V10 baseline.

Signals under test:
  A. Education-weighted demographics (race, hispanic, gender)
     Chain: NAICS -> BLS occ mix -> education dist -> ACS demographics by education
  B. SimplyAnalytics county x industry gender (direct signal)
  C. Both combined

Usage:
    py scripts/analysis/demographics_comparison/test_v11_signals.py
"""
import json
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
from config import get_census_region
from methodologies_v5 import RACE_CATS, smoothed_ipf

from run_v9_2 import (
    get_raw_signals, collect_black_signals,
    train_industry_weights, train_tier_weights,
    make_hispanic_predictor, get_diversity_tier,
    get_gender,
    train_calibration_v92, apply_calibration_v92,
    apply_black_adjustment, mae_dict, max_cat_error,
    evaluate, check_7_criteria, print_acceptance,
    blend_hispanic,
)
from run_v10 import (
    build_v10_splits, build_records, scenario_v92_full, scenario_v92_race,
    load_json, save_json, SCRIPT_DIR,
    train_hispanic_calibration, apply_hispanic_calibration, estimate_confidence,
    make_v92_pipeline, get_hispanic_county_tier,
)

HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]

# ================================================================
# BLS TYPICAL_EDUCATION -> ACS EDUCATION CODE MAPPING
# ================================================================
BLS_TO_ACS_EDU = {
    "No formal educational credential": "06",
    "High school diploma or equivalent": "06",
    "Some college, no degree": "07",
    "Postsecondary nondegree award": "07",
    "Associate's degree": "07",
    "Bachelor's degree": "08",
    "Master's degree": "10",
    "Doctoral or professional degree": "10",
}

ACS_EDU_TIERS = ["06", "07", "08", "10"]

# SimplyAnalytics sector -> NAICS 2-digit mapping
SA_SECTOR_TO_NAICS2 = {
    "Agriculture, forestry, fishing and hunting, and mining": ["11", "21"],
    "Construction": ["23"],
    "Manufacturing": ["31", "32", "33"],
    "Wholesale trade": ["42"],
    "Retail trade": ["44", "45"],
    "Transportation and warehousing, and utilities": ["48", "49", "22"],
    "Information": ["51"],
    "Finance and insurance, and real estate, and rental and leasing": ["52", "53"],
    "Professional, scientific, and management, and administrative, and waste management services": ["54", "55", "56"],
    "Educational services, and health care and social assistance": ["61", "62"],
    "Arts, entertainment, and recreation, and accommodation and food services": ["71", "72"],
    "Other services, except public administration": ["81"],
    "Public administration": ["92"],
}

# Reverse: NAICS 2-digit -> SA sector index (column offset)
NAICS2_TO_SA_SECTOR_IDX = {}
SA_SECTORS_ORDERED = list(SA_SECTOR_TO_NAICS2.keys())
for idx, (sector, naics_list) in enumerate(SA_SECTOR_TO_NAICS2.items()):
    for n2 in naics_list:
        NAICS2_TO_SA_SECTOR_IDX[n2] = idx


# ================================================================
# LOAD SIMPLYANALYTICS DATA
# ================================================================
def load_simplyanalytics_gender():
    """Load county x industry gender data from Excel.

    Returns dict: county_fips -> {naics2 -> {'Male': pct, 'Female': pct}}
    """
    try:
        import openpyxl
    except ImportError:
        print("  openpyxl not available, skipping SimplyAnalytics signal")
        return {}

    xlsx_path = os.path.join(
        os.path.dirname(SCRIPT_DIR), "..", "..",
        "New Project 3_Ranking_2026-03-12_12-25-03.xlsx"
    )
    if not os.path.exists(xlsx_path):
        # Try project root
        xlsx_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..",
            "New Project 3_Ranking_2026-03-12_12-25-03.xlsx"
        ))
    if not os.path.exists(xlsx_path):
        print("  SimplyAnalytics Excel not found, skipping")
        return {}

    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    ws = wb["SimplyAnalytics Export"]

    result = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # header
        vals = list(row)
        fips = str(vals[1]).zfill(5) if vals[1] else None
        if not fips:
            continue

        # Total male/female percentages
        total_male = float(vals[2]) if vals[2] else 0.0
        total_female = float(vals[16]) if vals[16] else 0.0

        county_data = {}

        # Overall county gender (not industry-specific)
        if total_male + total_female > 0:
            county_data["_overall"] = {
                "Male": round(total_male * 100 / (total_male + total_female), 2),
                "Female": round(total_female * 100 / (total_male + total_female), 2),
            }

        # Per-sector gender
        for sec_idx, sector_name in enumerate(SA_SECTORS_ORDERED):
            male_col = 3 + sec_idx      # columns 3-15 are male sectors
            female_col = 17 + sec_idx    # columns 17-29 are female sectors
            m_pct = float(vals[male_col]) if vals[male_col] else 0.0
            f_pct = float(vals[female_col]) if vals[female_col] else 0.0

            if m_pct + f_pct > 0:
                gender = {
                    "Male": round(m_pct * 100 / (m_pct + f_pct), 2),
                    "Female": round(f_pct * 100 / (m_pct + f_pct), 2),
                }
                for n2 in SA_SECTOR_TO_NAICS2[sector_name]:
                    county_data[n2] = gender

        result[fips] = county_data

    wb.close()
    return result


# ================================================================
# EDUCATION-WEIGHTED DEMOGRAPHICS SIGNAL
# ================================================================
class EducationSignalBuilder:
    """Builds education-weighted demographic estimates."""

    def __init__(self, cur):
        self.cur = cur
        self._occ_edu_cache = {}  # industry_code -> {edu_code: pct}
        self._acs_edu_cache = {}  # (naics4, state_fips, edu_code) -> demographics
        self._load_occ_education_mapping()

    def _load_occ_education_mapping(self):
        """Load BLS occupation -> typical education for all industries."""
        self.cur.execute("""
            SELECT bom.industry_code, bom.occupation_code, bom.employment_2024,
                   bp.typical_education
            FROM bls_industry_occupation_matrix bom
            JOIN bls_occupation_projections bp
              ON LEFT(bom.occupation_code, 7) = LEFT(bp.soc_code, 7)
            WHERE bp.typical_education IS NOT NULL
              AND bom.employment_2024 > 0
        """)

        # Build education distribution per industry
        industry_edu = defaultdict(lambda: defaultdict(float))
        for row in self.cur.fetchall():
            ind = row["industry_code"]
            edu = BLS_TO_ACS_EDU.get(row["typical_education"])
            if edu:
                industry_edu[ind][edu] += float(row["employment_2024"])

        # Normalize to percentages
        for ind, edu_dist in industry_edu.items():
            total = sum(edu_dist.values())
            if total > 0:
                self._occ_edu_cache[ind] = {
                    edu: emp / total for edu, emp in edu_dist.items()
                }

    def get_education_dist(self, naics4):
        """Get estimated education distribution for a NAICS industry.

        Tries 6-digit, 4-digit, 2-digit codes.
        Returns dict {edu_code: fraction} or None.
        """
        # Try exact codes with zero-padding
        for code in [naics4 + "00", naics4[:4] + "00", naics4[:3] + "000", naics4[:2] + "0000"]:
            if code in self._occ_edu_cache:
                return self._occ_edu_cache[code]
        return None

    def get_acs_demographics_by_education(self, naics4, state_fips, edu_code):
        """Get ACS race/hispanic/gender demographics for industry x state x education level."""
        key = (naics4, state_fips, edu_code)
        if key in self._acs_edu_cache:
            return self._acs_edu_cache[key]

        # Try NAICS4, then 2-digit, then state-wide
        for naics_val in [naics4, naics4[:2] if len(naics4) >= 2 else naics4]:
            self.cur.execute("""
                SELECT race, hispanic, sex,
                       SUM(weighted_workers) as w
                FROM cur_acs_workforce_demographics
                WHERE naics4 = %s AND state_fips = %s AND education = %s
                GROUP BY race, hispanic, sex
            """, (naics_val, state_fips, edu_code))
            rows = self.cur.fetchall()
            if rows:
                result = self._parse_acs_rows(rows)
                self._acs_edu_cache[key] = result
                return result

        self._acs_edu_cache[key] = None
        return None

    def _parse_acs_rows(self, rows):
        """Parse ACS rows into race/hispanic/gender dicts."""
        race_totals = defaultdict(float)
        hisp_totals = defaultdict(float)
        gender_totals = defaultdict(float)
        total_w = 0.0

        race_map = {
            '1': 'White', '2': 'Black', '3': 'AIAN',
            '4': 'Asian', '5': 'Asian', '6': 'Other',
            '7': 'Two+', '8': 'Two+', '9': 'Two+',
        }

        for row in rows:
            w = float(row['w'])
            total_w += w

            # Race (non-Hispanic only for race categories)
            if row['hispanic'] == '0':
                race_key = race_map.get(row['race'], 'Other')
                race_totals[race_key] += w

            # Hispanic
            if row['hispanic'] == '1':
                hisp_totals['Hispanic'] += w
            else:
                hisp_totals['Not Hispanic'] += w

            # Gender (column is 'sex')
            if row['sex'] == '1':
                gender_totals['Male'] += w
            elif row['sex'] == '2':
                gender_totals['Female'] += w

        result = {}

        # Race
        race_total = sum(race_totals.values())
        if race_total > 0:
            result['race'] = {k: round(100.0 * v / race_total, 2)
                             for k, v in race_totals.items()}

        # Hispanic
        hisp_total = sum(hisp_totals.values())
        if hisp_total > 0:
            result['hispanic'] = {k: round(100.0 * v / hisp_total, 2)
                                 for k, v in hisp_totals.items()}

        # Gender
        gender_total = sum(gender_totals.values())
        if gender_total > 0:
            result['gender'] = {k: round(100.0 * v / gender_total, 2)
                               for k, v in gender_totals.items()}

        return result if result else None

    def get_education_weighted_demographics(self, naics4, state_fips):
        """Get education-weighted demographics for industry x state.

        Returns dict with 'race', 'hispanic', 'gender' sub-dicts, or None.
        """
        edu_dist = self.get_education_dist(naics4)
        if not edu_dist:
            return None

        # Get demographics for each education tier
        weighted_race = defaultdict(float)
        weighted_hisp = defaultdict(float)
        weighted_gender = defaultdict(float)
        total_race_w = 0.0
        total_hisp_w = 0.0
        total_gender_w = 0.0

        for edu_code, edu_fraction in edu_dist.items():
            demo = self.get_acs_demographics_by_education(naics4, state_fips, edu_code)
            if not demo:
                continue

            if demo.get('race'):
                for cat, pct in demo['race'].items():
                    weighted_race[cat] += pct * edu_fraction
                total_race_w += edu_fraction

            if demo.get('hispanic'):
                for cat, pct in demo['hispanic'].items():
                    weighted_hisp[cat] += pct * edu_fraction
                total_hisp_w += edu_fraction

            if demo.get('gender'):
                for cat, pct in demo['gender'].items():
                    weighted_gender[cat] += pct * edu_fraction
                total_gender_w += edu_fraction

        result = {}

        if total_race_w > 0:
            result['race'] = {k: round(v / total_race_w, 2) for k, v in weighted_race.items()}
        if total_hisp_w > 0:
            result['hispanic'] = {k: round(v / total_hisp_w, 2) for k, v in weighted_hisp.items()}
        if total_gender_w > 0:
            result['gender'] = {k: round(v / total_gender_w, 2) for k, v in weighted_gender.items()}

        return result if result else None


# ================================================================
# SIGNAL BLENDING
# ================================================================
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


# ================================================================
# TEST HARNESS
# ================================================================
def main():
    t0 = time.time()
    print("V11 Signal Testing: Education + SimplyAnalytics Gender")
    print("=" * 80)

    # Load V10 splits and checkpoint
    print("\nLoading data...")
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

    # Train V10 baseline
    print("\nTraining V10 baseline (Hispanic weights + calibration)...")
    final_fn_v10, cal_v10, _, _ = make_v92_pipeline(
        train_records, all_records, d_race=0.85, d_hisp=0.05, d_gender=0.5)

    # Train Hispanic-specific calibration
    hisp_cal = train_hispanic_calibration(train_records, scenario_v92_full, max_offset=15.0)

    # V10 final function (d_race=0.85, d_hisp=0.50, d_gender=0.95)
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
    # SIGNAL A: Education-weighted demographics
    # ============================================================
    print("\n" + "=" * 80)
    print("SIGNAL A: Education-Weighted Demographics")
    print("=" * 80)

    print("Loading education signal builder...")
    edu_builder = EducationSignalBuilder(cur)
    print("  Loaded %d industry education distributions" % len(edu_builder._occ_edu_cache))

    # Compute education signal for all records
    edu_coverage = 0
    for rec in all_records:
        edu_demo = edu_builder.get_education_weighted_demographics(
            rec["naics4"], rec["state_fips"])
        rec["edu_signal"] = edu_demo
        if edu_demo:
            edu_coverage += 1
    print("  Education signal coverage: %d / %d (%.1f%%)" % (
        edu_coverage, len(all_records), 100.0 * edu_coverage / len(all_records)))

    # Test education signal as standalone
    print("\n--- Education signal standalone accuracy ---")
    def edu_only_fn(rec):
        edu = rec.get("edu_signal")
        if not edu:
            return v10_fn(rec)  # fallback to V10
        return edu

    m_edu_perm = evaluate(perm_records, edu_only_fn)
    print("  Perm:   Race=%.3f Hisp=%.3f Gender=%.3f" % (
        m_edu_perm["race"], m_edu_perm["hisp"], m_edu_perm["gender"]))

    # Test blending education signal with V10 at various weights
    print("\n--- Education signal blended with V10 (perm holdout) ---")
    print("  | %-8s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
        "Edu Wt", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
    print("  |%s|%s|%s|%s|%s|%s|" % (
        "-" * 10, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

    best_configs = []
    for edu_w in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        v10_w = 1.0 - edu_w

        def blended_fn(rec, _ew=edu_w, _vw=v10_w):
            v10_pred = v10_fn(rec)
            edu_pred = rec.get("edu_signal")
            if not v10_pred:
                return edu_pred
            if not edu_pred or _ew == 0:
                return v10_pred
            result = {}
            for dim in ["race", "hispanic", "gender"]:
                cats = RACE_CATS if dim == "race" else (HISP_CATS if dim == "hispanic" else GENDER_CATS)
                result[dim] = blend_dicts(
                    [(v10_pred.get(dim), _vw), (edu_pred.get(dim), _ew)], cats)
            return result

        m = evaluate(perm_records, blended_fn)
        notes = ""
        if edu_w == 0:
            notes = " (V10 baseline)"
        elif m["race"] < m_v10_perm["race"] and m["hisp"] < m_v10_perm["hisp"]:
            notes = " *BOTH IMPROVE*"
        elif m["race"] < m_v10_perm["race"]:
            notes = " race improves"
        elif m["hisp"] < m_v10_perm["hisp"]:
            notes = " hisp improves"

        print("  | %-8.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% |%s" % (
            edu_w, m["race"], m["hisp"], m["gender"], m["p20"], m["p30"], notes))
        best_configs.append({"edu_w": edu_w, "metrics": m})

    # Test per-dimension blending (different weight for each dimension)
    print("\n--- Per-dimension education blending (perm holdout) ---")
    print("  Testing: education weight applied to ONE dimension at a time")
    for dim_name, dim_key in [("Race", "race"), ("Hispanic", "hisp"), ("Gender", "gender")]:
        print("\n  %s dimension only:" % dim_name)
        cats = RACE_CATS if dim_key == "race" else (HISP_CATS if dim_key == "hisp" else GENDER_CATS)
        dim_label = dim_key if dim_key != "hisp" else "hispanic"

        for edu_w in [0.10, 0.20, 0.30, 0.40]:
            def dim_fn(rec, _ew=edu_w, _dim=dim_label, _cats=cats):
                v10_pred = v10_fn(rec)
                edu_pred = rec.get("edu_signal")
                if not v10_pred:
                    return edu_pred
                if not edu_pred:
                    return v10_pred
                result = dict(v10_pred)  # start with V10
                if edu_pred.get(_dim) and v10_pred.get(_dim):
                    result[_dim] = blend_dicts(
                        [(v10_pred[_dim], 1.0 - _ew), (edu_pred[_dim], _ew)], _cats)
                return result

            m = evaluate(perm_records, dim_fn)
            gap = m[dim_key] - m_v10_perm[dim_key]
            print("    edu_w=%.2f: %s=%.3f (%+.3f) Race=%.3f P20=%.1f%%" % (
                edu_w, dim_name, m[dim_key], gap, m["race"], m["p20"]))

    # ============================================================
    # SIGNAL B: SimplyAnalytics county x industry gender
    # ============================================================
    print("\n" + "=" * 80)
    print("SIGNAL B: SimplyAnalytics County x Industry Gender")
    print("=" * 80)

    print("Loading SimplyAnalytics data...")
    sa_gender = load_simplyanalytics_gender()
    print("  Loaded %d counties" % len(sa_gender))

    # Attach SA gender signal to records
    sa_coverage = 0
    for rec in all_records:
        county = rec["county_fips"]
        naics2 = rec["naics4"][:2] if rec["naics4"] else None
        sa = sa_gender.get(county, {})
        gender = sa.get(naics2) if naics2 else None
        if not gender:
            gender = sa.get("_overall")
        rec["sa_gender"] = gender
        if gender:
            sa_coverage += 1
    print("  SA gender coverage: %d / %d (%.1f%%)" % (
        sa_coverage, len(all_records), 100.0 * sa_coverage / len(all_records)))

    # SA gender standalone
    print("\n--- SA gender standalone accuracy ---")
    def sa_only_fn(rec):
        v10_pred = v10_fn(rec)
        if not v10_pred:
            return None
        sa = rec.get("sa_gender")
        if sa:
            result = dict(v10_pred)
            result["gender"] = sa
            return result
        return v10_pred

    m_sa_perm = evaluate(perm_records, sa_only_fn)
    print("  Perm (SA gender replaces V10 gender):")
    print("    Gender=%.3f (%+.3f vs V10)" % (
        m_sa_perm["gender"], m_sa_perm["gender"] - m_v10_perm["gender"]))

    # Test blending SA gender with V10 gender
    print("\n--- SA gender blended with V10 gender (perm holdout) ---")
    print("  | %-8s | %-10s | %-8s | %-10s |" % (
        "SA Wt", "Gender MAE", "Gap", "Notes"))
    print("  |%s|%s|%s|%s|" % ("-" * 10, "-" * 12, "-" * 10, "-" * 12))

    for sa_w in [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 1.0]:
        def sa_blend_fn(rec, _sw=sa_w):
            v10_pred = v10_fn(rec)
            if not v10_pred:
                return None
            sa = rec.get("sa_gender")
            if sa and _sw > 0:
                result = dict(v10_pred)
                result["gender"] = blend_dicts(
                    [(v10_pred.get("gender"), 1.0 - _sw), (sa, _sw)], GENDER_CATS)
                return result
            return v10_pred

        m = evaluate(perm_records, sa_blend_fn)
        gap = m["gender"] - m_v10_perm["gender"]
        notes = "BASELINE" if sa_w == 0 else ("IMPROVES" if gap < -0.05 else "")
        print("  | %-8.2f | %-10.3f | %-+8.3f | %-10s |" % (
            sa_w, m["gender"], gap, notes))

    # ============================================================
    # SIGNAL C: Combined (best education + best SA gender)
    # ============================================================
    print("\n" + "=" * 80)
    print("SIGNAL C: Combined Education + SA Gender")
    print("=" * 80)

    # Test a grid of combined configs
    print("  Testing education (race+hisp) + SA gender combinations")
    print("  | %-7s | %-7s | %-8s | %-8s | %-10s | %-7s | %-7s |" % (
        "Edu W", "SA W", "Race MAE", "Hisp MAE", "Gender MAE", "P>20pp", "P>30pp"))
    print("  |%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 9, "-" * 9, "-" * 10, "-" * 10, "-" * 12, "-" * 9, "-" * 9))

    combined_results = []
    for edu_w in [0.0, 0.10, 0.20, 0.30]:
        for sa_w in [0.0, 0.30, 0.50, 0.70, 1.0]:
            def combined_fn(rec, _ew=edu_w, _sw=sa_w):
                v10_pred = v10_fn(rec)
                if not v10_pred:
                    return None
                result = {}
                edu_pred = rec.get("edu_signal")

                # Race: V10 + education blend
                if edu_pred and edu_pred.get("race") and _ew > 0:
                    result["race"] = blend_dicts(
                        [(v10_pred.get("race"), 1.0 - _ew), (edu_pred["race"], _ew)],
                        RACE_CATS)
                else:
                    result["race"] = v10_pred.get("race")

                # Hispanic: V10 + education blend
                if edu_pred and edu_pred.get("hispanic") and _ew > 0:
                    result["hispanic"] = blend_dicts(
                        [(v10_pred.get("hispanic"), 1.0 - _ew), (edu_pred["hispanic"], _ew)],
                        HISP_CATS)
                else:
                    result["hispanic"] = v10_pred.get("hispanic")

                # Gender: V10 + SA gender blend
                sa = rec.get("sa_gender")
                if sa and _sw > 0:
                    result["gender"] = blend_dicts(
                        [(v10_pred.get("gender"), 1.0 - _sw), (sa, _sw)], GENDER_CATS)
                else:
                    result["gender"] = v10_pred.get("gender")

                return result

            m = evaluate(perm_records, combined_fn)
            race_gap = m["race"] - m_v10_perm["race"]
            hisp_gap = m["hisp"] - m_v10_perm["hisp"]
            gender_gap = m["gender"] - m_v10_perm["gender"]

            notes = []
            if race_gap < -0.02:
                notes.append("R+")
            if hisp_gap < -0.02:
                notes.append("H+")
            if gender_gap < -0.05:
                notes.append("G+")

            combined_results.append({
                "edu_w": edu_w, "sa_w": sa_w, "metrics": m,
                "gaps": {"race": race_gap, "hisp": hisp_gap, "gender": gender_gap},
            })

            print("  | %-7.2f | %-7.2f | %-8.3f | %-8.3f | %-10.3f | %-6.1f%% | %-6.1f%% | %s" % (
                edu_w, sa_w, m["race"], m["hisp"], m["gender"],
                m["p20"], m["p30"], " ".join(notes)))

    # ============================================================
    # CROSS-VALIDATION ON SEALED HOLDOUT
    # ============================================================
    print("\n" + "=" * 80)
    print("CROSS-VALIDATION: Best configs on V10 SEALED HOLDOUT")
    print("=" * 80)

    # Find top 5 configs by sum of improvements
    for cr in combined_results:
        cr["total_improvement"] = -(cr["gaps"]["race"] + cr["gaps"]["hisp"] + cr["gaps"]["gender"])
    combined_results.sort(key=lambda x: -x["total_improvement"])

    print("\n  Top configs (by total improvement on perm):")
    print("  | %-7s | %-7s | %-10s | %-10s | %-12s | %-12s | %-12s |" % (
        "Edu W", "SA W", "Race (perm)", "Race (seal)", "Hisp (perm)", "Hisp (seal)", "Gender (seal)"))
    print("  |%s|%s|%s|%s|%s|%s|%s|" % (
        "-" * 9, "-" * 9, "-" * 12, "-" * 12, "-" * 14, "-" * 14, "-" * 14))

    for cr in combined_results[:8]:
        edu_w = cr["edu_w"]
        sa_w = cr["sa_w"]

        def sealed_fn(rec, _ew=edu_w, _sw=sa_w):
            v10_pred = v10_fn(rec)
            if not v10_pred:
                return None
            result = {}
            edu_pred = rec.get("edu_signal")

            if edu_pred and edu_pred.get("race") and _ew > 0:
                result["race"] = blend_dicts(
                    [(v10_pred.get("race"), 1.0 - _ew), (edu_pred["race"], _ew)], RACE_CATS)
            else:
                result["race"] = v10_pred.get("race")

            if edu_pred and edu_pred.get("hispanic") and _ew > 0:
                result["hispanic"] = blend_dicts(
                    [(v10_pred.get("hispanic"), 1.0 - _ew), (edu_pred["hispanic"], _ew)], HISP_CATS)
            else:
                result["hispanic"] = v10_pred.get("hispanic")

            sa = rec.get("sa_gender")
            if sa and _sw > 0:
                result["gender"] = blend_dicts(
                    [(v10_pred.get("gender"), 1.0 - _sw), (sa, _sw)], GENDER_CATS)
            else:
                result["gender"] = v10_pred.get("gender")

            return result

        m_seal = evaluate(v10_records, sealed_fn)
        m_perm = cr["metrics"]

        print("  | %-7.2f | %-7.2f | %-10.3f | %-10.3f | %-12.3f | %-12.3f | %-12.3f |" % (
            edu_w, sa_w,
            m_perm["race"], m_seal["race"],
            m_perm["hisp"], m_seal["hisp"],
            m_seal["gender"]))

    # Also show V10 baseline on sealed for reference
    print("\n  V10 baseline sealed: Race=%.3f Hisp=%.3f Gender=%.3f P20=%.1f%% P30=%.1f%%" % (
        m_v10_sealed["race"], m_v10_sealed["hisp"], m_v10_sealed["gender"],
        m_v10_sealed["p20"], m_v10_sealed["p30"]))

    cur.close()
    conn.close()
    print("\nTotal runtime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
