"""Tests for _resolve_action_id (R7 audit -- action_id traceability for facts).

Three resolution strategies must all work; an unresolvable name returns None.
"""
from __future__ import annotations

from scripts.research.agent import _resolve_action_id


TOOL_MAP = {
    "search_osha": 101,
    "search_nlrb": 102,
    "search_whd": 103,
    "scrape_employer_website": 104,
    "search_company_enrich": 105,
}


def test_exact_match_wins():
    assert _resolve_action_id("search_osha", TOOL_MAP) == 101


def test_substring_match_recovers_tool_in_source_name():
    # LLM emits "OSHA via search_osha tool" -- substring strategy catches it
    assert _resolve_action_id("OSHA via search_osha tool", TOOL_MAP) == 101


def test_reverse_substring_recovers_short_token():
    # LLM emits 'osha' as a bare source_name; reverse-substring matches it
    # against 'search_osha'
    assert _resolve_action_id("osha", TOOL_MAP) == 101


def test_case_insensitive_substring():
    assert _resolve_action_id("CompanyEnrich response", {"search_company_enrich": 7}) is not None


def test_unknown_returns_none():
    assert _resolve_action_id("Wikipedia article", TOOL_MAP) is None
    assert _resolve_action_id("press release", TOOL_MAP) is None


def test_empty_inputs_return_none():
    assert _resolve_action_id(None, TOOL_MAP) is None
    assert _resolve_action_id("", TOOL_MAP) is None
    assert _resolve_action_id("search_osha", {}) is None


def test_short_source_name_does_not_false_match_via_reverse_substring():
    # Two-char strings would match too aggressively against tool names; the
    # >=3 char minimum guards against this.
    assert _resolve_action_id("ab", TOOL_MAP) is None
