"""
Extract 25,000 NY singleton master_employers, stratified across source_origin.

A "singleton" master is one with exactly 1 row in master_employer_source_ids
(i.e., it has only ever been linked to a single source-system record). These
are the prime targets for LLM-judged dedup -- if they're actually duplicates
of another master, no existing matching tier has caught the link yet.

Strategy:
  - Floor of 500 records from every source_origin (so even nlrb/990 are represented)
  - Otherwise proportional to NY-singleton count per source
  - Reproducible via setseed(0.42)
"""
import json
import math
import os
import sys
from collections import Counter
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

OUT_PATH = os.path.join(os.path.dirname(__file__), 'ny_singletons_25k.json')
TARGET_TOTAL = 25_000
FLOOR_PER_SOURCE = 500

NY_SINGLETON_COUNTS = {
    'bmf':       70_051,
    'corpwatch': 55_355,
    'mergent':   46_463,
    'sec':       37_758,
    'sam':       33_190,
    'osha':      19_556,
    'gleif':     15_016,
    'whd':       13_734,
    'f7':         8_491,
    '990':        3_060,
    'nlrb':       1_913,
}


def compute_quotas(target_total, counts, floor):
    """Allocate quotas: floor for everyone, then proportional split of remainder."""
    quotas = {src: min(floor, n) for src, n in counts.items()}
    floor_sum = sum(quotas.values())
    remainder = max(0, target_total - floor_sum)

    # Proportional allocation of remainder using counts above the floor
    above_floor = {src: max(0, n - floor) for src, n in counts.items()}
    total_above = sum(above_floor.values())
    if total_above == 0 or remainder == 0:
        return quotas

    for src, above in above_floor.items():
        share = math.floor(remainder * above / total_above)
        quotas[src] = min(counts[src], quotas[src] + share)
    return quotas


def main():
    quotas = compute_quotas(TARGET_TOTAL, NY_SINGLETON_COUNTS, FLOOR_PER_SOURCE)
    print('Quotas per source:')
    for src, q in sorted(quotas.items(), key=lambda kv: -kv[1]):
        print(f'  {src:12s} {q:>6,}')
    print(f'  {"TOTAL":12s} {sum(quotas.values()):>6,}')
    print()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT setseed(0.42)')

    all_records = []
    for src, quota in quotas.items():
        if quota == 0:
            continue
        cur.execute("""
            WITH ny_singletons AS (
              SELECT m.master_id
              FROM master_employers m
              JOIN master_employer_source_ids s ON m.master_id = s.master_id
              WHERE m.state = 'NY' AND m.source_origin = %s
              GROUP BY m.master_id
              HAVING COUNT(*) = 1
            )
            SELECT m.master_id, m.canonical_name, m.display_name, m.city, m.state,
                   m.zip, m.naics, m.ein, m.source_origin, m.employee_count,
                   m.is_union, m.is_public, m.is_nonprofit, m.is_federal_contractor,
                   m.website, m.industry_text, m.data_quality_score
            FROM master_employers m
            JOIN ny_singletons ns ON m.master_id = ns.master_id
            ORDER BY random()
            LIMIT %s
        """, (src, quota))

        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            d = {}
            for c, v in zip(cols, row):
                d[c] = float(v) if isinstance(v, Decimal) else v
            all_records.append(d)
        print(f'  pulled {src:12s} {len(all_records):>6,} (running total)')

    cur.close()
    conn.close()

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, indent=2, default=str)
    print(f'\nSaved {len(all_records):,} records -> {OUT_PATH}')

    # Summary
    print('\n--- Sample composition ---')
    src_counts = Counter(r['source_origin'] for r in all_records)
    for src, n in src_counts.most_common():
        print(f'  {str(src):12s} {n:>6,}')

    fields = [('ein', 'EIN'), ('naics', 'NAICS'), ('city', 'City'),
              ('zip', 'ZIP'), ('employee_count', 'Empl ct'), ('website', 'Website')]
    print('\nField population:')
    for f, label in fields:
        n = sum(1 for r in all_records if r.get(f) is not None)
        print(f'  {label:10s} {n:>6,} / {len(all_records):,} ({100*n/len(all_records):.1f}%)')


if __name__ == '__main__':
    main()
