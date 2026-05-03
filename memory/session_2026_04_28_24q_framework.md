# Session 2026-04-28 — 24 Questions Framework Adoption

## Changes Made

Strategic / framing session. No code changes. Created four vault documents establishing Tom Juravich's 24 Questions Corporate Research Framework ([strategiccorporateresearch.org](https://strategiccorporateresearch.org)) as the canonical organizing principle for all post-beta platform work.

**Vault files created:**
- `Decisions/2026-04-28 - Adopt 24 Questions Corporate Research Framework.md` — adoption decision (rationale, scope, what stays vs. changes, alternatives considered).
- `Systems/24 Questions Framework.md` — canonical reference: 24 questions, three organizational levels (Command & Control / Operational / External Stakeholders), four Sources of Power (institutional / structural / coalitional / symbolic), five deliverable artifacts.
- `ROADMAP_24Q_ADDENDUM_2026_04_28.md` — every existing roadmap item mapped to the question(s) it answers + 46 new items (24Q-1 through 24Q-46) in P0/P1/P2 bands, sequenced post-beta.

**Vault files modified:**
- `CLAUDE.md` — new "Organizing Principle" section after Critical Rules; Related wikilinks updated to point to all three new docs and the current roadmap (MERGED_ROADMAP_2026_04_25 instead of the obsolete _04_07); frontmatter date bumped to 2026-04-28.

**Auto-memory:**
- `project_24q_framework_adopted.md` (new) + one-line pointer in MEMORY.md.

## Key Findings

- **Coverage audit verdict:** 8 questions strong / 6 medium / 5 weak / 5 missing entirely.
- **Five "Missing" gaps:** Q9 Stockholders, Q10 Board, Q11 Lenders, Q21 Environmental, Q24 Political. All five map to high-leverage SCR pressure points and have zero existing data + zero existing roadmap items.
- **FEC API key gotcha:** P0 #26 marked DONE 2026-04-08 ("FEC API key moved to .env + rotated"). The key sits unused — no FEC ETL was ever built. 24Q-38 closes this.
- **The platform's deliverable layer is missing entirely.** SCR's value beyond data taxonomy is its five structured artifacts (Research Summary, Strategic Targets, Sources of Power chart, Campaign Calendar, Union Capacity Assessment). The platform currently produces narrative dossiers + a profile page — neither maps to SCR's deliverables. 24Q-42 through 24Q-46 close this.
- **Eight questions are already strong**: Q1 Basic Info (master_employers, Mergent, SEC, GLEIF, IRS), Q3 Facilities (OSHA establishments, geocoded master), Q4 Workforce (V12 demographics, OES, QCEW, ACS), Q5 Financials (SEC XBRL, Mergent), Q12 Parent (corporate_ultimate_parents), Q13 Subsidiaries (Ex21 POC + CorpWatch 773K edges), Q15 Competitors (Gower 18.3M comparables), Q20 Safety (OSHA + SOII).

## Roadmap Updates

**Added 46 new items** (24Q-1 through 24Q-46), grouped by question:
- Q2 Products: 24Q-1
- Q5 Financials: 24Q-2/3 (ratio worksheet + peer comparison)
- Q6 History: 24Q-4
- Q7 Strategy: 24Q-5/6 (profit center + growth plan)
- Q8 Management: 24Q-7/8 (surface execs + reconsider CEO pay ratio)
- Q9 Stockholders: 24Q-9/10/11 (13F ETL + UI + Form 4)
- Q10 Board: 24Q-12/13/14 (DEF14A + interlocks + UI)
- Q11 Lenders: 24Q-15/16 (credit agreements + UCC-1)
- Q13 Subsidiaries: 24Q-17 (promote Ex21 to production — also closes REG-6)
- Q14 Industry: 24Q-18/19 (HHI + M&A activity)
- Q16 Suppliers: 24Q-20/21
- Q17 Distribution: 24Q-22/23
- Q18 Utilities: 24Q-24/25
- Q19 Customers: 24Q-26/27/28
- Q21 Environmental: 24Q-29/30/31 (EPA ECHO ETL + match + UI)
- Q22 Legal: 24Q-32/33/34 (CourtListener + SEC enforcement + state AG)
- Q23 Community: 24Q-35/36/37 (990 Schedule I/G + philanthropy + WARN)
- Q24 Political: 24Q-38/39/40/41 (FEC + LDA + state political + UI)
- Deliverables: 24Q-42 (24-Q dossier restructure), 24Q-43 (Sources of Power view), 24Q-44 (Strategic Targets view), 24Q-45 (Campaign Workspace), 24Q-46 (Union Capacity Assessment integration)

**24Q-P0 wave (post-beta, ~10 weeks):** 24Q-9/10, 24Q-12/13/14, 24Q-29/30/31, 24Q-38/39/41, 24Q-42.

**Pre-beta path unchanged.** All R7 critical-path items in MERGED_ROADMAP_2026_04_25 remain priority through June 5 launch. 24Q is a post-beta organizing principle. Open R7 items: R7-1, R7-7, REG-2/3/4/5/6/7, DISABLE_AUTH flip, PHONETIC_STATE deactivation.

## Debugging Notes

- **MEMORY.md size warning:** auto-memory MEMORY.md is at 32.7KB (limit 24.4KB). Index entries are too long. Pointer for this session is one line; future entries should follow that pattern.
- **CLAUDE.md frontmatter date** was last_updated 2026-04-07 before this session. Bumped to 2026-04-28 with framework section added.
- **Active-roadmap link in CLAUDE.md Related** was still pointing at MERGED_ROADMAP_2026_04_07.md (obsolete since 2026-04-26 R7-aware roadmap shipped). Corrected to MERGED_ROADMAP_2026_04_25.md as a side-effect of this session.
- **No code, no tests, no MVs touched.** Pure documentation session.
