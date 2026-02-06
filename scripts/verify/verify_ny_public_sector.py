"""
Verify NY public sector union findings against the database.
Checks existing coverage and identifies gaps.
"""
import psycopg2
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def main():
    conn = psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )
    cur = conn.cursor()

    print("=" * 80)
    print("NY PUBLIC SECTOR DATABASE VERIFICATION")
    print("=" * 80)

    # =====================================================================
    # 1. Check ps_union_locals for NY
    # =====================================================================
    print("\n" + "=" * 80)
    print("1. PS_UNION_LOCALS - NY entries")
    print("=" * 80)
    cur.execute("""
        SELECT id, local_name, parent_union_id, city, state, members, sector_type
        FROM ps_union_locals WHERE state = 'NY'
        ORDER BY parent_union_id, local_name
    """)
    ny_locals = cur.fetchall()
    print("Total NY locals in ps_union_locals: %d" % len(ny_locals))
    if ny_locals:
        for row in ny_locals[:60]:
            print("  ID=%s | %s | parent=%s | %s, NY | members=%s | type=%s" % (
                row[0], row[1], row[2], row[3], row[5], row[6]
            ))
        if len(ny_locals) > 60:
            print("  ... and %d more" % (len(ny_locals) - 60))
    else:
        print("  (none found)")

    # =====================================================================
    # 2. Check ps_employers for NY
    # =====================================================================
    print("\n" + "=" * 80)
    print("2. PS_EMPLOYERS - NY entries")
    print("=" * 80)
    cur.execute("""
        SELECT id, employer_name, employer_type, city, county, state, total_employees
        FROM ps_employers WHERE state = 'NY'
        ORDER BY employer_type, employer_name
    """)
    ny_employers = cur.fetchall()
    print("Total NY employers in ps_employers: %d" % len(ny_employers))
    if ny_employers:
        for row in ny_employers[:60]:
            print("  ID=%s | %s | type=%s | %s, %s | employees=%s" % (
                row[0], row[1], row[2], row[3], row[4], row[6]
            ))
        if len(ny_employers) > 60:
            print("  ... and %d more" % (len(ny_employers) - 60))
    else:
        print("  (none found)")

    # =====================================================================
    # 3. Check ps_parent_unions
    # =====================================================================
    print("\n" + "=" * 80)
    print("3. PS_PARENT_UNIONS - All entries")
    print("=" * 80)
    cur.execute("SELECT id, abbrev, full_name, federation, sector_focus FROM ps_parent_unions ORDER BY id")
    parent_unions = cur.fetchall()
    print("Total parent unions: %d" % len(parent_unions))
    for row in parent_unions:
        print("  ID=%s | %s | %s | fed=%s | focus=%s" % (row[0], row[1], row[2], row[3], row[4]))

    # =====================================================================
    # 4. Check manual_employers for NY
    # =====================================================================
    print("\n" + "=" * 80)
    print("4. MANUAL_EMPLOYERS - NY entries")
    print("=" * 80)
    cur.execute("""
        SELECT employer_name, city, state, union_name, affiliation, num_employees, sector
        FROM manual_employers WHERE state = 'NY'
        ORDER BY num_employees DESC NULLS LAST
    """)
    ny_manual = cur.fetchall()
    print("Total NY manual employers: %d" % len(ny_manual))
    if ny_manual:
        for row in ny_manual[:80]:
            print("  %s | %s | union=%s | aff=%s | emp=%s | sector=%s" % (
                row[0], row[1], row[3], row[4], row[5], row[6]
            ))
        if len(ny_manual) > 80:
            print("  ... and %d more" % (len(ny_manual) - 80))
    else:
        print("  (none found)")

    # =====================================================================
    # 5. Search mv_employer_search for specific NY unions
    # =====================================================================
    print("\n" + "=" * 80)
    print("5. MV_EMPLOYER_SEARCH - Specific NY union searches")
    print("=" * 80)

    searches = [
        ("CSEA", ["csea"]),
        ("DC37 / District Council 37", ["dc37", "dc 37", "district council 37"]),
        ("PEF / Public Employees Federation", ["pef", "public employees federation"]),
        ("UUP / United University Professions", ["uup", "united university professions"]),
        ("NYSUT", ["nysut"]),
        ("UFT / United Federation of Teachers", ["uft", "united federation of teachers"]),
        ("TWU / Transport Workers", ["twu", "transport workers"]),
        ("NYSCOPBA", ["nyscopba"]),
        ("Council 82", ["council 82"]),
        ("AFSCME Council 66", ["afscme council 66", "council 66"]),
        ("PBA / Police Benevolent", ["pba", "police benevolent"]),
        ("Teamsters Local 831", ["teamsters local 831", "local 831"]),
        ("COBA / Correction Officers", ["coba", "correction officers"]),
        ("UFA Local 94 / Firefighters", ["ufa", "local 94"]),
        ("IBEW Local 2104 / NYPA", ["ibew 2104", "local 2104"]),
        ("PSC-CUNY", ["psc-cuny", "professional staff congress"]),
    ]

    for label, terms in searches:
        print("\n--- %s ---" % label)
        found_any = False
        for term in terms:
            cur.execute("""
                SELECT canonical_id, employer_name, city, state, source_type,
                       has_union, union_name
                FROM mv_employer_search
                WHERE state = 'NY'
                  AND (LOWER(employer_name) LIKE %s OR LOWER(COALESCE(union_name,'')) LIKE %s)
                ORDER BY employer_name
                LIMIT 15
            """, ('%' + term.lower() + '%', '%' + term.lower() + '%'))
            rows = cur.fetchall()
            if rows:
                found_any = True
                for r in rows:
                    cid = str(r[0])[:12] if r[0] else ''
                    print("  [%s] %s | %s, NY | union=%s | src=%s" % (
                        cid, r[1], r[2], r[6], r[4]
                    ))
        if not found_any:
            print("  NOT FOUND in mv_employer_search")

    # =====================================================================
    # 5b. Search unions_master for NY public-sector unions
    # =====================================================================
    print("\n" + "=" * 80)
    print("5b. UNIONS_MASTER - NY public-sector union filings")
    print("=" * 80)

    union_searches = [
        ("AFSCME", "afscme"),
        ("DC37", "dc 37"),
        ("CSEA", "csea"),
        ("PEF", "public employees"),
        ("UFT/NYSUT", "teachers"),
        ("TWU", "transport workers"),
        ("IAFF", "fire fighters"),
        ("ATU", "amalgamated transit"),
        ("Teamsters", "teamsters"),
        ("IBEW", "ibew"),
        ("CWA", "communications workers"),
        ("Police/PBA", "police"),
        ("Corrections", "correction"),
    ]

    for label, term in union_searches:
        cur.execute("""
            SELECT f_num, union_name, members, city
            FROM unions_master
            WHERE state = 'NY'
              AND LOWER(union_name) LIKE %s
            ORDER BY members DESC NULLS LAST
            LIMIT 8
        """, ('%' + term + '%',))
        rows = cur.fetchall()
        print("\n--- %s (term='%s') --- [%d results]" % (label, term, len(rows)))
        for r in rows:
            print("  f_num=%s | %s | members=%s | %s" % (r[0], r[1], r[2], r[3]))

    # =====================================================================
    # 6. Count existing coverage
    # =====================================================================
    print("\n" + "=" * 80)
    print("6. EXISTING COVERAGE COUNTS")
    print("=" * 80)

    # NY locals by parent union
    cur.execute("""
        SELECT pu.abbrev, pu.full_name, COUNT(l.id) as local_count, SUM(l.members) as total_members
        FROM ps_union_locals l
        JOIN ps_parent_unions pu ON l.parent_union_id = pu.id
        WHERE l.state = 'NY'
        GROUP BY pu.abbrev, pu.full_name
        ORDER BY total_members DESC NULLS LAST
    """)
    rows = cur.fetchall()
    print("\nNY locals by parent union:")
    if rows:
        for r in rows:
            print("  %s (%s): %d locals, %s members" % (r[0], r[1], r[2], r[3]))
    else:
        print("  (none)")

    # NY employers by type
    cur.execute("""
        SELECT employer_type, COUNT(*) as cnt, SUM(total_employees) as total_emp
        FROM ps_employers WHERE state = 'NY'
        GROUP BY employer_type
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    print("\nNY employers by type:")
    if rows:
        for r in rows:
            print("  %s: %d employers, %s employees" % (r[0], r[1], r[2]))
    else:
        print("  (none)")

    # Check for DC37 locals specifically
    print("\nDC37 locals in system:")
    cur.execute("""
        SELECT local_name, members, city
        FROM ps_union_locals
        WHERE state = 'NY'
          AND (LOWER(local_name) LIKE '%dc37%' OR LOWER(local_name) LIKE '%dc 37%'
               OR LOWER(local_name) LIKE '%district council 37%')
        ORDER BY local_name
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print("  %s | members=%s | %s" % (r[0], r[1], r[2]))
    else:
        print("  (none found in ps_union_locals)")

    # Also check unions_master for DC37 locals
    cur.execute("""
        SELECT f_num, union_name, members, city
        FROM unions_master
        WHERE state = 'NY'
          AND (LOWER(union_name) LIKE '%dc 37%' OR LOWER(union_name) LIKE '%district council 37%')
        ORDER BY union_name
    """)
    rows = cur.fetchall()
    print("  DC37 in unions_master: %d filings" % len(rows))
    for r in rows[:10]:
        print("    f_num=%s | %s | members=%s | %s" % (r[0], r[1], r[2], r[3]))

    # Check for CSEA locals
    print("\nCSEA locals/regions in system:")
    cur.execute("""
        SELECT local_name, members, city
        FROM ps_union_locals
        WHERE state = 'NY'
          AND LOWER(local_name) LIKE '%csea%'
        ORDER BY local_name
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print("  %s | members=%s | %s" % (r[0], r[1], r[2]))
    else:
        print("  (none found in ps_union_locals)")

    cur.execute("""
        SELECT f_num, union_name, members, city
        FROM unions_master
        WHERE state = 'NY' AND LOWER(union_name) LIKE '%csea%'
        ORDER BY members DESC NULLS LAST
        LIMIT 10
    """)
    rows = cur.fetchall()
    print("  CSEA in unions_master: %d shown" % len(rows))
    for r in rows:
        print("    f_num=%s | %s | members=%s | %s" % (r[0], r[1], r[2], r[3]))

    # IAFF fire locals
    print("\nIAFF fire locals in NY:")
    cur.execute("""
        SELECT local_name, members, city
        FROM ps_union_locals
        WHERE state = 'NY'
          AND (LOWER(local_name) LIKE '%iaff%' OR LOWER(local_name) LIKE '%fire%')
        ORDER BY local_name
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print("  %s | members=%s | %s" % (r[0], r[1], r[2]))
    else:
        print("  (none found in ps_union_locals)")

    cur.execute("""
        SELECT COUNT(*) FROM unions_master
        WHERE state = 'NY' AND (LOWER(union_name) LIKE '%fire fighters%' OR LOWER(union_name) LIKE '%iaff%')
    """)
    print("  IAFF/fire in unions_master: %d filings" % cur.fetchone()[0])

    # ATU transit locals
    print("\nATU transit locals in NY:")
    cur.execute("""
        SELECT local_name, members, city
        FROM ps_union_locals
        WHERE state = 'NY'
          AND (LOWER(local_name) LIKE '%atu%' OR LOWER(local_name) LIKE '%transit%')
        ORDER BY local_name
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print("  %s | members=%s | %s" % (r[0], r[1], r[2]))
    else:
        print("  (none found in ps_union_locals)")

    cur.execute("""
        SELECT COUNT(*) FROM unions_master
        WHERE state = 'NY' AND (LOWER(union_name) LIKE '%amalgamated transit%' OR LOWER(union_name) LIKE '%atu %')
    """)
    print("  ATU in unions_master: %d filings" % cur.fetchone()[0])

    # =====================================================================
    # 6b. unions_master NY totals by affiliation group
    # =====================================================================
    print("\n" + "=" * 80)
    print("6b. UNIONS_MASTER - Total NY union filings by affiliation")
    print("=" * 80)
    cur.execute("""
        SELECT
            CASE
                WHEN LOWER(union_name) LIKE '%afscme%' OR LOWER(union_name) LIKE '%state county%' THEN 'AFSCME'
                WHEN LOWER(union_name) LIKE '%csea%' THEN 'CSEA'
                WHEN LOWER(union_name) LIKE '%dc 37%' OR LOWER(union_name) LIKE '%district council 37%' THEN 'DC37'
                WHEN LOWER(union_name) LIKE '%teachers%' OR LOWER(union_name) LIKE '%nysut%' OR LOWER(union_name) LIKE '%uft%' THEN 'Teachers'
                WHEN LOWER(union_name) LIKE '%transport workers%' OR LOWER(union_name) LIKE '%twu%' THEN 'TWU'
                WHEN LOWER(union_name) LIKE '%fire fighters%' OR LOWER(union_name) LIKE '%iaff%' THEN 'IAFF'
                WHEN LOWER(union_name) LIKE '%amalgamated transit%' OR LOWER(union_name) LIKE '%atu %' THEN 'ATU'
                WHEN LOWER(union_name) LIKE '%teamsters%' THEN 'Teamsters'
                WHEN LOWER(union_name) LIKE '%ibew%' OR LOWER(union_name) LIKE '%electrical%' THEN 'IBEW'
                WHEN LOWER(union_name) LIKE '%communications workers%' OR LOWER(union_name) LIKE '%cwa%' THEN 'CWA'
                WHEN LOWER(union_name) LIKE '%seiu%' OR LOWER(union_name) LIKE '%service employees%' THEN 'SEIU'
                WHEN LOWER(union_name) LIKE '%police%' OR LOWER(union_name) LIKE '%pba%' THEN 'Police/PBA'
                WHEN LOWER(union_name) LIKE '%correction%' THEN 'Corrections'
                WHEN LOWER(union_name) LIKE '%public employees%' OR LOWER(union_name) LIKE '%pef%' THEN 'PEF'
                ELSE 'Other'
            END as affiliation_group,
            COUNT(*) as filing_count,
            SUM(members) as total_members
        FROM unions_master
        WHERE state = 'NY'
        GROUP BY affiliation_group
        ORDER BY total_members DESC NULLS LAST
    """)
    rows = cur.fetchall()
    for r in rows:
        print("  %s: %d filings, %s members" % (r[0], r[1], r[2]))

    # =====================================================================
    # 7. Large NY unions in unions_master
    # =====================================================================
    print("\n" + "=" * 80)
    print("7. LARGE NY UNIONS IN UNIONS_MASTER (>5K members)")
    print("=" * 80)
    cur.execute("""
        SELECT f_num, union_name, members, city
        FROM unions_master
        WHERE state = 'NY' AND members > 5000
        ORDER BY members DESC
        LIMIT 40
    """)
    rows = cur.fetchall()
    for r in rows:
        print("  f_num=%s | %s | members=%s | %s" % (r[0], r[1], r[2], r[3]))

    # =====================================================================
    # 8. Check ps_bargaining_units for NY
    # =====================================================================
    print("\n" + "=" * 80)
    print("8. PS_BARGAINING_UNITS - NY entries")
    print("=" * 80)
    cur.execute("""
        SELECT bu.id, l.local_name, e.employer_name, bu.unit_size
        FROM ps_bargaining_units bu
        JOIN ps_union_locals l ON bu.local_id = l.id
        JOIN ps_employers e ON bu.employer_id = e.id
        WHERE l.state = 'NY' OR e.state = 'NY'
        ORDER BY bu.unit_size DESC NULLS LAST
        LIMIT 30
    """)
    rows = cur.fetchall()
    print("NY bargaining units: %d shown" % len(rows))
    if rows:
        for r in rows:
            print("  BU=%s | %s <-> %s | size=%s" % (r[0], r[1], r[2], r[3]))
    else:
        print("  (none found)")

    # =====================================================================
    # 9. GAP ANALYSIS
    # =====================================================================
    print("\n" + "=" * 80)
    print("9. GAP ANALYSIS - Known entities vs database")
    print("=" * 80)

    known_entities = [
        ("CSEA (statewide)", 265000, "csea"),
        ("DC37 (NYC municipal)", 150000, "dc 37"),
        ("UFT (NYC teachers)", 190000, "united federation of teachers"),
        ("NYSUT (statewide teachers)", 600000, "nysut"),
        ("PEF (state professionals)", 52000, "public employees federation"),
        ("UUP (SUNY faculty)", 42000, "united university professions"),
        ("TWU Local 100 (NYC Transit)", 40000, "transport workers"),
        ("NYC PBA (police)", 20000, "police benevolent"),
        ("Teamsters Local 237 (NYCHA)", 24000, "local 237"),
        ("COBA (NYC corrections)", 9000, "correction officers"),
        ("UFA Local 94 (FDNY firefighters)", 9000, "uniformed firefighters"),
        ("Teamsters Local 831 (NYC sanitation)", 7100, "local 831"),
        ("SBA (sergeants)", 4400, "sergeants benevolent"),
        ("DEA (detectives)", 5500, "detectives endowment"),
        ("PSC-CUNY", 30000, "professional staff congress"),
        ("AFSCME Council 66 (upstate)", 35000, "council 66"),
        ("GSEU/CWA 1104 (grad students)", 4500, "graduate student"),
        ("NYSCOPBA (corrections officers)", 18000, "nyscopba"),
        ("Council 82 (law enforcement)", 4500, "council 82"),
        ("UFOA Local 854 (FDNY officers)", 7500, "fire officers"),
    ]

    print("\nChecking known entities against database:")
    total_expected = 0
    total_found = 0
    missing_list = []
    found_list = []

    for name, expected_members, search_term in known_entities:
        total_expected += expected_members

        # Check unions_master
        cur.execute("""
            SELECT f_num, union_name, members
            FROM unions_master
            WHERE state = 'NY' AND LOWER(union_name) LIKE %s
            ORDER BY members DESC NULLS LAST
            LIMIT 3
        """, ('%' + search_term + '%',))
        um_rows = cur.fetchall()

        # Check ps_union_locals
        cur.execute("""
            SELECT local_name, members
            FROM ps_union_locals
            WHERE state = 'NY' AND LOWER(local_name) LIKE %s
            ORDER BY members DESC NULLS LAST
            LIMIT 3
        """, ('%' + search_term + '%',))
        ps_rows = cur.fetchall()

        # Check manual_employers
        cur.execute("""
            SELECT employer_name, union_name, num_employees
            FROM manual_employers
            WHERE state = 'NY' AND (LOWER(union_name) LIKE %s OR LOWER(employer_name) LIKE %s)
            ORDER BY num_employees DESC NULLS LAST
            LIMIT 3
        """, ('%' + search_term + '%', '%' + search_term + '%'))
        me_rows = cur.fetchall()

        found_members = 0
        sources = []
        if um_rows:
            found_members = max(found_members, um_rows[0][2] or 0)
            sources.append("unions_master(f_num=%s, %s members)" % (um_rows[0][0], um_rows[0][2]))
        if ps_rows:
            found_members = max(found_members, ps_rows[0][1] or 0)
            sources.append("ps_union_locals(%s members)" % ps_rows[0][1])
        if me_rows:
            found_members = max(found_members, me_rows[0][2] or 0)
            sources.append("manual_employers(%s emp)" % me_rows[0][2])

        total_found += found_members
        status = "FOUND" if sources else "MISSING"

        print("\n  %s [%s] - Expected: %s" % (name, status, "{:,}".format(expected_members)))
        if sources:
            for s in sources:
                print("    -> %s" % s)
            found_list.append((name, expected_members, found_members))
        else:
            print("    ** ENTIRELY MISSING from database **")
            missing_list.append((name, expected_members))

    print("\n" + "-" * 60)
    print("FOUND (%d entities):" % len(found_list))
    for name, exp, found in found_list:
        print("  [OK] %s (expected %s, found %s)" % (name, "{:,}".format(exp), "{:,}".format(found)))

    print("\nMISSING (%d entities):" % len(missing_list))
    missing_total = 0
    for name, exp in missing_list:
        print("  [MISSING] %s (expected %s)" % (name, "{:,}".format(exp)))
        missing_total += exp

    print("\n" + "-" * 60)
    print("OVERALL SUMMARY:")
    print("  Known major NY public sector unions: %d" % len(known_entities))
    print("  Found in DB: %d" % len(found_list))
    print("  Missing from DB: %d" % len(missing_list))
    print("  Expected total members (major unions): ~%s" % "{:,}".format(total_expected))
    print("  Found in DB (max per entity): ~%s" % "{:,}".format(total_found))
    print("  Missing members: ~%s" % "{:,}".format(missing_total))

    # =====================================================================
    # 10. EPI Benchmark for NY
    # =====================================================================
    print("\n" + "=" * 80)
    print("10. EPI BENCHMARK FOR NY")
    print("=" * 80)
    cur.execute("SELECT * FROM epi_state_benchmarks WHERE state = 'NY'")
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    if rows:
        for row in rows:
            row_dict = dict(zip(cols, row))
            for k, v in row_dict.items():
                print("  %s: %s" % (k, v))
    else:
        print("  (not found)")

    # =====================================================================
    # 11. State sector density for NY
    # =====================================================================
    print("\n" + "=" * 80)
    print("11. STATE_SECTOR_UNION_DENSITY - NY latest")
    print("=" * 80)
    cur.execute("""
        SELECT state, sector, year, density_pct
        FROM state_sector_union_density
        WHERE state = 'NY'
        ORDER BY year DESC, sector
        LIMIT 10
    """)
    rows = cur.fetchall()
    for r in rows:
        print("  NY %s %s: %.1f%%" % (r[1], r[2], float(r[3])))

    # =====================================================================
    # 12. Total NY public sector workers tracked
    # =====================================================================
    print("\n" + "=" * 80)
    print("12. TOTAL NY PUBLIC SECTOR WORKERS CURRENTLY TRACKED")
    print("=" * 80)

    cur.execute("SELECT COALESCE(SUM(members), 0) FROM ps_union_locals WHERE state = 'NY'")
    ps_locals_total = cur.fetchone()[0]
    print("  ps_union_locals (NY): %s members" % "{:,}".format(ps_locals_total))

    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(num_employees), 0) FROM manual_employers WHERE state = 'NY'
    """)
    r = cur.fetchone()
    print("  manual_employers (NY): %d records, %s employees" % (r[0], "{:,}".format(r[1])))

    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(members), 0)
        FROM unions_master WHERE state = 'NY'
    """)
    r = cur.fetchone()
    print("  unions_master (NY): %d filings, %s total members" % (r[0], "{:,}".format(r[1])))

    # Public sector specific unions in unions_master
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(members), 0)
        FROM unions_master
        WHERE state = 'NY' AND (
            LOWER(union_name) LIKE '%afscme%' OR LOWER(union_name) LIKE '%state county%'
            OR LOWER(union_name) LIKE '%csea%'
            OR LOWER(union_name) LIKE '%teachers%' OR LOWER(union_name) LIKE '%nysut%'
            OR LOWER(union_name) LIKE '%uft%'
            OR LOWER(union_name) LIKE '%public employees federation%'
            OR LOWER(union_name) LIKE '%transport workers%'
            OR LOWER(union_name) LIKE '%fire fighters%' OR LOWER(union_name) LIKE '%iaff%'
            OR LOWER(union_name) LIKE '%police%' OR LOWER(union_name) LIKE '%pba%'
            OR LOWER(union_name) LIKE '%correction%'
            OR LOWER(union_name) LIKE '%sanitation%'
            OR LOWER(union_name) LIKE '%council 82%' OR LOWER(union_name) LIKE '%council 66%'
        )
    """)
    r = cur.fetchone()
    print("  unions_master (NY public-sector-related): %d filings, %s members" % (r[0], "{:,}".format(r[1])))

    # =====================================================================
    # 13. Check what DC37 locals exist in unions_master
    # =====================================================================
    print("\n" + "=" * 80)
    print("13. DC37 LOCALS IN UNIONS_MASTER (detailed)")
    print("=" * 80)
    cur.execute("""
        SELECT f_num, union_name, members, city
        FROM unions_master
        WHERE state = 'NY'
          AND (LOWER(union_name) LIKE '%dc 37%'
               OR LOWER(union_name) LIKE '%district council 37%'
               OR LOWER(union_name) LIKE '%afscme%local%'
               OR LOWER(union_name) LIKE '%dc37%')
          AND LOWER(union_name) NOT LIKE '%afscme council%'
        ORDER BY union_name
    """)
    rows = cur.fetchall()
    print("DC37-related filings: %d" % len(rows))
    for r in rows[:30]:
        print("  f_num=%s | %s | members=%s | %s" % (r[0], r[1], r[2], r[3]))
    if len(rows) > 30:
        print("  ... and %d more" % (len(rows) - 30))

    # =====================================================================
    # 14. Check for AFSCME locals separately
    # =====================================================================
    print("\n" + "=" * 80)
    print("14. ALL AFSCME-RELATED FILINGS IN NY (unions_master)")
    print("=" * 80)
    cur.execute("""
        SELECT f_num, union_name, members, city
        FROM unions_master
        WHERE state = 'NY'
          AND (LOWER(union_name) LIKE '%afscme%'
               OR LOWER(union_name) LIKE '%state county%'
               OR LOWER(union_name) LIKE '%csea%')
        ORDER BY members DESC NULLS LAST
        LIMIT 30
    """)
    rows = cur.fetchall()
    print("AFSCME/CSEA filings (top 30 by membership):")
    for r in rows:
        print("  f_num=%s | %s | members=%s | %s" % (r[0], r[1], r[2], r[3]))

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
