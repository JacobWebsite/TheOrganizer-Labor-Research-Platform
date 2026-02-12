from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db
from ..helpers import is_likely_law_firm

router = APIRouter()


@router.get("/api/nlrb/summary")
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


@router.get("/api/nlrb/elections/search")
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


@router.get("/api/nlrb/elections/map")
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


@router.get("/api/nlrb/elections/by-year")
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


@router.get("/api/nlrb/elections/by-state")
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


@router.get("/api/nlrb/elections/by-affiliation")
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


@router.get("/api/nlrb/election/{case_number}")
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


@router.get("/api/nlrb/ulp/search")
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


@router.get("/api/nlrb/ulp/by-section")
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


@router.get("/api/nlrb/patterns")
def get_nlrb_patterns():
    """Return NLRB historical success pattern reference data:
    industry win rates, size bucket win rates, and summary stats."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT naics_2, total_elections, union_wins, win_rate_pct, sample_quality
                FROM ref_nlrb_industry_win_rates
                ORDER BY total_elections DESC
            """)
            industry = cur.fetchall()

            cur.execute("""
                SELECT size_bucket, min_employees, max_employees,
                       total_elections, union_wins, win_rate_pct
                FROM ref_nlrb_size_win_rates
                ORDER BY min_employees
            """)
            size_buckets = cur.fetchall()

            cur.execute("""
                SELECT state, total_elections, union_wins, win_rate_pct
                FROM ref_nlrb_state_win_rates
                ORDER BY win_rate_pct DESC
            """)
            states = cur.fetchall()

            # Summary stats
            cur.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as wins,
                       ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
                       MIN(election_date) as earliest,
                       MAX(election_date) as latest
                FROM nlrb_elections WHERE union_won IS NOT NULL
            """)
            summary = cur.fetchone()

            return {
                "summary": {
                    "total_elections": summary['total'],
                    "union_wins": summary['wins'],
                    "overall_win_rate": float(summary['win_rate']),
                    "date_range": [str(summary['earliest']), str(summary['latest'])]
                },
                "by_industry": [dict(r) for r in industry],
                "by_size": [dict(r) for r in size_buckets],
                "by_state": [dict(r) for r in states]
            }
