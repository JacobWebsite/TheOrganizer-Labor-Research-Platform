import os
"""
VR Union Matching - Checkpoint 4A
Match unions using affiliation code + local number
Enhanced with improved local number normalization and affiliation variants
"""
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import (
    extract_local_number,
    normalize_local_number,
    get_affiliation_variants,
    AFFILIATION_MAPPINGS
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
print("VR Union Matching - Checkpoint 4A: Affiliation + Local (Enhanced)")
print("=" * 60)

# Check what we have
cur.execute("SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition")
vr_total = cur.fetchone()['cnt']
print(f"\nTotal VR records: {vr_total}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition 
    WHERE extracted_affiliation IS NOT NULL 
      AND extracted_affiliation != 'INDEPENDENT'
""")
vr_with_affil = cur.fetchone()['cnt']
print(f"VR records with known affiliation: {vr_with_affil}")

cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition 
    WHERE extracted_local_number IS NOT NULL
""")
vr_with_local = cur.fetchone()['cnt']
print(f"VR records with local number: {vr_with_local}")

cur.execute("SELECT COUNT(*) as cnt FROM unions_master")
unions_total = cur.fetchone()['cnt']
print(f"Unions in unions_master: {unions_total}")

# Clear previous matches
print("\nClearing previous union matches...")
cur.execute("""
    UPDATE nlrb_voluntary_recognition 
    SET matched_union_fnum = NULL,
        union_match_confidence = NULL,
        union_match_method = NULL
""")

# Pre-processing: Update extracted local numbers with enhanced extraction
print("\n--- Pre-processing: Enhanced local number extraction ---")
cur.execute("""
    SELECT id, union_name FROM nlrb_voluntary_recognition
    WHERE extracted_local_number IS NULL AND union_name IS NOT NULL
""")
vr_records = cur.fetchall()
local_updates = 0
for vr in vr_records:
    local_num = extract_local_number(vr['union_name'])
    if local_num:
        cur.execute("""
            UPDATE nlrb_voluntary_recognition
            SET extracted_local_number = %s
            WHERE id = %s
        """, (local_num, vr['id']))
        local_updates += 1
print(f"  Updated {local_updates} records with newly extracted local numbers")

# Strategy 1: Exact affiliation + local number match (with normalization)
print("\n--- Strategy 1: Exact affiliation + local number ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            um.f_num,
            um.union_name,
            0.95 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN unions_master um
            ON um.aff_abbr = vr.extracted_affiliation
            AND UPPER(REGEXP_REPLACE(um.local_number, '[-/\\s]', '', 'g')) =
                UPPER(REGEXP_REPLACE(vr.extracted_local_number, '[-/\\s]', '', 'g'))
        WHERE vr.extracted_affiliation IS NOT NULL
          AND vr.extracted_affiliation != 'INDEPENDENT'
          AND vr.extracted_local_number IS NOT NULL
          AND um.local_number IS NOT NULL
        ORDER BY vr.id, um.members DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_union_fnum = m.f_num,
        union_match_confidence = m.confidence,
        union_match_method = 'affiliation_local_exact'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
match_1 = cur.rowcount
print(f"  Matched: {match_1}")

# Strategy 1b: Affiliation VARIANTS + local number match
print("\n--- Strategy 1b: Affiliation variants + local number ---")
match_1b = 0
for vr_affil, variants in AFFILIATION_MAPPINGS.items():
    if len(variants) <= 1:
        continue
    cur.execute("""
        WITH matches AS (
            SELECT DISTINCT ON (vr.id)
                vr.id as vr_id,
                um.f_num,
                um.union_name,
                0.93 as confidence
            FROM nlrb_voluntary_recognition vr
            JOIN unions_master um
                ON um.aff_abbr = ANY(%s)
                AND UPPER(REGEXP_REPLACE(um.local_number, '[-/\\s]', '', 'g')) =
                    UPPER(REGEXP_REPLACE(vr.extracted_local_number, '[-/\\s]', '', 'g'))
            WHERE vr.extracted_affiliation = %s
              AND vr.extracted_local_number IS NOT NULL
              AND um.local_number IS NOT NULL
              AND vr.matched_union_fnum IS NULL
            ORDER BY vr.id, um.members DESC NULLS LAST
        )
        UPDATE nlrb_voluntary_recognition vr
        SET matched_union_fnum = m.f_num,
            union_match_confidence = m.confidence,
            union_match_method = 'affiliation_variant_local'
        FROM matches m
        WHERE vr.id = m.vr_id
    """, (variants, vr_affil))
    match_1b += cur.rowcount
print(f"  Matched: {match_1b}")

# Strategy 2: Affiliation match only (for national/international unions)
print("\n--- Strategy 2: Affiliation only (national level) ---")
cur.execute("""
    WITH national_unions AS (
        SELECT aff_abbr, f_num, union_name, members
        FROM unions_master
        WHERE local_number IS NULL 
           OR local_number = ''
           OR union_name ILIKE '%international%'
           OR union_name ILIKE '%national%'
        ORDER BY members DESC NULLS LAST
    ),
    matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            nu.f_num,
            nu.union_name,
            0.70 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN national_unions nu ON nu.aff_abbr = vr.extracted_affiliation
        WHERE vr.extracted_affiliation IS NOT NULL
          AND vr.extracted_affiliation != 'INDEPENDENT'
          AND vr.matched_union_fnum IS NULL
          AND vr.extracted_local_number IS NULL
        ORDER BY vr.id, nu.members DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_union_fnum = m.f_num,
        union_match_confidence = m.confidence,
        union_match_method = 'affiliation_national'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
match_2 = cur.rowcount
print(f"  Matched: {match_2}")

# Strategy 3: Affiliation + partial local number (e.g., "Local 1" matches "Local 1-A")
print("\n--- Strategy 3: Affiliation + partial local match ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            um.f_num,
            um.union_name,
            0.80 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN unions_master um
            ON um.aff_abbr = vr.extracted_affiliation
            AND (
                -- Normalized partial matching
                UPPER(REGEXP_REPLACE(um.local_number, '[-/\\s]', '', 'g'))
                    LIKE UPPER(REGEXP_REPLACE(vr.extracted_local_number, '[-/\\s]', '', 'g')) || '%'
                OR UPPER(REGEXP_REPLACE(vr.extracted_local_number, '[-/\\s]', '', 'g'))
                    LIKE UPPER(REGEXP_REPLACE(um.local_number, '[-/\\s]', '', 'g')) || '%'
            )
        WHERE vr.extracted_affiliation IS NOT NULL
          AND vr.extracted_affiliation != 'INDEPENDENT'
          AND vr.extracted_local_number IS NOT NULL
          AND um.local_number IS NOT NULL
          AND vr.matched_union_fnum IS NULL
        ORDER BY vr.id, um.members DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_union_fnum = m.f_num,
        union_match_confidence = m.confidence,
        union_match_method = 'affiliation_local_partial'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
match_3 = cur.rowcount
print(f"  Matched: {match_3}")

# Strategy 3b: Affiliation variants + partial local number
print("\n--- Strategy 3b: Affiliation variants + partial local ---")
match_3b = 0
for vr_affil, variants in AFFILIATION_MAPPINGS.items():
    if len(variants) <= 1:
        continue
    cur.execute("""
        WITH matches AS (
            SELECT DISTINCT ON (vr.id)
                vr.id as vr_id,
                um.f_num,
                um.union_name,
                0.78 as confidence
            FROM nlrb_voluntary_recognition vr
            JOIN unions_master um
                ON um.aff_abbr = ANY(%s)
                AND (
                    UPPER(REGEXP_REPLACE(um.local_number, '[-/\\s]', '', 'g'))
                        LIKE UPPER(REGEXP_REPLACE(vr.extracted_local_number, '[-/\\s]', '', 'g')) || '%%'
                    OR UPPER(REGEXP_REPLACE(vr.extracted_local_number, '[-/\\s]', '', 'g'))
                        LIKE UPPER(REGEXP_REPLACE(um.local_number, '[-/\\s]', '', 'g')) || '%%'
                )
            WHERE vr.extracted_affiliation = %s
              AND vr.extracted_local_number IS NOT NULL
              AND um.local_number IS NOT NULL
              AND vr.matched_union_fnum IS NULL
            ORDER BY vr.id, um.members DESC NULLS LAST
        )
        UPDATE nlrb_voluntary_recognition vr
        SET matched_union_fnum = m.f_num,
            union_match_confidence = m.confidence,
            union_match_method = 'affiliation_variant_local_partial'
        FROM matches m
        WHERE vr.id = m.vr_id
    """, (variants, vr_affil))
    match_3b += cur.rowcount
print(f"  Matched: {match_3b}")

# Strategy 4: Affiliation only fallback (pick largest local in same state if available)
print("\n--- Strategy 4: Affiliation + state fallback ---")
cur.execute("""
    WITH matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            um.f_num,
            um.union_name,
            0.60 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN unions_master um 
            ON um.aff_abbr = vr.extracted_affiliation
            AND um.state = vr.unit_state
        WHERE vr.extracted_affiliation IS NOT NULL
          AND vr.extracted_affiliation != 'INDEPENDENT'
          AND vr.unit_state IS NOT NULL
          AND vr.matched_union_fnum IS NULL
        ORDER BY vr.id, um.members DESC NULLS LAST
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_union_fnum = m.f_num,
        union_match_confidence = m.confidence,
        union_match_method = 'affiliation_state'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
match_4 = cur.rowcount
print(f"  Matched: {match_4}")

# Strategy 5: Any affiliation match (fallback to largest union of that affiliation)
print("\n--- Strategy 5: Affiliation only fallback ---")
cur.execute("""
    WITH largest_by_affil AS (
        SELECT DISTINCT ON (aff_abbr)
            aff_abbr, f_num, union_name, members
        FROM unions_master
        WHERE aff_abbr IS NOT NULL
        ORDER BY aff_abbr, members DESC NULLS LAST
    ),
    matches AS (
        SELECT DISTINCT ON (vr.id)
            vr.id as vr_id,
            la.f_num,
            la.union_name,
            0.50 as confidence
        FROM nlrb_voluntary_recognition vr
        JOIN largest_by_affil la ON la.aff_abbr = vr.extracted_affiliation
        WHERE vr.extracted_affiliation IS NOT NULL
          AND vr.extracted_affiliation != 'INDEPENDENT'
          AND vr.matched_union_fnum IS NULL
        ORDER BY vr.id
    )
    UPDATE nlrb_voluntary_recognition vr
    SET matched_union_fnum = m.f_num,
        union_match_confidence = m.confidence,
        union_match_method = 'affiliation_fallback'
    FROM matches m
    WHERE vr.id = m.vr_id
""")
match_5 = cur.rowcount
print(f"  Matched: {match_5}")

# Summary
total_matched = match_1 + match_1b + match_2 + match_3 + match_3b + match_4 + match_5
cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NOT NULL
""")
actual_matched = cur.fetchone()['cnt']

cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
""")
unmatched = cur.fetchone()['cnt']

print(f"\n{'=' * 60}")
print(f"CHECKPOINT 4A SUMMARY - Affiliation Matching (Enhanced)")
print(f"{'=' * 60}")
print(f"  Affil + local exact:        {match_1}")
print(f"  Affil variant + local:      {match_1b}")
print(f"  Affil national:             {match_2}")
print(f"  Affil + local partial:      {match_3}")
print(f"  Affil variant + partial:    {match_3b}")
print(f"  Affil + state:              {match_4}")
print(f"  Affil fallback:             {match_5}")
print(f"\n  TOTAL MATCHED:              {actual_matched} ({100*actual_matched/vr_total:.1f}%)")
print(f"  REMAINING UNMATCHED:        {unmatched} ({100*unmatched/vr_total:.1f}%)")

# Show what's left
print(f"\nUnmatched breakdown:")
cur.execute("""
    SELECT 
        extracted_affiliation,
        COUNT(*) as cnt
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
    GROUP BY extracted_affiliation
    ORDER BY COUNT(*) DESC
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"  {row['extracted_affiliation']:15} {row['cnt']}")

cur.close()
conn.close()

print(f"\n{'=' * 60}")
print("CHECKPOINT 4A COMPLETE")
print("Ready for 4B: Fuzzy name matching for independents")
print(f"{'=' * 60}")
