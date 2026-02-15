"""
Compare Teamsters locals from official website vs database
Generates reconciliation reports identifying gaps and discrepancies
"""

import psycopg2
import csv
from collections import defaultdict
from datetime import datetime
import os

from db_config import get_connection
# Database connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def get_database_locals():
    """Fetch Teamsters locals from unions_master database."""

    conn = get_connection()
    cur = conn.cursor()

    # Get all IBT locals (LU designation)
    query = """
        SELECT
            f_num,
            union_name,
            local_number,
            desig_name,
            city,
            state,
            members,
            yr_covered
        FROM unions_master
        WHERE aff_abbr = 'IBT'
          AND desig_name IN ('LU', 'LU   ')
          AND local_number IS NOT NULL
          AND local_number != '0'
        ORDER BY local_number::integer
    """

    cur.execute(query)
    rows = cur.fetchall()

    locals_data = []
    for row in rows:
        locals_data.append({
            'f_num': row[0],
            'union_name': row[1],
            'local_number': int(row[2]) if row[2] and row[2].isdigit() else row[2],
            'desig_name': row[3].strip() if row[3] else '',
            'city': row[4] or '',
            'state': row[5] or '',
            'members': row[6] or 0,
            'yr_covered': row[7] or ''
        })

    # Also get summary stats
    cur.execute("""
        SELECT
            COUNT(*) as total_ibt,
            COUNT(DISTINCT local_number) as distinct_locals,
            COUNT(*) FILTER (WHERE desig_name IN ('LU', 'LU   ')) as lu_count,
            COUNT(DISTINCT state) as states
        FROM unions_master
        WHERE aff_abbr = 'IBT'
    """)
    stats = cur.fetchone()

    conn.close()

    return locals_data, {
        'total_ibt': stats[0],
        'distinct_locals': stats[1],
        'lu_count': stats[2],
        'states': stats[3]
    }


def load_official_locals(filename='teamsters_official_locals.csv'):
    """Load scraped Teamsters locals from CSV."""

    locals_data = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                local_num = row.get('local_number', '')
                if local_num:
                    try:
                        local_num = int(local_num)
                    except ValueError:
                        pass
                    locals_data.append({
                        'local_number': local_num,
                        'local_name': row.get('local_name', ''),
                        'address': row.get('address', ''),
                        'city': row.get('city', ''),
                        'state': row.get('state', ''),
                        'zip': row.get('zip', ''),
                        'phone': row.get('phone', ''),
                        'website': row.get('website', ''),
                        'leadership_name': row.get('leadership_name', ''),
                        'leadership_title': row.get('leadership_title', ''),
                        'divisions': row.get('divisions', '')
                    })
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return []

    return locals_data


def export_database_locals(locals_data, filename='teamsters_database_locals.csv'):
    """Export database locals to CSV."""

    fieldnames = ['f_num', 'union_name', 'local_number', 'desig_name',
                  'city', 'state', 'members', 'yr_covered']

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(locals_data)

    print(f"Exported {len(locals_data)} database locals to {filename}")


def compare_locals(official_locals, db_locals):
    """Compare official website locals vs database locals."""

    # Create lookup dictionaries by local number
    official_by_num = {loc['local_number']: loc for loc in official_locals}
    db_by_num = {}

    # Handle potential duplicates in database
    for loc in db_locals:
        num = loc['local_number']
        if num in db_by_num:
            # Keep the one with more members or more recent year
            existing = db_by_num[num]
            if (loc.get('members', 0) or 0) > (existing.get('members', 0) or 0):
                db_by_num[num] = loc
        else:
            db_by_num[num] = loc

    official_nums = set(official_by_num.keys())
    db_nums = set(db_by_num.keys())

    # Find gaps
    missing_from_db = official_nums - db_nums
    not_on_website = db_nums - official_nums
    in_both = official_nums & db_nums

    # Detailed comparison for matches
    comparison_results = []
    discrepancies = []

    for num in sorted(in_both):
        off = official_by_num[num]
        db = db_by_num[num]

        result = {
            'local_number': num,
            'official_name': off.get('local_name', ''),
            'db_name': db.get('union_name', ''),
            'official_city': off.get('city', ''),
            'db_city': db.get('city', ''),
            'official_state': off.get('state', ''),
            'db_state': db.get('state', ''),
            'db_members': db.get('members', 0),
            'db_f_num': db.get('f_num', ''),
            'match_status': 'MATCH'
        }

        # Check for discrepancies
        issues = []

        # State mismatch
        if off.get('state', '').upper() != (db.get('state', '') or '').upper():
            if off.get('state') and db.get('state'):
                issues.append(f"state: {off.get('state')} vs {db.get('state')}")

        # City mismatch (fuzzy - just check if different)
        off_city = (off.get('city', '') or '').upper().strip()
        db_city = (db.get('city', '') or '').upper().strip()
        if off_city and db_city and off_city != db_city:
            # Allow for minor variations
            if not (off_city in db_city or db_city in off_city):
                issues.append(f"city: {off.get('city')} vs {db.get('city')}")

        if issues:
            result['match_status'] = 'DISCREPANCY'
            result['issues'] = '; '.join(issues)
            discrepancies.append(result)

        comparison_results.append(result)

    return {
        'missing_from_db': [official_by_num[n] for n in sorted(missing_from_db)],
        'not_on_website': [db_by_num[n] for n in sorted(not_on_website)],
        'comparison': comparison_results,
        'discrepancies': discrepancies,
        'stats': {
            'official_count': len(official_locals),
            'db_count': len(db_locals),
            'db_unique_locals': len(db_by_num),
            'missing_from_db': len(missing_from_db),
            'not_on_website': len(not_on_website),
            'matched': len(in_both),
            'discrepancies': len(discrepancies)
        }
    }


def save_comparison_report(results, prefix='teamsters'):
    """Save comparison results to CSV files."""

    timestamp = datetime.now().strftime('%Y%m%d')

    # Missing from DB
    if results['missing_from_db']:
        filename = f"{prefix}_missing_from_db.csv"
        fieldnames = ['local_number', 'local_name', 'city', 'state', 'address', 'zip', 'phone', 'website']
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results['missing_from_db'])
        print(f"Saved {len(results['missing_from_db'])} missing locals to {filename}")

    # Not on website
    if results['not_on_website']:
        filename = f"{prefix}_not_on_website.csv"
        fieldnames = ['local_number', 'union_name', 'city', 'state', 'members', 'f_num', 'yr_covered']
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results['not_on_website'])
        print(f"Saved {len(results['not_on_website'])} locals not on website to {filename}")

    # Full comparison
    filename = f"{prefix}_comparison_report.csv"
    fieldnames = ['local_number', 'match_status', 'official_name', 'db_name',
                  'official_city', 'db_city', 'official_state', 'db_state',
                  'db_members', 'db_f_num', 'issues']
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results['comparison'])
    print(f"Saved comparison report to {filename}")

    # Discrepancies only
    if results['discrepancies']:
        filename = f"{prefix}_discrepancies.csv"
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results['discrepancies'])
        print(f"Saved {len(results['discrepancies'])} discrepancies to {filename}")


def print_summary(results, db_stats):
    """Print summary statistics."""

    stats = results['stats']

    print("\n" + "="*60)
    print("TEAMSTERS LOCALS COMPARISON SUMMARY")
    print("="*60)

    print(f"\nDatabase Statistics:")
    print(f"   Total IBT records: {db_stats['total_ibt']}")
    print(f"   Distinct local numbers: {db_stats['distinct_locals']}")
    print(f"   LU designation records: {db_stats['lu_count']}")
    print(f"   States covered: {db_stats['states']}")

    print(f"\nOfficial Website:")
    print(f"   Locals listed: {stats['official_count']}")

    print(f"\nComparison Results:")
    print(f"   Matched locals: {stats['matched']}")
    print(f"   Missing from DB: {stats['missing_from_db']}")
    print(f"   Not on website: {stats['not_on_website']}")
    print(f"   Discrepancies: {stats['discrepancies']}")

    if stats['official_count'] > 0:
        coverage = (stats['matched'] / stats['official_count']) * 100
        print(f"\nDatabase Coverage: {coverage:.1f}%")

    print("\n" + "="*60)


def main():
    print("Teamsters Locals Comparison Tool")
    print("-" * 40)

    # Step 1: Get database locals
    print("\n1. Fetching database locals...")
    db_locals, db_stats = get_database_locals()
    print(f"   Found {len(db_locals)} IBT locals in database")

    # Export database locals to CSV
    export_database_locals(db_locals)

    # Step 2: Load official locals (from scraper output)
    print("\n2. Loading official locals from CSV...")
    official_locals = load_official_locals()

    if not official_locals:
        print("\n⚠️  No official locals found.")
        print("   Please run scrape_teamsters_locals.py first")
        print("   Or the website data may need manual extraction")

        # Still show database summary
        print_summary({
            'stats': {
                'official_count': 0,
                'db_count': len(db_locals),
                'db_unique_locals': len(set(l['local_number'] for l in db_locals)),
                'missing_from_db': 0,
                'not_on_website': 0,
                'matched': 0,
                'discrepancies': 0
            },
            'missing_from_db': [],
            'not_on_website': [],
            'comparison': [],
            'discrepancies': []
        }, db_stats)
        return

    print(f"   Found {len(official_locals)} locals from official website")

    # Step 3: Compare
    print("\n3. Comparing datasets...")
    results = compare_locals(official_locals, db_locals)

    # Step 4: Save reports
    print("\n4. Saving reports...")
    save_comparison_report(results)

    # Step 5: Print summary
    print_summary(results, db_stats)

    # Show some examples of issues
    if results['missing_from_db'][:5]:
        print("\nSample locals missing from database:")
        for loc in results['missing_from_db'][:5]:
            print(f"   Local {loc['local_number']}: {loc.get('city', '')}, {loc.get('state', '')}")

    if results['not_on_website'][:5]:
        print("\nSample locals not on website (possibly merged/closed):")
        for loc in results['not_on_website'][:5]:
            print(f"   Local {loc['local_number']}: {loc.get('city', '')}, {loc.get('state', '')} ({loc.get('members', 0):,} members)")


if __name__ == '__main__':
    main()
