"""
Industry peers / competitors endpoint for the master profile.

24Q-15: Competitors. For a given master employer, returns the nearest
industry peers, ranked by NAICS proximity (NAICS-6 first, falling back to
NAICS-4) and workforce size similarity (closest in log-employees).

Each peer chip exposes name, worker count, tier (from mv_target_scorecard
gold_standard_tier), and NAICS so the user can navigate to that peer's
master profile and use it as a comparable target.

Resolution path:
  master_id
    -> mv_target_scorecard (self row: NAICS + effective_employee_count)
    -> naics_codes_reference (label for the NAICS code, latest version)
    -> mv_target_scorecard (peer rows; same NAICS-6 if available, else
       NAICS-4 prefix; ORDER BY |ln(peer_workers) - ln(self_workers)|)

Coverage: ~36% of masters have a valid NAICS-4 row in mv_target_scorecard
(2,066,220 of 5,743,225 master_employers as of 2026-05-08). Without that
row this endpoint returns an empty peers[] with `naics: null` -- the
frontend renders an explicit empty state.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db

router = APIRouter()

DEFAULT_LIMIT = 12
MAX_LIMIT = 50


def _size_band(workers: Optional[float]) -> str:
    """Workforce decile label. Mirrors the bands in the spec.
    None -> 'unknown' so the frontend can hide the chip cleanly."""
    if workers is None:
        return "unknown"
    try:
        w = float(workers)
    except (TypeError, ValueError):
        return "unknown"
    if w < 100:
        return "1-100"
    if w < 1000:
        return "100-1K"
    if w < 10000:
        return "1K-10K"
    return "10000+"


def _empty(master_id: int, naics: Optional[str], naics_label: Optional[str], workers: Optional[float]) -> Dict[str, Any]:
    return {
        "master_id": master_id,
        "naics": naics,
        "naics_label": naics_label,
        "size_band": _size_band(workers),
        "peers": [],
        "as_of": date.today().isoformat(),
    }


@router.get("/api/employers/master/{master_id}/competitors")
def get_master_competitors(
    master_id: int,
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Max peers returned (sorted by log-workforce distance)",
    ),
) -> Dict[str, Any]:
    """Return industry peers for a master employer (24Q-15 Competitors).

    Response shape:
        {
            "master_id": int,
            "naics": str | null,           # 6-digit if available, else 4-digit prefix
            "naics_label": str | null,     # human-readable NAICS title
            "size_band": str,              # "1-100" | "100-1K" | "1K-10K" | "10000+" | "unknown"
            "peers": [
                {
                    "master_id": int,
                    "name": str,
                    "consolidated_workers": int | null,
                    "revenue_total": float | null,   # 990 revenue when present
                    "tier": str | null,              # mv_target_scorecard.gold_standard_tier
                    "naics": str,                    # peer's full NAICS code
                    "match_basis": "naics6" | "naics4",
                },
                ...up to `limit` peers (default 12)
            ],
            "as_of": "YYYY-MM-DD",
        }

    Ranking:
      1. Exclude self (`master_id <> :master_id`).
      2. Prefer same NAICS-6 if the self row has a 6-digit code; else
         match on NAICS-4 prefix.
      3. ORDER BY abs(ln(GREATEST(peer_workers, 1)) - ln(GREATEST(self_workers, 1)))
         ascending (closest in log-workforce-size first).
      4. Tie-break by peer master_id ascending for determinism.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # 404 on unknown master -- mirrors the other 24Q endpoints.
            cur.execute("SELECT 1 FROM master_employers WHERE master_id = %s", [master_id])
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Master employer not found")

            # Self row from the scorecard MV. If there's no row -- or the
            # row has a NULL/short NAICS -- return the empty shape with
            # naics=null. master_employers might still have a NAICS even
            # when the scorecard MV doesn't, but we don't fall through
            # to that: the scorecard is the canonical source for peers
            # because peers must also be present in the scorecard for
            # tier badges to render.
            cur.execute(
                """
                SELECT naics, effective_employee_count
                FROM mv_target_scorecard
                WHERE master_id = %s
                """,
                [master_id],
            )
            self_row = cur.fetchone()

            if not self_row or not self_row.get("naics"):
                # Try master_employers.naics as a last resort -- self has
                # a NAICS but no scorecard row. Peers query won't find
                # anything (peers come from the scorecard) but at least
                # the response carries the NAICS context so the frontend
                # can show "we know your industry, no peers in scorecard".
                cur.execute(
                    """
                    SELECT naics, employee_count AS effective_employee_count
                    FROM master_employers
                    WHERE master_id = %s
                    """,
                    [master_id],
                )
                self_row = cur.fetchone() or {}

            self_naics: Optional[str] = (self_row.get("naics") or None)
            self_workers = self_row.get("effective_employee_count")

            # Look up the NAICS label. We prefer the 2022 vintage; fall
            # back to whatever's available. Cast to str because some
            # rows have varchar NAICS.
            naics_label: Optional[str] = None
            if self_naics:
                cur.execute(
                    """
                    SELECT naics_title
                    FROM naics_codes_reference
                    WHERE naics_code = %s
                    ORDER BY naics_version DESC
                    LIMIT 1
                    """,
                    [str(self_naics)],
                )
                lr = cur.fetchone()
                if lr:
                    naics_label = lr.get("naics_title")

            # No NAICS -> return empty shape immediately. We still report
            # workers + size_band when those are known on master_employers.
            if not self_naics:
                return _empty(master_id, None, None, self_workers)

            # Peer search. Use NAICS-6 when the self code is full-length,
            # else fall back to NAICS-4 prefix. We store the matched
            # basis on each peer row so the frontend can show a chip.
            #
            # `effective_employee_count` is the right ranking key because
            # mv_target_scorecard already coalesces multiple workforce
            # signals (LM, F-7, 990, ppp, mergent). Peers without a
            # workforce count are excluded -- they can't be ranked.
            self_naics_str = str(self_naics)
            use_naics6 = len(self_naics_str) >= 6
            self_workers_log_input = float(self_workers) if self_workers else 1.0

            if use_naics6:
                # Exact NAICS-6 match. Use ::text cast because mv_target_scorecard.naics
                # is varchar(10) and we want pure equality on the trimmed value.
                where_clause = "s.naics = %(naics)s"
                naics_param = self_naics_str
            else:
                # NAICS-4 prefix (or shorter -- we stored fewer digits in
                # master_employers for some sources). LIKE 'XXXX%' keeps
                # the search index-friendly on naics.
                where_clause = "s.naics LIKE %(naics)s || '%%'"
                naics_param = self_naics_str[:4]

            cur.execute(
                f"""
                SELECT
                  s.master_id,
                  s.display_name AS name,
                  s.canonical_name,
                  s.naics,
                  s.effective_employee_count AS workers,
                  s.gold_standard_tier AS tier,
                  s.n990_revenue AS revenue
                FROM mv_target_scorecard s
                WHERE {where_clause}
                  AND s.master_id <> %(self_id)s
                  AND s.effective_employee_count IS NOT NULL
                ORDER BY
                  abs(ln(GREATEST(s.effective_employee_count::numeric, 1::numeric))
                      - ln(GREATEST(%(self_workers)s::numeric, 1::numeric))) ASC,
                  s.master_id ASC
                LIMIT %(limit)s
                """,
                {
                    "naics": naics_param,
                    "self_id": master_id,
                    "self_workers": self_workers_log_input,
                    "limit": limit,
                },
            )
            peer_rows = cur.fetchall() or []

    peers: List[Dict[str, Any]] = []
    for r in peer_rows:
        peers.append(
            {
                "master_id": int(r["master_id"]),
                "name": r.get("name") or r.get("canonical_name") or f"Master {r['master_id']}",
                "consolidated_workers": (
                    int(r["workers"]) if r.get("workers") is not None else None
                ),
                "revenue_total": (
                    float(r["revenue"]) if r.get("revenue") is not None else None
                ),
                "tier": r.get("tier"),
                "naics": r.get("naics"),
                "match_basis": "naics6" if use_naics6 else "naics4",
            }
        )

    return {
        "master_id": master_id,
        "naics": self_naics_str,
        "naics_label": naics_label,
        "size_band": _size_band(self_workers),
        "peers": peers,
        "as_of": date.today().isoformat(),
    }
