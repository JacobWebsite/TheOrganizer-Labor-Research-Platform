"""
Phase 5.5: Create propensity model database tables.

Two tables:
  1. ml_model_versions - tracks trained model metadata
  2. ml_election_propensity_scores - per-employer propensity scores

Run: py scripts/ml/create_propensity_tables.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


ML_MODEL_VERSIONS_DDL = """
CREATE TABLE IF NOT EXISTS ml_model_versions (
    model_version_id  SERIAL PRIMARY KEY,
    model_name        VARCHAR(50) NOT NULL,
    version_string    VARCHAR(20) NOT NULL,
    model_type        VARCHAR(30) NOT NULL,
    training_date     TIMESTAMPTZ DEFAULT NOW(),
    training_rows     INTEGER,
    test_rows         INTEGER,
    test_auc          NUMERIC(5,4),
    test_brier_score  NUMERIC(5,4),
    calibration_error NUMERIC(5,4),
    feature_list      JSONB NOT NULL,
    parameters        JSONB NOT NULL,
    feature_importance JSONB,
    score_stats       JSONB,
    artifact_path     TEXT,
    is_active         BOOLEAN DEFAULT FALSE,
    notes             TEXT
)
"""

ML_MODEL_VERSIONS_UNIQUE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_model_active
ON ml_model_versions (model_name) WHERE is_active = TRUE
"""

ML_PROPENSITY_SCORES_DDL = """
CREATE TABLE IF NOT EXISTS ml_election_propensity_scores (
    id                SERIAL PRIMARY KEY,
    employer_id       TEXT NOT NULL,
    establishment_id  TEXT,
    propensity_score  NUMERIC(5,4) NOT NULL,
    confidence_band   VARCHAR(10) NOT NULL,
    model_name        VARCHAR(50) NOT NULL,
    model_version_id  INTEGER REFERENCES ml_model_versions(model_version_id),
    feature_values    JSONB,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (employer_id, model_name)
)
"""

ML_PROPENSITY_SCORES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_propensity_employer ON ml_election_propensity_scores(employer_id)",
    "CREATE INDEX IF NOT EXISTS idx_propensity_estab ON ml_election_propensity_scores(establishment_id)",
    "CREATE INDEX IF NOT EXISTS idx_propensity_model ON ml_election_propensity_scores(model_name)",
    "CREATE INDEX IF NOT EXISTS idx_propensity_score ON ml_election_propensity_scores(propensity_score)",
]


def create_tables(conn):
    cur = conn.cursor()

    print("Creating ml_model_versions...")
    cur.execute(ML_MODEL_VERSIONS_DDL)
    cur.execute(ML_MODEL_VERSIONS_UNIQUE_IDX)
    conn.commit()

    print("Creating ml_election_propensity_scores...")
    cur.execute(ML_PROPENSITY_SCORES_DDL)
    for idx_sql in ML_PROPENSITY_SCORES_INDEXES:
        cur.execute(idx_sql)
    conn.commit()

    # Verify
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name IN ('ml_model_versions', 'ml_election_propensity_scores')
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"  Created tables: {tables}")
    return tables


def main():
    conn = get_connection()
    try:
        tables = create_tables(conn)
        assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}"
        print("DONE: Propensity tables created.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
