"""
Build manifest and coverage report for New Data sources bundle.

Usage:
  python scripts/etl/newsrc_manifest.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from newsrc_common import DEFAULT_SOURCE_ROOT


def sha256_head(path: Path, max_mb: int = 32) -> str:
    h = hashlib.sha256()
    remaining = max_mb * 1024 * 1024
    with open(path, "rb") as f:
        while remaining > 0:
            chunk = f.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def classify(name: str) -> str:
    n = name.lower()
    if "lodes" in n or "_wac_" in n or "_rac_" in n or "_od_" in n or "_xwalk" in n:
        return "lodes"
    if "f_5500" in n or "sch_" in n or "form5500" in n:
        return "form5500"
    if "cbp" in n or "cb2300" in n:
        return "cbp"
    if n.startswith("public_") and n.endswith(".csv"):
        return "ppp"
    if "contracts_full" in n and n.startswith("fy"):
        return "usaspending"
    if "annual" in n or "qtrly" in n or "enb" in n:
        return "qcew"
    if n.startswith("usa_00001"):
        return "ipums_acs"
    return "other"


def parse_args():
    ap = argparse.ArgumentParser(description="Create manifest for new data sources folder")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--include-hash", action="store_true")
    return ap.parse_args()


def main():
    args = parse_args()
    root = Path(args.source_root)
    files = sorted([p for p in root.rglob("*") if p.is_file()])

    rows = []
    coverage = {}
    for p in files:
        source = classify(p.name)
        coverage[source] = coverage.get(source, 0) + 1
        row = {
            "path": str(p),
            "name": p.name,
            "bytes": p.stat().st_size,
            "source": source,
            "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
        }
        if args.include_hash:
            row["sha256_head_32mb"] = sha256_head(p)
        rows.append(row)

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "root": str(root),
        "file_count": len(rows),
        "coverage_counts": coverage,
        "files": rows,
    }

    out = root / f"manifest_new_sources_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
