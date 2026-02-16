"""
Phase 5.4c: Pre-compute industry occupation overlap table.

Uses bls_industry_occupation_matrix to compute weighted Jaccard similarity
between all pairs of BLS industry codes based on shared occupations.

Also builds a naics_to_bls_industry mapping table via hierarchical prefix
matching (employer NAICS -> BLS industry code).

Run: py scripts/etl/compute_industry_occupation_overlap.py
"""
import sys
import os
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


CREATE_OVERLAP_TABLE = """
CREATE TABLE IF NOT EXISTS industry_occupation_overlap (
    industry_code_a VARCHAR(20) NOT NULL,
    industry_code_b VARCHAR(20) NOT NULL,
    overlap_score NUMERIC(5,4) NOT NULL,
    shared_occupations INTEGER NOT NULL,
    PRIMARY KEY (industry_code_a, industry_code_b)
)
"""

CREATE_MAPPING_TABLE = """
CREATE TABLE IF NOT EXISTS naics_to_bls_industry (
    naics_code VARCHAR(10) NOT NULL,
    bls_industry_code VARCHAR(20) NOT NULL,
    match_type VARCHAR(20) NOT NULL,
    PRIMARY KEY (naics_code, bls_industry_code)
)
"""


def load_industry_occupation_matrix(conn):
    """Load the BLS industry-occupation matrix into a dict of {industry: {occ: pct}}."""
    cur = conn.cursor()
    cur.execute("""
        SELECT industry_code, occupation_code, percent_of_industry
        FROM bls_industry_occupation_matrix
        WHERE percent_of_industry > 0
    """)
    matrix = defaultdict(dict)
    for row in cur.fetchall():
        matrix[row[0]][row[1]] = float(row[2])
    return matrix


def compute_weighted_jaccard(vec_a, vec_b):
    """Compute weighted Jaccard similarity: sum(min) / sum(max)."""
    all_keys = set(vec_a.keys()) | set(vec_b.keys())
    if not all_keys:
        return 0.0, 0
    num = 0.0
    den = 0.0
    shared = 0
    for k in all_keys:
        a = vec_a.get(k, 0.0)
        b = vec_b.get(k, 0.0)
        num += min(a, b)
        den += max(a, b)
        if a > 0 and b > 0:
            shared += 1
    if den == 0:
        return 0.0, 0
    return num / den, shared


def build_naics_mapping(conn):
    """Build NAICS -> BLS industry code mapping via prefix matching.

    BLS industry codes can be composite (e.g. '31-330' for manufacturing).
    Maps NAICS prefixes to the best matching BLS code.
    """
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT industry_code FROM bls_industry_occupation_matrix")
    bls_codes = [row[0] for row in cur.fetchall()]

    # BLS composite code -> NAICS 2-digit prefixes
    COMPOSITE_MAP = {
        '31-330': ['31', '32', '33'],
        '44-450': ['44', '45'],
        '48-490': ['48', '49'],
    }

    mappings = []
    for bls_code in bls_codes:
        # Check if it's a composite code
        if bls_code in COMPOSITE_MAP:
            for prefix in COMPOSITE_MAP[bls_code]:
                mappings.append((prefix, bls_code, 'composite'))
        else:
            # Extract numeric part for matching
            clean = ''.join(c for c in bls_code if c.isdigit())
            if clean:
                # Try various prefix lengths
                for length in [6, 5, 4, 3, 2]:
                    if len(clean) >= length:
                        mappings.append((clean[:length], bls_code, f'prefix_{length}'))

    return mappings


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("PHASE 5.4c: INDUSTRY OCCUPATION OVERLAP")
    print("=" * 70)

    # Step 1: Create tables
    print("\n=== Step 1: Creating tables ===")
    cur.execute(CREATE_OVERLAP_TABLE)
    cur.execute(CREATE_MAPPING_TABLE)
    conn.commit()

    # Step 2: Load matrix
    print("\n=== Step 2: Loading occupation matrix ===")
    matrix = load_industry_occupation_matrix(conn)
    industries = sorted(matrix.keys())
    print(f"  Industries: {len(industries)}")
    total_entries = sum(len(v) for v in matrix.values())
    print(f"  Total entries: {total_entries:,}")

    # Step 3: Compute pairwise overlap
    print("\n=== Step 3: Computing pairwise overlap ===")
    t0 = time.time()
    pairs = []
    n = len(industries)
    for i in range(n):
        for j in range(i, n):
            score, shared = compute_weighted_jaccard(matrix[industries[i]], matrix[industries[j]])
            if score >= 0.05 or i == j:
                pairs.append((industries[i], industries[j], round(score, 4), shared))
                if i != j:
                    pairs.append((industries[j], industries[i], round(score, 4), shared))

    elapsed = time.time() - t0
    print(f"  Computed {n * (n + 1) // 2:,} pairs in {elapsed:.1f}s")
    print(f"  Pairs with overlap >= 0.05: {len(pairs):,}")

    # Step 4: Write overlap table
    print("\n=== Step 4: Writing overlap table ===")
    cur.execute("DELETE FROM industry_occupation_overlap")
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """INSERT INTO industry_occupation_overlap
           (industry_code_a, industry_code_b, overlap_score, shared_occupations)
           VALUES %s
           ON CONFLICT (industry_code_a, industry_code_b) DO UPDATE
           SET overlap_score = EXCLUDED.overlap_score,
               shared_occupations = EXCLUDED.shared_occupations""",
        pairs,
        page_size=2000
    )
    conn.commit()
    print(f"  Inserted {len(pairs):,} rows")

    # Step 5: Build NAICS mapping
    print("\n=== Step 5: Building NAICS -> BLS mapping ===")
    mappings = build_naics_mapping(conn)
    cur.execute("DELETE FROM naics_to_bls_industry")
    execute_values(
        cur,
        """INSERT INTO naics_to_bls_industry (naics_code, bls_industry_code, match_type)
           VALUES %s
           ON CONFLICT (naics_code, bls_industry_code) DO UPDATE
           SET match_type = EXCLUDED.match_type""",
        mappings,
        page_size=1000
    )
    conn.commit()
    print(f"  Inserted {len(mappings):,} mapping rows")

    # Step 6: Stats
    print("\n=== Step 6: Statistics ===")
    cur.execute("SELECT COUNT(*) FROM industry_occupation_overlap")
    total = cur.fetchone()[0]
    cur.execute("SELECT AVG(overlap_score), MIN(overlap_score), MAX(overlap_score) FROM industry_occupation_overlap WHERE industry_code_a != industry_code_b")
    avg_s, min_s, max_s = cur.fetchone()
    print(f"  Total overlap pairs: {total:,}")
    if avg_s:
        print(f"  Avg overlap (non-self): {float(avg_s):.4f}")
        print(f"  Min: {float(min_s):.4f}, Max: {float(max_s):.4f}")

    cur.execute("SELECT COUNT(*) FROM naics_to_bls_industry")
    mapping_ct = cur.fetchone()[0]
    print(f"  NAICS->BLS mappings: {mapping_ct:,}")

    conn.close()
    print(f"\n{'=' * 70}")
    print("DONE")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
