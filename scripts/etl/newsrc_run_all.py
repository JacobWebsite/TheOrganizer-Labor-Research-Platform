"""
Orchestrator for loading newly downloaded data sources.

Runs:
1) manifest
2) cbp
3) ppp
4) form5500
5) lodes
6) usaspending
7) abs
8) (optional) acs profiles

Usage:
  python scripts/etl/newsrc_run_all.py
  python scripts/etl/newsrc_run_all.py --truncate
  python scripts/etl/newsrc_run_all.py --skip-lodes
  python scripts/etl/newsrc_run_all.py --with-acs-profiles
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_step(script_name: str, extra_args: list[str]) -> None:
    script_path = SCRIPT_DIR / script_name
    cmd = [sys.executable, str(script_path), *extra_args]
    print(f"\n=== {script_name} ===")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def parse_args():
    ap = argparse.ArgumentParser(description="Run all new source loaders")
    ap.add_argument("--truncate", action="store_true", help="Truncate destination tables before first load")
    ap.add_argument("--source-root", default=None, help="Override source root directory")
    ap.add_argument("--skip-lodes", action="store_true")
    ap.add_argument("--skip-usaspending", action="store_true")
    ap.add_argument("--skip-abs", action="store_true")
    ap.add_argument("--with-acs-profiles", action="store_true", help="Also build ACS occupation-demo profiles (slow)")
    return ap.parse_args()


def main():
    args = parse_args()
    common = []
    if args.source_root:
        common.extend(["--source-root", args.source_root])

    run_step("newsrc_manifest.py", common)
    run_step("newsrc_load_cbp.py", [*common, *(["--truncate"] if args.truncate else [])])
    run_step("newsrc_load_ppp.py", [*common, *(["--truncate"] if args.truncate else [])])
    run_step("newsrc_load_form5500.py", [*common, *(["--truncate"] if args.truncate else [])])

    if not args.skip_lodes:
        run_step("newsrc_load_lodes.py", [*common, *(["--truncate"] if args.truncate else [])])

    if not args.skip_usaspending:
        run_step("newsrc_load_usaspending.py", [*common, *(["--truncate"] if args.truncate else [])])

    if not args.skip_abs:
        run_step("newsrc_load_abs.py", [*common, *(["--truncate"] if args.truncate else [])])

    if args.with_acs_profiles:
        run_step("newsrc_build_acs_profiles.py", common)

    print("\nAll requested loaders completed.")


if __name__ == "__main__":
    main()
