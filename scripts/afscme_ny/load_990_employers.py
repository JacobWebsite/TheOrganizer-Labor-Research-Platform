"""
Load 990 Employers for AFSCME NY Matching
Filters employers_990.json to NY state and loads into database.
"""

import json
import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'scripts' / 'import'))

import psycopg2
from name_normalizer import normalize_employer

# AFSCME-relevant industry scores
AFSCME_INDUSTRY_SCORES = {
    'Healthcare': 0.95,
    'Senior Care': 0.95,
    'Social Services': 0.90,
    'Education': 0.85,
    'Housing': 0.75,
    'Transportation': 0.70,
    'Labor Organization': 0.50,  # Already organized
    'Arts/Entertainment': 0.30,
}

def get_afscme_relevance_score(industry_category: str, source_type: str) -> tuple:
    """
    Calculate AFSCME relevance score based on industry and source type.
    Returns (score, is_sector_match)
    """
    if not industry_category:
        return (0.20, False)  # Unknown industry gets low score

    score = AFSCME_INDUSTRY_SCORES.get(industry_category, 0.20)
    is_sector_match = score >= 0.70

    # Boost for direct filers (more complete data)
    if source_type == 'filer':
        score = min(1.0, score + 0.05)

    return (round(score, 2), is_sector_match)


def load_990_employers_to_db(json_path: str, state_filter: str = 'NY'):
    """
    Load 990 employers from JSON file into database.

    Args:
        json_path: Path to employers_990.json
        state_filter: State to filter (default: NY)
    """
    print(f"Loading 990 employers from {json_path}...")

    # Load JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_employers = data['summary']['total_employers']
    state_count = data['summary']['by_state'].get(state_filter, 0)
    print(f"Total employers: {total_employers}")
    print(f"{state_filter} employers expected: {state_count}")

    # Connect to database
    conn = psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )
    cur = conn.cursor()

    # Clear existing data
    print("Clearing existing employers_990 data...")
    cur.execute("DELETE FROM employers_990")

    # Filter and insert
    inserted = 0
    skipped = 0

    for emp in data['employers']:
        if emp.get('state') != state_filter:
            continue

        name = emp.get('name', '')
        if not name:
            skipped += 1
            continue

        # Normalize name
        name_normalized = normalize_employer(name, expand_abbrevs=True)

        # Get industry and calculate AFSCME score
        industry = emp.get('industry_category')
        source_type = emp.get('source_type', 'unknown')
        afscme_score, is_sector_match = get_afscme_relevance_score(industry, source_type)

        # Insert
        cur.execute("""
            INSERT INTO employers_990 (
                ein, name, name_normalized,
                address_line1, city, state, zip_code,
                source_type, source_ein, source_name, source_file,
                salaries_benefits, employee_count, total_revenue,
                grant_amount, contractor_payment,
                exempt_status, ntee_code, industry_category,
                afscme_relevance_score, afscme_sector_match, tax_year
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
        """, (
            emp.get('ein'),
            name,
            name_normalized,
            emp.get('address_line1'),
            emp.get('city'),
            emp.get('state'),
            emp.get('zip_code'),
            source_type,
            emp.get('source_ein'),
            emp.get('source_name'),
            emp.get('source_file'),
            emp.get('salaries_benefits'),
            emp.get('employee_count'),
            emp.get('total_revenue'),
            emp.get('grant_amount'),
            emp.get('contractor_payment'),
            emp.get('exempt_status'),
            emp.get('ntee_code'),
            industry,
            afscme_score,
            is_sector_match,
            emp.get('tax_year')
        ))

        inserted += 1
        if inserted % 1000 == 0:
            print(f"  Inserted {inserted} employers...")

    conn.commit()

    # Verify counts
    cur.execute("SELECT COUNT(*) FROM employers_990")
    db_count = cur.fetchone()[0]

    # Get industry breakdown
    cur.execute("""
        SELECT industry_category, COUNT(*) as cnt,
               AVG(afscme_relevance_score) as avg_score,
               SUM(CASE WHEN afscme_sector_match THEN 1 ELSE 0 END) as sector_matches
        FROM employers_990
        GROUP BY industry_category
        ORDER BY cnt DESC
    """)
    industries = cur.fetchall()

    # Get source type breakdown
    cur.execute("""
        SELECT source_type, COUNT(*) as cnt
        FROM employers_990
        GROUP BY source_type
        ORDER BY cnt DESC
    """)
    sources = cur.fetchall()

    cur.close()
    conn.close()

    print(f"\n=== Load Complete ===")
    print(f"Inserted: {inserted}")
    print(f"Skipped (no name): {skipped}")
    print(f"Database count: {db_count}")

    print(f"\n=== By Industry ===")
    for industry, cnt, avg_score, sector_matches in industries:
        ind_name = industry or 'Unknown'
        print(f"  {ind_name}: {cnt} employers (avg score: {avg_score:.2f}, sector match: {sector_matches})")

    print(f"\n=== By Source Type ===")
    for source, cnt in sources:
        print(f"  {source}: {cnt}")

    return inserted


if __name__ == '__main__':
    json_path = project_root / 'employers_990.json'

    if not json_path.exists():
        print(f"Error: Cannot find {json_path}")
        sys.exit(1)

    load_990_employers_to_db(str(json_path), state_filter='NY')
