"""
Apply Tier A rule-engine merge decisions to master_employer_merge_log.

Reads a Tier A CSV (output of national_dry_run.py), clusters pairs into
transitive groups via union-find, picks a winner per cluster using data
quality heuristics, and merges each cluster's losers into its winner
via the existing `merge_one()` procedure in dedup_master_employers.py.

DESTRUCTIVE OPERATION: each merge DELETEs the loser row from master_employers
and moves source_ids to the winner. Reversal requires restore from backup.

Usage:
  # Default is --dry-run; prints what WOULD happen, writes nothing.
  py scripts/llm_dedup/apply_rule_merges.py --csv scripts/llm_dedup/tier_A_dry_run_NY.csv

  # To actually apply, both flags required.
  py scripts/llm_dedup/apply_rule_merges.py --csv ... --apply --yes

  # Run in batches with commit every N merges (safer on long runs).
  py scripts/llm_dedup/apply_rule_merges.py --csv ... --apply --yes --batch 500
"""
import argparse
import csv
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, r"C:\Users\jakew\.local\bin\Labor Data Project_real")
from db_config import get_connection

# Reuse the existing merge implementation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'etl'))
import dedup_master_employers  # noqa: E402
from dedup_master_employers import merge_one  # noqa: E402

# MERGE_LOG_HAS_REASON / MERGE_LOG_HAS_MERGED_BY are set inside the module's
# main() via `global`. When we import merge_one directly, main() never runs
# and those globals don't exist -- causing NameError inside merge_one.
# Both columns exist in the live schema (confirmed 2026-04-17 DB introspection),
# so set them True at import time.
dedup_master_employers.MERGE_LOG_HAS_REASON = True
dedup_master_employers.MERGE_LOG_HAS_MERGED_BY = True


class UnionFind:
    def __init__(self):
        self.parent = {}
    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            return x
        # Path compression
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root
    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            # Keep the smaller id as the root for determinism
            if rx < ry:
                self.parent[ry] = rx
            else:
                self.parent[rx] = ry


def pick_winner(cluster_ids, employer_rows):
    """Pick the winner master_id within a cluster.
    Priority:
      1. Master with most source_ids (from n_sources dict)
      2. Master with non-null EIN
      3. Lowest master_id (tiebreak, deterministic)
    """
    candidates = [e for e in employer_rows if e.mid in cluster_ids]
    if not candidates:
        return min(cluster_ids)
    # Priority tuple for max():
    #   (n_sources, has_ein, -master_id)  -- higher n_sources, then has ein, then lower id
    def key(e):
        return (getattr(e, 'n_sources', 0),
                1 if (e.ein and e.ein.strip()) else 0,
                -e.mid)
    return max(candidates, key=key).mid


def load_cluster_members(conn, master_ids):
    """Fetch Employer rows for all master_ids. Uses fetch_employers() from
    dedup_master_employers.py to populate all dataclass fields including
    has_f7. Then augments each with n_sources for winner selection."""
    if not master_ids:
        return {}
    from dedup_master_employers import fetch_employers
    cur = conn.cursor()
    employers = fetch_employers(cur, pk_col='master_id', ids=list(master_ids),
                                include_labor_org=True)
    rows = {e.mid: e for e in employers}
    # Augment with n_sources
    cur.execute("""
        SELECT master_id, COUNT(*) FROM master_employer_source_ids
        WHERE master_id = ANY(%s) GROUP BY master_id
    """, (list(master_ids),))
    for mid, n in cur.fetchall():
        if mid in rows:
            rows[mid].n_sources = n
    cur.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True, help='Tier A CSV path')
    ap.add_argument('--apply', action='store_true', help='actually write to DB (default: dry-run)')
    ap.add_argument('--yes', action='store_true', help='required with --apply for safety')
    ap.add_argument('--batch', type=int, default=500, help='commit every N merges')
    ap.add_argument('--phase', default='rule_engine_v1', help='merge_phase label')
    args = ap.parse_args()

    if args.apply and not args.yes:
        print('ERROR: --apply requires --yes')
        return 1

    print(f'Reading {args.csv}')
    with open(args.csv, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f'  {len(rows):,} input pairs')

    # Union-find over all pairs
    uf = UnionFind()
    rules_by_pair = {}
    for r in rows:
        id1 = int(r['id1']); id2 = int(r['id2'])
        uf.union(id1, id2)
        # Keep the best rule per cluster-pair
        rules_by_pair[(min(id1, id2), max(id1, id2))] = r['rule']

    # Build clusters
    clusters = defaultdict(set)
    for mid in uf.parent:
        clusters[uf.find(mid)].add(mid)
    all_ids = set(uf.parent.keys())
    print(f'  {len(all_ids):,} distinct masters across pairs')
    print(f'  {len(clusters):,} clusters after union-find')
    size_dist = defaultdict(int)
    for c in clusters.values():
        size_dist[len(c)] += 1
    print('  Cluster size distribution:')
    for sz in sorted(size_dist):
        n = size_dist[sz]
        if sz >= 5 or n >= 50:
            print(f'    size {sz}: {n:,} clusters')

    # Load Employer rows for all masters
    print('\nLoading master_employer rows...')
    conn = get_connection()
    employers = load_cluster_members(conn, all_ids)
    print(f'  {len(employers):,}/{len(all_ids):,} masters found in DB')
    missing = all_ids - set(employers.keys())
    if missing:
        print(f'  WARNING: {len(missing):,} masters missing from DB '
              '(likely already merged in a prior run). They will be skipped.')

    # Plan merges per cluster
    print('\nPlanning merges per cluster...')
    total_merges = 0
    merge_plan = []  # list of (winner_id, loser_id, rule, conf)
    for cluster in clusters.values():
        alive = [mid for mid in cluster if mid in employers]
        if len(alive) < 2:
            continue
        winner_id = pick_winner(alive, [employers[m] for m in alive])
        losers = [m for m in alive if m != winner_id]
        for loser_id in losers:
            pair_key = (min(winner_id, loser_id), max(winner_id, loser_id))
            rule = rules_by_pair.get(pair_key, 'transitive')
            conf = {'H2+H3': 0.96, 'H6+H3': 0.96, 'H11': 1.00,
                    'H2+H6': 0.91, 'transitive': 0.85}.get(rule, 0.90)
            merge_plan.append((winner_id, loser_id, rule, conf))
            total_merges += 1

    print(f'  {total_merges:,} total merges planned (= masters to be deleted)')
    rule_counts = defaultdict(int)
    for _, _, r, _ in merge_plan:
        rule_counts[r] += 1
    print('  By rule:')
    for r, n in sorted(rule_counts.items(), key=lambda kv: -kv[1]):
        print(f'    {r:15s} {n:>6,}')

    if not args.apply:
        print('\n*** DRY RUN -- no database writes. Use --apply --yes to execute. ***')
        conn.close()
        return 0

    # Apply
    print(f'\nApplying {total_merges:,} merges (commit every {args.batch})...')
    cur = conn.cursor()
    applied = 0
    errors = 0
    t0 = time.time()
    for winner_id, loser_id, rule, conf in merge_plan:
        winner = employers.get(winner_id)
        loser = employers.get(loser_id)
        if not winner or not loser:
            errors += 1
            continue
        try:
            merge_one(
                cur, pk_col='master_id', include_labor_org=True,
                winner=winner, loser=loser,
                phase=args.phase,
                conf=conf,
                ev={'rule': rule, 'source': 'rule_engine_v1',
                    'winner_n_sources': getattr(winner, 'n_sources', 0),
                    'loser_n_sources': getattr(loser, 'n_sources', 0)},
            )
            applied += 1
            # Remove the loser from our in-memory dict to avoid double-processing
            employers.pop(loser_id, None)
        except Exception as e:
            errors += 1
            print(f'  ERROR on merge {winner_id} <- {loser_id}: {type(e).__name__}: {e}')
            conn.rollback()
            cur = conn.cursor()
            continue

        if applied % args.batch == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = applied / elapsed if elapsed > 0 else 0
            eta = (total_merges - applied) / rate if rate > 0 else 0
            print(f'  {applied:,}/{total_merges:,}  ({rate:.1f}/s, ETA {eta/60:.1f} min)')
    conn.commit()
    cur.close()
    conn.close()
    elapsed = time.time() - t0
    print(f'\nDone. Applied {applied:,} merges in {elapsed:.1f}s. Errors: {errors}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
