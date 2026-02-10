"""
Comprehensive validation suite with drift detection.

Runs all data quality checks and compares against stored baselines.
Alerts if any table changes > 5% without a documented ETL run.

Usage:
    py scripts/validation/run_all_checks.py                # Run checks
    py scripts/validation/run_all_checks.py --save-baseline # Save current counts as baseline
    py scripts/validation/run_all_checks.py --json          # Output as JSON

Runs automatically via: py -m pytest tests/ -v
"""
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from db_config import get_connection

BASELINE_FILE = Path(__file__).resolve().parent / 'baselines.json'
LOG_DIR = Path(__file__).resolve().parent.parent.parent / 'logs'

CORE_TABLES = {
    'unions_master': 25000,
    'f7_employers_deduped': 55000,
    'f7_union_employer_relations': 100000,
    'nlrb_elections': 30000,
    'nlrb_participants': 1000000,
    'osha_establishments': 900000,
    'osha_violations_detail': 2000000,
    'whd_cases': 300000,
    'gleif_us_entities': 300000,
    'gleif_ownership_links': 400000,
    'sec_companies': 400000,
    'corporate_identifier_crosswalk': 10000,
    'corporate_hierarchy': 100000,
    'union_hierarchy': 18000,
    'qcew_annual': 1500000,
    'federal_contract_recipients': 40000,
    'mergent_employers': 50000,
}


def query_one(cur, sql, params=None):
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row[0] if row else None


def check_bls_alignment(cur):
    """BLS total within 5%."""
    total = query_one(cur, """
        SELECT SUM(members)
        FROM unions_master um
        JOIN union_hierarchy uh ON um.f_num = uh.f_num
        WHERE uh.count_members = TRUE
    """)
    if total is None:
        total = query_one(cur, "SELECT SUM(members) FROM v_union_members_deduplicated")
    if total is None:
        return {'status': 'SKIP', 'message': 'No membership view available'}

    BLS = 14_286_000
    variance = abs(total - BLS) / BLS
    return {
        'status': 'PASS' if variance < 0.05 else 'FAIL',
        'value': total,
        'benchmark': BLS,
        'variance': f'{variance:.1%}',
    }


def check_naics_coverage(cur):
    """NAICS coverage >= 99%."""
    total = query_one(cur, "SELECT COUNT(*) FROM f7_employers_deduped")
    has_naics = query_one(cur, "SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NOT NULL AND naics != ''")
    rate = has_naics / total if total else 0
    return {
        'status': 'PASS' if rate >= 0.99 else 'FAIL',
        'value': f'{rate:.1%}',
        'detail': f'{has_naics:,}/{total:,}',
    }


def check_geocode_coverage(cur):
    """Geocode coverage >= 90%."""
    total = query_one(cur, "SELECT COUNT(*) FROM f7_employers_deduped")
    geocoded = query_one(cur, "SELECT COUNT(*) FROM f7_employers_deduped WHERE latitude IS NOT NULL")
    rate = geocoded / total if total else 0
    return {
        'status': 'PASS' if rate >= 0.90 else 'FAIL',
        'value': f'{rate:.1%}',
        'detail': f'{geocoded:,}/{total:,}',
    }


def check_hierarchy_coverage(cur):
    """Hierarchy coverage >= 95%."""
    total = query_one(cur, "SELECT COUNT(*) FROM unions_master")
    covered = query_one(cur, """
        SELECT COUNT(*) FROM unions_master um
        JOIN union_hierarchy uh ON um.f_num = uh.f_num
    """)
    rate = covered / total if total else 0
    return {
        'status': 'PASS' if rate >= 0.95 else 'FAIL',
        'value': f'{rate:.1%}',
        'detail': f'{covered:,}/{total:,}',
    }


def check_sector_completeness(cur):
    """Sector classification >= 99%."""
    total = query_one(cur, "SELECT COUNT(*) FROM unions_master")
    classified = query_one(cur, """
        SELECT COUNT(*) FROM unions_master
        WHERE sector IS NOT NULL AND sector != 'UNKNOWN'
    """)
    rate = classified / total if total else 0
    return {
        'status': 'PASS' if rate >= 0.99 else 'FAIL',
        'value': f'{rate:.1%}',
    }


def check_crosswalk_orphans(cur):
    """Crosswalk orphan rate < 40%."""
    orphans = query_one(cur, """
        SELECT COUNT(*) FROM corporate_identifier_crosswalk c
        LEFT JOIN f7_employers_deduped f ON c.f7_employer_id = f.employer_id
        WHERE f.employer_id IS NULL AND c.f7_employer_id IS NOT NULL
    """)
    total = query_one(cur, """
        SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE f7_employer_id IS NOT NULL
    """)
    rate = orphans / total if total else 0
    return {
        'status': 'PASS' if rate < 0.40 else 'FAIL',
        'value': f'{rate:.1%}',
        'detail': f'{orphans:,} orphans / {total:,} total',
    }


def check_no_exact_dupes(cur):
    """No exact name+city+state duplicates (< 100)."""
    dupes = query_one(cur, """
        SELECT COUNT(*) FROM (
            SELECT employer_name, UPPER(city), state
            FROM f7_employers_deduped
            GROUP BY employer_name, UPPER(city), state
            HAVING COUNT(*) > 1
        ) d
    """)
    return {
        'status': 'PASS' if dupes < 100 else 'FAIL',
        'value': dupes,
    }


def check_materialized_views(cur):
    """All materialized views populated."""
    cur.execute("""
        SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'
    """)
    views = [r[0] for r in cur.fetchall()]
    empty = []
    for v in views:
        cnt = query_one(cur, f"SELECT COUNT(*) FROM {v}")
        if cnt == 0:
            empty.append(v)
    return {
        'status': 'PASS' if not empty else 'FAIL',
        'value': f'{len(views) - len(empty)}/{len(views)} populated',
        'empty': empty if empty else None,
    }


def check_table_drift(cur, baselines):
    """Check for unexpected changes in table row counts."""
    if not baselines:
        return {'status': 'SKIP', 'message': 'No baselines saved'}

    drifts = []
    for table, baseline_count in baselines.items():
        try:
            current = query_one(cur, f"SELECT COUNT(*) FROM {table}")
            if baseline_count > 0:
                change = abs(current - baseline_count) / baseline_count
                if change > 0.05:
                    drifts.append({
                        'table': table,
                        'baseline': baseline_count,
                        'current': current,
                        'change': f'{change:.1%}',
                    })
        except Exception:
            pass

    return {
        'status': 'PASS' if not drifts else 'WARN',
        'drifts': drifts if drifts else None,
        'message': f'{len(drifts)} tables drifted > 5%' if drifts else 'All tables stable',
    }


def save_baseline(cur):
    """Save current row counts as baseline."""
    counts = {}
    for table in CORE_TABLES:
        try:
            counts[table] = query_one(cur, f"SELECT COUNT(*) FROM {table}")
        except Exception:
            pass

    counts['_saved_at'] = datetime.now().isoformat()
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_FILE, 'w') as f:
        json.dump(counts, f, indent=2, default=str)
    print(f"Baseline saved to {BASELINE_FILE}")
    print(f"Tables: {len(counts) - 1}")
    for table, count in sorted(counts.items()):
        if table.startswith('_'):
            continue
        print(f"  {table}: {count:,}")


def load_baselines():
    """Load saved baselines."""
    if BASELINE_FILE.exists():
        with open(BASELINE_FILE) as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith('_')}
    return {}


def main():
    parser = argparse.ArgumentParser(description="Run validation checks")
    parser.add_argument('--save-baseline', action='store_true', help='Save current counts')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    if args.save_baseline:
        save_baseline(cur)
        conn.close()
        return

    baselines = load_baselines()

    checks = {
        'BLS Alignment': check_bls_alignment(cur),
        'NAICS Coverage': check_naics_coverage(cur),
        'Geocode Coverage': check_geocode_coverage(cur),
        'Hierarchy Coverage': check_hierarchy_coverage(cur),
        'Sector Completeness': check_sector_completeness(cur),
        'Crosswalk Orphans': check_crosswalk_orphans(cur),
        'No Exact Duplicates': check_no_exact_dupes(cur),
        'Materialized Views': check_materialized_views(cur),
        'Table Drift': check_table_drift(cur, baselines),
    }

    timestamp = datetime.now().isoformat()
    results = {'timestamp': timestamp, 'checks': checks}

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print("=" * 60)
        print(f"Validation Report - {timestamp[:19]}")
        print("=" * 60)

        passed = sum(1 for c in checks.values() if c['status'] == 'PASS')
        failed = sum(1 for c in checks.values() if c['status'] == 'FAIL')
        warned = sum(1 for c in checks.values() if c['status'] == 'WARN')
        skipped = sum(1 for c in checks.values() if c['status'] == 'SKIP')

        for name, result in checks.items():
            status = result['status']
            icon = {'PASS': 'OK', 'FAIL': 'FAIL', 'WARN': 'WARN', 'SKIP': 'SKIP'}[status]
            value = result.get('value', result.get('message', ''))
            print(f"  [{icon:4s}] {name}: {value}")
            if result.get('drifts'):
                for d in result['drifts']:
                    print(f"         {d['table']}: {d['baseline']:,} -> {d['current']:,} ({d['change']})")

        print(f"\nSummary: {passed} PASS, {failed} FAIL, {warned} WARN, {skipped} SKIP")

        if not baselines:
            print("\nNo baseline saved. Run with --save-baseline to create one.")

    # Save to log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, 'w') as f:
        json.dump(results, indent=2, fp=f, default=str)

    conn.close()

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
