"""
Canonical Name Lookup - Phase 4
Maps union abbreviations/variants to canonical names
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, List
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


def lookup_canonical(name: str) -> Optional[Dict]:
    """
    Look up canonical name for a union variant.
    Returns canonical name and all known variants.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # First try exact match
            cur.execute("""
                SELECT canonical_name, variant_name, variant_type
                FROM union_name_variants
                WHERE LOWER(variant_name) = LOWER(%s)
            """, [name])
            result = cur.fetchone()
            
            if result:
                # Get all variants for this canonical name
                cur.execute("""
                    SELECT variant_name, variant_type
                    FROM union_name_variants
                    WHERE LOWER(canonical_name) = LOWER(%s)
                    ORDER BY variant_type, variant_name
                """, [result['canonical_name']])
                variants = cur.fetchall()
                
                return {
                    "input": name,
                    "canonical_name": result['canonical_name'],
                    "matched_variant": result['variant_name'],
                    "variant_type": result['variant_type'],
                    "all_variants": variants
                }
            
            # Try fuzzy match on variants
            cur.execute("""
                SELECT canonical_name, variant_name, variant_type,
                       similarity(variant_name, %s) as score
                FROM union_name_variants
                WHERE similarity(variant_name, %s) > 0.3
                ORDER BY similarity(variant_name, %s) DESC
                LIMIT 1
            """, [name, name, name])
            result = cur.fetchone()
            
            if result:
                cur.execute("""
                    SELECT variant_name, variant_type
                    FROM union_name_variants
                    WHERE LOWER(canonical_name) = LOWER(%s)
                    ORDER BY variant_type, variant_name
                """, [result['canonical_name']])
                variants = cur.fetchall()
                
                return {
                    "input": name,
                    "canonical_name": result['canonical_name'],
                    "matched_variant": result['variant_name'],
                    "variant_type": result['variant_type'],
                    "match_score": float(result['score']),
                    "match_type": "fuzzy",
                    "all_variants": variants
                }
            
            return None


def expand_search_term(name: str) -> List[str]:
    """
    Expand a search term to include canonical name and all variants.
    Useful for comprehensive union searches.
    """
    result = lookup_canonical(name)
    if result:
        terms = [result['canonical_name']]
        terms.extend([v['variant_name'] for v in result['all_variants']])
        return list(set(terms))
    return [name]


if __name__ == "__main__":
    print("=" * 60)
    print("CANONICAL LOOKUP TESTS")
    print("=" * 60)
    
    test_names = ["SEIU", "Teamsters", "UAW", "seiu", "United Auto Workers", "IBEW"]
    
    for name in test_names:
        print(f"\n'{name}':")
        result = lookup_canonical(name)
        if result:
            print(f"  Canonical: {result['canonical_name']}")
            print(f"  Matched: {result['matched_variant']} ({result['variant_type']})")
            print(f"  Variants: {len(result['all_variants'])}")
        else:
            print("  No match found")