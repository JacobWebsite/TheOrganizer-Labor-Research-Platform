"""
FIND INTERNATIONAL FILINGS BY DC LOCATION
International unions are headquartered in Washington DC
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

print("=" * 90)
print("INTERNATIONAL FILINGS - Identified by Washington DC headquarters")
print("=" * 90)

# Find Washington DC-based organizations with highest membership
cur.execute("""
    SELECT aff_abbr, f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE (city ILIKE '%WASHINGTON%' OR city ILIKE '%DC%')
    AND yr_covered = 2024
    AND members > 100000
    ORDER BY members DESC
""")

print(f"\n{'Affil':<10} {'File#':<10} {'Members':>12} {'Revenue':>16} Name")
print("-" * 90)

seen_affiliations = set()
international_members = 0
for r in cur.fetchall():
    aff, f_num, name, members, revenue = r
    # Only show one per affiliation (the largest = International)
    if aff and aff not in seen_affiliations:
        seen_affiliations.add(aff)
        international_members += members or 0
        print(f"{(aff or 'N/A'):<10} {f_num:<10} {members or 0:>12,} ${revenue or 0:>14,.0f} {(name or '')[:40]}")

# Now add non-DC internationals (like UAW in Detroit)
print("\n\nNon-DC Major Internationals:")
cur.execute("""
    SELECT aff_abbr, f_num, union_name, members, ttl_receipts, city
    FROM lm_data
    WHERE aff_abbr IN ('UAW', 'USW')
    AND yr_covered = 2024
    ORDER BY members DESC
    LIMIT 2
""")
for r in cur.fetchall():
    aff, f_num, name, members, revenue, city = r
    if aff not in seen_affiliations:
        international_members += members or 0
        print(f"{(aff or 'N/A'):<10} {f_num:<10} {members or 0:>12,} ${revenue or 0:>14,.0f} {city}")

# Also check AFSCME specifically
print("\n\nAFSCME - All DC-based filings:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE aff_abbr = 'AFSCME'
    AND city ILIKE '%WASHINGTON%'
    AND yr_covered = 2024
    ORDER BY members DESC
""")
for r in cur.fetchall():
    print(f"  F#: {r[0]:<10} Members: {r[1] or 0:>12,}  Revenue: ${r[2] or 0:>14,.0f}  {(r[1] or '')[:40]}")

# Check F#289 specifically
print("\n\nF#289 (AFSCME International):")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, city, state
    FROM lm_data
    WHERE f_num = '289'
    AND yr_covered = 2024
""")
result = cur.fetchone()
if result:
    print(f"  F#: {result[0]}  Members: {result[2]:,}  Revenue: ${result[3]:,.0f}  City: {result[4]}, {result[5]}")
else:
    print("  NOT FOUND")

conn.close()
