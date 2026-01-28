"""
Labor Relations Platform API v4.2 - With Fuzzy + Normalized Search
Run with: py -m uvicorn labor_api_v42:app --reload --port 8001
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

# Import name normalizer
from name_normalizer import normalize_employer, normalize_union, normalize_for_comparison, extract_local_number

app = FastAPI(
    title="Labor Relations Research API", 
    version="4.2",
    description="Employer search with fuzzy matching and name normalization"
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
# LOOKUPS
# ============================================================================

@app.get("/api/lookups/sectors")
def get_sectors():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT us.sector_code, us.sector_name, us.governing_law, us.f7_expected, us.description,
                       COUNT(DISTINCT um.f_num) as union_count, SUM(um.members) as total_members
                FROM union_sector us
                LEFT JOIN unions_master um ON us.sector_code = um.sector
                GROUP BY us.sector_code, us.sector_name, us.governing_law, us.f7_expected, us.description
                ORDER BY SUM(um.members) DESC NULLS LAST
            """)
            return {"sectors": cur.fetchall()}


@app.get("/api/lookups/naics-sectors")
def get_naics_sectors():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ns.naics_2digit, ns.sector_name, COUNT(DISTINCT e.employer_id) as employer_count,
                       SUM(e.latest_unit_size) as total_workers, vnd.union_density_pct
                FROM naics_sectors ns
                LEFT JOIN f7_employers_deduped e ON LEFT(e.naics, 2) = ns.naics_2digit
                LEFT JOIN v_naics_union_density vnd ON ns.naics_2digit = vnd.naics_2digit
                GROUP BY ns.naics_2digit, ns.sector_name, vnd.union_density_pct
                ORDER BY COUNT(DISTINCT e.employer_id) DESC NULLS LAST
            """)
            return {"naics_sectors": cur.fetchall()}


@app.get("/api/lookups/affiliations")
def get_affiliations(sector: Optional[str] = None):
    conditions = ["aff_abbr IS NOT NULL AND aff_abbr != ''"]
    params = []
    if sector and sector != 'ALL':
        conditions.append("sector = %s")
        params.append(sector.upper())
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT aff_abbr, MAX(union_name) as example_name, COUNT(*) as local_count,
                       SUM(members) as total_members, SUM(f7_employer_count) as employer_count
                FROM unions_master WHERE {where_clause}
                GROUP BY aff_abbr HAVING COUNT(*) >= 3
                ORDER BY SUM(members) DESC NULLS LAST
            """, params)
            return {"affiliations": cur.fetchall()}


@app.get("/api/lookups/states")
def get_states():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT state, COUNT(*) as employer_count, SUM(latest_unit_size) as total_workers
                FROM f7_employers_deduped WHERE state IS NOT NULL AND state != ''
                GROUP BY state ORDER BY COUNT(*) DESC
            """)
            return {"states": cur.fetchall()}


# ============================================================================
# UNION ENDPOINTS
# ============================================================================

@app.get("/api/unions/locals/{affiliation}")
def get_locals_for_affiliation(affiliation: str, state: Optional[str] = None, limit: int = Query(200, le=1000)):
    conditions = ["aff_abbr = %s"]
    params = [affiliation.upper()]
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    where_clause = " AND ".join(conditions)
    params.append(limit)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT f_num, union_name, local_number, desig_name, city, state, members, f7_employer_count, sector
                FROM unions_master WHERE {where_clause}
                ORDER BY CASE WHEN f7_employer_count > 0 THEN 0 ELSE 1 END, members DESC NULLS LAST
                LIMIT %s
            """, params)
            return {"affiliation": affiliation.upper(), "locals": cur.fetchall()}

@app.get("/api/unions/canonical-lookup")
def canonical_lookup_route(
    name: str = Query(..., description="Union name, acronym, or abbreviation")
):
    from canonical_lookup import lookup_canonical
    result = lookup_canonical(name)
    if result:
        return result
    return {"input": name, "canonical_name": None, "message": "No matching variant found"}


@app.get("/api/unions/smart-search")
def smart_search_unions(
    name: str = Query(..., description="Union name (expands acronyms automatically)"),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    limit: int = Query(50, le=500)
):
    from canonical_lookup import lookup_canonical
    canonical = lookup_canonical(name)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            if canonical:
                abbr_map = {
                    'Service Employees International Union': 'SEIU',
                    'United Food and Commercial Workers': 'UFCW',
                    'International Brotherhood of Teamsters': 'IBT',
                    'United Automobile Workers': 'UAW',
                    'American Federation of State County and Municipal Employees': 'AFSCME',
                    'Communications Workers of America': 'CWA',
                    'International Brotherhood of Electrical Workers': 'IBEW',
                    'United Steelworkers': 'USW',
                    'Laborers International Union of North America': 'LIUNA',
                    'American Federation of Teachers': 'AFT',
                    'International Association of Machinists and Aerospace Workers': 'IAM',
                    'United Brotherhood of Carpenters': 'UBC',
                    'International Union of Operating Engineers': 'IUOE',
                }
                aff_code = abbr_map.get(canonical['canonical_name'])
                if aff_code:
                    cur.execute("""
                        SELECT f_num, union_name, 1.0 as match_score,
                               aff_abbr, city, state, members, sector, f7_employer_count
                        FROM unions_master WHERE aff_abbr = %s
                        ORDER BY members DESC NULLS LAST LIMIT %s
                    """, [aff_code, limit])
                    return {"search_term": name, "expanded_to": canonical['canonical_name'],
                            "aff_abbr": aff_code, "match_type": "affiliation", "unions": cur.fetchall()}
            
            cur.execute("""
                SELECT f_num, union_name, similarity(union_name, %s) as match_score,
                       aff_abbr, city, state, members, sector, f7_employer_count
                FROM unions_master WHERE similarity(union_name, %s) > %s
                ORDER BY similarity(union_name, %s) DESC, members DESC NULLS LAST LIMIT %s
            """, [name, name, threshold, name, limit])
            return {"search_term": name, "match_type": "fuzzy", "unions": cur.fetchall()}

@app.get("/api/unions/{f_num}")
def get_union_detail(f_num: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT um.*, us.sector_name, us.governing_law
                FROM unions_master um
                LEFT JOIN union_sector us ON um.sector = us.sector_code
                WHERE um.f_num = %s
            """, [f_num])
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")
            
            cur.execute("""
                SELECT yr_covered, members, ttl_assets, ttl_receipts
                FROM lm_data WHERE f_num = %s ORDER BY yr_covered DESC LIMIT 5
            """, [int(f_num)])
            financials = cur.fetchall()
            
            return {"union": union, "financials": financials}


# ============================================================================
# EMPLOYER SEARCH
# ============================================================================

@app.get("/api/employers/search")
def search_employers(
    name: Optional[str] = None,
    affiliation: Optional[str] = None,
    f_num: Optional[str] = None,
    naics_2digit: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    active_only: bool = True,
    has_coords: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    sort_by: str = "workers"
):
    """Basic employer search with filters."""
    conditions = ["1=1"]
    params = []
    
    if name:
        conditions.append("LOWER(e.employer_name) LIKE %s")
        params.append(f"%{name.lower()}%")
    if affiliation:
        conditions.append("um.aff_abbr = %s")
        params.append(affiliation.upper())
    if f_num:
        conditions.append("e.latest_union_fnum = %s")
        params.append(int(f_num))
    if naics_2digit:
        conditions.append("LEFT(e.naics, 2) = %s")
        params.append(naics_2digit)
    if state:
        conditions.append("e.state = %s")
        params.append(state.upper())
    if city:
        conditions.append("LOWER(e.city) LIKE %s")
        params.append(f"%{city.lower()}%")
    if active_only:
        conditions.append("(e.potentially_defunct = 0 OR e.potentially_defunct IS NULL)")
    if has_coords is True:
        conditions.append("e.latitude IS NOT NULL")
    
    where_clause = " AND ".join(conditions)
    order_map = {"workers": "e.latest_unit_size DESC NULLS LAST", "name": "e.employer_name ASC"}
    order_by = order_map.get(sort_by, order_map["workers"])
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT COUNT(*) as total FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['total']
            
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, e.city, e.state, e.naics,
                       e.latest_unit_size, e.latest_union_fnum, e.latest_union_name,
                       e.latitude, e.longitude, um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause} ORDER BY {order_by} LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {"total": total, "employers": cur.fetchall()}


# ============================================================================
# FUZZY SEARCH (Phase 1 - pg_trgm)
# ============================================================================

@app.get("/api/employers/fuzzy-search")
def fuzzy_search_employers(
    name: str = Query(..., description="Employer name (typo-tolerant)"),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    state: Optional[str] = None,
    affiliation: Optional[str] = Query(None, description="Filter by union affiliation (e.g., SEIU, UAW)"),
    f_num: Optional[str] = Query(None, description="Filter by specific union f_num"),
    naics_2digit: Optional[str] = Query(None, description="Filter by 2-digit NAICS code"),
    union_sector: Optional[str] = Query(None, description="Filter by union sector (PRIVATE, FEDERAL)"),
    active_only: bool = Query(True, description="Show only active bargaining relationships"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Fuzzy search using pg_trgm similarity. Catches typos and variations."""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["similarity(e.employer_name, %s) > %s"]
            count_params = [name, threshold]
            
            if state:
                conditions.append("e.state = %s")
                count_params.append(state.upper())
            if affiliation:
                conditions.append("um.aff_abbr = %s")
                count_params.append(affiliation.upper())
            if f_num:
                conditions.append("e.latest_union_fnum::text = %s")
                count_params.append(f_num)
            if naics_2digit:
                conditions.append("LEFT(e.naics, 2) = %s")
                count_params.append(naics_2digit)
            if union_sector and union_sector != 'ALL':
                conditions.append("um.sector = %s")
                count_params.append(union_sector.upper())
            # Note: active_only filter removed - is_active column doesn't exist
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(*) as total FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [name] + count_params + [name, limit, offset]
            
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, similarity(e.employer_name, %s) as match_score,
                       e.city, e.state, e.naics, e.latest_unit_size, e.latest_union_fnum,
                       e.latest_union_name, e.latitude, e.longitude, um.aff_abbr,
                       ns.sector_name as naics_sector_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE {where_clause}
                ORDER BY similarity(e.employer_name, %s) DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)
            
            return {"search_term": name, "threshold": threshold, "total": total, "employers": cur.fetchall()}

@app.get("/api/search/unions")
def fuzzy_search_unions(
    name: str = Query(...),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    limit: int = Query(50, le=500)
):
    """Fuzzy search for unions."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT f_num, union_name, similarity(union_name, %s) as match_score,
                       aff_abbr, city, state, members, sector, f7_employer_count
                FROM unions_master WHERE similarity(union_name, %s) > %s
                ORDER BY similarity(union_name, %s) DESC, members DESC NULLS LAST LIMIT %s
            """, [name, name, threshold, name, limit])
            return {"search_term": name, "threshold": threshold, "unions": cur.fetchall()}


# ============================================================================
# NORMALIZED SEARCH (Phase 2)
# ============================================================================

@app.get("/api/employers/normalized-search")
def normalized_search_employers(
    name: str = Query(..., description="Employer name to search"),
    threshold: float = Query(0.35, ge=0.1, le=1.0),
    state: Optional[str] = None,
    affiliation: Optional[str] = Query(None, description="Filter by union affiliation"),
    f_num: Optional[str] = Query(None, description="Filter by specific union f_num"),
    naics_2digit: Optional[str] = Query(None, description="Filter by 2-digit NAICS code"),
    union_sector: Optional[str] = Query(None, description="Filter by union sector"),
    active_only: bool = Query(True, description="Show only active bargaining relationships"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """NORMALIZED + FUZZY search. Strips Inc/LLC/Corp and expands abbreviations."""
    normalized_search = normalize_for_comparison(name, 'employer')
    
    norm_sql = """LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(e.employer_name, '^[Tt]he\\s+', ''),
        ',?\\s*(Inc\\.?|LLC|Corp\\.?|Company|Co\\.?|Ltd\\.?|LP|LLP)\\s*$', '', 'gi'
    )))"""
    
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = [f"similarity({norm_sql}, %s) > %s"]
            count_params = [normalized_search, threshold]
            
            if state:
                conditions.append("e.state = %s")
                count_params.append(state.upper())
            if affiliation:
                conditions.append("um.aff_abbr = %s")
                count_params.append(affiliation.upper())
            if f_num:
                conditions.append("e.latest_union_fnum::text = %s")
                count_params.append(f_num)
            if naics_2digit:
                conditions.append("LEFT(e.naics, 2) = %s")
                count_params.append(naics_2digit)
            if union_sector and union_sector != 'ALL':
                conditions.append("um.sector = %s")
                count_params.append(union_sector.upper())
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(*) as total FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [normalized_search] + count_params + [normalized_search, limit, offset]
            
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, {norm_sql} as normalized_name,
                       similarity({norm_sql}, %s) as match_score,
                       e.city, e.state, e.naics, e.latest_unit_size, e.latest_union_fnum,
                       e.latest_union_name, e.latitude, e.longitude, um.aff_abbr,
                       ns.sector_name as naics_sector_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE {where_clause}
                ORDER BY similarity({norm_sql}, %s) DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)
            
            return {
                "search_term": name,
                "normalized_search": normalized_search,
                "threshold": threshold,
                "total": total,
                "employers": cur.fetchall()
            }


@app.get("/api/search/unions-normalized")
def normalized_search_unions(
    name: str = Query(...),
    threshold: float = Query(0.35, ge=0.1, le=1.0),
    limit: int = Query(50, le=500)
):
    """Normalized + fuzzy search for unions."""
    normalized_search = normalize_union(name)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            norm_sql = "LOWER(union_name)"
            
            cur.execute(f"""
                SELECT f_num, union_name, {norm_sql} as normalized_name,
                       similarity({norm_sql}, %s) as match_score,
                       aff_abbr, city, state, members, sector, f7_employer_count
                FROM unions_master
                WHERE similarity({norm_sql}, %s) > %s
                ORDER BY similarity({norm_sql}, %s) DESC, members DESC NULLS LAST LIMIT %s
            """, [normalized_search, normalized_search, threshold, normalized_search, limit])
            
            return {"search_term": name, "normalized_search": normalized_search, "unions": cur.fetchall()}


@app.get("/api/normalize/test")
def test_normalization(name: str = Query(...), entity_type: str = Query("employer")):
    """Test normalization without searching. Useful for debugging."""
    if entity_type == "union":
        return {
            "original": name,
            "normalized": normalize_union(name),
            "local_number": extract_local_number(name)
        }
    else:
        return {
            "original": name,
            "normalized": normalize_employer(name),
            "comparison": normalize_for_comparison(name, 'employer')
        }


# ============================================================================
# DENSITY & STATS
# ============================================================================

@app.get("/api/density/naics/{naics_2digit}")
def get_naics_density(naics_2digit: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT naics_2digit, sector_name, bls_indy_code, bls_indy_name, year, union_density_pct
                FROM v_naics_union_density WHERE naics_2digit = %s
            """, [naics_2digit])
            return {"naics_2digit": naics_2digit, "current": cur.fetchone()}


@app.get("/api/stats/overview")
def get_overview_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            stats = {}
            cur.execute("SELECT COUNT(*) as cnt FROM unions_master")
            stats['total_unions'] = cur.fetchone()['cnt']
            cur.execute("SELECT SUM(members) as total FROM unions_master")
            stats['total_members'] = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as cnt FROM f7_employers_deduped")
            stats['total_employers'] = cur.fetchone()['cnt']
            cur.execute("SELECT SUM(latest_unit_size) as total FROM f7_employers_deduped")
            stats['covered_workers'] = cur.fetchone()['total']
            cur.execute("SELECT COUNT(*) as cnt FROM f7_employers_deduped WHERE latitude IS NOT NULL")
            stats['geocoded_employers'] = cur.fetchone()['cnt']
            return stats

# ============================================================================
# CANONICAL NAME LOOKUP (Phase 4)
# ============================================================================

# ============================================================================
# RAPIDFUZZ BATCH MATCHING (Phase 3)
# ============================================================================

@app.get("/api/employers/normalized-search")
def normalized_search_employers(
    name: str = Query(..., description="Employer name to search"),
    threshold: float = Query(0.35, ge=0.1, le=1.0),
    state: Optional[str] = None,
    affiliation: Optional[str] = Query(None, description="Filter by union affiliation"),
    f_num: Optional[str] = Query(None, description="Filter by specific union f_num"),
    naics_2digit: Optional[str] = Query(None, description="Filter by 2-digit NAICS code"),
    union_sector: Optional[str] = Query(None, description="Filter by union sector"),
    active_only: bool = Query(True, description="Show only active bargaining relationships"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """NORMALIZED + FUZZY search. Strips Inc/LLC/Corp and expands abbreviations."""
    normalized_search = normalize_for_comparison(name, 'employer')
    
    norm_sql = """LOWER(TRIM(REGEXP_REPLACE(
        REGEXP_REPLACE(e.employer_name, '^[Tt]he\\s+', ''),
        ',?\\s*(Inc\\.?|LLC|Corp\\.?|Company|Co\\.?|Ltd\\.?|LP|LLP)\\s*$', '', 'gi'
    )))"""
    
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = [f"similarity({norm_sql}, %s) > %s"]
            count_params = [normalized_search, threshold]
            
            if state:
                conditions.append("e.state = %s")
                count_params.append(state.upper())
            if affiliation:
                conditions.append("um.aff_abbr = %s")
                count_params.append(affiliation.upper())
            if f_num:
                conditions.append("e.latest_union_fnum::text = %s")
                count_params.append(f_num)
            if naics_2digit:
                conditions.append("LEFT(e.naics, 2) = %s")
                count_params.append(naics_2digit)
            if union_sector and union_sector != 'ALL':
                conditions.append("um.sector = %s")
                count_params.append(union_sector.upper())
            # Note: active_only filter removed - is_active column doesn't exist
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(*) as total FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [normalized_search] + count_params + [normalized_search, limit, offset]
            
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, {norm_sql} as normalized_name,
                       similarity({norm_sql}, %s) as match_score,
                       e.city, e.state, e.naics, e.latest_unit_size, e.latest_union_fnum,
                       e.latest_union_name, e.latitude, e.longitude, um.aff_abbr,
                       ns.sector_name as naics_sector_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE {where_clause}
                ORDER BY similarity({norm_sql}, %s) DESC, e.latest_unit_size DESC NULLS LAST
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
# PROJECTIONS ENDPOINTS
# ============================================================================

@app.get("/api/projections/naics/{naics_2digit}")
def get_naics_projections(naics_2digit: str):
    """Get BLS employment projections for a 2-digit NAICS sector."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get sector-level projection (codes ending in 0000)
            cur.execute("""
                SELECT naics_2digit, sector_name, naics_code, industry_title,
                       employment_2024, employment_2034, employment_change, percent_change
                FROM v_naics_projections
                WHERE naics_2digit = %s AND naics_code LIKE %s
                LIMIT 1
            """, [naics_2digit, f"{naics_2digit}%0000"])
            
            sector = cur.fetchone()
            
            if not sector:
                # Try alternative match
                cur.execute("""
                    SELECT naics_2digit, sector_name, naics_code, industry_title,
                           employment_2024, employment_2034, employment_change, percent_change
                    FROM v_naics_projections
                    WHERE naics_2digit = %s
                    ORDER BY naics_code
                    LIMIT 1
                """, [naics_2digit])
                sector = cur.fetchone()
            
            if not sector:
                raise HTTPException(status_code=404, detail=f"No projections found for NAICS {naics_2digit}")
            
            # Get sub-industry projections
            cur.execute("""
                SELECT naics_code, industry_title, employment_2024, employment_2034, 
                       employment_change, percent_change
                FROM v_naics_projections
                WHERE naics_2digit = %s AND naics_code NOT LIKE %s
                ORDER BY employment_2024 DESC NULLS LAST
                LIMIT 10
            """, [naics_2digit, f"{naics_2digit}%0000"])
            
            sub_industries = cur.fetchall()
            
            return {
                "naics_2digit": naics_2digit,
                "sector_name": sector['sector_name'],
                "industry_title": sector['industry_title'],
                "employment_2024": float(sector['employment_2024']) if sector['employment_2024'] else None,
                "employment_2034": float(sector['employment_2034']) if sector['employment_2034'] else None,
                "employment_change": float(sector['employment_change']) if sector['employment_change'] else None,
                "percent_change": float(sector['percent_change']) if sector['percent_change'] else None,
                "sub_industries": sub_industries
            }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "version": "4.2-normalized"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
