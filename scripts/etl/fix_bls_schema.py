#!/usr/bin/env python3
"""
Fix BLS union density tables based on code review feedback.

Changes:
1. INTEGER to NUMERIC(12,1) for employment/member counts (preserve BLS precision)
2. Add foreign keys for referential integrity
3. Add updated_at timestamps
4. Change confidence from VARCHAR to BOOLEAN (is_estimated)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("Fixing BLS union density schema...")
    print("=" * 60)

    # 1. Fix precision - change INTEGER to NUMERIC(12,1)
    print("\n1. Fixing precision (INTEGER to NUMERIC)...")

    cur.execute("""
        -- bls_national_industry_density
        ALTER TABLE bls_national_industry_density
        ALTER COLUMN total_employed_thousands TYPE NUMERIC(12,1),
        ALTER COLUMN union_members_thousands TYPE NUMERIC(12,1),
        ALTER COLUMN represented_thousands TYPE NUMERIC(12,1);
    """)

    cur.execute("""
        -- bls_state_density
        ALTER TABLE bls_state_density
        ALTER COLUMN total_employed_thousands TYPE NUMERIC(12,1),
        ALTER COLUMN union_members_thousands TYPE NUMERIC(12,1),
        ALTER COLUMN represented_thousands TYPE NUMERIC(12,1);
    """)

    print("  OK - Changed count columns to NUMERIC(12,1)")

    # 2. Add updated_at timestamp to estimates table
    print("\n2. Adding updated_at timestamp...")

    cur.execute("""
        ALTER TABLE estimated_state_industry_density
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();
    """)

    cur.execute("""
        UPDATE estimated_state_industry_density
        SET updated_at = NOW()
        WHERE updated_at IS NULL;
    """)

    print("  OK - Added updated_at timestamp")

    # 3. Change confidence from VARCHAR to BOOLEAN
    print("\n3. Changing confidence to is_estimated boolean...")

    cur.execute("""
        ALTER TABLE estimated_state_industry_density
        ADD COLUMN IF NOT EXISTS is_estimated BOOLEAN DEFAULT TRUE;
    """)

    cur.execute("""
        UPDATE estimated_state_industry_density
        SET is_estimated = TRUE;
    """)

    # Don't drop old column yet - let it coexist for safety
    print("  OK - Added is_estimated boolean (old confidence column preserved)")

    # 4. Add foreign keys
    print("\n4. Adding foreign key constraints...")

    # Check if data exists before adding constraints
    cur.execute("""
        SELECT COUNT(*)
        FROM estimated_state_industry_density e
        LEFT JOIN bls_national_industry_density n
            ON e.year = n.year
            AND e.industry_code = n.industry_code
        WHERE n.year IS NULL
    """)
    orphan_industry = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM estimated_state_industry_density e
        LEFT JOIN bls_state_density s
            ON e.year = s.year
            AND e.state = s.state
        WHERE s.year IS NULL
    """)
    orphan_state = cur.fetchone()[0]

    if orphan_industry > 0:
        print(f"  WARNING: {orphan_industry} estimates have no matching national industry record")
        print("  Skipping foreign key to bls_national_industry_density")
    else:
        cur.execute("""
            ALTER TABLE estimated_state_industry_density
            DROP CONSTRAINT IF EXISTS fk_estimated_national_industry;

            ALTER TABLE estimated_state_industry_density
            ADD CONSTRAINT fk_estimated_national_industry
            FOREIGN KEY (year, industry_code)
            REFERENCES bls_national_industry_density(year, industry_code)
            ON DELETE CASCADE;
        """)
        print("  OK - Added FK to bls_national_industry_density")

    if orphan_state > 0:
        print(f"  WARNING: {orphan_state} estimates have no matching state record")
        print("  Skipping foreign key to bls_state_density")
    else:
        cur.execute("""
            ALTER TABLE estimated_state_industry_density
            DROP CONSTRAINT IF EXISTS fk_estimated_state;

            ALTER TABLE estimated_state_industry_density
            ADD CONSTRAINT fk_estimated_state
            FOREIGN KEY (year, state)
            REFERENCES bls_state_density(year, state)
            ON DELETE CASCADE;
        """)
        print("  OK - Added FK to bls_state_density")

    conn.commit()

    print("\n" + "=" * 60)
    print("Schema fixes complete")

    # Print summary
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(updated_at) as with_timestamp,
            COUNT(is_estimated) as with_boolean
        FROM estimated_state_industry_density
    """)
    stats = cur.fetchone()

    print(f"\nEstimates table: {stats[0]} rows")
    print(f"  With updated_at: {stats[1]}")
    print(f"  With is_estimated: {stats[2]}")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
