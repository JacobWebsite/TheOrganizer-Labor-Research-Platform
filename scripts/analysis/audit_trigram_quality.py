import argparse
import os
import random
import sys
from collections import defaultdict
from statistics import mean

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

BANDS = [
    (0.40, 0.49),
    (0.50, 0.59),
    (0.60, 0.69),
    (0.70, 0.79),
    (0.80, 0.89),
    (0.90, 1.00),
]


def extract_similarity(evidence):
    if not isinstance(evidence, dict):
        return None
    for key in ("name_similarity", "trigram_sim", "similarity"):
        val = evidence.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def pick_band(sim):
    if sim is None:
        return None
    for lo, hi in BANDS:
        if lo <= sim <= hi:
            return (lo, hi)
    return None


def main():
    parser = argparse.ArgumentParser(description="Audit FUZZY_TRIGRAM quality distribution")
    parser.add_argument("--floor", type=float, default=0.75, help="Candidate rejection floor")
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            SELECT id, source_system, source_id, target_id, confidence_score, evidence
            FROM unified_match_log
            WHERE status = 'active' AND match_method = 'FUZZY_TRIGRAM'
            """
        )
        rows = cur.fetchall()

        band_rows = defaultdict(list)
        valid = []
        for row in rows:
            sim = extract_similarity(row.get("evidence"))
            row["similarity"] = sim
            if sim is not None:
                valid.append(sim)
                band = pick_band(sim)
                if band:
                    band_rows[band].append(row)

        print(f"Active FUZZY_TRIGRAM rows: {len(rows):,}")
        print(f"Rows with usable similarity: {len(valid):,}")
        if valid:
            print(f"Similarity min/avg/max: {min(valid):.3f} / {mean(valid):.3f} / {max(valid):.3f}")

        print("\nHistogram:")
        for lo, hi in BANDS:
            bucket = band_rows[(lo, hi)]
            print(f"  {lo:.2f}-{hi:.2f}: {len(bucket):,}")

        random.seed(42)
        print("\nSamples (5 per band):")
        for lo, hi in BANDS:
            bucket = band_rows[(lo, hi)]
            print(f"\nBand {lo:.2f}-{hi:.2f} ({len(bucket):,} rows)")
            for row in random.sample(bucket, k=min(5, len(bucket))):
                ev = row.get("evidence") or {}
                src = ev.get("source_name") or ev.get("src") or "<missing>"
                tgt = ev.get("target_name") or ev.get("tgt") or "<missing>"
                print(f"  id={row['id']} source={row['source_system']} sim={row['similarity']:.3f} | {src} -> {tgt}")

        below = [r for r in rows if r.get("similarity") is not None and r["similarity"] < args.floor]
        by_source = defaultdict(int)
        for row in below:
            by_source[row["source_system"]] += 1

        print(f"\nWould be superseded at floor={args.floor:.2f}: {len(below):,}")
        for source, cnt in sorted(by_source.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {source}: {cnt:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
