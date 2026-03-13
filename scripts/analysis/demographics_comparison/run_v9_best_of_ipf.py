"""Run the V9 best-of-expert + IPF experiment.

Implements the prompt in `V9_BEST_OF_IPF_TEST_PROMPT.md` using the existing
V5/V6 expert wrappers and the frozen permanent holdout.

Notes:
- The permanent holdout stays fixed from `selected_permanent_holdout_1000.json`.
- The remaining 11,525 companies from `expanded_training_v6.json` are split
  into 10,000 training + 1,525 dev using a fixed seed.
- "IPF" is implemented locally as a simple 2D iterative scaling routine to
  avoid an external dependency for a small, deterministic calculation.
"""
import copy
import json
import math
import os
import random
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from db_config import get_connection
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(__file__))
from cached_loaders_v5 import cached_expert_a, cached_expert_b, cached_method_3c_v5
from cached_loaders_v6 import (
    CachedLoadersV6,
    cached_expert_e,
    cached_expert_g,
    cached_method_v6_full,
)
from classifiers import classify_naics_group
from config import (
    REGIONAL_CALIBRATION_INDUSTRIES,
    REGIONAL_CAL_MIN_N,
    get_census_region,
    get_county_minority_tier,
)
from eeo1_parser import load_all_eeo1_data, parse_eeo1_row
from methodologies import _blend_dicts
from methodologies_v5 import RACE_CATS
from methodologies_v5 import apply_floor, smoothed_ipf
from methodologies_v6 import get_gender_blend_weight

SCRIPT_DIR = os.path.dirname(__file__)
HISP_CATS = ["Hispanic", "Not Hispanic"]
GENDER_CATS = ["Male", "Female"]
EXPERT_ORDER = ["A", "B", "D", "E", "F", "G", "V6-Full"]
BASE_EXPERTS = {
    "A": lambda cl, n4, sf, cf, **kw: cached_expert_a(cl, n4, sf, cf),
    "B": lambda cl, n4, sf, cf, **kw: cached_expert_b(cl, n4, sf, cf, zipcode=kw.get("zipcode", "")),
    "D": lambda cl, n4, sf, cf, **kw: cached_method_3c_v5(cl, n4, sf, cf),
    "E": lambda cl, n4, sf, cf, **kw: cached_expert_e(cl, n4, sf, cf, **kw),
    "G": lambda cl, n4, sf, cf, **kw: cached_expert_g(cl, n4, sf, cf, **kw),
    "V6-Full": lambda cl, n4, sf, cf, **kw: cached_method_v6_full(cl, n4, sf, cf, **kw),
}
SPLIT_SEED = 20260311
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "v9_best_of_ipf_results.json")
DEV_HOLDOUT_JSON = os.path.join(SCRIPT_DIR, "dev_holdout_1500.json")
PREDICTION_CHECKPOINT_JSON = os.path.join(SCRIPT_DIR, "v9_best_of_ipf_prediction_checkpoint.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class FastExpertF:
    """Bulk-loaded implementation of Expert F's occupation-weighted race path."""

    def __init__(self, cl, companies):
        self.cl = cl
        self.occ_mix_by_naics4 = {}
        self.occ_race_by_naics_state = {}
        self._prepare(companies)

    def _prepare(self, companies):
        naics4_values = sorted({(c.get("naics") or "")[:4] for c in companies if c.get("naics")})
        states = sorted({c.get("state_fips", "") for c in companies if c.get("state_fips")})
        soc_variants = set()

        for naics4 in naics4_values:
            occ_mix = self.cl.get_occupation_mix(naics4) or []
            self.occ_mix_by_naics4[naics4] = occ_mix
            for soc_code, _ in occ_mix[:30]:
                soc_variants.add(soc_code)
                soc_variants.add(soc_code.replace("-", ""))

        if not soc_variants or not states:
            return

        self.cl.cur.execute(
            """
            SELECT soc_code, state_fips, race, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE soc_code = ANY(%s)
              AND state_fips = ANY(%s)
              AND hispanic = '0'
              AND race IN ('1','2','3','4','5','6','7','8','9')
            GROUP BY soc_code, state_fips, race
            """,
            [list(soc_variants), states],
        )
        rows = self.cl.cur.fetchall()

        grouped = defaultdict(dict)
        for row in rows:
            soc = str(row["soc_code"]).replace("-", "")
            grouped[(soc, row["state_fips"])][row["race"]] = float(row["w"])

        for (soc, state_fips), race_rows in grouped.items():
            total = sum(race_rows.values())
            if total <= 0:
                continue
            asian = race_rows.get("4", 0.0) + race_rows.get("5", 0.0)
            two_plus = (
                race_rows.get("6", 0.0)
                + race_rows.get("7", 0.0)
                + race_rows.get("8", 0.0)
                + race_rows.get("9", 0.0)
            )
            self.occ_race_by_naics_state[(soc, state_fips)] = {
                "White": round(100.0 * race_rows.get("1", 0.0) / total, 2),
                "Black": round(100.0 * race_rows.get("2", 0.0) / total, 2),
                "Asian": round(100.0 * asian / total, 2),
                "AIAN": round(100.0 * race_rows.get("3", 0.0) / total, 2),
                "NHOPI": 0.0,
                "Two+": round(100.0 * two_plus / total, 2),
            }

    def _occ_weighted_race(self, naics4, state_fips):
        occ_mix = self.occ_mix_by_naics4.get(naics4) or []
        if not occ_mix:
            return None
        weighted = {cat: 0.0 for cat in RACE_CATS}
        total_weight = 0.0
        for soc_code, pct_of_industry in occ_mix[:30]:
            demo = self.occ_race_by_naics_state.get((soc_code.replace("-", ""), state_fips))
            if not demo:
                continue
            for cat in RACE_CATS:
                weighted[cat] += demo.get(cat, 0.0) * pct_of_industry
            total_weight += pct_of_industry
        if total_weight <= 0:
            return None
        return {cat: round(weighted[cat] / total_weight, 2) for cat in RACE_CATS}

    def predict(self, naics4, state_fips, county_fips, cbsa_code=""):
        occ_race = self._occ_weighted_race(naics4, state_fips)
        lodes_race = self.cl.get_lodes_race(county_fips)
        if occ_race:
            race_result = smoothed_ipf(occ_race, lodes_race, RACE_CATS)
        else:
            race_data, _ = self.cl.get_pums_or_acs_race(naics4, state_fips, county_fips)
            race_result = smoothed_ipf(race_data, lodes_race, RACE_CATS)
        if race_result:
            race_result = apply_floor(race_result)

        occ_gender = self.cl.get_occupation_weighted_gender(naics4, cbsa_code)
        acs_gender = self.cl.get_acs_gender(naics4, state_fips)
        lodes_gender = self.cl.get_lodes_gender(county_fips)
        ipf_gender = smoothed_ipf(acs_gender, lodes_gender, GENDER_CATS)

        if occ_gender is not None and ipf_gender is not None:
            bls_weight = get_gender_blend_weight(naics4[:2])
            ipf_weight = 1.0 - bls_weight
            gender_result = _blend_dicts(
                [(occ_gender, bls_weight), (ipf_gender, ipf_weight)],
                GENDER_CATS,
            )
        else:
            gender_result = ipf_gender

        hisp_result = smoothed_ipf(
            self.cl.get_acs_hispanic(naics4, state_fips),
            self.cl.get_lodes_hispanic(county_fips),
            HISP_CATS,
        )

        return {
            "race": race_result,
            "hispanic": hisp_result,
            "gender": gender_result,
            "_expert": "F",
            "_impl": "fast_bulk",
        }


def build_truth_lookup():
    eeo1_rows = load_all_eeo1_data()
    by_code_year = {}
    by_code = defaultdict(list)
    for row in eeo1_rows:
        code = (row.get("COMPANY") or "").strip()
        year = int(float(row.get("YEAR", 0) or 0))
        if not code:
            continue
        parsed = parse_eeo1_row(row)
        if not parsed:
            continue
        by_code_year[(code, year)] = parsed
        by_code[code].append(parsed)
    for code in by_code:
        by_code[code].sort(key=lambda r: r.get("year", 0), reverse=True)
    return by_code_year, by_code


def get_truth(company, by_code_year, by_code):
    code = company["company_code"]
    year = company.get("year")
    truth = by_code_year.get((code, year))
    if truth:
        return truth
    vals = by_code.get(code, [])
    return vals[0] if vals else None


def abs_err(pred, actual, cat):
    if not pred or not actual or cat not in pred or cat not in actual:
        return None
    return abs(pred[cat] - actual[cat])


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def mae_dict(pred, actual, cats):
    vals = [abs_err(pred, actual, cat) for cat in cats]
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def max_cat_error(pred, actual, cats):
    vals = [abs_err(pred, actual, cat) for cat in cats]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def signed_bias(preds, actuals, cats):
    out = {}
    for cat in cats:
        errs = []
        for pred, actual in zip(preds, actuals):
            if pred and actual and cat in pred and cat in actual:
                errs.append(pred[cat] - actual[cat])
        out[cat] = sum(errs) / len(errs) if errs else None
    return out


def mean_abs_bias(preds, actuals, cats):
    biases = signed_bias(preds, actuals, cats)
    vals = [abs(v) for v in biases.values() if v is not None]
    return sum(vals) / len(vals) if vals else None


def normalize_race(raw_race):
    if not raw_race:
        return None
    total = sum(raw_race.get(cat, 0.0) for cat in RACE_CATS)
    if total <= 0:
        return None
    return {cat: round(raw_race.get(cat, 0.0) * 100.0 / total, 4) for cat in RACE_CATS}


def build_seed_matrix(cl, record):
    race_seed, race_source = cl.get_pums_or_acs_race(
        record["naics4"], record["state_fips"], record["county_fips"]
    )
    gender_seed = cl.get_lodes_gender(record["county_fips"]) or cl.get_acs_gender(
        record["naics4"], record["state_fips"]
    )
    if not race_seed:
        race_seed = {cat: 100.0 / len(RACE_CATS) for cat in RACE_CATS}
    if not gender_seed:
        gender_seed = {"Male": 50.0, "Female": 50.0}

    male = max(gender_seed.get("Male", 50.0), 0.00001)
    female = max(gender_seed.get("Female", 50.0), 0.00001)
    g_total = male + female
    male /= g_total
    female /= g_total

    race_total = sum(max(race_seed.get(cat, 0.0), 0.00001) for cat in RACE_CATS)
    matrix = []
    for cat in RACE_CATS:
        row = max(race_seed.get(cat, 0.0), 0.00001) / race_total
        matrix.append([row * male, row * female])
    return matrix, race_source or "acs_industry_x_lodes_gender_independence"


def adjust_seed_with_abs(seed_matrix, abs_share, abs_median):
    adjusted = [row[:] for row in seed_matrix]
    if abs_share is None or abs_share <= abs_median:
        return adjusted, False, 1.0
    boost = 1.0 + (abs_share - abs_median) * 0.5 / 100.0
    for idx in range(1, len(adjusted)):
        adjusted[idx][0] *= boost
        adjusted[idx][1] *= boost
    total = sum(sum(row) for row in adjusted)
    if total > 0:
        adjusted = [[cell / total for cell in row] for row in adjusted]
    return adjusted, True, boost


def ipf_2d(seed_matrix, row_margins, col_margins, eps=1e-4, max_iter=50):
    matrix = [[max(cell, 0.00001) for cell in row] for row in seed_matrix]
    total = sum(sum(row) for row in matrix)
    matrix = [[cell / total for cell in row] for row in matrix]

    row_margins = [max(v, 0.00001) for v in row_margins]
    r_total = sum(row_margins)
    row_margins = [v / r_total for v in row_margins]

    col_margins = [max(v, 0.00001) for v in col_margins]
    c_total = sum(col_margins)
    col_margins = [v / c_total for v in col_margins]

    final_change = None
    converged = False
    iterations = 0

    for iteration in range(1, max_iter + 1):
        prev = [row[:] for row in matrix]

        for i, target in enumerate(row_margins):
            row_sum = sum(matrix[i])
            factor = target / row_sum if row_sum > 0 else 1.0
            matrix[i][0] *= factor
            matrix[i][1] *= factor

        for j, target in enumerate(col_margins):
            col_sum = sum(matrix[i][j] for i in range(len(matrix)))
            factor = target / col_sum if col_sum > 0 else 1.0
            for i in range(len(matrix)):
                matrix[i][j] *= factor

        final_change = max(
            abs(matrix[i][j] - prev[i][j]) for i in range(len(matrix)) for j in range(2)
        )
        iterations = iteration
        if final_change < eps:
            converged = True
            break

    return {
        "matrix": matrix,
        "iterations": iterations,
        "final_change": final_change,
        "converged": converged,
    }


def matrix_to_output(result):
    matrix = result["matrix"]
    race = {cat: round(sum(matrix[idx]) * 100.0, 4) for idx, cat in enumerate(RACE_CATS)}
    gender = {
        "Male": round(sum(matrix[idx][0] for idx in range(len(RACE_CATS))) * 100.0, 4),
        "Female": round(sum(matrix[idx][1] for idx in range(len(RACE_CATS))) * 100.0, 4),
    }
    return race, gender


def serialize_matrix(matrix):
    return [[round(cell * 100.0, 4) for cell in row] for row in matrix]


def evaluate_scenario(records, scenario_func):
    preds_race = []
    actuals_race = []
    preds_hisp = []
    actuals_hisp = []
    preds_gender = []
    actuals_gender = []
    race_maes = []
    black_maes = []
    gender_maes = []
    hisp_maes = []
    max_errors = []

    for rec in records:
        pred = scenario_func(rec)
        if not pred:
            continue
        race_pred = pred.get("race")
        race_actual = rec["truth"]["race"]
        race_mae = mae_dict(race_pred, race_actual, RACE_CATS)
        if race_mae is not None:
            race_maes.append(race_mae)
            preds_race.append(race_pred)
            actuals_race.append(race_actual)
            mx = max_cat_error(race_pred, race_actual, RACE_CATS)
            if mx is not None:
                max_errors.append(mx)
            b_mae = abs_err(race_pred, race_actual, "Black")
            if b_mae is not None:
                black_maes.append(b_mae)

        hisp_pred = pred.get("hispanic")
        hisp_actual = rec["truth"]["hispanic"]
        hisp_mae = mae_dict(hisp_pred, hisp_actual, HISP_CATS)
        if hisp_mae is not None:
            hisp_maes.append(hisp_mae)
            preds_hisp.append(hisp_pred)
            actuals_hisp.append(hisp_actual)

        gender_pred = pred.get("gender")
        gender_actual = rec["truth"]["gender"]
        g_mae = mae_dict(gender_pred, gender_actual, GENDER_CATS)
        if g_mae is not None:
            gender_maes.append(g_mae)
            preds_gender.append(gender_pred)
            actuals_gender.append(gender_actual)

    return {
        "n": len(race_maes),
        "race_mae": mean(race_maes),
        "black_mae": mean(black_maes),
        "hisp_mae": mean(hisp_maes),
        "gender_mae": mean(gender_maes),
        "p_gt_20pp": (sum(1 for e in max_errors if e > 20.0) / len(max_errors) * 100.0) if max_errors else None,
        "p_gt_30pp": (sum(1 for e in max_errors if e > 30.0) / len(max_errors) * 100.0) if max_errors else None,
        "abs_bias": mean_abs_bias(preds_race, actuals_race, RACE_CATS),
    }


def breakdown_race_mae(records, scenario_func, key_name, key_values):
    out = {}
    for key in key_values:
        subset = [rec for rec in records if rec.get(key_name) == key]
        metric = evaluate_scenario(subset, scenario_func)
        out[key] = metric["race_mae"]
    return out


def healthcare_south_tail(records, scenario_func):
    subset = [
        rec for rec in records
        if rec["naics_group"] == "Healthcare/Social (62)" and rec["region"] == "South"
    ]
    max_errors = []
    for rec in subset:
        pred = scenario_func(rec)
        if not pred or not pred.get("race"):
            continue
        mx = max_cat_error(pred["race"], rec["truth"]["race"], RACE_CATS)
        if mx is not None:
            max_errors.append(mx)
    n = len(max_errors)
    return {
        "count": n,
        "p_gt_20pp": (sum(1 for e in max_errors if e > 20.0) / n * 100.0) if n else None,
        "p_gt_30pp": (sum(1 for e in max_errors if e > 30.0) / n * 100.0) if n else None,
    }


def train_category_winners(train_records):
    winner_table = {}
    failure_counts = {}
    overall_tail = {}

    for expert in EXPERT_ORDER:
        failures = 0
        max_errors = []
        for rec in train_records:
            pred = rec["expert_preds"].get(expert)
            if not pred or not pred.get("race") or not pred.get("hispanic") or not pred.get("gender"):
                failures += 1
                continue
            mx = max_cat_error(pred["race"], rec["truth"]["race"], RACE_CATS)
            if mx is not None:
                max_errors.append(mx)
        failure_counts[expert] = failures
        overall_tail[expert] = {
            "p_gt_20pp": (sum(1 for e in max_errors if e > 20.0) / len(max_errors) * 100.0) if max_errors else None,
            "p_gt_30pp": (sum(1 for e in max_errors if e > 30.0) / len(max_errors) * 100.0) if max_errors else None,
            "failures": failures,
        }

    row_specs = [
        ("White", "race", "White"),
        ("Black", "race", "Black"),
        ("Asian", "race", "Asian"),
        ("Hispanic", "hispanic", "Hispanic"),
        ("Female", "gender", "Female"),
        ("Two+", "race", "Two+"),
        ("AIAN", "race", "AIAN"),
        ("NHOPI", "race", "NHOPI"),
    ]

    for row_label, dim, cat in row_specs:
        maes = {}
        for expert in EXPERT_ORDER:
            errs = []
            for rec in train_records:
                pred = rec["expert_preds"].get(expert)
                if not pred or not pred.get(dim):
                    continue
                err = abs_err(pred[dim], rec["truth"][dim], cat)
                if err is not None:
                    errs.append(err)
            maes[expert] = mean(errs)

        ranked = [(exp, mae) for exp, mae in maes.items() if mae is not None]
        ranked.sort(key=lambda item: item[1])
        winner = ranked[0][0] if ranked else None
        winner_gap = None
        flagged_close = False
        if len(ranked) >= 2:
            winner_gap = ranked[1][1] - ranked[0][1]
            flagged_close = winner_gap < 0.1
        winner_table[row_label] = {
            "mae_by_expert": maes,
            "winner": winner,
            "ranked_experts": [exp for exp, _ in ranked],
            "runner_up_gap": winner_gap,
            "close_flag": flagged_close,
        }

    return winner_table, overall_tail


def assemble_best_of(record, winners):
    fallback_counts = {}
    race_raw = {}
    for cat in RACE_CATS:
        race_raw[cat] = 0.0
        for exp in winners[cat].get("ranked_experts", []):
            pred = record["expert_preds"].get(exp)
            race_pred = pred.get("race") if pred else None
            if race_pred and cat in race_pred:
                race_raw[cat] = race_pred.get(cat, 0.0)
                if exp != winners[cat]["winner"]:
                    fallback_counts[cat] = exp
                break

    hisp_pred = None
    for exp in winners["Hispanic"].get("ranked_experts", []):
        pred = record["expert_preds"].get(exp)
        dim_pred = pred.get("hispanic") if pred else None
        if dim_pred:
            hisp_pred = copy.deepcopy(dim_pred)
            if exp != winners["Hispanic"]["winner"]:
                fallback_counts["Hispanic"] = exp
            break

    gender_pred = None
    for exp in winners["Female"].get("ranked_experts", []):
        pred = record["expert_preds"].get(exp)
        dim_pred = pred.get("gender") if pred else None
        if dim_pred:
            gender_pred = copy.deepcopy(dim_pred)
            if exp != winners["Female"]["winner"]:
                fallback_counts["Female"] = exp
            break

    normalized_race = normalize_race(race_raw)

    return {
        "race_raw": race_raw,
        "race": normalized_race,
        "hispanic": hisp_pred,
        "gender": gender_pred,
        "fallbacks": fallback_counts,
    }


def attach_best_of_and_ipf(records, winners, cl, abs_median):
    for rec in records:
        best_of = assemble_best_of(rec, winners)
        rec["best_of"] = best_of

        seed_matrix, seed_source = build_seed_matrix(cl, rec)
        rec["ipf_seed_source"] = seed_source

        race = best_of.get("race")
        gender = best_of.get("gender")
        if race and gender:
            row_margins = [race.get(cat, 0.0) / 100.0 for cat in RACE_CATS]
            col_margins = [
                gender.get("Male", 50.0) / 100.0,
                gender.get("Female", 50.0) / 100.0,
            ]
            ipf_result = ipf_2d(seed_matrix, row_margins, col_margins)
            ipf_race, ipf_gender = matrix_to_output(ipf_result)
            rec["best_of_ipf"] = {
                "race": ipf_race,
                "gender": ipf_gender,
                "hispanic": copy.deepcopy(best_of.get("hispanic")),
                "ipf_meta": {
                    "seed_matrix": serialize_matrix(seed_matrix),
                    "output_matrix": serialize_matrix(ipf_result["matrix"]),
                    "iterations": ipf_result["iterations"],
                    "final_change": ipf_result["final_change"],
                    "converged": ipf_result["converged"],
                },
            }
        else:
            rec["best_of_ipf"] = None

        abs_info = cl.get_abs_owner_density(rec["county_fips"])
        abs_share = None
        if isinstance(abs_info, dict):
            abs_share = abs_info.get("minority_share")
        rec["abs_minority_share"] = abs_share

        if race and gender:
            adj_seed, abs_applied, abs_boost = adjust_seed_with_abs(seed_matrix, abs_share, abs_median)
            ipf_abs_result = ipf_2d(adj_seed, row_margins, col_margins)
            ipf_abs_race, ipf_abs_gender = matrix_to_output(ipf_abs_result)
            rec["best_of_ipf_abs"] = {
                "race": ipf_abs_race,
                "gender": ipf_abs_gender,
                "hispanic": copy.deepcopy(best_of.get("hispanic")),
                "ipf_meta": {
                    "seed_matrix": serialize_matrix(adj_seed),
                    "output_matrix": serialize_matrix(ipf_abs_result["matrix"]),
                    "iterations": ipf_abs_result["iterations"],
                    "final_change": ipf_abs_result["final_change"],
                    "converged": ipf_abs_result["converged"],
                    "abs_applied": abs_applied,
                    "abs_boost": abs_boost,
                },
            }
        else:
            rec["best_of_ipf_abs"] = None


def category_winner_map(winner_table):
    out = {}
    for cat in ["White", "Black", "Asian", "AIAN", "NHOPI", "Two+", "Hispanic", "Female"]:
        out[cat] = winner_table[cat]
    return out


def scenario_d_solo(rec):
    return rec["expert_preds"].get("D")


def scenario_best_of(rec):
    return {
        "race": rec["best_of"]["race"],
        "hispanic": rec["best_of"]["hispanic"],
        "gender": rec["best_of"]["gender"],
    }


def scenario_best_of_ipf(rec):
    return rec.get("best_of_ipf")


def scenario_best_of_ipf_abs(rec):
    return rec.get("best_of_ipf_abs")


def split_records(all_records, train_codes, dev_codes, perm_codes):
    train_records, dev_records, perm_records = [], [], []
    for rec in all_records:
        code = rec["company_code"]
        if code in train_codes:
            train_records.append(rec)
        elif code in dev_codes:
            dev_records.append(rec)
        elif code in perm_codes:
            perm_records.append(rec)
    return train_records, dev_records, perm_records


def build_splits():
    perm_data = load_json(os.path.join(SCRIPT_DIR, "selected_permanent_holdout_1000.json"))
    perm_companies = perm_data["companies"] if isinstance(perm_data, dict) else perm_data
    perm_codes = {c["company_code"] for c in perm_companies}

    pool = load_json(os.path.join(SCRIPT_DIR, "expanded_training_v6.json"))
    non_perm_pool = [c for c in pool if c["company_code"] not in perm_codes]

    rng = random.Random(SPLIT_SEED)
    shuffled = non_perm_pool[:]
    rng.shuffle(shuffled)
    train = shuffled[:10000]
    dev = shuffled[10000:]

    dev_payload = {
        "description": "V9 dev holdout split created from expanded_training_v6.json after excluding the frozen permanent holdout",
        "seed": SPLIT_SEED,
        "n_companies": len(dev),
        "company_codes": [c["company_code"] for c in dev],
    }
    save_json(DEV_HOLDOUT_JSON, dev_payload)

    return {
        "perm_companies": perm_companies,
        "perm_codes": perm_codes,
        "train_companies": train,
        "train_codes": {c["company_code"] for c in train},
        "dev_companies": dev,
        "dev_codes": {c["company_code"] for c in dev},
    }


def verify_no_overlap(splits):
    train_codes = splits["train_codes"]
    dev_codes = splits["dev_codes"]
    perm_codes = splits["perm_codes"]
    return {
        "train_dev": len(train_codes & dev_codes),
        "train_perm": len(train_codes & perm_codes),
        "dev_perm": len(dev_codes & perm_codes),
    }


def pick_example_ids(companies, n=5):
    return [c["company_code"] for c in companies[:n]]


def make_summary_table_records(records, scenario_func):
    return {
        "metrics": evaluate_scenario(records, scenario_func),
        "regions": breakdown_race_mae(
            records,
            scenario_func,
            "region",
            ["South", "West", "Northeast", "Midwest"],
        ),
        "sectors": breakdown_race_mae(
            records,
            scenario_func,
            "naics_group",
            ["Healthcare/Social (62)", "Admin/Staffing (56)", "Finance/Insurance (52)"],
        ),
        "healthcare_south": healthcare_south_tail(records, scenario_func),
    }


def main():
    t0 = time.time()
    print("RUN V9 BEST-OF + IPF")
    print("=" * 80)

    splits = build_splits()
    overlap = verify_no_overlap(splits)

    all_companies = splits["train_companies"] + splits["dev_companies"] + splits["perm_companies"]
    print("Training: %d | Dev: %d | Permanent: %d | Total: %d" % (
        len(splits["train_companies"]),
        len(splits["dev_companies"]),
        len(splits["perm_companies"]),
        len(all_companies),
    ))

    by_code_year, by_code = build_truth_lookup()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cl = CachedLoadersV6(cur)
    fast_f = FastExpertF(cl, all_companies)
    expert_cache = {}
    experts = dict(BASE_EXPERTS)
    experts["F"] = lambda cl, n4, sf, cf, **kw: fast_f.predict(n4, sf, cf, cbsa_code=kw.get("cbsa_code", ""))

    all_records = []
    abs_values = []
    if os.path.exists(PREDICTION_CHECKPOINT_JSON):
        checkpoint = load_json(PREDICTION_CHECKPOINT_JSON)
        all_records = checkpoint.get("all_records", [])
        abs_values = checkpoint.get("abs_values", [])
        print("Loaded prediction checkpoint: %s (%d records)" % (
            PREDICTION_CHECKPOINT_JSON, len(all_records)))
    else:
        for idx, company in enumerate(all_companies, 1):
            if idx % 250 == 0:
                print("  %d/%d companies (%.0fs)" % (idx, len(all_companies), time.time() - t0))

            truth = get_truth(company, by_code_year, by_code)
            if not truth or not truth.get("race"):
                continue

            naics = company.get("naics", "")
            naics4 = naics[:4]
            county_fips = company.get("county_fips", "")
            state_fips = company.get("state_fips", "")
            zipcode = company.get("zipcode", "")
            state = company.get("state", "")
            naics_group = company.get("classifications", {}).get("naics_group") or classify_naics_group(naics4)
            region = company.get("classifications", {}).get("region") or get_census_region(state)
            cbsa_code = cl.get_county_cbsa(county_fips) or ""
            lodes_race = cl.get_lodes_race(county_fips)
            county_minority_pct = (100.0 - lodes_race.get("White", 0.0)) if lodes_race else None
            county_tier = get_county_minority_tier(county_minority_pct)

            expert_preds = {}
            for expert_name, expert_fn in experts.items():
                cache_key = (
                    expert_name,
                    naics4,
                    state_fips,
                    county_fips,
                    zipcode,
                    naics_group,
                    cbsa_code,
                )
                if cache_key in expert_cache:
                    result = expert_cache[cache_key]
                    if result:
                        expert_preds[expert_name] = result
                    continue
                try:
                    result = expert_fn(
                        cl,
                        naics4,
                        state_fips,
                        county_fips,
                        cbsa_code=cbsa_code,
                        zipcode=zipcode,
                        naics_group=naics_group,
                    )
                except Exception:
                    result = None
                expert_cache[cache_key] = result
                if result:
                    expert_preds[expert_name] = result

            abs_info = cl.get_abs_owner_density(county_fips)
            if isinstance(abs_info, dict) and abs_info.get("minority_share") is not None:
                abs_values.append(abs_info["minority_share"])

            all_records.append({
                "company_code": company["company_code"],
                "name": company.get("name"),
                "year": company.get("year"),
                "naics4": naics4,
                "naics_group": naics_group,
                "region": region,
                "county_tier": county_tier,
                "county_fips": county_fips,
                "state_fips": state_fips,
                "state": state,
                "zipcode": zipcode,
                "truth": truth,
                "expert_preds": expert_preds,
            })

        save_json(PREDICTION_CHECKPOINT_JSON, {
            "split_seed": SPLIT_SEED,
            "n_records": len(all_records),
            "abs_values": abs_values,
            "all_records": all_records,
        })
        print("Saved prediction checkpoint: %s" % PREDICTION_CHECKPOINT_JSON)

    abs_values = sorted(abs_values)
    abs_median = abs_values[len(abs_values) // 2] if abs_values else None

    train_records, dev_records, perm_records = split_records(
        all_records,
        splits["train_codes"],
        splits["dev_codes"],
        splits["perm_codes"],
    )
    all_holdout_records = dev_records + perm_records

    winner_table, overall_tail = train_category_winners(train_records)
    winners = category_winner_map(winner_table)
    attach_best_of_and_ipf(all_records, winners, cl, abs_median)

    scorecards = {
        "all_2525": {
            "D_solo": make_summary_table_records(all_holdout_records, scenario_d_solo),
            "best_of_naive": make_summary_table_records(all_holdout_records, scenario_best_of),
            "best_of_ipf": make_summary_table_records(all_holdout_records, scenario_best_of_ipf),
            "best_of_ipf_abs": make_summary_table_records(all_holdout_records, scenario_best_of_ipf_abs),
        },
        "dev_1525": {
            "D_solo": make_summary_table_records(dev_records, scenario_d_solo),
            "best_of_naive": make_summary_table_records(dev_records, scenario_best_of),
            "best_of_ipf": make_summary_table_records(dev_records, scenario_best_of_ipf),
            "best_of_ipf_abs": make_summary_table_records(dev_records, scenario_best_of_ipf_abs),
        },
        "perm_1000": {
            "D_solo": make_summary_table_records(perm_records, scenario_d_solo),
            "best_of_naive": make_summary_table_records(perm_records, scenario_best_of),
            "best_of_ipf": make_summary_table_records(perm_records, scenario_best_of_ipf),
            "best_of_ipf_abs": make_summary_table_records(perm_records, scenario_best_of_ipf_abs),
        },
    }

    ipf_examples = []
    for rec in all_holdout_records[:5]:
        if rec.get("best_of_ipf"):
            ipf_examples.append({
                "company_code": rec["company_code"],
                "name": rec["name"],
                "naics_group": rec["naics_group"],
                "region": rec["region"],
                "best_of_raw_race": rec["best_of"]["race_raw"],
                "best_of_normalized_race": rec["best_of"]["race"],
                "best_of_gender": rec["best_of"]["gender"],
                "seed_source": rec["ipf_seed_source"],
                "seed_matrix_pct": rec["best_of_ipf"]["ipf_meta"]["seed_matrix"],
                "output_matrix_pct": rec["best_of_ipf"]["ipf_meta"]["output_matrix"],
                "iterations": rec["best_of_ipf"]["ipf_meta"]["iterations"],
                "final_change": rec["best_of_ipf"]["ipf_meta"]["final_change"],
                "converged": rec["best_of_ipf"]["ipf_meta"]["converged"],
                "race_sum": round(sum(rec["best_of_ipf"]["race"].values()), 4),
                "gender_sum": round(sum(rec["best_of_ipf"]["gender"].values()), 4),
            })
        if len(ipf_examples) >= 5:
            break

    abs_examples = []
    high_abs_recs = [
        rec for rec in all_holdout_records
        if rec.get("abs_minority_share") is not None and abs_median is not None and rec["abs_minority_share"] > abs_median
    ]
    for rec in high_abs_recs[:5]:
        abs_examples.append({
            "company_code": rec["company_code"],
            "name": rec["name"],
            "naics_group": rec["naics_group"],
            "region": rec["region"],
            "abs_minority_share": rec["abs_minority_share"],
            "median_abs_minority_share": abs_median,
            "ipf_matrix_pct": rec["best_of_ipf"]["ipf_meta"]["output_matrix"] if rec.get("best_of_ipf") else None,
            "ipf_abs_matrix_pct": rec["best_of_ipf_abs"]["ipf_meta"]["output_matrix"] if rec.get("best_of_ipf_abs") else None,
        })

    stop_gate = {
        "baseline_d_solo_all_2525": scorecards["all_2525"]["D_solo"]["healthcare_south"],
        "best_of_ipf_all_2525": scorecards["all_2525"]["best_of_ipf"]["healthcare_south"],
    }
    stop_gate["passes"] = bool(
        stop_gate["baseline_d_solo_all_2525"]["count"]
        and stop_gate["best_of_ipf_all_2525"]["count"]
        and stop_gate["best_of_ipf_all_2525"]["p_gt_20pp"] < stop_gate["baseline_d_solo_all_2525"]["p_gt_20pp"]
        and stop_gate["best_of_ipf_all_2525"]["p_gt_30pp"] < stop_gate["baseline_d_solo_all_2525"]["p_gt_30pp"]
    )

    result = {
        "run_date": "2026-03-11",
        "split_seed": SPLIT_SEED,
        "split_summary": {
            "training": len(splits["train_companies"]),
            "dev": len(splits["dev_companies"]),
            "permanent": len(splits["perm_companies"]),
            "total": len(all_companies),
            "overlap_check": overlap,
            "samples": {
                "training": pick_example_ids(splits["train_companies"]),
                "dev": pick_example_ids(splits["dev_companies"]),
                "permanent": pick_example_ids(splits["perm_companies"]),
            },
        },
        "winner_table": winner_table,
        "training_expert_tail": overall_tail,
        "winners_used": {k: v["winner"] for k, v in winners.items()},
        "abs_median": abs_median,
        "scorecards_precal": scorecards,
        "ipf_examples": ipf_examples,
        "abs_examples": abs_examples,
        "stop_gate": stop_gate,
        "notes": [
            "Dev holdout file name follows the prompt, but the exact leftover size is 1,525, not 1,500.",
            "The 2D IPF fallback seed uses industry-state race proportions x county gender proportions under independence because a direct race x gender cross-tab loader is not present in the current pipeline.",
            "With race row margins constrained to the normalized best-of race vector, IPF preserves the same race marginals as naive normalization.",
        ],
    }

    save_json(OUTPUT_JSON, result)

    print("")
    print("Saved results:")
    print("  %s" % OUTPUT_JSON)
    print("  %s" % DEV_HOLDOUT_JSON)
    print("")
    print("Winners: %s" % result["winners_used"])
    print("Stop gate passes: %s" % result["stop_gate"]["passes"])
    print("Runtime: %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
