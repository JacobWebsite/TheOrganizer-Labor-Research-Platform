"""
Generate Prioritized Organizing Targets
Creates a ranked list of potential AFSCME organizing targets from unmatched 990 employers.
"""

import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import psycopg2


def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='Juniordog33!'
    )


def calculate_priority_score(emp):
    """
    Calculate priority score (0-100) for organizing target.

    Formula:
    - AFSCME sector score (30% weight)
    - Size score based on employee count (30% weight)
    - Government funding score (20% weight) - placeholder until contract data
    - Not-already-organized bonus (20% weight)
    """
    score = 0

    # 1. AFSCME sector score (0-30 points)
    afscme_score = float(emp.get('afscme_relevance_score') or 0)
    score += afscme_score * 30

    # 2. Size score (0-30 points)
    employee_count = emp.get('employee_count') or 0
    if employee_count >= 1000:
        size_score = 30
    elif employee_count >= 500:
        size_score = 25
    elif employee_count >= 100:
        size_score = 20
    elif employee_count >= 50:
        size_score = 15
    elif employee_count >= 10:
        size_score = 10
    else:
        # No employee count data - use revenue as proxy
        revenue = float(emp.get('total_revenue') or 0)
        if revenue >= 10_000_000:
            size_score = 20
        elif revenue >= 5_000_000:
            size_score = 15
        elif revenue >= 1_000_000:
            size_score = 10
        elif revenue >= 500_000:
            size_score = 5
        else:
            size_score = 2
    score += size_score

    # 3. Government funding score (0-20 points) - placeholder
    # Will be populated after contract data integration
    govt_score = 0
    score += govt_score

    # 4. Not-organized bonus (20 points)
    # All targets in this list are unmatched, so full bonus
    score += 20

    return round(score, 2)


def get_priority_tier(score):
    """Assign priority tier based on score."""
    if score >= 70:
        return 'TOP'
    elif score >= 50:
        return 'HIGH'
    elif score >= 30:
        return 'MEDIUM'
    else:
        return 'LOW'


def generate_targets():
    """Generate organizing targets from unmatched 990 employers."""
    conn = get_db_connection()
    cur = conn.cursor()

    print("=" * 60)
    print("Generating AFSCME NY Organizing Targets")
    print("=" * 60)

    # Get unmatched 990 employers
    cur.execute("""
        SELECT e.id, e.ein, e.name, e.city, e.state,
               e.employee_count, e.total_revenue, e.salaries_benefits,
               e.industry_category, e.afscme_relevance_score, e.afscme_sector_match
        FROM employers_990 e
        LEFT JOIN employer_990_matches m ON e.id = m.employer_990_id
        WHERE e.state = 'NY'
        AND m.id IS NULL
    """)

    unmatched = []
    for row in cur.fetchall():
        unmatched.append({
            'id': row[0],
            'ein': row[1],
            'name': row[2],
            'city': row[3],
            'state': row[4],
            'employee_count': row[5],
            'total_revenue': row[6],
            'salaries_benefits': row[7],
            'industry_category': row[8],
            'afscme_relevance_score': row[9],
            'afscme_sector_match': row[10]
        })

    print(f"Found {len(unmatched)} unmatched employers")

    # Clear existing targets
    cur.execute("DELETE FROM organizing_targets")

    # Generate targets with priority scores
    inserted = 0
    tier_counts = {'TOP': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}

    for emp in unmatched:
        priority_score = calculate_priority_score(emp)
        priority_tier = get_priority_tier(priority_score)
        tier_counts[priority_tier] += 1

        cur.execute("""
            INSERT INTO organizing_targets (
                employer_990_id, employer_name, city, state, ein,
                employee_count, total_revenue, salaries_benefits,
                industry_category, afscme_sector_score,
                has_existing_afscme_contract,
                priority_score, priority_tier, status
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                FALSE,
                %s, %s, 'NEW'
            )
        """, (
            emp['id'],
            emp['name'],
            emp['city'],
            emp['state'],
            emp['ein'],
            emp['employee_count'],
            emp['total_revenue'],
            emp['salaries_benefits'],
            emp['industry_category'],
            emp['afscme_relevance_score'],
            priority_score,
            priority_tier
        ))
        inserted += 1

    conn.commit()

    # Summary
    print(f"\n=== Targets Generated ===")
    print(f"Total targets: {inserted}")
    print(f"\nBy Priority Tier:")
    for tier in ['TOP', 'HIGH', 'MEDIUM', 'LOW']:
        print(f"  {tier}: {tier_counts[tier]}")

    # Top targets by industry
    cur.execute("""
        SELECT industry_category, COUNT(*) as cnt,
               COUNT(*) FILTER (WHERE priority_tier IN ('TOP', 'HIGH')) as top_high
        FROM organizing_targets
        WHERE industry_category IS NOT NULL
        GROUP BY industry_category
        ORDER BY top_high DESC
    """)
    print(f"\n=== By Industry ===")
    for ind, cnt, top_high in cur.fetchall():
        print(f"  {ind}: {cnt} total ({top_high} TOP/HIGH)")

    # Top 20 targets
    cur.execute("""
        SELECT employer_name, city, industry_category,
               employee_count, priority_score, priority_tier
        FROM organizing_targets
        ORDER BY priority_score DESC
        LIMIT 20
    """)

    print(f"\n=== Top 20 Targets ===")
    for i, row in enumerate(cur.fetchall(), 1):
        name, city, industry, emp_count, score, tier = row
        emp_str = f"{emp_count} employees" if emp_count else "size unknown"
        print(f"{i:2}. [{tier}] {name}")
        print(f"      {city}, {industry or 'Unknown industry'} - {emp_str} (score: {score})")

    cur.close()
    conn.close()

    return inserted, tier_counts


if __name__ == '__main__':
    generate_targets()
