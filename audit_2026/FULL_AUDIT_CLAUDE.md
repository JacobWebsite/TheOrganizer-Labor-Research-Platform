# FULL PLATFORM AUDIT — CLAUDE CODE
# Labor Relations Research Platform
# Date: February 16, 2026

## YOUR ROLE

You are Claude Code, performing a FULL independent audit of this labor relations research platform. You have direct access to the database and all project files. You should actually connect to PostgreSQL and run queries. Actually read the code files. Actually test things.

Create your report at: docs/AUDIT_REPORT_CLAUDE_2026_R3.md
Update it after each section — don't wait until the end.

## COMMUNICATION STYLE
Write everything in plain, simple language. Assume the reader has limited coding and database knowledge. When you mention a technical concept, explain what it means and why it matters practically. Example: Don't just say "foreign key constraint violated" — say "824 employer records point to unions that don't exist in the system, so when someone looks up those employers, the union data will be wrong or missing."

## CRITICAL RULES
1. NEVER delete or modify data — this is read-only
2. STOP at each checkpoint and save progress to the report file
3. If something unexpected happens, document it and continue
4. Include the actual SQL queries you ran so findings can be verified
5. Number every finding (e.g., Finding 1.1, 1.2) for cross-referencing
6. Label severity: CRITICAL / HIGH / MEDIUM / LOW
7. State confidence: Verified (tested) / Likely (strong evidence) / Possible (inferred)

## DATABASE CONNECTION
```python
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
```

---

## WHAT THIS PROJECT IS (READ THIS CAREFULLY)

This platform helps union organizers decide where to focus their efforts. It pulls data from multiple government databases — Department of Labor (OLMS), NLRB (union elections), OSHA (workplace safety), SEC (public companies), IRS (nonprofits), and others — and connects them together so you can see the full picture of any employer.

The core technical challenge is "matching" — different agencies don't share employer IDs, and even employer names are spelled differently across databases. The platform uses a 5-tier matching pipeline (exact EIN → normalized name → address → aggressive name → fuzzy trigram) to connect records across sources.

### Current Platform Scale
- Database: ~20 GB (12 GB is unused GLEIF bulk data)
- 169 tables, 186 views, ~23.9 million rows (public schema)
- 152 API endpoints across 17 route groups
- 165 automated tests (all passing)
- 60,953 current employers, 52,760 historical employers
- 14.5M union members (deduplicated from 70.1M raw — within 1.5% of BLS)

### Known Issues Going In
- 3 density endpoints crash (code reads columns by position instead of name)
- Authentication disabled by default
- 824 union file number orphans (grew from 195 after historical import)
- 29 scripts have password bug (literal string instead of env lookup)
- 12 GB GLEIF raw schema (only 310 MB actually used)
- 37.7% NAICS coverage on current employers
- 299 unused indexes wasting 1.67 GB
- Documentation ~55% accurate

---

## AUDIT SECTIONS — COMPLETE ALL 10

### SECTION 1: Database Table Inventory
Connect to the database. Get EVERY table and view with actual row counts (not what docs say). Compare against CLAUDE.md. Flag: zero-row tables, undocumented tables, missing primary keys, count discrepancies vs documentation.

Group into: Core, OSHA, Public Sector, NLRB, Corporate/Financial, Mergent, Geography, Views, Unknown/Orphan.

**CHECKPOINT: Save findings to report.**

### SECTION 2: Data Quality Deep Dive
For each core table, check column-by-column: how many rows have data vs null/empty. Core tables: f7_employers_deduped, unions_master, nlrb_elections, osha_establishments, mergent_employers, manual_employers. Check for duplicates. Validate foreign key relationships. Count orphaned records.

**CHECKPOINT: Save findings to report.**

### SECTION 3: Materialized Views & Indexes
List all materialized views (row count, disk size, staleness). Test all regular views (SELECT LIMIT 1). List all indexes (table, columns, size, usage count). Flag unused indexes, missing indexes on large tables, broken views.

**CHECKPOINT: Save findings to report.**

### SECTION 4: Cross-Reference Integrity
Test the connections between data sources — this is the platform's core value:
- Corporate identifier crosswalk coverage (GLEIF, Mergent, SEC, IRS)
- OSHA match rates and confidence distribution
- NLRB coverage (elections to unions, employers to F7)
- Public sector linkage (locals to unions_master, employers to bargaining units)
- Unified employer view (source breakdown, geographic/NAICS/OSHA coverage)
- Scoring coverage (non-zero scores, tier distribution, missing components)

**CHECKPOINT: Save findings to report.**

### SECTION 5: API Endpoint Audit
Read api/labor_api_v6.py. List every endpoint with: HTTP method, tables queried, description. Flag: endpoints referencing nonexistent tables/columns, SQL injection risks, broken endpoints. Count: working vs broken vs risky. Find tables with no API access.

**CHECKPOINT: Save findings to report.**

### SECTION 6: File System & Script Inventory
Catalog scripts/ directory. For each script: does it use the database? Which tables? Is it one-time or recurring? Find scripts referencing deleted tables. Find hardcoded passwords. Identify critical-path scripts (needed to rebuild from scratch).

**CHECKPOINT: Save findings to report.**

### SECTION 7: Documentation Accuracy
Compare CLAUDE.md table names and row counts against actual database. Check README for correct commands and paths. Check Roadmap_TRUE_02_15.md against current state. Flag wrong claims, missing documentation.

**CHECKPOINT: Save findings to report.**

### SECTION 8: Frontend & User Experience
Read files/organizer_v5.html and associated JS files. Check for: old scoring references (0-62, 0-100, 6-factor), hardcoded localhost URLs, broken links. Assess navigation flow. Check if confidence/freshness indicators exist.

**CHECKPOINT: Save findings to report.**

### SECTION 9: Security Audit
Check auth status (is login enforced?). Search code for hardcoded passwords/API keys. Check for SQL injection in API. Verify JWT system. Check data protection.

**CHECKPOINT: Save findings to report.**

### SECTION 10: Summary & Recommendations
1. Health Score: Critical / Needs Work / Solid / Excellent
2. Top 10 issues ranked by organizer impact
3. Quick wins (under 1 hour each)
4. Tables to consider dropping
5. Missing index recommendations
6. Documentation corrections needed
7. Data quality priorities
8. Future integration readiness (is infrastructure ready for SEC EDGAR, IRS BMF, CPS microdata, OEWS?)
9. Matching pipeline assessment (scalable or needs overhaul?)
10. Scoring model assessment (is 9-factor model producing useful results?)

---

## CONTEXT: WHAT'S PLANNED NEXT (Don't Audit This — Just Be Aware)

Phase 1 (Week 1): Fix crashes, password bug, orphans, auth, GLEIF archive, docs, NAICS backfill
Phase 2 (Weeks 2-4): Frontend cleanup — 4 screens, remove old scores, split modals.js
Phase 3 (Weeks 3-7): Matching pipeline overhaul — standardize output, one name-cleaner, Splink, quality dashboard
Phase 4 (Weeks 8-10): New data — SEC EDGAR, IRS BMF, CPS/IPUMS, OEWS staffing patterns
Phase 5 (Weeks 10-12): Scoring — temporal decay, NAICS hierarchy, Gower distance, propensity model
Phase 6 (Weeks 11-14): Deployment — Docker, CI/CD, scheduling
Phase 7 (Week 14+): Web scrapers, state PERB, union-lost analysis, board reports

## PREVIOUS AUDIT NOTES
Last round had disagreements between auditors. Be aware:
- OSHA match rate: 47.3% (current employers) vs 25.37% (all employers) — both correct, different populations
- WHD matching: primary path improved 8x to 16%, but legacy Mergent path is still weak
- GLEIF: 396 MB useful distilled data vs 12 GB raw bulk — both in the database
- NLRB participants: 92.34% don't connect to elections — this is EXPECTED (participants include all case types, not just elections)
- Scoring: backend IS unified, but frontend still has old scale remnants
