"""Quick check: how many pairs fit the multi-location pattern."""
import csv, os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV = os.path.join(BASE, 'data', 'f7_combined_dedup_evidence.csv')

classes = {}
multi_loc_candidates = 0

with open(CSV, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cls = row['classification']
        classes[cls] = classes.get(cls, 0) + 1

        # Multi-location pattern: high pg_trgm (>= 0.8) but different cities
        pg = float(row['pgtrgm_combined']) if row['pgtrgm_combined'] else None
        sp = float(row['splink_prob']) if row['splink_prob'] else None
        c1, c2 = row.get('city1', ''), row.get('city2', '')
        if pg and pg >= 0.8 and c1.upper() != c2.upper() and c1 and c2:
            multi_loc_candidates += 1

print("Classification distribution in exported CSV:")
for cls, cnt in sorted(classes.items(), key=lambda x: -x[1]):
    print("  %-25s %6d" % (cls, cnt))

print("\nMulti-location candidates (pg_trgm >= 0.8, different cities): %d" % multi_loc_candidates)
