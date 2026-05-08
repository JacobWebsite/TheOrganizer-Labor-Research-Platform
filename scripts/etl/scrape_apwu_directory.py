"""
APWU (American Postal Workers Union) Locals Directory Scraper
-------------------------------------------------------------
APWU publishes a static HTML directory grouping local union websites by state
at https://apwu.org/apwu-local-and-state-organization-links/.

Structure:
    <strong>Alabama</strong><br />
    <a class="external" href="URL" target="_blank" rel="noopener">Local Name</a><br />
    <a class="external" href="URL" ...>Another Local</a>
    <strong>Arizona</strong><br />
    ...

Every `<a class="external">` until the next `<strong>STATE</strong>` is a local
in that state. Names sometimes include the local number ('Fayetteville Local 667'),
sometimes don't ('Birmingham Area Local').

Usage:
    py -u scripts/etl/scrape_apwu_directory.py --dry-run
    py -u scripts/etl/scrape_apwu_directory.py
    py -u scripts/etl/scrape_apwu_directory.py --match-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


PARENT_UNION = 'APWU'
DIRECTORY_URL = 'https://apwu.org/apwu-local-and-state-organization-links/'
USER_AGENT = 'LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)'

# US state names -> 2-letter code. Only US covered for APWU.
STATE_NAMES = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
    'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
    'District of Columbia': 'DC', 'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI',
    'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME',
    'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE',
    'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM',
    'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH',
    'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Puerto Rico': 'PR',
    'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT',
    'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV',
    'Wisconsin': 'WI', 'Wyoming': 'WY',
}

# Extracts local number from end of names like "South Alabama Area Local 715"
# or "Fayetteville Local 667". NOT all locals have a number.
LOCAL_NUMBER_RE = re.compile(r'\bLocal\s+#?(\d+[A-Za-z]?)\s*$', re.IGNORECASE)


def fetch_page() -> str:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html'}
    r = requests.get(DIRECTORY_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def parse_local_number(name: str) -> Optional[str]:
    if not name:
        return None
    m = LOCAL_NUMBER_RE.search(name)
    return m.group(1).upper() if m else None


def parse_page(html: str) -> list[dict]:
    """Walk the directory page in document order. State name comes from the
    most recent preceding <strong>...</strong> whose text matches STATE_NAMES.

    Returns list of dicts with: union_name, local_number, state, website_url."""
    soup = BeautifulSoup(html, 'lxml')

    # Walk every strong+anchor element in document order across the whole page.
    # First state header observed activates; subsequent state headers switch.
    # We start collecting anchors only after we see the first state header,
    # which implicitly filters out nav/header anchors that appear before.
    current_state: Optional[str] = None
    out = []
    for el in soup.find_all(['strong', 'a']):
        if el.name == 'strong':
            txt = el.get_text(' ', strip=True)
            if txt in STATE_NAMES:
                current_state = STATE_NAMES[txt]
            continue
        # el.name == 'a'
        if current_state is None:
            # Haven't entered the directory body yet
            continue
        cls = el.get('class') or []
        if 'external' not in cls:
            continue
        href = (el.get('href') or '').strip()
        name = el.get_text(' ', strip=True)
        if not href or not name:
            continue
        # Filter out obvious non-local links (social media, blog posts)
        if any(d in href.lower() for d in
               ['facebook.com', 'twitter.com', 'youtube.com', 'instagram.com', 'linkedin.com']):
            continue
        out.append({
            'union_name': name,
            'local_number': parse_local_number(name),
            'state': current_state,
            'website_url': href,
        })
    return out


def upsert_profile(cur, row: dict) -> str:
    """Insert-or-update. For rows with local_number, key on (parent, local, state).
    For rows without, key on (parent, union_name, state) to stay idempotent."""
    if row['local_number']:
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND local_number = %s AND state = %s""",
            (PARENT_UNION, row['local_number'], row['state']),
        )
    else:
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND local_number IS NULL
                 AND union_name = %s AND state = %s""",
            (PARENT_UNION, row['union_name'], row['state']),
        )
    existing = cur.fetchone()

    scrape_status = 'DIRECTORY_ONLY'
    extra = {'source': 'apwu_state_links_page'}
    source_url = DIRECTORY_URL

    if existing:
        cur.execute(
            """UPDATE web_union_profiles SET
                   union_name = %s,
                   website_url = COALESCE(%s, website_url),
                   source_directory_url = %s,
                   extra_data = COALESCE(extra_data, '{}'::jsonb) || %s::jsonb,
                   scrape_status = CASE
                       WHEN scrape_status IN ('PENDING', 'NO_WEBSITE') THEN %s
                       ELSE scrape_status
                   END
               WHERE id = %s""",
            (
                row['union_name'],
                row['website_url'],
                source_url,
                json.dumps(extra),
                scrape_status,
                existing[0],
            ),
        )
        return 'updated'
    cur.execute(
        """INSERT INTO web_union_profiles
               (union_name, local_number, parent_union, state, website_url,
                scrape_status, source_directory_url, extra_data)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (
            row['union_name'], row['local_number'], PARENT_UNION, row['state'],
            row['website_url'], scrape_status, source_url,
            json.dumps(extra),
        ),
    )
    return 'inserted'


def match_olms(conn) -> dict:
    """Match APWU web profiles to unions_master."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, local_number, state, union_name FROM web_union_profiles
           WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    profiles = cur.fetchall()

    cur.execute(
        """SELECT f_num, local_number, state, members, desig_name, union_name
           FROM unions_master WHERE aff_abbr = 'APWU'"""
    )
    rows = cur.fetchall()
    by_key: dict[tuple, list] = {}
    by_local: dict[str, list] = {}
    for f_num, local, st, members, desig, uname in rows:
        if local:
            k = (str(local).strip().upper(), (st or '').strip().upper())
            by_key.setdefault(k, []).append((f_num, members))
            by_local.setdefault(str(local).strip().upper(), []).append((f_num, st, members))

    matched = cross_state = unmatched = 0
    for pid, local, state, _name in profiles:
        if not local:
            # No local number on our side; mark UNMATCHED for now (name-based match is
            # a Phase 5 cleanup task, to keep this scraper simple).
            cur.execute(
                """UPDATE web_union_profiles
                   SET match_status = 'UNMATCHED', f_num = NULL
                   WHERE id = %s""",
                (pid,),
            )
            unmatched += 1
            continue
        key = (str(local).strip().upper(), (state or '').strip().upper())
        cands = by_key.get(key, [])
        if cands:
            f_num = max(cands, key=lambda x: x[1] or 0)[0]
            cur.execute(
                """UPDATE web_union_profiles
                   SET f_num = %s, match_status = 'MATCHED_OLMS'
                   WHERE id = %s""",
                (f_num, pid),
            )
            matched += 1
            continue
        loc_cands = by_local.get(str(local).strip().upper(), [])
        if loc_cands:
            # Phase 5.2 + codex-hardened: pick highest-member cross-state candidate
            # but ONLY when it dominates the runner-up by >= 2x. This avoids
            # silently promoting a genuinely-ambiguous shared-number local to a
            # confident but possibly-wrong f_num. If dominance fails, fall through
            # to UNMATCHED so the row surfaces in review.
            sorted_cands = sorted(loc_cands, key=lambda x: x[2] or 0, reverse=True)
            top_members = sorted_cands[0][2] or 0
            runner_up = sorted_cands[1][2] or 0 if len(sorted_cands) > 1 else 0
            if len(sorted_cands) == 1 or top_members >= 2 * max(runner_up, 1):
                f_num = sorted_cands[0][0]
                cur.execute(
                    """UPDATE web_union_profiles
                       SET f_num = %s, match_status = 'MATCHED_OLMS_CROSS_STATE'
                       WHERE id = %s""",
                    (f_num, pid),
                )
                cross_state += 1
                continue
        cur.execute(
            """UPDATE web_union_profiles
               SET match_status = 'UNMATCHED', f_num = NULL
               WHERE id = %s""",
            (pid,),
        )
        unmatched += 1
    conn.commit()
    return {'matched': matched, 'cross_state_matched': cross_state, 'unmatched': unmatched}


def report(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """SELECT
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE website_url IS NOT NULL) AS with_website,
               COUNT(*) FILTER (WHERE local_number IS NOT NULL) AS with_local_num,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS') AS matched,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS_CROSS_STATE') AS cross_state,
               COUNT(*) FILTER (WHERE match_status = 'UNMATCHED') AS unmatched
           FROM web_union_profiles WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    r = cur.fetchone()
    print('--- APWU profile summary ---')
    keys = ['total', 'with_website', 'with_local_num', 'matched', 'cross_state', 'unmatched']
    for k, v in zip(keys, r):
        print(f'  {k:16s} {v}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='Fetch + parse; no DB writes')
    ap.add_argument('--match-only', action='store_true', help='Skip fetch; just rematch')
    args = ap.parse_args()

    conn = get_connection()

    if args.match_only:
        print('[MATCH] Running OLMS match only...')
        counts = match_olms(conn)
        print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')
        report(conn)
        conn.close()
        return 0

    print(f'[STEP 1] Fetching {DIRECTORY_URL}')
    html = fetch_page()
    print(f'[OK] {len(html):,} bytes')

    print('[STEP 2] Parsing state sections + external links...')
    rows = parse_page(html)
    with_state = sum(1 for r in rows if r['state'])
    with_local_num = sum(1 for r in rows if r['local_number'])
    print(f'[OK] {len(rows)} locals; with_state={with_state}; with_local_num={with_local_num}')

    if args.dry_run:
        print('[DRY RUN] First 10 rows:')
        for r in rows[:10]:
            print(' ', r)
        # Also show any state-less rows as warnings
        stateless = [r for r in rows if not r['state']]
        if stateless:
            print(f'  WARNING: {len(stateless)} rows have no state (parse order issue):')
            for r in stateless[:3]:
                print('   ', r)
        conn.close()
        return 0

    print('[STEP 3] Upserting into web_union_profiles...')
    cur = conn.cursor()
    inserted = updated = errored = skipped_nostate = 0
    for row in rows:
        if not row['state']:
            skipped_nostate += 1
            continue
        try:
            action = upsert_profile(cur, row)
            conn.commit()
            if action == 'inserted':
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f'  ERR upserting {row.get("union_name")!r}/{row.get("state")}: {e}')
            conn.rollback()
            errored += 1
            continue
    print(f'[OK] inserted={inserted} updated={updated} errored={errored} skipped_nostate={skipped_nostate}')

    print('[STEP 4] Matching APWU profiles to unions_master...')
    counts = match_olms(conn)
    print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')

    report(conn)
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
