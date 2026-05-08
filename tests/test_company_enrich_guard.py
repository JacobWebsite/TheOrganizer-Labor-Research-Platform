"""
Tests for the search_company_enrich identity-grafting guard.

R7-16 (2026-04-27): the original composite-fuzzy guard caught the canonical
case (Crouse Hospital -> Children's National). 2026-04-30 added an
alias-based exclusion layer that catches collision cases the fuzzy
guard misses (Cleveland Clinic -> Cleveland-Cliffs at partial=83;
NYC Hospitals -> NYU Langone at partial=88).

These tests exercise the guard logic directly (the fuzzy comparisons +
alias-collision detection) so we lock in the behavior without hitting the
live CompanyEnrich API.
"""
import os
import sys
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


def _make_response(name: str, status: int = 200) -> MagicMock:
    """Mock a CompanyEnrich /companies/enrich response with a given returned name."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"name": name}
    resp.raise_for_status.return_value = None
    return resp


def _call_with_mock_response(query: str, returned_name: str, *, status: int = 200) -> dict:
    """Call search_company_enrich with a mocked HTTP layer."""
    from scripts.research import tools

    fake_resp = _make_response(returned_name, status=status)
    with patch.dict(os.environ, {"COMPANY_ENRICH_API_KEY": "test-key"}, clear=False), \
         patch.object(tools, "_ce_limiter", MagicMock()), \
         patch("requests.post", return_value=fake_resp), \
         patch("requests.get", return_value=fake_resp):
        return tools.search_company_enrich(query)


# ---------------------------------------------------------------------------
# Layer 2: composite fuzzy guard (canonical R7-16 case)
# ---------------------------------------------------------------------------

def test_crouse_to_childrens_national_rejected():
    """The canonical R7-16 case: name lookup grafted wrong hospital."""
    result = _call_with_mock_response("Crouse Hospital", "Children's National Hospital")
    assert result["found"] is False
    assert result.get("error") == "name_mismatch"
    assert "Identity mismatch" in result["summary"]


def test_starbucks_to_starbucks_corporation_accepted():
    """Substring/parent suffix should not false-reject."""
    result = _call_with_mock_response("Starbucks", "Starbucks Corporation")
    assert result["found"] is not False or result.get("error") != "name_mismatch", \
        f"Starbucks substring should be accepted, got {result}"


def test_walmart_to_walmart_inc_accepted():
    result = _call_with_mock_response("Walmart", "Walmart Inc.")
    assert result.get("error") != "name_mismatch"


def test_apple_to_apple_inc_accepted():
    result = _call_with_mock_response("Apple", "Apple Inc.")
    assert result.get("error") != "name_mismatch"


def test_kroger_subset_accepted():
    """`the kroger` vs `kroger company` -- token_set rewards the overlap."""
    result = _call_with_mock_response("the kroger", "kroger company")
    assert result.get("error") != "name_mismatch"


def test_crouse_to_crouse_health_accepted():
    """DBA / sibling brand -- should NOT be rejected."""
    result = _call_with_mock_response("Crouse Hospital", "Crouse Health")
    assert result.get("error") != "name_mismatch"


# ---------------------------------------------------------------------------
# Layer 1: alias-based collision exclusion (cases the fuzzy guard misses)
# ---------------------------------------------------------------------------

def test_cleveland_clinic_to_cleveland_cliffs_rejected_by_alias():
    """partial_ratio = 83 slips past the fuzzy guard.
    Layer 1 must catch via employer_aliases.json exclude_terms."""
    result = _call_with_mock_response("Cleveland Clinic", "Cleveland-Cliffs Inc")
    assert result["found"] is False
    assert result.get("error") == "alias_collision"
    assert "Cleveland-Cliffs" in result["summary"] or "cleveland-cliffs" in result["summary"]


def test_nyc_hospitals_to_nyu_langone_rejected_by_alias():
    """Healthcare collision: NYC Hospitals (public system) vs NYU Langone (private)."""
    result = _call_with_mock_response("nyc health and hospitals", "NYU Langone Hospitals")
    assert result["found"] is False
    assert result.get("error") == "alias_collision"


def test_alias_pass_through_when_no_excluded_term():
    """Cleveland Clinic -> Cleveland Clinic Foundation should pass alias layer."""
    result = _call_with_mock_response("Cleveland Clinic", "Cleveland Clinic Foundation")
    assert result.get("error") not in ("alias_collision", "name_mismatch")


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_404_returns_not_found_without_guard_logic():
    """Guard runs only on 2xx responses; 404 is its own short-circuit."""
    result = _call_with_mock_response("Nonexistent Co", "ignored", status=404)
    assert result["found"] is False
    assert result.get("error") != "name_mismatch"
    assert result.get("error") != "alias_collision"


def test_no_api_key_short_circuits():
    """Guard never reaches the API when no key is configured."""
    from scripts.research import tools
    with patch.dict(os.environ, {}, clear=True):
        result = tools.search_company_enrich("Anything")
    assert result["found"] is False
    assert result.get("error") == "missing_key"


def test_empty_returned_name_does_not_crash():
    """Guard tolerates empty/missing name field on the API response."""
    result = _call_with_mock_response("Anyquery", "")
    # Empty returned_name short-circuits the guard; result depends on
    # downstream parsing, but it must not raise.
    assert isinstance(result, dict)


def test_domain_lookup_skips_name_guard():
    """Domain-based lookup is high-trust; guard only runs on name lookups."""
    from scripts.research import tools
    fake_resp = _make_response("Children's National Hospital")
    with patch.dict(os.environ, {"COMPANY_ENRICH_API_KEY": "test-key"}, clear=False), \
         patch.object(tools, "_ce_limiter", MagicMock()), \
         patch("requests.get", return_value=fake_resp), \
         patch("requests.post", return_value=fake_resp):
        # domain-based call: even a wildly different returned name passes
        # because we trust domain matches.
        result = tools.search_company_enrich(
            "Crouse Hospital", domain="childrensnational.org"
        )
    # Should NOT be guard-rejected because domain branch is trusted
    assert result.get("error") not in ("name_mismatch", "alias_collision")
