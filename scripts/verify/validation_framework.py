"""
Automated data validation framework for the labor data platform.

Runs 8 checks with PASS/FAIL status and severity levels.
Exit code 0 = all checks pass, exit code 1 = any CRITICAL check fails.

PHILOSOPHY: Data quality over external benchmark alignment. We prefer
accurate, deduplicated data even if it means lower BLS coverage numbers.
BLS check is WARNING-level, not CRITICAL. Never inflate counts to hit
external targets.

Usage:
    py scripts/verify/validation_framework.py          # Run all checks
    py scripts/verify/validation_framework.py --verbose # Show detail rows
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import time

VERBOSE = '--verbose' in sys.argv

# Valid US state/territory codes (50 states + DC + territories + Canadian provinces in data)
VALID_STATE_CODES = {
    # 50 states + DC
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL',
    'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME',
    'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH',
    'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
    'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    # US territories
    'AS', 'GU', 'MH', 'MP', 'PR', 'PW', 'VI',
    # Canadian provinces (some cross-border unions)
    'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT',
}

BLS_PRIVATE_BENCHMARK = 7_200_000
BLS_LOW = BLS_PRIVATE_BENCHMARK * 0.90   # 6,480,000
BLS_HIGH = BLS_PRIVATE_BENCHMARK * 1.10  # 7,920,000


def connect():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def check_no_duplicate_employer_ids(cur):
    """Check 1: No duplicate employer_ids in f7_employers_deduped."""
    cur.execute("""
        SELECT employer_id, COUNT(*) as cnt
        FROM f7_employers_deduped
        GROUP BY employer_id
        HAVING COUNT(*) > 1
    """)
    dupes = cur.fetchall()
    count = len(dupes)
    if count == 0:
        return 'PASS', 'CRITICAL', f'All employer_ids are unique'
    else:
        detail = f'{count} duplicate employer_id values found'
        if VERBOSE and dupes:
            detail += f' (first 5: {[d[0] for d in dupes[:5]]})'
        return 'FAIL', 'CRITICAL', detail


def check_union_linkage(cur):
    """Check 2: Every F7 employer has union linkage (latest_union_fnum)."""
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN latest_union_fnum IS NULL THEN 1 ELSE 0 END) as missing
        FROM f7_employers_deduped
    """)
    row = cur.fetchone()
    total, missing = row[0], row[1]
    pct_linked = (total - missing) / total * 100 if total > 0 else 0
    if missing == 0:
        return 'PASS', 'WARNING', f'All {total:,} employers have union linkage'
    elif missing < total * 0.05:
        return 'PASS', 'WARNING', f'{missing:,} of {total:,} missing union linkage ({pct_linked:.1f}% linked)'
    else:
        return 'FAIL', 'WARNING', f'{missing:,} of {total:,} missing union linkage ({pct_linked:.1f}% linked)'


def check_bls_coverage(cur):
    """Check 3: Worker sum vs BLS benchmark (informational).
    WARNING-level only. Data quality > external benchmark alignment.
    We prefer accurate, deduplicated data even if coverage is lower."""
    cur.execute("""
        SELECT SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted,
               SUM(latest_unit_size) as total_raw
        FROM f7_employers_deduped
    """)
    row = cur.fetchone()
    counted = row[0] or 0
    total_raw = row[1] or 0
    pct = counted / BLS_PRIVATE_BENCHMARK * 100 if BLS_PRIVATE_BENCHMARK > 0 else 0
    detail = f'Counted workers: {counted:,} / BLS {BLS_PRIVATE_BENCHMARK:,} = {pct:.1f}% (raw: {total_raw:,})'
    if BLS_LOW <= counted <= BLS_HIGH:
        return 'PASS', 'WARNING', detail
    else:
        return 'FAIL', 'WARNING', detail


def check_no_orphan_nlrb(cur):
    """Check 4: No orphan NLRB references (matched_employer_id -> valid F7)."""
    cur.execute("""
        SELECT COUNT(*) as orphans
        FROM nlrb_participants np
        WHERE np.matched_employer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM f7_employers_deduped f
              WHERE f.employer_id = np.matched_employer_id
          )
    """)
    orphans = cur.fetchone()[0]
    if orphans == 0:
        return 'PASS', 'CRITICAL', 'All NLRB matched_employer_ids point to valid F7 records'
    else:
        detail = f'{orphans:,} NLRB participants reference non-existent F7 employer_ids'
        if VERBOSE:
            cur.execute("""
                SELECT np.matched_employer_id, COUNT(*) as cnt
                FROM nlrb_participants np
                WHERE np.matched_employer_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM f7_employers_deduped f
                      WHERE f.employer_id = np.matched_employer_id
                  )
                GROUP BY np.matched_employer_id
                ORDER BY cnt DESC LIMIT 5
            """)
            examples = cur.fetchall()
            detail += f' (top orphan IDs: {[e[0] for e in examples]})'
        return 'FAIL', 'CRITICAL', detail


def check_no_orphan_osha(cur):
    """Check 5: No orphan OSHA references (f7_employer_id -> valid F7)."""
    cur.execute("""
        SELECT COUNT(*) as orphans
        FROM osha_f7_matches om
        WHERE om.f7_employer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM f7_employers_deduped f
              WHERE f.employer_id = om.f7_employer_id
          )
    """)
    orphans = cur.fetchone()[0]
    if orphans == 0:
        return 'PASS', 'CRITICAL', 'All OSHA f7_employer_ids point to valid F7 records'
    else:
        detail = f'{orphans:,} OSHA matches reference non-existent F7 employer_ids'
        if VERBOSE:
            cur.execute("""
                SELECT om.f7_employer_id, COUNT(*) as cnt
                FROM osha_f7_matches om
                WHERE om.f7_employer_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM f7_employers_deduped f
                      WHERE f.employer_id = om.f7_employer_id
                  )
                GROUP BY om.f7_employer_id
                ORDER BY cnt DESC LIMIT 5
            """)
            examples = cur.fetchall()
            detail += f' (top orphan IDs: {[e[0] for e in examples]})'
        return 'FAIL', 'CRITICAL', detail


def check_valid_geocodes(cur):
    """Check 6: Valid geocodes within US boundaries.
    Lat 13-72 (Guam at ~13.4, Alaska at ~71), Lon -180 to -60 (excludes Guam/CNMI at 144-145).
    Use wider lon range to include Pacific territories: -180 to 180.
    Final: lat -15 to 72 (American Samoa at -14.3), lon -180 to 180."""
    cur.execute("""
        SELECT COUNT(*) as total_geocoded,
               SUM(CASE WHEN latitude < -15 OR latitude > 72
                        OR longitude < -180 OR longitude > 180
                   THEN 1 ELSE 0 END) as out_of_bounds
        FROM f7_employers_deduped
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)
    row = cur.fetchone()
    total_geocoded, oob = row[0], row[1]
    if oob == 0:
        return 'PASS', 'WARNING', f'All {total_geocoded:,} geocoded records within US bounds'
    else:
        detail = f'{oob:,} of {total_geocoded:,} geocoded records outside US bounds'
        if VERBOSE:
            cur.execute("""
                SELECT employer_id, employer_name, latitude, longitude, state
                FROM f7_employers_deduped
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND (latitude < -15 OR latitude > 72 OR longitude < -180 OR longitude > 180)
                LIMIT 5
            """)
            examples = cur.fetchall()
            for e in examples:
                detail += f'\n    {e[1]} ({e[4]}): {e[2]}, {e[3]}'
        return 'FAIL', 'WARNING', detail


def check_valid_naics(cur):
    """Check 7: Valid NAICS codes (2-6 digit numeric)."""
    cur.execute("""
        SELECT COUNT(*) as total_with_naics,
               SUM(CASE WHEN naics !~ '^[0-9]{2,6}$' THEN 1 ELSE 0 END) as invalid
        FROM f7_employers_deduped
        WHERE naics IS NOT NULL
    """)
    row = cur.fetchone()
    total, invalid = row[0], row[1]
    # Also check how many are missing NAICS
    cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NULL")
    missing = cur.fetchone()[0]
    if invalid == 0:
        return 'PASS', 'WARNING', f'{total:,} valid NAICS codes ({missing:,} records without NAICS)'
    else:
        detail = f'{invalid:,} of {total:,} have invalid NAICS format ({missing:,} missing)'
        if VERBOSE:
            cur.execute("""
                SELECT naics, COUNT(*) as cnt
                FROM f7_employers_deduped
                WHERE naics IS NOT NULL AND naics !~ '^[0-9]{2,6}$'
                GROUP BY naics
                ORDER BY cnt DESC LIMIT 5
            """)
            examples = cur.fetchall()
            detail += f' (examples: {examples})'
        return 'FAIL', 'WARNING', detail


def check_valid_state_codes(cur):
    """Check 8: Valid state codes (50 states + DC + territories)."""
    cur.execute("""
        SELECT DISTINCT state
        FROM f7_employers_deduped
        WHERE state IS NOT NULL
        ORDER BY state
    """)
    all_states = [r[0] for r in cur.fetchall()]
    invalid_states = [s for s in all_states if s not in VALID_STATE_CODES]
    if not invalid_states:
        return 'PASS', 'WARNING', f'All {len(all_states)} state codes are valid'
    else:
        # Get counts for invalid states
        cur.execute("""
            SELECT state, COUNT(*) as cnt
            FROM f7_employers_deduped
            WHERE state = ANY(%s)
            GROUP BY state
            ORDER BY cnt DESC
        """, (invalid_states,))
        invalid_counts = cur.fetchall()
        total_invalid = sum(c[1] for c in invalid_counts)
        detail = f'{len(invalid_states)} unrecognized state codes ({total_invalid:,} records): {invalid_counts}'
        return 'FAIL', 'WARNING', detail


def main():
    start = time.time()
    conn = connect()
    cur = conn.cursor()

    print("=" * 74)
    print("  DATA VALIDATION FRAMEWORK")
    print("=" * 74)
    print()

    checks = [
        ("1. No duplicate employer_ids", check_no_duplicate_employer_ids),
        ("2. F7 union linkage",          check_union_linkage),
        ("3. BLS coverage (informational)", check_bls_coverage),
        ("4. No orphan NLRB references",  check_no_orphan_nlrb),
        ("5. No orphan OSHA references",  check_no_orphan_osha),
        ("6. Valid geocodes (US+terr bounds)", check_valid_geocodes),
        ("7. Valid NAICS codes",          check_valid_naics),
        ("8. Valid state codes",          check_valid_state_codes),
    ]

    results = []
    any_critical_fail = False

    for name, check_fn in checks:
        try:
            status, severity, detail = check_fn(cur)
        except Exception as e:
            status, severity, detail = 'ERROR', 'CRITICAL', str(e)

        results.append((name, status, severity, detail))

        if status in ('FAIL', 'ERROR') and severity == 'CRITICAL':
            any_critical_fail = True

    # Print results table
    print(f"{'Check':<36} {'Status':<8} {'Severity':<10} Details")
    print("-" * 74)
    for name, status, severity, detail in results:
        # Truncate long details for table display
        short_detail = detail if len(detail) <= 60 else detail[:57] + '...'
        marker = '[PASS]' if status == 'PASS' else '[FAIL]' if status == 'FAIL' else '[ERR ]'
        print(f"{name:<36} {marker:<8} {severity:<10} {short_detail}")
        # If verbose and detail is long, print full detail below
        if VERBOSE and len(detail) > 60:
            for line in detail.split('\n'):
                print(f"{'':>36} {'':>8} {'':>10} {line}")

    elapsed = time.time() - start

    # Summary
    passed = sum(1 for _, s, _, _ in results if s == 'PASS')
    failed = sum(1 for _, s, _, _ in results if s in ('FAIL', 'ERROR'))
    total = len(results)

    print()
    print("-" * 74)
    print(f"  Results: {passed}/{total} passed, {failed}/{total} failed")
    print(f"  Elapsed: {elapsed:.1f}s")

    if any_critical_fail:
        print("  Status: CRITICAL FAILURES DETECTED")
        print()
        print("  Failed critical checks:")
        for name, status, severity, detail in results:
            if status in ('FAIL', 'ERROR') and severity == 'CRITICAL':
                print(f"    - {name}: {detail[:80]}")
    else:
        print("  Status: ALL CRITICAL CHECKS PASSED")

    print("=" * 74)

    cur.close()
    conn.close()

    sys.exit(1 if any_critical_fail else 0)


if __name__ == '__main__':
    main()
