"""
Checkpoint 2: AFSCME Union Website Fetcher
Fetches pages from union websites using Crawl4AI and saves raw markdown text.
No AI extraction - just downloading and cleaning webpages.

Usage:
    py -u scripts/scraper/fetch_union_sites.py             # fetch all PENDING
    py -u scripts/scraper/fetch_union_sites.py --limit 5   # fetch first 5 (test run)
    py -u scripts/scraper/fetch_union_sites.py --id 42     # fetch specific profile
"""
import sys
import os
import asyncio
import time
import argparse
from datetime import datetime
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


# ── Config ────────────────────────────────────────────────────────────────

USER_AGENT = "LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)"
PAGE_TIMEOUT_MS = 30000
RATE_LIMIT_SECS = 1.0        # between requests to same domain
DOMAIN_COOLDOWN_SECS = 2.0   # between switching domains
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]    # seconds

# Common subpages to discover
SUBPAGE_PATHS = [
    '/about', '/about-us', '/about/', '/about-us/',
    '/contracts', '/contracts/', '/collective-bargaining',
    '/news', '/news/', '/blog', '/blog/',
    '/members', '/membership',
]

# WordPress API endpoint to detect WP sites
WP_API_PATH = '/wp-json/wp/v2/'


# ── Helpers ───────────────────────────────────────────────────────────────

def normalize_url(url):
    """Ensure URL has a scheme."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    # Remove trailing slash for consistency
    return url.rstrip('/')


def get_domain(url):
    """Extract domain from URL."""
    return urlparse(url).netloc.lower()


async def fetch_page(crawler, url, run_config, retries=MAX_RETRIES):
    """Fetch a single page with retries. Returns (markdown_text, success, error)."""
    for attempt in range(retries):
        try:
            result = await crawler.arun(url=url, config=run_config)
            if result.success:
                text = ''
                if result.markdown:
                    if hasattr(result.markdown, 'raw_markdown'):
                        text = result.markdown.raw_markdown or ''
                    else:
                        text = str(result.markdown)
                return text, True, None
            else:
                error = result.error_message or 'Unknown error'
                if attempt < retries - 1:
                    wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                    print(f"    Retry {attempt + 1}/{retries} in {wait}s: {error}")
                    await asyncio.sleep(wait)
                else:
                    return '', False, error
        except Exception as e:
            error = str(e)
            if attempt < retries - 1:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                print(f"    Retry {attempt + 1}/{retries} in {wait}s: {error[:80]}")
                await asyncio.sleep(wait)
            else:
                return '', False, error
    return '', False, 'Max retries exceeded'


async def check_wordpress(crawler, base_url, run_config):
    """Check if site is WordPress by hitting /wp-json/wp/v2/."""
    wp_url = base_url.rstrip('/') + WP_API_PATH
    try:
        result = await crawler.arun(url=wp_url, config=run_config)
        if result.success:
            text = ''
            if result.markdown:
                text = result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown)
            if 'namespace' in text.lower() or 'wp/v2' in text.lower() or 'routes' in text.lower():
                return 'WordPress'
    except Exception:
        pass
    return None


async def discover_subpages(crawler, base_url, run_config):
    """Try common subpage paths and return {page_type: markdown_text}."""
    found = {}
    page_urls = []

    for path in SUBPAGE_PATHS:
        sub_url = base_url.rstrip('/') + path
        page_urls.append((path, sub_url))

    for path, sub_url in page_urls:
        await asyncio.sleep(RATE_LIMIT_SECS)
        text, success, error = await fetch_page(crawler, sub_url, run_config, retries=1)

        if success and text and len(text.strip()) > 200:
            # Categorize the page
            path_lower = path.lower()
            if 'about' in path_lower:
                page_type = 'about'
            elif 'contract' in path_lower or 'bargaining' in path_lower:
                page_type = 'contracts'
            elif 'news' in path_lower or 'blog' in path_lower:
                page_type = 'news'
            else:
                page_type = 'other'

            # Only keep first match per type
            if page_type not in found:
                found[page_type] = text
                print(f"    Found /{path.strip('/')}: {len(text):,} chars")

    return found


# ── Main Fetch Logic ──────────────────────────────────────────────────────

async def fetch_profile(crawler, run_config, profile, conn):
    """Fetch all pages for a single union profile."""
    pid, name, url, state = profile
    url = normalize_url(url)
    if not url:
        return False

    print(f"\n[{pid}] {name} ({state})")
    print(f"  URL: {url}")

    started_at = datetime.now()
    cur = conn.cursor()

    # Create scrape job
    cur.execute("""
        INSERT INTO scrape_jobs (target_url, target_entity_type, web_profile_id, status, started_at)
        VALUES (%s, 'UNION_LOCAL', %s, 'IN_PROGRESS', %s)
        RETURNING id
    """, (url, pid, started_at))
    job_id = cur.fetchone()[0]
    conn.commit()

    pages_scraped = 0
    pages_found = []
    error_msg = None

    try:
        # 1. Fetch homepage
        print(f"  Fetching homepage...")
        homepage_text, success, error = await fetch_page(crawler, url, run_config)

        if not success:
            error_msg = f"Homepage failed: {error}"
            print(f"  FAILED: {error}")
            cur.execute("""
                UPDATE web_union_profiles
                SET scrape_status = 'FAILED', last_scraped = NOW()
                WHERE id = %s
            """, (pid,))
            cur.execute("""
                UPDATE scrape_jobs
                SET status = 'FAILED', error_message = %s, completed_at = NOW(),
                    duration_seconds = EXTRACT(EPOCH FROM NOW() - started_at)
                WHERE id = %s
            """, (error_msg, job_id))
            conn.commit()
            return False

        pages_scraped += 1
        pages_found.append(url)
        print(f"  Homepage: {len(homepage_text):,} chars")

        # 2. Check WordPress
        await asyncio.sleep(RATE_LIMIT_SECS)
        platform = await check_wordpress(crawler, url, run_config)
        if platform:
            print(f"  Platform: {platform}")

        # 3. Discover subpages
        subpages = await discover_subpages(crawler, url, run_config)
        pages_scraped += len(subpages)
        for ptype in subpages:
            pages_found.append(f"{url}/{ptype}")

        # 4. Save to database
        about_text = subpages.get('about')
        contracts_text = subpages.get('contracts')
        news_text = subpages.get('news')

        cur.execute("""
            UPDATE web_union_profiles
            SET raw_text = %s,
                raw_text_about = %s,
                raw_text_contracts = %s,
                raw_text_news = %s,
                platform = %s,
                scrape_status = 'FETCHED',
                last_scraped = NOW()
            WHERE id = %s
        """, (homepage_text, about_text, contracts_text, news_text, platform, pid))

        # 5. Update scrape job
        duration = (datetime.now() - started_at).total_seconds()
        cur.execute("""
            UPDATE scrape_jobs
            SET status = 'COMPLETED', pages_scraped = %s, pages_found = %s,
                completed_at = NOW(), duration_seconds = %s
            WHERE id = %s
        """, (pages_scraped, pages_found, duration, job_id))

        conn.commit()
        print(f"  OK: {pages_scraped} pages, {len(homepage_text) + sum(len(v) for v in subpages.values()):,} total chars, {duration:.1f}s")
        return True

    except Exception as e:
        error_msg = str(e)[:500]
        print(f"  ERROR: {error_msg}")
        cur.execute("""
            UPDATE web_union_profiles
            SET scrape_status = 'FAILED', last_scraped = NOW()
            WHERE id = %s
        """, (pid,))
        cur.execute("""
            UPDATE scrape_jobs
            SET status = 'FAILED', error_message = %s, completed_at = NOW(),
                duration_seconds = EXTRACT(EPOCH FROM NOW() - started_at)
            WHERE id = %s
        """, (error_msg, job_id))
        conn.commit()
        return False


async def main(limit=None, profile_id=None):
    """Main entry point."""
    conn = get_connection()
    cur = conn.cursor()

    # Get profiles to fetch
    if profile_id:
        cur.execute("""
            SELECT id, union_name, website_url, state
            FROM web_union_profiles
            WHERE id = %s AND website_url IS NOT NULL
        """, (profile_id,))
    else:
        query = """
            SELECT id, union_name, website_url, state
            FROM web_union_profiles
            WHERE scrape_status = 'PENDING' AND website_url IS NOT NULL
            ORDER BY id
        """
        if limit:
            query += f" LIMIT {int(limit)}"
        cur.execute(query)

    profiles = cur.fetchall()
    print(f"Found {len(profiles)} profiles to fetch")

    if not profiles:
        print("Nothing to fetch!")
        conn.close()
        return

    # Configure Crawl4AI
    browser_config = BrowserConfig(
        headless=True,
        user_agent=USER_AGENT,
    )

    run_config = CrawlerRunConfig(
        page_timeout=PAGE_TIMEOUT_MS,
        wait_until="domcontentloaded",
        cache_mode=CacheMode.BYPASS,
        check_robots_txt=True,
        verbose=False,
    )

    # Process profiles
    success_count = 0
    fail_count = 0
    last_domain = None

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for profile in profiles:
            pid, name, url, state = profile
            url = normalize_url(url)
            if not url:
                continue

            # Domain cooldown
            domain = get_domain(url)
            if last_domain and domain != last_domain:
                await asyncio.sleep(DOMAIN_COOLDOWN_SECS)
            elif last_domain == domain:
                await asyncio.sleep(RATE_LIMIT_SECS)
            last_domain = domain

            ok = await fetch_profile(crawler, run_config, profile, conn)
            if ok:
                success_count += 1
            else:
                fail_count += 1

    # Summary
    print(f"\n{'=' * 60}")
    print(f"FETCH COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Success: {success_count}")
    print(f"  Failed:  {fail_count}")
    print(f"  Total:   {success_count + fail_count}")

    # Show saved text stats
    cur.execute("""
        SELECT id, union_name, state,
               LENGTH(raw_text) as homepage_len,
               LENGTH(raw_text_about) as about_len,
               LENGTH(raw_text_contracts) as contracts_len,
               LENGTH(raw_text_news) as news_len,
               platform
        FROM web_union_profiles
        WHERE scrape_status = 'FETCHED'
        ORDER BY LENGTH(raw_text) DESC NULLS LAST
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        print(f"\nTop fetched profiles by content size:")
        print(f"  {'ID':<5} {'Name':<40} {'ST':<4} {'Home':>8} {'About':>8} {'Contr':>8} {'News':>8} {'Platform'}")
        print(f"  {'-'*5} {'-'*40} {'-'*4} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
        for row in rows:
            pid, name, st, home, about, contr, news, plat = row
            print(f"  {pid:<5} {name[:40]:<40} {st:<4} "
                  f"{(home or 0):>8,} {(about or 0):>8,} "
                  f"{(contr or 0):>8,} {(news or 0):>8,} {plat or ''}")

    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch AFSCME union websites')
    parser.add_argument('--limit', type=int, help='Max profiles to fetch')
    parser.add_argument('--id', type=int, help='Fetch specific profile ID')
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit, profile_id=args.id))
