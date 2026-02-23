# Full Platform Audit — Gemini (Round 4, Part 2 of 2)
## Labor Relations Research Platform
**Date:** February 22, 2026
**Version:** Round 4 — Post-Codex merge, post-React frontend, post-ULP integration

**⚠️ This is Part 2 of 2. You should have already completed Part 1 (Sections 1-6). Continue adding to your report at `docs/AUDIT_REPORT_GEMINI_2026_R4.md`.**

---

## QUICK REFRESH — Where We Are

You've already audited:
- Section 1: Database Inventory
- Section 2: Data Quality Deep Dive
- Section 3: Matching Pipeline Integrity
- Section 4: Scoring System Verification
- Section 5: API & Endpoint Testing
- Section 6: Frontend & React App

Now complete the remaining sections below.

---

## SECTION 7: Master Employer Table & Deduplication

**What this does:** Audits the new master employer table — the biggest structural addition since the last audit.

**Why it matters:** The master table is supposed to be the single source of truth for ALL employers — union and non-union. If it has duplicates, bad data, or broken links, the whole "non-union target discovery" feature won't work.

**Key context:** The master table was seeded from 4 sources:
- F7 (union employers): 146,863 rows
- SAM (federal contractors): 797,226 rows
- Mergent (business data): 54,859 rows
- BMF (IRS nonprofits): 2,027,342 rows
- **Total before dedup:** 3,026,290
- **After dedup:** ~2,736,890 (289,400 merged)

**Steps:**
1. Check `master_employers` row count and breakdown by `source_origin` (F7, SAM, Mergent, BMF)
2. Check dedup quality: how many records were merged (expected: 289,400 merged from 3,026,290 → 2,736,890)?
3. Sample 20 merged records: did the dedup correctly identify these as the same employer?
4. Check for remaining duplicates: are there employers that appear multiple times with slightly different names?
5. Check the `data_quality_score` distribution: how many employers have a score above 60? Below 20?
6. Check `is_labor_org` flag on master_employers: 6,686 expected flagged. Does this look right?
7. Check `master_employer_source_ids`: does every master employer have at least one source ID?
8. Check links back to source tables: pick 10 random master employers and verify their source_ids correctly point to real records in f7, SAM, irs_bmf, etc.
9. Check the master API endpoints: do `/api/master/search`, `/api/master/stats`, `/api/master/non-union-targets` return consistent data?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 8: Scripts, Pipeline & Code Quality

**What this does:** Checks the codebase for broken scripts, dead code, security issues, and technical debt.

**Why it matters:** Broken scripts mean data can't be updated. Dead code makes everything harder to understand and maintain. Security issues could expose sensitive data.

**Key context:** The project has 134 active scripts (down from 530+ before reorganization). The full pipeline is documented in `PIPELINE_MANIFEST.md`. About 400 dead scripts have been moved to `archive/old_scripts/`.

**Steps:**
1. Verify the PIPELINE_MANIFEST.md is accurate: pick 10 random scripts listed as "active" and confirm they exist and are functional
2. Check for scripts that reference old table names or deleted tables
3. Check for hardcoded credentials: `grep -r "Juniordog33" scripts/` — should find ZERO results (was a known problem, supposedly fixed)
4. Check for hardcoded file paths: how many scripts still use `C:\Users\jakew\Downloads\` hardcoded paths instead of relative paths or config?
5. Check the broken password pattern: `password='os.environ.get(...)` — was this actually fixed in all 347 scripts?
6. Check `db_config.py`: is it properly using environment variables?
7. Run the test suite: `pytest tests/ -v` — do all tests pass? Which tests are new since the last audit?
8. Check test coverage: are there major features with NO tests?
9. Check for abandoned experiments: are there scripts in active directories (not archive/) that do nothing useful?
10. Check the archive: was the cleanup actually done (expected: ~400 dead scripts moved to `archive/old_scripts/`)?

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 9: Documentation Accuracy

**What this does:** Checks whether the documentation matches reality.

**Why it matters:** Three AI tools use these documents to understand the project. If the docs are wrong, the AIs will make wrong decisions. This was a major problem identified in the Document Reconciliation Analysis from February 21.

**Key context:** There are 5 core documents:
1. `CLAUDE.md` — Technical implementation reference
2. `PROJECT_STATE.md` — Session handoffs and live status
3. `PROJECT_DIRECTORY.md` — File and system catalog
4. `UNIFIED_ROADMAP_2026_02_19.md` — Master plan
5. `UNIFIED_PLATFORM_REDESIGN_SPEC.md` — Frontend and scoring redesign spec

A reconciliation analysis found many inconsistencies between these documents, including disagreeing numbers, stale references, and documents not knowing about each other.

**Steps:**
1. Check every number in CLAUDE.md against the actual database — flag discrepancies
2. Check every number in PROJECT_STATE.md against the actual database — flag discrepancies
3. Verify that all 5 core documents reference the UNIFIED_PLATFORM_REDESIGN_SPEC.md
4. Verify the roadmap filename is consistent everywhere (should be `UNIFIED_ROADMAP_2026_02_19.md`, not `_02_17`)
5. Check the scoring section in CLAUDE.md: does it reflect the new 8-factor weighted system or the old 7-factor equal-weight system?
6. Check the tier names: are all documents using Priority/Strong/Promising/Moderate/Low (new) rather than TOP/HIGH/MEDIUM/LOW (old)?
7. Check the test count: all documents should say 492 tests (491 pass, 0 fail, 1 skip)
8. Check the API router count: should be 21
9. Check the PIPELINE_MANIFEST.md against actual files on disk

**CHECKPOINT: Stop here and show findings before continuing.**

---

## SECTION 10: Summary & Recommendations

Pull everything together:

1. **Health Score:** Rate overall platform health: Critical / Needs Work / Solid / Excellent — with justification
2. **Top 10 Issues:** Most important problems, ranked by impact on organizers
3. **Quick Wins:** Things fixable in under an hour each
4. **Data Quality Priorities:** Which tables need the most cleanup
5. **Scoring Assessment:** Is the 8-factor weighted system producing useful results? What would make it more accurate?
6. **Master Employer Assessment:** Is the master table ready for production use, or does it need more dedup/cleanup?
7. **Frontend Assessment:** Is the React app production-ready? What's missing?
8. **Matching Pipeline Assessment:** Is matching trustworthy enough to deploy?
9. **Security Assessment:** What's the current security posture? What must be fixed before any real users?
10. **Documentation Gaps:** What's missing from the docs that a new developer would need?

---

## SECTION 11: What No One Thought to Ask

**This is the most important section.** The previous 10 sections check things we KNOW to look at. This section is about finding problems nobody anticipated — the blind spots, the silent failures, the assumptions that might be wrong.

**Think about these questions and investigate any that seem relevant:**

### Data Integrity Questions Nobody Asked

1. **Are there employers in the scorecard that don't exist anymore?** If a company went bankrupt, got acquired, or changed names — is the platform still scoring a ghost? Check if any high-scoring "Priority" employers have no recent activity across ANY data source (no OSHA inspections, no NLRB cases, no WHD cases, no SAM contracts in the last 5 years).

2. **Is the matching pipeline creating false connections?** Not just "are individual matches wrong" — but could a systematic error be linking thousands of records incorrectly? For example: if two companies at the same address get merged, and one is unionized and one isn't, the non-union company might disappear from the "targets" list. How many potential targets are being hidden by incorrect matches?

3. **Are there entire industries being missed?** The platform is built around F7 filings, which are for private-sector unions. Are there large industries where organizing is happening but the platform shows almost nothing? Check: tech, gig economy, cannabis, warehousing/logistics. What does the platform say about Amazon? About Starbucks?

4. **Is the deduplication OVER-counting or UNDER-counting?** The 14.5M member count is close to BLS — but is that because the methodology is correct, or because over-counting in some areas cancels out under-counting in others? Check: are there specific states or sectors where the platform's count diverges wildly from BLS?

5. **What happens to the scores when data is stale?** The half-life decay system means old violations count less. But what about employers with NO data? An employer with zero OSHA violations could be perfectly safe — or it could be that OSHA has never inspected them. Does the platform distinguish between "clean record" and "no record"?

### Architectural Questions Nobody Asked

6. **What's the performance cliff?** The system works with ~3M master employers. What happens at 5M? 10M? Are there queries that will become unusably slow? Check the largest table scans and joins — which ones don't have indexes?

7. **Is the materialized view refresh safe?** If someone refreshes the scorecard MV while the API is serving requests, do users see broken/partial data? Is `REFRESH MATERIALIZED VIEW CONCURRENTLY` being used everywhere?

8. **What happens when the database connection dies mid-operation?** Are there scripts that could leave the database in an inconsistent state if they crash halfway through?

9. **Is there a way to roll back a bad data update?** If someone runs the wrong ETL script and corrupts a table, is there a backup? Can you restore to yesterday's state?

### Strategic Questions Nobody Asked

10. **Is the platform scoring the RIGHT things?** The 8 factors measure conditions that make organizing more likely to succeed. But are there important factors being completely ignored? For example: employer turnover rate, local unemployment, political environment, presence of right-to-work laws, employer's legal counsel spending?

11. **Could the scoring system be gamed?** If an employer found out they were being scored, could they manipulate their public records to lower their score? (Settle OSHA violations quickly, avoid NLRB elections by voluntary recognition, etc.)

12. **What's the shelf life of a score?** If an organizer looks at a score today, how long is it valid? A week? A month? A year? Is there any indicator of when the underlying data was last updated?

13. **Are there unions that should be in the system but aren't?** The platform tracks 26,665 unions. The BLS says there are roughly 16,000 union locals in the US. Why does the platform have more? Are some of these defunct? Double-counted? National affiliates vs. locals?

14. **What's the false negative rate?** Of employers that actually got organized in the last 2 years (check NLRB election wins), how many were flagged as "Priority" or "Strong" by the platform BEFORE the election? If the platform consistently fails to predict successful organizing, the scoring model needs work.

15. **Is there geographic bias in the data?** Government enforcement varies hugely by region. OSHA inspects more in some states than others. WHD enforcement is concentrated in certain areas. Does this mean the platform systematically underscores employers in states with weak enforcement?

### Cross-System Questions Nobody Asked

16. **Do the 5 core documents actually agree with each other now?** The Document Reconciliation Analysis from Feb 21 found dozens of inconsistencies. Were they all fixed? Check 10 specific numbers across CLAUDE.md, PROJECT_STATE.md, and the ROADMAP.

17. **Is the React frontend actually connected to the same data as the legacy frontend?** If you search for the same employer in both, do you get the same results? Same scores? Same data?

18. **What would happen if you ran the full pipeline from scratch?** If you deleted all match tables and re-ran `run_deterministic.py all`, would you get the same results? Or have manual fixes and special cases accumulated that only exist in the current data?

19. **Are there circular dependencies in the scoring?** Could it be possible that Factor A depends on data that depends on Factor B, which depends on Factor A? For example: employer groups affect union proximity scores, but union proximity might affect which employers get grouped.

20. **What data sources are going stale?** Check the `data_freshness` table (if it exists). Which data sources haven't been refreshed in 6+ months? What's the oldest data being used in active scoring?

---

## OUTPUT FORMAT

Write your report in clear, plain language with actual numbers and evidence. When something is broken, explain what it means practically.

Include the actual queries or code you used, so findings can be independently verified.

Organize findings by severity:
- **CRITICAL** — Blocks basic use or produces wrong results organizers would act on
- **HIGH** — Significant gap that reduces platform value
- **MEDIUM** — Should be fixed soon but doesn't break core functionality
- **LOW** — Nice to have / cleanup

Number your findings (e.g., Finding 7.1, Finding 7.2 — continuing from Part 1) so they can be cross-referenced with the other auditors.

State your confidence in each finding:
- **Verified** — You tested it and confirmed
- **Likely** — Strong evidence but not fully tested
- **Possible** — Inferred from indirect evidence

---

## CROSS-AUDIT COMPARISON

Three AI tools are auditing the same system. To make comparison easier:

1. Use the severity labels above consistently
2. Number all findings
3. Note your confidence level
4. If you encounter ambiguous metrics (like match rates that can be measured different ways), explain BOTH interpretations
5. If you disagree with something in the documentation, explain why

---

*This prompt was built from: CLAUDE.md, PROJECT_STATE.md, UNIFIED_ROADMAP_2026_02_19.md, UNIFIED_PLATFORM_REDESIGN_SPEC.md, PROJECT_DIRECTORY.md, PIPELINE_MANIFEST.md, CODEX_TASKS_2026_02_22.md, DOCUMENT_RECONCILIATION_ANALYSIS.md, AUDIT_2026_FILE_INVENTORY.md, SCORING_SPECIFICATION.md, and actual current database state.*
