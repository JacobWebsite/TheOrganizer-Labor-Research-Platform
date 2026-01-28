"""
VR (Voluntary Recognition) API Endpoints - Checkpoint 6A (Fixed)
Routes ordered correctly - specific routes before wildcard routes

Run with: py -m uvicorn vr_api_endpoints:app --reload --port 8002
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
from datetime import date

app = FastAPI(
    title="Voluntary Recognition API",
    version="1.0",
    description="API for NLRB Voluntary Recognition data with employer/union linkages"
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
# ROOT - API Info
# ============================================================================

@app.get("/")
def root():
    """API root - shows available endpoints"""
    return {
        "api": "Voluntary Recognition API",
        "version": "1.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "vr_summary": "/api/vr/stats/summary",
            "vr_by_year": "/api/vr/stats/by-year",
            "vr_by_state": "/api/vr/stats/by-state",
            "vr_by_affiliation": "/api/vr/stats/by-affiliation",
            "vr_search": "/api/vr/search",
            "vr_map": "/api/vr/map",
            "vr_new_employers": "/api/vr/new-employers",
            "vr_pipeline": "/api/vr/pipeline",
            "vr_case_detail": "/api/vr/{case_number}",
            "organizing_summary": "/api/organizing/summary",
            "organizing_by_state": "/api/organizing/by-state"
        }
    }


# ============================================================================
# VR STATISTICS (specific routes first)
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


# ============================================================================
# VR MAP DATA
# ============================================================================

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
                SELECT 
                    id, vr_case_number, employer_name,
                    city, state, affiliation,
                    num_employees, year,
                    latitude, longitude
                FROM v_vr_map_data
                WHERE {where_clause}
                ORDER BY num_employees DESC NULLS LAST
                LIMIT %s
            """, params + [limit])
            
            return {"features": cur.fetchall()}


# ============================================================================
# NEW EMPLOYERS (Pipeline)
# ============================================================================

@app.get("/api/vr/new-employers")
def get_new_employers(
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
            cur.execute(f"""
                SELECT COUNT(*) FROM v_vr_new_employers
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            cur.execute(f"""
                SELECT *
                FROM v_vr_new_employers
                WHERE {where_clause}
                ORDER BY num_employees DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {
                "total": total,
                "description": "Employers with voluntary recognition but not yet in F-7 filings",
                "employers": cur.fetchall()
            }


# ============================================================================
# VR TO F7 PIPELINE
# ============================================================================

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
                SELECT 
                    sequence_type,
                    COUNT(*) as count,
                    AVG(days_vr_to_f7)::int as avg_days,
                    MIN(days_vr_to_f7) as min_days,
                    MAX(days_vr_to_f7) as max_days
                FROM v_vr_to_f7_pipeline
                GROUP BY sequence_type
            """)
            summary = cur.fetchall()
            
            cur.execute(f"""
                SELECT *
                FROM v_vr_to_f7_pipeline
                WHERE {where_clause}
                ORDER BY vr_date DESC
                LIMIT %s
            """, params + [limit])
            
            return {
                "summary": summary,
                "records": cur.fetchall()
            }


# ============================================================================
# VR SEARCH
# ============================================================================

@app.get("/api/vr/search")
def search_vr(
    employer: Optional[str] = Query(None, description="Employer name (contains match)"),
    union: Optional[str] = Query(None, description="Union name (contains match)"),
    affiliation: Optional[str] = Query(None, description="Union affiliation (e.g., SEIU, IBT)"),
    state: Optional[str] = Query(None, description="State abbreviation"),
    city: Optional[str] = Query(None, description="City name"),
    region: Optional[int] = Query(None, description="NLRB region number"),
    year: Optional[int] = Query(None, description="Year of VR request"),
    date_from: Optional[date] = Query(None, description="Start date"),
    date_to: Optional[date] = Query(None, description="End date"),
    employer_matched: Optional[bool] = Query(None, description="Has matched F7 employer"),
    union_matched: Optional[bool] = Query(None, description="Has matched OLMS union"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    sort_by: str = Query("date", description="Sort by: date, employees, employer")
):
    """Search Voluntary Recognition cases with comprehensive filtering."""
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
    if date_from:
        conditions.append("vr.date_vr_request_received >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("vr.date_vr_request_received <= %s")
        params.append(date_to)
    if employer_matched is not None:
        conditions.append("vr.matched_employer_id IS NOT NULL" if employer_matched else "vr.matched_employer_id IS NULL")
    if union_matched is not None:
        conditions.append("vr.matched_union_fnum IS NOT NULL" if union_matched else "vr.matched_union_fnum IS NULL")
    
    where_clause = " AND ".join(conditions)
    sort_map = {"date": "vr.date_vr_request_received DESC NULLS LAST", "employees": "vr.num_employees DESC NULLS LAST", "employer": "vr.employer_name_normalized ASC"}
    order_by = sort_map.get(sort_by, sort_map["date"])
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM nlrb_voluntary_recognition vr WHERE {where_clause}", params)
            total = cur.fetchone()['count']
            
            cur.execute(f"""
                SELECT 
                    vr.id, vr.vr_case_number, vr.region,
                    vr.employer_name_normalized as employer_name,
                    vr.unit_city as city, vr.unit_state as state,
                    vr.date_vr_request_received, vr.date_voluntary_recognition,
                    vr.union_name_normalized as union_name,
                    vr.extracted_affiliation as affiliation,
                    vr.extracted_local_number as local_number,
                    vr.num_employees, vr.unit_description, vr.r_case_number,
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


# ============================================================================
# COMBINED ORGANIZING ACTIVITY
# ============================================================================

@app.get("/api/organizing/summary")
def get_organizing_summary(year_from: int = 2020, year_to: int = 2025):
    """Get combined organizing activity summary (Elections + VR)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_organizing_by_year
                WHERE year >= %s AND year <= %s
                ORDER BY year
            """, [year_from, year_to])
            return {"years": cur.fetchall()}


@app.get("/api/organizing/by-state")
def get_organizing_by_state():
    """Get combined organizing activity by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_organizing_by_state ORDER BY total_events DESC")
            return {"states": cur.fetchall()}


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
def health_check():
    """API health check"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM nlrb_voluntary_recognition")
                vr_count = cur.fetchone()['count']
        return {"status": "healthy", "database": "connected", "vr_records": vr_count, "version": "1.0-vr"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ============================================================================
# VR CASE DETAIL (wildcard route LAST)
# ============================================================================

@app.get("/api/vr/{case_number}")
def get_vr_detail(case_number: str):
    """Get detailed info for a specific VR case"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    vr.*, nr.region_name,
                    f7.employer_name as f7_employer_name, f7.city as f7_city, f7.state as f7_state,
                    f7.naics as f7_naics, f7.latitude, f7.longitude,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
