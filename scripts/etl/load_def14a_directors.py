"""
24Q-12 Board of Directors -- DEF14A proxy parser SKELETON.

Loads board-of-directors data from SEC DEF14A (proxy statement) filings.
Mirrors the architecture of `load_sec_exhibit21.py`: discover the latest
DEF14A per filer via EDGAR submissions JSON, fetch the document, then
extract director rows via a sequence of parser strategies.

THIS IS A SKELETON. The schema, EDGAR client, CLI, and parser harness
are wired up but the actual director-row extraction logic in
`parse_directors()` is intentionally minimal. DEF14A formats vary widely
across filers and over time. Production-quality extraction will require
iteration against real filings; this commit lays the foundation so that
work can begin in a follow-up session without rebuilding the EDGAR
plumbing.

Usage (after schema migration is applied):
    py scripts/etl/load_def14a_directors.py --cik 829224  # Starbucks (single)
    py scripts/etl/load_def14a_directors.py --limit 5 --dry-run
    py scripts/etl/load_def14a_directors.py --limit 100 --commit
    py scripts/etl/load_def14a_directors.py --all --commit  # full ~7800 filers, ~3 hr

Verification:
    SELECT COUNT(*) FROM employer_directors;
    SELECT COUNT(*) FROM director_interlocks;  -- shared directors

Status (2026-05-03): SKELETON. Real extraction strategies to implement
are documented in parse_directors() docstring; the function currently
returns an empty list, which the loader gracefully treats as
'def14a_not_found' for skip tracking.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db_config import get_connection

_log = logging.getLogger("etl.def14a")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "Labor Data Terminal jakewartel@gmail.com",
)
RATE_LIMIT_S = 0.2  # 5 req/sec, polite under SEC's 10/sec limit


class RateLimiter:
    def __init__(self, s: float):
        self.s = s
        self._last = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.s:
            time.sleep(self.s - elapsed)
        self._last = time.monotonic()


_limiter = RateLimiter(RATE_LIMIT_S)


@dataclass
class Director:
    name: str
    age: int | None = None
    position: str | None = None
    director_since_year: int | None = None
    primary_occupation: str | None = None
    other_directorships: list[str] = field(default_factory=list)
    is_independent: bool | None = None
    committees: list[str] = field(default_factory=list)
    compensation_total: float | None = None
    parse_strategy: str = "unknown"


# --------------------------------------------------------------------------
# EDGAR client (mirrors load_sec_exhibit21.py)
# --------------------------------------------------------------------------


def fetch_latest_def14a_accession(cik: int) -> tuple[str, str] | None:
    """Return (accession_no_no_dashes, primary_doc_filename) or None."""
    cik10 = f"{cik:010d}"
    url = EDGAR_SUBMISSIONS_URL.format(cik10=cik10)
    _limiter.wait()
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException as e:
        _log.warning("submissions fetch failed CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None
    recent = (body.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accession = recent.get("accessionNumber") or []
    primary_doc = recent.get("primaryDocument") or []
    for i, form in enumerate(forms):
        # DEF14A is the standard proxy. DEFM14A = merger proxy, ignore.
        # PRE14A is the preliminary version of DEF14A, also ignored.
        if form == "DEF 14A":
            acc = accession[i]
            return acc.replace("-", ""), primary_doc[i] if i < len(primary_doc) else None
    return None


def fetch_def14a_html(cik: int, accession_no_dashes: str, primary_doc: str | None) -> tuple[str, str] | None:
    """Return (html_text, source_url) or None."""
    if primary_doc:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{primary_doc}"
        _limiter.wait()
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        except requests.RequestException as e:
            _log.warning("DEF14A primary doc fetch failed CIK %s: %s", cik, e)
            return None
        if resp.status_code == 200:
            return resp.text, url
    # Fallback: scan filing index for any .htm document
    idx_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/index.json"
    _limiter.wait()
    try:
        resp = requests.get(idx_url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None
    items = (body.get("directory") or {}).get("item") or []
    for it in items:
        name = (it.get("name") or "").lower()
        if name.endswith((".htm", ".html")) and "def14a" not in name and "ex" not in name:
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{it['name']}"
            _limiter.wait()
            try:
                doc_resp = requests.get(doc_url, headers={"User-Agent": USER_AGENT}, timeout=20)
                if doc_resp.status_code == 200:
                    return doc_resp.text, doc_url
            except requests.RequestException:
                continue
    return None


# --------------------------------------------------------------------------
# Director parsing strategies
# --------------------------------------------------------------------------


def parse_directors(html: str) -> list[Director]:
    """Extract director rows from a DEF14A HTML document.

    SKELETON. Production strategies to implement (in order of priority):

    1. Director-summary table. DEF14As frequently include a tabular summary
       like "Name | Age | Director Since | Independent | Committees".
       Parse with BeautifulSoup find_all('table'), score by header row
       presence of {Name, Age, Independent, Committee*}, extract <tr>s.

    2. Director bio sections. Many proxies have a "Directors and Executive
       Officers" section with bio paragraphs starting "<NAME>, age <N>".
       Regex: r"(?P<name>[A-Z][a-zA-Z\\s\\.]+),\\s+age\\s+(?P<age>\\d+)".

    3. Director-comp table. Annual director compensation table reliably
       lists every director name (column 1) with total comp (last col).

    4. Heuristic prose. Sentences like "Mr. Smith was elected as a
       Director in 2018" -- weakest, used as fallback.

    For now this returns an empty list; downstream code treats that as
    "no DEF14A found" via load_def14a_progress.status.
    """
    # Production: BeautifulSoup parse + 4 strategies above
    return []


# --------------------------------------------------------------------------
# DB writer
# --------------------------------------------------------------------------


def write_directors(conn, cik: int, accession: str, source_url: str, directors: list[Director], commit: bool) -> int:
    if not directors:
        return 0

    name_norm_re = re.compile(r"[^a-z0-9\s]")

    def norm(name: str) -> str:
        n = name_norm_re.sub("", name.lower()).strip()
        return re.sub(r"\s+", " ", n)

    # Master ID lookup via canonical match. Cheap because there are O(20)
    # directors per filing; trades a few extra queries for code clarity.
    rows = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT master_id FROM master_employers WHERE LEFT(canonical_name, 100) ILIKE ANY(%s) LIMIT 1",
            ([f"%{cik}%"],),
        )
        master_row = cur.fetchone()
        master_id = master_row[0] if master_row else None

    for d in directors:
        rows.append((
            master_id, cik, accession, None,  # fiscal_year inferred later
            d.name, norm(d.name), d.age, d.position,
            d.director_since_year, d.primary_occupation,
            d.other_directorships or None, d.is_independent,
            d.committees or None, d.compensation_total,
            source_url, d.parse_strategy,
        ))

    sql = """
        INSERT INTO employer_directors (
            master_id, filing_cik, filing_accession_number, fiscal_year,
            director_name, name_norm, age, position,
            director_since_year, primary_occupation,
            other_directorships, is_independent,
            committees, compensation_total,
            source_url, parse_strategy
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s
        )
        ON CONFLICT (filing_accession_number, name_norm) DO NOTHING
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
        written = cur.rowcount
    if commit:
        conn.commit()
    else:
        conn.rollback()
    return written


def record_progress(conn, cik: int, status: str, count: int, notes: str = ""):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO load_def14a_progress (cik, status, directors_found, notes, last_attempted)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (cik) DO UPDATE SET
                status = EXCLUDED.status,
                directors_found = EXCLUDED.directors_found,
                notes = EXCLUDED.notes,
                last_attempted = EXCLUDED.last_attempted
            """,
            (cik, status, count, notes[:500]),
        )
    conn.commit()


# --------------------------------------------------------------------------
# Per-filer pipeline
# --------------------------------------------------------------------------


def process_filer(conn, cik: int, name: str, commit: bool) -> dict:
    result = {"cik": cik, "name": name, "directors_found": 0, "directors_written": 0, "note": None}
    acc_pair = fetch_latest_def14a_accession(cik)
    if not acc_pair:
        result["note"] = "no DEF14A on file"
        record_progress(conn, cik, "def14a_not_found", 0, result["note"])
        return result

    accession, primary_doc = acc_pair
    fetched = fetch_def14a_html(cik, accession, primary_doc)
    if not fetched:
        result["note"] = "DEF14A document fetch failed"
        record_progress(conn, cik, "http_error", 0, result["note"])
        return result

    html, source_url = fetched
    directors = parse_directors(html)
    result["directors_found"] = len(directors)
    if not directors:
        result["note"] = "parser returned 0 rows (skeleton parse_directors is a stub)"
        record_progress(conn, cik, "parse_failed", 0, result["note"])
        return result

    result["directors_written"] = write_directors(conn, cik, accession, source_url, directors, commit=commit)
    record_progress(conn, cik, "ok", result["directors_written"])
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cik", type=int, help="Process a single CIK")
    ap.add_argument("--retry-failed", action="store_true",
                    help="Re-process CIKs whose load_def14a_progress.status is not 'ok'")
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    if args.cik:
        cur.execute("SELECT cik, company_name FROM sec_companies WHERE cik = %s", (args.cik,))
        rows = cur.fetchall()
    elif args.retry_failed:
        cur.execute(
            """
            SELECT s.cik, s.company_name FROM sec_companies s
            JOIN load_def14a_progress p ON p.cik = s.cik
            WHERE p.status <> 'ok' AND s.ticker IS NOT NULL
            ORDER BY p.last_attempted ASC
            """
        )
        rows = cur.fetchall()
    else:
        limit_clause = "" if args.all else f"LIMIT {max(args.limit, 1)}"
        cur.execute(f"""
            SELECT cik, company_name FROM sec_companies
            WHERE ticker IS NOT NULL AND cik IS NOT NULL
            ORDER BY cik
            {limit_clause}
        """)
        rows = cur.fetchall()

    _log.info("processing %d filer(s)", len(rows))
    total_dirs = 0
    total_written = 0
    failures = 0
    for i, (cik, name) in enumerate(rows, 1):
        try:
            result = process_filer(conn, cik, name, commit=args.commit and not args.dry_run)
        except Exception as e:
            _log.warning("CIK %s exception: %s", cik, e)
            failures += 1
            try:
                conn.rollback()
            except Exception:
                pass
            continue
        total_dirs += result["directors_found"]
        total_written += result["directors_written"]
        _log.info("[%d/%d] CIK %s %s -> %d directors (%d written)%s",
                  i, len(rows), cik, name[:40],
                  result["directors_found"], result["directors_written"],
                  f" [{result['note']}]" if result.get("note") else "")

    conn.close()
    _log.info("done: %d filers, %d directors found, %d written, %d failures",
              len(rows), total_dirs, total_written, failures)


if __name__ == "__main__":
    main()
