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

import json
import logging
import re
import sys
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

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
# External API Rate Limiters
# ---------------------------------------------------------------------------

import threading
import time as _time_mod

class _RateLimiter:
    """Simple thread-safe token bucket rate limiter."""
    def __init__(self, max_per_minute: int, name: str):
        self._lock = threading.Lock()
        self._name = name
        self._interval = 60.0 / max_per_minute
        self._last_call = 0.0
        self._total_calls = 0

    def wait(self):
        with self._lock:
            now = _time_mod.time()
            wait_time = self._interval - (now - self._last_call)
            if wait_time > 0:
                _log.debug("Rate limiter [%s]: waiting %.1fs", self._name, wait_time)
                _time_mod.sleep(wait_time)
            self._last_call = _time_mod.time()
            self._total_calls += 1

    @property
    def total_calls(self) -> int:
        return self._total_calls

_brave_limiter = _RateLimiter(max_per_minute=60, name="brave")
_ce_limiter = _RateLimiter(max_per_minute=200, name="company_enrich")

def get_api_call_stats() -> dict:
    """Return external API call counts for monitoring."""
    return {
        "brave_search_calls": _brave_limiter.total_calls,
        "company_enrich_calls": _ce_limiter.total_calls,
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


def _fix_json_escapes(text: str) -> str:
    """Fix common JSON escape issues from Gemini responses.

    Gemini sometimes returns JSON with unescaped newlines inside strings,
    or trailing commas. This cleans up the most common issues.
    """
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Replace unescaped newlines inside strings (naive but usually works)
    # This is a best-effort fix — structured output is the real solution
    return text


def _gemini_search_extract(prompt: str, extract_prompt: str,
                           expected_keys: list[str],
                           source: str) -> tuple[Optional[dict], str]:
    """Two-step Gemini search: (1) Google Search grounding, (2) structured extraction fallback.

    Args:
        prompt: The search prompt for Gemini with Google Search grounding
        extract_prompt: Simplified prompt for second-pass extraction (no grounding)
        expected_keys: Keys that must be present in valid output
        source: Source label for logging

    Returns:
        (parsed_data_or_None, raw_text)
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None, ""

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Step 1: Google Search grounding call
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )],
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=1024,
            temperature=0.0,
        ),
    )

    candidate = response.candidates[0] if response.candidates else None
    if not candidate or not candidate.content or not candidate.content.parts:
        return None, ""

    text = candidate.content.parts[0].text.strip()
    if not text or text.upper() == "NONE":
        return None, text or ""

    # Step 2: Try to parse JSON from the response
    data = None
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            data = json.loads(_fix_json_escapes(m.group(1).strip()))
        except Exception:
            pass
    if not data:
        try:
            data = json.loads(_fix_json_escapes(text))
        except Exception:
            pass

    # Validate: check expected keys are present
    if data and isinstance(data, dict):
        if all(k in data for k in expected_keys):
            return data, text

    # Step 3: Structured extraction fallback — second call without grounding
    # Ask Gemini to extract structured data from the raw text
    try:
        extract_full = (
            f"Extract structured data from the following text. {extract_prompt}\n\n"
            f"TEXT:\n{text[:3000]}\n\n"
            "Return ONLY valid JSON, no markdown, no explanation."
        )
        response2 = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=extract_full)],
            )],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=1024,
                temperature=0.0,
            ),
        )
        candidate2 = response2.candidates[0] if response2.candidates else None
        if candidate2 and candidate2.content and candidate2.content.parts:
            text2 = candidate2.content.parts[0].text.strip()
            try:
                data = json.loads(text2)
                if isinstance(data, dict):
                    return data, text
            except Exception:
                pass
    except Exception as exc:
        _log.debug("Structured extraction fallback failed for %s: %s", source, exc)

    # Return whatever we got (may be partial dict or None)
    return data if isinstance(data, dict) else None, text


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
# TOOL 2b: search_nlrb_docket
# ---------------------------------------------------------------------------


def search_nlrb_docket(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Search NLRB docket entries for procedural activity on an employer's cases."""
    source = "database:nlrb_docket"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Find case numbers linked to employer
        case_numbers: set[str] = set()

        if employer_id:
            cur.execute("""
                SELECT DISTINCT case_number FROM nlrb_participants
                WHERE matched_employer_id = %s AND participant_type = 'Employer'
            """, (employer_id,))
            case_numbers.update(r["case_number"] for r in cur.fetchall())

        if not case_numbers:
            name_clause, name_params = _name_like_clause("UPPER(participant_name)", company_name)
            cur.execute(f"""
                SELECT DISTINCT case_number FROM nlrb_participants
                WHERE {name_clause} AND participant_type = 'Employer'
                LIMIT 200
            """, name_params)
            filtered = _filter_by_name_similarity(cur.fetchall(), company_name, "case_number")
            case_numbers.update(r["case_number"] for r in filtered)

        if not case_numbers:
            conn.close()
            return {"found": False, "source": source,
                    "summary": "No NLRB cases found for this employer.", "data": {}}

        case_list = list(case_numbers)

        # Query docket entries
        cur.execute("""
            SELECT d.case_number,
                   MIN(d.docket_date) AS first_activity,
                   MAX(d.docket_date) AS last_activity,
                   COUNT(*) AS entry_count,
                   MAX(d.docket_date) >= CURRENT_DATE - INTERVAL '90 days' AS is_recent
            FROM nlrb_docket d
            WHERE d.case_number = ANY(%s)
            GROUP BY d.case_number
            ORDER BY MAX(d.docket_date) DESC NULLS LAST
        """, (case_list,))
        rows = _safe_list(cur.fetchall())

        conn.close()

        if not rows:
            return {"found": False, "source": source,
                    "summary": "No docket entries found for this employer's NLRB cases.", "data": {}}

        total_entries = sum(r.get("entry_count", 0) for r in rows)
        cases_with_recent = sum(1 for r in rows if r.get("is_recent"))

        data = {
            "cases_with_docket": len(rows),
            "total_entries": total_entries,
            "has_recent_activity": cases_with_recent > 0,
            "cases_with_recent_activity": cases_with_recent,
            "case_summaries": rows[:20],
        }

        parts = [f"{len(rows)} case(s) with docket data, {total_entries} total entries"]
        if cases_with_recent > 0:
            parts.append(f"{cases_with_recent} case(s) with activity in last 90 days")

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

        # Fetch XBRL financial data
        fin_rows = []
        if row.get("cik"):
            cur.execute("""
                SELECT fiscal_year_end, revenue, net_income, total_assets,
                       total_liabilities, cash, long_term_debt, employee_count
                FROM sec_xbrl_financials WHERE cik = %s
                ORDER BY fiscal_year_end DESC LIMIT 5
            """, (row["cik"],))
            fin_rows = _safe_list(cur.fetchall())

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

        if fin_rows:
            latest_fin = fin_rows[0]
            financials = {
                "latest_fiscal_year": latest_fin.get("fiscal_year_end"),
                "revenue": latest_fin.get("revenue"),
                "net_income": latest_fin.get("net_income"),
                "total_assets": latest_fin.get("total_assets"),
                "total_liabilities": latest_fin.get("total_liabilities"),
                "cash": latest_fin.get("cash"),
                "long_term_debt": latest_fin.get("long_term_debt"),
                "employee_count": latest_fin.get("employee_count"),
            }
            # Revenue growth YoY
            if len(fin_rows) >= 2:
                curr_rev = latest_fin.get("revenue")
                prev_rev = fin_rows[1].get("revenue")
                if curr_rev and prev_rev and prev_rev != 0:
                    financials["revenue_growth_pct"] = round(
                        float((curr_rev - prev_rev) / abs(prev_rev) * 100), 1
                    )
            financials["trend"] = [
                {"year": r.get("fiscal_year_end"), "revenue": r.get("revenue")}
                for r in fin_rows
            ]
            data["financials"] = financials

        summary = f"SEC: {data['company_name']}"
        if data.get("ticker"):
            summary += f" ({data['ticker']}:{data.get('exchange', '?')})"
        summary += f". SIC {data.get('sic_code', 'N/A')}: {data.get('sic_description', 'N/A')}."

        if data.get("financials"):
            rev = data["financials"].get("revenue")
            if rev:
                if rev >= 1e9:
                    summary += f" Revenue: ${rev/1e9:.1f}B."
                elif rev >= 1e6:
                    summary += f" Revenue: ${rev/1e6:.1f}M."
            ni = data["financials"].get("net_income")
            if ni is not None:
                if abs(ni) >= 1e9:
                    summary += f" Net income: ${ni/1e9:.1f}B."
                elif abs(ni) >= 1e6:
                    summary += f" Net income: ${ni/1e6:.1f}M."
            emp = data["financials"].get("employee_count")
            if emp:
                summary += f" Employees: {emp:,}."

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

        # NAICS hierarchy
        naics_hierarchy = []
        for length in [2, 3, 4, 5, 6]:
            prefix = naics[:length]
            if len(prefix) < length:
                break
            cur.execute("""
                SELECT naics_code, naics_title, code_level
                FROM naics_codes_reference
                WHERE naics_code = %s LIMIT 1
            """, (prefix,))
            row = cur.fetchone()
            if row:
                title = row["naics_title"]
                if title and title.endswith("T") and row["code_level"] < 6:
                    title = title[:-1]
                naics_hierarchy.append({
                    "code": row["naics_code"],
                    "title": title,
                    "level": row["code_level"],
                })

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

        # Pay ranges: join occupation matrix with projections for median wages
        pay_ranges = []
        if occupations:
            occ_codes = [o["occupation_code"] for o in occupations if o.get("occupation_code")]
            if occ_codes:
                cur.execute("""
                    SELECT soc_code, occupation_title, median_wage_2024,
                           typical_education
                    FROM bls_occupation_projections
                    WHERE soc_code = ANY(%s)
                      AND median_wage_2024 IS NOT NULL
                    ORDER BY median_wage_2024 DESC
                """, (occ_codes,))
                wage_rows = _safe_list(cur.fetchall())
                for wr in wage_rows:
                    pay_ranges.append({
                        "occupation": wr["occupation_title"],
                        "soc_code": wr["soc_code"],
                        "median_annual_wage": wr["median_wage_2024"],
                        "typical_education": wr.get("typical_education"),
                    })

        # CBP local context: establishment counts and employment for this NAICS + state
        cbp_local = None
        if state:
            for prefix_len in [len(naics), 4, 3, 2]:
                naics_prefix = naics[:prefix_len]
                cur.execute("""
                    SELECT naics, naics_label, establishment_count, employment,
                           annual_payroll, avg_weekly_wage
                    FROM cur_cbp_geo_naics
                    WHERE state_fips = (
                        SELECT state_fips AS fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1
                    )
                    AND naics = %s
                    AND (county_fips IS NULL OR county_fips IN ('', '000'))
                    LIMIT 1
                """, (state.upper(), naics_prefix))
                cbp_local = cur.fetchone()
                if cbp_local:
                    cbp_local = _safe_dict(cbp_local)
                    break

        # --- OES Area Wages (state-specific wage percentiles) ---
        oes_wages = []
        if state and occupations:
            occ_codes = [o["occupation_code"] for o in occupations if o.get("occupation_code")]
            if occ_codes:
                cur.execute("""
                    SELECT occ_code, occ_title, tot_emp, a_median, a_pct10, a_pct25,
                           a_pct75, a_pct90, h_median, loc_quotient
                    FROM mv_oes_area_wages
                    WHERE occ_code = ANY(%s) AND prim_state = %s
                    ORDER BY tot_emp DESC NULLS LAST
                """, (occ_codes, state.upper()))
                oes_wages = _safe_list(cur.fetchall())

        # --- SOII Injury Rates ---
        soii_rates = []
        for prefix_len in [len(naics), 4, 3, 2]:
            code = naics[:prefix_len].ljust(6, '0')
            cur.execute("""
                SELECT year, industry_name, case_type_text, rate
                FROM mv_soii_industry_rates
                WHERE industry_code = %s AND data_type_code = '3'
                ORDER BY year DESC, case_type_code
                LIMIT 15
            """, (code,))
            soii_rates = _safe_list(cur.fetchall())
            if soii_rates:
                break

        # --- JOLTS Turnover Rates ---
        jolts_rates = []
        for prefix_len in [len(naics), 4, 3, 2]:
            code = naics[:prefix_len].ljust(6, '0')
            cur.execute("""
                SELECT year, period, dataelement_text, rate
                FROM mv_jolts_industry_rates
                WHERE industry_code = %s
                ORDER BY year DESC, period DESC
                LIMIT 30
            """, (code,))
            jolts_rates = _safe_list(cur.fetchall())
            if jolts_rates:
                break

        # --- NCS Benefits Access ---
        ncs_benefits = []
        for prefix_len in [len(naics), 4, 3, 2]:
            code = naics[:prefix_len].ljust(6, '0')
            cur.execute("""
                SELECT year, provision_text, rate
                FROM mv_ncs_benefits_access
                WHERE industry_code = %s
                  AND ownership_code = '2'
                  AND datatype_code = '01'
                  AND subcell_code = '00'
                  AND provision_code IN ('014','015','016','018')
                ORDER BY year DESC, provision_code
                LIMIT 20
            """, (code,))
            ncs_benefits = _safe_list(cur.fetchall())
            if ncs_benefits:
                break
        # Fallback to all private industry
        if not ncs_benefits:
            cur.execute("""
                SELECT year, provision_text, rate
                FROM mv_ncs_benefits_access
                WHERE industry_code = '000000'
                  AND ownership_code = '2'
                  AND datatype_code = '01'
                  AND subcell_code = '00'
                  AND provision_code IN ('014','015','016','018')
                ORDER BY year DESC, provision_code
                LIMIT 20
            """)
            ncs_benefits = _safe_list(cur.fetchall())

        conn.close()

        data = {
            "naics_code": naics,
            "bls_industry_code": bls_code,
            "naics_hierarchy": naics_hierarchy,
            "top_occupations": occupations,
            "pay_ranges": pay_ranges,
            "national_density": national_density,
            "state_density": state_density,
            "cbp_local_context": cbp_local,
            "oes_area_wages": oes_wages,
            "soii_injury_rates": soii_rates,
            "jolts_turnover_rates": jolts_rates,
            "ncs_benefits_access": ncs_benefits,
        }

        if naics_hierarchy:
            hierarchy_str = " > ".join(f"{h['title']} ({h['code']})" for h in naics_hierarchy)
            summary = f"NAICS hierarchy: {hierarchy_str}. "
        else:
            summary = ""
        summary += f"Industry {bls_code} ({national_density['industry_name'] if national_density else 'N/A'}). "
        if occupations:
            top3 = ", ".join(f"{o['occupation_title']} ({o['percent_of_industry']}%)" for o in occupations[:3])
            summary += f"Top occupations: {top3}. "
        if pay_ranges:
            top_pay = ", ".join(f"{p['occupation']} (${p['median_annual_wage']:,.0f})" for p in pay_ranges[:3])
            summary += f"Pay ranges: {top_pay}. "
        if national_density:
            summary += f"National union density: {national_density['union_density_pct']}%."
        if state_density:
            summary += f" State ({state}) estimated density: {state_density['estimated_density']}%."
        if cbp_local:
            summary += f" CBP local ({state}): {cbp_local.get('establishment_count', 0):,} establishments, {cbp_local.get('employment', 0):,} employees, avg ${cbp_local.get('avg_weekly_wage', 0):,.0f}/week."
        if soii_rates:
            latest_injury = next((r for r in soii_rates if 'total' in (r.get('case_type_text') or '').lower()), soii_rates[0])
            summary += f" SOII injury rate ({latest_injury.get('year', '?')}): {latest_injury.get('rate', '?')}."
        if jolts_rates:
            quit_rate = next((r for r in jolts_rates if 'quit' in (r.get('dataelement_text') or '').lower()), None)
            if quit_rate:
                summary += f" JOLTS quit rate ({quit_rate.get('year', '?')} {quit_rate.get('period', '')}): {quit_rate.get('rate', '?')}%."
        if ncs_benefits:
            medical = next((r for r in ncs_benefits if 'medical' in (r.get('provision_text') or '').lower()), None)
            if medical:
                summary += f" NCS medical care access: {medical.get('rate', '?')}%."
        if oes_wages:
            summary += f" OES: {len(oes_wages)} occupations with state wage data."

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
# TOOL 11: search_web — REMOVED (2026-02-28)
# Stub had 0% hit rate across all calls. Web search handled by Gemini grounding.


# ---------------------------------------------------------------------------
# TOOL 12: scrape_employer_website  (Crawl4AI)
# ---------------------------------------------------------------------------

# Page budgets: (paths_to_try, char_limit)
_SCRAPE_PAGES = [
    ("homepage", ["/"], 3000),
    ("about", ["/about", "/about-us", "/company", "/our-story"], 2500),
    ("careers", ["/careers", "/jobs", "/work-with-us"], 1500),
    ("news", ["/news", "/press", "/newsroom", "/media"], 1000),
    ("locations", ["/locations", "/facilities", "/our-offices"], 1000),
    ("contact", ["/contact", "/contact-us", "/get-in-touch"], 1000),
    ("investors", ["/investors", "/investor-relations", "/financials"], 1500),
]
_SCRAPE_TOTAL_BUDGET = 12000
_SCRAPE_TIMEOUT = 35.0  # seconds — guarantees return within ~40s


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
    industry: Optional[str] = None,
    state: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Four-tier URL resolution. Returns (url, url_source)."""
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

    # Tier 3: Mergent by company name + state
    try:
        conn = _conn()
        cur = conn.cursor()
        name_clause, name_params = _name_like_clause("UPPER(company_name)", company_name)
        q = f"SELECT company_name, website FROM mergent_employers WHERE {name_clause} AND website IS NOT NULL AND website != ''"
        params = list(name_params)
        if state:
            q += " AND state = %s"
            params.append(state.upper())
        q += " ORDER BY employees_all_sites DESC NULLS LAST LIMIT 5"
        cur.execute(q, params)
        candidates = cur.fetchall()
        candidates = _filter_by_name_similarity(candidates, company_name, "company_name")
        conn.close()
        if candidates:
            norm = _normalize_url(candidates[0].get("website"))
            if norm:
                return norm, "name_search"
    except Exception as exc:
        _log.debug("Tier-3 URL lookup failed: %s", exc)

    # Tier 4: Google Search via Gemini grounding (lightweight, ~$0.001/call)
    if os.environ.get("RESEARCH_SCRAPER_GOOGLE_FALLBACK", "true").lower() != "false":
        try:
            resolved = _google_search_url(company_name, industry=industry, state=state)
            if resolved:
                norm = _normalize_url(resolved)
                if norm:
                    return norm, "google_search"
        except Exception as exc:
            _log.debug("Tier-4 Google Search URL lookup failed: %s", exc)

    return None, "none"


def _google_search_url(
    company_name: str,
    industry: Optional[str] = None,
    state: Optional[str] = None,
) -> Optional[str]:
    """Use Gemini + Google Search grounding to find a company's official URL.

    Returns the URL string or None if not found.
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        context = f"Company: \"{company_name}\""
        if state:
            context += f", Location: {state}"
        if industry:
            context += f", Industry: {industry}"

        prompt = (
            f"Find the official corporate website URL for: {context}. "
            "Return ONLY the absolute URL (e.g., https://www.example.com). "
            "If it's a subsidiary, find the subsidiary-specific site if it exists, "
            "otherwise the parent site. If you cannot find a definitive site, respond with NONE.\n"
            "Example: 'Xerox' -> https://www.xerox.com"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=256,
                temperature=0.0,
            ),
        )
        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content or not candidate.content.parts:
            return None
        text = candidate.content.parts[0].text.strip()
        if not text or text.upper() == "NONE":
            return None
        # Extract URL from response (may contain extra text)
        url_match = re.search(r'https?://[^\s<>"\']+', text)
        return url_match.group(0) if url_match else None
    except Exception as exc:
        _log.debug("Google Search URL resolution failed: %s", exc)
        return None


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
    # Cookie consent dismissal -- clicks common accept/agree buttons after page load
    _cookie_js = (
        '(function(){var s=["[id*=accept]","[class*=accept]","[id*=consent]",'
        '"[class*=consent]","[id*=agree]","[class*=agree]",'
        '"button[aria-label*=accept]","button[aria-label*=Allow]"];'
        'for(var i=0;i<s.length;i++){var e=document.querySelectorAll(s[i]);'
        'for(var j=0;j<e.length;j++){if(e[j].tagName==="BUTTON"||e[j].tagName==="A")'
        '{e[j].click();return;}}}})()'
    )
    run_cfg = CrawlerRunConfig(
        page_timeout=15000,
        wait_until="domcontentloaded",
        cache_mode=CacheMode.BYPASS,
        check_robots_txt=True,
        verbose=False,
        js_code=_cookie_js,
    )

    result_data = {
        "url": base_url,
        "homepage_text": None,
        "about_text": None,
        "careers_text": None,
        "news_text": None,
        "locations_text": None,
        "contact_text": None,
        "investors_text": None,
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
    industry: Optional[str] = None,
    state: Optional[str] = None,
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
        resolved_url, url_source = _resolve_employer_url(
            company_name, url, employer_id, industry=industry, state=state
        )
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
# Regex fallback helpers for Google Search grounding tools
# ---------------------------------------------------------------------------

def _extract_job_postings_from_text(text: str) -> Optional[dict]:
    """Regex-extract job posting count and sample titles from narrative text.

    Google Search grounding returns narrative like:
    - "approximately 5,000 open positions"
    - "Currently hiring for 120 roles including..."
    - "Warehouse Associate - $18/hr"
    """
    if not text:
        return None

    # Extract count estimate
    count = None
    count_patterns = [
        # "approximately 5,000 open positions"
        re.compile(
            r'(?:approximately|about|around|over|nearly|more than|currently|has|listing|found)\s+'
            r'([\d,]+)\s*(?:open|active|current|total|available)?\s*'
            r'(?:positions?|jobs?|listings?|openings?|roles?|vacancies|opportunities)',
            re.IGNORECASE,
        ),
        # "5,000+ jobs" or "5000 positions available"
        re.compile(
            r'([\d,]+)\+?\s*(?:open|active|current|total|available)?\s*'
            r'(?:positions?|jobs?|listings?|openings?|roles?|vacancies|opportunities)',
            re.IGNORECASE,
        ),
        # "hiring for 120 roles"
        re.compile(
            r'(?:hiring|recruiting)\s+(?:for\s+)?([\d,]+)\s*(?:roles?|positions?|people)',
            re.IGNORECASE,
        ),
    ]

    for pat in count_patterns:
        m = pat.search(text)
        if m:
            try:
                count = int(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass

    # Extract sample job titles
    # Look for patterns like "Warehouse Associate", "Registered Nurse", etc.
    sample_postings = []
    # Pattern: common job title structures near pay info or location
    title_pattern = re.compile(
        r'(?:^|\n|[;,])\s*([A-Z][a-z]+(?:\s+[A-Za-z]+){0,4})\s*'
        r'(?:[-:]|in\s+)\s*'
        r'([A-Z][a-z]+(?:,\s*[A-Z]{2})?)?'  # location
        r'(?:\s*[-:]\s*(\$[\d,.]+(?:/(?:hr|hour|year|yr|annual))?))?',  # pay
        re.MULTILINE,
    )
    for m in title_pattern.finditer(text):
        title = m.group(1).strip()
        location = (m.group(2) or "").strip()
        pay = (m.group(3) or "").strip()
        # Filter out non-job-title matches
        if len(title) > 5 and not title.startswith(("The ", "This ", "That ", "These ", "There ")):
            sample_postings.append({
                "title": title,
                "location": location or None,
                "pay": pay or None,
            })
            if len(sample_postings) >= 5:
                break

    if count is None and not sample_postings:
        return None

    return {
        "count_estimate": count or len(sample_postings),
        "sample_postings": sample_postings,
        "extraction_method": "regex_fallback",
    }


# TOOL 13: search_sec_proxy — REMOVED (2026-02-28)
# 0% hit rate (2 uses). SEC data already comes reliably from search_sec DB tool.


# ---------------------------------------------------------------------------
# TOOL 14: search_job_postings
# ---------------------------------------------------------------------------

def search_job_postings(
    company_name: str,
    *,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Estimate active job posting counts and titles using Google Search grounding."""
    source = "api:google_search_jobs"

    try:
        query = f"active job postings for \"{company_name}\""
        if state:
            query += f" in {state}"

        prompt = (
            f"Search for active job listings for: {query}. "
            "Estimate the total number of open positions found across major job boards (Indeed, LinkedIn, Glassdoor, etc.). "
            "List 3-5 sample job titles, their locations, and any mentioned pay/benefits. "
            "Return a JSON object with: {\"count_estimate\": 120, \"sample_postings\": [{\"title\": \"...\", \"location\": \"...\", \"pay\": \"...\"}]}. "
            "If no postings found, respond with NONE."
        )

        extract_prompt = (
            "Return a JSON object with keys: \"count_estimate\" (integer), "
            "\"sample_postings\" (array of objects with \"title\", \"location\", \"pay\")."
        )

        data, text = _gemini_search_extract(
            prompt, extract_prompt,
            expected_keys=["count_estimate"],
            source=source,
        )

        if not data:
            if not text:
                return {"found": False, "source": source, "summary": "No API key or no data.", "data": {}}
            # Last resort: regex fallback
            data = _extract_job_postings_from_text(text)
            if not data:
                return {"found": False, "source": source, "summary": "Unparseable job data.", "data": {"raw": text}}

        count = data.get("count_estimate", 0)
        samples = data.get("sample_postings", [])

        summary = f"Estimated {count} active job postings found. "
        if samples:
            summary += f"Sample roles: {', '.join(s.get('title', '?') for s in samples[:3])}."

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 15: get_workforce_demographics
# ---------------------------------------------------------------------------

def get_workforce_demographics(
    company_name: str,
    *,
    naics: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Get typical industry/state demographic baselines."""
    source = "database:demographic_baselines"
    try:
        if not naics:
            return {"found": False, "source": source, "summary": "NAICS required for demographics.", "data": {}}

        # For now, we use a curated list of industry baselines (Phase 6 placeholder)
        # Mapping 2-digit NAICS to broad demographic profiles
        _PROFILES = {
            "23": {"race_white": 85, "race_black": 6, "gender_male": 89, "avg_age": 42}, # Construction
            "62": {"race_white": 68, "race_black": 18, "gender_male": 23, "avg_age": 44}, # Healthcare
            "44": {"race_white": 70, "race_black": 12, "gender_male": 51, "avg_age": 38}, # Retail
            "72": {"race_white": 62, "race_black": 13, "gender_male": 46, "avg_age": 31}, # Hospitality
            "48": {"race_white": 65, "race_black": 18, "gender_male": 75, "avg_age": 45}, # Transport
            "31": {"race_white": 72, "race_black": 10, "gender_male": 70, "avg_age": 44}, # Manufacturing
        }

        naics_2 = naics[:2]
        baseline = _PROFILES.get(naics_2)
        is_generic_fallback = baseline is None

        if not baseline:
            # Generic private sector baseline
            baseline = {"race_white": 76, "race_black": 12, "gender_male": 53, "avg_age": 42}

        # Prefix the demographic_profile with an honest source label
        labeled_profile = f"INDUSTRY BASELINE (NAICS {naics_2}): " + ", ".join(
            f"{k}={v}" for k, v in baseline.items()
        )
        if is_generic_fallback:
            labeled_profile = f"GENERIC INDUSTRY BASELINE (no NAICS {naics_2} data): " + ", ".join(
                f"{k}={v}" for k, v in baseline.items()
            )

        data = {
            "naics_2": naics_2,
            "state": state,
            "demographic_profile": labeled_profile,
            "demographic_raw": baseline,
            "is_estimate": True,
            "is_generic_fallback": is_generic_fallback,
            "source_citation": "BLS Labor Force Statistics (Industry CPS 2024)"
        }

        summary = f"INDUSTRY BASELINE demographics (NAICS {naics_2}): {baseline['race_white']}% White, {baseline['race_black']}% Black, {baseline['gender_male']}% Male. Avg age: {baseline['avg_age']}. NOTE: These are industry averages, not company-specific."

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 16: search_gleif_ownership
# ---------------------------------------------------------------------------

def search_gleif_ownership(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Search GLEIF database for corporate ownership and parent-child relationships."""
    source = "database:gleif_us_entities"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Step 1: Find the entity in GLEIF
        entity = None
        if employer_id:
            # Via unified_match_log
            cur.execute("""
                SELECT g.* FROM gleif_us_entities g
                JOIN unified_match_log u ON u.source_id = g.lei
                WHERE u.source_system = 'gleif'
                  AND u.target_id = %s
                  AND u.status = 'active'
                LIMIT 1
            """, (employer_id,))
            entity = cur.fetchone()

        if not entity:
            name_clause, name_params = _name_like_clause("UPPER(entity_name)", company_name)
            cur.execute(f"SELECT * FROM gleif_us_entities WHERE {name_clause} LIMIT 5", name_params)
            candidates = cur.fetchall()
            candidates = _filter_by_name_similarity(candidates, company_name, "entity_name")
            entity = candidates[0] if candidates else None

        if not entity:
            conn.close()
            return {"found": False, "source": source, "summary": "No GLEIF entity found.", "data": {}}

        entity = _safe_dict(entity)
        entity_id = entity["id"]

        # Step 2: Find parents
        cur.execute("""
            SELECT p.entity_name AS parent_name, p.lei AS parent_lei, l.interest_level
            FROM gleif_ownership_links l
            JOIN gleif_us_entities p ON p.id = l.parent_entity_id
            WHERE l.child_entity_id = %s
        """, (entity_id,))
        parents = _safe_list(cur.fetchall())

        # Step 3: Find children
        cur.execute("""
            SELECT c.entity_name AS child_name, c.lei AS child_lei, l.interest_level
            FROM gleif_ownership_links l
            JOIN gleif_us_entities c ON c.id = l.child_entity_id
            WHERE l.parent_entity_id = %s
        """, (entity_id,))
        children = _safe_list(cur.fetchall())

        conn.close()

        data = {
            "entity": entity,
            "parents": parents,
            "children": children,
            "lei": entity.get("lei"),
        }

        summary = f"GLEIF: {entity['entity_name']} (LEI {entity.get('lei', 'N/A')}). "
        if parents:
            summary += f"Owned by {', '.join(p['parent_name'] for p in parents)}. "
        if children:
            summary += f"Directly owns {len(children)} subsidiaries. "

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 17: search_political_donations
# ---------------------------------------------------------------------------

def search_political_donations(
    company_name: str,
    *,
    ceo_name: Optional[str] = None,
    **_kw,
) -> dict:
    """Search for political donations from the company and its top executives using FEC API and Google grounding."""
    source = "api:fec_and_google"
    fec_api_key = os.environ.get("FEC_API_KEY", "")

    try:
        import requests

        fec_data = {}
        fec_summary = ""

        # Step 1: Query FEC API for employer-based contributions
        try:
            fec_url = "https://api.open.fec.gov/v1/schedules/schedule_a/by_employer/"
            params = {
                "api_key": fec_api_key,
                "employer": company_name,
                "sort": "-total",
                "per_page": 20
            }
            resp = requests.get(fec_url, params=params, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    total_fec = sum(r.get("total", 0) for r in results)
                    fec_data["employer_contributions"] = results
                    fec_data["fec_total"] = total_fec
                    fec_summary = f"FEC API found ${total_fec:,.2f} in contributions from employees of '{company_name}'. "
        except Exception as fec_exc:
            _log.warning("FEC API call failed: %s", fec_exc)

        # Step 2: Use Gemini with Google Search grounding for broader context
        target = f"\"{company_name}\""
        if ceo_name:
            target += f" and CEO \"{ceo_name}\""

        fec_context = f"\nFEC direct data found: {fec_summary}" if fec_summary else ""

        prompt = (
            f"Find comprehensive political donation data for {target}. {fec_context}\n"
            "Search for contributions to federal and state candidates, PACs, and parties from the company itself and its top executives. "
            "Cross-reference with OpenSecrets.org, FEC.gov, and news reports. "
            "Summarize the total amount donated, the partisan lean (Democrats vs Republicans), and any notable donors. "
            "Return a JSON object with: {\"total_amount\": \"$X,XXX\", \"partisan_lean\": \"Dem/Rep/Neutral\", \"top_donors\": [{\"name\": \"...\", \"amount\": \"...\", \"recipient\": \"...\"}], \"summary\": \"...\"}. "
            "If no data found, respond with NONE."
        )

        extract_prompt = (
            "Return a JSON object with keys: \"total_amount\" (string like \"$X,XXX\"), "
            "\"partisan_lean\" (one of \"Dem\", \"Rep\", \"Neutral\"), "
            "\"top_donors\" (array of objects with \"name\", \"amount\", \"recipient\"), "
            "\"summary\" (string)."
        )

        data, text = _gemini_search_extract(
            prompt, extract_prompt,
            expected_keys=["partisan_lean", "summary"],
            source=source,
        )

        if not data:
            if not text:
                if fec_data:
                    return {"found": True, "source": "api:fec", "summary": fec_summary, "data": fec_data}
                return {"found": False, "source": source, "summary": "No API key or no data.", "data": {}}
            # Combine FEC summary with Gemini narrative
            combined_summary = (fec_summary + text)[:500]
            return {"found": True, "source": source, "summary": combined_summary, "data": {"fec": fec_data, "narrative": text}}

        # Merge FEC raw data into the Gemini structured response
        data["fec_api_raw"] = fec_data

        final_summary = f"Political Donations: {data.get('total_amount', 'Unknown total')}. Lean: {data.get('partisan_lean', 'Unknown')}. " + data.get('summary', '')
        if fec_summary and "FEC API" not in final_summary:
            final_summary = fec_summary + final_summary

        return {
            "found": True,
            "source": source,
            "summary": final_summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 18: search_local_demographics
# ---------------------------------------------------------------------------

def search_local_demographics(
    company_name: str,
    city: str,
    state: str,
    **_kw,
) -> dict:
    """Search for local city/state demographic data using Google grounding."""
    source = "api:local_demographics"
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"found": False, "source": source, "summary": "No API key.", "data": {}}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"Provide current demographic data for {city}, {state}. "
            "Include population size, racial/ethnic breakdown (White, Black, Hispanic, Asian, etc.), median household income, and poverty rate. "
            "Also mention the top 3 largest industries in this city. "
            "Return a JSON object with: {'city': '...', 'population': '...', 'race_ethnicity': {'White': 'X%', ...}, 'median_income': '...', 'top_industries': ['...', '...', '...']}. "
            "If no data found, respond with NONE."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=1024,
                temperature=0.0,
            ),
        )

        candidate = response.candidates[0] if response.candidates else None
        text = candidate.content.parts[0].text.strip()
        if not text or text.upper() == "NONE":
            return {"found": False, "source": source, "summary": "No demographic data found.", "data": {}}

        # Extract JSON
        data = None
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            try:
                data = json.loads(_fix_json_escapes(m.group(1).strip()))
            except: pass
        if not data:
            try:
                data = json.loads(_fix_json_escapes(text))
            except: pass

        if not data or not isinstance(data, dict):
            return {"found": True, "source": source, "summary": f"Demographics for {city}, {state}", "data": {"raw": text}}

        summary = f"Demographics for {city}, {state}: Population {data.get('population')}, Median Income {data.get('median_income')}. "
        race = data.get('race_ethnicity', {})
        if race:
            summary += "Race: " + ", ".join(f"{k}: {v}" for k, v in list(race.items())[:3])

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 19: search_warn_notices
# ---------------------------------------------------------------------------

def search_warn_notices(
    company_name: str,
    *,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search for mass layoff (WARN Act) notices filed by this employer."""
    source = "api:warn_notices"

    try:
        query = f"WARN Act layoff notices \"{company_name}\""
        if state:
            query += f" in {state}"

        prompt = (
            f"Search for recent mass layoff (WARN Act) notices filed by {company_name}. "
            "Look for notices in the last 24 months. Include date filed, number of workers affected, and the location/facility name. "
            "Return a JSON object with: {\"notices\": [{\"date\": \"YYYY-MM-DD\", \"workers_affected\": 150, \"location\": \"...\", \"notes\": \"...\"}]}. "
            "If no notices found, respond with NONE."
        )

        extract_prompt = (
            "Return a JSON object with key \"notices\" containing an array of objects, "
            "each with \"date\" (string), \"workers_affected\" (integer), \"location\" (string), \"notes\" (string)."
        )

        data, text = _gemini_search_extract(
            prompt, extract_prompt,
            expected_keys=["notices"],
            source=source,
        )

        if not data:
            if not text:
                return {"found": False, "source": source, "summary": "No API key or no data.", "data": {}}
            # Try parsing as raw list
            try:
                parsed = json.loads(_fix_json_escapes(text))
                if isinstance(parsed, list):
                    data = {"notices": parsed}
            except Exception:
                pass
            if not data:
                return {"found": True, "source": source, "summary": f"WARN notices found for {company_name}", "data": {"raw": text}}

        notices = data.get("notices", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        if not notices:
            return {"found": False, "source": source, "summary": "No WARN notices found.", "data": {}}

        summary = f"Found {len(notices)} recent WARN layoff notice(s). "
        if notices:
            summary += f"Most recent: {notices[0].get('workers_affected')} workers in {notices[0].get('location')} on {notices[0].get('date')}."

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": notices,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 20: search_worker_sentiment
# ---------------------------------------------------------------------------

def search_worker_sentiment(
    company_name: str,
    *,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search for worker reviews and sentiment on Reddit, Glassdoor, and Indeed."""
    source = "api:worker_sentiment"

    try:
        target = f"\"{company_name}\" worker reviews"
        if state:
            target += f" in {state}"

        prompt = (
            f"Analyze current worker sentiment for {target}. "
            "Search specifically on Reddit (r/antiwork, r/work), Glassdoor, and Indeed reviews. "
            "Extract specific complaints about: management, wages, safety, overtime, and work-life balance. "
            "Summarize the general 'vibe' (positive/negative/toxic) and list 3-5 specific recent employee grievances. "
            "Return a JSON object with: {\"sentiment_score\": 0-10, \"top_complaints\": [\"...\", \"...\"], \"summary\": \"...\", \"sources\": [\"Reddit\", \"Glassdoor\", ...]}. "
            "If no reviews found, respond with NONE."
        )

        extract_prompt = (
            "Return a JSON object with keys: \"sentiment_score\" (integer 0-10), "
            "\"top_complaints\" (array of strings), \"summary\" (string), "
            "\"sources\" (array of platform names)."
        )

        data, text = _gemini_search_extract(
            prompt, extract_prompt,
            expected_keys=["sentiment_score", "summary"],
            source=source,
        )

        if not data:
            if not text:
                return {"found": False, "source": source, "summary": "No API key or no data.", "data": {}}
            return {"found": True, "source": source, "summary": text[:200], "data": {"raw": text}}

        summary = f"Worker Sentiment ({data.get('sentiment_score', 'N/A')}/10): " + data.get('summary', '')
        if data.get('top_complaints'):
            summary += " Major complaints: " + "; ".join(str(c) for c in data['top_complaints'][:3])

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 21: search_sos_filings
# ---------------------------------------------------------------------------

def search_sos_filings(
    company_name: str,
    state: str,
    **_kw,
) -> dict:
    """Search for official State Secretary of State (SOS) corporate filings."""
    source = "api:sos_filings"
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"found": False, "source": source, "summary": "No API key.", "data": {}}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"Find official corporate filing information for \"{company_name}\" in {state}. "
            "Search for the Secretary of State (SOS) record. "
            "Extract: Registered Agent name and address, list of current Officers/Directors, and any parent entities or LLC managers listed. "
            "Also provide a direct deep-link to the official state filing page if possible. "
            "Return a JSON object with: {'registered_agent': '...', 'officers': ['...', '...'], 'filing_url': '...', 'entity_status': '...', 'summary': '...'}. "
            "If no filings found, respond with NONE."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=1024,
                temperature=0.0,
            ),
        )

        candidate = response.candidates[0] if response.candidates else None
        text = candidate.content.parts[0].text.strip()
        if not text or text.upper() == "NONE":
            return {"found": False, "source": source, "summary": f"No SOS filings found in {state}.", "data": {}}

        # Extract JSON
        data = None
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            try:
                data = json.loads(_fix_json_escapes(m.group(1).strip()))
            except: pass
        if not data:
            try:
                data = json.loads(_fix_json_escapes(text))
            except: pass

        if not data or not isinstance(data, dict):
            return {"found": True, "source": source, "summary": text[:200], "data": {"raw": text}}

        summary = f"SOS Filing ({state}): Status {data.get('entity_status', 'Unknown')}. Registered Agent: {data.get('registered_agent')}. "
        if data.get('officers'):
            summary += f"Officers: {', '.join(data['officers'][:3])}."

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 22: compare_industry_wages
# ---------------------------------------------------------------------------

def compare_industry_wages(
    company_name: str,
    industry: str,
    city: str,
    state: str,
    **_kw,
) -> dict:
    """Compare target company wages with local competitors in the same sector."""
    source = "api:wage_comparison"
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"found": False, "source": source, "summary": "No API key.", "data": {}}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"Compare wages for \"{company_name}\" against 3-4 direct local competitors in the \"{industry}\" sector in {city}, {state}. "
            "Search current job postings (Indeed, Glassdoor, ZipRecruiter) for typical starting wages. "
            "Example: 'Amazon pays $18/hr vs UPS pays $21/hr for similar roles'. "
            "Identify if this company is above or below the local market average. "
            "Return a JSON object with: {'market_position': 'Below/At/Above Average', 'target_wages': '$X/hr', 'competitors': [{'name': '...', 'wage': '$Y/hr'}], 'summary': '...'}. "
            "If no comparison data found, respond with NONE."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=1024,
                temperature=0.0,
            ),
        )

        candidate = response.candidates[0] if response.candidates else None
        text = candidate.content.parts[0].text.strip()
        if not text or text.upper() == "NONE":
            return {"found": False, "source": source, "summary": "No local wage comparisons found.", "data": {}}

        # Extract JSON
        data = None
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            try:
                data = json.loads(_fix_json_escapes(m.group(1).strip()))
            except: pass
        if not data:
            try:
                data = json.loads(_fix_json_escapes(text))
            except: pass

        if not data or not isinstance(data, dict):
            return {"found": True, "source": source, "summary": text[:200], "data": {"raw": text}}

        summary = f"Wage Comparison: {data.get('market_position', 'Unknown')} position. Target: {data.get('target_wages')}. "
        comps = data.get('competitors', [])
        if comps:
            summary += "Competitors: " + ", ".join(f"{c['name']} ({c['wage']})" for c in comps[:2])

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 23: search_solidarity_network
# ---------------------------------------------------------------------------

def search_solidarity_network(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Find unionized 'sister' companies within the same corporate family using GLEIF."""
    source = "database:gleif_and_f7"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Step 1: Get the LEI for this entity
        lei = None
        if employer_id:
            cur.execute("SELECT gleif_lei FROM mv_employer_data_sources WHERE employer_id = %s", (employer_id,))
            row = cur.fetchone()
            if row: lei = row["gleif_lei"]

        if not lei:
            # Search by name in GLEIF entities
            name_clause, name_params = _name_like_clause("UPPER(entity_name)", company_name)
            cur.execute(f"SELECT lei FROM gleif_us_entities WHERE {name_clause} LIMIT 1", name_params)
            row = cur.fetchone()
            if row: lei = row["lei"]

        if not lei:
            conn.close()
            return {"found": False, "source": source, "summary": "No corporate LEI found to trace family.", "data": {}}

        # Step 2: Find the parent LEI
        cur.execute("SELECT parent_entity_id FROM gleif_ownership_links l JOIN gleif_us_entities e ON e.id = l.child_entity_id WHERE e.lei = %s LIMIT 1", (lei,))
        parent_row = cur.fetchone()
        if not parent_row:
            conn.close()
            return {"found": False, "source": source, "summary": "No corporate parent found in GLEIF.", "data": {"lei": lei}}

        parent_id = parent_row["parent_entity_id"]

        # Get parent name for summary
        cur.execute("SELECT entity_name, lei FROM gleif_us_entities WHERE id = %s", (parent_id,))
        parent_info = cur.fetchone()
        parent_name = parent_info["entity_name"] if parent_info else "Unknown Parent"

        # Step 3: Find ALL children of that parent and check their union status
        cur.execute("""
            WITH family AS (
                SELECT child_entity_id FROM gleif_ownership_links WHERE parent_entity_id = %s
            )
            SELECT DISTINCT 
                eds.employer_id, 
                eds.employer_name, 
                eds.state, 
                eds.latest_union_name,
                eds.latest_unit_size
            FROM family f
            JOIN gleif_us_entities g ON g.id = f.child_entity_id
            JOIN mv_employer_data_sources eds ON eds.gleif_lei = g.lei
            WHERE eds.latest_union_name IS NOT NULL
            ORDER BY eds.latest_unit_size DESC NULLS LAST
            LIMIT 20
        """, (parent_id,))
        sister_unions = _safe_list(cur.fetchall())
        conn.close()

        if not sister_unions:
            return {"found": True, "source": source, "summary": f"Corporate parent '{parent_name}' found, but no unionized sister companies identified in our database.", "data": {"parent_name": parent_name}}

        total_workers = sum(s.get("latest_unit_size", 0) or 0 for s in sister_unions)
        summary = f"Solidarity Network: Target is part of the '{parent_name}' family. We identified {len(sister_unions)} unionized sister facilities covering approx {total_workers:,} workers. Notable unions: "
        unions = list(set(s["latest_union_name"] for s in sister_unions if s.get("latest_union_name")))
        summary += ", ".join(unions[:5]) + "."

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": {
                "parent_name": parent_name,
                "sister_facilities": sister_unions,
                "unions_involved": unions
            }
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 24: search_local_subsidies
# ---------------------------------------------------------------------------

def search_local_subsidies(
    company_name: str,
    city: str,
    state: str,
    **_kw,
) -> dict:
    """Search for local tax breaks, abatements, and public subsidies."""
    source = "api:subsidies"
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"found": False, "source": source, "summary": "No API key.", "data": {}}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = (
            f"Search for public subsidies, tax abatements, or economic development grants received by \"{company_name}\" in {city}, {state}. "
            "Check sources like Good Jobs First (Subsidy Tracker), local IDA (Industrial Development Agency) records, and news reports. "
            "Look for: property tax breaks, sales tax exemptions, mortgage recording tax waivers, or direct grants. "
            "Identify the dollar amount and the 'quid pro quo' (e.g., job creation promises). "
            "Return a JSON object with: {'total_subsidy_value': '$X,XXX', 'subsidy_types': ['...', '...'], 'recent_awards': [{'year': '...', 'amount': '...', 'type': '...'}], 'summary': '...'}. "
            "If no data found, respond with NONE."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=1024,
                temperature=0.0,
            ),
        )

        candidate = response.candidates[0] if response.candidates else None
        text = candidate.content.parts[0].text.strip()
        if not text or text.upper() == "NONE":
            return {"found": False, "source": source, "summary": "No local subsidy data found.", "data": {}}

        # Extract JSON
        data = None
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            try:
                data = json.loads(_fix_json_escapes(m.group(1).strip()))
            except: pass
        if not data:
            try:
                data = json.loads(_fix_json_escapes(text))
            except: pass

        if not data or not isinstance(data, dict):
            return {"found": True, "source": source, "summary": text[:200], "data": {"raw": text}}

        summary = f"Taxpayer Receipt: {data.get('total_subsidy_value', 'Unknown total')} in subsidies/abatements identified. " + data.get('summary', '')

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_form5500
# ---------------------------------------------------------------------------

def search_form5500(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search Form 5500 benefit plan filings for this employer."""
    source = "database:cur_form5500_sponsor_rollup"
    try:
        conn = _conn()
        cur = conn.cursor()

        rows = []

        # Tier 1: If employer_id, go through master bridge to get EIN
        if employer_id:
            cur.execute("""
                SELECT f.* FROM cur_form5500_sponsor_rollup f
                JOIN master_employer_source_ids f5sid
                    ON f5sid.source_system = 'form5500' AND f5sid.source_id = f.sponsor_ein
                JOIN master_employer_source_ids f7sid
                    ON f7sid.master_id = f5sid.master_id AND f7sid.source_system = 'f7'
                WHERE f7sid.source_id = %s
                LIMIT 10
            """, (employer_id,))
            rows = cur.fetchall()

        # Tier 2: Name + state fallback
        if not rows and company_name:
            name_upper = company_name.strip().upper()
            params = [f"%{name_upper}%"]
            where = "UPPER(f.sponsor_name) LIKE %s"
            if state:
                where += " AND f.sponsor_state = %s"
                params.append(state.upper())
            cur.execute(f"""
                SELECT * FROM cur_form5500_sponsor_rollup f
                WHERE {where}
                ORDER BY f.total_active_participants DESC NULLS LAST
                LIMIT 10
            """, params)
            rows = cur.fetchall()

        conn.close()

        if not rows:
            return {"found": False, "source": source,
                    "summary": f"No Form 5500 filings found for {company_name}.",
                    "data": {}}

        top = rows[0]
        data = {
            "sponsor_count": len(rows),
            "sponsor_ein": top.get("sponsor_ein"),
            "sponsor_name": top.get("sponsor_name"),
            "plan_count": _safe(top.get("plan_count")),
            "total_active_participants": _safe(top.get("total_active_participants")),
            "total_participants_beneficiaries": _safe(top.get("total_participants_beneficiaries")),
            "has_collective_bargaining": top.get("has_collective_bargaining"),
            "has_pension": top.get("has_pension"),
            "has_welfare": top.get("has_welfare"),
            "latest_plan_year": _safe(top.get("latest_plan_year")),
            "earliest_plan_year": _safe(top.get("earliest_plan_year")),
            "years_filed": _safe(top.get("years_filed")),
            "all_sponsors": _safe_list(rows[:5]),
        }

        summary = f"Form 5500: {top.get('sponsor_name', 'N/A')} has {top.get('plan_count', 0)} benefit plan(s)"
        if top.get("total_active_participants"):
            summary += f" covering {top['total_active_participants']:,} active participants"
        summary += f". Filed {top.get('years_filed', 0)} year(s) ({top.get('earliest_plan_year', '?')}-{top.get('latest_plan_year', '?')})."
        if top.get("has_collective_bargaining"):
            summary += " Has collective bargaining plan."
        if top.get("has_pension"):
            summary += " Offers pension."
        if top.get("has_welfare"):
            summary += " Offers welfare benefits."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_ppp_loans
# ---------------------------------------------------------------------------

def search_ppp_loans(
    company_name: str,
    *,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search PPP loan data for this employer (pandemic-era financial context)."""
    source = "database:cur_ppp_employer_rollup"
    try:
        conn = _conn()
        cur = conn.cursor()

        name_upper = company_name.strip().upper()
        params = [f"%{name_upper}%"]
        where = "UPPER(p.borrower_name) LIKE %s"
        if state:
            where += " AND p.borrower_state = %s"
            params.append(state.upper())

        cur.execute(f"""
            SELECT * FROM cur_ppp_employer_rollup p
            WHERE {where}
            ORDER BY p.total_current_amount DESC NULLS LAST
            LIMIT 10
        """, params)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return {"found": False, "source": source,
                    "summary": f"No PPP loans found for {company_name}.",
                    "data": {}}

        top = rows[0]
        data = {
            "borrower_count": len(rows),
            "borrower_name": top.get("borrower_name"),
            "borrower_state": top.get("borrower_state"),
            "loan_count": _safe(top.get("loan_count")),
            "total_initial_amount": _safe(top.get("total_initial_amount")),
            "total_current_amount": _safe(top.get("total_current_amount")),
            "total_forgiveness_amount": _safe(top.get("total_forgiveness_amount")),
            "total_jobs_reported": _safe(top.get("total_jobs_reported")),
            "any_forgiven": top.get("any_forgiven"),
            "earliest_date_approved": _safe(top.get("earliest_date_approved")),
            "latest_date_approved": _safe(top.get("latest_date_approved")),
            "business_type": top.get("business_type"),
            "naics_code": top.get("naics_code"),
            "all_borrowers": _safe_list(rows[:5]),
        }

        amt = float(top.get("total_current_amount") or 0)
        summary = f"PPP: {top.get('borrower_name', 'N/A')} received {top.get('loan_count', 0)} PPP loan(s) totaling ${amt:,.0f}."
        if top.get("total_jobs_reported"):
            summary += f" Claimed {top['total_jobs_reported']:,} jobs retained."
        if top.get("any_forgiven"):
            forgiven = float(top.get("total_forgiveness_amount") or 0)
            summary += f" ${forgiven:,.0f} forgiven."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_cbp_context
# ---------------------------------------------------------------------------

def search_cbp_context(
    company_name: str,
    *,
    naics: Optional[str] = None,
    state: Optional[str] = None,
    county_fips: Optional[str] = None,
    **_kw,
) -> dict:
    """Search CBP for local industry establishment counts and employment context."""
    source = "database:cur_cbp_geo_naics"
    try:
        if not naics:
            return {"found": False, "source": source,
                    "summary": "Cannot look up CBP context without a NAICS code.",
                    "data": {}}

        conn = _conn()
        cur = conn.cursor()

        # State-level data for this NAICS
        state_data = None
        if state:
            # Try exact NAICS, then prefixes
            for prefix_len in [len(naics), 4, 3, 2]:
                naics_prefix = naics[:prefix_len]
                cur.execute("""
                    SELECT naics, naics_label, establishment_count, employment,
                           annual_payroll, avg_weekly_wage
                    FROM cur_cbp_geo_naics
                    WHERE state_fips = (
                        SELECT state_fips AS fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1
                    )
                    AND naics = %s
                    AND (county_fips IS NULL OR county_fips IN ('', '000'))
                    LIMIT 1
                """, (state.upper(), naics_prefix))
                state_data = cur.fetchone()
                if state_data:
                    break

        # National totals for this NAICS
        national_data = None
        for prefix_len in [len(naics), 4, 3, 2]:
            naics_prefix = naics[:prefix_len]
            cur.execute("""
                SELECT naics, naics_label,
                       SUM(establishment_count) AS establishment_count,
                       SUM(employment) AS employment,
                       SUM(annual_payroll) AS annual_payroll,
                       CASE WHEN SUM(employment) > 0
                            THEN ROUND(SUM(annual_payroll)::numeric / SUM(employment) / 52, 2)
                            ELSE NULL END AS avg_weekly_wage
                FROM cur_cbp_geo_naics
                WHERE naics = %s
                  AND geo_type = '01'
                GROUP BY naics, naics_label
                LIMIT 1
            """, (naics_prefix,))
            national_data = cur.fetchone()
            if national_data:
                break

        conn.close()

        if not state_data and not national_data:
            return {"found": False, "source": source,
                    "summary": f"No CBP data found for NAICS {naics}.",
                    "data": {}}

        data = {
            "naics": naics,
            "state_data": _safe_dict(state_data) if state_data else None,
            "national_data": _safe_dict(national_data) if national_data else None,
        }

        summary = f"CBP industry context for NAICS {naics}: "
        if national_data:
            summary += f"National: {national_data.get('establishment_count', 0):,} establishments, {national_data.get('employment', 0):,} employees, avg ${national_data.get('avg_weekly_wage', 0):,.0f}/week. "
        if state_data:
            summary += f"State ({state}): {state_data.get('establishment_count', 0):,} establishments, {state_data.get('employment', 0):,} employees."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_lodes_workforce
# ---------------------------------------------------------------------------

def search_lodes_workforce(
    company_name: str,
    *,
    state: Optional[str] = None,
    county_fips: Optional[str] = None,
    **_kw,
) -> dict:
    """Search LODES for county-level workforce metrics (jobs, earnings, commuting)."""
    source = "database:cur_lodes_geo_metrics"
    try:
        if not county_fips and not state:
            return {"found": False, "source": source,
                    "summary": "Need a state or county_fips to look up LODES workforce data.",
                    "data": {}}

        conn = _conn()
        cur = conn.cursor()

        rows = []
        if county_fips:
            cur.execute("""
                SELECT * FROM cur_lodes_geo_metrics
                WHERE county_fips = %s
                LIMIT 1
            """, (county_fips,))
            rows = cur.fetchall()

        # If no county, aggregate state-level
        if not rows and state:
            cur.execute("""
                SELECT
                    state_fips,
                    SUM(total_jobs) AS total_jobs,
                    SUM(jobs_earn_1250_or_less) AS jobs_earn_1250_or_less,
                    SUM(jobs_earn_1251_to_3333) AS jobs_earn_1251_to_3333,
                    SUM(jobs_earn_3334_plus) AS jobs_earn_3334_plus,
                    SUM(jobs_manufacturing) AS jobs_manufacturing,
                    SUM(jobs_healthcare) AS jobs_healthcare,
                    SUM(jobs_retail) AS jobs_retail,
                    SUM(jobs_accommodation_food) AS jobs_accommodation_food,
                    SUM(jobs_construction) AS jobs_construction,
                    ROUND(SUM(jobs_earn_3334_plus)::numeric / NULLIF(SUM(total_jobs), 0), 4) AS pct_high_earning,
                    ROUND(SUM(jobs_manufacturing)::numeric / NULLIF(SUM(total_jobs), 0), 4) AS pct_manufacturing,
                    ROUND(SUM(jobs_healthcare)::numeric / NULLIF(SUM(total_jobs), 0), 4) AS pct_healthcare
                FROM cur_lodes_geo_metrics
                WHERE state_fips = (
                    SELECT state_fips AS fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1
                )
                GROUP BY state_fips
                LIMIT 1
            """, (state.upper(),))
            rows = cur.fetchall()

        conn.close()

        if not rows:
            return {"found": False, "source": source,
                    "summary": "No LODES workforce data found.",
                    "data": {}}

        row = rows[0]
        data = _safe_dict(row)

        total = row.get("total_jobs") or 0
        summary = f"LODES workforce: {total:,} total jobs. "
        if row.get("pct_high_earning") is not None:
            summary += f"{float(row['pct_high_earning'])*100:.1f}% high-earning (>$3,333/mo). "
        if row.get("pct_manufacturing") is not None:
            summary += f"{float(row['pct_manufacturing'])*100:.1f}% manufacturing. "
        if row.get("pct_healthcare") is not None:
            summary += f"{float(row['pct_healthcare'])*100:.1f}% healthcare."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_abs_demographics
# ---------------------------------------------------------------------------

def search_abs_demographics(
    company_name: str,
    *,
    naics: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search ABS for firm demographics by industry (owner race, sex, veteran status)."""
    source = "database:cur_abs_geo_naics"
    try:
        if not naics:
            return {"found": False, "source": source,
                    "summary": "Cannot look up ABS demographics without a NAICS code.",
                    "data": {}}

        conn = _conn()
        cur = conn.cursor()

        # Try exact NAICS then prefixes
        naics_2 = naics[:2]
        geo_filter = ""
        params = [naics_2]
        if state:
            geo_filter = "AND a.state_fips = (SELECT state_fips AS fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1)"
            params.append(state.upper())

        cur.execute(f"""
            SELECT abs_dataset, geo_level, naics, naics_label,
                   owner_sex, owner_race, owner_ethnicity, owner_veteran,
                   sex, race_group, eth_group, vet_group,
                   firm_count, geo_name
            FROM cur_abs_geo_naics a
            WHERE a.naics = %s
              AND a.geo_level IN ('state', 'us')
              {geo_filter}
            ORDER BY a.firm_count DESC NULLS LAST
            LIMIT 50
        """, params)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return {"found": False, "source": source,
                    "summary": f"No ABS demographic data found for NAICS {naics}.",
                    "data": {}}

        total_firms = sum(r.get("firm_count") or 0 for r in rows)
        datasets = set(r.get("abs_dataset") for r in rows if r.get("abs_dataset"))

        data = {
            "naics": naics_2,
            "record_count": len(rows),
            "total_firm_count": total_firms,
            "datasets_available": sorted(datasets),
            "sample_records": _safe_list(rows[:20]),
        }

        summary = f"ABS demographics for NAICS {naics_2}: {total_firms:,} firms across {len(rows)} records. "
        summary += f"Datasets: {', '.join(sorted(datasets))}."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_acs_workforce
# ---------------------------------------------------------------------------

def search_acs_workforce(
    company_name: str,
    *,
    state: Optional[str] = None,
    naics: Optional[str] = None,
    soc_code: Optional[str] = None,
    metro_cbsa: Optional[str] = None,
    **_kw,
) -> dict:
    """Search ACS workforce demographics for a given geography/industry."""
    source = "database:cur_acs_workforce_demographics"
    try:
        if not state:
            return {"found": False, "source": source,
                    "summary": "Cannot look up ACS workforce data without a state.",
                    "data": {}}

        conn = _conn()
        cur = conn.cursor()

        # Resolve state abbreviation to FIPS code
        cur.execute(
            "SELECT state_fips AS fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1",
            (state.upper(),),
        )
        fips_row = cur.fetchone()
        if not fips_row:
            conn.close()
            return {"found": False, "source": source,
                    "summary": f"Unknown state: {state}",
                    "data": {}}
        state_fips = fips_row["fips"]

        where = ["state_fips = %s"]
        params: list = [state_fips]
        if naics:
            naics4 = naics[:4]
            where.append("naics4 = %s")
            params.append(naics4)
        if soc_code:
            where.append("soc_code = %s")
            params.append(soc_code)
        if metro_cbsa:
            where.append("metro_cbsa = %s")
            params.append(metro_cbsa)

        where_sql = " AND ".join(where)

        # Total weighted workers
        cur.execute(f"""
            SELECT COALESCE(SUM(weighted_workers), 0) AS total_workers
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
        """, params)
        total_row = cur.fetchone()
        total_workers = float(total_row["total_workers"]) if total_row else 0

        if total_workers == 0:
            conn.close()
            return {"found": False, "source": source,
                    "summary": f"No ACS workforce data for state={state}" +
                               (f", NAICS={naics}" if naics else "") + ".",
                    "data": {}}

        # Gender split
        cur.execute(f"""
            SELECT sex, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
            GROUP BY sex ORDER BY w DESC
        """, params)
        gender_rows = cur.fetchall()
        gender = {r["sex"]: round(float(r["w"]) / total_workers * 100, 1) for r in gender_rows}

        # Race breakdown
        cur.execute(f"""
            SELECT race, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
            GROUP BY race ORDER BY w DESC
        """, params)
        race_rows = cur.fetchall()
        race = {r["race"]: round(float(r["w"]) / total_workers * 100, 1) for r in race_rows}

        # Hispanic origin
        cur.execute(f"""
            SELECT hispanic, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
            GROUP BY hispanic ORDER BY w DESC
        """, params)
        hispan_rows = cur.fetchall()
        hispanic = {r["hispanic"]: round(float(r["w"]) / total_workers * 100, 1) for r in hispan_rows}

        # Age distribution
        cur.execute(f"""
            SELECT age_bucket, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
            GROUP BY age_bucket ORDER BY age_bucket
        """, params)
        age_rows = cur.fetchall()
        age_dist = {r["age_bucket"]: round(float(r["w"]) / total_workers * 100, 1) for r in age_rows}

        # Education profile
        cur.execute(f"""
            SELECT education, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
            GROUP BY education ORDER BY w DESC
        """, params)
        educ_rows = cur.fetchall()
        education = {r["education"]: round(float(r["w"]) / total_workers * 100, 1) for r in educ_rows}

        # Worker class split
        cur.execute(f"""
            SELECT worker_class, SUM(weighted_workers) AS w
            FROM cur_acs_workforce_demographics
            WHERE {where_sql}
            GROUP BY worker_class ORDER BY w DESC
        """, params)
        class_rows = cur.fetchall()
        worker_class = {r["worker_class"]: round(float(r["w"]) / total_workers * 100, 1) for r in class_rows}

        conn.close()

        data = {
            "state": state.upper(),
            "naics4": naics[:4] if naics else None,
            "soc_code": soc_code,
            "metro_cbsa": metro_cbsa,
            "total_weighted_workers": round(total_workers),
            "gender_pct": gender,
            "race_pct": race,
            "hispanic_pct": hispanic,
            "age_distribution_pct": age_dist,
            "education_pct": education,
            "worker_class_pct": worker_class,
        }

        summary = f"ACS workforce profile for {state.upper()}"
        if naics:
            summary += f" NAICS {naics[:4]}"
        summary += f": {round(total_workers):,} workers."
        if gender:
            top_gender = max(gender, key=gender.get)
            summary += f" {gender[top_gender]:.0f}% sex code {top_gender}."
        if age_dist:
            top_age = max(age_dist, key=age_dist.get)
            summary += f" Largest age group: {top_age} ({age_dist[top_age]:.0f}%)."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL 31: compare_employer_wages (QCEW-based)
# ---------------------------------------------------------------------------

def compare_employer_wages(
    company_name: str,
    *,
    state: Optional[str] = None,
    naics: Optional[str] = None,
    known_wage: Optional[float] = None,
    **_kw,
) -> dict:
    """Compare employer wages against QCEW local industry averages.

    Uses BLS Quarterly Census of Employment and Wages (QCEW) data to find
    the average annual pay for the employer's industry in their state,
    then computes a ratio and low-wage flag.
    """
    source = "database:qcew_wage_comparison"
    try:
        if not state or not naics:
            return {"found": False, "source": source, "summary": "State and NAICS required.", "data": {}}

        conn = _conn()
        cur = conn.cursor()

        # Get state FIPS code
        cur.execute(
            "SELECT state_fips AS fips FROM state_fips_map WHERE state_abbr = %s LIMIT 1",
            (state.upper(),),
        )
        fips_row = cur.fetchone()
        if not fips_row:
            conn.close()
            return {"found": False, "source": source, "summary": f"Unknown state: {state}", "data": {}}
        state_fips = fips_row["fips"]

        # area_fips for statewide = state_fips + '000'
        area_fips = f"{state_fips}000"
        naics_2 = naics[:2] if naics else None

        # Get latest year
        cur.execute("SELECT MAX(year) AS y FROM qcew_annual WHERE own_code = '5'")
        latest_year = cur.fetchone()["y"]

        # Try NAICS 2-digit at state level (own_code=5 = private sector)
        cur.execute("""
            SELECT avg_annual_pay, annual_avg_emplvl, industry_code, year
            FROM qcew_annual
            WHERE own_code = '5'
              AND area_fips = %s
              AND industry_code = %s
              AND year = %s
            LIMIT 1
        """, (area_fips, naics_2, latest_year))
        row = cur.fetchone()

        if not row:
            # Fallback: try national level (area_fips = 'US000' or 'US')
            cur.execute("""
                SELECT avg_annual_pay, annual_avg_emplvl, industry_code, year
                FROM qcew_annual
                WHERE own_code = '5'
                  AND area_fips IN ('US000', 'US')
                  AND industry_code = %s
                  AND year = %s
                LIMIT 1
            """, (naics_2, latest_year))
            row = cur.fetchone()

        conn.close()

        if not row:
            return {"found": False, "source": source, "summary": f"No QCEW data for NAICS {naics_2} in {state}.", "data": {}}

        local_avg_pay = float(row["avg_annual_pay"])
        local_employment = int(row["annual_avg_emplvl"])

        result = {
            "local_avg_annual_pay": local_avg_pay,
            "local_employment": local_employment,
            "industry_code": row["industry_code"],
            "data_year": row["year"],
            "state": state.upper(),
        }

        if known_wage and known_wage > 0:
            ratio = known_wage / local_avg_pay if local_avg_pay > 0 else None
            result["employer_wage"] = known_wage
            result["wage_ratio"] = round(ratio, 3) if ratio else None
            result["is_low_wage"] = ratio < 0.80 if ratio else False
            result["wage_percentile_est"] = (
                "well below average" if ratio and ratio < 0.70
                else "below average" if ratio and ratio < 0.85
                else "near average" if ratio and ratio < 1.15
                else "above average" if ratio and ratio < 1.40
                else "well above average" if ratio else "unknown"
            )
            summary = (
                f"QCEW {state.upper()} NAICS {naics_2}: avg annual pay ${local_avg_pay:,.0f} "
                f"({local_employment:,} workers). Employer wage ${known_wage:,.0f} = "
                f"{ratio:.0%} of local avg ({result['wage_percentile_est']})."
            )
        else:
            summary = (
                f"QCEW {state.upper()} NAICS {naics_2}: avg annual pay ${local_avg_pay:,.0f} "
                f"({local_employment:,} workers, {row['year']} data)."
            )

        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": result,
        }
    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_nyc_enforcement
# ---------------------------------------------------------------------------

def search_nyc_enforcement(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search NYC/NYS enforcement tables for wage theft, debarment, and local labor law violations."""
    source = "database:nyc_enforcement"
    try:
        conn = _conn()
        cur = conn.cursor()

        name_clause, name_params = _name_like_clause("employer_name_normalized", company_name)

        # Debarment list (210 rows)
        cur.execute(f"""
            SELECT 'debarment' AS source_type, employer_name, prosecuting_agency,
                   debarment_start_date, debarment_end_date,
                   NULL::numeric AS amount, NULL::integer AS num_claimants
            FROM nyc_debarment_list
            WHERE {name_clause}
        """, name_params)
        debarment_rows = cur.fetchall()

        # Local labor laws (568 rows)
        cur.execute(f"""
            SELECT 'local_labor_law' AS source_type, employer_name, NULL AS prosecuting_agency,
                   closed_date AS debarment_start_date, NULL::date AS debarment_end_date,
                   total_recovered AS amount, covered_workers AS num_claimants
            FROM nyc_local_labor_laws
            WHERE {name_clause}
        """, name_params)
        local_rows = cur.fetchall()

        # NYS wage theft (3,281 rows)
        cur.execute(f"""
            SELECT 'wage_theft_nys' AS source_type, employer_name, NULL AS prosecuting_agency,
                   NULL::date AS debarment_start_date, NULL::date AS debarment_end_date,
                   wages_owed AS amount, num_claimants
            FROM nyc_wage_theft_nys
            WHERE {name_clause}
        """, name_params)
        wage_rows = cur.fetchall()

        conn.close()

        all_rows = debarment_rows + local_rows + wage_rows

        # Filter by name similarity
        all_rows = _filter_by_name_similarity(all_rows, company_name, "employer_name")
        rows = _safe_list(all_rows)

        if not rows:
            return {"found": False, "source": source,
                    "summary": "No NYC/NYS enforcement records found for this employer.",
                    "data": {}}

        # Aggregate stats
        debarments = [r for r in rows if r["source_type"] == "debarment"]
        local_laws = [r for r in rows if r["source_type"] == "local_labor_law"]
        wage_theft = [r for r in rows if r["source_type"] == "wage_theft_nys"]

        from datetime import date as _date
        is_debarred = any(
            (not r.get("debarment_end_date") or r["debarment_end_date"] >= _date.today())
            for r in debarments
        )
        total_wages_owed = sum(float(r.get("amount") or 0) for r in wage_theft)
        total_recovered = sum(float(r.get("amount") or 0) for r in local_laws)

        data = {
            "record_count": len(rows),
            "debarment_count": len(debarments),
            "local_law_count": len(local_laws),
            "wage_theft_count": len(wage_theft),
            "is_debarred": is_debarred,
            "total_wages_owed": total_wages_owed,
            "total_recovered": total_recovered,
            "records": rows[:20],
        }

        summary = f"{len(rows)} NYC/NYS enforcement record(s). "
        if is_debarred:
            summary += "CURRENTLY DEBARRED. "
        if debarments:
            summary += f"{len(debarments)} debarment(s). "
        if local_laws:
            summary += f"{len(local_laws)} local labor law violation(s), ${total_recovered:,.0f} recovered. "
        if wage_theft:
            summary += f"{len(wage_theft)} NYS wage theft case(s), ${total_wages_owed:,.0f} owed."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_local_union_density
# ---------------------------------------------------------------------------

def search_local_union_density(
    company_name: str,
    *,
    state: str,
    naics: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
    **_kw,
) -> dict:
    """Get local union density context: F7 union counts, top unions, recent NLRB elections, and BLS state density."""
    source = "database:union_density"
    try:
        if not state or len(state) != 2:
            return {"found": False, "source": source,
                    "summary": "State (2-letter code) is required.",
                    "data": {}}

        state = state.upper()
        conn = _conn()
        cur = conn.cursor()

        naics_2 = naics[:2] if naics and len(naics) >= 2 else None

        # 1. F7 union counts in state (optionally filtered by 2-digit NAICS)
        naics_clause = ""
        params: list = [state]
        if naics_2:
            naics_clause = "AND LEFT(e.naics, 2) = %s"
            params.append(naics_2)

        cur.execute(f"""
            SELECT COUNT(DISTINCT e.employer_id) AS employer_count,
                   COUNT(DISTINCT r.union_file_number) AS union_count,
                   COALESCE(SUM(r.bargaining_unit_size), 0) AS total_bu_workers
            FROM f7_employers_deduped e
            JOIN f7_union_employer_relations r ON r.employer_id = e.employer_id
            WHERE e.state = %s {naics_clause}
        """, params)
        f7_stats = cur.fetchone()
        f7_summary = {
            "unionized_employers": f7_stats["employer_count"],
            "distinct_unions": f7_stats["union_count"],
            "total_bu_workers": int(f7_stats["total_bu_workers"]),
        }

        # 2. Top 10 unions in state/industry
        params2: list = [state]
        naics_clause2 = ""
        if naics_2:
            naics_clause2 = "AND LEFT(e.naics, 2) = %s"
            params2.append(naics_2)

        cur.execute(f"""
            SELECT u.f_num, u.union_name,
                   COUNT(DISTINCT r.employer_id) AS employer_count,
                   COALESCE(SUM(r.bargaining_unit_size), 0) AS total_workers
            FROM f7_union_employer_relations r
            JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
            JOIN unions_master u ON u.f_num = r.union_file_number::text
            WHERE e.state = %s {naics_clause2}
            GROUP BY u.f_num, u.union_name
            ORDER BY employer_count DESC
            LIMIT 10
        """, params2)
        top_unions = _safe_list(cur.fetchall())

        # 3. Recent NLRB elections (3 years) in state
        cur.execute("""
            SELECT ne.case_number, ne.election_date, ne.union_won,
                   ne.eligible_voters, p.participant_name
            FROM nlrb_elections ne
            JOIN nlrb_participants p ON p.case_number = ne.case_number
            WHERE p.participant_type = 'Employer'
              AND p.state = %s
              AND ne.election_date >= CURRENT_DATE - INTERVAL '3 years'
            ORDER BY ne.election_date DESC
            LIMIT 20
        """, (state,))
        recent_elections = _safe_list(cur.fetchall())
        elections_won = sum(1 for e in recent_elections if e.get("union_won"))
        elections_total = len(recent_elections)

        # 4. BLS state density benchmark
        cur.execute("""
            SELECT union_density_pct, represented_density_pct, year,
                   total_employed_thousands, union_members_thousands
            FROM bls_state_density
            WHERE state = %s
            ORDER BY year DESC LIMIT 1
        """, (state,))
        bls_row = cur.fetchone()
        bls_density = _safe_dict(bls_row) if bls_row else None

        conn.close()

        data = {
            "state": state,
            "naics_filter": naics_2,
            "f7_stats": f7_summary,
            "top_unions": top_unions,
            "recent_elections": recent_elections,
            "elections_summary": {
                "total": elections_total,
                "union_won": elections_won,
                "win_rate": round(elections_won / elections_total * 100, 1) if elections_total else None,
            },
            "bls_state_density": bls_density,
        }

        industry_label = f" (NAICS {naics_2}xx)" if naics_2 else ""
        summary = f"Union density in {state}{industry_label}: "
        summary += f"{f7_summary['unionized_employers']} unionized employers, "
        summary += f"{f7_summary['distinct_unions']} distinct unions, "
        summary += f"{f7_summary['total_bu_workers']:,} BU workers. "
        if top_unions:
            top3 = ", ".join(u["union_name"] for u in top_unions[:3])
            summary += f"Top unions: {top3}. "
        if elections_total:
            summary += f"Recent elections (3yr): {elections_total} found, {elections_won} union wins"
            if data["elections_summary"]["win_rate"] is not None:
                summary += f" ({data['elections_summary']['win_rate']}%)"
            summary += ". "
        if bls_density:
            summary += f"BLS state density ({bls_density.get('year', '?')}): {bls_density.get('union_density_pct', '?')}%."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_corporate_structure
# ---------------------------------------------------------------------------

def search_corporate_structure(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Build corporate family tree from crosswalk, GLEIF, CorpWatch, and SEC data."""
    source = "database:corporate_structure"
    try:
        conn = _conn()
        cur = conn.cursor()

        parent_info = None
        subsidiaries = []
        siblings = []
        crosswalk_row = None

        # 1. Check crosswalk for SEC/GLEIF/CorpWatch links
        if employer_id:
            cur.execute("""
                SELECT * FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s
                LIMIT 1
            """, (employer_id,))
            crosswalk_row = cur.fetchone()

        if not crosswalk_row:
            name_clause, name_params = _name_like_clause("UPPER(canonical_name)", company_name)
            cur.execute(f"""
                SELECT * FROM corporate_identifier_crosswalk
                WHERE {name_clause}
                LIMIT 1
            """, name_params)
            crosswalk_row = cur.fetchone()

        crosswalk_data = _safe_dict(crosswalk_row) if crosswalk_row else {}

        # 2. GLEIF parent/child lookup
        gleif_parents = []
        gleif_children = []
        if crosswalk_data.get("gleif_lei"):
            cur.execute("""
                SELECT id FROM gleif_us_entities WHERE lei = %s LIMIT 1
            """, (crosswalk_data["gleif_lei"],))
            ge = cur.fetchone()
            if ge:
                eid = ge["id"]
                cur.execute("""
                    SELECT p.entity_name, p.lei, l.interest_level
                    FROM gleif_ownership_links l
                    JOIN gleif_us_entities p ON p.id = l.parent_entity_id
                    WHERE l.child_entity_id = %s
                """, (eid,))
                gleif_parents = _safe_list(cur.fetchall())
                cur.execute("""
                    SELECT c.entity_name, c.lei, l.interest_level
                    FROM gleif_ownership_links l
                    JOIN gleif_us_entities c ON c.id = l.child_entity_id
                    WHERE l.parent_entity_id = %s
                    ORDER BY c.entity_name
                    LIMIT 50
                """, (eid,))
                gleif_children = _safe_list(cur.fetchall())

        # 3. CorpWatch parent/subsidiary lookup
        cw_parents = []
        cw_children = []
        cw_id = crosswalk_data.get("corpwatch_id")
        if not cw_id:
            # Try name match in corpwatch_companies
            name_clause, name_params = _name_like_clause("UPPER(company_name)", company_name)
            cur.execute(f"""
                SELECT cw_id, company_name, top_parent_id, num_children
                FROM corpwatch_companies
                WHERE {name_clause} AND is_us = true
                LIMIT 5
            """, name_params)
            cw_matches = cur.fetchall()
            cw_matches = _filter_by_name_similarity(cw_matches, company_name, "company_name")
            if cw_matches:
                cw_id = cw_matches[0]["cw_id"]

        if cw_id:
            # Parent: find rows where this entity is the child (target)
            cur.execute("""
                SELECT p.cw_id, p.company_name, p.sic_code, p.industry_name
                FROM corpwatch_relationships r
                JOIN corpwatch_companies p ON p.cw_id = r.source_cw_id
                WHERE r.target_cw_id = %s
                ORDER BY r.year DESC
                LIMIT 5
            """, (cw_id,))
            cw_parents = _safe_list(cur.fetchall())

            # Children: find rows where this entity is the parent (source)
            cur.execute("""
                SELECT c.cw_id, c.company_name, c.sic_code, c.industry_name
                FROM corpwatch_relationships r
                JOIN corpwatch_companies c ON c.cw_id = r.target_cw_id
                WHERE r.source_cw_id = %s
                ORDER BY c.company_name
                LIMIT 50
            """, (cw_id,))
            cw_children = _safe_list(cur.fetchall())

            # Top parent chain
            cur.execute("""
                SELECT cw_id, company_name, top_parent_id
                FROM corpwatch_companies WHERE cw_id = %s
            """, (cw_id,))
            cw_self = cur.fetchone()
            if cw_self and cw_self["top_parent_id"] and cw_self["top_parent_id"] != cw_id:
                cur.execute("""
                    SELECT cw_id, company_name, num_children
                    FROM corpwatch_companies WHERE cw_id = %s
                """, (cw_self["top_parent_id"],))
                top = cur.fetchone()
                if top:
                    parent_info = {
                        "name": top["company_name"],
                        "source": "corpwatch",
                        "subsidiaries_count": top["num_children"],
                    }

        # 4. SEC data for public companies
        sec_info = None
        if crosswalk_data.get("sec_cik"):
            cur.execute("""
                SELECT company_name, ticker, exchange, sic_code, sic_description,
                       entity_type, state_of_incorporation, is_public
                FROM sec_companies WHERE cik = %s LIMIT 1
            """, (crosswalk_data["sec_cik"],))
            sec_row = cur.fetchone()
            if sec_row:
                sec_info = _safe_dict(sec_row)

        # 5. Solidarity network -- unionized siblings in same corporate family
        solidarity_siblings = []
        corp_family_id = crosswalk_data.get("corporate_family_id")
        if corp_family_id:
            cur.execute("""
                SELECT c.canonical_name, c.f7_employer_id, c.state
                FROM corporate_identifier_crosswalk c
                WHERE c.corporate_family_id = %s
                  AND c.f7_employer_id IS NOT NULL
                  AND c.f7_employer_id != %s
                LIMIT 20
            """, (corp_family_id, employer_id or ""))
            solidarity_siblings = _safe_list(cur.fetchall())

        conn.close()

        # Merge parents from all sources
        if not parent_info and gleif_parents:
            parent_info = {
                "name": gleif_parents[0]["entity_name"],
                "source": "gleif",
                "lei": gleif_parents[0].get("lei"),
            }
        if not parent_info and cw_parents:
            parent_info = {
                "name": cw_parents[0]["company_name"],
                "source": "corpwatch",
            }

        # Merge subsidiaries
        seen = set()
        for c in gleif_children:
            n = c["entity_name"]
            if n not in seen:
                subsidiaries.append({"name": n, "source": "gleif"})
                seen.add(n)
        for c in cw_children:
            n = c["company_name"]
            if n not in seen:
                subsidiaries.append({"name": n, "source": "corpwatch"})
                seen.add(n)

        is_public = crosswalk_data.get("is_public", False) or (sec_info or {}).get("is_public", False)
        parent_type = "public" if is_public else "private"
        if sec_info and sec_info.get("entity_type"):
            parent_type = sec_info["entity_type"]

        data = {
            "crosswalk": crosswalk_data if crosswalk_data else None,
            "parent": parent_info,
            "parent_type": parent_type,
            "subsidiaries": subsidiaries[:50],
            "subsidiaries_count": len(subsidiaries),
            "solidarity_siblings": solidarity_siblings,
            "sec_info": sec_info,
            "is_public": is_public,
            "ticker": crosswalk_data.get("ticker") or (sec_info or {}).get("ticker"),
            "ein": crosswalk_data.get("ein"),
        }

        summary = ""
        if parent_info:
            summary += f"Parent company: {parent_info['name']} (via {parent_info['source']}). "
        else:
            summary += "No parent company identified (appears independent). "
        if subsidiaries:
            top3 = ", ".join(s["name"] for s in subsidiaries[:3])
            summary += f"{len(subsidiaries)} subsidiaries found (e.g. {top3}). "
        if solidarity_siblings:
            summary += f"{len(solidarity_siblings)} unionized sibling(s) in corporate family. "
        if sec_info:
            summary += f"SEC: {sec_info.get('ticker', 'N/A')} on {sec_info.get('exchange', 'N/A')}. "
        if is_public:
            summary += "Publicly traded. "

        return {"found": bool(crosswalk_data or parent_info or subsidiaries), "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_employer_locations
# ---------------------------------------------------------------------------

def search_employer_locations(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Discover employer locations from OSHA establishments, SAM entities, and match data."""
    source = "database:employer_locations"
    try:
        conn = _conn()
        cur = conn.cursor()

        locations = []

        # 1. OSHA establishments -- richest location data
        name_clause, name_params = _name_like_clause("UPPER(estab_name)", company_name)
        state_filter = ""
        if state:
            state_filter = "AND site_state = %s"
            name_params.append(state.upper())

        cur.execute(f"""
            SELECT estab_name, site_address, site_city, site_state, site_zip,
                   naics_code, employee_count, total_inspections,
                   first_inspection_date, last_inspection_date
            FROM osha_establishments
            WHERE {name_clause} {state_filter}
            ORDER BY total_inspections DESC
            LIMIT 100
        """, name_params)
        osha_rows = cur.fetchall()
        osha_rows = _filter_by_name_similarity(osha_rows, company_name, "estab_name", threshold=0.55)

        for row in osha_rows:
            r = _safe_dict(row)
            key = f"{r.get('site_city','')}-{r.get('site_state','')}-{r.get('site_zip','')}"
            locations.append({
                "address": r.get("site_address"),
                "city": r.get("site_city"),
                "state": r.get("site_state"),
                "zip": r.get("site_zip"),
                "source": "osha",
                "employee_count": r.get("employee_count"),
                "inspections": r.get("total_inspections"),
                "naics": r.get("naics_code"),
                "_dedup_key": key,
            })

        # 2. SAM entities
        name_clause2, name_params2 = _name_like_clause("UPPER(legal_business_name)", company_name)
        cur.execute(f"""
            SELECT legal_business_name, physical_city, physical_state, physical_zip,
                   entity_structure
            FROM sam_entities
            WHERE {name_clause2}
            LIMIT 50
        """, name_params2)
        sam_rows = cur.fetchall()
        sam_rows = _filter_by_name_similarity(sam_rows, company_name, "legal_business_name", threshold=0.55)

        for row in sam_rows:
            r = _safe_dict(row)
            key = f"{r.get('physical_city','')}-{r.get('physical_state','')}-{r.get('physical_zip','')}"
            locations.append({
                "city": r.get("physical_city"),
                "state": r.get("physical_state"),
                "zip": r.get("physical_zip"),
                "source": "sam",
                "entity_structure": r.get("entity_structure"),
                "_dedup_key": key,
            })

        # 3. F7 employer records (via match data)
        if employer_id:
            cur.execute("""
                SELECT e.site_city, e.site_state, e.site_zip
                FROM osha_f7_matches m
                JOIN osha_establishments e ON e.establishment_id = m.osha_establishment_id
                WHERE m.f7_employer_id = %s AND m.status = 'active'
            """, (employer_id,))
            for row in cur.fetchall():
                r = _safe_dict(row)
                key = f"{r.get('site_city','')}-{r.get('site_state','')}-{r.get('site_zip','')}"
                locations.append({
                    "city": r.get("site_city"),
                    "state": r.get("site_state"),
                    "zip": r.get("site_zip"),
                    "source": "osha_match",
                    "_dedup_key": key,
                })

        conn.close()

        # Deduplicate by city-state-zip
        seen_keys = set()
        deduped = []
        for loc in locations:
            key = loc.pop("_dedup_key", "")
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            deduped.append(loc)

        # Group by state
        by_state = {}
        for loc in deduped:
            st = loc.get("state") or "Unknown"
            by_state.setdefault(st, []).append(loc)

        data = {
            "locations": deduped[:50],
            "total_locations": len(deduped),
            "states": sorted(by_state.keys()),
            "state_counts": {k: len(v) for k, v in sorted(by_state.items())},
        }

        if not deduped:
            return {"found": False, "source": source,
                    "summary": "No establishment locations found for this employer.",
                    "data": data}

        summary = f"{len(deduped)} location(s) across {len(by_state)} state(s). "
        top_states = sorted(by_state.items(), key=lambda x: len(x[1]), reverse=True)[:3]
        state_str = ", ".join(f"{st} ({len(locs)})" for st, locs in top_states)
        summary += f"Top states: {state_str}. "
        osha_count = sum(1 for l in deduped if l.get("source") == "osha")
        if osha_count:
            summary += f"{osha_count} from OSHA establishment records."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_leadership
# ---------------------------------------------------------------------------

def search_leadership(
    company_name: str,
    *,
    employer_id: Optional[str] = None,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Extract leadership/management info from SEC, CorpWatch, crosswalk, and web search."""
    source = "database:leadership"
    try:
        conn = _conn()
        cur = conn.cursor()

        officers = []
        sec_executives = []
        ceo_name = None

        # 1. Check crosswalk for SEC link
        crosswalk_row = None
        if employer_id:
            cur.execute("""
                SELECT sec_cik, canonical_name, ticker, is_public
                FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s LIMIT 1
            """, (employer_id,))
            crosswalk_row = cur.fetchone()

        if not crosswalk_row:
            name_clause, name_params = _name_like_clause("UPPER(canonical_name)", company_name)
            cur.execute(f"""
                SELECT sec_cik, canonical_name, ticker, is_public
                FROM corporate_identifier_crosswalk
                WHERE {name_clause} LIMIT 1
            """, name_params)
            crosswalk_row = cur.fetchone()

        xw = _safe_dict(crosswalk_row) if crosswalk_row else {}
        is_public = xw.get("is_public", False)

        # 2. SEC company info for public companies
        if xw.get("sec_cik"):
            cur.execute("""
                SELECT company_name, entity_type, sic_description,
                       state_of_incorporation, state, city
                FROM sec_companies WHERE cik = %s LIMIT 1
            """, (xw["sec_cik"],))
            sec_co = cur.fetchone()
            if sec_co:
                sec_co = _safe_dict(sec_co)

        # 3. Use Gemini with Google Search grounding for leadership extraction
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                state_hint = f" in {state}" if state else ""
                prompt = (
                    f'Find the current leadership team for "{company_name}"{state_hint}. '
                    "Search for CEO/President, CFO, COO, and other C-suite executives. "
                    "Also find local/site management if this is a specific facility. "
                    'Return a JSON object: {{"ceo": "Name, Title", "executives": ["Name, Title", ...], '
                    '"board_members": ["Name", ...], "source_urls": ["..."]}}. '
                    "If no leadership info found, respond with NONE."
                )

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)],
                    )],
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        max_output_tokens=1024,
                        temperature=0.0,
                    ),
                )

                candidate = response.candidates[0] if response.candidates else None
                text = candidate.content.parts[0].text.strip() if candidate else ""
                if text and text.upper() != "NONE":
                    data_parsed = None
                    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
                    if m:
                        try:
                            data_parsed = json.loads(_fix_json_escapes(m.group(1).strip()))
                        except Exception:
                            pass
                    if not data_parsed:
                        try:
                            data_parsed = json.loads(_fix_json_escapes(text))
                        except Exception:
                            pass

                    if data_parsed and isinstance(data_parsed, dict):
                        ceo_name = data_parsed.get("ceo")
                        sec_executives = data_parsed.get("executives", [])
                        officers = data_parsed.get("board_members", [])
            except Exception as web_exc:
                _log.warning("Leadership web search failed: %s", web_exc)

        conn.close()

        data = {
            "ceo": ceo_name,
            "executives": sec_executives,
            "board_members": officers,
            "is_public": is_public,
            "ticker": xw.get("ticker"),
        }

        has_data = bool(ceo_name or sec_executives or officers)
        if not has_data:
            return {"found": False, "source": source,
                    "summary": "No leadership information found.",
                    "data": data}

        summary = ""
        if ceo_name:
            summary += f"CEO/President: {ceo_name}. "
        if sec_executives:
            summary += f"{len(sec_executives)} executive(s): {', '.join(str(e) for e in sec_executives[:3])}. "
        if officers:
            summary += f"{len(officers)} board member(s). "

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# TOOL: search_state_enforcement
# ---------------------------------------------------------------------------

def search_state_enforcement(
    company_name: str,
    *,
    state: Optional[str] = None,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Search state/local enforcement data beyond federal OSHA/WHD. Covers debarment, wage theft, and local labor laws."""
    source = "database:state_enforcement"
    try:
        conn = _conn()
        cur = conn.cursor()

        records = []

        # 1. NYC debarment list (210 rows -- small, full scan OK)
        name_clause, name_params = _name_like_clause("UPPER(employer_name_normalized)", company_name)
        cur.execute(f"""
            SELECT employer_name_normalized AS employer_name,
                   'debarment' AS record_type,
                   debarment_start_date, debarment_end_date,
                   prosecuting_agency AS agency
            FROM nyc_debarment_list
            WHERE {name_clause}
        """, name_params)
        debar_rows = _filter_by_name_similarity(cur.fetchall(), company_name, "employer_name")
        for r in _safe_list(debar_rows):
            r["source"] = "nyc_debarment"
            records.append(r)

        # 2. Use Gemini with Google Search for state-specific enforcement
        api_key = os.environ.get("GOOGLE_API_KEY")
        web_records = []
        if api_key and state:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                prompt = (
                    f'Search for state and local labor law violations, wage theft cases, '
                    f'and enforcement actions against "{company_name}" in {state}. '
                    f'Check state OSHA plans, state department of labor, state attorney general actions, '
                    f'and local enforcement. '
                    f'Return a JSON object: {{"violations": [{{"type": "...", "agency": "...", '
                    f'"date": "...", "penalty": "...", "description": "..."}}], '
                    f'"state_contracts": [{{"agency": "...", "amount": "...", "description": "..."}}]}}. '
                    f'If nothing found, respond with NONE.'
                )

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)],
                    )],
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                        max_output_tokens=1024,
                        temperature=0.0,
                    ),
                )

                candidate = response.candidates[0] if response.candidates else None
                text = candidate.content.parts[0].text.strip() if candidate else ""
                if text and text.upper() != "NONE":
                    data_parsed = None
                    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
                    if m:
                        try:
                            data_parsed = json.loads(_fix_json_escapes(m.group(1).strip()))
                        except Exception:
                            pass
                    if not data_parsed:
                        try:
                            data_parsed = json.loads(_fix_json_escapes(text))
                        except Exception:
                            pass

                    if data_parsed and isinstance(data_parsed, dict):
                        for v in data_parsed.get("violations", []):
                            if isinstance(v, dict):
                                v["source"] = f"web:{state}_enforcement"
                                v["record_type"] = v.get("type", "state_violation")
                                web_records.append(v)
                        for c in data_parsed.get("state_contracts", []):
                            if isinstance(c, dict):
                                c["source"] = f"web:{state}_contracts"
                                c["record_type"] = "state_contract"
                                web_records.append(c)
            except Exception as web_exc:
                _log.warning("State enforcement web search failed: %s", web_exc)

        records.extend(web_records)
        conn.close()

        data = {
            "records": records[:30],
            "record_count": len(records),
            "debarment_count": sum(1 for r in records if r.get("record_type") == "debarment"),
            "violation_count": sum(1 for r in records if "violation" in (r.get("record_type") or "")),
            "contract_count": sum(1 for r in records if r.get("record_type") == "state_contract"),
            "sources_checked": ["nyc_debarment"] + ([f"{state}_web_search"] if state else []),
        }

        if not records:
            return {"found": False, "source": source,
                    "summary": f"No state/local enforcement records found{' in ' + state if state else ''}.",
                    "data": data}

        from datetime import date as _date
        today_str = _date.today().isoformat()
        is_debarred = any(
            r.get("record_type") == "debarment"
            and (not r.get("debarment_end_date") or str(r["debarment_end_date"]) >= today_str)
            for r in records
        )

        summary = f"{len(records)} state/local record(s). "
        if is_debarred:
            summary += "CURRENTLY DEBARRED. "
        if data["debarment_count"]:
            summary += f"{data['debarment_count']} debarment(s). "
        if data["violation_count"]:
            summary += f"{data['violation_count']} state/local violation(s). "
        if data["contract_count"]:
            summary += f"{data['contract_count']} state/local contract(s) found. "

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


def search_company_enrich(
    company_name: str,
    *,
    domain: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    **_kw,
) -> dict:
    """Enrich company identity via CompanyEnrich.com API (30M+ companies)."""
    source = "api:company_enrich"
    try:
        import requests
        api_key = os.environ.get("COMPANY_ENRICH_API_KEY")
        if not api_key:
            return {"found": False, "source": source, "summary": "No COMPANY_ENRICH_API_KEY configured.", "data": {}, "error": "missing_key"}

        _ce_limiter.wait()
        base = "https://api.companyenrich.com"
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

        # Prefer domain-based lookup (higher accuracy)
        if domain:
            # Strip protocol if present
            d = domain.replace("https://", "").replace("http://", "").split("/")[0].lower()
            resp = requests.get(f"{base}/companies/enrich", params={"domain": d}, headers=headers, timeout=15)
        else:
            # Fall back to name-based lookup
            body = {"name": company_name}
            if linkedin_url:
                body["linkedinUrl"] = linkedin_url
            resp = requests.post(f"{base}/companies/enrich", json=body, headers=headers, timeout=15)

        if resp.status_code == 404:
            return {"found": False, "source": source, "summary": f"CompanyEnrich: No match for '{company_name}'.", "data": {}}
        if resp.status_code == 429:
            _log.warning("CompanyEnrich rate limited (429)")
            return {"found": False, "source": source, "summary": "CompanyEnrich: Rate limited. Try again later.", "data": {}, "error": "rate_limited"}
        resp.raise_for_status()
        co = resp.json()

        # R7-16 (2026-04-27): Identity grafting guard. CompanyEnrich's name-based
        # lookup occasionally returns a different entity than queried (e.g.
        # "Crouse Hospital" -> "Children's National Hospital"). When the lookup
        # was domain-based (line 4653) we trust the result; when name-based
        # (line 4659) we run a composite fuzzy check before accepting.
        #
        # The composite: reject only when ALL THREE strategies say it's a bad
        # match. Single strategies fail on legitimate edge cases:
        #   - token_sort_ratio penalizes substring matches ("Starbucks" vs
        #     "Starbucks Coffee Company" = 55% even though clearly the same).
        #   - partial_ratio is too permissive on shared prefixes ("Cleveland
        #     Clinic" vs "Cleveland-Cliffs" = 83%).
        #   - token_set_ratio rewards subset overlap ("the kroger" vs "kroger
        #     company" = 75% legitimate).
        # Combined: partial<80 AND token_sort<65 AND token_set<75 catches the
        # Crouse case (75/57/70) without false-rejecting Walmart/Starbucks/
        # Apple/Kroger/AT&T.
        returned_name = (co.get("name") or "").strip()
        if not domain and returned_name:
            qn_lower = company_name.lower()
            rn_lower = returned_name.lower()

            # Layer 1 (2026-04-30): Alias-based collision exclusion. If the
            # query matches a known-collision alias from config/employer_aliases.json,
            # reject any returned name that contains an exclude_term. The same
            # config powers the search-rank tiebreak in employers.py:_load_aliases.
            # Catches Cleveland Clinic -> Cleveland-Cliffs (partial=83 slips
            # past Layer 2) and NYC Hospitals -> NYU Langone (partial=88 slips
            # past Layer 2) -- the cases the composite fuzzy guard misses.
            try:
                import json as _json
                from pathlib import Path as _Path
                _alias_path = _Path(__file__).resolve().parents[2] / "config" / "employer_aliases.json"
                with _alias_path.open("r", encoding="utf-8") as _f:
                    _data = _json.load(_f)
                _entries = _data.get("aliases", []) if isinstance(_data, dict) else []
                for _entry in _entries:
                    if not isinstance(_entry, dict):
                        continue
                    if any(a in qn_lower for a in _entry.get("aliases", [])):
                        for _excl in _entry.get("exclude_terms", []):
                            if _excl.lower() in rn_lower:
                                _log.warning(
                                    "CompanyEnrich alias collision: query=%r, returned=%r, alias_match=%r, excluded_term=%r",
                                    company_name, returned_name,
                                    _entry.get("canonical_name"), _excl,
                                )
                                return {
                                    "found": False,
                                    "source": source,
                                    "summary": (
                                        f"CompanyEnrich: Alias collision (queried '{company_name}' "
                                        f"matches alias for '{_entry.get('canonical_name')}', "
                                        f"but returned '{returned_name}' contains excluded term "
                                        f"'{_excl}'). Rejected to prevent identity grafting."
                                    ),
                                    "data": {},
                                    "error": "alias_collision",
                                }
            except (FileNotFoundError, _json.JSONDecodeError, OSError):
                pass  # fail-open: missing/malformed alias file shouldn't break enrichment

            # Layer 2: Composite fuzzy guard (R7-16, 2026-04-27). Reject only
            # when all three strategies fall below threshold. Single strategies
            # fail on legitimate edge cases:
            #   - token_sort_ratio penalizes substring matches ("Starbucks" vs
            #     "Starbucks Coffee Company" = 55% even though clearly the same).
            #   - partial_ratio is too permissive on shared prefixes ("Cleveland
            #     Clinic" vs "Cleveland-Cliffs" = 83%) -- handled by Layer 1.
            #   - token_set_ratio rewards subset overlap ("the kroger" vs
            #     "kroger company" = 75% legitimate).
            # Combined: partial<80 AND token_sort<65 AND token_set<75 catches
            # Crouse Hospital -> Children's National (75/57/70) without
            # false-rejecting Walmart/Starbucks/Apple/Kroger/AT&T.
            try:
                from rapidfuzz import fuzz
                sim_partial = fuzz.partial_ratio(qn_lower, rn_lower)
                sim_sort = fuzz.token_sort_ratio(qn_lower, rn_lower)
                sim_set = fuzz.token_set_ratio(qn_lower, rn_lower)
                if sim_partial < 80 and sim_sort < 65 and sim_set < 75:
                    _log.warning(
                        "CompanyEnrich identity mismatch: query=%r, returned=%r, partial=%d sort=%d set=%d",
                        company_name, returned_name, sim_partial, sim_sort, sim_set,
                    )
                    return {
                        "found": False,
                        "source": source,
                        "summary": (
                            f"CompanyEnrich: Identity mismatch (queried '{company_name}', "
                            f"returned '{returned_name}'; similarity partial={sim_partial}% "
                            f"sort={sim_sort}% set={sim_set}%, all below thresholds). "
                            f"Rejected to prevent identity grafting."
                        ),
                        "data": {},
                        "error": "name_mismatch",
                    }
            except ImportError:
                pass  # rapidfuzz missing; skip guard rather than crash

        # Extract structured data
        location = co.get("location") or {}
        socials = co.get("socials") or {}
        financial = co.get("financial") or {}
        data = {
            "company_name": co.get("name"),
            "domain": co.get("domain"),
            "website": co.get("website") or co.get("domain"),
            "company_type": co.get("type"),
            "industry": co.get("industry"),
            "industries": co.get("industries", []),
            "naics_codes": co.get("naics_codes", []),
            "employee_range": co.get("employees"),
            "revenue_range": co.get("revenue"),
            "founded_year": co.get("founded_year"),
            "location_country": location.get("country"),
            "location_state": location.get("state"),
            "location_city": location.get("city"),
            "linkedin_url": socials.get("linkedin"),
            "twitter_url": socials.get("twitter"),
            "facebook_url": socials.get("facebook"),
            "stock_symbol": financial.get("stockSymbol"),
            "categories": co.get("categories", []),
            "keywords": co.get("keywords", []),
            "technologies": co.get("technologies", []),
        }

        # Build summary
        parts = [f"CompanyEnrich: {data['company_name'] or company_name}"]
        if data["employee_range"]:
            parts.append(f"{data['employee_range']} employees")
        if data["revenue_range"]:
            parts.append(f"Revenue: {data['revenue_range']}")
        if data["industry"]:
            parts.append(f"Industry: {data['industry']}")
        if data["founded_year"]:
            parts.append(f"Founded: {data['founded_year']}")
        if data["website"]:
            parts.append(f"Website: {data['website']}")
        summary = ". ".join(parts) + "."

        return {"found": True, "source": source, "summary": summary, "data": data}

    except Exception as exc:
        return _error_result(source, exc)


def search_brave_web(
    query: str,
    *,
    company_name: Optional[str] = None,
    count: int = 10,
    **_kw,
) -> dict:
    """Search the web using Brave Search API. Returns structured results."""
    source = "api:brave_search"
    try:
        import requests
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if not api_key:
            return {"found": False, "source": source, "summary": "No BRAVE_SEARCH_API_KEY configured.", "data": {}, "error": "missing_key"}

        _brave_limiter.wait()
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(count, 20), "result_filter": "web", "safesearch": "off"},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=10,
        )

        if resp.status_code == 429:
            _log.warning("Brave Search rate limited (429)")
            return {"found": False, "source": source, "summary": "Brave Search: Rate limited.", "data": {}, "error": "rate_limited"}
        resp.raise_for_status()
        body = resp.json()

        web_results = body.get("web", {}).get("results", [])
        if not web_results:
            return {"found": False, "source": source, "summary": f"Brave Search: No results for '{query}'.", "data": {"query": query, "result_count": 0, "results": []}}

        results = []
        for r in web_results[:count]:
            results.append({
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
            })

        top_titles = ", ".join(r["title"] for r in results[:3] if r["title"])
        summary = f"Brave Search: {len(results)} result(s) for '{query}'. Top: {top_titles}"

        return {"found": True, "source": source, "summary": summary, "data": {"query": query, "result_count": len(results), "results": results}}

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# LinkedIn Company Scraping (R-15)
# ---------------------------------------------------------------------------

def search_linkedin_company(company_name: str, linkedin_url: str = None, **_kw) -> dict:
    """Scrape a company's LinkedIn page for structured data using linkedin_scraper."""
    source = "linkedin"
    if not linkedin_url:
        return {"found": False, "source": source, "summary": "No LinkedIn URL provided", "data": {}}

    li_cookie = os.environ.get("LINKEDIN_LI_AT")
    li_email = os.environ.get("LINKEDIN_EMAIL")
    li_password = os.environ.get("LINKEDIN_PASSWORD")

    if not li_cookie and not (li_email and li_password):
        return {"found": False, "source": source, "summary": "No LinkedIn credentials configured (set LINKEDIN_LI_AT or LINKEDIN_EMAIL+LINKEDIN_PASSWORD)", "data": {}}

    try:
        import asyncio as _aio
        from linkedin_scraper import Linkedin

        async def _scrape():
            async with Linkedin(headless=True) as li:
                if li_cookie:
                    await li.login_with_cookie(li_cookie)
                else:
                    await li.login_with_credentials(li_email, li_password)
                return await li.get_company(linkedin_url)

        company = _aio.run(_scrape())

        data = {}
        if company.name:
            data["name"] = company.name
        if company.industry:
            data["industry"] = company.industry
        if company.company_size:
            data["company_size"] = company.company_size
        if company.headcount:
            data["headcount"] = company.headcount
        if company.headquarters:
            data["headquarters"] = company.headquarters
        if company.website:
            data["website"] = company.website
        if company.founded:
            data["founded"] = company.founded
        if company.company_type:
            data["company_type"] = company.company_type
        if company.specialties:
            data["specialties"] = company.specialties
        if company.about_us:
            data["about"] = company.about_us[:500]
        if company.employees:
            data["employee_sample"] = [
                {"name": e.name, "title": e.designation}
                for e in company.employees[:20]
            ]
        if company.affiliated_companies:
            data["affiliated_companies"] = [c.name for c in company.affiliated_companies]

        has_data = bool(data)
        summary_parts = [f"LinkedIn: {data.get('name', company_name)}"]
        if data.get("industry"):
            summary_parts.append(data["industry"])
        if data.get("company_size"):
            summary_parts.append(f"{data['company_size']} employees")
        if data.get("headquarters"):
            summary_parts.append(data["headquarters"])

        return {
            "found": has_data,
            "source": source,
            "summary": ", ".join(summary_parts),
            "data": data,
        }
    except Exception as exc:
        return {"found": False, "source": source, "summary": f"LinkedIn scrape failed: {str(exc)[:200]}", "data": {}, "error": str(exc)[:200]}


# ---------------------------------------------------------------------------
# Union Website Profiles (structured scraper data, 2026-04-19/21)
# ---------------------------------------------------------------------------
# Looks up union locals whose websites mention this employer. Replaces the
# dropped union-website site-restricted web queries with deterministic data
# from `web_union_profiles` (2,189 rows across 7 parent unions -- SEIU,
# AFSCME, IBT, CWA, IBEW, USW, APWU) and `web_union_employers` (2,241 rows
# extracted from union contract/news/about pages via the 2026-04-19/21
# scraper work).

def search_union_web_profiles(
    company_name: str,
    *,
    state: Optional[str] = None,
    employer_id: Optional[str] = None,
    **_kw,
) -> dict:
    """Look up structured union-local web-profile rows that mention this employer.

    Searches `web_union_employers` by name (using the same fuzzy-LIKE pattern
    as other DB tools) and joins back to `web_union_profiles` to return
    human-readable info about the union locals: parent union, local number,
    state, website, officers, and any extracted snippet from contract / news /
    about pages that mentions this employer.

    Useful for answering:
    - "Is any union representing workers at this employer (per union-side
      evidence on their own websites)?"
    - "Which union locals publish contracts, news, or organizing-campaign
      material about this employer?"

    Returns the usual research-agent tool shape
    (`{found, source, summary, data, error}`). When nothing matches, returns
    `{found: False, ...}` without erroring.
    """
    source = "database:web_union_profiles"
    try:
        conn = _conn()
        cur = conn.cursor()

        # Step 1 -- find matching employer mentions in web_union_employers
        name_clause, name_params = _name_like_clause("UPPER(employer_name_clean)", company_name)
        if state:
            cur.execute(f"""
                SELECT id, web_profile_id, employer_name, employer_name_clean,
                       state, sector, source_url, extraction_method,
                       confidence_score, source_element
                FROM web_union_employers
                WHERE {name_clause}
                  AND UPPER(COALESCE(state, '')) = UPPER(%s)
                LIMIT 100
            """, (*name_params, state))
        else:
            cur.execute(f"""
                SELECT id, web_profile_id, employer_name, employer_name_clean,
                       state, sector, source_url, extraction_method,
                       confidence_score, source_element
                FROM web_union_employers
                WHERE {name_clause}
                LIMIT 100
            """, name_params)
        raw_mentions = cur.fetchall()

        # RapidFuzz filter to drop false-positive substring matches
        mentions = _filter_by_name_similarity(raw_mentions, company_name, "employer_name_clean")

        if not mentions:
            conn.close()
            return {
                "found": False,
                "source": source,
                "summary": "No union-website mentions of this employer found in web_union_employers.",
                "data": {"mentions": [], "locals": []},
            }

        # Step 2 -- join back to web_union_profiles for the 1..N distinct locals
        profile_ids = sorted({m["web_profile_id"] for m in mentions if m["web_profile_id"]})
        locals_data: list[dict] = []
        if profile_ids:
            cur.execute("""
                SELECT id, f_num, union_name, parent_union, local_number,
                       state, website_url, officers, address, phone, email,
                       source_directory_url
                FROM web_union_profiles
                WHERE id = ANY(%s)
                ORDER BY parent_union, local_number
            """, (profile_ids,))
            locals_data = [dict(r) for r in cur.fetchall()]

        # Index locals by id for quick lookup
        locals_by_id = {loc["id"]: loc for loc in locals_data}

        # Build per-mention enriched records
        enriched_mentions = []
        for m in mentions:
            loc = locals_by_id.get(m["web_profile_id"])
            enriched_mentions.append({
                "employer_name": m["employer_name"],
                "state": m["state"],
                "source_url": m["source_url"],
                "source_element": m["source_element"],
                "extraction_method": m["extraction_method"],
                "confidence": float(m["confidence_score"] or 0),
                "union_local": {
                    "parent_union": loc["parent_union"] if loc else None,
                    "local_number": loc["local_number"] if loc else None,
                    "state": loc["state"] if loc else None,
                    "website_url": loc["website_url"] if loc else None,
                    "f_num": loc["f_num"] if loc else None,
                } if loc else None,
            })

        # Build summary
        n_mentions = len(enriched_mentions)
        n_locals = len(locals_data)
        parent_unions = sorted({
            loc["parent_union"] for loc in locals_data if loc.get("parent_union")
        })
        states_covered = sorted({
            loc["state"] for loc in locals_data if loc.get("state")
        })

        parts = [
            f"{n_mentions} union-website mention(s) across {n_locals} local(s).",
        ]
        if parent_unions:
            parts.append(f"Parent unions: {', '.join(parent_unions)}.")
        if states_covered:
            parts.append(f"States: {', '.join(states_covered[:8])}{'...' if len(states_covered) > 8 else ''}.")
        summary = " ".join(parts)

        data = {
            "mention_count": n_mentions,
            "local_count": n_locals,
            "parent_unions": parent_unions,
            "states_covered": states_covered,
            "mentions": enriched_mentions[:25],  # cap for payload size
            "locals": [
                {
                    "parent_union": loc["parent_union"],
                    "local_number": loc["local_number"],
                    "state": loc["state"],
                    "website_url": loc["website_url"],
                    "f_num": loc["f_num"],
                    "union_name": loc.get("union_name"),
                    "officers_excerpt": (loc.get("officers") or "")[:300],
                }
                for loc in locals_data
            ],
        }

        conn.close()
        return {
            "found": True,
            "source": source,
            "summary": summary,
            "data": data,
        }

    except Exception as exc:
        return _error_result(source, exc)


# ---------------------------------------------------------------------------
# EPA ECHO direct API
# ---------------------------------------------------------------------------
# Replaces the dead site-restricted EPA ECHO Google query (dropped from the
# agent's taxonomy in Session 1c) with a real API call.
# EPA ECHO publishes a free JSON endpoint (no auth) that returns facility
# compliance records, violation history, and enforcement actions. Documented
# at echo.epa.gov/tools/web-services.

def search_epa_echo(
    company_name: str,
    *,
    state: Optional[str] = None,
    **_kw,
) -> dict:
    """Search EPA ECHO for facilities + compliance records linked to this employer.

    Uses the public `get_facilities` JSON endpoint. Rate-limited to 1 req/sec.
    Returns the usual research-agent tool shape (`{found, source, summary,
    data, error}`) so the agent's orchestration loop handles it identically
    to other external-API tools.
    """
    source = "api:epa_echo"
    import requests

    try:
        _brave_limiter.wait()  # reuse the existing gentle rate-limiter
        params = {
            "output": "JSON",
            "qcolumns": "1,2,3,4,5,7,12,14,21",
            "p_fn": company_name,
            "p_act": "Y",  # active facilities only
            "responseset": "10",
        }
        if state:
            params["p_st"] = state.upper()

        resp = requests.get(
            "https://echodata.epa.gov/echo/echo_rest_services.get_facilities",
            params=params,
            headers={"User-Agent": "LaborDataTerminal/1.0", "Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {
                "found": False,
                "source": source,
                "summary": f"EPA ECHO returned HTTP {resp.status_code}",
                "data": {},
                "error": f"http_{resp.status_code}",
            }
        try:
            body = resp.json()
        except (ValueError, json.JSONDecodeError):
            return {
                "found": False,
                "source": source,
                "summary": "EPA ECHO returned non-JSON body",
                "data": {},
                "error": "non_json",
            }

        # EPA ECHO's `get_facilities` returns a summary envelope keyed
        # `Results`, NOT a facility array. The individual facility rows
        # require a second `get_qid` call with the QueryID. For the
        # research agent's purposes we report the aggregate signals
        # directly -- facility_count, inspections, significant violations,
        # current violations, formal enforcement actions.
        results = body.get("Results") or {}
        facility_count = _safe_int(results.get("QueryRows"))
        inspection_rows = _safe_int(results.get("INSPRows"))
        sig_violations = _safe_int(results.get("SVRows"))   # Significant Violations
        cur_violations = _safe_int(results.get("CVRows"))   # Current Violations
        fea_rows = _safe_int(results.get("FEARows"))        # Formal Enforcement Actions
        v3_rows = _safe_int(results.get("V3Rows"))          # 3-year violations
        query_id = results.get("QueryID")

        if facility_count == 0:
            return {
                "found": False,
                "source": source,
                "summary": f"EPA ECHO: no facilities found for '{company_name}'{f' in {state}' if state else ''}.",
                "data": {
                    "query_id": query_id,
                    "facility_count": 0,
                },
            }

        summary_parts = [
            f"EPA ECHO: {facility_count} facility/facilities matching '{company_name}'"
            + (f" in {state.upper()}" if state else "")
            + "."
        ]
        if inspection_rows:
            summary_parts.append(f"{inspection_rows} inspections.")
        if sig_violations:
            summary_parts.append(f"{sig_violations} significant violations.")
        if cur_violations:
            summary_parts.append(f"{cur_violations} current violations.")
        if fea_rows:
            summary_parts.append(f"{fea_rows} formal enforcement actions.")

        return {
            "found": True,
            "source": source,
            "summary": " ".join(summary_parts),
            "data": {
                "facility_count": facility_count,
                "total_inspections": inspection_rows,
                "significant_violations": sig_violations,
                "current_violations": cur_violations,
                "violations_3yr": v3_rows,
                "enforcement_actions": fea_rows,
                "query_id": query_id,
                # Facility detail requires a second call to
                # `get_qid?qid={query_id}` -- left to the caller if needed.
                "detail_url": (
                    f"https://echodata.epa.gov/echo/echo_rest_services.get_qid?qid={query_id}&output=JSON"
                    if query_id else None
                ),
            },
        }
    except Exception as exc:
        return _error_result(source, exc)


def _safe_int(v) -> int:
    """Coerce a value (string/int/None) to an int, 0 on failure."""
    if v is None:
        return 0
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip() or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------
# Maps tool names (used in Claude API tool definitions) to callables.
# The agent orchestration loop uses this to dispatch tool calls.

TOOL_REGISTRY: dict[str, callable] = {
    "search_osha": search_osha,
    "search_nlrb": search_nlrb,
    "search_nlrb_docket": search_nlrb_docket,
    "search_whd": search_whd,
    "search_sec": search_sec,
    "search_sam": search_sam,
    "search_990": search_990,
    "search_contracts": search_contracts,
    "get_industry_profile": get_industry_profile,
    "get_similar_employers": get_similar_employers,
    "search_mergent": search_mergent,
    "search_job_postings": search_job_postings,
    "get_workforce_demographics": get_workforce_demographics,
    "scrape_employer_website": scrape_employer_website,
    "search_gleif_ownership": search_gleif_ownership,
    "search_political_donations": search_political_donations,
    "search_local_demographics": search_local_demographics,
    "search_warn_notices": search_warn_notices,
    "search_worker_sentiment": search_worker_sentiment,
    "search_sos_filings": search_sos_filings,
    "compare_industry_wages": compare_industry_wages,
    "search_solidarity_network": search_solidarity_network,
    "search_local_subsidies": search_local_subsidies,
    "search_form5500": search_form5500,
    "search_ppp_loans": search_ppp_loans,
    "search_cbp_context": search_cbp_context,
    "search_lodes_workforce": search_lodes_workforce,
    "search_abs_demographics": search_abs_demographics,
    "search_acs_workforce": search_acs_workforce,
    "compare_employer_wages": compare_employer_wages,
    "search_nyc_enforcement": search_nyc_enforcement,
    "search_local_union_density": search_local_union_density,
    "search_corporate_structure": search_corporate_structure,
    "search_employer_locations": search_employer_locations,
    "search_leadership": search_leadership,
    "search_state_enforcement": search_state_enforcement,
    "search_company_enrich": search_company_enrich,
    "search_brave_web": search_brave_web,
    "search_linkedin_company": search_linkedin_company,
    "search_union_web_profiles": search_union_web_profiles,
    "search_epa_echo": search_epa_echo,
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
        "name": "search_nlrb_docket",
        "description": "Search NLRB docket entries for procedural activity on an employer's cases. Returns per-case docket summaries with entry counts, date ranges, and recent activity flags (last 90 days).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
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
        "name": "search_job_postings",
        "description": "Search for active job listings for this employer. Returns estimated posting counts, sample titles, locations, and pay/benefits. Tip: specify a state if searching for a local establishment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "get_workforce_demographics",
        "description": "Get typical workforce demographics (race, gender, age) for the employer's industry and state. Requires a NAICS code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "naics": {"type": "string", "description": "NAICS code (2-6 digits). Required."},
                "state": {"type": "string", "description": "2-letter state code for state-level context"},
            },
            "required": ["company_name", "naics"],
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
        "name": "scrape_employer_website",
        "description": "Scrape the employer's website for company info, leadership, careers/job postings, news, locations, and investor relations. If you don't have a URL, the tool will look it up. Tip: if search_mergent returned a 'website' field, pass that URL here.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "employer_id": {"type": "string", "description": "F7 employer_id for Mergent URL lookup"},
                "url": {"type": "string", "description": "Company website URL if known (e.g. from search_mergent)"},
                "industry": {"type": "string", "description": "Industry name or NAICS code for better URL lookup"},
                "state": {"type": "string", "description": "2-letter state code for better URL lookup"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_gleif_ownership",
        "description": "Search GLEIF database for corporate ownership and parent-child relationships. Returns legal name, LEI, parents, and subsidiaries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "employer_id": {"type": "string", "description": "F7 employer_id for precise lookup"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_political_donations",
        "description": "Search for political donations from the company and its top executives. Returns total amounts, partisan lean, and top donor details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "ceo_name": {"type": "string", "description": "Name of the CEO or top executive if known"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_local_demographics",
        "description": "Search for local city/state demographic data (population, race, income, major industries). Replaces national industry baselines with local context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "city": {"type": "string", "description": "City name"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name", "city", "state"],
        },
    },
    {
        "name": "search_warn_notices",
        "description": "Search for recent mass layoff (WARN Act) notices filed by this employer. Returns dates and worker counts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_worker_sentiment",
        "description": "Search for worker reviews and sentiment on Reddit, Glassdoor, and Indeed. Returns specific grievances and sentiment scores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_sos_filings",
        "description": "Search for official state Secretary of State corporate filings. Returns registered agent, officers, and filing links.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "state": {"type": "string", "description": "2-letter state code (Required)"},
            },
            "required": ["company_name", "state"],
        },
    },
    {
        "name": "compare_industry_wages",
        "description": "Compare target company wages with local competitors in the same sector. Returns market position and specific competitor pay rates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "industry": {"type": "string", "description": "Industry/Sector name (e.g. 'Warehouse', 'Nursing')"},
                "city": {"type": "string", "description": "City name"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name", "industry", "city", "state"],
        },
    },
    {
        "name": "search_solidarity_network",
        "description": "Find unionized 'sister' companies within the same corporate family using GLEIF and our union database. Returns a list of unionized facilities coverage totals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "employer_id": {"type": "string", "description": "F7 employer_id for precise tracing"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_local_subsidies",
        "description": "Search for local tax breaks, abatements, and public subsidies received by this employer. Returns dollar amounts and summary of awards.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "city": {"type": "string", "description": "City name"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name", "city", "state"],
        },
    },
    {
        "name": "search_form5500",
        "description": "Search Form 5500 benefit plan filings for this employer. Returns plan count, active participants, collective bargaining status, pension/welfare plan indicators, and filing history. Useful for understanding employer investment in worker benefits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known (for precise lookup)"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_ppp_loans",
        "description": "Search SBA Paycheck Protection Program (PPP) loan data (2020-2021). Returns loan amounts, forgiveness status, and jobs retained claims. Provides pandemic-era financial stability context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "state": {"type": "string", "description": "2-letter state code to narrow search"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_cbp_context",
        "description": "Search County Business Patterns for local industry context. Returns establishment counts, total employment, average wages, and industry concentration for a given NAICS code and state/county. Helps assess competitive landscape.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "naics": {"type": "string", "description": "NAICS code (2-6 digits). Required."},
                "state": {"type": "string", "description": "2-letter state code for state-level data"},
                "county_fips": {"type": "string", "description": "5-digit county FIPS code for county-level data"},
            },
            "required": ["company_name", "naics"],
        },
    },
    {
        "name": "search_lodes_workforce",
        "description": "Search LEHD LODES for county-level workforce metrics. Returns total jobs, earnings distribution (low/mid/high), industry sector breakdown, and commute patterns. Helps assess labor market tightness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "state": {"type": "string", "description": "2-letter state code"},
                "county_fips": {"type": "string", "description": "5-digit county FIPS code for precise data"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_abs_demographics",
        "description": "Search Annual Business Survey for firm demographics by industry. Returns firm counts by owner race, sex, veteran status, and firm size distribution. Provides diversity context for the employer's industry.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "naics": {"type": "string", "description": "NAICS code (2-6 digits). Required."},
                "state": {"type": "string", "description": "2-letter state code for state-level data"},
            },
            "required": ["company_name", "naics"],
        },
    },
    {
        "name": "search_acs_workforce",
        "description": "Search ACS (American Community Survey) workforce demographics for a state and optional industry/occupation. Returns gender split, race/ethnicity breakdown, age distribution, education profile, and worker class (private/govt/self-employed). Answers 'who works in this industry here?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "state": {"type": "string", "description": "2-letter state code. Required."},
                "naics": {"type": "string", "description": "NAICS code (first 4 digits used) for industry filtering"},
                "soc_code": {"type": "string", "description": "SOC occupation code for occupation filtering"},
                "metro_cbsa": {"type": "string", "description": "Metro area CBSA code for metro filtering"},
            },
            "required": ["company_name", "state"],
        },
    },
    {
        "name": "compare_employer_wages",
        "description": "Compare employer wages against QCEW (BLS) local industry averages. Returns avg annual pay for the industry in the state, and if a known_wage is provided, computes a ratio and low-wage flag. Useful for assessing whether the employer pays below local industry norms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "state": {"type": "string", "description": "2-letter state code. Required."},
                "naics": {"type": "string", "description": "NAICS code (first 2 digits used). Required."},
                "known_wage": {"type": "number", "description": "Known annual wage for this employer (from WHD, 990, or research). If provided, a ratio against local avg is computed."},
            },
            "required": ["company_name", "state", "naics"],
        },
    },
    {
        "name": "search_nyc_enforcement",
        "description": "Search NYC/NYS enforcement tables for wage theft, debarment, and local labor law violations. Covers NYS wage theft cases, NYC debarment list, and NYC local labor law enforcement actions. Small tables searched by name matching.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code (mainly NY)"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_local_union_density",
        "description": "Get local union density context for a state and optional industry. Returns F7 unionized employer counts, top unions, recent NLRB elections (3yr), and BLS state density benchmark. Useful for assessing organizing climate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name (for context)"},
                "state": {"type": "string", "description": "2-letter state code. Required."},
                "naics": {"type": "string", "description": "NAICS code (first 2 digits used for industry filter)"},
                "city": {"type": "string", "description": "City name (for context)"},
                "zip_code": {"type": "string", "description": "ZIP code (for context)"},
            },
            "required": ["company_name", "state"],
        },
    },
    {
        "name": "search_corporate_structure",
        "description": "Build corporate family tree from crosswalk, GLEIF ownership, CorpWatch hierarchy, and SEC data. Returns parent company, subsidiaries, unionized siblings, and public/private status. Use for 'Who owns this company?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_employer_locations",
        "description": "Discover employer locations from OSHA establishment records, SAM entities, and match data. Returns addresses, employee counts, and state-level grouping. Use for 'Does this employer have other locations?'",
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
        "name": "search_leadership",
        "description": "Extract leadership and management info from SEC, crosswalk, and web search. Returns CEO, executives, board members. Use for 'Who runs this company?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_state_enforcement",
        "description": "Search state and local enforcement records beyond federal OSHA/WHD. Covers NYC debarment, state labor violations, state OSHA plans, and state/local contracts via web search. Use for 'Are there state-level violations?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for"},
                "employer_id": {"type": "string", "description": "F7 employer_id if known"},
                "state": {"type": "string", "description": "2-letter state code. Recommended for targeted results."},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_company_enrich",
        "description": "Enrich company identity data using CompanyEnrich.com (30M+ companies). Returns employee count range, revenue range, website, LinkedIn URL, founding year, industry, company type, and social profiles. Covers millions of companies including private. Use this early to fill identity and financial gaps. Pass domain if known from other tools for better match accuracy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to look up"},
                "domain": {"type": "string", "description": "Company website domain if known (e.g. 'amazon.com') -- improves match accuracy"},
                "linkedin_url": {"type": "string", "description": "Company LinkedIn URL if known"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_brave_web",
        "description": "Search the web using Brave Search API. Returns structured web results with URLs, titles, and descriptions. Use for finding recent news, WARN notices, leadership names, corporate filings, or any web intelligence about a company. More traceable than Google grounding -- exact query and results are logged.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string (e.g. '\"Amazon\" WARN layoff notice 2025')"},
                "company_name": {"type": "string", "description": "Company name for logging context"},
                "count": {"type": "integer", "description": "Number of results (default 10, max 20)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_linkedin_company",
        "description": "Scrape a company's LinkedIn page for structured data: industry, employee size, headquarters, founding year, specialties, employee sample, and affiliated companies. Requires a LinkedIn URL. Use when CompanyEnrich or other tools have provided a linkedin_url.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "linkedin_url": {"type": "string", "description": "LinkedIn company page URL (e.g. 'https://www.linkedin.com/company/starbucks')"},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_union_web_profiles",
        "description": "Look up structured union-local web-profile rows that mention this employer. Searches 2,241 employer mentions extracted from union websites (contract pages, news, about pages) by the 2026-04-19/21 scraper work across 7 parent unions (SEIU, AFSCME, IBT, CWA, IBEW, USW, APWU). Returns which union locals mention the employer, their parent union, local number, state, website, and officers excerpt. Use this INSTEAD of union-website site-restricted Google queries -- it's structured data we already own.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name to search for in union-website employer mentions."},
                "state": {"type": "string", "description": "Optional 2-letter state code to restrict results (e.g. 'CA')."},
                "employer_id": {"type": "string", "description": "Optional F7 employer_id if known (currently unused by this tool but reserved for future F-7 linkage)."},
            },
            "required": ["company_name"],
        },
    },
    {
        "name": "search_epa_echo",
        "description": "Query EPA ECHO (Enforcement and Compliance History Online) via the direct JSON API for facilities and environmental-compliance records linked to this employer. Returns facility count, inspection count, violation count, and formal enforcement actions across Clean Water Act / Clean Air Act / RCRA programs. Use INSTEAD of site-restricted Google queries -- this hits the authoritative ECHO dataset directly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company or facility name to search for."},
                "state": {"type": "string", "description": "Optional 2-letter state code to restrict results (e.g. 'CA')."},
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
