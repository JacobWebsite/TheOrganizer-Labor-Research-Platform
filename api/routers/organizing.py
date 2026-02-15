import os
from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from ..database import get_db
from ..helpers import safe_sort_col, safe_order_dir

router = APIRouter()


# ---------------------------------------------------------------------------
# Private scoring helper functions (used by scorecard endpoints)
# ---------------------------------------------------------------------------

def _score_size(emp_count):
    """Size score (0-10): organizing sweet spot is 50-250 employees."""
    if 50 <= emp_count <= 250:
        return 10
    elif 250 < emp_count <= 500:
        return 8
    elif 25 <= emp_count < 50:
        return 6
    elif 500 < emp_count <= 1000:
        return 4
    else:
        return 2

def _score_osha_normalized(total_violations, willful, repeat, naics_code, osha_avgs):
    """OSHA score (0-10): violations normalized to industry average + severity bonus."""
    total_violations = total_violations or 0
    willful = willful or 0
    repeat = repeat or 0

    # Find best available industry average (4-digit preferred, then 2-digit, then overall)
    industry_avg = None
    if naics_code and len(naics_code) >= 4:
        industry_avg = osha_avgs.get(naics_code[:4])
    if industry_avg is None and naics_code and len(naics_code) >= 2:
        industry_avg = osha_avgs.get(naics_code[:2])
    if industry_avg is None:
        industry_avg = osha_avgs.get('ALL', 2.23)

    if industry_avg <= 0:
        industry_avg = 2.23  # fallback to overall average

    ratio = total_violations / industry_avg if total_violations > 0 else 0

    # Base score from ratio to industry average (0-7)
    if ratio >= 3.0:
        base = 7
    elif ratio >= 2.0:
        base = 5
    elif ratio >= 1.5:
        base = 4
    elif ratio >= 1.0:
        base = 3
    elif ratio > 0:
        base = 1
    else:
        base = 0

    # Severity bonus for willful/repeat (0-3)
    severity_bonus = min(3, willful * 2 + repeat)

    return min(10, base + severity_bonus), round(ratio, 2)

def _score_geographic(site_state, rtw_set, nlrb_rates, state_members):
    """Geographic favorability score (0-10): NLRB win rate + density + RTW adjustment."""
    # NLRB win rate component (0-4)
    win_rate = nlrb_rates.get(site_state, nlrb_rates.get('US', 75.0))
    if win_rate >= 85:
        nlrb_component = 4
    elif win_rate >= 75:
        nlrb_component = 3
    elif win_rate >= 65:
        nlrb_component = 2
    elif win_rate >= 55:
        nlrb_component = 1
    else:
        nlrb_component = 0

    # State density component (0-3)
    members = state_members.get(site_state, 0)
    if members > 1000000:
        density_component = 3
    elif members > 500000:
        density_component = 2
    elif members > 200000:
        density_component = 1
    else:
        density_component = 0

    # Non-RTW bonus (0-3)
    rtw_component = 0 if site_state in rtw_set else 3

    return min(10, nlrb_component + density_component + rtw_component)


# ---------------------------------------------------------------------------
# Score explanation helpers (plain-language reasons for each score component)
# ---------------------------------------------------------------------------

def _explain_size(emp_count):
    """Human-readable explanation for the size score."""
    if not emp_count or emp_count <= 0:
        return "No employee data available"
    if 50 <= emp_count <= 250:
        return f"{emp_count:,} employees -- in the 50-250 organizing sweet spot"
    elif 250 < emp_count <= 500:
        return f"{emp_count:,} employees -- mid-size, feasible target"
    elif 25 <= emp_count < 50:
        return f"{emp_count:,} employees -- small but organizable"
    elif 500 < emp_count <= 1000:
        return f"{emp_count:,} employees -- large, requires more resources"
    else:
        return f"{emp_count:,} employees -- very {'large' if emp_count > 1000 else 'small'} unit"


def _explain_osha(total_violations, osha_ratio):
    """Human-readable explanation for the OSHA score."""
    total_violations = total_violations or 0
    if total_violations == 0:
        return "No OSHA violations on record"
    ratio_str = ""
    if osha_ratio and osha_ratio > 0:
        ratio_str = f" ({osha_ratio:.1f}x industry average)"
    return f"{total_violations} violations{ratio_str}"


def _explain_geographic(state, is_rtw, win_rate):
    """Human-readable explanation for the geographic score."""
    parts = []
    if state:
        parts.append(state)
    if is_rtw is not None:
        parts.append("right-to-work state" if is_rtw else "non-RTW state")
    if win_rate is not None:
        parts.append(f"{win_rate:.0f}% NLRB win rate")
    return ", ".join(parts) if parts else "Geographic data unavailable"


def _explain_contracts(federal_amt, count):
    """Human-readable explanation for the contracts score."""
    federal_amt = federal_amt or 0
    count = count or 0
    if federal_amt <= 0:
        return "No federal contracts on record"
    if federal_amt >= 1_000_000:
        return f"${federal_amt / 1_000_000:.1f}M across {count} federal contract{'s' if count != 1 else ''}"
    elif federal_amt >= 1_000:
        return f"${federal_amt / 1_000:.0f}K across {count} federal contract{'s' if count != 1 else ''}"
    return f"${federal_amt:,.0f} in {count} federal contract{'s' if count != 1 else ''}"


def _explain_nlrb(predicted_pct):
    """Human-readable explanation for the NLRB score."""
    if predicted_pct is None:
        return "No NLRB prediction available (using blended rate)"
    return f"{predicted_pct:.0f}% predicted win rate"


def _explain_industry_density(score):
    """Human-readable explanation for industry density score."""
    if score is None:
        score = 0
    if score >= 10:
        return "15%+ union density in sector (very high)"
    elif score >= 8:
        return "10-15% union density in sector (high)"
    elif score >= 6:
        return "5-10% union density in sector (moderate)"
    elif score >= 4:
        return "2-5% union density in sector (low)"
    elif score >= 2:
        return "Under 2% union density (very low)"
    return "Density data unavailable"


def _explain_company_unions(score):
    """Human-readable explanation for company unions score."""
    if score is None:
        score = 0
    if score >= 15:
        return "Multiple related locations with union presence"
    elif score >= 10:
        return "Related location has union representation"
    elif score >= 5:
        return "Same-sector employer has nearby union"
    return "No related union presence detected"


def _explain_projections(score):
    """Human-readable explanation for BLS projections score."""
    if score is None:
        score = 0
    if score >= 8:
        return "Industry projected for strong growth (BLS)"
    elif score >= 5:
        return "Industry projected for moderate growth (BLS)"
    elif score >= 3:
        return "Industry projected for slow growth (BLS)"
    return "Industry growth data unavailable"


def _explain_similarity(score):
    """Human-readable explanation for employer similarity score."""
    if score is None:
        score = 0
    if score >= 8:
        return "Very similar to successfully organized employers"
    elif score >= 5:
        return "Moderately similar to organized employers"
    elif score >= 3:
        return "Some similarity to organized employers"
    return "Low similarity to organized employers"


def _build_explanations(row, is_rtw=None, win_rate=None):
    """Build the full score_explanations dict from a row."""
    return {
        'size': _explain_size(row.get('employee_count')),
        'osha': _explain_osha(
            row.get('total_violations'),
            float(row['osha_industry_ratio']) if row.get('osha_industry_ratio') is not None else None
        ),
        'geographic': _explain_geographic(
            row.get('site_state'), is_rtw, win_rate
        ),
        'contracts': _explain_contracts(
            float(row['federal_obligations']) if row.get('federal_obligations') else 0,
            row.get('federal_contract_count', 0)
        ),
        'nlrb': _explain_nlrb(
            float(row['nlrb_predicted_win_pct']) if row.get('nlrb_predicted_win_pct') else None
        ),
        'industry_density': _explain_industry_density(row.get('score_industry_density')),
        'company_unions': _explain_company_unions(row.get('score_company_unions')),
        'projections': _explain_projections(row.get('score_projections')),
        'similarity': _explain_similarity(row.get('score_similarity')),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/organizing/summary")
def get_organizing_summary(year_from: int = 2020, year_to: int = 2025):
    """Get combined organizing activity summary (Elections + VR)"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM v_organizing_by_year
                WHERE year >= %s AND year <= %s ORDER BY year
            """, [year_from, year_to])
            return {"years": cur.fetchall()}


@router.get("/api/organizing/by-state")
def get_organizing_by_state():
    """Get combined organizing activity by state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_organizing_by_state ORDER BY total_events DESC")
            return {"states": cur.fetchall()}


@router.get("/api/organizing/scorecard")
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
    Get scored organizing targets from pre-computed materialized view (0-90 points):
    - Company union shops (20): Related locations with union presence
    - Industry density (10): Union density in NAICS sector
    - Geographic favorability (10): NLRB win rate + state density + RTW
    - Size (10): Sweet spot 50-250 employees
    - OSHA (10): Violations normalized to industry average + severity
    - NLRB (10): Predicted win % or blended state/industry rate
    - Contracts (10): Federal contract funding
    - Projections (10): BLS industry growth outlook
    - Similarity (10): Gower distance to union employers
    """
    conditions = ["employee_count >= %s", "employee_count <= %s"]
    params: list = [min_employees, max_employees]

    if state:
        conditions.append("site_state = %s")
        params.append(state.upper())
    if naics_2digit:
        conditions.append("naics_code LIKE %s")
        params.append(f"{naics_2digit}%")
    if min_score > 0:
        conditions.append("organizing_score >= %s")
        params.append(min_score)
    if has_contracts and has_contracts.lower() in ('true', '1', 'yes'):
        conditions.append("has_federal_contracts = TRUE")

    where_clause = " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Count matching rows (before pagination)
            cur.execute(f"""
                SELECT COUNT(*) as cnt FROM v_organizing_scorecard
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['cnt']

            # Fetch paginated results sorted by score
            cur.execute(f"""
                SELECT * FROM v_organizing_scorecard
                WHERE {where_clause}
                ORDER BY organizing_score DESC, total_penalties DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            rows = cur.fetchall()

            # Batch ULP count: two fast queries instead of one complex CTE
            ulp_counts = {}
            if rows:
                estab_ids = [r['establishment_id'] for r in rows]
                # Step 1: Get NLRB employer names mapped to establishment IDs
                cur.execute("""
                    SELECT DISTINCT m.establishment_id, p.participant_name
                    FROM osha_f7_matches m
                    JOIN nlrb_participants p ON p.matched_employer_id = m.f7_employer_id
                    WHERE m.establishment_id = ANY(%s)
                      AND p.participant_type = 'Employer'
                """, [estab_ids])
                name_map = {}  # participant_name -> [establishment_ids]
                for row in cur.fetchall():
                    name_map.setdefault(row['participant_name'], []).append(row['establishment_id'])

                if name_map:
                    # Step 2: Count ULP cases for those employer names
                    names_list = list(name_map.keys())
                    cur.execute("""
                        SELECT p.participant_name, COUNT(DISTINCT c.case_number) as ulp_count
                        FROM nlrb_participants p
                        JOIN nlrb_cases c ON c.case_number = p.case_number
                        JOIN nlrb_case_types ct ON ct.case_type = c.case_type
                        WHERE p.participant_name = ANY(%s)
                          AND p.participant_type = 'Employer'
                          AND ct.case_category = 'unfair_labor_practice'
                        GROUP BY p.participant_name
                    """, [names_list])
                    for row in cur.fetchall():
                        count = row['ulp_count']
                        for eid in name_map.get(row['participant_name'], []):
                            ulp_counts[eid] = ulp_counts.get(eid, 0) + count

            results = []
            for r in rows:
                results.append({
                    'establishment_id': r['establishment_id'],
                    'estab_name': r['estab_name'],
                    'site_address': r['site_address'],
                    'site_city': r['site_city'],
                    'site_state': r['site_state'],
                    'site_zip': r['site_zip'],
                    'naics_code': r['naics_code'],
                    'employee_count': r['employee_count'],
                    'total_inspections': r['total_inspections'],
                    'last_inspection_date': str(r['last_inspection_date']) if r['last_inspection_date'] else None,
                    'willful_count': r['willful_count'],
                    'repeat_count': r['repeat_count'],
                    'serious_count': r['serious_count'],
                    'total_violations': r['total_violations'],
                    'total_penalties': float(r['total_penalties']) if r['total_penalties'] else None,
                    'accident_count': r['accident_count'],
                    'fatality_count': r['fatality_count'],
                    'risk_level': r['risk_level'],
                    'has_f7_match': r['has_f7_match'],
                    'has_federal_contracts': r['has_federal_contracts'],
                    'federal_obligations': float(r['federal_obligations']) if r['federal_obligations'] else None,
                    'organizing_score': r['organizing_score'],
                    'osha_industry_ratio': float(r['osha_industry_ratio']) if r['osha_industry_ratio'] is not None else None,
                    'score_breakdown': {
                        'company_unions': r['score_company_unions'],
                        'industry_density': r['score_industry_density'],
                        'geographic': r['score_geographic'],
                        'size': r['score_size'],
                        'osha': r['score_osha'],
                        'nlrb': r['score_nlrb'],
                        'contracts': r['score_contracts'],
                        'projections': r['score_projections'],
                        'similarity': r['score_similarity'],
                    },
                    'nlrb_predicted_win_pct': float(r['nlrb_predicted_win_pct']) if r['nlrb_predicted_win_pct'] else None,
                    'score_explanations': _build_explanations(r),
                    'ulp_case_count': ulp_counts.get(r['establishment_id'], 0),
                })

            return {
                "results": results,
                "total": total,
                "scored_count": total,
                "limit": limit,
                "offset": offset
            }


@router.get("/api/organizing/scorecard/{estab_id}")
def get_scorecard_detail(estab_id: str):
    """Get detailed scorecard for a specific establishment.
    Base scores come from the materialized view (consistent with list endpoint).
    Detail-only context (NY/NYC contracts, NLRB participants, etc.) added on top."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Read base scores from MV -- guarantees list/detail consistency
            cur.execute("""
                SELECT * FROM v_organizing_scorecard WHERE establishment_id = %s
            """, [estab_id])
            mv = cur.fetchone()
            if not mv:
                raise HTTPException(status_code=404, detail="Establishment not found")

            estab_name = mv['estab_name'] or ''
            est_state = mv['site_state'] or ''
            naics_2 = (mv['naics_code'] or '')[:2] or None

            # --- Detail-only context queries (not in MV) ---

            # RTW status for geographic context
            cur.execute("SELECT 1 FROM ref_rtw_states WHERE state = %s", [est_state])
            is_rtw = cur.fetchone() is not None

            # State NLRB win rate for context display
            cur.execute("SELECT win_rate_pct FROM ref_nlrb_state_win_rates WHERE state = %s", [est_state])
            wr = cur.fetchone()
            state_win_rate = float(wr['win_rate_pct']) if wr else None

            # NLRB case count via proper join through matched_employer_id
            # Step 1: Get employer names from matched representation cases
            cur.execute("""
                SELECT DISTINCT p.participant_name
                FROM osha_f7_matches m
                JOIN nlrb_participants p ON p.matched_employer_id = m.f7_employer_id
                WHERE m.establishment_id = %s AND p.participant_type = 'Employer'
            """, [estab_id])
            nlrb_employer_names = [r['participant_name'] for r in cur.fetchall()]

            # Step 2: Count all NLRB cases for those employer names
            nlrb_count = 0
            if nlrb_employer_names:
                cur.execute("""
                    SELECT COUNT(DISTINCT p.case_number) as cnt
                    FROM nlrb_participants p
                    WHERE p.participant_name = ANY(%s) AND p.participant_type = 'Employer'
                """, [nlrb_employer_names])
                nlrb_count = cur.fetchone()['cnt']

            # Step 3: ULP context -- cases where this employer is charged
            ulp_context = None
            if nlrb_employer_names:
                cur.execute("""
                    SELECT COUNT(DISTINCT c.case_number) as total_ulp,
                           COUNT(DISTINCT CASE WHEN c.case_type = 'CA' THEN c.case_number END) as employer_ulp,
                           MIN(c.earliest_date) as earliest,
                           MAX(c.latest_date) as latest
                    FROM nlrb_participants p
                    JOIN nlrb_cases c ON c.case_number = p.case_number
                    JOIN nlrb_case_types ct ON ct.case_type = c.case_type
                    WHERE p.participant_name = ANY(%s)
                      AND p.participant_type = 'Employer'
                      AND ct.case_category = 'unfair_labor_practice'
                """, [nlrb_employer_names])
                ulp_row = cur.fetchone()
                total_ulp = ulp_row['total_ulp'] or 0

                if total_ulp > 0:
                    # Get section breakdown from allegations
                    cur.execute("""
                        SELECT a.section, COUNT(*) as cnt
                        FROM nlrb_allegations a
                        JOIN nlrb_participants p ON p.case_number = a.case_number
                        JOIN nlrb_cases c ON c.case_number = a.case_number
                        JOIN nlrb_case_types ct ON ct.case_type = c.case_type
                        WHERE p.participant_name = ANY(%s)
                          AND p.participant_type = 'Employer'
                          AND ct.case_category = 'unfair_labor_practice'
                        GROUP BY a.section
                        ORDER BY cnt DESC
                        LIMIT 5
                    """, [nlrb_employer_names])
                    section_breakdown = [
                        {'section': r['section'], 'count': r['cnt']}
                        for r in cur.fetchall()
                    ]

                    # Get recent cases
                    cur.execute("""
                        SELECT DISTINCT c.case_number, c.case_type,
                               c.earliest_date, c.latest_date
                        FROM nlrb_participants p
                        JOIN nlrb_cases c ON c.case_number = p.case_number
                        JOIN nlrb_case_types ct ON ct.case_type = c.case_type
                        WHERE p.participant_name = ANY(%s)
                          AND p.participant_type = 'Employer'
                          AND ct.case_category = 'unfair_labor_practice'
                        ORDER BY c.latest_date DESC NULLS LAST
                        LIMIT 5
                    """, [nlrb_employer_names])
                    recent_cases = [
                        {
                            'case_number': r['case_number'],
                            'case_type': r['case_type'],
                            'earliest_date': str(r['earliest_date']) if r['earliest_date'] else None,
                            'latest_date': str(r['latest_date']) if r['latest_date'] else None,
                        }
                        for r in cur.fetchall()
                    ]

                    ulp_context = {
                        'total_cases': total_ulp,
                        'employer_ulp_cases': ulp_row['employer_ulp'] or 0,
                        'date_range': {
                            'earliest': str(ulp_row['earliest']) if ulp_row['earliest'] else None,
                            'latest': str(ulp_row['latest']) if ulp_row['latest'] else None,
                        },
                        'section_breakdown': section_breakdown,
                        'recent_cases': recent_cases,
                    }

            nlrb_factors = None
            cur.execute("""
                SELECT me.nlrb_success_factors
                FROM osha_f7_matches m
                JOIN mergent_employers me ON me.matched_f7_employer_id = m.f7_employer_id
                WHERE m.establishment_id = %s AND me.nlrb_predicted_win_pct IS NOT NULL
                LIMIT 1
            """, [estab_id])
            nlrb_row = cur.fetchone()
            if nlrb_row:
                nlrb_factors = nlrb_row['nlrb_success_factors']

            # NLRB industry win rate
            nlrb_industry_rate = None
            if naics_2:
                cur.execute("SELECT win_rate_pct FROM ref_nlrb_industry_win_rates WHERE naics_2 = %s", [naics_2])
                ir = cur.fetchone()
                if ir:
                    nlrb_industry_rate = float(ir['win_rate_pct'])

            # NY/NYC state contracts (detail-only, not in MV contract score)
            cur.execute("""
                SELECT COALESCE(SUM(current_amount), 0) as total FROM ny_state_contracts
                WHERE vendor_name ILIKE %s
            """, [f"%{estab_name[:15]}%"])
            ny_funding = float(cur.fetchone()['total'] or 0)
            cur.execute("""
                SELECT COALESCE(SUM(current_amount), 0) as total FROM nyc_contracts
                WHERE vendor_name ILIKE %s
            """, [f"%{estab_name[:15]}%"])
            nyc_funding = float(cur.fetchone()['total'] or 0)

            federal_funding = float(mv['federal_obligations'] or 0)
            federal_count = mv['federal_contract_count'] or 0

            # MV scores are the single source of truth
            similarity_score_val = float(mv['similarity_score']) if mv['similarity_score'] is not None else None
            nlrb_predicted_pct = float(mv['nlrb_predicted_win_pct']) if mv['nlrb_predicted_win_pct'] is not None else None
            osha_ratio = float(mv['osha_industry_ratio']) if mv['osha_industry_ratio'] is not None else None

            return {
                "establishment": {
                    'establishment_id': mv['establishment_id'],
                    'estab_name': mv['estab_name'],
                    'site_address': mv['site_address'],
                    'site_city': mv['site_city'],
                    'site_state': mv['site_state'],
                    'site_zip': mv['site_zip'],
                    'naics_code': mv['naics_code'],
                    'employee_count': mv['employee_count'],
                    'total_inspections': mv['total_inspections'],
                    'last_inspection_date': str(mv['last_inspection_date']) if mv['last_inspection_date'] else None,
                    'willful_count': mv['willful_count'],
                    'repeat_count': mv['repeat_count'],
                    'serious_count': mv['serious_count'],
                    'total_violations': mv['total_violations'],
                    'total_penalties': float(mv['total_penalties']) if mv['total_penalties'] else None,
                    'accident_count': mv['accident_count'],
                    'fatality_count': mv['fatality_count'],
                    'risk_level': mv['risk_level'],
                },
                "organizing_score": mv['organizing_score'],
                "score_breakdown": {
                    "company_unions": mv['score_company_unions'],
                    "industry_density": mv['score_industry_density'],
                    "geographic": mv['score_geographic'],
                    "size": mv['score_size'],
                    "osha": mv['score_osha'],
                    "nlrb": mv['score_nlrb'],
                    "contracts": mv['score_contracts'],
                    "projections": mv['score_projections'],
                    "similarity": mv['score_similarity'],
                },
                "similarity_context": {
                    "similarity_score": similarity_score_val,
                    "comparables_url": f"/api/employers/{estab_id}/comparables" if similarity_score_val else None
                },
                "osha_context": {
                    "industry_ratio": osha_ratio,
                    "total_violations": mv['total_violations'] or 0,
                    "willful": mv['willful_count'] or 0,
                    "repeat": mv['repeat_count'] or 0
                },
                "geographic_context": {
                    "is_rtw_state": is_rtw,
                    "nlrb_win_rate": state_win_rate
                },
                "contracts": {
                    "ny_state_funding": ny_funding,
                    "nyc_funding": nyc_funding,
                    "federal_funding": federal_funding,
                    "federal_contract_count": federal_count,
                    "total_funding": ny_funding + nyc_funding + federal_funding
                },
                "nlrb_context": {
                    "predicted_win_pct": nlrb_predicted_pct,
                    "state_win_rate": state_win_rate,
                    "industry_win_rate": nlrb_industry_rate,
                    "direct_case_count": nlrb_count,
                    "factors": nlrb_factors
                },
                "ulp_context": ulp_context,
                "context": {
                    "has_related_union": mv['has_f7_match'],
                    "nlrb_count": nlrb_count
                },
                "score_explanations": _build_explanations(
                    mv, is_rtw=is_rtw, win_rate=state_win_rate
                )
            }


@router.get("/api/organizing/siblings/{estab_id}")
def get_sibling_employers(estab_id: str, limit: int = Query(default=5, le=20)):
    """Find the most similar unionized F7 employers for a given OSHA target.
    Matches on NAICS sector, state/region, and employee size range.
    Returns ranked siblings with match quality indicators."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get the target establishment
            cur.execute("""
                SELECT establishment_id, estab_name, site_state, site_city, site_zip,
                       naics_code, employee_count
                FROM osha_establishments
                WHERE establishment_id = %s
            """, [estab_id])
            target = cur.fetchone()
            if not target:
                raise HTTPException(status_code=404, detail="Establishment not found")

            naics_code = target.get('naics_code') or ''
            naics_2 = naics_code[:2] if len(naics_code) >= 2 else None
            naics_4 = naics_code[:4] if len(naics_code) >= 4 else None
            target_state = target.get('site_state', '')
            target_emp = target.get('employee_count') or 0

            # Build a ranked query for F7 employers with similarity scoring
            # Match criteria (scored in SQL):
            #   - NAICS match at various levels (highest weight)
            #   - Same state
            #   - Same city
            #   - Similar size (within 2x range)
            cur.execute("""
                WITH scored AS (
                    SELECT
                        f.employer_id,
                        f.employer_name,
                        f.city,
                        f.state,
                        f.naics,
                        f.naics_detailed,
                        (
                            -- NAICS match scoring (0-50 points)
                            CASE
                                WHEN %(naics_4)s IS NOT NULL AND f.naics_detailed IS NOT NULL
                                     AND LEFT(f.naics_detailed, 4) = %(naics_4)s THEN 50
                                WHEN %(naics_2)s IS NOT NULL AND f.naics = %(naics_2)s THEN 30
                                WHEN %(naics_2)s IS NOT NULL AND f.naics IS NOT NULL
                                     AND LEFT(f.naics, 1) = LEFT(%(naics_2)s, 1) THEN 10
                                ELSE 0
                            END
                            -- Geography scoring (0-30 points)
                            + CASE WHEN f.state = %(state)s THEN 20 ELSE 0 END
                            + CASE WHEN f.city = %(city)s THEN 10 ELSE 0 END
                            -- Size similarity (0-20 points)
                            + CASE
                                WHEN %(emp)s > 0 AND f.naics IS NOT NULL THEN
                                    CASE
                                        WHEN %(emp)s = 0 THEN 5
                                        ELSE GREATEST(0, 20 - (ABS(%(emp)s - COALESCE(
                                            (SELECT COUNT(*) FROM f7_employers_deduped f2
                                             WHERE f2.naics = f.naics AND f2.state = f.state
                                             AND f2.employer_id != f.employer_id), 0
                                        )) * 0))
                                    END
                                ELSE 5
                            END
                        ) as match_score
                    FROM f7_employers_deduped f
                    WHERE f.exclude_from_counts IS NOT TRUE
                      AND (
                          (%(naics_2)s IS NOT NULL AND f.naics = %(naics_2)s)
                          OR (%(naics_4)s IS NOT NULL AND f.naics_detailed IS NOT NULL
                              AND LEFT(f.naics_detailed, 4) = %(naics_4)s)
                          OR (f.state = %(state)s AND f.naics IS NOT NULL
                              AND LEFT(f.naics, 1) = LEFT(%(naics_2)s, 1))
                      )
                )
                SELECT employer_id, employer_name, city, state, naics, naics_detailed,
                       match_score
                FROM scored
                WHERE match_score >= 20
                ORDER BY match_score DESC
                LIMIT %(lim)s
            """, {
                'naics_2': naics_2,
                'naics_4': naics_4,
                'state': target_state,
                'city': target.get('site_city', ''),
                'emp': target_emp,
                'lim': limit
            })
            siblings = cur.fetchall()

            # Describe match quality for each sibling
            results = []
            for s in siblings:
                match_reasons = []
                s_naics = s.get('naics_detailed') or s.get('naics') or ''
                if naics_4 and s_naics[:4] == naics_4:
                    match_reasons.append(f"Same 4-digit NAICS ({naics_4})")
                elif naics_2 and (s.get('naics') or '') == naics_2:
                    match_reasons.append(f"Same 2-digit sector ({naics_2})")
                if s.get('state') == target_state:
                    match_reasons.append(f"Same state ({target_state})")
                if s.get('city') == target.get('site_city'):
                    match_reasons.append(f"Same city ({s.get('city')})")

                results.append({
                    'employer_id': s['employer_id'],
                    'employer_name': s['employer_name'],
                    'city': s['city'],
                    'state': s['state'],
                    'naics': s.get('naics'),
                    'naics_detailed': s.get('naics_detailed'),
                    'match_score': s['match_score'],
                    'match_reasons': match_reasons
                })

            return {
                "target": {
                    "establishment_id": estab_id,
                    "estab_name": target.get('estab_name'),
                    "site_state": target_state,
                    "naics_code": naics_code,
                    "employee_count": target_emp
                },
                "siblings": results,
                "total_found": len(results)
            }


@router.post("/api/admin/refresh-scorecard")
def refresh_scorecard(request: Request):
    """Refresh the mv_organizing_scorecard materialized view.
    Requires admin role when auth is enabled.
    Call after data pipeline updates (new matches, new OSHA data, etc.)."""
    # Admin-only when auth is enabled
    from ..config import JWT_SECRET
    if JWT_SECRET:
        user = getattr(request.state, "user", None)
        role = getattr(request.state, "role", None)
        if not user or user == "anonymous" or role != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")

    import time
    from ..database import get_raw_connection
    conn = get_raw_connection()
    conn.autocommit = True
    try:
        cur = conn.cursor()
        t0 = time.time()
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_organizing_scorecard")
        elapsed = time.time() - t0
        cur.execute("SELECT COUNT(*) FROM mv_organizing_scorecard")
        count = cur.fetchone()[0]
    finally:
        conn.close()
    return {
        "status": "ok",
        "rows": count,
        "elapsed_seconds": round(elapsed, 1)
    }


@router.get("/api/admin/data-freshness")
def get_data_freshness():
    """Return freshness info for all data sources."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_name, display_name, last_updated,
                       record_count, date_range_start, date_range_end, notes
                FROM data_source_freshness
                ORDER BY display_name
            """)
            rows = cur.fetchall()
            sources = []
            total_records = 0
            oldest_update = None
            for r in rows:
                updated = r['last_updated']
                sources.append({
                    'source_name': r['source_name'],
                    'display_name': r['display_name'],
                    'last_updated': str(updated) if updated else None,
                    'record_count': r['record_count'],
                    'date_range_start': str(r['date_range_start']) if r['date_range_start'] else None,
                    'date_range_end': str(r['date_range_end']) if r['date_range_end'] else None,
                    'notes': r['notes'],
                })
                total_records += r['record_count'] or 0
                if updated and (oldest_update is None or updated < oldest_update):
                    oldest_update = updated

            return {
                "sources": sources,
                "source_count": len(sources),
                "total_records": total_records,
                "oldest_update": str(oldest_update) if oldest_update else None,
            }


@router.post("/api/admin/refresh-freshness")
def refresh_freshness(request: Request):
    """Re-query all data sources to update freshness counts and dates.
    Requires admin role when auth is enabled."""
    from ..config import JWT_SECRET
    if JWT_SECRET:
        user = getattr(request.state, "user", None)
        role = getattr(request.state, "role", None)
        if not user or user == "anonymous" or role != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")

    import time
    import subprocess
    t0 = time.time()
    script = os.path.join(
        os.path.dirname(__file__), '..', '..',
        'scripts', 'maintenance', 'create_data_freshness.py'
    )
    result = subprocess.run(
        ['py', script, '--refresh'],
        capture_output=True, text=True, timeout=120
    )
    elapsed = time.time() - t0

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Refresh failed: {result.stderr[:500]}")

    return {
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "output": result.stdout[:1000],
    }
