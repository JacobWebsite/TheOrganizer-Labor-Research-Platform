"""
Agent A: Name Field Audit & Cleanup - Phase 1 (Read-Only)
Audits employer_name_aggressive quality in f7_employers_deduped
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'import'))
from name_normalizer import normalize_employer_aggressive

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("PHASE 1: Name Quality Audit - f7_employers_deduped")
print("=" * 70)

# ============================================================================
# 1. Empty or NULL employer_name_aggressive
# ============================================================================
print("\n--- 1. Empty/NULL employer_name_aggressive ---")

cur.execute("""
    SELECT COUNT(*) as total FROM f7_employers_deduped
""")
total = cur.fetchone()['total']
print(f"Total f7_employers_deduped records: {total:,}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE employer_name_aggressive IS NULL OR TRIM(employer_name_aggressive) = ''
""")
empty_agg = cur.fetchone()['cnt']
print(f"Empty/NULL employer_name_aggressive: {empty_agg:,}")

if empty_agg > 0:
    cur.execute("""
        SELECT employer_id, employer_name, employer_name_aggressive,
               city, state
        FROM f7_employers_deduped
        WHERE employer_name_aggressive IS NULL OR TRIM(employer_name_aggressive) = ''
        ORDER BY employer_id
        LIMIT 50
    """)
    rows = cur.fetchall()
    print(f"\nSample empty aggressive names (showing up to 50):")
    for r in rows:
        derived = normalize_employer_aggressive(r['employer_name'] or '')
        print(f"  ID={r['employer_id']}: '{r['employer_name']}' -> aggressive='{r['employer_name_aggressive']}' -> RE-DERIVED='{derived}'")

# ============================================================================
# 2. Short names (<=3 chars) in employer_name_aggressive
# ============================================================================
print("\n--- 2. Short Names (<=3 chars) in employer_name_aggressive ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE LENGTH(TRIM(employer_name_aggressive)) <= 3
    AND employer_name_aggressive IS NOT NULL
    AND TRIM(employer_name_aggressive) != ''
""")
short_count = cur.fetchone()['cnt']
print(f"Short aggressive names (<=3 chars): {short_count:,}")

cur.execute("""
    SELECT employer_name_aggressive, COUNT(*) as cnt,
           (ARRAY_AGG(employer_name ORDER BY employer_name))[1:5] as examples
    FROM f7_employers_deduped
    WHERE LENGTH(TRIM(employer_name_aggressive)) <= 3
    AND employer_name_aggressive IS NOT NULL
    AND TRIM(employer_name_aggressive) != ''
    GROUP BY employer_name_aggressive
    ORDER BY COUNT(*) DESC
    LIMIT 30
""")
rows = cur.fetchall()
print(f"\nShort names by frequency (top 30):")
for r in rows:
    examples = ', '.join(r['examples'][:3])
    print(f"  '{r['employer_name_aggressive']}' x{r['cnt']} -- e.g. {examples}")

# ============================================================================
# 3. Case convention check
# ============================================================================
print("\n--- 3. Case Convention Analysis ---")

# F7 convention
cur.execute("""
    SELECT
        SUM(CASE WHEN employer_name_aggressive = LOWER(employer_name_aggressive) THEN 1 ELSE 0 END) as lowercase,
        SUM(CASE WHEN employer_name_aggressive = UPPER(employer_name_aggressive) THEN 1 ELSE 0 END) as uppercase,
        SUM(CASE WHEN employer_name_aggressive != LOWER(employer_name_aggressive)
                  AND employer_name_aggressive != UPPER(employer_name_aggressive) THEN 1 ELSE 0 END) as mixed
    FROM f7_employers_deduped
    WHERE employer_name_aggressive IS NOT NULL AND TRIM(employer_name_aggressive) != ''
""")
r = cur.fetchone()
print(f"F7 employer_name_aggressive case:")
print(f"  Lowercase: {r['lowercase']:,}")
print(f"  Uppercase: {r['uppercase']:,}")
print(f"  Mixed: {r['mixed']:,}")

# Mergent convention
cur.execute("""
    SELECT
        SUM(CASE WHEN company_name_normalized = LOWER(company_name_normalized) THEN 1 ELSE 0 END) as lowercase,
        SUM(CASE WHEN company_name_normalized = UPPER(company_name_normalized) THEN 1 ELSE 0 END) as uppercase,
        SUM(CASE WHEN company_name_normalized != LOWER(company_name_normalized)
                  AND company_name_normalized != UPPER(company_name_normalized) THEN 1 ELSE 0 END) as mixed
    FROM mergent_employers
    WHERE company_name_normalized IS NOT NULL AND TRIM(company_name_normalized) != ''
""")
r = cur.fetchone()
print(f"\nMergent company_name_normalized case:")
print(f"  Lowercase: {r['lowercase']:,}")
print(f"  Uppercase: {r['uppercase']:,}")
print(f"  Mixed: {r['mixed']:,}")

# ============================================================================
# 4. Case mismatch JOIN failures
# ============================================================================
print("\n--- 4. Case Mismatch JOIN Analysis ---")

# How many mergent records match f7 with case-insensitive but not case-sensitive?
cur.execute("""
    WITH case_sensitive AS (
        SELECT COUNT(*) as cnt FROM mergent_employers m
        JOIN f7_employers_deduped f ON m.company_name_normalized = f.employer_name_aggressive
        AND m.state = f.state
    ),
    case_insensitive AS (
        SELECT COUNT(*) as cnt FROM mergent_employers m
        JOIN f7_employers_deduped f ON LOWER(m.company_name_normalized) = LOWER(f.employer_name_aggressive)
        AND m.state = f.state
    )
    SELECT
        cs.cnt as case_sensitive_matches,
        ci.cnt as case_insensitive_matches,
        ci.cnt - cs.cnt as lost_to_case_mismatch
    FROM case_sensitive cs, case_insensitive ci
""")
r = cur.fetchone()
print(f"Mergent-to-F7 name+state joins:")
print(f"  Case-sensitive matches: {r['case_sensitive_matches']:,}")
print(f"  Case-insensitive matches: {r['case_insensitive_matches']:,}")
print(f"  Lost to case mismatch: {r['lost_to_case_mismatch']:,}")

if r['lost_to_case_mismatch'] > 0:
    cur.execute("""
        SELECT m.company_name_normalized as mergent_name,
               f.employer_name_aggressive as f7_name,
               m.state
        FROM mergent_employers m
        JOIN f7_employers_deduped f ON LOWER(m.company_name_normalized) = LOWER(f.employer_name_aggressive)
            AND m.state = f.state
        WHERE m.company_name_normalized != f.employer_name_aggressive
        LIMIT 20
    """)
    rows = cur.fetchall()
    print(f"\nSample case mismatches (up to 20):")
    for r in rows:
        print(f"  Mergent: '{r['mergent_name']}' vs F7: '{r['f7_name']}' ({r['state']})")

# ============================================================================
# 5. NULL employer_name
# ============================================================================
print("\n--- 5. NULL/Empty employer_name ---")

cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE employer_name IS NULL OR TRIM(employer_name) = ''
""")
r = cur.fetchone()
print(f"Empty/NULL employer_name: {r['cnt']:,}")

# ============================================================================
# 6. employer_name vs employer_name_aggressive derivation check
# ============================================================================
print("\n--- 6. Derivation Consistency Check ---")
print("Checking if employer_name_aggressive matches re-derived value from employer_name...")

cur.execute("""
    SELECT employer_id, employer_name, employer_name_aggressive
    FROM f7_employers_deduped
    WHERE employer_name IS NOT NULL
    ORDER BY employer_id
    LIMIT 5000
""")
rows = cur.fetchall()
mismatches = []
for r in rows:
    derived = normalize_employer_aggressive(r['employer_name'])
    stored = (r['employer_name_aggressive'] or '').strip()
    if derived != stored:
        mismatches.append({
            'employer_id': r['employer_id'],
            'employer_name': r['employer_name'],
            'stored': stored,
            'derived': derived
        })

print(f"Checked first 5,000 records")
print(f"Derivation mismatches: {len(mismatches)}")
if mismatches:
    print(f"\nSample mismatches (up to 20):")
    for m in mismatches[:20]:
        print(f"  ID={m['employer_id']}: '{m['employer_name']}'")
        print(f"    Stored:  '{m['stored']}'")
        print(f"    Derived: '{m['derived']}'")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total records: {total:,}")
print(f"Empty employer_name_aggressive: {empty_agg:,}")
print(f"Short names (<=3 chars): {short_count:,}")
print(f"Derivation mismatches (first 5k): {len(mismatches)}")
print(f"Case mismatch JOIN losses: check above")
print("=" * 70)

cur.close()
conn.close()
print("\nPhase 1 audit complete (read-only, no changes made)")
