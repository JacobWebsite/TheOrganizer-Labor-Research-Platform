# Research Agent — Dossier Quality Fix Plan

**Created:** 2026-02-23  
**Context:** Based on reviewing FedEx, HCA Healthcare, and ~20 other completed deep dive dossiers. Issues are consistent across runs.

Read these files first:
- `scripts/research/agent.py` — Agent orchestration (Gemini tool loop, web search, patch merge)
- `scripts/research/tools.py` — 10 DB tool implementations
- `frontend/src/features/research/` — 13 React components (dossier viewer)
- `RESEARCH_AGENT_TOOL_SPECS.md` — What each tool SHOULD return
- `sql/create_research_agent_tables.sql` — research_fact_vocabulary (48 attributes)

---

## Priority 1: Fix the "[object Object]" Serialization Bug

### Problem
Multiple dossier fields display the literal text "object" or "[object Object]" instead of actual data. This happens in: voluntary recognition values, similar organized employers, workforce composition, safety incidents, and some financial fields.

### Root Cause
When Gemini builds the dossier JSON, some attribute values are nested objects or arrays of objects (e.g., `{"union_name": "SEIU", "local": "32BJ", "unit_size": 450}`) rather than simple strings/numbers. The frontend renders these with `.toString()` which produces "[object Object]".

### Fix — Two Layers

**Layer 1 (agent.py — dossier construction):**
After Gemini produces the dossier JSON and after the web search patch merge, add a post-processing step that walks the entire dossier and ensures every `value` field in every fact is a **primitive type** (string, number, boolean, or null). If a value is an object or array, serialize it to a human-readable string.

Rules for flattening:
- If value is an array of objects → convert to a formatted string. Example: `[{"union": "SEIU", "local": "32BJ"}, {"union": "IUOE", "local": "15"}]` becomes `"SEIU Local 32BJ; IUOE Local 15"`
- If value is a single object → convert to key-value string. Example: `{"union_name": "SEIU", "local": "32BJ", "unit_size": 450}` becomes `"SEIU Local 32BJ (450 workers)"`
- If value is an array of primitives → join with semicolons. Example: `["Fall Protection", "Electrical", "Scaffolding"]` becomes `"Fall Protection; Electrical; Scaffolding"`
- Never store Python dict or list objects as fact values — always convert to display-ready strings

**Layer 2 (frontend — defensive rendering):**
In the dossier viewer components, add a safety check: if `typeof value === 'object'`, render `JSON.stringify(value, null, 2)` in a code block rather than showing "[object Object]". This is a fallback — Layer 1 should prevent it, but the frontend shouldn't break if it happens.

### How to Verify
Run a deep dive on any company. Check that these sections have readable text, not "object":
- Voluntary recognition entries
- Similar organized employers list
- Workforce composition values
- Safety incidents details
- Any financial fields with structured data

---

## Priority 2: Fix Tool Search Logic (Wrong/Inflated Results)

### Problem A: Union presence too high for FedEx
FedEx is notoriously non-union (one of the most prominent anti-union companies in the US). If the dossier shows high union presence, the search tools are returning false matches.

**Investigate:** 
1. Run `search_contracts("FedEx")` standalone and examine raw output. What employer_id values come back? Do they actually belong to FedEx Corporation, or to other companies with "Fed" in the name?
2. Check `_name_like_clause()` — is `%FED%EX%` matching things like "Federal Express Employees Credit Union" or other non-FedEx entities?
3. Check if the employer_id returned in the contracts section actually corresponds to FedEx in `f7_employers_deduped`. The employer_id MUST point to the company being researched, not to a loose name match.

**Fix pattern:** After name-matched results come back, add a **relevance filter**. If the tool searched for "FedEx" and got back results for employer_id 12345, verify that employer_id 12345's employer_name actually contains "FedEx" (or a known variant). Drop results where the matched employer name doesn't reasonably match the search term.

### Problem B: NLRB elections seem too high
Same pattern — `search_nlrb("FedEx")` may be pulling elections for similarly-named employers. Also: the NLRB participants table is joined by case_number, and if the name match is fuzzy, it may pull in elections where FedEx was a participant but not the employer (e.g., they were a "Party to Contract" or "Intervenor").

**Investigate:**
1. Run `search_nlrb("FedEx")` standalone. For each election returned, check: what is the participant_type? Is FedEx listed as "Employer" or some other role?
2. Check if the election results include Railway Labor Act cases (FedEx is covered under RLA, not NLRA — their elections go through the NMB, not NLRB). If NLRB returns results for FedEx, some may be ULP charges rather than actual elections.

**Fix:** Filter NLRB results to only include cases where the matched entity has `participant_type = 'Employer'` or `participant_type LIKE '%Employer%'`. 

### Problem C: "Union Won" = Yes but "Is Winner" = unpopulated
In the `nlrb_elections` table, `union_won` is a boolean derived from vote tallies. The `is_winner` field (if it exists in the data) may come from a different source or be populated by a different process.

**Investigate:** Check the actual column names in `nlrb_elections` and `nlrb_tallies`. Is `is_winner` a column that exists? If so, what populates it? If `union_won = true`, then the winning union should be identifiable from the tally data.

**Fix:** If `is_winner` isn't reliably populated, derive it: when `union_won = true`, the winner is the union with the most votes in `nlrb_tallies` for that case. Don't display an `is_winner` field that's empty — either populate it or remove it.

### Problem D: IUOE contract with FedEx — verify accuracy
The International Union of Operating Engineers (IUOE) representing FedEx workers would be unusual. This may be a false name match.

**Investigate:** Trace this specific result back through the data. What employer_id was matched? What's the actual employer_name for that ID in `f7_employers_deduped`? If it's not actually FedEx, this confirms the name matching is too loose.

### Problem E: Employer ID in contracts section should be the actual company
When the dossier shows union contract data, the employer_id displayed should be the canonical ID for the company being researched — not some intermediate match ID or the ID of a different employer that happened to match on name.

**Fix:** In `search_contracts()`, when returning results, include `matched_employer_name` alongside `employer_id` so the agent (and human reviewer) can see exactly which database employer record was matched. If the matched name doesn't match the search term, flag it as low confidence.

---

## Priority 3: Populate Missing Fields

### Problem
Many dossier fields that SHOULD have data are coming back empty. Two sub-problems:

**3A — Fields the tools look for but don't extract properly:**
These fields have data in the database or on the web, but the tool functions aren't pulling them into the dossier.

| Field | Expected Source | What to Check |
|-------|----------------|---------------|
| website_url | Web search / Mergent | Does `search_mergent` return a URL field? Does the web search phase extract company URLs? |
| hq_address | Mergent / SAM / web search | `mergent_employers` has address columns. Are they being returned? |
| year_founded | Mergent / web search | `mergent_employers.year_started` exists. Is it being extracted? |
| parent_company | Mergent / SEC / web search | `mergent_employers` may have parent info. `sec_companies` has some. Check both. |
| dba_names | F7 / Mergent / web search | `f7_employers_deduped` has `employer_name` vs `employer_name_aggressive`. Are alternate names being captured? For HCA this should find individual hospital names. |
| revenue | SEC (XBRL) / Mergent / web search | `mergent_employers.sales_actual` and `sec_companies` XBRL data. Are these being queried? |
| exec_compensation | SEC / 990 / web search | SEC proxy statements have this for public companies. 990s have it for nonprofits. Neither may be in the current tool queries. |

**3B — Fields defined in the vocabulary but no tool populates them yet:**
These are known gaps — the tools were never built to find this data.

| Field | Status | Action |
|-------|--------|--------|
| pay_ranges | Not populated | Requires web search targeting or job posting scraper (not built yet) |
| turnover_signals | Not populated | Requires web search targeting (layoff/hiring news) |
| job_posting_count | Not populated | Requires Indeed/job board scraper (not built yet) |
| job_posting_details | Not populated | Same — requires job board scraper |
| demographics | Not populated | Requires ACS PUMS data integration (not loaded yet) |
| financial_trend | Not populated | Requires year-over-year comparison logic (SEC or Mergent multi-year) |

**For 3A:** Fix the existing tools to extract data they already have access to. This is the quick win.
**For 3B:** These are future features. For now, the dossier should show "No data available" rather than empty fields or "object". Don't show fields with no data at all — hide the row entirely if there's nothing to show.

---

## Priority 4: NLRB Election Detail Improvements

### Problem
NLRB elections section needs more detail on the parties involved. When an election is listed, the dossier should show:
- Which union petitioned
- Which employer (with actual name, not just ID)
- Vote tallies (for, against, eligible)
- Whether the union won
- Date of election
- Case number (for reference)

### Fix
In `search_nlrb()`, when returning election results, join through `nlrb_participants` to get:
- The union name (participant_type containing 'Petitioner' or 'Labor Organization')
- The employer name (participant_type containing 'Employer')

Also join through `nlrb_tallies` to get:
- Votes for union
- Votes against
- Eligible voters
- The specific union that won (if union_won = true)

Format each election as a complete record with all parties identified, not just a count.

---

## Priority 5: Design/Content Changes

### 5A: Remove "major_locations" from dossier
This field is unreliable — database tools can't populate it well, and web search results for locations are inconsistent. Remove it from the dossier template and the fact vocabulary. It can be re-added later when the employer website scraper (Crawl4AI) is built and can extract location pages.

### 5B: Similar employers — display format
Currently showing as value objects (Priority 1 fixes this), but also: the display order should be:
**Employer Name — City, State** (not the other way around)
Lead with the company name since that's what the reader is scanning for.

### 5C: Redesign the Summary/Assessment section
The current summary tries to generate "challenges" and "recommended approach" — this is premature. We will eventually have organizing scores to power those recommendations.

**New summary structure:**
1. **Data Summary** — 2-3 sentences summarizing what the database found (number of violations, contracts, elections, etc.). Factual only, no interpretation.
2. **Web Intelligence Summary** — 2-3 sentences summarizing what web search found (recent news, organizing activity, worker sentiment). Clearly labeled as web-sourced.  
3. **Source Contradictions** (if any) — Flag cases where database data and web data disagree. Example: "Database shows no NLRB elections, but web search found a 2025 petition filed by National Nurses United." This is critical intelligence — it means either the database is stale or the web source is wrong.
4. **Remove for now:** "Challenges," "Recommended Approach," and "Campaign Strengths" sections. These will be replaced by the organizing scorecard once scores are implemented.

### 5D: Union names in contracts should include the local
When displaying union contract data, show "SEIU Local 32BJ" not just "SEIU". The local number matters — organizers need to know which specific local to contact. The data is in `unions_master` (union_name field typically includes the local). Make sure the full union name is being passed through.

---

## Work Order

1. **Fix serialization** (Priority 1) — affects everything, fix first
2. **Fix search logic** (Priority 2) — wrong data is worse than missing data  
3. **Populate missing fields** (Priority 3A only) — quick wins from existing data
4. **NLRB detail improvements** (Priority 4) — better election records
5. **Design changes** (Priority 5) — summary rewrite, display fixes

After each priority, run 2-3 test deep dives (use FedEx and HCA as regression tests) and verify the fixes before moving to the next priority.

---

## Checkpoint Expectations

**After Priority 1:** No more "[object Object]" anywhere in any dossier. All values render as readable text.

**After Priority 2:** Run FedEx again. Union presence should be low/none. NLRB elections should be accurate count with parties identified. Any IUOE contract should be verified as actually belonging to FedEx.

**After Priority 3A:** Run HCA again. Should now show: DBA names (hospital names), HQ address, website URL, year founded, revenue, parent company.

**After Priority 4:** NLRB elections show full details: union name, employer name, votes, outcome, date, case number.

**After Priority 5:** Summary section shows data summary + web intelligence + contradictions. No more "challenges" or "recommended approach." Similar employers display as "Name — City, ST."
