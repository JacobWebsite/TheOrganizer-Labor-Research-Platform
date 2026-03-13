"""Auto-generate METHODOLOGY_REPORT_V4.md from V4 comparison CSV data.

Usage:
    py scripts/analysis/demographics_comparison/generate_report_v4.py

Reads:
    comparison_all_v4_detailed.csv
    comparison_all_v4_summary.csv

Outputs:
    METHODOLOGY_REPORT_V4.md
"""
import sys
import os
import csv
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

SCRIPT_DIR = os.path.dirname(__file__)
REPORT_FILE = os.path.join(SCRIPT_DIR, 'METHODOLOGY_REPORT_V4.md')

# All ~23 method descriptions
METHOD_DESCRIPTIONS = {
    'M1 Baseline (60/40)': 'Fixed 60/40 ACS/LODES blend',
    'M2 Three-Layer (50/30/20)': '50/30/20 ACS/LODES/Tract blend',
    'M3 IPF': 'Normalized product of ACS and LODES',
    'M4 Occ-Weighted': 'Occupation-weighted ACS (70%) + LODES (30%)',
    'M5 Variable-Weight': 'Industry-adaptive ACS/LODES weights',
    'M1b Learned-Wt': 'Per-NAICS-group optimized weights (V2)',
    'M3b Damp-IPF': 'Geometric mean dampening (V2)',
    'M1c CV-Learned-Wt': 'M1b + 5-fold CV + [0.35,0.75] constraints',
    'M1d Regional-Wt': 'M1 + 75/25 ACS/LODES for West region',
    'M2c ZIP-Tract': 'M2 + ZIP-to-tract crosswalk for workplace layer',
    'M3c Var-Damp-IPF': 'M3b + per-industry-group alpha exponent (V3 champion)',
    'M3d Select-Damp': 'M3 + dampening only when minority > 20%',
    'M4c Top10-Occ': 'M4 with top-10 occupations (not top-30)',
    'M4d State-Top5': 'M4b + state ACS for top-5 only, national for rest',
    'M5c CV-Var-Wt': 'M5 + CV-optimized weights by M5 category',
    'M5d Corr-Min-Adapt': 'M5b flipped: increase LODES in high-minority',
    'M3e Fin-Route-IPF': 'Route Finance/Utilities to M3 IPF, others to M3c',
    'M3f Min-Ind-Thresh': 'M3 IPF for Finance/Utilities + minority threshold routing',
    'M1e Hi-Min-Floor': 'M1b with LODES floor in high-minority counties',
    'M4e Var-Occ-Trim': 'Filter occupations by demographic variance, 70/30 LODES',
    'M2d Amp-Tract': 'Three-Layer 45/20/35 (amplified tract weight)',
    'M5e Ind-Dispatch': 'Route to best method per industry category',
    'M8 Adaptive-Router': 'Meta-method: routes by industry, geography, minority share',
}

# V4 method base mappings
V4_BASE_METHODS = {
    'M3e Fin-Route-IPF': 'M3c Var-Damp-IPF',
    'M3f Min-Ind-Thresh': 'M3c Var-Damp-IPF',
    'M1e Hi-Min-Floor': 'M1b Learned-Wt',
    'M4e Var-Occ-Trim': 'M4 Occ-Weighted',
    'M2d Amp-Tract': 'M2c ZIP-Tract',
    'M5e Ind-Dispatch': 'M5 Variable-Weight',
    'M8 Adaptive-Router': 'M3c Var-Damp-IPF',
}

V4_METHODS = list(V4_BASE_METHODS.keys())

# Key comparison pairs
KEY_COMPARISONS = [
    ('M3e Fin-Route-IPF', 'M3c Var-Damp-IPF'),
    ('M8 Adaptive-Router', 'M3c Var-Damp-IPF'),
    ('M4e Var-Occ-Trim', 'M4 Occ-Weighted'),
    ('M1e Hi-Min-Floor', 'M1b Learned-Wt'),
    ('M3f Min-Ind-Thresh', 'M3c Var-Damp-IPF'),
]


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


def compute_m8_routing_stats(rows):
    """Compute M8 routing distribution and per-route MAE."""
    route_counts = defaultdict(int)
    route_maes = defaultdict(list)

    for row in rows:
        if row['method'] == 'M8 Adaptive-Router' and row['dimension'] == 'race':
            route = row.get('routing_method', '')
            if route:
                route_counts[route] += 1
                if row.get('mae'):
                    try:
                        route_maes[route].append(float(row['mae']))
                    except ValueError:
                        pass

    return route_counts, route_maes


def compute_source_set_maes(rows):
    """Compute per-method MAE by source_set."""
    source_method_maes = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row['dimension'] == 'race' and row.get('mae') and row.get('source_set'):
            try:
                source_method_maes[row['source_set']][row['method']].append(float(row['mae']))
            except ValueError:
                pass

    result = {}
    for src, methods in source_method_maes.items():
        result[src] = {m: sum(v) / len(v) for m, v in methods.items() if v}
    return result


def generate_report():
    """Generate the full V4 methodology report."""
    detail = load_detailed_csv(os.path.join(SCRIPT_DIR, 'comparison_all_v4_detailed.csv'))
    summary = load_detailed_csv(os.path.join(SCRIPT_DIR, 'comparison_all_v4_summary.csv'))

    if not detail:
        print('ERROR: No V4 data found.')
        print('Run comparison first: py scripts/analysis/demographics_comparison/run_comparison_all_v4.py')
        sys.exit(1)

    race_maes = compute_method_race_maes(detail)
    hisp_maes = compute_method_hisp_maes(detail)
    gender_maes = compute_method_gender_maes(detail)

    lines = []
    lines.append('# Demographics Estimation V4: Methodology Report')
    lines.append('')
    lines.append('Auto-generated by `generate_report_v4.py`')
    lines.append('')

    # Section 1: Executive Summary
    lines.append('## 1. Executive Summary')
    lines.append('')
    lines.append('All ~23 methods ranked by race MAE on ~998 companies (full evaluation set).')
    lines.append('')
    lines.append('| Rank | Method | Race MAE | Hisp MAE | Gender MAE | Description |')
    lines.append('|------|--------|----------|----------|------------|-------------|')

    sorted_methods = sorted(race_maes.keys(), key=lambda m: race_maes.get(m, 999))
    for rank, method in enumerate(sorted_methods, 1):
        r_mae = race_maes.get(method, 0)
        h_mae = hisp_maes.get(method, 0)
        g_mae = gender_maes.get(method, 0)
        desc = METHOD_DESCRIPTIONS.get(method, '')
        lines.append('| %d | %s | %.2f | %.2f | %.2f | %s |' % (
            rank, method, r_mae, h_mae, g_mae, desc))
    lines.append('')

    # Section 2: V4 Method Details
    lines.append('## 2. V4 Method Details')
    lines.append('')

    for method in V4_METHODS:
        base = V4_BASE_METHODS[method]
        desc = METHOD_DESCRIPTIONS.get(method, '')
        lines.append('### %s' % method)
        lines.append('')
        lines.append('- **Change from %s:** %s' % (base, desc))

        method_mae = race_maes.get(method)
        base_mae = race_maes.get(base)
        if method_mae is not None and base_mae is not None:
            improvement = base_mae - method_mae
            pct = 100 * improvement / base_mae if base_mae > 0 else 0
            direction = 'improvement' if improvement > 0 else 'regression'
            lines.append('- **Race MAE:** %.2f vs %.2f base (%+.2f, %.1f%% %s)' % (
                method_mae, base_mae, -improvement, abs(pct), direction))
        elif method_mae is not None:
            lines.append('- **Race MAE:** %.2f (base N/A)' % method_mae)

        # Hispanic and gender
        method_h = hisp_maes.get(method)
        base_h = hisp_maes.get(base)
        if method_h is not None and base_h is not None:
            lines.append('- **Hispanic MAE:** %.2f vs %.2f base' % (method_h, base_h))
        lines.append('')

    # Section 3: Key Comparisons
    lines.append('## 3. Key Comparisons')
    lines.append('')
    lines.append('| Method | Base | Race MAE | Base MAE | Delta | Improvement |')
    lines.append('|--------|------|----------|----------|-------|-------------|')

    for method, base in KEY_COMPARISONS:
        m_mae = race_maes.get(method, 0)
        b_mae = race_maes.get(base, 0)
        delta = m_mae - b_mae
        pct = 100 * (b_mae - m_mae) / b_mae if b_mae > 0 else 0
        lines.append('| %s | %s | %.2f | %.2f | %+.2f | %+.1f%% |' % (
            method, base, m_mae, b_mae, delta, pct))
    lines.append('')

    # Section 4: M8 Routing Analysis
    lines.append('## 4. M8 Routing Analysis')
    lines.append('')

    route_counts, route_maes = compute_m8_routing_stats(detail)
    if route_counts:
        lines.append('| Route | Count | Avg MAE |')
        lines.append('|-------|-------|---------|')
        for route in sorted(route_counts.keys()):
            maes = route_maes.get(route, [])
            avg = '%.2f' % (sum(maes) / len(maes)) if maes else 'N/A'
            lines.append('| %s | %d | %s |' % (route, route_counts[route], avg))
        lines.append('| **Total** | **%d** | |' % sum(route_counts.values()))
    else:
        lines.append('No M8 routing data available.')
    lines.append('')

    # M3c comparison per route
    m3c_mae = race_maes.get('M3c Var-Damp-IPF')
    if m3c_mae is not None and route_maes:
        lines.append('M3c (champion) overall MAE: %.2f' % m3c_mae)
        lines.append('')
        lines.append('Routes where M8 outperforms M3c:')
        for route in sorted(route_maes.keys()):
            maes = route_maes[route]
            if maes:
                avg = sum(maes) / len(maes)
                if avg < m3c_mae:
                    lines.append('- %s: %.2f (M3c: %.2f, delta: %+.2f)' % (
                        route, avg, m3c_mae, avg - m3c_mae))
        lines.append('')

    # Section 5: Source Set Analysis
    lines.append('## 5. Source Set Analysis (Optimism Bias Check)')
    lines.append('')

    source_maes = compute_source_set_maes(detail)
    if source_maes:
        # Get top-5 overall methods
        top5 = sorted_methods[:5]
        lines.append('Top-5 methods MAE by source set:')
        lines.append('')

        header = '| Method'
        for src in sorted(source_maes.keys()):
            header += ' | %s' % src
        header += ' |'
        lines.append(header)
        lines.append('|' + '|'.join(['--------'] * (1 + len(source_maes))) + '|')

        for method in top5:
            row = '| %s' % method
            for src in sorted(source_maes.keys()):
                mae = source_maes[src].get(method)
                row += ' | %.2f' % mae if mae is not None else ' | N/A'
            row += ' |'
            lines.append(row)
        lines.append('')

        # Flag if holdout performs > 0.5pp worse
        lines.append('Optimism flags (holdout > 0.5pp worse than training):')
        has_flag = False
        for method in top5:
            train_mae = source_maes.get('v3_train', {}).get(method)
            holdout_mae = source_maes.get('v3_holdout', {}).get(method)
            if train_mae is not None and holdout_mae is not None:
                delta = holdout_mae - train_mae
                if delta > 0.5:
                    lines.append('- **%s**: train=%.2f, holdout=%.2f, delta=+%.2f' % (
                        method, train_mae, holdout_mae, delta))
                    has_flag = True
        if not has_flag:
            lines.append('- None flagged.')
    else:
        lines.append('No source_set data available.')
    lines.append('')

    # Section 6: Dimensional Breakdowns
    lines.append('## 6. Dimensional Breakdowns (Top-3 per Bucket)')
    lines.append('')

    if summary:
        bucket_top3 = compute_bucket_top3(summary)
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

    # Section 7: Overfitting Flags
    lines.append('## 7. Overfitting Flags')
    lines.append('')

    if source_maes:
        train_maes = source_maes.get('v3_train', {})
        holdout_maes = source_maes.get('v3_holdout', {})

        if train_maes and holdout_maes:
            flagged = []
            for method in sorted(race_maes.keys()):
                t_mae = train_maes.get(method)
                h_mae = holdout_maes.get(method)
                if t_mae is not None and h_mae is not None and t_mae > 0:
                    pct_increase = 100 * (h_mae - t_mae) / t_mae
                    if pct_increase > 10:
                        flagged.append((method, t_mae, h_mae, pct_increase))

            if flagged:
                lines.append('Methods with >10% MAE increase from v3_train to v3_holdout:')
                lines.append('')
                lines.append('| Method | Train MAE | Holdout MAE | Increase |')
                lines.append('|--------|-----------|-------------|----------|')
                for method, t, h, pct in sorted(flagged, key=lambda x: -x[3]):
                    lines.append('| %s | %.2f | %.2f | +%.1f%% |' % (method, t, h, pct))
            else:
                lines.append('No methods flagged for overfitting (all <10% holdout increase).')
        else:
            lines.append('Insufficient source_set data for overfitting analysis.')
    else:
        lines.append('No source_set data available.')
    lines.append('')

    # Section 8: Bias Analysis
    lines.append('## 8. Bias Analysis')
    lines.append('')

    top3_methods = sorted_methods[:3]
    if top3_methods:
        signed = compute_signed_errors(detail, top3_methods)
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

    # Notes
    lines.append('## Notes')
    lines.append('')
    lines.append('- V4 uses all ~998 companies from V2 + V3 datasets as the evaluation set.')
    lines.append('- No new holdout -- this is development evaluation only.')
    lines.append('- M8 routing decisions are based on pre-classified company attributes.')
    lines.append('- Source set analysis checks for optimism bias across training/holdout splits.')
    lines.append('')

    # Write report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('Wrote %s' % REPORT_FILE)


if __name__ == '__main__':
    generate_report()
