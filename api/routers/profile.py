from fastapi import APIRouter, HTTPException

from ..database import get_db

router = APIRouter()


@router.get("/api/profile/employers/{employer_id}")
def get_employer_profile(employer_id: str):
    """Canonical employer profile payload for frontend detail rendering."""
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
                SELECT employer_id, employer_name, state, city, naics, latest_unit_size,
                       latest_union_name, source_count, has_osha, has_nlrb, has_whd,
                       has_sam, has_sec, has_gleif, has_mergent, is_federal_contractor,
                       is_public, score_osha, score_nlrb, score_whd, score_contracts,
                       score_union_proximity, score_financial, score_size,
                       factors_available, factors_total, unified_score, coverage_pct, score_tier
                FROM mv_unified_scorecard
                WHERE employer_id::text = %s
                LIMIT 1
                """,
                [f7_id],
            )
            unified_scorecard = cur.fetchone()

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
                       COALESCE(vs.repeat_count, 0) AS repeat_count
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
                SELECT id, flag_type, notes, created_at
                FROM employer_review_flags
                WHERE source_type = 'F7' AND source_id = %s
                ORDER BY created_at DESC
                """,
                [f7_id],
            )
            flags = cur.fetchall()

            return {
                "employer": employer,
                "unified_scorecard": unified_scorecard,
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
            }


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
                SELECT lm.yr_covered,
                       SUM(am.number) FILTER (WHERE am.voting_eligibility = 'T') AS members,
                       SUM(COALESCE(lm.ttl_assets, 0)) AS ttl_assets,
                       SUM(COALESCE(lm.ttl_receipts, 0)) AS ttl_receipts
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
