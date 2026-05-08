-- Centralized ETL run tracking table
CREATE TABLE IF NOT EXISTS data_refresh_log (
    id SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_count INTEGER,
    status TEXT NOT NULL CHECK (status IN ('success', 'partial', 'error')),
    error_message TEXT,
    script_path TEXT,
    duration_seconds NUMERIC(10,2)
);

CREATE INDEX IF NOT EXISTS idx_refresh_log_source
    ON data_refresh_log(source_name, loaded_at DESC);
