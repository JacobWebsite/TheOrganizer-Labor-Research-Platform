"""Create feedback_submissions table (beta onboarding feedback capture). Roadmap W8. [plumbing]

Beta testers submit free-text feedback from any page via the Feedback button.
Rows are monitored daily during soft launch (see RELEASE_CHECKLIST / W8 plan).
Idempotent: safe to re-run.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from db_config import get_connection


def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback_submissions (
            id SERIAL PRIMARY KEY,
            category VARCHAR(20) NOT NULL CHECK (category IN
                ('bug', 'confusing', 'data_issue', 'feature_request', 'praise', 'other')),
            message TEXT NOT NULL,
            page_url TEXT,
            employer_id TEXT,
            submitted_by VARCHAR(100),
            user_agent TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN
                ('new', 'triaged', 'resolved', 'wont_fix')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_submissions_created_at
        ON feedback_submissions(created_at DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_submissions_status
        ON feedback_submissions(status)
    """)
    print("feedback_submissions table created.")
    conn.close()


if __name__ == "__main__":
    main()
