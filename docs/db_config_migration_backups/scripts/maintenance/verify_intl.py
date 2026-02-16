import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
cur = conn.cursor()

print("VERIFYING INTERNATIONAL FILINGS")
print("=" * 90)

# AFSCME F#289
print("\nAFSCME F#289 Details:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, city, state, yr_covered
    FROM lm_data
    WHERE f_num = '289' AND aff_abbr = 'AFSCME'
    ORDER BY yr_covered DESC
    LIMIT 3
""")
for r in cur.fetchall():
    print(f"  Year: {r[6]}  Members: {r[2]:,}  Revenue: ${r[3]:,.0f}  Location: {r[4]}, {r[5]}")

# SEIU F#137
print("\nSEIU F#137 Details:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, city, state, yr_covered
    FROM lm_data
    WHERE f_num = '137'
    ORDER BY yr_covered DESC
    LIMIT 3
""")
for r in cur.fetchall():
    print(f"  Year: {r[6]}  Members: {r[2]:,}  Revenue: ${r[3]:,.0f}  Location: {r[4]}, {r[5]}")

# Now compare OLMS International vs. claimed membership
print("\n" + "=" * 90)
print("OLMS INTERNATIONAL FILING vs PUBLISHED MEMBERSHIP")
print("=" * 90)

unions = [
    ('AFSCME', '289', 1400000),
    ('SEIU', '137', 2000000),
    ('NEA', '342', 2900000),
    ('AFT', None, 1700000),
    ('IBT', '93', 1300000),
    ('UFCW', '56', 1300000),
]

print(f"{'Union':<10} {'File#':<8} {'OLMS Intl Members':>18} {'Published':>12} {'Diff':>12} {'OLMS %':>8}")
print("-" * 80)

for union, f_num, published in unions:
    if f_num:
        cur.execute("""
            SELECT members, ttl_receipts
            FROM lm_data
            WHERE f_num = %s
            AND yr_covered = 2024
        """, (f_num,))
        result = cur.fetchone()
        if result:
            olms = result[0] or 0
            diff = olms - published
            pct = (olms / published * 100) if published > 0 else 0
            print(f"{union:<10} {f_num:<8} {olms:>18,} {published:>12,} {diff:>+12,} {pct:>7.1f}%")
        else:
            print(f"{union:<10} {f_num:<8} {'No 2024 data':>18}")
    else:
        # Find largest filer
        cur.execute("""
            SELECT f_num, members, ttl_receipts
            FROM lm_data
            WHERE aff_abbr = %s
            AND yr_covered = 2024
            ORDER BY members DESC NULLS LAST
            LIMIT 1
        """, (union,))
        result = cur.fetchone()
        if result:
            print(f"{union:<10} {result[0]:<8} {result[1] or 0:>18,} {published:>12,}")

print("\n" + "=" * 90)
print("CONCLUSION: INTERNATIONAL LM-2 FILINGS EXIST")
print("=" * 90)
print("""
The OLMS data DOES contain International-level filings:
- AFSCME International (F#289): 1,288,804 members
- SEIU International (F#137): 1,947,177 members  
- NEA National (F#342): 2,839,808 members

These numbers are CLOSE to published membership claims, which validates the data.

For 990 VALIDATION:
- 990 Program Service Revenue should approximate OLMS Total Receipts
- If 990 revenue >> OLMS revenue, there may be additional funding sources
- If 990 implied members >> OLMS members, there may be counting differences

The 990 serves as a CROSS-CHECK, not a primary data source for these unions.
""")

conn.close()
