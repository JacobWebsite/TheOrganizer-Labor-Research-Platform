"""Auto-generate METHODOLOGY_REPORT_V3.md from comparison CSV data.

Usage:
    py scripts/analysis/demographics_comparison/generate_report_v3.py

Reads:
    comparison_training_400_v3_detailed.csv
    comparison_training_400_v3_summary.csv
    comparison_holdout_v3_v3_detailed.csv  (if available)
    comparison_holdout_v3_v3_summary.csv   (if available)

Outputs:
    METHODOLOGY_REPORT_V3.md in the same directory.
"""
import sys
import os
import csv
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

SCRIPT_DIR = os.path.dirname(__file__)
REPORT_FILE = os.path.join(SCRIPT_DIR, 'METHODOLOGY_REPORT_V3.md')

# Method descriptions for report
METHOD_DESCRIPTIONS = {
    'M1 Baseline (60/40)': 'Fixed 60/40 ACS/LODES blend',
    'M2 Three-Layer (50/30/20)': '50/30/20 ACS/LODES/Tract blend',
    'M3 IPF': 'Normalized product of ACS and LODES',
    'M4 Occ-Weighted': 'Occupation-weighted ACS (70%) + LODES (30%)',
    'M5 Variable-Weight': 'Industry-adaptive ACS/LODES weights',
    'M1b Learned-Wt': 'Per-NAICS-group optimized weights (V2)',
    'M3b Damp-IPF': 'Geometric mean dampening (V2 holdout winner)',
    'M1c CV-Learned-Wt': 'M1b + 5-fold CV + [0.35,0.75] constraints',
    'M1d Regional-Wt': 'M1 + 75/25 ACS/LODES for West region',
    'M2c ZIP-Tract': 'M2 + ZIP-to-tract crosswalk for workplace layer',
    'M3c Var-Damp-IPF': 'M3b + per-industry-group alpha exponent',
    'M3d Select-Damp': 'M3 + dampening only when minority > 20%',
    'M4c Top10-Occ': 'M4 with top-10 occupations (not top-30)',
    'M4d State-Top5': 'M4b + state ACS for top-5 only, national for rest',
    'M5c CV-Var-Wt': 'M5 + CV-optimized weights by M5 category',
    'M5d Corr-Min-Adapt': 'M5b flipped: increase LODES in high-minority',
}

# Base method mappings for V3 methods
V3_BASE_METHODS = {
    'M1c CV-Learned-Wt': 'M1b Learned-Wt',
    'M1d Regional-Wt': 'M1 Baseline (60/40)',
    'M2c ZIP-Tract': 'M2 Three-Layer (50/30/20)',
    'M3c Var-Damp-IPF': 'M3b Damp-IPF',
    'M3d Select-Damp': 'M3 IPF',
    'M4c Top10-Occ': 'M4 Occ-Weighted',
    'M4d State-Top5': 'M4 Occ-Weighted',
    'M5c CV-Var-Wt': 'M5 Variable-Weight',
    'M5d Corr-Min-Adapt': 'M5 Variable-Weight',
}

V3_METHODS = list(V3_BASE_METHODS.keys())


def load_detailed_csv(filepath):
    """Load detailed CSV into list of dicts."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def compute_method_race_maes(rows):
    """Compute per-method average race MAE from detailed CSV."""
    method_maes = defaultdict(list)
    for row in rows:
        if row['dimension'] == 'race' and row.get('mae'):
            try:
                method_maes[row['method']].append(float(row['mae']))
            except ValueError:
                pass
    return {m: sum(v) / len(v) for m, v in method_maes.items() if v}


def compute_method_hisp_maes(rows):
    """Compute per-method average Hispanic MAE."""
    method_maes = defaultdict(list)
    for row in rows:
        if row['dimension'] == 'hispanic' and row.get('mae'):
            try:
                method_maes[row['method']].append(float(row['mae']))
            except ValueError:
                pass
    return {m: sum(v) / len(v) for m, v in method_maes.items() if v}


def compute_method_gender_maes(rows):
    """Compute per-method average gender MAE."""
    method_maes = defaultdict(list)
    for row in rows:
        if row['dimension'] == 'gender' and row.get('mae'):
            try:
                method_maes[row['method']].append(float(row['mae']))
            except ValueError:
                pass
    return {m: sum(v) / len(v) for m, v in method_maes.items() if v}


def compute_bucket_top3(summary_rows):
    """For each dim+bucket, find top-3 methods by race MAE."""
    bucket_methods = defaultdict(list)
    for row in summary_rows:
        if row.get('avg_mae_race'):
            try:
                mae = float(row['avg_mae_race'])
                bucket_methods[(row['classification_dim'], row['bucket'])].append(
                    (row['method'], mae, int(row.get('n_companies', 0))))
            except ValueError:
                pass
    result = {}
    for key, methods in bucket_methods.items():
        methods.sort(key=lambda x: x[1])
        result[key] = methods[:3]
    return result


def compute_signed_errors(rows, methods):
    """Compute average signed errors for given methods."""
    method_cats = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row['dimension'] == 'race' and row['method'] in methods:
            for col, val in row.items():
                if col.startswith('signed_') and val:
                    cat = col.replace('signed_', '')
                    try:
                        method_cats[row['method']][cat].append(float(val))
                    except ValueError:
                        pass
    result = {}
    for method, cats in method_cats.items():
        result[method] = {cat: sum(v) / len(v) for cat, v in cats.items() if v}
    return result


def generate_report():
    """Generate the full V3 methodology report."""
    # Try to load both training and holdout data
    train_detail = load_detailed_csv(os.path.join(SCRIPT_DIR, 'comparison_training_400_v3_detailed.csv'))
    train_summary = load_detailed_csv(os.path.join(SCRIPT_DIR, 'comparison_training_400_v3_summary.csv'))
    holdout_detail = load_detailed_csv(os.path.join(SCRIPT_DIR, 'comparison_holdout_v3_v3_detailed.csv'))
    holdout_summary = load_detailed_csv(os.path.join(SCRIPT_DIR, 'comparison_holdout_v3_v3_summary.csv'))

    has_holdout = bool(holdout_detail)

    if not train_detail:
        print('ERROR: No training data found.')
        print('Run comparison first: py scripts/analysis/demographics_comparison/run_comparison_400_v3.py')
        sys.exit(1)

    train_race_maes = compute_method_race_maes(train_detail)
    train_hisp_maes = compute_method_hisp_maes(train_detail)
    train_gender_maes = compute_method_gender_maes(train_detail)

    holdout_race_maes = compute_method_race_maes(holdout_detail) if has_holdout else {}
    holdout_hisp_maes = compute_method_hisp_maes(holdout_detail) if has_holdout else {}

    lines = []
    lines.append('# Demographics Estimation V3: Methodology Report')
    lines.append('')
    lines.append('Auto-generated by `generate_report_v3.py`')
    lines.append('')

    # Section 1: Executive Summary
    lines.append('## 1. Executive Summary')
    lines.append('')

    if has_holdout:
        lines.append('| Rank | Method | Train MAE | Holdout MAE | Delta | Gen Score |')
        lines.append('|------|--------|-----------|-------------|-------|-----------|')
        sorted_methods = sorted(holdout_race_maes.keys(), key=lambda m: holdout_race_maes.get(m, 999))
    else:
        lines.append('| Rank | Method | Train MAE | Description |')
        lines.append('|------|--------|-----------|-------------|')
        sorted_methods = sorted(train_race_maes.keys(), key=lambda m: train_race_maes.get(m, 999))

    for rank, method in enumerate(sorted_methods, 1):
        train_mae = train_race_maes.get(method, 0)
        desc = METHOD_DESCRIPTIONS.get(method, '')
        if has_holdout:
            holdout_mae = holdout_race_maes.get(method, 0)
            delta = holdout_mae - train_mae
            # Generalization score: training advantage preserved on holdout
            best_train = min(train_race_maes.values()) if train_race_maes else 1
            train_adv = train_mae - best_train if train_mae > best_train else 0
            gen_score = 'N/A'
            if train_adv > 0 and holdout_mae > 0:
                holdout_adv = holdout_mae - min(holdout_race_maes.values())
                gen_score = '%.0f%%' % (100 * (1 - holdout_adv / train_adv)) if train_adv > 0 else 'N/A'
            lines.append('| %d | %s | %.2f | %.2f | %+.2f | %s |' % (
                rank, method, train_mae, holdout_mae, delta, gen_score))
        else:
            lines.append('| %d | %s | %.2f | %s |' % (rank, method, train_mae, desc))
    lines.append('')

    # Section 2: V3 Method Details
    lines.append('## 2. V3 Method Details')
    lines.append('')

    for method in V3_METHODS:
        base = V3_BASE_METHODS[method]
        desc = METHOD_DESCRIPTIONS.get(method, '')
        lines.append('### %s' % method)
        lines.append('')
        lines.append('- **Change from %s:** %s' % (base, desc))

        train_mae = train_race_maes.get(method)
        base_train_mae = train_race_maes.get(base)
        if train_mae is not None and base_train_mae is not None:
            improvement = base_train_mae - train_mae
            pct = 100 * improvement / base_train_mae if base_train_mae > 0 else 0
            lines.append('- **Training MAE:** %.2f vs %.2f (%+.1f%%)' % (
                train_mae, base_train_mae, -pct if improvement < 0 else pct))
        elif train_mae is not None:
            lines.append('- **Training MAE:** %.2f (base N/A)' % train_mae)

        if has_holdout:
            holdout_mae = holdout_race_maes.get(method)
            base_holdout_mae = holdout_race_maes.get(base)
            if holdout_mae is not None and base_holdout_mae is not None:
                improvement = base_holdout_mae - holdout_mae
                pct = 100 * improvement / base_holdout_mae if base_holdout_mae > 0 else 0
                lines.append('- **Holdout MAE:** %.2f vs %.2f (%+.1f%%)' % (
                    holdout_mae, base_holdout_mae, -pct if improvement < 0 else pct))
                # Generalization
                if train_mae and base_train_mae:
                    train_imp = base_train_mae - train_mae
                    holdout_imp = base_holdout_mae - holdout_mae
                    if train_imp != 0:
                        gen = 100 * holdout_imp / train_imp
                        lines.append('- **Generalization:** %.0f%% of training improvement held' % gen)
            elif holdout_mae is not None:
                lines.append('- **Holdout MAE:** %.2f (base N/A)' % holdout_mae)
        lines.append('')

    # Section 3: Dimensional Breakdowns
    lines.append('## 3. Dimensional Breakdowns')
    lines.append('')

    summary_source = holdout_summary if has_holdout else train_summary
    if summary_source:
        bucket_top3 = compute_bucket_top3(summary_source)
        dim_labels = {
            'naics_group': 'Industry Group',
            'size': 'Workforce Size',
            'region': 'Census Region',
            'minority_share': 'Minority Share',
            'urbanicity': 'Urbanicity',
        }
        for dim_key in ['naics_group', 'size', 'region', 'minority_share', 'urbanicity']:
            lines.append('### By %s' % dim_labels.get(dim_key, dim_key))
            lines.append('')
            lines.append('| Bucket | N | #1 | MAE | #2 | MAE | #3 | MAE |')
            lines.append('|--------|---|----|----|----|----|----|----|')

            dim_buckets = sorted(k for k in bucket_top3 if k[0] == dim_key)
            for _, bucket in dim_buckets:
                top3 = bucket_top3.get((dim_key, bucket), [])
                row_parts = ['| %s' % bucket]
                if top3:
                    row_parts.append('| %d' % top3[0][2])
                    for m, mae, _ in top3:
                        short = m.split(' ')[0] if ' ' in m else m[:6]
                        row_parts.append('| %s | %.1f' % (short, mae))
                    for _ in range(3 - len(top3)):
                        row_parts.append('| - | -')
                else:
                    row_parts.append('| 0 | - | - | - | - | - | -')
                row_parts.append('|')
                lines.append(' '.join(row_parts))
            lines.append('')

    # Section 4: Overfitting Flags
    lines.append('## 4. Overfitting Flags')
    lines.append('')

    if has_holdout:
        flagged = []
        for method in sorted(train_race_maes.keys()):
            train_mae = train_race_maes.get(method, 0)
            holdout_mae = holdout_race_maes.get(method, 0)
            if train_mae > 0 and holdout_mae > 0:
                # Find best training method
                best_train = min(train_race_maes.values())
                train_advantage = best_train / train_mae if train_mae > 0 else 0
                holdout_advantage = min(holdout_race_maes.values()) / holdout_mae if holdout_mae > 0 else 0
                # Flag if holdout advantage shrinks by > 50%
                if train_advantage > 0 and holdout_advantage > 0:
                    shrinkage = 1 - (holdout_advantage / train_advantage) if train_advantage > holdout_advantage else 0
                    if shrinkage > 0.50:
                        flagged.append((method, train_mae, holdout_mae, shrinkage * 100))

        if flagged:
            lines.append('Methods flagged for overfitting (training advantage shrinks > 50% on holdout):')
            lines.append('')
            lines.append('| Method | Train MAE | Holdout MAE | Shrinkage |')
            lines.append('|--------|-----------|-------------|-----------|')
            for method, t, h, s in flagged:
                lines.append('| %s | %.2f | %.2f | %.0f%% |' % (method, t, h, s))
        else:
            lines.append('No methods flagged for overfitting.')
    else:
        lines.append('Holdout data not yet available. Run holdout comparison first.')
    lines.append('')

    # Section 5: Bias Analysis
    lines.append('## 5. Bias Analysis')
    lines.append('')

    detail_source = holdout_detail if has_holdout else train_detail
    top3_methods = sorted(compute_method_race_maes(detail_source).keys(),
                          key=lambda m: compute_method_race_maes(detail_source).get(m, 999))[:3]

    if top3_methods:
        signed = compute_signed_errors(detail_source, top3_methods)
        lines.append('Average signed errors for top-3 methods (positive = overestimate):')
        lines.append('')
        lines.append('| Method | White | Black | Asian | AIAN | NHOPI | Two+ |')
        lines.append('|--------|-------|-------|-------|------|-------|------|')
        for method in top3_methods:
            errors = signed.get(method, {})
            lines.append('| %s | %+.1f | %+.1f | %+.1f | %+.1f | %+.1f | %+.1f |' % (
                method,
                errors.get('White', 0),
                errors.get('Black', 0),
                errors.get('Asian', 0),
                errors.get('AIAN', 0),
                errors.get('NHOPI', 0),
                errors.get('Two+', 0),
            ))
    lines.append('')

    # Note about M7
    lines.append('## Notes')
    lines.append('')
    lines.append('- M7 (Hybrid) is not re-tested as a separate V3 method. It automatically ')
    lines.append('  inherits M1c race output since M7 = M1b_race + M3_gender. Track M1c ')
    lines.append('  race performance as the M7 proxy.')
    lines.append('')

    # Write report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('Wrote %s' % REPORT_FILE)


if __name__ == '__main__':
    generate_report()
