import sqlite3
import re

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\crosswalk\union_lm_f7_crosswalk.db')
cursor = conn.cursor()

print("=== GEOCODING IMPROVEMENT ANALYSIS ===\n")

# Current state
cursor.execute("SELECT COUNT(*) FROM f7_employers WHERE geocode_status = 'geocoded'")
geocoded = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM f7_employers")
total = cursor.fetchone()[0]
print(f"Current: {geocoded:,} / {total:,} = {100*geocoded/total:.1f}%\n")

# Strategy 1: Clean multi-line addresses (take first line)
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed' AND street LIKE '%\n%'
""")
multiline = cursor.fetchone()[0]
print(f"1. MULTI-LINE ADDRESSES: {multiline:,}")
print("   Strategy: Extract first line only, retry")
print("   Expected recovery: ~70% = ~1,800")

# Strategy 2: Strip suite/unit numbers
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed' 
      AND (street LIKE '%Suite%' OR street LIKE '%Ste %' OR street LIKE '%Ste.%'
           OR street LIKE '%Unit%' OR street LIKE '%#%' OR street LIKE '%Apt%')
      AND street NOT LIKE 'PO Box%'
      AND street NOT LIKE '%\n%'
""")
suite = cursor.fetchone()[0]
print(f"\n2. SUITE/UNIT IN ADDRESS: {suite:,}")
print("   Strategy: Remove suite/unit/apt designations, retry")
print("   Expected recovery: ~60% = ~1,500")

# Strategy 3: Fix common typos/formatting
cursor.execute("""
    SELECT street, COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed' 
      AND (street LIKE '%  %' OR street LIKE '%,%' OR street NOT GLOB '*[0-9]*')
    GROUP BY street
    LIMIT 10
""")
print(f"\n3. FORMATTING ISSUES (double spaces, missing numbers):")
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed' 
      AND street LIKE '%  %'
""")
double_space = cursor.fetchone()[0]
print(f"   Double spaces: {double_space:,}")

# Strategy 4: Use alternative geocoder for PO Boxes (city centroid)
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE 'PO Box%' OR street LIKE 'P.O.%' OR street LIKE 'P O Box%')
      AND city IS NOT NULL AND state IS NOT NULL
""")
pobox = cursor.fetchone()[0]
print(f"\n4. PO BOX WITH CITY/STATE: {pobox:,}")
print("   Strategy: Geocode to city centroid (less precise but usable)")
print("   Expected recovery: ~95% = ~8,000")

# Strategy 5: Highway/Route cleanup
cursor.execute("""
    SELECT street, city, state FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE '%Highway%' OR street LIKE '%Route%' OR street LIKE '%Hwy%')
      AND street NOT LIKE 'PO Box%'
    LIMIT 10
""")
print(f"\n5. HIGHWAY/ROUTE ADDRESSES (sample):")
for row in cursor.fetchall():
    print(f"   {row[0][:50]} | {row[1]}, {row[2]}")

cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE '%Highway%' OR street LIKE '%Route%' OR street LIKE '%Hwy%' OR street LIKE '%Rt %')
      AND street NOT LIKE 'PO Box%'
""")
highway = cursor.fetchone()[0]
print(f"   Total: {highway:,}")
print("   Strategy: Standardize format (Route 6 -> US Route 6), retry")
print("   Expected recovery: ~40% = ~800")

# Strategy 6: Retry with Google/alternative geocoder
print(f"\n6. REMAINING 'OTHER' FAILURES:")
remaining = 23066 - suite - 800  # Rough estimate
print(f"   Estimated: ~{remaining:,}")
print("   Strategy: Try Google Geocoding API (has better address parsing)")
print("   Expected recovery: ~50% = ~10,000")

# Calculate potential improvement
print("\n" + "="*60)
print("PROJECTED IMPROVEMENT SUMMARY")
print("="*60)
potential_gains = [
    ("Multi-line cleanup", 1800),
    ("Suite/Unit removal", 1500),
    ("PO Box -> city centroid", 8000),
    ("Highway standardization", 800),
    ("Google geocoder fallback", 10000),
]
total_potential = sum(g[1] for g in potential_gains)
for name, gain in potential_gains:
    print(f"  {name:<30}: +{gain:,}")
print(f"  {'TOTAL POTENTIAL GAIN':<30}: +{total_potential:,}")
print(f"\nProjected new rate: {geocoded + total_potential:,} / {total:,} = {100*(geocoded + total_potential)/total:.1f}%")
print(f"(Up from {100*geocoded/total:.1f}%)")

conn.close()
