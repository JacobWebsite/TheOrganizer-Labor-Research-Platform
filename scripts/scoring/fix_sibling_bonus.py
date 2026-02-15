import os
from db_config import get_connection
"""
Fix sibling union bonus misclassifications across all sectors.

Problems found:
1. Same-address matches: Mergent employer has same street number + city as F-7
   employer but address formatting differs -> wrongly treated as "sibling at different
   location" instead of has_union=True.
2. Cross-state false positives: Name match but F-7 is in a different state with no
   parent_duns link -> not the same org.

This script:
A) Scans ALL sectors for same-address sibling matches -> marks as unionized
B) Scans for cross-state false positives -> removes bonus
C) Recalculates organizing_score and score_priority for affected records
"""

import psycopg2
import re

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("FIX SIBLING UNION BONUS MISCLASSIFICATIONS")
print("=" * 80)

# ── Step 0: Capture before-state ──────────────────────────────────────────────
print("\n=== Step 0: Before-state snapshot ===")
cur.execute("""
    SELECT sector_category,
           COUNT(*) FILTER (WHERE has_union IS NOT TRUE) as targets,
           COUNT(*) FILTER (WHERE has_union = TRUE) as unionized,
           COUNT(*) FILTER (WHERE sibling_union_bonus > 0 AND has_union IS NOT TRUE) as with_sibling
    FROM mergent_employers
    WHERE sector_category IS NOT NULL
    GROUP BY sector_category
    ORDER BY sector_category
""")
before = {}
for row in cur.fetchall():
    before[row[0]] = {'targets': row[1], 'unionized': row[2], 'sibling': row[3]}
    print(f"  {row[0]:<25} targets={row[1]:>5}  unionized={row[2]:>4}  sibling_bonus={row[3]:>3}")

total_sibling_before = sum(v['sibling'] for v in before.values())
print(f"\n  TOTAL with sibling bonus: {total_sibling_before}")

# ── Step 1: Find same-address sibling matches ────────────────────────────────
print("\n=== Step 1: Finding same-address sibling matches ===")

# Get all records with sibling bonus from name-match method (Method 2)
cur.execute("""
    SELECT m.duns, m.company_name, m.company_name_normalized,
           m.street_address, m.city, m.state, m.sector_category,
           m.sibling_union_note
    FROM mergent_employers m
    WHERE m.sibling_union_bonus > 0
      AND m.has_union IS NOT TRUE
      AND m.sibling_union_note LIKE 'Same org has union%'
    ORDER BY m.sector_category, m.company_name
""")
name_match_siblings = cur.fetchall()
print(f"  Name-match siblings to check: {len(name_match_siblings)}")


def extract_street_number(address):
    """Extract the leading street number from an address."""
    if not address:
        return ""
    # Remove suite/floor/room suffixes first
    clean = re.sub(r'\b(STE|SUITE|FL|FLOOR|RM|ROOM|APT|UNIT|#)\s*\S+', '', address, flags=re.IGNORECASE)
    # Find first number
    match = re.search(r'^\s*(\d+)', clean.strip())
    if match:
        return match.group(1)
    # Try finding any number followed by a street-name word
    match = re.search(r'\b(\d+)\s+[A-Za-z]', clean)
    return match.group(1) if match else ""


same_address_fixes = []  # (duns, f7_id, f7_name, f7_union, f7_fnum, sector)
cross_state_fixes = []   # (duns, company_name, mergent_state, f7_state, sector)
ambiguous = []           # (duns, company_name, note)

for duns, name, name_norm, m_addr, m_city, m_state, sector, note in name_match_siblings:
    # Find the F-7 match using the same logic as run_mergent_matching.py Method 2
    cur.execute("""
        SELECT employer_id, employer_name, employer_name_aggressive,
               street, city, state, latest_union_name, latest_union_fnum
        FROM f7_employers_deduped
        WHERE LOWER(employer_name_aggressive) = LOWER(%s)
          AND latest_union_name IS NOT NULL
    """, (name_norm,))
    f7_rows = cur.fetchall()

    if not f7_rows:
        ambiguous.append((duns, name, f"No F-7 match found for normalized name '{name_norm}'"))
        continue

    # Check each F-7 match
    matched = False
    for f7_id, f7_name, f7_agg, f7_street, f7_city, f7_state, f7_union, f7_fnum in f7_rows:
        m_num = extract_street_number(m_addr or "")
        f_num = extract_street_number(f7_street or "")

        # Same state check
        if m_state and f7_state and m_state.upper() != f7_state.upper():
            cross_state_fixes.append((duns, name, m_state, f7_state, sector))
            matched = True
            break

        # Same street number + same city = same location
        if m_num and f_num and m_num == f_num:
            m_city_upper = (m_city or "").upper().strip()
            f_city_upper = (f7_city or "").upper().strip()
            # City match (allow partial - "NEW YORK" in both, or one contains other)
            city_match = (
                m_city_upper == f_city_upper
                or m_city_upper in f_city_upper
                or f_city_upper in m_city_upper
                # Handle borough names
                or (m_city_upper in ("BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND", "MANHATTAN")
                    and f_city_upper in ("BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND", "MANHATTAN", "NEW YORK"))
                or (f_city_upper in ("BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND", "MANHATTAN")
                    and m_city_upper in ("BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND", "MANHATTAN", "NEW YORK"))
            )
            if city_match:
                same_address_fixes.append((duns, f7_id, f7_name, f7_union, f7_fnum, sector))
                matched = True
                break

    if not matched and len(f7_rows) > 0:
        # Different address, same state — this is a legitimate sibling (no fix needed)
        pass

print(f"\n  Same-address (should be unionized): {len(same_address_fixes)}")
for duns, f7_id, f7_name, f7_union, f7_fnum, sector in same_address_fixes:
    print(f"    [{sector}] {f7_name[:50]} -> {f7_union}")

print(f"\n  Cross-state false positives: {len(cross_state_fixes)}")
for duns, name, m_st, f_st, sector in cross_state_fixes:
    print(f"    [{sector}] {name[:50]} (Mergent: {m_st}, F-7: {f_st})")

print(f"\n  Ambiguous (no F-7 found): {len(ambiguous)}")
for duns, name, note in ambiguous:
    print(f"    {name[:50]} - {note}")

# ── Step 2: Fix same-address matches -> mark as unionized ─────────────────────
print(f"\n=== Step 2: Fixing {len(same_address_fixes)} same-address matches ===")

for duns, f7_id, f7_name, f7_union, f7_fnum, sector in same_address_fixes:
    cur.execute("""
        UPDATE mergent_employers SET
            has_union = TRUE,
            matched_f7_employer_id = %s,
            f7_union_name = %s,
            f7_union_fnum = %s,
            f7_match_method = 'SIBLING_FIX',
            sibling_union_bonus = 0,
            sibling_union_note = NULL,
            organizing_score = NULL,
            score_priority = NULL
        WHERE duns = %s
    """, (f7_id, f7_union, f7_fnum, duns))

conn.commit()
print(f"  Updated {len(same_address_fixes)} records to has_union=TRUE")

# ── Step 3: Fix cross-state false positives -> remove bonus ───────────────────
print(f"\n=== Step 3: Fixing {len(cross_state_fixes)} cross-state false positives ===")

for duns, name, m_st, f_st, sector in cross_state_fixes:
    cur.execute("""
        UPDATE mergent_employers SET
            sibling_union_bonus = 0,
            sibling_union_note = NULL
        WHERE duns = %s
    """, (duns,))

conn.commit()
print(f"  Removed sibling bonus from {len(cross_state_fixes)} records")

# ── Step 4: Recalculate scores for affected non-union records ─────────────────
print("\n=== Step 4: Recalculating scores for affected records ===")

# Recalculate organizing_score for all non-union records (safe to do globally)
cur.execute("""
    UPDATE mergent_employers
    SET organizing_score = COALESCE(score_geographic, 0)
                         + COALESCE(score_size, 0)
                         + COALESCE(score_industry_density, 0)
                         + COALESCE(score_nlrb_momentum, 0)
                         + COALESCE(score_osha_violations, 0)
                         + COALESCE(score_govt_contracts, 0)
                         + COALESCE(sibling_union_bonus, 0)
                         + COALESCE(score_labor_violations, 0)
    WHERE has_union IS NOT TRUE
""")
print(f"  Recalculated organizing_score for {cur.rowcount:,} records")

# Update priority tiers
cur.execute("""
    UPDATE mergent_employers
    SET score_priority = CASE
        WHEN organizing_score >= 30 THEN 'TOP'
        WHEN organizing_score >= 25 THEN 'HIGH'
        WHEN organizing_score >= 20 THEN 'MEDIUM'
        ELSE 'LOW'
    END
    WHERE has_union IS NOT TRUE
""")
print(f"  Updated tiers for {cur.rowcount:,} records")

conn.commit()

# ── Step 5: After-state and verification ──────────────────────────────────────
print("\n=== Step 5: After-state comparison ===")
cur.execute("""
    SELECT sector_category,
           COUNT(*) FILTER (WHERE has_union IS NOT TRUE) as targets,
           COUNT(*) FILTER (WHERE has_union = TRUE) as unionized,
           COUNT(*) FILTER (WHERE sibling_union_bonus > 0 AND has_union IS NOT TRUE) as with_sibling
    FROM mergent_employers
    WHERE sector_category IS NOT NULL
    GROUP BY sector_category
    ORDER BY sector_category
""")
after = {}
for row in cur.fetchall():
    after[row[0]] = {'targets': row[1], 'unionized': row[2], 'sibling': row[3]}

print(f"{'Sector':<25} {'Targets':<18} {'Unionized':<18} {'Sibling Bonus':<18}")
print(f"{'':25} {'Before->After':<18} {'Before->After':<18} {'Before->After':<18}")
print("-" * 80)
for sector in sorted(before.keys()):
    b = before[sector]
    a = after.get(sector, b)
    t_delta = a['targets'] - b['targets']
    u_delta = a['unionized'] - b['unionized']
    s_delta = a['sibling'] - b['sibling']
    t_str = f"{b['targets']}->{a['targets']}" + (f" ({t_delta:+d})" if t_delta else "")
    u_str = f"{b['unionized']}->{a['unionized']}" + (f" ({u_delta:+d})" if u_delta else "")
    s_str = f"{b['sibling']}->{a['sibling']}" + (f" ({s_delta:+d})" if s_delta else "")
    print(f"{sector:<25} {t_str:<18} {u_str:<18} {s_str:<18}")

total_sibling_after = sum(v['sibling'] for v in after.values())
print(f"\n  TOTAL sibling bonus: {total_sibling_before} -> {total_sibling_after} ({total_sibling_after - total_sibling_before:+d})")

# ── Step 6: Spot checks ──────────────────────────────────────────────────────
print("\n=== Step 6: Spot checks ===")

# Liberty Resources should have sibling_union_bonus=0
cur.execute("""
    SELECT company_name, state, sibling_union_bonus, sibling_union_note, has_union, organizing_score
    FROM mergent_employers
    WHERE company_name ILIKE '%liberty resources%'
""")
for row in cur.fetchall():
    print(f"  Liberty Resources: bonus={row[2]}, note={row[3]}, has_union={row[4]}, score={row[5]}")

# City Harvest should still have sibling_union_bonus=8
cur.execute("""
    SELECT company_name, sibling_union_bonus, sibling_union_note, has_union
    FROM mergent_employers
    WHERE company_name ILIKE '%city harvest%'
""")
for row in cur.fetchall():
    print(f"  City Harvest: bonus={row[1]}, note={row[2]}, has_union={row[3]}")

# Hope House should still have sibling_union_bonus=8
cur.execute("""
    SELECT company_name, sibling_union_bonus, sibling_union_note, has_union
    FROM mergent_employers
    WHERE company_name ILIKE '%hope house%' AND state = 'NY'
""")
for row in cur.fetchall():
    print(f"  Hope House: bonus={row[1]}, note={row[2]}, has_union={row[3]}")

# Covenant House should still have sibling_union_bonus=8
cur.execute("""
    SELECT company_name, sibling_union_bonus, sibling_union_note, has_union
    FROM mergent_employers
    WHERE company_name ILIKE '%covenant house%' AND state = 'NY' AND has_union IS NOT TRUE
""")
for row in cur.fetchall():
    print(f"  Covenant House: bonus={row[1]}, note={row[2]}, has_union={row[3]}")

# Make the Road should still have sibling_union_bonus=8
cur.execute("""
    SELECT company_name, sibling_union_bonus, sibling_union_note, has_union
    FROM mergent_employers
    WHERE company_name ILIKE '%make the road%' OR company_name ILIKE '%make road%'
""")
for row in cur.fetchall():
    print(f"  Make the Road: bonus={row[1]}, note={row[2]}, has_union={row[3]}")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("SIBLING BONUS FIX COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("  1. Run: py scripts/create_sector_views.py  (refresh views)")
print("  2. Restart API server")
