import os
"""
Export ALL union locals from raw lm_data (not deduplicated)
This shows the full granular breakdown of locals
"""
import psycopg2
import csv

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

print("=" * 90)
print("ALL UNION LOCALS FROM RAW LM DATA (2024)")
print("=" * 90)

# Get all locals from 2024 LM data
cur.execute("""
    SELECT 
        l.f_num,
        l.union_name,
        l.aff_abbr,
        COALESCE(uh.hierarchy_level, 'UNKNOWN') as hierarchy_level,
        COALESCE(um.sector, 'PRIVATE') as sector,
        l.state,
        l.city,
        l.members,
        COALESCE(uh.count_members, FALSE) as counted_in_dedup,
        l.form_type,
        l.ttl_receipts,
        l.ttl_assets,
        l.ttl_disbursements,
        um.f7_employer_count,
        um.f7_total_workers
    FROM lm_data l
    LEFT JOIN union_hierarchy uh ON l.f_num = uh.f_num
    LEFT JOIN unions_master um ON l.f_num = um.f_num
    WHERE l.yr_covered = 2024
    ORDER BY l.members DESC NULLS LAST
""")

rows = cur.fetchall()
print(f"\nFound {len(rows):,} total LM filings for 2024")

# Write to CSV
output_file = r'C:\Users\jakew\Downloads\labor-data-project\all_lm_filings_2024_raw.csv'
with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow([
        'file_number', 'union_name', 'affiliation', 'hierarchy_level', 
        'sector', 'state', 'city', 'members', 'counted_in_dedup',
        'form_type', 'receipts', 'assets', 'disbursements',
        'f7_employer_count', 'f7_total_workers'
    ])
    writer.writerows(rows)

print(f"Written to: {output_file}")

# Summary by form type
cur.execute("""
    SELECT 
        l.form_type,
        COUNT(*) as filings,
        SUM(l.members) as total_members,
        AVG(l.members)::int as avg_members
    FROM lm_data l
    WHERE l.yr_covered = 2024
    GROUP BY l.form_type
    ORDER BY SUM(l.members) DESC NULLS LAST
""")

print(f"\n### By Form Type ###")
print(f"  {'Form':<10} {'Filings':>10} {'Total Members':>15} {'Avg Members':>12}")
print("  " + "-" * 50)
for r in cur.fetchall():
    print(f"  {r[0]:<10} {r[1]:>10,} {r[2] or 0:>15,} {r[3] or 0:>12,}")

# Summary by hierarchy level
cur.execute("""
    SELECT 
        COALESCE(uh.hierarchy_level, 'UNCLASSIFIED') as level,
        COUNT(*) as filings,
        SUM(l.members) as total_members
    FROM lm_data l
    LEFT JOIN union_hierarchy uh ON l.f_num = uh.f_num
    WHERE l.yr_covered = 2024
    GROUP BY COALESCE(uh.hierarchy_level, 'UNCLASSIFIED')
    ORDER BY SUM(l.members) DESC NULLS LAST
""")

print(f"\n### By Hierarchy Level ###")
print(f"  {'Level':<20} {'Filings':>10} {'Total Members':>15}")
print("  " + "-" * 48)
for r in cur.fetchall():
    print(f"  {r[0]:<20} {r[1]:>10,} {r[2] or 0:>15,}")

# Top affiliations with locals breakdown
cur.execute("""
    SELECT 
        l.aff_abbr,
        COUNT(*) as total_filings,
        COUNT(*) FILTER (WHERE uh.hierarchy_level = 'LOCAL') as local_count,
        COUNT(*) FILTER (WHERE uh.hierarchy_level = 'INTERNATIONAL') as intl_count,
        SUM(l.members) as total_members,
        SUM(l.members) FILTER (WHERE uh.hierarchy_level = 'LOCAL') as local_members
    FROM lm_data l
    LEFT JOIN union_hierarchy uh ON l.f_num = uh.f_num
    WHERE l.yr_covered = 2024
    GROUP BY l.aff_abbr
    ORDER BY COUNT(*) FILTER (WHERE uh.hierarchy_level = 'LOCAL') DESC NULLS LAST
    LIMIT 25
""")

print(f"\n### Top 25 Affiliations by Number of Locals ###")
print(f"  {'Affil':<10} {'Total':>8} {'Locals':>8} {'Intl':>6} {'Total Mbrs':>12} {'Local Mbrs':>12}")
print("  " + "-" * 65)
for r in cur.fetchall():
    aff, total, locals_ct, intl, members, local_m = r
    print(f"  {aff or 'UNAFF':<10} {total:>8,} {locals_ct or 0:>8,} {intl or 0:>6,} {members or 0:>12,} {local_m or 0:>12,}")

# States summary
cur.execute("""
    SELECT 
        l.state,
        COUNT(*) as filings,
        SUM(l.members) as members
    FROM lm_data l
    WHERE l.yr_covered = 2024
      AND l.state IS NOT NULL 
      AND LENGTH(l.state) = 2
    GROUP BY l.state
    ORDER BY SUM(l.members) DESC NULLS LAST
    LIMIT 15
""")

print(f"\n### Top 15 States by Membership ###")
print(f"  {'State':<6} {'Filings':>10} {'Members':>15}")
print("  " + "-" * 35)
for r in cur.fetchall():
    print(f"  {r[0]:<6} {r[1]:>10,} {r[2] or 0:>15,}")

# Grand total
cur.execute("""
    SELECT 
        COUNT(*) as total_filings,
        SUM(members) as total_members,
        COUNT(DISTINCT aff_abbr) as affiliations,
        COUNT(DISTINCT state) as states
    FROM lm_data
    WHERE yr_covered = 2024
""")
r = cur.fetchone()
print(f"\n### GRAND TOTALS (2024 Raw LM Data) ###")
print(f"  Total Filings:      {r[0]:>12,}")
print(f"  Total Members:      {r[1]:>12,} (RAW - includes double-counting)")
print(f"  Unique Affiliations:{r[2]:>12,}")
print(f"  States:             {r[3]:>12,}")

print(f"\n  REMINDER: Raw total ({r[1]:,}) includes hierarchy double-counting.")
print(f"            Deduplicated total is 14,507,549 members.")

conn.close()
print("\nExport complete!")
