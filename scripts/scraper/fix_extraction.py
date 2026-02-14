"""
Fix extraction quality issues:
1. Delete false 'Howard County Schools' employer entries (shared AFSCME sidebar content)
2. Delete membership counts that match local numbers (false positives)
3. Delete year-like membership counts (2020, 2022, 2023 etc)
4. Re-run improved extraction for employers
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


def fix_employers(conn):
    """Delete false positive employers and re-extract with better heuristics."""
    cur = conn.cursor()

    # 1. Delete ALL auto-extracted employers (they're mostly bad)
    cur.execute("DELETE FROM web_union_employers WHERE extraction_method = 'auto_extract'")
    deleted = cur.rowcount
    print(f"Deleted {deleted} auto-extracted employer rows")

    # 2. Re-extract with improved heuristics
    cur.execute("""
        SELECT id, union_name, local_number, state, raw_text, raw_text_about
        FROM web_union_profiles
        WHERE scrape_status = 'EXTRACTED'
    """)
    profiles = cur.fetchall()

    # Build set of boilerplate phrases (appear in 5+ profiles)
    # Count phrase frequency across profiles
    phrase_counts = {}
    for pid, name, local, state, homepage, about in profiles:
        text = (about or '') + (homepage or '')
        # Find all potential employer mentions
        for pattern in [
            r'employees?\s+of\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,|\band\b|\bin\b)',
            r'represent(?:s|ing)?\s+(?:workers?|employees?|members?)\s+(?:at|of|in)\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,|\band\b)',
            r'contract\s+with\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,|\bfor\b)',
        ]:
            for m in re.finditer(pattern, text):
                phrase = m.group(1).strip().rstrip(',. ')
                if 4 <= len(phrase) <= 100:
                    phrase_counts[phrase.lower()] = phrase_counts.get(phrase.lower(), 0) + 1

    # Anything appearing in 5+ profiles is boilerplate
    boilerplate = {p for p, c in phrase_counts.items() if c >= 5}
    print(f"Identified {len(boilerplate)} boilerplate phrases (appear in 5+ profiles)")
    for bp in sorted(boilerplate):
        print(f"  - {bp} ({phrase_counts[bp]}x)")

    # 3. Re-extract with filters
    inserted = 0
    for pid, name, local, state, homepage, about in profiles:
        # Use about page preferentially, fall back to homepage
        text = about or homepage or ''
        if not text:
            continue

        employers = extract_employers_v2(text, state, local, boilerplate)
        for emp in employers:
            cur.execute("""
                INSERT INTO web_union_employers
                    (web_profile_id, employer_name, employer_name_clean, state, sector,
                     source_url, extraction_method, confidence_score)
                VALUES (%s, %s, %s, %s, %s,
                    (SELECT website_url FROM web_union_profiles WHERE id = %s),
                    'auto_extract_v2', %s)
            """, (pid, emp['employer_name'], emp['employer_name_clean'],
                  emp.get('state', state), emp.get('sector'),
                  pid, emp.get('confidence', 0.7)))
            inserted += 1

    conn.commit()
    print(f"\nInserted {inserted} employers (v2)")


def extract_employers_v2(text, state, local_number, boilerplate):
    """Improved employer extraction with boilerplate filtering."""
    results = []
    seen = set()

    patterns = [
        # "employees of the City of X"
        (r'employees?\s+of\s+(?:the\s+)?([A-Z][A-Za-z\s&,\'-]+?)(?:\.|,|\band\b|\bin\b|\bwho\b)', 0.7),
        # "represent workers at X"
        (r'represent(?:s|ing)?\s+(?:workers?|employees?|members?)\s+(?:at|of|in)\s+(?:the\s+)?([A-Z][A-Za-z\s&,\'-]+?)(?:\.|,|\band\b|\bwho\b)', 0.8),
        # "bargaining unit at X"
        (r'bargaining\s+(?:unit|agreement)\s+(?:at|with)\s+(?:the\s+)?([A-Z][A-Za-z\s&,\'-]+?)(?:\.|,)', 0.8),
        # "contract with X"
        (r'contract\s+with\s+(?:the\s+)?([A-Z][A-Za-z\s&,\'-]+?)(?:\.|,|\bfor\b|\bthat\b)', 0.7),
        # "work for X" / "works for X"
        (r'work(?:s|ing)?\s+for\s+(?:the\s+)?([A-Z][A-Za-z\s&,\'-]+?)(?:\.|,|\band\b|\bwho\b)', 0.7),
        # "employed by X"
        (r'employed\s+by\s+(?:the\s+)?([A-Z][A-Za-z\s&,\'-]+?)(?:\.|,|\band\b)', 0.7),
    ]

    skip_words = {'the', 'our', 'their', 'these', 'those', 'all', 'union',
                  'afscme', 'local', 'council', 'chapter', 'district',
                  'state', 'national', 'international', 'american',
                  'we', 'you', 'they', 'who', 'which', 'that',
                  'members', 'workers', 'employees', 'people'}

    for pattern, base_confidence in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            name = m.group(1).strip().rstrip(',. \'"')

            # Basic length filter
            if len(name) < 5 or len(name) > 80:
                continue

            # Skip common false positives
            if name.lower() in skip_words:
                continue
            if name.lower().startswith(('the ', 'a ', 'an ')):
                name = name[name.index(' ')+1:].strip()
                if len(name) < 5:
                    continue

            # Skip boilerplate
            if name.lower() in boilerplate:
                continue

            # Skip if it contains the union's own local number
            if local_number and f'local {local_number}' in name.lower():
                continue

            name_key = name.lower().strip()
            if name_key in seen:
                continue
            seen.add(name_key)

            sector = guess_sector(name)
            results.append({
                'employer_name': name,
                'employer_name_clean': name,
                'state': state,
                'sector': sector,
                'confidence': base_confidence,
            })

    return results


def guess_sector(name):
    """Guess employer sector from name keywords."""
    nl = name.lower()
    if any(w in nl for w in ['city of', 'county of', 'town of', 'village of',
                              'borough of', 'municipal', 'city council']):
        return 'PUBLIC_LOCAL'
    if any(w in nl for w in ['state of', 'commonwealth', 'department of']):
        return 'PUBLIC_STATE'
    if any(w in nl for w in ['university', 'college', 'school district',
                              'board of education', 'public school']):
        return 'PUBLIC_EDUCATION'
    if any(w in nl for w in ['hospital', 'health', 'medical center',
                              'nursing', 'healthcare']):
        return 'HEALTHCARE'
    if any(w in nl for w in ['federal', 'u.s.', 'united states']):
        return 'PUBLIC_FEDERAL'
    return None


def fix_membership(conn):
    """Remove false positive membership counts."""
    cur = conn.cursor()

    # Get all profiles with their local numbers
    cur.execute("""
        SELECT wp.id, wp.local_number, wm.id as mem_id, wm.member_count
        FROM web_union_profiles wp
        JOIN web_union_membership wm ON wm.web_profile_id = wp.id
    """)
    rows = cur.fetchall()

    deleted = 0
    for pid, local_num, mem_id, count in rows:
        should_delete = False

        # Delete if count matches local number
        if local_num and str(count) == str(local_num):
            should_delete = True
            reason = f"matches local number {local_num}"

        # Delete year-like values (2018-2030)
        elif 2018 <= count <= 2030:
            should_delete = True
            reason = f"looks like a year ({count})"

        # Delete suspiciously small counts that look like page numbers
        elif count < 50:
            should_delete = True
            reason = f"too small ({count}), likely page artifact"

        if should_delete:
            cur.execute("DELETE FROM web_union_membership WHERE id = %s", (mem_id,))
            deleted += 1
            cur.execute("SELECT union_name FROM web_union_profiles WHERE id = %s", (pid,))
            name = cur.fetchone()[0]
            print(f"  Deleted [{pid}] {name[:40]}: {count:,} - {reason}")

    conn.commit()
    print(f"\nDeleted {deleted} false positive membership counts")

    # Show remaining
    cur.execute("""
        SELECT wp.id, wp.union_name, wm.member_count, wm.count_type
        FROM web_union_membership wm
        JOIN web_union_profiles wp ON wm.web_profile_id = wp.id
        ORDER BY wm.member_count DESC
    """)
    rows = cur.fetchall()
    print(f"\nRemaining {len(rows)} membership counts:")
    for pid, name, count, ctype in rows:
        print(f"  [{pid}] {name[:50]:<50} {count:>10,} ({ctype})")


if __name__ == '__main__':
    conn = get_connection()
    try:
        print("=== FIXING EMPLOYERS ===")
        fix_employers(conn)
        print("\n=== FIXING MEMBERSHIP ===")
        fix_membership(conn)
    finally:
        conn.close()
