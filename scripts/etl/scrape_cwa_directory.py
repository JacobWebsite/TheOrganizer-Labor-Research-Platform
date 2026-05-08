"""
CWA (Communications Workers of America) Locals Directory Scraper
-----------------------------------------------------------------
CWA publishes a paginated Drupal Views list at
`https://www.cwa-union.org/members/find-your-local?page=N` with 8 locals per
page. Each local is an `<article class="node local-directory-item ...">`
containing a microformat address (`address-line1`, `locality`,
`administrative-area`, `postal-code`), phone/fax (`<a href="tel:...">`),
optional website (non-tel anchor), and district tag (last `<div>`).

Observed range as of 2026-04-21: pages 0-89 contain 8 locals each (720 rows),
page 90 returns zero. One sentinel row "Dummy Local 99999" is filtered out.
Expected unique real locals: ~700, with ~670 after dedup against the OLMS
aff_abbr='CWA' universe of 974.

Usage:
    py -u scripts/etl/scrape_cwa_directory.py --dry-run          # page 0 only
    py -u scripts/etl/scrape_cwa_directory.py --page 5 --dry-run # single page
    py -u scripts/etl/scrape_cwa_directory.py                    # full run
    py -u scripts/etl/scrape_cwa_directory.py --match-only       # rematch OLMS
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


PARENT_UNION = 'CWA'
BASE_URL = 'https://www.cwa-union.org/members/find-your-local'
USER_AGENT = 'LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)'

# Captures the digits after "Local " in names like:
#   "CWA Local 1036", "CWA LOCAL 1000", "IUE-CWA Local 86823"
LOCAL_NUMBER_RE = re.compile(r'\bLocal\s+#?(\d+[A-Za-z\-]*)\b', re.IGNORECASE)

# Sentinel / test rows to skip
NAME_BLOCKLIST_RE = re.compile(r'\b(dummy|test|placeholder)\b', re.IGNORECASE)

FETCH_TIMEOUT = 30
FETCH_SLEEP_SEC = 0.8  # polite pacing between pages
MAX_PAGES_DEFAULT = 150  # well above observed ~90; loop terminates on empty


def fetch_page(page: int) -> Optional[str]:
    """Return HTML text for a given page, or None on error/empty."""
    url = f'{BASE_URL}?page={page}'
    try:
        r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=FETCH_TIMEOUT)
        if r.status_code != 200:
            print(f'  [WARN] page={page} status={r.status_code}')
            return None
        return r.text
    except requests.RequestException as e:
        print(f'  [WARN] page={page} fetch error: {e}')
        return None


def parse_article(art) -> Optional[dict]:
    """Parse one <article> card. Returns row dict or None if unusable."""
    h2 = art.find('h2')
    if not h2:
        return None
    name = h2.get_text(' ', strip=True)
    if NAME_BLOCKLIST_RE.search(name):
        return None

    m = LOCAL_NUMBER_RE.search(name)
    local_number = m.group(1) if m else None

    # Address microformat (hCard-ish)
    address = city = state = zip_code = None
    addr_p = art.find('p', class_='address')
    if addr_p:
        al1 = addr_p.find('span', class_='address-line1')
        loc = addr_p.find('span', class_='locality')
        admin = addr_p.find('span', class_='administrative-area')
        pc = addr_p.find('span', class_='postal-code')
        street = al1.get_text(' ', strip=True) if al1 else None
        city = loc.get_text(' ', strip=True) if loc else None
        state = admin.get_text(' ', strip=True) if admin else None
        zip_code = pc.get_text(' ', strip=True) if pc else None
        # Full address string (mirror APWU/SEIU pattern)
        parts = [street, city, state, zip_code]
        address = ', '.join(x for x in parts if x) or None

    # Phone / fax: CWA uses two <a href="tel:...">  links in order P then F
    tel_links = art.find_all('a', href=lambda h: h and h.startswith('tel:'))
    phone = tel_links[0].get_text(' ', strip=True) if len(tel_links) >= 1 else None
    fax = tel_links[1].get_text(' ', strip=True) if len(tel_links) >= 2 else None

    # Website: first non-tel anchor
    website = None
    for a in art.find_all('a'):
        href = a.get('href', '')
        if href and not href.startswith('tel:') and not href.startswith('mailto:'):
            website = href.strip()
            break

    # District: look for a div whose text starts "District ..." or equals "Canada"
    district = None
    for div in art.find_all('div'):
        txt = div.get_text(' ', strip=True)
        if txt and (txt.startswith('District ') or txt == 'Canada'):
            district = txt
            break

    # Normalize state — CWA Canada rows leave administrative-area empty or show
    # a province code like "ON". We leave as-is but note it in extra so OLMS
    # matching (which is US-only for CWA in unions_master) naturally skips.
    extra = {
        'source': 'cwa_find_your_local',
        'district': district,
        'city': city,
        'zip': zip_code,
        'raw_name': name,
    }

    return {
        'union_name': name,
        'local_number': local_number,
        'state': state,
        'website_url': website,
        'address': address,
        'phone': phone,
        'fax': fax,
        'extra': extra,
    }


def parse_page_html(html: str) -> list[dict]:
    """Parse a page's HTML into a list of row dicts."""
    soup = BeautifulSoup(html, 'lxml')
    out = []
    for art in soup.find_all('article'):
        cls = art.get('class') or []
        if 'local-directory-item' not in cls:
            continue
        row = parse_article(art)
        if row:
            out.append(row)
    return out


def upsert_profile(cur, row: dict) -> str:
    """Insert-or-update. Keys on (parent, local_number, state) when possible,
    else (parent, union_name, state) to stay idempotent."""
    if row['local_number'] and row['state']:
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND local_number = %s AND state = %s""",
            (PARENT_UNION, row['local_number'], row['state']),
        )
    elif row['local_number']:
        # No state (Canada rows): key on (parent, local_number) alone — CWA
        # locals are globally numbered so collision risk is low.
        cur.execute(
            """SELECT id FROM web_union_profiles
               WHERE parent_union = %s AND local_number = %s AND state IS NULL""",
            (PARENT_UNION, row['local_number']),
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
    source_url = f'{BASE_URL}?page=0'

    if existing:
        cur.execute(
            """UPDATE web_union_profiles SET
                   union_name = %s,
                   website_url = COALESCE(%s, website_url),
                   address = COALESCE(%s, address),
                   phone = COALESCE(%s, phone),
                   fax = COALESCE(%s, fax),
                   source_directory_url = %s,
                   extra_data = COALESCE(extra_data, '{}'::jsonb) || %s::jsonb,
                   scrape_status = CASE
                       WHEN scrape_status IN ('PENDING', 'NO_WEBSITE') THEN %s
                       ELSE scrape_status
                   END
               WHERE id = %s""",
            (
                row['union_name'],
                row['website_url'], row['address'],
                row['phone'], row['fax'],
                source_url,
                json.dumps(row['extra']),
                scrape_status,
                existing[0],
            ),
        )
        return 'updated'
    cur.execute(
        """INSERT INTO web_union_profiles
               (union_name, local_number, parent_union, state, website_url,
                scrape_status, source_directory_url, address, phone, fax, extra_data)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (
            row['union_name'], row['local_number'], PARENT_UNION, row['state'],
            row['website_url'], scrape_status, source_url,
            row['address'], row['phone'], row['fax'],
            json.dumps(row['extra']),
        ),
    )
    return 'inserted'


def match_olms(conn) -> dict:
    """Match CWA web profiles to unions_master by (aff_abbr='CWA', local_number, state)."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, local_number, state FROM web_union_profiles
           WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    profiles = cur.fetchall()

    cur.execute(
        """SELECT f_num, local_number, state, members
           FROM unions_master WHERE aff_abbr = 'CWA'"""
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
               COUNT(*) FILTER (WHERE phone IS NOT NULL) AS with_phone,
               COUNT(*) FILTER (WHERE local_number IS NOT NULL) AS with_local_num,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS') AS matched,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS_CROSS_STATE') AS cross_state,
               COUNT(*) FILTER (WHERE match_status = 'UNMATCHED') AS unmatched
           FROM web_union_profiles WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    r = cur.fetchone()
    print('--- CWA profile summary ---')
    keys = ['total', 'with_website', 'with_phone', 'with_local_num',
            'matched', 'cross_state', 'unmatched']
    for k, v in zip(keys, r):
        print(f'  {k:16s} {v}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='Fetch + parse; no DB writes')
    ap.add_argument('--match-only', action='store_true', help='Skip fetch; just rematch')
    ap.add_argument('--page', type=int, help='Fetch a single page (debug)')
    ap.add_argument('--max-pages', type=int, default=MAX_PAGES_DEFAULT,
                    help='Safety cap on pages to fetch')
    args = ap.parse_args()

    conn = get_connection()

    if args.match_only:
        print('[MATCH] Running OLMS match only...')
        counts = match_olms(conn)
        print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')
        report(conn)
        conn.close()
        return 0

    # Decide page range
    if args.page is not None:
        pages = [args.page]
    elif args.dry_run:
        pages = [0]  # default dry-run scope: page 0 only
    else:
        pages = list(range(args.max_pages))

    print(f'[STEP 1] Fetching CWA directory pages: {pages[0]}..{pages[-1]}')
    all_rows: list[dict] = []
    fetched = 0
    empty_streak = 0
    for p in pages:
        html = fetch_page(p)
        if html is None:
            empty_streak += 1
            if empty_streak >= 3:
                print(f'  [STOP] 3 consecutive fetch failures at page {p}, halting')
                break
            continue
        rows = parse_page_html(html)
        if not rows:
            print(f'  [END] page {p}: 0 locals (pagination exhausted)')
            break
        all_rows.extend(rows)
        fetched += 1
        empty_streak = 0
        # Only sleep in full runs, not single-page debug
        if args.page is None and not args.dry_run:
            time.sleep(FETCH_SLEEP_SEC)

    print(f'[OK] fetched {fetched} pages, {len(all_rows)} locals parsed')

    # Dedup by (local_number, state) within the fetch (defensive; Drupal shouldnt dupe)
    seen = set()
    deduped = []
    for r in all_rows:
        key = (r['local_number'], r['state'], r['union_name'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    if len(deduped) != len(all_rows):
        print(f'  [DEDUP] {len(all_rows)} -> {len(deduped)} unique rows')

    with_state = sum(1 for r in deduped if r['state'])
    with_web = sum(1 for r in deduped if r['website_url'])
    with_local = sum(1 for r in deduped if r['local_number'])
    with_phone = sum(1 for r in deduped if r['phone'])
    print(f'[PARSE] with_state={with_state} with_local_num={with_local} '
          f'with_website={with_web} with_phone={with_phone}')

    if args.dry_run:
        print('[DRY RUN] First 10 rows:')
        for r in deduped[:10]:
            print(' ', {k: v for k, v in r.items() if k != 'extra'})
            print('    extra:', r['extra'])
        stateless = [r for r in deduped if not r['state']]
        if stateless:
            print(f'  WARNING: {len(stateless)} rows have no state (Canada or parse issue):')
            for r in stateless[:3]:
                print('   ', r['union_name'], '|', r['extra'])
        conn.close()
        return 0

    print('[STEP 2] Upserting into web_union_profiles...')
    cur = conn.cursor()
    inserted = updated = errored = skipped = 0
    for row in deduped:
        # Allow no-state rows when local_number is present (Canada locals)
        if not row['state'] and not row['local_number']:
            skipped += 1
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
    print(f'[OK] inserted={inserted} updated={updated} errored={errored} skipped={skipped}')

    print('[STEP 3] Matching CWA profiles to unions_master...')
    counts = match_olms(conn)
    print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')

    report(conn)
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
