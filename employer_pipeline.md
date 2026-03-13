# Employer Pipeline: Full Lifecycle Reference

## Stage 1: Ingestion

**Primary source:** F-7 filings (DOL filings when union files for representation)
**Scripts:** `scripts/import/load_f7_data.py`, `scripts/import/load_f7_crosswalk.py`
**Source:** SQLite `data/f7/employers_deduped.db`

**Tables created:**
| Table | Key Columns | Rows |
|-------|-------------|------|
| `f7_employers` (raw) | employer_id, employer_name, state, naics, lat, lon | ~62K |
| `f7_employers_deduped` | + employer_name_aggressive, naics_detailed | ~60,953 |
| `f7_union_employer_relations` | employer_id, union_file_number, bargaining_unit_size | ~120K |
| `unions_master` | f_num, union_name, aff_abbr, members | ~21K |

**Critical:** `employer_name_aggressive` = uppercased, suffix-stripped name. Used by ALL downstream matching.

**Secondary sources (own tables):** Mergent (56K `mergent_employers`), OSHA (1M `osha_establishments`), WHD (363K `whd_cases`), 990 (`national_990_filers`), SAM (826K `sam_entities`), GLEIF (379K `gleif_us_entities`), SEC (`sec_companies`).

## Stage 2: Deduplication

**Scripts:** `scripts/matching/splink_pipeline.py` (run), `scripts/matching/splink_config.py` (config), `scripts/cleanup/merge_f7_enhanced.py` (merge)

**Splink config (F7_SELF_DEDUP_SETTINGS):**
- Link type: `dedupe_only` (single DataFrame, DuckDB backend)
- Comparisons: JaroWinkler name [0.95/0.88/0.80/0.70], exact state, Levenshtein city [1/2], JW zip [0.95/0.80], exact naics (with TF), JW street [0.90/0.70]
- Blocking: state+name3, state+city, zip+name prefix
- Auto-accept >= 0.85, review >= 0.70

**Merge process:** Union-find groups -> keeper selection (largest unit_size, then most notices, then alpha) -> updates 6 tables:
1. `f7_union_employer_relations` (re-point employer_id)
2. `nlrb_voluntary_recognition` (re-point matched_employer_id)
3. `nlrb_participants` (re-point matched_employer_id)
4. `osha_f7_matches` (re-point f7_employer_id, handle dup estab conflicts)
5. `mergent_employers` (re-point matched_f7_employer_id)
6. `corporate_identifier_crosswalk` (COALESCE identifiers or re-point)

**Result:** 62,163 -> 60,953 (1,210 merges). Logged to `f7_employer_merge_log`.

## Stage 3: Matching Pipeline

### 3A: Corporate Crosswalk (`scripts/matching/build_corporate_crosswalk.py`)
Central identity hub: `corporate_identifier_crosswalk` with columns: id, ein, cik, lei, duns, f7_employer_id, mergent_duns, gleif_lei, sec_cik, sam_uei, sam_cage_code, naics_6digit, is_federal_contractor, federal_obligations, federal_contract_count, source, match_method, match_confidence, canonical_name, state.

Built through: Mergent-EIN->SEC-CIK, SEC-LEI->GLEIF, SEC->GLEIF name+state, 990-EIN->SEC-CIK, F7->SEC name+state, Mergent bridge.

Growth: 3,010 -> 4,220 -> 5,772 -> 14,561 -> ~25,177.

### 3B: Splink Cross-Source (`scripts/matching/splink_pipeline.py`)
- Mergent->F7: 947 matches (company_name_normalized vs employer_name_aggressive)
- GLEIF->F7: 605 matches (name_normalized vs employer_name_aggressive, no city comparison)

### 3C: OSHA Matching (`scripts/scoring/osha_match_phase5.py`)
Output: `osha_f7_matches` (establishment_id, f7_employer_id, match_method, match_confidence, match_source)

4 tiers:
1. **Mergent bridge:** OSHA->Mergent (fuzzy sim>=0.50)->crosswalk->F7
2. **Address:** street_number+first_word+state (sim>=0.25 sanity), then normalized_addr+city+state+zip3
3. **Facility stripping:** `strip_facility_markers()` removes #123/STORE/WAREHOUSE/DBA/PLANT, then city+state+sim>=0.55
4. **State+NAICS fuzzy:** same state + 2-digit NAICS + pg_trgm sim>=0.55 (was 0.40, too aggressive)

Result: 138,340 matches (13.7%).

### 3D: WHD Matching (`scripts/scoring/whd_match_phase5.py`)
Output: `whd_f7_matches` (case_id, f7_employer_id, match_method, match_confidence, match_source)

6 tiers:
1. name_normalized + state + city (conf 0.90)
2. name_normalized + state (conf 0.80)
3. Trade/legal name cross-match (when different from primary)
4. Mergent bridge (same as OSHA)
5. Normalized address + city + state
6. pg_trgm fuzzy + state (sim>=0.55), state-by-state

Also re-aggregates WHD data onto `f7_employers_deduped` and `mergent_employers`.
Result: 24,610 matches (6.8%).

### 3E: 990 Matching (`scripts/scoring/match_990_national.py`)
Output: `national_990_f7_matches` (n990_id, ein, f7_employer_id, match_method, match_confidence)

5 tiers:
1. EIN via existing crosswalk (conf 0.95)
2. EIN via Mergent (conf 0.90)
3. Name+state exact (conf 0.85)
4. pg_trgm fuzzy >=0.60, state-by-state
5. Address match (conf 0.75)

Updates crosswalk with new EINs (+10,688 rows).
Result: 14,059 matches (2.4%).

### 3F: SAM Matching (`scripts/scoring/match_sam_to_employers.py`)
Output: `sam_f7_matches` (uei, f7_employer_id, match_method, match_confidence)

4 tiers:
1. Exact name+state (A1: aggressive, A2: full normalized)
2. City+state + pg_trgm `%` operator (GIN-indexed, threshold 0.55)
3. NAICS+state + pg_trgm `%` (threshold 0.60, stricter)
4. DBA name exact match

Updates crosswalk with sam_uei, cage_code, is_federal_contractor, naics_6digit.
Result: ~10,164 matches.

## Stage 4: Enrichment

### Gower Similarity (`scripts/scoring/compute_gower_similarity.py`)
**Materialized view:** `mv_employer_features` (54,973 rows, 14 features)
- Categorical: state, county, company_type
- Numeric: employees_here_log, employees_total_log, revenue_log, company_age, osha_violation_rate, whd_violation_rate, bls_growth_pct
- Binary: is_subsidiary, is_federal_contractor
- Hierarchical: naics_4 (exact=0, same 2-digit=0.3, different=1.0)

Weights: industry=3.0, workforce=2.0, most=1.0, county/type/age=0.5.

Splits into union refs (is_union=1, ~989) vs targets (~54K). Top-5 nearest per target.
Output: `employer_comparables` (269,810 rows), `mergent_employers.similarity_score` = 1 - avg_distance.

### NLRB Predictions (`scripts/scoring/compute_nlrb_patterns.py`)
Analyzes 33K historical elections -> `ref_nlrb_industry_win_rates` (24), `ref_nlrb_size_win_rates` (8).
Computes `mergent_employers.nlrb_predicted_win_pct` = state(35%) + industry(35%) + size(20%) + trend(10%).
Range: 69.5-85.3% across 56,426 employers.

## Stage 5: Scoring (Pre-computed MV, `api/routers/organizing.py`)

Endpoint: `GET /api/organizing/scorecard`
Source: `mv_organizing_scorecard` materialized view (pre-computed from `v_osha_organizing_targets` + 8 reference tables)
Detail: `GET /api/organizing/scorecard/{estab_id}` reads base scores from MV, adds detail-only context (NY/NYC contracts, NLRB participants)
Refresh: `POST /api/admin/refresh-scorecard` (admin-only, CONCURRENTLY)
Script: `scripts/scoring/create_scorecard_mv.py` (create or `--refresh`)

**9-Factor System (0-100):**

| # | Factor | Max | Source | Logic |
|---|--------|-----|--------|-------|
| 1 | Company Unions | 20 | osha_f7_matches | 20 if linked to F7 employer, else 0 |
| 2 | Industry Density | 10 | v_naics_union_density | >20%=10, >10%=8, >5%=5, else 2 |
| 3 | Geographic | 10 | ref_rtw_states + ref_nlrb_state_win_rates + epi_state_benchmarks | NLRB win(0-4) + density(0-3) + non-RTW(0-3) |
| 4 | Size | 10 | employee_count | 50-250=10, 250-500=8, 25-50=6, 500-1K=4, else 2 |
| 5 | OSHA | 10 | ref_osha_industry_averages | ratio to industry avg (>=3x=7 base + severity bonus) |
| 6 | NLRB | 10 | ref_nlrb rates + mergent.nlrb_predicted_win_pct | predicted win% via Mergent link or state+industry fallback |
| 7 | Contracts | 10 | corporate_identifier_crosswalk | >$5M=10, >$1M=7, >$100K=4, >0=2 |
| 8 | Projections | 10 | bls_industry_projections | BLS growth >10%=10, >5%=7, >0%=4, else 2 |
| 9 | Similarity | 10 | mergent_employers.similarity_score | >=0.80=10, >=0.60=7, >=0.40=4, else 1 |

**Tiers:** TOP>=30, HIGH>=25, MEDIUM>=20, LOW<20

**Critical insight:** Unmatched OSHA establishments (no F7 link) lose the 20pt union factor and likely contracts/similarity/NLRB too, capping practical score ~50/100.

## Stage 6: Frontend (`files/organizer_v5.html`, ~9,100 lines)

**3 modes** via `currentAppMode`:
- **Territory:** union + state/metro selection -> 7 parallel API calls -> KPIs, Leaflet map, Chart.js charts, target tables, elections, violators
- **Search:** name/state/city/NAICS/union filters -> results list with mini score bars
- **Deep Dive:** full employer profile -> 9 factor bars, OSHA/geographic/NLRB/contracts panels, sibling employers, election history

## Critical Join Path (How an Employer Gets Scored)

```
OSHA establishment (osha_establishments)
  |-> v_osha_organizing_targets (view: violation summary)
  |-> osha_f7_matches.f7_employer_id (enables 20pt Company Unions)
  |     |-> corporate_identifier_crosswalk (enables Contracts factor)
  |     |-> mergent_employers.matched_f7_employer_id (enables Similarity + NLRB)
  |-> NAICS code (Industry Density, OSHA normalization, BLS Projections)
  |-> State (Geographic Favorability)
  |-> Employee count (Size factor)
```
