"""
Employer endpoints: search, detail, flags, NAICS stats, unified, comparables.
Extracted from labor_api_v6.py.
"""
import re

import psycopg2.errors
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List

from ..database import get_db
from ..dependencies import require_auth
from ..models.schemas import FlagCreate

router = APIRouter()


# ============================================================================
# EMPLOYER SEARCH
# ============================================================================

@router.get("/api/employers/cities")
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


@router.get("/api/employers/search")
def search_employers(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    naics: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    metro: Optional[str] = None,
    sector: Optional[str] = None,
    has_nlrb: Optional[bool] = None,  # DEPRECATED: declared but never used in query
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """DEPRECATED: Superseded by /api/employers/unified-search. Kept for potential external consumers."""
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


@router.get("/api/employers/fuzzy-search")
def fuzzy_search_employers(
    name: str = Query(..., description="Employer name to search (typo-tolerant)"),
    threshold: float = Query(0.3, ge=0.1, le=1.0),
    state: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """DEPRECATED: Superseded by /api/employers/unified-search (has built-in similarity). Kept for potential external consumers."""
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


@router.get("/api/employers/normalized-search")
def normalized_search_employers(
    name: str = Query(..., description="Employer name"),
    threshold: float = Query(0.35, ge=0.1, le=1.0),
    state: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """DEPRECATED: Superseded by /api/employers/unified-search. Kept for potential external consumers."""
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
# DATA SOURCE COVERAGE
# ============================================================================

@router.get("/api/employers/data-coverage")
def get_data_coverage():
    """Aggregate stats: how many employers have 0/1/2/3+ external data sources."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM mv_employer_data_sources")
            total = cur.fetchone()['cnt']

            cur.execute("""
                SELECT source_count, COUNT(*) AS cnt
                FROM mv_employer_data_sources
                GROUP BY source_count
                ORDER BY source_count
            """)
            distribution = cur.fetchall()

            cur.execute("""
                SELECT
                    SUM(has_osha::int) AS osha,
                    SUM(has_nlrb::int) AS nlrb,
                    SUM(has_whd::int) AS whd,
                    SUM(has_990::int) AS n990,
                    SUM(has_sam::int) AS sam,
                    SUM(has_sec::int) AS sec,
                    SUM(has_gleif::int) AS gleif,
                    SUM(has_mergent::int) AS mergent
                FROM mv_employer_data_sources
            """)
            by_source = cur.fetchone()

            return {
                "total_employers": total,
                "source_count_distribution": distribution,
                "by_source": by_source,
            }


# ============================================================================
# UNIFIED EMPLOYER SEARCH (mv_employer_search + review flags)
# ============================================================================

@router.get("/api/employers/unified-search")
def unified_employer_search(
    name: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    metro: Optional[str] = None,
    sector: Optional[str] = None,
    naics: Optional[str] = None,
    aff_abbr: Optional[str] = None,
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
            if metro:
                # mv_employer_search does not yet carry reliable CBSA for all sources.
                raise HTTPException(
                    status_code=422,
                    detail="metro filter is not supported on unified search yet",
                )
            if sector:
                sv = sector.upper()
                if sv == "PUBLIC_SECTOR":
                    conditions.append("source_type = 'PUBLIC'")
                elif sv == "PRIVATE":
                    conditions.append("source_type = 'F7'")
            if naics:
                conditions.append("naics LIKE %s")
                params.append(f"{naics}%")
            if aff_abbr:
                conditions.append(
                    "EXISTS (SELECT 1 FROM unions_master um WHERE um.f_num = m.union_fnum::text AND um.aff_abbr = %s)"
                )
                params.append(aff_abbr.upper())
            if source_type:
                conditions.append("source_type = %s")
                params.append(source_type.upper())
            if has_union is not None:
                conditions.append("has_union = %s")
                params.append(has_union)

            where_clause = " AND ".join(conditions)

            # Count
            cur.execute(f"SELECT COUNT(*) FROM mv_employer_search m WHERE {where_clause}", params)
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


@router.get("/api/employers/unified-detail/{canonical_id:path}")
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
                try:
                    source_id_int = int(source_id)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=404, detail="Employer not found")
                cur.execute("""
                    SELECT p.id, p.participant_name as employer_name, p.city, p.state,
                           p.address_1 as street, p.zip, p.case_number,
                           'NLRB' as source_type
                    FROM nlrb_participants p
                    WHERE p.id = %s
                """, [source_id_int])
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
                try:
                    source_id_int = int(source_id)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=404, detail="Employer not found")
                cur.execute("""
                    SELECT m.*, 'MANUAL' as source_type
                    FROM manual_employers m
                    WHERE m.id = %s
                """, [source_id_int])
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


@router.post("/api/employers/flags")
def create_flag(flag: FlagCreate, user=Depends(require_auth)):
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


@router.get("/api/employers/flags/pending")
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


@router.post("/api/employers/refresh-search")
def refresh_unified_search(user=Depends(require_auth)):
    """Refresh the materialized view for unified employer search."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW mv_employer_search")
            conn.commit()
            cur.execute("SELECT COUNT(*) FROM mv_employer_search")
            total = cur.fetchone()['count']
            return {"refreshed": True, "total_records": total}


@router.delete("/api/employers/flags/{flag_id}")
def delete_flag(flag_id: int, user=Depends(require_auth)):
    """Remove a review flag."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employer_review_flags WHERE id = %s RETURNING id", [flag_id])
            deleted = cur.fetchone()
            conn.commit()
            if not deleted:
                raise HTTPException(status_code=404, detail="Flag not found")
            return {"deleted": True}


@router.get("/api/employers/flags/by-employer/{canonical_id:path}")
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


@router.get("/api/employers/flags/by-source")
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

@router.get("/api/employers/{employer_id}")
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

            # Canonical group context
            group_context = None
            if employer.get('canonical_group_id'):
                cur.execute("""
                    SELECT group_id, canonical_name, canonical_employer_id,
                           member_count, consolidated_workers, is_cross_state, states
                    FROM employer_canonical_groups
                    WHERE group_id = %s
                """, [employer['canonical_group_id']])
                group_context = cur.fetchone()

            return {
                "employer": employer,
                "nlrb_elections": elections,
                "nlrb_summary": {
                    "total_elections": len(elections),
                    "union_wins": sum(1 for e in elections if e['union_won']),
                    "ulp_cases": len(ulp_cases)
                },
                "ulp_cases": ulp_cases,
                "group_context": group_context,
            }


@router.get("/api/employers/{employer_id}/related-filings")
def get_employer_related_filings(employer_id: str):
    """Get canonical group info and all member filings for an employer.

    If the employer is ungrouped (singleton), returns just the single filing.
    If grouped, returns all filings in the same canonical group.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check employer exists and get group info
            cur.execute("""
                SELECT e.employer_id, e.employer_name, e.canonical_group_id,
                       e.is_canonical_rep
                FROM f7_employers_deduped e
                WHERE e.employer_id = %s
            """, [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            group_id = emp['canonical_group_id']

            if not group_id:
                # Ungrouped singleton
                return {
                    "canonical_group_id": None,
                    "canonical_name": emp['employer_name'],
                    "member_count": 1,
                    "consolidated_workers": None,
                    "filings": [{
                        "employer_id": emp['employer_id'],
                        "employer_name": emp['employer_name'],
                        "is_canonical_rep": True,
                    }]
                }

            # Get group metadata
            cur.execute("""
                SELECT group_id, canonical_name, canonical_employer_id,
                       member_count, consolidated_workers, is_cross_state, states
                FROM employer_canonical_groups
                WHERE group_id = %s
            """, [group_id])
            group = cur.fetchone()
            if not group:
                raise HTTPException(status_code=404, detail="Group not found")

            # Get all filings in this group
            cur.execute("""
                SELECT e.employer_id, e.employer_name, e.city, e.state,
                       e.latest_unit_size, e.latest_union_fnum, e.latest_union_name,
                       e.latest_notice_date, e.is_historical,
                       e.is_canonical_rep, e.exclude_from_counts,
                       um.aff_abbr
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.canonical_group_id = %s
                ORDER BY e.is_canonical_rep DESC, e.latest_unit_size DESC NULLS LAST
            """, [group_id])
            filings = cur.fetchall()

            return {
                "canonical_group_id": group['group_id'],
                "canonical_name": group['canonical_name'],
                "canonical_employer_id": group['canonical_employer_id'],
                "member_count": group['member_count'],
                "consolidated_workers": group['consolidated_workers'],
                "is_cross_state": group['is_cross_state'],
                "states": group['states'],
                "filings": filings,
            }


@router.get("/api/admin/employer-groups")
def get_employer_groups_summary(
    limit: int = Query(20, le=100)
):
    """Summary stats for canonical employer groups."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check table exists
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'employer_canonical_groups'
            """)
            if cur.fetchone()['count'] == 0:
                return {"total_groups": 0, "total_grouped": 0, "top_groups": []}

            cur.execute("SELECT COUNT(*) FROM employer_canonical_groups")
            total_groups = cur.fetchone()['count']

            cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE canonical_group_id IS NOT NULL")
            total_grouped = cur.fetchone()['count']

            cur.execute("SELECT COUNT(*) FROM employer_canonical_groups WHERE is_cross_state = TRUE")
            cross_state = cur.fetchone()['count']

            cur.execute("""
                SELECT group_id, canonical_name, canonical_employer_id,
                       state, member_count, consolidated_workers,
                       is_cross_state, states
                FROM employer_canonical_groups
                ORDER BY member_count DESC
                LIMIT %s
            """, [limit])
            top_groups = cur.fetchall()

            return {
                "total_groups": total_groups,
                "total_grouped": total_grouped,
                "cross_state_groups": cross_state,
                "top_groups": top_groups,
            }


@router.get("/api/employers/{employer_id}/similar")
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


@router.get("/api/employers/{employer_id}/data-sources")
def get_employer_data_sources(employer_id: str):
    """Get data source availability and corporate crosswalk for one employer."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM mv_employer_data_sources
                WHERE employer_id = %s
            """, [employer_id])
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Employer not found")
            return dict(row)


@router.get("/api/employers/{employer_id}/osha")
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


@router.get("/api/employers/{employer_id}/nlrb")
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
# NLRB HISTORY (Bridge View)
# ============================================================================

@router.get("/api/employers/{employer_id}/nlrb-history")
def get_employer_nlrb_history(employer_id: str):
    """Get full NLRB history for an employer via the bridge view.

    Returns timeline grouped by category: representation, ULP, unit_clarification.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check employer exists
            cur.execute("SELECT employer_name FROM f7_employers_deduped WHERE employer_id = %s", [employer_id])
            emp = cur.fetchone()
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get all NLRB history from bridge view
            cur.execute("""
                SELECT case_number, case_category, case_type,
                       event_date, case_open_date, case_close_date,
                       employer_name,
                       election_type, union_won,
                       eligible_voters, vote_margin,
                       union_name, union_abbr, allegation_section
                FROM v_nlrb_employer_history
                WHERE f7_employer_id = %s
                ORDER BY event_date DESC
            """, [employer_id])
            rows = cur.fetchall()

            # Group by category
            representation = []
            ulp = []
            unit_clarification = []
            other = []

            for r in rows:
                item = dict(r)
                cat = r['case_category']
                if cat == 'representation':
                    representation.append(item)
                elif cat == 'ulp':
                    ulp.append(item)
                elif cat == 'unit_clarification':
                    unit_clarification.append(item)
                else:
                    other.append(item)

            return {
                "employer_name": emp['employer_name'],
                "employer_id": employer_id,
                "total_cases": len(rows),
                "representation": {
                    "cases": representation,
                    "total": len(representation),
                    "elections": sum(1 for r in representation if r.get('event_date')),
                    "union_wins": sum(1 for r in representation if r.get('union_won') is True),
                    "union_losses": sum(1 for r in representation if r.get('union_won') is False),
                },
                "ulp": {
                    "cases": ulp,
                    "total": len(ulp),
                },
                "unit_clarification": {
                    "cases": unit_clarification,
                    "total": len(unit_clarification),
                },
            }


@router.get("/api/employers/{employer_id}/workforce-profile")
def get_employer_workforce_profile(
    employer_id: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Return typical workforce composition from BLS occupation matrix for employer NAICS."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_name, naics, naics_detailed
                FROM f7_employers_deduped
                WHERE employer_id = %s
            """, [employer_id])
            employer = cur.fetchone()

            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            raw_naics = (employer.get("naics_detailed") or employer.get("naics") or "").strip()
            naics_code = re.sub(r"[^0-9]", "", raw_naics)

            if not naics_code:
                return {
                    "employer_id": employer_id,
                    "employer_name": employer.get("employer_name"),
                    "naics_code": None,
                    "workforce_profile": [],
                    "note": "Employer has no NAICS code",
                }

            cur.execute("""
                SELECT
                    occupation_code,
                    occupation_title,
                    occupation_type,
                    employment_2024,
                    percent_of_industry
                FROM bls_industry_occupation_matrix
                WHERE industry_code LIKE %s
                ORDER BY percent_of_industry DESC NULLS LAST,
                         employment_2024 DESC NULLS LAST,
                         occupation_title
                LIMIT %s
            """, [f"{naics_code}%", limit])
            rows = cur.fetchall()

            return {
                "employer_id": employer_id,
                "employer_name": employer.get("employer_name"),
                "naics_code": naics_code,
                "workforce_profile": [
                    {
                        "occupation_code": row["occupation_code"],
                        "occupation_title": row["occupation_title"],
                        "occupation_type": row["occupation_type"],
                        "employment_2024": float(row["employment_2024"]) if row.get("employment_2024") is not None else None,
                        "employment_share_pct": float(row["percent_of_industry"]) if row.get("percent_of_industry") is not None else None,
                    }
                    for row in rows
                ],
                "note": None if rows else "No BLS occupation data found for NAICS code",
            }


# ============================================================================
# NAICS STATS
# ============================================================================

@router.get("/api/naics/stats")
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


@router.get("/api/employers/by-naics-detailed/{naics_code}")
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
# UNIFIED EMPLOYER STATS (unified_employers_osha)
# ============================================================================

@router.get("/api/employers/unified/stats")
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


@router.get("/api/employers/unified/search")
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
    """DEPRECATED: Legacy endpoint querying old unified_employers_osha table. Use /api/employers/unified-search instead."""
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


@router.get("/api/employers/unified/{unified_id}")
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


@router.get("/api/osha/unified-matches")
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


@router.get("/api/employers/unified/sources")
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
# EMPLOYER COMPARABLES
# ============================================================================

@router.get("/api/employers/{employer_id}/comparables")
def get_employer_comparables(employer_id: int):
    """Get the top-5 most similar unionized employers for a given mergent employer.
    Uses pre-computed Gower distance from the employer similarity engine."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get the target employer
            cur.execute("""
                SELECT id, company_name, state, naics_primary, employees_site,
                       employees_all_sites, similarity_score
                FROM mergent_employers WHERE id = %s
            """, [employer_id])
            employer = cur.fetchone()
            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Get comparables
            cur.execute("""
                SELECT ec.rank, ec.gower_distance, ec.feature_breakdown,
                       me.id AS comparable_id, me.company_name AS comparable_name,
                       me.state AS comparable_state, me.naics_primary AS comparable_naics,
                       me.employees_site AS comparable_employees,
                       me.f7_union_name
                FROM employer_comparables ec
                JOIN mergent_employers me ON me.id = ec.comparable_employer_id
                WHERE ec.employer_id = %s
                ORDER BY ec.rank
            """, [employer_id])
            rows = cur.fetchall()

            comparables = []
            for r in rows:
                breakdown = r.get('feature_breakdown') or {}
                if isinstance(breakdown, str):
                    import json
                    breakdown = json.loads(breakdown)

                # Generate human-readable match reasons from feature breakdown
                match_reasons = []
                target_naics = employer.get('naics_primary') or ''
                comp_naics = r.get('comparable_naics') or ''
                if breakdown.get('naics_4', 1) == 0:
                    match_reasons.append(f"Same industry (NAICS {target_naics[:4]})")
                elif breakdown.get('naics_4', 1) <= 0.3:
                    match_reasons.append(f"Same sector (NAICS {target_naics[:2]})")

                if breakdown.get('state', 1) == 0:
                    match_reasons.append(f"Same state ({employer.get('state')})")

                if breakdown.get('employees_here_log', 1) < 0.15:
                    t_emp = employer.get('employees_site') or employer.get('employees_all_sites')
                    c_emp = r.get('comparable_employees')
                    if t_emp and c_emp:
                        match_reasons.append(f"Similar size ({t_emp:,} vs {c_emp:,} employees)")
                    else:
                        match_reasons.append("Similar workforce size")

                if breakdown.get('county', 1) == 0:
                    match_reasons.append("Same county")

                if breakdown.get('is_subsidiary', 1) == 0:
                    match_reasons.append("Same corporate structure")

                if breakdown.get('osha_violation_rate', 1) < 0.1:
                    match_reasons.append("Similar OSHA violation profile")

                if breakdown.get('whd_violation_rate', 1) < 0.1:
                    match_reasons.append("Similar wage compliance profile")

                if breakdown.get('is_federal_contractor', 1) == 0:
                    match_reasons.append("Both federal contractors" if breakdown.get('is_federal_contractor', 1) == 0 else "")

                comparables.append({
                    'rank': r['rank'],
                    'comparable_id': r['comparable_id'],
                    'comparable_name': r['comparable_name'],
                    'union_name': r.get('f7_union_name'),
                    'gower_distance': float(r['gower_distance']),
                    'similarity_pct': round((1 - float(r['gower_distance'])) * 100),
                    'match_reasons': [m for m in match_reasons if m],
                    'feature_breakdown': breakdown
                })

            return {
                "employer_id": employer_id,
                "employer_name": employer.get('company_name'),
                "similarity_score": float(employer['similarity_score']) if employer.get('similarity_score') is not None else None,
                "comparables": comparables
            }
