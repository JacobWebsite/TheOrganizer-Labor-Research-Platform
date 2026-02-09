# Honest Assessment & Comprehensive Roadmap: From Now to Deployable

**Date:** February 9, 2026
**Version:** 2.0 (supersedes v1.0 from February 8, 2026)
**Perspective:** Written as if advising a union president
**Scope:** Current state audit + complete technical roadmap to publication-ready deployment

---

## Table of Contents

1. [Honest Assessment](#honest-assessment-if-i-were-a-union-president)
2. [Architecture Overview (As-Is)](#architecture-overview-as-is)
3. [Security Audit](#security-audit-critical)
4. [Data Pipeline Architecture](#data-pipeline-architecture)
5. [Phase 0: Stabilize What Exists](#phase-0-stabilize-what-exists-weeks-1-3)
6. [Phase 1: Clean the Foundation](#phase-1-clean-the-foundation-weeks-3-5)
7. [Phase 2: Validate and Upgrade the Scorecard](#phase-2-validate-and-upgrade-the-scorecard-weeks-5-9)
8. [Phase 3: Architecture for Deployment](#phase-3-architecture-for-deployment-weeks-7-12)
9. [Phase 4: Build the Decision Interface](#phase-4-build-the-decision-interface-weeks-10-15)
10. [Phase 5: Publication Readiness](#phase-5-publication-readiness-weeks-14-18)
11. [Phase 6: Post-Launch Growth](#phase-6-post-launch-growth-ongoing)
12. [Summary Timeline](#summary-timeline)
13. [Current Data Inventory](#current-data-inventory-february-2026)
14. [Complete Database Schema Reference](#complete-database-schema-reference)
15. [Script Inventory & Pipeline Map](#script-inventory--pipeline-map)
16. [Technical Debt Registry](#technical-debt-registry)
17. [Decision Log & Architectural Choices](#decision-log--architectural-choices)
18. [Risk Register](#risk-register)
19. [Appendix A: What I'd Cut / What I'd Never Cut](#appendix-a-what-id-cut--what-id-never-cut)
20. [Appendix B: Cost Projections](#appendix-b-cost-projections)
21. [Appendix C: Glossary](#appendix-c-glossary)

---

## Honest Assessment: If I Were a Union President

### What I'd Say to My Executive Board

**"We have something genuinely remarkable here -- and also something that can't leave this laptop."**

### The Good (and it's legitimately good)

**The data is real.** 14.5 million members counted, validated against the BLS within 1.4%. That's not a rounding error -- that's publishable accuracy. Fifty out of 51 states reconciled against EPI benchmarks within 15%. The one miss (Texas) has a documented methodological explanation that would hold up under scrutiny. If someone challenged our numbers, we could defend them.

**The coverage is extraordinary.** 60,953 deduplicated employers. 2.2 million OSHA violations worth $3.52 billion in penalties. 363,000 wage theft cases totaling $4.7 billion in backwages. 33,000 NLRB elections. GLEIF corporate ownership chains with 498,963 parent-child links. USASpending federal contractor data. IRS 990 nonprofit financials. This isn't a spreadsheet -- it's 90+ database tables with genuine cross-referencing between them, backed by a 33GB PostgreSQL database.

**The matching is sophisticated.** Splink probabilistic linking, RapidFuzz composite scoring (0.35xJaroWinkler + 0.35xtoken_set_ratio + 0.30xfuzz.ratio), cleanco name normalization, pg_trgm candidate retrieval -- these aren't buzzwords. They turned 3,010 cross-referenced employer identities into 14,561 through six distinct matching tiers. They merged 1,210 duplicate employers with zero errors using union-find grouping with cascading updates across 6 downstream tables. That's real data engineering, not just duct tape.

**The validation methodology is defensible.** The platform cross-references against three independent benchmarks (BLS CPS for national totals, EPI analysis for state-level public sector, and NLRB for election outcomes). The hierarchy-based deduplication system accounts for federation/intermediate/international/local double-counting, retirees (-2.1M), Canadian members (-1.3M), and NEA/AFT dual affiliates (-903K). The 70.1M raw OLMS figure systematically reconciles to 14.5M. Any labor economist could follow the methodology paper and reproduce the result.

### The Problems (and a union president would find them fast)

**1. Nobody can use this but the person who built it.**

It runs on one Windows laptop in a Downloads folder, started from a batch file (`start-claude.bat`), serving `localhost:8001`. There is no login, no deployment, no URL anyone else can visit. My organizing director can't see it. My regional VPs can't see it. It's the world's most well-informed single-user application.

The startup command is literally:
```
cd /d "C:\Users\jakew\Downloads\labor-data-project"
py -m uvicorn api.labor_api_v6:app --reload --port 8001
```

**2. The frontend is a prototype pretending to be a product.**

`organizer_v5.html` is a single 476KB HTML file -- 8,841 lines of inline JavaScript, CSS, Tailwind via CDN, Leaflet.js, Chart.js, and MarkerCluster, all in one document. That's not a web application -- that's a proof of concept. It uses CDN-loaded dependencies (meaning it breaks without internet), has no build step, no component structure, no state management, and no way for two developers to work on it simultaneously without merge conflicts on every commit. A union president would open it, click around for 30 seconds, and say "this looks like a developer tool."

**3. The scorecard -- the platform's whole value proposition -- hasn't been validated.**

The 8-factor, 0-62 point scoring system exists and runs. The factors are:

| Factor | Range | What It Measures |
|---|---|---|
| `score_geographic` | varies | Location-based organizing likelihood |
| `score_size` | 0-5 | Employer bargaining unit size |
| `score_industry_density` | 0-10 | Union density in that NAICS/geography |
| `score_nlrb_momentum` | 0-10 | NLRB election activity in the sector |
| `score_osha_violations` | 0-4 | Workplace safety violation history |
| `score_govt_contracts` | 0-15 | Federal contractor status and volume |
| `sibling_union_bonus` | 0-8 | Other bargaining units at same employer |
| `score_labor_violations` | 0-10 | Wage theft, ULP cases, debarment |

Tiers: TOP (>=30), HIGH (25-29), MEDIUM (15-24), LOW (<15).

But nobody has checked whether the employers it ranks #1 are actually better organizing targets than the ones it ranks #500. There are 33,096 NLRB election outcomes sitting in the database that could validate or invalidate the scoring model, and that analysis hasn't been done. The weights were assigned by judgment, not data. A union president relying on this scorecard is trusting a formula, not evidence.

**4. Match rates on the newest data are painfully low.**

| Data Source | Records | Matched to F7 | Rate | Gap |
|---|---|---|---|---|
| OSHA | 1,007,217 | 79,981 | 7.9% | 927,236 unlinked establishments |
| WHD Wage Theft | 363,365 | ~17,000 | ~4.8% | 346,365 unlinked cases |
| Mergent | 56,431 | ~3,400 | ~6.0% | 53,031 unlinked businesses |
| GLEIF | 379,192 | ~3,300 | ~0.9% | 375,892 unlinked entities |
| USASpending | 47,193 | 9,305 | 19.7% | 37,888 unlinked recipients |
| IRS 990 (National) | 586,767 | 0 | 0.0% | Not yet matched |

These numbers mean that for most employers in the system, the "violations" and "corporate ownership" sections of their profile are blank. The infrastructure exists to display the data, but the data isn't connected for 80-95% of employers. An organizing director who pulls up an employer and sees empty OSHA and wage theft sections will lose trust in the entire platform.

**The matching problem is structural, not just algorithmic.** F7 employers are bargaining units (union-reported), while OSHA/WHD/Mergent are establishment-level (employer-reported). The same company might appear as "ABC MANUFACTURING INC" in F7, "ABC MFG" in OSHA, "A.B.C. Manufacturing, Incorporated" in WHD, and "ABC Manufacturing LLC" in Mergent. Address matching helps, but F7 addresses are often union hall addresses, not employer worksites.

**5. There's no data pipeline. Everything is manual.**

Every data source was loaded by running a one-off Python script. When OSHA updates their violation data next quarter, someone needs to manually re-download, re-run the ETL, re-match, and re-validate. There are 440 Python scripts in the `scripts/` folder organized across 18 subdirectories with no orchestration, no scheduling, no dependency tracking, and no way to know which scripts to run in what order.

The ETL scripts are hardcoded to specific file paths on the developer's machine:
```python
# From load_whd_national.py
CSV_PATH = r"C:\Users\jakew\Downloads\labor-data-project\whd_whisard_20260116.csv"

# From load_gleif_bods.py
PGDUMP_PATH = r'C:\Users\jakew\Downloads\pgdump.sql.gz'

# From load_osha_violations.py
SQLITE_DB = r'C:\Users\jakew\Downloads\osha_enforcement.db'
```

This isn't a platform -- it's a collection of bespoke data engineering sessions.

**6. Security is nonexistent -- and the vulnerabilities are specific and severe.**

This is the most urgent problem. The API has **65+ SQL injection vulnerabilities** through f-string WHERE clause construction, **hardcoded database credentials** (password: `<password in .env file>` in `labor_api_v6.py` line 35, README.md, CLAUDE.md, and dozens of scripts), **no authentication** on any of 142 endpoints including POST endpoints that modify data, **wide-open CORS** (`allow_origins=["*"]`), and **no connection pooling** (a new psycopg2 connection per request). See the [Security Audit](#security-audit-critical) section for the full breakdown.

**7. The project lives in a Downloads folder with no dependency management.**

The physical location is `C:\Users\jakew\Downloads\labor-data-project`. There is no `requirements.txt`, no `pyproject.toml`, no `Dockerfile`, no `docker-compose.yml`. The Python dependencies (psycopg2, pandas, splink 4.0.12, RapidFuzz, cleanco, FastAPI, uvicorn, jellyfish) are installed globally. There's a `.git` directory but no evidence of regular pushes to a remote. If this laptop dies, the 33GB database and any uncommitted work vanish.

### The Bottom Line

**What we have:** The most comprehensive labor relations dataset I've ever seen, with validated methodology, sophisticated entity resolution, genuine analytical capability, and 142 API endpoints already serving the data.

**What we don't have:** A product. No deployment, no multi-user access, no validated scoring, no data freshness, no security, no testing, no dependency management, and a frontend that can't scale.

The gap between "impressive research database" and "deployable platform for publication" is approximately **280-350 hours of focused work**. The previous estimate of 211 hours underweighted security remediation (the SQL injection count alone was unknown), the IRS 990 matching gap, and the complexity of standing up a real deployment pipeline. This roadmap accounts for all of it.

---

## Architecture Overview (As-Is)

### System Diagram

```
+---------------------------+       +----------------------------+
|  organizer_v5.html        |       |  Developer's Laptop        |
|  (476KB monolith)         |       |  (Windows 11)              |
|  Tailwind CSS (CDN)       |       |  Python 3.14               |
|  Leaflet.js (CDN)         |  HTTP |  PostgreSQL 17             |
|  Chart.js (CDN)           | <---> |  33GB database             |
|  MarkerCluster (CDN)      |       |  440 Python scripts        |
|  8,841 lines inline JS    |       |  102 SQL files             |
+---------------------------+       +----------------------------+
                                           |
                                    +------+------+
                                    |             |
                              labor_api_v6.py   start-claude.bat
                              (6,642 lines)     (batch launcher)
                              142 endpoints
                              FastAPI + psycopg2
                              Port 8001
                              No auth, no TLS
```

### Technology Stack

| Layer | Technology | Version | Status |
|---|---|---|---|
| Language | Python | 3.14 | Bleeding-edge; `\s` escape warnings |
| Web Framework | FastAPI | latest | Good choice, underutilized |
| Database | PostgreSQL | 17 | Solid, well-indexed |
| DB Driver | psycopg2 | latest | No connection pooling |
| Entity Resolution | Splink | 4.0.12 | DuckDB backend, works well |
| Fuzzy Matching | RapidFuzz | latest | Composite scoring implemented |
| Name Normalization | cleanco | latest | Critical for international suffixes |
| Trigram Search | pg_trgm | PostgreSQL ext | Top-5 candidate retrieval |
| Frontend | Raw HTML | N/A | Single-file monolith |
| CSS | Tailwind | CDN | No build step, no purging |
| Mapping | Leaflet.js | 1.9.4 | CDN-loaded |
| Charts | Chart.js | 4.4.1 | CDN-loaded |
| Deployment | None | N/A | `localhost:8001` only |

### Database Statistics

| Metric | Value |
|---|---|
| Total database size | ~33GB |
| Total tables | 90+ |
| Largest table | `lm_data` (2.6M+ rows) |
| Most complex view | `mv_employer_search` (120,169 rows) |
| Materialized views | 10+ |
| Indexes | Unaudited (likely missing key ones) |

### Codebase Statistics

| Metric | Value |
|---|---|
| Python scripts (scripts/) | 440 across 18 subdirectories |
| Python scripts (total) | 702 including archive/other |
| SQL files | 102 (~1.9M lines including BLS archives) |
| API endpoints | 142 (GET, POST, DELETE) |
| API code | 6,642 lines in single file |
| Frontend code | 8,841 lines in single HTML file |
| Documentation | 103 markdown files |
| Test files | 15 (mostly ad-hoc, not pytest) |
| Data files | 375MB+ in data/ directory |

---

## Security Audit (CRITICAL)

This section documents every known security vulnerability. **None of these can be deferred.** Every issue in the "Critical" and "High" categories must be fixed before any deployment.

### CRITICAL: SQL Injection (65+ vulnerable endpoints)

The API constructs SQL queries using Python f-strings with user-controlled WHERE clauses. This is the textbook definition of SQL injection.

**Pattern found 65+ times:**
```python
# VULNERABLE (actual code from labor_api_v6.py)
cur.execute(f"""
    SELECT aff_abbr, COUNT(*) as local_count
    FROM unions_master
    WHERE {where_clause}  -- User input injected directly
    GROUP BY aff_abbr
""", params)
```

**Vulnerable lines (sampled):** 94, 179, 590, 599, 901, 1171, 1291, 1305, 1380, 1394, 2023, 2095, 2102, 2144, 2153, 2186, 2197, 2235, 2253, 2325, 2330, 2514, 2528, 3123, 3131, 3399, 3491, 3503, 3558, 3590, 3623, 3741, 3753, 3790, 3906, 3916, 3930, 3943, 4027, 4067, 4103, 4168, 4300, 4393, 4424, 4493, 4581, 4838, 4990, 5697, 5705, 5749, 5898, 5999, 6010, 6108, 6117, 6227, 6234, 6473, 6482, 6509

**Especially dangerous -- dynamic table names:**
```python
# Line 6509: Table name from user input
cur.execute(f"SELECT * FROM {view_name}")
```

**Impact:** An attacker could extract the entire database, modify data, or execute arbitrary PostgreSQL functions. The database contains sensitive employer information, union organizing strategy data, and 586,767 IRS 990 nonprofit filings.

**Remediation:** Replace all f-string WHERE clause construction with parameterized queries using `%s` placeholders. For dynamic table/column names, use a whitelist lookup. Estimated: 12-16 hours to audit and fix all 142 endpoints.

### CRITICAL: Hardcoded Credentials

**Location:** `api/labor_api_v6.py` lines 30-36
```python
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': '<password in .env file>'
}
```

Also present in: `README.md`, `CLAUDE.md`, and at least 20+ Python scripts in `scripts/`.

**Remediation:** Move to `.env` file, read via `os.environ` or `python-dotenv`. Rotate the database password after cleanup. Scrub from git history with `git filter-repo` or BFG Repo Cleaner.

### CRITICAL: No Authentication

All 142 API endpoints are publicly accessible. This includes:
- **POST /api/employers/{id}/flags** (line 2473) -- anyone can flag employers
- **DELETE /api/employers/{id}/flags/{flag_id}** -- anyone can remove flags
- All read endpoints expose the complete database

**Remediation:** Add authentication middleware (JWT or session-based). See [Phase 3.2](#32-authentication-and-authorization-15-hrs).

### HIGH: Permissive CORS

**Lines 23-28:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This allows any website to make authenticated requests to the API, enabling CSRF and credential exfiltration once auth is added.

**Remediation:** Whitelist specific origins. For development: `["http://localhost:3000", "http://localhost:8001"]`. For production: the actual domain.

### HIGH: No Connection Pooling

**Line 38-39:**
```python
def get_db():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
```

Every request creates a new database connection. PostgreSQL has a default limit of 100 concurrent connections. Under load, this will exhaust connections and crash the API.

**Remediation:** Use `psycopg2.pool.ThreadedConnectionPool` or switch to `asyncpg` for async support. Alternatively, use PgBouncer as an external connection pooler.

### MEDIUM: Unbounded Result Sets

11+ endpoints return `SELECT *` without `LIMIT`:
- Line 293: `/api/density/naics/{code}` -- full table scan
- Lines 3971-3998: VR summary endpoints -- no pagination
- Line 4209: Organizing by state -- could return thousands
- Line 6509: Dynamic view query -- completely unbounded

**Remediation:** Add `LIMIT`/`OFFSET` pagination to all list endpoints. Default to 50, max 500.

### MEDIUM: Silent Error Swallowing

**Line 5367-5370:**
```python
try:
    cur.execute("SELECT COUNT(*) FROM gleif_us_entities")
except Exception:
    pass  # Database errors silently ignored
```

**Remediation:** Add structured logging. At minimum, log all exceptions. Use FastAPI's exception handlers for consistent error responses.

### LOW: No Rate Limiting

No request throttling on any endpoint. A single client could hammer the API and consume all database connections.

**Remediation:** Add `slowapi` or nginx-level rate limiting. Suggested: 60 requests/minute for unauthenticated, 300/minute for authenticated.

### LOW: No Request Logging

No access logs, no audit trail, no way to know who queried what or when.

**Remediation:** Add structured logging middleware. Log: timestamp, client IP, endpoint, response code, duration.

---

## Data Pipeline Architecture

### Current Data Flow

```
RAW DATA SOURCES
  |
  |  Manual downloads to C:\Users\jakew\Downloads\
  v
+------------------------------------------------------------------+
| ETL LAYER (one-off scripts, hardcoded paths)                     |
|                                                                  |
| load_whd_national.py  --> whd_cases (363K)                       |
| load_gleif_bods.py    --> gleif_us_entities (379K)                |
|                       --> gleif_ownership_links (499K)            |
| fetch_qcew.py         --> qcew_annual (1.9M)                     |
| fetch_usaspending.py  --> federal_contract_recipients (47K)      |
| load_osha_violations  --> osha_violations_detail (2.2M)          |
| load_mergent.py       --> mergent_employers (56K)                |
| [NLRB scripts]        --> nlrb_elections (33K)                   |
|                       --> nlrb_participants (1.9M)                |
+------------------------------------------------------------------+
  |
  v
+------------------------------------------------------------------+
| MATCHING LAYER                                                   |
|                                                                  |
| Tier 1: Deterministic (exact name+city+state, EIN, DUNS, LEI)   |
|   - 1,127 EIN exact (SEC<->Mergent)                             |
|   - 84 LEI exact (SEC<->GLEIF)                                  |
|                                                                  |
| Tier 2: Normalized (cleanco + name+state)                        |
|   - 3,009 name+state matches                                    |
|                                                                  |
| Tier 3: Splink Probabilistic (JW>=0.88, prob>=0.85)             |
|   - Mergent->F7: 947 matches                                    |
|   - GLEIF->F7: 605 matches                                      |
|   - Blocking: state+substr(name,1,3), state+city, zip_prefix    |
|   - Comparison: name(JW 4-level), state, city(Lev), zip(JW),    |
|     naics(exact+TF), address(JW)                                |
|                                                                  |
| Tier 4: USASpending (exact + pg_trgm fuzzy)                     |
|   - 1,994 exact name+state                                      |
|   - 6,795 fuzzy (pg_trgm >= 0.55)                               |
|                                                                  |
| --> corporate_identifier_crosswalk (14,561 rows)                 |
+------------------------------------------------------------------+
  |
  v
+------------------------------------------------------------------+
| CONSOLIDATION LAYER                                              |
|                                                                  |
| merge_f7_enhanced.py:                                            |
|   1. Union-find grouping (transitive closure of duplicate pairs) |
|   2. Keeper selection (largest unit_size, most notices, alpha)   |
|   3. Cascade to 6 tables: f7_union_employer_relations,          |
|      nlrb_voluntary_recognition, nlrb_participants,              |
|      osha_f7_matches, mergent_employers,                         |
|      corporate_identifier_crosswalk                              |
|   4. COALESCE identifiers on crosswalk merge                    |
|   5. Audit log to f7_employer_merge_log                         |
|                                                                  |
| link_multi_location.py:                                          |
|   - 969 employers in 459 corporate_parent_id groups              |
+------------------------------------------------------------------+
  |
  v
+------------------------------------------------------------------+
| SCORING LAYER                                                    |
|                                                                  |
| 8 factors, 0-62 points:                                         |
|   score_geographic (varies)                                      |
|   score_size (0-5)                                               |
|   score_industry_density (0-10) -- from QCEW/BLS                |
|   score_nlrb_momentum (0-10) -- NLRB activity by NAICS          |
|   score_osha_violations (0-4)                                    |
|   score_govt_contracts (0-15) -- USASpending                     |
|   sibling_union_bonus (0-8) -- other BUs at same employer       |
|   score_labor_violations (0-10):                                 |
|     - Wage theft: 0-4 pts (>=$100K=4, >=$50K=3, >=$10K=2, >0=1)|
|     - ULP cases: 0-3 pts (>=3=3, >=2=2, >=1=1)                 |
|     - Local labor law: 0-2 pts (>=2=2, >=1=1)                   |
|     - Debarment: 0-1 pt                                         |
|                                                                  |
| Tiers: TOP>=30, HIGH>=25, MEDIUM>=15, LOW<15                    |
+------------------------------------------------------------------+
  |
  v
+------------------------------------------------------------------+
| SERVING LAYER                                                    |
|                                                                  |
| labor_api_v6.py (FastAPI, 6,642 lines, 142 endpoints)           |
|   - No auth, no rate limiting                                   |
|   - psycopg2 (no pooling)                                       |
|   - Materialized views for search (mv_employer_search: 120K)    |
|   - Key views: v_union_members_deduplicated,                    |
|     v_state_epi_comparison, v_nlrb_union_win_rates              |
|                                                                  |
| organizer_v5.html (476KB SPA, CDN deps)                         |
+------------------------------------------------------------------+
```

### Data Source Update Frequencies

| Source | Update Cadence | Current File | API/Download |
|---|---|---|---|
| OLMS (LM filings) | Annual (March) | SQLite dump | `olms.dol.gov` |
| OSHA (violations) | Quarterly | `osha_enforcement.db` | OSHA IMIS |
| NLRB (elections) | Monthly | API scrape | `nlrb.gov/api` |
| WHD (wage theft) | Quarterly | `whd_whisard_*.csv` | DOL download |
| USASpending | Annual (FY rollover) | Paginated API | `api.usaspending.gov` |
| QCEW | Annual (Q3 release) | BLS zip file | `data.bls.gov/cew` |
| GLEIF | Quarterly | `pgdump.sql.gz` | Open Ownership |
| SEC | Continuous | EDGAR API | `efts.sec.gov` |
| Mergent | On-demand | CSV export | CUNY library access |
| IRS 990 | Annual | AWS bulk | `s3.amazonaws.com/irs-form-990` |
| BLS CPS | Annual (January) | Manual entry | `bls.gov/cps` |
| EPI State | Annual | Manual entry | EPI publications |

---

## Phase 0: Stabilize What Exists (Weeks 1-3)

*Before building anything new, stop the foundation from shifting. This phase has zero user-visible output. It's entirely about reducing risk.*

### 0.1 Emergency Security Triage (8 hrs)

The SQL injection vulnerabilities and hardcoded credentials are the most urgent items in this entire roadmap. If the API is ever accidentally exposed to a network (e.g., via ngrok, a misconfigured firewall, or a shared WiFi), the entire database is compromised.

**0.1.1 Extract credentials to environment variables (2 hrs)**
- Create `.env` file at project root:
  ```
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=olms_multiyear
  DB_USER=postgres
  DB_PASSWORD=<new_rotated_password>
  API_SECRET_KEY=<generate_random_key>
  ```
- Add `.env` to `.gitignore` (verify it's not already tracked)
- Create `.env.example` with placeholder values for documentation
- Install `python-dotenv`, update `labor_api_v6.py` lines 30-36:
  ```python
  from dotenv import load_dotenv
  import os
  load_dotenv()
  DB_CONFIG = {
      'host': os.getenv('DB_HOST', 'localhost'),
      'port': int(os.getenv('DB_PORT', 5432)),
      'database': os.getenv('DB_NAME', 'olms_multiyear'),
      'user': os.getenv('DB_USER', 'postgres'),
      'password': os.getenv('DB_PASSWORD'),
  }
  ```
- Grep all Python files for the old password string, update each one
- Remove password from `README.md` and `CLAUDE.md`
- Rotate the PostgreSQL password after all files are updated

**0.1.2 Fix SQL injection vulnerabilities (6 hrs)**

This is the single highest-priority code change. Every f-string WHERE clause must be replaced with parameterized queries.

**Current vulnerable pattern:**
```python
conditions = []
params = []
if state:
    conditions.append("state = %s")
    params.append(state)
where_clause = " AND ".join(conditions) if conditions else "TRUE"
cur.execute(f"SELECT * FROM table WHERE {where_clause}", params)
```

The `where_clause` itself is safe here (it's built from hardcoded strings with `%s` placeholders), but the f-string pattern is fragile -- it relies on every developer always using `%s` and never interpolating user input into `conditions`. The real danger is lines like 6509 where a *table name* is injected via f-string.

**Remediation approach:**
1. Audit all 142 endpoints for the f-string pattern
2. For WHERE clause builders: verify all conditions use `%s` placeholders (most already do -- the pattern is safe-but-fragile)
3. For dynamic table/column names (lines 6473-6509): replace with whitelist:
   ```python
   ALLOWED_VIEWS = {'v_museum_target_stats', 'v_osha_organizing_targets', ...}
   if view_name not in ALLOWED_VIEWS:
       raise HTTPException(400, "Invalid view name")
   ```
4. Add a linting rule or pre-commit hook to flag `cur.execute(f"` patterns

**Acceptance criteria:** `grep -c 'cur.execute(f"' labor_api_v6.py` returns 0 for dynamic table names. All WHERE builders verified to use parameterized placeholders only.

### 0.2 Git Hygiene and Backup (4 hrs)

**0.2.1 Credential scrubbing (1 hr)**
- Use BFG Repo Cleaner or `git filter-repo` to remove the password from git history
- Force-push the cleaned history (document this for any collaborators)
- Verify: `git log -p --all -S 'Juniordog33'` returns nothing

**0.2.2 .gitignore audit (1 hr)**
Current `.gitignore` already excludes `data/`, `output/`, `archive/`, `*.xlsx`, `*.pdf`, `*.zip`, `__pycache__/`. Verify and add:
```gitignore
.env
*.db
*.sqlite
*.sql.gz
*.csv
!data/epi_state_benchmarks_2025.csv  # small reference files OK
```

**0.2.3 Remote backup (1 hr)**
- Push to GitHub (private repo)
- Set up GitHub Actions for automated push reminder (or just verify remote exists)
- Document: the 33GB PostgreSQL database is NOT in git. Backup strategy:
  - `pg_dump olms_multiyear | gzip > backup_$(date +%Y%m%d).sql.gz`
  - Store on external drive or cloud storage (S3/Backblaze B2, ~$0.50/month for 33GB)

**0.2.4 Project relocation (1 hr)**
- Move from `C:\Users\jakew\Downloads\labor-data-project` to `C:\Users\jakew\projects\labor-data-project` (or equivalent proper location)
- Update `start-claude.bat` path
- Update any hardcoded paths in scripts (grep for `Downloads`)
- Document the new canonical path

### 0.3 Environment Reproducibility (8 hrs)

**0.3.1 Dependency management (3 hrs)**
- Create `pyproject.toml` with all dependencies:
  ```toml
  [project]
  name = "labor-research-platform"
  version = "0.1.0"
  requires-python = ">=3.11"
  dependencies = [
      "fastapi>=0.104.0",
      "uvicorn[standard]>=0.24.0",
      "psycopg2-binary>=2.9.9",
      "python-dotenv>=1.0.0",
      "pandas>=2.1.0",
      "splink>=4.0.12",
      "rapidfuzz>=3.5.0",
      "cleanco>=2.2",
      "jellyfish>=1.0.0",
      "httpx>=0.25.0",
  ]

  [project.optional-dependencies]
  dev = ["pytest>=7.4.0", "ruff>=0.1.0", "pre-commit>=3.5.0"]
  ```
- Test: `pip install -e .` on a clean virtualenv
- Document any system-level dependencies (PostgreSQL 17, pg_trgm extension)

**0.3.2 Database setup script (3 hrs)**
- Create `scripts/setup/init_database.py`:
  1. Create database `olms_multiyear` if not exists
  2. Enable extensions: `pg_trgm`, `uuid-ossp`
  3. Run schema files in order (from `sql/schema/`)
  4. Create materialized views
  5. Report: table count, expected vs actual
- Create `scripts/setup/seed_reference_data.py`:
  - Load lookup tables: `union_sector`, `naics_sectors`, `state_fips_map`, `cbsa_reference`
  - Load benchmarks: `epi_state_benchmarks`, `bls_industry_density`
- Test on a second machine (or in Docker) to verify reproducibility

**0.3.3 Configuration management (2 hrs)**
- Create `config.py` module:
  ```python
  import os
  from dotenv import load_dotenv
  load_dotenv()

  DB_HOST = os.getenv('DB_HOST', 'localhost')
  DB_PORT = int(os.getenv('DB_PORT', 5432))
  DB_NAME = os.getenv('DB_NAME', 'olms_multiyear')
  DB_USER = os.getenv('DB_USER', 'postgres')
  DB_PASSWORD = os.getenv('DB_PASSWORD')

  DATA_DIR = os.getenv('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
  ```
- Update the ~30 actively-used scripts to import from `config` instead of hardcoding
- The remaining ~410 archived/inactive scripts can stay as-is (document which are active)

### 0.4 Connection Pooling (2 hrs)

Replace the per-request connection creation with a pool:

```python
from psycopg2.pool import ThreadedConnectionPool

pool = ThreadedConnectionPool(
    minconn=2,
    maxconn=20,
    **DB_CONFIG,
    cursor_factory=RealDictCursor
)

def get_db():
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)
```

This prevents connection exhaustion under load and reduces per-request latency by ~5-10ms.

### 0.5 Automated Test Baseline (10 hrs)

**0.5.1 API integration tests (5 hrs)**
Write pytest tests for the 20 most critical endpoints:
- `/api/summary` -- basic health check
- `/api/employers/search?q=walmart` -- search returns results
- `/api/employers/{id}` -- detail returns expected fields
- `/api/unions/search?q=seiu` -- union search
- `/api/nlrb/elections?state=NY` -- NLRB filtering
- `/api/density/by-state` -- density data exists
- `/api/osha/summary` -- OSHA aggregation
- `/api/lookups/sectors` -- reference data
- etc.

Each test verifies: HTTP 200, response has expected keys, data is non-empty, response time < 2 seconds.

**0.5.2 Data validation tests (3 hrs)**
Automate the 8 integrity checks from the February 8 sprint:
1. BLS total alignment (< 5% variance)
2. State coverage vs EPI (50/51 within 15%)
3. No orphan records in crosswalk
4. F7 employer count stability (60,953 +/- 100)
5. NLRB match rate (> 95%)
6. Materialized view freshness
7. No NULL primary keys in core tables
8. Sector classification completeness

**0.5.3 Test infrastructure (2 hrs)**
- `pytest.ini` or `pyproject.toml` test config
- GitHub Actions workflow: run tests on push
- Test database fixture (or test against production with read-only assertions)

**Phase 0 Deliverable:** The project can be cloned, configured, and running on a new machine in under 30 minutes. Passwords aren't in the repo or git history. SQL injection vectors are closed. Connection pooling is active. 20+ tests pass on every push.

**Phase 0 Total: ~32 hrs**

---

## Phase 1: Clean the Foundation (Weeks 3-5)

*Mostly from Roadmap v12 Phase 1, adjusted for what's already done and what the audit revealed.*

### 1.1 Remaining Duplicate Resolution (6 hrs)

The 1,210 Splink merges are done (967 SPLINK_CONFIRMED + 243 NEW_MATCH). The remaining work:

**1.1.1 Complex duplicate review (4 hrs)**
- The 234 edge cases from v12 Task 1.2 (different cities, ambiguous names)
- Build a CLI review tool:
  ```
  PAIR: "ABC Manufacturing" (NYC) vs "ABC Mfg Inc" (Newark)
  Score: 0.82 | Name JW: 0.91 | Same NAICS: Yes | Distance: 12 miles
  [M]erge  [K]eep both  [S]kip  [?]Details
  ```
- Decision criteria: merge if JW >= 0.88 AND (same city OR distance < 25 miles AND same NAICS)
- Log all decisions for audit trail

**1.1.2 Multi-location consolidation review (2 hrs)**
- 969 employers in 459 corporate_parent_id groups need spot-checking
- Verify that no false positives crept in (same name, different companies)
- Sample 50 groups, check 10% manually

### 1.2 Fill Missing NAICS Codes (4 hrs)

~8,000 employers missing industry codes. Backfill strategy (in priority order):

1. **OSHA match** (highest coverage): If the employer has an OSHA establishment match, inherit NAICS
2. **QCEW validation**: Cross-reference state+county NAICS distribution for plausibility
3. **Mergent match**: If crosswalk links to Mergent, inherit `naics_primary`
4. **Keyword inference**: Pattern matching on employer name:
   | Pattern | NAICS | Confidence |
   |---|---|---|
   | HOSPITAL, MEDICAL CENTER | 622110 | High |
   | SCHOOL DISTRICT, ACADEMY | 611110 | High |
   | HOTEL, MARRIOTT, HILTON | 721110 | High |
   | CONSTRUCTION, BUILDING | 236xxx | Medium |
   | TRUCKING, FREIGHT | 484xxx | Medium |
5. **Manual review**: Remaining gaps after automated passes

**Acceptance criteria:** < 500 employers with NULL NAICS (< 1% of 60,953)

### 1.3 Geocode Remaining Employers (6 hrs)

~16,000 employers without coordinates (current geocoding: 57.2%).

**1.3.1 Census Geocoder batch API (4 hrs)**
- Free, no API key, 10,000 records per batch
- Format: street, city, state, zip -> latitude, longitude, match quality
- Expected yield: ~12,000 matches (75% of remaining)
- Flag PO Boxes and non-geocodable addresses as `geocode_status = 'FAILED'`

**1.3.2 Fallback: city centroid (1 hr)**
- For employers where street address fails, use city+state centroid
- Mark as `geocode_quality = 'CITY_CENTROID'` (distinct from precise geocodes)
- Still useful for state/county-level map displays

**1.3.3 Map layer validation (1 hr)**
- Spot-check 50 geocoded employers against Google Maps
- Verify no offshore or clearly wrong coordinates
- Fix any state-level mismatches (address in NJ but coordinates in PA)

**Target: > 90% geocoded** (up from 57.2%)

### 1.4 Union Hierarchy Cleanup (4 hrs)

2,104 orphan locals already identified. These are locals that reference a parent union `f_num` that doesn't exist in `unions_master`.

**1.4.1 Automated re-linking (2 hrs)**
- Match orphans to parents by affiliation abbreviation + state
- If exact aff_abbr match exists in state, assign as parent
- Expected: ~1,500 resolved automatically

**1.4.2 Manual resolution (1.5 hrs)**
- Remaining ~600: check if union is disbanded, merged, or misfiled
- Mark disbanded unions as `status = 'DISBANDED'` with year
- Mark mergers with forwarding `merged_into_fnum`

**1.4.3 Revalidation (0.5 hrs)**
- Re-run BLS membership total calculation
- Verify: still within 1.4% of BLS CPS figure
- Verify: 50/51 states still within 15% of EPI

### 1.5 Sector Classification Audit (2 hrs)

Already scripted. Run the existing sector audit script, review flagged misclassifications:
- RAILROAD_AIRLINE_RLA employers incorrectly coded as PRIVATE
- PUBLIC_SECTOR employers in F7 (which is private-sector only)
- FEDERAL employees in state/local tables

**Acceptance criteria:** Zero cross-sector contamination in core tables.

### 1.6 Automated Validation Suite (6 hrs)

**1.6.1 Formalize integrity checks (3 hrs)**
Create `scripts/validation/run_all_checks.py`:
```python
CHECKS = [
    ("BLS Total Alignment", check_bls_total, {"max_variance": 0.05}),
    ("State EPI Coverage", check_state_coverage, {"min_states": 50, "threshold": 0.15}),
    ("Crosswalk Orphans", check_crosswalk_orphans, {"max_orphans": 0}),
    ("F7 Count Stability", check_f7_count, {"expected": 60953, "tolerance": 200}),
    ("NLRB Match Rate", check_nlrb_match, {"min_rate": 0.95}),
    ("Materialized View Freshness", check_mv_freshness, {"max_age_days": 7}),
    ("Null Primary Keys", check_null_pks, {"tables": CORE_TABLES}),
    ("Sector Completeness", check_sector_completeness, {"min_rate": 0.99}),
    ("Duplicate Detection", check_no_new_dupes, {"threshold": 0.95}),
    ("Geocode Coverage", check_geocode_coverage, {"min_rate": 0.90}),
]
```

**1.6.2 Drift detection (2 hrs)**
- Store baseline counts in a `validation_baselines` table
- Compare current counts on each run
- Alert (log + email) if any table changes > 5% without an ETL run

**1.6.3 Scheduling (1 hr)**
- Windows Task Scheduler: run weekly (Sunday 2 AM)
- Output to `logs/validation_YYYYMMDD.json`
- GitHub Actions: run on every push to main

**Phase 1 Deliverable:** All data quality metrics green. Employer count stable. BLS validation passes all sectors. Automated checks running weekly. > 90% geocoded. < 1% missing NAICS.

**Phase 1 Total: ~28 hrs**

---

## Phase 2: Validate and Upgrade the Scorecard (Weeks 5-9)

*This is where the platform goes from "data warehouse" to "decision tool." Phase 2.1 is the single most important task in this entire roadmap.*

### 2.1 Historical Outcome Validation (16 hrs) -- CRITICAL

This is the make-or-break analysis. If the scorecard doesn't predict real outcomes, the platform's value proposition collapses.

**2.1.1 Dataset preparation (3 hrs)**
- Pull all 33,096 NLRB elections with outcomes (win/loss/withdrawn)
- Join to F7 employers: employer size, NAICS, state, existing union presence
- Join to OSHA: violation count, penalty total, severity
- Join to WHD: wage theft cases, backwages
- Join to USASpending: federal contractor status
- Join to crosswalk: corporate hierarchy depth, parent company size
- Result: a features-plus-outcome dataset for every election

**2.1.2 Temporal split (1 hr)**
- Training set: elections before 2022 (~25,000)
- Test set: elections 2022-2024 (~8,000)
- Never let test data leak into training

**2.1.3 Current scorecard evaluation (4 hrs)**
- Apply the current 8-factor formula to historical elections
- Measure: AUC-ROC, precision@k (top 100, 500, 1000), calibration
- Key question: do employers scored TOP (>= 30) have a measurably higher win rate than MEDIUM (15-24)?
- Null hypothesis: the scorecard is no better than random
- If AUC < 0.55: the scorecard is noise and needs rebuilding
- If AUC 0.55-0.65: some signal, needs reweighting
- If AUC > 0.65: meaningful predictive power, document and publish

**2.1.4 Factor importance analysis (4 hrs)**
- Which of the 8 factors actually predict wins?
- Logistic regression with each factor as a feature
- Random forest feature importance
- Expected findings (hypotheses):
  - `score_industry_density` is probably the strongest predictor
  - `score_size` matters (larger units are harder to organize)
  - `score_osha_violations` may be weak (violations happen everywhere)
  - `sibling_union_bonus` should be strong (demonstrated organizing receptivity)

**2.1.5 Scorecard rebuild if needed (4 hrs)**
- If current weights are wrong, re-derive from logistic regression coefficients
- Normalize to 0-100 scale (more intuitive than 0-62)
- Cross-validate on training set, evaluate on test set
- Document the new weights with statistical justification

**Acceptance criteria:** A documented analysis showing whether the scorecard predicts election outcomes better than chance. If yes, publish the AUC and calibration curve. If no, rebuild with data-derived weights and re-validate.

**Why this matters:** Without validation, the platform is a research database with an opinions layer on top. With validation, it's an evidence-based decision tool. That's the difference between "interesting" and "fundable."

### 2.2 Employer Similarity Scoring (14 hrs)

The "comparables" feature -- for each non-union employer, find the most similar unionized employers. This is arguably more useful to organizers than the scorecard itself.

**2.2.1 Feature engineering (4 hrs)**
Features for similarity comparison:
- Industry (NAICS 2-digit sector, 4-digit subsector)
- Size (employee count, bucketed: <50, 50-200, 200-1000, 1000+)
- Geography (state, metro area, rural/urban)
- Violation profile (OSHA severity, WHD backwages)
- Corporate structure (subsidiary depth, parent company size)
- Federal contractor status

**2.2.2 Gower Distance implementation (6 hrs)**
- Gower Distance handles mixed types (categorical + numeric)
- For each non-union employer, find the 5 nearest unionized employers
- Store results in `employer_comparables` table:
  ```sql
  CREATE TABLE employer_comparables (
      employer_id INTEGER REFERENCES f7_employers_deduped(employer_id),
      comparable_employer_id INTEGER,
      similarity_score FLOAT,
      rank INTEGER,
      shared_features TEXT[],  -- e.g., ['same_naics', 'same_state', 'similar_size']
      PRIMARY KEY (employer_id, rank)
  );
  ```
- Pre-compute for all 60,953 employers (batch process)

**2.2.3 API endpoints (2 hrs)**
- `GET /api/employers/{id}/comparables` -- return top 5 similar unionized employers
- `GET /api/employers/{id}/comparables?features=naics,state` -- filter by specific features
- Include explanation: "This employer is similar because: same industry (NAICS 722511), same state (NY), similar size (150-200 employees)"

**2.2.4 Validation (2 hrs)**
- Spot-check 50 employer-comparable pairs
- Verify intuitive sense: a non-union hospital should find similar unionized hospitals, not auto dealerships
- Measure diversity: are all comparables from the same state? (bad -- should be geographically diverse)

### 2.3 Improve Match Rates (14 hrs)

Current match rates are the platform's biggest data coverage gap. Here's a targeted approach for each source.

**2.3.1 OSHA matching improvement (6 hrs)**

Current: 7.9% (79,981 / 1,007,217). Target: > 20%.

The problem: OSHA establishment names are often abbreviated, use DBA names, or are site-specific ("WALMART STORE #4532" vs F7's "WAL-MART STORES INC").

Strategy:
1. **Corporate parent matching**: If OSHA establishment matches a Mergent/GLEIF subsidiary, inherit the F7 link from the crosswalk
2. **Address-first matching**: Match on street address + city + state (OSHA has physical workplace addresses; F7 sometimes has them)
3. **Aggressive name normalization**: Strip store numbers, DBA prefixes, and legal suffixes before matching
4. **NAICS-constrained fuzzy**: Only fuzzy-match within the same 2-digit NAICS to reduce false positives

Expected yield breakdown:
| Method | Additional matches | Running total |
|---|---|---|
| Current (exact name+city) | 79,981 | 79,981 (7.9%) |
| Corporate parent inheritance | ~15,000 | ~95,000 (9.4%) |
| Address matching | ~40,000 | ~135,000 (13.4%) |
| Aggressive name normalization | ~30,000 | ~165,000 (16.4%) |
| NAICS-constrained fuzzy | ~40,000 | ~205,000 (20.3%) |

**2.3.2 WHD matching improvement (4 hrs)**

Current: 4.8% (~17,000 / 363,365). Target: > 12%.

The problem: WHD cases use `legal_name` and `trade_name` which often differ from F7's `employer_name`. Many WHD cases are small businesses not in F7 at all.

Strategy:
1. **Trade name matching**: Currently only matching on `legal_name`; add `trade_name` as fallback
2. **Mergent bridge**: Match WHD -> Mergent (by EIN or name+city), then Mergent -> F7 via crosswalk
3. **Address matching**: WHD has street addresses; match on address+city+state
4. **Accept lower confidence**: WHD tier 2 (name+state without city) is currently available but conservative; lower the pg_trgm threshold from 0.55 to 0.45 for WHD only

**2.3.3 IRS 990 matching (4 hrs)**

Current: 0% (586,767 national records loaded, zero matched to F7). This is the largest untapped data source.

Strategy:
1. **EIN-based matching**: 990 filers have EIN; crosswalk has EIN for ~1,127 employers. Direct join.
2. **Name+state matching**: `organization_name` from 990 against `employer_name_aggressive` from F7
3. **Expected yield**: 990 filers are nonprofits (hospitals, universities, social services); F7 has significant nonprofit coverage. Estimate: 5,000-15,000 matches (1-2.5% of 990 filers).
4. **Value add**: Revenue, total employees, executive compensation -- fields not available from any other source

### 2.4 Refresh and Re-Score All Employers (8 hrs)

After scorecard validation and match rate improvements:

**2.4.1 Re-run all matching pipelines (3 hrs)**
- Execute improved OSHA, WHD, and 990 matchers
- Update `corporate_identifier_crosswalk` with new links
- Refresh materialized views

**2.4.2 Re-score all employers (2 hrs)**
- Apply validated (or rebuilt) scorecard to all 60,953 employers
- Generate new tier assignments
- Store in `employer_scores_v2` (keep v1 for comparison)

**2.4.3 Generate ranked target lists (3 hrs)**
- By state (51 lists)
- By industry (21 sector lists)
- By union jurisdiction (top 20 affiliations)
- Export as CSV for immediate use by organizers even before the frontend is rebuilt

**Phase 2 Deliverable:** A scorecard validated against 33K real elections with documented AUC. Similarity-based comparables for every employer. Match rates: OSHA > 20%, WHD > 12%, 990 > 1%. Ranked target lists by state/industry/union.

**Phase 2 Total: ~52 hrs**

---

## Phase 3: Architecture for Deployment (Weeks 7-12)

*The hardest phase. This is where the laptop project becomes a deployable application. Every task in this phase is load-bearing -- skip any one and the deployment fails.*

### 3.1 API Restructure and Hardening (16 hrs)

The current API is a single 6,642-line file with 142 endpoints. It works, but it can't be maintained, tested, or deployed safely.

**3.1.1 Split into modules (6 hrs)**
```
api/
  __init__.py
  main.py              # FastAPI app creation, middleware, startup/shutdown
  config.py            # Settings from environment
  database.py          # Connection pool, get_db dependency
  middleware/
    auth.py            # Authentication middleware
    rate_limit.py      # Rate limiting
    logging.py         # Request/response logging
  routers/
    employers.py       # /api/employers/* (14 endpoints)
    unions.py          # /api/unions/* (9 endpoints)
    nlrb.py            # /api/nlrb/* (7 endpoints)
    osha.py            # /api/osha/* (4 endpoints)
    density.py         # /api/density/* (20 endpoints)
    projections.py     # /api/projections/* (14 endpoints)
    trends.py          # /api/trends/* (7 endpoints)
    lookups.py         # /api/lookups/* (6 endpoints)
    organizing.py      # /api/organizing/* + /api/vr/* (8 endpoints)
    corporate.py       # /api/corporate/* (3+ endpoints)
    sectors.py         # /api/sectors/* (sector-specific endpoints)
    admin.py           # Flag management, data refresh (auth required)
  models/
    schemas.py         # Pydantic response models
```

This split doesn't change any functionality -- it's purely organizational. Each router file is 200-600 lines instead of one file at 6,642.

**3.1.2 Add response pagination (4 hrs)**
- Create a standard pagination wrapper:
  ```python
  class PaginatedResponse(BaseModel):
      data: list
      total: int
      page: int
      per_page: int
      pages: int
  ```
- Apply to all list endpoints (currently 11+ return unbounded results)
- Default: 50 per page, max 500
- Endpoints affected: density lists, organizing targets, election searches, employer searches

**3.1.3 Input validation (3 hrs)**
- Add Pydantic models for all query parameters
- Validate state codes against a known list (not just any string)
- Validate NAICS codes against `naics_sectors` table
- Validate numeric ranges (year: 2000-2026, limit: 1-500)

**3.1.4 Error handling standardization (2 hrs)**
- Consistent error response format:
  ```json
  {"error": "message", "code": "INVALID_STATE", "detail": "State 'XX' not recognized"}
  ```
- Replace all `except Exception: pass` with proper logging + error response
- Add FastAPI exception handlers for database errors, validation errors

**3.1.5 CORS lockdown (1 hr)**
- Replace `allow_origins=["*"]` with specific origins
- Development: `["http://localhost:3000", "http://localhost:8001"]`
- Production: `[os.getenv("FRONTEND_URL")]`

### 3.2 Authentication and Authorization (15 hrs)

**3.2.1 Choose auth strategy (2 hrs)**

| Option | Pros | Cons | Recommendation |
|---|---|---|---|
| JWT (self-issued) | Simple, stateless, no external deps | Must handle refresh tokens, revocation | Good for v1 |
| Session cookies | Simpler client-side, familiar | Requires session store (Redis/DB) | Overkill for v1 |
| OAuth (Google/GitHub) | No password management | Requires external provider setup | Add in v2 |
| Auth0/Clerk | Fully managed | Monthly cost, vendor lock-in | Consider for scale |

**Recommendation:** JWT with refresh tokens for v1. Add OAuth as an option in v2.

**3.2.2 User model and roles (3 hrs)**
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
    organization VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    key_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

Roles:
- **admin**: Full access, can create users, manage flags, trigger data refreshes
- **organizer**: Read all data, export, create notes/flags
- **viewer**: Read-only access to dashboards and search
- **api**: Programmatic access via API key (for integrations)

**3.2.3 Auth middleware implementation (6 hrs)**
- Password hashing with `bcrypt`
- JWT token generation (access: 15 min, refresh: 7 days)
- FastAPI dependency: `current_user = Depends(get_current_user)`
- Apply to all endpoints (some public endpoints like `/api/health` exempt)
- POST endpoints (flags, admin) require `organizer` or `admin` role

**3.2.4 User management endpoints (2 hrs)**
- `POST /api/auth/register` (admin-only or invite-only)
- `POST /api/auth/login` -> returns JWT
- `POST /api/auth/refresh` -> new access token
- `GET /api/auth/me` -> current user info
- `PUT /api/auth/password` -> change password

**3.2.5 API key management (2 hrs)**
- `POST /api/auth/api-keys` -> generate new key
- `GET /api/auth/api-keys` -> list active keys
- `DELETE /api/auth/api-keys/{id}` -> revoke key
- API keys authenticate via `Authorization: Bearer <key>` header

### 3.3 Deployment Infrastructure (16 hrs)

**3.3.1 Docker containerization (6 hrs)**

`Dockerfile`:
```dockerfile
FROM python:3.12-slim
# Note: 3.12 not 3.14 for production stability
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY api/ api/
COPY config.py .
EXPOSE 8001
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

`docker-compose.yml`:
```yaml
services:
  api:
    build: .
    ports:
      - "8001:8001"
    environment:
      - DB_HOST=db
      - DB_PASSWORD=${DB_PASSWORD}
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:17
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql/schema:/docker-entrypoint-initdb.d
    environment:
      - POSTGRES_DB=olms_multiyear
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certbot:/etc/letsencrypt

volumes:
  pgdata:
```

**3.3.2 Database migration strategy (3 hrs)**
- The database is 33GB with 90+ tables. Options:
  - **Option A: pg_dump/pg_restore** -- dump from laptop, restore to server. One-time, ~30 min.
  - **Option B: Schema-only + ETL replay** -- deploy schema, re-run all ETL scripts. Validates reproducibility but takes hours.
  - **Recommendation:** Option A for initial deployment, Option B as a documented disaster recovery procedure.
- Create `scripts/migration/export_database.sh` and `import_database.sh`

**3.3.3 Hosting selection (2 hrs)**

| Provider | Cost/month | Managed DB | Ease | Recommendation |
|---|---|---|---|---|
| Railway | $20-50 | Yes (Postgres) | Very easy | Best for MVP |
| Render | $25-65 | Yes (Postgres) | Easy | Good alternative |
| DigitalOcean | $30-70 | Yes (Managed DB) | Medium | More control |
| AWS (ECS+RDS) | $50-150 | Yes (RDS) | Complex | For scale |
| Fly.io | $15-40 | Yes (Postgres) | Easy | Cheapest option |

**Key constraint:** 33GB database. Most managed Postgres services charge per GB. At $0.10/GB, that's $3.30/month for storage alone -- not the bottleneck. The bottleneck is RAM: 33GB database needs at least 4GB RAM for reasonable query performance.

**Recommendation:** Railway or Render for v1. Migrate to AWS/DO if user count exceeds 50.

**3.3.4 CI/CD pipeline (3 hrs)**
```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_DB: test_db
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: railway up  # or render deploy, etc.
```

**3.3.5 Domain and HTTPS (2 hrs)**
- Register domain (e.g., `laborresearch.org`, `organizertool.org`)
- Configure DNS to point to hosting provider
- Enable HTTPS via Let's Encrypt (automatic on Railway/Render)
- Redirect HTTP -> HTTPS

### 3.4 Data Freshness Pipeline (12 hrs)

**3.4.1 ETL orchestrator (6 hrs)**

Create `scripts/etl/orchestrate.py` -- a simple DAG runner:

```python
PIPELINE = [
    # Stage 1: Extract (can run in parallel)
    {"name": "fetch_olms", "script": "etl/fetch_olms.py", "schedule": "annual", "deps": []},
    {"name": "fetch_osha", "script": "etl/extract_osha.py", "schedule": "quarterly", "deps": []},
    {"name": "fetch_whd", "script": "etl/load_whd_national.py", "schedule": "quarterly", "deps": []},
    {"name": "fetch_nlrb", "script": "etl/fetch_nlrb.py", "schedule": "monthly", "deps": []},
    {"name": "fetch_qcew", "script": "etl/fetch_qcew.py", "schedule": "annual", "deps": []},
    {"name": "fetch_usaspending", "script": "etl/fetch_usaspending.py", "schedule": "annual", "deps": []},

    # Stage 2: Match (sequential, depends on Stage 1)
    {"name": "match_osha", "script": "scoring/match_osha.py", "deps": ["fetch_osha"]},
    {"name": "match_whd", "script": "scoring/match_whd_to_employers.py", "deps": ["fetch_whd"]},
    {"name": "match_usaspending", "script": "etl/_match_usaspending.py", "deps": ["fetch_usaspending"]},
    {"name": "splink_run", "script": "matching/splink_pipeline.py", "deps": ["fetch_olms"]},

    # Stage 3: Consolidate
    {"name": "merge_dupes", "script": "cleanup/merge_f7_enhanced.py", "deps": ["splink_run"]},
    {"name": "rescore", "script": "scoring/update_whd_scores.py", "deps": ["match_whd", "match_osha"]},

    # Stage 4: Validate
    {"name": "validate", "script": "validation/run_all_checks.py", "deps": ["rescore", "merge_dupes"]},
    {"name": "refresh_views", "script": "maintenance/refresh_materialized_views.py", "deps": ["validate"]},
]
```

Each step logs start/end time, row counts, errors. Failed steps don't cascade.

**3.4.2 Parameterize ETL scripts (4 hrs)**
- Replace hardcoded file paths with CLI arguments or environment variables:
  ```python
  # Before:
  CSV_PATH = r"C:\Users\jakew\Downloads\labor-data-project\whd_whisard_20260116.csv"

  # After:
  CSV_PATH = os.getenv('WHD_CSV_PATH') or sys.argv[1]
  ```
- Add `--dry-run` flag to each script (show what would change without writing)

**3.4.3 Scheduling (2 hrs)**
- GitHub Actions scheduled workflow for monthly NLRB fetch
- Quarterly reminder (GitHub issue auto-created) for OSHA/WHD manual downloads
- Document the full update procedure in `docs/DATA_UPDATE_GUIDE.md`

**Phase 3 Deliverable:** The platform is accessible at a URL with HTTPS. Multiple users can log in with role-based permissions. The API is modular, paginated, and hardened against injection. Data update pipeline is documented and partially automated.

**Phase 3 Total: ~59 hrs**

---

## Phase 4: Build the Decision Interface (Weeks 10-15)

*Now that the engine is deployed, build the dashboard organizers will actually use.*

### 4.1 Frontend Architecture Decision (4 hrs)

The 476KB monolith must be replaced. Here's the full analysis:

| Option | Build Time | Maintenance | Performance | Learning Curve |
|---|---|---|---|---|
| **A: FastAPI + Jinja2 + HTMX** | 40 hrs | Low | Good | Low (Python-only) |
| **B: Next.js (React)** | 60 hrs | Medium | Excellent | High (new stack) |
| **C: Modularized HTML + ES modules** | 25 hrs | Medium | Okay | Low |
| **D: Svelte/SvelteKit** | 45 hrs | Low | Excellent | Medium |

**Recommendation: Option A (HTMX + Jinja2)** for these reasons:
1. Zero new languages -- it's all Python
2. Server-rendered pages are fast, SEO-friendly, and accessible
3. HTMX handles interactivity (search, filtering, pagination) without a JS framework
4. No build step, no node_modules, no webpack/vite configuration
5. FastAPI already supports Jinja2 templates natively
6. The existing 142 API endpoints become the data layer; templates become the view layer

### 4.2 Territory Dashboard (14 hrs)

The primary landing page after login.

**4.2.1 Union-first entry point (3 hrs)**
- "Who are you?" selector: union affiliation dropdown
- Auto-populates territory: states/regions where this union has locals
- Saves preference in user profile

**4.2.2 Territory overview panel (4 hrs)**
- Key metrics at a glance:
  - Total employers in territory (organized vs non-organized)
  - Workforce coverage: organized members / total workforce
  - Trend arrows: membership up/down vs prior year
  - Active NLRB elections in territory
- Powered by existing endpoints: `/api/summary`, `/api/density/by-state`

**4.2.3 Top targets list (3 hrs)**
- Table: employer name, city, state, industry, score, tier, comparables count
- Sortable by any column
- Click to expand: quick preview of why this employer scored high
- Powered by: `/api/employers/search` + scorecard data

**4.2.4 Territory map (4 hrs)**
- Leaflet.js map (already working in v5, needs extraction)
- Layers: organized employers (green), non-organized targets (yellow/red by score)
- Cluster markers for dense areas
- Click marker -> employer summary popup
- Powered by: geocoded employer data + `/api/density/by-county`

### 4.3 Employer Deep-Dive Profile (12 hrs)

Single page per employer with all available intelligence consolidated.

**4.3.1 Header section (2 hrs)**
- Employer name, address, NAICS industry, employee count
- Score badge (TOP/HIGH/MEDIUM/LOW with color)
- Union status: currently organized (which union, since when) or non-union
- Corporate parent (if known, with link to GLEIF hierarchy)

**4.3.2 Score breakdown (2 hrs)**
- Visual: 8-bar chart showing each factor's contribution
- Explanation text for each factor: "This employer scored 8/10 on industry density because 24% of workers in NAICS 722 (Food Services) are unionized nationally"
- If comparables exist: "5 similar employers are unionized" with links

**4.3.3 Violations tab (3 hrs)**
- OSHA: timeline of inspections, violation count/severity, penalties
- WHD: wage theft cases, backwages owed, civil penalties
- NYC-specific: local labor law violations, debarment status
- All linked to original case IDs for verification

**4.3.4 NLRB history tab (2 hrs)**
- Elections at this employer (won/lost, vote counts, dates)
- ULP cases filed (open/closed, allegations)
- Voluntary recognition events
- Timeline visualization

**4.3.5 Corporate structure tab (2 hrs)**
- Parent company (from GLEIF/crosswalk)
- Subsidiaries (if any)
- Federal contractor status and obligation amounts
- SEC filing info (if public company)
- IRS 990 data (if nonprofit: revenue, employees, executive comp)

**4.3.6 Comparables sidebar (1 hr)**
- 5 most similar unionized employers
- For each: name, location, industry, what union represents them, similarity score
- "Why similar?" explanation

### 4.4 Search and Filtering (6 hrs)

**4.4.1 Unified search bar (2 hrs)**
- Single search that queries employers, unions, and NLRB cases
- Auto-suggest as you type (HTMX partial update)
- Results grouped by type with clear headers

**4.4.2 Advanced filters panel (2 hrs)**
- State / metro area
- Industry (NAICS 2-digit)
- Score tier (TOP / HIGH / MEDIUM / LOW)
- Has violations (yes/no)
- Federal contractor (yes/no)
- Employee count range
- Currently organized (yes/no)

**4.4.3 Saved searches (2 hrs)**
- Save filter combinations as named searches
- Share searches between organizers in the same organization
- "My territory" as a default saved search

### 4.5 Export and Reporting (8 hrs)

**4.5.1 CSV export (2 hrs)**
- Export any search result or target list
- Include all available fields (not just displayed columns)
- Respect user's current filters

**4.5.2 PDF employer profile (3 hrs)**
- Printable single-page summary of an employer
- Include: score breakdown, violation summary, comparable employers, NLRB history
- Suitable for handing to an organizer before a site visit

**4.5.3 Territory summary report (3 hrs)**
- Board presentation format: PDF with charts
- Key metrics, top 10 targets, trend charts, map screenshot
- Configurable: "Generate report for SEIU in New York State"

### 4.6 Mobile Responsiveness (4 hrs)

Not a native app -- just make the web interface usable on phones/tablets:
- Responsive grid layout (Tailwind handles this)
- Collapsible sidebar navigation on mobile
- Touch-friendly map controls
- Employer profile readable on phone (stacked sections instead of tabs)

**Phase 4 Deliverable:** A union organizing director can log in, see their territory, find top targets with evidence-backed scores, drill into employer profiles with violation history, view comparables, and export a report for their board meeting -- in under 5 minutes.

**Phase 4 Total: ~48 hrs**

---

## Phase 5: Publication Readiness (Weeks 14-18)

*The final push from "works" to "publishable."*

### 5.1 Documentation for Users (8 hrs)

**5.1.1 User guide (4 hrs)**
- Getting started: logging in, setting up territory
- Searching and filtering employers
- Understanding the scorecard: what each factor means, how to interpret tiers
- Using comparables: "If this employer organized, here's what similar ones look like"
- Exporting data for board reports
- Interpreting violation data (what OSHA/WHD numbers mean in practice)

**5.1.2 Data methodology page (2 hrs)**
- Public-facing version of `docs/METHODOLOGY_SUMMARY_v8.md`
- Written for a union research director, not a data engineer
- Key sections: where the data comes from, how it's matched, what the scorecard predicts, known limitations
- Data freshness dates for each source

**5.1.3 FAQ (2 hrs)**
- "Why is my employer's profile empty?" -- match rates explanation
- "How current is the data?" -- update schedule
- "Can I trust the score?" -- validation methodology link
- "Why is the OSHA data different from what I see on OSHA.gov?" -- scope and matching explanation
- "How do I report a data error?" -- feedback mechanism

### 5.2 Documentation for Developers (6 hrs)

**5.2.1 API documentation (2 hrs)**
- FastAPI auto-generates Swagger docs at `/docs`
- Add descriptions to all endpoints (many currently have none)
- Add response examples for key endpoints
- Document authentication requirements per endpoint

**5.2.2 Database schema diagram (2 hrs)**
- ERD diagram of core tables and relationships
- Tools: `pgAdmin` ERD tool, or `dbdiagram.io` for a shareable link
- Separate diagrams for: core union/employer tables, violation tables, matching/crosswalk tables, geographic tables

**5.2.3 Architecture overview and contribution guide (2 hrs)**
- System architecture diagram (update from As-Is to deployed state)
- How to add a new data source (ETL template)
- How to add a new API endpoint (router template)
- How to run tests locally
- Branch and PR conventions

### 5.3 Data Methodology Audit (10 hrs)

**5.3.1 External review (6 hrs)**
- Find 2-3 reviewers: labor economist, union researcher, data engineer
- Provide: methodology document, database access (read-only), scorecard validation results
- Ask them to:
  1. Verify the BLS reconciliation math
  2. Spot-check 20 employer profiles against public records
  3. Review the scorecard validation statistics
  4. Identify any methodological concerns

**5.3.2 Data source provenance documentation (4 hrs)**
Create `docs/DATA_SOURCES.md`:

| Source | URL | Date Acquired | Records | Match Method | Known Limitations | License |
|---|---|---|---|---|---|---|
| OLMS LM filings | `olms.dol.gov` | Jan 2026 | 2.6M+ | -- (source of truth) | >$300K/year reporting only | Public domain |
| OSHA IMIS | `osha.gov` | Jan 2026 | 2.2M | Establishment name+city+state | DBA names, abbreviations | Public domain |
| WHD WHISARD | `dol.gov/whd` | Jan 2026 | 363K | Legal name+state (2-tier) | Small business bias | Public domain |
| NLRB case data | `nlrb.gov` | Jan 2026 | 33K elections | Case number + entity match | Pre-2000 data sparse | Public domain |
| GLEIF/Open Ownership | `register.openownership.org` | Dec 2025 | 379K US | LEI, name+state | Foreign entities only with LEI | Open data |
| SEC EDGAR | `efts.sec.gov` | Dec 2025 | 517K | CIK, EIN, name+state | Public companies only | Public domain |
| USASpending | `usaspending.gov` | Nov 2025 | 47K | UEI, name+state | No EIN (tax-sensitive) | Public domain |
| QCEW | `data.bls.gov/cew` | Nov 2025 | 1.9M | NAICS+county (industry only) | Aggregated, no employer names | Public domain |
| Mergent Intellect | CUNY library | Nov 2025 | 56K | DUNS, name+city+state | NY-biased sample | Licensed |
| IRS 990 | AWS S3 | Oct 2025 | 587K | EIN, name+state | Nonprofits only | Public domain |
| BLS CPS | `bls.gov/cps` | Jan 2026 | Benchmark | Validation target | Survey (sampling error) | Public domain |
| EPI analysis | EPI publications | 2025 | 51 states | Validation target | Model-based estimates | Published research |

### 5.4 Performance and Stress Testing (8 hrs)

**5.4.1 Query performance audit (4 hrs)**
- Run `EXPLAIN ANALYZE` on the 20 slowest API queries
- Focus on: employer search, scorecard generation, density calculations, corporate hierarchy traversal
- Add missing indexes:
  ```sql
  -- Likely missing (verify with EXPLAIN):
  CREATE INDEX idx_f7_employers_naics ON f7_employers_deduped(naics);
  CREATE INDEX idx_f7_employers_state_city ON f7_employers_deduped(state, UPPER(city));
  CREATE INDEX idx_osha_est_state_city ON osha_establishments(state, UPPER(city));
  CREATE INDEX idx_whd_name_state ON whd_cases(name_normalized, state);
  CREATE INDEX idx_crosswalk_f7 ON corporate_identifier_crosswalk(f7_employer_id);
  ```
- Target: all API responses < 500ms at p95

**5.4.2 Load testing (2 hrs)**
- Use `locust` or `k6` to simulate concurrent users
- Scenarios:
  - 10 concurrent users searching employers
  - 5 concurrent users loading employer profiles
  - 2 concurrent users generating reports
- Target: API handles 50 concurrent users without degradation
- Connection pool sizing: verify 20 connections is sufficient

**5.4.3 Monitoring setup (2 hrs)**
- Health check endpoint: `GET /api/health` -- returns DB status, table counts, last ETL run
- Set up uptime monitoring (UptimeRobot, free tier)
- Error alerting: send notification on 5xx errors (Sentry free tier, or simple email)
- Dashboard: basic Grafana or just a `/api/admin/status` page

### 5.5 Soft Launch and Feedback (10 hrs)

**5.5.1 Recruit beta testers (2 hrs)**
- Identify 3-5 trusted union leaders/organizers
- Ideal mix: 1 national research director, 2 regional organizing directors, 2 local organizers
- Create accounts, provide brief training document

**5.5.2 Structured feedback collection (4 hrs)**
- Provide a feedback form (Google Form or built-in):
  1. "Did you find the employer you were looking for?" (yes/no)
  2. "Was the information useful for making an organizing decision?" (1-5)
  3. "Was anything confusing or unclear?" (text)
  4. "What information was missing?" (text)
  5. "Would you use this tool regularly?" (yes/no/maybe)
- Observe 2-3 users in a live session (screen share) -- watch where they get stuck

**5.5.3 Issue triage and fixes (4 hrs)**
- Categorize feedback: data accuracy, UX confusion, missing features, bugs
- Fix critical issues immediately
- Log non-critical issues as GitHub issues for future sprints
- Send follow-up to beta testers showing what changed based on their feedback

**Phase 5 Deliverable:** The platform is live, documented, performance-tested, and has been validated by real users with documented feedback.

**Phase 5 Total: ~42 hrs**

---

## Phase 6: Post-Launch Growth (Ongoing)

*These are enhancements that add value after the platform is live. Order by impact.*

### 6.1 Contract Expiration Tracking (Priority: HIGH)
- FMCS (Federal Mediation and Conciliation Service) maintains a database of collective bargaining agreements with expiration dates
- Knowing when a contract expires is the #1 timing signal for organizing: workers at non-union shops owned by companies with expiring contracts elsewhere are especially targetable
- Source: `fmcs.gov/services/collective-bargaining-mediation/f-7-notice-filings/`
- Estimated: 15 hrs

### 6.2 Real-Time NLRB Monitoring (Priority: HIGH)
- NLRB publishes new case filings daily
- Build a scraper that checks for new cases, matches to employers, sends alerts
- "New election petition filed at [employer] in [city]" -> notify organizers in that territory
- Estimated: 12 hrs

### 6.3 State PERB Data Integration (Priority: MEDIUM)
- Public Employment Relations Board data (varies by state)
- Fills the public sector gap: state/local government bargaining unit data
- Start with NY PERB (well-structured data), expand to CA, IL, NJ, OH
- Estimated: 20 hrs (5 per state)

### 6.4 Political Contribution Integration (Priority: MEDIUM)
- FEC data: PAC contributions, lobbying disclosures
- "This employer spent $500K lobbying against the PRO Act" is powerful intelligence
- Source: `fec.gov/data/` (bulk downloads, well-structured)
- Estimated: 15 hrs

### 6.5 Collective Bargaining Agreement Database (Priority: MEDIUM)
- DOL CBA database + FOIA requests for specific agreements
- Extract: wage rates, benefit levels, key contract terms
- Enable: "Here's what workers at similar employers negotiated"
- Estimated: 25 hrs

### 6.6 News & Media Monitoring (Priority: LOW)
- GDELT or NewsAPI for labor-related news
- Entity extraction: link articles to employers/unions in the database
- Sentiment analysis: positive/negative labor coverage
- "Breaking: Strike announced at [employer]" -> automatic alert
- Estimated: 20 hrs

### 6.7 Predictive Analytics (Priority: LOW)
- Time-series analysis of organizing trends
- Election outcome prediction model (using validated scorecard as foundation)
- Industry growth/decline identification for strategic planning
- Requires Phase 2.1 validation to be complete first
- Estimated: 30 hrs

---

## Summary Timeline

| Phase | Weeks | Hours | What You Get |
|---|---|---|---|
| **0: Stabilize** | 1-3 | 32 | Secure, reproducible, testable, connection-pooled |
| **1: Clean Data** | 3-5 | 28 | >90% geocoded, <1% missing NAICS, automated validation |
| **2: Scorecard** | 5-9 | 52 | Validated scoring, comparables, improved match rates |
| **3: Architecture** | 7-12 | 59 | Deployed, authenticated, modular API, auto-updating |
| **4: Interface** | 10-15 | 48 | Territory dashboard, employer profiles, export |
| **5: Publication** | 14-18 | 42 | Documented, tested, user-validated |
| **Total** | **~18 weeks** | **~261 hrs** | **Deployable for publication** |

At 15 hrs/week: **18 weeks** (4.5 months)
At 10 hrs/week: **26 weeks** (6.5 months)
At 20 hrs/week: **13 weeks** (3.3 months)

Phases overlap intentionally: 2/3 run in parallel (data work + architecture work), and 4/5 overlap (building interface while documenting).

### Critical Path

The longest sequential dependency chain determines the minimum calendar time:

```
Phase 0 (Security) -> Phase 2.1 (Scorecard Validation) -> Phase 3.2 (Auth)
    -> Phase 3.3 (Deploy) -> Phase 5.5 (Soft Launch)
```

Nothing else on the roadmap matters if the scorecard isn't validated (2.1) and the platform isn't deployed (3.3). These are the two load-bearing tasks.

---

## Current Data Inventory (February 2026)

### Core Data Tables

| Source | Table | Records | Matched to F7 | Match Rate | Status |
|---|---|---|---|---|---|
| OLMS Unions | `unions_master` | 26,665 | -- | -- | Complete |
| F7 Employers | `f7_employers_deduped` | 60,953 | -- | -- | Deduplicated |
| F7 Relations | `f7_union_employer_relations` | 150,386 | -- | -- | Complete |
| NLRB Elections | `nlrb_elections` | 33,096 | 31,649 | 95.7% | Complete |
| NLRB Participants | `nlrb_participants` | 1,906,542 | 1,824,558 | 95.7% | Complete |
| OSHA Establishments | `osha_establishments` | 1,007,217 | 79,981 | 7.9% | Needs improvement |
| OSHA Violations | `osha_violations_detail` | 2,245,020 | via estab. | -- | Complete |
| WHD Wage Theft | `whd_cases` | 363,365 | ~17,000 | ~4.8% | Needs improvement |
| Mergent Intellect | `mergent_employers` | 56,431 | ~3,400 | ~6.0% | NY-biased |
| GLEIF Entities | `gleif_us_entities` | 379,192 | ~3,300 | ~0.9% | Complete |
| GLEIF Ownership | `gleif_ownership_links` | 498,963 | via entities | -- | Complete |
| SEC Companies | `sec_companies` | 517,403 | ~2,000 | ~0.4% | Complete |
| USASpending | `federal_contract_recipients` | 47,193 | 9,305 | 19.7% | Complete |
| IRS 990 (National) | `national_990_filers` | 586,767 | 0 | 0.0% | NOT MATCHED |
| IRS 990 (NY) | `ny_990_filers` | 47,614 | partial | -- | Partially matched |
| QCEW | `qcew_annual` | 1,943,426 | 97.5% (ind.) | -- | Complete |
| Historical LM | `lm_data` | 2,600,000+ | -- | -- | 2010-2024 |

### Supporting Tables

| Source | Table | Records | Purpose |
|---|---|---|---|
| Public Sector Locals | `ps_union_locals` | 1,520 | State/local union locals |
| Public Sector Employers | `ps_employers` | 7,987 | Government employers |
| Public Sector BUs | `ps_bargaining_units` | 438 | Union-employer relationships |
| Corporate Crosswalk | `corporate_identifier_crosswalk` | 14,561 | Multi-source entity linking |
| Corporate Hierarchy | `corporate_hierarchy` | 125,120 | Parent-subsidiary chains |
| NYC Wage Theft (USDOL) | `nyc_wage_theft_usdol` | 431 | Federal DOL NYC cases |
| NYC Wage Theft (NYS) | `nyc_wage_theft_nys` | 3,281 | State DOL NYC cases |
| NYC Wage Theft (Litigation) | `nyc_wage_theft_litigation` | 54 | Court settlements |
| NYC ULP (Closed) | `nyc_ulp_closed` | 260 | NLRB closed cases |
| NYC ULP (Open) | `nyc_ulp_open` | 660 | NLRB open cases |
| NYC Local Labor Laws | `nyc_local_labor_laws` | 568 | PSSL, Fair Workweek |
| NYC Debarment | `nyc_debarment_list` | 210 | Debarred employers |
| NYC Prevailing Wage | `nyc_prevailing_wage` | 46 | Underpayment cases |
| NYC Discrimination | `nyc_discrimination` | 111 | Discrimination cases |
| NY State Contracts | `ny_state_contracts` | 51,500 | State contract awards |
| NYC Contracts | `nyc_contracts` | 49,767 | City contract awards |
| Employer Search MV | `mv_employer_search` | 120,169 | Unified search view |
| Industry Scores | `f7_industry_scores` | 121,433 | QCEW density scoring |
| Federal Scores | `f7_federal_scores` | 9,305 | Contractor scoring |
| Organizing Targets | `organizing_targets` | 5,428 | AFSCME NY targets |
| National 990 | `national_990_filers` | 586,767 | Nonprofit financials |
| BLS Industry Density | `bls_industry_density` | 12 | 2024 benchmarks |

### Platform Totals

| Metric | Value |
|---|---|
| Total database size | ~33GB |
| Total records across all tables | ~13.5M+ |
| Total Python scripts | 702 (440 active in scripts/) |
| Total SQL files | 102 |
| API endpoints | 142 |
| API code | 6,642 lines |
| Frontend code | 8,841 lines (476KB) |
| Documentation | 103 markdown files |
| Crosswalk coverage | 14,561 multi-source employer identities |
| BLS validation accuracy | 98.6% (1.4% variance) |
| State EPI validation | 50/51 within 15% |

---

## Complete Database Schema Reference

### Entity Relationship Overview

```
unions_master (26,665)
    |-- f_num (PK)
    |-- aff_abbr, union_name, members, sector
    |-- 1:M --> f7_union_employer_relations
    |-- 1:M --> lm_data (2.6M historical filings)
    |-- 1:1 --> union_hierarchy (level classification)

f7_employers_deduped (60,953)
    |-- employer_id (PK)
    |-- employer_name, city, state, naics, latest_unit_size
    |-- lat, lon (57.2% geocoded)
    |-- M:M --> unions via f7_union_employer_relations
    |-- 1:M --> osha_f7_matches --> osha_establishments
    |-- 1:1 --> corporate_identifier_crosswalk (14,561)
    |-- 1:M --> employer_comparables (TBD)
    |-- 1:M --> employer_review_flags

corporate_identifier_crosswalk (14,561)
    |-- f7_employer_id (FK)
    |-- gleif_lei, mergent_duns, sec_cik, ein
    |-- is_federal_contractor, federal_obligations
    |-- Links to: gleif_us_entities, mergent_employers, sec_companies

nlrb_elections (33,096)
    |-- case_number (PK)
    |-- employer_name, city, state
    |-- eligible_voters, votes_for, votes_against
    |-- union_won (BOOLEAN)
    |-- 1:M --> nlrb_participants
    |-- 1:M --> nlrb_tallies, nlrb_allegations

osha_establishments (1,007,217)
    |-- establishment_id (PK)
    |-- name, city, state, naics
    |-- 1:M --> osha_violations_detail (2.2M)
    |-- M:1 --> f7_employers via osha_f7_matches

whd_cases (363,365)
    |-- case_id (PK)
    |-- trade_name, legal_name, name_normalized
    |-- city, state, naics_code
    |-- total_violations, civil_penalties, backwages_amount
```

### Matching Tier Breakdown (corporate_identifier_crosswalk)

| Tier | Method | Matches | Confidence |
|---|---|---|---|
| 1 | EIN exact (SEC<->Mergent) | 1,127 | HIGH |
| 2 | LEI exact (SEC<->GLEIF) | 84 | HIGH |
| 3 | Name+State (cleanco normalized) | 3,009 | MEDIUM |
| 4 | Splink probabilistic (JW>=0.88) | 1,552 | MEDIUM |
| 5 | USASpending exact name+state | 1,994 | HIGH |
| 6 | USASpending fuzzy (pg_trgm>=0.55) | 6,795 | MEDIUM |
| **Total** | | **14,561** | |

### Key Views and Materialized Views

| View | Records | Purpose | Refresh Frequency |
|---|---|---|---|
| `v_union_members_deduplicated` | ~14,500 | Hierarchy-based dedup membership | On demand |
| `v_union_members_counted` | ~14,500 | Counted-only members | On demand |
| `v_state_epi_comparison` | 51 | State vs EPI benchmarks | After ETL |
| `v_union_name_lookup` | ~26,665 | Fuzzy union name search | On demand |
| `v_nlrb_union_win_rates` | varies | Election win rates by union | After NLRB ETL |
| `v_nlrb_employer_activity` | varies | Employer NLRB case history | After NLRB ETL |
| `mv_employer_search` | 120,169 | **Materialized** unified search | Must REFRESH |
| `mv_whd_employer_agg` | varies | **Materialized** WHD aggregation | After WHD ETL |

---

## Script Inventory & Pipeline Map

### Active Scripts by Category

| Category | Count | Key Scripts | Description |
|---|---|---|---|
| **etl** | 52 | `load_whd_national.py`, `load_gleif_bods.py`, `fetch_qcew.py`, `fetch_usaspending.py`, `extract_osha.py` | Data loading from external sources |
| **matching** | 30 | `splink_pipeline.py`, `splink_config.py`, `splink_integrate.py`, `f7_comprehensive_match.py` | Entity resolution across datasets |
| **scoring** | 9 | `update_whd_scores.py`, `match_whd_to_employers.py`, `match_whd_tier2.py`, `run_mergent_matching.py` | Organizing scorecard computation |
| **cleanup** | 34 | `merge_f7_enhanced.py`, `link_multi_location.py`, `fix_multi_employer.py` | Deduplication and data correction |
| **maintenance** | 95 | `refresh_materialized_views.py`, `test_api_endpoints.py`, `validate_schema.py` | Schema validation, view refresh, testing |
| **import** | 45 | `load_lm_multiyear.py`, `import_f7_crosswalk.py`, `load_ps_data.py` | Data ingestion from OLMS/F7 |
| **density** | 16 | `calculate_county_density.py`, `ny_tract_density.py` | Union density computation |
| **coverage** | 16 | `public_sector_reconciliation.py`, `federal_verification.py` | BLS/EPI benchmark validation |
| **analysis** | 33 | `analyze_coverage.py`, `analyze_deduplication.py` | Research and reporting |
| **verify** | 39 | `test_api.py`, `test_edge_cases.py`, `spot_check_*.py` | Quality assurance |
| **export** | 11 | `export_discovery.py`, `platform_summary.py` | Data export and reporting |
| **batch** | 9 | `run_batch_match.py`, `batch_comparison.py` | Large-scale processing |
| **research** | 8 | `teamsters_analysis.py`, `seiu_locals.py`, `afscme_ny.py` | Union-specific deep dives |
| **discovery** | 3 | `event_catalog.py`, `crosscheck.py` | New organizing opportunity identification |
| **archive** | 18 | (inactive) | Historical scripts preserved |

### Critical Execution Order (Full Refresh)

```
1. ETL Stage (parallelizable)
   fetch_olms.py
   extract_osha.py
   load_whd_national.py
   fetch_nlrb.py
   fetch_qcew.py
   fetch_usaspending.py

2. Matching Stage (sequential)
   splink_pipeline.py --scenario mergent_f7
   splink_pipeline.py --scenario gleif_f7
   splink_pipeline.py --scenario f7_self_dedup
   splink_integrate.py  (1:1 dedup + quality filter)
   match_whd_to_employers.py
   match_whd_tier2.py
   _match_usaspending.py

3. Consolidation Stage
   merge_f7_enhanced.py --source combined
   link_multi_location.py
   build_crosswalk.py (refresh)

4. Scoring Stage
   update_whd_scores.py
   _integrate_qcew.py (industry density)
   run_mergent_matching.py (full 7-step pipeline)

5. Validation Stage
   run_all_checks.py
   refresh_materialized_views.py

Total estimated runtime: 2-4 hours (mostly ETL downloads)
```

---

## Technical Debt Registry

| ID | Severity | Category | Description | Estimated Fix | Phase |
|---|---|---|---|---|---|
| TD-01 | CRITICAL | Security | 65+ SQL injection via f-string WHERE clauses | 6 hrs | 0.1 |
| TD-02 | CRITICAL | Security | Hardcoded DB password in 20+ files + git history | 3 hrs | 0.1/0.2 |
| TD-03 | CRITICAL | Security | Zero authentication on 142 endpoints | 15 hrs | 3.2 |
| TD-04 | HIGH | Security | Permissive CORS (`allow_origins=["*"]`) | 1 hr | 3.1 |
| TD-05 | HIGH | Architecture | 6,642-line monolith API file | 6 hrs | 3.1 |
| TD-06 | HIGH | Architecture | 476KB monolith frontend (8,841 lines) | 40 hrs | 4.x |
| TD-07 | HIGH | Reliability | No connection pooling (new conn per request) | 2 hrs | 0.4 |
| TD-08 | HIGH | Reliability | 11+ endpoints return unbounded result sets | 4 hrs | 3.1 |
| TD-09 | HIGH | Ops | No dependency management (no requirements.txt) | 3 hrs | 0.3 |
| TD-10 | HIGH | Ops | Project in Downloads folder | 1 hr | 0.2 |
| TD-11 | HIGH | Ops | No database backup strategy | 1 hr | 0.2 |
| TD-12 | MEDIUM | Data | IRS 990 national (586K records) unmatched | 4 hrs | 2.3 |
| TD-13 | MEDIUM | Data | OSHA match rate 7.9% (target >20%) | 6 hrs | 2.3 |
| TD-14 | MEDIUM | Data | WHD match rate 4.8% (target >12%) | 4 hrs | 2.3 |
| TD-15 | MEDIUM | Data | 43% employers missing geocodes | 6 hrs | 1.3 |
| TD-16 | MEDIUM | Data | ~8,000 employers missing NAICS codes | 4 hrs | 1.2 |
| TD-17 | MEDIUM | Data | Scorecard weights unvalidated against outcomes | 16 hrs | 2.1 |
| TD-18 | MEDIUM | Ops | ETL hardcoded to local Windows file paths | 4 hrs | 3.4 |
| TD-19 | MEDIUM | Ops | 440 scripts with no orchestration | 6 hrs | 3.4 |
| TD-20 | MEDIUM | Reliability | Silent exception swallowing in API | 2 hrs | 3.1 |
| TD-21 | MEDIUM | Reliability | No request logging or audit trail | 2 hrs | 3.1 |
| TD-22 | LOW | Quality | 15 test files, none using pytest properly | 5 hrs | 0.5 |
| TD-23 | LOW | Quality | No CI/CD pipeline | 3 hrs | 3.3 |
| TD-24 | LOW | Compat | Python 3.14-specific (not widely supported) | 1 hr | 0.3 |
| TD-25 | LOW | Ops | No rate limiting on API | 1 hr | 3.1 |

---

## Decision Log & Architectural Choices

### Decision 1: Frontend Technology

**Context:** The 476KB HTML monolith needs replacement.

**Options considered:**
| Option | Effort | Maintenance | Performance | Verdict |
|---|---|---|---|---|
| HTMX + Jinja2 | 40 hrs | Low | Good | RECOMMENDED |
| Next.js (React) | 60 hrs | Medium | Excellent | Too much new tech |
| Modularized HTML + ES modules | 25 hrs | Medium | Okay | Doesn't solve the root problem |
| SvelteKit | 45 hrs | Low | Excellent | Good but unnecessary complexity |

**Decision:** HTMX + Jinja2. Rationale: stays in the Python ecosystem, no build step, no JavaScript framework to learn, FastAPI has native Jinja2 support.

### Decision 2: Authentication Strategy

**Decision:** JWT (self-issued) for v1, add OAuth in v2.
**Rationale:** Simplest implementation, no external dependencies, works for the expected user count (<100).

### Decision 3: Hosting Provider

**Decision:** Railway or Render for v1.
**Rationale:** Managed Postgres, easy deployment, reasonable cost ($20-50/month), zero DevOps overhead.

### Decision 4: Python Version for Production

**Decision:** Target Python 3.12 for deployment (not 3.14).
**Rationale:** 3.14 is bleeding-edge with limited library support and `\s` escape warnings. 3.12 is stable, widely supported, and all dependencies are compatible.

### Decision 5: Database Migration

**Decision:** pg_dump/pg_restore for initial deployment, ETL replay as documented DR procedure.
**Rationale:** 33GB database takes ~30 min to dump/restore vs hours to replay all ETL from scratch.

### Decision 6: Scorecard Scale

**Decision:** If Phase 2.1 validates current weights, keep 0-62 scale. If rebuild needed, normalize to 0-100.
**Rationale:** 0-100 is more intuitive for non-technical users. "This employer scores 73/100" means more than "43/62."

---

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Scorecard validation fails (AUC < 0.55) | Medium | HIGH | Phase 2.1 includes rebuild path. Budget 4 extra hours. |
| R-02 | Database too large for affordable hosting | Low | HIGH | Consider read replicas, table partitioning, or archiving pre-2015 data |
| R-03 | Laptop failure before backup strategy | Medium | CRITICAL | Phase 0.2 is highest calendar priority. Do backup FIRST. |
| R-04 | Python 3.14 incompatibilities in production | Medium | MEDIUM | Target 3.12 for Docker, test all scripts on 3.12 |
| R-05 | Mergent data license restricts redistribution | Medium | MEDIUM | Check license terms before deploying Mergent-sourced fields |
| R-06 | IRS 990 matching yields < 1,000 results | Low | LOW | Still adds nonprofit revenue data for matched employers |
| R-07 | No organizers want to test it | Low | HIGH | Pre-recruit beta testers before Phase 5. Build relationships early. |
| R-08 | OSHA/WHD data freshness lapses | Medium | MEDIUM | Phase 3.4 pipeline with quarterly reminders |
| R-09 | Single-developer bus factor | HIGH | CRITICAL | Documentation (Phase 5.2), open-source contribution guide |
| R-10 | Scope creep from Phase 6 features | Medium | MEDIUM | Phase 6 is explicitly post-launch. Don't start until Phase 5 is done. |

---

## Appendix A: What I'd Cut / What I'd Never Cut

### Minimum Viable Deployment (Cut to ~180 hours / 12 weeks)

If you need a working deployment as fast as possible:

1. **Skip Phase 1.1** (remaining 234 complex duplicates) -- they're edge cases
2. **Reduce Phase 2.2** (comparables) -- implement post-launch as Phase 6 feature
3. **Skip Phase 3.1.1** (API split into modules) -- keep monolith, just fix security
4. **Use Option C for frontend** (modularize HTML, don't rebuild) -- 25 hrs saved
5. **Skip Phase 4.4** (mobile responsive) -- desktop-first is fine for v1
6. **Reduce Phase 4.5** (export) -- CSV only, no PDF reports
7. **Reduce Phase 5.1** (user docs) -- README is fine for soft launch
8. **Skip Phase 5.3** (external methodology audit) -- do post-launch

That gives you: deployed, authenticated, validated scorecard, basic dashboard, CSV export, at a URL your organizing directors can visit.

### What I'd Never Cut

- **Phase 0.1** (SQL injection + credential fixes) -- without this, a single attacker destroys everything
- **Phase 0.2** (backup) -- without this, a laptop failure destroys everything
- **Phase 2.1** (scorecard validation) -- without this, the platform's core feature is an unvalidated opinion
- **Phase 3.2** (authentication) -- no auth = no deployment
- **Phase 3.3** (deployment infrastructure) -- the whole point is getting off the laptop
- **Phase 5.5** (user feedback) -- building for organizers without talking to organizers is how tools die unused

---

## Appendix B: Cost Projections

### Monthly Hosting Costs (Post-Deployment)

| Component | Provider | Cost/month |
|---|---|---|
| API server (2 vCPU, 4GB RAM) | Railway/Render | $15-25 |
| PostgreSQL (33GB, 4GB RAM) | Managed Postgres | $15-50 |
| Domain name | Namecheap/Cloudflare | $1 |
| HTTPS certificate | Let's Encrypt | Free |
| Uptime monitoring | UptimeRobot | Free |
| Error tracking | Sentry (free tier) | Free |
| **Total** | | **$31-76/month** |

### One-Time Costs

| Item | Cost |
|---|---|
| Domain registration | $12/year |
| External methodology review (if paid) | $500-2,000 |
| Load testing tools | Free (locust/k6) |

### Scaling Costs (if user base grows)

| Users | Monthly Cost | Notes |
|---|---|---|
| 1-10 | $31-50 | Minimal tier |
| 10-50 | $50-100 | May need larger DB instance |
| 50-200 | $100-200 | Add read replica, CDN |
| 200+ | $200-500 | Consider AWS/DO, caching layer |

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| **F7** | OLMS Form LM-7 -- "Agreement and Activities Report" filed by unions listing employers they have contracts with |
| **OLMS** | Office of Labor-Management Standards (DOL division that collects union filings) |
| **LM** | Form LM-2/3/4 -- annual union financial disclosure filings |
| **BLS CPS** | Bureau of Labor Statistics Current Population Survey -- source of official union membership numbers |
| **EPI** | Economic Policy Institute -- publishes state-level union density estimates |
| **NLRB** | National Labor Relations Board -- administers union elections and unfair labor practice cases |
| **WHD** | Wage and Hour Division (DOL) -- enforces minimum wage, overtime, child labor laws |
| **OSHA** | Occupational Safety and Health Administration -- workplace safety inspections and violations |
| **GLEIF** | Global Legal Entity Identifier Foundation -- maintains LEI (Legal Entity Identifier) database |
| **QCEW** | Quarterly Census of Employment and Wages (BLS) -- establishment-level employment counts |
| **Splink** | Probabilistic record linkage library (uses DuckDB backend) |
| **pg_trgm** | PostgreSQL trigram extension for fuzzy text matching |
| **cleanco** | Python library for cleaning/normalizing company names (removes suffixes like Inc, LLC, GmbH) |
| **RapidFuzz** | Fast fuzzy string matching library (Jaro-Winkler, token_set_ratio, etc.) |
| **Gower Distance** | Similarity metric that handles mixed data types (categorical + numeric) |
| **AUC-ROC** | Area Under the Receiver Operating Characteristic curve -- measures predictive model quality (0.5 = random, 1.0 = perfect) |
| **NAICS** | North American Industry Classification System -- 2-6 digit industry codes |
| **UEI** | Unique Entity Identifier -- replaced DUNS in 2022 for federal contracting |
| **DUNS** | Dun & Bradstreet Universal Numbering System -- legacy business identifier |
| **LEI** | Legal Entity Identifier -- 20-character global company ID maintained by GLEIF |
| **CIK** | Central Index Key -- SEC's company identifier |
| **EIN** | Employer Identification Number -- IRS tax ID (9 digits) |
| **FMCS** | Federal Mediation and Conciliation Service -- mediates labor disputes, tracks CBA expirations |
| **PRO Act** | Protecting the Right to Organize Act -- proposed federal labor law reform |
| **RLA** | Railway Labor Act -- governs labor relations in railroad and airline industries |
| **ULP** | Unfair Labor Practice -- violation of workers' rights under NLRA |
| **VR** | Voluntary Recognition -- employer voluntarily recognizes union without NLRB election |
| **BU** | Bargaining Unit -- group of employees represented by a union for collective bargaining |

---

*This document supersedes ROADMAP_TO_DEPLOYMENT.md v1.0 (February 8, 2026) and LABOR_PLATFORM_ROADMAP_v12.md for deployment planning. The v12 roadmap remains valid for data/feature work within Phases 1-2.*

*Last updated: February 9, 2026*
