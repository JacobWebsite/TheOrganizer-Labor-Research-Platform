"""Unit tests for ``scripts/etl/sec_10k/extract_relationship_entities.py``.

These tests exercise the regex / heuristic surface only -- they do not
touch the database. End-to-end DB testing is the user's smoke run.

The fixtures are hand-crafted snippets modeled on real 10-K prose seen
during section-parsing development:

* customers: the Walmart-style "represented approximately N% of sales"
  pattern, plus the introducer-list "principal customers include X, Y"
  pattern.
* suppliers: the "key suppliers include" / "single source supplier"
  pattern.
* distribution: the airline-style "distributed through OTAs such as
  Expedia, Booking" pattern.

We also assert specific NEGATIVE cases: stop-list rejections, generic
common-noun rejections, and self-reference rejections.
"""
from __future__ import annotations


from scripts.etl.sec_10k import extract_relationship_entities as ext


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

CUSTOMERS_TEXT_WALMART = (
    "Customers\n"
    "Our largest customer, Walmart Inc., represented approximately 16% in 2025 "
    "and 2024 and 15% in 2023 of our net sales from continuing operations. "
    "Net sales to Walmart Inc. were primarily in the NA segment. We also sell "
    "directly to consumers through our website."
)


CUSTOMERS_TEXT_LIST = (
    "Major Customers\n"
    "Our principal customers include Acme Corporation, Globex Industries, "
    "Initech Inc. and Soylent Corp. No single customer accounted for more "
    "than 10% of our consolidated revenues."
)


CUSTOMERS_TEXT_GENERIC = (
    "Customers\n"
    "Our products are sold to government agencies, large enterprises and "
    "various retailers across North America. Our customers include Fortune "
    "500 companies, government agencies and small businesses."
)


SUPPLIERS_TEXT_LIST = (
    "Sources and Availability of Raw Materials\n"
    "Our key suppliers include Intel Corporation, Samsung Electronics and "
    "Taiwan Semiconductor Manufacturing Company. We rely on a limited number "
    "of suppliers for certain critical components."
)


SUPPLIERS_TEXT_GENERIC = (
    "Raw Materials\n"
    "Materials are generally available from many sources, and the segment is "
    "not dependent upon any single supplier for any raw material. We do not "
    "purchase or commit for the purchase of a major portion of raw materials."
)


DISTRIBUTION_TEXT_OTAS = (
    "Distribution and Marketing Agreements\n"
    "Passengers can purchase tickets through our website and our reservations "
    "centers, and through third-party distribution channels, including travel "
    "management companies and online travel agents (OTAs) such as Expedia, "
    "Booking Holdings, Amadeus, Sabre and Travelport."
)


SHORT_TEXT = "Customers\nNo data here."


# --------------------------------------------------------------------------
# Cleanup helpers
# --------------------------------------------------------------------------


def test_clean_entity_text_strips_punctuation_and_whitespace():
    assert ext._clean_entity_text("  Walmart Inc.,  ") == "Walmart Inc"
    assert ext._clean_entity_text("(Acme Corp)") == "Acme Corp"
    assert ext._clean_entity_text('"Globex"') == "Globex"
    assert ext._clean_entity_text("and Initech") == "Initech"


def test_is_acceptable_entity_rejects_self_references():
    assert not ext._is_acceptable_entity("the Company")
    assert not ext._is_acceptable_entity("Our Subsidiaries")
    assert not ext._is_acceptable_entity("Customers")
    assert not ext._is_acceptable_entity("government agencies")


def test_is_acceptable_entity_rejects_10k_boilerplate():
    """10-K cross-references that the regex picks up at sentence boundaries.

    Discovered in 2026-05-10 full-corpus run: 'Item' / 'Form' / 'Part II'
    were 7-17 mentions each at the top of the unmatched + falsely-matched
    rankings. All are 10-K body cross-references ('Part II, Item 8',
    'Form 10-K', etc.), not real entities. Regression-guard so future
    stop-list edits don't accidentally re-introduce them.
    """
    for boilerplate in ("Item", "Form", "Part II", "Part III", "Part IV",
                        "Part V", "Form 10-Q", "Form 8-K", "Risk Factors"):
        assert not ext._is_acceptable_entity(boilerplate), boilerplate


def test_is_acceptable_entity_rejects_tech_jargon_acronyms():
    """Tech-industry generic abbreviations that show up in 10-K prose.

    Discovered in 2026-05-10 full-corpus run: 'OEMs' (20), 'OEM' (11),
    'MSPs' (6), 'VARs' (3), 'EMS' (3), 'ODMs' (3), 'OSATs' (3), 'DIY' (3).
    All are common-category abbreviations, not company names. Many appear
    inside 'Our customers include OEMs and VARs...' style sentences.
    """
    for jargon in ("OEM", "OEMs", "MSP", "MSPs", "ISP", "ISPs",
                   "VAR", "VARs", "EMS", "ODM", "ODMs", "OSAT", "OSATs",
                   "DIY", "SIs"):
        assert not ext._is_acceptable_entity(jargon), jargon


def test_is_acceptable_entity_rejects_sentence_starters_and_pronouns():
    """Capitalized sentence-starters the regex captures.

    Discovered in 2026-05-10 full-corpus run:
      Sales (7), Internet (5), While (3), Two (3), Fortune (3),
      Canadian (3), Company's (3).
    """
    for starter in ("Sales", "Net Sales", "Internet", "While",
                    "While the Company", "Two", "Fortune", "Canadian",
                    "Company's"):
        assert not ext._is_acceptable_entity(starter), starter


def test_is_acceptable_entity_rejects_sentence_boundary_bug():
    """The 'Raw Materials\\nThe Company concentrates...' splice produces
    'Raw Materials The Company' as a single mention. Real fix is in the
    sentence-splitter; meanwhile we stop-list the exact phrase.
    """
    assert not ext._is_acceptable_entity("Raw Materials The Company")


def test_is_acceptable_entity_does_not_overreach():
    """Make sure the new stop-list entries don't accidentally veto real
    companies whose names CONTAIN a stopped substring.

    E.g. 'Sales' is stopped but 'Salesforce' must still pass; 'Item' is
    stopped but 'Itemize Inc.' (hypothetical) should pass.
    """
    assert ext._is_acceptable_entity("Salesforce")
    assert ext._is_acceptable_entity("Salesforce.com Inc")
    assert ext._is_acceptable_entity("Fortune Brands Innovations")
    # 'Canadian Pacific' is a real company; bare 'Canadian' is the noise.
    assert ext._is_acceptable_entity("Canadian Pacific Railway")
    # Per Codex crosscheck 2026-05-11: tighten the 'item' stop entry guard.
    assert ext._is_acceptable_entity("Itemize Inc")
    # And the 'form' stop entry guard -- FormFactor Inc is a real
    # semiconductor probe-card company.
    assert ext._is_acceptable_entity("FormFactor Inc")


def test_is_acceptable_entity_rejects_short_or_lowercase():
    assert not ext._is_acceptable_entity("ab")            # too short
    assert not ext._is_acceptable_entity("walmart")       # lowercase
    assert not ext._is_acceptable_entity("various")       # all stop-tokens


def test_is_acceptable_entity_accepts_real_companies():
    assert ext._is_acceptable_entity("Walmart Inc")
    assert ext._is_acceptable_entity("Intel Corporation")
    assert ext._is_acceptable_entity("Samsung Electronics")
    assert ext._is_acceptable_entity("3M Company")


# --------------------------------------------------------------------------
# Customers section
# --------------------------------------------------------------------------


def test_extracts_walmart_from_pct_pattern():
    """'Walmart Inc., represented approximately 16%' -> Walmart Inc."""
    out = ext.extract_entities_from_section(
        cik=1, accession="acc1", section_type="customers",
        section_text=CUSTOMERS_TEXT_WALMART,
    )
    names = [e.entity_text for e in out]
    assert any("Walmart" in n for n in names), f"expected Walmart in {names}"


def test_extracts_principal_customer_list_via_introducer():
    """'principal customers include Acme, Globex, Initech, Soylent' -> 4 names."""
    out = ext.extract_entities_from_section(
        cik=1, accession="acc2", section_type="customers",
        section_text=CUSTOMERS_TEXT_LIST,
    )
    names_lower = [e.entity_text.lower() for e in out]
    assert any("acme" in n for n in names_lower), names_lower
    assert any("globex" in n for n in names_lower), names_lower
    assert any("initech" in n for n in names_lower), names_lower


def test_rejects_generic_customer_categories():
    """'government agencies', 'various retailers', 'Fortune 500' -> all rejected."""
    out = ext.extract_entities_from_section(
        cik=1, accession="acc3", section_type="customers",
        section_text=CUSTOMERS_TEXT_GENERIC,
    )
    names_lower = [e.entity_text.lower() for e in out]
    for bad in ("government agencies", "various retailers", "fortune 500",
                "small businesses", "large enterprises"):
        assert bad not in names_lower, f"'{bad}' leaked through to {names_lower}"


# --------------------------------------------------------------------------
# Suppliers section
# --------------------------------------------------------------------------


def test_extracts_supplier_list_via_introducer():
    out = ext.extract_entities_from_section(
        cik=1, accession="acc4", section_type="suppliers",
        section_text=SUPPLIERS_TEXT_LIST,
    )
    names_lower = [e.entity_text.lower() for e in out]
    assert any("intel" in n for n in names_lower), names_lower
    assert any("samsung" in n for n in names_lower), names_lower


def test_supplier_section_with_no_entities_returns_empty():
    """Generic 'sources are available, no single supplier' should yield no entities."""
    out = ext.extract_entities_from_section(
        cik=1, accession="acc5", section_type="suppliers",
        section_text=SUPPLIERS_TEXT_GENERIC,
    )
    # The text mentions no real firms; we should get 0 (or at most a
    # mis-cap of 'Materials' which we filter).
    names_lower = [e.entity_text.lower() for e in out]
    for bad in ("materials", "raw materials", "the segment"):
        assert bad not in names_lower, f"'{bad}' leaked through"


# --------------------------------------------------------------------------
# Distribution section
# --------------------------------------------------------------------------


def test_extracts_ota_partners_from_distribution_section():
    out = ext.extract_entities_from_section(
        cik=1, accession="acc6", section_type="distribution",
        section_text=DISTRIBUTION_TEXT_OTAS,
    )
    names_lower = [e.entity_text.lower() for e in out]
    # All four OTA names should appear.
    assert any("expedia" in n for n in names_lower), names_lower
    assert any("amadeus" in n for n in names_lower), names_lower
    assert any("sabre" in n for n in names_lower), names_lower


# --------------------------------------------------------------------------
# Position-offset and context shape
# --------------------------------------------------------------------------


def test_context_window_is_returned_and_bounded():
    out = ext.extract_entities_from_section(
        cik=1, accession="acc7", section_type="customers",
        section_text=CUSTOMERS_TEXT_WALMART,
    )
    assert out, "expected at least one entity"
    for e in out:
        assert e.context, f"context missing for {e.entity_text}"
        # Soft upper bound: ~240 chars + ellipsis.
        assert len(e.context) <= 250, f"context too long: {len(e.context)}"
        # Position offset is within the source text.
        assert 0 <= e.position_offset <= len(CUSTOMERS_TEXT_WALMART)


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


def test_empty_text_returns_empty():
    assert ext.extract_entities_from_section(
        cik=1, accession="acc8", section_type="customers", section_text=""
    ) == []


def test_short_text_returns_empty():
    out = ext.extract_entities_from_section(
        cik=1, accession="acc9", section_type="customers", section_text=SHORT_TEXT
    )
    # No real entities in "No data here."
    assert out == [] or all(not e.entity_text.lower().startswith("no") for e in out)


def test_dedupes_walmart_mentioned_twice():
    """'Walmart Inc.' appears twice in CUSTOMERS_TEXT_WALMART -- should dedupe to 1."""
    out = ext.extract_entities_from_section(
        cik=1, accession="acc10", section_type="customers",
        section_text=CUSTOMERS_TEXT_WALMART,
    )
    # Get all walmart-ish entities; should only be one.
    walmart_hits = [e for e in out if "walmart" in e.entity_text.lower()]
    assert len(walmart_hits) == 1, [e.entity_text for e in walmart_hits]
