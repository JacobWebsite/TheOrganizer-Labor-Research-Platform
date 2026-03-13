from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from ..database import get_db

router = APIRouter()

ORGANIZING_DISBURSEMENT_FIELDS = ("representational", "strike_benefits")
TREND_THRESHOLD_PCT = 2.0

INTERMEDIATE_CODES = {'DC', 'JC', 'CONF', 'D', 'C', 'SC', 'SA', 'BCTC'}


def _classify_union_level(desig_name):
    code = (desig_name or '').strip().upper()
    if code in ('NHQ', 'FED'):
        return 'national'
    if code in INTERMEDIATE_CODES:
        return 'intermediate'
    return 'local'


def _compute_trend_from_points(points: List[dict]) -> str:
    """Classify trend from earliest/latest values in a year-series."""
    if len(points) < 2:
        return "stable"

    ordered = sorted(points, key=lambda p: p["year"])
    first = ordered[0]["members"]
    last = ordered[-1]["members"]

    if first is None or last is None or first <= 0:
        return "stable"

    pct_change = ((last - first) / first) * 100.0
    if pct_change > TREND_THRESHOLD_PCT:
        return "growing"
    if pct_change < -TREND_THRESHOLD_PCT:
        return "declining"
    return "stable"


def _get_membership_points(cur, file_number: str, years: int = 10) -> List[dict]:
    cur.execute(
        """
        WITH yearly AS (
            SELECT
                lm.yr_covered AS year,
                SUM(CASE WHEN am.voting_eligibility = 'T' THEN COALESCE(am.number, 0) ELSE 0 END) AS members
            FROM ar_membership am
            JOIN lm_data lm ON lm.rpt_id = am.rpt_id
            WHERE lm.f_num = %s
            GROUP BY lm.yr_covered
        )
        SELECT year, members
        FROM yearly
        ORDER BY year DESC
        LIMIT %s
        """,
        [file_number, years],
    )
    rows = cur.fetchall()
    return [
        {"year": row["year"], "members": int(row["members"] or 0)}
        for row in sorted(rows, key=lambda r: r["year"])
    ]


@router.get("/api/unions/cities")
def get_union_cities(
    state: str = Query(..., description="State code (e.g., CA, NY)"),
    limit: int = Query(200, le=500)
):
    """Get cities for a state from unions_master, ordered by union count"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT UPPER(city) as city, COUNT(*) as union_count, SUM(members) as total_members
                FROM unions_master
                WHERE state = %s AND city IS NOT NULL AND TRIM(city) != ''
                GROUP BY UPPER(city)
                ORDER BY COUNT(*) DESC, SUM(members) DESC
                LIMIT %s
            """, [state.upper(), limit])
            return {"state": state.upper(), "cities": cur.fetchall()}


@router.get("/api/unions/search")
def search_unions(
    name: Optional[str] = None,
    q: Optional[str] = None,
    aff_abbr: Optional[str] = None,
    sector: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    union_type: Optional[str] = None,
    min_members: Optional[int] = None,
    has_employers: Optional[bool] = None,
    include_historical: bool = False,
    limit: int = Query(50, le=500),
    offset: int = 0
):
    """Search unions with filters including display names and hierarchy type.

    By default, only shows current unions (yr_covered >= 2022).
    Set include_historical=true to include older/defunct unions.
    Accepts both 'name' and 'q' as search parameters.
    """
    # Accept both 'q' and 'name' for search term
    search_term = name or q

    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["1=1"]
            params = []

            # Filter out stale/historical unions by default
            if not include_historical:
                conditions.append("um.yr_covered >= 2022")

            if search_term:
                # Search union_name, local_number, and display_name
                conditions.append("""(
                    um.union_name ILIKE %s
                    OR um.local_number = %s
                    OR v.display_name ILIKE %s
                )""")
                clean_name = search_term.replace('local ', '').replace('Local ', '').strip()
                params.extend([f"%{search_term}%", clean_name, f"%{search_term}%"])
            if aff_abbr:
                conditions.append("um.aff_abbr = %s")
                params.append(aff_abbr.upper())
            if sector:
                conditions.append("um.sector = %s")
                params.append(sector.upper())
            if state:
                conditions.append("um.state = %s")
                params.append(state.upper())
            if city:
                conditions.append("UPPER(um.city) = %s")
                params.append(city.upper())
            if union_type:
                conditions.append("TRIM(um.desig_name) = %s")
                params.append(union_type.upper())
            if min_members:
                conditions.append("um.members >= %s")
                params.append(min_members)
            if has_employers:
                conditions.append("um.has_f7_employers = true")

            where_clause = " AND ".join(conditions)

            # Count query
            cur.execute(f"""
                SELECT COUNT(*) FROM unions_master um
                LEFT JOIN v_union_display_names v ON um.f_num = v.f_num
                WHERE {where_clause}
            """, params)
            total = cur.fetchone()['count']

            params.extend([limit, offset])
            cur.execute(f"""
                SELECT um.f_num, um.union_name, v.display_name, um.local_number,
                    um.aff_abbr, um.desig_name, um.members, um.city, um.state,
                    um.sector, um.f7_employer_count, um.f7_total_workers, um.has_f7_employers,
                    lm.ttl_assets, lm.ttl_receipts, um.is_likely_inactive
                FROM unions_master um
                LEFT JOIN v_union_display_names v ON um.f_num = v.f_num
                LEFT JOIN lm_data lm ON um.f_num = lm.f_num AND lm.yr_covered = 2024
                WHERE {where_clause}
                ORDER BY um.members DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, params)

            return {"total": total, "unions": cur.fetchall()}


@router.get("/api/unions/types")
def get_union_types():
    """Get list of union designation types with counts"""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TRIM(desig_name) as type_code,
                    CASE TRIM(desig_name)
                        WHEN 'LU' THEN 'Local Union'
                        WHEN 'NHQ' THEN 'National Headquarters'
                        WHEN 'C' THEN 'Council'
                        WHEN 'JC' THEN 'Joint Council'
                        WHEN 'DC' THEN 'District Council'
                        WHEN 'SC' THEN 'State Council'
                        WHEN 'D' THEN 'District'
                        WHEN 'BR' THEN 'Branch'
                        WHEN 'LG' THEN 'Lodge'
                        WHEN 'DIV' THEN 'Division'
                        WHEN 'CH' THEN 'Chapter'
                        WHEN 'CONF' THEN 'Conference'
                        WHEN 'FED' THEN 'Federation'
                        WHEN 'SLG' THEN 'Sub-Lodge'
                        WHEN 'LLG' THEN 'Local Lodge'
                        WHEN 'SA' THEN 'System Assembly'
                        WHEN 'BCTC' THEN 'Building & Construction Trades Council'
                        WHEN 'LEC' THEN 'Local Executive Council'
                        ELSE TRIM(desig_name)
                    END as type_name,
                    SUM(cnt) as count
                FROM (
                    SELECT TRIM(desig_name) as desig_name, COUNT(*) as cnt
                    FROM unions_master
                    WHERE desig_name IS NOT NULL AND TRIM(desig_name) != ''
                    GROUP BY desig_name
                ) sub
                GROUP BY TRIM(desig_name)
                HAVING SUM(cnt) >= 10
                ORDER BY SUM(cnt) DESC
            """)
            return {"types": cur.fetchall()}


@router.get("/api/unions/national")
def get_national_unions(
    include_inactive: bool = False,
    limit: int = Query(50, le=200)
):
    """Get national/international unions aggregated by affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            inactive_filter = "" if include_inactive else "AND (NOT is_likely_inactive OR is_likely_inactive IS NULL)"
            cur.execute(f"""
                SELECT um.aff_abbr,
                       MAX(um.union_name) as example_name,
                       COUNT(*) as local_count,
                       SUM(um.members) as total_members,
                       SUM(CASE WHEN uh.count_members THEN um.members ELSE 0 END) as deduplicated_members,
                       MAX(um.members) as nhq_members,
                       SUM(um.f7_employer_count) as employer_count,
                       SUM(um.f7_total_workers) as covered_workers,
                       COUNT(DISTINCT um.state) as state_count
                FROM unions_master um
                LEFT JOIN union_hierarchy uh ON um.f_num = uh.f_num
                WHERE um.aff_abbr IS NOT NULL AND um.aff_abbr != ''
                  {inactive_filter.replace('is_likely_inactive', 'um.is_likely_inactive')}
                GROUP BY um.aff_abbr
                HAVING SUM(um.members) > 0
                ORDER BY MAX(um.members) DESC NULLS LAST
                LIMIT %s
            """, [limit])
            return {"national_unions": cur.fetchall()}


@router.get("/api/unions/national/{aff_abbr}")
def get_national_union_detail(aff_abbr: str, include_inactive: bool = False):
    """Get detailed info for a national union affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            inactive_filter = "" if include_inactive else "AND (NOT is_likely_inactive OR is_likely_inactive IS NULL)"

            # Summary stats
            cur.execute(f"""
                SELECT um.aff_abbr,
                       COUNT(*) as local_count,
                       SUM(um.members) as total_members,
                       SUM(CASE WHEN uh.count_members THEN um.members ELSE 0 END) as deduplicated_members,
                       SUM(um.f7_employer_count) as employer_count,
                       SUM(um.f7_total_workers) as covered_workers,
                       COUNT(DISTINCT um.state) as state_count
                FROM unions_master um
                LEFT JOIN union_hierarchy uh ON um.f_num = uh.f_num
                WHERE um.aff_abbr = %s {inactive_filter.replace('is_likely_inactive', 'um.is_likely_inactive')}
                GROUP BY um.aff_abbr
            """, [aff_abbr.upper()])
            summary = cur.fetchone()

            if not summary:
                raise HTTPException(status_code=404, detail="Affiliation not found")

            # Top locals by membership
            cur.execute(f"""
                SELECT f_num, union_name, local_number, city, state, members,
                       f7_employer_count, f7_total_workers
                FROM unions_master
                WHERE aff_abbr = %s {inactive_filter}
                ORDER BY members DESC NULLS LAST
                LIMIT 20
            """, [aff_abbr.upper()])
            top_locals = cur.fetchall()

            # State breakdown
            cur.execute(f"""
                SELECT state, COUNT(*) as local_count, SUM(members) as total_members
                FROM unions_master
                WHERE aff_abbr = %s AND state IS NOT NULL {inactive_filter}
                GROUP BY state
                ORDER BY SUM(members) DESC NULLS LAST
            """, [aff_abbr.upper()])
            by_state = cur.fetchall()

            # Recent NLRB activity
            cur.execute("""
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                       p.participant_name as employer_name, p.state
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number
                    AND p.participant_type = 'Employer'
                WHERE um.aff_abbr = %s
                ORDER BY e.election_date DESC
                LIMIT 20
            """, [aff_abbr.upper()])
            recent_elections = cur.fetchall()

            return {
                "summary": summary,
                "top_locals": top_locals,
                "by_state": by_state,
                "recent_elections": recent_elections
            }


@router.get("/api/unions/hierarchy/{aff_abbr}")
def get_union_hierarchy(aff_abbr: str, include_inactive: bool = False):
    """Full hierarchy tree for an affiliation with intermediates."""
    with get_db() as conn:
        with conn.cursor() as cur:
            inactive_filter = "" if include_inactive else "AND (NOT is_likely_inactive OR is_likely_inactive IS NULL)"

            # Get all unions for this affiliation
            cur.execute(f"""
                SELECT f_num, union_name, desig_name, local_number,
                       city, state, members, parent_fnum, is_likely_inactive
                FROM unions_master
                WHERE aff_abbr = %s {inactive_filter}
                ORDER BY members DESC NULLS LAST
            """, [aff_abbr.upper()])
            all_unions = cur.fetchall()

            if not all_unions:
                raise HTTPException(status_code=404, detail="Affiliation not found")

            # Classify each union
            national = None
            intermediates = {}  # f_num -> {data, locals: []}
            orphan_locals = {}  # state -> [locals]

            for u in all_unions:
                level = _classify_union_level(u['desig_name'])
                if level == 'national':
                    national = {
                        "f_num": u['f_num'], "name": u['union_name'],
                        "members": u['members'], "is_likely_inactive": u.get('is_likely_inactive', False)
                    }
                elif level == 'intermediate':
                    intermediates[u['f_num']] = {
                        "f_num": u['f_num'], "name": u['union_name'],
                        "level_code": (u['desig_name'] or '').strip().upper(),
                        "members": u['members'], "city": u['city'], "state": u['state'],
                        "is_likely_inactive": u.get('is_likely_inactive', False),
                        "locals": []
                    }
                else:
                    parent = u.get('parent_fnum')
                    if parent and parent in intermediates:
                        intermediates[parent]["locals"].append({
                            "f_num": u['f_num'], "name": u['union_name'],
                            "local_number": u.get('local_number'),
                            "members": u['members'], "city": u['city'], "state": u['state'],
                            "is_likely_inactive": u.get('is_likely_inactive', False)
                        })
                    else:
                        st = u['state'] or 'Unknown'
                        if st not in orphan_locals:
                            orphan_locals[st] = []
                        orphan_locals[st].append({
                            "f_num": u['f_num'], "name": u['union_name'],
                            "local_number": u.get('local_number'),
                            "members": u['members'], "city": u['city'], "state": u['state'],
                            "is_likely_inactive": u.get('is_likely_inactive', False)
                        })

            # Add locals_count to intermediates
            inter_list = list(intermediates.values())
            for inter in inter_list:
                inter["locals_count"] = len(inter["locals"])

            return {
                "affiliation": aff_abbr.upper(),
                "national": national,
                "intermediates": inter_list,
                "unaffiliated_locals": {"by_state": orphan_locals}
            }


@router.get("/api/unions/{file_number}/disbursements")
def get_union_disbursements(file_number: str):
    """Return up to 10 years of categorized disbursement breakdowns for a union."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f_num, union_name FROM unions_master WHERE f_num = %s",
                [file_number],
            )
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            cur.execute(
                """
                SELECT lm.yr_covered AS year,
                       COALESCE(adt.representational, 0) AS representational,
                       COALESCE(adt.political, 0) AS political,
                       COALESCE(adt.strike_benefits, 0) AS strike_benefits,
                       COALESCE(adt.to_officers, 0) AS to_officers,
                       COALESCE(adt.to_employees, 0) AS to_employees,
                       COALESCE(adt.benefits, 0) AS benefits,
                       COALESCE(adt.per_capita_tax, 0) AS per_capita_tax,
                       COALESCE(adt.general_overhead, 0) AS general_overhead,
                       COALESCE(adt.contributions, 0) AS contributions,
                       COALESCE(adt.affiliates, 0) AS affiliates,
                       COALESCE(adt.union_administration, 0) AS union_administration,
                       COALESCE(adt.supplies, 0) AS supplies,
                       COALESCE(adt.fees, 0) AS fees,
                       COALESCE(adt.administration, 0) AS administration,
                       COALESCE(adt.direct_taxes, 0) AS direct_taxes,
                       COALESCE(adt.withheld, 0) AS withheld,
                       COALESCE(adt.members, 0) AS members,
                       COALESCE(adt.investments, 0) AS investments,
                       COALESCE(adt.loans_made, 0) AS loans_made,
                       COALESCE(adt.loans_payment, 0) AS loans_payment,
                       COALESCE(adt.other_disbursements, 0) AS other_disbursements
                FROM lm_data lm
                JOIN ar_disbursements_total adt ON adt.rpt_id = lm.rpt_id
                WHERE lm.f_num = %s
                ORDER BY lm.yr_covered DESC
                LIMIT 10
                """,
                [file_number],
            )
            rows = cur.fetchall()

            years = []
            for row in rows:
                organizing = (
                    float(row["representational"])
                    + float(row["strike_benefits"])
                    + float(row["political"])
                )
                compensation = (
                    float(row["to_officers"])
                    + float(row["to_employees"])
                )
                benefits_members = (
                    float(row["benefits"])
                    + float(row["members"])
                    + float(row["contributions"])
                )
                administration = (
                    float(row["general_overhead"])
                    + float(row["union_administration"])
                    + float(row["supplies"])
                    + float(row["fees"])
                    + float(row["administration"])
                    + float(row["direct_taxes"])
                    + float(row["withheld"])
                )
                external = (
                    float(row["per_capita_tax"])
                    + float(row["affiliates"])
                    + float(row["investments"])
                    + float(row["loans_made"])
                    + float(row["loans_payment"])
                    + float(row["other_disbursements"])
                )
                total = organizing + compensation + benefits_members + administration + external

                years.append({
                    "year": row["year"],
                    "organizing": organizing,
                    "compensation": compensation,
                    "benefits_members": benefits_members,
                    "administration": administration,
                    "external": external,
                    "total": total,
                    "categories": {
                        "representational": float(row["representational"]),
                        "political": float(row["political"]),
                        "strike_benefits": float(row["strike_benefits"]),
                        "to_officers": float(row["to_officers"]),
                        "to_employees": float(row["to_employees"]),
                        "benefits": float(row["benefits"]),
                        "per_capita_tax": float(row["per_capita_tax"]),
                        "general_overhead": float(row["general_overhead"]),
                        "contributions": float(row["contributions"]),
                        "affiliates": float(row["affiliates"]),
                        "union_administration": float(row["union_administration"]),
                        "supplies": float(row["supplies"]),
                        "fees": float(row["fees"]),
                        "administration": float(row["administration"]),
                        "direct_taxes": float(row["direct_taxes"]),
                        "withheld": float(row["withheld"]),
                        "members": float(row["members"]),
                        "investments": float(row["investments"]),
                        "loans_made": float(row["loans_made"]),
                        "loans_payment": float(row["loans_payment"]),
                        "other_disbursements": float(row["other_disbursements"]),
                    },
                })

            has_strike_fund = False
            if years:
                has_strike_fund = years[0]["categories"]["strike_benefits"] > 0

            return {
                "file_number": file_number,
                "years": years,
                "has_strike_fund": has_strike_fund,
            }


@router.get("/api/unions/{file_number}/organizing-capacity")
def get_union_organizing_capacity(file_number: str):
    """Return latest organizing-spend share and recent membership trend for a union."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f_num, union_name FROM unions_master WHERE f_num = %s",
                [file_number],
            )
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            cur.execute(
                """
                WITH latest_year AS (
                    SELECT MAX(lm.yr_covered) AS reporting_year
                    FROM ar_disbursements_total adt
                    JOIN lm_data lm ON lm.rpt_id = adt.rpt_id
                    WHERE lm.f_num = %s
                )
                SELECT
                    ly.reporting_year,
                    SUM(
                        COALESCE(adt.representational, 0) +
                        COALESCE(adt.political, 0) +
                        COALESCE(adt.contributions, 0) +
                        COALESCE(adt.general_overhead, 0) +
                        COALESCE(adt.union_administration, 0) +
                        COALESCE(adt.withheld, 0) +
                        COALESCE(adt.members, 0) +
                        COALESCE(adt.supplies, 0) +
                        COALESCE(adt.fees, 0) +
                        COALESCE(adt.administration, 0) +
                        COALESCE(adt.direct_taxes, 0) +
                        COALESCE(adt.strike_benefits, 0) +
                        COALESCE(adt.per_capita_tax, 0) +
                        COALESCE(adt.to_officers, 0) +
                        COALESCE(adt.investments, 0) +
                        COALESCE(adt.benefits, 0) +
                        COALESCE(adt.loans_made, 0) +
                        COALESCE(adt.loans_payment, 0) +
                        COALESCE(adt.affiliates, 0) +
                        COALESCE(adt.other_disbursements, 0) +
                        COALESCE(adt.to_employees, 0)
                    ) AS total_disbursements,
                    SUM(COALESCE(adt.representational, 0) + COALESCE(adt.strike_benefits, 0)) AS organizing_disbursements
                FROM latest_year ly
                LEFT JOIN lm_data lm
                    ON lm.f_num = %s
                   AND lm.yr_covered = ly.reporting_year
                LEFT JOIN ar_disbursements_total adt
                    ON adt.rpt_id = lm.rpt_id
                GROUP BY ly.reporting_year
                """,
                [file_number, file_number],
            )
            spend_row = cur.fetchone() or {}

            trend_points = _get_membership_points(cur, file_number, years=3)
            membership_trend = _compute_trend_from_points(trend_points)

            total_disbursements = spend_row.get("total_disbursements")
            organizing_disbursements = spend_row.get("organizing_disbursements")
            organizing_spend_pct = None
            if total_disbursements and float(total_disbursements) > 0:
                organizing_spend_pct = round(
                    (float(organizing_disbursements or 0) / float(total_disbursements)) * 100.0, 2
                )

            return {
                "file_number": file_number,
                "union_name": union["union_name"],
                "reporting_year": spend_row.get("reporting_year"),
                "organizing_categories": list(ORGANIZING_DISBURSEMENT_FIELDS),
                "organizing_spend_pct": organizing_spend_pct,
                "total_disbursements": float(total_disbursements) if total_disbursements is not None else None,
                "organizing_disbursements": float(organizing_disbursements) if organizing_disbursements is not None else None,
                "membership_trend": membership_trend,
            }


@router.get("/api/unions/{file_number}/membership-history")
def get_union_membership_history(file_number: str):
    """Return last 10 years of membership and trend metrics for a union."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT f_num, union_name FROM unions_master WHERE f_num = %s",
                [file_number],
            )
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            history = _get_membership_points(cur, file_number, years=10)

            trend = _compute_trend_from_points(history)
            change_pct = None
            peak_year = None
            peak_members = None

            if history:
                peak = max(history, key=lambda p: p["members"])
                peak_year = peak["year"]
                peak_members = peak["members"]

            if len(history) >= 2 and history[0]["members"] > 0:
                change_pct = round(((history[-1]["members"] - history[0]["members"]) / history[0]["members"]) * 100.0, 2)

            return {
                "file_number": file_number,
                "union_name": union["union_name"],
                "history": history,
                "trend": trend,
                "change_pct": change_pct,
                "peak_year": peak_year,
                "peak_members": peak_members,
            }


def _compute_health_indicators(cur, f_num: str) -> dict:
    """Compute 4 sub-indicators + composite for union health."""

    # 1. Membership Trend (3-yr CAGR)
    membership_trend = None
    points = _get_membership_points(cur, f_num, years=4)
    if len(points) >= 2:
        first_val = points[0]["members"]
        last_val = points[-1]["members"]
        n_years = points[-1]["year"] - points[0]["year"]
        if first_val and first_val > 0 and n_years > 0:
            cagr = ((last_val / first_val) ** (1.0 / n_years) - 1) * 100
            # Map: >+5%=100, 0%=50, <-5%=0 (linear between)
            score = max(0, min(100, 50 + (cagr / 5) * 50))
            label = "Growing" if cagr > 2 else ("Stable" if cagr > -2 else "Declining")
            membership_trend = {
                "score": round(score, 1),
                "label": label,
                "cagr_pct": round(cagr, 2),
                "years": n_years,
            }

    # 2. Election Win Rate
    election_win_rate = None
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN e.union_won THEN 1 ELSE 0 END) as wins
        FROM nlrb_tallies t
        JOIN nlrb_elections e ON t.case_number = e.case_number
        WHERE t.matched_olms_fnum = %s AND e.union_won IS NOT NULL
    """, [f_num])
    row = cur.fetchone()
    if row and row["total"] and row["total"] >= 3:
        win_rate = row["wins"] / row["total"]
        election_win_rate = {
            "score": round(win_rate * 100, 1),
            "label": "Strong" if win_rate >= 0.7 else ("Moderate" if win_rate >= 0.4 else "Weak"),
            "wins": row["wins"],
            "total": row["total"],
        }

    # 3. Financial Stability (asset/liability ratio + receipts trend)
    financial_stability = None
    cur.execute("""
        SELECT yr_covered, ttl_assets, ttl_liabilities, ttl_receipts
        FROM lm_data
        WHERE f_num = %s AND ttl_assets IS NOT NULL
        ORDER BY yr_covered DESC
        LIMIT 3
    """, [f_num])
    fin_rows = cur.fetchall()
    if fin_rows:
        latest = fin_rows[0]
        assets = float(latest["ttl_assets"] or 0)
        liabilities = float(latest["ttl_liabilities"] or 1)
        if liabilities > 0:
            ratio = min(assets / liabilities, 10.0)
        else:
            ratio = 10.0
        # Map ratio 0-10 to score 0-100
        base_score = (ratio / 10.0) * 80
        # Receipts trend bonus (up to +20)
        bonus = 0
        if len(fin_rows) >= 2:
            r_latest = float(fin_rows[0]["ttl_receipts"] or 0)
            r_oldest = float(fin_rows[-1]["ttl_receipts"] or 0)
            if r_oldest > 0 and r_latest > r_oldest:
                bonus = min(20, ((r_latest - r_oldest) / r_oldest) * 100)
        score = min(100, base_score + bonus)
        label = "Strong" if score >= 70 else ("Stable" if score >= 40 else "Weak")
        financial_stability = {
            "score": round(score, 1),
            "label": label,
            "asset_liability_ratio": round(ratio, 2),
        }

    # 4. Organizing Activity (RC filings in last 3 years)
    organizing_activity = None
    cur.execute("""
        SELECT COUNT(DISTINCT c.case_number) as rc_count
        FROM nlrb_cases c
        JOIN nlrb_tallies t ON t.case_number = c.case_number
        WHERE c.case_type = 'RC'
          AND t.matched_olms_fnum = %s
          AND c.latest_date >= (CURRENT_DATE - INTERVAL '3 years')
    """, [f_num])
    rc_row = cur.fetchone()
    rc_count = rc_row["rc_count"] if rc_row else 0
    # Map: 0=0, 1=40, 2=60, 3=75, 5+=100
    rc_map = {0: 0, 1: 40, 2: 60, 3: 75, 4: 90}
    score = rc_map.get(rc_count, 100) if rc_count <= 4 else 100
    label = "Active" if score >= 60 else ("Some" if score >= 30 else "None")
    organizing_activity = {
        "score": score,
        "label": label,
        "rc_filings_3yr": rc_count,
    }

    # Composite
    indicators = [membership_trend, election_win_rate, financial_stability, organizing_activity]
    non_null = [ind for ind in indicators if ind is not None]
    if non_null:
        composite_score = sum(ind["score"] for ind in non_null) / len(non_null)
    else:
        composite_score = 0

    if composite_score >= 80:
        grade = "A"
    elif composite_score >= 60:
        grade = "B"
    elif composite_score >= 40:
        grade = "C"
    elif composite_score >= 20:
        grade = "D"
    else:
        grade = "F"

    return {
        "membership_trend": membership_trend,
        "election_win_rate": election_win_rate,
        "financial_stability": financial_stability,
        "organizing_activity": organizing_activity,
        "composite": {
            "score": round(composite_score, 1),
            "grade": grade,
            "indicators_available": len(non_null),
        },
    }


@router.get("/api/unions/{file_number}/health")
def get_union_health(file_number: str):
    """Composite health indicators for a union."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT f_num FROM unions_master WHERE f_num = %s", [file_number])
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Union not found")
            return _compute_health_indicators(cur, file_number)


@router.get("/api/unions/{f_num}")
def get_union_detail(f_num: str, consolidated: bool = True):
    """Get full union details including NLRB history.

    When consolidated=True (default), top_employers groups by canonical group,
    returning one row per group with canonical_name and consolidated_workers.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM unions_master WHERE f_num = %s", [f_num])
            union = cur.fetchone()

            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            # F-7 employers -- optionally consolidated
            if consolidated:
                cur.execute("""
                    SELECT
                        COALESCE(g.canonical_employer_id, e.employer_id) AS employer_id,
                        COALESCE(g.canonical_name, e.employer_name) AS employer_name,
                        e.city, e.state,
                        COALESCE(g.consolidated_workers, e.latest_unit_size) AS latest_unit_size,
                        g.group_id AS canonical_group_id,
                        g.member_count
                    FROM f7_employers_deduped e
                    LEFT JOIN employer_canonical_groups g ON e.canonical_group_id = g.group_id
                    WHERE e.latest_union_fnum = %s
                      AND (e.is_canonical_rep = TRUE OR e.canonical_group_id IS NULL)
                    ORDER BY COALESCE(g.consolidated_workers, e.latest_unit_size) DESC NULLS LAST
                    LIMIT 20
                """, [f_num])
            else:
                cur.execute("""
                    SELECT employer_id, employer_name, city, state, latest_unit_size
                    FROM f7_employers_deduped
                    WHERE latest_union_fnum = %s
                    ORDER BY latest_unit_size DESC NULLS LAST LIMIT 20
                """, [f_num])
            employers = cur.fetchall()

            # NLRB elections
            cur.execute("""
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                    e.vote_margin, p.participant_name as employer_name, p.state
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number
                    AND p.participant_type = 'Employer'
                WHERE t.matched_olms_fnum = %s
                ORDER BY e.election_date DESC
            """, [f_num])
            elections = cur.fetchall()

            # Financial trends (used by profile charts)
            cur.execute("""
                SELECT lm.yr_covered AS year,
                       SUM(am.number) FILTER (WHERE am.voting_eligibility = 'T') AS members,
                       SUM(COALESCE(lm.ttl_assets, 0)) AS assets,
                       SUM(COALESCE(lm.ttl_receipts, 0)) AS receipts
                FROM lm_data lm
                LEFT JOIN ar_membership am ON am.rpt_id = lm.rpt_id
                WHERE lm.f_num = %s
                GROUP BY lm.yr_covered
                ORDER BY lm.yr_covered DESC
                LIMIT 10
            """, [f_num])
            financial_trends = cur.fetchall()

            # Industry distribution based on covered workers.
            cur.execute("""
                SELECT LEFT(e.naics, 2) AS naics_2digit,
                       COALESCE(ns.sector_name, 'NAICS ' || LEFT(e.naics, 2)) AS sector_name,
                       SUM(COALESCE(e.latest_unit_size, 0)) AS workers
                FROM f7_employers_deduped e
                LEFT JOIN naics_sectors ns ON LEFT(e.naics, 2) = ns.naics_2digit
                WHERE e.latest_union_fnum = %s
                  AND e.naics IS NOT NULL
                GROUP BY LEFT(e.naics, 2), COALESCE(ns.sector_name, 'NAICS ' || LEFT(e.naics, 2))
                ORDER BY SUM(COALESCE(e.latest_unit_size, 0)) DESC
                LIMIT 10
            """, [f_num])
            industry_distribution = cur.fetchall()

            # Sister locals for same affiliation.
            sister_locals = []
            if union.get("aff_abbr"):
                cur.execute("""
                    SELECT f_num, union_name, local_number, desig_name, city, state,
                           members, f7_employer_count AS employer_count
                    FROM unions_master
                    WHERE aff_abbr = %s AND f_num <> %s
                    ORDER BY members DESC NULLS LAST
                    LIMIT 20
                """, [union["aff_abbr"], f_num])
                sister_locals = cur.fetchall()

            # Geographic distribution by state for covered workers.
            cur.execute("""
                SELECT state, SUM(COALESCE(latest_unit_size, 0)) AS workers
                FROM f7_employers_deduped
                WHERE latest_union_fnum = %s AND state IS NOT NULL
                GROUP BY state
                ORDER BY SUM(COALESCE(latest_unit_size, 0)) DESC
                LIMIT 15
            """, [f_num])
            geo_distribution = cur.fetchall()

            return {
                "union": union,
                "top_employers": employers,
                "nlrb_elections": elections,
                "financial_trends": financial_trends,
                "industry_distribution": industry_distribution,
                "sister_locals": sister_locals,
                "geo_distribution": geo_distribution,
                "nlrb_summary": {
                    "total_elections": len(elections),
                    "wins": sum(1 for e in elections if e['union_won']),
                    "losses": sum(1 for e in elections if e['union_won'] is False),
                    "win_rate": round(100.0 * sum(1 for e in elections if e['union_won']) / max(len(elections), 1), 1)
                }
            }


@router.get("/api/unions/{f_num}/employers")
def get_union_employers(
    f_num: str,
    consolidated: bool = True,
    limit: int = Query(50, le=200)
):
    """Get all employers for a specific union.

    When consolidated=True (default), groups by canonical group and returns
    canonical_group_id and member_count per employer row.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check union exists
            cur.execute("SELECT union_name, aff_abbr FROM unions_master WHERE f_num = %s", [f_num])
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            if consolidated:
                cur.execute("""
                    SELECT
                        COALESCE(g.canonical_employer_id, e.employer_id) AS employer_id,
                        COALESCE(g.canonical_name, e.employer_name) AS employer_name,
                        e.city, e.state, e.naics,
                        COALESCE(g.consolidated_workers, e.latest_unit_size) AS latest_unit_size,
                        e.latest_notice_date,
                        c.cbsa_title as metro_name,
                        g.group_id AS canonical_group_id,
                        g.member_count
                    FROM f7_employers_deduped e
                    LEFT JOIN employer_canonical_groups g ON e.canonical_group_id = g.group_id
                    LEFT JOIN cbsa_definitions c ON e.cbsa_code = c.cbsa_code
                    WHERE e.latest_union_fnum = %s
                      AND (e.is_canonical_rep = TRUE OR e.canonical_group_id IS NULL)
                    ORDER BY COALESCE(g.consolidated_workers, e.latest_unit_size) DESC NULLS LAST
                    LIMIT %s
                """, [f_num, limit])
            else:
                cur.execute("""
                    SELECT e.employer_id, e.employer_name, e.city, e.state, e.naics,
                           e.latest_unit_size, e.latest_notice_date,
                           c.cbsa_title as metro_name,
                           e.canonical_group_id,
                           COALESCE(g.member_count, 1) as member_count
                    FROM f7_employers_deduped e
                    LEFT JOIN employer_canonical_groups g ON e.canonical_group_id = g.group_id
                    LEFT JOIN cbsa_definitions c ON e.cbsa_code = c.cbsa_code
                    WHERE e.latest_union_fnum = %s
                    ORDER BY e.latest_unit_size DESC NULLS LAST
                    LIMIT %s
                """, [f_num, limit])
            employers = cur.fetchall()

            return {
                "union_name": union['union_name'],
                "aff_abbr": union['aff_abbr'],
                "total_employers": len(employers),
                "employers": employers
            }


@router.get("/api/unions/locals/{affiliation}")
def get_locals_for_affiliation(
    affiliation: str,
    state: Optional[str] = None,
    limit: int = Query(100, le=500)
):
    """Get local unions for a national affiliation"""
    with get_db() as conn:
        with conn.cursor() as cur:
            conditions = ["aff_abbr = %s"]
            params = [affiliation.upper()]

            if state:
                conditions.append("state = %s")
                params.append(state.upper())

            where_clause = " AND ".join(conditions)
            params.append(limit)

            cur.execute(f"""
                SELECT f_num, union_name, display_name, local_number, city, state, members, f7_employer_count
                FROM v_union_display_names
                WHERE {where_clause}
                ORDER BY members DESC NULLS LAST
                LIMIT %s
            """, params)

            return {"affiliation": affiliation, "locals": cur.fetchall()}
