# Data Source Lessons (moved from MEMORY.md for brevity)

## SAM.gov
- **SAM public extract has NO EIN** — EIN/TIN is tax-sensitive, only in the restricted extract. Public has: UEI, CAGE, name, address, NAICS (6-digit!), entity structure.
- **SAM V2 format** — pipe-delimited, 142 fields per record, BOF/EOF header/footer. UTF-8 version preferred.
- **826,042 USA entities loaded** — `sam_entities` table. 739K active, 595K have NAICS, 737K have CAGE, 173K have DBA names.
- **Column mapping** — [0]=UEI, [3]=CAGE, [5]=Status(A/E), [11]=LegalName, [12]=DBA, [15-19]=Address, [21]=Country, [27]=EntityStructure, [32]=PrimaryNAICS, [34]=AllNAICS(tilde-delimited).
- **Tier A exact name: FIXED with UPPER(TRIM())** — v1 got 0 matches because F7 stores mixed-case `employer_name_aggressive`. v2 wraps both sides in `UPPER(TRIM())`.
- **similarity() function causes full cross-joins** — 826K x 7K per state = 558M comparisons. MUST use `%` operator (GIN-indexed) for candidate retrieval.
- **Every SAM entity IS a federal contractor** — being registered in SAM means they do business with the government.
- **Scripts** — `scripts/etl/load_sam.py`, `scripts/scoring/match_sam_to_employers.py`, `scripts/etl/check_sam_progress.py`.

## Splink
- **Splink 4.0.12 uses DuckDB** — no PostgreSQL backend needed. Load DataFrames, run in memory.
- **Name comparison level filter is critical** — without filtering by JW >= 0.88, geographic overlaps dominate.
- **Splink self-dedup (dedupe_only)** — `link_type="dedupe_only"` with `Linker([df], settings)`. 62K records produces 3.8M candidate pairs.
- **NEW_MATCH requires name_level >= 4** — level 3 (JW >= 0.80) allows city-name-prefix false positives.
- **1:1 dedup mandatory** — raw Splink returns many-to-many. Use ROW_NUMBER() OVER (PARTITION BY source_id).
- **EM blocking rules must differ from prediction blocking** — Splink can't estimate parameters for columns used in blocking.

## WHD
- **WHD national data** — `whd_cases` table: 363,365 rows. Columns: `case_id`, `trade_name`, `legal_name`, `name_normalized`, address fields, `naics_code`, `total_violations`, `civil_penalties`, `employees_violated`, `backwages_amount`, `employees_backwages`.
- **Scripts** — `scripts/etl/load_whd_national.py`, `scripts/scoring/match_whd_to_employers.py`, `scripts/scoring/match_whd_tier2.py`.

## QCEW + USASpending
- **QCEW is aggregated data** — industry x geography, NO employer names. Useful for density scoring only.
- **F7 NAICS is all 2-digit** — QCEW uses hyphenated ranges ("31-33", "44-45", "48-49").
- **USASpending has NO EIN** — tax-sensitive data. Only UEI. Bulk download API returns 403; use paginated search.

## Phase 5 Matching
- **f7_employer_id is TEXT, not INTEGER** — all match tables must use TEXT. Type mismatch causes silent INSERT failures.
- **pg_trgm 0.40 threshold is way too aggressive** — 0.55 is the safe floor for state-wide fuzzy.
- **Mergent bridge is NY-only** — only 1,226 bridge rows, all NY.
- **F7 universe (~61K) is the match rate ceiling** — OSHA has 1M estabs but only ~14% unionized. 13.7% approaches max.
- **strip_facility_markers() PL/pgSQL function** — removes facility suffixes. Created in osha_match_phase5.py.
- **990 matching added 10,688 new crosswalk rows** — crosswalk grew from ~14.5K to ~25K.

## Gower Similarity
- **mergent_employers uses `company_name`** — NOT `employer_name`.
- **BLS `bls_industry_projections` uses `matrix_code`** — NOT `industry_code`. Codes: `310000`, `31-330`, etc.
- **BLS LEFT JOIN can produce duplicates** — composite NAICS codes match multiple BLS rows.
- **Gower computation was fast** — 54K targets x 989 refs = 50M pairs in 1.1 minutes.
- **`employer_comparables` table** — 269,810 rows (53,962 targets x 5 each).

## NLRB Patterns
- **33,096 elections, 67.4% union win rate** — 99.1% have outcomes, excellent data quality.
- **Unit size strongly predicts wins** — 1-10 emp: 73.8%, 26-250: 63-65%, 1000+: 70.2%.
- **No NAICS on NLRB tables** — industry requires joining through matched employers (only 32.3% coverage).
- **ref_nlrb_industry_win_rates** — 24 rows. ref_nlrb_size_win_rates: 8 buckets.
- **nlrb_predicted_win_pct on mergent_employers** — 56,426 scored. Range: 69.5-85.3%.

## Web Scraper
- **Crawl4AI on Python 3.14/Windows** — install with `--no-deps` then manually install ~14 deps.
- **Shared sidebar/template content = massive false positives** — boilerplate frequency detection essential.
- **AI extraction >> heuristic regex** — Heuristic v2 found 5 employers, AI extraction found 160.
- **AFSCME is mostly public-sector** — 87/160 unmatched, overwhelmingly state/local/education.
- **Web scraper tables** — `web_union_profiles` (295), `web_union_employers` (160), `web_union_contracts` (120), `web_union_membership` (31), `web_union_news` (183), `scrape_jobs` (112).

## Phase 4 Frontend
- **organizer_v5.html** — ~9,500+ lines. 3 modes: territory, search, deepdive.
- **API response shapes** — Scorecard: `results[]`, WHD: `results[]`, Trends: `trends[]`, Elections: `elections[]`, Unions: `unions[]`.
- **escapeHtml() must escape single quotes** — `&#39;` for onclick handlers.
- **Chart.js cleanup** — must `.destroy()` before re-creating to prevent memory leaks.

## Quality Audit Lessons
- **API response shapes diverge from frontend assumptions** — most common: `data.summary` vs `data.osha_summary`.
- **Lookups return objects** — `{state, employer_count, ...}`, not plain strings.
- **NLRB detail uses `elections_summary`** — not `summary`. Boolean `union_won`, not string.
- **Duplicate HTML IDs break getElementById** — always check for ID uniqueness.
