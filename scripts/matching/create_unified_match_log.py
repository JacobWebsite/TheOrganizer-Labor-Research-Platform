"""
Create the unified_match_log table and enhance match_runs.

This is the central audit trail for ALL matching operations.
Every match (past and future) gets recorded here with standardized
schema: source_system, match_tier, confidence_band, evidence JSONB.

Usage:
    py scripts/matching/create_unified_match_log.py
    py scripts/matching/create_unified_match_log.py --drop  # recreate
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


DDL = """
-- ============================================================================
-- unified_match_log: One table for ALL match results
-- ============================================================================
CREATE TABLE IF NOT EXISTS unified_match_log (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    source_system VARCHAR(50) NOT NULL,
    source_id TEXT NOT NULL,
    target_system VARCHAR(50) NOT NULL DEFAULT 'f7',
    target_id TEXT NOT NULL,
    match_method VARCHAR(100) NOT NULL,
    match_tier VARCHAR(20) NOT NULL,
    confidence_band VARCHAR(10) NOT NULL,
    confidence_score NUMERIC(5,3),
    evidence JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(run_id, source_system, source_id, target_id)
);

CREATE INDEX IF NOT EXISTS idx_uml_source_system
    ON unified_match_log(source_system);
CREATE INDEX IF NOT EXISTS idx_uml_target_id
    ON unified_match_log(target_id);
CREATE INDEX IF NOT EXISTS idx_uml_confidence_band
    ON unified_match_log(confidence_band);
CREATE INDEX IF NOT EXISTS idx_uml_status
    ON unified_match_log(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_uml_run_id
    ON unified_match_log(run_id);
CREATE INDEX IF NOT EXISTS idx_uml_source_id
    ON unified_match_log(source_system, source_id);

-- ============================================================================
-- Enhance match_runs with source_system + confidence counts
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'match_runs' AND column_name = 'source_system'
    ) THEN
        ALTER TABLE match_runs ADD COLUMN source_system VARCHAR(50);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'match_runs' AND column_name = 'method_type'
    ) THEN
        ALTER TABLE match_runs ADD COLUMN method_type VARCHAR(50);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'match_runs' AND column_name = 'high_count'
    ) THEN
        ALTER TABLE match_runs ADD COLUMN high_count INTEGER DEFAULT 0;
        ALTER TABLE match_runs ADD COLUMN medium_count INTEGER DEFAULT 0;
        ALTER TABLE match_runs ADD COLUMN low_count INTEGER DEFAULT 0;
    END IF;
END $$;

-- ============================================================================
-- historical_merge_candidates (for Block 7)
-- ============================================================================
CREATE TABLE IF NOT EXISTS historical_merge_candidates (
    id SERIAL PRIMARY KEY,
    historical_employer_id TEXT NOT NULL,
    current_employer_id TEXT NOT NULL,
    match_method VARCHAR(100) NOT NULL,
    confidence_score NUMERIC(5,3),
    evidence JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(historical_employer_id, current_employer_id)
);
"""


def main():
    parser = argparse.ArgumentParser(description="Create unified_match_log table")
    parser.add_argument("--drop", action="store_true", help="Drop and recreate tables")
    args = parser.parse_args()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if args.drop:
                print("Dropping existing tables...")
                cur.execute("DROP TABLE IF EXISTS unified_match_log CASCADE")
                cur.execute("DROP TABLE IF EXISTS historical_merge_candidates CASCADE")

            print("Creating unified_match_log table...")
            cur.execute(DDL)
            conn.commit()

            # Verify
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'unified_match_log'
                ORDER BY ordinal_position
            """)
            cols = cur.fetchall()
            print(f"\nunified_match_log created with {len(cols)} columns:")
            for col in cols:
                print(f"  {col[0]:25s} {col[1]}")

            cur.execute("SELECT COUNT(*) FROM unified_match_log")
            count = cur.fetchone()[0]
            print(f"\nRows: {count}")
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
