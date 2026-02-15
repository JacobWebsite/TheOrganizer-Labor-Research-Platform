import os
from db_config import get_connection
"""
VR Union Matching - Checkpoint 4B
Fuzzy name matching for independents and remaining unions
Enhanced with token-based matching, improved trigrams, and expanded patterns
"""
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import (
    normalize_union,
    extract_local_number,
    normalize_local_number,
    token_similarity,
    extract_key_tokens,
    compute_match_score,
    get_affiliation_variants,
    AFFILIATION_MAPPINGS,
    UNION_ACRONYMS
)

conn = get_connection()
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("VR Union Matching - Checkpoint 4B: Fuzzy Name Match (Enhanced)")
print("=" * 60)

# Check unmatched
cur.execute("""
    SELECT COUNT(*) as cnt FROM nlrb_voluntary_recognition 
    WHERE matched_union_fnum IS NULL
""")
unmatched_start = cur.fetchone()['cnt']
print(f"\nUnmatched VR records to process: {unmatched_start}")

# First, fix affiliation mismatches using centralized mapping
print("\n--- Fixing affiliation mapping issues (using centralized mappings) ---")

# Special name patterns for specific affiliations
AFFILIATION_NAME_PATTERNS = {
    'UNITE HERE': ['%unite here%', '%hotel employees%restaurant%'],
    'IUPAT': ['%painters%allied%', '%glaziers%'],
    'SMART': ['%sheet metal%', '%transportation union%'],
    'IAM': ['%machinists%aerospace%', '%machinists%'],
    'USW': ['%steelworkers%', '%steel workers%'],
    'CWA': ['%communications workers%', '%newspaper guild%'],
    'IFPTE': ['%professional%technical%engineer%'],
    'TNG-CWA': ['%newspaper guild%', '%news guild%'],
    'SEATU': ['%exposition%', '%trade show%'],
}

affiliation_variant_matches = 0
for vr_affil, variants in AFFILIATION_MAPPINGS.items():
    # First try: match by affiliation code variants only
    cur.execute("""
        WITH matches AS (
            SELECT DISTINCT ON (vr.id)
                vr.id as vr_id,
                um.f_num,
                um.union_name,
                0.85 as confidence
            FROM nlrb_voluntary_recognition vr
            JOIN unions_master um ON um.aff_abbr = ANY(%s)
            WHERE vr.extracted_affiliation = %s
              AND vr.matched_union_fnum IS NULL
            ORDER BY vr.id, um.members DESC NULLS LAST
        )
        UPDATE nlrb_voluntary_recognition vr
        SET matched_union_fnum = m.f_num,
            union_match_confidence = m.confidence,
            union_match_method = 'affiliation_variant_match'
        FROM matches m
        WHERE vr.id = m.vr_id
    """, (variants, vr_affil))
    if cur.rowcount > 0:
        print(f"  {vr_affil} (by code): {cur.rowcount} matches")
        affiliation_variant_matches += cur.rowcount

    # Second try: match by name patterns if defined
    if vr_affil in AFFILIATION_NAME_PATTERNS:
        name_patterns = AFFILIATION_NAME_PATTERNS[vr_affil]
        cur.execute("""
            WITH matches AS (
                SELECT DISTINCT ON (vr.id)
                    vr.id as vr_id,
                    um.f_num,
                    um.union_name,
                    0.80 as confidence
                FROM nlrb_voluntary_recognition vr
                JOIN unions_master um ON um.union_name ILIKE ANY(%s)
                WHERE vr.extracted_affiliation = %s
                  AND vr.matched_union_fnum IS NULL
                ORDER BY vr.id, um.members DESC NULLS LAST
            )
            UPDATE nlrb_voluntary_recognition vr
            SET matched_union_fnum = m.f_num,
                union_match_confidence = m.confidence,
                union_match_method = 'affiliation_name_pattern'
            FROM matches m
            WHERE vr.id = m.vr_id
        """, (name_patterns, vr_affil))
        if cur.rowcount > 0:
            print(f"  {vr_affil} (by name): {cur.rowcount} matches")
            affiliation_variant_matches += cur.rowcount

print(f"  Total affiliation variant matches: {affiliation_variant_matches}")

# Strategy 6: Enhanced trigram similarity for independents (with token matching)
print("\n--- Strategy 6: Enhanced trigram + token similarity for independents ---")
cur.execute("""
    SELECT id, union_name, union_name_normalized, unit_state
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
      AND extracted_affiliation = 'INDEPENDENT'
""")
independents = cur.fetchall()
print(f"  Processing {len(independents)} independent unions...")

trgm_matches = 0
token_only_matches = 0
for i, vr in enumerate(independents):
    if not vr['union_name_normalized']:
        continue

    name = vr['union_name_normalized']
    # Adjust threshold based on name length (longer names need lower threshold)
    threshold = 0.35 if len(name) > 40 else (0.40 if len(name) > 25 else 0.45)

    # Try trigram first with word_similarity for better partial matching
    cur.execute("""
        SELECT f_num, union_name, local_number,
               similarity(union_name, %s) as sim,
               word_similarity(%s, union_name) as word_sim
        FROM unions_master
        WHERE similarity(union_name, %s) > %s
           OR word_similarity(%s, union_name) > %s
        ORDER BY GREATEST(similarity(union_name, %s), word_similarity(%s, union_name)) DESC
        LIMIT 5
    """, (name, name, name, threshold, name, threshold, name, name))

    candidates = cur.fetchall()
    best_match = None
    best_score = 0

    for cand in candidates:
        # Combine trigram with token similarity
        trgm_score = max(cand['sim'] or 0, cand['word_sim'] or 0)
        token_score = token_similarity(name, cand['union_name'])

        # Extract local numbers and check
        vr_local = extract_local_number(vr['union_name'])
        cand_local = cand['local_number']
        local_bonus = 0
        if vr_local and cand_local:
            if normalize_local_number(vr_local) == normalize_local_number(cand_local):
                local_bonus = 0.15

        combined_score = (trgm_score * 0.5) + (token_score * 0.35) + local_bonus

        if combined_score > best_score:
            best_score = combined_score
            best_match = cand

    if best_match and best_score >= 0.45:
        cur.execute("""
            UPDATE nlrb_voluntary_recognition
            SET matched_union_fnum = %s,
                union_match_confidence = %s,
                union_match_method = 'trigram_token_independent'
            WHERE id = %s AND matched_union_fnum IS NULL
        """, (best_match['f_num'], round(min(best_score, 0.95), 2), vr['id']))
        if cur.rowcount > 0:
            trgm_matches += 1

    if (i + 1) % 100 == 0:
        print(f"    Processed {i+1}/{len(independents)}... ({trgm_matches} matches so far)")

print(f"  Matched: {trgm_matches}")

# Strategy 6b: Token-based matching for remaining unmatched (including non-independents)
print("\n--- Strategy 6b: Token-based matching for remaining unmatched ---")
cur.execute("""
    SELECT id, union_name, union_name_normalized
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
      AND union_name_normalized IS NOT NULL
""")
remaining = cur.fetchall()
print(f"  Processing {len(remaining)} remaining unmatched...")

token_matches = 0
for i, vr in enumerate(remaining):
    name = vr['union_name_normalized']
    key_tokens = extract_key_tokens(name)

    if not key_tokens or len(key_tokens) < 2:
        continue

    # Search for unions with matching key tokens
    token_patterns = ['%' + t + '%' for t in list(key_tokens)[:3]]

    cur.execute("""
        SELECT f_num, union_name, local_number
        FROM unions_master
        WHERE union_name ILIKE ANY(%s)
        ORDER BY members DESC NULLS LAST
        LIMIT 10
    """, (token_patterns,))

    candidates = cur.fetchall()
    best_match = None
    best_score = 0

    for cand in candidates:
        score = token_similarity(name, cand['union_name'])

        # Local number bonus
        vr_local = extract_local_number(vr['union_name'])
        if vr_local and cand['local_number']:
            if normalize_local_number(vr_local) == normalize_local_number(cand['local_number']):
                score += 0.15

        if score > best_score:
            best_score = score
            best_match = cand

    if best_match and best_score >= 0.55:
        cur.execute("""
            UPDATE nlrb_voluntary_recognition
            SET matched_union_fnum = %s,
                union_match_confidence = %s,
                union_match_method = 'token_match'
            WHERE id = %s AND matched_union_fnum IS NULL
        """, (best_match['f_num'], round(min(best_score, 0.90), 2), vr['id']))
        if cur.rowcount > 0:
            token_matches += 1

    if (i + 1) % 100 == 0:
        print(f"    Processed {i+1}/{len(remaining)}... ({token_matches} matches)")

print(f"  Matched: {token_matches}")

# Strategy 7: Expanded keyword matching for common union patterns
print("\n--- Strategy 7: Expanded keyword pattern matching ---")

# Extended pattern list with variations
patterns = [
    # Healthcare
    ('nurses', ['%nurs%'], 'NNU'),
    ('healthcare', ['%healthcare%', '%health care%', '%hospital%worker%'], 'SEIU'),

    # Education
    ('teachers', ['%teacher%', '%educator%', '%faculty%'], 'AFT'),
    ('education', ['%education%assoc%', '%school%employ%'], 'NEA'),

    # Building trades
    ('carpenters', ['%carpenter%', '%carpntr%', '%millwright%'], 'UBC'),
    ('plumbers', ['%plumber%', '%pipefitter%', '%steamfitter%'], 'UA'),
    ('electricians', ['%electric%', '%ibew%'], 'IBEW'),
    ('laborers', ['%laborer%', '%liuna%'], 'LIUNA'),
    ('ironworkers', ['%ironwork%', '%iron work%'], 'IW'),
    ('painters', ['%painter%', '%glazier%', '%drywall%'], 'IUPAT'),
    ('roofers', ['%roofer%', '%waterproof%'], 'ROOFERS'),
    ('sheetmetal', ['%sheet metal%', '%sheetmetal%', '%hvac%'], 'SMART'),
    ('boilermakers', ['%boilermak%', '%boiler mak%'], 'IBB'),
    ('operating_eng', ['%operating engineer%', '%iuoe%', '%heavy equip%'], 'IUOE'),
    ('bricklayers', ['%bricklayer%', '%mason%', '%tile%'], 'BAC'),

    # Public sector
    ('firefighters', ['%firefight%', '%fire fight%', '%iaff%'], 'IAFF'),
    ('police', ['%police%', '%law enforcement%', '%fop%', '%officer%'], 'FOP'),
    ('government', ['%government employ%', '%public employ%', '%afscme%', '%state employ%', '%county employ%', '%city employ%', '%municipal%'], 'AFSCME'),
    ('federal', ['%federal employ%', '%afge%'], 'AFGE'),

    # Postal
    ('postal', ['%postal%', '%letter carrier%', '%mail handler%'], 'APWU'),

    # Transportation
    ('transit', ['%transit%', '%bus driver%', '%atu%'], 'ATU'),
    ('transport', ['%transport worker%', '%twu%'], 'TWU'),
    ('airline', ['%airline%', '%flight attend%'], 'AFA'),
    ('pilots', ['%pilot%', '%alpa%'], 'ALPA'),
    ('teamsters', ['%teamster%', '%truck%driver%', '%freight%'], 'IBT'),

    # Manufacturing/Industrial
    ('auto', ['%auto%worker%', '%automobile%', '%uaw%'], 'UAW'),
    ('steel', ['%steelworker%', '%steel worker%', '%usw%', '%metal%worker%'], 'USW'),
    ('machinists', ['%machinist%', '%aerospace%', '%iam%'], 'IAM'),
    ('bakery', ['%bakery%', '%confection%', '%tobacco%', '%grain%'], 'BCTGM'),

    # Service/Retail
    ('food_workers', ['%food%commercial%', '%grocery%', '%retail%', '%ufcw%'], 'UFCW'),
    ('hotel', ['%hotel%', '%hospitality%', '%restaurant%', '%gaming%', '%casino%'], 'UNITEHERE'),
    ('service', ['%service employ%', '%seiu%', '%janitor%', '%custod%', '%security%'], 'SEIU'),

    # Communications
    ('communications', ['%communication%worker%', '%cwa%', '%telephone%', '%telecom%'], 'CWA'),
    ('office', ['%office%professional%', '%opeiu%', '%clerical%'], 'OPEIU'),

    # Entertainment
    ('stage', ['%stage%', '%theatrical%', '%iatse%', '%film%', '%motion picture%'], 'IATSE'),
    ('musicians', ['%musician%', '%afm%'], 'AFM'),
    ('writers', ['%writer%', '%wga%'], 'WGA'),
    ('actors', ['%actor%', '%sag%', '%aftra%', '%performer%'], 'SAGAFTRA'),
]

keyword_matches = 0
for keyword, pattern_list, default_affil in patterns:
    for pattern in pattern_list:
        cur.execute("""
            WITH matches AS (
                SELECT DISTINCT ON (vr.id)
                    vr.id as vr_id,
                    um.f_num,
                    0.55 as confidence
                FROM nlrb_voluntary_recognition vr
                JOIN unions_master um ON um.union_name ILIKE %s
                WHERE vr.matched_union_fnum IS NULL
                  AND vr.union_name_normalized ILIKE %s
                ORDER BY vr.id, um.members DESC NULLS LAST
            )
            UPDATE nlrb_voluntary_recognition vr
            SET matched_union_fnum = m.f_num,
                union_match_confidence = m.confidence,
                union_match_method = 'keyword_pattern'
            FROM matches m
            WHERE vr.id = m.vr_id
        """, (pattern, pattern))
        keyword_matches += cur.rowcount

print(f"  Matched: {keyword_matches}")

# Strategy 8: Enhanced local number extraction and matching
print("\n--- Strategy 8: Enhanced local number extraction and matching ---")
cur.execute("""
    SELECT id, union_name, union_name_normalized
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
      AND (
          union_name ILIKE '%local%'
          OR union_name ILIKE '%lodge%'
          OR union_name ILIKE '%branch%'
          OR union_name ILIKE '%division%'
          OR union_name ILIKE '%district%'
          OR union_name ILIKE '%chapter%'
          OR union_name ~ '\\d{2,5}$'
      )
""")
locals_to_check = cur.fetchall()
print(f"  Checking {len(locals_to_check)} records with potential local numbers...")

local_matches = 0
for vr in locals_to_check:
    # Use enhanced extraction
    local_num = extract_local_number(vr['union_name'])
    if not local_num:
        continue

    normalized_local = normalize_local_number(local_num)

    # Try to find matching local with normalized comparison
    cur.execute("""
        SELECT f_num, union_name, local_number
        FROM unions_master
        WHERE UPPER(REGEXP_REPLACE(local_number, '[-/\\s]', '', 'g')) = %s
        ORDER BY members DESC NULLS LAST
        LIMIT 3
    """, (normalized_local,))

    candidates = cur.fetchall()
    if candidates:
        # If multiple matches, try to pick the best one based on name similarity
        best_match = candidates[0]
        if len(candidates) > 1:
            best_score = 0
            for cand in candidates:
                score = token_similarity(vr['union_name_normalized'] or '', cand['union_name'])
                if score > best_score:
                    best_score = score
                    best_match = cand

        cur.execute("""
            UPDATE nlrb_voluntary_recognition
            SET matched_union_fnum = %s,
                union_match_confidence = 0.65,
                union_match_method = 'local_number_lookup'
            WHERE id = %s AND matched_union_fnum IS NULL
        """, (best_match['f_num'], vr['id']))
        if cur.rowcount > 0:
            local_matches += 1

print(f"  Matched: {local_matches}")

# Strategy 9: Acronym matching for remaining
print("\n--- Strategy 9: Acronym matching for remaining ---")
cur.execute("""
    SELECT id, union_name, union_name_normalized
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
""")
remaining_for_acronym = cur.fetchall()

acronym_matches = 0
for vr in remaining_for_acronym:
    name = (vr['union_name_normalized'] or '').lower()
    # Check if name contains a known acronym
    for acronym in UNION_ACRONYMS:
        if acronym in name.split():
            # Find union with this acronym as affiliation
            cur.execute("""
                SELECT f_num, union_name
                FROM unions_master
                WHERE LOWER(aff_abbr) = %s
                ORDER BY members DESC NULLS LAST
                LIMIT 1
            """, (acronym,))
            match = cur.fetchone()
            if match:
                cur.execute("""
                    UPDATE nlrb_voluntary_recognition
                    SET matched_union_fnum = %s,
                        union_match_confidence = 0.60,
                        union_match_method = 'acronym_match'
                    WHERE id = %s AND matched_union_fnum IS NULL
                """, (match['f_num'], vr['id']))
                if cur.rowcount > 0:
                    acronym_matches += 1
                    break

print(f"  Matched: {acronym_matches}")

# Summary
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(matched_union_fnum) as matched
    FROM nlrb_voluntary_recognition
""")
final = cur.fetchone()

print(f"\n{'=' * 60}")
print(f"CHECKPOINT 4B SUMMARY - Fuzzy Matching (Enhanced)")
print(f"{'=' * 60}")
print(f"  Affiliation variants:       {affiliation_variant_matches}")
print(f"  Trigram + token (indep):    {trgm_matches}")
print(f"  Token matching:             {token_matches}")
print(f"  Keyword patterns:           {keyword_matches}")
print(f"  Local number lookup:        {local_matches}")
print(f"  Acronym matching:           {acronym_matches}")
print(f"\n  TOTAL MATCHED:              {final['matched']} ({100*final['matched']/final['total']:.1f}%)")
print(f"  REMAINING UNMATCHED:        {final['total'] - final['matched']} ({100*(final['total']-final['matched'])/final['total']:.1f}%)")

# Match method breakdown
print(f"\nMatch method breakdown:")
cur.execute("""
    SELECT union_match_method, COUNT(*), 
           ROUND(AVG(union_match_confidence), 2) as avg_conf
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NOT NULL
    GROUP BY union_match_method
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print(f"  {row['union_match_method']:25} {row['count']:4} (avg conf: {row['avg_conf']})")

cur.close()
conn.close()

print(f"\n{'=' * 60}")
print("CHECKPOINT 4B COMPLETE")
print("Ready for 4C: Verification and report")
print(f"{'=' * 60}")
