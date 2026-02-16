#!/usr/bin/env python3
"""
Calculate occupation similarity from industry staffing patterns.

Similarity is cosine similarity over occupation vectors where each dimension is
an industry_code and each value is percent_of_industry.
"""
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from psycopg2.extras import RealDictCursor, execute_batch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


def build_occupation_vectors(cur) -> Dict[str, Dict[str, float]]:
    """
    Build sparse vectors: {occupation_code: {industry_code: percent_of_industry}}.
    """
    cur.execute(
        """
        SELECT occupation_code, industry_code, percent_of_industry
        FROM bls_industry_occupation_matrix
        WHERE occupation_type = 'Line Item'
          AND occupation_code IS NOT NULL
          AND industry_code IS NOT NULL
          AND percent_of_industry IS NOT NULL
          AND percent_of_industry > 0
        """
    )

    vectors: Dict[str, Dict[str, float]] = {}
    for row in cur.fetchall():
        occ = row["occupation_code"]
        ind = row["industry_code"]
        pct = float(row["percent_of_industry"])
        vectors.setdefault(occ, {})[ind] = pct
    return vectors


def calculate_similarities(
    occupation_vectors: Dict[str, Dict[str, float]],
    threshold: float = 0.3,
) -> List[Dict]:
    """
    Calculate pairwise cosine similarity for all occupation pairs.
    """
    occupations = sorted(occupation_vectors.keys())
    norms: Dict[str, float] = {}
    for occ in occupations:
        vec = occupation_vectors[occ]
        norms[occ] = math.sqrt(sum(v * v for v in vec.values()))

    results: List[Dict] = []
    total_pairs = len(occupations) * (len(occupations) - 1) // 2
    processed = 0

    for i, occ1 in enumerate(occupations):
        vec1 = occupation_vectors[occ1]
        norm1 = norms[occ1]
        if norm1 == 0:
            continue

        keys1 = set(vec1.keys())
        for occ2 in occupations[i + 1:]:
            processed += 1
            vec2 = occupation_vectors[occ2]
            norm2 = norms[occ2]
            if norm2 == 0:
                continue

            shared_keys = keys1.intersection(vec2.keys())
            if not shared_keys:
                continue

            dot = sum(vec1[k] * vec2[k] for k in shared_keys)
            sim = dot / (norm1 * norm2)

            if sim >= threshold:
                results.append(
                    {
                        "occupation_code_1": occ1,
                        "occupation_code_2": occ2,
                        "similarity_score": round(sim, 4),
                        "shared_industries": len(shared_keys),
                        "method": "cosine",
                    }
                )

        if (i + 1) % 100 == 0 or i + 1 == len(occupations):
            print(f"  Progress: {i + 1}/{len(occupations)} occupations ({processed:,}/{total_pairs:,} pairs)")

    return results


def create_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS occupation_similarity (
            occupation_code_1 VARCHAR(10),
            occupation_code_2 VARCHAR(10),
            similarity_score NUMERIC(5,4),
            shared_industries INTEGER,
            method VARCHAR(20) DEFAULT 'cosine',
            PRIMARY KEY (occupation_code_1, occupation_code_2)
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_occ_sim_1 ON occupation_similarity(occupation_code_1);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_occ_sim_2 ON occupation_similarity(occupation_code_2);")


def load_similarities(cur, similarities: List[Dict]) -> int:
    if not similarities:
        return 0

    cur.execute("TRUNCATE TABLE occupation_similarity")
    query = """
        INSERT INTO occupation_similarity (
            occupation_code_1,
            occupation_code_2,
            similarity_score,
            shared_industries,
            method
        ) VALUES (
            %(occupation_code_1)s,
            %(occupation_code_2)s,
            %(similarity_score)s,
            %(shared_industries)s,
            %(method)s
        )
    """
    execute_batch(cur, query, similarities, page_size=2000)
    return len(similarities)


def show_top_pairs(cur, min_score: float = 0.7, limit: int = 20) -> List[Tuple]:
    cur.execute(
        """
        SELECT
            o1.occupation_title AS occ_title_1,
            o2.occupation_title AS occ_title_2,
            s.similarity_score
        FROM occupation_similarity s
        JOIN (
            SELECT occupation_code, MAX(occupation_title) AS occupation_title
            FROM bls_industry_occupation_matrix
            GROUP BY occupation_code
        ) o1 ON s.occupation_code_1 = o1.occupation_code
        JOIN (
            SELECT occupation_code, MAX(occupation_title) AS occupation_title
            FROM bls_industry_occupation_matrix
            GROUP BY occupation_code
        ) o2 ON s.occupation_code_2 = o2.occupation_code
        WHERE s.similarity_score >= %s
        ORDER BY s.similarity_score DESC
        LIMIT %s
        """,
        (min_score, limit),
    )
    return [(row["occ_title_1"], row["occ_title_2"], row["similarity_score"]) for row in cur.fetchall()]


def main() -> int:
    conn = get_connection(cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            print("Building occupation vectors...")
            vectors = build_occupation_vectors(cur)
            print(f"  Occupations with vectors: {len(vectors):,}")

            print("Calculating cosine similarities (threshold=0.30)...")
            similarities = calculate_similarities(vectors, threshold=0.3)
            print(f"  Similar pairs above threshold: {len(similarities):,}")

            create_table(cur)
            loaded = load_similarities(cur, similarities)
            conn.commit()
            print(f"Loaded {loaded:,} similarity rows")

            cur.execute("SELECT COUNT(*) AS c FROM occupation_similarity")
            total = cur.fetchone()["c"]
            print(f"Total rows in occupation_similarity: {total:,}")

            print("\nTop high-similarity occupation pairs:")
            for title1, title2, score in show_top_pairs(cur):
                print(f"  {title1} <-> {title2}: {score}")

        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
