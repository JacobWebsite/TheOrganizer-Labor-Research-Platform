"""
EPA ECHO endpoint mirroring the OSHA shape on the employer profile.

24Q-31: EnvironmentalCard. Pulls the EPA ECHO facilities linked to a master
employer through master_employer_source_ids, aggregates them into a
summary block and a top-N facility table, and returns the latest record
date for the freshness footer.

Mirrors the contract of OshaSection.jsx (summary + establishments +
latest_record_date) so the EnvironmentalCard component can reuse the same
rendering pattern.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db

router = APIRouter()

# Top facilities returned in the table. Same magnitude as the OSHA
# enrichment query (25). EnvironmentalCard initially shows 5, then expands.
DEFAULT_FACILITY_LIMIT = 25


def _safe_iso(d) -> Optional[str]:
    """Convert a date / datetime to ISO string, tolerate None / strings."""
    if d is None:
        return None
    if hasattr(d, "isoformat"):
        try:
            return d.isoformat()
        except Exception:  # pragma: no cover - defensive
            return None
    return str(d)


@router.get("/api/employers/master/{master_id}/epa-echo")
def get_master_epa_echo(
    master_id: int,
    facility_limit: int = Query(
        default=DEFAULT_FACILITY_LIMIT,
        ge=1,
        le=200,
        description="Max facilities returned in the facilities array",
    ),
) -> Dict[str, Any]:
    """Return EPA ECHO summary + top facilities for a master employer.

    Response shape:
        {
            "summary": {
                "total_facilities": int,
                "active_facilities": int,
                "total_inspections": int,
                "total_formal_actions": int,
                "total_informal_actions": int,
                "total_penalties": float,
                "snc_facilities": int,        # Significant Non-Complier flag count
            },
            "facilities": [
                {
                    "registry_id": str,
                    "facility_name": str,
                    "city": str,
                    "state": str,
                    "naics": str,
                    "active": bool,
                    "snc_flag": bool,
                    "inspection_count": int,
                    "formal_action_count": int,
                    "informal_action_count": int,
                    "total_penalties": float,
                    "last_inspection_date": iso str | null,
                    "last_formal_action_date": iso str | null,
                    "last_penalty_date": iso str | null,
                    "compliance_status": str | null,
                    "match_confidence": float | null,
                },
                ...
            ],
            "latest_record_date": iso str | null,
        }
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Verify master exists. Mirror master.py error semantics.
            cur.execute(
                "SELECT 1 FROM master_employers WHERE master_id = %s",
                [master_id],
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Master employer not found")

            # Pull all EPA registry_ids linked to this master, with the
            # match_confidence carried for the per-facility row. We resolve
            # the facility row in epa_echo_facilities via registry_id.
            cur.execute(
                """
                SELECT
                  ef.registry_id,
                  ef.fac_name              AS facility_name,
                  ef.fac_city              AS city,
                  ef.fac_state             AS state,
                  ef.fac_zip               AS zip,
                  ef.fac_naics_codes       AS naics,
                  ef.fac_active_flag       AS active_flag,
                  ef.fac_snc_flag          AS snc_flag,
                  COALESCE(ef.fac_inspection_count, 0)    AS inspection_count,
                  COALESCE(ef.fac_formal_action_count, 0) AS formal_action_count,
                  COALESCE(ef.fac_informal_count, 0)      AS informal_action_count,
                  COALESCE(ef.fac_total_penalties, 0)     AS total_penalties,
                  ef.fac_date_last_inspection      AS last_inspection_date,
                  ef.fac_date_last_formal_action   AS last_formal_action_date,
                  ef.fac_date_last_penalty         AS last_penalty_date,
                  ef.fac_compliance_status         AS compliance_status,
                  sid.match_confidence
                FROM master_employer_source_ids sid
                JOIN epa_echo_facilities ef ON ef.registry_id = sid.source_id
                WHERE sid.master_id = %s
                  AND sid.source_system = 'epa_echo'
                ORDER BY
                  COALESCE(ef.fac_total_penalties, 0) DESC NULLS LAST,
                  COALESCE(ef.fac_formal_action_count, 0) DESC,
                  COALESCE(ef.fac_inspection_count, 0) DESC
                """,
                [master_id],
            )
            rows = cur.fetchall() or []

    # Empty path: still return the shape so the frontend doesn't have to
    # special-case missing data. EnvironmentalCard renders a "no records
    # matched" panel based on summary.total_facilities == 0.
    if not rows:
        return {
            "summary": {
                "total_facilities": 0,
                "active_facilities": 0,
                "total_inspections": 0,
                "total_formal_actions": 0,
                "total_informal_actions": 0,
                "total_penalties": 0.0,
                "snc_facilities": 0,
            },
            "facilities": [],
            "latest_record_date": None,
        }

    # Aggregate the summary across ALL linked facilities (not just the
    # truncated facility list). active_facilities counts the EPA
    # 'fac_active_flag' = 'Y' rows. snc_facilities counts SNC flag = 'Y'.
    total_facilities = len(rows)
    active_facilities = sum(1 for r in rows if (r.get("active_flag") or "").upper() == "Y")
    snc_facilities = sum(1 for r in rows if (r.get("snc_flag") or "").upper() == "Y")
    total_inspections = sum(int(r["inspection_count"] or 0) for r in rows)
    total_formal = sum(int(r["formal_action_count"] or 0) for r in rows)
    total_informal = sum(int(r["informal_action_count"] or 0) for r in rows)
    total_penalties = float(sum(float(r["total_penalties"] or 0) for r in rows))

    # Latest record date across inspection / formal action / penalty.
    latest_record_date = None
    for r in rows:
        for col in ("last_inspection_date", "last_formal_action_date", "last_penalty_date"):
            v = r.get(col)
            if v is None:
                continue
            if latest_record_date is None or v > latest_record_date:
                latest_record_date = v

    # Truncate facilities array to facility_limit. Already ordered by the
    # SQL above (penalties DESC, formal_action DESC, inspection DESC).
    facilities: List[Dict[str, Any]] = []
    for r in rows[:facility_limit]:
        facilities.append(
            {
                "registry_id": r["registry_id"],
                "facility_name": r["facility_name"],
                "city": r["city"],
                "state": r["state"],
                "zip": r.get("zip"),
                "naics": r["naics"],
                "active": (r.get("active_flag") or "").upper() == "Y",
                "snc_flag": (r.get("snc_flag") or "").upper() == "Y",
                "inspection_count": int(r["inspection_count"] or 0),
                "formal_action_count": int(r["formal_action_count"] or 0),
                "informal_action_count": int(r["informal_action_count"] or 0),
                "total_penalties": float(r["total_penalties"] or 0),
                "last_inspection_date": _safe_iso(r["last_inspection_date"]),
                "last_formal_action_date": _safe_iso(r["last_formal_action_date"]),
                "last_penalty_date": _safe_iso(r["last_penalty_date"]),
                "compliance_status": r.get("compliance_status"),
                "match_confidence": (
                    float(r["match_confidence"]) if r.get("match_confidence") is not None else None
                ),
            }
        )

    return {
        "summary": {
            "total_facilities": total_facilities,
            "active_facilities": active_facilities,
            "total_inspections": total_inspections,
            "total_formal_actions": total_formal,
            "total_informal_actions": total_informal,
            "total_penalties": total_penalties,
            "snc_facilities": snc_facilities,
        },
        "facilities": facilities,
        "latest_record_date": _safe_iso(latest_record_date),
    }
