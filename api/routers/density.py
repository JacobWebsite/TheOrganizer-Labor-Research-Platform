"""
Density router -- BLS union density by industry/state, county estimates,
industry-weighted analysis, and NY sub-county density.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from ..database import get_db

router = APIRouter()


# ============================================================================
# BLS UNION DENSITY BY INDUSTRY
# ============================================================================

@router.get("/api/density/naics/{naics_2digit}")
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


@router.get("/api/density/all")
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


@router.get("/api/density/by-state")
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


@router.get("/api/density/by-state/{state}/history")
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


@router.get("/api/density/by-govt-level")
def get_density_by_govt_level():
    """Get estimated union density by government level (federal/state/local) for all states

    Uses uniform multiplier method: each state's density at each government level
    is estimated as k x national_baseline, where k is calculated from the state's
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
                    "formula": "state_density = k x national_baseline"
                },
                "summary": {
                    "avg_federal_density": stats['avg_federal'],
                    "avg_state_density": stats['avg_state'],
                    "avg_local_density": stats['avg_local'],
                    "avg_multiplier": stats['avg_multiplier'],
                    "high_union_states": stats['high_union_states'],
                    "low_union_states": stats['low_union_states']
                },
                "states": results
            }


@router.get("/api/density/by-govt-level/{state}")
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
            fed_contribution = result['fed_share_of_public'] * result['est_federal_density']
            state_contribution = result['state_share_of_public'] * result['est_state_density']
            local_contribution = result['local_share_of_public'] * result['est_local_density']

            return {
                "state": result['state'],
                "state_name": result['state_name'],
                "densities": {
                    "private": result['private_density_pct'],
                    "public_combined": result['public_density_pct'],
                    "public_is_estimated": result['public_is_estimated'],
                    "federal_estimated": result['est_federal_density'],
                    "state_estimated": result['est_state_density'],
                    "local_estimated": result['est_local_density'],
                    "total": result['total_density_pct']
                },
                "multiplier": {
                    "value": result['multiplier'],
                    "interpretation": "above national average" if result['multiplier'] > 1 else "below national average"
                },
                "workforce_composition": {
                    "federal_pct": result['federal_workforce_pct'],
                    "state_pct": result['state_workforce_pct'],
                    "local_pct": result['local_workforce_pct'],
                    "public_total_pct": result['public_workforce_pct'],
                    "private_pct": result['private_workforce_pct']
                },
                "public_sector_composition": {
                    "federal_share": round(result['fed_share_of_public'] * 100, 1),
                    "state_share": round(result['state_share_of_public'] * 100, 1),
                    "local_share": round(result['local_share_of_public'] * 100, 1)
                },
                "contribution_to_public_density": {
                    "federal": round(fed_contribution, 1),
                    "state": round(state_contribution, 1),
                    "local": round(local_contribution, 1),
                    "total": round(fed_contribution + state_contribution + local_contribution, 1)
                },
                "comparison_to_national": {
                    "federal": {"state": result['est_federal_density'], "national": 25.3, "premium": round(result['est_federal_density'] - 25.3, 1)},
                    "state": {"state": result['est_state_density'], "national": 27.8, "premium": round(result['est_state_density'] - 27.8, 1)},
                    "local": {"state": result['est_local_density'], "national": 38.2, "premium": round(result['est_local_density'] - 38.2, 1)}
                }
            }


# ============================================================================
# COUNTY UNION DENSITY ESTIMATES
# ============================================================================

@router.get("/api/density/by-county")
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
            total = cur.fetchone()['count']

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


@router.get("/api/density/by-county/{fips}")
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
                "fips": result['fips'],
                "state": result['state'],
                "county_name": result['county_name'],
                "estimated_densities": {
                    "total": result['estimated_total_density'],
                    "private": result['estimated_private_density'],
                    "public": result['estimated_public_density'],
                    "federal": result['estimated_federal_density'],
                    "state_gov": result['estimated_state_density'],
                    "local": result['estimated_local_density']
                },
                "workforce_composition": {
                    "private_pct": round(float(result['private_share']) * 100, 1) if result['private_share'] else 0,
                    "federal_pct": round(float(result['federal_share']) * 100, 1) if result['federal_share'] else 0,
                    "state_pct": round(float(result['state_share']) * 100, 1) if result['state_share'] else 0,
                    "local_pct": round(float(result['local_share']) * 100, 1) if result['local_share'] else 0,
                    "public_pct": round(float(result['public_share']) * 100, 1) if result['public_share'] else 0,
                    "self_employed_pct": round(float(result['self_employed_share']) * 100, 1) if result['self_employed_share'] else 0
                },
                "state_density_rates_used": {
                    "private": result['state_private_rate'],
                    "federal": result['state_federal_rate'],
                    "state_gov": result['state_state_rate'],
                    "local": result['state_local_rate']
                },
                "confidence_level": result['confidence_level'],
                "state_union_multiplier": result['state_multiplier'],
                "methodology": {
                    "description": "State density rates applied to county workforce composition",
                    "formula": "Total = (Private% x State_Private_Rate) + (Fed% x State_Fed_Rate) + (State% x State_State_Rate) + (Local% x State_Local_Rate)",
                    "note": "Self-employed workers (0% union rate) are excluded from calculation"
                }
            }


@router.get("/api/density/by-state/{state}/counties")
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
                    "county_count": summary['county_count'],
                    "avg_county_density": summary['avg_density'],
                    "min_county_density": summary['min_density'],
                    "max_county_density": summary['max_density'],
                    "state_total_density": state_density['total_density_pct'] if state_density else None
                },
                "counties": counties
            }


@router.get("/api/density/county-summary")
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
                    "total_counties": national['total_counties'],
                    "avg_density": national['avg_density'],
                    "min_density": national['min_density'],
                    "max_density": national['max_density'],
                    "stddev_density": national['stddev_density'],
                    "high_confidence_count": national['high_confidence'],
                    "medium_confidence_count": national['medium_confidence']
                },
                "top_density_counties": top_counties,
                "bottom_density_counties": bottom_counties,
                "by_state": by_state,
                "methodology_note": "Estimates based on state density rates x county workforce composition. Self-employed workers excluded (0% union rate)."
            }


# ============================================================================
# INDUSTRY-WEIGHTED DENSITY ANALYSIS
# ============================================================================

@router.get("/api/density/industry-rates")
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


@router.get("/api/density/state-industry-comparison")
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
                "methodology": "Expected density = sum(industry_share x BLS_industry_rate) for 12 industries. Climate multiplier = actual / expected. STRONG > 1.5x, ABOVE_AVERAGE 1.0-1.5x, BELOW_AVERAGE 0.5-1.0x, WEAK < 0.5x."
            }


@router.get("/api/density/state-industry-comparison/{state}")
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


@router.get("/api/density/by-county/{fips}/industry")
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

@router.get("/api/density/ny/counties")
def get_ny_county_density(
    min_density: Optional[float] = None,
    max_density: Optional[float] = None,
    sort_by: str = Query("total_density", pattern="^(total_density|private_density|public_density|name)$")
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


@router.get("/api/density/ny/county/{fips}")
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


@router.get("/api/density/ny/zips")
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


@router.get("/api/density/ny/zip/{zip_code}")
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


@router.get("/api/density/ny/tracts")
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


@router.get("/api/density/ny/tract/{tract_fips}")
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


@router.get("/api/density/ny/summary")
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
