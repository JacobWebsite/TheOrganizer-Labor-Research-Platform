import os
"""
VR Employer Matching - Checkpoint 3A
Exact matching on normalized employer name + city + state
Enhanced with aggressive normalization and abbreviation expansion
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import (
    normalize_employer,
    normalize_employer_aggressive,
    EMPLOYER_ABBREVIATIONS
)

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("VR Employer Matching - Checkpoint 3A: Exact Match (Enhanced)")
print("=" * 60)

# First, let's see what we're working with
cur.execute("SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition")
vr_total = cur.fetchone()['cnt']
print(f"\nTotal VR records: {vr_total}")

cur.execute("SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition WHERE unit_state IS NOT NULL")
vr_with_state = cur.fetchone()['cnt']
print(f"VR records with state: {vr_with_state}")

cur.execute("SELECT COUNT(*) as cnt FROM f7_employers_deduped")
f7_total = cur.fetchone()['cnt']
print(f"F7 employers available: {f7_total}")

# Clear previous matches
print("\nClearing previous employer matches...")
cur.execute("""
    UPDATE nlrb_voluntary_recognition
    SET matched_employer_id = NULL,
        employer_match_confidence = NULL,
        employer_match_method = NULL
""")

# Pre-processing: Add aggressively normalized names if column doesn't exist
print("\n--- Pre-processing: Creating normalized name columns ---")
try:
    cur.execute("""
        ALTER TABLE nlrb_voluntary_recognition
        ADD COLUMN IF NOT EXISTS employer_name_aggressive TEXT
    """)
    cur.execute("""
        ALTER TABLE f7_employers_deduped
        ADD COLUMN IF NOT EXISTS employer_name_aggressive TEXT
    """)
except:
    pass  # Columns may already exist

# Update VR table with aggressively normalized names
print("  Normalizing VR employer names...")
cur.execute("SELECT id, employer_name FROM nlrb_voluntary_recognition WHERE employer_name IS NOT NULL")
vr_records = cur.fetchall()
for vr in vr_records:
    agg_name = normalize_employer_aggressive(vr['employer_name'])
    cur.execute("""
        UPDATE nlrb_voluntary_recognition
        SET employer_name_aggressive = %s
        WHERE id = %s
    """, (agg_name, vr['id']))

# Update F7 table with aggressively normalized names
print("  Normalizing F7 employer names...")
cur.execute("SELECT employer_id, employer_name FROM f7_employers_deduped WHERE employer_name IS NOT NULL")
f7_records = cur.fetchall()
batch_count = 0
for f7 in f7_records:
    agg_name = normalize_employer_aggressive(f7['employer_name'])
    cur.execute("""
        UPDATE f7_employers_deduped
        SET employer_name_aggressive = %s
        WHERE employer_id = %s
    """, (agg_name, f7['employer_id']))
    batch_count += 1
    if batch_count % 5000 == 0:
        print(f"    Processed {batch_count}/{len(f7_records)}...")

print(f"  Normalized {len(vr_records)} VR and {len(f7_records)} F7 records")

# Create indexes for faster matching
print("  Creating indexes...")
try:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vr_emp_agg ON nlrb_voluntary_recognition(employer_name_aggressive)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_f7_emp_agg ON f7_employers_deduped(employer_name_aggressive)")
except:
    pass

# Strategy 1: Exact match on employer_name_upper + city + state
print("\n--- Strategy 1: Exact name + city + state ---")
cur.execute("""
    WITH matches AS (
        SELECT 
            vr.id as vr_id,
            f7.employer_id,
            f7.employer_name as f7_name,
            1.00 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7 
            ON UPPER(TRIM(f7.employer_name)) = vr.employer_name_upper
            AND UPPER(TRIM(f7.city)) = UPPER(TRIM(vr.unit_city))
            AND f7.state = vr.unit_state
        WHERE vr.unit_city IS NOT NULL 
          AND vr.unit_state IS NOT NULL
          AND vr.matched_employer_id IS NULL
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'exact_name_city_state'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
exact_matches_1 = cur.rowcount
print(f"  Matched: {exact_matches_1}")

# Strategy 2: Exact match on normalized name + state only (city may vary)
print("\n--- Strategy 2: Exact normalized name + state ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            f7.employer_name as f7_name,
            0.90 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7 
            ON UPPER(TRIM(f7.employer_name)) = vr.employer_name_upper
            AND f7.state = vr.unit_state
        WHERE vr.unit_state IS NOT NULL
          AND vr.matched_employer_id IS NULL
        ORDER BY vr.id, f7.latest_notice_date DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'exact_name_state'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
exact_matches_2 = cur.rowcount
print(f"  Matched: {exact_matches_2}")

# Strategy 3: Exact match on normalized name only (for records without state)
print("\n--- Strategy 3: Exact normalized name only ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            f7.employer_name as f7_name,
            0.80 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7
            ON UPPER(TRIM(f7.employer_name)) = vr.employer_name_upper
        WHERE vr.matched_employer_id IS NULL
        ORDER BY vr.id, f7.latest_notice_date DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'exact_name_only'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
exact_matches_3 = cur.rowcount
print(f"  Matched: {exact_matches_3}")

# Strategy 4: Aggressive normalized name + state
print("\n--- Strategy 4: Aggressive normalized name + state ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            f7.employer_name as f7_name,
            0.88 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7
            ON f7.employer_name_aggressive = vr.employer_name_aggressive
            AND f7.state = vr.unit_state
        WHERE vr.unit_state IS NOT NULL
          AND vr.employer_name_aggressive IS NOT NULL
          AND LENGTH(vr.employer_name_aggressive) >= 3
          AND vr.matched_employer_id IS NULL
        ORDER BY vr.id, f7.latest_notice_date DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'aggressive_norm_state'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
exact_matches_4 = cur.rowcount
print(f"  Matched: {exact_matches_4}")

# Strategy 5: Aggressive normalized name only (no state)
print("\n--- Strategy 5: Aggressive normalized name only ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            f7.employer_name as f7_name,
            0.78 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7
            ON f7.employer_name_aggressive = vr.employer_name_aggressive
        WHERE vr.employer_name_aggressive IS NOT NULL
          AND LENGTH(vr.employer_name_aggressive) >= 5
          AND vr.matched_employer_id IS NULL
        ORDER BY vr.id, f7.latest_notice_date DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'aggressive_norm_only'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
exact_matches_5 = cur.rowcount
print(f"  Matched: {exact_matches_5}")

# Summary
total_exact = exact_matches_1 + exact_matches_2 + exact_matches_3 + exact_matches_4 + exact_matches_5
print(f"\n{'=' * 60}")
print(f"CHECKPOINT 3A SUMMARY - Exact Matching (Enhanced)")
print(f"{'=' * 60}")
print(f"  Exact name+city+state:     {exact_matches_1}")
print(f"  Exact name+state:          {exact_matches_2}")
print(f"  Exact name only:           {exact_matches_3}")
print(f"  Aggressive norm+state:     {exact_matches_4}")
print(f"  Aggressive norm only:      {exact_matches_5}")
print(f"  TOTAL EXACT MATCHES:       {total_exact} ({100*total_exact/vr_total:.1f}%)")

# Remaining unmatched
cur.execute("""
    SELECT COUNT(*) as cnt 
    FROM nlrb_voluntary_recognition 
    WHERE matched_employer_id IS NULL
""")
unmatched = cur.fetchone()['cnt']
print(f"\n  Remaining unmatched:   {unmatched} ({100*unmatched/vr_total:.1f}%)")

# Sample matches
print(f"\nSample exact matches:")
cur.execute("""
    SELECT 
        vr.employer_name_normalized as vr_employer,
        vr.unit_city, vr.unit_state,
        f7.employer_name as f7_employer,
        f7.city as f7_city, f7.state as f7_state,
        vr.employer_match_method
    FROM nlrb_voluntary_recognition vr
    JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    WHERE vr.employer_match_confidence >= 0.9
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"  VR: {row['vr_employer'][:30]} ({row['unit_city']}, {row['unit_state']})")
    print(f"  F7: {row['f7_employer'][:30]} ({row['f7_city']}, {row['f7_state']})")
    print(f"      Method: {row['employer_match_method']}")
    print()

cur.close()
conn.close()

print(f"{'=' * 60}")
print("CHECKPOINT 3A COMPLETE")
print("Ready for 3B: Fuzzy matching")
print(f"{'=' * 60}")
