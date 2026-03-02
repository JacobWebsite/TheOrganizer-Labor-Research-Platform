"""
Monthly coverage QA -- check factor coverage by state and industry.

Usage:
    py scripts/maintenance/coverage_qa.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'docs', 'coverage_qa.csv')

FACTORS = [
    'score_osha', 'score_nlrb', 'score_whd', 'score_contracts',
    'score_union_proximity', 'score_financial', 'score_industry_growth',
    'score_size', 'score_similarity',
]

LOW_COVERAGE_THRESHOLD = 1.0  # percent


def get_state_coverage(conn):
    """Get factor coverage by state."""
    cur = conn.cursor()

    # Build dynamic SQL for factor coverage per state
    factor_exprs = []
    for f in FACTORS:
        factor_exprs.append(
            f"ROUND(100.0 * COUNT(*) FILTER (WHERE {f} IS NOT NULL) / COUNT(*), 1) AS {f}_pct"
        )

    sql = f"""
        SELECT
            state,
            COUNT(*) AS total,
            {', '.join(factor_exprs)}
        FROM mv_unified_scorecard
        WHERE state IS NOT NULL
        GROUP BY state
        ORDER BY state
    """
    cur.execute(sql)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def get_industry_coverage(conn):
    """Get factor coverage by 2-digit NAICS."""
    cur = conn.cursor()

    factor_exprs = []
    for f in FACTORS:
        factor_exprs.append(
            f"ROUND(100.0 * COUNT(*) FILTER (WHERE {f} IS NOT NULL) / COUNT(*), 1) AS {f}_pct"
        )

    sql = f"""
        SELECT
            SUBSTRING(naics FROM 1 FOR 2) AS naics_2,
            COUNT(*) AS total,
            {', '.join(factor_exprs)}
        FROM mv_unified_scorecard
        WHERE naics IS NOT NULL
        GROUP BY SUBSTRING(naics FROM 1 FOR 2)
        HAVING COUNT(*) >= 10
        ORDER BY SUBSTRING(naics FROM 1 FOR 2)
    """
    cur.execute(sql)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def find_low_coverage(rows, dimension_key):
    """Flag rows where any factor coverage is suspiciously low."""
    alerts = []
    for row in rows:
        dim_val = row[dimension_key]
        total = row['total']
        for f in FACTORS:
            pct = float(row.get(f'{f}_pct', 0) or 0)
            if pct < LOW_COVERAGE_THRESHOLD and pct > 0:
                alerts.append({
                    'dimension': dimension_key,
                    'value': dim_val,
                    'total_employers': total,
                    'factor': f,
                    'coverage_pct': pct,
                })
    return alerts


def find_data_deserts(industry_rows):
    """Find industries with minimal enforcement data (OSHA + WHD + NLRB all < 5%)."""
    deserts = []
    for row in industry_rows:
        osha_pct = float(row.get('score_osha_pct', 0) or 0)
        whd_pct = float(row.get('score_whd_pct', 0) or 0)
        nlrb_pct = float(row.get('score_nlrb_pct', 0) or 0)
        if osha_pct < 5 and whd_pct < 5 and nlrb_pct < 5:
            deserts.append({
                'naics_2': row['naics_2'],
                'total': row['total'],
                'osha_pct': osha_pct,
                'whd_pct': whd_pct,
                'nlrb_pct': nlrb_pct,
            })
    return deserts


def save_csv(state_rows, industry_rows):
    """Save combined coverage data to CSV."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        header = ['dimension', 'value', 'total']
        for fac in FACTORS:
            header.append(f'{fac}_pct')
        writer.writerow(header)

        # State rows
        for row in state_rows:
            out = ['state', row['state'], row['total']]
            for fac in FACTORS:
                out.append(row.get(f'{fac}_pct', ''))
            writer.writerow(out)

        # Industry rows
        for row in industry_rows:
            out = ['naics_2', row['naics_2'], row['total']]
            for fac in FACTORS:
                out.append(row.get(f'{fac}_pct', ''))
            writer.writerow(out)

    print(f"  CSV saved to {OUTPUT_PATH}")


def main():
    print("=" * 60)
    print("  MONTHLY COVERAGE QA")
    print("=" * 60)

    conn = get_connection()
    try:
        state_rows = get_state_coverage(conn)
        industry_rows = get_industry_coverage(conn)
    finally:
        conn.close()

    # --- State coverage summary ---
    print(f"\n  States with data: {len(state_rows)}")

    state_alerts = find_low_coverage(state_rows, 'state')
    if state_alerts:
        print(f"\n  LOW COVERAGE ALERTS (by state, <{LOW_COVERAGE_THRESHOLD}%):")
        for a in state_alerts[:20]:
            print(f"    State={a['value']}  factor={a['factor']}  "
                  f"coverage={a['coverage_pct']:.1f}%  (n={a['total_employers']:,})")
        if len(state_alerts) > 20:
            print(f"    ... and {len(state_alerts) - 20} more")
    else:
        print("  No low-coverage state alerts.")

    # --- Industry coverage summary ---
    print(f"\n  Industries (2-digit NAICS) with data: {len(industry_rows)}")

    industry_alerts = find_low_coverage(industry_rows, 'naics_2')
    if industry_alerts:
        print(f"\n  LOW COVERAGE ALERTS (by industry, <{LOW_COVERAGE_THRESHOLD}%):")
        for a in industry_alerts[:20]:
            print(f"    NAICS={a['value']}  factor={a['factor']}  "
                  f"coverage={a['coverage_pct']:.1f}%  (n={a['total_employers']:,})")
        if len(industry_alerts) > 20:
            print(f"    ... and {len(industry_alerts) - 20} more")
    else:
        print("  No low-coverage industry alerts.")

    # --- Data deserts ---
    deserts = find_data_deserts(industry_rows)
    if deserts:
        print(f"\n  DATA DESERTS (OSHA + WHD + NLRB all <5%):")
        for d in deserts:
            print(f"    NAICS={d['naics_2']}  n={d['total']:,}  "
                  f"OSHA={d['osha_pct']:.1f}%  WHD={d['whd_pct']:.1f}%  NLRB={d['nlrb_pct']:.1f}%")
    else:
        print("\n  No data deserts found.")

    # --- Overall coverage table ---
    print(f"\n  OVERALL FACTOR COVERAGE:")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mv_unified_scorecard")
        total = cur.fetchone()[0]
        print(f"  Total employers: {total:,}")
        print(f"\n  {'Factor':<25s} {'Count':>10s} {'Pct':>8s}")
        print(f"  {'-' * 25} {'-' * 10} {'-' * 8}")
        for f in FACTORS:
            cur.execute(f"SELECT COUNT(*) FROM mv_unified_scorecard WHERE {f} IS NOT NULL")
            cnt = cur.fetchone()[0]
            pct = 100.0 * cnt / total if total else 0
            print(f"  {f:<25s} {cnt:>10,} {pct:>7.1f}%")
        cur.close()
    finally:
        conn.close()

    # Save CSV
    save_csv(state_rows, industry_rows)
    print()


if __name__ == '__main__':
    main()
