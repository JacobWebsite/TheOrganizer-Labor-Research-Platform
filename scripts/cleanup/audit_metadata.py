import os
from db_config import get_connection
"""
Agent D: Score/Priority & Defunct Status Audit - Phase 1 (Read-Only)
Audits metadata consistency in mergent_employers and f7_employers_deduped
"""

import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("PHASE 1: Metadata Audit - mergent_employers & f7_employers_deduped")
print("=" * 70)

# ============================================================================
# 1. Unionized records with score_priority set (should be NULL)
# ============================================================================
print("\n--- 1. Unionized Records with score_priority (should be NULL) ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE
""")
r = cur.fetchone()
print(f"Total unionized mergent_employers: {r['cnt']:,}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND score_priority IS NOT NULL
""")
r = cur.fetchone()
print(f"Unionized with score_priority set: {r['cnt']:,}")

if r['cnt'] > 0:
    cur.execute("""
        SELECT duns, company_name, score_priority, organizing_score,
               sector_category, city, state
        FROM mergent_employers
        WHERE has_union = TRUE AND score_priority IS NOT NULL
        ORDER BY company_name
        LIMIT 25
    """)
    rows = cur.fetchall()
    print(f"\nSample unionized records with score_priority (up to 25):")
    for r in rows:
        print(f"  {r['company_name']} ({r['city']}, {r['state']}) -- sector: {r['sector_category']}, priority: {r['score_priority']}, score: {r['organizing_score']}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND organizing_score IS NOT NULL
""")
r = cur.fetchone()
print(f"\nUnionized with organizing_score set: {r['cnt']:,}")

# ============================================================================
# 2. Defunct employer analysis
# ============================================================================
print("\n--- 2. Defunct Employer Analysis ---")

# Check if defunct column exists in f7
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    AND column_name IN ('defunct', 'is_defunct', 'status', 'active')
    ORDER BY column_name
""")
defunct_cols = [r['column_name'] for r in cur.fetchall()]
print(f"Defunct-related columns in f7_employers_deduped: {defunct_cols}")

if defunct_cols:
    for col in defunct_cols:
        cur.execute(f"""
            SELECT {col}, COUNT(*) as cnt
            FROM f7_employers_deduped
            GROUP BY {col}
            ORDER BY COUNT(*) DESC
        """)
        print(f"\n  {col} distribution:")
        for r in cur.fetchall():
            print(f"    {r[col]}: {r['cnt']:,}")

# Check latest_notice_date for recency
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    AND (column_name LIKE '%date%' OR column_name LIKE '%notice%' OR column_name LIKE '%filing%')
    ORDER BY column_name
""")
date_cols = [r['column_name'] for r in cur.fetchall()]
print(f"\nDate-related columns in f7_employers_deduped: {date_cols}")

if date_cols:
    for col in date_cols:
        cur.execute(f"""
            SELECT MIN({col}::text) as earliest, MAX({col}::text) as latest,
                   COUNT(*) as total,
                   SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) as missing
            FROM f7_employers_deduped
        """)
        r = cur.fetchone()
        print(f"  {col}: earliest={r['earliest']}, latest={r['latest']}, missing={r['missing']:,}")

# Stale defunct check: marked defunct but has recent filing
if 'defunct' in defunct_cols or 'is_defunct' in defunct_cols:
    dcol = 'defunct' if 'defunct' in defunct_cols else 'is_defunct'
    for datecol in date_cols:
        if 'notice' in datecol or 'filing' in datecol:
            cur.execute(f"""
                SELECT COUNT(*) as cnt FROM f7_employers_deduped
                WHERE {dcol} = TRUE
                AND {datecol}::text >= '2023-01-01'
            """)
            r = cur.fetchone()
            print(f"\n  Defunct but recent {datecol} (>=2023): {r['cnt']:,}")
            if r['cnt'] > 0:
                cur.execute(f"""
                    SELECT employer_id, employer_name, city, state, {dcol}, {datecol}
                    FROM f7_employers_deduped
                    WHERE {dcol} = TRUE AND {datecol}::text >= '2023-01-01'
                    ORDER BY {datecol} DESC
                    LIMIT 15
                """)
                for row in cur.fetchall():
                    print(f"    ID={row['employer_id']}: {row['employer_name']} ({row['city']}, {row['state']}) -- {datecol}={row[datecol]}")

# ============================================================================
# 3. data_quality_flag distribution
# ============================================================================
print("\n--- 3. data_quality_flag Distribution ---")

# Check if column exists in f7
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    AND column_name = 'data_quality_flag'
""")
has_dqf = cur.fetchone()

if has_dqf:
    cur.execute("""
        SELECT data_quality_flag, COUNT(*) as cnt
        FROM f7_employers_deduped
        GROUP BY data_quality_flag
        ORDER BY COUNT(*) DESC
    """)
    print("  f7_employers_deduped.data_quality_flag:")
    for r in cur.fetchall():
        print(f"    {r['data_quality_flag'] or 'NULL'}: {r['cnt']:,}")
else:
    print("  Column 'data_quality_flag' does not exist in f7_employers_deduped")
    print("  -> Will need to add it in Phase 2")

# Check if column exists in mergent
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'mergent_employers'
    AND column_name = 'data_quality_flag'
""")
has_dqf_m = cur.fetchone()
if has_dqf_m:
    cur.execute("""
        SELECT data_quality_flag, COUNT(*) as cnt
        FROM mergent_employers
        GROUP BY data_quality_flag
        ORDER BY COUNT(*) DESC
    """)
    print("\n  mergent_employers.data_quality_flag:")
    for r in cur.fetchall():
        print(f"    {r['data_quality_flag'] or 'NULL'}: {r['cnt']:,}")
else:
    print("  Column 'data_quality_flag' does not exist in mergent_employers")

# ============================================================================
# 4. Score consistency check
# ============================================================================
print("\n--- 4. Score Consistency Check ---")

# Non-union targets: verify score = sum of components
cur.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN organizing_score IS NULL THEN 1 ELSE 0 END) as null_score,
           SUM(CASE WHEN score_priority IS NULL THEN 1 ELSE 0 END) as null_priority
    FROM mergent_employers
    WHERE has_union = FALSE
""")
r = cur.fetchone()
print(f"Non-union targets: {r['total']:,}")
print(f"  With NULL organizing_score: {r['null_score']:,}")
print(f"  With NULL score_priority: {r['null_priority']:,}")

# Check score formula consistency
cur.execute("""
    SELECT COUNT(*) as cnt
    FROM mergent_employers
    WHERE has_union = FALSE
      AND organizing_score IS NOT NULL
      AND organizing_score != COALESCE(score_geographic, 0) +
                              COALESCE(score_size, 0) +
                              COALESCE(score_industry_density, 0) +
                              COALESCE(score_nlrb_momentum, 0) +
                              COALESCE(score_osha_violations, 0) +
                              COALESCE(score_govt_contracts, 0) +
                              COALESCE(sibling_union_bonus, 0) +
                              COALESCE(score_labor_violations, 0)
""")
r = cur.fetchone()
print(f"  Score != sum of components: {r['cnt']:,}")

if r['cnt'] > 0:
    cur.execute("""
        SELECT company_name, organizing_score,
               COALESCE(score_geographic, 0) as geo,
               COALESCE(score_size, 0) as sz,
               COALESCE(score_industry_density, 0) as ind,
               COALESCE(score_nlrb_momentum, 0) as nlrb,
               COALESCE(score_osha_violations, 0) as osha,
               COALESCE(score_govt_contracts, 0) as contracts,
               COALESCE(sibling_union_bonus, 0) as sibling,
               COALESCE(score_labor_violations, 0) as labor,
               COALESCE(score_geographic, 0) + COALESCE(score_size, 0) +
               COALESCE(score_industry_density, 0) + COALESCE(score_nlrb_momentum, 0) +
               COALESCE(score_osha_violations, 0) + COALESCE(score_govt_contracts, 0) +
               COALESCE(sibling_union_bonus, 0) + COALESCE(score_labor_violations, 0) as computed
        FROM mergent_employers
        WHERE has_union = FALSE
          AND organizing_score IS NOT NULL
          AND organizing_score != COALESCE(score_geographic, 0) +
                                  COALESCE(score_size, 0) +
                                  COALESCE(score_industry_density, 0) +
                                  COALESCE(score_nlrb_momentum, 0) +
                                  COALESCE(score_osha_violations, 0) +
                                  COALESCE(score_govt_contracts, 0) +
                                  COALESCE(sibling_union_bonus, 0) +
                                  COALESCE(score_labor_violations, 0)
        LIMIT 10
    """)
    rows = cur.fetchall()
    print(f"\n  Sample score mismatches (up to 10):")
    for r in rows:
        print(f"    {r['company_name']}: stored={r['organizing_score']} computed={r['computed']}")
        print(f"      geo={r['geo']} sz={r['sz']} ind={r['ind']} nlrb={r['nlrb']} osha={r['osha']} contracts={r['contracts']} sibling={r['sibling']} labor={r['labor']}")

# Check tier assignment consistency
cur.execute("""
    SELECT COUNT(*) as cnt
    FROM mergent_employers
    WHERE has_union = FALSE
      AND organizing_score IS NOT NULL
      AND score_priority IS NOT NULL
      AND (
        (organizing_score >= 30 AND score_priority != 'TOP') OR
        (organizing_score >= 25 AND organizing_score < 30 AND score_priority != 'HIGH') OR
        (organizing_score >= 20 AND organizing_score < 25 AND score_priority != 'MEDIUM') OR
        (organizing_score < 20 AND score_priority != 'LOW')
      )
""")
r = cur.fetchone()
print(f"\n  Tier assignment mismatches: {r['cnt']:,}")

if r['cnt'] > 0:
    cur.execute("""
        SELECT company_name, organizing_score, score_priority,
               CASE
                   WHEN organizing_score >= 30 THEN 'TOP'
                   WHEN organizing_score >= 25 THEN 'HIGH'
                   WHEN organizing_score >= 20 THEN 'MEDIUM'
                   ELSE 'LOW'
               END as expected_tier
        FROM mergent_employers
        WHERE has_union = FALSE
          AND organizing_score IS NOT NULL
          AND score_priority IS NOT NULL
          AND (
            (organizing_score >= 30 AND score_priority != 'TOP') OR
            (organizing_score >= 25 AND organizing_score < 30 AND score_priority != 'HIGH') OR
            (organizing_score >= 15 AND organizing_score < 25 AND score_priority != 'MEDIUM') OR
            (organizing_score < 15 AND score_priority != 'LOW')
          )
        LIMIT 15
    """)
    for r in cur.fetchall():
        print(f"    {r['company_name']}: score={r['organizing_score']}, stored tier={r['score_priority']}, expected={r['expected_tier']}")

# ============================================================================
# 5. Mergent has_union without match evidence
# ============================================================================
print("\n--- 5. has_union Without Match Evidence ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE
      AND matched_f7_employer_id IS NULL
      AND nlrb_union_won IS NULL
      AND osha_establishment_id IS NULL
      AND f7_match_method IS NULL
""")
r = cur.fetchone()
print(f"  has_union=TRUE but no F7/NLRB/OSHA evidence: {r['cnt']:,}")

if r['cnt'] > 0:
    cur.execute("""
        SELECT company_name, city, state, sector_category, f7_match_method
        FROM mergent_employers
        WHERE has_union = TRUE
          AND matched_f7_employer_id IS NULL
          AND nlrb_union_won IS NULL
          AND osha_establishment_id IS NULL
          AND f7_match_method IS NULL
        LIMIT 15
    """)
    for r in cur.fetchall():
        print(f"    {r['company_name']} ({r['city']}, {r['state']}) -- sector: {r['sector_category']}, method: {r['f7_match_method']}")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("Issues to fix in Phase 2:")
print("  1. Unionized records with score_priority -> set to NULL")
print("  2. Score formula mismatches -> recalculate")
print("  3. Tier assignment mismatches -> reassign")
print("  4. Defunct flag reconciliation -> check against filing dates")
print("  5. data_quality_flag column -> add if missing")
print("=" * 70)

cur.close()
conn.close()
print("\nPhase 1 audit complete (read-only, no changes made)")
