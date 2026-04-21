"""
Score classify_pair_v2 tier assignments against the 31,532 Haiku-labeled
pairs. For each tier, reports:
  - count of pairs assigned
  - distribution of LLM verdicts (DUPLICATE / RELATED / DIFFERENT)
  - observed precision vs DUPLICATE
  - recall of LLM DUPLICATEs captured in this tier
"""
import csv
import json
import os
from collections import Counter, defaultdict

import sys
DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from rule_engine import classify_pair_v2, pair_from_candidate

CANDIDATES = os.path.join(DIR, 'candidates_singletons_scored.json')
RESULTS_CSV = os.path.join(DIR, 'anthropic_batch_results.csv')
OUT = os.path.join(DIR, 'rule_engine_validation.json')


def main():
    verdicts = {}
    with open(RESULTS_CSV, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['id1'] and r['id2']:
                verdicts[(int(r['id1']), int(r['id2']))] = r['verdict']

    with open(CANDIDATES) as f:
        pairs = json.load(f)

    print(f'Candidate pairs: {len(pairs):,}')
    print(f'LLM verdicts:    {len(verdicts):,}')
    total_dup = sum(1 for v in verdicts.values() if v == 'DUPLICATE')
    total_rel = sum(1 for v in verdicts.values() if v == 'RELATED')
    total_dif = sum(1 for v in verdicts.values() if v == 'DIFFERENT')
    print(f'Total LLM DUPs: {total_dup:,}  RELs: {total_rel:,}  DIFFs: {total_dif:,}')
    print()

    # Classify every pair
    tier_buckets = defaultdict(lambda: {'n': 0, 'verdicts': Counter(), 'rules': Counter()})
    per_pair = []
    for p in pairs:
        cls = classify_pair_v2(pair_from_candidate(p))
        tier_buckets[cls.tier]['n'] += 1
        tier_buckets[cls.tier]['rules'][cls.rule or '<none>'] += 1
        v = verdicts.get((p['id1'], p['id2']))
        if v:
            tier_buckets[cls.tier]['verdicts'][v] += 1
        per_pair.append((p['id1'], p['id2'], cls.tier, cls.rule, cls.predicted, v))

    # Summarize
    tier_order = ['tier_series_demoted', 'tier_A_auto_merge', 'tier_B_high_conf',
                  'tier_C_review', 'tier_D_different']

    print(f'{"Tier":25s} {"Count":>7s} {"DUP":>6s} {"REL":>6s} {"DIF":>6s} {"Prec":>7s} {"Recall":>8s}')
    print('-' * 75)
    report = {'tiers': {}, 'total_pairs': len(pairs),
              'total_dup': total_dup, 'total_rel': total_rel, 'total_dif': total_dif}

    cumulative_dup = 0
    for t in tier_order:
        b = tier_buckets.get(t, {'n': 0, 'verdicts': Counter(), 'rules': Counter()})
        n = b['n']
        dup = b['verdicts'].get('DUPLICATE', 0)
        rel = b['verdicts'].get('RELATED', 0)
        dif = b['verdicts'].get('DIFFERENT', 0)
        # Precision vs DUPLICATE, where applicable
        if t in ('tier_A_auto_merge', 'tier_B_high_conf'):
            prec = dup / n if n else 0
            recall = dup / total_dup if total_dup else 0
        elif t == 'tier_series_demoted':
            # For demoted: precision = fraction NOT-DUP
            prec = (rel + dif) / n if n else 0
            recall = (rel + dif) / (total_rel + total_dif) if (total_rel + total_dif) else 0
        elif t == 'tier_C_review':
            prec = dup / n if n else 0
            recall = dup / total_dup if total_dup else 0
        else:  # tier_D_different
            prec = dif / n if n else 0
            recall = dif / total_dif if total_dif else 0
        if t in ('tier_A_auto_merge', 'tier_B_high_conf'):
            cumulative_dup += dup
        print(f'{t:25s} {n:>7,} {dup:>6,} {rel:>6,} {dif:>6,} '
              f'{100*prec:>6.1f}% {100*recall:>7.2f}%')

        report['tiers'][t] = {
            'count': n,
            'llm_dup': dup, 'llm_rel': rel, 'llm_dif': dif,
            'precision': round(prec, 4),
            'recall': round(recall, 4),
            'rule_breakdown': dict(b['rules']),
        }

    print('-' * 75)
    print('\\nCUMULATIVE MERGE-TIER PERFORMANCE (Tier A + Tier B):')
    a_count = tier_buckets['tier_A_auto_merge']['n']
    b_count = tier_buckets['tier_B_high_conf']['n']
    a_dup = tier_buckets['tier_A_auto_merge']['verdicts'].get('DUPLICATE', 0)
    b_dup = tier_buckets['tier_B_high_conf']['verdicts'].get('DUPLICATE', 0)
    a_rel = tier_buckets['tier_A_auto_merge']['verdicts'].get('RELATED', 0)
    b_rel = tier_buckets['tier_B_high_conf']['verdicts'].get('RELATED', 0)
    a_dif = tier_buckets['tier_A_auto_merge']['verdicts'].get('DIFFERENT', 0)
    b_dif = tier_buckets['tier_B_high_conf']['verdicts'].get('DIFFERENT', 0)
    ab_n = a_count + b_count
    ab_dup = a_dup + b_dup; ab_rel = a_rel + b_rel; ab_dif = a_dif + b_dif
    ab_prec = ab_dup / ab_n if ab_n else 0
    ab_recall = ab_dup / total_dup if total_dup else 0
    print(f'  Total A+B merges proposed: {ab_n}')
    print(f'  True DUPs:                 {ab_dup} (precision {100*ab_prec:.1f}%)')
    print(f'  LLM-RELATED misclassified: {ab_rel}  (benign: parents/subs/fund families)')
    print(f'  LLM-DIFFERENT misclassified: {ab_dif}  (real FPs)')
    print(f'  Recall of LLM DUPs:        {100*ab_recall:.1f}%')
    report['merge_tier_totals'] = {
        'count': ab_n, 'true_dup': ab_dup, 'rel': ab_rel, 'dif': ab_dif,
        'precision': round(ab_prec, 4), 'recall': round(ab_recall, 4),
    }

    # What Tier A+B MISSES (real DUPs that fell into C or D)
    missed_in_c = tier_buckets['tier_C_review']['verdicts'].get('DUPLICATE', 0)
    missed_in_d = tier_buckets['tier_D_different']['verdicts'].get('DUPLICATE', 0)
    print(f'\\n  Real DUPs routed to Tier C (review): {missed_in_c}')
    print(f'  Real DUPs routed to Tier D (different, MISS): {missed_in_d}')

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    print(f'\\nFull report: {OUT}')

    # Emit per-pair CSV for Tier A (ready to apply as merges)
    tier_a_csv = os.path.join(DIR, 'tier_A_auto_merge.csv')
    tier_a_pairs = [r for r in per_pair if r[2] == 'tier_A_auto_merge']
    # Join to original pair for the full picture
    by_key = {(p['id1'], p['id2']): p for p in pairs}
    with open(tier_a_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['id1', 'id2', 'rule', 'src1', 'src2',
                    'name1', 'name2', 'zip1', 'zip2', 'llm_verdict', 'expected_precision'])
        for id1, id2, tier, rule, pred, llm_v in tier_a_pairs:
            orig = by_key.get((id1, id2), {})
            w.writerow([id1, id2, rule or '',
                        orig.get('source_1', ''), orig.get('source_2', ''),
                        orig.get('display_name_1', ''), orig.get('display_name_2', ''),
                        orig.get('zip_1', ''), orig.get('zip_2', ''),
                        llm_v or '', 0.96])
    print(f'Tier A merge-ready CSV: {tier_a_csv} ({len(tier_a_pairs)} pairs)')


if __name__ == '__main__':
    main()
