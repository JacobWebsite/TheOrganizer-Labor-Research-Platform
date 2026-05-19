"""Tests for the Haiku batch verdict-parser helpers in
scripts/llm_dedup/submit_anthropic_batch.py and submit_validation_batch.py.

Regression target: the 2026-04-21 validation batch (39,127 rows) was silently
written to CSV as all ``verdict=UNKNOWN`` / ``reason=''`` because the v2.0
validation prompt returns ``label`` + ``reasoning`` while the parser only
looked for ``verdict`` + ``reason``. The fix extracted the inline logic into
``parse_verdict_obj()`` and made it schema-tolerant. These tests pin that
behavior so a future schema change doesn't silently corrupt another batch.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LLM_DEDUP_DIR = REPO_ROOT / "scripts" / "llm_dedup"


def _load(module_name: str):
    """Import a module from scripts/llm_dedup by adding the dir to sys.path
    and importing by file-name. We don't import via dotted path because the
    submit_* scripts run as standalone CLIs and don't sit inside a package.

    The ``anthropic`` SDK is imported at module top-level; if it's not
    installed locally the import will fail and the test skips.
    """
    sys.path.insert(0, str(LLM_DEDUP_DIR))
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"cannot import {module_name}: {exc}")


@pytest.fixture(scope="module")
def parse_validation():
    mod = _load("submit_validation_batch")
    return mod.parse_verdict_obj


@pytest.fixture(scope="module")
def parse_anthropic():
    mod = _load("submit_anthropic_batch")
    return mod.parse_verdict_obj


# ---------------------------------------------------------------------------
# Bad-input pattern: v2.0 schema (label + reasoning) — the exact pattern
# that produced 39,127 silent UNKNOWN rows before the fix.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_v2_validation_schema_parsed_correctly(parser_fixture, request):
    """v2.0 prompt returns ``label`` + ``reasoning``. Pre-fix, the parser
    returned ``UNKNOWN`` / ``''`` for every v2.0 row. After the fix, both
    fields are extracted."""
    parse = request.getfixturevalue(parser_fixture)
    v2_obj = {"label": "DUPLICATE", "confidence": "high", "reasoning": "shared EIN"}
    verdict, confidence, reason = parse(v2_obj)
    assert verdict == "DUPLICATE"
    assert confidence == "high"
    assert reason == "shared EIN"


@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_v2_all_six_validation_labels(parser_fixture, request):
    """The v2.0 prompt's full label set: DUPLICATE / RELATED / PARENT_CHILD /
    SIBLING / UNRELATED / BROKEN. Each must round-trip."""
    parse = request.getfixturevalue(parser_fixture)
    for label in ("DUPLICATE", "RELATED", "PARENT_CHILD", "SIBLING", "UNRELATED", "BROKEN"):
        verdict, _, _ = parse({"label": label, "confidence": "med", "reasoning": "ok"})
        assert verdict == label


# ---------------------------------------------------------------------------
# v1.0 schema (verdict + reason) — must still work after the fix.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_v1_dedup_schema_still_works(parser_fixture, request):
    """v1.0 prompt returns ``verdict`` + ``reason``. The fix must remain
    backwards compatible with v1.0 outputs (the dedup batch CSV consumers
    rely on this)."""
    parse = request.getfixturevalue(parser_fixture)
    v1_obj = {"verdict": "DUPLICATE", "confidence": "high", "reason": "same EIN"}
    verdict, confidence, reason = parse(v1_obj)
    assert verdict == "DUPLICATE"
    assert confidence == "high"
    assert reason == "same EIN"


# ---------------------------------------------------------------------------
# Edge cases: missing keys, mixed schemas, empty / non-dict input.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_missing_keys_fall_back_to_unknown(parser_fixture, request):
    parse = request.getfixturevalue(parser_fixture)
    verdict, confidence, reason = parse({})
    assert verdict == "UNKNOWN"
    assert confidence == "UNKNOWN"
    assert reason == ""


@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_non_dict_input_is_safe(parser_fixture, request):
    """If json.loads happens to produce a list / string / None, the parser
    must not raise. Returns the all-UNKNOWN sentinel."""
    parse = request.getfixturevalue(parser_fixture)
    for bad in (None, [], "not a dict", 42):
        verdict, confidence, reason = parse(bad)
        assert verdict == "UNKNOWN"
        assert confidence == "UNKNOWN"
        assert reason == ""


@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_label_takes_precedence_over_verdict_on_mixed_payload(parser_fixture, request):
    """If a payload somehow contains BOTH keys (e.g. a transitional prompt),
    ``label`` wins so v2.0 results aren't shadowed by a stale v1.0 default."""
    parse = request.getfixturevalue(parser_fixture)
    verdict, _, reason = parse({
        "label": "RELATED",
        "verdict": "DUPLICATE",
        "reasoning": "v2 reason",
        "reason": "v1 reason",
    })
    assert verdict == "RELATED"
    assert reason == "v2 reason"


@pytest.mark.parametrize("parser_fixture", ["parse_validation", "parse_anthropic"])
def test_empty_string_label_falls_through_to_verdict(parser_fixture, request):
    """An empty-string ``label`` is falsy, so the ``or`` chain falls through
    to ``verdict``. This protects against partially-formed Haiku output
    where the v2.0 key exists but is blank."""
    parse = request.getfixturevalue(parser_fixture)
    verdict, _, _ = parse({"label": "", "verdict": "DUPLICATE"})
    assert verdict == "DUPLICATE"
