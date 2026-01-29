# Session Summary: Union & Employer Matching Improvements
**Date:** January 26, 2026
**Database:** olms_multiyear (PostgreSQL)
**Dataset:** NLRB Voluntary Recognition records (1,681 records)

---

## Executive Summary

Significantly improved the match rates for linking NLRB voluntary recognition records to OLMS union and employer data:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Union Match Rate** | ~60% | **96.7%** | +36.7% |
| **Employer Match Rate** | 35.1% | **51.0%** | +15.9% |
| **Both Matched** | 34.1% | **49.4%** | +15.3% |
| **F7 Employers Deduplicated** | 71,077 | **63,118** | -11.2% |

---

## Files Modified

### Core Normalizer
- **`name_normalizer.py`** - Major enhancements (phonetic algorithms, order-independent matching, word normalization)

### Union Matching Scripts
- **`vr_union_match_4a.py`** - Affiliation-based matching (enhanced)
- **`vr_union_match_4b.py`** - Fuzzy matching (enhanced)
- **`vr_union_match_4c.py`** - Verification report (enhanced)

### Employer Matching Scripts
- **`vr_employer_match_3a.py`** - Exact matching (enhanced)
- **`vr_employer_match_3b.py`** - Fuzzy matching (enhanced)
- **`vr_employer_match_3c.py`** - Verification report (enhanced)

### Duplicate Detection & Merge Scripts (NEW)
- **`find_duplicate_employers.py`** - Detect duplicate employers using fuzzy matching
- **`merge_f7_duplicates.py`** - Merge F7 employer duplicates with audit logging

### Generated Reports
- `f7_internal_duplicates.csv` - 68,589 F7 duplicate pairs
- `vr_internal_duplicates.csv` - 79 VR duplicate pairs
- `vr_f7_potential_matches.csv` - 156 cross-table potential matches
- `employer_matches_for_review.csv` - Flagged matches for manual review

---

## Union Matching Improvements

### New Strategies Added

1. **Enhanced Local Number Extraction** (`extract_local_number`)
   - Added 15+ patterns: Local, District Council, Joint Council, Joint Board, Lodge, Division, Branch, Chapter, Unit, Region, Area, Assembly, Section, General Committee, System Board
   - Handles compound numbers: `1-A`, `1/2`, `123-B`
   - Specific patterns for Teamsters, SEIU, IBEW, CWA District, AFSCME Council, etc.
   - **Address filtering**: Automatically removes address blocks, phone numbers, ZIP codes, and contact info from malformed union name fields
   - Pattern extraction rate: 57% of VR records (appropriate since many are independent unions)

2. **Local Number Normalization** (`normalize_local_number`)
   - `001` → `1`, `1-A` → `1A` for consistent comparison

3. **Token-Based Similarity** (`token_similarity`)
   - Jaccard similarity on tokens, ignores word order
   - Handles reordered names like "Teamsters International Brotherhood"

4. **Affiliation Variant Mapping** (`AFFILIATION_MAPPINGS`)
   - 30+ affiliations mapped to all known variants
   - Example: `UNITE HERE` → `['UNITEHERE', 'HERE', 'UNITE-HERE', 'HEREIU', 'UNITE', 'HRE']`

5. **Expanded Abbreviations** (~40 new)
   - International variations: `intrnl`, `internatnl`, `intnl`
   - Trade-specific: `pipeftrs`, `ironwkrs`, `sheetmtl`, `boilermkrs`
   - Healthcare: `healthcr`, `hlthcre`, `nurs`

6. **Typo Corrections** (`UNION_TYPO_CORRECTIONS`)
   - 100+ common misspellings mapped to correct forms
   - Examples: `assocation` → `association`, `committe` → `committee`

7. **Expanded Keyword Patterns**
   - Increased from 8 to 50+ industry patterns
   - Categories: Healthcare, Education, Building trades, Public sector, Transportation, Manufacturing, Service/Retail, Entertainment

### Union Match Results by Method

| Method | Matches | Avg Confidence |
|--------|---------|----------------|
| affiliation_local_exact | 530 | 0.95 |
| affiliation_national | 326 | 0.70 |
| keyword_pattern | 219 | 0.55 |
| trigram_token_independent | 171 | 0.67 |
| local_number_lookup | 99 | 0.65 |
| affiliation_variant_match | 80 | 0.85 |
| affiliation_variant_local | 59 | 0.93 |
| affiliation_local_partial | 54 | 0.80 |
| affiliation_variant_local_partial | 41 | 0.78 |
| affiliation_fallback | 21 | 0.50 |
| affiliation_state | 20 | 0.60 |
| token_match | 3 | 0.59 |
| acronym_match | 2 | 0.60 |

### Union Match Rate by Affiliation
- **100% match rate** for: IBT, SEIU, UAW, UFCW, CWA, IBEW, IUPAT, OPEIU, SMART, USW, AFSCME, LIUNA, etc.
- **90.2% match rate** for INDEPENDENT unions (478 of 530)
- Only 56 records remain unmatched (3.3%)

---

## Employer Matching Improvements

### New Strategies Added

1. **Aggressive Normalization** (`normalize_employer_aggressive`)
   - Strips all legal suffixes
   - Expands all abbreviations
   - Normalizes variations (Saint/St, Mount/Mt, &/and)

2. **Token-Based Employer Matching** (`employer_token_similarity`)
   - Key word extraction and Jaccard similarity
   - Handles word order differences

3. **Enhanced Trigram Matching**
   - Process ALL unmatched (removed 500 record limit)
   - Dynamic threshold based on name length
   - Combined trigram + word_similarity + token scores

4. **Industry Pattern Matching**
   - Healthcare, Hospitality, Retail, Manufacturing, Transportation patterns

5. **Two-Word Prefix Matching**
   - Match first two substantive words + state

6. **Extended Abbreviation Dictionary**
   - Healthcare: `hosp`, `med`, `ctr`, `hlth`, `rehab`, `surg`, `pharm`
   - Hospitality: `htl`, `rst`, `restrnt`
   - Geographic: `mt`, `st`, `ft`, `n/e/s/w`
   - Business: `mgmt`, `mfg`, `dist`, `whse`, `admin`

### Employer Match Results by Method

| Method | Matches | Employees | Avg Token Sim |
|--------|---------|-----------|---------------|
| first_word_state | 184 | 11,103 | 0.30 |
| aggressive_norm_only | 159 | 1,302 | 0.95 |
| exact_name_only | 130 | 2,819 | 1.00 |
| trigram_token_nostate | 123 | 579 | 0.61 |
| exact_name_city_state | 64 | 7,233 | 1.00 |
| aggressive_norm_state | 52 | 2,634 | 0.93 |
| trigram_token_state | 50 | 6,566 | 0.51 |
| exact_name_state | 29 | 1,424 | 1.00 |

### Employer Match Rate by Year
| Year | Total | Matched | Rate |
|------|-------|---------|------|
| 2007 | 71 | 31 | 43.7% |
| 2008 | 475 | 150 | 31.6% |
| 2009 | 402 | 127 | 31.6% |
| 2020 | 31 | 19 | 61.3% |
| 2021 | 127 | 92 | 72.4% |
| 2022 | 209 | 135 | 64.6% |
| 2023 | 181 | 110 | 60.8% |
| 2024 | 183 | 127 | 69.4% |

**Note:** Recent years (2020-2024) have significantly higher match rates because these employers are more likely to already have F-7 filings.

---

## Duplicate Employer Detection & Deduplication

### Duplicate Detection Script
Created `find_duplicate_employers.py` to identify potential duplicate employers using fuzzy matching:

**Detection Methods:**
- PostgreSQL `pg_trgm` extension for trigram similarity
- Token-based similarity from `name_normalizer.py`
- GIN indexes for efficient similarity searches

**Results Found:**

| Category | Pairs Found | High Confidence (≥0.7) |
|----------|-------------|------------------------|
| F7 Internal Duplicates | 68,589 | 22,280 |
| VR Internal Duplicates | 79 | 58 |
| VR → F7 Cross-matches | 156 | 13 |

**Exports Generated:**
- `f7_internal_duplicates.csv` - 68,589 duplicate pairs
- `vr_internal_duplicates.csv` - 79 duplicate pairs
- `vr_f7_potential_matches.csv` - 156 cross-table matches

### F7 Employer Merge Operation
Created `merge_f7_duplicates.py` to merge duplicate F7 employers:

**Merge Criteria:**
- Similarity score ≥ 0.9
- Same state
- Keep record with larger `latest_unit_size` (or more relations if tied)

**Merge Results:**

| Metric | Value |
|--------|-------|
| Duplicate pairs (score ≥ 0.9) | 11,815 |
| Merge groups (connected components) | 6,158 |
| **Total merges performed** | **7,959** |
| f7_union_employer_relations updated | 7,943 |
| VR matched_employer_id updated | 91 |

**F7 Employer Count:**
- Before: 71,077
- After: **63,118** (-11.2%)

**Top Merges by Impact:**

| Kept Name | Deleted Name | F7 Relations Updated |
|-----------|--------------|---------------------|
| ABF Freight System, Incorporated | ABF FREIGHT SYSTEM, INC. | 68 |
| Hertz Corporation | The Hertz Corporation | 51 |
| ARAMARK UNIFORM SERVICES | Aramark Uniform Services | 31 |
| Paragon Systems, Inc | Paragon Systems, Inc. | 29 |
| Granite Construction | Granite Construction Company | 29 |

### Cross-Table Matches Applied
Applied 2 high-confidence (≥0.7, same state) matches from duplicate detection:

| VR Employer | F7 Employer | State | Score |
|-------------|-------------|-------|-------|
| PMY Construction | PMZ CONSTRUCTION | NY | 0.789 |
| Petrotechnologies | Petro Technologies | LA | 0.762 |

---

## Database Schema Changes

### New Tables
- **`f7_employer_merge_log`** - Audit log for employer merges
  - `merge_date`, `kept_id`, `deleted_id`, `kept_name`, `deleted_name`
  - `similarity_score`, `f7_union_employer_relations_updated`, `vr_records_updated`

### Added Columns
`nlrb_voluntary_recognition`:
- `employer_name_aggressive` (TEXT) - Aggressively normalized employer name
- `employer_match_needs_review` (BOOLEAN) - Flag for manual review
- `employer_review_status` (TEXT) - Review classification

`f7_employers_deduped`:
- `employer_name_aggressive` (TEXT) - Aggressively normalized employer name

### Added Indexes
- `idx_vr_emp_agg` on `nlrb_voluntary_recognition(employer_name_aggressive)`
- `idx_f7_emp_agg` on `f7_employers_deduped(employer_name_aggressive)`
- `idx_f7_emp_trgm` GIN index on `f7_employers_deduped(employer_name)` for trigram search
- `idx_f7_emp_agg_trgm` GIN index on `f7_employers_deduped(employer_name_aggressive)`
- `idx_vr_emp_trgm` GIN index on `nlrb_voluntary_recognition(employer_name_normalized)`

---

## Known Issues & Future Improvements

### Union Matching
1. **56 unmatched records** - Mostly unique local organizations (Joint Executive Boards, Orchestra associations)
2. Some keyword matches have low token similarity but are correct affiliations

### Employer Matching
1. **`first_word_state` method has false positives** (avg token sim: 0.30)
   - Example: "American Backflow" matched to "American Colloid"
   - 184 records flagged for manual review

2. **~824 unmatched employers** - Most are genuinely NEW to organizing:
   - Anchor Health Homecare Services (3,230 employees)
   - ASC Staffing (1,200 employees)
   - Ultium Cells (1,000 employees) - new EV battery plant

3. **NATCA employers (0% match)** - Federal air traffic controllers not in F-7 data

### F7 Deduplication
1. **~46,000 remaining duplicate pairs** with scores 0.5-0.9 - require manual review
2. Cross-state duplicates not merged (may be legitimate separate locations)

### Completed Enhancements ✓
- ✓ Phonetic matching (Soundex/Metaphone) implemented
- ✓ Order-independent union name matching
- ✓ F7 employer deduplication (7,959 merges)
- ✓ Audit logging for merges

### Potential Future Enhancements
- Add parent company / subsidiary matching
- Add address-based matching as secondary confirmation
- Consider ML-based entity resolution for remaining unmatched
- Merge F7 duplicates with scores 0.8-0.9 after manual review

---

## How to Run

```bash
# Union matching (run in order)
python vr_union_match_4a.py  # Affiliation-based matching
python vr_union_match_4b.py  # Fuzzy matching
python vr_union_match_4c.py  # Verification report

# Employer matching (run in order)
python vr_employer_match_3a.py  # Exact matching
python vr_employer_match_3b.py  # Fuzzy matching (takes ~10-15 min)
python vr_employer_match_3c.py  # Verification report

# Duplicate detection & merge
python find_duplicate_employers.py          # Generate duplicate reports
python merge_f7_duplicates.py               # DRY RUN - preview merges
python merge_f7_duplicates.py --apply       # APPLY - execute merges
```

---

## Key Functions Added to name_normalizer.py

```python
# Union functions
normalize_union(name, expand_abbrevs=True, fix_typos=True)
extract_local_number(union_name)
normalize_local_number(local_num)
token_similarity(name1, name2)
extract_key_tokens(union_name)
get_affiliation_variants(affil_code)
get_union_name_equivalents(name)
correct_union_name(name)

# Employer functions
normalize_employer(name, expand_abbrevs=True, remove_stopwords=False)
normalize_employer_aggressive(name)
employer_token_similarity(name1, name2)
extract_employer_key_words(name)
compute_employer_match_score(vr_name, f7_name, ...)

# Phonetic functions (NEW)
soundex(name)                    # Classic Soundex algorithm
metaphone(name)                  # Metaphone phonetic encoding
double_metaphone(name)           # Returns (primary, alternate) codes
phonetic_similarity(n1, n2)      # Combined phonetic similarity (0-1)
phonetic_match_score(n1, n2)     # Comprehensive match with details
find_phonetic_matches(target, candidates, threshold)  # Find similar names

# Order-independent matching (NEW)
extract_union_tokens(name)                  # Extract categorized tokens
union_token_match_score(name1, name2)       # Order-independent match score
find_best_union_match(target, candidates)   # Find best match from list
compare_union_names(name1, name2)           # Comprehensive comparison
normalize_union_word(word)                  # Normalize plurals (employees->employee)
get_key_identifiers_from_expansion(acronyms)      # Get identifiers from acronym
get_specific_identifiers_from_expansion(acronyms) # Get non-generic identifiers

# Data structures
UNION_TYPO_CORRECTIONS      # 100+ typo -> correction mappings
UNION_NAME_EQUIVALENTS      # Canonical name -> variations
AFFILIATION_MAPPINGS        # 30+ affiliation code variants
EMPLOYER_ABBREVIATIONS      # 100+ abbreviation expansions
EMPLOYER_NAME_VARIATIONS    # Common name variations
UNION_ACRONYM_EXPANSIONS    # Acronym -> word list (IBT, SEIU, LIUNA, etc.)
UNION_KEY_IDENTIFIERS       # Trade/industry-specific words
UNION_WORD_NORMALIZATIONS   # Plural -> singular mappings
GENERIC_IDENTIFIERS         # Generic words (worker, employee) for filtering
```

### Order-Independent Matching Examples

| Name 1 | Name 2 | Score | Result |
|--------|--------|-------|--------|
| SEIU Local 1000 | Service Employees International Union Local 1000 | 0.96 | MATCH |
| Laborers Local 79 | LIUNA Local 79 | 0.94 | MATCH |
| Teamsters Local 705 | Local 705 International Brotherhood of Teamsters | 1.00 | MATCH |
| UAW Local 100 | USW Local 100 | 0.00 | NO_MATCH (different unions) |
| IBEW Local 3 | Laborers Local 3 | 0.15 | NO_MATCH |

### Phonetic Algorithm Examples

| Name 1 | Name 2 | Soundex | Metaphone | Score |
|--------|--------|---------|-----------|-------|
| Smith | Smythe | MATCH [S530] | MATCH [SM0] | 1.0 |
| Teamsters | Temsters | MATCH [T523] | MATCH [TMSTRS] | 1.0 |
| Hospital | Hosptial | MATCH [H213] | MATCH | 0.93 |
| Association | Assocation | MATCH [A235] | MATCH [KMT] | 1.0 |
| American Hospital | Amerikan Hosptial | MATCH | - | 0.93 |

---

## Final Statistics

```
Total VR Records:           1,681
Union Matched:              1,625 (96.7%)
Employer Matched:             857 (51.0%)
Both Matched:                 830 (49.4%)
Total Employees Covered:   ~50,000

F7 Employers (deduplicated): 63,118 (was 71,077)
F7 Merge Log Entries:        7,959
```
