# Codex — Deep Investigation Round 2
## February 26, 2026

---

## CONTEXT

You just completed a thorough audit of this platform (FULL_AUDIT_CODEX_2026-02-26.md). This is a follow-up investigation that digs deeper into the most important unresolved questions from that audit and from the three-audit synthesis.

Your job is to read actual code, trace actual execution paths, and produce concrete documentation that makes the next phase of development faster and less error-prone.

**Context files you should have:**
- Your own audit report (FULL_AUDIT_CODEX_2026-02-26.md)
- THREE_AUDIT_SYNTHESIS_2026_02_26.md — the synthesis of all three audits
- SCORING_SPECIFICATION.md — how scoring is supposed to work
- PROJECT_STATE.md — current platform state
- REACT_IMPLEMENTATION_PLAN.md — frontend architecture

**Rules (same as before):**
1. Show file paths, line numbers, and code snippets for every finding.
2. Do NOT change any code — document only.
3. Say "I didn't check this" when you skip something.

---

## Investigation 1: NLRB Nearby 25-Mile Implementation Plan

The scoring specification says 70% of the NLRB factor (which carries 3x weight) should come from nearby election activity within 25 miles and similar industry. This is the single most heavily-weighted concept in the entire scoring system, and it's currently a TODO in the code.

Your job is to trace what exists and produce a concrete implementation plan.

**Step 1: Find the TODO.**

Open `scripts/scoring/build_unified_scorecard.py`. Find the exact line(s) where the NLRB nearby component is referenced or where the TODO appears. Show the surrounding code context (10-15 lines before and after).

**Step 2: What data exists to build this?**

Check these tables and report what's available:
- `f7_employers_deduped` — does it have latitude/longitude columns? What % are populated?
- `nlrb_elections` — does it have location data (lat/lng, city, state, zip)? What columns?
- `nlrb_participants` — same question. Can we get employer locations from participants?
- Any geocoding tables — is there a dedicated geocoding table that maps employers to coordinates?

For each: show the column names, a sample of 3-5 rows, and the % that have usable location data.

**Step 3: What would the implementation look like?**

Produce a concrete plan with:
- Which tables to JOIN
- How to calculate distance (PostGIS `ST_DWithin`? Haversine formula in SQL? Something else already in the codebase?)
- How to define "similar industry" (same 2-digit NAICS? Same 3-digit? What field?)
- How to handle the 17% of employers without geocoding (skip them? Use state-level fallback?)
- Where exactly in `build_unified_scorecard.py` the new CTE would go (between which existing CTEs?)
- How the 70/30 split would work in the weighted average (separate sub-scores? Combined before weighting?)

**Step 4: What about the existing `score_union_proximity`?**

The audit found that `score_union_proximity` uses corporate family groupings (employer_canonical_groups), NOT geographic proximity. The spec calls for geographic proximity.

- Are these two different concepts that should both exist (corporate family proximity + geographic election proximity)?
- Or should geographic proximity replace corporate family proximity?
- What would the weighting look like if both exist?

Show the exact code where `score_union_proximity` is calculated so we can compare the two concepts.

**Deliverable:** A step-by-step implementation plan with file paths, line numbers, table names, column names, and pseudocode for each new CTE. Not actual code — just the precise blueprint.

---

## Investigation 2: Every Place the Frontend Explains Scoring

The three-audit synthesis identified spec/code/frontend drift as a critical trust problem. Before we can fix the frontend explanations, we need to know every place they appear.

**Step 1: Find all scoring explanation text.**

Search the entire `frontend/` directory for:
- Any string containing "weight" or "weighted"
- Any string containing factor names: "osha", "nlrb", "safety", "wage theft", "contracts", "density", "proximity", "similarity", "growth", "financial", "size"
- Any string containing "score" or "scoring" or "factor"
- Any component that renders a scoring breakdown or explanation

For each match, report:
- File path and line number
- The exact text string
- Whether it's a user-visible label, a tooltip, a help section, or internal comment

**Step 2: Categorize the drift.**

For each piece of user-visible explanation text, check it against what the code actually does (from your audit) and report:

| File:Line | What frontend says | What code does | Match? |
|-----------|-------------------|----------------|--------|

**Step 3: Produce the correction list.**

For each mismatch, write the corrected text that accurately describes what the code currently does. Keep language simple and non-technical — these are for organizers, not engineers.

**Deliverable:** A complete list of every frontend string that mentions scoring, with current text, whether it's correct, and suggested replacement text if not.

---

## Investigation 3: Dynamic SQL Security Classification

Your audit found 49 routes using dynamic SQL with f-strings, 47 without explicit auth. That's a scary headline number. But not all of them are equally risky.

**Step 1: List all 49 routes.**

For each, report:
- Method + path (e.g., `GET /api/employers/search`)
- The dynamic SQL pattern (what user input goes into the SQL string?)
- Whether it's read-only (SELECT) or writes data (INSERT/UPDATE/DELETE)
- Whether it accepts user-provided strings vs. only numeric IDs or enum values
- Auth requirement (none, user, admin)

**Step 2: Classify risk level.**

| Risk | Criteria |
|------|----------|
| **Critical** | Accepts user strings in SQL + no auth + writes data |
| **High** | Accepts user strings in SQL + no auth + read-only |
| **Medium** | Accepts only numeric IDs or enum values in SQL + no auth |
| **Low** | Has auth requirement OR only uses parameterized queries despite f-string pattern |

**Step 3: Produce the fix priority list.**

For Critical and High risk routes:
- What's the specific injection risk?
- What's the minimal fix? (parameterized query? input validation? auth gate?)
- Estimated effort per fix

**Deliverable:** A classified inventory of all 49 routes with risk levels and a prioritized fix list for the dangerous ones.

---

## Investigation 4: Pipeline Dependency Graph

Your audit found race conditions between scripts. Produce the definitive "how to run the pipeline" document.

**Step 1: Inventory every script in the pipeline.**

Check `scripts/` directory. For each script that's part of the data pipeline (ETL, matching, scoring, MV refresh):
- File path
- What it reads (which tables/views)
- What it writes (which tables/views)
- Whether it does DELETE/TRUNCATE before writing (destructive rebuild)
- Approximate runtime (if logged or documented)

**Step 2: Build the dependency graph.**

Which scripts MUST run before which others? Show this as a simple ordered list with arrows:

```
ETL scripts (parallel OK)
  ↓
run_deterministic.py (all sources) — reads: source tables, writes: unified_match_log
  ↓
build_employer_groups.py — reads: unified_match_log, writes: employer_canonical_groups [DESTRUCTIVE]
  ↓
...
```

**Step 3: Identify race conditions.**

Which pairs of scripts would produce wrong results if run simultaneously? For each:
- Script A and Script B
- What goes wrong (e.g., "Script A truncates employer_groups while Script B is reading it")
- How to prevent it (e.g., "always run A before B, never in parallel")

**Step 4: What about partial re-runs?**

If we only need to re-run matching for one source (e.g., OSHA), what's the minimum set of scripts that need to run afterward? (Just matching? Matching + groups + scoring? Everything?)

**Deliverable:** A complete pipeline dependency document that could be followed by someone who has never seen the codebase. Include a simple diagram and a numbered step-by-step run order.

---

## Investigation 5: Docker Production Readiness Checklist

The Docker artifacts exist but serve the legacy frontend and have security defaults. Produce a concrete checklist for making them production-ready.

**Step 1: Read the current Docker files.**

Open and report the complete contents of:
- `Dockerfile`
- `docker-compose.yml`
- `nginx.conf`
- Any `.dockerignore`

**Step 2: What's missing for the React frontend?**

- Where is the React app's build output? (`frontend/dist/`? `frontend/build/`?)
- What build command produces it? (`npm run build`? `vite build`?)
- What nginx config changes are needed to serve it instead of `organizer_v5.html`?
- Does the React app need environment variables at build time? (API URL, etc.)

**Step 3: What environment variables are required?**

Search the entire codebase for:
- `os.environ` / `os.getenv` references
- `.env` file contents
- Any hardcoded credentials or paths

Produce a complete `.env.example` with every required variable, a description, and a safe default value.

**Step 4: The checklist.**

Produce a numbered checklist: "To deploy this platform from scratch, you would need to:"

1. [ ] ...
2. [ ] ...
3. [ ] ...

Include: database setup, data loading, API server, frontend build, nginx config, auth setup, MV refresh, and health verification.

**Deliverable:** A complete deployment checklist and `.env.example` file.

---

## Investigation 6: Dead Code and Safe-to-Remove Inventory

Your audit found 151 database objects with zero code references and mentioned ~55 analysis scripts. Produce the specific safe-to-remove list.

**Step 1: Database objects.**

From your `db_object_reference_scan_2026-02-26.json` artifact, extract:
- Tables with 0 code references AND 0 rows → definitely safe to drop
- Tables with 0 code references AND >0 rows → check if any view or MV depends on them
- Views with 0 code references → check if any other view depends on them
- Materialized views with 0 code references → safe to drop if no API uses them

For each candidate, verify it's not referenced by:
- Any view definition (`pg_views.definition`)
- Any MV definition
- Any API endpoint
- Any test file

**Step 2: Python scripts.**

Search `scripts/` and `src/` for files that are:
- Never imported by another file
- Never referenced in any test
- Never referenced in PROJECT_STATE.md or PIPELINE_MANIFEST.md
- Have version suffixes suggesting they're superseded (e.g., `analyze_v1.py`, `analyze_v2.py` when `analyze_v3.py` exists)

**Step 3: Frontend files.**

Check for:
- React components never imported by any other component
- Dead routes (defined in router but no navigation link points to them)
- Unused CSS/style files

**Step 4: Produce three lists.**

**List A — Safe to delete immediately (no dependencies found):**
| Type | Name | Size | Reason |

**List B — Probably safe but verify first (low-confidence references):**
| Type | Name | Size | What to check |

**List C — Keep but archive (has data, no active use):**
| Type | Name | Size | Reason to keep |

**Deliverable:** Three concrete lists with specific names, not categories. "Drop table X" not "drop unused tables."

---

## OUTPUT FORMAT

For each investigation:
1. **The question** (one sentence)
2. **The evidence** (file paths, line numbers, code snippets)
3. **The deliverable** (the concrete artifact requested)
4. **Caveats** (what you couldn't verify and why)

End with a summary of how these findings affect the Tier 0-1 roadmap items from the synthesis.
