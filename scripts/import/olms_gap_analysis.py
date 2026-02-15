import os
from db_config import get_connection
"""
OLMS vs Published Membership: Identifying Gaps
Form 990 serves as validation, not primary data
"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

print("=" * 90)
print("OLMS DATA vs PUBLISHED MEMBERSHIP - GAP ANALYSIS")
print("=" * 90)
print("""
PURPOSE: Compare OLMS LM data against published/claimed membership to identify:
  1. Data quality issues in OLMS
  2. Public sector gaps (members not captured in LM filings)
  3. Hierarchy/deduplication issues
""")

# Known published membership claims (from union websites, press releases)
published_membership = {
    'AFSCME': 1400000,    # AFSCME claims ~1.4 million members
    'SEIU': 2000000,      # SEIU claims ~2 million members  
    'NEA': 2900000,       # NEA claims ~2.9 million members
    'AFT': 1700000,       # AFT claims ~1.7 million members
    'IAFF': 340000,       # IAFF claims ~340,000 members
    'FOP': 370000,        # FOP claims ~370,000 members (including associates)
    'UFCW': 1300000,      # UFCW claims ~1.3 million members
    'IBT': 1300000,       # Teamsters claim ~1.3 million members
    'UAW': 400000,        # UAW claims ~400,000 members
    'USW': 850000,        # USW claims ~850,000 members
}

print("\n" + "=" * 90)
print("COMPARISON: OLMS REPORTED vs PUBLISHED MEMBERSHIP")
print("=" * 90)
print(f"{'Union':<12} {'OLMS Members':>14} {'Published':>12} {'Gap':>12} {'% of Published':>15}")
print("-" * 90)

for union, published in published_membership.items():
    # Get OLMS data for this union
    cur.execute("""
        SELECT SUM(members)
        FROM lm_data
        WHERE aff_abbr = %s
        AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    """, (union,))
    olms_result = cur.fetchone()[0]
    
    if olms_result is None:
        # Try alternative name matching
        cur.execute("""
            SELECT SUM(members)
            FROM lm_data
            WHERE union_name ILIKE %s
            AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
        """, (f'%{union}%',))
        olms_result = cur.fetchone()[0]
    
    olms_members = int(olms_result) if olms_result else 0
    gap = published - olms_members
    pct = (olms_members / published * 100) if published > 0 else 0
    
    print(f"{union:<12} {olms_members:>14,} {published:>12,} {gap:>+12,} {pct:>14.1f}%")

print("-" * 90)

# Detailed breakdown for key unions
print("\n" + "=" * 90)
print("DETAILED BREAKDOWN: AFSCME")
print("=" * 90)

cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, state
    FROM lm_data
    WHERE aff_abbr = 'AFSCME'
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 15
""")

print(f"{'File #':<12} {'Name':<45} {'Members':>10} {'Revenue':>16} {'State':<5}")
print("-" * 90)
for r in cur.fetchall():
    f_num, name, members, revenue, state = r
    print(f"{f_num:<12} {(name or '')[:43]:<45} {members or 0:>10,} ${revenue or 0:>14,.0f} {state or '':<5}")

# Get the International (largest filing)
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts
    FROM lm_data
    WHERE aff_abbr = 'AFSCME'
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY ttl_receipts DESC NULLS LAST
    LIMIT 1
""")
intl = cur.fetchone()
if intl:
    print(f"\nAFSCME International (largest by revenue):")
    print(f"  File #: {intl[0]}")
    print(f"  Members Reported: {intl[2]:,}")
    print(f"  Total Receipts: ${intl[3]:,.0f}")

print("\n" + "=" * 90)
print("DETAILED BREAKDOWN: SEIU")
print("=" * 90)

cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, state
    FROM lm_data
    WHERE (aff_abbr = 'SEIU' OR union_name ILIKE '%SERVICE EMPLOYEES%')
    AND yr_covered = (SELECT MAX(yr_covered) FROM lm_data)
    ORDER BY members DESC NULLS LAST
    LIMIT 15
""")

print(f"{'File #':<12} {'Name':<45} {'Members':>10} {'Revenue':>16} {'State':<5}")
print("-" * 90)
for r in cur.fetchall():
    f_num, name, members, revenue, state = r
    print(f"{f_num:<12} {(name or '')[:43]:<45} {members or 0:>10,} ${revenue or 0:>14,.0f} {state or '':<5}")

print("\n" + "=" * 90)
print("GAP ANALYSIS INTERPRETATION")
print("=" * 90)
print("""
WHY GAPS EXIST:

1. PUBLIC SECTOR NOT IN OLMS:
   - LM forms only required for unions with private sector members
   - Pure public sector locals don't file LM forms
   - This is the PRIMARY source of gaps for AFSCME/SEIU

2. HIERARCHY ISSUES:
   - International reports aggregate membership
   - Councils/locals report same members
   - OLMS SUM overcounts due to hierarchy

3. DATA QUALITY:
   - Some filings have incomplete member counts
   - Mergers/reaffiliations create gaps
   - Filing delays

USING 990 DATA TO VALIDATE:
   - For unions that file BOTH LM and 990, compare totals
   - 990 dues revenue / per-capita rate = implied membership
   - If 990 implied > OLMS reported, gap = public sector members
""")

conn.close()
