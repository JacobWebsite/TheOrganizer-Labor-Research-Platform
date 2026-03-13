"""
WordPress REST API extraction for union web scraper.

Uses requests (not Crawl4AI) for WP REST API -- returns JSON, no browser needed.

Usage:
    py scripts/scraper/extract_wordpress.py
    py scripts/scraper/extract_wordpress.py --profile-id 42
    py scripts/scraper/extract_wordpress.py --wp-only
"""
import sys
import os
import time
import json
import argparse
import hashlib

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection
from scripts.scraper.parse_structured import (
    extract_from_tables,
    extract_from_lists,
    extract_pdf_links,
    clean_employer_name,
    guess_sector,
)


# ── Config ────────────────────────────────────────────────────────────────

REQUEST_TIMEOUT = 20
RATE_LIMIT_SECS = 1.0
USER_AGENT = "LaborResearchPlatform/1.0 (Academic Research)"
HEADERS = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}


# ── WP API Helpers ───────────────────────────────────────────────────────

def check_wp_api(base_url, session):
    """Check if WP REST API is available. Returns api_base or None."""
    api_base = base_url.rstrip('/') + '/wp-json/wp/v2'
    try:
        resp = session.get(api_base + '/pages?per_page=1&_fields=id',
                           timeout=REQUEST_TIMEOUT, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return api_base
    except Exception:
        pass

    # Try alternate /index.php?rest_route= pattern
    alt_base = base_url.rstrip('/') + '/index.php?rest_route=/wp/v2'
    try:
        resp = session.get(alt_base + '/pages&per_page=1&_fields=id',
                           timeout=REQUEST_TIMEOUT, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return alt_base
    except Exception:
        pass

    return None


def fetch_wp_pages(api_base, session):
    """Fetch all WP pages via REST API. Returns list of page dicts."""
    pages = []
    page_num = 1
    per_page = 100
    fields = 'id,title,slug,link,content'

    while True:
        sep = '&' if '?' in api_base else '?'
        url = f"{api_base}/pages{sep}per_page={per_page}&page={page_num}&_fields={fields}"
        try:
            time.sleep(RATE_LIMIT_SECS)
            resp = session.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
            if resp.status_code == 429:
                print(f"    Rate limited, waiting 5s...")
                time.sleep(5)
                resp = session.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not isinstance(data, list) or not data:
                break
            pages.extend(data)
            if len(data) < per_page:
                break
            page_num += 1
        except Exception as e:
            print(f"    WP pages fetch error: {e}")
            break

    return pages


def fetch_wp_posts(api_base, session, limit=20):
    """Fetch recent WP posts. Returns list of post dicts."""
    sep = '&' if '?' in api_base else '?'
    url = f"{api_base}/posts{sep}per_page={limit}&_fields=id,title,slug,link,date,excerpt"
    try:
        time.sleep(RATE_LIMIT_SECS)
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


# ── Extraction Logic ─────────────────────────────────────────────────────

def extract_for_profile(conn, profile_id, session):
    """Run WP API extraction for a single profile."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, union_name, website_url, state, platform, wp_api_available, wp_api_base
        FROM web_union_profiles WHERE id = %s
    """, (profile_id,))
    row = cur.fetchone()
    if not row:
        return 0

    pid, name, base_url, state, platform, wp_avail, wp_base = row
    if not base_url:
        return 0

    base_url = base_url.strip().rstrip('/')
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'https://' + base_url

    print(f"[{pid}] {name}")

    # Check WP API availability
    if wp_base:
        api_base = wp_base
    else:
        api_base = check_wp_api(base_url, session)

    if not api_base:
        cur.execute("""
            UPDATE web_union_profiles SET wp_api_available = FALSE WHERE id = %s
        """, (pid,))
        conn.commit()
        print(f"  WP API not available")
        return 0

    # Update profile with API info
    cur.execute("""
        UPDATE web_union_profiles SET wp_api_available = TRUE, wp_api_base = %s WHERE id = %s
    """, (api_base, pid))

    # Fetch pages
    wp_pages = fetch_wp_pages(api_base, session)
    print(f"  Fetched {len(wp_pages)} WP pages")

    employers_inserted = 0
    pages_stored = 0
    pdfs_found = 0

    for wp_page in wp_pages:
        title = wp_page.get('title', {}).get('rendered', '')
        link = wp_page.get('link', '')
        content_html = wp_page.get('content', {}).get('rendered', '')

        if not content_html:
            continue

        content_hash = hashlib.md5(content_html.encode('utf-8', errors='replace')).hexdigest()

        # Store page in web_union_pages
        try:
            cur.execute("""
                INSERT INTO web_union_pages
                    (web_profile_id, page_url, page_type, html_raw, content_hash,
                     discovered_from, http_status, last_scraped)
                VALUES (%s, %s, %s, %s, %s, 'wp_api', 200, NOW())
                ON CONFLICT (web_profile_id, page_url) DO UPDATE
                SET html_raw = EXCLUDED.html_raw,
                    content_hash = EXCLUDED.content_hash,
                    last_scraped = NOW()
                RETURNING id
            """, (pid, link, _classify_wp_page(title, link),
                  content_html, content_hash))
            page_row = cur.fetchone()
            page_id = page_row[0] if page_row else None
            pages_stored += 1
        except Exception:
            page_id = None

        # Extract from tables
        for emp in extract_from_tables(content_html):
            inserted = _insert_employer(cur, pid, emp, state, link, 'wp_api')
            employers_inserted += inserted

        # Extract from lists
        for emp in extract_from_lists(content_html):
            inserted = _insert_employer(cur, pid, emp, state, link, 'wp_api')
            employers_inserted += inserted

        # Extract PDF links
        for pdf in extract_pdf_links(content_html, base_url):
            try:
                cur.execute("""
                    INSERT INTO web_union_pdf_links
                        (profile_id, page_id, pdf_url, link_text, pdf_type, discovered_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (profile_id, pdf_url) DO NOTHING
                """, (pid, page_id, pdf['pdf_url'], pdf['link_text'], pdf['pdf_type']))
                pdfs_found += cur.rowcount
            except Exception:
                pass

    # Fetch and store recent posts as news
    posts = fetch_wp_posts(api_base, session)
    news_inserted = 0
    for post in posts:
        headline = post.get('title', {}).get('rendered', '')
        pub_date = (post.get('date') or '')[:10]  # YYYY-MM-DD
        excerpt = post.get('excerpt', {}).get('rendered', '')
        link = post.get('link', '')

        if not headline or len(headline) < 10:
            continue

        # Clean HTML from headline/excerpt
        import re
        headline = re.sub(r'<[^>]+>', '', headline).strip()[:200]
        excerpt = re.sub(r'<[^>]+>', '', excerpt).strip()[:500]

        try:
            cur.execute("""
                INSERT INTO web_union_news
                    (web_profile_id, headline, summary, news_type, date_published, source_url)
                VALUES (%s, %s, %s, 'general', %s, %s)
                ON CONFLICT DO NOTHING
            """, (pid, headline, excerpt or None, pub_date or None, link))
            news_inserted += cur.rowcount
        except Exception:
            pass

    conn.commit()
    print(f"  Results: {employers_inserted} employers, {pages_stored} pages, "
          f"{pdfs_found} PDFs, {news_inserted} news")
    return employers_inserted


def _classify_wp_page(title, url):
    """Classify a WP page by title/URL."""
    from scripts.scraper.parse_structured import classify_page_type
    return classify_page_type(url, title)


def _insert_employer(cur, profile_id, emp, state, source_url, method):
    """Insert employer with ON CONFLICT. Returns 1 if new, 0 if exists."""
    name = emp['employer_name']
    sector = guess_sector(name)
    try:
        cur.execute("""
            INSERT INTO web_union_employers
                (web_profile_id, employer_name, employer_name_clean, state, sector,
                 source_url, extraction_method, confidence_score,
                 source_page_url, source_element, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (web_profile_id, employer_name_clean) DO UPDATE
            SET confidence_score = GREATEST(web_union_employers.confidence_score, EXCLUDED.confidence_score),
                extraction_method = CASE
                    WHEN EXCLUDED.confidence_score > web_union_employers.confidence_score
                    THEN EXCLUDED.extraction_method
                    ELSE web_union_employers.extraction_method
                END,
                source_page_url = COALESCE(EXCLUDED.source_page_url, web_union_employers.source_page_url),
                source_element = COALESCE(EXCLUDED.source_element, web_union_employers.source_element),
                updated_at = NOW()
        """, (profile_id, name, name, state, sector,
              source_url, method, emp.get('confidence', 0.7),
              source_url, emp.get('source_element', 'wp_api')))
        return cur.rowcount
    except Exception:
        return 0


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='WordPress REST API extraction')
    parser.add_argument('--profile-id', type=int, help='Process single profile')
    parser.add_argument('--wp-only', action='store_true',
                        help='Only process profiles with platform=WordPress')
    parser.add_argument('--limit', type=int, help='Max profiles to process')
    args = parser.parse_args()

    conn = get_connection()
    session = requests.Session()
    cur = conn.cursor()

    if args.profile_id:
        extract_for_profile(conn, args.profile_id, session)
    else:
        query = """
            SELECT id FROM web_union_profiles
            WHERE website_url IS NOT NULL
              AND scrape_status IN ('FETCHED', 'EXTRACTED')
        """
        if args.wp_only:
            query += " AND platform = 'WordPress'"

        query += " ORDER BY id"

        if args.limit:
            query += f" LIMIT {int(args.limit)}"

        cur.execute(query)
        ids = [r[0] for r in cur.fetchall()]
        print(f"Processing {len(ids)} profiles for WP API extraction...\n")

        total_employers = 0
        wp_found = 0
        for pid in ids:
            n = extract_for_profile(conn, pid, session)
            if n > 0:
                wp_found += 1
            total_employers += n

        print(f"\n{'='*60}")
        print(f"WP EXTRACTION COMPLETE")
        print(f"  Profiles processed: {len(ids)}")
        print(f"  Profiles with WP employers: {wp_found}")
        print(f"  Total employers extracted: {total_employers}")

        # Show method breakdown
        cur.execute("""
            SELECT extraction_method, COUNT(*)
            FROM web_union_employers
            GROUP BY extraction_method
            ORDER BY COUNT(*) DESC
        """)
        print(f"\nEmployer counts by method:")
        for method, cnt in cur.fetchall():
            print(f"  {method:<20} {cnt:>6}")

    conn.close()


if __name__ == '__main__':
    main()
