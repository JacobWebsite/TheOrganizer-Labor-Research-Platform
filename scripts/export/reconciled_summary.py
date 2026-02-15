import os
from db_config import get_connection
"""
FINAL RECONCILED PLATFORM SUMMARY
Properly accounts for overlap between OLMS and Form 990 data
"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

print("=" * 90)
print("LABOR RELATIONS PLATFORM - RECONCILED MEMBERSHIP SUMMARY")
print("=" * 90)

# ============================================================================
# KEY INSIGHT: Overlap exists between OLMS and 990 data
# ============================================================================
print("""
DATA SOURCE OVERLAP:
  - NEA files BOTH Department of Labor LM-2 forms AND IRS Form 990
  - AFSCME International files BOTH LM-2 and 990
  - SEIU International files BOTH LM-2 and 990
  
To avoid double-counting, we need to:
  1. Use OLMS for PRIVATE sector unions
  2. Use Form 990 for PUBLIC sector unions (teachers, police, fire, state/municipal)
  3. Use FLRA for FEDERAL sector
""")

# ============================================================================
# STEP 1: Get OLMS private sector only (exclude public sector unions)
# ============================================================================
print("\n" + "=" * 70)
print("STEP 1: OLMS DATA - PRIVATE SECTOR ONLY")
print("=" * 70)

# Get OLMS totals excluding major public sector unions
cur.execute("""
    SELECT SUM(counted_members)
    FROM v_deduplicated_membership
    WHERE aff_abbr NOT IN ('NEA', 'AFT', 'AFSCME', 'SEIU', 'FOP', 'IAFF', 'PBA')
    AND aff_abbr NOT LIKE '%TEACH%'
    AND aff_abbr NOT LIKE '%EDUC%'
    AND aff_abbr NOT LIKE '%FIRE%'
    AND aff_abbr NOT LIKE '%POLICE%'
""")
olms_private = cur.fetchone()[0] or 0

# Also get SEIU/AFSCME private sector portions (healthcare, building services)
# These are legitimately private sector
cur.execute("""
    SELECT SUM(counted_members)
    FROM v_deduplicated_membership
    WHERE aff_abbr IN ('SEIU', 'AFSCME')
""")
seiu_afscme_olms = cur.fetchone()[0] or 0

# Estimate private sector portion of SEIU/AFSCME (roughly 40% based on BLS)
seiu_afscme_private = int(seiu_afscme_olms * 0.4)

print(f"  OLMS excluding public sector unions: {int(olms_private):,}")
print(f"  SEIU/AFSCME in OLMS:                 {int(seiu_afscme_olms):,}")
print(f"  Est. private portion (40%):          {seiu_afscme_private:,}")
print(f"  ADJUSTED PRIVATE SECTOR:             {int(olms_private) + seiu_afscme_private:,}")

private_sector_total = int(olms_private) + seiu_afscme_private

# ============================================================================
# STEP 2: Form 990 Public Sector (State/Local)
# ============================================================================
print("\n" + "=" * 70)
print("STEP 2: FORM 990 DATA - STATE/LOCAL PUBLIC SECTOR")
print("=" * 70)

cur.execute("""
    SELECT SUM(estimated_members)
    FROM form_990_estimates
    WHERE org_type IN ('NEA_NATIONAL', 'FOP_NATIONAL', 'IAFF_NATIONAL',
                       'AFSCME_NATIONAL', 'SEIU_NATIONAL', 'PBA_LOCAL', 'PBA_STATE')
""")
public_sector_990 = cur.fetchone()[0] or 0

# Break down by category
cur.execute("SELECT SUM(estimated_members) FROM form_990_estimates WHERE org_type = 'NEA_NATIONAL'")
teachers = cur.fetchone()[0] or 0

cur.execute("SELECT SUM(estimated_members) FROM form_990_estimates WHERE org_type IN ('FOP_NATIONAL', 'PBA_LOCAL', 'PBA_STATE')")
police = cur.fetchone()[0] or 0

cur.execute("SELECT SUM(estimated_members) FROM form_990_estimates WHERE org_type = 'IAFF_NATIONAL'")
firefighters = cur.fetchone()[0] or 0

cur.execute("SELECT SUM(estimated_members) FROM form_990_estimates WHERE org_type IN ('AFSCME_NATIONAL', 'SEIU_NATIONAL')")
state_muni = cur.fetchone()[0] or 0

# Adjust AFSCME/SEIU for public sector only (60%)
state_muni_public = int(state_muni * 0.6)

print(f"  Teachers (NEA National):             {int(teachers):,}")
print(f"  Police (FOP + PBA):                  {int(police):,}")
print(f"  Firefighters (IAFF):                 {int(firefighters):,}")
print(f"  AFSCME/SEIU Total:                   {int(state_muni):,}")
print(f"  Est. public portion (60%):           {state_muni_public:,}")
print(f"  ADJUSTED STATE/LOCAL PUBLIC:         {int(teachers) + int(police) + int(firefighters) + state_muni_public:,}")

state_local_total = int(teachers) + int(police) + int(firefighters) + state_muni_public

# ============================================================================
# STEP 3: FLRA Federal Sector
# ============================================================================
print("\n" + "=" * 70)
print("STEP 3: FLRA DATA - FEDERAL SECTOR")
print("=" * 70)

cur.execute("SELECT COUNT(*), SUM(total_in_unit) FROM federal_bargaining_units")
flra = cur.fetchone()
federal_units = flra[0] or 0
federal_employees = int(flra[1]) if flra[1] else 0

print(f"  Bargaining Units:                    {federal_units:,}")
print(f"  Federal Employees:                   {federal_employees:,}")

# ============================================================================
# RECONCILED TOTALS
# ============================================================================
print("\n" + "=" * 90)
print("RECONCILED PLATFORM TOTALS")
print("=" * 90)

platform_total = private_sector_total + state_local_total + federal_employees

print(f"""
Sector                      Platform Est.     BLS 2024      Variance
-----------------------------------------------------------------------
Private Sector              {private_sector_total:>12,}    {7400000:>12,}    {private_sector_total - 7400000:>+10,}
State/Local Public          {state_local_total:>12,}    {5700000:>12,}    {state_local_total - 5700000:>+10,}
Federal                     {federal_employees:>12,}    {1200000:>12,}    {federal_employees - 1200000:>+10,}
-----------------------------------------------------------------------
TOTAL                       {platform_total:>12,}    {14300000:>12,}    {platform_total - 14300000:>+10,}

Coverage: {platform_total/14300000*100:.1f}% of BLS Total
""")

# ============================================================================
# PUBLIC SECTOR CATEGORY DETAIL
# ============================================================================
print("=" * 90)
print("PUBLIC SECTOR BREAKDOWN (State/Local + Federal)")
print("=" * 90)

total_public = state_local_total + federal_employees

print(f"""
Category                        Members         % of Public
----------------------------------------------------------------
Teachers (NEA):                 {int(teachers):>10,}         {teachers/total_public*100:>5.1f}%
Police (FOP/PBA):               {int(police):>10,}         {police/total_public*100:>5.1f}%
Firefighters (IAFF):            {int(firefighters):>10,}         {firefighters/total_public*100:>5.1f}%
State/Muni (AFSCME/SEIU):       {state_muni_public:>10,}         {state_muni_public/total_public*100:>5.1f}%
Federal (FLRA):                 {federal_employees:>10,}         {federal_employees/total_public*100:>5.1f}%
----------------------------------------------------------------
TOTAL PUBLIC SECTOR:            {total_public:>10,}         100.0%

BLS Public Sector Total:        {6900000:>10,}
Variance:                       {total_public - 6900000:>+10,}
Coverage:                       {total_public/6900000*100:>9.1f}%
""")

# ============================================================================
# DATA QUALITY ASSESSMENT
# ============================================================================
print("=" * 90)
print("DATA QUALITY ASSESSMENT")
print("=" * 90)

print(f"""
Form 990 Confidence Levels:
""")
cur.execute("""
    SELECT confidence_level, COUNT(*), SUM(estimated_members)
    FROM form_990_estimates
    GROUP BY confidence_level
    ORDER BY 
        CASE confidence_level 
            WHEN 'HIGH' THEN 1 
            WHEN 'MEDIUM' THEN 2 
            WHEN 'LOW' THEN 3 
        END
""")
for row in cur.fetchall():
    conf, count, members = row
    print(f"  {conf:<10} {count:>3} orgs    {int(members):>12,} members")

print(f"""
Methodology Notes:
  - NEA per-capita VALIDATED against LM-2 data ($134.44/member blended)
  - FOP national per-capita CONFIRMED at $11.50/year (research finding)
  - IAFF per-capita from official IAFF convention resolutions (~$190/year)
  - AFSCME/SEIU per-capita from published constitutional rates
  - State affiliate rates back-calculated from published membership + 990 revenue
  
Key Assumptions:
  - SEIU/AFSCME split 40% private / 60% public (based on BLS sector data)
  - State affiliates retain 70-80% of dues (national per-capita pass-through)
  - FOP Grand Lodge receives only $11.50/member (very low national per-capita)
""")

conn.close()
print("=" * 90)
