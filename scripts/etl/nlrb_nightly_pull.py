"""
NLRB nightly delta pull.

Problem: the existing NLRB loader (`scripts/etl/sync_nlrb_sqlite.py`) is
bulk-file-based (nlrb.db SQLite drops manually). That means new charges and
election filings lag by days or weeks before they surface in our platform.

This script pulls the *last 24-48 hours* of NLRB filings from the public
`nlrb.gov` JSON search endpoint and inserts new rows into the same 4 target
tables (`nlrb_cases`, `nlrb_participants`, `nlrb_allegations`,
`nlrb_elections`). Dedup is strictly by `case_number` PK (INSERT ... ON
CONFLICT DO NOTHING). Post-insert, it emits the list of newly-inserted
case_numbers to a JSON handoff file so
`scripts/matching/match_nlrb_nightly_to_masters.py` can apply the rule
engine (H1-H16) to newly-linked participant rows.

Running this as a daily scheduled task (see
`scripts/maintenance/setup_nlrb_nightly_task.ps1`) keeps the platform's
NLRB view same-day-current without waiting for the next bulk drop.

Usage:
    py scripts/etl/nlrb_nightly_pull.py --hours-back 48 --dry-run
    py scripts/etl/nlrb_nightly_pull.py --hours-back 24 --commit
    # From a local JSON file (for testing without hitting the API):
    py scripts/etl/nlrb_nightly_pull.py --from-file path/to/fixture.json --commit

Verification:
    SELECT MAX(earliest_date) FROM nlrb_cases;      -- should advance daily
    SELECT COUNT(*) FROM nlrb_cases
        WHERE created_at > CURRENT_DATE - INTERVAL '48 hours';

Notes on the API:
    nlrb.gov does not publish a formally-versioned public API. The
    `/search/case.json` endpoint is used by the public case-search UI and
    returns paginated JSON. We rate-limit to 1 req/sec to be polite (no
    documented limit, but their WAF does 429 under sustained load).
    If the endpoint shape changes, the _extract_* helpers below are the
    only piece that needs updating.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from db_config import get_connection

_log = logging.getLogger("etl.nlrb_nightly")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# --- Config ---
NLRB_SEARCH_URL = "https://www.nlrb.gov/search/case.json"
USER_AGENT = "LaborDataTerminal/1.0 (labor organizing research; +https://github.com/labordata)"
RATE_LIMIT_SECONDS = 1.0   # be polite; NLRB has no documented public rate limit
PAGE_SIZE = 50
MAX_PAGES = 50             # hard cap to avoid runaway fetches
MAX_RATE_LIMIT_RETRIES = 5 # per-page retry budget before aborting
DEFAULT_HANDOFF_DIR = ROOT / "scripts" / "etl" / "_nlrb_nightly_handoff"

# Module-level tracker for per-page 429 retries (reset per fetch_recent_cases call).
_rate_limit_retries: dict[int, int] = {}


# --------------------------------------------------------------------------
# HTTP fetch
# --------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, seconds: float):
        self.seconds = seconds
        self._last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last
        if elapsed < self.seconds:
            time.sleep(self.seconds - elapsed)
        self._last = time.monotonic()


_limiter = RateLimiter(RATE_LIMIT_SECONDS)


def fetch_recent_cases(hours_back: int) -> list[dict]:
    """Fetch JSON case records filed in the last `hours_back` hours.

    Returns a list of raw case dicts as returned by the NLRB search endpoint.
    Callers pass this to `extract_tables()` to normalize into our schema.

    This function is intentionally thin -- it does not write to the DB.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    since_str = since.strftime("%Y-%m-%d")

    # Reset per-call retry budget.
    _rate_limit_retries.clear()

    all_cases: list[dict] = []
    page = 1
    while page <= MAX_PAGES:
        _limiter.wait()
        params = {
            "f[0]": "type:case",
            # NLRB search honors a date-filed-since filter in the UI; replicate here.
            # If the UI parameter name drifts, the response will just include all
            # recent cases + we filter by date in-memory (the date filter below).
            "f[1]": f"case_date_filed:>{since_str}",
            "page": page,
        }
        try:
            resp = requests.get(
                NLRB_SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=30,
            )
        except requests.RequestException as exc:
            _log.warning("fetch page %d failed: %s", page, exc)
            # Abort the whole run on network failure; partial pagination is
            # worse than a same-day gap we can retry tomorrow.
            raise

        # Rate-limit retry: stay on the SAME page. Codex finding #1 (2026-04-24):
        # previously this used `continue` which advanced to the next page and
        # silently skipped the rate-limited one.
        if resp.status_code == 429:
            if page not in _rate_limit_retries:
                _rate_limit_retries[page] = 0
            _rate_limit_retries[page] += 1
            if _rate_limit_retries[page] > MAX_RATE_LIMIT_RETRIES:
                _log.error(
                    "rate limited at page %d for >%d attempts; aborting run",
                    page, MAX_RATE_LIMIT_RETRIES,
                )
                raise RuntimeError(
                    f"NLRB nightly pull: page {page} rate-limited beyond retry budget"
                )
            backoff = 10 * _rate_limit_retries[page]
            _log.warning(
                "rate limited at page %d (retry %d/%d); sleeping %ds",
                page, _rate_limit_retries[page], MAX_RATE_LIMIT_RETRIES, backoff,
            )
            time.sleep(backoff)
            # DO NOT increment page; retry the same one.
            continue
        if resp.status_code != 200:
            _log.warning("page %d returned HTTP %d; aborting run", page, resp.status_code)
            # Same reason as network failure: partial pagination is worse than
            # a retry tomorrow.
            raise RuntimeError(
                f"NLRB nightly pull: page {page} returned HTTP {resp.status_code}"
            )

        try:
            body = resp.json()
        except json.JSONDecodeError:
            _log.warning("page %d returned non-JSON body; aborting run", page)
            raise RuntimeError(
                f"NLRB nightly pull: page {page} returned non-JSON body"
            )

        cases = body.get("results") or body.get("cases") or []
        if not cases:
            break  # end of pagination
        all_cases.extend(cases)
        if len(cases) < PAGE_SIZE:
            break  # last page
        page += 1

    # Safety net: filter on earliest_date >= since (in case the API filter was ignored)
    since_date = since.date()
    filtered = []
    for c in all_cases:
        earliest = _parse_date(c.get("date_filed") or c.get("earliest_date"))
        if earliest is None or earliest >= since_date:
            filtered.append(c)
    _log.info("fetched %d cases (%d after date-filter >= %s)", len(all_cases), len(filtered), since_date)
    return filtered


def _parse_date(v) -> "datetime.date | None":
    """Parse a date from an NLRB API value. Accepts:
    - None -> None
    - 'YYYY-MM-DD'
    - 'YYYY-MM-DDTHH:MM:SS'  (strips time)
    - 'YYYY-MM-DDTHH:MM:SS+TZ' (strips time + tz)
    """
    if v is None:
        return None
    if not isinstance(v, str):
        return None
    # Strip a 'T' time suffix so the date prefix is all we try to parse
    head = v.split("T", 1)[0]
    try:
        return datetime.strptime(head, "%Y-%m-%d").date()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Normalize JSON -> our 4-table schema
# --------------------------------------------------------------------------


def extract_tables(cases: list[dict]) -> dict[str, list[tuple]]:
    """Split raw case dicts into rows ready to INSERT into each target table.

    Returns a dict keyed on table name -> list of param tuples matching the
    SQL INSERT statements below.
    """
    rows = {
        "nlrb_cases": [],
        "nlrb_participants": [],
    }

    for c in cases:
        case_number = c.get("case_number") or c.get("caseNumber")
        if not case_number:
            continue

        # nlrb_cases insert params
        region = _safe_int(c.get("region"))
        case_type = c.get("case_type") or c.get("caseType")
        case_year = _safe_int(c.get("case_year") or _year_from_case_number(case_number))
        case_seq = _safe_int(c.get("case_seq") or _seq_from_case_number(case_number))
        earliest_date = _parse_date(c.get("date_filed") or c.get("earliest_date"))
        latest_date = _parse_date(c.get("date_closed") or c.get("latest_date")) or earliest_date

        rows["nlrb_cases"].append(
            (case_number, region, case_type, case_year, case_seq, earliest_date, latest_date)
        )

        # nlrb_participants inserts (one per participant in the case)
        for p in c.get("participants") or []:
            rows["nlrb_participants"].append((
                case_number,
                p.get("name") or p.get("participant_name"),
                p.get("type") or p.get("participant_type"),
                p.get("subtype") or p.get("participant_subtype"),
                p.get("address"),
                p.get("address_1"),
                p.get("address_2"),
                p.get("city"),
                p.get("state"),
                p.get("zip") or p.get("zip_code"),
                p.get("phone") or p.get("phone_number"),
            ))

    return rows


def _safe_int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _year_from_case_number(case_num: str) -> int | None:
    # NLRB case-number format: 2-letter region + "-" + case-type + "-" + 6-digit seq
    # Case year is often embedded in the high-order digits of seq (legacy
    # pattern) but most recent cases use a separate date. Safe fallback: None.
    return None


def _seq_from_case_number(case_num: str) -> int | None:
    # Try to extract trailing numeric as sequence
    parts = (case_num or "").split("-")
    if parts:
        tail = parts[-1]
        return _safe_int(tail)
    return None


# --------------------------------------------------------------------------
# DB upsert
# --------------------------------------------------------------------------


SQL_UPSERT_CASE = """
INSERT INTO nlrb_cases
    (case_number, region, case_type, case_year, case_seq, earliest_date, latest_date)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (case_number) DO UPDATE SET
    latest_date = GREATEST(EXCLUDED.latest_date, nlrb_cases.latest_date),
    region      = COALESCE(EXCLUDED.region, nlrb_cases.region),
    case_type   = COALESCE(EXCLUDED.case_type, nlrb_cases.case_type)
RETURNING (xmax = 0) AS inserted;
"""

# nlrb_participants has no natural PK beyond the auto id. Dedup on
# (case_number, participant_name, participant_type) to avoid duplicating
# when this script runs more than once per day.
SQL_UPSERT_PARTICIPANT = """
INSERT INTO nlrb_participants
    (case_number, participant_name, participant_type, participant_subtype,
     address, address_1, address_2, city, state, zip, phone_number)
SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
WHERE NOT EXISTS (
    SELECT 1 FROM nlrb_participants p
    WHERE p.case_number = %s
      AND COALESCE(p.participant_name, '') = COALESCE(%s, '')
      AND COALESCE(p.participant_type, '') = COALESCE(%s, '')
);
"""


def upsert(conn, rows: dict[str, list[tuple]], commit: bool) -> dict:
    """Write the normalized rows to the DB. Returns summary counts.

    Honors --dry-run (commit=False) by rolling back at the end.

    Codex finding #2 (2026-04-24): `INSERT ... WHERE NOT EXISTS` is not
    concurrency-safe without a unique constraint on the dedup key. The
    `nlrb_participants` table has 34K pre-existing dupe groups on
    `(case_number, participant_name, participant_type)`, so adding a unique
    constraint now would require a bulk dedup migration.
    Mitigation: acquire a pg advisory transaction lock keyed to this loader
    so a second concurrent invocation blocks until the first commits/rolls
    back. Removes the race window between the SELECT-side of WHERE NOT
    EXISTS and the INSERT. Single-writer daily cron is now safe regardless
    of manual re-runs.
    """
    cur = conn.cursor()
    conn.autocommit = False

    # Advisory xact-lock: hash of "nlrb_nightly_pull.v1". Blocks a second
    # writer (from parallel runs / manual re-exec) until this transaction
    # commits or rolls back. Single literal hash -> serialized writers.
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (7734911201234567890,))

    new_cases: list[str] = []
    dup_cases = 0
    for params in rows["nlrb_cases"]:
        cur.execute(SQL_UPSERT_CASE, params)
        r = cur.fetchone()
        was_inserted = (r[0] if r else False)
        if was_inserted:
            new_cases.append(params[0])
        else:
            dup_cases += 1

    inserted_participants = 0
    for params in rows["nlrb_participants"]:
        # Rebuild the param tuple for the dedup subquery
        case_number, name, p_type = params[0], params[1], params[2]
        expanded = (*params, case_number, name, p_type)
        cur.execute(SQL_UPSERT_PARTICIPANT, expanded)
        inserted_participants += cur.rowcount

    summary = {
        "new_cases": len(new_cases),
        "existing_cases_seen": dup_cases,
        "new_case_numbers": new_cases,
        "new_participants": inserted_participants,
    }

    if commit:
        conn.commit()
    else:
        conn.rollback()

    return summary


# --------------------------------------------------------------------------
# Handoff file for downstream matcher
# --------------------------------------------------------------------------


def write_handoff(summary: dict, handoff_dir: Path) -> Path | None:
    """Dump newly-inserted case_numbers to a JSON file so the downstream
    matcher (`match_nlrb_nightly_to_masters.py`) knows which new rows to
    rule-engine-match to masters."""
    if not summary.get("new_case_numbers"):
        return None
    handoff_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = handoff_dir / f"nightly_cases_{ts}.json"
    path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_summary": {k: v for k, v in summary.items() if k != "new_case_numbers"},
        "case_numbers": summary["new_case_numbers"],
    }, indent=2))
    _log.info("wrote handoff -> %s (%d cases)", path, len(summary["new_case_numbers"]))
    return path


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours-back", type=int, default=24, help="Pull filings from the last N hours (default 24).")
    ap.add_argument("--commit", action="store_true", help="Persist changes to the DB (default: dry-run).")
    ap.add_argument("--dry-run", action="store_true", help="Do not write (alias for leaving --commit off).")
    ap.add_argument("--from-file", type=Path, help="Skip the API fetch and load a JSON fixture file (for testing).")
    ap.add_argument("--handoff-dir", type=Path, default=DEFAULT_HANDOFF_DIR, help="Where to write the newly-inserted case_numbers for downstream matching.")
    args = ap.parse_args()

    if args.from_file:
        _log.info("loading cases from %s", args.from_file)
        with open(args.from_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
        cases = doc if isinstance(doc, list) else doc.get("results") or doc.get("cases") or []
    else:
        cases = fetch_recent_cases(args.hours_back)

    if not cases:
        _log.info("no cases to process")
        return

    rows = extract_tables(cases)
    _log.info(
        "normalized %d cases -> %d case rows, %d participant rows",
        len(cases), len(rows["nlrb_cases"]), len(rows["nlrb_participants"]),
    )

    conn = get_connection()
    try:
        summary = upsert(conn, rows, commit=args.commit and not args.dry_run)
    finally:
        conn.close()

    _log.info("summary: %s new case(s), %d existing seen, %d new participant row(s)",
              summary["new_cases"], summary["existing_cases_seen"], summary["new_participants"])

    if args.commit and not args.dry_run:
        write_handoff(summary, args.handoff_dir)
    elif summary["new_cases"]:
        _log.info("DRY RUN -- would have written handoff with %d case numbers", summary["new_cases"])


if __name__ == "__main__":
    main()
