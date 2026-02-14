# Claude Code Audit Methodology
## How the Blind Audit Was Conducted — 2026-02-14

---

## Overview

This document explains the methodology behind the independent audit saved as `claude_audit_report.md`. It covers how I decided what to focus on, how I structured the work, what trade-offs I made, and what limitations exist in the findings.

---

## Phase 1: Orientation (First 5 Minutes)

### What I Read First and Why

The audit prompt (`BLIND_AUDIT_PROMPT.md`) specified a reading order:

1. **README.md** — First impressions matter. This is what any new developer sees. I immediately noted the wrong startup command (`api.labor_api_v6:app` vs `api.main:app`), which became a Critical finding because it blocks the very first thing a new user tries.

2. **CLAUDE.md** (675 lines) — The authoritative schema reference. I used this as a map of the database and API surface, but didn't trust the numbers at face value — I verified key counts against live database queries later.

3. **SESSION_LOG_2026.md** — Development history. This told me *what was built when*, which helped me assess whether recent changes had been properly integrated (e.g., the Splink dedup was done Feb 8 but the orphaned relations from that dedup were still broken on Feb 14).

4. **LABOR_PLATFORM_ROADMAP_v13.md** — What the developers think is left to do. I compared this against what I found to check if they were aware of the issues I discovered.

5. **docs/METHODOLOGY_SUMMARY_v8.md** — The data science methodology. I evaluated whether the deduplication and matching approaches were sound in theory, then checked if the implementation matched the description.

### Why This Order Matters

The reading order follows a funnel: big picture → schema → history → plans → methodology. Each document adds context that changes how I interpret the next one. By the time I reached the methodology doc, I already knew from SESSION_LOG that the Splink dedup had created orphaned records, so I could evaluate whether the methodology doc acknowledged this risk (it didn't).

---

## Phase 2: Parallel Deep Exploration (Minutes 5-20)

### The 5-Agent Strategy

I launched 5 specialized background agents simultaneously, each covering a different audit domain:

| Agent | Focus | Why This Split |
|-------|-------|----------------|
| **Database** | Live SQL queries against PostgreSQL | The database is the foundation. Bad data makes everything else unreliable. Needed actual `COUNT(*)` and `pg_stat` queries, not just reading code. |
| **API Security** | All 16 router files + middleware | SQL injection and auth are the highest-impact security risks. Needed line-by-line review of every `execute()` call. |
| **Matching Pipeline** | `scripts/matching/` + scoring scripts | This is the platform's core intellectual property. False positives/negatives directly impact organizer trust. |
| **Frontend + Tests** | `files/organizer_v5.html` + `tests/` | UX determines whether anyone actually uses the tool. Tests determine whether it stays working. |
| **Project Organization** | Directory structure, docs, file inventory | The "can someone else work on this?" question. Affects long-term maintainability. |

### Why Parallel, Not Sequential

Each agent domain is largely independent — knowing about database orphans doesn't change how I evaluate CSS responsiveness. Parallel execution cut the audit time roughly in half. The agents ran for 90-220 seconds each while I simultaneously read critical files directly.

### What I Read Directly (While Agents Worked)

I didn't delegate everything. Some files are too important to rely on an agent's summary:

- **`api/routers/organizing.py`** (709 lines) — The scoring engine. This is the single most important file in the project because it determines which employers organizers see as "top targets." I read every scoring function to evaluate whether the weights and logic make organizing sense, not just technical sense.

- **`api/middleware/auth.py`** — Authentication is a binary: it works or it doesn't. I found auth is disabled by default and leaks exception details.

- **`api/middleware/rate_limit.py`** — Checked for the memory leak pattern (in-memory dicts that grow unbounded). Found it in 30 seconds.

- **`db_config.py` and `.env`** — Credentials handling. Found the plaintext password, then immediately ran a Grep for that password string across the entire codebase. Found it hardcoded in `nlrb_win_rates.py` and in `BLIND_AUDIT_PROMPT.md` itself.

- **`tests/conftest.py` and `tests/test_api.py`** — Test quality tells you how fragile the system is. Found `autocommit=True` (no test isolation) and presence-only assertions (no schema validation).

### What I Chose NOT to Deep-Dive

- **Individual ETL scripts** (40+ in `scripts/etl/`) — Spot-checked a few but didn't audit each one. The matching pipeline agent covered the matching scripts; ETL scripts are run-once importers where bugs are caught at load time.

- **SQL view definitions** (187 views) — Verified that views reference `f7_employers_deduped` (not the raw table) via a targeted query. Didn't read every view definition — the database agent's live queries caught data quality issues that bad views would cause.

- **Archive/legacy files** — The project has 785 Python files. I focused on the ~100 that are actively used (api/, scripts/matching/, scripts/scoring/, tests/) and treated the rest as organizational debt.

- **GLEIF data model** — 10.6 GB across 9 tables, but only 605 matches. I flagged the ROI concern but didn't audit the GLEIF schema in detail because the cost-benefit didn't warrant it.

---

## Phase 3: Deciding What's Critical vs. Nice-to-Have

### The Prioritization Framework

I used three criteria to decide severity:

1. **Data impact** — Does this cause wrong answers? The orphaned relations issue (50.4% of union-employer links silently dropped) is Critical because every query, every score, and every search result is affected. A CSS color contrast issue is Low because it doesn't change the data.

2. **Blast radius** — How many features does this affect? CORS `allow_origins=["*"]` is High because it affects the entire API surface. A broken corporate.py endpoint is High but narrower — only 4 endpoints.

3. **Reversibility** — Can this be fixed quickly? The README wrong command is Critical despite being a 5-minute fix because it's the first thing that fails and the fix is trivial — there's no excuse for it to remain broken. The frontend monolith is Medium because refactoring it is a multi-week project and the current version works.

### Why I Weighted Data Integrity Over Security

Both the orphaned relations and the open CORS are serious. I ranked data integrity higher because:

- **The platform's value proposition is data accuracy.** If an organizer looks up an employer and half the union relationships are missing, they make wrong decisions about where to organize. That's a trust-destroying failure.
- **Security issues have no current users.** The platform is localhost-only with no authentication. While this blocks deployment, there's no active exploitation risk today. The data integrity issue is actively causing wrong results *right now* in every query.

### Why I Elevated the Password-in-Code Finding

Database credentials committed to git (`nlrb_win_rates.py` line 9: `'Juniordog33!'`) is Critical even though:
- `.env` is properly gitignored
- Most scripts use `db_config.py` correctly
- The database is localhost-only

The reason: **git history is permanent.** Even if the file is fixed tomorrow, the password exists in every clone of the repository forever (unless scrubbed with BFG or filter-branch). If this repo is ever shared, pushed to GitHub, or accessed by a contractor, the database is compromised.

---

## Phase 4: Evaluating From the Union Organizer Perspective

### Why This Section Exists

The audit prompt explicitly asks to "think like a union organizer, not just a programmer." Most code audits stop at technical findings. This platform exists to help workers organize — if it doesn't serve that purpose, nothing else matters.

### How I Evaluated Usefulness

I asked five questions:

1. **"Where should I go next?"** — Does the scorecard actually identify good organizing targets? I traced the scoring logic and found that 86% of OSHA establishments score artificially low because they can't be linked to union data. The pre-filter `LIMIT 500` means high-scoring targets outside the initial database result set are never evaluated. These are real analytical flaws, not just code bugs.

2. **"Can I trust this data?"** — No data freshness indicators. No source dates shown in the UI. No match confidence visible to users. An organizer has no way to know if they're looking at 2025 OSHA data or 2018 data.

3. **"Can I use this in the field?"** — Not mobile responsive. No offline capability. Organizers work in parking lots and break rooms, not at desks. A desktop-only tool is a research tool, not a field tool.

4. **"What's missing that I'd need?"** — ULP (Unfair Labor Practice) data is the #1 gap. Every organizer I've read about uses ULP patterns to assess employer hostility. It's public data from NLRB and it's not in the platform.

5. **"Would my leadership pay for this?"** — The difference between "interesting research project" and "tool we need" is workflow integration. Campaign tracking, alerts, collaboration, and CRM export are what make tools sticky. The platform stops at research.

### What I Recommended for MVP

The MVP section was the hardest to write because everything feels important. I scoped it to: what's the minimum set of fixes that would let a single union pilot this tool with real organizers?

The answer: fix the data (orphaned relations), add a map (geocoding), lock it down (auth + HTTPS), and explain the scores (plain language). Everything else is polish.

---

## Phase 5: Synthesizing Agent Results

### How I Handled Conflicting Findings

The 5 agents occasionally found the same issue from different angles:

- **Database agent** found 60,373 orphaned relations via SQL query
- **Matching agent** found that scores aren't persisted to the database
- **Frontend agent** found that the UI doesn't show match confidence

These are three manifestations of the same root problem: the data pipeline doesn't maintain integrity end-to-end. I consolidated them into a single narrative rather than listing each separately.

### How I Handled Agent Errors

- The database agent reported `f7_employers_deduped` has no primary key based on initial queries, but a follow-up query confirmed the PK was added (post-Feb 13 audit fix). I updated accordingly.
- The database agent noted `sam_uei` column doesn't exist on the crosswalk, contradicting my memory. I trusted the live database query over documentation.
- Agent output files were initially empty (a tool limitation). I resumed each agent to extract findings. This added ~5 minutes but ensured no findings were lost.

### What the Agents Missed

No agent caught the `LIMIT 500` pre-filter issue in `organizing.py` — that required reading the scoring engine line by line and understanding that the SQL `LIMIT` applies *before* Python-side scoring, not after. This is the kind of semantic bug that requires domain understanding: you have to realize that "top 500 by violation count" is not the same as "top 500 by organizing potential."

Similarly, no agent evaluated whether the scoring *weights* make organizing sense (e.g., whether 20 points for union presence vs. 10 for OSHA violations is the right ratio). That required thinking about what organizers actually prioritize, which is domain knowledge beyond code analysis.

---

## Limitations of This Audit

### What I Could Not Evaluate

1. **Actual false positive/negative rates.** I can identify that 23-27% of matches are low-confidence, but without a ground-truth labeled dataset, I can't say what the actual error rate is. This would require human review of a random sample.

2. **Query performance under load.** I checked that endpoints respond in <5 seconds for single requests, but didn't load-test. The `_build_match_lookup()` function that loads 138K rows per request would likely fail under concurrent users.

3. **Historical data accuracy.** I validated current counts against BLS benchmarks (14.5M vs 14.3M = 1.4% variance), but I didn't verify that individual employer records are correct. There could be systematic errors in specific industries or states.

4. **User testing.** I evaluated UX by reading code, not by watching organizers use the tool. Real usability testing would reveal friction points I can't see from code alone.

5. **The 785 Python scripts I didn't read.** I focused on ~100 actively-used files. There could be bugs or security issues in scripts I classified as "legacy" that are actually still being run.

### Potential Biases in My Analysis

- **I may over-weight technical debt.** As a code auditor, I naturally focus on maintainability and architecture. A union organizer might tolerate a messy codebase if the tool gives them the right answers.
- **I may under-weight domain-specific issues.** I don't have firsthand organizing experience. My assessment of "what organizers need" is based on reading about organizing workflows, not doing them.
- **I was influenced by the audit prompt.** The prompt mentioned that auth doesn't exist (Section 5: "Hint: there isn't"). This primed me to look for security issues that I might have weighted differently without the hint.
- **Recency bias from memory context.** My memory contains extensive notes from previous sessions with this project. While I avoided consulting the previous audit report (`docs/AUDIT_REPORT_2026.md`) as instructed, knowledge of past issues (orphaned relations, password patterns, GLEIF ROI) likely influenced where I looked first.

---

## Time Allocation

| Phase | Time | Activity |
|-------|------|----------|
| Orientation | ~5 min | Read 5 key documents |
| Agent Launch | ~2 min | Configure and launch 5 parallel agents |
| Direct Code Review | ~15 min | Read organizing.py, auth.py, rate_limit.py, test files, .env, db_config.py |
| Security Scan | ~3 min | Grep for hardcoded passwords, check .gitignore |
| Agent Collection | ~8 min | Resume agents, collect findings, resolve conflicts |
| Report Writing | ~20 min | Synthesize all findings into structured report |
| **Total** | **~53 min** | |

The parallel agent strategy was the key time optimization. Without it, the database queries alone (20 queries against a 20 GB database) would have taken 10+ minutes of serial execution, during which no other work could happen.

---

## Reproducibility

To reproduce this audit:

1. Read the 5 documents in the order specified in `BLIND_AUDIT_PROMPT.md`
2. Run the database exploration queries from the prompt against `olms_multiyear`
3. Read `api/routers/organizing.py` line by line — this is the scoring engine
4. Grep for hardcoded passwords: `grep -r "Juniordog33" .`
5. Check `api/main.py` for CORS configuration
6. Check `api/middleware/auth.py` for whether auth is enabled
7. Count orphaned relations: `SELECT COUNT(*) FROM f7_union_employer_relations r LEFT JOIN f7_employers_deduped e ON r.employer_id = e.employer_id WHERE e.employer_id IS NULL`
8. Evaluate the frontend by reading `files/organizer_v5.html` with attention to global state, error handling, and accessibility
9. Read `tests/test_api.py` and `tests/test_data_integrity.py` for assertion quality

Any auditor following these steps should reach substantially similar conclusions.
