"""
Analyze membership duplication in union data
Understand hierarchy and multi-counting issues
"""

from db_config import get_connection

conn = get_connection()
cursor = conn.cursor()

print("="*70)
print("MEMBERSHIP DUPLICATION ANALYSIS")
print("="*70)

# 1. Overall membership totals from different sources
print("\n1. MEMBERSHIP TOTALS BY SOURCE")
print("-"*50)

cursor.execute("""
    SELECT 
        'unions_master' as source,
        COUNT(*) as union_count,
        SUM(members) as total_members
    FROM unions_master
    WHERE members IS NOT NULL
""")
row = cursor.fetchone()
print(f"unions_master: {row[1]:,} unions, {row[2]:,} members")

cursor.execute("""
    SELECT 
        'lm_data 2024' as source,
        COUNT(*) as union_count,
        SUM(members) as total_members
    FROM lm_data
    WHERE yr_covered = 2024 AND members IS NOT NULL
""")
row = cursor.fetchone()
print(f"lm_data (2024): {row[1]:,} filings, {row[2]:,} members")

cursor.execute("""
    SELECT 
        'f7_employers' as source,
        COUNT(*) as employer_count,
        SUM(latest_unit_size) as total_workers
    FROM f7_employers
    WHERE latest_unit_size IS NOT NULL
""")
row = cursor.fetchone()
print(f"f7_employers: {row[1]:,} employers, {row[2]:,} workers in bargaining units")

# 2. Look at form types to understand hierarchy
print("\n2. LM FORM TYPE DISTRIBUTION (2024)")
print("-"*50)
print("LM-2: Large unions (>$250K receipts) - detailed reporting")
print("LM-3: Medium unions ($10K-$250K receipts)")
print("LM-4: Small unions (<$10K receipts)")

cursor.execute("""
    SELECT 
        form_type,
        COUNT(*) as count,
        SUM(members) as total_members,
        AVG(members) as avg_members,
        SUM(ttl_assets) as total_assets
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY form_type
    ORDER BY total_members DESC
""")
print(f"\n{'Form':<8} {'Count':>8} {'Total Members':>15} {'Avg Members':>12} {'Total Assets':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<8} {row[1]:>8,} {row[2] or 0:>15,} {row[3] or 0:>12,.0f} ${row[4] or 0:>14,}")

# 3. Identify potential "parent" unions (nationals/internationals)
print("\n3. POTENTIAL PARENT UNIONS (Largest by membership)")
print("-"*50)

cursor.execute("""
    SELECT 
        f_num, union_name, aff_abbr, members, 
        ttl_assets, state, city
    FROM lm_data
    WHERE yr_covered = 2024 
    AND members > 100000
    ORDER BY members DESC
    LIMIT 20
""")
print(f"{'f_num':<10} {'Members':>12} {'Assets':>15} {'Union Name':<50}")
for row in cursor.fetchall():
    name = (row[1] or '')[:50]
    print(f"{row[0]:<10} {row[3]:>12,} ${row[4] or 0:>14,} {name}")

# 4. Look for hierarchy patterns in names
print("\n4. HIERARCHY PATTERNS IN UNION NAMES")
print("-"*50)

# Count unions with "Local" in name vs without
cursor.execute("""
    SELECT 
        CASE 
            WHEN union_name ILIKE '%local%' THEN 'Local'
            WHEN union_name ILIKE '%district%' OR union_name ILIKE '%region%' 
                 OR union_name ILIKE '%council%' OR union_name ILIKE '%joint%' THEN 'Intermediate'
            WHEN union_name ILIKE '%international%' OR union_name ILIKE '%national%' 
                 OR union_name ILIKE '%federation%' THEN 'National/International'
            ELSE 'Other/Unclear'
        END as level_type,
        COUNT(*) as count,
        SUM(members) as total_members,
        AVG(members) as avg_members
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY level_type
    ORDER BY total_members DESC
""")
print(f"\n{'Level Type':<25} {'Count':>10} {'Total Members':>15} {'Avg Members':>12}")
for row in cursor.fetchall():
    print(f"{row[0]:<25} {row[1]:>10,} {row[2] or 0:>15,} {row[3] or 0:>12,.0f}")

# 5. Look at specific large affiliations
print("\n5. MEMBERSHIP BY AFFILIATION (Top 15)")
print("-"*50)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as filing_count,
        SUM(members) as total_members,
        MAX(members) as max_single_filing,
        COUNT(CASE WHEN members > 10000 THEN 1 END) as large_locals
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY aff_abbr
    ORDER BY total_members DESC
    LIMIT 15
""")
print(f"\n{'Affiliation':<15} {'Filings':>10} {'Total Members':>15} {'Max Single':>12} {'Large (>10K)':>12}")
for row in cursor.fetchall():
    print(f"{row[0]:<15} {row[1]:>10,} {row[2] or 0:>15,} {row[3] or 0:>12,} {row[4]:>12,}")

# 6. Check for same f_num appearing multiple times in same year
print("\n6. DUPLICATE F_NUM CHECK (same union filing multiple times in 2024)")
print("-"*50)

cursor.execute("""
    SELECT f_num, COUNT(*) as cnt, SUM(members) as total
    FROM lm_data
    WHERE yr_covered = 2024
    GROUP BY f_num
    HAVING COUNT(*) > 1
    ORDER BY cnt DESC
    LIMIT 10
""")
dups = cursor.fetchall()
if dups:
    print("Found duplicates:")
    for row in dups:
        print(f"  f_num {row[0]}: {row[1]} filings, {row[2]:,} total members")
else:
    print("No duplicate f_num in same year (good)")

# 7. Analyze parent-local relationship for a major union (e.g., SEIU)
print("\n7. SEIU HIERARCHY EXAMPLE")
print("-"*50)

cursor.execute("""
    SELECT 
        f_num, union_name, members, ttl_assets,
        CASE 
            WHEN union_name ILIKE '%local%' THEN 'Local'
            WHEN union_name ILIKE '%district%' OR union_name ILIKE '%state%council%' THEN 'Intermediate'
            ELSE 'National/Other'
        END as level
    FROM lm_data
    WHERE yr_covered = 2024 
    AND aff_abbr = 'SEIU'
    ORDER BY members DESC
    LIMIT 15
""")
print(f"\n{'f_num':<10} {'Level':<12} {'Members':>12} {'Union Name':<40}")
for row in cursor.fetchall():
    name = (row[1] or '')[:40]
    print(f"{row[0]:<10} {row[4]:<12} {row[2] or 0:>12,} {name}")

cursor.execute("""
    SELECT 
        CASE 
            WHEN union_name ILIKE '%local%' THEN 'Local'
            WHEN union_name ILIKE '%district%' OR union_name ILIKE '%state%council%' THEN 'Intermediate'
            ELSE 'National/Other'
        END as level,
        COUNT(*) as cnt,
        SUM(members) as total
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'SEIU'
    GROUP BY level
    ORDER BY total DESC
""")
print("\nSEIU Summary by Level:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} unions, {row[2] or 0:,} members")

# 8. Check F7 vs LM relationship
print("\n8. F7 EMPLOYERS vs LM MEMBERSHIP FOR MATCHED UNIONS")
print("-"*50)

cursor.execute("""
    SELECT 
        um.aff_abbr,
        COUNT(DISTINCT um.f_num) as union_count,
        SUM(um.members) as lm_members,
        SUM(um.f7_total_workers) as f7_workers,
        SUM(um.f7_employer_count) as employer_count
    FROM unions_master um
    WHERE um.has_f7_employers = true
    GROUP BY um.aff_abbr
    ORDER BY lm_members DESC
    LIMIT 10
""")
print(f"\n{'Affiliation':<12} {'Unions':>8} {'LM Members':>15} {'F7 Workers':>15} {'Employers':>10}")
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>8,} {row[2] or 0:>15,} {row[3] or 0:>15,} {row[4] or 0:>10,}")

cursor.close()
conn.close()

print("\n" + "="*70)
print("ANALYSIS COMPLETE")
print("="*70)
