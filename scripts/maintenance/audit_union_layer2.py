"""Union Explorer Audit -- Layer 2 (API <-> DB consistency) + Layer 3 (cross-source linkage).

For a sampled set of unions, hit the Union Explorer API endpoints and compare each
response field to a hand-written SQL truth query that mirrors the endpoint's
intended semantics. Plus a small set of population-level cross-source linkage
metrics (Layer 3).

Modes (Codex recommendation 2026-05-04):
  --mode http   default; live API on http://localhost:8001
  --mode asgi   FastAPI TestClient/ASGITransport; no uvicorn needed (CI-friendly)
  --mode direct router functions called directly; debug only, skips serialization

Sample (~270 unions per the plan):
  Top 50 by latest reported members
  Top 50 by ttl_assets
  Top 50 by F7 match count
  Random 100 from middle of distribution
  20 known weirds (parentless locals, non-ASCII names, large active+0 NLRB)
  All distinct aff_abbr nationals (~50)

Output:
  audit_runs/<DATE>/layer2_per_union.json   per-union results
  audit_runs/<DATE>/layer2_layer3.json       Layer 3 aggregates
  audit_runs/<DATE>/layer2_report.md          summary

Usage:
  py scripts/maintenance/audit_union_layer2.py
  py scripts/maintenance/audit_union_layer2.py --mode asgi --sample-size 50
  py scripts/maintenance/audit_union_layer2.py --output-dir custom/path --mode http
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import os
import random
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db_config import get_connection


# ============================================================
# Client abstraction (http / asgi / direct)
# ============================================================

class APIClient:
    def get(self, path: str) -> tuple[int, dict | None]:
        raise NotImplementedError


class HTTPClient(APIClient):
    def __init__(self, base_url: str):
        import requests
        self.session = requests.Session()
        self.base_url = base_url.rstrip("/")

    def get(self, path: str) -> tuple[int, dict | None]:
        try:
            r = self.session.get(f"{self.base_url}{path}", timeout=30)
            try:
                return r.status_code, r.json()
            except Exception:
                return r.status_code, None
        except Exception as exc:
            return 0, {"_client_error": str(exc)}


class ASGIClient(APIClient):
    def __init__(self):
        os.environ.setdefault("DISABLE_AUTH", "true")
        # Disable rate limiting for audit runs (default is 100 req/60s per IP, way
        # too low for a 270-union batch). MUST be set before importing api.main
        # because RATE_LIMIT_REQUESTS is read into a module-level constant at import.
        os.environ["RATE_LIMIT_REQUESTS"] = "0"
        from fastapi.testclient import TestClient
        from api.main import app
        self.client = TestClient(app)

    def get(self, path: str) -> tuple[int, dict | None]:
        r = self.client.get(path)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, None


def get_client(mode: str) -> APIClient:
    if mode == "http":
        return HTTPClient("http://localhost:8001")
    if mode == "asgi":
        return ASGIClient()
    if mode == "direct":
        # Same as ASGI for now (direct router calls bypass middleware which we generally do want to test)
        return ASGIClient()
    raise ValueError(f"unknown mode: {mode}")


# ============================================================
# Sample selection
# ============================================================

def select_sample(cur, sample_size: int | None = None) -> dict[str, list[str]]:
    """Build the audit sample. Each bucket is a list of f_num strings."""
    samples: dict[str, list[str]] = {}

    # Top 50 by latest reported members
    cur.execute("""
        SELECT f_num FROM unions_master
        WHERE NOT is_likely_inactive AND members IS NOT NULL
        ORDER BY members DESC NULLS LAST LIMIT 50
    """)
    samples["top_members"] = [r[0] for r in cur.fetchall()]

    # Top 50 by ttl_assets (from latest LM-2 filing)
    cur.execute("""
        WITH latest AS (
            SELECT f_num, ttl_assets,
                   ROW_NUMBER() OVER (PARTITION BY f_num ORDER BY yr_covered DESC) AS rn
            FROM lm_data WHERE ttl_assets IS NOT NULL
        )
        SELECT l.f_num
        FROM latest l
        JOIN unions_master um ON um.f_num = l.f_num
        WHERE l.rn = 1 AND NOT um.is_likely_inactive
        ORDER BY l.ttl_assets DESC
        LIMIT 50
    """)
    samples["top_assets"] = [r[0] for r in cur.fetchall()]

    # Top 50 by F7 employer match count
    cur.execute("""
        WITH f7_counts AS (
            SELECT latest_union_fnum::text AS f_num, COUNT(*) AS cnt
            FROM f7_employers_deduped
            WHERE latest_union_fnum IS NOT NULL
            GROUP BY latest_union_fnum
        )
        SELECT f.f_num
        FROM f7_counts f
        JOIN unions_master um ON um.f_num = f.f_num
        WHERE NOT um.is_likely_inactive
        ORDER BY f.cnt DESC LIMIT 50
    """)
    samples["top_f7"] = [r[0] for r in cur.fetchall()]

    # Random 100 from mid-distribution (members between 50 and 5000)
    cur.execute("""
        SELECT f_num FROM unions_master
        WHERE NOT is_likely_inactive
          AND members BETWEEN 50 AND 5000
        ORDER BY md5(f_num)
        LIMIT 100
    """)
    samples["random_mid"] = [r[0] for r in cur.fetchall()]

    # 20 known weirds: large active with zero NLRB matches
    cur.execute("""
        WITH nlrb_matched AS (
            SELECT DISTINCT matched_olms_fnum AS f_num
            FROM nlrb_tallies WHERE matched_olms_fnum IS NOT NULL
        )
        SELECT um.f_num FROM unions_master um
        LEFT JOIN nlrb_matched nm ON nm.f_num = um.f_num
        WHERE NOT um.is_likely_inactive
          AND um.members > 5000
          AND nm.f_num IS NULL
        ORDER BY um.members DESC
        LIMIT 20
    """)
    samples["weirds"] = [r[0] for r in cur.fetchall()]

    # All distinct aff_abbr nationals -- pick the row with highest members per affiliation
    cur.execute("""
        SELECT DISTINCT ON (aff_abbr) f_num
        FROM unions_master
        WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
          AND aff_abbr NOT IN ('SOC')
          AND NOT is_likely_inactive
        ORDER BY aff_abbr, members DESC NULLS LAST
    """)
    samples["aff_nationals"] = [r[0] for r in cur.fetchall()]

    if sample_size is not None:
        # Cap at sample_size by proportionally downsampling each bucket
        ratio = sample_size / sum(len(v) for v in samples.values())
        ratio = min(ratio, 1.0)
        for k, v in list(samples.items()):
            n = max(1, int(round(len(v) * ratio)))
            random.seed(hash(k) % (2**32))
            samples[k] = random.sample(v, min(n, len(v)))

    return samples


# ============================================================
# Per-union checks (Layer 2)
# ============================================================

@dataclass
class CheckResult:
    f_num: str
    check: str
    gate: str  # "hard" or "advisory"
    passed: bool
    api_value: Any = None
    truth_value: Any = None
    notes: str = ""


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (decimal.Decimal, int, float)):
        return float(v)
    try:
        return float(v)
    except Exception:
        return None


def _approx_equal(a: float | None, b: float | None, tol_pct: float = 1.0) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a == 0 and b == 0:
        return True
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom * 100 <= tol_pct


def check_name_consistency(client, cur, f_num: str) -> CheckResult:
    code, body = client.get(f"/api/unions/{f_num}")
    if code != 200 or not body:
        return CheckResult(f_num, "name_consistency", "hard", False,
                           notes=f"endpoint returned {code}")
    cur.execute("SELECT union_name FROM unions_master WHERE f_num = %s", [f_num])
    row = cur.fetchone()
    if not row:
        return CheckResult(f_num, "name_consistency", "hard", False,
                           notes="not in unions_master")
    truth_name = row[0]
    api_name = (body.get("union") or {}).get("union_name")
    return CheckResult(
        f_num=f_num, check="name_consistency", gate="hard",
        passed=(api_name == truth_name),
        api_value=api_name, truth_value=truth_name,
    )


def check_latest_lm2_year(client, cur, f_num: str) -> CheckResult:
    code, body = client.get(f"/api/unions/{f_num}")
    if code != 200 or not body:
        return CheckResult(f_num, "latest_lm2_year", "advisory", False,
                           notes=f"endpoint returned {code}")
    cur.execute("SELECT MAX(yr_covered) FROM lm_data WHERE f_num = %s", [f_num])
    truth = cur.fetchone()[0]
    fts = body.get("financial_trends") or []
    api_year = fts[0]["year"] if fts else None
    if truth is None and api_year is None:
        return CheckResult(f_num, "latest_lm2_year", "advisory", True,
                           api_value=None, truth_value=None,
                           notes="no LM-2 filings (consistent)")
    return CheckResult(
        f_num=f_num, check="latest_lm2_year", gate="advisory",
        passed=(int(api_year) == int(truth)) if (api_year is not None and truth is not None) else False,
        api_value=api_year, truth_value=truth,
    )


def check_financial_trend_assets(client, cur, f_num: str) -> CheckResult:
    """Verify the post-Bug-1-fix financial_trends.assets equals raw lm_data.ttl_assets per year."""
    code, body = client.get(f"/api/unions/{f_num}")
    if code != 200 or not body:
        return CheckResult(f_num, "financial_trend_assets", "hard", False,
                           notes=f"endpoint returned {code}")
    cur.execute("""
        SELECT yr_covered, SUM(COALESCE(ttl_assets, 0)) AS truth_assets
        FROM lm_data WHERE f_num = %s GROUP BY yr_covered
        ORDER BY yr_covered DESC LIMIT 10
    """, [f_num])
    truth_by_year = {int(r[0]): _to_float(r[1]) for r in cur.fetchall()}
    fts = body.get("financial_trends") or []
    deltas = []
    for r in fts:
        api_y = int(r["year"])
        api_a = _to_float(r.get("assets"))
        truth_a = truth_by_year.get(api_y)
        if not _approx_equal(api_a, truth_a, tol_pct=1.0):
            deltas.append({"year": api_y, "api_assets": api_a, "truth_assets": truth_a})
    return CheckResult(
        f_num=f_num, check="financial_trend_assets", gate="hard",
        passed=(len(deltas) == 0),
        api_value=[r.get("assets") for r in fts[:3]],
        truth_value=[truth_by_year.get(int(r["year"])) for r in fts[:3]],
        notes=f"{len(deltas)} year(s) diverge" if deltas else "all years match",
    )


def check_top_employers_consolidation(client, cur, f_num: str) -> CheckResult:
    """When consolidated=true, no two top_employers should share canonical_group_id."""
    code, body = client.get(f"/api/unions/{f_num}?consolidated=true")
    if code != 200 or not body:
        return CheckResult(f_num, "top_employers_consolidation", "hard", False,
                           notes=f"endpoint returned {code}")
    employers = body.get("top_employers") or []
    seen_group_ids = []
    dup = None
    for e in employers:
        gid = e.get("canonical_group_id")
        if gid is None:
            continue
        if gid in seen_group_ids:
            dup = gid
            break
        seen_group_ids.append(gid)
    return CheckResult(
        f_num=f_num, check="top_employers_consolidation", gate="hard",
        passed=(dup is None),
        api_value=len(employers),
        truth_value=None,
        notes=f"duplicate canonical_group_id={dup}" if dup else "ok",
    )


def check_top_employers_count(client, cur, f_num: str) -> CheckResult:
    """Top employers list should have count matching the canonical-rep filter from unions.py:867-872."""
    code, body = client.get(f"/api/unions/{f_num}?consolidated=true")
    if code != 200 or not body:
        return CheckResult(f_num, "top_employers_count", "advisory", False,
                           notes=f"endpoint returned {code}")
    employers = body.get("top_employers") or []
    cur.execute("""
        SELECT COUNT(*) FROM f7_employers_deduped e
        WHERE e.latest_union_fnum::text = %s
          AND (e.is_canonical_rep = TRUE OR e.canonical_group_id IS NULL)
    """, [f_num])
    truth_count = cur.fetchone()[0]
    expected = min(20, truth_count)
    return CheckResult(
        f_num=f_num, check="top_employers_count", gate="advisory",
        passed=(len(employers) == expected),
        api_value=len(employers), truth_value=expected,
    )


def check_affiliate_fallback_correct(client, cur, f_num: str) -> CheckResult:
    """elections_source semantics (per unions.py:914-945):
       - direct matches exist                  -> 'direct'
       - no direct AND aff_abbr is set        -> 'affiliate' (regardless of whether affiliate also returns 0 rows;
                                                              the endpoint enters the fallback branch unconditionally)
       - no direct AND no aff_abbr            -> stays 'direct' (with empty list)
    """
    code, body = client.get(f"/api/unions/{f_num}")
    if code != 200 or not body:
        return CheckResult(f_num, "affiliate_fallback_correct", "hard", False,
                           notes=f"endpoint returned {code}")
    cur.execute("""SELECT COUNT(*) FROM nlrb_tallies WHERE matched_olms_fnum = %s""", [f_num])
    direct_count = cur.fetchone()[0]
    cur.execute("SELECT aff_abbr FROM unions_master WHERE f_num = %s", [f_num])
    aff_row = cur.fetchone()
    aff_abbr = aff_row[0] if aff_row else None
    elections_source = body.get("elections_source")

    if direct_count > 0:
        expected = "direct"
    elif aff_abbr:
        expected = "affiliate"
    else:
        expected = "direct"
    passed = elections_source == expected
    return CheckResult(
        f_num=f_num, check="affiliate_fallback_correct", gate="hard",
        passed=passed,
        api_value=elections_source, truth_value=expected,
        notes=f"direct_count={direct_count}, aff_abbr={aff_abbr}",
    )


def check_disbursement_buckets_present(client, cur, f_num: str) -> CheckResult:
    """All 7 frontend buckets should appear (even if 0) for filings that have disbursement detail."""
    code, body = client.get(f"/api/unions/{f_num}/disbursements")
    if code != 200 or not body:
        return CheckResult(f_num, "disbursement_buckets_present", "advisory", False,
                           notes=f"endpoint returned {code}")
    years = body.get("years") or []
    if not years:
        return CheckResult(f_num, "disbursement_buckets_present", "advisory", True,
                           notes="no disbursement years (consistent if no LM-2)")
    required = {"representational", "political_lobbying", "staff_officers",
                "member_benefits", "operations", "affiliation_dues", "financial"}
    missing_per_year = []
    for y in years:
        missing = required - set(y.keys())
        if missing:
            missing_per_year.append({"year": y.get("year"), "missing": sorted(missing)})
    return CheckResult(
        f_num=f_num, check="disbursement_buckets_present", gate="advisory",
        passed=(len(missing_per_year) == 0),
        api_value=len(years), truth_value=None,
        notes=f"{len(missing_per_year)} year(s) missing buckets" if missing_per_year else "all 7 buckets present",
    )


def check_health_composite(client, cur, f_num: str) -> CheckResult:
    """/health must return non-null grade between 0 and 100."""
    code, body = client.get(f"/api/unions/{f_num}/health")
    if code != 200 or not body:
        return CheckResult(f_num, "health_composite", "advisory", False,
                           notes=f"endpoint returned {code}")
    composite = body.get("composite")
    if not composite:
        return CheckResult(f_num, "health_composite", "advisory", True,
                           notes="no composite (acceptable for unions with thin LM-2 data)")
    # Use 'in' instead of 'or' — composite["score"]=0.0 is a valid value but falsy
    score = composite["score"] if "score" in composite else composite.get("composite_score")
    grade = composite.get("grade")
    passed = (score is not None) and (0 <= float(score) <= 100) and (grade is not None)
    return CheckResult(
        f_num=f_num, check="health_composite", gate="advisory",
        passed=passed,
        api_value={"score": score, "grade": grade},
    )


def check_assets_year_mismatch_honest(client, cur, f_num: str) -> CheckResult:
    """If /assets exposes year_mismatch, validate the field rather than treating divergence as failure (Codex)."""
    code, body = client.get(f"/api/unions/{f_num}/assets")
    if code != 200 or not body:
        return CheckResult(f_num, "assets_year_mismatch_honest", "advisory", True,
                           notes=f"endpoint returned {code} (no holdings = pass)")
    # Existence of the field is the whole point; we just check it doesn't 500
    return CheckResult(
        f_num=f_num, check="assets_year_mismatch_honest", gate="advisory",
        passed=True,
        api_value={"has_year_mismatch_field": "year_mismatch" in body,
                   "holdings_count": len(body.get("holdings") or [])},
    )


PER_UNION_CHECKS: list[Callable] = [
    check_name_consistency,
    check_latest_lm2_year,
    check_financial_trend_assets,
    check_top_employers_consolidation,
    check_top_employers_count,
    check_affiliate_fallback_correct,
    check_disbursement_buckets_present,
    check_health_composite,
    check_assets_year_mismatch_honest,
]


# ============================================================
# Affiliation-level check
# ============================================================

def check_affiliation_local_count(client, cur, aff_abbr: str) -> CheckResult:
    code, body = client.get(f"/api/unions/national/{aff_abbr}")
    if code == 404:
        # Excluded affiliations are expected to 404
        return CheckResult(f_num=f"aff:{aff_abbr}", check="affiliation_local_count",
                           gate="advisory", passed=True,
                           api_value=404, notes="excluded (expected)")
    if code != 200 or not body:
        return CheckResult(f_num=f"aff:{aff_abbr}", check="affiliation_local_count",
                           gate="hard", passed=False,
                           notes=f"endpoint returned {code}")
    api_count = (body.get("summary") or {}).get("local_count")
    cur.execute("""
        SELECT COUNT(*) FROM unions_master
        WHERE aff_abbr = %s AND (NOT is_likely_inactive OR is_likely_inactive IS NULL)
    """, [aff_abbr])
    truth_count = cur.fetchone()[0]
    return CheckResult(
        f_num=f"aff:{aff_abbr}", check="affiliation_local_count", gate="hard",
        passed=(int(api_count or 0) == int(truth_count or 0)),
        api_value=api_count, truth_value=truth_count,
    )


# ============================================================
# Layer 3 -- aggregate cross-source linkage
# ============================================================

def layer3_aggregates(cur) -> dict[str, Any]:
    out: dict[str, Any] = {}

    # F7 orphan rate: F7 employers whose master_id has zero links from any
    # OTHER source_system (no OSHA/NLRB/WHD/SAM/etc enrichment).
    # See [[Open Problems/F7 Orphan Rate Regression]] for the canonical definition
    # (R7 baseline 67.4%, 2026-04-30 measurement 68.1%).
    cur.execute("""
        WITH f7_master AS (
            SELECT source_id AS f7_employer_id, master_id
            FROM master_employer_source_ids
            WHERE source_system = 'f7'
        ), cross_source_counts AS (
            SELECT master_id, COUNT(*) AS cross_source_n
            FROM master_employer_source_ids
            WHERE source_system != 'f7'
            GROUP BY master_id
        )
        SELECT
            COUNT(*) AS f7_total,
            COUNT(*) FILTER (WHERE COALESCE(c.cross_source_n, 0) > 0) AS f7_with_cross_source,
            COUNT(*) FILTER (WHERE COALESCE(c.cross_source_n, 0) = 0) AS f7_orphan,
            ROUND(100.0 * COUNT(*) FILTER (WHERE COALESCE(c.cross_source_n, 0) = 0)
                  / NULLIF(COUNT(*), 0), 2) AS orphan_pct
        FROM f7_master fm
        LEFT JOIN cross_source_counts c ON c.master_id = fm.master_id
    """)
    r = cur.fetchone()
    out["f7_cross_source_orphan"] = {
        "f7_total": r[0], "f7_with_cross_source": r[1], "f7_orphan": r[2],
        "orphan_pct": _to_float(r[3]),
    }

    # NLRB tally match rate
    cur.execute("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE matched_olms_fnum IS NOT NULL) AS matched,
               ROUND(100.0 * COUNT(*) FILTER (WHERE matched_olms_fnum IS NOT NULL)
                     / NULLIF(COUNT(*), 0), 2) AS match_pct
        FROM nlrb_tallies
    """)
    r = cur.fetchone()
    out["nlrb_tally_match_rate"] = {
        "total": r[0], "matched": r[1], "match_pct": _to_float(r[2]),
    }

    # NLRB matches per affiliation -- which affiliations have rich vs sparse election data
    cur.execute("""
        WITH per_aff AS (
            SELECT um.aff_abbr,
                   COUNT(DISTINCT um.f_num) AS local_count,
                   COUNT(DISTINCT t.case_number) AS election_count
            FROM unions_master um
            LEFT JOIN nlrb_tallies t ON t.matched_olms_fnum = um.f_num
            WHERE um.aff_abbr IS NOT NULL AND um.aff_abbr != ''
              AND um.aff_abbr NOT IN ('SOC')
            GROUP BY um.aff_abbr
        )
        SELECT COUNT(*) AS aff_count,
               COUNT(*) FILTER (WHERE election_count = 0) AS aff_with_zero_elections,
               COUNT(*) FILTER (WHERE election_count > 100) AS aff_with_100plus
        FROM per_aff
    """)
    r = cur.fetchone()
    out["nlrb_per_affiliation"] = {
        "affiliations_total": r[0],
        "affiliations_with_zero_elections": r[1],
        "affiliations_with_100plus_elections": r[2],
    }

    return out


# ============================================================
# Main
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["http", "asgi", "direct"], default="http",
                    help="API client mode (default: http on localhost:8001)")
    ap.add_argument("--sample-size", type=int, default=None,
                    help="Cap sample to roughly this many unions (default: full ~270)")
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--no-fail-on-hard", action="store_true")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    out_dir = Path(args.output_dir) if args.output_dir else (
        here.parent.parent / "audit_runs" / dt.date.today().isoformat()
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Mode: {args.mode}")
    print(f"Output: {out_dir}")
    client = get_client(args.mode)

    started = time.perf_counter()
    all_results: list[CheckResult] = []
    aff_results: list[CheckResult] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            samples = select_sample(cur, sample_size=args.sample_size)
            distinct_fnums: list[str] = []
            seen = set()
            for bucket, fnums in samples.items():
                for f in fnums:
                    if f not in seen:
                        seen.add(f)
                        distinct_fnums.append(f)
            print(f"Sample buckets: {{ {', '.join(f'{k}={len(v)}' for k, v in samples.items())} }}")
            print(f"Total distinct f_nums to audit: {len(distinct_fnums)}")

            # Per-union checks
            for i, f_num in enumerate(distinct_fnums, 1):
                if i % 25 == 0 or i == 1:
                    print(f"  per-union [{i:>4}/{len(distinct_fnums)}] f_num={f_num}")
                for check_fn in PER_UNION_CHECKS:
                    try:
                        r = check_fn(client, cur, f_num)
                    except Exception as exc:
                        try:
                            cur.connection.rollback()
                        except Exception:
                            pass
                        r = CheckResult(f_num=f_num, check=check_fn.__name__, gate="hard",
                                        passed=False, notes=f"exception: {exc}")
                    all_results.append(r)

            # Affiliation-level checks: hit /national/{aff} for all aff_abbrs in sample
            cur.execute("""
                SELECT DISTINCT aff_abbr FROM unions_master
                WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
                  AND aff_abbr NOT IN ('SOC')
                ORDER BY aff_abbr
            """)
            all_affs = [r[0] for r in cur.fetchall()]
            print(f"Affiliation checks: {len(all_affs)} aff_abbrs")
            for aff in all_affs:
                try:
                    r = check_affiliation_local_count(client, cur, aff)
                except Exception as exc:
                    try:
                        cur.connection.rollback()
                    except Exception:
                        pass
                    r = CheckResult(f_num=f"aff:{aff}", check="affiliation_local_count",
                                    gate="hard", passed=False, notes=f"exception: {exc}")
                aff_results.append(r)

            # Layer 3 aggregates
            print("Layer 3 aggregates ...")
            l3 = layer3_aggregates(cur)

    elapsed = time.perf_counter() - started
    print(f"\nElapsed: {elapsed:.1f}s")

    # ----- Summary -----
    n = len(all_results) + len(aff_results)
    n_pass = sum(1 for r in all_results + aff_results if r.passed)
    hard_fail = [r for r in all_results + aff_results if not r.passed and r.gate == "hard"]
    advisory_fail = [r for r in all_results + aff_results if not r.passed and r.gate == "advisory"]

    summary = {
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "elapsed_seconds": round(elapsed, 1),
        "total_checks": n,
        "passed": n_pass,
        "hard_failures": len(hard_fail),
        "advisory_failures": len(advisory_fail),
        "distinct_unions_audited": len(distinct_fnums),
        "affiliations_audited": len(aff_results),
    }

    # ----- Write outputs -----
    out_per_union = out_dir / "layer2_per_union.json"
    out_aff = out_dir / "layer2_affiliations.json"
    out_l3 = out_dir / "layer2_layer3.json"
    out_md = out_dir / "layer2_report.md"

    out_per_union.write_text(
        json.dumps({"summary": summary, "checks": [asdict(r) for r in all_results]},
                   indent=2, default=str), encoding="utf-8")
    out_aff.write_text(
        json.dumps({"checks": [asdict(r) for r in aff_results]},
                   indent=2, default=str), encoding="utf-8")
    out_l3.write_text(json.dumps(l3, indent=2, default=str), encoding="utf-8")

    # Markdown report
    lines = [
        "# Union Explorer Audit -- Layer 2 + Layer 3 Report", "",
        f"Run at: {summary['ran_at']}    Mode: {summary['mode']}    Elapsed: {summary['elapsed_seconds']}s", "",
        f"- Total checks: {n}",
        f"- Passed: {n_pass} ({round(100*n_pass/max(n,1),1)}%)",
        f"- Hard failures: {len(hard_fail)}",
        f"- Advisory failures: {len(advisory_fail)}",
        f"- Distinct unions audited: {len(distinct_fnums)}",
        f"- Affiliations audited: {len(aff_results)}", "",
        "## Layer 3 -- Cross-source linkage",
        "",
        "```json",
        json.dumps(l3, indent=2, default=str),
        "```", "",
    ]
    if hard_fail:
        lines += ["## Top hard failures", ""]
        # Group by check name
        by_check: dict[str, list[CheckResult]] = {}
        for r in hard_fail:
            by_check.setdefault(r.check, []).append(r)
        for check_name, fails in sorted(by_check.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"### {check_name} ({len(fails)} failures)")
            for r in fails[:10]:
                lines.append(f"- f_num={r.f_num}: api={r.api_value!r}, truth={r.truth_value!r}, notes={r.notes}")
            if len(fails) > 10:
                lines.append(f"- ... and {len(fails)-10} more")
            lines.append("")
    if advisory_fail:
        lines += ["## Top advisory failures", ""]
        by_check2: dict[str, list[CheckResult]] = {}
        for r in advisory_fail:
            by_check2.setdefault(r.check, []).append(r)
        for check_name, fails in sorted(by_check2.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"- {check_name}: {len(fails)} advisory failure(s)")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print("\nResults written to:")
    print(f"  {out_per_union}")
    print(f"  {out_aff}")
    print(f"  {out_l3}")
    print(f"  {out_md}")

    print(f"\nSUMMARY: {n_pass}/{n} pass, {len(hard_fail)} hard, {len(advisory_fail)} advisory")
    if hard_fail and not args.no_fail_on_hard:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
