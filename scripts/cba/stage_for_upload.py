"""Prepare PDFs from a shard CSV for upload to RunPod.

Two modes:
  --mode copy    Copy the shard's PDFs into a clean staging directory.
                 Use for the small benchmark (~20 files) where one SCP
                 command handles it.
  --mode list    Write a newline-delimited list of source paths to a .txt
                 file that rsync can consume:
                     rsync -av --files-from=upload_list.txt SRC USER@POD:DEST
                 Use for the full upload (8 GB of scanned PDFs).

Default input is the benchmark shard.

Usage:
    py scripts/cba/stage_for_upload.py                                # benchmark, copy mode
    py scripts/cba/stage_for_upload.py --shard data/cba_shards/shard_00_of_04.csv --mode list
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

DEFAULT_SHARD = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real"
    r"\data\cba_shards\benchmark_shard.csv"
)
DEFAULT_SRC = r"C:\Users\jakew\Downloads\OPDR CBAs"
DEFAULT_STAGE_ROOT = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_upload_staging"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", default=DEFAULT_SHARD)
    parser.add_argument("--src-dir", default=DEFAULT_SRC)
    parser.add_argument("--stage-root", default=DEFAULT_STAGE_ROOT)
    parser.add_argument(
        "--mode",
        choices=["copy", "list"],
        default="copy",
        help="copy: physically copy files; list: write rsync --files-from= manifest.",
    )
    args = parser.parse_args()

    shard_path = Path(args.shard)
    src = Path(args.src_dir)
    stage_root = Path(args.stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)

    with shard_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    print(f"Shard:  {shard_path.name}  ({len(rows)} rows)")
    print(f"Source: {src}")

    if args.mode == "copy":
        target_dir = stage_root / shard_path.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        copied_bytes = 0
        missing = 0
        for r in rows:
            sp = src / r["filename"]
            tp = target_dir / r["filename"]
            if not sp.exists():
                missing += 1
                print(f"  MISSING: {r['filename']}")
                continue
            if tp.exists() and tp.stat().st_size == sp.stat().st_size:
                continue   # already staged
            shutil.copy2(sp, tp)
            copied_bytes += sp.stat().st_size
        print(f"Staged to: {target_dir}")
        print(
            f"Copied: {copied_bytes / (1024**2):.1f} MB   "
            f"missing: {missing}"
        )
        print()
        print("Upload command (replace POD_IP and POD_PORT):")
        print(f'  scp -P POD_PORT -r "{target_dir}" root@POD_IP:/workspace/pdfs')
        return

    # mode == list
    list_path = stage_root / f"{shard_path.stem}.upload.txt"
    missing = 0
    total_bytes = 0
    with list_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            sp = src / r["filename"]
            if not sp.exists():
                missing += 1
                continue
            fh.write(r["filename"] + "\n")
            total_bytes += sp.stat().st_size

    print(f"Wrote: {list_path}")
    print(
        f"Files: {len(rows) - missing:,}   "
        f"size: {total_bytes / (1024**3):.2f} GB   "
        f"missing: {missing}"
    )
    print()
    print("Upload command (replace POD_IP and POD_PORT):")
    print(
        f'  rsync -avP --files-from="{list_path}" \\\n'
        f'    "{src}/" root@POD_IP:/workspace/pdfs/ \\\n'
        f"    -e 'ssh -p POD_PORT'"
    )


if __name__ == "__main__":
    main()
