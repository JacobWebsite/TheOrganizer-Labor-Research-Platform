# Research Agent — Claude Code Handoff

## Context
Read these files first:
- `Start each AI/CLAUDE.md` and `Start each AI/PROJECT_STATE.md` for project context
- `RESEARCH_AGENT_IMPLEMENTATION_PLAN.md` at project root — the full plan
- `RESEARCH_AGENT_TOOL_SPECS.md` at project root — **CRITICAL: detailed specs for all 12 tools** (what to query, what to return, example output structures). Follow these specs exactly.
- `sql/create_research_agent_tables.sql` — NEW, not yet executed. Creates 5 tables + seeds 48 fact vocabulary entries.
- `api/routers/research.py` — NEW, already wired into `api/main.py`. 6 endpoints, placeholder for the actual agent.

## Decisions Already Made
| # | Decision | Choice |
|---|----------|--------|
| 1 | Web search API | Claude's built-in web search (via Anthropic API tool use) |
| 2 | Report depth | Full dossier every time (all 7 sections, no tiered/quick scan mode) |
| 3 | Where it runs | FastAPI background task (not command line) |
| 4 | Agent autonomy | Guided autonomy — recommended tool order, Claude can skip/reorder with reason |

## What's Already Built
1. **SQL migration** (`sql/create_research_agent_tables.sql`): `research_fact_vocabulary`, `research_runs`, `research_actions`, `research_facts`, `research_strategies`. NOT YET EXECUTED — run this first.
2. **FastAPI router** (`api/routers/research.py`): POST `/api/research/run`, GET `/status/{id}`, GET `/result/{id}`, GET `/runs`, GET `/vocabulary`, GET `/strategies`. Already imported in `api/main.py`. The `_run_research_placeholder` function is where the real agent gets wired in.

## What You Need to Build (Phase 1)

### Step 1: Execute the SQL migration
Run `sql/create_research_agent_tables.sql` against the database (`olms_multiyear` on localhost, use `db_config.get_connection()`).

### Step 2: Build the internal tool definitions
Create `scripts/research/tools.py` (or similar). Each tool is a function that queries the existing database and returns structured results. The agent will call these via Claude API tool use.

Tools to build — **see `RESEARCH_AGENT_TOOL_SPECS.md` for full specifications** including exact data points, which tables/columns to query, example output structures, and why each data point matters for organizing. The spec file is the authoritative guide for what each tool returns.

Summary of tools:

| Tool | Source Tables | What It Returns |
|------|--------------|-----------------|
| `search_osha` | `osha_establishments` + `osha_violations_detail` + `osha_f7_matches` | Violation count, types, penalties, serious count |
| `search_nlrb` | `nlrb_elections` + `nlrb_cases` + `nlrb_participants` + `nlrb_allegations` | Elections (dates, outcomes, votes), ULP charges |
| `search_whd` | `whd_cases` | Wage theft cases, backwages, penalties, repeat violator status |
| `search_sec` | `sec_companies` (+ XBRL if available) | Revenue, employee count, SIC code, filings |
| `search_sam` | `sam_entities` | Federal contractor status, contract amounts |
| `search_990` | `national_990_filers` + `employers_990_deduped` | Nonprofit revenue, assets, EIN |
| `search_contracts` | `f7_union_employer_relations` + `unions_master` | Existing union contracts, union names, unit sizes |
| `get_industry_profile` | `bls_industry_occupation_matrix` | Occupation mix, wage data for this NAICS |
| `get_similar_employers` | `industry_occupation_overlap` or Gower comparables | Similar employers by industry/size |
| `search_mergent` | `mergent_employers` | Revenue, employees, parent company, NAICS |
| `search_web` | Claude built-in web search | General company info, news |
| `scrape_employer_website` | Crawl4AI (already set up) | Company description, locations, leadership |

Each tool function should:
- Accept company_name (required) + optional params (state, naics, employer_id)
- Return a dict with: `found` (bool), `data` (dict of findings), `source` (str), `summary` (str)
- Handle errors gracefully (return found=False with error info)
- Be usable both standalone AND as Claude API tool definitions

### Step 3: Build the agent orchestration
Create `scripts/research/agent.py`. This is the core loop:

1. Receive a run_id
2. Update `research_runs` status to 'running'
3. Build the agent prompt with: company info, tool list, recommended order, dossier template
4. Call Anthropic API with tool definitions (using `anthropic` Python SDK)
5. Process tool_use responses — when Claude wants to call a tool, execute it and return results
6. Continue the conversation until Claude says it's done
7. Parse the final dossier from Claude's response
8. Save facts to `research_facts`, actions to `research_actions`
9. Update `research_runs` with results, set status='completed'
10. Throughout: update `current_step` and `progress_pct` so frontend can show progress

The guided autonomy prompt should give Claude a recommended order like:
```
1. Check internal databases first (fast, free): OSHA, NLRB, WHD, SEC, SAM, 990, contracts, Mergent
2. Get industry context: BLS profile, similar employers
3. Web research: company website, news search, job postings
4. Synthesize: write the organizing assessment
You may skip sources that clearly don't apply (e.g., skip SEC for private companies, skip 990 for for-profits). Explain any skips.
```

### Step 4: Wire the agent into the router
Replace `_run_research_placeholder` in `api/routers/research.py` with a call to the real agent.

### Step 5: Test on 3-5 known companies
Pick employers already in the database with good data coverage. Run deep dives. Check that:
- Facts get saved with correct attribute_names from the vocabulary
- Actions get logged with timing and outcomes
- The dossier JSON is complete and well-structured
- Progress updates work (status endpoint returns changing progress_pct)

## Important Technical Notes
- Database connection: `from db_config import get_connection` (project root)
- API database pool: `from api.database import get_db` (context manager)
- Anthropic SDK: `pip install anthropic` if not already installed. Needs `ANTHROPIC_API_KEY` in `.env`.
- All facts MUST use attribute_names from `research_fact_vocabulary`. Query the table at agent startup to get the valid list.
- The `research_runs.dossier_json` field stores the complete report as a single JSON blob for easy retrieval. Individual facts ALSO go in `research_facts` for queryability.
- Update `progress_pct` and `current_step` after each tool call so the frontend can show real progress.

## Do NOT Change
- Existing tables (no ALTER TABLE on anything that already exists)
- Existing routers (the research router is already wired in, don't modify other routers)
- `db_config.py` (the shared database config module)
- The fact vocabulary structure (48 entries already defined in the SQL seed data)

## Work in Checkpoints
1. Run SQL migration, verify tables exist
2. Build + test 3 internal tools (OSHA, NLRB, WHD)
3. Build remaining internal tools
4. Build agent orchestration (Claude API loop)
5. Wire into router, test end-to-end
Show results at each checkpoint before proceeding.
