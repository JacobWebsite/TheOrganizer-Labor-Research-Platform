"""
Research Agent — Core Orchestration Loop (Gemini 2.5 Flash)

Runs a deep-dive research session on a single employer:

  1. Loads run metadata from research_runs
  2. Builds a system prompt with company context, tool list, dossier template
  3. Calls Google Gemini API in a tool-use loop
  4. Dispatches function_call parts to the local tool registry
  5. Logs every action to research_actions
  6. Parses the final dossier JSON from Gemini's response
  7. Saves individual facts to research_facts
  8. Updates research_runs with results

The function ``run_research`` is the main entry point.  It is designed to be
called from a FastAPI BackgroundTask (or directly for testing).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Project-root imports
# ---------------------------------------------------------------------------
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from google import genai
from google.genai import types
from psycopg2.extras import RealDictCursor
from db_config import get_connection

from scripts.research.tools import TOOL_REGISTRY, TOOL_DEFINITIONS

_log = logging.getLogger("research.agent")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = os.getenv("RESEARCH_AGENT_MODEL", "gemini-2.5-flash")
MAX_TOOL_TURNS = int(os.getenv("RESEARCH_AGENT_MAX_TURNS", "25"))
MAX_TOKENS = int(os.getenv("RESEARCH_AGENT_MAX_TOKENS", "65536"))

# Gemini 2.5 Flash pricing (cents per 1K tokens)
_INPUT_COST_PER_1K = 0.03    # $0.30/M input
_OUTPUT_COST_PER_1K = 0.25   # $2.50/M output

# Ordered list of internal tools (for progress tracking)
_INTERNAL_TOOLS = [
    "search_osha", "search_nlrb", "search_whd", "search_sec",
    "search_sam", "search_990", "search_contracts", "search_mergent",
    "get_industry_profile", "get_similar_employers", "scrape_employer_website",
    "google_search",
]

# Dossier sections
_DOSSIER_SECTIONS = [
    "identity", "financial", "workforce", "labor",
    "workplace", "assessment", "sources",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn():
    return get_connection(cursor_factory=RealDictCursor)


def _safe(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return val


def _update_run(run_id: int, **fields):
    """Update fields on the research_runs row."""
    if not fields:
        return
    sets = []
    vals = []
    for k, v in fields.items():
        sets.append(f"{k} = %s")
        vals.append(v)
    sets.append("updated_at = NOW()")
    vals.append(run_id)
    sql = f"UPDATE research_runs SET {', '.join(sets)} WHERE id = %s"
    conn = _conn()
    cur = conn.cursor()
    cur.execute(sql, vals)
    conn.commit()
    conn.close()


def _progress(run_id: int, step: str, pct: int):
    """Update the progress indicator visible to the frontend."""
    _update_run(run_id, current_step=step, progress_pct=min(pct, 100))


def _ensure_vocab_entries():
    """Ensure vocabulary entries added after initial schema creation exist."""
    conn = _conn()
    cur = conn.cursor()
    # federal_contract_status was missing from the original seed data
    cur.execute("""
        INSERT INTO research_fact_vocabulary
            (attribute_name, display_name, dossier_section, data_type,
             existing_column, existing_table, description)
        VALUES ('federal_contract_status', 'Federal Contractor', 'financial', 'boolean',
                'is_federal_contractor', 'federal_contract_recipients',
                'Whether the employer is a federal contractor')
        ON CONFLICT (attribute_name) DO NOTHING
    """)
    conn.commit()
    conn.close()


def _load_vocabulary() -> dict[str, dict]:
    """Load the fact vocabulary into a lookup dict keyed by attribute_name."""
    _ensure_vocab_entries()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM research_fact_vocabulary")
    rows = cur.fetchall()
    conn.close()
    return {r["attribute_name"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Result Caching
# ---------------------------------------------------------------------------

# Default cache window: 7 days. Tool results don't change often.
CACHE_MAX_AGE_HOURS = int(os.getenv("RESEARCH_CACHE_HOURS", "168"))


def _check_cache(employer_id: Optional[int], tool_name: str,
                 max_age_hours: int = CACHE_MAX_AGE_HOURS) -> Optional[dict]:
    """Check for a recent successful result for this tool+employer.

    Returns the cached row (result_summary, tool_params) or None.
    """
    if not employer_id:
        return None
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ra.result_summary, ra.tool_params
        FROM research_actions ra
        JOIN research_runs rr ON ra.run_id = rr.id
        WHERE ra.tool_name = %s AND ra.data_found = TRUE
          AND rr.employer_id = %s
          AND rr.started_at > NOW() - make_interval(hours := %s)
        ORDER BY ra.created_at DESC LIMIT 1
    """, (tool_name, employer_id, max_age_hours))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Gap-Aware Web Search (Phase 5.2)
# ---------------------------------------------------------------------------

def _ensure_query_effectiveness_table():
    """Create the query effectiveness table if it doesn't exist."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_query_effectiveness (
            id                      SERIAL PRIMARY KEY,
            gap_type                TEXT NOT NULL,
            company_type            VARCHAR(30),
            industry_sector         VARCHAR(10),
            query_template          TEXT NOT NULL,
            times_used              INTEGER DEFAULT 0,
            times_produced_result   INTEGER DEFAULT 0,
            avg_facts_produced      REAL DEFAULT 0,
            last_used_at            TIMESTAMPTZ,
            created_at              TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(gap_type, query_template)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_qe_gap
        ON research_query_effectiveness(gap_type)
    """)
    conn.commit()
    conn.close()


# Maps each data gap to targeted search queries.
# {company} and {state} and {year} are filled at runtime.
_GAP_QUERY_TEMPLATES = {
    # When Mergent misses (48% miss rate)
    "employee_count": [
        '"{company}" number of employees',
        '"{company}" workforce size headcount',
        '"{company}" company size LinkedIn',
    ],
    "revenue": [
        '"{company}" annual revenue sales',
        '"{company}" revenue financial results {year}',
    ],
    "website_url": [
        '"{company}" official website {state}',
    ],
    # When OSHA misses
    "osha_violations": [
        '"{company}" OSHA violations safety citations',
        '"{company}" workplace safety inspection {state}',
    ],
    # When NLRB misses
    "nlrb_activity": [
        '"{company}" NLRB union election filing',
        '"{company}" unfair labor practice charge',
        '"{company}" union organizing campaign {year}',
    ],
    # When WHD misses
    "whd_violations": [
        '"{company}" wage theft Department of Labor',
        '"{company}" Fair Labor Standards Act violation',
    ],
    # When 990 misses (nonprofits)
    "nonprofit_financials": [
        '"{company}" 990 tax return nonprofit revenue',
        '"{company}" GuideStar ProPublica nonprofit',
    ],
    # Always-run queries (refined from current static 6)
    "recent_news": [
        '"{company}" news {year}',
        '"{company}" layoffs expansion acquisition {year}',
    ],
    "labor_stance": [
        '"{company}" union stance labor relations',
        '"{company}" anti-union OR pro-union workers',
    ],
    "worker_conditions": [
        '"{company}" Glassdoor employee reviews working conditions',
        '"{company}" worker complaints lawsuit labor',
    ],
}

# Maps tool names to the gap types they cover
_TOOL_GAP_MAP = {
    "search_mergent": ["employee_count", "revenue", "website_url"],
    "search_osha": ["osha_violations"],
    "search_nlrb": ["nlrb_activity"],
    "search_whd": ["whd_violations"],
    "search_990": ["nonprofit_financials"],
}


def _get_best_queries(gap_type: str, company_type: Optional[str] = None,
                      min_uses: int = 3) -> list[str]:
    """Return query templates ranked by effectiveness.

    After ~20-30 runs, the system naturally surfaces templates that work
    and suppresses those that don't.
    """
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT query_template
            FROM research_query_effectiveness
            WHERE gap_type = %s AND times_used >= %s
              AND (company_type = %s OR company_type IS NULL)
            ORDER BY times_produced_result::float / NULLIF(times_used, 0) DESC
            LIMIT 5
        """, (gap_type, min_uses, company_type))
        rows = cur.fetchall()
        conn.close()
        return [r["query_template"] for r in rows] if rows else []
    except Exception:
        return []


def _build_web_search_queries(company_name: str, company_type: Optional[str],
                               company_state: Optional[str],
                               db_gaps: list[str],
                               year: str = "2025") -> list[str]:
    """Build targeted search queries based on which DB tools missed.

    Args:
        company_name: The employer name
        company_type: public/private/nonprofit/government
        company_state: 2-letter state code
        db_gaps: list of tool_names that returned no data
        year: current year for recency queries

    Returns:
        List of filled query strings, capped at 15.
    """
    queries = []
    gap_types_used = []  # track (gap_type, template) for effectiveness logging

    for tool_name in db_gaps:
        for gap_key in _TOOL_GAP_MAP.get(tool_name, []):
            # Check learned effectiveness first
            best = _get_best_queries(gap_key, company_type)
            templates = best or _GAP_QUERY_TEMPLATES.get(gap_key, [])
            for t in templates[:2]:
                queries.append(t)
                gap_types_used.append((gap_key, t))

    # Always-run queries
    for key in ["recent_news", "labor_stance", "worker_conditions"]:
        templates = _GAP_QUERY_TEMPLATES[key]
        for t in templates[:1]:
            queries.append(t)
            gap_types_used.append((key, t))

    # Fill placeholders
    filled = []
    for q in queries:
        try:
            filled.append(q.format(
                company=company_name,
                state=company_state or "",
                year=year,
            ))
        except (KeyError, IndexError):
            filled.append(q.replace("{company}", company_name))

    return filled[:15], gap_types_used[:15]


def _update_query_effectiveness(gap_types_queried: list[tuple],
                                 facts_by_section: dict[str, int],
                                 company_type: Optional[str] = None):
    """Update hit rates for query templates after a run.

    Args:
        gap_types_queried: list of (gap_type, template) pairs from _build_web_search_queries
        facts_by_section: dict mapping gap_type -> number of facts produced
        company_type: employer type for segmented tracking
    """
    if not gap_types_queried:
        return
    try:
        _ensure_query_effectiveness_table()
        conn = _conn()
        cur = conn.cursor()
        for gap_type, template in gap_types_queried:
            produced = 1 if facts_by_section.get(gap_type, 0) > 0 else 0
            cur.execute("""
                INSERT INTO research_query_effectiveness
                    (gap_type, company_type, query_template,
                     times_used, times_produced_result, last_used_at)
                VALUES (%s, %s, %s, 1, %s, NOW())
                ON CONFLICT (gap_type, query_template) DO UPDATE
                SET times_used = research_query_effectiveness.times_used + 1,
                    times_produced_result = research_query_effectiveness.times_produced_result + EXCLUDED.times_produced_result,
                    company_type = COALESCE(EXCLUDED.company_type, research_query_effectiveness.company_type),
                    last_used_at = NOW()
            """, (gap_type, company_type, template, produced))
        conn.commit()
        conn.close()
    except Exception as e:
        _log.warning("Failed to update query effectiveness: %s", e)


# ---------------------------------------------------------------------------
# Gemini Tool Definitions
# ---------------------------------------------------------------------------

def _build_gemini_tools() -> list[types.Tool]:
    """Convert our TOOL_DEFINITIONS to Gemini FunctionDeclaration format."""
    declarations = []
    for td in TOOL_DEFINITIONS:
        # Skip stubs — web search uses a separate grounding phase,
        # scraper is not yet implemented
        if td["name"] in ("search_web",):
            continue

        schema = td["input_schema"]
        props = {}
        for pname, pdef in schema.get("properties", {}).items():
            props[pname] = types.Schema(
                type=pdef["type"].upper(),
                description=pdef.get("description", ""),
            )

        declarations.append(types.FunctionDeclaration(
            name=td["name"],
            description=td["description"],
            parameters=types.Schema(
                type="OBJECT",
                properties=props,
                required=schema.get("required", []),
            ),
        ))

    return [types.Tool(function_declarations=declarations)]


def _build_google_search_tool() -> list[types.Tool]:
    """Build a tools list with only Google Search grounding.

    Gemini does not allow function_declarations and google_search in the
    same request, so we run web search as a separate phase after the
    function-calling loop completes.
    """
    return [types.Tool(google_search=types.GoogleSearch())]


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(run: dict, vocabulary: dict[str, dict]) -> str:
    """Build the system prompt for the research agent."""

    vocab_by_section: dict[str, list[str]] = {}
    for attr, meta in vocabulary.items():
        sec = meta["dossier_section"]
        vocab_by_section.setdefault(sec, []).append(
            f"  - {attr} ({meta['data_type']}): {meta['description']}"
        )

    vocab_text = ""
    for sec in _DOSSIER_SECTIONS:
        attrs = vocab_by_section.get(sec, [])
        vocab_text += f"\n### {sec}\n" + "\n".join(attrs) + "\n"

    company_name = run["company_name"]
    employer_id = run.get("employer_id") or "unknown"
    naics = run.get("industry_naics") or "unknown"
    company_type = run.get("company_type") or "unknown"
    state = run.get("company_state") or "unknown"
    size_bucket = run.get("employee_size_bucket") or "unknown"

    return f"""You are a labor-relations research agent. Your job is to compile a comprehensive organizing dossier on a single employer by querying internal databases.

## Company Under Research
- **Name:** {company_name}
- **Employer ID (internal):** {employer_id}
- **NAICS:** {naics}
- **Type:** {company_type}
- **State:** {state}
- **Size bucket:** {size_bucket}

## Instructions

1. **Check internal databases first** (fast, free):
   - OSHA violations (search_osha)
   - NLRB elections & ULP charges (search_nlrb)
   - Wage & Hour cases (search_whd)
   - SEC filings (search_sec) -- skip if private/nonprofit
   - SAM.gov federal contracts (search_sam)
   - IRS 990 nonprofit data (search_990) -- skip if public company
   - Existing union contracts (search_contracts)
   - Mergent business data (search_mergent)

2. **Get industry context:**
   - BLS industry profile (get_industry_profile) -- needs a NAICS code
   - Similar organized employers (get_similar_employers)

3. **Scrape employer website** (scrape_employer_website) -- if search_mergent returned a website URL, pass it here. Otherwise the tool will look it up. Returns homepage, about, careers, and news text.

4. **Synthesize** your findings into the dossier.

IMPORTANT: Do NOT attempt to call google_search or any web search tool. Web search is handled separately after your database queries. Focus ONLY on the database tools listed above.

Always pass the company_name parameter. If the employer_id is known (not "unknown"), pass it too for more precise matching.
If the NAICS is known, pass it to get_industry_profile and get_similar_employers.
If the state is known, pass it where accepted.

If a tool returns no results for a long company name, try again with a well-known abbreviation or shorter name (e.g., "University of Pittsburgh Medical Center" -> try "UPMC", "United Parcel Service" -> try "UPS"). The database tools now handle acronym matching automatically, but Gemini-chosen alternate names can help too.

If search_990 returns financial data (revenue, assets, employees), include it prominently in the "financial" section. Nonprofit 990 data is critical intelligence -- never omit it from the dossier.

You MAY skip tools that clearly don't apply (e.g., skip search_sec for nonprofits, skip search_990 for public companies). Briefly note each skip and why.

## Dossier Fact Vocabulary

When you compile the final dossier, use ONLY these attribute names:
{vocab_text}

## Output Format

After gathering data from all relevant tools, produce your final answer as a single JSON code block with the following structure:

```json
{{
  "dossier": {{
    "identity": {{ "<attribute_name>": <value>, ... }},
    "financial": {{ ... }},
    "workforce": {{ ... }},
    "labor": {{ ... }},
    "workplace": {{ ... }},
    "assessment": {{ ... }},
    "sources": {{ ... }}
  }},
  "facts": [
    {{
      "dossier_section": "...",
      "attribute_name": "...",
      "attribute_value": "...",
      "attribute_value_json": null,
      "source_type": "database",
      "source_name": "...",
      "confidence": 0.9,
      "as_of_date": "YYYY-MM-DD or null"
    }}
  ],
  "skipped_tools": [
    {{ "tool": "...", "reason": "..." }}
  ]
}}
```

For the **assessment** section, provide factual analysis only:
- `data_summary`: 2-3 paragraph factual summary of what the data reveals. State what was found, patterns, and what is notable. No strategy recommendations.
- `web_intelligence`: Key findings from web search beyond database records. Include dates and sources.
- `source_contradictions`: Contradictions between data sources (e.g., DB says no NLRB activity but web reports ongoing campaigns).
- `data_gaps`: Critical information missing or unverifiable.

Do NOT include: recommended_approach, similar_organized, or strategic advice.

For the **sources** section:
- `section_confidence`: object mapping each section to "high"/"medium"/"low"
- `data_gaps`: list of what was NOT found
- `source_list`: list of every source checked

Make sure every fact in the `facts` array uses an `attribute_name` from the vocabulary above. Use `attribute_value` for simple text/number values and `attribute_value_json` for complex objects (lists, dicts).

Be thorough but efficient. Do not call the same tool twice with the same parameters."""


# ---------------------------------------------------------------------------
# Action logging
# ---------------------------------------------------------------------------

def _log_action(
    run_id: int,
    tool_name: str,
    tool_params: dict,
    execution_order: int,
    result: dict,
    latency_ms: int,
    company_context: Optional[dict] = None,
) -> int:
    """Insert a row into research_actions and return the action id."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO research_actions
            (run_id, tool_name, tool_params, execution_order,
             data_found, data_quality, facts_extracted,
             result_summary, latency_ms, company_context, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        run_id,
        tool_name,
        json.dumps(tool_params),
        execution_order,
        result.get("found", False),
        1.0 if result.get("found") else 0.0,
        0,
        result.get("summary", "")[:1000],
        latency_ms,
        json.dumps(company_context) if company_context else None,
        result.get("error"),
    ))
    action_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return action_id


# ---------------------------------------------------------------------------
# Fact saving
# ---------------------------------------------------------------------------

def _flatten_fact_value(val, val_json):
    """Ensure attribute_value is always a displayable string.

    When Gemini sets attribute_value to None but puts data in
    attribute_value_json, we derive a human-readable string so the
    frontend never shows raw JSON or [object Object].
    """
    if val is not None:
        return val
    if val_json is None:
        return None
    # val is None but val_json has data — derive a display string
    if isinstance(val_json, str):
        try:
            parsed = json.loads(val_json)
        except (json.JSONDecodeError, TypeError):
            return val_json
        val_json = parsed
    if isinstance(val_json, list):
        if not val_json:
            return None
        if all(isinstance(x, str) for x in val_json):
            return ", ".join(val_json)
        return f"{len(val_json)} item(s)"
    if isinstance(val_json, dict):
        parts = []
        for k, v in val_json.items():
            if v is not None:
                parts.append(f"{k}: {v}")
        return ", ".join(parts) if parts else None
    return str(val_json)


def _save_facts(run_id: int, employer_id: Optional[int], facts: list[dict], vocabulary: dict) -> int:
    """Save parsed facts to research_facts. Returns count saved."""
    if not facts:
        return 0

    conn = _conn()
    cur = conn.cursor()
    saved = 0

    for f in facts:
        attr = f.get("attribute_name", "")
        if attr not in vocabulary:
            _log.warning("Skipping unknown attribute_name: %s", attr)
            continue

        val = f.get("attribute_value")
        val_json = f.get("attribute_value_json")
        if val_json and not isinstance(val_json, str):
            val_json = json.dumps(val_json)
        elif not val_json:
            val_json = None

        # Ensure attribute_value is always a displayable string
        val = _flatten_fact_value(val, val_json)

        if val is not None and not isinstance(val, str):
            val = json.dumps(val) if isinstance(val, (dict, list)) else str(val)

        # Sanitize as_of_date — Gemini sometimes returns just a year
        as_of_date = f.get("as_of_date")
        if as_of_date:
            as_of_date = str(as_of_date).strip()
            if re.match(r"^\d{4}$", as_of_date):
                as_of_date = f"{as_of_date}-01-01"
            elif re.match(r"^\d{4}-\d{2}$", as_of_date):
                as_of_date = f"{as_of_date}-01"
            elif not re.match(r"^\d{4}-\d{2}-\d{2}", as_of_date):
                as_of_date = None  # unparseable, skip

        # Sanitize confidence
        confidence = f.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5

        cur.execute("""
            INSERT INTO research_facts
                (run_id, employer_id, dossier_section, attribute_name,
                 attribute_value, attribute_value_json,
                 source_type, source_name, source_url,
                 confidence, as_of_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            run_id,
            employer_id,
            f.get("dossier_section", vocabulary[attr]["dossier_section"]),
            attr,
            val,
            val_json,
            f.get("source_type", "database"),
            f.get("source_name"),
            f.get("source_url"),
            confidence,
            as_of_date,
        ))
        saved += 1

    conn.commit()
    conn.close()
    return saved


# ---------------------------------------------------------------------------
# Fallback fact extraction from research_actions
# ---------------------------------------------------------------------------

# Maps tool_name -> list of (attribute_name, extractor_key_or_None)
_TOOL_FACT_MAP = {
    "search_990": [
        ("nonprofit_revenue", "total_revenue"),
        ("nonprofit_assets", "total_assets"),
        ("employee_count", "total_employees"),       # was nonprofit_employees (not in vocab)
    ],
    "search_osha": [
        ("osha_violation_count", "violation_count"),
        ("osha_serious_count", "serious_count"),
        ("osha_penalty_total", "penalty_total"),
    ],
    "search_nlrb": [
        ("nlrb_election_count", "election_count"),
        ("nlrb_ulp_count", "ulp_count"),
    ],
    "search_whd": [
        ("whd_case_count", "case_count"),
        ("whd_backwages", "total_backwages"),
    ],
    "search_sam": [
        ("federal_contract_status", "is_federal_contractor"),
    ],
    "search_contracts": [
        ("existing_contracts", "contract_count"),
    ],
    "search_mergent": [
        ("employee_count", "employees_all_sites"),
        ("revenue", "sales_amount"),                 # was annual_revenue (not in vocab)
        ("website_url", "website"),                   # was company_website (not in vocab)
    ],
    "scrape_employer_website": [
        ("website_url", "url"),                       # was company_website (not in vocab)
    ],
}

# Maps attribute_name -> dossier_section (must match _TOOL_FACT_MAP keys)
_ATTR_SECTION = {
    "nonprofit_revenue": "financial", "nonprofit_assets": "financial",
    "osha_violation_count": "workplace", "osha_serious_count": "workplace",
    "osha_penalty_total": "workplace",
    "nlrb_election_count": "labor", "nlrb_ulp_count": "labor",
    "whd_case_count": "workplace", "whd_backwages": "workplace",
    "federal_contract_status": "financial",
    "existing_contracts": "labor",
    "employee_count": "financial", "revenue": "financial",
    "website_url": "identity",
}


def _extract_fallback_facts(run_id: int) -> list[dict]:
    """Extract basic facts from research_actions when dossier JSON parsing fails.

    Tool results are already persisted in research_actions during Phase 1.
    This function harvests them into the facts format so 990 data (and all
    other tool data) survives even when Gemini produces unparseable JSON.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT tool_name, data_found, result_summary, tool_params
        FROM research_actions
        WHERE run_id = %s AND data_found = TRUE
        ORDER BY execution_order
    """, (run_id,))
    actions = cur.fetchall()
    conn.close()

    facts = []
    for action in actions:
        tool_name = action["tool_name"]
        mapping = _TOOL_FACT_MAP.get(tool_name, [])
        summary = action.get("result_summary") or ""

        for attr_name, _key in mapping:
            # We don't have the raw data dict here (only the summary was
            # persisted), so use the summary as the attribute_value.
            section = _ATTR_SECTION.get(attr_name, "identity")
            facts.append({
                "dossier_section": section,
                "attribute_name": attr_name,
                "attribute_value": summary[:500],
                "attribute_value_json": None,
                "source_type": "database",
                "source_name": tool_name,
                "confidence": 0.8,
            })
            # Only emit one fact per tool for fallback (the summary covers it)
            break

    _log.info("Fallback extraction produced %d facts from %d successful actions",
              len(facts), len(actions))
    return facts


# ---------------------------------------------------------------------------
# Dossier JSON parser
# ---------------------------------------------------------------------------

def _fix_json_escapes(s: str) -> str:
    """Fix invalid JSON escape sequences that Gemini sometimes produces.

    JSON only allows: \\", \\\\, \\/, \\b, \\f, \\n, \\r, \\t, \\uXXXX.
    Gemini sometimes emits \\S, \\s, \\d, etc. Replace them with the
    literal character (drop the backslash).
    """
    return re.sub(
        r'\\([^"\\/bfnrtu])',
        lambda m: m.group(1),
        s,
    )


def _try_parse_json(text: str) -> Optional[dict]:
    """Try to parse JSON with progressive repair strategies."""
    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fix invalid escape sequences
    try:
        return json.loads(_fix_json_escapes(text))
    except json.JSONDecodeError:
        pass

    # Strategy 3: fix unescaped quotes inside strings by removing
    # control characters and other common Gemini quirks
    cleaned = text
    # Remove any trailing garbage after the last }
    last_brace = cleaned.rfind("}")
    if last_brace > 0:
        cleaned = cleaned[: last_brace + 1]
    try:
        return json.loads(_fix_json_escapes(cleaned))
    except json.JSONDecodeError:
        pass

    # Strategy 4: strip non-JSON prefix before first {
    first_brace = text.find("{")
    if first_brace > 0:
        stripped = text[first_brace:]
        try:
            return json.loads(_fix_json_escapes(stripped))
        except json.JSONDecodeError:
            pass
        # Also try trimming trailing garbage on the stripped version
        last = stripped.rfind("}")
        if last > 0:
            try:
                return json.loads(_fix_json_escapes(stripped[: last + 1]))
            except json.JSONDecodeError:
                pass

    return None


def _extract_dossier_json(text: str) -> Optional[dict]:
    """Extract the JSON dossier from Gemini's final text response."""
    # Look for ```json ... ``` block (flexible whitespace handling)
    m = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if m:
        obj = _try_parse_json(m.group(1).strip())
        if obj:
            return obj
        _log.warning("Failed to parse dossier JSON from code block")

    # Fallback: find the first { that starts a "dossier" object
    # Only check the first few { characters, not the entire string
    attempts = 0
    for start in range(len(text)):
        if text[start] == '{':
            obj = _try_parse_json(text[start:])
            if obj and isinstance(obj, dict) and "dossier" in obj:
                return obj
            attempts += 1
            if attempts > 5:
                break

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_research(run_id: int) -> dict:
    """
    Execute a full research run.

    This is the main function called by the FastAPI background task.
    It manages the entire lifecycle: loading context, calling Gemini,
    dispatching tools, saving results.

    Returns a summary dict (also stored in research_runs).
    """
    _log.info("Starting research run %d", run_id)

    # ------------------------------------------------------------------
    # 1. Load run metadata
    # ------------------------------------------------------------------
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM research_runs WHERE id = %s", (run_id,))
    run = cur.fetchone()
    conn.close()

    if not run:
        raise ValueError(f"Research run {run_id} not found")

    run = {k: _safe(v) for k, v in run.items()}

    # ------------------------------------------------------------------
    # 2. Mark as running
    # ------------------------------------------------------------------
    start_time = time.time()
    _update_run(
        run_id,
        status="running",
        started_at=datetime.now(),
        current_step="Initialising research agent...",
        progress_pct=0,
    )

    try:
        return _run_agent_loop(run_id, run, start_time)
    except Exception as exc:
        _log.exception("Research run %d failed: %s", run_id, exc)
        _update_run(
            run_id,
            status="failed",
            completed_at=datetime.now(),
            duration_seconds=int(time.time() - start_time),
            current_step=f"FAILED: {str(exc)[:200]}",
            progress_pct=0,
        )
        return {"status": "failed", "error": str(exc)}


def _run_agent_loop(run_id: int, run: dict, start_time: float) -> dict:
    """Inner loop — separated for cleaner error handling."""

    # ------------------------------------------------------------------
    # Load vocabulary
    # ------------------------------------------------------------------
    vocabulary = _load_vocabulary()
    _progress(run_id, "Building research plan...", 5)

    # ------------------------------------------------------------------
    # Build system prompt and initial message
    # ------------------------------------------------------------------
    system_prompt = _build_system_prompt(run, vocabulary)

    user_message = (
        f"Please conduct a thorough deep-dive research on **{run['company_name']}** "
        f"using the available tools. Start with internal database searches, then "
        f"search the web for recent news and labor context, then "
        f"synthesize into a dossier. When done, produce the JSON dossier."
    )

    # ------------------------------------------------------------------
    # Initialise Gemini client
    # ------------------------------------------------------------------
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY not set. Add it to .env or environment variables."
        )

    client = genai.Client(api_key=api_key)
    gemini_tools = _build_gemini_tools()

    # Build conversation history for Gemini
    # Gemini uses a list of Content objects
    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        )
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    execution_order = 0
    tools_called = 0
    final_text = ""

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------
    for turn in range(MAX_TOOL_TURNS):
        _log.info("Run %d: turn %d", run_id, turn + 1)

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=gemini_tools,
                max_output_tokens=MAX_TOKENS,
            ),
        )

        # Track token usage
        if response.usage_metadata:
            total_input_tokens += response.usage_metadata.prompt_token_count or 0
            total_output_tokens += response.usage_metadata.candidates_token_count or 0

        # Extract parts from response
        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Check for function calls
        function_calls = [p for p in parts if p.function_call]
        text_parts = [p for p in parts if p.text]

        if not function_calls:
            # No function calls — Gemini is done. Collect final text.
            final_text = "\n".join(p.text for p in text_parts if p.text)
            finish_reason = getattr(candidate, 'finish_reason', None)
            _log.info("Run %d: finished (reason=%s, text_len=%d)",
                      run_id, finish_reason, len(final_text))
            break

        # Add Gemini's response (with function calls) to conversation
        contents.append(candidate.content)

        # Execute each function call and build responses
        function_responses = []
        for part in function_calls:
            fc = part.function_call
            execution_order += 1
            tools_called += 1
            tool_name = fc.name
            tool_input = dict(fc.args) if fc.args else {}

            # Update progress
            pct = 10 + int(70 * (execution_order / max(len(_INTERNAL_TOOLS), 1)))
            step_desc = f"Searching {tool_name.replace('_', ' ').replace('search ', '')}..."
            _progress(run_id, step_desc, min(pct, 80))

            _log.info("Run %d: calling %s(%s)", run_id, tool_name,
                      json.dumps(tool_input, default=str)[:200])

            # Check cache before executing the tool
            cached = None
            if tool_name in TOOL_REGISTRY and tool_name != "google_search":
                cached = _check_cache(run.get("employer_id"), tool_name)

            t0 = time.time()
            if cached:
                # Use cached result instead of re-querying
                result = {
                    "found": True,
                    "source": f"cache:{tool_name}",
                    "summary": f"[Cached] {cached['result_summary'] or ''}",
                    "data": {},
                }
                _log.info("Run %d: cache hit for %s (employer %s)",
                          run_id, tool_name, run.get("employer_id"))
            elif tool_name == "google_search":
                # Gemini sometimes emits google_search as a function call
                # even though it's not in our declarations. Reject it so
                # Gemini focuses on the database tools instead.
                result = {
                    "found": False, "source": "google_search",
                    "summary": "Web search is not available. Focus on the database tools listed in your instructions.",
                    "data": {}, "error": "google_search is not a registered tool",
                }
            elif tool_name in TOOL_REGISTRY:
                try:
                    result = TOOL_REGISTRY[tool_name](**tool_input)
                except Exception as e:
                    result = {
                        "found": False, "source": tool_name,
                        "summary": f"Tool error: {e}",
                        "data": {}, "error": str(e),
                    }
            else:
                result = {
                    "found": False, "source": tool_name,
                    "summary": f"Unknown tool: {tool_name}",
                    "data": {}, "error": f"Unknown tool: {tool_name}",
                }
            latency_ms = int((time.time() - t0) * 1000)

            # Log to database (mark cached actions)
            log_tool_name = f"{tool_name} (cached)" if cached else tool_name
            _log_action(
                run_id, log_tool_name, tool_input, execution_order,
                result, latency_ms,
                company_context={
                    "company_name": run["company_name"],
                    "employer_id": run.get("employer_id"),
                },
            )

            # Build function response for Gemini
            # Gemini expects the response as a dict (not a JSON string)
            function_responses.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response=result,
                )
            )

        # Add function responses as a user turn
        contents.append(
            types.Content(
                role="user",
                parts=function_responses,
            )
        )

    else:
        # Exhausted turns
        _log.warning("Run %d: exhausted %d turns", run_id, MAX_TOOL_TURNS)
        # Collect whatever text we got in the last response
        if not final_text:
            final_text = "\n".join(p.text for p in parts if p.text)

    # ------------------------------------------------------------------
    # Phase 2: Web search via Google Search grounding
    # ------------------------------------------------------------------
    # Gemini cannot combine function_declarations and google_search in
    # one request, so we run a separate call with only Google Search
    # grounding enabled to enrich the dossier with current web context.
    _progress(run_id, "Searching the web for current context...", 82)

    # Build a summary of what Phase 1 found / missed for targeted web search
    db_summaries = []
    db_gaps = []   # tool names that returned no data
    conn_summary = _conn()
    cur_summary = conn_summary.cursor()
    cur_summary.execute(
        """SELECT tool_name, data_found, result_summary
           FROM research_actions
           WHERE run_id = %s AND tool_name NOT LIKE '%%google_search%%'
             AND tool_name NOT LIKE '%%(cached)%%'
           ORDER BY execution_order""",
        (run_id,),
    )
    for row in cur_summary.fetchall():
        tn = row["tool_name"]
        if row["data_found"]:
            db_summaries.append(f"- {tn}: {(row['result_summary'] or '')[:150]}")
        else:
            db_gaps.append(tn)
    conn_summary.close()

    db_context = "\n".join(db_summaries) if db_summaries else "(no database results)"
    gap_text = ", ".join(db_gaps) if db_gaps else "none"

    company_name = run["company_name"]
    company_type = run.get("company_type") or "unknown"
    industry_naics = run.get("industry_naics") or ""
    company_state = run.get("company_state") or ""

    # Build gap-aware query list
    targeted_queries, gap_types_queried = _build_web_search_queries(
        company_name, company_type, company_state, db_gaps
    )
    query_list = "\n".join(f"- {q}" for q in targeted_queries)
    _log.info("Run %d: built %d targeted web queries from %d DB gaps (%s)",
              run_id, len(targeted_queries), len(db_gaps), ", ".join(db_gaps))

    try:
        web_prompt = f"""You are a labor-relations research agent. You already queried internal government databases for **{company_name}** and found the following:

## What our databases found:
{db_context}

## Gaps (databases with NO results):
{gap_text}

## Company context:
- Type: {company_type}
- NAICS: {industry_naics}
- State: {company_state}

## Your task:
Search the web to fill gaps and add current context. Use these targeted searches (generated from our database gaps):

{query_list}

Search for EACH of these individually. Do not stop after one search. Try at least 5-6 different searches.

Also check for:
1. **Recent news** (2024-2026): layoffs, expansions, lawsuits, mergers, acquisitions, executive changes
2. **Union organizing**: active campaigns, election results, strikes, work stoppages
3. **Worker issues**: wage theft complaints, safety incidents, employee lawsuits
4. **NLRB activity**: recent filings, unfair labor practice charges, board decisions
5. **Company labor stance**: CEO/leadership statements about unions

Return ALL findings as a JSON code block. Include EVERY fact you find, even if minor:

```json
{{
  "recent_news": [
    "Headline or summary with specific details (Source Name, YYYY-MM-DD)"
  ],
  "organizing_activity": [
    "Description of organizing, election, strike, or campaign (Source Name, YYYY-MM-DD)"
  ],
  "worker_issues": [
    "Wage theft, safety, lawsuits, complaints (Source Name, YYYY-MM-DD)"
  ],
  "nlrb_activity": [
    "Filings, charges, decisions, rulings (Source Name, YYYY-MM-DD)"
  ],
  "company_labor_stance": [
    "Leadership quotes, anti-union actions, policy statements (Source Name, YYYY-MM-DD)"
  ],
  "company_context": "2-3 paragraph summary of what web sources reveal about this company's labor relations landscape, recent trajectory, and organizing potential",
  "sources": [
    {{"title": "Article or page title", "url": "https://...", "date": "YYYY-MM-DD"}}
  ]
}}
```

Be thorough. An empty section means you did not search hard enough. Every company has SOME news. If the company is small or obscure, search for industry-level labor news in their sector."""

        web_response = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=web_prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=_build_google_search_tool(),
                max_output_tokens=16384,
            ),
        )

        # Track token usage from web search phase
        if web_response.usage_metadata:
            total_input_tokens += web_response.usage_metadata.prompt_token_count or 0
            total_output_tokens += web_response.usage_metadata.candidates_token_count or 0

        web_candidate = web_response.candidates[0] if web_response.candidates else None
        web_parts = (web_candidate.content.parts or []) if web_candidate and web_candidate.content else []
        web_text = "\n".join(
            p.text for p in web_parts if p.text
        )

        # Log grounding metadata
        grounding_meta = getattr(web_candidate, 'grounding_metadata', None) if web_candidate else None
        search_queries_used = []
        if grounding_meta:
            search_queries_used = getattr(grounding_meta, 'web_search_queries', []) or []
            if search_queries_used:
                _log.info("Run %d: Google Search queries: %s",
                          run_id, search_queries_used[:5])

        execution_order += 1
        tools_called += 1
        _log_action(
            run_id, "google_search",
            {"queries": search_queries_used[:10]},
            execution_order,
            {"found": bool(web_text.strip()),
             "source": "google_search",
             "summary": f"Web search: {', '.join(search_queries_used[:3])}" if search_queries_used
                        else "Web search grounding (queries not exposed)",
             "data": {}},
            0,
        )

        # Save original dossier text before web merge.
        original_final_text = final_text

        if web_text.strip():
            _log.info("Run %d: web search returned %d chars", run_id, len(web_text))
        else:
            _log.info("Run %d: web search returned no text", run_id)

    except Exception as web_exc:
        _log.warning("Run %d: web search phase failed (non-fatal): %s", run_id, web_exc)
        web_text = ""
        original_final_text = final_text

    # ------------------------------------------------------------------
    # Phase 3: Merge web findings into the dossier
    # ------------------------------------------------------------------
    # Parse web findings JSON directly from Phase 2 output, then apply
    # to the dossier programmatically. No extra LLM call needed.
    if web_text.strip():
        _progress(run_id, "Merging web findings into dossier...", 84)
        try:
            # Extract JSON from web search response
            web_data = None
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", web_text, re.DOTALL)
            if m:
                raw = m.group(1).strip()
                try:
                    web_data = json.loads(raw)
                except json.JSONDecodeError:
                    try:
                        web_data = json.loads(_fix_json_escapes(raw))
                    except json.JSONDecodeError as e:
                        _log.warning("Run %d: web JSON parse error in code block: %s", run_id, e)
            if not web_data:
                # Try finding raw JSON object
                for i, ch in enumerate(web_text):
                    if ch == '{':
                        try:
                            web_data = json.loads(web_text[i:])
                            break
                        except json.JSONDecodeError:
                            try:
                                web_data = json.loads(_fix_json_escapes(web_text[i:]))
                                break
                            except json.JSONDecodeError:
                                continue

            if web_data and isinstance(web_data, dict):
                # Handle nested {"web_findings": {...}} or flat format
                if "web_findings" in web_data:
                    web_data = web_data["web_findings"]

                # Parse the original dossier
                original_dossier = _extract_dossier_json(original_final_text)
                if original_dossier and "dossier" in original_dossier:
                    dossier_body = original_dossier["dossier"]
                    assessment = dossier_body.get("assessment", {}) or {}

                    # --- Build assessment additions from web data ---
                    web_context = web_data.get("company_context", "")
                    if web_context:
                        existing = assessment.get("organizing_summary") or ""
                        if existing:
                            assessment["organizing_summary"] = (
                                existing + "\n\n**Web sources add:** " + web_context
                            )
                        else:
                            assessment["organizing_summary"] = web_context

                    # Add organizing activity as campaign strengths/intel
                    organizing = web_data.get("organizing_activity", [])
                    if organizing:
                        strengths = assessment.get("campaign_strengths", []) or []
                        for item in organizing:
                            if isinstance(item, str) and item.strip():
                                strengths.append(f"[Web] {item}")
                        assessment["campaign_strengths"] = strengths

                    # Add worker issues as campaign context
                    worker_issues = web_data.get("worker_issues", [])
                    if worker_issues:
                        strengths = assessment.get("campaign_strengths", []) or []
                        for item in worker_issues:
                            if isinstance(item, str) and item.strip():
                                strengths.append(f"[Web] Worker issue: {item}")
                        assessment["campaign_strengths"] = strengths

                    # Add company labor stance as challenges
                    labor_stance = web_data.get("company_labor_stance", [])
                    if labor_stance:
                        challenges = assessment.get("campaign_challenges", []) or []
                        for item in labor_stance:
                            if isinstance(item, str) and item.strip():
                                challenges.append(f"[Web] {item}")
                        assessment["campaign_challenges"] = challenges

                    # Add NLRB activity to labor section
                    nlrb_web = web_data.get("nlrb_activity", [])
                    if nlrb_web:
                        labor = dossier_body.get("labor", {}) or {}
                        existing_nlrb = labor.get("recent_nlrb_web", [])
                        for item in nlrb_web:
                            if isinstance(item, str) and item.strip():
                                existing_nlrb.append(item)
                        if existing_nlrb:
                            labor["recent_nlrb_web"] = existing_nlrb
                            dossier_body["labor"] = labor

                    dossier_body["assessment"] = assessment

                    # --- Add web sources ---
                    sources_sec = dossier_body.get("sources", {}) or {}
                    web_sources_list = web_data.get("sources", [])
                    # Also handle old format "sources_consulted"
                    if not web_sources_list:
                        web_sources_list = web_data.get("sources_consulted", [])
                    for ws in web_sources_list:
                        if isinstance(ws, dict):
                            summary = f"{ws.get('title', 'Web')} ({ws.get('url', '')}, {ws.get('date', '')})"
                        elif isinstance(ws, str):
                            summary = ws
                        else:
                            continue
                        sources_sec.setdefault("source_list", []).append(
                            {"tool": "web_search", "summary": summary}
                        )
                    dossier_body["sources"] = sources_sec

                    # --- Add web facts ---
                    recent_news = web_data.get("recent_news", [])
                    for item in recent_news:
                        if isinstance(item, str) and item.strip():
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "workplace",
                                "attribute_name": "recent_labor_news",
                                "attribute_value": item,
                                "source_type": "web",
                                "source_name": "google_search",
                                "confidence": 0.7,
                            })
                    # Add organizing activity as facts too
                    for item in organizing:
                        if isinstance(item, str) and item.strip():
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "labor",
                                "attribute_name": "recent_organizing",
                                "attribute_value": item,
                                "source_type": "web",
                                "source_name": "google_search",
                                "confidence": 0.7,
                            })

                    # Re-serialize the patched dossier as the final text
                    final_text = "```json\n" + json.dumps(original_dossier, indent=2, default=str) + "\n```"
                    web_source_count = len(web_sources_list)
                    _log.info("Run %d: merged web findings (%d sources, %d news items, %d organizing, %d issues)",
                              run_id, web_source_count, len(recent_news), len(organizing), len(worker_issues))
                else:
                    _log.warning("Run %d: could not parse original dossier for patching", run_id)
            else:
                # Fallback: JSON parse failed but we have raw web text.
                # Append a truncated summary to the assessment.
                _log.warning("Run %d: web JSON parse failed, using raw text fallback (%d chars)",
                             run_id, len(web_text))
                original_dossier = _extract_dossier_json(original_final_text)
                if original_dossier and "dossier" in original_dossier:
                    dossier_body = original_dossier["dossier"]
                    assessment = dossier_body.get("assessment", {}) or {}
                    # Truncate raw web text to a reasonable size
                    raw_summary = web_text[:4000].strip()
                    existing = assessment.get("organizing_summary") or ""
                    if existing:
                        assessment["organizing_summary"] = (
                            existing + "\n\n**Additional web context:** " + raw_summary
                        )
                    else:
                        assessment["organizing_summary"] = raw_summary
                    dossier_body["assessment"] = assessment
                    final_text = "```json\n" + json.dumps(original_dossier, indent=2, default=str) + "\n```"
                    _log.info("Run %d: appended raw web summary fallback (%d chars)", run_id, len(raw_summary))

        except Exception as merge_exc:
            _log.warning("Run %d: web merge phase failed (non-fatal): %s", run_id, merge_exc)
            final_text = original_final_text  # restore clean dossier on failure

    # ------------------------------------------------------------------
    # Track query effectiveness (Phase 5.2 learning)
    # ------------------------------------------------------------------
    if gap_types_queried:
        try:
            # Count which web sections produced facts
            web_facts_by_gap = {}
            if web_text.strip():
                _web_data = None
                _m = re.search(r"```(?:json)?\s*\n?(.*?)```", web_text, re.DOTALL)
                if _m:
                    try:
                        _web_data = json.loads(_fix_json_escapes(_m.group(1).strip()))
                    except json.JSONDecodeError:
                        pass
                if _web_data and isinstance(_web_data, dict):
                    # Map web JSON sections to gap types
                    _section_gap_map = {
                        "recent_news": "recent_news",
                        "organizing_activity": "nlrb_activity",
                        "worker_issues": "worker_conditions",
                        "nlrb_activity": "nlrb_activity",
                        "company_labor_stance": "labor_stance",
                        "company_context": "recent_news",
                    }
                    for sec_key, gap_key in _section_gap_map.items():
                        val = _web_data.get(sec_key, [])
                        if isinstance(val, list) and val:
                            web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + len(val)
                        elif isinstance(val, str) and val.strip():
                            web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + 1
            _update_query_effectiveness(gap_types_queried, web_facts_by_gap, company_type)
        except Exception as qe_exc:
            _log.warning("Run %d: query effectiveness tracking failed (non-fatal): %s", run_id, qe_exc)

    # ------------------------------------------------------------------
    # Parse dossier from final response
    # ------------------------------------------------------------------
    _progress(run_id, "Parsing dossier...", 85)

    dossier_data = _extract_dossier_json(final_text)

    if not dossier_data:
        _log.warning("Run %d: could not parse dossier JSON (text_len=%d, first 200=%s)",
                     run_id, len(final_text), repr(final_text[:200]))
        dossier_data = {
            "dossier": {"raw_text": final_text},
            "facts": [],
            "parse_error": "Could not extract structured JSON from agent response",
        }

    # ------------------------------------------------------------------
    # Save facts
    # ------------------------------------------------------------------
    _progress(run_id, "Saving facts...", 90)

    facts_list = dossier_data.get("facts", [])

    # Fallback: if dossier parse failed (or produced no facts), harvest
    # basic facts from the already-persisted research_actions.  This
    # ensures 990 data and all other tool results survive even when
    # Gemini produces unparseable JSON.
    if not facts_list and dossier_data.get("parse_error"):
        _log.info("Run %d: dossier parse failed — extracting fallback facts from research_actions", run_id)
        facts_list = _extract_fallback_facts(run_id)

    facts_saved = _save_facts(
        run_id,
        run.get("employer_id"),
        facts_list,
        vocabulary,
    )

    # Count sections with data
    dossier_body = dossier_data.get("dossier", {})
    sections_filled = sum(
        1 for sec in _DOSSIER_SECTIONS
        if isinstance(dossier_body, dict) and dossier_body.get(sec)
        and isinstance(dossier_body[sec], dict)
        and any(v for v in dossier_body[sec].values() if v is not None)
    )

    # ------------------------------------------------------------------
    # Calculate cost
    # ------------------------------------------------------------------
    total_tokens = total_input_tokens + total_output_tokens
    cost_cents = int(
        (total_input_tokens / 1000 * _INPUT_COST_PER_1K)
        + (total_output_tokens / 1000 * _OUTPUT_COST_PER_1K)
    )

    # ------------------------------------------------------------------
    # Finalise the run
    # ------------------------------------------------------------------
    duration = int(time.time() - start_time)

    _update_run(
        run_id,
        status="completed",
        completed_at=datetime.now(),
        duration_seconds=duration,
        total_tools_called=tools_called,
        total_facts_found=facts_saved,
        sections_filled=sections_filled,
        dossier_json=json.dumps(dossier_data, default=str),
        total_tokens_used=total_tokens,
        total_cost_cents=cost_cents,
        current_step="Research complete",
        progress_pct=100,
    )

    summary = {
        "status": "completed",
        "run_id": run_id,
        "duration_seconds": duration,
        "tools_called": tools_called,
        "facts_saved": facts_saved,
        "sections_filled": sections_filled,
        "tokens_used": total_tokens,
        "cost_cents": cost_cents,
    }
    _log.info("Run %d completed: %s", run_id, json.dumps(summary))
    return summary


# ---------------------------------------------------------------------------
# CLI entry point for testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run a research agent deep dive")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=int, help="Existing research_runs.id to resume/execute")
    group.add_argument("--company", type=str, help="Company name (creates a new run)")
    parser.add_argument("--employer-id", type=str, help="F7 employer_id (optional)")
    parser.add_argument("--naics", type=str, help="NAICS code (optional)")
    parser.add_argument("--state", type=str, help="State abbreviation (optional)")
    parser.add_argument("--type", type=str, help="Company type: public/private/nonprofit/government")
    args = parser.parse_args()

    if args.company:
        # Create a new run
        conn = _conn()
        cur = conn.cursor()
        size_bucket = "medium"
        if args.employer_id:
            cur.execute("""
                SELECT latest_unit_size FROM f7_employers_deduped
                WHERE employer_id = %s
            """, (args.employer_id,))
            r = cur.fetchone()
            if r and r["latest_unit_size"]:
                sz = r["latest_unit_size"]
                size_bucket = "small" if sz < 100 else ("medium" if sz < 1000 else "large")

        cur.execute("""
            INSERT INTO research_runs
                (company_name, employer_id, industry_naics, company_type,
                 company_state, employee_size_bucket, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
        """, (
            args.company,
            args.employer_id,
            args.naics,
            args.type,
            args.state,
            size_bucket,
        ))
        run_id = cur.fetchone()["id"]
        conn.commit()
        conn.close()
        print(f"Created research run {run_id}")
    else:
        run_id = args.run_id

    result = run_research(run_id)
    print(json.dumps(result, indent=2, default=str))
