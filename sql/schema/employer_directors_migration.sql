-- 24Q-12 Board of Directors Coverage
-- Skeleton migration for parsing DEF14A proxy statements.
--
-- Source: SEC EDGAR DEF14A filings (one per public company per year). The
-- proxy lists every director with bio, committee assignments, other board
-- memberships, and total compensation. This is the canonical source for
-- Question 10 (Board of Directors) of the 24-Question framework.
--
-- The loader (scripts/etl/load_def14a_directors.py) reuses the SEC EDGAR
-- submissions JSON pattern from load_sec_exhibit21.py to discover the most
-- recent DEF14A per CIK, fetches the document, and extracts directors via
-- a sequence of parser strategies (ordered by hit rate):
--   1. HTML table with header rows like "Name", "Age", "Director Since"
--   2. Inline bullet list of "<name>, age <N>" patterns
--   3. Heuristic regex on prose mentioning "elected director"
--
-- Coverage caveat: not every public filer files a DEF14A every year (some
-- file 10-K-only or are exempt). About 60-70 percent of SEC filers should
-- have a recent DEF14A; the remainder will silently emit 0 directors and
-- be flagged as `def14a_not_found` in load_def14a_progress.

DROP TABLE IF EXISTS employer_directors CASCADE;

CREATE TABLE employer_directors (
    id                       SERIAL PRIMARY KEY,
    master_id                INTEGER REFERENCES master_employers(master_id) ON DELETE SET NULL,
    filing_cik               INTEGER NOT NULL,
    filing_accession_number  VARCHAR(20) NOT NULL,
    fiscal_year              SMALLINT,
    director_name            TEXT NOT NULL,
    name_norm                TEXT NOT NULL,
    age                      SMALLINT,
    position                 TEXT,                  -- "Chairman", "Lead Independent Director", etc.
    director_since_year      SMALLINT,
    primary_occupation       TEXT,                  -- self-described primary employment
    other_directorships      TEXT[],                -- other public boards (free-text array)
    is_independent           BOOLEAN,
    committees               TEXT[],                -- ['Audit', 'Compensation', 'Nominating']
    compensation_total       NUMERIC(12, 2),        -- total annual board compensation USD
    source_url               TEXT NOT NULL,
    extracted_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parse_strategy           VARCHAR(40),           -- which extractor produced this row
    UNIQUE (filing_accession_number, name_norm)
);

CREATE INDEX idx_employer_directors_master ON employer_directors(master_id);
CREATE INDEX idx_employer_directors_cik ON employer_directors(filing_cik);
CREATE INDEX idx_employer_directors_name_norm ON employer_directors USING gin (name_norm gin_trgm_ops);
CREATE INDEX idx_employer_directors_committees ON employer_directors USING gin (committees);

-- Progress / failure tracking, parallel to the Ex21 loader's CIK skip list.
CREATE TABLE IF NOT EXISTS load_def14a_progress (
    cik              INTEGER PRIMARY KEY,
    last_attempted   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status           VARCHAR(40) NOT NULL,  -- 'ok' | 'def14a_not_found' | 'parse_failed' | 'http_error'
    directors_found  INTEGER DEFAULT 0,
    notes            TEXT
);

-- Director interlock view (24Q-13). Materializes the "shared director"
-- relationship: any pair of CIKs that share a director by name_norm. Built
-- as a view rather than an MV so it stays current as employer_directors
-- grows. Promote to MV when row counts justify it (~10K+ interlocks).
--
-- Self-join uses `a.filing_cik < b.filing_cik` (not `<>`) so each interlock
-- pair appears exactly once -- otherwise COUNT(*) and any aggregate would
-- double-count A->B and B->A. (Codex 2026-05-03)
CREATE OR REPLACE VIEW director_interlocks AS
SELECT
    a.name_norm,
    a.director_name,
    a.master_id      AS master_id_a,
    b.master_id      AS master_id_b,
    a.filing_cik     AS cik_a,
    b.filing_cik     AS cik_b,
    a.fiscal_year    AS fiscal_year_a,
    b.fiscal_year    AS fiscal_year_b
FROM employer_directors a
JOIN employer_directors b
  ON a.name_norm = b.name_norm
 AND a.filing_cik < b.filing_cik
 AND a.master_id IS NOT NULL
 AND b.master_id IS NOT NULL;
