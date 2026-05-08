"""
Name-based fallback match for web_union_profiles where local-number match failed.

Scope: APWU state-level profiles only (validated 2026-04-24). The AFSCME
unmatched tail turned out to have no usable distinguishing name field in
unions_master (`desig_name` is a type code like 'LU'/'DC', not a human-readable
local name), so AFSCME is intentionally NOT handled here.

APWU logic:
    - Find UNMATCHED profiles whose union_name contains a state-level hint:
        * "State APWU"
        * "APWU of {STATE}"
        * "{STATE} Postal Workers Union"
    - Each US state has exactly one `unions_master` row with
      aff_abbr='APWU', desig_name='SA', state=XX.
    - If the profile's state matches, promote the profile to
      match_status='MATCHED_OLMS_NAME' with that SA row's f_num.

Usage:
    py -u scripts/matching/match_web_profiles_by_name.py --dry-run
    py -u scripts/matching/match_web_profiles_by_name.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


STATE_NAME_TO_CODE = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'district of columbia': 'DC', 'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI',
    'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
    'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME',
    'maryland': 'MD', 'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN',
    'mississippi': 'MS', 'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE',
    'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ', 'new mexico': 'NM',
    'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
    'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI',
    'south carolina': 'SC', 'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX',
    'utah': 'UT', 'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA',
    'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY', 'puerto rico': 'PR',
}

# Pattern: "State APWU", "APWU of X", "X Postal Workers Union", "X State APWU"
STATE_LEVEL_PATTERNS = [
    re.compile(r'\bAPWU\s+of\s+([A-Za-z ]+)', re.IGNORECASE),
    re.compile(r'\b([A-Za-z ]+?)\s+State\s+APWU\b', re.IGNORECASE),
    re.compile(r'\b([A-Za-z ]+?)\s+Postal\s+Workers\s+Union\b', re.IGNORECASE),
]


def extract_state_from_name(union_name: str) -> str | None:
    """Return a 2-letter state code if the union_name matches a state-level
    pattern AND the captured state name maps cleanly to a code."""
    if not union_name:
        return None
    for pat in STATE_LEVEL_PATTERNS:
        m = pat.search(union_name)
        if not m:
            continue
        captured = m.group(1).strip().lower()
        if captured in STATE_NAME_TO_CODE:
            return STATE_NAME_TO_CODE[captured]
    return None


def match_apwu_state_unions(conn, dry_run: bool = False) -> dict:
    """Find APWU unmatched profiles that are state-level unions and match to
    the parent union's SA row in unions_master."""
    cur = conn.cursor()

    cur.execute(
        """SELECT id, state, union_name FROM web_union_profiles
           WHERE parent_union = 'APWU' AND match_status = 'UNMATCHED'"""
    )
    unmatched = cur.fetchall()

    # Index OLMS SA rows by state (one row per state)
    cur.execute(
        """SELECT state, f_num, members FROM unions_master
           WHERE aff_abbr = 'APWU' AND desig_name = 'SA'"""
    )
    sa_by_state = {row[0]: (row[1], row[2]) for row in cur.fetchall() if row[0]}

    matched = 0
    skipped_no_state_hint = 0
    skipped_state_mismatch = 0
    skipped_no_sa_row = 0

    for pid, profile_state, union_name in unmatched:
        # Extract state from name
        name_state = extract_state_from_name(union_name)
        if not name_state:
            skipped_no_state_hint += 1
            continue
        # Reconcile with profile state if populated
        effective_state = profile_state or name_state
        if profile_state and profile_state != name_state:
            skipped_state_mismatch += 1
            continue
        # Look up the SA row
        sa = sa_by_state.get(effective_state)
        if not sa:
            skipped_no_sa_row += 1
            continue
        f_num, members = sa
        print(f'  [MATCH] pid={pid} state={effective_state} name={union_name!r:55} -> SA f_num={f_num} members={members}')
        if not dry_run:
            cur.execute(
                """UPDATE web_union_profiles
                   SET f_num = %s,
                       match_status = 'MATCHED_OLMS_NAME',
                       state = COALESCE(state, %s),
                       extra_data = COALESCE(extra_data, '{}'::jsonb)
                                    || jsonb_build_object(
                                        'name_match_rule', 'apwu_state_association',
                                        'name_match_olms_f_num', %s
                                       )
                   WHERE id = %s""",
                (f_num, effective_state, f_num, pid),
            )
        matched += 1

    if not dry_run:
        conn.commit()
    return {
        'matched': matched,
        'skipped_no_state_hint': skipped_no_state_hint,
        'skipped_state_mismatch': skipped_state_mismatch,
        'skipped_no_sa_row': skipped_no_sa_row,
        'total_unmatched_considered': len(unmatched),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true',
                    help='Plan matches without committing')
    args = ap.parse_args()

    conn = get_connection()
    print(f'[APWU state-association match{"" if not args.dry_run else " (dry-run)"}]')
    stats = match_apwu_state_unions(conn, dry_run=args.dry_run)
    print()
    print('--- stats ---')
    for k, v in stats.items():
        print(f'  {k:30s} {v}')
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
