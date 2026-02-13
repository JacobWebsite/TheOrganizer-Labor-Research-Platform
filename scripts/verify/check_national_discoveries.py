import os
"""
Check discovered union organizing events (2015-2025) against the labor relations database.
Classifies each as EXACT_MATCH, PARTIAL_MATCH, or NOT_FOUND.
"""
import psycopg2
import re
from collections import defaultdict

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

# ============================================================
# Define all employers to check
# ============================================================
# Format: (name, city, state, category)
EMPLOYERS = [
    # DIGITAL MEDIA / NEWSROOMS
    ("Gawker Media", "New York", "NY", "DIGITAL_MEDIA"),
    ("Guardian US", "New York", "NY", "DIGITAL_MEDIA"),
    ("Vice Media", "New York", "NY", "DIGITAL_MEDIA"),
    ("HuffPost", "New York", "NY", "DIGITAL_MEDIA"),
    ("Los Angeles Times", "Los Angeles", "CA", "DIGITAL_MEDIA"),
    ("Vox Media", "New York", "NY", "DIGITAL_MEDIA"),
    ("The New Yorker", "New York", "NY", "DIGITAL_MEDIA"),
    ("Chicago Tribune", "Chicago", "IL", "DIGITAL_MEDIA"),
    ("BuzzFeed News", "New York", "NY", "DIGITAL_MEDIA"),
    ("Hearst Magazines", "New York", "NY", "DIGITAL_MEDIA"),
    ("Wirecutter", "New York", "NY", "DIGITAL_MEDIA"),
    ("Slate", "New York", "NY", "DIGITAL_MEDIA"),
    ("Gimlet Media", "New York", "NY", "DIGITAL_MEDIA"),
    ("Fast Company", "New York", "NY", "DIGITAL_MEDIA"),
    ("Law360", "New York", "NY", "DIGITAL_MEDIA"),
    ("Sports Illustrated", "New York", "NY", "DIGITAL_MEDIA"),
    ("Dallas Morning News", "Dallas", "TX", "DIGITAL_MEDIA"),
    ("Arizona Republic", "Phoenix", "AZ", "DIGITAL_MEDIA"),
    ("Miami Herald", "Miami", "FL", "DIGITAL_MEDIA"),
    ("NBC Digital News", "New York", "NY", "DIGITAL_MEDIA"),
    ("Refinery29", "New York", "NY", "DIGITAL_MEDIA"),
    ("The Intercept", "New York", "NY", "DIGITAL_MEDIA"),
    ("Fortune", "New York", "NY", "DIGITAL_MEDIA"),
    ("Quartz", "New York", "NY", "DIGITAL_MEDIA"),
    ("Time", "New York", "NY", "DIGITAL_MEDIA"),
    ("The Onion", "Chicago", "IL", "DIGITAL_MEDIA"),
    ("Salon", "San Francisco", "CA", "DIGITAL_MEDIA"),
    ("ThinkProgress", "Washington", "DC", "DIGITAL_MEDIA"),
    ("Thrillist", "New York", "NY", "DIGITAL_MEDIA"),
    ("The Ringer", "Los Angeles", "CA", "DIGITAL_MEDIA"),

    # MUSEUMS / CULTURAL
    ("New Museum", "New York", "NY", "MUSEUM"),
    ("Guggenheim Museum", "New York", "NY", "MUSEUM"),
    ("Philadelphia Museum of Art", "Philadelphia", "PA", "MUSEUM"),
    ("Brooklyn Academy of Music", "Brooklyn", "NY", "MUSEUM"),
    ("Whitney Museum", "New York", "NY", "MUSEUM"),
    ("Museum of Contemporary Art", "Los Angeles", "CA", "MUSEUM"),
    ("MoMA", "New York", "NY", "MUSEUM"),
    ("Art Institute of Chicago", "Chicago", "IL", "MUSEUM"),
    ("Walker Art Center", "Minneapolis", "MN", "MUSEUM"),

    # TECH
    ("Kickstarter", "New York", "NY", "TECH"),
    ("Glitch", "New York", "NY", "TECH"),
    ("Alphabet Workers Union", "Mountain View", "CA", "TECH"),
    ("Google", "Mountain View", "CA", "TECH"),
    ("NYT Tech Guild", "New York", "NY", "TECH"),
    ("New York Times", "New York", "NY", "TECH"),
    ("Mapbox", "Washington", "DC", "TECH"),
    ("Apple", "Towson", "MD", "TECH"),
    ("Apple", "Oklahoma City", "OK", "TECH"),

    # RETAIL / FOOD
    ("REI", "New York", "NY", "RETAIL"),
    ("REI", "Berkeley", "CA", "RETAIL"),
    ("REI", "Cleveland", "OH", "RETAIL"),
    ("Trader Joe's", "Hadley", "MA", "RETAIL"),
    ("Trader Joe's", "Minneapolis", "MN", "RETAIL"),
    ("Trader Joe's", "Louisville", "KY", "RETAIL"),
    ("Chipotle", "Augusta", "ME", "RETAIL"),
    ("Burgerville", "Portland", "OR", "RETAIL"),
    ("Colectivo Coffee", "Milwaukee", "WI", "RETAIL"),
    ("Tartine Bakery", "San Francisco", "CA", "RETAIL"),
    ("Blue Bottle Coffee", "New York", "NY", "RETAIL"),
    ("Peet's Coffee", "Davis", "CA", "RETAIL"),

    # AMAZON
    ("Amazon", "Staten Island", "NY", "AMAZON"),
    ("Amazon JFK8", "Staten Island", "NY", "AMAZON"),
    ("Amazon ALB1", "Schodack", "NY", "AMAZON"),
    ("Amazon LAX7", "Moreno Valley", "CA", "AMAZON"),

    # GRAD STUDENT UNIONS
    ("Columbia University", "New York", "NY", "GRAD_UNION"),
    ("Harvard University", "Cambridge", "MA", "GRAD_UNION"),
    ("Brown University", "Providence", "RI", "GRAD_UNION"),
    ("Georgetown University", "Washington", "DC", "GRAD_UNION"),
    ("MIT", "Cambridge", "MA", "GRAD_UNION"),
    ("Massachusetts Institute of Technology", "Cambridge", "MA", "GRAD_UNION"),
    ("Johns Hopkins University", "Baltimore", "MD", "GRAD_UNION"),
    ("Northwestern University", "Evanston", "IL", "GRAD_UNION"),
    ("Caltech", "Pasadena", "CA", "GRAD_UNION"),
    ("California Institute of Technology", "Pasadena", "CA", "GRAD_UNION"),
    ("Yale University", "New Haven", "CT", "GRAD_UNION"),
    ("Boston College", "Chestnut Hill", "MA", "GRAD_UNION"),
    ("University of Southern California", "Los Angeles", "CA", "GRAD_UNION"),
    ("USC", "Los Angeles", "CA", "GRAD_UNION"),
    ("University of California", "Berkeley", "CA", "GRAD_UNION"),

    # HOSPITALITY
    ("Marriott", "New York", "NY", "HOSPITALITY"),
    ("Hilton", "Stamford", "CT", "HOSPITALITY"),

    # CANNABIS
    ("Cresco Labs", "Joliet", "IL", "CANNABIS"),

    # NONPROFITS
    ("Center for American Progress", "Washington", "DC", "NONPROFIT"),
    ("EMILY's List", "Washington", "DC", "NONPROFIT"),
    ("Guttmacher Institute", "New York", "NY", "NONPROFIT"),

    # CHARTER SCHOOLS
    ("Olney Charter", "Philadelphia", "PA", "CHARTER_SCHOOL"),
]

# ============================================================
# Helper: generate search keywords from name
# ============================================================
def get_search_keywords(name):
    """Extract meaningful keywords for ILIKE search."""
    cleaned = re.sub(r'\b(Inc|LLC|Corp|Ltd|Co|of|the|and|for)\b', '', name, flags=re.IGNORECASE)
    words = [w.strip() for w in cleaned.split() if len(w.strip()) >= 3]
    if not words:
        words = [name]
    return words

def build_ilike_patterns(name):
    """Build patterns for searching. Returns list of patterns to try."""
    patterns = []
    # Full name
    patterns.append(f"%{name.lower()}%")
    # Keywords
    keywords = get_search_keywords(name)
    if keywords and keywords[0].lower() != name.lower():
        patterns.append(f"%{keywords[0].lower()}%")
    return list(dict.fromkeys(patterns))  # dedupe preserving order


# ============================================================
# Search functions
# ============================================================
def search_mv_employer(name, city, state):
    """Search mv_employer_search materialized view."""
    results = []
    patterns = build_ilike_patterns(name)

    for pattern in patterns:
        cur.execute("""
            SELECT canonical_id, employer_name, city, state, source_type, has_union
            FROM mv_employer_search
            WHERE search_name LIKE %s
              AND state = %s
            LIMIT 10
        """, (pattern, state))
        for row in cur.fetchall():
            results.append({
                'source': 'mv_employer_search',
                'canonical_id': row[0],
                'name': row[1],
                'city': row[2],
                'state': row[3],
                'source_type': row[4],
                'has_union': row[5]
            })

    seen = set()
    unique = []
    for r in results:
        if r['canonical_id'] not in seen:
            seen.add(r['canonical_id'])
            unique.append(r)
    return unique


def search_nlrb_participants(name, state):
    """Search nlrb_participants (Employer type) joined to nlrb_elections."""
    results = []
    patterns = build_ilike_patterns(name)

    for pattern in patterns:
        cur.execute("""
            SELECT p.case_number, p.participant_name, p.city, p.state,
                   e.election_date, e.union_won, e.eligible_voters
            FROM nlrb_participants p
            LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
            WHERE LOWER(p.participant_name) LIKE %s
              AND p.state = %s
              AND p.participant_type = 'Employer'
            LIMIT 15
        """, (pattern, state))
        for row in cur.fetchall():
            results.append({
                'source': 'nlrb_elections',
                'case_number': row[0],
                'name': row[1],
                'city': row[2],
                'state': row[3],
                'election_date': str(row[4]) if row[4] else None,
                'union_won': row[5],
                'eligible_voters': row[6]
            })

    seen = set()
    unique = []
    for r in results:
        if r['case_number'] not in seen:
            seen.add(r['case_number'])
            unique.append(r)
    return unique


def search_f7_employers(name, state):
    """Search f7_employers_deduped."""
    results = []
    patterns = build_ilike_patterns(name)

    for pattern in patterns:
        cur.execute("""
            SELECT employer_id, employer_name_aggressive, city, state
            FROM f7_employers_deduped
            WHERE employer_name_aggressive LIKE %s
              AND state = %s
            LIMIT 10
        """, (pattern, state))
        for row in cur.fetchall():
            results.append({
                'source': 'f7_employers_deduped',
                'employer_id': row[0],
                'name': row[1],
                'city': row[2],
                'state': row[3]
            })

    seen = set()
    unique = []
    for r in results:
        if r['employer_id'] not in seen:
            seen.add(r['employer_id'])
            unique.append(r)
    return unique


def search_manual_employers(name, state):
    """Search manual_employers."""
    results = []
    patterns = build_ilike_patterns(name)

    for pattern in patterns:
        cur.execute("""
            SELECT id, employer_name, city, state, source_type, notes
            FROM manual_employers
            WHERE LOWER(employer_name) LIKE %s
              AND state = %s
            LIMIT 10
        """, (pattern, state))
        for row in cur.fetchall():
            results.append({
                'source': 'manual_employers',
                'id': row[0],
                'name': row[1],
                'city': row[2],
                'state': row[3],
                'manual_source': row[4],
                'notes': row[5]
            })

    seen = set()
    unique = []
    for r in results:
        if r['id'] not in seen:
            seen.add(r['id'])
            unique.append(r)
    return unique


def search_vr(name, state):
    """Search nlrb_voluntary_recognition."""
    results = []
    patterns = build_ilike_patterns(name)
    for pattern in patterns:
        try:
            cur.execute("""
                SELECT vr_case_number, employer_name, unit_city, unit_state
                FROM nlrb_voluntary_recognition
                WHERE LOWER(employer_name) LIKE %s
                  AND unit_state = %s
                LIMIT 10
            """, (pattern, state))
            for row in cur.fetchall():
                results.append({
                    'source': 'nlrb_voluntary_recognition',
                    'case_number': row[0],
                    'name': row[1],
                    'city': row[2],
                    'state': row[3]
                })
        except Exception:
            conn.rollback()
    return results


def classify_match(name, city, state, all_results):
    """Classify as EXACT_MATCH, PARTIAL_MATCH, or NOT_FOUND."""
    name_lower = name.lower().strip()
    city_lower = city.lower().strip()

    for r in all_results:
        r_name = (r.get('name') or '').lower().strip()
        r_city = (r.get('city') or '').lower().strip()

        # Exact: name substring match + same city
        if (name_lower in r_name or r_name in name_lower) and city_lower in r_city:
            return 'EXACT_MATCH', r
        # Keyword match + same city
        keywords = get_search_keywords(name)
        if keywords:
            main_kw = keywords[0].lower()
            if len(main_kw) >= 4 and main_kw in r_name and city_lower in r_city:
                return 'EXACT_MATCH', r

    # Partial: same state, similar name but different city
    for r in all_results:
        r_name = (r.get('name') or '').lower().strip()
        keywords = get_search_keywords(name)
        if keywords:
            main_kw = keywords[0].lower()
            if len(main_kw) >= 4 and main_kw in r_name:
                return 'PARTIAL_MATCH', r

    if all_results:
        return 'PARTIAL_MATCH', all_results[0]

    return 'NOT_FOUND', None


# ============================================================
# Run checks
# ============================================================
print("=" * 80)
print("NATIONAL UNION ORGANIZING DISCOVERIES - DATABASE VERIFICATION")
print("=" * 80)

results_by_category = defaultdict(list)
summary = defaultdict(int)
not_found_list = []

for name, city, state, category in EMPLOYERS:
    mv_results = search_mv_employer(name, city, state)
    nlrb_results = search_nlrb_participants(name, state)
    f7_results = search_f7_employers(name, state)
    manual_results = search_manual_employers(name, state)
    vr_results = search_vr(name, state)

    all_results = mv_results + nlrb_results + f7_results + manual_results + vr_results

    classification, best_match = classify_match(name, city, state, all_results)
    summary[classification] += 1

    result_entry = {
        'name': name,
        'city': city,
        'state': state,
        'category': category,
        'classification': classification,
        'best_match': best_match,
        'total_matches': len(all_results),
        'mv_count': len(mv_results),
        'nlrb_count': len(nlrb_results),
        'f7_count': len(f7_results),
        'manual_count': len(manual_results),
        'vr_count': len(vr_results)
    }
    results_by_category[category].append(result_entry)

    if classification == 'NOT_FOUND':
        not_found_list.append((name, city, state, category))

# ============================================================
# Print detailed results by category
# ============================================================
for category in sorted(results_by_category.keys()):
    entries = results_by_category[category]
    print(f"\n{'=' * 80}")
    print(f"  CATEGORY: {category}")
    print(f"{'=' * 80}")

    for e in entries:
        tag = e['classification']
        marker = f'[{tag}]'

        print(f"\n  {marker} {e['name']} ({e['city']}, {e['state']})")
        print(f"    Sources: MV={e['mv_count']}, NLRB={e['nlrb_count']}, F7={e['f7_count']}, Manual={e['manual_count']}, VR={e['vr_count']}")

        if e['best_match']:
            bm = e['best_match']
            print(f"    Best match from: {bm['source']}")
            print(f"      Name: {bm.get('name', 'N/A')}")
            print(f"      City: {bm.get('city', 'N/A')}, State: {bm.get('state', 'N/A')}")
            if 'canonical_id' in bm:
                print(f"      Canonical ID: {bm['canonical_id']}")
                print(f"      Source type: {bm.get('source_type', 'N/A')}, Has union: {bm.get('has_union', 'N/A')}")
            if 'case_number' in bm:
                print(f"      Case: {bm['case_number']}")
                if 'election_date' in bm:
                    print(f"      Election: {bm.get('election_date')}, Won: {bm.get('union_won')}, Eligible: {bm.get('eligible_voters')}")
            if 'employer_id' in bm:
                print(f"      F7 ID: {bm['employer_id']}")
            if 'manual_source' in bm:
                print(f"      Manual source: {bm.get('manual_source')}, Notes: {bm.get('notes')}")

# ============================================================
# Starbucks special check
# ============================================================
print(f"\n{'=' * 80}")
print("  SPECIAL CHECK: STARBUCKS")
print(f"{'=' * 80}")

cur.execute("""
    SELECT source_type, COUNT(*), COUNT(*) FILTER (WHERE has_union)
    FROM mv_employer_search
    WHERE search_name LIKE '%starbucks%'
    GROUP BY source_type
    ORDER BY COUNT(*) DESC
""")
rows = cur.fetchall()
total_sb = 0
total_union = 0
for row in rows:
    print(f"  {row[0]}: {row[1]} total, {row[2]} with union flag")
    total_sb += row[1]
    total_union += row[2]
print(f"  TOTAL Starbucks in DB: {total_sb} ({total_union} with union)")

# Starbucks NLRB elections via participants
cur.execute("""
    SELECT p.case_number, p.participant_name, p.city, p.state,
           e.election_date, e.union_won
    FROM nlrb_participants p
    LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
    WHERE LOWER(p.participant_name) LIKE '%starbucks%'
      AND p.participant_type = 'Employer'
    ORDER BY e.election_date DESC NULLS LAST
    LIMIT 25
""")
nlrb_sb = cur.fetchall()
print(f"  Starbucks NLRB election cases: {len(nlrb_sb)}")
for row in nlrb_sb:
    won_str = "WON" if row[5] else ("LOST" if row[5] is not None else "N/A")
    date_str = str(row[4]) if row[4] else "no-date"
    print(f"    {row[0]} | {(row[1] or '')[:45]:45s} | {row[2] or 'N/A':15s}, {row[3] or 'N/A'} | {date_str} | {won_str}")

# Starbucks VR
cur.execute("""
    SELECT vr_case_number, employer_name, unit_city, unit_state
    FROM nlrb_voluntary_recognition
    WHERE LOWER(employer_name) LIKE '%starbucks%'
    LIMIT 10
""")
vr_sb = cur.fetchall()
print(f"  Starbucks VR cases: {len(vr_sb)}")
for row in vr_sb:
    print(f"    {row[0]} | {row[1][:45]:45s} | {row[2]}, {row[3]}")

# ============================================================
# Summary
# ============================================================
print(f"\n{'=' * 80}")
print("  SUMMARY")
print(f"{'=' * 80}")
total = sum(summary.values())
print(f"  Total employers checked: {total}")
for cls in ['EXACT_MATCH', 'PARTIAL_MATCH', 'NOT_FOUND']:
    cnt = summary[cls]
    pct = 100 * cnt / total if total else 0
    print(f"  {cls:15s}: {cnt:3d} ({pct:.1f}%)")

print(f"\n  --- By Category ---")
for category in sorted(results_by_category.keys()):
    entries = results_by_category[category]
    cat_exact = sum(1 for e in entries if e['classification'] == 'EXACT_MATCH')
    cat_partial = sum(1 for e in entries if e['classification'] == 'PARTIAL_MATCH')
    cat_nf = sum(1 for e in entries if e['classification'] == 'NOT_FOUND')
    print(f"  {category:25s} | {len(entries):3d} checked | Exact: {cat_exact}, Partial: {cat_partial}, Not Found: {cat_nf}")

# ============================================================
# Generate INSERT statements for NOT_FOUND records
# ============================================================
if not_found_list:
    print(f"\n{'=' * 80}")
    print("  INSERT STATEMENTS FOR NOT_FOUND RECORDS (manual_employers)")
    print(f"{'=' * 80}")

    cur.execute("SELECT COALESCE(MAX(id), 0) FROM manual_employers")
    max_id = cur.fetchone()[0]

    print(f"  -- Current max manual_employers ID: {max_id}")
    print(f"  -- {len(not_found_list)} new records to insert\n")

    next_id = max_id + 1
    for name, city, state, category in not_found_list:
        safe_name = name.replace("'", "''")
        safe_city = city.replace("'", "''")
        source_note = f"2015-2025 organizing wave - {category}"
        print(f"  INSERT INTO manual_employers (id, employer_name, city, state, source_type, notes)")
        print(f"    VALUES ({next_id}, '{safe_name}', '{safe_city}', '{state}', 'RESEARCH_DISCOVERY', '{source_note}');")
        next_id += 1
else:
    print("\n  All employers found in database - no inserts needed.")

print(f"\n{'=' * 80}")
print("  VERIFICATION COMPLETE")
print(f"{'=' * 80}")

cur.close()
conn.close()
