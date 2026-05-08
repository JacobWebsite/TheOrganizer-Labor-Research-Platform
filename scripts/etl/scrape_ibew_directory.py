"""
IBEW (International Brotherhood of Electrical Workers) Locals Directory Scraper
-------------------------------------------------------------------------------
The public `ibew.org/local-union-directory/` page is an iframe into
`https://www.ibewapp.org/ludSearch/lusStart.htm`, an ASP.NET SPA whose data
layer is a single .ashx endpoint:

    https://www.ibewapp.org/ludSearch/DataIO.ashx?action=...

Three actions power the whole directory:
  1. action=list-locals                         -> [{ID, LU}, ...]  (~764 rows)
  2. action=show-local-info&LocalUnionID=<ID>   -> detailed rows (address,
                                                    phone/fax, website, email,
                                                    officers, trade classes)
  3. action=list-locals-by-state&state=XX&filter=all (not needed here)

The detail feed returns rows with `tableName` discriminators:
  LocalUnion  ->  LU_SC|CharterCity|CharterState  AND  Website
  Addresses   ->  Address1           AND  City|State|Zip
  Phones      ->  PhoneNo            (Fax distinguished by "Fax" in rendered Line)
  Emails      ->  Email
  Members     ->  fname|mi|lname|suffix|pos|bs  (officers)
  TradeClasses->  comma list (catv, em, govt, i, lctt, mo, o, ptc, t, u)

Usage:
    py -u scripts/etl/scrape_ibew_directory.py --dry-run       # list only, 5-sample detail
    py -u scripts/etl/scrape_ibew_directory.py --limit 20       # first 20 locals
    py -u scripts/etl/scrape_ibew_directory.py                  # full 764-local run
    py -u scripts/etl/scrape_ibew_directory.py --match-only     # rematch OLMS
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


PARENT_UNION = 'IBEW'
BASE_URL = 'https://www.ibewapp.org/ludSearch/DataIO.ashx'
DIRECTORY_URL = 'https://ibew.org/local-union-directory/'
USER_AGENT = 'LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)'

FETCH_TIMEOUT = 30
FETCH_SLEEP_SEC = 0.1  # polite pacing between detail fetches


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({'User-Agent': USER_AGENT, 'Accept': 'application/json, text/plain, */*'})
    return s


def fetch_all_local_ids(s: requests.Session) -> list[dict]:
    """Return [{ID, LU}, ...] for every IBEW local."""
    r = s.get(BASE_URL, params={'action': 'list-locals'}, timeout=FETCH_TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_local_detail(s: requests.Session, local_id: str) -> list[dict]:
    """Return the show-local-info array for one local, or [] on error."""
    try:
        r = s.get(BASE_URL,
                  params={'action': 'show-local-info', 'LocalUnionID': str(local_id)},
                  timeout=FETCH_TIMEOUT)
        if r.status_code != 200:
            return []
        return r.json()
    except requests.RequestException:
        return []
    except ValueError:  # invalid JSON
        return []


def _clean_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip().strip('/')
    if not u or u.lower() in ('none', 'n/a', 'na', '-'):
        return None
    if not re.match(r'^https?://', u, re.IGNORECASE):
        u = 'http://' + u
    return u


def parse_local_detail(jdata: list[dict], local_number: str) -> dict:
    """Convert the show-local-info rows into a single profile row."""
    row = {
        'union_name': f'IBEW Local {local_number}',
        'local_number': local_number,
        'state': None,
        'city': None,
        'zip': None,
        'address': None,
        'address_line1': None,
        'phone': None,
        'fax': None,
        'email': None,
        'website_url': None,
        'officers': [],
        'trade_classes': None,
    }

    for item in jdata:
        tname = item.get('tableName') or ''
        efn = item.get('editFieldNames') or ''
        efv = item.get('editFieldValues') or ''
        line = item.get('Line') or ''

        if tname == 'LocalUnion' and 'LU_SC' in efn:
            # top row: "LU_SC|CharterCity|CharterState"
            parts = efv.split('|')
            if len(parts) >= 3:
                row['city'] = row['city'] or (parts[1].strip() or None)
                row['state'] = row['state'] or (parts[2].strip() or None)
        elif tname == 'LocalUnion' and 'Website' in efn:
            row['website_url'] = _clean_url(efv) or row['website_url']
        elif tname == 'TradeClasses':
            row['trade_classes'] = efv.strip() or None
        elif tname == 'Addresses' and 'Address1' in efn:
            row['address_line1'] = efv.strip() or row['address_line1']
        elif tname == 'Addresses' and 'City' in efn:
            # "City|State|Zip"
            parts = efv.split('|')
            if len(parts) >= 3:
                row['city'] = parts[0].strip() or row['city']
                # Some rows use [State] wrapper which editFieldNames shows; value is plain
                row['state'] = parts[1].strip() or row['state']
                row['zip'] = parts[2].strip() or row['zip']
        elif tname == 'Phones':
            phone = efv.strip()
            if not phone:
                continue
            if 'Fax' in line:
                if not row['fax']:
                    row['fax'] = phone
            else:
                if not row['phone']:
                    row['phone'] = phone
        elif tname == 'Emails':
            if not row['email']:
                row['email'] = efv.strip() or None
        elif tname == 'Members':
            # editFieldValues: fname|mi|lname|suffix|pos|bs
            parts = efv.split('|')
            if len(parts) >= 3:
                fname = parts[0].strip()
                mi = parts[1].strip()
                lname = parts[2].strip()
                suffix = parts[3].strip() if len(parts) > 3 else ''
                pos = parts[4].strip() if len(parts) > 4 else ''
                full = ' '.join(x for x in [fname, mi, lname] if x)
                if suffix:
                    full += f', {suffix}'
                # Position is a JSON-ish blob sometimes e.g. {"M":"B.M."} — try to extract
                pos_label = None
                if pos:
                    try:
                        obj = json.loads(pos)
                        if isinstance(obj, dict) and obj:
                            pos_label = list(obj.values())[0]
                    except (json.JSONDecodeError, TypeError):
                        pos_label = pos
                entry = f"{full} ({pos_label})" if pos_label else full
                row['officers'].append(entry)

    # Compose full address
    addr_parts = []
    if row['address_line1']:
        addr_parts.append(row['address_line1'])
    if row['city'] or row['state'] or row['zip']:
        tail_parts = []
        if row['city']:
            tail_parts.append(row['city'])
        if row['state']:
            tail_parts.append(row['state'])
        if row['zip']:
            tail_parts.append(row['zip'])
        addr_parts.append(', '.join(tail_parts))
    if addr_parts:
        row['address'] = ', '.join(addr_parts)

    return row


def upsert_profile(cur, row: dict) -> str:
    """Insert-or-update one IBEW profile. Keys on (parent, local_number, state)."""
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
               WHERE parent_union = %s AND local_number IS NULL
                 AND union_name = %s AND state = %s""",
            (PARENT_UNION, row['union_name'], row['state']),
        )
    existing = cur.fetchone()

    scrape_status = 'DIRECTORY_ONLY'
    source_url = DIRECTORY_URL
    officers_text = '\n'.join(row['officers']) if row['officers'] else None
    extra = {
        'source': 'ibew_dataio_ashx',
        'trade_classes': row['trade_classes'],
        'city': row['city'],
        'zip': row['zip'],
        'officer_count': len(row['officers']),
    }

    if existing:
        cur.execute(
            """UPDATE web_union_profiles SET
                   union_name = %s,
                   website_url = COALESCE(%s, website_url),
                   address = COALESCE(%s, address),
                   phone = COALESCE(%s, phone),
                   fax = COALESCE(%s, fax),
                   email = COALESCE(%s, email),
                   officers = COALESCE(%s, officers),
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
                row['phone'], row['fax'], row['email'],
                officers_text,
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
                scrape_status, source_directory_url, address, phone, fax, email,
                officers, extra_data)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
        (
            row['union_name'], row['local_number'], PARENT_UNION, row['state'],
            row['website_url'], scrape_status, source_url,
            row['address'], row['phone'], row['fax'], row['email'],
            officers_text,
            json.dumps(extra),
        ),
    )
    return 'inserted'


def match_olms(conn) -> dict:
    """Match IBEW web profiles to unions_master."""
    cur = conn.cursor()
    cur.execute(
        """SELECT id, local_number, state FROM web_union_profiles
           WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    profiles = cur.fetchall()

    cur.execute(
        """SELECT f_num, local_number, state, members
           FROM unions_master WHERE aff_abbr = 'IBEW'"""
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
               COUNT(*) FILTER (WHERE officers IS NOT NULL) AS with_officers,
               COUNT(*) FILTER (WHERE local_number IS NOT NULL) AS with_local_num,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS') AS matched,
               COUNT(*) FILTER (WHERE match_status = 'MATCHED_OLMS_CROSS_STATE') AS cross_state,
               COUNT(*) FILTER (WHERE match_status = 'UNMATCHED') AS unmatched
           FROM web_union_profiles WHERE parent_union = %s""",
        (PARENT_UNION,),
    )
    r = cur.fetchone()
    print('--- IBEW profile summary ---')
    keys = ['total', 'with_website', 'with_phone', 'with_officers', 'with_local_num',
            'matched', 'cross_state', 'unmatched']
    for k, v in zip(keys, r):
        print(f'  {k:16s} {v}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='List + 5-detail sample; no DB')
    ap.add_argument('--match-only', action='store_true', help='Skip fetch; just rematch')
    ap.add_argument('--limit', type=int, help='Fetch only first N locals (debug)')
    args = ap.parse_args()

    conn = get_connection()

    if args.match_only:
        print('[MATCH] Running OLMS match only...')
        counts = match_olms(conn)
        print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')
        report(conn)
        conn.close()
        return 0

    s = make_session()

    print('[STEP 1] Fetching IBEW local list from DataIO.ashx...')
    id_list = fetch_all_local_ids(s)
    print(f'[OK] {len(id_list)} locals listed')

    if args.limit:
        id_list = id_list[:args.limit]
        print(f'  [LIMIT] truncated to {len(id_list)} locals')

    sample_count = 5 if args.dry_run and not args.limit else len(id_list)
    fetch_list = id_list[:sample_count]

    print(f'[STEP 2] Fetching detail for {len(fetch_list)} locals ({FETCH_SLEEP_SEC}s pacing)...')
    rows: list[dict] = []
    t0 = time.time()
    for idx, item in enumerate(fetch_list):
        local_id = item['ID']
        local_number = item['LU']
        detail = fetch_local_detail(s, local_id)
        if not detail:
            print(f'  [WARN] empty detail for ID={local_id} LU={local_number}')
            continue
        row = parse_local_detail(detail, local_number)
        rows.append(row)
        if (idx + 1) % 50 == 0:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed if elapsed > 0 else 0
            print(f'  [PROGRESS] {idx+1}/{len(fetch_list)} ({rate:.1f}/s, {elapsed:.0f}s elapsed)')
        time.sleep(FETCH_SLEEP_SEC)

    print(f'[OK] {len(rows)} rows assembled in {time.time()-t0:.1f}s')
    with_state = sum(1 for r in rows if r['state'])
    with_web = sum(1 for r in rows if r['website_url'])
    with_phone = sum(1 for r in rows if r['phone'])
    with_officers = sum(1 for r in rows if r['officers'])
    print(f'[PARSE] with_state={with_state} with_website={with_web} '
          f'with_phone={with_phone} with_officers={with_officers}')

    if args.dry_run:
        print('[DRY RUN] Sample rows:')
        for r in rows[:5]:
            summary = {k: r[k] for k in ['union_name', 'local_number', 'state', 'city',
                                          'website_url', 'phone', 'email']}
            summary['officer_count'] = len(r['officers'])
            summary['address'] = r['address']
            print(' ', summary)
        conn.close()
        return 0

    print('[STEP 3] Upserting into web_union_profiles...')
    cur = conn.cursor()
    inserted = updated = errored = skipped = 0
    for row in rows:
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

    print('[STEP 4] Matching IBEW profiles to unions_master...')
    counts = match_olms(conn)
    print(f'[OK] matched={counts["matched"]} cross_state={counts["cross_state_matched"]} unmatched={counts["unmatched"]}')

    report(conn)
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
