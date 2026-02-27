"""
Create the research_score_enhancements table.

This table stores scorecard factor scores derived from research agent dossiers,
enabling a feedback loop from deep-dive research back into the unified scorecard.

Two paths:
  - Path A (is_union_reference=TRUE): Enriches the Gower reference pool.
    When a union employer (F7) is researched, extracted features feed into
    mv_employer_features for better similarity comparisons.
  - Path B (is_union_reference=FALSE): Directly enhances a non-union employer's
    scorecard factors via LEFT JOIN in mv_unified_scorecard.

Usage:
  py scripts/scoring/create_research_enhancements.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS research_score_enhancements (
    id                  SERIAL PRIMARY KEY,
    employer_id         TEXT NOT NULL,
    run_id              INTEGER NOT NULL REFERENCES research_runs(id),
    run_quality         NUMERIC(4,2),

    -- Which path this enhancement serves
    is_union_reference  BOOLEAN DEFAULT FALSE,

    -- Factor scores (NULL = no research data for this factor)
    -- These use the same formulas as build_unified_scorecard.py
    score_osha          NUMERIC(4,2),
    score_nlrb          NUMERIC(4,2),
    score_whd           NUMERIC(4,2),
    score_contracts     NUMERIC(4,2),
    score_financial     NUMERIC(4,2),
    score_size          NUMERIC(4,2),
    score_stability     NUMERIC(4,2),
    score_anger         NUMERIC(4,2),

    -- Raw extracted values (for audit trail + Gower feature refresh)
    osha_violations_found       INTEGER,
    osha_serious_found          INTEGER,
    osha_penalty_total_found    NUMERIC,
    nlrb_elections_found        INTEGER,
    nlrb_ulp_found              INTEGER,
    whd_cases_found             INTEGER,
    employee_count_found        INTEGER,
    revenue_found               BIGINT,
    federal_obligations_found   BIGINT,
    year_founded_found          INTEGER,
    naics_found                 VARCHAR(10),
    turnover_rate_found         NUMERIC(4,2),
    sentiment_score_found       NUMERIC(4,2),
    revenue_per_employee_found  NUMERIC,

    -- Assessment (display only -- not scored)
    recommended_approach    TEXT,
    campaign_strengths      JSONB,
    campaign_challenges     JSONB,
    source_contradictions   JSONB,
    financial_trend         TEXT,

    -- Metadata
    confidence_avg  NUMERIC(3,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT uq_rse_employer UNIQUE (employer_id)
);
"""

INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_rse_employer ON research_score_enhancements(employer_id)",
    "CREATE INDEX IF NOT EXISTS idx_rse_union_ref ON research_score_enhancements(is_union_reference) WHERE is_union_reference = TRUE",
    "CREATE INDEX IF NOT EXISTS idx_rse_run_id ON research_score_enhancements(run_id)",
]


def create_table(conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        cur = conn.cursor()
        cur.execute(TABLE_SQL)
        for stmt in INDEX_SQL:
            cur.execute(stmt)
        conn.commit()
        print("Created research_score_enhancements table + indexes.")

        cur.execute("SELECT COUNT(*) FROM research_score_enhancements")
        count = cur.fetchone()[0]
        print(f"  Current rows: {count}")
    finally:
        if close_conn:
            conn.close()


if __name__ == "__main__":
    create_table()
