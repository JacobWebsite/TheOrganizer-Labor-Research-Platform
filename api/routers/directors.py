"""Director permalink endpoint (24Q-14 / 24Q-10 Board, sister to BoardCard).

`GET /api/directors/{slug}` returns the full board roster for a director:
all companies (masters) where they serve, with per-board context
(committees, since-year, position) and a centrality score (number of
distinct masters).

Builds on the same `employer_directors` table that the BoardCard reads;
applies `director_name_filter.is_likely_real_director_name()` so the
endpoint never surfaces parser garbage (e.g. "Chief", "Continuing
Directors", "DEF 14A" — top false-positives by occurrence pre-filter).

Slug → name resolution: the frontend slug is `lowercase + hyphens`
(see `name_to_slug` in director_name_filter.py). Slugs aren't unique
to a single canonical spelling — "Adam D. Portnoy" and "Adam D. Portnoy
(3)" both slug to `adam-d-portnoy` (after stripping `(3)`). The endpoint
returns ALL matching director records with the same slug; the frontend
groups them.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..services.director_name_filter import (
    SQL_FILTER_CLAUSE,  # noqa: F401  used in f-string SQL below
    is_likely_real_director_name,
    name_to_slug,
    sql_filter_params,  # noqa: F401  used in list_top_directors below
)


router = APIRouter()

DEFAULT_LIMIT = 100  # max boards per director (no real director sits on > 50, but allow headroom)
MAX_LIMIT = 500


def _empty_shape(slug: str) -> Dict[str, Any]:
    return {
        "slug": slug,
        "names_matched": [],
        "summary": {
            "boards_count": 0,
            "is_independent_count": 0,
            "earliest_since_year": None,
            "latest_since_year": None,
        },
        "boards": [],
    }


@router.get("/api/directors/{slug}")
def get_director_profile(
    slug: str,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> Dict[str, Any]:
    """Return all boards a director serves on, keyed by URL slug.

    Slug lookup is case-insensitive and matches against ANY name in
    `employer_directors` whose computed slug equals the request slug.
    Duplicate-spelling rows (e.g. "Adam Portnoy" and "Adam D. Portnoy")
    that resolve to different slugs each get their own page; same-slug
    rows roll up into one page.
    """
    slug = (slug or "").strip().lower()
    if not slug or len(slug) < 3:
        raise HTTPException(status_code=400, detail="Slug too short")

    with get_db() as conn:
        with conn.cursor() as cur:
            # Slug equality computed at query time, not at fetch time.
            # The previous version used a `LIKE first_token%` prefix
            # filter then capped at LIMIT 100 — for common first tokens
            # ("john", "michael", etc) the cap could drop valid slugs
            # that landed past the limit, producing false 404s.
            # (Codex finding 2026-05-06.)
            #
            # `employer_directors` is ~24K rows. A full-table regex
            # comparison runs in <50ms — fine without an index.
            cur.execute(
                """
                SELECT
                    d.director_name,
                    d.master_id,
                    d.age,
                    d.position,
                    d.director_since_year,
                    d.primary_occupation,
                    d.is_independent,
                    d.committees,
                    d.fiscal_year,
                    d.parse_strategy,
                    d.source_url,
                    m.canonical_name AS master_canonical_name,
                    m.state AS master_state,
                    m.naics AS master_naics
                FROM employer_directors d
                LEFT JOIN master_employers m ON m.master_id = d.master_id
                WHERE TRIM(BOTH '-' FROM REGEXP_REPLACE(
                          LOWER(d.director_name), '[^a-z0-9]+', '-', 'g'
                      )) = %s
                ORDER BY d.director_name, d.fiscal_year DESC NULLS LAST
                LIMIT %s
                """,
                [slug, limit],
            )
            rows = cur.fetchall() or []

    # Re-filter in Python: exact slug match + name-quality predicate.
    matches = []
    seen_names: set[str] = set()
    for r in rows:
        name = r.get("director_name") or ""
        if not is_likely_real_director_name(name):
            continue
        if name_to_slug(name) != slug:
            continue
        seen_names.add(name)
        matches.append(r)

    if not matches:
        # 404 instead of 200+empty so the frontend can show a clear
        # "director not found" page rather than a blank profile.
        raise HTTPException(status_code=404, detail="Director not found")

    # Group by master_id — one director can have multiple rows from
    # multiple fiscal years. Keep the most-recent per master.
    by_master: Dict[int, Dict[str, Any]] = {}
    independent_set: set[int] = set()
    for r in matches:
        mid = r.get("master_id")
        if mid is None:
            continue
        existing = by_master.get(mid)
        cur_fy = r.get("fiscal_year")
        if existing is None or (
            cur_fy is not None
            and (existing.get("fiscal_year") is None
                 or cur_fy > existing["fiscal_year"])
        ):
            by_master[mid] = r
        if r.get("is_independent") is True:
            independent_set.add(mid)

    # Build response.
    boards: List[Dict[str, Any]] = []
    earliest_since: int | None = None
    latest_since: int | None = None
    for mid, r in by_master.items():
        sy = r.get("director_since_year")
        if sy is not None:
            if earliest_since is None or sy < earliest_since:
                earliest_since = sy
            if latest_since is None or sy > latest_since:
                latest_since = sy
        boards.append({
            "master_id": mid,
            "canonical_name": r.get("master_canonical_name"),
            "state": r.get("master_state"),
            "naics": r.get("master_naics"),
            "since_year": sy,
            "position": r.get("position"),
            "is_independent": mid in independent_set,
            "committees": list(r.get("committees") or []),
            "fiscal_year": r.get("fiscal_year"),
            "source_url": r.get("source_url"),
        })

    # Sort boards by master canonical_name for stable output.
    boards.sort(key=lambda b: (b.get("canonical_name") or "").lower())

    return {
        "slug": slug,
        "names_matched": sorted(seen_names),
        "summary": {
            "boards_count": len(boards),
            "is_independent_count": len(independent_set),
            "earliest_since_year": earliest_since,
            "latest_since_year": latest_since,
        },
        "boards": boards,
    }


@router.get("/api/directors")
def list_top_directors(limit: int = Query(default=25, ge=1, le=100)) -> Dict[str, Any]:
    """Return the top-N most-connected directors (highest board count).

    Useful as a landing page for the directors index. Filtered through
    the same name-quality predicate as the per-director endpoint.
    """
    # Pre-filter at the DB layer using SQL_FILTER_CLAUSE — without it,
    # the top-N is dominated by parser-garbage strings ("Chief" 202
    # boards, "DEF 14A" 169 boards, etc.) and a Python post-filter
    # would have to over-fetch by 10x+ to reach 25 real entries.
    params = sql_filter_params()
    params["row_limit"] = limit * 3  # small over-fetch for the year-regex residue
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT director_name,
                       COUNT(DISTINCT master_id) AS boards_count
                FROM employer_directors
                WHERE {SQL_FILTER_CLAUSE}
                GROUP BY director_name
                HAVING COUNT(DISTINCT master_id) >= 2
                ORDER BY 2 DESC, director_name
                LIMIT %(row_limit)s
                """,
                params,
            )
            rows = cur.fetchall() or []

    out = []
    for r in rows:
        name = r.get("director_name") or ""
        if not is_likely_real_director_name(name):
            continue
        out.append({
            "name": name,
            "slug": name_to_slug(name),
            "boards_count": int(r.get("boards_count") or 0),
        })
        if len(out) >= limit:
            break
    return {"directors": out, "limit": limit}
