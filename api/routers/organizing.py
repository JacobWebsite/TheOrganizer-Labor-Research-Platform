from fastapi import APIRouter, Query, HTTPException
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
    Get scored organizing targets based on 8-factor system (0-100 points):
    - Company union shops (20): Related locations with union presence
    - Industry density (10): Union density in NAICS sector (hierarchical NAICS)
    - Geographic favorability (10): NLRB win rate + state density + RTW adjustment
    - Size (10): Sweet spot 50-250 employees
    - OSHA (10): Violations normalized to industry average + severity
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

            cur.execute("SELECT state, members_total FROM epi_state_benchmarks")
            state_members = {r['state']: float(r['members_total'] or 0) for r in cur.fetchall()}

            cur.execute("SELECT matrix_code, employment_change_pct FROM bls_industry_projections")
            projections = {r['matrix_code']: float(r['employment_change_pct'] or 0) for r in cur.fetchall()}
            # Map 2-digit NAICS to BLS composite codes (31-33->Manufacturing, etc.)
            _BLS_ALIASES = {
                '310000': '31-330', '320000': '31-330', '330000': '31-330',
                '440000': '44-450', '450000': '44-450',
                '480000': '48-490', '490000': '48-490',
            }
            for alias, real in _BLS_ALIASES.items():
                if real in projections and alias not in projections:
                    projections[alias] = projections[real]

            # New reference data for Phase 2 scoring upgrades
            cur.execute("SELECT naics_prefix, avg_violations_per_estab FROM ref_osha_industry_averages")
            osha_avgs = {r['naics_prefix']: float(r['avg_violations_per_estab']) for r in cur.fetchall()}

            cur.execute("SELECT state FROM ref_rtw_states")
            rtw_set = {r['state'].strip() for r in cur.fetchall()}

            cur.execute("SELECT state, win_rate_pct FROM ref_nlrb_state_win_rates")
            nlrb_rates = {r['state'].strip(): float(r['win_rate_pct']) for r in cur.fetchall()}

            # Pre-fetch F7 matches (powers score_company_unions)
            cur.execute("SELECT establishment_id, f7_employer_id FROM osha_f7_matches")
            f7_match_set = {r['establishment_id'] for r in cur.fetchall()}

            # Pre-fetch federal contractor data (powers score_contracts)
            cur.execute("""
                SELECT DISTINCT m.establishment_id,
                       c.federal_obligations, c.federal_contract_count
                FROM osha_f7_matches m
                JOIN corporate_identifier_crosswalk c ON c.f7_employer_id = m.f7_employer_id
                WHERE c.is_federal_contractor = TRUE
            """)
            federal_contracts = {r['establishment_id']: {
                'obligations': float(r['federal_obligations'] or 0),
                'count': r['federal_contract_count'] or 0
            } for r in cur.fetchall()}

            # Pre-fetch similarity scores (powers score_similarity)
            cur.execute("""
                SELECT m.establishment_id, me.similarity_score, me.nlrb_predicted_win_pct
                FROM osha_f7_matches m
                JOIN mergent_employers me ON me.matched_f7_employer_id = m.f7_employer_id
                WHERE me.similarity_score IS NOT NULL OR me.nlrb_predicted_win_pct IS NOT NULL
            """)
            similarity_scores = {}
            nlrb_predicted = {}
            for r in cur.fetchall():
                if r['similarity_score'] is not None:
                    similarity_scores[r['establishment_id']] = float(r['similarity_score'])
                if r['nlrb_predicted_win_pct'] is not None:
                    nlrb_predicted[r['establishment_id']] = float(r['nlrb_predicted_win_pct'])

            # Load NLRB industry win rates for enhanced scoring
            cur.execute("SELECT naics_2, win_rate_pct FROM ref_nlrb_industry_win_rates")
            nlrb_industry_rates = {r['naics_2']: float(r['win_rate_pct']) for r in cur.fetchall()}

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
                naics_code = r.get('naics_code') or ''
                naics_2 = naics_code[:2]
                site_state = r.get('site_state', '')
                emp_count = r.get('employee_count', 0) or 0

                # 1. Company union shops (check if matched to F7 employer via osha_f7_matches)
                estab_id = r.get('establishment_id', '')
                score_company_unions = 20 if estab_id in f7_match_set else 0

                # 2. Industry density (hierarchical NAICS lookup)
                ind_pct = industry_density.get(naics_2, 0)
                score_industry_density = 10 if ind_pct > 20 else 8 if ind_pct > 10 else 5 if ind_pct > 5 else 2

                # 3. Geographic favorability (RTW + NLRB win rate + state density)
                score_geographic = _score_geographic(site_state, rtw_set, nlrb_rates, state_members)

                # 4. Size (sweet spot 50-250)
                score_size = _score_size(emp_count)

                # 5. OSHA violations (normalized to industry average)
                total_viols = r.get('total_violations', 0) or 0
                willful = r.get('willful_count', 0) or 0
                repeat = r.get('repeat_count', 0) or 0
                score_osha, osha_ratio = _score_osha_normalized(total_viols, willful, repeat, naics_code, osha_avgs)

                # 6. NLRB (enhanced: predicted win % from state + industry + size patterns)
                predicted_pct = nlrb_predicted.get(estab_id)
                if predicted_pct is not None:
                    score_nlrb = 10 if predicted_pct >= 82 else 8 if predicted_pct >= 78 else 5 if predicted_pct >= 74 else 3 if predicted_pct >= 70 else 1
                else:
                    # Fallback: state win rate + industry bonus
                    win_rate = nlrb_rates.get(site_state, nlrb_rates.get('US', 75.0))
                    ind_rate = nlrb_industry_rates.get(naics_2, nlrb_industry_rates.get('US', 68.0))
                    blended = win_rate * 0.6 + ind_rate * 0.4
                    score_nlrb = 10 if blended >= 82 else 8 if blended >= 78 else 5 if blended >= 74 else 3 if blended >= 70 else 1

                # 7. Contracts (federal contractor data via crosswalk)
                fed = federal_contracts.get(estab_id)
                if fed:
                    oblig = fed['obligations']
                    score_contracts = 10 if oblig > 5_000_000 else 7 if oblig > 1_000_000 else 4 if oblig > 100_000 else 2
                else:
                    score_contracts = 0

                # 8. Projections
                proj_pct = projections.get(f"{naics_2}0000", 0)
                score_projections = 10 if proj_pct > 10 else 7 if proj_pct > 5 else 4 if proj_pct > 0 else 2

                # 9. Similarity (Gower distance to union employers)
                sim = similarity_scores.get(estab_id)
                if sim is not None:
                    score_similarity = 10 if sim >= 0.80 else 7 if sim >= 0.60 else 4 if sim >= 0.40 else 1
                else:
                    score_similarity = 0

                organizing_score = (score_company_unions + score_industry_density + score_geographic +
                                   score_size + score_osha + score_nlrb + score_contracts + score_projections +
                                   score_similarity)

                if organizing_score >= min_score:
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
                        'has_f7_match': estab_id in f7_match_set,
                        'has_federal_contracts': estab_id in federal_contracts,
                        'federal_obligations': fed['obligations'] if fed else None,
                        'organizing_score': organizing_score,
                        'osha_industry_ratio': osha_ratio,
                        'score_breakdown': {
                            'company_unions': score_company_unions,
                            'industry_density': score_industry_density,
                            'geographic': score_geographic,
                            'size': score_size,
                            'osha': score_osha,
                            'nlrb': score_nlrb,
                            'contracts': score_contracts,
                            'projections': score_projections,
                            'similarity': score_similarity
                        },
                        'nlrb_predicted_win_pct': predicted_pct or nlrb_rates.get(site_state, nlrb_rates.get('US', 75.0))
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


@router.get("/api/organizing/scorecard/{estab_id}")
def get_scorecard_detail(estab_id: str):
    """Get detailed scorecard for a specific establishment with 8-factor breakdown.
    Phase 2 upgrades: OSHA normalization, geographic favorability, refined size scoring."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get base establishment data
            cur.execute("""
                SELECT * FROM v_osha_organizing_targets WHERE establishment_id = %s
            """, [estab_id])
            base = cur.fetchone()
            if not base:
                raise HTTPException(status_code=404, detail="Establishment not found")

            naics_code = base.get('naics_code') or ''
            naics_2 = naics_code[:2] if naics_code else None
            est_state = base.get('site_state')
            emp_count = base.get('employee_count', 0) or 0
            estab_name = base.get('estab_name', '')

            # Load reference data
            cur.execute("SELECT naics_prefix, avg_violations_per_estab FROM ref_osha_industry_averages")
            osha_avgs = {r['naics_prefix']: float(r['avg_violations_per_estab']) for r in cur.fetchall()}

            cur.execute("SELECT state FROM ref_rtw_states")
            rtw_set = {r['state'].strip() for r in cur.fetchall()}

            cur.execute("SELECT state, win_rate_pct FROM ref_nlrb_state_win_rates")
            nlrb_rates = {r['state'].strip(): float(r['win_rate_pct']) for r in cur.fetchall()}

            cur.execute("SELECT state, members_total FROM epi_state_benchmarks")
            state_members_map = {r['state']: float(r['members_total'] or 0) for r in cur.fetchall()}

            # 1. Company union shops (check osha_f7_matches first, then fuzzy fallback)
            cur.execute("""
                SELECT f7_employer_id FROM osha_f7_matches WHERE establishment_id = %s
            """, [estab_id])
            f7_match = cur.fetchone()
            if f7_match:
                has_related_union = True
            else:
                cur.execute("""
                    SELECT COUNT(*) > 0 as has_union FROM f7_employers_deduped
                    WHERE similarity(employer_name_aggressive, %s) > 0.5
                """, [estab_name])
                has_related_union = cur.fetchone()['has_union']
            score_company_unions = 20 if has_related_union else 0

            # 2. Industry density (hierarchical NAICS)
            score_industry_density = 2
            if naics_2:
                cur.execute("""
                    SELECT union_density_pct FROM v_naics_union_density WHERE naics_2digit = %s
                """, [naics_2])
                density_row = cur.fetchone()
                if density_row and density_row['union_density_pct']:
                    pct = float(density_row['union_density_pct'])
                    score_industry_density = 10 if pct > 20 else 8 if pct > 10 else 5 if pct > 5 else 2

            # 3. Geographic favorability (RTW + NLRB win rate + state density)
            score_geographic = _score_geographic(est_state or '', rtw_set, nlrb_rates, state_members_map)
            is_rtw = est_state in rtw_set if est_state else False
            state_win_rate = nlrb_rates.get(est_state, nlrb_rates.get('US', 75.0)) if est_state else None

            # 4. Size score (refined sweet spot)
            score_size = _score_size(emp_count)

            # 5. OSHA score (normalized to industry average)
            total_viols = base.get('total_violations', 0) or 0
            willful = base.get('willful_count', 0) or 0
            repeat = base.get('repeat_count', 0) or 0
            score_osha, osha_ratio = _score_osha_normalized(total_viols, willful, repeat, naics_code, osha_avgs)

            # 6. NLRB score (enhanced: predicted win % + direct case count)
            cur.execute("""
                SELECT COUNT(*) as cnt FROM nlrb_participants
                WHERE participant_name ILIKE %s AND participant_type = 'Employer'
            """, [f"%{estab_name[:20]}%"])
            nlrb_count = cur.fetchone()['cnt']

            # Get predicted win pct from mergent_employers via osha_f7_matches
            nlrb_predicted_pct = None
            nlrb_factors = None
            cur.execute("""
                SELECT me.nlrb_predicted_win_pct, me.nlrb_success_factors
                FROM osha_f7_matches m
                JOIN mergent_employers me ON me.matched_f7_employer_id = m.f7_employer_id
                WHERE m.establishment_id = %s AND me.nlrb_predicted_win_pct IS NOT NULL
                LIMIT 1
            """, [estab_id])
            nlrb_row = cur.fetchone()
            if nlrb_row:
                nlrb_predicted_pct = float(nlrb_row['nlrb_predicted_win_pct'])
                nlrb_factors = nlrb_row['nlrb_success_factors']

            # Load NLRB industry win rate for this employer's industry
            nlrb_industry_rate = None
            if naics_2:
                cur.execute("SELECT win_rate_pct FROM ref_nlrb_industry_win_rates WHERE naics_2 = %s", [naics_2])
                ir = cur.fetchone()
                if ir:
                    nlrb_industry_rate = float(ir['win_rate_pct'])

            # Score: use predicted pct if available, else case count
            if nlrb_predicted_pct is not None:
                score_nlrb = 10 if nlrb_predicted_pct >= 82 else 8 if nlrb_predicted_pct >= 78 else 5 if nlrb_predicted_pct >= 74 else 3 if nlrb_predicted_pct >= 70 else 1
            else:
                score_nlrb = min(10, nlrb_count * 5)

            # 7. Contracts score (NY/NYC state contracts + federal via crosswalk)
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

            # Federal contracts via osha_f7_matches -> crosswalk
            federal_funding = 0
            federal_count = 0
            cur.execute("""
                SELECT c.federal_obligations, c.federal_contract_count
                FROM osha_f7_matches m
                JOIN corporate_identifier_crosswalk c ON c.f7_employer_id = m.f7_employer_id
                WHERE m.establishment_id = %s AND c.is_federal_contractor = TRUE
            """, [estab_id])
            fed_row = cur.fetchone()
            if fed_row:
                federal_funding = float(fed_row['federal_obligations'] or 0)
                federal_count = fed_row['federal_contract_count'] or 0

            total_funding = ny_funding + nyc_funding + federal_funding
            score_contracts = 10 if total_funding > 5000000 else 7 if total_funding > 1000000 else 4 if total_funding > 100000 else 2 if total_funding > 0 else 0

            # 8. Projections score
            score_projections = 4
            if naics_2:
                # Try direct lookup, then BLS composite code alias
                _DETAIL_BLS_ALIASES = {
                    '31': '31-330', '32': '31-330', '33': '31-330',
                    '44': '44-450', '45': '44-450',
                    '48': '48-490', '49': '48-490',
                }
                cur.execute("""
                    SELECT employment_change_pct FROM bls_industry_projections WHERE matrix_code = %s
                """, [f"{naics_2}0000"])
                proj_row = cur.fetchone()
                if not proj_row and naics_2 in _DETAIL_BLS_ALIASES:
                    cur.execute("""
                        SELECT employment_change_pct FROM bls_industry_projections WHERE matrix_code = %s
                    """, [_DETAIL_BLS_ALIASES[naics_2]])
                    proj_row = cur.fetchone()
                if proj_row and proj_row['employment_change_pct'] is not None:
                    change = float(proj_row['employment_change_pct'])
                    score_projections = 10 if change > 10 else 7 if change > 5 else 4 if change > 0 else 2

            # 9. Similarity score (via osha_f7_matches -> mergent_employers)
            score_similarity = 0
            similarity_score_val = None
            cur.execute("""
                SELECT me.similarity_score
                FROM osha_f7_matches m
                JOIN mergent_employers me ON me.matched_f7_employer_id = m.f7_employer_id
                WHERE m.establishment_id = %s AND me.similarity_score IS NOT NULL
                LIMIT 1
            """, [estab_id])
            sim_row = cur.fetchone()
            if sim_row and sim_row['similarity_score'] is not None:
                similarity_score_val = float(sim_row['similarity_score'])
                score_similarity = 10 if similarity_score_val >= 0.80 else 7 if similarity_score_val >= 0.60 else 4 if similarity_score_val >= 0.40 else 1

            organizing_score = (score_company_unions + score_industry_density + score_geographic +
                              score_size + score_osha + score_nlrb + score_contracts + score_projections +
                              score_similarity)

            return {
                "establishment": base,
                "organizing_score": organizing_score,
                "score_breakdown": {
                    "company_unions": score_company_unions,
                    "industry_density": score_industry_density,
                    "geographic": score_geographic,
                    "size": score_size,
                    "osha": score_osha,
                    "nlrb": score_nlrb,
                    "contracts": score_contracts,
                    "projections": score_projections,
                    "similarity": score_similarity
                },
                "similarity_context": {
                    "similarity_score": similarity_score_val,
                    "comparables_url": f"/api/employers/{estab_id}/comparables" if similarity_score_val else None
                },
                "osha_context": {
                    "industry_ratio": osha_ratio,
                    "total_violations": total_viols,
                    "willful": willful,
                    "repeat": repeat
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
                    "total_funding": total_funding
                },
                "nlrb_context": {
                    "predicted_win_pct": nlrb_predicted_pct,
                    "state_win_rate": state_win_rate,
                    "industry_win_rate": nlrb_industry_rate,
                    "direct_case_count": nlrb_count,
                    "factors": nlrb_factors
                },
                "context": {
                    "has_related_union": has_related_union,
                    "nlrb_count": nlrb_count
                }
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
