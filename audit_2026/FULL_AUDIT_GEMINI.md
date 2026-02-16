# FULL PLATFORM AUDIT — GEMINI
# Labor Relations Research Platform
# Date: February 16, 2026

## YOUR ROLE

You are Gemini, performing a FULL independent audit of this labor relations research platform. Your primary strengths are research, methodology validation, and fact-checking. You should cross-reference claims against public data sources and verify that the platform's benchmarks and methodologies are sound. But complete ALL sections.

Create your report at: docs/AUDIT_REPORT_GEMINI_2026_R3.md
Update it after each section.

## COMMUNICATION STYLE
Write everything in plain, simple language. Assume the reader has limited coding and database knowledge. When you mention a technical concept, explain what it means and why it matters practically.

## CRITICAL RULES
1. NEVER delete or modify data — this is read-only
2. STOP at each checkpoint and save progress to the report file
3. Number every finding (e.g., Finding 1.1, 1.2) for cross-referencing
4. Label severity: CRITICAL / HIGH / MEDIUM / LOW
5. State confidence: Verified (tested) / Likely (strong evidence) / Possible (inferred)
6. When verifying external claims, cite your sources

## DATABASE CONNECTION
```
psql -U postgres -d olms_multiyear
Password: Juniordog33!
```

---

## WHAT THIS PROJECT IS

This platform helps union organizers decide where to focus their efforts. It pulls data from multiple government databases — Department of Labor (OLMS), NLRB (union elections), OSHA (workplace safety), SEC (public companies), IRS (nonprofits) — and connects them together so you can see the full picture of any employer.

### Current Scale
- 169 tables, 186 views, ~23.9 million rows
- 60,953 current employers, 52,760 historical
- 14.5M union members (deduplicated from 70.1M raw — claims to match BLS within 1.5%)
- 152 API endpoints, 165 automated tests
- Scoring system: 9 factors, 0-100 points

### Key Methodology Claims to Verify
1. "14.5M members matches BLS benchmark of 14.3M within 1.5%"
2. "Deduplication correctly reduces 70.1M raw to 14.5M"
3. "Public sector coverage at 98.3% of EPI benchmark"
4. "OSHA violations total $3.52 billion in penalties"
5. "47.3% OSHA match rate for current employers"
6. "The 5-tier matching pipeline achieves 96.2% entity matching"
7. "County density estimates use industry-weighted BLS rates with auto-calibrated multiplier"
8. Industry-level union density rates from BLS are applied correctly
9. NLRB election data is current and complete
10. Multi-employer deduplication methodology is sound

---

## AUDIT SECTIONS — COMPLETE ALL 10

### SECTION 1: Database Table Inventory
Get every table/view with actual row counts. Compare against documentation. Flag discrepancies, zero-row tables, undocumented tables.

**CHECKPOINT: Save findings to report.**

### SECTION 2: Data Quality Deep Dive
Check core tables for column completeness, duplicates, orphaned records, data consistency.

**CHECKPOINT: Save findings to report.**

### SECTION 3: Materialized Views & Indexes
List views (staleness, size). Test if views work. List indexes (usage stats). Flag unused/missing.

**CHECKPOINT: Save findings to report.**

### SECTION 4: Cross-Reference Integrity
Test connections between data sources: corporate crosswalk, OSHA matching, NLRB coverage, public sector linkage, unified employer view, scoring coverage.

Note: 92.34% of NLRB participants NOT connecting to elections is EXPECTED — participants include all case types. Don't flag as bug.

**CHECKPOINT: Save findings to report.**

### SECTION 5: API Endpoint Audit
Read api/labor_api_v6.py. List endpoints. Flag broken references, security issues. Count working vs broken.

**CHECKPOINT: Save findings to report.**

### SECTION 6: File System & Script Inventory
Catalog scripts. Identify dead references, hardcoded credentials, critical-path scripts.

**CHECKPOINT: Save findings to report.**

### SECTION 7: Documentation Accuracy ⭐ (YOUR PRIMARY STRENGTH)
Go deep here. For every factual claim in documentation:

**CLAUDE.md:**
- Every table name — does it exist?
- Every row count — does it match?
- Every feature described — does it work?
- API endpoint lists — are they complete and accurate?
- Scoring factor descriptions — do they match the code?

**README.md:**
- Startup command — does it work?
- File paths — do they exist?
- Feature list — is it current?

**Roadmap_TRUE_02_15.md:**
- "Things That Are Working Well" section — verify each claim
- Known issues list — are these still the actual issues?
- Phase descriptions — do they accurately describe what needs doing?

**Methodology documents (if accessible):**
- BLS benchmark comparison — are the right BLS numbers being used?
- EPI benchmark comparison — is the EPI source data current?
- Deduplication methodology — does the logic make sense?

**CHECKPOINT: Save findings to report.**

### SECTION 8: Frontend & User Experience
Read frontend files. Check for old scoring references, broken links, inconsistencies.

**CHECKPOINT: Save findings to report.**

### SECTION 9: Security Audit
Check auth status, hardcoded credentials, SQL injection risks, JWT implementation.

**CHECKPOINT: Save findings to report.**

### SECTION 10: Summary & Recommendations ⭐ (GO DEEP)

In addition to the standard summary items, provide:

1. Health Score: Critical / Needs Work / Solid / Excellent
2. Top 10 issues ranked by organizer impact
3. Quick wins
4. **Methodology Assessment:**
   - Is the deduplication approach statistically sound?
   - Are the density estimation methods appropriate?
   - Is the scoring model well-designed for its purpose?
   - Are BLS/EPI benchmarks being used correctly?
5. **Data Source Assessment:**
   - Which integrated data sources are being used effectively?
   - Which are underutilized?
   - What data sources should be prioritized next?
6. **Future Integration Readiness:**
   - SEC EDGAR: is the current infrastructure ready?
   - IRS BMF: what would need to change?
   - CPS/IPUMS microdata: compatible with current density methodology?
   - OEWS staffing patterns: would this integrate naturally?
7. **Benchmarking:**
   - How does 14.5M members compare to current BLS numbers? (verify externally)
   - Is the 98.3% public sector coverage claim accurate against current EPI data?
   - Are OSHA violation penalty totals in line with publicly available OSHA reports?
8. Documentation corrections needed
9. Data quality priorities
10. Research methodology recommendations

---

## POTENTIAL TOOLS & DATA SOURCES FOR FUTURE (Context Only)

The platform plans to integrate these. Note whether current infrastructure supports them:
- edgartools (Python) — SEC EDGAR parsing, EIN-based matching
- Splink (Python) — probabilistic record matching
- ipumspy (Python) — Census microdata, metro-level density
- Crawl4AI / Firecrawl — AI-powered web scraping
- Good Jobs First Subsidy Tracker — 722,000+ entries
- ProPublica Nonprofit Explorer — broader 990 coverage
- DOL contract database — 25,000+ union contracts for AI extraction
- State PERB data (NY, CA, IL) — no open-source tools exist yet

## PREVIOUS AUDIT NOTES
- OSHA match rate: 47.3% (current) vs 25.37% (all) — different populations, both correct
- WHD: primary path at 16%, legacy Mergent path weak
- GLEIF: 396 MB useful vs 12 GB raw bulk
- NLRB participants: 92.34% not connected to elections is EXPECTED
- Scoring: backend unified 9-factor, frontend has old 6-factor remnants
