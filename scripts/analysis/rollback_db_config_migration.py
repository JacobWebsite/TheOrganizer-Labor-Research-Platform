"""
Rollback helper for db_config migration backups.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
BACKUP_ROOT = ROOT / "docs" / "db_config_migration_backups"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback db_config migration from backups")
    parser.add_argument("--prefix", default="", help="Restore only backup paths under this prefix")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not BACKUP_ROOT.exists():
        print(f"No backup directory: {BACKUP_ROOT}")
        return 1

    restored = 0
    for src in BACKUP_ROOT.rglob("*.py"):
        rel = src.relative_to(BACKUP_ROOT)
        rel_str = str(rel).replace("\\", "/")
        if args.prefix and not rel_str.startswith(args.prefix.replace("\\", "/").rstrip("/")):
            continue
        dst = ROOT / rel
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        restored += 1

    mode = "dry-run" if args.dry_run else "apply"
    print(f"Rollback mode: {mode}")
    print(f"Files {'matched' if args.dry_run else 'restored'}: {restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

