"""
Analyze remaining over-count in deduplicated membership
"""

from db_config import get_connection

conn = get_connection()
cursor = conn.cursor()

print("="*70)
print("REMAINING OVER-COUNT ANALYSIS")
print("="*70)

# Current totals
cursor.execute("""
    SELECT 
        SUM(reported_members) as reported,
        SUM(counted_members) as counted
    FROM v_deduplicated_membership
""")
row = cursor.fetchone()
print(f"\nCurrent state:")
print(f"  Reported: {row[0]:,}")
print(f"  Counted:  {row[1]:,}")
print(f"  BLS:      14,300,000")
print(f"  Over by:  {row[1] - 14300000:,} ({(row[1]/14300000 - 1)*100:.1f}%)")

# 1. Breakdown by dedup_category for counted items
print("\n1. COUNTED MEMBERS BY CATEGORY")
print("-"*60)

cursor.execute("""
    SELECT 
        ol.dedup_category,
        COUNT(*) as cnt,
        SUM(COALESCE(l.members, 0)) as total
    FROM union_organization_level ol
    JOIN lm_data l ON ol.f_num = l.f_num AND l.yr_covered = 2024
    WHERE ol.is_leaf_level = TRUE
    GROUP BY ol.dedup_category
    ORDER BY total DESC
""")
print(f"{'Category':<30} {'Count':>8} {'Members':>15}")
for row in cursor.fetchall():
    print(f"{row[0]:<30} {row[1]:>8,} {row[2]:>15,}")

# 2. Look at large "locals" that might be aggregates
print("\n2. LARGE 'LOCAL' ORGANIZATIONS (>50K members)")
print("-"*60)

cursor.execute("""
    SELECT 
        l.f_num, l.union_name, l.aff_abbr, l.members,
        TRIM(l.desig_name) as desig, ol.dedup_category
    FROM lm_data l
    JOIN union_organization_level ol ON l.f_num = ol.f_num
    WHERE l.yr_covered = 2024
    AND ol.is_leaf_level = TRUE
    AND l.members > 50000
    ORDER BY l.members DESC
    LIMIT 20
""")
print(f"{'f_num':<10} {'Affil':<8} {'Members':>10} {'Desig':<8} {'Name':<35}")
large_local_total = 0
for row in cursor.fetchall():
    name = (row[1] or '')[:35]
    print(f"{row[0]:<10} {row[2]:<8} {row[3]:>10,} {row[4] or '':<8} {name}")
    large_local_total += row[3]
print(f"\nTotal from large 'locals': {large_local_total:,}")

# 3. Compare known union sizes
print("\n3. COMPARISON WITH KNOWN UNION SIZES")
print("-"*60)

known_sizes = {
    'SEIU': 2000000,
    'IBT': 1300000,
    'UFCW': 1300000,
    'AFT': 1700000,
    'NEA': 3000000,
    'AFSCME': 1400000,
    'UAW': 400000,
    'IBEW': 775000,
    'CWA': 700000,
    'LIUNA': 500000,
    'IAM': 600000,
    'USW': 850000,
    'CJA': 500000,
}

cursor.execute("""
    SELECT 
        aff_abbr,
        SUM(counted_members) as counted
    FROM v_deduplicated_membership
    GROUP BY aff_abbr
    ORDER BY counted DESC
""")
results = {r[0]: r[1] for r in cursor.fetchall()}

print(f"{'Union':<10} {'Counted':>12} {'Known':>12} {'Diff':>12} {'%':>8}")
total_over = 0
for union, known in sorted(known_sizes.items(), key=lambda x: x[1], reverse=True):
    counted = results.get(union, 0)
    diff = counted - known
    pct = (counted / known - 1) * 100 if known > 0 else 0
    total_over += max(0, diff)
    print(f"{union:<10} {counted:>12,} {known:>12,} {diff:>+12,} {pct:>+7.1f}%")

print(f"\nTotal over-count from known unions: {total_over:,}")

# 4. Look at unions not in known list
print("\n4. OTHER SIGNIFICANT COUNTED UNIONS")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        SUM(counted_members) as counted
    FROM v_deduplicated_membership
    WHERE aff_abbr NOT IN ('SEIU', 'IBT', 'UFCW', 'AFT', 'NEA', 'AFSCME', 
                           'UAW', 'IBEW', 'CWA', 'LIUNA', 'IAM', 'USW', 'CJA',
                           'AFLCIO', 'SOC', 'TTD')
    AND counted_members > 0
    GROUP BY aff_abbr
    HAVING SUM(counted_members) > 100000
    ORDER BY counted DESC
""")
print(f"{'Union':<12} {'Counted':>12}")
other_total = 0
for row in cursor.fetchall():
    print(f"{row[0]:<12} {row[1]:>12,}")
    other_total += row[1]
print(f"\nTotal from other unions: {other_total:,}")

# 5. Federal employee unions analysis
print("\n5. FEDERAL EMPLOYEE UNIONS")
print("-"*60)

cursor.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as filings,
        SUM(reported_members) as reported,
        SUM(counted_members) as counted
    FROM v_deduplicated_membership
    WHERE aff_abbr IN ('AFGE', 'NFFE', 'NTEU', 'NALC', 'APWU', 'NPMHU', 'NRLCA')
    GROUP BY aff_abbr
    ORDER BY reported DESC
""")
print(f"{'Union':<10} {'Filings':>8} {'Reported':>12} {'Counted':>12}")
fed_total = 0
for row in cursor.fetchall():
    print(f"{row[0]:<10} {row[1]:>8,} {row[2]:>12,} {row[3]:>12,}")
    fed_total += row[3]
print(f"\nTotal federal unions counted: {fed_total:,}")
print("Note: BLS includes federal workers in their ~14.3M total")

cursor.close()
conn.close()

print("\n" + "="*70)
