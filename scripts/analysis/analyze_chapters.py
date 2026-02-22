"""
Analyze chapters and specialized units that cause over-counting
"""

from db_config import get_connection

conn = get_connection()
cursor = conn.cursor()

print("="*70)
print("CHAPTER & SPECIALIZED UNIT ANALYSIS")
print("="*70)

# 1. What affiliations have chapters?
print("\n1. CHAPTERS (CH, LCH, CAP, ASSN) BY AFFILIATION")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as cnt,
        SUM(COALESCE(members, 0)) as total_members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND TRIM(desig_name) IN ('CH', 'LCH', 'CAP', 'ASSN')
    GROUP BY aff_abbr
    ORDER BY total_members DESC
    LIMIT 15
""")
print(f"{'Affiliation':<12} {'Count':>8} {'Members':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>8,} {row[2]:>15,}")

# 2. AFT and NEA analysis - they use chapters
print("\n2. AFT STRUCTURE ANALYSIS")
print("-"*60)

cursor.execute("""
    SELECT 
        TRIM(desig_name) as dtype,
        COUNT(*) as cnt,
        SUM(COALESCE(members, 0)) as total
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = 'AFT'
    GROUP BY TRIM(desig_name)
    ORDER BY total DESC
""")
print("AFT by designation type:")
aft_total = 0
for row in cursor.fetchall():
    print(f"  {row[0] or '(none)':<10}: {row[1]:>5} orgs, {row[2]:>12,} members")
    aft_total += row[2]
print(f"  TOTAL: {aft_total:,}")
print(f"  Actual AFT membership: ~1,700,000")

# 3. Specialized units (SA, LEADC, BCTC, etc.)
print("\n3. SPECIALIZED UNITS BY AFFILIATION")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        TRIM(desig_name) as dtype,
        COUNT(*) as cnt,
        SUM(COALESCE(members, 0)) as total
    FROM lm_data
    WHERE yr_covered = 2024 
    AND TRIM(desig_name) IN ('SA', 'GCA', 'LEADC', 'BCTC', 'MEC', 'LEC')
    GROUP BY aff_abbr, TRIM(desig_name)
    ORDER BY total DESC
    LIMIT 20
""")
print(f"{'Affiliation':<12} {'Type':<8} {'Count':>6} {'Members':>12}")
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:<8} {row[2]:>6,} {row[3]:>12,}")

# 4. What is LEADC, SA, BCTC?
print("\n4. SAMPLE SPECIALIZED UNIT RECORDS")
print("-"*60)

cursor.execute("""
    SELECT f_num, union_name, aff_abbr, TRIM(desig_name), COALESCE(members, 0)
    FROM lm_data
    WHERE yr_covered = 2024 
    AND TRIM(desig_name) IN ('SA', 'LEADC', 'BCTC')
    ORDER BY members DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"  {row[3]}: {row[4]:>10,} - {row[0]} {row[1][:45]}")

# 5. Railroad/Airline unions use different structure
print("\n5. RAILROAD/AIRLINE UNIONS (RLA-covered)")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as cnt,
        SUM(COALESCE(members, 0)) as total
    FROM lm_data
    WHERE yr_covered = 2024 
    AND aff_abbr IN ('BLET', 'BMWE', 'BRS', 'SMART', 'AFA', 'ALPA', 'TWU', 'IAM', 'TCU')
    GROUP BY aff_abbr
    ORDER BY total DESC
""")
print(f"{'Affiliation':<12} {'Filings':>8} {'Members':>15}")
rla_total = 0
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>8,} {row[2]:>15,}")
    rla_total += row[2]
print(f"\nTotal RLA-related: {rla_total:,}")

# 6. Revised estimate: Only LU-type for traditional unions
print("\n6. REVISED DEDUPLICATION ESTIMATE")
print("-"*60)
print("Strategy: Count only 'LU' type locals for unions with clear hierarchy")

cursor.execute("""
    WITH union_hierarchy AS (
        SELECT 
            aff_abbr,
            TRIM(desig_name) as dtype,
            COALESCE(members, 0) as members,
            CASE 
                -- Traditional unions with LU structure - count only LU
                WHEN aff_abbr IN ('IBT', 'UFCW', 'USW', 'UAW', 'IBEW', 'CWA', 'IAM', 
                                  'LIUNA', 'PPF', 'IUOE', 'SMW', 'HERE', 'BCTGM', 
                                  'GMP', 'OPEIU', 'SEIU', 'AFSCME')
                     AND TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'SLG', 'DLG', 'LOCAL')
                THEN 'count_lu'
                
                -- Traditional unions - exclude aggregates
                WHEN aff_abbr IN ('IBT', 'UFCW', 'USW', 'UAW', 'IBEW', 'CWA', 'IAM', 
                                  'LIUNA', 'PPF', 'IUOE', 'SMW', 'HERE', 'BCTGM',
                                  'GMP', 'OPEIU', 'SEIU', 'AFSCME')
                THEN 'exclude_traditional_aggregate'
                
                -- Teachers (AFT, NEA) - complex, use NHQ only
                WHEN aff_abbr IN ('AFT', 'NEA') AND TRIM(desig_name) = 'NHQ'
                THEN 'count_teacher_nhq'
                WHEN aff_abbr IN ('AFT', 'NEA')
                THEN 'exclude_teacher_duplicate'
                
                -- Carpenters - count LU
                WHEN aff_abbr = 'CJA' AND TRIM(desig_name) IN ('LU', 'LG')
                THEN 'count_lu'
                WHEN aff_abbr = 'CJA'
                THEN 'exclude_cja_aggregate'
                
                -- Entertainment - IATSE uses LU
                WHEN aff_abbr = 'IATSE' AND TRIM(desig_name) = 'LU'
                THEN 'count_lu'
                WHEN aff_abbr = 'IATSE'
                THEN 'exclude_iatse_aggregate'
                
                -- Federations - always exclude
                WHEN aff_abbr IN ('AFLCIO', 'SOC', 'TTD')
                THEN 'exclude_federation'
                
                -- Independent/unaffiliated - count if small
                WHEN aff_abbr = 'UNAFF' AND members <= 10000
                THEN 'count_independent'
                WHEN aff_abbr = 'UNAFF'
                THEN 'exclude_large_independent'
                
                -- Railroad/Airline (RLA) - different structure, count divisions
                WHEN aff_abbr IN ('BLET', 'BMWE', 'BRS', 'SMART', 'AFA', 'ALPA', 'TCU')
                     AND TRIM(desig_name) NOT IN ('NHQ', 'GEB', 'CONF')
                THEN 'count_rla'
                WHEN aff_abbr IN ('BLET', 'BMWE', 'BRS', 'SMART', 'AFA', 'ALPA', 'TCU')
                THEN 'exclude_rla_nhq'
                
                -- Others - default count if looks like local
                WHEN TRIM(desig_name) IN ('LU', 'LG', 'LLG', 'BR', 'DIV', 'CH')
                     AND members <= 50000
                THEN 'count_other_local'
                
                -- Default exclude if large
                WHEN members > 50000
                THEN 'exclude_large'
                
                ELSE 'count_remaining'
            END as action
        FROM lm_data
        WHERE yr_covered = 2024
    )
    SELECT 
        action,
        COUNT(*) as cnt,
        SUM(members) as total
    FROM union_hierarchy
    GROUP BY action
    ORDER BY total DESC
""")
count_total = 0
exclude_total = 0
print(f"{'Action':<35} {'Count':>8} {'Members':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<35} {row[1]:>8,} {row[2]:>15,}")
    if row[0].startswith('count'):
        count_total += row[2]
    else:
        exclude_total += row[2]

print(f"\n  -------------------------------------------")
print(f"  COUNTED:  {count_total:>15,}")
print(f"  EXCLUDED: {exclude_total:>15,}")
print(f"  BLS 2024: {14300000:>15,}")
print(f"  Diff:     {count_total - 14300000:>+15,}")

cursor.close()
conn.close()

print("\n" + "="*70)
