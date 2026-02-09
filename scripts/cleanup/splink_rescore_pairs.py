"""
Combine pg_trgm similarity pairs with Splink probabilistic evidence for F7 dedup.

Loads:
  1. Existing pg_trgm pairs from output/f7_internal_duplicates.csv
  2. Splink results from splink_match_results WHERE scenario = 'f7_self_dedup'

Classification rules:
  AUTO_MERGE:        pg_trgm >= 0.9 AND Splink prob >= 0.85 AND name_level >= 3
  SPLINK_CONFIRMED:  pg_trgm 0.8-0.9 AND Splink prob >= 0.85 AND name_level >= 3
  LIKELY_DUPLICATE:  Splink prob >= 0.70 AND city_level >= 2
  MULTI_LOCATION:    pg_trgm >= 0.8 AND Splink prob < 0.50
  NEW_MATCH:         Splink prob >= 0.85 AND NOT in pg_trgm results

Exports: data/f7_combined_dedup_evidence.csv

Usage:
    py scripts/cleanup/splink_rescore_pairs.py
    py scripts/cleanup/splink_rescore_pairs.py --verbose
"""
import csv
import os
import sys
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor

VERBOSE = '--verbose' in sys.argv
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PGTRGM_CSV = os.path.join(BASE_DIR, 'output', 'f7_internal_duplicates.csv')
OUTPUT_CSV = os.path.join(BASE_DIR, 'data', 'f7_combined_dedup_evidence.csv')


def main():
    conn = psycopg2.connect(
        host='localhost',
        dbname='olms_multiyear',
        user='postgres',
        password='os.environ.get('DB_PASSWORD', '')'
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("=" * 70)
    print("SPLINK RESCORE: Combine pg_trgm + Splink Evidence")
    print("=" * 70)

    # =========================================================================
    # Step 1: Load pg_trgm pairs
    # =========================================================================
    print("\nStep 1: Loading pg_trgm pairs from %s..." % PGTRGM_CSV)

    pgtrgm_pairs = {}  # (id1, id2) -> row dict, normalized so id1 < id2
    with open(PGTRGM_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            id1, id2 = row['ID1'], row['ID2']
            # Normalize pair order so we can match against Splink
            key = tuple(sorted([id1, id2]))
            pgtrgm_pairs[key] = {
                'id1': key[0],
                'id2': key[1],
                'name1': row['Name1'] if id1 == key[0] else row['Name2'],
                'name2': row['Name2'] if id1 == key[0] else row['Name1'],
                'city1': row['City1'] if id1 == key[0] else row['City2'],
                'city2': row['City2'] if id1 == key[0] else row['City1'],
                'state1': row['State1'] if id1 == key[0] else row['State2'],
                'state2': row['State2'] if id1 == key[0] else row['State1'],
                'size1': int(row['Size1']) if row['Size1'] else 0,
                'size2': int(row['Size2']) if row['Size2'] else 0,
                'pgtrgm_name_sim': float(row['Name_Sim']),
                'pgtrgm_token_sim': float(row['Token_Sim']),
                'pgtrgm_combined': float(row['Combined_Score']),
            }

    print("  Loaded %d pg_trgm pairs" % len(pgtrgm_pairs))

    # Distribution
    high = sum(1 for p in pgtrgm_pairs.values() if p['pgtrgm_combined'] >= 0.9)
    medium = sum(1 for p in pgtrgm_pairs.values() if 0.8 <= p['pgtrgm_combined'] < 0.9)
    low = sum(1 for p in pgtrgm_pairs.values() if p['pgtrgm_combined'] < 0.8)
    print("  pg_trgm score distribution: >= 0.9: %d | 0.8-0.9: %d | < 0.8: %d" % (high, medium, low))

    # =========================================================================
    # Step 2: Load Splink results
    # =========================================================================
    print("\nStep 2: Loading Splink results (scenario = 'f7_self_dedup')...")

    cur.execute("""
        SELECT source_id, target_id, source_name, target_name,
               match_probability, match_weight,
               name_comparison_level, state_comparison_level,
               city_comparison_level, zip_comparison_level,
               naics_comparison_level, address_comparison_level
        FROM splink_match_results
        WHERE scenario = 'f7_self_dedup'
        ORDER BY match_probability DESC
    """)
    splink_rows = cur.fetchall()
    print("  Loaded %d Splink pairs" % len(splink_rows))

    if not splink_rows:
        print("\n  WARNING: No Splink results found. Run the self-dedup first:")
        print("    py scripts/matching/splink_pipeline.py f7_self_dedup")
        cur.close()
        conn.close()
        return

    # Build lookup: (id1, id2) normalized -> splink data
    splink_pairs = {}
    for row in splink_rows:
        key = tuple(sorted([row['source_id'], row['target_id']]))
        splink_pairs[key] = {
            'splink_prob': row['match_probability'],
            'splink_weight': row['match_weight'],
            'name_level': row['name_comparison_level'],
            'state_level': row['state_comparison_level'],
            'city_level': row['city_comparison_level'],
            'zip_level': row['zip_comparison_level'],
            'naics_level': row['naics_comparison_level'],
            'address_level': row['address_comparison_level'],
            'source_name': row['source_name'],
            'target_name': row['target_name'],
        }

    splink_high = sum(1 for s in splink_pairs.values() if s['splink_prob'] >= 0.85)
    splink_mid = sum(1 for s in splink_pairs.values() if 0.70 <= s['splink_prob'] < 0.85)
    print("  Splink prob distribution: >= 0.85: %d | 0.70-0.85: %d" % (splink_high, splink_mid))

    # =========================================================================
    # Step 3: Join and classify
    # =========================================================================
    print("\nStep 3: Classifying all pairs...")

    all_keys = set(pgtrgm_pairs.keys()) | set(splink_pairs.keys())
    print("  Unique pairs (union): %d" % len(all_keys))

    overlap = set(pgtrgm_pairs.keys()) & set(splink_pairs.keys())
    pgtrgm_only = set(pgtrgm_pairs.keys()) - set(splink_pairs.keys())
    splink_only = set(splink_pairs.keys()) - set(pgtrgm_pairs.keys())
    print("  Overlap (both sources): %d" % len(overlap))
    print("  pg_trgm only: %d" % len(pgtrgm_only))
    print("  Splink only: %d" % len(splink_only))

    results = []
    counts = defaultdict(int)

    for key in all_keys:
        pg = pgtrgm_pairs.get(key)
        sp = splink_pairs.get(key)

        pgtrgm_score = pg['pgtrgm_combined'] if pg else None
        splink_prob = sp['splink_prob'] if sp else None
        name_level = sp['name_level'] if sp else None
        city_level = sp['city_level'] if sp else None

        # Classification logic
        classification = 'UNCLASSIFIED'

        if pg and sp:
            # Both sources have this pair
            if pgtrgm_score >= 0.9 and splink_prob >= 0.85 and name_level is not None and name_level >= 3:
                classification = 'AUTO_MERGE'
            elif 0.8 <= pgtrgm_score < 0.9 and splink_prob >= 0.85 and name_level is not None and name_level >= 3:
                classification = 'SPLINK_CONFIRMED'
            elif pgtrgm_score >= 0.8 and splink_prob < 0.50:
                classification = 'MULTI_LOCATION'
            elif splink_prob >= 0.70 and city_level is not None and city_level >= 2:
                classification = 'LIKELY_DUPLICATE'
            elif splink_prob >= 0.70:
                classification = 'LIKELY_DUPLICATE'
            else:
                classification = 'LOW_CONFIDENCE'
        elif sp and not pg:
            # Splink found it, pg_trgm didn't
            # CRITICAL: require name_level >= 4 (JW >= 0.88) for NEW_MATCH to
            # prevent city-name-prefix false positives (e.g. "Cleveland Cliffs"
            # matching "Cleveland Ballet" at name_level 3). Level 3 (JW >= 0.80)
            # is only safe with pg_trgm cross-confirmation (SPLINK_CONFIRMED).
            if splink_prob >= 0.85 and name_level is not None and name_level >= 4:
                classification = 'NEW_MATCH'
            elif splink_prob >= 0.70 and name_level is not None and name_level >= 4:
                classification = 'LIKELY_DUPLICATE'
            elif splink_prob >= 0.85 and (name_level is None or name_level < 4):
                classification = 'GEO_ONLY'
            else:
                classification = 'LOW_CONFIDENCE'
        elif pg and not sp:
            # pg_trgm found it, Splink didn't (below threshold or blocked)
            if pgtrgm_score >= 0.9:
                classification = 'PGTRGM_ONLY_HIGH'
            else:
                classification = 'PGTRGM_ONLY_LOW'

        counts[classification] += 1

        # Build output row
        row = {
            'id1': key[0],
            'id2': key[1],
            'name1': pg['name1'] if pg else (sp['source_name'] if sp and key[0] == key[0] else ''),
            'name2': pg['name2'] if pg else (sp['target_name'] if sp else ''),
            'city1': pg.get('city1', '') if pg else '',
            'city2': pg.get('city2', '') if pg else '',
            'state1': pg.get('state1', '') if pg else '',
            'state2': pg.get('state2', '') if pg else '',
            'size1': pg.get('size1', '') if pg else '',
            'size2': pg.get('size2', '') if pg else '',
            'pgtrgm_combined': '%.3f' % pgtrgm_score if pgtrgm_score is not None else '',
            'splink_prob': '%.4f' % splink_prob if splink_prob is not None else '',
            'splink_weight': '%.2f' % sp['splink_weight'] if sp and sp['splink_weight'] is not None else '',
            'name_level': name_level if name_level is not None else '',
            'state_level': sp['state_level'] if sp and sp['state_level'] is not None else '',
            'city_level': city_level if city_level is not None else '',
            'zip_level': sp['zip_level'] if sp and sp['zip_level'] is not None else '',
            'naics_level': sp['naics_level'] if sp and sp['naics_level'] is not None else '',
            'address_level': sp['address_level'] if sp and sp['address_level'] is not None else '',
            'classification': classification,
        }
        results.append(row)

    # Sort by classification priority, then descending probability
    class_order = {
        'AUTO_MERGE': 0, 'SPLINK_CONFIRMED': 1, 'NEW_MATCH': 2,
        'LIKELY_DUPLICATE': 3, 'MULTI_LOCATION': 4,
        'PGTRGM_ONLY_HIGH': 5, 'PGTRGM_ONLY_LOW': 6,
        'GEO_ONLY': 7, 'LOW_CONFIDENCE': 8, 'UNCLASSIFIED': 9,
    }
    results.sort(key=lambda r: (
        class_order.get(r['classification'], 99),
        -float(r['splink_prob']) if r['splink_prob'] else 0,
        -float(r['pgtrgm_combined']) if r['pgtrgm_combined'] else 0,
    ))

    # =========================================================================
    # Step 4: Print summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("CLASSIFICATION SUMMARY")
    print("=" * 70)

    for cls in sorted(counts.keys(), key=lambda c: class_order.get(c, 99)):
        print("  %-25s %6d pairs" % (cls, counts[cls]))
    print("  %-25s %6d pairs" % ("TOTAL", len(results)))

    # Actionable counts
    mergeable = counts.get('AUTO_MERGE', 0) + counts.get('SPLINK_CONFIRMED', 0)
    new_finds = counts.get('NEW_MATCH', 0)
    multi_loc = counts.get('MULTI_LOCATION', 0)
    print("\n  Actionable:")
    print("    Ready to merge (AUTO_MERGE + SPLINK_CONFIRMED): %d" % mergeable)
    print("    New matches (Splink-only discoveries):          %d" % new_finds)
    print("    Multi-location (link, don't merge):             %d" % multi_loc)

    # =========================================================================
    # Step 5: Export CSV
    # =========================================================================
    print("\nStep 5: Exporting to %s..." % OUTPUT_CSV)

    # Only export actionable classifications (skip GEO_ONLY noise)
    skip_classes = {'GEO_ONLY', 'LOW_CONFIDENCE', 'UNCLASSIFIED'}
    export_rows = [r for r in results if r['classification'] not in skip_classes]

    fieldnames = [
        'id1', 'id2', 'name1', 'name2', 'city1', 'city2', 'state1', 'state2',
        'size1', 'size2', 'pgtrgm_combined', 'splink_prob', 'splink_weight',
        'name_level', 'state_level', 'city_level', 'zip_level',
        'naics_level', 'address_level', 'classification',
    ]
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(export_rows)

    print("  Wrote %d actionable rows (skipped %d GEO_ONLY/LOW_CONFIDENCE)" % (
        len(export_rows), len(results) - len(export_rows)))

    # Show samples from each class
    if VERBOSE:
        for cls in ['AUTO_MERGE', 'SPLINK_CONFIRMED', 'NEW_MATCH', 'MULTI_LOCATION']:
            samples = [r for r in results if r['classification'] == cls][:3]
            if samples:
                print("\n  Sample %s pairs:" % cls)
                for s in samples:
                    print("    %s <-> %s | pg=%-5s sp=%-6s n=%s c=%s" % (
                        (s['name1'] or '')[:30], (s['name2'] or '')[:30],
                        s['pgtrgm_combined'] or '-', s['splink_prob'] or '-',
                        s['name_level'] or '-', s['city_level'] or '-'))

    print("\n" + "=" * 70)
    print("RESCORE COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Review data/f7_combined_dedup_evidence.csv")
    print("  2. Run AUTO_MERGE batch:")
    print("     py scripts/cleanup/merge_f7_enhanced.py --apply --source combined")
    print("  3. Run SPLINK_CONFIRMED batch after checkpoint")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
