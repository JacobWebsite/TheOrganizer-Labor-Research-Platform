# Match Quality Report

Generated: 2026-02-15T15:08:50.547535

## Overview

| Metric | Value |
|--------|-------|
| Total active matches | 253,691 |
| Unique F7 employers matched | 48,469 |
| Total F7 employers | 113,713 |
| Overall coverage | 42.6% |

## Match Rates by Source

| Source | Matches | Unique Employers | Coverage |
|--------|---------|-----------------|----------|
| osha | 151,944 | 31,804 | 28.0% |
| whd | 29,964 | 11,019 | 9.7% |
| crosswalk | 19,293 | 13,998 | 12.3% |
| nlrb | 17,516 | 9,281 | 8.2% |
| 990 | 16,596 | 7,621 | 6.7% |
| sam | 15,010 | 11,565 | 10.2% |
| gleif | 1,840 | 1,840 | 1.6% |
| mergent | 1,045 | 1,045 | 0.9% |
| sec | 483 | 483 | 0.4% |

## Confidence Distribution

| Source | HIGH | MEDIUM | LOW |
|--------|------|--------|-----|
| 990 | 1,822 | 7,726 | 7,048 |
| crosswalk | 0 | 19,293 | 0 |
| gleif | 0 | 1,840 | 0 |
| mergent | 364 | 681 | 0 |
| nlrb | 0 | 13,031 | 4,485 |
| osha | 14,116 | 35,517 | 102,311 |
| sam | 5,685 | 2,064 | 7,261 |
| sec | 0 | 483 | 0 |
| whd | 5,718 | 9,453 | 14,793 |

## Top Match Methods

| Method | Tier | Count |
|--------|------|-------|
| STATE_NAICS_FUZZY | deterministic | 51,840 |
| FUZZY_NAME_STATE | probabilistic | 21,732 |
| NORMALIZED_NAME_STATE | deterministic | 18,295 |
| STREET_NUM_ZIP | deterministic | 17,586 |
| ADDRESS_CITY_STATE | deterministic | 16,606 |
| NAME_STATE_EXACT | deterministic | 15,524 |
| NAME_AGGRESSIVE_STATE | deterministic | 11,667 |
| CROSSWALK | deterministic | 10,688 |
| STATE_PREFIX5_FUZZY | deterministic | 8,994 |
| name_zip_exact | deterministic | 8,140 |
| FUZZY_TRIGRAM | probabilistic | 7,620 |
| USASPENDING_FUZZY_NAME_STATE | deterministic | 6,661 |
| CITY_STATE_FUZZY | deterministic | 6,291 |
| EXACT_NAME_STATE | deterministic | 6,256 |
| STRIPPED_FACILITY_MATCH | deterministic | 5,530 |
| name_state_exact | deterministic | 4,891 |
| NAME_STATE | deterministic | 3,742 |
| MERGENT_BRIDGE | deterministic | 3,586 |
| ZIP_FUZZY_NAICS | deterministic | 3,362 |
| zip_partial | deterministic | 3,349 |

## Baseline Check

- **osha**: 28.0% (baseline: 13.0%) -- PASS
- **whd**: 9.7% (baseline: 6.0%) -- PASS
- **990**: 6.7% (baseline: 2.0%) -- PASS