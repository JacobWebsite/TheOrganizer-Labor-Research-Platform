from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db

router = APIRouter()


@router.get("/api/projections/summary")
def get_projections_summary():
    """Get summary of industry projections: counts by growth category + top/bottom industries"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Count by growth category
            cur.execute("""
                SELECT growth_category, COUNT(*) as count,
                       AVG(employment_change_pct) as avg_change_pct,
                       SUM(employment_2024) as total_emp_2024
                FROM bls_industry_projections
                WHERE growth_category IS NOT NULL
                GROUP BY growth_category
                ORDER BY avg_change_pct DESC
            """)
            by_category = cur.fetchall()

            # Top 5 fastest growing
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE employment_change_pct IS NOT NULL
                ORDER BY employment_change_pct DESC
                LIMIT 5
            """)
            top_growing = cur.fetchall()

            # Top 5 fastest declining
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE employment_change_pct IS NOT NULL
                ORDER BY employment_change_pct ASC
                LIMIT 5
            """)
            top_declining = cur.fetchall()

            return {
                "by_category": by_category,
                "top_growing": top_growing,
                "top_declining": top_declining
            }


@router.get("/api/projections/industry/{naics_code}")
def get_industry_projections(naics_code: str):
    """Get employment projections for a NAICS 2-digit sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get NAICS sector info
            cur.execute("""
                SELECT naics_2digit, sector_name
                FROM naics_sectors
                WHERE naics_2digit = %s
            """, [naics_code])
            naics_info = cur.fetchone()

            # Construct BLS matrix_code from NAICS (e.g., "62" -> "620000")
            matrix_code = f"{naics_code}0000"

            # Get industry projection using constructed matrix_code
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            projection = cur.fetchone()

            if not projection:
                raise HTTPException(status_code=404, detail=f"No BLS projection found for NAICS {naics_code}")

            return {
                "naics_code": naics_code,
                "naics_sector_name": naics_info['sector_name'] if naics_info else None,
                "bls_matrix_code": matrix_code,
                "bls_industry_name": projection['industry_title'] if projection else None,
                "projection": projection
            }


@router.get("/api/projections/occupations/{naics_code}")
def get_occupation_projections_v2(naics_code: str, limit: int = Query(15, le=50)):
    """Get top occupations in a NAICS sector from bls_industry_occupation_matrix"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Construct BLS industry_code from NAICS (e.g., "62" -> "620000")
            industry_code = f"{naics_code}0000"

            # Get industry name from projections
            cur.execute("""
                SELECT industry_title FROM bls_industry_projections WHERE matrix_code = %s
            """, [industry_code])
            proj_info = cur.fetchone()

            # Get occupations for this industry
            cur.execute("""
                SELECT occupation_code, occupation_title, emp_2024, emp_change_pct
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
                ORDER BY emp_2024 DESC NULLS LAST
                LIMIT %s
            """, [industry_code, limit])
            occupations = cur.fetchall()

            if not occupations:
                raise HTTPException(status_code=404, detail=f"No occupation data found for NAICS {naics_code}")

            return {
                "naics_code": naics_code,
                "bls_industry_code": industry_code,
                "bls_industry_name": proj_info['industry_title'] if proj_info else None,
                "occupations": occupations
            }


@router.get("/api/projections/industries/{sector}")
def get_sector_sub_industries(sector: str, growth_category: str = None):
    """Get all sub-industries for a 2-digit NAICS sector with projections.

    Returns detailed breakdown of all industries within a sector (e.g., sector=23 returns
    238110 Poured Concrete, 238210 Electrical Contractors, etc.)

    Optional filter by growth_category: fast_growing, growing, stable, declining, fast_declining
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get sector name
            cur.execute("""
                SELECT sector_name FROM naics_sectors WHERE naics_2digit = %s
            """, [sector])
            sector_info = cur.fetchone()

            # Get all sub-industries for this sector
            query = """
                SELECT matrix_code, industry_title, industry_type,
                       employment_2024, employment_2034, employment_change,
                       employment_change_pct, growth_category, display_level
                FROM bls_industry_projections
                WHERE matrix_code LIKE %s
            """
            params = [f"{sector}%"]

            if growth_category:
                query += " AND growth_category = %s"
                params.append(growth_category)

            query += " ORDER BY matrix_code"

            cur.execute(query, params)
            industries = cur.fetchall()

            if not industries:
                raise HTTPException(status_code=404, detail=f"No industries found for sector {sector}")

            # Calculate sector summary
            total_2024 = sum(i['employment_2024'] or 0 for i in industries if i['matrix_code'].endswith('0000'))
            total_2034 = sum(i['employment_2034'] or 0 for i in industries if i['matrix_code'].endswith('0000'))

            return {
                "sector": sector,
                "sector_name": sector_info['sector_name'] if sector_info else None,
                "industry_count": len(industries),
                "summary": {
                    "total_employment_2024": total_2024,
                    "total_employment_2034": total_2034,
                    "total_change": total_2034 - total_2024 if total_2024 and total_2034 else None
                },
                "industries": industries
            }


@router.get("/api/projections/matrix/{matrix_code}")
def get_industry_by_matrix_code(matrix_code: str):
    """Get projection for a specific BLS industry matrix code (e.g., 238110, 621610).

    Use this for detailed sub-industry lookups. Matrix codes correspond to NAICS codes
    at various levels of detail (4-digit, 5-digit, 6-digit).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT matrix_code, industry_title, industry_type,
                       employment_2024, employment_2034, employment_change,
                       employment_change_pct, employment_cagr,
                       output_2024, output_2034, output_cagr,
                       growth_category, display_level
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            projection = cur.fetchone()

            if not projection:
                raise HTTPException(status_code=404, detail=f"No projection found for matrix code {matrix_code}")

            # Determine NAICS sector
            naics_2digit = matrix_code[:2]
            cur.execute("""
                SELECT sector_name FROM naics_sectors WHERE naics_2digit = %s
            """, [naics_2digit])
            sector_info = cur.fetchone()

            # Get occupation count for this industry
            cur.execute("""
                SELECT COUNT(*) as occ_count,
                       COUNT(*) FILTER (WHERE occupation_type = 'Line Item') as detailed_count
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
            """, [matrix_code])
            occ_counts = cur.fetchone()

            return {
                "matrix_code": matrix_code,
                "naics_sector": naics_2digit,
                "sector_name": sector_info['sector_name'] if sector_info else None,
                "projection": projection,
                "occupation_data_available": occ_counts['occ_count'] > 0,
                "occupation_count": occ_counts['occ_count'],
                "detailed_occupation_count": occ_counts['detailed_count']
            }


@router.get("/api/projections/matrix/{matrix_code}/occupations")
def get_occupations_by_matrix_code(
    matrix_code: str,
    occupation_type: str = Query(None, description="Filter by type: 'Line Item' for detailed, 'Summary' for groups"),
    min_employment: float = Query(None, description="Minimum 2024 employment (in thousands)"),
    sort_by: str = Query("employment", description="Sort by: employment, growth, change"),
    limit: int = Query(50, le=200)
):
    """Get occupation breakdown for a specific industry matrix code.

    Returns all occupations employed in the industry with 2024/2034 projections.
    Use occupation_type='Line Item' for specific job titles, 'Summary' for occupation groups.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get industry name
            cur.execute("""
                SELECT industry_title FROM bls_industry_projections WHERE matrix_code = %s
            """, [matrix_code])
            industry = cur.fetchone()

            # Build query
            query = """
                SELECT occupation_code, occupation_title, occupation_type,
                       emp_2024, emp_2024_pct_industry, emp_2024_pct_occupation,
                       emp_2034, emp_2034_pct_industry, emp_2034_pct_occupation,
                       emp_change, emp_change_pct, display_level
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
            """
            params = [matrix_code]

            if occupation_type:
                query += " AND occupation_type = %s"
                params.append(occupation_type)

            if min_employment is not None:
                query += " AND emp_2024 >= %s"
                params.append(min_employment)

            # Sort options
            if sort_by == "growth":
                query += " ORDER BY emp_change_pct DESC NULLS LAST"
            elif sort_by == "change":
                query += " ORDER BY emp_change DESC NULLS LAST"
            else:
                query += " ORDER BY emp_2024 DESC NULLS LAST"

            query += " LIMIT %s"
            params.append(limit)

            cur.execute(query, params)
            occupations = cur.fetchall()

            if not occupations:
                raise HTTPException(status_code=404, detail=f"No occupation data found for matrix code {matrix_code}")

            # Get summary stats
            cur.execute("""
                SELECT
                    SUM(emp_2024) FILTER (WHERE occupation_code = '00-0000') as total_2024,
                    SUM(emp_2034) FILTER (WHERE occupation_code = '00-0000') as total_2034,
                    COUNT(*) FILTER (WHERE occupation_type = 'Line Item') as detailed_count,
                    COUNT(*) FILTER (WHERE emp_change_pct > 0) as growing_count,
                    COUNT(*) FILTER (WHERE emp_change_pct < 0) as declining_count
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
            """, [matrix_code])
            stats = cur.fetchone()

            return {
                "matrix_code": matrix_code,
                "industry_title": industry['industry_title'] if industry else None,
                "summary": {
                    "total_employment_2024": stats['total_2024'],
                    "total_employment_2034": stats['total_2034'],
                    "detailed_occupations": stats['detailed_count'],
                    "growing_occupations": stats['growing_count'],
                    "declining_occupations": stats['declining_count']
                },
                "occupations": occupations
            }


@router.get("/api/projections/search")
def search_industry_projections(
    q: str = Query(None, description="Search industry titles"),
    growth_category: str = Query(None, description="Filter: fast_growing, growing, stable, declining, fast_declining"),
    min_employment: float = Query(None, description="Minimum 2024 employment (thousands)"),
    min_growth: float = Query(None, description="Minimum growth percentage"),
    max_growth: float = Query(None, description="Maximum growth percentage"),
    limit: int = Query(50, le=200)
):
    """Search and filter industry projections across all sectors."""
    with get_db() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT p.matrix_code, p.industry_title, p.industry_type,
                       p.employment_2024, p.employment_2034, p.employment_change,
                       p.employment_change_pct, p.growth_category,
                       ns.naics_2digit, ns.sector_name
                FROM bls_industry_projections p
                LEFT JOIN naics_sectors ns ON LEFT(p.matrix_code, 2) = ns.naics_2digit
                WHERE 1=1
            """
            params = []

            if q:
                query += " AND p.industry_title ILIKE %s"
                params.append(f"%{q}%")

            if growth_category:
                query += " AND p.growth_category = %s"
                params.append(growth_category)

            if min_employment is not None:
                query += " AND p.employment_2024 >= %s"
                params.append(min_employment)

            if min_growth is not None:
                query += " AND p.employment_change_pct >= %s"
                params.append(min_growth)

            if max_growth is not None:
                query += " AND p.employment_change_pct <= %s"
                params.append(max_growth)

            query += " ORDER BY p.employment_2024 DESC NULLS LAST LIMIT %s"
            params.append(limit)

            cur.execute(query, params)
            results = cur.fetchall()

            return {
                "query": q,
                "filters": {
                    "growth_category": growth_category,
                    "min_employment": min_employment,
                    "min_growth": min_growth,
                    "max_growth": max_growth
                },
                "count": len(results),
                "industries": results
            }


@router.get("/api/employer/{employer_id}/projections")
def get_employer_projections(employer_id: str):
    """Get industry outlook and top occupations for an employer based on their NAICS"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer info including enhanced NAICS
            cur.execute("""
                SELECT employer_id, employer_name, city, state, naics,
                       naics_detailed, naics_source, naics_confidence,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Use detailed NAICS if available, fall back to original
            naics_detailed = employer.get('naics_detailed')
            naics = employer.get('naics')
            naics_for_lookup = naics_detailed[:2] if naics_detailed else naics

            if not naics_for_lookup:
                return {
                    "employer": employer,
                    "error": "Employer has no NAICS code assigned",
                    "industry_outlook": None,
                    "top_occupations": None
                }

            # Get NAICS sector name
            cur.execute("""
                SELECT sector_name FROM naics_sectors WHERE naics_2digit = %s
            """, [naics_for_lookup])
            naics_info = cur.fetchone()

            # Construct BLS matrix_code from NAICS (e.g., "62" -> "620000")
            matrix_code = f"{naics_for_lookup}0000"

            industry_outlook = None
            top_occupations = []

            # Get industry projection
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            industry_outlook = cur.fetchone()

            # Get top 10 occupations
            cur.execute("""
                SELECT occupation_code, occupation_title, emp_2024, emp_change_pct
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
                ORDER BY emp_2024 DESC NULLS LAST
                LIMIT 10
            """, [matrix_code])
            top_occupations = cur.fetchall()

            return {
                "employer": employer,
                "naics_sector_name": naics_info['sector_name'] if naics_info else None,
                "naics_detailed": naics_detailed,
                "naics_source": employer.get('naics_source'),
                "naics_confidence": float(employer.get('naics_confidence')) if employer.get('naics_confidence') else None,
                "bls_matrix_code": matrix_code,
                "industry_outlook": industry_outlook,
                "top_occupations": top_occupations
            }


# Legacy endpoints for backwards compatibility
@router.get("/api/projections/naics/{naics_2digit}")
def get_naics_projections(naics_2digit: str, limit: int = Query(20, le=100)):
    """Get employment projections for a NAICS 2-digit sector (legacy)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Construct BLS matrix_code from NAICS (e.g., "62" -> "620000")
            matrix_code = f"{naics_2digit}0000"

            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct as employment_change, employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            projections = cur.fetchall()

            summary = None
            if projections:
                p = projections[0]
                summary = {
                    "total_2024": p.get('employment_2024'),
                    "total_2034": p.get('employment_2034'),
                    "avg_change_pct": p.get('employment_change_pct'),
                    "growth_category": p.get('growth_category')
                }

            return {"naics_2digit": naics_2digit, "summary": summary, "projections": projections}


@router.get("/api/projections/top")
def get_top_projections(growing: bool = Query(True), limit: int = Query(20, le=100)):
    """Get top growing or declining industries"""
    with get_db() as conn:
        with conn.cursor() as cur:
            order = "DESC" if growing else "ASC"
            condition = "> 0" if growing else "< 0"
            cur.execute(f"""
                SELECT bip.matrix_code, bip.industry_title,
                       bip.employment_2024, bip.employment_2034,
                       bip.employment_change_pct, bip.growth_category,
                       LEFT(bip.matrix_code, 2) as naics_2digit,
                       ns.sector_name
                FROM bls_industry_projections bip
                LEFT JOIN naics_sectors ns ON LEFT(bip.matrix_code, 2) = ns.naics_2digit
                WHERE bip.employment_change_pct {condition}
                ORDER BY bip.employment_change_pct {order}
                LIMIT %s
            """, [limit])
            return {"type": "growing" if growing else "declining", "projections": cur.fetchall()}
