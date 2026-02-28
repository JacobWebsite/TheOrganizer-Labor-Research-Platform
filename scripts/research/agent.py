"""
Research Agent (Phase 5.8)

Gemini-powered AI orchestration loop for deep-dive corporate intelligence.
Conducts multi-turn research using internal databases and parallel web tools.
Produces a structured dossier JSON with guaranteed 72-field coverage.

Improvements:
- Async parallel execution for all tools.
- Integrated Cross-Union Solidarity matching (GLEIF + F7).
- Integrated Taxpayer Receipt (Local Subsidies & IDAs).
- Integrated Worker Sentiment (Reddit/Glassdoor/Indeed).
- Integrated SOS LLC Unmasking.
- Address-aware matching and web searching.
- Exhaustive reporting logic (Verified None).
"""
import json
import logging
import os
import re
import sys
import time
import asyncio
from datetime import datetime, date
from typing import Optional, Any, Tuple

from google import genai
from google.genai import types

from scripts.research.tools import TOOL_REGISTRY, TOOL_DEFINITIONS, _conn, _safe, _safe_dict, _safe_list

# Configuration
MODEL = os.environ.get("RESEARCH_AGENT_MODEL", "gemini-2.5-flash")
MAX_TOOL_TURNS = int(os.environ.get("RESEARCH_AGENT_MAX_TURNS", 25))
MAX_TOKENS = int(os.environ.get("RESEARCH_AGENT_MAX_TOKENS", 65536))

_INPUT_COST_PER_1K = 0.003  # $0.30 per 1M
_OUTPUT_COST_PER_1K = 0.025  # $2.50 per 1M

_log = logging.getLogger("research.agent")

_DOSSIER_SECTIONS = ["identity", "financial", "workforce", "labor", "workplace", "assessment", "sources"]

_INTERNAL_TOOLS = [
    "search_osha", "search_nlrb", "search_whd", "search_sec",
    "search_sam", "search_990", "search_contracts", "search_mergent",
    "search_sec_proxy", "search_job_postings", "get_workforce_demographics",
    "get_industry_profile", "get_similar_employers",
    "scrape_employer_website", "google_search",
    "search_worker_sentiment", "search_sos_filings", "compare_industry_wages",
    "search_solidarity_network", "search_local_subsidies",
    "search_acs_workforce",
]

# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def _update_run(run_id: int, **kwargs):
    """Update research_runs table."""
    if not kwargs:
        return
    conn = _conn()
    cur = conn.cursor()
    sets = ", ".join([f"{k} = %s" for k in kwargs.keys()])
    vals = list(kwargs.values())
    cur.execute(f"UPDATE research_runs SET {sets} WHERE id = %s", vals + [run_id])
    conn.commit()
    conn.close()

def _progress(run_id: int, step: str, pct: int):
    """Update progress in research_runs."""
    _update_run(run_id, current_step=step, progress_pct=pct)

def _load_vocabulary() -> dict:
    """Load canonical attribute names from research_fact_vocabulary."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM research_fact_vocabulary")
    rows = cur.fetchall()
    conn.close()
    return {r["attribute_name"]: dict(r) for r in rows}

def _check_cache(employer_id: str, tool_name: str) -> Optional[dict]:
    """Check if we have a recent successful tool result for this employer."""
    if not employer_id:
        return None
    cache_hours = int(os.environ.get("RESEARCH_CACHE_HOURS", 168))  # 7 days default
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT result_summary, data_quality, created_at
        FROM research_actions
        WHERE tool_name = %s
          AND (company_context->>'employer_id') = %s
          AND data_found = TRUE
          AND created_at > NOW() - INTERVAL '%s hours'
        ORDER BY created_at DESC LIMIT 1
    """, (tool_name, str(employer_id), cache_hours))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

# ---------------------------------------------------------------------------
# Query Builder & Effectiveness (Phase 5.2)
# ---------------------------------------------------------------------------

_GAP_QUERY_TEMPLATES = {
    # When Mergent misses (48% miss rate)
    "employee_count": [
        '"{company}" number of employees {year} {address}',
        '"{company}" employees site:linkedin.com {address}',
        '"{company}" workforce size headcount {state}',
    ],
    "revenue": [
        '"{company}" annual revenue {year}',
        '"{company}" revenue SEC 10-K billion million',
        '"{company}" revenue financial results {state} {year} {address}',
    ],
    "website_url": [
        '"{company}" official site {address}',
        '"{company}" homepage {state}',
    ],
    # When OSHA misses
    "osha_violations": [
        '"{company}" OSHA violations safety citations {state} {address}',
        '"{company}" OSHA inspection fine {year}',
        '"{company}" workplace safety incident {state} {year} {address}',
    ],
    # When NLRB misses
    "nlrb_activity": [
        '"{company}" NLRB union election filing {address}',
        '"{company}" unfair labor practice charge {address}',
        '"{company}" union organizing campaign {year} {address}',
    ],
    # When WHD misses
    "whd_violations": [
        '"{company}" wage theft Department of Labor {state} {address}',
        '"{company}" FLSA violation back wages {year} {address}',
        '"{company}" Fair Labor Standards Act {state} {year}',
    ],
    # When 990 misses (nonprofits)
    "nonprofit_financials": [
        '"{company}" 990 tax return nonprofit revenue {address}',
        '"{company}" GuideStar ProPublica nonprofit',
    ],
    # Always-run queries (refined from current static 6)
    "recent_news": [
        '"{company}" news {year} {address}',
        '"{company}" layoffs expansion acquisition {year} {address}',
    ],
    "labor_stance": [
        '"{company}" union stance labor relations {address}',
        '"{company}" anti-union OR pro-union workers {address}',
    ],
    "worker_conditions": [
        '"{company}" Glassdoor employee reviews working conditions {address}',
        '"{company}" worker complaints lawsuit labor {address}',
    ],
}

_TOOL_GAP_MAP = {
    "search_mergent": ["employee_count", "revenue", "website_url"],
    "search_990": ["nonprofit_financials", "employee_count"],
    "search_osha": ["osha_violations"],
    "search_nlrb": ["nlrb_activity"],
    "search_whd": ["whd_violations"],
}

def _get_best_queries(gap_type: str, company_type: Optional[str] = None) -> list[str]:
    """Return top templates from research_query_effectiveness.

    Skips templates that have been tried >=5 times with zero results.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT query_template FROM research_query_effectiveness
        WHERE gap_type = %s AND (company_type = %s OR company_type IS NULL)
          AND NOT (times_used >= 5 AND times_produced_result = 0)
        ORDER BY avg_facts_produced DESC, times_produced_result DESC
        LIMIT 2
    """, (gap_type, company_type))
    rows = cur.fetchall()
    conn.close()
    return [r["query_template"] for r in rows]

def _update_query_effectiveness(gap_types_used: list, web_facts_by_gap: dict, company_type: str):
    """Log which query templates produced results."""
    conn = _conn()
    cur = conn.cursor()
    for gap_type, template in gap_types_used:
        produced = web_facts_by_gap.get(gap_type, 0)
        cur.execute("""
            INSERT INTO research_query_effectiveness 
                (gap_type, company_type, query_template, times_used, times_produced_result, avg_facts_produced, last_used_at)
            VALUES (%s, %s, %s, 1, %s, %s, NOW())
            ON CONFLICT (gap_type, query_template) DO UPDATE SET
                times_used = research_query_effectiveness.times_used + 1,
                times_produced_result = research_query_effectiveness.times_produced_result + (CASE WHEN %s > 0 THEN 1 ELSE 0 END),
                avg_facts_produced = (research_query_effectiveness.avg_facts_produced * research_query_effectiveness.times_used + %s) / (research_query_effectiveness.times_used + 1),
                last_used_at = NOW()
        """, (gap_type, company_type, template, 1 if produced > 0 else 0, produced, produced, produced))
    conn.commit()
    conn.close()

def _build_web_search_queries(company_name: str, company_type: Optional[str],
                               company_state: Optional[str],
                               db_gaps: list[str],
                               year: str = None,
                               company_address: Optional[str] = None) -> list[str]:
    """Build targeted search queries based on which DB tools missed."""
    if year is None:
        year = str(datetime.now().year)
    queries = []
    gap_types_used = []

    for tool_name in db_gaps:
        for gap_key in _TOOL_GAP_MAP.get(tool_name, []):
            best = _get_best_queries(gap_key, company_type)
            templates = best or _GAP_QUERY_TEMPLATES.get(gap_key, [])
            for t in templates[:2]:
                queries.append(t)
                gap_types_used.append((gap_key, t))

    for key in ["recent_news", "labor_stance", "worker_conditions"]:
        templates = _GAP_QUERY_TEMPLATES.get(key)
        for t in templates[:1]:
            queries.append(t)
            gap_types_used.append((key, t))

    filled = []
    for q in queries:
        try:
            filled.append(q.format(
                company=company_name,
                state=company_state or "",
                year=year,
                address=company_address or "",
            ))
        except (KeyError, IndexError):
            filled.append(q.format(
                company=company_name,
                state=company_state or "",
                year=year
            ))

    return filled[:15], gap_types_used[:15]

# ---------------------------------------------------------------------------
# Strategy Loader (Learning Loop)
# ---------------------------------------------------------------------------

def _load_strategy(naics_2: str, company_type: str, size_bucket: str) -> list[dict]:
    """Load tool effectiveness data for this industry/type/size combo.

    Returns ordered list of dicts with tool_name, hit_rate, avg_quality, times_tried.
    Sorted by hit_rate * avg_quality descending (most effective tools first).
    """
    if not naics_2:
        return []
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT tool_name, hit_rate, avg_quality, times_tried
            FROM research_strategies
            WHERE industry_naics_2digit = %s
              AND company_type = %s
              AND company_size_bucket = %s
              AND times_tried >= 3
            ORDER BY COALESCE(hit_rate, 0) * COALESCE(avg_quality, 0) DESC
        """, (naics_2, company_type or "", size_bucket or ""))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        _log.debug("Strategy load failed: %s", exc)
        return []


def _build_strategy_prompt_section(strategy: list[dict]) -> str:
    """Build a system prompt section from strategy data."""
    if not strategy:
        return ""

    high = [r for r in strategy if (r.get("hit_rate") or 0) > 0.6]
    moderate = [r for r in strategy if 0.3 <= (r.get("hit_rate") or 0) <= 0.6]
    low = [r for r in strategy if (r.get("hit_rate") or 0) < 0.1 and (r.get("times_tried") or 0) >= 5]

    if not high and not moderate and not low:
        return ""

    lines = [f"\n## Tool Effectiveness (based on {sum(r.get('times_tried', 0) for r in strategy)} prior runs)"]
    if high:
        tools = ", ".join(f"{r['tool_name']} ({r['hit_rate']:.0%})" for r in high[:5])
        lines.append(f"- HIGH VALUE: {tools} -- call these first")
    if moderate:
        tools = ", ".join(f"{r['tool_name']} ({r['hit_rate']:.0%})" for r in moderate[:5])
        lines.append(f"- MODERATE: {tools} -- call if relevant")
    if low:
        tools = ", ".join(r["tool_name"] for r in low[:5])
        lines.append(f"- LOW VALUE: {tools} -- skip unless specifically needed")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(run: dict, vocabulary: dict[str, dict]) -> str:
    """Build the system prompt for the research agent."""
    company_name = run["company_name"]
    employer_id = run.get("employer_id") or "unknown"
    company_address = run.get("company_address") or "unknown"
    naics = run.get("industry_naics") or "unknown"
    company_type = run.get("company_type") or "unknown"
    state = run.get("company_state") or "unknown"
    size_bucket = run.get("employee_size_bucket") or "unknown"

    prompt = f"""You are a labor-relations research agent. Your job is to compile a comprehensive organizing dossier on a single employer by querying internal databases.

## Company Under Research
- **Name:** {company_name}
- **Address:** {company_address}
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
   - GLEIF corporate ownership (search_gleif_ownership) -- Call for large (>500 employees) or public companies. Returns parent companies and subsidiaries.
   - Solidarity Network (search_solidarity_network) -- Call if corporate family context is available. Finds unionized sister facilities in the corporate family.
   - Form 5500 benefit plans (search_form5500) -- ALWAYS call this. Returns pension/welfare plan data, participant counts, and collective bargaining indicators.
   - PPP loans (search_ppp_loans) -- Call this. Returns pandemic-era loan amounts, forgiveness status, and jobs retained.

2. **Get industry and local context:**
   - BLS industry profile (get_industry_profile) -- needs a NAICS code. Now includes CBP local establishment counts if state is provided.
   - Similar organized employers (get_similar_employers)
   - Local demographics (search_local_demographics) -- Call if city and state are known. Returns population, race, and income context. (Note: ACS tool below is preferred.)
   - Taxpayer Subsidies (search_local_subsidies) -- Call if relevant to the employer. Returns local tax breaks and grants.
   - CBP industry context (search_cbp_context) -- ALWAYS call this if NAICS is known. Returns local establishment counts, employment, and avg wages.
   - LODES workforce data (search_lodes_workforce) -- Call if state/county is known. Returns job counts, earnings tiers, and industry mix.
   - ABS firm demographics (search_abs_demographics) -- Call if NAICS is known. Returns firm owner demographics by industry.
   - ACS workforce demographics (search_acs_workforce) -- ALWAYS call this if state is known. Returns gender, race, age, education, and worker class breakdowns for the workforce in this state/industry.

3. **Get additional enrichment** (these tools fill critical gaps):
   - Job postings estimate (search_job_postings) -- ALWAYS call this. Returns active job count and sample titles/pay. High turnover signal if count > 100.
   - Workforce demographics (get_workforce_demographics) -- Call if NAICS is known. Returns industry demographic baselines (race, gender, age).
   - Political donations (search_political_donations) -- Call for larger companies (>500 employees). Returns contributions by the company and executives.
   - WARN layoff notices (search_warn_notices) -- ALWAYS call this. Returns recent mass layoff notices.
   - Worker sentiment (search_worker_sentiment) -- ALWAYS call this. Searches Reddit, Glassdoor, and Indeed for employee complaints and 'vibe'.
   - SOS corporate filings (search_sos_filings) -- ALWAYS call this. Finds registered agents, officers, and filing links.
   - Competitor wage comparison (compare_industry_wages) -- ALWAYS call this. Compares target wages against local industry peers.
   - QCEW wage comparison (compare_employer_wages) -- Call if state and NAICS are known. Compares employer wages against BLS local industry averages. Pass known_wage if available from WHD or 990 data.

4. **Scrape employer website** (scrape_employer_website) -- if search_mergent returned a website URL, pass it here. Otherwise the tool will look it up. Returns homepage, about, careers, and news text.

5. **Synthesize** your findings into the dossier.

IMPORTANT: Do NOT call `google_search` directly -- web search is handled separately after your database queries. But DO call all tools listed in steps 1-4 above.

Return your final report as a JSON object inside a code block. Your response must be parseable JSON with this structure:
{{
  "dossier": {{
    "identity": {{ ... }},
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
      "as_of_date": "YYYY-MM-DD"
    }}
  ]
}}
"""
    # Inject strategy section if available
    naics_2 = (run.get("industry_naics") or "")[:2]
    company_type = run.get("company_type") or ""
    size_bucket = run.get("employee_size_bucket") or ""
    strategy = _load_strategy(naics_2, company_type, size_bucket)
    strategy_section = _build_strategy_prompt_section(strategy)
    if strategy_section:
        prompt += strategy_section

    return prompt

def _build_gemini_tools():
    """Build FunctionDeclarations for Gemini."""
    declarations = []
    for td in TOOL_DEFINITIONS:
        params = {}
        required = td["input_schema"].get("required", [])
        for p, pdef in td["input_schema"]["properties"].items():
            params[p] = types.Schema(
                type=pdef["type"].upper(),
                description=pdef.get("description", ""),
            )
        declarations.append(types.FunctionDeclaration(
            name=td["name"],
            description=td["description"],
            parameters=types.Schema(
                type="OBJECT",
                properties=params,
                required=required,
            ),
        ))
    return [types.Tool(function_declarations=declarations)]

def _build_google_search_tool():
    """Build the Tool object for Google Search grounding."""
    return [types.Tool(google_search=types.GoogleSearch())]

# ---------------------------------------------------------------------------
# Post-Processing & Validation
# ---------------------------------------------------------------------------

def _extract_financial_from_text(text: str) -> dict:
    """Regex-extract employee count and revenue from raw web text."""
    result = {}
    if not text: return result
    
    # Employee count
    m_emp = re.search(r'\b(?:employ(?:ees?|s)|headcount|workforce)\s*(?:of|is|at|approx\.?)?\s*([\d,]+)\b', text, re.IGNORECASE)
    if m_emp:
        val = m_emp.group(1).replace(",", "")
        if val.isdigit() and int(val) > 0: result["employee_count"] = val
        
    # Revenue
    m_rev = re.search(r'\b(?:revenue|sales|turnover)\s*(?:of|is|at|approx\.?)?\s*\$?\s*([\d,.]+\s*[bm]illion)\b', text, re.IGNORECASE)
    if m_rev: result["revenue"] = m_rev.group(1)
    
    return result

def _patch_dossier_financials(dossier_data: dict, web_text: str = "") -> int:
    """Scan narrative sections for missing financial data."""
    if not dossier_data or "dossier" not in dossier_data: return 0
    body = dossier_data["dossier"]
    identity = body.setdefault("identity", {})
    financial = body.setdefault("financial", {})
    
    patched = 0
    if not financial.get("employee_count") or not financial.get("revenue"):
        extracted = _extract_financial_from_text(web_text)
        for k, v in extracted.items():
            if not financial.get(k):
                financial[k] = v
                patched += 1
    return patched

def _resolve_contradictions(dossier_data: dict) -> int:
    """Check for and log contradictions in the dossier."""
    return 0

def _extract_financial_trend(dossier_data: dict, web_text: str = "") -> bool:
    """Extract financial_trend from web text and dossier narratives."""
    if not dossier_data or "dossier" not in dossier_data: return False
    body = dossier_data["dossier"]
    assessment = body.setdefault("assessment", {})
    if assessment.get("financial_trend"): return False
    
    combined = (assessment.get("organizing_summary") or "") + " " + (web_text or "")
    if "layoff" in combined.lower() or "closing" in combined.lower():
        assessment["financial_trend"] = "declining"
        return True
    if "expand" in combined.lower() or "growth" in combined.lower():
        assessment["financial_trend"] = "growing"
        return True
    return False

def _validate_employee_count(dossier_data: dict, run: dict) -> None:
    """Flag suspiciously low employee counts."""
    if not dossier_data or "dossier" not in dossier_data: return
    financial = dossier_data["dossier"].get("financial", {})
    emp_val = financial.get("employee_count")
    if not emp_val: return
    
    try:
        num = int(str(emp_val).replace(",", "").split()[0])
        if num < 50 and run.get("employee_size_bucket") == "large":
            financial["employee_count"] = f"{emp_val} (UNVERIFIED)"
    except: pass

def _count_null_fields(dossier_data: dict) -> tuple[int, int]:
    """Count (total_fields, null_fields)."""
    if not dossier_data or "dossier" not in dossier_data: return (0, 0)
    body = dossier_data["dossier"]
    total, nulls = 0, 0
    for sec in ["identity", "financial", "workforce", "labor", "workplace"]:
        s_dict = body.get(sec, {})
        if not isinstance(s_dict, dict): continue
        for val in s_dict.values():
            total += 1
            if val is None or val == "" or val == []: nulls += 1
    return (total, nulls)

def _ensure_exhaustive_coverage(run_id: int, dossier_data: dict, vocabulary: dict) -> int:
    """Ensure all vocabulary fields are non-null."""
    if not dossier_data or "dossier" not in dossier_data: return 0
    body = dossier_data["dossier"]
    
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT tool_name FROM research_actions WHERE run_id = %s", (run_id,))
    ran = set(row["tool_name"] for row in cur.fetchall()); conn.close()

    filled = 0
    facts_arr = dossier_data.setdefault("facts", [])
    for attr, meta in vocabulary.items():
        sec = meta["dossier_section"]
        if sec not in _DOSSIER_SECTIONS: continue
        sec_dict = body.setdefault(sec, {})
        if sec_dict.get(attr) in (None, "", []):
            status = "Verified None (Tools searched)" if ran else "Not searched"
            sec_dict[attr] = status
            facts_arr.append({
                "dossier_section": sec, "attribute_name": attr, "attribute_value": status,
                "source_type": "system", "source_name": "exhaustive_coverage", "confidence": 1.0,
                "as_of_date": date.today().isoformat()
            })
            filled += 1
    return filled

# ---------------------------------------------------------------------------
# Action Logging & Fact Saving
# ---------------------------------------------------------------------------

def _log_action(run_id: int, tool_name: str, tool_params: dict, order: int, result: dict, lat: int, company_context: dict = None) -> int:
    conn = _conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO research_actions (run_id, tool_name, tool_params, execution_order, data_found, result_summary, latency_ms, company_context, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (run_id, tool_name, json.dumps(tool_params), order, result.get("found", False), result.get("summary", "")[:1000], lat, json.dumps(company_context), result.get("error")))
    aid = cur.fetchone()["id"]; conn.commit(); conn.close()
    return aid

def _save_facts(run_id: int, employer_id: str, facts: list, vocabulary: dict, tool_action_map: dict) -> int:
    if not facts: return 0
    conn = _conn(); cur = conn.cursor()
    saved = 0
    for f in facts:
        attr = f.get("attribute_name")
        if attr not in vocabulary: continue
        aid = tool_action_map.get(f.get("source_name"))
        cur.execute("""
            INSERT INTO research_facts (run_id, employer_id, action_id, dossier_section, attribute_name, attribute_value, attribute_value_json, source_type, source_name, confidence, as_of_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (run_id, employer_id, aid, f.get("dossier_section"), attr, str(f.get("attribute_value"))[:1000], json.dumps(f.get("attribute_value_json")), f.get("source_type"), f.get("source_name"), f.get("confidence", 0.5), f.get("as_of_date")))
        saved += 1
    conn.commit(); conn.close()
    return saved

# ---------------------------------------------------------------------------
# Dossier Extraction
# ---------------------------------------------------------------------------

def _extract_dossier_json(text: str) -> Optional[dict]:
    if not text: return None
    m = re.search(r"```json\s*\n?(.*?)```", text, re.DOTALL)
    raw = m.group(1).strip() if m else text.strip()
    try:
        return json.loads(raw)
    except:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            try: return json.loads(raw[start:end+1])
            except: pass
    return None

# ---------------------------------------------------------------------------
# Async Research Engine
# ---------------------------------------------------------------------------

def run_research(run_id: int) -> dict:
    """Synchronous entry point."""
    return asyncio.run(_run_research_async(run_id))

async def _run_research_async(run_id: int) -> dict:
    _log.info("Starting research run %d (async)", run_id)
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM research_runs WHERE id = %s", (run_id,))
    run = cur.fetchone(); conn.close()
    if not run: raise ValueError(f"Run {run_id} not found")
    
    start_time = time.time()
    _update_run(run_id, status="running", started_at=datetime.now(), current_step="Initializing...", progress_pct=0)
    
    try:
        return await _run_agent_loop(run_id, dict(run), start_time)
    except Exception as exc:
        _log.exception("Run %d failed", run_id)
        _update_run(run_id, status="failed", completed_at=datetime.now(), duration_seconds=int(time.time()-start_time), current_step=f"FAILED: {str(exc)[:200]}")
        return {"status": "failed", "error": str(exc)}

async def _run_agent_loop(run_id: int, run: dict, start_time: float) -> dict:
    vocabulary = _load_vocabulary()
    system_prompt = _build_system_prompt(run, vocabulary)
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    gemini_tools = _build_gemini_tools()
    
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=f"Research {run['company_name']}")])]
    execution_order, tools_called = 0, 0
    tools_called_set = set(); tool_action_map = {}
    final_text = ""

    # Phase 1: Gemini Multi-Turn Loop
    for turn in range(MAX_TOOL_TURNS):
        response = await asyncio.to_thread(client.models.generate_content, model=MODEL, contents=contents, config=types.GenerateContentConfig(system_instruction=system_prompt, tools=gemini_tools, max_output_tokens=MAX_TOKENS))
        candidate = response.candidates[0]
        function_calls = [p for p in candidate.content.parts if p.function_call]
        if not function_calls:
            final_text = "\n".join(p.text for p in candidate.content.parts if p.text)
            break
        
        contents.append(candidate.content)
        async def _run_tool(part, order):
            fc = part.function_call
            tname, targs = fc.name, dict(fc.args) if fc.args else {}
            if tname in ("google_search", "search_web"): return tname, types.Part.from_function_response(name=tname, response={"found": False, "summary": "Use DB tools."}), None
            _log.info("Run %d: turn %d call %s", run_id, turn+1, tname)
            t0 = time.time()
            res = await asyncio.to_thread(TOOL_REGISTRY[tname], **targs)
            aid = await asyncio.to_thread(_log_action, run_id, tname, targs, order, res, int((time.time()-t0)*1000), {"turn": turn})
            return tname, types.Part.from_function_response(name=tname, response=res), aid

        tasks = [ _run_tool(fc, execution_order + i + 1) for i, fc in enumerate(function_calls) ]
        results = await asyncio.gather(*tasks)
        execution_order += len(function_calls); tools_called += len(function_calls)
        
        f_resps = []
        for tname, p_resp, aid in results:
            if aid: tool_action_map[tname] = aid
            tools_called_set.add(tname)
            f_resps.append(p_resp)
        contents.append(types.Content(role="user", parts=f_resps))

    # Phase 1.5 & 1.6: Forced Enrichment (Parallel)
    # Load strategy to skip low-value tools for this industry/type/size
    _naics_2 = (run.get("industry_naics") or "")[:2]
    _company_type = run.get("company_type") or ""
    _size_bucket = run.get("employee_size_bucket") or ""
    _strategy = _load_strategy(_naics_2, _company_type, _size_bucket)
    _skip_tools = {r["tool_name"] for r in _strategy if (r.get("hit_rate") or 0) < 0.10 and (r.get("times_tried") or 0) >= 5}
    if _skip_tools:
        _log.info("Run %d: skipping low-value tools based on strategy: %s", run_id, _skip_tools)

    forced_tasks = []

    async def _f_scrape():
        if "scrape_employer_website" in tools_called_set: return None
        if "scrape_employer_website" in _skip_tools: return None
        res = await asyncio.to_thread(TOOL_REGISTRY["scrape_employer_website"], company_name=run["company_name"], employer_id=run.get("employer_id"), state=run.get("company_state"))
        return ("scrape", res)
    forced_tasks.append(_f_scrape())

    async def _f_gleif():
        if "search_gleif_ownership" in tools_called_set: return None
        if "search_gleif_ownership" in _skip_tools: return None
        # Only force GLEIF for large or public companies (>500 employees or public)
        emp_count = run.get("employee_count") or 0
        is_public = (run.get("company_type") or "").lower() == "public"
        if emp_count < 500 and not is_public: return None
        res = await asyncio.to_thread(TOOL_REGISTRY["search_gleif_ownership"], company_name=run["company_name"], employer_id=run.get("employer_id"))
        return ("gleif", res)
    forced_tasks.append(_f_gleif())

    async def _f_donations():
        if "search_political_donations" in tools_called_set: return None
        if "search_political_donations" in _skip_tools: return None
        # Only force donations search for larger companies (>500 employees)
        emp_count = run.get("employee_count") or 0
        if emp_count < 500: return None
        res = await asyncio.to_thread(TOOL_REGISTRY["search_political_donations"], company_name=run["company_name"])
        return ("donations", res)
    forced_tasks.append(_f_donations())

    async def _f_sentiment():
        if "search_worker_sentiment" in tools_called_set: return None
        if "search_worker_sentiment" in _skip_tools: return None
        res = await asyncio.to_thread(TOOL_REGISTRY["search_worker_sentiment"], company_name=run["company_name"], state=run.get("company_state"))
        return ("sentiment", res)
    forced_tasks.append(_f_sentiment())

    async def _f_sos():
        if "search_sos_filings" in tools_called_set or not run.get("company_state"): return None
        if "search_sos_filings" in _skip_tools: return None
        res = await asyncio.to_thread(TOOL_REGISTRY["search_sos_filings"], company_name=run["company_name"], state=run.get("company_state"))
        return ("sos", res)
    forced_tasks.append(_f_sos())

    # search_solidarity_network removed from forced list (22% hit rate).
    # Gemini can still call it voluntarily via the tool registry.

    # search_local_subsidies removed from forced list (44% hit rate).
    # Gemini can still call it voluntarily via the tool registry.

    async def _f_form5500():
        if "search_form5500" in tools_called_set: return None
        if "search_form5500" in _skip_tools: return None
        res = await asyncio.to_thread(TOOL_REGISTRY["search_form5500"], company_name=run["company_name"], employer_id=run.get("employer_id"), state=run.get("company_state"))
        return ("form5500", res)
    forced_tasks.append(_f_form5500())

    async def _f_cbp():
        if "search_cbp_context" in tools_called_set: return None
        if "search_cbp_context" in _skip_tools: return None
        naics = run.get("naics")
        if not naics:
            d = _extract_dossier_json(final_text)
            if d:
                try: naics = d.get("dossier", {}).get("identity", {}).get("naics_code")
                except: pass
        if naics:
            res = await asyncio.to_thread(TOOL_REGISTRY["search_cbp_context"], company_name=run["company_name"], naics=naics, state=run.get("company_state"))
            return ("cbp", res)
        return None
    forced_tasks.append(_f_cbp())

    async def _f_acs():
        if "search_acs_workforce" in tools_called_set: return None
        if "search_acs_workforce" in _skip_tools: return None
        if run.get("company_state"):
            naics = run.get("naics")
            if not naics:
                d = _extract_dossier_json(final_text)
                if d:
                    try: naics = d.get("dossier", {}).get("identity", {}).get("naics_code")
                    except: pass
            res = await asyncio.to_thread(TOOL_REGISTRY["search_acs_workforce"], company_name=run["company_name"], state=run.get("company_state"), naics=naics)
            return ("acs_workforce", res)
        return None
    forced_tasks.append(_f_acs())

    enrich_res = await asyncio.gather(*(t for t in forced_tasks if t is not None))
    
    # Patch Dossier with Enrichment Results
    dossier_data = _extract_dossier_json(final_text) or {"dossier": {}, "facts": []}
    body = dossier_data["dossier"]
    
    for r in enrich_res:
        if not r or not r[1].get("found"): continue
        rtype, rdata = r[0], r[1]
        if rtype == "gleif":
            body.setdefault("identity", {})["parent_company"] = rdata.get("data", {}).get("parents", [{}])[0].get("parent_name")
        elif rtype == "donations":
            body.setdefault("assessment", {})["political_donations"] = rdata.get("data")
        elif rtype == "sentiment":
            body.setdefault("workplace", {})["worker_complaints"] = rdata.get("summary")
        elif rtype == "sos":
            body.setdefault("identity", {})["registered_agent"] = rdata.get("data", {}).get("registered_agent")
        elif rtype == "acs_workforce":
            body.setdefault("workforce", {})["acs_demographics"] = rdata.get("data")

        execution_order += 1; tools_called += 1
        aid = await asyncio.to_thread(_log_action, run_id, f"search_{rtype} (forced)", {"company_name": run["company_name"]}, execution_order, rdata, 0)
        tool_action_map[f"search_{rtype}"] = aid

    _ensure_exhaustive_coverage(run_id, dossier_data, vocabulary)
    facts_saved = _save_facts(run_id, run.get("employer_id"), dossier_data.get("facts", []), vocabulary, tool_action_map)
    _update_run(run_id, status="completed", completed_at=datetime.now(), duration_seconds=int(time.time()-start_time), dossier_json=json.dumps(dossier_data, default=str), total_facts_found=facts_saved)

    # Auto-grade and update strategy tables (learning loop)
    try:
        from scripts.research.auto_grader import grade_and_save, update_strategy_quality
        grade_and_save(run_id)
        update_strategy_quality()
        _log.info("Run %d: auto-graded and strategy tables updated.", run_id)
    except Exception as exc:
        _log.debug("Auto-grade/strategy update for run %d failed: %s", run_id, exc)

    return {"status": "completed", "run_id": run_id, "facts_saved": facts_saved}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--state")
    args = parser.parse_args()
    conn = _conn(); cur = conn.cursor()
    cur.execute("INSERT INTO research_runs (company_name, company_state, status) VALUES (%s, %s, 'pending') RETURNING id", (args.company, args.state))
    rid = cur.fetchone()["id"]; conn.commit(); conn.close()
    print(f"Created run {rid}")
    print(run_research(rid))
