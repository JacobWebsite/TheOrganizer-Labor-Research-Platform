"""Identify the most recent 10-K filing for the top ~1,500 SEC filers.

Step 1 of the 10-K text-mining foundation (24Q-16/17/19, Week 2/3 of the
2026-05-04 launch roadmap).

Ranking heuristic
-----------------
Pick SEC filers that are:

* Linked to a master employer (``master_employer_source_ids.source_system IN
  ('sec','sec_companies')``)
* Have an active ticker (``sec_companies.ticker IS NOT NULL``)

ranked by ``effective_employee_count DESC NULLS LAST`` from
``mv_target_scorecard`` (falls back to ``master_employers.employee_count``).
Empirically this puts AT&T / IBM / Citi / Intel / Amazon at the top, which
is what we want for organizing-platform supplier/customer mining.

Output: rows in the staging table ``sec_10k_filings_to_download``
(PK ``(cik, accession)``). Idempotent on re-run -- existing rows refresh
their queue position via ``ON CONFLICT DO UPDATE``.

Rate limit: 5 req/sec (SEC's published max is 10/sec; we stay well below).
Each top-1500 candidate costs exactly one EDGAR submissions-JSON call
(~5 minutes total at 5 req/sec).

Usage
-----
::

    py scripts/etl/sec_10k/identify_recent_10k.py                 # default top 1500
    py scripts/etl/sec_10k/identify_recent_10k.py --limit 50      # smoke test
    py scripts/etl/sec_10k/identify_recent_10k.py --recreate-tables  # drop+create

Verification
------------
::

    SELECT COUNT(*) FROM sec_10k_filings_to_download;
    SELECT status, COUNT(*) FROM load_sec_10k_progress GROUP BY status;
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from db_config import get_connection  # noqa: E402

_log = logging.getLogger("etl.sec_10k.identify")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# --------------------------------------------------------------------------
# EDGAR client
# --------------------------------------------------------------------------

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "LaborDataPlatform/1.0 (jakewartel@gmail.com)",
)
RATE_LIMIT_S = 0.2  # 5 req/sec; SEC fair-use ceiling is 10/sec.


class RateLimiter:
    """Sleep just enough so successive ``wait()`` calls are ``s`` seconds apart."""

    def __init__(self, s: float):
        self.s = s
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.s:
            time.sleep(self.s - elapsed)
        self._last = time.monotonic()


_limiter = RateLimiter(RATE_LIMIT_S)


@dataclass
class TenKFiling:
    cik: int
    accession_no_dashes: str  # e.g. ``000073271726000120``
    accession_dashed: str  # e.g. ``0000732717-26-000120``
    primary_document: str | None
    filing_date: str | None  # YYYY-MM-DD
    report_date: str | None  # YYYY-MM-DD (period end)
    form: str  # ``10-K`` or ``10-K/A``


def fetch_recent_10k(cik: int) -> TenKFiling | None:
    """Look up the most recent ``10-K`` (or ``10-K/A``) for a CIK.

    Returns ``None`` on HTTP errors, JSON-decode failures, or when no 10-K
    is on file. Network is the only side-effect; no DB writes.
    """
    cik10 = f"{cik:010d}"
    url = EDGAR_SUBMISSIONS_URL.format(cik10=cik10)
    _limiter.wait()
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=15
        )
    except requests.RequestException as e:
        _log.warning("submissions fetch failed CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200:
        _log.warning("CIK %s submissions HTTP %d", cik, resp.status_code)
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None

    recent = (body.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    primary_docs = recent.get("primaryDocument") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []

    # Iterate in order; SEC returns most-recent-first.
    for i, form in enumerate(forms):
        if form not in ("10-K", "10-K/A"):
            continue
        acc = accessions[i] if i < len(accessions) else None
        if not acc:
            continue
        return TenKFiling(
            cik=cik,
            accession_no_dashes=acc.replace("-", ""),
            accession_dashed=acc,
            primary_document=primary_docs[i] if i < len(primary_docs) else None,
            filing_date=filing_dates[i] if i < len(filing_dates) else None,
            report_date=report_dates[i] if i < len(report_dates) else None,
            form=form,
        )
    return None


# --------------------------------------------------------------------------
# DDL
# --------------------------------------------------------------------------

DDL_FILINGS_TO_DOWNLOAD = """
CREATE TABLE IF NOT EXISTS sec_10k_filings_to_download (
    cik                BIGINT      NOT NULL,
    accession          VARCHAR(32) NOT NULL,
    accession_dashed   VARCHAR(32) NOT NULL,
    primary_document   TEXT,
    filing_date        DATE,
    report_date        DATE,
    form               VARCHAR(16) NOT NULL,
    company_name       TEXT,
    ticker             VARCHAR(16),
    master_id          BIGINT,
    rank_score         BIGINT,
    rank_position      INTEGER,
    queued_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes              TEXT,
    PRIMARY KEY (cik, accession)
);
CREATE INDEX IF NOT EXISTS ix_sec_10k_filings_filing_date
    ON sec_10k_filings_to_download (filing_date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_sec_10k_filings_rank
    ON sec_10k_filings_to_download (rank_position);
"""

DDL_PROGRESS = """
CREATE TABLE IF NOT EXISTS load_sec_10k_progress (
    cik              BIGINT      NOT NULL,
    accession        VARCHAR(32) NOT NULL,
    status           VARCHAR(32) NOT NULL,
    bytes_written    BIGINT,
    file_path        TEXT,
    last_attempted   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes            TEXT,
    PRIMARY KEY (cik, accession)
);
CREATE INDEX IF NOT EXISTS ix_load_sec_10k_progress_status
    ON load_sec_10k_progress (status);
"""

DDL_DROP = """
DROP TABLE IF EXISTS sec_10k_filings_to_download;
DROP TABLE IF EXISTS load_sec_10k_progress;
"""


def ensure_tables(conn, recreate: bool = False) -> None:
    """Create the two staging tables if missing.

    DDL needs ``autocommit=True`` per CLAUDE.md ETL conventions; we restore
    the prior mode on the way out.
    """
    prior = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            if recreate:
                cur.execute(DDL_DROP)
            cur.execute(DDL_FILINGS_TO_DOWNLOAD)
            cur.execute(DDL_PROGRESS)
    finally:
        conn.autocommit = prior


# --------------------------------------------------------------------------
# Candidate ranking
# --------------------------------------------------------------------------

CANDIDATE_QUERY = """
WITH linked AS (
    SELECT DISTINCT ON (s.cik)
        s.cik,
        s.company_name,
        s.ticker,
        m.master_id,
        COALESCE(ts.effective_employee_count::bigint,
                 m.employee_count::bigint, 0) AS effective_workers
    FROM sec_companies s
    JOIN master_employer_source_ids msi
      ON msi.source_system IN ('sec', 'sec_companies')
     AND msi.source_id::text = s.cik::text
    JOIN master_employers m ON m.master_id = msi.master_id
    LEFT JOIN mv_target_scorecard ts ON ts.master_id = m.master_id
    WHERE s.ticker IS NOT NULL
      AND s.cik IS NOT NULL
    ORDER BY s.cik, effective_workers DESC NULLS LAST
)
SELECT cik, company_name, ticker, master_id, effective_workers
FROM linked
ORDER BY effective_workers DESC NULLS LAST, cik
LIMIT %s
"""


@dataclass
class Candidate:
    cik: int
    company_name: str | None
    ticker: str | None
    master_id: int | None
    rank_score: int


def fetch_candidates(conn, limit: int) -> list[Candidate]:
    """Pull the top ``limit`` SEC filers ranked by employee count."""
    with conn.cursor() as cur:
        cur.execute(CANDIDATE_QUERY, (limit,))
        rows = cur.fetchall()
    return [
        Candidate(
            cik=int(r[0]),
            company_name=r[1],
            ticker=r[2],
            master_id=int(r[3]) if r[3] is not None else None,
            rank_score=int(r[4]) if r[4] is not None else 0,
        )
        for r in rows
    ]


# --------------------------------------------------------------------------
# Upsert
# --------------------------------------------------------------------------

UPSERT_FILING = """
INSERT INTO sec_10k_filings_to_download (
    cik, accession, accession_dashed, primary_document,
    filing_date, report_date, form,
    company_name, ticker, master_id, rank_score, rank_position, queued_at,
    notes
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s, %s, NOW(),
    %s
)
ON CONFLICT (cik, accession) DO UPDATE SET
    accession_dashed = EXCLUDED.accession_dashed,
    primary_document = EXCLUDED.primary_document,
    filing_date      = EXCLUDED.filing_date,
    report_date      = EXCLUDED.report_date,
    form             = EXCLUDED.form,
    company_name     = EXCLUDED.company_name,
    ticker           = EXCLUDED.ticker,
    master_id        = EXCLUDED.master_id,
    rank_score       = EXCLUDED.rank_score,
    rank_position    = EXCLUDED.rank_position,
    notes            = EXCLUDED.notes
"""

UPSERT_PROGRESS_PENDING = """
INSERT INTO load_sec_10k_progress (cik, accession, status, last_attempted)
VALUES (%s, %s, 'pending', NOW())
ON CONFLICT (cik, accession) DO UPDATE SET
    -- Don't clobber a successfully-downloaded row; only refresh pending/error.
    status = CASE
        WHEN load_sec_10k_progress.status IN ('downloaded', 'verified')
        THEN load_sec_10k_progress.status
        ELSE EXCLUDED.status
    END,
    last_attempted = EXCLUDED.last_attempted
"""

UPSERT_NOTE = """
INSERT INTO sec_10k_filings_to_download (
    cik, accession, accession_dashed, primary_document,
    filing_date, report_date, form,
    company_name, ticker, master_id, rank_score, rank_position, queued_at, notes
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s,
    %s, %s, %s, %s, %s, NOW(),
    %s
)
ON CONFLICT (cik, accession) DO UPDATE SET
    notes         = EXCLUDED.notes,
    rank_position = EXCLUDED.rank_position,
    rank_score    = EXCLUDED.rank_score
"""


def queue_candidate(
    conn,
    cand: Candidate,
    rank_position: int,
    filing: TenKFiling | None,
) -> str:
    """Upsert one candidate; if no 10-K on file, store a sentinel note row.

    Returns the status string for logging:
      * ``"queued"`` -- row written, ready for download
      * ``"no_10k"`` -- candidate has no 10-K (ticker may be defunct)
    """
    with conn.cursor() as cur:
        if filing is None:
            # Use a sentinel "no_10k" accession so the (cik, accession) PK
            # is well-defined and the row is idempotent. The download stage
            # filters these out via ``WHERE accession <> 'NO_10K'``.
            cur.execute(
                UPSERT_NOTE,
                (
                    cand.cik,
                    "NO_10K",
                    "NO_10K",
                    None,
                    None,
                    None,
                    "NONE",
                    cand.company_name,
                    cand.ticker,
                    cand.master_id,
                    cand.rank_score,
                    rank_position,
                    "no 10-K found in EDGAR submissions JSON",
                ),
            )
            conn.commit()
            return "no_10k"

        cur.execute(
            UPSERT_FILING,
            (
                cand.cik,
                filing.accession_no_dashes,
                filing.accession_dashed,
                filing.primary_document,
                filing.filing_date,
                filing.report_date,
                filing.form,
                cand.company_name,
                cand.ticker,
                cand.master_id,
                cand.rank_score,
                rank_position,
                None,
            ),
        )
        cur.execute(
            UPSERT_PROGRESS_PENDING,
            (cand.cik, filing.accession_no_dashes),
        )
    conn.commit()
    return "queued"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        type=int,
        default=1500,
        help="Top-N filers to queue (default 1500).",
    )
    ap.add_argument(
        "--recreate-tables",
        action="store_true",
        help="DROP+CREATE the staging tables before queueing.",
    )
    ap.add_argument(
        "--start-rank",
        type=int,
        default=1,
        help="Skip candidates with rank position < this value (resume).",
    )
    ap.add_argument(
        "--max-failures",
        type=int,
        default=20,
        help="Abort if more than this many consecutive HTTP failures.",
    )
    args = ap.parse_args()

    conn = get_connection()
    ensure_tables(conn, recreate=args.recreate_tables)

    candidates = fetch_candidates(conn, args.limit)
    _log.info("ranked %d candidate filers", len(candidates))

    queued = 0
    no_10k = 0
    consecutive_failures = 0

    for rank_position, cand in enumerate(candidates, start=1):
        if rank_position < args.start_rank:
            continue
        try:
            filing = fetch_recent_10k(cand.cik)
        except Exception as e:  # noqa: BLE001
            _log.warning("CIK %s fetch_recent_10k exception: %s", cand.cik, e)
            consecutive_failures += 1
            if consecutive_failures >= args.max_failures:
                _log.error(
                    "aborting: %d consecutive failures (rate-limited?)",
                    consecutive_failures,
                )
                conn.close()
                return 1
            continue

        if filing is None:
            no_10k += 1
            consecutive_failures += 1
        else:
            consecutive_failures = 0

        try:
            status = queue_candidate(conn, cand, rank_position, filing)
        except Exception as e:  # noqa: BLE001
            _log.warning("CIK %s upsert failed: %s", cand.cik, e)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            continue

        if status == "queued":
            queued += 1

        if rank_position % 50 == 0 or rank_position <= 5:
            _log.info(
                "[%d/%d] CIK %s %s -> %s%s",
                rank_position,
                len(candidates),
                cand.cik,
                (cand.company_name or "?")[:40],
                status,
                f" (acc={filing.accession_dashed}, date={filing.filing_date})"
                if filing
                else "",
            )

        if consecutive_failures >= args.max_failures:
            _log.error(
                "aborting: %d consecutive failures (rate-limited?)",
                consecutive_failures,
            )
            conn.close()
            return 1

    conn.close()
    _log.info(
        "done: %d candidates, %d queued, %d no-10k",
        len(candidates),
        queued,
        no_10k,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
