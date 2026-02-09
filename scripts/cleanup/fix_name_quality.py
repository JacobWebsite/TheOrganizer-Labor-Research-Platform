"""
Agent A: Name Field Cleanup - Phase 2
Fixes case mismatch and empty aggressive names
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'import'))
from name_normalizer import normalize_employer_aggressive

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("PHASE 2: Name Quality Fixes")
print("=" * 70)

# ============================================================================
# 1. Fix Mergent company_name_normalized case to match F7 convention (lowercase)
# ============================================================================
print("\n--- 1. Lowercase mergent_employers.company_name_normalized ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE company_name_normalized != LOWER(company_name_normalized)
    AND company_name_normalized IS NOT NULL
""")
r = cur.fetchone()
print(f"Records needing lowercase conversion: {r['cnt']:,}")

if r['cnt'] > 0:
    cur.execute("""
        UPDATE mergent_employers
        SET company_name_normalized = LOWER(company_name_normalized)
        WHERE company_name_normalized != LOWER(company_name_normalized)
        AND company_name_normalized IS NOT NULL
    """)
    print(f"Updated {cur.rowcount:,} records")

# Verify the JOIN improvement
cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers m
    JOIN f7_employers_deduped f ON m.company_name_normalized = f.employer_name_aggressive
    AND m.state = f.state
""")
r = cur.fetchone()
print(f"Case-sensitive matches after fix: {r['cnt']:,} (was 0 before)")

# ============================================================================
# 2. Re-derive empty employer_name_aggressive from employer_name
# ============================================================================
print("\n--- 2. Fix empty employer_name_aggressive ---")

cur.execute("""
    SELECT employer_id, employer_name
    FROM f7_employers_deduped
    WHERE employer_name_aggressive IS NULL OR TRIM(employer_name_aggressive) = ''
""")
empty_rows = cur.fetchall()
print(f"Records with empty employer_name_aggressive: {len(empty_rows)}")

fixed_count = 0
still_empty = 0
for row in empty_rows:
    derived = normalize_employer_aggressive(row['employer_name'] or '')
    if derived:
        cur.execute("""
            UPDATE f7_employers_deduped
            SET employer_name_aggressive = %s
            WHERE employer_id = %s
        """, (derived, row['employer_id']))
        fixed_count += 1
        print(f"  Fixed: '{row['employer_name']}' -> '{derived}'")
    else:
        # Name normalizes to empty - flag it
        cur.execute("""
            UPDATE f7_employers_deduped
            SET data_quality_flag = 'EMPTY_AGGRESSIVE_NAME'
            WHERE employer_id = %s
        """, (row['employer_id'],))
        still_empty += 1
        print(f"  Still empty: '{row['employer_name']}' -> flagged EMPTY_AGGRESSIVE_NAME")

print(f"\nFixed: {fixed_count}")
print(f"Still empty (flagged): {still_empty}")

# ============================================================================
# 3. Flag short names (<=3 chars) for awareness
# ============================================================================
print("\n--- 3. Flag short aggressive names ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE LENGTH(TRIM(employer_name_aggressive)) <= 3
    AND employer_name_aggressive IS NOT NULL
    AND TRIM(employer_name_aggressive) != ''
    AND (data_quality_flag IS NULL OR data_quality_flag != 'SHORT_NAME')
""")
r = cur.fetchone()
print(f"Short names to flag: {r['cnt']:,}")

if r['cnt'] > 0:
    cur.execute("""
        UPDATE f7_employers_deduped
        SET data_quality_flag = 'SHORT_NAME'
        WHERE LENGTH(TRIM(employer_name_aggressive)) <= 3
        AND employer_name_aggressive IS NOT NULL
        AND TRIM(employer_name_aggressive) != ''
        AND (data_quality_flag IS NULL OR data_quality_flag != 'SHORT_NAME')
    """)
    print(f"Flagged {cur.rowcount:,} records with data_quality_flag = 'SHORT_NAME'")

# ============================================================================
# 4. Commit
# ============================================================================
conn.commit()
print("\nAll changes committed successfully")

# ============================================================================
# 5. Verify
# ============================================================================
print("\n--- Verification ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE employer_name_aggressive IS NULL OR TRIM(employer_name_aggressive) = ''
""")
r = cur.fetchone()
print(f"Empty employer_name_aggressive: {r['cnt']:,} (originally 29)")

cur.execute("""
    SELECT data_quality_flag, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE data_quality_flag IS NOT NULL
    GROUP BY data_quality_flag
    ORDER BY COUNT(*) DESC
""")
print(f"\ndata_quality_flag distribution:")
for r in cur.fetchall():
    print(f"  {r['data_quality_flag']}: {r['cnt']:,}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE company_name_normalized != LOWER(company_name_normalized)
    AND company_name_normalized IS NOT NULL
""")
r = cur.fetchone()
print(f"\nMergent non-lowercase names remaining: {r['cnt']:,} (should be 0)")

print("\n" + "=" * 70)
print("Phase 2 name quality fixes complete")
print("=" * 70)

cur.close()
conn.close()
