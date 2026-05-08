-- ============================================================================
-- RESEARCH RUNS: CRITIQUE RESULT + TOKEN ACCOUNTING MIGRATION
-- Created: 2026-04-24
-- Purpose: Adds the columns that `scripts/research/agent.py::_update_run`
--          writes to, but that no checked-in migration has ever created.
--
--          These columns already exist on the live production database
--          (added ad-hoc during previous sessions), so this migration is a
--          no-op there thanks to IF NOT EXISTS. On a fresh environment
--          built from repo SQL, it ensures the agent's completion write
--          (agent.py:~1845) doesn't fail with a "column does not exist"
--          error.
--
--          Also creates supporting indexes for cost / token reporting.
-- ============================================================================

-- 1. Columns the iterative critique loop writes (2026-04-21)
ALTER TABLE research_runs
    ADD COLUMN IF NOT EXISTS critique_result   JSONB,         -- {rounds: [...], final_assessment: str}
    ADD COLUMN IF NOT EXISTS total_input_tokens  INTEGER,     -- accumulated across Gemini calls
    ADD COLUMN IF NOT EXISTS total_output_tokens INTEGER,     -- accumulated across Gemini calls
    ADD COLUMN IF NOT EXISTS retry_count         INTEGER DEFAULT 0;  -- per-round retries

-- 2. Helpful index for token-cost rollups by day / company / status
CREATE INDEX IF NOT EXISTS idx_research_runs_completed_at
    ON research_runs (completed_at)
    WHERE status = 'completed';

-- 3. Backfill note: existing completed rows have NULL in the new columns
--    because they predate the instrumentation. That's fine -- downstream
--    readers already handle NULL via COALESCE. No DML needed here.
