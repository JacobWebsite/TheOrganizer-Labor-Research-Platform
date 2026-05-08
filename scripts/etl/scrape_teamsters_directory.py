"""
Teamsters (IBT) Locals Directory Scraper
----------------------------------------
Pulls ~331 Teamsters local union profiles from teamster.org and loads them
into web_union_profiles with parent_union='IBT'.

Two-stage fetch:
  1. WP REST API (teamster.org/wp-json/wp/v2/local) -> canonical list + state
  2. State-filtered HTML pages (/locals/?local-state=XX) -> contact details

Each local is tagged with its Teamsters divisions so downstream filters can
split public-sector (public-services-healthcare-division) from private-sector
(freight, package, warehouse, etc.).

Also matches each profile to unions_master by (aff_abbr='IBT', local_number,
state) -- with a cross-state fallback for locals whose registered OLMS state
differs from the directory state.

Usage:
    py -u scripts/etl/scrape_teamsters_directory.py --dry-run --state NY
    py -u scripts/etl/scrape_teamsters_directory.py --state NY
    py -u scripts/etl/scrape_teamsters_directory.py           # all states
    py -u scripts/etl/scrape_teamsters_directory.py --match-only
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


PARENT_UNION = 'IBT'
BASE = 'https://teamster.org'
WP_API = f'{BASE}/wp-json/wp/v2/local'
STATE_PAGE = f'{BASE}/locals/?local-state={{state}}'
USER_AGENT = 'LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)'
RATE_LIMIT_SECS = 1.2

PUBLIC_SECTOR_DIVISIONS = {'public-services-healthcare-division'}


def http_get(url: str, timeout: int = 60, retries: int = 3) -> requests.Response:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,application/json'}
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            time.sleep(2 + attempt * 2)
    raise last_exc  # type: ignore[misc]


def fetch_wp_local_list() -> list[dict]:
    """Fetch all Teamsters locals via WP REST API. Returns list of dicts with
    id, slug, title, link, state, divisions (slugs)."""
    out = []
    per_page = 100
    page = 1
    while True:
        url = f'{WP_API}?per_page={per_page}&page={page}&_embed'
        r = http_get(url)
        batch = r.json()
        if not batch:
            break
        total_pages = int(r.headers.get('X-WP-TotalPages', '1'))
        for lu in batch:
            state_slug = None
            division_slugs = []
            for group in lu.get('_embedded', {}).get('wp:term', []):
                for term in group:
                    tax = term.get('taxonomy')
                    if tax == 'local-state' and not state_slug:
                        state_slug = (term.get('slug') or '').upper()
                    elif tax == 'division-news':
                        division_slugs.append(term.get('slug'))
            # Fallback: scan class_list for local-state-XX if taxonomy missing
            if not state_slug:
                for cls in lu.get('class_list', []):
                    if cls.startswith('local-state-'):
                        state_slug = cls.replace('local-state-', '').upper()
                        break
            out.append({
                'wp_id': lu['id'],
                'slug': lu.get('slug'),
                'title': (lu.get('title', {}) or {}).get('rendered') or '',
                'link': lu.get('link'),
                'state': state_slug,
                'divisions': division_slugs,
            })
        if page >= total_pages:
            break
        page += 1
        time.sleep(RATE_LIMIT_SECS)
    return out


LOCAL_NUMBER_RE = re.compile(r'(?:LU\s*No?\.?|Local)\s*#?\s*([0-9]+[A-Z]?)', re.IGNORECASE)


def parse_local_number(title: str) -> Optional[str]:
    """Extract the local number from titles like 'Teamsters LU No 118'."""
    if not title:
        return None
    m = LOCAL_NUMBER_RE.search(title)
    if m:
        return m.group(1).upper()
    # Fallback: last number in the title
    nums = re.findall(r'\b(\d+[A-Z]?)\b', title)
    return nums[-1].upper() if nums else None


def parse_state_page(html: str, state: str) -> list[dict]:
    """Parse a teamster.org state-filtered directory page into per-local dicts."""
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    for div in soup.select('div.local'):
        # Extract state from class list (authoritative) with fallback to arg
        classes = div.get('class', [])
        page_state = state
        division_slugs = []
        for cls in classes:
            if cls.startswith('local-state-'):
                page_state = cls.replace('local-state-', '').upper()
            elif cls.startswith('division-news-'):
                division_slugs.append(cls.replace('division-news-', ''))

        title_el = div.select_one('h4.local--title, h4.local--title.org')
        title = title_el.get_text(strip=True) if title_el else ''
        local_num = parse_local_number(title)

        # President / Secretary-Treasurer etc.
        officers_parts = []
        for p in div.select('p.local--sub'):
            text = p.get_text(' ', strip=True)
            # Divisions are also in local--sub, but we handle those via class list
            if text.lower().startswith('divisions/conferences'):
                continue
            officers_parts.append(text)
        officers = ' | '.join(officers_parts) if officers_parts else None

        phone_el = div.select_one('p.local--foot.tel a[href^="tel:"]')
        phone = None
        if phone_el:
            phone = phone_el.get_text(strip=True) or phone_el.get('href', '').replace('tel:', '')

        website = None
        website_el = div.select_one('p.local--foot.url a[href]')
        if website_el:
            href = website_el.get('href', '').strip()
            if href:
                # Strip protocol-relative // or normalize
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('www.'):
                    href = 'https://' + href
                elif not href.startswith(('http://', 'https://')):
                    href = 'https://' + href.lstrip('/')
                # Some entries contain the malformed '//https//:www.ibt707.com' form
                href = href.replace('//https//:', 'https://')
                website = href

        email_el = div.select_one('a.local--foot.email, a[href^="mailto:"]')
        email = None
        if email_el:
            mailto = email_el.get('href', '')
            if mailto.startswith('mailto:'):
                email = mailto.replace('mailto:', '').strip() or None
            else:
                email = email_el.get_text(strip=True) or None

        addr_el = div.select_one('div.local--adr p.street-address')
        address_text = None
        locality = region = postal = None
        if addr_el:
            locality_el = addr_el.select_one('span.locality')
            region_el = addr_el.select_one('span.region')
            postal_el = addr_el.select_one('span.postal-code')
            locality = locality_el.get_text(strip=True) if locality_el else None
            region = region_el.get_text(strip=True) if region_el else None
            postal = postal_el.get_text(strip=True) if postal_el else None
            # Reconstruct full address (street is the first text node before <br>)
            # Take the full text minus the structured spans, and collapse whitespace
            raw = addr_el.get_text(' ', strip=True)
            address_text = re.sub(r'\s+', ' ', raw).strip()

        is_public_sector = any(d in PUBLIC_SECTOR_DIVISIONS for d in division_slugs)

        results.append({
            'state': page_state,
            'title': title,
            'local_number': local_num,
            'officers': officers,
            'phone': phone,
            'website_url': website,
            'email': email,
            'address': address_text,
            'city': locality,
            'region': region,
            'postal': postal,
            'divisions': division_slugs,
            'is_public_sector': is_public_sector,
        })
    return results


def fetch_state_locals(state: str) -> list[dict]:
    """Fetch and parse one state-filtered directory page."""
    url = STATE_PAGE.format(state=state.lower())
    r = http_get(url)
    return [dict(x, source_directory_url=url) for x in parse_state_page(r.text, state)]


def upsert_profile(cur, row: dict, permalink: Optional[str] = None) -> str:
    """Insert or update a web_union_profiles row.
    Returns 'inserted' or 'updated'."""
    cur.execute(
        """SELECT id FROM web_union_profiles
           WHERE parent_union = %s AND local_number = %s AND state = %s""",
        (PARENT_UNION, row['local_number'], row['state']),
    )
    existing = cur.fetchone()

    extra = {
        'wp_permalink': permalink,
        'divisions': row.get('divisions', []),
        'is_public_sector': row.get('is_public_sector', False),
        'city': row.get('city'),
        'postal_code': row.get('postal'),
    }
    # Remove None values for cleanliness
    extra = {k: v for k, v in extra.items() if v not in (None, [])}

    scrape_status = 'DIRECTORY_ONLY'  # not yet deep-scraped, but directory row captured

    if existing:
        cur.execute(
            """UPDATE web_union_profiles SET
                   union_name = %s,
                   website_url = COALESCE(%s, website_url),
                   officers = COALESCE(%s, officers),
                   address = COALESCE(%s, address),
                   phone = COALESCE(%s, phone),
                   email = COALESCE(%s, email),
                   source_directory_url = %s,
                   extra_data = COALESCE(extra_data, '{}'::jsonb) || %s::jsonb,
                   scrape_status = CASE
                       WHEN scrape_status IN ('PENDING', 'NO_WEBSITE') THEN %s
                       ELSE scrape_status
                   END
               WHERE id = %s""",
            (
                row['title'],
                row['website_url'], row['officers'], row['address'],
                row['phone'], row['email'],
                row['source_directory_url'],
                json.dumps(extra),
                scrape_status,
                existing[0],
            ),
        )
        return 'updated'
    else:
        cur.execute(
            """INSERT INTO web_union_profiles
                   (union_name, local_number, parent_union, state, website_url,
                    scrape_status, source_directory_url, officers, address,
                    phone, email, extra_data)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (
                row['title'], row['local_number'], PARENT_UNION, row['state'],
                row['website_url'], scrape_status, row['source_directory_url'],
                row['officers'], row['address'], row['phone'], row['email'],
                json.dumps(extra),
            ),
        )
        return 'inserted'


def match_olms(conn) -> dict:
    """Match IBT web profiles to unions_master. Returns counts dict."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, local_number, state FROM web_union_profiles
           WHERE parent_union = %s AND local_number IS NOT NULL""",
        (PARENT_UNION,),
    )
    profiles = cur.fetchall()

    cur.execute(
        """SELECT f_num, local_number, state, members
           FROM unions_master WHERE aff_abbr = 'IBT' AND local_number IS NOT NULL"""
    )
    rows = cur.fetchall()
    by_key: dict[tuple, list] = {}
    by_local: dict[str, list] = {}
    for f_num, local, st, members in rows:
        k = (str(local).strip().upper(), (st or '').strip().upper())
        by_key.setdefault(k, []).append((f_num, members))
        by_local.setdefault(str(local).strip().upper(), []).append((f_num, st, members))

    matched = cross_state = unmatched = 0
    for pid, local, state in profiles:
        key = (str(local).strip().upper(), (state or '').strip().upper())
        cands = by_key.get(key, [])
        if cands:
            # Pick highest-members
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
               COUNT(*) FILTER (WHERE email IS NOT NULL) AS with_email,
               COUNT(*) FILTER (WHERE phone IS NOT NULL) AS with_phone,
               COUNT(*) FILTER (WHERE (extra_data->>'is_public_sector')::boolean) AS public_sector,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS') AS matched,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS_CROSS_STATE') AS cross_state,
               COUNT(*) FILTER (WHERE match_status = 'UNMATCHED') AS unmatched,
               COUNT(*) FILTER (WHERE match_status = 'PENDING_REVIEW') AS pending
           FROM web_union_profiles WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    r = cur.fetchone()
    print('--- IBT profile summary ---')
    keys = ['total', 'with_website', 'with_email', 'with_phone', 'public_sector',
            'matched', 'cross_state', 'unmatched', 'pending']
    for k, v in zip(keys, r):
        print(f'  {k:18s} {v}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state', help='Scrape a single state abbrev only (e.g. NY)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Fetch + parse but do not write to DB')
    ap.add_argument('--match-only', action='store_true',
                    help='Skip scraping; only (re-)run the OLMS match step')
    ap.add_argument('--skip-wp-api', action='store_true',
                    help='Skip the WP REST pre-fetch (use only state HTML pages)')
    args = ap.parse_args()

    conn = get_connection()

    if args.match_only:
        print('[MATCH] Running OLMS match only...')
        counts = match_olms(conn)
        print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')
        report(conn)
        conn.close()
        return 0

    # Step 1: enumerate all states we need to fetch
    if args.state:
        states = [args.state.upper()]
        print(f'[STEP 1] Single-state mode: {states[0]}')
    else:
        if args.skip_wp_api:
            # Hard-coded fallback state list (from the teamster.org dropdown)
            states = ['AL','AK','AR','AZ','CA','CO','CT','DC','DE','FL','GA','HI','IA','ID',
                      'IL','IN','KS','KY','LA','MA','MD','ME','MI','MN','MO','MS','MT','NC',
                      'ND','NE','NH','NJ','NM','NV','NY','OH','OK','OR','PA','PR','RI','SC',
                      'SD','TN','TX','UT','VA','VT','WA','WI','WV',
                      'AB','BC','MB','NL','NS','ON','QC','SK']
            print(f'[STEP 1] Skipping WP API, using {len(states)} hard-coded states')
        else:
            print('[STEP 1] Fetching WP REST API list of locals...')
            wp_locals = fetch_wp_local_list()
            state_set = sorted({x['state'] for x in wp_locals if x.get('state')})
            states = state_set
            print(f'[OK] {len(wp_locals)} locals via REST; {len(states)} distinct states')

    # Step 2: scrape state pages
    print(f'[STEP 2] Scraping {len(states)} state directory pages...')
    all_rows: list[dict] = []
    fetch_errors = []
    for i, st in enumerate(states, 1):
        try:
            rows = fetch_state_locals(st)
            all_rows.extend(rows)
            print(f'  [{i:2d}/{len(states)}] {st:3s}: {len(rows)} locals')
        except Exception as e:
            fetch_errors.append((st, str(e)))
            print(f'  [{i:2d}/{len(states)}] {st:3s}: ERROR {e}')
        time.sleep(RATE_LIMIT_SECS)

    print(f'[OK] Parsed {len(all_rows)} total local entries; {len(fetch_errors)} fetch errors')

    # Dedupe on (local_number, state) since border locals sometimes list in two states
    seen = set()
    deduped = []
    for row in all_rows:
        if not row.get('local_number'):
            # Skip anything we couldn't extract a number from
            continue
        key = (row['local_number'], row['state'])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    print(f'[OK] {len(deduped)} unique (local_number, state) rows after dedup')

    with_website = sum(1 for r in deduped if r.get('website_url'))
    public = sum(1 for r in deduped if r.get('is_public_sector'))
    print(f'       with_website={with_website}, public_sector_tagged={public}')

    if args.dry_run:
        print('[DRY RUN] First 3 rows:')
        for row in deduped[:3]:
            print(' ', {k: v for k, v in row.items() if k != 'divisions'})
            print('    divisions:', row.get('divisions'))
        conn.close()
        return 0

    # Step 3: upsert
    print('[STEP 3] Upserting into web_union_profiles...')
    cur = conn.cursor()
    inserted = updated = errored = 0
    for row in deduped:
        try:
            action = upsert_profile(cur, row)
            conn.commit()  # per-row commit -- a later row's failure cannot discard this one
            if action == 'inserted':
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f'  ERR upserting LU {row.get("local_number")}/{row.get("state")}: {e}')
            conn.rollback()  # rolls back only the failed row's statement
            errored += 1
            continue
    print(f'[OK] inserted={inserted} updated={updated} errored={errored}')

    # Step 4: match to OLMS
    print('[STEP 4] Matching IBT profiles to unions_master...')
    counts = match_olms(conn)
    print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')

    # Step 5: summary
    report(conn)

    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
