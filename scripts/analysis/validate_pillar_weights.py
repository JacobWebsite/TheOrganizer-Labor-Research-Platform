"""
Validate pillar weights via logistic regression against NLRB outcomes.

Usage:
    py scripts/analysis/validate_pillar_weights.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'docs', 'pillar_weight_validation.csv')

# Current pillar weights from the scoring formula
CURRENT_WEIGHTS = {'anger': 3, 'stability': 0, 'leverage': 4}


def fetch_election_data(conn):
    """
    Pull NLRB election outcomes linked to scored employers with pillar scores.

    Returns list of dicts with keys:
        employer_id, union_won, score_anger, score_stability, score_leverage
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT
            m.employer_id,
            e.union_won,
            m.score_anger,
            m.score_stability,
            m.score_leverage
        FROM nlrb_elections e
        JOIN nlrb_participants p
            ON p.case_number = e.case_number
            AND p.participant_type = 'Employer'
        JOIN mv_unified_scorecard m
            ON m.employer_id = p.matched_employer_id
        WHERE p.matched_employer_id IS NOT NULL
          AND m.score_anger IS NOT NULL
          AND m.score_leverage IS NOT NULL
    """)
    columns = ['employer_id', 'union_won', 'score_anger', 'score_stability', 'score_leverage']
    rows = []
    for row in cur.fetchall():
        rows.append(dict(zip(columns, row)))
    cur.close()
    return rows


def run_regression(data):
    """Run logistic regression and report results."""
    # Prepare features -- use anger, stability, leverage
    # stability may be NULL for many rows, fill with 0
    X = []
    y = []
    for d in data:
        anger = float(d['score_anger']) if d['score_anger'] is not None else 0.0
        stability = float(d['score_stability']) if d['score_stability'] is not None else 0.0
        leverage = float(d['score_leverage']) if d['score_leverage'] is not None else 0.0
        X.append([anger, stability, leverage])
        y.append(1 if d['union_won'] else 0)

    if len(set(y)) < 2:
        print("  ERROR: Only one class present in outcomes -- cannot run regression.")
        return None

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_scaled, y)

    y_pred = model.predict(X_scaled)
    accuracy = accuracy_score(y, y_pred)

    return {
        'model': model,
        'scaler': scaler,
        'accuracy': accuracy,
        'coefficients': dict(zip(['anger', 'stability', 'leverage'], model.coef_[0])),
        'intercept': model.intercept_[0],
        'X': X,
        'y': y,
        'y_pred': y_pred,
    }


def print_report(results, data):
    """Print the regression report to stdout."""
    print("\n" + "=" * 60)
    print("  PILLAR WEIGHT VALIDATION -- Logistic Regression")
    print("=" * 60)

    print(f"\n  Data points: {len(data):,}")
    wins = sum(1 for d in data if d['union_won'])
    losses = len(data) - wins
    print(f"  Union wins:  {wins:,} ({100.0 * wins / len(data):.1f}%)")
    print(f"  Union losses: {losses:,} ({100.0 * losses / len(data):.1f}%)")

    print(f"\n  Model accuracy: {results['accuracy']:.3f}")
    print(f"  Intercept: {results['intercept']:.4f}")

    print("\n  Coefficients (standardized):")
    print(f"  {'Pillar':<15s} {'Coeff':>10s} {'Odds Ratio':>12s} {'Current Wt':>12s}")
    print(f"  {'-' * 15} {'-' * 10} {'-' * 12} {'-' * 12}")

    import math
    for pillar in ['anger', 'stability', 'leverage']:
        coeff = results['coefficients'][pillar]
        odds = math.exp(coeff)
        current = CURRENT_WEIGHTS[pillar]
        print(f"  {pillar:<15s} {coeff:>10.4f} {odds:>12.4f} {current:>12d}")

    # Compute optimal weights (proportional to abs coefficients)
    total_coeff = sum(abs(c) for c in results['coefficients'].values())
    if total_coeff > 0:
        print("\n  Suggested weights (proportional to |coeff|, summing to 10):")
        for pillar in ['anger', 'stability', 'leverage']:
            coeff = results['coefficients'][pillar]
            suggested = round(10 * abs(coeff) / total_coeff, 1)
            print(f"    {pillar}: {suggested:.1f}")

    # Compare current 3-0-4 vs optimal
    print("\n  Current formula:  anger*3 + stability*0 + leverage*4  (/ dynamic denom)")
    print(f"  Model prediction: anger*{results['coefficients']['anger']:.2f} "
          f"+ stability*{results['coefficients']['stability']:.2f} "
          f"+ leverage*{results['coefficients']['leverage']:.2f}")


def save_csv(results, data):
    """Save detailed results to CSV."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'employer_id', 'union_won', 'score_anger', 'score_stability',
            'score_leverage', 'predicted_win',
        ])
        for i, d in enumerate(data):
            writer.writerow([
                d['employer_id'],
                1 if d['union_won'] else 0,
                d['score_anger'] or '',
                d['score_stability'] or '',
                d['score_leverage'] or '',
                results['y_pred'][i],
            ])

    print(f"\n  Results saved to {OUTPUT_PATH}")


def main():
    if not HAS_SKLEARN:
        print("ERROR: scikit-learn is required but not installed.")
        print("Install it with:  py -m pip install scikit-learn")
        sys.exit(1)

    conn = get_connection()
    try:
        data = fetch_election_data(conn)
    finally:
        conn.close()

    if len(data) < 30:
        print(f"WARNING: Only {len(data)} data points found (need at least 30).")
        print("Not enough NLRB election data linked to scored employers for meaningful regression.")
        if len(data) == 0:
            print("No matching records found. Ensure nlrb_participants.matched_employer_id is populated.")
            sys.exit(0)

    print(f"Fetched {len(data):,} election outcomes linked to scored employers.")

    results = run_regression(data)
    if results is None:
        sys.exit(1)

    print_report(results, data)
    save_csv(results, data)


if __name__ == '__main__':
    main()
