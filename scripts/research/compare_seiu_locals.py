import os
from db_config import get_connection
"""
SEIU Locals Comparison Script
Fetches SEIU's official list of locals from their API and compares to OLMS database.
"""

import requests
import xml.etree.ElementTree as ET
import psycopg2
import re
from collections import defaultdict


def extract_local_number(name):
    """Extract local number from union name string."""
    if not name:
        return None

    # Common patterns: "SEIU Local 721", "Local 1", "SEIU 32BJ", etc.
    patterns = [
        r'Local\s*(\d+[A-Z]*)',      # Local 721, Local 32BJ
        r'SEIU\s+(\d+[A-Z]*)\b',     # SEIU 32BJ (not followed by more)
        r'#\s*(\d+)',                 # #721
        r'\bLocal\s*(\d+)',          # Just Local followed by number
        r'(\d{3,}[A-Z]*)\b',         # 3+ digit numbers (like 1199)
    ]

    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            result = match.group(1).upper().lstrip('0')
            # Filter out single digits that might be false positives
            if result and (len(result) > 1 or result.isalpha()):
                return result
            elif result:
                return result

    return None


def fetch_seiu_api():
    """Fetch SEIU locals from their official API."""
    url = 'https://api.seiu.org/directory/api/full/hq/'
    print(f"Fetching SEIU API: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching SEIU API: {e}")
        return []

    root = ET.fromstring(response.content)

    seiu_official = []
    for local in root.findall('.//local'):
        crmid = local.find('crmid')
        name = local.find('name')
        city = local.find('city')
        state = local.find('state')
        country = local.find('country')

        name_text = name.text if name is not None else ''
        local_data = {
            'crmid': crmid.text if crmid is not None else None,
            'name': name_text,
            'city': city.text if city is not None else '',
            'state': state.text if state is not None else '',
            'country': country.text if country is not None else '',
            'local_number': extract_local_number(name_text)
        }
        seiu_official.append(local_data)

    return seiu_official


def fetch_olms_seiu_locals(include_workers_united=True):
    """Fetch SEIU locals from OLMS database.

    Args:
        include_workers_united: If True, also include Workers United (WU) affiliates
    """
    conn = get_connection()

    if include_workers_united:
        aff_filter = "aff_abbr IN ('SEIU', 'WU')"
    else:
        aff_filter = "aff_abbr = 'SEIU'"

    query = f"""
        SELECT f_num, union_name, desig_name, local_number,
               city, state, members, aff_abbr
        FROM unions_master
        WHERE {aff_filter}
        ORDER BY COALESCE(members, 0) DESC;
    """

    cursor = conn.cursor()
    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description]

    olms_locals = []
    for row in cursor.fetchall():
        local_data = dict(zip(columns, row))
        # Get effective local number - skip '0' and empty values
        raw_local = local_data.get('local_number')
        if raw_local and raw_local != '0' and raw_local.strip():
            local_data['effective_local_number'] = raw_local.strip().lstrip('0')
        else:
            # Try to extract from name
            local_data['effective_local_number'] = extract_local_number(local_data['union_name'])
        olms_locals.append(local_data)

    cursor.close()
    conn.close()

    return olms_locals


def get_olms_stats(olms_locals):
    """Get breakdown of OLMS locals by affiliation."""
    stats = {}
    for local in olms_locals:
        aff = local.get('aff_abbr', 'SEIU')
        if aff not in stats:
            stats[aff] = {'count': 0, 'members': 0}
        stats[aff]['count'] += 1
        stats[aff]['members'] += local.get('members') or 0
    return stats


def normalize_local_number(num):
    """Normalize local number for comparison."""
    if not num:
        return None
    num_str = str(num).upper().strip().lstrip('0')
    if not num_str:
        return None
    return num_str


def get_base_local_number(num):
    """Get base number without letter suffixes for fuzzy matching.
    E.g., '32BJ' -> '32', '121RN' -> '121'
    """
    if not num:
        return None
    # Extract leading digits
    match = re.match(r'^(\d+)', str(num))
    if match:
        return match.group(1).lstrip('0')
    return None


def compare_locals(seiu_official, olms_locals):
    """Compare SEIU official list with OLMS database."""

    # Build lookup dictionaries
    seiu_by_number = {}
    for local in seiu_official:
        num = normalize_local_number(local['local_number'])
        if num:
            if num not in seiu_by_number:
                seiu_by_number[num] = []
            seiu_by_number[num].append(local)

    olms_by_number = {}
    for local in olms_locals:
        num = normalize_local_number(local.get('effective_local_number'))
        if num:
            if num not in olms_by_number:
                olms_by_number[num] = []
            olms_by_number[num].append(local)

    # Find matches
    matched = []
    matched_seiu_crmids = set()
    matched_olms_fnums = set()

    # Match by local number (exact)
    for num in seiu_by_number:
        if num in olms_by_number:
            seiu_list = seiu_by_number[num]
            olms_list = olms_by_number[num]

            # Match each SEIU local to the best OLMS match
            for seiu_local in seiu_list:
                # Take the OLMS with most members
                best_olms = max(olms_list, key=lambda x: x.get('members') or 0)
                matched.append({
                    'seiu': seiu_local,
                    'olms': best_olms,
                    'local_number': num,
                    'match_type': 'exact'
                })
                matched_seiu_crmids.add(seiu_local['crmid'])
                matched_olms_fnums.add(best_olms['f_num'])

    # Second pass: fuzzy match with suffix stripping (e.g., 32BJ -> 32)
    for local in seiu_official:
        if local['crmid'] in matched_seiu_crmids:
            continue
        num = local.get('local_number')
        if not num:
            continue
        base_num = get_base_local_number(num)
        if base_num and base_num in olms_by_number:
            olms_list = [o for o in olms_by_number[base_num] if o['f_num'] not in matched_olms_fnums]
            if olms_list:
                best_olms = max(olms_list, key=lambda x: x.get('members') or 0)
                matched.append({
                    'seiu': local,
                    'olms': best_olms,
                    'local_number': f"{num} -> {base_num}",
                    'match_type': 'fuzzy'
                })
                matched_seiu_crmids.add(local['crmid'])
                matched_olms_fnums.add(best_olms['f_num'])

    # Unmatched
    seiu_only = [l for l in seiu_official if l['crmid'] not in matched_seiu_crmids]
    olms_only = [l for l in olms_locals if l['f_num'] not in matched_olms_fnums]

    return matched, seiu_only, olms_only


def categorize_seiu_unmatched(seiu_only):
    """Categorize unmatched SEIU locals."""
    categories = {
        'canadian': [],
        'workers_united': [],
        'state_associations': [],
        'healthcare_divisions': [],
        'special_units': [],
        'no_local_number': [],
        'other': []
    }

    for local in seiu_only:
        name = local['name'].lower()

        if 'canada' in name or local.get('country', '').upper() in ('CA', 'CANADA'):
            categories['canadian'].append(local)
        elif 'workers united' in name or 'wu conf' in name or 'joint board' in name:
            categories['workers_united'].append(local)
        elif any(x in name for x in ['state employees', 'public employees', 'association', 'seanc']):
            categories['state_associations'].append(local)
        elif any(x in name for x in ['healthcare', '1199', 'nurse']):
            categories['healthcare_divisions'].append(local)
        elif any(x in name for x in ['international', 'committee', 'council', 'forum', 'federation']):
            categories['special_units'].append(local)
        elif not local.get('local_number'):
            categories['no_local_number'].append(local)
        else:
            categories['other'].append(local)

    return categories


def print_report(seiu_official, olms_locals, matched, seiu_only, olms_only):
    """Print comparison report."""

    print("\n" + "="*80)
    print("SEIU LOCALS COMPARISON REPORT (including Workers United)")
    print("="*80)

    # Get OLMS breakdown
    olms_stats = get_olms_stats(olms_locals)

    print(f"\n{'Source':<35} {'Locals':>10} {'Members':>15}")
    print("-"*62)
    print(f"{'SEIU Official API':<35} {len(seiu_official):>10} {'(not provided)':>15}")
    print(f"{'OLMS Database (combined)':<35} {len(olms_locals):>10} {sum(l.get('members') or 0 for l in olms_locals):>15,}")
    for aff, stats in sorted(olms_stats.items()):
        print(f"{'  - ' + aff:<35} {stats['count']:>10} {stats['members']:>15,}")

    print(f"\n{'Comparison Results':<35} {'Count':>10}")
    print("-"*47)
    print(f"{'Matched':<35} {len(matched):>10}")
    print(f"{'SEIU Only (not in OLMS)':<35} {len(seiu_only):>10}")
    print(f"{'OLMS Only (not in SEIU list)':<35} {len(olms_only):>10}")

    # Matched locals
    print("\n" + "-"*80)
    print("MATCHED LOCALS (top 25 by membership)")
    print("-"*80)

    matched_sorted = sorted(matched, key=lambda x: x['olms'].get('members') or 0, reverse=True)
    for m in matched_sorted[:25]:
        seiu = m['seiu']
        olms = m['olms']
        members = olms.get('members') or 0
        aff = olms.get('aff_abbr', 'SEIU')
        aff_tag = f"[{aff}]" if aff != 'SEIU' else ""
        print(f"  Local {m['local_number']:<8} {seiu['name'][:32]:<32} -> {olms['f_num']} {aff_tag} ({members:,} members)")

    if len(matched) > 25:
        print(f"  ... and {len(matched) - 25} more matched locals")

    # Show match breakdown by affiliation
    match_by_aff = {}
    for m in matched:
        aff = m['olms'].get('aff_abbr', 'SEIU')
        if aff not in match_by_aff:
            match_by_aff[aff] = {'count': 0, 'members': 0}
        match_by_aff[aff]['count'] += 1
        match_by_aff[aff]['members'] += m['olms'].get('members') or 0

    print(f"\n  Match breakdown by OLMS affiliation:")
    for aff, stats in sorted(match_by_aff.items()):
        print(f"    {aff}: {stats['count']} locals, {stats['members']:,} members")

    # SEIU Only - categorized
    print("\n" + "-"*80)
    print("IN SEIU OFFICIAL LIST ONLY (not found in OLMS) - CATEGORIZED")
    print("-"*80)

    categories = categorize_seiu_unmatched(seiu_only)

    for cat_name, cat_locals in categories.items():
        if cat_locals:
            display_name = cat_name.replace('_', ' ').title()
            print(f"\n  {display_name} ({len(cat_locals)}):")
            for local in cat_locals:
                num = local.get('local_number', '')
                num_str = f"[{num}]" if num else ""
                print(f"    - {local['name']:<50} {num_str}")

    # OLMS Only
    print("\n" + "-"*80)
    print("IN OLMS ONLY (not in SEIU official list)")
    print("-"*80)

    olms_only_sorted = sorted(olms_only, key=lambda x: x.get('members') or 0, reverse=True)

    # Categorize OLMS-only
    with_local_num = [l for l in olms_only_sorted if l.get('effective_local_number')]
    without_local_num = [l for l in olms_only_sorted if not l.get('effective_local_number')]

    # Show breakdown by affiliation first
    olms_only_by_aff = {}
    for local in olms_only:
        aff = local.get('aff_abbr', 'SEIU')
        if aff not in olms_only_by_aff:
            olms_only_by_aff[aff] = []
        olms_only_by_aff[aff].append(local)

    print(f"\n  By affiliation:")
    for aff in sorted(olms_only_by_aff.keys()):
        locals_list = olms_only_by_aff[aff]
        members = sum(l.get('members') or 0 for l in locals_list)
        print(f"    {aff}: {len(locals_list)} locals, {members:,} members")

    if with_local_num:
        print(f"\n  With local numbers ({len(with_local_num)}) - may need matching:")
        for local in with_local_num[:20]:
            members = local.get('members') or 0
            num = local.get('effective_local_number', '?')
            aff = local.get('aff_abbr', 'SEIU')
            print(f"    - {local['f_num']}: Local {num:<8} [{aff}] ({local.get('state', '?')}) {members:>10,} members")
        if len(with_local_num) > 20:
            print(f"    ... and {len(with_local_num) - 20} more")

    if without_local_num:
        print(f"\n  Without local numbers ({len(without_local_num)}) - likely regional/state bodies:")
        for local in without_local_num[:15]:
            members = local.get('members') or 0
            aff = local.get('aff_abbr', 'SEIU')
            desig = local.get('desig_name', '')[:25] if local.get('desig_name') else ''
            print(f"    - {local['f_num']}: {local['union_name'][:30]:<30} [{aff}] [{desig}] ({members:>10,} members)")
        if len(without_local_num) > 15:
            print(f"    ... and {len(without_local_num) - 15} more")

    # Summary statistics
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    total_matched_members = sum(m['olms'].get('members') or 0 for m in matched)
    total_olms_only_members = sum(l.get('members') or 0 for l in olms_only)
    total_olms_members = sum(l.get('members') or 0 for l in olms_locals)

    olms_stats = get_olms_stats(olms_locals)

    print(f"\n  Total OLMS locals: {len(olms_locals):,}")
    for aff, stats in sorted(olms_stats.items()):
        print(f"    - {aff}: {stats['count']} locals, {stats['members']:,} members")

    print(f"\n  Total OLMS members: {total_olms_members:,}")
    print(f"  Members in matched locals: {total_matched_members:,} ({100*total_matched_members/total_olms_members:.1f}%)")
    print(f"  Members in OLMS-only locals: {total_olms_only_members:,} ({100*total_olms_only_members/total_olms_members:.1f}%)")

    match_rate = 100 * len(matched) / len(seiu_official) if seiu_official else 0
    print(f"\n  Match rate (SEIU official -> OLMS): {match_rate:.1f}%")

    # Explain unmatched categories
    print("\n  Analysis of unmatched SEIU locals:")
    categories = categorize_seiu_unmatched(seiu_only)
    for cat_name, cat_locals in categories.items():
        if cat_locals:
            display_name = cat_name.replace('_', ' ').title()
            print(f"    - {display_name}: {len(cat_locals)}")

    # Count WU matches
    wu_matches = sum(1 for m in matched if m['olms'].get('aff_abbr') == 'WU')

    print("\n  Notes:")
    if categories['canadian']:
        print(f"    * {len(categories['canadian'])} Canadian locals expected missing (OLMS is US-only)")
    if categories['workers_united']:
        print(f"    * {len(categories['workers_united'])} Workers United entries unmatched (mostly Joint Boards/conferences)")
        if wu_matches:
            print(f"    * {wu_matches} SEIU API entries matched to WU affiliation in OLMS")
    if categories['state_associations']:
        print(f"    * {len(categories['state_associations'])} state associations may be independent or merged")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Compare SEIU official locals with OLMS database')
    parser.add_argument('--no-wu', action='store_true', help='Exclude Workers United from OLMS query')
    args = parser.parse_args()

    include_wu = not args.no_wu

    print("Fetching SEIU official locals from API...")
    seiu_official = fetch_seiu_api()
    print(f"  Retrieved {len(seiu_official)} locals from SEIU API")

    print(f"\nFetching SEIU locals from OLMS database (include Workers United: {include_wu})...")
    olms_locals = fetch_olms_seiu_locals(include_workers_united=include_wu)

    olms_stats = get_olms_stats(olms_locals)
    print(f"  Retrieved {len(olms_locals)} locals from OLMS:")
    for aff, stats in sorted(olms_stats.items()):
        print(f"    - {aff}: {stats['count']} locals, {stats['members']:,} members")

    print("\nComparing data sources...")
    matched, seiu_only, olms_only = compare_locals(seiu_official, olms_locals)

    print_report(seiu_official, olms_locals, matched, seiu_only, olms_only)


if __name__ == '__main__':
    main()
