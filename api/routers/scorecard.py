from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from .organizing import get_organizing_scorecard, get_scorecard_detail

router = APIRouter()


@router.get("/api/scorecard/")
def get_scorecard_list(
    state: Optional[str] = None,
    naics_2digit: Optional[str] = None,
    min_employees: int = Query(default=25),
    max_employees: int = Query(default=5000),
    min_score: int = Query(default=0),
    has_contracts: Optional[str] = None,
    offset: int = Query(default=0, ge=0),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Paginated scorecard list wrapper over organizing scorecard data."""
    result = get_organizing_scorecard(
        state=state,
        naics_2digit=naics_2digit,
        min_employees=min_employees,
        max_employees=max_employees,
        min_score=min_score,
        has_contracts=has_contracts,
        limit=page_size,
        offset=offset,
    )
    data = result.get("results", [])
    total = result.get("total", 0)
    return {
        "data": data,
        "total": total,
        "offset": offset,
        "page_size": page_size,
        "has_more": (offset + page_size) < total,
    }


@router.get("/api/scorecard/states")
def get_scorecard_states():
    """Distinct states available in scorecard data, with counts."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT site_state AS state, COUNT(*) AS count
                FROM mv_organizing_scorecard
                WHERE site_state IS NOT NULL AND TRIM(site_state) <> ''
                GROUP BY site_state
                ORDER BY site_state
            """)
            rows = cur.fetchall()
    return rows


@router.get("/api/scorecard/versions")
def get_score_versions():
    """All score versions ordered newest first."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM score_versions
                ORDER BY created_at DESC
            """)
            return {"versions": cur.fetchall()}


@router.get("/api/scorecard/versions/current")
def get_current_score_version():
    """Latest score version."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM score_versions
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="No score versions found")
            return {"current": row}


# ============================================================================
# UNIFIED SCORECARD (Phase E3 — signal-strength scoring, all F7 employers)
# ============================================================================

@router.get("/api/scorecard/unified")
def get_unified_scorecard(
    state: Optional[str] = None,
    naics: Optional[str] = None,
    min_score: float = Query(default=0, ge=0, le=10),
    min_factors: int = Query(default=2, ge=1, le=8),
    score_tier: Optional[str] = None,
    has_osha: Optional[bool] = None,
    has_nlrb: Optional[bool] = None,
    has_research: Optional[bool] = None,
    sort: str = Query(default="score", pattern="^(score|size|factors|name|strategic_delta|score_delta)$"),
    offset: int = Query(default=0, ge=0),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Unified scorecard: weighted 8-factor scoring for all F7 employers."""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["factors_available >= %s"]
            params = [min_factors]

            if min_score > 0:
                conditions.append("unified_score >= %s")
                params.append(min_score)
            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if naics:
                conditions.append("naics LIKE %s")
                params.append(f"{naics}%")
            if score_tier:
                st = score_tier.strip()
                if st.upper() in {"TOP", "HIGH", "MEDIUM", "LOW"}:
                    conditions.append("score_tier_legacy = %s")
                    params.append(st.upper())
                else:
                    conditions.append("score_tier = %s")
                    params.append(st.title())
            if has_osha is True:
                conditions.append("has_osha")
            if has_osha is False:
                conditions.append("NOT has_osha")
            if has_nlrb is True:
                conditions.append("has_nlrb")
            if has_nlrb is False:
                conditions.append("NOT has_nlrb")
            if has_research is True:
                conditions.append("has_research")
            if has_research is False:
                conditions.append("NOT has_research")

            where = " AND ".join(conditions)

            sort_map = {
                "score": "weighted_score DESC NULLS LAST",
                "size": "latest_unit_size DESC NULLS LAST",
                "factors": "factors_available DESC, weighted_score DESC NULLS LAST",
                "name": "employer_name",
                "strategic_delta": "strategic_delta DESC NULLS LAST",
                "score_delta": "strategic_delta DESC NULLS LAST",
            }
            order = sort_map.get(sort, sort_map["score"])

            # Count
            cur.execute(f"SELECT COUNT(*) AS cnt FROM mv_unified_scorecard WHERE {where}", params)
            total = cur.fetchone()['cnt']

            # Results
            params.extend([page_size, offset])
            cur.execute(f"""
                SELECT employer_id, employer_name, state, city, naics,
                       latest_unit_size, latest_union_name, is_historical,
                       source_count, has_osha, has_nlrb, has_whd,
                       has_sam, has_sec, has_gleif, has_mergent,
                       is_federal_contractor, is_public,
                       score_osha, score_nlrb, score_whd, score_contracts,
                       score_union_proximity, score_financial, score_size, score_similarity,
                       factors_available, factors_total,
                       total_weight, weighted_score, unified_score, coverage_pct,
                       score_tier, score_tier_legacy,
                       has_research, research_run_id, research_quality,
                       strategic_delta, research_approach
                FROM mv_unified_scorecard
                WHERE {where}
                ORDER BY {order}
                LIMIT %s OFFSET %s
            """, params)
            data = cur.fetchall()

            for row in data:
                row["weighted_score"] = row.get("weighted_score", row.get("unified_score"))
                row["unified_score"] = row.get("unified_score", row.get("weighted_score"))
                row["legacy_score_tier"] = row.get("score_tier_legacy")
                # Backward compat aliases for renamed columns
                row["score_delta"] = row.get("strategic_delta")
                row["research_weighted_score"] = row.get("research_quality")

            return {
                "data": data,
                "total": total,
                "offset": offset,
                "page_size": page_size,
                "has_more": (offset + page_size) < total,
            }


@router.get("/api/scorecard/unified/stats")
def get_unified_scorecard_stats():
    """Aggregate stats for the unified scorecard."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_employers,
                    ROUND(AVG(weighted_score)::numeric, 2) AS avg_score,
                    MIN(weighted_score) AS min_score,
                    MAX(weighted_score) AS max_score,
                    ROUND(AVG(factors_available)::numeric, 1) AS avg_factors,
                    ROUND(AVG(coverage_pct)::numeric, 1) AS avg_coverage_pct
                FROM mv_unified_scorecard
            """)
            overview = cur.fetchone()

            cur.execute("""
                SELECT score_tier, COUNT(*) AS cnt
                FROM mv_unified_scorecard
                GROUP BY score_tier
                ORDER BY CASE score_tier
                    WHEN 'Priority' THEN 1 WHEN 'Strong' THEN 2
                    WHEN 'Promising' THEN 3 WHEN 'Moderate' THEN 4
                    WHEN 'Low' THEN 5
                END
            """)
            tiers = cur.fetchall()

            cur.execute("""
                SELECT factors_available, COUNT(*) AS cnt
                FROM mv_unified_scorecard
                GROUP BY factors_available
                ORDER BY factors_available
            """)
            factor_dist = cur.fetchall()

            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE score_osha IS NOT NULL) AS osha,
                    COUNT(*) FILTER (WHERE score_nlrb IS NOT NULL) AS nlrb,
                    COUNT(*) FILTER (WHERE score_whd IS NOT NULL) AS whd,
                    COUNT(*) FILTER (WHERE score_contracts IS NOT NULL) AS contracts,
                    COUNT(*) FILTER (WHERE score_union_proximity IS NOT NULL) AS union_proximity,
                    COUNT(*) FILTER (WHERE score_financial IS NOT NULL) AS financial,
                    COUNT(*) FILTER (WHERE score_size IS NOT NULL) AS size,
                    COUNT(*) FILTER (WHERE score_similarity IS NOT NULL) AS similarity
                FROM mv_unified_scorecard
            """)
            factor_coverage = cur.fetchone()

            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE has_research) AS researched,
                    ROUND(AVG(strategic_delta) FILTER (WHERE strategic_delta IS NOT NULL)::numeric, 2) AS avg_delta,
                    MAX(strategic_delta) AS max_delta
                FROM mv_unified_scorecard
            """)
            research_stats = cur.fetchone()

            return {
                "overview": overview,
                "tier_distribution": tiers,
                "factors_available_distribution": factor_dist,
                "factor_coverage": factor_coverage,
                "research_coverage": research_stats,
            }


@router.get("/api/scorecard/unified/states")
def get_unified_scorecard_states():
    """Distinct states in the unified scorecard with counts and avg scores."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT state, COUNT(*) AS count,
                       ROUND(AVG(weighted_score)::numeric, 2) AS avg_score,
                       ROUND(AVG(factors_available)::numeric, 1) AS avg_factors
                FROM mv_unified_scorecard
                WHERE state IS NOT NULL AND TRIM(state) <> ''
                GROUP BY state
                ORDER BY state
            """)
            return cur.fetchall()


@router.get("/api/scorecard/unified/{employer_id}")
def get_unified_scorecard_detail(employer_id: str):
    """Detailed unified scorecard for a single employer.

    Returns weighted score factors, metadata, and human-readable explanations.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM mv_unified_scorecard WHERE employer_id = %s", [employer_id])
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Employer not found in unified scorecard")

            data = dict(row)
            data["weighted_score"] = data.get("weighted_score", data.get("unified_score"))
            data["unified_score"] = data.get("unified_score", data.get("weighted_score"))
            data["legacy_score_tier"] = data.get("score_tier_legacy")
            data["score_delta"] = data.get("strategic_delta")
            data["research_weighted_score"] = data.get("research_quality")

            # Build score explanations
            explanations = {}
            if data.get('score_osha') is not None:
                explanations['osha'] = (
                    f"OSHA safety: {data.get('osha_total_violations', 0)} violations "
                    f"across {data.get('osha_estab_count', 0)} establishments, "
                    f"decay factor {data.get('osha_decay_factor', 1.0)}"
                )
            if data.get('score_nlrb') is not None:
                wins = data.get('nlrb_win_count', 0) or 0
                total = data.get('nlrb_election_count', 0) or 0
                ind_wins = data.get('nlrb_industry_wins_3yr', 0) or 0
                st_wins = data.get('nlrb_state_wins_3yr', 0) or 0
                momentum_parts = []
                if ind_wins > 0:
                    momentum_parts.append(f"{ind_wins} industry wins (3yr)")
                if st_wins > 0:
                    momentum_parts.append(f"{st_wins} state wins (3yr)")
                momentum_str = "; momentum: " + ", ".join(momentum_parts) if momentum_parts else ""
                explanations['nlrb'] = (
                    f"NLRB activity: {total} elections ({wins} union wins), "
                    f"latest {data.get('nlrb_latest_election', 'N/A')}"
                    f"{momentum_str}"
                )
            if data.get('score_whd') is not None:
                explanations['whd'] = (
                    f"Wage theft: {data.get('whd_case_count', 0)} cases, "
                    f"${data.get('whd_total_backwages', 0):,.0f} backwages, "
                    f"${data.get('whd_total_penalties', 0):,.0f} penalties"
                    + (", repeat violator" if data.get('whd_repeat_violator') else "")
                )
            if data.get('score_contracts') is not None:
                explanations['contracts'] = (
                    "Government contracts: federal-only data currently active; "
                    f"${data.get('federal_obligations', 0):,.0f} "
                    f"({data.get('federal_contract_count', 0)} contracts)."
                )
            explanations['union_proximity'] = (
                f"Union proximity: canonical group "
                + (f"#{data.get('canonical_group_id')}" if data.get('canonical_group_id') else "none (standalone)")
            )
            if data.get('score_financial') is not None:
                growth = data.get('bls_growth_pct')
                growth_str = f"{growth}% projected growth" if growth is not None else "no BLS data"
                explanations['financial'] = (
                    f"Financial: {growth_str}"
                    + (", public company" if data.get('is_public') else "")
                    + (", has 990 data" if data.get('has_990') else "")
                )
            explanations['size'] = f"Employer size: {data.get('latest_unit_size', 'unknown')} workers"
            if data.get("score_similarity") is not None:
                explanations["similarity"] = (
                    f"Statistical similarity: {data.get('unionized_comparable_count', 0)} unionized comparables, "
                    f"best Gower distance {data.get('best_distance')}"
                )
            explanations["weights"] = (
                "Weights: union proximity 3x, NLRB 3x, contracts 2x, "
                "industry growth 2x, financial 2x, OSHA 1x, WHD 1x. "
                "Size is a filter dimension (not weighted). Similarity disabled."
            )

            # Research enhancement info
            if data.get('has_research'):
                delta = data.get('strategic_delta')
                explanations['research'] = (
                    f"Research-enhanced: run #{data.get('research_run_id')}, "
                    f"delta {'+' if delta and delta > 0 else ''}{delta or 0}"
                )
                data['research_dossier_url'] = f"/api/research/result/{data['research_run_id']}"

            data['explanations'] = explanations
            return data


# ============================================================================
# LEGACY OSHA-CENTRIC SCORECARD (backward compatible)
# ============================================================================

@router.get("/api/scorecard/{estab_id}")
def get_scorecard_item(estab_id: str):
    """Scorecard detail passthrough for compatibility with /api/scorecard namespace."""
    return get_scorecard_detail(estab_id)
