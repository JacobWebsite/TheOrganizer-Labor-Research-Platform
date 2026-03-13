from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Query
from fastapi import HTTPException

from ..database import get_db
from ..helpers import safe_order_dir, safe_sort_col

router = APIRouter()

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
    union_name: str | None,
    employer_name: str | None,
    cba_id: int | None,
    modal_verb: str | None = None,
    min_confidence: float | None = None,
) -> tuple[str, list[Any]]:
    conditions = ["1=1"]
    params: list[Any] = []

    if q:
        conditions.append("v.provision_text ILIKE %s")
        params.append(f"%{q}%")
    if provision_class:
        conditions.append("v.provision_class = %s")
        params.append(provision_class)
    if category:
        conditions.append("v.category = %s")
        params.append(category)
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
    union_name: str | None = None,
    employer_name: str | None = None,
    cba_id: int | None = None,
    modal_verb: str | None = None,
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=200),
    sort: str = Query(default="page_start", pattern="^(page_start|employer_name|union_name|provision_class|confidence_score)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    sort_map = {
        "page_start": "v.page_start",
        "employer_name": "v.employer_name",
        "union_name": "v.union_name",
        "provision_class": "v.provision_class",
        "confidence_score": "p.confidence_score",
    }
    sort_col = safe_sort_col(sort, sort_map, "page_start")
    order_dir = safe_order_dir(order)

    where, params = _base_query_filters(
        q=q,
        provision_class=provision_class,
        category=category,
        union_name=union_name,
        employer_name=employer_name,
        cba_id=cba_id,
        modal_verb=modal_verb,
        min_confidence=min_confidence,
    )

    base_from = "v_cba_provision_search v JOIN cba_provisions p ON p.provision_id = v.provision_id"

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
                ORDER BY {sort_col} {order_dir} NULLS LAST, v.provision_id
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
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
                  prov.categories
                FROM cba_documents d
                {cat_join}
                LEFT JOIN LATERAL (
                  SELECT
                    COUNT(*) AS provision_count,
                    ARRAY_AGG(DISTINCT p.category ORDER BY p.category) AS categories
                  FROM cba_provisions p
                  WHERE p.cba_id = d.cba_id
                ) prov ON TRUE
                WHERE {where}
                GROUP BY d.cba_id, prov.provision_count, prov.categories
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
        conditions.append("(s.section_title ILIKE %s OR s.section_text ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
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
