"""
Smoke checks for migrated scopes (verify + maintenance).
"""
from __future__ import annotations

from pathlib import Path
import sys
import importlib.util


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from db_config import get_connection  # noqa: E402


SCOPES = ["scripts/verify", "scripts/maintenance"]
MIGRATOR_PATH = ROOT / "scripts" / "analysis" / "migrate_to_db_config_connection.py"
SPEC = importlib.util.spec_from_file_location("migrator", MIGRATOR_PATH)
MIGRATOR = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
# Python 3.14: register module in sys.modules before exec so @dataclass can resolve it
sys.modules["migrator"] = MIGRATOR
SPEC.loader.exec_module(MIGRATOR)


def check_scope(scope: str) -> tuple[int, int]:
    scope_path = ROOT / scope
    total = 0
    pending = 0
    include_prefixes = [scope.replace("\\", "/")]
    for path in scope_path.rglob("*.py"):
        total += 1
        text = path.read_text(encoding="utf-8")
        if not MIGRATOR.should_scan(path, include_prefixes):
            continue
        _new_text, replacements, _lines = MIGRATOR.migrate_text(text)
        if replacements > 0:
            pending += 1
    return total, pending


def main() -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        _ = cur.fetchone()
    finally:
        conn.close()

    failures = 0
    for scope in SCOPES:
        total, pending = check_scope(scope)
        print(f"{scope}: files={total}, pending_migrations={pending}")
        if pending > 0:
            failures += 1

    if failures:
        print("Smoke check failed")
        return 1
    print("Smoke check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
