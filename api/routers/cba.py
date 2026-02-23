from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Query
from fastapi import HTTPException

from ..database import get_db
from ..helpers import safe_order_dir, safe_sort_col

router = APIRouter()


def _base_query_filters(
    *,
    q: str | None,
    provision_class: str | None,
    category: str | None,
    union_name: str | None,
    employer_name: str | None,
    cba_id: int | None,
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

    return " AND ".join(conditions), params


@router.get("/api/cba/provisions/search")
def search_cba_provisions(
    q: str | None = None,
    provision_class: str | None = None,
    category: str | None = None,
    union_name: str | None = None,
    employer_name: str | None = None,
    cba_id: int | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=200),
    sort: str = Query(default="page_start", pattern="^(page_start|employer_name|union_name|provision_class)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    sort_map = {
        "page_start": "v.page_start",
        "employer_name": "v.employer_name",
        "union_name": "v.union_name",
        "provision_class": "v.provision_class",
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
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM v_cba_provision_search v WHERE {where}", params)
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
                  p.model_version
                FROM v_cba_provision_search v
                JOIN cba_provisions p ON p.provision_id = v.provision_id
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
                SELECT provision_class, COUNT(*) AS cnt
                FROM cba_provisions
                GROUP BY provision_class
                ORDER BY cnt DESC, provision_class
                """
            )
            return {"results": cur.fetchall()}


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
                      created_at
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
