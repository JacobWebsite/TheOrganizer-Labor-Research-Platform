"""
Data Assessment for Union Case Studies
3 Unions (SEIU, Teamsters/IBT, AFSCME) x 3 States (NY, MN, VA)
"""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

print('=' * 80)
print('PART 1: F-7 EMPLOYER FOOTPRINT (Private Sector CBAs)')
print('=' * 80)

# F-7 Employer counts by union affiliation and state
cur.execute('''
    SELECT 
        u.aff_abbr,
        e.state,
        COUNT(DISTINCT e.employer_id) as employer_count,
        COALESCE(SUM(e.latest_unit_size), 0) as total_workers
    FROM f7_employers_deduped e
    JOIN unions_master u ON e.latest_union_fnum::text = u.f_num::text
    WHERE u.aff_abbr IN ('SEIU', 'IBT', 'AFSCME')
      AND e.state IN ('NY', 'MN', 'VA')
    GROUP BY u.aff_abbr, e.state
    ORDER BY u.aff_abbr, e.state
''')

results = cur.fetchall()

# Build matrix
matrix_f7 = {}
for row in results:
    union, state, employers, workers = row
    if union not in matrix_f7:
        matrix_f7[union] = {}
    matrix_f7[union][state] = (employers, int(workers))

print("\nF-7 Employers (workers in parentheses):")
print("-" * 55)
header = f"{'Union':<12} {'NY':<15} {'MN':<15} {'VA':<15}"
print(header)
print("-" * 55)

for union in ['SEIU', 'IBT', 'AFSCME']:
    row_str = f'{union:<12}'
    for state in ['NY', 'MN', 'VA']:
        if union in matrix_f7 and state in matrix_f7[union]:
            e, w = matrix_f7[union][state]
            cell = f"{e} ({w:,})"
        else:
            cell = "0 (0)"
        row_str += f'{cell:<15}'
    print(row_str)

print('\n' + '=' * 80)
print('PART 2: NLRB ELECTIONS (2015-2025)')
print('=' * 80)

# NLRB Elections by union and state
cur.execute('''
    SELECT 
        u.aff_abbr,
        n.state,
        COUNT(*) as elections,
        SUM(CASE WHEN n.won THEN 1 ELSE 0 END) as wins,
        ROUND(100.0 * SUM(CASE WHEN n.won THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as win_rate
    FROM nlrb_elections n
    JOIN nlrb_participants p ON n.case_number = p.case_number
    JOIN unions_master u ON p.matched_olms_fnum::text = u.f_num::text
    WHERE u.aff_abbr IN ('SEIU', 'IBT', 'AFSCME')
      AND n.state IN ('NY', 'MN', 'VA')
      AND n.date_filed >= '2015-01-01'
    GROUP BY u.aff_abbr, n.state
    ORDER BY u.aff_abbr, n.state
''')

results = cur.fetchall()

matrix_nlrb = {}
for row in results:
    union, state, elections, wins, win_rate = row
    if union not in matrix_nlrb:
        matrix_nlrb[union] = {}
    matrix_nlrb[union][state] = (elections, wins, float(win_rate) if win_rate else 0)

print("\nNLRB Elections (wins / total, win rate %):")
print("-" * 70)
header = f"{'Union':<12} {'NY':<20} {'MN':<20} {'VA':<20}"
print(header)
print("-" * 70)

for union in ['SEIU', 'IBT', 'AFSCME']:
    row_str = f'{union:<12}'
    for state in ['NY', 'MN', 'VA']:
        if union in matrix_nlrb and state in matrix_nlrb[union]:
            e, w, r = matrix_nlrb[union][state]
            cell = f"{w}/{e} ({r}%)"
        else:
            cell = "0/0 (0%)"
        row_str += f'{cell:<20}'
    print(row_str)

print('\n' + '=' * 80)
print('PART 3: PUBLIC SECTOR FOOTPRINT')
print('=' * 80)

# Public sector locals
cur.execute('''
    SELECT 
        parent_abbr,
        state,
        COUNT(*) as locals,
        COALESCE(SUM(members), 0) as members
    FROM ps_union_locals
    WHERE parent_abbr IN ('SEIU', 'IBT', 'AFSCME')
      AND state IN ('NY', 'MN', 'VA')
    GROUP BY parent_abbr, state
    ORDER BY parent_abbr, state
''')

results = cur.fetchall()

matrix_ps = {}
for row in results:
    union, state, locals, members = row
    if union not in matrix_ps:
        matrix_ps[union] = {}
    matrix_ps[union][state] = (locals, int(members))

print("\nPublic Sector Locals (members in parentheses):")
print("-" * 55)
header = f"{'Union':<12} {'NY':<15} {'MN':<15} {'VA':<15}"
print(header)
print("-" * 55)

for union in ['SEIU', 'IBT', 'AFSCME']:
    row_str = f'{union:<12}'
    for state in ['NY', 'MN', 'VA']:
        if union in matrix_ps and state in matrix_ps[union]:
            l, m = matrix_ps[union][state]
            cell = f"{l} ({m:,})"
        else:
            cell = "0 (0)"
        row_str += f'{cell:<15}'
    print(row_str)

print('\n' + '=' * 80)
print('PART 4: OSHA TARGET UNIVERSE BY RELEVANT NAICS')
print('=' * 80)

# Define NAICS codes relevant to each union
union_naics = {
    'SEIU': ['622110', '622210', '622310', '623110', '623210', '623311', '623312',
             '561720', '561210', '624110', '624120', '624190'],
    'IBT': ['484110', '484121', '484122', '484210', '484220', '484230',
            '493110', '493120', '493130', '492110', '492210',
            '311', '312', '424'],  # Food/beverage manufacturing, wholesale
    'AFSCME': ['921110', '921120', '921130', '921140', '921150', '921190',
               '922110', '922120', '922130', '922140', '922150', '922160',
               '712110', '712120', '712130']
}

print("\nOSHA Establishments by Union-Relevant NAICS:")
print("-" * 70)

for union, naics_list in union_naics.items():
    # Build NAICS pattern for LIKE matching (for 3-digit codes like '311')
    naics_conditions = []
    params = []
    for n in naics_list:
        if len(n) <= 3:
            naics_conditions.append("naics_code LIKE %s")
            params.append(f"{n}%")
        else:
            naics_conditions.append("naics_code = %s")
            params.append(n)
    
    naics_where = " OR ".join(naics_conditions)
    
    for state in ['NY', 'MN', 'VA']:
        query = f'''
            SELECT 
                COUNT(*) as establishments,
                COALESCE(SUM(CASE WHEN nr_in_estab > 0 THEN nr_in_estab ELSE 0 END), 0) as employees
            FROM osha_establishments
            WHERE state = %s
              AND ({naics_where})
        '''
        cur.execute(query, [state] + params)
        result = cur.fetchone()
        estabs, emps = result[0], int(result[1])
        print(f"{union:<10} {state}: {estabs:,} establishments, {emps:,} employees")
    print()

print('=' * 80)
print('PART 5: EXISTING ORGANIZING TARGETS (990 + Contracts)')
print('=' * 80)

# Check if organizing_targets table exists and has data for these states
cur.execute('''
    SELECT 
        state,
        COUNT(*) as targets,
        SUM(CASE WHEN priority_tier = 'TOP' THEN 1 ELSE 0 END) as top_tier,
        SUM(CASE WHEN priority_tier = 'HIGH' THEN 1 ELSE 0 END) as high_tier,
        COALESCE(SUM(total_funding), 0) as total_funding
    FROM organizing_targets
    WHERE state IN ('NY', 'MN', 'VA')
    GROUP BY state
    ORDER BY state
''')

results = cur.fetchall()
print("\nOrganizing Targets (990 + Contract data):")
print("-" * 70)
print(f"{'State':<8} {'Total':<10} {'TOP':<8} {'HIGH':<8} {'Funding':<15}")
print("-" * 70)
for row in results:
    state, total, top, high, funding = row
    print(f"{state:<8} {total:<10} {top:<8} {high:<8} ${funding:,.0f}")

print('\n' + '=' * 80)
print('PART 6: DATA AVAILABILITY SUMMARY')
print('=' * 80)

# Summary of what data exists
cur.execute('''
    SELECT 
        'NY State Contracts' as source, COUNT(*) as records
    FROM ny_state_contracts
    UNION ALL
    SELECT 
        'NYC Contracts' as source, COUNT(*) as records
    FROM nyc_contracts
    UNION ALL
    SELECT 
        '990 Employers' as source, COUNT(*) as records
    FROM employers_990
''')

print("\nContract/990 Data Available:")
print("-" * 40)
for row in cur.fetchall():
    print(f"{row[0]:<25} {row[1]:,}")

# Check for MN and VA specific data
print("\nState-Specific Data Gaps:")
print("-" * 40)
print("NY: Full coverage (state + city contracts, 990 data)")
print("MN: No state contract data loaded")
print("VA: No state contract data loaded")

conn.close()

print('\n' + '=' * 80)
print('ASSESSMENT COMPLETE')
print('=' * 80)
