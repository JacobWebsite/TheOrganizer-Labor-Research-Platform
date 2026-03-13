"""
Check documentation consistency against live database.

Usage:
    py scripts/maintenance/check_doc_consistency.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CLAUDE_MD = os.path.join(PROJECT_ROOT, 'CLAUDE.md')


def read_claude_md():
    """Read CLAUDE.md and return its content."""
    with open(CLAUDE_MD, 'r', encoding='utf-8') as f:
        return f.read()


def extract_claims(text):
    """Extract testable claims from CLAUDE.md using regex."""
    claims = {}

    # Backend test count: "~942 tests" or "~960 tests"
    m = re.search(r'~(\d+)\s+tests?\s+passing.*?0\s+failure', text)
    if m:
        claims['backend_test_count'] = int(m.group(1))

    # Frontend test count: "~184 tests"
    m = re.search(r'frontend.*?~(\d+)\s+tests?\s+passing', text, re.IGNORECASE)
    if m:
        claims['frontend_test_count'] = int(m.group(1))

    # mv_unified_scorecard row count: "146,863"
    m = re.search(r'mv_unified_scorecard.*?(\d[\d,]+)\s+rows', text)
    if m:
        claims['mv_unified_scorecard_rows'] = int(m.group(1).replace(',', ''))

    # mv_target_scorecard row count: "4,386,205"
    m = re.search(r'mv_target_scorecard.*?(\d[\d,]+)\s+rows', text)
    if m:
        claims['mv_target_scorecard_rows'] = int(m.group(1).replace(',', ''))

    # Factor count: "10 factors"
    m = re.search(r'(\d+)\s+factors?\s+\(each\s+0-10\)', text)
    if m:
        claims['factor_count'] = int(m.group(1))

    # Materialized view count (from architecture section)
    # Count all mv_ references for approximate MV count
    mv_names = set(re.findall(r'mv_\w+', text))
    if mv_names:
        claims['mv_names_mentioned'] = mv_names

    # UML row count if mentioned
    m = re.search(r'unified_match_log.*?(\d[\d,]+)', text)
    if m:
        claims['uml_rows'] = int(m.group(1).replace(',', ''))

    return claims


def get_live_counts(conn):
    """Query the live database for actual counts."""
    cur = conn.cursor()
    live = {}

    # MV row counts
    for mv in ['mv_unified_scorecard', 'mv_target_scorecard']:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {mv}")
            live[f'{mv}_rows'] = cur.fetchone()[0]
        except Exception:
            conn.rollback()
            live[f'{mv}_rows'] = None

    # Total MV count
    cur.execute("""
        SELECT COUNT(*) FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'm'
    """)
    live['mv_count'] = cur.fetchone()[0]

    # List MV names
    cur.execute("""
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'm'
        ORDER BY c.relname
    """)
    live['mv_names_actual'] = {r[0] for r in cur.fetchall()}

    # Table count
    cur.execute("""
        SELECT COUNT(*) FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
    """)
    live['table_count'] = cur.fetchone()[0]

    # Factor count from mv_unified_scorecard columns
    cur.execute("""
        SELECT attname FROM pg_attribute
        WHERE attrelid = 'mv_unified_scorecard'::regclass
          AND attnum > 0 AND NOT attisdropped
          AND attname LIKE 'score_%%'
          AND attname NOT IN ('score_anger', 'score_stability', 'score_leverage',
                              'score_tier', 'score_tier_legacy', 'score_percentile',
                              'weighted_score', 'unified_score')
    """)
    live['factor_columns'] = [r[0] for r in cur.fetchall()]
    # +1 for research (counted in factors_available via has_research, no score_ column)
    live['factor_count'] = len(live['factor_columns']) + 1

    # UML rows
    try:
        cur.execute("SELECT COUNT(*) FROM unified_match_log")
        live['uml_rows'] = cur.fetchone()[0]
    except Exception:
        conn.rollback()
        live['uml_rows'] = None

    cur.close()
    return live


def get_test_count():
    """Run pytest --collect-only to count backend tests."""
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', 'tests/', '--collect-only', '-q'],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=60
        )
        # Count lines that look like test items
        count = 0
        for line in result.stdout.splitlines():
            if '::test_' in line or '::Test' in line:
                count += 1
        if count == 0:
            # Try parsing "N selected"
            for line in result.stdout.splitlines():
                if 'selected' in line:
                    parts = line.split()
                    for part in parts:
                        if part.isdigit():
                            return int(part)
        return count if count > 0 else None
    except Exception:
        return None


def check_consistency():
    """Main consistency check logic."""
    print("=" * 60)
    print("  DOC CONSISTENCY CHECK")
    print("=" * 60)

    # Read claims from CLAUDE.md
    text = read_claude_md()
    claims = extract_claims(text)
    print(f"\n  Extracted {len(claims)} testable claims from CLAUDE.md")

    # Get live data
    conn = get_connection()
    try:
        live = get_live_counts(conn)
    finally:
        conn.close()

    test_count = get_test_count()

    mismatches = []
    matches = []

    # Check MV row counts
    for mv in ['mv_unified_scorecard', 'mv_target_scorecard']:
        claim_key = f'{mv}_rows'
        if claim_key in claims and live.get(claim_key) is not None:
            claimed = claims[claim_key]
            actual = live[claim_key]
            pct_diff = abs(actual - claimed) / max(claimed, 1) * 100
            if pct_diff > 5:
                mismatches.append(
                    f"{mv} rows: doc says {claimed:,}, actual is {actual:,} ({pct_diff:.1f}% diff)"
                )
            else:
                matches.append(f"{mv} rows: doc={claimed:,}, actual={actual:,} (OK)")

    # Check factor count
    if 'factor_count' in claims:
        claimed = claims['factor_count']
        actual = live.get('factor_count', 0)
        if claimed != actual:
            mismatches.append(
                f"Factor count: doc says {claimed}, actual score_ columns = {actual} "
                f"({', '.join(live.get('factor_columns', []))})"
            )
        else:
            matches.append(f"Factor count: doc={claimed}, actual={actual} (OK)")

    # Check backend test count
    if 'backend_test_count' in claims and test_count is not None:
        claimed = claims['backend_test_count']
        pct_diff = abs(test_count - claimed) / max(claimed, 1) * 100
        if pct_diff > 10:
            mismatches.append(
                f"Backend tests: doc says ~{claimed}, actual collected = {test_count} ({pct_diff:.1f}% diff)"
            )
        else:
            matches.append(f"Backend tests: doc=~{claimed}, actual={test_count} (OK)")

    # Check MV names mentioned vs actual
    if 'mv_names_mentioned' in claims:
        mentioned = claims['mv_names_mentioned']
        actual = live.get('mv_names_actual', set())
        missing_in_db = mentioned - actual
        if missing_in_db:
            mismatches.append(
                f"MVs mentioned in docs but missing from DB: {', '.join(sorted(missing_in_db))}"
            )
        new_in_db = actual - mentioned
        if new_in_db:
            # This is informational, not necessarily a mismatch
            matches.append(
                f"MVs in DB but not mentioned in CLAUDE.md: {', '.join(sorted(new_in_db))} (info)"
            )

    # Check UML rows
    if 'uml_rows' in claims and live.get('uml_rows') is not None:
        claimed = claims['uml_rows']
        actual = live['uml_rows']
        pct_diff = abs(actual - claimed) / max(claimed, 1) * 100
        if pct_diff > 10:
            mismatches.append(
                f"UML rows: doc says {claimed:,}, actual is {actual:,} ({pct_diff:.1f}% diff)"
            )
        else:
            matches.append(f"UML rows: doc={claimed:,}, actual={actual:,} (OK)")

    # Print results
    print(f"\n  MATCHING ({len(matches)}):")
    for m in matches:
        print(f"    [OK] {m}")

    if mismatches:
        print(f"\n  MISMATCHES ({len(mismatches)}):")
        for m in mismatches:
            print(f"    [!!] {m}")
    else:
        print("\n  No mismatches found -- docs are consistent with live DB.")

    print()
    return len(mismatches)


def main():
    mismatches = check_consistency()
    sys.exit(1 if mismatches > 0 else 0)


if __name__ == '__main__':
    main()
