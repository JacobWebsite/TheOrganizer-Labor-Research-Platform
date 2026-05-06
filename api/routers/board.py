"""
Board of directors endpoint for the master profile (24Q-14 / 24Q-10 Board).

Pulls director rosters parsed from SEC DEF14A proxy filings and the
director_interlocks view that surfaces shared directors across companies.

The endpoint returns:
  - summary: director count, independent count, parse strategy, source freshness
  - directors: per-director rows (name, age, position, since, occupation,
    independence, committees, compensation)
  - interlocks: list of {director_name, other_master_id, other_canonical_name,
    other_cik} -- "this person also serves on the board of X"

Pairs with ExecutivesCard (24Q-7) for the full Q8/Q10 management+board view.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..services.director_name_filter import is_likely_real_director_name


router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# The Mergent occupation field is a Frankenstein of title + multi-paragraph
# bio text. Truncate to keep the card readable without losing the title.
_OCCUPATION_TRUNCATE = 180


def _tables_exist(cur) -> bool:
    """Both `employer_directors` AND `director_interlocks` must be present.
    The endpoint queries the interlocks view unconditionally when directors
    exist, so a missing view would 500 instead of degrading gracefully.
    (Codex finding 2026-05-04: original code only checked `d`.)
    """
    cur.execute(
        """
        SELECT to_regclass('employer_directors') AS d,
               to_regclass('director_interlocks') AS i
        """
    )
    row = cur.fetchone()
    return bool(row and row.get("d") and row.get("i"))


def _empty_shape() -> Dict[str, Any]:
    return {
        "summary": {
            "is_matched": False,
            "director_count": 0,
            "independent_count": 0,
            "fiscal_year": None,
            "parse_strategy": None,
            "source_url": None,
            "extracted_at": None,
        },
        "directors": [],
        "interlocks": [],
    }


def _truncate(text: str | None, n: int = _OCCUPATION_TRUNCATE) -> str | None:
    if not text:
        return None
    s = str(text).strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


@router.get("/api/employers/master/{master_id}/board")
def get_master_board(
    master_id: int,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """Return the board-of-directors roster + interlocks for a master employer."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT canonical_name FROM master_employers WHERE master_id = %s",
                [master_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Master employer not found")

            if not _tables_exist(cur):
                return _empty_shape()

            # Summary aggregates over the FULL roster, not just the page
            # being returned. Without this, `summary.director_count` and
            # `summary.independent_count` would silently report the LIMIT
            # not the real total -- a caller passing limit=5 against a
            # 30-director board would see "5 directors / 1 independent"
            # instead of "30 / 8". Same for the source-freshness fields.
            # (Codex finding 2026-05-04, fixed same day.)
            cur.execute(
                """
                SELECT
                  COUNT(*) AS director_count,
                  COUNT(*) FILTER (WHERE is_independent IS TRUE) AS independent_count,
                  MAX(fiscal_year) AS latest_fy
                FROM employer_directors
                WHERE master_id = %s
                """,
                [master_id],
            )
            agg_row = cur.fetchone() or {}
            director_count = int(agg_row.get("director_count") or 0)
            independent_count = int(agg_row.get("independent_count") or 0)
            latest_fy: int | None = agg_row.get("latest_fy")

            # Pull the parse_strategy / source_url / extracted_at from the
            # row that has the latest fiscal year (most-recent filing).
            # Separate query so we get the "freshest" metadata regardless
            # of whether that row falls within the LIMIT page.
            latest_strategy: str | None = None
            latest_source_url: str | None = None
            latest_extracted_at = None
            if latest_fy is not None:
                cur.execute(
                    """
                    SELECT parse_strategy, source_url, extracted_at
                    FROM employer_directors
                    WHERE master_id = %s AND fiscal_year = %s
                    LIMIT 1
                    """,
                    [master_id, latest_fy],
                )
                fr = cur.fetchone()
                if fr:
                    latest_strategy = fr.get("parse_strategy")
                    latest_source_url = fr.get("source_url")
                    latest_extracted_at = fr.get("extracted_at")

            cur.execute(
                """
                SELECT
                  director_name, age, position, director_since_year,
                  primary_occupation, is_independent, committees,
                  compensation_total, fiscal_year, parse_strategy,
                  source_url, extracted_at
                FROM employer_directors
                WHERE master_id = %s
                ORDER BY
                  CASE WHEN is_independent IS FALSE THEN 0 ELSE 1 END,
                  director_since_year ASC NULLS LAST,
                  director_name ASC
                LIMIT %s
                """,
                [master_id, limit],
            )
            rows = cur.fetchall() or []

            directors = []
            for r in rows:
                directors.append(
                    {
                        "name": r.get("director_name"),
                        "age": r.get("age"),
                        "position": r.get("position"),
                        "since_year": r.get("director_since_year"),
                        "occupation": _truncate(r.get("primary_occupation")),
                        "is_independent": r.get("is_independent"),
                        "committees": list(r.get("committees") or []),
                        "compensation_total": (
                            float(r["compensation_total"])
                            if r.get("compensation_total") is not None
                            else None
                        ),
                        "fiscal_year": r.get("fiscal_year"),
                        "parse_strategy": r.get("parse_strategy"),
                    }
                )

            # 24Q-14 C.4 (2026-05-06): per-director enforcement-risk score.
            # For each director on this master's board, sum the enforcement
            # signals from the OTHER boards they serve on. A director who
            # sits on 4 companies and 3 of them have major OSHA / NLRB ULP
            # / WHD enforcement is signal that THIS company's governance
            # may be shaped by the same playbook.
            #
            # Filter through `is_likely_real_director_name` (Python predicate
            # applied at write-time below) so parser-garbage names don't
            # contribute fake "Chief sits on 200 companies" signals.
            director_names = [
                d["name"] for d in directors
                if d.get("name") and is_likely_real_director_name(d["name"])
            ]
            risk_by_name: dict[str, dict] = {}
            if director_names:
                cur.execute(
                    """
                    WITH other_boards AS (
                        SELECT d.director_name, d.master_id AS other_master_id
                        FROM employer_directors d
                        WHERE d.director_name = ANY(%s)
                          AND d.master_id <> %s
                    )
                    SELECT
                        ob.director_name,
                        COUNT(DISTINCT ob.other_master_id) AS other_boards_count,
                        SUM(COALESCE(ts.osha_total_violations, 0))::int AS osha_violations,
                        SUM(COALESCE(ts.nlrb_ulp_count, 0))::int AS nlrb_ulps,
                        SUM(COALESCE(ts.whd_total_backwages, 0))::numeric AS whd_backwages,
                        SUM(COALESCE(ts.osha_total_penalties, 0))::numeric AS osha_penalties
                    FROM other_boards ob
                    LEFT JOIN mv_target_scorecard ts ON ts.master_id = ob.other_master_id
                    GROUP BY ob.director_name
                    """,
                    [director_names, master_id],
                )
                for r in cur.fetchall() or []:
                    nm = r["director_name"]
                    osha_v = int(r.get("osha_violations") or 0)
                    nlrb_u = int(r.get("nlrb_ulps") or 0)
                    whd_bw = float(r.get("whd_backwages") or 0)
                    osha_p = float(r.get("osha_penalties") or 0)
                    # Risk-score formula. Weights chosen so:
                    #   - 1 OSHA violation contributes 3 points
                    #   - 1 NLRB ULP contributes 5 points (heavier, ULPs
                    #     are intentional employer behavior whereas OSHA
                    #     violations can be near-miss reporting)
                    #   - $50K WHD backwages contributes 1 point
                    #   - $5K OSHA penalties contributes 1 point
                    score = (
                        osha_v * 3.0
                        + nlrb_u * 5.0
                        + whd_bw / 50_000.0
                        + osha_p / 5_000.0
                    )
                    # Tier thresholds. GREEN < 20, YELLOW 20-100, RED > 100.
                    # Calibrated against current data: ~70% of real
                    # directors with >= 2 boards land GREEN; only the
                    # most-egregious enforcement-overlap directors hit RED.
                    if score >= 100:
                        tier = "RED"
                    elif score >= 20:
                        tier = "YELLOW"
                    else:
                        tier = "GREEN"
                    risk_by_name[nm] = {
                        "other_boards_count": int(r.get("other_boards_count") or 0),
                        "risk_score": round(score, 1),
                        "risk_tier": tier,
                        "components": {
                            "osha_violations": osha_v,
                            "nlrb_ulps": nlrb_u,
                            "whd_backwages": round(whd_bw, 0),
                            "osha_penalties": round(osha_p, 0),
                        },
                    }

            # Attach risk to each director row. Directors with only one
            # board (this one) get null risk — they don't have an
            # enforcement-overlap signal.
            for d in directors:
                d["enforcement_risk"] = risk_by_name.get(d["name"])

            interlocks: list = []
            if directors:
                cur.execute(
                    """
                    SELECT
                      i.director_name,
                      CASE
                        WHEN i.master_id_a = %(mid)s THEN i.master_id_b
                        ELSE i.master_id_a
                      END AS other_master_id,
                      CASE
                        WHEN i.master_id_a = %(mid)s THEN i.cik_b
                        ELSE i.cik_a
                      END AS other_cik,
                      CASE
                        WHEN i.master_id_a = %(mid)s THEN i.fiscal_year_b
                        ELSE i.fiscal_year_a
                      END AS other_fiscal_year
                    FROM director_interlocks i
                    WHERE i.master_id_a = %(mid)s OR i.master_id_b = %(mid)s
                    """,
                    {"mid": master_id},
                )
                raw_interlocks = cur.fetchall() or []
                if raw_interlocks:
                    other_ids = sorted(
                        {r["other_master_id"] for r in raw_interlocks if r.get("other_master_id")}
                    )
                    name_lookup: dict[int, str] = {}
                    if other_ids:
                        cur.execute(
                            "SELECT master_id, canonical_name FROM master_employers "
                            "WHERE master_id = ANY(%s)",
                            [other_ids],
                        )
                        name_lookup = {
                            r["master_id"]: r["canonical_name"] for r in cur.fetchall() or []
                        }
                    interlocks = [
                        {
                            "director_name": r["director_name"],
                            "other_master_id": r["other_master_id"],
                            "other_canonical_name": name_lookup.get(r["other_master_id"]),
                            "other_cik": r["other_cik"],
                            "other_fiscal_year": r["other_fiscal_year"],
                        }
                        for r in raw_interlocks
                    ]

    # is_matched + director_count both come from the FULL aggregate (not
    # the limited roster), so a small `limit` doesn't make a board look
    # smaller than it is. The directors[] array still respects `limit`.
    is_matched = director_count > 0
    return {
        "summary": {
            "is_matched": is_matched,
            "director_count": director_count,
            "independent_count": independent_count,
            "fiscal_year": latest_fy,
            "parse_strategy": latest_strategy,
            "source_url": latest_source_url,
            "extracted_at": latest_extracted_at.isoformat() if latest_extracted_at else None,
        },
        "directors": directors,
        "interlocks": interlocks,
    }
