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


router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# The Mergent occupation field is a Frankenstein of title + multi-paragraph
# bio text. Truncate to keep the card readable without losing the title.
_OCCUPATION_TRUNCATE = 180


def _tables_exist(cur) -> bool:
    cur.execute(
        """
        SELECT to_regclass('employer_directors') AS d,
               to_regclass('director_interlocks') AS i
        """
    )
    row = cur.fetchone()
    return bool(row and row.get("d"))


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
            independent_count = 0
            latest_fy: int | None = None
            latest_strategy: str | None = None
            latest_source_url: str | None = None
            latest_extracted_at = None
            for r in rows:
                if r.get("is_independent") is True:
                    independent_count += 1
                fy = r.get("fiscal_year")
                if fy is not None and (latest_fy is None or fy > latest_fy):
                    latest_fy = fy
                    latest_strategy = r.get("parse_strategy")
                    latest_source_url = r.get("source_url")
                    latest_extracted_at = r.get("extracted_at")
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
                        "fiscal_year": fy,
                        "parse_strategy": r.get("parse_strategy"),
                    }
                )

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

    is_matched = len(directors) > 0
    return {
        "summary": {
            "is_matched": is_matched,
            "director_count": len(directors),
            "independent_count": independent_count,
            "fiscal_year": latest_fy,
            "parse_strategy": latest_strategy,
            "source_url": latest_source_url,
            "extracted_at": latest_extracted_at.isoformat() if latest_extracted_at else None,
        },
        "directors": directors,
        "interlocks": interlocks,
    }
