# I5 - Name Similarity Floor Validation (0.80)

Date: 2026-02-23  
DB: `olms_multiyear` (`postgres`)

## Question
Validate the `0.80` name similarity floor using 100 random OSHA Splink matches from `unified_match_log` where:
- `match_method='FUZZY_SPLINK_ADAPTIVE'`
- `source_system='osha'`
- score from `evidence->>'name_similarity'`

## Findings
1. Active OSHA adaptive-fuzzy pool already starts at 0.80:
- Pool size: `4,774`
- min/25th/50th/75th/max similarity: `0.800 / 0.814 / 0.839 / 0.880 / 1.000`

2. 100-row random sample review at threshold:
- At `>=0.80`: sample kept = `100/100` (because sampled pool is already floor-filtered)
- Around 0.80, many matches are plausible but noisy (construction/generic token collisions).

3. Threshold effect by count in active pool:
- `>=0.80`: `4,774`
- `>=0.85`: `2,011`

Raising floor to `0.85` would remove ~58% of currently active adaptive fuzzy OSHA matches.

## Decision Check
- `0.80` remains the best floor for recall/precision balance in current pipeline.
- `0.85` appears overly strict given large volume drop.

## Implementation Evidence
- Matcher supports configurable floor via `MATCH_MIN_NAME_SIM` in `scripts/matching/deterministic_matcher.py`.
- Existing maintenance script `scripts/maintenance/reject_stale_osha.py` enforces rejecting active rows `<0.80`.

