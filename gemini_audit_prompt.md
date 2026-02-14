# Independent Platform Audit

You are conducting a full independent technical audit of this Labor Relations Research Platform. Form your own opinions based entirely on what you find in the code, data, and documentation. Do not reference or seek out any previous audit reports or review documents that may exist in the project — your assessment should be completely your own.

The project owner has limited coding and database experience. Explain all findings in plain, conversational language. For every issue you find, explain WHY it matters in practical terms — not just what the technical problem is.

## How to Conduct This Audit

1. Start by reading CLAUDE.md as a data dictionary to understand the database schema (tables, columns, relationships). Treat it only as a reference for what exists — form your own judgments about quality.
2. Explore the actual project files systematically — read code, SQL, documentation, and the frontend.
3. Work through each section below, investigating thoroughly before writing findings.
4. Save your complete report as `gemini_audit_report.md` in the project root.

---

## SECTION 1: Architecture & Project Organization

Explore the full directory structure and how components relate to each other.

- Is the project organized in a way that makes sense? Could a new person navigate it?
- Are there files that seem orphaned, misplaced, or redundant?
- How clean is the separation between data processing, API, and frontend?
- Is there unnecessary duplication anywhere?
- What's in the archive/ folder and does the right stuff live there?

---

## SECTION 2: Database Design

Review the schema through CLAUDE.md, sql/ files, and any migration scripts.

- Is the schema well-designed for this use case?
- Are there missing indexes, foreign keys, or constraints?
- Are naming conventions consistent across 200+ tables?
- Are there tables that seem disconnected from everything else?
- Are data types appropriate and consistent across tables that need to join?
- Is the use of materialized views appropriate?
- What would you redesign if starting fresh?

---

## SECTION 3: Entity Matching

This is arguably the most important part of the platform — matching the same employer or union across different government databases. Review scripts/matching/ and the various match tables.

- How robust is the matching approach? What are its blind spots?
- Are the similarity thresholds well-chosen, or likely producing false matches?
- What edge cases would break the matching (abbreviations, subsidiaries, DBAs, mergers)?
- How does match quality degrade across the tiers?
- Is there a mechanism to catch and correct bad matches?
- What alternative approaches could improve accuracy?
- What's the estimated false positive and false negative rate?

---

## SECTION 4: Scoring & Target Identification

Review the organizing scorecards and how targets are ranked.

- Are the scoring formulas well-reasoned, or do the weights seem arbitrary?
- Could the scores produce misleading results or be easily gamed?
- Are there important organizing signals NOT captured in the scoring?
- How sensitive are the results to missing or incomplete data?
- Do the priority tiers create meaningful differentiation?
- Is the geographic density methodology sound?
- How would you improve the scoring approach?

---

## SECTION 5: API Design & Security

Review api/main.py and the routers/ directory.

- Are there SQL injection risks?
- Is input validation sufficient?
- Can any endpoint return dangerously large result sets?
- Is error handling consistent?
- Are there authentication or access controls?
- How are database connections managed?
- Are there performance concerns (slow queries, N+1 problems)?

---

## SECTION 6: Data Quality & Validation

Review the test suite, quality check files, and data validation approach.

- How comprehensive is automated testing?
- Are there data integrity checks? How often do they run?
- What happens when source data gets updated?
- How reliable is the membership deduplication (70.1M to 14.5M)?
- Are the external benchmark comparisons methodologically sound?
- What data quality risks could undermine the platform's usefulness?

---

## SECTION 7: Frontend & Usability

Review files/organizer_v5.html.

- Is this usable by non-technical union staff?
- What are the biggest usability problems?
- How does it handle API errors or slow responses?
- Is the data presentation effective for decision-making?
- Does it work on mobile devices?
- Is a single HTML file sustainable, or should it be restructured?

---

## SECTION 8: Strategic Gaps & Missing Capabilities

Think about what this platform SHOULD do that it doesn't.

- What data sources are conspicuously absent?
- What analytical capabilities would union organizers actually need?
- Are there predictive or forecasting features that should exist?
- How does this compare to what commercial tools offer?
- Is there a strategy for keeping data fresh?
- What would make this 10x more useful for day-to-day organizing work?

---

## SECTION 9: Code Quality & Maintainability

Sample multiple Python scripts across different directories.

- Is code style consistent?
- Are there hardcoded values that should be configurable?
- Is error handling adequate?
- Are scripts well-documented?
- Are there scripts trying to do too many things at once?
- Are dependencies properly tracked?

---

## SECTION 10: Production Readiness

Assess what it would take to make this a real production system.

- What stands between this and multi-user deployment?
- Are there monitoring or alerting capabilities?
- How is backup handled?
- Could someone else set up and maintain this from the documentation alone?
- What are the scaling bottlenecks?
- Are there legal or licensing concerns with any data sources?

---

## Report Format

For each finding, provide:
- **Finding** — What you observed
- **Severity** — CRITICAL / HIGH / MEDIUM / LOW / INFO
- **Impact** — Why this matters, explained simply
- **Recommendation** — What to do about it
- **Effort** — Quick fix / Medium project / Major undertaking

At the end of the report, include:

### Top 10 Priority Actions
Ranked by a combination of impact and feasibility.

### Overall Assessment
A candid, honest summary. What's genuinely impressive about this project? What are its biggest risks? Where is it strongest and weakest?

### Strategic Recommendations
3-5 high-level suggestions for where the project should go next.

Save the complete report as `gemini_audit_report.md`.
