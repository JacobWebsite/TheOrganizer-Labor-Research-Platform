# Independent Platform Audit — Labor Relations Research Platform
**Date issued:** 2026-02-18
**For:** Gemini / Codex / Claude Code — run separately, do not share findings until all three are complete
**Prepared by:** Jacob (platform owner)

---

## What This Is and How to Approach It

This is an open-ended independent audit. You are being asked to investigate a codebase and database that has been built over many months across many AI sessions and human work sessions. It is a real working system, not a toy project. It has real problems, and it has things that work well — your job is to find out which is which.

**The most important thing:** treat every claim in every document as a hypothesis, not a fact. The project uses three AI tools working in parallel — Claude Code, Codex, and Gemini — and documentation written during one session frequently describes a plan or a partial fix as if it were a completed, verified fact. Your job is to find where that has happened.

Three AI systems are running this same audit independently. Your outputs will be compared directly. The comparison has the most value when each of you investigates things the others might not think to look at. This means: follow your instincts. If something looks suspicious, investigate it. If a number doesn't add up, dig into why. If you find something that was never mentioned in any document, that may be the most important finding you produce.

**Do not soften findings. Do not assume good intent explains a discrepancy. Report what you observe.**

---

## Project Context

This is a labor relations research platform that helps workplace organizers identify and prioritize employers for organizing campaigns. It pulls together data from 18+ government databases — OSHA safety violations, NLRB union elections, Department of Labor wage theft enforcement, IRS nonprofit filings, federal contractor registries, SEC company filings, and more — and connects all of it to a master list of employers derived from Department of Labor F-7 filings.

The F-7 filing is the Department of Labor form that unions file to report which employers they have bargaining relationships with. This gives the platform its foundation: 146,863 employer records, each representing an employer where a union has (or had) a contract. Everything else in the system gets matched back to these employers.

**The core data flow, simplified:**
Raw government data → loaded into PostgreSQL database → matching system figures out which OSHA record, NLRB record, wage theft case, etc. belongs to which F-7 employer → scoring system combines all those signals into an "organizing score" → an API serves the data → an HTML frontend displays it.

**Database:** PostgreSQL, database name `olms_multiyear`, localhost:5432, user `postgres`. Credentials are in `.env` at the project root. The connection pattern used by all scripts is:
```python
import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection
conn = get_connection()
```

**Project root:** `C:\Users\jakew\Downloads\labor-data-project`

**Start by reading these four documents carefully — not just skimming:**
- `PROJECT_STATE.md` — current status, known issues, and session handoff notes from recent AI sessions
- `CLAUDE.md` — full database schema reference and project operating instructions
- `UNIFIED_ROADMAP_2026_02_17.md` — the strategic plan and what phase of work the project is in
- `PIPELINE_MANIFEST.md` — which scripts are active and in what order they run

These documents are your starting point, not your conclusion. Every number, status claim, and "FIXED" notation in them is a hypothesis to be verified.

---

## How to Report Your Findings

Use this format for each discrete finding:

- **What I investigated**
- **What the documentation claims** — quote the exact language if possible
- **What I actually observed** — the query result, file content, or test output
- **Severity:** CRITICAL / HIGH / MEDIUM / LOW
- **Recommended action**

You may have as many findings as you want. You are not limited to the six areas described below. If you find something important that falls outside those areas, report it in a section called **"Findings Outside the Audit Scope"** — this is encouraged, not optional.

---

## The Six Investigation Areas

These areas give you a starting orientation. Within each one, you are expected to go further than what is described here. The questions are entry points, not a complete list. Write your own queries. Read files you think are relevant. Follow any thread that looks suspicious.

---

### Area 1: Documentation vs Reality

The project has three primary documents that are supposed to reflect the same current reality: `PROJECT_STATE.md`, `CLAUDE.md`, and `UNIFIED_ROADMAP_2026_02_17.md`. These are written and updated in different sessions by different AI tools. In a multi-AI project like this, documentation drift is one of the most persistent and dangerous problems — because every subsequent AI session reads the docs and makes decisions based on what they claim.

Investigate systematically. Pick claims that are specific and verifiable — row counts, issue statuses marked "FIXED," dates, test counts, match rates — and check them against the live database and codebase. Where the documents contradict each other or contradict reality, that is a finding worth reporting regardless of how minor it seems.

Run the automated test suite and report exactly what you observe:
```cmd
cd C:\Users\jakew\Downloads\labor-data-project
py -m pytest tests/ -q 2>&1
```

Go beyond the obvious contradictions. The more subtle documentation drift is often the most dangerous, because it causes the next AI session to build on a faulty foundation without realizing it.

---

### Area 2: The Matching Pipeline

The matching system is the engine that connects OSHA records, NLRB records, wage theft cases, and other government data to the F-7 employer list. It uses a tiered approach — starting with the most reliable methods (exact tax ID match) and falling back to increasingly fuzzy methods when those fail. The quality of every downstream feature — the scorecard, employer profiles, corporate hierarchy — depends entirely on this matching being accurate.

A major matching re-run (called "Phase B4") just completed for the OSHA database. The checkpoint file at `checkpoints/osha_rerun.json` records what happened batch by batch. The code that runs the matching lives in `scripts/matching/`, primarily `deterministic_matcher.py` and `run_deterministic.py`. The results live in `unified_match_log`.

Investigate the quality and completeness of the current matching state. Think like a skeptic: what does "successful" actually mean for a matching system, and does the evidence support that characterization? Look at confidence bands, method distributions, and whether the other data sources (beyond OSHA) have been re-run as planned. Read the matching code and ask whether the logic is airtight or whether there are scenarios it doesn't handle correctly.

Don't limit yourself to what the documentation flags as a known concern. Look at the actual match data and report what you see.

---

### Area 3: The Scoring System

The organizing scorecard is the platform's primary output — what an organizer actually looks at when deciding where to focus a campaign. It scores each employer on seven factors and combines them into a single score used to rank organizing opportunities.

The platform recently replaced an older scorecard with a new "unified" one that is supposed to cover all 146,863 employers using "signal-strength scoring" — the design principle being that missing data is excluded from the calculation rather than penalized. The code is in `scripts/scoring/build_unified_scorecard.py`. The results are in `mv_unified_scorecard`.

Investigate whether the code actually implements the stated design principle, whether the scores make intuitive sense when you look at the distribution, and whether the materialized views reflect current data or are stale. Also look at the relationship between the old scorecard (`mv_organizing_scorecard`) and the new one — do they agree for employers that appear in both, and what does any disagreement tell you?

There may be things about the scoring logic that nobody has examined carefully. Look at it fresh and report what you find, including anything that seems off even if you can't immediately explain why.

---

### Area 4: Data Gaps and Missing Connections

The platform has acknowledged gaps — places where data exists in the database but isn't connected to anything useful, or where connections were supposed to be made but something went wrong.

The two documented gap categories are: "missing unions" (union file numbers in the relations table that don't match any union in the master table, making those union-employer relationships invisible to users), and unused OLMS annual report data (tables like `ar_membership`, `ar_disbursements_total`, `ar_assets_investments` that were loaded but never integrated into scoring or search).

Investigate both of those. But also look beyond them. Walk through the database schema and ask: are there tables with significant data that don't appear to be connected to anything? Are there match tables where the rates seem surprising — either too high or too low? Are there tables mentioned in the documentation that don't actually exist, or tables that exist but aren't mentioned anywhere?

Look at the data sources with low match rates (IRS 990 at ~12%, SAM.gov at ~7.5%) and investigate whether those rates reflect real limitations or whether bugs or methodology problems are causing legitimate matches to be missed.

---

### Area 5: The API and Frontend

The API connects the database to the HTML frontend that users actually see. The frontend (`files/organizer_v5.html`) is what an organizer would use in practice.

Start the API:
```cmd
py -m uvicorn api.main:app --reload --port 8001
```

Then explore it as an investigator, not just as a tester. The API documentation at `http://localhost:8001/docs` will show you what's registered. Look at the actual router files in `api/routers/` to understand what's supposed to exist. Test endpoints that matter — particularly anything related to the scorecard, corporate hierarchy, and administrative functions.

Pay attention to: whether the documented ~160 endpoints are all actually present; whether endpoints that were described as "fixed" in session notes actually work; whether authentication is being enforced where the documentation says it should be; and whether the response data looks correct or suspicious.

Also look at the frontend HTML file in a browser with the API running. Does the interface work? Are there features that are broken or showing no data? The frontend is what an actual user would see — any gap between what it promises and what it delivers is worth documenting.

---

### Area 6: Infrastructure, Code Health, and What Nobody Thought to Ask

This area is deliberately open. Investigate anything about the project's health that doesn't fit the other categories.

The project went through a major reorganization that supposedly reduced ~530 active scripts to ~120. Look at what's actually in the `scripts/` directory and form your own view. Check the database size, index state, and credential patterns. Look at whether the test suite is actually testing the things that matter.

More importantly: look for things that nobody asked about. Walk through the database and find tables or data patterns that seem strange. Read parts of the codebase that the documentation doesn't emphasize. Look at the archive directory and think about whether anything there should have stayed active. Check whether recent changes introduced problems that the tests don't catch.

Some questions to get you started — but do not limit yourself to these:
- Are there tables much larger or smaller than you'd expect given what the documentation says?
- Are there views or materialized views that reference tables or columns that no longer exist?
- Are there hard-coded values (dates, thresholds, IDs) that look like they were set temporarily and never updated?
- Does anything in the codebase suggest a feature was started and never finished?
- Are there any places where two systems are doing the same work independently, creating inconsistency?

Report whatever you find, whether or not it fits a named category.

---

## Final Deliverable

Write your findings throughout, then close with four sections:

**Section 1: What Is Actually Working Well**
List 3-5 things you verified are functioning correctly, with the specific evidence you used. Be concrete — "the matching pipeline seems fine" is not useful; the specific match counts, confidence rates, and how they compare to expectations is useful.

**Section 2: Where Documentation Contradicts Reality**
For every gap between a documented claim and your actual observation: quote the claim, show the observation, rate the severity. Do not trim this section for brevity — if you found twenty contradictions, list all twenty.

**Section 3: The Three Most Important Things to Fix**
Your top three findings, prioritized by real-world impact on someone using this platform to make actual organizing decisions. For each: what the problem is, why it matters in practice, and what fixing it would require.

**Section 4: Things Nobody Knew to Ask About**
Anything you found that doesn't appear in the project documentation — problems that were never identified, gaps that were never noticed, patterns that no one has commented on. This section is where the most valuable audit findings often come from. If you found nothing in this category, say so explicitly.

---

## Why Three Independent Audits

Each AI brings different instincts and reads the same materials differently. Claude Code will tend toward live database investigation and code execution. Codex will tend toward close code logic review. Gemini will tend toward cross-referencing documents and spotting structural inconsistencies. By not coordinating, each follows its own threads.

The comparison becomes meaningful when all three independently find the same problem — that confirms something is definitely wrong. It also becomes meaningful when they disagree — that reveals where something is genuinely ambiguous and needs a human decision.

The only rule: no finding counts unless it is grounded in something you actually ran, read, or observed. A document that says "FIXED" is a claim. A query result is evidence.
