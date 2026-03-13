"""Create campaign_outcomes table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db_config import get_connection


def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_outcomes (
            id SERIAL PRIMARY KEY,
            employer_id TEXT NOT NULL,
            employer_name TEXT,
            outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('won', 'lost', 'abandoned', 'in_progress')),
            notes TEXT,
            reported_by VARCHAR(100),
            outcome_date DATE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_outcomes_employer
        ON campaign_outcomes(employer_id)
    """)
    print("campaign_outcomes table created.")
    conn.close()


if __name__ == "__main__":
    main()
