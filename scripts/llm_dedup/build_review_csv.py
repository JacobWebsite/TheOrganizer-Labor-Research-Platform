"""
Build a prioritized human-review CSV from the LLM batch DUPLICATE verdicts.

Priority order (most-deserving-of-review first):
  1. MEDIUM confidence DUPLICATEs (the ones the LLM was less sure about)
  2. Cross-source DUPLICATEs that came from heuristic class != auto_duplicate
     (these are the genuinely new finds that the heuristics missed)
  3. Cross-source DUPLICATEs from auto_duplicate (basic sanity-check)
  4. Same-source DUPLICATEs (lowest priority -- usually obvious dupes)

Adds 4 review columns: DECISION (APPROVE/REJECT/SKIP), NOTE, REVIEWER, REVIEW_DATE.
"""
import csv
import os
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(DIR, 'anthropic_batch_results.csv')
REVIEW_CSV  = os.path.join(DIR, 'review_duplicates.csv')


def priority(row):
    cross_source = row['src1'].strip('"') != row['src2'].strip('"')
    is_ambiguous_origin = row['classification'] == 'ambiguous'
    is_medium = row['confidence'] == 'MEDIUM'
    # Lower number = higher priority
    return (
        0 if is_medium else 1,
        0 if (cross_source and is_ambiguous_origin) else 1,
        0 if cross_source else 1,
        -float(row['composite']),  # higher composite = more obvious; review later
    )


def main():
    with open(RESULTS_CSV, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    dups = [r for r in rows if r['verdict'] == 'DUPLICATE']
    print(f'Total DUPLICATEs: {len(dups)}')

    # Stats by category
    by_bucket = defaultdict(int)
    for r in dups:
        cs = r['src1'].strip('"') != r['src2'].strip('"')
        ho = r['classification']
        bucket = f'{"cross" if cs else "same"}-source / {ho}'
        by_bucket[bucket] += 1
    print('\nBucket counts:')
    for k, n in sorted(by_bucket.items(), key=lambda kv: -kv[1]):
        print(f'  {k:40s} {n:>4}')

    dups.sort(key=priority)

    out_cols = ['DECISION', 'NOTE', 'REVIEWER', 'REVIEW_DATE',
                'priority_rank', 'cross_source',
                'id1', 'id2', 'src1', 'src2', 'name1', 'name2',
                'classification', 'composite', 'confidence', 'reason']
    with open(REVIEW_CSV, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=out_cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for rank, r in enumerate(dups, 1):
            cs = r['src1'].strip('"') != r['src2'].strip('"')
            w.writerow({
                'DECISION': '',           # APPROVE / REJECT / SKIP
                'NOTE': '',
                'REVIEWER': '',
                'REVIEW_DATE': '',
                'priority_rank': rank,
                'cross_source': 'YES' if cs else 'no',
                'id1': r['id1'],
                'id2': r['id2'],
                'src1': r['src1'].strip('"'),
                'src2': r['src2'].strip('"'),
                'name1': r['name1'].strip('"'),
                'name2': r['name2'].strip('"'),
                'classification': r['classification'],
                'composite': r['composite'],
                'confidence': r['confidence'],
                'reason': r['reason'].strip('"'),
            })

    print(f'\nWrote {len(dups)} rows -> {REVIEW_CSV}')
    print('\nReview workflow:')
    print('  1. Open review_duplicates.csv in Excel / Google Sheets')
    print('  2. Start at priority_rank=1 (MEDIUM-confidence cross-source ambiguous wins)')
    print('  3. Fill DECISION column: APPROVE | REJECT | SKIP')
    print('  4. After ~25 rows, eyeball whether the LLM is reliably right.')
    print('     If yes, you can apply the rest in bulk. If no, expand review.')


if __name__ == '__main__':
    main()
