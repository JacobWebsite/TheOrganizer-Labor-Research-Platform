import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

print("AFSCME in OLMS LM Data:")
print("=" * 80)
cur.execute("""
    SELECT union_name, f_num, members, ttl_receipts, yr_covered
    FROM lm_data
    WHERE (aff_abbr = 'AFSCME' OR union_name ILIKE '%AFSCME%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 20
""")
for r in cur.fetchall():
    print(f"  {r[0][:50]:<52} F#: {r[1]:<10} Members: {r[2] or 0:>10,} Revenue: ${r[3] or 0:>14,.0f}")

# Total AFSCME
cur.execute("""
    SELECT COUNT(*), SUM(members), SUM(ttl_receipts)
    FROM lm_data
    WHERE (aff_abbr = 'AFSCME' OR union_name ILIKE '%AFSCME%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
""")
total = cur.fetchone()
print(f"\n  AFSCME TOTAL: {total[0]} orgs, {total[1] or 0:,} members, ${total[2] or 0:,.0f} revenue")

print("\n" + "=" * 80)
print("SEIU in OLMS LM Data:")
print("=" * 80)
cur.execute("""
    SELECT union_name, f_num, members, ttl_receipts, yr_covered
    FROM lm_data
    WHERE (aff_abbr = 'SEIU' OR union_name ILIKE '%SEIU%' OR union_name ILIKE '%SERVICE EMPLOYEES%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 20
""")
for r in cur.fetchall():
    print(f"  {r[0][:50]:<52} F#: {r[1]:<10} Members: {r[2] or 0:>10,} Revenue: ${r[3] or 0:>14,.0f}")

# Total SEIU
cur.execute("""
    SELECT COUNT(*), SUM(members), SUM(ttl_receipts)
    FROM lm_data
    WHERE (aff_abbr = 'SEIU' OR union_name ILIKE '%SEIU%' OR union_name ILIKE '%SERVICE EMPLOYEES%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
""")
total = cur.fetchone()
print(f"\n  SEIU TOTAL: {total[0]} orgs, {total[1] or 0:,} members, ${total[2] or 0:,.0f} revenue")

conn.close()
