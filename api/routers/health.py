from fastapi import APIRouter
from typing import Optional
from ..database import get_db

router = APIRouter()


@router.get("/api/summary")
def get_platform_summary():
    """Get overall platform summary statistics"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Unions
            cur.execute("""
                SELECT COUNT(*) as total_unions, SUM(members) as total_members,
                    COUNT(DISTINCT aff_abbr) as affiliations
                FROM unions_master
            """)
            unions = cur.fetchone()

            # Employers (with deduplication stats)
            cur.execute("""
                SELECT COUNT(*) as total_employers,
                    SUM(latest_unit_size) as total_workers_raw,
                    SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) as covered_workers,
                    COUNT(DISTINCT state) as states,
                    COUNT(CASE WHEN exclude_from_counts = TRUE THEN 1 END) as excluded_records,
                    ROUND(100.0 * SUM(CASE WHEN exclude_from_counts = FALSE THEN latest_unit_size ELSE 0 END) / 7200000, 1) as bls_coverage_pct
                FROM f7_employers_deduped
            """)
            employers = cur.fetchone()

            # NLRB
            cur.execute("""
                SELECT COUNT(*) as total_elections,
                    SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
                    ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) /
                        NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections WHERE union_won IS NOT NULL
            """)
            elections = cur.fetchone()

            cur.execute("""
                SELECT COUNT(*) as total_cases
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                WHERE ct.case_category = 'unfair_labor_practice'
            """)
            ulp = cur.fetchone()

            # Voluntary Recognition
            cur.execute("""
                SELECT COUNT(*) as total_cases,
                       COUNT(matched_employer_id) as employers_matched,
                       COUNT(matched_union_fnum) as unions_matched,
                       SUM(COALESCE(num_employees, 0)) as total_employees
                FROM nlrb_voluntary_recognition
            """)
            vr = cur.fetchone()

            return {
                "unions": unions,
                "employers": employers,
                "nlrb": {
                    "elections": elections,
                    "ulp_cases": ulp['total_cases']
                },
                "voluntary_recognition": vr
            }


@router.get("/api/stats/breakdown")
def get_stats_breakdown(
    state: str = None,
    naics_code: str = None,
    cbsa_code: str = None,
    name: str = None
):
    """Get breakdown statistics for the filter panel"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Build WHERE clause (use f. prefix for joined queries)
            conditions = ["f.exclude_from_counts = FALSE"]
            params = []

            if state:
                conditions.append("f.state = %s")
                params.append(state)
            if naics_code:
                conditions.append("f.naics LIKE %s")
                params.append(f"{naics_code}%")
            if cbsa_code:
                conditions.append("f.cbsa_code = %s")
                params.append(cbsa_code)
            if name:
                conditions.append("f.employer_name ILIKE %s")
                params.append(f"%{name}%")

            where_clause = " AND ".join(conditions)

            # Totals
            cur.execute(f"""
                SELECT COUNT(*) as total_employers,
                       COALESCE(SUM(f.latest_unit_size), 0) as total_workers,
                       COUNT(DISTINCT f.latest_union_fnum) as total_locals
                FROM f7_employers_deduped f
                WHERE {where_clause}
            """, params)
            totals = cur.fetchone()

            # By Industry (top 5 NAICS 2-digit)
            cur.execute(f"""
                SELECT LEFT(f.naics, 2) as naics_code,
                       COALESCE(ns.sector_name, LEFT(f.naics, 2)) as industry_name,
                       COUNT(*) as employer_count, COALESCE(SUM(f.latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN naics_sectors ns ON LEFT(f.naics, 2) = ns.naics_2digit
                WHERE {where_clause} AND f.naics IS NOT NULL AND LENGTH(f.naics) >= 2
                GROUP BY LEFT(f.naics, 2), ns.sector_name
                ORDER BY worker_count DESC NULLS LAST
                LIMIT 5
            """, params)
            by_industry = cur.fetchall()

            # By Metro (top 5)
            cur.execute(f"""
                SELECT f.cbsa_code, COALESCE(c.cbsa_title, f.cbsa_code) as metro_name,
                       COUNT(*) as employer_count, COALESCE(SUM(latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN cbsa_definitions c ON f.cbsa_code = c.cbsa_code
                WHERE {where_clause} AND f.cbsa_code IS NOT NULL
                GROUP BY f.cbsa_code, c.cbsa_title
                ORDER BY worker_count DESC NULLS LAST
                LIMIT 5
            """, params)
            by_metro = cur.fetchall()

            # By Sector (union sector - Private, Public, Federal, RLA)
            cur.execute(f"""
                SELECT COALESCE(um.sector, 'Unknown') as sector_name,
                       COUNT(*) as employer_count, COALESCE(SUM(f.latest_unit_size), 0) as worker_count
                FROM f7_employers_deduped f
                LEFT JOIN unions_master um ON f.latest_union_fnum::text = um.f_num
                WHERE {where_clause}
                GROUP BY um.sector
                ORDER BY worker_count DESC NULLS LAST
            """, params)
            by_sector = cur.fetchall()

            return {
                "totals": totals,
                "by_sector": by_sector,
                "by_industry": by_industry,
                "by_metro": by_metro
            }


@router.get("/api/health/details")
def health_check():
    """Detailed API health diagnostics."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as vr FROM nlrb_voluntary_recognition")
                vr_count = cur.fetchone()['vr']
                cur.execute("SELECT COUNT(*) as osha FROM osha_establishments")
                osha_count = cur.fetchone()['osha']
                cur.execute("SELECT COUNT(*) as ind FROM bls_industry_projections")
                ind_count = cur.fetchone()['ind']
                cur.execute("SELECT COUNT(*) as occ FROM bls_industry_occupation_matrix")
                occ_count = cur.fetchone()['occ']
                # NAICS granularity stats
                cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE naics_source = 'OSHA') as osha_enriched,
                           COUNT(*) FILTER (WHERE LENGTH(naics_detailed) = 6) as six_digit_naics
                    FROM f7_employers_deduped
                """)
                naics_stats = cur.fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "version": "6.4-multi-employer-dedup",
            "vr_records": vr_count,
            "osha_establishments": osha_count,
            "bls_industries": ind_count,
            "bls_occupation_records": occ_count,
            "naics_osha_enriched": naics_stats['osha_enriched'],
            "naics_6digit_employers": naics_stats['six_digit_naics']
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
