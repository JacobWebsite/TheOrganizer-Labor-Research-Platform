"""
SEIU Locals Directory Scraper
-----------------------------
SEIU publishes a clean XML feed of every local union + branch office at:
    https://www.seiu.org/wp-content/uploads/2026/01/localscrmdata.xml

320 total markers resolve to 138 unique locals (by crmid). Locals with multiple
offices (e.g., SEIU 32BJ has 15 branches across NY/CT/MD/VA/FL/etc.) are
collapsed to one row per local, with branches stored as a list in extra_data.

Each local gets:
  union_name, local_number (extracted from name), parent_union='SEIU',
  state, website_url, phone, email (rare), address, facebook/twitter.
  OLMS matched on (aff_abbr='SEIU', local_number, state) with cross-state
  fallback.

Usage:
    py -u scripts/etl/scrape_seiu_directory.py --dry-run     # preview first 5 rows
    py -u scripts/etl/scrape_seiu_directory.py               # full run + OLMS match
    py -u scripts/etl/scrape_seiu_directory.py --match-only  # skip fetch, just rematch
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional

import requests
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


PARENT_UNION = 'SEIU'
XML_URL = 'https://www.seiu.org/wp-content/uploads/2026/01/localscrmdata.xml'
USER_AGENT = 'LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)'

# Extracts the local number from name strings like:
#   'SEIU Local 1'            -> '1'
#   'SEIU Local 32BJ'         -> '32BJ'
#   'SEIU Local 2.on'         -> '2'         (drop .on -- Canadian suffix)
#   'SEIU F&O Local 8'        -> '8'
#   'Doctors Council SEIU, Local 10MD' -> '10MD'
#   'Window Cleaners Union Local 16'   -> '16'
LOCAL_NUMBER_RE = re.compile(r'\bLocal\s+#?(\d+[A-Za-z\-]*)', re.IGNORECASE)


def fetch_xml() -> str:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/xml,text/xml'}
    r = requests.get(XML_URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def parse_local_number(name: str) -> Optional[str]:
    if not name:
        return None
    m = LOCAL_NUMBER_RE.search(name)
    if not m:
        return None
    num = m.group(1).upper()
    # Drop trailing dot-suffix like '.on' (Canadian)
    num = re.sub(r'\.[A-Z]+$', '', num)
    return num


def parse_xml_to_locals(xml_text: str) -> list[dict]:
    """Parse the SEIU XML and collapse multi-location locals into one record each.

    Returns one dict per unique crmid. HEADQUARTERS marker wins when present;
    otherwise the first marker. Other markers become branches in extra_data.
    """
    root = ET.fromstring(xml_text)
    markers = root.findall('.//marker')

    # Group by crmid
    by_crmid: dict[str, list[ET.Element]] = {}
    for m in markers:
        crmid = (m.findtext('crmid') or '').strip()
        if not crmid:
            continue
        by_crmid.setdefault(crmid, []).append(m)

    def text(el: ET.Element, tag: str) -> Optional[str]:
        t = el.findtext(tag)
        if t is None:
            return None
        t = t.strip()
        return t or None

    out = []
    for crmid, group in by_crmid.items():
        # Choose canonical marker: prefer HEADQUARTERS, else first
        hq = next((m for m in group if (text(m, 'addresstype') or '').upper() == 'HEADQUARTERS'), None)
        canonical = hq if hq is not None else group[0]

        name = text(canonical, 'name') or ''
        local_num = parse_local_number(name)
        local_type = text(canonical, 'type') or ''
        url = text(canonical, 'url')
        if url and not url.startswith(('http://', 'https://')):
            url = 'https://' + url.lstrip('/')

        # Branches: all non-canonical markers, captured compactly
        branches = []
        for m in group:
            if m is canonical:
                continue
            branches.append({
                'addresstype': text(m, 'addresstype'),
                'address': text(m, 'address'),
                'city': text(m, 'city'),
                'state': text(m, 'state'),
                'zip': text(m, 'zip'),
                'phone': text(m, 'phone'),
            })

        extra = {
            'seiu_crmid': crmid,
            'seiu_type': local_type,  # 'Local Union' | 'State Council' | 'Sub-Local'
            'division': text(canonical, 'division'),
            'city': text(canonical, 'city'),
            'postal_code': text(canonical, 'zip'),
            'lat': text(canonical, 'lat'),
            'lng': text(canonical, 'lng'),
            'facebook': text(canonical, 'facebook'),
            'twitter': text(canonical, 'twitter'),
            'branches': branches,
            'n_branches': len(branches),
        }
        extra = {k: v for k, v in extra.items() if v not in (None, '', [])}

        out.append({
            'crmid': crmid,
            'union_name': name,
            'local_number': local_num,
            'state': text(canonical, 'state'),
            'website_url': url,
            'phone': text(canonical, 'phone'),
            'email': None,  # XML does not expose email
            'address': text(canonical, 'address'),
            'local_type': local_type,
            'extra': extra,
        })
    return out


def upsert_profile(cur, row: dict) -> str:
    """Insert-or-update one SEIU profile. Returns 'inserted' or 'updated'."""
    cur.execute(
        """SELECT id FROM web_union_profiles
           WHERE parent_union = %s AND local_number = %s AND state = %s""",
        (PARENT_UNION, row['local_number'], row['state']),
    )
    existing = cur.fetchone()

    scrape_status = 'DIRECTORY_ONLY'
    source_url = XML_URL

    if existing:
        cur.execute(
            """UPDATE web_union_profiles SET
                   union_name = %s,
                   website_url = COALESCE(%s, website_url),
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
                row['union_name'],
                row['website_url'], row['address'],
                row['phone'], row['email'],
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
                scrape_status, source_directory_url, address, phone, email, extra_data)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (
            row['union_name'], row['local_number'], PARENT_UNION, row['state'],
            row['website_url'], scrape_status, source_url,
            row['address'], row['phone'], row['email'],
            json.dumps(row['extra']),
        ),
    )
    return 'inserted'


def match_olms(conn) -> dict:
    """Match SEIU web profiles to unions_master by (aff_abbr='SEIU', local_number, state).
    Falls back to cross-state when local_number alone is unique."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, local_number, state FROM web_union_profiles
           WHERE parent_union = %s AND local_number IS NOT NULL""",
        (PARENT_UNION,),
    )
    profiles = cur.fetchall()

    cur.execute(
        """SELECT f_num, local_number, state, members
           FROM unions_master WHERE aff_abbr = 'SEIU' AND local_number IS NOT NULL"""
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
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS') AS matched,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS_CROSS_STATE') AS cross_state,
               COUNT(*) FILTER (WHERE match_status = 'UNMATCHED') AS unmatched,
               COUNT(*) FILTER (WHERE (extra_data->>'seiu_type') = 'State Council') AS state_councils
           FROM web_union_profiles WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    r = cur.fetchone()
    print('--- SEIU profile summary ---')
    keys = ['total', 'with_website', 'with_phone', 'matched', 'cross_state',
            'unmatched', 'state_councils']
    for k, v in zip(keys, r):
        print(f'  {k:16s} {v}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true',
                    help='Fetch + parse but do not write to DB')
    ap.add_argument('--match-only', action='store_true',
                    help='Skip fetch; just (re-)run OLMS match step')
    args = ap.parse_args()

    conn = get_connection()

    if args.match_only:
        print('[MATCH] Running OLMS match only...')
        counts = match_olms(conn)
        print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')
        report(conn)
        conn.close()
        return 0

    print(f'[STEP 1] Fetching {XML_URL}')
    xml = fetch_xml()
    print(f'[OK] {len(xml):,} bytes')

    print('[STEP 2] Parsing XML into canonical local records...')
    records = parse_xml_to_locals(xml)
    print(f'[OK] {len(records)} unique locals')

    with_website = sum(1 for r in records if r['website_url'])
    with_phone = sum(1 for r in records if r['phone'])
    with_local_num = sum(1 for r in records if r['local_number'])
    councils = sum(1 for r in records if r['local_type'] == 'State Council')
    print(f'       with_website={with_website}  with_phone={with_phone}  with_local_number={with_local_num}  state_councils={councils}')

    if args.dry_run:
        print('[DRY RUN] First 5 records:')
        for r in records[:5]:
            compact = {k: v for k, v in r.items() if k != 'extra'}
            print(' ', compact)
            print('    extra:', {k: v for k, v in r['extra'].items() if k != 'branches'},
                  f'n_branches={len(r["extra"].get("branches", []))}')
        conn.close()
        return 0

    print('[STEP 3] Upserting into web_union_profiles...')
    cur = conn.cursor()
    inserted = updated = errored = skipped_no_local_num = 0
    for row in records:
        if not row['local_number']:
            # State Councils + Canadian generic entries -- skip, we can't key them safely.
            # TODO: future phase, create separate storage for these.
            skipped_no_local_num += 1
            continue
        try:
            action = upsert_profile(cur, row)
            conn.commit()
            if action == 'inserted':
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            print(f'  ERR upserting SEIU Local {row.get("local_number")}/{row.get("state")}: {e}')
            conn.rollback()
            errored += 1
            continue
    print(f'[OK] inserted={inserted} updated={updated} errored={errored} skipped_no_local_num={skipped_no_local_num}')

    print('[STEP 4] Matching SEIU profiles to unions_master...')
    counts = match_olms(conn)
    print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')

    report(conn)
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
