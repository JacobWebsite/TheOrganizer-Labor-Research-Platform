# Scoring System Architecture

The scoring system evaluates employers for organizing potential across two pools: **union employers** (F7-based, 146K) scored in `mv_unified_scorecard`, and **non-union targets** (master-based, 4.3M) inventoried in `mv_target_scorecard`. Both are materialized views rebuilt from upstream data source MVs, with optional research enhancement.

---

## Pipeline Build Order

```
1. build_employer_data_sources.py  →  mv_employer_data_sources   (146K F7 employers)
2. build_unified_scorecard.py      →  mv_unified_scorecard        (depends on #1)
3. build_target_data_sources.py    →  mv_target_data_sources      (4.3M non-union masters)
4. build_target_scorecard.py       →  mv_target_scorecard          (depends on #3)
5. rebuild_search_mv.py            →  mv_employer_search           (independent, 107K)
6. compute_gower_similarity.py     →  mv_employer_features +       (optional, currently broken)
                                      employer_comparables
```

All scripts support `--refresh` for `REFRESH MATERIALIZED VIEW CONCURRENTLY` (requires unique index). Without `--refresh`, they DROP CASCADE + CREATE.

**Warning:** Dropping `mv_employer_data_sources` cascades to `mv_unified_scorecard`. Dropping `mv_target_data_sources` cascades to `mv_target_scorecard`. Rebuild in order.

---

## Unified Scorecard (`mv_unified_scorecard`)

**Script:** `scripts/scoring/build_unified_scorecard.py`
**Rows:** 146,863 (1:1 with `f7_employers_deduped`)
**Rebuild:** `PYTHONPATH=. py scripts/scoring/build_unified_scorecard.py` (~14s)

### CTE Pipeline

```
osha_agg → osha_avgs → nlrb_elections_agg → nlrb_ulp_agg → nlrb_agg
→ nlrb_industry_momentum → nlrb_state_momentum
→ whd_agg → union_prox → bls_proj → financial_990
→ feature_bridge → similarity_agg
→ raw_scores (all JOINs)
→ scored (adds score_similarity + score_financial)
→ research_enhanced (LEFT JOIN research_score_enhancements, GREATEST logic)
→ strategic_pillars (Anger / Stability / Leverage)
→ weighted (composite score + legacy score)
→ ranked (percentile + tier assignment)
→ final SELECT (flags, tiers, delta)
```

### The 9 Scoring Factors

All factors score 0-10 (NULL if no data).

#### 1. score_osha (weight=1x, coverage=22.3%)

Industry-normalized OSHA violations with temporal decay.

```
base = (total_violations / industry_avg) * exp(-LN(2)/5 * years_since_inspection)
score_osha = LEAST(10, base + severity_bonus)
```

- **Industry normalization:** `ref_osha_industry_averages` at 4-digit NAICS, falls back to 2-digit, then overall average (2.23)
- **Temporal decay:** 5-year half-life from `latest_inspection`
- **Severity bonus:** +1 if willful OR repeat violations > 0
- **Source:** `osha_f7_matches` + `osha_establishments` + `osha_violation_summary`

#### 2. score_nlrb (weight=3x, coverage=17.6%)

Own election history + ULP charges + industry/state win momentum.

```
election_score = (wins*2 + elections - losses) * decay_7yr
ulp_boost = tier(ulp_count) * ulp_decay_7yr     -- 0→0, 1→2, 2-3→4, 4-9→6, 10+→8
industry_momentum = tier(naics2_wins_3yr)         -- 50+→2.0, 20+→1.5, 5+→1.0, 1+→0.5
state_momentum = tier(state_wins_3yr)             -- 100+→2.0, 40+→1.5, 10+→1.0, 1+→0.5
score_nlrb = LEAST(10, GREATEST(0, election_score + ulp_boost + industry_momentum + state_momentum))
```

- **Temporal decay:** 7-year half-life from `latest_election` / `latest_ulp`
- **Momentum CTEs:** Aggregate `nlrb_elections` wins in last 3 years by NAICS-2 and state, joined via `nlrb_participants` -> `f7_employers_deduped`
- **Source:** `nlrb_participants` (Employer path for elections, Charged Party/Respondent for ULP -CA- cases)
- **Output columns:** `nlrb_industry_wins_3yr`, `nlrb_state_wins_3yr` (for transparency)

#### 3. score_whd (weight=1x, coverage=7.7%)

Wage & Hour Division case count with temporal decay.

```
base = tier(case_count) * exp(-LN(2)/5 * years_since_finding)
-- 0→0, 1→5, 2-3→7, 4+→10
```

- **Source:** `whd_f7_matches` + `whd_cases`
- **Metadata:** backwages, civil penalties, repeat violator flag carried through

#### 4. score_contracts (weight=2x, coverage=6.3%)

Federal contract obligations tiered.

```
$100M+ → 10, $10M+ → 8, $1M+ → 6, $100K+ → 4, >$0 → 2, registered only → 1
```

- **Source:** `mv_employer_data_sources.federal_obligations` (from `corporate_identifier_crosswalk`)

#### 5. score_union_proximity (weight=3x, coverage=100%)

Canonical group size and corporate family connections.

```
group_members - 1 >= 2 → 10
group_members - 1 = 1 OR has_corporate_family → 5
standalone → 0
both NULL → NULL
```

- **Source:** `employer_canonical_groups` + `corporate_identifier_crosswalk.corporate_family_id`

#### 6. score_industry_growth (weight=2x, coverage=84.9%)

BLS employment projection trends.

```
score = ((employment_change_pct + 10) / 20) * 10   [clamped 0-10]
```

- **Hierarchical NAICS:** 2-digit primary with aliasing for composite codes (31-33→'31-330', 44-45→'44-450', 48-49→'48-490')
- **Source:** `bls_industry_projections`

#### 7. score_size (weight=0x, coverage=100%)

Employer size sweet spot. **Weight is zero** — size is a filter dimension, not a scoring signal. Audit finding: +0.2pp predictive power (effectively zero).

```
<15 → 0, 500+ → 10, else → ((size - 15) / 485) * 10
```

- Uses `company_size` (consolidated) or `latest_unit_size` (BU-level)

#### 8. score_similarity (weight=0x, coverage=0.1%)

Gower distance to unionized comparables. **Weight is zero** — broken pipeline (name+state bridge only matches 833/146K employers). Column kept for future repair.

```
unionized_comparable_count: 5→10, 4→8, 3→6, 2→4, 1→2, 0→0
bonus: +1 if best_distance < 0.15
gated: NULL if score_union_proximity >= 5 (grouped employers excluded)
```

- **Source:** `employer_comparables` via `feature_bridge` CTE (name+state join to `mv_employer_features`)

#### 9. score_financial (weight=2x, coverage=7.3%)

990 nonprofit health + public company signal.

```
If has 990 data:
    revenue_scale: $10M+ → 6, $1M+ → 4, $100K+ → 2, else → 0
    asset_cushion: assets > 2x expenses → +2, > 1x → +1
    revenue_per_worker: $50K+ → +2, $20K+ → +1
    score = LEAST(10, sum of above)
If public company (no 990): 7
```

- **Source:** `national_990_f7_matches` + `national_990_filers`

### Research Enhancement

The `research_enhanced` CTE LEFT JOINs `research_score_enhancements` on `employer_id`:

```sql
GREATEST(s.score_osha, rse.score_osha) AS enh_score_osha
GREATEST(s.score_nlrb, rse.score_nlrb) AS enh_score_nlrb
-- ... same for whd, contracts, financial
COALESCE(s.score_size, rse.score_size) AS enh_score_size
```

Research can only **upgrade** a score, never downgrade (GREATEST logic). Enhanced scores flow into the strategic pillars.

**Output columns:** `has_research`, `research_run_id`, `research_quality`, `research_approach`, `research_trend`, `research_contradictions`, all `enh_score_*` columns.

### Strategic Pillars

Three action-oriented dimensions computed from enhanced scores:

#### Pillar 1: ANGER (Motivation) — "How angry are the workers?"

```
If research-provided score_anger exists → use it
Else:
    enh_score_osha * 0.3
    + enh_score_whd * 0.3
    + nlrb_ulp_tier * 0.4    -- 0→0, 1→4, 2-3→6, 4-9→8, 10+→10
    + sentiment_bonus         -- from research (0 if absent)
```

#### Pillar 2: STABILITY (Winnability) — "Can they maintain a committee?"

```
If research-provided score_stability exists → use it
If turnover_rate_found exists → 10 - turnover_rate
Else → 5.0 (baseline)
```

#### Pillar 3: LEVERAGE (Power) — "What structural power exists?"

```
LEAST(10,
    score_union_proximity * 0.3
    + enh_score_contracts * 0.2
    + enh_score_financial * 0.2
    + score_industry_growth * 0.15
    + enh_score_size * 0.15
    + RPE_bonus)              -- +1 if revenue_per_employee > $500K
```

### Final Weighted Score

```
weighted_score = (score_anger * 3 + score_stability * 3 + score_leverage * 4) / 10
```

### Legacy Weighted Score (backward compat)

Traditional weighted average of individual factors (not pillars):

```
legacy = (proximity*3 + nlrb*3 + contracts*2 + growth*2 + financial*2 + osha*1 + whd*1)
         / (sum of weights for non-null factors)
```

`strategic_delta = weighted_score - legacy_weighted_score`

### Tier Assignment

Percentile-based with a 3-factor guardrail (Decision D3):

| Tier | Percentile | Guardrail | Distribution |
|------|-----------|-----------|-------------|
| Priority | >= 97th | >= 3 factors | ~3% |
| Strong | >= 85th | >= 3 factors | ~12% |
| Promising | >= 60th | none | ~25% |
| Moderate | >= 25th | none | ~35% |
| Low | < 25th | none | ~25% |

Legacy tiers (TOP/HIGH/MEDIUM/LOW) also computed for backward compatibility.

### Flag Columns

- `has_recent_violations`: OSHA inspection OR WHD finding OR NLRB ULP within 2 years
- `has_active_contracts`: score_contracts > 0

### Indexes

```sql
UNIQUE idx_mv_us_employer_id (employer_id)          -- enables REFRESH CONCURRENTLY
idx_mv_us_state (state)
idx_mv_us_unified_score (unified_score DESC NULLS LAST)
idx_mv_us_weighted_score (weighted_score DESC NULLS LAST)
idx_mv_us_naics (naics)
idx_mv_us_score_tier (score_tier)
idx_mv_us_factors (factors_available)
idx_mv_us_has_research (has_research) WHERE TRUE
idx_mv_us_strategic_delta (strategic_delta DESC NULLS LAST)
```

---

## Target Scorecard (`mv_target_scorecard`)

**Script:** `scripts/scoring/build_target_scorecard.py`
**Rows:** 4,381,582 (non-union employers with >= 1 data source)
**Rebuild:** `PYTHONPATH=. py scripts/scoring/build_target_scorecard.py` (~120s)

### Key Difference from Unified

The target scorecard has **no composite score**. Discovery is filter-driven (state, industry, size, enforcement flags). Default sort is by signal count, then alphabetically. All JOINs go through `master_employer_source_ids` instead of F7 match tables.

### CTE Pipeline

```
osha_agg → osha_avgs → whd_agg
→ nlrb_elections_agg → nlrb_ulp_agg → nlrb_agg
→ nlrb_industry_momentum → nlrb_state_momentum
→ financial_990 → bls_proj → state_density → industry_density
→ research_bridge (F7 link to research_score_enhancements)
→ raw_signals (all JOINs, 8 signal computations)
→ enhanced (GREATEST with research, signal inventory, enforcement flags)
→ final SELECT (pillars, gold standard tiers)
```

### The 8 Signals

| Signal | Coverage | Avg | Formula |
|--------|----------|-----|---------|
| signal_osha | 16.2% | 0.60 | Same as unified (industry-normalized, 5yr decay) |
| signal_whd | 6.7% | 1.37 | Same as unified (case count tiers, 5yr decay) |
| signal_nlrb | 3.0% | 2.94 | Same as unified (elections + ULP + momentum) |
| signal_contracts | 17.8% | 5.00 | **Binary: is_federal_contractor → 5** (not tiered like unified) |
| signal_financial | 26.5% | 5.87 | Same as unified (990 revenue + assets + RPE) |
| signal_industry_growth | 36.4% | 6.68 | Same as unified (BLS projections) |
| signal_union_density | 95.7% | 1.63 | **NEW:** `(state_density*0.5 + industry_density*0.5) / 4` |
| signal_size | 16.7% | 0.81 | Same as unified (weight=0, filter only) |

**signal_union_density** is unique to the target scorecard. It blends state-level union membership (`bls_state_density`) with BLS industry-level density (`bls_national_industry_density`) via a NAICS-to-BLS-category mapping (e.g., NAICS 62 → 'EDU_HEALTH'). Higher density means workers have more union exposure.

### Research Enhancement Bridge

Target scorecard uses an indirect path to `research_score_enhancements`:

```sql
research_bridge AS (
    SELECT DISTINCT ON (mesi.master_id)
        mesi.master_id,
        rse.*
    FROM master_employer_source_ids mesi
    JOIN research_score_enhancements rse ON rse.employer_id = mesi.source_id
    WHERE mesi.source_system = 'f7'
    ORDER BY mesi.master_id, rse.run_quality DESC NULLS LAST
)
```

This bridges through F7 source IDs in `master_employer_source_ids`. Currently 0 matches (researched employers are union F7, not in non-union target pool).

### Enhanced Signals

Same GREATEST logic as unified — research can only upgrade:

```sql
GREATEST(rs.signal_osha, rs.rse_score_osha) AS enh_signal_osha
-- ... same for all signals
```

### Signal Inventory

```sql
signals_present = SUM(CASE WHEN signal_X IS NOT NULL THEN 1 ELSE 0 END)  -- for all 8 signals
enforcement_count = SUM of (osha, whd, nlrb) non-null signals
has_enforcement = any enforcement signal present
has_recent_violations = any enforcement date within 2 years
```

### Pillar Computation

| Pillar | Formula | Coverage |
|--------|---------|----------|
| pillar_anger | AVG of non-null (enh_osha, enh_whd, enh_nlrb), or research anger | 25.5% |
| pillar_leverage | AVG of non-null (enh_contracts, enh_financial, union_density) | widespread |
| pillar_stability | Research stability, or `10 - turnover`, or NULL | rare |

### Gold Standard Tiers

Profile completeness, not scoring:

| Tier | Criteria |
|------|----------|
| Platinum | has research + quality >= 8.5 |
| Gold | has research + quality >= 7.0 |
| Silver | has research + quality >= 5.0 |
| Bronze | has research (any quality) OR >= 3 enforcement/financial signals |
| Stub | everything else |

---

## Employer Data Sources (`mv_employer_data_sources`)

**Script:** `scripts/scoring/build_employer_data_sources.py`
**Rows:** 146,863 (1:1 with `f7_employers_deduped`)
**Rebuild:** `PYTHONPATH=. py scripts/scoring/build_employer_data_sources.py`

Foundation MV for the unified scorecard. Computes source availability flags and corporate crosswalk data.

### Source Flags

Each flag is a boolean computed via existence check in the respective match table:

| Flag | Source Table | Join Path | Coverage |
|------|-------------|-----------|----------|
| has_osha | osha_f7_matches | f7_employer_id | 21.8% (32,051) |
| has_nlrb | nlrb_participants | matched_employer_id (elections OR ULP) | 17.6% (25,879) |
| has_whd | whd_f7_matches | f7_employer_id | 7.7% (11,297) |
| has_990 | national_990_f7_matches | f7_employer_id | 7.3% (10,646) |
| has_sam | sam_f7_matches | f7_employer_id | 12.6% (18,550) |
| has_sec | unified_match_log | source_system='sec', status='active' | 1.1% (1,642) |
| has_gleif | unified_match_log | source_system='gleif', status='active' | 1.2% (1,810) |
| has_mergent | unified_match_log | source_system='mergent', status='active' | 0.7% (1,045) |

`source_count` = sum of all flags. Distribution: 0=49.2%, 1=30.0%, 2+=20.8%.

### Corporate Crosswalk Columns

Via LATERAL JOIN to `corporate_identifier_crosswalk` (picks row with highest `federal_obligations`):

- `corporate_family_id`, `sec_cik`, `gleif_lei`, `mergent_duns`, `ein`, `ticker`
- `is_public`, `is_federal_contractor`, `federal_obligations`, `federal_contract_count`

### Identity Columns

From `f7_employers_deduped`: `employer_id`, `employer_name`, `state`, `city`, `naics`, `latest_unit_size`, `latest_union_name`, `is_historical`, `canonical_group_id`, `is_canonical_rep`.

From `employer_canonical_groups`: `company_size` (consolidated workers across group).

---

## Target Data Sources (`mv_target_data_sources`)

**Script:** `scripts/scoring/build_target_data_sources.py`
**Rows:** 4,381,582
**Rebuild:** `PYTHONPATH=. py scripts/scoring/build_target_data_sources.py`

Foundation MV for the target scorecard. Uses `master_employer_source_ids` instead of F7 match tables.

### Key Differences from Employer Data Sources

| Feature | Employer Data Sources | Target Data Sources |
|---------|----------------------|---------------------|
| Base table | f7_employers_deduped | master_employers (non-union) |
| Join path | Legacy F7 match tables | master_employer_source_ids |
| Row count | 146K | 4.3M |
| Quality gate | None | data_quality_score >= 20 |
| Extra flags | has_gleif | has_bmf, has_corpwatch |
| Source origin | Always 'f7' | BMF/SAM/OSHA/CorpWatch/WHD/NLRB/Mergent |

### Source Distribution

BMF (40%), SAM (18%), OSHA (16%), CorpWatch (14.5%), WHD (6.7%), NLRB (4.4%), Mergent (1.2%).

---

## Gower Similarity Engine

**Script:** `scripts/scoring/compute_gower_similarity.py`
**Output:** `mv_employer_features` (view) + `employer_comparables` (table)
**Runtime:** ~30 minutes

### The 14 Features

| Feature | Weight | Type | Source |
|---------|--------|------|--------|
| naics_4 | 3.0 | Hierarchical | 4-digit exact=0, 2-digit=0.3, diff=1.0 |
| employees_here_log | 2.0 | Numeric (log) | mergent_employers |
| employees_total_log | 1.0 | Numeric (log) | mergent_employers |
| state | 1.0 | Categorical | mergent_employers |
| county | 0.5 | Categorical | mergent_employers |
| company_type | 0.5 | Categorical | mergent_employers |
| is_subsidiary | 1.0 | Binary | mergent_employers |
| revenue_log | 1.0 | Numeric (log) | mergent_employers |
| company_age | 0.5 | Numeric (min-max) | mergent_employers |
| osha_violation_rate | 1.0 | Numeric | osha (violations/employee) |
| whd_violation_rate | 1.0 | Numeric | whd (violations/employee) |
| is_federal_contractor | 1.0 | Binary | crosswalk |
| bls_growth_pct | 0.5 | Numeric | bls_industry_projections |
| occupation_overlap | 1.5 | Numeric | bls_industry_occupation_matrix |

**Total weight:** 19.5

### Gower Distance Formula

```
gower_distance = sum(feature_distance_i * weight_i * valid_mask_i)
                 / sum(weight_i * valid_mask_i)
```

- **Numeric:** Absolute difference after min-max normalization, clamped [0,1]
- **Categorical/Binary:** Hamming distance (0=same, 1=different)
- **Hierarchical NAICS:** exact 4-digit=0, same 2-digit=0.3, else=1.0
- **NULL handling:** Missing features excluded from both numerator and denominator

Computes pairwise distances between all non-union targets and union references. Stores top-5 nearest neighbors per target in `employer_comparables`.

### Current State

Broken for the unified scorecard — the `feature_bridge` CTE joins `mv_employer_features` to `mv_employer_data_sources` via name+state, which only matches 833/146K F7 employers. `score_similarity` weight is zeroed.

---

## Search MV (`mv_employer_search`)

**Script:** `scripts/scoring/rebuild_search_mv.py`
**Rows:** 107,321
**Rebuild:** `PYTHONPATH=. py scripts/scoring/rebuild_search_mv.py`

Unified search index across 4 union employer sources:

| Source | Rows | Logic |
|--------|------|-------|
| F7 | 50,446 | Canonical reps + ungrouped singletons, excludes historical |
| NLRB | 55,531 | Distinct participant name+city+state, unmatched to F7 |
| VR | 824 | Voluntary recognition, unmatched to F7 |
| MANUAL | 520 | Research/case studies |

**Indexes:** UNIQUE on `canonical_id`, GiST trigram on `search_name`, state, city, source_type, group_id.

**API:** `GET /api/employers/unified-search`
**Frontend:** Full-text search with state/industry filters, results link to `/employers/:id`

---

## Legacy Scorecard (`mv_organizing_scorecard`)

**Script:** `scripts/scoring/create_scorecard_mv.py`
**Status:** Legacy (pre-Phase E3), still queryable but superseded by unified scorecard.

OSHA-centric view of non-union establishments with violations. 9 factors summed to 0-90 scale. `score_versions` table tracks all creation/refresh operations with factor weights, decay params, and score stats.

---

## Research Score Enhancements

**Script:** `scripts/scoring/create_research_enhancements.py` (schema only)
**Table:** `research_score_enhancements` (populated by research agent auto-grader)

Stores per-employer scorecard factor overrides derived from research dossiers. UNIQUE on `employer_id` — higher-quality research replaces lower via UPSERT.

### Integration Paths

- **Path A (Union enrichment):** `is_union_reference=TRUE` → Extracted features improve Gower reference pool
- **Path B (Non-union scoring):** `is_union_reference=FALSE` → Directly upgrades unified scorecard factors via LEFT JOIN + GREATEST()

### Quality Gate

Research enhancements are skipped if `overall_quality_score < 3.0` (too low confidence to feed into scorecards).

---

## Reference Tables

| Table | Purpose | Rows | Update Frequency |
|-------|---------|------|-----------------|
| `ref_osha_industry_averages` | NAICS 2/4-digit violation medians | ~600 | Annually |
| `bls_industry_projections` | Employment change % by matrix code | ~430 | Annually |
| `bls_state_density` | State union density by year | ~3K | Annually |
| `bls_national_industry_density` | BLS industry category density | ~12 | Annually |
| `bls_industry_occupation_matrix` | Occupation mix by industry | ~40K | Annually |
| `ref_nlrb_state_win_rates` | State election win % | 51 | Annually |
| `ref_nlrb_industry_win_rates` | NAICS-2 election win % | ~20 | Annually |
| `ref_rtw_states` | Right-to-work states | ~28 | Static |
| `epi_state_benchmarks` | State union member totals | 51 | Annually |
| `score_versions` | MV creation/refresh audit trail | growing | Each rebuild |

---

## Match Tables

Source-to-F7 match tables that feed the scoring system:

| Table | Source → Target | Rows | Key Column |
|-------|----------------|------|------------|
| `osha_f7_matches` | OSHA establishments → F7 | ~73K | establishment_id → f7_employer_id |
| `whd_f7_matches` | WHD cases → F7 | ~4K | case_id → f7_employer_id |
| `national_990_f7_matches` | 990 filers → F7 | ~2K | n990_id → f7_employer_id |
| `sam_f7_matches` | SAM.gov → F7 | ~8K | sam_id → f7_employer_id |
| `unified_match_log` | Central audit log (all sources) | ~1.8M | (run_id, source_system, source_id, target_id) |
| `master_employer_source_ids` | All sources → non-union masters | ~11M | (master_id, source_system, source_id) |

---

## API Endpoints

### Unified Scorecard (`api/routers/scorecard.py`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/scorecard/unified` | List with filters + sort + pagination |
| GET | `/api/scorecard/unified/stats` | Aggregate stats, tier distribution, factor coverage |
| GET | `/api/scorecard/unified/states` | State-level summary (count, avg_score, avg_factors) |
| GET | `/api/scorecard/unified/{employer_id}` | Detail with explanations for each factor |

**List filters:** `state`, `naics` (prefix), `min_score`, `min_factors` (default 2), `score_tier`, `has_osha`, `has_nlrb`, `has_research`.

**Sort options:** `score` (default), `size`, `factors`, `name`, `strategic_delta`, `score_delta`.

**Detail explanations:** Human-readable text for each non-null factor, including momentum counts for NLRB, decay factors for OSHA, dollar amounts for contracts/WHD. Research enhancement info when `has_research=true` with link to `/api/research/result/{run_id}`.

### Target Scorecard (`api/routers/target_scorecard.py`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/targets/scorecard` | List with filters + sort + pagination |
| GET | `/api/targets/scorecard/stats` | Signal coverage, enforcement flags, gold tiers |
| GET | `/api/targets/scorecard/{master_id}` | Detail with signal explanations + pillars |

**List filters:** `q` (name search), `state`, `naics`, `min_signals`, `has_enforcement`, `has_recent_violations`, `min_employees`, `max_employees`, `is_federal_contractor`, `is_nonprofit`, `source_origin`, `has_research`, `gold_standard_tier`.

**Sort options:** `signals` (default), `name`, `employees`, `enforcement`, `source_count`, `research_quality`, `gold_tier`.

---

## Audit Findings That Shaped the Design

Seven audit reports (Feb 2025-26, 3 AI tools, 2 rounds + synthesis) validated and reshaped the scoring system:

| Finding | Impact |
|---------|--------|
| Score IS predictive: win rates monotonic by tier (Priority 90.9% → Low 74.1%) | Validated overall approach |
| NLRB is strongest signal (+10.2pp), Industry Growth underweighted (+9.6pp) | NLRB gets 3x weight, growth gets 2x |
| Size has zero predictive power (+0.2pp) | Weight set to 0 |
| Similarity has zero predictive power | Weight set to 0 (also broken pipeline) |
| OSHA predicts losses (-0.6pp) | Weight reduced to 1x |
| Fewer data factors = higher win rates (2-factor=88.2%, 8-factor=73.4%) | 3-factor guardrail for top tiers |
| 86% of Priority tier lacks enforcement data | Enforcement gate rejected (D1/D7) |
| Propensity model is fake (hardcoded, accuracy 0.53) | Replaced by strategic pillars |
| Fuzzy match 0.80-0.85 has 40-50% FP rate | Below-0.85 deactivated |

### Key Design Decisions

- **D1/D7:** No enforcement gate for any tier. Structural signals over enforcement presence.
- **D2:** Size = filter dimension, not scoring signal (weight=0).
- **D3:** Minimum 3 factors required for Priority and Strong tiers.
- **D4:** Strategic pillars (Anger/Stability/Leverage) replace single composite heuristic.
- **D5:** Research upgrades signals, never downgrades (GREATEST logic).

---

## Tests

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_unified_scorecard.py` | 26 | MV schema, factor ranges, tier assignment, research columns, API endpoints |
| `tests/test_target_scorecard.py` | 28 | Signal ranges, pillar computation, gold tiers, enhanced signals, API endpoints |
| `tests/test_employer_data_sources.py` | 19 | Source flags, crosswalk integration, API |
| `tests/test_research_enhancements.py` | 31 | Enhancement schema, quality gate, UPSERT, MV columns |
| `tests/test_weighted_scorecard.py` | various | Legacy scorecard compatibility |

---

## Complete Column Lists

### mv_unified_scorecard

**Identity:** employer_id, employer_name, state, city, naics, latest_unit_size, latest_union_fnum, latest_union_name, is_historical, canonical_group_id, is_canonical_rep, source_count, ein, ticker, corporate_family_id.

**Source flags:** has_osha, has_nlrb, has_whd, has_990, has_sam, has_sec, has_gleif, has_mergent, is_public, is_federal_contractor, federal_obligations, federal_contract_count.

**Factor scores (0-10):** score_osha, score_nlrb, score_whd, score_contracts, score_union_proximity, score_industry_growth, score_size, score_similarity, score_financial.

**Raw detail:** osha_estab_count, osha_total_violations, osha_total_penalties, osha_latest_inspection, osha_decay_factor, nlrb_election_count, nlrb_win_count, nlrb_latest_election, nlrb_total_eligible, nlrb_decay_factor, nlrb_ulp_count, nlrb_latest_ulp, nlrb_industry_wins_3yr, nlrb_state_wins_3yr, whd_case_count, whd_total_backwages, whd_total_penalties, whd_latest_finding, whd_repeat_violator, bls_growth_pct, n990_revenue, n990_assets, n990_expenses, unionized_comparable_count, best_distance.

**Research:** has_research, research_run_id, research_quality, research_approach, research_trend, research_contradictions, enh_score_osha, enh_score_nlrb, enh_score_whd, enh_score_contracts, enh_score_financial, enh_score_size, rse_score_stability, rse_score_anger, turnover_rate_found, sentiment_score_found, revenue_per_employee_found.

**Pillars:** score_anger, score_stability, score_leverage.

**Composite:** weighted_score, unified_score, legacy_weighted_score, strategic_delta, total_weight, factors_available, factors_total, coverage_pct, score_percentile.

**Tiers & flags:** score_tier, score_tier_legacy, has_recent_violations, has_active_contracts.

### mv_target_scorecard

**Identity:** master_id, display_name, canonical_name, city, state, zip, naics, employee_count, ein, is_public, is_federal_contractor, is_nonprofit, source_origin, data_quality_score, source_count.

**Source flags:** has_osha, has_whd, has_nlrb, has_990, has_sam, has_sec, has_mergent.

**Signals (0-10):** signal_osha, signal_whd, signal_nlrb, signal_contracts, signal_financial, signal_industry_growth, signal_union_density, signal_size.

**Raw detail:** osha_estab_count, osha_total_violations, osha_total_penalties, osha_latest_inspection, osha_decay_factor, nlrb_election_count, nlrb_win_count, nlrb_loss_count, nlrb_latest_election, nlrb_total_eligible, nlrb_decay_factor, nlrb_ulp_count, nlrb_latest_ulp, nlrb_industry_wins_3yr, nlrb_state_wins_3yr, whd_case_count, whd_total_backwages, whd_total_penalties, whd_latest_finding, whd_repeat_violator, bls_growth_pct, state_union_density_pct, industry_union_density_pct, n990_revenue, n990_assets, n990_expenses.

**Research:** has_research, research_run_id, research_quality, rse_score_osha, rse_score_nlrb, rse_score_whd, rse_score_contracts, rse_score_financial, rse_score_size, rse_score_anger, rse_score_stability, research_approach, research_trend, research_contradictions, research_strengths, research_challenges, research_employee_count, research_revenue, turnover_rate_found, sentiment_score_found, revenue_per_employee_found, research_confidence.

**Enhanced:** enh_signal_osha, enh_signal_whd, enh_signal_nlrb, enh_signal_contracts, enh_signal_financial, enh_signal_size.

**Inventory:** signals_present, has_enforcement, enforcement_count, has_recent_violations.

**Pillars:** pillar_anger, pillar_leverage, pillar_stability.

**Tier:** gold_standard_tier (stub/bronze/silver/gold/platinum).
