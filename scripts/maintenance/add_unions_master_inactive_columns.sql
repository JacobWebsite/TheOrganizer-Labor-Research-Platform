-- ============================================================
-- Migration: add unions_master.term_date column
-- ============================================================
-- Purpose:
--   The is_likely_inactive flag already exists on unions_master (added by
--   scripts/etl/flag_stale_unions.py). This migration adds the companion
--   term_date column used by the 2026-05-12 backfill of 138 OLMS-terminated
--   f_nums that legacy F-7 filings reference but unions_master never had.
--
-- Both statements are guarded with IF NOT EXISTS / IF EXISTS so the migration
-- is idempotent and safe to re-run.
--
-- Background:
--   - is_likely_inactive: BOOLEAN, default FALSE. Already present in DB
--     (added by flag_stale_unions.py). Re-declared here for documentation.
--   - term_date: DATE, NULL. Date the union terminated per OLMS public
--     records (POST /olpdr/GetFilerListServlet termDate millis -> DATE).
--     NULL for active unions; populated only for backfilled inactive rows.
--
-- Related:
--   - Investigation: docs/scratch/138_unresolved_f_nums_investigation_2026_05_12.md
--   - Backfill script: scripts/etl/backfill_terminated_fnums_unions_master.py
--   - Open Problem: vault/Open Problems/138 Unresolved Union File Numbers.md
-- ============================================================

ALTER TABLE unions_master
    ADD COLUMN IF NOT EXISTS is_likely_inactive BOOLEAN DEFAULT FALSE;

ALTER TABLE unions_master
    ADD COLUMN IF NOT EXISTS term_date DATE;

-- Partial index helps the "active unions only" filter on the union endpoint.
CREATE INDEX IF NOT EXISTS idx_unions_master_inactive
    ON unions_master (is_likely_inactive)
    WHERE is_likely_inactive = TRUE;
