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
import time
import asyncio
from datetime import datetime, date
from typing import Optional

from google import genai
from google.genai import types

from scripts.research.tools import TOOL_REGISTRY, TOOL_DEFINITIONS, _conn

# Configuration
MODEL = os.environ.get("RESEARCH_AGENT_MODEL", "gemini-2.5-flash")
MAX_TOOL_TURNS = int(os.environ.get("RESEARCH_AGENT_MAX_TURNS", 25))
MAX_TOKENS = int(os.environ.get("RESEARCH_AGENT_MAX_TOKENS", 65536))
# Iterative critique loop: number of rounds and per-round timeout (seconds).
# Each round = 1 Gemini critique call + up to 5 parallel tool calls.
CRITIQUE_ROUNDS = int(os.environ.get("RESEARCH_CRITIQUE_ROUNDS", 3))
CRITIQUE_ROUND_TIMEOUT_S = int(os.environ.get("RESEARCH_CRITIQUE_ROUND_TIMEOUT_S", 120))

_INPUT_COST_PER_1K = 0.003  # $0.30 per 1M
_OUTPUT_COST_PER_1K = 0.025  # $2.50 per 1M

_log = logging.getLogger("research.agent")

_DOSSIER_SECTIONS = [
    "identity",
    "corporate_structure",
    "locations",
    "leadership",
    "financial",
    "workforce",
    "labor",
    "workplace",
    "assessment",
    "sources",
    "adaptive_findings",
]

_INTERNAL_TOOLS = [
    "search_osha", "search_nlrb", "search_whd", "search_sec",
    "search_sam", "search_990", "search_contracts", "search_mergent",
    "search_sec_proxy", "search_job_postings", "get_workforce_demographics",
    "get_industry_profile", "get_similar_employers",
    "scrape_employer_website", "google_search",
    "search_worker_sentiment", "search_sos_filings", "compare_industry_wages",
    "search_solidarity_network", "search_local_subsidies",
    "search_acs_workforce",
    "search_local_union_density",
    "search_corporate_structure",
    "search_employer_locations",
    "search_leadership",
    "search_state_enforcement",
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

_SECTION_QUERY_TEMPLATES = {
    "financial": [
        '"{company}" revenue annual report {year}',
        '"{company}" employee count headcount {year}',
    ],
    "leadership": [
        '"{company}" CEO executive team management',
        '"{company}" leadership officers directors {state}',
    ],
    "corporate_structure": [
        '"{company}" parent company owner subsidiary',
        '"{company}" acquired merger acquisition {year}',
    ],
    "workplace": [
        '"{company}" worker complaints safety violations {state}',
        '"{company}" working conditions employee reviews',
    ],
    "labor": [
        '"{company}" union organizing NLRB election',
        '"{company}" labor relations collective bargaining {state}',
    ],
    "workforce": [
        '"{company}" jobs hiring employees {state} {year}',
    ],
    "identity": [
        '"{company}" company profile industry {state}',
    ],
}

_TOOL_GAP_MAP = {
    "search_mergent": ["employee_count", "revenue", "website_url"],
    "search_990": ["nonprofit_financials", "employee_count"],
    "search_osha": ["osha_violations"],
    "search_nlrb": ["nlrb_activity"],
    "search_whd": ["whd_violations"],
}

# --------------------------------------------------------------------------
# Per-archetype query overrides (Session 6a, 2026-04-24)
# --------------------------------------------------------------------------
# Appends / replaces base templates based on the employer's `company_type`.
# Matches the classifications emitted by the scorecard + managed-agents
# pipelines. Keys line up with `research_query_effectiveness.company_type`.
#
# Philosophy:
# - Public SEC filers get SEC-proxy and 10-K queries, skip generic Google
# - Nonprofits skip SEC entirely, add 990 and GuideStar queries
# - Municipal employers skip NLRB (use state PERB/SERB), add state audit
#   + city council queries
_ARCHETYPE_QUERY_OVERRIDES = {
    "public_sec": {
        "revenue": [
            '"{company}" SEC 10-K annual report {year}',
            '"{company}" 10-Q earnings revenue {year}',
            '"{company}" investor relations financial results',
        ],
        "employee_count": [
            '"{company}" SEC 10-K employees headcount {year}',
            '"{company}" proxy DEF14A officers compensation',
        ],
        "leadership": [
            '"{company}" CEO executive compensation DEF14A proxy',
            '"{company}" board of directors SEC filing',
        ],
    },
    "nonprofit": {
        "revenue": [
            '"{company}" Form 990 revenue {year}',
            '"{company}" GuideStar ProPublica nonprofit explorer',
            '"{company}" nonprofit annual report {year}',
        ],
        "employee_count": [
            '"{company}" Form 990 Schedule J compensation {year}',
            '"{company}" 990 Part IX functional expenses',
        ],
        "nonprofit_financials": [
            '"{company}" 990 Schedule D Schedule J {year}',
            '"{company}" nonprofit Form 990 GuideStar ProPublica',
        ],
    },
    "municipal": {
        "nlrb_activity": [
            '"{company}" PERB SERB public employment relations {state}',
            '"{company}" AFSCME SEIU public-sector union {state}',
            '"{company}" bargaining unit municipal state {year}',
        ],
        "whd_violations": [
            '"{company}" state audit Auditor "{state}"',
            '"{company}" city council budget audit report',
        ],
        "recent_news": [
            '"{company}" city council meeting minutes {year}',
            '"{company}" budget layoffs service cuts {year}',
        ],
    },
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

def _pick_templates(gap_key: str, company_type: Optional[str]) -> list[str]:
    """Resolve the template list for a gap, applying per-archetype overrides.

    Resolution order:
      1. Learned templates from research_query_effectiveness (_get_best_queries)
      2. Archetype-specific overrides for this company_type (if any)
      3. Base templates in _GAP_QUERY_TEMPLATES
    """
    learned = _get_best_queries(gap_key, company_type)
    if learned:
        return learned
    ct = (company_type or "").strip().lower()
    archetype = _ARCHETYPE_QUERY_OVERRIDES.get(ct, {})
    if gap_key in archetype:
        return archetype[gap_key]
    return _GAP_QUERY_TEMPLATES.get(gap_key, [])


def _build_web_search_queries(company_name: str, company_type: Optional[str],
                               company_state: Optional[str],
                               db_gaps: list[str],
                               year: str = None,
                               company_address: Optional[str] = None,
                               weak_sections: Optional[list[str]] = None) -> list[str]:
    """Build targeted search queries based on which DB tools missed and weak dossier sections.

    Applies per-archetype overrides (Session 6a) + time-boxing of recency-
    sensitive gap types (Session 6b). For recent_news / nlrb_activity /
    whd_violations the rendered query always includes the current year + the
    prior year so we catch same-day filings and last-quarter events without
    relying on the template author remembering to stamp `{year}`.
    """
    if year is None:
        year = str(datetime.now().year)
    prior_year = str(int(year) - 1)
    queries = []
    gap_types_used = []

    # Priority 1: Gap-targeted queries for weak dossier sections
    if weak_sections:
        for sec in weak_sections:
            templates = _SECTION_QUERY_TEMPLATES.get(sec, [])
            for t in templates[:2]:
                queries.append((t, f"section_{sec}"))

    # Priority 2: Tool-gap queries, with archetype awareness
    for tool_name in db_gaps:
        for gap_key in _TOOL_GAP_MAP.get(tool_name, []):
            templates = _pick_templates(gap_key, company_type)
            for t in templates[:2]:
                queries.append((t, gap_key))

    # Priority 3: Always-run queries (news, labor, conditions)
    for key in ["recent_news", "labor_stance", "worker_conditions"]:
        templates = _pick_templates(key, company_type)
        for t in templates[:1]:
            queries.append((t, key))

    # Time-boxing suffix for recency-sensitive gap types. Adds the current +
    # prior year to the query string so the search engine surfaces fresh hits
    # even when the template doesn't stamp `{year}` itself.
    _TIME_BOXED_GAPS = {"recent_news", "nlrb_activity", "whd_violations", "section_workplace", "section_labor"}

    filled: list[str] = []
    gap_types_aligned: list[tuple[str, str]] = []
    for q, gap_key in queries:
        try:
            rendered = q.format(
                company=company_name,
                state=company_state or "",
                year=year,
                address=company_address or "",
            )
        except (KeyError, IndexError):
            rendered = q.format(
                company=company_name,
                state=company_state or "",
                year=year,
            )
        # Append year disjunction for time-boxed gap types unless the template
        # already stamped the current year (we don't want e.g. "2026 2026 OR 2025").
        if gap_key in _TIME_BOXED_GAPS and year not in rendered:
            rendered = f"{rendered} {year} OR {prior_year}"
        filled.append(rendered)
        # `_update_query_effectiveness` expects (gap_key, template) tuples;
        # `template` is the raw (un-rendered) template for learning stability
        # across company-name swaps. See scripts/research/agent.py:297.
        gap_types_aligned.append((gap_key, q))

    return filled[:15], gap_types_aligned[:15]

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
            ORDER BY recommended_order ASC NULLS LAST
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
    website_url = run.get("website_url") or "unknown"

    prompt = f"""You are a labor-relations research agent. Your job is to compile a comprehensive organizing dossier on a single employer by querying internal databases.

## Company Under Research
- **Name:** {company_name}
- **Address:** {company_address}
- **Employer ID (internal):** {employer_id}
- **NAICS:** {naics}
- **Type:** {company_type}
- **State:** {state}
- **Size bucket:** {size_bucket}
- **Website:** {website_url}

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
   - Company Enrich (search_company_enrich) -- ALWAYS call this early. Returns employee count range, revenue range, website, LinkedIn, founding year, industry, company type. Covers 30M+ companies including private. Pass domain if known from other tools for better match accuracy.

2. **Get industry and local context:**
   - BLS industry profile (get_industry_profile) -- needs a NAICS code. Now includes CBP local establishment counts if state is provided.
   - Similar organized employers (get_similar_employers)
   - Local demographics (search_local_demographics) -- Call if city and state are known. Returns population, race, and income context. (Note: ACS tool below is preferred.)
   - Taxpayer Subsidies (search_local_subsidies) -- Call if relevant to the employer. Returns local tax breaks and grants.
   - CBP industry context (search_cbp_context) -- ALWAYS call this if NAICS is known. Returns local establishment counts, employment, and avg wages.
   - LODES workforce data (search_lodes_workforce) -- Call if state/county is known. Returns job counts, earnings tiers, and industry mix.
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
   - Brave Web Search (search_brave_web) -- Use for targeted factual queries (recent news, WARN notices, leadership names). Returns structured URLs and descriptions with traceable queries.

4. **Scrape employer website** (scrape_employer_website) -- if search_mergent returned a website URL, pass it here. Otherwise the tool will look it up. Returns homepage, about, careers, and news text.

5. **Synthesize** your findings into the dossier.

6. **Populate the new dossier sections:**
   - **corporate_structure**: parent company, parent type (public/private/PE/nonprofit), known subsidiaries, investors, corporate family context. Use data from search_gleif_ownership, search_sec, search_mergent, search_solidarity_network. If no parent found, note "Appears to be an independent company."
   - **locations**: all known employer addresses from OSHA establishments, SAM entities, SOS filings, and web scrape. Group by city/state. Include establishment counts per location if available.
   - **leadership**: CEO/president, executive team, local management. Source from search_sos_filings (officers/directors), search_sec (for public companies), and web scrape of "about us" / "leadership" pages.

7. **Flag adaptive findings:** If you discover something important that does NOT fit the standard 10 sections -- such as pending acquisitions, store closures, major lawsuits, private equity involvement, regulatory actions, or industry disruption -- add it to the "adaptive_findings" section. Each finding should have: "finding" (what you discovered), "significance" (why it matters for organizing), "source" (where you found it). This section captures critical intelligence that the template was not designed for.

IMPORTANT: Do NOT call `google_search` directly -- web search is handled separately after your database queries. But DO call all tools listed in steps 1-4 above.

Return your final report as a JSON object inside a code block. Your response must be parseable JSON with this structure:
{{
  "dossier": {{
    "identity": {{ ... }},
    "corporate_structure": {{ ... }},
    "locations": {{ ... }},
    "leadership": {{ ... }},
    "financial": {{ ... }},
    "workforce": {{ ... }},
    "labor": {{ ... }},
    "workplace": {{ ... }},
    "assessment": {{ ... }},
    "sources": {{ ... }},
    "adaptive_findings": {{ ... }}
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

## Confidence Scoring Rules
Assign confidence using this scale:
- 1.00: Official government records from our database (OSHA citations, NLRB cases, WHD findings, SEC filings, SAM.gov)
- 0.90: Structured third-party data (Mergent, IRS 990, BLS, Form 5500, CompanyEnrich)
- 0.75: Company's own website or official filings (About page, annual report, careers page)
- 0.60: News articles, press releases, job posting aggregators. Single web source.
- 0.40: Inferred or estimated values (industry averages, ranges, educated guesses)
- 0.20: Unverified claims from anonymous sources (Reddit, Glassdoor reviews)

Do NOT default to 0.9 or 1.0. Most web-sourced facts should be 0.60-0.75.
Database tool results should be 0.90-1.00. Your own analysis/assessment fields should be 0.50-0.70.
"""
    # Inject strategy section if available
    naics_2 = (run.get("industry_naics") or "")[:2]
    company_type = run.get("company_type") or ""
    size_bucket = run.get("employee_size_bucket") or ""
    strategy = _load_strategy(naics_2, company_type, size_bucket)
    strategy_section = _build_strategy_prompt_section(strategy)
    if strategy_section:
        prompt += strategy_section

    # Inject few-shot examples from gold-standard dossiers (Session 6d).
    # Pedagogical signal only: shows the agent what a high-quality dossier
    # Bottom Line + Data Quality Notes + citation density look like. The
    # agent's OWN output is still JSON (dossier + facts), but the dossier
    # structure + citation discipline transfers.
    try:
        few_shot = _build_few_shot_examples(run.get("company_type"))
        if few_shot:
            prompt += few_shot
    except Exception:
        pass

    return prompt


# Module-level cache so we don't pull from DB on every run.
_FEW_SHOT_CACHE: dict[str, str] = {}


def _build_few_shot_examples(company_type: Optional[str], n: int = 2) -> str:
    """Return a compact prompt section with 2 gold-standard dossier excerpts.

    The agent learns the output format + citation discipline, NOT the
    content. Each example is truncated so the total injection stays under
    ~3KB of prompt text. We pick diverse archetypes (thin-data small
    employer + data-rich public company + municipal if possible), prefering
    gold_standard rows with the widest range of sources_count.

    Cached per-company_type for the lifetime of the process.
    """
    cache_key = (company_type or "").lower() or "__default__"
    if cache_key in _FEW_SHOT_CACHE:
        return _FEW_SHOT_CACHE[cache_key]

    conn = _conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT company_name, sections_filled, total_facts_found,
                   dossier_json->'metadata'->>'gap_cell' AS gap_cell,
                   dossier_json->'metadata'->>'headline_finding' AS headline_finding,
                   LEFT(dossier_json->>'markdown_body', 900) AS markdown_snippet
            FROM research_runs
            WHERE is_gold_standard = TRUE
              AND dossier_json IS NOT NULL
              AND sections_filled >= 10
            ORDER BY total_facts_found DESC
            LIMIT %s
            """,
            (n,),
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    if not rows:
        _FEW_SHOT_CACHE[cache_key] = ""
        return ""

    parts = [
        "",
        "## Example Gold-Standard Dossier Excerpts (for format + citation-density reference only)",
        "",
        "The following are condensed excerpts from gold-standard dossiers in our `research_runs` "
        "table. They illustrate the expected tone, section structure, and citation density. "
        "Your own output is JSON (dossier + facts) -- match the rigor, not the prose verbatim.",
    ]
    for i, row in enumerate(rows, 1):
        name = row["company_name"] if isinstance(row, dict) else row[0]
        sections = row["sections_filled"] if isinstance(row, dict) else row[1]
        cites = row["total_facts_found"] if isinstance(row, dict) else row[2]
        gap_cell = row["gap_cell"] if isinstance(row, dict) else row[3]
        headline = row["headline_finding"] if isinstance(row, dict) else row[4]
        snippet = row["markdown_snippet"] if isinstance(row, dict) else row[5]
        snippet = (snippet or "").strip()[:600]
        parts.append("")
        parts.append(f"### EXAMPLE_{i}: {name}")
        if gap_cell:
            parts.append(f"- Archetype: {gap_cell}")
        parts.append(f"- Sections filled: {sections} / Citations: {cites}")
        if headline:
            parts.append(f"- Headline finding: {headline[:400]}")
        if snippet:
            parts.append("- Excerpt:")
            parts.append("```")
            parts.append(snippet)
            parts.append("```")
    result = "\n".join(parts)
    _FEW_SHOT_CACHE[cache_key] = result
    return result

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


def _build_dossier_schema(vocabulary: dict) -> types.Schema:
    """Build a Gemini response_schema from the vocabulary table.

    Groups vocabulary entries by dossier_section, builds an OBJECT schema
    per section with STRING properties for each vocabulary attribute_name.
    Used with response_mime_type='application/json' to force structured output.
    """
    by_section: dict[str, list[str]] = {}
    for attr_name, meta in vocabulary.items():
        sec = meta["dossier_section"]
        by_section.setdefault(sec, []).append(attr_name)

    section_schemas = {}
    for sec in _DOSSIER_SECTIONS:
        if sec == "adaptive_findings":
            section_schemas[sec] = types.Schema(
                type="ARRAY",
                items=types.Schema(type="OBJECT", properties={
                    "finding": types.Schema(type="STRING"),
                    "significance": types.Schema(type="STRING"),
                    "source": types.Schema(type="STRING"),
                }),
            )
        elif sec in by_section:
            props = {attr: types.Schema(type="STRING", nullable=True) for attr in by_section[sec]}
            section_schemas[sec] = types.Schema(type="OBJECT", properties=props)
        else:
            section_schemas[sec] = types.Schema(type="OBJECT")

    fact_schema = types.Schema(type="OBJECT", properties={
        "dossier_section": types.Schema(type="STRING"),
        "attribute_name": types.Schema(type="STRING"),
        "attribute_value": types.Schema(type="STRING", nullable=True),
        "source_type": types.Schema(type="STRING"),
        "source_name": types.Schema(type="STRING"),
        "confidence": types.Schema(type="NUMBER"),
        "as_of_date": types.Schema(type="STRING", nullable=True),
    }, required=["dossier_section", "attribute_name", "attribute_value",
                 "source_type", "confidence"])

    return types.Schema(type="OBJECT", properties={
        "dossier": types.Schema(type="OBJECT", properties=section_schemas),
        "facts": types.Schema(type="ARRAY", items=fact_schema),
    }, required=["dossier", "facts"])


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

def _string_similarity(a: str, b: str) -> float:
    """Bigram Jaccard similarity (0.0-1.0). No external deps."""
    if not a or not b:
        return 0.0
    ba = set(a[i:i + 2] for i in range(len(a) - 1))
    bb = set(b[i:i + 2] for i in range(len(b) - 1))
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


_NUMERIC_ATTRS = {
    "employee_count", "revenue", "osha_violation_count",
    "osha_serious_count", "whd_case_count", "nlrb_ulp_count",
    "federal_obligations",
}

_SKIP_VALUES = {
    "-", "none", "null", "verified none (tools searched)",
    "not found (searched)", "not searched",
}


def _find_contradictions(facts_by_attr: dict[str, list[dict]]) -> list[tuple[int, int]]:
    """Core contradiction logic shared by within-run and cross-run detection.

    Returns list of (fact_id_to_flag, contradicts_id) tuples.
    """
    to_flag: list[tuple[int, int]] = []

    for attr, facts in facts_by_attr.items():
        if len(facts) < 2:
            continue

        if attr in _NUMERIC_ATTRS:
            nums = []
            for f in facts:
                val = f.get("attribute_value")
                if val is None:
                    continue
                cleaned = re.sub(r'[^\d.]', '', str(val).split()[0].replace(',', ''))
                try:
                    n = float(cleaned) if cleaned else None
                except ValueError:
                    n = None
                if n is not None and n > 0:
                    nums.append((n, f))
            if len(nums) >= 2:
                nums.sort(key=lambda x: x[0])
                min_val, min_fact = nums[0]
                max_val, max_fact = nums[-1]
                if min_val > 0 and (max_val / min_val) > 1.5:
                    newer = max_fact if max_fact["id"] > min_fact["id"] else min_fact
                    older = min_fact if newer is max_fact else max_fact
                    to_flag.append((newer["id"], older["id"]))
        else:
            # String comparison with fuzzy matching
            seen_vals: list[tuple[str, dict]] = []
            for f in facts:
                val = str(f.get("attribute_value") or "").strip().lower()
                if not val or val in _SKIP_VALUES:
                    continue
                is_duplicate = False
                for existing_val, _existing_fact in seen_vals:
                    if val == existing_val or _string_similarity(val, existing_val) > 0.90:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    seen_vals.append((val, f))
            if len(seen_vals) >= 2:
                ordered = sorted([f for _, f in seen_vals], key=lambda x: x["id"])
                older = ordered[0]
                for newer in ordered[1:]:
                    to_flag.append((newer["id"], older["id"]))

    return to_flag


def _resolve_contradictions(run_id: int) -> int:
    """Detect and flag contradictions among facts for a research run.

    For numeric attributes: if max/min > 1.5, flag the newer fact.
    For string attributes: flag if different values (fuzzy similarity <= 0.90).

    Returns the count of contradictions flagged.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, attribute_name, attribute_value FROM research_facts WHERE run_id = %s ORDER BY id",
        (run_id,),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return 0

    by_attr: dict[str, list[dict]] = {}
    for r in rows:
        by_attr.setdefault(r["attribute_name"], []).append(dict(r))

    to_flag = _find_contradictions(by_attr)

    if not to_flag:
        return 0

    conn = _conn()
    cur = conn.cursor()
    for fact_id, contradicts_id in to_flag:
        cur.execute(
            "UPDATE research_facts SET contradicts_fact_id = %s WHERE id = %s AND contradicts_fact_id IS NULL",
            (contradicts_id, fact_id),
        )
    conn.commit()
    conn.close()
    return len(to_flag)


def _resolve_cross_run_contradictions(employer_id: str, run_id: int) -> int:
    """Detect contradictions between the current run and the most recent prior run
    for the same employer. Returns count of contradictions flagged."""
    conn = _conn()
    cur = conn.cursor()
    # Find the most recent prior completed run for this employer
    cur.execute(
        "SELECT id FROM research_runs "
        "WHERE employer_id = %s AND status = 'completed' AND id != %s "
        "ORDER BY completed_at DESC LIMIT 1",
        (employer_id, run_id),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return 0
    prior_run_id = row["id"]

    # Fetch facts from both runs
    cur.execute(
        "SELECT id, attribute_name, attribute_value, run_id FROM research_facts "
        "WHERE run_id IN (%s, %s) AND source_name != 'exhaustive_coverage' ORDER BY id",
        (run_id, prior_run_id),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return 0

    # Group by attribute, but only include attrs that appear in BOTH runs
    by_attr: dict[str, list[dict]] = {}
    for r in rows:
        by_attr.setdefault(r["attribute_name"], []).append(dict(r))

    # Filter to attrs present in both runs
    cross_attrs: dict[str, list[dict]] = {}
    for attr, facts in by_attr.items():
        run_ids_present = {f["run_id"] for f in facts}
        if run_id in run_ids_present and prior_run_id in run_ids_present:
            cross_attrs[attr] = facts

    to_flag = _find_contradictions(cross_attrs)

    if not to_flag:
        return 0

    conn = _conn()
    cur = conn.cursor()
    for fact_id, contradicts_id in to_flag:
        cur.execute(
            "UPDATE research_facts SET contradicts_fact_id = %s WHERE id = %s AND contradicts_fact_id IS NULL",
            (contradicts_id, fact_id),
        )
    conn.commit()
    conn.close()
    return len(to_flag)

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

def _assess_coverage(dossier_data: dict) -> tuple[float, list[str]]:
    """Assess dossier coverage. Returns (coverage_pct, list_of_weak_sections).

    A section is 'weak' if less than 50% of its fields are filled.
    """
    _body = dossier_data.get("dossier", {})
    filled_total, field_total = 0, 0
    weak = []
    _null_vals = {"", "null", "None", "none"}
    for sec in ["identity", "financial", "workforce", "labor", "workplace",
                 "leadership", "corporate_structure", "assessment"]:
        sec_dict = _body.get(sec, {})
        if not isinstance(sec_dict, dict):
            continue
        sec_filled, sec_total = 0, 0
        for v in sec_dict.values():
            sec_total += 1
            if v is not None and str(v).strip() not in _null_vals:
                sec_filled += 1
        filled_total += sec_filled
        field_total += sec_total
        if sec_total > 0 and (sec_filled / sec_total) < 0.5:
            weak.append(sec)
    pct = (filled_total / max(field_total, 1)) * 100
    return pct, weak


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
        sec_val = body.get(sec)
        # Skip sections that are lists (e.g., adaptive_findings) -- not dict-based
        if isinstance(sec_val, list):
            continue
        sec_dict = body.setdefault(sec, {})
        if not isinstance(sec_dict, dict):
            continue
        if sec_dict.get(attr) in (None, "", []):
            status = "Not found (searched)" if ran else "Not searched"
            sec_dict[attr] = status
            facts_arr.append({
                "dossier_section": sec, "attribute_name": attr, "attribute_value": status,
                "source_type": "system", "source_name": "exhaustive_coverage", "confidence": 0.10,
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

def _resolve_action_id(source_name: str | None, tool_action_map: dict) -> int | None:
    """Resolve a fact's source_name to an action_id with three strategies.

    Historical facts are 89% NULL on action_id (6,226 rows / 661 with id) -- a
    direct consequence of the LLM returning source_name strings like 'OSHA
    database' or 'company website' that never match the tool_action_map keys
    (search_osha, scrape_employer_website, etc.). Strategies, in order:

    1. Exact match (the original behavior).
    2. Substring match: any tool name appearing inside source_name (case-
       insensitive). Catches 'search_osha tool' / 'OSHA via search_osha'.
    3. Reverse substring: source_name appearing inside a tool name. Catches
       'OSHA' -> search_osha, 'NLRB' -> search_nlrb.

    Returns None if nothing matches; the caller decides whether to skip or
    log+save based on REQUIRE_FACT_ACTION_ID.
    """
    if not source_name or not tool_action_map:
        return None
    aid = tool_action_map.get(source_name)
    if aid is not None:
        return aid
    # Normalize separators so 'CompanyEnrich' matches 'search_company_enrich':
    # strip non-alphanumerics from both sides, and strip the 'search'/'get'/
    # 'scrape'/'compare' tool-name prefixes that the LLM almost always omits
    # when naming a source.
    def _alnum(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum())

    def _strip_prefix(s: str) -> str:
        for pfx in ("search", "get", "scrape", "compare"):
            if s.startswith(pfx) and len(s) > len(pfx):
                return s[len(pfx):]
        return s

    src_alnum = _strip_prefix(_alnum(source_name))
    if not src_alnum:
        return None
    # Strategy 2: tool key (prefix-stripped, alnum) appears inside source_name.
    # Catches 'OSHA via search_osha tool', 'CompanyEnrich response'.
    for tname, tid in tool_action_map.items():
        if not tname:
            continue
        tkey = _strip_prefix(_alnum(tname))
        if tkey and tkey in src_alnum:
            return tid
    # Strategy 3: source_name appears inside a tool key. Catches the LLM
    # emitting bare 'osha' / 'nlrb' / 'whd'. Three-char floor avoids
    # meaningless two-char matches.
    if len(src_alnum) >= 3:
        for tname, tid in tool_action_map.items():
            if not tname:
                continue
            tkey = _strip_prefix(_alnum(tname))
            if tkey and src_alnum in tkey:
                return tid
    return None


def _save_facts(run_id: int, employer_id: str, facts: list, vocabulary: dict, tool_action_map: dict) -> int:
    """Persist facts to research_facts.

    Uses a PostgreSQL SAVEPOINT per row so a single bad insert does not
    roll back the earlier successful inserts in the same connection.
    Before this change, a `conn.rollback()` inside the loop silently
    undid every successful row up to that point while the `saved` counter
    kept incrementing -- so `total_facts_found` could report many facts
    that were no longer in the table.

    Action-id traceability (2026-05-03): every fact should be tied to the
    tool action that produced it. _resolve_action_id() now applies three
    matching strategies (exact / substring / reverse-substring). When set,
    REQUIRE_FACT_ACTION_ID=true makes unresolvable facts skip rather than
    save with NULL -- enforces the R7 traceability requirement on new runs.
    Default off so existing pipelines keep saving (with a WARN log).
    """
    if not facts: return 0
    require_aid = os.environ.get("REQUIRE_FACT_ACTION_ID", "").lower() in ("1", "true", "yes")
    conn = _conn(); cur = conn.cursor()
    saved = 0
    skipped_no_aid = 0
    for f in facts:
        attr = f.get("attribute_name")
        if attr not in vocabulary:
            _log.debug("Run %d: dropping fact with unknown attr '%s'", run_id, attr)
            continue
        aid = _resolve_action_id(f.get("source_name"), tool_action_map)
        if aid is None:
            if require_aid:
                _log.warning("Run %d: skipping fact attr=%s source_name=%r -- "
                             "no resolvable action_id (REQUIRE_FACT_ACTION_ID=true)",
                             run_id, attr, f.get("source_name"))
                skipped_no_aid += 1
                continue
            else:
                _log.warning("Run %d: fact attr=%s source_name=%r saved with NULL "
                             "action_id (no match in tool_action_map)",
                             run_id, attr, f.get("source_name"))
        # Truncate varchar fields to match column limits
        section = (f.get("dossier_section") or "")[:50]
        src_type = (f.get("source_type") or "")[:30]
        src_name = (f.get("source_name") or "")[:200]
        # Sanitize as_of_date: Gemini sometimes returns just a year ("2017")
        # or other non-date strings. Coerce to valid date or None.
        raw_date = f.get("as_of_date")
        as_of_date = None
        if raw_date and isinstance(raw_date, str):
            raw_date = raw_date.strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
                as_of_date = raw_date
            elif re.match(r"^\d{4}-\d{2}$", raw_date):
                as_of_date = raw_date + "-01"
            elif re.match(r"^\d{4}$", raw_date):
                as_of_date = raw_date + "-01-01"
        # SAVEPOINT per row: scoped rollback on failure so earlier inserts
        # in this batch survive.
        cur.execute("SAVEPOINT fact_insert")
        try:
            cur.execute("""
                INSERT INTO research_facts (run_id, employer_id, action_id, dossier_section, attribute_name, attribute_value, attribute_value_json, source_type, source_name, confidence, as_of_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (run_id, employer_id, aid, section, attr[:100], str(f.get("attribute_value"))[:1000], json.dumps(f.get("attribute_value_json")), src_type, src_name, f.get("confidence", 0.5), as_of_date))
            cur.execute("RELEASE SAVEPOINT fact_insert")
            saved += 1
        except Exception as e:
            _log.warning("Run %d: failed to save fact %s: %s", run_id, attr, e)
            cur.execute("ROLLBACK TO SAVEPOINT fact_insert")
    conn.commit(); conn.close()
    if skipped_no_aid:
        _log.warning("Run %d: %d fact(s) skipped because no action_id could "
                     "be resolved (REQUIRE_FACT_ACTION_ID=true)",
                     run_id, skipped_no_aid)
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
# Phase 2.7: Critique Loop
# ---------------------------------------------------------------------------

async def _critique_and_followup(
    run_id: int,
    run: dict,
    dossier_data: dict,
    credibility_summary: dict,
    triangulation_summary: dict,
    tool_action_map: dict,
    execution_order: int,
    tools_called: int,
) -> tuple:
    """Review dossier through 3 lenses iteratively and run follow-up tools for gaps.

    Runs up to ``CRITIQUE_ROUNDS`` rounds. Each round: (1) one Gemini critique
    call (no tools), then (2) up to 5 parallel follow-up tool calls for the
    gaps it surfaces. The ``tools_called_set`` (including tools already called
    before the critique phase) persists across all rounds so we never call the
    same tool twice. Stops early when Gemini returns zero gaps, when none of
    the suggested tools are actionable, or when a round exceeds
    ``CRITIQUE_ROUND_TIMEOUT_S``.

    Persists per-round results to ``research_runs.critique_result`` as
    ``{"rounds": [...], "final_assessment": "..."}``.

    Returns (updated_dossier_data, new_execution_order, new_tools_called).
    """
    body = dossier_data.get("dossier", {})
    company_name = run.get("company_name", "Unknown")

    # Build credibility/triangulation context for critique prompt (static across rounds)
    cred_ctx = ""
    if credibility_summary:
        cred_ctx = (
            f"Average source credibility: {credibility_summary.get('avg_score', 'N/A')}/100. "
            f"{credibility_summary.get('low_credibility_count', 0)} facts scored below 40 (low credibility)."
        )

    tri_ctx = ""
    flagged = triangulation_summary.get("flagged_claims", [])
    if flagged:
        tri_ctx = f"Single-source claims (need more corroboration): {', '.join(flagged)}"
    elif triangulation_summary:
        tri_ctx = "All major numeric claims have multiple independent sources."

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    # tools_called_set persists across all rounds so round N+1 can't re-suggest a
    # tool already called in round 1..N (or earlier in the pipeline).
    tools_called_set = set(tool_action_map.keys())

    rounds_payload: list = []
    final_assessment = ""
    max_rounds = max(1, CRITIQUE_ROUNDS)

    async def _run_one_round(round_number: int) -> dict:
        """Run a single critique round.

        All mutations to shared state (``execution_order``, ``tools_called``,
        ``final_assessment``, ``tools_called_set``, ``tool_action_map``, and
        ``body`` section merges) are staged locally and applied atomically only
        on successful round completion. If ``asyncio.wait_for`` fires its
        timeout, this coroutine is cancelled and the staged mutations are
        discarded — the next round starts from the same baseline as if this
        round never ran. (Background threads launched via ``asyncio.to_thread``
        may still finish and commit their own DB writes; those become orphan
        rows rather than corrupting in-memory dossier state.)

        A tool is added to ``tools_called_set`` only after it returned (even
        returning ``{"found": False}`` counts as "ran"). Exceptions during the
        tool call leave the tool eligible for retry in a later round.
        """
        nonlocal execution_order, tools_called, final_assessment

        # Re-truncate from the (possibly updated) body each round — earlier
        # rounds may have merged critique output into sections.
        dossier_str = json.dumps(body, default=str)
        if len(dossier_str) > 12000:
            dossier_str = dossier_str[:12000] + "... [truncated]"

        critique_prompt = f"""You are a quality reviewer for a labor research dossier about {company_name}.

Review this dossier through 3 critical lenses:

1. SKEPTICAL PRACTITIONER: Would a union organizer trust this information enough to act on it? Flag claims that seem unsupported or would raise eyebrows.

2. ADVERSARIAL REVIEWER: What could an employer's lawyer disprove or challenge? Flag claims with weak sourcing.

3. IMPLEMENTATION ENGINEER: Can someone actually USE this information to plan an organizing campaign? Flag missing actionable details.

## Source Quality Context
{cred_ctx}

## Triangulation Context
{tri_ctx}

## Dossier Under Review
{dossier_str}

Return ONLY a JSON object (no markdown fencing) with this structure:
{{
  "gaps": [
    {{
      "lens": "practitioner|adversarial|engineer",
      "section": "workforce|financial|labor|workplace|identity|corporate_structure|locations|leadership|assessment",
      "description": "What is missing or weak",
      "suggested_tool": "search_osha|search_nlrb|search_whd|search_sec|search_sam|search_990|search_contracts|search_mergent|search_company_enrich|search_brave_web|search_form5500|search_cbp_context|search_acs_workforce|scrape_employer_website"
    }}
  ],
  "overall_assessment": "Brief 2-sentence quality assessment"
}}

Rules:
- Only suggest tools from the list above
- Maximum 5 gaps
- Focus on the most impactful gaps, not minor details
- If the dossier is strong, return an empty gaps list"""

        # Phase A: Get critique from Gemini (no tools)
        _log.info("Run %d: requesting critique round %d/%d from Gemini...", run_id, round_number, max_rounds)
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=critique_prompt)])],
            config=types.GenerateContentConfig(max_output_tokens=4096),
        )

        critique_text = ""
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    critique_text += part.text

        # Parse critique JSON
        critique_result = _extract_dossier_json(critique_text)
        if not critique_result:
            try:
                critique_result = json.loads(critique_text)
            except (json.JSONDecodeError, TypeError):
                _log.warning("Run %d: could not parse critique response (round %d)", run_id, round_number)
                critique_result = {"gaps": [], "overall_assessment": "Critique parsing failed"}

        gaps = critique_result.get("gaps", []) or []
        assessment = critique_result.get("overall_assessment", "") or ""

        # Filter to valid, not-yet-called tools (cap at 5). We additionally
        # dedupe within this round via ``seen_this_round`` — the same tool is
        # never fired twice in one round even if suggested twice. The
        # permanent ``tools_called_set`` is NOT written here; a tool only
        # becomes "permanently called" after it returns successfully below.
        seen_this_round: set = set()
        followup_tasks = []
        for gap in gaps[:5]:
            tool_name = gap.get("suggested_tool", "")
            if (
                tool_name in TOOL_REGISTRY
                and tool_name not in tools_called_set
                and tool_name not in seen_this_round
            ):
                followup_tasks.append((tool_name, gap))
                seen_this_round.add(tool_name)

        _log.info(
            "Run %d: critique round %d/%d found %d gaps, %d actionable",
            run_id, round_number, max_rounds, len(gaps), len(followup_tasks),
        )

        round_record = {
            "round_number": round_number,
            "gaps": gaps,
            "overall_assessment": assessment,
            "followups_executed": [],
            "followups_failed": [],
        }

        if not followup_tasks:
            # No tools to run — still commit the assessment on clean return.
            final_assessment = assessment or final_assessment
            return round_record

        async def _run_followup(tool_name, gap):
            kwargs = {"company_name": company_name}
            if run.get("employer_id"):
                kwargs["employer_id"] = run["employer_id"]
            if run.get("company_state"):
                kwargs["state"] = run["company_state"]
            t0 = time.time()
            res = await asyncio.to_thread(TOOL_REGISTRY[tool_name], **kwargs)
            lat = int((time.time() - t0) * 1000)
            return tool_name, res, lat, gap

        results = await asyncio.gather(
            *(_run_followup(tn, g) for tn, g in followup_tasks),
            return_exceptions=True,
        )

        # Stage all mutations locally. Only applied at the bottom of this
        # function, after every ``await`` point has returned. A cancellation
        # during any await above discards these without touching nonlocals.
        local_exec_order = execution_order
        local_tools_called = tools_called
        pending_tool_action_map: dict = {}
        pending_tools_called_add: set = set()
        pending_body_merges: dict = {}  # section -> merged value (replaces existing)

        for r in results:
            if isinstance(r, Exception):
                # Transient failure (tool raised). Do NOT blacklist — tool
                # remains eligible for retry in a later round.
                _log.debug("Run %d: critique follow-up raised: %s", run_id, r)
                continue
            tool_name, res, lat, gap = r
            # Tool returned something (even {"found": False}) — count it as run.
            local_exec_order += 1
            local_tools_called += 1
            try:
                aid = await asyncio.to_thread(
                    _log_action, run_id, f"{tool_name} (critique)",
                    {"company_name": company_name, "reason": gap.get("description", "")[:200]},
                    local_exec_order, res, lat,
                    {"phase": "critique_followup", "lens": gap.get("lens", ""), "round": round_number},
                )
            except Exception as log_err:  # pragma: no cover — defensive
                _log.warning("Run %d: could not log critique action for %s: %s", run_id, tool_name, log_err)
                # Still mark the tool called so we don't retry it repeatedly.
                pending_tools_called_add.add(tool_name)
                round_record["followups_failed"].append(tool_name)
                continue

            pending_tool_action_map[tool_name] = aid
            pending_tools_called_add.add(tool_name)
            round_record["followups_executed"].append(tool_name)

            if res.get("found"):
                section = gap.get("section", "")
                if section and section in body:
                    existing = pending_body_merges.get(section, body[section])
                    if isinstance(existing, dict):
                        merged = dict(existing)
                        merged[f"critique_{tool_name}"] = res.get("summary", "")
                        pending_body_merges[section] = merged
                    elif isinstance(existing, str):
                        pending_body_merges[section] = existing + "\n\n" + res.get("summary", "")

        # Also record failed tasks (raised exceptions) in the round record
        # so the persisted JSONB shows what was attempted but failed.
        for tool_name, _gap in followup_tasks:
            if (
                tool_name not in round_record["followups_executed"]
                and tool_name not in round_record["followups_failed"]
            ):
                round_record["followups_failed"].append(tool_name)

        # ------------------------------------------------------------------
        # Commit point. All staged mutations are applied below; if a
        # cancellation fires before reaching here, none of these lines run
        # and the nonlocals remain at the values they had on round entry.
        # ------------------------------------------------------------------
        for section, merged in pending_body_merges.items():
            body[section] = merged
        for tool_name, aid in pending_tool_action_map.items():
            tool_action_map[tool_name] = aid
        tools_called_set.update(pending_tools_called_add)
        execution_order = local_exec_order
        tools_called = local_tools_called
        final_assessment = assessment or final_assessment

        # NOTE: critique follow-up tool results are logged to
        # ``research_actions`` and merged into the dossier body, but they are
        # NOT extracted into ``research_facts``. Structured fact extraction
        # would require a second Gemini call per tool result to normalize the
        # summary into vocabulary-typed facts — out of scope for the critique
        # loop. If future work wants credibility rescoring and contradiction
        # detection to see critique follow-ups, add a ``_extract_facts_from_tool``
        # pass here and feed the result through ``_save_facts``.

        return round_record

    # Outer iteration: up to max_rounds rounds, with per-round timeout and
    # multiple stop conditions.
    for round_number in range(1, max_rounds + 1):
        try:
            round_record = await asyncio.wait_for(
                _run_one_round(round_number),
                timeout=float(CRITIQUE_ROUND_TIMEOUT_S),
            )
        except asyncio.TimeoutError:
            _log.warning(
                "Run %d: critique round %d/%d exceeded %ds timeout",
                run_id, round_number, max_rounds, CRITIQUE_ROUND_TIMEOUT_S,
            )
            # Continue with what we already have — no error.
            break

        rounds_payload.append(round_record)

        # Stop conditions:
        # 1) Zero gaps suggested → dossier passes critique, done.
        # 2) Gaps suggested but zero tools actionable this round — i.e., every
        #    suggested tool was already in ``tools_called_set`` (exhausted) or
        #    unregistered. Future rounds will see the same state, so stop.
        # Transient failures (tools that raised exceptions) land in
        # ``followups_failed`` and intentionally do NOT trigger stop — those
        # tools remain eligible for retry next round.
        if not round_record.get("gaps"):
            break
        if (
            not round_record.get("followups_executed")
            and not round_record.get("followups_failed")
            and len(round_record.get("gaps", [])) > 0
        ):
            _log.info(
                "Run %d: no actionable follow-up tools in round %d, stopping critique loop",
                run_id, round_number,
            )
            break

    # Persist the full iterative payload to research_runs.critique_result.
    critique_payload = {
        "rounds": rounds_payload,
        "final_assessment": final_assessment,
    }
    _update_run(run_id, critique_result=json.dumps(critique_payload, default=str))

    return dossier_data, execution_order, tools_called


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
    # Pre-lookup: try to find a website URL from master_employers or mergent
    # so Gemini and CompanyEnrich have the domain from the start
    if not run.get("website_url"):
        try:
            _pc = _conn(); _pcur = _pc.cursor()
            _pcur.execute(
                "SELECT website FROM master_employers "
                "WHERE canonical_name ILIKE %s AND website IS NOT NULL AND website != '' "
                "LIMIT 1",
                (f"%{run['company_name']}%",)
            )
            _row = _pcur.fetchone()
            if _row and _row.get("website"):
                run["website_url"] = _row["website"]
                _log.info("Run %d: pre-looked up website '%s' from master_employers", run_id, run["website_url"])
            _pc.close()
        except Exception:
            pass  # Non-critical: proceed without website

    vocabulary = _load_vocabulary()
    system_prompt = _build_system_prompt(run, vocabulary)
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    gemini_tools = _build_gemini_tools()

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=f"Research {run['company_name']}")])]
    execution_order, tools_called = 0, 0
    tools_called_set = set(); tool_action_map = {}
    final_text = ""
    _total_input_tokens = 0
    _total_output_tokens = 0

    def _track_tokens(resp):
        nonlocal _total_input_tokens, _total_output_tokens
        um = getattr(resp, "usage_metadata", None)
        if um:
            _total_input_tokens += getattr(um, "prompt_token_count", 0) or 0
            _total_output_tokens += getattr(um, "candidates_token_count", 0) or 0

    # Phase 1: Gemini Multi-Turn Loop
    for turn in range(MAX_TOOL_TURNS):
        pct = min(int((turn / MAX_TOOL_TURNS) * 70), 70)
        _update_run(run_id, current_step=f"Turn {turn+1}: querying Gemini...", progress_pct=pct)
        response = await asyncio.to_thread(client.models.generate_content, model=MODEL, contents=contents, config=types.GenerateContentConfig(system_instruction=system_prompt, tools=gemini_tools, max_output_tokens=MAX_TOKENS))
        _track_tokens(response)
        candidate = response.candidates[0]
        function_calls = [p for p in candidate.content.parts if p.function_call]
        text_parts = [p.text for p in candidate.content.parts if p.text]

        # Capture any text Gemini returns (even alongside tool calls)
        if text_parts:
            partial_text = "\n".join(text_parts)
            if len(partial_text) > len(final_text):
                final_text = partial_text

        if not function_calls:
            break

        tool_names = [p.function_call.name for p in function_calls]
        _update_run(run_id, current_step=f"Turn {turn+1}: running {', '.join(tool_names)}...", progress_pct=pct, total_tools_called=tools_called + len(function_calls))

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

    # If the loop exhausted all turns without Gemini producing a final dossier,
    # make one more call WITHOUT tools to force synthesis
    if not _extract_dossier_json(final_text):
        _log.warning("Run %d: no dossier JSON after %d turns, forcing synthesis call", run_id, MAX_TOOL_TURNS)
        _update_run(run_id, current_step="Forcing final synthesis...", progress_pct=71)
        contents.append(types.Content(role="user", parts=[
            types.Part.from_text(text="You have gathered enough data. Now produce your final JSON dossier report. Do NOT call any more tools. Return the dossier JSON immediately.")
        ]))
        try:
            synth_response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL, contents=contents,
                config=types.GenerateContentConfig(system_instruction=system_prompt, max_output_tokens=MAX_TOKENS)
            )
            _track_tokens(synth_response)
            synth_text = "\n".join(p.text for p in synth_response.candidates[0].content.parts if p.text)
            if synth_text and len(synth_text) > len(final_text):
                final_text = synth_text
                _log.info("Run %d: forced synthesis produced %d chars", run_id, len(final_text))
        except Exception as synth_exc:
            _log.error("Run %d: forced synthesis failed: %s", run_id, synth_exc)

    # Phase 1.5 & 1.6: Forced Enrichment (Parallel)
    # Load strategy to skip low-value tools for this industry/type/size
    _naics_2 = (run.get("industry_naics") or "")[:2]
    _company_type = run.get("company_type") or ""
    _size_bucket = run.get("employee_size_bucket") or ""
    _strategy = _load_strategy(_naics_2, _company_type, _size_bucket)
    _prune_hr = float(os.environ.get("RESEARCH_PRUNE_HIT_RATE", "0.10"))
    _prune_min = int(os.environ.get("RESEARCH_PRUNE_MIN_TRIES", "5"))
    _latency_skip_ms = int(os.environ.get("RESEARCH_LATENCY_SKIP_MS", "15000"))
    _latency_skip_hr = float(os.environ.get("RESEARCH_LATENCY_SKIP_HIT_RATE", "0.20"))
    _latency_skip_min = int(os.environ.get("RESEARCH_LATENCY_SKIP_MIN_TRIES", "3"))
    _skip_tools = set()
    for r in _strategy:
        hr = r.get("hit_rate") or 0
        tries = r.get("times_tried") or 0
        latency = r.get("avg_latency_ms") or 0
        if hr < _prune_hr and tries >= _prune_min:
            _skip_tools.add(r["tool_name"])
        elif latency > _latency_skip_ms and hr < _latency_skip_hr and tries >= _latency_skip_min:
            _skip_tools.add(r["tool_name"])
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

    async def _f_company_enrich():
        if "search_company_enrich" in tools_called_set: return None
        if "search_company_enrich" in _skip_tools: return None
        kwargs = {"company_name": run["company_name"]}
        # Try to find a domain for better CompanyEnrich match accuracy
        # Priority: dossier (from Gemini tools) > pre-looked-up website > run metadata
        website = None
        d = _extract_dossier_json(final_text)
        if d:
            try:
                website = d.get("dossier", {}).get("identity", {}).get("website_url")
            except Exception:
                pass
        if not website:
            website = run.get("website_url")
        if website and isinstance(website, str) and "." in website:
            domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            kwargs["domain"] = domain
        if run.get("linkedin_url"):
            kwargs["linkedin_url"] = run["linkedin_url"]
        res = await asyncio.to_thread(TOOL_REGISTRY["search_company_enrich"], **kwargs)
        return ("company_enrich", res)
    forced_tasks.append(_f_company_enrich())

    async def _f_linkedin():
        if "search_linkedin_company" in tools_called_set: return None
        if "search_linkedin_company" not in TOOL_REGISTRY: return None
        # Get LinkedIn URL from dossier (CompanyEnrich often provides it)
        li_url = None
        d = _extract_dossier_json(final_text)
        if d:
            try:
                li_url = d.get("dossier", {}).get("identity", {}).get("linkedin_url")
            except Exception:
                pass
        if not li_url:
            li_url = run.get("linkedin_url")
        if not li_url:
            return None
        res = await asyncio.to_thread(TOOL_REGISTRY["search_linkedin_company"],
                                       company_name=run["company_name"], linkedin_url=li_url)
        return ("linkedin", res)
    forced_tasks.append(_f_linkedin())

    _update_run(run_id, current_step="Enriching with additional data sources...", progress_pct=72, total_tools_called=tools_called)
    enrich_res = await asyncio.gather(*(t for t in forced_tasks if t is not None))

    # Phase 1.8: Structured Dossier Extraction (response_schema)
    _log.info("Run %d: structured dossier extraction...", run_id)
    _update_run(run_id, current_step="Extracting structured dossier...", progress_pct=73)
    dossier_schema = _build_dossier_schema(vocabulary)
    extraction_prompt = (
        "Reformat your research into the structured JSON schema. "
        "Use ONLY the exact attribute names defined in the schema for facts. "
        "Set confidence per the scoring rules. Null for fields not found.\n\n"
        "RAW OUTPUT:\n" + final_text[:40000]
    )
    try:
        extract_resp = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=contents + [types.Content(role="user", parts=[types.Part.from_text(text=extraction_prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=dossier_schema,
                max_output_tokens=MAX_TOKENS,
            ),
        )
        _track_tokens(extract_resp)
        extract_text = ""
        if extract_resp.candidates:
            for part in extract_resp.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    extract_text += part.text
        if extract_text:
            dossier_data = json.loads(extract_text)
            _log.info("Run %d: structured extraction OK (%d chars)", run_id, len(extract_text))
        else:
            _log.warning("Run %d: structured extraction empty, regex fallback", run_id)
            dossier_data = _extract_dossier_json(final_text) or {"dossier": {}, "facts": []}
    except Exception as exc:
        _log.warning("Run %d: structured extraction failed (%s), regex fallback", run_id, exc)
        dossier_data = _extract_dossier_json(final_text) or {"dossier": {}, "facts": []}

    # Patch Dossier with Enrichment Results
    body = dossier_data.setdefault("dossier", {})

    for r in enrich_res:
        if not r or not r[1].get("found"): continue
        rtype, rdata = r[0], r[1]
        if rtype == "gleif":
            body.setdefault("corporate_structure", {})["parent_company"] = rdata.get("data", {}).get("parents", [{}])[0].get("parent_name")
        elif rtype == "donations":
            body.setdefault("assessment", {})["political_donations"] = rdata.get("data")
        elif rtype == "sentiment":
            body.setdefault("workplace", {})["worker_complaints"] = rdata.get("summary")
        elif rtype == "sos":
            body.setdefault("leadership", {})["registered_agent"] = rdata.get("data", {}).get("registered_agent")
        elif rtype == "acs_workforce":
            body.setdefault("workforce", {})["acs_demographics"] = rdata.get("data")
        elif rtype == "company_enrich":
            ce_data = rdata.get("data", {})
            identity = body.setdefault("identity", {})
            if ce_data.get("website") and not identity.get("website_url"):
                identity["website_url"] = ce_data["website"]
            if ce_data.get("linkedin_url") and not identity.get("linkedin_url"):
                identity["linkedin_url"] = ce_data["linkedin_url"]
            if ce_data.get("founded_year") and not identity.get("year_founded"):
                identity["year_founded"] = ce_data["founded_year"]
            if ce_data.get("industry") and not identity.get("naics_description"):
                identity["naics_description"] = ce_data["industry"]
            if ce_data.get("company_type") and not identity.get("company_type"):
                identity["company_type"] = ce_data["company_type"]
            financial = body.setdefault("financial", {})
            if ce_data.get("employee_range") and not financial.get("employee_count"):
                financial["employee_count"] = ce_data["employee_range"]
            if ce_data.get("revenue_range") and not financial.get("revenue_range"):
                financial["revenue_range"] = ce_data["revenue_range"]
            if not identity.get("hq_address"):
                loc_parts = [ce_data.get("location_city"), ce_data.get("location_state"), ce_data.get("location_country")]
                loc_str = ", ".join(p for p in loc_parts if p)
                if loc_str:
                    identity["hq_address"] = loc_str

        elif rtype == "linkedin":
            li_data = rdata.get("data", {})
            identity = body.setdefault("identity", {})
            if li_data.get("industry") and not identity.get("naics_description"):
                identity["naics_description"] = li_data["industry"]
            if li_data.get("headquarters") and not identity.get("hq_address"):
                identity["hq_address"] = li_data["headquarters"]
            if li_data.get("founded") and not identity.get("year_founded"):
                identity["year_founded"] = li_data["founded"]
            if li_data.get("company_type") and not identity.get("company_type"):
                identity["company_type"] = li_data["company_type"]
            financial = body.setdefault("financial", {})
            if li_data.get("company_size") and not financial.get("employee_count"):
                financial["employee_count"] = li_data["company_size"]
            if li_data.get("about"):
                body.setdefault("identity", {}).setdefault("company_description", li_data["about"])

        execution_order += 1; tools_called += 1
        aid = await asyncio.to_thread(_log_action, run_id, f"search_{rtype} (forced)", {"company_name": run["company_name"]}, execution_order, rdata, 0)
        tool_action_map[f"search_{rtype}"] = aid

    # Early termination check: assess dossier coverage after enrichment
    _coverage_pct, _weak_sections = _assess_coverage(dossier_data)
    _log.info("Run %d: post-enrichment coverage %.0f%%, weak sections: %s",
              run_id, _coverage_pct, _weak_sections or "none")

    # Phase 1.7: Variant Web Queries (fill gaps from missed DB tools)
    # Skip if coverage is already very strong (saves Brave API calls + time)
    _skip_variants = _coverage_pct >= 90 and not _weak_sections
    if _skip_variants:
        _log.info("Run %d: coverage %.0f%% >= 90%%, skipping variant queries", run_id, _coverage_pct)
    else:
        _update_run(run_id, current_step="Running variant web queries...", progress_pct=78, total_tools_called=tools_called)
        try:
            # Identify which DB tools actually returned NO data (genuine gaps).
            # Prior bug: this collected every tool in `tool_action_map` --
            # i.e., tools that RAN -- which inverts the semantics and causes
            # variant queries to fire for gaps that are already filled.
            # Fix: query `research_actions` for this run and filter to
            # data_found=false rows.
            db_gaps: list[str] = []
            try:
                _conn_a = _conn()
                _cur_a = _conn_a.cursor()
                _cur_a.execute(
                    "SELECT tool_name, data_found FROM research_actions WHERE run_id = %s",
                    (run_id,),
                )
                for row in _cur_a.fetchall():
                    tn = row["tool_name"] if isinstance(row, dict) else row[0]
                    found = row["data_found"] if isinstance(row, dict) else row[1]
                    if found is False and tn in _TOOL_GAP_MAP and tn not in db_gaps:
                        db_gaps.append(tn)
                _conn_a.close()
            except Exception as exc:
                _log.debug("Run %d: could not read research_actions for db_gaps: %s", run_id, exc)
            # Also capture enrichment misses (enrich_res is in-memory, fresher
            # than the DB log for actions written later in the pipeline).
            for r in enrich_res:
                if r and not r[1].get("found"):
                    gap_tool = f"search_{r[0]}"
                    if gap_tool in _TOOL_GAP_MAP and gap_tool not in db_gaps:
                        db_gaps.append(gap_tool)

            if db_gaps or True:  # always run news/labor/conditions queries
                queries, gap_types_used = _build_web_search_queries(
                    run["company_name"],
                    run.get("company_type"),
                    run.get("company_state"),
                    db_gaps,
                    company_address=run.get("company_address"),
                    weak_sections=_weak_sections,
                )

                if queries and "search_brave_web" in TOOL_REGISTRY:
                    # Pair each query with its gap_type for downstream
                    # attribution. `gap_types_used` is aligned 1:1 with
                    # `queries`. Each element is a (gap_key, raw_template)
                    # tuple -- we only need the gap_key here.
                    _query_to_gap: dict[str, str] = {}
                    for _q, _gt_pair in zip(queries, gap_types_used):
                        _gt = _gt_pair[0] if isinstance(_gt_pair, tuple) else _gt_pair
                        _query_to_gap[_q] = _gt

                    async def _run_variant(q):
                        res = await asyncio.to_thread(
                            TOOL_REGISTRY["search_brave_web"],
                            query=q, company_name=run["company_name"],
                        )
                        return (q, res)

                    # Run up to 8 variant queries in parallel
                    variant_results = await asyncio.gather(
                        *(_run_variant(q) for q in queries[:8]),
                        return_exceptions=True,
                    )

                    variant_found = 0
                    # Build fact-count-by-gap-type as we iterate. Prior bug
                    # passed an empty dict here, which silently logged every
                    # variant query as 0-facts and poisoned the learning
                    # table (research_query_effectiveness).
                    web_facts_by_gap: dict[str, int] = {}
                    for vr in variant_results:
                        if isinstance(vr, Exception):
                            continue
                        query_str, res = vr
                        if res.get("found"):
                            variant_found += 1
                            execution_order += 1; tools_called += 1
                            aid = await asyncio.to_thread(
                                _log_action, run_id, "search_brave_web (variant)",
                                {"query": query_str}, execution_order, res, 0,
                            )
                            # Attribute the returned result_count to this query's gap_type
                            gt = _query_to_gap.get(query_str)
                            if gt:
                                n_results = 0
                                try:
                                    n_results = int((res.get("data") or {}).get("result_count") or 0)
                                except (TypeError, ValueError):
                                    n_results = 0
                                web_facts_by_gap[gt] = web_facts_by_gap.get(gt, 0) + n_results

                    if variant_found > 0:
                        _log.info("Run %d: %d/%d variant queries returned results", run_id, variant_found, len(queries[:8]))

                    # Update query effectiveness tracking with real attribution
                    try:
                        _update_query_effectiveness(gap_types_used, web_facts_by_gap, run.get("company_type") or "")
                    except Exception as exc:
                        _log.debug("Run %d: _update_query_effectiveness failed: %s", run_id, exc)
        except Exception as exc:
            _log.warning("Run %d: variant query phase failed: %s", run_id, exc)

    _update_run(run_id, current_step="Saving facts and checking coverage...", progress_pct=85, total_tools_called=tools_called)
    _ensure_exhaustive_coverage(run_id, dossier_data, vocabulary)
    facts_saved = _save_facts(run_id, run.get("employer_id"), dossier_data.get("facts", []), vocabulary, tool_action_map)

    # Phase 2.5: Source Credibility Scoring
    _update_run(run_id, current_step="Scoring source credibility...", progress_pct=86)
    credibility_summary = {}
    try:
        from scripts.research.source_credibility import score_facts_credibility
        cred_count = score_facts_credibility(run_id)
        _log.info("Run %d: scored credibility for %d facts", run_id, cred_count)
        conn_c = _conn(); cur_c = conn_c.cursor()
        cur_c.execute(
            "SELECT AVG(credibility_score) AS avg_cred, "
            "COUNT(*) FILTER (WHERE credibility_score < 40) AS low_cred "
            "FROM research_facts WHERE run_id = %s AND credibility_score IS NOT NULL",
            (run_id,),
        )
        row = cur_c.fetchone()
        credibility_summary = {
            "avg_score": round(float(row["avg_cred"] or 0), 1),
            "low_credibility_count": row["low_cred"] or 0,
            "total_scored": cred_count,
        }
        conn_c.close()
    except Exception as exc:
        _log.warning("Run %d: credibility scoring failed: %s", run_id, exc)

    # Phase 2.6: Triangulation
    _update_run(run_id, current_step="Triangulating claims...", progress_pct=88)
    triangulation_summary = {}
    try:
        from scripts.research.triangulation import triangulate_facts
        triangulation_summary = triangulate_facts(run_id)
        _log.info(
            "Run %d: %d claims, %d single-source",
            run_id,
            triangulation_summary.get("total_claims", 0),
            triangulation_summary.get("single_source_count", 0),
        )
    except Exception as exc:
        _log.warning("Run %d: triangulation failed: %s", run_id, exc)

    # Phase 2.7: Critique Loop (iterative — up to CRITIQUE_ROUNDS rounds)
    _update_run(run_id, current_step="Running critique review...", progress_pct=90)
    # Outer guard: rounds * per-round + 60s buffer. Per-round timeout is
    # enforced inside _critique_and_followup; this is the belt-and-suspenders
    # kill switch in case something hangs outside the round loop itself.
    _critique_outer_timeout = float(max(1, CRITIQUE_ROUNDS) * CRITIQUE_ROUND_TIMEOUT_S + 60)
    try:
        dossier_data, execution_order, tools_called = await asyncio.wait_for(
            _critique_and_followup(
                run_id, run, dossier_data,
                credibility_summary, triangulation_summary,
                tool_action_map, execution_order, tools_called,
            ),
            timeout=_critique_outer_timeout,
        )
    except asyncio.TimeoutError:
        _log.warning("Run %d: critique loop timed out at %ds", run_id, int(_critique_outer_timeout))
    except Exception as exc:
        _log.warning("Run %d: critique loop failed: %s", run_id, exc)

    # Detect contradictions before auto-grade (feeds into consistency score)
    try:
        contradictions = _resolve_contradictions(run_id)
        if contradictions:
            _log.info("Run %d: flagged %d contradiction(s).", run_id, contradictions)
    except Exception as exc:
        _log.debug("Contradiction detection for run %d failed: %s", run_id, exc)

    # Cross-run contradictions (compare against most recent prior run for same employer)
    if run.get("employer_id"):
        try:
            cross = _resolve_cross_run_contradictions(run["employer_id"], run_id)
            if cross:
                _log.info("Run %d: flagged %d cross-run contradiction(s).", run_id, cross)
        except Exception as exc:
            _log.debug("Cross-run contradiction detection for run %d failed: %s", run_id, exc)

    # Count filled sections in the dossier
    _DOSSIER_SECTIONS = {
        "identity",
        "corporate_structure",
        "locations",
        "leadership",
        "labor",
        "assessment",
        "workforce",
        "workplace",
        "financial",
        "sources",
        "adaptive_findings",
    }
    _body = dossier_data.get("dossier", {})
    _sections_filled = sum(1 for s in _DOSSIER_SECTIONS if _body.get(s))

    # Compute API cost
    _total_cost = (_total_input_tokens / 1000 * _INPUT_COST_PER_1K +
                   _total_output_tokens / 1000 * _OUTPUT_COST_PER_1K)
    _log.info("Run %d: tokens in=%d out=%d cost=$%.4f", run_id, _total_input_tokens, _total_output_tokens, _total_cost)

    _update_run(run_id, status="completed", completed_at=datetime.now(), duration_seconds=int(time.time()-start_time), dossier_json=json.dumps(dossier_data, default=str), total_facts_found=facts_saved, sections_filled=_sections_filled, total_tools_called=tools_called, total_input_tokens=_total_input_tokens, total_output_tokens=_total_output_tokens, total_cost_cents=round(_total_cost * 100, 2))

    _update_run(run_id, current_step="Auto-grading and updating strategy...", progress_pct=95, total_facts_found=facts_saved)

    # Auto-linkage: if employer_id is still NULL, attempt lookup now
    try:
        _conn2 = _conn()
        _cur2 = _conn2.cursor()
        _cur2.execute("SELECT employer_id, company_name, company_state, company_address FROM research_runs WHERE id = %s", (run_id,))
        _run_row = _cur2.fetchone()
        if _run_row and not _run_row.get("employer_id"):
            from scripts.research.employer_lookup import lookup_employer
            _eid, _ename, _method = lookup_employer(
                _cur2, _run_row["company_name"],
                _run_row.get("company_state"), _run_row.get("company_address"),
            )
            if _eid:
                _cur2.execute("UPDATE research_runs SET employer_id = %s WHERE id = %s", (_eid, run_id))
                _conn2.commit()
                _log.info("Run %d: auto-linked to employer %s (%s) via %s", run_id, _eid, _ename, _method)
        _conn2.close()
    except Exception as exc:
        _log.debug("Auto-linkage for run %d failed: %s", run_id, exc)

    # Report validation (Phase 8: automated quality checks)
    validation_report = None
    try:
        from scripts.research.report_validation import validate_dossier
        validation_report = validate_dossier(run_id)
        _log.info(
            "Run %d: validation %d/%d checks passed",
            run_id, validation_report.get("passed_count", 0),
            validation_report.get("total_checks", 0),
        )
    except Exception as exc:
        _log.debug("Validation for run %d failed: %s", run_id, exc)

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
    parser.add_argument("--company", help="Company name (required unless --run-id is provided).")
    parser.add_argument("--state")
    parser.add_argument(
        "--run-id",
        type=int,
        help=(
            "Execute research on a pre-existing research_runs row. Useful for "
            "A/B tests that need to control `triggered_by` or env vars like "
            "RESEARCH_CRITIQUE_ROUNDS per run."
        ),
    )
    args = parser.parse_args()
    if args.run_id:
        rid = args.run_id
        print(f"Using existing run {rid}")
    else:
        if not args.company:
            parser.error("--company is required unless --run-id is provided")
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO research_runs (company_name, company_state, status) "
            "VALUES (%s, %s, 'pending') RETURNING id",
            (args.company, args.state),
        )
        rid = cur.fetchone()["id"]
        conn.commit()
        conn.close()
        print(f"Created run {rid}")
    print(run_research(rid))
