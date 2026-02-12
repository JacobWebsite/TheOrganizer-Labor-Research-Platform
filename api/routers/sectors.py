from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from ..database import get_db
from ..helpers import SECTOR_VIEWS

router = APIRouter()


@router.get("/api/sectors/list")
def list_sectors():
    """List all available sectors with target counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    sector_category,
                    COUNT(*) as total_employers,
                    SUM(CASE WHEN has_union THEN 1 ELSE 0 END) as unionized_count,
                    SUM(CASE WHEN has_union IS NOT TRUE THEN 1 ELSE 0 END) as target_count,
                    SUM(COALESCE(employees_site, 0)) as total_employees,
                    ROUND(100.0 * SUM(CASE WHEN has_union THEN 1 ELSE 0 END) / COUNT(*), 1) as union_density_pct
                FROM mergent_employers
                WHERE sector_category IS NOT NULL
                GROUP BY sector_category
                ORDER BY COUNT(*) DESC
            """)
            return {"sectors": cur.fetchall()}


@router.get("/api/sectors/{sector}/summary")
def get_sector_summary(sector: str):
    """Get summary statistics for a sector"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found. Valid: {list(SECTOR_VIEWS.keys())}")

    sector_upper = sector_key.upper()

    with get_db() as conn:
        with conn.cursor() as cur:
            # Target stats
            cur.execute("""
                SELECT
                    COUNT(*) as target_count,
                    SUM(COALESCE(employees_site, ny990_employees, 0)) as target_employees,
                    SUM(COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0)) as contract_value
                FROM mergent_employers
                WHERE sector_category = %s AND has_union IS NOT TRUE
            """, [sector_upper])
            targets = cur.fetchone()

            # Unionized stats
            cur.execute("""
                SELECT
                    COUNT(*) as unionized_count,
                    SUM(COALESCE(employees_site, ny990_employees, 0)) as unionized_employees
                FROM mergent_employers
                WHERE sector_category = %s AND has_union = TRUE
            """, [sector_upper])
            unionized = cur.fetchone()

            # Score distribution
            cur.execute("""
                SELECT
                    score_priority as priority_tier,
                    COUNT(*) as count,
                    SUM(COALESCE(employees_site, ny990_employees, 0)) as employees
                FROM mergent_employers
                WHERE sector_category = %s AND has_union IS NOT TRUE
                GROUP BY score_priority
                ORDER BY
                    CASE score_priority
                        WHEN 'TOP' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END
            """, [sector_upper])
            by_tier = cur.fetchall()

            total = (targets['target_count'] or 0) + (unionized['unionized_count'] or 0)
            density = round(unionized['unionized_count'] / total * 100, 1) if total > 0 else 0

            return {
                "sector": sector_upper,
                "targets": targets,
                "unionized": unionized,
                "by_tier": by_tier,
                "union_density_pct": density
            }


@router.get("/api/sectors/{sector}/targets")
def search_sector_targets(
    sector: str,
    tier: Optional[str] = None,
    city: Optional[str] = None,
    min_employees: Optional[int] = None,
    max_employees: Optional[int] = None,
    min_score: Optional[int] = None,
    has_osha_violations: Optional[bool] = None,
    has_govt_contracts: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("total_score", pattern="^(total_score|employee_count|employer_name|total_contract_value)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search organizing targets in a specific sector"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"

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
                SELECT COUNT(*) FROM {view_name}
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            # Get results
            order_dir = "DESC" if sort_order == "desc" else "ASC"
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM {view_name}
                WHERE {where_clause}
                ORDER BY {sort_by} {order_dir} NULLS LAST, employer_name
                LIMIT %s OFFSET %s
            """, params)

            return {
                "sector": sector_key.upper(),
                "total": total,
                "limit": limit,
                "offset": offset,
                "targets": cur.fetchall()
            }


@router.get("/api/sectors/{sector}/targets/stats")
def get_sector_target_stats(sector: str):
    """Get summary statistics by tier for a sector"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_target_stats"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {view_name}")
            tiers = cur.fetchall()

            # Get overall totals
            targets_view = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"
            cur.execute(f"""
                SELECT
                    COUNT(*) as total_targets,
                    SUM(best_employee_count) as total_employees,
                    ROUND(AVG(total_score), 1) as avg_score,
                    COUNT(*) FILTER (WHERE osha_violation_count > 0) as with_violations,
                    COUNT(*) FILTER (WHERE total_contract_value > 0) as with_contracts
                FROM {targets_view}
            """)
            totals = cur.fetchone()

            return {
                "sector": sector_key.upper(),
                "by_tier": tiers,
                "totals": totals
            }


@router.get("/api/sectors/{sector}/targets/cities")
def get_sector_target_cities(sector: str):
    """Get list of cities with targets for dropdown"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT city, COUNT(*) as target_count, SUM(best_employee_count) as total_employees
                FROM {view_name}
                WHERE city IS NOT NULL
                GROUP BY city
                ORDER BY COUNT(*) DESC
            """)
            return {"cities": cur.fetchall()}


@router.get("/api/sectors/{sector}/targets/{target_id}")
def get_sector_target_detail(sector: str, target_id: int):
    """Get detailed information for a specific target"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    targets_view = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"
    unionized_view = f"v_{SECTOR_VIEWS[sector_key]}_unionized"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM {targets_view}
                WHERE id = %s
            """, [target_id])
            target = cur.fetchone()

            if not target:
                raise HTTPException(status_code=404, detail="Target not found")

            # Get nearby unionized in same sector
            cur.execute(f"""
                SELECT employer_name, city, employee_count, union_name, nlrb_election_date
                FROM {unionized_view}
                WHERE city = %s OR state = %s
                ORDER BY employee_count DESC NULLS LAST
                LIMIT 5
            """, [target['city'], target['state']])
            nearby_unionized = cur.fetchall()

            return {
                "target": target,
                "nearby_unionized": nearby_unionized
            }


@router.get("/api/sectors/{sector}/unionized")
def get_sector_unionized(
    sector: str,
    city: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get list of unionized employers in sector for reference"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_unionized"

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
                SELECT COUNT(*) FROM {view_name}
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM {view_name}
                WHERE {where_clause}
                ORDER BY employee_count DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)

            return {
                "sector": sector_key.upper(),
                "total": total,
                "unionized": cur.fetchall()
            }
