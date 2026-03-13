"""
Clean up noise from wp_api extracted employers.

Adds `validated` boolean column to web_union_employers and marks entries
as valid or invalid based on pattern matching. Does NOT delete -- just flags.

Usage:
    py scripts/scraper/clean_wp_employers.py              # dry-run (report only)
    py scripts/scraper/clean_wp_employers.py --apply       # apply flags to DB
    py scripts/scraper/clean_wp_employers.py --delete      # delete invalid rows
"""
import sys
import os
import re
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ── Rejection patterns ───────────────────────────────────────────────────

# Person name: 2-4 words, each capitalized or ALL CAPS, no org keywords, no digits
_PERSON_RE = re.compile(
    r'^[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\s+(?:Jr|Sr|II|III|IV)\.?)?$'  # "John A Smith Jr"
    r'|^[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+(?:Jr|Sr|II|III|IV)\.?)?$'                  # "John Smith"
    r'|^[A-Z][a-z]+\s+[A-Z]\s+[A-Z][a-z]+(?:\s+(?:Jr|Sr|II|III|IV)\.?)?$'          # "John A Smith"
    r'|^[A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+$'                                  # "Maria Del Carmen"
    r'|^[A-Z]{2,}\s+[A-Z]\.?\s+[A-Z]{2,}$'                                         # "JOHN A SMITH"
    r'|^[A-Z]{2,}\s+[A-Z]{2,}$'                                                     # "JOHN SMITH"
    r'|^[A-Z]{2,}\s+[A-Z]\.?\s+[A-Z]{2,}\s+[A-Z]{2,}$'                             # "MARIA DEL CARMEN"
)

# Words that confirm NOT a person name (even if pattern matches)
_ORG_KEYWORDS = [
    'city', 'county', 'town', 'village', 'borough', 'university', 'college',
    'school', 'hospital', 'medical', 'district', 'authority', 'department',
    'dept', 'corp', 'inc', 'llc', 'ltd', 'company', 'municipal', 'township',
    'board', 'commission', 'agency', 'center', 'centre', 'library', 'museum',
    'institute', 'state of', 'federal', 'u.s.', 'local', 'head start',
    'transit', 'housing', 'water', 'fire', 'police', 'sheriff', 'union',
    'workers', 'employees', 'association', 'council', 'services', 'group',
    'systems', 'industries', 'enterprises', 'partners', 'health',
    'electric', 'gas', 'utility', 'airlines', 'airways', 'railroad',
    'nursing', 'rehab', 'clinic', 'labs', 'foods', 'mills', 'plant',
    'factory', 'warehouse', 'terminal', 'port', 'airport',
    'care', 'urgent', 'pediatric', 'pharmacy', 'dental',
    'senior', 'retirement', 'assisted living',
]

# Sentence/description indicators
_VERB_PHRASES = [
    'perform ', 'assist ', 'respond ', 'maintain ', 'ensure ', 'provide ',
    'worked for', 'attended ', 'expanding ', 'advocate ', 'avoid ',
    'decreases', 'successfully', 'proficiency', 'required', 'preferred',
    'we asked', 'we were', 'shall be', 'clarifies', 'new language',
    'includes ', 'submitte', 'support our', 'increase ', 'continue to',
    'expand the', 'promotes ', 'improve ', 'strengthen ', 'protect ',
    'responsible for', 'duties as assigned', 'experience in ',
    'led by ', 'swearing-in', 'one-on-one meeting',
    'exhibits polite', 'professional communication', 'via phone',
    'coordinate with', 'prepare and', 'compile ',
    'answer telephone', 'transfer to', 'filing and',
    'schedule and', 'process and', 'review and',
]

# News/date snippet pattern
_NEWS_DATE_RE = re.compile(
    r'(?:January|February|March|April|May|June|July|August|September|'
    r'October|November|December)\s+\d{1,2},?\s+\d{4}'
)

# Tax/form references
_FORM_PATTERNS = [
    'form 1099', 'form w-2', 'form w2', 'earned income credit',
    'tax refund', 'cancellation of debt', 'gambling winnings',
    'dividends received', 'self-employed income', 'tax credit',
    'reimbursement form',
]

# Education/degree references
_EDUCATION_PATTERNS = [
    "bachelor's", "master's", "bachelor", "master",
    'degree from', 'majoring in', 'accredited college',
    'post-high school', 'high school diploma',
]

# Bio/candidate fragments
_BIO_PATTERNS = [
    'board member since', 'board member,', 'unit \\d+ board',
    'chair since', 'representative on', 'member since',
    'years of experience', 'term unit',
]

# Meeting/event descriptions
_EVENT_PATTERNS = [
    'meeting with', 'meeting,', 'orientation,', 'training led by',
    'bargaining training', 'local board meeting',
]

# Policy language
_POLICY_PATTERNS = [
    'bereavement leave', 'overtime hours', 'hazard pay',
    'calculation of eligible', 'budget deficit', 'budget cuts',
    'treats represented', 'treating represented',
]

# Generic single words that aren't employers
_GENERIC_SINGLES = {
    'eastern', 'western', 'northern', 'southern', 'northeast', 'northwest',
    'southeast', 'southwest', 'central', 'locals', 'members-at-large',
    'chemistry', 'other', 'none', 'various', 'general', 'retired',
    'retirees', 'unknown', 'retiree membership', 'local',
}

# Politician pattern: "Name, Title/Office" or "District N, Title, Name"
_POLITICIAN_RE = re.compile(
    r'^[A-Z][a-z]+\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+,\s+'       # "Nathan Fletcher, "
    r'(?:Board of Supervisors|City Council|Mayor|Assembly|Senate|Director|'
    r'State Assembly|State Senate|Congress|House of Representatives|'
    r'Trustee|Commissioner|Supervisor|Council\s*(?:member|woman|man))',
    re.IGNORECASE
)
_POLITICIAN_RE2 = re.compile(
    r'^District\s+\d+,?\s+(?:House of Representatives|Senate|Assembly|State)',
    re.IGNORECASE
)


def is_valid_employer(name):
    """Return (valid: bool, reason: str) for an employer name."""
    if not name:
        return False, 'empty'

    nl = name.lower().strip()

    # Too long = sentence fragment
    if len(name) > 80:
        return False, 'too_long'

    # Politician references
    if _POLITICIAN_RE.match(name) or _POLITICIAN_RE2.match(name):
        return False, 'politician'

    # Form/tax references
    for pat in _FORM_PATTERNS:
        if pat in nl:
            return False, 'form_reference'

    # Verb phrases / job descriptions
    for pat in _VERB_PHRASES:
        if pat in nl:
            return False, 'verb_phrase'

    # Education/degree
    for pat in _EDUCATION_PATTERNS:
        if pat in nl:
            return False, 'education'

    # Bio fragments
    for pat in _BIO_PATTERNS:
        if re.search(pat, nl):
            return False, 'bio_fragment'

    # Event descriptions
    for pat in _EVENT_PATTERNS:
        if pat in nl:
            return False, 'event'

    # Policy language
    for pat in _POLICY_PATTERNS:
        if pat in nl:
            return False, 'policy'

    # Contract clause pattern: "LABEL:..." (ALL CAPS before colon)
    if re.match(r'^[A-Z ]{4,}:', name):
        return False, 'contract_clause'

    # Contains dollar amounts
    if '$' in name or re.search(r'\$[\d,]+', name):
        return False, 'dollar_amount'

    # News/date snippets ("WROC, December 13, 2017: ...")
    if _NEWS_DATE_RE.search(name):
        return False, 'news_snippet'

    # Generic single words
    if nl in _GENERIC_SINGLES:
        return False, 'generic'

    # Has org keyword = likely valid
    has_org_kw = any(kw in nl for kw in _ORG_KEYWORDS)

    # Person name check (only if no org keyword)
    if not has_org_kw and _PERSON_RE.match(name):
        return False, 'person_name'

    # ALL CAPS person name: "FIRSTNAME LASTNAME" with no org keyword
    if not has_org_kw:
        words = name.split()
        if 2 <= len(words) <= 4:
            all_upper = all(w.isupper() for w in words)
            all_short = all(len(w) <= 12 for w in words)
            no_digits = not re.search(r'\d', name)
            # Check if it looks like a name (short upper words, no numbers)
            # But exclude things like "BRYAN CITY" which have org keywords
            if all_upper and all_short and no_digits:
                # Could be abbreviated org like "PERKINS LOCAL" or person "JOHN SMITH"
                # If any word is a common org suffix, keep it
                org_suffixes = {'local', 'city', 'county', 'ex', 'vlg', 'dd',
                                'cbdd', 'head', 'bus', 'aides', 'sec'}
                if not any(w.lower() in org_suffixes for w in words):
                    # Check if it looks like a 2-3 word person name
                    # Middle initials: single letter or letter+period
                    mid_initials = sum(1 for w in words if len(w) <= 2)
                    if mid_initials <= 1 and len(words) <= 3:
                        return False, 'person_name_caps'

    # Single word, no org keyword, short
    words = name.split()
    if len(words) == 1 and not has_org_kw and len(name) < 15:
        return False, 'single_word'

    # Contains "BU \d" standalone (bargaining unit reference, not employer)
    if re.search(r'\(BU \d', name):
        # These are actually useful - they describe what workers at an employer
        # but the name itself isn't an employer. Keep if it also has an employer name.
        pass

    return True, 'ok'


def main():
    parser = argparse.ArgumentParser(description='Clean wp_api employer noise')
    parser.add_argument('--apply', action='store_true',
                        help='Apply validated flags to database')
    parser.add_argument('--delete', action='store_true',
                        help='Delete invalid entries (implies --apply)')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    # Ensure validated column exists
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'web_union_employers' AND column_name = 'validated'
    """)
    if not cur.fetchone():
        if args.apply or args.delete:
            cur.execute("""
                ALTER TABLE web_union_employers
                ADD COLUMN validated BOOLEAN DEFAULT NULL
            """)
            conn.commit()
            print("Added 'validated' column to web_union_employers")
        else:
            print("(dry-run: would add 'validated' column)")

    # Fetch all wp_api employers
    cur.execute("""
        SELECT id, employer_name_clean, extraction_method
        FROM web_union_employers
        WHERE extraction_method = 'wp_api'
        ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"Checking {len(rows)} wp_api entries...\n")

    valid_ids = []
    invalid_ids = []
    reasons = {}

    for eid, name, method in rows:
        ok, reason = is_valid_employer(name)
        if ok:
            valid_ids.append(eid)
        else:
            invalid_ids.append(eid)
            reasons[reason] = reasons.get(reason, 0) + 1

    print(f"=== RESULTS ===")
    print(f"  Valid:   {len(valid_ids):>6}")
    print(f"  Invalid: {len(invalid_ids):>6}")
    print(f"  Total:   {len(rows):>6}")
    print()

    print(f"=== REJECTION REASONS ===")
    for reason, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason:<25} {cnt:>6}")

    # Show sample of what would be removed
    print(f"\n=== SAMPLE INVALID (first 30) ===")
    cur.execute("""
        SELECT id, employer_name_clean FROM web_union_employers
        WHERE extraction_method = 'wp_api' AND id = ANY(%s)
        LIMIT 30
    """, (invalid_ids[:30],))
    for eid, name in cur.fetchall():
        _, reason = is_valid_employer(name)
        print(f"  [{reason:<20}] {name[:80]}")

    # Show sample of valid
    print(f"\n=== SAMPLE VALID (random 20) ===")
    import random
    sample_valid = random.sample(valid_ids, min(20, len(valid_ids)))
    cur.execute("""
        SELECT id, employer_name_clean FROM web_union_employers
        WHERE id = ANY(%s)
    """, (sample_valid,))
    for eid, name in cur.fetchall():
        print(f"  {name[:80]}")

    if args.apply or args.delete:
        # Mark valid
        if valid_ids:
            cur.execute("""
                UPDATE web_union_employers SET validated = TRUE
                WHERE id = ANY(%s)
            """, (valid_ids,))

        # Mark invalid
        if invalid_ids:
            cur.execute("""
                UPDATE web_union_employers SET validated = FALSE
                WHERE id = ANY(%s)
            """, (invalid_ids,))

        # Also mark non-wp_api as validated (they went through better extraction)
        cur.execute("""
            UPDATE web_union_employers SET validated = TRUE
            WHERE extraction_method != 'wp_api' AND validated IS NULL
        """)

        conn.commit()
        print(f"\nApplied: {len(valid_ids)} valid, {len(invalid_ids)} invalid")

        if args.delete:
            cur.execute("""
                DELETE FROM web_union_employers WHERE validated = FALSE
            """)
            deleted = cur.rowcount
            conn.commit()
            print(f"Deleted {deleted} invalid entries")

    else:
        print(f"\nDry run. Use --apply to flag, --delete to remove.")

    # Final stats
    cur.execute("""
        SELECT extraction_method, COUNT(*) FROM web_union_employers
        GROUP BY extraction_method ORDER BY COUNT(*) DESC
    """)
    print(f"\n=== CURRENT EMPLOYER COUNTS ===")
    total = 0
    for method, cnt in cur.fetchall():
        print(f"  {method:<25} {cnt:>6}")
        total += cnt
    print(f"  {'TOTAL':<25} {total:>6}")

    conn.close()


if __name__ == '__main__':
    main()
