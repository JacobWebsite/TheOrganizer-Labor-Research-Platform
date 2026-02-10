"""
Phase 2: Scorecard Quick Wins - Create Reference Tables

Creates three reference tables used by the upgraded scoring system:
1. ref_osha_industry_averages - OSHA violation rates by NAICS (2-digit and 4-digit)
2. ref_rtw_states - Right-to-work state list
3. ref_nlrb_state_win_rates - NLRB election win rates by state (2020+)

Run: py scripts/scoring/create_scorecard_reference_tables.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection
import psycopg2.extras

def get_conn():
    return get_connection(cursor_factory=psycopg2.extras.RealDictCursor)

def create_osha_industry_averages(cur):
    print("=== Creating ref_osha_industry_averages ===")

    cur.execute("DROP TABLE IF EXISTS ref_osha_industry_averages CASCADE")
    cur.execute("""
        CREATE TABLE ref_osha_industry_averages (
            naics_prefix VARCHAR(6) PRIMARY KEY,
            digit_level INT NOT NULL,
            establishment_count INT NOT NULL,
            total_violations INT NOT NULL,
            avg_violations_per_estab NUMERIC(8,3) NOT NULL,
            avg_penalty_per_estab NUMERIC(12,2) NOT NULL DEFAULT 0,
            total_penalties NUMERIC(16,2) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 2-digit NAICS averages
    cur.execute("""
        INSERT INTO ref_osha_industry_averages
            (naics_prefix, digit_level, establishment_count, total_violations,
             avg_violations_per_estab, avg_penalty_per_estab, total_penalties)
        SELECT
            LEFT(oe.naics_code, 2) as naics_prefix,
            2 as digit_level,
            COUNT(DISTINCT oe.establishment_id) as establishment_count,
            COUNT(vd.id) as total_violations,
            ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 3),
            ROUND(COALESCE(SUM(vd.current_penalty), 0)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2),
            COALESCE(SUM(vd.current_penalty), 0)
        FROM osha_establishments oe
        LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
        WHERE oe.naics_code IS NOT NULL AND LENGTH(oe.naics_code) >= 2
        GROUP BY LEFT(oe.naics_code, 2)
        HAVING COUNT(DISTINCT oe.establishment_id) >= 50
    """)
    two_digit = cur.rowcount
    print(f"  2-digit NAICS: {two_digit} rows")

    # 4-digit NAICS averages
    cur.execute("""
        INSERT INTO ref_osha_industry_averages
            (naics_prefix, digit_level, establishment_count, total_violations,
             avg_violations_per_estab, avg_penalty_per_estab, total_penalties)
        SELECT
            LEFT(oe.naics_code, 4) as naics_prefix,
            4 as digit_level,
            COUNT(DISTINCT oe.establishment_id) as establishment_count,
            COUNT(vd.id) as total_violations,
            ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 3),
            ROUND(COALESCE(SUM(vd.current_penalty), 0)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2),
            COALESCE(SUM(vd.current_penalty), 0)
        FROM osha_establishments oe
        LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
        WHERE oe.naics_code IS NOT NULL AND LENGTH(oe.naics_code) >= 4
        GROUP BY LEFT(oe.naics_code, 4)
        HAVING COUNT(DISTINCT oe.establishment_id) >= 20
    """)
    four_digit = cur.rowcount
    print(f"  4-digit NAICS: {four_digit} rows")

    # Overall average (for fallback)
    cur.execute("""
        INSERT INTO ref_osha_industry_averages
            (naics_prefix, digit_level, establishment_count, total_violations,
             avg_violations_per_estab, avg_penalty_per_estab, total_penalties)
        SELECT
            'ALL' as naics_prefix,
            0 as digit_level,
            COUNT(DISTINCT oe.establishment_id),
            COUNT(vd.id),
            ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 3),
            ROUND(COALESCE(SUM(vd.current_penalty), 0)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2),
            COALESCE(SUM(vd.current_penalty), 0)
        FROM osha_establishments oe
        LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
    """)
    print(f"  Overall baseline: 1 row")

    cur.execute("CREATE INDEX idx_ref_osha_avg_prefix ON ref_osha_industry_averages(naics_prefix)")
    cur.execute("CREATE INDEX idx_ref_osha_avg_digit ON ref_osha_industry_averages(digit_level)")

    cur.execute("SELECT COUNT(*) as cnt FROM ref_osha_industry_averages")
    total = cur.fetchone()['cnt']
    print(f"  Total: {total} rows")


def create_rtw_states(cur):
    print("\n=== Creating ref_rtw_states ===")

    cur.execute("DROP TABLE IF EXISTS ref_rtw_states CASCADE")
    cur.execute("""
        CREATE TABLE ref_rtw_states (
            state CHAR(2) PRIMARY KEY,
            state_name VARCHAR(50) NOT NULL,
            year_enacted INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 27 right-to-work states as of 2025
    rtw_states = [
        ('AL', 'Alabama', 1953), ('AZ', 'Arizona', 1946), ('AR', 'Arkansas', 1947),
        ('FL', 'Florida', 1944), ('GA', 'Georgia', 1947), ('ID', 'Idaho', 1985),
        ('IN', 'Indiana', 2012), ('IA', 'Iowa', 1947), ('KS', 'Kansas', 1958),
        ('KY', 'Kentucky', 2017), ('LA', 'Louisiana', 1976), ('MI', 'Michigan', 2013),
        ('MS', 'Mississippi', 1954), ('NE', 'Nebraska', 1946), ('NV', 'Nevada', 1951),
        ('NC', 'North Carolina', 1947), ('ND', 'North Dakota', 1947),
        ('OK', 'Oklahoma', 2001), ('SC', 'South Carolina', 1954),
        ('SD', 'South Dakota', 1946), ('TN', 'Tennessee', 1947),
        ('TX', 'Texas', 1993), ('UT', 'Utah', 1955), ('VA', 'Virginia', 1947),
        ('WV', 'West Virginia', 2016), ('WI', 'Wisconsin', 2015), ('WY', 'Wyoming', 1963),
    ]

    cur.executemany(
        "INSERT INTO ref_rtw_states (state, state_name, year_enacted) VALUES (%s, %s, %s)",
        rtw_states
    )
    print(f"  Inserted {len(rtw_states)} right-to-work states")


def create_nlrb_win_rates(cur):
    print("\n=== Creating ref_nlrb_state_win_rates ===")

    cur.execute("DROP TABLE IF EXISTS ref_nlrb_state_win_rates CASCADE")
    cur.execute("""
        CREATE TABLE ref_nlrb_state_win_rates (
            state CHAR(2) PRIMARY KEY,
            total_elections INT NOT NULL,
            union_wins INT NOT NULL,
            win_rate_pct NUMERIC(5,1) NOT NULL,
            period_start DATE NOT NULL DEFAULT '2020-01-01',
            period_end DATE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Calculate from NLRB data (2020+, distinct case_number per state)
    cur.execute("""
        INSERT INTO ref_nlrb_state_win_rates (state, total_elections, union_wins, win_rate_pct, period_end)
        SELECT
            p.state,
            COUNT(DISTINCT e.case_number) as total_elections,
            COUNT(DISTINCT CASE WHEN e.union_won = true THEN e.case_number END) as union_wins,
            ROUND(
                COUNT(DISTINCT CASE WHEN e.union_won = true THEN e.case_number END)::numeric
                / NULLIF(COUNT(DISTINCT e.case_number), 0) * 100, 1
            ) as win_rate_pct,
            MAX(e.election_date) as period_end
        FROM nlrb_elections e
        JOIN nlrb_participants p ON e.case_number = p.case_number
        WHERE p.state ~ '^[A-Z]{2}$'
          AND e.election_date >= '2020-01-01'
        GROUP BY p.state
        HAVING COUNT(DISTINCT e.case_number) >= 5
    """)
    count = cur.rowcount
    print(f"  Inserted {count} state win rates (2020+, min 5 elections)")

    # Also compute national average
    cur.execute("""
        SELECT
            COUNT(DISTINCT case_number) as total,
            COUNT(DISTINCT CASE WHEN union_won = true THEN case_number END) as wins
        FROM nlrb_elections
        WHERE election_date >= '2020-01-01'
    """)
    nat = cur.fetchone()
    nat_rate = round(nat['wins'] / nat['total'] * 100, 1) if nat['total'] > 0 else 0
    cur.execute("""
        INSERT INTO ref_nlrb_state_win_rates (state, total_elections, union_wins, win_rate_pct)
        VALUES ('US', %s, %s, %s)
    """, [nat['total'], nat['wins'], nat_rate])
    print(f"  National average: {nat_rate}% ({nat['wins']}/{nat['total']})")


def main():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            create_osha_industry_averages(cur)
            create_rtw_states(cur)
            create_nlrb_win_rates(cur)

        conn.commit()
        print("\n=== All reference tables created successfully ===")

        # Verify
        with conn.cursor() as cur:
            for tbl in ['ref_osha_industry_averages', 'ref_rtw_states', 'ref_nlrb_state_win_rates']:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {tbl}")
                print(f"  {tbl}: {cur.fetchone()['cnt']} rows")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
