import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

print("=" * 90)
print("990 vs OLMS CROSS-VALIDATION FOR MIXED SECTOR UNIONS")
print("=" * 90)
print("""
For unions that file BOTH LM forms AND 990s, we can cross-validate:
- OLMS: Direct member counts from LM-2 filings
- 990: Dues revenue / per-capita rate = implied membership

If 990 implied > OLMS deduped, gap = public sector not in LM filings
""")

# Get AFSCME from both sources
print("\n" + "=" * 90)
print("AFSCME CROSS-VALIDATION")
print("=" * 90)

# OLMS deduplicated
cur.execute("""
    SELECT total_counted FROM v_dedup_summary_by_affiliation 
    WHERE aff_abbr = 'AFSCME'
""")
afscme_olms = cur.fetchone()
print(f"OLMS Deduplicated: {afscme_olms[0]:,}" if afscme_olms else "OLMS: Not found")

# 990 estimate
cur.execute("""
    SELECT SUM(estimated_members), SUM(dues_revenue)
    FROM form_990_estimates 
    WHERE org_type LIKE 'AFSCME%'
""")
r = cur.fetchone()
print(f"990 Estimated: {r[0]:,} (from ${r[1]:,.0f} dues revenue)" if r[0] else "990: Not found")

# AFSCME claims
print(f"Published claim: ~1,400,000")

print("\n" + "=" * 90)
print("SEIU CROSS-VALIDATION")
print("=" * 90)

# OLMS deduplicated - need to find SEIU
cur.execute("""
    SELECT aff_abbr, total_counted FROM v_dedup_summary_by_affiliation 
    WHERE aff_abbr IN ('SEIU', 'SERVICE')
""")
seiu_results = cur.fetchall()
for r in seiu_results:
    print(f"OLMS {r[0]}: {r[1]:,}")

# 990 estimate
cur.execute("""
    SELECT SUM(estimated_members), SUM(dues_revenue)
    FROM form_990_estimates 
    WHERE org_type LIKE 'SEIU%'
""")
r = cur.fetchone()
print(f"990 Estimated: {r[0]:,} (from ${r[1]:,.0f} dues revenue)" if r[0] else "990: Not found")
print(f"Published claim: ~2,000,000")

print("\n" + "=" * 90)
print("NEA (Pure Public Sector - 990 is PRIMARY source)")
print("=" * 90)

cur.execute("""
    SELECT aff_abbr, total_counted FROM v_dedup_summary_by_affiliation 
    WHERE aff_abbr = 'NEA'
""")
nea_olms = cur.fetchone()
print(f"OLMS Deduplicated: {nea_olms[1]:,}" if nea_olms else "OLMS: Not found")

cur.execute("""
    SELECT SUM(estimated_members), SUM(dues_revenue)
    FROM form_990_estimates 
    WHERE org_type LIKE 'NEA%' OR org_type LIKE 'AFT_NEA%'
""")
r = cur.fetchone()
print(f"990 Estimated: {r[0]:,}" if r[0] else "990: Not found")
print(f"Published claim: ~2,900,000 (NEA) + dual affiliates")

# Show what 990 records we have
print("\n" + "=" * 90)
print("FORM 990 ESTIMATES - SOURCE CHECK")
print("=" * 90)
print("NOTE: Need to verify which dues_revenue values are REAL vs FABRICATED")
print()

cur.execute("""
    SELECT organization_name, dues_revenue, dues_rate_used, estimated_members, 
           dues_rate_source
    FROM form_990_estimates
    WHERE org_type IN ('NEA_NATIONAL', 'AFSCME_NATIONAL', 'SEIU_NATIONAL')
    ORDER BY estimated_members DESC
""")

for r in cur.fetchall():
    name, dues, rate, members, source = r
    print(f"{name[:40]:<42}")
    print(f"  Dues Revenue: ${float(dues):>15,.0f}")
    print(f"  Rate Used:    ${float(rate):>8.2f}/member")
    print(f"  Est Members:  {members:>12,}")
    print(f"  Source: {source[:70]}")
    print()

conn.close()
