"""
Edge Case Testing for Unified Matching Module
Tests CLI single-match and Python API with unusual inputs.
"""

import sys
import os
import traceback

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

def get_conn():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )

def test_match(pipeline, name, state=None, city=None, ein=None, address=None):
    """Run a single match and return results dict."""
    try:
        result = pipeline.match(
            source_name=name,
            state=state,
            city=city,
            ein=ein,
            address=address,
        )
        return {
            'input': name,
            'state': state or '',
            'matched': result.matched,
            'target': result.target_name if result.matched else '',
            'method': result.method if result.matched else '',
            'tier': result.tier if result.matched else '',
            'score': f"{result.score:.4f}" if result.matched and result.score else '',
            'error': '',
        }
    except Exception as e:
        return {
            'input': name,
            'state': state or '',
            'matched': False,
            'target': '',
            'method': '',
            'tier': '',
            'score': '',
            'error': str(e)[:80],
        }


def print_row(row, widths):
    """Print a table row."""
    parts = []
    for val, w in zip(row, widths):
        s = str(val)[:w]
        parts.append(s.ljust(w))
    print(' | '.join(parts))


def print_table(headers, rows):
    """Print a formatted table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], min(len(str(val)), 40))

    print_row(headers, widths)
    print('-+-'.join('-' * w for w in widths))
    for row in rows:
        print_row(row, widths)


def main():
    print("=" * 80)
    print("EDGE CASE TEST SUITE - Unified Matching Module")
    print("=" * 80)

    conn = get_conn()

    from scripts.matching.pipeline import MatchPipeline
    pipeline = MatchPipeline(conn, scenario='mergent_to_f7', skip_fuzzy=True)

    results = []

    # =====================================================
    # 1. LEGAL SUFFIX VARIATIONS
    # =====================================================
    print("\n--- Test Category 1: Legal Suffix Variations ---")
    suffix_tests = [
        ("Walmart Inc", "NY"),
        ("Walmart Corporation", "NY"),
        ("Walmart LLC", "NY"),
        ("Walmart Co", "NY"),
        ("Target Corp", "NY"),
        ("Target Corporation", "NY"),
        ("Target Incorporated", "NY"),
    ]
    for name, state in suffix_tests:
        r = test_match(pipeline, name, state=state)
        results.append(('SUFFIX', r))

    # =====================================================
    # 2. ABBREVIATIONS
    # =====================================================
    print("--- Test Category 2: Abbreviations ---")
    abbrev_tests = [
        ("St. Mary's Hospital", "NY"),
        ("Saint Marys Hospital", "NY"),
        ("Saint Mary's Hospital", "NY"),
        ("Mt Sinai Medical Center", "NY"),
        ("Mount Sinai Medical Center", "NY"),
        ("Intl Brotherhood of Teamsters", "NY"),
        ("International Brotherhood of Teamsters", "NY"),
    ]
    for name, state in abbrev_tests:
        r = test_match(pipeline, name, state=state)
        results.append(('ABBREV', r))

    # =====================================================
    # 3. SPECIAL CHARACTERS
    # =====================================================
    print("--- Test Category 3: Special Characters ---")
    special_tests = [
        ("AT&T", "NY"),
        ("AT & T", "NY"),
        ("Coca-Cola", "NY"),
        ("Coca Cola", "NY"),
        ("McDonald's", "NY"),
        ("McDonalds", "NY"),
        ("Ben & Jerry's", "NY"),
        ("Johnson & Johnson", "NJ"),
        ("Toys R Us", "NJ"),
        ("Marks & Spencer", "NY"),
    ]
    for name, state in special_tests:
        r = test_match(pipeline, name, state=state)
        results.append(('SPECIAL', r))

    # =====================================================
    # 4. VERY SHORT NAMES (Acronyms)
    # =====================================================
    print("--- Test Category 4: Very Short Names ---")
    short_tests = [
        ("IBM", "NY"),
        ("UPS", "NY"),
        ("ABC", "NY"),
        ("GE", "NY"),
        ("HP", "NY"),
        ("3M", "MN"),
        ("A", "NY"),
        ("AB", "NY"),
    ]
    for name, state in short_tests:
        r = test_match(pipeline, name, state=state)
        results.append(('SHORT', r))

    # =====================================================
    # 5. D/B/A NAMES
    # =====================================================
    print("--- Test Category 5: D/B/A Patterns ---")
    dba_tests = [
        ("John Smith DBA Quick Mart", "NY"),
        ("Quick Mart d/b/a Smith Stores", "NY"),
        ("Smith Enterprises doing business as Smith Foods", "NY"),
        ("ABC Inc d.b.a. XYZ Corp", "NY"),
    ]
    for name, state in dba_tests:
        r = test_match(pipeline, name, state=state)
        results.append(('DBA', r))

    # =====================================================
    # 6. MISSING / EMPTY PARAMETERS
    # =====================================================
    print("--- Test Category 6: Missing/Empty Parameters ---")

    # No state
    r = test_match(pipeline, "Walmart")
    results.append(('MISSING', r))

    # Empty name
    r = test_match(pipeline, "")
    results.append(('MISSING', r))

    # None name
    r = test_match(pipeline, None)
    results.append(('MISSING', {
        'input': 'None',
        'state': '',
        'matched': r['matched'] if isinstance(r, dict) else False,
        'target': r.get('target', '') if isinstance(r, dict) else '',
        'method': r.get('method', '') if isinstance(r, dict) else '',
        'tier': r.get('tier', '') if isinstance(r, dict) else '',
        'score': r.get('score', '') if isinstance(r, dict) else '',
        'error': r.get('error', '') if isinstance(r, dict) else '',
    }))

    # Whitespace only
    r = test_match(pipeline, "   ")
    results.append(('MISSING', r))

    # Single space
    r = test_match(pipeline, " ")
    results.append(('MISSING', r))

    # =====================================================
    # 7. INVALID / UNUSUAL INPUTS
    # =====================================================
    print("--- Test Category 7: Invalid/Unusual Inputs ---")

    # Very long name (200+ chars)
    long_name = "A" * 250
    r = test_match(pipeline, long_name, state="NY")
    results.append(('INVALID', {**r, 'input': f'"{long_name[:30]}..." (250 chars)'}))

    # Numeric only
    r = test_match(pipeline, "12345", state="NY")
    results.append(('INVALID', r))

    # All punctuation
    r = test_match(pipeline, "!@#$%^&*()", state="NY")
    results.append(('INVALID', r))

    # Unicode characters (use ASCII-safe name for display)
    unicode_name = "Caf\u00e9 de Flore"
    r = test_match(pipeline, unicode_name, state="NY")
    r['input'] = 'Cafe de Flore (unicode e)'
    results.append(('INVALID', r))

    # CJK characters - test but replace display name to avoid cp1252 crash
    cjk_name = "\u6771\u4eac\u682a\u5f0f\u4f1a\u793e"
    r = test_match(pipeline, cjk_name, state="NY")
    r['input'] = '<CJK chars>'
    results.append(('INVALID', r))

    # SQL injection attempt (should be safe via parameterized queries)
    r = test_match(pipeline, "'; DROP TABLE f7_employers_deduped; --", state="NY")
    results.append(('INVALID', r))

    # Very long state code
    r = test_match(pipeline, "Walmart", state="NEW YORK")
    results.append(('INVALID', r))

    # Invalid state code
    r = test_match(pipeline, "Walmart", state="ZZ")
    results.append(('INVALID', r))

    # Newlines in name
    r = test_match(pipeline, "Walmart\nInc", state="NY")
    results.append(('INVALID', r))

    # Tab in name
    r = test_match(pipeline, "Walmart\tInc", state="NY")
    results.append(('INVALID', r))

    # =====================================================
    # 8. REAL EMPLOYER NAMES (Validation)
    # =====================================================
    print("--- Test Category 8: Known Employers (Should Match) ---")
    known_tests = [
        ("New York Botanical Garden", "NY"),
        ("Alvin Ailey Dance Foundation", "NY"),
        ("City Harvest", "NY"),
    ]
    for name, state in known_tests:
        r = test_match(pipeline, name, state=state)
        results.append(('KNOWN', r))

    # =====================================================
    # PRINT SUMMARY TABLE
    # =====================================================
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    headers = ['Category', 'Input', 'State', 'Matched', 'Target', 'Method', 'Tier', 'Error']
    rows = []
    for cat, r in results:
        rows.append([
            cat,
            str(r['input'])[:35],
            r['state'],
            'YES' if r['matched'] else 'NO',
            str(r['target'])[:35] if r['target'] else '',
            r['method'],
            r['tier'],
            r['error'][:35] if r['error'] else '',
        ])

    print_table(headers, rows)

    # =====================================================
    # ERROR SUMMARY
    # =====================================================
    errors = [(cat, r) for cat, r in results if r['error']]
    crashes = [(cat, r) for cat, r in results if r['error'] and 'Error' in r['error']]

    print(f"\n--- Summary ---")
    print(f"Total tests: {len(results)}")
    print(f"Matched: {sum(1 for _, r in results if r['matched'])}")
    print(f"No match: {sum(1 for _, r in results if not r['matched'] and not r['error'])}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\n--- Errors Detail ---")
        for cat, r in errors:
            print(f"  [{cat}] Input: {str(r['input'])[:40]}")
            print(f"         Error: {r['error']}")

    # =====================================================
    # NORMALIZER EDGE CASES
    # =====================================================
    print("\n" + "=" * 80)
    print("NORMALIZER EDGE CASES")
    print("=" * 80)

    from scripts.matching.normalizer import normalize_employer_name

    norm_tests = [
        ("", "standard"),
        ("   ", "standard"),
        (None, "standard"),
        ("A", "standard"),
        ("AB", "standard"),
        ("Inc.", "standard"),
        ("The", "aggressive"),
        ("!!!", "standard"),
        ("12345", "standard"),
        ("A" * 500, "standard"),
        ("Cafe", "standard"),
        ("Tokyo", "standard"),
        ("St. Mary's Hospital", "standard"),
        ("St. Mary's Hospital", "aggressive"),
        ("St. Mary's Hospital", "fuzzy"),
        ("AT&T Inc.", "standard"),
        ("AT&T Inc.", "aggressive"),
        ("doing business as Quick Mart", "standard"),
        ("McDonald's Corp.", "standard"),
        ("New\nYork\tHospital", "standard"),
    ]

    headers2 = ['Input', 'Level', 'Output', 'Error']
    rows2 = []
    for name, level in norm_tests:
        try:
            result = normalize_employer_name(name, level)
            rows2.append([
                repr(name)[:30] if name is not None else 'None',
                level,
                repr(result)[:40],
                '',
            ])
        except Exception as e:
            rows2.append([
                repr(name)[:30] if name is not None else 'None',
                level,
                '',
                str(e)[:40],
            ])

    print_table(headers2, rows2)

    norm_errors = [r for r in rows2 if r[3]]
    print(f"\nNormalizer tests: {len(norm_tests)}")
    print(f"Normalizer errors: {len(norm_errors)}")
    if norm_errors:
        print("Errors:")
        for r in norm_errors:
            print(f"  Input={r[0]}, Level={r[1]}, Error={r[3]}")

    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
