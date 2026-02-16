#!/usr/bin/env python3
"""
Create State × Industry Union Density Estimates

Combines:
- National industry density (from BLS Table 3)
- State climate multipliers (from state_industry_density_comparison)

To estimate: state×industry density = national_industry_rate × state_multiplier

Example: Construction in NY = 10.3% (national) × 1.8 (NY multiplier) = 18.5% (estimated)
"""
import sys
sys.path.insert(0, '.')

from psycopg2.extras import RealDictCursor
from db_config import get_connection


def create_table(cur):
    """Create estimated_state_industry_density table"""

    cur.execute("""
        DROP TABLE IF EXISTS estimated_state_industry_density CASCADE;
        CREATE TABLE estimated_state_industry_density (
            year INTEGER,
            state VARCHAR(2),
            industry_code VARCHAR(20),
            industry_name VARCHAR(100),
            national_rate DECIMAL(5,2),
            state_multiplier DECIMAL(5,3),
            estimated_density DECIMAL(5,2),
            confidence VARCHAR(20) DEFAULT 'ESTIMATED',
            PRIMARY KEY (year, state, industry_code)
        );

        CREATE INDEX idx_est_state_ind_year ON estimated_state_industry_density(year);
        CREATE INDEX idx_est_state_ind_state ON estimated_state_industry_density(state);
        CREATE INDEX idx_est_state_ind_code ON estimated_state_industry_density(industry_code);

        COMMENT ON TABLE estimated_state_industry_density IS 'Estimated union density by state and industry (national rate × state multiplier)';
        COMMENT ON COLUMN estimated_state_industry_density.confidence IS 'ESTIMATED (calculated) vs ACTUAL (from CPS microdata if available)';
    """)

    print("Created table: estimated_state_industry_density")


def calculate_estimates(cur):
    """Calculate state × industry estimates"""

    # Get national industry rates
    cur.execute("""
        SELECT industry_code, industry_name, union_density_pct
        FROM bls_national_industry_density
        WHERE year = 2024 AND industry_code IS NOT NULL
    """)
    industries = cur.fetchall()

    # Get state climate multipliers
    cur.execute("""
        SELECT state, climate_multiplier
        FROM state_industry_density_comparison
    """)
    states = cur.fetchall()

    print(f"Generating estimates for {len(states)} states × {len(industries)} industries = {len(states) * len(industries)} combinations...")

    # Generate all state × industry combinations
    estimates = []
    for state_row in states:
        state = state_row['state']
        multiplier = float(state_row['climate_multiplier'])

        for ind_row in industries:
            industry_code = ind_row['industry_code']
            industry_name = ind_row['industry_name']
            national_rate = float(ind_row['union_density_pct'])

            # Calculate estimated state×industry density
            estimated = national_rate * multiplier

            # Cap at reasonable bounds (0-100%)
            estimated = max(0.0, min(100.0, estimated))

            estimates.append({
                'year': 2024,
                'state': state,
                'industry_code': industry_code,
                'industry_name': industry_name,
                'national_rate': national_rate,
                'state_multiplier': multiplier,
                'estimated_density': round(estimated, 2),
                'confidence': 'ESTIMATED'
            })

    # Bulk insert
    insert_query = """
        INSERT INTO estimated_state_industry_density (
            year, state, industry_code, industry_name,
            national_rate, state_multiplier, estimated_density, confidence
        ) VALUES (
            %(year)s, %(state)s, %(industry_code)s, %(industry_name)s,
            %(national_rate)s, %(state_multiplier)s, %(estimated_density)s, %(confidence)s
        )
    """

    cur.executemany(insert_query, estimates)

    print(f"Loaded {len(estimates)} state×industry estimates")

    return estimates


def print_summary(cur):
    """Print summary statistics"""

    print("\n" + "=" * 70)
    print("STATE × INDUSTRY DENSITY ESTIMATES")
    print("=" * 70)

    # Example: Construction by state
    print("\nConstruction Union Density by State (Top 10):")
    cur.execute("""
        SELECT state, national_rate, state_multiplier, estimated_density
        FROM estimated_state_industry_density
        WHERE year = 2024 AND industry_code = 'CONST'
        ORDER BY estimated_density DESC
        LIMIT 10
    """)

    for row in cur.fetchall():
        print(f"  {row['state']:2}  National: {row['national_rate']:5.1f}%  × {row['state_multiplier']:.2f}  = {row['estimated_density']:5.1f}%")

    # Statistics
    print("\n" + "=" * 70)
    cur.execute("""
        SELECT
            COUNT(*) as total_estimates,
            COUNT(DISTINCT state) as states,
            COUNT(DISTINCT industry_code) as industries,
            ROUND(AVG(estimated_density), 1) as avg_density,
            ROUND(MIN(estimated_density), 1) as min_density,
            ROUND(MAX(estimated_density), 1) as max_density
        FROM estimated_state_industry_density
        WHERE year = 2024
    """)

    stats = cur.fetchone()
    print(f"Total estimates: {stats['total_estimates']:,}")
    print(f"States: {stats['states']}")
    print(f"Industries: {stats['industries']}")
    print(f"Average estimated density: {stats['avg_density']}%")
    print(f"Range: {stats['min_density']}% - {stats['max_density']}%")

    # Industry breakdown
    print("\n" + "=" * 70)
    print("Average Estimated Density by Industry:")
    cur.execute("""
        SELECT
            industry_code,
            industry_name,
            ROUND(AVG(estimated_density), 1) as avg_density,
            ROUND(MIN(estimated_density), 1) as min_density,
            ROUND(MAX(estimated_density), 1) as max_density
        FROM estimated_state_industry_density
        WHERE year = 2024
        GROUP BY industry_code, industry_name
        ORDER BY avg_density DESC
    """)

    for row in cur.fetchall():
        print(f"  {row['industry_code']:15} {row['industry_name']:35} Avg: {row['avg_density']:5.1f}%  Range: {row['min_density']:5.1f}%-{row['max_density']:5.1f}%")


def main():
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor()

    try:
        print("Creating State × Industry Density Estimates...")
        print("=" * 70)

        create_table(cur)
        conn.commit()

        calculate_estimates(cur)
        conn.commit()

        print_summary(cur)

        print("\n✓ State×industry estimates created successfully")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
