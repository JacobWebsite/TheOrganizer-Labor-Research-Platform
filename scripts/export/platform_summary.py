"""
Platform Integration Summary - Combining all data sources
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

print("=" * 90)
print("LABOR RELATIONS PLATFORM - COMPLETE COVERAGE SUMMARY")
print("=" * 90)

# ============================================================================
# 1. OLMS LM DATA (Private Sector + Some Public)
# ============================================================================
print("\n1. OLMS LM FORMS (Private Sector + Some Public)")
print("-" * 70)

# Get latest year data
cur.execute("""
    SELECT MAX(yr_covered) FROM lm_data
""")
latest_year = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(DISTINCT f_num), SUM(members)
    FROM lm_data
    WHERE yr_covered = %s
""", (latest_year,))
lm = cur.fetchone()
print(f"  Latest Year: {latest_year}")
print(f"  Organizations: {lm[0]:,}")
print(f"  Raw Members: {lm[1]:,}")

# Get deduplicated view if exists
cur.execute("""
    SELECT SUM(counted_members) FROM v_deduplicated_membership
""")
dedup = cur.fetchone()[0]
if dedup:
    print(f"  Deduplicated Members: {int(dedup):,}")

# ============================================================================
# 2. FLRA FEDERAL SECTOR DATA
# ============================================================================
print("\n2. FLRA DATA (Federal Sector)")
print("-" * 70)

cur.execute("""
    SELECT COUNT(*), SUM(total_in_unit)
    FROM federal_bargaining_units
""")
flra = cur.fetchone()
print(f"  Bargaining Units: {flra[0]:,}")
print(f"  Federal Employees: {int(flra[1]):,}" if flra[1] else "  Federal Employees: N/A")

# ============================================================================
# 3. FORM 990 PUBLIC SECTOR ESTIMATES
# ============================================================================
print("\n3. FORM 990 ESTIMATES (State/Local Public Sector)")
print("-" * 70)

cur.execute("""
    SELECT org_type, COUNT(*), SUM(estimated_members), ROUND(AVG(dues_rate_used)::numeric, 0)
    FROM form_990_estimates
    GROUP BY org_type
    ORDER BY SUM(estimated_members) DESC
""")
rows = cur.fetchall()
print(f"  {'Org Type':<20} {'Orgs':>5} {'Members':>12} {'Avg Rate':>10}")
print(f"  " + "-" * 52)
total_990 = 0
for r in rows:
    org_type, orgs, members, rate = r
    print(f"  {org_type:<20} {orgs:>5} {members:>12,} ${rate:>8,}")
    total_990 += members

print(f"  " + "-" * 52)
print(f"  {'TOTAL':<20} {len(rows):>5} {total_990:>12,}")

# Get deduplicated 990 total (using national level to avoid double-counting)
cur.execute("""
    SELECT SUM(estimated_members) 
    FROM form_990_estimates 
    WHERE org_type IN ('NEA_NATIONAL', 'FOP_NATIONAL', 'IAFF_NATIONAL', 
                       'AFSCME_NATIONAL', 'SEIU_NATIONAL', 'PBA_LOCAL', 'PBA_STATE')
""")
dedup_990 = cur.fetchone()[0] or 0
print(f"\n  Deduplicated (using national level): {int(dedup_990):,}")

# ============================================================================
# 4. NLRB ELECTION DATA
# ============================================================================
print("\n4. NLRB ELECTION DATA (Organizing Activity)")
print("-" * 70)

cur.execute("""
    SELECT COUNT(*), SUM(eligible_voters)
    FROM nlrb_elections
""")
nlrb = cur.fetchone()
print(f"  Total Elections: {nlrb[0]:,}")
print(f"  Eligible Voters: {int(nlrb[1]):,}" if nlrb[1] else "  Eligible Voters: N/A")

# ============================================================================
# 5. F-7 EMPLOYER BARGAINING DATA
# ============================================================================
print("\n5. F-7 EMPLOYER BARGAINING NOTICES")
print("-" * 70)

cur.execute("""
    SELECT COUNT(*), SUM(latest_unit_size)
    FROM f7_employers
""")
f7 = cur.fetchone()
print(f"  Employer Agreements: {f7[0]:,}")
print(f"  Workers Covered: {int(f7[1]):,}" if f7[1] else "  Workers Covered: N/A")

# ============================================================================
# PLATFORM SUMMARY
# ============================================================================
print("\n" + "=" * 90)
print("PLATFORM COVERAGE SUMMARY")
print("=" * 90)

# Calculate combined totals
private_sector = int(dedup) if dedup else 14500000  # OLMS deduplicated
federal_sector = int(flra[1]) if flra[1] else 1280000  # FLRA
public_sector = int(dedup_990)  # 990 estimates

print(f"""
DATA SOURCE               ORGANIZATIONS    MEMBERS (Dedup)
--------------------------------------------------------------
OLMS LM Forms (Private)   {lm[0]:>10,}      {private_sector:>12,}
FLRA (Federal)            {flra[0]:>10,}      {federal_sector:>12,}
Form 990 (State/Local)    {len(rows):>10}      {public_sector:>12,}
--------------------------------------------------------------
PLATFORM TOTAL                             {private_sector + federal_sector + public_sector:>12,}
""")

# BLS Comparison
print("\nCOMPARISON WITH BLS DATA (2024)")
print("-" * 70)
print("""
BLS Union Membership:
  Private Sector:   7,400,000 (6.0% density)
  Public Sector:    6,900,000 (32.5% density)
    - Federal:      1,200,000
    - State:        2,100,000
    - Local:        3,600,000
  ----------------------------------------
  TOTAL:           14,300,000
""")

platform_total = private_sector + federal_sector + public_sector
bls_total = 14300000

print(f"Platform Estimate:     {platform_total:>12,}")
print(f"BLS Total:             {bls_total:>12,}")
print(f"Difference:            {platform_total - bls_total:>+12,}")
print(f"Coverage Ratio:        {platform_total/bls_total*100:>11.1f}%")

# Sector breakdown comparison
print("\nSECTOR BREAKDOWN COMPARISON")
print("-" * 70)
print(f"{'Sector':<25} {'Platform':>14} {'BLS':>14} {'Variance':>12}")
print("-" * 70)

# Note: OLMS includes some public sector unions that also file LM forms
# NEA files both LM-2 and 990, so there's overlap
olms_public_overlap = 2800000  # NEA, AFSCME, SEIU file both LM and 990
adjusted_private = private_sector - olms_public_overlap

print(f"{'Private Sector':<25} {adjusted_private:>14,} {7400000:>14,} {adjusted_private - 7400000:>+12,}")
print(f"{'Federal Sector':<25} {federal_sector:>14,} {1200000:>14,} {federal_sector - 1200000:>+12,}")
print(f"{'State/Local Public':<25} {public_sector + olms_public_overlap:>14,} {5700000:>14,} {(public_sector + olms_public_overlap) - 5700000:>+12,}")

print("""
NOTE: Some unions (NEA, AFSCME, SEIU) file both LM forms and 990s.
The 'adjusted' figures account for this overlap.
""")

# ============================================================================
# PUBLIC SECTOR CATEGORY BREAKDOWN
# ============================================================================
print("=" * 90)
print("PUBLIC SECTOR DETAILED BREAKDOWN (Form 990 Estimates)")
print("=" * 90)

# Teachers
cur.execute("""
    SELECT SUM(estimated_members) 
    FROM form_990_estimates 
    WHERE org_type = 'NEA_NATIONAL'
""")
teachers = cur.fetchone()[0] or 0

# Police
cur.execute("""
    SELECT SUM(estimated_members) 
    FROM form_990_estimates 
    WHERE org_type IN ('FOP_NATIONAL', 'PBA_LOCAL', 'PBA_STATE')
""")
police = cur.fetchone()[0] or 0

# Firefighters
cur.execute("""
    SELECT SUM(estimated_members) 
    FROM form_990_estimates 
    WHERE org_type = 'IAFF_NATIONAL'
""")
fire = cur.fetchone()[0] or 0

# State/Municipal
cur.execute("""
    SELECT SUM(estimated_members) 
    FROM form_990_estimates 
    WHERE org_type IN ('AFSCME_NATIONAL', 'SEIU_NATIONAL')
""")
state_muni = cur.fetchone()[0] or 0

print(f"""
Public Sector Category              Estimated Members
--------------------------------------------------------
Teachers (NEA):                     {int(teachers):>12,}
Police (FOP + PBA):                 {int(police):>12,}
Firefighters (IAFF):                {int(fire):>12,}
State/Municipal (AFSCME + SEIU):    {int(state_muni):>12,}
--------------------------------------------------------
TOTAL STATE/LOCAL PUBLIC:           {int(teachers + police + fire + state_muni):>12,}

+ Federal Employees (FLRA):         {federal_sector:>12,}
--------------------------------------------------------
TOTAL PUBLIC SECTOR:                {int(teachers + police + fire + state_muni) + federal_sector:>12,}

BLS Public Sector Total:            {6900000:>12,}
Coverage:                           {(int(teachers + police + fire + state_muni) + federal_sector)/6900000*100:>11.1f}%
""")

conn.close()
print("=" * 90)
