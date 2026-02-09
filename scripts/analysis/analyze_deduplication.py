"""
Continue hierarchy analysis - estimate deduplicated membership
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
print("DEDUPLICATION STRATEGY ANALYSIS")
print("="*70)

# 1. Understand designation patterns better
print("\n1. DESIGNATION NAME PATTERNS (desig_name field)")
print("-"*60)

cursor.execute("""
    SELECT 
        desig_name,
        COUNT(*) as cnt,
        SUM(members) as total_members
    FROM lm_data
    WHERE yr_covered = 2024 AND desig_name IS NOT NULL AND desig_name != ''
    GROUP BY desig_name
    ORDER BY cnt DESC
    LIMIT 20
""")
print(f"{'Desig Name':<15} {'Count':>10} {'Members':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<15} {row[1]:>10,} {row[2] or 0:>15,}")

# 2. Identify organization types by desig_name
print("\n2. ORGANIZATION TYPE BY DESIGNATION NAME")
print("-"*60)

cursor.execute("""
    SELECT 
        CASE 
            WHEN desig_name IN ('LU', 'LOCAL', 'LG', 'L', 'LOC') THEN 'Local Union'
            WHEN desig_name IN ('JC', 'DC', 'JATC', 'JAC') THEN 'Joint/District Council'
            WHEN desig_name IN ('DIV', 'DIST', 'BR', 'BRANCH') THEN 'Division/Branch'
            WHEN desig_name IN ('NHQ', 'HQ', 'INT', 'NATL', 'GEB') THEN 'National HQ'
            WHEN desig_name IN ('CONF', 'COUNCIL', 'STATE') THEN 'Conference/State'
            WHEN desig_name IS NULL OR desig_name = '' THEN 'No Designation'
            ELSE 'Other'
        END as org_type,
        COUNT(*) as cnt,
        SUM(members) as total_members,
        AVG(members) as avg_members
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY org_type
    ORDER BY total_members DESC
""")
print(f"{'Org Type':<25} {'Count':>8} {'Total Members':>15} {'Avg':>12}")
for row in cursor.fetchall():
    print(f"{row[0]:<25} {row[1]:>8,} {row[2] or 0:>15,} {row[3] or 0:>12,.0f}")

# 3. Test: Count only "LU" type designations
print("\n3. COUNTING ONLY LOCAL UNIONS (LU designations)")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as local_count,
        SUM(members) as local_members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND desig_name IN ('LU', 'LOCAL', 'LG', 'L', 'LOC')
    GROUP BY aff_abbr
    ORDER BY local_members DESC
    LIMIT 15
""")
print(f"{'Affiliation':<12} {'Locals':>8} {'Members':>15}")
lu_total = 0
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>8,} {row[2] or 0:>15,}")
    lu_total += row[2] or 0
print(f"\nTotal from Local Unions only: {lu_total:,}")

# 4. What about organizations WITHOUT designation?
print("\n4. ORGANIZATIONS WITHOUT DESIGNATION (potential nationals)")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as cnt,
        SUM(members) as total_members,
        MAX(members) as max_members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND (desig_name IS NULL OR desig_name = '')
    GROUP BY aff_abbr
    ORDER BY total_members DESC
    LIMIT 15
""")
print(f"{'Affiliation':<12} {'Count':>8} {'Total':>15} {'Max Single':>12}")
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>8,} {row[2] or 0:>15,} {row[3] or 0:>12,}")

# 5. Look at intermediate bodies specifically
print("\n5. INTERMEDIATE BODIES (Joint Councils, Districts)")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr, f_num, union_name, desig_name, desig_num, members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND desig_name IN ('JC', 'DC', 'JATC', 'JAC', 'CONF', 'COUNCIL')
    ORDER BY members DESC
    LIMIT 15
""")
print(f"{'Affil':<8} {'f_num':<10} {'Desig':<6} {'Members':>10} {'Name':<35}")
jc_total = 0
for row in cursor.fetchall():
    name = (row[2] or '')[:35]
    print(f"{row[0]:<8} {row[1]:<10} {row[3]:<6} {row[5] or 0:>10,} {name}")
    jc_total += row[5] or 0

cursor.execute("""
    SELECT COUNT(*), SUM(members)
    FROM lm_data
    WHERE yr_covered = 2024 
    AND desig_name IN ('JC', 'DC', 'JATC', 'JAC', 'CONF', 'COUNCIL')
""")
row = cursor.fetchone()
print(f"\nTotal intermediate bodies: {row[0]:,} with {row[1] or 0:,} reported members")

# 6. Strategy: Deduplicate by counting lowest level only
print("\n6. DEDUPLICATION ESTIMATE")
print("-"*60)

# For unions with clear hierarchy (IBT, IBEW, LIUNA, etc.), count only locals
# For others, need different approach

cursor.execute("""
    WITH classified AS (
        SELECT 
            *,
            CASE 
                -- Federations to exclude
                WHEN aff_abbr IN ('AFLCIO', 'SOC', 'TTD') THEN 'federation'
                
                -- Clear locals
                WHEN desig_name IN ('LU', 'LOCAL', 'LG', 'L', 'LOC') THEN 'local'
                
                -- Intermediate bodies to exclude  
                WHEN desig_name IN ('JC', 'DC', 'JATC', 'JAC', 'CONF', 'COUNCIL', 'STATE') THEN 'intermediate'
                
                -- National HQ to exclude
                WHEN desig_name IN ('NHQ', 'HQ', 'INT', 'NATL', 'GEB') THEN 'national'
                
                -- Division/Branch - these are often direct-member units
                WHEN desig_name IN ('DIV', 'DIST', 'BR', 'BRANCH') THEN 'local'
                
                -- No designation - could be either
                WHEN desig_name IS NULL OR desig_name = '' THEN 'unclassified'
                
                ELSE 'other'
            END as org_level
        FROM lm_data
        WHERE yr_covered = 2024
    )
    SELECT 
        org_level,
        COUNT(*) as cnt,
        SUM(members) as total_members
    FROM classified
    GROUP BY org_level
    ORDER BY total_members DESC
""")
print(f"{'Level':<20} {'Count':>8} {'Members':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<20} {row[1]:>8,} {row[2] or 0:>15,}")

# 7. Handle unclassified - split by size
print("\n7. UNCLASSIFIED ORGANIZATIONS BY SIZE")
print("-"*60)

cursor.execute("""
    SELECT 
        CASE 
            WHEN members > 100000 THEN 'Very Large (>100K) - likely national'
            WHEN members > 10000 THEN 'Large (10K-100K)'
            WHEN members > 1000 THEN 'Medium (1K-10K)'
            ELSE 'Small (<1K) - likely local'
        END as size_cat,
        COUNT(*) as cnt,
        SUM(members) as total
    FROM lm_data
    WHERE yr_covered = 2024
    AND (desig_name IS NULL OR desig_name = '')
    GROUP BY size_cat
    ORDER BY total DESC
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,} orgs, {row[2] or 0:,} members")

# 8. Final estimate
print("\n8. FINAL DEDUPLICATION ESTIMATE")
print("-"*60)

cursor.execute("""
    WITH classified AS (
        SELECT 
            members,
            CASE 
                -- Federations to exclude
                WHEN aff_abbr IN ('AFLCIO', 'SOC', 'TTD') THEN 'exclude'
                
                -- Clear locals - COUNT
                WHEN desig_name IN ('LU', 'LOCAL', 'LG', 'L', 'LOC', 'DIV', 'DIST', 'BR', 'BRANCH') THEN 'count'
                
                -- Intermediate/national - exclude  
                WHEN desig_name IN ('JC', 'DC', 'JATC', 'JAC', 'CONF', 'COUNCIL', 'STATE', 'NHQ', 'HQ', 'INT', 'NATL', 'GEB') THEN 'exclude'
                
                -- Unclassified: count if small (<10K), exclude if large
                WHEN (desig_name IS NULL OR desig_name = '') AND members <= 10000 THEN 'count'
                WHEN (desig_name IS NULL OR desig_name = '') AND members > 10000 THEN 'exclude'
                
                ELSE 'count'
            END as action
        FROM lm_data
        WHERE yr_covered = 2024
    )
    SELECT 
        action,
        COUNT(*) as cnt,
        SUM(members) as total
    FROM classified
    GROUP BY action
""")
count_total = 0
exclude_total = 0
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,} orgs, {row[2] or 0:,} members")
    if row[0] == 'count':
        count_total = row[2] or 0
    else:
        exclude_total = row[2] or 0

print(f"\n  ESTIMATED UNIQUE MEMBERS: {count_total:,}")
print(f"  BLS Reported (2024):      ~14,300,000")
print(f"  Difference:               {count_total - 14300000:+,}")

cursor.close()
conn.close()

print("\n" + "="*70)
