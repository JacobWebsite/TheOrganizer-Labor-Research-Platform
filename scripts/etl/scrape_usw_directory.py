"""
USW (United Steelworkers) Locals Directory Scraper
---------------------------------------------------
USW publishes per-district "local websites" pages at
`https://usw.org/districts/district-<N>/district-<N>-local-websites/`.
Only districts with active locals are listed; District 10 returns 404 in
2026-04. Each district page contains anchor tags to the local's public site
on `uswlocals.org/<slug>` (primary) or `myuswlocal.org/sites/US/LU<NUMBER>`
(legacy). Anchor text is typically "USW Local 1-112", "USW Local 207L*", or
"USW Local 1123*" (asterisks denote special-status).

The USW numbering format differs from OLMS:
  - Website: "1-112"  <-> OLMS: "112"    (district-prefix hyphen)
  - Website: "207L"   <-> OLMS: "207"    (alpha suffix = subordinate unit)
  - Website: "1123*"  <-> OLMS: "1123"   (asterisk = retiree/special)

The scraper stores the raw website-form in `union_name` and extracts a
canonical numeric-only `local_number` for OLMS matching. State is inferred
from the URL slug's trailing token when present (e.g. "...middletownohio" →
"OH"); otherwise left NULL so cross-state fallback catches it.

Usage:
    py -u scripts/etl/scrape_usw_directory.py --dry-run
    py -u scripts/etl/scrape_usw_directory.py --district 1 --dry-run
    py -u scripts/etl/scrape_usw_directory.py                   # full run
    py -u scripts/etl/scrape_usw_directory.py --match-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


PARENT_UNION = 'USW'
US_DISTRICTS = [1, 4, 7, 8, 9, 10, 11, 12, 13]  # 10 is 404 but loop handles it
BASE_URL_TEMPLATE = 'https://usw.org/districts/district-{d}/district-{d}-local-websites/'
USER_AGENT = 'LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)'

FETCH_TIMEOUT = 30
FETCH_SLEEP_SEC = 0.5

# Match "USW Local 1-112", "Local 207L", "Local 1123*"
LOCAL_NAME_RE = re.compile(r'\bLocal\s+#?([\d\-]+[A-Za-z]*)\*?', re.IGNORECASE)

# US states for slug inference
STATE_NAMES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'florida': 'FL', 'georgia': 'GA', 'hawaii': 'HI', 'idaho': 'ID',
    'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA', 'kansas': 'KS',
    'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
    'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV',
    'newhampshire': 'NH', 'newjersey': 'NJ', 'newmexico': 'NM', 'newyork': 'NY',
    'northcarolina': 'NC', 'northdakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK',
    'oregon': 'OR', 'pennsylvania': 'PA', 'rhodeisland': 'RI', 'southcarolina': 'SC',
    'southdakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT',
    'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA', 'westvirginia': 'WV',
    'wisconsin': 'WI', 'wyoming': 'WY',
}
STATE_ABBR = set(STATE_NAMES.values())


def fetch_district_page(s: requests.Session, district: int) -> Optional[str]:
    url = BASE_URL_TEMPLATE.format(d=district)
    try:
        r = s.get(url, timeout=FETCH_TIMEOUT)
        if r.status_code == 404:
            print(f'  [404] District {district} has no local-websites page')
            return None
        if r.status_code != 200:
            print(f'  [WARN] District {district}: status {r.status_code}')
            return None
        return r.text
    except requests.RequestException as e:
        print(f'  [WARN] District {district}: {e}')
        return None


def _infer_state_from_slug(url: str) -> Optional[str]:
    """Parse the trailing slug tokens for a US state hint."""
    path = urlparse(url).path.lower()
    # take the last segment
    slug = path.rstrip('/').rsplit('/', 1)[-1]
    # split on hyphens, look at last 1-3 tokens
    parts = slug.split('-')
    if not parts:
        return None
    # Check last token as 2-letter state abbrev
    last = parts[-1].upper()
    if last in STATE_ABBR:
        return last
    # Check last token as full state name (e.g. 'ohio', 'pennsylvania')
    for n in range(1, min(4, len(parts) + 1)):
        tail = ''.join(parts[-n:]).lower()
        if tail in STATE_NAMES:
            return STATE_NAMES[tail]
    # One-word 'ohio' already handled via STATE_NAMES
    return None


def _canonical_local_number(raw: str) -> Optional[str]:
    """Convert website-form '1-112' → '112', '207L' → '207', '1123*' → '1123'."""
    if not raw:
        return None
    cleaned = raw.strip().rstrip('*').strip()
    if not cleaned:
        return None
    # If hyphenated "X-Y", take Y (post-hyphen is the actual local)
    if '-' in cleaned:
        parts = cleaned.split('-')
        if len(parts) == 2 and parts[0].isdigit() and parts[1]:
            cleaned = parts[1]
    # Strip trailing alpha suffix (e.g. 207L → 207)
    m = re.match(r'^(\d+)([A-Za-z]+)$', cleaned)
    if m:
        cleaned = m.group(1)
    # Validate final form is pure digits (OLMS format)
    if cleaned.isdigit():
        return cleaned
    return None


def parse_district_page(html: str, district: int) -> list[dict]:
    """Extract local rows from a district-N-local-websites page."""
    soup = BeautifulSoup(html, 'lxml')
    out: list[dict] = []
    seen = set()  # by url

    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        txt = a.get_text(' ', strip=True)
        if not href.startswith('http'):
            continue
        host = urlparse(href).netloc.lower()
        # Only accept the USW local platforms or known redirect hosts
        if not ('uswlocals.org' in host or 'myuswlocal.org' in host):
            continue
        if href in seen:
            continue
        seen.add(href)

        # Parse local number from anchor text first, fall back to URL slug
        local_raw = None
        m = LOCAL_NAME_RE.search(txt) if txt else None
        if m:
            local_raw = m.group(1)
        else:
            # URL slug: "local-1046-louisville-ohio" → "1046"
            slug = urlparse(href).path.rstrip('/').rsplit('/', 1)[-1]
            mm = re.match(r'(?:usw[-_])?local[-_#]?([\d\-]+[A-Za-z]*)', slug, re.IGNORECASE)
            if mm:
                local_raw = mm.group(1)

        if not local_raw:
            continue
        local_number = _canonical_local_number(local_raw)
        if not local_number:
            continue

        state = _infer_state_from_slug(href)

        name = txt or f'USW Local {local_raw}'
        # Clean up name: strip trailing '*' — keep "USW Local 207L" so users see
        # the distinguishing suffix, but use normalized local_number for matching.
        name = re.sub(r'\s*\*+\s*$', '', name).strip()
        if not name.lower().startswith('usw'):
            name = f'USW {name}' if name.lower().startswith('local') else f'USW Local {local_raw}'

        out.append({
            'union_name': name,
            'local_number': local_number,
            'local_raw': local_raw,
            'state': state,
            'website_url': href,
            'district': str(district),
            'has_asterisk': '*' in (txt or ''),
        })
    return out


def upsert_profile(cur, row: dict) -> str:
    """Insert-or-update. Keys on (parent, local_number, state) when possible."""
    if row['local_number'] and row['state']:
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND local_number = %s AND state = %s""",
            (PARENT_UNION, row['local_number'], row['state']),
        )
    elif row['local_number']:
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND local_number = %s AND state IS NULL""",
            (PARENT_UNION, row['local_number']),
        )
    else:
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND union_name = %s""",
            (PARENT_UNION, row['union_name']),
        )
    existing = cur.fetchone()

    scrape_status = 'DIRECTORY_ONLY'
    source_url = BASE_URL_TEMPLATE.format(d=row['district'])
    extra = {
        'source': 'usw_district_local_websites_page',
        'district': row['district'],
        'local_raw': row['local_raw'],
        'has_asterisk': row['has_asterisk'],
    }

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
    """Match USW web profiles to unions_master by (aff_abbr='USW', local_number, state)."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, local_number, state FROM web_union_profiles
           WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    profiles = cur.fetchall()

    cur.execute(
        """SELECT f_num, local_number, state, members
           FROM unions_master WHERE aff_abbr = 'USW'"""
    )
    rows = cur.fetchall()
    by_key: dict[tuple, list] = {}
    by_local: dict[str, list] = {}
    for f_num, local, st, members in rows:
        if local:
            k = (str(local).strip().upper(), (st or '').strip().upper())
            by_key.setdefault(k, []).append((f_num, members))
            by_local.setdefault(str(local).strip().upper(), []).append((f_num, st, members))

    matched = cross_state = unmatched = 0
    for pid, local, state in profiles:
        if not local:
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
            # Phase 5.2 + codex-hardened: require 2x member dominance before
            # auto-matching across states; else fall through to UNMATCHED.
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
               COUNT(*) FILTER (WHERE state IS NOT NULL) AS with_state,
               COUNT(*) FILTER (WHERE local_number IS NOT NULL) AS with_local_num,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS') AS matched,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS_CROSS_STATE') AS cross_state,
               COUNT(*) FILTER (WHERE match_status = 'UNMATCHED') AS unmatched
           FROM web_union_profiles WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    r = cur.fetchone()
    print('--- USW profile summary ---')
    keys = ['total', 'with_website', 'with_state', 'with_local_num',
            'matched', 'cross_state', 'unmatched']
    for k, v in zip(keys, r):
        print(f'  {k:16s} {v}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='Fetch + parse; no DB writes')
    ap.add_argument('--match-only', action='store_true', help='Skip fetch; just rematch')
    ap.add_argument('--district', type=int, help='Fetch single district for debug')
    args = ap.parse_args()

    conn = get_connection()

    if args.match_only:
        print('[MATCH] Running OLMS match only...')
        counts = match_olms(conn)
        print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')
        report(conn)
        conn.close()
        return 0

    s = requests.Session()
    s.headers.update({'User-Agent': USER_AGENT})

    districts = [args.district] if args.district else US_DISTRICTS
    print(f'[STEP 1] Fetching USW district pages: {districts}')
    all_rows: list[dict] = []
    for d in districts:
        html = fetch_district_page(s, d)
        if not html:
            continue
        rows = parse_district_page(html, d)
        print(f'  District {d:2d}: {len(rows)} locals')
        all_rows.extend(rows)
        if not args.dry_run and args.district is None:
            time.sleep(FETCH_SLEEP_SEC)

    # Dedup by URL — a local can appear on multiple district pages (rare but handle it)
    by_url: dict[str, dict] = {}
    for r in all_rows:
        prior = by_url.get(r['website_url'])
        if prior:
            # Keep the one with a state set, or the first otherwise
            if not prior['state'] and r['state']:
                by_url[r['website_url']] = r
        else:
            by_url[r['website_url']] = r
    deduped = list(by_url.values())
    print(f'[OK] {len(all_rows)} raw -> {len(deduped)} unique locals')

    with_state = sum(1 for r in deduped if r['state'])
    with_local = sum(1 for r in deduped if r['local_number'])
    print(f'[PARSE] with_state={with_state} with_local_num={with_local}')

    if args.dry_run:
        print('[DRY RUN] First 15 rows:')
        for r in deduped[:15]:
            print(' ', r)
        conn.close()
        return 0

    print('[STEP 2] Upserting into web_union_profiles...')
    cur = conn.cursor()
    inserted = updated = errored = 0
    for row in deduped:
        try:
            action = upsert_profile(cur, row)
            conn.commit()
            if action == 'inserted':
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f'  ERR upserting {row.get("union_name")!r}: {e}')
            conn.rollback()
            errored += 1
    print(f'[OK] inserted={inserted} updated={updated} errored={errored}')

    print('[STEP 3] Matching USW profiles to unions_master...')
    counts = match_olms(conn)
    print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')

    report(conn)
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
