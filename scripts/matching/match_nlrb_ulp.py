"""
Match NLRB ULP (Unfair Labor Practice) charged parties to f7_employers_deduped.

The nlrb_participants table has 866K "Charged Party / Respondent" records with
0 matched. Of these, 671K are CA cases (employer charged with ULP) -- the
strongest organizing signal. This script matches them.

Data quality issues handled:
  - 44% of names have newline (attorney name + employer/firm name)
  - City/state fields are garbage (literal header text) for 99.8%
  - Many records are person names or law firms, not employers
  - NLRB region provides approximate state

Usage:
  py scripts/matching/match_nlrb_ulp.py                # dry-run
  py scripts/matching/match_nlrb_ulp.py --commit       # apply matches
  py scripts/matching/match_nlrb_ulp.py --commit --log # also write to unified_match_log
"""
import sys
import os
import re
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

# NLRB region -> primary state(s) mapping
# Regions cover multiple states, but the primary state is most common
REGION_STATES = {
    1: ['CT', 'MA', 'ME', 'NH', 'RI', 'VT'],
    2: ['NY'],  # NYC
    3: ['NY'],  # Buffalo/Albany
    4: ['PA', 'DE'],  # Philadelphia
    5: ['DC', 'MD', 'VA', 'WV'],  # Baltimore
    6: ['PA', 'WV'],  # Pittsburgh
    7: ['MI'],
    8: ['OH'],  # Cleveland
    9: ['OH', 'KY', 'IN'],  # Cincinnati
    10: ['GA', 'TN', 'AL', 'NC'],  # Atlanta
    11: ['NC'],  # Winston-Salem (subregion)
    12: ['FL'],
    13: ['IL'],  # Chicago
    14: ['MO', 'IL', 'IN'],  # St. Louis
    15: ['LA', 'MS'],  # New Orleans
    16: ['TX'],  # Fort Worth
    17: ['KS', 'MO', 'NE'],
    18: ['MN', 'WI', 'IA', 'ND', 'SD'],
    19: ['WA', 'OR', 'ID', 'MT', 'AK'],  # Seattle
    20: ['CA'],  # San Francisco
    21: ['CA'],  # Los Angeles
    22: ['NJ'],
    24: ['PR', 'VI'],
    25: ['IN'],
    26: ['TN', 'AR', 'MS'],  # Memphis
    27: ['CO', 'WY'],
    28: ['AZ', 'NM', 'TX'],  # Phoenix
    29: ['NY'],  # Brooklyn
    30: ['WI'],  # Milwaukee
    31: ['CA'],  # Los Angeles (south)
    32: ['CA'],  # Oakland
    33: ['IL'],  # Peoria (subregion)
    34: ['CT'],  # Hartford (subregion)
    36: ['OR'],  # Portland (subregion)
    37: ['HI'],
}

# Law firm indicators (these are NOT employers)
LAW_FIRM_RE = re.compile(
    r'(?i)'
    r'(?:'
    r'\bll\.?p\.?\b'
    r'|\bp\.?\s*c\.?\s*$'
    r'|\bpllc\b'
    r'|\b(?:law\s+)?(?:office|firm)s?\s+of\b'
    r'|\battorney'
    r'|\bcounsel\b'
    r'|\besq\.?\b'
    r'|\b(?:fisher\s*&\s*phillips|jackson\s+lewis|littler\s+mendelson)\b'
    r'|\b(?:barnes\s*&\s*thornburg|ogletree\s+deakins|seyfarth\s+shaw)\b'
    r'|\b(?:morgan\s+lewis|proskauer|jones\s+day|foley\s*&\s*lardner)\b'
    r'|\b(?:bryan\s+cave|greenberg\s+traurig|baker\s*&\s*hostetler)\b'
    r'|\b(?:constangy|cozen\s+o.connor|ford\s*&\s*harrison|hunton)\b'
    r'|\b(?:labor\s+relations\s+counsel|management\s+counsel)\b'
    r')'
)

# Person name pattern: "Last, First" or "LAST, FIRST" with no corp indicators
PERSON_NAME_RE = re.compile(
    r'^[A-Z][a-zA-Z]+,\s+[A-Z][a-zA-Z]+\.?$'
)


def is_person_name(name):
    """Check if name looks like a person (Last, First) not a company."""
    name = name.strip()
    if PERSON_NAME_RE.match(name):
        return True
    # Also catch "LAST, FIRST MIDDLE" pattern
    if re.match(r'^[A-Z]+,\s+[A-Z][A-Za-z]+(?:\s+[A-Z]\.?)?$', name):
        return True
    return False


def is_law_firm(name):
    """Check if name is a law firm."""
    return bool(LAW_FIRM_RE.search(name))


def extract_employer_name(participant_name):
    """Extract the actual employer name from NLRB participant_name.

    Handles:
      - Multi-line: "Attorney Name\\nEmployer Name" -> Employer Name
      - Single line employer: "ACME CORP" -> ACME CORP
      - Person names: "SMITH, JOHN" -> None
      - Law firms: "Fisher & Phillips, LLP" -> None
    """
    if not participant_name or not participant_name.strip():
        return None

    name = participant_name.strip()

    # Multi-line: check line 2 first (usually the org)
    if '\n' in name:
        lines = [l.strip() for l in name.split('\n') if l.strip()]
        if len(lines) >= 2:
            # Line 2 could be employer OR law firm
            line2 = lines[1]
            if is_law_firm(line2):
                # Line 2 is a law firm. Line 1 is the attorney. Skip.
                return None
            if not is_person_name(line2):
                return line2
            # Both lines are persons
            return None
        elif len(lines) == 1:
            name = lines[0]

    # Single-line checks
    if is_person_name(name):
        return None
    if is_law_firm(name):
        return None

    # Skip very short names (likely initials or garbage)
    if len(name) < 3:
        return None

    return name


def normalize_for_match(name):
    """Simple normalization for matching: lowercase, strip punctuation and suffixes."""
    if not name:
        return None
    n = name.lower().strip()
    # Remove common suffixes
    n = re.sub(r'\b(?:inc|llc|corp|ltd|co|company|corporation|incorporated|limited)\b\.?', '', n)
    # Remove d/b/a prefix
    n = re.sub(r'^(?:d/?b/?a|dba)\s+', '', n)
    # Remove punctuation
    n = re.sub(r'[^\w\s]', ' ', n)
    # Collapse whitespace
    n = re.sub(r'\s+', ' ', n).strip()
    return n if n else None


def load_f7_lookup(cur):
    """Build employer lookup dicts from f7_employers_deduped."""
    cur.execute("""
        SELECT employer_id, employer_name, name_standard, name_aggressive, state
        FROM f7_employers_deduped
        WHERE employer_name IS NOT NULL
    """)
    # name_standard -> [(employer_id, state), ...]
    by_standard = defaultdict(list)
    by_aggressive = defaultdict(list)
    by_simple = defaultdict(list)

    for row in cur.fetchall():
        eid, ename, nstd, nagg, state = row
        if nstd:
            by_standard[nstd].append((eid, state))
        if nagg:
            by_aggressive[nagg].append((eid, state))
        simple = normalize_for_match(ename)
        if simple:
            by_simple[simple].append((eid, state))

    return by_standard, by_aggressive, by_simple


def match_name(name, region, by_standard, by_aggressive, by_simple):
    """Try to match a name against F7 employers.

    Returns (employer_id, confidence, method) or None.
    """
    region_states = REGION_STATES.get(region, [])

    # Normalize the ULP name
    simple = normalize_for_match(name)
    if not simple:
        return None

    # Try simple normalized match first (highest volume)
    candidates = by_simple.get(simple, [])
    if candidates:
        # Prefer same-state match
        if region_states:
            state_matches = [c for c in candidates if c[1] in region_states]
            if state_matches:
                return (state_matches[0][0], 0.90, 'ulp_name_state')
        # No state filter or no state match -- take first if unique
        if len(candidates) == 1:
            return (candidates[0][0], 0.80, 'ulp_name_exact')
        elif len(candidates) <= 3:
            return (candidates[0][0], 0.70, 'ulp_name_ambiguous')
        # Too many candidates -- skip
        return None

    # Try pre-computed standard normalization
    # We need to normalize the ULP name the same way
    # Import the normalizer
    try:
        from scripts.matching.normalizer import normalize_employer_name
        nstd = normalize_employer_name(name, 'standard')
        candidates = by_standard.get(nstd, [])
        if candidates:
            if region_states:
                state_matches = [c for c in candidates if c[1] in region_states]
                if state_matches:
                    return (state_matches[0][0], 0.85, 'ulp_standard_state')
            if len(candidates) == 1:
                return (candidates[0][0], 0.75, 'ulp_standard')
            elif len(candidates) <= 3:
                return (candidates[0][0], 0.65, 'ulp_standard_ambig')
            return None

        # Try aggressive
        nagg = normalize_employer_name(name, 'aggressive')
        candidates = by_aggressive.get(nagg, [])
        if candidates:
            if region_states:
                state_matches = [c for c in candidates if c[1] in region_states]
                if state_matches:
                    return (state_matches[0][0], 0.75, 'ulp_aggressive_state')
            if len(candidates) == 1:
                return (candidates[0][0], 0.65, 'ulp_aggressive')
            return None
    except ImportError:
        pass

    return None


def main():
    parser = argparse.ArgumentParser(description='Match NLRB ULP charged parties')
    parser.add_argument('--commit', action='store_true', help='Apply matches to DB')
    parser.add_argument('--log', action='store_true', help='Write to unified_match_log')
    parser.add_argument('--limit', type=int, default=0, help='Limit records processed')
    parser.add_argument('--verbose', action='store_true', help='Print each match')
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    print('Loading F7 employer lookup...')
    by_standard, by_aggressive, by_simple = load_f7_lookup(cur)
    print(f'  {len(by_simple)} simple, {len(by_standard)} standard, {len(by_aggressive)} aggressive keys')

    # Load CA-only charged parties
    limit_clause = f'LIMIT {args.limit}' if args.limit else ''
    cur.execute(f"""
        SELECT p.id, p.participant_name, p.case_number,
               c.region
        FROM nlrb_participants p
        JOIN nlrb_cases c ON c.case_number = p.case_number
        WHERE p.participant_type = 'Charged Party / Respondent'
          AND p.case_number ~ '-CA-'
          AND p.matched_employer_id IS NULL
        {limit_clause}
    """)
    rows = cur.fetchall()
    print(f'  {len(rows):,} unmatched CA charged party records loaded')

    # Process
    stats = {
        'total': len(rows),
        'extracted': 0,
        'skipped_person': 0,
        'skipped_lawfirm': 0,
        'skipped_empty': 0,
        'matched': 0,
        'unmatched': 0,
    }
    method_counts = defaultdict(int)
    matches = []  # (participant_id, employer_id, confidence, method)

    for pid, pname, case_num, region in rows:
        employer_name = extract_employer_name(pname)
        if not employer_name:
            if pname and '\n' in pname:
                lines = pname.strip().split('\n')
                if len(lines) >= 2 and is_law_firm(lines[1].strip()):
                    stats['skipped_lawfirm'] += 1
                elif is_person_name(pname.strip().split('\n')[0].strip()):
                    stats['skipped_person'] += 1
                else:
                    stats['skipped_empty'] += 1
            elif pname and is_person_name(pname.strip()):
                stats['skipped_person'] += 1
            else:
                stats['skipped_empty'] += 1
            continue

        stats['extracted'] += 1
        result = match_name(employer_name, region, by_standard, by_aggressive, by_simple)

        if result:
            eid, conf, method = result
            matches.append((pid, eid, conf, method))
            method_counts[method] += 1
            stats['matched'] += 1
            if args.verbose:
                print(f'  MATCH: {employer_name[:50]:50s} -> {eid} ({method}, {conf:.2f})')
        else:
            stats['unmatched'] += 1

    # Summary
    print(f'\n=== NLRB ULP MATCHING RESULTS ===')
    print(f'Total CA records:    {stats["total"]:>8,}')
    print(f'Names extracted:     {stats["extracted"]:>8,}')
    print(f'  Skipped (person):  {stats["skipped_person"]:>8,}')
    print(f'  Skipped (lawfirm): {stats["skipped_lawfirm"]:>8,}')
    print(f'  Skipped (empty):   {stats["skipped_empty"]:>8,}')
    print(f'Matched:             {stats["matched"]:>8,} ({100*stats["matched"]/max(stats["extracted"],1):.1f}% of extracted)')
    print(f'Unmatched:           {stats["unmatched"]:>8,}')

    print(f'\nMatch methods:')
    for method, cnt in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f'  {method:30s}: {cnt:>7,}')

    # Distinct employers matched
    distinct_employers = len(set(m[1] for m in matches))
    print(f'\nDistinct F7 employers matched: {distinct_employers:,}')

    if args.commit and matches:
        print(f'\nWriting {len(matches):,} matches to nlrb_participants...')
        batch_size = 5000
        for i in range(0, len(matches), batch_size):
            batch = matches[i:i+batch_size]
            # Build VALUES for batch update
            cur.execute("""
                CREATE TEMP TABLE IF NOT EXISTS _ulp_matches (
                    pid BIGINT, employer_id TEXT, confidence NUMERIC, method TEXT
                ) ON COMMIT DROP
            """)
            from psycopg2.extras import execute_values
            execute_values(cur, """
                INSERT INTO _ulp_matches (pid, employer_id, confidence, method)
                VALUES %s
            """, batch)
            cur.execute("""
                UPDATE nlrb_participants p
                SET matched_employer_id = m.employer_id,
                    match_confidence = m.confidence,
                    match_method = m.method
                FROM _ulp_matches m
                WHERE p.id = m.pid
            """)
            cur.execute("DROP TABLE IF EXISTS _ulp_matches")
            if (i // batch_size) % 10 == 0:
                print(f'  Batch {i//batch_size + 1}: {min(i+batch_size, len(matches)):,}/{len(matches):,}')

        if args.log:
            print('Writing to unified_match_log...')
            # Group by employer_id, take highest confidence per employer
            best_per_employer = {}
            for pid, eid, conf, method in matches:
                if eid not in best_per_employer or conf > best_per_employer[eid][1]:
                    best_per_employer[eid] = (pid, conf, method)

            log_rows = [
                (eid, 'nlrb_ulp', str(pid), conf, method, 'active')
                for eid, (pid, conf, method) in best_per_employer.items()
            ]
            execute_values(cur, """
                INSERT INTO unified_match_log
                    (f7_employer_id, source_type, source_id, confidence, match_tier, status)
                VALUES %s
                ON CONFLICT DO NOTHING
            """, log_rows)
            print(f'  Wrote {len(log_rows):,} UML entries')

        conn.commit()
        print('COMMITTED.')
    elif not args.commit:
        print('\nDry run. Use --commit to apply.')

    conn.close()


if __name__ == '__main__':
    main()
