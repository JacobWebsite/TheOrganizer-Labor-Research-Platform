"""
Labor Relations Platform API v4.1 - Enhanced with Density, Projections, Local Cascade
Run with: py -m uvicorn labor_api_v4:app --reload --port 8001
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List
from pydantic import BaseModel

# Import name normalizer for Phase 2
from name_normalizer import normalize_employer, normalize_union

app = FastAPI(
    industry_title="Labor Relations Research API", 
    version="4.1",
    description="Employer search with union density, projections, and local union cascade"
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


# ============================================================================
# LOOKUP DATA - Dropdowns and filters
# ============================================================================

@app.get("/api/lookups/sectors")
def get_sectors():
    """Get all union sectors (Private, Federal, Public, RLA)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    us.sector_code,
                    us.sector_name,
                    us.governing_law,
                    us.f7_expected,
                    us.description,
                    COUNT(DISTINCT um.f_num) as union_count,
                    SUM(um.members) as total_members,
                    SUM(um.f7_employer_count) as employer_count
                FROM union_sector us
                LEFT JOIN unions_master um ON us.sector_code = um.sector
                GROUP BY us.sector_code, us.sector_name, us.governing_law, us.f7_expected, us.description
                ORDER BY SUM(um.members) DESC NULLS LAST
            """)
            return {"sectors": cur.fetchall()}


@app.get("/api/lookups/naics-sectors")
def get_naics_sectors():
    """Get all NAICS 2-digit sectors with employer counts and union density"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    ns.naics_2digit,
                    ns.sector_name,
                    COUNT(DISTINCT e.employer_id) as employer_count,
                    SUM(e.latest_unit_size) as total_workers,
                    COUNT(DISTINCT e.latest_union_fnum) as union_count,
                    vnd.union_density_pct,
                    vnd.year as density_year
                FROM naics_sectors ns
                LEFT JOIN f7_employers_deduped e ON LEFT(e.naics, 2) = ns.naics_2digit
                LEFT JOIN v_naics_union_density vnd ON ns.naics_2digit = vnd.naics_2digit
                GROUP BY ns.naics_2digit, ns.sector_name, vnd.union_density_pct, vnd.year
                ORDER BY COUNT(DISTINCT e.employer_id) DESC NULLS LAST
            """)
            return {"naics_sectors": cur.fetchall()}


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
                SELECT 
                    aff_abbr,
                    MAX(union_name) as example_name,
                    COUNT(*) as local_count,
                    SUM(members) as total_members,
                    SUM(f7_employer_count) as employer_count,
                    SUM(f7_total_workers) as covered_workers,
                    array_agg(DISTINCT sector) FILTER (WHERE sector IS NOT NULL) as sectors
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
                SELECT 
                    state,
                    COUNT(*) as employer_count,
                    SUM(latest_unit_size) as total_workers,
                    COUNT(DISTINCT latest_union_fnum) as union_count
                FROM f7_employers_deduped
                WHERE state IS NOT NULL AND state != ''
                GROUP BY state
                ORDER BY COUNT(*) DESC
            """)
            return {"states": cur.fetchall()}


# ============================================================================
# FEATURE C: Local Union Cascade
# ============================================================================

@app.get("/api/unions/locals/{affiliation}")
def get_locals_for_affiliation(
    affiliation: str,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    has_employers: Optional[bool] = None,
    limit: int = Query(200, le=1000)
):
    """Get all local unions for a national affiliation (for cascade dropdown)"""
    conditions = ["aff_abbr = %s"]
    params = [affiliation.upper()]
    
    if sector and sector != 'ALL':
        conditions.append("sector = %s")
        params.append(sector.upper())
    
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    
    if has_employers is True:
        conditions.append("f7_employer_count > 0")
    
    where_clause = " AND ".join(conditions)
    params.append(limit)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    f_num,
                    union_name,
                    city,
                    state,
                    members,
                    f7_employer_count,
                    f7_total_workers,
                    sector
                FROM unions_master
                WHERE {where_clause}
                ORDER BY 
                    CASE WHEN f7_employer_count > 0 THEN 0 ELSE 1 END,
                    members DESC NULLS LAST
                LIMIT %s
            """, params)
            locals_list = cur.fetchall()
            
            return {
                "affiliation": affiliation.upper(),
                "count": len(locals_list),
                "locals": locals_list
            }


@app.get("/api/unions/{f_num}")
def get_union_detail(f_num: str):
    """Get detailed info for a specific local union"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Basic info
            cur.execute("""
                SELECT 
                    um.*,
                    us.sector_name,
                    us.governing_law
                FROM unions_master um
                LEFT JOIN union_sector us ON um.sector = us.sector_code
                WHERE um.f_num = %s
            """, [f_num])
            union = cur.fetchone()
            
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")
            
            # Get financial data from lm_data
            cur.execute("""
                SELECT 
                    yr_covered,
                    members,
                    ttl_assets,
                    ttl_liabilities,
                    ttl_receipts,
                    ttl_disbursements
                FROM lm_data
                WHERE f_num = %s
                ORDER BY yr_covered DESC
                LIMIT 5
            """, [int(f_num)])
            financials = cur.fetchall()
            
            # Get NAICS distribution
            cur.execute("""
                SELECT 
                    LEFT(naics, 2) as naics_2digit,
                    ns.sector_name,
                    COUNT(*) as employer_count,
                    SUM(latest_unit_size) as workers
                FROM f7_employers_deduped e
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE latest_union_fnum = %s AND naics IS NOT NULL
                GROUP BY LEFT(naics, 2), ns.sector_name
                ORDER BY SUM(latest_unit_size) DESC NULLS LAST
            """, [int(f_num)])
            industries = cur.fetchall()
            
            return {
                "union": union,
                "financials": financials,
                "industries": industries
            }


# ============================================================================
# EMPLOYER SEARCH - Primary search endpoint
# ============================================================================

@app.get("/api/employers/search")
def search_employers(
    # Search terms
    name: Optional[str] = Query(None, description="Employer name (fuzzy match)"),
    
    # Union filters
    affiliation: Optional[str] = Query(None, description="National union affiliation (e.g., SEIU, UAW)"),
    f_num: Optional[str] = Query(None, description="Specific local union file number"),
    union_sector: Optional[str] = Query(None, description="Union sector: PRIVATE, FEDERAL, PUBLIC_SECTOR, RLA"),
    
    # Industry filters
    naics_2digit: Optional[str] = Query(None, description="NAICS 2-digit sector code"),
    naics_prefix: Optional[str] = Query(None, description="NAICS code prefix (any length)"),
    
    # Geographic filters
    state: Optional[str] = Query(None, description="State abbreviation"),
    city: Optional[str] = Query(None, description="City name"),
    
    # Status filters
    active_only: bool = Query(True, description="Exclude potentially defunct employers"),
    has_coords: Optional[bool] = Query(None, description="Only geocoded employers (for mapping)"),
    
    # Pagination
    limit: int = Query(50, le=500),
    offset: int = 0,
    
    # Sorting
    sort_by: str = Query("workers", description="Sort by: workers, name, date")
):
    """
    Search F-7 employers with comprehensive filtering.
    Supports union, industry, and geographic filters with fuzzy name matching.
    """
    conditions = ["1=1"]
    params = []
    
    # Name search (case-insensitive contains)
    if name:
        conditions.append("LOWER(e.employer_name) LIKE %s")
        params.append(f"%{name.lower()}%")
    
    # Union filters
    if affiliation:
        conditions.append("um.aff_abbr = %s")
        params.append(affiliation.upper())
    
    if f_num:
        conditions.append("e.latest_union_fnum = %s")
        params.append(int(f_num))
    
    if union_sector and union_sector != 'ALL':
        conditions.append("um.sector = %s")
        params.append(union_sector.upper())
    
    # Industry filters
    if naics_2digit:
        conditions.append("LEFT(e.naics, 2) = %s")
        params.append(naics_2digit)
    elif naics_prefix:
        conditions.append("e.naics LIKE %s")
        params.append(f"{naics_prefix}%")
    
    # Geographic filters
    if state:
        conditions.append("e.state = %s")
        params.append(state.upper())
    
    if city:
        conditions.append("LOWER(e.city) LIKE %s")
        params.append(f"%{city.lower()}%")
    
    # Status filters
    if active_only:
        conditions.append("(e.potentially_defunct = 0 OR e.potentially_defunct IS NULL)")
    
    if has_coords is True:
        conditions.append("e.latitude IS NOT NULL AND e.longitude IS NOT NULL")
    elif has_coords is False:
        conditions.append("(e.latitude IS NULL OR e.longitude IS NULL)")
    
    where_clause = " AND ".join(conditions)
    
    # Sorting
    order_map = {
        "workers": "e.latest_unit_size DESC NULLS LAST",
        "name": "e.employer_name ASC",
        "date": "e.latest_notice_date DESC NULLS LAST"
    }
    order_by = order_map.get(sort_by, order_map["workers"])
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get count
            cur.execute(f"""
                SELECT COUNT(*) as total
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['total']
            
            # Get results with NAICS sector info
            params_with_pagination = params + [limit, offset]
            cur.execute(f"""
                SELECT 
                    e.employer_id,
                    e.employer_name,
                    e.city,
                    e.state,
                    e.zip,
                    e.naics,
                    LEFT(e.naics, 2) as naics_2digit,
                    ns.sector_name as naics_sector_name,
                    e.latest_unit_size,
                    e.latest_union_fnum,
                    e.latest_union_name,
                    e.latest_notice_date,
                    e.latitude,
                    e.longitude,
                    e.healthcare_related,
                    e.potentially_defunct,
                    um.aff_abbr,
                    um.union_name as union_display_name,
                    um.members as union_members,
                    um.sector as union_sector
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """, params_with_pagination)
            
            employers = cur.fetchall()
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "employers": employers
            }


# ============================================================================
# FEATURE A: BLS Union Density by Industry
# ============================================================================

@app.get("/api/density/naics/{naics_2digit}")
def get_naics_density(naics_2digit: str):
    """Get union density data for a NAICS 2-digit sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get current density
            cur.execute("""
                SELECT 
                    naics_2digit,
                    sector_name,
                    bls_indy_code,
                    bls_indy_name,
                    year,
                    union_density_pct
                FROM v_naics_union_density
                WHERE naics_2digit = %s
            """, [naics_2digit])
            current = cur.fetchone()
            
            # Get historical trend (if mapping exists)
            if current and current['bls_indy_code']:
                cur.execute("""
                    SELECT 
                        bud.year,
                        bud.value as union_density_pct
                    FROM bls_union_series bus
                    JOIN bls_union_data bud ON bus.series_id = bud.series_id
                    WHERE bus.indy_code = %s AND bus.fips_code = '00' AND bus.pcts_code = '05' AND bus.unin_code = '1'
                    ORDER BY bud.year DESC
                    LIMIT 15
                """, [current['bls_indy_code']])
                trend = cur.fetchall()
            else:
                trend = []
            
            return {
                "naics_2digit": naics_2digit,
                "current": current,
                "trend": trend
            }


@app.get("/api/density/all")
def get_all_density(year: Optional[int] = None):
    """Get union density for all NAICS sectors"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if year:
                cur.execute("""
                    SELECT 
                        bnm.naics_2digit,
                        ns.sector_name,
                        bnm.bls_indy_name,
                        bud.year,
                        bud.value as union_density_pct
                    FROM bls_naics_mapping bnm
                    JOIN naics_sectors ns ON bnm.naics_2digit = ns.naics_2digit
                    JOIN bls_union_series bus ON bus.indy_code = bnm.bls_indy_code AND bus.fips_code = '00'
                    JOIN bls_union_data bud ON bus.series_id = bud.series_id
                    WHERE bud.year = %s
                    ORDER BY bud.value DESC
                """, [year])
            else:
                cur.execute("""
                    SELECT * FROM v_naics_union_density
                    ORDER BY union_density_pct DESC
                """)
            
            return {"density": cur.fetchall()}


# ============================================================================
# FEATURE B: Employment Projections
# ============================================================================

@app.get("/api/projections/naics/{naics_2digit}")
def get_naics_projections(naics_2digit: str, limit: int = Query(20, le=100)):
    """Get employment projections for a NAICS 2-digit sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get sector-level projection
            cur.execute("""
                SELECT 
                    naics_code,
                    industry_title,
                    employment_2024,
                    employment_2034,
                    employment_change,
                    employment_change_pct
                FROM bls_industry_projections
                WHERE naics_code = %s OR naics_code LIKE %s
                ORDER BY 
                    CASE WHEN naics_code = %s THEN 0 ELSE 1 END,
                    ABS(employment_change) DESC
                LIMIT %s
            """, [naics_2digit, f"{naics_2digit}%", naics_2digit, limit])
            
            projections = cur.fetchall()
            
            # Calculate sector summary
            cur.execute("""
                SELECT 
                    SUM(employment_2024) as total_2024,
                    SUM(employment_2034) as total_2034,
                    SUM(employment_change) as total_change,
                    AVG(employment_change_pct) as avg_employment_change_pct
                FROM bls_industry_projections
                WHERE naics_code LIKE %s
            """, [f"{naics_2digit}%"])
            summary = cur.fetchone()
            
            return {
                "naics_2digit": naics_2digit,
                "summary": summary,
                "projections": projections
            }


@app.get("/api/projections/top")
def get_top_projections(
    growing: bool = Query(True, description="True for growing, False for declining"),
    limit: int = Query(20, le=100)
):
    """Get top growing or declining industries"""
    with get_db() as conn:
        with conn.cursor() as cur:
            order = "DESC" if growing else "ASC"
            condition = "> 0" if growing else "< 0"
            
            cur.execute(f"""
                SELECT 
                    LEFT(naics_code, 2) as naics_2digit,
                    ns.sector_name,
                    naics_code,
                    industry_title,
                    employment_2024,
                    employment_2034,
                    employment_change,
                    employment_change_pct
                FROM bls_industry_projections bip
                LEFT JOIN naics_sectors ns ON LEFT(bip.naics_code, 2) = ns.naics_2digit
                WHERE employment_change_pct {condition}
                ORDER BY employment_change_pct {order}
                LIMIT %s
            """, [limit])
            
            return {
                "type": "growing" if growing else "declining",
                "projections": cur.fetchall()
            }


@app.get("/api/projections/occupations/{naics_2digit}")
def get_occupation_projections(naics_2digit: str, limit: int = Query(20, le=100)):
    """Get top occupations in a NAICS sector with employment projections"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    m.soc_code,
                    m.soc_title,
                    m.employment_2024,
                    m.employment_2034,
                    m.employment_change,
                    m.employment_change_pct,
                    m.percent_of_industry_employment
                FROM bls_industry_occupation_matrix m
                WHERE m.naics_code LIKE %s
                ORDER BY m.employment_2024 DESC
                LIMIT %s
            """, [f"{naics_2digit}%", limit])
            
            return {"naics_2digit": naics_2digit, "occupations": cur.fetchall()}


# ============================================================================
# STATISTICS / DASHBOARD
# ============================================================================

@app.get("/api/stats/overview")
def get_overview_stats():
    """Get platform-wide statistics for dashboard"""
    with get_db() as conn:
        with conn.cursor() as cur:
            stats = {}
            
            # Union counts
            cur.execute("SELECT COUNT(*) as cnt FROM unions_master")
            stats['total_unions'] = cur.fetchone()['cnt']
            
            cur.execute("SELECT COUNT(DISTINCT aff_abbr) as cnt FROM unions_master WHERE aff_abbr IS NOT NULL")
            stats['national_affiliations'] = cur.fetchone()['cnt']
            
            cur.execute("SELECT SUM(members) as total FROM unions_master")
            stats['total_members'] = cur.fetchone()['total']
            
            # Employer counts
            cur.execute("SELECT COUNT(*) as cnt FROM f7_employers_deduped")
            stats['total_employers'] = cur.fetchone()['cnt']
            
            cur.execute("SELECT SUM(latest_unit_size) as total FROM f7_employers_deduped")
            stats['covered_workers'] = cur.fetchone()['total']
            
            cur.execute("SELECT COUNT(*) as cnt FROM f7_employers_deduped WHERE latitude IS NOT NULL")
            stats['geocoded_employers'] = cur.fetchone()['cnt']
            
            # Sector breakdown
            cur.execute("""
                SELECT sector, COUNT(*) as union_count, SUM(members) as members
                FROM unions_master
                WHERE sector IS NOT NULL
                GROUP BY sector
                ORDER BY SUM(members) DESC NULLS LAST
            """)
            stats['by_sector'] = cur.fetchall()
            
            # Top NAICS sectors with density
            cur.execute("""
                SELECT 
                    LEFT(e.naics, 2) as naics_2digit,
                    ns.sector_name,
                    COUNT(*) as employer_count,
                    SUM(e.latest_unit_size) as workers,
                    vnd.union_density_pct
                FROM f7_employers_deduped e
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                LEFT JOIN v_naics_union_density vnd ON LEFT(e.naics, 2) = vnd.naics_2digit
                WHERE e.naics IS NOT NULL
                GROUP BY LEFT(e.naics, 2), ns.sector_name, vnd.union_density_pct
                ORDER BY SUM(e.latest_unit_size) DESC NULLS LAST
                LIMIT 10
            """)
            stats['top_industries'] = cur.fetchall()
            
            return stats


# ============================================================================
# FUZZY NAME SEARCH - New in v4.2
# ============================================================================

@app.get("/api/employers/fuzzy-search")
def fuzzy_search_employers(
    name: str = Query(..., description="Employer name to search (typo-tolerant)"),
    threshold: float = Query(0.3, ge=0.1, le=1.0, description="Similarity threshold (0.3=loose, 0.7=strict)"),
    state: Optional[str] = Query(None, description="Filter by state"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """
    FUZZY search for employers using pg_trgm similarity.
    
    - Catches typos: 'kaizer' finds 'Kaiser Permanente'
    - Catches variations: 'kroger' finds 'The Kroger Company', 'Kroger Mid-Atlantic', etc.
    - Returns match_score (0-1) showing how close the match is
    
    Threshold guide:
    - 0.3: Very loose, catches many variations (default)
    - 0.5: Moderate, good balance
    - 0.7: Strict, only close matches
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Build WHERE clause
            state_filter = "AND e.state = %s" if state else ""
            
            # Count total matches
            count_params = [name, threshold]
            if state:
                count_params.append(state.upper())
            
            cur.execute(f"""
                SELECT COUNT(*) as total
                FROM f7_employers_deduped e
                WHERE similarity(e.employer_name, %s) > %s {state_filter}
            """, count_params)
            total = cur.fetchone()['total']
            
            # Get results sorted by similarity
            # Params: name (for similarity in SELECT), name (for WHERE), threshold, [state], name (for ORDER BY), limit, offset
            select_params = [name, name, threshold]
            if state:
                select_params.append(state.upper())
            select_params.extend([name, limit, offset])
            
            cur.execute(f"""
                SELECT 
                    e.employer_id,
                    e.employer_name,
                    similarity(e.employer_name, %s) as match_score,
                    e.city,
                    e.state,
                    e.naics,
                    e.latest_unit_size,
                    e.latest_union_fnum,
                    e.latest_union_name,
                    e.latitude,
                    e.longitude,
                    um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE similarity(e.employer_name, %s) > %s {state_filter}
                ORDER BY similarity(e.employer_name, %s) DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)
            
            return {
                "search_term": name,
                "threshold": threshold,
                "total": total,
                "employers": cur.fetchall()
            }


@app.get("/api/employers/find-similar")
def find_similar_employers(
    employer_id: str = Query(..., description="Employer ID to find similar matches for"),
    threshold: float = Query(0.7, ge=0.3, le=1.0, description="Similarity threshold"),
    same_state: bool = Query(True, description="Only match within same state (blocking)"),
    limit: int = Query(20, le=100)
):
    """
    Find employers similar to a given employer (for deduplication/grouping).
    Uses blocking strategy (same state) for efficiency.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get the source employer
            cur.execute("""
                SELECT employer_name, city, state 
                FROM f7_employers_deduped 
                WHERE employer_id = %s
            """, [employer_id])
            source = cur.fetchone()
            
            if not source:
                raise HTTPException(status_code=404, detail="Employer not found")
            
            source_name = source['employer_name']
            state_filter = "AND e.state = %s" if (same_state and source['state']) else ""
            
            # Build params list in order of %s placeholders:
            # SELECT: similarity(%s), WHERE: employer_id != %s, similarity(%s) > %s, [state], ORDER BY: similarity(%s), LIMIT: %s
            params = [source_name, employer_id, source_name, threshold]
            if same_state and source['state']:
                params.append(source['state'])
            params.extend([source_name, limit])
            
            cur.execute(f"""
                SELECT 
                    e.employer_id,
                    e.employer_name,
                    similarity(e.employer_name, %s) as match_score,
                    e.city,
                    e.state,
                    e.latest_unit_size,
                    e.latest_union_name,
                    um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.employer_id != %s 
                  AND similarity(e.employer_name, %s) > %s {state_filter}
                ORDER BY similarity(e.employer_name, %s) DESC
                LIMIT %s
            """, params)
            
            return {
                "source_employer": source,
                "threshold": threshold,
                "same_state_only": same_state,
                "similar_employers": cur.fetchall()
            }


@app.get("/api/search/unions")
def fuzzy_search_unions(
    name: str = Query(..., description="Union name to search"),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    limit: int = Query(50, le=500)
):
    """
    FUZZY search for unions using pg_trgm similarity.
    Catches abbreviations and variations.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    f_num,
                    union_name,
                    similarity(union_name, %s) as match_score,
                    aff_abbr,
                    city,
                    state,
                    members,
                    sector,
                    f7_employer_count
                FROM unions_master
                WHERE similarity(union_name, %s) > %s
                ORDER BY similarity(union_name, %s) DESC, members DESC NULLS LAST
                LIMIT %s
            """, [name, name, threshold, name, limit])
            
            return {
                "search_term": name,
                "threshold": threshold,
                "unions": cur.fetchall()
            }


@app.get("/api/employers/normalized-search")
def normalized_search_employers(
    name: str = Query(..., description="Employer name to search"),
    threshold: float = Query(0.4, ge=0.1, le=1.0, description="Similarity threshold"),
    state: Optional[str] = Query(None, description="Filter by state"),
    strip_location: bool = Query(True, description="Remove location suffixes like '- Oakland'"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """
    Search employers with NAME NORMALIZATION + fuzzy matching.
    
    Normalization removes:
    - "The", "Inc", "LLC", "Corp", "Company", etc.
    - Optionally location suffixes like "- Oakland" or "(Master)"
    
    This means:
    - "The Kroger Company" and "Kroger" will both match "kroger"
    - "Kaiser Permanente - Oakland" matches "kaiser permanente"
    
    Returns both raw name and normalized version for comparison.
    """
    # Normalize the search term
    normalized_search = normalize_employer(name, strip_location=strip_location)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # We'll normalize on the fly in SQL using a CTE
            # For better performance, you could pre-compute normalized names in a column
            
            state_filter = "AND e.state = %s" if state else ""
            
            # Count
            count_params = [normalized_search, threshold]
            if state:
                count_params.append(state.upper())
                
            cur.execute(f"""
                WITH normalized AS (
                    SELECT 
                        e.*,
                        LOWER(REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(e.employer_name, '^[Tt]he\\s+', ''),
                                '\\s*(Inc\\.?|LLC|Corp\\.?|Company|Co\\.?|Ltd\\.?|LP|LLP)\\s*


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    """API health check"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "version": "4.2-fuzzy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
, '', 'gi'
                            ),
                            '\\s*[-]\\s*\\w+\\s*


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    """API health check"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "version": "4.2-fuzzy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
, '', 'g'
                        )) as normalized_name
                    FROM f7_employers_deduped e
                )
                SELECT COUNT(*) as total
                FROM normalized n
                WHERE similarity(n.normalized_name, %s) > %s {state_filter}
            """, count_params)
            total = cur.fetchone()['total']
            
            # Results
            select_params = [normalized_search, normalized_search, threshold]
            if state:
                select_params.append(state.upper())
            select_params.extend([normalized_search, limit, offset])
            
            cur.execute(f"""
                WITH normalized AS (
                    SELECT 
                        e.*,
                        LOWER(REGEXP_REPLACE(
                            REGEXP_REPLACE(
                                REGEXP_REPLACE(e.employer_name, '^[Tt]he\\s+', ''),
                                '\\s*(Inc\\.?|LLC|Corp\\.?|Company|Co\\.?|Ltd\\.?|LP|LLP)\\s*


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    """API health check"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "version": "4.2-fuzzy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
, '', 'gi'
                            ),
                            '\\s*[-]\\s*\\w+\\s*


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    """API health check"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "version": "4.2-fuzzy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
, '', 'g'
                        )) as normalized_name
                    FROM f7_employers_deduped e
                )
                SELECT 
                    n.employer_id,
                    n.employer_name,
                    n.normalized_name,
                    similarity(n.normalized_name, %s) as match_score,
                    n.city,
                    n.state,
                    n.naics,
                    n.latest_unit_size,
                    n.latest_union_fnum,
                    n.latest_union_name,
                    n.latitude,
                    n.longitude,
                    um.aff_abbr
                FROM normalized n
                LEFT JOIN unions_master um ON n.latest_union_fnum::text = um.f_num
                WHERE similarity(n.normalized_name, %s) > %s {state_filter}
                ORDER BY similarity(n.normalized_name, %s) DESC, n.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)
            
            return {
                "search_term": name,
                "normalized_search": normalized_search,
                "threshold": threshold,
                "total": total,
                "employers": cur.fetchall()
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
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "version": "4.2-fuzzy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
