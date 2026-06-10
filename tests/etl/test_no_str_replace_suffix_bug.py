"""CI guard: prevent regression of the Mergent loader str.replace suffix bug.

The bug pattern (see Open Problems/Pfizer Master Canonical Name Corruption.md):

    for suffix in [' llc', ' inc', ' corp', ' ltd', ' co', ' company',
                   ' corporation', ...]:
        name = name.replace(suffix, '')

Because ``str.replace`` has no word boundaries and the list ordering puts the
shorter suffix first (`' corp'` before `' corporation'`), the loop eats the
shorter suffix out of the middle of the longer one. ~19,140 rows of
``master_employers.canonical_name`` got corrupted before this was caught.

This test AST-scans every ``scripts/etl/load_mergent_*.py`` file and FAILS
if any of them contains a ``name.replace(suffix, '')`` call inside a loop
over a list-literal of suffix-like strings. Use the canonical token-based
normalizer (``src.python.matching.name_normalization``) instead.
"""
import ast
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


SUFFIX_INDICATOR_RE = re.compile(
    r"^\s*(llc|inc|corp|corporation|ltd|limited|co|company|incorporated)\s*$",
    re.IGNORECASE,
)


def _is_suffix_list_literal(node):
    """Return True if `node` is a list of string literals where ANY element
    is a known legal suffix (with optional leading space).
    """
    if not isinstance(node, (ast.List, ast.Tuple)):
        return False
    found_any = False
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            stripped = elt.value.strip()
            if SUFFIX_INDICATOR_RE.match(stripped):
                found_any = True
    return found_any


def _walk_for_bug_pattern(tree):
    """Yield (lineno, message) for each `for suffix in [...]: x.replace(suffix, '')` pattern."""
    findings = []
    for node in ast.walk(tree):
        # Looking for `for <var> in <list-of-suffixes>: ...`
        if not isinstance(node, ast.For):
            continue
        if not _is_suffix_list_literal(node.iter):
            continue
        loop_var = node.target.id if isinstance(node.target, ast.Name) else None
        if not loop_var:
            continue
        # Walk the body for `<x>.replace(<loop_var>, '')`
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if not (isinstance(func, ast.Attribute) and func.attr == "replace"):
                continue
            if not inner.args:
                continue
            first_arg = inner.args[0]
            if isinstance(first_arg, ast.Name) and first_arg.id == loop_var:
                findings.append((
                    inner.lineno,
                    f"str.replace({loop_var}, ...) inside loop over suffix-list "
                    f"literal at line {node.lineno} -- this is the Pfizer "
                    f"normalize_name bug. Use "
                    f"src.python.matching.name_normalization."
                    f"normalize_name_legal_suffixes_only instead.",
                ))
    return findings


def _mergent_loader_paths():
    etl_dir = ROOT / "scripts" / "etl"
    return sorted(etl_dir.glob("load_mergent_*.py"))


def test_at_least_one_mergent_loader_exists():
    """Sanity: the test only protects what it can see."""
    paths = _mergent_loader_paths()
    assert paths, "No load_mergent_*.py files found -- test infrastructure broken?"


@pytest.mark.parametrize(
    "loader_path",
    _mergent_loader_paths(),
    ids=lambda p: p.name,
)
def test_no_str_replace_suffix_bug(loader_path):
    """Each loader must NOT contain the str.replace-in-suffix-loop bug pattern."""
    source = loader_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(loader_path))
    findings = _walk_for_bug_pattern(tree)
    if findings:
        msg = (
            f"\nBUG REGRESSION in {loader_path.name}:\n"
            + "\n".join(f"  line {ln}: {m}" for ln, m in findings)
            + "\n\nSee Open Problems/Pfizer Master Canonical Name Corruption.md"
        )
        pytest.fail(msg)


def test_loader_imports_canonical_normalizer_function_local():
    """Both loaders should reference the canonical normalizer name.

    Function-local imports show up as `from ... import normalize_name_legal_suffixes_only`
    inside the function body, not at module top. We just check the
    name is present in the source text.
    """
    for path in _mergent_loader_paths():
        source = path.read_text(encoding="utf-8")
        assert "normalize_name_legal_suffixes_only" in source, (
            f"{path.name} does not reference the canonical normalizer; "
            "did you forget to swap the buggy implementation?"
        )


# ============================================================================
# AST self-test: the detector must catch the buggy snippet
# ============================================================================

def test_detector_catches_known_buggy_snippet():
    """Self-test the AST walker so we know the regression guard actually works."""
    buggy_src = (
        "def normalize_name(name):\n"
        "    name = str(name).lower().strip()\n"
        "    for suffix in [' llc', ' inc', ' corp', ' ltd', ' co', ' company',\n"
        "                   ' corporation', ' incorporated', ' limited']:\n"
        "        name = name.replace(suffix, '')\n"
        "    return name\n"
    )
    tree = ast.parse(buggy_src)
    findings = _walk_for_bug_pattern(tree)
    assert findings, "Detector failed to flag the canonical buggy pattern"


def test_detector_does_not_false_positive_on_safe_replace():
    """Replacing something other than the loop var must NOT trigger."""
    safe_src = (
        "def f(s):\n"
        "    for suffix in [' llc', ' inc']:\n"
        "        s = s.replace(',', '')  # this is fine; replacing a literal\n"
        "    return s\n"
    )
    tree = ast.parse(safe_src)
    findings = _walk_for_bug_pattern(tree)
    assert not findings, "False positive on safe str.replace pattern"


def test_detector_does_not_flag_loop_over_non_suffix_list():
    """A loop over a list of non-suffix strings must NOT trigger."""
    safe_src = (
        "def f(s):\n"
        "    for word in ['hello', 'world', 'foo']:\n"
        "        s = s.replace(word, '')\n"
        "    return s\n"
    )
    tree = ast.parse(safe_src)
    findings = _walk_for_bug_pattern(tree)
    assert not findings, "False positive on non-suffix word list"
