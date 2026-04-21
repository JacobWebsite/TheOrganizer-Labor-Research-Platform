"""
National-scale dry run: pull ALL singleton master_employers for a given state,
run blocking to generate candidate pairs, apply the rule engine, and report
tier counts + projected auto-merge/hierarchy-edge yield.

No API calls, no DB writes. Pure analysis.

Usage:
  py scripts/llm_dedup/national_dry_run.py --state NY
  py scripts/llm_dedup/national_dry_run.py --state NY --limit 50000    # test
"""
import argparse
import csv
import importlib.util
import os
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal

sys.path.insert(0, r"C:\Users\jakew\.local\bin\Labor Data Project_real")
from db_config import get_connection

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from rule_engine import classify_pair_v2, pair_from_candidate  # noqa: E402

# Load the blocking module (filename has leading digit -> can't import normally)
spec = importlib.util.spec_from_file_location('blocking', os.path.join(DIR, '01_blocking.py'))
blocking = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blocking)


def pull_state_singletons(state, limit=None):
    """Pull all singleton masters in the given state."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT setseed(0.42)")
    q = """
        WITH src_counts AS (
          SELECT master_id, COUNT(*) AS n FROM master_employer_source_ids GROUP BY master_id HAVING COUNT(*)=1
        )
        SELECT m.master_id, m.canonical_name, m.display_name, m.city, m.state,
               m.zip, m.naics, m.ein, m.source_origin, m.employee_count,
               m.is_union, m.is_public, m.is_nonprofit, m.is_federal_contractor,
               m.website, m.industry_text, m.data_quality_score
        FROM master_employers m
        JOIN src_counts s ON m.master_id = s.master_id
        WHERE m.state = %s
    """
    if limit:
        q += f" ORDER BY random() LIMIT {int(limit)}"
    cur.execute(q, (state,))
    cols = [d[0] for d in cur.description]
    records = []
    for row in cur.fetchall():
        d = {}
        for c, v in zip(cols, row):
            d[c] = float(v) if isinstance(v, Decimal) else v
        records.append(d)
    cur.close()
    conn.close()
    return records


def run_blocking(records):
    """Re-use the blocking functions from 01_blocking.py on an in-memory list."""
    all_candidates = {}
    strategies = [
        ('ein_exact', blocking.block_ein),
        ('exact_name', blocking.block_exact_name),
        ('normalized_name', blocking.block_normalized_name),
        ('sorted_tokens', blocking.block_sorted_tokens),
        ('zip_name_prefix', blocking.block_zip_name_prefix),
        ('city_name_prefix', blocking.block_city_name_prefix),
    ]
    for label, func in strategies:
        t0 = time.time()
        cands = func(records)
        for key, methods in cands.items():
            all_candidates.setdefault(key, set()).update(methods)
        print(f'  {label:20s} {len(cands):>8,} new pairs  ({time.time()-t0:.1f}s)')

    # Score + shape into candidate dicts compatible with rule engine
    by_id = {r['master_id']: r for r in records}
    scored = []
    for (id1, id2), methods in all_candidates.items():
        r1 = by_id[id1]; r2 = by_id[id2]
        scores = blocking.score_pair(r1, r2)
        scored.append({
            'id1': id1, 'id2': id2,
            'display_name_1': r1['display_name'], 'display_name_2': r2['display_name'],
            'canonical_name_1': r1['canonical_name'], 'canonical_name_2': r2['canonical_name'],
            'city_1': r1.get('city'), 'city_2': r2.get('city'),
            'zip_1': r1.get('zip'), 'zip_2': r2.get('zip'),
            'ein_1': r1.get('ein'), 'ein_2': r2.get('ein'),
            'naics_1': r1.get('naics'), 'naics_2': r2.get('naics'),
            'source_1': r1.get('source_origin'), 'source_2': r2.get('source_origin'),
            'employee_count_1': r1.get('employee_count'), 'employee_count_2': r2.get('employee_count'),
            'is_public_1': r1.get('is_public'), 'is_public_2': r2.get('is_public'),
            'is_nonprofit_1': r1.get('is_nonprofit'), 'is_nonprofit_2': r2.get('is_nonprofit'),
            'industry_1': r1.get('industry_text'), 'industry_2': r2.get('industry_text'),
            'blocking_methods': sorted(methods),
            'scores': scores,
            'classification': blocking.classify_pair(scores),  # heuristic baseline
        })
    return scored


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', default='NY')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    t0 = time.time()
    print(f'Pulling {"all" if not args.limit else args.limit} {args.state} singletons...')
    records = pull_state_singletons(args.state, limit=args.limit)
    print(f'  {len(records):,} records  ({time.time()-t0:.1f}s)')

    print('\\nRunning blocking...')
    pairs = run_blocking(records)
    print(f'  {len(pairs):,} candidate pairs generated')

    print('\\nApplying rule engine...')
    tier_counts = Counter()
    rule_counts = Counter()
    tier_A_pairs = []
    tier_B_pairs = []
    tier_C_pairs = []
    tier_D_pairs = []
    hierarchy_stats = {'H4_siblings': 0, 'H9_subsidiary': 0}
    series_parents = defaultdict(set)

    from rule_engine import (
        h4_series_anti_dup, h9_token_containment, h12_activity_suffix,
        TRAILING_TOKEN, normalize_punct_only, normalize_h8,
    )

    # Collect hierarchy edges for export
    hierarchy_edges = []  # list of dicts ready to CSV-out

    t1 = time.time()
    for p in pairs:
        pd = pair_from_candidate(p)
        cls = classify_pair_v2(pd)
        tier_counts[cls.tier] += 1
        rule_counts[cls.rule or '<none>'] += 1
        if cls.tier == 'tier_A_auto_merge':
            tier_A_pairs.append((p, cls))
        elif cls.tier == 'tier_B_high_conf':
            tier_B_pairs.append((p, cls))
        elif cls.tier == 'tier_C_review':
            tier_C_pairs.append((p, cls))
        elif cls.tier == 'tier_D_different':
            tier_D_pairs.append((p, cls))

        # Hierarchy signals (independent of tier).
        # Same semantics as extract_hierarchy.py:
        #   H4  -> SIBLING_OF (shared synthetic parent = stable prefix)
        #   H9  -> CHILD_OF  (shorter name = parent, longer = child)
        #   H12 -> CHILD_OF  (prefix + activity suffix; shorter = parent)
        if h4_series_anti_dup(pd):
            n1 = normalize_punct_only(p.get('canonical_name_1') or p.get('display_name_1') or '')
            n2 = normalize_punct_only(p.get('canonical_name_2') or p.get('display_name_2') or '')
            n1s = TRAILING_TOKEN.sub('', n1).strip()
            n2s = TRAILING_TOKEN.sub('', n2).strip()
            if n1s == n2s and len(n1s) >= 8:
                series_parents[n1s].add(p['id1'])
                series_parents[n1s].add(p['id2'])
                hierarchy_stats['H4_siblings'] += 1
                hierarchy_edges.append({
                    'rule': 'H4',
                    'master_id_1': p['id1'],
                    'master_id_2': p['id2'],
                    'parent_id': '',
                    'child_id': '',
                    'parent_candidate_name': n1s,
                    'confidence': 0.95,
                    'name_1': p.get('display_name_1'),
                    'name_2': p.get('display_name_2'),
                    'src_1': p.get('source_1'), 'src_2': p.get('source_2'),
                    'zip_1': p.get('zip_1'), 'zip_2': p.get('zip_2'),
                })
        elif h9_token_containment(pd):
            hierarchy_stats['H9_subsidiary'] += 1
            n1 = normalize_h8(p.get('canonical_name_1') or p.get('display_name_1') or '')
            n2 = normalize_h8(p.get('canonical_name_2') or p.get('display_name_2') or '')
            if len(n1.split()) <= len(n2.split()):
                parent_id, child_id, parent_name = p['id1'], p['id2'], n1
            else:
                parent_id, child_id, parent_name = p['id2'], p['id1'], n2
            hierarchy_edges.append({
                'rule': 'H9',
                'master_id_1': '', 'master_id_2': '',
                'parent_id': parent_id, 'child_id': child_id,
                'parent_candidate_name': parent_name,
                'confidence': 0.60,
                'name_1': p.get('display_name_1'), 'name_2': p.get('display_name_2'),
                'src_1': p.get('source_1'), 'src_2': p.get('source_2'),
                'zip_1': p.get('zip_1'), 'zip_2': p.get('zip_2'),
            })
        elif h12_activity_suffix(pd):
            n1 = normalize_h8(p.get('canonical_name_1') or p.get('display_name_1') or '')
            n2 = normalize_h8(p.get('canonical_name_2') or p.get('display_name_2') or '')
            if len(n1.split()) <= len(n2.split()):
                parent_id, child_id, parent_name = p['id1'], p['id2'], n1
            else:
                parent_id, child_id, parent_name = p['id2'], p['id1'], n2
            hierarchy_edges.append({
                'rule': 'H12',
                'master_id_1': '', 'master_id_2': '',
                'parent_id': parent_id, 'child_id': child_id,
                'parent_candidate_name': parent_name,
                'confidence': 0.92,
                'name_1': p.get('display_name_1'), 'name_2': p.get('display_name_2'),
                'src_1': p.get('source_1'), 'src_2': p.get('source_2'),
                'zip_1': p.get('zip_1'), 'zip_2': p.get('zip_2'),
            })

    print(f'  {time.time()-t1:.1f}s to classify all pairs')
    print()

    # Report
    print('=' * 70)
    print(f'DRY-RUN SUMMARY ({args.state} singletons)')
    print('=' * 70)
    print(f'Singletons pulled:       {len(records):>10,}')
    print(f'Candidate pairs:         {len(pairs):>10,}')
    print(f'Pairs per record:        {len(pairs)/len(records):>10.2f}')
    print()
    print('Tier distribution:')
    for t in ['tier_series_demoted', 'tier_A_auto_merge', 'tier_B_high_conf',
              'tier_C_review', 'tier_D_different']:
        n = tier_counts.get(t, 0)
        print(f'  {t:25s} {n:>10,}  ({100*n/len(pairs):.2f}%)')
    print()
    print('Hierarchy signals:')
    print(f'  H4 sibling edges:      {hierarchy_stats["H4_siblings"]:>10,}')
    print(f'  H4 distinct parents:   {len(series_parents):>10,}')
    print(f'  H9 subsidiary edges:   {hierarchy_stats["H9_subsidiary"]:>10,}')
    print()
    print('Projected outcomes (applying the Haiku-validated precisions):')
    tA = tier_counts.get('tier_A_auto_merge', 0)
    tB = tier_counts.get('tier_B_high_conf', 0)
    print(f'  Tier A auto-merges:    {tA:>10,}  (expect ~{int(tA*0.961):,} true DUPs at 96.1% prec)')
    print(f'  Tier B high-conf:      {tB:>10,}  (expect ~{int(tB*0.70):,} true DUPs at 70% prec, review recommended)')
    print(f'  Combined A+B merges:   {tA+tB:>10,}  (expect ~{int(tA*0.961+tB*0.70):,} true DUPs at 91% blended)')

    # Top series parents
    if series_parents:
        print('\\nTop 15 series-parent clusters (by member count):')
        for name, members in sorted(series_parents.items(), key=lambda kv: -len(kv[1]))[:15]:
            n = name if len(name) <= 65 else name[:62] + '...'
            print(f'  {len(members):>3d} members  | {n}')

    # Export tier A merge list
    out_csv = os.path.join(DIR, f'tier_A_dry_run_{args.state}.csv')
    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(['id1', 'id2', 'rule', 'src1', 'src2', 'name1', 'name2', 'zip1', 'zip2'])
        for p, cls in tier_A_pairs:
            w.writerow([p['id1'], p['id2'], cls.rule,
                        p.get('source_1', ''), p.get('source_2', ''),
                        p.get('display_name_1', ''), p.get('display_name_2', ''),
                        p.get('zip_1', ''), p.get('zip_2', '')])
    print(f'\\nTier A merge candidates: {out_csv}')

    # Export tier B/C/D residual pairs (used for LLM validation sampling).
    # Full pair metadata so downstream prompt can render canonical + display + EIN + etc.
    def _write_tier_csv(tier_label, pair_list):
        if not pair_list:
            return
        out = os.path.join(DIR, f'tier_{tier_label}_pairs_{args.state}.csv')
        cols = ['id1', 'id2', 'rule', 'tier', 'confidence',
                'src1', 'src2', 'name1', 'name2',
                'cname1', 'cname2', 'city1', 'city2', 'zip1', 'zip2',
                'ein1', 'ein2', 'naics1', 'naics2',
                'np1', 'np2', 'pub1', 'pub2', 'emp1', 'emp2',
                'ind1', 'ind2']
        with open(out, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(cols)
            for p, cls in pair_list:
                w.writerow([p['id1'], p['id2'], cls.rule or '', cls.tier,
                            f'{cls.expected_precision:.3f}' if cls.expected_precision else '',
                            p.get('source_1', ''), p.get('source_2', ''),
                            p.get('display_name_1', ''), p.get('display_name_2', ''),
                            p.get('canonical_name_1', ''), p.get('canonical_name_2', ''),
                            p.get('city_1', ''), p.get('city_2', ''),
                            p.get('zip_1', ''), p.get('zip_2', ''),
                            p.get('ein_1', ''), p.get('ein_2', ''),
                            p.get('naics_1', ''), p.get('naics_2', ''),
                            p.get('is_nonprofit_1', ''), p.get('is_nonprofit_2', ''),
                            p.get('is_public_1', ''), p.get('is_public_2', ''),
                            p.get('employee_count_1', ''), p.get('employee_count_2', ''),
                            p.get('industry_1', ''), p.get('industry_2', '')])
        print(f'Tier {tier_label} pairs: {out} ({len(pair_list):,} rows)')

    # Cap tier_D at 5K per state (full dump would be huge, and we only need
    # samples of UNRELATED for ground truth).
    import random
    random.seed(42)
    tier_D_sample = random.sample(tier_D_pairs, min(5000, len(tier_D_pairs)))
    _write_tier_csv('B', tier_B_pairs)
    _write_tier_csv('C', tier_C_pairs)
    _write_tier_csv('D', tier_D_sample)

    # Export hierarchy edges
    if hierarchy_edges:
        hier_csv = os.path.join(DIR, f'hierarchy_edges_{args.state}.csv')
        cols = ['rule', 'master_id_1', 'master_id_2', 'parent_id', 'child_id',
                'parent_candidate_name', 'confidence',
                'name_1', 'name_2', 'src_1', 'src_2', 'zip_1', 'zip_2']
        with open(hier_csv, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_ALL, extrasaction='ignore')
            w.writeheader()
            for e in hierarchy_edges:
                w.writerow(e)
        print(f'Hierarchy edges: {hier_csv} ({len(hierarchy_edges):,} edges)')

    print(f'\\nTotal elapsed: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
