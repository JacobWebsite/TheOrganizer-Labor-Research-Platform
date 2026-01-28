"""
Unified Labor Relations API v3 - FIXED
Run with: py -m uvicorn labor_api_v3:app --reload --port 8000
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

app = FastAPI(title="Unified Labor Relations API", version="3.0")

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
# AFFILIATIONS
# ============================================================================

@app.get("/api/affiliations")
def list_affiliations():
    """List all affiliations with summary stats"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    aff_abbr,
                    MAX(union_name) as aff_name,
                    COUNT(*) as local_count,
                    SUM(members) as total_members,
                    COUNT(*) FILTER (WHERE has_f7_employers) as locals_with_employers,
                    SUM(f7_employer_count) as total_employers
                FROM unions_master
                WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
                GROUP BY aff_abbr
                HAVING COUNT(*) >= 5
                ORDER BY SUM(members) DESC NULLS LAST
            """)
            return {"affiliations": cur.fetchall()}


# ============================================================================
# UNION SEARCH
# ============================================================================

@app.get("/api/unions/search")
def search_unions(
    affiliation: Optional[str] = None,
    state: Optional[str] = None,
    name: Optional[str] = None,
    has_employers: Optional[bool] = None,
    min_members: Optional[int] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search union locals"""
    conditions = ["1=1"]
    params = []
    
    if affiliation:
        conditions.append("um.aff_abbr = %s")
        params.append(affiliation.upper())
    if state:
        conditions.append("um.state = %s")
        params.append(state.upper())
    if name:
        conditions.append("LOWER(um.union_name) LIKE %s")
        params.append(f"%{name.lower()}%")
    if has_employers:
        conditions.append("um.has_f7_employers = true")
    if min_members:
        conditions.append("um.members >= %s")
        params.append(min_members)
    
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get total count
            cur.execute(f"SELECT COUNT(*) as cnt FROM unions_master um WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            # Get results with NLRB counts
            cur.execute(f"""
                SELECT 
                    um.f_num,
                    um.union_name,
                    um.aff_abbr,
                    um.local_number,
                    um.desig_name,
                    um.members,
                    um.city,
                    um.state,
                    um.has_f7_employers,
                    um.f7_employer_count,
                    um.f7_total_workers,
                    COALESCE(nlrb.case_count, 0) as nlrb_case_count,
                    COALESCE(nlrb.election_count, 0) as nlrb_election_count
                FROM unions_master um
                LEFT JOIN (
                    SELECT 
                        x.olms_f_num::text as f_num,
                        COUNT(DISTINCT c.case_number) as case_count,
                        COUNT(DISTINCT e.election_id) as election_count
                    FROM nlrb_union_xref x
                    JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
                    LEFT JOIN nlrb_cases c ON p.case_number = c.case_number
                    LEFT JOIN nlrb_elections e ON c.case_number = e.case_number
                    WHERE x.olms_f_num IS NOT NULL
                    GROUP BY x.olms_f_num
                ) nlrb ON um.f_num = nlrb.f_num
                WHERE {where_clause}
                ORDER BY um.members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            return {
                "total_count": total,
                "limit": limit,
                "offset": offset,
                "results": cur.fetchall()
            }


# ============================================================================
# UNION DETAIL
# ============================================================================

@app.get("/api/unions/{f_num}")
def get_union_detail(f_num: str):
    """Get full details for a union"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Basic union info
            cur.execute("""
                SELECT f_num, union_name, aff_abbr, local_number, desig_name, members, 
                       city, state, sector,
                       has_f7_employers, f7_employer_count, f7_total_workers
                FROM unions_master WHERE f_num = %s
            """, [f_num])
            
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")
            
            # Get LM financial summary (correct column names)
            cur.execute("""
                SELECT 
                    yr_covered,
                    ttl_assets as total_assets,
                    ttl_liabilities as total_liabilities,
                    ttl_receipts as total_receipts,
                    ttl_disbursements as total_disbursements,
                    (ttl_assets - ttl_liabilities) as net_assets
                FROM lm_data
                WHERE f_num = %s
                ORDER BY yr_covered DESC
                LIMIT 5
            """, [f_num])
            lm_data = cur.fetchall()
            
            # Get NLRB summary
            cur.execute("""
                SELECT 
                    COUNT(DISTINCT c.case_number) as total_cases,
                    COUNT(DISTINCT e.election_id) as total_elections,
                    COUNT(DISTINCT CASE WHEN c.case_type = 'CA' THEN c.case_number END) as employer_ulp_cases,
                    COUNT(DISTINCT CASE WHEN c.case_type = 'CB' THEN c.case_number END) as union_ulp_cases,
                    COUNT(DISTINCT CASE WHEN c.case_type IN ('RC', 'RD', 'RM') THEN c.case_number END) as representation_cases
                FROM nlrb_union_xref x
                JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
                JOIN nlrb_cases c ON p.case_number = c.case_number
                LEFT JOIN nlrb_elections e ON c.case_number = e.case_number
                WHERE x.olms_f_num = %s::int
            """, [f_num])
            nlrb_summary = cur.fetchone()
            
            return {
                "union": union,
                "lm_financial": lm_data,
                "nlrb_summary": nlrb_summary
            }


# ============================================================================
# UNION EMPLOYERS (F-7)
# ============================================================================

@app.get("/api/unions/{f_num}/employers")
def get_union_employers(f_num: str, limit: int = Query(100, le=500), offset: int = 0):
    """Get F-7 employers for a union"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as cnt FROM f7_employers_deduped
                WHERE latest_union_fnum = %s::int
            """, [f_num])
            total = cur.fetchone()['cnt']
            
            cur.execute("""
                SELECT 
                    employer_id, employer_name, city, state, zip,
                    latest_unit_size as bargaining_unit_size,
                    latest_notice_date, latitude, longitude
                FROM f7_employers_deduped
                WHERE latest_union_fnum = %s::int
                ORDER BY latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, [f_num, limit, offset])
            
            return {"total_count": total, "results": cur.fetchall()}


# ============================================================================
# UNION NLRB ELECTIONS
# ============================================================================

@app.get("/api/unions/{f_num}/elections")
def get_union_elections(f_num: str, limit: int = Query(50, le=200), offset: int = 0):
    """Get NLRB elections for a union"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get elections with tally data
            cur.execute("""
                SELECT 
                    e.election_id,
                    e.case_number,
                    e.election_date,
                    e.tally_type,
                    e.ballot_type,
                    e.unit_size,
                    er.total_ballots_counted,
                    er.void_ballots,
                    er.certified_union,
                    -- Employer info
                    emp.participant_name as employer_name,
                    emp.city as employer_city,
                    emp.state as employer_state
                FROM nlrb_union_xref x
                JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
                JOIN nlrb_cases c ON p.case_number = c.case_number
                JOIN nlrb_elections e ON c.case_number = e.case_number
                LEFT JOIN nlrb_election_results er ON e.election_id = er.election_id
                LEFT JOIN nlrb_participants emp ON c.case_number = emp.case_number AND emp.subtype = 'Employer'
                WHERE x.olms_f_num = %s::int
                ORDER BY e.election_date DESC
                LIMIT %s OFFSET %s
            """, [f_num, limit, offset])
            
            elections_raw = cur.fetchall()
            
            # Now get vote tallies for each election
            elections = []
            for e in elections_raw:
                election = dict(e)
                # Get tallies
                cur.execute("""
                    SELECT option, votes FROM nlrb_tallies 
                    WHERE election_id = %s
                """, [e['election_id']])
                tallies = cur.fetchall()
                
                votes_for = 0
                votes_against = 0
                for t in tallies:
                    opt = (t['option'] or '').lower()
                    if 'no' in opt or 'against' in opt:
                        votes_against += t['votes'] or 0
                    else:
                        votes_for += t['votes'] or 0
                
                election['votes_for_union'] = votes_for
                election['votes_against'] = votes_against
                
                if votes_for > votes_against:
                    election['outcome'] = 'Won'
                elif votes_for < votes_against:
                    election['outcome'] = 'Lost'
                else:
                    election['outcome'] = 'Unknown'
                    
                elections.append(election)
            
            # Get summary stats
            cur.execute("""
                SELECT COUNT(DISTINCT e.election_id) as total_elections
                FROM nlrb_union_xref x
                JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
                JOIN nlrb_cases c ON p.case_number = c.case_number
                JOIN nlrb_elections e ON c.case_number = e.case_number
                WHERE x.olms_f_num = %s::int
            """, [f_num])
            total = cur.fetchone()['total_elections']
            
            wins = sum(1 for e in elections if e.get('outcome') == 'Won')
            losses = sum(1 for e in elections if e.get('outcome') == 'Lost')
            
            return {
                "summary": {"total_elections": total, "wins": wins, "losses": losses},
                "elections": elections
            }


# ============================================================================
# UNION NLRB CASES
# ============================================================================

@app.get("/api/unions/{f_num}/cases")
def get_union_cases(f_num: str, case_type: Optional[str] = None, limit: int = Query(50, le=200), offset: int = 0):
    """Get NLRB cases for a union"""
    conditions = ["x.olms_f_num = %s::int"]
    params = [f_num]
    
    if case_type:
        conditions.append("c.case_type = %s")
        params.append(case_type.upper())
    
    where_clause = " AND ".join(conditions)
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT
                    c.case_number, c.case_type, c.case_name,
                    c.date_filed, c.date_closed, c.status,
                    c.city, c.state,
                    emp.participant_name as employer_name
                FROM nlrb_union_xref x
                JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
                JOIN nlrb_cases c ON p.case_number = c.case_number
                LEFT JOIN nlrb_participants emp ON c.case_number = emp.case_number AND emp.subtype = 'Employer'
                WHERE {where_clause}
                ORDER BY c.date_filed DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            cases = cur.fetchall()
            
            # Get case type breakdown
            cur.execute(f"""
                SELECT c.case_type, COUNT(DISTINCT c.case_number) as count
                FROM nlrb_union_xref x
                JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
                JOIN nlrb_cases c ON p.case_number = c.case_number
                WHERE x.olms_f_num = %s::int
                GROUP BY c.case_type ORDER BY count DESC
            """, [f_num])
            
            return {"case_type_breakdown": cur.fetchall(), "cases": cases}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
