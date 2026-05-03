"""Split a CBA scan manifest into N roughly-equal shards by total page count.

Used to divide OCR work across N parallel RunPod pods so they finish at
roughly the same wall-clock time. Only scanned rows are sharded --
text-extractable PDFs do not need GPU OCR.

Usage:
    py scripts/cba/shard_manifest.py --shards 4
    py scripts/cba/shard_manifest.py --manifest PATH --shards 2 --out-dir PATH
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

DEFAULT_MANIFEST = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_scan_manifest.csv"
)
DEFAULT_OUT = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_shards"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    parser.add_argument("--shards", type=int, required=True, help="Number of shards")
    parser.add_argument(
        "--include-text",
        action="store_true",
        help="Include text-extractable PDFs in shards (default: scanned only).",
    )
    args = parser.parse_args()

    manifest = Path(args.manifest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with manifest.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    fields = list(rows[0].keys()) if rows else []

    eligible = [
        r for r in rows
        if not r["error"]
        and (args.include_text or r["is_scanned"] == "1")
    ]
    # Sort largest-first so the greedy balancer works well.
    eligible.sort(key=lambda r: int(r["page_count"]), reverse=True)

    shards: list[list[dict]] = [[] for _ in range(args.shards)]
    load: list[int] = [0] * args.shards

    # Greedy: drop each row onto the shard with the smallest current load.
    for row in eligible:
        idx = load.index(min(load))
        shards[idx].append(row)
        load[idx] += int(row["page_count"])

    total_pages = sum(load)
    print(f"Manifest: {manifest}")
    print(f"Eligible rows: {len(eligible):,} ({total_pages:,} pages)")
    print(f"Shard target:  ~{total_pages // args.shards:,} pages each")
    print()

    for i, shard in enumerate(shards):
        path = out_dir / f"shard_{i:02d}_of_{args.shards:02d}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(shard)
        share = load[i] / max(total_pages, 1) * 100
        print(
            f"  shard {i:02d}: {len(shard):4d} PDFs  "
            f"{load[i]:7,d} pages  ({share:5.1f}%)  -> {path.name}"
        )

    print()
    print(f"Wrote {args.shards} shard CSVs to {out_dir}")


if __name__ == "__main__":
    main()
