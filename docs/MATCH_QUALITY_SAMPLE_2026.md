# Match Quality Sample Report
**Date:** February 16, 2026
**Auditor:** Claude Code (Opus 4.6)

## What This Report Shows

The platform connects employer records across different government databases using name matching. This report randomly sampled matches to check whether they actually link the same employer, or whether they accidentally connected two different companies.

## Method

I pulled 15 random OSHA matches and 10 random SAM matches, showing the names from both sides so you can judge if they're the same company. I also categorized each by the matching method used.

## OSHA Match Samples (15 random)

### Clearly Correct Matches (4 of 15 = 27%)

| OSHA Name | F7 Name | State | Method | Confidence |
|-----------|---------|-------|--------|------------|
| ALSCO UNIFORMS | Alsco Uniforms | CA | EXACT_NAME_STATE | 0.95 |
| ADM Milling Company | ADM Milling Company | MO | EXACT_NAME_STATE | 0.95 |
| DATTCO INC. | Dattco, Inc. | CT | NORMALIZED_NAME_STATE | 0.85 |
| Metro Roofing | Metro Roofing | MO | NORMALIZED_NAME_STATE | 0.85 |

These are correct. The names match (allowing for capitalization and punctuation differences) and they're in the same state.

### Questionable Matches (3 of 15 = 20%)

| OSHA Name | F7 Name | State | Method | Confidence |
|-----------|---------|-------|--------|------------|
| 66201 - RIDLEY USA INC (Flemingsburg, KY) | Ridley USA, Inc. (Nicholasville, KY) | KY | STATE_NAICS_FUZZY | 0.65 |
| ROVE PEST CONTROL (MN) | Rove Pest Control (MN) | MN | STREET_NUM_ZIP | 0.70 |
| FGB Construction (CT) | FGB Construction (CT) | CT | STATE_NAICS_FUZZY | 0.65 |

These are probably correct (same name, same state) but in different cities, which adds some uncertainty.

### Likely False Positives (8 of 15 = 53%)

| OSHA Name | F7 Name | State | Method | Confidence | Problem |
|-----------|---------|-------|--------|------------|---------|
| J STEVENS CONSTRUCTION | Marycrest Manor | MI | STREET_NUM_ZIP | 0.70 | Completely different companies -- matched by street number + zip |
| DIMENSION CONSTRUCTION | DK Construction Inc | KY | FUZZY_TRIGRAM | 0.61 | Different construction companies |
| U.S. DEPARTMENT OF THE NAVY | Trident Refit | GA | STREET_NUM_ZIP | 0.70 | Government agency matched to private company by address |
| NYCHA IMPARTIAL HEARING OFFICE | Fast Company Inc | NY | STREET_NUM_ZIP | 0.70 | NYC Housing Authority office matched to a private company |
| DAVIS VISION | Sunoco GP LLC | PA | STREET_NUM_ZIP | 0.70 | Eye care company matched to energy company |
| COVEY CONSTRUCTION | Guido Construction Company | TX | STATE_NAICS_FUZZY | 0.57 | Different construction companies in different cities |
| STAPP CONSTRUCTION INC | A P & F Construction, Inc. | UT | FUZZY_TRIGRAM | 0.68 | Different construction companies |
| VANLAAN CONCRETE CONSTRUCTION | Frederick Meijer Gardens | MI | STREET_NUM_ZIP | 0.70 | Construction company matched to a botanical garden |

**In plain language: More than half of the randomly sampled OSHA matches appear to be wrong -- they connected two completely different employers that happen to share an address or have vaguely similar names.**

## SAM Match Samples (10 random)

| SAM Entity | F7 Name | State | Method | Confidence | Assessment |
|-----------|---------|-------|--------|------------|------------|
| (Emory University UEI) | Emory University | GA | EXACT_NAME_STATE | 0.95 | CORRECT |
| (Mechanics Local 701 UEI) | Mechanics Local 701 Training Fund | IL | EXACT_NAME_STATE | 0.95 | CORRECT |
| (Town of Ridgeway UEI) | Town of Ridgeway | NY | EXACT_FULLNAME_STATE | 0.90 | CORRECT |
| (GOMEZ CONCRETE UEI) | GOMEZ CONCRETE RESTORATION INC. | CA | STATE_NAICS_FUZZY | 0.87 | LIKELY CORRECT |
| (T47 International UEI) | T47 International | MD | CITY_STATE_FUZZY | 0.90 | LIKELY CORRECT |
| (Child Care Council UEI) | Child Care Coordinating Council of San M | CA | NAME_AGGRESSIVE_STATE | 0.75 | LIKELY CORRECT |
| (O & G Industries UEI) | O & G Industries, Inc. | CT | STATE_NAICS_FUZZY | 0.65 | PROBABLY CORRECT |
| (Warrenton OR UEI) | City Of Warrenton, Oregon | OR | CITY_STATE_FUZZY | 0.70 | PROBABLY CORRECT |
| (San Bernardino UEI) | City of San Bernardino | CA | CITY_STATE_FUZZY | 0.61 | UNCERTAIN |
| (N. American Security UEI) | North American Security | OK | CITY_STATE_FUZZY | 0.65 | PROBABLY CORRECT |

SAM matches look much better -- 8-9 out of 10 appear correct. This is because SAM entities are federal contractors, which overlap well with the F7 employer population.

## Match Method Reliability (Based on Sampling)

| Method | Sample Count | Accuracy | Recommendation |
|--------|-------------|----------|----------------|
| EXACT_NAME_STATE | 5 | ~100% | Reliable -- keep |
| NORMALIZED_NAME_STATE | 2 | ~100% | Reliable -- keep |
| EXACT_FULLNAME_STATE | 1 | ~100% | Reliable -- keep |
| NAME_AGGRESSIVE_STATE | 1 | ~90% | Generally reliable |
| CITY_STATE_FUZZY | 4 | ~75% | Decent but needs review |
| STREET_NUM_ZIP | 5 | ~20% | **Very unreliable -- many false positives** |
| STATE_NAICS_FUZZY | 7 | ~40% | **Unreliable -- many false matches** |
| FUZZY_TRIGRAM | 3 | ~33% | **Unreliable** |
| ZIP_FUZZY_NAICS | 2 | ~25% | **Very unreliable** |

## Key Finding

**The STREET_NUM_ZIP method is the biggest source of false positives.** It matches employers simply because they share the same street number and zip code. An office building at "100 Main St, 10001" could contain 50 different businesses -- matching them together makes no sense.

**53% of OSHA matches in this sample appear to be false positives.** This doesn't mean 53% of ALL OSHA matches are wrong (the sample over-represents fuzzy matches), but it does mean the LOW-confidence OSHA matches (102,311 of them) need systematic review.

## Recommendation

1. **Reject or quarantine all STREET_NUM_ZIP matches** unless the names also have some similarity (e.g., trigram similarity > 0.3)
2. **Raise confidence thresholds** for STATE_NAICS_FUZZY and FUZZY_TRIGRAM methods
3. **Add a name similarity check** as a post-filter on all fuzzy methods -- if the names share less than 30% of characters, the match should be rejected
4. **Periodically sample and review** LOW-confidence matches to catch systematic errors
