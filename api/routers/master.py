from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from ..database import get_db
from ..helpers import safe_order_dir, safe_sort_col, TTLCache
from ..match_labels import build_master_citation, SOURCE_LABELS

router = APIRouter()

_MASTER_PK_COL: Optional[str] = None
_HAS_LABOR_COL: Optional[bool] = None
_INDEXES_READY = False
_stats_cache = TTLCache(ttl_seconds=300)  # 5-minute cache for expensive stats


def _normalize_q(q: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (q or "").lower()).split())


def _schema_flags(cur) -> Tuple[str, bool]:
    global _MASTER_PK_COL, _HAS_LABOR_COL
    if _MASTER_PK_COL is not None and _HAS_LABOR_COL is not None:
        return _MASTER_PK_COL, _HAS_LABOR_COL

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='master_employers'
          AND column_name IN ('master_id', 'id')
        ORDER BY CASE WHEN column_name='master_id' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="master_employers PK not found")
    _MASTER_PK_COL = row["column_name"]

    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema='public'
            AND table_name='master_employers'
            AND column_name='is_labor_org'
        ) AS e
        """
    )
    _HAS_LABOR_COL = bool(cur.fetchone()["e"])
    return _MASTER_PK_COL, _HAS_LABOR_COL


def _ensure_indexes(cur, pk_col: str) -> None:
    global _INDEXES_READY
    if _INDEXES_READY:
        return

    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_master_employers_canonical_name_trgm "
        "ON master_employers USING gin (canonical_name gin_trgm_ops)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_employers_state ON master_employers(state)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_employers_ein ON master_employers(ein)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_employers_naics ON master_employers(naics)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_employers_source_origin ON master_employers(source_origin)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_employers_quality ON master_employers(data_quality_score)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_master_employers_union ON master_employers(is_union)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_master_source_ids_master ON master_employer_source_ids(master_id)"
    )
    _INDEXES_READY = True


def _search_impl(
    cur,
    *,
    q: Optional[str],
    state: Optional[str],
    naics: Optional[str],
    min_employees: Optional[int],
    max_employees: Optional[int],
    source_origin: Optional[str],
    has_union: Optional[bool],
    is_federal_contractor: Optional[bool],
    is_nonprofit: Optional[bool],
    min_quality: Optional[int],
    sort: str,
    order: str,
    page: int,
    limit: int,
    force_non_union_targets: bool = False,
) -> Dict[str, Any]:
    pk_col, has_labor_col = _schema_flags(cur)
    _ensure_indexes(cur, pk_col)

    labor_select = "COALESCE(m.is_labor_org, FALSE) AS is_labor_org," if has_labor_col else "FALSE AS is_labor_org,"
    conditions: List[str] = ["1=1"]
    params: List[Any] = []

    if q:
        qn = _normalize_q(q)
        conditions.append("m.canonical_name ILIKE %s")
        params.append(f"%{qn}%")
    if state:
        conditions.append("m.state = %s")
        params.append(state.upper())
    if naics:
        conditions.append("m.naics LIKE %s")
        params.append(f"{naics}%")
    if min_employees is not None:
        conditions.append("m.employee_count >= %s")
        params.append(min_employees)
    if max_employees is not None:
        conditions.append("m.employee_count <= %s")
        params.append(max_employees)
    if source_origin:
        conditions.append("m.source_origin = %s")
        params.append(source_origin.lower())
    if has_union is not None:
        conditions.append("m.is_union = %s")
        params.append(has_union)
    if is_federal_contractor is not None:
        conditions.append("m.is_federal_contractor = %s")
        params.append(is_federal_contractor)
    if is_nonprofit is not None:
        conditions.append("m.is_nonprofit = %s")
        params.append(is_nonprofit)
    if min_quality is not None:
        conditions.append("m.data_quality_score >= %s")
        params.append(min_quality)

    if force_non_union_targets:
        conditions.append("m.is_union = FALSE")
        if has_labor_col:
            conditions.append("COALESCE(m.is_labor_org, FALSE) = FALSE")
        conditions.append("m.data_quality_score >= 40")

    where = " AND ".join(conditions)

    sort_map = {
        "name": "m.display_name",
        "quality": "m.data_quality_score",
        "employees": "m.employee_count",
    }
    sort_col = safe_sort_col(sort, sort_map, "name")
    order_dir = safe_order_dir(order)
    if force_non_union_targets and sort == "name":
        sort_col = "m.data_quality_score"
        order_dir = "DESC"

    cur.execute(f"SELECT COUNT(*) AS cnt FROM master_employers m WHERE {where}", params)
    total = int(cur.fetchone()["cnt"])

    offset = (page - 1) * limit
    q_params = params + [limit, offset]
    # LEFT JOIN target scorecard signals for non-union discovery
    ts_select = ""
    ts_join = ""
    if force_non_union_targets:
        ts_select = """,
          ts.signals_present,
          ts.has_enforcement,
          ts.enforcement_count,
          ts.has_recent_violations,
          ts.signal_osha,
          ts.signal_whd,
          ts.signal_nlrb,
          ts.signal_contracts,
          ts.signal_financial,
          ts.signal_industry_growth,
          ts.signal_union_density,
          ts.pillar_anger,
          ts.pillar_leverage"""
        ts_join = f"LEFT JOIN mv_target_scorecard ts ON ts.master_id = m.{pk_col}"

    cur.execute(
        f"""
        SELECT
          m.{pk_col} AS id,
          m.display_name,
          m.city,
          m.state,
          m.naics,
          m.employee_count,
          m.is_union,
          m.is_federal_contractor,
          m.is_nonprofit,
          {labor_select}
          m.source_origin,
          m.data_quality_score,
          COALESCE(src.source_count, 0) AS source_count
          {ts_select}
        FROM master_employers m
        LEFT JOIN (
          SELECT master_id, COUNT(DISTINCT source_system) AS source_count
          FROM master_employer_source_ids
          GROUP BY master_id
        ) src ON src.master_id = m.{pk_col}
        {ts_join}
        WHERE {where}
        ORDER BY {sort_col} {order_dir} NULLS LAST, m.{pk_col}
        LIMIT %s OFFSET %s
        """,
        q_params,
    )

    pages = int(math.ceil(total / limit)) if limit else 1
    return {"total": total, "page": page, "pages": pages, "results": cur.fetchall()}


@router.get("/api/master/search")
def master_search(
    q: Optional[str] = None,
    state: Optional[str] = None,
    naics: Optional[str] = None,
    min_employees: Optional[int] = Query(default=None, ge=0),
    max_employees: Optional[int] = Query(default=None, ge=0),
    source_origin: Optional[str] = None,
    has_union: Optional[bool] = None,
    is_federal_contractor: Optional[bool] = None,
    is_nonprofit: Optional[bool] = None,
    min_quality: Optional[int] = Query(default=None, ge=0, le=100),
    sort: str = Query(default="name", pattern="^(name|quality|employees)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
):
    """Search master employer universe with filters and pagination."""
    with get_db() as conn:
        with conn.cursor() as cur:
            return _search_impl(
                cur,
                q=q,
                state=state,
                naics=naics,
                min_employees=min_employees,
                max_employees=max_employees,
                source_origin=source_origin,
                has_union=has_union,
                is_federal_contractor=is_federal_contractor,
                is_nonprofit=is_nonprofit,
                min_quality=min_quality,
                sort=sort,
                order=order,
                page=page,
                limit=limit,
                force_non_union_targets=False,
            )


@router.get("/api/master/non-union-targets")
def master_non_union_targets(
    q: Optional[str] = None,
    state: Optional[str] = None,
    naics: Optional[str] = None,
    min_employees: Optional[int] = Query(default=None, ge=0),
    max_employees: Optional[int] = Query(default=None, ge=0),
    source_origin: Optional[str] = None,
    is_federal_contractor: Optional[bool] = None,
    is_nonprofit: Optional[bool] = None,
    min_quality: Optional[int] = Query(default=40, ge=0, le=100),
    sort: str = Query(default="quality", pattern="^(name|quality|employees)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
):
    """Discovery endpoint restricted to likely non-union targets."""
    with get_db() as conn:
        with conn.cursor() as cur:
            return _search_impl(
                cur,
                q=q,
                state=state,
                naics=naics,
                min_employees=min_employees,
                max_employees=max_employees,
                source_origin=source_origin,
                has_union=False,
                is_federal_contractor=is_federal_contractor,
                is_nonprofit=is_nonprofit,
                min_quality=min_quality,
                sort=sort,
                order=order,
                page=page,
                limit=limit,
                force_non_union_targets=True,
            )


@router.get("/api/master/{master_id:int}")
def master_detail(master_id: int):
    """Get full master employer profile plus linked source records."""
    with get_db() as conn:
        with conn.cursor() as cur:
            pk_col, has_labor_col = _schema_flags(cur)
            labor_select = "COALESCE(m.is_labor_org, FALSE) AS is_labor_org," if has_labor_col else "FALSE AS is_labor_org,"

            cur.execute(
                f"""
                SELECT
                  m.{pk_col} AS id, m.canonical_name, m.display_name, m.city, m.state, m.zip,
                  m.naics, m.employee_count, m.employee_count_source, m.ein,
                  m.is_union, m.is_public, m.is_federal_contractor, m.is_nonprofit,
                  {labor_select}
                  m.source_origin, m.data_quality_score, m.created_at, m.updated_at,
                  COALESCE(src.source_count, 0) AS source_count
                FROM master_employers m
                LEFT JOIN (
                  SELECT master_id, COUNT(DISTINCT source_system) AS source_count
                  FROM master_employer_source_ids
                  GROUP BY master_id
                ) src ON src.master_id = m.{pk_col}
                WHERE m.{pk_col} = %s
                """,
                [master_id],
            )
            master = cur.fetchone()
            if not master:
                raise HTTPException(status_code=404, detail="Master employer not found")

            cur.execute(
                """
                SELECT source_system, source_id, match_confidence, matched_at
                FROM master_employer_source_ids
                WHERE master_id = %s
                ORDER BY source_system, source_id
                """,
                [master_id],
            )
            source_ids = cur.fetchall()
            src_map: Dict[str, List[str]] = {}
            for r in source_ids:
                src_map.setdefault(r["source_system"], []).append(r["source_id"])

            enrichment: Dict[str, Any] = {}

            f7_ids = src_map.get("f7", [])
            if f7_ids:
                f7_id = f7_ids[0]
                cur.execute("SELECT * FROM mv_unified_scorecard WHERE employer_id::text = %s LIMIT 1", [f7_id])
                enrichment["scorecard"] = cur.fetchone()

            osha_ids = src_map.get("osha", [])
            if osha_ids:
                cur.execute(
                    """
                    SELECT
                      COUNT(*) AS establishments,
                      SUM(COALESCE(vs.violation_count, 0)) AS total_violations,
                      SUM(COALESCE(vs.total_penalties, 0)) AS total_penalties
                    FROM osha_establishments o
                    LEFT JOIN osha_violation_summary vs ON vs.establishment_id = o.establishment_id
                    WHERE o.establishment_id::text = ANY(%s)
                    """,
                    [osha_ids],
                )
                enrichment["osha_summary"] = cur.fetchone()

            nlrb_ids = src_map.get("nlrb", [])
            if nlrb_ids:
                cur.execute(
                    """
                    SELECT COUNT(*) AS participants
                    FROM nlrb_participants
                    WHERE id::text = ANY(%s)
                    """,
                    [nlrb_ids],
                )
                enrichment["nlrb_summary"] = cur.fetchone()

            whd_ids = src_map.get("whd", [])
            if whd_ids:
                cur.execute(
                    """
                    SELECT
                      COUNT(*) AS case_count,
                      SUM(COALESCE(backwages_amount, 0)) AS backwages_amount,
                      SUM(COALESCE(civil_penalties, 0)) AS civil_penalties
                    FROM whd_cases
                    WHERE case_id::text = ANY(%s)
                    """,
                    [whd_ids],
                )
                enrichment["whd_summary"] = cur.fetchone()

            sam_ids = src_map.get("sam", [])
            if sam_ids:
                cur.execute(
                    """
                    SELECT uei, legal_business_name, dba_name, physical_city, physical_state, naics_primary
                    FROM sam_entities
                    WHERE uei = ANY(%s)
                    ORDER BY uei
                    LIMIT 20
                    """,
                    [sam_ids],
                )
                enrichment["sam_records"] = cur.fetchall()

            bmf_ids = src_map.get("bmf", [])
            if bmf_ids:
                cur.execute(
                    """
                    SELECT ein, org_name, city, state, ntee_code, subsection_code, is_labor_org
                    FROM irs_bmf
                    WHERE ein = ANY(%s)
                    ORDER BY ein
                    LIMIT 20
                    """,
                    [bmf_ids],
                )
                enrichment["bmf_records"] = cur.fetchall()

            # Build match summary from source_ids grouped by source_system
            src_summary: Dict[str, Dict[str, Any]] = {}
            for r in source_ids:
                sys = r["source_system"]
                conf = float(r["match_confidence"]) if r.get("match_confidence") is not None else None
                if sys not in src_summary:
                    src_summary[sys] = {
                        "source_system": sys,
                        "source_label": SOURCE_LABELS.get(sys, sys),
                        "match_count": 0,
                        "best_confidence": conf,
                    }
                src_summary[sys]["match_count"] += 1
                if conf is not None:
                    prev = src_summary[sys]["best_confidence"]
                    if prev is None or conf > prev:
                        src_summary[sys]["best_confidence"] = conf

            match_summary = []
            for s in sorted(src_summary.values(), key=lambda x: x["best_confidence"] or 0, reverse=True):
                s["citation"] = build_master_citation(s["source_system"], s["best_confidence"])
                match_summary.append(s)

            return {"master": master, "source_ids": source_ids, "enrichment": enrichment, "match_summary": match_summary}


@router.get("/api/master/stats")
def master_stats():
    """Aggregate stats for the master employer universe."""
    cached = _stats_cache.get("master_stats")
    if cached is not None:
        return cached
    with get_db() as conn:
        with conn.cursor() as cur:
            pk_col, has_labor_col = _schema_flags(cur)
            _ensure_indexes(cur, pk_col)

            cur.execute("SELECT COUNT(*) AS total FROM master_employers")
            total = int(cur.fetchone()["total"])

            cur.execute(
                "SELECT source_origin, COUNT(*) AS cnt FROM master_employers GROUP BY 1 ORDER BY cnt DESC"
            )
            by_origin = cur.fetchall()

            cur.execute(
                """
                SELECT state, COUNT(*) AS cnt
                FROM master_employers
                WHERE state IS NOT NULL AND TRIM(state) <> ''
                GROUP BY 1
                ORDER BY cnt DESC
                LIMIT 20
                """
            )
            by_state = cur.fetchall()

            labor_expr = "COALESCE(is_labor_org, FALSE)" if has_labor_col else "FALSE"
            cur.execute(
                f"""
                SELECT
                  COUNT(*) FILTER (WHERE is_union) AS union_true,
                  COUNT(*) FILTER (WHERE is_nonprofit) AS nonprofit_true,
                  COUNT(*) FILTER (WHERE is_federal_contractor) AS contractor_true,
                  COUNT(*) FILTER (WHERE {labor_expr}) AS labor_org_true
                FROM master_employers
                """
            )
            flags = cur.fetchone()

            cur.execute(
                """
                SELECT
                  CASE
                    WHEN data_quality_score <= 20 THEN '0-20'
                    WHEN data_quality_score <= 40 THEN '21-40'
                    WHEN data_quality_score <= 60 THEN '41-60'
                    WHEN data_quality_score <= 80 THEN '61-80'
                    ELSE '81-100'
                  END AS tier,
                  COUNT(*) AS cnt
                FROM master_employers
                GROUP BY 1
                ORDER BY 1
                """
            )
            quality_distribution = cur.fetchall()

            cur.execute(
                """
                SELECT ROUND(AVG(source_count)::numeric, 2) AS avg_source_count
                FROM (
                  SELECT master_id, COUNT(DISTINCT source_system) AS source_count
                  FROM master_employer_source_ids
                  GROUP BY master_id
                ) s
                """
            )
            avg_source_count = cur.fetchone()["avg_source_count"]

            result = {
                "total": total,
                "by_source_origin": by_origin,
                "top_states": by_state,
                "flags": flags,
                "quality_distribution": quality_distribution,
                "avg_source_count": avg_source_count,
            }
            _stats_cache.set("master_stats", result)
            return result
