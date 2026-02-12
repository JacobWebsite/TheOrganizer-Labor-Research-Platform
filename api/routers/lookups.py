from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db

router = APIRouter()


@router.get("/api/lookups/sectors")
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


@router.get("/api/lookups/affiliations")
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


@router.get("/api/lookups/states")
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


@router.get("/api/lookups/naics-sectors")
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


@router.get("/api/lookups/metros")
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


@router.get("/api/lookups/cities")
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


@router.get("/api/metros/{cbsa_code}/stats")
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
