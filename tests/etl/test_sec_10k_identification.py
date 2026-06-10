"""Tests for ``scripts/etl/sec_10k/identify_recent_10k.py``.

Network is mocked via ``requests_mock``-style monkeypatching so the suite
can run offline. DB access is mocked with an in-memory Fake -- the goal of
this test file is to exercise the EDGAR-parsing + queue-upsert logic, not
to verify Postgres semantics (the schema-check test below does the latter
via the DDL string itself).
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock


from scripts.etl.sec_10k import identify_recent_10k as ident


# --------------------------------------------------------------------------
# fetch_recent_10k: EDGAR JSON parsing
# --------------------------------------------------------------------------


SAMPLE_SUBMISSIONS_BODY: dict[str, Any] = {
    "cik": "732717",
    "name": "AT&T INC.",
    "filings": {
        "recent": {
            "form": ["8-K", "10-K", "DEF 14A", "10-K/A"],
            "accessionNumber": [
                "0000732717-26-000200",
                "0000732717-26-000120",
                "0000732717-26-000050",
                "0000732717-25-000999",
            ],
            "primaryDocument": [
                "ex991.htm",
                "t-20251231.htm",
                "att-2026-proxy.htm",
                "t-20241231-amend.htm",
            ],
            "filingDate": [
                "2026-03-15",
                "2026-02-09",
                "2026-03-30",
                "2025-08-15",
            ],
            "reportDate": [
                "2026-03-15",
                "2025-12-31",
                "2026-03-30",
                "2024-12-31",
            ],
        }
    },
}


def _mock_get(monkeypatch, status: int, body: Any) -> MagicMock:
    """Patch ``requests.get`` to return a single canned response object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    if isinstance(body, (dict, list)):
        mock_resp.text = json.dumps(body)
        mock_resp.json.return_value = body
    else:
        mock_resp.text = body or ""
        mock_resp.json.side_effect = json.JSONDecodeError("not json", "", 0)
    mock_resp.content = (mock_resp.text or "").encode()
    mock_get = MagicMock(return_value=mock_resp)
    monkeypatch.setattr(ident.requests, "get", mock_get)
    return mock_get


def test_fetch_recent_10k_returns_first_10k(monkeypatch):
    _mock_get(monkeypatch, 200, SAMPLE_SUBMISSIONS_BODY)
    res = ident.fetch_recent_10k(732717)
    assert res is not None
    # The 10-K is the SECOND form in the canned list; we should pick it
    # (not the 8-K above it, not the DEF 14A below).
    assert res.form == "10-K"
    assert res.accession_dashed == "0000732717-26-000120"
    assert res.accession_no_dashes == "000073271726000120"
    assert res.primary_document == "t-20251231.htm"
    assert res.filing_date == "2026-02-09"
    assert res.report_date == "2025-12-31"


def test_fetch_recent_10k_handles_no_10k(monkeypatch):
    body = {
        "filings": {
            "recent": {
                "form": ["8-K", "DEF 14A"],
                "accessionNumber": ["a-b-c", "d-e-f"],
                "primaryDocument": ["x.htm", "y.htm"],
                "filingDate": ["2026-01-01", "2026-02-02"],
                "reportDate": ["2026-01-01", "2026-02-02"],
            }
        }
    }
    _mock_get(monkeypatch, 200, body)
    assert ident.fetch_recent_10k(99999) is None


def test_fetch_recent_10k_handles_http_error(monkeypatch):
    _mock_get(monkeypatch, 503, "Service Unavailable")
    assert ident.fetch_recent_10k(99999) is None


def test_fetch_recent_10k_handles_invalid_json(monkeypatch):
    _mock_get(monkeypatch, 200, "<html>oops</html>")
    assert ident.fetch_recent_10k(99999) is None


def test_fetch_recent_10k_handles_amended_10k_only(monkeypatch):
    """A 10-K/A counts as a 10-K for our purposes (some filers only have
    amended versions in the recent window after a restatement)."""
    body = {
        "filings": {
            "recent": {
                "form": ["10-K/A"],
                "accessionNumber": ["0000999999-26-000001"],
                "primaryDocument": ["amend.htm"],
                "filingDate": ["2026-04-01"],
                "reportDate": ["2025-12-31"],
            }
        }
    }
    _mock_get(monkeypatch, 200, body)
    res = ident.fetch_recent_10k(999999)
    assert res is not None
    assert res.form == "10-K/A"


# --------------------------------------------------------------------------
# DDL: schema sanity-check
# --------------------------------------------------------------------------


def test_ddl_creates_expected_columns():
    """The DDL strings define our public contract with downstream callers
    -- the columns referenced by the SELECTs in download_10k_batch.py and
    by the README must exist. Cheap string-level guard against DDL drift.
    """
    expected_filings_cols = [
        "cik",
        "accession",
        "accession_dashed",
        "primary_document",
        "filing_date",
        "report_date",
        "form",
        "company_name",
        "ticker",
        "master_id",
        "rank_score",
        "rank_position",
        "queued_at",
        "notes",
    ]
    for col in expected_filings_cols:
        assert col in ident.DDL_FILINGS_TO_DOWNLOAD, (
            f"sec_10k_filings_to_download is missing column {col!r}"
        )

    expected_progress_cols = [
        "cik",
        "accession",
        "status",
        "bytes_written",
        "file_path",
        "last_attempted",
        "notes",
    ]
    for col in expected_progress_cols:
        assert col in ident.DDL_PROGRESS, (
            f"load_sec_10k_progress is missing column {col!r}"
        )

    # Both tables must declare PRIMARY KEY (cik, accession).
    assert "PRIMARY KEY (cik, accession)" in ident.DDL_FILINGS_TO_DOWNLOAD
    assert "PRIMARY KEY (cik, accession)" in ident.DDL_PROGRESS


def test_upsert_filing_uses_on_conflict_do_update():
    """Idempotency on re-run: the upsert must be ON CONFLICT DO UPDATE,
    not DO NOTHING (the latter would leave rank_position stale)."""
    assert "ON CONFLICT (cik, accession) DO UPDATE" in ident.UPSERT_FILING


def test_upsert_progress_preserves_downloaded_status():
    """A re-run of `identify` must not bump a row that's already
    `downloaded` back to `pending`. The CASE clause guards that."""
    assert "WHEN load_sec_10k_progress.status IN ('downloaded'" in ident.UPSERT_PROGRESS_PENDING


# --------------------------------------------------------------------------
# queue_candidate: idempotency on the DB side (mocked cursor)
# --------------------------------------------------------------------------


class FakeCursor:
    def __init__(self, store: dict[tuple[int, str], dict]):
        self.store = store
        self.last_sql: str | None = None
        self.last_params: tuple | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql: str, params: tuple | None = None):
        self.last_sql = sql
        self.last_params = params
        # Crude UPSERT simulator -- pull (cik, accession) from positional params.
        if params and "INSERT INTO sec_10k_filings_to_download" in sql:
            cik, accession = int(params[0]), params[1]
            self.store[(cik, accession)] = {
                "primary_document": params[3],
                "filing_date": params[4],
                "form": params[6],
                "rank_position": params[11],
                "notes": params[13] if len(params) > 13 else None,
            }
        if params and "INSERT INTO load_sec_10k_progress" in sql:
            cik, accession = int(params[0]), params[1]
            self.store.setdefault(("progress", cik, accession), {"status": "pending"})


class FakeConn:
    def __init__(self):
        self.store: dict = {}
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_queue_candidate_idempotent_on_rerun():
    """Running identify twice over the same candidate must produce one
    row in the staging table, not two. We simulate via a fake cursor that
    treats (cik, accession) as the primary key."""
    conn = FakeConn()
    cand = ident.Candidate(
        cik=732717,
        company_name="AT&T INC.",
        ticker="T",
        master_id=106406,
        rank_score=999_999,
    )
    filing = ident.TenKFiling(
        cik=732717,
        accession_no_dashes="000073271726000120",
        accession_dashed="0000732717-26-000120",
        primary_document="t-20251231.htm",
        filing_date="2026-02-09",
        report_date="2025-12-31",
        form="10-K",
    )

    s1 = ident.queue_candidate(conn, cand, rank_position=1, filing=filing)
    s2 = ident.queue_candidate(conn, cand, rank_position=1, filing=filing)
    assert s1 == "queued"
    assert s2 == "queued"
    # Single (cik, accession) row regardless of how many times we run.
    assert (732717, "000073271726000120") in conn.store
    n_filing_keys = sum(
        1
        for k in conn.store
        if isinstance(k, tuple) and len(k) == 2 and k[0] == 732717
    )
    assert n_filing_keys == 1


def test_queue_candidate_writes_no_10k_sentinel():
    """Candidates with no 10-K still get a row (so the next identify run
    knows we already checked them); the sentinel uses ``accession='NO_10K'``."""
    conn = FakeConn()
    cand = ident.Candidate(
        cik=999_888,
        company_name="Defunct Corp",
        ticker="DEAD",
        master_id=None,
        rank_score=10,
    )
    s = ident.queue_candidate(conn, cand, rank_position=99, filing=None)
    assert s == "no_10k"
    assert (999_888, "NO_10K") in conn.store


# --------------------------------------------------------------------------
# RateLimiter
# --------------------------------------------------------------------------


def test_rate_limiter_enforces_minimum_gap(monkeypatch):
    """Successive ``wait()`` calls should be at least ``s`` seconds apart.

    The first call also sleeps when the clock starts at 0 (since
    ``_last`` initialises to 0.0). What we actually care about is the
    second call -- it must sleep approximately ``s`` minus whatever
    elapsed since the previous call.
    """
    sleeps: list[float] = []
    fake_now = [100.0]  # Avoid the clock=0 + _last=0 quirk.

    def fake_monotonic():
        return fake_now[0]

    def fake_sleep(s: float):
        sleeps.append(s)
        fake_now[0] += s

    monkeypatch.setattr(ident.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(ident.time, "sleep", fake_sleep)

    rl = ident.RateLimiter(0.2)
    # Pre-prime _last as if a wait() just happened. This exercises the
    # interesting branch: caller does some work, then wait() sleeps just
    # enough to enforce the minimum gap.
    rl._last = fake_now[0]
    fake_now[0] += 0.05  # Caller does 50 ms of work.
    rl.wait()
    assert len(sleeps) == 1
    assert 0.10 <= sleeps[0] <= 0.20


# --------------------------------------------------------------------------
# Candidate query: structural sanity (no DB call)
# --------------------------------------------------------------------------


def test_candidate_query_filters_to_linked_filers_with_ticker():
    sql = ident.CANDIDATE_QUERY
    assert "master_employer_source_ids" in sql
    assert "source_system IN ('sec', 'sec_companies')" in sql
    assert "ticker IS NOT NULL" in sql
    assert "ORDER BY effective_workers DESC NULLS LAST" in sql
