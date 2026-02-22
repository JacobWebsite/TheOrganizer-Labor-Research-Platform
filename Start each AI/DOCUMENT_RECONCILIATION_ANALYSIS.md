# Document Reconciliation Analysis
## What Needs to Change So All 5 Documents Work Together

**Date:** February 21, 2026
**Documents reviewed:**
1. `UNIFIED_PLATFORM_REDESIGN_SPEC.md` (1,074 lines) — the brand-new platform redesign spec
2. `PROJECT_DIRECTORY.md` (1,289 lines) — complete file/system reference
3. `CLAUDE.md` (771 lines) — AI assistant context document
4. `PROJECT_STATE.md` (646 lines) — shared multi-AI context + session handoffs
5. `UNIFIED_ROADMAP_2026_02_19.md` (628 lines) — master roadmap

---

## THE BIG PICTURE PROBLEM

Right now, an AI tool reading all 5 documents would be **confused** about some very basic things:

- How many scoring factors are there? (7 or 8, depending which doc you read)
- How many tests pass? (441, 456, or 457, depending which doc you read)
- What's the frontend built with? (Vanilla JS or React?)
- Which roadmap filename is correct? (02_17 or 02_19?)
- What's the current plan? (The old roadmap phases, or the new redesign spec?)

The root cause: **the Redesign Spec was created AFTER the other 4 documents, and none of them know it exists.** The Redesign Spec makes several major decisions that supersede things described in the Roadmap, CLAUDE.md, and PROJECT_STATE — but nobody updated those docs yet.

Below is every inconsistency I found, organized by severity.

---

## CATEGORY 1: ROLE CONFUSION — WHO DOES WHAT?

### Problem: Massive overlap between documents

Right now, the same information appears in multiple places, often with slightly different numbers. This is the #1 source of confusion. Here's what each document TRIES to do:

| Document | Current Role | Overlap With |
|----------|-------------|-------------|
| **CLAUDE.md** | AI reference: schema, gotchas, scoring, matching, API endpoints | PROJECT_STATE (schema, decisions), PROJECT_DIRECTORY (schema, pipeline) |
| **PROJECT_STATE.md** | Multi-AI context: quick start, DB inventory, status, decisions, session logs | CLAUDE.md (schema, quick start), ROADMAP (status, decisions) |
| **PROJECT_DIRECTORY.md** | File/system catalog: every file, every table, every script | CLAUDE.md (schema, scripts), PROJECT_STATE (DB inventory, pipeline) |
| **ROADMAP** | Planning: what's wrong, what to do, what comes later | PROJECT_STATE (status, decisions), REDESIGN SPEC (future plans, scoring) |
| **REDESIGN SPEC** | Frontend + scoring redesign: how the NEW platform should look and work | ROADMAP (scoring factors, future plans) |

**The fix:** Each document needs a clearly defined lane, and the others should POINT TO IT instead of duplicating. Proposed:

| Document | New Role | Rule |
|----------|----------|------|
| **CLAUDE.md** | "How to work on this codebase" — schema, gotchas, matching details, API reference, dev workflow | Only place for technical implementation details |
| **PROJECT_STATE.md** | "What just happened" — session handoffs, latest numbers, active bugs | Only place for session logs and live status |
| **PROJECT_DIRECTORY.md** | "What exists and where" — file catalog, database inventory | Only place for comprehensive file/table listings |
| **ROADMAP** | "What's wrong and what to do" — problems, phases, decisions | Only place for the plan and problem tracking |
| **REDESIGN SPEC** | "What the new platform should be" — design, scoring, UX, pages | Only place for redesign decisions |

---

## CATEGORY 2: NUMBERS THAT DISAGREE

### 2a. Test counts

| Document | Says |
|----------|------|
| CLAUDE.md | "441 automated tests (2 known failures)" |
| PROJECT_STATE (header) | "456 pass / 1 fail" |
| PROJECT_STATE (quick start) | "457 tests" |
| PROJECT_DIRECTORY | "456 passing / 1 failing" |
| ROADMAP | "441 (439 passing, 2 known failures)" |

**What happened:** Tests were added over time. The 441 number is from the Feb 19 audit. The 456/457 number is from the Feb 20 session (15+ tests added during B4 completion work).

**Fix:** All documents should say **456 passing / 1 known failure** (the hospital abbreviation test). The second "known failure" (test_osha_count_matches_legacy_table) was apparently resolved during B4 re-runs.

### 2b. API router count

| Document | Says |
|----------|------|
| CLAUDE.md | "19 routers" |
| PROJECT_DIRECTORY | "20 routers" |
| ROADMAP | "19 routers" |

**Fix:** Count the actual router files and use one number everywhere. PROJECT_DIRECTORY is the most recent (Feb 20) so 20 is likely correct.

### 2c. View count

| Document | Says |
|----------|------|
| PROJECT_STATE | "186 views" |
| PROJECT_DIRECTORY | "123 views" |

**Fix:** One of these was generated at a different time, or one counts materialized views differently. Re-run the inventory script and use one number.

### 2d. Table count

| Document | Says |
|----------|------|
| PROJECT_STATE | "178 tables" |
| PROJECT_DIRECTORY | "174 tables" |
| ROADMAP | "174+ tables" |

**Fix:** Same issue — re-run inventory, use one number everywhere.

### 2e. Unified Match Log row count

| Document | Says |
|----------|------|
| CLAUDE.md | "1,160,702" |
| ROADMAP | "1,160,702" |
| PROJECT_STATE | "1,738,115" |
| PROJECT_DIRECTORY | "1,738,115" |

**What happened:** The B4 re-runs (Feb 18-20) added ~577K rows. CLAUDE.md and ROADMAP have the pre-re-run number. PROJECT_STATE and PROJECT_DIRECTORY have the post-re-run number.

**Fix:** All should say **1,738,115** (the current number).

### 2f. SAM entities count

| Document | Says |
|----------|------|
| CLAUDE.md | "826,042" |
| PROJECT_DIRECTORY | "834,725" |

**Fix:** Check actual table and use one number.

### 2g. mv_organizing_scorecard row count

| Document | Says |
|----------|------|
| PROJECT_STATE | "212,441" |
| PROJECT_DIRECTORY | "212,441" |
| ROADMAP | "199,414" (in problem list), "200,890 → 199,414 → 195,164" (in investigation) |

**What happened:** The MV was refreshed during Phase B4 completion. The roadmap has the older number.

**Fix:** All should use the current refreshed count (212,441).

### 2h. Splink name similarity floor

| Document | Says |
|----------|------|
| CLAUDE.md | ">= 0.65" |
| ROADMAP | ">= 0.70 default" |

**What happened:** The Codex Feb 19 session raised the default from 0.65 to 0.70.

**Fix:** CLAUDE.md should say 0.70 (configurable via `MATCH_MIN_NAME_SIM`, was 0.65 before Feb 19).

---

## CATEGORY 3: THE REDESIGN SPEC VS EVERYTHING ELSE

This is the biggest structural problem. The Redesign Spec makes major decisions that the other documents don't know about.

### 3a. Scoring: 7 factors vs 8 factors

**Roadmap says 7 factors:**
1. OSHA Safety Violations
2. NLRB Election Activity Nearby
3. Wage Theft Violations
4. Government Contracts
5. Union Proximity
6. Financial Indicators & Industry Viability
7. Employer Size

**Redesign Spec says 8 factors:**
1. OSHA Safety Violations
2. NLRB Election Activity Nearby
3. Wage Theft & Labor Law Violations
4. Government Contracts
5. Union Proximity
6. Financial Indicators & Industry Viability
7. Employer Size
8. **Statistical Similarity** (NEW — Gower distance output as a scoring signal)

**Also different:** The Redesign Spec adds specific weights, exact formulas with half-life decay curves, and percentile-based tier breakpoints (Priority/Strong/Promising/Moderate/Low) instead of the Roadmap's fixed-threshold tiers (TOP 7+, HIGH 5+, MEDIUM 3.5+, LOW <3.5).

**Fix:** The Roadmap needs to acknowledge that its scoring section has been superseded by the Redesign Spec's Section 2. The Roadmap should POINT TO the Redesign Spec rather than defining its own scoring system.

### 3b. Frontend technology

**Current state (all 4 older docs):** Vanilla JS SPA (`organizer_v5.html`) with Tailwind, Chart.js, Leaflet.

**Redesign Spec says:** Migrate to React + Vite, Tailwind, shadcn/ui, Zustand for state management, TanStack Query for data fetching. 6-phase build order. Docker Compose deployment with nginx + API + postgres.

**None of the other documents mention this migration.** The Roadmap's "Wave 4: Major frontend redesign" is now fully specified in the Redesign Spec, but the Roadmap doesn't know that.

**Fix:** The Roadmap should reference the Redesign Spec for frontend plans. CLAUDE.md's "Frontend Interfaces" section should note the upcoming React migration.

### 3c. Tier naming

| Document | Tier Names |
|----------|-----------|
| Roadmap | TOP, HIGH, MEDIUM, LOW |
| CLAUDE.md (legacy) | TOP >=30, HIGH >=25, MEDIUM >=20, LOW <20 |
| CLAUDE.md (unified) | TOP 7+, HIGH 5+, MEDIUM 3.5+, LOW <3.5 |
| Redesign Spec | Priority, Strong, Promising, Moderate, Low (percentile-based) |

**Fix:** The Redesign Spec's tier names supersede everything. Old tier names are legacy.

### 3d. Task list conflicts

The Redesign Spec Section 16 has its own 19-item Claude Code Task List. The Roadmap has Phases A-F with different tasks. Some overlap, some conflict, some are in one but not the other.

**Fix:** Need to reconcile these into one authoritative task list. The Redesign Spec tasks (React build, BMF load, Deep Dive infrastructure, etc.) should be integrated into the Roadmap phases, or the Roadmap should point to the Redesign Spec for post-Phase-F work.

---

## CATEGORY 4: STALE REFERENCES

### 4a. Roadmap filename

CLAUDE.md, PROJECT_STATE, and PROJECT_DIRECTORY all reference `UNIFIED_ROADMAP_2026_02_17.md`. The actual current file is `UNIFIED_ROADMAP_2026_02_19.md`.

**Fix:** Update all references to the correct filename.

### 4b. Phase completion status is stale in the Roadmap

The Roadmap was written when Phases A-F were the plan. Since then:
- Phases A, B, D1, E1-E3 are DONE
- Phase B4 re-runs are DONE
- The Redesign Spec now defines what comes AFTER Phase F

But the Roadmap still describes these phases as future work. The strikethrough notation helps, but it's confusing.

**Fix:** The Roadmap's Part 3 needs a clear "CURRENT STATUS" header showing which phases are complete, which are in progress, and which are remaining. Better yet, just move completed phases to a "Completed Work" section and keep Part 3 focused on what's still TODO.

### 4c. CLAUDE.md's scoring section describes the OLD system

CLAUDE.md's "Key Features" section (#1 and #7) describes the legacy scoring systems in detail (8 factors with max 80 points, Mergent 62-point scale). The Redesign Spec defines a completely new scoring approach.

**Fix:** CLAUDE.md should note that the scoring system described there is the CURRENT (legacy) system, and point to the Redesign Spec for the new scoring design that will replace it.

### 4d. The Redesign Spec is not listed in any document's file references

None of the 4 other documents mention `UNIFIED_PLATFORM_REDESIGN_SPEC.md` in their file listings, reference docs, or critical files sections.

**Fix:** Add it to CLAUDE.md's Reference Documentation table, PROJECT_STATE's Key Files table, and PROJECT_DIRECTORY's Critical Files section.

---

## CATEGORY 5: STRUCTURAL ISSUES

### 5a. PROJECT_STATE.md has become a dumping ground

PROJECT_STATE is 646 lines, and most of it is session handoff notes from February 17-20. These session logs are valuable for continuity between work sessions, but they make the document unwieldy. The "quick start" and "current status" sections — the things an AI tool needs FIRST — are buried.

**Fix:** Move older session handoff notes (anything before the last 2-3 sessions) to `docs/session-summaries/`. Keep PROJECT_STATE focused on: (1) Quick Start, (2) Current Status, (3) Last 2-3 session summaries.

### 5b. PROJECT_DIRECTORY duplicates CLAUDE.md's schema section

Both documents have extensive database schema tables. They give different numbers in some cases. An AI tool reading both would have to decide which to trust.

**Fix:** CLAUDE.md keeps the schema details (since it's the "how to work on this" doc). PROJECT_DIRECTORY keeps only the summary inventory (table count, top 15 by row count, MV list) and says "See CLAUDE.md for full schema details."

### 5c. The Roadmap's decisions list is duplicated in PROJECT_STATE

The 25 planning decisions from Feb 16-17 appear in both the Roadmap (Appendix B) and PROJECT_STATE (Section 5). They're identical, which means one is unnecessary.

**Fix:** Keep in Roadmap (it's the planning doc). PROJECT_STATE Section 5 should just say "See UNIFIED_ROADMAP Appendix B for full decisions list" plus any NEW decisions made after the roadmap was written.

---

## RECOMMENDED ACTION PLAN

Here's what I'd suggest doing, in priority order:

### Step 1: Add the Redesign Spec to all document references
Quick fix — just add a line to CLAUDE.md, PROJECT_STATE, PROJECT_DIRECTORY, and ROADMAP acknowledging the Redesign Spec exists and what it covers. This way, no AI tool is surprised by it.

### Step 2: Fix the disagreeing numbers
Pick the correct current number for each metric (tests, routers, views, tables, UML rows, etc.) and update all 5 documents. This is mechanical but important.

### Step 3: Reconcile scoring system descriptions
The Roadmap's scoring section and the Redesign Spec's scoring section need to be consistent. Simplest approach: Roadmap says "See UNIFIED_PLATFORM_REDESIGN_SPEC.md Section 2 for the complete redesigned scoring system" and keeps only a brief summary.

### Step 4: Trim PROJECT_STATE session logs
Move everything older than the last 3 sessions to docs/session-summaries/. This makes PROJECT_STATE readable again.

### Step 5: Resolve document role overlaps
Add a "Document Purpose" header to each doc that explicitly says what it covers and what to find elsewhere. Example for CLAUDE.md: "This document covers technical implementation details. For project status, see PROJECT_STATE.md. For the plan, see the ROADMAP. For redesign decisions, see the REDESIGN SPEC. For file locations, see PROJECT_DIRECTORY.md."

### Step 6: Reconcile task lists
The Redesign Spec's Section 16 task list and the Roadmap's Phase A-F structure need to be harmonized into one plan. The Redesign Spec tasks should either be mapped into the Roadmap's phase structure, or the Roadmap should explicitly say "post-Phase-F work is defined in the Redesign Spec."

---

## QUICK REFERENCE: EVERY SPECIFIC NUMBER TO FIX

| Metric | Correct Value | Wrong In |
|--------|--------------|----------|
| Tests passing | 456 | CLAUDE.md (441), ROADMAP (441) |
| Tests failing | 1 | CLAUDE.md (2), ROADMAP (2) |
| API routers | 20 | CLAUDE.md (19), ROADMAP (19) |
| UML rows | 1,738,115 | CLAUDE.md (1,160,702), ROADMAP (1,160,702) |
| Scoring factors | 8 (new design) | ROADMAP (7) |
| Tier names | Priority/Strong/Promising/Moderate/Low | CLAUDE.md (TOP/HIGH/MEDIUM/LOW), ROADMAP (same) |
| Splink name floor | 0.70 default | CLAUDE.md (0.65) |
| Roadmap filename | UNIFIED_ROADMAP_2026_02_19.md | CLAUDE.md (_02_17), PROJECT_STATE (_02_17), PROJECT_DIRECTORY (_02_17) |
| mv_organizing_scorecard | 212,441 | ROADMAP (199,414) |
| Redesign Spec exists | Yes | Not mentioned in any other doc |
