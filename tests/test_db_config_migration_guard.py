"""
Guard test: previously migrated scopes should remain clean under dry-run migrator.
"""
from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parent.parent

_MIGRATOR_PATH = ROOT / "scripts" / "analysis" / "migrate_to_db_config_connection.py"
_SPEC = importlib.util.spec_from_file_location("migrator", _MIGRATOR_PATH)
_MIGRATOR = importlib.util.module_from_spec(_SPEC)
# Python 3.14: register module in sys.modules before exec so @dataclass can resolve it
sys.modules["migrator"] = _MIGRATOR
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_MIGRATOR)


def _count_pending(prefix: str) -> int:
    include_prefixes = [prefix.replace("\\", "/").rstrip("/")]
    pending = 0
    for path in ROOT.rglob("*.py"):
        if not _MIGRATOR.should_scan(path, include_prefixes):
            continue
        text = path.read_text(encoding="utf-8")
        _new_text, replacements, _lines = _MIGRATOR.migrate_text(text)
        if replacements > 0:
            pending += 1
    return pending


def test_verify_scope_remains_migrated():
    assert _count_pending("scripts/verify") == 0


def test_maintenance_scope_remains_migrated():
    assert _count_pending("scripts/maintenance") == 0
