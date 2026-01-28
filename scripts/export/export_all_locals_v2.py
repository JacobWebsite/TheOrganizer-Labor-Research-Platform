"""
Export COMPLETE list of all union locals and councils with membership
Includes both OLMS (private/mixed) and Form 990 (public sector) data
"""
import psycopg2
import csv

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

print("=" * 90)
print("COMPLETE UNION LOCALS AND COUNCILS EXPORT")
print("=" * 90)

# Part 1: OLMS Data (from v_union_members_counted - deduplicated)
print("\n### Part 1: OLMS LM Data (Private/Mixed Sector) ###")

cur.execute("""
    SELECT 
        v.f_num,
        v.union_name,
        v.aff_abbr,
        v.hierarchy_level,
        COALESCE(v.sector, 'PRIVATE') as sector,
        v.state,
        v.city,
        v.members,
        v.count_members,
        v.ttl_receipts,
        v.ttl_assets,
        v.ttl_disbursements,
        v.f7_employer_count,
        v.f7_total_workers,
        'OLMS_LM' as data_source
    FROM v_union_members_counted v
    WHERE v.hierarchy_level IN ('local', 'intermediate', 'specialized', 'other')
       OR (v.hierarchy_level = 'national' AND v.count_members = TRUE)
    ORDER BY v.members DESC NULLS LAST
""")

olms_rows = cur.fetchall()
print(f"  Found {len(olms_rows):,} OLMS local/council unions")

# Get column names
olms_cols = [desc[0] for desc in cur.description]

# Summary by hierarchy level
cur.execute("""
    SELECT 
        v.hierarchy_level,
        COUNT(*) as orgs,
        SUM(v.members) as total_members,
        SUM(CASE WHEN v.count_members THEN v.members ELSE 0 END) as counted_members
    FROM v_union_members_counted v
    WHERE v.hierarchy_level IN ('local', 'intermediate', 'specialized', 'other')
       OR (v.hierarchy_level = 'national' AND v.count_members = TRUE)
    GROUP BY v.hierarchy_level
    ORDER BY total_members DESC NULLS LAST
""")

print(f"\n  {'Level':<15} {'Orgs':>8} {'Total Members':>15} {'Counted':>15}")
print("  " + "-" * 55)
for r in cur.fetchall():
    level, orgs, members, counted = r
    print(f"  {level:<15} {orgs:>8,} {members or 0:>15,} {counted or 0:>15,}")

# Part 2: Form 990 Public Sector Estimates
print("\n### Part 2: Form 990 Data (Public Sector Estimates) ###")

cur.execute("""
    SELECT 
        ein as f_num,
        organization_name as union_name,
        org_type as aff_abbr,
        CASE 
            WHEN org_type LIKE '%LOCAL%' THEN 'local'
            WHEN org_type LIKE '%COUNCIL%' THEN 'intermediate'
            WHEN org_type LIKE '%STATE%' THEN 'intermediate'
            WHEN org_type LIKE '%NATIONAL%' THEN 'national'
            ELSE 'other'
        END as hierarchy_level,
        'PUBLIC' as sector,
        state,
        city,
        estimated_members as members,
        TRUE as count_members,
        dues_revenue as ttl_receipts,
        total_assets as ttl_assets,
        NULL as ttl_disbursements,
        NULL as f7_employer_count,
        NULL as f7_total_workers,
        '990_EST' as data_source
    FROM form_990_estimates
    ORDER BY estimated_members DESC
""")

f990_rows = cur.fetchall()
print(f"  Found {len(f990_rows):,} Form 990 public sector organizations")

# Summary of 990 data
cur.execute("""
    SELECT 
        org_type,
        COUNT(*) as orgs,
        SUM(estimated_members) as members
    FROM form_990_estimates
    GROUP BY org_type
    ORDER BY SUM(estimated_members) DESC
""")

print(f"\n  {'Org Type':<25} {'Orgs':>6} {'Members':>12}")
print("  " + "-" * 45)
for r in cur.fetchall():
    print(f"  {r[0]:<25} {r[1]:>6} {r[2]:>12,}")

# Part 3: Federal Sector (FLRA data if available)
print("\n### Part 3: Federal Sector (FLRA Bargaining Units) ###")

cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = 'federal_bargaining_units'
    )
""")
has_flra = cur.fetchone()[0]

flra_rows = []
if has_flra:
    cur.execute("""
        SELECT 
            bu_id as f_num,
            union_name,
            COALESCE(affiliation, 'FEDERAL') as aff_abbr,
            'federal_unit' as hierarchy_level,
            'FEDERAL' as sector,
            NULL as state,
            NULL as city,
            employees as members,
            TRUE as count_members,
            NULL as ttl_receipts,
            NULL as ttl_assets,
            NULL as ttl_disbursements,
            NULL as f7_employer_count,
            NULL as f7_total_workers,
            'FLRA' as data_source
        FROM federal_bargaining_units
        ORDER BY employees DESC NULLS LAST
    """)
    flra_rows = cur.fetchall()
    print(f"  Found {len(flra_rows):,} federal bargaining units")
    
    # Summary
    cur.execute("""
        SELECT 
            COALESCE(affiliation, 'Other'),
            COUNT(*),
            SUM(employees)
        FROM federal_bargaining_units
        GROUP BY affiliation
        ORDER BY SUM(employees) DESC NULLS LAST
        LIMIT 10
    """)
    print(f"\n  {'Affiliation':<20} {'Units':>8} {'Employees':>12}")
    print("  " + "-" * 42)
    for r in cur.fetchall():
        print(f"  {r[0] or 'Unknown':<20} {r[1]:>8} {r[2] or 0:>12,}")
else:
    print("  Federal bargaining units table not found")

# Combine all data and write to CSV
print("\n" + "=" * 90)
print("WRITING COMBINED EXPORT")
print("=" * 90)

all_rows = list(olms_rows) + list(f990_rows) + list(flra_rows)

output_file = r'C:\Users\jakew\Downloads\labor-data-project\all_union_locals_councils_complete.csv'
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow([
        'file_number', 'union_name', 'affiliation', 'hierarchy_level', 
        'sector', 'state', 'city', 'members', 'counted_in_total',
        'receipts', 'assets', 'disbursements', 
        'f7_employer_count', 'f7_total_workers', 'data_source'
    ])
    writer.writerows(all_rows)

print(f"\nWritten {len(all_rows):,} total records to:")
print(f"  {output_file}")

# Grand totals
print("\n### GRAND TOTALS ###")
print(f"  OLMS Locals/Councils:    {len(olms_rows):>8,} orgs")
print(f"  Form 990 Public Sector:  {len(f990_rows):>8,} orgs")
print(f"  Federal (FLRA):          {len(flra_rows):>8,} units")
print(f"  {'TOTAL':>25}: {len(all_rows):>8,} records")

# Calculate total members
cur.execute("""
    WITH olms AS (
        SELECT SUM(members) as m FROM v_union_members_counted
        WHERE hierarchy_level IN ('local', 'intermediate', 'specialized', 'other')
           OR (hierarchy_level = 'national' AND count_members = TRUE)
    ),
    f990 AS (
        SELECT SUM(estimated_members) as m FROM form_990_estimates
    )
    SELECT 
        (SELECT m FROM olms) as olms_members,
        (SELECT m FROM f990) as f990_members
""")
r = cur.fetchone()
olms_total = r[0] or 0
f990_total = r[1] or 0

if has_flra:
    cur.execute("SELECT SUM(employees) FROM federal_bargaining_units")
    flra_total = cur.fetchone()[0] or 0
else:
    flra_total = 0

print(f"\n### TOTAL MEMBERSHIP ###")
print(f"  OLMS (deduplicated):     {olms_total:>12,}")
print(f"  Form 990 Public:         {f990_total:>12,}")
print(f"  Federal (FLRA):          {flra_total:>12,}")
print(f"  {'COMBINED':>22}: {olms_total + f990_total + flra_total:>12,}")
print(f"\n  Note: Some overlap exists between OLMS and 990 for mixed-sector unions")

conn.close()
print("\nExport complete!")
