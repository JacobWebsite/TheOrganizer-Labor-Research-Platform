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
    "get_industry_profile", "get_similar_employers", "google_search",
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


def _load_vocabulary() -> dict[str, dict]:
    """Load the fact vocabulary into a lookup dict keyed by attribute_name."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM research_fact_vocabulary")
    rows = cur.fetchall()
    conn.close()
    return {r["attribute_name"]: dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Gemini Tool Definitions
# ---------------------------------------------------------------------------

def _build_gemini_tools() -> list[types.Tool]:
    """Convert our TOOL_DEFINITIONS to Gemini FunctionDeclaration format."""
    declarations = []
    for td in TOOL_DEFINITIONS:
        # Skip stubs — web search uses a separate grounding phase,
        # scraper is not yet implemented
        if td["name"] in ("search_web", "scrape_employer_website"):
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

3. **Search the web** for current context (automatic via Google Search):
   - Recent news about the company (layoffs, expansions, lawsuits)
   - Ongoing or recent organizing campaigns, strikes, work stoppages
   - Worker complaints (Glassdoor themes, Reddit, news articles)
   - Company leadership statements about unions
   - Recent NLRB developments not yet in our database

   Search queries to try:
   - "{company_name}" union organizing workers
   - "{company_name}" strike labor dispute
   - "{company_name}" NLRB
   - "{company_name}" layoffs workers 2025 2026

4. **Synthesize** your findings into the dossier.

Always pass the company_name parameter. If the employer_id is known (not "unknown"), pass it too for more precise matching.
If the NAICS is known, pass it to get_industry_profile and get_similar_employers.
If the state is known, pass it where accepted.

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

For the **assessment** section, write original analysis:
- `organizing_summary`: 2-3 paragraph assessment of organizing potential
- `campaign_strengths`: list of key advantages
- `campaign_challenges`: list of key obstacles
- `similar_organized`: list of comparable organized employers
- `recommended_approach`: suggested strategy

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
# Dossier JSON parser
# ---------------------------------------------------------------------------

def _extract_dossier_json(text: str) -> Optional[dict]:
    """Extract the JSON dossier from Gemini's final text response."""
    # Look for ```json ... ``` block (flexible whitespace handling)
    m = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if m:
        json_str = m.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            _log.warning("Failed to parse dossier JSON block: %s", e)

    # Fallback: try to find a raw JSON object containing "dossier"
    for start in range(len(text)):
        if text[start] == '{':
            try:
                obj = json.loads(text[start:])
                if "dossier" in obj:
                    return obj
            except json.JSONDecodeError:
                continue
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

            # Execute the tool
            t0 = time.time()
            if tool_name == "google_search":
                # Gemini sometimes emits google_search as a function call
                # even though it's not in our declarations. Handle gracefully —
                # actual web search happens in Phase 2 (grounding).
                result = {
                    "found": True, "source": "google_search",
                    "summary": "Web search will be performed in the grounding phase.",
                    "data": {},
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

            # Log to database
            _log_action(
                run_id, tool_name, tool_input, execution_order,
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

    try:
        web_prompt = (
            f"You are a labor-relations research agent. You have already queried internal databases "
            f"for **{run['company_name']}** and produced a preliminary dossier.\n\n"
            f"Now search the web for current context to enrich the assessment. Look for:\n"
            f"- Recent news about {run['company_name']} (layoffs, expansions, lawsuits, M&A)\n"
            f"- Ongoing or recent union organizing campaigns, strikes, work stoppages\n"
            f"- Worker complaints, Glassdoor reviews themes, Reddit discussions\n"
            f"- Company leadership statements about unions or labor relations\n"
            f"- Recent NLRB filings or rulings not yet in government databases\n\n"
            f"Return your findings as a JSON code block:\n"
            f"```json\n"
            f'{{"web_findings": {{\n'
            f'  "recent_news": ["headline or summary (source, date)", ...],\n'
            f'  "organizing_activity": ["description (source, date)", ...],\n'
            f'  "worker_sentiment": ["theme or quote (source)", ...],\n'
            f'  "company_context": "1-2 paragraph summary of what web sources reveal",\n'
            f'  "sources_consulted": ["url or source name", ...]\n'
            f"}}}}\n"
            f"```\n\n"
            f"If you find nothing relevant, return empty lists. Be specific with dates and sources."
        )

        web_response = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=web_prompt)],
            )],
            config=types.GenerateContentConfig(
                tools=_build_google_search_tool(),
                max_output_tokens=8192,
            ),
        )

        # Track token usage from web search phase
        if web_response.usage_metadata:
            total_input_tokens += web_response.usage_metadata.prompt_token_count or 0
            total_output_tokens += web_response.usage_metadata.candidates_token_count or 0

        web_candidate = web_response.candidates[0]
        web_text = "\n".join(
            p.text for p in web_candidate.content.parts if p.text
        )

        # Log grounding metadata
        grounding_meta = getattr(web_candidate, 'grounding_metadata', None)
        search_queries_used = []
        if grounding_meta:
            search_queries_used = getattr(grounding_meta, 'web_search_queries', []) or []
            grounding_chunks = getattr(grounding_meta, 'grounding_chunks', []) or []
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

        # Save original dossier text before appending web findings.
        # If the merge phase fails, we fall back to this clean version.
        original_final_text = final_text

        if web_text.strip():
            final_text += "\n\n--- WEB SEARCH FINDINGS ---\n" + web_text
            _log.info("Run %d: web search returned %d chars", run_id, len(web_text))
        else:
            _log.info("Run %d: web search returned no text", run_id)

    except Exception as web_exc:
        _log.warning("Run %d: web search phase failed (non-fatal): %s", run_id, web_exc)
        original_final_text = final_text  # no web findings appended

    # ------------------------------------------------------------------
    # Phase 3: Merge web findings into the dossier via patch
    # ------------------------------------------------------------------
    # Instead of asking Gemini to reproduce the entire dossier JSON (which
    # fails on large dossiers), we ask for a small PATCH object and apply
    # it ourselves.  This is cheaper, faster, and more reliable.
    web_findings_text = ""
    if "--- WEB SEARCH FINDINGS ---" in final_text:
        web_findings_text = final_text.split("--- WEB SEARCH FINDINGS ---", 1)[1]
        final_text = original_final_text  # always parse from clean original

    if web_findings_text.strip():
        _progress(run_id, "Merging web findings into dossier...", 84)
        try:
            patch_prompt = (
                f"Below are web search findings about **{run['company_name']}**.\n\n"
                f"Based on these findings, produce a JSON patch object with ONLY the "
                f"new or updated content to merge into an existing dossier. Format:\n\n"
                f"```json\n"
                f'{{\n'
                f'  "assessment_additions": {{\n'
                f'    "organizing_summary_addendum": "1-2 paragraphs of web-sourced context to append",\n'
                f'    "additional_strengths": ["strength from web..."],\n'
                f'    "additional_challenges": ["challenge from web..."]\n'
                f'  }},\n'
                f'  "web_facts": [\n'
                f'    {{"dossier_section": "...", "attribute_name": "...", "attribute_value": "...", '
                f'"source_type": "web", "source_name": "...", "confidence": 0.7, "as_of_date": "..."}}\n'
                f'  ],\n'
                f'  "web_sources": ["source description (url, date)", ...]\n'
                f'}}\n'
                f"```\n\n"
                f"Web findings:\n{web_findings_text[:12000]}"
            )

            patch_response = client.models.generate_content(
                model=MODEL,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=patch_prompt)],
                )],
                config=types.GenerateContentConfig(
                    max_output_tokens=8192,
                ),
            )

            if patch_response.usage_metadata:
                total_input_tokens += patch_response.usage_metadata.prompt_token_count or 0
                total_output_tokens += patch_response.usage_metadata.candidates_token_count or 0

            patch_text = "\n".join(
                p.text for p in patch_response.candidates[0].content.parts if p.text
            )
            _log.info("Run %d: patch response length=%d, first 200=%s",
                       run_id, len(patch_text), repr(patch_text[:200]))

            # Extract any JSON from the patch response (not _extract_dossier_json
            # which requires a "dossier" key).
            patch_data = None
            # Try ```json ... ``` block (allow optional whitespace/newline after ```)
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", patch_text, re.DOTALL)
            if m:
                try:
                    patch_data = json.loads(m.group(1).strip())
                except json.JSONDecodeError as e:
                    _log.warning("Run %d: patch JSON parse error: %s", run_id, e)
            if not patch_data:
                # Try raw JSON parse
                for i, ch in enumerate(patch_text):
                    if ch == '{':
                        try:
                            patch_data = json.loads(patch_text[i:])
                            break
                        except json.JSONDecodeError:
                            continue

            if patch_data and isinstance(patch_data, dict):
                # Parse the original dossier
                original_dossier = _extract_dossier_json(final_text)
                if original_dossier and "dossier" in original_dossier:
                    dossier_body = original_dossier["dossier"]
                    assessment = dossier_body.get("assessment", {})

                    # Apply assessment additions
                    additions = patch_data.get("assessment_additions", {})
                    addendum = additions.get("organizing_summary_addendum", "")
                    if addendum and assessment.get("organizing_summary"):
                        assessment["organizing_summary"] += "\n\n" + addendum
                    elif addendum:
                        assessment["organizing_summary"] = addendum

                    for s in additions.get("additional_strengths", []):
                        assessment.setdefault("campaign_strengths", []).append(s)
                    for c in additions.get("additional_challenges", []):
                        assessment.setdefault("campaign_challenges", []).append(c)

                    dossier_body["assessment"] = assessment

                    # Add web sources
                    sources_sec = dossier_body.get("sources", {})
                    for ws in patch_data.get("web_sources", []):
                        sources_sec.setdefault("source_list", []).append(
                            {"tool": "web_search", "summary": ws}
                        )
                    dossier_body["sources"] = sources_sec

                    # Add web facts to the facts array
                    for wf in patch_data.get("web_facts", []):
                        wf["source_type"] = "web"
                        original_dossier.setdefault("facts", []).append(wf)

                    # Re-serialize the patched dossier as the final text
                    final_text = "```json\n" + json.dumps(original_dossier, indent=2, default=str) + "\n```"
                    _log.info("Run %d: successfully patched dossier with web findings", run_id)
                else:
                    _log.warning("Run %d: could not parse original dossier for patching", run_id)
            else:
                _log.warning("Run %d: web patch produced no usable data", run_id)

        except Exception as merge_exc:
            _log.warning("Run %d: web merge phase failed (non-fatal): %s", run_id, merge_exc)

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
