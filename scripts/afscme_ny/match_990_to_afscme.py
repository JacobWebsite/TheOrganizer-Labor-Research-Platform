"""
Match 990 Employers to Existing AFSCME Unions in NY
Uses EIN matching and fuzzy name matching to identify organized vs unorganized employers.
"""

import sys
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'scripts' / 'import'))

import psycopg2
from name_normalizer import normalize_employer

# Try importing RapidFuzz for fuzzy matching
try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    print("Warning: rapidfuzz not installed. Install with: pip install rapidfuzz")


def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def get_afscme_employers_ny():
    """
    Get all AFSCME-represented employers in NY from the database.
    Combines F7 (private sector) and public sector employers.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    employers = []

    # Get AFSCME unions in NY first
    cur.execute("""
        SELECT DISTINCT f_num, union_name, aff_abbr
        FROM unions_master
        WHERE state = 'NY'
        AND aff_abbr = 'AFSCME'
    """)
    afscme_unions = cur.fetchall()
    print(f"Found {len(afscme_unions)} AFSCME unions in NY")

    # Get F7 employers linked to AFSCME unions
    cur.execute("""
        SELECT DISTINCT
            e.employer_id,
            e.employer_name,
            e.city,
            e.state,
            NULL as ein,
            'f7' as source_table,
            u.f_num as union_fnum
        FROM f7_employers_deduped e
        JOIN unions_master u ON e.latest_union_fnum::text = u.f_num
        WHERE u.aff_abbr = 'AFSCME'
        AND u.state = 'NY'
    """)
    f7_employers = cur.fetchall()
    print(f"Found {len(f7_employers)} F7 employers under AFSCME in NY")

    for row in f7_employers:
        emp_id, emp_name, city, state, ein, source, union_fnum = row
        employers.append({
            'id': emp_id,
            'name': emp_name,
            'name_normalized': normalize_employer(emp_name) if emp_name else '',
            'city': city,
            'state': state,
            'ein': ein,
            'source': 'f7',
            'union_fnum': union_fnum
        })

    # Get public sector employers from ps_employers linked to AFSCME
    cur.execute("""
        SELECT DISTINCT
            e.id,
            e.employer_name,
            e.city,
            e.state,
            NULL as ein,
            'ps' as source_table,
            bu.local_id
        FROM ps_employers e
        JOIN ps_bargaining_units bu ON e.id = bu.employer_id
        JOIN ps_union_locals l ON bu.local_id = l.id
        JOIN ps_parent_unions p ON l.parent_union_id = p.id
        WHERE p.abbrev = 'AFSCME'
        AND e.state = 'NY'
    """)
    ps_employers = cur.fetchall()
    print(f"Found {len(ps_employers)} public sector employers under AFSCME in NY")

    for row in ps_employers:
        emp_id, emp_name, city, state, ein, source, local_id = row
        employers.append({
            'id': emp_id,
            'name': emp_name,
            'name_normalized': normalize_employer(emp_name) if emp_name else '',
            'city': city,
            'state': state,
            'ein': ein,
            'source': 'ps',
            'local_id': local_id
        })

    cur.close()
    conn.close()

    return employers


def get_990_employers_ny():
    """Get all NY employers from the 990 data."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, ein, name, name_normalized, city, state,
               employee_count, total_revenue, industry_category,
               afscme_relevance_score, afscme_sector_match, source_type
        FROM employers_990
        WHERE state = 'NY'
    """)

    employers = []
    for row in cur.fetchall():
        employers.append({
            'id': row[0],
            'ein': row[1],
            'name': row[2],
            'name_normalized': row[3],
            'city': row[4],
            'state': row[5],
            'employee_count': row[6],
            'total_revenue': row[7],
            'industry_category': row[8],
            'afscme_relevance_score': float(row[9]) if row[9] else 0,
            'afscme_sector_match': row[10],
            'source_type': row[11]
        })

    cur.close()
    conn.close()

    return employers


def match_by_ein(emp_990_list, afscme_employers):
    """Match employers by exact EIN."""
    matches = []

    # Build EIN index from AFSCME employers
    ein_index = {}
    for emp in afscme_employers:
        if emp.get('ein'):
            ein_index[emp['ein']] = emp

    for emp_990 in emp_990_list:
        if emp_990.get('ein') and emp_990['ein'] in ein_index:
            afscme_emp = ein_index[emp_990['ein']]
            matches.append({
                'employer_990_id': emp_990['id'],
                'f7_employer_id': afscme_emp['id'] if afscme_emp['source'] == 'f7' else None,
                'ps_employer_id': afscme_emp['id'] if afscme_emp['source'] == 'ps' else None,
                'match_method': 'ein_exact',
                'match_score': 100.0,
                'match_confidence': 'HIGH'
            })

    return matches


def fuzzy_match_name_location(emp_990_list, afscme_employers, threshold=75):
    """
    Fuzzy match employers by name and location.
    Uses weighted combination of fuzzy match algorithms.
    """
    if not HAS_RAPIDFUZZ:
        print("Skipping fuzzy matching - rapidfuzz not installed")
        return []

    matches = []

    # Build index by city for faster matching
    city_index = defaultdict(list)
    for emp in afscme_employers:
        city = (emp.get('city') or '').upper()
        city_index[city].append(emp)
        # Also add to statewide pool
        city_index['_STATE_NY'].append(emp)

    matched_990_ids = set()

    for emp_990 in emp_990_list:
        if emp_990['id'] in matched_990_ids:
            continue

        name_norm = emp_990.get('name_normalized', '')
        if not name_norm or len(name_norm) < 3:
            continue

        city = (emp_990.get('city') or '').upper()

        # Get candidates from same city first, then state
        candidates = city_index.get(city, []) + city_index.get('_STATE_NY', [])

        best_match = None
        best_score = 0

        for afscme_emp in candidates:
            afscme_name = afscme_emp.get('name_normalized', '')
            if not afscme_name:
                continue

            # Weighted scoring
            jaro = fuzz.WRatio(name_norm, afscme_name)
            token_sort = fuzz.token_sort_ratio(name_norm, afscme_name)
            token_set = fuzz.token_set_ratio(name_norm, afscme_name)

            score = (jaro * 0.4 + token_sort * 0.3 + token_set * 0.3)

            # Boost for same city
            if city and city == (afscme_emp.get('city') or '').upper():
                score = min(100, score + 10)

            if score > best_score and score >= threshold:
                best_score = score
                best_match = afscme_emp

        if best_match:
            confidence = 'HIGH' if best_score >= 90 else 'MEDIUM' if best_score >= 80 else 'LOW'
            matches.append({
                'employer_990_id': emp_990['id'],
                'f7_employer_id': best_match['id'] if best_match['source'] == 'f7' else None,
                'ps_employer_id': best_match['id'] if best_match['source'] == 'ps' else None,
                'match_method': 'fuzzy_name_location',
                'match_score': round(best_score, 2),
                'match_confidence': confidence
            })
            matched_990_ids.add(emp_990['id'])

    return matches


def save_matches_to_db(matches):
    """Save match results to database."""
    if not matches:
        return 0

    conn = get_db_connection()
    cur = conn.cursor()

    # Clear existing matches
    cur.execute("DELETE FROM employer_990_matches")

    for match in matches:
        cur.execute("""
            INSERT INTO employer_990_matches (
                employer_990_id, f7_employer_id, ps_employer_id,
                match_method, match_score, match_confidence
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            match['employer_990_id'],
            match['f7_employer_id'],
            match['ps_employer_id'],
            match['match_method'],
            match['match_score'],
            match['match_confidence']
        ))

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM employer_990_matches")
    count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return count


def run_matching():
    """Main matching pipeline."""
    print("=" * 60)
    print("AFSCME NY Employer Matching Pipeline")
    print("=" * 60)

    # Step 1: Get employers
    print("\n[Step 1] Loading employers...")
    afscme_employers = get_afscme_employers_ny()
    emp_990_list = get_990_employers_ny()

    print(f"  - AFSCME employers in NY: {len(afscme_employers)}")
    print(f"  - 990 employers in NY: {len(emp_990_list)}")

    # Count 990 employers with EIN
    with_ein = sum(1 for e in emp_990_list if e.get('ein'))
    print(f"  - 990 employers with EIN: {with_ein} ({100*with_ein/len(emp_990_list):.1f}%)")

    # Step 2: Match by EIN
    print("\n[Step 2] Matching by EIN...")
    ein_matches = match_by_ein(emp_990_list, afscme_employers)
    print(f"  - EIN matches: {len(ein_matches)}")

    # Step 3: Fuzzy match remaining
    print("\n[Step 3] Fuzzy matching by name/location...")
    matched_990_ids = {m['employer_990_id'] for m in ein_matches}
    unmatched_990 = [e for e in emp_990_list if e['id'] not in matched_990_ids]
    fuzzy_matches = fuzzy_match_name_location(unmatched_990, afscme_employers)
    print(f"  - Fuzzy matches: {len(fuzzy_matches)}")

    # Step 4: Save to database
    print("\n[Step 4] Saving matches to database...")
    all_matches = ein_matches + fuzzy_matches
    saved_count = save_matches_to_db(all_matches)
    print(f"  - Saved: {saved_count} matches")

    # Step 5: Summary
    print("\n" + "=" * 60)
    print("MATCHING SUMMARY")
    print("=" * 60)

    total_990 = len(emp_990_list)
    total_matched = len(all_matches)
    total_unmatched = total_990 - total_matched

    print(f"Total 990 employers:     {total_990}")
    print(f"Matched to AFSCME:       {total_matched} ({100*total_matched/total_990:.1f}%)")
    print(f"  - By EIN:              {len(ein_matches)}")
    print(f"  - By fuzzy name:       {len(fuzzy_matches)}")
    print(f"Unmatched (potential):   {total_unmatched} ({100*total_unmatched/total_990:.1f}%)")

    # Unmatched by sector
    matched_ids = {m['employer_990_id'] for m in all_matches}
    unmatched = [e for e in emp_990_list if e['id'] not in matched_ids]

    sector_unmatched = sum(1 for e in unmatched if e.get('afscme_sector_match'))
    print(f"\nUnmatched in AFSCME sectors: {sector_unmatched}")

    # By industry
    industry_counts = defaultdict(int)
    for e in unmatched:
        ind = e.get('industry_category') or 'Unknown'
        industry_counts[ind] += 1

    print("\nUnmatched by Industry:")
    for ind, cnt in sorted(industry_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ind}: {cnt}")

    return total_matched, total_unmatched


if __name__ == '__main__':
    run_matching()
