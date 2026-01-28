"""
Labor Relations Search API - Updated with local numbers and deduplicated data
Run with: py -m uvicorn labor_search_api_v2:app --reload --port 8000
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

app = FastAPI(
    title="Labor Relations Search API",
    description="Search employers, unions, and labor relations data from DOL filings",
    version="2.0"
)

# Enable CORS for local HTML file access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration - UPDATE PASSWORD
PG_CONFIG = {
    'host': 'localhost',
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'postgres'  # UPDATE THIS
}

def get_db():
    return psycopg2.connect(**PG_CONFIG, cursor_factory=RealDictCursor)


# ============== AFFILIATIONS ==============

@app.get("/affiliations")
def list_affiliations():
    """List all affiliations with summary stats"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT affiliation, affiliation_name, local_count, 
                       total_members, total_assets, total_receipts,
                       f7_employer_count, f7_total_workers
                FROM v_affiliation_summary
                WHERE local_count > 0
                ORDER BY total_members DESC NULLS LAST
            """)
            return cur.fetchall()


# ============== EMPLOYER SEARCH ==============

@app.get("/employers/search")
def search_employers(
    affiliation: Optional[str] = None,
    union_file_number: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    employer_name: Optional[str] = None,
    min_unit_size: Optional[int] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search F-7 employers with various filters"""
    conditions = []
    params = []
    
    if affiliation:
        conditions.append("affiliation = %s")
        params.append(affiliation.upper())
    if union_file_number:
        conditions.append("union_file_number = %s")
        params.append(union_file_number)
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    if city:
        conditions.append("LOWER(city) LIKE %s")
        params.append(f"%{city.lower()}%")
    if employer_name:
        conditions.append("LOWER(employer_name) LIKE %s")
        params.append(f"%{employer_name.lower()}%")
    if min_unit_size:
        conditions.append("bargaining_unit_size >= %s")
        params.append(min_unit_size)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get total count
            cur.execute(f"SELECT COUNT(*) as cnt FROM v_employer_search {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            # Get results
            cur.execute(f"""
                SELECT employer_id, employer_name, city, state, 
                       bargaining_unit_size, latest_notice_date,
                       union_file_number, union_name_f7, union_name_lm,
                       affiliation, affiliation_name,
                       latitude, longitude
                FROM v_employer_search
                {where_clause}
                ORDER BY bargaining_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {
                "total_count": total,
                "limit": limit,
                "offset": offset,
                "results": cur.fetchall()
            }


@app.get("/employers/{employer_id}")
def get_employer(employer_id: str):
    """Get details for a specific employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_employer_search 
                WHERE employer_id = %s
            """, [employer_id])
            result = cur.fetchone()
            if not result:
                return {"error": "Employer not found"}
            return result


# ============== UNION LOCAL SEARCH ==============

@app.get("/unions/locals/search")
def search_union_locals(
    affiliation: Optional[str] = None,
    state: Optional[str] = None,
    union_name: Optional[str] = None,
    local_number: Optional[str] = None,
    min_members: Optional[int] = None,
    has_employers: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search union locals with various filters"""
    conditions = []
    params = []
    
    if affiliation:
        conditions.append("affiliation = %s")
        params.append(affiliation.upper())
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    if union_name:
        conditions.append("(LOWER(union_name) LIKE %s OR LOWER(local_display_name) LIKE %s)")
        params.append(f"%{union_name.lower()}%")
        params.append(f"%{union_name.lower()}%")
    if local_number:
        conditions.append("local_number = %s")
        params.append(local_number)
    if min_members:
        conditions.append("members >= %s")
        params.append(min_members)
    if has_employers:
        conditions.append("f7_employer_count > 0")
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get total count
            cur.execute(f"SELECT COUNT(*) as cnt FROM v_union_local_search {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            # Get results
            cur.execute(f"""
                SELECT file_number, union_name, local_display_name, local_number,
                       affiliation, affiliation_name, desig_name,
                       city, state, members, total_assets, total_receipts,
                       f7_employer_count, f7_total_workers
                FROM v_union_local_search
                {where_clause}
                ORDER BY members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {
                "total_count": total,
                "limit": limit,
                "offset": offset,
                "results": cur.fetchall()
            }


@app.get("/unions/locals/{file_number}")
def get_union_local(file_number: str):
    """Get detailed info for a union local including financial history and employers"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Current year data from view
            cur.execute("""
                SELECT file_number, union_name, local_display_name, local_number,
                       affiliation, affiliation_name, desig_name,
                       city, state, members, total_assets, total_receipts, total_disbursements,
                       f7_employer_count, f7_total_workers
                FROM v_union_local_search
                WHERE file_number = %s
            """, [file_number])
            current = cur.fetchone()
            
            if not current:
                return {"error": "Union local not found"}
            
            # Historical data (last 5 years)
            cur.execute("""
                SELECT rpt_id, f_num as file_number, union_name, aff_abbr as affiliation,
                       TRIM(desig_name) as desig_name, TRIM(desig_num) as local_number,
                       city, state, yr_covered as fiscal_year, members,
                       ttl_assets as total_assets, ttl_liabilities as total_liabilities,
                       ttl_receipts as total_receipts, ttl_disbursements as total_disbursements,
                       CASE WHEN ttl_assets > 0 
                            THEN ROUND(100.0 * ttl_liabilities / ttl_assets, 1)
                            ELSE 0 END as debt_ratio_pct,
                       CASE WHEN members > 0 
                            THEN ROUND(ttl_assets::numeric / members, 0)
                            ELSE 0 END as assets_per_member,
                       CASE WHEN members > 0 
                            THEN ROUND(ttl_receipts::numeric / members, 0)
                            ELSE 0 END as receipts_per_member
                FROM lm_data
                WHERE f_num = %s
                ORDER BY yr_covered DESC
                LIMIT 5
            """, [file_number])
            history = cur.fetchall()
            
            # Get employers from deduplicated table
            cur.execute("""
                SELECT employer_id, employer_name, city, state, 
                       latest_unit_size as bargaining_unit_size, latest_notice_date
                FROM f7_employers_deduped
                WHERE latest_union_fnum = %s
                ORDER BY latest_unit_size DESC NULLS LAST
                LIMIT 50
            """, [file_number])
            employers = cur.fetchall()
            
            return {
                "current": current,
                "history": history,
                "employers": employers,
                "employer_count": current['f7_employer_count'] if current else 0
            }


@app.get("/unions/locals/{file_number}/employers")
def get_union_employers(file_number: str, limit: int = Query(100, le=500), offset: int = 0):
    """Get all employers for a union local"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, city, state,
                       latest_unit_size as bargaining_unit_size, latest_notice_date,
                       latitude, longitude
                FROM f7_employers_deduped
                WHERE latest_union_fnum = %s
                ORDER BY latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, [file_number, limit, offset])
            return cur.fetchall()


# ============== STATE ENDPOINTS ==============

@app.get("/states")
def list_states():
    """List all states with union density and F-7 employer counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    s.state_abbr,
                    s.state,
                    us.pct_members as union_density,
                    us.members_thousands * 1000 as union_members,
                    COALESCE(f7.employer_count, 0) as f7_employers,
                    COALESCE(f7.union_count, 0) as unions_with_employers
                FROM state_abbrev s
                LEFT JOIN unionstats_state us 
                    ON s.state_name = us.state 
                    AND us.year = 2024 
                    AND us.sector = 'Total'
                LEFT JOIN (
                    SELECT state, 
                           COUNT(*) as employer_count,
                           COUNT(DISTINCT latest_union_fnum) as union_count
                    FROM f7_employers_deduped
                    GROUP BY state
                ) f7 ON s.state_abbr = f7.state
                WHERE s.state_abbr IS NOT NULL
                ORDER BY union_density DESC NULLS LAST
            """)
            return cur.fetchall()


@app.get("/states/{state_abbr}/employers")
def get_state_employers(
    state_abbr: str, 
    affiliation: Optional[str] = None,
    limit: int = Query(50, le=500), 
    offset: int = 0
):
    """Get employers in a state"""
    conditions = ["state = %s"]
    params = [state_abbr.upper()]
    
    if affiliation:
        conditions.append("affiliation = %s")
        params.append(affiliation.upper())
    
    where_clause = "WHERE " + " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT employer_id, employer_name, city, state,
                       bargaining_unit_size, union_name_f7, affiliation, affiliation_name
                FROM v_employer_search
                {where_clause}
                ORDER BY bargaining_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {
                "state": state_abbr.upper(),
                "results": cur.fetchall()
            }


# ============== UTILITY ENDPOINTS ==============

@app.get("/")
def root():
    return {
        "name": "Labor Relations Search API",
        "version": "2.0",
        "description": "Search 71,000+ deduplicated employers and union locals",
        "endpoints": {
            "/affiliations": "List all union affiliations",
            "/employers/search": "Search employers",
            "/unions/locals/search": "Search union locals",
            "/states": "List states with density data",
            "/docs": "Interactive API documentation"
        }
    }


@app.get("/health")
def health_check():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
                emp_count = cur.fetchone()['count']
                cur.execute("SELECT COUNT(*) FROM lm_data WHERE yr_covered = 2024")
                union_count = cur.fetchone()['count']
        return {
            "status": "healthy",
            "database": "connected",
            "f7_employers_deduped": emp_count,
            "lm_unions_2024": union_count
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
