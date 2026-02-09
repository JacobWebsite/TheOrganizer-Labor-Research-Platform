import os
"""
PROPER 990 VALIDATION FRAMEWORK
Form 990 is used to VALIDATE and identify GAPS in OLMS data
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

print("=" * 90)
print("990 VALIDATION FRAMEWORK: Checking if key unions file LM-2 forms")
print("=" * 90)
print("""
LOGIC:
- If a union files LM-2: OLMS is primary, 990 validates
- If a union DOESN'T file LM-2: 990 is the only source for membership estimation
- Gap = 990 implied members - OLMS reported members = public sector workers
""")

# Check AFSCME International specifically
print("\n" + "=" * 90)
print("AFSCME INTERNATIONAL - Looking for LM-2 filing")
print("=" * 90)

cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, yr_covered, form_type
    FROM lm_data
    WHERE aff_abbr = 'AFSCME'
    AND form_type = 'LM-2'
    AND yr_covered = 2024
    ORDER BY ttl_receipts DESC
    LIMIT 5
""")

print("Largest AFSCME LM-2 filers (by revenue) in 2024:")
for r in cur.fetchall():
    print(f"  F#: {r[0]:<10} {r[1][:40]:<42} Members: {r[2] or 0:>10,}  Revenue: ${r[3] or 0:>14,.0f}")

# Check if there's an "International" filing
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, yr_covered, form_type
    FROM lm_data
    WHERE (union_name ILIKE '%AFSCME%INTERNATIONAL%' 
           OR union_name ILIKE '%STATE COUNTY%INTERNATIONAL%'
           OR (aff_abbr = 'AFSCME' AND union_name ILIKE '%INTL%'))
    ORDER BY yr_covered DESC, ttl_receipts DESC
    LIMIT 5
""")
intl = cur.fetchall()
if intl:
    print("\nAFSCME International filings found:")
    for r in intl:
        print(f"  {r}")
else:
    print("\n*** NO AFSCME INTERNATIONAL LM-2 FILING FOUND ***")
    print("This means AFSCME International does NOT file LM-2 with DOL")
    print("990 would be the PRIMARY source for International-level data")

# Check SEIU
print("\n" + "=" * 90)
print("SEIU INTERNATIONAL - Looking for LM-2 filing")
print("=" * 90)

cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, yr_covered, form_type
    FROM lm_data
    WHERE (aff_abbr = 'SEIU' OR union_name ILIKE '%SERVICE EMPLOYEES%')
    AND form_type = 'LM-2'
    AND yr_covered = 2024
    ORDER BY ttl_receipts DESC
    LIMIT 5
""")

print("Largest SEIU LM-2 filers (by revenue) in 2024:")
for r in cur.fetchall():
    print(f"  F#: {r[0]:<10} {r[1][:40]:<42} Members: {r[2] or 0:>10,}  Revenue: ${r[3] or 0:>14,.0f}")

cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE (union_name ILIKE '%SEIU%INTERNATIONAL%' 
           OR union_name ILIKE '%SERVICE EMPLOYEES%INTERNATIONAL%')
    ORDER BY yr_covered DESC, ttl_receipts DESC
    LIMIT 5
""")
intl = cur.fetchall()
if intl:
    print("\nSEIU International filings found:")
    for r in intl:
        print(f"  {r}")
else:
    print("\n*** NO SEIU INTERNATIONAL LM-2 FILING FOUND ***")

# Check NEA
print("\n" + "=" * 90)
print("NEA - Checking if they file LM-2")
print("=" * 90)

cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, form_type
    FROM lm_data
    WHERE aff_abbr = 'NEA'
    AND yr_covered = 2024
    ORDER BY ttl_receipts DESC
    LIMIT 5
""")
nea = cur.fetchall()
if nea:
    print("NEA LM filers found:")
    for r in nea:
        print(f"  F#: {r[0]:<10} {r[1][:40]:<42} Members: {r[2] or 0:>10,}  Form: {r[4]}")
else:
    print("*** NO NEA LM FILINGS - This is expected (pure public sector)")

# Summary
print("\n" + "=" * 90)
print("VALIDATION FRAMEWORK SUMMARY")
print("=" * 90)
print("""
FOR UNIONS WITH LM-2 FILINGS (IBT, UFCW, UAW, USW, IBEW, CWA):
  - OLMS is definitive for membership
  - 990 can validate revenue figures
  - Compare: OLMS ttl_receipts ≈ 990 total revenue

FOR UNIONS WITHOUT LM-2 INTERNATIONAL FILING:
  - AFSCME: Local/council LM-2s exist, but no International LM-2
  - SEIU: Similar - locals file, International may not
  - NEA: Pure public sector, no LM filing (990 only)
  - FOP: Pure public sector, no LM filing (990 only)

GAP ANALYSIS METHODOLOGY:
  1. Sum all AFSCME local/council LM-2 members = private sector workers
  2. Get AFSCME 990 Program Service Revenue
  3. Apply per-capita rate to estimate total 990-implied membership
  4. Gap = 990 implied - OLMS sum = public sector workers NOT in LM filings
""")

conn.close()
