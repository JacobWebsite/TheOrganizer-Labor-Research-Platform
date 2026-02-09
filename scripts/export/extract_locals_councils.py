import os
"""
Extract complete list of union locals and councils with membership
Covers both public and private sectors from OLMS data
"""
import psycopg2
import csv

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

print("=" * 80)
print("EXTRACTING COMPLETE UNION LOCAL/COUNCIL LIST")
print("=" * 80)

# Get all locals and councils from 2024 LM data with hierarchy info
print("\n1. Extracting all locals and councils from 2024 data...")

query = """
SELECT 
    l.f_num as file_number,
    l.union_name,
    l.unit_name,
    l.aff_abbr as affiliation,
    l.desig_name,
    l.desig_num,
    l.members,
    l.state,
    l.city,
    l.form_type,
    l.ttl_receipts,
    l.ttl_assets,
    l.ttl_disbursements,
    COALESCE(h.hierarchy_level, 
        CASE 
            WHEN l.form_type = 'LM-2' THEN 'UNKNOWN_LM2'
            WHEN l.form_type = 'LM-3' THEN 'UNKNOWN_LM3'
            WHEN l.form_type = 'LM-4' THEN 'UNKNOWN_LM4'
            ELSE 'UNKNOWN'
        END
    ) as hierarchy_level,
    COALESCE(h.count_members, FALSE) as counted_in_dedup,
    CASE 
        WHEN l.aff_abbr IN ('AFGE', 'NFFE', 'NTEU') THEN 'FEDERAL'
        WHEN l.aff_abbr IN ('NEA', 'AFT') THEN 'PUBLIC_EDUCATION'
        WHEN l.aff_abbr IN ('IAFF', 'NFOP', 'PBA') THEN 'PUBLIC_SAFETY'
        WHEN l.aff_abbr IN ('APWU', 'NALC', 'NPMHU', 'RLCA') THEN 'POSTAL'
        WHEN l.aff_abbr IN ('AFSCME') THEN 'PUBLIC_MIXED'
        WHEN l.aff_abbr IN ('SEIU') THEN 'PRIVATE_MIXED'
        ELSE 'PRIVATE'
    END as sector_estimate
FROM lm_data l
LEFT JOIN union_hierarchy h ON l.f_num = h.f_num
WHERE l.yr_covered = 2024
ORDER BY l.members DESC NULLS LAST
"""

cur.execute(query)
rows = cur.fetchall()
cols = [desc[0] for desc in cur.description]

print(f"   Found {len(rows):,} total LM filings for 2024")

# Write to CSV
output_file = r'C:\Users\jakew\Downloads\labor-data-project\union_locals_councils_2024.csv'
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(cols)
    writer.writerows(rows)

print(f"\n2. Written to: {output_file}")

# Summary by hierarchy level
print("\n3. By Hierarchy Level:")
cur.execute("""
    SELECT 
        COALESCE(h.hierarchy_level, 'UNCLASSIFIED') as level,
        COUNT(*) as orgs,
        SUM(l.members) as total_members
    FROM lm_data l
    LEFT JOIN union_hierarchy h ON l.f_num = h.f_num
    WHERE l.yr_covered = 2024
    GROUP BY COALESCE(h.hierarchy_level, 'UNCLASSIFIED')
    ORDER BY SUM(l.members) DESC NULLS LAST
""")
print(f"   {'Level':<20} {'Organizations':>12} {'Members':>15}")
print("   " + "-" * 50)
for r in cur.fetchall():
    print(f"   {r[0]:<20} {r[1]:>12,} {r[2] or 0:>15,}")

# Summary by form type
print("\n4. By Form Type:")
cur.execute("""
    SELECT form_type, COUNT(*) as orgs, SUM(members) as members
    FROM lm_data WHERE yr_covered = 2024
    GROUP BY form_type ORDER BY SUM(members) DESC NULLS LAST
""")
print(f"   {'Form':<10} {'Organizations':>12} {'Members':>15}")
print("   " + "-" * 40)
for r in cur.fetchall():
    print(f"   {r[0]:<10} {r[1]:>12,} {r[2] or 0:>15,}")

# Summary by sector
print("\n5. By Estimated Sector:")
cur.execute("""
    SELECT 
        CASE 
            WHEN aff_abbr IN ('AFGE', 'NFFE', 'NTEU') THEN 'FEDERAL'
            WHEN aff_abbr IN ('NEA', 'AFT') THEN 'PUBLIC_EDUCATION'
            WHEN aff_abbr IN ('IAFF', 'NFOP', 'PBA') THEN 'PUBLIC_SAFETY'
            WHEN aff_abbr IN ('APWU', 'NALC', 'NPMHU', 'RLCA') THEN 'POSTAL'
            WHEN aff_abbr IN ('AFSCME') THEN 'PUBLIC_MIXED'
            WHEN aff_abbr IN ('SEIU') THEN 'PRIVATE_MIXED'
            ELSE 'PRIVATE'
        END as sector,
        COUNT(*) as orgs,
        SUM(members) as members
    FROM lm_data WHERE yr_covered = 2024
    GROUP BY 1 ORDER BY SUM(members) DESC NULLS LAST
""")
print(f"   {'Sector':<20} {'Organizations':>12} {'Members':>15}")
print("   " + "-" * 50)
for r in cur.fetchall():
    print(f"   {r[0]:<20} {r[1]:>12,} {r[2] or 0:>15,}")

# Top affiliations
print("\n6. Top 30 Affiliations by Membership:")
cur.execute("""
    SELECT 
        COALESCE(aff_abbr, 'INDEPENDENT') as affiliation,
        COUNT(*) as orgs,
        SUM(members) as members
    FROM lm_data WHERE yr_covered = 2024
    GROUP BY aff_abbr
    ORDER BY SUM(members) DESC NULLS LAST
    LIMIT 30
""")
print(f"   {'Affiliation':<15} {'Organizations':>12} {'Members':>15}")
print("   " + "-" * 45)
for r in cur.fetchall():
    print(f"   {r[0]:<15} {r[1]:>12,} {r[2] or 0:>15,}")

# Grand totals
print("\n7. GRAND TOTALS:")
cur.execute("""
    SELECT COUNT(*), SUM(members), COUNT(DISTINCT aff_abbr)
    FROM lm_data WHERE yr_covered = 2024
""")
r = cur.fetchone()
print(f"   Total Organizations:  {r[0]:>12,}")
print(f"   Total Members (RAW):  {r[1]:>12,}")
print(f"   Unique Affiliations:  {r[2]:>12,}")
print(f"\n   Note: Raw member total includes double-counting from hierarchy")
print(f"         Deduplicated total (from v_union_members_counted) is ~14.5M")

conn.close()
print("\n" + "=" * 80)
print("EXTRACTION COMPLETE")
print("=" * 80)
