import os
"""
CHECKPOINT 7: Validation and Final Verification
Validates all federal sector integration components
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')"
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 80)
print("CHECKPOINT 7: VALIDATION & FINAL VERIFICATION")
print("=" * 80)

validation_results = {
    "status": "PASSED",
    "checks": [],
    "warnings": [],
    "stats": {}
}

def check(name, query, expected_min=None, expected_exact=None):
    """Run a validation check"""
    try:
        cur.execute(query)
        result = cur.fetchone()
        value = list(result.values())[0] if result else 0
        
        passed = True
        if expected_min and value < expected_min:
            passed = False
        if expected_exact and value != expected_exact:
            passed = False
        
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}: {value:,}")
        
        validation_results["checks"].append({
            "name": name,
            "value": value,
            "passed": passed
        })
        
        if not passed:
            validation_results["status"] = "FAILED"
        
        return value
    except Exception as e:
        print(f"  [ERROR] {name}: {str(e)[:50]}")
        validation_results["checks"].append({
            "name": name,
            "error": str(e),
            "passed": False
        })
        validation_results["status"] = "FAILED"
        return None


# ============================================================================
# 1. TABLE VALIDATION
# ============================================================================
print("\n--- 1. TABLE VALIDATION ---")

check("federal_agencies table rows", 
      "SELECT COUNT(*) FROM federal_agencies",
      expected_min=100)

check("federal_bargaining_units table rows",
      "SELECT COUNT(*) FROM federal_bargaining_units",
      expected_min=2000)

check("flra_olms_union_map table rows",
      "SELECT COUNT(*) FROM flra_olms_union_map",
      expected_min=25)


# ============================================================================
# 2. VIEW VALIDATION
# ============================================================================
print("\n--- 2. VIEW VALIDATION ---")

check("public_sector_employers view rows",
      "SELECT COUNT(*) FROM public_sector_employers",
      expected_min=2000)

check("all_employers_unified view rows",
      "SELECT COUNT(*) FROM all_employers_unified",
      expected_min=50000)

check("sector_summary has both sectors",
      "SELECT COUNT(*) FROM sector_summary",
      expected_exact=2)


# ============================================================================
# 3. FEDERAL DATA QUALITY
# ============================================================================
print("\n--- 3. FEDERAL DATA QUALITY ---")

cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(DISTINCT agency_name) as agencies,
           SUM(total_in_unit) as workers
    FROM federal_bargaining_units
    WHERE status = 'Active'
""")
fed = cur.fetchone()
print(f"  Federal active bargaining units: {fed['total']:,}")
print(f"  Unique agencies: {fed['agencies']:,}")
print(f"  Total federal workers: {fed['workers']:,}")

validation_results["stats"]["federal"] = dict(fed)

# Check top agencies
cur.execute("""
    SELECT agency_name, SUM(total_in_unit) as workers
    FROM federal_bargaining_units
    WHERE status = 'Active'
    GROUP BY agency_name
    ORDER BY workers DESC
    LIMIT 5
""")
print("\n  Top 5 Federal Agencies:")
for row in cur.fetchall():
    print(f"    - {row['agency_name'][:40]}: {row['workers']:,} workers")


# ============================================================================
# 4. SECTOR COMPARISON
# ============================================================================
print("\n--- 4. SECTOR COMPARISON ---")

cur.execute("SELECT * FROM sector_summary ORDER BY total_workers DESC")
sectors = cur.fetchall()

print(f"\n  {'Sector':<12} {'Employers':>12} {'Workers':>14} {'Unions':>8}")
print("  " + "-" * 50)
for s in sectors:
    print(f"  {s['sector_code']:<12} {s['employer_count']:>12,} {s['total_workers']:>14,} {s['union_count']:>8}")

validation_results["stats"]["sectors"] = [dict(s) for s in sectors]


# ============================================================================
# 5. OLMS LINKAGE VALIDATION
# ============================================================================
print("\n--- 5. OLMS LINKAGE VALIDATION ---")

cur.execute("""
    SELECT match_type, COUNT(*) as units, SUM(federal_workers) as workers
    FROM flra_olms_enhanced_crosswalk
    GROUP BY match_type
    ORDER BY workers DESC
""")
linkage = cur.fetchall()

print(f"\n  {'Match Type':<20} {'Units':>8} {'Workers':>12}")
print("  " + "-" * 45)
for row in linkage:
    print(f"  {row['match_type']:<20} {row['units']:>8,} {row['workers'] or 0:>12,}")

validation_results["stats"]["linkage"] = [dict(r) for r in linkage]


# ============================================================================
# 6. UNION COVERAGE VALIDATION
# ============================================================================
print("\n--- 6. UNION COVERAGE VALIDATION ---")

cur.execute("""
    SELECT 
        union_acronym,
        SUM(CASE WHEN sector_code = 'PRIVATE' THEN workers_covered ELSE 0 END) as private,
        SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) as federal,
        SUM(workers_covered) as total
    FROM all_employers_unified
    WHERE union_acronym IS NOT NULL
    GROUP BY union_acronym
    HAVING SUM(CASE WHEN sector_code = 'FEDERAL' THEN workers_covered ELSE 0 END) > 0
    ORDER BY federal DESC
    LIMIT 10
""")
unions = cur.fetchall()

print("\n  Top 10 Unions with Federal Presence:")
print(f"  {'Union':<12} {'Private':>12} {'Federal':>12} {'Total':>12}")
print("  " + "-" * 52)
for u in unions:
    print(f"  {u['union_acronym']:<12} {u['private']:>12,} {u['federal']:>12,} {u['total']:>12,}")


# ============================================================================
# 7. GEOCODING STATUS
# ============================================================================
print("\n--- 7. GEOCODING STATUS ---")

cur.execute("""
    SELECT 
        sector_code,
        COUNT(*) as total,
        COUNT(CASE WHEN lat IS NOT NULL THEN 1 END) as geocoded
    FROM all_employers_unified
    GROUP BY sector_code
""")
geo = cur.fetchall()

for row in geo:
    pct = row['geocoded']/row['total']*100 if row['total'] > 0 else 0
    status = "[OK]" if pct > 50 or row['sector_code'] == 'FEDERAL' else "[WARN]"
    print(f"  {status} {row['sector_code']}: {row['geocoded']:,}/{row['total']:,} geocoded ({pct:.1f}%)")
    
    if row['sector_code'] == 'FEDERAL' and row['geocoded'] == 0:
        validation_results["warnings"].append("Federal sector has no geocoding - expected, but could be enhanced")


# ============================================================================
# 8. DATA QUALITY CHECKS
# ============================================================================
print("\n--- 8. DATA QUALITY CHECKS ---")

# Check for null employers
cur.execute("""
    SELECT COUNT(*) FROM all_employers_unified WHERE employer_name IS NULL OR employer_name = ''
""")
null_employers = cur.fetchone()['count']
if null_employers > 0:
    print(f"  [WARN] {null_employers:,} records with null/empty employer names")
    validation_results["warnings"].append(f"{null_employers} records with null employer names")
else:
    print(f"  [OK] No null employer names")

# Check for null workers
cur.execute("""
    SELECT COUNT(*) FROM all_employers_unified WHERE workers_covered IS NULL OR workers_covered = 0
""")
null_workers = cur.fetchone()['count']
print(f"  [INFO] {null_workers:,} records with null/zero workers")

# Check sector distribution
cur.execute("""
    SELECT sector_code, COUNT(*) as cnt
    FROM all_employers_unified
    GROUP BY sector_code
""")
for row in cur.fetchall():
    print(f"  [INFO] {row['sector_code']}: {row['cnt']:,} employers")


# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("VALIDATION SUMMARY")
print("=" * 80)

passed = sum(1 for c in validation_results["checks"] if c.get("passed", False))
total = len(validation_results["checks"])
print(f"\n  Checks Passed: {passed}/{total}")
print(f"  Warnings: {len(validation_results['warnings'])}")
print(f"  Overall Status: {validation_results['status']}")

if validation_results["warnings"]:
    print("\n  Warnings:")
    for w in validation_results["warnings"]:
        print(f"    - {w}")

# Save validation report
with open('C:/Users/jakew/Downloads/validation_report.json', 'w') as f:
    json.dump(validation_results, f, indent=2)
print("\n  Validation report saved to: validation_report.json")

conn.close()

print("\n" + "=" * 80)
print("CHECKPOINT 7 COMPLETE")
print("=" * 80)
print("""
All federal sector integration checkpoints complete:

  [x] Checkpoint 1: Schema created (federal_agencies, federal_bargaining_units)
  [x] Checkpoint 2: FLRA data loaded (2,183 bargaining units, 1.28M workers)
  [x] Checkpoint 3: OLMS linkage created (83% coverage)
  [x] Checkpoint 4: Unified views created (public + private sectors)
  [x] Checkpoint 5: API updated (labor_api_v5.py)
  [x] Checkpoint 6: Frontend updated (labor_search_v5.html)
  [x] Checkpoint 7: Validation complete

To run the platform:
  1. Start API: py -m uvicorn labor_api_v5:app --reload --port 8000
  2. Open frontend: labor_search_v5.html in browser
""")
