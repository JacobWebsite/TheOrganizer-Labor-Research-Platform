# Phase 1B Investigation Sprint - Consolidated Summary

Generated: 2026-02-24 19:05

## Overall Status

- **Investigations run:** 8
- **Succeeded:** 8
- **Failed:** 0
- **Total runtime:** 22s
- **Verification pass:** PASS (2s)

## Investigation Results

| # | Topic | Tier | Status | Time | Report |
|---|-------|------|--------|------|--------|
| I11 | Geocoding gap by score tier | 1 | OK | 1s | I11_geocoding_gap_by_tier.md |
| I17 | Score distribution after Phase 1 | 1 | OK | 1s | I17_score_distribution_phase1.md |
| I18 | Active unions (filed LM in last 3 years) | 1 | OK | 3s | I18_active_unions.md |
| I20 | Corporate hierarchy Factor 1 coverage | 1 | OK | 1s | I20_corporate_hierarchy_coverage.md |
| I19 | Mel-Ro Construction OSHA spot check | 2 | OK | 1s | I19_mel_ro_spot_check.md |
| I15 | Missing source ID linkages root cause | 2 | OK | 6s | I15_missing_source_id_linkages.md |
| I14 | Legacy poisoned matches (non-SAM) | 2 | OK | 6s | I14_legacy_poisoned_matches.md |
| I12 | Geographic enforcement bias | 3 | OK | 4s | I12_geographic_enforcement_bias.md |

## Investigation Summaries

### I11 - Geocoding gap by score tier

Overall geocoding rate: **122,351** / **146,863** (83.3%). **24,512** employers lack coordinates.

### I17 - Score distribution after Phase 1

Total scored employers: **146,863**. Weighted score range: 0.00-10.00, mean 4.18, median 4.00.

### I18 - Active unions (filed LM in last 3 years)

**20,612** unions filed an LM report with `yr_covered >= 2022`, out of **26,666** total distinct unions in `lm_data`.

### I20 - Corporate hierarchy Factor 1 coverage

**3,317** / **146,863** F7 employers (2.3%) have a `corporate_family_id`. The corporate identifier crosswalk contains **26,705** entries spanning **5,764** distinct corporate families.

### I19 - Mel-Ro Construction OSHA spot check

Investigated **Mel-Ro Construction** (`6c5fec90faef51ae`) which has **12** active OSHA matches in `unified_match_log`. - Sampled **12** matches for spot-check - Estimated false-positive rate: **100.0%** (12/12 SUSPECT)

### I15 - Missing source ID linkages root cause

| Table | Source | Total | Linked | Orphaned | Orphan % | | --- | --- | --- | --- | --- | --- | | osha_f7_matches | osha | 98,891 | 43,998 | 54,893 | 55.5% | | whd_f7_matches | whd | 19,462 | 10,991 | 8,471 | 43.5% | | national_990_f7_matches | 990 | 20,005 | 13,215 | 6,790 | 33.9% |

### I14 - Legacy poisoned matches (non-SAM)

This audit samples active matches from the **oldest pipeline runs** for each source system to assess whether early matches contain false positives that have persisted uncorrected.

### I12 - Geographic enforcement bias

This investigation examines whether geographic enforcement density (specifically OSHA inspection/match rates by state) systematically inflates organizing scores. If states with more OSHA data also score higher, the scorecard may reflect enforcement geography rather than genuine organizing potential. - **States analyzed:** 61 - **OSHA match rate range:** 0.0% - 30.6% - **Avg weighted score range:** 0.05 - 8.88 - **Pearson r (OSHA match % vs avg score):** **0.0828**

## Verification Pass

- **5** of **11** checks passed (OK) - **5** stale (delta > 5%) - **1** errors

## Decision Implications

Depending on findings, these investigations may trigger:
- **I20**: If corporate hierarchy covers <5% of F7, may need to reduce Factor 1 (union proximity) weight from 3x
- **I17**: If distribution is still bimodal, more scoring work needed before Phase 4/6
- **I12**: If geographic bias is severe, geographic normalization needed in scoring
- **I19**: If Mel-Ro false positive rate is high, many-to-one inflation is systematic
- **I15/I14**: If legacy match quality is poor, re-running matching pipeline with stricter floors is warranted

