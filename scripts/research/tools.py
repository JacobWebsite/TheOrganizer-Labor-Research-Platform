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
import re
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


_ACRONYM_STOP_WORDS = frozenset({
    "OF", "THE", "AND", "FOR", "IN", "AT", "BY", "TO", "A", "AN",
    "INC", "LLC", "CORP", "LTD", "CO", "COMPANY", "CORPORATION",
    "GROUP", "SERVICES", "SYSTEMS", "SYSTEM",
})


def _make_acronym(company_name: str) -> Optional[str]:
    """Generate a plausible acronym from a multi-word company name.

    Returns the acronym (e.g. "UPMC" from "University of Pittsburgh
    Medical Center") or None if the name is too short or the acronym
    would be ambiguous (< 3 chars).
    """
    upper = company_name.upper().strip()
    # Strip common corporate suffixes before acronym extraction
    for suffix in (", INC.", ", INC", " INC.", " INC", ", LLC", " LLC",
                   ", CORP.", ", CORP", " CORP.", " CORP", ", LTD", " LTD"):
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)]

    words = re.split(r"[\s\-/]+", upper)
    significant = [w for w in words if w and w not in _ACRONYM_STOP_WORDS]

    if len(significant) < 3:
        return None

    acronym = "".join(w[0] for w in significant)
    # Only useful if 3-7 chars (short enough to be a real abbreviation)
    if len(acronym) < 3 or len(acronym) > 7:
        return None
    return acronym


def _name_like_clause(column: str, company_name: str) -> tuple[str, list[str]]:
    """Build a flexible LIKE clause that handles spaces and common variations.

    Returns (sql_fragment, params_list).  The SQL uses OR to search for:
      - The original name as-is  (substring match)
      - The name with spaces removed  (catches "Fed Ex" -> "FEDEX")
      - An acronym as prefix match  (catches "University of Pittsburgh
        Medical Center" -> records starting with "UPMC")

    Example:
        sql, params = _name_like_clause("UPPER(estab_name)", "Fed Ex")
        # sql   = "(UPPER(estab_name) LIKE %s OR UPPER(estab_name) LIKE %s)"
        # params = ['%FED EX%', '%FEDEX%']
    """
    upper = company_name.upper().strip()
    nospace = upper.replace(" ", "")

    patterns = [f"%{upper}%"]
    if nospace != upper:
        patterns.append(f"%{nospace}%")

    # Add acronym prefix pattern for long multi-word names
    acronym = _make_acronym(company_name)
    if acronym:
        # Prefix match: catches "UPMC BEDFORD", "UPMC EAST", etc.
        patterns.append(f"{acronym}%")

    clauses = " OR ".join(f"{column} LIKE %s" for _ in patterns)
    return f"({clauses})", patterns


def _filter_by_name_similarity(rows, company_name, name_column, threshold=0.50):
    """Post-query filter using RapidFuzz token_sort_ratio.

    Applied only on name-based fallback paths (not employer_id paths) to
    remove false matches like "Federal Express Employees Credit Union"
    matching "FedEx".  Threshold 0.50 is intentionally lenient — the LIKE
    clause already did rough filtering.
    """
    from rapidfuzz import fuzz
    upper = company_name.upper().strip()
    return [
        r for r in rows
        if fuzz.token_sort_ratio(upper, (r.get(name_column) or r[name_column] or "").upper()) >= threshold * 100
    ]


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
            name_clause, name_params = _name_like_clause("UPPER(estab_name)", company_name)
            if state:
                cur.execute(f"""
                    SELECT establishment_id, estab_name FROM osha_establishments
                    WHERE {name_clause} AND site_state = %s
                    LIMIT 50
                """, (*name_params, state.upper()))
            else:
                cur.execute(f"""
                    SELECT establishment_id, estab_name FROM osha_establishments
                    WHERE {name_clause}
                    LIMIT 50
                """, name_params)
            matched = _filter_by_name_similarity(cur.fetchall(), company_name, "estab_name")
            estab_ids = [r["establishment_id"] for r in matched]

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
                 AND p.participant_type = 'Employer'
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
            name_clause, name_params = _name_like_clause("UPPER(participant_name)", company_name)
            if state:
                cur.execute(f"""
                    SELECT DISTINCT case_number, participant_name FROM nlrb_participants
                    WHERE {name_clause}
                      AND participant_type = 'Employer'
                      AND UPPER(state) = %s
                    LIMIT 200
                """, (*name_params, state.upper()))
            else:
                cur.execute(f"""
                    SELECT DISTINCT case_number, participant_name FROM nlrb_participants
                    WHERE {name_clause}
                      AND participant_type = 'Employer'
                    LIMIT 200
                """, name_params)
            filtered = _filter_by_name_similarity(cur.fetchall(), company_name, "participant_name")
            case_numbers.update(r["case_number"] for r in filtered)

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

        # Enrich elections with employer names from participants
        election_case_nums = list({r["case_number"] for r in elections_raw})
        employer_names_by_case = {}
        if election_case_nums:
            cur.execute("""
                SELECT case_number, participant_name
                FROM nlrb_participants
                WHERE case_number = ANY(%s)
                  AND participant_type = 'Employer'
            """, (election_case_nums,))
            for r in cur.fetchall():
                employer_names_by_case.setdefault(r["case_number"], []).append(r["participant_name"])

        # Deduplicate by case_number (keep first = most recent)
        seen_cases = set()
        elections = []
        for row in elections_raw:
            cn = row["case_number"]
            if cn not in seen_cases:
                seen_cases.add(cn)
                # Add employer name
                emp_names = employer_names_by_case.get(cn, [])
                row["employer_name"] = emp_names[0] if emp_names else None
                # Add outcome string
                if row.get("union_won") is True:
                    row["outcome"] = "Union Won"
                elif row.get("union_won") is False:
                    row["outcome"] = "Union Lost"
                else:
                    row["outcome"] = "Pending"
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
        vr_clause, vr_params = _name_like_clause("UPPER(employer_name)", company_name)
        cur.execute(f"""
            SELECT vr_case_number, employer_name, union_name,
                   date_voluntary_recognition, num_employees,
                   unit_city, unit_state, unit_description
            FROM nlrb_voluntary_recognition
            WHERE {vr_clause}
               OR matched_employer_id = %s
            ORDER BY date_voluntary_recognition DESC
        """, (*vr_params, employer_id or ''))
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
            legal_clause, legal_params = _name_like_clause("UPPER(legal_name)", company_name)
            trade_clause, trade_params = _name_like_clause("UPPER(trade_name)", company_name)
            q = f"""
                SELECT id, legal_name, trade_name FROM whd_cases
                WHERE ({legal_clause} OR {trade_clause})
            """
            params: list = [*legal_params, *trade_params]
            if state:
                q += " AND state = %s"
                params.append(state.upper())
            q += " LIMIT 100"
            cur.execute(q, params)
            raw = cur.fetchall()
            # Filter: either legal_name or trade_name must be similar
            from rapidfuzz import fuzz
            upper_cn = company_name.upper().strip()
            filtered = [
                r for r in raw
                if fuzz.token_sort_ratio(upper_cn, (r.get("legal_name") or "").upper()) >= 50
                or fuzz.token_sort_ratio(upper_cn, (r.get("trade_name") or "").upper()) >= 50
            ]
            case_ids = [r["id"] for r in filtered]

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
            name_clause, name_params = _name_like_clause("UPPER(company_name)", company_name)
            # Prefer public companies and shorter names (less likely to be
            # asset-backed securities or subsidiary filings)
            cur.execute(f"""
                SELECT * FROM sec_companies
                WHERE {name_clause}
                ORDER BY is_public DESC NULLS LAST,
                         LENGTH(company_name) ASC
                LIMIT 1
            """, name_params)
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
            name_clause, name_params = _name_like_clause("UPPER(legal_business_name)", company_name)
            q = f"SELECT * FROM sam_entities WHERE {name_clause}"
            params: list = list(name_params)
            if state:
                q += " AND physical_state = %s"
                params.append(state.upper())
            q += " ORDER BY last_update_date DESC NULLS LAST LIMIT 5"
            cur.execute(q, params)
            candidates = cur.fetchall()
            candidates = _filter_by_name_similarity(candidates, company_name, "legal_business_name")
            sam_row = candidates[0] if candidates else None

        if not sam_row:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No SAM.gov registration found for this employer.", "data": {}}

        sam_row = _safe_dict(sam_row)

        # Check federal_contract_recipients for dollar amounts
        contract_data = None
        fcr_clause, fcr_params = _name_like_clause("UPPER(recipient_name)", company_name)
        cur.execute(f"""
            SELECT SUM(total_obligations) AS total_obligations,
                   SUM(contract_count) AS total_contracts,
                   MAX(fiscal_year) AS latest_year
            FROM federal_contract_recipients
            WHERE {fcr_clause}
        """, fcr_params)
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
            name_clause, name_params = _name_like_clause("UPPER(business_name)", company_name)
            cur.execute(f"""
                SELECT * FROM national_990_filers
                WHERE {name_clause}
                ORDER BY tax_year DESC
                LIMIT 10
            """, name_params)
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
            name_clause, name_params = _name_like_clause("UPPER(e.employer_name)", company_name)
            cur.execute(f"""
                SELECT r.employer_id, r.union_file_number, r.bargaining_unit_size,
                       r.notice_date,
                       u.union_name, u.aff_abbr, u.members AS union_members,
                       u.city AS union_city, u.state AS union_state,
                       e.employer_name
                FROM f7_union_employer_relations r
                JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
                LEFT JOIN unions_master u ON u.f_num = CAST(r.union_file_number AS TEXT)
                WHERE {name_clause}
                ORDER BY r.notice_date DESC NULLS LAST
                LIMIT 100
            """, name_params)

        raw_rows = cur.fetchall()
        # Filter name-based results by similarity (employer_id path skips this)
        if not employer_id:
            raw_rows = _filter_by_name_similarity(raw_rows, company_name, "employer_name")
        rows = _safe_list(raw_rows)
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
             AND p.participant_type = 'Employer'
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
            name_clause, name_params = _name_like_clause("UPPER(company_name)", company_name)
            q = f"SELECT * FROM mergent_employers WHERE {name_clause}"
            params: list = list(name_params)
            if state:
                q += " AND state = %s"
                params.append(state.upper())
            q += " ORDER BY employees_all_sites DESC NULLS LAST LIMIT 5"
            cur.execute(q, params)
            candidates = cur.fetchall()
            candidates = _filter_by_name_similarity(candidates, company_name, "company_name")
            row = candidates[0] if candidates else None

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
            "website": row.get("website"),
            "phone": row.get("phone"),
            "street_address": row.get("street_address"),
            "zip": row.get("zip"),
            "county": row.get("county"),
            "trade_name": row.get("trade_name"),
            "former_name": row.get("former_name"),
            "line_of_business": row.get("line_of_business"),
            "minority_owned": row.get("minority_owned"),
        }

        summary = f"Mergent: {data['company_name']}. "
        if data.get("employees_all_sites"):
            summary += f"{data['employees_all_sites']:,} employees (all sites). "
        if data.get("sales_amount"):
            summary += f"Revenue: ${data['sales_amount']:,.0f}. "
        if data.get("parent_name"):
            summary += f"Parent: {data['parent_name']}. "
        if data.get("website"):
            summary += f"Website: {data['website']}. "
        summary += f"NAICS {data.get('naics_primary', 'N/A')}: {data.get('naics_primary_desc', 'N/A')}."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 11: search_web  (replaced by Gemini Google Search grounding)
# ---------------------------------------------------------------------------
# Web search is now handled by Gemini's native Google Search grounding tool,
# which is passed alongside function declarations in agent.py._build_gemini_tools().
# Gemini automatically searches the web when it needs current information.
# This stub is kept for backward compatibility with the TOOL_REGISTRY.

def search_web(company_name: str, query: Optional[str] = None, **_kw) -> dict:
    """Stub — web search is handled by Gemini Google Search grounding.
    This function is not called directly; Gemini uses its built-in search."""
    return {
        "found": False,
        "source": "web_search",
        "summary": "Web search is handled by Gemini Google Search grounding (not a function call).",
        "data": {},
        "error": "Not callable locally — handled by Gemini grounding.",
    }


# ---------------------------------------------------------------------------
# TOOL 12: scrape_employer_website  (Crawl4AI)
# ---------------------------------------------------------------------------

# Page budgets: (paths_to_try, char_limit)
_SCRAPE_PAGES = [
    ("homepage", ["/"], 3000),
    ("about", ["/about", "/about-us", "/company"], 2500),
    ("careers", ["/careers", "/jobs"], 1500),
    ("news", ["/news", "/press", "/newsroom"], 1000),
]
_SCRAPE_TOTAL_BUDGET = 8000
_SCRAPE_TIMEOUT = 28.0  # seconds — guarantees return within ~30s


def _normalize_url(raw: Optional[str]) -> Optional[str]:
    """Normalise a URL from Mergent or user input.

    Mergent stores values like ``WWW.COMPANY.COM`` or ``N/A``.
    Returns a clean ``https://...`` URL or None.
    """
    if not raw:
        return None
    cleaned = str(raw).strip()
    if not cleaned or cleaned.upper() in ("N/A", "NA", "NAN", "NONE", "NULL", ""):
        return None
    cleaned = cleaned.lower()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    return cleaned.rstrip("/")


def _resolve_employer_url(
    company_name: str,
    url: Optional[str] = None,
    employer_id: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Three-tier URL resolution. Returns (url, url_source)."""
    # Tier 1: provided URL
    if url:
        norm = _normalize_url(url)
        if norm:
            return norm, "provided"

    # Tier 2: Mergent via employer_id -> unified_match_log -> mergent_employers
    if employer_id:
        try:
            conn = _conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT source_id FROM unified_match_log
                WHERE source_system = 'mergent'
                  AND target_id = %s
                  AND status = 'active'
                LIMIT 1
            """, (employer_id,))
            r = cur.fetchone()
            if r:
                cur.execute(
                    "SELECT website FROM mergent_employers WHERE duns = %s LIMIT 1",
                    (r["source_id"],),
                )
                mr = cur.fetchone()
                if mr:
                    norm = _normalize_url(mr.get("website"))
                    if norm:
                        conn.close()
                        return norm, "mergent_db"
            conn.close()
        except Exception as exc:
            _log.debug("Tier-2 URL lookup failed: %s", exc)

    # Tier 3: Mergent by company name
    try:
        conn = _conn()
        cur = conn.cursor()
        name_clause, name_params = _name_like_clause("UPPER(company_name)", company_name)
        cur.execute(f"""
            SELECT company_name, website FROM mergent_employers
            WHERE {name_clause} AND website IS NOT NULL AND website != ''
            ORDER BY employees_all_sites DESC NULLS LAST
            LIMIT 5
        """, name_params)
        candidates = cur.fetchall()
        candidates = _filter_by_name_similarity(candidates, company_name, "company_name")
        conn.close()
        if candidates:
            norm = _normalize_url(candidates[0].get("website"))
            if norm:
                return norm, "name_search"
    except Exception as exc:
        _log.debug("Tier-3 URL lookup failed: %s", exc)

    return None, "none"


def _sanitize_markdown(text: str) -> str:
    """Replace Unicode chars that break Windows cp1252 with ASCII equivalents."""
    replacements = {
        "\u2192": "->", "\u2190": "<-", "\u2194": "<->",
        "\u2013": "-", "\u2014": "--", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
        "\u2022": "*", "\u2023": ">", "\u25aa": "*", "\u25cf": "*",
        "\u2713": "[x]", "\u2717": "[ ]", "\u00b7": "*",
    }
    for char, repl in replacements.items():
        text = text.replace(char, repl)
    # Strip any remaining non-ASCII that could cause encoding errors
    return text.encode("ascii", errors="replace").decode("ascii")


def _truncate_markdown(text: str, limit: int) -> str:
    """Truncate markdown at a paragraph or sentence boundary."""
    if not text or len(text) <= limit:
        return text or ""
    # Try paragraph boundary
    cut = text.rfind("\n\n", 0, limit)
    if cut > limit * 0.5:
        return text[:cut].rstrip()
    # Try sentence boundary
    for sep in (". ", ".\n", "! ", "? "):
        cut = text.rfind(sep, 0, limit)
        if cut > limit * 0.3:
            return text[: cut + 1].rstrip()
    # Hard cut at word boundary
    cut = text.rfind(" ", 0, limit)
    if cut > 0:
        return text[:cut].rstrip() + "..."
    return text[:limit]


async def _scrape_pages(base_url: str) -> dict:
    """Async core — scrape homepage + subpages with Crawl4AI.

    Returns a dict with keys: homepage_text, about_text, careers_text,
    news_text, pages_scraped, total_chars, url.
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    browser_cfg = BrowserConfig(
        headless=True,
        user_agent="LaborResearchPlatform/1.0 (Academic Research; contact: jakewartel@gmail.com)",
    )
    run_cfg = CrawlerRunConfig(
        page_timeout=15000,
        wait_until="domcontentloaded",
        cache_mode=CacheMode.BYPASS,
        check_robots_txt=True,
        verbose=False,
    )

    result_data = {
        "url": base_url,
        "homepage_text": None,
        "about_text": None,
        "careers_text": None,
        "news_text": None,
        "pages_scraped": 0,
        "total_chars": 0,
    }

    import asyncio as _aio

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for page_key, paths, char_limit in _SCRAPE_PAGES:
            text = None
            for path in paths:
                page_url = base_url.rstrip("/") + path if path != "/" else base_url
                try:
                    res = await crawler.arun(url=page_url, config=run_cfg)
                    if res.success:
                        raw = ""
                        if res.markdown:
                            raw = (
                                res.markdown.raw_markdown
                                if hasattr(res.markdown, "raw_markdown")
                                else str(res.markdown)
                            )
                        if raw and len(raw.strip()) > 100:
                            text = _truncate_markdown(
                                _sanitize_markdown(raw.strip()), char_limit
                            )
                            break
                except Exception:
                    pass
                await _aio.sleep(0.5)

            data_key = f"{page_key}_text"
            if text:
                result_data[data_key] = text
                result_data["pages_scraped"] += 1
                result_data["total_chars"] += len(text)
            else:
                result_data[data_key] = None

            # Homepage is required — if it failed, stop early
            if page_key == "homepage" and not text:
                return result_data

            # Respect total budget
            if result_data["total_chars"] >= _SCRAPE_TOTAL_BUDGET:
                break

    return result_data


def scrape_employer_website(
    company_name: str,
    *,
    url: Optional[str] = None,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Scrape the employer's website for company info, leadership, careers, and news."""
    source = "web_scrape:employer_website"
    try:
        from crawl4ai import AsyncWebCrawler  # noqa: F401 — availability check
    except ImportError:
        return {
            "found": False,
            "source": source,
            "summary": "Crawl4AI not installed.",
            "data": {},
            "error": "Crawl4AI not installed.",
        }

    try:
        resolved_url, url_source = _resolve_employer_url(company_name, url, employer_id)
        if not resolved_url:
            return {
                "found": False,
                "source": source,
                "summary": f"No website URL found for {company_name}.",
                "data": {"url_source": "none"},
            }

        import asyncio
        import io

        # Crawl4AI prints Unicode chars (arrows, etc.) during browser init.
        # Windows cp1252 stdout can't encode them, so redirect to devnull.
        _orig_stdout, _orig_stderr = sys.stdout, sys.stderr
        try:
            sys.stdout = io.TextIOWrapper(
                io.BytesIO(), encoding="utf-8", errors="replace"
            )
            sys.stderr = io.TextIOWrapper(
                io.BytesIO(), encoding="utf-8", errors="replace"
            )
            result_data = asyncio.run(
                asyncio.wait_for(_scrape_pages(resolved_url), timeout=_SCRAPE_TIMEOUT)
            )
        finally:
            sys.stdout = _orig_stdout
            sys.stderr = _orig_stderr
        result_data["url_source"] = url_source

        if not result_data.get("homepage_text"):
            return {
                "found": False,
                "source": source,
                "summary": f"Could not fetch homepage at {resolved_url}.",
                "data": result_data,
            }

        from urllib.parse import urlparse
        domain = urlparse(resolved_url).netloc

        return {
            "found": True,
            "source": source,
            "summary": (
                f"Scraped {result_data['pages_scraped']} page(s) from {domain} "
                f"({result_data['total_chars']:,} chars total)."
            ),
            "data": result_data,
        }

    except asyncio.TimeoutError:
        return {
            "found": False,
            "source": source,
            "summary": f"Website scrape timed out after {_SCRAPE_TIMEOUT}s.",
            "data": {},
            "error": "Timeout",
        }
    except Exception as exc:
        return _error_result(source, exc)


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
    # search_web removed — replaced by Gemini Google Search grounding in agent.py
    {
        "name": "scrape_employer_website",
        "description": "Scrape the employer's website for company info, leadership, careers/job postings, and news. If you don't have a URL, the tool will look it up in the Mergent database. Tip: if search_mergent returned a 'website' field, pass that URL here.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "employer_id": {"type": "string", "description": "F7 employer_id for Mergent URL lookup"},
                "url": {"type": "string", "description": "Company website URL if known (e.g. from search_mergent)"},
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
