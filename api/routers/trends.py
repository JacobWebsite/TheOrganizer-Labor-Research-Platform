from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db

router = APIRouter()


@router.get("/api/trends/national")
def get_national_trends():
    """Get national union membership trends by year (2010-2024) with deduplicated estimates"""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get raw trends by year
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members_raw,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """)
            raw_trends = cur.fetchall()

            # Get current deduplicated total and ratio from view
            cur.execute("""
                SELECT
                    SUM(CASE WHEN count_members THEN members ELSE 0 END) as deduplicated_total,
                    SUM(members) as raw_total
                FROM v_union_members_deduplicated
            """)
            dedup_stats = cur.fetchone()

            # Calculate deduplication ratio (typically ~0.20-0.21)
            dedup_ratio = 0.20  # fallback
            if dedup_stats and dedup_stats['raw_total'] and dedup_stats['raw_total'] > 0:
                dedup_ratio = dedup_stats['deduplicated_total'] / dedup_stats['raw_total']

            # Apply ratio to get estimated deduplicated membership by year
            trends = []
            for row in raw_trends:
                trend = dict(row)
                # Estimate deduplicated members using the ratio
                trend['total_members_dedup'] = int(row['total_members_raw'] * dedup_ratio)
                trends.append(trend)

            return {
                "description": "National union membership trends",
                "note": "total_members_dedup is estimated using current deduplication ratio. BLS benchmark is ~14-15M",
                "dedup_ratio": round(dedup_ratio, 4),
                "current_dedup_total": dedup_stats['deduplicated_total'] if dedup_stats else None,
                "trends": trends
            }


@router.get("/api/trends/affiliations/summary")
def get_affiliation_trends_summary():
    """Get membership trends summary for top affiliations"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH yearly AS (
                    SELECT aff_abbr,
                           yr_covered,
                           SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as members
                    FROM lm_data
                    WHERE aff_abbr IS NOT NULL AND yr_covered IN (2010, 2024)
                    GROUP BY aff_abbr, yr_covered
                ),
                pivoted AS (
                    SELECT aff_abbr,
                           MAX(CASE WHEN yr_covered = 2010 THEN members END) as members_2010,
                           MAX(CASE WHEN yr_covered = 2024 THEN members END) as members_2024
                    FROM yearly
                    GROUP BY aff_abbr
                )
                SELECT aff_abbr,
                       members_2010,
                       members_2024,
                       members_2024 - members_2010 as change,
                       ROUND(100.0 * (members_2024 - members_2010) / NULLIF(members_2010, 0), 1) as pct_change
                FROM pivoted
                WHERE members_2024 > 10000
                ORDER BY members_2024 DESC
                LIMIT 30
            """)
            return {"affiliations": cur.fetchall()}


@router.get("/api/trends/by-affiliation/{aff_abbr}")
def get_affiliation_trends(aff_abbr: str):
    """Get membership trends for a specific affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE aff_abbr = %s AND yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """, [aff_abbr.upper()])
            trends = cur.fetchall()

            return {
                "affiliation": aff_abbr.upper(),
                "trends": trends
            }


@router.get("/api/trends/states/summary")
def get_state_trends_summary():
    """Get membership summary by state for latest year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH state_data AS (
                    SELECT state,
                           yr_covered,
                           SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as members,
                           COUNT(DISTINCT f_num) as union_count
                    FROM lm_data
                    WHERE state IS NOT NULL AND yr_covered IN (2010, 2024)
                    GROUP BY state, yr_covered
                ),
                pivoted AS (
                    SELECT state,
                           MAX(CASE WHEN yr_covered = 2010 THEN members END) as members_2010,
                           MAX(CASE WHEN yr_covered = 2024 THEN members END) as members_2024,
                           MAX(CASE WHEN yr_covered = 2024 THEN union_count END) as unions_2024
                    FROM state_data
                    GROUP BY state
                )
                SELECT state,
                       members_2010,
                       members_2024,
                       unions_2024,
                       ROUND(100.0 * (members_2024 - members_2010) / NULLIF(members_2010, 0), 1) as pct_change
                FROM pivoted
                WHERE members_2024 > 0
                ORDER BY members_2024 DESC
            """)
            return {"states": cur.fetchall()}


@router.get("/api/trends/by-state/{state}")
def get_state_trends(state: str):
    """Get membership trends for a specific state"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT yr_covered as year,
                       COUNT(DISTINCT f_num) as union_count,
                       SUM(CASE WHEN members > 0 THEN members ELSE 0 END) as total_members,
                       COUNT(*) as filing_count
                FROM lm_data
                WHERE state = %s AND yr_covered BETWEEN 2010 AND 2024
                GROUP BY yr_covered
                ORDER BY yr_covered
            """, [state.upper()])
            trends = cur.fetchall()

            return {
                "state": state.upper(),
                "trends": trends
            }


@router.get("/api/trends/elections")
def get_election_trends():
    """Get NLRB election trends by year"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(YEAR FROM election_date)::int as year,
                       COUNT(*) as total_elections,
                       SUM(CASE WHEN union_won THEN 1 ELSE 0 END) as union_wins,
                       SUM(CASE WHEN union_won = false THEN 1 ELSE 0 END) as union_losses,
                       SUM(eligible_voters) as total_voters,
                       ROUND(100.0 * SUM(CASE WHEN union_won THEN 1 ELSE 0 END) /
                           NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections
                WHERE election_date IS NOT NULL
                  AND union_won IS NOT NULL
                  AND EXTRACT(YEAR FROM election_date) BETWEEN 2007 AND 2024
                GROUP BY EXTRACT(YEAR FROM election_date)
                ORDER BY year
            """)
            return {"election_trends": cur.fetchall()}


@router.get("/api/trends/elections/by-affiliation/{aff_abbr}")
def get_election_trends_by_affiliation(aff_abbr: str):
    """Get NLRB election trends for a specific union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXTRACT(YEAR FROM e.election_date)::int as year,
                       COUNT(DISTINCT e.case_number) as total_elections,
                       SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as union_wins,
                       ROUND(100.0 * SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) /
                           NULLIF(COUNT(*), 0), 1) as win_rate
                FROM nlrb_elections e
                JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE um.aff_abbr = %s
                  AND e.election_date IS NOT NULL
                  AND e.union_won IS NOT NULL
                  AND EXTRACT(YEAR FROM e.election_date) BETWEEN 2007 AND 2024
                GROUP BY EXTRACT(YEAR FROM e.election_date)
                ORDER BY year
            """, [aff_abbr.upper()])

            return {
                "affiliation": aff_abbr.upper(),
                "election_trends": cur.fetchall()
            }


@router.get("/api/trends/sectors")
def get_sector_trends():
    """Get employer distribution by NAICS sector"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT LEFT(e.naics, 2) as naics_2digit,
                       ns.sector_name,
                       COUNT(*) as employer_count,
                       SUM(e.latest_unit_size) as total_workers,
                       ROUND(AVG(e.latest_unit_size), 0) as avg_unit_size
                FROM f7_employers_deduped e
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE e.naics IS NOT NULL AND LENGTH(e.naics) >= 2
                GROUP BY LEFT(e.naics, 2), ns.sector_name
                ORDER BY COUNT(*) DESC
            """)
            return {"sectors": cur.fetchall()}
