"""
Labor Relations Platform API v5.0 - Integrated with NLRB Data
Run with: py -m uvicorn labor_api_v5:app --reload --port 8001
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List

app = FastAPI(
    title="Labor Relations Research API", 
    version="5.0",
    description="Integrated platform: OLMS union data, F-7 employers, BLS density, and NLRB elections"
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


# ============================================================================
# EMPLOYER SEARCH
# ============================================================================

@app.get("/api/employers/search")
def search_employers(
    name: Optional[str] = None,
    state: Optional[str] = None,
    naics: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    has_nlrb: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search employers with filters"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if name:
                conditions.append("e.employer_name ILIKE %s")
                params.append(f"%{name}%")
            if state:
                conditions.append("e.state = %s")
                params.append(state.upper())
            if naics:
                conditions.append("e.naics LIKE %s")
                params.append(f"{naics}%")
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            
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
                    e.latitude, e.longitude, um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
                ORDER BY e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "employers": cur.fetchall()}


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


# ============================================================================
# UNION SEARCH
# ============================================================================

@app.get("/api/unions/search")
def search_unions(
    name: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    min_members: Optional[int] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search unions with filters"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if name:
                conditions.append("union_name ILIKE %s")
                params.append(f"%{name}%")
            if aff_abbr:
                conditions.append("aff_abbr = %s")
                params.append(aff_abbr.upper())
            if sector:
                conditions.append("sector = %s")
                params.append(sector.upper())
            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if min_members:
                conditions.append("members >= %s")
                params.append(min_members)
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"SELECT COUNT(*) FROM unions_master WHERE {where_clause}", params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT f_num, union_name, aff_abbr, members, city, state, sector,
                    f7_employer_count, f7_total_workers
                FROM unions_master
                WHERE {where_clause}
                ORDER BY members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "unions": cur.fetchall()}


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
                SELECT f_num, union_name, city, state, members, f7_employer_count
                FROM unions_master
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
            
            return {"total": total, "limit": limit, "offset": offset, "elections": cur.fetchall()}


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
            
            # Employers
            cur.execute("""
                SELECT COUNT(*) as total_employers, SUM(latest_unit_size) as covered_workers,
                    COUNT(DISTINCT state) as states
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
        return {"status": "healthy", "database": "connected", "version": "5.1-vr-integrated", "vr_records": vr_count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
