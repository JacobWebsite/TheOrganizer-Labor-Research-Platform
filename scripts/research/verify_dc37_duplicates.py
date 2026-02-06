"""
Verify DC37 Duplicate Analysis
Check if DC37 locals are double-counted or separate filings
"""

import psycopg2

DB_CONFIG = {
    'host': 'localhost',
    'dbname': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

DC37_LOCALS = [
    95, 154, 205, 215, 253, 299, 371, 372, 374, 375, 376, 384, 389, 420, 436,
    461, 508, 768, 924, 957, 983, 1070, 1087, 1113, 1157, 1189, 1251, 1306,
    1320, 1321, 1322, 1359, 1407, 1455, 1482, 1501, 1502, 1503, 1505, 1506,
    1507, 1508, 1549, 1559, 1597, 1655, 1740, 1757, 1797, 1930, 1931, 2054,
    2507, 2627, 2906, 3005, 3333, 3599, 3621, 3652, 3778, 5911
]


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("="*80)
    print("DC37 DUPLICATE VERIFICATION")
    print("="*80)

    # 1. Get DC37 main council details
    print("\n1. DC37 MAIN COUNCIL (Local 37) DETAILS")
    print("-"*60)

    cur.execute("""
        SELECT f_num, union_name, local_number, desig_name, aff_abbr,
               members, city, state, yr_covered
        FROM unions_master
        WHERE aff_abbr = 'AFSCME' AND local_number = '37' AND state = 'NY'
    """)
    dc37_main = cur.fetchone()

    if dc37_main:
        print(f"  F#: {dc37_main[0]}")
        print(f"  Name: {dc37_main[1]}")
        print(f"  Local: {dc37_main[2]}")
        print(f"  Designation: {dc37_main[3]} / {dc37_main[4]}")
        print(f"  Members: {dc37_main[5]:,}")
        print(f"  Location: {dc37_main[6]}, {dc37_main[7]}")
        print(f"  Year: {dc37_main[8]}")

    # 2. Check historical DC37 filings
    print("\n2. DC37 HISTORICAL MEMBERSHIP (lm_data)")
    print("-"*60)

    cur.execute("""
        SELECT yr_covered, members, ttl_receipts
        FROM lm_data
        WHERE f_num = '59403'
        ORDER BY yr_covered DESC
        LIMIT 5
    """)

    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1] or 0:>10,} members, ${row[2] or 0:>14,.0f} receipts")

    # 3. Get all DC37 locals with separate filings
    print("\n3. DC37 LOCALS WITH SEPARATE OLMS FILINGS")
    print("-"*60)

    local_nums_str = ','.join([f"'{n}'" for n in DC37_LOCALS])
    cur.execute(f"""
        SELECT f_num, union_name, local_number, desig_name, members, city, yr_covered
        FROM unions_master
        WHERE aff_abbr = 'AFSCME'
          AND state = 'NY'
          AND local_number IN ({local_nums_str})
        ORDER BY members DESC NULLS LAST
    """)

    dc37_locals = cur.fetchall()
    total_local_members = 0

    print(f"\n  {'Local':<8} {'Name':<40} {'Members':>10} {'Year'}")
    print(f"  {'-'*70}")

    for row in dc37_locals:
        members = row[4] or 0
        total_local_members += members
        print(f"  {row[2]:<8} {row[1][:38]:<40} {members:>10,} {row[6]}")

    print(f"  {'-'*70}")
    print(f"  {'TOTAL':<8} {'':<40} {total_local_members:>10,}")

    # 4. Check if DC37 locals are affiliated under DC37
    print("\n4. CHECK AFFILIATION CODES FOR DC37 LOCALS")
    print("-"*60)

    cur.execute(f"""
        SELECT f_num, local_number, desig_name, aff_abbr,
               SUBSTRING(union_name, 1, 50) as name_short
        FROM unions_master
        WHERE aff_abbr = 'AFSCME'
          AND state = 'NY'
          AND local_number IN ({local_nums_str})
        ORDER BY local_number::integer
    """)

    print(f"\n  {'F#':<10} {'Local':<8} {'Desig':<8} {'Desig#':<10} {'Name'}")
    for row in cur.fetchall():
        print(f"  {row[0]:<10} {row[1]:<8} {row[2] or 'N/A':<8} {row[3] or 'N/A':<10} {row[4]}")

    # 5. Compare to DC37 990 data
    print("\n5. DC37 FORM 990 COMPARISON")
    print("-"*60)

    cur.execute("""
        SELECT organization_name, ein, dues_revenue, estimated_members, dues_rate_used
        FROM form_990_estimates
        WHERE organization_name ILIKE '%DC 37%' OR organization_name ILIKE '%DC37%'
           OR organization_name ILIKE '%DISTRICT COUNCIL 37%'
    """)

    for row in cur.fetchall():
        print(f"  Organization: {row[0]}")
        print(f"  EIN: {row[1]}")
        print(f"  Dues Revenue: ${float(row[2]):,.0f}")
        print(f"  Estimated Members: {row[3]:,}")
        print(f"  Dues Rate Used: ${float(row[4]):,.0f}/member")

    # 6. Determine if duplicates
    print("\n" + "="*80)
    print("ANALYSIS CONCLUSION")
    print("="*80)

    dc37_main_members = dc37_main[5] if dc37_main else 0

    print(f"\n  DC37 Main (Local 37) reports: {dc37_main_members:,} members")
    print(f"  Sum of DC37 locals filing separately: {total_local_members:,} members")
    print(f"  Combined (if separate): {dc37_main_members + total_local_members:,} members")
    print(f"  990 Estimate: 128,571 members")

    # Logic check
    combined = dc37_main_members + total_local_members

    print(f"\n  Analysis:")
    if combined > 150000:
        print(f"  - Combined ({combined:,}) significantly exceeds 990 estimate (128,571)")
        print(f"  - LIKELY DUPLICATE: DC37 locals are probably included in Local 37's count")
    elif abs(dc37_main_members - 128571) < abs(combined - 128571):
        print(f"  - Local 37 alone ({dc37_main_members:,}) is closer to 990 estimate than combined")
        print(f"  - LIKELY DUPLICATE: DC37 locals are probably included in Local 37's count")
    else:
        print(f"  - Combined total ({combined:,}) is closer to 990 estimate")
        print(f"  - LIKELY SEPARATE: DC37 locals may be separate from Local 37")

    # Check if locals members add up to a significant portion
    if total_local_members > 0:
        pct_of_main = (total_local_members / dc37_main_members) * 100 if dc37_main_members else 0
        print(f"\n  DC37 locals = {pct_of_main:.1f}% of Local 37's reported membership")

        if pct_of_main < 20:
            print(f"  - Locals represent a small fraction - could be subset filing separately")
        else:
            print(f"  - Locals represent significant portion - duplication more likely")

    # 7. Check what designation codes mean
    print("\n7. DESIGNATION CODE ANALYSIS")
    print("-"*60)

    cur.execute("""
        SELECT DISTINCT desig_name, COUNT(*) as cnt
        FROM unions_master
        WHERE aff_abbr = 'AFSCME' AND state = 'NY'
        GROUP BY desig_name
        ORDER BY cnt DESC
    """)

    print("\n  AFSCME NY Designation Types:")
    for row in cur.fetchall():
        desig = row[0].strip() if row[0] else 'NULL'
        print(f"    {desig:<10} : {row[1]} unions")

    # Check DC37 main designation vs locals
    cur.execute("""
        SELECT desig_name, aff_abbr
        FROM unions_master
        WHERE f_num = '59403'
    """)
    dc37_desig = cur.fetchone()
    print(f"\n  DC37 Main designation: {dc37_desig[0]} / {dc37_desig[1]}" if dc37_desig else "  DC37 Main not found")

    # DC = District Council, LU = Local Union
    # If DC37 is a District Council and locals are Local Unions,
    # the DC typically reports aggregate of all its locals

    conn.close()


if __name__ == '__main__':
    main()
