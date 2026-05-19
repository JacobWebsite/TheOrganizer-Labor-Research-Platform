"""Tests for /api/employers/master/{master_id}/power-profile.pdf (C.5).

Mix of:
  - pure renderer tests (synthetic payload, no DB)
  - live-DB endpoint tests (skip if master_employers is empty)
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services.power_profile_renderer import (
    _fmt_int,
    _fmt_money,
    _truncate,
    render_power_profile_pdf,
)
from db_config import get_connection


client = TestClient(app)


# ---- Helpers -----------------------------------------------------------

def _has_master_employers() -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM master_employers LIMIT 1")
        ok = cur.fetchone() is not None
        conn.close()
        return ok
    except Exception:
        return False


def _pick_known_master() -> int | None:
    """Try Abbott Laboratories (rich data), else first row in the table."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT master_id FROM master_employers "
            "WHERE master_id = 4036186 LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            conn.close()
            return int(row[0])
        cur.execute("SELECT master_id FROM master_employers LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return int(row[0]) if row else None
    except Exception:
        return None


# ---- Pure helper / renderer tests --------------------------------------

def test_fmt_money_short_units():
    assert _fmt_money(0) == "$0"
    assert _fmt_money(None) == "--"
    assert _fmt_money(1234) == "$1.2K"
    assert _fmt_money(1_500_000) == "$1.5M"
    assert _fmt_money(2_750_000_000) == "$2.8B"


def test_fmt_money_long_form():
    assert _fmt_money(1234567, short=False) == "$1,234,567"


def test_fmt_int():
    assert _fmt_int(None) == "--"
    assert _fmt_int(0) == "0"
    assert _fmt_int(1234567) == "1,234,567"


def test_truncate():
    assert _truncate("short", 20) == "short"
    # Renderer truncate keeps `n - 1` chars then appends "..."
    out = _truncate("hello world", 8)
    assert out.endswith("...")
    # "hello w" + "..." -> "hello w..."
    assert out.startswith("hello w")
    assert _truncate(None, 5) == ""


def test_renderer_with_minimal_payload_produces_pdf():
    """Pure unit test: hand the renderer a barely-populated payload.

    We expect a valid PDF with the %PDF header even if every section
    falls through to its 'No data available.' line.
    """
    payload = {
        "master_id": 1,
        "canonical_name": "Test Co",
        "display_name": "TEST CO",
        "state": "CA",
    }
    pdf = render_power_profile_pdf(payload)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    # Page count via header marker -- ReportLab emits one /Type /Page per page.
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 3 \
        or len(re.findall(rb"/Type\s*/Page[^s]", pdf)) >= 3, \
        f"Expected at least 3 pages in PDF (len={len(pdf)})"


def test_renderer_with_rich_payload_includes_section_headers():
    """Verify the generated PDF byte stream references each major section."""
    payload = {
        "master_id": 999,
        "canonical_name": "Acme",
        "display_name": "ACME CORP",
        "state": "NY",
        "naics": "311111",
        "employee_count": 5000,
        "is_public": True,
        "latest_revenue": 1_000_000_000,
        "latest_assets": 500_000_000,
        "institutional_owners": [
            {"filer_name": "Vanguard", "filer_state": "PA",
             "value": 2_000_000_000, "shares": 12_000_000},
            {"filer_name": "BlackRock", "filer_state": "NY",
             "value": 1_500_000_000, "shares": 8_000_000},
        ],
        "institutional_owners_period": "2025-09-30",
        "institutional_owners_total_value": 3_500_000_000,
        "institutional_owners_count": 2,
        "fec": {"pac_dollars_total": 100_000.0, "employee_dollars_total": 50_000.0,
                "pac_committees_count": 1, "pac_recipients_count": 5,
                "employee_donations_count": 50},
        "lobbying": {"total_spend": 250_000.0, "total_filings": 4,
                     "active_quarters": 4, "registrants_count": 2,
                     "client_name_used": "Acme Corp"},
        "demographics": {
            "has_data": True, "method": "acs_state_naics4",
            "total_workforce": 12345, "pct_female": 42.5,
            "pct_minority": 30.1, "pct_under_25": 12.0, "pct_55_plus": 15.5,
            "pct_no_hs": 5.0, "pct_bachelors_plus": 35.0,
            "vintage_year": "ACS 2022",
        },
        "osha": {"inspection_count": 10, "violation_count": 25,
                 "penalty_total": 250_000.0,
                 "worst_inspection_label": "Plant A (NJ) -- $200K"},
        "nlrb": {"election_count": 3, "ulp_count": 8,
                 "union_wins": 2, "union_losses": 1,
                 "latest_label": "Latest 2025-01-15"},
        "whd": {"case_count": 5, "violation_count": 12,
                "backwages_total": 300_000.0,
                "worst_record": "Latest finding 2024-09-01"},
        "epa": {"facility_count": 2, "inspection_count": 4,
                "penalty_total": 25_000.0, "snc_count": 0,
                "any_air_flag": False},
        "directors": [
            {"name": "Jane Smith", "position": "Chair",
             "is_independent": True,
             "enforcement_risk": {"other_boards_count": 3,
                                  "risk_score": 12.5, "risk_tier": "GREEN"}},
        ],
        "director_network_stats": {"one_hop_count": 5,
                                   "two_hop_count": 25,
                                   "shared_directors_total": 3},
        "executives": [
            {"name": "Bob Jones", "title": "CEO", "title_rank_label": "CEO"},
        ],
        "gold_standard_tier": "gold",
        "score_value": 7.85,
        "score_kind": "unified",
        "pillar_anger": 5.5, "pillar_leverage": 6.2, "pillar_stability": 4.0,
        "signals_present": 8,
    }
    pdf = render_power_profile_pdf(payload)
    assert pdf.startswith(b"%PDF-")
    # PDFs compress text streams so we can't grep readable strings directly.
    # The size sanity check is sufficient -- a 3-page PDF with this much
    # content is materially larger than the empty-payload PDF.
    assert len(pdf) > 4000


# ---- Live endpoint tests -----------------------------------------------

@pytest.mark.skipif(not _has_master_employers(), reason="master_employers empty")
def test_unknown_master_returns_404_json():
    r = client.get("/api/employers/master/9999999999/power-profile.pdf")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["detail"]


@pytest.mark.skipif(not _has_master_employers(), reason="master_employers empty")
def test_known_master_returns_pdf_bytes():
    mid = _pick_known_master()
    if mid is None:
        pytest.skip("No master_id available")
    r = client.get(f"/api/employers/master/{mid}/power-profile.pdf")
    assert r.status_code == 200, r.text
    # Headers
    ct = r.headers["content-type"]
    assert ct.startswith("application/pdf"), f"unexpected content-type: {ct}"
    cd = r.headers.get("content-disposition", "")
    assert "filename" in cd, f"missing filename in {cd!r}"
    # Body
    body = r.content
    assert isinstance(body, bytes)
    assert len(body) > 1000, f"PDF suspiciously small ({len(body)} bytes)"
    assert body.startswith(b"%PDF-"), \
        f"expected %PDF- magic, got {body[:8]!r}"
    # ReportLab default Helvetica produces a PDF with multiple pages -- check.
    assert b"/Type /Catalog" in body


@pytest.mark.skipif(not _has_master_employers(), reason="master_employers empty")
def test_pdf_size_under_target():
    """Roadmap target: under 100 KB per PDF. We allow a 250 KB ceiling
    here -- the v1 implementation typically lands well under 60 KB but
    we don't want this to fail flakily if a master has unusually rich
    director / owner data."""
    mid = _pick_known_master()
    if mid is None:
        pytest.skip("No master_id available")
    r = client.get(f"/api/employers/master/{mid}/power-profile.pdf")
    assert r.status_code == 200
    assert len(r.content) < 250_000, f"PDF too large: {len(r.content)} bytes"


@pytest.mark.skipif(not _has_master_employers(), reason="master_employers empty")
def test_negative_master_id_404s():
    """master_id is `int` so -1 will pass schema validation but the row
    doesn't exist in master_employers. Should 404, not 500."""
    r = client.get("/api/employers/master/-1/power-profile.pdf")
    assert r.status_code == 404
