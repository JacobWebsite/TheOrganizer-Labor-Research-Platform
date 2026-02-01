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

            # Get recommended organizing targets (for AFSCME unions)
            recommended_targets = []
            if union.get('aff_abbr') == 'AFSCME':
                # Get industries of current employers
                cur.execute("""
                    SELECT DISTINCT e990.industry_category
                    FROM f7_employers_deduped f7
                    JOIN employer_990_matches em ON f7.employer_id = em.f7_employer_id
                    JOIN employers_990 e990 ON em.employer_990_id = e990.id
                    WHERE f7.latest_union_fnum = %s
                    AND e990.industry_category IS NOT NULL
                """, [f_num])
                industries = [row['industry_category'] for row in cur.fetchall()]

                # Find matching targets
                cur.execute("""
                    SELECT
                        ot.id, ot.employer_name, ot.city, ot.state,
                        ot.employee_count, ot.industry_category,
                        ot.total_govt_funding, ot.priority_score, ot.priority_tier
                    FROM organizing_targets ot
                    WHERE ot.has_existing_afscme_contract = FALSE
                    AND ot.state = %s
                    AND ot.priority_score > 30
                    ORDER BY ot.priority_score DESC
                    LIMIT 10
                """, [union.get('state') or 'NY'])
                recommended_targets = cur.fetchall()

            return {
                "union": union,
                "top_employers": employers,
                "nlrb_elections": elections,
                "nlrb_summary": {
                    "total_elections": len(elections),
                    "wins": sum(1 for e in elections if e['union_won']),
                    "losses": sum(1 for e in elections if e['union_won'] is False),
                    "win_rate": round(100.0 * sum(1 for e in elections if e['union_won']) / max(len(elections), 1), 1)
                },
                "recommended_targets": recommended_targets
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
# EPI UNION MEMBERSHIP - Historical Density Data
# ============================================================================

@app.get("/api/epi/national-trends")
def get_epi_national_trends(
    start_year: int = Query(1983, ge=1977),
    end_year: int = Query(2024, le=2030)
):
    """Get national union membership trends over time"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    year,
                    MAX(CASE WHEN measure = 'Number of union members' THEN value END) as members,
                    MAX(CASE WHEN measure = 'Number represented by a union' THEN value END) as covered,
                    MAX(CASE WHEN measure = 'Share in a union' THEN value END) * 100 as membership_rate,
                    MAX(CASE WHEN measure = 'Share represented by a union' THEN value END) * 100 as coverage_rate
                FROM epi_union_membership
                WHERE geo_type = 'national'
                AND year BETWEEN %s AND %s
                AND demographic_group IS NULL
                GROUP BY year
                ORDER BY year
            """, [start_year, end_year])
            results = cur.fetchall()
            return {
                "start_year": start_year,
                "end_year": end_year,
                "trends": [
                    {
                        "year": r["year"],
                        "members": int(r["members"]) if r["members"] else None,
                        "covered": int(r["covered"]) if r["covered"] else None,
                        "membership_rate": round(float(r["membership_rate"]), 1) if r["membership_rate"] else None,
                        "coverage_rate": round(float(r["coverage_rate"]), 1) if r["coverage_rate"] else None
                    }
                    for r in results
                ]
            }


@app.get("/api/epi/by-state")
def get_epi_by_state(
    year: int = Query(2023),
    min_members: int = Query(0)
):
    """Get union membership by state for a given year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    geo_name as state,
                    MAX(CASE WHEN measure = 'Number of union members' THEN value END) as members,
                    MAX(CASE WHEN measure = 'Number represented by a union' THEN value END) as covered,
                    MAX(CASE WHEN measure = 'Share in a union' THEN value END) * 100 as membership_rate,
                    MAX(CASE WHEN measure = 'Share represented by a union' THEN value END) * 100 as coverage_rate
                FROM epi_union_membership
                WHERE geo_type = 'state'
                AND year = %s
                AND demographic_group IS NULL
                GROUP BY geo_name
                HAVING MAX(CASE WHEN measure = 'Number of union members' THEN value END) >= %s
                ORDER BY MAX(CASE WHEN measure = 'Number of union members' THEN value END) DESC
            """, [year, min_members])
            results = cur.fetchall()
            return {
                "year": year,
                "states": [
                    {
                        "state": r["state"],
                        "members": int(r["members"]) if r["members"] else None,
                        "covered": int(r["covered"]) if r["covered"] else None,
                        "membership_rate": round(float(r["membership_rate"]), 1) if r["membership_rate"] else None,
                        "coverage_rate": round(float(r["coverage_rate"]), 1) if r["coverage_rate"] else None
                    }
                    for r in results
                ]
            }


@app.get("/api/epi/state-history/{state}")
def get_epi_state_history(
    state: str,
    start_year: int = Query(1983, ge=1977),
    end_year: int = Query(2024, le=2030)
):
    """Get historical union membership for a specific state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    year,
                    geo_name as state,
                    MAX(CASE WHEN measure = 'Number of union members' THEN value END) as members,
                    MAX(CASE WHEN measure = 'Number represented by a union' THEN value END) as covered,
                    MAX(CASE WHEN measure = 'Share in a union' THEN value END) * 100 as membership_rate,
                    MAX(CASE WHEN measure = 'Share represented by a union' THEN value END) * 100 as coverage_rate
                FROM epi_union_membership
                WHERE geo_type = 'state'
                AND LOWER(geo_name) LIKE LOWER(%s)
                AND year BETWEEN %s AND %s
                AND demographic_group IS NULL
                GROUP BY year, geo_name
                ORDER BY year
            """, [f"%{state}%", start_year, end_year])
            results = cur.fetchall()

            if not results:
                raise HTTPException(status_code=404, detail=f"No data found for state: {state}")

            return {
                "state": results[0]["state"] if results else state,
                "history": [
                    {
                        "year": r["year"],
                        "members": int(r["members"]) if r["members"] else None,
                        "covered": int(r["covered"]) if r["covered"] else None,
                        "membership_rate": round(float(r["membership_rate"]), 1) if r["membership_rate"] else None,
                        "coverage_rate": round(float(r["coverage_rate"]), 1) if r["coverage_rate"] else None
                    }
                    for r in results
                ]
            }


@app.get("/api/epi/by-region")
def get_epi_by_region(year: int = Query(2023)):
    """Get union membership by Census region"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    geo_name as region,
                    MAX(CASE WHEN measure = 'Number of union members' THEN value END) as members,
                    MAX(CASE WHEN measure = 'Share in a union' THEN value END) * 100 as membership_rate
                FROM epi_union_membership
                WHERE geo_type = 'region'
                AND year = %s
                AND demographic_group IS NULL
                GROUP BY geo_name
                ORDER BY MAX(CASE WHEN measure = 'Number of union members' THEN value END) DESC
            """, [year])
            results = cur.fetchall()
            return {
                "year": year,
                "regions": [
                    {
                        "region": r["region"],
                        "members": int(r["members"]) if r["members"] else None,
                        "membership_rate": round(float(r["membership_rate"]), 1) if r["membership_rate"] else None
                    }
                    for r in results
                ]
            }


@app.get("/api/epi/compare-states")
def get_epi_compare_states(
    states: str = Query(..., description="Comma-separated state names"),
    start_year: int = Query(2000),
    end_year: int = Query(2024)
):
    """Compare union membership trends across multiple states"""
    state_list = [s.strip() for s in states.split(",")]

    with get_db() as conn:
        with conn.cursor() as cur:
            # Build LIKE conditions for each state
            like_conditions = " OR ".join(["LOWER(geo_name) LIKE LOWER(%s)" for _ in state_list])
            params = [f"%{s}%" for s in state_list] + [start_year, end_year]

            cur.execute(f"""
                SELECT
                    year,
                    geo_name as state,
                    MAX(CASE WHEN measure = 'Number of union members' THEN value END) as members,
                    MAX(CASE WHEN measure = 'Share in a union' THEN value END) * 100 as membership_rate
                FROM epi_union_membership
                WHERE geo_type = 'state'
                AND ({like_conditions})
                AND year BETWEEN %s AND %s
                AND demographic_group IS NULL
                GROUP BY year, geo_name
                ORDER BY geo_name, year
            """, params)

            results = cur.fetchall()

            # Pivot by state
            by_state = {}
            for r in results:
                st = r['state']
                if st not in by_state:
                    by_state[st] = []
                by_state[st].append({
                    'year': r['year'],
                    'members': int(r['members']) if r['members'] else None,
                    'rate': round(float(r['membership_rate']), 1) if r['membership_rate'] else None
                })

            return {
                "states_requested": state_list,
                "states_found": list(by_state.keys()),
                "data": by_state
            }


# ============================================================================
# NLRB PARTICIPANTS - Enhanced Employer/Union Matching
# ============================================================================

@app.get("/api/nlrb/participants/search")
def search_nlrb_participants(
    q: str = Query(..., min_length=2),
    participant_type: Optional[str] = Query(None, description="Employer, Union, Charged Party / Respondent, etc."),
    state: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    """Search NLRB participants by name"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["LOWER(participant_name) LIKE %s"]
            params = [f"%{q.lower()}%"]

            if participant_type:
                conditions.append("participant_type ILIKE %s")
                params.append(f"%{participant_type}%")

            if state:
                conditions.append("state = %s")
                params.append(state.upper())

            params.append(limit)

            cur.execute(f"""
                SELECT
                    id, case_number, participant_name, participant_type, participant_subtype,
                    city, state, zip, phone_number, matched_employer_id, matched_olms_fnum
                FROM nlrb_participants
                WHERE {' AND '.join(conditions)}
                AND participant_name IS NOT NULL AND participant_name != ''
                ORDER BY participant_name
                LIMIT %s
            """, params)

            return {"query": q, "participants": cur.fetchall()}


@app.get("/api/nlrb/participants/by-case/{case_number}")
def get_nlrb_case_participants(case_number: str):
    """Get all participants in an NLRB case"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, participant_name, participant_type, participant_subtype,
                    city, state, zip, phone_number,
                    matched_employer_id, matched_olms_fnum, match_confidence
                FROM nlrb_participants
                WHERE case_number = %s
                ORDER BY participant_type, participant_name
            """, [case_number])

            participants = cur.fetchall()

            # Group by type
            grouped = {}
            for p in participants:
                ptype = p['participant_type'] or 'Other'
                if ptype not in grouped:
                    grouped[ptype] = []
                grouped[ptype].append(dict(p))

            return {
                "case_number": case_number,
                "participants_by_type": grouped,
                "total": len(participants)
            }


@app.get("/api/nlrb/participants/employers/{employer_id}/cases")
def get_employer_nlrb_cases_enhanced(employer_id: str):
    """Enhanced NLRB lookup using participant matching"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer info
            cur.execute("""
                SELECT employer_name, city, state
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            emp = cur.fetchone()

            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get cases where this employer is matched
            cur.execute("""
                SELECT DISTINCT
                    p.case_number,
                    p.participant_name as matched_name,
                    p.participant_type,
                    p.city as nlrb_city,
                    p.state as nlrb_state,
                    p.match_confidence,
                    c.case_type,
                    ct.description as case_type_desc,
                    c.earliest_date
                FROM nlrb_participants p
                JOIN nlrb_cases c ON p.case_number = c.case_number
                LEFT JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                WHERE p.matched_employer_id = %s
                ORDER BY c.earliest_date DESC NULLS LAST
                LIMIT 50
            """, [employer_id])

            matched_cases = cur.fetchall()

            # Also search by name similarity if no exact matches
            if len(matched_cases) < 5:
                cur.execute("""
                    SELECT DISTINCT
                        p.case_number,
                        p.participant_name as matched_name,
                        p.participant_type,
                        p.city as nlrb_city,
                        p.state as nlrb_state,
                        c.case_type,
                        c.earliest_date
                    FROM nlrb_participants p
                    JOIN nlrb_cases c ON p.case_number = c.case_number
                    WHERE p.participant_subtype = 'Employer'
                    AND LOWER(p.participant_name) LIKE %s
                    AND p.matched_employer_id IS NULL
                    ORDER BY c.earliest_date DESC NULLS LAST
                    LIMIT 20
                """, [f"%{emp['employer_name'].lower()[:20]}%"])
                fuzzy_matches = cur.fetchall()
            else:
                fuzzy_matches = []

            # Get election results for matched cases
            case_numbers = [c['case_number'] for c in matched_cases]
            elections = []
            if case_numbers:
                cur.execute("""
                    SELECT case_number, election_date, union_won, eligible_voters, vote_margin
                    FROM nlrb_elections
                    WHERE case_number = ANY(%s)
                """, [case_numbers])
                elections = cur.fetchall()

            return {
                "employer": dict(emp),
                "matched_cases": matched_cases,
                "fuzzy_matches": fuzzy_matches,
                "elections": elections,
                "total_matched": len(matched_cases),
                "total_fuzzy": len(fuzzy_matches)
            }


@app.get("/api/nlrb/participants/unions/{f_num}/cases")
def get_union_nlrb_cases_enhanced(f_num: str):
    """Enhanced NLRB lookup for unions using participant matching"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get union info
            cur.execute("""
                SELECT union_name, aff_abbr, city, state
                FROM unions_master
                WHERE f_num = %s
            """, [f_num])
            union = cur.fetchone()

            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            # Get cases where this union is matched
            cur.execute("""
                SELECT DISTINCT
                    p.case_number,
                    p.participant_name as matched_name,
                    p.participant_type,
                    p.match_confidence,
                    c.case_type,
                    ct.description as case_type_desc,
                    c.earliest_date
                FROM nlrb_participants p
                JOIN nlrb_cases c ON p.case_number = c.case_number
                LEFT JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                WHERE p.matched_olms_fnum = %s
                ORDER BY c.earliest_date DESC NULLS LAST
                LIMIT 100
            """, [f_num])

            matched_cases = cur.fetchall()

            # Summarize by case type
            by_type = {}
            for c in matched_cases:
                ct = c['case_type'] or 'Unknown'
                if ct not in by_type:
                    by_type[ct] = 0
                by_type[ct] += 1

            return {
                "union": dict(union),
                "matched_cases": matched_cases,
                "by_case_type": by_type,
                "total_cases": len(matched_cases)
            }


@app.get("/api/nlrb/participants/stats")
def get_nlrb_participant_stats():
    """Get statistics about NLRB participants data"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    participant_type,
                    COUNT(*) as count,
                    COUNT(DISTINCT case_number) as unique_cases,
                    COUNT(CASE WHEN matched_employer_id IS NOT NULL THEN 1 END) as matched_employers,
                    COUNT(CASE WHEN matched_olms_fnum IS NOT NULL THEN 1 END) as matched_unions
                FROM nlrb_participants
                GROUP BY participant_type
                ORDER BY COUNT(*) DESC
            """)
            by_type = cur.fetchall()

            cur.execute("""
                SELECT
                    state,
                    COUNT(*) as participants,
                    COUNT(DISTINCT case_number) as cases
                FROM nlrb_participants
                WHERE state IS NOT NULL
                AND state NOT LIKE '%Address%'
                AND LENGTH(state) = 2
                AND participant_subtype = 'Employer'
                GROUP BY state
                ORDER BY COUNT(*) DESC
                LIMIT 20
            """)
            by_state = cur.fetchall()

            cur.execute("""
                SELECT COUNT(*) as total,
                    COUNT(DISTINCT case_number) as unique_cases,
                    COUNT(CASE WHEN matched_employer_id IS NOT NULL THEN 1 END) as employers_matched,
                    COUNT(CASE WHEN matched_olms_fnum IS NOT NULL THEN 1 END) as unions_matched
                FROM nlrb_participants
            """)
            totals = cur.fetchone()

            return {
                "totals": totals,
                "by_participant_type": by_type,
                "employers_by_state": by_state
            }


# ============================================================================
# AR MEMBERSHIP - Detailed Membership Categories
# ============================================================================

@app.get("/api/membership/union/{f_num}")
def get_union_membership_detail(f_num: str):
    """Get detailed membership breakdown for a union"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get membership data aggregated by year
            cur.execute("""
                SELECT
                    l.yr_covered as year,
                    l.union_name,
                    l.aff_abbr,
                    SUM(m.number) as total_members,
                    SUM(CASE WHEN m.voting_eligibility = 'T' THEN m.number ELSE 0 END) as voting_members,
                    SUM(CASE WHEN m.voting_eligibility = 'F' THEN m.number ELSE 0 END) as non_voting_members,
                    COUNT(DISTINCT m.category) as category_count
                FROM ar_membership m
                JOIN lm_data l ON m.rpt_id = l.rpt_id
                WHERE l.f_num = %s
                GROUP BY l.yr_covered, l.union_name, l.aff_abbr
                ORDER BY l.yr_covered DESC
                LIMIT 10
            """, [f_num])

            filings = cur.fetchall()

            if not filings:
                raise HTTPException(status_code=404, detail="No membership data found")

            return {
                "f_num": f_num,
                "union_name": filings[0]['union_name'] if filings else None,
                "affiliation": filings[0]['aff_abbr'] if filings else None,
                "membership_history": [
                    {
                        "year": f["year"],
                        "total_members": f["total_members"],
                        "voting_members": f["voting_members"],
                        "non_voting_members": f["non_voting_members"],
                        "category_count": f["category_count"]
                    }
                    for f in filings
                ]
            }


@app.get("/api/membership/trends")
def get_membership_trends(
    aff_abbr: Optional[str] = None,
    start_year: int = Query(2015),
    end_year: int = Query(2024)
):
    """Get membership trends by year, optionally filtered by affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["l.yr_covered BETWEEN %s AND %s"]
            params = [start_year, end_year]

            if aff_abbr:
                conditions.append("l.aff_abbr = %s")
                params.append(aff_abbr.upper())

            cur.execute(f"""
                SELECT
                    l.yr_covered as year,
                    COUNT(DISTINCT l.f_num) as unions_reporting,
                    SUM(m.number) as total_members,
                    SUM(CASE WHEN m.voting_eligibility = 'T' THEN m.number ELSE 0 END) as voting_members,
                    SUM(CASE WHEN m.voting_eligibility = 'F' THEN m.number ELSE 0 END) as non_voting_members,
                    ROUND(AVG(m.number), 0) as avg_per_category
                FROM ar_membership m
                JOIN lm_data l ON m.rpt_id = l.rpt_id
                WHERE {' AND '.join(conditions)}
                GROUP BY l.yr_covered
                ORDER BY l.yr_covered
            """, params)

            return {
                "affiliation": aff_abbr,
                "start_year": start_year,
                "end_year": end_year,
                "trends": cur.fetchall()
            }


@app.get("/api/membership/by-affiliation")
def get_membership_by_affiliation(year: int = Query(2023)):
    """Get membership totals by national affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COALESCE(l.aff_abbr, 'Independent') as affiliation,
                    COUNT(DISTINCT l.f_num) as locals,
                    SUM(m.number) as total_members,
                    SUM(CASE WHEN m.voting_eligibility = 'T' THEN m.number ELSE 0 END) as voting_members,
                    SUM(CASE WHEN m.voting_eligibility = 'F' THEN m.number ELSE 0 END) as non_voting_members,
                    ROUND(AVG(m.number), 0) as avg_per_local
                FROM ar_membership m
                JOIN lm_data l ON m.rpt_id = l.rpt_id
                WHERE l.yr_covered = %s
                GROUP BY COALESCE(l.aff_abbr, 'Independent')
                ORDER BY SUM(m.number) DESC NULLS LAST
            """, [year])

            return {
                "year": year,
                "affiliations": cur.fetchall()
            }


@app.get("/api/membership/by-state")
def get_ar_membership_by_state(year: int = Query(2023)):
    """Get membership totals by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    l.state,
                    COUNT(DISTINCT l.f_num) as locals,
                    SUM(m.number) as total_members,
                    SUM(CASE WHEN m.voting_eligibility = 'T' THEN m.number ELSE 0 END) as voting_members,
                    SUM(CASE WHEN m.voting_eligibility = 'F' THEN m.number ELSE 0 END) as non_voting_members
                FROM ar_membership m
                JOIN lm_data l ON m.rpt_id = l.rpt_id
                WHERE l.yr_covered = %s
                AND l.state IS NOT NULL AND l.state != ''
                GROUP BY l.state
                ORDER BY SUM(m.number) DESC NULLS LAST
            """, [year])

            return {
                "year": year,
                "states": cur.fetchall()
            }


@app.get("/api/membership/categories")
def get_membership_categories(year: int = Query(2023)):
    """Get breakdown of membership by voting eligibility nationally"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    SUM(m.number) as total_members,
                    SUM(CASE WHEN m.voting_eligibility = 'T' THEN m.number ELSE 0 END) as voting_members,
                    SUM(CASE WHEN m.voting_eligibility = 'F' THEN m.number ELSE 0 END) as non_voting_members,
                    COUNT(DISTINCT l.f_num) as unions_reporting,
                    COUNT(DISTINCT m.category) as unique_categories,
                    ROUND(100.0 * SUM(CASE WHEN m.voting_eligibility = 'F' THEN m.number ELSE 0 END) /
                        NULLIF(SUM(m.number), 0), 1) as non_voting_pct
                FROM ar_membership m
                JOIN lm_data l ON m.rpt_id = l.rpt_id
                WHERE l.yr_covered = %s
            """, [year])

            return {
                "year": year,
                "summary": cur.fetchone()
            }


@app.get("/api/membership/growth")
def get_membership_growth():
    """Get year-over-year membership growth by affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH yearly AS (
                    SELECT
                        COALESCE(l.aff_abbr, 'IND') as affiliation,
                        l.yr_covered as year,
                        SUM(m.number) as members
                    FROM ar_membership m
                    JOIN lm_data l ON m.rpt_id = l.rpt_id
                    WHERE l.yr_covered IN (2022, 2023, 2024)
                    GROUP BY COALESCE(l.aff_abbr, 'IND'), l.yr_covered
                )
                SELECT
                    y1.affiliation,
                    y1.members as members_latest,
                    y2.members as members_prior,
                    y1.members - COALESCE(y2.members, 0) as change,
                    CASE WHEN y2.members > 0 THEN
                        ROUND(100.0 * (y1.members - y2.members) / y2.members, 1)
                    ELSE NULL END as pct_change,
                    y1.year as latest_year
                FROM yearly y1
                LEFT JOIN yearly y2 ON y1.affiliation = y2.affiliation AND y2.year = y1.year - 1
                WHERE y1.year = (SELECT MAX(year) FROM yearly)
                AND y1.members > 10000
                ORDER BY y1.members DESC
            """)

            return {"growth": cur.fetchall()}


# ============================================================================
# ORGANIZING TARGETS - AFSCME NY Case Study
# ============================================================================

@app.get("/api/targets/search")
def search_organizing_targets(
    state: Optional[str] = Query(None, description="Filter by state (e.g., NY)"),
    sector: Optional[str] = Query(None, description="Industry sector"),
    city: Optional[str] = Query(None, description="City name"),
    min_contract_value: Optional[float] = Query(None, description="Minimum government contract value"),
    min_employees: Optional[int] = Query(None, description="Minimum employee count"),
    tier: Optional[str] = Query(None, description="Priority tier: TOP, HIGH, MEDIUM, LOW"),
    exclude_organized: bool = Query(True, description="Exclude already-organized employers"),
    limit: int = Query(50, le=500),
    offset: int = 0,
    sort_by: str = Query("score", description="Sort by: score, funding, employees, name")
):
    """Search potential organizing targets with filters."""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if state:
                conditions.append("ot.state = %s")
                params.append(state.upper())
            if sector:
                conditions.append("ot.industry_category ILIKE %s")
                params.append(f"%{sector}%")
            if city:
                conditions.append("ot.city ILIKE %s")
                params.append(f"%{city}%")
            if min_contract_value:
                conditions.append("ot.total_govt_funding >= %s")
                params.append(min_contract_value)
            if min_employees:
                conditions.append("ot.employee_count >= %s")
                params.append(min_employees)
            if tier:
                conditions.append("ot.priority_tier = %s")
                params.append(tier.upper())
            if exclude_organized:
                conditions.append("ot.has_existing_afscme_contract = FALSE")

            where_clause = " AND ".join(conditions)

            sort_map = {
                "score": "ot.priority_score DESC NULLS LAST",
                "funding": "ot.total_govt_funding DESC NULLS LAST",
                "employees": "ot.employee_count DESC NULLS LAST",
                "name": "ot.employer_name ASC"
            }
            order_by = sort_map.get(sort_by, sort_map["score"])

            # Count
            cur.execute(f"SELECT COUNT(*) FROM organizing_targets ot WHERE {where_clause}", params)
            total = cur.fetchone()['count']

            # Results
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT
                    ot.id, ot.employer_name, ot.city, ot.state,
                    ot.employee_count, ot.total_revenue, ot.industry_category,
                    ot.ny_state_contract_count, ot.ny_state_contract_total,
                    ot.nyc_contract_count, ot.nyc_contract_total,
                    ot.total_govt_funding, ot.priority_score, ot.priority_tier,
                    ot.has_existing_afscme_contract, ot.existing_union_name,
                    e990.ein
                FROM organizing_targets ot
                LEFT JOIN employers_990 e990 ON ot.employer_990_id = e990.id
                WHERE {where_clause}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """, params)

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "targets": cur.fetchall()
            }


@app.get("/api/targets/stats")
def get_organizing_targets_stats():
    """Get summary statistics for organizing targets."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Overall stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_targets,
                    COUNT(*) FILTER (WHERE has_existing_afscme_contract = FALSE) as unorganized,
                    COUNT(*) FILTER (WHERE priority_tier = 'TOP') as top_tier,
                    COUNT(*) FILTER (WHERE priority_tier = 'HIGH') as high_tier,
                    COUNT(*) FILTER (WHERE priority_tier = 'MEDIUM') as medium_tier,
                    SUM(total_govt_funding) as total_funding,
                    SUM(employee_count) as total_employees,
                    AVG(priority_score) as avg_score
                FROM organizing_targets
            """)
            overall = cur.fetchone()

            # By industry
            cur.execute("""
                SELECT
                    industry_category,
                    COUNT(*) as count,
                    SUM(total_govt_funding) as funding,
                    AVG(employee_count) as avg_employees,
                    COUNT(*) FILTER (WHERE priority_tier IN ('TOP', 'HIGH')) as high_priority
                FROM organizing_targets
                WHERE industry_category IS NOT NULL
                GROUP BY industry_category
                ORDER BY COUNT(*) DESC
                LIMIT 15
            """)
            by_industry = cur.fetchall()

            # By city (for NY)
            cur.execute("""
                SELECT
                    city,
                    COUNT(*) as count,
                    SUM(total_govt_funding) as funding,
                    COUNT(*) FILTER (WHERE priority_tier IN ('TOP', 'HIGH')) as high_priority
                FROM organizing_targets
                WHERE city IS NOT NULL AND state = 'NY'
                GROUP BY city
                ORDER BY SUM(total_govt_funding) DESC NULLS LAST
                LIMIT 20
            """)
            by_city = cur.fetchall()

            # Contract funding summary
            cur.execute("""
                SELECT
                    SUM(ny_state_contract_total) as ny_state_total,
                    SUM(nyc_contract_total) as nyc_total,
                    COUNT(*) FILTER (WHERE ny_state_contract_count > 0) as with_state_contracts,
                    COUNT(*) FILTER (WHERE nyc_contract_count > 0) as with_nyc_contracts
                FROM organizing_targets
            """)
            funding = cur.fetchone()

            return {
                "overall": overall,
                "by_industry": by_industry,
                "by_city": by_city,
                "funding_summary": funding
            }


@app.get("/api/targets/for-union/{f_num}")
def get_targets_for_union(
    f_num: str,
    limit: int = Query(20, le=100)
):
    """Get recommended organizing targets for a specific union local.

    Matches based on:
    - Same geographic area (city/state)
    - Similar industry to existing employers
    - High priority score
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get union info and its current employers
            cur.execute("""
                SELECT um.f_num, um.union_name, um.aff_abbr, um.city, um.state
                FROM unions_master um
                WHERE um.f_num = %s
            """, [f_num])
            union = cur.fetchone()

            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            # Get industries of current employers
            cur.execute("""
                SELECT DISTINCT e990.industry_category
                FROM f7_employers_deduped f7
                JOIN employer_990_matches em ON f7.employer_id = em.f7_employer_id
                JOIN employers_990 e990 ON em.employer_990_id = e990.id
                WHERE f7.latest_union_fnum = %s
                AND e990.industry_category IS NOT NULL
            """, [f_num])
            industries = [row['industry_category'] for row in cur.fetchall()]

            # Build query for targets
            conditions = [
                "ot.has_existing_afscme_contract = FALSE",
                "ot.priority_score > 0"
            ]
            params = []

            # Prefer same state
            if union['state']:
                conditions.append("ot.state = %s")
                params.append(union['state'])

            where_clause = " AND ".join(conditions)

            # Score targets - prioritize same city, same industry
            params.append(union['city'] or '')
            params.append(limit)

            cur.execute(f"""
                SELECT
                    ot.id, ot.employer_name, ot.city, ot.state,
                    ot.employee_count, ot.industry_category,
                    ot.total_govt_funding, ot.priority_score, ot.priority_tier,
                    CASE WHEN ot.city = %s THEN 10 ELSE 0 END +
                    CASE WHEN ot.industry_category = ANY(ARRAY{industries or ['']}) THEN 10 ELSE 0 END +
                    ot.priority_score as match_score
                FROM organizing_targets ot
                WHERE {where_clause}
                ORDER BY match_score DESC, ot.priority_score DESC
                LIMIT %s
            """, params)

            targets = cur.fetchall()

            return {
                "union": union,
                "current_industries": industries,
                "recommended_targets": targets,
                "total_found": len(targets)
            }


@app.get("/api/targets/{target_id}")
def get_target_detail(target_id: int):
    """Get detailed information about a specific organizing target."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get target info
            cur.execute("""
                SELECT
                    ot.*,
                    e990.ein, e990.address_line1, e990.zip_code,
                    e990.ntee_code, e990.exempt_status
                FROM organizing_targets ot
                LEFT JOIN employers_990 e990 ON ot.employer_990_id = e990.id
                WHERE ot.id = %s
            """, [target_id])
            target = cur.fetchone()

            if not target:
                raise HTTPException(status_code=404, detail="Target not found")

            # Get NY State contracts
            cur.execute("""
                SELECT
                    c.contract_number, c.contract_title, c.agency_name,
                    c.current_amount, c.start_date, c.end_date,
                    c.contract_type, c.service_description
                FROM ny_state_contracts c
                JOIN contract_employer_matches cem ON c.id = cem.ny_state_contract_id
                WHERE cem.employer_990_id = %s
                ORDER BY c.current_amount DESC NULLS LAST
                LIMIT 20
            """, [target['employer_990_id']])
            ny_contracts = cur.fetchall()

            # Get NYC contracts
            cur.execute("""
                SELECT
                    c.contract_id, c.purpose, c.agency_name,
                    c.current_amount, c.start_date, c.end_date,
                    c.contract_type, c.industry_type
                FROM nyc_contracts c
                JOIN contract_employer_matches cem ON c.id = cem.nyc_contract_id
                WHERE cem.employer_990_id = %s
                ORDER BY c.current_amount DESC NULLS LAST
                LIMIT 20
            """, [target['employer_990_id']])
            nyc_contracts = cur.fetchall()

            return {
                "target": target,
                "ny_state_contracts": ny_contracts,
                "nyc_contracts": nyc_contracts,
                "contract_summary": {
                    "ny_state_count": len(ny_contracts),
                    "nyc_count": len(nyc_contracts),
                    "total_contracts": len(ny_contracts) + len(nyc_contracts)
                }
            }


@app.get("/api/targets/{target_id}/contracts")
def get_target_contracts(
    target_id: int,
    source: Optional[str] = Query(None, description="Filter by source: ny_state, nyc"),
    limit: int = Query(50, le=200)
):
    """Get all government contracts for a target employer."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer_990_id for this target
            cur.execute("SELECT employer_990_id FROM organizing_targets WHERE id = %s", [target_id])
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Target not found")

            emp_id = result['employer_990_id']
            contracts = []

            if source in (None, 'ny_state'):
                cur.execute("""
                    SELECT
                        'ny_state' as source,
                        c.contract_number as contract_id,
                        c.contract_title as title,
                        c.agency_name,
                        c.current_amount as amount,
                        c.start_date, c.end_date,
                        c.contract_type, c.service_description as description
                    FROM ny_state_contracts c
                    JOIN contract_employer_matches cem ON c.id = cem.ny_state_contract_id
                    WHERE cem.employer_990_id = %s
                    ORDER BY c.current_amount DESC NULLS LAST
                    LIMIT %s
                """, [emp_id, limit])
                contracts.extend(cur.fetchall())

            if source in (None, 'nyc'):
                cur.execute("""
                    SELECT
                        'nyc' as source,
                        c.contract_id,
                        c.purpose as title,
                        c.agency_name,
                        c.current_amount as amount,
                        c.start_date, c.end_date,
                        c.contract_type, c.industry_type as description
                    FROM nyc_contracts c
                    JOIN contract_employer_matches cem ON c.id = cem.nyc_contract_id
                    WHERE cem.employer_990_id = %s
                    ORDER BY c.current_amount DESC NULLS LAST
                    LIMIT %s
                """, [emp_id, limit])
                contracts.extend(cur.fetchall())

            return {
                "target_id": target_id,
                "contracts": contracts,
                "total": len(contracts)
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
        return {"status": "healthy", "database": "connected", "version": "5.1-vr-integrated", "vr_records": vr_count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
