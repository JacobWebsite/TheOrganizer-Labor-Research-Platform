"""
Checkpoint 3: AI Extraction Helper
- Reads raw text for a profile and prints it for Claude Code analysis
- Accepts structured JSON and writes to correct tables
- Can run in batch mode with auto-extraction heuristics

Usage:
    py scripts/scraper/extract_union_data.py --read 42          # print raw text for profile 42
    py scripts/scraper/extract_union_data.py --read-batch 10    # print summaries for next 10
    py scripts/scraper/extract_union_data.py --insert data.json # insert extracted data
    py scripts/scraper/extract_union_data.py --auto-extract     # run heuristic extraction on all FETCHED
"""
import sys
import os
import json
import re
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ── Read helpers ──────────────────────────────────────────────────────────

def read_profile(conn, profile_id):
    """Read and print raw text for a single profile."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, union_name, local_number, state, website_url, platform,
               f_num, match_status, scrape_status,
               raw_text, raw_text_about, raw_text_contracts, raw_text_news,
               officers, address, phone, email
        FROM web_union_profiles
        WHERE id = %s
    """, (profile_id,))
    row = cur.fetchone()
    if not row:
        print(f"Profile {profile_id} not found")
        return

    cols = ['id', 'union_name', 'local_number', 'state', 'website_url', 'platform',
            'f_num', 'match_status', 'scrape_status',
            'raw_text', 'raw_text_about', 'raw_text_contracts', 'raw_text_news',
            'officers', 'address', 'phone', 'email']
    p = dict(zip(cols, row))

    print(f"{'='*70}")
    print(f"[{p['id']}] {p['union_name']} ({p['state']})")
    print(f"URL: {p['website_url']}  Platform: {p['platform']}")
    print(f"OLMS: f_num={p['f_num']}  match={p['match_status']}")
    print(f"Directory: officers={p['officers']}")
    print(f"           address={p['address']}")
    print(f"           phone={p['phone']}  email={p['email']}")
    print(f"{'='*70}")

    for field, label in [('raw_text', 'HOMEPAGE'),
                         ('raw_text_about', 'ABOUT PAGE'),
                         ('raw_text_contracts', 'CONTRACTS PAGE'),
                         ('raw_text_news', 'NEWS PAGE')]:
        text = p[field]
        if text and len(text.strip()) > 100:
            print(f"\n--- {label} ({len(text):,} chars) ---")
            print(text[:3000])
            if len(text) > 3000:
                print(f"\n... [{len(text) - 3000:,} more chars] ...")
        else:
            print(f"\n--- {label}: (empty/stub) ---")


def read_batch(conn, limit=10):
    """Print summaries for next batch of FETCHED profiles."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, union_name, local_number, state, website_url, platform,
               f_num, match_status,
               LENGTH(raw_text) as home_len,
               LENGTH(raw_text_about) as about_len,
               LENGTH(raw_text_contracts) as contr_len,
               LENGTH(raw_text_news) as news_len
        FROM web_union_profiles
        WHERE scrape_status = 'FETCHED'
        ORDER BY id
        LIMIT %s
    """, (limit,))

    rows = cur.fetchall()
    print(f"Next {len(rows)} profiles ready for extraction:\n")
    for row in rows:
        pid, name, local, st, url, plat, fnum, match, hl, al, cl, nl = row
        print(f"  [{pid}] {name[:55]:<55} {st}  L{local or '?':<6} "
              f"f={fnum or '-':<8} {plat or '-':<10} "
              f"H:{hl or 0:>6,} A:{al or 0:>6,} C:{cl or 0:>6,} N:{nl or 0:>6,}")
    return [r[0] for r in rows]


# ── Insert helpers ────────────────────────────────────────────────────────

def insert_extracted(conn, data):
    """Insert extracted data from JSON structure.

    Expected format:
    {
        "profile_id": 42,
        "employers": [
            {"employer_name": "City of New York", "sector": "PUBLIC_LOCAL",
             "confidence": 0.9, "method": "about_page"}
        ],
        "contracts": [
            {"contract_title": "2024-2027 CBA", "employer_name": "City of NY",
             "expiration_date": "2027-03-31", "contract_url": null}
        ],
        "membership": [
            {"member_count": 150000, "source": "homepage", "count_type": "stated"}
        ],
        "news": [
            {"headline": "New Contract Ratified", "news_type": "contract",
             "date_published": "2025-09-15", "summary": "..."}
        ]
    }
    """
    cur = conn.cursor()
    pid = data['profile_id']

    # Get website URL for source_url
    cur.execute("SELECT website_url FROM web_union_profiles WHERE id = %s", (pid,))
    row = cur.fetchone()
    source_url = row[0] if row else None

    inserted = {'employers': 0, 'contracts': 0, 'membership': 0, 'news': 0}

    for emp in data.get('employers', []):
        cur.execute("""
            INSERT INTO web_union_employers
                (web_profile_id, employer_name, employer_name_clean, state, sector,
                 source_url, extraction_method, confidence_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (pid, emp['employer_name'],
              emp.get('employer_name_clean', emp['employer_name']),
              emp.get('state'), emp.get('sector'),
              source_url, emp.get('method', 'auto_extract'),
              emp.get('confidence', 0.5)))
        inserted['employers'] += 1

    for ctr in data.get('contracts', []):
        exp_date = ctr.get('expiration_date')
        cur.execute("""
            INSERT INTO web_union_contracts
                (web_profile_id, contract_title, employer_name, contract_url,
                 expiration_date, source_url)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (pid, ctr.get('contract_title'), ctr.get('employer_name'),
              ctr.get('contract_url'), exp_date, source_url))
        inserted['contracts'] += 1

    for mem in data.get('membership', []):
        cur.execute("""
            INSERT INTO web_union_membership
                (web_profile_id, member_count, member_count_source, count_type,
                 source_url)
            VALUES (%s, %s, %s, %s, %s)
        """, (pid, mem['member_count'], mem.get('source', 'website'),
              mem.get('count_type', 'stated'), source_url))
        inserted['membership'] += 1

    for nws in data.get('news', []):
        cur.execute("""
            INSERT INTO web_union_news
                (web_profile_id, headline, summary, news_type,
                 date_published, source_url)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (pid, nws.get('headline'), nws.get('summary'),
              nws.get('news_type'), nws.get('date_published'), source_url))
        inserted['news'] += 1

    # Update scrape status
    cur.execute("""
        UPDATE web_union_profiles SET scrape_status = 'EXTRACTED' WHERE id = %s
    """, (pid,))
    conn.commit()

    return inserted


# ── Auto-extraction heuristics ────────────────────────────────────────────

def extract_membership(text):
    """Extract membership count from text using regex patterns."""
    if not text:
        return []

    results = []
    patterns = [
        # "150,000 members" or "150000 members"
        (r'([\d,]+)\s+members?\b', 'stated'),
        # "representing 150,000 workers"
        (r'represent(?:s|ing)\s+([\d,]+)\s+(?:workers?|employees?|people)', 'stated'),
        # "more than 150,000 members"
        (r'more\s+than\s+([\d,]+)\s+members?', 'stated'),
        # "over 150,000 members"
        (r'over\s+([\d,]+)\s+members?', 'approximate'),
        # "approximately 150,000 members"
        (r'approximately\s+([\d,]+)\s+members?', 'approximate'),
        # "nearly 150,000 members"
        (r'nearly\s+([\d,]+)\s+members?', 'approximate'),
        # "a union of 150,000"
        (r'union\s+of\s+([\d,]+)', 'stated'),
    ]

    seen = set()
    for pattern, count_type in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            num_str = m.group(1).replace(',', '')
            try:
                num = int(num_str)
                if 10 <= num <= 5_000_000 and num not in seen:
                    seen.add(num)
                    results.append({
                        'member_count': num,
                        'source': 'auto_extract',
                        'count_type': count_type,
                    })
            except ValueError:
                pass

    return results


def extract_employers(text, state=None):
    """Extract employer names from text using patterns."""
    if not text:
        return []

    results = []
    patterns = [
        # "employees of the City of X"
        r'employees?\s+of\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,|\band\b|\bin\b)',
        # "represent workers at X"
        r'represent(?:s|ing)?\s+(?:workers?|employees?|members?)\s+(?:at|of|in)\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,|\band\b)',
        # "bargaining unit at X"
        r'bargaining\s+unit\s+at\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,)',
        # "contract with X"
        r'contract\s+with\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,|\bfor\b)',
        # "employed by X"
        r'employed\s+by\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,)',
        # "works for X" / "work for X"
        r'works?\s+for\s+(?:the\s+)?([A-Z][A-Za-z\s&,]+?)(?:\.|,)',
    ]

    seen = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            name = m.group(1).strip().rstrip(',. ')
            # Filter out junk
            if len(name) < 4 or len(name) > 100:
                continue
            if name.lower() in ('the', 'our', 'their', 'these', 'those', 'all', 'union'):
                continue
            name_key = name.lower()
            if name_key not in seen:
                seen.add(name_key)
                # Guess sector
                sector = guess_sector(name)
                results.append({
                    'employer_name': name,
                    'employer_name_clean': name,
                    'state': state,
                    'sector': sector,
                    'method': 'auto_extract',
                    'confidence': 0.6,
                })

    return results


def guess_sector(name):
    """Guess employer sector from name keywords."""
    name_lower = name.lower()
    if any(w in name_lower for w in ['city of', 'county of', 'town of',
                                      'village of', 'borough of',
                                      'municipal', 'city council']):
        return 'PUBLIC_LOCAL'
    if any(w in name_lower for w in ['state of', 'commonwealth',
                                      'department of', 'state university']):
        return 'PUBLIC_STATE'
    if any(w in name_lower for w in ['university', 'college', 'school district',
                                      'board of education', 'public school']):
        return 'PUBLIC_EDUCATION'
    if any(w in name_lower for w in ['hospital', 'health', 'medical center',
                                      'nursing', 'healthcare']):
        return 'HEALTHCARE'
    if any(w in name_lower for w in ['federal', 'u.s.', 'united states']):
        return 'PUBLIC_FEDERAL'
    return None


def extract_contracts(text):
    """Extract contract/CBA mentions from text."""
    if not text:
        return []

    results = []
    patterns = [
        # "2024-2027 Contract" or "2024-2027 CBA"
        r'(\d{4})\s*[-\u2013]\s*(\d{4})\s+(?:Contract|CBA|Agreement|Collective Bargaining)',
        # "Contract expires 2027"
        r'(?:contract|agreement|CBA)\s+expires?\s+(?:in\s+)?(\w+\s+\d{1,2},?\s+)?(\d{4})',
        # "Collective Bargaining Agreement" as standalone title
        r'((?:Collective Bargaining|Labor)\s+Agreement(?:\s+[-\u2013]\s+.{5,60})?)',
    ]

    seen = set()
    for i, pattern in enumerate(patterns):
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if i == 0:
                title = f"{m.group(1)}-{m.group(2)} Agreement"
                exp = f"{m.group(2)}-12-31"
            elif i == 1:
                year = m.group(2) if m.group(2) else m.group(1)
                title = f"Contract (expires {year})"
                exp = f"{year}-12-31" if year and year.isdigit() else None
            else:
                title = m.group(1).strip()[:100]
                exp = None

            if title not in seen:
                seen.add(title)
                results.append({
                    'contract_title': title,
                    'employer_name': None,
                    'expiration_date': exp,
                    'contract_url': None,
                })

    # Also look for PDF links to contracts
    pdf_pattern = r'\[([^\]]*(?:contract|agreement|CBA|bargaining)[^\]]*)\]\(([^)]+\.pdf[^)]*)\)'
    for m in re.finditer(pdf_pattern, text, re.IGNORECASE):
        title = m.group(1).strip()[:100]
        url = m.group(2).strip()
        if title not in seen:
            seen.add(title)
            results.append({
                'contract_title': title,
                'expiration_date': None,
                'employer_name': None,
                'contract_url': url,
            })

    return results


def extract_news(text):
    """Extract news headlines from text (usually blog/news pages)."""
    if not text:
        return []

    results = []

    # Look for markdown headings followed by dates
    # ## Headline\n date or similar
    heading_pattern = r'#+\s+(.{10,120}?)(?:\n|\r)'
    date_pattern = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'

    # Find headings that look like news
    news_keywords = ['ratif', 'strike', 'contract', 'negoti', 'elect', 'organiz',
                     'rally', 'protest', 'victory', 'win', 'fight', 'demand',
                     'bargain', 'wage', 'raise', 'vote', 'picket', 'grievance',
                     'arbitrat', 'unfair', 'labor', 'action', 'settle']

    for m in re.finditer(heading_pattern, text):
        headline = m.group(1).strip()
        # Skip navigation/boilerplate
        if any(skip in headline.lower() for skip in ['menu', 'search', 'navigation',
                                                      'skip to', 'footer', 'sidebar',
                                                      'categories', 'archives', 'tag']):
            continue
        if len(headline) < 15:
            continue

        # Check if news-like
        is_news = any(kw in headline.lower() for kw in news_keywords)
        if not is_news and len(results) >= 3:
            continue  # only grab obvious news after first 3

        # Try to find a nearby date
        context = text[max(0, m.start()-50):m.end()+200]
        date_match = re.search(date_pattern, context)
        pub_date = None
        if date_match:
            try:
                from dateutil.parser import parse as parse_date
                pub_date = parse_date(date_match.group(0)).strftime('%Y-%m-%d')
            except Exception:
                pass

        # Guess news type
        hl_lower = headline.lower()
        if any(w in hl_lower for w in ['contract', 'ratif', 'bargain', 'negoti']):
            news_type = 'contract'
        elif any(w in hl_lower for w in ['strike', 'picket', 'action', 'rally']):
            news_type = 'action'
        elif any(w in hl_lower for w in ['elect', 'vote', 'organiz']):
            news_type = 'organizing'
        else:
            news_type = 'general'

        results.append({
            'headline': headline[:200],
            'news_type': news_type,
            'date_published': pub_date,
            'summary': None,
        })

        if len(results) >= 5:
            break

    return results


def auto_extract_profile(conn, profile_id):
    """Run all heuristic extractors on a profile."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, union_name, state, raw_text, raw_text_about,
               raw_text_contracts, raw_text_news
        FROM web_union_profiles WHERE id = %s
    """, (profile_id,))
    row = cur.fetchone()
    if not row:
        return None

    pid, name, state, homepage, about, contracts, news = row

    # Combine texts for different extraction types
    all_text = '\n'.join(t for t in [homepage, about, contracts, news] if t)
    about_text = '\n'.join(t for t in [about, homepage] if t)

    data = {
        'profile_id': pid,
        'employers': extract_employers(about_text, state),
        'contracts': extract_contracts(contracts or homepage or ''),
        'membership': extract_membership(all_text),
        'news': extract_news(news or ''),
    }

    return data


def auto_extract_all(conn):
    """Run auto-extraction on all FETCHED profiles."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM web_union_profiles
        WHERE scrape_status = 'FETCHED'
        ORDER BY id
    """)
    ids = [r[0] for r in cur.fetchall()]

    print(f"Auto-extracting {len(ids)} profiles...\n")

    total = {'employers': 0, 'contracts': 0, 'membership': 0, 'news': 0}
    extracted = 0

    for pid in ids:
        data = auto_extract_profile(conn, pid)
        if not data:
            continue

        has_data = any(data.get(k) for k in ['employers', 'contracts', 'membership', 'news'])

        if has_data:
            inserted = insert_extracted(conn, data)
            extracted += 1
            for k in total:
                total[k] += inserted[k]
            items = ', '.join(f"{v} {k}" for k, v in inserted.items() if v > 0)
            print(f"  [{pid}] {items}")
        else:
            # Mark as extracted even if nothing found (no data on site)
            cur.execute("""
                UPDATE web_union_profiles SET scrape_status = 'EXTRACTED' WHERE id = %s
            """, (pid,))
            conn.commit()
            extracted += 1

    print(f"\n{'='*60}")
    print(f"AUTO-EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"  Profiles processed: {extracted}")
    print(f"  Employers found:    {total['employers']}")
    print(f"  Contracts found:    {total['contracts']}")
    print(f"  Membership counts:  {total['membership']}")
    print(f"  News items:         {total['news']}")

    return total


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AFSCME data extraction helper')
    parser.add_argument('--read', type=int, help='Read raw text for profile ID')
    parser.add_argument('--read-batch', type=int, default=0, help='Read batch of N profiles')
    parser.add_argument('--insert', type=str, help='Insert from JSON file')
    parser.add_argument('--auto-extract', action='store_true', help='Run heuristic extraction on all FETCHED')
    args = parser.parse_args()

    conn = get_connection()
    try:
        if args.read:
            read_profile(conn, args.read)
        elif args.read_batch:
            read_batch(conn, args.read_batch)
        elif args.insert:
            with open(args.insert, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    inserted = insert_extracted(conn, item)
                    print(f"  [{item['profile_id']}] {inserted}")
            else:
                inserted = insert_extracted(conn, data)
                print(f"  [{data['profile_id']}] {inserted}")
        elif args.auto_extract:
            auto_extract_all(conn)
        else:
            parser.print_help()
    finally:
        conn.close()
