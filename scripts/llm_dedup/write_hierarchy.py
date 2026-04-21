"""
Write rule-derived hierarchy edges to the rule_derived_hierarchy table.

Reads one or more hierarchy_edges CSV files produced by extract_hierarchy.py
(or the hierarchy-edges-per-state variant below). Assigns sibling_cluster_id
to all H4 edges sharing a parent_candidate_name. Inserts everything in a
single transaction.

Requires ddl_rule_derived_hierarchy.sql to have been applied.

Usage:
  # Default is --dry-run. Reports what would be written, writes nothing.
  py scripts/llm_dedup/write_hierarchy.py --csv scripts/llm_dedup/hierarchy_edges.csv

  # Multiple edge files (e.g., one per state):
  py scripts/llm_dedup/write_hierarchy.py --csv NY.csv CA.csv TX.csv FL.csv

  # Apply to DB (both flags required for safety):
  py scripts/llm_dedup/write_hierarchy.py --csv ... --apply --yes
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\Users\jakew\.local\bin\Labor Data Project_real")
from db_config import get_connection

DIR = os.path.dirname(os.path.abspath(__file__))


def load_edges(csv_paths):
    """Read edges from one or more hierarchy_edges CSV files. Dedupe on
    (rule, child_master_id, parent_master_id_or_cluster_name)."""
    seen = set()
    rows = []
    for path in csv_paths:
        if not os.path.exists(path):
            print(f'SKIP (not found): {path}')
            continue
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for r in reader:
                rule = (r.get('rule') or '').strip()
                if not rule:
                    continue
                # Build dedup key
                if rule == 'H4':
                    # sibling pair — dedup by (rule, sorted(child_ids))
                    m1 = int(r['master_id_1']) if r.get('master_id_1') else None
                    m2 = int(r['master_id_2']) if r.get('master_id_2') else None
                    if m1 is None or m2 is None:
                        continue
                    key = ('H4', min(m1, m2), max(m1, m2))
                elif rule in ('H9', 'H12'):
                    child = int(r['child_id']) if r.get('child_id') else None
                    parent = int(r['parent_id']) if r.get('parent_id') else None
                    if child is None or parent is None:
                        continue
                    key = (rule, child, parent)
                else:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                rows.append(r)
    return rows


def build_insert_rows(edges):
    """Transform raw CSV rows into (rule, relationship, child, parent,
    parent_name, cluster_id, confidence) tuples ready for insert.

    Sibling_cluster_id is assigned based on parent_candidate_name: all H4
    edges sharing a parent name get the same cluster_id.
    """
    # Build cluster_id map for H4
    cluster_map = {}
    next_cluster_id = 1
    for r in edges:
        if r.get('rule') != 'H4':
            continue
        name = (r.get('parent_candidate_name') or '').strip().lower()
        if not name:
            continue
        if name not in cluster_map:
            cluster_map[name] = next_cluster_id
            next_cluster_id += 1

    out = []
    for r in edges:
        rule = r.get('rule', '').strip()
        parent_name = (r.get('parent_candidate_name') or '').strip() or None
        try:
            conf = float(r.get('confidence', 0)) if r.get('confidence') else None
        except (TypeError, ValueError):
            conf = None

        if rule == 'H4':
            # Emit TWO sibling edges (one per master) all under the same cluster
            m1 = int(r['master_id_1']); m2 = int(r['master_id_2'])
            cluster = cluster_map.get((parent_name or '').lower())
            for mid in (m1, m2):
                out.append({
                    'rule': 'H4',
                    'relationship': 'SIBLING_OF',
                    'child_master_id': mid,
                    'parent_master_id': None,  # synthetic parent, no master row
                    'parent_candidate_name': parent_name,
                    'sibling_cluster_id': cluster,
                    'confidence': conf if conf is not None else 0.95,
                })
        elif rule in ('H9', 'H12'):
            child = int(r['child_id']); parent = int(r['parent_id'])
            if child == parent:
                continue
            out.append({
                'rule': rule,
                'relationship': 'CHILD_OF',
                'child_master_id': child,
                'parent_master_id': parent,
                'parent_candidate_name': parent_name,
                'sibling_cluster_id': None,
                'confidence': conf if conf is not None else (0.92 if rule == 'H12' else 0.60),
            })
    return out, len(cluster_map)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', nargs='+', required=True,
                    help='one or more hierarchy_edges CSV files')
    ap.add_argument('--apply', action='store_true',
                    help='actually write to DB (default: dry-run)')
    ap.add_argument('--yes', action='store_true',
                    help='required with --apply for safety')
    ap.add_argument('--source', default='rule_engine_v1',
                    help='source label for inserted rows')
    args = ap.parse_args()

    if args.apply and not args.yes:
        print('ERROR: --apply requires --yes')
        return 1

    print(f'Reading {len(args.csv)} edge file(s)...')
    edges = load_edges(args.csv)
    print(f'  {len(edges):,} unique edges loaded')

    insert_rows, cluster_count = build_insert_rows(edges)
    print(f'  -> {len(insert_rows):,} DB rows to insert ({cluster_count} sibling clusters)')

    # Breakdown
    by_rule = defaultdict(int)
    for r in insert_rows:
        by_rule[r['rule']] += 1
    print('  By rule:')
    for rule in ('H4', 'H9', 'H12'):
        print(f'    {rule:5s} {by_rule.get(rule, 0):>8,}')

    # Master_id validation: warn if any referenced master_ids are missing
    print('\nValidating master_ids against DB...')
    all_ids = set()
    for r in insert_rows:
        if r['child_master_id'] is not None:
            all_ids.add(r['child_master_id'])
        if r['parent_master_id'] is not None:
            all_ids.add(r['parent_master_id'])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT master_id FROM master_employers WHERE master_id = ANY(%s)",
        (list(all_ids),),
    )
    live_ids = {r[0] for r in cur.fetchall()}
    missing = all_ids - live_ids
    print(f'  {len(live_ids):,} of {len(all_ids):,} master_ids live in DB')
    if missing:
        print(f'  WARNING: {len(missing):,} master_ids missing (possibly already merged). '
              'Rows referencing them will be skipped.')

    # Filter out rows with missing master_ids
    filtered = []
    for r in insert_rows:
        if r['child_master_id'] and r['child_master_id'] not in live_ids:
            continue
        if r['parent_master_id'] and r['parent_master_id'] not in live_ids:
            continue
        filtered.append(r)
    print(f'  Final insertable rows: {len(filtered):,} '
          f'(dropped {len(insert_rows) - len(filtered):,})')

    # Confirm table exists
    cur.execute("""SELECT 1 FROM information_schema.tables
                   WHERE table_name='rule_derived_hierarchy'""")
    if not cur.fetchone():
        print('\nERROR: rule_derived_hierarchy table does not exist.')
        print('Apply the DDL first:')
        print('  psql ... -f scripts/llm_dedup/ddl_rule_derived_hierarchy.sql')
        conn.close()
        return 1

    if not args.apply:
        print('\n*** DRY RUN -- no database writes. Use --apply --yes to execute. ***')
        conn.close()
        return 0

    # Insert in a single transaction
    print(f'\nInserting {len(filtered):,} rows...')
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        """
        INSERT INTO rule_derived_hierarchy
          (rule, relationship, child_master_id, parent_master_id,
           parent_candidate_name, sibling_cluster_id, confidence, source)
        VALUES %s
        """,
        [(r['rule'], r['relationship'], r['child_master_id'],
          r['parent_master_id'], r['parent_candidate_name'],
          r['sibling_cluster_id'], r['confidence'], args.source)
         for r in filtered],
        page_size=1000,
    )
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM rule_derived_hierarchy WHERE source=%s", (args.source,))
    total = cur.fetchone()[0]
    print(f'Done. Table now has {total:,} rows for source={args.source}.')
    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
