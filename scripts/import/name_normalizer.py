"""
Name Normalizer for Labor Relations Platform
Phase 2: Standardize employer and union names before fuzzy matching

Usage:
    from name_normalizer import (
        # Employer functions
        normalize_employer,
        normalize_employer_aggressive,
        employer_token_similarity,
        extract_employer_key_words,
        compute_employer_match_score,
        EMPLOYER_ABBREVIATIONS,
        EMPLOYER_NAME_VARIATIONS,
        # Union functions
        normalize_union,
        normalize_for_comparison,
        extract_local_number,
        normalize_local_number,
        token_similarity,
        extract_key_tokens,
        compute_match_score,
        get_affiliation_variants,
        AFFILIATION_MAPPINGS,
        UNION_ACRONYMS,
        # Phonetic functions
        soundex,
        metaphone,
        double_metaphone,
        phonetic_match_score,
        phonetic_similarity,
        # Order-independent union matching
        extract_union_tokens,
        union_token_match_score,
        find_best_union_match,
        compare_union_names,
        UNION_ACRONYM_EXPANSIONS,
    )
"""

import re
from typing import Optional, Tuple, List


# ============================================================================
# PHONETIC ALGORITHMS
# ============================================================================

def soundex(name: str) -> str:
    """
    Generate Soundex code for a name.

    Soundex is a phonetic algorithm that indexes names by sound.
    Names that sound alike get the same code.

    Examples:
        soundex("Robert") -> "R163"
        soundex("Rupert") -> "R163"
        soundex("Smith") -> "S530"
        soundex("Smythe") -> "S530"

    Args:
        name: Input name string

    Returns:
        4-character Soundex code
    """
    if not name:
        return ""

    # Convert to uppercase and keep only letters
    name = ''.join(c for c in name.upper() if c.isalpha())
    if not name:
        return ""

    # Soundex mapping
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6',
        # A, E, I, O, U, H, W, Y are ignored (mapped to '')
    }

    # Keep first letter
    result = name[0]
    prev_code = mapping.get(name[0], '')

    # Process remaining letters
    for char in name[1:]:
        code = mapping.get(char, '')
        if code and code != prev_code:
            result += code
        prev_code = code if code else prev_code

    # Pad with zeros or truncate to 4 characters
    result = (result + '000')[:4]

    return result


def metaphone(name: str) -> str:
    """
    Generate Metaphone code for a name.

    Metaphone is a more accurate phonetic algorithm than Soundex,
    especially for English words.

    Examples:
        metaphone("Smith") -> "SM0"
        metaphone("Schmidt") -> "SXMT" or "SKMT"
        metaphone("Phone") -> "FN"

    Args:
        name: Input name string

    Returns:
        Metaphone code string
    """
    if not name:
        return ""

    # Convert to uppercase
    name = name.upper()
    # Keep only letters
    name = ''.join(c for c in name if c.isalpha())
    if not name:
        return ""

    result = []
    i = 0
    length = len(name)

    # Helper to get character at position (returns '' if out of bounds)
    def get(pos):
        return name[pos] if 0 <= pos < length else ''

    # Helper to check if position is a vowel
    def is_vowel(pos):
        return get(pos) in 'AEIOU'

    # Drop initial silent letters
    if name[:2] in ('KN', 'GN', 'PN', 'AE', 'WR'):
        i = 1
    elif name[:1] == 'X':
        name = 'S' + name[1:]
    elif name[:2] == 'WH':
        name = 'W' + name[2:]

    while i < length:
        c = get(i)

        # Skip vowels unless at start
        if c in 'AEIOU':
            if i == 0:
                result.append(c)
            i += 1
            continue

        if c == 'B':
            # -MB at end is silent
            if not (i == length - 1 and get(i-1) == 'M'):
                result.append('P')
            i += 1

        elif c == 'C':
            # -CIA-, -CH-
            if get(i+1) == 'I' and get(i+2) == 'A':
                result.append('X')
                i += 3
            elif get(i+1) == 'H':
                result.append('X')
                i += 2
            elif get(i+1) in 'IEY':
                result.append('S')
                i += 1
            else:
                result.append('K')
                i += 1

        elif c == 'D':
            if get(i+1) == 'G' and get(i+2) in 'IEY':
                result.append('J')
                i += 3
            else:
                result.append('T')
                i += 1

        elif c == 'F':
            result.append('F')
            i += 2 if get(i+1) == 'F' else 1

        elif c == 'G':
            if get(i+1) == 'H':
                if i > 0 and not is_vowel(i-1):
                    i += 2
                else:
                    result.append('F')
                    i += 2
            elif get(i+1) == 'N':
                if i == 0 or (i == length - 2):
                    i += 2
                else:
                    result.append('K')
                    i += 1
            elif get(i+1) in 'IEY':
                result.append('J')
                i += 1
            else:
                result.append('K')
                i += 2 if get(i+1) == 'G' else 1

        elif c == 'H':
            # H is silent after vowel or before non-vowel
            if i > 0 and is_vowel(i-1):
                i += 1
            elif i < length - 1 and not is_vowel(i+1):
                i += 1
            else:
                result.append('H')
                i += 1

        elif c == 'J':
            result.append('J')
            i += 1

        elif c == 'K':
            result.append('K')
            i += 2 if get(i+1) == 'K' else 1

        elif c == 'L':
            result.append('L')
            i += 2 if get(i+1) == 'L' else 1

        elif c == 'M':
            result.append('M')
            i += 2 if get(i+1) == 'M' else 1

        elif c == 'N':
            result.append('N')
            i += 2 if get(i+1) == 'N' else 1

        elif c == 'P':
            if get(i+1) == 'H':
                result.append('F')
                i += 2
            else:
                result.append('P')
                i += 2 if get(i+1) == 'P' else 1

        elif c == 'Q':
            result.append('K')
            i += 1

        elif c == 'R':
            result.append('R')
            i += 2 if get(i+1) == 'R' else 1

        elif c == 'S':
            if get(i+1) == 'H':
                result.append('X')
                i += 2
            elif get(i+1) == 'I' and get(i+2) in 'OA':
                result.append('X')
                i += 3
            else:
                result.append('S')
                i += 2 if get(i+1) == 'S' else 1

        elif c == 'T':
            if get(i+1) == 'I' and get(i+2) in 'OA':
                result.append('X')
                i += 3
            elif get(i+1) == 'H':
                result.append('0')  # TH sound
                i += 2
            elif get(i+1) == 'C' and get(i+2) == 'H':
                i += 3
            else:
                result.append('T')
                i += 2 if get(i+1) == 'T' else 1

        elif c == 'V':
            result.append('F')
            i += 1

        elif c == 'W':
            if is_vowel(i+1):
                result.append('W')
            i += 1

        elif c == 'X':
            result.append('KS')
            i += 1

        elif c == 'Y':
            if is_vowel(i+1):
                result.append('Y')
            i += 1

        elif c == 'Z':
            result.append('S')
            i += 1

        else:
            i += 1

    return ''.join(result)


def double_metaphone(name: str) -> Tuple[str, str]:
    """
    Generate Double Metaphone codes for a name.

    Returns two codes: primary and alternate. The alternate handles
    cases where a name might have multiple pronunciations.

    Examples:
        double_metaphone("Smith") -> ("SM0", "XMT")
        double_metaphone("Schmidt") -> ("XMT", "SMT")

    Args:
        name: Input name string

    Returns:
        Tuple of (primary_code, alternate_code)
    """
    # Simplified double metaphone - returns primary and a variant
    primary = metaphone(name)

    # Generate alternate by trying common sound substitutions
    if not name:
        return ("", "")

    name_upper = name.upper()
    alternate = primary

    # Common alternate sounds
    if 'SCH' in name_upper:
        alternate = primary.replace('X', 'SK')
    elif 'PH' in name_upper:
        alternate = metaphone(name_upper.replace('PH', 'F'))
    elif name_upper.startswith('X'):
        alternate = 'S' + primary[1:] if len(primary) > 1 else 'S'
    elif 'GH' in name_upper:
        alternate = metaphone(name_upper.replace('GH', 'F'))
    elif 'CK' in name_upper:
        alternate = metaphone(name_upper.replace('CK', 'K'))

    return (primary, alternate)


def phonetic_codes(name: str) -> dict:
    """
    Generate all phonetic codes for a name.

    Args:
        name: Input name string

    Returns:
        Dictionary with soundex, metaphone, and double_metaphone codes
    """
    dm_primary, dm_alt = double_metaphone(name)
    return {
        'soundex': soundex(name),
        'metaphone': metaphone(name),
        'double_metaphone_primary': dm_primary,
        'double_metaphone_alt': dm_alt,
    }


def phonetic_similarity(name1: str, name2: str) -> float:
    """
    Calculate phonetic similarity between two names.

    Uses Soundex and Metaphone to determine if names sound alike.

    Args:
        name1: First name
        name2: Second name

    Returns:
        Similarity score from 0.0 to 1.0
    """
    if not name1 or not name2:
        return 0.0

    # Get phonetic codes
    s1, s2 = soundex(name1), soundex(name2)
    m1, m2 = metaphone(name1), metaphone(name2)
    dm1, dm1_alt = double_metaphone(name1)
    dm2, dm2_alt = double_metaphone(name2)

    score = 0.0

    # Soundex match (weight: 0.25)
    if s1 and s2:
        if s1 == s2:
            score += 0.25
        elif s1[:3] == s2[:3]:  # First 3 chars match
            score += 0.15
        elif s1[0] == s2[0]:  # Same first letter
            score += 0.05

    # Metaphone match (weight: 0.40)
    if m1 and m2:
        if m1 == m2:
            score += 0.40
        else:
            # Partial match - compare common prefix
            min_len = min(len(m1), len(m2))
            if min_len > 0:
                common = sum(1 for a, b in zip(m1, m2) if a == b)
                score += 0.40 * (common / max(len(m1), len(m2)))

    # Double Metaphone match (weight: 0.35)
    dm_match = False
    if dm1 == dm2 or dm1 == dm2_alt or dm1_alt == dm2 or dm1_alt == dm2_alt:
        score += 0.35
        dm_match = True
    elif not dm_match:
        # Partial double metaphone match
        best_match = 0
        for code1 in [dm1, dm1_alt]:
            for code2 in [dm2, dm2_alt]:
                if code1 and code2:
                    common = sum(1 for a, b in zip(code1, code2) if a == b)
                    match_ratio = common / max(len(code1), len(code2))
                    best_match = max(best_match, match_ratio)
        score += 0.35 * best_match

    return min(score, 1.0)


def phonetic_match_score(name1: str, name2: str,
                         include_token_phonetics: bool = True) -> dict:
    """
    Comprehensive phonetic matching between two names.

    Computes phonetic similarity at both the full-name and token levels.

    Args:
        name1: First name (e.g., VR employer name)
        name2: Second name (e.g., F7 employer name)
        include_token_phonetics: Whether to compare individual word phonetics

    Returns:
        Dictionary with:
        - overall_score: Combined phonetic similarity (0.0-1.0)
        - full_name_score: Phonetic similarity of full names
        - token_score: Average phonetic similarity of matching tokens
        - soundex_match: Boolean if Soundex codes match
        - metaphone_match: Boolean if Metaphone codes match
        - details: Detailed breakdown of codes
    """
    if not name1 or not name2:
        return {
            'overall_score': 0.0,
            'full_name_score': 0.0,
            'token_score': 0.0,
            'soundex_match': False,
            'metaphone_match': False,
            'details': {}
        }

    # Clean names - remove punctuation, lowercase
    clean1 = re.sub(r'[^\w\s]', ' ', name1.lower()).strip()
    clean2 = re.sub(r'[^\w\s]', ' ', name2.lower()).strip()

    # Full name phonetic comparison
    full_name_score = phonetic_similarity(clean1, clean2)

    # Get phonetic codes for full names
    s1, s2 = soundex(clean1), soundex(clean2)
    m1, m2 = metaphone(clean1), metaphone(clean2)

    soundex_match = s1 == s2 if (s1 and s2) else False
    metaphone_match = m1 == m2 if (m1 and m2) else False

    # Token-level phonetic comparison
    token_score = 0.0
    if include_token_phonetics:
        tokens1 = [t for t in clean1.split() if len(t) >= 3]
        tokens2 = [t for t in clean2.split() if len(t) >= 3]

        if tokens1 and tokens2:
            # Find best phonetic matches between tokens
            token_matches = []
            for t1 in tokens1:
                best_match = 0.0
                for t2 in tokens2:
                    sim = phonetic_similarity(t1, t2)
                    best_match = max(best_match, sim)
                token_matches.append(best_match)

            if token_matches:
                token_score = sum(token_matches) / len(token_matches)

    # Combine scores
    if include_token_phonetics:
        overall_score = (full_name_score * 0.4) + (token_score * 0.6)
    else:
        overall_score = full_name_score

    return {
        'overall_score': round(overall_score, 3),
        'full_name_score': round(full_name_score, 3),
        'token_score': round(token_score, 3),
        'soundex_match': soundex_match,
        'metaphone_match': metaphone_match,
        'details': {
            'name1_soundex': s1,
            'name2_soundex': s2,
            'name1_metaphone': m1,
            'name2_metaphone': m2,
        }
    }


def find_phonetic_matches(target: str, candidates: List[str],
                          threshold: float = 0.6) -> List[Tuple[str, float]]:
    """
    Find phonetically similar names from a list of candidates.

    Args:
        target: Name to match
        candidates: List of candidate names to compare
        threshold: Minimum phonetic similarity score (default 0.6)

    Returns:
        List of (candidate_name, score) tuples, sorted by score descending
    """
    matches = []
    for candidate in candidates:
        result = phonetic_match_score(target, candidate)
        if result['overall_score'] >= threshold:
            matches.append((candidate, result['overall_score']))

    return sorted(matches, key=lambda x: -x[1])


# ============================================================================
# ORDER-INDEPENDENT TOKEN MATCHING FOR UNIONS
# ============================================================================

# Acronym to full name expansions for matching
UNION_ACRONYM_EXPANSIONS = {
    'ibt': ['international', 'brotherhood', 'teamsters'],
    'teamsters': ['international', 'brotherhood', 'teamsters'],
    'seiu': ['service', 'employees', 'international', 'union'],
    'ufcw': ['united', 'food', 'commercial', 'workers'],
    'uaw': ['united', 'auto', 'automobile', 'workers'],
    'usw': ['united', 'steelworkers', 'steel', 'workers'],
    'cwa': ['communications', 'workers', 'america'],
    'ibew': ['international', 'brotherhood', 'electrical', 'workers'],
    'iam': ['international', 'association', 'machinists', 'aerospace'],
    'iamaw': ['international', 'association', 'machinists', 'aerospace', 'workers'],
    'liuna': ['laborers', 'international', 'union', 'north', 'america'],
    'afscme': ['american', 'federation', 'state', 'county', 'municipal', 'employees'],
    'aft': ['american', 'federation', 'teachers'],
    'nea': ['national', 'education', 'association'],
    'iaff': ['international', 'association', 'fire', 'fighters'],
    'iuoe': ['international', 'union', 'operating', 'engineers'],
    'unite': ['unite', 'here', 'hotel', 'employees', 'restaurant'],
    'here': ['hotel', 'employees', 'restaurant'],
    'unitehere': ['unite', 'here', 'hotel', 'employees', 'restaurant'],
    'smart': ['sheet', 'metal', 'air', 'rail', 'transportation'],
    'bctgm': ['bakery', 'confectionery', 'tobacco', 'grain', 'millers'],
    'opeiu': ['office', 'professional', 'employees', 'international', 'union'],
    'apwu': ['american', 'postal', 'workers', 'union'],
    'nalc': ['national', 'association', 'letter', 'carriers'],
    'atda': ['american', 'train', 'dispatchers', 'association'],
    'bac': ['bricklayers', 'allied', 'craftworkers'],
    'iupat': ['international', 'union', 'painters', 'allied', 'trades'],
    'ua': ['united', 'association', 'plumbers', 'pipefitters'],
    'ubc': ['united', 'brotherhood', 'carpenters'],
    'atu': ['amalgamated', 'transit', 'union'],
    'twu': ['transport', 'workers', 'union'],
}

# Words that are common but don't help identify a specific union
UNION_STOPWORDS = {
    'the', 'a', 'an', 'of', 'and', 'for', 'in', 'at', 'by', 'to',
    'local', 'union', 'council', 'district', 'chapter', 'lodge',
    'branch', 'division', 'unit', 'joint', 'board', 'afl', 'cio',
    'aflcio', 'afl-cio', 'international', 'national', 'american',
    'united', 'general', 'no', 'number'
}

# High-value identifying words (trade/industry specific)
# Include both singular and plural forms for proper matching
UNION_KEY_IDENTIFIERS = {
    # Trades (singular and plural)
    'teamster', 'teamsters', 'carpenter', 'carpenters',
    'plumber', 'plumbers', 'pipefitter', 'pipefitters',
    'electrician', 'electricians', 'electrical',
    'laborer', 'laborers', 'painter', 'painters',
    'roofer', 'roofers', 'ironworker', 'ironworkers',
    'steelworker', 'steelworkers', 'machinist', 'machinists',
    'boilermaker', 'boilermakers', 'bricklayer', 'bricklayers',
    'glazier', 'glaziers', 'sheetmetal', 'millwright', 'millwrights',
    'elevator', 'operator', 'operators', 'engineer', 'engineers',
    # Workers/Employees
    'worker', 'workers', 'employee', 'employees',
    # Industries
    'teacher', 'teachers', 'nurse', 'nurses',
    'firefighter', 'firefighters', 'police', 'postal',
    'transit', 'airline', 'pilot', 'pilots',
    'autoworker', 'autoworkers', 'auto', 'automobile',
    'food', 'commercial', 'retail', 'hotel', 'restaurant',
    'healthcare', 'hospital', 'service', 'services', 'government',
    'communication', 'communications', 'telephone',
    'office', 'professional', 'public',
    # Organizations
    'brotherhood', 'federation', 'association', 'guild',
}

# Map plural forms to singular for consistent matching
UNION_WORD_NORMALIZATIONS = {
    'teamsters': 'teamster', 'carpenters': 'carpenter',
    'plumbers': 'plumber', 'pipefitters': 'pipefitter',
    'electricians': 'electrician', 'laborers': 'laborer',
    'painters': 'painter', 'roofers': 'roofer',
    'ironworkers': 'ironworker', 'steelworkers': 'steelworker',
    'machinists': 'machinist', 'boilermakers': 'boilermaker',
    'bricklayers': 'bricklayer', 'glaziers': 'glazier',
    'millwrights': 'millwright', 'operators': 'operator',
    'engineers': 'engineer', 'workers': 'worker',
    'employees': 'employee', 'teachers': 'teacher',
    'nurses': 'nurse', 'firefighters': 'firefighter',
    'pilots': 'pilot', 'autoworkers': 'autoworker',
    'services': 'service', 'communications': 'communication',
}


def normalize_union_word(word: str) -> str:
    """
    Normalize a union word to its base form for consistent matching.
    Handles plural -> singular conversions.
    """
    word = word.lower().strip()
    return UNION_WORD_NORMALIZATIONS.get(word, word)


def extract_union_tokens(name: str) -> dict:
    """
    Extract meaningful tokens from a union name for order-independent matching.

    Returns a dictionary with:
    - identifiers: Key identifying words (trades, industries)
    - acronyms: Known union acronyms found
    - local_number: Extracted local/district number
    - other_tokens: Other meaningful words
    - all_tokens: All tokens combined

    Args:
        name: Union name string

    Returns:
        Dictionary of extracted token categories
    """
    if not name:
        return {
            'identifiers': set(),
            'acronyms': set(),
            'local_number': None,
            'other_tokens': set(),
            'all_tokens': set()
        }

    # Normalize the name
    normalized = normalize_union(name, expand_abbrevs=False, fix_typos=True)
    tokens = set(normalized.split())

    # Extract local number
    local_num = extract_local_number(name)

    # Categorize tokens
    identifiers = set()
    acronyms = set()
    other_tokens = set()

    for token in tokens:
        # Skip stopwords and short tokens
        if token in UNION_STOPWORDS or len(token) < 2:
            continue

        # Normalize the token (handle plural/singular)
        normalized_token = normalize_union_word(token)

        # Check if it's a known acronym
        if token in UNION_ACRONYM_EXPANSIONS:
            acronyms.add(token)
        # Check if normalized form is a key identifier
        elif normalized_token in UNION_KEY_IDENTIFIERS or token in UNION_KEY_IDENTIFIERS:
            identifiers.add(normalized_token)  # Store normalized form
        # Skip numbers (handled separately)
        elif token.isdigit():
            continue
        # Other meaningful tokens
        elif len(token) >= 3:
            other_tokens.add(normalized_token)  # Store normalized form

    # Combine all meaningful tokens
    all_tokens = identifiers | acronyms | other_tokens

    return {
        'identifiers': identifiers,
        'acronyms': acronyms,
        'local_number': local_num,
        'other_tokens': other_tokens,
        'all_tokens': all_tokens
    }


def expand_acronyms_to_tokens(acronyms: set, normalize: bool = True,
                               filter_stopwords: bool = False) -> set:
    """
    Expand union acronyms to their component words.

    Args:
        acronyms: Set of acronyms (e.g., {'ibt', 'seiu'})
        normalize: If True, normalize words to base forms (singular, etc.)
        filter_stopwords: If True, filter out stopwords from expansion

    Returns:
        Set of expanded words (normalized if requested)
    """
    expanded = set()
    for acr in acronyms:
        if acr in UNION_ACRONYM_EXPANSIONS:
            for word in UNION_ACRONYM_EXPANSIONS[acr]:
                normalized_word = normalize_union_word(word) if normalize else word
                # Optionally filter stopwords
                if filter_stopwords and normalized_word in UNION_STOPWORDS:
                    continue
                expanded.add(normalized_word)
    return expanded


# Generic identifiers that appear in multiple union types (not unique)
GENERIC_IDENTIFIERS = {
    'worker', 'workers', 'employee', 'employees',
    'brotherhood', 'federation', 'association', 'guild',
}


def get_key_identifiers_from_expansion(acronyms: set) -> set:
    """
    Get only the KEY IDENTIFIERS from acronym expansion.
    These are trade/industry-specific words that uniquely identify the union.

    Args:
        acronyms: Set of acronyms (e.g., {'seiu', 'liuna'})

    Returns:
        Set of key identifier words from the expansion
    """
    expanded = expand_acronyms_to_tokens(acronyms, normalize=True)
    # Return only words that are key identifiers
    return expanded & UNION_KEY_IDENTIFIERS


def get_specific_identifiers_from_expansion(acronyms: set) -> set:
    """
    Get SPECIFIC (non-generic) identifiers from acronym expansion.
    These are industry/trade-specific words that uniquely identify the union type.
    Excludes generic words like 'worker' that appear in multiple union names.

    Args:
        acronyms: Set of acronyms (e.g., {'uaw', 'usw'})

    Returns:
        Set of specific identifier words
    """
    key_ids = get_key_identifiers_from_expansion(acronyms)
    # Remove generic identifiers
    return key_ids - GENERIC_IDENTIFIERS


def union_token_match_score(name1: str, name2: str) -> dict:
    """
    Calculate order-independent token match score between two union names.

    Handles cases like:
    - "Teamsters Local 705" vs "Local 705 International Brotherhood of Teamsters"
    - "SEIU Local 1000" vs "Service Employees International Union Local 1000"

    Args:
        name1: First union name
        name2: Second union name

    Returns:
        Dictionary with:
        - overall_score: Combined match score (0.0-1.0)
        - identifier_score: Score based on key identifiers
        - acronym_match: Whether acronyms match or expand to same
        - local_match: Whether local numbers match
        - token_overlap: Jaccard similarity of all tokens
        - details: Breakdown of matched/unmatched tokens
    """
    if not name1 or not name2:
        return {
            'overall_score': 0.0,
            'identifier_score': 0.0,
            'acronym_match': False,
            'local_match': False,
            'token_overlap': 0.0,
            'details': {}
        }

    # Extract tokens from both names
    tokens1 = extract_union_tokens(name1)
    tokens2 = extract_union_tokens(name2)

    # 1. Check local number match (high importance)
    local_match = False
    local_score = 0.0
    if tokens1['local_number'] and tokens2['local_number']:
        norm1 = normalize_local_number(tokens1['local_number'])
        norm2 = normalize_local_number(tokens2['local_number'])
        if norm1 == norm2:
            local_match = True
            local_score = 1.0
        elif norm1.startswith(norm2) or norm2.startswith(norm1):
            local_match = True
            local_score = 0.7

    # 2. Check acronym match (expand and compare)
    acronym_match = False
    acronym_score = 0.0

    # Direct acronym match (same acronym)
    if tokens1['acronyms'] & tokens2['acronyms']:
        acronym_match = True
        acronym_score = 1.0
    else:
        # Get KEY IDENTIFIERS from acronym expansions (trade-specific words only)
        key_ids1 = get_key_identifiers_from_expansion(tokens1['acronyms'])
        key_ids2 = get_key_identifiers_from_expansion(tokens2['acronyms'])

        # Check if acronym's key identifiers match the other name's identifiers
        # This catches: SEIU -> {service, employee} matching "Service Employees..."
        # And: LIUNA -> {laborer} matching "Laborers Local..."
        if key_ids1 and tokens2['identifiers']:
            key_overlap = key_ids1 & tokens2['identifiers']
            if key_overlap:
                acronym_match = True
                # Score based on how many key identifiers matched
                acronym_score = min(len(key_overlap) / len(key_ids1), 1.0) * 0.95

        if not acronym_match and key_ids2 and tokens1['identifiers']:
            key_overlap = key_ids2 & tokens1['identifiers']
            if key_overlap:
                acronym_match = True
                acronym_score = min(len(key_overlap) / len(key_ids2), 1.0) * 0.95

        # Both have acronyms - check if their SPECIFIC identifiers overlap
        # This prevents false positives like UAW vs USW (auto != steel)
        if not acronym_match and tokens1['acronyms'] and tokens2['acronyms']:
            # Get specific (non-generic) identifiers for each
            spec_ids1 = get_specific_identifiers_from_expansion(tokens1['acronyms'])
            spec_ids2 = get_specific_identifiers_from_expansion(tokens2['acronyms'])

            if spec_ids1 and spec_ids2:
                spec_overlap = spec_ids1 & spec_ids2
                if spec_overlap:
                    # They share specific identifiers -> same union type
                    acronym_match = True
                    acronym_score = 0.9
                else:
                    # Different specific identifiers (auto vs steel) = different unions
                    acronym_score = -0.5  # Strong penalty
            elif key_ids1 & key_ids2:
                # No specific identifiers but share generic ones - weak match
                acronym_match = True
                acronym_score = 0.5

    # 3. Check identifier overlap (trade/industry words)
    identifier_overlap = 0.0
    if tokens1['identifiers'] or tokens2['identifiers']:
        all_identifiers = tokens1['identifiers'] | tokens2['identifiers']
        common_identifiers = tokens1['identifiers'] & tokens2['identifiers']
        if all_identifiers:
            identifier_overlap = len(common_identifiers) / len(all_identifiers)

    # 4. Overall token overlap (Jaccard)
    all_tokens1 = tokens1['all_tokens'] | expand_acronyms_to_tokens(tokens1['acronyms'])
    all_tokens2 = tokens2['all_tokens'] | expand_acronyms_to_tokens(tokens2['acronyms'])

    token_overlap = 0.0
    if all_tokens1 or all_tokens2:
        intersection = all_tokens1 & all_tokens2
        union = all_tokens1 | all_tokens2
        if union:
            token_overlap = len(intersection) / len(union)

    # 5. Phonetic matching for remaining tokens
    phonetic_score = 0.0
    unmatched1 = tokens1['all_tokens'] - tokens2['all_tokens']
    unmatched2 = tokens2['all_tokens'] - tokens1['all_tokens']

    if unmatched1 and unmatched2:
        phonetic_matches = 0
        for t1 in unmatched1:
            for t2 in unmatched2:
                if phonetic_similarity(t1, t2) >= 0.8:
                    phonetic_matches += 1
                    break
        if unmatched1:
            phonetic_score = phonetic_matches / len(unmatched1)

    # Calculate overall score with weights
    # IMPORTANT: Local number alone is not enough - need union identity match too

    # Handle mismatch penalty (different unions with same local)
    if acronym_score < 0:
        # Different unions (e.g., UAW vs USW with same local number)
        overall_score = max(0.0, 0.15 + acronym_score + token_overlap * 0.3)
        return {
            'overall_score': round(overall_score, 3),
            'identifier_score': round(identifier_overlap, 3),
            'acronym_match': False,
            'local_match': local_match,
            'token_overlap': round(token_overlap, 3),
            'details': {
                'name1_identifiers': tokens1['identifiers'],
                'name2_identifiers': tokens2['identifiers'],
                'name1_acronyms': tokens1['acronyms'],
                'name2_acronyms': tokens2['acronyms'],
                'name1_local': tokens1['local_number'],
                'name2_local': tokens2['local_number'],
                'common_tokens': tokens1['all_tokens'] & tokens2['all_tokens'],
            }
        }

    identity_score = max(acronym_score, identifier_overlap)

    if acronym_match and acronym_score >= 0.5:
        # Strong identity match through acronym expansion
        # This handles SEIU -> "Service Employees..." and LIUNA -> "Laborers..."
        overall_score = (
            acronym_score * 0.50 +         # Acronym/identifier match (primary)
            local_score * 0.30 +           # Local number match
            token_overlap * 0.10 +         # General token overlap
            phonetic_score * 0.10          # Phonetic similarity
        )
        # Bonus if both local and identity match
        if local_match:
            overall_score = min(overall_score + 0.15, 1.0)
    elif identity_score >= 0.5:
        # Good identity match through direct identifier overlap
        overall_score = (
            identity_score * 0.45 +       # Acronym/identifier match (primary)
            local_score * 0.30 +          # Local number match
            token_overlap * 0.15 +        # General token overlap
            phonetic_score * 0.10         # Phonetic similarity
        )
        # Bonus if both local and identity match
        if local_match:
            overall_score = min(overall_score + 0.10, 1.0)
    elif local_match and identity_score > 0:
        # Weak identity match with local - still give decent score if acronym matched
        if acronym_match:
            overall_score = (
                identity_score * 0.45 +
                local_score * 0.35 +
                token_overlap * 0.15 +
                phonetic_score * 0.05
            )
        else:
            overall_score = (
                identity_score * 0.40 +
                local_score * 0.20 +          # Reduce local weight when identity weak
                token_overlap * 0.25 +
                phonetic_score * 0.15
            )
    else:
        # No identity match - local number alone not enough
        overall_score = (
            local_score * 0.15 +          # Local alone gives minimal score
            token_overlap * 0.50 +        # Rely more on token overlap
            phonetic_score * 0.35
        )

    return {
        'overall_score': round(overall_score, 3),
        'identifier_score': round(identifier_overlap, 3),
        'acronym_match': acronym_match,
        'local_match': local_match,
        'token_overlap': round(token_overlap, 3),
        'details': {
            'name1_identifiers': tokens1['identifiers'],
            'name2_identifiers': tokens2['identifiers'],
            'name1_acronyms': tokens1['acronyms'],
            'name2_acronyms': tokens2['acronyms'],
            'name1_local': tokens1['local_number'],
            'name2_local': tokens2['local_number'],
            'common_tokens': tokens1['all_tokens'] & tokens2['all_tokens'],
        }
    }


def find_best_union_match(target: str, candidates: List[Tuple[str, any]],
                          threshold: float = 0.5) -> Optional[Tuple[any, str, float]]:
    """
    Find the best matching union from a list of candidates using order-independent matching.

    Args:
        target: Union name to match
        candidates: List of (union_name, identifier) tuples
        threshold: Minimum score to consider a match

    Returns:
        Tuple of (identifier, matched_name, score) or None if no match
    """
    best_match = None
    best_score = 0.0
    best_name = None

    for candidate_name, identifier in candidates:
        result = union_token_match_score(target, candidate_name)
        if result['overall_score'] > best_score and result['overall_score'] >= threshold:
            best_score = result['overall_score']
            best_match = identifier
            best_name = candidate_name

    if best_match:
        return (best_match, best_name, best_score)
    return None


def compare_union_names(name1: str, name2: str) -> dict:
    """
    Comprehensive comparison of two union names using multiple methods.

    Combines token matching, phonetic matching, and traditional similarity.

    Args:
        name1: First union name
        name2: Second union name

    Returns:
        Dictionary with all comparison metrics and recommendation
    """
    # Token-based matching (order-independent)
    token_result = union_token_match_score(name1, name2)

    # Phonetic matching
    phonetic_result = phonetic_match_score(name1, name2)

    # Traditional token similarity
    trad_sim = token_similarity(name1, name2)

    # Combine scores
    combined_score = (
        token_result['overall_score'] * 0.50 +
        phonetic_result['overall_score'] * 0.25 +
        trad_sim * 0.25
    )

    # Determine confidence level
    if combined_score >= 0.8:
        confidence = 'HIGH'
    elif combined_score >= 0.6:
        confidence = 'MEDIUM'
    elif combined_score >= 0.4:
        confidence = 'LOW'
    else:
        confidence = 'NO_MATCH'

    return {
        'combined_score': round(combined_score, 3),
        'confidence': confidence,
        'token_score': token_result['overall_score'],
        'phonetic_score': phonetic_result['overall_score'],
        'traditional_sim': round(trad_sim, 3),
        'local_match': token_result['local_match'],
        'acronym_match': token_result['acronym_match'],
        'recommendation': 'MATCH' if combined_score >= 0.5 else 'NO_MATCH'
    }

# ============================================================================
# EMPLOYER NAME NORMALIZATION
# ============================================================================

# Legal suffixes to strip (order matters - longer first)
LEGAL_SUFFIXES = [
    # Corporations
    r'\bincorporated\b',
    r'\bcorporation\b',
    r'\bcompany\b',
    r'\blimited\b',
    r'\bcorp\b\.?',
    r'\binc\b\.?',
    r'\bco\b\.?',
    r'\bltd\b\.?',
    r'\bllc\b\.?',
    r'\bllp\b\.?',
    r'\blp\b\.?',
    r'\bplc\b\.?',
    r'\bpc\b\.?',
    r'\bpa\b\.?',  # Professional Association
    r'\bpllc\b\.?',
    # Other common suffixes
    r'\bd/?b/?a\b\.?',  # DBA
    r'\baka\b\.?',  # AKA
    r'\bn/?a\b\.?',  # N/A, NA
]

# Common employer abbreviations to expand
EMPLOYER_ABBREVIATIONS = {
    # Healthcare
    'hosp': 'hospital',
    'hosptl': 'hospital',
    'hosptal': 'hospital',
    'med': 'medical',
    'medcl': 'medical',
    'ctr': 'center',
    'cntr': 'center',
    'hlth': 'health',
    'hc': 'healthcare',
    'hlthcare': 'healthcare',
    'rehab': 'rehabilitation',
    'rehabil': 'rehabilitation',
    'nurs': 'nursing',
    'surg': 'surgical',
    'surgcl': 'surgical',
    'pharm': 'pharmacy',
    'pharma': 'pharmaceutical',
    'clin': 'clinic',
    'clinc': 'clinic',
    'diag': 'diagnostic',
    'diagnstic': 'diagnostic',
    'ortho': 'orthopedic',
    'peds': 'pediatric',
    'psych': 'psychiatric',
    # General business
    'cntry': 'country',
    'svcs': 'services',
    'svc': 'service',
    'serv': 'service',
    'servs': 'services',
    'mgmt': 'management',
    'mgt': 'management',
    'mngmt': 'management',
    'grp': 'group',
    'intl': 'international',
    "int'l": 'international',
    'internatl': 'international',
    'natl': 'national',
    "nat'l": 'national',
    'natnl': 'national',
    'govt': 'government',
    'gov': 'government',
    'dept': 'department',
    'div': 'division',
    'divn': 'division',
    'mfg': 'manufacturing',
    'manuf': 'manufacturing',
    'manufact': 'manufacturing',
    'dist': 'distribution',
    'distrib': 'distribution',
    'distr': 'distribution',
    'assoc': 'associates',
    'assocs': 'associates',
    'assn': 'association',
    'amer': 'american',
    'amern': 'american',
    'univ': 'university',
    'univrsty': 'university',
    'comm': 'community',
    'commun': 'community',
    'sys': 'system',
    'syst': 'system',
    'systm': 'system',
    'tech': 'technology',
    'technol': 'technology',
    'techn': 'technology',
    'ind': 'industries',
    'indus': 'industries',
    'industr': 'industries',
    'constr': 'construction',
    'const': 'construction',
    'constru': 'construction',
    'elec': 'electric',
    'electr': 'electric',
    'equip': 'equipment',
    'equipmt': 'equipment',
    'transp': 'transportation',
    'trans': 'transportation',
    'transpo': 'transportation',
    'pkg': 'packaging',
    'pkging': 'packaging',
    'proc': 'processing',
    'prods': 'products',
    'prod': 'products',
    'prop': 'properties',
    'props': 'properties',
    'ent': 'enterprises',
    'enterp': 'enterprises',
    'fdn': 'foundation',
    'found': 'foundation',
    'foundn': 'foundation',
    'auth': 'authority',
    # Hospitality
    'htl': 'hotel',
    'rst': 'restaurant',
    'restrnt': 'restaurant',
    'resturant': 'restaurant',
    'hosp': 'hospitality',
    # Retail/Commercial
    'whse': 'warehouse',
    'wrhs': 'warehouse',
    'wrhse': 'warehouse',
    'whsle': 'wholesale',
    'rtl': 'retail',
    'str': 'store',
    'strs': 'stores',
    'mkt': 'market',
    'mkts': 'markets',
    'supermkt': 'supermarket',
    'supmkt': 'supermarket',
    'groc': 'grocery',
    # Geographic
    'mt': 'mount',
    'mtn': 'mountain',
    'st': 'saint',
    'ft': 'fort',
    'pt': 'point',
    'n': 'north',
    'e': 'east',
    's': 'south',
    'w': 'west',
    'ne': 'northeast',
    'nw': 'northwest',
    'se': 'southeast',
    'sw': 'southwest',
    # Other common
    'admin': 'administration',
    'admn': 'administration',
    'ops': 'operations',
    'oper': 'operations',
    'hq': 'headquarters',
    'hdqtrs': 'headquarters',
    'corp': 'corporate',
    'reg': 'regional',
    'regl': 'regional',
    'res': 'resources',
    'rsrc': 'resources',
    'hr': 'human resources',
    'fin': 'financial',
    'financl': 'financial',
    'ins': 'insurance',
    'insur': 'insurance',
    'acct': 'accounting',
    'accting': 'accounting',
    'consult': 'consulting',
    'consltg': 'consulting',
    'solns': 'solutions',
    'soln': 'solution',
}

# Common employer name variations for matching
EMPLOYER_NAME_VARIATIONS = {
    'saint': ['st', 'st.', 'saint'],
    'mount': ['mt', 'mt.', 'mount'],
    'fort': ['ft', 'ft.', 'fort'],
    'and': ['&', 'and', '+'],
    'company': ['co', 'co.', 'company'],
    'brothers': ['bros', 'bros.', 'brothers'],
    'manufacturing': ['mfg', 'mfg.', 'manufacturing', 'manuf'],
    'hospital': ['hosp', 'hosp.', 'hospital', 'hosptl'],
    'medical': ['med', 'med.', 'medical', 'medcl'],
    'center': ['ctr', 'ctr.', 'center', 'cntr', 'centre'],
    'services': ['svcs', 'svc', 'services', 'servs'],
    'healthcare': ['hc', 'healthcare', 'health care'],
    'international': ['intl', "int'l", 'international', 'internatl'],
    'national': ['natl', "nat'l", 'national', 'natnl'],
    'university': ['univ', 'univ.', 'university'],
    'community': ['comm', 'community', 'commun'],
}

# Words to remove (articles, etc.)
STOPWORDS = {'the', 'a', 'an', 'of', 'and', '&'}


def normalize_employer(name: str, expand_abbrevs: bool = True, remove_stopwords: bool = False) -> str:
    """
    Normalize employer name for matching.
    
    Steps:
    1. Lowercase
    2. Remove punctuation (keep alphanumeric and spaces)
    3. Strip legal suffixes (Inc, LLC, Corp, etc.)
    4. Optionally expand abbreviations
    5. Optionally remove stopwords
    6. Collapse whitespace
    
    Args:
        name: Raw employer name
        expand_abbrevs: Whether to expand common abbreviations
        remove_stopwords: Whether to remove articles (the, a, an, of)
    
    Returns:
        Normalized name string
    """
    if not name:
        return ""
    
    # Lowercase
    result = name.lower().strip()
    
    # Remove punctuation except hyphens and apostrophes initially
    result = re.sub(r"[^\w\s\-']", " ", result)
    
    # Strip legal suffixes
    for suffix in LEGAL_SUFFIXES:
        result = re.sub(suffix, '', result, flags=re.IGNORECASE)
    
    # Remove apostrophes now
    result = result.replace("'", "")
    
    # Expand abbreviations
    if expand_abbrevs:
        words = result.split()
        words = [EMPLOYER_ABBREVIATIONS.get(w, w) for w in words]
        result = " ".join(words)
    
    # Remove stopwords
    if remove_stopwords:
        words = result.split()
        words = [w for w in words if w not in STOPWORDS]
        result = " ".join(words)
    
    # Collapse multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()
    
    return result


# ============================================================================
# UNION NAME NORMALIZATION
# ============================================================================

# Union-specific abbreviations
UNION_ABBREVIATIONS = {
    # Common union words
    'intl': 'international',
    "int'l": 'international',
    'internatl': 'international',
    'intrnl': 'international',
    'internatnl': 'international',
    'internat': 'international',
    'intnl': 'international',
    'natl': 'national',
    "nat'l": 'national',
    'natnl': 'national',
    'assn': 'association',
    'assoc': 'association',
    'assocn': 'association',
    'asstn': 'association',
    'bro': 'brotherhood',
    'brthrhd': 'brotherhood',
    'brhd': 'brotherhood',
    'brotherhd': 'brotherhood',
    'brothrhd': 'brotherhood',
    'wkrs': 'workers',
    'wrkrs': 'workers',
    'wkr': 'worker',
    'wrk': 'worker',
    'wrkr': 'worker',
    'empl': 'employees',
    'emp': 'employees',
    'empls': 'employees',
    'emplys': 'employees',
    'emplyees': 'employees',
    'employes': 'employees',  # Common typo
    'loc': 'local',
    'dist': 'district',
    'cncl': 'council',
    'coun': 'council',
    'cncil': 'council',
    'councl': 'council',
    'fed': 'federation',
    'fedn': 'federation',
    'org': 'organization',
    'orgn': 'organization',
    'comm': 'committee',
    'cmte': 'committee',
    'div': 'division',
    'dept': 'department',
    'govt': 'government',
    'serv': 'service',
    'svcs': 'services',
    'svc': 'service',
    'indus': 'industrial',
    'ind': 'industrial',
    'tech': 'technical',
    'prof': 'professional',
    'profnl': 'professional',
    'oper': 'operating',
    'engrs': 'engineers',
    'engr': 'engineers',
    'elec': 'electrical',
    'elect': 'electrical',
    'mech': 'mechanical',
    'plmbrs': 'plumbers',
    'plmrs': 'plumbers',
    'carps': 'carpenters',
    'carp': 'carpenters',
    'carpntrs': 'carpenters',
    'lbrs': 'laborers',
    'labrs': 'laborers',
    'laborrs': 'laborers',
    'teamstrs': 'teamsters',
    'amer': 'american',
    'am': 'american',
    'u': 'union',
    'un': 'union',
    'unin': 'union',
    'unn': 'union',
    # Trade-specific abbreviations
    'pipeftrs': 'pipefitters',
    'pipfttrs': 'pipefitters',
    'stmftrs': 'steamfitters',
    'steamftrs': 'steamfitters',
    'ironwkrs': 'ironworkers',
    'ironwrkrs': 'ironworkers',
    'sheetmtl': 'sheetmetal',
    'shtmtl': 'sheetmetal',
    'boilermkrs': 'boilermakers',
    'boilermkr': 'boilermakers',
    'millwrts': 'millwrights',
    'millwrght': 'millwrights',
    'insulatrs': 'insulators',
    'bricklayrs': 'bricklayers',
    'bricklyr': 'bricklayers',
    'plastrs': 'plasterers',
    'glazrs': 'glaziers',
    'roofers': 'roofers',
    'drywall': 'drywall',
    # Healthcare
    'healthcr': 'healthcare',
    'hlthcre': 'healthcare',
    'hlthcare': 'healthcare',
    'nurs': 'nurses',
    'nurss': 'nurses',
    'hosp': 'hospital',
    # Transportation
    'transp': 'transportation',
    'transpn': 'transportation',
    'transpo': 'transportation',
    'drivrs': 'drivers',
    'drvrs': 'drivers',
    # Common union acronyms - DON'T expand (they're identifiers)
    # 'seiu', 'ufcw', 'uaw', 'ibt', 'ibew', etc. - keep as-is
}

# Affiliation code mappings (VR extraction -> OLMS aff_abbr variants)
AFFILIATION_MAPPINGS = {
    'UNITE HERE': ['UNITEHERE', 'HERE', 'UNITE-HERE', 'HEREIU', 'UNITE', 'HRE'],
    'IUPAT': ['IUPAT', 'PAT', 'PAINTERS', 'PDC', 'IBPAT'],
    'SMART': ['SMART', 'SMWIA', 'SMW', 'UTU', 'SMART-UTU'],
    'IAM': ['IAM', 'IAMAW', 'MACHINISTS', 'IAM&AW'],
    'USW': ['USW', 'USWA', 'STEELWORKERS', 'UNITED STEELWORKERS'],
    'CWA': ['CWA', 'TNG', 'CWA-TNG', 'TNG-CWA'],
    'RWDSU': ['RWDSU', 'RWDSU-UFCW', 'RWDSU/UFCW'],
    'AFSCME': ['AFSCME', 'AFSCME-AFL-CIO'],
    'SEIU': ['SEIU', 'SEIU-UHW', 'SEIU-USWW', 'UHW', 'USWW'],
    'UFCW': ['UFCW', 'RWDSU-UFCW', 'UFCW-RWDSU'],
    'IBEW': ['IBEW', 'NECA-IBEW'],
    'LIUNA': ['LIUNA', 'LABORERS', 'LABORER', 'LIUNAOPDC'],
    'IBT': ['IBT', 'TEAMSTERS', 'TEAMSTER'],
    'UAW': ['UAW', 'UAAW', 'AUTOWORKERS', 'AUTO WORKERS'],
    'OPEIU': ['OPEIU', 'OPEU'],
    'AFGE': ['AFGE', 'AFGE-AFL-CIO'],
    'NTEU': ['NTEU'],
    'NFFE': ['NFFE', 'NFFE-IAM'],
    'IAFF': ['IAFF', 'FIREFIGHTERS', 'FIRE FIGHTERS'],
    'FOP': ['FOP', 'FRATERNAL ORDER'],
    'BCTGM': ['BCTGM', 'BAKERY', 'BCT'],
    'UBC': ['UBC', 'CARPENTERS', 'CARPENTER', 'UBCJA'],
    'UA': ['UA', 'PLUMBERS', 'PLUMBER', 'PIPEFITTERS', 'PPF'],
    'IUOE': ['IUOE', 'OPERATING ENGINEERS', 'OE'],
    'ATU': ['ATU', 'TRANSIT', 'AMALGAMATED TRANSIT'],
    'TWU': ['TWU', 'TRANSPORT WORKERS'],
    'AFA': ['AFA', 'AFA-CWA', 'FLIGHT ATTENDANTS'],
    'ALPA': ['ALPA', 'AIRLINE PILOTS', 'AIR LINE PILOTS'],
    'NNU': ['NNU', 'NATIONAL NURSES', 'NURSES UNITED'],
    'AFT': ['AFT', 'TEACHERS', 'FEDERATION OF TEACHERS'],
    'NEA': ['NEA', 'EDUCATION ASSOCIATION'],
    'APWU': ['APWU', 'POSTAL WORKERS'],
    'NALC': ['NALC', 'LETTER CARRIERS'],
    'NPMHU': ['NPMHU', 'MAIL HANDLERS'],
    'IW': ['IW', 'IRONWORKERS', 'IRON WORKERS'],
    'IBB': ['IBB', 'BOILERMAKERS', 'BOILERMAKER'],
}


def get_affiliation_variants(affil_code: str) -> list:
    """Get all known variants for an affiliation code."""
    if not affil_code:
        return []
    affil_upper = affil_code.upper().strip()
    # Check if it's a key
    if affil_upper in AFFILIATION_MAPPINGS:
        return AFFILIATION_MAPPINGS[affil_upper]
    # Check if it's a value in any mapping
    for key, variants in AFFILIATION_MAPPINGS.items():
        if affil_upper in [v.upper() for v in variants]:
            return variants
    return [affil_upper]


def get_union_name_equivalents(name: str) -> list:
    """
    Get equivalent union name variations for matching.

    Args:
        name: Union name to look up

    Returns:
        List of equivalent names/patterns
    """
    if not name:
        return []

    name_lower = name.lower().strip()
    equivalents = [name_lower]

    # Check if name matches any known equivalents
    for canonical, variations in UNION_NAME_EQUIVALENTS.items():
        if name_lower == canonical or name_lower in variations:
            equivalents.extend([canonical] + variations)
            break
        # Also check if any variation is contained in the name
        for var in [canonical] + variations:
            if var in name_lower or name_lower in var:
                equivalents.extend([canonical] + variations)
                break

    return list(set(equivalents))


def correct_union_name(name: str) -> str:
    """
    Apply all corrections to a union name: typos, abbreviations, etc.

    Args:
        name: Raw union name

    Returns:
        Corrected and normalized name
    """
    if not name:
        return ""

    result = name.lower().strip()

    # Apply typo corrections at word level
    words = re.findall(r"[\w']+", result)
    corrected_words = []
    for w in words:
        # Check typo corrections
        if w in UNION_TYPO_CORRECTIONS:
            corrected_words.append(UNION_TYPO_CORRECTIONS[w])
        # Check abbreviation expansions
        elif w in UNION_ABBREVIATIONS:
            corrected_words.append(UNION_ABBREVIATIONS[w])
        else:
            corrected_words.append(w)

    return ' '.join(corrected_words)

# Common typos and misspellings -> correct spelling
UNION_TYPO_CORRECTIONS = {
    # Misspellings
    'assocation': 'association',
    'asociation': 'association',
    'assocaition': 'association',
    'associaton': 'association',
    'asssociation': 'association',
    'committe': 'committee',
    'commitee': 'committee',
    'comittee': 'committee',
    'commttee': 'committee',
    'brotherhod': 'brotherhood',
    'broderhood': 'brotherhood',
    'brotherood': 'brotherhood',
    'bortherhood': 'brotherhood',
    'internation': 'international',
    'interational': 'international',
    'internationl': 'international',
    'inernational': 'international',
    'internatinal': 'international',
    'employes': 'employees',
    'employess': 'employees',
    'emplyees': 'employees',
    'employeees': 'employees',
    'emploees': 'employees',
    'emplyes': 'employees',
    'teamster': 'teamsters',
    'temsters': 'teamsters',
    'teamsters\'': 'teamsters',
    'teemsters': 'teamsters',
    'machinist': 'machinists',
    'machinest': 'machinists',
    'machinsts': 'machinists',
    'laborer': 'laborers',
    'laborers\'': 'laborers',
    'laboers': 'laborers',
    'labourers': 'laborers',
    'worker': 'workers',
    'workers\'': 'workers',
    'wrokers': 'workers',
    'workrs': 'workers',
    'plumber': 'plumbers',
    'plummers': 'plumbers',
    'plubmers': 'plumbers',
    'carpenter': 'carpenters',
    'carpentars': 'carpenters',
    'carpentar': 'carpenters',
    'electircal': 'electrical',
    'electricl': 'electrical',
    'eletricians': 'electricians',
    'electricans': 'electricians',
    'enginner': 'engineer',
    'enginer': 'engineer',
    'enginners': 'engineers',
    'enginers': 'engineers',
    'comunication': 'communication',
    'communiction': 'communication',
    'communicaton': 'communication',
    'profesional': 'professional',
    'proffesional': 'professional',
    'professinal': 'professional',
    'hosptial': 'hospital',
    'hospitl': 'hospital',
    'hopital': 'hospital',
    'hostpital': 'hospital',
    'healtcare': 'healthcare',
    'healthare': 'healthcare',
    'hlthcare': 'healthcare',
    'disrict': 'district',
    'distirct': 'district',
    'distrct': 'district',
    'counicl': 'council',
    'concil': 'council',
    'counsil': 'council',
    'coucil': 'council',
    'federacion': 'federation',  # Spanish
    'federtion': 'federation',
    'fedration': 'federation',
    'servcies': 'services',
    'servies': 'services',
    'serivces': 'services',
    'warehose': 'warehouse',
    'warhouse': 'warehouse',
    'warehosue': 'warehouse',
    'manufacuring': 'manufacturing',
    'manufactring': 'manufacturing',
    'manufacting': 'manufacturing',
    'transportaion': 'transportation',
    'transporation': 'transportation',
    'trasportation': 'transportation',
    'maintainance': 'maintenance',
    'maintenace': 'maintenance',
    'maintanence': 'maintenance',
    'goverment': 'government',
    'govenment': 'government',
    'governmet': 'government',
    'secuirty': 'security',
    'securtiy': 'security',
    'sercurity': 'security',
    # Singular/plural normalization
    'employee': 'employees',
    'service': 'services',
    'communication': 'communications',
    'professional': 'professionals',
    'machinist': 'machinists',
    'teamster': 'teamsters',
    'laborer': 'laborers',
    'plumber': 'plumbers',
    'carpenter': 'carpenters',
    'painter': 'painters',
    'roofer': 'roofers',
    'electrician': 'electricians',
    'ironworker': 'ironworkers',
    'steelworker': 'steelworkers',
    'firefighter': 'firefighters',
    'boilermaker': 'boilermakers',
}

# Common name variations that should be treated as equivalent
UNION_NAME_EQUIVALENTS = {
    # UNITE HERE variations
    'unite here': ['unitehere', 'unite-here', 'unite here!', 'here', 'hotel employees restaurant employees'],
    # Teamsters
    'teamsters': ['ibt', 'international brotherhood of teamsters', 'chauffeurs warehousemen'],
    # SEIU
    'seiu': ['service employees international union', 'service employees'],
    # UFCW
    'ufcw': ['united food and commercial workers', 'united food commercial workers', 'food and commercial workers'],
    # CWA
    'cwa': ['communications workers of america', 'communications workers'],
    # UAW
    'uaw': ['united auto workers', 'united automobile workers', 'auto workers'],
    # USW
    'usw': ['united steelworkers', 'steelworkers', 'united steel workers'],
    # IBEW
    'ibew': ['international brotherhood of electrical workers', 'electrical workers'],
    # IAM
    'iam': ['machinists', 'international association of machinists', 'machinists and aerospace workers'],
    # LIUNA
    'liuna': ['laborers international', 'laborers union'],
    # AFSCME
    'afscme': ['american federation of state county municipal', 'state county municipal employees'],
}

# Union identifiers to preserve (don't alter these)
UNION_ACRONYMS = {
    'seiu', 'ufcw', 'uaw', 'ibt', 'ibew', 'iatse', 'afscme', 'aft', 'nea',
    'cwa', 'usw', 'unite', 'here', 'liuna', 'smart', 'iuoe', 'bctgm',
    'rwdsu', 'opeiu', 'apwu', 'nalc', 'npmhu', 'nrlca', 'iaff', 'afge',
    'nteu', 'nffe', 'ifpte', 'iaff', 'iam', 'iamaw', 'uwua', 'umwa',
    'gmp', 'smwia', 'ibfo', 'wga', 'sag', 'aftra', 'sagaftra', 'dga',
    'aia', 'bac', 'iupat', 'atda', 'bmwe', 'brs', 'tcrc', 'twu'
}


def normalize_union(name: str, expand_abbrevs: bool = True, fix_typos: bool = True) -> str:
    """
    Normalize union name for matching.

    Steps:
    1. Lowercase
    2. Remove punctuation
    3. Fix common typos/misspellings
    4. Expand union-specific abbreviations (but preserve acronyms like SEIU)
    5. Handle local numbers (normalize format)
    6. Collapse whitespace

    Args:
        name: Raw union name
        expand_abbrevs: Whether to expand abbreviations
        fix_typos: Whether to fix common typos

    Returns:
        Normalized name string
    """
    if not name:
        return ""

    # Lowercase
    result = name.lower().strip()

    # Normalize apostrophes in abbreviations before removing
    result = result.replace("int'l", "intl").replace("nat'l", "natl")

    # Remove punctuation except hyphens
    result = re.sub(r"[^\w\s\-]", " ", result)

    # Split into words for processing
    words = result.split()
    new_words = []

    for w in words:
        # Fix typos first
        if fix_typos and w in UNION_TYPO_CORRECTIONS:
            w = UNION_TYPO_CORRECTIONS[w]

        # Expand abbreviations (but not union acronyms)
        if expand_abbrevs:
            if w in UNION_ACRONYMS:
                new_words.append(w)  # Keep acronym as-is
            else:
                new_words.append(UNION_ABBREVIATIONS.get(w, w))
        else:
            new_words.append(w)

    result = " ".join(new_words)

    # Normalize "local XXX" patterns
    result = re.sub(r'\blocal\s*#?\s*(\d+)', r'local \1', result)

    # Normalize "district XXX" patterns
    result = re.sub(r'\bdistrict\s*#?\s*(\d+)', r'district \1', result)

    # Collapse multiple spaces
    result = re.sub(r'\s+', ' ', result).strip()

    return result


# ============================================================================
# COMPARISON HELPER
# ============================================================================

def normalize_for_comparison(name: str, entity_type: str = 'employer') -> str:
    """
    Aggressive normalization for comparison purposes.
    Removes stopwords and expands all abbreviations.
    
    Args:
        name: Raw name
        entity_type: 'employer' or 'union'
    
    Returns:
        Aggressively normalized string for comparison
    """
    if entity_type == 'union':
        return normalize_union(name, expand_abbrevs=True)
    else:
        return normalize_employer(name, expand_abbrevs=True, remove_stopwords=True)


def extract_local_number(union_name: str) -> Optional[str]:
    """
    Extract local union number from name with enhanced pattern matching.

    Examples:
        "SEIU Local 1000" -> "1000"
        "Teamsters 705" -> "705"
        "UFCW Local #400" -> "400"
        "Local 1-A" -> "1-A"
        "District Council 37" -> "37"
        "AFSCME Council 4" -> "4"
        "Lodge 123" -> "123"
        "Region 8" -> "8"

    Returns:
        Local number as string, or None if not found
    """
    if not union_name:
        return None

    # First, clean up the input - remove address info that could be confused
    # Split by newlines and only keep lines that look like union names
    clean_name = union_name

    # If there are newlines, filter out address-like lines
    if '\n' in clean_name:
        lines = clean_name.split('\n')
        good_lines = []
        for line in lines:
            line = line.strip()
            # Skip lines that look like addresses or contact info
            if re.search(r'^\d+\s+\w', line):  # Starts with street number
                continue
            if re.search(r'\b[A-Z]{2}\s+\d{5}', line):  # City, ST ZIP
                continue
            if re.search(r'\(\d{3}\)', line):  # Phone number
                continue
            if re.search(r'@|\.com|\.org|\.net', line, re.IGNORECASE):  # Email/web
                continue
            if re.search(r'^(attn|attention|c/o|organizer|representative):', line, re.IGNORECASE):
                continue
            if re.search(r'^\w+\s+\w+,\s*(esq|organizer|representative)', line, re.IGNORECASE):
                continue
            if line:
                good_lines.append(line)
        clean_name = ' '.join(good_lines)

    # Remove remaining address patterns
    address_patterns = [
        r'\d+\s+(?:street|st\.?|avenue|ave\.?|road|rd\.?|drive|dr\.?|boulevard|blvd\.?|lane|ln\.?|way|place|pl\.?|floor|suite|ste\.?)\b.*',
        r'\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b.*',  # State + ZIP
        r'\(\d{3}\)\s*\d{3}[-.]\d{4}',  # Phone numbers (xxx) xxx-xxxx
        r'\d{3}[-.]\s*\d{3}[-.]\s*\d{4}',  # Phone numbers xxx-xxx-xxxx (with optional spaces)
        r'tel\.?:?\s*\d',  # Tel: xxx
        r'phone:?\s*\d',  # Phone: xxx
        r'fax:?\s*\d.*',  # Fax: xxx
        r'ext\.?\s*\d+',
        r'office:?\s*\d',  # Office: xxx
    ]
    for addr_pattern in address_patterns:
        clean_name = re.sub(addr_pattern, '', clean_name, flags=re.IGNORECASE)

    # Try patterns in order of specificity
    patterns = [
        # Primary: "Local 123", "Local #123", "Local No. 123", "Local No 123", "Local 1-A"
        r'\blocal\s*(?:no\.?|#|number)?\s*(\d+(?:[-/][a-zA-Z0-9]+)?)',

        # District Council patterns (with or without "No.")
        r'\bdistrict\s+council\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # District patterns (without Council) - for CWA District 7, etc.
        r'\bdistrict\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Joint Council/Board patterns
        r'\bjoint\s*(?:council|board)\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Council patterns (AFSCME Council 4, Council 31) - must have number immediately after
        r'\bcouncil\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Lodge patterns (for IAM, BLE, etc.) - "Local Lodge 447", "District Lodge 15"
        r'\b(?:local\s+)?lodge\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Division patterns (for transit unions)
        r'\bdivision\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Branch patterns (for postal unions)
        r'\bbranch\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Chapter patterns
        r'\bchapter\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Unit patterns (but not "United")
        r'\bunit\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Region patterns
        r'\bregion\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Area patterns
        r'\barea\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Assembly patterns
        r'\bassembly\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Section patterns
        r'\bsection\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # General Committee patterns (railroads)
        r'\bgeneral\s+committee\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # System Board patterns (railroads)
        r'\bsystem\s+(?:board|council)\s*(?:no\.?|#)?\s*(\d+[a-zA-Z]?)\b',

        # Trailing number with known union name (e.g., "Teamsters 705", "SEIU 1199")
        r'(?:teamsters?|seiu|ufcw|ibew|liuna|iuoe|afscme|cwa|usw|uaw|iam|unite\s*here?)\s+(\d{2,5}[a-zA-Z]?)\b',

        # Hash number anywhere
        r'#\s*(\d+[a-zA-Z]?)\b',

        # Generic trailing number as last resort (2-5 digits at end of cleaned name)
        # But avoid ZIP codes (5 digits)
        r'\b(\d{2,4})\s*$',
    ]

    for pattern in patterns:
        match = re.search(pattern, clean_name, re.IGNORECASE)
        if match:
            num = match.group(1)
            # Validate: skip if it looks like a ZIP code (exactly 5 digits)
            if len(num) == 5 and num.isdigit():
                continue
            return num

    return None


def normalize_local_number(local_num: str) -> str:
    """
    Normalize local number for comparison.

    Examples:
        "001" -> "1"
        "1-A" -> "1A"
        "123/456" -> "123456"

    Returns:
        Normalized local number string
    """
    if not local_num:
        return ""
    # Remove leading zeros
    result = local_num.lstrip('0') or '0'
    # Remove hyphens/slashes for comparison
    result = re.sub(r'[-/\s]', '', result)
    return result.upper()


def token_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity based on shared tokens, ignoring word order.
    Handles name reordering cases.

    Args:
        name1: First union name
        name2: Second union name

    Returns:
        Jaccard similarity score (0.0 to 1.0)
    """
    # Normalize both names
    tokens1 = set(normalize_union(name1).split())
    tokens2 = set(normalize_union(name2).split())

    # Remove common stopwords for comparison
    stopwords = {'of', 'the', 'and', 'for', 'local', 'a', 'an'}
    tokens1 = tokens1 - stopwords
    tokens2 = tokens2 - stopwords

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard similarity
    intersection = tokens1 & tokens2
    union_set = tokens1 | tokens2

    return len(intersection) / len(union_set)


def extract_key_tokens(union_name: str) -> set:
    """
    Extract identifying tokens from union name.
    Useful for matching reordered names.

    Args:
        union_name: Raw or normalized union name

    Returns:
        Set of key identifying tokens
    """
    normalized = normalize_union(union_name)
    tokens = set(normalized.split())

    # Common words to exclude (not identifying)
    exclude = {
        'local', 'union', 'workers', 'employees', 'of', 'the', 'and',
        'for', 'a', 'an', 'council', 'district', 'international',
        'national', 'american', 'united'
    }

    # Keep acronyms and significant words
    key_tokens = set()
    for token in tokens:
        if token in UNION_ACRONYMS:
            key_tokens.add(token)
        elif len(token) > 3 and token not in exclude:
            key_tokens.add(token)

    return key_tokens


def employer_token_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity between employer names based on shared tokens.
    Handles name variations and word order differences.
    """
    # Normalize both names
    tokens1 = set(normalize_employer(name1, expand_abbrevs=True, remove_stopwords=True).split())
    tokens2 = set(normalize_employer(name2, expand_abbrevs=True, remove_stopwords=True).split())

    # Remove very common words that don't help differentiate
    common_words = {'the', 'a', 'an', 'of', 'and', 'for', 'in', 'at', 'by'}
    tokens1 = tokens1 - common_words
    tokens2 = tokens2 - common_words

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard similarity
    intersection = tokens1 & tokens2
    union_set = tokens1 | tokens2

    return len(intersection) / len(union_set)


def extract_employer_key_words(name: str) -> set:
    """
    Extract key identifying words from employer name.
    Useful for blocking/candidate selection.
    """
    normalized = normalize_employer(name, expand_abbrevs=True, remove_stopwords=True)
    tokens = set(normalized.split())

    # Words that don't help identify (too common)
    exclude = {
        'the', 'a', 'an', 'of', 'and', 'for', 'in', 'at', 'by',
        'group', 'services', 'service', 'company', 'corporation',
        'enterprises', 'industries', 'holdings', 'partners', 'solutions'
    }

    # Keep substantive words
    key_words = set()
    for token in tokens:
        if len(token) >= 3 and token not in exclude:
            key_words.add(token)

    return key_words


def compute_employer_match_score(vr_name: str, f7_name: str, vr_city: str = None,
                                  f7_city: str = None, vr_state: str = None,
                                  f7_state: str = None) -> float:
    """
    Compute comprehensive match score between VR and F7 employer names.
    """
    score = 0.0

    # Token similarity (0.0 - 0.5)
    token_sim = employer_token_similarity(vr_name, f7_name)
    score += token_sim * 0.5

    # Key word overlap (0.0 - 0.25)
    vr_keys = extract_employer_key_words(vr_name)
    f7_keys = extract_employer_key_words(f7_name)
    if vr_keys and f7_keys:
        key_overlap = len(vr_keys & f7_keys) / max(len(vr_keys), len(f7_keys))
        score += key_overlap * 0.25

    # Location match bonus (0.0 - 0.25)
    if vr_state and f7_state:
        if vr_state.upper() == f7_state.upper():
            score += 0.15
            if vr_city and f7_city:
                if vr_city.upper() == f7_city.upper():
                    score += 0.10
                elif vr_city.upper() in f7_city.upper() or f7_city.upper() in vr_city.upper():
                    score += 0.05

    return min(score, 1.0)


def normalize_employer_aggressive(name: str) -> str:
    """
    Aggressively normalize employer name for fuzzy matching.
    Removes all suffixes, expands all abbreviations, removes punctuation.
    """
    if not name:
        return ""

    result = name.lower().strip()

    # Normalize common variations first
    replacements = [
        (r"saint\b", "st"),
        (r"mount\b", "mt"),
        (r"fort\b", "ft"),
        (r"\s*&\s*", " and "),
        (r"\s*\+\s*", " and "),
        (r"'s\b", "s"),
        (r"n'", "n"),  # rock 'n' roll -> rock n roll
    ]
    for pattern, repl in replacements:
        result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

    # Remove all punctuation
    result = re.sub(r"[^\w\s]", " ", result)

    # Strip all legal suffixes
    for suffix in LEGAL_SUFFIXES:
        result = re.sub(suffix, '', result, flags=re.IGNORECASE)

    # Expand abbreviations
    words = result.split()
    words = [EMPLOYER_ABBREVIATIONS.get(w, w) for w in words]
    result = " ".join(words)

    # Remove stopwords
    words = result.split()
    words = [w for w in words if w not in STOPWORDS and len(w) > 1]
    result = " ".join(words)

    # Collapse whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def compute_match_score(vr_name: str, olms_name: str, vr_local: str = None, olms_local: str = None) -> float:
    """
    Compute a comprehensive match score between VR and OLMS union names.

    Args:
        vr_name: Normalized VR union name
        olms_name: OLMS union name
        vr_local: Extracted local number from VR (optional)
        olms_local: Local number from OLMS (optional)

    Returns:
        Match score from 0.0 to 1.0
    """
    score = 0.0

    # Token similarity (0.0 - 0.5)
    token_sim = token_similarity(vr_name, olms_name)
    score += token_sim * 0.5

    # Key token overlap bonus (0.0 - 0.3)
    vr_keys = extract_key_tokens(vr_name)
    olms_keys = extract_key_tokens(olms_name)
    if vr_keys and olms_keys:
        key_overlap = len(vr_keys & olms_keys) / max(len(vr_keys), len(olms_keys))
        score += key_overlap * 0.3

    # Local number match bonus (0.0 - 0.2)
    if vr_local and olms_local:
        vr_norm = normalize_local_number(vr_local)
        olms_norm = normalize_local_number(olms_local)
        if vr_norm == olms_norm:
            score += 0.2
        elif vr_norm.startswith(olms_norm) or olms_norm.startswith(vr_norm):
            score += 0.1  # Partial match

    return min(score, 1.0)


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    # Test employer normalization
    test_employers = [
        "The Kroger Company",
        "Kroger Co.",
        "KROGER, INC.",
        "Kroger",
        "Kaiser Permanente, LLC",
        "KAISER PERMANENTE",
        "Mercy Hosp. Med. Ctr.",
        "St. Mary's Hospital, Inc.",
    ]

    print("=" * 60)
    print("EMPLOYER NORMALIZATION TESTS")
    print("=" * 60)
    for emp in test_employers:
        normalized = normalize_employer(emp)
        comparison = normalize_for_comparison(emp, 'employer')
        print(f"  {emp}")
        print(f"    -> {normalized}")
        print(f"    -> {comparison} (comparison)")
        print()

    # Test union normalization
    test_unions = [
        "Service Employees Int'l Union Local 1000",
        "SEIU Local #1000",
        "International Brotherhood of Teamsters 705",
        "IBT Local 705",
        "United Food & Commercial Workers 400",
        "UFCW Loc. 400",
    ]

    print("=" * 60)
    print("UNION NORMALIZATION TESTS")
    print("=" * 60)
    for union in test_unions:
        normalized = normalize_union(union)
        local_num = extract_local_number(union)
        print(f"  {union}")
        print(f"    -> {normalized}")
        print(f"    -> Local #: {local_num}")
        print()

    # Test enhanced local number extraction
    print("=" * 60)
    print("LOCAL NUMBER EXTRACTION TESTS")
    print("=" * 60)
    test_local_nums = [
        "SEIU Local 1000",
        "Teamsters 705",
        "UFCW Local #400",
        "Local 1-A",
        "District Council 37",
        "Lodge 123",
        "Joint Council 7",
        "Branch 36",
        "AFSCME Local No. 3299",
        "Division 85",
        "Chapter 42",
        "IBEW 134",
        "Local 001",  # Should normalize to "1"
    ]
    for name in test_local_nums:
        local = extract_local_number(name)
        normalized = normalize_local_number(local) if local else None
        print(f"  {name:40} -> {local:10} (normalized: {normalized})")
    print()

    # Test token similarity
    print("=" * 60)
    print("TOKEN SIMILARITY TESTS")
    print("=" * 60)
    test_pairs = [
        ("International Brotherhood of Teamsters", "Teamsters International Brotherhood"),
        ("Service Employees International Union", "SEIU"),
        ("United Food and Commercial Workers", "UFCW International Union"),
        ("Laborers International Union", "LIUNA Local 79"),
        ("Nurses United", "National Nurses United"),
    ]
    for name1, name2 in test_pairs:
        sim = token_similarity(name1, name2)
        print(f"  {name1[:35]:35} vs {name2[:30]:30} -> {sim:.2f}")
    print()

    # Test affiliation variants
    print("=" * 60)
    print("AFFILIATION VARIANT TESTS")
    print("=" * 60)
    test_affils = ["UNITE HERE", "IUPAT", "SEIU", "IBT", "UNKNOWN"]
    for affil in test_affils:
        variants = get_affiliation_variants(affil)
        print(f"  {affil:15} -> {variants}")
    print()

    # Test compute_match_score
    print("=" * 60)
    print("MATCH SCORE TESTS")
    print("=" * 60)
    test_matches = [
        ("SEIU Local 1000", "Service Employees International Union Local 1000", "1000", "1000"),
        ("Teamsters 705", "International Brotherhood of Teamsters Local 705", "705", "705"),
        ("UFCW 400", "United Food Commercial Workers 400", "400", "400"),
        ("Laborers Local 79", "LIUNA Local 80", "79", "80"),
    ]
    for vr, olms, vr_local, olms_local in test_matches:
        score = compute_match_score(vr, olms, vr_local, olms_local)
        print(f"  VR: {vr[:30]:30} OLMS: {olms[:35]:35} -> {score:.2f}")
    print()

    # Test Soundex
    print("=" * 60)
    print("SOUNDEX TESTS")
    print("=" * 60)
    soundex_tests = [
        ("Robert", "Rupert"),
        ("Smith", "Smythe"),
        ("Johnson", "Jonson"),
        ("Teamsters", "Temsters"),
        ("Association", "Assocation"),
        ("Hospital", "Hosptial"),
        ("Manufacturing", "Manufacting"),
        ("Schmidt", "Smith"),
    ]
    for name1, name2 in soundex_tests:
        s1, s2 = soundex(name1), soundex(name2)
        match = "MATCH" if s1 == s2 else "differ"
        print(f"  {name1:20} [{s1}] vs {name2:20} [{s2}] -> {match}")
    print()

    # Test Metaphone
    print("=" * 60)
    print("METAPHONE TESTS")
    print("=" * 60)
    metaphone_tests = [
        ("Smith", "Smyth"),
        ("Phone", "Fone"),
        ("Knight", "Night"),
        ("Wright", "Right"),
        ("Teamsters", "Temsters"),
        ("Committee", "Committe"),
        ("Carpenters", "Carpentars"),
        ("Healthcare", "Healthcair"),
    ]
    for name1, name2 in metaphone_tests:
        m1, m2 = metaphone(name1), metaphone(name2)
        match = "MATCH" if m1 == m2 else "differ"
        print(f"  {name1:20} [{m1:10}] vs {name2:20} [{m2:10}] -> {match}")
    print()

    # Test phonetic_similarity
    print("=" * 60)
    print("PHONETIC SIMILARITY TESTS")
    print("=" * 60)
    phonetic_tests = [
        ("Smith Healthcare", "Smythe Health Care"),
        ("Johnson Manufacturing", "Jonson Manufacting"),
        ("American Hospital", "Amerikan Hosptial"),
        ("Teamsters Union", "Temsters Unoin"),
        ("Golden Age Care", "Golden Gate Care"),  # Should NOT match
        ("Compass Group", "Compass Equipment"),  # Partial match
        ("St Mary Hospital", "Saint Mary Hosptial"),
        ("Mt Vernon Healthcare", "Mount Vernon Health Care"),
    ]
    for name1, name2 in phonetic_tests:
        result = phonetic_match_score(name1, name2)
        print(f"  {name1[:25]:25} vs {name2[:25]:25}")
        print(f"    Overall: {result['overall_score']:.2f}, Soundex: {'Y' if result['soundex_match'] else 'N'}, Metaphone: {'Y' if result['metaphone_match'] else 'N'}")
    print()

    # Test find_phonetic_matches
    print("=" * 60)
    print("FIND PHONETIC MATCHES TEST")
    print("=" * 60)
    target = "Amerikan Hospittal"
    candidates = [
        "American Hospital",
        "American Hotels",
        "Ameritech Systems",
        "American Healthcare",
        "Amerika Hospitality",
    ]
    print(f"  Target: '{target}'")
    print(f"  Candidates: {candidates}")
    matches = find_phonetic_matches(target, candidates, threshold=0.5)
    print(f"  Matches (threshold 0.5):")
    for match, score in matches:
        print(f"    {match}: {score:.2f}")
    print()

    # Test ORDER-INDEPENDENT UNION MATCHING
    print("=" * 60)
    print("ORDER-INDEPENDENT UNION TOKEN MATCHING")
    print("=" * 60)
    reorder_tests = [
        ("Teamsters Local 705", "Local 705 International Brotherhood of Teamsters"),
        ("SEIU Local 1000", "Service Employees International Union Local 1000"),
        ("IBT Local 705", "Teamsters Local 705"),
        ("UFCW Local 400", "United Food and Commercial Workers Local 400"),
        ("Painters District Council 5", "International Union of Painters and Allied Trades DC 5"),
        ("Laborers Local 79", "LIUNA Local 79"),
        ("CWA Local 1180", "Communications Workers of America Local 1180"),
        ("UAW Local 600", "United Auto Workers Local 600"),
        # These should NOT match well
        ("Teamsters Local 705", "SEIU Local 705"),
        ("IBEW Local 3", "Plumbers Local 3"),
    ]
    print("  Testing reordered/variant names:")
    print()
    for name1, name2 in reorder_tests:
        result = union_token_match_score(name1, name2)
        match_indicator = "MATCH" if result['overall_score'] >= 0.5 else "NO"
        print(f"  {name1[:35]:35}")
        print(f"  {name2[:35]:35}")
        print(f"    Score: {result['overall_score']:.2f}, Local: {'Y' if result['local_match'] else 'N'}, Acronym: {'Y' if result['acronym_match'] else 'N'} -> [{match_indicator}]")
        print()

    # Test compare_union_names (comprehensive)
    print("=" * 60)
    print("COMPREHENSIVE UNION NAME COMPARISON")
    print("=" * 60)
    compare_tests = [
        ("Teamsters 705", "International Brotherhood of Teamsters Local 705"),
        ("SEIU", "Service Employees International Union"),
        ("Nurses United Local 123", "National Nurses United Local 123"),
        ("Random Workers Union", "Completely Different Union"),
    ]
    for name1, name2 in compare_tests:
        result = compare_union_names(name1, name2)
        print(f"  '{name1}' vs '{name2}'")
        print(f"    Combined: {result['combined_score']:.2f}, Confidence: {result['confidence']}, Rec: {result['recommendation']}")
        print()
