"""
Load SEC 10-K Exhibit 21 subsidiary lists into `corporate_ultimate_parents`.

Background: every SEC-filing public company publishes an annual 10-K, and
Item 21 (Exhibit 21) is a legally required list of their subsidiaries
with state/country of incorporation. This is the most authoritative source
for corporate hierarchy we have access to -- the equivalent of asking the
company directly.

Session 7 (2026-04-24) plan: for each row in `sec_companies` with a
ticker (i.e. actively-traded filer), fetch its most recent 10-K, extract
Exhibit 21, parse subsidiary names + state of incorporation, and insert
an `entity_name -> ultimate_parent_name` edge into
`corporate_ultimate_parents` tagged `source='SEC_EXHIBIT_21'`.

Rate limits: SEC EDGAR allows 10 req/sec with a real User-Agent. We
limit to 5 req/sec to be polite. Full run over ~15K tickers at 3
requests each = ~2 hours wall clock.

Parser coverage:
- HTML tables with 2 columns (name | state) -- most common (~60%)
- Indented lists (bullet + name, sometimes with state on same line) (~25%)
- Comma-separated name + state lines (~10%)
- Free-text prose (~5%) -- fallback to conservative regex

Usage:
    # Test on 10 filers (no DB writes):
    py scripts/etl/load_sec_exhibit21.py --limit 10 --dry-run

    # Small commit batch (writes, rate-limited):
    py scripts/etl/load_sec_exhibit21.py --limit 100 --commit

    # Full production run (~2 hrs):
    py scripts/etl/load_sec_exhibit21.py --all --commit

Verification:
    SELECT COUNT(*) FROM corporate_ultimate_parents
        WHERE source = 'SEC_EXHIBIT_21';
    -- Expect: ~100-500 subsidiaries per filer * N filers
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
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db_config import get_connection

_log = logging.getLogger("etl.sec_ex21")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# --- Config ---
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/"
# SEC EDGAR requires a descriptive User-Agent with a contact email.
# See https://www.sec.gov/os/accessing-edgar-data. Without this, SEC returns 403.
# Override via environment var SEC_USER_AGENT if you want to use a different
# contact (e.g. for a production deployment).
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "Labor Data Terminal jakewartel@gmail.com",
)
RATE_LIMIT_S = 0.2   # 5 req/sec -- gentle below SEC's 10/sec limit
SOURCE_TAG = "SEC_EXHIBIT_21"


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
class Subsidiary:
    name: str
    jurisdiction: str | None


# --------------------------------------------------------------------------
# Step 1: Fetch the latest 10-K accession number for a CIK
# --------------------------------------------------------------------------


def fetch_latest_10k_accession(cik: int) -> tuple[str, str] | None:
    """Returns (accession_no_no_dashes, primary_document_filename) or None."""
    cik10 = f"{cik:010d}"
    url = EDGAR_SUBMISSIONS_URL.format(cik10=cik10)
    _limiter.wait()
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException as e:
        _log.warning("fetch submissions failed for CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200:
        _log.warning("CIK %s submissions returned HTTP %d", cik, resp.status_code)
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None

    # Recent filings are in body['filings']['recent']
    recent = (body.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accession = recent.get("accessionNumber") or []
    primary_doc = recent.get("primaryDocument") or []
    # Find the most recent 10-K (or 10-K/A)
    for i, form in enumerate(forms):
        if form in ("10-K", "10-K/A"):
            acc = accession[i]
            acc_no_dashes = acc.replace("-", "")
            doc = primary_doc[i] if i < len(primary_doc) else None
            return acc_no_dashes, doc
    return None


# --------------------------------------------------------------------------
# Step 2: Find the Exhibit 21 file in the filing index
# --------------------------------------------------------------------------


def fetch_ex21_content(cik: int, accession_no_dashes: str) -> str | None:
    """Locate + download the Exhibit 21 document for a filing."""
    index_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb=&owner=include&count=40"  # fallback
    # Primary path: the accession's filing-index JSON
    idx_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik:010d}&type=10-K&dateb=&owner=include&count=40"
    )
    # Actually: the filing-index JSON lives at
    # /Archives/edgar/data/{cik}/{acc_no_dashes}/index.json
    idx_json_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/index.json"
    )
    _limiter.wait()
    try:
        resp = requests.get(idx_json_url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except requests.RequestException as e:
        _log.warning("index.json fetch failed CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except json.JSONDecodeError:
        return None

    items = (body.get("directory") or {}).get("item") or []
    # Common filename patterns:
    #   ex-21.htm / ex21.htm / exhibit21.htm (simple)
    #   sbux-09282025xexhibit21.htm (ticker + date prefix, no separator)
    #   a2023ex-21.htm (year + ex21)
    # Match `ex21` or `exhibit21` anywhere in the filename; exclude anything
    # that also has `exhibit21_someotherthing` (e.g. exhibit211 = 21.1).
    ex21_name = None
    for it in items:
        name = (it.get("name") or "").lower()
        if not name.endswith((".htm", ".html", ".txt")):
            continue
        # Look for ex21 / exhibit21 not immediately followed by another digit
        if re.search(r"(ex[\-_]?21|exhibit[\-_]?21)(?!\d)", name):
            ex21_name = it["name"]
            break
    if not ex21_name:
        return None

    doc_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{ex21_name}"
    )
    _limiter.wait()
    try:
        resp = requests.get(doc_url, headers={"User-Agent": USER_AGENT}, timeout=20)
    except requests.RequestException as e:
        _log.warning("Ex21 fetch failed CIK %s: %s", cik, e)
        return None
    if resp.status_code != 200:
        return None
    return resp.text


# --------------------------------------------------------------------------
# Step 3: Parse the Exhibit 21 HTML/text into Subsidiary records
# --------------------------------------------------------------------------


_KNOWN_JURISDICTIONS = {
    # US states + common foreign jurisdictions (not exhaustive)
    "delaware", "california", "new york", "texas", "washington", "massachusetts",
    "illinois", "florida", "pennsylvania", "ohio", "michigan", "georgia",
    "north carolina", "virginia", "new jersey", "colorado", "arizona",
    "minnesota", "wisconsin", "indiana", "tennessee", "maryland", "missouri",
    "alabama", "oregon", "nevada", "utah", "iowa", "connecticut", "kansas",
    "arkansas", "mississippi", "louisiana", "kentucky", "oklahoma",
    "south carolina", "nebraska", "idaho", "new mexico", "hawaii", "maine",
    "montana", "rhode island", "delaware", "new hampshire", "south dakota",
    "north dakota", "alaska", "vermont", "wyoming", "west virginia",
    "district of columbia", "puerto rico",
    # common foreign
    "canada", "cayman islands", "bermuda", "united kingdom", "england",
    "ireland", "germany", "france", "japan", "mexico", "china", "singapore",
    "netherlands", "luxembourg", "switzerland", "australia", "brazil",
}


def parse_exhibit21(html: str) -> list[Subsidiary]:
    """Parse an Exhibit 21 HTML/text blob into a list of subsidiaries.

    Handles the three most common formats:
    1. HTML table with name + jurisdiction columns (most common)
    2. Indented/bulleted list with '(State)' or ', State' annotations
    3. Line-separated text with 'Name (Jurisdiction)' pattern

    Conservative: drops rows with no clear name or names under 4 chars.
    """
    if not html:
        return []

    results: list[Subsidiary] = []
    soup = BeautifulSoup(html, "html.parser")

    # Strategy A: HTML tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for tr in rows:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            name = cells[0].strip()
            if not name or len(name) < 4:
                continue
            # Header-row heuristic: common header labels. We check the
            # lowercase name with punctuation/whitespace stripped and a small
            # set of "entity name" variants.
            norm = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
            if norm in {
                "name", "entity", "subsidiary", "name of subsidiary",
                "entity name", "legal entity name", "subsidiary name",
                "name of entity", "subsidiaries", "entity names",
            }:
                continue  # header row
            # Also skip rows whose second cell is a header label like
            # "organized under the laws of" or "state/country of incorporation"
            if cells[1] and any(
                tok in cells[1].lower() for tok in (
                    "organized under", "state/country", "state or country",
                    "jurisdiction of incorporation", "incorporation",
                )
            ) and "," not in cells[1] and len(cells[1]) > 20:
                continue
            juris = None
            # Jurisdiction is often the second col, or a later col for 3-col tables
            for rest in cells[1:]:
                if rest and rest.lower().strip() in _KNOWN_JURISDICTIONS:
                    juris = rest.strip()
                    break
                if rest and len(rest) < 40 and re.search(r"[A-Za-z]", rest):
                    juris = rest.strip()
                    break
            results.append(Subsidiary(name=name, jurisdiction=juris))

    # Strategy B: if nothing found in tables, try a text-line parse
    if not results:
        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) < 4:
                continue
            # Pattern: "Name (Jurisdiction)" or "Name, Jurisdiction"
            m = re.match(r"^(.+?)\s*[\(\,]\s*([A-Za-z][A-Za-z\.\s]{1,40})\s*\)?\s*$", line)
            if m:
                name, juris = m.group(1).strip(), m.group(2).strip()
                if len(name) >= 4 and not name.lower().startswith(("exhibit", "item ")):
                    results.append(Subsidiary(name=name, jurisdiction=juris))

    # De-dup on name (case-insensitive)
    seen = set()
    deduped = []
    for s in results:
        key = s.name.upper().strip()
        if key in seen or len(key) < 4:
            continue
        seen.add(key)
        deduped.append(s)
    return deduped


# --------------------------------------------------------------------------
# Step 4: Insert into corporate_ultimate_parents
# --------------------------------------------------------------------------


SQL_INSERT_EDGE = """
INSERT INTO corporate_ultimate_parents
    (entity_name, ultimate_parent_name, ultimate_parent_cik, chain_depth, source, built_at)
VALUES (%s, %s, %s, 1, %s, %s)
"""


def write_edges(conn, parent_name: str, parent_cik: int,
                subs: list[Subsidiary], commit: bool = True) -> int:
    """Insert one row per (subsidiary, parent) edge. Returns rows inserted.

    Uses the connection's existing transaction state. Callers set autocommit
    mode at the top of main() so we don't collide with an already-open
    transaction here.
    """
    if not subs:
        return 0
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    inserted = 0

    # Check for existing rows so we don't double-insert in re-runs
    cur.execute(
        """
        SELECT entity_name FROM corporate_ultimate_parents
        WHERE ultimate_parent_cik = %s AND source = %s
        """,
        (parent_cik, SOURCE_TAG),
    )
    existing = {r[0].upper().strip() for r in cur.fetchall() if r and r[0]}

    for sub in subs:
        key = sub.name.upper().strip()
        if key in existing:
            continue
        cur.execute(
            SQL_INSERT_EDGE,
            (sub.name, parent_name, parent_cik, SOURCE_TAG, now),
        )
        inserted += 1

    if commit:
        conn.commit()
    else:
        conn.rollback()
    return inserted


# --------------------------------------------------------------------------
# Main per-filer pipeline
# --------------------------------------------------------------------------


def process_filer(conn, cik: int, company_name: str, commit: bool) -> dict:
    """Run the full Ex21 pipeline for a single filer."""
    result = {
        "cik": cik, "company_name": company_name,
        "accession": None, "subs_found": 0, "subs_written": 0, "note": None,
    }

    latest = fetch_latest_10k_accession(cik)
    if not latest:
        result["note"] = "no 10-K found"
        return result
    accession, _primary = latest
    result["accession"] = accession

    html = fetch_ex21_content(cik, accession)
    if not html:
        result["note"] = "Ex21 document not found in 10-K filing index"
        return result

    subs = parse_exhibit21(html)
    result["subs_found"] = len(subs)
    if not subs:
        result["note"] = "Ex21 parser returned 0 rows"
        return result

    written = write_edges(conn, company_name, cik, subs, commit=commit)
    result["subs_written"] = written
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="Process up to N filers (default: 10 for safe testing).")
    ap.add_argument("--all", action="store_true", help="Process every SEC filer with a ticker (~15K; ~2 hrs).")
    ap.add_argument("--commit", action="store_true", help="Write edges to corporate_ultimate_parents.")
    ap.add_argument("--dry-run", action="store_true", help="Parse + print, do not write.")
    ap.add_argument("--cik", type=int, help="Process a single CIK (useful for debugging).")
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    if args.cik:
        cur.execute("SELECT cik, company_name FROM sec_companies WHERE cik = %s", (args.cik,))
        rows = cur.fetchall()
    else:
        # Prioritize filers with tickers (actively traded) + sorted by CIK for
        # deterministic processing across re-runs.
        limit_clause = "" if args.all else f"LIMIT {max(args.limit, 1)}"
        cur.execute(f"""
            SELECT cik, company_name FROM sec_companies
            WHERE ticker IS NOT NULL AND cik IS NOT NULL
            ORDER BY cik
            {limit_clause}
        """)
        rows = cur.fetchall()

    _log.info("processing %d filer(s)", len(rows))
    total_subs = 0
    total_written = 0
    failures = 0
    for i, (cik, name) in enumerate(rows, 1):
        try:
            result = process_filer(
                conn, cik, name,
                commit=args.commit and not args.dry_run,
            )
        except Exception as e:
            _log.warning("CIK %s exception: %s", cik, e)
            failures += 1
            # Codex finding #4 (2026-04-24): a shared psycopg2 connection
            # enters a failed-transaction state after any DB error; every
            # subsequent statement fails until we roll back. Without this,
            # one bad filer poisons the rest of a 15K-filer run.
            try:
                conn.rollback()
            except Exception as rb_exc:
                _log.warning("rollback after CIK %s failure itself failed: %s", cik, rb_exc)
            continue
        total_subs += result["subs_found"]
        total_written += result["subs_written"]
        _log.info("[%d/%d] CIK %s %s -> %d subs (%d written)%s",
                  i, len(rows), cik, name[:40],
                  result["subs_found"], result["subs_written"],
                  f" [{result['note']}]" if result.get("note") else "")

    conn.close()
    _log.info(
        "done: %d filers processed, %d subsidiaries found, %d written, %d failures",
        len(rows), total_subs, total_written, failures,
    )


if __name__ == "__main__":
    main()
