# Session: Mergent Bulk Import (2026-03-02)

## What We Did

### 1. Built `import_mergent.py`
- Reads Mergent xlsx files (disguised as .csv) from any directory
- Normalizes: EIN (zero-padded 9-digit), state (full name -> 2-letter), employee count (strip commas), zip (zero-pad)
- EIN merge on import: if EIN matches existing record, enriches NULL fields instead of inserting duplicate
- Tracks per-file progress in `mergent_import_progress` table (idempotent -- skips already-imported files)
- Supports `--dir`, `--file`, `--status` flags

### 2. Imported 88 Files (176,000 rows) in 3 Batches
- **Batch 1:** `all companies mergent/` -- 36 files, 72,000 rows
- **Batch 2:** `all companies 37_63/` -- 27 files, 54,000 rows
- **Batch 3:** `all companies 64_88/` -- 25 files, 50,000 rows
- Files contain heavy internal duplication (~62% of rows are duplicates across files within a batch)

### 3. Ran Dedup Pipeline After Each Batch
- **Cumulative merges:** Phase 1 (EIN) ~495, Phase 2 (Name+State exact) ~59k, Phase 3 (fuzzy) ~2.5k
- Name+State exact is 93%+ of all dedup merges

### 4. Cumulative Results
- **DB before:** 4,533,068 records (62,550 pre-existing mergent)
- **DB after:** 4,541,146 records (72,342 mergent)
- **Tier impact (cumulative):** 61-80 +13.3%, 41-60 +7.8%, 21-40 +1.6%, 0-20 +0.6%
- **Cross-source links:** ~20k mergent records (28.8%) linked to form5500, BMF, CorpWatch, OSHA, PPP, WHD, NLRB
- **Enrichment:** ~5k EINs, ~68k employee counts, ~67k NAICS codes contributed

### 5. Diminishing Returns Observed (Batch 3)
- Batch 3 (64-88) added 2,576 net records, ALL in 0-20 tier
- Easy cross-source matches (OSHA, WHD, NLRB, F7) were exhausted in batches 1-2
- Later batches are mostly smaller/less-regulated companies only in Mergent
- 5,857 absorbed by SAM but those SAM records were themselves 0-20

### 6. Key Finding: Score vs Data Richness Gap
- **Mergent 0-20 records:** 95% have employee count, 100% NAICS, 47.7% EIN, 100% city/state/zip
- **Non-mergent 0-20 records:** 0.1% employee count, 52% NAICS, 0% EIN, ~90% city/state/zip
- Quality score measures cross-source linkage count, NOT actual data completeness
- Mergent records are far more actionable despite same quality tier

### 7. Known Bug: Missing source_ids
- `import_mergent.py` does NOT create `master_employer_source_ids` rows for new inserts
- New mergent records have 0 source_ids, Phase 4 scores them 10-20 max (just EIN/emp bonuses)
- When mergent is absorbed by another source, the loser's source_ids are deleted, so winner stays at 1 source
- **Fix needed:** Insert `source_system='mergent'` into `master_employer_source_ids` during import

## Lessons Learned
1. Mergent files are xlsx despite .csv extension -- must copy to .xlsx temp file for openpyxl
2. Heavy duplication within Mergent batches (many files contain overlapping records)
3. `--resume` on dedup phases 1-3 does NOT pick up new records (cursor already past them). Must run fresh. Phase 4 resume works fine (processes by ascending master_id).
4. Name+State exact matching (Phase 2) is 93% of all dedup merges -- far more effective than EIN matching for this dataset
5. Lock timeout errors when chaining dedup phases with `&&` -- run phases separately
6. Full dedup takes ~47 min for 4.5M records; incremental (phases 1-3 fresh + phase 4 resume) takes ~20 min
7. Diminishing returns after first 2 batches for cross-source linking; value shifts to data enrichment

## Commands for Next Batch
```bash
# Import new files
py import_mergent.py --dir "all companies NEXT_BATCH/"

# Check progress
py import_mergent.py --status

# Dedup (run each separately, not chained)
py scripts/etl/dedup_master_employers.py --phase 1 --batch-size 1000
py scripts/etl/dedup_master_employers.py --phase 2 --batch-size 1000
py scripts/etl/dedup_master_employers.py --phase 3 --batch-size 1000 --min-name-sim 0.85
py scripts/etl/dedup_master_employers.py --phase 4 --resume --batch-size 1000
```

## Universe Tracking
- Total Mergent universe: 1,744,929 companies
- Loaded: 176,000 (10.09%)
- Remaining: 1,568,929 (784 batches of 2,000)
