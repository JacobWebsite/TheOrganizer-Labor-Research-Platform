"""
PROPER RECONCILIATION: Using International LM-2 filings as primary
990 data is for VALIDATION and GAP-FILLING only
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

print("=" * 90)
print("PROPER MEMBERSHIP RECONCILIATION")
print("Using International LM-2 filings (deduplicated, not sum of all locals)")
print("=" * 90)

# International file numbers for major unions
international_filings = {
    'AFSCME': '289',      # AFSCME International
    'SEIU': '137',        # SEIU International
    'NEA': '342',         # NEA National
    'IBT': '93',          # IBT International
    'UFCW': '56',         # UFCW International
    'UAW': '149',         # UAW International
    'USW': '1',           # USW International (need to verify)
    'CWA': '26',          # CWA (need to verify)
    'IBEW': '68',         # IBEW International (need to verify)
}

print("\nINTERNATIONAL FILING MEMBERSHIP (2024):")
print("-" * 80)
print(f"{'Union':<12} {'File#':<8} {'Members':>12} {'Revenue':>16} {'City':<20}")
print("-" * 80)

total_members = 0
for union, f_num in international_filings.items():
    cur.execute("""
        SELECT members, ttl_receipts, city
        FROM lm_data
        WHERE f_num = %s
        AND yr_covered = 2024
    """, (f_num,))
    result = cur.fetchone()
    if result and result[0]:
        members = result[0]
        revenue = result[1] or 0
        city = result[2] or ''
        total_members += members
        print(f"{union:<12} {f_num:<8} {members:>12,} ${revenue:>14,.0f} {city:<20}")
    else:
        print(f"{union:<12} {f_num:<8} {'Not found/no data':>12}")

print("-" * 80)
print(f"{'TOTAL':<12} {'':<8} {total_members:>12,}")

# Now identify unions WITHOUT International LM-2 filings (990 needed)
print("\n" + "=" * 90)
print("UNIONS WHERE 990 IS PRIMARY SOURCE (No LM-2 International Filing)")
print("=" * 90)

# FOP - Check if they file
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE union_name ILIKE '%FRATERNAL ORDER%POLICE%'
       OR union_name ILIKE '%FOP%'
    AND yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 5
""")
fop = cur.fetchall()
if fop:
    print("\nFOP LM filings found:")
    for r in fop:
        print(f"  {r}")
else:
    print("\n*** FOP: No LM filings - 990 is PRIMARY source ***")

# PBA
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE union_name ILIKE '%PATROLMEN%BENEVOLENT%'
       OR union_name ILIKE '%PBA%'
    AND yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 5
""")
pba = cur.fetchall()
if pba:
    print("\nPBA LM filings found:")
    for r in pba:
        print(f"  {r}")
else:
    print("\n*** PBA: No LM filings - 990 is PRIMARY source ***")

# IAFF
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE aff_abbr = 'IAFF'
    AND yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 5
""")
iaff = cur.fetchall()
print("\nIAFF LM filings:")
if iaff:
    for r in iaff:
        print(f"  F#: {r[0]:<10} Members: {r[2] or 0:>10,}  Revenue: ${r[3] or 0:>14,.0f}")
else:
    print("  No IAFF LM filings found")

# Summary
print("\n" + "=" * 90)
print("RECONCILIATION SUMMARY")
print("=" * 90)

# Get proper totals using International filings
cur.execute("""
    SELECT SUM(members)
    FROM lm_data
    WHERE f_num IN ('289', '137', '342', '93', '56', '149', '1', '26', '68')
    AND yr_covered = 2024
""")
intl_total = cur.fetchone()[0] or 0

# BLS union membership total
bls_total = 14300000  # BLS 2024 estimate

print(f"""
OLMS International Filings Total: {intl_total:,}
BLS Total Union Membership:       {bls_total:,}
Gap to fill from 990/other:       {bls_total - intl_total:,}

The gap represents:
- Public sector workers in state/local unions without LM filing
- FOP, PBA members (pure public sector)
- Federal employees (FLRA data, not OLMS)
- Small unions below LM filing threshold

990 DATA SHOULD BE USED FOR:
1. Validating OLMS revenue matches 990 revenue
2. Filling gaps for FOP, PBA, other non-LM filers
3. NOT for replacing OLMS data where LM-2 exists
""")

conn.close()
