from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from ..database import get_db

router = APIRouter()


@router.get("/api/public-sector/stats")
def get_public_sector_stats():
    """Get summary statistics for public sector data"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM ps_union_locals")
            locals_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_employers")
            employers_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_parent_unions")
            parents_count = cur.fetchone()['count']
            cur.execute("SELECT COUNT(*) as count FROM ps_bargaining_units")
            bu_count = cur.fetchone()['count']
            cur.execute("SELECT SUM(members) as total FROM ps_union_locals WHERE members > 0")
            total_members = cur.fetchone()['total'] or 0
            cur.execute("""
                SELECT employer_type, COUNT(*) as count
                FROM ps_employers
                GROUP BY employer_type
                ORDER BY count DESC
            """)
            employer_types = cur.fetchall()
            cur.execute("""
                SELECT p.abbrev, p.full_name, COUNT(l.id) as local_count,
                       SUM(l.members) as total_members
                FROM ps_parent_unions p
                LEFT JOIN ps_union_locals l ON p.id = l.parent_union_id
                GROUP BY p.id, p.abbrev, p.full_name
                ORDER BY total_members DESC NULLS LAST
            """)
            parent_summary = cur.fetchall()

            return {
                "union_locals": locals_count,
                "employers": employers_count,
                "parent_unions": parents_count,
                "bargaining_units": bu_count,
                "total_members": total_members,
                "employer_types": employer_types,
                "parent_summary": parent_summary
            }


@router.get("/api/public-sector/parent-unions")
def get_public_sector_parent_unions():
    """Get list of parent unions for filtering"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.abbrev, p.full_name, p.federation, p.sector_focus,
                       COUNT(l.id) as local_count
                FROM ps_parent_unions p
                LEFT JOIN ps_union_locals l ON p.id = l.parent_union_id
                GROUP BY p.id
                ORDER BY p.full_name
            """)
            return {"parent_unions": cur.fetchall()}


@router.get("/api/public-sector/locals")
def search_public_sector_locals(
    state: Optional[str] = None,
    parent_union: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search public sector union locals"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if state:
                conditions.append("l.state = %s")
                params.append(state.upper())
            if parent_union:
                conditions.append("p.abbrev = %s")
                params.append(parent_union.upper())
            if name:
                conditions.append("l.local_name ILIKE %s")
                params.append(f"%{name}%")

            where_clause = " AND ".join(conditions)

            cur.execute(f"""
                SELECT COUNT(*) FROM ps_union_locals l
                JOIN ps_parent_unions p ON l.parent_union_id = p.id
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            params.extend([limit, offset])
            cur.execute(f"""
                SELECT l.id, l.local_name, l.local_designation, l.state, l.city,
                       l.members, l.sector_type, l.f_num,
                       p.abbrev as parent_abbrev, p.full_name as parent_name
                FROM ps_union_locals l
                JOIN ps_parent_unions p ON l.parent_union_id = p.id
                WHERE {where_clause}
                ORDER BY l.members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "locals": cur.fetchall()}


@router.get("/api/public-sector/employers")
def search_public_sector_employers(
    state: Optional[str] = None,
    employer_type: Optional[str] = None,
    name: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search public sector employers"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            if state:
                conditions.append("state = %s")
                params.append(state.upper())
            if employer_type:
                conditions.append("employer_type = %s")
                params.append(employer_type.upper())
            if name:
                conditions.append("employer_name ILIKE %s")
                params.append(f"%{name}%")

            where_clause = " AND ".join(conditions)

            cur.execute(f"SELECT COUNT(*) FROM ps_employers WHERE {where_clause}", params)
            total = cur.fetchone()['count']

            params.extend([limit, offset])
            cur.execute(f"""
                SELECT id, employer_name, employer_type, state, city, county,
                       total_employees, naics_code
                FROM ps_employers
                WHERE {where_clause}
                ORDER BY employer_name
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "employers": cur.fetchall()}


@router.get("/api/public-sector/employer-types")
def get_public_sector_employer_types():
    """Get list of employer types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT employer_type, COUNT(*) as count
                FROM ps_employers
                GROUP BY employer_type
                ORDER BY count DESC
            """)
            return {"employer_types": cur.fetchall()}


@router.get("/api/public-sector/benchmarks")
def get_public_sector_benchmarks(state: Optional[str] = None):
    """Get state-level public sector benchmarks"""
    with get_db() as conn:
        with conn.cursor() as cur:
            if state:
                cur.execute("""
                    SELECT * FROM public_sector_benchmarks WHERE state = %s
                """, [state.upper()])
                result = cur.fetchone()
                return {"benchmark": result}
            else:
                cur.execute("""
                    SELECT state, state_name, epi_public_members, epi_public_density_pct,
                           olms_state_local_members, olms_federal_members, data_quality_flag
                    FROM public_sector_benchmarks
                    ORDER BY epi_public_members DESC NULLS LAST
                """)
                return {"benchmarks": cur.fetchall()}
