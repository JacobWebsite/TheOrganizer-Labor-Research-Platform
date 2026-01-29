"""
NLRB Participant Matching via Union Names Crosswalk
===================================================
Implements Phase 1A from LABOR_PLATFORM_ROADMAP_v7

This script matches NLRB union petitioners to OLMS file numbers
using the union_names_crosswalk table.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Database connection
conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("NLRB PARTICIPANT MATCHING - CROSSWALK IMPLEMENTATION")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# Step 1: Pre-match stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as already_matched
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
pre_stats = cur.fetchone()
print(f"\nPre-match status:")
print(f"  Total union petitioners: {pre_stats['total']:,}")
print(f"  Already matched: {pre_stats['already_matched']:,}")
print(f"  To be matched: {pre_stats['total'] - pre_stats['already_matched']:,}")

# Step 2: Exact match with high-confidence single-match crosswalk entries
print("\n" + "-" * 70)
print("PHASE 1: Exact name match (single file number, score >= 0.9)")
print("-" * 70)

update_sql_phase1 = """
    UPDATE nlrb_participants p
    SET matched_olms_fnum = c.pred_fnum::integer,
        match_method = 'crosswalk_exact',
        match_confidence = c.pred_union_score
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_fnum IS NOT NULL
    AND c.pred_fnum NOT LIKE '[%'
    AND c.pred_fnum_multiple = FALSE
    AND c.pred_union_score >= 0.9
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
"""

cur.execute(update_sql_phase1)
phase1_count = cur.rowcount
print(f"  Records updated: {phase1_count:,}")

# Step 3: Match with moderate confidence (0.8-0.9)
print("\n" + "-" * 70)
print("PHASE 2: Exact name match (single file number, score 0.8-0.9)")
print("-" * 70)

update_sql_phase2 = """
    UPDATE nlrb_participants p
    SET matched_olms_fnum = c.pred_fnum::integer,
        match_method = 'crosswalk_exact_moderate',
        match_confidence = c.pred_union_score
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_fnum IS NOT NULL
    AND c.pred_fnum NOT LIKE '[%'
    AND c.pred_fnum_multiple = FALSE
    AND c.pred_union_score >= 0.8
    AND c.pred_union_score < 0.9
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
"""

cur.execute(update_sql_phase2)
phase2_count = cur.rowcount
print(f"  Records updated: {phase2_count:,}")

# Step 4: Match with any confidence (remaining single-match entries)
print("\n" + "-" * 70)
print("PHASE 3: Remaining exact matches (any score, single file number)")
print("-" * 70)

update_sql_phase3 = """
    UPDATE nlrb_participants p
    SET matched_olms_fnum = c.pred_fnum::integer,
        match_method = 'crosswalk_exact_lower',
        match_confidence = c.pred_union_score
    FROM union_names_crosswalk c
    WHERE LOWER(p.participant_name) = LOWER(c.union_name)
    AND c.pred_fnum IS NOT NULL
    AND c.pred_fnum NOT LIKE '[%'
    AND c.pred_fnum_multiple = FALSE
    AND p.matched_olms_fnum IS NULL
    AND p.participant_type = 'Petitioner'
    AND p.participant_subtype = 'Union'
"""

cur.execute(update_sql_phase3)
phase3_count = cur.rowcount
print(f"  Records updated: {phase3_count:,}")

# Post-match stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched,
        COUNT(*) FILTER (WHERE match_method = 'crosswalk_exact') as exact_high,
        COUNT(*) FILTER (WHERE match_method = 'crosswalk_exact_moderate') as exact_mod,
        COUNT(*) FILTER (WHERE match_method = 'crosswalk_exact_lower') as exact_low
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
""")
post_stats = cur.fetchone()

print("\n" + "=" * 70)
print("MATCHING RESULTS SUMMARY")
print("=" * 70)
print(f"Total union petitioners: {post_stats['total']:,}")
print(f"Now matched: {post_stats['matched']:,}")
print(f"Match rate: {post_stats['matched']/post_stats['total']*100:.1f}%")
print(f"\nBy method:")
print(f"  crosswalk_exact (>=0.9): {post_stats['exact_high']:,}")
print(f"  crosswalk_exact_moderate (0.8-0.9): {post_stats['exact_mod']:,}")
print(f"  crosswalk_exact_lower (<0.8): {post_stats['exact_low']:,}")
print(f"\nTotal records updated: {phase1_count + phase2_count + phase3_count:,}")

# Sample matched records
print("\n" + "-" * 70)
print("SAMPLE MATCHED RECORDS")
print("-" * 70)
cur.execute("""
    SELECT p.participant_name, p.matched_olms_fnum, p.match_method, 
           ROUND(p.match_confidence::numeric, 3) as confidence,
           u.union_name as olms_union_name
    FROM nlrb_participants p
    LEFT JOIN unions_master u ON p.matched_olms_fnum = u.f_num
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND p.matched_olms_fnum IS NOT NULL
    LIMIT 15
""")
for r in cur.fetchall():
    name = r['participant_name'][:40] if r['participant_name'] else 'NULL'
    olms = r['olms_union_name'][:30] if r['olms_union_name'] else 'N/A'
    print(f"  {name:40} -> F#{r['matched_olms_fnum']} ({r['confidence']}) [{olms}]")

# Commit changes
conn.commit()
print("\n" + "=" * 70)
print("CHANGES COMMITTED SUCCESSFULLY")
print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

conn.close()
