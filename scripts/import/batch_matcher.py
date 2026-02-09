"""
Batch Name Matching with RapidFuzz
Phase 3: Jaro-Winkler + token-based matching for company names
"""

from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler
from typing import List, Dict, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import normalize_employer, normalize_union, normalize_for_comparison
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

def get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


# ============================================================================
# MATCHING ALGORITHMS
# ============================================================================

def jaro_winkler_score(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity (0-100). Good for company names - weights prefix matches."""
    return JaroWinkler.similarity(s1.lower(), s2.lower()) * 100


def token_sort_score(s1: str, s2: str) -> float:
    """Token sort ratio - handles word reordering. 'Kaiser Permanente' vs 'Permanente Kaiser'"""
    return fuzz.token_sort_ratio(s1.lower(), s2.lower())


def token_set_score(s1: str, s2: str) -> float:
    """Token set ratio - handles extra words. 'Kroger' vs 'The Kroger Company Inc'"""
    return fuzz.token_set_ratio(s1.lower(), s2.lower())


def combined_score(s1: str, s2: str, weights: Dict[str, float] = None) -> float:
    """
    Weighted combination of multiple algorithms.
    Default weights optimized for company names.
    """
    if weights is None:
        weights = {
            'jaro_winkler': 0.4,
            'token_sort': 0.3,
            'token_set': 0.3,
        }
    
    scores = {
        'jaro_winkler': jaro_winkler_score(s1, s2),
        'token_sort': token_sort_score(s1, s2),
        'token_set': token_set_score(s1, s2),
    }
    
    return sum(scores[k] * weights[k] for k in weights)


# ============================================================================
# BATCH MATCHING
# ============================================================================

def find_best_matches(
    query: str,
    candidates: List[str],
    threshold: float = 70.0,
    limit: int = 10,
    algorithm: str = 'combined'
) -> List[Tuple[str, float, int]]:
    """
    Find best matches for a query against a list of candidates.
    """
    scorer_map = {
        'jaro_winkler': lambda s1, s2: JaroWinkler.similarity(s1, s2) * 100,
        'token_sort': fuzz.token_sort_ratio,
        'token_set': fuzz.token_set_ratio,
        'combined': combined_score,
    }
    
    scorer = scorer_map.get(algorithm, combined_score)
    
    if algorithm in ['token_sort', 'token_set']:
        results = process.extract(
            query.lower(),
            [c.lower() for c in candidates],
            scorer=scorer_map[algorithm],
            limit=limit,
            score_cutoff=threshold
        )
        return [(candidates[r[2]], r[1], r[2]) for r in results]
    else:
        scored = []
        query_lower = query.lower()
        for i, candidate in enumerate(candidates):
            score = scorer(query_lower, candidate.lower())
            if score >= threshold:
                scored.append((candidate, score, i))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]


def batch_match_employers(
    queries: List[str],
    threshold: float = 75.0,
    algorithm: str = 'combined',
    state_filter: Optional[str] = None,
    limit_per_query: int = 5
) -> Dict[str, List[Dict]]:
    """
    Batch match multiple employer names against the database.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            state_clause = "WHERE state = %s" if state_filter else ""
            params = [state_filter.upper()] if state_filter else []
            
            cur.execute(f"""
                SELECT employer_id, employer_name, city, state, latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                {state_clause}
                ORDER BY latest_unit_size DESC NULLS LAST
                LIMIT 50000
            """, params)
            
            candidates = cur.fetchall()
            candidate_names = [c['employer_name'] for c in candidates]
            
            results = {}
            for query in queries:
                norm_query = normalize_for_comparison(query, 'employer')
                
                matches = find_best_matches(
                    norm_query,
                    [normalize_for_comparison(n, 'employer') for n in candidate_names],
                    threshold=threshold,
                    limit=limit_per_query,
                    algorithm=algorithm
                )
                
                results[query] = []
                for match_name, score, idx in matches:
                    emp = candidates[idx]
                    results[query].append({
                        'employer_id': emp['employer_id'],
                        'employer_name': emp['employer_name'],
                        'normalized_name': match_name,
                        'match_score': round(score, 2),
                        'city': emp['city'],
                        'state': emp['state'],
                        'workers': emp['latest_unit_size'],
                        'union': emp['latest_union_name']
                    })
            
            return results


# ============================================================================
# CLI TESTING
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("RAPIDFUZZ MATCHING TESTS")
    print("=" * 60)
    
    test_pairs = [
        ("Kroger", "The Kroger Company"),
        ("Kaiser Permanente", "Kaiser Permanente Medical Center"),
        ("kaizer permanente", "Kaiser Permanente"),
        ("SEIU Local 1000", "Service Employees International Union Local 1000"),
    ]
    
    print("\n--- Algorithm Comparison ---")
    for s1, s2 in test_pairs:
        print(f"\n'{s1}' vs '{s2}':")
        print(f"  Jaro-Winkler: {jaro_winkler_score(s1, s2):.1f}")
        print(f"  Token Sort:   {token_sort_score(s1, s2):.1f}")
        print(f"  Token Set:    {token_set_score(s1, s2):.1f}")
        print(f"  Combined:     {combined_score(s1, s2):.1f}")
    
    print("\n--- Batch Matching Test ---")
    test_queries = ["Kroger", "Kaiser", "Walmart", "Amazon"]
    
    print(f"\nMatching {len(test_queries)} queries against database...")
    results = batch_match_employers(test_queries, threshold=70, limit_per_query=3)
    
    for query, matches in results.items():
        print(f"\n'{query}' -> {len(matches)} matches:")
        for m in matches[:3]:
            print(f"  {m['match_score']:.1f}: {m['employer_name']} ({m['city']}, {m['state']})")
