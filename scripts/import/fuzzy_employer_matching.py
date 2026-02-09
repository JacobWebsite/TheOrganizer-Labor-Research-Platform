import os
"""
Fuzzy Employer Matching: NLRB Participants → F7 Employers
Improves match rate from 9.4% using name normalization and fuzzy matching
"""
import psycopg2
from collections import defaultdict
import re
from difflib import SequenceMatcher

def normalize_name(name):
    """Normalize employer name for matching"""
    if not name:
        return ""
    
    # Lowercase
    name = name.lower().strip()
    
    # Remove common suffixes
    suffixes = [
        r'\binc\.?\b', r'\bllc\.?\b', r'\bcorp\.?\b', r'\bcorporation\b',
        r'\bco\.?\b', r'\bcompany\b', r'\bltd\.?\b', r'\blimited\b',
        r'\blp\b', r'\bllp\b', r'\bpc\b', r'\bp\.c\.\b',
        r'\bd/b/a\b.*', r'\baka\b.*', r'\bt/a\b.*',
        r'\bthe\b'
    ]
    for suffix in suffixes:
        name = re.sub(suffix, '', name)
    
    # Remove punctuation except spaces
    name = re.sub(r'[^\w\s]', '', name)
    
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def similarity(a, b):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, a, b).ratio()

def main():
    conn = psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )
    cur = conn.cursor()
    
    print("Loading F7 employers...")
    cur.execute("""
        SELECT employer_id, employer_name, city, state
        FROM f7_employers_deduped
        WHERE employer_name IS NOT NULL
    """)
    
    # Build F7 lookup: normalized_name -> [(id, original_name, city, state), ...]
    f7_by_name = defaultdict(list)
    f7_by_state_name = defaultdict(list)
    
    for row in cur.fetchall():
        emp_id, name, city, state = row
        norm = normalize_name(name)
        if len(norm) > 2:
            f7_by_name[norm].append((emp_id, name, city, state))
            if state:
                key = (state.upper() if state else '', norm)
                f7_by_state_name[key].append((emp_id, name, city, state))
    
    print(f"  Loaded {len(f7_by_name):,} unique normalized F7 names")
    
    print("\nLoading unmatched NLRB employers...")
    cur.execute("""
        SELECT id, participant_name, city, state
        FROM nlrb_participants
        WHERE participant_type = 'Employer'
        AND matched_employer_id IS NULL
        AND participant_name IS NOT NULL
        AND LENGTH(TRIM(participant_name)) > 3
        AND participant_name NOT LIKE '%P.C.%'
        AND participant_name NOT LIKE '%LLP%'
        AND participant_name NOT LIKE '%Esq%'
        LIMIT 50000
    """)
    nlrb_employers = cur.fetchall()
    print(f"  Loaded {len(nlrb_employers):,} unmatched NLRB employers")
    
    # Match
    print("\nMatching...")
    matches = []
    exact_matches = 0
    fuzzy_matches = 0
    
    for nlrb_id, name, city, state in nlrb_employers:
        norm = normalize_name(name)
        if len(norm) < 3:
            continue
            
        match = None
        method = None
        confidence = 0
        
        # Try exact normalized match with state
        state_key = (state.upper() if state else '', norm)
        if state_key in f7_by_state_name:
            match = f7_by_state_name[state_key][0]
            method = 'exact_state'
            confidence = 1.0
            exact_matches += 1
        
        # Try exact normalized match without state
        elif norm in f7_by_name:
            match = f7_by_name[norm][0]
            method = 'exact_name'
            confidence = 0.95
            exact_matches += 1
        
        # Try fuzzy match (only for longer names)
        elif len(norm) > 8:
            best_score = 0
            best_match = None
            
            # Check state-specific matches first
            if state:
                for key, employers in f7_by_state_name.items():
                    if key[0] == state.upper():
                        score = similarity(norm, key[1])
                        if score > best_score and score > 0.85:
                            best_score = score
                            best_match = employers[0]
            
            if best_match:
                match = best_match
                method = 'fuzzy_state'
                confidence = best_score
                fuzzy_matches += 1
        
        if match:
            matches.append((nlrb_id, match[0], method, confidence, name, match[1]))
    
    print(f"\n{'='*60}")
    print(f"MATCHING RESULTS")
    print(f"{'='*60}")
    print(f"Exact matches: {exact_matches:,}")
    print(f"Fuzzy matches: {fuzzy_matches:,}")
    print(f"Total new matches: {len(matches):,}")
    
    # Show sample matches
    print(f"\nSample matches:")
    for m in matches[:15]:
        nlrb_id, f7_id, method, conf, nlrb_name, f7_name = m
        print(f"  [{method}:{conf:.2f}] {nlrb_name[:40]:40} → {f7_name[:40]}")
    
    # Apply matches to database
    if matches:
        print(f"\nApplying {len(matches):,} matches to database...")
        for nlrb_id, f7_id, method, confidence, _, _ in matches:
            cur.execute("""
                UPDATE nlrb_participants
                SET matched_employer_id = %s,
                    match_method = %s,
                    match_confidence = %s
                WHERE id = %s
            """, (f7_id, method, confidence, nlrb_id))
        
        conn.commit()
        print("Done!")
    
    # Check new match rate
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(matched_employer_id) as matched
        FROM nlrb_participants
        WHERE participant_type = 'Employer'
    """)
    row = cur.fetchone()
    print(f"\nNew employer match rate: {row[1]:,} / {row[0]:,} = {100*row[1]/row[0]:.1f}%")
    
    conn.close()

if __name__ == "__main__":
    main()
