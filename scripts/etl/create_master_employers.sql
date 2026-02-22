-- Master Employer Schema (Wave 0 foundation)
-- Idempotent DDL only. Do not run automatically from Python scripts.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS master_employers (
    master_id BIGSERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    city TEXT,
    state CHAR(2),
    zip TEXT,
    naics VARCHAR(10),
    employee_count INTEGER,
    employee_count_source TEXT,
    ein TEXT,
    is_union BOOLEAN NOT NULL DEFAULT FALSE,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    is_federal_contractor BOOLEAN NOT NULL DEFAULT FALSE,
    is_nonprofit BOOLEAN NOT NULL DEFAULT FALSE,
    source_origin TEXT NOT NULL,
    data_quality_score NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_master_source_origin
        CHECK (source_origin IN ('f7', 'sam', 'mergent', 'osha', 'bmf', 'nlrb', 'sec', 'manual')),
    CONSTRAINT chk_master_data_quality_score
        CHECK (data_quality_score >= 0 AND data_quality_score <= 100),
    CONSTRAINT chk_master_employee_count
        CHECK (employee_count IS NULL OR employee_count >= 0)
);

CREATE TABLE IF NOT EXISTS master_employer_source_ids (
    master_id BIGINT NOT NULL REFERENCES master_employers(master_id) ON DELETE CASCADE,
    source_system TEXT NOT NULL,
    source_id TEXT NOT NULL,
    match_confidence NUMERIC(5,4),
    matched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (master_id, source_system, source_id),
    CONSTRAINT chk_master_source_system
        CHECK (source_system IN ('f7', 'sam', 'mergent', 'osha', 'bmf', 'nlrb', 'sec', 'gleif', '990', 'manual')),
    CONSTRAINT chk_master_match_confidence
        CHECK (match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1))
);

CREATE TABLE IF NOT EXISTS master_employer_merge_log (
    merge_id BIGSERIAL PRIMARY KEY,
    winner_master_id BIGINT NOT NULL REFERENCES master_employers(master_id),
    loser_master_id BIGINT NOT NULL REFERENCES master_employers(master_id),
    merge_reason TEXT NOT NULL,
    merged_by TEXT NOT NULL DEFAULT 'system',
    merged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_master_merge_not_self
        CHECK (winner_master_id <> loser_master_id)
);

-- Required indexes from task spec
CREATE INDEX IF NOT EXISTS idx_master_employers_ein
    ON master_employers (ein)
    WHERE ein IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_master_employers_state
    ON master_employers (state)
    WHERE state IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_master_employers_naics
    ON master_employers (naics)
    WHERE naics IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_master_employers_canonical_name_trgm
    ON master_employers USING gin (canonical_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_master_employers_source_origin
    ON master_employers (source_origin);

-- Operational indexes for joins/upserts in future seeding waves
CREATE INDEX IF NOT EXISTS idx_master_source_ids_system_source
    ON master_employer_source_ids (source_system, source_id);

CREATE INDEX IF NOT EXISTS idx_master_source_ids_master
    ON master_employer_source_ids (master_id);

CREATE INDEX IF NOT EXISTS idx_master_merge_log_winner
    ON master_employer_merge_log (winner_master_id);

CREATE INDEX IF NOT EXISTS idx_master_merge_log_loser
    ON master_employer_merge_log (loser_master_id);

-- Column comments
COMMENT ON TABLE master_employers IS
'Canonical employer universe across F-7, SAM, Mergent, BMF, OSHA, NLRB, and SEC.';
COMMENT ON COLUMN master_employers.master_id IS
'Synthetic primary key for stable joins across all source systems.';
COMMENT ON COLUMN master_employers.canonical_name IS
'Normalized preferred name for matching and deduplication.';
COMMENT ON COLUMN master_employers.display_name IS
'User-facing display name with original casing.';
COMMENT ON COLUMN master_employers.city IS
'Best available city from reconciled sources.';
COMMENT ON COLUMN master_employers.state IS
'Best available state code from reconciled sources.';
COMMENT ON COLUMN master_employers.zip IS
'Best available ZIP code from reconciled sources.';
COMMENT ON COLUMN master_employers.naics IS
'Best available NAICS industry code.';
COMMENT ON COLUMN master_employers.employee_count IS
'Best employee count estimate after source reconciliation.';
COMMENT ON COLUMN master_employers.employee_count_source IS
'Source used for employee_count (f7, sam, mergent, osha_estimate, model_estimate).';
COMMENT ON COLUMN master_employers.ein IS
'Employer identification number. Nullable and intentionally non-unique.';
COMMENT ON COLUMN master_employers.is_union IS
'TRUE when entity has a union relationship from F-7-derived universe.';
COMMENT ON COLUMN master_employers.is_public IS
'TRUE when linked to SEC/public company identifiers.';
COMMENT ON COLUMN master_employers.is_federal_contractor IS
'TRUE when linked to SAM.gov or federal award recipients.';
COMMENT ON COLUMN master_employers.is_nonprofit IS
'TRUE when classified as nonprofit through BMF/990 data.';
COMMENT ON COLUMN master_employers.source_origin IS
'First source that created the master row.';
COMMENT ON COLUMN master_employers.data_quality_score IS
'0-100 confidence score based on identifier completeness and source agreement.';
COMMENT ON COLUMN master_employers.created_at IS
'Record creation timestamp.';
COMMENT ON COLUMN master_employers.updated_at IS
'Last update timestamp.';

COMMENT ON TABLE master_employer_source_ids IS
'Maps each master employer to its source-system record IDs and confidence.';
COMMENT ON COLUMN master_employer_source_ids.source_system IS
'Source namespace (f7, sam, mergent, bmf, osha, nlrb, sec, etc.).';
COMMENT ON COLUMN master_employer_source_ids.source_id IS
'Raw source-system identifier for the mapped record.';
COMMENT ON COLUMN master_employer_source_ids.match_confidence IS
'0-1 confidence from deterministic/fuzzy/manual linkage.';

COMMENT ON TABLE master_employer_merge_log IS
'Audit trail of master-record merges for reproducibility and rollback.';
COMMENT ON COLUMN master_employer_merge_log.merge_reason IS
'Merge rationale (ein_match, name_dedup, manual, source_reconciliation, etc.).';
COMMENT ON COLUMN master_employer_merge_log.merged_by IS
'Actor performing merge (system or user identifier).';

-- Wave 0 seed: bootstrap canonical universe from F-7 deduped employers.
INSERT INTO master_employers (
    canonical_name,
    display_name,
    city,
    state,
    zip,
    naics,
    employee_count,
    employee_count_source,
    ein,
    is_union,
    is_public,
    is_federal_contractor,
    is_nonprofit,
    source_origin,
    data_quality_score
)
SELECT
    COALESCE(
        NULLIF(
            trim(
                regexp_replace(
                    lower(COALESCE(f.employer_name, '')),
                    '[^a-z0-9 ]',
                    ' ',
                    'g'
                )
            ),
            ''
        ),
        'unknown_' || f.employer_id::TEXT
    ) AS canonical_name,
    f.employer_name AS display_name,
    f.city,
    f.state,
    f.zip,
    f.naics,
    f.latest_unit_size AS employee_count,
    CASE WHEN f.latest_unit_size IS NOT NULL THEN 'f7' ELSE NULL END AS employee_count_source,
    NULL::TEXT AS ein,
    TRUE AS is_union,
    FALSE AS is_public,
    FALSE AS is_federal_contractor,
    FALSE AS is_nonprofit,
    'f7' AS source_origin,
    70.00 AS data_quality_score
FROM f7_employers_deduped f
WHERE f.employer_name IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM master_employers m
      WHERE m.source_origin = 'f7'
        AND m.display_name = f.employer_name
        AND COALESCE(m.city, '') = COALESCE(f.city, '')
        AND COALESCE(m.state, '') = COALESCE(f.state, '')
        AND COALESCE(m.zip, '') = COALESCE(f.zip, '')
  );

-- Wave 0 source-id mapping: attach F-7 employer_id to seeded rows.
INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
SELECT
    m.master_id,
    'f7' AS source_system,
    f.employer_id::TEXT AS source_id,
    1.0 AS match_confidence,
    NOW() AS matched_at
FROM f7_employers_deduped f
JOIN master_employers m
  ON m.source_origin = 'f7'
 AND m.display_name = f.employer_name
 AND COALESCE(m.city, '') = COALESCE(f.city, '')
 AND COALESCE(m.state, '') = COALESCE(f.state, '')
 AND COALESCE(m.zip, '') = COALESCE(f.zip, '')
WHERE NOT EXISTS (
    SELECT 1
    FROM master_employer_source_ids s
    WHERE s.master_id = m.master_id
      AND s.source_system = 'f7'
      AND s.source_id = f.employer_id::TEXT
);
