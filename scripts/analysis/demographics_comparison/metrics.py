"""Comparison metrics for demographics estimation.

All metrics operate on two dicts with matching keys (category -> percentage).
Percentages should sum to ~100.
"""
import math


def mae(estimated, actual):
    """Mean Absolute Error across categories.

    Args:
        estimated: dict {category: pct}
        actual: dict {category: pct}
    Returns:
        float: average |est - actual| across shared categories
    """
    keys = set(estimated.keys()) & set(actual.keys())
    if not keys:
        return None
    return sum(abs(estimated[k] - actual[k]) for k in keys) / len(keys)


def rmse(estimated, actual):
    """Root Mean Square Error across categories."""
    keys = set(estimated.keys()) & set(actual.keys())
    if not keys:
        return None
    return math.sqrt(sum((estimated[k] - actual[k]) ** 2 for k in keys) / len(keys))


def hellinger_distance(estimated, actual):
    """Hellinger distance between two distributions.

    Range [0, 1]. 0 = identical distributions.
    Inputs are percentages (0-100).
    """
    keys = set(estimated.keys()) & set(actual.keys())
    if not keys:
        return None
    # Convert percentages to proportions
    est_total = sum(estimated[k] for k in keys)
    act_total = sum(actual[k] for k in keys)
    if est_total == 0 or act_total == 0:
        return 1.0

    sq_sum = 0.0
    for k in keys:
        p = estimated[k] / est_total
        q = actual[k] / act_total
        sq_sum += (math.sqrt(p) - math.sqrt(q)) ** 2

    return math.sqrt(0.5 * sq_sum)


def max_absolute_error(estimated, actual):
    """Worst-case category error.

    Returns (max_error, category_name).
    """
    keys = set(estimated.keys()) & set(actual.keys())
    if not keys:
        return None, None
    errors = {k: estimated[k] - actual[k] for k in keys}
    worst_key = max(errors, key=lambda k: abs(errors[k]))
    return abs(errors[worst_key]), worst_key


def signed_errors(estimated, actual):
    """Per-category signed error (positive = overestimate).

    Returns dict {category: signed_error}.
    """
    keys = set(estimated.keys()) & set(actual.keys())
    return {k: round(estimated[k] - actual[k], 2) for k in sorted(keys)}


def compute_all_metrics(estimated, actual):
    """Compute all metrics for a single dimension.

    Returns dict with mae, rmse, hellinger, max_error, max_error_cat, signed.
    """
    max_err, max_cat = max_absolute_error(estimated, actual)
    return {
        'mae': round(mae(estimated, actual), 2) if mae(estimated, actual) is not None else None,
        'rmse': round(rmse(estimated, actual), 3) if rmse(estimated, actual) is not None else None,
        'hellinger': round(hellinger_distance(estimated, actual), 4) if hellinger_distance(estimated, actual) is not None else None,
        'max_error': round(max_err, 2) if max_err is not None else None,
        'max_error_cat': max_cat,
        'signed': signed_errors(estimated, actual),
    }


def composite_score(method_preds, method_actuals, cat_cols=None):
    """Composite score combining MAE + tail risk + bias.

    Composite = MAE + 0.20*P(>20pp)*100 + 0.35*P(>30pp)*100 + 0.15*mean_abs_signed_bias

    Args:
        method_preds: list of dicts {category: pct} -- one per company
        method_actuals: list of dicts {category: pct} -- matching ground truth
        cat_cols: list of category keys (default: RACE_CATEGORIES)

    Returns:
        dict with composite, avg_mae, p_gt_20pp, p_gt_30pp, mean_abs_bias
    """
    if cat_cols is None:
        cat_cols = ['White', 'Black', 'Asian', 'AIAN', 'NHOPI', 'Two+']

    if not method_preds or not method_actuals:
        return None

    maes = []
    max_errors = []
    signed_biases = {k: [] for k in cat_cols}

    for pred, actual in zip(method_preds, method_actuals):
        if pred is None or actual is None:
            continue

        # Per-company MAE
        keys = [k for k in cat_cols if k in pred and k in actual]
        if not keys:
            continue
        company_mae = sum(abs(pred[k] - actual[k]) for k in keys) / len(keys)
        maes.append(company_mae)

        # Max error across categories for this company
        company_max = max(abs(pred[k] - actual[k]) for k in keys)
        max_errors.append(company_max)

        # Signed bias per category
        for k in keys:
            signed_biases[k].append(pred[k] - actual[k])

    if not maes:
        return None

    n = len(maes)
    avg_mae = sum(maes) / n

    # Tail risk: fraction of companies with max category error > threshold
    p_gt_20pp = sum(1 for e in max_errors if e > 20.0) / n
    p_gt_30pp = sum(1 for e in max_errors if e > 30.0) / n

    # Mean absolute signed bias (average across categories of |mean signed error|)
    cat_biases = []
    for k in cat_cols:
        if signed_biases[k]:
            cat_biases.append(abs(sum(signed_biases[k]) / len(signed_biases[k])))
    mean_abs_bias = sum(cat_biases) / len(cat_biases) if cat_biases else 0.0

    composite = avg_mae + 0.20 * p_gt_20pp * 100 + 0.35 * p_gt_30pp * 100 + 0.15 * mean_abs_bias

    return {
        'composite': round(composite, 3),
        'avg_mae': round(avg_mae, 3),
        'p_gt_20pp': round(p_gt_20pp, 4),
        'p_gt_30pp': round(p_gt_30pp, 4),
        'mean_abs_bias': round(mean_abs_bias, 3),
        'n_companies': n,
    }
