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
    "search_sec_proxy", "search_job_postings", "get_workforce_demographics",
    "get_industry_profile", "get_similar_employers",
    "scrape_employer_website", "google_search",
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


def _extract_financial_from_text(text: str) -> dict:
    """Regex-extract employee count and revenue from raw web text.

    Returns dict with keys 'employee_count', 'revenue' (strings or None).
    Used as a fallback when Gemini doesn't produce a structured financial_data dict.
    """
    result = {}

    # Employee count patterns: "150,000 employees", "~12000 workers"
    emp_pattern = re.compile(
        r'(?:approximately|about|around|~|over|nearly|more than|has)?\s*'
        r'(\d[\d,]+)\s*(?:employees|workers|staff|associates|team members)',
        re.IGNORECASE,
    )
    emp_matches = emp_pattern.findall(text)
    if emp_matches:
        # Take the largest number found (most likely to be total headcount)
        counts = []
        for m in emp_matches:
            try:
                counts.append(int(m.replace(",", "")))
            except ValueError:
                pass
        if counts:
            result["employee_count"] = f"{max(counts):,} employees (web source, {date.today().year})"

    # Revenue patterns: "$1.2 billion", "$500 million", "$2.5B"
    rev_pattern = re.compile(
        r'\$\s*([\d.]+)\s*(billion|million|trillion|B|M|T)\b',
        re.IGNORECASE,
    )
    rev_matches = rev_pattern.findall(text)
    if rev_matches:
        best_val = 0
        best_str = ""
        for num_str, unit in rev_matches:
            try:
                num = float(num_str)
                unit_l = unit.lower()
                if unit_l in ("billion", "b"):
                    val = num * 1e9
                elif unit_l in ("million", "m"):
                    val = num * 1e6
                elif unit_l in ("trillion", "t"):
                    val = num * 1e12
                else:
                    val = num
                if val > best_val:
                    best_val = val
                    best_str = f"${num_str} {unit}"
            except ValueError:
                pass
        if best_str:
            result["revenue"] = f"{best_str} (web source, {date.today().year})"

    # Website URL pattern
    url_pattern = re.compile(
        r'(?:official\s+(?:website|site)|homepage|website)\s*(?:is|at|:)?\s*'
        r'(https?://[^\s<>"]+)',
        re.IGNORECASE,
    )
    url_match = url_pattern.search(text)
    if url_match:
        result["website_url"] = url_match.group(1).rstrip(".,;)")

    return result


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
        '"{company}" number of employees {year}',
        '"{company}" employees site:linkedin.com',
        '"{company}" workforce size headcount {state}',
    ],
    "revenue": [
        '"{company}" annual revenue {year}',
        '"{company}" revenue SEC 10-K billion million',
        '"{company}" revenue financial results {state} {year}',
    ],
    "website_url": [
        '"{company}" official site',
        '"{company}" homepage {state}',
    ],
    # When OSHA misses
    "osha_violations": [
        '"{company}" OSHA violations safety citations {state}',
        '"{company}" OSHA inspection fine {year}',
        '"{company}" workplace safety incident {state} {year}',
    ],
    # When NLRB misses
    "nlrb_activity": [
        '"{company}" NLRB union election filing',
        '"{company}" unfair labor practice charge',
        '"{company}" union organizing campaign {year}',
    ],
    # When WHD misses
    "whd_violations": [
        '"{company}" wage theft Department of Labor {state}',
        '"{company}" FLSA violation back wages {year}',
        '"{company}" Fair Labor Standards Act {state} {year}',
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
                               year: str = None) -> list[str]:
    """Build targeted search queries based on which DB tools missed.

    Args:
        company_name: The employer name
        company_type: public/private/nonprofit/government
        company_state: 2-letter state code
        db_gaps: list of tool_names that returned no data
        year: current year for recency queries (defaults to current year)

    Returns:
        List of filled query strings, capped at 15.
    """
    if year is None:
        year = str(datetime.now().year)
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
# Strategy Hints
# ---------------------------------------------------------------------------

def _get_strategy_hints(naics: str, company_type: str, size_bucket: str) -> str:
    """Query research_strategies for tool hit rates matching this employer's profile.

    Returns a short text block appended to the system prompt, or empty string.
    """
    if not naics or naics == "unknown":
        return ""
    naics_2 = naics[:2]
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT tool_name,
                   ROUND(hit_rate * 100)::int AS hit_pct,
                   times_tried
            FROM research_strategies
            WHERE industry_naics_2digit = %s
              AND (company_type = %s OR company_type IS NULL)
              AND (company_size_bucket = %s OR company_size_bucket IS NULL)
              AND times_tried >= 3
            ORDER BY hit_rate DESC
            LIMIT 10
        """, (naics_2, company_type, size_bucket))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        lines = [f"\n## Strategy Hints (from {len(rows)} past runs in NAICS {naics_2}):"]
        for r in rows:
            lines.append(f"- {r['tool_name']}: {r['hit_pct']}% hit rate ({r['times_tried']} runs)")
        return "\n".join(lines) + "\n"
    except Exception as e:
        _log.debug("Strategy hints lookup failed (non-fatal): %s", e)
        return ""


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

    prompt = f"""You are a labor-relations research agent. Your job is to compile a comprehensive organizing dossier on a single employer by querying internal databases.

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

3. **Get additional enrichment** (these tools fill critical gaps):
   - SEC proxy executive pay (search_sec_proxy) -- ONLY for public companies. Pass any CIK or ticker you found from search_sec results. Returns top executive compensation.
   - Job postings estimate (search_job_postings) -- ALWAYS call this. Returns active job count and sample titles/pay. High turnover signal if count > 100.
   - Workforce demographics (get_workforce_demographics) -- Call if NAICS is known. Returns industry demographic baselines (race, gender, age). NOTE: This data is industry-level, not company-specific. Always label it as "INDUSTRY BASELINE" in the dossier.

4. **Scrape employer website** (scrape_employer_website) -- if search_mergent returned a website URL, pass it here. Otherwise the tool will look it up. Returns homepage, about, careers, and news text.

5. **Synthesize** your findings into the dossier.

IMPORTANT: Do NOT call `google_search` directly -- web search is handled separately after your database queries. But DO call `search_sec_proxy`, `search_job_postings`, and `get_workforce_demographics` as listed in step 3 above.

Always pass the company_name parameter. If the employer_id is known (not "unknown"), pass it too for more precise matching.
If the NAICS is known, pass it to get_industry_profile and get_similar_employers.
If the state is known, pass it where accepted.

If a tool returns no results for a long company name, try again with a well-known abbreviation or shorter name (e.g., "University of Pittsburgh Medical Center" -> try "UPMC", "United Parcel Service" -> try "UPS"). The database tools now handle acronym matching automatically, but Gemini-chosen alternate names can help too.

If search_990 returns financial data (revenue, assets, employees), include it prominently in the "financial" section. Nonprofit 990 data is critical intelligence -- never omit it from the dossier.

You MAY skip tools that clearly don't apply (e.g., skip search_sec for nonprofits, skip search_990 for public companies). Briefly note each skip and why.

## Dossier Fact Vocabulary

When you compile the final dossier, use ONLY these attribute names:
{vocab_text}

## CRITICAL FIELD RULES
- You MUST include ALL sections in your JSON output, even if empty (use empty objects {{}}).
- Within each section, include ALL vocabulary fields. Use null for fields with no data. Do NOT omit fields.
- **employee_count** and **revenue** belong in the **financial** section, NOT identity.
- **pay_ranges** belong in the **workforce** section (from BLS wage data).
- **recent_labor_news** belongs in the **workplace** section.
- **turnover_signals** belongs in the **workforce** section.
- Do NOT invent non-vocabulary field names (e.g., no "employee_count_web", "revenue_web", "safety_violations_web").
- For list-type fields (e.g., osha_violation_details, whd_violation_details), use JSON arrays.

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
      "as_of_date": "YYYY-MM-DD or null",
      "contradicts_fact_attribute": "attribute_name_it_conflicts_with or null"
    }}
  ],
  "skipped_tools": [
    {{ "tool": "...", "reason": "..." }}
  ]
}}
```

For the **assessment** section, provide factual analysis:
- `data_summary`: 2-3 paragraph factual summary of what the data reveals. State what was found, patterns, and what is notable.
- `organizing_summary`: Key organizing intelligence synthesized from all sources.
- `campaign_strengths`: List of factors favorable for organizing (from database + web). Aim for 3+ items.
- `campaign_challenges`: List of obstacles to organizing (from database + web). Aim for 3+ items.
- `web_intelligence`: Key findings from web search beyond database records. Include dates and sources.
- `source_contradictions`: Contradictions between data sources (e.g., DB says no NLRB activity but web reports ongoing campaigns). IMPORTANT: If any database tool returned 0 results but web/news sources show activity, you MUST note this here.
- `data_gaps`: Critical information missing or unverifiable.
- `recommended_approach`: A 2-3 sentence factual synthesis of organizing viability based on the data gathered. Ground it in specific facts from the dossier. Example: "With 120 ULP charges, existing Teamsters contracts at 3 facilities, and $156M in federal obligations, this employer has significant organizing pressure points. The high job posting volume (5,000+) suggests turnover that could fuel organizing interest." Do NOT leave this null.
- `financial_trend`: One of "growing", "stable", "declining", or "unknown" followed by 1-sentence evidence (e.g., "growing - Revenue increased 15% YoY per 2025 10-K filing"). Derive from SEC filings, web news, or financial data.

Do NOT include: similar_organized. Set that to null.

For the **sources** section:
- `section_confidence`: object mapping each section to "high"/"medium"/"low"
- `data_gaps`: list of what was NOT found
- `source_list`: list of every source checked

Make sure every fact in the `facts` array uses an `attribute_name` from the vocabulary above. Use `attribute_value` for simple text/number values and `attribute_value_json` for complex objects (lists, dicts).

Be thorough but efficient. Do not call the same tool twice with the same parameters."""

    # Append strategy hints if available
    hints = _get_strategy_hints(str(naics), str(company_type), str(size_bucket))
    if hints:
        return prompt + hints
    return prompt


def _patch_dossier_financials(dossier_data: dict, web_text: str = "") -> int:
    """Scan narrative sections for missing financial data (Issue #1).

    If employee_count or revenue are missing in the structured dossier,
    we scan data_summary, web_intelligence, and organizing_summary for
    patterns, then update the dossier and facts array.
    """
    if not dossier_data or "dossier" not in dossier_data:
        return 0

    body = dossier_data["dossier"]
    financial = body.get("financial", {}) or {}
    assessment = body.get("assessment", {}) or {}

    # Gather all narrative text
    narratives = [
        assessment.get("data_summary") or "",
        assessment.get("web_intelligence") or "",
        assessment.get("organizing_summary") or "",
        web_text or "",
    ]
    combined_text = "\n".join(narratives)
    if not combined_text.strip():
        return 0

    # Extract patterns
    extracted = _extract_financial_from_text(combined_text)
    patched = 0

    # Map extracted keys to vocab attribute names
    _MAP = {
        "employee_count": "employee_count",
        "revenue": "revenue",
        "website_url": "website_url",
    }

    for ext_key, attr_name in _MAP.items():
        val = extracted.get(ext_key)
        if not val:
            continue

        # Check if already present in dossier
        sec = "identity" if ext_key == "website_url" else "financial"
        target_sec = body.get(sec, {}) or {}
        if not target_sec.get(attr_name):
            target_sec[attr_name] = val
            body[sec] = target_sec
            patched += 1

            # Also add to facts array if missing
            facts = dossier_data.setdefault("facts", [])
            if not any(f.get("attribute_name") == attr_name for f in facts):
                facts.append({
                    "dossier_section": sec,
                    "attribute_name": attr_name,
                    "attribute_value": val,
                    "source_type": "web_search",
                    "source_name": "regex_extraction",
                    "confidence": 0.6,
                    "as_of_date": date.today().isoformat(),
                })

    return patched


def _fill_dossier_gaps(
    run_id: int,
    dossier_data: dict,
    web_text: str,
    vocabulary: dict
) -> int:
    """Perform a second LLM pass to fill remaining null fields (Issue #13).

    Scans the raw web text specifically for fields that are still null
    after the first pass and merging.
    """
    if not web_text or not dossier_data or "dossier" not in dossier_data:
        return 0

    body = dossier_data["dossier"]
    missing = []
    
    # Identify null fields (excluding assessment/sources)
    for sec_name in ["identity", "financial", "workforce", "labor", "workplace"]:
        sec_dict = body.get(sec_name, {})
        for key, val in sec_dict.items():
            if val is None or val == "" or val == []:
                missing.append(f"{sec_name}.{key}")

    if not missing:
        return 0

    _log.info("Run %d: Second pass hunting for %d missing fields", run_id, len(missing))

    # Build prompt for gap filling
    gap_list = "\n".join(f"- {m}" for m in missing)
    prompt = f"""You are a data extraction specialist. We have a research dossier with missing information.
Your task is to scan the provided raw web text and extract values ONLY for these specific missing fields:

{gap_list}

## Raw Web Text:
{web_text[:30000]}

## Instructions:
1. Return a JSON object where keys are the 'section.field' names and values are the extracted data.
2. If the data is truly not present in the text, omit the key or use null.
3. Use a concise string format for values.
4. Do NOT re-extract information that is NOT on the missing list.
5. Provide a 'source_name' for each find.

Example:
{{
  "identity.year_founded": "1994 (Source: Wikipedia)",
  "workforce.job_posting_count": "45 open positions (Source: Indeed)"
}}
"""

    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )],
            config=types.GenerateContentConfig(
                max_output_tokens=4096,
                temperature=0.0,
            ),
        )
        
        text = response.text
        # Extract JSON block
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        found_data = None
        if m:
            try:
                found_data = json.loads(_fix_json_escapes(m.group(1).strip()))
            except: pass
        if not found_data:
            try:
                found_data = json.loads(_fix_json_escapes(text.strip()))
            except: pass

        if not found_data or not isinstance(found_data, dict):
            return 0

        patched = 0
        facts = dossier_data.setdefault("facts", [])
        
        for gap_key, val in found_data.items():
            if not val or '.' not in gap_key:
                continue
            
            sec, attr = gap_key.split('.', 1)
            if attr not in vocabulary:
                continue
            
            # Update dossier body
            target_sec = body.get(sec, {})
            if not target_sec.get(attr):
                target_sec[attr] = val
                body[sec] = target_sec
                patched += 1
                
                # Update facts array
                facts.append({
                    "dossier_section": sec,
                    "attribute_name": attr,
                    "attribute_value": val,
                    "source_type": "web_search",
                    "source_name": "second_pass_gap_filler",
                    "confidence": 0.55,
                    "as_of_date": date.today().isoformat(),
                })
        
        return patched

    except Exception as e:
        _log.warning("Run %d: Second-pass gap filler failed: %s", run_id, e)
        return 0


def _resolve_contradictions(dossier_data: dict) -> int:
    """Detect DB-zero vs web-nonzero contradictions and populate source_contradictions.

    Scans the dossier for cases where a database tool returned 0 (e.g.,
    osha_violation_count=0) but web/assessment text mentions violations.
    Writes findings to assessment.source_contradictions.

    Returns number of contradictions found.
    """
    if not dossier_data or "dossier" not in dossier_data:
        return 0

    body = dossier_data["dossier"]
    assessment = body.get("assessment", {}) or {}
    workplace = body.get("workplace", {}) or {}
    labor = body.get("labor", {}) or {}

    # Collect all narrative text for searching
    narratives = [
        assessment.get("data_summary") or "",
        assessment.get("organizing_summary") or "",
        assessment.get("web_intelligence") or "",
    ]
    # Also check web-sourced list items
    for items in [
        assessment.get("campaign_strengths", []) or [],
        assessment.get("campaign_challenges", []) or [],
        workplace.get("recent_labor_news", []) or [],
        workplace.get("osha_violation_details", []) or [],
        workplace.get("whd_violation_details", []) or [],
        labor.get("recent_nlrb_web", []) or [],
    ]:
        if isinstance(items, list):
            narratives.extend(str(i) for i in items if i)
        elif isinstance(items, str):
            narratives.append(items)

    combined_text = " ".join(narratives).lower()
    if not combined_text.strip():
        return 0

    contradictions = []

    # Check OSHA: DB says 0 but web mentions violations/fines/citations
    osha_count = workplace.get("osha_violation_count")
    if _is_zero_or_none(osha_count):
        osha_keywords = re.compile(
            r'\b(osha\s+(?:violation|citation|fine|penalt)|'
            r'safety\s+violation|workplace\s+(?:injury|death|fatality)|'
            r'osha\s+(?:cited|fined))\b', re.IGNORECASE,
        )
        if osha_keywords.search(combined_text):
            contradictions.append(
                f"Database matched 0 OSHA violations under employer name -- "
                f"web sources report OSHA citations/fines. "
                f"Likely caused by entity name mismatch (subsidiary names, DBA names)."
            )
            # Annotate the DB value
            if osha_count is not None:
                workplace["osha_violation_count"] = f"{osha_count} (DB name match -- see source_contradictions)"

    # Check NLRB: DB says 0 elections/ULPs but web mentions organizing
    nlrb_election = labor.get("nlrb_election_count")
    nlrb_ulp = labor.get("nlrb_ulp_count")
    if _is_zero_or_none(nlrb_election) and _is_zero_or_none(nlrb_ulp):
        nlrb_keywords = re.compile(
            r'\b(nlrb|unfair\s+labor\s+practice|ulp\s+charge|'
            r'union\s+election|organizing\s+(?:campaign|drive|effort)|'
            r'filed\s+(?:a\s+)?petition|bargaining\s+unit)\b', re.IGNORECASE,
        )
        if nlrb_keywords.search(combined_text):
            contradictions.append(
                f"Database matched 0 NLRB elections/ULP charges under employer name -- "
                f"web sources report union organizing activity or NLRB filings. "
                f"Likely caused by entity name mismatch or recent filings not yet in database."
            )
            if nlrb_election is not None:
                labor["nlrb_election_count"] = f"{nlrb_election} (DB name match -- see source_contradictions)"
            if nlrb_ulp is not None:
                labor["nlrb_ulp_count"] = f"{nlrb_ulp} (DB name match -- see source_contradictions)"

    # Check WHD: DB says 0 but web mentions wage theft
    whd_count = workplace.get("whd_case_count")
    if _is_zero_or_none(whd_count):
        whd_keywords = re.compile(
            r'\b(wage\s+theft|back\s+wages|flsa\s+violation|'
            r'department\s+of\s+labor\s+(?:fine|investigation)|'
            r'unpaid\s+(?:wages|overtime))\b', re.IGNORECASE,
        )
        if whd_keywords.search(combined_text):
            contradictions.append(
                f"Database matched 0 WHD cases under employer name -- "
                f"web sources report wage violations or DOL investigations. "
                f"Likely caused by entity name mismatch or settlement agreements."
            )
            if whd_count is not None:
                workplace["whd_case_count"] = f"{whd_count} (DB name match -- see source_contradictions)"

    # Write contradictions to assessment
    if contradictions:
        assessment["source_contradictions"] = contradictions
        body["workplace"] = workplace
        body["labor"] = labor
        body["assessment"] = assessment
        _log.info("Contradiction resolver found %d DB-vs-web mismatches", len(contradictions))

    return len(contradictions)


def _is_zero_or_none(val) -> bool:
    """Check if a value represents zero or no data."""
    if val is None:
        return True
    if isinstance(val, (int, float)) and val == 0:
        return True
    if isinstance(val, str):
        stripped = val.strip()
        if stripped in ("0", "0.0", "", "null", "None", "N/A"):
            return True
    return False


def _extract_financial_trend(dossier_data: dict, web_text: str = "") -> bool:
    """Extract financial_trend from web text and dossier narratives.

    Populates assessment.financial_trend with "growing/stable/declining/unknown"
    plus 1-sentence evidence.

    Returns True if financial_trend was populated.
    """
    if not dossier_data or "dossier" not in dossier_data:
        return False

    body = dossier_data["dossier"]
    assessment = body.get("assessment", {}) or {}

    # Skip if already populated
    if assessment.get("financial_trend"):
        return False

    # Gather text to scan
    texts = [
        assessment.get("data_summary") or "",
        assessment.get("web_intelligence") or "",
        assessment.get("organizing_summary") or "",
        web_text or "",
    ]
    combined = " ".join(texts)
    if not combined.strip():
        return False

    # Growth keywords
    _GROWING = re.compile(
        r'\b(revenue\s+(?:grew|increased|rose|surged|up)|'
        r'record\s+(?:revenue|profits?|earnings)|'
        r'expand(?:ing|ed|s)\s+(?:operations?|facilities|workforce)|'
        r'opened\s+(?:new|additional)\s+(?:facilities|stores|locations)|'
        r'year-over-year\s+(?:growth|increase)|'
        r'strong\s+(?:financial|revenue|earnings)\s+growth|'
        r'revenue\s+growth|grew\s+(?:by\s+)?\d+%|'
        r'acquisition|acquired|IPO)\b', re.IGNORECASE,
    )
    _DECLINING = re.compile(
        r'\b(revenue\s+(?:declined|decreased|fell|dropped|down)|'
        r'layoffs?|laid\s+off|workforce\s+reduction|'
        r'clos(?:ing|ed)\s+(?:facilities|stores|locations|plants)|'
        r'bankrupt(?:cy)?|chapter\s+(?:7|11)|'
        r'restructur(?:ing|ed)|downsiz(?:ing|ed)|'
        r'declining\s+(?:revenue|sales|profits?)|'
        r'loss(?:es)?(?:\s+of)?\s+\$|net\s+loss)\b', re.IGNORECASE,
    )
    _STABLE = re.compile(
        r'\b(steady|stable\s+(?:revenue|growth|performance)|'
        r'consistent\s+(?:revenue|performance|results)|'
        r'maintained\s+(?:revenue|profitability))\b', re.IGNORECASE,
    )

    trend = None
    evidence = None

    # Search for evidence in order of priority
    growing_match = _GROWING.search(combined)
    declining_match = _DECLINING.search(combined)
    stable_match = _STABLE.search(combined)

    if declining_match:
        # Extract context around the match
        start = max(0, declining_match.start() - 50)
        end = min(len(combined), declining_match.end() + 100)
        context = combined[start:end].strip().replace("\n", " ")
        trend = "declining"
        evidence = context
    elif growing_match:
        start = max(0, growing_match.start() - 50)
        end = min(len(combined), growing_match.end() + 100)
        context = combined[start:end].strip().replace("\n", " ")
        trend = "growing"
        evidence = context
    elif stable_match:
        start = max(0, stable_match.start() - 50)
        end = min(len(combined), stable_match.end() + 100)
        context = combined[start:end].strip().replace("\n", " ")
        trend = "stable"
        evidence = context

    if trend:
        # Truncate evidence to ~150 chars
        if evidence and len(evidence) > 150:
            evidence = evidence[:147] + "..."
        assessment["financial_trend"] = f"{trend} - {evidence}" if evidence else trend
        body["assessment"] = assessment
        return True

    return False


def _validate_employee_count(dossier_data: dict, run: dict) -> None:
    """Validate employee count for plausibility (Phase 5.7).

    For public companies or companies with large size_bucket, flag suspiciously
    low employee counts (likely grabbed from a news snippet about layoffs
    rather than actual headcount).
    """
    if not dossier_data or "dossier" not in dossier_data:
        return

    body = dossier_data["dossier"]
    financial = body.get("financial", {}) or {}
    emp_val = financial.get("employee_count")
    if not emp_val:
        return

    # Parse the numeric value
    emp_num = None
    if isinstance(emp_val, (int, float)):
        emp_num = int(emp_val)
    elif isinstance(emp_val, str):
        # Extract number: "27,000 employees (web source, 2026)" -> 27000
        m = re.search(r'([\d,]+)', emp_val)
        if m:
            try:
                emp_num = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

    if emp_num is None:
        return

    company_type = (run.get("company_type") or "").lower()
    size_bucket = (run.get("employee_size_bucket") or "").lower()

    # Flag suspiciously low counts for known-large entities
    suspicious = False
    reason = ""

    if company_type == "public" and emp_num < 1000:
        suspicious = True
        reason = f"Public company with only {emp_num:,} employees seems low"
    elif size_bucket == "large" and emp_num < 500:
        suspicious = True
        reason = f"Large-bucket employer with only {emp_num:,} employees seems low"

    if suspicious:
        # Don't overwrite, but add a warning annotation
        financial["employee_count"] = f"{emp_val} (UNVERIFIED - {reason})"
        body["financial"] = financial
        _log.warning("Employee count validation: %s for %s",
                     reason, run.get("company_name", "unknown"))


def _count_null_fields(dossier_data: dict) -> tuple[int, int]:
    """Count (total_fields, null_fields) across identity/financial/workforce/labor/workplace.

    Returns (total, nulls). Useful for before/after measurement of patching.
    """
    if not dossier_data or "dossier" not in dossier_data:
        return (0, 0)
    body = dossier_data["dossier"]
    total = 0
    nulls = 0
    for sec_name in ["identity", "financial", "workforce", "labor", "workplace"]:
        sec_dict = body.get(sec_name)
        if not isinstance(sec_dict, dict):
            continue
        for _key, val in sec_dict.items():
            total += 1
            if val is None or val == "" or val == []:
                nulls += 1
    return (total, nulls)


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


def _save_facts(
    run_id: int,
    employer_id: Optional[int],
    facts: list[dict],
    vocabulary: dict,
    tool_action_map: Optional[dict] = None,
) -> int:
    """Save parsed facts to research_facts. Returns count saved.

    Links facts to their source research_actions via action_id.
    """
    if not facts:
        return 0

    conn = _conn()
    cur = conn.cursor()
    saved_ids = {}  # attribute_name -> fact_id
    saved_count = 0

    # Pass 1: save facts without contradiction links
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

        # Link to action_id
        action_id = None
        if tool_action_map:
            # First try the raw source name as provided by Gemini
            action_id = tool_action_map.get(f.get("source_name", ""))
            # Then try a cached version if applicable
            if not action_id:
                action_id = tool_action_map.get(f"{f.get('source_name')} (cached)")

        cur.execute("""
            INSERT INTO research_facts
                (run_id, employer_id, action_id, dossier_section, attribute_name,
                 attribute_value, attribute_value_json,
                 source_type, source_name, source_url,
                 confidence, as_of_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            run_id,
            employer_id,
            action_id,
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
        row = cur.fetchone()
        saved_ids[attr] = row["id"]
        saved_count += 1

    # Pass 2: resolve contradictions if Gemini provided a hint
    for f in facts:
        attr = f.get("attribute_name", "")
        # Gemini can flag which attribute this fact contradicts
        contradicted_attr = f.get("contradicts_fact_attribute")
        if contradicted_attr and contradicted_attr in saved_ids and attr in saved_ids:
            cur.execute(
                "UPDATE research_facts SET contradicts_fact_id = %s WHERE id = %s",
                (saved_ids[contradicted_attr], saved_ids[attr])
            )

    conn.commit()
    conn.close()
    return saved_count


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
    "search_sec_proxy": [
        ("exec_compensation", "executives"),
    ],
    "search_job_postings": [
        ("job_posting_count", "count_estimate"),
        ("job_posting_details", "sample_postings"),
    ],
    "get_workforce_demographics": [
        ("demographic_profile", "demographic_profile"),
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
    "exec_compensation": "financial",
    "job_posting_count": "workforce",
    "job_posting_details": "workforce",
    "demographic_profile": "workforce",
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
    tools_called_set: set[str] = set()
    tool_action_map: dict[str, int] = {}  # tool_name -> latest action_id
    final_text = ""
    _consecutive_web_only_turns = 0  # Track turns where Gemini only calls google_search

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
        _rejected_web_calls = 0
        for part in function_calls:
            fc = part.function_call
            tool_name = fc.name
            tool_input = dict(fc.args) if fc.args else {}

            # --- Reject web-search calls silently (don't count as real tools) ---
            if tool_name in ("google_search", "search_web"):
                _rejected_web_calls += 1
                _log.info("Run %d: rejected %s call #%d (not available in Phase 1)",
                          run_id, tool_name, _rejected_web_calls)
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={
                            "found": False, "source": tool_name,
                            "summary": "STOP calling this tool. Web search is NOT available here. "
                                       "You MUST use only the database tools: search_osha, search_nlrb, "
                                       "search_whd, search_sec, search_sam, search_990, search_contracts, "
                                       "search_mergent, get_industry_profile, get_similar_employers, "
                                       "scrape_employer_website. Produce your dossier JSON now.",
                            "data": {},
                        },
                    )
                )
                continue

            execution_order += 1
            tools_called += 1
            tools_called_set.add(tool_name)

            # Update progress
            pct = 10 + int(70 * (execution_order / max(len(_INTERNAL_TOOLS), 1)))
            step_desc = f"Searching {tool_name.replace('_', ' ').replace('search ', '')}..."
            _progress(run_id, step_desc, min(pct, 80))

            _log.info("Run %d: calling %s(%s)", run_id, tool_name,
                      json.dumps(tool_input, default=str)[:200])

            # Check cache before executing the tool
            cached = None
            if tool_name in TOOL_REGISTRY:
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
            action_id = _log_action(
                run_id, log_tool_name, tool_input, execution_order,
                result, latency_ms,
                company_context={
                    "company_name": run["company_name"],
                    "employer_id": run.get("employer_id"),
                },
            )
            tool_action_map[tool_name] = action_id

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

        # If ALL calls this turn were rejected web-search calls, track it.
        # After 2 consecutive web-only turns, break — Gemini is stuck.
        if _rejected_web_calls > 0 and _rejected_web_calls == len(function_calls):
            _consecutive_web_only_turns += 1
            if _consecutive_web_only_turns >= 2:
                _log.warning("Run %d: Gemini stuck calling google_search — breaking loop", run_id)
                if text_parts:
                    final_text = "\n".join(p.text for p in text_parts if p.text)
                break
        else:
            _consecutive_web_only_turns = 0

    else:
        # Exhausted turns
        _log.warning("Run %d: exhausted %d turns", run_id, MAX_TOOL_TURNS)
        # Collect whatever text we got in the last response
        if not final_text:
            final_text = "\n".join(p.text for p in parts if p.text)

    # ------------------------------------------------------------------
    # Phase 1.5: Force scraper if Gemini didn't call it
    # ------------------------------------------------------------------
    if "scrape_employer_website" not in tools_called_set:
        _progress(run_id, "Scraping employer website...", 81)
        try:
            scrape_result = TOOL_REGISTRY["scrape_employer_website"](
                company_name=run["company_name"],
                employer_id=run.get("employer_id"),
                industry=run.get("industry_naics"),
                state=run.get("company_state"),
            )
            execution_order += 1
            tools_called += 1
            tools_called_set.add("scrape_employer_website")
            _log_action(
                run_id, "scrape_employer_website (forced)",
                {
                    "company_name": run["company_name"],
                    "employer_id": run.get("employer_id"),
                    "industry": run.get("industry_naics"),
                    "state": run.get("company_state"),
                },
                execution_order,
                scrape_result,
                0,
            )
            # Parse scraper results into the dossier text if we have a dossier
            if scrape_result.get("found"):
                scrape_data = scrape_result.get("data", {})
                # Try to patch the dossier with scraper findings
                dossier_obj = _extract_dossier_json(final_text)
                if dossier_obj and "dossier" in dossier_obj:
                    body = dossier_obj["dossier"]
                    identity = body.get("identity", {}) or {}
                    if scrape_data.get("url") and not identity.get("website_url"):
                        identity["website_url"] = scrape_data["url"]
                    body["identity"] = identity
                    # Re-serialize
                    final_text = "```json\n" + json.dumps(dossier_obj, indent=2, default=str) + "\n```"
                    _log.info("Run %d: forced scraper found URL: %s", run_id, scrape_data.get("url"))
        except Exception as scrape_exc:
            _log.warning("Run %d: forced scraper failed (non-fatal): %s", run_id, scrape_exc)

    # ------------------------------------------------------------------
    # Phase 1.6: Force-call new enrichment tools
    # ------------------------------------------------------------------
    # These tools were added in Phase 5.5/5.6 but Gemini never calls them
    # voluntarily, so we force them like the scraper above.

    # 1.6a: search_sec_proxy — only for public companies where search_sec found data
    if "search_sec_proxy" not in tools_called_set:
        # Check if search_sec returned data (indicates public company)
        _is_public = False
        _sec_cik = None
        _sec_ticker = None
        try:
            conn_check = _conn()
            cur_check = conn_check.cursor()
            cur_check.execute("""
                SELECT data_found, result_summary
                FROM research_actions
                WHERE run_id = %s AND tool_name IN ('search_sec', 'search_sec (cached)')
                  AND data_found = TRUE
                ORDER BY execution_order DESC LIMIT 1
            """, (run_id,))
            sec_row = cur_check.fetchone()
            conn_check.close()
            if sec_row:
                _is_public = True
                _summary = sec_row["result_summary"] or ""
                # Try to extract CIK/ticker from summary
                cik_m = re.search(r'CIK[:\s]*(\d+)', _summary, re.IGNORECASE)
                if cik_m:
                    _sec_cik = cik_m.group(1)
                ticker_m = re.search(r'ticker[:\s]*([A-Z]{1,5})', _summary, re.IGNORECASE)
                if ticker_m:
                    _sec_ticker = ticker_m.group(1)
        except Exception:
            pass

        if _is_public:
            _progress(run_id, "Fetching SEC proxy executive pay...", 82)
            try:
                t0 = time.time()
                proxy_result = TOOL_REGISTRY["search_sec_proxy"](
                    company_name=run["company_name"],
                    cik=_sec_cik,
                    ticker=_sec_ticker,
                )
                lat = int((time.time() - t0) * 1000)
                execution_order += 1
                tools_called += 1
                tools_called_set.add("search_sec_proxy")
                action_id = _log_action(
                    run_id, "search_sec_proxy (forced)",
                    {"company_name": run["company_name"], "cik": _sec_cik, "ticker": _sec_ticker},
                    execution_order, proxy_result, lat,
                )
                tool_action_map["search_sec_proxy"] = action_id
                if proxy_result.get("found"):
                    dossier_obj = _extract_dossier_json(final_text)
                    if dossier_obj and "dossier" in dossier_obj:
                        financial = dossier_obj["dossier"].setdefault("financial", {})
                        if not financial.get("exec_compensation"):
                            financial["exec_compensation"] = proxy_result.get("data", {}).get("executives")
                            final_text = "```json\n" + json.dumps(dossier_obj, indent=2, default=str) + "\n```"
                    _log.info("Run %d: forced search_sec_proxy found exec pay", run_id)
            except Exception as exc:
                _log.warning("Run %d: forced search_sec_proxy failed (non-fatal): %s", run_id, exc)

    # 1.6b: search_job_postings — always
    if "search_job_postings" not in tools_called_set:
        _progress(run_id, "Searching for job postings...", 83)
        try:
            t0 = time.time()
            jobs_result = TOOL_REGISTRY["search_job_postings"](
                company_name=run["company_name"],
                state=run.get("company_state"),
            )
            lat = int((time.time() - t0) * 1000)
            execution_order += 1
            tools_called += 1
            tools_called_set.add("search_job_postings")
            action_id = _log_action(
                run_id, "search_job_postings (forced)",
                {"company_name": run["company_name"], "state": run.get("company_state")},
                execution_order, jobs_result, lat,
            )
            tool_action_map["search_job_postings"] = action_id
            if jobs_result.get("found"):
                dossier_obj = _extract_dossier_json(final_text)
                if dossier_obj and "dossier" in dossier_obj:
                    workforce = dossier_obj["dossier"].setdefault("workforce", {})
                    job_data = jobs_result.get("data", {})
                    if not workforce.get("job_posting_count"):
                        workforce["job_posting_count"] = job_data.get("count_estimate")
                    if not workforce.get("job_posting_details"):
                        workforce["job_posting_details"] = job_data.get("sample_postings")
                    # Turnover signal if many postings
                    count = job_data.get("count_estimate", 0)
                    if isinstance(count, (int, float)) and count > 100 and not workforce.get("turnover_signals"):
                        workforce["turnover_signals"] = f"High hiring volume ({count}+ open positions may indicate turnover)"
                    final_text = "```json\n" + json.dumps(dossier_obj, indent=2, default=str) + "\n```"
                _log.info("Run %d: forced search_job_postings found %s postings",
                          run_id, jobs_result.get("data", {}).get("count_estimate", "?"))
        except Exception as exc:
            _log.warning("Run %d: forced search_job_postings failed (non-fatal): %s", run_id, exc)

    # 1.6c: get_workforce_demographics — only if NAICS known
    if "get_workforce_demographics" not in tools_called_set:
        _naics = run.get("industry_naics") or ""
        if _naics and _naics != "unknown":
            _progress(run_id, "Getting workforce demographics...", 84)
            try:
                t0 = time.time()
                demo_result = TOOL_REGISTRY["get_workforce_demographics"](
                    company_name=run["company_name"],
                    naics=_naics,
                    state=run.get("company_state"),
                )
                lat = int((time.time() - t0) * 1000)
                execution_order += 1
                tools_called += 1
                tools_called_set.add("get_workforce_demographics")
                action_id = _log_action(
                    run_id, "get_workforce_demographics (forced)",
                    {"company_name": run["company_name"], "naics": _naics, "state": run.get("company_state")},
                    execution_order, demo_result, lat,
                )
                tool_action_map["get_workforce_demographics"] = action_id
                if demo_result.get("found"):
                    dossier_obj = _extract_dossier_json(final_text)
                    if dossier_obj and "dossier" in dossier_obj:
                        workforce = dossier_obj["dossier"].setdefault("workforce", {})
                        labeled_profile = demo_result.get("data", {}).get("demographic_profile")
                        # Always overwrite with labeled version (has INDUSTRY BASELINE prefix)
                        if labeled_profile:
                            workforce["demographic_profile"] = labeled_profile
                            final_text = "```json\n" + json.dumps(dossier_obj, indent=2, default=str) + "\n```"
                    _log.info("Run %d: forced get_workforce_demographics found demographics", run_id)
            except Exception as exc:
                _log.warning("Run %d: forced get_workforce_demographics failed (non-fatal): %s", run_id, exc)

    # ------------------------------------------------------------------
    # Phase 2: Web search via Google Search grounding
    # ------------------------------------------------------------------
    # Gemini cannot combine function_declarations and google_search in
    # one request, so we run a separate call with only Google Search
    # grounding enabled to enrich the dossier with current web context.
    _progress(run_id, "Searching the web for current context...", 85)

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
1. **Recent news** ({datetime.now().year - 1}-{datetime.now().year}): layoffs, expansions, lawsuits, mergers, acquisitions, executive changes
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
  "financial_data": {{
    "employee_count": "Number of employees (Source Name, YYYY)",
    "revenue": "Annual revenue in dollars (Source Name, YYYY)",
    "website_url": "Official company website URL"
  }},
  "safety_violations": [
    "OSHA citations, fines, workplace injuries, safety incidents (Source Name, YYYY-MM-DD)"
  ],
  "wage_violations": [
    "Wage theft, DOL investigations, FLSA violations, back wages (Source Name, YYYY-MM-DD)"
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
        action_id = _log_action(
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
        tool_action_map["google_search"] = action_id

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
        _progress(run_id, "Merging web findings into dossier...", 88)
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

                    # Extract turnover signals from worker_issues
                    _TURNOVER_KEYWORDS = re.compile(
                        r'\b(turnover|quit|retention|hiring|understaffed|'
                        r'attrition|shortage|staffing|vacancy|resign)',
                        re.IGNORECASE,
                    )
                    if worker_issues:
                        turnover_hits = []
                        for item in worker_issues:
                            if isinstance(item, str) and _TURNOVER_KEYWORDS.search(item):
                                turnover_hits.append(item)
                        if turnover_hits:
                            workforce = dossier_body.get("workforce", {}) or {}
                            existing_turnover = workforce.get("turnover_signals", [])
                            if not isinstance(existing_turnover, list):
                                existing_turnover = [existing_turnover] if existing_turnover else []
                            existing_turnover.extend(turnover_hits)
                            workforce["turnover_signals"] = existing_turnover
                            dossier_body["workforce"] = workforce

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

                    # --- Merge financial_data into financial/identity ---
                    fin_data = web_data.get("financial_data")
                    if not isinstance(fin_data, dict):
                        fin_data = {}

                    # Fallback: regex-extract from raw web text when Gemini
                    # didn't produce a structured financial_data dict
                    if not fin_data.get("employee_count") or not fin_data.get("revenue"):
                        regex_fin = _extract_financial_from_text(web_text)
                        for k, v in regex_fin.items():
                            if not fin_data.get(k):
                                fin_data[k] = v
                                _log.info("Run %d: regex-extracted %s from web text", run_id, k)

                    if fin_data:
                        identity = dossier_body.get("identity", {}) or {}
                        financial = dossier_body.get("financial", {}) or {}
                        if fin_data.get("employee_count"):
                            financial.setdefault("employee_count", fin_data["employee_count"])
                        if fin_data.get("revenue"):
                            financial.setdefault("revenue", fin_data["revenue"])
                        if fin_data.get("website_url"):
                            identity.setdefault("website_url", fin_data["website_url"])
                        dossier_body["identity"] = identity
                        dossier_body["financial"] = financial

                    # --- Merge safety_violations into workplace ---
                    safety_violations = web_data.get("safety_violations", [])
                    if safety_violations:
                        workplace = dossier_body.get("workplace", {}) or {}
                        existing_safety = workplace.get("osha_violation_details", [])
                        if not isinstance(existing_safety, list):
                            existing_safety = [existing_safety] if existing_safety else []
                        for item in safety_violations:
                            if isinstance(item, str) and item.strip():
                                existing_safety.append(f"[Web] {item}")
                        if existing_safety:
                            workplace["osha_violation_details"] = existing_safety
                            dossier_body["workplace"] = workplace

                    # --- Merge wage_violations into workplace ---
                    wage_violations = web_data.get("wage_violations", [])
                    if wage_violations:
                        workplace = dossier_body.get("workplace", {}) or {}
                        existing_wage = workplace.get("whd_violation_details", [])
                        if not isinstance(existing_wage, list):
                            existing_wage = [existing_wage] if existing_wage else []
                        for item in wage_violations:
                            if isinstance(item, str) and item.strip():
                                existing_wage.append(f"[Web] {item}")
                        if existing_wage:
                            workplace["whd_violation_details"] = existing_wage
                            dossier_body["workplace"] = workplace

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

                    # --- Merge recent_news into workplace body ---
                    recent_news = web_data.get("recent_news", [])
                    if recent_news:
                        workplace = dossier_body.get("workplace", {}) or {}
                        existing_news = workplace.get("recent_labor_news", [])
                        if not isinstance(existing_news, list):
                            existing_news = [existing_news] if existing_news else []
                        for item in recent_news:
                            if isinstance(item, str) and item.strip():
                                existing_news.append(item)
                        if existing_news:
                            workplace["recent_labor_news"] = existing_news
                            dossier_body["workplace"] = workplace

                    # --- Add web facts ---
                    for item in recent_news:
                        if isinstance(item, str) and item.strip():
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "workplace",
                                "attribute_name": "recent_labor_news",
                                "attribute_value": item,
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.7,
                                "as_of_date": date.today().isoformat(),
                            })
                    # Add organizing activity as facts too
                    for item in organizing:
                        if isinstance(item, str) and item.strip():
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "labor",
                                "attribute_name": "recent_organizing",
                                "attribute_value": item,
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.7,
                                "as_of_date": date.today().isoformat(),
                            })
                    # Add financial data as facts
                    if isinstance(fin_data, dict):
                        _today_iso = date.today().isoformat()
                        if fin_data.get("employee_count"):
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "identity",
                                "attribute_name": "employee_count",
                                "attribute_value": fin_data["employee_count"],
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.6,
                                "as_of_date": _today_iso,
                            })
                        if fin_data.get("revenue"):
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "financial",
                                "attribute_name": "revenue",
                                "attribute_value": fin_data["revenue"],
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.6,
                                "as_of_date": _today_iso,
                            })
                        if fin_data.get("website_url"):
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "identity",
                                "attribute_name": "website_url",
                                "attribute_value": fin_data["website_url"],
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.7,
                                "as_of_date": _today_iso,
                            })
                    # Add safety violations as facts
                    for item in safety_violations:
                        if isinstance(item, str) and item.strip():
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "workplace",
                                "attribute_name": "osha_violation_web",
                                "attribute_value": item,
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.6,
                                "as_of_date": date.today().isoformat(),
                            })
                    # Add wage violations as facts
                    for item in wage_violations:
                        if isinstance(item, str) and item.strip():
                            original_dossier.setdefault("facts", []).append({
                                "dossier_section": "workplace",
                                "attribute_name": "whd_violation_web",
                                "attribute_value": item,
                                "source_type": "web_search",
                                "source_name": "google_search",
                                "confidence": 0.6,
                                "as_of_date": date.today().isoformat(),
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
    # Phase 4: Post-merge validation — copy facts to dossier body
    # ------------------------------------------------------------------
    # Facts array may contain data that didn't make it into the dossier body.
    # This pass copies fact values into the appropriate dossier body sections.
    try:
        validated_dossier = _extract_dossier_json(final_text)
        if validated_dossier and "dossier" in validated_dossier:
            vd_body = validated_dossier["dossier"]
            facts_arr = validated_dossier.get("facts", [])
            missing_fields = []
            patched = 0

            for fact in facts_arr:
                sec = fact.get("dossier_section")
                attr = fact.get("attribute_name")
                val = fact.get("attribute_value")
                if not sec or not attr or not val:
                    continue

                sec_dict = vd_body.get(sec)
                if not isinstance(sec_dict, dict):
                    sec_dict = {}
                    vd_body[sec] = sec_dict

                # Copy fact to body if the field is empty
                existing = sec_dict.get(attr)
                if existing is None or existing == "" or existing == []:
                    sec_dict[attr] = val
                    patched += 1

            # Log which vocabulary fields are still missing
            for sec_name in _DOSSIER_SECTIONS:
                sec_dict = vd_body.get(sec_name)
                if not isinstance(sec_dict, dict):
                    missing_fields.append(f"{sec_name}.*")
                    continue
                for key, val in sec_dict.items():
                    if val is None:
                        missing_fields.append(f"{sec_name}.{key}")

            if patched:
                final_text = "```json\n" + json.dumps(validated_dossier, indent=2, default=str) + "\n```"
                _log.info("Run %d: validation patched %d fields from facts array", run_id, patched)
            if missing_fields:
                _log.info("Run %d: still missing %d fields: %s",
                          run_id, len(missing_fields), ", ".join(missing_fields[:20]))
    except Exception as val_exc:
        _log.warning("Run %d: post-merge validation failed (non-fatal): %s", run_id, val_exc)

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
                        "safety_violations": "osha_violations",
                        "wage_violations": "whd_violations",
                    }
                    for sec_key, gap_key in _section_gap_map.items():
                        val = _web_data.get(sec_key, [])
                        if isinstance(val, list) and val:
                            web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + len(val)
                        elif isinstance(val, str) and val.strip():
                            web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + 1

                    # Handle financial_data dict -> 3 separate gap types
                    fin_data = _web_data.get("financial_data")
                    if isinstance(fin_data, dict):
                        for fin_key, gap_key in [
                            ("employee_count", "employee_count"),
                            ("revenue", "revenue"),
                            ("website_url", "website_url"),
                        ]:
                            val = fin_data.get(fin_key)
                            if val and isinstance(val, str) and val.strip():
                                web_facts_by_gap[gap_key] = web_facts_by_gap.get(gap_key, 0) + 1
            _update_query_effectiveness(gap_types_queried, web_facts_by_gap, company_type)
        except Exception as qe_exc:
            _log.warning("Run %d: query effectiveness tracking failed (non-fatal): %s", run_id, qe_exc)

    # ------------------------------------------------------------------
    # Parse dossier from final response
    # ------------------------------------------------------------------
    _progress(run_id, "Parsing dossier...", 90)

    dossier_data = _extract_dossier_json(final_text)

    if not dossier_data:
        _log.warning("Run %d: could not parse dossier JSON (text_len=%d, first 200=%s)",
                     run_id, len(final_text), repr(final_text[:200]))
        dossier_data = {
            "dossier": {"raw_text": final_text},
            "facts": [],
            "parse_error": "Could not extract structured JSON from agent response",
        }
    else:
        # Patch missing financials from narrative (Issue #1)
        total_before, nulls_before = _count_null_fields(dossier_data)
        patched_count = _patch_dossier_financials(dossier_data, web_text)
        if patched_count:
            _total_after, nulls_after = _count_null_fields(dossier_data)
            _log.info("Run %d: _patch_dossier_financials: patched=%d, nulls %d->%d (of %d fields)",
                       run_id, patched_count, nulls_before, nulls_after, total_before)

        # Employee count validation (Phase 5.7)
        _validate_employee_count(dossier_data, run)

        # Resolve DB-vs-web contradictions (Phase 5.7)
        contradictions_found = _resolve_contradictions(dossier_data)
        if contradictions_found:
            _log.info("Run %d: resolved %d DB-vs-web contradictions", run_id, contradictions_found)

        # Extract financial_trend from narratives (Phase 5.7)
        if _extract_financial_trend(dossier_data, web_text):
            _log.info("Run %d: extracted financial_trend from narratives", run_id)

        # Second-pass gap filler (Issue #13)
        total_before2, nulls_before2 = _count_null_fields(dossier_data)
        gaps_filled = _fill_dossier_gaps(run_id, dossier_data, web_text, vocabulary)
        if gaps_filled:
            _total_after2, nulls_after2 = _count_null_fields(dossier_data)
            _log.info("Run %d: _fill_dossier_gaps: filled=%d, nulls %d->%d (of %d fields)",
                       run_id, gaps_filled, nulls_before2, nulls_after2, total_before2)

    # ------------------------------------------------------------------
    # Save facts
    # ------------------------------------------------------------------
    _progress(run_id, "Saving facts...", 93)

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
        tool_action_map=tool_action_map,
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

    # Auto-grade the completed run (non-blocking)
    try:
        from scripts.research.auto_grader import grade_and_save
        grade_and_save(run_id)
    except Exception as e:
        _log.warning("Auto-grading failed for run %d: %s", run_id, e)

    # Compute scorecard enhancements (non-blocking)
    try:
        from scripts.research.auto_grader import compute_research_enhancements
        compute_research_enhancements(run_id)
    except Exception as e:
        _log.warning("Scorecard enhancement failed for run %d: %s", run_id, e)

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
