"""Script 12: Embed CBA articles and classify 'other' articles using kNN.

Uses Gemini text-embedding-004 to generate embeddings, then classifies
"other" articles by cosine similarity to labeled articles. Pure numpy
classification -- no generative LLM calls.

Subcommands:
    py scripts/cba/12_embed_classify.py embed --all
    py scripts/cba/12_embed_classify.py classify --dry-run
    py scripts/cba/12_embed_classify.py classify --auto-assign --threshold 0.85
    py scripts/cba/12_embed_classify.py cluster
    py scripts/cba/12_embed_classify.py report
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Load .env for GOOGLE_API_KEY
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from db_config import get_connection

BATCH_SIZE = 100  # Gemini embed API limit
MAX_TEXT_CHARS = 8000  # text-embedding-004 handles ~8192 tokens
MODEL_NAME = "gemini-embedding-001"
DIMENSIONS = 3072


def _get_genai_client():
    """Initialize Gemini client."""
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set in environment")
        sys.exit(1)
    return genai.Client(api_key=api_key)


def _build_embedding_text(title: str, body: str) -> str:
    """Build text to embed: title prepended for weight, body truncated."""
    header = f"Article: {title}\n\n"
    body_limit = MAX_TEXT_CHARS - len(header)
    return header + body[:body_limit]


# ── embed subcommand ────────────────────────────────────────────────

def _fetch_articles_to_embed(cur, cba_id=None):
    """Return list of (object_id, title, text) for articles missing embeddings."""
    where = "AND s.cba_id = %s" if cba_id else ""
    params = [MODEL_NAME] + ([cba_id] if cba_id else [])
    cur.execute(f"""
        SELECT s.section_id, s.section_title, s.section_text
        FROM cba_sections s
        LEFT JOIN cba_embeddings e
            ON s.section_id = e.section_id
           AND e.model_name = %s
           AND e.object_type = 'article'
        WHERE e.embedding_id IS NULL
          AND s.detection_method = 'article_heading'
          AND length(s.section_text) > 100
          {where}
        ORDER BY s.section_id
    """, params)
    return cur.fetchall()


def _fetch_provisions_to_embed(cur, cba_id=None):
    """Return list of (object_id, title, text) for provisions missing embeddings.

    Title is constructed from provision metadata (class + article_reference)
    to give the embedding richer context.
    """
    where = "AND p.cba_id = %s" if cba_id else ""
    params = [MODEL_NAME] + ([cba_id] if cba_id else [])
    cur.execute(f"""
        SELECT p.provision_id,
               COALESCE(NULLIF(p.article_reference, ''), '')
                 || CASE WHEN p.provision_class IS NOT NULL AND p.provision_class <> ''
                         THEN ' / ' || p.provision_class ELSE '' END AS title,
               p.provision_text
        FROM cba_provisions p
        LEFT JOIN cba_embeddings e
            ON p.provision_id = e.provision_id
           AND e.model_name = %s
           AND e.object_type = 'provision'
        WHERE e.embedding_id IS NULL
          AND length(p.provision_text) > 50
          {where}
        ORDER BY p.provision_id
    """, params)
    return cur.fetchall()


def _insert_embedding(cur, object_type, object_id, values):
    """UPSERT an embedding row. object_type in {'article', 'provision'}."""
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in values) + "]"
    if object_type == "article":
        cur.execute("""
            INSERT INTO cba_embeddings
                (section_id, object_type, model_name, dimensions,
                 embedding, embedding_halfvec)
            VALUES (%s, 'article', %s, %s, %s, %s::halfvec)
            ON CONFLICT (section_id, model_name)
                WHERE object_type = 'article'
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_halfvec = EXCLUDED.embedding_halfvec,
                created_at = CURRENT_TIMESTAMP
        """, [object_id, MODEL_NAME, DIMENSIONS, json.dumps(values), vec_literal])
    elif object_type == "provision":
        cur.execute("""
            INSERT INTO cba_embeddings
                (provision_id, object_type, model_name, dimensions,
                 embedding, embedding_halfvec)
            VALUES (%s, 'provision', %s, %s, %s, %s::halfvec)
            ON CONFLICT (provision_id, model_name)
                WHERE object_type = 'provision'
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_halfvec = EXCLUDED.embedding_halfvec,
                created_at = CURRENT_TIMESTAMP
        """, [object_id, MODEL_NAME, DIMENSIONS, json.dumps(values), vec_literal])
    else:
        raise ValueError(f"Unknown object_type: {object_type}")


def _embed_batch(client, object_type, rows):
    """Embed a single batch of rows and upsert. Returns count embedded."""
    from google.genai import types

    texts = [_build_embedding_text(title or "", body or "") for _, title, body in rows]

    try:
        result = client.models.embed_content(
            model=MODEL_NAME,
            contents=texts,
            config=types.EmbedContentConfig(task_type="CLASSIFICATION"),
        )
    except Exception as exc:
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            print("  Rate limited, waiting 60s...")
            time.sleep(60)
            try:
                result = client.models.embed_content(
                    model=MODEL_NAME,
                    contents=texts,
                    config=types.EmbedContentConfig(task_type="CLASSIFICATION"),
                )
            except Exception as exc2:
                print(f"  Retry failed: {exc2}")
                return 0
        else:
            print(f"  API error: {exc}")
            time.sleep(2)
            return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, emb in enumerate(result.embeddings):
                _insert_embedding(cur, object_type, rows[i][0], emb.values)
        conn.commit()

    return len(rows)


def cmd_embed(args):
    """Generate embeddings for articles, provisions, or both via Gemini API."""
    obj_types = ["article", "provision"] if args.type == "all" else [args.type]
    client = _get_genai_client()

    for object_type in obj_types:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if object_type == "article":
                    rows = _fetch_articles_to_embed(cur, args.cba_id)
                else:
                    rows = _fetch_provisions_to_embed(cur, args.cba_id)

        if not rows:
            print(f"All {object_type}s already have embeddings. Skipping.")
            continue

        total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Embedding {len(rows)} {object_type}s ({total_batches} batches)")
        print("=" * 60)

        total_embedded = 0
        for batch_start in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            n = _embed_batch(client, object_type, batch)
            total_embedded += n
            print(f"  Batch {batch_num}/{total_batches}: embedded {n} (total: {total_embedded}/{len(rows)})")
            if batch_start + BATCH_SIZE < len(rows):
                time.sleep(0.5)

        print(f"\nDone: {total_embedded} {object_type}s embedded")


# ── classify subcommand ─────────────────────────────────────────────

def cmd_classify(args):
    """Classify 'other' articles by kNN in embedding space."""
    threshold = args.threshold
    k = 10

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Load labeled articles (non-other) with embeddings
            cur.execute("""
                SELECT e.section_id, e.embedding,
                       s.attributes->>'category' as category,
                       s.section_title
                FROM cba_embeddings e
                JOIN cba_sections s ON s.section_id = e.section_id
                WHERE s.attributes->>'category' != 'other'
                  AND e.model_name = %s
            """, [MODEL_NAME])
            labeled_rows = cur.fetchall()

            # Load "other" articles with embeddings
            cur.execute("""
                SELECT e.section_id, e.embedding,
                       s.section_title, s.cba_id
                FROM cba_embeddings e
                JOIN cba_sections s ON s.section_id = e.section_id
                WHERE s.attributes->>'category' = 'other'
                  AND e.model_name = %s
            """, [MODEL_NAME])
            other_rows = cur.fetchall()

    if not labeled_rows:
        print("No labeled embeddings found. Run 'embed --all' first.")
        return

    if not other_rows:
        print("No 'other' articles with embeddings found.")
        return

    print(f"Classifying {len(other_rows)} 'other' articles using {len(labeled_rows)} labeled examples")
    print(f"Threshold: {threshold}, k={k}")
    print("=" * 60)

    # Build numpy arrays
    labeled_embs = np.array([row[1] for row in labeled_rows], dtype=np.float32)
    labeled_cats = [row[2] for row in labeled_rows]

    other_embs = np.array([row[1] for row in other_rows], dtype=np.float32)

    # Normalize for cosine similarity
    labeled_norm = labeled_embs / np.linalg.norm(labeled_embs, axis=1, keepdims=True)
    other_norm = other_embs / np.linalg.norm(other_embs, axis=1, keepdims=True)

    # Compute similarity matrix
    sim_matrix = other_norm @ labeled_norm.T

    # Classify each "other" article
    results = []
    for i in range(len(other_rows)):
        section_id = other_rows[i][0]
        title = other_rows[i][2] or "(untitled)"
        cba_id = other_rows[i][3]

        top_k_idx = np.argsort(sim_matrix[i])[-k:][::-1]
        top_k_sims = sim_matrix[i][top_k_idx]
        top_k_cats = [labeled_cats[j] for j in top_k_idx]

        # Weighted vote
        votes = {}
        for cat, sim in zip(top_k_cats, top_k_sims):
            votes[cat] = votes.get(cat, 0.0) + float(sim)

        total_weight = sum(votes.values())
        sorted_votes = sorted(votes.items(), key=lambda x: -x[1])
        best_cat = sorted_votes[0][0]
        confidence = sorted_votes[0][1] / total_weight
        runner_up = sorted_votes[1] if len(sorted_votes) > 1 else None

        results.append({
            "section_id": section_id,
            "cba_id": cba_id,
            "title": title,
            "predicted": best_cat,
            "confidence": round(confidence, 3),
            "top_sim": round(float(top_k_sims[0]), 3),
            "runner_up": (runner_up[0], round(runner_up[1] / total_weight, 3)) if runner_up else None,
        })

    # Bucket by confidence tier
    high = [r for r in results if r["confidence"] >= 0.85]
    medium = [r for r in results if 0.60 <= r["confidence"] < 0.85]
    low = [r for r in results if r["confidence"] < 0.60]

    # Print results
    print(f"\nHigh confidence (>= 0.85): {len(high)} articles -> auto-assign")
    for r in sorted(high, key=lambda x: -x["confidence"]):
        print(f"  CBA {r['cba_id']:>3d} | {r['title'][:45]:<45s} -> {r['predicted']:<22s} ({r['confidence']:.2f})")

    print(f"\nMedium confidence (0.60-0.85): {len(medium)} articles -> needs review")
    for r in sorted(medium, key=lambda x: -x["confidence"]):
        ru = f"  runner-up: {r['runner_up'][0]}" if r["runner_up"] else ""
        print(f"  CBA {r['cba_id']:>3d} | {r['title'][:45]:<45s} -> {r['predicted']:<22s} ({r['confidence']:.2f}){ru}")

    print(f"\nLow confidence (< 0.60): {len(low)} articles -> genuinely other")
    for r in sorted(low, key=lambda x: -x["confidence"]):
        print(f"  CBA {r['cba_id']:>3d} | {r['title'][:45]:<45s} -> {r['predicted']:<22s} ({r['confidence']:.2f})")

    # Category distribution of predictions
    cat_counts = {}
    for r in high + medium:
        cat_counts[r["predicted"]] = cat_counts.get(r["predicted"], 0) + 1
    print("\nPredicted category distribution (high + medium):")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:<25s} {cnt:>4d}")

    if args.dry_run:
        print("\nDRY RUN -- no changes written")
        return

    # Write results to cba_sections.attributes
    with get_connection() as conn:
        with conn.cursor() as cur:
            for r in results:
                updates = {
                    "embedding_category": r["predicted"],
                    "embedding_confidence": r["confidence"],
                    "embedding_top_similarity": r["top_sim"],
                }
                if r["runner_up"]:
                    updates["embedding_runner_up"] = list(r["runner_up"])

                if r["confidence"] >= 0.85 and args.auto_assign:
                    # Auto-assign: update the main category
                    updates["original_category"] = "other"
                    cur.execute("""
                        UPDATE cba_sections
                        SET attributes = attributes || %s
                        WHERE section_id = %s
                    """, [json.dumps({"category": r["predicted"], **updates}), r["section_id"]])
                elif r["confidence"] >= 0.60:
                    # Medium: flag for review
                    updates["needs_review"] = True
                    cur.execute("""
                        UPDATE cba_sections
                        SET attributes = attributes || %s
                        WHERE section_id = %s
                    """, [json.dumps(updates), r["section_id"]])
                else:
                    # Low: mark as genuinely other
                    updates["genuinely_other"] = True
                    cur.execute("""
                        UPDATE cba_sections
                        SET attributes = attributes || %s
                        WHERE section_id = %s
                    """, [json.dumps(updates), r["section_id"]])

            conn.commit()

    auto_count = len(high) if args.auto_assign else 0
    print(f"\nWritten: {auto_count} auto-assigned, {len(medium)} flagged for review, {len(low)} marked genuinely_other")


# ── cluster subcommand ──────────────────────────────────────────────

def cmd_cluster(args):
    """Discover clusters among remaining 'other' articles."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.section_id, e.embedding,
                       s.section_title, s.cba_id
                FROM cba_embeddings e
                JOIN cba_sections s ON s.section_id = e.section_id
                WHERE s.attributes->>'category' = 'other'
                  AND COALESCE(s.attributes->>'genuinely_other', 'false') != 'true'
                  AND e.model_name = %s
            """, [MODEL_NAME])
            rows = cur.fetchall()

    if not rows:
        # Fall back to all "other" articles
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT e.section_id, e.embedding,
                           s.section_title, s.cba_id
                    FROM cba_embeddings e
                    JOIN cba_sections s ON s.section_id = e.section_id
                    WHERE s.attributes->>'category' = 'other'
                      AND e.model_name = %s
                """, [MODEL_NAME])
                rows = cur.fetchall()

    if len(rows) < 4:
        print(f"Only {len(rows)} 'other' articles with embeddings -- too few to cluster.")
        return

    print(f"Clustering {len(rows)} 'other' articles")
    print("=" * 60)

    embs = np.array([row[1] for row in rows], dtype=np.float32)

    # Find optimal k
    max_k = min(15, len(rows) - 1)
    best_k, best_score = 3, -1
    print("\nSilhouette scores:")
    for k in range(3, max_k + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(embs)
        score = silhouette_score(embs, labels, metric="cosine")
        marker = " <-- best" if score > best_score else ""
        print(f"  k={k:>2d}: {score:.3f}{marker}")
        if score > best_score:
            best_k, best_score = k, score

    # Run final clustering
    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(embs)

    print(f"\nBest k={best_k} (silhouette={best_score:.3f})")
    print("\nCluster contents:")

    for cluster_id in range(best_k):
        members = [(rows[i][2], rows[i][3]) for i in range(len(rows)) if labels[i] == cluster_id]
        print(f"\n  Cluster {cluster_id + 1} ({len(members)} articles):")
        for title, cba_id in members[:10]:
            print(f"    CBA {cba_id:>3d}: {(title or '(untitled)')[:60]}")
        if len(members) > 10:
            print(f"    ... and {len(members) - 10} more")


# ── report subcommand ───────────────────────────────────────────────

def cmd_report(args):
    """Print summary statistics."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM cba_sections WHERE detection_method = 'article_heading'")
            total_articles = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM cba_embeddings WHERE model_name = %s", [MODEL_NAME])
            total_embedded = cur.fetchone()[0]

            cur.execute("""
                SELECT attributes->>'category', count(*)
                FROM cba_sections
                WHERE detection_method = 'article_heading'
                GROUP BY attributes->>'category'
                ORDER BY count(*) DESC
            """)
            cat_dist = cur.fetchall()

            cur.execute("""
                SELECT count(*) FROM cba_sections
                WHERE attributes->>'embedding_category' IS NOT NULL
            """)
            classified = cur.fetchone()[0]

            cur.execute("""
                SELECT count(*) FROM cba_sections
                WHERE attributes->>'original_category' = 'other'
            """)
            auto_assigned = cur.fetchone()[0]

            cur.execute("""
                SELECT count(*) FROM cba_sections
                WHERE attributes->>'needs_review' = 'true'
            """)
            needs_review = cur.fetchone()[0]

            cur.execute("""
                SELECT count(*) FROM cba_sections
                WHERE attributes->>'genuinely_other' = 'true'
            """)
            genuinely_other = cur.fetchone()[0]

    other_count = sum(cnt for cat, cnt in cat_dist if cat == "other")

    print("=== CBA Article Embedding Classification Report ===")
    print()
    print(f"Total articles:           {total_articles:>6,}")
    print(f"Embedded:                 {total_embedded:>6,}")
    print(f"Originally 'other':       {other_count:>6,} ({other_count * 100 // max(total_articles, 1)}%)")
    print()
    print("Embedding classifications:")
    print(f"  Auto-assigned:          {auto_assigned:>6,}")
    print(f"  Needs review:           {needs_review:>6,}")
    print(f"  Genuinely other:        {genuinely_other:>6,}")
    print(f"  Not yet classified:     {other_count - auto_assigned - needs_review - genuinely_other:>6,}")
    print()
    print("Category distribution (current):")
    for cat, cnt in cat_dist:
        pct = cnt * 100 // max(total_articles, 1)
        print(f"  {cat or '(null)':<25s} {cnt:>5,} ({pct}%)")


# ── main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CBA article embedding and classification")
    sub = parser.add_subparsers(dest="command", required=True)

    # embed
    p_embed = sub.add_parser("embed", help="Generate embeddings via Gemini API")
    p_embed.add_argument("--type", choices=["article", "provision", "all"],
                         default="article",
                         help="What to embed: articles, provisions, or both (default: article)")
    g = p_embed.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="All of the selected type")
    g.add_argument("--cba-id", type=int, help="Single contract")

    # classify
    p_cls = sub.add_parser("classify", help="Classify 'other' articles by kNN")
    p_cls.add_argument("--threshold", type=float, default=0.85, help="Confidence threshold (default: 0.85)")
    p_cls.add_argument("--auto-assign", action="store_true", help="Auto-update category for high-confidence")
    p_cls.add_argument("--dry-run", action="store_true", help="Print only, no DB changes")

    # cluster
    sub.add_parser("cluster", help="Discover clusters in 'other' articles")

    # report
    sub.add_parser("report", help="Print summary statistics")

    args = parser.parse_args()

    if args.command == "embed":
        cmd_embed(args)
    elif args.command == "classify":
        cmd_classify(args)
    elif args.command == "cluster":
        cmd_cluster(args)
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
