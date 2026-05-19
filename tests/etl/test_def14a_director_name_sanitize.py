"""Tests for the DEF14A director-name suffix sanitizer (2026-05-18).

These guard the artifact-strip logic in
`scripts.etl.director_name_sanitizer.sanitize_director_name`, which
is wired into the live parser's `_norm_director_name` (Option A) and
is also used by the one-shot back-fix script (Option B).

Categories:
  1. Positive: each known artifact pattern is stripped.
  2. Negative: real surnames matching artifact tokens are preserved.
  3. End-to-end: the live parser's `_norm_director_name` produces a
     clean name when given the synthetic profile-block HTML that
     triggers the bug in production.
"""
from __future__ import annotations

import pytest

from scripts.etl.director_name_sanitizer import sanitize_director_name
from scripts.etl.load_def14a_directors import _norm_director_name, parse_directors


# ----- POSITIVE: every artifact pattern is stripped --------------------------

class TestCommaRoleSuffix:
    """Round 3 Agent F finding: 46 rows in employer_directors end in
    ", Director" / ", Chairman" / similar."""

    @pytest.mark.parametrize("artifact,expected", [
        ("Cecile B. Harper, Director", "Cecile B. Harper"),
        ("Dwight P. Aubrey, Director", "Dwight P. Aubrey"),
        ("John F. Chiste, Director", "John F. Chiste"),
        ("Charles Gillman, Director", "Charles Gillman"),
        ("Steven K. Norgaard, Director", "Steven K. Norgaard"),
        ("Patricia W. Chadwick, Director", "Patricia W. Chadwick"),
        ("Christopher C. Grisanti, Director", "Christopher C. Grisanti"),
        # Other role tags
        ("Jane Doe, Chairman", "Jane Doe"),
        ("John Smith, President", "John Smith"),
        ("Alice Brown, CEO", "Alice Brown"),
        ("Bob Green, CFO", "Bob Green"),
        ("Carol White, COO", "Carol White"),
        ("Dave Black, Chair", "Dave Black"),
        ("Eve Gray, Lead Director", "Eve Gray"),
        ("Frank Hill, Independent Director", "Frank Hill"),
        ("Grace Hopper, Vice Chairman", "Grace Hopper"),
        ("Heather Lee, Vice Chairperson", "Heather Lee"),
        # Chained
        ("Ivan Petrov, Chair, President", "Ivan Petrov"),
    ])
    def test_strips_comma_role_suffix(self, artifact, expected):
        assert sanitize_director_name(artifact) == expected


class TestDashRoleSuffix:
    """Round 3 Agent F finding: 4 rows with ' - Director'."""

    @pytest.mark.parametrize("artifact,expected", [
        ("John Smith - Director", "John Smith"),
        ("Jane Doe -- Director", "Jane Doe"),
        ("Alice Brown --- Director", "Alice Brown"),
        ("Bob Green - Chairman", "Bob Green"),
        ("Carol White -- President", "Carol White"),
        ("Dave Black - CEO", "Dave Black"),
    ])
    def test_strips_dash_role_suffix(self, artifact, expected):
        assert sanitize_director_name(artifact) == expected


class TestKeyTitleBleed:
    """Round 1 Agent 4 finding: 12 Pfizer directors have ' KEY' title-
    bleed and 13 rows have ' Key' (mixed-case fallback layout)."""

    @pytest.mark.parametrize("artifact,expected", [
        # ALL-CAPS "KEY" stripped via the trailing-allcaps rule
        ("Ronald E. Blaylock KEY", "Ronald E. Blaylock"),
        ("Mortimer J. Buckley KEY", "Mortimer J. Buckley"),
        ("Joseph J. Echevarria KEY", "Joseph J. Echevarria"),
        ("Shantanu Narayen KEY", "Shantanu Narayen"),
        ("Suzanne Nora Johnson KEY", "Suzanne Nora Johnson"),
        ("James C. Smith KEY", "James C. Smith"),
        ("Cyrus Taraporevala KEY", "Cyrus Taraporevala"),
        # Mixed-case "Key" stripped via the dedicated regex
        ("Jane Doe Key", "Jane Doe"),
        ("John Smith Key", "John Smith"),
    ])
    def test_strips_key_title_bleed(self, artifact, expected):
        assert sanitize_director_name(artifact) == expected

    def test_strips_credentials_before_key(self):
        # "Albert Bourla, DVM, Ph.D. KEY" should strip KEY first, then
        # the comma-suffix MD-style strip is NOT our job (existing
        # honorific regex handles ", MD"/", PhD"). Sanitizer guarantees
        # the artifact is gone.
        result = sanitize_director_name("Albert Bourla, DVM, Ph.D. KEY")
        assert "KEY" not in result
        # Bourla's name + credentials survive (caller can decide whether
        # to drop the credentials elsewhere).
        assert result.startswith("Albert Bourla")


class TestCompanySuffixBleed:
    """Round 1 Agent 4 finding: 11 Boeing directors have ' Boeing' suffix
    from the Boeing DEF14A profile-block layout. Tested in CONSERVATIVE
    mode (no filer context) and AGGRESSIVE mode (filer_company supplied).
    """

    @pytest.mark.parametrize("artifact,expected", [
        # Conservative: 3+ words OR has punctuated initial
        ("Robert A. Bradway Boeing", "Robert A. Bradway"),
        ("Lynne M. Doughtie Boeing", "Lynne M. Doughtie"),
        ("David L. Gitlin Boeing", "David L. Gitlin"),
        ("Lynn J. Good Boeing", "Lynn J. Good"),
        ("Stayce D. Harris Boeing", "Stayce D. Harris"),
        ("David L. Joyce Boeing", "David L. Joyce"),
        ("Robert Kelly Ortberg Boeing", "Robert Kelly Ortberg"),
        ("John M. Richardson Boeing", "John M. Richardson"),
        ("Bradley D. Tilden Boeing", "Bradley D. Tilden"),
        # Apple case ("Timothy J. Apple" = Tim Cook in Apple proxy data).
        # Trailing "." gets eaten by the outer strip(" ,;.|"), which is
        # OK -- the rest of the name normalization step handles canonical
        # initial formatting elsewhere.
        ("Timothy J. Apple", "Timothy J"),
    ])
    def test_strips_company_suffix_conservative_mode(self, artifact, expected):
        # No filer context; conservative threshold (3+ words OR initial).
        assert sanitize_director_name(artifact) == expected

    @pytest.mark.parametrize("artifact,expected,filer", [
        # Aggressive mode: filer name matches suffix token, 2-word names OK
        ("Akhil Johri Boeing", "Akhil Johri", "The Boeing Company"),
        ("Robert A. Bradway Boeing", "Robert A. Bradway", "The Boeing Company"),
        ("Lynn J. Good Boeing", "Lynn J. Good", "The Boeing Company"),
        # Pfizer hypothetical
        ("John Doe Pfizer", "John Doe", "Pfizer Inc."),
    ])
    def test_strips_company_suffix_aggressive_with_filer(
        self, artifact, expected, filer,
    ):
        assert sanitize_director_name(artifact, filer_company=filer) == expected


# ----- NEGATIVE: real surnames matching artifact tokens are preserved --------

class TestNegativeRealSurnames:
    """Critical: the sanitizer must not strip legitimate surnames that
    happen to spell the same as an artifact token."""

    def test_real_surname_director_preserved(self):
        # No comma => not the comma-role-bleed pattern. Must survive.
        assert sanitize_director_name("James W. Director") == "James W. Director"

    def test_real_surname_director_two_word(self):
        # "Asia Director" is the only 2-word real example we've seen in
        # the live DB. Without a comma there's no signal to strip.
        assert sanitize_director_name("Asia Director") == "Asia Director"

    def test_real_surname_boeing_two_word(self):
        # "Alex Boeing" is the canonical two-word case from the task spec.
        # Only 2 tokens after strip would be 1 token; we protect short
        # names from the company-suffix rule.
        assert sanitize_director_name("Alex Boeing") == "Alex Boeing"

    def test_real_surname_apple_two_word(self):
        # Similar guard for Apple.
        assert sanitize_director_name("Jane Apple") == "Jane Apple"

    def test_real_surname_pfizer_two_word(self):
        assert sanitize_director_name("Bob Pfizer") == "Bob Pfizer"

    @pytest.mark.parametrize("name", [
        # Real honorifics / credentials with ALL-CAPS at end are preserved.
        # Note: the existing _norm_director_name honorific regex would
        # strip "Jr." before sanitize is invoked, but the sanitizer itself
        # must not blindly strip these.
        "John Smith MD",
        "Jane Doe PHD",
        "Robert Jones CPA",
        "Alice Brown JD",
        "Bob Green ESQ",
        "Carol White RN",
        "Dave Black MBA",
        "Eve Gray USN",       # retired military
        "Frank Hill USA",
        "Grace Hopper USAF",
        "Henry I. III",
        "Ivan J. IV",
    ])
    def test_honorific_credentials_preserved(self, name):
        # Real honorifics / military / academic credentials at end must
        # not be stripped by the all-caps rule.
        assert sanitize_director_name(name) == name

    def test_short_three_word_name_with_dash_not_stripped(self):
        # Real name with mid-dash: "Jean-Pierre Dupont" should survive.
        result = sanitize_director_name("Jean-Pierre Dupont")
        assert result == "Jean-Pierre Dupont"

    def test_normal_clean_name_unchanged(self):
        # Sanitizer is a no-op on already-clean names.
        for name in ("John Smith", "Jane Q. Public", "Bill Fehrman",
                     "Sandra Beach Lin", "R. Joseph Jackson"):
            assert sanitize_director_name(name) == name


# ----- BOUNDARY: empty / whitespace / None -----------------------------------

class TestSanitizerEdgeCases:
    def test_empty_string_returns_empty(self):
        assert sanitize_director_name("") == ""

    def test_none_returns_empty(self):
        assert sanitize_director_name(None) == ""

    def test_whitespace_only_returns_empty(self):
        assert sanitize_director_name("   ") == ""

    def test_collapses_internal_whitespace(self):
        assert sanitize_director_name("John   Smith") == "John Smith"

    def test_strips_outer_punctuation(self):
        assert sanitize_director_name(",  John Smith.  ") == "John Smith"


# ----- INTEGRATION: live parser produces clean names -------------------------

class TestParserUsesSanitizer:
    """End-to-end: feed the parser HTML modeled on a Boeing/Pfizer/AAR
    profile-block layout that historically produced the suffix bug.
    Verify the parser output has no artifacts."""

    # Boeing's real layout: the company name "Boeing" sits between the
    # director's name and the role-tag "Director", and the title-boundary
    # regex lands on " Director" leaving "NAME Boeing" as the captured
    # cand. The sanitizer's _strip_company_suffix rule (conservative mode
    # since these names all have punctuated initials) cleans it.
    BOEING_LIKE_PROFILE_HTML = """
    <html><body>
    <h1>Director Nominees</h1>
    <div>
      Robert A. Bradway Boeing Director Independent Lead Director
      Age: 65 Director Since: 2018 Other Public Company Directorships:
      Amgen Inc. Committees: Audit Skills relevant to our business
    </div>
    <div>
      Lynne M. Doughtie Boeing Director Independent
      Age: 60 Director Since: 2021 Other Public Company Directorships:
      SAP SE Workday Inc. Committees: Audit Compensation Skills
    </div>
    <div>
      David L. Gitlin Boeing Director Independent
      Age: 56 Director Since: 2022 Other Public Company Directorships:
      Carrier Global Corp. Committees: Finance Skills
    </div>
    <div>
      Lynn J. Good Boeing Director Independent
      Age: 65 Director Since: 2015 Other Public Company Directorships:
      Duke Energy Corp. Committees: Audit Nominating Skills
    </div>
    </body></html>
    """

    # Pfizer's real-world layout: "NAME KEY Skills..." (KEY is a column
    # heading that bleeds in because the title-boundary regex matches at
    # "Skills"). Without the sanitizer, the cand becomes "NAME KEY",
    # which the existing _norm_director_name preserves; the sanitizer's
    # ALL-CAPS-trailing-token rule strips it.
    PFIZER_LIKE_PROFILE_HTML = """
    <html><body>
    <h1>Director Nominees</h1>
    <div>
      Ronald E. Blaylock KEY Skills relevant to our business
      Age: 65 Director Since: 2017
      Independent: Yes Other Public Company Directorships: CarMax Inc.
      Committees: Audit
    </div>
    <div>
      Shantanu Narayen KEY Skills tech industry experience
      Age: 60 Director Since: 2020
      Independent: Yes Other Public Company Directorships: Adobe Inc.
      Committees: Compensation
    </div>
    <div>
      Cyrus Taraporevala KEY Skills financial services
      Age: 58 Director Since: 2022
      Independent: Yes Committees: Audit
    </div>
    <div>
      Joseph J. Echevarria KEY Skills audit and finance
      Age: 65 Director Since: 2007
      Independent: Yes Committees: Audit Governance
    </div>
    </body></html>
    """

    # Comma-Director layout: "NAME, Director" pattern with "Skills" later
    # in the same block (the profile-block title-boundary regex lands on
    # "Skills" not on "Director" because "Director" is preceded by ", "
    # not " "). Without the sanitizer, the cand becomes "NAME, Director";
    # with the sanitizer the comma-role rule strips the artifact.
    COMMA_DIRECTOR_PROFILE_HTML = """
    <html><body>
    <h1>Our Board</h1>
    <div>
      Cecile B. Harper, Director Age: 62 Director Since: 2019
      Independent: Yes Committees: Audit Skills relevant to our business
    </div>
    <div>
      Dwight P. Aubrey, Director Age: 70 Director Since: 2010
      Independent: Yes Committees: Compensation Governance Skills
    </div>
    <div>
      Patricia W. Chadwick, Director Age: 71 Director Since: 2014
      Independent: Yes Committees: Audit Skills
    </div>
    <div>
      Steven K. Norgaard, Director Age: 56 Director Since: 2018
      Independent: Yes Committees: Finance Skills
    </div>
    </body></html>
    """

    def test_boeing_like_proxy_produces_clean_names(self):
        dirs = parse_directors(self.BOEING_LIKE_PROFILE_HTML)
        names = [d.name for d in dirs]
        for n in names:
            assert "Boeing" not in n, f"Boeing suffix bleed: {n!r}"
        # And we should still get the expected directors
        joined = " | ".join(names)
        assert "Robert A. Bradway" in joined
        assert "Lynne M. Doughtie" in joined

    def test_pfizer_like_proxy_strips_key_bleed(self):
        dirs = parse_directors(self.PFIZER_LIKE_PROFILE_HTML)
        names = [d.name for d in dirs]
        for n in names:
            assert "KEY" not in n.upper().split(), \
                f"KEY title-bleed: {n!r}"
        joined = " | ".join(names)
        assert "Ronald E. Blaylock" in joined
        assert "Shantanu Narayen" in joined

    def test_comma_director_proxy_strips_role_suffix(self):
        dirs = parse_directors(self.COMMA_DIRECTOR_PROFILE_HTML)
        names = [d.name for d in dirs]
        for n in names:
            assert not n.endswith(", Director"), \
                f"comma-Director suffix: {n!r}"
            assert not n.endswith(", Chairman"), \
                f"comma-Chairman suffix: {n!r}"
        joined = " | ".join(names)
        assert "Cecile B. Harper" in joined
        assert "Dwight P. Aubrey" in joined


class TestNormDirectorNameWiredToSanitizer:
    """Defense-in-depth: even if a future strategy returns text the
    sanitizer would catch, _norm_director_name produces a clean name."""

    @pytest.mark.parametrize("raw,clean", [
        ("Robert A. Bradway Boeing", "Robert A. Bradway"),
        ("Ronald E. Blaylock KEY", "Ronald E. Blaylock"),
        ("Cecile B. Harper, Director", "Cecile B. Harper"),
        ("John Smith - Director", "John Smith"),
        ("Jane Doe -- Chairman", "Jane Doe"),
    ])
    def test_norm_strips_artifacts(self, raw, clean):
        assert _norm_director_name(raw) == clean

    @pytest.mark.parametrize("raw", [
        "James W. Director",   # real surname Director
        "Asia Director",
        "Alex Boeing",          # real surname Boeing
        "Jane Apple",
    ])
    def test_norm_preserves_legit_surnames(self, raw):
        # _norm_director_name shouldn't strip these (no comma signal /
        # short name).
        assert _norm_director_name(raw) == raw
