"""Pure-Python tests for the director-name filter.

The filter has both a Python predicate (`is_likely_real_director_name`)
and a SQL fragment (`SQL_FILTER_CLAUSE`). These tests cover the predicate
only — the SQL fragment is exercised end-to-end in test_directors_endpoint.py.
"""
from __future__ import annotations

from api.services.director_name_filter import (
    is_likely_real_director_name as ok,
    name_to_slug,
)


def test_clean_two_word_name_accepted():
    assert ok("Manuel Chavez")
    assert ok("Nancy Yao")


def test_name_with_middle_initial_accepted():
    assert ok("LeAnne M. Zumwalt")
    assert ok("R. Alex Rankin")
    assert ok("FRED M. DIAZ")
    assert ok("THOMAS E. CAPASSE")


def test_name_with_paren_suffix_accepted():
    # Real pattern in the data — Mergent footnote markers like "(3)"
    # carry through into the proxy tables. Don't reject.
    assert ok("Adam Portnoy (3)")


def test_single_word_rejected():
    assert not ok("Bill")
    assert not ok("Smith")


def test_empty_or_short_rejected():
    assert not ok("")
    assert not ok(None)
    assert not ok("A B")  # 3 chars total
    assert not ok("  ")


def test_first_word_title_fragment_rejected():
    assert not ok("Chief")  # single-word, but also bad-first-word
    assert not ok("Chief Financial Officer")
    assert not ok("President and")
    assert not ok("Senior")
    assert not ok("Vice")
    assert not ok("Audit")
    assert not ok("CEO and")  # 2026-05-05 added


def test_section_header_rejected():
    assert not ok("Continuing Directors")
    assert not ok("Independent Directors")
    assert not ok("Class I Directors")
    assert not ok("Outside Directors")


def test_proxy_statement_artifacts_rejected():
    # 2026-05-05: the parser was picking up running-header text
    # like these. Rejecting them is the year-regex + substring rules.
    assert not ok("DEF 14A")
    assert not ok("2026 Proxy Statement 15")
    assert not ok("12 2026 Proxy Statement")
    assert not ok("All directors and")
    assert not ok("Our Board of Directors")


def test_year_in_name_rejected():
    # Real names don't contain 4-digit years. Page-header artifacts do.
    assert not ok("John Smith 2024")
    assert not ok("2026 Proxy Statement")


def test_bio_paragraph_lead_rejected():
    assert not ok("Planner. Michael A. Wheeler")
    assert not ok("Treasurer and")


def test_entity_wrapper_rejected():
    assert not ok("Khosla Ventures, LLC (6)")


def test_overly_long_name_rejected():
    assert not ok("A" * 100)


def test_slug_basic_lowercase_with_hyphens():
    assert name_to_slug("Adam Portnoy") == "adam-portnoy"
    assert name_to_slug("Nancy Yao") == "nancy-yao"
    assert name_to_slug("Marcus L. Smith") == "marcus-l-smith"


def test_slug_strips_paren_suffix():
    # "Adam Portnoy (3)" and "Adam Portnoy" produce DIFFERENT slugs
    # — caller must aware. Documented in the endpoint docstring.
    assert name_to_slug("Adam Portnoy (3)") == "adam-portnoy-3"
    assert name_to_slug("Adam Portnoy") == "adam-portnoy"


def test_slug_handles_unicode_via_collapse():
    # Non-ASCII chars get collapsed to a hyphen (lossy but URL-safe).
    s = name_to_slug("Møller-Maersk")
    assert "-" in s
    assert s.lower() == s


def test_slug_strips_leading_trailing_hyphens():
    assert name_to_slug("  John  Smith  ") == "john-smith"
    assert name_to_slug("---X Y---") == "x-y"


def test_slug_empty_input():
    assert name_to_slug("") == ""
    assert name_to_slug(None) == ""
