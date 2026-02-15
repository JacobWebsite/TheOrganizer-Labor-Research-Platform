import os
from db_config import get_connection
"""
Recalculate Form 990 estimates using FULL unified dues rates
Shows relationship between what org receives vs total member cost
"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

print("TEACHER UNION DUES STRUCTURE")
print("=" * 70)
print("""
When a teacher pays dues, it's split:
  Local Union     -->  keeps ~$150-300
  State Affiliate -->  keeps ~$400-550  
  NEA National    -->  receives ~$218 (professional) / $134 (blended)
  ---------------------------------------------------------------
  TOTAL UNIFIED   =   $700-950/year depending on state
""")

# Full unified dues by state (researched rates)
unified_dues = {
    'CA': 737,   # CTA - one of highest
    'NJ': 950,   # NJEA - highest in nation
    'NY': 650,   # NYSUT (varies by local)
    'PA': 620,   # PSEA
    'IL': 580,   # IEA  
    'OH': 550,   # OEA
    'MI': 520,   # MEA
    'WA': 560,   # WEA
    'FL': 480,   # FEA (RTW state, lower)
    'TX': 450,   # TSTA (RTW state)
    'MO': 480,   # MSTA
    'OK': 400,   # OEA (RTW, lower)
}

# What portion does the STATE affiliate receive (vs local + national)?
# Typically state gets 55-70% of unified dues
state_portion_pct = {
    'CA': 0.71,  # CTA gets ~$520 of $737
    'NJ': 0.50,  # NJEA gets ~$475 of $950
    'NY': 0.35,  # NYSUT - federation model, lower direct
    'PA': 0.71,  # PSEA
    'IL': 0.70,  # IEA
    'OH': 0.73,  # OEA
    'MI': 0.72,  # MEA
    'WA': 0.71,  # WEA
    'FL': 0.44,  # FEA - dual affiliate
    'TX': 0.75,  # TSTA
    'MO': 0.83,  # MSTA
    'OK': 0.79,  # OEA-OK
}

print("\nFULL UNIFIED DUES BY STATE")
print("=" * 70)
print(f"{'State':<6} {'Full Unified':<14} {'State Gets %':<14} {'State Portion'}")
print("-" * 70)
for st in sorted(unified_dues.keys()):
    full = unified_dues[st]
    pct = state_portion_pct.get(st, 0.65)
    portion = full * pct
    print(f"{st:<6} ${full:<13,} {pct*100:>6.0f}%          ${portion:,.0f}")

# Now recalculate membership estimates
# Formula: Members = 990_Revenue / State_Portion_Rate

print("\n" + "=" * 70)
print("RECALCULATED MEMBERSHIP ESTIMATES")
print("=" * 70)

# Get current 990 data
cur.execute("""
    SELECT organization_name, ein, state, dues_revenue, estimated_members, org_type
    FROM form_990_estimates
    WHERE org_type LIKE 'NEA%' OR org_type LIKE 'AFT_NEA%'
    ORDER BY dues_revenue DESC
""")
rows = cur.fetchall()

updates = []
print(f"\n{'Organization':<40} {'990 Revenue':>14} {'Full Rate':>10} {'New Est':>10} {'Old Est':>10}")
print("-" * 90)

for r in rows:
    name, ein, state, dues_rev, old_est, org_type = r
    dues_rev = float(dues_rev) if dues_rev else 0
    
    if org_type == 'NEA_NATIONAL':
        # NEA National - use blended per-capita, already validated
        full_rate = 134.44  # This IS what NEA receives per member
        new_est = int(dues_rev / full_rate) if dues_rev else 0
        note = "(validated)"
    elif state in unified_dues:
        # State affiliate - use the portion they actually receive
        full_unified = unified_dues[state]
        pct = state_portion_pct.get(state, 0.65)
        state_rate = full_unified * pct
        new_est = int(dues_rev / state_rate) if dues_rev else 0
        full_rate = state_rate
        note = f"(${full_unified} × {pct:.0%})"
    else:
        # Default
        full_rate = 450
        new_est = int(dues_rev / full_rate) if dues_rev else 0
        note = "(default)"
    
    if dues_rev:
        print(f"{name[:38]:<40} ${dues_rev:>12,.0f} ${full_rate:>8,.0f} {new_est:>10,} {old_est:>10,}")
        updates.append((new_est, full_rate, ein, 2024))

# Update database
print("\n" + "=" * 70)
print("UPDATING DATABASE...")

for new_est, rate, ein, year in updates:
    cur.execute("""
        UPDATE form_990_estimates 
        SET estimated_members = %s,
            dues_rate_used = %s,
            dues_rate_source = 'Full unified dues - state portion'
        WHERE ein = %s AND tax_year = %s
    """, (new_est, rate, ein, year))

conn.commit()
print(f"Updated {len(updates)} records")

# Show summary comparison
print("\n" + "=" * 70)
print("COMPARISON: OLD vs NEW ESTIMATES")
print("=" * 70)

cur.execute("""
    SELECT organization_name, state, estimated_members, dues_rate_used
    FROM form_990_estimates
    WHERE org_type LIKE 'NEA%' OR org_type LIKE 'AFT_NEA%'
    ORDER BY estimated_members DESC
""")

total = 0
for r in cur.fetchall():
    name, state, members, rate = r
    print(f"  {name[:42]:<44} {state:>2}  {members:>10,} @ ${rate:,.0f}")
    total += members or 0

print("-" * 70)
print(f"  {'TOTAL TEACHER UNION MEMBERS':<44}     {total:>10,}")

# Also show full unified dues for reference
print("\n" + "=" * 70)
print("REFERENCE: What Teachers Actually Pay (Full Unified)")
print("=" * 70)
print("""
  New Jersey (NJEA)     $950/year  - Highest in nation
  California (CTA)      $737/year  
  Pennsylvania (PSEA)   $620/year
  New York (NYSUT)      $650/year  - Varies by local
  Illinois (IEA)        $580/year
  Ohio (OEA)            $550/year
  Michigan (MEA)        $520/year
  Texas (TSTA)          $450/year  - RTW state
  Oklahoma (OEA)        $400/year  - RTW state
""")

conn.close()
