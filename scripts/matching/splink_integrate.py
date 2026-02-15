"""
Integrate Splink probabilistic matches into the corporate crosswalk.

Takes the best 1:1 match per source record (deduplicated by both source
and target), filters by probability and name comparison level, then
inserts into corporate_identifier_crosswalk.
"""
import psycopg2
import time
import os

from db_config import get_connection
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

# Quality tiers based on analysis:
# Auto-accept: prob >= 0.85 AND name_level >= 3 (JW >= 0.88)
# Review: prob >= 0.85 AND name_level == 2 (JW >= 0.80)
# Reject: everything else

MIN_PROBABILITY = 0.85
MIN_NAME_LEVEL_ACCEPT = 3  # JW >= 0.88
MIN_NAME_LEVEL_REVIEW = 2  # JW >= 0.80


def update_review_statuses(conn):
    """Reclassify matches based on quality analysis."""
    cur = conn.cursor()
    print("=== Updating review statuses ===")

    # First, set everything to 'rejected'
    cur.execute("""
        UPDATE splink_match_results
        SET review_status = 'rejected'
        WHERE scenario = 'mergent_to_f7'
    """)
    print(f"  Reset {cur.rowcount:,} to rejected")

    # Create a deduped view of best 1:1 matches
    # Auto-accept: high probability + good name match
    cur.execute("""
        WITH best_per_source AS (
            SELECT id,
                ROW_NUMBER() OVER (
                    PARTITION BY source_id
                    ORDER BY match_probability DESC, name_comparison_level DESC
                ) as rn_src
            FROM splink_match_results
            WHERE scenario = 'mergent_to_f7'
              AND match_probability >= %(min_prob)s
              AND name_comparison_level >= %(min_name)s
        ),
        source_deduped AS (
            SELECT id FROM best_per_source WHERE rn_src = 1
        ),
        -- Now also dedupe by target (each F7 matched to at most 1 Mergent)
        target_ranked AS (
            SELECT s.id,
                ROW_NUMBER() OVER (
                    PARTITION BY r.target_id
                    ORDER BY r.match_probability DESC, r.name_comparison_level DESC
                ) as rn_tgt
            FROM source_deduped s
            JOIN splink_match_results r ON r.id = s.id
        )
        UPDATE splink_match_results
        SET review_status = 'auto_accept'
        WHERE id IN (SELECT id FROM target_ranked WHERE rn_tgt = 1)
    """, {'min_prob': MIN_PROBABILITY, 'min_name': MIN_NAME_LEVEL_ACCEPT})
    auto_count = cur.rowcount
    print(f"  Auto-accept (prob>={MIN_PROBABILITY}, name_level>={MIN_NAME_LEVEL_ACCEPT}): {auto_count:,}")

    # Review: lower name level but still good probability
    cur.execute("""
        WITH best_per_source AS (
            SELECT id,
                ROW_NUMBER() OVER (
                    PARTITION BY source_id
                    ORDER BY match_probability DESC, name_comparison_level DESC
                ) as rn_src
            FROM splink_match_results
            WHERE scenario = 'mergent_to_f7'
              AND match_probability >= %(min_prob)s
              AND name_comparison_level >= %(min_name_review)s
              AND name_comparison_level < %(min_name_accept)s
              AND review_status = 'rejected'
        ),
        source_deduped AS (
            SELECT id FROM best_per_source WHERE rn_src = 1
        ),
        target_ranked AS (
            SELECT s.id,
                ROW_NUMBER() OVER (
                    PARTITION BY r.target_id
                    ORDER BY r.match_probability DESC, r.name_comparison_level DESC
                ) as rn_tgt
            FROM source_deduped s
            JOIN splink_match_results r ON r.id = s.id
        )
        UPDATE splink_match_results
        SET review_status = 'needs_review'
        WHERE id IN (SELECT id FROM target_ranked WHERE rn_tgt = 1)
    """, {
        'min_prob': MIN_PROBABILITY,
        'min_name_review': MIN_NAME_LEVEL_REVIEW,
        'min_name_accept': MIN_NAME_LEVEL_ACCEPT,
    })
    review_count = cur.rowcount
    print(f"  Needs review (prob>={MIN_PROBABILITY}, name_level={MIN_NAME_LEVEL_REVIEW}): {review_count:,}")

    conn.commit()
    return auto_count, review_count


def integrate_into_crosswalk(conn):
    """Insert auto-accepted Splink matches into corporate_identifier_crosswalk."""
    cur = conn.cursor()
    print("\n=== Integrating into crosswalk ===")

    # For mergent_to_f7: source_id = duns, target_id = employer_id
    # Check which auto-accepted matches are NOT already in crosswalk
    cur.execute("""
        SELECT COUNT(*)
        FROM splink_match_results r
        WHERE r.scenario = 'mergent_to_f7'
          AND r.review_status = 'auto_accept'
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c
              WHERE c.mergent_duns = r.source_id AND c.f7_employer_id = r.target_id
          )
    """)
    new_count = cur.fetchone()[0]
    print(f"  New matches to integrate: {new_count:,}")

    if new_count == 0:
        print("  Nothing to integrate.")
        return 0

    # Insert new crosswalk rows for Splink matches
    start = time.time()
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (mergent_duns, f7_employer_id, canonical_name, state,
             match_tier, match_confidence)
        SELECT
            r.source_id,
            r.target_id,
            COALESCE(r.source_name, r.target_name),
            -- Get state from mergent_employers
            m.state,
            'SPLINK_PROB',
            CASE
                WHEN r.match_probability >= 0.99 THEN 'HIGH'
                WHEN r.match_probability >= 0.95 THEN 'MEDIUM_HIGH'
                ELSE 'MEDIUM'
            END
        FROM splink_match_results r
        LEFT JOIN mergent_employers m ON m.duns = r.source_id
        WHERE r.scenario = 'mergent_to_f7'
          AND r.review_status = 'auto_accept'
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c
              WHERE c.mergent_duns = r.source_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c
              WHERE c.f7_employer_id = r.target_id
          )
    """)
    inserted = cur.rowcount
    conn.commit()
    print(f"  Inserted {inserted:,} new crosswalk rows in {time.time()-start:.1f}s")

    # Also backfill: update existing crosswalk rows that have Mergent but no F7
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET f7_employer_id = r.target_id
        FROM splink_match_results r
        WHERE r.scenario = 'mergent_to_f7'
          AND r.review_status = 'auto_accept'
          AND c.mergent_duns = r.source_id
          AND c.f7_employer_id IS NULL
    """)
    backfilled_f7 = cur.rowcount
    conn.commit()
    if backfilled_f7 > 0:
        print(f"  Backfilled F7 on {backfilled_f7:,} existing rows")

    # And update rows that have F7 but no Mergent
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET mergent_duns = r.source_id
        FROM splink_match_results r
        WHERE r.scenario = 'mergent_to_f7'
          AND r.review_status = 'auto_accept'
          AND c.f7_employer_id = r.target_id
          AND c.mergent_duns IS NULL
    """)
    backfilled_m = cur.rowcount
    conn.commit()
    if backfilled_m > 0:
        print(f"  Backfilled Mergent on {backfilled_m:,} existing rows")

    # Assign family IDs for new rows
    cur.execute("""
        UPDATE corporate_identifier_crosswalk
        SET corporate_family_id = id
        WHERE corporate_family_id IS NULL
    """)
    conn.commit()

    return inserted + backfilled_f7 + backfilled_m


def print_crosswalk_summary(conn):
    """Print updated crosswalk stats."""
    cur = conn.cursor()
    print("\n=== UPDATED CROSSWALK SUMMARY ===")

    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk')
    print(f"  Total rows: {cur.fetchone()[0]:,}")

    cur.execute('SELECT match_tier, COUNT(*) FROM corporate_identifier_crosswalk GROUP BY 1 ORDER BY 2 DESC')
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE mergent_duns IS NOT NULL) as mergent,
            COUNT(*) FILTER (WHERE f7_employer_id IS NOT NULL) as f7,
            COUNT(*) FILTER (WHERE sec_id IS NOT NULL) as sec,
            COUNT(*) FILTER (WHERE gleif_id IS NOT NULL) as gleif,
            COUNT(*) FILTER (WHERE
                (CASE WHEN sec_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN gleif_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN mergent_duns IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN f7_employer_id IS NOT NULL THEN 1 ELSE 0 END) >= 3
            ) as three_plus
        FROM corporate_identifier_crosswalk
    """)
    r = cur.fetchone()
    print(f"\n  Mergent: {r[0]:,} | F7: {r[1]:,} | SEC: {r[2]:,} | GLEIF: {r[3]:,} | 3+: {r[4]:,}")


def main():
    conn = get_connection()
    conn.autocommit = False

    auto_count, review_count = update_review_statuses(conn)
    total_integrated = integrate_into_crosswalk(conn)
    print_crosswalk_summary(conn)

    # Sample newly integrated matches
    cur = conn.cursor()
    print("\n=== SAMPLE NEW SPLINK CROSSWALK ENTRIES ===")
    cur.execute("""
        SELECT canonical_name, state, match_confidence, mergent_duns, f7_employer_id
        FROM corporate_identifier_crosswalk
        WHERE match_tier = 'SPLINK_PROB'
        ORDER BY id DESC
        LIMIT 15
    """)
    for row in cur.fetchall():
        name = (row[0] or '')[:50]
        print(f"  {name:<50} {row[1] or '':<4} {row[2]:<12} duns={row[3]} f7={row[4]}")

    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
