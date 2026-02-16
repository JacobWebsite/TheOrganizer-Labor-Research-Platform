import os
"""
Export all union locals and councils with membership
Covers both public and private sectors
"""
import psycopg2
import csv
from datetime import datetime

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

print("=" * 80)
print("EXPORTING ALL UNION LOCALS AND COUNCILS")
print("=" * 80)

# First, let's understand what we have
print("\n### Checking available data sources ###")

# Check union_hierarchy for classification
cur.execute("""
    SELECT hierarchy_level, COUNT(*), SUM(members)
    FROM union_hierarchy
    GROUP BY hierarchy_level
    ORDER BY SUM(members) DESC NULLS LAST
""")
print("\nUnion Hierarchy Levels:")
for r in cur.fetchall():
    print(f"  {r[0]:<20}: {r[1]:>6} orgs, {r[2] or 0:>12,} members")

# Check what's in lm_data for 2024
cur.execute("""
    SELECT form_type, COUNT(*), SUM(members)
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY form_type
    ORDER BY SUM(members) DESC NULLS LAST
""")
print("\n2024 LM Filings by Form Type:")
for r in cur.fetchall():
    print(f"  {r[0]:<10}: {r[1]:>6} filings, {r[2] or 0:>12,} members")

print("\n" + "=" * 80)
print("EXPORTING LOCAL AND COUNCIL LEVEL UNIONS")
print("=" * 80)

# Main export query - locals and councils only (not federations or internationals that aggregate)
# Using union_hierarchy to get deduplicated, non-double-counted unions
cur.execute("""
    SELECT 
        uh.f_num,
        uh.union_name,
        uh.aff_abbr,
        uh.hierarchy_level,
        uh.sector,
        uh.state,
        uh.city,
        uh.members,
        uh.count_members,
        lm.form_type,
        lm.ttl_receipts,
        lm.ttl_assets,
        lm.ttl_disbursements,
        lm.yr_covered
    FROM union_hierarchy uh
    LEFT JOIN lm_data lm ON uh.f_num = lm.f_num AND lm.yr_covered = 2024
    WHERE uh.hierarchy_level IN ('local', 'intermediate', 'specialized', 'other')
       OR (uh.hierarchy_level = 'national' AND uh.count_members = TRUE)
    ORDER BY uh.members DESC NULLS LAST
""")

rows = cur.fetchall()
print(f"\nFound {len(rows):,} local/council level unions")

# Write to CSV
output_file = r'C:\Users\jakew\Downloads\labor-data-project\all_union_locals_councils.csv'
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow([
        'file_number', 'union_name', 'affiliation', 'hierarchy_level', 
        'sector', 'state', 'city', 'members', 'counted_in_total',
        'form_type', 'receipts', 'assets', 'disbursements', 'year'
    ])
    writer.writerows(rows)

print(f"Written to: {output_file}")

# Summary stats
cur.execute("""
    SELECT 
        uh.hierarchy_level,
        uh.sector,
        COUNT(*) as orgs,
        SUM(uh.members) as total_members,
        SUM(CASE WHEN uh.count_members THEN uh.members ELSE 0 END) as counted_members
    FROM union_hierarchy uh
    WHERE uh.hierarchy_level IN ('local', 'intermediate', 'specialized', 'other')
       OR (uh.hierarchy_level = 'national' AND uh.count_members = TRUE)
    GROUP BY uh.hierarchy_level, uh.sector
    ORDER BY total_members DESC NULLS LAST
""")

print("\n### Summary by Level and Sector ###")
print(f"{'Level':<15} {'Sector':<10} {'Orgs':>8} {'Total Members':>15} {'Counted':>15}")
print("-" * 70)
total_orgs = 0
total_members = 0
total_counted = 0
for r in cur.fetchall():
    level, sector, orgs, members, counted = r
    members = members or 0
    counted = counted or 0
    print(f"{level:<15} {sector or 'Unknown':<10} {orgs:>8,} {members:>15,} {counted:>15,}")
    total_orgs += orgs
    total_members += members
    total_counted += counted

print("-" * 70)
print(f"{'TOTAL':<15} {'':<10} {total_orgs:>8,} {total_members:>15,} {total_counted:>15,}")

conn.close()
print(f"\nExport complete!")
