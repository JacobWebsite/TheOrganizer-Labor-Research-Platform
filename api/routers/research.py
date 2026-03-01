"""
Research Agent Router — Deep Dive company intelligence system.

Endpoints:
  POST /api/research/run         — Start a new deep dive on a company
  GET  /api/research/status/{id} — Check progress of a running deep dive
  GET  /api/research/result/{id} — Get the completed dossier
  GET  /api/research/runs        — List all research runs (with filters)
  GET  /api/research/vocabulary  — List all valid fact attribute names

Phase 2+ (scaffolded but not active yet):
  GET  /api/research/strategies  — View learned strategies by industry
"""
import logging
import os
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from ..database import get_db

router = APIRouter(prefix="/api/research", tags=["research"])
_log = logging.getLogger("labor_api.research")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------
class ResearchRequest(BaseModel):
    """What the frontend sends to start a deep dive."""
    company_name: str                          # Required: the company to research
    employer_id: Optional[str] = None           # Optional: if we already know the DB record (hex string)
    naics_code: Optional[str] = None           # Optional: industry hint
    company_type: Optional[str] = None         # Optional: public/private/nonprofit/government
    state: Optional[str] = None                # Optional: state hint
    company_address: Optional[str] = None      # Optional: address hint for stricter matching


class FactReviewRequest(BaseModel):
    """Human review of a single research fact."""
    verdict: Literal["confirmed", "rejected", "irrelevant"]
    notes: Optional[str] = None


class HumanScoreRequest(BaseModel):
    """Manual quality score override for a research run."""
    human_quality_score: float


# ---------------------------------------------------------------------------
# POST /api/research/run — Start a new deep dive
# ---------------------------------------------------------------------------
@router.post("/run")
async def start_research_run(request: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Start a deep dive research run on a company.

    Creates a research_runs record with status='pending', then kicks off
    the actual research in the background. Returns immediately with the
    run ID so the frontend can poll for progress.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Auto-lookup employer_id if not provided
            employer_id = request.employer_id
            if not employer_id:
                from scripts.research.employer_lookup import lookup_employer
                emp_id, emp_name, method = lookup_employer(
                    cur, request.company_name, request.state, request.company_address
                )
                if emp_id:
                    employer_id = emp_id
                    _log.info("Auto-linked %r -> %s (%s) [%s]",
                              request.company_name, emp_name, emp_id, method)

            # If employer_id known (provided or auto-looked-up), fetch info
            known_info = {}
            if employer_id:
                cur.execute("""
                    SELECT employer_name, naics, city, state, latest_unit_size
                    FROM f7_employers_deduped
                    WHERE employer_id = %s
                    LIMIT 1
                """, (employer_id,))
                row = cur.fetchone()
                if row:
                    known_info = dict(row)
                else:
                    # Fallback: try master_employers (non-F7 employers)
                    cur.execute("""
                        SELECT display_name AS employer_name, naics, city, state,
                               employee_count AS latest_unit_size
                        FROM master_employers
                        WHERE master_id::TEXT = %s
                        LIMIT 1
                    """, (employer_id,))
                    mrow = cur.fetchone()
                    if mrow:
                        known_info = dict(mrow)

            # Dedup check: warn if recent high-quality run exists
            dedup_days = int(os.environ.get("RESEARCH_DEDUP_DAYS", "30"))
            dedup_quality = float(os.environ.get("RESEARCH_DEDUP_MIN_QUALITY", "7.0"))
            dedup_warning = None

            if employer_id and dedup_days > 0:
                cur.execute("""
                    SELECT id, overall_quality_score, completed_at
                    FROM research_runs
                    WHERE employer_id = %s AND status = 'completed'
                      AND overall_quality_score >= %s
                      AND completed_at >= NOW() - make_interval(days => %s)
                    ORDER BY overall_quality_score DESC
                    LIMIT 1
                """, (employer_id, dedup_quality, dedup_days))
                existing = cur.fetchone()
                if existing:
                    dedup_warning = {
                        "existing_run_id": existing['id'],
                        "existing_quality": float(existing['overall_quality_score']),
                        "message": f"A recent high-quality run already exists (#{existing['id']}, quality={float(existing['overall_quality_score']):.1f})"
                    }

            # Determine size bucket from employee count
            unit_size = known_info.get('latest_unit_size', 0) or 0
            if unit_size < 100:
                size_bucket = 'small'
            elif unit_size < 1000:
                size_bucket = 'medium'
            else:
                size_bucket = 'large'

            # Create the run record
            cur.execute("""
                INSERT INTO research_runs
                    (company_name, company_address, employer_id, industry_naics, company_type,
                     company_state, employee_size_bucket, status, current_step, progress_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', 'Queued for research...', 0)
                RETURNING id
            """, (
                request.company_name,
                request.company_address,
                employer_id,
                request.naics_code or known_info.get('naics'),
                request.company_type,
                request.state or known_info.get('state'),
                size_bucket,
            ))
            run_id = cur.fetchone()['id']

    # Schedule the actual research to run in the background
    background_tasks.add_task(_run_research_background, run_id)

    return {
        "run_id": run_id,
        "status": "pending",
        "warning": dedup_warning,
        "message": f"Deep dive started for '{request.company_name}'. Poll /api/research/status/{run_id} for progress."
    }


def _run_research_background(run_id: int):
    """Wrapper that imports and calls the research agent."""
    try:
        from scripts.research.agent import run_research
        run_research(run_id)
    except Exception as e:
        _log.exception(f"Research run {run_id} failed: {e}")
        # Mark the run as failed so the frontend knows
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE research_runs
                    SET status = 'failed',
                        current_step = %s,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                """, (f"FAILED: {str(e)[:200]}", run_id))



# ---------------------------------------------------------------------------
# GET /api/research/status/{run_id} — Check progress
# ---------------------------------------------------------------------------
@router.get("/status/{run_id}")
def get_research_status(run_id: int):
    """
    Check the current status of a research run.

    The frontend polls this endpoint every few seconds while a run
    is in progress, to show a progress bar and current step description.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, company_name, company_address, status, current_step, progress_pct,
                       started_at, completed_at, duration_seconds,
                       total_tools_called, total_facts_found, sections_filled,
                       total_cost_cents, overall_quality_score, quality_dimensions
                FROM research_runs
                WHERE id = %s
            """, (run_id,))
            run = cur.fetchone()

    if not run:
        raise HTTPException(status_code=404, detail=f"Research run {run_id} not found")

    return dict(run)


# ---------------------------------------------------------------------------
# GET /api/research/result/{run_id} — Get completed dossier
# ---------------------------------------------------------------------------
@router.get("/result/{run_id}")
def get_research_result(run_id: int):
    """
    Get the full results of a completed research run.

    Returns the dossier (the finished report) plus all the individual
    facts that were found, organized by section.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get the run record
            cur.execute("SELECT * FROM research_runs WHERE id = %s", (run_id,))
            run = cur.fetchone()
            if not run:
                raise HTTPException(status_code=404, detail=f"Research run {run_id} not found")

            if run['status'] != 'completed':
                return {
                    "run_id": run_id,
                    "status": run['status'],
                    "message": "Research is still in progress" if run['status'] == 'running'
                               else "Research has not started yet"
                }

            # Get all facts, organized by section (includes review fields)
            cur.execute("""
                SELECT f.id AS fact_id, f.dossier_section, f.attribute_name,
                       f.attribute_value, f.attribute_value_json,
                       f.source_type, f.source_name, f.source_url,
                       f.confidence, f.as_of_date, f.contradicts_fact_id,
                       f.human_verdict, f.human_notes, f.reviewed_at,
                       v.display_name, v.data_type
                FROM research_facts f
                LEFT JOIN research_fact_vocabulary v ON f.attribute_name = v.attribute_name
                WHERE f.run_id = %s
                ORDER BY f.dossier_section, f.attribute_name
            """, (run_id,))
            facts = cur.fetchall()

            # Get action log (what the agent did)
            cur.execute("""
                SELECT tool_name, execution_order, data_found, data_quality,
                       facts_extracted, latency_ms, result_summary, error_message
                FROM research_actions
                WHERE run_id = %s
                ORDER BY execution_order
            """, (run_id,))
            actions = cur.fetchall()

    # Organize facts by section
    sections = {}
    for fact in facts:
        section = fact['dossier_section']
        if section not in sections:
            sections[section] = []
        sections[section].append(dict(fact))

    return {
        "run_id": run_id,
        "company_name": run['company_name'],
        "status": "completed",
        "duration_seconds": run['duration_seconds'],
        "sections_filled": run['sections_filled'],
        "total_facts": run['total_facts_found'],
        "dossier": run['dossier_json'],       # The complete report as JSON
        "facts_by_section": sections,          # Individual facts grouped
        "action_log": [dict(a) for a in actions],  # What the agent did
        "quality_score": float(run['overall_quality_score']) if run['overall_quality_score'] else None,
        "quality_dimensions": run['quality_dimensions'] if run['quality_dimensions'] else None,
        "human_quality_score": float(run['human_quality_score']) if run.get('human_quality_score') else None,
    }



# ---------------------------------------------------------------------------
# GET /api/research/runs — List all research runs
# ---------------------------------------------------------------------------
@router.get("/runs")
def list_research_runs(
    status: Optional[str] = Query(None, description="Filter by status: pending/running/completed/failed"),
    employer_id: Optional[str] = Query(None, description="Filter by employer"),
    naics: Optional[str] = Query(None, description="Filter by 2-digit NAICS"),
    q: Optional[str] = Query(None, description="Search by company name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List research runs with optional filters, most recent first."""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = []
            params = []

            if status:
                conditions.append("status = %s")
                params.append(status)
            if employer_id:
                conditions.append("employer_id = %s")
                params.append(employer_id)
            if naics:
                conditions.append("industry_naics LIKE %s")
                params.append(f"{naics}%")
            if q:
                conditions.append("company_name ILIKE %s")
                params.append(f"%{q}%")

            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            cur.execute(f"""
                SELECT id, company_name, company_address, employer_id, industry_naics, company_type,
                       status, started_at, completed_at, duration_seconds,
                       sections_filled, total_facts_found, overall_quality_score,
                       progress_pct, current_step
                FROM research_runs
                {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            runs = cur.fetchall()

            # Get total count
            cur.execute(f"SELECT COUNT(*) as total FROM research_runs {where}", params)
            total = cur.fetchone()['total']

    return {
        "runs": [dict(r) for r in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# GET /api/research/candidates — Suggested employers for research
# ---------------------------------------------------------------------------
@router.get("/candidates")
def get_research_candidates(
    type: Literal["non_union", "union_reference"] = Query("non_union",
                       description="non_union: best targets for direct enhancement; "
                                   "union_reference: best F7 employers to enrich the reference pool"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Suggest employers where research would have the most impact.

    - **non_union** (default): Non-union employers with high DB scores but few
      data sources and no existing research. Sorted by potential uplift.
    - **union_reference**: F7 union employers that appear as Gower comparables
      for many non-union targets but have thin profiles. Enriching these
      improves similarity scores for all non-union employers.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            if type == "non_union":
                cur.execute("""
                    SELECT ts.master_id::TEXT AS employer_id,
                           ts.display_name AS employer_name,
                           ts.state, ts.city, ts.naics,
                           ts.employee_count AS latest_unit_size,
                           ts.signals_present AS factors_available,
                           ts.gold_standard_tier AS score_tier,
                           ts.source_count
                    FROM mv_target_scorecard ts
                    WHERE NOT ts.has_research
                      AND ts.signals_present >= 2
                      AND ts.has_enforcement
                    ORDER BY ts.enforcement_count DESC,
                             ts.signals_present ASC,
                             ts.source_count DESC
                    LIMIT %s
                """, (limit,))
            else:
                # union_reference: F7 employers with thin profiles
                # Prioritize those with low source coverage
                cur.execute("""
                    SELECT
                        f.employer_id, f.employer_name, f.state, f.city, f.naics,
                        f.latest_unit_size,
                        ds.source_count
                    FROM f7_employers_deduped f
                    JOIN mv_employer_data_sources ds ON ds.employer_id = f.employer_id
                    LEFT JOIN research_score_enhancements rse
                        ON rse.employer_id = f.employer_id
                    WHERE rse.id IS NULL
                      AND ds.source_count <= 2
                      AND f.latest_unit_size IS NOT NULL
                    ORDER BY ds.source_count ASC,
                             f.latest_unit_size DESC NULLS LAST
                    LIMIT %s
                """, (limit,))

            rows = cur.fetchall()

    return {"candidates": [dict(r) for r in rows], "total": len(rows), "type": type}


# ---------------------------------------------------------------------------
# GET /api/research/vocabulary — List all valid fact attributes
# ---------------------------------------------------------------------------
@router.get("/vocabulary")
def get_fact_vocabulary(section: Optional[str] = Query(None, description="Filter by dossier section")):
    """
    List all valid attribute names the research agent can use.

    This is the 'dictionary' of facts. Useful for understanding what
    the agent looks for, and for building frontend display logic.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            if section:
                cur.execute("""
                    SELECT attribute_name, display_name, dossier_section, data_type,
                           existing_table, description
                    FROM research_fact_vocabulary
                    WHERE dossier_section = %s
                    ORDER BY dossier_section, attribute_name
                """, (section,))
            else:
                cur.execute("""
                    SELECT attribute_name, display_name, dossier_section, data_type,
                           existing_table, description
                    FROM research_fact_vocabulary
                    ORDER BY dossier_section, attribute_name
                """)
            vocab = cur.fetchall()

    return {"vocabulary": [dict(v) for v in vocab], "total": len(vocab)}


# ---------------------------------------------------------------------------
# POST /api/research/facts/{fact_id}/review — Human fact review
# ---------------------------------------------------------------------------
@router.post("/facts/{fact_id}/review")
def review_fact(fact_id: int, request: FactReviewRequest):
    """
    Submit a human review verdict for a single research fact.

    Propagates the review into the learning loop: updates action-level
    data_quality and triggers strategy re-ranking when enough facts reviewed.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Verify fact exists
            cur.execute("SELECT id FROM research_facts WHERE id = %s", (fact_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found")

            cur.execute("""
                UPDATE research_facts
                SET human_verdict = %s,
                    human_notes = %s,
                    reviewed_at = NOW()
                WHERE id = %s
            """, (request.verdict, request.notes, fact_id))

    # Propagate to learning loop (outside transaction to avoid blocking)
    try:
        from scripts.research.auto_grader import apply_human_fact_review
        apply_human_fact_review(fact_id, request.verdict)
    except Exception as exc:
        _log.debug("Learning loop propagation failed for fact %d: %s", fact_id, exc)

    return {"fact_id": fact_id, "verdict": request.verdict, "message": "Review saved"}


# ---------------------------------------------------------------------------
# GET /api/research/runs/{run_id}/review-summary — Review progress
# ---------------------------------------------------------------------------
@router.get("/runs/{run_id}/review-summary")
def get_review_summary(run_id: int):
    """
    Get a summary of human review progress for a research run.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM research_runs WHERE id = %s", (run_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Research run {run_id} not found")

            cur.execute("""
                SELECT
                    COUNT(*) AS total_facts,
                    COUNT(*) FILTER (WHERE human_verdict IS NOT NULL) AS reviewed,
                    COUNT(*) FILTER (WHERE human_verdict IS NULL) AS unreviewed,
                    COUNT(*) FILTER (WHERE human_verdict = 'confirmed') AS confirmed,
                    COUNT(*) FILTER (WHERE human_verdict = 'rejected') AS rejected,
                    COUNT(*) FILTER (WHERE human_verdict = 'irrelevant') AS irrelevant
                FROM research_facts
                WHERE run_id = %s
            """, (run_id,))
            row = cur.fetchone()

    return {"run_id": run_id, **{k: v for k, v in dict(row).items()}}


# ---------------------------------------------------------------------------
# PATCH /api/research/runs/{run_id}/human-score — Set human quality score
# ---------------------------------------------------------------------------
@router.patch("/runs/{run_id}/human-score")
def set_human_score(run_id: int, request: HumanScoreRequest):
    """
    Set a manual human quality score (0.0-10.0) for a research run.
    """
    if request.human_quality_score < 0.0 or request.human_quality_score > 10.0:
        raise HTTPException(status_code=422, detail="human_quality_score must be between 0.0 and 10.0")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM research_runs WHERE id = %s", (run_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"Research run {run_id} not found")

            cur.execute("""
                UPDATE research_runs
                SET human_quality_score = %s
                WHERE id = %s
            """, (request.human_quality_score, run_id))

    return {"run_id": run_id, "human_quality_score": request.human_quality_score}


# ---------------------------------------------------------------------------
# GET /api/research/strategies — View learned strategies (Phase 2)
# ---------------------------------------------------------------------------
@router.get("/strategies")
def get_research_strategies(
    naics: Optional[str] = Query(None, description="2-digit NAICS filter"),
    company_type: Optional[str] = Query(None, description="public/private/nonprofit/government"),
):
    """
    View the agent's learned strategies — which tools work best for
    which types of companies. Only meaningful after 30+ runs.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = []
            params = []

            if naics:
                conditions.append("industry_naics_2digit = %s")
                params.append(naics)
            if company_type:
                conditions.append("company_type = %s")
                params.append(company_type)

            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            cur.execute(f"""
                SELECT tool_name, industry_naics_2digit, company_type,
                       company_size_bucket, times_tried, times_found_data,
                       hit_rate, avg_quality, avg_latency_ms, recommended_order
                FROM research_strategies
                {where}
                ORDER BY hit_rate DESC
            """, params)
            strategies = cur.fetchall()

    return {"strategies": [dict(s) for s in strategies], "total": len(strategies)}
