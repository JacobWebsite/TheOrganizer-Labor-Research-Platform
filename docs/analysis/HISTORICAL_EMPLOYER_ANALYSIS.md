# Historical vs Current Employer Analysis

**Date:** 2026-02-15
**Table:** `f7_employers_deduped`
**Status:** Investigation complete, resolution pending

## Summary

The 52,760 historical employers added during Sprint 1's orphan fix are **not duplicates** of the 60,953 current employers. The dedup pipeline already consolidated same-name-same-state pairs. These are distinct entities -- mostly small, defunct bargaining units that once appeared in F7 filings but no longer do.

## Counts

| Category | Count |
|----------|-------|
| Total employers | 113,713 |
| Current (`is_historical = false`) | 60,953 |
| Historical (`is_historical = true`) | 52,760 |

## Overlap Analysis

| Match Type | Historical Matches | % |
|------------|-------------------|---|
| Exact name + state | 0 | 0% |
| Exact name only (different state) | 3,338 | 6.3% |
| Aggressive name + state | 4,942 | 9.4% |
| Aggressive name only (any state) | 10,501 | 19.9% |
| **No match at all** | **42,259** | **80.1%** |

The zero exact name+state matches confirm the dedup pipeline is working correctly.

The 4,942 aggressive-name+state matches (9.4%) are the closest thing to potential duplicates -- cases where normalized names (strip "Inc", "LLC", lowercase, etc.) match a current employer in the same state. These may be legitimate duplicates worth merging or related-but-distinct entities.

## Profile of Historical Employers

- **65.3%** flagged `potentially_defunct = 1`
- **76.9%** have only a single filing
- **65.3%** last filed before 2015
- **34.7%** last filed 2015-2019

Typical examples: small bargaining units (1-50 employees) from 2010-2019 -- "Parkview Care Center" (Buffalo MN, SEIU), "Bryant & Stratton College" (Rochester NY, UAW), "Arizona Central Painting" (Peoria AZ, IUPAT).

## External References

| Match Table | Historical Refs | Notes |
|-------------|----------------|-------|
| `osha_f7_matches` | 0 | Never matched |
| `whd_f7_matches` | 0 | Never matched |
| `national_990_f7_matches` | 0 | Never matched |
| `sam_f7_matches` | 0 | Never matched |
| `nlrb_participants` | 0 | Never matched |
| `mergent_employers` | 0 | Never matched |
| `usaspending_f7_matches` | 2,844 | Only external refs |
| `corporate_identifier_crosswalk` | 2,844 | Via USASpending |
| `mv_organizing_scorecard` | 0 | Not scored |

**94.6% of historical employers have zero external references anywhere in the database.** The core match pipeline (OSHA, WHD, 990, SAM, NLRB, Mergent) was only ever run against current employers.

## Resolution Options (TBD)

1. **Leave as-is** -- `is_historical` flag filters them from all active queries. No performance impact on scorecard or match pipeline.

2. **Archive to separate table** -- move the 47,818 unique historical employers to `f7_employers_historical` to reduce table size.

3. **Run matching against them** -- useful for historical trend analysis ("which employers lost their unions?"). Would add OSHA/WHD/990 context to 52K employers.

4. **Merge the 4,942 fuzzy matches** -- investigate aggressive-name+state overlaps and consolidate confirmed duplicates.

5. **Hybrid** -- merge confirmed duplicates (option 4), archive the rest (option 2), keep a `was_historical` flag for provenance.
