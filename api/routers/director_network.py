"""Director-network endpoint (24Q-14 C.2-3, sister to BoardCard + DirectorProfilePage).

`GET /api/employers/master/{master_id}/director-network?depth=2`

Surfaces the corporate-power-map view: from any company, see the
directly-connected companies (via shared directors), then the
one-additional-hop neighbors. Together this is the "who controls X
and what else do they control" research view.

Caps:
- `depth` is hard-capped to 2. Beyond that the result combinatorially
  explodes (top masters have ~300 1-hop neighbors; 2-hop without a
  cap could return 90,000+ rows).
- 2-hop is limited to top 100 companies by # of distinct paths from
  the anchor. Real organizing leverage is concentrated in the high-
  connection-count tail, not the long tail.
- Filtered through `director_name_filter.is_likely_real_director_name`
  so parser-garbage names ("Chief", "DEF 14A") never appear as
  network paths. Without the filter, every company sharing a "Chief"
  row would appear as connected to every other company sharing a
  "Chief" row — a fake mega-cluster.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..services.director_name_filter import (
    SQL_FILTER_CLAUSE,
    is_likely_real_director_name,
    name_to_slug,
    sql_filter_params,  # noqa: F401  used in WHERE below
)


router = APIRouter()

# Caps. `MAX_DEPTH` is fixed at 2 — depth=3 explodes (Sankey-style
# graphs would use it but the basic profile UI doesn't need it).
MAX_DEPTH = 2
DEFAULT_TOP_TWO_HOP = 50
MAX_TOP_TWO_HOP = 200
# Self-gate: don't render the section for masters with too few neighbors.
# (Frontend has its own gate but the endpoint exposes the raw count.)
MIN_NEIGHBORS_TO_SURFACE = 3


def _resolve_canonical_names(cur, master_ids: list[int]) -> dict[int, dict]:
    """Bulk-load canonical_name + state for a list of master_ids."""
    if not master_ids:
        return {}
    cur.execute(
        """
        SELECT master_id, canonical_name, state, naics
        FROM master_employers
        WHERE master_id = ANY(%s)
        """,
        [master_ids],
    )
    return {
        r["master_id"]: {
            "canonical_name": r.get("canonical_name"),
            "state": r.get("state"),
            "naics": r.get("naics"),
        }
        for r in cur.fetchall() or []
    }


@router.get("/api/employers/master/{master_id}/director-network")
def get_director_network(
    master_id: int,
    depth: int = Query(default=2, ge=1, le=MAX_DEPTH),
    top_two_hop: int = Query(default=DEFAULT_TOP_TWO_HOP, ge=1, le=MAX_TOP_TWO_HOP),
) -> Dict[str, Any]:
    """Return the 1-hop and (optionally) 2-hop director network for a master."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT canonical_name FROM master_employers WHERE master_id = %s",
                [master_id],
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Master employer not found")
            anchor_name = row["canonical_name"]

            # 1-hop: every company sharing at least one director with the
            # anchor. The interlocks view is symmetric (each shared
            # director produces one row with master_id_a/master_id_b in
            # alphabetical-id order), so we union both directions.
            params = sql_filter_params()
            params["anchor"] = master_id
            cur.execute(
                f"""
                WITH all_edges AS (
                    SELECT i.director_name,
                           i.master_id_a AS anchor_side,
                           i.master_id_b AS other_side
                    FROM director_interlocks i
                    WHERE i.master_id_a = %(anchor)s
                    UNION ALL
                    SELECT i.director_name,
                           i.master_id_b AS anchor_side,
                           i.master_id_a AS other_side
                    FROM director_interlocks i
                    WHERE i.master_id_b = %(anchor)s
                )
                SELECT director_name, other_side
                FROM all_edges
                WHERE EXISTS (
                    SELECT 1 FROM employer_directors d
                    WHERE d.director_name = all_edges.director_name
                      AND ({SQL_FILTER_CLAUSE.replace('director_name', 'd.director_name')})
                    LIMIT 1
                )
                """,
                params,
            )
            one_hop_edges = cur.fetchall() or []

            # Filter the surviving director names through the Python
            # predicate as well (catches the year-regex residue that
            # SQL_FILTER_CLAUSE doesn't cover).
            one_hop_clean = [
                (e["director_name"], e["other_side"])
                for e in one_hop_edges
                if is_likely_real_director_name(e["director_name"])
            ]
            if not one_hop_clean:
                # No real-name interlocks at all; return the empty shape
                # with all keys present so the frontend doesn't have to
                # guard against missing fields.
                return {
                    "anchor": {
                        "master_id": master_id,
                        "canonical_name": anchor_name,
                    },
                    "stats": {
                        "one_hop_count": 0,
                        "two_hop_count": 0,
                        "two_hop_returned": 0,
                        "shared_directors_total": 0,
                        "should_surface": False,
                    },
                    "shared_directors": [],
                    "one_hop": [],
                    "two_hop": [],
                }

            # Aggregate per neighbor — count how many distinct directors
            # connect anchor -> each 1-hop neighbor.
            from collections import defaultdict
            one_hop_dirs_by_master: dict[int, set[str]] = defaultdict(set)
            shared_directors: set[str] = set()
            for dname, other in one_hop_clean:
                if other == master_id:
                    continue
                one_hop_dirs_by_master[other].add(dname)
                shared_directors.add(dname)

            # Resolve names for 1-hop masters.
            one_hop_ids = list(one_hop_dirs_by_master.keys())
            one_hop_meta = _resolve_canonical_names(cur, one_hop_ids)

            one_hop: List[Dict[str, Any]] = []
            for mid, dnames in one_hop_dirs_by_master.items():
                meta = one_hop_meta.get(mid, {})
                one_hop.append({
                    "master_id": mid,
                    "canonical_name": meta.get("canonical_name"),
                    "state": meta.get("state"),
                    "naics": meta.get("naics"),
                    "shared_directors": sorted(dnames),
                    "shared_director_count": len(dnames),
                })
            # Sort by shared-director count desc, then name asc.
            one_hop.sort(key=lambda x: (
                -x["shared_director_count"],
                (x.get("canonical_name") or "").lower(),
            ))

            two_hop: List[Dict[str, Any]] = []
            two_hop_count = 0
            if depth >= 2 and one_hop_ids:
                # 2-hop: any company sharing a director with any 1-hop
                # neighbor, EXCEPT the anchor itself and the 1-hop set.
                exclude_ids = set([master_id, *one_hop_ids])
                params_2 = sql_filter_params()
                params_2["one_hop_ids"] = one_hop_ids
                params_2["exclude_ids"] = list(exclude_ids)
                cur.execute(
                    f"""
                    WITH all_edges AS (
                        SELECT i.director_name,
                               i.master_id_a AS source_side,
                               i.master_id_b AS dest_side
                        FROM director_interlocks i
                        WHERE i.master_id_a = ANY(%(one_hop_ids)s)
                        UNION ALL
                        SELECT i.director_name,
                               i.master_id_b AS source_side,
                               i.master_id_a AS dest_side
                        FROM director_interlocks i
                        WHERE i.master_id_b = ANY(%(one_hop_ids)s)
                    )
                    SELECT director_name, source_side, dest_side
                    FROM all_edges
                    WHERE dest_side != ALL(%(exclude_ids)s)
                      AND EXISTS (
                        SELECT 1 FROM employer_directors d
                        WHERE d.director_name = all_edges.director_name
                          AND ({SQL_FILTER_CLAUSE.replace('director_name', 'd.director_name')})
                        LIMIT 1
                      )
                    """,
                    params_2,
                )
                two_hop_edges = cur.fetchall() or []

                # Aggregate per 2-hop master — count distinct paths.
                two_hop_paths: dict[int, dict] = defaultdict(lambda: {
                    "via_companies": set(), "via_directors": set(),
                })
                for e in two_hop_edges:
                    dname = e["director_name"]
                    if not is_likely_real_director_name(dname):
                        continue
                    src = e["source_side"]   # 1-hop neighbor (or anchor; filter)
                    dest = e["dest_side"]    # 2-hop master
                    if dest in exclude_ids:
                        continue
                    two_hop_paths[dest]["via_companies"].add(src)
                    two_hop_paths[dest]["via_directors"].add(dname)

                two_hop_count = len(two_hop_paths)

                # Resolve canonical_names for the kept top-N (sort first).
                ranked = sorted(
                    two_hop_paths.items(),
                    key=lambda kv: (-len(kv[1]["via_companies"]),
                                    -len(kv[1]["via_directors"])),
                )[:top_two_hop]
                kept_ids = [mid for mid, _ in ranked]
                kept_meta = _resolve_canonical_names(cur, kept_ids)
                for mid, info in ranked:
                    meta = kept_meta.get(mid, {})
                    two_hop.append({
                        "master_id": mid,
                        "canonical_name": meta.get("canonical_name"),
                        "state": meta.get("state"),
                        "naics": meta.get("naics"),
                        "via_company_count": len(info["via_companies"]),
                        "via_director_count": len(info["via_directors"]),
                    })

    return {
        "anchor": {
            "master_id": master_id,
            "canonical_name": anchor_name,
        },
        "stats": {
            "one_hop_count": len(one_hop),
            "two_hop_count": two_hop_count,
            "two_hop_returned": len(two_hop),
            "shared_directors_total": len(shared_directors),
            "should_surface": len(one_hop) >= MIN_NEIGHBORS_TO_SURFACE,
        },
        "shared_directors": [
            {"name": n, "slug": name_to_slug(n)}
            for n in sorted(shared_directors)
        ],
        "one_hop": one_hop,
        "two_hop": two_hop,
    }
