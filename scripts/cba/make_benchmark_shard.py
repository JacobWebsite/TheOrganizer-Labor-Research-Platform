"""Build a small representative benchmark shard from the scan manifest.

Picks N scanned PDFs stratified by page-count quartile so the per-page
throughput estimate is realistic (not biased by short or long contracts).

Usage:
    py scripts/cba/make_benchmark_shard.py                 # default 20 PDFs
    py scripts/cba/make_benchmark_shard.py --count 40
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
from pathlib import Path

DEFAULT_MANIFEST = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_scan_manifest.csv"
)
DEFAULT_OUT = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real"
    r"\data\cba_shards\benchmark_shard.csv"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--output", default=DEFAULT_OUT)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    with open(args.manifest, "r", encoding="utf-8", newline="") as fh:
        rows = [
            r for r in csv.DictReader(fh)
            if r["is_scanned"] == "1" and not r["error"] and int(r["page_count"]) > 0
        ]
        fields = list(rows[0].keys())

    rows.sort(key=lambda r: int(r["page_count"]))
    n = len(rows)

    # Quartile boundaries
    q1 = n // 4
    q2 = n // 2
    q3 = 3 * n // 4

    buckets = {
        "Q1 (smallest 25%)": rows[:q1],
        "Q2 (25-50%)": rows[q1:q2],
        "Q3 (50-75%)": rows[q2:q3],
        "Q4 (largest 25%)": rows[q3:],
    }

    per_bucket = max(1, args.count // 4)
    chosen: list[dict] = []
    print(f"Stratified sample of {args.count} from {n:,} scanned PDFs:")
    for name, bucket in buckets.items():
        sample = rng.sample(bucket, min(per_bucket, len(bucket)))
        chosen.extend(sample)
        pcs = [int(r["page_count"]) for r in bucket]
        print(
            f"  {name:25s} pages {min(pcs)}-{max(pcs)}  "
            f"(median {statistics.median(pcs):.0f})  -> picked {len(sample)}"
        )

    chosen.sort(key=lambda r: int(r["page_count"]))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(chosen)

    total_pages = sum(int(r["page_count"]) for r in chosen)
    print()
    print(f"Wrote {len(chosen)} PDFs ({total_pages:,} pages) -> {out_path}")
    print(f"Expected wall time on A4000 @ 0.6s/page: {total_pages * 0.6 / 60:.1f} min")
    print(f"Expected cost: ${total_pages * 0.6 / 3600 * 0.20:.3f}")


if __name__ == "__main__":
    main()
