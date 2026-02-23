"""
Research Agent — Internal Tool Definitions

Each tool queries the existing database and returns a standardised result dict:
    {
        "found": bool,
        "source": str,            # e.g. "database:osha_violations_detail"
        "summary": str,           # one-paragraph human-readable summary
        "data": { ... },          # structured findings (varies per tool)
        "error": str | None       # only present when found=False due to error
    }

Tools are called by the agent orchestration loop (agent.py) whenever the
Claude API returns a tool_use block.  They can also be imported and called
standalone for testing.
"""

from __future__ import annotations

import logging
import sys
import os
import traceback
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Allow imports from project root
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from db_config import get_connection

_log = logging.getLogger("research.tools")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn():
    """Get a psycopg2 connection with RealDictCursor."""
    return get_connection(cursor_factory=RealDictCursor)


def _safe(val: Any) -> Any:
    """Make a value JSON-safe (Decimal → float, date → str)."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def _safe_dict(d: dict) -> dict:
    return {k: _safe(v) for k, v in d.items()}


def _safe_list(rows: list[dict]) -> list[dict]:
    return [_safe_dict(r) for r in rows]


def _error_result(source: str, err: Exception) -> dict:
    _log.error("Tool error [%s]: %s", source, err)
    return {
        "found": False,
        "source": source,
        "summary": f"Error: {err}",
        "data": {},
        "error": str(err),
    }


# ---------------------------------------------------------------------------
# TOOL 1: search_osha
# ---------------------------------------------------------------------------

def search_osha(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search OSHA tables for workplace safety violations."""
    source = "database:osha_violations_detail"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Step 1 — find establishment_ids linked to this employer
        estab_ids: list[str] = []

        if employer_id:
            # Via osha_f7_matches
            cur.execute("""
                SELECT establishment_id
                FROM osha_f7_matches
                WHERE f7_employer_id = %s
            """, (employer_id,))
            estab_ids = [r["establishment_id"] for r in cur.fetchall()]

            # Also check unified_match_log
            if not estab_ids:
                cur.execute("""
                    SELECT source_id
                    FROM unified_match_log
                    WHERE source_system = 'osha'
                      AND target_id = %s
                      AND status = 'active'
                """, (employer_id,))
                estab_ids = [r["source_id"] for r in cur.fetchall()]

        if not estab_ids:
            # Fuzzy fallback by name + optional state
            like_pat = f"%{company_name.upper()}%"
            if state:
                cur.execute("""
                    SELECT establishment_id FROM osha_establishments
                    WHERE UPPER(estab_name) LIKE %s AND site_state = %s
                    LIMIT 20
                """, (like_pat, state.upper()))
            else:
                cur.execute("""
                    SELECT establishment_id FROM osha_establishments
                    WHERE UPPER(estab_name) LIKE %s
                    LIMIT 20
                """, (like_pat,))
            estab_ids = [r["establishment_id"] for r in cur.fetchall()]

        if not estab_ids:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No OSHA establishments found for this employer.",
                    "data": {}}

        # Step 2 — aggregate violations
        cur.execute("""
            SELECT
                COUNT(*) AS violation_count,
                COUNT(*) FILTER (WHERE violation_type = 'S') AS serious_count,
                COUNT(*) FILTER (WHERE violation_type = 'W') AS willful_count,
                COUNT(*) FILTER (WHERE violation_type = 'R') AS repeat_count,
                COALESCE(SUM(current_penalty), 0) AS penalty_total,
                MAX(issuance_date) AS most_recent_date,
                COUNT(DISTINCT activity_nr) AS inspection_count
            FROM osha_violations_detail
            WHERE establishment_id = ANY(%s)
        """, (estab_ids,))
        agg = _safe_dict(cur.fetchone())

        # Step 3 — top violation types by standard prefix
        cur.execute("""
            SELECT
                COALESCE(
                    CASE
                        WHEN standard LIKE '1926.50%%' THEN 'Fall Protection'
                        WHEN standard LIKE '1926.451%%' THEN 'Scaffolding'
                        WHEN standard LIKE '1910.134%%' THEN 'Respiratory Protection'
                        WHEN standard LIKE '1910.147%%' THEN 'Lockout/Tagout'
                        WHEN standard LIKE '1910.305%%' OR standard LIKE '1910.303%%' THEN 'Electrical'
                        WHEN standard LIKE '1910.212%%' THEN 'Machine Guarding'
                        WHEN standard LIKE '1910.1200%%' THEN 'Hazard Communication'
                        WHEN standard LIKE '1926.102%%' THEN 'Eye/Face Protection'
                        WHEN standard LIKE '1910.178%%' THEN 'Powered Industrial Trucks'
                        ELSE LEFT(standard, 8)
                    END, 'Unknown') AS viol_type,
                COUNT(*) AS cnt
            FROM osha_violations_detail
            WHERE establishment_id = ANY(%s)
            GROUP BY 1 ORDER BY cnt DESC LIMIT 5
        """, (estab_ids,))
        top_types = _safe_list(cur.fetchall())

        # Step 4 — accidents
        cur.execute("""
            SELECT event_date, is_fatality, hospitalized, amputation,
                   injury_count, event_description
            FROM osha_accidents
            WHERE establishment_id = ANY(%s)
            ORDER BY event_date DESC LIMIT 10
        """, (estab_ids,))
        accidents = _safe_list(cur.fetchall())

        conn.close()

        data = {
            "violation_count": agg["violation_count"],
            "serious_count": agg["serious_count"],
            "willful_count": agg["willful_count"],
            "repeat_count": agg["repeat_count"],
            "penalty_total": agg["penalty_total"],
            "most_recent_date": agg["most_recent_date"],
            "inspection_count": agg["inspection_count"],
            "establishment_count": len(estab_ids),
            "top_violation_types": [{"type": r["viol_type"], "count": r["cnt"]} for r in top_types],
            "accidents": accidents,
        }

        parts = [f"{data['violation_count']} OSHA violations across {data['establishment_count']} establishments"]
        if data["serious_count"]:
            parts.append(f"including {data['serious_count']} serious")
        parts.append(f"${data['penalty_total']:,.0f} in penalties")
        if data["most_recent_date"]:
            parts.append(f"Most recent: {data['most_recent_date']}")
        if accidents:
            parts.append(f"{len(accidents)} accident(s) on record")

        return {"found": True, "source": source, "summary": ". ".join(parts) + ".", "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 2: search_nlrb
# ---------------------------------------------------------------------------

def search_nlrb(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search NLRB tables for election history and ULP charges."""
    source = "database:nlrb_cases"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Step 1 — find case numbers linked to this employer
        case_numbers: set[str] = set()

        if employer_id:
            # Via xref table
            cur.execute("""
                SELECT DISTINCT p.case_number
                FROM nlrb_employer_xref x
                JOIN nlrb_participants p
                  ON UPPER(p.participant_name) = UPPER(x.nlrb_employer_name)
                 AND p.participant_type LIKE '%%Employer%%'
                WHERE x.f7_employer_id = %s
            """, (employer_id,))
            case_numbers.update(r["case_number"] for r in cur.fetchall())

            # Also via matched_employer_id on participants
            cur.execute("""
                SELECT DISTINCT case_number FROM nlrb_participants
                WHERE matched_employer_id = %s
            """, (employer_id,))
            case_numbers.update(r["case_number"] for r in cur.fetchall())

        if not case_numbers:
            like_pat = f"%{company_name.upper()}%"
            if state:
                cur.execute("""
                    SELECT DISTINCT case_number FROM nlrb_participants
                    WHERE UPPER(participant_name) LIKE %s
                      AND participant_type LIKE '%%Employer%%'
                      AND UPPER(state) = %s
                    LIMIT 100
                """, (like_pat, state.upper()))
            else:
                cur.execute("""
                    SELECT DISTINCT case_number FROM nlrb_participants
                    WHERE UPPER(participant_name) LIKE %s
                      AND participant_type LIKE '%%Employer%%'
                    LIMIT 100
                """, (like_pat,))
            case_numbers.update(r["case_number"] for r in cur.fetchall())

        if not case_numbers:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No NLRB cases found for this employer.", "data": {}}

        case_list = list(case_numbers)

        # Step 2 — elections
        cur.execute("""
            SELECT e.case_number, e.election_date, e.eligible_voters,
                   e.total_votes, e.union_won, e.vote_margin, e.election_type,
                   t.labor_org_name, t.votes_for, t.is_winner
            FROM nlrb_elections e
            LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number
            WHERE e.case_number = ANY(%s)
            ORDER BY e.election_date DESC
        """, (case_list,))
        elections_raw = _safe_list(cur.fetchall())

        # Deduplicate by case_number (keep first = most recent)
        seen_cases = set()
        elections = []
        for row in elections_raw:
            cn = row["case_number"]
            if cn not in seen_cases:
                seen_cases.add(cn)
                elections.append(row)

        wins = sum(1 for e in elections if e.get("union_won"))
        losses = sum(1 for e in elections if e.get("union_won") is False)

        # Step 3 — ULP cases (CA type)
        cur.execute("""
            SELECT c.case_number, c.case_type, c.earliest_date, c.latest_date
            FROM nlrb_cases c
            WHERE c.case_number = ANY(%s)
              AND c.case_type = 'CA'
            ORDER BY c.earliest_date DESC
        """, (case_list,))
        ulp_cases = _safe_list(cur.fetchall())

        # Step 4 — ULP allegations
        ulp_case_nums = [u["case_number"] for u in ulp_cases]
        allegations = []
        if ulp_case_nums:
            cur.execute("""
                SELECT case_number, section, allegation_text, allegation_status
                FROM nlrb_allegations
                WHERE case_number = ANY(%s)
                ORDER BY case_number
            """, (ulp_case_nums,))
            allegations = _safe_list(cur.fetchall())

        # Step 5 — Voluntary recognitions
        like_pat = f"%{company_name.upper()}%"
        cur.execute("""
            SELECT vr_case_number, employer_name, union_name,
                   date_voluntary_recognition, num_employees,
                   unit_city, unit_state, unit_description
            FROM nlrb_voluntary_recognition
            WHERE UPPER(employer_name) LIKE %s
               OR matched_employer_id = %s
            ORDER BY date_voluntary_recognition DESC
        """, (like_pat, employer_id or ''))
        vr_records = _safe_list(cur.fetchall())

        # Step 6 — which unions were involved
        cur.execute("""
            SELECT DISTINCT participant_name, participant_type
            FROM nlrb_participants
            WHERE case_number = ANY(%s)
              AND participant_type LIKE '%%Union%%'
        """, (case_list,))
        unions_involved = _safe_list(cur.fetchall())

        conn.close()

        data = {
            "election_count": len(elections),
            "elections": elections[:20],
            "wins": wins,
            "losses": losses,
            "ulp_count": len(ulp_cases),
            "ulp_cases": ulp_cases[:20],
            "ulp_allegations": allegations[:30],
            "voluntary_recognitions": vr_records,
            "unions_involved": unions_involved,
            "total_cases": len(case_list),
        }

        parts = [f"{len(case_list)} NLRB cases found"]
        if elections:
            parts.append(f"{len(elections)} election(s) ({wins}W-{losses}L)")
        if ulp_cases:
            parts.append(f"{len(ulp_cases)} ULP charge(s)")
        if vr_records:
            parts.append(f"{len(vr_records)} voluntary recognition(s)")

        return {"found": True, "source": source, "summary": ". ".join(parts) + ".", "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 3: search_whd
# ---------------------------------------------------------------------------

def search_whd(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search DOL Wage & Hour Division records."""
    source = "database:whd_cases"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Find matching cases
        case_ids: list[int] = []

        if employer_id:
            # Via whd_f7_matches first (most reliable)
            cur.execute("""
                SELECT w.id FROM whd_cases w
                JOIN whd_f7_matches m ON m.case_id = w.case_id
                WHERE m.f7_employer_id = %s
            """, (employer_id,))
            case_ids = [r["id"] for r in cur.fetchall()]

            # Fallback: unified_match_log
            if not case_ids:
                cur.execute("""
                    SELECT w.id FROM whd_cases w
                    JOIN unified_match_log u ON u.source_id = w.case_id
                    WHERE u.source_system = 'whd'
                      AND u.target_id = %s
                      AND u.status = 'active'
                """, (employer_id,))
                case_ids = [r["id"] for r in cur.fetchall()]

        if not case_ids:
            like_pat = f"%{company_name.upper()}%"
            q = """
                SELECT id FROM whd_cases
                WHERE (UPPER(legal_name) LIKE %s OR UPPER(trade_name) LIKE %s)
            """
            params: list = [like_pat, like_pat]
            if state:
                q += " AND state = %s"
                params.append(state.upper())
            q += " LIMIT 50"
            cur.execute(q, params)
            case_ids = [r["id"] for r in cur.fetchall()]

        if not case_ids:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No WHD cases found for this employer.", "data": {}}

        # Aggregate
        cur.execute("""
            SELECT
                COUNT(*) AS case_count,
                COALESCE(SUM(backwages_amount), 0) AS total_backwages,
                COALESCE(SUM(civil_penalties), 0) AS total_penalties,
                COALESCE(SUM(employees_violated), 0) AS total_employees_affected,
                BOOL_OR(COALESCE(flsa_repeat_violator, false)) AS is_repeat,
                COALESCE(SUM(flsa_child_labor_violations), 0) AS child_labor_violations,
                COALESCE(SUM(flsa_child_labor_minors), 0) AS child_labor_minors,
                COALESCE(SUM(flsa_violations), 0) AS flsa_violation_count,
                COALESCE(SUM(flsa_overtime_backwages), 0) AS overtime_backwages,
                COALESCE(SUM(flsa_mw_backwages), 0) AS min_wage_backwages,
                MIN(findings_start_date) AS earliest_date,
                MAX(findings_end_date) AS latest_date
            FROM whd_cases WHERE id = ANY(%s)
        """, (case_ids,))
        agg = _safe_dict(cur.fetchone())

        # Grab DBA/trade names
        cur.execute("""
            SELECT DISTINCT trade_name FROM whd_cases
            WHERE id = ANY(%s) AND trade_name IS NOT NULL AND trade_name != ''
        """, (case_ids,))
        trade_names = [r["trade_name"] for r in cur.fetchall()]

        conn.close()

        data = {
            "case_count": agg["case_count"],
            "total_backwages": agg["total_backwages"],
            "total_penalties": agg["total_penalties"],
            "employees_affected": agg["total_employees_affected"],
            "is_repeat_violator": agg["is_repeat"],
            "child_labor_violations": agg["child_labor_violations"],
            "child_labor_minors": agg["child_labor_minors"],
            "flsa_violation_count": agg["flsa_violation_count"],
            "overtime_backwages": agg["overtime_backwages"],
            "min_wage_backwages": agg["min_wage_backwages"],
            "earliest_date": agg["earliest_date"],
            "latest_date": agg["latest_date"],
            "trade_names": trade_names,
        }

        parts = [f"{data['case_count']} WHD case(s)"]
        if data["total_backwages"]:
            parts.append(f"${data['total_backwages']:,.0f} in back wages")
        if data["total_penalties"]:
            parts.append(f"${data['total_penalties']:,.0f} in penalties")
        if data["employees_affected"]:
            parts.append(f"{data['employees_affected']} workers affected")
        if data["is_repeat_violator"]:
            parts.append("REPEAT VIOLATOR")
        if data["child_labor_violations"]:
            parts.append(f"{data['child_labor_violations']} child labor violation(s)")

        return {"found": True, "source": source, "summary": ". ".join(parts) + ".", "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 4: search_sec
# ---------------------------------------------------------------------------

def search_sec(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    company_type: Optional[str] = None,
    **_kw,
) -> dict:
    """Search SEC EDGAR for public company financial data."""
    source = "database:sec_companies"
    try:
        if company_type and company_type.lower() in ("private", "nonprofit"):
            return {"found": False, "source": source,
                    "summary": f"Skipped: company_type is '{company_type}' (no SEC filings for non-public companies).",
                    "data": {}, "skipped": True}

        conn = _conn()
        cur = conn.cursor()

        row = None
        if employer_id:
            # Via crosswalk
            cur.execute("""
                SELECT s.* FROM sec_companies s
                JOIN corporate_identifier_crosswalk c ON c.sec_cik = s.cik
                WHERE c.f7_employer_id = %s
                LIMIT 1
            """, (employer_id,))
            row = cur.fetchone()

        if not row:
            like_pat = f"%{company_name.upper()}%"
            cur.execute("""
                SELECT * FROM sec_companies
                WHERE UPPER(company_name) LIKE %s
                ORDER BY is_public DESC NULLS LAST
                LIMIT 1
            """, (like_pat,))
            row = cur.fetchone()

        if not row:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No SEC company found matching this employer.", "data": {}}

        row = _safe_dict(row)

        # Check crosswalk for federal contractor info
        crosswalk_data = None
        if row.get("cik"):
            cur.execute("""
                SELECT is_public, is_federal_contractor, federal_obligations,
                       federal_contract_count, ticker, ein
                FROM corporate_identifier_crosswalk
                WHERE sec_cik = %s LIMIT 1
            """, (row["cik"],))
            cw = cur.fetchone()
            if cw:
                crosswalk_data = _safe_dict(cw)

        conn.close()

        data = {
            "cik": row.get("cik"),
            "company_name": row.get("company_name"),
            "ticker": row.get("ticker"),
            "exchange": row.get("exchange"),
            "sic_code": row.get("sic_code"),
            "sic_description": row.get("sic_description"),
            "state": row.get("state"),
            "is_public": row.get("is_public"),
            "ein": row.get("ein"),
        }
        if crosswalk_data:
            data["federal_contractor"] = crosswalk_data.get("is_federal_contractor")
            data["federal_obligations"] = crosswalk_data.get("federal_obligations")

        summary = f"SEC: {data['company_name']}"
        if data.get("ticker"):
            summary += f" ({data['ticker']}:{data.get('exchange', '?')})"
        summary += f". SIC {data.get('sic_code', 'N/A')}: {data.get('sic_description', 'N/A')}."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 5: search_sam
# ---------------------------------------------------------------------------

def search_sam(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search SAM.gov for federal contractor registration."""
    source = "database:sam_entities"
    try:
        conn = _conn()
        cur = conn.cursor()

        sam_row = None
        uei = None

        if employer_id:
            # Via unified_match_log
            cur.execute("""
                SELECT source_id FROM unified_match_log
                WHERE source_system = 'sam'
                  AND target_id = %s
                  AND status = 'active'
                LIMIT 1
            """, (employer_id,))
            r = cur.fetchone()
            if r:
                uei = r["source_id"]
                cur.execute("SELECT * FROM sam_entities WHERE uei = %s", (uei,))
                sam_row = cur.fetchone()

        if not sam_row:
            like_pat = f"%{company_name.upper()}%"
            q = "SELECT * FROM sam_entities WHERE UPPER(legal_business_name) LIKE %s"
            params: list = [like_pat]
            if state:
                q += " AND physical_state = %s"
                params.append(state.upper())
            q += " ORDER BY last_update_date DESC NULLS LAST LIMIT 1"
            cur.execute(q, params)
            sam_row = cur.fetchone()

        if not sam_row:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No SAM.gov registration found for this employer.", "data": {}}

        sam_row = _safe_dict(sam_row)

        # Check federal_contract_recipients for dollar amounts
        contract_data = None
        cur.execute("""
            SELECT SUM(total_obligations) AS total_obligations,
                   SUM(contract_count) AS total_contracts,
                   MAX(fiscal_year) AS latest_year
            FROM federal_contract_recipients
            WHERE UPPER(recipient_name) LIKE %s
        """, (f"%{company_name.upper()}%",))
        cr = cur.fetchone()
        if cr and cr.get("total_obligations"):
            contract_data = _safe_dict(cr)

        conn.close()

        is_active = sam_row.get("sam_status", "").strip() == "A"

        data = {
            "is_federal_contractor": True,
            "uei": sam_row.get("uei"),
            "legal_name": sam_row.get("legal_business_name"),
            "dba_name": sam_row.get("dba_name"),
            "status_active": is_active,
            "registration_date": sam_row.get("registration_date"),
            "expiration_date": sam_row.get("expiration_date"),
            "naics_primary": sam_row.get("naics_primary"),
            "naics_all": sam_row.get("naics_all"),
            "entity_structure": sam_row.get("entity_structure"),
            "physical_state": sam_row.get("physical_state"),
            "physical_city": sam_row.get("physical_city"),
        }
        if contract_data:
            data["total_obligations"] = contract_data["total_obligations"]
            data["total_contracts"] = contract_data["total_contracts"]
            data["latest_contract_year"] = contract_data["latest_year"]

        summary = f"Federal contractor: {data['legal_name']}. "
        summary += "Active" if is_active else "Inactive"
        summary += f". NAICS {data.get('naics_primary', 'N/A')}."
        if contract_data:
            summary += f" ${data['total_obligations']:,.0f} in federal obligations across {data['total_contracts']} contracts."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 6: search_990
# ---------------------------------------------------------------------------

def search_990(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    company_type: Optional[str] = None,
    **_kw,
) -> dict:
    """Search IRS Form 990 data for nonprofit financial information."""
    source = "database:national_990_filers"
    try:
        if company_type and company_type.lower() == "public":
            return {"found": False, "source": source,
                    "summary": "Skipped: company_type is 'public' (publicly traded companies don't file 990s).",
                    "data": {}, "skipped": True}

        conn = _conn()
        cur = conn.cursor()

        rows = []
        if employer_id:
            # Via match table
            cur.execute("""
                SELECT n.* FROM national_990_filers n
                JOIN national_990_f7_matches m ON m.ein = n.ein
                WHERE m.f7_employer_id = %s
                ORDER BY n.tax_year DESC
            """, (employer_id,))
            rows = cur.fetchall()

        if not rows:
            like_pat = f"%{company_name.upper()}%"
            cur.execute("""
                SELECT * FROM national_990_filers
                WHERE UPPER(business_name) LIKE %s
                ORDER BY tax_year DESC
                LIMIT 10
            """, (like_pat,))
            rows = cur.fetchall()

        if not rows:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No IRS 990 records found for this employer.", "data": {}}

        latest = _safe_dict(rows[0])

        data = {
            "ein": latest.get("ein"),
            "business_name": latest.get("business_name"),
            "total_revenue": latest.get("total_revenue"),
            "total_assets": latest.get("total_assets"),
            "total_expenses": latest.get("total_expenses"),
            "total_employees": latest.get("total_employees"),
            "tax_year": latest.get("tax_year"),
            "form_type": latest.get("form_type"),
            "ntee_code": latest.get("ntee_code"),
            "state": latest.get("state"),
            "city": latest.get("city"),
            "years_available": [_safe(r["tax_year"]) for r in rows],
        }

        summary = f"990 filer: {data['business_name']} (EIN {data['ein']}). "
        if data["total_revenue"]:
            summary += f"Revenue: ${data['total_revenue']:,.0f}. "
        if data["total_assets"]:
            summary += f"Assets: ${data['total_assets']:,.0f}. "
        if data["total_employees"]:
            summary += f"Employees: {data['total_employees']:,}. "
        summary += f"Tax year {data['tax_year']}."

        conn.close()
        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 7: search_contracts
# ---------------------------------------------------------------------------

def search_contracts(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Search F-7 data for existing union contracts at this employer."""
    source = "database:f7_union_employer_relations"
    try:
        conn = _conn()
        cur = conn.cursor()

        if employer_id:
            cur.execute("""
                SELECT r.employer_id, r.union_file_number, r.bargaining_unit_size,
                       r.notice_date,
                       u.union_name, u.aff_abbr, u.members AS union_members,
                       u.city AS union_city, u.state AS union_state
                FROM f7_union_employer_relations r
                LEFT JOIN unions_master u ON u.f_num = CAST(r.union_file_number AS TEXT)
                WHERE r.employer_id = %s
                ORDER BY r.notice_date DESC NULLS LAST
            """, (employer_id,))
        else:
            # Try through f7_employers_deduped name search
            like_pat = f"%{company_name.upper()}%"
            cur.execute("""
                SELECT r.employer_id, r.union_file_number, r.bargaining_unit_size,
                       r.notice_date,
                       u.union_name, u.aff_abbr, u.members AS union_members,
                       u.city AS union_city, u.state AS union_state
                FROM f7_union_employer_relations r
                JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
                LEFT JOIN unions_master u ON u.f_num = CAST(r.union_file_number AS TEXT)
                WHERE UPPER(e.employer_name) LIKE %s
                ORDER BY r.notice_date DESC NULLS LAST
                LIMIT 50
            """, (like_pat,))

        rows = _safe_list(cur.fetchall())
        conn.close()

        if not rows:
            return {"found": False, "source": source,
                    "summary": "No union contracts found for this employer.", "data": {}}

        # Summarize
        union_names = list({r["union_name"] for r in rows if r.get("union_name")})
        affiliations = list({r["aff_abbr"] for r in rows if r.get("aff_abbr")})
        total_workers = sum(r.get("bargaining_unit_size") or 0 for r in rows)

        data = {
            "has_contracts": True,
            "contract_count": len(rows),
            "contracts": rows[:20],
            "union_names": union_names,
            "affiliations": affiliations,
            "total_workers_covered": total_workers,
            "distinct_unions": len(union_names),
        }

        summary = f"{len(rows)} union contract(s). "
        summary += f"{len(union_names)} distinct union(s): {', '.join(union_names[:5])}. "
        summary += f"{total_workers:,} workers covered."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 8: get_industry_profile
# ---------------------------------------------------------------------------

def get_industry_profile(
    company_name: str,
    *,
    naics: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Get BLS occupation and wage data for this employer's industry."""
    source = "database:bls_industry_occupation_matrix"
    try:
        if not naics:
            return {"found": False, "source": source,
                    "summary": "Cannot look up industry profile without a NAICS code.",
                    "data": {}}

        conn = _conn()
        cur = conn.cursor()

        # Map NAICS to BLS industry code
        cur.execute("""
            SELECT bls_industry_code, match_type
            FROM naics_to_bls_industry
            WHERE naics_code = %s
            LIMIT 1
        """, (naics,))
        mapping = cur.fetchone()

        # Try prefix fallback (4-digit, 3-digit, 2-digit)
        if not mapping and len(naics) > 2:
            for length in [4, 3, 2]:
                prefix = naics[:length]
                cur.execute("""
                    SELECT bls_industry_code, match_type
                    FROM naics_to_bls_industry
                    WHERE naics_code = %s
                    LIMIT 1
                """, (prefix,))
                mapping = cur.fetchone()
                if mapping:
                    break

        if not mapping:
            conn.close()
            return {"found": False, "source": source,
                    "summary": f"No BLS industry mapping found for NAICS {naics}.",
                    "data": {}}

        bls_code = mapping["bls_industry_code"]

        # Top occupations
        cur.execute("""
            SELECT occupation_title, occupation_code,
                   percent_of_industry, employment_2024,
                   employment_change_pct
            FROM bls_industry_occupation_matrix
            WHERE industry_code = %s
              AND LOWER(occupation_type) = 'line item'
            ORDER BY percent_of_industry DESC NULLS LAST
            LIMIT 10
        """, (bls_code,))
        occupations = _safe_list(cur.fetchall())

        # Map NAICS 2-digit prefix to BLS density sector codes
        _NAICS_TO_DENSITY_SECTOR = {
            "11": "CONST",   # Agriculture -> closest
            "21": "CONST",   # Mining -> closest
            "23": "CONST",   # Construction
            "31": "MFG", "32": "MFG", "33": "MFG",  # Manufacturing
            "42": "WHOLESALE",
            "44": "RETAIL", "45": "RETAIL",
            "48": "TRANS_UTIL", "49": "TRANS_UTIL",
            "51": "PROF_BUS",  # Information
            "52": "FINANCE", "53": "FINANCE",
            "54": "PROF_BUS", "55": "PROF_BUS", "56": "PROF_BUS",
            "61": "EDU_HEALTH", "62": "EDU_HEALTH",
            "71": "LEISURE", "72": "LEISURE",
            "81": "PROF_BUS",  # Other services
            "92": "EDU_HEALTH",  # Government -> closest
        }
        density_sector = _NAICS_TO_DENSITY_SECTOR.get(naics[:2])

        # National union density for this industry
        national_density = None
        if density_sector:
            cur.execute("""
                SELECT union_density_pct, industry_name, year
                FROM bls_national_industry_density
                WHERE industry_code = %s
                ORDER BY year DESC LIMIT 1
            """, (density_sector,))
            density = cur.fetchone()
            national_density = _safe_dict(density) if density else None

        # State-level density
        state_density = None
        if state and density_sector:
            cur.execute("""
                SELECT estimated_density, confidence, year
                FROM estimated_state_industry_density
                WHERE industry_code = %s AND state = %s
                ORDER BY year DESC LIMIT 1
            """, (density_sector, state.upper()))
            sd = cur.fetchone()
            if sd:
                state_density = _safe_dict(sd)

        conn.close()

        data = {
            "naics_code": naics,
            "bls_industry_code": bls_code,
            "top_occupations": occupations,
            "national_density": national_density,
            "state_density": state_density,
        }

        summary = f"Industry {bls_code} ({national_density['industry_name'] if national_density else 'N/A'}). "
        if occupations:
            top3 = ", ".join(f"{o['occupation_title']} ({o['percent_of_industry']}%)" for o in occupations[:3])
            summary += f"Top occupations: {top3}. "
        if national_density:
            summary += f"National union density: {national_density['union_density_pct']}%."
        if state_density:
            summary += f" State ({state}) estimated density: {state_density['estimated_density']}%."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 9: get_similar_employers
# ---------------------------------------------------------------------------

def get_similar_employers(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    naics: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Find comparable employers in the same industry that have been organized."""
    source = "database:f7_employers_deduped"
    try:
        conn = _conn()
        cur = conn.cursor()

        # We need a NAICS to compare; try to resolve it
        resolved_naics = naics
        if not resolved_naics and employer_id:
            cur.execute("SELECT naics FROM f7_employers_deduped WHERE employer_id = %s", (employer_id,))
            r = cur.fetchone()
            if r and r["naics"]:
                resolved_naics = r["naics"]

        if not resolved_naics:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "Cannot find similar employers without a NAICS code.",
                    "data": {}}

        # Find employers in the same 4-digit NAICS with union contracts
        naics_prefix = resolved_naics[:4]
        cur.execute("""
            SELECT e.employer_id, e.employer_name, e.naics, e.state, e.city,
                   e.latest_unit_size,
                   s.weighted_score, s.score_tier,
                   COUNT(r.id) AS contract_count,
                   SUM(r.bargaining_unit_size) AS total_bu_workers
            FROM f7_employers_deduped e
            JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
            LEFT JOIN mv_unified_scorecard s ON s.employer_id = e.employer_id
            WHERE e.naics LIKE %s
              AND e.employer_id != COALESCE(%s, '')
            GROUP BY e.employer_id, e.employer_name, e.naics, e.state, e.city,
                     e.latest_unit_size, s.weighted_score, s.score_tier
            ORDER BY s.weighted_score DESC NULLS LAST
            LIMIT 10
        """, (f"{naics_prefix}%", employer_id or ''))
        similar = _safe_list(cur.fetchall())

        # Also check for recent NLRB elections in this industry
        cur.execute("""
            SELECT p.participant_name, p.state, e.election_date,
                   e.union_won, e.eligible_voters
            FROM nlrb_elections e
            JOIN nlrb_participants p
              ON p.case_number = e.case_number
             AND p.participant_type LIKE '%%Employer%%'
            WHERE e.election_date >= CURRENT_DATE - INTERVAL '3 years'
            ORDER BY e.election_date DESC
            LIMIT 10
        """)
        recent_elections = _safe_list(cur.fetchall())

        conn.close()

        data = {
            "similar_employers": similar,
            "naics_prefix": naics_prefix,
            "recent_industry_elections": recent_elections,
        }

        summary = f"{len(similar)} similar employers found in NAICS {naics_prefix}xxx. "
        if similar:
            summary += f"Top: {similar[0]['employer_name']} (score {similar[0].get('weighted_score', 'N/A')}). "
        summary += f"{len(recent_elections)} recent NLRB elections in similar industries."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 10: search_mergent
# ---------------------------------------------------------------------------

def search_mergent(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search Mergent Intellect business data."""
    source = "database:mergent_employers"
    try:
        conn = _conn()
        cur = conn.cursor()

        row = None
        if employer_id:
            # Via unified_match_log
            cur.execute("""
                SELECT source_id FROM unified_match_log
                WHERE source_system = 'mergent'
                  AND target_id = %s
                  AND status = 'active'
                LIMIT 1
            """, (employer_id,))
            r = cur.fetchone()
            if r:
                cur.execute("SELECT * FROM mergent_employers WHERE duns = %s LIMIT 1",
                            (r["source_id"],))
                row = cur.fetchone()

        if not row:
            like_pat = f"%{company_name.upper()}%"
            q = "SELECT * FROM mergent_employers WHERE UPPER(company_name) LIKE %s"
            params: list = [like_pat]
            if state:
                q += " AND state = %s"
                params.append(state.upper())
            q += " ORDER BY employees_all_sites DESC NULLS LAST LIMIT 1"
            cur.execute(q, params)
            row = cur.fetchone()

        if not row:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No Mergent record found for this employer.", "data": {}}

        row = _safe_dict(row)
        conn.close()

        data = {
            "company_name": row.get("company_name"),
            "duns": row.get("duns"),
            "ein": row.get("ein"),
            "employees_site": row.get("employees_site"),
            "employees_all_sites": row.get("employees_all_sites"),
            "sales_amount": row.get("sales_amount"),
            "sales_raw": row.get("sales_raw"),
            "parent_name": row.get("parent_name"),
            "domestic_parent_name": row.get("domestic_parent_name"),
            "parent_duns": row.get("parent_duns"),
            "naics_primary": row.get("naics_primary"),
            "naics_primary_desc": row.get("naics_primary_desc"),
            "year_founded": row.get("year_founded"),
            "company_type": row.get("company_type"),
            "subsidiary_status": row.get("subsidiary_status"),
            "location_type": row.get("location_type"),
            "state": row.get("state"),
            "city": row.get("city"),
        }

        summary = f"Mergent: {data['company_name']}. "
        if data.get("employees_all_sites"):
            summary += f"{data['employees_all_sites']:,} employees (all sites). "
        if data.get("sales_amount"):
            summary += f"Revenue: ${data['sales_amount']:,.0f}. "
        if data.get("parent_name"):
            summary += f"Parent: {data['parent_name']}. "
        summary += f"NAICS {data.get('naics_primary', 'N/A')}: {data.get('naics_primary_desc', 'N/A')}."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 11: search_web  (executed BY Claude via built-in web search)
# ---------------------------------------------------------------------------
# This tool is NOT called locally — it is defined as a tool_definition for
# the Claude API.  When Claude decides to use it, the orchestrator delegates
# to Claude's built-in web search capability.  We still define a stub here
# so the tool registry is complete.

def search_web(company_name: str, query: Optional[str] = None, **_kw) -> dict:
    """Stub — web search is handled via the Claude API's built-in web search tool.
    The agent orchestration loop intercepts this and uses the Anthropic API."""
    return {
        "found": False,
        "source": "web_search",
        "summary": "Web search must be executed through the Claude API built-in tool.",
        "data": {},
        "error": "Not callable locally — use Claude API web search.",
    }


# ---------------------------------------------------------------------------
# TOOL 12: scrape_employer_website  (deferred to Phase 2 / Crawl4AI)
# ---------------------------------------------------------------------------

def scrape_employer_website(company_name: str, url: Optional[str] = None, **_kw) -> dict:
    """Stub — website scraping requires Crawl4AI async runtime.
    Will be implemented when the full agent loop is in place."""
    return {
        "found": False,
        "source": "web_scrape",
        "summary": "Website scraping is not yet implemented (Phase 2).",
        "data": {},
        "error": "Not yet implemented.",
    }


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------
# Maps tool names (used in Claude API tool definitions) to callables.
# The agent orchestration loop uses this to dispatch tool calls.

TOOL_REGISTRY: dict[str, callable] = {
    "search_osha": search_osha,
    "search_nlrb": search_nlrb,
    "search_whd": search_whd,
    "search_sec": search_sec,
    "search_sam": search_sam,
    "search_990": search_990,
    "search_contracts": search_contracts,
    "get_industry_profile": get_industry_profile,
    "get_similar_employers": get_similar_employers,
    "search_mergent": search_mergent,
    "search_web": search_web,
    "scrape_employer_website": scrape_employer_website,
}


# ---------------------------------------------------------------------------
# Claude API Tool Definitions
# ---------------------------------------------------------------------------
# These are passed to the Anthropic API as the tools array. Claude uses these
# schemas to decide which tools to call and with what arguments.

TOOL_DEFINITIONS = [
    {
        "name": "search_osha",
        "description": "Search OSHA tables for workplace safety violations at this employer. Returns violation counts, penalty totals, serious/willful/repeat breakdowns, top violation types, and workplace accidents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known (more precise)"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_nlrb",
        "description": "Search NLRB tables for union election history and unfair labor practice (ULP) charges. Returns election outcomes, vote counts, ULP allegations, voluntary recognitions, and which unions were involved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_whd",
        "description": "Search DOL Wage & Hour Division records for wage theft cases. Returns case counts, back wages owed, civil penalties, employees affected, repeat violator status, and child labor violations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_sec",
        "description": "Search SEC EDGAR for public company financial data. Returns company info, SIC code, ticker, exchange, and cross-referenced federal contractor status. Skip for private/nonprofit companies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "company_type": {"type": "string", "description": "public/private/nonprofit — if private or nonprofit, this tool will be skipped"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_sam",
        "description": "Search SAM.gov for federal contractor registration and USASpending contract amounts. Returns registration status, contract totals, NAICS codes, and entity structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_990",
        "description": "Search IRS Form 990 data for nonprofit financial information. Returns revenue, assets, employees, NTEE code. Skip for publicly traded companies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company or nonprofit name"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "company_type": {"type": "string", "description": "If 'public', this tool will be skipped"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_contracts",
        "description": "Search F-7 data for existing union contracts at this employer. Returns contract counts, union names, bargaining unit sizes, and affiliations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known (recommended for precision)"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "get_industry_profile",
        "description": "Get BLS occupation mix, wage data, and union density for a given NAICS industry code. Requires a NAICS code. Returns top occupations, national and state union density.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "naics": {"type": "string", "description": "NAICS code (2-6 digits). Required."},
                "state": {"type": "string", "description": "2-letter state code for state-level density"},
            },
            "required": ["company_name", "naics"],
        },
    },
    {
        "name": "get_similar_employers",
        "description": "Find comparable employers in the same industry that have been organized (have union contracts). Also returns recent NLRB elections in similar industries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "naics": {"type": "string", "description": "NAICS code for industry comparison"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_mergent",
        "description": "Search Mergent Intellect for business data including employee counts, revenue, parent company, DUNS number, and industry classification. Good for private companies not in SEC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_web",
        "description": "Search the web for recent news, labor developments, and company information. Use for current events not in government databases: layoffs, organizing campaigns, strikes, worker complaints, company descriptions. Provide a specific search query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "query": {"type": "string", "description": "Specific search query to run. Include the company name and topic, e.g. '\"Amazon\" workers union organizing 2025'"},
            },
            "required": ["company_name", "query"],
        },
    },
    {
        "name": "scrape_employer_website",
        "description": "Scrape the employer's website for company info, job postings, leadership, and locations. Provide the URL if known. (Currently a placeholder — returns no data.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "url": {"type": "string", "description": "Company website URL if known"},
            },
            "required": ["company_name"],
        },
    },
]


# ---------------------------------------------------------------------------
# Quick self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    print("=== Research Agent Tools Self-Test ===\n")
    print(f"Registered tools: {list(TOOL_REGISTRY.keys())}")
    print(f"Tool definitions: {len(TOOL_DEFINITIONS)}")
    print()

    # Test with a known employer — pick one with good data coverage
    test_name = "AMAZON"
    test_id = None  # Will use name search

    for tool_name in ["search_osha", "search_nlrb", "search_whd"]:
        print(f"--- {tool_name}('{test_name}') ---")
        result = TOOL_REGISTRY[tool_name](test_name, state="NY")
        print(f"  found: {result['found']}")
        print(f"  summary: {result['summary'][:200]}")
        if result["found"]:
            print(f"  data keys: {list(result['data'].keys())}")
        print()
