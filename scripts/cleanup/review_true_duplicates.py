"""
Review and merge 234 true duplicate groups from f7_duplicate_groups.csv.

Uses the same merge infrastructure as merge_f7_enhanced.py but operates on
pre-categorized TRUE_DUPLICATE groups instead of pairwise similarity scores.

Input: data/f7_duplicate_groups.csv (category=TRUE_DUPLICATE)
Each row has: aggressive_name, state, count, category, ids (semicolon-separated),
              original_names (semicolon-separated), cities (semicolon-separated)

Usage:
    py scripts/cleanup/review_true_duplicates.py                  # DRY RUN
    py scripts/cleanup/review_true_duplicates.py --apply          # Apply merges
    py scripts/cleanup/review_true_duplicates.py --export-only    # Just export review CSV
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import sys
import os
from datetime import datetime

DRY_RUN = '--apply' not in sys.argv
EXPORT_ONLY = '--export-only' in sys.argv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_INPUT = os.path.join(BASE_DIR, 'data', 'f7_duplicate_groups.csv')
CSV_OUTPUT = os.path.join(BASE_DIR, 'data', 'true_duplicate_review.csv')


def main():
    conn = psycopg2.connect(
        host='localhost',
        database='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("TRUE DUPLICATE GROUP REVIEW")
    print("=" * 70)
    print("Mode: %s" % ('DRY RUN' if DRY_RUN else '*** APPLYING MERGES ***'))
    print("Input: %s" % CSV_INPUT)
    print()

    # =========================================================================
    # Step 1: Load TRUE_DUPLICATE groups
    # =========================================================================
    print("Step 1: Loading true duplicate groups...")

    groups = []
    with open(CSV_INPUT, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['category'] == 'TRUE_DUPLICATE':
                ids = row['ids'].split(';')
                names = row['original_names'].split(';')
                cities = row['cities'].split(';') if row.get('cities') else [''] * len(ids)
                groups.append({
                    'aggressive_name': row['aggressive_name'],
                    'state': row['state'],
                    'count': int(row['count']),
                    'ids': ids,
                    'names': names,
                    'cities': cities,
                })

    print("  TRUE_DUPLICATE groups loaded: %d" % len(groups))
    total_employers = sum(g['count'] for g in groups)
    total_merges = sum(g['count'] - 1 for g in groups)
    print("  Total employers involved: %d" % total_employers)
    print("  Total merges to perform: %d" % total_merges)

    # =========================================================================
    # Step 2: Query full details for each group
    # =========================================================================
    print("\nStep 2: Querying employer details and downstream references...")

    all_ids = []
    for g in groups:
        all_ids.extend(g['ids'])

    # Get employer details
    cur.execute("""
        SELECT employer_id, employer_name, city, state, latest_unit_size,
               latest_union_fnum, latest_union_name, naics, street, zip,
               latitude, longitude
        FROM f7_employers_deduped
        WHERE employer_id = ANY(%s)
    """, (all_ids,))
    details = {row['employer_id']: dict(row) for row in cur.fetchall()}

    # Get downstream reference counts for each employer
    for emp_id in all_ids:
        if emp_id not in details:
            continue

        cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations WHERE employer_id = %s", (emp_id,))
        details[emp_id]['f7_relations'] = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) FROM nlrb_voluntary_recognition WHERE matched_employer_id = %s", (emp_id,))
        details[emp_id]['vr_refs'] = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE matched_employer_id = %s", (emp_id,))
        details[emp_id]['nlrb_refs'] = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) FROM osha_f7_matches WHERE f7_employer_id = %s", (emp_id,))
        details[emp_id]['osha_refs'] = cur.fetchone()['count']

        cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE matched_f7_employer_id = %s", (emp_id,))
        details[emp_id]['mergent_refs'] = cur.fetchone()['count']

    missing_ids = [eid for eid in all_ids if eid not in details]
    if missing_ids:
        print("  WARNING: %d employer_ids not found in f7_employers_deduped" % len(missing_ids))

    print("  Details loaded for %d employers" % len(details))

    # =========================================================================
    # Step 3: Select keeper for each group
    # =========================================================================
    print("\nStep 3: Selecting keeper for each group...")

    merge_decisions = []
    review_rows = []

    for g in groups:
        group_employers = [details[eid] for eid in g['ids'] if eid in details]
        if len(group_employers) < 2:
            continue

        # Sort: largest unit_size, most references, alphabetical name
        group_employers.sort(
            key=lambda x: (
                -(x['latest_unit_size'] or 0),
                -(x['f7_relations'] + x['vr_refs'] + x['nlrb_refs'] + x['osha_refs'] + x['mergent_refs']),
                x['employer_name'] or ''
            )
        )

        keeper = group_employers[0]

        for emp in group_employers[1:]:
            merge_decisions.append({
                'kept_id': keeper['employer_id'],
                'kept_name': keeper['employer_name'],
                'kept_city': keeper['city'],
                'kept_state': keeper['state'],
                'kept_size': keeper['latest_unit_size'],
                'deleted_id': emp['employer_id'],
                'deleted_name': emp['employer_name'],
                'deleted_city': emp['city'],
                'deleted_state': emp['state'],
                'deleted_size': emp['latest_unit_size'],
                'group_name': g['aggressive_name'],
            })

        # Build review row
        review_rows.append({
            'group_name': g['aggressive_name'],
            'state': g['state'],
            'count': g['count'],
            'keeper_id': keeper['employer_id'],
            'keeper_name': keeper['employer_name'],
            'keeper_city': keeper['city'],
            'keeper_size': keeper['latest_unit_size'] or 0,
            'keeper_refs': keeper['f7_relations'] + keeper['vr_refs'] + keeper['nlrb_refs'] + keeper['osha_refs'],
            'merged_names': '; '.join(e['employer_name'] or '' for e in group_employers[1:]),
            'merged_sizes': '; '.join(str(e['latest_unit_size'] or 0) for e in group_employers[1:]),
        })

    print("  Merge decisions: %d" % len(merge_decisions))

    # =========================================================================
    # Step 4: Export review CSV
    # =========================================================================
    print("\nStep 4: Exporting review CSV to %s..." % CSV_OUTPUT)

    with open(CSV_OUTPUT, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'group_name', 'state', 'count', 'keeper_id', 'keeper_name',
            'keeper_city', 'keeper_size', 'keeper_refs', 'merged_names', 'merged_sizes'
        ])
        writer.writeheader()
        writer.writerows(review_rows)
    print("  Wrote %d review rows" % len(review_rows))

    if EXPORT_ONLY:
        print("\n--export-only mode: stopping here.")
        cur.close()
        conn.close()
        return

    # =========================================================================
    # Step 5: Preview merges
    # =========================================================================
    print("\n" + "=" * 70)
    print("MERGE PREVIEW (first 20)")
    print("=" * 70)

    for i, m in enumerate(merge_decisions[:20]):
        print("\n[%d] Group: %s" % (i + 1, m['group_name']))
        print("    KEEP:   %s (%s, %s) size=%s" % (
            m['kept_name'], m['kept_city'], m['kept_state'], m['kept_size'] or 0))
        print("    DELETE: %s (%s, %s) size=%s" % (
            m['deleted_name'], m['deleted_city'], m['deleted_state'], m['deleted_size'] or 0))

    if len(merge_decisions) > 20:
        print("\n... and %d more merge operations" % (len(merge_decisions) - 20))

    # =========================================================================
    # Step 6: Impact analysis
    # =========================================================================
    print("\n" + "=" * 70)
    print("IMPACT ANALYSIS")
    print("=" * 70)

    deleted_ids = [m['deleted_id'] for m in merge_decisions]

    cur.execute("SELECT COUNT(*) FROM f7_union_employer_relations WHERE employer_id = ANY(%s)",
                (deleted_ids,))
    impact_relations = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) FROM nlrb_voluntary_recognition WHERE matched_employer_id = ANY(%s)",
                (deleted_ids,))
    impact_vr = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) FROM nlrb_participants WHERE matched_employer_id = ANY(%s)",
                (deleted_ids,))
    impact_nlrb = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) FROM osha_f7_matches WHERE f7_employer_id = ANY(%s)",
                (deleted_ids,))
    impact_osha = cur.fetchone()['count']

    cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE matched_f7_employer_id = ANY(%s)",
                (deleted_ids,))
    impact_mergent = cur.fetchone()['count']

    print("  f7_union_employer_relations: %d" % impact_relations)
    print("  nlrb_voluntary_recognition:  %d" % impact_vr)
    print("  nlrb_participants:           %d" % impact_nlrb)
    print("  osha_f7_matches:             %d" % impact_osha)
    print("  mergent_employers:           %d" % impact_mergent)

    # =========================================================================
    # Step 7: Execute merges (if --apply)
    # =========================================================================
    if DRY_RUN:
        print("\n" + "=" * 70)
        print("DRY RUN COMPLETE - No changes made")
        print("=" * 70)
        print("\nTo apply these merges, run:")
        print("  py scripts/cleanup/review_true_duplicates.py --apply")
    else:
        print("\n" + "=" * 70)
        print("APPLYING MERGES")
        print("=" * 70)

        # Ensure merge log table exists (same schema as merge_f7_enhanced.py)
        cur_plain = conn.cursor()
        cur_plain.execute("""
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
                mergent_updated INTEGER DEFAULT 0
            )
        """)
        conn.commit()

        successful = 0
        errors = []
        totals = {
            'relations': 0, 'vr': 0, 'nlrb': 0,
            'osha_updated': 0, 'osha_conflicts': 0, 'mergent': 0
        }

        for i, m in enumerate(merge_decisions):
            if i % 50 == 0 and i > 0:
                conn.commit()
                print("  Processed %d/%d..." % (i, len(merge_decisions)))

            try:
                cur_plain.execute("SAVEPOINT merge_op")

                # 1. f7_union_employer_relations
                cur_plain.execute(
                    "UPDATE f7_union_employer_relations SET employer_id = %s WHERE employer_id = %s",
                    (m['kept_id'], m['deleted_id']))
                rel_updated = cur_plain.rowcount

                # 2. nlrb_voluntary_recognition
                cur_plain.execute(
                    "UPDATE nlrb_voluntary_recognition SET matched_employer_id = %s WHERE matched_employer_id = %s",
                    (m['kept_id'], m['deleted_id']))
                vr_updated = cur_plain.rowcount

                # 3. nlrb_participants
                cur_plain.execute(
                    "UPDATE nlrb_participants SET matched_employer_id = %s WHERE matched_employer_id = %s",
                    (m['kept_id'], m['deleted_id']))
                nlrb_updated = cur_plain.rowcount

                # 4. osha_f7_matches - handle conflicts
                # First delete rows that would conflict (same establishment already linked to keeper)
                cur_plain.execute("""
                    DELETE FROM osha_f7_matches
                    WHERE f7_employer_id = %s
                      AND establishment_id IN (
                          SELECT establishment_id FROM osha_f7_matches WHERE f7_employer_id = %s
                      )
                """, (m['deleted_id'], m['kept_id']))
                osha_conflicts = cur_plain.rowcount

                # Then update remaining
                cur_plain.execute(
                    "UPDATE osha_f7_matches SET f7_employer_id = %s WHERE f7_employer_id = %s",
                    (m['kept_id'], m['deleted_id']))
                osha_updated = cur_plain.rowcount

                # 5. mergent_employers
                cur_plain.execute(
                    "UPDATE mergent_employers SET matched_f7_employer_id = %s WHERE matched_f7_employer_id = %s",
                    (m['kept_id'], m['deleted_id']))
                mergent_updated = cur_plain.rowcount

                # Log the merge (score=1.0 since these are confirmed true duplicates)
                cur_plain.execute("""
                    INSERT INTO f7_employer_merge_log
                    (kept_id, deleted_id, kept_name, deleted_name, similarity_score,
                     f7_relations_updated, vr_records_updated, nlrb_participants_updated,
                     osha_matches_updated, osha_conflicts_deleted, mergent_updated)
                    VALUES (%s, %s, %s, %s, 1.0, %s, %s, %s, %s, %s, %s)
                """, (m['kept_id'], m['deleted_id'], m['kept_name'], m['deleted_name'],
                      rel_updated, vr_updated, nlrb_updated, osha_updated,
                      osha_conflicts, mergent_updated))

                # Delete the duplicate employer
                cur_plain.execute(
                    "DELETE FROM f7_employers_deduped WHERE employer_id = %s",
                    (m['deleted_id'],))

                cur_plain.execute("RELEASE SAVEPOINT merge_op")
                successful += 1

                totals['relations'] += rel_updated
                totals['vr'] += vr_updated
                totals['nlrb'] += nlrb_updated
                totals['osha_updated'] += osha_updated
                totals['osha_conflicts'] += osha_conflicts
                totals['mergent'] += mergent_updated

            except Exception as e:
                cur_plain.execute("ROLLBACK TO SAVEPOINT merge_op")
                errors.append((m['deleted_id'], str(e)))

        conn.commit()

        print("\n  Successful merges: %d" % successful)
        if errors:
            print("  Errors: %d" % len(errors))
            for eid, err in errors[:5]:
                print("    %s: %s" % (eid, err))

        print("\n  Downstream updates:")
        print("    f7_relations:       %d" % totals['relations'])
        print("    vr_records:         %d" % totals['vr'])
        print("    nlrb_participants:  %d" % totals['nlrb'])
        print("    osha_updated:       %d" % totals['osha_updated'])
        print("    osha_conflicts:     %d (deleted)" % totals['osha_conflicts'])
        print("    mergent:            %d" % totals['mergent'])

        # Verify
        cur_plain.execute("SELECT COUNT(*) FROM f7_employers_deduped")
        remaining = cur_plain.fetchone()[0]
        print("\n  Remaining employers: %d" % remaining)
        cur_plain.close()

        print("\n" + "=" * 70)
        print("TRUE DUPLICATE MERGE COMPLETE")
        print("=" * 70)

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
