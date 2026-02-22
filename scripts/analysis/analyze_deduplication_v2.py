"""
Corrected deduplication analysis using TRIM on desig_name
"""

from db_config import get_connection

conn = get_connection()
cursor = conn.cursor()

print("="*70)
print("CORRECTED MEMBERSHIP DEDUPLICATION ANALYSIS")
print("="*70)

# 1. Classify by organization type using TRIM
print("\n1. ORGANIZATION TYPE CLASSIFICATION")
print("-"*60)

cursor.execute("""
    SELECT 
        CASE 
            WHEN TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'SLG', 'DLG', 'LOCAL') THEN 'Local Union'
            WHEN TRIM(desig_name) IN ('JC', 'DC', 'JATC', 'JAC') THEN 'Joint/District Council'
            WHEN TRIM(desig_name) IN ('BR', 'BRANCH', 'LBR', 'SLB') THEN 'Branch'
            WHEN TRIM(desig_name) IN ('DIV', 'LDIV', 'DIST', 'D') THEN 'Division'
            WHEN TRIM(desig_name) IN ('CH', 'LCH', 'CAP', 'ASSN') THEN 'Chapter/Association'
            WHEN TRIM(desig_name) IN ('NHQ', 'HQ', 'INT', 'NATL', 'GEB') THEN 'National HQ'
            WHEN TRIM(desig_name) IN ('CONF', 'COUNCIL', 'STATE', 'STC', 'MTC') THEN 'Conference/State'
            WHEN TRIM(desig_name) IN ('SA', 'GCA', 'LEADC', 'BCTC', 'MEC', 'LEC') THEN 'Specialized Unit'
            WHEN TRIM(desig_name) = '' OR desig_name IS NULL THEN 'No Designation'
            ELSE 'Other'
        END as org_type,
        COUNT(*) as cnt,
        SUM(COALESCE(members, 0)) as total_members,
        AVG(COALESCE(members, 0)) as avg_members
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY org_type
    ORDER BY total_members DESC
""")
print(f"{'Org Type':<25} {'Count':>8} {'Total Members':>15} {'Avg':>10}")
for row in cursor.fetchall():
    print(f"{row[0]:<25} {row[1]:>8,} {row[2]:>15,} {row[3]:>10,.0f}")

# 2. LU (Local Unions) by affiliation
print("\n2. LOCAL UNIONS (LU, LG, etc.) BY AFFILIATION")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as local_count,
        SUM(COALESCE(members, 0)) as total_members,
        AVG(COALESCE(members, 0)) as avg_members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'SLG', 'DLG', 'LOCAL')
    GROUP BY aff_abbr
    ORDER BY total_members DESC
    LIMIT 15
""")
print(f"{'Affiliation':<12} {'Locals':>8} {'Total Members':>15} {'Avg':>10}")
local_total = 0
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>8,} {row[2]:>15,} {row[3]:>10,.0f}")
    local_total += row[2]
print(f"\nTotal from Local Unions: {local_total:,}")

# 3. National HQ organizations
print("\n3. NATIONAL HEADQUARTERS")
print("-"*60)

cursor.execute("""
    SELECT f_num, union_name, aff_abbr, COALESCE(members, 0) as members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND TRIM(desig_name) = 'NHQ'
    ORDER BY members DESC
    LIMIT 15
""")
print(f"{'f_num':<10} {'Affil':<10} {'Members':>12} {'Name':<40}")
nhq_total = 0
for row in cursor.fetchall():
    name = (row[1] or '')[:40]
    print(f"{row[0]:<10} {row[2]:<10} {row[3]:>12,} {name}")
    nhq_total += row[3]
print(f"\nTotal NHQ reported: {nhq_total:,}")

# 4. Joint Councils
print("\n4. JOINT/DISTRICT COUNCILS")
print("-"*60)

cursor.execute("""
    SELECT f_num, union_name, aff_abbr, COALESCE(members, 0) as members, TRIM(desig_name) as dn
    FROM lm_data
    WHERE yr_covered = 2024 
    AND TRIM(desig_name) IN ('JC', 'DC', 'JATC', 'JAC')
    ORDER BY members DESC
    LIMIT 15
""")
print(f"{'f_num':<10} {'Type':<6} {'Members':>12} {'Name':<40}")
jc_total = 0
for row in cursor.fetchall():
    name = (row[1] or '')[:40]
    print(f"{row[0]:<10} {row[4]:<6} {row[3]:>12,} {name}")
    jc_total += row[3]

cursor.execute("""
    SELECT COUNT(*), SUM(COALESCE(members, 0))
    FROM lm_data WHERE yr_covered = 2024 
    AND TRIM(desig_name) IN ('JC', 'DC', 'JATC', 'JAC')
""")
row = cursor.fetchone()
print(f"\nTotal Joint/District Councils: {row[0]:,} with {row[1]:,} members")

# 5. Deduplication strategy
print("\n5. DEDUPLICATION STRATEGY")
print("-"*60)

cursor.execute("""
    WITH classified AS (
        SELECT 
            f_num, union_name, aff_abbr, COALESCE(members, 0) as members,
            CASE 
                -- Count: Direct member organizations
                WHEN TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'SLG', 'DLG', 'LOCAL') THEN 'local'
                WHEN TRIM(desig_name) IN ('BR', 'BRANCH', 'LBR', 'SLB') THEN 'branch'
                WHEN TRIM(desig_name) IN ('DIV', 'LDIV', 'DIST', 'D') THEN 'division'
                WHEN TRIM(desig_name) IN ('CH', 'LCH', 'CAP', 'ASSN') THEN 'chapter'
                
                -- Exclude: Aggregate organizations
                WHEN TRIM(desig_name) IN ('NHQ', 'HQ', 'INT', 'NATL', 'GEB') THEN 'national_hq'
                WHEN TRIM(desig_name) IN ('JC', 'DC', 'JATC', 'JAC') THEN 'joint_council'
                WHEN TRIM(desig_name) IN ('CONF', 'COUNCIL', 'STATE', 'STC', 'MTC') THEN 'conference'
                
                -- Federations
                WHEN aff_abbr IN ('AFLCIO', 'SOC', 'TTD') THEN 'federation'
                
                -- Specialized units - need case-by-case
                WHEN TRIM(desig_name) IN ('SA', 'GCA', 'LEADC', 'BCTC', 'MEC', 'LEC') THEN 'specialized'
                
                -- No designation - analyze by size
                WHEN TRIM(desig_name) = '' OR desig_name IS NULL THEN 'no_designation'
                
                ELSE 'other'
            END as category
        FROM lm_data
        WHERE yr_covered = 2024
    )
    SELECT 
        category,
        COUNT(*) as cnt,
        SUM(members) as total_members
    FROM classified
    GROUP BY category
    ORDER BY total_members DESC
""")
print(f"{'Category':<20} {'Count':>8} {'Members':>15} {'Action':<20}")
count_members = 0
exclude_members = 0
for row in cursor.fetchall():
    cat = row[0]
    if cat in ('local', 'branch', 'division', 'chapter', 'other'):
        action = 'COUNT'
        count_members += row[2]
    elif cat == 'no_designation':
        action = 'ANALYZE'
    elif cat == 'specialized':
        action = 'ANALYZE'
    else:
        action = 'EXCLUDE'
        exclude_members += row[2]
    print(f"{row[0]:<20} {row[1]:>8,} {row[2]:>15,} {action:<20}")

# 6. Handle no_designation by size
print("\n6. NO DESIGNATION ANALYSIS (by size)")
print("-"*60)

cursor.execute("""
    SELECT 
        CASE 
            WHEN members > 100000 THEN '>100K (national)'
            WHEN members > 10000 THEN '10K-100K (large local or intermediate)'
            WHEN members > 1000 THEN '1K-10K (medium local)'
            ELSE '<1K (small local)'
        END as size_bucket,
        COUNT(*) as cnt,
        SUM(COALESCE(members, 0)) as total
    FROM lm_data
    WHERE yr_covered = 2024
    AND (TRIM(desig_name) = '' OR desig_name IS NULL)
    GROUP BY size_bucket
    ORDER BY total DESC
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,} orgs, {row[2]:,} members")

# 7. Final estimate with conservative approach
print("\n7. FINAL DEDUPLICATION ESTIMATE")
print("-"*60)

cursor.execute("""
    WITH classified AS (
        SELECT 
            COALESCE(members, 0) as members,
            CASE 
                -- Count: Direct member organizations
                WHEN TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'SLG', 'DLG', 'LOCAL', 
                                          'BR', 'BRANCH', 'LBR', 'SLB',
                                          'DIV', 'LDIV', 'DIST', 'D',
                                          'CH', 'LCH', 'CAP', 'ASSN') THEN 'count_direct'
                
                -- Exclude: Aggregate organizations
                WHEN TRIM(desig_name) IN ('NHQ', 'HQ', 'INT', 'NATL', 'GEB',
                                          'JC', 'DC', 'JATC', 'JAC',
                                          'CONF', 'COUNCIL', 'STATE', 'STC', 'MTC') THEN 'exclude_aggregate'
                
                -- Federations - always exclude
                WHEN aff_abbr IN ('AFLCIO', 'SOC', 'TTD') THEN 'exclude_federation'
                
                -- No designation: count small/medium, exclude large
                WHEN (TRIM(desig_name) = '' OR desig_name IS NULL) AND members <= 10000 THEN 'count_no_desig_small'
                WHEN (TRIM(desig_name) = '' OR desig_name IS NULL) AND members > 10000 THEN 'exclude_no_desig_large'
                
                -- Specialized & other: count if small, exclude if large
                WHEN members <= 10000 THEN 'count_other_small'
                ELSE 'exclude_other_large'
            END as action
        FROM lm_data
        WHERE yr_covered = 2024
    )
    SELECT 
        CASE WHEN action LIKE 'count%' THEN 'COUNT' ELSE 'EXCLUDE' END as summary,
        SUM(members) as total
    FROM classified
    GROUP BY summary
""")
results = {r[0]: r[1] for r in cursor.fetchall()}
count_total = results.get('COUNT', 0)
exclude_total = results.get('EXCLUDE', 0)

print(f"  Organizations to COUNT:   {count_total:>15,}")
print(f"  Organizations to EXCLUDE: {exclude_total:>15,}")
print(f"  -------------------------------------------")
print(f"  ESTIMATED UNIQUE MEMBERS: {count_total:>15,}")
print(f"  BLS Reported (2024):      {14300000:>15,}")
print(f"  Difference:               {count_total - 14300000:>+15,}")

if count_total > 14300000:
    print(f"\n  Still over-counting by {(count_total/14300000 - 1)*100:.1f}%")
    print("  Likely reasons:")
    print("    - Some 'branches' aggregate locals")
    print("    - Some chapters report duplicate membership")
    print("    - Non-LM reported unions in BLS data")

cursor.close()
conn.close()

print("\n" + "="*70)
