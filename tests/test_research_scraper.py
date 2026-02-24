"""
Tests for the research agent employer website scraper.

All Crawl4AI interactions are mocked — no network or browser needed.
"""
import sys
import os
import types as builtin_types
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers to build mock Crawl4AI results
# ---------------------------------------------------------------------------

def _make_crawl_result(success=True, markdown_text="", error_message=None):
    """Build a mock CrawlResult with .success and .markdown.raw_markdown."""
    result = MagicMock()
    result.success = success
    result.error_message = error_message
    if markdown_text:
        result.markdown = MagicMock()
        result.markdown.raw_markdown = markdown_text
    else:
        result.markdown = None
    return result


def _build_fake_crawl4ai():
    """Build a fake crawl4ai module with AsyncWebCrawler, configs, and CacheMode."""
    mod = builtin_types.ModuleType("crawl4ai")
    mod.BrowserConfig = MagicMock
    mod.CrawlerRunConfig = MagicMock
    mod.CacheMode = MagicMock()
    mod.CacheMode.BYPASS = "BYPASS"

    class FakeAsyncWebCrawler:
        def __init__(self, *a, **kw):
            self._results = kw.pop("_results", {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def arun(self, url="", config=None, **kw):
            # Check for exact URL match first, then prefix match
            if url in self._results:
                return self._results[url]
            # Default: 404
            return _make_crawl_result(success=False, error_message="404 Not Found")

    mod.AsyncWebCrawler = FakeAsyncWebCrawler
    return mod


# ---------------------------------------------------------------------------
# URL Normalisation
# ---------------------------------------------------------------------------

class TestNormalizeUrl:
    def test_uppercase_no_scheme(self):
        from scripts.research.tools import _normalize_url
        assert _normalize_url("WWW.EXAMPLE.COM") == "https://www.example.com"

    def test_with_scheme(self):
        from scripts.research.tools import _normalize_url
        assert _normalize_url("http://example.com/") == "http://example.com"

    def test_na_returns_none(self):
        from scripts.research.tools import _normalize_url
        assert _normalize_url("N/A") is None
        assert _normalize_url("nan") is None
        assert _normalize_url("") is None
        assert _normalize_url(None) is None


# ---------------------------------------------------------------------------
# URL Resolution
# ---------------------------------------------------------------------------

class TestResolveEmployerUrl:
    def test_provided_url_used_directly(self):
        from scripts.research.tools import _resolve_employer_url
        url, source = _resolve_employer_url("Acme Corp", url="https://acme.com")
        assert url == "https://acme.com"
        assert source == "provided"

    def test_provided_url_normalised(self):
        from scripts.research.tools import _resolve_employer_url
        url, source = _resolve_employer_url("Acme Corp", url="WWW.ACME.COM")
        assert url == "https://www.acme.com"
        assert source == "provided"

    @patch("scripts.research.tools._conn")
    def test_mergent_employer_id_lookup(self, mock_conn):
        """Tier 2: employer_id -> unified_match_log -> mergent_employers.website."""
        from scripts.research.tools import _resolve_employer_url

        mock_cur = MagicMock()
        mock_cur.fetchone = MagicMock(side_effect=[
            {"source_id": "DUNS123"},      # unified_match_log hit
            {"website": "WWW.EXAMPLE.COM"},  # mergent_employers hit
        ])
        mock_conn.return_value.cursor.return_value = mock_cur

        url, source = _resolve_employer_url("Example Inc", employer_id="emp123")
        assert url == "https://www.example.com"
        assert source == "mergent_db"

    @patch("scripts.research.tools._conn")
    @patch("scripts.research.tools._filter_by_name_similarity")
    def test_mergent_name_search(self, mock_filter, mock_conn):
        """Tier 3: name-based Mergent lookup."""
        from scripts.research.tools import _resolve_employer_url

        # Tier 2 fails (no employer_id passed)
        # Tier 3: name search succeeds
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {"company_name": "EXAMPLE CORP", "website": "WWW.EXAMPLE.COM"},
        ]
        mock_conn.return_value.cursor.return_value = mock_cur
        mock_filter.return_value = [
            {"company_name": "EXAMPLE CORP", "website": "WWW.EXAMPLE.COM"},
        ]

        url, source = _resolve_employer_url("Example Corp")
        assert url == "https://www.example.com"
        assert source == "name_search"

    def test_no_url_found(self):
        """All tiers fail when no DB access and no URL provided."""
        from scripts.research.tools import _resolve_employer_url

        # Tier 1 fails (no url), Tier 2/3 fail (DB errors are caught)
        with patch("scripts.research.tools._conn", side_effect=Exception("no db")):
            url, source = _resolve_employer_url("Unknown Corp")
        assert url is None
        assert source == "none"


# ---------------------------------------------------------------------------
# Scraping (mocked Crawl4AI)
# ---------------------------------------------------------------------------

class TestScrapeEmployerWebsite:
    def _patch_crawl4ai(self, results_map):
        """Return a context manager that patches crawl4ai imports with fake results."""
        fake_mod = _build_fake_crawl4ai()
        # Patch AsyncWebCrawler to inject results
        OrigClass = fake_mod.AsyncWebCrawler

        class PatchedCrawler(OrigClass):
            def __init__(self, *a, **kw):
                super().__init__(*a, _results=results_map, **kw)

        fake_mod.AsyncWebCrawler = PatchedCrawler
        return patch.dict("sys.modules", {"crawl4ai": fake_mod})

    def test_homepage_success(self):
        """Homepage found -> found=True, homepage_text populated."""
        from scripts.research.tools import scrape_employer_website

        results = {
            "https://example.com": _make_crawl_result(
                success=True,
                markdown_text="Welcome to Example Corp. " * 20,
            ),
        }
        with self._patch_crawl4ai(results):
            # Provide URL directly to skip DB lookup
            out = scrape_employer_website("Example Corp", url="https://example.com")

        assert out["found"] is True
        assert out["source"] == "web_scrape:employer_website"
        assert out["data"]["pages_scraped"] >= 1
        assert out["data"]["homepage_text"] is not None
        assert "example.com" in out["summary"]

    def test_homepage_failure_returns_not_found(self):
        """If homepage fails, return found=False."""
        from scripts.research.tools import scrape_employer_website

        results = {
            "https://bad.example.com": _make_crawl_result(
                success=False, error_message="Connection refused",
            ),
        }
        with self._patch_crawl4ai(results):
            out = scrape_employer_website("Bad Corp", url="https://bad.example.com")

        assert out["found"] is False

    def test_subpage_discovery(self):
        """About page found but careers returns 404."""
        from scripts.research.tools import scrape_employer_website

        homepage_text = "Welcome to Acme Corp. We are a leading provider. " * 10
        about_text = "About Acme Corp. Founded in 1995. " * 10
        results = {
            "https://acme.com": _make_crawl_result(True, homepage_text),
            "https://acme.com/about": _make_crawl_result(True, about_text),
            # /about-us and /company will 404 (default)
            # /careers and /jobs will 404
        }
        with self._patch_crawl4ai(results):
            out = scrape_employer_website("Acme Corp", url="https://acme.com")

        assert out["found"] is True
        assert out["data"]["homepage_text"] is not None
        assert out["data"]["about_text"] is not None
        assert out["data"]["careers_text"] is None
        assert out["data"]["pages_scraped"] == 2

    def test_text_truncation(self):
        """Text exceeding char budget is truncated."""
        from scripts.research.tools import scrape_employer_website

        # Generate a very long page
        long_text = ("This is a long paragraph about the company. " * 200)
        results = {
            "https://long.com": _make_crawl_result(True, long_text),
        }
        with self._patch_crawl4ai(results):
            out = scrape_employer_website("Long Corp", url="https://long.com")

        assert out["found"] is True
        # Homepage budget is 3000 chars
        assert len(out["data"]["homepage_text"]) <= 3100  # small margin for boundary

    def test_no_url_found_returns_not_found(self):
        """When URL resolution fails entirely, return found=False."""
        from scripts.research.tools import scrape_employer_website

        with patch("scripts.research.tools._resolve_employer_url", return_value=(None, "none")):
            out = scrape_employer_website("Ghost Corp")

        assert out["found"] is False
        assert "No website URL found" in out["summary"]

    def test_crawl4ai_not_installed(self):
        """When Crawl4AI is not importable, return graceful error."""
        # Temporarily hide crawl4ai
        with patch.dict("sys.modules", {"crawl4ai": None}):
            # Need to re-import to trigger the ImportError path
            # Instead, call the function which does a lazy import check
            from scripts.research.tools import scrape_employer_website
            # The function first tries `from crawl4ai import AsyncWebCrawler`
            # When the module is None in sys.modules, import will fail
            out = scrape_employer_website("Test Corp", url="https://test.com")

        assert out["found"] is False
        assert "not installed" in out["summary"].lower() or "not installed" in out.get("error", "").lower()


# ---------------------------------------------------------------------------
# Text Truncation Helper
# ---------------------------------------------------------------------------

class TestTruncateMarkdown:
    def test_within_limit_unchanged(self):
        from scripts.research.tools import _truncate_markdown
        assert _truncate_markdown("Hello world.", 100) == "Hello world."

    def test_cuts_at_paragraph_boundary(self):
        from scripts.research.tools import _truncate_markdown
        text = "First paragraph.\n\nSecond paragraph that is much longer."
        result = _truncate_markdown(text, 30)
        assert result == "First paragraph."

    def test_empty_string(self):
        from scripts.research.tools import _truncate_markdown
        assert _truncate_markdown("", 100) == ""
        assert _truncate_markdown(None, 100) == ""


# ---------------------------------------------------------------------------
# Integration: tool registered and not skipped
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_in_tool_registry(self):
        from scripts.research.tools import TOOL_REGISTRY
        assert "scrape_employer_website" in TOOL_REGISTRY
        assert callable(TOOL_REGISTRY["scrape_employer_website"])

    def test_in_tool_definitions(self):
        from scripts.research.tools import TOOL_DEFINITIONS
        names = [td["name"] for td in TOOL_DEFINITIONS]
        assert "scrape_employer_website" in names
        # Verify it has employer_id in properties
        scraper_def = next(td for td in TOOL_DEFINITIONS if td["name"] == "scrape_employer_website")
        assert "employer_id" in scraper_def["input_schema"]["properties"]

    def test_not_in_agent_skip_list(self):
        """scrape_employer_website should NOT be skipped by _build_gemini_tools."""
        from scripts.research.agent import _build_gemini_tools
        # _build_gemini_tools skips tools in ("search_web",)
        # We can't easily call it without google.genai, so check the source
        import inspect
        source = inspect.getsource(_build_gemini_tools)
        assert "scrape_employer_website" not in source

    def test_in_internal_tools_list(self):
        from scripts.research.agent import _INTERNAL_TOOLS
        assert "scrape_employer_website" in _INTERNAL_TOOLS
