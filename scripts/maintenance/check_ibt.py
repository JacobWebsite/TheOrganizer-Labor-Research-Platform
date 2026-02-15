import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Check IBT - they should have an international filing
print("IBT (Teamsters) - ALL filings:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, state
    FROM lm_data
    WHERE aff_abbr = 'IBT'
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY ttl_receipts DESC NULLS LAST
""")
total_ibt = 0
for r in cur.fetchall():
    total_ibt += r[2] or 0
    print(f"  {r[0]:<12} {(r[1] or '')[:40]:<42} {r[2] or 0:>10,} ${r[3] or 0:>14,.0f} {r[4] or ''}")
print(f"\n  TOTAL IBT members in OLMS: {total_ibt:,}")

# Check if there's a hierarchy issue - look at form types
print("\n\nCheck form types in data:")
cur.execute("""
    SELECT form_type, COUNT(*) 
    FROM lm_data 
    WHERE yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    GROUP BY form_type
    ORDER BY COUNT(*) DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]:<10} {r[1]:>6} filings")

# Total organizations vs total member sum
cur.execute("""
    SELECT COUNT(DISTINCT f_num), SUM(members)
    FROM lm_data
    WHERE yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
""")
r = cur.fetchone()
print(f"\n\nTotal unique file numbers: {r[0]:,}")
print(f"Total members (raw sum): {r[1]:,}")

# Check year coverage
print("\n\nYear coverage in lm_data:")
cur.execute("""
    SELECT yr_covered, COUNT(*) as filings, SUM(members) as total_members
    FROM lm_data
    GROUP BY yr_covered
    ORDER BY yr_covered DESC
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  Year {r[0]}: {r[1]:,} filings, {r[2] or 0:,} members")

conn.close()
