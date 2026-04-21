"""
Hierarchy extraction from LLM-RELATED / non-merge pair classifications.

The rule engine's merge tiers (A, B) handle *duplicate* decisions. But many
pairs the LLM marked RELATED are also valuable: they reveal parent/subsidiary
/ fund-family / chapter relationships that should populate a hierarchy graph.

This script emits three kinds of hierarchy edges, one per rule that fires:

  1. H4 (series/numbered variants) -> SIBLING_OF relationship
     Both records share a "stable prefix" that is the parent umbrella.
     Example: "DEFINED ASSET FUNDS MUNICIPAL INVT TR FD MON SER 253" and
              "DEFINED ASSET FUNDS MUNICIPAL INVT TR FD MON SER 457"
              -> parent_candidate = "DEFINED ASSET FUNDS MUNICIPAL INVT TR FD MON"
              -> both masters are siblings under that parent

  2. H9 (shorter tokens contained in longer) -> CHILD_OF relationship
     Shorter name is the parent, longer name is a subsidiary/division.
     Example: "CBS BROADCASTING INC" inside "CBS BROADCASTING INC (WBBM-TV)"
              -> longer master is child of shorter master

  3. H12 (prefix + activity suffix) -> CHILD_OF (activity division)
     Same as H9 but the extra tokens are activity descriptors.
     Example: "Bland Farms" parent of "Bland Farms Production and Packing"

All edges are candidates, not confirmed truth. They feed a new
`rule_derived_hierarchy` table for human review or downstream merging into
`corporate_hierarchy` / `corporate_ultimate_parents`.

Output: hierarchy_edges.csv with columns:
  rule, relationship, child_master_id, parent_master_id_or_null,
  parent_candidate_name, source_rule_confidence, src_pair_context
"""
import csv
import json
import os
import sys
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from rule_engine import (
    h4_series_anti_dup, h9_token_containment, h12_activity_suffix,
    normalize_punct_only, normalize_h8, TRAILING_TOKEN, pair_from_candidate,
)

CANDIDATES = os.path.join(DIR, 'candidates_singletons_scored.json')
OUT_CSV = os.path.join(DIR, 'hierarchy_edges.csv')
OUT_SUMMARY = os.path.join(DIR, 'hierarchy_extraction_summary.json')


def extract_series_parent(name1, name2):
    """Given two names that differ only by trailing series/numeric token,
    return the shared stable prefix as the parent-candidate name."""
    n1 = normalize_punct_only(name1)
    n2 = normalize_punct_only(name2)
    n1_stripped = TRAILING_TOKEN.sub('', n1).strip()
    n2_stripped = TRAILING_TOKEN.sub('', n2).strip()
    if n1_stripped == n2_stripped:
        return n1_stripped
    return None


def extract_containment_parent_child(pair):
    """For H9/H12 fires, return (parent_id, child_id, parent_name).
    The shorter name's master_id is the parent."""
    n1 = normalize_h8(pair.get('canonical_name_1') or pair.get('display_name_1') or '')
    n2 = normalize_h8(pair.get('canonical_name_2') or pair.get('display_name_2') or '')
    t1 = len(n1.split())
    t2 = len(n2.split())
    if t1 <= t2:
        return (pair['id1'], pair['id2'], n1)  # side 1 is parent
    else:
        return (pair['id2'], pair['id1'], n2)  # side 2 is parent


def main():
    with open(CANDIDATES) as f:
        pairs = json.load(f)

    print(f'Scanning {len(pairs):,} candidate pairs for hierarchy signals...')

    edges = []
    series_parents = defaultdict(set)  # parent_name -> {master_id1, master_id2, ...}
    stats = {'H4_siblings': 0, 'H9_subsidiary': 0, 'H12_activity_division': 0}

    for p in pairs:
        pd = pair_from_candidate(p)

        # H4 -> sibling relationship
        if h4_series_anti_dup(pd):
            parent = extract_series_parent(
                p.get('canonical_name_1') or p.get('display_name_1') or '',
                p.get('canonical_name_2') or p.get('display_name_2') or '',
            )
            if parent and len(parent) >= 8:
                series_parents[parent].add(p['id1'])
                series_parents[parent].add(p['id2'])
                stats['H4_siblings'] += 1
                edges.append({
                    'rule': 'H4',
                    'relationship': 'SIBLING_OF',
                    'master_id_1': p['id1'],
                    'master_id_2': p['id2'],
                    'parent_candidate_name': parent,
                    'confidence': 0.95,
                    'name_1': p.get('display_name_1'),
                    'name_2': p.get('display_name_2'),
                    'src_1': p.get('source_1'),
                    'src_2': p.get('source_2'),
                    'zip_1': p.get('zip_1'),
                    'zip_2': p.get('zip_2'),
                })

        # H9 -> subsidiary relationship
        elif h9_token_containment(pd):
            parent_id, child_id, parent_name = extract_containment_parent_child(p)
            stats['H9_subsidiary'] += 1
            edges.append({
                'rule': 'H9',
                'relationship': 'CHILD_OF',
                'child_id': child_id,
                'parent_id': parent_id,
                'parent_candidate_name': parent_name,
                'confidence': 0.60,   # H9 alone was 58.7% precision as DUP; use that as base
                'name_1': p.get('display_name_1'),
                'name_2': p.get('display_name_2'),
                'src_1': p.get('source_1'),
                'src_2': p.get('source_2'),
            })

        # H12 -> activity-division relationship
        elif h12_activity_suffix(pd):
            parent_id, child_id, parent_name = extract_containment_parent_child(p)
            stats['H12_activity_division'] += 1
            edges.append({
                'rule': 'H12',
                'relationship': 'CHILD_OF',
                'child_id': child_id,
                'parent_id': parent_id,
                'parent_candidate_name': parent_name,
                'confidence': 0.92,   # H12 was 91.8% precision
                'name_1': p.get('display_name_1'),
                'name_2': p.get('display_name_2'),
                'src_1': p.get('source_1'),
                'src_2': p.get('source_2'),
            })

    # Consolidate series siblings into one-row-per-parent-cluster
    # (each parent name with N siblings = N-1 pair edges collapse to 1 cluster)
    sibling_clusters = []
    for parent, masters in series_parents.items():
        if len(masters) < 2:
            continue
        sibling_clusters.append({
            'parent_candidate_name': parent,
            'member_count': len(masters),
            'member_master_ids': sorted(masters),
        })
    sibling_clusters.sort(key=lambda c: -c['member_count'])

    # Write edges CSV
    all_cols = ['rule', 'relationship', 'parent_candidate_name', 'confidence',
                'master_id_1', 'master_id_2', 'parent_id', 'child_id',
                'name_1', 'name_2', 'src_1', 'src_2', 'zip_1', 'zip_2']
    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=all_cols, quoting=csv.QUOTE_ALL, extrasaction='ignore')
        w.writeheader()
        for e in edges:
            w.writerow(e)

    # Summary stats
    summary = {
        'total_pairs_scanned': len(pairs),
        'edges': stats,
        'total_edges': len(edges),
        'distinct_series_parent_candidates': len(sibling_clusters),
        'top_20_series_parents': sibling_clusters[:20],
        'distinct_subsidiary_parents_h9': len(set(e.get('parent_id') for e in edges if e['rule'] == 'H9')),
        'distinct_activity_parents_h12': len(set(e.get('parent_id') for e in edges if e['rule'] == 'H12')),
    }
    with open(OUT_SUMMARY, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, default=str)

    # Report
    print()
    print('Edges extracted:')
    for k, v in stats.items():
        print(f'  {k:25s} {v:>6,}')
    print(f'\\nTotal edges: {len(edges):,}')
    print(f'Distinct series-parent clusters: {len(sibling_clusters):,}')
    print(f'Distinct H9 subsidiary parents:  {summary["distinct_subsidiary_parents_h9"]:,}')
    print(f'Distinct H12 activity parents:   {summary["distinct_activity_parents_h12"]:,}')
    print()
    print('Top 10 series-parent clusters by member count:')
    for c in sibling_clusters[:10]:
        name = c['parent_candidate_name']
        if len(name) > 65:
            name = name[:62] + '...'
        print(f'  {c["member_count"]:>3d} members  | {name}')

    print(f'\\nEdges CSV: {OUT_CSV}')
    print(f'Summary:   {OUT_SUMMARY}')


if __name__ == '__main__':
    main()
