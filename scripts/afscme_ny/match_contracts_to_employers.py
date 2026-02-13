import os
"""
Match NY State Contracts to 990 Employers
Links contract vendors to employers for government funding exposure analysis.
"""

import sys
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'scripts' / 'import'))

import psycopg2

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    print("Warning: rapidfuzz not installed")


def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password=os.environ.get('DB_PASSWORD', '')
    )


def match_contracts_to_990():
    """Match NY State contract vendors to 990 employers."""
    conn = get_db_connection()
    cur = conn.cursor()

    print("=" * 60)
    print("Matching NY State Contracts to 990 Employers")
    print("=" * 60)

    # Get all 990 employers with normalized names
    cur.execute("""
        SELECT id, name, name_normalized, city, ein
        FROM employers_990
        WHERE state = 'NY'
    """)
    employers_990 = {}
    name_index = defaultdict(list)

    for row in cur.fetchall():
        emp_id, name, name_norm, city, ein = row
        employers_990[emp_id] = {
            'id': emp_id,
            'name': name,
            'name_normalized': name_norm or '',
            'city': city,
            'ein': ein
        }
        if name_norm:
            # Index by first word for faster lookup
            first_word = name_norm.split()[0] if name_norm.split() else ''
            if first_word:
                name_index[first_word].append(emp_id)

    print(f"Loaded {len(employers_990)} 990 employers")

    # Get all NY State contracts
    cur.execute("""
        SELECT id, vendor_name, vendor_name_normalized, vendor_ein, current_amount
        FROM ny_state_contracts
        WHERE is_afscme_relevant = TRUE
    """)
    contracts = cur.fetchall()
    print(f"Processing {len(contracts)} AFSCME-relevant contracts")

    # Clear existing matches
    cur.execute("DELETE FROM contract_employer_matches WHERE ny_state_contract_id IS NOT NULL")

    matches = []
    matched_vendors = set()
    vendor_matches = {}  # Cache vendor -> employer matches

    for contract_id, vendor_name, vendor_norm, vendor_ein, amount in contracts:
        if not vendor_name:
            continue

        # Check cache first
        cache_key = vendor_norm or vendor_name.lower()
        if cache_key in vendor_matches:
            emp_id, score = vendor_matches[cache_key]
            matches.append((contract_id, emp_id, 'cached', score))
            continue

        best_match = None
        best_score = 0

        # Try EIN match first
        if vendor_ein:
            for emp_id, emp in employers_990.items():
                if emp.get('ein') == vendor_ein:
                    best_match = emp_id
                    best_score = 100
                    break

        # Fuzzy name match if no EIN match
        if not best_match and HAS_RAPIDFUZZ and vendor_norm:
            first_word = vendor_norm.split()[0] if vendor_norm.split() else ''

            # Get candidates from index
            candidates = name_index.get(first_word, [])

            # Also check all employers if few candidates
            if len(candidates) < 50:
                candidates = list(employers_990.keys())

            for emp_id in candidates:
                emp = employers_990[emp_id]
                emp_norm = emp.get('name_normalized', '')
                if not emp_norm:
                    continue

                score = fuzz.token_set_ratio(vendor_norm, emp_norm)

                if score > best_score and score >= 80:
                    best_score = score
                    best_match = emp_id

        if best_match:
            matches.append((contract_id, best_match, 'fuzzy_name', best_score))
            vendor_matches[cache_key] = (best_match, best_score)
            matched_vendors.add(vendor_name)

    print(f"Found {len(matches)} contract-employer matches")
    print(f"Unique vendors matched: {len(matched_vendors)}")

    # Insert matches
    for contract_id, emp_id, method, score in matches:
        cur.execute("""
            INSERT INTO contract_employer_matches (
                ny_state_contract_id, employer_990_id, match_method, match_score
            ) VALUES (%s, %s, %s, %s)
        """, (contract_id, emp_id, method, score))

    conn.commit()

    # Verify
    cur.execute("SELECT COUNT(*) FROM contract_employer_matches WHERE ny_state_contract_id IS NOT NULL")
    match_count = cur.fetchone()[0]
    print(f"Saved {match_count} matches to database")

    cur.close()
    conn.close()

    return len(matches)


def update_target_funding_scores():
    """Update organizing targets with government funding data."""
    conn = get_db_connection()
    cur = conn.cursor()

    print("\n" + "=" * 60)
    print("Updating Target Priority Scores with Contract Funding")
    print("=" * 60)

    # Get contract totals by 990 employer
    cur.execute("""
        SELECT
            e990.id,
            COUNT(DISTINCT c.id) as contract_count,
            COALESCE(SUM(c.current_amount), 0) as total_funding
        FROM employers_990 e990
        JOIN contract_employer_matches cem ON e990.id = cem.employer_990_id
        JOIN ny_state_contracts c ON cem.ny_state_contract_id = c.id
        WHERE c.is_afscme_relevant = TRUE
        GROUP BY e990.id
    """)

    funding_data = {row[0]: {'count': row[1], 'total': float(row[2])} for row in cur.fetchall()}
    print(f"Found funding data for {len(funding_data)} employers")

    # Update organizing targets
    cur.execute("""
        SELECT id, employer_990_id, priority_score
        FROM organizing_targets
    """)
    targets = cur.fetchall()

    updated = 0
    for target_id, emp_990_id, old_score in targets:
        funding = funding_data.get(emp_990_id, {'count': 0, 'total': 0})

        # Calculate funding score (0-20 points)
        total = funding['total']
        if total >= 10_000_000:  # $10M+
            funding_score = 20
        elif total >= 5_000_000:  # $5M+
            funding_score = 16
        elif total >= 1_000_000:  # $1M+
            funding_score = 12
        elif total >= 500_000:  # $500K+
            funding_score = 8
        elif total >= 100_000:  # $100K+
            funding_score = 4
        elif total > 0:
            funding_score = 2
        else:
            funding_score = 0

        # Update priority score (add funding component)
        # Old score had 0 for govt funding, so add the new funding score
        new_score = float(old_score or 0) + funding_score

        # Determine new tier
        if new_score >= 70:
            tier = 'TOP'
        elif new_score >= 50:
            tier = 'HIGH'
        elif new_score >= 30:
            tier = 'MEDIUM'
        else:
            tier = 'LOW'

        cur.execute("""
            UPDATE organizing_targets
            SET ny_state_contract_count = %s,
                ny_state_contract_total = %s,
                total_govt_funding = %s,
                govt_funding_score = %s,
                priority_score = %s,
                priority_tier = %s
            WHERE id = %s
        """, (
            funding['count'],
            funding['total'],
            funding['total'],  # total_govt_funding (will add NYC later)
            round(funding_score / 20, 2),  # Normalize to 0-1
            round(new_score, 2),
            tier,
            target_id
        ))
        updated += 1

    conn.commit()

    # Summary
    cur.execute("""
        SELECT priority_tier, COUNT(*), AVG(total_govt_funding)
        FROM organizing_targets
        GROUP BY priority_tier
        ORDER BY
            CASE priority_tier
                WHEN 'TOP' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                ELSE 4
            END
    """)

    print(f"\nUpdated {updated} targets")
    print("\n=== Target Tiers After Funding Update ===")
    for tier, count, avg_funding in cur.fetchall():
        avg_str = f"${float(avg_funding)/1e6:.2f}M" if avg_funding else "$0"
        print(f"  {tier}: {count} targets (avg funding: {avg_str})")

    # Show top targets with funding
    cur.execute("""
        SELECT employer_name, city, industry_category,
               ny_state_contract_count, ny_state_contract_total,
               priority_score, priority_tier
        FROM organizing_targets
        WHERE ny_state_contract_total > 0
        ORDER BY priority_score DESC
        LIMIT 15
    """)

    print("\n=== Top 15 Targets with State Contract Funding ===")
    for name, city, industry, cnt, total, score, tier in cur.fetchall():
        total_str = f"${float(total)/1e6:.1f}M" if total else "$0"
        print(f"  [{tier}] {name[:40]}")
        print(f"        {city} | {industry or 'Unknown'} | {cnt} contracts ({total_str}) | Score: {score}")

    cur.close()
    conn.close()

    return updated


if __name__ == '__main__':
    match_contracts_to_990()
    update_target_funding_scores()
