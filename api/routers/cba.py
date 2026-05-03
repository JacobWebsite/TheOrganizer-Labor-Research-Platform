from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..database import get_db
from ..helpers import safe_order_dir, safe_sort_col

router = APIRouter()

# ---------------------------------------------------------------------------
# Category groupings for search/filter UI
# ---------------------------------------------------------------------------
CATEGORY_GROUPS = {
    "Compensation": ["wages_hours", "overtime", "shifts", "pay_period", "scheduling"],
    "Leave & Time Off": ["leave", "vacations", "sick_leave", "holidays"],
    "Benefits & Retirement": ["benefits", "pension", "disability", "childcare", "severance"],
    "Job Security & Discipline": ["job_security", "discipline", "probation", "seniority"],
    "Union Rights": ["union_security", "union_access", "steward", "employee_rights"],
    "Workplace Conditions": ["working_conditions", "safety", "technology", "uniforms", "drug_alcohol"],
    "Contract Structure": ["duration", "separability", "general", "preamble", "waiver", "successorship", "negotiations"],
    "Dispute Resolution": ["grievance", "arbitration"],
    "Management": ["management_rights", "subcontracting"],
    "Workforce": ["classifications", "vacancies", "transfers", "evaluation", "training", "apprenticeship", "referral", "temporary_employees"],
    "Other": ["other", "non_discrimination", "past_practices", "personnel_records", "travel", "housing", "political_activity", "joint_industry", "coverage", "no_strike", "calendar", "foreman", "superintendents", "signatory", "new_development", "building_acquisition"],
}

# Reverse lookup: category -> group name
CATEGORY_TO_GROUP: dict[str, str] = {}
for _group_name, _categories in CATEGORY_GROUPS.items():
    for _cat in _categories:
        CATEGORY_TO_GROUP[_cat] = _group_name

# Check at module load whether the updated view has section columns
_has_section_cols: bool | None = None


def _check_section_cols() -> bool:
    """Check if v_cba_provision_search has section_num column."""
    global _has_section_cols
    if _has_section_cols is not None:
        return _has_section_cols
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'v_cba_provision_search' AND column_name = 'section_num'"
                )
                _has_section_cols = cur.fetchone() is not None
    except Exception:
        _has_section_cols = False
    return _has_section_cols


def _section_cols() -> str:
    """Return section column SQL fragment if available."""
    if _check_section_cols():
        return (
            ", v.section_num, v.section_title"
            ", v.parent_section_num, v.parent_section_title"
        )
    return ""


_has_extracted_values: bool | None = None


def _check_extracted_values() -> bool:
    """Check if cba_provisions has extracted_values column."""
    global _has_extracted_values
    if _has_extracted_values is not None:
        return _has_extracted_values
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_attribute WHERE attrelid = 'cba_provisions'::regclass "
                    "AND attname = 'extracted_values' AND NOT attisdropped"
                )
                _has_extracted_values = cur.fetchone() is not None
    except Exception:
        _has_extracted_values = False
    return _has_extracted_values


def _base_query_filters(
    *,
    q: str | None,
    provision_class: str | None,
    category: str | None,
    category_group: str | None = None,
    union_name: str | None,
    employer_name: str | None,
    cba_id: int | None,
    modal_verb: str | None = None,
    min_confidence: float | None = None,
) -> tuple[str, list[Any]]:
    conditions = ["1=1"]
    params: list[Any] = []

    if q:
        conditions.append("to_tsvector('english', v.provision_text) @@ plainto_tsquery('english', %s)")
        params.append(q)
    if provision_class:
        conditions.append("v.provision_class = %s")
        params.append(provision_class)
    if category:
        conditions.append("v.category = %s")
        params.append(category)
    if category_group and category_group in CATEGORY_GROUPS:
        cats = CATEGORY_GROUPS[category_group]
        placeholders = ",".join(["%s"] * len(cats))
        conditions.append(f"v.category IN ({placeholders})")
        params.extend(cats)
    if union_name:
        conditions.append("v.union_name ILIKE %s")
        params.append(f"%{union_name}%")
    if employer_name:
        conditions.append("v.employer_name ILIKE %s")
        params.append(f"%{employer_name}%")
    if cba_id is not None:
        conditions.append("v.cba_id = %s")
        params.append(cba_id)
    if modal_verb:
        conditions.append("v.modal_verb = %s")
        params.append(modal_verb)
    if min_confidence is not None:
        conditions.append("p.confidence_score >= %s")
        params.append(min_confidence)

    return " AND ".join(conditions), params


@router.get("/api/cba/provisions/search")
def search_cba_provisions(
    q: str | None = None,
    provision_class: str | None = None,
    category: str | None = None,
    category_group: str | None = None,
    union_name: str | None = None,
    employer_name: str | None = None,
    cba_id: int | None = None,
    modal_verb: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=200),
    sort: str = Query(default="page_start", pattern="^(page_start|employer_name|union_name|provision_class|confidence_score|relevance)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    sort_map = {
        "page_start": "v.page_start",
        "employer_name": "v.employer_name",
        "union_name": "v.union_name",
        "provision_class": "v.provision_class",
        "confidence_score": "p.confidence_score",
    }

    # Default to relevance sort when a search query is provided
    effective_sort = sort
    if q and sort == "page_start":
        effective_sort = "relevance"

    where, params = _base_query_filters(
        q=q,
        provision_class=provision_class,
        category=category,
        category_group=category_group,
        union_name=union_name,
        employer_name=employer_name,
        cba_id=cba_id,
        modal_verb=modal_verb,
        min_confidence=min_confidence,
    )

    base_from = "v_cba_provision_search v JOIN cba_provisions p ON p.provision_id = v.provision_id"

    # Build ORDER BY clause -- relevance uses ts_rank and needs an extra param
    order_params: list[Any] = []
    if effective_sort == "relevance" and q:
        order_clause = "ts_rank(to_tsvector('english', v.provision_text), plainto_tsquery('english', %s)) DESC"
        order_params.append(q)
    else:
        sort_col = safe_sort_col(effective_sort, sort_map, "page_start")
        order_dir = safe_order_dir(order)
        order_clause = f"{sort_col} {order_dir} NULLS LAST"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {base_from} WHERE {where}", params)
            total = int(cur.fetchone()["cnt"])

            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                  v.provision_id,
                  v.cba_id,
                  v.employer_id,
                  v.employer_name,
                  v.union_name,
                  v.aff_abbr,
                  v.source_name,
                  v.category,
                  v.provision_class,
                  v.provision_text,
                  v.modal_verb,
                  v.page_start,
                  v.effective_date,
                  v.expiration_date,
                  v.state,
                  v.city,
                  v.naics_2digit,
                  p.page_end,
                  p.char_start,
                  p.char_end,
                  p.confidence_score,
                  p.model_version,
                  v.context_before,
                  v.context_after
                  {_section_cols()}
                FROM {base_from}
                WHERE {where}
                ORDER BY {order_clause}, v.provision_id
                LIMIT %s OFFSET %s
                """,
                params + order_params + [limit, offset],
            )
            rows = cur.fetchall()

    pages = int(math.ceil(total / limit)) if total else 0
    return {"total": total, "page": page, "pages": pages, "results": rows}


@router.get("/api/cba/provisions/classes")
def list_cba_provision_classes():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT category, provision_class, COUNT(*) AS cnt
                FROM cba_provisions
                GROUP BY category, provision_class
                ORDER BY category, cnt DESC, provision_class
                """
            )
            return {"results": cur.fetchall()}


@router.get("/api/cba/filter-options")
def list_cba_filter_options():
    """Return distinct employers, unions, and categories for filter dropdowns."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT d.employer_name_raw AS name, d.cba_id
                FROM cba_documents d
                WHERE d.employer_name_raw IS NOT NULL
                ORDER BY d.employer_name_raw
                """
            )
            employers = cur.fetchall()

            cur.execute(
                """
                SELECT DISTINCT d.union_name_raw AS name, d.cba_id
                FROM cba_documents d
                WHERE d.union_name_raw IS NOT NULL
                ORDER BY d.union_name_raw
                """
            )
            unions = cur.fetchall()

            cur.execute(
                """
                SELECT DISTINCT modal_verb
                FROM cba_provisions
                WHERE modal_verb IS NOT NULL
                ORDER BY modal_verb
                """
            )
            modal_verbs = [r["modal_verb"] for r in cur.fetchall()]

    return {
        "employers": employers,
        "unions": unions,
        "modal_verbs": modal_verbs,
    }


@router.get("/api/cba/documents")
def list_cba_documents(
    employer: str | None = None,
    union: str | None = None,
    category: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=200),
    sort: str = Query(default="cba_id", pattern="^(cba_id|employer_name_raw|union_name_raw|effective_date|expiration_date|page_count)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    """List all CBA documents with provision counts and category summary."""
    sort_map = {
        "cba_id": "d.cba_id",
        "employer_name_raw": "d.employer_name_raw",
        "union_name_raw": "d.union_name_raw",
        "effective_date": "d.effective_date",
        "expiration_date": "d.expiration_date",
        "page_count": "d.page_count",
    }
    sort_col = safe_sort_col(sort, sort_map, "cba_id")
    order_dir = safe_order_dir(order)

    conditions = ["1=1"]
    params: list[Any] = []

    if employer:
        conditions.append("d.employer_name_raw ILIKE %s")
        params.append(f"%{employer}%")
    if union:
        conditions.append("d.union_name_raw ILIKE %s")
        params.append(f"%{union}%")

    # If category filter, only count documents that have provisions in that category
    cat_join = ""
    if category:
        cat_join = "JOIN cba_provisions cp_filter ON cp_filter.cba_id = d.cba_id AND cp_filter.category = %s"
        params.append(category)

    where = " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Count matching documents
            cur.execute(
                f"SELECT COUNT(DISTINCT d.cba_id) AS cnt FROM cba_documents d {cat_join} WHERE {where}",
                params,
            )
            total = int(cur.fetchone()["cnt"])

            # Fetch documents with provision counts
            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                  d.cba_id,
                  d.employer_id,
                  d.f_num,
                  d.employer_name_raw,
                  d.union_name_raw,
                  d.local_number,
                  d.source_name,
                  d.file_format,
                  d.is_scanned,
                  d.page_count,
                  d.effective_date,
                  d.expiration_date,
                  d.is_current,
                  d.structure_quality,
                  d.extraction_status,
                  d.created_at,
                  COALESCE(prov.provision_count, 0) AS provision_count,
                  prov.categories,
                  COALESCE(art.article_count, 0) AS article_count
                FROM cba_documents d
                {cat_join}
                LEFT JOIN LATERAL (
                  SELECT
                    COUNT(*) AS provision_count,
                    ARRAY_AGG(DISTINCT p.category ORDER BY p.category) AS categories
                  FROM cba_provisions p
                  WHERE p.cba_id = d.cba_id
                ) prov ON TRUE
                LEFT JOIN LATERAL (
                  SELECT COUNT(*) AS article_count
                  FROM cba_sections s
                  WHERE s.cba_id = d.cba_id AND s.detection_method = 'article_heading'
                ) art ON TRUE
                WHERE {where}
                GROUP BY d.cba_id, prov.provision_count, prov.categories, art.article_count
                ORDER BY {sort_col} {order_dir} NULLS LAST, d.cba_id
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()

            # Stats: total contracts, total provisions, category breakdown
            cur.execute("SELECT COUNT(*) AS cnt FROM cba_documents")
            total_contracts = int(cur.fetchone()["cnt"])

            cur.execute("SELECT COUNT(*) AS cnt FROM cba_provisions")
            total_provisions = int(cur.fetchone()["cnt"])

            cur.execute(
                """
                SELECT category, COUNT(*) AS cnt
                FROM cba_provisions
                GROUP BY category
                ORDER BY cnt DESC, category
                """
            )
            category_breakdown = cur.fetchall()

    pages = int(math.ceil(total / limit)) if total else 0
    return {
        "total": total,
        "page": page,
        "pages": pages,
        "stats": {
            "total_contracts": total_contracts,
            "total_provisions": total_provisions,
            "category_breakdown": category_breakdown,
        },
        "results": rows,
    }


@router.get("/api/cba/categories")
def list_cba_categories():
    """List all categories with provision counts."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  c.category_id,
                  c.category_name,
                  c.display_name,
                  c.subcategories,
                  c.sort_order,
                  c.description,
                  COALESCE(p.provision_count, 0) AS provision_count,
                  COALESCE(p.document_count, 0) AS document_count
                FROM cba_categories c
                LEFT JOIN (
                  SELECT
                    category,
                    COUNT(*) AS provision_count,
                    COUNT(DISTINCT cba_id) AS document_count
                  FROM cba_provisions
                  GROUP BY category
                ) p ON p.category = c.category_name
                ORDER BY c.sort_order, c.category_name
                """
            )
            return {"results": cur.fetchall()}


@router.get("/api/cba/compare")
def compare_cba_provisions(
    cba_ids: str = Query(..., description="Comma-separated CBA IDs, e.g. '21,22,26'"),
):
    """Compare provisions across multiple contracts, grouped by category and provision_class."""
    try:
        id_list = [int(x.strip()) for x in cba_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="cba_ids must be comma-separated integers")
    if not id_list:
        raise HTTPException(status_code=400, detail="At least one cba_id is required")
    if len(id_list) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 contracts can be compared at once")

    with get_db() as conn:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(id_list))
            cur.execute(
                f"""
                SELECT
                  cba_id, employer_id, employer_name_raw, union_name_raw,
                  local_number, source_name, effective_date, expiration_date,
                  page_count, is_current
                FROM cba_documents
                WHERE cba_id IN ({placeholders})
                ORDER BY cba_id
                """,
                id_list,
            )
            documents = cur.fetchall()

            found_ids = {d["cba_id"] for d in documents}
            missing = [i for i in id_list if i not in found_ids]
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail=f"CBA documents not found: {missing}",
                )

            # Fetch provisions with optional section context and extracted values
            ev_col = ", p.extracted_values" if _check_extracted_values() else ""
            has_section_id = _check_section_cols()
            if has_section_id:
                section_join = (
                    "LEFT JOIN cba_sections s ON p.section_id = s.section_id "
                    "LEFT JOIN cba_sections ps ON s.parent_section_id = ps.section_id"
                )
                section_select = (
                    ", s.section_num, s.section_title"
                    ", ps.section_num AS parent_section_num"
                    ", ps.section_title AS parent_section_title"
                )
            else:
                section_join = ""
                section_select = ""

            cur.execute(
                f"""
                SELECT
                  p.provision_id, p.cba_id, p.category, p.provision_class,
                  p.provision_text, p.summary, p.page_start, p.page_end,
                  p.modal_verb, p.legal_weight, p.confidence_score,
                  p.context_before, p.context_after
                  {ev_col}
                  {section_select}
                FROM cba_provisions p
                {section_join}
                WHERE p.cba_id IN ({placeholders})
                ORDER BY p.category, p.provision_class, p.cba_id,
                         p.page_start NULLS LAST, p.provision_id
                """,
                id_list,
            )
            provisions = cur.fetchall()

    # Build section breadcrumb for each provision
    for prov in provisions:
        parts = []
        if prov.get("parent_section_num"):
            parts.append(f"{prov['parent_section_num']} {prov['parent_section_title'] or ''}".strip())
        if prov.get("section_num"):
            parts.append(f"{prov['section_num']} {prov['section_title'] or ''}".strip())
        prov["section_breadcrumb"] = " > ".join(parts) if parts else None

    # Group by category -> provision_class
    comparison: dict[str, dict[str, dict]] = {}
    for prov in provisions:
        cat = prov["category"] or "uncategorized"
        pclass = prov["provision_class"] or "unknown"

        if cat not in comparison:
            comparison[cat] = {}
        if pclass not in comparison[cat]:
            comparison[cat][pclass] = {"provisions": [], "missing_from": []}

        comparison[cat][pclass]["provisions"].append(prov)

    # Compute missing_from for each provision_class
    for cat_data in comparison.values():
        for pclass_data in cat_data.values():
            present_ids = {p["cba_id"] for p in pclass_data["provisions"]}
            pclass_data["missing_from"] = [cid for cid in id_list if cid not in present_ids]

    # Gap analysis per contract
    all_categories = set()
    cat_by_contract: dict[int, set] = {cid: set() for cid in id_list}
    for prov in provisions:
        cat = prov["category"] or "uncategorized"
        all_categories.add(cat)
        cat_by_contract[prov["cba_id"]].add(cat)

    gap_analysis = {}
    for cid in id_list:
        covered = sorted(cat_by_contract[cid])
        missing_cats = sorted(all_categories - cat_by_contract[cid])
        gap_analysis[str(cid)] = {"covered": covered, "missing": missing_cats}

    return {
        "documents": documents,
        "comparison": comparison,
        "gap_analysis": gap_analysis,
    }


@router.get("/api/cba/provisions/compare-values")
def compare_provision_values(
    provision_class: str = Query(..., description="Provision class to compare"),
    cba_ids: str = Query(..., description="Comma-separated CBA IDs"),
):
    """Compare extracted values for a specific provision class across contracts."""
    try:
        id_list = [int(x.strip()) for x in cba_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="cba_ids must be comma-separated integers")

    with get_db() as conn:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(id_list))
            ev_col = ", p.extracted_values" if _check_extracted_values() else ""
            has_sec = _check_section_cols()
            sec_join = "LEFT JOIN cba_sections s ON p.section_id = s.section_id" if has_sec else ""
            sec_cols = ", s.section_num, s.section_title" if has_sec else ""
            cur.execute(
                f"""
                SELECT
                  p.provision_id, p.cba_id, p.provision_class,
                  p.provision_text, p.confidence_score,
                  d.employer_name_raw, d.union_name_raw
                  {ev_col}
                  {sec_cols}
                FROM cba_provisions p
                JOIN cba_documents d ON p.cba_id = d.cba_id
                {sec_join}
                WHERE p.provision_class = %s
                  AND p.cba_id IN ({placeholders})
                ORDER BY p.cba_id, p.page_start NULLS LAST
                """,
                [provision_class] + id_list,
            )
            results = cur.fetchall()

    return {"provision_class": provision_class, "results": results}


@router.get("/api/cba/documents/{cba_id:int}")
def get_cba_document_detail(
    cba_id: int,
    include_provisions: bool = Query(default=True),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """Return one CBA document and its extracted provisions."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  cba_id,
                  employer_id,
                  f_num,
                  employer_name_raw,
                  union_name_raw,
                  local_number,
                  source_name,
                  source_url,
                  file_path,
                  file_format,
                  is_scanned,
                  page_count,
                  effective_date,
                  expiration_date,
                  is_current,
                  structure_quality,
                  ocr_status,
                  extraction_status,
                  created_at,
                  updated_at
                FROM cba_documents
                WHERE cba_id = %s
                """,
                [cba_id],
            )
            doc = cur.fetchone()
            if not doc:
                raise HTTPException(status_code=404, detail="CBA document not found")

            cur.execute(
                """
                SELECT category, provision_class, COUNT(*) AS cnt
                FROM cba_provisions
                WHERE cba_id = %s
                GROUP BY category, provision_class
                ORDER BY cnt DESC, category, provision_class
                """,
                [cba_id],
            )
            class_counts = cur.fetchall()

            cur.execute(
                """
                SELECT
                  COUNT(*) AS provision_count,
                  MIN(page_start) AS min_page_start,
                  MAX(page_end) AS max_page_end,
                  MIN(char_start) AS min_char_start,
                  MAX(char_end) AS max_char_end
                FROM cba_provisions
                WHERE cba_id = %s
                """,
                [cba_id],
            )
            summary = cur.fetchone()

            provisions = []
            if include_provisions:
                cur.execute(
                    """
                    SELECT
                      provision_id,
                      category,
                      provision_class,
                      provision_text,
                      summary,
                      page_start,
                      page_end,
                      char_start,
                      char_end,
                      modal_verb,
                      legal_weight,
                      confidence_score,
                      model_version,
                      is_human_verified,
                      created_at,
                      context_before,
                      context_after
                    FROM cba_provisions
                    WHERE cba_id = %s
                    ORDER BY page_start NULLS LAST, provision_id
                    LIMIT %s
                    """,
                    [cba_id, limit],
                )
                provisions = cur.fetchall()

            return {
                "document": doc,
                "summary": summary,
                "class_counts": class_counts,
                "provisions": provisions,
            }


@router.get("/api/cba/sections/search")
def search_cba_sections(
    q: str | None = None,
    category: str | None = None,
    employer_name: str | None = None,
    union_name: str | None = None,
    cba_id: int | None = None,
    has_wage_table: bool | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=200),
):
    """Search contract sections with full text and attributes."""
    conditions = ["1=1"]
    params: list[Any] = []

    if q:
        conditions.append("(to_tsvector('english', COALESCE(s.section_title, '') || ' ' || COALESCE(s.section_text, '')) @@ plainto_tsquery('english', %s))")
        params.append(q)
    if category:
        conditions.append("s.attributes->'categories_detected' ? %s")
        params.append(category)
    if employer_name:
        conditions.append("d.employer_name_raw ILIKE %s")
        params.append(f"%{employer_name}%")
    if union_name:
        conditions.append("d.union_name_raw ILIKE %s")
        params.append(f"%{union_name}%")
    if cba_id is not None:
        conditions.append("s.cba_id = %s")
        params.append(cba_id)
    if has_wage_table is not None:
        conditions.append("(s.attributes->>'has_wage_table')::boolean = %s")
        params.append(has_wage_table)

    where = " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM cba_sections s
                JOIN cba_documents d ON s.cba_id = d.cba_id
                WHERE {where}
                """,
                params,
            )
            total = int(cur.fetchone()["cnt"])

            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                    s.section_id,
                    s.cba_id,
                    s.section_num,
                    s.section_title,
                    s.section_level,
                    s.sort_order,
                    s.page_start,
                    s.page_end,
                    s.detection_method,
                    s.attributes,
                    s.has_page_images,
                    LENGTH(s.section_text) AS text_length,
                    LEFT(s.section_text, 500) AS text_preview,
                    d.employer_name_raw,
                    d.union_name_raw,
                    d.page_count
                FROM cba_sections s
                JOIN cba_documents d ON s.cba_id = d.cba_id
                WHERE {where}
                ORDER BY d.employer_name_raw, s.sort_order
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()

    pages = int(math.ceil(total / limit)) if total else 0
    return {"total": total, "page": page, "pages": pages, "results": rows}


@router.get("/api/cba/articles/search")
def search_cba_articles(
    q: str | None = None,
    category: str | None = None,
    category_group: str | None = None,
    employer_name: str | None = None,
    union_name: str | None = None,
    sort_by: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
):
    """Search article text across all contracts."""
    conditions = ["s.detection_method = 'article_heading'"]
    params: list[Any] = []

    if q:
        conditions.append(
            "to_tsvector('english', COALESCE(s.section_text, '')) @@ plainto_tsquery('english', %s)"
        )
        params.append(q)
    if category:
        conditions.append("s.attributes->>'category' = %s")
        params.append(category)
    if category_group and category_group in CATEGORY_GROUPS:
        cats = CATEGORY_GROUPS[category_group]
        placeholders = ",".join(["%s"] * len(cats))
        conditions.append(f"s.attributes->>'category' IN ({placeholders})")
        params.extend(cats)
    if employer_name:
        conditions.append("d.employer_name_raw ILIKE %s")
        params.append(f"%{employer_name}%")
    if union_name:
        conditions.append("d.union_name_raw ILIKE %s")
        params.append(f"%{union_name}%")

    where = " AND ".join(conditions)

    # Build ORDER BY -- relevance first when searching, otherwise sort_order
    order_params: list[Any] = []
    effective_sort = sort_by
    if q and not sort_by:
        effective_sort = "relevance"

    if effective_sort == "relevance" and q:
        order_clause = "ts_rank(to_tsvector('english', COALESCE(s.section_text, '')), plainto_tsquery('english', %s)) DESC"
        order_params.append(q)
    elif effective_sort == "category":
        order_clause = "s.attributes->>'category', d.employer_name_raw, s.sort_order"
    elif effective_sort == "employer":
        order_clause = "d.employer_name_raw, s.sort_order"
    else:
        order_clause = "d.employer_name_raw, s.sort_order"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM cba_sections s
                JOIN cba_documents d ON s.cba_id = d.cba_id
                WHERE {where}
                """,
                params,
            )
            total = int(cur.fetchone()["cnt"])

            offset_val = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                    s.section_id,
                    s.cba_id,
                    s.section_num AS number,
                    s.section_title AS title,
                    s.attributes->>'category' AS category,
                    s.section_text AS text,
                    LENGTH(s.section_text) AS text_length,
                    COALESCE((s.attributes->>'word_count')::int, 0) AS word_count,
                    s.page_start,
                    s.page_end,
                    d.employer_name_raw AS employer_name,
                    d.union_name_raw AS union_name,
                    d.effective_date,
                    d.expiration_date
                FROM cba_sections s
                JOIN cba_documents d ON s.cba_id = d.cba_id
                WHERE {where}
                ORDER BY {order_clause}, s.section_id
                LIMIT %s OFFSET %s
                """,
                params + order_params + [limit, offset_val],
            )
            rows = cur.fetchall()

    # Enrich with category_group
    for row in rows:
        cat = row.get("category")
        row["category_group"] = CATEGORY_TO_GROUP.get(cat) if cat else None

    pages_count = int(math.ceil(total / limit)) if total else 0
    return {"total": total, "page": page, "pages": pages_count, "results": rows}


# ---------------------------------------------------------------------------
# Semantic search (pgvector + Gemini embeddings)
# ---------------------------------------------------------------------------

_gemini_client = None
_GEMINI_EMBED_MODEL = "gemini-embedding-001"
_GEMINI_EMBED_DIMS = 3072


def _get_gemini_embed_client():
    """Lazy-init Gemini client. Raises HTTPException if API key not set."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    import os
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        # Try loading from .env at project root
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "GOOGLE_API_KEY":
                        api_key = v.strip()
                        os.environ["GOOGLE_API_KEY"] = api_key
                        break
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Semantic search unavailable: GOOGLE_API_KEY not configured",
        )
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Semantic search unavailable: {exc}",
        ) from exc
    return _gemini_client


def _embed_query(query: str) -> list[float]:
    """Embed a user query via Gemini (RETRIEVAL_QUERY task type)."""
    from google.genai import types as genai_types
    client = _get_gemini_embed_client()
    try:
        result = client.models.embed_content(
            model=_GEMINI_EMBED_MODEL,
            contents=[query],
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Query embedding failed: {exc}",
        ) from exc
    return list(result.embeddings[0].values)


def _to_halfvec_literal(values: list[float]) -> str:
    """Format a Python list as a pgvector halfvec literal string."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


@router.get("/api/cba/semantic-search")
def semantic_search_cba(
    q: str = Query(..., min_length=2, description="Natural-language query"),
    types: str = Query(
        default="article,provision",
        description="Comma-separated object types to search: article, provision, or both",
    ),
    top_k: int = Query(default=25, ge=1, le=100),
    min_similarity: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity to include (0.0 = no floor)",
    ),
    employer_name: str | None = None,
    union_name: str | None = None,
    category: str | None = None,
    category_group: str | None = None,
    cba_id: int | None = None,
):
    """Semantic search across CBA articles and provisions via pgvector.

    Returns top-K matches ordered by cosine similarity (1 - distance).
    Similarity = 1.0 is identical, 0.0 is orthogonal, negative is opposed.
    """
    requested_types = {t.strip() for t in types.split(",") if t.strip()}
    if not requested_types or not requested_types.issubset({"article", "provision"}):
        raise HTTPException(
            status_code=400,
            detail="types must be a comma list containing 'article' and/or 'provision'",
        )

    # 1) Embed the query string
    import time as _time
    t0 = _time.time()
    query_vec = _embed_query(q)
    embed_ms = int((t0 and (_time.time() - t0) * 1000) or 0)
    if len(query_vec) != _GEMINI_EMBED_DIMS:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected query embedding dimension: {len(query_vec)}",
        )
    vec_literal = _to_halfvec_literal(query_vec)

    # 2) Build filter clauses (applied per-subquery)
    max_distance = 1.0 - min_similarity  # cosine distance upper bound

    # Shared filter for BOTH sides of the UNION (joined via cba_documents)
    shared_filters: list[str] = []
    shared_params: list[Any] = []
    if employer_name:
        shared_filters.append("d.employer_name_raw ILIKE %s")
        shared_params.append(f"%{employer_name}%")
    if union_name:
        shared_filters.append("d.union_name_raw ILIKE %s")
        shared_params.append(f"%{union_name}%")
    if cba_id is not None:
        shared_filters.append("d.cba_id = %s")
        shared_params.append(cba_id)

    # Category filter — articles use attributes->>'category', provisions use p.category
    article_cat_filters: list[str] = []
    article_cat_params: list[Any] = []
    provision_cat_filters: list[str] = []
    provision_cat_params: list[Any] = []

    if category:
        article_cat_filters.append("s.attributes->>'category' = %s")
        article_cat_params.append(category)
        provision_cat_filters.append("p.category = %s")
        provision_cat_params.append(category)
    if category_group and category_group in CATEGORY_GROUPS:
        cats = CATEGORY_GROUPS[category_group]
        a_placeholders = ",".join(["%s"] * len(cats))
        p_placeholders = ",".join(["%s"] * len(cats))
        article_cat_filters.append(f"s.attributes->>'category' IN ({a_placeholders})")
        article_cat_params.extend(cats)
        provision_cat_filters.append(f"p.category IN ({p_placeholders})")
        provision_cat_params.extend(cats)

    # 3) Build per-type subqueries only for requested types
    subqueries: list[str] = []
    subquery_params: list[Any] = []

    if "article" in requested_types:
        article_filters = [
            "e.object_type = 'article'",
            "e.embedding_halfvec IS NOT NULL",
            "s.detection_method = 'article_heading'",
            "(e.embedding_halfvec <=> %s::halfvec) <= %s",
            *shared_filters,
            *article_cat_filters,
        ]
        article_where = " AND ".join(article_filters)
        subqueries.append(f"""
            SELECT
                'article'::text AS object_type,
                e.section_id    AS object_id,
                s.section_title AS title,
                s.section_text  AS text,
                s.cba_id,
                s.attributes->>'category' AS category,
                s.page_start,
                s.page_end,
                d.employer_name_raw AS employer_name,
                d.union_name_raw    AS union_name,
                d.effective_date,
                d.expiration_date,
                (e.embedding_halfvec <=> %s::halfvec)::real AS distance
            FROM cba_embeddings e
            JOIN cba_sections  s ON s.section_id = e.section_id
            JOIN cba_documents d ON d.cba_id = s.cba_id
            WHERE {article_where}
            ORDER BY e.embedding_halfvec <=> %s::halfvec
            LIMIT %s
        """)
        # Params: SELECT distance, WHERE distance filter (vec + max_distance),
        #         shared, article_cat, ORDER BY distance, LIMIT
        subquery_params.extend([
            vec_literal,            # SELECT distance
            vec_literal,            # WHERE distance <= max
            max_distance,
            *shared_params,
            *article_cat_params,
            vec_literal,            # ORDER BY distance
            top_k,
        ])

    if "provision" in requested_types:
        provision_filters = [
            "e.object_type = 'provision'",
            "e.embedding_halfvec IS NOT NULL",
            "(e.embedding_halfvec <=> %s::halfvec) <= %s",
            *shared_filters,
            *provision_cat_filters,
        ]
        provision_where = " AND ".join(provision_filters)
        subqueries.append(f"""
            SELECT
                'provision'::text AS object_type,
                e.provision_id    AS object_id,
                (COALESCE(NULLIF(p.article_reference, ''), '')
                 || CASE WHEN p.provision_class IS NOT NULL AND p.provision_class <> ''
                         THEN ' / ' || p.provision_class ELSE '' END) AS title,
                p.provision_text AS text,
                p.cba_id,
                p.category,
                p.page_start,
                p.page_end,
                d.employer_name_raw AS employer_name,
                d.union_name_raw    AS union_name,
                d.effective_date,
                d.expiration_date,
                (e.embedding_halfvec <=> %s::halfvec)::real AS distance
            FROM cba_embeddings e
            JOIN cba_provisions p ON p.provision_id = e.provision_id
            JOIN cba_documents  d ON d.cba_id = p.cba_id
            WHERE {provision_where}
            ORDER BY e.embedding_halfvec <=> %s::halfvec
            LIMIT %s
        """)
        subquery_params.extend([
            vec_literal,
            vec_literal,
            max_distance,
            *shared_params,
            *provision_cat_params,
            vec_literal,
            top_k,
        ])

    full_query = " UNION ALL ".join(f"({sq})" for sq in subqueries)
    full_query += "\nORDER BY distance ASC\nLIMIT %s"
    subquery_params.append(top_k)

    # 4) Execute
    t1 = _time.time()
    with get_db() as conn:
        with conn.cursor() as cur:
            # Increase HNSW ef_search for better recall on this session
            cur.execute("SET LOCAL hnsw.ef_search = 100")
            cur.execute(full_query, subquery_params)
            rows = cur.fetchall()
    search_ms = int((_time.time() - t1) * 1000)

    # 5) Post-process: similarity, preview text, category_group
    PREVIEW_CHARS = 500
    results = []
    for row in rows:
        text = row.get("text") or ""
        distance = float(row.get("distance") or 0.0)
        similarity = max(0.0, min(1.0, 1.0 - distance))
        cat = row.get("category")
        results.append({
            "object_type": row.get("object_type"),
            "object_id": row.get("object_id"),
            "title": row.get("title"),
            "preview": text[:PREVIEW_CHARS] + ("..." if len(text) > PREVIEW_CHARS else ""),
            "text_length": len(text),
            "cba_id": row.get("cba_id"),
            "category": cat,
            "category_group": CATEGORY_TO_GROUP.get(cat) if cat else None,
            "page_start": row.get("page_start"),
            "page_end": row.get("page_end"),
            "employer_name": row.get("employer_name"),
            "union_name": row.get("union_name"),
            "effective_date": row.get("effective_date"),
            "expiration_date": row.get("expiration_date"),
            "similarity": round(similarity, 4),
            "distance": round(distance, 4),
        })

    return {
        "query": q,
        "types": sorted(requested_types),
        "top_k": top_k,
        "min_similarity": min_similarity,
        "embedding_time_ms": embed_ms,
        "search_time_ms": search_ms,
        "result_count": len(results),
        "results": results,
    }


@router.get("/api/cba/category-groups")
def get_category_groups():
    """Return category grouping for search/filter UI."""
    groups = [
        {
            "group_name": name,
            "display_name": name,
            "categories": cats,
            "category_count": len(cats),
        }
        for name, cats in CATEGORY_GROUPS.items()
    ]
    return {"groups": groups}


@router.get("/api/cba/sections/{section_id:int}")
def get_cba_section_detail(section_id: int):
    """Return full section text and linked provisions."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    s.section_id,
                    s.cba_id,
                    s.section_num,
                    s.section_title,
                    s.section_level,
                    s.section_text,
                    s.page_start,
                    s.page_end,
                    s.char_start,
                    s.char_end,
                    s.detection_method,
                    s.attributes,
                    s.has_page_images,
                    s.page_image_paths,
                    d.employer_name_raw,
                    d.union_name_raw,
                    d.page_count
                FROM cba_sections s
                JOIN cba_documents d ON s.cba_id = d.cba_id
                WHERE s.section_id = %s
                """,
                [section_id],
            )
            section = cur.fetchone()
            if not section:
                raise HTTPException(status_code=404, detail="Section not found")

            # Fetch linked provisions
            provision_ids = (section.get("attributes") or {}).get("linked_provision_ids", [])
            provisions = []
            if provision_ids:
                placeholders = ",".join(["%s"] * len(provision_ids))
                cur.execute(
                    f"""
                    SELECT
                        provision_id, category, provision_class,
                        provision_text, modal_verb, confidence_score,
                        page_start, article_reference
                    FROM cba_provisions
                    WHERE provision_id IN ({placeholders})
                    ORDER BY page_start NULLS LAST
                    """,
                    provision_ids,
                )
                provisions = cur.fetchall()

            return {"section": section, "provisions": provisions}


@router.get("/api/cba/documents/{cba_id:int}/articles")
def get_cba_articles(cba_id: int):
    """Return contract metadata and all articles with full text.

    Simple article-based view: parties, dates, and each article's heading + body.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cba_id, employer_id, employer_name_raw, union_name_raw,
                       local_number, effective_date, expiration_date,
                       page_count, source_name
                FROM cba_documents WHERE cba_id = %s
                """,
                [cba_id],
            )
            doc = cur.fetchone()
            if not doc:
                raise HTTPException(status_code=404, detail="Contract not found")

            cur.execute(
                """
                SELECT section_id, section_num, section_title, section_level,
                       sort_order, section_text, page_start, page_end,
                       attributes
                FROM cba_sections
                WHERE cba_id = %s
                ORDER BY sort_order, section_num
                """,
                [cba_id],
            )
            articles = cur.fetchall()

            def _clean_text(raw: str) -> str:
                """Clean PDF layout text into readable paragraphs.

                Preserves paragraph breaks at blank lines and numbered sections.
                """
                if not raw:
                    return ""
                import re
                lines = [line.strip() for line in raw.split("\n")]
                new_section_re = re.compile(
                    r"^(?:"
                    r"\d+[\.\)]\s"           # 1. or 2)
                    r"|\([a-z]\)\s"          # (a) (b)
                    r"|\([ivxlc]+\)\s"       # (i) (ii)
                    r"|[A-Z]\.\s"            # A. B.
                    r"|Section\s"            # Section 3
                    r"|SECTION\s"            # SECTION 3
                    r")",
                    re.IGNORECASE,
                )
                paragraphs = []
                current = []
                for line in lines:
                    if not line:
                        if current:
                            paragraphs.append(" ".join(current))
                            current = []
                        continue
                    if new_section_re.match(line) and current:
                        paragraphs.append(" ".join(current))
                        current = []
                    current.append(line)
                if current:
                    paragraphs.append(" ".join(current))
                return "\n\n".join(paragraphs).strip()

            return {
                "document": doc,
                "articles": [
                    {
                        "section_id": a["section_id"],
                        "number": a["section_num"],
                        "title": a["section_title"],
                        "sort_order": a["sort_order"],
                        "text": _clean_text(a["section_text"]),
                        "page_start": a["page_start"],
                        "page_end": a["page_end"],
                        "category": (a["attributes"] or {}).get("category", "other"),
                        "word_count": (a["attributes"] or {}).get("word_count", 0),
                        "subfields": (a["attributes"] or {}).get("subfields", {}),
                    }
                    for a in articles
                ],
            }


# ---------------------------------------------------------------------------
# Rule Review & Feedback Endpoints
# ---------------------------------------------------------------------------

_RULES_DIR = Path(__file__).resolve().parents[2] / "config" / "cba_rules"


@router.get("/api/cba/rules")
def list_cba_rules():
    """List all rule categories with their patterns and per-rule match/review stats."""
    # Load rule files from disk
    rules = []
    if _RULES_DIR.is_dir():
        for fp in sorted(_RULES_DIR.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                rules.append({
                    "file": fp.name,
                    "category": data.get("category", fp.stem),
                    "provision_classes": data.get("provision_classes", []),
                    "text_patterns": data.get("text_patterns", []),
                    "heading_signals": data.get("heading_signals", []),
                    "negative_patterns": data.get("negative_patterns", []),
                })
            except Exception:
                continue

    # Per-rule match counts + review stats from DB
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.rule_name,
                    p.category,
                    COUNT(*) AS match_count,
                    AVG(p.confidence_score) AS avg_confidence,
                    MIN(p.confidence_score) AS min_confidence,
                    MAX(p.confidence_score) AS max_confidence,
                    COUNT(*) FILTER (WHERE p.is_human_verified) AS verified_count
                FROM cba_provisions p
                WHERE p.rule_name IS NOT NULL
                GROUP BY p.rule_name, p.category
                ORDER BY p.category, match_count DESC
            """)
            rule_stats = {}
            for row in cur.fetchall():
                rule_stats[row["rule_name"]] = {
                    "match_count": row["match_count"],
                    "avg_confidence": float(row["avg_confidence"]) if row["avg_confidence"] else None,
                    "min_confidence": float(row["min_confidence"]) if row["min_confidence"] else None,
                    "max_confidence": float(row["max_confidence"]) if row["max_confidence"] else None,
                    "verified_count": row["verified_count"],
                    "category": row["category"],
                }

            # Review stats per rule_name (via provision join)
            cur.execute("""
                SELECT
                    p.rule_name,
                    r.review_action,
                    COUNT(*) AS cnt
                FROM cba_reviews r
                JOIN cba_provisions p ON r.provision_id = p.provision_id
                WHERE p.rule_name IS NOT NULL
                GROUP BY p.rule_name, r.review_action
            """)
            review_stats: dict[str, dict[str, int]] = {}
            for row in cur.fetchall():
                rn = row["rule_name"]
                if rn not in review_stats:
                    review_stats[rn] = {}
                review_stats[rn][row["review_action"]] = row["cnt"]

    return {
        "rules": rules,
        "rule_stats": rule_stats,
        "review_stats": review_stats,
    }


@router.get("/api/cba/review/queue")
def get_review_queue(
    category: str | None = None,
    rule_name: str | None = None,
    review_status: str = Query(default="unreviewed", pattern="^(unreviewed|reviewed|all)$"),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    max_confidence: float | None = Query(default=None, ge=0, le=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="confidence_score", pattern="^(confidence_score|rule_name|category|page_start)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    """Get provisions for review, sorted by confidence (lowest first by default)."""
    conditions = ["1=1"]
    params: list[Any] = []

    if category:
        conditions.append("p.category = %s")
        params.append(category)
    if rule_name:
        conditions.append("p.rule_name = %s")
        params.append(rule_name)
    if min_confidence is not None:
        conditions.append("p.confidence_score >= %s")
        params.append(min_confidence)
    if max_confidence is not None:
        conditions.append("p.confidence_score <= %s")
        params.append(max_confidence)

    if review_status == "unreviewed":
        conditions.append("r.review_id IS NULL")
    elif review_status == "reviewed":
        conditions.append("r.review_id IS NOT NULL")

    where = " AND ".join(conditions)
    sort_map = {
        "confidence_score": "p.confidence_score",
        "rule_name": "p.rule_name",
        "category": "p.category",
        "page_start": "p.page_start",
    }
    sort_col = safe_sort_col(sort, sort_map, "confidence_score")
    order_dir = safe_order_dir(order)

    review_join = "LEFT JOIN cba_reviews r ON r.provision_id = p.provision_id"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(DISTINCT p.provision_id) AS cnt FROM cba_provisions p {review_join} WHERE {where}",
                params,
            )
            total = int(cur.fetchone()["cnt"])

            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                    p.provision_id,
                    p.cba_id,
                    p.category,
                    p.provision_class,
                    p.provision_text,
                    p.summary,
                    p.page_start,
                    p.page_end,
                    p.modal_verb,
                    p.legal_weight,
                    p.confidence_score,
                    p.rule_name,
                    p.article_reference,
                    p.is_human_verified,
                    p.context_before,
                    p.context_after,
                    d.employer_name_raw,
                    d.union_name_raw,
                    r.review_id,
                    r.review_action,
                    r.corrected_category,
                    r.corrected_class,
                    r.notes AS review_notes
                FROM cba_provisions p
                JOIN cba_documents d ON d.cba_id = p.cba_id
                {review_join}
                WHERE {where}
                ORDER BY {sort_col} {order_dir} NULLS LAST, p.provision_id
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()

    pages = int(math.ceil(total / limit)) if total else 0
    return {"total": total, "page": page, "pages": pages, "results": rows}


class ReviewPayload(BaseModel):
    review_action: str = Field(..., pattern="^(approve|reject|correct)$")
    corrected_category: str | None = None
    corrected_class: str | None = None
    notes: str | None = None


@router.post("/api/cba/provisions/{provision_id}/review")
def submit_provision_review(provision_id: int, payload: ReviewPayload):
    """Submit a review (accept/reject/correct) for a provision."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Verify provision exists
            cur.execute(
                "SELECT provision_id, category, provision_class FROM cba_provisions WHERE provision_id = %s",
                [provision_id],
            )
            prov = cur.fetchone()
            if not prov:
                raise HTTPException(status_code=404, detail="Provision not found")

            # Upsert review (one review per provision)
            cur.execute(
                """
                INSERT INTO cba_reviews (provision_id, original_category, original_class,
                    corrected_category, corrected_class, review_action, notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (provision_id) DO UPDATE SET
                    corrected_category = EXCLUDED.corrected_category,
                    corrected_class = EXCLUDED.corrected_class,
                    review_action = EXCLUDED.review_action,
                    notes = EXCLUDED.notes,
                    created_at = NOW()
                RETURNING review_id
                """,
                [
                    provision_id,
                    prov["category"],
                    prov["provision_class"],
                    payload.corrected_category,
                    payload.corrected_class,
                    payload.review_action,
                    payload.notes,
                ],
            )
            review_id = cur.fetchone()["review_id"]

            # Mark provision as human-verified
            cur.execute(
                "UPDATE cba_provisions SET is_human_verified = TRUE WHERE provision_id = %s",
                [provision_id],
            )
            conn.commit()

    return {"review_id": review_id, "provision_id": provision_id, "status": "saved"}


@router.get("/api/cba/review/stats")
def get_review_stats():
    """Summary statistics for the review process."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM cba_provisions")
            total_provisions = int(cur.fetchone()["cnt"])

            cur.execute("SELECT COUNT(*) AS cnt FROM cba_provisions WHERE is_human_verified")
            verified = int(cur.fetchone()["cnt"])

            cur.execute("""
                SELECT review_action, COUNT(*) AS cnt
                FROM cba_reviews
                GROUP BY review_action
                ORDER BY cnt DESC
            """)
            action_counts = {r["review_action"]: r["cnt"] for r in cur.fetchall()}

            cur.execute("""
                SELECT
                    p.category,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE p.is_human_verified) AS reviewed,
                    AVG(p.confidence_score) AS avg_confidence
                FROM cba_provisions p
                GROUP BY p.category
                ORDER BY p.category
            """)
            by_category = cur.fetchall()

            cur.execute("""
                SELECT
                    p.rule_name,
                    p.category,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE p.is_human_verified) AS reviewed,
                    COUNT(r.review_id) FILTER (WHERE r.review_action = 'approve') AS accepted,
                    COUNT(r.review_id) FILTER (WHERE r.review_action = 'reject') AS rejected,
                    COUNT(r.review_id) FILTER (WHERE r.review_action = 'correct') AS corrected,
                    AVG(p.confidence_score) AS avg_confidence
                FROM cba_provisions p
                LEFT JOIN cba_reviews r ON r.provision_id = p.provision_id
                WHERE p.rule_name IS NOT NULL
                GROUP BY p.rule_name, p.category
                ORDER BY total DESC
            """)
            by_rule = cur.fetchall()

    return {
        "total_provisions": total_provisions,
        "verified": verified,
        "unreviewed": total_provisions - verified,
        "action_counts": action_counts,
        "by_category": by_category,
        "by_rule": by_rule,
    }
