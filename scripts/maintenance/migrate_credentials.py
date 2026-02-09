"""
One-time migration script: remove hardcoded DB password from all project files.
Replaces DB_CONFIG blocks with shared db_config import.
Replaces inline password references in markdown.
"""
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASSWORD = os.environ.get('DB_PASSWORD', '')  # Migration already run 2026-02-09
SKIP_FILES = {
    os.path.join(PROJECT_ROOT, '.env'),
    os.path.join(PROJECT_ROOT, 'db_config.py'),
    os.path.join(PROJECT_ROOT, 'scripts', 'maintenance', 'migrate_credentials.py'),
}

# Pattern: multi-line DB_CONFIG = { ... 'password': '...' ... }
DB_CONFIG_BLOCK = re.compile(
    r"DB_CONFIG\s*=\s*\{[^}]*?'password'\s*:\s*'[^']*'[^}]*\}",
    re.DOTALL
)

# Pattern: psycopg2.connect(host=..., password='...', ...)
CONNECT_INLINE = re.compile(
    r"psycopg2\.connect\([^)]*password\s*=\s*['\"][^'\"]*['\"][^)]*\)",
    re.DOTALL
)

# Simple password string
PASSWORD_STR = re.compile(re.escape(PASSWORD))

IMPORT_LINE = "import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * {depth}))); from db_config import DB_CONFIG"

DB_CONFIG_REPLACEMENT = """DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}"""

stats = {"py_config_replaced": 0, "py_password_replaced": 0, "md_replaced": 0, "skipped": 0, "errors": 0}

def get_depth(filepath):
    """How many '..' needed to reach project root from this file's directory."""
    rel = os.path.relpath(os.path.dirname(filepath), PROJECT_ROOT)
    if rel == '.':
        return 0
    return len(rel.replace('\\', '/').split('/'))

def fix_python_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    if PASSWORD not in content:
        return False

    original = content
    depth = get_depth(filepath)

    # Case 1: Has DB_CONFIG block - replace with env-var version + add os import
    if DB_CONFIG_BLOCK.search(content):
        content = DB_CONFIG_BLOCK.sub(DB_CONFIG_REPLACEMENT, content)
        # Make sure 'import os' exists
        if 'import os' not in content:
            # Add after the last top-level import
            lines = content.split('\n')
            last_import = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    last_import = i
            lines.insert(last_import + 1, 'import os')
            content = '\n'.join(lines)
        stats["py_config_replaced"] += 1

    # Case 2: Still has password somewhere (inline connect, comments, etc.)
    if PASSWORD in content:
        content = content.replace(PASSWORD, "os.environ.get('DB_PASSWORD', '')")
        if 'import os' not in content:
            content = 'import os\n' + content
        stats["py_password_replaced"] += 1

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def fix_markdown_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    if PASSWORD not in content:
        return False

    new_content = content.replace(PASSWORD, '<password in .env file>')

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        stats["md_replaced"] += 1
        return True
    return False

def main():
    fixed_files = []

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip .git, __pycache__, archive
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.claude'}]

        for fname in files:
            filepath = os.path.join(root, fname)

            if filepath in SKIP_FILES:
                stats["skipped"] += 1
                continue

            try:
                if fname.endswith('.py'):
                    if fix_python_file(filepath):
                        fixed_files.append(filepath)
                elif fname.endswith('.md'):
                    if fix_markdown_file(filepath):
                        fixed_files.append(filepath)
            except Exception as e:
                print(f"  ERROR: {filepath}: {e}")
                stats["errors"] += 1

    print(f"\n=== Credential Migration Complete ===")
    print(f"Python DB_CONFIG blocks replaced: {stats['py_config_replaced']}")
    print(f"Python inline passwords replaced: {stats['py_password_replaced']}")
    print(f"Markdown files cleaned: {stats['md_replaced']}")
    print(f"Files skipped: {stats['skipped']}")
    print(f"Errors: {stats['errors']}")
    print(f"\nTotal files modified: {len(fixed_files)}")

    if fixed_files:
        print(f"\nModified files:")
        for f in sorted(fixed_files):
            rel = os.path.relpath(f, PROJECT_ROOT)
            print(f"  {rel}")

if __name__ == '__main__':
    main()
