# Missing Unions Analysis (Task 1)

Date: 2026-02-18
Database: `olms_multiyear`
Scope: Research only. No updates were made to `f7_union_employer_relations`.

## Summary

- Distinct orphaned union file numbers in `f7_union_employer_relations`: **195**
- Total workers tied to orphaned file numbers: **92,627**
- Orphaned file numbers with a crosswalk entry: **30**
- Orphaned file numbers with crosswalk -> existing `unions_master.f_num`: **30**
- Workers tied to those 30 resolvable file numbers: **69,076**
- Remaining unresolved file numbers: **165**
- Workers tied to unresolved file numbers: **23,551**

## Crosswalk Findings

Crosswalk coverage is concentrated in a small number of high-worker file numbers (for example `12590`, `18001`, `15677`, `23547`).

Important caveat: several old file numbers map to **multiple** `matched_fnum` values in `f7_fnum_crosswalk` (one-to-many). Example old file numbers with multiple targets include:
- `12590` -> `512497, 526792, 528302, 540383, 543920`
- `18001` -> `32450, 42829, 51950, 542653, 67051`
- `23547` -> `516213, 521560, 544042`

This means an automatic UPDATE needs a deterministic tie-break rule (or manual review) before remapping.

## Top 20 Unresolved File Numbers (by workers)

| union_file_number | relation_count | total_workers |
|---|---:|---:|
| 26025 | 29 | 2,144 |
| 26087 | 2 | 1,249 |
| 47349 | 101 | 1,158 |
| 3775 | 1 | 1,100 |
| 9337 | 1 | 968 |
| 542767 | 1 | 900 |
| 541278 | 1 | 750 |
| 26220 | 1 | 700 |
| 517317 | 2 | 650 |
| 43723 | 1 | 610 |
| 28564 | 49 | 518 |
| 1923 | 4 | 516 |
| 23385 | 2 | 461 |
| 7760 | 4 | 459 |
| 7096 | 6 | 385 |
| 29595 | 1 | 365 |
| 508720 | 2 | 341 |
| 59976 | 2 | 334 |
| 58551 | 20 | 328 |
| 512199 | 10 | 301 |

## Suggested Categories for Unresolved Set

- **Merged/Reorganized locals**: likely where old file numbers were retired but no crosswalk row exists.
- **Dissolved/Inactivated locals**: historical relationships retained in F-7 relations but no current master record.
- **Data quality/ingest issues**: malformed or partial file numbers, or missing master load for specific years.
- **Unknown/manual review**: rows requiring lookup against OLMS source records.

## Recommendation

1. Resolve one-to-many crosswalk ambiguity first (tie-break policy).
2. Apply crosswalk remap for the 30 resolvable file numbers in a transaction.
3. Manually research top unresolved file numbers (table above) before further remaps.

---

## Phase C Resolution (2026-02-21)

### Actions Taken

1. **Crosswalk remaps (2026-02-18):** 29 one-to-one crosswalk cases remapped. Orphans: 195 -> 166, workers: 92,627 -> 61,743.

2. **CWA District 7 geographic devolution (2026-02-21):** Fnum 12590 (80 relations, 38,192 workers) resolved:
   - 38 relations remapped to 5 state-matched successor locals:
     - CO -> 512497, MN -> 526792, TX -> 528302, CA -> 543920, OR -> 540383
   - 42 relations in unmapped states (AL, OH, ND, AR, IN, WA, PA, CT, SD, MT, MO, NJ, UT, NE) kept under fnum 12590, which was added to `unions_master` as "Communications Workers of America District 7".

3. **Investigation of remaining 165 orphan fnums:** All 165 are ghost file numbers -- they appear in `f7_union_employer_relations` but have:
   - Zero entries in `lm_data` (no filing history)
   - Zero entries in `f7_fnum_crosswalk` (no forwarding)
   - Zero pg_trgm name matches (no names to match against)
   - These are categorized as DATA_QUALITY issues and logged in `union_fnum_resolution_log`.

### Results

| Metric | Before (2026-02-18) | After crosswalk | After Phase C |
|--------|--------------------:|----------------:|--------------:|
| Orphan fnums | 195 | 166 | 165 |
| Orphan rows | 824 | 577 | 497 |
| Orphan workers | 92,627 | 61,743 | 23,551 |

### Audit Trail

- Resolution log: `union_fnum_resolution_log` table (166 entries)
- Diagnostic script: `scripts/analysis/verify_missing_unions.py`
- Resolution script: `scripts/maintenance/resolve_missing_unions.py`
- Tests: `tests/test_missing_unions_resolution.py` (7 tests)

### Remaining Work

The 165 ghost fnums (23,551 workers) cannot be resolved programmatically. Options:
- **Manual OLMS lookup** for the top 20 by worker count (see table above)
- **Accept as data gap** -- these may be defunct locals from decades past with no digital records
- **Future data load** -- if OLMS provides a historical union registry, these could be resolved
