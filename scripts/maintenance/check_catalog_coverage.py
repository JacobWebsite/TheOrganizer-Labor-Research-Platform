"""
Check PROJECT_CATALOG.md coverage against actual filesystem.

Usage:
    py scripts/maintenance/check_catalog_coverage.py
"""
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CATALOG_PATH = os.path.join(PROJECT_ROOT, 'PROJECT_CATALOG.md')

# Directories to scan for active project files
SCAN_DIRS = [
    'scripts',
    'api',
    'frontend',
    'tests',
    'sql',
    'src',
    'config',
    '.claude',
]

# Directories to exclude entirely
EXCLUDE_DIRS = {
    'archive',
    'node_modules',
    '__pycache__',
    '.git',
    'dist',
    '.pip_cache',
    '.pip_tmp',
    '.pytest_cache',
    '.vite',
    'docs',
    'memory',
}

# Subdirectory paths to exclude (normalized with forward slashes)
EXCLUDE_SUBPATHS = [
    '.claude/memory',
    '.claude/projects',
]

# File extensions to track, by directory context
CODE_EXTENSIONS = {'.py', '.jsx', '.js', '.css', '.sql', '.bat'}

# Special files that are tracked regardless of directory
SPECIAL_FILES = {'cba_search.html'}

# Root-level files to track
ROOT_FILES = {'db_config.py'}


def normalize_path(p):
    """Normalize a path to use forward slashes and strip leading ./"""
    p = p.replace('\\', '/')
    if p.startswith('./'):
        p = p[2:]
    return p


def parse_catalog_paths(catalog_text):
    """Extract backtick-delimited file paths from markdown table rows."""
    paths = set()
    # Match backtick-delimited paths that look like project files
    # Patterns: scripts/..., api/..., frontend/..., tests/..., sql/..., src/...,
    #           config/..., .claude/..., db_config.py, etc.
    # Excludes data/ directory paths (tracked as directory summaries, not individual files)
    pattern = re.compile(
        r'`('
        r'(?:scripts|api|frontend|tests|sql|src|config|\.claude)'
        r'/[^`]+'
        r'|db_config\.py'
        r')`'
    )
    for line in catalog_text.splitlines():
        # Only look at lines that are part of markdown tables (contain |)
        if '|' not in line:
            continue
        for match in pattern.finditer(line):
            raw = match.group(1)
            normalized = normalize_path(raw)
            # Strip trailing characters that are not part of the path
            normalized = normalized.rstrip(',;:')
            # Skip bare directory references (ending with /)
            if normalized.endswith('/'):
                continue
            paths.add(normalized)
    return paths


def should_exclude_dir(dirpath_rel):
    """Check whether a relative directory path should be excluded."""
    parts = dirpath_rel.replace('\\', '/').split('/')
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    norm = normalize_path(dirpath_rel)
    for subpath in EXCLUDE_SUBPATHS:
        if norm == subpath or norm.startswith(subpath + '/'):
            return True
    return False


def should_include_file(filepath_rel):
    """Determine if a file should be tracked based on extension and location."""
    norm = normalize_path(filepath_rel)
    basename = os.path.basename(norm)
    _, ext = os.path.splitext(basename)

    # Special files by name
    if basename in SPECIAL_FILES:
        return True

    # Root-level files
    if '/' not in norm and basename in ROOT_FILES:
        return True

    # Standard code extensions
    if ext in CODE_EXTENSIONS:
        return True

    # .json files only in config/
    if ext == '.json' and norm.startswith('config/'):
        return True

    # .md files in specific subdirectories
    if ext == '.md':
        if (norm.startswith('.claude/agents/')
                or norm.startswith('.claude/specs/')
                or norm.startswith('.claude/skills/')
                or norm.startswith('scripts/analysis/demographics_comparison/')
                or norm.startswith('config/')):
            return True

    # .html files -- only cba_search.html (handled by SPECIAL_FILES above)
    # .bat files already in CODE_EXTENSIONS

    return False


def collect_disk_files():
    """Walk project directories and collect all relevant files."""
    disk_files = set()

    # Scan root-level files
    for f in ROOT_FILES:
        full = os.path.join(PROJECT_ROOT, f)
        if os.path.isfile(full):
            disk_files.add(f)

    # Scan each directory
    for scan_dir in SCAN_DIRS:
        abs_dir = os.path.join(PROJECT_ROOT, scan_dir)
        if not os.path.isdir(abs_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(abs_dir):
            rel_dir = os.path.relpath(dirpath, PROJECT_ROOT)
            if should_exclude_dir(rel_dir):
                dirnames[:] = []  # prune walk
                continue
            # Prune excluded subdirectories
            dirnames[:] = [
                d for d in dirnames
                if not should_exclude_dir(os.path.join(rel_dir, d))
            ]
            for fname in filenames:
                rel_file = normalize_path(os.path.join(rel_dir, fname))
                if should_include_file(rel_file):
                    disk_files.add(rel_file)

    return disk_files


def check_coverage():
    """Main coverage check logic."""
    print("=" * 64)
    print("  PROJECT CATALOG COVERAGE CHECK")
    print("=" * 64)

    # Read catalog
    if not os.path.isfile(CATALOG_PATH):
        print("\n  [ERROR] PROJECT_CATALOG.md not found at project root.")
        print(f"  Expected: {CATALOG_PATH}")
        return 1

    with open(CATALOG_PATH, 'r', encoding='utf-8') as f:
        catalog_text = f.read()

    catalog_paths = parse_catalog_paths(catalog_text)
    disk_files = collect_disk_files()

    print(f"\n  Catalog entries:  {len(catalog_paths)}")
    print(f"  Disk files:       {len(disk_files)}")

    # Files in catalog but missing from disk
    missing_from_disk = sorted(catalog_paths - disk_files)

    # Files on disk but missing from catalog
    missing_from_catalog = sorted(disk_files - catalog_paths)

    drift = False

    # Report missing from disk
    print(f"\n  IN CATALOG BUT MISSING FROM DISK ({len(missing_from_disk)}):")
    if missing_from_disk:
        drift = True
        for p in missing_from_disk:
            print(f"    [-] {p}")
    else:
        print("    (none)")

    # Report missing from catalog
    print(f"\n  ON DISK BUT MISSING FROM CATALOG ({len(missing_from_catalog)}):")
    if missing_from_catalog:
        drift = True
        for p in missing_from_catalog:
            print(f"    [+] {p}")
    else:
        print("    (none)")

    # Summary
    print()
    print("-" * 64)
    if drift:
        total = len(missing_from_disk) + len(missing_from_catalog)
        print(f"  DRIFT DETECTED: {total} discrepancies found.")
        print(f"    {len(missing_from_disk)} cataloged files missing from disk")
        print(f"    {len(missing_from_catalog)} disk files missing from catalog")
    else:
        print("  CLEAN: Catalog matches filesystem. No drift detected.")
    print("-" * 64)
    print()

    return 1 if drift else 0


def main():
    result = check_coverage()
    sys.exit(result)


if __name__ == '__main__':
    main()
