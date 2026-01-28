"""
COMPLETE OLMS INTERNATIONAL FILINGS - All major unions
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

print("=" * 90)
print("FINDING ALL INTERNATIONAL/NATIONAL LM-2 FILINGS")
print("=" * 90)

# Find largest filer by revenue for each major union (International is usually largest)
unions_to_check = ['AFSCME', 'SEIU', 'NEA', 'AFT', 'IBT', 'UFCW', 'UAW', 'USW', 'CWA', 'IBEW', 
                   'IAFF', 'LIUNA', 'SMART', 'IUOE', 'UNITE HERE', 'APWU', 'NALC', 'AFGE']

print(f"\n{'Union':<12} {'File#':<10} {'Members':>12} {'Revenue':>16} {'City':<15}")
print("-" * 80)

international_data = {}
for union in unions_to_check:
    cur.execute("""
        SELECT f_num, members, ttl_receipts, city
        FROM lm_data
        WHERE aff_abbr = %s
        AND yr_covered = 2024
        ORDER BY ttl_receipts DESC NULLS LAST
        LIMIT 1
    """, (union,))
    result = cur.fetchone()
    if result:
        f_num, members, revenue, city = result
        international_data[union] = {'f_num': f_num, 'members': members or 0, 'revenue': revenue or 0}
        print(f"{union:<12} {f_num:<10} {members or 0:>12,} ${revenue or 0:>14,.0f} {(city or '')[:15]:<15}")

# Add FOP manually (not in standard affiliations)
cur.execute("""
    SELECT f_num, members, ttl_receipts, city
    FROM lm_data
    WHERE union_name ILIKE '%FRATERNAL ORDER%POLICE%'
    AND yr_covered = 2024
    ORDER BY ttl_receipts DESC NULLS LAST
    LIMIT 1
""")
result = cur.fetchone()
if result:
    print(f"{'FOP':<12} {result[0]:<10} {result[1] or 0:>12,} ${result[2] or 0:>14,.0f} {(result[3] or '')[:15]:<15}")
    international_data['FOP'] = {'f_num': result[0], 'members': result[1] or 0, 'revenue': result[2] or 0}

# Calculate totals
print("\n" + "=" * 90)
print("SUMMARY OF MAJOR UNION INTERNATIONAL FILINGS")
print("=" * 90)

total_members = sum(d['members'] for d in international_data.values())
total_revenue = sum(d['revenue'] for d in international_data.values())

print(f"\nTotal unions found: {len(international_data)}")
print(f"Total membership (International filings): {total_members:,}")
print(f"Total revenue: ${total_revenue:,.0f}")

# Compare to BLS
bls_private = 7400000  # BLS private sector union members
bls_public = 6900000   # BLS public sector union members
bls_total = 14300000

print(f"\nBLS COMPARISON:")
print(f"  BLS Private Sector: {bls_private:,}")
print(f"  BLS Public Sector:  {bls_public:,}")
print(f"  BLS Total:          {bls_total:,}")
print(f"  OLMS Intl Total:    {total_members:,}")
print(f"  OLMS Coverage:      {total_members/bls_total*100:.1f}%")

# The gap analysis
gap = bls_total - total_members
print(f"\n  GAP to fill:        {gap:,}")
print("""
WHERE IS THE GAP?
- State/local affiliates reporting separately (hierarchy duplication in OLMS)
- Federal employees (FLRA data covers ~1.3M)
- Some smaller unions not in this list
- Canadian members (some internationals include Canadian workers)

KEY INSIGHT: Using International filings AVOIDS the hierarchy duplication
problem that caused our earlier overcounts of 70M+ members.
""")

conn.close()
