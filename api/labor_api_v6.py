"""
Labor Relations Platform API v6.4 - Multi-Employer Deduplication
Run with: py -m uvicorn labor_api_v6:app --reload --port 8001
Features:
- OSHA-enriched 6-digit NAICS codes for 20,090 employers
- Multi-employer agreement deduplication (90% BLS coverage vs 203% raw)
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List
import re

app = FastAPI(
    title="Labor Relations Research API",
    version="6.2",
    description="Integrated platform: OLMS union data, F-7 employers, BLS density & projections, NLRB elections, OSHA safety"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

def get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


# Law firm detection patterns for NLRB data quality
LAW_FIRM_PATTERNS = [
    r'\bLLP\b', r'\bLLC\b.*LAW', r'\bATTORNEY',
    r'\bLAW\s+(FIRM|OFFICE|GROUP|OFFICES)', r'\bESQ\.?\b', r'\bCOUNSEL\b',
    r'\bLAW\s+&\s+', r'\b&\s+LAW\b', r'\bLAWYERS?\b', r'\bLEGAL\s+SERVICES'
]

def is_likely_law_firm(name: str) -> bool:
    """Detect if an employer name is likely a law firm (data quality issue in NLRB)"""
    if not name:
        return False
    for pattern in LAW_FIRM_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


# ============================================================================
# LOOKUP DATA - Dropdowns and filters
# ============================================================================

@app.get("/api/lookups/sectors")
def get_sectors():
    """Get all union sectors (Private, Federal, Public, RLA)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT us.sector_code, us.sector_name, us.governing_law, us.f7_expected,
                    COUNT(DISTINCT um.f_num) as union_count,
                    SUM(um.members) as total_members
                FROM union_sector us
                LEFT JOIN unions_master um ON us.sector_code = um.sector
                GROUP BY us.sector_code, us.sector_name, us.governing_law, us.f7_expected
                ORDER BY SUM(um.members) DESC NULLS LAST
            """)
            return {"sectors": cur.fetchall()}


@app.get("/api/lookups/affiliations")
def get_affiliations(sector: Optional[str] = None):
    """Get all national union affiliations with stats"""
    conditions = ["aff_abbr IS NOT NULL AND aff_abbr != ''"]
    params = []
    
    if sector and sector != 'ALL':
        conditions.append("sector = %s")
        params.append(sector.upper())
    
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT aff_abbr, MAX(union_name) as example_name,
                    COUNT(*) as local_count, SUM(members) as total_members,
                    SUM(f7_employer_count) as employer_count
                FROM unions_master
                WHERE {where_clause}
                GROUP BY aff_abbr
                HAVING COUNT(*) >= 3
                ORDER BY SUM(members) DESC NULLS LAST
            """, params)
            return {"affiliations": cur.fetchall()}


@app.get("/api/lookups/states")
def get_states():
    """Get all states with employer counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT state, COUNT(*) as employer_count, SUM(latest_unit_size) as total_workers
                FROM f7_employers_deduped
                WHERE state IS NOT NULL AND state != ''
                GROUP BY state ORDER BY COUNT(*) DESC
            """)
            return {"states": cur.fetchall()}


@app.get("/api/lookups/naics-sectors")
def get_naics_sectors():
    """Get all NAICS 2-digit sectors with union density"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ns.naics_2digit, ns.sector_name, 
                       vnd.union_density_pct, vnd.bls_indy_name
                FROM naics_sectors ns
                LEFT JOIN v_naics_union_density vnd ON ns.naics_2digit = vnd.naics_2digit
                ORDER BY ns.naics_2digit
            """)
            return {"sectors": cur.fetchall()}


@app.get("/api/lookups/metros")
def get_metros():
    """Get all metropolitan areas with employer counts and union density"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.cbsa_code, c.cbsa_title, c.cbsa_type,
                       COUNT(DISTINCT e.employer_id) as employer_count,
                       SUM(e.latest_unit_size) as total_workers,
                       m.pct_members as union_density
                FROM cbsa_definitions c
                LEFT JOIN f7_employers_deduped e ON e.cbsa_code = c.cbsa_code
                LEFT JOIN msa_union_stats m ON m.fips_code = c.cbsa_code AND m.sector = 'Total'
                WHERE c.cbsa_type = 'Metropolitan'
                GROUP BY c.cbsa_code, c.cbsa_title, c.cbsa_type, m.pct_members
                HAVING COUNT(DISTINCT e.employer_id) > 0
                ORDER BY COUNT(DISTINCT e.employer_id) DESC
            """)
            return {"metros": cur.fetchall()}


@app.get("/api/lookups/cities")
def get_cities_lookup(
    state: Optional[str] = None,
    cbsa: Optional[str] = None,
    limit: int = Query(200, le=500)
):
    """Get cities for a state or metro, ordered by employer count"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["city IS NOT NULL AND TRIM(city) != ''"]
            params = []

            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if cbsa:
                conditions.append("cbsa_code = %s")
                params.append(cbsa)

            where_clause = " AND ".join(conditions)
            params.append(limit)

            cur.execute(f"""
                SELECT UPPER(city) as city, COUNT(*) as employer_count
                FROM f7_employers_deduped
                WHERE {where_clause}
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, UPPER(city)
                LIMIT %s
            """, params)
            return {"cities": cur.fetchall()}


@app.get("/api/metros/{cbsa_code}/stats")
def get_metro_stats(cbsa_code: str):
    """Get detailed stats for a specific metro area"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Basic info
            cur.execute("""
                SELECT c.cbsa_code, c.cbsa_title, c.cbsa_type, c.csa_title,
                       COUNT(DISTINCT e.employer_id) as employer_count,
                       SUM(e.latest_unit_size) as total_workers,
                       COUNT(DISTINCT e.latest_union_fnum) as union_count
                FROM cbsa_definitions c
                LEFT JOIN f7_employers_deduped e ON e.cbsa_code = c.cbsa_code
                WHERE c.cbsa_code = %s
                GROUP BY c.cbsa_code, c.cbsa_title, c.cbsa_type, c.csa_title
            """, [cbsa_code])
            metro = cur.fetchone()
            if not metro:
                return {"error": "Metro not found"}
            
            # Union density by sector
            cur.execute("""
                SELECT sector, employment_thousands, members_thousands, 
                       pct_members, pct_covered
                FROM msa_union_stats WHERE fips_code = %s
            """, [cbsa_code])
            density = cur.fetchall()
            
            # Top unions in this metro
            cur.execute("""
                SELECT um.aff_abbr, um.union_name, COUNT(*) as employer_count,
                       SUM(e.latest_unit_size) as total_workers
                FROM f7_employers_deduped e
                JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.cbsa_code = %s AND um.aff_abbr IS NOT NULL
                GROUP BY um.aff_abbr, um.union_name
                ORDER BY SUM(e.latest_unit_size) DESC NULLS LAST
                LIMIT 10
            """, [cbsa_code])
            top_unions = cur.fetchall()
            
            # Counties in this metro
            cur.execute("""
                SELECT county_name, state_name, central_outlying
                FROM cbsa_counties WHERE cbsa_code = %s ORDER BY central_outlying, county_name
            """, [cbsa_code])
            counties = cur.fetchall()
            
            return {
                "metro": metro,
                "union_density": density,
                "top_unions": top_unions,
                "counties": counties
            }


# ============================================================================
# BLS UNION DENSITY BY INDUSTRY
# ============================================================================

@app.get("/api/density/naics/{naics_2digit}")
def get_naics_density(naics_2digit: str):
    """Get union density data for a NAICS 2-digit sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT naics_2digit, sector_name, bls_indy_code, bls_indy_name,
                       year, union_density_pct
                FROM v_naics_union_density WHERE naics_2digit = %s
            """, [naics_2digit])
            current = cur.fetchone()
            
            trend = []
            if current and current['bls_indy_code']:
                cur.execute("""
                    SELECT bud.year, bud.value as union_density_pct
                    FROM bls_union_series bus
                    JOIN bls_union_data bud ON bus.series_id = bud.series_id
                    WHERE bus.indy_code = %s AND bus.fips_code = '00' 
                      AND bus.pcts_code = '05' AND bus.unin_code = '1'
                    ORDER BY bud.year DESC LIMIT 15
                """, [current['bls_indy_code']])
                trend = cur.fetchall()
            
            return {"naics_2digit": naics_2digit, "current": current, "trend": trend}


@app.get("/api/density/all")
def get_all_density(year: Optional[int] = None):
    """Get union density for all NAICS sectors"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if year:
                cur.execute("""
                    SELECT bnm.naics_2digit, ns.sector_name, bnm.bls_indy_name,
                           bud.year, bud.value as union_density_pct
                    FROM bls_naics_mapping bnm
                    JOIN naics_sectors ns ON bnm.naics_2digit = ns.naics_2digit
                    JOIN bls_union_series bus ON bus.indy_code = bnm.bls_indy_code AND bus.fips_code = '00'
                    JOIN bls_union_data bud ON bus.series_id = bud.series_id
                    WHERE bud.year = %s ORDER BY bud.value DESC
                """, [year])
            else:
                cur.execute("SELECT * FROM v_naics_union_density ORDER BY union_density_pct DESC")
            return {"density": cur.fetchall()}


# ============================================================================
# BLS EMPLOYMENT PROJECTIONS (Enhanced with correct schema)
# ============================================================================

@app.get("/api/projections/summary")
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


@app.get("/api/projections/industry/{naics_code}")
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


@app.get("/api/projections/occupations/{naics_code}")
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


@app.get("/api/employer/{employer_id}/projections")
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
@app.get("/api/projections/naics/{naics_2digit}")
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


@app.get("/api/projections/top")
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


# ============================================================================
# EMPLOYER SEARCH
# ============================================================================

@app.get("/api/employers/cities")
def get_cities_for_state(
    state: str = Query(..., description="State code (e.g., CA, NY)"),
    limit: int = Query(200, le=500)
):
    """Get cities for a state, ordered by employer count"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT UPPER(city) as city, COUNT(*) as employer_count
                FROM f7_employers_deduped
                WHERE state = %s AND city IS NOT NULL AND TRIM(city) != ''
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, UPPER(city)
                LIMIT %s
            """, [state.upper(), limit])
            return {"state": state.upper(), "cities": cur.fetchall()}


@app.get("/api/employers/search")
def search_employers(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    naics: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    metro: Optional[str] = None,
    sector: Optional[str] = None,
    has_nlrb: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search employers with filters. Use sector=PUBLIC_SECTOR to search public sector employers."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Handle public sector search separately
            if sector and sector.upper() == 'PUBLIC_SECTOR':
                conditions = ["1=1"]
                params = []

                if name:
                    conditions.append("employer_name ILIKE %s")
                    params.append(f"%{name}%")
                if state:
                    conditions.append("state = %s")
                    params.append(state.upper())
                if city:
                    conditions.append("UPPER(city) = %s")
                    params.append(city.upper())

                where_clause = " AND ".join(conditions)

                # Count
                cur.execute(f"""
                    SELECT COUNT(*) FROM ps_employers WHERE {where_clause}
                """, params)
                total = cur.fetchone()['count']

                # Results
                params.extend([limit, offset])
                cur.execute(f"""
                    SELECT id as employer_id, employer_name, city, state,
                           total_employees as latest_unit_size,
                           employer_type, employer_type as employer_subtype,
                           NULL as naics, NULL as latest_union_fnum, NULL as latest_union_name,
                           NULL as latitude, NULL as longitude, NULL as aff_abbr,
                           NULL as cbsa_code, NULL as metro_name,
                           'PUBLIC' as source_type, 'PUBLIC_SECTOR' as union_sector
                    FROM ps_employers
                    WHERE {where_clause}
                    ORDER BY total_employees DESC NULLS LAST
                    LIMIT %s OFFSET %s
                """, params)

                return {"total": total, "employers": cur.fetchall()}

            # Standard F-7 employer search
            conditions = ["1=1"]
            params = []

            if name:
                conditions.append("e.employer_name ILIKE %s")
                params.append(f"%{name}%")
            if state:
                conditions.append("e.state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(e.city) = %s")
                params.append(city.upper())
            if naics:
                conditions.append("e.naics LIKE %s")
                params.append(f"{naics}%")
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            if metro:
                conditions.append("e.cbsa_code = %s")
                params.append(metro)

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"""
                SELECT COUNT(*) FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            # Results
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, e.city, e.state, e.naics,
                    e.latest_unit_size, e.latest_union_fnum, e.latest_union_name,
                    e.latitude, e.longitude, um.aff_abbr,
                    e.cbsa_code, c.cbsa_title as metro_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                LEFT JOIN cbsa_definitions c ON e.cbsa_code = c.cbsa_code
                WHERE {where_clause}
                ORDER BY e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/employers/fuzzy-search")
def fuzzy_search_employers(
    name: str = Query(..., description="Employer name to search (typo-tolerant)"),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    state: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Fuzzy search using pg_trgm similarity - catches typos and variations"""
    with get_db() as conn:
        with conn.cursor() as cur:
            state_filter = "AND e.state = %s" if state else ""
            count_params = [name, threshold]
            if state:
                count_params.append(state.upper())
            
            cur.execute(f"""
                SELECT COUNT(*) as total FROM f7_employers_deduped e
                WHERE similarity(e.employer_name, %s) > %s {state_filter}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [name, name, threshold]
            if state:
                select_params.append(state.upper())
            select_params.extend([name, limit, offset])
            
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, similarity(e.employer_name, %s) as match_score,
                       e.city, e.state, e.naics, e.latest_unit_size, e.latitude, e.longitude,
                       um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE similarity(e.employer_name, %s) > %s {state_filter}
                ORDER BY similarity(e.employer_name, %s) DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)
            
            return {"search_term": name, "threshold": threshold, "total": total, "employers": cur.fetchall()}


@app.get("/api/employers/normalized-search")
def normalized_search_employers(
    name: str = Query(..., description="Employer name"),
    threshold: float = Query(0.35, ge=0.1, le=1.0),
    state: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search with normalized names - strips Inc, LLC, Corp, etc."""
    import re
    normalized_search = re.sub(r'\b(inc|llc|corp|corporation|company|co|ltd|limited|the)\b', '', 
                               name.lower(), flags=re.IGNORECASE).strip()
    normalized_search = re.sub(r'[^\w\s]', '', normalized_search)
    normalized_search = ' '.join(normalized_search.split())
    
    with get_db() as conn:
        with conn.cursor() as cur:
            state_filter = "AND e.state = %s" if state else ""
            
            count_params = [normalized_search, threshold]
            if state:
                count_params.append(state.upper())
            
            cur.execute(f"""
                WITH normalized AS (
                    SELECT *, regexp_replace(
                        regexp_replace(lower(employer_name), 
                            '\\m(inc|llc|corp|corporation|company|co|ltd|limited|the)\\M', '', 'gi'),
                        '[^a-z0-9\\s]', '', 'gi') as normalized_name
                    FROM f7_employers_deduped
                )
                SELECT COUNT(*) as total FROM normalized
                WHERE similarity(normalized_name, %s) > %s {state_filter}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [normalized_search, normalized_search, threshold]
            if state:
                select_params.append(state.upper())
            select_params.extend([normalized_search, limit, offset])
            
            cur.execute(f"""
                WITH normalized AS (
                    SELECT *, regexp_replace(
                        regexp_replace(lower(employer_name), 
                            '\\m(inc|llc|corp|corporation|company|co|ltd|limited|the)\\M', '', 'gi'),
                        '[^a-z0-9\\s]', '', 'gi') as normalized_name
                    FROM f7_employers_deduped
                )
                SELECT employer_id, employer_name, normalized_name,
                       similarity(normalized_name, %s) as match_score,
                       city, state, naics, latest_unit_size, latest_union_fnum, latitude, longitude,
                       um.aff_abbr
                FROM normalized n
                LEFT JOIN unions_master um ON n.latest_union_fnum::text = um.f_num
                WHERE similarity(n.normalized_name, %s) > %s {state_filter}
                ORDER BY similarity(n.normalized_name, %s) DESC, n.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)
            
            return {"search_term": name, "normalized_search": normalized_search, 
                    "threshold": threshold, "total": total, "employers": cur.fetchall()}


@app.get("/api/employers/{employer_id}")
def get_employer_detail(employer_id: str):
    """Get full employer details including NLRB history"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Basic info
            cur.execute("""
                SELECT e.*, um.aff_abbr, um.union_name as union_full_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()
            
            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")
            
            # NLRB elections
            cur.execute("""
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                    e.vote_margin, t.labor_org_name as union_name, um.aff_abbr
                FROM nlrb_elections e
                JOIN nlrb_participants p ON e.case_number = p.case_number 
                    AND p.participant_type = 'Employer'
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE p.matched_employer_id = %s
                ORDER BY e.election_date DESC
            """, [employer_id])
            elections = cur.fetchall()
            
            # ULP cases
            cur.execute("""
                SELECT c.case_number, c.case_type, c.earliest_date, ct.description
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                JOIN nlrb_participants p ON c.case_number = p.case_number 
                    AND p.participant_type = 'Charged Party'
                WHERE p.matched_employer_id = %s AND ct.case_category = 'unfair_labor_practice'
                ORDER BY c.earliest_date DESC LIMIT 20
            """, [employer_id])
            ulp_cases = cur.fetchall()
            
            return {
                "employer": employer,
                "nlrb_elections": elections,
                "nlrb_summary": {
                    "total_elections": len(elections),
                    "union_wins": sum(1 for e in elections if e['union_won']),
                    "ulp_cases": len(ulp_cases)
                },
                "ulp_cases": ulp_cases
            }


@app.get("/api/employers/{employer_id}/similar")
def get_similar_employers(
    employer_id: str,
    limit: int = Query(10, le=50)
):
    """Get employers similar to this one (same NAICS, state, or union)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get the employer's info first
            cur.execute("""
                SELECT employer_name, state, naics, latest_union_fnum, cbsa_code
                FROM f7_employers_deduped WHERE employer_id = %s
            """, [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Find similar employers
            cur.execute("""
                SELECT e.employer_id, e.employer_name, e.city, e.state, e.naics,
                       e.latest_unit_size, e.latest_unit_size as employee_count,
                       e.latest_union_name, um.aff_abbr,
                       CASE
                           WHEN e.naics = %s AND e.state = %s THEN 3
                           WHEN e.naics = %s THEN 2
                           WHEN e.state = %s THEN 1
                           ELSE 0
                       END as similarity_score
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.employer_id != %s
                  AND (e.naics = %s OR e.state = %s OR e.latest_union_fnum = %s)
                ORDER BY similarity_score DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s
            """, [emp['naics'], emp['state'], emp['naics'], emp['state'],
                  employer_id, emp['naics'], emp['state'], emp['latest_union_fnum'], limit])

            return {"similar_employers": cur.fetchall()}


@app.get("/api/employers/{employer_id}/osha")
def get_employer_osha(employer_id: str):
    """Get OSHA violations and safety data for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check employer exists
            cur.execute("SELECT employer_name FROM f7_employers_deduped WHERE employer_id = %s", [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get OSHA matches via osha_f7_matches with violation summaries
            cur.execute("""
                SELECT o.establishment_id, o.estab_name, o.site_address, o.site_city,
                       o.site_state, o.site_zip, o.naics_code, o.sic_code,
                       o.employee_count, o.total_inspections, o.last_inspection_date,
                       m.match_method, m.match_confidence,
                       COALESCE(vs.willful_count, 0) as willful_count,
                       COALESCE(vs.repeat_count, 0) as repeat_count,
                       COALESCE(vs.serious_count, 0) as serious_count,
                       COALESCE(vs.other_count, 0) as other_count,
                       COALESCE(vs.total_violations, 0) as total_violations,
                       COALESCE(vs.total_penalties, 0) as total_penalties
                FROM osha_f7_matches m
                JOIN osha_establishments o ON m.establishment_id = o.establishment_id
                LEFT JOIN (
                    SELECT establishment_id,
                           SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) as willful_count,
                           SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) as repeat_count,
                           SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) as serious_count,
                           SUM(CASE WHEN violation_type = 'O' THEN violation_count ELSE 0 END) as other_count,
                           SUM(violation_count) as total_violations,
                           SUM(total_penalties) as total_penalties
                    FROM osha_violation_summary
                    GROUP BY establishment_id
                ) vs ON o.establishment_id = vs.establishment_id
                WHERE m.f7_employer_id = %s
                ORDER BY vs.total_penalties DESC NULLS LAST
            """, [employer_id])
            establishments = cur.fetchall()

            # Calculate summary stats
            summary = {
                "total_establishments": len(establishments),
                "total_inspections": sum(e['total_inspections'] or 0 for e in establishments),
                "total_violations": sum(e['total_violations'] or 0 for e in establishments),
                "total_penalties": sum(float(e['total_penalties'] or 0) for e in establishments),
                "willful_violations": sum(e['willful_count'] or 0 for e in establishments),
                "serious_violations": sum(e['serious_count'] or 0 for e in establishments)
            }

            return {
                "employer_name": emp['employer_name'],
                "osha_summary": summary,
                "establishments": establishments
            }


@app.get("/api/employers/{employer_id}/nlrb")
def get_employer_nlrb(employer_id: str):
    """Get NLRB elections and ULP cases for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check employer exists
            cur.execute("SELECT employer_name FROM f7_employers_deduped WHERE employer_id = %s", [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # NLRB elections
            cur.execute("""
                SELECT e.case_number, e.election_date, e.election_type, e.union_won,
                       e.eligible_voters, e.vote_margin, t.labor_org_name as union_name, um.aff_abbr
                FROM nlrb_elections e
                JOIN nlrb_participants p ON e.case_number = p.case_number
                    AND p.participant_type = 'Employer'
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE p.matched_employer_id = %s
                ORDER BY e.election_date DESC
            """, [employer_id])
            elections = cur.fetchall()

            # ULP cases
            cur.execute("""
                SELECT c.case_number, c.case_type, c.earliest_date, c.latest_date,
                       ct.description as case_type_desc
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                JOIN nlrb_participants p ON c.case_number = p.case_number
                    AND p.participant_type = 'Charged Party'
                WHERE p.matched_employer_id = %s AND ct.case_category = 'unfair_labor_practice'
                ORDER BY c.earliest_date DESC LIMIT 50
            """, [employer_id])
            ulp_cases = cur.fetchall()

            return {
                "employer_name": emp['employer_name'],
                "elections": elections,
                "elections_summary": {
                    "total": len(elections),
                    "union_wins": sum(1 for e in elections if e['union_won']),
                    "union_losses": sum(1 for e in elections if e['union_won'] is False),
                    "win_rate": round(100.0 * sum(1 for e in elections if e['union_won']) / max(len(elections), 1), 1)
                },
                "ulp_cases": ulp_cases,
                "ulp_summary": {
                    "total": len(ulp_cases)
                }
            }


# ============================================================================
# HISTORICAL TRENDS
# ============================================================================

@app.get("/api/trends/national")
def get_national_trends():
    """Get national union membership trends by year (2010-2024) with deduplicated estimates"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get raw trends by year
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members_raw,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """)
            raw_trends = cur.fetchall()

            # Get current deduplicated total and ratio from view
            cur.execute("""
                SELECT
                    SUM(CASE WHEN count_members THEN members ELSE 0 END) as deduplicated_total,
                    SUM(members) as raw_total
                FROM v_union_members_deduplicated
            """)
            dedup_stats = cur.fetchone()

            # Calculate deduplication ratio (typically ~0.20-0.21)
            dedup_ratio = 0.20  # fallback
            if dedup_stats and dedup_stats['raw_total'] and dedup_stats['raw_total'] > 0:
                dedup_ratio = dedup_stats['deduplicated_total'] / dedup_stats['raw_total']

            # Apply ratio to get estimated deduplicated membership by year
            trends = []
            for row in raw_trends:
                trend = dict(row)
                # Estimate deduplicated members using the ratio
                trend['total_members_dedup'] = int(row['total_members_raw'] * dedup_ratio)
                trends.append(trend)

            return {
                "description": "National union membership trends",
                "note": "total_members_dedup is estimated using current deduplication ratio. BLS benchmark is ~14-15M",
                "dedup_ratio": round(dedup_ratio, 4),
                "current_dedup_total": dedup_stats['deduplicated_total'] if dedup_stats else None,
                "trends": trends
            }


@app.get("/api/trends/affiliations/summary")
def get_affiliation_trends_summary():
    """Get membership trends summary for top affiliations"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH yearly AS (
                    SELECT aff_abbr,
                           yr_covered,
                           SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as members
                    FROM lm_data
                    WHERE aff_abbr IS NOT NULL AND yr_covered IN (2010, 2024)
                    GROUP BY aff_abbr, yr_covered
                ),
                pivoted AS (
                    SELECT aff_abbr,
                           MAX(CASE WHEN yr_covered = 2010 THEN members END) as members_2010,
                           MAX(CASE WHEN yr_covered = 2024 THEN members END) as members_2024
                    FROM yearly
                    GROUP BY aff_abbr
                )
                SELECT aff_abbr,
                       members_2010,
                       members_2024,
                       members_2024 - members_2010 as change,
                       ROUND(100.0 * (members_2024 - members_2010) / NULLIF(members_2010, 0), 1) as pct_change
                FROM pivoted
                WHERE members_2024 > 10000
                ORDER BY members_2024 DESC
                LIMIT 30
            """)
            return {"affiliations": cur.fetchall()}


@app.get("/api/trends/by-affiliation/{aff_abbr}")
def get_affiliation_trends(aff_abbr: str):
    """Get membership trends for a specific affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE aff_abbr = %s AND yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """, [aff_abbr.upper()])
            trends = cur.fetchall()
            
            return {
                "affiliation": aff_abbr.upper(),
                "trends": trends
            }


@app.get("/api/trends/states/summary")
def get_state_trends_summary():
    """Get membership summary by state for latest year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH state_data AS (
                    SELECT state,
                           yr_covered,
                           SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as members,
                           COUNT(DISTINCT f_num) as union_count
                    FROM lm_data
                    WHERE state IS NOT NULL AND yr_covered IN (2010, 2024)
                    GROUP BY state, yr_covered
                ),
                pivoted AS (
                    SELECT state,
                           MAX(CASE WHEN yr_covered = 2010 THEN members END) as members_2010,
                           MAX(CASE WHEN yr_covered = 2024 THEN members END) as members_2024,
                           MAX(CASE WHEN yr_covered = 2024 THEN union_count END) as unions_2024
                    FROM state_data
                    GROUP BY state
                )
                SELECT state,
                       members_2010,
                       members_2024,
                       unions_2024,
                       ROUND(100.0 * (members_2024 - members_2010) / NULLIF(members_2010, 0), 1) as pct_change
                FROM pivoted
                WHERE members_2024 > 0
                ORDER BY members_2024 DESC
            """)
            return {"states": cur.fetchall()}


@app.get("/api/trends/by-state/{state}")
def get_state_trends(state: str):
    """Get membership trends for a specific state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE state = %s AND yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """, [state.upper()])
            trends = cur.fetchall()
            
            return {
                "state": state.upper(),
                "trends": trends
            }


@app.get("/api/trends/elections")
def get_election_trends():
    """Get NLRB election trends by year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(YEAR FROM election_date)::int as year,
                       COUNT(*) as total_elections,
                       SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
                       SUM(CASE WHEN union_won = false THEN 1 ELSE 0 END) as union_losses,
                       SUM(eligible_voters) as total_voters,
                       ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / 
                           NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections
                WHERE election_date IS NOT NULL 
                  AND union_won IS NOT NULL
                  AND EXTRACT(YEAR FROM election_date) BETWEEN 2007 AND 2024
                GROUP BY EXTRACT(YEAR FROM election_date)
                ORDER BY year
            """)
            return {"election_trends": cur.fetchall()}


@app.get("/api/trends/elections/by-affiliation/{aff_abbr}")
def get_election_trends_by_affiliation(aff_abbr: str):
    """Get NLRB election trends for a specific union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(YEAR FROM e.election_date)::int as year,
                       COUNT(DISTINCT e.case_number) as total_elections,
                       SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
                       ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
                           NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections e
                JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE um.aff_abbr = %s
                  AND e.election_date IS NOT NULL 
                  AND e.union_won IS NOT NULL
                  AND EXTRACT(YEAR FROM e.election_date) BETWEEN 2007 AND 2024
                GROUP BY EXTRACT(YEAR FROM e.election_date)
                ORDER BY year
            """, [aff_abbr.upper()])
            
            return {
                "affiliation": aff_abbr.upper(),
                "election_trends": cur.fetchall()
            }


@app.get("/api/trends/sectors")
def get_sector_trends():
    """Get employer distribution by NAICS sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT LEFT(e.naics, 2) as naics_2digit,
                       ns.sector_name,
                       COUNT(*) as employer_count,
                       SUM(e.latest_unit_size) as total_workers,
                       ROUND(AVG(e.latest_unit_size), 0) as avg_unit_size
                FROM f7_employers_deduped e
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE e.naics IS NOT NULL AND LENGTH(e.naics) >= 2
                GROUP BY LEFT(e.naics, 2), ns.sector_name
                ORDER BY COUNT(*) DESC
            """)
            return {"sectors": cur.fetchall()}


# ============================================================================
# UNION SEARCH
# ============================================================================

@app.get("/api/unions/cities")
def get_union_cities(
    state: str = Query(..., description="State code (e.g., CA, NY)"),
    limit: int = Query(200, le=500)
):
    """Get cities for a state from unions_master, ordered by union count"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT UPPER(city) as city, COUNT(*) as union_count, SUM(members) as total_members
                FROM unions_master
                WHERE state = %s AND city IS NOT NULL AND TRIM(city) != ''
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, SUM(members) DESC
                LIMIT %s
            """, [state.upper(), limit])
            return {"state": state.upper(), "cities": cur.fetchall()}


@app.get("/api/unions/search")
def search_unions(
    name: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    union_type: Optional[str] = None,
    min_members: Optional[int] = None,
    has_employers: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search unions with filters including display names and hierarchy type"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if name:
                # Search union_name, local_number, and display_name
                conditions.append("""(
                    um.union_name ILIKE %s 
                    OR um.local_number = %s 
                    OR v.display_name ILIKE %s
                )""")
                clean_name = name.replace('local ', '').replace('Local ', '').strip()
                params.extend([f"%{name}%", clean_name, f"%{name}%"])
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            if sector:
                conditions.append("um.sector = %s")
                params.append(sector.upper())
            if state:
                conditions.append("um.state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(um.city) = %s")
                params.append(city.upper())
            if union_type:
                conditions.append("TRIM(um.desig_name) = %s")
                params.append(union_type.upper())
            if min_members:
                conditions.append("um.members >= %s")
                params.append(min_members)
            if has_employers:
                conditions.append("um.has_f7_employers = true")
            
            where_clause = " AND ".join(conditions)
            
            # Count query
            cur.execute(f"""
                SELECT COUNT(*) FROM unions_master um
                LEFT JOIN v_union_display_names v ON um.f_num = v.f_num
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT um.f_num, um.union_name, v.display_name, um.local_number,
                    um.aff_abbr, um.desig_name, um.members, um.city, um.state, 
                    um.sector, um.f7_employer_count, um.f7_total_workers, um.has_f7_employers,
                    lm.ttl_assets, lm.ttl_receipts
                FROM unions_master um
                LEFT JOIN v_union_display_names v ON um.f_num = v.f_num
                LEFT JOIN lm_data lm ON um.f_num = lm.f_num AND lm.yr_covered = 2024
                WHERE {where_clause}
                ORDER BY um.members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "unions": cur.fetchall()}


@app.get("/api/unions/types")
def get_union_types():
    """Get list of union designation types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TRIM(desig_name) as type_code,
                    CASE TRIM(desig_name)
                        WHEN 'LU' THEN 'Local Union'
                        WHEN 'NHQ' THEN 'National Headquarters'
                        WHEN 'C' THEN 'Council'
                        WHEN 'JC' THEN 'Joint Council'
                        WHEN 'DC' THEN 'District Council'
                        WHEN 'SC' THEN 'State Council'
                        WHEN 'D' THEN 'District'
                        WHEN 'BR' THEN 'Branch'
                        WHEN 'LG' THEN 'Lodge'
                        WHEN 'DIV' THEN 'Division'
                        WHEN 'CH' THEN 'Chapter'
                        WHEN 'CONF' THEN 'Conference'
                        WHEN 'FED' THEN 'Federation'
                        WHEN 'SLG' THEN 'Sub-Lodge'
                        WHEN 'LLG' THEN 'Local Lodge'
                        WHEN 'SA' THEN 'System Assembly'
                        WHEN 'BCTC' THEN 'Building & Construction Trades Council'
                        WHEN 'LEC' THEN 'Local Executive Council'
                        ELSE TRIM(desig_name)
                    END as type_name,
                    SUM(cnt) as count
                FROM (
                    SELECT TRIM(desig_name) as desig_name, COUNT(*) as cnt
                    FROM unions_master
                    WHERE desig_name IS NOT NULL AND TRIM(desig_name) != ''
                    GROUP BY desig_name
                ) sub
                GROUP BY TRIM(desig_name)
                HAVING SUM(cnt) >= 10
                ORDER BY SUM(cnt) DESC
            """)
            return {"types": cur.fetchall()}


@app.get("/api/unions/cities")
def get_union_cities(
    state: str = Query(..., description="State code (e.g., CA, NY)"),
    limit: int = Query(200, le=500)
):
    """Get cities for a state with union counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT UPPER(city) as city, COUNT(*) as union_count
                FROM unions_master
                WHERE state = %s AND city IS NOT NULL AND TRIM(city) != ''
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, UPPER(city)
                LIMIT %s
            """, [state.upper(), limit])
            return {"state": state.upper(), "cities": cur.fetchall()}


@app.get("/api/unions/national")
def get_national_unions(
    limit: int = Query(50, le=200)
):
    """Get national/international unions aggregated by affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT aff_abbr,
                       MAX(union_name) as example_name,
                       COUNT(*) as local_count,
                       SUM(members) as total_members,
                       SUM(f7_employer_count) as employer_count,
                       SUM(f7_total_workers) as covered_workers,
                       COUNT(DISTINCT state) as state_count
                FROM unions_master
                WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
                GROUP BY aff_abbr
                HAVING SUM(members) > 0
                ORDER BY SUM(members) DESC NULLS LAST
                LIMIT %s
            """, [limit])
            return {"national_unions": cur.fetchall()}


@app.get("/api/unions/national/{aff_abbr}")
def get_national_union_detail(aff_abbr: str):
    """Get detailed info for a national union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Summary stats
            cur.execute("""
                SELECT aff_abbr,
                       COUNT(*) as local_count,
                       SUM(members) as total_members,
                       SUM(f7_employer_count) as employer_count,
                       SUM(f7_total_workers) as covered_workers,
                       COUNT(DISTINCT state) as state_count
                FROM unions_master
                WHERE aff_abbr = %s
                GROUP BY aff_abbr
            """, [aff_abbr.upper()])
            summary = cur.fetchone()

            if not summary:
                raise HTTPException(status_code=404, detail="Affiliation not found")

            # Top locals by membership
            cur.execute("""
                SELECT f_num, union_name, local_number, city, state, members,
                       f7_employer_count, f7_total_workers
                FROM unions_master
                WHERE aff_abbr = %s
                ORDER BY members DESC NULLS LAST
                LIMIT 20
            """, [aff_abbr.upper()])
            top_locals = cur.fetchall()

            # State breakdown
            cur.execute("""
                SELECT state, COUNT(*) as local_count, SUM(members) as total_members
                FROM unions_master
                WHERE aff_abbr = %s AND state IS NOT NULL
                GROUP BY state
                ORDER BY SUM(members) DESC NULLS LAST
            """, [aff_abbr.upper()])
            by_state = cur.fetchall()

            # Recent NLRB activity
            cur.execute("""
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                       p.participant_name as employer_name, p.state
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number
                    AND p.participant_type = 'Employer'
                WHERE um.aff_abbr = %s
                ORDER BY e.election_date DESC
                LIMIT 20
            """, [aff_abbr.upper()])
            recent_elections = cur.fetchall()

            return {
                "summary": summary,
                "top_locals": top_locals,
                "by_state": by_state,
                "recent_elections": recent_elections
            }


@app.get("/api/unions/{f_num}")
def get_union_detail(f_num: str):
    """Get full union details including NLRB history"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM unions_master WHERE f_num = %s", [f_num])
            union = cur.fetchone()
            
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")
            
            # F-7 employers
            cur.execute("""
                SELECT employer_id, employer_name, city, state, latest_unit_size
                FROM f7_employers_deduped
                WHERE latest_union_fnum = %s
                ORDER BY latest_unit_size DESC NULLS LAST LIMIT 20
            """, [f_num])
            employers = cur.fetchall()
            
            # NLRB elections
            cur.execute("""
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                    e.vote_margin, p.participant_name as employer_name, p.state
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number 
                    AND p.participant_type = 'Employer'
                WHERE t.matched_olms_fnum = %s
                ORDER BY e.election_date DESC
            """, [f_num])
            elections = cur.fetchall()
            
            return {
                "union": union,
                "top_employers": employers,
                "nlrb_elections": elections,
                "nlrb_summary": {
                    "total_elections": len(elections),
                    "wins": sum(1 for e in elections if e['union_won']),
                    "losses": sum(1 for e in elections if e['union_won'] is False),
                    "win_rate": round(100.0 * sum(1 for e in elections if e['union_won']) / max(len(elections), 1), 1)
                }
            }


@app.get("/api/unions/{f_num}/employers")
def get_union_employers(
    f_num: str,
    limit: int = Query(50, le=200)
):
    """Get all employers for a specific union"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check union exists
            cur.execute("SELECT union_name, aff_abbr FROM unions_master WHERE f_num = %s", [f_num])
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            # Get employers
            cur.execute("""
                SELECT e.employer_id, e.employer_name, e.city, e.state, e.naics,
                       e.latest_unit_size, e.latest_notice_date,
                       c.cbsa_title as metro_name
                FROM f7_employers_deduped e
                LEFT JOIN cbsa_definitions c ON e.cbsa_code = c.cbsa_code
                WHERE e.latest_union_fnum = %s
                ORDER BY e.latest_unit_size DESC NULLS LAST
                LIMIT %s
            """, [f_num, limit])
            employers = cur.fetchall()

            return {
                "union_name": union['union_name'],
                "aff_abbr": union['aff_abbr'],
                "total_employers": len(employers),
                "employers": employers
            }


@app.get("/api/unions/locals/{affiliation}")
def get_locals_for_affiliation(
    affiliation: str,
    state: Optional[str] = None,
    limit: int = Query(100, le=500)
):
    """Get local unions for a national affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["aff_abbr = %s"]
            params = [affiliation.upper()]
            
            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            cur.execute(f"""
                SELECT f_num, union_name, display_name, local_number, city, state, members, f7_employer_count
                FROM v_union_display_names
                WHERE {where_clause}
                ORDER BY members DESC NULLS LAST
                LIMIT %s
            """, params)
            
            return {"affiliation": affiliation, "locals": cur.fetchall()}


# ============================================================================
# NLRB - Elections
# ============================================================================

@app.get("/api/nlrb/summary")
def get_nlrb_summary():
    """Get overall NLRB statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as total_elections,
                    SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
                    SUM(CASE WHEN union_won = false THEN 1 ELSE 0 END) as union_losses,
                    SUM(eligible_voters) as total_eligible_voters,
                    ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / 
                        NULLIF(COUNT(*), 0), 1) as win_rate_pct
                FROM nlrb_elections WHERE union_won IS NOT NULL
            """)
            elections = cur.fetchone()
            
            cur.execute("""
                SELECT um.aff_abbr, um.union_name,
                    COUNT(DISTINCT t.case_number) as elections,
                    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as wins,
                    ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
                        NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE t.tally_type = 'For' AND t.matched_olms_fnum IS NOT NULL
                GROUP BY um.aff_abbr, um.union_name
                HAVING COUNT(*) >= 50
                ORDER BY COUNT(*) DESC LIMIT 15
            """)
            top_unions = cur.fetchall()
            
            return {"elections": elections, "top_unions": top_unions}


@app.get("/api/nlrb/elections/search")
def search_nlrb_elections(
    state: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    employer_name: Optional[str] = None,
    union_won: Optional[bool] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    min_voters: Optional[int] = None,
    limit: int = Query(100, le=500),
    offset: int = 0
):
    """Search NLRB elections with filters"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if state:
                conditions.append("p.state = %s")
                params.append(state.upper())
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            if employer_name:
                conditions.append("p.participant_name ILIKE %s")
                params.append(f"%{employer_name}%")
            if union_won is not None:
                conditions.append("e.union_won = %s")
                params.append(union_won)
            if year_from:
                conditions.append("EXTRACT(YEAR FROM e.election_date) >= %s")
                params.append(year_from)
            if year_to:
                conditions.append("EXTRACT(YEAR FROM e.election_date) <= %s")
                params.append(year_to)
            if min_voters:
                conditions.append("e.eligible_voters >= %s")
                params.append(min_voters)
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(DISTINCT e.case_number)
                FROM nlrb_elections e
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number 
                    AND p.participant_type = 'Employer'
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT DISTINCT ON (e.case_number)
                    e.case_number, e.election_date, e.election_type, e.eligible_voters,
                    e.union_won, e.vote_margin, p.participant_name as employer_name,
                    p.city as employer_city, p.state as employer_state, p.matched_employer_id,
                    t.labor_org_name as union_name, um.aff_abbr, f7.latitude, f7.longitude
                FROM nlrb_elections e
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number 
                    AND p.participant_type = 'Employer'
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                LEFT JOIN f7_employers_deduped f7 ON p.matched_employer_id = f7.employer_id
                WHERE {where_clause}
                ORDER BY e.case_number, e.election_date DESC
                LIMIT %s OFFSET %s
            """, params)

            elections = cur.fetchall()
            # Add law firm detection flag to each election
            for election in elections:
                election['is_law_firm'] = is_likely_law_firm(election.get('employer_name'))

            return {"total": total, "limit": limit, "offset": offset, "elections": elections}


@app.get("/api/nlrb/elections/map")
def get_nlrb_elections_map(
    state: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    year_from: Optional[int] = None,
    union_won: Optional[bool] = None,
    limit: int = Query(1000, le=5000)
):
    """Get election data for map visualization"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["f7.latitude IS NOT NULL", "f7.longitude IS NOT NULL"]
            params = []
            
            if state:
                conditions.append("p.state = %s")
                params.append(state.upper())
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            if year_from:
                conditions.append("EXTRACT(YEAR FROM e.election_date) >= %s")
                params.append(year_from)
            if union_won is not None:
                conditions.append("e.union_won = %s")
                params.append(union_won)
            
            where_clause = " AND ".join(conditions)
            params.append(limit)
            
            cur.execute(f"""
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                    p.participant_name as employer_name, p.city, p.state,
                    t.labor_org_name as union_name, um.aff_abbr,
                    f7.latitude, f7.longitude
                FROM nlrb_elections e
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number 
                    AND p.participant_type = 'Employer'
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                LEFT JOIN f7_employers_deduped f7 ON p.matched_employer_id = f7.employer_id
                WHERE {where_clause}
                ORDER BY e.election_date DESC LIMIT %s
            """, params)
            
            return {"elections": cur.fetchall()}


@app.get("/api/nlrb/elections/by-year")
def get_nlrb_elections_by_year(aff_abbr: Optional[str] = None):
    """Get election statistics by year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["e.election_date IS NOT NULL"]
            params = []
            
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT EXTRACT(YEAR FROM e.election_date)::int as year,
                    COUNT(*) as total_elections,
                    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
                    SUM(CASE WHEN e.union_won = false THEN 1 ELSE 0 END) as union_losses,
                    ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
                        NULLIF(COUNT(*), 0), 1) as win_rate,
                    SUM(e.eligible_voters) as total_voters
                FROM nlrb_elections e
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE {where_clause}
                GROUP BY EXTRACT(YEAR FROM e.election_date)
                ORDER BY 1 DESC
            """, params)
            
            return {"yearly_stats": cur.fetchall()}


@app.get("/api/nlrb/elections/by-state")
def get_nlrb_elections_by_state(year: Optional[int] = None):
    """Get election statistics by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["p.state IS NOT NULL", "LENGTH(p.state) = 2"]
            params = []
            
            if year:
                conditions.append("EXTRACT(YEAR FROM e.election_date) = %s")
                params.append(year)
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT p.state, COUNT(DISTINCT e.case_number) as total_elections,
                    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
                    SUM(CASE WHEN e.union_won = false THEN 1 ELSE 0 END) as union_losses,
                    ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
                        NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections e
                JOIN nlrb_participants p ON e.case_number = p.case_number 
                    AND p.participant_type = 'Employer'
                WHERE {where_clause}
                GROUP BY p.state ORDER BY COUNT(*) DESC
            """, params)
            
            return {"state_stats": cur.fetchall()}


@app.get("/api/nlrb/elections/by-affiliation")
def get_nlrb_elections_by_affiliation(min_elections: int = 10):
    """Get election statistics by union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT um.aff_abbr, MIN(um.union_name) as union_name,
                    COUNT(DISTINCT t.case_number) as elections,
                    SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as wins,
                    ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
                        NULLIF(COUNT(*), 0), 1) as win_rate,
                    AVG(e.eligible_voters)::int as avg_unit_size
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE t.tally_type = 'For' AND um.aff_abbr IS NOT NULL
                GROUP BY um.aff_abbr
                HAVING COUNT(DISTINCT t.case_number) >= %s
                ORDER BY COUNT(*) DESC
            """, [min_elections])
            
            return {"affiliation_stats": cur.fetchall()}


@app.get("/api/nlrb/election/{case_number}")
def get_nlrb_election_detail(case_number: str):
    """Get detailed information about a specific election"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.*, c.region, c.case_type
                FROM nlrb_elections e
                JOIN nlrb_cases c ON e.case_number = c.case_number
                WHERE e.case_number = %s
            """, [case_number])
            election = cur.fetchone()
            
            if not election:
                raise HTTPException(status_code=404, detail="Election not found")
            
            cur.execute("""
                SELECT participant_name, participant_type, city, state,
                    matched_employer_id, matched_olms_fnum
                FROM nlrb_participants WHERE case_number = %s
            """, [case_number])
            participants = cur.fetchall()
            
            cur.execute("""
                SELECT t.tally_type, t.labor_org_name, t.votes_for, t.is_winner,
                    um.union_name as olms_union_name, um.aff_abbr
                FROM nlrb_tallies t
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE t.case_number = %s
                ORDER BY t.votes_for DESC NULLS LAST
            """, [case_number])
            tallies = cur.fetchall()
            
            return {"election": election, "participants": participants, "tallies": tallies}


# ============================================================================
# NLRB - ULP Cases
# ============================================================================

@app.get("/api/nlrb/ulp/search")
def search_nlrb_ulp(
    state: Optional[str] = None,
    case_type: Optional[str] = None,
    section: Optional[str] = None,
    charged_party: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    limit: int = Query(100, le=500),
    offset: int = 0
):
    """Search ULP (Unfair Labor Practice) cases"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["ct.case_category = 'unfair_labor_practice'"]
            params = []
            
            if state:
                conditions.append("chg.state = %s")
                params.append(state.upper())
            if case_type:
                conditions.append("c.case_type = %s")
                params.append(case_type.upper())
            if section:
                conditions.append("a.section ILIKE %s")
                params.append(f"%{section}%")
            if charged_party:
                conditions.append("chg.participant_name ILIKE %s")
                params.append(f"%{charged_party}%")
            if year_from:
                conditions.append("EXTRACT(YEAR FROM c.earliest_date) >= %s")
                params.append(year_from)
            if year_to:
                conditions.append("EXTRACT(YEAR FROM c.earliest_date) <= %s")
                params.append(year_to)
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(DISTINCT c.case_number)
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                LEFT JOIN nlrb_participants chg ON c.case_number = chg.case_number 
                    AND chg.participant_type = 'Charged Party'
                LEFT JOIN nlrb_allegations a ON c.case_number = a.case_number
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT DISTINCT ON (c.case_number)
                    c.case_number, c.region, c.case_type, ct.description as case_type_desc,
                    c.earliest_date, chg.participant_name as charged_party,
                    chg.city, chg.state, cp.participant_name as charging_party,
                    STRING_AGG(DISTINCT a.section, ', ') as allegations
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                LEFT JOIN nlrb_participants chg ON c.case_number = chg.case_number 
                    AND chg.participant_type = 'Charged Party'
                LEFT JOIN nlrb_participants cp ON c.case_number = cp.case_number 
                    AND cp.participant_type = 'Charging Party'
                LEFT JOIN nlrb_allegations a ON c.case_number = a.case_number
                WHERE {where_clause}
                GROUP BY c.case_number, c.region, c.case_type, ct.description,
                         c.earliest_date, chg.participant_name, chg.city, chg.state, cp.participant_name
                ORDER BY c.case_number, c.earliest_date DESC
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "limit": limit, "offset": offset, "cases": cur.fetchall()}


@app.get("/api/nlrb/ulp/by-section")
def get_nlrb_ulp_by_section(year: Optional[int] = None):
    """Get ULP case counts by NLRA section"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["a.section IS NOT NULL"]
            params = []
            
            if year:
                conditions.append("EXTRACT(YEAR FROM c.earliest_date) = %s")
                params.append(year)
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT a.section, COUNT(DISTINCT c.case_number) as case_count,
                    COUNT(DISTINCT CASE WHEN chg.participant_subtype = 'Employer' 
                        THEN c.case_number END) as against_employers,
                    COUNT(DISTINCT CASE WHEN chg.participant_subtype = 'Union' 
                        THEN c.case_number END) as against_unions
                FROM nlrb_allegations a
                JOIN nlrb_cases c ON a.case_number = c.case_number
                LEFT JOIN nlrb_participants chg ON c.case_number = chg.case_number 
                    AND chg.participant_type = 'Charged Party'
                WHERE {where_clause}
                GROUP BY a.section
                ORDER BY COUNT(*) DESC LIMIT 30
            """, params)
            
            return {"section_stats": cur.fetchall()}


# ============================================================================
# PLATFORM SUMMARY - Dashboard data
# ============================================================================

@app.get("/api/summary")
def get_platform_summary():
    """Get overall platform summary statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Unions
            cur.execute("""
                SELECT COUNT(*) as total_unions, SUM(members) as total_members,
                    COUNT(DISTINCT aff_abbr) as affiliations
                FROM unions_master
            """)
            unions = cur.fetchone()
            
            # Employers (with deduplication stats)
            cur.execute("""
                SELECT COUNT(*) as total_employers,
                    SUM(latest_unit_size) as total_workers_raw,
                    SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as covered_workers,
                    COUNT(DISTINCT state) as states,
                    COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
                    ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
                FROM f7_employers_deduped
            """)
            employers = cur.fetchone()
            
            # NLRB
            cur.execute("""
                SELECT COUNT(*) as total_elections,
                    SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
                    ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / 
                        NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections WHERE union_won IS NOT NULL
            """)
            elections = cur.fetchone()
            
            cur.execute("""
                SELECT COUNT(*) as total_cases
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                WHERE ct.case_category = 'unfair_labor_practice'
            """)
            ulp = cur.fetchone()
            
            # Voluntary Recognition
            cur.execute("""
                SELECT COUNT(*) as total_cases, 
                       COUNT(matched_employer_id) as employers_matched,
                       COUNT(matched_union_fnum) as unions_matched,
                       SUM(COALESCE(num_employees, 0)) as total_employees
                FROM nlrb_voluntary_recognition
            """)
            vr = cur.fetchone()
            
            return {
                "unions": unions,
                "employers": employers,
                "nlrb": {
                    "elections": elections,
                    "ulp_cases": ulp['total_cases']
                },
                "voluntary_recognition": vr
            }


@app.get("/api/stats/breakdown")
def get_stats_breakdown(
    state: str = None,
    naics_code: str = None,
    cbsa_code: str = None,
    name: str = None
):
    """Get breakdown statistics for the filter panel"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Build WHERE clause
            conditions = ["exclude_from_counts = FALSE"]
            params = []

            if state:
                conditions.append("state = %s")
                params.append(state)
            if naics_code:
                conditions.append("naics LIKE %s")
                params.append(f"{naics_code}%")
            if cbsa_code:
                conditions.append("cbsa_code = %s")
                params.append(cbsa_code)
            if name:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{name}%")

            where_clause = " AND ".join(conditions)

            # Totals
            cur.execute(f"""
                SELECT COUNT(*) as total_employers,
                       COALESCE(SUM(latest_unit_size), 0) as total_workers,
                       COUNT(DISTINCT latest_union_fnum) as total_locals
                FROM f7_employers_deduped
                WHERE {where_clause}
            """, params)
            totals = cur.fetchone()

            # By Industry (top 5 NAICS 2-digit)
            cur.execute(f"""
                SELECT LEFT(f.naics, 2) as naics_code,
                       COALESCE(ns.sector_name, LEFT(f.naics, 2)) as industry_name,
                       COUNT(*) as employer_count, COALESCE(SUM(f.latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN naics_sectors ns ON LEFT(f.naics, 2) = ns.naics_2digit
                WHERE {where_clause} AND f.naics IS NOT NULL AND LENGTH(f.naics) >= 2
                GROUP BY LEFT(f.naics, 2), ns.sector_name
                ORDER BY worker_count DESC NULLS LAST
                LIMIT 5
            """, params)
            by_industry = cur.fetchall()

            # By Metro (top 5)
            cur.execute(f"""
                SELECT f.cbsa_code, COALESCE(c.cbsa_title, f.cbsa_code) as metro_name,
                       COUNT(*) as employer_count, COALESCE(SUM(latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN cbsa_definitions c ON f.cbsa_code = c.cbsa_code
                WHERE {where_clause} AND f.cbsa_code IS NOT NULL
                GROUP BY f.cbsa_code, c.cbsa_title
                ORDER BY worker_count DESC NULLS LAST
                LIMIT 5
            """, params)
            by_metro = cur.fetchall()

            # By Sector (union sector - Private, Public, Federal, RLA)
            cur.execute(f"""
                SELECT COALESCE(um.sector, 'Unknown') as sector_name,
                       COUNT(*) as employer_count, COALESCE(SUM(f.latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN unions_master um ON f.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
                GROUP BY um.sector
                ORDER BY worker_count DESC NULLS LAST
            """, params)
            by_sector = cur.fetchall()

            return {
                "totals": totals,
                "by_sector": by_sector,
                "by_industry": by_industry,
                "by_metro": by_metro
            }


# ============================================================================
# VOLUNTARY RECOGNITION (VR) ENDPOINTS
# ============================================================================

@app.get("/api/vr/stats/summary")
def get_vr_summary():
    """Get overall VR statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_vr_summary_stats")
            return cur.fetchone()


@app.get("/api/vr/stats/by-year")
def get_vr_by_year():
    """Get VR cases by year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_vr_yearly_summary ORDER BY year")
            return {"years": cur.fetchall()}


@app.get("/api/vr/stats/by-state")
def get_vr_by_state():
    """Get VR cases by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_vr_state_summary ORDER BY total_cases DESC")
            return {"states": cur.fetchall()}


@app.get("/api/vr/stats/by-affiliation")
def get_vr_by_affiliation():
    """Get VR cases by union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_vr_affiliation_summary ORDER BY total_cases DESC")
            return {"affiliations": cur.fetchall()}


@app.get("/api/vr/map")
def get_vr_map_data(
    state: Optional[str] = None,
    affiliation: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = Query(500, le=2000)
):
    """Get VR cases with coordinates for mapping"""
    conditions = ["latitude IS NOT NULL"]
    params = []
    
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    if affiliation:
        conditions.append("affiliation = %s")
        params.append(affiliation.upper())
    if year:
        conditions.append("year = %s")
        params.append(year)
    
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, vr_case_number, employer_name, city, state, affiliation,
                       num_employees, year, latitude, longitude
                FROM v_vr_map_data
                WHERE {where_clause}
                ORDER BY num_employees DESC NULLS LAST
                LIMIT %s
            """, params + [limit])
            return {"features": cur.fetchall()}


@app.get("/api/vr/new-employers")
def get_vr_new_employers(
    state: Optional[str] = None,
    affiliation: Optional[str] = None,
    min_employees: Optional[int] = None,
    limit: int = Query(100, le=500),
    offset: int = 0
):
    """Get employers with VR but not yet in F7 data (new organizing)"""
    conditions = ["1=1"]
    params = []
    
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    if affiliation:
        conditions.append("union_affiliation = %s")
        params.append(affiliation.upper())
    if min_employees:
        conditions.append("num_employees >= %s")
        params.append(min_employees)
    
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM v_vr_new_employers WHERE {where_clause}", params)
            total = cur.fetchone()['count']
            
            cur.execute(f"""
                SELECT * FROM v_vr_new_employers
                WHERE {where_clause}
                ORDER BY num_employees DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/vr/pipeline")
def get_vr_pipeline(
    sequence: Optional[str] = Query(None, description="Filter: 'VR preceded F7' or 'F7 preceded VR'"),
    limit: int = Query(100, le=500)
):
    """Analyze VR to F7 filing pipeline timing"""
    conditions = ["1=1"]
    params = []
    
    if sequence:
        conditions.append("sequence_type = %s")
        params.append(sequence)
    
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sequence_type, COUNT(*) as count,
                       AVG(days_vr_to_f7)::int as avg_days,
                       MIN(days_vr_to_f7) as min_days,
                       MAX(days_vr_to_f7) as max_days
                FROM v_vr_to_f7_pipeline GROUP BY sequence_type
            """)
            summary = cur.fetchall()
            
            cur.execute(f"""
                SELECT * FROM v_vr_to_f7_pipeline
                WHERE {where_clause}
                ORDER BY vr_date DESC LIMIT %s
            """, params + [limit])
            
            return {"summary": summary, "records": cur.fetchall()}


@app.get("/api/vr/search")
def search_vr(
    employer: Optional[str] = Query(None, description="Employer name"),
    union: Optional[str] = Query(None, description="Union name"),
    affiliation: Optional[str] = Query(None, description="Union affiliation (e.g., SEIU, IBT)"),
    state: Optional[str] = Query(None, description="State abbreviation"),
    city: Optional[str] = Query(None, description="City name"),
    region: Optional[int] = Query(None, description="NLRB region number"),
    year: Optional[int] = Query(None, description="Year of VR request"),
    employer_matched: Optional[bool] = Query(None, description="Has matched F7 employer"),
    union_matched: Optional[bool] = Query(None, description="Has matched OLMS union"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    sort_by: str = Query("date", description="Sort by: date, employees, employer")
):
    """Search Voluntary Recognition cases"""
    conditions = ["1=1"]
    params = []
    
    if employer:
        conditions.append("LOWER(vr.employer_name_normalized) LIKE %s")
        params.append(f"%{employer.lower()}%")
    if union:
        conditions.append("LOWER(vr.union_name_normalized) LIKE %s")
        params.append(f"%{union.lower()}%")
    if affiliation:
        conditions.append("vr.extracted_affiliation = %s")
        params.append(affiliation.upper())
    if state:
        conditions.append("vr.unit_state = %s")
        params.append(state.upper())
    if city:
        conditions.append("LOWER(vr.unit_city) LIKE %s")
        params.append(f"%{city.lower()}%")
    if region:
        conditions.append("vr.region = %s")
        params.append(region)
    if year:
        conditions.append("EXTRACT(YEAR FROM vr.date_vr_request_received) = %s")
        params.append(year)
    if employer_matched is not None:
        conditions.append("vr.matched_employer_id IS NOT NULL" if employer_matched else "vr.matched_employer_id IS NULL")
    if union_matched is not None:
        conditions.append("vr.matched_union_fnum IS NOT NULL" if union_matched else "vr.matched_union_fnum IS NULL")
    
    where_clause = " AND ".join(conditions)
    sort_map = {"date": "vr.date_vr_request_received DESC NULLS LAST", 
                "employees": "vr.num_employees DESC NULLS LAST", 
                "employer": "vr.employer_name_normalized ASC"}
    order_by = sort_map.get(sort_by, sort_map["date"])
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM nlrb_voluntary_recognition vr WHERE {where_clause}", params)
            total = cur.fetchone()['count']
            
            cur.execute(f"""
                SELECT vr.id, vr.vr_case_number, vr.region,
                       vr.employer_name_normalized as employer_name,
                       vr.unit_city as city, vr.unit_state as state,
                       vr.date_vr_request_received, vr.date_voluntary_recognition,
                       vr.union_name_normalized as union_name,
                       vr.extracted_affiliation as affiliation,
                       vr.extracted_local_number as local_number,
                       vr.num_employees, vr.unit_description,
                       vr.matched_employer_id, vr.employer_match_confidence,
                       f7.employer_name as f7_employer_name, f7.latitude, f7.longitude,
                       vr.matched_union_fnum, vr.union_match_confidence,
                       um.union_name as olms_union_name, um.members as olms_members
                FROM nlrb_voluntary_recognition vr
                LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
                LEFT JOIN unions_master um ON vr.matched_union_fnum = um.f_num
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {"total": total, "limit": limit, "offset": offset, "results": cur.fetchall()}


@app.get("/api/organizing/summary")
def get_organizing_summary(year_from: int = 2020, year_to: int = 2025):
    """Get combined organizing activity summary (Elections + VR)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_organizing_by_year
                WHERE year >= %s AND year <= %s ORDER BY year
            """, [year_from, year_to])
            return {"years": cur.fetchall()}


@app.get("/api/organizing/by-state")
def get_organizing_by_state():
    """Get combined organizing activity by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_organizing_by_state ORDER BY total_events DESC")
            return {"states": cur.fetchall()}


@app.get("/api/vr/{case_number}")
def get_vr_detail(case_number: str):
    """Get detailed info for a specific VR case"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT vr.*, nr.region_name,
                       f7.employer_name as f7_employer_name, f7.city as f7_city, 
                       f7.state as f7_state, f7.naics as f7_naics, f7.latitude, f7.longitude,
                       um.union_name as olms_union_name, um.aff_abbr as olms_affiliation,
                       um.members as olms_members, um.city as olms_city, um.state as olms_state
                FROM nlrb_voluntary_recognition vr
                LEFT JOIN nlrb_regions nr ON vr.region = nr.region_number
                LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
                LEFT JOIN unions_master um ON vr.matched_union_fnum = um.f_num
                WHERE vr.vr_case_number = %s
            """, [case_number])
            vr = cur.fetchone()
            if not vr:
                raise HTTPException(status_code=404, detail="VR case not found")
            return {"vr_case": vr}


# ============================================================================
# OSHA SAFETY DATA
# ============================================================================

@app.get("/api/osha/summary")
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


@app.get("/api/osha/establishments/search")
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


@app.get("/api/osha/establishments/{establishment_id}")
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


@app.get("/api/osha/by-state")
def get_osha_by_state():
    """Get OSHA summary statistics by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_osha_state_summary ORDER BY establishments DESC")
            return {"states": cur.fetchall()}


@app.get("/api/osha/high-severity")
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


@app.get("/api/osha/organizing-targets")
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


@app.get("/api/organizing/scorecard")
def get_organizing_scorecard(
    state: Optional[str] = None,
    naics_2digit: Optional[str] = None,
    min_employees: int = Query(default=25),
    max_employees: int = Query(default=5000),
    min_score: int = Query(default=0),
    has_contracts: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """
    Get scored organizing targets based on 8-factor system (0-100 points):
    - Company union shops (20): Related locations with union presence
    - Industry density (10): Union density in NAICS sector
    - State density (10): State union membership relative to national
    - Size (10): Establishment size sweet spot
    - OSHA (10): Violation severity and recency
    - NLRB (10): Past election activity
    - Contracts (10): Government contract funding
    - Projections (10): BLS industry growth outlook
    """
    conditions = ["employee_count >= %s", "employee_count <= %s"]
    params = [min_employees, max_employees]

    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if naics_2digit:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics_2digit}%")

    where_clause = " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Pre-fetch lookup data for efficiency
            cur.execute("SELECT naics_2digit, union_density_pct FROM v_naics_union_density")
            industry_density = {r['naics_2digit']: float(r['union_density_pct'] or 0) for r in cur.fetchall()}

            # Use members_total as a proxy for state union density (higher = more union friendly)
            cur.execute("SELECT state, members_total FROM epi_state_benchmarks")
            state_density = {r['state']: float(r['members_total'] or 0) for r in cur.fetchall()}

            cur.execute("SELECT matrix_code, employment_change_pct FROM bls_industry_projections")
            projections = {r['matrix_code']: float(r['employment_change_pct'] or 0) for r in cur.fetchall()}

            # Get base results
            cur.execute(f"""
                SELECT * FROM v_osha_organizing_targets
                WHERE {where_clause}
                ORDER BY total_penalties DESC NULLS LAST
                LIMIT 500
            """, params)
            base_results = cur.fetchall()

            # Calculate scores in Python
            scored_results = []
            for r in base_results:
                naics_2 = (r.get('naics_code') or '')[:2]
                site_state = r.get('site_state', '')
                emp_count = r.get('employee_count', 0) or 0

                # 1. Company union shops (simplified - check if matched employer exists)
                score_company_unions = 20 if r.get('matched_employer_id') else 0

                # 2. Industry density
                ind_pct = industry_density.get(naics_2, 0)
                score_industry_density = 10 if ind_pct > 20 else 8 if ind_pct > 10 else 5 if ind_pct > 5 else 2

                # 3. State density (using members_total as proxy - higher counts = stronger unions)
                st_members = state_density.get(site_state, 0)
                score_state_density = 10 if st_members > 1000000 else 8 if st_members > 500000 else 5 if st_members > 200000 else 2

                # 4. Size
                score_size = 10 if 100 <= emp_count <= 500 else 5 if emp_count > 25 else 2

                # 5. OSHA violations
                willful = r.get('willful_count', 0) or 0
                repeat = r.get('repeat_count', 0) or 0
                serious = r.get('serious_count', 0) or 0
                score_osha = min(10, willful * 4 + repeat * 2 + serious)

                # 6. NLRB (simplified - based on violation history as proxy)
                score_nlrb = 5 if r.get('total_violations', 0) > 5 else 2

                # 7. Contracts (simplified)
                score_contracts = 0

                # 8. Projections
                proj_pct = projections.get(f"{naics_2}0000", 0)
                score_projections = 10 if proj_pct > 10 else 7 if proj_pct > 5 else 4 if proj_pct > 0 else 2

                organizing_score = (score_company_unions + score_industry_density + score_state_density +
                                   score_size + score_osha + score_nlrb + score_contracts + score_projections)

                if organizing_score >= min_score:
                    # Create explicit dict to ensure proper serialization
                    result = {
                        'establishment_id': r.get('establishment_id'),
                        'estab_name': r.get('estab_name'),
                        'site_address': r.get('site_address'),
                        'site_city': r.get('site_city'),
                        'site_state': r.get('site_state'),
                        'site_zip': r.get('site_zip'),
                        'naics_code': r.get('naics_code'),
                        'employee_count': r.get('employee_count'),
                        'total_inspections': r.get('total_inspections'),
                        'last_inspection_date': str(r.get('last_inspection_date')) if r.get('last_inspection_date') else None,
                        'willful_count': r.get('willful_count'),
                        'repeat_count': r.get('repeat_count'),
                        'serious_count': r.get('serious_count'),
                        'total_violations': r.get('total_violations'),
                        'total_penalties': float(r.get('total_penalties')) if r.get('total_penalties') else None,
                        'accident_count': r.get('accident_count'),
                        'fatality_count': r.get('fatality_count'),
                        'risk_level': r.get('risk_level'),
                        'matched_employer_id': r.get('matched_employer_id'),
                        'organizing_score': organizing_score,
                        'score_breakdown': {
                            'company_unions': score_company_unions,
                            'industry_density': score_industry_density,
                            'state_density': score_state_density,
                            'size': score_size,
                            'osha': score_osha,
                            'nlrb': score_nlrb,
                            'contracts': score_contracts,
                            'projections': score_projections
                        }
                    }
                    scored_results.append(result)

            # Sort by score and apply pagination
            scored_results.sort(key=lambda x: x['organizing_score'], reverse=True)
            paginated = scored_results[offset:offset + limit]

            cur.execute(f"""
                SELECT COUNT(*) as cnt FROM v_osha_organizing_targets
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['cnt']

            return {
                "results": paginated,
                "total": total,
                "scored_count": len(scored_results),
                "limit": limit,
                "offset": offset
            }


@app.get("/api/organizing/scorecard/{estab_id}")
def get_scorecard_detail(estab_id: str):
    """Get detailed scorecard for a specific establishment with 8-factor breakdown"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get base establishment data
            cur.execute("""
                SELECT * FROM v_osha_organizing_targets WHERE establishment_id = %s
            """, [estab_id])
            base = cur.fetchone()
            if not base:
                raise HTTPException(status_code=404, detail="Establishment not found")

            naics_2 = base.get('naics_code', '')[:2] if base.get('naics_code') else None
            state = base.get('site_state')
            emp_count = base.get('employee_count', 0)
            estab_name = base.get('estab_name', '')

            # Calculate individual factor scores
            # 1. Company union shops (check for related union locations)
            cur.execute("""
                SELECT COUNT(*) > 0 as has_union FROM f7_employers_deduped
                WHERE similarity(employer_name_aggressive, %s) > 0.5
            """, [estab_name])
            has_related_union = cur.fetchone()['has_union']
            score_company_unions = 20 if has_related_union else 0

            # 2. Industry density
            score_industry_density = 2
            if naics_2:
                cur.execute("""
                    SELECT union_density_pct FROM v_naics_union_density WHERE naics_2digit = %s
                """, [naics_2])
                density_row = cur.fetchone()
                if density_row and density_row['union_density_pct']:
                    pct = float(density_row['union_density_pct'])
                    score_industry_density = 10 if pct > 20 else 8 if pct > 10 else 5 if pct > 5 else 2

            # 3. State density (using members_total as proxy)
            score_state_density = 2
            if state:
                cur.execute("""
                    SELECT members_total FROM epi_state_benchmarks WHERE state = %s
                """, [state])
                state_row = cur.fetchone()
                if state_row and state_row['members_total']:
                    members = float(state_row['members_total'])
                    score_state_density = 10 if members > 1000000 else 8 if members > 500000 else 5 if members > 200000 else 2

            # 4. Size score
            score_size = 10 if 100 <= emp_count <= 500 else 5 if emp_count > 25 else 2

            # 5. OSHA score
            willful = base.get('willful_count', 0) or 0
            repeat = base.get('repeat_count', 0) or 0
            serious = base.get('serious_count', 0) or 0
            score_osha = min(10, willful * 4 + repeat * 2 + serious)

            # 6. NLRB score
            cur.execute("""
                SELECT COUNT(*) as cnt FROM nlrb_participants
                WHERE participant_name ILIKE %s AND participant_type = 'Employer'
            """, [f"%{estab_name[:20]}%"])
            nlrb_count = cur.fetchone()['cnt']
            score_nlrb = min(10, nlrb_count * 5)

            # 7. Contracts score
            cur.execute("""
                SELECT COALESCE(SUM(current_amount), 0) as total FROM ny_state_contracts
                WHERE vendor_name ILIKE %s
            """, [f"%{estab_name[:15]}%"])
            ny_funding = cur.fetchone()['total'] or 0
            cur.execute("""
                SELECT COALESCE(SUM(current_amount), 0) as total FROM nyc_contracts
                WHERE vendor_name ILIKE %s
            """, [f"%{estab_name[:15]}%"])
            nyc_funding = cur.fetchone()['total'] or 0
            total_funding = ny_funding + nyc_funding
            score_contracts = 10 if total_funding > 5000000 else 7 if total_funding > 1000000 else 4 if total_funding > 100000 else 2 if total_funding > 0 else 0

            # 8. Projections score
            score_projections = 4
            if naics_2:
                cur.execute("""
                    SELECT employment_change_pct FROM bls_industry_projections WHERE matrix_code = %s
                """, [f"{naics_2}0000"])
                proj_row = cur.fetchone()
                if proj_row and proj_row['employment_change_pct']:
                    change = float(proj_row['employment_change_pct'])
                    score_projections = 10 if change > 10 else 7 if change > 5 else 4 if change > 0 else 2

            organizing_score = (score_company_unions + score_industry_density + score_state_density +
                              score_size + score_osha + score_nlrb + score_contracts + score_projections)

            return {
                "establishment": base,
                "organizing_score": organizing_score,
                "score_breakdown": {
                    "company_unions": score_company_unions,
                    "industry_density": score_industry_density,
                    "state_density": score_state_density,
                    "size": score_size,
                    "osha": score_osha,
                    "nlrb": score_nlrb,
                    "contracts": score_contracts,
                    "projections": score_projections
                },
                "contracts": {
                    "contract_count": 1 if total_funding > 0 else 0,
                    "total_funding": total_funding
                },
                "context": {
                    "has_related_union": has_related_union,
                    "nlrb_count": nlrb_count
                }
            }


@app.get("/api/osha/employer-safety/{f7_employer_id}")
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


# ============================================================================
# NAICS GRANULARITY ENDPOINTS
# ============================================================================

@app.get("/api/naics/stats")
def get_naics_stats():
    """Get statistics about NAICS code granularity and sources"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Source distribution
            cur.execute("""
                SELECT naics_source, COUNT(*) as count,
                       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
                FROM f7_employers_deduped
                GROUP BY naics_source
                ORDER BY count DESC
            """)
            by_source = cur.fetchall()

            # Granularity distribution
            cur.execute("""
                SELECT LENGTH(naics_detailed) as digits, COUNT(*) as count,
                       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
                FROM f7_employers_deduped
                WHERE naics_detailed IS NOT NULL
                GROUP BY LENGTH(naics_detailed)
                ORDER BY 1
            """)
            by_length = cur.fetchall()

            # Top detailed NAICS codes
            cur.execute("""
                SELECT naics_detailed, COUNT(*) as employers
                FROM f7_employers_deduped
                WHERE naics_source = 'OSHA'
                GROUP BY naics_detailed
                ORDER BY COUNT(*) DESC
                LIMIT 20
            """)
            top_detailed = cur.fetchall()

            return {
                "by_source": by_source,
                "by_granularity": by_length,
                "top_detailed_naics": top_detailed
            }


@app.get("/api/employers/by-naics-detailed/{naics_code}")
def get_employers_by_detailed_naics(
    naics_code: str,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get employers with a specific detailed NAICS code"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Count total
            cur.execute("""
                SELECT COUNT(*) FROM f7_employers_deduped
                WHERE naics_detailed LIKE %s
            """, [f"{naics_code}%"])
            total = cur.fetchone()['count']

            # Get employers
            cur.execute("""
                SELECT employer_id, employer_name, city, state, naics,
                       naics_detailed, naics_source, naics_confidence,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE naics_detailed LIKE %s
                ORDER BY latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, [f"{naics_code}%", limit, offset])
            employers = cur.fetchall()

            return {
                "naics_code": naics_code,
                "total": total,
                "employers": employers
            }


# ============================================================================
# MULTI-EMPLOYER AGREEMENT ENDPOINTS
# ============================================================================

@app.get("/api/multi-employer/stats")
def get_multi_employer_stats():
    """Get multi-employer agreement deduplication statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Summary stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_employers,
                    SUM(latest_unit_size) as total_workers_raw,
                    SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
                    SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END) as excluded_workers,
                    COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
                    ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
                FROM f7_employers_deduped
            """)
            summary = cur.fetchone()

            # By exclusion reason
            cur.execute("""
                SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
                       COUNT(*) as employers,
                       SUM(latest_unit_size) as workers
                FROM f7_employers_deduped
                GROUP BY exclude_reason
                ORDER BY SUM(latest_unit_size) DESC
            """)
            by_reason = cur.fetchall()

            # Top multi-employer groups
            cur.execute("""
                SELECT multi_employer_group_id,
                       MAX(latest_union_name) as union_name,
                       COUNT(*) as employers_in_group,
                       SUM(latest_unit_size) as total_workers,
                       SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers
                FROM f7_employers_deduped
                WHERE multi_employer_group_id IS NOT NULL
                GROUP BY multi_employer_group_id
                ORDER BY SUM(latest_unit_size) DESC
                LIMIT 20
            """)
            top_groups = cur.fetchall()

            return {
                "summary": summary,
                "by_reason": by_reason,
                "top_groups": top_groups
            }


@app.get("/api/multi-employer/groups")
def get_multi_employer_groups(limit: int = Query(50, le=200)):
    """Get list of multi-employer agreement groups"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_multi_employer_groups
                ORDER BY total_reported_workers DESC
                LIMIT %s
            """, [limit])
            return {"groups": cur.fetchall()}


@app.get("/api/employer/{employer_id}/agreement")
def get_employer_agreement_info(employer_id: str):
    """Get multi-employer agreement context for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, multi_employer_group_id,
                       is_primary_in_group, exclude_from_counts, exclude_reason,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get other employers in same group
            group_members = []
            if employer.get('multi_employer_group_id'):
                cur.execute("""
                    SELECT employer_id, employer_name, city, state,
                           latest_unit_size, is_primary_in_group, exclude_from_counts
                    FROM f7_employers_deduped
                    WHERE multi_employer_group_id = %s
                    ORDER BY latest_unit_size DESC
                    LIMIT 20
                """, [employer['multi_employer_group_id']])
                group_members = cur.fetchall()

            return {
                "employer": employer,
                "group_members": group_members,
                "group_size": len(group_members)
            }


# ============================================================================
# CORPORATE FAMILY / RELATED EMPLOYERS
# ============================================================================

@app.get("/api/corporate/family/{employer_id}")
def get_corporate_family(employer_id: str):
    """Get related employers (corporate family) - based on name similarity and multi-employer groups"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer info
            cur.execute("""
                SELECT employer_id, employer_name, employer_name_aggressive, state, naics,
                       multi_employer_group_id, latest_union_name, latest_unit_size
                FROM f7_employers_deduped WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            family_members = []

            # First, check for multi-employer group members
            if employer.get('multi_employer_group_id'):
                cur.execute("""
                    SELECT employer_id, employer_name, city, state, naics,
                           latest_unit_size, latest_union_name, 'MULTI_EMPLOYER_GROUP' as relationship
                    FROM f7_employers_deduped
                    WHERE multi_employer_group_id = %s AND employer_id != %s
                    ORDER BY latest_unit_size DESC
                    LIMIT 20
                """, [employer['multi_employer_group_id'], employer_id])
                family_members.extend(cur.fetchall())

            # Then find similar names using normalized name
            if employer.get('employer_name_aggressive'):
                group_id = employer.get('multi_employer_group_id')
                if group_id:
                    # Exclude employers already in the same multi-employer group
                    cur.execute("""
                        SELECT employer_id, employer_name, city, state, naics,
                               latest_unit_size, latest_union_name,
                               'NAME_SIMILARITY' as relationship,
                               similarity(employer_name_aggressive, %s) as name_similarity
                        FROM f7_employers_deduped
                        WHERE employer_id != %s
                          AND (multi_employer_group_id IS NULL OR multi_employer_group_id != %s)
                          AND similarity(employer_name_aggressive, %s) > 0.5
                        ORDER BY similarity(employer_name_aggressive, %s) DESC
                        LIMIT 15
                    """, [employer['employer_name_aggressive'], employer_id,
                          group_id, employer['employer_name_aggressive'],
                          employer['employer_name_aggressive']])
                else:
                    # No group to exclude
                    cur.execute("""
                        SELECT employer_id, employer_name, city, state, naics,
                               latest_unit_size, latest_union_name,
                               'NAME_SIMILARITY' as relationship,
                               similarity(employer_name_aggressive, %s) as name_similarity
                        FROM f7_employers_deduped
                        WHERE employer_id != %s
                          AND similarity(employer_name_aggressive, %s) > 0.5
                        ORDER BY similarity(employer_name_aggressive, %s) DESC
                        LIMIT 15
                    """, [employer['employer_name_aggressive'], employer_id,
                          employer['employer_name_aggressive'],
                          employer['employer_name_aggressive']])
                family_members.extend(cur.fetchall())

            return {
                "employer": employer,
                "family_members": family_members,
                "total_family": len(family_members)
            }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    """API health check"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as vr FROM nlrb_voluntary_recognition")
                vr_count = cur.fetchone()['vr']
                cur.execute("SELECT COUNT(*) as osha FROM osha_establishments")
                osha_count = cur.fetchone()['osha']
                cur.execute("SELECT COUNT(*) as ind FROM bls_industry_projections")
                ind_count = cur.fetchone()['ind']
                cur.execute("SELECT COUNT(*) as occ FROM bls_industry_occupation_matrix")
                occ_count = cur.fetchone()['occ']
                # NAICS granularity stats
                cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE naics_source = 'OSHA') as osha_enriched,
                           COUNT(*) FILTER (WHERE LENGTH(naics_detailed) = 6) as six_digit_naics
                    FROM f7_employers_deduped
                """)
                naics_stats = cur.fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "version": "6.4-multi-employer-dedup",
            "vr_records": vr_count,
            "osha_establishments": osha_count,
            "bls_industries": ind_count,
            "bls_occupation_records": occ_count,
            "naics_osha_enriched": naics_stats['osha_enriched'],
            "naics_6digit_employers": naics_stats['six_digit_naics']
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ============================================================================
# PUBLIC SECTOR
# ============================================================================

@app.get("/api/public-sector/stats")
def get_public_sector_stats():
    """Get summary statistics for public sector data"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM ps_union_locals")
            locals_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_employers")
            employers_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_parent_unions")
            parents_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_bargaining_units")
            bu_count = cur.fetchone()['count']
            cur.execute("SELECT SUM(members) as total FROM ps_union_locals WHERE members > 0")
            total_members = cur.fetchone()['total'] or 0
            cur.execute("""
                SELECT employer_type, COUNT(*) as count 
                FROM ps_employers 
                GROUP BY employer_type 
                ORDER BY count DESC
            """)
            employer_types = cur.fetchall()
            cur.execute("""
                SELECT p.abbrev, p.full_name, COUNT(l.id) as local_count, 
                       SUM(l.members) as total_members
                FROM ps_parent_unions p
                LEFT JOIN ps_union_locals l ON p.id = l.parent_union_id
                GROUP BY p.id, p.abbrev, p.full_name
                ORDER BY total_members DESC NULLS LAST
            """)
            parent_summary = cur.fetchall()
            
            return {
                "union_locals": locals_count,
                "employers": employers_count,
                "parent_unions": parents_count,
                "bargaining_units": bu_count,
                "total_members": total_members,
                "employer_types": employer_types,
                "parent_summary": parent_summary
            }


@app.get("/api/public-sector/parent-unions")
def get_public_sector_parent_unions():
    """Get list of parent unions for filtering"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.abbrev, p.full_name, p.federation, p.sector_focus,
                       COUNT(l.id) as local_count
                FROM ps_parent_unions p
                LEFT JOIN ps_union_locals l ON p.id = l.parent_union_id
                GROUP BY p.id
                ORDER BY p.full_name
            """)
            return {"parent_unions": cur.fetchall()}


@app.get("/api/public-sector/locals")
def search_public_sector_locals(
    state: Optional[str] = None,
    parent_union: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search public sector union locals"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if state:
                conditions.append("l.state = %s")
                params.append(state.upper())
            if parent_union:
                conditions.append("p.abbrev = %s")
                params.append(parent_union.upper())
            if name:
                conditions.append("l.local_name ILIKE %s")
                params.append(f"%{name}%")
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(*) FROM ps_union_locals l
                JOIN ps_parent_unions p ON l.parent_union_id = p.id
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT l.id, l.local_name, l.local_designation, l.state, l.city,
                       l.members, l.sector_type, l.f_num,
                       p.abbrev as parent_abbrev, p.full_name as parent_name
                FROM ps_union_locals l
                JOIN ps_parent_unions p ON l.parent_union_id = p.id
                WHERE {where_clause}
                ORDER BY l.members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "locals": cur.fetchall()}


@app.get("/api/public-sector/employers")
def search_public_sector_employers(
    state: Optional[str] = None,
    employer_type: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search public sector employers"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if employer_type:
                conditions.append("employer_type = %s")
                params.append(employer_type.upper())
            if name:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{name}%")
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"SELECT COUNT(*) FROM ps_employers WHERE {where_clause}", params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT id, employer_name, employer_type, state, city, county,
                       total_employees, naics_code
                FROM ps_employers
                WHERE {where_clause}
                ORDER BY employer_name
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/public-sector/employer-types")
def get_public_sector_employer_types():
    """Get list of employer types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_type, COUNT(*) as count
                FROM ps_employers
                GROUP BY employer_type
                ORDER BY count DESC
            """)
            return {"employer_types": cur.fetchall()}


@app.get("/api/public-sector/benchmarks")
def get_public_sector_benchmarks(state: Optional[str] = None):
    """Get state-level public sector benchmarks"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if state:
                cur.execute("""
                    SELECT * FROM public_sector_benchmarks WHERE state = %s
                """, [state.upper()])
                result = cur.fetchone()
                return {"benchmark": result}
            else:
                cur.execute("""
                    SELECT state, state_name, epi_public_members, epi_public_density_pct,
                           olms_state_local_members, olms_federal_members, data_quality_flag
                    FROM public_sector_benchmarks
                    ORDER BY epi_public_members DESC NULLS LAST
                """)
                return {"benchmarks": cur.fetchall()}


# ============================================================================
# UNIFIED EMPLOYERS - All employer sources combined
# ============================================================================

@app.get("/api/employers/unified/stats")
def get_unified_employer_stats():
    """Get statistics for unified employers by source type"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # By source type
            cur.execute("""
                SELECT source_type, COUNT(*) as employer_count,
                       COUNT(union_fnum) as with_union,
                       SUM(employee_count) as total_employees
                FROM unified_employers_osha
                GROUP BY source_type
                ORDER BY COUNT(*) DESC
            """)
            by_source = cur.fetchall()

            # OSHA match stats
            cur.execute("""
                SELECT u.source_type,
                       COUNT(DISTINCT m.establishment_id) as osha_establishments,
                       COUNT(DISTINCT m.unified_employer_id) as employers_matched
                FROM osha_unified_matches m
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                GROUP BY u.source_type
                ORDER BY COUNT(DISTINCT m.establishment_id) DESC
            """)
            osha_matches = cur.fetchall()

            # Overall totals
            cur.execute("SELECT COUNT(*) as total FROM unified_employers_osha")
            total_employers = cur.fetchone()['total']

            cur.execute("SELECT COUNT(DISTINCT establishment_id) as total FROM osha_unified_matches")
            total_osha_matches = cur.fetchone()['total']

            cur.execute("""
                SELECT COUNT(DISTINCT m.establishment_id)
                FROM osha_unified_matches m
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                WHERE u.union_fnum IS NOT NULL
            """)
            union_connected = cur.fetchone()['count']

            return {
                "total_employers": total_employers,
                "total_osha_matches": total_osha_matches,
                "union_connected_matches": union_connected,
                "by_source": by_source,
                "osha_matches_by_source": osha_matches
            }


@app.get("/api/employers/unified/search")
def search_unified_employers(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source_type: Optional[str] = None,
    has_union: Optional[bool] = None,
    has_osha: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search all unified employers across all sources (F7, NLRB, VR, PUBLIC)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if name:
                conditions.append("u.employer_name ILIKE %s")
                params.append(f"%{name}%")
            if state:
                conditions.append("u.state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(u.city) = %s")
                params.append(city.upper())
            if source_type:
                conditions.append("u.source_type = %s")
                params.append(source_type.upper())
            if has_union is True:
                conditions.append("u.union_fnum IS NOT NULL")
            if has_union is False:
                conditions.append("u.union_fnum IS NULL")
            if has_osha is True:
                conditions.append("EXISTS (SELECT 1 FROM osha_unified_matches m WHERE m.unified_employer_id = u.unified_id)")
            if has_osha is False:
                conditions.append("NOT EXISTS (SELECT 1 FROM osha_unified_matches m WHERE m.unified_employer_id = u.unified_id)")

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"SELECT COUNT(*) FROM unified_employers_osha u WHERE {where_clause}", params)
            total = cur.fetchone()['count']

            # Results with OSHA match count
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT u.unified_id, u.source_type, u.source_id, u.employer_name,
                       u.city, u.state, u.zip, u.naics, u.union_fnum, u.union_name,
                       u.employee_count,
                       COUNT(m.id) as osha_match_count
                FROM unified_employers_osha u
                LEFT JOIN osha_unified_matches m ON m.unified_employer_id = u.unified_id
                WHERE {where_clause}
                GROUP BY u.unified_id, u.source_type, u.source_id, u.employer_name,
                         u.city, u.state, u.zip, u.naics, u.union_fnum, u.union_name,
                         u.employee_count
                ORDER BY u.employee_count DESC NULLS LAST, u.employer_name
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/employers/unified/{unified_id}")
def get_unified_employer(unified_id: int):
    """Get details for a specific unified employer including OSHA matches"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Main employer data
            cur.execute("""
                SELECT u.*, um.union_name as full_union_name, um.aff_abbr, um.members as union_members
                FROM unified_employers_osha u
                LEFT JOIN unions_master um ON u.union_fnum = um.f_num
                WHERE u.unified_id = %s
            """, [unified_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # OSHA matches
            cur.execute("""
                SELECT m.establishment_id, m.match_method, m.match_confidence,
                       o.estab_name, o.site_city, o.site_state, o.site_zip,
                       o.naics_code, o.employee_count, o.total_inspections
                FROM osha_unified_matches m
                JOIN osha_establishments o ON o.establishment_id = m.establishment_id
                WHERE m.unified_employer_id = %s
                ORDER BY m.match_confidence DESC
            """, [unified_id])
            osha_matches = cur.fetchall()

            # If OSHA matches exist, get violations summary
            violations_summary = None
            if osha_matches:
                estab_ids = [m['establishment_id'] for m in osha_matches]
                cur.execute("""
                    SELECT COUNT(*) as total_violations,
                           SUM(CASE WHEN issuance_date >= NOW() - INTERVAL '5 years' THEN 1 ELSE 0 END) as recent_violations,
                           SUM(current_penalty) as total_penalties,
                           SUM(CASE WHEN viol_type IN ('S', 'W') THEN 1 ELSE 0 END) as serious_violations
                    FROM osha_violations_detail
                    WHERE establishment_id = ANY(%s)
                """, [estab_ids])
                violations_summary = cur.fetchone()

            return {
                "employer": employer,
                "osha_matches": osha_matches,
                "violations_summary": violations_summary
            }


@app.get("/api/osha/unified-matches")
def search_osha_unified_matches(
    state: Optional[str] = None,
    source_type: Optional[str] = None,
    has_union: Optional[bool] = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    match_method: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search OSHA establishments matched to unified employers"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["m.match_confidence >= %s"]
            params = [min_confidence]

            if state:
                conditions.append("o.site_state = %s")
                params.append(state.upper())
            if source_type:
                conditions.append("u.source_type = %s")
                params.append(source_type.upper())
            if has_union is True:
                conditions.append("u.union_fnum IS NOT NULL")
            if has_union is False:
                conditions.append("u.union_fnum IS NULL")
            if match_method:
                conditions.append("m.match_method = %s")
                params.append(match_method.upper())

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"""
                SELECT COUNT(*)
                FROM osha_unified_matches m
                JOIN osha_establishments o ON o.establishment_id = m.establishment_id
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            # Results
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT m.id, m.establishment_id, m.match_method, m.match_confidence,
                       o.estab_name, o.site_city, o.site_state, o.naics_code,
                       u.unified_id, u.source_type, u.employer_name as matched_employer,
                       u.union_fnum, u.union_name
                FROM osha_unified_matches m
                JOIN osha_establishments o ON o.establishment_id = m.establishment_id
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                WHERE {where_clause}
                ORDER BY m.match_confidence DESC, o.estab_name
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "matches": cur.fetchall()}


@app.get("/api/employers/unified/sources")
def get_unified_source_types():
    """Get list of source types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_type, COUNT(*) as count,
                       COUNT(union_fnum) as with_union
                FROM unified_employers_osha
                GROUP BY source_type
                ORDER BY COUNT(*) DESC
            """)
            return {"source_types": cur.fetchall()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
