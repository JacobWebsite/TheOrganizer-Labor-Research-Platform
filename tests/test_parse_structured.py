"""Tests for scripts/scraper/parse_structured.py -- no DB needed."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts', 'scraper'))

from parse_structured import (
    extract_from_tables,
    extract_from_lists,
    extract_pdf_links,
    clean_employer_name,
    guess_sector,
    classify_page_type,
)


# ── clean_employer_name ──────────────────────────────────────────────────

class TestCleanEmployerName:
    def test_valid_name(self):
        assert clean_employer_name("City of New York") == "City of New York"

    def test_strips_bullets(self):
        assert clean_employer_name("- City of Newark") == "City of Newark"

    def test_strips_asterisks(self):
        assert clean_employer_name("* County of Cook") == "County of Cook"

    def test_strips_numbering(self):
        assert clean_employer_name("1. State of Illinois") == "State of Illinois"

    def test_rejects_too_short(self):
        assert clean_employer_name("NYC") is None

    def test_rejects_too_long(self):
        assert clean_employer_name("A" * 121) is None

    def test_rejects_none(self):
        assert clean_employer_name(None) is None

    def test_rejects_empty(self):
        assert clean_employer_name("") is None

    def test_rejects_boilerplate(self):
        assert clean_employer_name("Click Here") is None
        assert clean_employer_name("read more") is None

    def test_rejects_all_digits(self):
        assert clean_employer_name("12345") is None

    def test_rejects_url(self):
        assert clean_employer_name("https://example.com") is None

    def test_strips_trailing_punctuation(self):
        assert clean_employer_name("City of Detroit,") == "City of Detroit"


# ── guess_sector ─────────────────────────────────────────────────────────

class TestGuessSector:
    def test_public_local(self):
        assert guess_sector("City of Chicago") == "PUBLIC_LOCAL"
        assert guess_sector("County of Los Angeles") == "PUBLIC_LOCAL"

    def test_public_state(self):
        assert guess_sector("State of California") == "PUBLIC_STATE"
        assert guess_sector("Department of Transportation") == "PUBLIC_STATE"

    def test_public_education(self):
        assert guess_sector("University of Michigan") == "PUBLIC_EDUCATION"
        assert guess_sector("Chicago School District 299") == "PUBLIC_EDUCATION"

    def test_healthcare(self):
        assert guess_sector("Memorial Hospital") == "HEALTHCARE"
        assert guess_sector("Regional Medical Center") == "HEALTHCARE"

    def test_public_federal(self):
        assert guess_sector("U.S. Postal Service") == "PUBLIC_FEDERAL"

    def test_private(self):
        assert guess_sector("Acme Corp") == "PRIVATE"
        assert guess_sector("Widget Inc") == "PRIVATE"

    def test_unknown(self):
        assert guess_sector("AFSCME Local 101") is None

    def test_none_input(self):
        assert guess_sector(None) is None


# ── classify_page_type ───────────────────────────────────────────────────

class TestClassifyPageType:
    def test_contracts(self):
        assert classify_page_type("https://example.com/contracts") == "contracts"
        assert classify_page_type("https://example.com/cba-list") == "contracts"

    def test_about(self):
        assert classify_page_type("https://example.com/about-us") == "about"

    def test_news(self):
        assert classify_page_type("https://example.com/blog") == "news"
        assert classify_page_type("https://example.com/press-releases") == "news"

    def test_members(self):
        assert classify_page_type("https://example.com/membership") == "members"

    def test_employers(self):
        assert classify_page_type("https://example.com/where-we-work") == "employers"

    def test_unknown(self):
        assert classify_page_type("https://example.com/xyz123") == "unknown"

    def test_title_override(self):
        assert classify_page_type("https://example.com/page1", "Our Contracts") == "contracts"


# ── extract_from_tables ──────────────────────────────────────────────────

class TestExtractFromTables:
    def test_basic_table(self):
        html = """
        <table>
            <thead><tr><th>Employer</th><th>Location</th></tr></thead>
            <tbody>
                <tr><td>City of Detroit</td><td>Michigan</td></tr>
                <tr><td>County of Wayne</td><td>Michigan</td></tr>
            </tbody>
        </table>
        """
        results = extract_from_tables(html)
        names = [r['employer_name'] for r in results]
        assert "City of Detroit" in names
        assert "County of Wayne" in names
        assert all(r['source_element'] == 'table_row' for r in results)

    def test_company_header(self):
        html = """
        <table>
            <tr><th>Company</th><th>Workers</th></tr>
            <tr><td>Acme Corp</td><td>500</td></tr>
        </table>
        """
        results = extract_from_tables(html)
        assert len(results) == 1
        assert results[0]['employer_name'] == "Acme Corp"

    def test_no_matching_header(self):
        html = """
        <table>
            <tr><th>Date</th><th>Amount</th></tr>
            <tr><td>2024-01-01</td><td>100</td></tr>
        </table>
        """
        results = extract_from_tables(html)
        assert len(results) == 0

    def test_deduplicates(self):
        html = """
        <table>
            <tr><th>Employer</th></tr>
            <tr><td>City of Detroit</td></tr>
            <tr><td>City of Detroit</td></tr>
        </table>
        """
        results = extract_from_tables(html)
        assert len(results) == 1

    def test_empty_html(self):
        assert extract_from_tables("") == []
        assert extract_from_tables(None) == []

    def test_rejects_short_names(self):
        html = """
        <table>
            <tr><th>Agency</th></tr>
            <tr><td>OK</td></tr>
            <tr><td>City of Flint</td></tr>
        </table>
        """
        results = extract_from_tables(html)
        assert len(results) == 1
        assert results[0]['employer_name'] == "City of Flint"


# ── extract_from_lists ───────────────────────────────────────────────────

class TestExtractFromLists:
    def test_basic_list(self):
        html = """
        <div class="content">
            <ul>
                <li>City of Detroit</li>
                <li>County of Wayne</li>
                <li>City of Flint</li>
                <li>University of Michigan</li>
            </ul>
        </div>
        """
        results = extract_from_lists(html)
        names = [r['employer_name'] for r in results]
        assert "City of Detroit" in names
        assert "County of Wayne" in names
        assert all(r['source_element'] == 'list_item' for r in results)

    def test_skips_nav_lists(self):
        html = """
        <nav>
            <ul>
                <li>City of Detroit</li>
                <li>County of Wayne</li>
                <li>City of Flint</li>
            </ul>
        </nav>
        """
        results = extract_from_lists(html)
        assert len(results) == 0

    def test_skips_short_lists(self):
        html = """
        <ul>
            <li>City of Detroit</li>
            <li>County of Wayne</li>
        </ul>
        """
        results = extract_from_lists(html)
        assert len(results) == 0  # < 3 items

    def test_skips_footer_class(self):
        html = """
        <div class="footer-nav">
            <ul>
                <li>City of Detroit</li>
                <li>County of Wayne</li>
                <li>City of Flint</li>
            </ul>
        </div>
        """
        results = extract_from_lists(html)
        assert len(results) == 0

    def test_empty(self):
        assert extract_from_lists("") == []
        assert extract_from_lists(None) == []


# ── extract_pdf_links ────────────────────────────────────────────────────

class TestExtractPdfLinks:
    def test_basic_pdf(self):
        html = '<a href="https://example.com/doc.pdf">My Document</a>'
        results = extract_pdf_links(html)
        assert len(results) == 1
        assert results[0]['pdf_url'] == "https://example.com/doc.pdf"
        assert results[0]['link_text'] == "My Document"
        assert results[0]['pdf_type'] == "other"

    def test_contract_pdf(self):
        html = '<a href="/files/contract-2024.pdf">2024 CBA Agreement</a>'
        results = extract_pdf_links(html, "https://union.org")
        assert len(results) == 1
        assert results[0]['pdf_url'] == "https://union.org/files/contract-2024.pdf"
        assert results[0]['pdf_type'] == "contract"

    def test_relative_url_resolution(self):
        html = '<a href="/docs/report.pdf">Report</a>'
        results = extract_pdf_links(html, "https://example.com/page")
        assert results[0]['pdf_url'] == "https://example.com/docs/report.pdf"

    def test_deduplicates(self):
        html = """
        <a href="/doc.pdf">Link 1</a>
        <a href="/doc.pdf">Link 2</a>
        """
        results = extract_pdf_links(html, "https://example.com")
        assert len(results) == 1

    def test_skips_non_pdf(self):
        html = '<a href="/page.html">Not a PDF</a>'
        results = extract_pdf_links(html)
        assert len(results) == 0

    def test_pdf_with_query_string(self):
        html = '<a href="/doc.pdf?v=2">Document</a>'
        results = extract_pdf_links(html, "https://example.com")
        assert len(results) == 1

    def test_empty(self):
        assert extract_pdf_links("") == []
        assert extract_pdf_links(None) == []

    def test_contract_in_url(self):
        html = '<a href="/agreements/cba-2024.pdf">Download</a>'
        results = extract_pdf_links(html, "https://union.org")
        assert results[0]['pdf_type'] == "contract"
