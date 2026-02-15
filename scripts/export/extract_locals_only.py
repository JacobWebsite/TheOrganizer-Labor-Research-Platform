import os
from db_config import get_connection
"""
Extract ONLY locals and councils (not federations/internationals that aggregate)
Plus add Form 990 public sector organizations
"""
import psycopg2
import csv

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("UNION LOCALS AND COUNCILS ONLY (No Aggregating Parent Orgs)")
print("=" * 80)

# Get LOCAL level unions only from 2024
print("\n1. Extracting LOCAL hierarchy level organizations...")

cur.execute("""
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
        h.hierarchy_level,
        CASE 
            WHEN l.aff_abbr IN ('AFGE', 'NFFE', 'NTEU') THEN 'FEDERAL'
            WHEN l.aff_abbr IN ('NEA', 'AFT') THEN 'PUBLIC_EDUCATION'
            WHEN l.aff_abbr IN ('IAFF', 'NFOP', 'PBA') THEN 'PUBLIC_SAFETY'
            WHEN l.aff_abbr IN ('APWU', 'NALC', 'NPMHU', 'RLCA') THEN 'POSTAL'
            WHEN l.aff_abbr IN ('AFSCME') THEN 'PUBLIC_MIXED'
            WHEN l.aff_abbr IN ('SEIU') THEN 'PRIVATE_MIXED'
            ELSE 'PRIVATE'
        END as sector,
        'OLMS_LM' as data_source
    FROM lm_data l
    JOIN union_hierarchy h ON l.f_num = h.f_num
    WHERE l.yr_covered = 2024
      AND h.hierarchy_level IN ('LOCAL', 'INTERMEDIATE')
    ORDER BY l.members DESC NULLS LAST
""")

olms_rows = cur.fetchall()
print(f"   Found {len(olms_rows):,} local/intermediate level unions from OLMS")

# Get Form 990 public sector data
print("\n2. Adding Form 990 public sector organizations...")

cur.execute("""
    SELECT 
        ein as file_number,
        organization_name as union_name,
        NULL as unit_name,
        org_type as affiliation,
        NULL as desig_name,
        NULL as desig_num,
        estimated_members as members,
        state,
        city,
        '990' as form_type,
        dues_revenue as ttl_receipts,
        total_assets as ttl_assets,
        NULL as ttl_disbursements,
        CASE 
            WHEN org_type LIKE '%LOCAL%' THEN 'LOCAL'
            WHEN org_type LIKE '%COUNCIL%' THEN 'INTERMEDIATE'
            WHEN org_type LIKE '%STATE%' THEN 'STATE_AFFILIATE'
            ELSE 'NATIONAL'
        END as hierarchy_level,
        'PUBLIC' as sector,
        'FORM_990' as data_source
    FROM form_990_estimates
    ORDER BY estimated_members DESC
""")

f990_rows = cur.fetchall()
print(f"   Found {len(f990_rows):,} Form 990 organizations")

# Get Federal FLRA bargaining units
print("\n3. Adding Federal FLRA bargaining units...")

cur.execute("""
    SELECT 
        unit_id::text as file_number,
        COALESCE(union_name, agency_name) as union_name,
        unit_description as unit_name,
        COALESCE(affiliation, union_acronym, 'FEDERAL') as affiliation,
        agency_name as desig_name,
        local_number as desig_num,
        total_in_unit as members,
        NULL as state,
        NULL as city,
        'FLRA' as form_type,
        NULL as ttl_receipts,
        NULL as ttl_assets,
        NULL as ttl_disbursements,
        'FEDERAL_UNIT' as hierarchy_level,
        'FEDERAL' as sector,
        'FLRA' as data_source
    FROM federal_bargaining_units
    WHERE status = 'Active' OR status IS NULL
    ORDER BY total_in_unit DESC NULLS LAST
""")

flra_rows = cur.fetchall()
print(f"   Found {len(flra_rows):,} federal bargaining units")

# Combine all
all_rows = list(olms_rows) + list(f990_rows) + list(flra_rows)

# Write to CSV
output_file = r'C:\Users\jakew\Downloads\labor-data-project\union_locals_councils_COMPLETE.csv'
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow([
        'file_number', 'union_name', 'unit_name', 'affiliation', 
        'desig_name', 'desig_num', 'members', 'state', 'city',
        'form_type', 'receipts', 'assets', 'disbursements',
        'hierarchy_level', 'sector', 'data_source'
    ])
    writer.writerows(all_rows)

print(f"\n4. Written {len(all_rows):,} total records to:")
print(f"   {output_file}")

# Summary statistics
print("\n" + "=" * 80)
print("SUMMARY STATISTICS")
print("=" * 80)

# By data source
print("\n5. By Data Source:")
print(f"   {'Source':<15} {'Organizations':>12} {'Members':>15}")
print("   " + "-" * 45)

cur.execute("""
    SELECT COUNT(*), SUM(members) FROM lm_data l
    JOIN union_hierarchy h ON l.f_num = h.f_num
    WHERE l.yr_covered = 2024 AND h.hierarchy_level IN ('LOCAL', 'INTERMEDIATE')
""")
r = cur.fetchone()
print(f"   {'OLMS Locals':<15} {r[0]:>12,} {r[1] or 0:>15,}")

cur.execute("SELECT COUNT(*), SUM(estimated_members) FROM form_990_estimates")
r = cur.fetchone()
print(f"   {'Form 990':<15} {r[0]:>12,} {r[1] or 0:>15,}")

cur.execute("SELECT COUNT(*), SUM(total_in_unit) FROM federal_bargaining_units WHERE status = 'Active' OR status IS NULL")
r = cur.fetchone()
print(f"   {'FLRA Federal':<15} {r[0]:>12,} {r[1] or 0:>15,}")

# By sector (OLMS locals only)
print("\n6. OLMS Locals by Sector:")
cur.execute("""
    SELECT 
        CASE 
            WHEN l.aff_abbr IN ('AFGE', 'NFFE', 'NTEU') THEN 'FEDERAL'
            WHEN l.aff_abbr IN ('NEA', 'AFT') THEN 'PUBLIC_EDUCATION'
            WHEN l.aff_abbr IN ('IAFF', 'NFOP', 'PBA') THEN 'PUBLIC_SAFETY'
            WHEN l.aff_abbr IN ('APWU', 'NALC', 'NPMHU', 'RLCA') THEN 'POSTAL'
            WHEN l.aff_abbr IN ('AFSCME') THEN 'PUBLIC_MIXED'
            WHEN l.aff_abbr IN ('SEIU') THEN 'PRIVATE_MIXED'
            ELSE 'PRIVATE'
        END as sector,
        COUNT(*) as orgs,
        SUM(l.members) as members
    FROM lm_data l
    JOIN union_hierarchy h ON l.f_num = h.f_num
    WHERE l.yr_covered = 2024 AND h.hierarchy_level IN ('LOCAL', 'INTERMEDIATE')
    GROUP BY 1 ORDER BY SUM(l.members) DESC NULLS LAST
""")
print(f"   {'Sector':<20} {'Organizations':>12} {'Members':>15}")
print("   " + "-" * 50)
for r in cur.fetchall():
    print(f"   {r[0]:<20} {r[1]:>12,} {r[2] or 0:>15,}")

# Top affiliations among locals
print("\n7. Top 25 Affiliations (OLMS Locals Only):")
cur.execute("""
    SELECT 
        COALESCE(l.aff_abbr, 'INDEPENDENT') as affiliation,
        COUNT(*) as orgs,
        SUM(l.members) as members
    FROM lm_data l
    JOIN union_hierarchy h ON l.f_num = h.f_num
    WHERE l.yr_covered = 2024 AND h.hierarchy_level IN ('LOCAL', 'INTERMEDIATE')
    GROUP BY l.aff_abbr
    ORDER BY COUNT(*) DESC
    LIMIT 25
""")
print(f"   {'Affiliation':<15} {'Locals':>10} {'Members':>15}")
print("   " + "-" * 45)
for r in cur.fetchall():
    print(f"   {r[0]:<15} {r[1]:>10,} {r[2] or 0:>15,}")

# Top states
print("\n8. Top 15 States (OLMS Locals Only):")
cur.execute("""
    SELECT 
        l.state,
        COUNT(*) as orgs,
        SUM(l.members) as members
    FROM lm_data l
    JOIN union_hierarchy h ON l.f_num = h.f_num
    WHERE l.yr_covered = 2024 
      AND h.hierarchy_level IN ('LOCAL', 'INTERMEDIATE')
      AND l.state IS NOT NULL AND LENGTH(l.state) = 2
    GROUP BY l.state
    ORDER BY SUM(l.members) DESC NULLS LAST
    LIMIT 15
""")
print(f"   {'State':<8} {'Locals':>10} {'Members':>15}")
print("   " + "-" * 35)
for r in cur.fetchall():
    print(f"   {r[0]:<8} {r[1]:>10,} {r[2] or 0:>15,}")

conn.close()
print("\n" + "=" * 80)
print("EXPORT COMPLETE")
print("=" * 80)
