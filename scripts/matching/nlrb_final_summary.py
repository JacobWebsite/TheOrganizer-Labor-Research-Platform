"""
NLRB Matching - Final Summary Report
====================================
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB PARTICIPANT MATCHING - FINAL REPORT")
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Overall statistics
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched,
        COUNT(*) FILTER (WHERE participant_name IS NULL) as null_names
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
stats = cur.fetchone()

print("\n" + "=" * 70)
print("OVERALL RESULTS")
print("=" * 70)
print(f"Total union petitioners: {stats['total']:,}")
print(f"Successfully matched: {stats['matched']:,}")
print(f"Match rate: {stats['matched']/stats['total']*100:.1f}%")
print(f"NULL entries: {stats['null_names']:,}")

# Match method breakdown
cur.execute("""
    SELECT match_method, COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NOT NULL
    GROUP BY match_method
    ORDER BY cnt DESC
""")
print("\n" + "-" * 70)
print("MATCH METHOD BREAKDOWN")
print("-" * 70)
methods = cur.fetchall()
for r in methods:
    print(f"  {r['match_method']:35}: {r['cnt']:6,}")

# Summary by method category
print("\n" + "-" * 70)
print("MATCH CATEGORY SUMMARY")
print("-" * 70)
cur.execute("""
    SELECT 
        CASE 
            WHEN match_method = 'crosswalk_exact' THEN '1. Crosswalk Exact (high conf)'
            WHEN match_method LIKE 'crosswalk_aff%' THEN '2. Crosswalk Affiliation'
            WHEN match_method LIKE 'pattern%' THEN '3. Pattern Match'
            WHEN match_method = 'crosswalk_ue' THEN '2. Crosswalk Affiliation'
            ELSE '4. Other'
        END as category,
        COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NOT NULL
    GROUP BY category
    ORDER BY category
""")
for r in cur.fetchall():
    pct = r['cnt'] / stats['matched'] * 100
    print(f"  {r['category']:35}: {r['cnt']:6,} ({pct:5.1f}%)")

# Top matched unions
cur.execute("""
    SELECT u.union_name, p.matched_olms_fnum as fnum, COUNT(*) as cnt
    FROM nlrb_participants p
    LEFT JOIN unions_master u ON p.matched_olms_fnum = u.f_num
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND p.matched_olms_fnum IS NOT NULL
    GROUP BY u.union_name, p.matched_olms_fnum
    ORDER BY cnt DESC
    LIMIT 25
""")
print("\n" + "-" * 70)
print("TOP 25 MATCHED UNIONS BY FREQUENCY")
print("-" * 70)
for i, r in enumerate(cur.fetchall(), 1):
    name = r['union_name'][:40] if r['union_name'] else 'N/A'
    print(f"{i:2}. F#{r['fnum']:<6} {name:40}: {r['cnt']:5,}")

# Remaining unmatched (excluding NULL and law firms)
cur.execute("""
    SELECT participant_name, COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NULL
    AND participant_name IS NOT NULL
    AND participant_name NOT LIKE '%LLC%'
    AND participant_name NOT LIKE '%P.C.%'
    AND participant_name NOT LIKE '%Law Office%'
    GROUP BY participant_name
    ORDER BY cnt DESC
    LIMIT 20
""")
print("\n" + "-" * 70)
print("TOP 20 REMAINING UNMATCHED (TRUE UNIONS)")
print("-" * 70)
for r in cur.fetchall():
    name = r['participant_name'][:55] if r['participant_name'] else 'NULL'
    print(f"  {name:55}: {r['cnt']:4}")

# Matching timeline
print("\n" + "=" * 70)
print("MATCHING PHASES SUMMARY")
print("=" * 70)
print("""
Phase 1: Crosswalk Exact Match (score >= 0.9)     -> 15,588 records (51.3%)
Phase 2: Affiliation-Based (major internationals) ->  8,841 records (80.4%)
Phase 3: Extended Patterns (nurses, SAG, etc.)    ->  1,316 records (89.8%)
Phase 4: Additional Affiliations (NAGE, CJA...)   ->  1,093 records (93.4%)
Phase 5: Final Affiliations + Patterns            ->    534 records (95.1%)
Phase 6: Final Cleanup                            ->    174 records (95.7%)
""")

print("=" * 70)
print("KEY ACHIEVEMENTS")
print("=" * 70)
print(f"""
- Initial target: 80%+ match rate
- Achieved: {stats['matched']/stats['total']*100:.1f}% raw, ~96.1% adjusted
- Records matched: {stats['matched']:,} of {stats['total']:,}
- Improvement: From ~50% (pre-crosswalk) to 95.7%

NOTES:
- 187 NULL entries cannot be matched
- ~120 entries are law firms (correctly excluded)
- Remaining ~1,000 are small independent/local unions
""")

conn.close()
