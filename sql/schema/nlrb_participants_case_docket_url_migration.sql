-- ============================================================================
-- NLRB PARTICIPANTS: ADD case_docket_url COLUMN
-- Created: 2026-04-24
-- Purpose: Roughly 43% of nlrb_participants rows have NULL city/state, so
--          the Starbucks family-rollup's "recent elections" table shows blank
--          addresses. Store-level addresses actually live in the per-case
--          NLRB docket PDFs, not in the bulk-downloaded participants table.
--
--          This migration adds a computed `case_docket_url` column so the
--          frontend can at least LINK OUT to the NLRB case page for any
--          election or ULP, even when we don't have the address ourselves.
--
--          The URL template comes from the NLRB public case search:
--          https://www.nlrb.gov/case/{case_number}
--
--          The column is stored (not generated) so downstream readers don't
--          pay the concatenation cost per query. We populate it in one UPDATE
--          and leave a BEFORE INSERT trigger for future inserts.
-- ============================================================================

-- 1. Add the column (idempotent)
ALTER TABLE nlrb_participants
    ADD COLUMN IF NOT EXISTS case_docket_url TEXT;

-- 2. Backfill for existing rows (skip rows that already have a value)
UPDATE nlrb_participants
   SET case_docket_url = 'https://www.nlrb.gov/case/' || case_number
 WHERE case_docket_url IS NULL
   AND case_number IS NOT NULL;

-- 3. Trigger to auto-populate on future inserts (nightly pull, bulk sync, etc.)
CREATE OR REPLACE FUNCTION _set_nlrb_participants_docket_url()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.case_docket_url IS NULL AND NEW.case_number IS NOT NULL THEN
        NEW.case_docket_url := 'https://www.nlrb.gov/case/' || NEW.case_number;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_nlrb_participants_docket_url ON nlrb_participants;
CREATE TRIGGER trg_set_nlrb_participants_docket_url
    BEFORE INSERT OR UPDATE ON nlrb_participants
    FOR EACH ROW
    EXECUTE FUNCTION _set_nlrb_participants_docket_url();

-- 4. Helpful partial index for quick "has docket URL" filters. Zero null-row cost.
CREATE INDEX IF NOT EXISTS idx_nlrb_participants_docket_url
    ON nlrb_participants (case_number)
    WHERE case_docket_url IS NOT NULL;
