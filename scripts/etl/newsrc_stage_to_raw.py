"""
Stage "New Data sources 2_27" files into canonical data/raw folders.

Usage:
  python scripts/etl/newsrc_stage_to_raw.py
  python scripts/etl/newsrc_stage_to_raw.py --copy   # default is move
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from newsrc_common import DEFAULT_SOURCE_ROOT, PROJECT_ROOT


TARGETS = {
    "form5500": "data/raw/form5500",
    "lodes": "data/raw/lodes",
    "cbp": "data/raw/cbp",
    "ppp": "data/raw/ppp",
    "usaspending": "data/raw/usaspending",
    "qcew": "data/raw/qcew",
    "ipums_acs": "data/raw/ipums_acs",
}


def classify(name: str) -> str | None:
    n = name.lower()
    if "form5500" in n or "f_5500" in n or "sch_" in n:
        return "form5500"
    if "lodes" in n or "_wac_" in n or "_rac_" in n or "_od_" in n or "_xwalk" in n:
        return "lodes"
    if "cbp" in n or "cb2300" in n:
        return "cbp"
    if n.startswith("public_") or "ppp" in n:
        return "ppp"
    if n.startswith("fy") and "contracts_full" in n:
        return "usaspending"
    if "qtrly" in n or "annual" in n or "enb" in n:
        return "qcew"
    if n.startswith("usa_00001"):
        return "ipums_acs"
    return None


def parse_args():
    ap = argparse.ArgumentParser(description="Stage new source files into data/raw")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--copy", action="store_true", help="Copy files instead of moving")
    return ap.parse_args()


def main():
    args = parse_args()
    src = Path(args.source_root)
    moved = 0

    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        key = classify(p.name)
        if not key:
            continue
        target_dir = PROJECT_ROOT / TARGETS[key]
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / p.name
        if dest.exists():
            continue
        if args.copy:
            shutil.copy2(p, dest)
        else:
            shutil.move(str(p), str(dest))
        moved += 1
        print(f"[ok] {p.name} -> {target_dir}")

    print(f"Done. files_staged={moved}")


if __name__ == "__main__":
    main()
