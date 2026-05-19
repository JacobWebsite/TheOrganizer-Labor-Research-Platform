"""Tests for ``scripts/etl/sec_10k/parse_10k_sections.py``.

The 10-K test corpus is synthetic HTML modeled on actual 10-K layouts:

* IBM-style: a table-of-contents block at the top whose ``Item 1.``/``Item
  1A.`` lines look very similar to the body section headers, plus body
  prose later. The parser must pick the *body* match, not the TOC entry.
* AT&T-style: the body header is uppercase (``ITEM 1.``) on its own line,
  followed by a section title on the next line.

The DB-write side is exercised at the SQL-string level only; end-to-end
DB testing is the verification step in the parser's docstring.
"""
from __future__ import annotations


from scripts.etl.sec_10k import parse_10k_sections as parser


# --------------------------------------------------------------------------
# Synthetic fixtures
# --------------------------------------------------------------------------

# IBM-style TOC + body.
# Note: the TOC has every item header tightly packed (small gap to next item);
# the body Item 1 has thousands of chars before Item 1A.
_BUSINESS_FILLER = ("Acme Corp is a leading manufacturer of widgets. " * 200)
_RISK_FILLER = ("The following risk factors should be considered carefully. " * 200)

IBM_STYLE_HTML = (
    "<html><body>"
    "<div>Table of Contents</div>"
    "<div>PART I</div>"
    "<table><tr><td>Item 1. Business</td><td>1</td></tr>"
    "<tr><td>Item 1A. Risk Factors</td><td>3</td></tr>"
    "<tr><td>Item 1B. Unresolved Staff Comments</td><td>10</td></tr>"
    "<tr><td>Item 2. Properties</td><td>11</td></tr>"
    "<tr><td>Item 3. Legal Proceedings</td><td>11</td></tr>"
    "<tr><td>Item 4. Mine Safety Disclosures</td><td>11</td></tr></table>"
    "<div>PART I</div>"
    "<h2>Item 1. Business</h2>"
    "<p>" + _BUSINESS_FILLER +
    "Our principal customers include Fortune 500 enterprises across the "
    "United States.</p>"
    "<h3>Customers</h3>"
    "<p>No single customer accounted for more than 10% of our consolidated "
    "revenues in fiscal 2025. Our top five customers in aggregate represented "
    "approximately 22% of consolidated revenue.</p>"
    "<h3>Suppliers</h3>"
    "<p>We rely on a limited number of suppliers for certain critical "
    "components. Our largest supplier provided approximately 18% of total "
    "purchased materials.</p>"
    "<h3>Distribution</h3>"
    "<p>We distribute our products through a combination of direct sales, "
    "third-party resellers, and online channels.</p>"
    "<h2>Item 1A. Risk Factors</h2>"
    "<p>" + _RISK_FILLER +
    "We depend on third-party suppliers for a significant portion of our "
    "components. Any disruption could materially affect our business.</p>"
    "<h2>Item 1B. Unresolved Staff Comments</h2>"
    "<p>Not applicable.</p>"
    "<h2>Item 2. Properties</h2>"
    "<p>Our principal executive offices are located in Armonk, NY.</p>"
    "</body></html>"
)


# AT&T-style: ITEM headers in uppercase, on their own lines.
_ATT_BUSINESS_FILLER = ("AT&amp;T Inc. is a holding company. " * 100)
_ATT_RISK_FILLER = ("We face numerous risks. " * 200)

ATT_STYLE_HTML = (
    "<html><body>"
    "<div>Table of Contents</div>"
    "<div>"
    "Item 1. Business 1 "
    "Item 1A. Risk Factors 5 "
    "Item 1B. Unresolved Staff Comments 10 "
    "Item 2. Properties 11"
    "</div>"
    "<div>"
    "ITEM 1.<br/>BUSINESS<br/>GENERAL<br/>" + _ATT_BUSINESS_FILLER +
    "<br/><br/>MAJOR CUSTOMERS<br/>"
    "No customer accounted for 10% or more of our consolidated revenues. "
    "Our top three customers represented approximately 12% of revenue.<br/>"
    "<br/>COMPETITION<br/>"
    "Competition continues to increase for communications and digital services."
    "</div>"
    "<div>ITEM 1A.<br/>RISK FACTORS<br/>" + _ATT_RISK_FILLER +
    "Our customers are subject to economic cycles. We depend on our "
    "suppliers for network equipment.</div>"
    "<div>ITEM 2.<br/>PROPERTIES<br/>Our properties are described.</div>"
    "</body></html>"
)


# Malformed HTML: empty body, just a tag soup. Parser must not crash.
MALFORMED_HTML = "<html><body></body></html>"

# Tiny document: well-formed but no item structure at all.
TINY_NO_ITEMS = "<html><body><p>This document does not contain any items.</p></body></html>"


# --------------------------------------------------------------------------
# Section regex finds Item 1 / Item 1A
# --------------------------------------------------------------------------


def test_finds_business_section_in_ibm_style_toc_and_body():
    """Parser must pick the body Item 1, not the TOC line of the same name."""
    parsed = parser.parse_filing(
        cik=51143, accession="000005114326000010", html=IBM_STYLE_HTML
    )
    assert parsed.error is None
    assert parser.SECTION_BUSINESS in parsed.sections
    body = parsed.sections[parser.SECTION_BUSINESS]
    # Body must be substantial (the TOC entry itself is ~20 chars).
    assert len(body) > 1000, f"body suspiciously short: {len(body)} chars"
    # The body must contain the prose, not just headers.
    assert "Acme Corp is a leading manufacturer" in body


def test_finds_risk_factors_section_in_ibm_style():
    parsed = parser.parse_filing(
        cik=51143, accession="000005114326000010", html=IBM_STYLE_HTML
    )
    assert parser.SECTION_RISK_FACTORS in parsed.sections
    rf = parsed.sections[parser.SECTION_RISK_FACTORS]
    assert len(rf) > 500
    assert "risk factors should be considered" in rf
    # And the Item 1A section must NOT spill into Item 1B.
    assert "Properties" not in rf or rf.find("Properties") > rf.find("third-party suppliers")


def test_finds_business_section_in_att_uppercase_style():
    """Uppercase ``ITEM 1.``-on-its-own-line layout (AT&T pattern)."""
    parsed = parser.parse_filing(
        cik=732717, accession="000073271726000120", html=ATT_STYLE_HTML
    )
    assert parser.SECTION_BUSINESS in parsed.sections
    body = parsed.sections[parser.SECTION_BUSINESS]
    assert "AT&T Inc." in body
    assert len(body) > 1000


# --------------------------------------------------------------------------
# Sub-heading detection
# --------------------------------------------------------------------------


def test_detects_customers_subsection_inside_item_1():
    parsed = parser.parse_filing(
        cik=51143, accession="000005114326000010", html=IBM_STYLE_HTML
    )
    assert parser.SECTION_CUSTOMERS in parsed.sections
    cust = parsed.sections[parser.SECTION_CUSTOMERS]
    assert "10%" in cust
    assert "consolidated revenues" in cust


def test_detects_suppliers_subsection_inside_item_1():
    parsed = parser.parse_filing(
        cik=51143, accession="000005114326000010", html=IBM_STYLE_HTML
    )
    assert parser.SECTION_SUPPLIERS in parsed.sections
    sup = parsed.sections[parser.SECTION_SUPPLIERS]
    assert "supplier" in sup.lower()


def test_detects_distribution_subsection_inside_item_1():
    parsed = parser.parse_filing(
        cik=51143, accession="000005114326000010", html=IBM_STYLE_HTML
    )
    assert parser.SECTION_DISTRIBUTION in parsed.sections
    dist = parsed.sections[parser.SECTION_DISTRIBUTION]
    assert "direct sales" in dist or "resellers" in dist or "channels" in dist


def test_detects_major_customers_in_att_style():
    """AT&T uses ``MAJOR CUSTOMERS`` (uppercase) as the sub-heading."""
    parsed = parser.parse_filing(
        cik=732717, accession="000073271726000120", html=ATT_STYLE_HTML
    )
    assert parser.SECTION_CUSTOMERS in parsed.sections
    cust = parsed.sections[parser.SECTION_CUSTOMERS]
    assert "10% or more" in cust


# --------------------------------------------------------------------------
# HTML cleanup preserves paragraph breaks
# --------------------------------------------------------------------------


def test_html_to_clean_text_strips_script_and_style():
    html = (
        "<html><head>"
        "<script>console.log('hidden');</script>"
        "<style>body { color: red; }</style>"
        "</head><body><p>visible content</p></body></html>"
    )
    text = parser.html_to_clean_text(html)
    assert "visible content" in text
    assert "console.log" not in text
    assert "color: red" not in text


def test_html_to_clean_text_preserves_paragraph_breaks():
    """Multiple <p> tags should produce a multi-line plain-text result."""
    html = "<html><body><p>First paragraph.</p><p>Second paragraph.</p><p>Third paragraph.</p></body></html>"
    text = parser.html_to_clean_text(html)
    lines = [ln for ln in text.split("\n") if ln.strip()]
    # We expect at least one line per paragraph.
    assert len(lines) >= 3
    assert any("First paragraph" in ln for ln in lines)
    assert any("Second paragraph" in ln for ln in lines)
    assert any("Third paragraph" in ln for ln in lines)


def test_html_to_clean_text_collapses_whitespace_within_lines():
    html = "<html><body><p>Word1   Word2\t\tWord3</p></body></html>"
    text = parser.html_to_clean_text(html)
    assert "Word1 Word2 Word3" in text


# --------------------------------------------------------------------------
# Resumability / target selection
# --------------------------------------------------------------------------


def test_select_downloaded_includes_cached_status():
    """The downloader marks resumed runs ``cached``; we must pick those up."""
    assert "'downloaded'" in parser.SELECT_DOWNLOADED
    assert "'cached'" in parser.SELECT_DOWNLOADED


def test_existing_parsed_query_used_for_resumability():
    """The resumable path must filter rows already in ``sec_10k_sections``."""
    assert "FROM sec_10k_sections" in parser.EXISTING_PARSED_CIKS


def test_upsert_uses_on_conflict_do_update():
    """Re-parses must overwrite (not append) for the same (cik, accession, section)."""
    assert "ON CONFLICT (cik, accession, section) DO UPDATE" in parser.UPSERT_SECTION


# --------------------------------------------------------------------------
# Malformed / empty document handling
# --------------------------------------------------------------------------


def test_malformed_empty_html_does_not_crash():
    parsed = parser.parse_filing(cik=1, accession="x", html=MALFORMED_HTML)
    # No crash; returns a ParsedFiling with an error string and zero sections.
    assert parsed.cik == 1
    assert parsed.sections == {}
    assert parsed.error is not None  # short-text or no-content message


def test_completely_blank_html_returns_error_not_exception():
    parsed = parser.parse_filing(cik=1, accession="x", html="")
    assert parsed.sections == {}
    assert parsed.error is not None


def test_document_without_item_structure_returns_no_sections():
    """A 10-K that's just plain text with no item headers should yield zero
    sections rather than crash. The error field is allowed to be empty here
    since the HTML *was* parseable -- we just couldn't find item headers."""
    parsed = parser.parse_filing(cik=1, accession="x", html=TINY_NO_ITEMS)
    # Either: error on too-short text, OR sections empty with no error.
    if parsed.error is None:
        assert parsed.sections == {}


# --------------------------------------------------------------------------
# find_section_body helper
# --------------------------------------------------------------------------


def test_find_section_body_returns_none_when_no_candidate_qualifies():
    """A document with item headers tightly packed (TOC only) must not return
    a 'body' -- the gap between Item 1 and Item 1A is below min_body_chars."""
    text = (
        "Item 1. Business\n1\n"
        "Item 1A. Risk Factors\n3\n"
        "Item 2. Properties\n11\n"
    )
    assert parser.find_section_body(text, "1") is None


def test_find_section_body_picks_largest_gap_match():
    """Two ``Item 1.`` matches: one tight TOC, one body. Body wins."""
    body_padding = "x" * 5000
    text = (
        "Item 1. Business\n1\n"   # TOC
        "Item 1A. Risk Factors\n3\n"
        "Item 2. Properties\n11\n"
        "PART I\n"
        "Item 1. Business\n"      # Body header
        + body_padding
        + "\nItem 1A. Risk Factors\n"
        + ("y" * 5000)
        + "\nItem 2. Properties\nshort\n"
    )
    loc = parser.find_section_body(text, "1")
    assert loc is not None
    start, end = loc
    # Must be the body header, not the TOC. The body header sits after
    # the TOC + Item 2 + PART I marker, so its position > 50.
    assert start > 50
    assert end - start >= 5000


# --------------------------------------------------------------------------
# DDL contains expected columns
# --------------------------------------------------------------------------


def test_ddl_has_expected_columns_and_pk():
    ddl = parser.DDL_SECTIONS
    for col in ("cik", "accession", "section", "text", "char_count", "parsed_at"):
        assert col in ddl, f"DDL missing column {col}"
    assert "PRIMARY KEY (cik, accession, section)" in ddl


def test_all_sections_constant_lists_six_keys():
    """Future-proof: if someone adds a section type we must update both ends."""
    assert len(parser.ALL_SECTIONS) == 6
    expected = {"business", "risk_factors", "customers", "suppliers", "distribution", "partners"}
    assert set(parser.ALL_SECTIONS) == expected
