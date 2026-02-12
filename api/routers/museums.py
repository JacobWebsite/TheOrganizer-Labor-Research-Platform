from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from ..database import get_db

router = APIRouter()


@router.get("/api/museums/targets")
def search_museum_targets(
    tier: Optional[str] = None,
    city: Optional[str] = None,
    min_employees: Optional[int] = None,
    max_employees: Optional[int] = None,
    min_score: Optional[int] = None,
    has_osha_violations: Optional[bool] = None,
    has_govt_contracts: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("total_score", pattern="^(total_score|best_employee_count|revenue_millions|employer_name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """
    Search museum organizing targets.

    - tier: TOP, HIGH, MEDIUM, LOW
    - city: Filter by city name
    - min_employees/max_employees: Employee count range
    - min_score: Minimum organizing score
    - has_osha_violations: Filter for museums with OSHA violations
    - has_govt_contracts: Filter for museums with government contracts
    - search: Text search on employer name
    - sort_by: Field to sort by
    - sort_order: asc or desc
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if tier:
                conditions.append("priority_tier = %s")
                params.append(tier.upper())
            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if min_employees:
                conditions.append("best_employee_count >= %s")
                params.append(min_employees)
            if max_employees:
                conditions.append("best_employee_count <= %s")
                params.append(max_employees)
            if min_score:
                conditions.append("total_score >= %s")
                params.append(min_score)
            if has_osha_violations is True:
                conditions.append("osha_violation_count > 0")
            if has_osha_violations is False:
                conditions.append("(osha_violation_count = 0 OR osha_violation_count IS NULL)")
            if has_govt_contracts is True:
                conditions.append("total_contract_value > 0")
            if has_govt_contracts is False:
                conditions.append("(total_contract_value = 0 OR total_contract_value IS NULL)")
            if search:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{search}%")

            where_clause = " AND ".join(conditions)

            # Count total
            cur.execute(f"""
                SELECT COUNT(*) FROM v_museum_organizing_targets
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            # Get results
            order_dir = "DESC" if sort_order == "desc" else "ASC"
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM v_museum_organizing_targets
                WHERE {where_clause}
                ORDER BY {sort_by} {order_dir} NULLS LAST, employer_name
                LIMIT %s OFFSET %s
            """, params)

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "targets": cur.fetchall()
            }


@router.get("/api/museums/targets/stats")
def get_museum_target_stats():
    """Get summary statistics for museum organizing targets by tier"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_museum_target_stats")
            tiers = cur.fetchall()

            # Also get overall totals
            cur.execute("""
                SELECT
                    COUNT(*) as total_targets,
                    SUM(best_employee_count) as total_employees,
                    ROUND(AVG(total_score), 1) as avg_score,
                    SUM(revenue_millions) as total_revenue_millions,
                    COUNT(*) FILTER (WHERE has_osha_data) as with_osha_data,
                    COUNT(*) FILTER (WHERE has_990_data) as with_990_data,
                    COUNT(*) FILTER (WHERE osha_violation_count > 0) as with_violations,
                    COUNT(*) FILTER (WHERE total_contract_value > 0) as with_contracts
                FROM v_museum_organizing_targets
            """)
            totals = cur.fetchone()

            return {
                "by_tier": tiers,
                "totals": totals
            }


@router.get("/api/museums/targets/{target_id}")
def get_museum_target_detail(target_id: str):
    """Get detailed information for a specific museum target"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_museum_organizing_targets
                WHERE id = %s
            """, [target_id])
            target = cur.fetchone()

            if not target:
                raise HTTPException(status_code=404, detail="Target not found")

            # Get nearby unionized museums (same city or nearby)
            cur.execute("""
                SELECT employer_name, city, best_employee_count, union_name, nlrb_election_date
                FROM v_museum_unionized
                WHERE city = %s OR state = %s
                ORDER BY best_employee_count DESC
                LIMIT 5
            """, [target['city'], target['state']])
            nearby_unionized = cur.fetchall()

            return {
                "target": target,
                "nearby_unionized": nearby_unionized
            }


@router.get("/api/museums/targets/cities")
def get_museum_target_cities():
    """Get list of cities with museum targets for dropdown"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT city, COUNT(*) as target_count, SUM(best_employee_count) as total_employees
                FROM v_museum_organizing_targets
                GROUP BY city
                ORDER BY COUNT(*) DESC
            """)
            return {"cities": cur.fetchall()}


@router.get("/api/museums/unionized")
def get_unionized_museums(
    city: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get list of already-unionized museums for reference"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if search:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{search}%")

            where_clause = " AND ".join(conditions)

            cur.execute(f"""
                SELECT COUNT(*) FROM v_museum_unionized
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM v_museum_unionized
                WHERE {where_clause}
                ORDER BY best_employee_count DESC
                LIMIT %s OFFSET %s
            """, params)

            return {
                "total": total,
                "museums": cur.fetchall()
            }


@router.get("/api/museums/summary")
def get_museum_sector_summary():
    """Get overall summary of museum sector (targets + unionized)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Target stats
            cur.execute("""
                SELECT
                    COUNT(*) as target_count,
                    SUM(best_employee_count) as target_employees,
                    ROUND(SUM(revenue_millions), 1) as target_revenue_millions
                FROM v_museum_organizing_targets
            """)
            targets = cur.fetchone()

            # Unionized stats
            cur.execute("""
                SELECT
                    COUNT(*) as unionized_count,
                    SUM(best_employee_count) as unionized_employees,
                    ROUND(SUM(revenue_millions), 1) as unionized_revenue_millions
                FROM v_museum_unionized
            """)
            unionized = cur.fetchone()

            # Score distribution
            cur.execute("""
                SELECT
                    priority_tier,
                    COUNT(*) as count,
                    SUM(best_employee_count) as employees
                FROM v_museum_organizing_targets
                GROUP BY priority_tier
                ORDER BY
                    CASE priority_tier
                        WHEN 'TOP' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END
            """)
            by_tier = cur.fetchall()

            return {
                "sector": "MUSEUMS",
                "targets": targets,
                "unionized": unionized,
                "by_tier": by_tier,
                "union_density_pct": round(
                    unionized['unionized_count'] / (targets['target_count'] + unionized['unionized_count']) * 100, 1
                ) if targets['target_count'] else 0
            }
