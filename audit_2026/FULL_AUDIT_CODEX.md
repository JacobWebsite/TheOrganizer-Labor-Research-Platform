# FULL PLATFORM AUDIT — CODEX
# Labor Relations Research Platform
# Date: February 16, 2026

## YOUR ROLE

You are Codex, performing a FULL independent audit of this labor relations research platform. You have access to all project files in this directory. Focus especially on code quality, logic correctness, security, and architecture — but complete ALL sections.

Create your report at: docs/AUDIT_REPORT_CODEX_2026_R3.md
Update it after each section.

## COMMUNICATION STYLE
Write everything in plain, simple language. Assume the reader has limited coding and database knowledge. When you mention a technical concept, explain what it means and why it matters practically. Example: Don't say "SQL injection vulnerability in endpoint" — say "someone could type special characters into the search box that trick the database into running commands it shouldn't, potentially exposing or deleting data."

## CRITICAL RULES
1. NEVER delete or modify data — this is read-only
2. STOP at each checkpoint and save progress to the report file
3. Number every finding (e.g., Finding 1.1, 1.2) for cross-referencing
4. Label severity: CRITICAL / HIGH / MEDIUM / LOW
5. State confidence: Verified (tested) / Likely (strong evidence) / Possible (inferred)
6. Include code snippets and file paths as evidence

## DATABASE CONNECTION (for queries if needed)
```
psql -U postgres -d olms_multiyear
Password: Juniordog33!
```

---

## WHAT THIS PROJECT IS

This platform helps union organizers decide where to focus their efforts. It pulls data from multiple government databases — Department of Labor, NLRB (union elections), OSHA (workplace safety), SEC (public companies), IRS (nonprofits) — and connects them together so you can see the full picture of any employer.

The core technical challenge is "matching" — different agencies don't share employer IDs, so the platform uses a 5-tier pipeline (exact EIN → normalized name → address → aggressive name → fuzzy trigram) to connect records. The matching code lives in scripts/matching/.

### Architecture
- PostgreSQL database (olms_multiyear): 169 tables, 186 views, ~23.9M rows
- FastAPI backend: api/labor_api_v6.py — 152 endpoints across 17 route groups
- Frontend: files/organizer_v5.html + 11 supporting JS files (split from 1 monolith)
- Python scripts: ~494 across scripts/ directory
- Tests: 165 automated tests in tests/ (all passing)

### Known Issues Going In
- 3 density endpoints crash (code reads columns by position instead of name)
- Authentication disabled by default
- 29 scripts have password bug (send literal "os.environ.get('DB_PASSWORD', '')" as password string)
- modals.js is 2,598 lines (secondary monolith)
- 103 inline onclick handlers in HTML
- Documentation ~55% accurate

---

## AUDIT SECTIONS — COMPLETE ALL 10

### SECTION 1: Database Table Inventory
Connect to database. Get every table/view with actual row counts. Compare against CLAUDE.md documentation. Flag: zero-row tables, undocumented tables, missing primary keys, count discrepancies.

**CHECKPOINT: Save findings to report.**

### SECTION 2: Data Quality Deep Dive
For core tables (f7_employers_deduped, unions_master, nlrb_elections, osha_establishments, mergent_employers), check column completeness (null/empty rates). Check for duplicates. Validate foreign key relationships. Count orphaned records.

**CHECKPOINT: Save findings to report.**

### SECTION 3: Materialized Views & Indexes
List materialized views (row count, size, staleness). Test regular views. List indexes (table, columns, size, usage). Flag unused indexes, missing indexes, broken views.

**CHECKPOINT: Save findings to report.**

### SECTION 4: Cross-Reference Integrity
Test connections between data sources:
- Corporate crosswalk coverage (GLEIF, Mergent, SEC, IRS)
- OSHA match rates and confidence
- NLRB coverage
- Public sector linkage
- Unified employer view breakdown
- Scoring coverage and tier distribution

Note: 92.34% of NLRB participants NOT connecting to elections is EXPECTED — participants include all case types, not just elections. Don't flag this as a bug.

**CHECKPOINT: Save findings to report.**

### SECTION 5: API Endpoint Audit ⭐ (YOUR PRIMARY STRENGTH)
This is where you should go deepest. Read api/labor_api_v6.py line by line.

For every endpoint:
- HTTP method and URL path
- What tables/views it queries
- Whether those tables/columns actually exist
- Whether it uses parameterized queries or string concatenation (security)
- Error handling: what happens with bad input?
- Whether response format is consistent

Flag:
- Endpoints referencing nonexistent tables/columns
- SQL injection vulnerabilities (string concatenation in queries)
- Missing input validation
- Inconsistent error responses
- Endpoints that duplicate functionality
- Tables with data but NO API endpoint serving them

**CHECKPOINT: Save findings to report.**

### SECTION 6: File System & Script Inventory ⭐ (YOUR PRIMARY STRENGTH)
Read through the scripts/ directory structure.

For each script category:
- What does it do? (data loading, matching, analysis, utility)
- Does it reference tables that still exist?
- Does it have hardcoded credentials?
- Is it one-time (data import) or recurring (needs to run again)?
- Code quality: error handling, logging, modularity

Identify:
- Scripts referencing deleted/renamed tables
- Hardcoded passwords or API keys (SECURITY)
- Critical-path scripts (needed to rebuild database)
- Dead code that should be archived
- The matching module (scripts/matching/) — is the architecture sound?

**CHECKPOINT: Save findings to report.**

### SECTION 7: Documentation Accuracy
Compare CLAUDE.md against actual database state. Check README. Check Roadmap_TRUE_02_15.md. Flag all incorrect claims.

**CHECKPOINT: Save findings to report.**

### SECTION 8: Frontend & User Experience ⭐ (YOUR PRIMARY STRENGTH)
Read files/organizer_v5.html and all JS files.

Check for:
- Old scoring scale references (0-62, 0-100, 6-factor) — should all be 9-factor/0-100
- Hardcoded localhost URLs
- Inline onclick handlers (count them)
- modals.js complexity — identify natural split points
- Accessibility issues
- Error handling in API calls (what does user see when API fails?)
- State management issues (does data persist correctly between views?)

**CHECKPOINT: Save findings to report.**

### SECTION 9: Security Audit ⭐ (YOUR PRIMARY STRENGTH)
Go through every code file systematically:

1. Authentication:
   - Is JWT auth enforced? Check the middleware
   - Can you access API endpoints without a token?
   - Token expiration and refresh logic

2. Credentials:
   - Search ALL files for: password, secret, api_key, token, credential
   - Flag every instance of hardcoded sensitive data
   - Check .env vs .env.example

3. SQL Injection:
   - Search all .py files for f-string or .format() used in SQL queries
   - Every instance is a potential vulnerability

4. Input Validation:
   - Do API endpoints validate query parameters?
   - Can someone pass malicious input?

5. CORS/Headers:
   - Are CORS settings appropriate?
   - Any sensitive headers exposed?

**CHECKPOINT: Save findings to report.**

### SECTION 10: Summary & Recommendations
1. Health Score: Critical / Needs Work / Solid / Excellent
2. Top 10 issues ranked by organizer impact
3. Quick wins (under 1 hour)
4. Tables to drop
5. Missing index recommendations
6. Documentation corrections
7. Data quality priorities
8. Code architecture assessment — is the codebase maintainable?
9. Security posture — is this safe to deploy externally?
10. Technical debt estimate — how much cleanup before new features?

---

## PREVIOUS AUDIT NOTES
- OSHA match rate: 47.3% (current employers) vs 25.37% (all) — both correct, different populations
- WHD matching: primary path works (16%), legacy Mergent columns are weak/outdated
- GLEIF: 396 MB useful data vs 12 GB raw — both in database
- Scoring: backend unified, frontend has old remnants
