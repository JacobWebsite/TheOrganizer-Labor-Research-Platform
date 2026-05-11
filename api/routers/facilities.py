"""
Facilities (geocoded) endpoint for the master profile map card.

Week 3 A.2 (ROADMAP_2026_05_04_to_2026_07_05_LAUNCH.md): backs the
FacilitiesMapCard on the master profile. Returns the union of every
geocoded location linked to a master employer through
master_employer_source_ids -- EPA ECHO facilities, F-7 bargaining-unit
addresses, and Mergent corporate addresses (HQ + branch where present).

OSHA establishments + NY ABO state contracts have addresses but no
lat/lng in the database, so they're omitted here. Geocoding those
sources is its own workstream (deferred per Week 3 A.2 spec).

Response shape:
    {
        "summary": {
            "total_facilities": int,
            "by_source": {"epa": int, "f7": int, "mergent": int},
            "states": [...],
        },
        "facilities": [
            {
                "id": str,             # source-prefixed unique id
                "source": "epa"|"f7"|"mergent",
                "lat": float,
                "lng": float,
                "label": str,           # display name
                "address": str|null,
                "city": str|null,
                "state": str|null,
                "zip": str|null,
                "extra": {...source-specific fields...},
            },
            ...
        ],
    }
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db

router = APIRouter()

# Hard cap to prevent runaway responses on huge corporate families.
# Abbott has 7 EPA + handful of F-7s; Walmart's family could in principle
# have thousands across all sources -- 2,000 is enough for a Leaflet map
# while keeping payload <500 KB.
DEFAULT_FACILITY_LIMIT = 2000


def _is_valid_coord(lat, lng) -> bool:
    """Bounds check: reject NULL, sentinel zeros, or out-of-range values."""
    if lat is None or lng is None:
        return False
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False
    if lat == 0.0 and lng == 0.0:
        return False  # Likely sentinel; nothing legitimate sits at 0,0.
    if lat < -90 or lat > 90:
        return False
    if lng < -180 or lng > 180:
        return False
    return True


@router.get("/api/employers/master/{master_id}/facilities")
def get_master_facilities(
    master_id: int,
    limit: int = Query(
        default=DEFAULT_FACILITY_LIMIT,
        ge=1,
        le=10000,
        description="Maximum facilities returned across all sources combined.",
    ),
) -> Dict[str, Any]:
    """Combined geocoded facility list across EPA + F-7 + Mergent."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Verify master exists. Mirror master.py error semantics.
            cur.execute(
                "SELECT 1 FROM master_employers WHERE master_id = %s",
                [master_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Master employer not found")

            facilities: List[Dict[str, Any]] = []
            states: set = set()

            # 1. EPA ECHO facilities. Order by penalties DESC so the most
            # significant locations are at the top of the truncated list.
            cur.execute(
                """
                SELECT
                  ef.registry_id,
                  ef.fac_name,
                  ef.fac_street,
                  ef.fac_city,
                  ef.fac_state,
                  ef.fac_zip,
                  ef.fac_lat,
                  ef.fac_long,
                  ef.fac_active_flag,
                  ef.fac_snc_flag,
                  COALESCE(ef.fac_inspection_count, 0) AS inspection_count,
                  COALESCE(ef.fac_formal_action_count, 0) AS formal_action_count,
                  COALESCE(ef.fac_total_penalties, 0) AS total_penalties
                FROM master_employer_source_ids sid
                JOIN epa_echo_facilities ef ON ef.registry_id = sid.source_id
                WHERE sid.master_id = %s
                  AND sid.source_system = 'epa_echo'
                  AND ef.fac_lat IS NOT NULL
                  AND ef.fac_long IS NOT NULL
                ORDER BY COALESCE(ef.fac_total_penalties, 0) DESC NULLS LAST
                """,
                [master_id],
            )
            for r in cur.fetchall() or []:
                if not _is_valid_coord(r["fac_lat"], r["fac_long"]):
                    continue
                state = (r.get("fac_state") or "").strip() or None
                if state:
                    states.add(state)
                facilities.append(
                    {
                        "id": f"epa-{r['registry_id']}",
                        "source": "epa",
                        "lat": float(r["fac_lat"]),
                        "lng": float(r["fac_long"]),
                        "label": (r.get("fac_name") or "EPA Facility").strip() or "EPA Facility",
                        "address": (r.get("fac_street") or None),
                        "city": r.get("fac_city"),
                        "state": state,
                        "zip": r.get("fac_zip"),
                        "extra": {
                            "registry_id": r["registry_id"],
                            "active": (r.get("fac_active_flag") or "").upper() == "Y",
                            "snc_flag": (r.get("fac_snc_flag") or "").upper() == "Y",
                            "inspection_count": int(r["inspection_count"] or 0),
                            "formal_action_count": int(r["formal_action_count"] or 0),
                            "total_penalties": float(r["total_penalties"] or 0),
                        },
                    }
                )

            # 2. F-7 bargaining-unit addresses. F-7 is the OLMS LM-2 union
            # filing layer -- a "facility" here is a represented
            # workplace, not a corporate office. Order by latest_unit_size
            # DESC so the biggest units float to the top.
            cur.execute(
                """
                SELECT
                  f7.employer_id,
                  f7.employer_name,
                  f7.street,
                  f7.city,
                  f7.state,
                  f7.zip,
                  f7.latitude,
                  f7.longitude,
                  f7.latest_unit_size,
                  f7.latest_union_name,
                  f7.latest_union_fnum,
                  f7.latest_notice_date
                FROM master_employer_source_ids sid
                JOIN f7_employers f7 ON f7.employer_id = sid.source_id
                WHERE sid.master_id = %s
                  AND sid.source_system = 'f7'
                  AND f7.latitude IS NOT NULL
                  AND f7.longitude IS NOT NULL
                ORDER BY COALESCE(f7.latest_unit_size, 0) DESC NULLS LAST
                """,
                [master_id],
            )
            for r in cur.fetchall() or []:
                if not _is_valid_coord(r["latitude"], r["longitude"]):
                    continue
                state = (r.get("state") or "").strip() or None
                if state:
                    states.add(state)
                facilities.append(
                    {
                        "id": f"f7-{r['employer_id']}",
                        "source": "f7",
                        "lat": float(r["latitude"]),
                        "lng": float(r["longitude"]),
                        "label": (r.get("employer_name") or "F-7 Workplace").strip() or "F-7 Workplace",
                        "address": (r.get("street") or None),
                        "city": r.get("city"),
                        "state": state,
                        "zip": r.get("zip"),
                        "extra": {
                            "employer_id": r["employer_id"],
                            "latest_unit_size": (
                                int(r["latest_unit_size"]) if r.get("latest_unit_size") is not None else None
                            ),
                            "latest_union_name": r.get("latest_union_name"),
                            "latest_union_fnum": r.get("latest_union_fnum"),
                            "latest_notice_date": (
                                r["latest_notice_date"].isoformat()
                                if r.get("latest_notice_date") is not None and hasattr(r["latest_notice_date"], "isoformat")
                                else r.get("latest_notice_date")
                            ),
                        },
                    }
                )

            # 3. Mergent corporate addresses. Mergent typically covers HQ
            # + maybe a few branches. The link key is `duns` (master
            # source_id == mergent_employers.duns). Sort by site headcount
            # so the largest sites surface first when limit is hit.
            cur.execute(
                """
                SELECT
                  m.duns AS source_id,
                  m.company_name,
                  m.street_address,
                  m.city,
                  m.state,
                  m.zip,
                  m.latitude,
                  m.longitude,
                  m.employees_site,
                  m.employees_all_sites,
                  m.location_type
                FROM master_employer_source_ids sid
                JOIN mergent_employers m ON m.duns = sid.source_id
                WHERE sid.master_id = %s
                  AND sid.source_system = 'mergent'
                  AND m.latitude IS NOT NULL
                  AND m.longitude IS NOT NULL
                ORDER BY COALESCE(m.employees_site, m.employees_all_sites, 0) DESC NULLS LAST
                """,
                [master_id],
            )
            for r in cur.fetchall() or []:
                if not _is_valid_coord(r["latitude"], r["longitude"]):
                    continue
                state = (r.get("state") or "").strip() or None
                if state:
                    states.add(state)
                facilities.append(
                    {
                        "id": f"mergent-{r['source_id']}",
                        "source": "mergent",
                        "lat": float(r["latitude"]),
                        "lng": float(r["longitude"]),
                        "label": (r.get("company_name") or "Corporate Address").strip()
                        or "Corporate Address",
                        "address": (r.get("street_address") or None),
                        "city": r.get("city"),
                        "state": state,
                        "zip": r.get("zip"),
                        "extra": {
                            "duns": r["source_id"],
                            "employees_site": (
                                int(r["employees_site"]) if r.get("employees_site") is not None else None
                            ),
                            "employees_all_sites": (
                                int(r["employees_all_sites"]) if r.get("employees_all_sites") is not None else None
                            ),
                            "location_type": r.get("location_type"),
                        },
                    }
                )

    # Counts pre-truncation so the summary is honest about total coverage.
    by_source: Dict[str, int] = {"epa": 0, "f7": 0, "mergent": 0}
    for f in facilities:
        by_source[f["source"]] = by_source.get(f["source"], 0) + 1
    total = len(facilities)

    # Truncate to limit. EPA rows already came back ordered by penalty
    # severity, F-7 by unit size, Mergent by employee count -- so simply
    # taking the first `limit` keeps the most significant per source.
    if total > limit:
        facilities = facilities[:limit]

    return {
        "summary": {
            "total_facilities": total,
            "by_source": by_source,
            "states": sorted(states),
        },
        "facilities": facilities,
    }
