"""
Auto-fix quoted-literal DB password bugs.

Usage:
  python scripts/analysis/fix_literal_password_bug.py --dry-run
  python scripts/analysis/fix_literal_password_bug.py --apply --backup-dir docs/password_fix_backups
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "docs" / "PARALLEL_PASSWORD_AUTOFIX_REPORT.md"

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".claude", "archive", "logs", "output", "reports"}

REPLACEMENTS = [
    ('"os.environ.get(\'DB_PASSWORD\', \'\')"', "os.environ.get('DB_PASSWORD', '')"),
    ("'os.environ.get('DB_PASSWORD', '')'", "os.environ.get('DB_PASSWORD', '')"),
    ('"os.environ.get(\\"DB_PASSWORD\\", \\"\\")"', 'os.environ.get("DB_PASSWORD", "")'),
    ("'os.environ.get(\"DB_PASSWORD\", \"\")'", 'os.environ.get("DB_PASSWORD", "")'),
]


def should_scan(path: Path) -> bool:
    return path.suffix.lower() == ".py" and not any(part in SKIP_DIRS for part in path.parts)


def fix_file(path: Path) -> tuple[int, str]:
    text = path.read_text(encoding="utf-8")
    original = text
    replacements = 0
    for old, new in REPLACEMENTS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            replacements += count
    if text != original:
        return replacements, text
    return 0, original


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix quoted-literal DB_PASSWORD bugs")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--dry-run", action="store_true", help="Report only (default behavior)")
    parser.add_argument("--backup-dir", default="", help="Backup directory (used only with --apply)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Markdown report output path")
    args = parser.parse_args()

    apply = bool(args.apply)
    if not args.apply and not args.dry_run:
        # default to dry-run
        apply = False

    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    if apply and backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)

    changed = []
    total_replacements = 0
    scanned = 0

    for path in ROOT.rglob("*.py"):
        if not should_scan(path):
            continue
        scanned += 1
        count, new_text = fix_file(path)
        if count <= 0:
            continue

        rel = path.relative_to(ROOT)
        changed.append((str(rel), count))
        total_replacements += count

        if apply:
            if backup_dir:
                dst = backup_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)
            path.write_text(new_text, encoding="utf-8")

    report_path = Path(args.report)
    lines = [
        "# Parallel Password Auto-fix Report",
        "",
        f"- Mode: {'apply' if apply else 'dry-run'}",
        f"- Files scanned: {scanned}",
        f"- Files changed: {len(changed)}",
        f"- Total replacements: {total_replacements}",
        "",
        "## Changed Files",
    ]
    if changed:
        for rel, count in changed:
            lines.append(f"- `{rel}` ({count} replacement{'s' if count != 1 else ''})")
    else:
        lines.append("- None")

    if apply and backup_dir:
        lines.extend(["", f"- Backups written to: `{backup_dir}`"])

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {report_path}")
    print(f"Files changed: {len(changed)}")
    print(f"Total replacements: {total_replacements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

