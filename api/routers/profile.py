import logging
import re
from datetime import date as _date

from fastapi import APIRouter, HTTPException

from ..database import get_db
from ..helpers import TTLCache

_logger = logging.getLogger(__name__)

router = APIRouter()
_profile_cache = TTLCache(ttl_seconds=300)  # 5-minute cache per employer


def _get_nyc_enforcement(cur, employer: dict) -> dict:
    """On-the-fly name lookup against 3 small NYC/NYS enforcement tables."""
    employer_name = employer.get("employer_name", "")
    if not employer_name:
        return {"summary": {"record_count": 0, "is_debarred": False,
                            "debarment_end_date": None, "total_wages_owed": 0,
                            "total_recovered": 0}, "records": []}
    name_norm = employer_name.upper().strip()
    cur.execute("""
        SELECT 'debarment' AS source, employer_name, debarment_start_date,
               debarment_end_date, prosecuting_agency, NULL::numeric AS amount
        FROM nyc_debarment_list
        WHERE employer_name_normalized = %s
           OR employer_name_normalized LIKE '%%' || %s || '%%'
        UNION ALL
        SELECT 'local_labor_law', employer_name, closed_date, NULL,
               NULL, total_recovered
        FROM nyc_local_labor_laws
        WHERE employer_name_normalized = %s
           OR employer_name_normalized LIKE '%%' || %s || '%%'
        UNION ALL
        SELECT 'wage_theft_nys', employer_name, NULL, NULL,
               NULL, wages_owed
        FROM nyc_wage_theft_nys
        WHERE employer_name_normalized = %s
           OR employer_name_normalized LIKE '%%' || %s || '%%'
    """, [name_norm] * 6)
    rows = cur.fetchall()

    if not rows:
        return {"summary": {"record_count": 0, "is_debarred": False,
                            "debarment_end_date": None, "total_wages_owed": 0,
                            "total_recovered": 0}, "records": []}

    debarments = [r for r in rows if r["source"] == "debarment"]
    active_debarment_end = None
    is_debarred = False
    for d in debarments:
        end = d.get("debarment_end_date")
        if not end or end >= _date.today():
            is_debarred = True
            if end and (active_debarment_end is None or end > active_debarment_end):
                active_debarment_end = end

    total_wages_owed = sum(
        float(r["amount"] or 0) for r in rows if r["source"] == "wage_theft_nys"
    )
    total_recovered = sum(
        float(r["amount"] or 0) for r in rows if r["source"] == "local_labor_law"
    )

    return {
        "summary": {
            "record_count": len(rows),
            "is_debarred": is_debarred,
            "debarment_end_date": str(active_debarment_end) if active_debarment_end else None,
            "total_wages_owed": total_wages_owed,
            "total_recovered": total_recovered,
        },
        "records": [dict(r) for r in rows[:20]],
    }


def _get_nlrb_docket_summary(cur, f7_id: str) -> dict:
    """Aggregate docket activity for an employer's NLRB cases."""
    cur.execute(
        """
        SELECT d.case_number,
               MIN(d.docket_date) AS first_activity,
               MAX(d.docket_date) AS last_activity,
               COUNT(*) AS entry_count,
               MAX(d.docket_date) >= CURRENT_DATE - INTERVAL '90 days' AS is_recent
        FROM nlrb_docket d
        JOIN nlrb_participants p ON d.case_number = p.case_number
            AND p.participant_type = 'Employer'
        WHERE p.matched_employer_id::text = %s
        GROUP BY d.case_number
        ORDER BY MAX(d.docket_date) DESC NULLS LAST
        LIMIT 20
        """,
        [f7_id],
    )
    rows = cur.fetchall()

    if not rows:
        return {
            "summary": {
                "cases_with_docket": 0,
                "total_entries": 0,
                "has_recent_activity": False,
                "most_recent_date": None,
            },
            "cases": [],
        }

    total_entries = sum(r["entry_count"] for r in rows)
    has_recent = any(r["is_recent"] for r in rows)
    most_recent = rows[0]["last_activity"]

    cases = []
    for r in rows:
        first = r["first_activity"]
        last = r["last_activity"]
        duration = (last - first).days if first and last else None
        cases.append({
            "case_number": r["case_number"],
            "first_activity": str(first) if first else None,
            "last_activity": str(last) if last else None,
            "entry_count": r["entry_count"],
            "is_recent": bool(r["is_recent"]),
            "duration_days": duration,
        })

    return {
        "summary": {
            "cases_with_docket": len(rows),
            "total_entries": total_entries,
            "has_recent_activity": has_recent,
            "most_recent_date": str(most_recent) if most_recent else None,
        },
        "cases": cases,
    }


@router.get("/api/profile/employers/{employer_id}")
def get_employer_profile(employer_id: str):
    """Canonical employer profile payload for frontend detail rendering."""
    cached = _profile_cache.get(f"profile:{employer_id}")
    if cached is not None:
        return cached
    with get_db() as conn:
        with conn.cursor() as cur:
            # Prefer F7 ID exact match, then canonical-id lookup from unified search MV.
            cur.execute(
                """
                SELECT employer_id::text AS f7_employer_id
                FROM f7_employers_deduped
                WHERE employer_id::text = %s
                LIMIT 1
                """,
                [employer_id],
            )
            row = cur.fetchone()

            if not row:
                cur.execute(
                    """
                    SELECT employer_id::text AS f7_employer_id
                    FROM mv_employer_search
                    WHERE canonical_id = %s AND source_type = 'F7'
                    LIMIT 1
                    """,
                    [employer_id],
                )
                row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Employer not found")

            f7_id = row["f7_employer_id"]

            cur.execute(
                """
                SELECT e.*, um.aff_abbr, um.union_name AS union_full_name
                FROM f7_employers_deduped e
                LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num
                WHERE e.employer_id::text = %s
                """,
                [f7_id],
            )
            employer = cur.fetchone()
            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            # Unified scoring context (single frontend scorecard source).
            cur.execute(
                """
                SELECT *
                FROM mv_unified_scorecard
                WHERE employer_id::text = %s
                LIMIT 1
                """,
                [f7_id],
            )
            unified_scorecard = cur.fetchone()
            if unified_scorecard:
                unified_scorecard["weighted_score"] = unified_scorecard.get(
                    "weighted_score", unified_scorecard.get("unified_score")
                )
                unified_scorecard["unified_score"] = unified_scorecard.get(
                    "unified_score", unified_scorecard.get("weighted_score")
                )
                unified_scorecard["legacy_score_tier"] = unified_scorecard.get("score_tier_legacy")

            cur.execute(
                """
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                       e.vote_margin, t.labor_org_name AS union_name, um.aff_abbr
                FROM nlrb_elections e
                JOIN nlrb_participants p ON e.case_number = p.case_number
                    AND p.participant_type = 'Employer'
                LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                LEFT JOIN unions_master um ON t.matched_olms_fnum = um.f_num
                WHERE p.matched_employer_id::text = %s
                ORDER BY e.election_date DESC
                LIMIT 50
                """,
                [f7_id],
            )
            nlrb_elections = cur.fetchall()

            cur.execute(
                """
                SELECT c.case_number, c.case_type, c.earliest_date, c.latest_date,
                       ct.description AS case_type_desc
                FROM nlrb_cases c
                JOIN nlrb_case_types ct ON c.case_type = ct.case_type
                JOIN nlrb_participants p ON c.case_number = p.case_number
                    AND p.participant_type = 'Charged Party'
                WHERE p.matched_employer_id::text = %s
                  AND ct.case_category = 'unfair_labor_practice'
                ORDER BY c.earliest_date DESC
                LIMIT 50
                """,
                [f7_id],
            )
            ulp_cases = cur.fetchall()

            cur.execute(
                """
                SELECT o.establishment_id, o.estab_name, o.site_city, o.site_state,
                       o.total_inspections, o.last_inspection_date,
                       COALESCE(vs.total_violations, 0) AS total_violations,
                       COALESCE(vs.total_penalties, 0) AS total_penalties,
                       COALESCE(vs.serious_count, 0) AS serious_count,
                       COALESCE(vs.willful_count, 0) AS willful_count,
                       COALESCE(vs.repeat_count, 0) AS repeat_count,
                       COALESCE(m.score_eligible, TRUE) AS score_eligible,
                       m.match_method, m.match_confidence
                FROM osha_f7_matches m
                JOIN osha_establishments o ON m.establishment_id = o.establishment_id
                LEFT JOIN (
                    SELECT establishment_id,
                           SUM(violation_count) AS total_violations,
                           SUM(total_penalties) AS total_penalties,
                           SUM(CASE WHEN violation_type = 'S' THEN violation_count ELSE 0 END) AS serious_count,
                           SUM(CASE WHEN violation_type = 'W' THEN violation_count ELSE 0 END) AS willful_count,
                           SUM(CASE WHEN violation_type = 'R' THEN violation_count ELSE 0 END) AS repeat_count
                    FROM osha_violation_summary
                    GROUP BY establishment_id
                ) vs ON vs.establishment_id = o.establishment_id
                WHERE m.f7_employer_id::text = %s
                ORDER BY COALESCE(vs.total_penalties, 0) DESC
                LIMIT 25
                """,
                [f7_id],
            )
            osha_establishments = cur.fetchall()

            osha_summary = {
                "total_establishments": len(osha_establishments),
                "total_inspections": sum(e["total_inspections"] or 0 for e in osha_establishments),
                "total_violations": sum(e["total_violations"] or 0 for e in osha_establishments),
                "total_penalties": float(sum(float(e["total_penalties"] or 0) for e in osha_establishments)),
                "serious_violations": sum(e["serious_count"] or 0 for e in osha_establishments),
                "willful_violations": sum(e["willful_count"] or 0 for e in osha_establishments),
                "repeat_violations": sum(e["repeat_count"] or 0 for e in osha_establishments),
            }

            cur.execute(
                """
                SELECT source_type, source_id, employer_name, city, state, case_number,
                       election_date, unit_size, election_result, union_name, confidence_band
                FROM (
                    SELECT 'NLRB'::text AS source_type, p.id::text AS source_id,
                           p.participant_name AS employer_name, p.city, p.state, p.case_number,
                           e.election_date::text AS election_date, e.eligible_voters AS unit_size,
                           CASE WHEN e.union_won THEN 'Won' ELSE 'Lost' END AS election_result,
                           t.labor_org_name AS union_name, NULL::text AS confidence_band
                    FROM nlrb_participants p
                    LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
                    LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
                    WHERE p.matched_employer_id::text = %s
                      AND p.participant_type = 'Employer'
                    UNION ALL
                    SELECT 'VR'::text AS source_type, vr.vr_case_number::text AS source_id,
                           vr.employer_name, vr.unit_city AS city, vr.unit_state AS state,
                           vr.vr_case_number AS case_number,
                           vr.date_voluntary_recognition::text AS election_date,
                           vr.num_employees AS unit_size,
                           'Vol. Recognition'::text AS election_result,
                           vr.union_name, NULL::text AS confidence_band
                    FROM nlrb_voluntary_recognition vr
                    WHERE vr.matched_employer_id::text = %s
                ) x
                ORDER BY election_date DESC NULLS LAST
                LIMIT 40
                """,
                [f7_id, f7_id],
            )
            cross_references = cur.fetchall()

            cur.execute(
                """
                SELECT source_count
                FROM mv_employer_data_sources
                WHERE employer_id::text = %s
                LIMIT 1
                """,
                [f7_id],
            )
            ds_row = cur.fetchone()
            external_source_count = ds_row["source_count"] if ds_row else 0

            cur.execute(
                """
                SELECT id, flag_type, notes, created_at
                FROM employer_review_flags
                WHERE source_type = 'F7' AND source_id = %s
                ORDER BY created_at DESC
                """,
                [f7_id],
            )
            flags = cur.fetchall()

            # Check if this employer is union (F7) or non-union
            is_union = bool(employer.get("is_union", True))

            result = {
                "employer": employer,
                "is_union_reference": is_union,
                "unified_scorecard": unified_scorecard if is_union else None,
                "data_coverage": {
                    "external_source_count": external_source_count,
                    "factors_available": unified_scorecard.get("factors_available", 0) if unified_scorecard else 0,
                    "factors_total": unified_scorecard.get("factors_total", 8) if unified_scorecard else 8,
                    "label": (
                        "Reference data (union employer)"
                        if is_union
                        else f"Signal inventory ({external_source_count} data sources)"
                    ),
                },
                "osha": {
                    "summary": osha_summary,
                    "establishments": osha_establishments,
                },
                "nlrb": {
                    "elections": nlrb_elections,
                    "ulp_cases": ulp_cases,
                    "summary": {
                        "total_elections": len(nlrb_elections),
                        "union_wins": sum(1 for r in nlrb_elections if r.get("union_won") is True),
                        "union_losses": sum(1 for r in nlrb_elections if r.get("union_won") is False),
                        "ulp_cases": len(ulp_cases),
                    },
                },
                "cross_references": cross_references,
                "flags": flags,
                "nyc_enforcement": _get_nyc_enforcement(cur, employer),
                "nlrb_docket": _get_nlrb_docket_summary(cur, f7_id),
            }
            _profile_cache.set(f"profile:{employer_id}", result)
            return result


@router.get("/api/profile/unions/{f_num}")
def get_union_profile(f_num: str):
    """Canonical union profile payload for frontend detail rendering."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM unions_master WHERE f_num = %s", [f_num])
            union = cur.fetchone()
            if not union:
                raise HTTPException(status_code=404, detail="Union not found")

            cur.execute(
                """
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
                LIMIT 25
                """,
                [f_num],
            )
            top_employers = cur.fetchall()

            cur.execute(
                """
                SELECT e.case_number, e.election_date, e.union_won, e.eligible_voters,
                       e.vote_margin, p.participant_name AS employer_name, p.state
                FROM nlrb_tallies t
                JOIN nlrb_elections e ON t.case_number = e.case_number
                LEFT JOIN nlrb_participants p ON e.case_number = p.case_number
                    AND p.participant_type = 'Employer'
                WHERE t.matched_olms_fnum = %s
                ORDER BY e.election_date DESC
                LIMIT 100
                """,
                [f_num],
            )
            nlrb_elections = cur.fetchall()

            cur.execute(
                """
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
                """,
                [f_num],
            )
            financial_trends = cur.fetchall()

            cur.execute(
                """
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
                """,
                [f_num],
            )
            industry_distribution = cur.fetchall()

            aff = union.get("aff_abbr")
            sister_locals = []
            if aff:
                cur.execute(
                    """
                    SELECT f_num, union_name, local_number, desig_name, city, state,
                           members, f7_employer_count AS employer_count
                    FROM unions_master
                    WHERE aff_abbr = %s AND f_num <> %s
                    ORDER BY members DESC NULLS LAST
                    LIMIT 20
                    """,
                    [aff, f_num],
                )
                sister_locals = cur.fetchall()

            cur.execute(
                """
                SELECT state, SUM(COALESCE(latest_unit_size, 0)) AS workers
                FROM f7_employers_deduped
                WHERE latest_union_fnum = %s AND state IS NOT NULL
                GROUP BY state
                ORDER BY SUM(COALESCE(latest_unit_size, 0)) DESC
                LIMIT 15
                """,
                [f_num],
            )
            geo_distribution = cur.fetchall()

            return {
                "union": union,
                "top_employers": top_employers,
                "nlrb_elections": nlrb_elections,
                "nlrb_summary": {
                    "total_elections": len(nlrb_elections),
                    "wins": sum(1 for e in nlrb_elections if e.get("union_won") is True),
                    "losses": sum(1 for e in nlrb_elections if e.get("union_won") is False),
                    "win_rate": round(
                        100.0
                        * sum(1 for e in nlrb_elections if e.get("union_won") is True)
                        / max(len(nlrb_elections), 1),
                        1,
                    ),
                },
                "financial_trends": financial_trends,
                "industry_distribution": industry_distribution,
                "sister_locals": sister_locals,
                "geo_distribution": geo_distribution,
            }


def _onet_tables_exist(cur) -> bool:
    """Check if O*NET tables are available."""
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name IN ('onet_skills', 'onet_knowledge', 'onet_work_context', 'onet_job_zones')
    """)
    return cur.fetchone()["count"] >= 3


def _enrich_occupations_onet(cur, occupations: list):
    """Add O*NET skills, knowledge, work context, and job zone to each occupation."""
    if not occupations:
        return
    try:
        if not _onet_tables_exist(cur):
            return
    except Exception:
        return

    # Collect SOC codes and look up O*NET data
    # O*NET uses 10-char (e.g. 29-1141.00), BLS uses 7-char (e.g. 29-1141)
    soc_codes = [occ["occupation_code"] for occ in occupations if occ.get("occupation_code")]
    if not soc_codes:
        return

    # Build SOC prefix patterns for matching
    soc_patterns = [code + "%" for code in soc_codes]

    # Top 5 skills (by importance, scale_id='IM') per occupation
    try:
        cur.execute("""
            SELECT LEFT(s.onetsoc_code, 7) AS soc7,
                   cm.element_name AS skill_name,
                   s.data_value AS importance
            FROM onet_skills s
            JOIN onet_content_model cm ON s.element_id = cm.element_id
            WHERE s.scale_id = 'IM'
              AND LEFT(s.onetsoc_code, 7) = ANY(%s)
            ORDER BY LEFT(s.onetsoc_code, 7), s.data_value DESC
        """, [soc_codes])

        skills_by_soc = {}
        for r in cur.fetchall():
            soc = r["soc7"]
            if soc not in skills_by_soc:
                skills_by_soc[soc] = []
            if len(skills_by_soc[soc]) < 5:
                skills_by_soc[soc].append({
                    "name": r["skill_name"],
                    "importance": float(r["importance"]) if r["importance"] else None,
                })
    except Exception:
        skills_by_soc = {}

    # Top 3 knowledge domains per occupation
    try:
        cur.execute("""
            SELECT LEFT(k.onetsoc_code, 7) AS soc7,
                   cm.element_name AS knowledge_name,
                   k.data_value AS importance
            FROM onet_knowledge k
            JOIN onet_content_model cm ON k.element_id = cm.element_id
            WHERE k.scale_id = 'IM'
              AND LEFT(k.onetsoc_code, 7) = ANY(%s)
            ORDER BY LEFT(k.onetsoc_code, 7), k.data_value DESC
        """, [soc_codes])

        knowledge_by_soc = {}
        for r in cur.fetchall():
            soc = r["soc7"]
            if soc not in knowledge_by_soc:
                knowledge_by_soc[soc] = []
            if len(knowledge_by_soc[soc]) < 3:
                knowledge_by_soc[soc].append({
                    "name": r["knowledge_name"],
                    "importance": float(r["importance"]) if r["importance"] else None,
                })
    except Exception:
        knowledge_by_soc = {}

    # Top 3 work context items per occupation
    try:
        cur.execute("""
            SELECT LEFT(wc.onetsoc_code, 7) AS soc7,
                   cm.element_name AS context_name,
                   wc.data_value AS value
            FROM onet_work_context wc
            JOIN onet_content_model cm ON wc.element_id = cm.element_id
            WHERE wc.scale_id = 'CX'
              AND LEFT(wc.onetsoc_code, 7) = ANY(%s)
            ORDER BY LEFT(wc.onetsoc_code, 7), wc.data_value DESC
        """, [soc_codes])

        context_by_soc = {}
        for r in cur.fetchall():
            soc = r["soc7"]
            if soc not in context_by_soc:
                context_by_soc[soc] = []
            if len(context_by_soc[soc]) < 3:
                context_by_soc[soc].append({
                    "name": r["context_name"],
                    "value": float(r["value"]) if r["value"] else None,
                })
    except Exception:
        context_by_soc = {}

    # Job zones
    try:
        cur.execute("""
            SELECT LEFT(jz.onetsoc_code, 7) AS soc7,
                   jz.job_zone
            FROM onet_job_zones jz
            WHERE LEFT(jz.onetsoc_code, 7) = ANY(%s)
        """, [soc_codes])

        job_zone_by_soc = {}
        for r in cur.fetchall():
            job_zone_by_soc[r["soc7"]] = r["job_zone"]
    except Exception:
        job_zone_by_soc = {}

    # Attach to occupation dicts
    for occ in occupations:
        soc = occ.get("occupation_code", "")
        occ["top_skills"] = skills_by_soc.get(soc, [])
        occ["top_knowledge"] = knowledge_by_soc.get(soc, [])
        occ["top_work_context"] = context_by_soc.get(soc, [])
        occ["job_zone"] = job_zone_by_soc.get(soc)


@router.get("/api/profile/employers/{employer_id}/occupations")
def get_employer_occupations(employer_id: str):
    """Top BLS occupations and similar industries for an employer's NAICS."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Verify employer exists
            cur.execute(
                """
                SELECT employer_id, naics, naics_detailed
                FROM f7_employers_deduped
                WHERE employer_id::text = %s
                LIMIT 1
                """,
                [employer_id],
            )
            employer = cur.fetchone()
            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            raw_naics = (employer.get("naics_detailed") or employer.get("naics") or "").strip()
            naics_code = re.sub(r"[^0-9]", "", raw_naics)

            if not naics_code:
                return {
                    "employer_naics": None,
                    "top_occupations": [],
                    "similar_industries": [],
                }

            # Try progressively shorter NAICS prefixes for BLS match
            top_occupations = []
            matched_prefix = None
            for length in range(len(naics_code), 1, -1):
                prefix = naics_code[:length]
                cur.execute(
                    """
                    SELECT DISTINCT ON (bm.occupation_code)
                           bm.occupation_code, bm.occupation_title,
                           bm.employment_2024, bm.employment_change_pct
                    FROM bls_industry_occupation_matrix bm
                    WHERE bm.industry_code LIKE %s
                      AND bm.occupation_type = 'Line Item'
                    ORDER BY bm.occupation_code, bm.employment_2024 DESC NULLS LAST
                    """,
                    [prefix + "%"],
                )
                rows = cur.fetchall()
                if rows:
                    matched_prefix = prefix
                    # Sort by employment descending, take top 15
                    rows.sort(
                        key=lambda r: float(r["employment_2024"] or 0),
                        reverse=True,
                    )
                    top_occupations = [
                        {
                            "occupation_code": r["occupation_code"],
                            "occupation_title": r["occupation_title"],
                            "employment_2024": (
                                float(r["employment_2024"])
                                if r["employment_2024"] is not None
                                else None
                            ),
                            "employment_change_pct": (
                                float(r["employment_change_pct"])
                                if r["employment_change_pct"] is not None
                                else None
                            ),
                        }
                        for r in rows[:15]
                    ]
                    break

            # Find similar industries via overlap table
            similar_industries = []
            if matched_prefix:
                cur.execute(
                    """
                    SELECT io.industry_code_b AS similar_industry,
                           io.overlap_score, io.shared_occupations
                    FROM industry_occupation_overlap io
                    WHERE io.industry_code_a = %s
                    ORDER BY io.overlap_score DESC
                    LIMIT 10
                    """,
                    [matched_prefix],
                )
                similar_industries = [
                    {
                        "similar_industry": r["similar_industry"],
                        "overlap_score": (
                            float(r["overlap_score"])
                            if r["overlap_score"] is not None
                            else None
                        ),
                        "shared_occupations": (
                            r["shared_occupations"]
                            if r["shared_occupations"] is not None
                            else 0
                        ),
                    }
                    for r in cur.fetchall()
                ]

            # Enrich occupations with O*NET data if tables exist
            _enrich_occupations_onet(cur, top_occupations)

            return {
                "employer_naics": naics_code,
                "top_occupations": top_occupations,
                "similar_industries": similar_industries,
            }


@router.get("/api/profile/employers/{employer_id}/workplace-demographics")
def get_employer_workplace_demographics(employer_id: str):
    """County-level workplace demographics from LODES WAC data."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get employer ZIP code
            cur.execute("""
                SELECT employer_id, zip, state, city
                FROM f7_employers_deduped
                WHERE employer_id::text = %s
                LIMIT 1
            """, [employer_id])
            employer = cur.fetchone()
            if not employer:
                raise HTTPException(status_code=404, detail="Employer not found")

            zip_code = (employer.get("zip") or "").strip()[:5]
            if not zip_code or len(zip_code) < 5:
                return {"available": False, "reason": "No ZIP code for employer"}

            # Look up county FIPS via crosswalk
            cur.execute("""
                SELECT county_fips FROM zip_county_crosswalk
                WHERE zip_code = %s LIMIT 1
            """, [zip_code])
            xwalk = cur.fetchone()
            if not xwalk:
                return {"available": False, "reason": f"No county mapping for ZIP {zip_code}"}

            county_fips = xwalk["county_fips"]

            # Check if LODES demographics exist
            cur.execute("""
                SELECT * FROM cur_lodes_geo_metrics
                WHERE county_fips = %s LIMIT 1
            """, [county_fips])
            lodes = cur.fetchone()
            if not lodes or lodes.get("jobs_white") is None:
                return {"available": False, "reason": "No LODES data for county"}

            demo_total = lodes.get("demo_total_jobs") or lodes.get("total_jobs") or 0

            return {
                "available": True,
                "source": "LODES 2022 (Census Bureau)",
                "geography": "County",
                "county_fips": county_fips,
                "total_jobs": demo_total,
                "gender": {
                    "male": lodes.get("jobs_male"),
                    "female": lodes.get("jobs_female"),
                    "pct_female": float(lodes["pct_female"]) if lodes.get("pct_female") else None,
                },
                "race": {
                    "white": lodes.get("jobs_white"),
                    "black": lodes.get("jobs_black"),
                    "native": lodes.get("jobs_native"),
                    "asian": lodes.get("jobs_asian"),
                    "pacific": lodes.get("jobs_pacific"),
                    "two_plus": lodes.get("jobs_two_plus_races"),
                    "pct_minority": float(lodes["pct_minority"]) if lodes.get("pct_minority") else None,
                },
                "ethnicity": {
                    "not_hispanic": lodes.get("jobs_not_hispanic"),
                    "hispanic": lodes.get("jobs_hispanic"),
                    "pct_hispanic": float(lodes["pct_hispanic"]) if lodes.get("pct_hispanic") else None,
                },
                "education": {
                    "less_than_hs": lodes.get("jobs_edu_less_than_hs"),
                    "hs": lodes.get("jobs_edu_hs"),
                    "some_college": lodes.get("jobs_edu_some_college"),
                    "bachelors_plus": lodes.get("jobs_edu_bachelors_plus"),
                    "pct_bachelors_plus": float(lodes["pct_bachelors_plus"]) if lodes.get("pct_bachelors_plus") else None,
                },
            }


# ---------------------------------------------------------------------------
# Workforce Profile -- unified demographic + labor-market context endpoint
# ---------------------------------------------------------------------------

_SEX_LABELS = {"1": "Male", "2": "Female"}
_RACE_LABELS = {
    "1": "White", "2": "Black/African American",
    "3": "American Indian/Alaska Native",
    "4": "Chinese", "5": "Japanese",
    "6": "Other Asian/Pacific Islander",
    "7": "Other race", "8": "Two major races",
    "9": "Three or more races",
}
_RACE_CONSOLIDATED = {
    "1": "White", "2": "Black/African American",
    "3": "American Indian/Alaska Native",
    "4": "Asian/Pacific Islander", "5": "Asian/Pacific Islander",
    "6": "Asian/Pacific Islander",
    "7": "Other", "8": "Two or more", "9": "Two or more",
}
_AGE_LABELS = {
    "u25": "Under 25", "25_34": "25-34", "35_44": "35-44",
    "45_54": "45-54", "55_64": "55-64", "65p": "65+",
}
_HISP_LABELS = {"0": "Not Hispanic/Latino", "1": "Hispanic/Latino",
                 "2": "Hispanic/Latino", "3": "Hispanic/Latino", "4": "Hispanic/Latino"}
_EDU_GROUPS = {
    "No HS diploma": ["00", "01", "02", "03", "04", "05", "06", "07"],
    "HS diploma/GED": ["08"],
    "Some college/Associate's": ["10", "11"],
    "Bachelor's": ["12"],
    "Graduate/Professional": ["13", "14", "15"],
}


def _pct(num, denom):
    if not denom or not num:
        return 0.0
    return round(float(num) / float(denom) * 100, 1)


def _float(v):
    if v is None:
        return None
    return float(v)


def _get_employer_basics(cur, employer_id: str):
    """Get employer basics: state, zip, naics, city."""
    cur.execute("""
        SELECT employer_id, employer_name, state, city, zip,
               naics, naics_detailed, latest_unit_size
        FROM f7_employers_deduped
        WHERE employer_id::text = %s LIMIT 1
    """, [employer_id])
    return cur.fetchone()


def _get_county_fips(cur, zip_code: str):
    if not zip_code or len(zip_code) < 5:
        return None
    cur.execute(
        "SELECT county_fips FROM zip_county_crosswalk WHERE zip_code = %s LIMIT 1",
        [zip_code[:5]],
    )
    row = cur.fetchone()
    return row["county_fips"] if row else None


def _get_state_fips(cur, state: str):
    cur.execute(
        "SELECT state_fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1",
        [state.upper()],
    )
    row = cur.fetchone()
    return row["state_fips"] if row else None


def _get_acs_demographics(cur, state_fips: str, naics_code: str):
    """ACS industry x state demographics with NAICS fallback."""
    naics4 = (naics_code or "")[:4]
    # Try exact 4-digit, then LIKE 2-digit prefix, then state-wide
    candidates = []
    if len(naics4) >= 4:
        candidates.append(("exact", naics4))
    if len(naics4) >= 2:
        candidates.append(("prefix", naics4[:2]))
    candidates.append(("state", None))

    for match_type, prefix in candidates:
        where = ["state_fips = %s"]
        params = [state_fips]
        level = "industry"
        if match_type == "exact":
            where.append("naics4 = %s")
            params.append(prefix)
        elif match_type == "prefix":
            where.append("naics4 LIKE %s")
            params.append(prefix + "%")
            level = "industry_broad"
        else:
            level = "state"

        cur.execute(f"""
            SELECT COALESCE(SUM(weighted_workers), 0) AS total
            FROM cur_acs_workforce_demographics WHERE {' AND '.join(where)}
        """, params)
        total = float(cur.fetchone()["total"])
        if total == 0:
            continue

        # Gender
        cur.execute(f"""
            SELECT sex, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics WHERE {' AND '.join(where)}
            GROUP BY sex ORDER BY w DESC
        """, params)
        gender = [{"label": _SEX_LABELS.get(r["sex"], r["sex"]),
                    "pct": _pct(r["w"], total)} for r in cur.fetchall()]

        # Race (consolidated)
        cur.execute(f"""
            SELECT race, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics WHERE {' AND '.join(where)}
            GROUP BY race ORDER BY w DESC
        """, params)
        race_raw = {}
        for r in cur.fetchall():
            label = _RACE_CONSOLIDATED.get(r["race"], "Other")
            race_raw[label] = race_raw.get(label, 0) + float(r["w"])
        race = [{"label": k, "pct": _pct(v, total)}
                for k, v in sorted(race_raw.items(), key=lambda x: -x[1])]

        # Hispanic (consolidate codes 1-4 into Hispanic/Latino)
        cur.execute(f"""
            SELECT CASE WHEN hispanic = '0' THEN '0' ELSE '1' END AS hisp_group,
                   SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics WHERE {' AND '.join(where)}
            GROUP BY hisp_group ORDER BY w DESC
        """, params)
        hispanic = [{"label": _HISP_LABELS.get(r["hisp_group"], r["hisp_group"]),
                      "pct": _pct(r["w"], total)} for r in cur.fetchall()]

        # Age
        cur.execute(f"""
            SELECT age_bucket, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics WHERE {' AND '.join(where)}
            GROUP BY age_bucket ORDER BY age_bucket
        """, params)
        age_raw = {r["age_bucket"]: float(r["w"]) for r in cur.fetchall()}
        age = [{"label": _AGE_LABELS.get(k, k), "pct": _pct(age_raw.get(k, 0), total)}
               for k in ["u25", "25_34", "35_44", "45_54", "55_64", "65p"] if k in age_raw]

        # Education
        cur.execute(f"""
            SELECT education, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics WHERE {' AND '.join(where)}
            GROUP BY education
        """, params)
        educ_raw = {r["education"]: float(r["w"]) for r in cur.fetchall()}
        education = []
        for grp, codes in _EDU_GROUPS.items():
            s = sum(educ_raw.get(c, 0) for c in codes)
            if s > 0:
                education.append({"label": grp, "pct": _pct(s, total)})

        return {
            "source": "ACS (Census Bureau)",
            "level": level,
            "naics_matched": prefix,
            "total_workers": round(total),
            "gender": gender,
            "race": race,
            "hispanic": hispanic,
            "age": age,
            "education": education,
        }
    return None


def _get_lodes_demographics(cur, county_fips: str):
    """LODES county-level demographics."""
    cur.execute("SELECT * FROM cur_lodes_geo_metrics WHERE county_fips = %s LIMIT 1",
                [county_fips])
    lodes = cur.fetchone()
    if not lodes or lodes.get("jobs_white") is None:
        return None

    # Demographics (gender, race, education, ethnicity) use demo_total_jobs
    demo_total = float(lodes.get("demo_total_jobs") or 0)
    # Age and earnings use total_jobs (different LODES table)
    age_total = float(lodes.get("total_jobs") or 0)
    if demo_total == 0:
        return None

    return {
        "source": "LODES 2022 (Census Bureau)",
        "county_fips": county_fips,
        "total_jobs": round(age_total),
        "demo_total_jobs": round(demo_total),
        "gender": [
            {"label": "Male", "pct": _pct(lodes.get("jobs_male"), demo_total)},
            {"label": "Female", "pct": _pct(lodes.get("jobs_female"), demo_total)},
        ],
        "race": [
            {"label": "White", "pct": _pct(lodes.get("jobs_white"), demo_total)},
            {"label": "Black/African American", "pct": _pct(lodes.get("jobs_black"), demo_total)},
            {"label": "Asian/Pacific Islander", "pct": _pct(
                (lodes.get("jobs_asian") or 0) + (lodes.get("jobs_pacific") or 0), demo_total)},
            {"label": "American Indian/Alaska Native", "pct": _pct(lodes.get("jobs_native"), demo_total)},
            {"label": "Two or more", "pct": _pct(lodes.get("jobs_two_plus_races"), demo_total)},
        ],
        "hispanic": [
            {"label": "Not Hispanic/Latino", "pct": _pct(lodes.get("jobs_not_hispanic"), demo_total)},
            {"label": "Hispanic/Latino", "pct": _pct(lodes.get("jobs_hispanic"), demo_total)},
        ],
        "age": [
            {"label": "29 or younger", "pct": _pct(lodes.get("jobs_age_29_or_younger"), age_total)},
            {"label": "30-54", "pct": _pct(lodes.get("jobs_age_30_to_54"), age_total)},
            {"label": "55+", "pct": _pct(lodes.get("jobs_age_55_plus"), age_total)},
        ],
        "education": [
            {"label": "No HS diploma", "pct": _pct(lodes.get("jobs_edu_less_than_hs"), demo_total)},
            {"label": "HS diploma/GED", "pct": _pct(lodes.get("jobs_edu_hs"), demo_total)},
            {"label": "Some college/Associate's", "pct": _pct(lodes.get("jobs_edu_some_college"), demo_total)},
            {"label": "Bachelor's+", "pct": _pct(lodes.get("jobs_edu_bachelors_plus"), demo_total)},
        ],
    }


def _get_tract_demographics(cur, employer_id: str):
    """Census tract-level neighborhood demographics from ACS."""
    cur.execute("""
        SELECT e.census_tract, t.*
        FROM f7_employers_deduped e
        LEFT JOIN acs_tract_demographics t ON t.tract_fips = e.census_tract
        WHERE e.employer_id::text = %s AND e.census_tract IS NOT NULL
        LIMIT 1
    """, [employer_id])
    row = cur.fetchone()
    if not row or not row.get("tract_fips"):
        return None

    total_pop = float(row.get("total_population") or 0)
    pop_25plus = float(row.get("pop_25plus") or 0)

    gender = []
    if total_pop > 0:
        gender = [
            {"label": "Male", "pct": _pct(row.get("pop_male"), total_pop)},
            {"label": "Female", "pct": _pct(row.get("pop_female"), total_pop)},
        ]

    race = []
    if total_pop > 0:
        race = [
            {"label": "White", "pct": _pct(row.get("pop_white"), total_pop)},
            {"label": "Black/African American", "pct": _pct(row.get("pop_black"), total_pop)},
            {"label": "Asian", "pct": _pct(row.get("pop_asian"), total_pop)},
            {"label": "American Indian/Alaska Native", "pct": _pct(row.get("pop_aian"), total_pop)},
            {"label": "Native Hawaiian/Pacific Islander", "pct": _pct(row.get("pop_nhpi"), total_pop)},
            {"label": "Other", "pct": _pct(row.get("pop_other_race"), total_pop)},
            {"label": "Two or more", "pct": _pct(row.get("pop_two_plus"), total_pop)},
        ]

    hispanic = []
    if total_pop > 0:
        hispanic = [
            {"label": "Not Hispanic/Latino", "pct": _pct(row.get("pop_not_hispanic"), total_pop)},
            {"label": "Hispanic/Latino", "pct": _pct(row.get("pop_hispanic"), total_pop)},
        ]

    education = []
    if pop_25plus > 0:
        education = [
            {"label": "No HS diploma", "pct": _pct(row.get("edu_no_hs"), pop_25plus)},
            {"label": "HS diploma/GED", "pct": _pct(row.get("edu_hs"), pop_25plus)},
            {"label": "Some college/Associate's", "pct": _pct(row.get("edu_some_college"), pop_25plus)},
            {"label": "Bachelor's", "pct": _pct(row.get("edu_bachelors"), pop_25plus)},
            {"label": "Graduate+", "pct": _pct(row.get("edu_graduate"), pop_25plus)},
        ]

    return {
        "source": "ACS Tract (Census Bureau)",
        "tract_fips": row["tract_fips"],
        "total_population": int(total_pop) if total_pop else None,
        "median_household_income": int(row["median_household_income"]) if row.get("median_household_income") else None,
        "unemployment_rate": float(row["unemployment_rate"]) if row.get("unemployment_rate") else None,
        "pct_female": float(row["pct_female"]) if row.get("pct_female") else None,
        "pct_minority": float(row["pct_minority"]) if row.get("pct_minority") else None,
        "gender": gender,
        "race": [r for r in race if r["pct"] > 0],
        "hispanic": hispanic,
        "education": education,
    }


_NAICS_SECTOR_QCEW = {
    "31": "31-33", "32": "31-33", "33": "31-33",
    "44": "44-45", "45": "44-45",
    "48": "48-49", "49": "48-49",
}


def _get_qcew_context(cur, county_fips: str, naics_code: str):
    """QCEW local employment context for employer's county + industry."""
    naics_clean = re.sub(r"[^0-9]", "", naics_code or "")
    if not county_fips or not naics_clean:
        return None

    # QCEW uses 3-digit NAICS or hyphenated sector codes (31-33, 44-45, 48-49)
    candidates = []
    if len(naics_clean) >= 4:
        candidates.append(naics_clean[:4])
    if len(naics_clean) >= 3:
        candidates.append(naics_clean[:3])
    sector = _NAICS_SECTOR_QCEW.get(naics_clean[:2], naics_clean[:2])
    candidates.append(sector)
    candidates.append("10")  # Total private

    for code in candidates:
        cur.execute("""
            SELECT year, annual_avg_emplvl, annual_avg_estabs,
                   avg_annual_pay, annual_avg_wkly_wage,
                   industry_code
            FROM qcew_annual
            WHERE area_fips = %s AND industry_code = %s
              AND own_code = '5'
            ORDER BY year DESC LIMIT 1
        """, [county_fips, code])
        row = cur.fetchone()
        if row and row.get("annual_avg_emplvl"):
            return {
                "source": "QCEW (BLS)",
                "year": row["year"],
                "county_fips": county_fips,
                "industry_code": row["industry_code"],
                "local_employment": int(row["annual_avg_emplvl"]),
                "local_establishments": int(row["annual_avg_estabs"]) if row.get("annual_avg_estabs") else None,
                "avg_annual_pay": _float(row.get("avg_annual_pay")),
                "avg_weekly_wage": _float(row.get("annual_avg_wkly_wage")),
            }
    return None


def _get_oes_wages(cur, state: str, naics_code: str):
    """Top occupation wages from OES for employer's state."""
    if not state:
        return None
    cur.execute("""
        SELECT occ_code, occ_title, tot_emp, a_mean, a_median,
               a_pct10, a_pct25, a_pct75, a_pct90
        FROM mv_oes_area_wages
        WHERE prim_state = %s AND occ_code != '00-0000'
        ORDER BY tot_emp DESC NULLS LAST
        LIMIT 10
    """, [state.upper()])
    rows = cur.fetchall()
    if not rows:
        return None
    return {
        "source": "OES (BLS)",
        "state": state.upper(),
        "top_occupations": [
            {
                "code": r["occ_code"],
                "title": r["occ_title"],
                "employment": _float(r["tot_emp"]),
                "mean_wage": _float(r["a_mean"]),
                "median_wage": _float(r["a_median"]),
                "pct10": _float(r["a_pct10"]),
                "pct90": _float(r["a_pct90"]),
            }
            for r in rows
        ],
    }


def _get_injury_rates(cur, naics_code: str):
    """SOII injury/illness rates for employer's industry."""
    naics_clean = re.sub(r"[^0-9]", "", naics_code or "")
    if not naics_clean:
        return None

    padded = (naics_clean + "000000")[:6]
    # Try exact, then progressively broader
    for prefix in [padded, padded[:4] + "00", padded[:3] + "000"]:
        cur.execute("""
            SELECT year, industry_code, industry_name, rate
            FROM mv_soii_industry_rates
            WHERE industry_code = %s
              AND case_type_code = '1' AND data_type_code = '3'
            ORDER BY year DESC LIMIT 1
        """, [prefix])
        row = cur.fetchone()
        if row and row.get("rate") is not None:
            return {
                "source": "SOII (BLS)",
                "year": row["year"],
                "industry": row["industry_name"],
                "total_recordable_rate": _float(row["rate"]),
                "per": "100 full-time workers",
            }

    # LIKE fallback for broad sectors (e.g., NAICS 31 -> match 31xxxx)
    cur.execute("""
        SELECT year, industry_code, industry_name, rate
        FROM mv_soii_industry_rates
        WHERE industry_code LIKE %s
          AND case_type_code = '1' AND data_type_code = '3'
        ORDER BY LENGTH(industry_code), year DESC LIMIT 1
    """, [naics_clean[:2] + "%"])
    row = cur.fetchone()
    if row and row.get("rate") is not None:
        return {
            "source": "SOII (BLS)",
            "year": row["year"],
            "industry": row["industry_name"],
            "total_recordable_rate": _float(row["rate"]),
            "per": "100 full-time workers",
        }

    # All-industry fallback
    cur.execute("""
        SELECT year, industry_name, rate
        FROM mv_soii_industry_rates
        WHERE industry_code = '000000'
          AND case_type_code = '1' AND data_type_code = '3'
        ORDER BY year DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row and row.get("rate") is not None:
        return {
            "source": "SOII (BLS)",
            "year": row["year"],
            "industry": row["industry_name"],
            "total_recordable_rate": _float(row["rate"]),
            "per": "100 full-time workers",
        }
    return None


_NAICS_TO_JOLTS = {
    "11": "110099", "21": "110099", "23": "230000",
    "31": "300000", "32": "300000", "33": "300000",
    "42": "420000", "44": "440000", "45": "440000",
    "48": "480099", "49": "480099", "51": "510000",
    "52": "520000", "53": "530000", "54": "540099", "55": "540099", "56": "540099",
    "61": "610000", "62": "620000", "71": "710000", "72": "720000",
    "81": "810000", "92": "900000",
}


def _get_turnover_rates(cur, naics_code: str):
    """JOLTS turnover data for employer's industry."""
    naics_clean = re.sub(r"[^0-9]", "", naics_code or "")
    if not naics_clean:
        return None

    jolts_code = _NAICS_TO_JOLTS.get(naics_clean[:2], "100000")

    cur.execute("""
        SELECT year, period, dataelement_text, rate
        FROM mv_jolts_industry_rates
        WHERE industry_code = %s
        ORDER BY year DESC, period DESC
        LIMIT 20
    """, [jolts_code])
    rows = cur.fetchall()
    if not rows:
        return None

    latest_year = rows[0]["year"]
    latest = {r["dataelement_text"]: _float(r["rate"])
              for r in rows if r["year"] == latest_year}
    return {
        "source": "JOLTS (BLS)",
        "year": latest_year,
        "rates": latest,
    }


_NAICS_TO_NCS = {
    "22": "220000", "23": "230000",
    "31": "300000", "32": "300000", "33": "300000",
    "42": "420000", "44": "412000", "45": "412000",
    "48": "430000", "49": "430000", "51": "510000",
    "52": "520000", "53": "530000", "54": "540000",
    "55": "540A00", "56": "560000",
    "61": "610000", "62": "620000", "71": "700000", "72": "720000",
    "81": "810000", "92": "920000",
}


def _get_benefits_access(cur, naics_code: str):
    """NCS benefits access for employer's industry."""
    naics_clean = re.sub(r"[^0-9]", "", naics_code or "")
    if not naics_clean:
        return None

    # Try exact NAICS prefixes first, then mapped code, then all-industry
    candidates = [naics_clean[:6], naics_clean[:4], naics_clean[:3],
                  _NAICS_TO_NCS.get(naics_clean[:2], ""), "000000"]

    for code in candidates:
        if not code:
            continue
        cur.execute("""
            SELECT DISTINCT ON (estimate_text)
                   year, estimate_text, rate
            FROM mv_ncs_benefits_access
            WHERE industry_code = %s
              AND datatype_code = '19'
            ORDER BY estimate_text, year DESC
        """, [code])
        rows = cur.fetchall()
        if rows:
            benefits = {}
            year = None
            for r in rows:
                if r.get("rate") is not None:
                    benefits[r["estimate_text"]] = _float(r["rate"])
                    if year is None:
                        year = r["year"]
            if benefits:
                return {
                    "source": "NCS (BLS)",
                    "year": year,
                    "industry_code": code,
                    "access_rates": benefits,
                }
    return None


def _get_union_density(cur, state: str, naics_code: str):
    """Union density from CPS-sourced BLS tables."""
    result = {}
    # State-level
    if state:
        cur.execute("""
            SELECT year, union_density_pct, represented_density_pct,
                   total_employed_thousands
            FROM bls_state_density
            WHERE state = %s ORDER BY year DESC LIMIT 1
        """, [state.upper()])
        row = cur.fetchone()
        if row:
            result["state"] = {
                "year": row["year"],
                "union_density_pct": _float(row["union_density_pct"]),
                "represented_pct": _float(row["represented_density_pct"]),
                "total_employed_k": _float(row["total_employed_thousands"]),
            }

    # National industry-level
    naics_clean = re.sub(r"[^0-9]", "", naics_code or "")
    if naics_clean:
        cur.execute("""
            SELECT bls_industry_code FROM naics_to_bls_industry
            WHERE naics_code = %s LIMIT 1
        """, [naics_clean[:4]])
        mapping = cur.fetchone()
        if mapping:
            cur.execute("""
                SELECT year, industry_name, union_density_pct, represented_density_pct,
                       total_employed_thousands
                FROM bls_national_industry_density
                WHERE industry_code = %s ORDER BY year DESC LIMIT 1
            """, [mapping["bls_industry_code"]])
            row = cur.fetchone()
            if row:
                result["industry"] = {
                    "year": row["year"],
                    "industry_name": row["industry_name"],
                    "union_density_pct": _float(row["union_density_pct"]),
                    "represented_pct": _float(row["represented_density_pct"]),
                    "total_employed_k": _float(row["total_employed_thousands"]),
                }

    # Estimated state x industry
    if state and naics_clean:
        cur.execute("""
            SELECT year, estimated_density, confidence, industry_name
            FROM estimated_state_industry_density
            WHERE state = %s AND industry_code = (
                SELECT bls_industry_code FROM naics_to_bls_industry
                WHERE naics_code = %s LIMIT 1
            )
            ORDER BY year DESC LIMIT 1
        """, [state.upper(), naics_clean[:4]])
        row = cur.fetchone()
        if row:
            result["state_industry"] = {
                "year": row["year"],
                "estimated_density_pct": _float(row["estimated_density"]),
                "confidence": row["confidence"],
                "industry_name": row["industry_name"],
            }

    return result if result else None


def _blend_demographics(acs, lodes):
    """Blend ACS (industry x state) and LODES (county) into estimated composition.

    ACS is weighted 60% (industry-specific) and LODES 40% (geography-specific).
    For categories that exist in both, we blend. For categories only in one, pass through.
    """
    if not acs and not lodes:
        return None
    if not lodes:
        return {"method": "acs_only", "demographics": acs}
    if not acs:
        return {"method": "lodes_only", "demographics": lodes}

    ACS_W, LODES_W = 0.6, 0.4

    # Normalization maps to align ACS and LODES labels
    _RACE_NORM = {
        "Asian/Pacific Islander": "Asian/Pacific Islander",
        "Asian": "Asian/Pacific Islander",
        "Pacific Islander": "Asian/Pacific Islander",
        "Two or more": "Two or more",
        "Two or More": "Two or more",
    }
    _AGE_NORM = {
        # Map fine-grained ACS to broad LODES buckets
        "Under 25": "29 or younger",
        "25-34": "30-54",
        "35-44": "30-54",
        "45-54": "30-54",
        "55-64": "55+",
        "65+": "55+",
    }

    def _normalize_list(items, norm_map):
        """Consolidate items by normalized labels."""
        merged = {}
        for item in (items or []):
            key = norm_map.get(item["label"], item["label"])
            merged[key] = merged.get(key, 0) + item["pct"]
        return [{"label": k, "pct": round(v, 1)} for k, v in merged.items()]

    _EDU_NORM = {
        "Bachelor's+": "Bachelor's+",
        "Bachelor's": "Bachelor's+",
        "Graduate/Professional": "Bachelor's+",
    }

    def blend_lists(acs_list, lodes_list, dimension):
        """Blend two lists of {label, pct} items, normalized to 100%."""
        norm = (_RACE_NORM if dimension == "race"
                else _AGE_NORM if dimension == "age"
                else _EDU_NORM if dimension == "education"
                else {})
        a_items = _normalize_list(acs_list, norm) if norm else (acs_list or [])
        l_items = _normalize_list(lodes_list, norm) if norm else (lodes_list or [])

        acs_map = {item["label"]: item["pct"] for item in a_items}
        lodes_map = {item["label"]: item["pct"] for item in l_items}
        all_labels = list(dict.fromkeys(
            [i["label"] for i in a_items] + [i["label"] for i in l_items]
        ))
        blended = []
        for label in all_labels:
            a = acs_map.get(label)
            l = lodes_map.get(label)
            if a is not None and l is not None:
                val = round(a * ACS_W + l * LODES_W, 1)
            elif a is not None:
                val = a
            else:
                val = l
            if val and val > 0:
                blended.append({"label": label, "pct": val})
        # Normalize to 100%
        raw_sum = sum(item["pct"] for item in blended)
        if raw_sum > 0 and abs(raw_sum - 100) > 1:
            for item in blended:
                item["pct"] = round(item["pct"] / raw_sum * 100, 1)
        return sorted(blended, key=lambda x: -x["pct"])

    return {
        "method": "blended",
        "weights": {"acs": ACS_W, "lodes": LODES_W},
        "note": "ACS (industry x state) weighted 60%, LODES (county geography) weighted 40%",
        "gender": blend_lists(acs.get("gender"), lodes.get("gender"), "gender"),
        "race": blend_lists(acs.get("race"), lodes.get("race"), "race"),
        "hispanic": blend_lists(acs.get("hispanic"), lodes.get("hispanic"), "hispanic"),
        "age": blend_lists(acs.get("age"), lodes.get("age"), "age"),
        "education": blend_lists(acs.get("education"), lodes.get("education"), "education"),
    }


@router.get("/api/profile/employers/{employer_id}/workforce-profile")
def get_employer_workforce_profile(employer_id: str):
    """Comprehensive workforce profile combining ACS, LODES, QCEW, BLS, and CPS data.

    Returns blended demographic estimates and labor market context.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            emp = _get_employer_basics(cur, employer_id)
            if not emp:
                raise HTTPException(status_code=404, detail="Employer not found")

            state = (emp.get("state") or "").strip()
            zip_code = (emp.get("zip") or "").strip()[:5]
            naics = re.sub(r"[^0-9]", "",
                           (emp.get("naics_detailed") or emp.get("naics") or "").strip())

            county_fips = _get_county_fips(cur, zip_code)
            state_fips = _get_state_fips(cur, state) if state else None

            # Gather all data sources
            acs = _get_acs_demographics(cur, state_fips, naics) if state_fips else None
            lodes = _get_lodes_demographics(cur, county_fips) if county_fips else None
            qcew = _get_qcew_context(cur, county_fips, naics) if county_fips else None
            oes = _get_oes_wages(cur, state, naics) if state else None
            soii = _get_injury_rates(cur, naics)
            jolts = _get_turnover_rates(cur, naics)
            ncs = _get_benefits_access(cur, naics)
            density = _get_union_density(cur, state, naics)

            # Tract demographics (neighborhood, NOT blended into workforce)
            tract = _get_tract_demographics(cur, employer_id)

            # V5 Gate-routed estimate (preferred), with old blend as fallback
            v5_estimate = None
            try:
                from ..services.demographics_v5 import estimate_demographics_v5
                total_emp = emp.get("latest_unit_size") or 100
                v5_result = estimate_demographics_v5(
                    cur, naics, state_fips, zip_code, county_fips,
                    total_employees=total_emp,
                )
                if v5_result and v5_result.get('race'):
                    v5_estimate = {
                        "method": "gate_v1",
                        "race": [{"label": k, "pct": v}
                                 for k, v in v5_result['race'].items()],
                        "hispanic": ([{"label": k, "pct": v}
                                      for k, v in v5_result['hispanic'].items()]
                                     if v5_result.get('hispanic') else None),
                        "gender": ([{"label": k, "pct": v}
                                    for k, v in v5_result['gender'].items()]
                                   if v5_result.get('gender') else None),
                        "metadata": v5_result.get('metadata'),
                    }
            except Exception as exc:
                _logger.warning("V5 demographics unavailable: %s", exc)

            # Fallback: old 60/40 ACS/LODES blend
            blended = _blend_demographics(acs, lodes)
            estimated = v5_estimate or blended

            return {
                "employer_id": employer_id,
                "employer_name": emp.get("employer_name"),
                "state": state,
                "city": emp.get("city"),
                "naics": naics or None,
                "unit_size": emp.get("latest_unit_size"),

                # Blended workforce composition estimate
                "estimated_composition": estimated,

                # Source data
                "acs": acs,
                "lodes": lodes,
                "qcew": qcew,
                "oes": oes,
                "soii": soii,
                "jolts": jolts,
                "ncs": ncs,
                "union_density": density,

                # Neighborhood demographics (census tract, area average)
                "tract": tract,
            }
