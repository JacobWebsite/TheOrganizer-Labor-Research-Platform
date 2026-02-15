"""
Enhanced merge script for F7 employer duplicates.

Fixes from the original merge_f7_duplicates.py:
  1. Uses f7_employers_deduped (not f7_employers)
  2. Updates ALL 5 downstream tables (not just 2)
  3. Uses SAVEPOINT per merge for error recovery (not full rollback)
  4. Commits in batches of 100
  5. Enhanced audit log with per-table counts

Downstream tables updated:
  - f7_union_employer_relations  (employer_id)
  - nlrb_voluntary_recognition   (matched_employer_id)
  - nlrb_participants             (matched_employer_id)
  - osha_f7_matches              (f7_employer_id) -- with conflict handling
  - mergent_employers            (matched_f7_employer_id)
  - corporate_identifier_crosswalk (f7_employer_id) -- COALESCE or re-point

Usage:
    python scripts/cleanup/merge_f7_enhanced.py                      # DRY RUN (default)
    python scripts/cleanup/merge_f7_enhanced.py --apply              # Apply merges
    python scripts/cleanup/merge_f7_enhanced.py --include-diff-cities  # Include different cities
    python scripts/cleanup/merge_f7_enhanced.py --min-score 0.95     # Custom threshold
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import sys
import os
from datetime import datetime
from collections import defaultdict

from db_config import get_connection
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DRY_RUN = '--apply' not in sys.argv
INCLUDE_DIFF_CITIES = '--include-diff-cities' in sys.argv
BATCH_SIZE = 100

# Input source: 'pgtrgm' (default) or 'combined' (Splink-rescored evidence)
SOURCE_MODE = 'pgtrgm'
CLASSIFICATION_FILTER = None  # e.g., 'SPLINK_CONFIRMED', 'AUTO_MERGE', 'NEW_MATCH'
for i, arg in enumerate(sys.argv):
    if arg == '--source' and i + 1 < len(sys.argv):
        SOURCE_MODE = sys.argv[i + 1]
    if arg == '--classification' and i + 1 < len(sys.argv):
        CLASSIFICATION_FILTER = sys.argv[i + 1]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Parse --min-score if provided
MIN_SCORE = 0.9
for arg in sys.argv:
    if arg.startswith('--min-score'):
        if '=' in arg:
            MIN_SCORE = float(arg.split('=')[1])
        else:
            idx = sys.argv.index(arg)
            if idx + 1 < len(sys.argv):
                MIN_SCORE = float(sys.argv[idx + 1])

if SOURCE_MODE == 'combined':
    CSV_FILE = os.path.join(BASE_DIR, 'data', 'f7_combined_dedup_evidence.csv')
else:
    CSV_FILE = os.path.join(BASE_DIR, 'output', 'f7_internal_duplicates.csv')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_city(city):
    """Normalize city name for comparison."""
    if not city:
        return ''
    return city.strip().upper().replace(',', '').replace('.', '').replace('  ', ' ')


def cities_match(city1, city2):
    """
    Check if two cities are the same or typos of each other.
    Returns True only for same city or very close typos.
    """
    c1 = normalize_city(city1)
    c2 = normalize_city(city2)

    if c1 == c2:
        return True
    if not c1 and not c2:
        return True
    if not c1 or not c2:
        return False

    # Short abbreviation is substring of other
    if len(c1) <= 4 and c1 in c2:
        return True
    if len(c2) <= 4 and c2 in c1:
        return True

    # Similar length - check for typos (edit distance approximation)
    if abs(len(c1) - len(c2)) <= 2:
        shorter, longer = (c1, c2) if len(c1) <= len(c2) else (c2, c1)
        if len(shorter) >= 4:
            diffs = 0
            for i, char in enumerate(shorter):
                if i < len(longer) and char != longer[i]:
                    diffs += 1
            diffs += len(longer) - len(shorter)
            if diffs <= 2:
                return True

    return False


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------
_parent = {}

def find(x):
    if x not in _parent:
        _parent[x] = x
    if _parent[x] != x:
        _parent[x] = find(_parent[x])
    return _parent[x]

def union(x, y):
    px, py = find(x), find(y)
    if px != py:
        _parent[px] = py


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("F7 Employer Duplicate Merge - Enhanced")
    print("=" * 70)
    print("Mode: %s" % ('DRY RUN' if DRY_RUN else '*** APPLYING CHANGES ***'))
    print("Source: %s%s" % (SOURCE_MODE, ' (classification=%s)' % CLASSIFICATION_FILTER if CLASSIFICATION_FILTER else ''))
    print("Minimum score: %s" % MIN_SCORE)
    print("City filter: %s" % (
        'DISABLED (including different cities)' if INCLUDE_DIFF_CITIES
        else 'ENABLED (same city only)'
    ))
    print("CSV: %s" % CSV_FILE)
    print()

    # =================================================================
    # Step 1: Load and filter duplicate pairs from CSV
    # =================================================================
    print("Step 1: Loading duplicate pairs from CSV...")

    all_pairs = []
    same_city_pairs = []
    diff_city_pairs = []

    if SOURCE_MODE == 'combined':
        # Load from combined Splink+pg_trgm evidence CSV
        print("  Source: combined evidence (classification=%s)" % CLASSIFICATION_FILTER)
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if CLASSIFICATION_FILTER and row['classification'] != CLASSIFICATION_FILTER:
                    continue
                # Use splink_prob as primary score, fall back to pgtrgm
                score_str = row.get('splink_prob') or row.get('pgtrgm_combined') or '0'
                score = float(score_str) if score_str else 0.0
                pair = {
                    'id1': row['id1'],
                    'name1': row['name1'],
                    'city1': row['city1'],
                    'state1': row['state1'],
                    'size1': int(row['size1']) if row['size1'] else 0,
                    'id2': row['id2'],
                    'name2': row['name2'],
                    'city2': row['city2'],
                    'state2': row['state2'],
                    'size2': int(row['size2']) if row['size2'] else 0,
                    'score': score,
                }
                all_pairs.append(pair)

                if cities_match(row['city1'], row['city2']):
                    same_city_pairs.append(pair)
                else:
                    diff_city_pairs.append(pair)
    else:
        # Load from original pg_trgm CSV
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                score = float(row['Combined_Score'])
                if score >= MIN_SCORE:
                    pair = {
                        'id1': row['ID1'],
                        'name1': row['Name1'],
                        'city1': row['City1'],
                        'state1': row['State1'],
                        'size1': int(row['Size1']) if row['Size1'] else 0,
                        'id2': row['ID2'],
                        'name2': row['Name2'],
                        'city2': row['City2'],
                        'state2': row['State2'],
                        'size2': int(row['Size2']) if row['Size2'] else 0,
                        'score': score,
                    }
                    all_pairs.append(pair)

                    if cities_match(row['City1'], row['City2']):
                        same_city_pairs.append(pair)
                    else:
                        diff_city_pairs.append(pair)

    print("  Total pairs loaded: %d" % len(all_pairs))
    print("    - Same city (or typo): %d (will merge)" % len(same_city_pairs))
    print("    - Different cities:    %d (skipped)" % len(diff_city_pairs))

    if INCLUDE_DIFF_CITIES:
        print("\n  WARNING: --include-diff-cities flag set, merging ALL pairs!")
        duplicate_pairs = all_pairs
    else:
        duplicate_pairs = same_city_pairs

    print("  Pairs to process: %d" % len(duplicate_pairs))

    if not duplicate_pairs:
        print("\nNo pairs to merge. Exiting.")
        cur.close()
        conn.close()
        return

    # =================================================================
    # Step 2: Build merge graph (union-find for transitive groups)
    # =================================================================
    print("\nStep 2: Building merge graph (union-find)...")

    for pair in duplicate_pairs:
        union(pair['id1'], pair['id2'])

    all_ids = set()
    for pair in duplicate_pairs:
        all_ids.add(pair['id1'])
        all_ids.add(pair['id2'])

    groups = defaultdict(set)
    for emp_id in all_ids:
        root = find(emp_id)
        groups[root].add(emp_id)

    merge_groups = {k: v for k, v in groups.items() if len(v) > 1}

    total_merges = sum(len(g) - 1 for g in merge_groups.values())
    print("  Unique employer IDs involved: %d" % len(all_ids))
    print("  Merge groups (connected components): %d" % len(merge_groups))
    print("  Total merges to perform: %d" % total_merges)

    # Show group size distribution
    size_dist = defaultdict(int)
    for g in merge_groups.values():
        size_dist[len(g)] += 1
    for sz in sorted(size_dist.keys()):
        print("    Groups of size %d: %d" % (sz, size_dist[sz]))

    # =================================================================
    # Step 3: Determine keeper for each group
    # =================================================================
    print("\nStep 3: Fetching employer details and determining keepers...")

    id_list = list(all_ids)
    cur.execute("""
        SELECT employer_id, employer_name, city, state, latest_unit_size,
               (SELECT COUNT(*)
                FROM f7_union_employer_relations
                WHERE employer_id = e.employer_id) AS notice_count
        FROM f7_employers_deduped e
        WHERE employer_id = ANY(%s)
    """, (id_list,))

    employer_details = {row['employer_id']: dict(row) for row in cur.fetchall()}

    # Build a score lookup for pairs (keyed both directions)
    pair_scores = {}
    for pair in duplicate_pairs:
        pair_scores[(pair['id1'], pair['id2'])] = pair['score']
        pair_scores[(pair['id2'], pair['id1'])] = pair['score']

    merge_decisions = []

    for root, group_ids in merge_groups.items():
        group_employers = [
            employer_details[eid] for eid in group_ids if eid in employer_details
        ]
        if len(group_employers) < 2:
            continue

        # Keeper: largest unit_size -> most notices -> alphabetical name
        group_employers.sort(
            key=lambda x: (
                -(x['latest_unit_size'] or 0),
                -(x['notice_count']),
                x['employer_name'] or '',
            ),
        )

        keeper = group_employers[0]
        for emp in group_employers[1:]:
            pair_score = pair_scores.get(
                (keeper['employer_id'], emp['employer_id']), MIN_SCORE
            )
            merge_decisions.append({
                'kept_id': keeper['employer_id'],
                'kept_name': keeper['employer_name'],
                'kept_city': keeper['city'],
                'kept_state': keeper['state'],
                'kept_size': keeper['latest_unit_size'],
                'kept_notices': keeper['notice_count'],
                'deleted_id': emp['employer_id'],
                'deleted_name': emp['employer_name'],
                'deleted_city': emp['city'],
                'deleted_state': emp['state'],
                'deleted_size': emp['latest_unit_size'],
                'deleted_notices': emp['notice_count'],
                'score': pair_score,
            })

    print("  Merge decisions prepared: %d" % len(merge_decisions))

    # =================================================================
    # Step 4: Preview first 20 merges
    # =================================================================
    print("\n" + "=" * 70)
    print("MERGE PREVIEW (first 20)")
    print("=" * 70)

    for i, m in enumerate(merge_decisions[:20]):
        print("\n[%d] KEEP: %s" % (i + 1, m['kept_name']))
        print("       City: %s, State: %s, Size: %s, Notices: %s" % (
            m['kept_city'], m['kept_state'], m['kept_size'] or 0, m['kept_notices']))
        print("    DELETE: %s" % m['deleted_name'])
        print("       City: %s, State: %s, Size: %s, Notices: %s" % (
            m['deleted_city'], m['deleted_state'], m['deleted_size'] or 0, m['deleted_notices']))
        print("    Score: %.3f" % m['score'])

    if len(merge_decisions) > 20:
        print("\n... and %d more merge operations" % (len(merge_decisions) - 20))

    # =================================================================
    # Step 5: Impact analysis on ALL 5 downstream tables
    # =================================================================
    print("\n" + "=" * 70)
    print("IMPACT ANALYSIS (all 6 downstream tables)")
    print("=" * 70)

    deleted_ids = [m['deleted_id'] for m in merge_decisions]

    # 1. f7_union_employer_relations
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM f7_union_employer_relations
        WHERE employer_id = ANY(%s)
    """, (deleted_ids,))
    impact_f7_relations = cur.fetchone()['cnt']
    print("  f7_union_employer_relations to update: %d" % impact_f7_relations)

    # 2. nlrb_voluntary_recognition
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM nlrb_voluntary_recognition
        WHERE matched_employer_id = ANY(%s)
    """, (deleted_ids,))
    impact_vr = cur.fetchone()['cnt']
    print("  nlrb_voluntary_recognition to update:  %d" % impact_vr)

    # 3. nlrb_participants
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM nlrb_participants
        WHERE matched_employer_id = ANY(%s)
    """, (deleted_ids,))
    impact_nlrb = cur.fetchone()['cnt']
    print("  nlrb_participants to update:            %d" % impact_nlrb)

    # 4. osha_f7_matches
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM osha_f7_matches
        WHERE f7_employer_id = ANY(%s)
    """, (deleted_ids,))
    impact_osha = cur.fetchone()['cnt']
    print("  osha_f7_matches to update:              %d" % impact_osha)

    # 4b. Check potential OSHA conflicts (same establishment already mapped to keeper)
    osha_conflict_count = 0
    for m in merge_decisions:
        cur.execute("""
            SELECT COUNT(*) AS cnt
            FROM osha_f7_matches o1
            WHERE o1.f7_employer_id = %s
              AND o1.establishment_id IN (
                  SELECT establishment_id FROM osha_f7_matches WHERE f7_employer_id = %s
              )
        """, (m['kept_id'], m['deleted_id']))
        osha_conflict_count += cur.fetchone()['cnt']
    print("  osha_f7_matches potential conflicts:    %d (will delete instead of update)" % osha_conflict_count)

    # 5. mergent_employers
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM mergent_employers
        WHERE matched_f7_employer_id = ANY(%s)
    """, (deleted_ids,))
    impact_mergent = cur.fetchone()['cnt']
    print("  mergent_employers to update:            %d" % impact_mergent)

    # 6. corporate_identifier_crosswalk
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM corporate_identifier_crosswalk
        WHERE f7_employer_id = ANY(%s)
    """, (deleted_ids,))
    impact_crosswalk = cur.fetchone()['cnt']
    print("  corporate_identifier_crosswalk:         %d" % impact_crosswalk)

    # Total employers to delete
    print("\n  f7_employers_deduped records to delete: %d" % len(merge_decisions))

    # =================================================================
    # Step 6: Execute or summary
    # =================================================================
    if DRY_RUN:
        print("\n" + "=" * 70)
        print("DRY RUN COMPLETE - No changes made")
        print("=" * 70)
        print("""
Summary:
  Duplicate pairs (score >= %s): %d
  Unique employers involved: %d
  Merge groups: %d
  Total merges to perform: %d

  Downstream impact:
    f7_union_employer_relations: %d rows
    nlrb_voluntary_recognition:  %d rows
    nlrb_participants:           %d rows
    osha_f7_matches:             %d rows (%d conflicts)
    mergent_employers:           %d rows
    corporate_identifier_crosswalk: %d rows

To apply these merges, run:
  python scripts/cleanup/merge_f7_enhanced.py --apply
""" % (
            MIN_SCORE, len(duplicate_pairs), len(all_ids),
            len(merge_groups), len(merge_decisions),
            impact_f7_relations, impact_vr, impact_nlrb,
            impact_osha, osha_conflict_count, impact_mergent,
            impact_crosswalk,
        ))
        cur.close()
        conn.close()
        return

    # -----------------------------------------------------------------
    # APPLY MODE
    # -----------------------------------------------------------------
    print("\n" + "=" * 70)
    print("APPLYING MERGES")
    print("=" * 70)

    # Create/upgrade audit log table
    print("\nCreating audit log table (if not exists)...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS f7_employer_merge_log (
            id SERIAL PRIMARY KEY,
            merge_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kept_id TEXT NOT NULL,
            deleted_id TEXT NOT NULL,
            kept_name TEXT,
            deleted_name TEXT,
            similarity_score NUMERIC(5,3),
            f7_relations_updated INTEGER DEFAULT 0,
            vr_records_updated INTEGER DEFAULT 0,
            nlrb_participants_updated INTEGER DEFAULT 0,
            osha_matches_updated INTEGER DEFAULT 0,
            osha_conflicts_deleted INTEGER DEFAULT 0,
            mergent_updated INTEGER DEFAULT 0,
            crosswalk_updated INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    # Ensure all columns exist (in case the old table exists with fewer columns)
    for col, coltype in [
        ('nlrb_participants_updated', 'INTEGER DEFAULT 0'),
        ('osha_matches_updated', 'INTEGER DEFAULT 0'),
        ('osha_conflicts_deleted', 'INTEGER DEFAULT 0'),
        ('mergent_updated', 'INTEGER DEFAULT 0'),
        ('crosswalk_updated', 'INTEGER DEFAULT 0'),
    ]:
        try:
            cur.execute(
                "ALTER TABLE f7_employer_merge_log ADD COLUMN %s %s" % (col, coltype)
            )
            conn.commit()
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()

    # Counters
    successful = 0
    errors = []
    totals = {
        'f7_relations': 0,
        'vr': 0,
        'nlrb': 0,
        'osha_updated': 0,
        'osha_conflicts': 0,
        'mergent': 0,
        'crosswalk': 0,
    }

    print("Processing %d merges (batch commit every %d)...\n" % (
        len(merge_decisions), BATCH_SIZE))

    for i, m in enumerate(merge_decisions):
        kept = m['kept_id']
        deleted = m['deleted_id']

        # Progress reporting
        if i > 0 and i % 100 == 0:
            print("  Progress: %d / %d  (errors so far: %d)" % (
                i, len(merge_decisions), len(errors)))

        sp_name = "sp_merge_%d" % i
        try:
            cur.execute("SAVEPOINT %s" % sp_name)

            # --- 1. f7_union_employer_relations ---
            cur.execute("""
                UPDATE f7_union_employer_relations
                SET employer_id = %s
                WHERE employer_id = %s
            """, (kept, deleted))
            cnt_f7_rel = cur.rowcount

            # --- 2. nlrb_voluntary_recognition ---
            cur.execute("""
                UPDATE nlrb_voluntary_recognition
                SET matched_employer_id = %s
                WHERE matched_employer_id = %s
            """, (kept, deleted))
            cnt_vr = cur.rowcount

            # --- 3. nlrb_participants ---
            cur.execute("""
                UPDATE nlrb_participants
                SET matched_employer_id = %s
                WHERE matched_employer_id = %s
            """, (kept, deleted))
            cnt_nlrb = cur.rowcount

            # --- 4. osha_f7_matches (with conflict handling) ---
            # First, find establishment_ids that would conflict:
            #   they already map to the keeper AND also map to the deleted id.
            cur.execute("""
                SELECT o_del.establishment_id
                FROM osha_f7_matches o_del
                JOIN osha_f7_matches o_keep
                  ON o_del.establishment_id = o_keep.establishment_id
                WHERE o_del.f7_employer_id = %s
                  AND o_keep.f7_employer_id = %s
            """, (deleted, kept))
            conflict_estabs = [row['establishment_id'] for row in cur.fetchall()]
            cnt_osha_conflict = len(conflict_estabs)

            if conflict_estabs:
                # Delete the duplicate rows (keeper already covers these)
                cur.execute("""
                    DELETE FROM osha_f7_matches
                    WHERE f7_employer_id = %s
                      AND establishment_id = ANY(%s)
                """, (deleted, conflict_estabs))

            # Now update the non-conflicting rows
            cur.execute("""
                UPDATE osha_f7_matches
                SET f7_employer_id = %s
                WHERE f7_employer_id = %s
            """, (kept, deleted))
            cnt_osha = cur.rowcount

            # --- 5. mergent_employers ---
            cur.execute("""
                UPDATE mergent_employers
                SET matched_f7_employer_id = %s
                WHERE matched_f7_employer_id = %s
            """, (kept, deleted))
            cnt_mergent = cur.rowcount

            # --- 6. corporate_identifier_crosswalk ---
            cnt_crosswalk = 0
            # Check if keeper already has a crosswalk row
            cur.execute("""
                SELECT id FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s LIMIT 1
            """, (kept,))
            keeper_cw = cur.fetchone()

            cur.execute("""
                SELECT id, gleif_lei, mergent_duns, sec_cik, ein,
                       is_federal_contractor, federal_obligations, federal_contract_count
                FROM corporate_identifier_crosswalk
                WHERE f7_employer_id = %s
            """, (deleted,))
            deleted_cw_rows = cur.fetchall()

            if deleted_cw_rows:
                if keeper_cw:
                    # COALESCE: merge identifiers from deleted into keeper
                    keeper_cw_id = keeper_cw['id']
                    for dcw in deleted_cw_rows:
                        cur.execute("""
                            UPDATE corporate_identifier_crosswalk
                            SET gleif_lei = COALESCE(gleif_lei, %(lei)s),
                                mergent_duns = COALESCE(mergent_duns, %(duns)s),
                                sec_cik = COALESCE(sec_cik, %(cik)s),
                                ein = COALESCE(ein, %(ein)s),
                                is_federal_contractor = COALESCE(is_federal_contractor, %(is_fc)s),
                                federal_obligations = COALESCE(federal_obligations, %(fed_oblig)s),
                                federal_contract_count = COALESCE(federal_contract_count, %(fed_cnt)s)
                            WHERE id = %(keeper_id)s
                        """, {
                            'lei': dcw['gleif_lei'],
                            'duns': dcw['mergent_duns'],
                            'cik': dcw['sec_cik'],
                            'ein': dcw['ein'],
                            'is_fc': dcw['is_federal_contractor'],
                            'fed_oblig': dcw['federal_obligations'],
                            'fed_cnt': dcw['federal_contract_count'],
                            'keeper_id': keeper_cw_id,
                        })
                        # Delete the orphaned crosswalk row
                        cur.execute(
                            "DELETE FROM corporate_identifier_crosswalk WHERE id = %s",
                            (dcw['id'],))
                        cnt_crosswalk += 1
                else:
                    # Keeper has no crosswalk row: re-point deleted's row to keeper
                    cur.execute("""
                        UPDATE corporate_identifier_crosswalk
                        SET f7_employer_id = %s
                        WHERE f7_employer_id = %s
                    """, (kept, deleted))
                    cnt_crosswalk = cur.rowcount

            # --- Audit log ---
            cur.execute("""
                INSERT INTO f7_employer_merge_log
                    (kept_id, deleted_id, kept_name, deleted_name,
                     similarity_score, f7_relations_updated, vr_records_updated,
                     nlrb_participants_updated, osha_matches_updated,
                     osha_conflicts_deleted, mergent_updated, crosswalk_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                kept, deleted, m['kept_name'], m['deleted_name'],
                m['score'],
                cnt_f7_rel, cnt_vr, cnt_nlrb,
                cnt_osha, cnt_osha_conflict, cnt_mergent, cnt_crosswalk,
            ))

            # --- Delete the duplicate from f7_employers_deduped ---
            cur.execute("""
                DELETE FROM f7_employers_deduped
                WHERE employer_id = %s
            """, (deleted,))

            cur.execute("RELEASE SAVEPOINT %s" % sp_name)
            successful += 1

            totals['f7_relations'] += cnt_f7_rel
            totals['vr'] += cnt_vr
            totals['nlrb'] += cnt_nlrb
            totals['osha_updated'] += cnt_osha
            totals['osha_conflicts'] += cnt_osha_conflict
            totals['mergent'] += cnt_mergent
            totals['crosswalk'] += cnt_crosswalk

        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT %s" % sp_name)
            cur.execute("RELEASE SAVEPOINT %s" % sp_name)
            errors.append((deleted, str(e)))

        # Batch commit
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()

    # Final commit for remaining
    conn.commit()

    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------
    print("\n" + "=" * 70)
    print("MERGE COMPLETE")
    print("=" * 70)
    print("  Successful merges: %d" % successful)
    print("  Errors:            %d" % len(errors))
    print()
    print("  Downstream updates:")
    print("    f7_union_employer_relations: %d" % totals['f7_relations'])
    print("    nlrb_voluntary_recognition:  %d" % totals['vr'])
    print("    nlrb_participants:           %d" % totals['nlrb'])
    print("    osha_f7_matches updated:     %d" % totals['osha_updated'])
    print("    osha_f7_matches conflicts:   %d (deleted)" % totals['osha_conflicts'])
    print("    mergent_employers:           %d" % totals['mergent'])
    print("    crosswalk rows updated:      %d" % totals['crosswalk'])

    if errors:
        print("\n  First 10 errors:")
        for emp_id, err in errors[:10]:
            print("    %s: %s" % (emp_id, err))

    # Verification counts
    cur.execute("SELECT COUNT(*) AS cnt FROM f7_employer_merge_log")
    log_count = cur.fetchone()['cnt']
    print("\n  Total merge log entries: %d" % log_count)

    cur.execute("SELECT COUNT(*) AS cnt FROM f7_employers_deduped")
    remaining = cur.fetchone()['cnt']
    print("  Remaining employers in f7_employers_deduped: %d" % remaining)

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()
