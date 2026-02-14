# Independent Audit of the Labor Relations Research Platform

## Your Role

You are conducting an **independent technical audit** of a labor relations research platform. This is a real project — not a demo or exercise. Your job is to explore the codebase, database, API, frontend, and documentation with fresh eyes, then deliver honest findings.

**Do not reference, seek out, or be influenced by any previous audit reports in this project.** Form your own opinions from what you find in the code and data.

---

## What This Project Is (Plain English)

This platform helps **unions** (labor organizations that represent workers) make smarter decisions about **where to organize next**. It pulls together data from many government sources — workplace safety violations, union election results, employer financial filings, government contracts — and combines them into one searchable system.

Think of it like a research dashboard: a union organizer could search for "hospitals in New York with lots of safety violations and no union" and get a ranked list of potential organizing targets.

The platform currently tracks:
- **26,665 unions** and their membership/financial data
- **~100,000 employers** from multiple government databases  
- **14.5 million union members** (deduplicated from 70M+ raw records)
- **33,000+ union elections** and their outcomes
- **1 million+ workplace safety inspections** and 2.2 million violations
- **363,000+ wage theft cases**

---

## How to Audit This Project

### Step 1: Read These Files First (in this order)

1. **`README.md`** — Project overview, quick start, data sources
2. **`CLAUDE.md`** — Database schema reference (table names, columns, record counts)
3. **`SESSION_LOG_2026.md`** — What was built and when (development history)  
4. **`LABOR_PLATFORM_ROADMAP_v13.md`** — Current state assessment and what's planned next
5. **`docs/METHODOLOGY_SUMMARY_v8.md`** — How the data was processed and validated

### Step 2: Explore the Actual Code

Dig into these directories and form your own opinions:

| Directory | What's There |
|-----------|-------------|
| `api/` | FastAPI backend — the main API server and route files |
| `scripts/` | Python scripts for data processing, matching, imports |
| `scripts/matching/` | The entity matching pipeline (how employers get linked across databases) |
| `sql/` | SQL scripts for schema creation, views, migrations |
| `frontend/` | Web interface files |
| `files/organizer_v5.html` | The main user-facing interface (single HTML file) |
| `tests/` | Test suite |
| `docs/` | Methodology docs, case studies, benchmarks |

### Step 3: Check the Database (if you have access)

```python
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
```

Useful exploration queries:
```sql
-- How many tables exist?
SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';

-- Biggest tables
SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 20;

-- Check for missing indexes on foreign keys
SELECT * FROM pg_indexes WHERE tablename LIKE '%employer%';

-- Check match rates
SELECT match_tier, count(*) FROM osha_f7_matches GROUP BY match_tier;
```

---

## What to Evaluate (10 Areas)

For each area, note what's **working well**, what's **broken or risky**, and what **should be improved**.

### 1. Project Organization & Architecture
- Is the code organized logically? Can a new developer find things?
- Is the separation between API, scripts, SQL, and frontend clear?
- Are there dead files, duplicates, or confusing naming conventions?

### 2. Database Design
- Are tables normalized properly? Are there redundant or orphaned tables?
- Are indexes present where they should be? Missing indexes on JOIN columns?
- Are foreign keys enforced, or is referential integrity just hoped for?
- Are naming conventions consistent?

### 3. Entity Matching Pipeline
- The platform links employers across 5+ government databases using a 5-tier matching system (EIN exact → normalized name → address → aggressive name → fuzzy trigram). Evaluate this:
  - How likely are false positives (wrong matches)?
  - How likely are false negatives (missed matches)?
  - Are match confidence scores tracked?
  - Are there edge cases that would break the matching?

### 4. Scoring & Target Identification
- Two scoring systems exist: an OSHA scorecard (0-100 points) and a sector scorecard (0-62 points)
- Are the scoring weights reasonable? Would they actually identify good organizing targets?
- Are there biases in the scoring that might mislead organizers?
- Do the scores make intuitive sense when you look at actual results?

### 5. API Design & Security
- Is there any authentication? (Hint: there isn't)
- Are SQL queries safe from injection?
- Are inputs validated?
- Is there pagination on list endpoints?
- Is there rate limiting?
- Are error messages helpful without leaking internal details?

### 6. Data Quality & Coverage
- The platform claims 14.5M members vs 14.3M BLS benchmark (101.4% coverage). Does this hold up?
- Raw data started at 70.1M and was deduplicated. Is the dedup methodology sound?
- What about the match rates that are still low (OSHA 7.9%, WHD 4.8%, 990 filers 0%)?
- Are there data sources that are stale or incomplete?

### 7. Frontend & User Experience
- Look at `files/organizer_v5.html` — is it usable?
- Would a union organizer (not a programmer) be able to use this effectively?
- What information is missing from the interface that organizers would need?
- Is the interface accessible? Mobile-friendly?

### 8. Testing & Reliability
- Look at the test suite in `tests/`. Is coverage adequate?
- Are there tests for the matching pipeline? For scoring calculations?
- What would break if someone made a database change?
- Is there any monitoring or alerting?

### 9. Documentation
- Is there enough documentation for someone new to understand the project?
- Are the methodology decisions explained and justified?
- Is there a clear guide for updating data when new government releases come out?

### 10. Security & Deployment Readiness
- Database credentials in plaintext?
- CORS configuration?
- Is this ready to deploy for real users, or is it still a local prototype?
- What would need to change to put this on a server accessible to union staff?

---

## Part 2: Improvement Recommendations with Priority Levels

After completing your audit, provide a **prioritized list of improvements**. Use these priority levels:

| Priority | Meaning | Timeline |
|----------|---------|----------|
| 🔴 **CRITICAL** | Blocks deployment or risks data integrity. Fix immediately. | This week |
| 🟠 **HIGH** | Significantly limits usefulness or creates security risk. Fix before any users touch it. | Next 2 weeks |
| 🟡 **MEDIUM** | Would meaningfully improve quality or usability. Plan for next development cycle. | Next month |
| 🟢 **LOW** | Nice to have. Would polish the platform but not essential for launch. | When time allows |

For each recommendation, include:
1. **What's wrong** (specific finding)
2. **Why it matters** (impact on users or data)
3. **What to do** (concrete fix, not vague advice)
4. **Effort estimate** (hours or days, rough)

---

## Part 3: Making This Usable for Unions

This is the most important section. The whole point of this platform is to be **useful to real union organizers and researchers**. With that in mind:

### A. What would unions actually need from this tool?

Think about the real-world workflow of a union organizer:
- They're trying to identify employers where workers might want to organize
- They need to understand an employer's history (safety violations, past elections, wage theft)  
- They need to know if similar employers have been successfully organized
- They need to build a case for why organizing at a specific workplace makes sense
- They need geographic intelligence (what's happening in their region)

### B. What's missing that would make this genuinely useful?

Consider:
- **Information gaps:** What data would organizers want that isn't here?
- **Workflow gaps:** What steps in the organizing process aren't supported?
- **Usability gaps:** What would frustrate a non-technical user?
- **Trust gaps:** How would organizers know the data is accurate and current?
- **Access gaps:** How would union staff actually access and use this day-to-day?

### C. What would make this a "must-have" tool vs a "nice research project"?

The difference between a useful tool and an academic exercise. What features, data, or capabilities would make union leadership say "we need this" rather than "that's interesting"?

### D. Realistic path to union adoption

- What's the minimum viable product that a union could start using?
- What training or onboarding would be needed?
- How should updates and data freshness be handled?
- What privacy or security concerns would unions have?
- How does this compare to what unions currently use (if anything)?

---

## Output Format

Save your complete audit report as a markdown file. Structure it as:

```
# Independent Platform Audit — [Your Tool Name]
## Date: [Today's date]

## Executive Summary
(2-3 paragraphs: overall assessment, biggest strengths, biggest risks)

## Audit Findings by Area
### 1. Project Organization
### 2. Database Design
### 3. Entity Matching
### 4. Scoring Systems
### 5. API Design & Security  
### 6. Data Quality
### 7. Frontend & UX
### 8. Testing
### 9. Documentation
### 10. Security & Deployment

## Prioritized Improvements
### 🔴 Critical
### 🟠 High  
### 🟡 Medium
### 🟢 Low

## Making This Usable for Unions
### What Unions Need
### What's Missing
### Must-Have vs Nice-to-Have
### Path to Adoption

## Top 10 Actions (If You Could Only Do 10 Things)
(Ranked list combining technical fixes and union-usability improvements)
```

**Save your report as: `[toolname]_audit_report.md`**
(Example: `gemini_audit_report.md`, `codex_audit_report.md`, `claude_audit_report.md`)

---

## Important Notes

- **Be honest.** Diplomatic but direct. If something is bad, say so.
- **Be specific.** "The API has security issues" is useless. "Endpoint /api/employers/search constructs SQL using f-string interpolation at line 234" is useful.
- **Think like a union organizer**, not just a programmer. The ultimate question is: would this actually help workers?
- **Do not look at or reference any previous audit reports** in the `docs/` folder or elsewhere. This is a blind audit.
- **Take your time.** Read the code. Run queries if you can. Look at actual data. Don't just skim file names.
