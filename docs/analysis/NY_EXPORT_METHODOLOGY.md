# NY Employer-Union CSV Export: Methodology Document

**File:** `export_ny_deduped.py`
**Output:** `ny_employers_deduped.csv`
**Last updated:** 2026-02-20
**Author:** Claude Code (Opus 4.6) with human direction

---

## 1. Purpose

Produce a deduplicated, one-row-per-real-employer CSV of all New York state employers with known union relationships. The export combines data from DOL Form LM-7 (F7) filings, manual public-sector research, NLRB election wins, and NLRB voluntary recognition cases.

The CSV is designed for analysis in Excel, with clear typing and sorting so that a researcher can quickly:
- See the largest public-sector bargaining units at the top
- Identify which rows represent real single employers vs. multi-employer agreements
- Filter by `employer_type` to isolate specific categories
- Use `location_count` and `locations` columns to understand geographic scope

---

## 2. Data Sources

### 2.1 F7 Employers (Primary)

**Table:** `f7_employers_deduped` (146,863 rows nationwide, 16,138 in NY)

The DOL Form LM-7 is filed by labor organizations to report their bargaining relationships. Each row in `f7_employers_deduped` represents a unique employer entity extracted from these filings. This is the only comprehensive registry of active union-employer relationships in the United States.

**Key columns used:**
- `employer_id` (TEXT, primary key) -- hash-based unique identifier
- `employer_name`, `city`, `state`, `zip` -- employer location
- `naics` -- industry code
- `latest_unit_size` -- number of workers in the bargaining unit
- `latest_notice_date` -- most recent F7 filing date referencing this employer
- `latest_union_name`, `latest_union_fnum` -- the union in the most recent filing
- `canonical_group_id` -- FK to `employer_canonical_groups.group_id` (NULL if ungrouped)
- `is_canonical_rep` -- boolean, TRUE if this employer is the representative of its group

**Joined tables:**
- `employer_canonical_groups` -- provides `canonical_name` for grouped employers
- `unions_master` -- provides `aff_abbr` (affiliation) and `sector` for the union
- `mv_employer_data_sources` -- provides cross-source flags (`has_osha`, `has_nlrb`, etc.), `ein`, `is_public`, `is_federal_contractor`

### 2.2 Manual Employers (Public Sector)

**Table:** `manual_employers` (53 in NY)

Hand-researched public-sector bargaining units not in the F7 system. F7 only covers private-sector employers, so major public-sector unions (NYSUT, CSEA, DC37, PEF, TWU, PBA, etc.) must be added manually.

**Key columns:** `employer_name`, `city`, `state`, `union_name`, `affiliation`, `num_employees`, `sector`, `recognition_date`

### 2.3 NLRB Election Wins (Unmatched)

**Table:** `nlrb_elections` + `nlrb_participants` (1,287 deduplicated employer-city combos in NY)

NLRB-supervised elections where the union won, but the employer was not matched to any F7 record. These represent organizing activity that may not yet appear in F7 filings (e.g., newly organized workplaces, first contracts in progress).

**Deduplication:** Grouped by `participant_name + city + state + zip`, with `MAX(eligible_voters)` as worker count and `STRING_AGG(DISTINCT union_name)` for unions involved.

### 2.4 NLRB Voluntary Recognition (Unmatched)

**Table:** `nlrb_voluntary_recognition` (32 in NY)

Employers that voluntarily recognized a union without an election, not matched to F7.

---

## 3. Deduplication Pipeline

The export runs a 7-step pipeline to produce the final CSV.

### Step 1: Pull all NY F7 employers

Single SQL query joins `f7_employers_deduped` with `employer_canonical_groups`, `unions_master`, and `mv_employer_data_sources`. Returns 16,138 rows for NY.

### Step 2: Separate multi-employer agreements

**Problem:** F7 filings include industry-wide and signatory agreements where the "employer" is actually a collective bargaining agreement covering many employers. Examples:
- "2016-2019 Commercials and/or Audio Commercials Code/SAG-AFTRA" (165,000 workers)
- "Joint Policy Committee" (160,000 workers)
- "Multiple Companies (List Available)" (159,999 workers)
- "2006 RAB Apartment Building Agreement" (30,000 workers)
- "AFTRA National Code of Fair Practice for Commercial Radio" (70,000 workers)

These inflate worker counts dramatically and don't represent single real employers.

**Detection method:** Regex pattern matching against employer name. Patterns include:
- Year + code/agreement/agt: `\b\d{4}\b.*\b(?:code|agreement|agt\.?)\b`
- Explicit multi-employer: `\bmultiple companies\b`, `\bindependent contractors\b`, `various`
- Industry agreements: `\bjoint policy\b`, `\bmaster agreement\b`, `\bgeneral agreement\b`
- Building trade agreements: `\bbuilding (?:agreement|agt\.?)\b`, `\brab\b.*\b(?:agreement|agt\.?)\b`
- Entertainment industry: `\bamptp\b`, `\btv code\b`, `\bnational code of fair practice\b`
- Collective indicators: `\band its members\b`, `@\s*multiple locations`

**Result:** 78 rows flagged as `MULTI_EMPLOYER_AGREEMENT`. These are kept in the CSV for reference but clearly typed so they can be filtered out of analyses.

**Known limitation:** Detection is name-based only. Some multi-employer agreements may use names that don't match these patterns. Conversely, a legitimate single employer named "Various Industries" would be incorrectly flagged (no such case exists in current data).

### Step 3: Collapse canonical groups

**Problem:** The same real-world employer often appears as multiple rows in F7 because each bargaining unit gets a separate filing. Starbucks has 20+ NY rows (one per unionized store), Corning has 3 NY rows (different facilities), Bob's Discount Furniture has 4.

**Solution:** The upstream `employer_canonical_groups` system (built by `scripts/matching/build_employer_groups.py`) has already identified 1,641 groups covering 3,642 NY employers. The export collapses each group into a single row.

**Collapse logic:**
- **Representative:** Use the member with `is_canonical_rep = TRUE`. If the representative is not in NY (cross-state groups like Starbucks), fall back to the NY member with the largest `latest_unit_size`.
- **Employer name:** Use `canonical_name` from the groups table (a normalized, clean name).
- **Workers:** SUM of `latest_unit_size` across all NY members. Each member represents a distinct bargaining unit with separate workers.
- **Union names:** Collected from all members, then deduplicated via normalization:
  - Strip "N/A" suffix
  - Strip "affiliated with..." / "a/w ..." clauses
  - Strip "/SEIU" and ", SEIU" suffixes
  - Strip "- Service Employees International..." suffixes
  - Group by normalized name, pick shortest original variant as representative
  - Example: 15 variants of "Workers United" collapse to one entry
- **Cities:** All distinct cities collected into `locations` column (pipe-separated). `location_count` = number of distinct cities.
- **Data source flags:** OR across all members (if any member `has_osha`, the group `has_osha`).
- **EIN:** First non-empty value across members.
- **Sector:** Majority vote across members.
- **Public/contractor flags:** OR (if any member is public or contractor, the group is).
- **Latest date:** MAX across members.
- **Time period:** Current if latest date >= 2020, else Historical.

**Result:** 3,642 individual employer rows -> 1,641 `CANONICAL_GROUP` rows.

### Step 4: Fuzzy dedup for large ungrouped employers

**Problem:** Some large employers (10K+ workers) may have slight name variations that weren't caught by the canonical grouping system. Example: "Verizon Companies" vs "Verizon Wireless" vs "Verizon, Inc."

**Method:** For ungrouped employers with `latest_unit_size >= 10,000` (5 in NY):
- Normalize employer names (strip ", Inc.", " Corporation", " LLC", etc.)
- Compare all pairs using `rapidfuzz.fuzz.token_sort_ratio`
- Threshold: >= 80 for clustering
- Collapse clusters using same logic as canonical groups

**Result in current data:** No additional collapses found. The 5 large ungrouped employers were all genuinely distinct entities.

**Why only 10K+:** Fuzzy matching at lower thresholds would produce many false positives. "ABC Corp" and "ABD Corp" are different companies. The canonical grouping system (which uses more signals than just name) is the right tool for smaller employers.

### Step 5: Small ungrouped employers as-is

The remaining 12,413 ungrouped employers with < 10K workers are emitted as individual `SINGLE_EMPLOYER` rows. Each gets `location_count = 1`.

### Step 6: Multi-employer agreement rows

The 78 multi-employer rows identified in Step 2 are emitted with `employer_type = 'MULTI_EMPLOYER_AGREEMENT'`. They keep their original worker counts (which represent covered workers under the agreement, not a single employer's workforce).

### Step 7: Manual employers, NLRB VR, NLRB elections

These are pulled from their respective tables and formatted as output rows with appropriate `employer_type` values (`PUBLIC_SECTOR`, `NLRB_VR`, `NLRB_ELECTION`).

---

## 4. Output Format

### CSV columns

| Column | Type | Description |
|--------|------|-------------|
| `employer_name` | text | Name of the employer (canonical name for groups) |
| `city` | text | City of the representative location |
| `state` | text | Always "NY" |
| `zip` | text | ZIP code of the representative location |
| `naics` | text | NAICS industry code (first non-empty in group) |
| `sector` | text | "Private" or "Public" (majority vote for groups) |
| `employer_type` | text | See below |
| `workers` | int | Number of workers (summed for groups) |
| `union_names` | text | Pipe-separated list of distinct unions |
| `union_count` | int | Number of distinct unions (after normalization) |
| `affiliation` | text | Union affiliation abbreviation (e.g., "SEIU", "UAW") |
| `latest_date` | date | Most recent filing/recognition date |
| `time_period` | text | "Current" (>=2020) or "Historical" (<2020) |
| `data_sources` | text | Comma-separated list of matched data sources |
| `source_count` | int | Number of cross-matched data sources |
| `location_count` | int | Number of distinct cities in group |
| `locations` | text | Pipe-separated list of cities (for groups) |
| `canonical_group_id` | int | ID of the canonical group (if applicable) |
| `ein` | text | Employer Identification Number (if known) |
| `is_public_company` | text | "Y" if publicly traded |
| `is_federal_contractor` | text | "Y" if federal contractor |
| `primary_source` | text | Source of the record (F7_OLMS, MANUAL, NLRB_ELECTION, NLRB_VR) |
| `employer_id` | text | Internal employer ID (hash, for F7 records) |

### employer_type values

| Type | Description | Count |
|------|-------------|-------|
| `PUBLIC_SECTOR` | Manual public-sector entries (NYSUT, CSEA, DC37, etc.) | 20 |
| `CANONICAL_GROUP` | Collapsed from canonical employer grouping | 1,641 |
| `SINGLE_EMPLOYER` | Ungrouped F7 employer, single location | 12,451 |
| `FUZZY_COLLAPSED` | Ungrouped 10K+ employers collapsed by name similarity | 0 (none found) |
| `MULTI_EMPLOYER_AGREEMENT` | Industry-wide / signatory agreements | 78 |
| `NLRB_ELECTION` | Unmatched NLRB election wins | 1,287 |
| `NLRB_VR` | Unmatched NLRB voluntary recognition | 32 |

### Sort order

The CSV is ordered in sections:
1. **PUBLIC_SECTOR** entries (sorted by workers DESC) -- at the very top
2. **F7 employers** (CANONICAL_GROUP + SINGLE_EMPLOYER + FUZZY_COLLAPSED, sorted by workers DESC)
3. **MULTI_EMPLOYER_AGREEMENT** (sorted by workers DESC)
4. **NLRB_ELECTION** (sorted by workers DESC)
5. **NLRB_VR** (sorted by workers DESC)

---

## 5. Problems Encountered and Fixed

### 5.1 Multi-employer agreement inflation (Critical)

**Problem:** SAG-AFTRA entertainment industry agreements appeared 6+ times in the v1 export, each claiming 160,000-165,000 workers. These represent the same pool of actors/performers covered under different agreement codes. Similarly, Realty Advisory Board (RAB) building trade agreements appeared multiple times at 20,000-30,000 workers each. These are industry-wide agreements covering many separate building owners, not single employers.

**Fix:** Regex-based detection flags these rows as `MULTI_EMPLOYER_AGREEMENT`. They are kept in the CSV for transparency but clearly marked so they don't inflate per-employer worker counts.

**Residual issue:** The worker counts on multi-employer agreements (e.g., 165,000 for Joint Policy Committee) represent "covered workers" under the agreement, which may overlap across agreements. There is no deduplication of workers across multi-employer agreements.

### 5.2 Same employer, multiple locations (High)

**Problem:** Starbucks had 20+ separate rows in NY (one per unionized store, 13-50 workers each). Corning had 3 rows (Corning, Canton, Oneonta). Bob's Discount Furniture had 4 rows.

**Fix:** Canonical group collapse. Starbucks becomes 1 row with 513 total workers, 19 locations. Workers are summed (each store has different workers). Union names are deduplicated.

**Residual issue:** 12,451 employers remain ungrouped. Some may be duplicates not caught by the canonical grouping algorithm.

### 5.3 Union name variant noise (Medium)

**Problem:** The same union appeared under 15+ name variants in Starbucks filings: "Workers United", "Workers United N/A", "WORKERS UNITED", "Workers United a/w SEIU", "Workers United/SEIU", "Workers United, affiliated with Service Employees International Union", etc.

**Fix:** `normalize_union()` function strips common suffixes (N/A, affiliated with, a/w, /SEIU, -SEIU) and normalizes to uppercase. `dedup_union_names()` groups by normalized name and picks the shortest original variant as representative. This collapses 15 variants to 1 "Workers United" entry.

### 5.4 RAB "Agt." abbreviation (Low)

**Problem:** Initial regex only matched "Agreement" but many RAB building trade filings use the abbreviation "Agt." (e.g., "2008 RAB Security Officers Owners Agt.", "2010 Long Island RAB Apartment Building Agt."). This caused 30 multi-employer agreements to be classified as single employers.

**Fix:** Added `agt\.?` as alternative to `agreement` in all relevant patterns. Also added `\band its members\b` (catches "Realty Advisory Board (RAB) and its members") and `\bsecurity officers owners\b` patterns.

### 5.5 Cross-state canonical group representatives (Low)

**Problem:** For cross-state groups like Starbucks, the canonical representative (`is_canonical_rep = TRUE`) is often in another state (e.g., Starbucks HQ in Washington). Using that representative's city/zip would be misleading for a NY export.

**Fix:** If the canonical representative is not in the NY subset, fall back to the NY member with the largest `latest_unit_size`.

### 5.6 File locking (Operational)

**Problem:** Writing to `ny_employers_deduped.csv` failed with `PermissionError` because the file was open in Excel. Excel locks CSV files exclusively on Windows.

**Fix:** Close the file in Excel before re-running. The script does not handle this automatically.

---

## 6. Known Remaining Issues

### 6.1 Ungrouped employer duplicates

**Severity:** Medium
**Scope:** Unknown (up to 12,451 rows affected)

77% of NY employers have no canonical group. The canonical grouping algorithm uses name similarity + geographic proximity + EIN matching, but its thresholds are tuned conservatively to avoid false positives. Some real duplicates slip through.

**Examples that may be duplicable:**
- "St John's Episcopal Hospital South Shore" and "St John's Episcopal Hospital South Shore (RN)" -- same hospital, different bargaining units
- Employer name typos ("Bayshore" vs "Bay Shore", "Mt Vernon" vs "Mount Vernon")
- Legal entity variants ("Employer, Inc." vs "Employer Corporation")

### 6.2 Verizon still fragmented

**Severity:** Low
**Scope:** 11 rows

The canonical group caught the main "Verizon Companies" entity (69,171 workers across 2 locations). But 9 other Verizon legal entities remain as separate rows: "Verizon - New England" (8,100), "Verizon, LLC" (189), and various smaller entities. Some may be genuinely separate subsidiaries; others may be duplicates.

### 6.3 No worker deduplication across multi-employer agreements

**Severity:** Medium
**Scope:** 78 rows

Different multi-employer agreements may cover overlapping worker pools. "Joint Policy Commitee, LLC" (165,000 workers) and "Joint Policy Committee" (160,000 workers) are likely the same agreement with a name typo across filing years. The 165,000 SAG-AFTRA workers appear under multiple agreement codes. Summing workers across multi-employer agreements would dramatically overcount.

### 6.4 Public sector completeness unknown

**Severity:** Medium
**Scope:** 20 entries

The 53 manual employers (20 marked public sector) were hand-researched but may be incomplete. Major units like NYSUT (467K), CSEA (250K), and DC37 (150K) are covered, but smaller municipal units, school district locals, and county-level bargaining units may be missing entirely.

### 6.5 NLRB election data quality

**Severity:** Low
**Scope:** 1,287 rows

NLRB election data uses `eligible_voters` as the worker count proxy, which may differ from actual bargaining unit size post-election. Some entries have NULL eligible voters. Employer names from NLRB filings are often informal or abbreviated.

### 6.6 Historical data mixed with current

**Severity:** Informational
**Scope:** 7,984 rows (51.5%)

Over half the rows have `time_period = 'Historical'` (latest filing before 2020). These employers had union relationships in the past but may no longer. The `time_period` column lets users filter to current-only if desired.

---

## 7. Possible Alternative Approaches and Enhancements

### 7.1 Lower fuzzy dedup threshold

**Current:** Only employers with >= 10,000 workers get fuzzy matching.
**Alternative:** Extend to 1,000+ or even all ungrouped employers.
**Trade-off:** Much higher false positive rate. "ABC Corp" and "ABD Corp" are different companies. Would require manual review of every proposed collapse, which is infeasible at scale.
**Recommendation:** Better to improve the upstream canonical grouping algorithm than to add more fuzzy logic in the export.

### 7.2 Address-based deduplication

**Current:** Dedup is name-based only.
**Alternative:** Match employers by physical address (street + city + zip). Two employers at the same address are likely the same entity or at least closely related.
**Trade-off:** F7 has address data but it's often incomplete or uses PO boxes. Multi-tenant buildings would create false positives. Hospital systems may have multiple bargaining units at the same address that are legitimately separate.
**Recommendation:** Good supplementary signal for the canonical grouping algorithm, not for the export script.

### 7.3 EIN-based deduplication

**Current:** EIN is included in output but not used for dedup.
**Alternative:** Employers sharing the same EIN are definitively the same legal entity. Could collapse by EIN.
**Trade-off:** Many F7 records have no EIN (it comes from cross-matching with 990/SEC/SAM, which covers ~38% of employers). Also, a single EIN can span legitimately different operating entities.
**Recommendation:** Add as a tier in the canonical grouping algorithm. Would catch some duplicates currently missed by name matching.

### 7.4 Filing-based temporal clustering

**Current:** Each F7 row is the latest filing for that employer.
**Alternative:** Group employers that appear in the same union's F7 filings across multiple years, even if the employer name varies slightly between filings.
**Trade-off:** Would require joining back to raw F7 data (not just the deduped table). Complex to implement. May catch name changes over time (e.g., "South Shore Hospital" -> "South Shore University Hospital").
**Recommendation:** Interesting for future work. Would catch temporal name changes that the current system misses.

### 7.5 Expanded canonical grouping

**Current:** Canonical grouping uses name normalization + geographic proximity.
**Alternative:** Run the grouping pipeline with more aggressive parameters (lower name similarity threshold, broader geographic radius) or add new signals (shared EIN, shared union, shared NAICS).
**Trade-off:** More false positives, but the pipeline already has human-review-friendly output. Better investment than patching the export.
**Recommendation:** Best approach for improving the export. Changes upstream propagate automatically.

### 7.6 Multi-employer agreement member enumeration

**Current:** Multi-employer agreements show total covered workers with no breakdown.
**Alternative:** For agreements like "Joint Policy Committee", identify the individual member employers. Some F7 filings list the members; others reference "Multiple Companies (List Available)".
**Trade-off:** Would require parsing free-text member lists or cross-referencing with other filings. Significant manual research effort.
**Recommendation:** High value but high effort. Would be the definitive fix for the SAG-AFTRA and RAB inflation problem.

### 7.7 Corporate hierarchy collapsing

**Current:** Subsidiaries are collapsed only if they're in the same canonical group.
**Alternative:** Use SEC EDGAR parent-subsidiary data, GLEIF ownership links, or Mergent corporate family data to collapse all subsidiaries of the same parent into one row.
**Trade-off:** Would reduce Verizon from 11 rows to 1-2 rows. But different subsidiaries may have very different labor relations profiles. Combining "Verizon Wireless" (largely non-union) with "Verizon Companies" (heavily unionized landline division) would be misleading.
**Recommendation:** Offer as an optional `--collapse-corporate` flag rather than default behavior. Users may want either view.

### 7.8 Probabilistic entity resolution

**Current:** Dedup uses deterministic rules (canonical groups, regex patterns, fuzzy thresholds).
**Alternative:** Use a probabilistic model (Splink, dedupe library, or custom) trained on known-duplicate pairs to score all employer pairs and collapse above a confidence threshold.
**Trade-off:** Most sophisticated approach. Requires labeled training data (known duplicates and known non-duplicates). The Splink model already exists for cross-source matching and could potentially be adapted for within-F7 dedup.
**Recommendation:** Future work. Would require a dedicated effort to label training pairs and tune the model for within-source dedup (different from cross-source matching).

### 7.9 NAICS-based worker estimation

**Current:** Worker counts come directly from F7 `latest_unit_size`.
**Alternative:** For employers with no worker count, estimate using NAICS industry averages from BLS QCEW data (already in the database).
**Trade-off:** Estimates would be rough (industry average, not employer-specific). Could mislead if presented as actual counts.
**Recommendation:** Add as a separate `estimated_workers` column rather than overwriting the `workers` column. Flag with a data quality indicator.

### 7.10 Geographic normalization

**Current:** City names are taken as-is from F7 data.
**Alternative:** Normalize city names to canonical forms (e.g., "NYC" -> "New York", "Mt Vernon" -> "Mount Vernon", "Bklyn" -> "Brooklyn"). Use USPS address standardization.
**Trade-off:** Would improve `location_count` accuracy for canonical groups (currently "New York" and "NYC" count as 2 locations). Moderate implementation effort.
**Recommendation:** Good quality-of-life improvement. Could be added to the `locations` column logic without changing the overall architecture.

---

## 8. Verification Checklist

After running the export, verify in Excel:

- [ ] Public sector employers (NYSUT, CSEA, DC37, PEF, TWU) are in the first 20 rows
- [ ] Filter `employer_type = 'CANONICAL_GROUP'` -- Starbucks should appear once with ~500 workers and 19+ locations
- [ ] Filter `employer_type = 'MULTI_EMPLOYER_AGREEMENT'` -- SAG-AFTRA/Joint Policy/RAB agreements should be here, not in SINGLE_EMPLOYER
- [ ] Sort by `workers` DESC -- the largest single employers should be Amazon (8,000), Home Health Aides (6,700), NYU (4,000)
- [ ] Filter `employer_type = 'NLRB_ELECTION'` -- 1,287 rows, all with `primary_source = 'NLRB_ELECTION'`
- [ ] Spot-check `union_names` column for CANONICAL_GROUP rows -- should show pipe-separated, deduplicated union names
- [ ] Spot-check `locations` column for CANONICAL_GROUP rows -- should show pipe-separated city names
- [ ] No rows should have `employer_type` = NULL or empty

---

## 9. Dependencies

**Python packages:**
- `psycopg2` -- PostgreSQL driver
- `rapidfuzz` -- fuzzy string matching (optional; script degrades gracefully without it)
- `csv`, `re`, `collections` -- standard library

**Database tables/views:**
- `f7_employers_deduped` -- primary employer table
- `employer_canonical_groups` -- grouping metadata
- `unions_master` -- union affiliation and sector
- `mv_employer_data_sources` -- cross-source flags, EIN, public/contractor status
- `manual_employers` -- hand-researched public sector entries
- `nlrb_elections` + `nlrb_participants` -- NLRB election data
- `nlrb_voluntary_recognition` -- NLRB VR data

**Upstream pipeline steps (must be current):**
1. F7 ETL (`scripts/etl/load_f7_*.py`)
2. Matching pipeline (`scripts/matching/run_deterministic.py all`)
3. Canonical grouping (`scripts/matching/build_employer_groups.py`)
4. Employer data sources MV (`scripts/scoring/build_employer_data_sources.py --refresh`)
