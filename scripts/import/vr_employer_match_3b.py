import os
from db_config import get_connection
"""
VR Employer Matching - Checkpoint 3B
Fuzzy matching using trigram similarity, token matching, and industry patterns
Enhanced with comprehensive matching strategies
"""
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import (
    normalize_employer,
    normalize_employer_aggressive,
    employer_token_similarity,
    extract_employer_key_words,
    compute_employer_match_score,
    EMPLOYER_ABBREVIATIONS
)

conn = get_connection()
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("VR Employer Matching - Checkpoint 3B: Fuzzy Match (Enhanced)")
print("=" * 60)

# Check if pg_trgm extension exists
cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
has_trgm = cur.fetchone() is not None
print(f"\npg_trgm extension available: {has_trgm}")

if not has_trgm:
    print("Attempting to create pg_trgm extension...")
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        has_trgm = True
        print("  pg_trgm extension created successfully")
    except Exception as e:
        print(f"  Could not create pg_trgm: {e}")

# Get current status
cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition 
    WHERE matched_employer_id IS NULL
""")
unmatched_start = cur.fetchone()['cnt']
print(f"\nUnmatched VR records to process: {unmatched_start}")

# Strategy 4: First word match + state (for companies like "Dana Corporation")
print("\n--- Strategy 4: First word + state match ---")
cur.execute("""
    WITH vr_first_word AS (
        SELECT 
            id,
            UPPER(SPLIT_PART(employer_name_normalized, ' ', 1)) as first_word,
            unit_state
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id IS NULL
          AND unit_state IS NOT NULL
          AND LENGTH(SPLIT_PART(employer_name_normalized, ' ', 1)) >= 4
    ),
    f7_first_word AS (
        SELECT 
            employer_id,
            employer_name,
            UPPER(SPLIT_PART(employer_name, ' ', 1)) as first_word,
            state
        FROM f7_employers_deduped
        WHERE LENGTH(SPLIT_PART(employer_name, ' ', 1)) >= 4
    ),
    matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            0.70 as confidence
        FROM vr_first_word vr
        JOIN f7_first_word f7 
            ON vr.first_word = f7.first_word
            AND vr.unit_state = f7.state
        ORDER BY vr.id, f7.employer_id
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'first_word_state'
    FROM matches m
    WHERE vr.id = m.vr_id
      AND vr.matched_employer_id IS NULL
""")
first_word_matches = cur.rowcount
print(f"  Matched: {first_word_matches}")

# Strategy 5: Enhanced trigram + word similarity + state (process ALL unmatched)
if has_trgm:
    print("\n--- Strategy 5: Enhanced trigram/word similarity + state ---")
    cur.execute("""
        SELECT id, employer_name, employer_name_normalized, employer_name_aggressive, unit_state, unit_city
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id IS NULL
          AND unit_state IS NOT NULL
    """)
    unmatched = cur.fetchall()
    print(f"  Processing {len(unmatched)} unmatched records with state...")

    trgm_matches = 0
    for i, vr in enumerate(unmatched):
        if not vr['employer_name_normalized']:
            continue

        name = vr['employer_name_normalized']
        agg_name = vr['employer_name_aggressive'] or normalize_employer_aggressive(vr['employer_name'])

        # Dynamic threshold based on name length
        threshold = 0.35 if len(name) > 30 else (0.40 if len(name) > 20 else 0.45)

        # Use both similarity and word_similarity
        cur.execute("""
            SELECT employer_id, employer_name, employer_name_aggressive, city,
                   similarity(employer_name, %s) as sim,
                   word_similarity(%s, employer_name) as word_sim,
                   similarity(COALESCE(employer_name_aggressive, ''), %s) as agg_sim
            FROM f7_employers_deduped
            WHERE state = %s
              AND (similarity(employer_name, %s) > %s
                   OR word_similarity(%s, employer_name) > %s
                   OR similarity(COALESCE(employer_name_aggressive, ''), %s) > %s)
            ORDER BY GREATEST(
                similarity(employer_name, %s),
                word_similarity(%s, employer_name),
                similarity(COALESCE(employer_name_aggressive, ''), %s)
            ) DESC
            LIMIT 5
        """, (name, name, agg_name, vr['unit_state'],
              name, threshold, name, threshold, agg_name, threshold,
              name, name, agg_name))

        candidates = cur.fetchall()
        best_match = None
        best_score = 0

        for cand in candidates:
            # Combine multiple similarity scores
            trgm_score = max(cand['sim'] or 0, cand['word_sim'] or 0, cand['agg_sim'] or 0)
            token_score = employer_token_similarity(name, cand['employer_name'])

            # City match bonus
            city_bonus = 0
            if vr['unit_city'] and cand['city']:
                if vr['unit_city'].upper() == cand['city'].upper():
                    city_bonus = 0.15
                elif vr['unit_city'].upper() in cand['city'].upper() or cand['city'].upper() in vr['unit_city'].upper():
                    city_bonus = 0.08

            combined_score = (trgm_score * 0.45) + (token_score * 0.40) + city_bonus

            if combined_score > best_score:
                best_score = combined_score
                best_match = cand

        if best_match and best_score >= 0.50:
            cur.execute("""
                UPDATE nlrb_voluntary_recognition
                SET matched_employer_id = %s,
                    employer_match_confidence = %s,
                    employer_match_method = 'trigram_token_state'
                WHERE id = %s AND matched_employer_id IS NULL
            """, (best_match['employer_id'], round(min(best_score, 0.95), 2), vr['id']))
            if cur.rowcount > 0:
                trgm_matches += 1

        if (i + 1) % 200 == 0:
            print(f"    Processed {i+1}/{len(unmatched)}... ({trgm_matches} matches)")

    print(f"  Matched: {trgm_matches}")

    # Strategy 5b: Trigram without state requirement (for remaining)
    print("\n--- Strategy 5b: Trigram/token similarity (no state) ---")
    cur.execute("""
        SELECT id, employer_name, employer_name_normalized, employer_name_aggressive
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id IS NULL
    """)
    remaining = cur.fetchall()
    print(f"  Processing {len(remaining)} remaining unmatched...")

    trgm_no_state = 0
    for i, vr in enumerate(remaining):
        if not vr['employer_name_normalized']:
            continue

        name = vr['employer_name_normalized']
        agg_name = vr['employer_name_aggressive'] or normalize_employer_aggressive(vr['employer_name'] or '')

        # Higher threshold when no state
        threshold = 0.55

        cur.execute("""
            SELECT employer_id, employer_name,
                   similarity(employer_name, %s) as sim,
                   word_similarity(%s, employer_name) as word_sim
            FROM f7_employers_deduped
            WHERE similarity(employer_name, %s) > %s
               OR word_similarity(%s, employer_name) > %s
            ORDER BY GREATEST(similarity(employer_name, %s), word_similarity(%s, employer_name)) DESC
            LIMIT 3
        """, (name, name, name, threshold, name, threshold, name, name))

        candidates = cur.fetchall()
        best_match = None
        best_score = 0

        for cand in candidates:
            trgm_score = max(cand['sim'] or 0, cand['word_sim'] or 0)
            token_score = employer_token_similarity(name, cand['employer_name'])
            combined_score = (trgm_score * 0.5) + (token_score * 0.5)

            if combined_score > best_score:
                best_score = combined_score
                best_match = cand

        if best_match and best_score >= 0.60:
            cur.execute("""
                UPDATE nlrb_voluntary_recognition
                SET matched_employer_id = %s,
                    employer_match_confidence = %s,
                    employer_match_method = 'trigram_token_nostate'
                WHERE id = %s AND matched_employer_id IS NULL
            """, (best_match['employer_id'], round(min(best_score, 0.85), 2), vr['id']))
            if cur.rowcount > 0:
                trgm_no_state += 1

        if (i + 1) % 200 == 0:
            print(f"    Processed {i+1}/{len(remaining)}... ({trgm_no_state} matches)")

    print(f"  Matched: {trgm_no_state}")
else:
    trgm_matches = 0
    trgm_no_state = 0
    print("\n--- Strategy 5: Skipped (no pg_trgm) ---")

# Strategy 6: Common variations (remove Inc, LLC, Corp, etc.)
print("\n--- Strategy 6: Stripped suffix matching ---")
cur.execute("""
    WITH cleaned_vr AS (
        SELECT 
            id,
            UPPER(REGEXP_REPLACE(
                employer_name_normalized,
                E'\\s*(Inc\\.?|LLC|Corp\\.?|Corporation|Company|Co\\.?|Ltd\\.?|LP|LLP)\\s*$',
                '', 'gi'
            )) as clean_name,
            unit_state
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id IS NULL
    ),
    cleaned_f7 AS (
        SELECT 
            employer_id,
            UPPER(REGEXP_REPLACE(
                employer_name,
                E'\\s*(Inc\\.?|LLC|Corp\\.?|Corporation|Company|Co\\.?|Ltd\\.?|LP|LLP)\\s*$',
                '', 'gi'
            )) as clean_name,
            state
        FROM f7_employers_deduped
    ),
    matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            0.75 as confidence
        FROM cleaned_vr vr
        JOIN cleaned_f7 f7 
            ON vr.clean_name = f7.clean_name
            AND vr.unit_state = f7.state
        WHERE LENGTH(vr.clean_name) >= 5
        ORDER BY vr.id, f7.employer_id
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'stripped_suffix_state'
    FROM matches m
    WHERE vr.id = m.vr_id
      AND vr.matched_employer_id IS NULL
""")
suffix_matches = cur.rowcount
print(f"  Matched: {suffix_matches}")

# Strategy 7: Match without state for large/national employers
print("\n--- Strategy 7: National employer match (no state required) ---")
# These are employers that appear in multiple states in F7
cur.execute("""
    WITH national_employers AS (
        SELECT UPPER(employer_name) as emp_upper, employer_id
        FROM f7_employers_deduped
        WHERE employer_name IN (
            SELECT employer_name
            FROM f7_employers_deduped
            GROUP BY employer_name
            HAVING COUNT(DISTINCT state) >= 3
        )
    ),
    matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            ne.employer_id,
            0.65 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN national_employers ne ON vr.employer_name_upper = ne.emp_upper
        WHERE vr.matched_employer_id IS NULL
        ORDER BY vr.id, ne.employer_id
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'national_employer'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
national_matches = cur.rowcount
print(f"  Matched: {national_matches}")

# Strategy 8: Token-based key word matching
print("\n--- Strategy 8: Key word token matching + state ---")
cur.execute("""
    SELECT id, employer_name, employer_name_normalized, unit_state, unit_city
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NULL
      AND unit_state IS NOT NULL
""")
remaining_for_token = cur.fetchall()
print(f"  Processing {len(remaining_for_token)} records for token matching...")

token_matches = 0
for i, vr in enumerate(remaining_for_token):
    name = vr['employer_name_normalized'] or ''
    key_words = extract_employer_key_words(name)

    if not key_words or len(key_words) < 1:
        continue

    # Search F7 for employers with matching key words
    patterns = ['%' + kw + '%' for kw in list(key_words)[:3]]

    cur.execute("""
        SELECT employer_id, employer_name, city
        FROM f7_employers_deduped
        WHERE state = %s
          AND employer_name ILIKE ANY(%s)
        ORDER BY latest_notice_date DESC NULLS LAST
        LIMIT 10
    """, (vr['unit_state'], patterns))

    candidates = cur.fetchall()
    best_match = None
    best_score = 0

    for cand in candidates:
        score = employer_token_similarity(name, cand['employer_name'])

        # City bonus
        if vr['unit_city'] and cand['city']:
            if vr['unit_city'].upper() == cand['city'].upper():
                score += 0.12

        if score > best_score:
            best_score = score
            best_match = cand

    if best_match and best_score >= 0.55:
        cur.execute("""
            UPDATE nlrb_voluntary_recognition
            SET matched_employer_id = %s,
                employer_match_confidence = %s,
                employer_match_method = 'token_keyword_state'
            WHERE id = %s AND matched_employer_id IS NULL
        """, (best_match['employer_id'], round(min(best_score, 0.85), 2), vr['id']))
        if cur.rowcount > 0:
            token_matches += 1

    if (i + 1) % 200 == 0:
        print(f"    Processed {i+1}/{len(remaining_for_token)}... ({token_matches} matches)")

print(f"  Matched: {token_matches}")

# Strategy 9: Industry-specific pattern matching
print("\n--- Strategy 9: Industry pattern matching ---")

# Common industry patterns
industry_patterns = [
    # Healthcare
    ('healthcare', ['%hospital%', '%medical%center%', '%health%system%', '%clinic%', '%healthcare%'], '%hospital%'),
    ('nursing', ['%nursing%home%', '%skilled%nursing%', '%rehab%', '%care%center%'], '%nursing%'),

    # Hospitality
    ('hotel', ['%hotel%', '%resort%', '%inn%', '%marriott%', '%hilton%', '%hyatt%'], '%hotel%'),
    ('restaurant', ['%restaurant%', '%cafe%', '%dining%', '%food%service%'], '%restaurant%'),

    # Retail/Grocery
    ('grocery', ['%grocery%', '%supermarket%', '%food%store%', '%market%'], '%grocery%'),
    ('retail', ['%store%', '%retail%', '%shop%', '%outlet%'], '%retail%'),

    # Manufacturing
    ('manufacturing', ['%manufacturing%', '%factory%', '%plant%', '%production%'], '%manufacturing%'),
    ('automotive', ['%auto%', '%motor%', '%vehicle%', '%parts%'], '%auto%'),

    # Transportation
    ('trucking', ['%trucking%', '%freight%', '%logistics%', '%transport%', '%shipping%'], '%trucking%'),
    ('warehouse', ['%warehouse%', '%distribution%', '%fulfillment%'], '%warehouse%'),

    # Services
    ('security', ['%security%', '%guard%', '%protective%'], '%security%'),
    ('janitorial', ['%janitorial%', '%cleaning%', '%custodial%', '%maintenance%'], '%janitorial%'),
    ('staffing', ['%staffing%', '%temp%', '%employment%agency%'], '%staffing%'),
]

industry_matches = 0
for industry, vr_patterns, f7_pattern in industry_patterns:
    for vr_pattern in vr_patterns:
        cur.execute("""
            WITH matches AS (
                SELECT DISTINCT ON (vr.id)
                    vr.id as vr_id,
                    f7.employer_id,
                    0.55 as confidence
                FROM nlrb_voluntary_recognition vr
                JOIN f7_employers_deduped f7
                    ON f7.employer_name ILIKE %s
                    AND f7.state = vr.unit_state
                WHERE vr.matched_employer_id IS NULL
                  AND vr.employer_name_normalized ILIKE %s
                  AND vr.unit_state IS NOT NULL
                ORDER BY vr.id, f7.latest_notice_date DESC NULLS LAST
            )
            UPDATE nlrb_voluntary_recognition vr
            SET matched_employer_id = m.employer_id,
                employer_match_confidence = m.confidence,
                employer_match_method = 'industry_pattern'
            FROM matches m
            WHERE vr.id = m.vr_id
        """, (f7_pattern, vr_pattern))
        industry_matches += cur.rowcount

print(f"  Matched: {industry_matches}")

# Strategy 10: Two-word prefix matching + state
print("\n--- Strategy 10: Two-word prefix + state ---")
cur.execute("""
    WITH vr_prefix AS (
        SELECT
            id,
            UPPER(
                SPLIT_PART(employer_name_normalized, ' ', 1) || ' ' ||
                SPLIT_PART(employer_name_normalized, ' ', 2)
            ) as two_word_prefix,
            unit_state
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id IS NULL
          AND unit_state IS NOT NULL
          AND LENGTH(SPLIT_PART(employer_name_normalized, ' ', 2)) >= 2
    ),
    f7_prefix AS (
        SELECT
            employer_id,
            employer_name,
            UPPER(
                SPLIT_PART(employer_name, ' ', 1) || ' ' ||
                SPLIT_PART(employer_name, ' ', 2)
            ) as two_word_prefix,
            state
        FROM f7_employers_deduped
        WHERE LENGTH(SPLIT_PART(employer_name, ' ', 2)) >= 2
    ),
    matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            f7.employer_id,
            0.68 as confidence
        FROM vr_prefix vr
        JOIN f7_prefix f7
            ON vr.two_word_prefix = f7.two_word_prefix
            AND vr.unit_state = f7.state
        WHERE LENGTH(vr.two_word_prefix) >= 6
        ORDER BY vr.id, f7.employer_id
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_employer_id = m.employer_id,
        employer_match_confidence = m.confidence,
        employer_match_method = 'two_word_prefix_state'
    FROM matches m
    WHERE vr.id = m.vr_id
      AND vr.matched_employer_id IS NULL
""")
two_word_matches = cur.rowcount
print(f"  Matched: {two_word_matches}")

# Summary
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(matched_employer_id) as matched,
        COUNT(*) - COUNT(matched_employer_id) as unmatched
    FROM nlrb_voluntary_recognition
""")
final = cur.fetchone()

print(f"\n{'=' * 60}")
print(f"CHECKPOINT 3B SUMMARY - Fuzzy Matching (Enhanced)")
print(f"{'=' * 60}")
print(f"  First word + state:         {first_word_matches}")
print(f"  Trigram/token + state:      {trgm_matches}")
print(f"  Trigram/token no state:     {trgm_no_state}")
print(f"  Stripped suffix:            {suffix_matches}")
print(f"  National employer:          {national_matches}")
print(f"  Token keyword + state:      {token_matches}")
print(f"  Industry patterns:          {industry_matches}")
print(f"  Two-word prefix + state:    {two_word_matches}")
print(f"\n  TOTAL MATCHED:              {final['matched']} ({100*final['matched']/final['total']:.1f}%)")
print(f"  REMAINING UNMATCHED:        {final['unmatched']} ({100*final['unmatched']/final['total']:.1f}%)")

# Match method breakdown
print(f"\nMatch method breakdown:")
cur.execute("""
    SELECT employer_match_method, COUNT(*), 
           ROUND(AVG(employer_match_confidence), 2) as avg_conf
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NOT NULL
    GROUP BY employer_match_method
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print(f"  {row['employer_match_method']:25} {row['count']:4} (avg conf: {row['avg_conf']})")

cur.close()
conn.close()

print(f"\n{'=' * 60}")
print("CHECKPOINT 3B COMPLETE")
print("Ready for 3C: Verification and report")
print(f"{'=' * 60}")
