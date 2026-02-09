"""
SEIU NJ Member-to-Employer Matching Reconciliation
===================================================
Maximizes matching of SEIU NJ State Council members (~20,000) to employers
across all data sources (F7, NLRB, VR).

Scope includes:
- SEIU locals in NJ
- Workers United (WU) - SEIU affiliate
- 32BJ and 1199 (NY-based, cover NJ)
- CIR (Committee of Interns and Residents)
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import re
from datetime import datetime
from collections import defaultdict

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Output directory
OUTPUT_DIR = r'C:\Users\jakew\Downloads\labor-data-project\output'

# SEIU NJ State Council Scope
SEIU_NJ_AFFILIATIONS = ['SEIU', 'WU']  # SEIU + Workers United

SEIU_NJ_FNUMS = [
    '541343',   # SEIU NJ main (10,862)
    '537082',   # Local 617 (1,306)
    '4005',     # Local 175 (743)
    '542113',   # Local 32 NJ (413)
    '544405',   # Workers United NJ (7,554)
    '137',      # SEIU National (files F7s)
    '11661',    # 32BJ NY (covers NJ)
    '31847',    # 1199 NY (covers NJ)
]

# Union name patterns for normalization
UNION_NAME_PATTERNS = {
    '32BJ': [r'32\s*BJ', r'32-?BJ', r'LOCAL\s*32\s*BJ'],
    '1199': [r'1199', r'NUHHCE', r'NATIONAL UNION.*HEALTHCARE'],
    'WORKERS_UNITED': [r'WORKERS\s*UNITED', r'LDFS', r'LAUNDRY.*DISTRIBUTION.*FOOD'],
    'CIR': [r'COMMITTEE.*INTERNS.*RESIDENTS', r'\bCIR\b'],
}


def normalize_employer_name(name):
    """Normalize employer name for matching."""
    if not name:
        return ''

    # Uppercase
    name = name.upper()

    # Remove common suffixes
    suffixes = [
        r'\s+INC\.?$', r'\s+LLC\.?$', r'\s+LLP\.?$', r'\s+LP\.?$',
        r'\s+CORP\.?$', r'\s+CORPORATION$', r'\s+CO\.?$', r'\s+COMPANY$',
        r'\s+D/B/A\s+.*$', r'\s+DBA\s+.*$', r'\s+A/K/A\s+.*$',
        r'\s+OF\s+NEW\s+JERSEY$', r'\s+OF\s+NJ$',
    ]
    for suffix in suffixes:
        name = re.sub(suffix, '', name)

    # Remove punctuation except alphanumeric and space
    name = re.sub(r'[^\w\s]', ' ', name)

    # Collapse whitespace
    name = ' '.join(name.split())

    return name.strip()


def categorize_union_name(name):
    """Categorize union name into normalized local type."""
    if not name:
        return 'OTHER_SEIU'

    name_upper = name.upper()

    for category, patterns in UNION_NAME_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, name_upper):
                return category

    return 'OTHER_SEIU'


def calculate_match_score(name1, name2, city1=None, city2=None):
    """Calculate fuzzy match score between two employer names."""
    if not name1 or not name2:
        return 0.0

    norm1 = normalize_employer_name(name1)
    norm2 = normalize_employer_name(name2)

    if not norm1 or not norm2:
        return 0.0

    # Exact match after normalization
    if norm1 == norm2:
        return 1.0

    # Token-based matching
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard similarity
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    jaccard = len(intersection) / len(union)

    # Boost for city match
    city_boost = 0.0
    if city1 and city2:
        if city1.upper().strip() == city2.upper().strip():
            city_boost = 0.1

    return min(jaccard + city_boost, 1.0)


def get_seiu_nj_membership():
    """Get SEIU NJ State Council membership from unions_master."""
    print("\n" + "=" * 80)
    print("STEP 1: SEIU NJ State Council Membership Analysis")
    print("=" * 80)

    # NJ-based SEIU and Workers United locals
    cur.execute("""
        SELECT f_num, union_name, local_number, members, aff_abbr, desig_name
        FROM unions_master
        WHERE state = 'NJ'
        AND aff_abbr IN ('SEIU', 'WU')
        ORDER BY members DESC NULLS LAST
    """)
    nj_locals = cur.fetchall()

    print(f"\nNJ-based SEIU/WU locals: {len(nj_locals)}")
    total_nj_members = 0
    for local in nj_locals:
        members = local['members'] or 0
        total_nj_members += members
        print(f"  {local['f_num']:>8} | {local['aff_abbr']:<5} | {local['union_name'][:40]:<40} | {members:>8,} members")

    print(f"\n  Total NJ-based members: {total_nj_members:,}")

    # NY-based unions covering NJ (32BJ, 1199)
    cur.execute("""
        SELECT f_num, union_name, local_number, members, aff_abbr, state
        FROM unions_master
        WHERE f_num IN ('11661', '31847')
    """)
    ny_coverage = cur.fetchall()

    print(f"\nNY-based unions covering NJ:")
    for u in ny_coverage:
        print(f"  {u['f_num']:>8} | {u['union_name'][:50]:<50} | {u['members']:>10,} members")

    return {
        'nj_locals': nj_locals,
        'ny_coverage': ny_coverage,
        'total_nj_members': total_nj_members
    }


def get_f7_employers_nj():
    """Get all F7 employers in NJ for SEIU/WU affiliates."""
    print("\n" + "=" * 80)
    print("STEP 2: F7 Employers in NJ (SEIU/WU Scope)")
    print("=" * 80)

    cur.execute("""
        SELECT
            e.employer_id,
            e.employer_name,
            e.city,
            e.state,
            e.latest_unit_size,
            e.latest_union_fnum,
            e.latest_union_name,
            u.aff_abbr
        FROM f7_employers_deduped e
        LEFT JOIN unions_master u ON e.latest_union_fnum::text = u.f_num::text
        WHERE e.state = 'NJ'
        AND (
            u.aff_abbr IN ('SEIU', 'WU')
            OR e.latest_union_name ILIKE '%SEIU%'
            OR e.latest_union_name ILIKE '%1199%'
            OR e.latest_union_name ILIKE '%32BJ%'
            OR e.latest_union_name ILIKE '%workers united%'
            OR e.latest_union_name ILIKE '%NUHHCE%'
            OR e.latest_union_name ILIKE '%interns%residents%'
        )
        ORDER BY e.latest_unit_size DESC NULLS LAST
    """)
    employers = cur.fetchall()

    # Categorize by union type
    by_category = defaultdict(list)
    for emp in employers:
        cat = categorize_union_name(emp['latest_union_name'])
        by_category[cat].append(emp)

    print(f"\nTotal F7 employers in NJ (SEIU scope): {len(employers)}")
    print(f"\nBy affiliate category:")

    total_workers = 0
    for cat in sorted(by_category.keys()):
        emp_list = by_category[cat]
        workers = sum(e['latest_unit_size'] or 0 for e in emp_list)
        total_workers += workers
        print(f"  {cat:<20}: {len(emp_list):>5} employers, {workers:>8,} workers")

    print(f"\n  Total workers: {total_workers:,}")

    # Top 15 employers
    print(f"\nTop 15 employers by unit size:")
    for emp in employers[:15]:
        cat = categorize_union_name(emp['latest_union_name'])
        print(f"  {emp['employer_name'][:35]:<35} | {emp['city'] or '':^15} | {cat:<15} | {emp['latest_unit_size'] or 0:>6}")

    return employers, by_category


def get_nlrb_elections_nj():
    """Get NLRB elections in NJ with SEIU/WU petitioners."""
    print("\n" + "=" * 80)
    print("STEP 3: NLRB Elections in NJ (SEIU/WU Wins)")
    print("=" * 80)

    # Schema: nlrb_elections has case_number, eligible_voters, union_won
    # nlrb_participants has employer info (participant_type='Employer')
    # nlrb_participants has union info (participant_type='Petitioner', participant_subtype='Union')
    # nlrb_tallies has vote counts
    cur.execute("""
        SELECT DISTINCT
            e.case_number,
            emp.participant_name as employer_name,
            emp.city,
            emp.state,
            e.eligible_voters as total_eligible_voters,
            t.votes_for,
            e.election_date,
            p.participant_name as union_name,
            p.matched_olms_fnum
        FROM nlrb_elections e
        JOIN nlrb_participants p ON e.case_number = p.case_number
        JOIN nlrb_participants emp ON e.case_number = emp.case_number
        LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.is_winner = true
        WHERE emp.state = 'NJ'
        AND emp.participant_type = 'Employer'
        AND emp.participant_subtype = 'Employer'
        AND p.participant_type = 'Petitioner'
        AND p.participant_subtype = 'Union'
        AND (
            p.participant_name ILIKE '%SEIU%'
            OR p.participant_name ILIKE '%1199%'
            OR p.participant_name ILIKE '%32BJ%'
            OR p.participant_name ILIKE '%workers united%'
            OR p.participant_name ILIKE '%service employees%'
            OR p.participant_name ILIKE '%NUHHCE%'
            OR p.participant_name ILIKE '%healthcare workers%'
        )
        AND e.union_won = true
        ORDER BY e.eligible_voters DESC NULLS LAST
    """)
    elections = cur.fetchall()

    print(f"\nSEIU/WU won elections in NJ: {len(elections)}")
    total_voters = sum(e['total_eligible_voters'] or 0 for e in elections)
    print(f"Total eligible voters: {total_voters:,}")

    # Categorize
    by_category = defaultdict(list)
    for elec in elections:
        cat = categorize_union_name(elec['union_name'])
        by_category[cat].append(elec)

    print(f"\nBy affiliate category:")
    for cat in sorted(by_category.keys()):
        elec_list = by_category[cat]
        voters = sum(e['total_eligible_voters'] or 0 for e in elec_list)
        print(f"  {cat:<20}: {len(elec_list):>5} elections, {voters:>8,} voters")

    return elections


def match_nlrb_to_f7(nlrb_elections, f7_employers):
    """Match NLRB employers to F7 employers using fuzzy matching."""
    print("\n" + "=" * 80)
    print("STEP 4: NLRB to F7 Employer Matching")
    print("=" * 80)

    # Build F7 lookup by normalized name + city
    f7_lookup = {}
    for emp in f7_employers:
        key = (normalize_employer_name(emp['employer_name']),
               (emp['city'] or '').upper().strip())
        f7_lookup[key] = emp

    matched = []
    needs_review = []
    unmatched = []

    for elec in nlrb_elections:
        nlrb_name = elec['employer_name']
        nlrb_city = elec['city'] or ''
        nlrb_norm = normalize_employer_name(nlrb_name)

        best_match = None
        best_score = 0.0

        for f7_emp in f7_employers:
            score = calculate_match_score(
                nlrb_name, f7_emp['employer_name'],
                nlrb_city, f7_emp['city']
            )
            if score > best_score:
                best_score = score
                best_match = f7_emp

        result = {
            'case_number': elec['case_number'],
            'nlrb_employer': nlrb_name,
            'nlrb_city': nlrb_city,
            'voters': elec['total_eligible_voters'] or 0,
            'union_name': elec['union_name'],
            'match_score': best_score,
            'f7_employer': best_match['employer_name'] if best_match else None,
            'f7_city': best_match['city'] if best_match else None,
            'f7_employer_id': best_match['employer_id'] if best_match else None,
            'f7_unit_size': best_match['latest_unit_size'] if best_match else None,
        }

        if best_score >= 0.80:
            matched.append(result)
        elif best_score >= 0.50:
            needs_review.append(result)
        else:
            unmatched.append(result)

    print(f"\nMatching results:")
    print(f"  Auto-matched (>=80%): {len(matched):>5} elections")
    print(f"  Needs review (50-79%): {len(needs_review):>5} elections")
    print(f"  No match found (<50%): {len(unmatched):>5} elections")
    print(f"  Total NLRB elections:  {len(nlrb_elections):>5}")

    match_rate = len(matched) / len(nlrb_elections) * 100 if nlrb_elections else 0
    print(f"\n  Auto-match rate: {match_rate:.1f}%")

    return matched, needs_review, unmatched


def get_voluntary_recognition_nj():
    """Get voluntary recognition cases in NJ for SEIU/WU."""
    print("\n" + "=" * 80)
    print("STEP 5: Voluntary Recognition in NJ (SEIU/WU)")
    print("=" * 80)

    # Check if vr_cases table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'vr_cases'
        )
    """)
    has_vr = cur.fetchone()['exists']

    if not has_vr:
        print("  VR cases table not found - skipping")
        return []

    cur.execute("""
        SELECT *
        FROM vr_cases
        WHERE state = 'NJ'
        AND (
            union_name ILIKE '%SEIU%'
            OR union_name ILIKE '%1199%'
            OR union_name ILIKE '%32BJ%'
            OR union_name ILIKE '%workers united%'
            OR union_name ILIKE '%service employees%'
        )
        ORDER BY employee_count DESC NULLS LAST
    """)
    vr_cases = cur.fetchall()

    print(f"\nSEIU/WU voluntary recognition in NJ: {len(vr_cases)}")

    return vr_cases


def generate_summary_report(membership, f7_employers, f7_by_category, nlrb_elections,
                           matched, needs_review, unmatched):
    """Generate summary statistics."""
    print("\n" + "=" * 80)
    print("STEP 6: SEIU NJ Coverage Summary")
    print("=" * 80)

    summary = {
        'membership': {
            'nj_based_members': membership['total_nj_members'],
            'nj_locals_count': len(membership['nj_locals']),
        },
        'f7_employers': {
            'total_employers': len(f7_employers),
            'total_workers': sum(e['latest_unit_size'] or 0 for e in f7_employers),
        },
        'nlrb': {
            'total_elections': len(nlrb_elections),
            'matched': len(matched),
            'needs_review': len(needs_review),
            'unmatched': len(unmatched),
            'match_rate': len(matched) / len(nlrb_elections) * 100 if nlrb_elections else 0,
        },
        'by_affiliate': {},
    }

    # Aggregate by affiliate category
    for cat, emp_list in f7_by_category.items():
        summary['by_affiliate'][cat] = {
            'f7_employers': len(emp_list),
            'f7_workers': sum(e['latest_unit_size'] or 0 for e in emp_list),
        }

    # Print summary
    print(f"\n{'Metric':<40} {'Value':>15}")
    print("-" * 57)
    print(f"{'NJ-based SEIU/WU Members (LM):':<40} {summary['membership']['nj_based_members']:>15,}")
    print(f"{'NJ-based locals count:':<40} {summary['membership']['nj_locals_count']:>15}")
    print(f"{'F7 Employers in NJ:':<40} {summary['f7_employers']['total_employers']:>15}")
    print(f"{'F7 Workers in NJ:':<40} {summary['f7_employers']['total_workers']:>15,}")
    print(f"{'NLRB Elections (SEIU wins):':<40} {summary['nlrb']['total_elections']:>15}")
    print(f"{'NLRB Auto-matched to F7:':<40} {summary['nlrb']['matched']:>15}")
    print(f"{'NLRB Match Rate:':<40} {summary['nlrb']['match_rate']:>14.1f}%")

    print(f"\nBy Affiliate:")
    print(f"  {'Category':<20} {'Employers':>10} {'Workers':>12}")
    print("  " + "-" * 44)
    for cat in sorted(summary['by_affiliate'].keys()):
        data = summary['by_affiliate'][cat]
        print(f"  {cat:<20} {data['f7_employers']:>10} {data['f7_workers']:>12,}")

    return summary


def export_csv_reports(f7_employers, matched, needs_review, unmatched, summary):
    """Export CSV reports."""
    print("\n" + "=" * 80)
    print("STEP 7: Exporting CSV Reports")
    print("=" * 80)

    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. All F7 employers with normalized union names
    f7_path = os.path.join(OUTPUT_DIR, 'seiu_nj_employers_all.csv')
    with open(f7_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['employer_id', 'employer_name', 'city', 'state',
                        'unit_size', 'union_fnum', 'union_name', 'normalized_affiliate'])
        for emp in f7_employers:
            writer.writerow([
                emp['employer_id'],
                emp['employer_name'],
                emp['city'],
                emp['state'],
                emp['latest_unit_size'],
                emp['latest_union_fnum'],
                emp['latest_union_name'],
                categorize_union_name(emp['latest_union_name'])
            ])
    print(f"  Exported: {f7_path}")

    # 2. NLRB auto-matched
    matched_path = os.path.join(OUTPUT_DIR, 'seiu_nj_nlrb_matched.csv')
    with open(matched_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['case_number', 'nlrb_employer', 'nlrb_city', 'voters',
                        'union_name', 'match_score', 'f7_employer', 'f7_city',
                        'f7_employer_id', 'f7_unit_size'])
        for m in matched:
            writer.writerow([
                m['case_number'], m['nlrb_employer'], m['nlrb_city'], m['voters'],
                m['union_name'], f"{m['match_score']:.2f}", m['f7_employer'],
                m['f7_city'], m['f7_employer_id'], m['f7_unit_size']
            ])
    print(f"  Exported: {matched_path}")

    # 3. NLRB needs review
    review_path = os.path.join(OUTPUT_DIR, 'seiu_nj_nlrb_review.csv')
    with open(review_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['case_number', 'nlrb_employer', 'nlrb_city', 'voters',
                        'union_name', 'match_score', 'f7_employer', 'f7_city',
                        'f7_employer_id', 'f7_unit_size', 'review_notes'])
        for m in needs_review:
            writer.writerow([
                m['case_number'], m['nlrb_employer'], m['nlrb_city'], m['voters'],
                m['union_name'], f"{m['match_score']:.2f}", m['f7_employer'],
                m['f7_city'], m['f7_employer_id'], m['f7_unit_size'], ''
            ])
    print(f"  Exported: {review_path}")

    # 4. NLRB unmatched
    unmatched_path = os.path.join(OUTPUT_DIR, 'seiu_nj_nlrb_unmatched.csv')
    with open(unmatched_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['case_number', 'nlrb_employer', 'nlrb_city', 'voters',
                        'union_name', 'best_match_score', 'closest_f7_employer'])
        for m in unmatched:
            writer.writerow([
                m['case_number'], m['nlrb_employer'], m['nlrb_city'], m['voters'],
                m['union_name'], f"{m['match_score']:.2f}", m['f7_employer']
            ])
    print(f"  Exported: {unmatched_path}")

    # 5. Summary report
    summary_path = os.path.join(OUTPUT_DIR, 'seiu_nj_summary.csv')
    with open(summary_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['category', 'metric', 'value'])
        writer.writerow(['Membership', 'NJ-based SEIU/WU Members', summary['membership']['nj_based_members']])
        writer.writerow(['Membership', 'NJ-based Locals Count', summary['membership']['nj_locals_count']])
        writer.writerow(['F7', 'Total Employers', summary['f7_employers']['total_employers']])
        writer.writerow(['F7', 'Total Workers', summary['f7_employers']['total_workers']])
        writer.writerow(['NLRB', 'Elections Won', summary['nlrb']['total_elections']])
        writer.writerow(['NLRB', 'Auto-matched to F7', summary['nlrb']['matched']])
        writer.writerow(['NLRB', 'Needs Review', summary['nlrb']['needs_review']])
        writer.writerow(['NLRB', 'Unmatched', summary['nlrb']['unmatched']])
        writer.writerow(['NLRB', 'Match Rate (%)', f"{summary['nlrb']['match_rate']:.1f}"])
        for cat, data in summary['by_affiliate'].items():
            writer.writerow(['Affiliate', f'{cat} Employers', data['f7_employers']])
            writer.writerow(['Affiliate', f'{cat} Workers', data['f7_workers']])
    print(f"  Exported: {summary_path}")


def create_database_view():
    """Create a database view for ongoing SEIU NJ queries."""
    print("\n" + "=" * 80)
    print("STEP 8: Creating Database View")
    print("=" * 80)

    view_sql = """
    CREATE OR REPLACE VIEW v_seiu_nj_employers AS
    SELECT
        e.employer_id,
        e.employer_name,
        e.city,
        e.state,
        e.latest_unit_size,
        e.latest_union_fnum,
        e.latest_union_name,
        u.aff_abbr,
        CASE
            WHEN e.latest_union_name ~* '32\\s*BJ' THEN '32BJ'
            WHEN e.latest_union_name ~* '1199|NUHHCE' THEN '1199'
            WHEN e.latest_union_name ~* 'workers\\s*united|LDFS' THEN 'WORKERS_UNITED'
            WHEN e.latest_union_name ~* 'interns.*residents|\\bCIR\\b' THEN 'CIR'
            ELSE 'OTHER_SEIU'
        END as normalized_affiliate,
        'F7' as source
    FROM f7_employers_deduped e
    LEFT JOIN unions_master u ON e.latest_union_fnum::text = u.f_num::text
    WHERE e.state = 'NJ'
    AND (
        u.aff_abbr IN ('SEIU', 'WU')
        OR e.latest_union_name ILIKE '%SEIU%'
        OR e.latest_union_name ILIKE '%1199%'
        OR e.latest_union_name ILIKE '%32BJ%'
        OR e.latest_union_name ILIKE '%workers united%'
        OR e.latest_union_name ILIKE '%NUHHCE%'
        OR e.latest_union_name ILIKE '%interns%residents%'
    );
    """

    try:
        cur.execute(view_sql)
        conn.commit()
        print("  Created view: v_seiu_nj_employers")

        # Verify
        cur.execute("SELECT COUNT(*), COALESCE(SUM(latest_unit_size), 0) FROM v_seiu_nj_employers")
        result = cur.fetchone()
        print(f"  View contains: {result['count']} employers, {int(result['coalesce']):,} workers")
    except Exception as e:
        print(f"  Warning: Could not create view: {e}")
        conn.rollback()


def main():
    print("=" * 80)
    print("SEIU NJ MEMBER-TO-EMPLOYER MATCHING RECONCILIATION")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Step 1: Analyze membership
    membership = get_seiu_nj_membership()

    # Step 2: Get F7 employers
    f7_employers, f7_by_category = get_f7_employers_nj()

    # Step 3: Get NLRB elections
    nlrb_elections = get_nlrb_elections_nj()

    # Step 4: Match NLRB to F7
    matched, needs_review, unmatched = match_nlrb_to_f7(nlrb_elections, f7_employers)

    # Step 5: Get VR cases (if available)
    vr_cases = get_voluntary_recognition_nj()

    # Step 6: Generate summary
    summary = generate_summary_report(
        membership, f7_employers, f7_by_category, nlrb_elections,
        matched, needs_review, unmatched
    )

    # Step 7: Export CSVs
    export_csv_reports(f7_employers, matched, needs_review, unmatched, summary)

    # Step 8: Create database view
    create_database_view()

    # Final summary
    print("\n" + "=" * 80)
    print("RECONCILIATION COMPLETE")
    print("=" * 80)

    print(f"""
Key Findings:
- NJ-based SEIU/WU members:  {membership['total_nj_members']:,}
- F7 employers covered:      {len(f7_employers)}
- F7 workers covered:        {sum(e['latest_unit_size'] or 0 for e in f7_employers):,}
- NLRB elections matched:    {len(matched)}/{len(nlrb_elections)} ({summary['nlrb']['match_rate']:.1f}%)
- Needs manual review:       {len(needs_review)}

Output files in: {OUTPUT_DIR}
Database view:   v_seiu_nj_employers
""")

    conn.close()


if __name__ == '__main__':
    main()
