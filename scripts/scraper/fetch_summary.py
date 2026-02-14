"""Checkpoint 2 summary report."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# Failed sites
print('=== FAILED SITES ===')
cur.execute("""
    SELECT wp.id, wp.union_name, wp.state, wp.website_url, sj.error_message
    FROM web_union_profiles wp
    JOIN scrape_jobs sj ON sj.web_profile_id = wp.id
    WHERE sj.status = 'FAILED'
    ORDER BY wp.id
""")
for row in cur.fetchall():
    pid, name, st, url, err = row
    err_short = (err or '')[:100]
    print(f'  [{pid}] {name[:50]:<50} {st}')
    print(f'    URL: {url}')
    print(f'    Error: {err_short}')

# Overall stats
print('\n=== OVERALL STATS ===')
cur.execute("SELECT scrape_status, count(*) FROM web_union_profiles GROUP BY scrape_status ORDER BY count(*) DESC")
for status, cnt in cur.fetchall():
    print(f'  {status}: {cnt}')

# Content volume
cur.execute("""
    SELECT count(*) as profiles,
           SUM(LENGTH(COALESCE(raw_text, ''))) as home_bytes,
           SUM(LENGTH(COALESCE(raw_text_about, ''))) as about_bytes,
           SUM(LENGTH(COALESCE(raw_text_contracts, ''))) as contr_bytes,
           SUM(LENGTH(COALESCE(raw_text_news, ''))) as news_bytes
    FROM web_union_profiles
    WHERE scrape_status = 'FETCHED'
""")
row = cur.fetchone()
profiles, home, about, contr, news = row
total = (home or 0) + (about or 0) + (contr or 0) + (news or 0)
print(f'\n  Fetched profiles: {profiles}')
print(f'  Homepage text:    {(home or 0)//1024:,} KB')
print(f'  About text:       {(about or 0)//1024:,} KB')
print(f'  Contracts text:   {(contr or 0)//1024:,} KB')
print(f'  News text:        {(news or 0)//1024:,} KB')
print(f'  TOTAL raw text:   {total//1024:,} KB ({total/1024/1024:.1f} MB)')

# WordPress detection
cur.execute("SELECT count(*) FROM web_union_profiles WHERE platform = 'WordPress'")
wp = cur.fetchone()[0]
print(f'  WordPress sites:  {wp}')

# Unique domains
cur.execute("""
    SELECT count(DISTINCT SPLIT_PART(SPLIT_PART(website_url, '://', 2), '/', 1))
    FROM web_union_profiles WHERE scrape_status = 'FETCHED'
""")
domains = cur.fetchone()[0]
print(f'  Unique domains:   {domains}')

conn.close()
