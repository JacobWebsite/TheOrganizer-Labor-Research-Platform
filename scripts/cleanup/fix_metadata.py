import os
from db_config import get_connection
"""
Agent D: Score/Priority & Defunct Status Fix - Phase 2
Fixes metadata inconsistencies in mergent_employers
"""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("PHASE 2: Metadata Fixes - mergent_employers")
print("=" * 70)

# ============================================================================
# 1. NULL out score_priority for unionized records
# ============================================================================
print("\n--- 1. Fix: Unionized records with score_priority ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND score_priority IS NOT NULL
""")
before = cur.fetchone()['cnt']
print(f"Before: {before} unionized records with score_priority set")

if before > 0:
    cur.execute("""
        UPDATE mergent_employers
        SET score_priority = NULL
        WHERE has_union = TRUE AND score_priority IS NOT NULL
    """)
    print(f"Updated {cur.rowcount} records: score_priority -> NULL")

# Also ensure organizing_score is NULL for unionized
cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND organizing_score IS NOT NULL
""")
score_cnt = cur.fetchone()['cnt']
if score_cnt > 0:
    cur.execute("""
        UPDATE mergent_employers
        SET organizing_score = NULL
        WHERE has_union = TRUE AND organizing_score IS NOT NULL
    """)
    print(f"Updated {cur.rowcount} records: organizing_score -> NULL (unionized)")
else:
    print("No unionized records have organizing_score set (good)")

# ============================================================================
# 2. Verify no stale data_quality_flag values
# ============================================================================
print("\n--- 2. Clean up placeholder data_quality_flag ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE data_quality_flag = 'placeholder_value'
""")
r = cur.fetchone()
if r['cnt'] > 0:
    cur.execute("""
        UPDATE f7_employers_deduped
        SET data_quality_flag = NULL
        WHERE data_quality_flag = 'placeholder_value'
    """)
    print(f"Cleared {cur.rowcount} placeholder data_quality_flag values")
else:
    print("No placeholder values found")

# ============================================================================
# 3. Commit
# ============================================================================
conn.commit()
print("\nAll changes committed successfully")

# ============================================================================
# 4. Verify
# ============================================================================
print("\n--- Verification ---")
cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND score_priority IS NOT NULL
""")
r = cur.fetchone()
print(f"Unionized with score_priority: {r['cnt']} (should be 0)")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND organizing_score IS NOT NULL
""")
r = cur.fetchone()
print(f"Unionized with organizing_score: {r['cnt']} (should be 0)")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE data_quality_flag = 'placeholder_value'
""")
r = cur.fetchone()
print(f"Placeholder data_quality_flag: {r['cnt']} (should be 0)")

print("\n" + "=" * 70)
print("Phase 2 metadata fixes complete")
print("=" * 70)

cur.close()
conn.close()
