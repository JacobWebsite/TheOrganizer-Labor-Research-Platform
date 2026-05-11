"""Download queued 10-K HTML documents to disk and mark progress.

Step 2 of the 10-K text-mining foundation. Reads from
``sec_10k_filings_to_download``, writes the primary 10-K HTML document for
each row to ``files/sec_10k/{cik}/{accession}.html``, and updates
``load_sec_10k_progress``.

Resumable
---------
Skips any (cik, accession) whose progress row is already ``status='downloaded'``
AND whose target file exists. Re-running on the same queue is a near-no-op
once the queue is fully consumed.

Rate limit
----------
5 req/sec (well under SEC's 10/sec ceiling). A full 1,500-filing run is
~5-7 minutes wall-clock plus disk-write time (10-K HTML averages ~3-15 MB).

Usage
-----
::

    py scripts/etl/sec_10k/download_10k_batch.py --limit 5      # smoke test
    py scripts/etl/sec_10k/download_10k_batch.py                # full queue
    py scripts/etl/sec_10k/download_10k_batch.py --retry-failed # re-fetch errors

Verification
------------
::

    SELECT status, COUNT(*) FROM load_sec_10k_progress GROUP BY status;
    -- Expect: 'downloaded' = N, 'pending' = 0, 'http_error' / 'no_doc' = small
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from db_config import get_connection  # noqa: E402

_log = logging.getLogger("etl.sec_10k.download")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "LaborDataPlatform/1.0 (jakewartel@gmail.com)",
)
RATE_LIMIT_S = 0.2  # 5 req/sec
DOWNLOAD_ROOT = ROOT / "files" / "sec_10k"
HTTP_TIMEOUT_S = 60  # 10-Ks can be 10+ MB, give the connection time.


class RateLimiter:
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


# --------------------------------------------------------------------------
# Queue read
# --------------------------------------------------------------------------


@dataclass
class QueueRow:
    cik: int
    accession: str
    primary_document: str | None
    company_name: str | None
    ticker: str | None
    rank_position: int | None


SELECT_PENDING = """
SELECT
    f.cik,
    f.accession,
    f.primary_document,
    f.company_name,
    f.ticker,
    f.rank_position
FROM sec_10k_filings_to_download f
LEFT JOIN load_sec_10k_progress p
       ON p.cik = f.cik AND p.accession = f.accession
WHERE f.accession <> 'NO_10K'
  AND (
        p.status IS NULL
     OR p.status = 'pending'
     {extra_clause}
  )
ORDER BY f.rank_position NULLS LAST, f.cik
{limit_clause}
"""


def fetch_pending(
    conn,
    limit: int | None,
    retry_failed: bool,
) -> list[QueueRow]:
    """Read rows from the queue that still need a download.

    ``retry_failed`` widens the WHERE clause to also pick up rows with
    ``http_error`` / ``no_doc`` / ``parse_error`` statuses.
    """
    extra = (
        " OR p.status IN ('http_error', 'no_doc', 'parse_error')"
        if retry_failed
        else ""
    )
    limit_clause = f"LIMIT {int(limit)}" if limit and limit > 0 else ""
    sql = SELECT_PENDING.format(extra_clause=extra, limit_clause=limit_clause)
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [
        QueueRow(
            cik=int(r[0]),
            accession=r[1],
            primary_document=r[2],
            company_name=r[3],
            ticker=r[4],
            rank_position=int(r[5]) if r[5] is not None else None,
        )
        for r in rows
    ]


# --------------------------------------------------------------------------
# Progress writer
# --------------------------------------------------------------------------

UPSERT_PROGRESS = """
INSERT INTO load_sec_10k_progress (
    cik, accession, status, bytes_written, file_path, last_attempted, notes
) VALUES (
    %s, %s, %s, %s, %s, NOW(), %s
)
ON CONFLICT (cik, accession) DO UPDATE SET
    status         = EXCLUDED.status,
    bytes_written  = EXCLUDED.bytes_written,
    file_path      = EXCLUDED.file_path,
    last_attempted = EXCLUDED.last_attempted,
    notes          = EXCLUDED.notes
"""


def record_progress(
    conn,
    cik: int,
    accession: str,
    status: str,
    bytes_written: int | None,
    file_path: str | None,
    notes: str | None,
) -> None:
    """Upsert the (cik, accession) progress row. Always commits."""
    with conn.cursor() as cur:
        cur.execute(
            UPSERT_PROGRESS,
            (cik, accession, status, bytes_written, file_path, (notes or "")[:500]),
        )
    conn.commit()


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------


def target_path(cik: int, accession: str) -> Path:
    """Local path: ``files/sec_10k/{cik}/{accession}.html``."""
    return DOWNLOAD_ROOT / str(cik) / f"{accession}.html"


def fetch_via_primary_document(
    cik: int, accession: str, primary_document: str | None
) -> tuple[str, bytes] | None:
    """Try the canonical "primary document" path (cheapest, single GET).

    Returns ``(url, body_bytes)`` or ``None`` if the primary document is
    missing / errored / too small to be a real 10-K.
    """
    if not primary_document:
        return None
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession}/{primary_document}"
    )
    _limiter.wait()
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_S
        )
    except requests.RequestException as e:
        _log.warning("primary doc request failed CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    return url, resp.content


def fetch_via_index_scan(
    cik: int, accession: str
) -> tuple[str, bytes] | None:
    """Fallback: scan the filing's ``index.json`` for a 10-K-like .htm file.

    Filing-bundle filenames vary; common patterns:

      * ``aapl-20240928.htm``  (ticker + period)
      * ``form10-k.htm`` / ``10-k.htm``
      * ``aaa-yyyymmdd_10k.htm``

    We score candidates: presence of ``10-k`` / ``10k`` / ``form10`` /
    ticker-style date stamps adds points; obvious exhibit names
    (``ex-21``/``exhibit21``) are excluded.
    """
    idx_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
    )
    _limiter.wait()
    try:
        resp = requests.get(
            idx_url, headers={"User-Agent": USER_AGENT}, timeout=15
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None

    items = (body.get("directory") or {}).get("item") or []
    candidates: list[tuple[int, str, int]] = []  # (score, name, size)
    for it in items:
        name = (it.get("name") or "").lower()
        if not name.endswith((".htm", ".html")):
            continue
        # Exclude exhibits.
        if re.search(r"(^|[\-_])(ex[\-_]?\d|exhibit[\-_]?\d)", name):
            continue
        score = 0
        if re.search(r"10[-_]?k", name):
            score += 10
        if "form10" in name:
            score += 5
        if re.search(r"\d{8}", name):  # date stamp like 20240928
            score += 2
        # Bigger files are more likely to be the actual 10-K body.
        try:
            size = int(it.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        candidates.append((score, it.get("name") or "", size))

    if not candidates:
        return None
    # Highest score first; break ties by file size descending.
    candidates.sort(key=lambda x: (-x[0], -x[2]))
    for score, name, _size in candidates:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"
        _limiter.wait()
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_S
            )
        except requests.RequestException:
            continue
        if resp.status_code != 200 or not resp.content:
            continue
        return url, resp.content
    return None


def download_one(row: QueueRow) -> dict:
    """Download a single 10-K. Returns a dict with status / file_path / etc.

    Status codes:
      * ``downloaded``  -- new file written
      * ``cached``      -- file already on disk (resumed run)
      * ``http_error``  -- both primary + index-scan paths failed
      * ``no_doc``      -- index scan returned zero candidates
    """
    out_path = target_path(row.cik, row.accession)
    result = {
        "cik": row.cik,
        "accession": row.accession,
        "status": "pending",
        "bytes_written": 0,
        "file_path": str(out_path),
        "notes": None,
    }

    if out_path.exists() and out_path.stat().st_size > 0:
        result["status"] = "cached"
        result["bytes_written"] = out_path.stat().st_size
        return result

    fetched = fetch_via_primary_document(
        row.cik, row.accession, row.primary_document
    )
    if not fetched:
        fetched = fetch_via_index_scan(row.cik, row.accession)

    if not fetched:
        result["status"] = "http_error"
        result["notes"] = "both primary-doc and index-scan paths returned no body"
        return result

    url, body = fetched
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(body)
    result["status"] = "downloaded"
    result["bytes_written"] = len(body)
    result["notes"] = url
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap on rows to process this run (0 = no cap).",
    )
    ap.add_argument(
        "--retry-failed",
        action="store_true",
        help="Also pick up rows whose progress is http_error / no_doc.",
    )
    ap.add_argument(
        "--max-failures",
        type=int,
        default=30,
        help="Abort if this many consecutive HTTP failures (rate-limit hint).",
    )
    args = ap.parse_args()

    conn = get_connection()
    pending = fetch_pending(
        conn,
        limit=args.limit if args.limit > 0 else None,
        retry_failed=args.retry_failed,
    )
    _log.info("pending downloads: %d", len(pending))

    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    n_downloaded = 0
    n_cached = 0
    n_failed = 0
    consecutive_failures = 0

    for i, row in enumerate(pending, start=1):
        try:
            res = download_one(row)
        except Exception as e:  # noqa: BLE001
            _log.warning("CIK %s exception: %s", row.cik, e)
            try:
                record_progress(
                    conn,
                    row.cik,
                    row.accession,
                    "parse_error",
                    None,
                    None,
                    f"exception: {e!r}",
                )
            except Exception:  # noqa: BLE001
                conn.rollback()
            consecutive_failures += 1
            n_failed += 1
            if consecutive_failures >= args.max_failures:
                _log.error(
                    "aborting after %d consecutive failures",
                    consecutive_failures,
                )
                break
            continue

        try:
            record_progress(
                conn,
                res["cik"],
                res["accession"],
                res["status"],
                res["bytes_written"],
                res["file_path"],
                res["notes"],
            )
        except Exception as e:  # noqa: BLE001
            _log.warning("CIK %s progress upsert failed: %s", row.cik, e)
            conn.rollback()

        if res["status"] in ("downloaded", "cached"):
            consecutive_failures = 0
            if res["status"] == "downloaded":
                n_downloaded += 1
            else:
                n_cached += 1
        else:
            consecutive_failures += 1
            n_failed += 1

        if i <= 5 or i % 25 == 0:
            _log.info(
                "[%d/%d] CIK %s %s -> %s (%d bytes)",
                i,
                len(pending),
                row.cik,
                (row.company_name or "?")[:40],
                res["status"],
                res["bytes_written"],
            )

        if consecutive_failures >= args.max_failures:
            _log.error(
                "aborting after %d consecutive failures",
                consecutive_failures,
            )
            break

    conn.close()
    _log.info(
        "done: %d downloaded, %d cached, %d failed (of %d pending)",
        n_downloaded,
        n_cached,
        n_failed,
        len(pending),
    )
    return 0 if n_failed < args.max_failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
