from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db

router = APIRouter()


@router.get("/api/unions/cities")
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


@router.get("/api/unions/search")
def search_unions(
    name: Optional[str] = None,
    q: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    union_type: Optional[str] = None,
    min_members: Optional[int] = None,
    has_employers: Optional[bool] = None,
    include_historical: bool = False,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search unions with filters including display names and hierarchy type.

    By default, only shows current unions (yr_covered >= 2022).
    Set include_historical=true to include older/defunct unions.
    Accepts both 'name' and 'q' as search parameters.
    """
    # Accept both 'q' and 'name' for search term
    search_term = name or q

    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            # Filter out stale/historical unions by default
            if not include_historical:
                conditions.append("um.yr_covered >= 2022")

            if search_term:
                # Search union_name, local_number, and display_name
                conditions.append("""(
                    um.union_name ILIKE %s
                    OR um.local_number = %s
                    OR v.display_name ILIKE %s
                )""")
                clean_name = search_term.replace('local ', '').replace('Local ', '').strip()
                params.extend([f"%{search_term}%", clean_name, f"%{search_term}%"])
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


@router.get("/api/unions/types")
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


@router.get("/api/unions/national")
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


@router.get("/api/unions/national/{aff_abbr}")
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


@router.get("/api/unions/{f_num}")
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


@router.get("/api/unions/{f_num}/employers")
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


@router.get("/api/unions/locals/{affiliation}")
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
