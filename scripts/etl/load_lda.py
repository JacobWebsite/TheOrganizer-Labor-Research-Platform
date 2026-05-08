"""
Load LDA (Lobbying Disclosure Act) filings via the lda.gov REST API.

24Q-39 Political. Closes the third pillar of Q24 alongside FEC contributions
and (eventually) state political giving. Each LDA "filing" represents a
quarterly LD-1 (registration) or LD-2 (quarterly activity) disclosure
filed by a registrant (lobbying firm) on behalf of a client (the entity
that is paying for the lobbying). Filings carry $ amounts and a list of
issues lobbied on.

API caveats and the parallel-shard strategy:

  - Every LDA REST endpoint hard-caps `page_size=25` regardless of what
    the client requests. With ~108K filings/year, a serial pass over
    5 years would burn ~7 hours of wall time.
  - The bulk-ZIP path under soprweb.senate.gov is dead (DNS).
  - lda.gov/downloads/{year}_{q}.zip returns 403 even with the API key.
  - Workaround: the API supports filtering by `client_state`, so we
    shard the request space by (year, client_state). 5 years x 59
    states = 295 shards. With 5 worker threads we parallelize the slow
    serial loop.
  - One coverage gap: filings whose client has no state (null) are not
    captured here. That's a small fraction of US-firm filings (typically
    foreign-headquartered clients) -- documented in the data source note.

Schema:

  lda_registrants    one row per lobbying firm (registrant.id PK)
  lda_clients        one row per client (client.id PK)
  lda_filings        one row per filing (filing_uuid PK)
  lda_lobbying_activities  flattened activity rows joined to filings

Usage:

  py scripts/etl/load_lda.py                                  # 2021-2025, all states
  py scripts/etl/load_lda.py --years 2024 2025                # subset of years
  py scripts/etl/load_lda.py --years 2025 --states NY VA OH   # subset of states (smoke test)
  py scripts/etl/load_lda.py --workers 3                      # tune parallelism
  py scripts/etl/load_lda.py --reset-schema                   # DROP + CREATE before load

Run time: ~60-90 minutes for 5 years across 59 states with 5 workers.
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection


API_BASE = "https://lda.gov/api/v1"
USER_AGENT = "LaborDataTerminal research/1.0"

# Default scope. Adjustable via CLI.
DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025]

# 50 states + DC + territories + military. Pulled from /constants/general/states/.
STATE_CODES = [
    "AL", "AK", "AS", "AZ", "AR", "CA", "CO", "CT", "DE", "DC",
    "FL", "GA", "GU", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "MP", "OH", "OK",
    "OR", "PA", "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VI", "VA", "WA", "WV", "WI", "WY",
]


# Architecture: fan-out fetch / fan-in write.
#
# Earlier attempts used per-worker DB connections with `INSERT ... ON
# CONFLICT (id)` upserts to lda_registrants and lda_clients. With 5
# workers, the same hot registrants (Akin Gump, K&L Gates, etc.) appear
# across many (year, state) shards and the concurrent transactions
# deadlock on unique-key locks. Switching to ON CONFLICT DO NOTHING did
# not help -- Postgres still acquires the row lock to evaluate the
# unique constraint, so deadlocks still occur within milliseconds.
#
# The fix: workers do API fetch ONLY, no DB. They push fetched filings
# onto a single queue. A dedicated writer thread drains the queue and
# inserts in a single connection. This keeps API parallelism (the
# bottleneck) while serializing DB writes (so no row-lock contention).
#
# Sentinel: a fetcher pushes (None, None, None) to signal it's done.
# The writer counts sentinels and exits when it sees one per fetcher.
_WRITER_QUEUE: "queue.Queue[Optional[Tuple[int, str, List[Dict[str, Any]]]]]" = queue.Queue(maxsize=20)
_WRITER_DONE = object()  # sentinel


def _get_api_key() -> str:
    """Read the LDA API key from .env. The variable name has spaces and
    a dot in it ('LDA.gov REST API 1') so we parse line-by-line rather
    than rely on `python-dotenv` which doesn't tolerate exotic names."""
    env_path = PROJECT_ROOT / ".env"
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("LDA.gov REST API 1="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("LDA.gov REST API 1 not found in .env")


# ---------- Schema ----------

DDL_TABLES = """
DROP TABLE IF EXISTS lda_lobbying_activities CASCADE;
DROP TABLE IF EXISTS lda_filings CASCADE;
DROP TABLE IF EXISTS lda_clients CASCADE;
DROP TABLE IF EXISTS lda_registrants CASCADE;

CREATE TABLE lda_registrants (
    id                  BIGINT PRIMARY KEY,
    house_registrant_id INTEGER,
    name                TEXT NOT NULL,
    description         TEXT,
    address_1           TEXT,
    address_2           TEXT,
    city                TEXT,
    state               TEXT,
    zip                 TEXT,
    country             TEXT,
    contact_name        TEXT,
    contact_telephone   TEXT,
    dt_updated          TIMESTAMPTZ,
    loaded_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lda_clients (
    id                  BIGINT PRIMARY KEY,
    client_id           INTEGER,
    name                TEXT NOT NULL,
    name_norm           TEXT NOT NULL,
    general_description TEXT,
    state               TEXT,
    country             TEXT,
    ppb_state           TEXT,
    ppb_country         TEXT,
    effective_date      DATE,
    loaded_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lda_filings (
    filing_uuid         UUID PRIMARY KEY,
    filing_type         TEXT,
    filing_type_display TEXT,
    filing_year         INTEGER NOT NULL,
    filing_period       TEXT,
    filing_period_display TEXT,
    filing_document_url TEXT,
    income              NUMERIC(14, 2),
    expenses            NUMERIC(14, 2),
    expenses_method     TEXT,
    posted_by_name      TEXT,
    dt_posted           TIMESTAMPTZ,
    termination_date    DATE,
    registrant_id       BIGINT,
    client_id           BIGINT,
    loaded_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE lda_lobbying_activities (
    id                          BIGSERIAL PRIMARY KEY,
    filing_uuid                 UUID NOT NULL,
    general_issue_code          TEXT,
    general_issue_code_display  TEXT,
    description                 TEXT,
    foreign_entity_issues       TEXT,
    lobbyists_json              JSONB
);
"""

DDL_INDEXES = """
CREATE INDEX idx_lda_clients_name_norm
    ON lda_clients (name_norm);
CREATE INDEX idx_lda_clients_name_norm_trgm
    ON lda_clients USING gin (name_norm gin_trgm_ops);
CREATE INDEX idx_lda_clients_state
    ON lda_clients (state) WHERE state IS NOT NULL;
CREATE INDEX idx_lda_filings_client_id
    ON lda_filings (client_id);
CREATE INDEX idx_lda_filings_year_period
    ON lda_filings (filing_year, filing_period);
CREATE INDEX idx_lda_filings_registrant_id
    ON lda_filings (registrant_id);
CREATE INDEX idx_lda_activities_filing_uuid
    ON lda_lobbying_activities (filing_uuid);
CREATE INDEX idx_lda_activities_issue_code
    ON lda_lobbying_activities (general_issue_code) WHERE general_issue_code IS NOT NULL;
"""


# ---------- Helpers ----------

_NORM_RE = re.compile(r"[^a-z0-9 ]+")


def _norm_name(name: str) -> str:
    """Normalize for matching to master_employers.canonical_name. Same
    spirit as the loader normalization for SEC 13F."""
    if not name:
        return ""
    s = name.lower().strip()
    for suffix in (
        " inc", " incorporated", " corporation", " corp", " co", " company",
        " ltd", " plc", " llc", " l p", " lp", " holdings", " group",
    ):
        if s.endswith(suffix):
            s = s[: -len(suffix)].rstrip(" ,.")
            break
    s = _NORM_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    # Effective date is YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    return None


def _parse_dt(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return s  # ISO-8601 with TZ; postgres tolerates


def _parse_num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


# ---------- API fetcher ----------

class TokenBucket:
    """Thread-safe global rate limiter. All workers share one bucket so
    the per-key request rate stays under the LDA API's (undocumented)
    throttle threshold regardless of worker count.

    Usage: every API call should `bucket.acquire()` before issuing the
    request. If no tokens are available, the call sleeps until one is.
    """
    def __init__(self, rate_per_sec: float, capacity: Optional[float] = None):
        self.rate = float(rate_per_sec)
        self.capacity = float(capacity if capacity is not None else max(1.0, rate_per_sec))
        self.tokens = self.capacity
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            wait = (1.0 - self.tokens) / self.rate
            self.tokens = 0.0
            self.last = now + wait
        time.sleep(wait)


class ApiClient:
    def __init__(self, key: str, bucket: Optional[TokenBucket] = None):
        self.key = key
        self.bucket = bucket
        self._pages_fetched = 0
        self._lock = threading.Lock()

    def get_page(self, year: int, state: str, page: int, retries: int = 8):
        """Fetch one page with retry-on-transient. Returns parsed JSON.

        Backoff schedule for retries: 1, 2, 4, 8, 16, 30, 60, 60 seconds.
        Combined with the global TokenBucket throttle, this lets us
        recover from API rate-limits without giving up on a shard.
        """
        url = f"{API_BASE}/filings/?filing_year={year}&client_state={state}&page={page}"
        backoff = [1, 2, 4, 8, 16, 30, 60, 60]
        last_err = None
        for attempt in range(retries):
            if self.bucket is not None:
                self.bucket.acquire()
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Token {self.key}",
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                with self._lock:
                    self._pages_fetched += 1
                return json.loads(body)
            except urllib.error.HTTPError as e:
                # 404 means "no more pages"; pass back as empty
                if e.code == 404:
                    return {"results": [], "next": None, "count": 0}
                # 429 throttling: back off and retry
                if e.code == 429:
                    last_err = e
                    if attempt < retries - 1:
                        time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                last_err = e
                if attempt < retries - 1:
                    time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < retries - 1:
                    time.sleep(backoff[min(attempt, len(backoff) - 1)])
                    continue
                raise
        raise RuntimeError(f"exhausted retries for {url}: {last_err}")

    def pages_fetched(self) -> int:
        with self._lock:
            return self._pages_fetched


# ---------- Insert helpers ----------

# UPSERT-with-DO-UPDATE on a hot row triggers cross-worker lock contention
# (proven via pg_stat_activity in the 2026-05-02 first attempt: 5 workers
# all stalled on transactionid waits because high-volume registrants like
# Akin Gump appear in every shard). Switching to DO NOTHING because the
# fields we display in the card (name, state) are stable across shards --
# the first shard's row is functionally equivalent to any later shard's,
# so losing the would-be UPDATE is fine.
INSERT_REGISTRANT = """
INSERT INTO lda_registrants (
    id, house_registrant_id, name, description,
    address_1, address_2, city, state, zip, country,
    contact_name, contact_telephone, dt_updated
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""

INSERT_CLIENT = """
INSERT INTO lda_clients (
    id, client_id, name, name_norm, general_description,
    state, country, ppb_state, ppb_country, effective_date
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
"""

INSERT_FILING = """
INSERT INTO lda_filings (
    filing_uuid, filing_type, filing_type_display, filing_year,
    filing_period, filing_period_display, filing_document_url,
    income, expenses, expenses_method, posted_by_name, dt_posted,
    termination_date, registrant_id, client_id
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (filing_uuid) DO NOTHING
"""

INSERT_ACTIVITY = """
INSERT INTO lda_lobbying_activities (
    filing_uuid, general_issue_code, general_issue_code_display,
    description, foreign_entity_issues, lobbyists_json
) VALUES (%s, %s, %s, %s, %s, %s)
"""


def _process_filing(cur, filing: Dict[str, Any]) -> Tuple[int, int]:
    """Insert one filing + its embedded registrant/client/activities.

    Returns (n_filings_added, n_activities_added). n_filings_added is 0
    if it was a duplicate (ON CONFLICT DO NOTHING)."""
    reg = filing.get("registrant") or {}
    cli = filing.get("client") or {}

    # Skip filings missing registrant or client (rare, malformed records).
    if not reg.get("id") or not cli.get("id"):
        return 0, 0

    # Upsert registrant
    cur.execute(
        INSERT_REGISTRANT,
        (
            reg["id"],
            _parse_int(reg.get("house_registrant_id")),
            reg.get("name"),
            reg.get("description"),
            reg.get("address_1"),
            reg.get("address_2"),
            reg.get("city"),
            reg.get("state"),
            reg.get("zip"),
            reg.get("country"),
            reg.get("contact_name"),
            reg.get("contact_telephone"),
            _parse_dt(reg.get("dt_updated")),
        ),
    )

    # Upsert client
    cli_name = cli.get("name") or ""
    cur.execute(
        INSERT_CLIENT,
        (
            cli["id"],
            _parse_int(cli.get("client_id")),
            cli_name,
            _norm_name(cli_name),
            cli.get("general_description"),
            cli.get("state"),
            cli.get("country"),
            cli.get("ppb_state"),
            cli.get("ppb_country"),
            _parse_date(cli.get("effective_date")),
        ),
    )

    # Insert filing (UUID; ON CONFLICT skips dupes from cross-shard overlap)
    cur.execute(
        INSERT_FILING,
        (
            filing["filing_uuid"],
            filing.get("filing_type"),
            filing.get("filing_type_display"),
            filing["filing_year"],
            filing.get("filing_period"),
            filing.get("filing_period_display"),
            filing.get("filing_document_url"),
            _parse_num(filing.get("income")),
            _parse_num(filing.get("expenses")),
            filing.get("expenses_method"),
            filing.get("posted_by_name"),
            _parse_dt(filing.get("dt_posted")),
            _parse_date(filing.get("termination_date")),
            reg["id"],
            cli["id"],
        ),
    )
    n_filings = cur.rowcount or 0

    # Insert lobbying activities (only on first insert; if filing is a dupe,
    # activities are presumed already inserted).
    n_activities = 0
    if n_filings == 1:
        for act in filing.get("lobbying_activities") or []:
            lob_json = json.dumps(act.get("lobbyists") or [])
            cur.execute(
                INSERT_ACTIVITY,
                (
                    filing["filing_uuid"],
                    act.get("general_issue_code"),
                    act.get("general_issue_code_display"),
                    act.get("description"),
                    act.get("foreign_entity_issues"),
                    lob_json,
                ),
            )
            n_activities += 1

    return n_filings, n_activities


# ---------- Fetcher (no DB) ----------

def fetch_shard(api: ApiClient, year: int, state: str) -> Dict[str, Any]:
    """Walk every page of (year, state) and push the collected filings
    onto _WRITER_QUEUE. No DB calls -- workers are pure-IO.

    Returns a status dict for the orchestrator's progress log.
    """
    all_filings: List[Dict[str, Any]] = []
    page = 1
    err: Optional[str] = None
    while True:
        try:
            data = api.get_page(year, state, page)
        except Exception as e:
            err = f"fetch error page {page}: {e}"
            break
        rows = data.get("results") or []
        all_filings.extend(rows)
        if not data.get("next") or not rows:
            break
        page += 1

    # Push the shard's filings to the writer. The writer's queue is
    # bounded so a runaway fetcher cannot blow up memory.
    _WRITER_QUEUE.put((year, state, all_filings))

    return {
        "year": year,
        "state": state,
        "fetched": len(all_filings),
        "pages": page,
        "error": err,
    }


# ---------- Writer (single thread, single DB connection) ----------

def writer_thread(stop_signal: threading.Event) -> Dict[str, int]:
    """Single-threaded DB writer. Drains _WRITER_QUEUE, processing each
    shard's filings through _process_filing. Commits per shard so
    progress is durable. Returns aggregate counts when stop_signal is set
    AND the queue is drained.

    The writer never sees concurrent transactions on lda_registrants /
    lda_clients, which is what eliminates the deadlocks the parallel-
    workers approach hit.
    """
    conn = get_connection()
    cur = conn.cursor()
    total_filings = 0
    total_activities = 0
    shards_seen = 0

    while True:
        try:
            item = _WRITER_QUEUE.get(timeout=1.0)
        except queue.Empty:
            if stop_signal.is_set():
                break
            continue

        if item is None or item == _WRITER_DONE:
            _WRITER_QUEUE.task_done()
            continue

        year, state, filings = item
        shards_seen += 1
        n_f = 0
        n_a = 0

        try:
            for filing in filings:
                f, a = _process_filing(cur, filing)
                n_f += f
                n_a += a
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"  WRITER error on {year}-{state}: {e}", flush=True)

        total_filings += n_f
        total_activities += n_a
        if n_f > 0:
            elapsed = time.time() - WRITER_START_TIME
            rate = total_filings / elapsed if elapsed > 0 else 0
            print(
                f"  [shard {shards_seen}] {year}-{state}: "
                f"+{n_f:>5,} filings, +{n_a:>5,} activities "
                f"(running total {total_filings:>7,}, {rate:.0f} f/s)",
                flush=True,
            )
        _WRITER_QUEUE.task_done()

    conn.close()
    return {
        "filings": total_filings,
        "activities": total_activities,
        "shards": shards_seen,
    }


# Module-level so writer_thread can read it for the rate calculation.
WRITER_START_TIME = 0.0


# ---------- Orchestrator ----------

def run(years: List[int], states: List[str], workers: int,
        reset_schema: bool, rate_per_sec: float) -> None:
    bucket = TokenBucket(rate_per_sec=rate_per_sec, capacity=max(2.0, rate_per_sec))
    api = ApiClient(_get_api_key(), bucket=bucket)

    # Schema setup
    setup_conn = get_connection()
    setup_cur = setup_conn.cursor()
    if reset_schema:
        setup_conn.autocommit = True
        setup_cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        print("Resetting lda_* tables (indexes deferred)...")
        setup_cur.execute(DDL_TABLES)
        setup_conn.autocommit = False
    setup_conn.close()

    shards = [(y, s) for y in years for s in states]
    print(f"\nDispatching {len(shards):,} shards: {workers} fetchers + 1 writer", flush=True)
    print(f"  years:       {years}", flush=True)
    print(f"  states:      {len(states)}", flush=True)
    print(f"  rate limit:  {rate_per_sec} req/sec global", flush=True)

    t0 = time.time()
    global WRITER_START_TIME
    WRITER_START_TIME = t0

    # Start the single writer thread.
    stop_signal = threading.Event()
    writer_result: Dict[str, int] = {}

    def _writer_runner():
        nonlocal writer_result
        writer_result = writer_thread(stop_signal)

    writer = threading.Thread(target=_writer_runner, name="lda-writer", daemon=False)
    writer.start()

    fetcher_errors: List[Dict[str, Any]] = []
    fetched_total = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_shard, api, y, s): (y, s) for y, s in shards}
        for fut in as_completed(futures):
            res = fut.result()
            completed += 1
            if res.get("error"):
                fetcher_errors.append(res)
                print(
                    f"  [fetcher {completed:>3d}/{len(shards)}] "
                    f"{res['year']}-{res['state']}: FETCH ERROR {res['error']}",
                    flush=True,
                )
            else:
                fetched_total += res["fetched"]
                if completed % 25 == 0 or completed == len(shards):
                    print(
                        f"  [fetchers {completed:>3d}/{len(shards)}] "
                        f"queued {fetched_total:,} filings so far",
                        flush=True,
                    )

    # All fetchers done; signal the writer to drain its queue and exit.
    print(f"\n  Fetchers done ({fetched_total:,} filings queued). Waiting for writer...", flush=True)
    stop_signal.set()
    writer.join()
    total_filings = writer_result.get("filings", 0)
    total_activities = writer_result.get("activities", 0)
    errors = fetcher_errors

    if reset_schema:
        # Build indexes after the bulk load (much faster than per-row)
        print("\nCreating indexes...")
        idx_t = time.time()
        idx_conn = get_connection()
        idx_conn.autocommit = True
        idx_cur = idx_conn.cursor()
        idx_cur.execute(DDL_INDEXES)
        idx_conn.close()
        print(f"  indexes done in {time.time()-idx_t:.0f}s")

    # Update freshness row
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO data_source_freshness
            (source_name, display_name, last_updated, record_count, notes)
        VALUES (
            'lda', 'LDA Lobbying Disclosure Act Filings', %s, %s,
            '24Q-39 political. Senate LDA REST API; sharded by (year, client_state).'
        )
        ON CONFLICT (source_name) DO UPDATE SET
            last_updated = EXCLUDED.last_updated,
            record_count = EXCLUDED.record_count,
            notes = EXCLUDED.notes
        """,
        (datetime.now(timezone.utc), total_filings),
    )
    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print(f"TOTAL: {total_filings:,} filings + {total_activities:,} activities")
    print(f"       in {elapsed/60:.1f} min ({api.pages_fetched():,} API pages fetched)")
    print(f"       errors: {len(errors)}")
    if errors:
        print("\nFailed shards (re-run with --years/--states to retry):")
        for e in errors[:10]:
            print(f"  {e['year']}-{e['state']}: {e['error']}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--years", nargs="+", type=int, default=DEFAULT_YEARS)
    p.add_argument("--states", nargs="+", default=STATE_CODES)
    p.add_argument("--workers", type=int, default=5)
    p.add_argument(
        "--rate-per-sec",
        type=float,
        default=2.5,
        help=(
            "Global API request rate cap (req/sec) shared across all "
            "workers. Default 2.5 keeps us under LDA's observed ~3-5 "
            "req/sec throttle threshold while completing 5y/56-state "
            "load in ~3-4 hours."
        ),
    )
    p.add_argument(
        "--reset-schema",
        action="store_true",
        default=True,
        help="Drop + create tables before load (default true; pass --no-reset-schema to incremental-load)",
    )
    p.add_argument("--no-reset-schema", dest="reset_schema", action="store_false")
    args = p.parse_args()
    run(args.years, args.states, args.workers, args.reset_schema, args.rate_per_sec)


if __name__ == "__main__":
    main()
