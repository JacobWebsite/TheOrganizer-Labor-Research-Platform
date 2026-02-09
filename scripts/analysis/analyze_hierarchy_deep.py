"""
Deep dive into union hierarchy and double-counting patterns
"""

import psycopg2
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

print("="*70)
print("UNION HIERARCHY DEEP DIVE")
print("="*70)

# 1. Identify federations (AFL-CIO, CTW, etc.)
print("\n1. FEDERATIONS (Organizations of unions)")
print("-"*60)

cursor.execute("""
    SELECT f_num, union_name, members, ttl_assets, aff_abbr
    FROM lm_data
    WHERE yr_covered = 2024
    AND (
        union_name ILIKE '%AFL-CIO%' 
        OR union_name ILIKE '%federation%'
        OR union_name ILIKE '%change to win%'
        OR union_name ILIKE '%strategic organizing%'
        OR union_name ILIKE '% dept %'
        OR union_name ILIKE '%trades dept%'
        OR f_num IN ('106', '385', '387')  -- Known federations
    )
    ORDER BY members DESC
    LIMIT 15
""")
print(f"{'f_num':<10} {'Members':>12} {'Affiliation':<10} {'Name':<45}")
fed_total = 0
for row in cursor.fetchall():
    name = (row[1] or '')[:45]
    print(f"{row[0]:<10} {row[2] or 0:>12,} {row[4] or '':<10} {name}")
    fed_total += row[2] or 0
print(f"\nTotal federation-reported members: {fed_total:,}")

# 2. Look at designation patterns (desig_num indicates local structure)
print("\n2. DESIGNATION NUMBER PATTERNS")
print("-"*60)
print("Unions with designation numbers are typically locals/subunits")

cursor.execute("""
    SELECT 
        CASE 
            WHEN desig_num IS NOT NULL AND desig_num != '' THEN 'Has Designation'
            ELSE 'No Designation'
        END as has_desig,
        COUNT(*) as cnt,
        SUM(members) as total_members,
        AVG(members) as avg_members
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY has_desig
""")
for row in cursor.fetchall():
    print(f"{row[0]}: {row[1]:,} unions, {row[2] or 0:,} members (avg: {row[3] or 0:,.0f})")

# 3. Analyze a specific affiliation's hierarchy (Teamsters)
print("\n3. TEAMSTERS (IBT) HIERARCHY ANALYSIS")
print("-"*60)

cursor.execute("""
    SELECT 
        f_num, union_name, desig_name, desig_num, members, 
        city, state, ttl_assets
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'IBT'
    ORDER BY members DESC
    LIMIT 20
""")
print(f"{'f_num':<10} {'Desig#':<8} {'Members':>10} {'State':<5} {'Name/Designation':<40}")
for row in cursor.fetchall():
    desig = row[3] or ''
    name = (row[2] or row[1] or '')[:40]
    print(f"{row[0]:<10} {str(desig):<8} {row[4] or 0:>10,} {row[6] or '':<5} {name}")

# Count IBT hierarchy levels
cursor.execute("""
    SELECT 
        CASE 
            WHEN union_name ILIKE '%joint council%' OR union_name ILIKE '%jc %' THEN 'Joint Council'
            WHEN union_name ILIKE '%conference%' THEN 'Conference'
            WHEN desig_num IS NOT NULL AND desig_num != '' AND CAST(desig_num AS INTEGER) < 1000 THEN 'Local (<1000)'
            WHEN desig_num IS NOT NULL AND desig_num != '' THEN 'Local (1000+)'
            ELSE 'National/Other'
        END as level,
        COUNT(*) as cnt,
        SUM(members) as total_members
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'IBT'
    GROUP BY level
    ORDER BY total_members DESC
""")
print("\nIBT by Organization Level:")
ibt_total = 0
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} orgs, {row[2] or 0:,} members")
    ibt_total += row[2] or 0
print(f"  TOTAL (with double-counting): {ibt_total:,}")
print(f"  Actual IBT membership (~): 1,300,000")

# 4. Check if locals' members sum to parent's reported total
print("\n4. LOCALS VS PARENT MEMBERSHIP (AFT Example)")
print("-"*60)

cursor.execute("""
    SELECT f_num, union_name, desig_num, members, state
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'AFT'
    ORDER BY members DESC
    LIMIT 5
""")
print("Top AFT organizations:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[3] or 0:,} - {row[1][:50]}")

cursor.execute("""
    SELECT 
        CASE WHEN desig_num IS NOT NULL AND desig_num != '' THEN 'Local' ELSE 'National/Other' END as level,
        COUNT(*) as cnt,
        SUM(members) as total
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'AFT'
    GROUP BY level
""")
print("\nAFT Hierarchy:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} orgs, {row[2] or 0:,} members")

# 5. Look at form types vs hierarchy
print("\n5. FORM TYPE VS ORGANIZATION SIZE")
print("-"*60)

cursor.execute("""
    SELECT 
        form_type,
        CASE 
            WHEN members > 100000 THEN '>100K'
            WHEN members > 10000 THEN '10K-100K'
            WHEN members > 1000 THEN '1K-10K'
            WHEN members > 100 THEN '100-1K'
            ELSE '<100'
        END as size_bucket,
        COUNT(*) as cnt
    FROM lm_data
    WHERE yr_covered = 2024 AND form_type != 'LM-5'
    GROUP BY form_type, size_bucket
    ORDER BY form_type, 
        CASE size_bucket 
            WHEN '>100K' THEN 1 
            WHEN '10K-100K' THEN 2 
            WHEN '1K-10K' THEN 3 
            WHEN '100-1K' THEN 4 
            ELSE 5 
        END
""")
print(f"{'Form':<8} {'Size Bucket':<12} {'Count':>8}")
for row in cursor.fetchall():
    print(f"{row[0]:<8} {row[1]:<12} {row[2]:>8,}")

# 6. Identify "root" organizations (nationals with no parent designation)
print("\n6. IDENTIFYING ROOT ORGANIZATIONS")
print("-"*60)

cursor.execute("""
    WITH large_orgs AS (
        SELECT DISTINCT aff_abbr
        FROM lm_data
        WHERE yr_covered = 2024 AND members > 500000
    )
    SELECT 
        l.aff_abbr,
        COUNT(*) as total_filings,
        COUNT(CASE WHEN l.members > 100000 THEN 1 END) as very_large,
        MAX(l.members) as max_members,
        SUM(l.members) as sum_all
    FROM lm_data l
    JOIN large_orgs lo ON l.aff_abbr = lo.aff_abbr
    WHERE l.yr_covered = 2024
    GROUP BY l.aff_abbr
    ORDER BY max_members DESC
""")
print(f"{'Affil':<10} {'Filings':>8} {'>100K':>8} {'Max Single':>12} {'Sum All':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<10} {row[1]:>8,} {row[2]:>8,} {row[3] or 0:>12,} {row[4] or 0:>15,}")

# 7. Estimate deduplicated membership
print("\n7. ESTIMATED DEDUPLICATED MEMBERSHIP")
print("-"*60)

# Method: Count only locals (entities with designation numbers) 
# plus independents without clear affiliation
cursor.execute("""
    SELECT 
        CASE 
            WHEN aff_abbr IN ('AFLCIO', 'SOC', 'TTD') THEN 'Federation (exclude)'
            WHEN desig_num IS NOT NULL AND desig_num != '' THEN 'Local (count)'
            WHEN members > 500000 THEN 'Large Parent (exclude)'
            ELSE 'Independent/Unclear (count)'
        END as category,
        COUNT(*) as cnt,
        SUM(members) as total
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY category
    ORDER BY total DESC
""")
print(f"{'Category':<30} {'Count':>8} {'Members':>15}")
estimated_total = 0
for row in cursor.fetchall():
    print(f"{row[0]:<30} {row[1]:>8,} {row[2] or 0:>15,}")
    if 'count' in row[0].lower():
        estimated_total += row[2] or 0

print(f"\nEstimated deduplicated total (rough): {estimated_total:,}")
print(f"BLS reported union membership (2024): ~14,300,000")
print(f"Difference: {estimated_total - 14300000:,}")

cursor.close()
conn.close()

print("\n" + "="*70)
