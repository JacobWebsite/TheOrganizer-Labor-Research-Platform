"""Tests for ``scripts/etl/sec_10k/download_10k_batch.py``.

Network is mocked. Disk writes go to ``tmp_path`` via monkey-patched
``DOWNLOAD_ROOT``. The DB-side is exercised at the SQL-string level only
(idempotency assertions). End-to-end DB testing is covered by the smoke
script invocation in the verification step.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock


from scripts.etl.sec_10k import download_10k_batch as dl


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _mock_response(status: int, body: bytes | str | dict | None) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    if isinstance(body, dict):
        text = json.dumps(body)
        m.text = text
        m.content = text.encode()
        m.json.return_value = body
    elif isinstance(body, bytes):
        m.text = body.decode("utf-8", errors="replace")
        m.content = body
        m.json.side_effect = json.JSONDecodeError("", "", 0)
    elif isinstance(body, str):
        m.text = body
        m.content = body.encode()
        m.json.side_effect = json.JSONDecodeError("", "", 0)
    else:
        m.text = ""
        m.content = b""
    return m


# --------------------------------------------------------------------------
# fetch_via_primary_document
# --------------------------------------------------------------------------


def test_fetch_via_primary_document_returns_url_and_body(monkeypatch):
    body = b"<html><body>10-K body content</body></html>" * 100
    monkeypatch.setattr(
        dl.requests,
        "get",
        MagicMock(return_value=_mock_response(200, body)),
    )
    result = dl.fetch_via_primary_document(
        cik=732717,
        accession="000073271726000120",
        primary_document="t-20251231.htm",
    )
    assert result is not None
    url, content = result
    assert "Archives/edgar/data/732717/000073271726000120/t-20251231.htm" in url
    assert content == body


def test_fetch_via_primary_document_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(
        dl.requests,
        "get",
        MagicMock(return_value=_mock_response(404, b"not found")),
    )
    assert (
        dl.fetch_via_primary_document(
            cik=99999,
            accession="acc",
            primary_document="missing.htm",
        )
        is None
    )


def test_fetch_via_primary_document_returns_none_when_doc_missing():
    """Some EDGAR submissions JSON entries omit primaryDocument; we must
    fall through to the index-scan path rather than crashing."""
    assert (
        dl.fetch_via_primary_document(
            cik=99999,
            accession="acc",
            primary_document=None,
        )
        is None
    )


# --------------------------------------------------------------------------
# fetch_via_index_scan
# --------------------------------------------------------------------------


def test_fetch_via_index_scan_picks_10k_file_over_exhibit(monkeypatch):
    """When the filing has both ``ex-21.htm`` and ``form10-k.htm`` we must
    pick the latter -- exhibit-21 is a separate concern handled by
    ``load_sec_exhibit21.py``."""
    index_body = {
        "directory": {
            "item": [
                {"name": "ex-21.htm", "size": "12345"},
                {"name": "ex-32-1.htm", "size": "1024"},
                {"name": "form10-k.htm", "size": "5000000"},
                {"name": "summary.htm", "size": "8000"},
            ]
        }
    }
    body_10k = b"<html>10-K body" + b"x" * 5_000_000 + b"</html>"

    call_history: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        call_history.append(url)
        if url.endswith("/index.json"):
            return _mock_response(200, index_body)
        if url.endswith("/form10-k.htm"):
            return _mock_response(200, body_10k)
        return _mock_response(404, b"")

    monkeypatch.setattr(dl.requests, "get", MagicMock(side_effect=fake_get))
    res = dl.fetch_via_index_scan(cik=42, accession="00004200012345600001")
    assert res is not None
    url, content = res
    assert url.endswith("/form10-k.htm")
    assert content == body_10k
    # We did not download the exhibit.
    assert not any(u.endswith("/ex-21.htm") for u in call_history)


def test_fetch_via_index_scan_returns_none_when_no_candidates(monkeypatch):
    index_body = {
        "directory": {
            "item": [
                {"name": "ex-21.htm", "size": "12345"},
                {"name": "ex-101.sch.xml", "size": "100"},
            ]
        }
    }
    monkeypatch.setattr(
        dl.requests,
        "get",
        MagicMock(return_value=_mock_response(200, index_body)),
    )
    assert dl.fetch_via_index_scan(cik=1, accession="acc") is None


# --------------------------------------------------------------------------
# download_one
# --------------------------------------------------------------------------


def test_download_one_writes_html_to_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(dl, "DOWNLOAD_ROOT", tmp_path)
    body = b"<html>real 10-K body</html>"
    monkeypatch.setattr(
        dl.requests,
        "get",
        MagicMock(return_value=_mock_response(200, body)),
    )

    row = dl.QueueRow(
        cik=732717,
        accession="000073271726000120",
        primary_document="t-20251231.htm",
        company_name="AT&T INC.",
        ticker="T",
        rank_position=1,
    )
    res = dl.download_one(row)
    assert res["status"] == "downloaded"
    assert res["bytes_written"] == len(body)

    expected_path = (
        tmp_path / "732717" / "000073271726000120.html"
    )
    assert expected_path.exists()
    assert expected_path.read_bytes() == body


def test_download_one_resumable_skips_existing_file(monkeypatch, tmp_path):
    """If the target file already exists with content, we must not re-fetch
    -- that's the whole point of the resumability contract."""
    monkeypatch.setattr(dl, "DOWNLOAD_ROOT", tmp_path)
    expected_path = (
        tmp_path / "732717" / "000073271726000120.html"
    )
    expected_path.parent.mkdir(parents=True)
    expected_path.write_bytes(b"<html>cached</html>")

    mock_get = MagicMock()
    monkeypatch.setattr(dl.requests, "get", mock_get)

    row = dl.QueueRow(
        cik=732717,
        accession="000073271726000120",
        primary_document="t-20251231.htm",
        company_name="AT&T INC.",
        ticker="T",
        rank_position=1,
    )
    res = dl.download_one(row)
    assert res["status"] == "cached"
    assert res["bytes_written"] == len(b"<html>cached</html>")
    # The fetcher must not have been called.
    assert mock_get.call_count == 0


def test_download_one_falls_back_to_index_scan(monkeypatch, tmp_path):
    """Primary doc returns 404 -> index scan finds form10-k.htm. End result
    must be a successful download, not http_error."""
    monkeypatch.setattr(dl, "DOWNLOAD_ROOT", tmp_path)
    index_body = {
        "directory": {
            "item": [{"name": "form10-k.htm", "size": "1000"}]
        }
    }
    body_10k = b"<html>fallback body</html>"

    def fake_get(url, headers=None, timeout=None):
        if url.endswith("/missing-primary.htm"):
            return _mock_response(404, b"")
        if url.endswith("/index.json"):
            return _mock_response(200, index_body)
        if url.endswith("/form10-k.htm"):
            return _mock_response(200, body_10k)
        return _mock_response(404, b"")

    monkeypatch.setattr(dl.requests, "get", MagicMock(side_effect=fake_get))

    row = dl.QueueRow(
        cik=99999,
        accession="acc",
        primary_document="missing-primary.htm",
        company_name="Test Co",
        ticker="T",
        rank_position=1,
    )
    res = dl.download_one(row)
    assert res["status"] == "downloaded"
    assert res["bytes_written"] == len(body_10k)


def test_download_one_returns_http_error_when_both_paths_fail(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(dl, "DOWNLOAD_ROOT", tmp_path)
    monkeypatch.setattr(
        dl.requests,
        "get",
        MagicMock(return_value=_mock_response(503, b"down")),
    )
    row = dl.QueueRow(
        cik=1,
        accession="acc",
        primary_document="x.htm",
        company_name="X",
        ticker="X",
        rank_position=1,
    )
    res = dl.download_one(row)
    assert res["status"] == "http_error"
    assert res["bytes_written"] == 0


# --------------------------------------------------------------------------
# Queue-read SQL: structural assertions
# --------------------------------------------------------------------------


def test_select_pending_excludes_no_10k_sentinel():
    assert "f.accession <> 'NO_10K'" in dl.SELECT_PENDING


def test_select_pending_skips_already_downloaded():
    """The default WHERE must let `NULL` (never tried) and `pending` through,
    but skip `downloaded` so re-runs are near-no-ops."""
    sql = dl.SELECT_PENDING.format(extra_clause="", limit_clause="")
    # Status check uses an OR over NULL + pending only (no 'downloaded').
    assert "p.status IS NULL" in sql
    assert "p.status = 'pending'" in sql
    # Default does not include the retry clause.
    assert "http_error" not in sql


def test_select_pending_with_retry_includes_failed():
    sql = dl.SELECT_PENDING.format(
        extra_clause=" OR p.status IN ('http_error', 'no_doc', 'parse_error')",
        limit_clause="",
    )
    assert "http_error" in sql
    assert "parse_error" in sql


def test_upsert_progress_uses_on_conflict_do_update():
    """A re-run must overwrite the prior status (otherwise a transient
    http_error never recovers to 'downloaded' on retry)."""
    assert "ON CONFLICT (cik, accession) DO UPDATE" in dl.UPSERT_PROGRESS


# --------------------------------------------------------------------------
# target_path
# --------------------------------------------------------------------------


def test_target_path_format():
    p = dl.target_path(732717, "000073271726000120")
    parts = p.parts[-2:]
    assert parts[0] == "732717"
    assert parts[1] == "000073271726000120.html"
