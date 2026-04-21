"""Analyze H4 sibling cluster size distribution + sample small clusters.

Groups all H4 edges from the 4 hierarchy CSVs by parent_candidate_name,
counts distinct masters per parent, and prints:
  1. Size distribution (how many clusters at each size)
  2. Sample of smallest clusters (2-member, 3-member)
  3. All MOSTLY_GENERIC-like candidates (2-token parent with danger keyword)
"""
import csv
import glob
import os
from collections import defaultdict

DANGER_KEYWORDS = {
    'partners', 'fund', 'funds', 'capital', 'holdings', 'group',
    'trust', 'ventures', 'portfolio', 'portfolios', 'global',
    'investments', 'management', 'advisors', 'partner',
}

def is_mostly_generic(parent_name):
    """Heuristic: 2-token name with one in danger_keywords and other token <5 chars."""
    tokens = parent_name.split()
    if len(tokens) != 2:
        return False
    t0, t1 = tokens[0], tokens[1]
    has_danger = t0 in DANGER_KEYWORDS or t1 in DANGER_KEYWORDS
    distinct_tok = t1 if t0 in DANGER_KEYWORDS else t0
    return has_danger and len(distinct_tok) < 5


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    csvs = sorted(glob.glob(os.path.join(here, 'hierarchy_edges_*.csv')))
    print(f'Reading {len(csvs)} state CSVs...')

    # Per parent_name: set of master_ids involved, list of sample (name_1, name_2) tuples
    cluster_masters = defaultdict(set)
    cluster_samples = defaultdict(list)
    cluster_sources = defaultdict(set)
    cluster_states = defaultdict(set)

    for path in csvs:
        state = os.path.basename(path).split('_')[-1].split('.')[0]
        with open(path, 'r', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r['rule'] != 'H4':
                    continue
                p = r['parent_candidate_name']
                try:
                    m1 = int(r['master_id_1']) if r['master_id_1'] else None
                    m2 = int(r['master_id_2']) if r['master_id_2'] else None
                except ValueError:
                    continue
                if m1: cluster_masters[p].add(m1)
                if m2: cluster_masters[p].add(m2)
                cluster_states[p].add(state)
                if r.get('src_1'): cluster_sources[p].add(r['src_1'])
                if r.get('src_2'): cluster_sources[p].add(r['src_2'])
                if len(cluster_samples[p]) < 4:
                    cluster_samples[p].append((r['name_1'], r['name_2']))

    # Build (name, size, n_sources, n_states) table
    clusters = []
    for p, masters in cluster_masters.items():
        clusters.append({
            'parent': p,
            'size': len(masters),
            'n_sources': len(cluster_sources[p]),
            'n_states': len(cluster_states[p]),
            'states': sorted(cluster_states[p]),
            'sources': sorted(cluster_sources[p]),
            'samples': cluster_samples[p],
            'n_tokens': len(p.split()),
            'mostly_generic': is_mostly_generic(p),
        })

    print(f'\n=== SIZE DISTRIBUTION ({len(clusters):,} distinct H4 parents) ===')
    size_hist = defaultdict(int)
    for c in clusters:
        size_hist[c['size']] += 1
    cum = 0
    total = len(clusters)
    for sz in sorted(size_hist):
        n = size_hist[sz]
        cum += n
        pct = 100 * n / total
        cum_pct = 100 * cum / total
        if sz <= 10 or sz in (15, 20, 30, 50, 100, 181):
            print(f'  size {sz:>4}: {n:>6,} clusters  ({pct:5.1f}%, cum {cum_pct:5.1f}%)')

    print('\n=== TOKEN COUNT DISTRIBUTION ===')
    tok_hist = defaultdict(int)
    for c in clusters:
        tok_hist[c['n_tokens']] += 1
    for ntok in sorted(tok_hist):
        n = tok_hist[ntok]
        print(f'  {ntok} tokens: {n:>6,} clusters  ({100*n/total:5.1f}%)')

    print('\n=== MOSTLY_GENERIC (2-token + danger keyword + <5char other) ===')
    mg = [c for c in clusters if c['mostly_generic']]
    print(f'  {len(mg)} clusters flagged')
    for c in sorted(mg, key=lambda x: -x['size'])[:40]:
        sample = ' | '.join(f'{a}' for a, b in c['samples'][:2])
        print(f'  size={c["size"]:<3} src={c["n_sources"]} st={c["n_states"]} '
              f'"{c["parent"]}"  -- {sample}')

    print('\n=== SMALL CLUSTERS: 2 members (sample of 30) ===')
    small2 = [c for c in clusters if c['size'] == 2]
    print(f'  {len(small2):,} total 2-member clusters')
    # Sample across source diversity
    for c in sorted(small2, key=lambda x: (-x['n_sources'], x['parent']))[:30]:
        sample = c['samples'][0] if c['samples'] else ('', '')
        print(f'  [{c["n_sources"]} src] "{c["parent"]}"  -- {sample[0]} | {sample[1]}')

    print('\n=== SMALL CLUSTERS: 3 members (sample of 20) ===')
    small3 = [c for c in clusters if c['size'] == 3]
    print(f'  {len(small3):,} total 3-member clusters')
    for c in sorted(small3, key=lambda x: (-x['n_sources'], x['parent']))[:20]:
        sample = ' | '.join(a for a, b in c['samples'][:2])
        print(f'  [{c["n_sources"]} src] "{c["parent"]}"  -- {sample}')

    print('\n=== SOURCE HOMOGENEITY breakdown ===')
    src_hist = defaultdict(int)
    for c in clusters:
        src_hist[c['n_sources']] += 1
    for n in sorted(src_hist):
        cnt = src_hist[n]
        print(f'  {n} distinct source systems: {cnt:>6,} clusters  ({100*cnt/total:5.1f}%)')

    # Write a filtered CSV for manual review
    out_path = os.path.join(here, 'small_h4_clusters_for_review.csv')
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['DECISION', 'parent', 'size', 'n_sources', 'n_states',
                    'n_tokens', 'mostly_generic', 'sources', 'sample_1', 'sample_2'])
        for c in sorted(clusters, key=lambda x: (x['size'], -x['n_tokens'], x['parent'])):
            if c['size'] > 3:
                continue  # small only
            s1 = c['samples'][0][0] if c['samples'] else ''
            s2 = c['samples'][0][1] if c['samples'] else ''
            w.writerow(['', c['parent'], c['size'], c['n_sources'], c['n_states'],
                        c['n_tokens'], 'Y' if c['mostly_generic'] else '',
                        ','.join(c['sources']), s1, s2])
    print(f'\nWrote small-cluster review CSV: {out_path}')
    print(f'  {sum(1 for c in clusters if c["size"] <= 3):,} rows (clusters with size <= 3)')


if __name__ == '__main__':
    main()
