import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.python.matching.name_normalization import (  # noqa: E402
    normalize_name_aggressive,
    normalize_name_fuzzy,
    normalize_name_standard,
)


def test_standard_keeps_core_tokens():
    assert normalize_name_standard("WAL-MART STORES, INC.") == "wal mart stores inc"


def test_standard_removes_dba_tail():
    assert normalize_name_standard("Acme LLC DBA Midtown Labs") == "acme llc"


def test_aggressive_removes_legal_suffixes():
    assert normalize_name_aggressive("Acme Corporation, LLC") == "acme"


def test_aggressive_removes_common_noise_tokens():
    assert normalize_name_aggressive("The Acme Services Group") == "acme"


def test_fuzzy_is_order_insensitive():
    a = normalize_name_fuzzy("Global Logistics Partners")
    b = normalize_name_fuzzy("Partners Global Logistics")
    assert a == b


def test_fuzzy_ascii_folds():
    assert normalize_name_fuzzy("Caf\u00e9 Internacional, Inc.") == "cafe internacional"

