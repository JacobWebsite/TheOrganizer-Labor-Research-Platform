"""Unit tests for the BoardCard quality audit helpers.

Only tests the pure-function helpers; the DB-touching checks are
exercised by running the script directly (the audit itself is the
integration test).

Canonical source of the audit script: originated on
``ship/2026-05-11-q16-19-rollup``. Both this test file and
``scripts/research/audit_boardcard_quality.py`` were cherry-picked
to master on 2026-05-18 via ``ship/2026-05-18-fix-test-collection-error``
to clear a collection error (the test file existed in the working tree
but the script it imported did not). When the q16-19 rollup merges,
the canonical copy will be the merge result; no action needed here.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the audit module by file path -- it lives under scripts/research/
# which isn't a normal package import path.
_THIS = Path(__file__).resolve()
_PROJECT = _THIS.parent.parent.parent
_SCRIPT = _PROJECT / "scripts" / "research" / "audit_boardcard_quality.py"
sys.path.insert(0, str(_PROJECT))
spec = importlib.util.spec_from_file_location("audit_boardcard_quality", _SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(audit)


class TestAccessionYearParser:
    """SEC accession numbers encode the filing year in positions 10-12.
    Format: NNNNNNNNNN-YY-NNNNNN -- 10 chars filer, 2 chars year, 6 chars seq.
    Separators may or may not be present.
    """

    def test_parses_2026_accession_number(self):
        # Real example from employer_directors (Bowser, Hasbro)
        assert audit._accession_year("000119312526160426") == 2026

    def test_parses_dashed_form(self):
        assert audit._accession_year("0001193125-26-160426") == 2026

    def test_year_threshold_below_50_is_2000s(self):
        assert audit._accession_year("000123456724000001") == 2024

    def test_year_threshold_at_50_is_1900s(self):
        # Year 50 -> 1950 by our cutoff
        assert audit._accession_year("000123456750000001") == 1950
        # Year 99 -> 1999
        assert audit._accession_year("000123456799000001") == 1999

    def test_returns_none_on_short_input(self):
        assert audit._accession_year("12345") is None

    def test_returns_none_on_none(self):
        assert audit._accession_year(None) is None

    def test_returns_none_on_empty(self):
        assert audit._accession_year("") is None

    def test_strips_non_digits(self):
        # Mixed format from CSV / Excel mangling
        assert audit._accession_year("0001193125-26-160426  ") == 2026


class TestSuspectReasons:
    """`_suspect_reasons` flags surface heuristics that suggest a name
    might be parser garbage even if it passes the main filter."""

    def test_real_name_has_no_reasons(self):
        assert audit._suspect_reasons("Jane M. Smith") == []

    def test_chief_token_flagged(self):
        reasons = audit._suspect_reasons("Joe Cantie Director")
        assert "contains_chief_token" in reasons

    def test_corp_suffix_flagged(self):
        reasons = audit._suspect_reasons("Acme Capital Inc")
        assert "ends_in_corp_suffix" in reasons

    def test_all_caps_flagged(self):
        # Real all-caps director names exist (e.g., "ROBERT GLASER")
        # so the heuristic is meant to trigger a review, not auto-reject.
        reasons = audit._suspect_reasons("ROBERT GLASER")
        assert "all_caps_token" in reasons

    def test_committee_word_flagged(self):
        reasons = audit._suspect_reasons("Audit Committee Chair")
        assert "contains_committee_word" in reasons

    def test_single_word_flagged(self):
        reasons = audit._suspect_reasons("Kennedy")
        assert "single_word" in reasons

    def test_very_short_flagged(self):
        reasons = audit._suspect_reasons("AB")
        # "AB" -> 1 token -> single_word + very_short
        assert "very_short" in reasons


class TestSuspectPatternList:
    """The SUSPECT_PATTERNS list is what drives the false-positive
    sample. Make sure the regexes don't match obvious real names."""

    @pytest.mark.parametrize(
        "name",
        [
            "John Smith",
            "Jane M. Doe",
            "Robert K. Wilson Jr.",
            "Mary-Ann O'Brien",
            "LeAnne M. Zumwalt",
        ],
    )
    def test_clean_real_names_have_no_matches(self, name):
        # Some patterns are LEGITIMATELY noisy (all_caps_token, single_word)
        # but the clean Title-Case names above shouldn't trip ANY of them.
        reasons = audit._suspect_reasons(name)
        # Allow `contains_phd_or_md_only` to appear -- that pattern is
        # benign-but-flag-for-review by design.
        non_benign = [r for r in reasons if r != "contains_phd_or_md_only"]
        assert non_benign == [], f"unexpected flags on {name}: {non_benign}"
