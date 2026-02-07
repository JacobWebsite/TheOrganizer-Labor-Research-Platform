"""
Labor Relations Platform API v6.4 - Multi-Employer Deduplication
Run with: py -m uvicorn labor_api_v6:app --reload --port 8001
Features:
- OSHA-enriched 6-digit NAICS codes for 20,090 employers
- Multi-employer agreement deduplication (90% BLS coverage vs 203% raw)
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, List
from pydantic import BaseModel
import re

app = FastAPI(
    title="Labor Relations Research API",
    version="6.2",
    description="Integrated platform: OLMS union data, F-7 employers, BLS density & projections, NLRB elections, OSHA safety"
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


# Law firm detection patterns for NLRB data quality
LAW_FIRM_PATTERNS = [
    r'\bLLP\b', r'\bLLC\b.*LAW', r'\bATTORNEY',
    r'\bLAW\s+(FIRM|OFFICE|GROUP|OFFICES)', r'\bESQ\.?\b', r'\bCOUNSEL\b',
    r'\bLAW\s+&\s+', r'\b&\s+LAW\b', r'\bLAWYERS?\b', r'\bLEGAL\s+SERVICES'
]

def is_likely_law_firm(name: str) -> bool:
    """Detect if an employer name is likely a law firm (data quality issue in NLRB)"""
    if not name:
        return False
    for pattern in LAW_FIRM_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


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


@app.get("/api/lookups/naics-sectors")
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


@app.get("/api/lookups/metros")
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


@app.get("/api/lookups/cities")
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


@app.get("/api/metros/{cbsa_code}/stats")
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


# ============================================================================
# BLS UNION DENSITY BY INDUSTRY
# ============================================================================

@app.get("/api/density/naics/{naics_2digit}")
def get_naics_density(naics_2digit: str):
    """Get union density data for a NAICS 2-digit sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT naics_2digit, sector_name, bls_indy_code, bls_indy_name,
                       year, union_density_pct
                FROM v_naics_union_density WHERE naics_2digit = %s
            """, [naics_2digit])
            current = cur.fetchone()
            
            trend = []
            if current and current['bls_indy_code']:
                cur.execute("""
                    SELECT bud.year, bud.value as union_density_pct
                    FROM bls_union_series bus
                    JOIN bls_union_data bud ON bus.series_id = bud.series_id
                    WHERE bus.indy_code = %s AND bus.fips_code = '00' 
                      AND bus.pcts_code = '05' AND bus.unin_code = '1'
                    ORDER BY bud.year DESC LIMIT 15
                """, [current['bls_indy_code']])
                trend = cur.fetchall()
            
            return {"naics_2digit": naics_2digit, "current": current, "trend": trend}


@app.get("/api/density/all")
def get_all_density(year: Optional[int] = None):
    """Get union density for all NAICS sectors"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if year:
                cur.execute("""
                    SELECT bnm.naics_2digit, ns.sector_name, bnm.bls_indy_name,
                           bud.year, bud.value as union_density_pct
                    FROM bls_naics_mapping bnm
                    JOIN naics_sectors ns ON bnm.naics_2digit = ns.naics_2digit
                    JOIN bls_union_series bus ON bus.indy_code = bnm.bls_indy_code AND bus.fips_code = '00'
                    JOIN bls_union_data bud ON bus.series_id = bud.series_id
                    WHERE bud.year = %s ORDER BY bud.value DESC
                """, [year])
            else:
                cur.execute("SELECT * FROM v_naics_union_density ORDER BY union_density_pct DESC")
            return {"density": cur.fetchall()}


@app.get("/api/density/by-state")
def get_density_by_state(state: Optional[str] = None):
    """Get union density by state (private and public sector)

    Args:
        state: Optional 2-letter state code. If not provided, returns all states.

    Returns:
        Latest density values for private and public sectors by state.
        Includes public_is_estimated flag (true for states where public density
        was estimated from total and private density due to small CPS samples).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            if state:
                cur.execute("""
                    SELECT state, state_name,
                           private_density_pct, private_year,
                           public_density_pct, public_year,
                           public_is_estimated,
                           total_density_pct, total_year
                    FROM v_state_density_latest
                    WHERE state = %s
                """, [state.upper()])
                result = cur.fetchone()
                if not result:
                    raise HTTPException(status_code=404, detail=f"State not found: {state}")
                return {"state": result}
            else:
                cur.execute("""
                    SELECT state, state_name,
                           private_density_pct, private_year,
                           public_density_pct, public_year,
                           public_is_estimated,
                           total_density_pct, total_year
                    FROM v_state_density_latest
                    ORDER BY state
                """)
                return {"states": cur.fetchall()}


@app.get("/api/density/by-state/{state}/history")
def get_state_density_history(state: str, sector: Optional[str] = None):
    """Get historical union density for a state

    Args:
        state: 2-letter state code
        sector: Optional filter: 'private', 'public', or 'total'. If not provided, returns all.

    Returns:
        Historical density values by year for the specified state.
        Includes source field ('unionstats_csv' or 'estimated_from_total').
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            if sector:
                if sector.lower() not in ('private', 'public', 'total'):
                    raise HTTPException(status_code=400, detail="Sector must be 'private', 'public', or 'total'")
                cur.execute("""
                    SELECT state, state_name, sector, year, density_pct, source
                    FROM state_sector_union_density
                    WHERE state = %s AND sector = %s
                    ORDER BY year DESC
                """, [state.upper(), sector.lower()])
            else:
                cur.execute("""
                    SELECT state, state_name, sector, year, density_pct, source
                    FROM state_sector_union_density
                    WHERE state = %s
                    ORDER BY sector, year DESC
                """, [state.upper()])

            results = cur.fetchall()
            if not results:
                raise HTTPException(status_code=404, detail=f"No data found for state: {state}")

            # Get latest values for summary
            cur.execute("""
                SELECT state, state_name,
                       private_density_pct, private_year,
                       public_density_pct, public_year,
                       public_is_estimated, total_density_pct, total_year
                FROM v_state_density_latest
                WHERE state = %s
            """, [state.upper()])
            latest = cur.fetchone()

            return {
                "state": state.upper(),
                "latest": latest,
                "history": results
            }


@app.get("/api/density/by-govt-level")
def get_density_by_govt_level():
    """Get estimated union density by government level (federal/state/local) for all states

    Uses uniform multiplier method: each state's density at each government level
    is estimated as k × national_baseline, where k is calculated from the state's
    overall public sector density.

    Returns:
        All states with estimated federal, state, and local government union densities.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    state,
                    state_name,
                    public_density_pct,
                    public_is_estimated,
                    multiplier,
                    est_federal_density,
                    est_state_density,
                    est_local_density,
                    fed_share_of_public,
                    state_share_of_public,
                    local_share_of_public
                FROM state_govt_level_density
                ORDER BY public_density_pct DESC
            """)
            results = cur.fetchall()

            # Get summary stats
            cur.execute("""
                SELECT
                    ROUND(AVG(est_federal_density), 1) as avg_federal,
                    ROUND(AVG(est_state_density), 1) as avg_state,
                    ROUND(AVG(est_local_density), 1) as avg_local,
                    ROUND(AVG(multiplier), 2) as avg_multiplier,
                    COUNT(CASE WHEN multiplier > 1.5 THEN 1 END) as high_union_states,
                    COUNT(CASE WHEN multiplier <= 0.75 THEN 1 END) as low_union_states
                FROM state_govt_level_density
            """)
            stats = cur.fetchone()

            return {
                "methodology": {
                    "description": "Uniform multiplier method using national baselines",
                    "national_federal_baseline": 25.3,
                    "national_state_baseline": 27.8,
                    "national_local_baseline": 38.2,
                    "formula": "state_density = k × national_baseline"
                },
                "summary": {
                    "avg_federal_density": stats[0],
                    "avg_state_density": stats[1],
                    "avg_local_density": stats[2],
                    "avg_multiplier": stats[3],
                    "high_union_states": stats[4],
                    "low_union_states": stats[5]
                },
                "states": results
            }


@app.get("/api/density/by-govt-level/{state}")
def get_state_density_by_govt_level(state: str):
    """Get estimated union density by government level for a specific state

    Args:
        state: 2-letter state code

    Returns:
        State's estimated federal, state, and local government union densities,
        along with workforce composition and comparison to national baselines.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    g.state,
                    g.state_name,
                    g.public_density_pct,
                    g.public_is_estimated,
                    g.multiplier,
                    g.est_federal_density,
                    g.est_state_density,
                    g.est_local_density,
                    g.fed_share_of_public,
                    g.state_share_of_public,
                    g.local_share_of_public,
                    w.federal_gov_share * 100 as federal_workforce_pct,
                    w.state_gov_share * 100 as state_workforce_pct,
                    w.local_gov_share * 100 as local_workforce_pct,
                    w.public_share * 100 as public_workforce_pct,
                    w.private_share * 100 as private_workforce_pct,
                    d.private_density_pct,
                    d.total_density_pct
                FROM state_govt_level_density g
                JOIN state_workforce_shares w ON g.state = w.state
                JOIN v_state_density_latest d ON g.state = d.state
                WHERE g.state = %s
            """, [state.upper()])

            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"State not found: {state}")

            # Calculate contribution breakdown
            fed_contribution = result[8] * result[5]  # fed_share_of_public * est_fed_density
            state_contribution = result[9] * result[6]
            local_contribution = result[10] * result[7]

            return {
                "state": result[0],
                "state_name": result[1],
                "densities": {
                    "private": result[16],
                    "public_combined": result[2],
                    "public_is_estimated": result[3],
                    "federal_estimated": result[5],
                    "state_estimated": result[6],
                    "local_estimated": result[7],
                    "total": result[17]
                },
                "multiplier": {
                    "value": result[4],
                    "interpretation": "above national average" if result[4] > 1 else "below national average"
                },
                "workforce_composition": {
                    "federal_pct": result[11],
                    "state_pct": result[12],
                    "local_pct": result[13],
                    "public_total_pct": result[14],
                    "private_pct": result[15]
                },
                "public_sector_composition": {
                    "federal_share": round(result[8] * 100, 1),
                    "state_share": round(result[9] * 100, 1),
                    "local_share": round(result[10] * 100, 1)
                },
                "contribution_to_public_density": {
                    "federal": round(fed_contribution, 1),
                    "state": round(state_contribution, 1),
                    "local": round(local_contribution, 1),
                    "total": round(fed_contribution + state_contribution + local_contribution, 1)
                },
                "comparison_to_national": {
                    "federal": {"state": result[5], "national": 25.3, "premium": round(result[5] - 25.3, 1)},
                    "state": {"state": result[6], "national": 27.8, "premium": round(result[6] - 27.8, 1)},
                    "local": {"state": result[7], "national": 38.2, "premium": round(result[7] - 38.2, 1)}
                }
            }


# ============================================================================
# COUNTY UNION DENSITY ESTIMATES
# ============================================================================

@app.get("/api/density/by-county")
def get_density_by_county(
    state: Optional[str] = None,
    min_density: Optional[float] = None,
    max_density: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get estimated union density for counties

    Args:
        state: Optional 2-letter state code filter
        min_density: Minimum total density filter
        max_density: Maximum total density filter
        limit: Max results (default 100, max 500)
        offset: Pagination offset

    Returns:
        Counties with estimated density values and confidence levels.
    """
    if limit > 500:
        limit = 500

    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = []
            params = []

            if state:
                conditions.append("e.state = %s")
                params.append(state.upper())
            if min_density is not None:
                conditions.append("e.estimated_total_density >= %s")
                params.append(min_density)
            if max_density is not None:
                conditions.append("e.estimated_total_density <= %s")
                params.append(max_density)

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            # Count total
            cur.execute(f"""
                SELECT COUNT(*)
                FROM county_union_density_estimates e
                {where_clause}
            """, params)
            total = cur.fetchone()[0]

            # Get results
            query_params = params + [limit, offset]
            cur.execute(f"""
                SELECT
                    e.fips,
                    e.state,
                    e.county_name,
                    e.estimated_total_density,
                    e.estimated_private_density,
                    e.estimated_public_density,
                    e.confidence_level,
                    e.state_multiplier,
                    w.public_share * 100 as public_workforce_pct,
                    w.private_share * 100 as private_workforce_pct,
                    w.self_employed_share * 100 as self_employed_pct
                FROM county_union_density_estimates e
                JOIN county_workforce_shares w ON e.fips = w.fips
                {where_clause}
                ORDER BY e.estimated_total_density DESC
                LIMIT %s OFFSET %s
            """, query_params)

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "counties": cur.fetchall()
            }


@app.get("/api/density/by-county/{fips}")
def get_county_density_detail(fips: str):
    """Get detailed density estimate for a specific county

    Args:
        fips: 5-digit FIPS code (e.g., '36061' for New York County, NY)

    Returns:
        Complete density breakdown with methodology explanation.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.fips,
                    e.state,
                    e.county_name,
                    e.estimated_total_density,
                    e.estimated_private_density,
                    e.estimated_public_density,
                    e.estimated_federal_density,
                    e.estimated_state_density,
                    e.estimated_local_density,
                    e.private_share,
                    e.federal_share,
                    e.state_share,
                    e.local_share,
                    e.public_share,
                    e.state_private_rate,
                    e.state_federal_rate,
                    e.state_state_rate,
                    e.state_local_rate,
                    e.confidence_level,
                    e.state_multiplier,
                    w.self_employed_share
                FROM county_union_density_estimates e
                JOIN county_workforce_shares w ON e.fips = w.fips
                WHERE e.fips = %s
            """, [fips.zfill(5)])

            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail=f"County not found: {fips}")

            return {
                "fips": result[0],
                "state": result[1],
                "county_name": result[2],
                "estimated_densities": {
                    "total": result[3],
                    "private": result[4],
                    "public": result[5],
                    "federal": result[6],
                    "state_gov": result[7],
                    "local": result[8]
                },
                "workforce_composition": {
                    "private_pct": round(float(result[9]) * 100, 1) if result[9] else 0,
                    "federal_pct": round(float(result[10]) * 100, 1) if result[10] else 0,
                    "state_pct": round(float(result[11]) * 100, 1) if result[11] else 0,
                    "local_pct": round(float(result[12]) * 100, 1) if result[12] else 0,
                    "public_pct": round(float(result[13]) * 100, 1) if result[13] else 0,
                    "self_employed_pct": round(float(result[20]) * 100, 1) if result[20] else 0
                },
                "state_density_rates_used": {
                    "private": result[14],
                    "federal": result[15],
                    "state_gov": result[16],
                    "local": result[17]
                },
                "confidence_level": result[18],
                "state_union_multiplier": result[19],
                "methodology": {
                    "description": "State density rates applied to county workforce composition",
                    "formula": "Total = (Private% × State_Private_Rate) + (Fed% × State_Fed_Rate) + (State% × State_State_Rate) + (Local% × State_Local_Rate)",
                    "note": "Self-employed workers (0% union rate) are excluded from calculation"
                }
            }


@app.get("/api/density/by-state/{state}/counties")
def get_state_counties_density(state: str):
    """Get all county density estimates for a state

    Args:
        state: 2-letter state code

    Returns:
        All counties in the state with density estimates.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    e.fips,
                    e.county_name,
                    e.estimated_total_density,
                    e.estimated_public_density,
                    e.confidence_level,
                    w.public_share * 100 as public_workforce_pct,
                    w.private_share * 100 as private_workforce_pct
                FROM county_union_density_estimates e
                JOIN county_workforce_shares w ON e.fips = w.fips
                WHERE e.state = %s
                ORDER BY e.estimated_total_density DESC
            """, [state.upper()])

            counties = cur.fetchall()
            if not counties:
                raise HTTPException(status_code=404, detail=f"No counties found for state: {state}")

            # Get state-level summary
            cur.execute("""
                SELECT
                    COUNT(*) as county_count,
                    ROUND(AVG(estimated_total_density), 2) as avg_density,
                    ROUND(MIN(estimated_total_density), 2) as min_density,
                    ROUND(MAX(estimated_total_density), 2) as max_density
                FROM county_union_density_estimates
                WHERE state = %s
            """, [state.upper()])
            summary = cur.fetchone()

            # Get state density for comparison
            cur.execute("""
                SELECT total_density_pct FROM v_state_density_latest WHERE state = %s
            """, [state.upper()])
            state_density = cur.fetchone()

            return {
                "state": state.upper(),
                "summary": {
                    "county_count": summary[0],
                    "avg_county_density": summary[1],
                    "min_county_density": summary[2],
                    "max_county_density": summary[3],
                    "state_total_density": state_density[0] if state_density else None
                },
                "counties": counties
            }


@app.get("/api/density/county-summary")
def get_county_density_summary():
    """Get summary statistics for county density estimates

    Returns:
        National and state-level summaries of county density variation.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # National stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_counties,
                    ROUND(AVG(estimated_total_density), 2) as avg_density,
                    ROUND(MIN(estimated_total_density), 2) as min_density,
                    ROUND(MAX(estimated_total_density), 2) as max_density,
                    ROUND(STDDEV(estimated_total_density), 2) as stddev_density,
                    COUNT(CASE WHEN confidence_level = 'HIGH' THEN 1 END) as high_confidence,
                    COUNT(CASE WHEN confidence_level = 'MEDIUM' THEN 1 END) as medium_confidence
                FROM county_union_density_estimates
            """)
            national = cur.fetchone()

            # Top 10 counties
            cur.execute("""
                SELECT fips, state, county_name, estimated_total_density
                FROM county_union_density_estimates
                ORDER BY estimated_total_density DESC
                LIMIT 10
            """)
            top_counties = cur.fetchall()

            # Bottom 10 counties (excluding zeros)
            cur.execute("""
                SELECT fips, state, county_name, estimated_total_density
                FROM county_union_density_estimates
                WHERE estimated_total_density > 0
                ORDER BY estimated_total_density ASC
                LIMIT 10
            """)
            bottom_counties = cur.fetchall()

            # State summaries
            cur.execute("""
                SELECT
                    state,
                    COUNT(*) as county_count,
                    ROUND(AVG(estimated_total_density), 2) as avg_density
                FROM county_union_density_estimates
                GROUP BY state
                ORDER BY avg_density DESC
            """)
            by_state = cur.fetchall()

            return {
                "national_summary": {
                    "total_counties": national[0],
                    "avg_density": national[1],
                    "min_density": national[2],
                    "max_density": national[3],
                    "stddev_density": national[4],
                    "high_confidence_count": national[5],
                    "medium_confidence_count": national[6]
                },
                "top_density_counties": top_counties,
                "bottom_density_counties": bottom_counties,
                "by_state": by_state,
                "methodology_note": "Estimates based on state density rates × county workforce composition. Self-employed workers excluded (0% union rate)."
            }


# ============================================================================
# INDUSTRY-WEIGHTED DENSITY ANALYSIS
# ============================================================================

@app.get("/api/density/industry-rates")
def get_industry_density_rates():
    """Get BLS industry union density rates (2024)

    Returns:
        List of 12 industry categories with their union density percentages.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT industry_code, industry_name, union_density_pct, year, source
                FROM bls_industry_density
                ORDER BY union_density_pct DESC
            """)
            rates = cur.fetchall()

            return {
                "industry_rates": [
                    {
                        "industry_code": r["industry_code"],
                        "industry_name": r["industry_name"],
                        "union_density_pct": r["union_density_pct"],
                        "year": r["year"],
                        "source": r["source"]
                    }
                    for r in rates
                ],
                "note": "Rates from BLS Union Membership Table 3 (2024). Used to calculate expected private sector density from industry composition."
            }


@app.get("/api/density/state-industry-comparison")
def get_state_industry_comparison(
    sort_by: str = Query("climate_multiplier", description="Sort by: climate_multiplier, expected, actual, difference"),
    order: str = Query("desc", description="Sort order: asc or desc")
):
    """Get state-level expected vs actual private sector density comparison

    Returns:
        All 51 states with:
        - Expected density (based on industry composition)
        - Actual density (from CPS)
        - Climate multiplier (actual / expected)
        - Interpretation (STRONG, ABOVE_AVERAGE, BELOW_AVERAGE, WEAK)
    """
    valid_sorts = {
        "climate_multiplier": "climate_multiplier",
        "expected": "expected_private_density",
        "actual": "actual_private_density",
        "difference": "density_difference",
        "state": "state"
    }
    sort_col = valid_sorts.get(sort_by, "climate_multiplier")
    order_dir = "DESC" if order.lower() == "desc" else "ASC"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT state, state_name, expected_private_density, actual_private_density,
                       density_difference, climate_multiplier, interpretation
                FROM state_industry_density_comparison
                ORDER BY {sort_col} {order_dir}
            """)
            states = cur.fetchall()

            # Summary stats
            cur.execute("""
                SELECT interpretation, COUNT(*), ROUND(AVG(climate_multiplier), 2)
                FROM state_industry_density_comparison
                GROUP BY interpretation
                ORDER BY AVG(climate_multiplier) DESC
            """)
            summary = cur.fetchall()

            return {
                "states": [
                    {
                        "state": s["state"],
                        "state_name": s["state_name"],
                        "expected_private_density": s["expected_private_density"],
                        "actual_private_density": s["actual_private_density"],
                        "density_difference": s["density_difference"],
                        "climate_multiplier": s["climate_multiplier"],
                        "interpretation": s["interpretation"]
                    }
                    for s in states
                ],
                "summary_by_interpretation": [
                    {
                        "interpretation": s["interpretation"],
                        "state_count": s["count"],
                        "avg_multiplier": s["round"]
                    }
                    for s in summary
                ],
                "methodology": "Expected density = sum(industry_share × BLS_industry_rate) for 12 industries. Climate multiplier = actual / expected. STRONG > 1.5x, ABOVE_AVERAGE 1.0-1.5x, BELOW_AVERAGE 0.5-1.0x, WEAK < 0.5x."
            }


@app.get("/api/density/state-industry-comparison/{state}")
def get_state_industry_detail(state: str):
    """Get detailed industry composition and density comparison for a single state

    Args:
        state: Two-letter state abbreviation (e.g., NY, CA)

    Returns:
        Industry breakdown with BLS rates and contribution to expected density.
    """
    state = state.upper()

    with get_db() as conn:
        with conn.cursor() as cur:
            # Get state comparison data
            cur.execute("""
                SELECT state, state_name, expected_private_density, actual_private_density,
                       density_difference, climate_multiplier, interpretation,
                       agriculture_mining_share, construction_share, manufacturing_share,
                       wholesale_share, retail_share, transportation_utilities_share,
                       information_share, finance_share, professional_services_share,
                       education_health_share, leisure_hospitality_share, other_services_share
                FROM state_industry_density_comparison
                WHERE state = %s
            """, (state,))
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail=f"State {state} not found")

            # Get BLS rates
            cur.execute("SELECT industry_code, industry_name, union_density_pct FROM bls_industry_density")
            bls_rates = {r["industry_code"]: (r["industry_name"], float(r["union_density_pct"])) for r in cur.fetchall()}

            # Map shares to industry codes
            share_map = {
                'AGR_MIN': ('agriculture_mining_share', row["agriculture_mining_share"]),
                'CONST': ('construction_share', row["construction_share"]),
                'MFG': ('manufacturing_share', row["manufacturing_share"]),
                'WHOLESALE': ('wholesale_share', row["wholesale_share"]),
                'RETAIL': ('retail_share', row["retail_share"]),
                'TRANS_UTIL': ('transportation_utilities_share', row["transportation_utilities_share"]),
                'INFO': ('information_share', row["information_share"]),
                'FINANCE': ('finance_share', row["finance_share"]),
                'PROF_BUS': ('professional_services_share', row["professional_services_share"]),
                'EDU_HEALTH': ('education_health_share', row["education_health_share"]),
                'LEISURE': ('leisure_hospitality_share', row["leisure_hospitality_share"]),
                'OTHER': ('other_services_share', row["other_services_share"])
            }

            # Calculate contribution from each industry
            # Renormalize shares to exclude public admin (sum to 1.0)
            total_private_share = sum(float(s[1] or 0) for s in share_map.values())

            industry_breakdown = []
            for code, (col_name, share) in share_map.items():
                share_val = float(share or 0)
                normalized_share = share_val / total_private_share if total_private_share > 0 else 0
                bls_name, bls_rate = bls_rates.get(code, ('Unknown', 5.9))
                contribution = normalized_share * bls_rate

                industry_breakdown.append({
                    "industry_code": code,
                    "industry_name": bls_name,
                    "share_pct": round(share_val * 100, 2),
                    "normalized_share_pct": round(normalized_share * 100, 2),
                    "bls_density_pct": bls_rate,
                    "contribution_pct": round(contribution, 3)
                })

            # Sort by contribution descending
            industry_breakdown.sort(key=lambda x: x['contribution_pct'], reverse=True)

            return {
                "state": row["state"],
                "state_name": row["state_name"],
                "expected_private_density": row["expected_private_density"],
                "actual_private_density": row["actual_private_density"],
                "density_difference": row["density_difference"],
                "climate_multiplier": row["climate_multiplier"],
                "interpretation": row["interpretation"],
                "industry_breakdown": industry_breakdown,
                "note": f"{row['state_name']} has {'stronger' if row['climate_multiplier'] > 1 else 'weaker'} union presence than expected from its industry mix alone. Climate multiplier of {row['climate_multiplier']}x indicates {'favorable' if row['climate_multiplier'] > 1 else 'challenging'} organizing environment."
            }


@app.get("/api/density/by-county/{fips}/industry")
def get_county_industry_detail(fips: str):
    """Get industry composition and density calculation for a single county

    Args:
        fips: 5-digit county FIPS code

    Returns:
        County industry breakdown with contribution to expected private density.
    """
    fips = fips.zfill(5)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Get county industry shares
            cur.execute("""
                SELECT fips, state, county_name,
                       agriculture_mining_share, construction_share, manufacturing_share,
                       wholesale_share, retail_share, transportation_utilities_share,
                       information_share, finance_share, professional_services_share,
                       education_health_share, leisure_hospitality_share, other_services_share,
                       public_admin_share
                FROM county_industry_shares
                WHERE fips = %s
            """, (fips,))
            county = cur.fetchone()

            if not county:
                raise HTTPException(status_code=404, detail=f"County FIPS {fips} not found in industry data")

            # Get county density estimates
            cur.execute("""
                SELECT industry_expected_private, state_climate_multiplier, industry_adjusted_private,
                       estimated_total_density
                FROM county_union_density_estimates
                WHERE fips = %s
            """, (fips,))
            density = cur.fetchone()

            # Get state multiplier
            cur.execute("""
                SELECT climate_multiplier, interpretation
                FROM state_industry_density_comparison
                WHERE state = %s
            """, (county["state"],))
            state_info = cur.fetchone()

            # Get BLS rates
            cur.execute("SELECT industry_code, industry_name, union_density_pct FROM bls_industry_density")
            bls_rates = {r["industry_code"]: (r["industry_name"], float(r["union_density_pct"])) for r in cur.fetchall()}

            # Map shares
            share_map = {
                'AGR_MIN': ('Agriculture/Mining', county["agriculture_mining_share"]),
                'CONST': ('Construction', county["construction_share"]),
                'MFG': ('Manufacturing', county["manufacturing_share"]),
                'WHOLESALE': ('Wholesale Trade', county["wholesale_share"]),
                'RETAIL': ('Retail Trade', county["retail_share"]),
                'TRANS_UTIL': ('Transportation/Utilities', county["transportation_utilities_share"]),
                'INFO': ('Information', county["information_share"]),
                'FINANCE': ('Finance/Real Estate', county["finance_share"]),
                'PROF_BUS': ('Professional Services', county["professional_services_share"]),
                'EDU_HEALTH': ('Education/Healthcare', county["education_health_share"]),
                'LEISURE': ('Leisure/Hospitality', county["leisure_hospitality_share"]),
                'OTHER': ('Other Services', county["other_services_share"])
            }

            # Renormalize excluding public admin
            total_private_share = sum(float(s[1] or 0) for s in share_map.values())

            industry_breakdown = []
            for code, (name, share) in share_map.items():
                share_val = float(share or 0)
                normalized_share = share_val / total_private_share if total_private_share > 0 else 0
                _, bls_rate = bls_rates.get(code, ('', 5.9))
                contribution = normalized_share * bls_rate

                industry_breakdown.append({
                    "industry": name,
                    "share_pct": round(share_val * 100, 2),
                    "bls_density_pct": bls_rate,
                    "contribution_pct": round(contribution, 3)
                })

            industry_breakdown.sort(key=lambda x: x['contribution_pct'], reverse=True)

            state_mult = state_info["climate_multiplier"] if state_info else 1.0

            return {
                "fips": county["fips"],
                "state": county["state"],
                "county_name": county["county_name"],
                "public_admin_share_pct": round(float(county["public_admin_share"] or 0) * 100, 2),
                "industry_breakdown": industry_breakdown,
                "expected_private_density": density["industry_expected_private"] if density else None,
                "state_climate_multiplier": density["state_climate_multiplier"] if density else state_mult,
                "adjusted_private_density": density["industry_adjusted_private"] if density else None,
                "estimated_total_density": density["estimated_total_density"] if density else None,
                "state_interpretation": state_info["interpretation"] if state_info else None,
                "methodology": f"Expected density from county industry mix, adjusted by state climate multiplier ({state_mult}x) to account for regional union culture."
            }


# ============================================================================
# NY SUB-COUNTY DENSITY ESTIMATES (County, ZIP, Census Tract)
# ============================================================================

@app.get("/api/density/ny/counties")
def get_ny_county_density(
    min_density: Optional[float] = None,
    max_density: Optional[float] = None,
    sort_by: str = Query("total_density", regex="^(total_density|private_density|public_density|name)$")
):
    """Get union density estimates for all 62 NY counties

    Args:
        min_density: Minimum total density filter
        max_density: Maximum total density filter
        sort_by: Sort field (total_density, private_density, public_density, name)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = []
            params = []

            if min_density is not None:
                conditions.append("estimated_total_density >= %s")
                params.append(min_density)
            if max_density is not None:
                conditions.append("estimated_total_density <= %s")
                params.append(max_density)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            sort_map = {
                "total_density": "estimated_total_density DESC",
                "private_density": "estimated_private_density DESC",
                "public_density": "estimated_public_density DESC",
                "name": "county_name ASC"
            }
            order_by = sort_map.get(sort_by, "estimated_total_density DESC")

            cur.execute(f"""
                SELECT county_fips, county_name,
                       estimated_total_density, estimated_private_density, estimated_public_density,
                       estimated_federal_density, estimated_state_density, estimated_local_density,
                       private_class_total, govt_class_total,
                       education_health_share, public_admin_share,
                       private_in_public_industries
                FROM ny_county_density_estimates
                {where_clause}
                ORDER BY {order_by}
            """, params)

            counties = cur.fetchall()

            # Summary stats
            cur.execute("""
                SELECT COUNT(*) as count,
                       AVG(estimated_total_density) as avg_total,
                       MIN(estimated_total_density) as min_total,
                       MAX(estimated_total_density) as max_total,
                       AVG(estimated_private_density) as avg_private,
                       AVG(estimated_public_density) as avg_public
                FROM ny_county_density_estimates
            """)
            stats = cur.fetchone()

            return {
                "counties": counties,
                "count": len(counties),
                "summary": {
                    "total_counties": stats["count"],
                    "avg_total_density": round(float(stats["avg_total"]), 2),
                    "min_total_density": round(float(stats["min_total"]), 2),
                    "max_total_density": round(float(stats["max_total"]), 2),
                    "avg_private_density": round(float(stats["avg_private"]), 2),
                    "avg_public_density": round(float(stats["avg_public"]), 2)
                },
                "methodology": "Industry-weighted density (10 BLS industries), auto-calibrated multiplier (2.26x) targeting CPS statewide 12.4%"
            }


@app.get("/api/density/ny/county/{fips}")
def get_ny_county_density_detail(fips: str):
    """Get detailed density breakdown for a single NY county

    Args:
        fips: 5-digit county FIPS code
    """
    fips = fips.zfill(5)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM ny_county_density_estimates
                WHERE county_fips = %s
            """, (fips,))
            county = cur.fetchone()

            if not county:
                raise HTTPException(status_code=404, detail=f"County FIPS {fips} not found")

            # Get tract count for this county
            cur.execute("""
                SELECT COUNT(*) as tract_count,
                       AVG(estimated_total_density) as avg_tract_density,
                       MIN(estimated_total_density) as min_tract_density,
                       MAX(estimated_total_density) as max_tract_density
                FROM ny_tract_density_estimates
                WHERE county_fips = %s
            """, (fips,))
            tract_stats = cur.fetchone()

            return {
                "county": dict(county),
                "tract_statistics": {
                    "tract_count": tract_stats["tract_count"],
                    "avg_tract_density": round(float(tract_stats["avg_tract_density"] or 0), 2),
                    "min_tract_density": round(float(tract_stats["min_tract_density"] or 0), 2),
                    "max_tract_density": round(float(tract_stats["max_tract_density"] or 0), 2)
                },
                "methodology": {
                    "private_sector": "Industry-weighted BLS rates for 10 private industries (excludes edu/health and public admin to avoid double-counting with public sector)",
                    "public_sector": "Decomposed by government level using NY-specific rates (Fed: 42.2%, State: 46.3%, Local: 63.7%)",
                    "climate_multiplier": 2.26,
                    "calibration": "Auto-calibrated to match CPS statewide private density of 12.4%",
                    "note": "NY climate multiplier indicates significantly stronger union presence than expected from industry mix alone"
                }
            }


@app.get("/api/density/ny/zips")
def get_ny_zip_density(
    min_density: Optional[float] = None,
    max_density: Optional[float] = None,
    limit: int = Query(100, le=2000),
    offset: int = 0
):
    """Get union density estimates for NY ZIP codes

    Args:
        min_density: Minimum total density filter
        max_density: Maximum total density filter
        limit: Max results (default 100, max 2000)
        offset: Pagination offset
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["estimated_total_density > 0"]  # Exclude zero-density ZIPs by default
            params = []

            if min_density is not None:
                conditions.append("estimated_total_density >= %s")
                params.append(min_density)
            if max_density is not None:
                conditions.append("estimated_total_density <= %s")
                params.append(max_density)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            cur.execute(f"""
                SELECT zip_code, zip_name,
                       estimated_total_density, estimated_private_density, estimated_public_density,
                       estimated_federal_density, estimated_state_density, estimated_local_density,
                       private_class_total, govt_class_total
                FROM ny_zip_density_estimates
                {where_clause}
                ORDER BY estimated_total_density DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])

            zips = cur.fetchall()

            # Total count
            cur.execute(f"""
                SELECT COUNT(*) FROM ny_zip_density_estimates {where_clause}
            """, params)
            total = cur.fetchone()["count"]

            return {
                "zips": zips,
                "count": len(zips),
                "total": total,
                "offset": offset,
                "limit": limit
            }


@app.get("/api/density/ny/zip/{zip_code}")
def get_ny_zip_density_detail(zip_code: str):
    """Get detailed density breakdown for a single NY ZIP code

    Args:
        zip_code: 5-digit ZIP code
    """
    zip_code = zip_code.zfill(5)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM ny_zip_density_estimates
                WHERE zip_code = %s
            """, (zip_code,))
            zip_data = cur.fetchone()

            if not zip_data:
                raise HTTPException(status_code=404, detail=f"ZIP code {zip_code} not found")

            return {
                "zip": dict(zip_data),
                "methodology": "Industry-weighted density with class-of-worker adjustment"
            }


@app.get("/api/density/ny/tracts")
def get_ny_tract_density(
    county_fips: Optional[str] = None,
    min_density: Optional[float] = None,
    max_density: Optional[float] = None,
    limit: int = Query(100, le=5500),
    offset: int = 0
):
    """Get union density estimates for NY census tracts

    Args:
        county_fips: Filter by county FIPS (5-digit)
        min_density: Minimum total density filter
        max_density: Maximum total density filter
        limit: Max results (default 100, max 5500)
        offset: Pagination offset
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["estimated_total_density > 0"]
            params = []

            if county_fips:
                conditions.append("county_fips = %s")
                params.append(county_fips.zfill(5))
            if min_density is not None:
                conditions.append("estimated_total_density >= %s")
                params.append(min_density)
            if max_density is not None:
                conditions.append("estimated_total_density <= %s")
                params.append(max_density)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            cur.execute(f"""
                SELECT tract_fips, county_fips, tract_name,
                       estimated_total_density, estimated_private_density, estimated_public_density,
                       estimated_federal_density, estimated_state_density, estimated_local_density,
                       private_class_total, govt_class_total
                FROM ny_tract_density_estimates
                {where_clause}
                ORDER BY estimated_total_density DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])

            tracts = cur.fetchall()

            # Total count
            cur.execute(f"""
                SELECT COUNT(*) FROM ny_tract_density_estimates {where_clause}
            """, params)
            total = cur.fetchone()["count"]

            return {
                "tracts": tracts,
                "count": len(tracts),
                "total": total,
                "offset": offset,
                "limit": limit
            }


@app.get("/api/density/ny/tract/{tract_fips}")
def get_ny_tract_density_detail(tract_fips: str):
    """Get detailed density breakdown for a single NY census tract

    Args:
        tract_fips: 11-digit tract FIPS code
    """
    tract_fips = tract_fips.zfill(11)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM ny_tract_density_estimates
                WHERE tract_fips = %s
            """, (tract_fips,))
            tract = cur.fetchone()

            if not tract:
                raise HTTPException(status_code=404, detail=f"Tract FIPS {tract_fips} not found")

            # Get county info for context
            cur.execute("""
                SELECT county_name, estimated_total_density as county_density
                FROM ny_county_density_estimates
                WHERE county_fips = %s
            """, (tract_fips[:5],))
            county = cur.fetchone()

            return {
                "tract": dict(tract),
                "county_context": {
                    "county_name": county["county_name"] if county else None,
                    "county_density": float(county["county_density"]) if county else None
                },
                "methodology": "Industry-weighted density with class-of-worker adjustment"
            }


@app.get("/api/density/ny/summary")
def get_ny_density_summary():
    """Get summary statistics for NY density estimates at all geographic levels"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # County stats
            cur.execute("""
                SELECT 'county' as level,
                       COUNT(*) as count,
                       AVG(estimated_total_density) as avg_total,
                       MIN(estimated_total_density) as min_total,
                       MAX(estimated_total_density) as max_total,
                       AVG(estimated_private_density) as avg_private,
                       AVG(estimated_public_density) as avg_public
                FROM ny_county_density_estimates
            """)
            county_stats = cur.fetchone()

            # ZIP stats
            cur.execute("""
                SELECT 'zip' as level,
                       COUNT(*) as count,
                       COUNT(*) FILTER (WHERE estimated_total_density > 0) as nonzero_count,
                       AVG(estimated_total_density) FILTER (WHERE estimated_total_density > 0) as avg_total,
                       MIN(estimated_total_density) FILTER (WHERE estimated_total_density > 0) as min_total,
                       MAX(estimated_total_density) as max_total
                FROM ny_zip_density_estimates
            """)
            zip_stats = cur.fetchone()

            # Tract stats
            cur.execute("""
                SELECT 'tract' as level,
                       COUNT(*) as count,
                       COUNT(*) FILTER (WHERE estimated_total_density > 0) as nonzero_count,
                       AVG(estimated_total_density) FILTER (WHERE estimated_total_density > 0) as avg_total,
                       MIN(estimated_total_density) FILTER (WHERE estimated_total_density > 0) as min_total,
                       MAX(estimated_total_density) as max_total
                FROM ny_tract_density_estimates
            """)
            tract_stats = cur.fetchone()

            # Top counties
            cur.execute("""
                SELECT county_name, estimated_total_density
                FROM ny_county_density_estimates
                ORDER BY estimated_total_density DESC
                LIMIT 5
            """)
            top_counties = cur.fetchall()

            return {
                "county": {
                    "count": county_stats["count"],
                    "avg_total_density": round(float(county_stats["avg_total"]), 2),
                    "min_total_density": round(float(county_stats["min_total"]), 2),
                    "max_total_density": round(float(county_stats["max_total"]), 2),
                    "avg_private_density": round(float(county_stats["avg_private"]), 2),
                    "avg_public_density": round(float(county_stats["avg_public"]), 2)
                },
                "zip": {
                    "total_count": zip_stats["count"],
                    "nonzero_count": zip_stats["nonzero_count"],
                    "avg_total_density": round(float(zip_stats["avg_total"] or 0), 2),
                    "min_total_density": round(float(zip_stats["min_total"] or 0), 2),
                    "max_total_density": round(float(zip_stats["max_total"] or 0), 2)
                },
                "tract": {
                    "total_count": tract_stats["count"],
                    "nonzero_count": tract_stats["nonzero_count"],
                    "avg_total_density": round(float(tract_stats["avg_total"] or 0), 2),
                    "min_total_density": round(float(tract_stats["min_total"] or 0), 2),
                    "max_total_density": round(float(tract_stats["max_total"] or 0), 2)
                },
                "top_counties": [
                    {"name": c["county_name"], "density": float(c["estimated_total_density"])}
                    for c in top_counties
                ],
                "methodology": {
                    "description": "Industry-weighted private sector density (10 BLS industries, excludes edu/health), auto-calibrated to CPS statewide 12.4%",
                    "climate_multiplier": 2.26,
                    "public_sector_rates": {
                        "federal": 42.2,
                        "state": 46.3,
                        "local": 63.7
                    },
                    "source": "ACS 2025 industry and class of worker estimates"
                }
            }


# ============================================================================
# BLS EMPLOYMENT PROJECTIONS (Enhanced with correct schema)
# ============================================================================

@app.get("/api/projections/summary")
def get_projections_summary():
    """Get summary of industry projections: counts by growth category + top/bottom industries"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Count by growth category
            cur.execute("""
                SELECT growth_category, COUNT(*) as count,
                       AVG(employment_change_pct) as avg_change_pct,
                       SUM(employment_2024) as total_emp_2024
                FROM bls_industry_projections
                WHERE growth_category IS NOT NULL
                GROUP BY growth_category
                ORDER BY avg_change_pct DESC
            """)
            by_category = cur.fetchall()

            # Top 5 fastest growing
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE employment_change_pct IS NOT NULL
                ORDER BY employment_change_pct DESC
                LIMIT 5
            """)
            top_growing = cur.fetchall()

            # Top 5 fastest declining
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE employment_change_pct IS NOT NULL
                ORDER BY employment_change_pct ASC
                LIMIT 5
            """)
            top_declining = cur.fetchall()

            return {
                "by_category": by_category,
                "top_growing": top_growing,
                "top_declining": top_declining
            }


@app.get("/api/projections/industry/{naics_code}")
def get_industry_projections(naics_code: str):
    """Get employment projections for a NAICS 2-digit sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get NAICS sector info
            cur.execute("""
                SELECT naics_2digit, sector_name
                FROM naics_sectors
                WHERE naics_2digit = %s
            """, [naics_code])
            naics_info = cur.fetchone()

            # Construct BLS matrix_code from NAICS (e.g., "62" -> "620000")
            matrix_code = f"{naics_code}0000"

            # Get industry projection using constructed matrix_code
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            projection = cur.fetchone()

            if not projection:
                raise HTTPException(status_code=404, detail=f"No BLS projection found for NAICS {naics_code}")

            return {
                "naics_code": naics_code,
                "naics_sector_name": naics_info['sector_name'] if naics_info else None,
                "bls_matrix_code": matrix_code,
                "bls_industry_name": projection['industry_title'] if projection else None,
                "projection": projection
            }


@app.get("/api/projections/occupations/{naics_code}")
def get_occupation_projections_v2(naics_code: str, limit: int = Query(15, le=50)):
    """Get top occupations in a NAICS sector from bls_industry_occupation_matrix"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Construct BLS industry_code from NAICS (e.g., "62" -> "620000")
            industry_code = f"{naics_code}0000"

            # Get industry name from projections
            cur.execute("""
                SELECT industry_title FROM bls_industry_projections WHERE matrix_code = %s
            """, [industry_code])
            proj_info = cur.fetchone()

            # Get occupations for this industry
            cur.execute("""
                SELECT occupation_code, occupation_title, emp_2024, emp_change_pct
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
                ORDER BY emp_2024 DESC NULLS LAST
                LIMIT %s
            """, [industry_code, limit])
            occupations = cur.fetchall()

            if not occupations:
                raise HTTPException(status_code=404, detail=f"No occupation data found for NAICS {naics_code}")

            return {
                "naics_code": naics_code,
                "bls_industry_code": industry_code,
                "bls_industry_name": proj_info['industry_title'] if proj_info else None,
                "occupations": occupations
            }


@app.get("/api/projections/industries/{sector}")
def get_sector_sub_industries(sector: str, growth_category: str = None):
    """Get all sub-industries for a 2-digit NAICS sector with projections.

    Returns detailed breakdown of all industries within a sector (e.g., sector=23 returns
    238110 Poured Concrete, 238210 Electrical Contractors, etc.)

    Optional filter by growth_category: fast_growing, growing, stable, declining, fast_declining
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get sector name
            cur.execute("""
                SELECT sector_name FROM naics_sectors WHERE naics_2digit = %s
            """, [sector])
            sector_info = cur.fetchone()

            # Get all sub-industries for this sector
            query = """
                SELECT matrix_code, industry_title, industry_type,
                       employment_2024, employment_2034, employment_change,
                       employment_change_pct, growth_category, display_level
                FROM bls_industry_projections
                WHERE matrix_code LIKE %s
            """
            params = [f"{sector}%"]

            if growth_category:
                query += " AND growth_category = %s"
                params.append(growth_category)

            query += " ORDER BY matrix_code"

            cur.execute(query, params)
            industries = cur.fetchall()

            if not industries:
                raise HTTPException(status_code=404, detail=f"No industries found for sector {sector}")

            # Calculate sector summary
            total_2024 = sum(i['employment_2024'] or 0 for i in industries if i['matrix_code'].endswith('0000'))
            total_2034 = sum(i['employment_2034'] or 0 for i in industries if i['matrix_code'].endswith('0000'))

            return {
                "sector": sector,
                "sector_name": sector_info['sector_name'] if sector_info else None,
                "industry_count": len(industries),
                "summary": {
                    "total_employment_2024": total_2024,
                    "total_employment_2034": total_2034,
                    "total_change": total_2034 - total_2024 if total_2024 and total_2034 else None
                },
                "industries": industries
            }


@app.get("/api/projections/matrix/{matrix_code}")
def get_industry_by_matrix_code(matrix_code: str):
    """Get projection for a specific BLS industry matrix code (e.g., 238110, 621610).

    Use this for detailed sub-industry lookups. Matrix codes correspond to NAICS codes
    at various levels of detail (4-digit, 5-digit, 6-digit).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT matrix_code, industry_title, industry_type,
                       employment_2024, employment_2034, employment_change,
                       employment_change_pct, employment_cagr,
                       output_2024, output_2034, output_cagr,
                       growth_category, display_level
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            projection = cur.fetchone()

            if not projection:
                raise HTTPException(status_code=404, detail=f"No projection found for matrix code {matrix_code}")

            # Determine NAICS sector
            naics_2digit = matrix_code[:2]
            cur.execute("""
                SELECT sector_name FROM naics_sectors WHERE naics_2digit = %s
            """, [naics_2digit])
            sector_info = cur.fetchone()

            # Get occupation count for this industry
            cur.execute("""
                SELECT COUNT(*) as occ_count,
                       COUNT(*) FILTER (WHERE occupation_type = 'Line Item') as detailed_count
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
            """, [matrix_code])
            occ_counts = cur.fetchone()

            return {
                "matrix_code": matrix_code,
                "naics_sector": naics_2digit,
                "sector_name": sector_info['sector_name'] if sector_info else None,
                "projection": projection,
                "occupation_data_available": occ_counts['occ_count'] > 0,
                "occupation_count": occ_counts['occ_count'],
                "detailed_occupation_count": occ_counts['detailed_count']
            }


@app.get("/api/projections/matrix/{matrix_code}/occupations")
def get_occupations_by_matrix_code(
    matrix_code: str,
    occupation_type: str = Query(None, description="Filter by type: 'Line Item' for detailed, 'Summary' for groups"),
    min_employment: float = Query(None, description="Minimum 2024 employment (in thousands)"),
    sort_by: str = Query("employment", description="Sort by: employment, growth, change"),
    limit: int = Query(50, le=200)
):
    """Get occupation breakdown for a specific industry matrix code.

    Returns all occupations employed in the industry with 2024/2034 projections.
    Use occupation_type='Line Item' for specific job titles, 'Summary' for occupation groups.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get industry name
            cur.execute("""
                SELECT industry_title FROM bls_industry_projections WHERE matrix_code = %s
            """, [matrix_code])
            industry = cur.fetchone()

            # Build query
            query = """
                SELECT occupation_code, occupation_title, occupation_type,
                       emp_2024, emp_2024_pct_industry, emp_2024_pct_occupation,
                       emp_2034, emp_2034_pct_industry, emp_2034_pct_occupation,
                       emp_change, emp_change_pct, display_level
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
            """
            params = [matrix_code]

            if occupation_type:
                query += " AND occupation_type = %s"
                params.append(occupation_type)

            if min_employment is not None:
                query += " AND emp_2024 >= %s"
                params.append(min_employment)

            # Sort options
            if sort_by == "growth":
                query += " ORDER BY emp_change_pct DESC NULLS LAST"
            elif sort_by == "change":
                query += " ORDER BY emp_change DESC NULLS LAST"
            else:
                query += " ORDER BY emp_2024 DESC NULLS LAST"

            query += " LIMIT %s"
            params.append(limit)

            cur.execute(query, params)
            occupations = cur.fetchall()

            if not occupations:
                raise HTTPException(status_code=404, detail=f"No occupation data found for matrix code {matrix_code}")

            # Get summary stats
            cur.execute("""
                SELECT
                    SUM(emp_2024) FILTER (WHERE occupation_code = '00-0000') as total_2024,
                    SUM(emp_2034) FILTER (WHERE occupation_code = '00-0000') as total_2034,
                    COUNT(*) FILTER (WHERE occupation_type = 'Line Item') as detailed_count,
                    COUNT(*) FILTER (WHERE emp_change_pct > 0) as growing_count,
                    COUNT(*) FILTER (WHERE emp_change_pct < 0) as declining_count
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
            """, [matrix_code])
            stats = cur.fetchone()

            return {
                "matrix_code": matrix_code,
                "industry_title": industry['industry_title'] if industry else None,
                "summary": {
                    "total_employment_2024": stats['total_2024'],
                    "total_employment_2034": stats['total_2034'],
                    "detailed_occupations": stats['detailed_count'],
                    "growing_occupations": stats['growing_count'],
                    "declining_occupations": stats['declining_count']
                },
                "occupations": occupations
            }


@app.get("/api/projections/search")
def search_industry_projections(
    q: str = Query(None, description="Search industry titles"),
    growth_category: str = Query(None, description="Filter: fast_growing, growing, stable, declining, fast_declining"),
    min_employment: float = Query(None, description="Minimum 2024 employment (thousands)"),
    min_growth: float = Query(None, description="Minimum growth percentage"),
    max_growth: float = Query(None, description="Maximum growth percentage"),
    limit: int = Query(50, le=200)
):
    """Search and filter industry projections across all sectors."""
    with get_db() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT p.matrix_code, p.industry_title, p.industry_type,
                       p.employment_2024, p.employment_2034, p.employment_change,
                       p.employment_change_pct, p.growth_category,
                       ns.naics_2digit, ns.sector_name
                FROM bls_industry_projections p
                LEFT JOIN naics_sectors ns ON LEFT(p.matrix_code, 2) = ns.naics_2digit
                WHERE 1=1
            """
            params = []

            if q:
                query += " AND p.industry_title ILIKE %s"
                params.append(f"%{q}%")

            if growth_category:
                query += " AND p.growth_category = %s"
                params.append(growth_category)

            if min_employment is not None:
                query += " AND p.employment_2024 >= %s"
                params.append(min_employment)

            if min_growth is not None:
                query += " AND p.employment_change_pct >= %s"
                params.append(min_growth)

            if max_growth is not None:
                query += " AND p.employment_change_pct <= %s"
                params.append(max_growth)

            query += " ORDER BY p.employment_2024 DESC NULLS LAST LIMIT %s"
            params.append(limit)

            cur.execute(query, params)
            results = cur.fetchall()

            return {
                "query": q,
                "filters": {
                    "growth_category": growth_category,
                    "min_employment": min_employment,
                    "min_growth": min_growth,
                    "max_growth": max_growth
                },
                "count": len(results),
                "industries": results
            }


@app.get("/api/employer/{employer_id}/projections")
def get_employer_projections(employer_id: str):
    """Get industry outlook and top occupations for an employer based on their NAICS"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer info including enhanced NAICS
            cur.execute("""
                SELECT employer_id, employer_name, city, state, naics,
                       naics_detailed, naics_source, naics_confidence,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Use detailed NAICS if available, fall back to original
            naics_detailed = employer.get('naics_detailed')
            naics = employer.get('naics')
            naics_for_lookup = naics_detailed[:2] if naics_detailed else naics

            if not naics_for_lookup:
                return {
                    "employer": employer,
                    "error": "Employer has no NAICS code assigned",
                    "industry_outlook": None,
                    "top_occupations": None
                }

            # Get NAICS sector name
            cur.execute("""
                SELECT sector_name FROM naics_sectors WHERE naics_2digit = %s
            """, [naics_for_lookup])
            naics_info = cur.fetchone()

            # Construct BLS matrix_code from NAICS (e.g., "62" -> "620000")
            matrix_code = f"{naics_for_lookup}0000"

            industry_outlook = None
            top_occupations = []

            # Get industry projection
            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            industry_outlook = cur.fetchone()

            # Get top 10 occupations
            cur.execute("""
                SELECT occupation_code, occupation_title, emp_2024, emp_change_pct
                FROM bls_industry_occupation_matrix
                WHERE industry_code = %s
                ORDER BY emp_2024 DESC NULLS LAST
                LIMIT 10
            """, [matrix_code])
            top_occupations = cur.fetchall()

            return {
                "employer": employer,
                "naics_sector_name": naics_info['sector_name'] if naics_info else None,
                "naics_detailed": naics_detailed,
                "naics_source": employer.get('naics_source'),
                "naics_confidence": float(employer.get('naics_confidence')) if employer.get('naics_confidence') else None,
                "bls_matrix_code": matrix_code,
                "industry_outlook": industry_outlook,
                "top_occupations": top_occupations
            }


# Legacy endpoints for backwards compatibility
@app.get("/api/projections/naics/{naics_2digit}")
def get_naics_projections(naics_2digit: str, limit: int = Query(20, le=100)):
    """Get employment projections for a NAICS 2-digit sector (legacy)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Construct BLS matrix_code from NAICS (e.g., "62" -> "620000")
            matrix_code = f"{naics_2digit}0000"

            cur.execute("""
                SELECT matrix_code, industry_title, employment_2024, employment_2034,
                       employment_change_pct as employment_change, employment_change_pct, growth_category
                FROM bls_industry_projections
                WHERE matrix_code = %s
            """, [matrix_code])
            projections = cur.fetchall()

            summary = None
            if projections:
                p = projections[0]
                summary = {
                    "total_2024": p.get('employment_2024'),
                    "total_2034": p.get('employment_2034'),
                    "avg_change_pct": p.get('employment_change_pct'),
                    "growth_category": p.get('growth_category')
                }

            return {"naics_2digit": naics_2digit, "summary": summary, "projections": projections}


@app.get("/api/projections/top")
def get_top_projections(growing: bool = Query(True), limit: int = Query(20, le=100)):
    """Get top growing or declining industries"""
    with get_db() as conn:
        with conn.cursor() as cur:
            order = "DESC" if growing else "ASC"
            condition = "> 0" if growing else "< 0"
            cur.execute(f"""
                SELECT bip.matrix_code, bip.industry_title,
                       bip.employment_2024, bip.employment_2034,
                       bip.employment_change_pct, bip.growth_category,
                       LEFT(bip.matrix_code, 2) as naics_2digit,
                       ns.sector_name
                FROM bls_industry_projections bip
                LEFT JOIN naics_sectors ns ON LEFT(bip.matrix_code, 2) = ns.naics_2digit
                WHERE bip.employment_change_pct {condition}
                ORDER BY bip.employment_change_pct {order}
                LIMIT %s
            """, [limit])
            return {"type": "growing" if growing else "declining", "projections": cur.fetchall()}


# ============================================================================
# EMPLOYER SEARCH
# ============================================================================

@app.get("/api/employers/cities")
def get_cities_for_state(
    state: str = Query(..., description="State code (e.g., CA, NY)"),
    limit: int = Query(200, le=500)
):
    """Get cities for a state, ordered by employer count"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT UPPER(city) as city, COUNT(*) as employer_count
                FROM f7_employers_deduped
                WHERE state = %s AND city IS NOT NULL AND TRIM(city) != ''
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, UPPER(city)
                LIMIT %s
            """, [state.upper(), limit])
            return {"state": state.upper(), "cities": cur.fetchall()}


@app.get("/api/employers/search")
def search_employers(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    naics: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    metro: Optional[str] = None,
    sector: Optional[str] = None,
    has_nlrb: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search employers with filters. Use sector=PUBLIC_SECTOR to search public sector employers."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Handle public sector search separately
            if sector and sector.upper() == 'PUBLIC_SECTOR':
                conditions = ["1=1"]
                params = []

                if name:
                    conditions.append("employer_name ILIKE %s")
                    params.append(f"%{name}%")
                if state:
                    conditions.append("state = %s")
                    params.append(state.upper())
                if city:
                    conditions.append("UPPER(city) = %s")
                    params.append(city.upper())

                where_clause = " AND ".join(conditions)

                # Count
                cur.execute(f"""
                    SELECT COUNT(*) FROM ps_employers WHERE {where_clause}
                """, params)
                total = cur.fetchone()['count']

                # Results
                params.extend([limit, offset])
                cur.execute(f"""
                    SELECT id as employer_id, employer_name, city, state,
                           total_employees as latest_unit_size,
                           employer_type, employer_type as employer_subtype,
                           NULL as naics, NULL as latest_union_fnum, NULL as latest_union_name,
                           NULL as latitude, NULL as longitude, NULL as aff_abbr,
                           NULL as cbsa_code, NULL as metro_name,
                           'PUBLIC' as source_type, 'PUBLIC_SECTOR' as union_sector
                    FROM ps_employers
                    WHERE {where_clause}
                    ORDER BY total_employees DESC NULLS LAST
                    LIMIT %s OFFSET %s
                """, params)

                return {"total": total, "employers": cur.fetchall()}

            # Standard F-7 employer search
            conditions = ["1=1"]
            params = []

            if name:
                conditions.append("e.employer_name ILIKE %s")
                params.append(f"%{name}%")
            if state:
                conditions.append("e.state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(e.city) = %s")
                params.append(city.upper())
            if naics:
                conditions.append("e.naics LIKE %s")
                params.append(f"{naics}%")
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            if metro:
                conditions.append("e.cbsa_code = %s")
                params.append(metro)

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
                    e.naics_detailed, e.naics_source, e.naics_confidence,
                    e.latest_unit_size, e.latest_union_fnum, e.latest_union_name,
                    e.latitude, e.longitude, um.aff_abbr,
                    e.cbsa_code, c.cbsa_title as metro_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                LEFT JOIN cbsa_definitions c ON e.cbsa_code = c.cbsa_code
                WHERE {where_clause}
                ORDER BY e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/employers/fuzzy-search")
def fuzzy_search_employers(
    name: str = Query(..., description="Employer name to search (typo-tolerant)"),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    state: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Fuzzy search using pg_trgm similarity - catches typos and variations"""
    with get_db() as conn:
        with conn.cursor() as cur:
            state_filter = "AND e.state = %s" if state else ""
            count_params = [name, threshold]
            if state:
                count_params.append(state.upper())
            
            cur.execute(f"""
                SELECT COUNT(*) as total FROM f7_employers_deduped e
                WHERE similarity(e.employer_name, %s) > %s {state_filter}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [name, name, threshold]
            if state:
                select_params.append(state.upper())
            select_params.extend([name, limit, offset])
            
            cur.execute(f"""
                SELECT e.employer_id, e.employer_name, similarity(e.employer_name, %s) as match_score,
                       e.city, e.state, e.naics, e.naics_detailed, e.naics_source,
                       e.latest_unit_size, e.latitude, e.longitude,
                       um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE similarity(e.employer_name, %s) > %s {state_filter}
                ORDER BY similarity(e.employer_name, %s) DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)

            return {"search_term": name, "threshold": threshold, "total": total, "employers": cur.fetchall()}


@app.get("/api/employers/normalized-search")
def normalized_search_employers(
    name: str = Query(..., description="Employer name"),
    threshold: float = Query(0.35, ge=0.1, le=1.0),
    state: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search with normalized names - strips Inc, LLC, Corp, etc."""
    import re
    normalized_search = re.sub(r'\b(inc|llc|corp|corporation|company|co|ltd|limited|the)\b', '', 
                               name.lower(), flags=re.IGNORECASE).strip()
    normalized_search = re.sub(r'[^\w\s]', '', normalized_search)
    normalized_search = ' '.join(normalized_search.split())
    
    with get_db() as conn:
        with conn.cursor() as cur:
            state_filter = "AND e.state = %s" if state else ""
            
            count_params = [normalized_search, threshold]
            if state:
                count_params.append(state.upper())
            
            cur.execute(f"""
                WITH normalized AS (
                    SELECT *, regexp_replace(
                        regexp_replace(lower(employer_name), 
                            '\\m(inc|llc|corp|corporation|company|co|ltd|limited|the)\\M', '', 'gi'),
                        '[^a-z0-9\\s]', '', 'gi') as normalized_name
                    FROM f7_employers_deduped
                )
                SELECT COUNT(*) as total FROM normalized
                WHERE similarity(normalized_name, %s) > %s {state_filter}
            """, count_params)
            total = cur.fetchone()['total']
            
            select_params = [normalized_search, normalized_search, threshold]
            if state:
                select_params.append(state.upper())
            select_params.extend([normalized_search, limit, offset])
            
            cur.execute(f"""
                WITH normalized AS (
                    SELECT *, regexp_replace(
                        regexp_replace(lower(employer_name),
                            '\\m(inc|llc|corp|corporation|company|co|ltd|limited|the)\\M', '', 'gi'),
                        '[^a-z0-9\\s]', '', 'gi') as normalized_name
                    FROM f7_employers_deduped
                )
                SELECT employer_id, employer_name, normalized_name,
                       similarity(normalized_name, %s) as match_score,
                       city, state, naics, naics_detailed, naics_source,
                       latest_unit_size, latest_union_fnum, latitude, longitude,
                       um.aff_abbr
                FROM normalized n
                LEFT JOIN unions_master um ON n.latest_union_fnum::text = um.f_num
                WHERE similarity(n.normalized_name, %s) > %s {state_filter}
                ORDER BY similarity(n.normalized_name, %s) DESC, n.latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, select_params)

            return {"search_term": name, "normalized_search": normalized_search,
                    "threshold": threshold, "total": total, "employers": cur.fetchall()}


# ============================================================================
# UNIFIED EMPLOYER SEARCH (mv_employer_search + review flags)
# ============================================================================

class FlagCreate(BaseModel):
    source_type: str
    source_id: str
    flag_type: str
    notes: Optional[str] = None


@app.get("/api/employers/unified-search")
def unified_employer_search(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source_type: Optional[str] = None,
    has_union: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search across all employer sources (F7, NLRB, VR, Manual) with deduplication."""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            order_clause = "unit_size DESC NULLS LAST"

            if name:
                conditions.append("similarity(search_name, %s) > 0.2")
                params.append(name.lower())
                order_clause = "similarity(search_name, %s) DESC, unit_size DESC NULLS LAST"
            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if source_type:
                conditions.append("source_type = %s")
                params.append(source_type.upper())
            if has_union is not None:
                conditions.append("has_union = %s")
                params.append(has_union)

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"SELECT COUNT(*) FROM mv_employer_search WHERE {where_clause}", params)
            total = cur.fetchone()['count']

            # Results with flag count
            order_params = [name.lower()] if name else []
            cur.execute(f"""
                SELECT m.canonical_id, m.source_type, m.employer_name, m.city, m.state,
                       m.zip, m.naics, m.unit_size, m.union_name, m.union_fnum,
                       m.has_union, m.latitude, m.longitude,
                       COALESCE(f.flag_count, 0) AS flag_count
                FROM mv_employer_search m
                LEFT JOIN (
                    SELECT source_type || '-' || source_id AS key, COUNT(*) AS flag_count
                    FROM employer_review_flags GROUP BY source_type, source_id
                ) f ON f.key = CASE
                    WHEN m.source_type = 'F7' THEN 'F7-' || m.canonical_id
                    ELSE m.source_type || '-' || REPLACE(m.canonical_id, m.source_type || '-', '')
                END
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            """, params + order_params + [limit, offset])

            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/employers/unified-detail/{canonical_id:path}")
def unified_employer_detail(canonical_id: str):
    """Get employer detail with cross-references from all sources."""
    with get_db() as conn:
        with conn.cursor() as cur:
            if canonical_id.startswith("NLRB-"):
                source_type, source_id = "NLRB", canonical_id[5:]
            elif canonical_id.startswith("VR-"):
                source_type, source_id = "VR", canonical_id[3:]
            elif canonical_id.startswith("MANUAL-"):
                source_type, source_id = "MANUAL", canonical_id[7:]
            else:
                source_type, source_id = "F7", canonical_id

            primary = None
            cross_refs = []

            if source_type == "F7":
                cur.execute("""
                    SELECT e.*, um.aff_abbr, um.union_name as union_full_name,
                           'F7' as source_type
                    FROM f7_employers_deduped e
                    LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                    WHERE e.employer_id = %s
                """, [source_id])
                primary = cur.fetchone()

                if primary:
                    cur.execute("""
                        SELECT 'NLRB' as source_type, p.id::text as source_id,
                               p.participant_name as employer_name, p.city, p.state,
                               p.case_number, e.election_date,
                               e.eligible_voters as unit_size,
                               CASE WHEN e.union_won THEN 'Won' ELSE 'Lost' END as election_result,
                               t.labor_org_name as union_name
                        FROM nlrb_participants p
                        LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
                        LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                        WHERE p.matched_employer_id = %s AND p.participant_type = 'Employer'
                        ORDER BY e.election_date DESC NULLS LAST
                        LIMIT 20
                    """, [source_id])
                    cross_refs.extend(cur.fetchall())

                    cur.execute("""
                        SELECT 'VR' as source_type, vr.vr_case_number as source_id,
                               vr.employer_name, vr.unit_city as city, vr.unit_state as state,
                               vr.vr_case_number as case_number,
                               vr.date_voluntary_recognition::text as election_date,
                               vr.num_employees as unit_size,
                               'Vol. Recognition' as election_result,
                               vr.union_name
                        FROM nlrb_voluntary_recognition vr
                        WHERE vr.matched_employer_id = %s
                        ORDER BY vr.date_voluntary_recognition DESC NULLS LAST
                    """, [source_id])
                    cross_refs.extend(cur.fetchall())

            elif source_type == "NLRB":
                cur.execute("""
                    SELECT p.id, p.participant_name as employer_name, p.city, p.state,
                           p.address_1 as street, p.zip, p.case_number,
                           'NLRB' as source_type
                    FROM nlrb_participants p
                    WHERE p.id = %s
                """, [int(source_id)])
                primary = cur.fetchone()

                if primary:
                    cur.execute("""
                        SELECT 'NLRB' as source_type, p.id::text as source_id,
                               p.participant_name as employer_name, p.city, p.state,
                               p.case_number, e.election_date,
                               e.eligible_voters as unit_size,
                               CASE WHEN e.union_won THEN 'Won' ELSE 'Lost' END as election_result,
                               t.labor_org_name as union_name
                        FROM nlrb_participants p
                        LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
                        LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                        WHERE UPPER(p.participant_name) = UPPER(%s)
                          AND p.participant_type = 'Employer'
                          AND UPPER(COALESCE(p.state,'')) = UPPER(COALESCE(%s,''))
                        ORDER BY e.election_date DESC NULLS LAST
                        LIMIT 20
                    """, [primary['employer_name'], primary.get('state', '')])
                    cross_refs = cur.fetchall()

            elif source_type == "VR":
                cur.execute("""
                    SELECT vr.*, 'VR' as source_type
                    FROM nlrb_voluntary_recognition vr
                    WHERE vr.vr_case_number = %s
                """, [source_id])
                primary = cur.fetchone()

            elif source_type == "MANUAL":
                cur.execute("""
                    SELECT m.*, 'MANUAL' as source_type
                    FROM manual_employers m
                    WHERE m.id = %s
                """, [int(source_id)])
                primary = cur.fetchone()

            if not primary:
                raise HTTPException(status_code=404, detail="Employer not found")

            cur.execute("""
                SELECT id, flag_type, notes, created_at
                FROM employer_review_flags
                WHERE source_type = %s AND source_id = %s
                ORDER BY created_at DESC
            """, [source_type, source_id])
            flags = cur.fetchall()

            return {
                "employer": primary,
                "source_type": source_type,
                "cross_references": cross_refs,
                "flags": flags
            }


@app.post("/api/employers/flags")
def create_flag(flag: FlagCreate):
    """Create a review flag for an employer."""
    valid_types = ['ALREADY_UNION', 'DUPLICATE', 'LABOR_ORG_NOT_EMPLOYER',
                   'DEFUNCT', 'DATA_QUALITY', 'NEEDS_REVIEW', 'VERIFIED_OK']
    if flag.flag_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid flag_type. Must be one of: {valid_types}")

    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO employer_review_flags (source_type, source_id, flag_type, notes)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, flag_type, notes, created_at
                """, [flag.source_type, flag.source_id, flag.flag_type, flag.notes])
                conn.commit()
                return {"flag": cur.fetchone()}
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(status_code=409, detail="Flag already exists for this employer/type")


@app.get("/api/employers/flags/pending")
def get_pending_flags(
    flag_type: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get all flagged employers for review queue."""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            if flag_type:
                conditions.append("f.flag_type = %s")
                params.append(flag_type)

            where_clause = " AND ".join(conditions)
            params.extend([limit, offset])

            cur.execute(f"""
                SELECT f.id, f.source_type, f.source_id, f.flag_type, f.notes, f.created_at,
                       m.employer_name, m.city, m.state
                FROM employer_review_flags f
                LEFT JOIN mv_employer_search m ON m.canonical_id = CASE
                    WHEN f.source_type = 'F7' THEN f.source_id
                    ELSE f.source_type || '-' || f.source_id
                END
                WHERE {where_clause}
                ORDER BY f.created_at DESC
                LIMIT %s OFFSET %s
            """, params)
            flags = cur.fetchall()

            cur.execute(f"""
                SELECT COUNT(*) FROM employer_review_flags f WHERE {where_clause}
            """, params[:-2] if params[:-2] else [])
            total = cur.fetchone()['count']

            return {"total": total, "flags": flags}


@app.post("/api/employers/refresh-search")
def refresh_unified_search():
    """Refresh the materialized view for unified employer search."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW mv_employer_search")
            conn.commit()
            cur.execute("SELECT COUNT(*) FROM mv_employer_search")
            total = cur.fetchone()['count']
            return {"refreshed": True, "total_records": total}


@app.delete("/api/employers/flags/{flag_id}")
def delete_flag(flag_id: int):
    """Remove a review flag."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employer_review_flags WHERE id = %s RETURNING id", [flag_id])
            deleted = cur.fetchone()
            conn.commit()
            if not deleted:
                raise HTTPException(status_code=404, detail="Flag not found")
            return {"deleted": True}


@app.get("/api/employers/flags/by-employer/{canonical_id:path}")
def get_employer_flags(canonical_id: str):
    """Get all review flags for an employer by canonical_id."""
    if canonical_id.startswith("NLRB-"):
        source_type, source_id = "NLRB", canonical_id[5:]
    elif canonical_id.startswith("VR-"):
        source_type, source_id = "VR", canonical_id[3:]
    elif canonical_id.startswith("MANUAL-"):
        source_type, source_id = "MANUAL", canonical_id[7:]
    else:
        source_type, source_id = "F7", canonical_id

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, flag_type, notes, created_at
                FROM employer_review_flags
                WHERE source_type = %s AND source_id = %s
                ORDER BY created_at DESC
            """, [source_type, source_id])
            return {"flags": cur.fetchall()}


@app.get("/api/employers/flags/by-source")
def get_flags_by_source(source_type: str, source_id: str):
    """Get review flags by source_type and source_id directly (for scorecard items)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, flag_type, notes, created_at
                FROM employer_review_flags
                WHERE source_type = %s AND source_id = %s
                ORDER BY created_at DESC
            """, [source_type, source_id])
            return {"flags": cur.fetchall()}


# ============================================================================
# EMPLOYER DETAIL & RELATED (F7-specific)
# ============================================================================

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


@app.get("/api/employers/{employer_id}/similar")
def get_similar_employers(
    employer_id: str,
    limit: int = Query(10, le=50)
):
    """Get employers similar to this one (same NAICS, state, or union)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get the employer's info first
            cur.execute("""
                SELECT employer_name, state, naics, latest_union_fnum, cbsa_code
                FROM f7_employers_deduped WHERE employer_id = %s
            """, [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Find similar employers
            cur.execute("""
                SELECT e.employer_id, e.employer_name, e.city, e.state, e.naics,
                       e.latest_unit_size, e.latest_unit_size as employee_count,
                       e.latest_union_name, um.aff_abbr,
                       CASE
                           WHEN e.naics = %s AND e.state = %s THEN 3
                           WHEN e.naics = %s THEN 2
                           WHEN e.state = %s THEN 1
                           ELSE 0
                       END as similarity_score
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.employer_id != %s
                  AND (e.naics = %s OR e.state = %s OR e.latest_union_fnum = %s)
                ORDER BY similarity_score DESC, e.latest_unit_size DESC NULLS LAST
                LIMIT %s
            """, [emp['naics'], emp['state'], emp['naics'], emp['state'],
                  employer_id, emp['naics'], emp['state'], emp['latest_union_fnum'], limit])

            return {"similar_employers": cur.fetchall()}


@app.get("/api/employers/{employer_id}/osha")
def get_employer_osha(employer_id: str):
    """Get OSHA violations and safety data for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check employer exists
            cur.execute("SELECT employer_name FROM f7_employers_deduped WHERE employer_id = %s", [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get OSHA matches via osha_f7_matches with violation summaries
            cur.execute("""
                SELECT o.establishment_id, o.estab_name, o.site_address, o.site_city,
                       o.site_state, o.site_zip, o.naics_code, o.sic_code,
                       o.employee_count, o.total_inspections, o.last_inspection_date,
                       m.match_method, m.match_confidence,
                       COALESCE(vs.willful_count, 0) as willful_count,
                       COALESCE(vs.repeat_count, 0) as repeat_count,
                       COALESCE(vs.serious_count, 0) as serious_count,
                       COALESCE(vs.other_count, 0) as other_count,
                       COALESCE(vs.total_violations, 0) as total_violations,
                       COALESCE(vs.total_penalties, 0) as total_penalties
                FROM osha_f7_matches m
                JOIN osha_establishments o ON m.establishment_id = o.establishment_id
                LEFT JOIN (
                    SELECT establishment_id,
                           SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) as willful_count,
                           SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) as repeat_count,
                           SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) as serious_count,
                           SUM(CASE WHEN violation_type = 'O' THEN violation_count ELSE 0 END) as other_count,
                           SUM(violation_count) as total_violations,
                           SUM(total_penalties) as total_penalties
                    FROM osha_violation_summary
                    GROUP BY establishment_id
                ) vs ON o.establishment_id = vs.establishment_id
                WHERE m.f7_employer_id = %s
                ORDER BY vs.total_penalties DESC NULLS LAST
            """, [employer_id])
            establishments = cur.fetchall()

            # Calculate summary stats
            summary = {
                "total_establishments": len(establishments),
                "total_inspections": sum(e['total_inspections'] or 0 for e in establishments),
                "total_violations": sum(e['total_violations'] or 0 for e in establishments),
                "total_penalties": sum(float(e['total_penalties'] or 0) for e in establishments),
                "willful_violations": sum(e['willful_count'] or 0 for e in establishments),
                "serious_violations": sum(e['serious_count'] or 0 for e in establishments)
            }

            return {
                "employer_name": emp['employer_name'],
                "osha_summary": summary,
                "establishments": establishments
            }


@app.get("/api/employers/{employer_id}/nlrb")
def get_employer_nlrb(employer_id: str):
    """Get NLRB elections and ULP cases for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check employer exists
            cur.execute("SELECT employer_name FROM f7_employers_deduped WHERE employer_id = %s", [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # NLRB elections
            cur.execute("""
                SELECT e.case_number, e.election_date, e.election_type, e.union_won,
                       e.eligible_voters, e.vote_margin, t.labor_org_name as union_name, um.aff_abbr
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
                SELECT c.case_number, c.case_type, c.earliest_date, c.latest_date,
                       ct.description as case_type_desc
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                JOIN nlrb_participants p ON c.case_number = p.case_number
                    AND p.participant_type = 'Charged Party'
                WHERE p.matched_employer_id = %s AND ct.case_category = 'unfair_labor_practice'
                ORDER BY c.earliest_date DESC LIMIT 50
            """, [employer_id])
            ulp_cases = cur.fetchall()

            return {
                "employer_name": emp['employer_name'],
                "elections": elections,
                "elections_summary": {
                    "total": len(elections),
                    "union_wins": sum(1 for e in elections if e['union_won']),
                    "union_losses": sum(1 for e in elections if e['union_won'] is False),
                    "win_rate": round(100.0 * sum(1 for e in elections if e['union_won']) / max(len(elections), 1), 1)
                },
                "ulp_cases": ulp_cases,
                "ulp_summary": {
                    "total": len(ulp_cases)
                }
            }


# ============================================================================
# HISTORICAL TRENDS
# ============================================================================

@app.get("/api/trends/national")
def get_national_trends():
    """Get national union membership trends by year (2010-2024) with deduplicated estimates"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get raw trends by year
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members_raw,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """)
            raw_trends = cur.fetchall()

            # Get current deduplicated total and ratio from view
            cur.execute("""
                SELECT
                    SUM(CASE WHEN count_members THEN members ELSE 0 END) as deduplicated_total,
                    SUM(members) as raw_total
                FROM v_union_members_deduplicated
            """)
            dedup_stats = cur.fetchone()

            # Calculate deduplication ratio (typically ~0.20-0.21)
            dedup_ratio = 0.20  # fallback
            if dedup_stats and dedup_stats['raw_total'] and dedup_stats['raw_total'] > 0:
                dedup_ratio = dedup_stats['deduplicated_total'] / dedup_stats['raw_total']

            # Apply ratio to get estimated deduplicated membership by year
            trends = []
            for row in raw_trends:
                trend = dict(row)
                # Estimate deduplicated members using the ratio
                trend['total_members_dedup'] = int(row['total_members_raw'] * dedup_ratio)
                trends.append(trend)

            return {
                "description": "National union membership trends",
                "note": "total_members_dedup is estimated using current deduplication ratio. BLS benchmark is ~14-15M",
                "dedup_ratio": round(dedup_ratio, 4),
                "current_dedup_total": dedup_stats['deduplicated_total'] if dedup_stats else None,
                "trends": trends
            }


@app.get("/api/trends/affiliations/summary")
def get_affiliation_trends_summary():
    """Get membership trends summary for top affiliations"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH yearly AS (
                    SELECT aff_abbr,
                           yr_covered,
                           SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as members
                    FROM lm_data
                    WHERE aff_abbr IS NOT NULL AND yr_covered IN (2010, 2024)
                    GROUP BY aff_abbr, yr_covered
                ),
                pivoted AS (
                    SELECT aff_abbr,
                           MAX(CASE WHEN yr_covered = 2010 THEN members END) as members_2010,
                           MAX(CASE WHEN yr_covered = 2024 THEN members END) as members_2024
                    FROM yearly
                    GROUP BY aff_abbr
                )
                SELECT aff_abbr,
                       members_2010,
                       members_2024,
                       members_2024 - members_2010 as change,
                       ROUND(100.0 * (members_2024 - members_2010) / NULLIF(members_2010, 0), 1) as pct_change
                FROM pivoted
                WHERE members_2024 > 10000
                ORDER BY members_2024 DESC
                LIMIT 30
            """)
            return {"affiliations": cur.fetchall()}


@app.get("/api/trends/by-affiliation/{aff_abbr}")
def get_affiliation_trends(aff_abbr: str):
    """Get membership trends for a specific affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE aff_abbr = %s AND yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """, [aff_abbr.upper()])
            trends = cur.fetchall()
            
            return {
                "affiliation": aff_abbr.upper(),
                "trends": trends
            }


@app.get("/api/trends/states/summary")
def get_state_trends_summary():
    """Get membership summary by state for latest year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH state_data AS (
                    SELECT state,
                           yr_covered,
                           SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as members,
                           COUNT(DISTINCT f_num) as union_count
                    FROM lm_data
                    WHERE state IS NOT NULL AND yr_covered IN (2010, 2024)
                    GROUP BY state, yr_covered
                ),
                pivoted AS (
                    SELECT state,
                           MAX(CASE WHEN yr_covered = 2010 THEN members END) as members_2010,
                           MAX(CASE WHEN yr_covered = 2024 THEN members END) as members_2024,
                           MAX(CASE WHEN yr_covered = 2024 THEN union_count END) as unions_2024
                    FROM state_data
                    GROUP BY state
                )
                SELECT state,
                       members_2010,
                       members_2024,
                       unions_2024,
                       ROUND(100.0 * (members_2024 - members_2010) / NULLIF(members_2010, 0), 1) as pct_change
                FROM pivoted
                WHERE members_2024 > 0
                ORDER BY members_2024 DESC
            """)
            return {"states": cur.fetchall()}


@app.get("/api/trends/by-state/{state}")
def get_state_trends(state: str):
    """Get membership trends for a specific state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE state = %s AND yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """, [state.upper()])
            trends = cur.fetchall()
            
            return {
                "state": state.upper(),
                "trends": trends
            }


@app.get("/api/trends/elections")
def get_election_trends():
    """Get NLRB election trends by year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(YEAR FROM election_date)::int as year,
                       COUNT(*) as total_elections,
                       SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
                       SUM(CASE WHEN union_won = false THEN 1 ELSE 0 END) as union_losses,
                       SUM(eligible_voters) as total_voters,
                       ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) / 
                           NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections
                WHERE election_date IS NOT NULL 
                  AND union_won IS NOT NULL
                  AND EXTRACT(YEAR FROM election_date) BETWEEN 2007 AND 2024
                GROUP BY EXTRACT(YEAR FROM election_date)
                ORDER BY year
            """)
            return {"election_trends": cur.fetchall()}


@app.get("/api/trends/elections/by-affiliation/{aff_abbr}")
def get_election_trends_by_affiliation(aff_abbr: str):
    """Get NLRB election trends for a specific union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(YEAR FROM e.election_date)::int as year,
                       COUNT(DISTINCT e.case_number) as total_elections,
                       SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
                       ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) / 
                           NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections e
                JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE um.aff_abbr = %s
                  AND e.election_date IS NOT NULL 
                  AND e.union_won IS NOT NULL
                  AND EXTRACT(YEAR FROM e.election_date) BETWEEN 2007 AND 2024
                GROUP BY EXTRACT(YEAR FROM e.election_date)
                ORDER BY year
            """, [aff_abbr.upper()])
            
            return {
                "affiliation": aff_abbr.upper(),
                "election_trends": cur.fetchall()
            }


@app.get("/api/trends/sectors")
def get_sector_trends():
    """Get employer distribution by NAICS sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT LEFT(e.naics, 2) as naics_2digit,
                       ns.sector_name,
                       COUNT(*) as employer_count,
                       SUM(e.latest_unit_size) as total_workers,
                       ROUND(AVG(e.latest_unit_size), 0) as avg_unit_size
                FROM f7_employers_deduped e
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE e.naics IS NOT NULL AND LENGTH(e.naics) >= 2
                GROUP BY LEFT(e.naics, 2), ns.sector_name
                ORDER BY COUNT(*) DESC
            """)
            return {"sectors": cur.fetchall()}


# ============================================================================
# UNION SEARCH
# ============================================================================

@app.get("/api/unions/cities")
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


@app.get("/api/unions/search")
def search_unions(
    name: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    union_type: Optional[str] = None,
    min_members: Optional[int] = None,
    has_employers: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search unions with filters including display names and hierarchy type"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if name:
                # Search union_name, local_number, and display_name
                conditions.append("""(
                    um.union_name ILIKE %s 
                    OR um.local_number = %s 
                    OR v.display_name ILIKE %s
                )""")
                clean_name = name.replace('local ', '').replace('Local ', '').strip()
                params.extend([f"%{name}%", clean_name, f"%{name}%"])
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


@app.get("/api/unions/types")
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


@app.get("/api/unions/cities")
def get_union_cities(
    state: str = Query(..., description="State code (e.g., CA, NY)"),
    limit: int = Query(200, le=500)
):
    """Get cities for a state with union counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT UPPER(city) as city, COUNT(*) as union_count
                FROM unions_master
                WHERE state = %s AND city IS NOT NULL AND TRIM(city) != ''
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, UPPER(city)
                LIMIT %s
            """, [state.upper(), limit])
            return {"state": state.upper(), "cities": cur.fetchall()}


@app.get("/api/unions/national")
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


@app.get("/api/unions/national/{aff_abbr}")
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


@app.get("/api/unions/{f_num}/employers")
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
                SELECT f_num, union_name, display_name, local_number, city, state, members, f7_employer_count
                FROM v_union_display_names
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

            elections = cur.fetchall()
            # Add law firm detection flag to each election
            for election in elections:
                election['is_law_firm'] = is_likely_law_firm(election.get('employer_name'))

            return {"total": total, "limit": limit, "offset": offset, "elections": elections}


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
            
            # Employers (with deduplication stats)
            cur.execute("""
                SELECT COUNT(*) as total_employers,
                    SUM(latest_unit_size) as total_workers_raw,
                    SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as covered_workers,
                    COUNT(DISTINCT state) as states,
                    COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
                    ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
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


@app.get("/api/stats/breakdown")
def get_stats_breakdown(
    state: str = None,
    naics_code: str = None,
    cbsa_code: str = None,
    name: str = None
):
    """Get breakdown statistics for the filter panel"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Build WHERE clause (use f. prefix for joined queries)
            conditions = ["f.exclude_from_counts = FALSE"]
            params = []

            if state:
                conditions.append("f.state = %s")
                params.append(state)
            if naics_code:
                conditions.append("f.naics LIKE %s")
                params.append(f"{naics_code}%")
            if cbsa_code:
                conditions.append("f.cbsa_code = %s")
                params.append(cbsa_code)
            if name:
                conditions.append("f.employer_name ILIKE %s")
                params.append(f"%{name}%")

            where_clause = " AND ".join(conditions)

            # Totals
            cur.execute(f"""
                SELECT COUNT(*) as total_employers,
                       COALESCE(SUM(f.latest_unit_size), 0) as total_workers,
                       COUNT(DISTINCT f.latest_union_fnum) as total_locals
                FROM f7_employers_deduped f
                WHERE {where_clause}
            """, params)
            totals = cur.fetchone()

            # By Industry (top 5 NAICS 2-digit)
            cur.execute(f"""
                SELECT LEFT(f.naics, 2) as naics_code,
                       COALESCE(ns.sector_name, LEFT(f.naics, 2)) as industry_name,
                       COUNT(*) as employer_count, COALESCE(SUM(f.latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN naics_sectors ns ON LEFT(f.naics, 2) = ns.naics_2digit
                WHERE {where_clause} AND f.naics IS NOT NULL AND LENGTH(f.naics) >= 2
                GROUP BY LEFT(f.naics, 2), ns.sector_name
                ORDER BY worker_count DESC NULLS LAST
                LIMIT 5
            """, params)
            by_industry = cur.fetchall()

            # By Metro (top 5)
            cur.execute(f"""
                SELECT f.cbsa_code, COALESCE(c.cbsa_title, f.cbsa_code) as metro_name,
                       COUNT(*) as employer_count, COALESCE(SUM(latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN cbsa_definitions c ON f.cbsa_code = c.cbsa_code
                WHERE {where_clause} AND f.cbsa_code IS NOT NULL
                GROUP BY f.cbsa_code, c.cbsa_title
                ORDER BY worker_count DESC NULLS LAST
                LIMIT 5
            """, params)
            by_metro = cur.fetchall()

            # By Sector (union sector - Private, Public, Federal, RLA)
            cur.execute(f"""
                SELECT COALESCE(um.sector, 'Unknown') as sector_name,
                       COUNT(*) as employer_count, COALESCE(SUM(f.latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN unions_master um ON f.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
                GROUP BY um.sector
                ORDER BY worker_count DESC NULLS LAST
            """, params)
            by_sector = cur.fetchall()

            return {
                "totals": totals,
                "by_sector": by_sector,
                "by_industry": by_industry,
                "by_metro": by_metro
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
# OSHA SAFETY DATA
# ============================================================================

@app.get("/api/osha/summary")
def get_osha_summary():
    """Get OSHA database summary statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM osha_establishments) as total_establishments,
                    (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'Y') as union_establishments,
                    (SELECT COUNT(*) FROM osha_establishments WHERE union_status = 'N') as nonunion_establishments,
                    (SELECT SUM(violation_count) FROM osha_violation_summary) as total_violations,
                    (SELECT SUM(total_penalties) FROM osha_violation_summary) as total_penalties,
                    (SELECT COUNT(*) FROM osha_accidents) as total_accidents,
                    (SELECT COUNT(*) FROM osha_accidents WHERE is_fatality = true) as fatality_incidents,
                    (SELECT COUNT(*) FROM osha_f7_matches) as f7_matches,
                    (SELECT COUNT(DISTINCT f7_employer_id) FROM osha_f7_matches) as unique_f7_employers_matched
            """)
            return {"summary": cur.fetchone()}


@app.get("/api/osha/establishments/search")
def search_osha_establishments(
    q: Optional[str] = None,
    state: Optional[str] = None,
    union_status: Optional[str] = None,
    risk_level: Optional[str] = None,
    naics: Optional[str] = None,
    f7_matched: Optional[bool] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0
):
    """Search OSHA establishments with filters"""
    conditions = []
    params = []
    
    if q:
        conditions.append("(estab_name_normalized ILIKE %s OR estab_name ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if union_status:
        conditions.append("union_status = %s")
        params.append(union_status.upper())
    if risk_level:
        conditions.append("risk_level = %s")
        params.append(risk_level.upper())
    if naics:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics}%")
    if f7_matched is not None:
        if f7_matched:
            conditions.append("f7_employer_id IS NOT NULL")
        else:
            conditions.append("f7_employer_id IS NULL")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT establishment_id, estab_name, site_address, site_city, site_state, site_zip,
                       naics_code, union_status, employee_count, total_inspections, last_inspection_date,
                       willful_violations, repeat_violations, serious_violations, total_violations, 
                       total_penalties, accidents, fatalities, risk_level,
                       f7_employer_id, f7_employer_name, latest_union_name, match_confidence
                FROM v_osha_establishment_search
                WHERE {where_clause}
                ORDER BY total_penalties DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            results = cur.fetchall()
            
            cur.execute(f"SELECT COUNT(*) as cnt FROM v_osha_establishment_search WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            return {"establishments": results, "total": total, "limit": limit, "offset": offset}


@app.get("/api/osha/establishments/{establishment_id}")
def get_osha_establishment(establishment_id: str):
    """Get detailed OSHA establishment info including violations and accidents"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get establishment
            cur.execute("SELECT * FROM v_osha_establishment_search WHERE establishment_id = %s", [establishment_id])
            establishment = cur.fetchone()
            if not establishment:
                raise HTTPException(status_code=404, detail="Establishment not found")
            
            # Get violations summary
            cur.execute("""
                SELECT violation_type, violation_count, total_penalties, 
                       first_violation_date, last_violation_date
                FROM osha_violation_summary WHERE establishment_id = %s
                ORDER BY violation_count DESC
            """, [establishment_id])
            violations = cur.fetchall()
            
            # Get recent violations detail
            cur.execute("""
                SELECT activity_nr, violation_type, issuance_date, current_penalty, standard
                FROM osha_violations_detail WHERE establishment_id = %s
                ORDER BY issuance_date DESC LIMIT 20
            """, [establishment_id])
            recent_violations = cur.fetchall()
            
            # Get accidents
            cur.execute("""
                SELECT summary_nr, event_date, is_fatality, injury_count, hospitalized, event_description
                FROM osha_accidents WHERE establishment_id = %s
                ORDER BY event_date DESC
            """, [establishment_id])
            accidents = cur.fetchall()
            
            return {
                "establishment": establishment,
                "violation_summary": violations,
                "recent_violations": recent_violations,
                "accidents": accidents
            }


@app.get("/api/osha/by-state")
def get_osha_by_state():
    """Get OSHA summary statistics by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_osha_state_summary ORDER BY establishments DESC")
            return {"states": cur.fetchall()}


@app.get("/api/osha/high-severity")
def get_osha_high_severity(
    state: Optional[str] = None,
    violation_type: Optional[str] = None,
    limit: int = Query(default=100, le=500)
):
    """Get recent high-severity violations (Willful/Repeat)"""
    conditions = []
    params = []
    
    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if violation_type:
        conditions.append("violation_type = %s")
        params.append(violation_type.upper())
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM v_osha_high_severity_recent
                WHERE {where_clause}
                ORDER BY issuance_date DESC
                LIMIT %s
            """, params + [limit])
            return {"violations": cur.fetchall()}


@app.get("/api/osha/organizing-targets")
def get_osha_organizing_targets(
    state: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """Get non-union establishments with significant safety violations (organizing targets)"""
    conditions = []
    params = []
    
    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if risk_level:
        conditions.append("risk_level = %s")
        params.append(risk_level.upper())
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM v_osha_organizing_targets
                WHERE {where_clause}
                ORDER BY 
                    CASE risk_level 
                        WHEN 'CRITICAL' THEN 1 
                        WHEN 'HIGH' THEN 2 
                        WHEN 'MODERATE' THEN 3 
                        ELSE 4 
                    END,
                    total_penalties DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            results = cur.fetchall()
            
            cur.execute(f"SELECT COUNT(*) as cnt FROM v_osha_organizing_targets WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            return {"targets": results, "total": total, "limit": limit, "offset": offset}


@app.get("/api/organizing/scorecard")
def get_organizing_scorecard(
    state: Optional[str] = None,
    naics_2digit: Optional[str] = None,
    min_employees: int = Query(default=25),
    max_employees: int = Query(default=5000),
    min_score: int = Query(default=0),
    has_contracts: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0
):
    """
    Get scored organizing targets based on 8-factor system (0-100 points):
    - Company union shops (20): Related locations with union presence
    - Industry density (10): Union density in NAICS sector
    - State density (10): State union membership relative to national
    - Size (10): Establishment size sweet spot
    - OSHA (10): Violation severity and recency
    - NLRB (10): Past election activity
    - Contracts (10): Government contract funding
    - Projections (10): BLS industry growth outlook
    """
    conditions = ["employee_count >= %s", "employee_count <= %s"]
    params = [min_employees, max_employees]

    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if naics_2digit:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics_2digit}%")

    where_clause = " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Pre-fetch lookup data for efficiency
            cur.execute("SELECT naics_2digit, union_density_pct FROM v_naics_union_density")
            industry_density = {r['naics_2digit']: float(r['union_density_pct'] or 0) for r in cur.fetchall()}

            # Use members_total as a proxy for state union density (higher = more union friendly)
            cur.execute("SELECT state, members_total FROM epi_state_benchmarks")
            state_density = {r['state']: float(r['members_total'] or 0) for r in cur.fetchall()}

            cur.execute("SELECT matrix_code, employment_change_pct FROM bls_industry_projections")
            projections = {r['matrix_code']: float(r['employment_change_pct'] or 0) for r in cur.fetchall()}

            # Get base results
            cur.execute(f"""
                SELECT * FROM v_osha_organizing_targets
                WHERE {where_clause}
                ORDER BY total_penalties DESC NULLS LAST
                LIMIT 500
            """, params)
            base_results = cur.fetchall()

            # Calculate scores in Python
            scored_results = []
            for r in base_results:
                naics_2 = (r.get('naics_code') or '')[:2]
                site_state = r.get('site_state', '')
                emp_count = r.get('employee_count', 0) or 0

                # 1. Company union shops (simplified - check if matched employer exists)
                score_company_unions = 20 if r.get('matched_employer_id') else 0

                # 2. Industry density
                ind_pct = industry_density.get(naics_2, 0)
                score_industry_density = 10 if ind_pct > 20 else 8 if ind_pct > 10 else 5 if ind_pct > 5 else 2

                # 3. State density (using members_total as proxy - higher counts = stronger unions)
                st_members = state_density.get(site_state, 0)
                score_state_density = 10 if st_members > 1000000 else 8 if st_members > 500000 else 5 if st_members > 200000 else 2

                # 4. Size
                score_size = 10 if 100 <= emp_count <= 500 else 5 if emp_count > 25 else 2

                # 5. OSHA violations
                willful = r.get('willful_count', 0) or 0
                repeat = r.get('repeat_count', 0) or 0
                serious = r.get('serious_count', 0) or 0
                score_osha = min(10, willful * 4 + repeat * 2 + serious)

                # 6. NLRB (simplified - based on violation history as proxy)
                score_nlrb = 5 if r.get('total_violations', 0) > 5 else 2

                # 7. Contracts (simplified)
                score_contracts = 0

                # 8. Projections
                proj_pct = projections.get(f"{naics_2}0000", 0)
                score_projections = 10 if proj_pct > 10 else 7 if proj_pct > 5 else 4 if proj_pct > 0 else 2

                organizing_score = (score_company_unions + score_industry_density + score_state_density +
                                   score_size + score_osha + score_nlrb + score_contracts + score_projections)

                if organizing_score >= min_score:
                    # Create explicit dict to ensure proper serialization
                    result = {
                        'establishment_id': r.get('establishment_id'),
                        'estab_name': r.get('estab_name'),
                        'site_address': r.get('site_address'),
                        'site_city': r.get('site_city'),
                        'site_state': r.get('site_state'),
                        'site_zip': r.get('site_zip'),
                        'naics_code': r.get('naics_code'),
                        'employee_count': r.get('employee_count'),
                        'total_inspections': r.get('total_inspections'),
                        'last_inspection_date': str(r.get('last_inspection_date')) if r.get('last_inspection_date') else None,
                        'willful_count': r.get('willful_count'),
                        'repeat_count': r.get('repeat_count'),
                        'serious_count': r.get('serious_count'),
                        'total_violations': r.get('total_violations'),
                        'total_penalties': float(r.get('total_penalties')) if r.get('total_penalties') else None,
                        'accident_count': r.get('accident_count'),
                        'fatality_count': r.get('fatality_count'),
                        'risk_level': r.get('risk_level'),
                        'matched_employer_id': r.get('matched_employer_id'),
                        'organizing_score': organizing_score,
                        'score_breakdown': {
                            'company_unions': score_company_unions,
                            'industry_density': score_industry_density,
                            'state_density': score_state_density,
                            'size': score_size,
                            'osha': score_osha,
                            'nlrb': score_nlrb,
                            'contracts': score_contracts,
                            'projections': score_projections
                        }
                    }
                    scored_results.append(result)

            # Sort by score and apply pagination
            scored_results.sort(key=lambda x: x['organizing_score'], reverse=True)
            paginated = scored_results[offset:offset + limit]

            cur.execute(f"""
                SELECT COUNT(*) as cnt FROM v_osha_organizing_targets
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['cnt']

            return {
                "results": paginated,
                "total": total,
                "scored_count": len(scored_results),
                "limit": limit,
                "offset": offset
            }


@app.get("/api/organizing/scorecard/{estab_id}")
def get_scorecard_detail(estab_id: str):
    """Get detailed scorecard for a specific establishment with 8-factor breakdown"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get base establishment data
            cur.execute("""
                SELECT * FROM v_osha_organizing_targets WHERE establishment_id = %s
            """, [estab_id])
            base = cur.fetchone()
            if not base:
                raise HTTPException(status_code=404, detail="Establishment not found")

            naics_2 = base.get('naics_code', '')[:2] if base.get('naics_code') else None
            state = base.get('site_state')
            emp_count = base.get('employee_count', 0)
            estab_name = base.get('estab_name', '')

            # Calculate individual factor scores
            # 1. Company union shops (check for related union locations)
            cur.execute("""
                SELECT COUNT(*) > 0 as has_union FROM f7_employers_deduped
                WHERE similarity(employer_name_aggressive, %s) > 0.5
            """, [estab_name])
            has_related_union = cur.fetchone()['has_union']
            score_company_unions = 20 if has_related_union else 0

            # 2. Industry density
            score_industry_density = 2
            if naics_2:
                cur.execute("""
                    SELECT union_density_pct FROM v_naics_union_density WHERE naics_2digit = %s
                """, [naics_2])
                density_row = cur.fetchone()
                if density_row and density_row['union_density_pct']:
                    pct = float(density_row['union_density_pct'])
                    score_industry_density = 10 if pct > 20 else 8 if pct > 10 else 5 if pct > 5 else 2

            # 3. State density (using members_total as proxy)
            score_state_density = 2
            if state:
                cur.execute("""
                    SELECT members_total FROM epi_state_benchmarks WHERE state = %s
                """, [state])
                state_row = cur.fetchone()
                if state_row and state_row['members_total']:
                    members = float(state_row['members_total'])
                    score_state_density = 10 if members > 1000000 else 8 if members > 500000 else 5 if members > 200000 else 2

            # 4. Size score
            score_size = 10 if 100 <= emp_count <= 500 else 5 if emp_count > 25 else 2

            # 5. OSHA score
            willful = base.get('willful_count', 0) or 0
            repeat = base.get('repeat_count', 0) or 0
            serious = base.get('serious_count', 0) or 0
            score_osha = min(10, willful * 4 + repeat * 2 + serious)

            # 6. NLRB score
            cur.execute("""
                SELECT COUNT(*) as cnt FROM nlrb_participants
                WHERE participant_name ILIKE %s AND participant_type = 'Employer'
            """, [f"%{estab_name[:20]}%"])
            nlrb_count = cur.fetchone()['cnt']
            score_nlrb = min(10, nlrb_count * 5)

            # 7. Contracts score
            cur.execute("""
                SELECT COALESCE(SUM(current_amount), 0) as total FROM ny_state_contracts
                WHERE vendor_name ILIKE %s
            """, [f"%{estab_name[:15]}%"])
            ny_funding = cur.fetchone()['total'] or 0
            cur.execute("""
                SELECT COALESCE(SUM(current_amount), 0) as total FROM nyc_contracts
                WHERE vendor_name ILIKE %s
            """, [f"%{estab_name[:15]}%"])
            nyc_funding = cur.fetchone()['total'] or 0
            total_funding = ny_funding + nyc_funding
            score_contracts = 10 if total_funding > 5000000 else 7 if total_funding > 1000000 else 4 if total_funding > 100000 else 2 if total_funding > 0 else 0

            # 8. Projections score
            score_projections = 4
            if naics_2:
                cur.execute("""
                    SELECT employment_change_pct FROM bls_industry_projections WHERE matrix_code = %s
                """, [f"{naics_2}0000"])
                proj_row = cur.fetchone()
                if proj_row and proj_row['employment_change_pct']:
                    change = float(proj_row['employment_change_pct'])
                    score_projections = 10 if change > 10 else 7 if change > 5 else 4 if change > 0 else 2

            organizing_score = (score_company_unions + score_industry_density + score_state_density +
                              score_size + score_osha + score_nlrb + score_contracts + score_projections)

            return {
                "establishment": base,
                "organizing_score": organizing_score,
                "score_breakdown": {
                    "company_unions": score_company_unions,
                    "industry_density": score_industry_density,
                    "state_density": score_state_density,
                    "size": score_size,
                    "osha": score_osha,
                    "nlrb": score_nlrb,
                    "contracts": score_contracts,
                    "projections": score_projections
                },
                "contracts": {
                    "contract_count": 1 if total_funding > 0 else 0,
                    "total_funding": total_funding
                },
                "context": {
                    "has_related_union": has_related_union,
                    "nlrb_count": nlrb_count
                }
            }


@app.get("/api/osha/employer-safety/{f7_employer_id}")
def get_employer_safety_profile(f7_employer_id: str):
    """Get OSHA safety profile for an F-7 employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_employer_safety_profile 
                WHERE employer_id = %s
            """, [f7_employer_id])
            profiles = cur.fetchall()
            if not profiles:
                raise HTTPException(status_code=404, detail="No OSHA data found for this employer")
            return {"safety_profiles": profiles}


# ============================================================================
# WHD - WAGE & HOUR DIVISION VIOLATIONS (National WHISARD Data)
# ============================================================================

@app.get("/api/whd/summary")
def get_whd_summary():
    """Get WHD national database summary statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM whd_cases) as total_cases,
                    (SELECT COUNT(DISTINCT case_id) FROM whd_cases) as unique_case_ids,
                    (SELECT COUNT(DISTINCT state) FROM whd_cases WHERE state IS NOT NULL) as states_covered,
                    (SELECT SUM(COALESCE(backwages_amount, 0)) FROM whd_cases) as total_backwages,
                    (SELECT SUM(COALESCE(civil_penalties, 0)) FROM whd_cases) as total_penalties,
                    (SELECT SUM(COALESCE(employees_violated, 0)) FROM whd_cases) as total_employees_violated,
                    (SELECT SUM(COALESCE(total_violations, 0)) FROM whd_cases) as total_violations,
                    (SELECT COUNT(*) FROM whd_cases WHERE flsa_repeat_violator = TRUE) as repeat_violators,
                    (SELECT MIN(findings_start_date) FROM whd_cases WHERE findings_start_date IS NOT NULL) as earliest_finding,
                    (SELECT MAX(findings_end_date) FROM whd_cases WHERE findings_end_date IS NOT NULL) as latest_finding
            """)
            summary = cur.fetchone()

            # Top states
            cur.execute("""
                SELECT state, COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                       SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                       SUM(COALESCE(employees_violated, 0)) as employees_violated
                FROM whd_cases
                WHERE state IS NOT NULL
                GROUP BY state
                ORDER BY case_count DESC
                LIMIT 10
            """)
            top_states = cur.fetchall()

            # Top industries
            cur.execute("""
                SELECT naics_code, COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages
                FROM whd_cases
                WHERE naics_code IS NOT NULL
                GROUP BY naics_code
                ORDER BY case_count DESC
                LIMIT 10
            """)
            top_industries = cur.fetchall()

            # Match coverage
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL) as f7_matched,
                    (SELECT COUNT(*) FROM f7_employers_deduped) as f7_total,
                    (SELECT COUNT(*) FROM mergent_employers WHERE whd_violation_count IS NOT NULL) as mergent_matched,
                    (SELECT COUNT(*) FROM mergent_employers) as mergent_total
            """)
            coverage = cur.fetchone()

            return {
                "summary": summary,
                "top_states": top_states,
                "top_industries": top_industries,
                "match_coverage": coverage
            }


@app.get("/api/whd/search")
def search_whd_cases(
    q: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    naics: Optional[str] = None,
    min_backwages: Optional[float] = None,
    repeat_only: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search WHD cases by employer name, state, city, NAICS"""
    conditions = []
    params = []

    if q:
        conditions.append("(trade_name ILIKE %s OR legal_name ILIKE %s OR name_normalized ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q.lower()}%"])
    if state:
        conditions.append("state = %s")
        params.append(state.upper())
    if city:
        conditions.append("city ILIKE %s")
        params.append(f"%{city}%")
    if naics:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics}%")
    if min_backwages:
        conditions.append("backwages_amount >= %s")
        params.append(min_backwages)
    if repeat_only:
        conditions.append("flsa_repeat_violator = TRUE")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) as cnt FROM whd_cases WHERE {where_clause}", params)
            total = cur.fetchone()['cnt']

            query_params = params + [limit, offset]
            cur.execute(f"""
                SELECT case_id, trade_name, legal_name, city, state, zip_code, naics_code,
                       total_violations, civil_penalties, employees_violated,
                       backwages_amount, flsa_violations, flsa_repeat_violator,
                       flsa_child_labor_violations, flsa_child_labor_minors,
                       findings_start_date, findings_end_date
                FROM whd_cases
                WHERE {where_clause}
                ORDER BY backwages_amount DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, query_params)
            results = cur.fetchall()

            return {"total": total, "limit": limit, "offset": offset, "results": results}


@app.get("/api/whd/by-state/{state}")
def get_whd_by_state(state: str):
    """Get WHD violations summary for a specific state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total_cases,
                    SUM(COALESCE(total_violations, 0)) as total_violations,
                    SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                    SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                    SUM(COALESCE(employees_violated, 0)) as employees_violated,
                    COUNT(*) FILTER (WHERE flsa_repeat_violator = TRUE) as repeat_violators,
                    SUM(COALESCE(flsa_child_labor_violations, 0)) as child_labor_violations
                FROM whd_cases
                WHERE state = %s
            """, [state.upper()])
            summary = cur.fetchone()

            # Top violators in state
            cur.execute("""
                SELECT name_normalized, city,
                       COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                       SUM(COALESCE(employees_violated, 0)) as employees_violated,
                       BOOL_OR(flsa_repeat_violator) as is_repeat
                FROM whd_cases
                WHERE state = %s AND name_normalized IS NOT NULL
                GROUP BY name_normalized, city
                ORDER BY total_backwages DESC
                LIMIT 20
            """, [state.upper()])
            top_violators = cur.fetchall()

            # By NAICS in state
            cur.execute("""
                SELECT naics_code, COUNT(*) as case_count,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages
                FROM whd_cases
                WHERE state = %s AND naics_code IS NOT NULL
                GROUP BY naics_code
                ORDER BY case_count DESC
                LIMIT 10
            """, [state.upper()])
            by_naics = cur.fetchall()

            return {
                "state": state.upper(),
                "summary": summary,
                "top_violators": top_violators,
                "by_naics": by_naics
            }


@app.get("/api/whd/employer/{employer_id}")
def get_whd_employer_cases(employer_id: str):
    """Get WHD cases matched to a specific employer (F7 or Mergent)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Try F7 first
            cur.execute("""
                SELECT employer_name_aggressive, state, city,
                       whd_violation_count, whd_backwages, whd_employees_violated,
                       whd_penalties, whd_child_labor, whd_repeat_violator
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            f7 = cur.fetchone()

            if f7 and f7['employer_name_aggressive']:
                name_norm = f7['employer_name_aggressive']
                state = f7['state']
                city = f7['city']
            else:
                # Try Mergent by duns
                cur.execute("""
                    SELECT company_name_normalized, state, city,
                           whd_violation_count, whd_backwages, whd_employees_violated,
                           whd_penalties, whd_child_labor, whd_repeat_violator
                    FROM mergent_employers
                    WHERE duns = %s
                """, [employer_id])
                mergent = cur.fetchone()
                if not mergent:
                    raise HTTPException(status_code=404, detail="Employer not found")
                name_norm = mergent['company_name_normalized']
                state = mergent['state']
                city = mergent['city']

            # Find matching WHD cases
            cur.execute("""
                SELECT case_id, trade_name, legal_name, city, state, naics_code,
                       total_violations, civil_penalties, employees_violated,
                       backwages_amount, flsa_violations, flsa_repeat_violator,
                       flsa_child_labor_violations, findings_start_date, findings_end_date
                FROM whd_cases
                WHERE name_normalized = %s AND state = %s
                ORDER BY backwages_amount DESC NULLS LAST
            """, [name_norm, state])
            cases = cur.fetchall()

            return {
                "employer_id": employer_id,
                "name_normalized": name_norm,
                "state": state,
                "city": city,
                "whd_summary": f7 or mergent,
                "cases": cases
            }


@app.get("/api/whd/top-violators")
def get_whd_top_violators(
    state: Optional[str] = None,
    metric: str = Query("backwages", pattern="^(backwages|violations|penalties|employees)$"),
    limit: int = Query(50, le=200)
):
    """Get worst WHD violators by backwages, violations, penalties, or employees affected"""
    order_col = {
        "backwages": "total_backwages",
        "violations": "total_violations",
        "penalties": "total_penalties",
        "employees": "total_employees_violated"
    }[metric]

    conditions = ["name_normalized IS NOT NULL"]
    params = []
    if state:
        conditions.append("state = %s")
        params.append(state.upper())

    where_clause = " AND ".join(conditions)
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT name_normalized, city, state,
                       COUNT(*) as case_count,
                       SUM(COALESCE(total_violations, 0)) as total_violations,
                       SUM(COALESCE(backwages_amount, 0)) as total_backwages,
                       SUM(COALESCE(civil_penalties, 0)) as total_penalties,
                       SUM(COALESCE(employees_violated, 0)) as total_employees_violated,
                       BOOL_OR(flsa_repeat_violator) as is_repeat_violator,
                       SUM(COALESCE(flsa_child_labor_violations, 0)) as child_labor_violations,
                       MAX(findings_end_date) as latest_finding
                FROM whd_cases
                WHERE {where_clause}
                GROUP BY name_normalized, city, state
                ORDER BY {order_col} DESC NULLS LAST
                LIMIT %s
            """, params)
            results = cur.fetchall()

            return {"metric": metric, "state": state, "results": results}


# ============================================================================
# NAICS GRANULARITY ENDPOINTS
# ============================================================================

@app.get("/api/naics/stats")
def get_naics_stats():
    """Get statistics about NAICS code granularity and sources"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Source distribution
            cur.execute("""
                SELECT naics_source, COUNT(*) as count,
                       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
                FROM f7_employers_deduped
                GROUP BY naics_source
                ORDER BY count DESC
            """)
            by_source = cur.fetchall()

            # Granularity distribution
            cur.execute("""
                SELECT LENGTH(naics_detailed) as digits, COUNT(*) as count,
                       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
                FROM f7_employers_deduped
                WHERE naics_detailed IS NOT NULL
                GROUP BY LENGTH(naics_detailed)
                ORDER BY 1
            """)
            by_length = cur.fetchall()

            # Top detailed NAICS codes
            cur.execute("""
                SELECT naics_detailed, COUNT(*) as employers
                FROM f7_employers_deduped
                WHERE naics_source = 'OSHA'
                GROUP BY naics_detailed
                ORDER BY COUNT(*) DESC
                LIMIT 20
            """)
            top_detailed = cur.fetchall()

            return {
                "by_source": by_source,
                "by_granularity": by_length,
                "top_detailed_naics": top_detailed
            }


@app.get("/api/employers/by-naics-detailed/{naics_code}")
def get_employers_by_detailed_naics(
    naics_code: str,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get employers with a specific detailed NAICS code"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Count total
            cur.execute("""
                SELECT COUNT(*) FROM f7_employers_deduped
                WHERE naics_detailed LIKE %s
            """, [f"{naics_code}%"])
            total = cur.fetchone()['count']

            # Get employers
            cur.execute("""
                SELECT employer_id, employer_name, city, state, naics,
                       naics_detailed, naics_source, naics_confidence,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE naics_detailed LIKE %s
                ORDER BY latest_unit_size DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, [f"{naics_code}%", limit, offset])
            employers = cur.fetchall()

            return {
                "naics_code": naics_code,
                "total": total,
                "employers": employers
            }


# ============================================================================
# MULTI-EMPLOYER AGREEMENT ENDPOINTS
# ============================================================================

@app.get("/api/multi-employer/stats")
def get_multi_employer_stats():
    """Get multi-employer agreement deduplication statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Summary stats
            cur.execute("""
                SELECT
                    COUNT(*) as total_employers,
                    SUM(latest_unit_size) as total_workers_raw,
                    SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers,
                    SUM(CASE WHEN exclude_from_counts = TRUE THEN latest_unit_size ELSE 0 END) as excluded_workers,
                    COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
                    ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
                FROM f7_employers_deduped
            """)
            summary = cur.fetchone()

            # By exclusion reason
            cur.execute("""
                SELECT COALESCE(exclude_reason, 'INCLUDED') as reason,
                       COUNT(*) as employers,
                       SUM(latest_unit_size) as workers
                FROM f7_employers_deduped
                GROUP BY exclude_reason
                ORDER BY SUM(latest_unit_size) DESC
            """)
            by_reason = cur.fetchall()

            # Top multi-employer groups
            cur.execute("""
                SELECT multi_employer_group_id,
                       MAX(latest_union_name) as union_name,
                       COUNT(*) as employers_in_group,
                       SUM(latest_unit_size) as total_workers,
                       SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as counted_workers
                FROM f7_employers_deduped
                WHERE multi_employer_group_id IS NOT NULL
                GROUP BY multi_employer_group_id
                ORDER BY SUM(latest_unit_size) DESC
                LIMIT 20
            """)
            top_groups = cur.fetchall()

            return {
                "summary": summary,
                "by_reason": by_reason,
                "top_groups": top_groups
            }


@app.get("/api/multi-employer/groups")
def get_multi_employer_groups(limit: int = Query(50, le=200)):
    """Get list of multi-employer agreement groups"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_multi_employer_groups
                ORDER BY total_reported_workers DESC
                LIMIT %s
            """, [limit])
            return {"groups": cur.fetchall()}


@app.get("/api/employer/{employer_id}/agreement")
def get_employer_agreement_info(employer_id: str):
    """Get multi-employer agreement context for an employer"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, multi_employer_group_id,
                       is_primary_in_group, exclude_from_counts, exclude_reason,
                       latest_unit_size, latest_union_name
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get other employers in same group
            group_members = []
            if employer.get('multi_employer_group_id'):
                cur.execute("""
                    SELECT employer_id, employer_name, city, state,
                           latest_unit_size, is_primary_in_group, exclude_from_counts
                    FROM f7_employers_deduped
                    WHERE multi_employer_group_id = %s
                    ORDER BY latest_unit_size DESC
                    LIMIT 20
                """, [employer['multi_employer_group_id']])
                group_members = cur.fetchall()

            return {
                "employer": employer,
                "group_members": group_members,
                "group_size": len(group_members)
            }


# ============================================================================
# CORPORATE FAMILY / RELATED EMPLOYERS
# ============================================================================

@app.get("/api/corporate/family/{employer_id}")
def get_corporate_family(employer_id: str):
    """Get related employers (corporate family) - based on name similarity and multi-employer groups"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer info
            cur.execute("""
                SELECT employer_id, employer_name, employer_name_aggressive, state, naics,
                       multi_employer_group_id, latest_union_name, latest_unit_size
                FROM f7_employers_deduped WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            family_members = []

            # First, check for multi-employer group members
            if employer.get('multi_employer_group_id'):
                cur.execute("""
                    SELECT employer_id, employer_name, city, state, naics,
                           latest_unit_size, latest_union_name, 'MULTI_EMPLOYER_GROUP' as relationship
                    FROM f7_employers_deduped
                    WHERE multi_employer_group_id = %s AND employer_id != %s
                    ORDER BY latest_unit_size DESC
                    LIMIT 20
                """, [employer['multi_employer_group_id'], employer_id])
                family_members.extend(cur.fetchall())

            # Then find similar names using normalized name
            if employer.get('employer_name_aggressive'):
                group_id = employer.get('multi_employer_group_id')
                if group_id:
                    # Exclude employers already in the same multi-employer group
                    cur.execute("""
                        SELECT employer_id, employer_name, city, state, naics,
                               latest_unit_size, latest_union_name,
                               'NAME_SIMILARITY' as relationship,
                               similarity(employer_name_aggressive, %s) as name_similarity
                        FROM f7_employers_deduped
                        WHERE employer_id != %s
                          AND (multi_employer_group_id IS NULL OR multi_employer_group_id != %s)
                          AND similarity(employer_name_aggressive, %s) > 0.5
                        ORDER BY similarity(employer_name_aggressive, %s) DESC
                        LIMIT 15
                    """, [employer['employer_name_aggressive'], employer_id,
                          group_id, employer['employer_name_aggressive'],
                          employer['employer_name_aggressive']])
                else:
                    # No group to exclude
                    cur.execute("""
                        SELECT employer_id, employer_name, city, state, naics,
                               latest_unit_size, latest_union_name,
                               'NAME_SIMILARITY' as relationship,
                               similarity(employer_name_aggressive, %s) as name_similarity
                        FROM f7_employers_deduped
                        WHERE employer_id != %s
                          AND similarity(employer_name_aggressive, %s) > 0.5
                        ORDER BY similarity(employer_name_aggressive, %s) DESC
                        LIMIT 15
                    """, [employer['employer_name_aggressive'], employer_id,
                          employer['employer_name_aggressive'],
                          employer['employer_name_aggressive']])
                family_members.extend(cur.fetchall())

            return {
                "employer": employer,
                "family_members": family_members,
                "total_family": len(family_members)
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
                cur.execute("SELECT COUNT(*) as osha FROM osha_establishments")
                osha_count = cur.fetchone()['osha']
                cur.execute("SELECT COUNT(*) as ind FROM bls_industry_projections")
                ind_count = cur.fetchone()['ind']
                cur.execute("SELECT COUNT(*) as occ FROM bls_industry_occupation_matrix")
                occ_count = cur.fetchone()['occ']
                # NAICS granularity stats
                cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE naics_source = 'OSHA') as osha_enriched,
                           COUNT(*) FILTER (WHERE LENGTH(naics_detailed) = 6) as six_digit_naics
                    FROM f7_employers_deduped
                """)
                naics_stats = cur.fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "version": "6.4-multi-employer-dedup",
            "vr_records": vr_count,
            "osha_establishments": osha_count,
            "bls_industries": ind_count,
            "bls_occupation_records": occ_count,
            "naics_osha_enriched": naics_stats['osha_enriched'],
            "naics_6digit_employers": naics_stats['six_digit_naics']
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ============================================================================
# PUBLIC SECTOR
# ============================================================================

@app.get("/api/public-sector/stats")
def get_public_sector_stats():
    """Get summary statistics for public sector data"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM ps_union_locals")
            locals_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_employers")
            employers_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_parent_unions")
            parents_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_bargaining_units")
            bu_count = cur.fetchone()['count']
            cur.execute("SELECT SUM(members) as total FROM ps_union_locals WHERE members > 0")
            total_members = cur.fetchone()['total'] or 0
            cur.execute("""
                SELECT employer_type, COUNT(*) as count 
                FROM ps_employers 
                GROUP BY employer_type 
                ORDER BY count DESC
            """)
            employer_types = cur.fetchall()
            cur.execute("""
                SELECT p.abbrev, p.full_name, COUNT(l.id) as local_count, 
                       SUM(l.members) as total_members
                FROM ps_parent_unions p
                LEFT JOIN ps_union_locals l ON p.id = l.parent_union_id
                GROUP BY p.id, p.abbrev, p.full_name
                ORDER BY total_members DESC NULLS LAST
            """)
            parent_summary = cur.fetchall()
            
            return {
                "union_locals": locals_count,
                "employers": employers_count,
                "parent_unions": parents_count,
                "bargaining_units": bu_count,
                "total_members": total_members,
                "employer_types": employer_types,
                "parent_summary": parent_summary
            }


@app.get("/api/public-sector/parent-unions")
def get_public_sector_parent_unions():
    """Get list of parent unions for filtering"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.abbrev, p.full_name, p.federation, p.sector_focus,
                       COUNT(l.id) as local_count
                FROM ps_parent_unions p
                LEFT JOIN ps_union_locals l ON p.id = l.parent_union_id
                GROUP BY p.id
                ORDER BY p.full_name
            """)
            return {"parent_unions": cur.fetchall()}


@app.get("/api/public-sector/locals")
def search_public_sector_locals(
    state: Optional[str] = None,
    parent_union: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search public sector union locals"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if state:
                conditions.append("l.state = %s")
                params.append(state.upper())
            if parent_union:
                conditions.append("p.abbrev = %s")
                params.append(parent_union.upper())
            if name:
                conditions.append("l.local_name ILIKE %s")
                params.append(f"%{name}%")
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(*) FROM ps_union_locals l
                JOIN ps_parent_unions p ON l.parent_union_id = p.id
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT l.id, l.local_name, l.local_designation, l.state, l.city,
                       l.members, l.sector_type, l.f_num,
                       p.abbrev as parent_abbrev, p.full_name as parent_name
                FROM ps_union_locals l
                JOIN ps_parent_unions p ON l.parent_union_id = p.id
                WHERE {where_clause}
                ORDER BY l.members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "locals": cur.fetchall()}


@app.get("/api/public-sector/employers")
def search_public_sector_employers(
    state: Optional[str] = None,
    employer_type: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search public sector employers"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if employer_type:
                conditions.append("employer_type = %s")
                params.append(employer_type.upper())
            if name:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{name}%")
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"SELECT COUNT(*) FROM ps_employers WHERE {where_clause}", params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT id, employer_name, employer_type, state, city, county,
                       total_employees, naics_code
                FROM ps_employers
                WHERE {where_clause}
                ORDER BY employer_name
                LIMIT %s OFFSET %s
            """, params)
            
            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/public-sector/employer-types")
def get_public_sector_employer_types():
    """Get list of employer types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_type, COUNT(*) as count
                FROM ps_employers
                GROUP BY employer_type
                ORDER BY count DESC
            """)
            return {"employer_types": cur.fetchall()}


@app.get("/api/public-sector/benchmarks")
def get_public_sector_benchmarks(state: Optional[str] = None):
    """Get state-level public sector benchmarks"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if state:
                cur.execute("""
                    SELECT * FROM public_sector_benchmarks WHERE state = %s
                """, [state.upper()])
                result = cur.fetchone()
                return {"benchmark": result}
            else:
                cur.execute("""
                    SELECT state, state_name, epi_public_members, epi_public_density_pct,
                           olms_state_local_members, olms_federal_members, data_quality_flag
                    FROM public_sector_benchmarks
                    ORDER BY epi_public_members DESC NULLS LAST
                """)
                return {"benchmarks": cur.fetchall()}


# ============================================================================
# UNIFIED EMPLOYERS - All employer sources combined
# ============================================================================

@app.get("/api/employers/unified/stats")
def get_unified_employer_stats():
    """Get statistics for unified employers by source type"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # By source type
            cur.execute("""
                SELECT source_type, COUNT(*) as employer_count,
                       COUNT(union_fnum) as with_union,
                       SUM(employee_count) as total_employees
                FROM unified_employers_osha
                GROUP BY source_type
                ORDER BY COUNT(*) DESC
            """)
            by_source = cur.fetchall()

            # OSHA match stats
            cur.execute("""
                SELECT u.source_type,
                       COUNT(DISTINCT m.establishment_id) as osha_establishments,
                       COUNT(DISTINCT m.unified_employer_id) as employers_matched
                FROM osha_unified_matches m
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                GROUP BY u.source_type
                ORDER BY COUNT(DISTINCT m.establishment_id) DESC
            """)
            osha_matches = cur.fetchall()

            # Overall totals
            cur.execute("SELECT COUNT(*) as total FROM unified_employers_osha")
            total_employers = cur.fetchone()['total']

            cur.execute("SELECT COUNT(DISTINCT establishment_id) as total FROM osha_unified_matches")
            total_osha_matches = cur.fetchone()['total']

            cur.execute("""
                SELECT COUNT(DISTINCT m.establishment_id)
                FROM osha_unified_matches m
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                WHERE u.union_fnum IS NOT NULL
            """)
            union_connected = cur.fetchone()['count']

            return {
                "total_employers": total_employers,
                "total_osha_matches": total_osha_matches,
                "union_connected_matches": union_connected,
                "by_source": by_source,
                "osha_matches_by_source": osha_matches
            }


@app.get("/api/employers/unified/search")
def search_unified_employers(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source_type: Optional[str] = None,
    has_union: Optional[bool] = None,
    has_osha: Optional[bool] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search all unified employers across all sources (F7, NLRB, VR, PUBLIC)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if name:
                conditions.append("u.employer_name ILIKE %s")
                params.append(f"%{name}%")
            if state:
                conditions.append("u.state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(u.city) = %s")
                params.append(city.upper())
            if source_type:
                conditions.append("u.source_type = %s")
                params.append(source_type.upper())
            if has_union is True:
                conditions.append("u.union_fnum IS NOT NULL")
            if has_union is False:
                conditions.append("u.union_fnum IS NULL")
            if has_osha is True:
                conditions.append("EXISTS (SELECT 1 FROM osha_unified_matches m WHERE m.unified_employer_id = u.unified_id)")
            if has_osha is False:
                conditions.append("NOT EXISTS (SELECT 1 FROM osha_unified_matches m WHERE m.unified_employer_id = u.unified_id)")

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"SELECT COUNT(*) FROM unified_employers_osha u WHERE {where_clause}", params)
            total = cur.fetchone()['count']

            # Results with OSHA match count
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT u.unified_id, u.source_type, u.source_id, u.employer_name,
                       u.city, u.state, u.zip, u.naics, u.union_fnum, u.union_name,
                       u.employee_count,
                       COUNT(m.id) as osha_match_count
                FROM unified_employers_osha u
                LEFT JOIN osha_unified_matches m ON m.unified_employer_id = u.unified_id
                WHERE {where_clause}
                GROUP BY u.unified_id, u.source_type, u.source_id, u.employer_name,
                         u.city, u.state, u.zip, u.naics, u.union_fnum, u.union_name,
                         u.employee_count
                ORDER BY u.employee_count DESC NULLS LAST, u.employer_name
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "employers": cur.fetchall()}


@app.get("/api/employers/unified/{unified_id}")
def get_unified_employer(unified_id: int):
    """Get details for a specific unified employer including OSHA matches"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Main employer data
            cur.execute("""
                SELECT u.*, um.union_name as full_union_name, um.aff_abbr, um.members as union_members
                FROM unified_employers_osha u
                LEFT JOIN unions_master um ON u.union_fnum = um.f_num
                WHERE u.unified_id = %s
            """, [unified_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # OSHA matches
            cur.execute("""
                SELECT m.establishment_id, m.match_method, m.match_confidence,
                       o.estab_name, o.site_city, o.site_state, o.site_zip,
                       o.naics_code, o.employee_count, o.total_inspections
                FROM osha_unified_matches m
                JOIN osha_establishments o ON o.establishment_id = m.establishment_id
                WHERE m.unified_employer_id = %s
                ORDER BY m.match_confidence DESC
            """, [unified_id])
            osha_matches = cur.fetchall()

            # If OSHA matches exist, get violations summary
            violations_summary = None
            if osha_matches:
                estab_ids = [m['establishment_id'] for m in osha_matches]
                cur.execute("""
                    SELECT COUNT(*) as total_violations,
                           SUM(CASE WHEN issuance_date >= NOW() - INTERVAL '5 years' THEN 1 ELSE 0 END) as recent_violations,
                           SUM(current_penalty) as total_penalties,
                           SUM(CASE WHEN viol_type IN ('S', 'W') THEN 1 ELSE 0 END) as serious_violations
                    FROM osha_violations_detail
                    WHERE establishment_id = ANY(%s)
                """, [estab_ids])
                violations_summary = cur.fetchone()

            return {
                "employer": employer,
                "osha_matches": osha_matches,
                "violations_summary": violations_summary
            }


@app.get("/api/osha/unified-matches")
def search_osha_unified_matches(
    state: Optional[str] = None,
    source_type: Optional[str] = None,
    has_union: Optional[bool] = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    match_method: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search OSHA establishments matched to unified employers"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["m.match_confidence >= %s"]
            params = [min_confidence]

            if state:
                conditions.append("o.site_state = %s")
                params.append(state.upper())
            if source_type:
                conditions.append("u.source_type = %s")
                params.append(source_type.upper())
            if has_union is True:
                conditions.append("u.union_fnum IS NOT NULL")
            if has_union is False:
                conditions.append("u.union_fnum IS NULL")
            if match_method:
                conditions.append("m.match_method = %s")
                params.append(match_method.upper())

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"""
                SELECT COUNT(*)
                FROM osha_unified_matches m
                JOIN osha_establishments o ON o.establishment_id = m.establishment_id
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            # Results
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT m.id, m.establishment_id, m.match_method, m.match_confidence,
                       o.estab_name, o.site_city, o.site_state, o.naics_code,
                       u.unified_id, u.source_type, u.employer_name as matched_employer,
                       u.union_fnum, u.union_name
                FROM osha_unified_matches m
                JOIN osha_establishments o ON o.establishment_id = m.establishment_id
                JOIN unified_employers_osha u ON u.unified_id = m.unified_employer_id
                WHERE {where_clause}
                ORDER BY m.match_confidence DESC, o.estab_name
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "matches": cur.fetchall()}


@app.get("/api/employers/unified/sources")
def get_unified_source_types():
    """Get list of source types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_type, COUNT(*) as count,
                       COUNT(union_fnum) as with_union
                FROM unified_employers_osha
                GROUP BY source_type
                ORDER BY COUNT(*) DESC
            """)
            return {"source_types": cur.fetchall()}


# ============================================================================
# MUSEUM ORGANIZING TARGETS
# ============================================================================

@app.get("/api/museums/targets")
def search_museum_targets(
    tier: Optional[str] = None,
    city: Optional[str] = None,
    min_employees: Optional[int] = None,
    max_employees: Optional[int] = None,
    min_score: Optional[int] = None,
    has_osha_violations: Optional[bool] = None,
    has_govt_contracts: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("total_score", regex="^(total_score|best_employee_count|revenue_millions|employer_name)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """
    Search museum organizing targets.
    
    - tier: TOP, HIGH, MEDIUM, LOW
    - city: Filter by city name
    - min_employees/max_employees: Employee count range
    - min_score: Minimum organizing score
    - has_osha_violations: Filter for museums with OSHA violations
    - has_govt_contracts: Filter for museums with government contracts
    - search: Text search on employer name
    - sort_by: Field to sort by
    - sort_order: asc or desc
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if tier:
                conditions.append("priority_tier = %s")
                params.append(tier.upper())
            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if min_employees:
                conditions.append("best_employee_count >= %s")
                params.append(min_employees)
            if max_employees:
                conditions.append("best_employee_count <= %s")
                params.append(max_employees)
            if min_score:
                conditions.append("total_score >= %s")
                params.append(min_score)
            if has_osha_violations is True:
                conditions.append("osha_violation_count > 0")
            if has_osha_violations is False:
                conditions.append("(osha_violation_count = 0 OR osha_violation_count IS NULL)")
            if has_govt_contracts is True:
                conditions.append("total_contract_value > 0")
            if has_govt_contracts is False:
                conditions.append("(total_contract_value = 0 OR total_contract_value IS NULL)")
            if search:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{search}%")
            
            where_clause = " AND ".join(conditions)
            
            # Count total
            cur.execute(f"""
                SELECT COUNT(*) FROM v_museum_organizing_targets
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            # Get results
            order_dir = "DESC" if sort_order == "desc" else "ASC"
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM v_museum_organizing_targets
                WHERE {where_clause}
                ORDER BY {sort_by} {order_dir} NULLS LAST, employer_name
                LIMIT %s OFFSET %s
            """, params)
            
            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "targets": cur.fetchall()
            }


@app.get("/api/museums/targets/stats")
def get_museum_target_stats():
    """Get summary statistics for museum organizing targets by tier"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_museum_target_stats")
            tiers = cur.fetchall()
            
            # Also get overall totals
            cur.execute("""
                SELECT 
                    COUNT(*) as total_targets,
                    SUM(best_employee_count) as total_employees,
                    ROUND(AVG(total_score), 1) as avg_score,
                    SUM(revenue_millions) as total_revenue_millions,
                    COUNT(*) FILTER (WHERE has_osha_data) as with_osha_data,
                    COUNT(*) FILTER (WHERE has_990_data) as with_990_data,
                    COUNT(*) FILTER (WHERE osha_violation_count > 0) as with_violations,
                    COUNT(*) FILTER (WHERE total_contract_value > 0) as with_contracts
                FROM v_museum_organizing_targets
            """)
            totals = cur.fetchone()
            
            return {
                "by_tier": tiers,
                "totals": totals
            }


@app.get("/api/museums/targets/{target_id}")
def get_museum_target_detail(target_id: str):
    """Get detailed information for a specific museum target"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_museum_organizing_targets
                WHERE id = %s
            """, [target_id])
            target = cur.fetchone()
            
            if not target:
                raise HTTPException(status_code=404, detail="Target not found")
            
            # Get nearby unionized museums (same city or nearby)
            cur.execute("""
                SELECT employer_name, city, best_employee_count, union_name, nlrb_election_date
                FROM v_museum_unionized
                WHERE city = %s OR state = %s
                ORDER BY best_employee_count DESC
                LIMIT 5
            """, [target['city'], target['state']])
            nearby_unionized = cur.fetchall()
            
            return {
                "target": target,
                "nearby_unionized": nearby_unionized
            }


@app.get("/api/museums/targets/cities")
def get_museum_target_cities():
    """Get list of cities with museum targets for dropdown"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT city, COUNT(*) as target_count, SUM(best_employee_count) as total_employees
                FROM v_museum_organizing_targets
                GROUP BY city
                ORDER BY COUNT(*) DESC
            """)
            return {"cities": cur.fetchall()}


@app.get("/api/museums/unionized")
def get_unionized_museums(
    city: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get list of already-unionized museums for reference"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []
            
            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if search:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{search}%")
            
            where_clause = " AND ".join(conditions)
            
            cur.execute(f"""
                SELECT COUNT(*) FROM v_museum_unionized
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']
            
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM v_museum_unionized
                WHERE {where_clause}
                ORDER BY best_employee_count DESC
                LIMIT %s OFFSET %s
            """, params)
            
            return {
                "total": total,
                "museums": cur.fetchall()
            }


@app.get("/api/museums/summary")
def get_museum_sector_summary():
    """Get overall summary of museum sector (targets + unionized)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Target stats
            cur.execute("""
                SELECT 
                    COUNT(*) as target_count,
                    SUM(best_employee_count) as target_employees,
                    ROUND(SUM(revenue_millions), 1) as target_revenue_millions
                FROM v_museum_organizing_targets
            """)
            targets = cur.fetchone()
            
            # Unionized stats
            cur.execute("""
                SELECT 
                    COUNT(*) as unionized_count,
                    SUM(best_employee_count) as unionized_employees,
                    ROUND(SUM(revenue_millions), 1) as unionized_revenue_millions
                FROM v_museum_unionized
            """)
            unionized = cur.fetchone()
            
            # Score distribution
            cur.execute("""
                SELECT 
                    priority_tier,
                    COUNT(*) as count,
                    SUM(best_employee_count) as employees
                FROM v_museum_organizing_targets
                GROUP BY priority_tier
                ORDER BY 
                    CASE priority_tier 
                        WHEN 'TOP' THEN 1 
                        WHEN 'HIGH' THEN 2 
                        WHEN 'MEDIUM' THEN 3 
                        ELSE 4 
                    END
            """)
            by_tier = cur.fetchall()
            
            return {
                "sector": "MUSEUMS",
                "targets": targets,
                "unionized": unionized,
                "by_tier": by_tier,
                "union_density_pct": round(
                    unionized['unionized_count'] / (targets['target_count'] + unionized['unionized_count']) * 100, 1
                ) if targets['target_count'] else 0
            }


# ============================================================================
# GENERIC SECTOR ORGANIZING TARGETS
# ============================================================================

# Valid sectors with their view names
SECTOR_VIEWS = {
    'civic_organizations': 'civic_organizations',
    'building_services': 'building_services',
    'education': 'education',
    'social_services': 'social_services',
    'broadcasting': 'broadcasting',
    'publishing': 'publishing',
    'waste_mgmt': 'waste_mgmt',
    'government': 'government',
    'repair_services': 'repair_services',
    'museums': 'museums',
    'information': 'information',
    'other': 'other',
    'professional': 'professional',
    'healthcare_ambulatory': 'healthcare_ambulatory',
    'healthcare_nursing': 'healthcare_nursing',
    'healthcare_hospitals': 'healthcare_hospitals',
    'transit': 'transit',
    'utilities': 'utilities',
    'hospitality': 'hospitality',
    'food_service': 'food_service',
    'arts_entertainment': 'arts_entertainment',
}


@app.get("/api/sectors/list")
def list_sectors():
    """List all available sectors with target counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    sector_category,
                    COUNT(*) as total_employers,
                    SUM(CASE WHEN has_union THEN 1 ELSE 0 END) as unionized_count,
                    SUM(CASE WHEN has_union IS NOT TRUE THEN 1 ELSE 0 END) as target_count,
                    SUM(COALESCE(employees_site, 0)) as total_employees,
                    ROUND(100.0 * SUM(CASE WHEN has_union THEN 1 ELSE 0 END) / COUNT(*), 1) as union_density_pct
                FROM mergent_employers
                WHERE sector_category IS NOT NULL
                GROUP BY sector_category
                ORDER BY COUNT(*) DESC
            """)
            return {"sectors": cur.fetchall()}


@app.get("/api/sectors/{sector}/summary")
def get_sector_summary(sector: str):
    """Get summary statistics for a sector"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found. Valid: {list(SECTOR_VIEWS.keys())}")

    sector_upper = sector_key.upper()

    with get_db() as conn:
        with conn.cursor() as cur:
            # Target stats
            cur.execute("""
                SELECT
                    COUNT(*) as target_count,
                    SUM(COALESCE(employees_site, ny990_employees, 0)) as target_employees,
                    SUM(COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0)) as contract_value
                FROM mergent_employers
                WHERE sector_category = %s AND has_union IS NOT TRUE
            """, [sector_upper])
            targets = cur.fetchone()

            # Unionized stats
            cur.execute("""
                SELECT
                    COUNT(*) as unionized_count,
                    SUM(COALESCE(employees_site, ny990_employees, 0)) as unionized_employees
                FROM mergent_employers
                WHERE sector_category = %s AND has_union = TRUE
            """, [sector_upper])
            unionized = cur.fetchone()

            # Score distribution
            cur.execute("""
                SELECT
                    score_priority as priority_tier,
                    COUNT(*) as count,
                    SUM(COALESCE(employees_site, ny990_employees, 0)) as employees
                FROM mergent_employers
                WHERE sector_category = %s AND has_union IS NOT TRUE
                GROUP BY score_priority
                ORDER BY
                    CASE score_priority
                        WHEN 'TOP' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END
            """, [sector_upper])
            by_tier = cur.fetchall()

            total = (targets['target_count'] or 0) + (unionized['unionized_count'] or 0)
            density = round(unionized['unionized_count'] / total * 100, 1) if total > 0 else 0

            return {
                "sector": sector_upper,
                "targets": targets,
                "unionized": unionized,
                "by_tier": by_tier,
                "union_density_pct": density
            }


@app.get("/api/sectors/{sector}/targets")
def search_sector_targets(
    sector: str,
    tier: Optional[str] = None,
    city: Optional[str] = None,
    min_employees: Optional[int] = None,
    max_employees: Optional[int] = None,
    min_score: Optional[int] = None,
    has_osha_violations: Optional[bool] = None,
    has_govt_contracts: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("total_score", regex="^(total_score|employee_count|employer_name|total_contract_value)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search organizing targets in a specific sector"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"

    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if tier:
                conditions.append("priority_tier = %s")
                params.append(tier.upper())
            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if min_employees:
                conditions.append("best_employee_count >= %s")
                params.append(min_employees)
            if max_employees:
                conditions.append("best_employee_count <= %s")
                params.append(max_employees)
            if min_score:
                conditions.append("total_score >= %s")
                params.append(min_score)
            if has_osha_violations is True:
                conditions.append("osha_violation_count > 0")
            if has_osha_violations is False:
                conditions.append("(osha_violation_count = 0 OR osha_violation_count IS NULL)")
            if has_govt_contracts is True:
                conditions.append("total_contract_value > 0")
            if has_govt_contracts is False:
                conditions.append("(total_contract_value = 0 OR total_contract_value IS NULL)")
            if search:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{search}%")

            where_clause = " AND ".join(conditions)

            # Count total
            cur.execute(f"""
                SELECT COUNT(*) FROM {view_name}
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            # Get results
            order_dir = "DESC" if sort_order == "desc" else "ASC"
            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM {view_name}
                WHERE {where_clause}
                ORDER BY {sort_by} {order_dir} NULLS LAST, employer_name
                LIMIT %s OFFSET %s
            """, params)

            return {
                "sector": sector_key.upper(),
                "total": total,
                "limit": limit,
                "offset": offset,
                "targets": cur.fetchall()
            }


@app.get("/api/sectors/{sector}/targets/stats")
def get_sector_target_stats(sector: str):
    """Get summary statistics by tier for a sector"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_target_stats"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {view_name}")
            tiers = cur.fetchall()

            # Get overall totals
            targets_view = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"
            cur.execute(f"""
                SELECT
                    COUNT(*) as total_targets,
                    SUM(best_employee_count) as total_employees,
                    ROUND(AVG(total_score), 1) as avg_score,
                    COUNT(*) FILTER (WHERE osha_violation_count > 0) as with_violations,
                    COUNT(*) FILTER (WHERE total_contract_value > 0) as with_contracts
                FROM {targets_view}
            """)
            totals = cur.fetchone()

            return {
                "sector": sector_key.upper(),
                "by_tier": tiers,
                "totals": totals
            }


@app.get("/api/sectors/{sector}/targets/cities")
def get_sector_target_cities(sector: str):
    """Get list of cities with targets for dropdown"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT city, COUNT(*) as target_count, SUM(best_employee_count) as total_employees
                FROM {view_name}
                WHERE city IS NOT NULL
                GROUP BY city
                ORDER BY COUNT(*) DESC
            """)
            return {"cities": cur.fetchall()}


@app.get("/api/sectors/{sector}/targets/{target_id}")
def get_sector_target_detail(sector: str, target_id: int):
    """Get detailed information for a specific target"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    targets_view = f"v_{SECTOR_VIEWS[sector_key]}_organizing_targets"
    unionized_view = f"v_{SECTOR_VIEWS[sector_key]}_unionized"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM {targets_view}
                WHERE id = %s
            """, [target_id])
            target = cur.fetchone()

            if not target:
                raise HTTPException(status_code=404, detail="Target not found")

            # Get nearby unionized in same sector
            cur.execute(f"""
                SELECT employer_name, city, employee_count, union_name, nlrb_election_date
                FROM {unionized_view}
                WHERE city = %s OR state = %s
                ORDER BY employee_count DESC NULLS LAST
                LIMIT 5
            """, [target['city'], target['state']])
            nearby_unionized = cur.fetchall()

            return {
                "target": target,
                "nearby_unionized": nearby_unionized
            }


@app.get("/api/sectors/{sector}/unionized")
def get_sector_unionized(
    sector: str,
    city: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Get list of unionized employers in sector for reference"""
    sector_key = sector.lower().replace('-', '_')
    if sector_key not in SECTOR_VIEWS:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' not found")

    view_name = f"v_{SECTOR_VIEWS[sector_key]}_unionized"

    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if city:
                conditions.append("UPPER(city) = %s")
                params.append(city.upper())
            if search:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{search}%")

            where_clause = " AND ".join(conditions)

            cur.execute(f"""
                SELECT COUNT(*) FROM {view_name}
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            params.extend([limit, offset])
            cur.execute(f"""
                SELECT * FROM {view_name}
                WHERE {where_clause}
                ORDER BY employee_count DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)

            return {
                "sector": sector_key.upper(),
                "total": total,
                "unionized": cur.fetchall()
            }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
