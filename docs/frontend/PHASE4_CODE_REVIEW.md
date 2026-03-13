# Phase 4 Code Review

Date: 2026-02-16  
Scope:
- `scripts/matching/adapters/sec_adapter_module.py`
- `scripts/matching/run_deterministic.py`
- `scripts/etl/download_bls_union_tables.py`
- `scripts/etl/parse_bls_union_tables.py`
- `scripts/etl/create_state_industry_estimates.py`
- `scripts/etl/fix_bls_schema.py`
- `scripts/etl/parse_oews_employment_matrix.py`

## Critical Issues (Must Fix)

1. **Destructive schema rebuilds in ETL paths**
- `scripts/etl/parse_bls_union_tables.py` and `scripts/etl/create_state_industry_estimates.py` use `DROP ... CASCADE` in normal runs.
- Risk: accidental deletion of dependent views/objects and hard-to-recover drift.
- Fix: migrate to `CREATE TABLE IF NOT EXISTS` + `TRUNCATE`/`UPSERT`, and explicit drop of known views only when needed.
- Estimate: **1.5-2.5 hours**

2. **Precision mismatch risk in BLS parser**
- `parse_bls_union_tables.py` parses floats but historically created INTEGER count columns (later patched by `fix_bls_schema.py`).
- Risk: silent precision truncation if parser runs before schema-fix script.
- Fix: make parser create the correct NUMERIC schema directly, remove dependency on post-fix scripts.
- Estimate: **1 hour**

3. **Brittle HTML parsing assumptions**
- Fixed column offsets and exact `'INDUSTRY'` marker make parser fragile to upstream BLS structure shifts.
- Risk: partial loads with no hard failure.
- Fix: header-driven column detection, minimum-row sanity checks, and fail-fast thresholds.
- Estimate: **2-3 hours**

## Suggested Improvements (Ranked)

1. **Normalize DB access patterns in SEC adapter module**
- `sec_adapter_module.py` uses positional tuple access and dynamic `LIMIT` string concatenation.
- Improve with `RealDictCursor` and fully parameterized SQL for consistency and safety hardening.
- Estimate: **45-60 minutes**

2. **Downloader resiliency**
- Add request timeout/retry/backoff and failure summary in `download_bls_union_tables.py`.
- Estimate: **45 minutes**

3. **Centralize repeated constants/mappings**
- Industry maps, null tokens, and year constants are duplicated/hardcoded.
- Move to shared module and parameterize year/paths.
- Estimate: **1-1.5 hours**

4. **Remove unused imports and encoding artifacts**
- `parse_bls_union_tables.py` has unused imports (`re`, `pandas`) and some mojibake text in console output.
- Estimate: **20-30 minutes**

5. **Index tuning for heavy read paths**
- Validate composite indexes for frequent access patterns in `unified_match_log` and OEWS matrix queries.
- Estimate: **1-2 hours** including `EXPLAIN ANALYZE`.

## Code Quality Score

**7.1 / 10**

Rationale:
- Good progress on broad ETL coverage and idempotent loading in OEWS.
- Main deductions are for parser fragility, schema-destructive operations, and uneven data-access conventions across modules.
