"""
Extract 20,000 random NY employers from master_employers for LLM dedup experiments.
Uses setseed(0.42) for reproducibility.
"""
import json
import sys
import os
from collections import Counter
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Set seed for reproducible random sampling
    cur.execute("SELECT setseed(0.42)")

    cur.execute("""
        SELECT master_id, canonical_name, display_name, city, state, zip,
               naics, ein, source_origin, employee_count, is_union, is_public,
               is_nonprofit, is_federal_contractor, website, industry_text,
               data_quality_score
        FROM master_employers
        WHERE state = 'NY'
        ORDER BY random()
        LIMIT 20000
    """)

    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Convert to list of dicts, handling Decimal types
    records = []
    for row in rows:
        d = {}
        for col, val in zip(columns, row):
            if isinstance(val, Decimal):
                d[col] = float(val)
            else:
                d[col] = val
        records.append(d)

    # Save to JSON
    out_path = os.path.join(os.path.dirname(__file__), 'ny_sample_20k.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, default=str)

    print(f"Saved {len(records)} records to {out_path}")
    print()

    # --- Summary Statistics ---
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)

    print(f"\nTotal records: {len(records)}")

    # Count by source_origin
    source_counts = Counter(r['source_origin'] for r in records)
    print(f"\nBy source_origin ({len(source_counts)} distinct):")
    for src, cnt in source_counts.most_common():
        print(f"  {str(src):25s} {cnt:>6,}")

    # Field population rates
    fields = [
        ('ein', 'EIN'),
        ('naics', 'NAICS'),
        ('city', 'City'),
        ('zip', 'ZIP'),
        ('employee_count', 'Employee Count'),
        ('website', 'Website'),
        ('industry_text', 'Industry Text'),
        ('data_quality_score', 'Data Quality Score'),
    ]
    print("\nField population:")
    for field, label in fields:
        populated = sum(1 for r in records if r.get(field) is not None)
        pct = populated / len(records) * 100
        print(f"  {label:25s} {populated:>6,} / {len(records):,}  ({pct:5.1f}%)")

    # Boolean flags
    bool_fields = [
        ('is_union', 'Union'),
        ('is_public', 'Public'),
        ('is_nonprofit', 'Nonprofit'),
        ('is_federal_contractor', 'Federal Contractor'),
    ]
    print("\nBoolean flags (True count):")
    for field, label in bool_fields:
        true_count = sum(1 for r in records if r.get(field) is True)
        pct = true_count / len(records) * 100
        print(f"  {label:25s} {true_count:>6,} / {len(records):,}  ({pct:5.1f}%)")

    # Top cities
    city_counts = Counter(r['city'] for r in records if r['city'])
    print("\nTop 15 cities:")
    for city, cnt in city_counts.most_common(15):
        print(f"  {city:25s} {cnt:>6,}")

    # NAICS prefix distribution (2-digit)
    naics_2 = Counter(r['naics'][:2] for r in records if r['naics'] and len(r['naics']) >= 2)
    print("\nTop 15 NAICS 2-digit sectors:")
    for code, cnt in naics_2.most_common(15):
        print(f"  {code:25s} {cnt:>6,}")


if __name__ == '__main__':
    main()
