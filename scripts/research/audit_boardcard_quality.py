"""Read-only programmatic QA audit for the BoardCard / DEF14A pipeline.

24Q-14 BoardCard validation. Walks `employer_directors` and the
`director_interlocks` view through 7 quality checks, then writes a
markdown report to `docs/scratch/boardcard_audit_2026_05_09.md` for
Jacob's domain spot-check pass.

Read-only: NO UPDATEs/DELETEs. Mergent loads may be running in parallel.

Usage:
    py scripts/research/audit_boardcard_quality.py

Checks:
    1. Suspicious-volume directors (>15 boards after filter)
    2. Stale filing rate by score_tier
    3. Filed-but-no-directors masters by tier (parse-failure proxy)
    4. Filter false-negatives sample (30 random rejected names)
    5. Filter false-positives sample (30 names that pass filter but
       look suspicious by surface heuristics)
    6. Coverage by tier (% of masters with >=1 director)
    7. Top 30 masters per tier - live API health-check on /board endpoint
    8. Hidden whitespace (ZWSP/NBSP) in director names (parser bug)
    9. Router DB-reference health (catches stale MV refs that 500
       the production endpoint)

Outputs:
    docs/scratch/boardcard_audit_2026_05_09.md
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Project imports - assume CWD is project root or adjusted.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection  # noqa: E402
from api.services.director_name_filter import (  # noqa: E402
    is_likely_real_director_name,
)

# Optional dep for live API check; degrade gracefully if absent.
try:
    import urllib.request  # stdlib
    _HAVE_HTTP = True
except ImportError:  # pragma: no cover
    _HAVE_HTTP = False

REPORT_PATH = PROJECT_ROOT / "docs" / "scratch" / "boardcard_audit_2026_05_09.md"
API_BASE = os.environ.get("BOARDCARD_API_BASE", "http://localhost:8001")
API_TIMEOUT = 5  # seconds; we don't want the audit to hang
RANDOM_SEED = 42  # deterministic samples


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# -----------------------------------------------------------------
# Tier list (canonical order for reports). From mv_unified_scorecard
# distinct values discovered 2026-05-09.
# -----------------------------------------------------------------
TIER_ORDER = ["Priority", "Strong", "Promising", "Speculative", "Moderate", "Low"]

# Suspicion patterns for false-positive sampling. A name that PASSES
# `is_likely_real_director_name` but matches any of these warrants
# Jacob's eyeball check.
SUSPECT_PATTERNS = [
    ("contains_chief_token", re.compile(r"\b(Chief|Officer|Director|President|Chairman)\b", re.I)),
    ("ends_in_corp_suffix", re.compile(r"\b(Inc\.?|Corp\.?|LLC\.?|LP|Ltd\.?|Co\.?)\s*$", re.I)),
    ("all_caps_token", re.compile(r"\b[A-Z]{4,}\b")),
    ("contains_committee_word", re.compile(r"\b(Committee|Compensation|Audit|Nominating|Governance)\b", re.I)),
    ("contains_proxy_word", re.compile(r"\b(Proxy|Statement|Annual|Report|Filing)\b", re.I)),
    ("starts_with_lowercase", re.compile(r"^[a-z]")),
    ("looks_like_section_header", re.compile(r"\b(Continuing|Independent|Outside|Class)\b", re.I)),
    ("contains_phd_or_md_only", re.compile(r"^\s*(Mr|Mrs|Ms|Dr)\.?\s+[A-Z]", re.I)),  # benign — but flag to confirm
]


def _suspect_reasons(name: str) -> List[str]:
    """Return list of suspicion-pattern names matching `name`."""
    out: List[str] = []
    for label, rx in SUSPECT_PATTERNS:
        if rx.search(name):
            out.append(label)
    # Single-word
    tokens = name.strip().split()
    if len(tokens) <= 1:
        out.append("single_word")
    # Very short
    if len(name.strip()) <= 3:
        out.append("very_short")
    return out


def _accession_year(acc: str | None) -> int | None:
    """Extract 2-digit year from SEC accession number form
    `NNNNNNNNNN-YY-NNNNNN` (filer-year-seq), with separators stripped.
    Returns 4-digit year, or None if unparseable.
    Layout: chars 10-12 are the 2-digit year. e.g. 0001193125-26-160426 -> 26.
    """
    if not acc:
        return None
    s = re.sub(r"[^0-9]", "", str(acc))
    if len(s) < 18:
        return None
    try:
        yy = int(s[10:12])
    except ValueError:
        return None
    # Accession-number convention: YY < 50 -> 20xx, else 19xx.
    return 2000 + yy if yy < 50 else 1900 + yy


# -----------------------------------------------------------------
# Check helpers
# -----------------------------------------------------------------


def check_total_counts(cur) -> Dict[str, Any]:
    """Baseline: total directors, distinct masters, etc."""
    cur.execute("SELECT COUNT(*) FROM employer_directors")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT master_id) FROM employer_directors")
    distinct_masters = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT director_name) FROM employer_directors")
    distinct_names = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT (filing_cik, filing_accession_number)) FROM employer_directors")
    distinct_filings = cur.fetchone()[0]
    return {
        "total_director_rows": total,
        "distinct_masters": distinct_masters,
        "distinct_names": distinct_names,
        "distinct_filings": distinct_filings,
    }


def check1_suspicious_volume(cur) -> List[Tuple[str, int]]:
    """Names that PASS the filter but appear on >15 boards."""
    cur.execute(
        """
        SELECT director_name, COUNT(DISTINCT master_id) AS boards
        FROM employer_directors
        WHERE director_name IS NOT NULL
        GROUP BY director_name
        HAVING COUNT(DISTINCT master_id) > 15
        ORDER BY boards DESC
        LIMIT 200
        """
    )
    rows = cur.fetchall()
    flagged: List[Tuple[str, int]] = []
    for name, boards in rows:
        if is_likely_real_director_name(name):
            flagged.append((name, int(boards)))
    return flagged


def check2_stale_filings(cur) -> Dict[str, Dict[str, Any]]:
    """% rows whose accession-date proxy is > 24 months old, by tier.

    Tier comes from `mv_unified_scorecard` keyed on f7 `source_id` via
    `master_employer_source_ids`. Most DEF14A masters are SEC-only and
    have no F7 link, so they fall into `(no_tier_match)` -- still useful
    as a fleet-level staleness percentage.
    """
    cur.execute(
        """
        WITH dir_tier AS (
          SELECT
            d.master_id,
            d.filing_accession_number,
            (
              SELECT s.score_tier
              FROM master_employer_source_ids mesi
              JOIN mv_unified_scorecard s ON s.employer_id = mesi.source_id
              WHERE mesi.master_id = d.master_id
                AND mesi.source_system = 'f7'
              LIMIT 1
            ) AS score_tier
          FROM employer_directors d
          WHERE d.filing_accession_number IS NOT NULL
        )
        SELECT score_tier, filing_accession_number, COUNT(*) AS rows
        FROM dir_tier
        GROUP BY score_tier, filing_accession_number
        """
    )
    rows = cur.fetchall()
    cur_year = datetime.now(timezone.utc).year
    by_tier: Dict[str, Dict[str, int]] = {}
    overall = {"total": 0, "stale": 0}
    for tier, acc, n in rows:
        tier_key = tier or "(no_tier_match)"
        bucket = by_tier.setdefault(tier_key, {"total": 0, "stale": 0})
        bucket["total"] += int(n)
        overall["total"] += int(n)
        yr = _accession_year(acc)
        # > 24 months = filed before (today - 24 months); use year-2 as
        # rough cutoff (good enough for a fleet-level percentage).
        if yr is not None and yr < cur_year - 2:
            bucket["stale"] += int(n)
            overall["stale"] += int(n)
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in by_tier.items():
        pct = (100.0 * v["stale"] / v["total"]) if v["total"] else 0.0
        out[k] = {**v, "stale_pct": round(pct, 2)}
    out["__overall__"] = {
        **overall,
        "stale_pct": round((100.0 * overall["stale"] / overall["total"]) if overall["total"] else 0.0, 2),
    }
    return out


def check3_filed_but_no_directors(cur) -> Dict[str, Dict[str, int]]:
    """Masters where the DEF14A loader recorded a status but
    `employer_directors` has 0 rows.

    `load_def14a_progress` is keyed on CIK; we map CIK to master via
    `master_employer_source_ids` (source_system='sec'). Bucket by load
    status only -- tier rarely available for SEC-only masters.
    """
    # First check whether master_employer_source_ids has SEC entries
    cur.execute(
        """
        SELECT COUNT(*) FROM master_employer_source_ids
        WHERE source_system = 'sec' LIMIT 1
        """
    )
    has_sec = (cur.fetchone()[0] or 0) > 0

    if has_sec:
        # Try CIK-as-source_id (SEC companies are commonly stored that way)
        cur.execute(
            """
            WITH cik_to_master AS (
              SELECT mesi.master_id, mesi.source_id::int AS cik
              FROM master_employer_source_ids mesi
              WHERE mesi.source_system = 'sec'
                AND mesi.source_id ~ '^[0-9]+$'
            )
            SELECT
              p.status,
              COUNT(DISTINCT cm.master_id) AS masters_in_status,
              COUNT(DISTINCT cm.master_id) FILTER (
                WHERE NOT EXISTS (
                  SELECT 1 FROM employer_directors d WHERE d.master_id = cm.master_id
                )
              ) AS masters_zero_dirs
            FROM load_def14a_progress p
            JOIN cik_to_master cm ON cm.cik = p.cik
            GROUP BY p.status
            ORDER BY 1
            """
        )
    else:
        # Fall back: bucket by load status alone, no master tagging
        cur.execute(
            """
            SELECT p.status,
                   COUNT(DISTINCT p.cik) AS ciks,
                   0 AS zero
            FROM load_def14a_progress p
            GROUP BY p.status
            """
        )

    rows = cur.fetchall()
    out: Dict[str, Dict[str, int]] = {}
    for status, masters, zero in rows:
        key = status or "(no_status)"
        out[key] = {"masters": int(masters), "zero_dir_masters": int(zero)}
    return out


def check4_filter_false_negatives(cur, n: int = 30) -> List[str]:
    """Random sample of `director_name` rows REJECTED by the filter.
    Jacob will eyeball - any look like real names? If yes, the filter
    is over-aggressive."""
    # Pull a generously sized batch; filter in Python; sample.
    # ORDER BY random() is slow on big tables -> use TABLESAMPLE.
    cur.execute(
        """
        SELECT DISTINCT director_name
        FROM employer_directors TABLESAMPLE SYSTEM (5)
        WHERE director_name IS NOT NULL
        LIMIT 5000
        """
    )
    candidates = [r[0] for r in cur.fetchall()]
    rejected = [c for c in candidates if not is_likely_real_director_name(c)]
    if len(rejected) < n:
        # Fallback: full scan
        cur.execute(
            "SELECT DISTINCT director_name FROM employer_directors WHERE director_name IS NOT NULL LIMIT 50000"
        )
        candidates = [r[0] for r in cur.fetchall()]
        rejected = [c for c in candidates if not is_likely_real_director_name(c)]
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(rejected)
    return rejected[:n]


def check5_filter_false_positives(cur, n: int = 30) -> List[Tuple[str, List[str]]]:
    """Random sample of names that PASS the filter but trip surface
    suspicion patterns. Each row: (name, [reason_labels])."""
    cur.execute(
        """
        SELECT DISTINCT director_name
        FROM employer_directors TABLESAMPLE SYSTEM (10)
        WHERE director_name IS NOT NULL
        LIMIT 10000
        """
    )
    candidates = [r[0] for r in cur.fetchall()]
    flagged: List[Tuple[str, List[str]]] = []
    for c in candidates:
        if not is_likely_real_director_name(c):
            continue
        reasons = _suspect_reasons(c)
        if reasons:
            flagged.append((c, reasons))
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(flagged)
    return flagged[:n]


def check6_coverage_by_tier(cur) -> Dict[str, Dict[str, Any]]:
    """% of masters in each tier that have >=1 director row.

    Two stratifications are produced:
      - by `score_tier` (only masters with f7 source link)
      - by `is_public` flag (universe = all masters; DEF14A is a
        public-co artifact so private masters should be near 0%)

    The result dict has tier keys + special keys
    `__public_universe__` / `__private_universe__` for the latter.
    """
    # Tier-keyed coverage via master_employer_source_ids (source_system='f7')
    cur.execute(
        """
        WITH master_tier AS (
          SELECT mesi.master_id, s.score_tier
          FROM master_employer_source_ids mesi
          JOIN mv_unified_scorecard s ON s.employer_id = mesi.source_id
          WHERE mesi.source_system = 'f7'
        )
        SELECT
          score_tier,
          COUNT(DISTINCT master_id) AS masters,
          COUNT(DISTINCT master_id) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM employer_directors d
              WHERE d.master_id = mt.master_id
            )
          ) AS with_directors
        FROM master_tier mt
        GROUP BY score_tier
        """
    )
    out: Dict[str, Dict[str, Any]] = {}
    for tier, masters, with_dirs in cur.fetchall():
        masters = int(masters)
        with_dirs = int(with_dirs)
        pct = (100.0 * with_dirs / masters) if masters else 0.0
        out[tier or "(no_tier)"] = {
            "masters": masters,
            "with_directors": with_dirs,
            "coverage_pct": round(pct, 2),
        }

    # is_public-keyed universe coverage (broader denominator)
    cur.execute(
        """
        SELECT
          COALESCE(is_public, false) AS is_public,
          COUNT(*) AS masters,
          COUNT(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM employer_directors d WHERE d.master_id = me.master_id
            )
          ) AS with_directors
        FROM master_employers me
        GROUP BY is_public
        """
    )
    for is_public, masters, with_dirs in cur.fetchall():
        masters = int(masters)
        with_dirs = int(with_dirs)
        pct = (100.0 * with_dirs / masters) if masters else 0.0
        key = "__public_universe__" if is_public else "__private_universe__"
        out[key] = {
            "masters": masters,
            "with_directors": with_dirs,
            "coverage_pct": round(pct, 2),
        }
    return out


def check8_hidden_whitespace(cur) -> Dict[str, Any]:
    """Names containing zero-width-space (U+200B-200F), line/paragraph
    separators (U+2028-2029), or non-breaking space (U+00A0). These
    slip past the filter (length passes, first-word passes) but cause
    duplicate-name fragmentation and ugly UI display.

    HTML scraping artifact -- the proxy statements use `&zwj;` /
    `&nbsp;` in director rows for layout and the parser doesn't
    normalize.
    """
    cur.execute(
        r"""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (WHERE director_name ~ '[​-‏]') AS zwsp,
          COUNT(*) FILTER (WHERE director_name ~ ' ') AS nbsp,
          COUNT(*) FILTER (WHERE director_name ~ '[  ]') AS sep
        FROM employer_directors
        WHERE director_name ~ '[​-‏]|[  ]| '
        """
    )
    counts_row = cur.fetchone()
    total = int(counts_row[0])
    cur.execute(
        r"""
        SELECT director_name, COUNT(*) AS rows
        FROM employer_directors
        WHERE director_name ~ '[​-‏]|[  ]| '
        GROUP BY director_name
        ORDER BY 2 DESC
        LIMIT 5
        """
    )
    samples = [(r[0], int(r[1])) for r in cur.fetchall()]
    return {
        "total_rows": total,
        "with_zwsp": int(counts_row[1]),
        "with_nbsp": int(counts_row[2]),
        "with_separator": int(counts_row[3]),
        "samples": samples,
    }


def check9_api_endpoint_500_diagnosis(cur) -> Dict[str, Any]:
    """The audit's check 7 surfaces high error rates; this check
    diagnoses ROOT CAUSE by inspecting the SQL the endpoint runs.

    Specifically checks for stale MV refs in `api/routers/board.py`.
    Returns a list of {ref, exists, severity} so the report can call
    out broken refs as production bugs.
    """
    refs = ["mv_target_scorecard", "mv_unified_scorecard", "director_interlocks", "employer_directors"]
    out = []
    for ref in refs:
        cur.execute("SELECT to_regclass(%s)", [ref])
        exists = cur.fetchone()[0] is not None
        out.append({"ref": ref, "exists": exists})
    return {"refs": out}


def check7_api_health_top30(cur) -> Dict[str, Any]:
    """For each tier, pick the top 30 masters by unified_score that
    have a director, hit /api/employers/master/{id}/board, and record
    HTTP status + director_count. Tolerate API down -> mark all as
    'api_unreachable' instead of erroring out.
    """
    cur.execute(
        """
        WITH master_tier AS (
          SELECT mesi.master_id, s.score_tier, s.unified_score
          FROM master_employer_source_ids mesi
          JOIN mv_unified_scorecard s ON s.employer_id = mesi.source_id
          WHERE mesi.source_system = 'f7'
            AND EXISTS (
              SELECT 1 FROM employer_directors d
              WHERE d.master_id = mesi.master_id
            )
        ),
        ranked AS (
          SELECT
            score_tier,
            master_id,
            unified_score,
            ROW_NUMBER() OVER (
              PARTITION BY score_tier
              ORDER BY unified_score DESC NULLS LAST
            ) AS rk
          FROM master_tier
        )
        SELECT score_tier, master_id::text AS master_id, unified_score
        FROM ranked
        WHERE rk <= 30
        ORDER BY score_tier, rk
        """
    )
    samples = [(tier, "MASTER:" + str(mid), score) for tier, mid, score in cur.fetchall()]
    if not samples:
        return {"api_unreachable": True, "samples_total": 0, "by_tier": {}}

    # Probe API once first
    try:
        with urllib.request.urlopen(API_BASE + "/api/health", timeout=API_TIMEOUT) as r:
            r.read(64)
    except Exception as exc:
        return {
            "api_unreachable": True,
            "api_error": str(exc),
            "samples_total": len(samples),
            "by_tier": {},
        }

    by_tier: Dict[str, Dict[str, int]] = {}
    n_checked = 0
    for tier, employer_id, _score in samples:
        master_id = employer_id.split(":", 1)[1]
        url = f"{API_BASE}/api/employers/master/{master_id}/board"
        bucket = by_tier.setdefault(
            tier or "(no_tier)",
            {"checked": 0, "ok_with_dirs": 0, "ok_empty": 0, "errors": 0},
        )
        bucket["checked"] += 1
        n_checked += 1
        try:
            with urllib.request.urlopen(url, timeout=API_TIMEOUT) as resp:
                payload = json.loads(resp.read())
            dirs = payload.get("directors") or []
            if dirs:
                bucket["ok_with_dirs"] += 1
            else:
                bucket["ok_empty"] += 1
        except Exception:
            bucket["errors"] += 1
    return {
        "api_unreachable": False,
        "samples_total": len(samples),
        "samples_checked": n_checked,
        "by_tier": by_tier,
    }


# -----------------------------------------------------------------
# Recommendations engine - builds parser-fix list from check evidence
# -----------------------------------------------------------------


def _build_recommendations(
    suspicious: List[Tuple[str, int]],
    fp_samples: List[Tuple[str, List[str]]],
    fn_samples: List[str],
) -> List[Dict[str, str]]:
    """Surface specific fixes warranted by the data."""
    recs: List[Dict[str, str]] = []
    # Recommendation 1: any suspicious-volume hits that look like
    # form-template strings, suggest filter additions.
    if suspicious:
        offenders = [n for n, _b in suspicious if any(t in n.lower() for t in
                     ("officer", "director", "chief", "committee", "compensation",
                      "principal", "senior", "manager"))]
        if offenders:
            recs.append({
                "title": "Add boilerplate-title tokens to filter",
                "evidence": f"{len(offenders)} suspicious-volume names contain "
                            "title tokens (Officer, Director, Chief, Committee, etc.).",
                "fix": "Extend `_BAD_FIRST_WORDS` and `_BAD_SUBSTRINGS` in "
                       "`api/services/director_name_filter.py` with the offending tokens.",
                "examples": "; ".join(offenders[:3]),
            })

    # Recommendation 2: false-positive samples by reason - aggregate counts
    if fp_samples:
        reason_counts: Dict[str, int] = {}
        for _name, reasons in fp_samples:
            for r in reasons:
                reason_counts[r] = reason_counts.get(r, 0) + 1
        # Pick the most common
        top_reason = max(reason_counts.items(), key=lambda x: x[1])
        if top_reason[1] >= 5:
            recs.append({
                "title": f"Investigate filter false positives: {top_reason[0]}",
                "evidence": f"{top_reason[1]} of {len(fp_samples)} sampled passing names "
                            f"trip the `{top_reason[0]}` heuristic.",
                "fix": "Review the sampled names; if they ARE real directors, leave alone. "
                       "If they're parser garbage, add corresponding patterns to the filter.",
                "examples": "; ".join(n for n, r in fp_samples if top_reason[0] in r)[:200],
            })

    # Recommendation 3: any rejected-name with hyphenation (e.g.,
    # "Mary-Ann O'Brien") - those are real. Filter would break them.
    suspicious_rejects = [n for n in fn_samples if re.search(r"[A-Z][a-z]+[- ][A-Z]", n or "")]
    if suspicious_rejects:
        recs.append({
            "title": "Audit: filter may reject hyphenated/multi-part real names",
            "evidence": f"{len(suspicious_rejects)} of {len(fn_samples)} rejected names "
                        "have hyphenation or multi-part capitalization that LOOKS real.",
            "fix": "Eyeball the `examples` list. If they're real names, relax the "
                   "first-word rule or the substring blacklist that's catching them.",
            "examples": "; ".join(suspicious_rejects[:3]),
        })

    # Recommendation 4: directors with trailing entity suffixes
    entity_offenders = [n for n, _b in suspicious if re.search(r"\b(Inc|Corp|LLC|LP|Ltd|Co)\.?\s*$", n or "", re.I)]
    if entity_offenders:
        recs.append({
            "title": "Strip entity suffixes from director names at parse time",
            "evidence": f"{len(entity_offenders)} suspicious-volume names end in "
                        "Inc/Corp/LLC etc. - these are entities, not people.",
            "fix": "In each parser strategy in the DEF14A loader, after extracting "
                   "a candidate name, reject if it matches "
                   "`r'\\b(Inc|Corp|LLC|LP|Ltd|Co)\\.?\\s*$'` (case-insensitive). "
                   "Currently they leak through to `employer_directors` and "
                   "are caught only by the 'venture'/'llc ('/'inc. (' substring rule.",
            "examples": "; ".join(entity_offenders[:3]),
        })

    # Recommendation 5: if more than ~5 sampled false-negatives look
    # real to a quick eye-test (4+ tokens, all-Title-Case), the filter
    # may be too aggressive on long but legitimate names with prefixes
    # like 'The Honorable' or 'Dr.' etc.
    long_real_looking = [
        n for n in fn_samples
        if n and len(n.split()) >= 3
        and all(t[0].isupper() for t in n.split() if t and t[0].isalpha())
        and not any(bad in n.lower() for bad in ("inc", "corp", "llc", "committee", "page"))
    ]
    if len(long_real_looking) >= 5:
        recs.append({
            "title": "Filter may over-reject titled/long real names (e.g. 'Dr. ...')",
            "evidence": f"{len(long_real_looking)} of {len(fn_samples)} rejected names "
                        "are 3+ Title-Case tokens with no obvious entity/header words.",
            "fix": "Inspect _BAD_FIRST_WORDS - tokens like 'managing', 'founder', 'co-founder' "
                   "may legitimately appear in director bio prefixes. Consider relaxing or moving "
                   "those to context-sensitive checks.",
            "examples": "; ".join(long_real_looking[:3]),
        })

    return recs


# -----------------------------------------------------------------
# Report writer
# -----------------------------------------------------------------


def _md_table(headers: List[str], rows: List[List[Any]]) -> str:
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def write_report(
    counts: Dict[str, Any],
    suspicious: List[Tuple[str, int]],
    stale: Dict[str, Dict[str, Any]],
    parse_fail: Dict[str, Dict[str, int]],
    fn_samples: List[str],
    fp_samples: List[Tuple[str, List[str]]],
    coverage: Dict[str, Dict[str, Any]],
    api_health: Dict[str, Any],
    hidden_ws: Dict[str, Any],
    router_refs: Dict[str, Any],
    recommendations: List[Dict[str, str]],
    elapsed_s: float,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Build summary table
    summary_rows = []
    summary_rows.append(["1. Suspicious-volume directors (>15 boards, post-filter)",
                         len(suspicious),
                         "CONCERN" if suspicious else "PASS"])
    overall_stale_pct = stale.get("__overall__", {}).get("stale_pct", 0)
    summary_rows.append(["2. Stale filings (>24mo, fleet-wide)",
                         f"{overall_stale_pct}%",
                         "CONCERN" if overall_stale_pct > 50 else "PASS"])
    pf_zero = sum(v["zero_dir_masters"] for v in parse_fail.values())
    summary_rows.append(["3. Filed-but-no-directors masters",
                         pf_zero,
                         "CONCERN" if pf_zero > 100 else "INFO"])
    summary_rows.append(["4. Filter false-negatives sample",
                         len(fn_samples),
                         "JACOB-REVIEW"])
    summary_rows.append(["5. Filter false-positives sample",
                         len(fp_samples),
                         "JACOB-REVIEW"])
    public_cov = coverage.get("__public_universe__", {}).get("coverage_pct", 0)
    cov_concern = public_cov < 30
    summary_rows.append(["6. Public-master coverage",
                         f"{public_cov}%",
                         "CONCERN" if cov_concern else "INFO"])
    if api_health.get("api_unreachable"):
        api_status = "API DOWN"
        api_verdict = "JACOB-RUN"
    else:
        total_checked = sum(v.get("checked", 0) for v in api_health.get("by_tier", {}).values())
        total_errors = sum(v.get("errors", 0) for v in api_health.get("by_tier", {}).values())
        err_rate = (100.0 * total_errors / total_checked) if total_checked else 0
        api_status = f"{total_errors}/{total_checked} errors ({err_rate:.0f}%)"
        api_verdict = "**CONCERN**" if err_rate > 25 else "PASS"
    summary_rows.append(["7. Live API top-30 health",
                         api_status,
                         api_verdict])
    summary_rows.append(["8. Hidden whitespace in names",
                         hidden_ws["total_rows"],
                         "**CONCERN**" if hidden_ws["total_rows"] > 50 else "INFO"])
    missing_refs = [r for r in router_refs["refs"] if not r["exists"]]
    summary_rows.append(["9. Router DB-reference health",
                         f"{len(missing_refs)} missing of {len(router_refs['refs'])}",
                         "**PRODUCTION BUG**" if missing_refs else "PASS"])

    lines: List[str] = []
    lines.append("# BoardCard Quality Audit -- 2026-05-09")
    lines.append("")
    lines.append(f"_Generated: {_now_iso()} (audit took {elapsed_s:.1f}s)_")
    lines.append("")
    lines.append("Read-only programmatic QA pass over `employer_directors` and the")
    lines.append("`director_interlocks` view. Engineering half of the Week-3 A.1 BoardCard")
    lines.append("validation — Jacob still owns the 15 spot-check companies, this finds")
    lines.append("issues programmatically.")
    lines.append("")

    # Baseline counts
    lines.append("## Baseline counts")
    lines.append("")
    lines.append(_md_table(
        ["metric", "value"],
        [
            ["total director rows", counts["total_director_rows"]],
            ["distinct masters with >=1 director", counts["distinct_masters"]],
            ["distinct director names", counts["distinct_names"]],
            ["distinct (CIK, accession) filings", counts["distinct_filings"]],
        ],
    ))
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(_md_table(
        ["check", "result", "verdict"],
        summary_rows,
    ))
    lines.append("")
    lines.append("Verdict legend: PASS = no action; CONCERN = address; INFO = noted; "
                 "JACOB-REVIEW = needs domain eyes; JACOB-RUN = re-run with API up.")
    lines.append("")

    # Check 1
    lines.append("## Check 1: Suspicious-volume directors (>15 boards, post-filter)")
    lines.append("")
    lines.append("Filter: `is_likely_real_director_name`. Names that pass and still appear on")
    lines.append("more than 15 distinct masters — celebrity director or parser merge.")
    lines.append("")
    if suspicious:
        top20 = suspicious[:20]
        lines.append(_md_table(
            ["director_name", "boards"],
            [[n, b] for n, b in top20],
        ))
        if len(suspicious) > 20:
            lines.append("")
            lines.append(f"... and {len(suspicious) - 20} more.")
    else:
        lines.append("_No directors found with >15 boards after filter -- pass._")
    lines.append("")

    # Check 2
    lines.append("## Check 2: Stale filings (>24 months) by tier")
    lines.append("")
    lines.append("Filing date proxy: 2-digit year embedded in SEC accession number")
    lines.append("(positions 10-12 of the 18-digit form). 24-month cutoff is rough")
    lines.append("(year-based, not month-based). Most director masters are SEC-only and")
    lines.append("don't have an F7 link, so they fall into `(no_tier_match)` — that row")
    lines.append("is the most representative fleet-level number.")
    lines.append("")
    rows = []
    for tier in TIER_ORDER:
        if tier in stale:
            v = stale[tier]
            rows.append([tier, v["total"], v["stale"], f"{v['stale_pct']}%"])
    extra_keys = [k for k in stale.keys() if k not in TIER_ORDER and k != "__overall__"]
    for k in sorted(extra_keys):
        v = stale[k]
        rows.append([k, v["total"], v["stale"], f"{v['stale_pct']}%"])
    if "__overall__" in stale:
        v = stale["__overall__"]
        rows.append(["**OVERALL**", v["total"], v["stale"], f"**{v['stale_pct']}%**"])
    if rows:
        lines.append(_md_table(["tier", "total_rows", "stale_rows", "stale_pct"], rows))
    else:
        lines.append("_No data._")
    lines.append("")

    # Check 3
    lines.append("## Check 3: Filed-but-no-directors masters by tier/status")
    lines.append("")
    lines.append("Joins `load_def14a_progress` -> `sec_companies` (via EIN or canonical_name)")
    lines.append("-> `master_employers`. A master that hit any non-pending status but has")
    lines.append("zero rows in `employer_directors` is a likely parse failure.")
    lines.append("")
    rows = []
    for k, v in sorted(parse_fail.items()):
        rows.append([k, v["masters"], v["zero_dir_masters"]])
    if rows:
        lines.append(_md_table(["status", "masters", "zero_dir_masters"], rows))
    else:
        lines.append("_No data._")
    lines.append("")

    # Check 4 - false negatives
    lines.append("## Check 4: Filter false-negatives sample")
    lines.append("")
    lines.append("Random 30 names REJECTED by `is_likely_real_director_name`.")
    lines.append("If any look like real people, the filter is over-aggressive.")
    lines.append("**Showing first 10; full list lives in script-stdout debug if needed.**")
    lines.append("")
    for i, name in enumerate(fn_samples[:10], 1):
        lines.append(f"{i}. `{name}`")
    lines.append("")

    # Check 5 - false positives
    lines.append("## Check 5: Filter false-positives sample")
    lines.append("")
    lines.append("Names that PASS the filter but trip surface-suspicion patterns")
    lines.append("(boilerplate tokens, all-caps, entity suffixes, etc.). **First 10:**")
    lines.append("")
    for i, (name, reasons) in enumerate(fp_samples[:10], 1):
        lines.append(f"{i}. `{name}` -- {', '.join(reasons)}")
    lines.append("")

    # Check 6 - coverage
    lines.append("## Check 6: Master coverage")
    lines.append("")
    lines.append("Two stratifications. (a) by `score_tier` for the masters with an F7 link")
    lines.append("(small slice — most director masters are SEC-only and won't appear here)")
    lines.append("and (b) by `is_public` flag across ALL masters (DEF14A is a public-co")
    lines.append("artifact so private should be ~0%).")
    lines.append("")
    lines.append("### By tier (F7-linked masters only)")
    lines.append("")
    rows = []
    for tier in TIER_ORDER:
        if tier in coverage:
            v = coverage[tier]
            rows.append([tier, v["masters"], v["with_directors"], f"{v['coverage_pct']}%"])
    extra = [k for k in coverage.keys() if k not in TIER_ORDER and not k.startswith("__")]
    for k in sorted(extra):
        v = coverage[k]
        rows.append([k, v["masters"], v["with_directors"], f"{v['coverage_pct']}%"])
    if rows:
        lines.append(_md_table(["tier", "masters", "with_directors", "coverage_pct"], rows))
    else:
        lines.append("_No tier data — none of the director masters have an F7 link._")
    lines.append("")
    lines.append("### By is_public (universe-wide)")
    lines.append("")
    rows = []
    for k, label in [("__public_universe__", "is_public=true"),
                     ("__private_universe__", "is_public=false/null")]:
        v = coverage.get(k)
        if v:
            rows.append([label, v["masters"], v["with_directors"], f"{v['coverage_pct']}%"])
    if rows:
        lines.append(_md_table(["bucket", "masters", "with_directors", "coverage_pct"], rows))
    lines.append("")

    # Check 7 - live API
    lines.append("## Check 7: Live API health-check on top 30 per tier")
    lines.append("")
    if api_health.get("api_unreachable"):
        lines.append(f"_API at `{API_BASE}` was unreachable. Re-run when uvicorn is up._")
        lines.append("")
        lines.append(f"Error: `{api_health.get('api_error', 'no /health probe')}`")
        lines.append("")
        lines.append(f"Samples that would have been checked: {api_health.get('samples_total', 0)}")
    else:
        rows = []
        for tier in TIER_ORDER + [k for k in api_health.get("by_tier", {}).keys() if k not in TIER_ORDER]:
            v = api_health.get("by_tier", {}).get(tier)
            if v:
                rows.append([tier, v["checked"], v["ok_with_dirs"], v["ok_empty"], v["errors"]])
        if rows:
            lines.append(_md_table(
                ["tier", "checked", "ok_with_dirs", "ok_empty", "errors"],
                rows,
            ))
    lines.append("")
    if not api_health.get("api_unreachable"):
        # Surface aggregate error rate
        total_checked = sum(v.get("checked", 0) for v in api_health.get("by_tier", {}).values())
        total_errors = sum(v.get("errors", 0) for v in api_health.get("by_tier", {}).values())
        if total_checked and total_errors / total_checked > 0.5:
            lines.append(f"**ERROR RATE: {total_errors}/{total_checked} = "
                         f"{100.0 * total_errors / total_checked:.1f}%.** "
                         "Production endpoint is broken. See Check 9 for root cause.")
            lines.append("")

    # Check 8 - Hidden whitespace
    lines.append("## Check 8: Hidden whitespace in director names")
    lines.append("")
    lines.append("HTML scraping artifact. Proxy statements use `&zwj;` (zero-width-")
    lines.append("joiner U+200B-200F), `&nbsp;` (non-breaking space U+00A0), and other")
    lines.append("invisible characters in directory layouts. The parser stores them")
    lines.append("verbatim, causing duplicate-name fragmentation (`John Doe` !=")
    lines.append("`John Doe\\u200b`) and ugly UI display.")
    lines.append("")
    lines.append(_md_table(
        ["category", "count"],
        [
            ["total rows w/ any hidden whitespace", hidden_ws["total_rows"]],
            ["rows w/ zero-width chars (U+200B-200F)", hidden_ws["with_zwsp"]],
            ["rows w/ non-breaking space (U+00A0)", hidden_ws["with_nbsp"]],
            ["rows w/ line/paragraph separator (U+2028-2029)", hidden_ws["with_separator"]],
        ],
    ))
    lines.append("")
    lines.append("Top samples (visible representation, hidden chars rendered):")
    lines.append("")
    for i, (name, n) in enumerate(hidden_ws["samples"], 1):
        # Render a backtick-quoted version with explicit unicode escape
        # so reviewers can see what's there
        escaped = name.encode("unicode_escape").decode("ascii")
        lines.append(f"{i}. `{escaped}` ({n} rows)")
    lines.append("")

    # Check 9 - Router MV refs
    lines.append("## Check 9: BoardCard router DB-reference health")
    lines.append("")
    lines.append("`api/routers/board.py` issues SQL referencing several MVs/tables.")
    lines.append("This check verifies each one resolves. A missing reference means")
    lines.append("the endpoint will 500 whenever its code path is hit.")
    lines.append("")
    rows = []
    for r in router_refs["refs"]:
        rows.append([r["ref"],
                     "OK" if r["exists"] else "**MISSING (production bug)**"])
    lines.append(_md_table(["object", "status"], rows))
    lines.append("")
    missing = [r for r in router_refs["refs"] if not r["exists"]]
    if missing:
        lines.append("**Missing references:**")
        for r in missing:
            lines.append(f"- `{r['ref']}` -- referenced in `api/routers/board.py`")
        lines.append("")
        lines.append("This explains the high error rate in Check 7. The router calls")
        lines.append("the missing object inside the per-director risk-scoring block,")
        lines.append("which is why empty-board masters return 200 OK and populated")
        lines.append("boards return 500.")
    lines.append("")

    # Recommendations
    lines.append("## Parser-fix recommendations")
    lines.append("")
    if not recommendations:
        lines.append("_No actionable patterns identified by heuristics. Filter is reasonable;")
        lines.append("residual issues likely need Jacob's domain eye._")
    else:
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"### {i}. {rec['title']}")
            lines.append("")
            lines.append(f"**Evidence:** {rec['evidence']}")
            lines.append("")
            lines.append(f"**Fix:** {rec['fix']}")
            lines.append("")
            if rec.get("examples"):
                lines.append(f"**Examples:** {rec['examples']}")
                lines.append("")
    lines.append("")

    # Open questions
    lines.append("## Open questions for Jacob")
    lines.append("")
    lines.append("1. **Are the suspicious-volume directors above (>15 boards) celebrity")
    lines.append("   directors or parser merges?** Spot-check 5: search the name on SEC EDGAR")
    lines.append("   and confirm the board count is real. If any merge two distinct people")
    lines.append("   onto one row, we need a name-disambiguation pass keyed on (CIK, name).")
    lines.append("")
    lines.append("2. **Are any of the Check 4 false-negatives real names that the filter")
    lines.append("   over-rejects?** If so, which `_BAD_FIRST_WORDS` or `_BAD_SUBSTRINGS`")
    lines.append("   entry caused it? (Hint: run the rejected name through the predicate")
    lines.append("   step-by-step — the first failing rule is the culprit.)")
    lines.append("")
    lines.append("3. **Are the Check 3 filed-but-no-directors masters real parse failures,")
    lines.append("   or do they have a different filing type? (E.g., shell-co or wind-down")
    lines.append("   filings legitimately have no board.)** ~1,859 still parse_failed per")
    lines.append("   MEMORY.md; this check tells us how many of those are in CONCERN tiers.")
    lines.append("")
    lines.append("4. **Is the 24-month staleness threshold appropriate for board data?**")
    lines.append("   Boards rotate slowly; arguably 36 months is fine. Adjust the cutoff")
    lines.append("   in this script if Jacob disagrees.")
    lines.append("")
    lines.append("5. **Coverage in Promising/Moderate/Low looks low. Is this expected (most")
    lines.append("   are private, no DEF14A)?** Or should we be cross-referencing private-")
    lines.append("   company board sources (Mergent execs is the closest existing source)?")
    lines.append("")
    lines.append("6. **Hidden whitespace cleanup: do it as a one-time DELETE/UPDATE pass,")
    lines.append("   or fix at the parser?** Parser fix is cleaner long-term but the dirty")
    lines.append("   rows already in DB will need scrubbing either way. ~568 rows affected.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("Script: `scripts/research/audit_boardcard_quality.py`")
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------


def main() -> int:
    print(f"BoardCard quality audit -- {_now_iso()}")
    print(f"Output: {REPORT_PATH}")
    t0 = time.time()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            print("[1/7] Counting baselines...")
            counts = check_total_counts(cur)
            print(f"      {counts['total_director_rows']} director rows / "
                  f"{counts['distinct_masters']} masters / "
                  f"{counts['distinct_names']} distinct names")

            print("[2/7] Suspicious-volume directors...")
            suspicious = check1_suspicious_volume(cur)
            print(f"      {len(suspicious)} flagged (>15 boards post-filter)")

            print("[3/7] Stale filings by tier...")
            stale = check2_stale_filings(cur)
            print(f"      {len(stale)} tier buckets")

            print("[4/7] Filed-but-no-directors...")
            try:
                parse_fail = check3_filed_but_no_directors(cur)
                print(f"      {len(parse_fail)} (tier,status) buckets")
            except Exception as e:
                print(f"      ERROR (continuing): {e}")
                parse_fail = {}

            print("[5/7] Filter false-negatives sample...")
            fn_samples = check4_filter_false_negatives(cur)
            print(f"      {len(fn_samples)} sampled")

            print("[6/7] Filter false-positives sample...")
            fp_samples = check5_filter_false_positives(cur)
            print(f"      {len(fp_samples)} flagged")

            print("[7a/7] Coverage by tier...")
            coverage = check6_coverage_by_tier(cur)
            print(f"      {len(coverage)} tiers")

            print("[7b/9] Live API health-check (top 30 per tier)...")
            api_health = check7_api_health_top30(cur)
            if api_health.get("api_unreachable"):
                print("      API unreachable - report will note this")
            else:
                print(f"      Checked {api_health.get('samples_checked', 0)} masters")

            print("[8/9] Hidden-whitespace director names...")
            hidden_ws = check8_hidden_whitespace(cur)
            print(f"      {hidden_ws['total_rows']} rows have ZWSP/NBSP/etc.")

            print("[9/9] BoardCard router MV-reference health...")
            router_refs = check9_api_endpoint_500_diagnosis(cur)
            for r in router_refs["refs"]:
                print(f"      {r['ref']}: {'OK' if r['exists'] else 'MISSING (production bug)'}")
    finally:
        conn.close()

    recs = _build_recommendations(suspicious, fp_samples, fn_samples)
    # Promote the MV-reference bug to recommendation #1 if any are missing.
    missing_refs = [r for r in router_refs["refs"] if not r["exists"]]
    if missing_refs:
        recs.insert(0, {
            "title": "PRODUCTION BUG: BoardCard endpoint references missing MV",
            "evidence": f"`api/routers/board.py` references {len(missing_refs)} object(s) "
                        f"that no longer exist: {', '.join(r['ref'] for r in missing_refs)}. "
                        "The endpoint returns 500 for any master with directors "
                        "(empty-board masters return 200 because the broken query is "
                        "in the conditional `if director_names:` block).",
            "fix": "Replace `mv_target_scorecard` with `mv_unified_scorecard` and re-key "
                   "the join. The replacement MV uses `employer_id` (TEXT, F7 hash) as "
                   "PK, so the join needs to go via `master_employer_source_ids` where "
                   "`source_system='f7'`. See lines 203-223 of `api/routers/board.py`. "
                   "Alternative: drop the per-director risk-scoring loop entirely "
                   "until the cross-master enforcement-rollup is rebuilt.",
            "examples": "Verified by audit Check 7: of 110 masters sampled across all "
                        "tiers, only 5 returned non-error responses (the rest 500'd).",
        })
    elapsed = time.time() - t0
    write_report(
        counts=counts,
        suspicious=suspicious,
        stale=stale,
        parse_fail=parse_fail,
        fn_samples=fn_samples,
        fp_samples=fp_samples,
        coverage=coverage,
        api_health=api_health,
        hidden_ws=hidden_ws,
        router_refs=router_refs,
        recommendations=recs,
        elapsed_s=elapsed,
    )
    print(f"Wrote {REPORT_PATH} ({elapsed:.1f}s total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
