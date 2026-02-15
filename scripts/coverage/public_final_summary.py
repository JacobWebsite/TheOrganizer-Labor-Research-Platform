import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("PUBLIC SECTOR UNION COVERAGE - CORRECTED ANALYSIS")
print("=" * 80)

# Define public sector affiliations
public_sector_affs = [
    # Federal
    'AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NPMHU', 'NAGE', 'NRLCA',
    # Teachers
    'NEA', 'AFT',
    # State/Local
    'AFSCME', 'IAFF', 'FOP', 'PBA'
]

# Mixed unions with public sector portions
mixed_unions = {
    'SEIU': 0.40,   # ~40% public
    'CWA': 0.25,    # ~25% public
    'ATU': 0.85,    # ~85% public (transit)
    'OPEIU': 0.15,  # ~15% public
    'LIUNA': 0.10,  # ~10% public works
}

print("\n" + "=" * 80)
print("1. NATIONAL HEADQUARTERS MEMBERSHIP (Primary Source)")
print("=" * 80)

# Get NHQ filings - DC-based, LM-2 form, largest per affiliation
# Excluding obvious data errors (members > reasonable for local)

cur.execute("""
    WITH nhq_candidates AS (
        SELECT 
            aff_abbr,
            union_name,
            unit_name,
            state,
            COALESCE(members, 0) as members,
            form_type,
            -- Flag suspicious entries (small locals with huge membership)
            CASE 
                WHEN form_type = 'LM-4' AND members > 100000 THEN TRUE
                WHEN form_type = 'LM-3' AND members > 500000 THEN TRUE
                ELSE FALSE
            END as suspicious,
            ROW_NUMBER() OVER (
                PARTITION BY aff_abbr 
                ORDER BY 
                    -- Prefer DC headquarters
                    CASE WHEN state = 'DC' THEN 0 ELSE 1 END,
                    -- Prefer LM-2 (largest unions)
                    CASE form_type WHEN 'LM-2' THEN 0 WHEN 'LM-3' THEN 1 ELSE 2 END,
                    -- Then by membership
                    members DESC NULLS LAST
            ) as rn
        FROM lm_data
        WHERE yr_covered = 2024
        AND aff_abbr = ANY(%s)
    )
    SELECT aff_abbr, union_name, unit_name, state, members, form_type, suspicious
    FROM nhq_candidates
    WHERE rn = 1
    ORDER BY members DESC;
""", (public_sector_affs,))

results = {}
print(f"\n{'Aff':8} {'State':5} {'Form':5} {'Members':>12}  Notes")
print("-" * 80)

for row in cur.fetchall():
    aff, name, unit, state, members, form, suspicious = row
    
    # Skip suspicious entries and use alternative
    if suspicious:
        print(f"{aff:8} {state or 'NA':5} {form:5} {members:>12,.0f}  ** DATA ERROR - SKIPPING")
        # Get the next best entry
        cur.execute("""
            SELECT COALESCE(members,0), state, form_type
            FROM lm_data
            WHERE yr_covered = 2024 AND aff_abbr = %s
            AND NOT (form_type = 'LM-4' AND members > 100000)
            ORDER BY members DESC LIMIT 1;
        """, (aff,))
        alt = cur.fetchone()
        if alt:
            members = alt[0]
            print(f"{'':8} {alt[1] or 'NA':5} {alt[2]:5} {members:>12,.0f}  (using alt)")
    else:
        display = (unit if unit else name)[:40]
        print(f"{aff:8} {state or 'NA':5} {form:5} {members:>12,.0f}  {display}")
    
    results[aff] = members

# Calculate totals by category
print("\n" + "=" * 80)
print("2. MEMBERSHIP BY CATEGORY")
print("=" * 80)

# Federal
federal_affs = ['AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NPMHU', 'NAGE', 'NRLCA']
fed_total = sum(results.get(a, 0) for a in federal_affs)
print(f"\nFEDERAL EMPLOYEES:")
for a in federal_affs:
    if results.get(a, 0) > 0:
        print(f"  {a:10} {results[a]:>12,.0f}")
print(f"  {'SUBTOTAL':10} {fed_total:>12,.0f}")

# Teachers (with overlap adjustment)
nea = results.get('NEA', 0)
aft = results.get('AFT', 0)
# ~900K are dual members of both NEA and AFT
overlap = 900000
teacher_total = nea + aft - overlap
print(f"\nTEACHERS:")
print(f"  NEA:       {nea:>12,.0f}")
print(f"  AFT:       {aft:>12,.0f}")
print(f"  Overlap:   {-overlap:>12,.0f}  (est. dual members)")
print(f"  SUBTOTAL:  {teacher_total:>12,.0f}")

# State/Local (non-mixed)
statelocal_affs = ['AFSCME', 'IAFF', 'FOP', 'PBA']
statelocal_total = sum(results.get(a, 0) for a in statelocal_affs)
print(f"\nSTATE/LOCAL GOVERNMENT:")
for a in statelocal_affs:
    if results.get(a, 0) > 0:
        print(f"  {a:10} {results[a]:>12,.0f}")
print(f"  {'SUBTOTAL':10} {statelocal_total:>12,.0f}")

# Mixed unions - get their NHQ totals
print(f"\nMIXED UNIONS (Public Portion):")
mixed_public = 0
for aff, pct in mixed_unions.items():
    cur.execute("""
        SELECT COALESCE(members,0) FROM lm_data
        WHERE yr_covered = 2024 AND aff_abbr = %s
        AND form_type = 'LM-2'
        ORDER BY members DESC LIMIT 1;
    """, (aff,))
    row = cur.fetchone()
    total = row[0] if row else 0
    public = int(total * pct)
    if total > 0:
        print(f"  {aff:10} {total:>12,.0f} x {pct*100:.0f}% = {public:>10,.0f}")
        mixed_public += public
print(f"  {'SUBTOTAL':10} {'':>12} {mixed_public:>12,.0f}")

# Grand total
grand_total = fed_total + teacher_total + statelocal_total + mixed_public

print("\n" + "=" * 80)
print("3. FINAL SUMMARY")
print("=" * 80)

print(f"""
CATEGORY                       MEMBERS    % of 7M
-------------------------------------------------------
Federal employees:         {fed_total:>12,.0f}    {fed_total/7000000*100:5.1f}%
Teachers (NEA+AFT adj.):   {teacher_total:>12,.0f}    {teacher_total/7000000*100:5.1f}%
State/Local (AFSCME+):     {statelocal_total:>12,.0f}    {statelocal_total/7000000*100:5.1f}%
Mixed (SEIU/CWA/ATU etc):  {mixed_public:>12,.0f}    {mixed_public/7000000*100:5.1f}%
=======================================================
TOTAL COVERED IN OLMS:     {grand_total:>12,.0f}    {grand_total/7000000*100:5.1f}%

BLS BENCHMARK:                 7,000,000   100.0%
-------------------------------------------------------
GAP:                       {7000000 - grand_total:>12,.0f}    {(7000000-grand_total)/7000000*100:5.1f}%
""")

# Breakdown of what's in the gap
print("=" * 80)
print("4. GAP ANALYSIS - MISSING ~{:,.0f} PUBLIC WORKERS".format(7000000 - grand_total))
print("=" * 80)

print("""
KNOWN MISSING CATEGORIES:

A. INDEPENDENT STATE EMPLOYEE ASSOCIATIONS (~500K-800K)
   - California State Employees Assn (CSEA-SEIU Local 1000)
   - Texas State Employees Union
   - Many file as SEIU locals now, others don't file OLMS

B. POLICE NOT IN FOP (~200-300K)
   - Patrolmen's Benevolent Associations (NYC PBA: ~24K)
   - State-specific police unions
   - Sheriff's associations
   
C. NURSES IN PUBLIC HOSPITALS (~150-250K)
   - Counted in SEIU, but may be undercounted
   - NNU in public hospitals
   
D. PUBLIC UNIVERSITY EMPLOYEES (~100-200K)
   - Faculty unions (AAUP, independents)
   - Graduate student unions
   - Classified staff
   
E. PURELY PUBLIC SECTOR UNIONS (~200-400K)
   - OLMS filing NOT required if no private sector members
   - Many local government unions exempt
   
F. DATA QUALITY / TIMING ISSUES
   - Some unions report members differently
   - Fiscal year vs calendar year differences
""")

print("=" * 80)
print("5. PUBLIC SECTOR EMPLOYER STATUS")
print("=" * 80)

print(f"""
CURRENT DATABASE STATUS:
  Private sector employers (F-7):     ~150,000 employers
  Public sector employers:                    0 employers

DATA SOURCES NEEDED FOR PUBLIC EMPLOYERS:

| Source              | Agency | Employers | Est. Workers |
|---------------------|--------|-----------|--------------|
| FLRA Agency File    | FLRA   | ~100      | ~600K federal|
| NCES School Districts| DoEd  | ~13,500   | ~3.7M teachers|
| NY PERB             | NY State| ~2,000   | ~1M state/local|
| CA PERB             | CA State| ~3,000   | ~1.5M        |
| NJ PERC             | NJ State| ~1,000   | ~400K        |
| Other State PERBs   | Various | ~5,000   | ~2M          |
| Census of Govts     | Census  | ~90,000  | comprehensive|

RECOMMENDED STARTING POINTS:
1. NCES School Districts - covers largest category (teachers)
2. FLRA Federal Agencies - cleanest, centralized data
3. NY PERB - highest volume single state, has DC37 etc.
""")

conn.close()
