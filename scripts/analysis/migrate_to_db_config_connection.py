"""
Migrate simple `psycopg2.connect(...)` assignments to `db_config.get_connection(...)`.

Safety features:
- dry-run by default
- optional apply mode
- optional backups
- optional path-prefix filtering
- optional limit for pilot rollouts
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "docs" / "PARALLEL_DB_CONFIG_MIGRATION_REPORT.md"

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".claude",
    "archive",
    "logs",
    "output",
    "reports",
    "password_fix_backups",
    "db_config_migration_backups",
}

ASSIGN_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*psycopg2\.connect\(", re.M)


@dataclass
class Edit:
    path: Path
    replacements: int
    lines: list[int]


def should_scan(path: Path, include_prefixes: list[str]) -> bool:
    if path.suffix.lower() != ".py":
        return False
    rel = path.relative_to(ROOT)
    if rel.parts[:2] == ("scripts", "analysis"):
        return False
    if any(part in SKIP_DIRS for part in rel.parts):
        return False
    if include_prefixes:
        rel_str = str(rel).replace("\\", "/")
        if not any(rel_str.startswith(p) for p in include_prefixes):
            return False
    return True


def find_call_end(text: str, start_idx: int) -> int:
    depth = 0
    i = start_idx
    in_single = False
    in_double = False
    escape = False
    while i < len(text):
        ch = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if not in_double and ch == "'" and not in_single:
            in_single = True
            i += 1
            continue
        if in_single and ch == "'":
            in_single = False
            i += 1
            continue
        if not in_single and ch == '"' and not in_double:
            in_double = True
            i += 1
            continue
        if in_double and ch == '"':
            in_double = False
            i += 1
            continue
        if in_single or in_double:
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def ensure_get_connection_import(text: str) -> str:
    if re.search(r"from\s+db_config\s+import\s+.*\bget_connection\b", text):
        return text

    db_import_match = re.search(r"^from\s+db_config\s+import\s+([^\n]+)$", text, re.M)
    if db_import_match:
        full = db_import_match.group(0)
        imports = db_import_match.group(1)
        new_line = f"from db_config import {imports}, get_connection"
        return text.replace(full, new_line, 1)

    lines = text.splitlines(keepends=True)
    i = 0

    if lines and lines[0].startswith("#!"):
        i = 1

    # Respect encoding cookie if present
    if i < len(lines) and "coding" in lines[i]:
        i += 1

    # Skip module docstring block if present
    if i < len(lines) and lines[i].lstrip().startswith('"""'):
        i += 1
        while i < len(lines) and '"""' not in lines[i]:
            i += 1
        if i < len(lines):
            i += 1
        # consume trailing blank lines
        while i < len(lines) and lines[i].strip() == "":
            i += 1

    # Insert after import block starting at i
    insert_at = i
    while insert_at < len(lines):
        stripped = lines[insert_at].strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_at += 1
            continue
        if stripped == "":
            insert_at += 1
            continue
        break

    lines.insert(insert_at, "from db_config import get_connection\n")
    return "".join(lines)


def migrate_text(text: str) -> tuple[str, int, list[int]]:
    out = text
    replacements = 0
    line_hits: list[int] = []

    while True:
        m = ASSIGN_RE.search(out)
        if not m:
            break

        indent, var_name = m.group(1), m.group(2)
        call_start = m.end() - 1  # index at '('
        call_end = find_call_end(out, call_start)
        if call_end == -1:
            # malformed; skip this one by moving search window
            out = out[:m.start() + 1] + out[m.start() + 1:]
            continue

        call_block = out[m.start():call_end + 1]
        if "get_connection(" in call_block:
            # already migrated
            out = out[:call_end + 1] + out[call_end + 1:]
            continue

        # Cursor factory preservation (common case: RealDictCursor)
        if "cursor_factory" in call_block and "RealDictCursor" in call_block:
            replacement = f"{indent}{var_name} = get_connection(cursor_factory=RealDictCursor)"
        elif "cursor_factory" in call_block:
            # generic cursor_factory expression fallback
            cf_match = re.search(r"cursor_factory\s*=\s*([A-Za-z_][A-Za-z0-9_]*)", call_block)
            if cf_match:
                replacement = f"{indent}{var_name} = get_connection(cursor_factory={cf_match.group(1)})"
            else:
                replacement = f"{indent}{var_name} = get_connection()"
        else:
            replacement = f"{indent}{var_name} = get_connection()"

        line_no = out.count("\n", 0, m.start()) + 1
        line_hits.append(line_no)
        out = out[:m.start()] + replacement + out[call_end + 1:]
        replacements += 1

    if replacements > 0:
        out = ensure_get_connection_import(out)
    return out, replacements, line_hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate psycopg2.connect assignments to get_connection")
    parser.add_argument("--apply", action="store_true", help="Write changes")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--backup-dir", default="", help="Backup directory (with --apply)")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Markdown report path")
    parser.add_argument("--limit", type=int, default=0, help="Max files to modify (0 = no limit)")
    parser.add_argument(
        "--include-prefix",
        action="append",
        default=[],
        help="Workspace-relative prefix filter, repeatable (e.g., scripts/verify)",
    )
    args = parser.parse_args()

    apply = bool(args.apply)
    if not args.apply and not args.dry_run:
        apply = False

    include_prefixes = [p.replace("\\", "/").rstrip("/") for p in args.include_prefix]
    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    if apply and backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)

    scanned = 0
    edits: list[Edit] = []
    total_replacements = 0

    for path in ROOT.rglob("*.py"):
        if not should_scan(path, include_prefixes):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8")
        new_text, replacements, lines = migrate_text(text)
        if replacements <= 0:
            continue

        edits.append(Edit(path=path, replacements=replacements, lines=lines))
        total_replacements += replacements

        if apply:
            if backup_dir:
                rel = path.relative_to(ROOT)
                dst = backup_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)
            path.write_text(new_text, encoding="utf-8")

        if args.limit and len(edits) >= args.limit:
            break

    report_path = Path(args.report)
    lines = [
        "# Parallel db_config Migration Report",
        "",
        f"- Mode: {'apply' if apply else 'dry-run'}",
        f"- Files scanned: {scanned}",
        f"- Files changed: {len(edits)}",
        f"- Total connect() replacements: {total_replacements}",
        f"- Prefix filters: {include_prefixes if include_prefixes else 'None'}",
        f"- Limit: {args.limit if args.limit else 'None'}",
        "",
        "## Changed Files",
    ]
    if edits:
        for e in edits:
            rel = e.path.relative_to(ROOT)
            lines.append(f"- `{rel}` ({e.replacements} replacement{'s' if e.replacements != 1 else ''}; lines {e.lines})")
    else:
        lines.append("- None")

    if apply and backup_dir:
        lines.extend(["", f"- Backups written to: `{backup_dir}`"])

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {report_path}")
    print(f"Files changed: {len(edits)}")
    print(f"Total replacements: {total_replacements}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
