# Session Summary: 2026-02-20c — NY Employer CSV Export v2 (Collapsed Dedup)

**Agent:** Claude Code (Opus 4.6)
**Date:** 2026-02-20
**Duration:** ~30 min

## What was done

Rewrote `export_ny_deduped.py` to produce a collapsed, one-row-per-real-employer CSV export for New York state. The previous version (v1) had 18,482 rows with major duplication from signatory/multi-employer agreements, same employer across multiple locations, same employer with different unions, and name/city typos.

### Changes made

**File modified:** `export_ny_deduped.py` (full rewrite)

### Deduplication strategy (5 steps)

1. **Canonical group collapse:** 1,641 canonical groups covering 3,642 employers collapsed into 1,641 rows. Workers summed across group members. Union names deduplicated via normalization (stripping "N/A", "affiliated with...", "/SEIU", etc.). Distinct cities collected into `locations` column.

2. **Multi-employer agreement detection:** 78 rows flagged as `MULTI_EMPLOYER_AGREEMENT` using regex pattern matching on employer names (year+code/agreement patterns, "Multiple Companies", "Joint Policy", "AMPTP", RAB agreements, "and its members", etc.). These are kept in the CSV but clearly typed so they can be filtered.

3. **Fuzzy dedup for large ungrouped employers (10K+):** 5 employers checked via `rapidfuzz.fuzz.token_sort_ratio >= 80`. No additional collapses found (the large employers were already distinct entities).

4. **Public sector at top:** 20 public-sector manual employers (NYSUT 467K, CSEA 250K, DC37 150K, etc.) placed at top of CSV with `employer_type = 'PUBLIC_SECTOR'`.

5. **Unmatched NLRB appended:** 1,287 unmatched election wins + 32 unmatched VR cases at the end.

### Results

| Metric | v1 | v2 | Change |
|--------|----|----|--------|
| Total rows | 18,482 | 15,509 | -16% |
| Starbucks rows | 20+ | 3 | Collapsed to 1 canonical group (513 workers, 19 locations) + 2 standalone variants |
| SAG-AFTRA rows | 6+ | 2 | 1 real office (27 workers) + 1 multi-employer agreement (165K) |
| Verizon rows | ~15 | 11 | Main group collapsed (69K workers, 2 locations) |
| Multi-employer flagged | 0 | 78 | Previously mixed in with real employers |
| Public sector at top | No | Yes | 20 entries prominently placed |

### Output columns (new)
`employer_name, city, state, zip, naics, sector, employer_type, workers, union_names, union_count, affiliation, latest_date, time_period, data_sources, source_count, location_count, locations, canonical_group_id, ein, is_public_company, is_federal_contractor, primary_source, employer_id`

### employer_type breakdown
| Type | Count |
|------|-------|
| SINGLE_EMPLOYER | 12,451 |
| CANONICAL_GROUP | 1,641 |
| NLRB_ELECTION | 1,287 |
| MULTI_EMPLOYER_AGREEMENT | 78 |
| NLRB_VR | 32 |
| PUBLIC_SECTOR | 20 |

## Problems encountered and fixed

1. **PermissionError on output file:** Old CSV was open in Excel, locking the file. Worked around by writing to `_v2.csv` temporarily, then re-ran after user closed the file.

2. **RAB "Agt." abbreviation not caught:** Initial multi-employer regex only matched "Agreement" but many RAB filings use "Agt." abbreviation. Added `agt\.?` as alternative in all relevant patterns, plus `\band its members\b` and `\bsecurity officers owners\b` patterns. Caught 30 additional multi-employer rows (48 -> 78).

3. **Union name variant noise:** Starbucks had 15+ union name variants for the same union ("Workers United", "Workers United N/A", "WORKERS UNITED", "Workers United a/w SEIU", etc.). Added `normalize_union()` + `dedup_union_names()` that strips common suffixes and picks the shortest representative name per normalized group.

4. **Canonical group representative out-of-state:** For cross-state groups like Starbucks, the canonical representative may not be in NY. The script falls back to the NY member with the largest unit_size.

## Problems remaining

1. **12,451 ungrouped single employers:** 77% of NY employers have no canonical group. Many of these are genuinely unique, but some may be duplicates not yet caught by the grouping system.

2. **Verizon still has 11 rows:** The canonical group caught the main "Verizon Companies" (69K across 2 locations), but 9 other Verizon legal entities remain separate (Verizon - New England, Verizon LLC, Verizon Connect, etc.). Some may be genuinely different entities; others could potentially be grouped.

3. **RAB substring false positives in spot check:** The spot check for "RAB" matches 31 rows because it does substring matching. Names like "North Strabane Rehab" or "Tryax Realty" contain "rab" as a substring. The multi-employer regex correctly uses word boundaries (`\brab\b`) so these are NOT incorrectly flagged -- the spot check display is just misleading.

4. **Siren Retail / Starbucks Reserve Roastery not grouped:** "Siren Retail Corporation d/b/a Starbucks Reserve Roastery" is a separate legal entity not in the Starbucks canonical group. This is a data quality issue in the upstream grouping, not in this export.

5. **Joint Policy Committee appears twice:** "Joint Policy Commitee, LLC" (typo) and "Joint Policy Committee" are separate multi-employer filings. Could be collapsed but they represent different filing periods.

6. **South Shore has 14 rows:** Multiple hospitals with "South Shore" in the name (South Shore University Hospital, St John's Episcopal Hospital South Shore, etc.) -- some are legitimately different institutions, some may be the same hospital with different union contracts.

7. **No fuzzy dedup for small employers:** Only employers with 10K+ workers get fuzzy matching. Smaller employers with typos (e.g., "Bayshore" vs "Bay Shore") remain duplicated.

## Possible alternative approaches

1. **Fuzzy dedup threshold lower than 10K:** Extend fuzzy matching to 1K+ or even all ungrouped employers. Risk: false positives increase significantly (e.g., "ABC Corp" matching "ABD Corp"). Would need manual review.

2. **Address-based dedup:** Match employers by physical address (street + city + zip) to catch same-location variants. F7 has address data that could be used.

3. **EIN-based dedup:** Employers with matching EINs are definitely the same entity. However, many F7 records have no EIN. Could be used as a supplementary signal.

4. **Union-filing-based clustering:** Group employers that appear in the same union's F7 filing across years, since the same employer may have slightly different names in different filing years.

5. **Expanded canonical grouping:** Run the canonical grouping pipeline with lower thresholds or more aggressive name normalization to catch more groups upstream, rather than fixing it in the export.

6. **Multi-employer agreement worker counting:** Instead of showing the full 165K for "Joint Policy Committee", estimate actual unique workers by cross-referencing the member employers listed in the agreement. This data may exist in the F7 filings.

7. **Hierarchical collapsing:** For conglomerates like Verizon, use corporate hierarchy data (SEC, GLEIF) to collapse subsidiaries under the parent entity, with a worker count that sums all subsidiaries.
