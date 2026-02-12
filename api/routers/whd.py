from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db

router = APIRouter()


@router.get("/api/whd/summary")
def get_whd_summary():
    """Get WHD national database summary statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM whd_cases) as total_cases,
                    (SELECT COUNT(DISTINCT case_id) FROM whd_cases) as unique_case_ids,
                    (SELECT COUNT(DISTINCT state) FROM whd_cases WHERE state IS NOT NULL) as states_covered,
                    (SELECT SUM(COALESCE(backwages_amount, 0)) FROM whd_cases) as total_backwages,
                    (SELECT SUM(COALESCE(civil_penalties, 0)) FROM whd_cases) as total_penalties,
                    (SELECT SUM(COALESCE(employees_violated, 0)) FROM whd_cases) as total_employees_violated,
                    (SELECT SUM(COALESCE(total_violations, 0)) FROM whd_cases) as total_violations,
                    (SELECT COUNT(*) FROM whd_cases WHERE flsa_repeat_violator = TRUE) as repeat_violators,
                    (SELECT MIN(findings_start_date) FROM whd_cases WHERE findings_start_date IS NOT NULL) as earliest_finding,
                    (SELECT MAX(findings_end_date) FROM whd_cases WHERE findings_end_date IS NOT NULL) as latest_finding
            """)
            summary = cur.fetchone()

            # Top states
            cur.execute("""
                SELECT state, COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                       SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                       SUM(COALESCE(employees_violated, 0)) as employees_violated
                FROM whd_cases
                WHERE state IS NOT NULL
                GROUP BY state
                ORDER BY case_count DESC
                LIMIT 10
            """)
            top_states = cur.fetchall()

            # Top industries
            cur.execute("""
                SELECT naics_code, COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages
                FROM whd_cases
                WHERE naics_code IS NOT NULL
                GROUP BY naics_code
                ORDER BY case_count DESC
                LIMIT 10
            """)
            top_industries = cur.fetchall()

            # Match coverage
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL) as f7_matched,
                    (SELECT COUNT(*) FROM f7_employers_deduped) as f7_total,
                    (SELECT COUNT(*) FROM mergent_employers WHERE whd_violation_count IS NOT NULL) as mergent_matched,
                    (SELECT COUNT(*) FROM mergent_employers) as mergent_total
            """)
            coverage = cur.fetchone()

            return {
                "summary": summary,
                "top_states": top_states,
                "top_industries": top_industries,
                "match_coverage": coverage
            }


@router.get("/api/whd/search")
def search_whd_cases(
    q: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    naics: Optional[str] = None,
    min_backwages: Optional[float] = None,
    repeat_only: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search WHD cases by employer name, state, city, NAICS"""
    conditions = []
    params = []

    if q:
        conditions.append("(trade_name ILIKE %s OR legal_name ILIKE %s OR name_normalized ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q.lower()}%"])
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    if city:
        conditions.append("city ILIKE %s")
        params.append(f"%{city}%")
    if naics:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics}%")
    if min_backwages:
        conditions.append("backwages_amount >= %s")
        params.append(min_backwages)
    if repeat_only:
        conditions.append("flsa_repeat_violator = TRUE")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) as cnt FROM whd_cases WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']

            query_params = params + [limit, offset]
            cur.execute(f"""
                SELECT case_id, trade_name, legal_name, city, state, zip_code, naics_code,
                       total_violations, civil_penalties, employees_violated,
                       backwages_amount, flsa_violations, flsa_repeat_violator,
                       flsa_child_labor_violations, flsa_child_labor_minors,
                       findings_start_date, findings_end_date
                FROM whd_cases
                WHERE {where_clause}
                ORDER BY backwages_amount DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, query_params)
            results = cur.fetchall()

            return {"total": total, "limit": limit, "offset": offset, "results": results}


@router.get("/api/whd/by-state/{state}")
def get_whd_by_state(state: str):
    """Get WHD violations summary for a specific state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_cases,
                    SUM(COALESCE(total_violations, 0)) as total_violations,
                    SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                    SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                    SUM(COALESCE(employees_violated, 0)) as employees_violated,
                    COUNT(*) FILTER (WHERE flsa_repeat_violator = TRUE) as repeat_violators,
                    SUM(COALESCE(flsa_child_labor_violations, 0)) as child_labor_violations
                FROM whd_cases
                WHERE state = %s
            """, [state.upper()])
            summary = cur.fetchone()

            # Top violators in state
            cur.execute("""
                SELECT name_normalized, city,
                       COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                       SUM(COALESCE(employees_violated, 0)) as employees_violated,
                       BOOL_OR(flsa_repeat_violator) as is_repeat
                FROM whd_cases
                WHERE state = %s AND name_normalized IS NOT NULL
                GROUP BY name_normalized, city
                ORDER BY total_backwages DESC
                LIMIT 20
            """, [state.upper()])
            top_violators = cur.fetchall()

            # By NAICS in state
            cur.execute("""
                SELECT naics_code, COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages
                FROM whd_cases
                WHERE state = %s AND naics_code IS NOT NULL
                GROUP BY naics_code
                ORDER BY case_count DESC
                LIMIT 10
            """, [state.upper()])
            by_naics = cur.fetchall()

            return {
                "state": state.upper(),
                "summary": summary,
                "top_violators": top_violators,
                "by_naics": by_naics
            }


@router.get("/api/whd/employer/{employer_id}")
def get_whd_employer_cases(employer_id: str):
    """Get WHD cases matched to a specific employer (F7 or Mergent)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Try F7 first
            cur.execute("""
                SELECT employer_name_aggressive, state, city,
                       whd_violation_count, whd_backwages, whd_employees_violated,
                       whd_penalties, whd_child_labor, whd_repeat_violator
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            f7 = cur.fetchone()

            if f7 and f7['employer_name_aggressive']:
                name_norm = f7['employer_name_aggressive']
                state = f7['state']
                city = f7['city']
            else:
                # Try Mergent by duns
                cur.execute("""
                    SELECT company_name_normalized, state, city,
                           whd_violation_count, whd_backwages, whd_employees_violated,
                           whd_penalties, whd_child_labor, whd_repeat_violator
                    FROM mergent_employers
                    WHERE duns = %s
                """, [employer_id])
                mergent = cur.fetchone()
                if not mergent:
                    raise HTTPException(status_code=404, detail="Employer not found")
                name_norm = mergent['company_name_normalized']
                state = mergent['state']
                city = mergent['city']

            # Find matching WHD cases
            cur.execute("""
                SELECT case_id, trade_name, legal_name, city, state, naics_code,
                       total_violations, civil_penalties, employees_violated,
                       backwages_amount, flsa_violations, flsa_repeat_violator,
                       flsa_child_labor_violations, findings_start_date, findings_end_date
                FROM whd_cases
                WHERE name_normalized = %s AND state = %s
                ORDER BY backwages_amount DESC NULLS LAST
            """, [name_norm, state])
            cases = cur.fetchall()

            return {
                "employer_id": employer_id,
                "name_normalized": name_norm,
                "state": state,
                "city": city,
                "whd_summary": f7 or mergent,
                "cases": cases
            }


@router.get("/api/whd/top-violators")
def get_whd_top_violators(
    state: Optional[str] = None,
    metric: str = Query("backwages", pattern="^(backwages|violations|penalties|employees)$"),
    limit: int = Query(50, le=200)
):
    """Get worst WHD violators by backwages, violations, penalties, or employees affected"""
    order_col = {
        "backwages": "total_backwages",
        "violations": "total_violations",
        "penalties": "total_penalties",
        "employees": "total_employees_violated"
    }[metric]

    conditions = ["name_normalized IS NOT NULL"]
    params = []
    if state:
        conditions.append("state = %s")
        params.append(state.upper())

    where_clause = " AND ".join(conditions)
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT name_normalized, city, state,
                       COUNT(*) as case_count,
                       SUM(COALESCE(total_violations, 0)) as total_violations,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                       SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                       SUM(COALESCE(employees_violated, 0)) as total_employees_violated,
                       BOOL_OR(flsa_repeat_violator) as is_repeat_violator,
                       SUM(COALESCE(flsa_child_labor_violations, 0)) as child_labor_violations,
                       MAX(findings_end_date) as latest_finding
                FROM whd_cases
                WHERE {where_clause}
                GROUP BY name_normalized, city, state
                ORDER BY {order_col} DESC NULLS LAST
                LIMIT %s
            """, params)
            results = cur.fetchall()

            return {"metric": metric, "state": state, "results": results}
