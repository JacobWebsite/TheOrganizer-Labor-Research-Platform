"""
Page discovery for union web scraper.

Three discovery strategies (run in order):
  1. Sitemap -- fetch /sitemap.xml and sitemap_index.xml
  2. Nav links -- parse markdown links from existing raw_text
  3. Hardcoded probes -- extended subpage paths as fallback

Usage:
    py scripts/scraper/discover_pages.py
    py scripts/scraper/discover_pages.py --profile-id 42
    py scripts/scraper/discover_pages.py --status FETCHED
    py scripts/scraper/discover_pages.py --union AFSCME
"""
import sys
import os
import re
import time
import argparse
import hashlib
from urllib.parse import urljoin, urlparse

import requests
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection
from scripts.scraper.parse_structured import classify_page_type


# ── Config ────────────────────────────────────────────────────────────────

REQUEST_TIMEOUT = 15
RATE_LIMIT_SECS = 1.0
USER_AGENT = "LaborResearchPlatform/1.0 (Academic Research)"

HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
}

# Extended subpage paths beyond SUBPAGE_PATHS in fetch_union_sites.py
PROBE_PATHS = [
    '/about', '/about-us', '/about/',
    '/contracts', '/contracts/', '/collective-bargaining',
    '/collective-bargaining-agreements',
    '/news', '/news/', '/blog', '/blog/',
    '/members', '/membership', '/join',
    '/resources', '/links',
    '/employers', '/where-we-work', '/workplaces',
    '/bargaining-units', '/represented-employers',
    '/officers', '/leadership', '/executive-board',
    '/contact', '/contact-us',
    '/stewards', '/steward-resources',
    '/events', '/calendar',
    '/political-action', '/cope',
    '/history', '/who-we-are',
    '/benefits', '/member-benefits',
    '/grievance', '/grievances',
    '/faqs', '/faq',
]


# ── Sitemap Discovery ────────────────────────────────────────────────────

def discover_sitemap(base_url, session):
    """Fetch and parse sitemap.xml. Returns list of (url, page_type) tuples."""
    pages = []
    sitemap_urls_to_try = [
        base_url.rstrip('/') + '/sitemap.xml',
        base_url.rstrip('/') + '/sitemap_index.xml',
        base_url.rstrip('/') + '/wp-sitemap.xml',
    ]

    for sitemap_url in sitemap_urls_to_try:
        try:
            resp = session.get(sitemap_url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
            if resp.status_code != 200:
                continue

            content_type = resp.headers.get('content-type', '')
            if 'xml' not in content_type and '<?xml' not in resp.text[:100]:
                continue

            root = etree.fromstring(resp.content)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            # Check if it's a sitemap index
            sitemaps = root.findall('.//sm:sitemap/sm:loc', ns)
            if sitemaps:
                # It's an index -- fetch each child sitemap
                for sm_loc in sitemaps[:10]:  # limit to 10 sub-sitemaps
                    child_url = sm_loc.text.strip()
                    time.sleep(RATE_LIMIT_SECS)
                    try:
                        child_resp = session.get(child_url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
                        if child_resp.status_code == 200:
                            child_root = etree.fromstring(child_resp.content)
                            for url_elem in child_root.findall('.//sm:url/sm:loc', ns):
                                url = url_elem.text.strip()
                                pages.append((url, classify_page_type(url)))
                    except Exception:
                        continue

            # Also check for direct URL entries
            for url_elem in root.findall('.//sm:url/sm:loc', ns):
                url = url_elem.text.strip()
                pages.append((url, classify_page_type(url)))

            if pages:
                return pages, sitemap_url

        except Exception:
            continue

    return pages, None


# ── Nav Link Discovery ───────────────────────────────────────────────────

def discover_nav_links(raw_text, base_url):
    """Parse markdown links [text](url) from raw_text. Returns list of (url, page_type)."""
    if not raw_text:
        return []

    pages = []
    seen = set()
    base_domain = urlparse(base_url).netloc.lower()

    # Match markdown links
    for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', raw_text):
        text = m.group(1).strip()
        url = m.group(2).strip()

        # Resolve relative URLs
        if not url.startswith(('http://', 'https://')):
            url = urljoin(base_url, url)

        # Filter to same domain
        url_domain = urlparse(url).netloc.lower()
        if url_domain != base_domain:
            continue

        # Skip anchors, fragments, media
        if url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js')):
            continue
        if '#' in url:
            url = url.split('#')[0]
        if not url or url in seen:
            continue

        seen.add(url)
        page_type = classify_page_type(url, text)
        pages.append((url, page_type))

    return pages


# ── Hardcoded Probe Discovery ────────────────────────────────────────────

def discover_probes(base_url, session):
    """Try hardcoded paths and return reachable ones. Returns list of (url, page_type)."""
    pages = []

    for path in PROBE_PATHS:
        url = base_url.rstrip('/') + path
        try:
            time.sleep(RATE_LIMIT_SECS)
            resp = session.head(url, timeout=REQUEST_TIMEOUT, headers=HEADERS,
                                allow_redirects=True)
            # Accept 200 and some 3xx final destinations
            if resp.status_code == 200:
                page_type = classify_page_type(url)
                pages.append((url, page_type))
        except Exception:
            continue

    return pages


# ── Main Discovery Logic ─────────────────────────────────────────────────

def discover_for_profile(conn, profile_id, session):
    """Run all discovery strategies for a single profile."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, union_name, website_url, raw_text, sitemap_parsed, nav_links_parsed
        FROM web_union_profiles WHERE id = %s
    """, (profile_id,))
    row = cur.fetchone()
    if not row:
        return 0

    pid, name, base_url, raw_text, sitemap_done, nav_done = row
    if not base_url:
        return 0

    base_url = base_url.strip().rstrip('/')
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'https://' + base_url

    print(f"[{pid}] {name}")
    total_inserted = 0

    # Strategy 1: Sitemap
    if not sitemap_done:
        sitemap_pages, sitemap_url = discover_sitemap(base_url, session)
        if sitemap_pages:
            for url, page_type in sitemap_pages:
                inserted = _insert_page(cur, pid, url, page_type, 'sitemap')
                total_inserted += inserted
            cur.execute("""
                UPDATE web_union_profiles
                SET sitemap_parsed = TRUE, sitemap_url = %s
                WHERE id = %s
            """, (sitemap_url, pid))
            print(f"  Sitemap: {len(sitemap_pages)} URLs found, {total_inserted} new")
        else:
            cur.execute("UPDATE web_union_profiles SET sitemap_parsed = TRUE WHERE id = %s", (pid,))
            print(f"  Sitemap: none found")

    # Strategy 2: Nav links from raw_text
    pre_nav = total_inserted
    if not nav_done and raw_text:
        nav_pages = discover_nav_links(raw_text, base_url)
        for url, page_type in nav_pages:
            inserted = _insert_page(cur, pid, url, page_type, 'nav_link')
            total_inserted += inserted
        cur.execute("UPDATE web_union_profiles SET nav_links_parsed = TRUE WHERE id = %s", (pid,))
        print(f"  Nav links: {len(nav_pages)} links found, {total_inserted - pre_nav} new")

    # Strategy 3: Hardcoded probes (only if < 3 pages found so far)
    cur.execute("SELECT COUNT(*) FROM web_union_pages WHERE web_profile_id = %s", (pid,))
    existing_count = cur.fetchone()[0]

    if existing_count < 3:
        pre_probe = total_inserted
        probe_pages = discover_probes(base_url, session)
        for url, page_type in probe_pages:
            inserted = _insert_page(cur, pid, url, page_type, 'probe')
            total_inserted += inserted
        print(f"  Probes: {len(probe_pages)} reachable, {total_inserted - pre_probe} new")

    # Update page_inventory
    cur.execute("""
        SELECT page_type, COUNT(*) FROM web_union_pages
        WHERE web_profile_id = %s
        GROUP BY page_type
    """, (pid,))
    inventory = {row[0]: row[1] for row in cur.fetchall()}
    cur.execute("""
        UPDATE web_union_profiles SET page_inventory = %s::jsonb WHERE id = %s
    """, (str(inventory).replace("'", '"'), pid))

    conn.commit()
    print(f"  Total: {total_inserted} new pages discovered")
    return total_inserted


def _insert_page(cur, profile_id, url, page_type, discovered_from):
    """Insert a page record, ON CONFLICT skip. Returns 1 if inserted, 0 if exists."""
    try:
        cur.execute("""
            INSERT INTO web_union_pages (web_profile_id, page_url, page_type, discovered_from)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (web_profile_id, page_url) DO NOTHING
        """, (profile_id, url, page_type, discovered_from))
        return cur.rowcount
    except Exception:
        return 0


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Discover pages for union profiles')
    parser.add_argument('--profile-id', type=int, help='Process single profile')
    parser.add_argument('--status', default='FETCHED', help='Filter by scrape_status (default: FETCHED)')
    parser.add_argument('--union', help='Filter by union name (LIKE match)')
    parser.add_argument('--limit', type=int, help='Max profiles to process')
    args = parser.parse_args()

    conn = get_connection()
    session = requests.Session()
    cur = conn.cursor()

    if args.profile_id:
        discover_for_profile(conn, args.profile_id, session)
    else:
        query = """
            SELECT id FROM web_union_profiles
            WHERE website_url IS NOT NULL
              AND scrape_status = %s
        """
        params = [args.status]

        if args.union:
            query += " AND union_name ILIKE %s"
            params.append(f'%{args.union}%')

        query += " ORDER BY id"

        if args.limit:
            query += " LIMIT %s"
            params.append(args.limit)

        cur.execute(query, params)
        ids = [r[0] for r in cur.fetchall()]
        print(f"Discovering pages for {len(ids)} profiles...\n")

        total = 0
        for pid in ids:
            n = discover_for_profile(conn, pid, session)
            total += n

        print(f"\n{'='*60}")
        print(f"DISCOVERY COMPLETE: {total} new pages across {len(ids)} profiles")

        # Summary
        cur.execute("""
            SELECT discovered_from, COUNT(*)
            FROM web_union_pages
            GROUP BY discovered_from
            ORDER BY COUNT(*) DESC
        """)
        print(f"\nPages by discovery method:")
        for method, cnt in cur.fetchall():
            print(f"  {method:<15} {cnt:>6}")

    conn.close()


if __name__ == '__main__':
    main()
