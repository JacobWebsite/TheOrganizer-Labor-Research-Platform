from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from ..database import get_db
from ..helpers import safe_sort_col, safe_order_dir

router = APIRouter()


@router.get("/api/osha/summary")
def get_osha_summary():
    """Get OSHA database summary statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM osha_establishments) as total_establishments,
                    (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'Y') as union_establishments,
                    (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'N') as nonunion_establishments,
                    (SELECT SUM(violation_count) FROM osha_violation_summary) as total_violations,
                    (SELECT SUM(total_penalties) FROM osha_violation_summary) as total_penalties,
                    (SELECT COUNT(*) FROM osha_accidents) as total_accidents,
                    (SELECT COUNT(*) FROM osha_accidents WHERE is_fatality = true) as fatality_incidents,
                    (SELECT COUNT(*) FROM osha_f7_matches) as f7_matches,
                    (SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches) as unique_f7_employers_matched
            """)
            return {"summary": cur.fetchone()}


@router.get("/api/osha/establishments/search")
def search_osha_establishments(
    q: Optional[str] = None,
    state: Optional[str] = None,
    union_status: Optional[str] = None,
    risk_level: Optional[str] = None,
    naics: Optional[str] = None,
    f7_matched: Optional[bool] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0
):
    """Search OSHA establishments with filters"""
    conditions = []
    params = []

    if q:
        conditions.append("(estab_name_normalized ILIKE %s OR estab_name ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if union_status:
        conditions.append("union_status = %s")
        params.append(union_status.upper())
    if risk_level:
        conditions.append("risk_level = %s")
        params.append(risk_level.upper())
    if naics:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics}%")
    if f7_matched is not None:
        if f7_matched:
            conditions.append("f7_employer_id IS NOT NULL")
        else:
            conditions.append("f7_employer_id IS NULL")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT establishment_id, estab_name, site_address, site_city, site_state, site_zip,
                       naics_code, union_status, employee_count, total_inspections, last_inspection_date,
                       willful_violations, repeat_violations, serious_violations, total_violations,
                       total_penalties, accidents, fatalities, risk_level,
                       f7_employer_id, f7_employer_name, latest_union_name, match_confidence
                FROM v_osha_establishment_search
                WHERE {where_clause}
                ORDER BY total_penalties DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            results = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) as cnt FROM v_osha_establishment_search WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']

            return {"establishments": results, "total": total, "limit": limit, "offset": offset}


@router.get("/api/osha/establishments/{establishment_id}")
def get_osha_establishment(establishment_id: str):
    """Get detailed OSHA establishment info including violations and accidents"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get establishment
            cur.execute("SELECT * FROM v_osha_establishment_search WHERE establishment_id = %s", [establishment_id])
            establishment = cur.fetchone()
            if not establishment:
                raise HTTPException(status_code=404, detail="Establishment not found")

            # Get violations summary
            cur.execute("""
                SELECT violation_type, violation_count, total_penalties,
                       first_violation_date, last_violation_date
                FROM osha_violation_summary WHERE establishment_id = %s
                ORDER BY violation_count DESC
            """, [establishment_id])
            violations = cur.fetchall()

            # Get recent violations detail
            cur.execute("""
                SELECT activity_nr, violation_type, issuance_date, current_penalty, standard
                FROM osha_violations_detail WHERE establishment_id = %s
                ORDER BY issuance_date DESC LIMIT 20
            """, [establishment_id])
            recent_violations = cur.fetchall()

            # Get accidents
            cur.execute("""
                SELECT summary_nr, event_date, is_fatality, injury_count, hospitalized, event_description
                FROM osha_accidents WHERE establishment_id = %s
                ORDER BY event_date DESC
            """, [establishment_id])
            accidents = cur.fetchall()

            return {
                "establishment": establishment,
                "violation_summary": violations,
                "recent_violations": recent_violations,
                "accidents": accidents
            }


@router.get("/api/osha/by-state")
def get_osha_by_state():
    """Get OSHA summary statistics by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_osha_state_summary ORDER BY establishments DESC")
            return {"states": cur.fetchall()}


@router.get("/api/osha/high-severity")
def get_osha_high_severity(
    state: Optional[str] = None,
    violation_type: Optional[str] = None,
    limit: int = Query(default=100, le=500)
):
    """Get recent high-severity violations (Willful/Repeat)"""
    conditions = []
    params = []

    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if violation_type:
        conditions.append("violation_type = %s")
        params.append(violation_type.upper())

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM v_osha_high_severity_recent
                WHERE {where_clause}
                ORDER BY issuance_date DESC
                LIMIT %s
            """, params + [limit])
            return {"violations": cur.fetchall()}


@router.get("/api/osha/organizing-targets")
def get_osha_organizing_targets(
    state: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """Get non-union establishments with significant safety violations (organizing targets)"""
    conditions = []
    params = []

    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if risk_level:
        conditions.append("risk_level = %s")
        params.append(risk_level.upper())

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM v_osha_organizing_targets
                WHERE {where_clause}
                ORDER BY
                    CASE risk_level
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MODERATE' THEN 3
                        ELSE 4
                    END,
                    total_penalties DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            results = cur.fetchall()

            cur.execute(f"SELECT COUNT(*) as cnt FROM v_osha_organizing_targets WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']

            return {"targets": results, "total": total, "limit": limit, "offset": offset}


@router.get("/api/osha/employer-safety/{f7_employer_id}")
def get_employer_safety_profile(f7_employer_id: str):
    """Get OSHA safety profile for an F-7 employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_employer_safety_profile
                WHERE employer_id = %s
            """, [f7_employer_id])
            profiles = cur.fetchall()
            if not profiles:
                raise HTTPException(status_code=404, detail="No OSHA data found for this employer")
            return {"safety_profiles": profiles}
