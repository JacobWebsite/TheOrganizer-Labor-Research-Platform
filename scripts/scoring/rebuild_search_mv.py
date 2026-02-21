"""
Rebuild mv_employer_search with dedup and historical filtering.

Changes from original (archive/old_scripts/etl_archive/setup_unified_search.py):
  - F7 source: canonical dedup (show rep for grouped, all ungrouped)
  - F7 source: exclude historical (pre-2020) records
  - New columns: canonical_group_id, group_member_count, consolidated_workers
  - UNIQUE INDEX on canonical_id for REFRESH CONCURRENTLY support

Usage: py scripts/scoring/rebuild_search_mv.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # ── Before counts ───────────────────────────────────────────────────
    print("Getting before counts...")
    before_total = 0
    try:
        cur.execute("""
            SELECT source_type, COUNT(*)
            FROM mv_employer_search
            GROUP BY source_type ORDER BY COUNT(*) DESC
        """)
        before_counts = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM mv_employer_search")
        before_total = cur.fetchone()[0]
        print(f"  Before: {before_total:,} total rows")
        for r in before_counts:
            print(f"    {r[0]}: {r[1]:,}")
    except Exception:
        print("  (mv_employer_search does not exist yet)")

    # ── Drop old MV ─────────────────────────────────────────────────────
    print("\nDropping old mv_employer_search...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_employer_search CASCADE")

    # ── Ensure review-flags table exists ────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employer_review_flags (
            id SERIAL PRIMARY KEY,
            source_type VARCHAR(20) NOT NULL,
            source_id TEXT NOT NULL,
            flag_type VARCHAR(50) NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(source_type, source_id, flag_type)
        )
    """)

    # ── Create new MV with dedup ────────────────────────────────────────
    print("Creating mv_employer_search with dedup + historical filter...")
    cur.execute("""
        CREATE MATERIALIZED VIEW mv_employer_search AS

        -- Source 1: F7 employers
        --   Grouped employers: only the canonical representative
        --   Ungrouped employers: all (they are already 1 row per entity)
        --   Historical (pre-2020): excluded
        SELECT
            e.employer_id AS canonical_id,
            'F7' AS source_type,
            e.employer_name,
            e.city,
            e.state,
            e.street,
            e.zip,
            e.naics,
            e.latest_unit_size AS unit_size,
            e.latest_union_name AS union_name,
            e.latest_union_fnum::text AS union_fnum,
            TRUE AS has_union,
            e.latitude,
            e.longitude,
            LOWER(e.employer_name) AS search_name,
            e.canonical_group_id,
            g.member_count AS group_member_count,
            g.consolidated_workers
        FROM f7_employers_deduped e
        LEFT JOIN employer_canonical_groups g
            ON e.canonical_group_id = g.group_id
        WHERE NOT e.is_historical
          AND (e.canonical_group_id IS NULL
               OR e.is_canonical_rep = TRUE)

        UNION ALL

        -- Source 2: NLRB employer participants (unmatched to F7)
        SELECT
            'NLRB-' || sub.id::text AS canonical_id,
            'NLRB' AS source_type,
            sub.participant_name AS employer_name,
            sub.city,
            sub.state,
            sub.address_1 AS street,
            sub.zip,
            NULL AS naics,
            sub.eligible_voters AS unit_size,
            sub.labor_org_name AS union_name,
            sub.matched_olms_fnum AS union_fnum,
            COALESCE(sub.union_won, FALSE) AS has_union,
            NULL::double precision AS latitude,
            NULL::double precision AS longitude,
            LOWER(sub.participant_name) AS search_name,
            NULL::int AS canonical_group_id,
            NULL::int AS group_member_count,
            NULL::int AS consolidated_workers
        FROM (
            SELECT DISTINCT ON (
                UPPER(p.participant_name),
                UPPER(COALESCE(p.city, '')),
                UPPER(COALESCE(p.state, ''))
            )
                p.id, p.participant_name, p.city, p.state,
                p.address_1, p.zip, p.case_number,
                e.union_won, e.eligible_voters,
                t.labor_org_name, t.matched_olms_fnum
            FROM nlrb_participants p
            LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
            LEFT JOIN nlrb_tallies t
                ON e.case_number = t.case_number AND t.tally_type = 'For'
            WHERE p.participant_type = 'Employer'
              AND p.matched_employer_id IS NULL
              AND p.participant_name IS NOT NULL
              AND LENGTH(TRIM(p.participant_name)) > 1
            ORDER BY
                UPPER(p.participant_name),
                UPPER(COALESCE(p.city, '')),
                UPPER(COALESCE(p.state, '')),
                e.union_won DESC NULLS LAST,
                e.election_date DESC NULLS LAST
        ) sub

        UNION ALL

        -- Source 3: Voluntary Recognition (unmatched to F7)
        SELECT
            'VR-' || vr.vr_case_number AS canonical_id,
            'VR' AS source_type,
            vr.employer_name,
            vr.unit_city AS city,
            vr.unit_state AS state,
            NULL AS street,
            NULL AS zip,
            NULL AS naics,
            vr.num_employees AS unit_size,
            vr.union_name,
            vr.matched_union_fnum::text AS union_fnum,
            TRUE AS has_union,
            NULL::double precision AS latitude,
            NULL::double precision AS longitude,
            LOWER(vr.employer_name) AS search_name,
            NULL::int AS canonical_group_id,
            NULL::int AS group_member_count,
            NULL::int AS consolidated_workers
        FROM nlrb_voluntary_recognition vr
        WHERE vr.matched_employer_id IS NULL
          AND vr.employer_name IS NOT NULL

        UNION ALL

        -- Source 4: Manual/research employers
        SELECT
            'MANUAL-' || m.id::text AS canonical_id,
            'MANUAL' AS source_type,
            m.employer_name,
            m.city,
            m.state,
            NULL AS street,
            NULL AS zip,
            m.naics_sector AS naics,
            m.num_employees AS unit_size,
            m.union_name,
            NULL AS union_fnum,
            TRUE AS has_union,
            NULL::double precision AS latitude,
            NULL::double precision AS longitude,
            LOWER(m.employer_name) AS search_name,
            NULL::int AS canonical_group_id,
            NULL::int AS group_member_count,
            NULL::int AS consolidated_workers
        FROM manual_employers m
    """)

    # ── Indexes ─────────────────────────────────────────────────────────
    print("Creating indexes...")
    cur.execute("""
        CREATE INDEX idx_mv_search_trgm
        ON mv_employer_search USING GIN (search_name gin_trgm_ops)
    """)
    cur.execute("""
        CREATE INDEX idx_mv_search_state
        ON mv_employer_search (state)
    """)
    cur.execute("""
        CREATE INDEX idx_mv_search_city
        ON mv_employer_search (UPPER(city))
    """)
    cur.execute("""
        CREATE UNIQUE INDEX idx_mv_search_canonical_id
        ON mv_employer_search (canonical_id)
    """)
    cur.execute("""
        CREATE INDEX idx_mv_search_source
        ON mv_employer_search (source_type)
    """)
    cur.execute("""
        CREATE INDEX idx_mv_search_group
        ON mv_employer_search (canonical_group_id)
        WHERE canonical_group_id IS NOT NULL
    """)

    # ── Verify ──────────────────────────────────────────────────────────
    print("\nVerifying...")
    cur.execute("""
        SELECT source_type, COUNT(*)
        FROM mv_employer_search
        GROUP BY source_type ORDER BY COUNT(*) DESC
    """)
    after_counts = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM mv_employer_search")
    after_total = cur.fetchone()[0]

    print(f"  After: {after_total:,} total rows")
    for r in after_counts:
        print(f"    {r[0]}: {r[1]:,}")

    if before_total > 0:
        reduction = before_total - after_total
        pct = 100.0 * reduction / before_total
        print(f"\n  Reduction: {reduction:,} rows ({pct:.1f}%)")

    # F7 dedup stats
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE canonical_group_id IS NOT NULL) AS grouped,
            COUNT(*) FILTER (WHERE canonical_group_id IS NULL) AS ungrouped,
            COUNT(*) FILTER (WHERE group_member_count > 1) AS with_group_info
        FROM mv_employer_search
        WHERE source_type = 'F7'
    """)
    stats = cur.fetchone()
    print(f"\n  F7 dedup stats:")
    print(f"    Grouped (canonical reps): {stats[0]:,}")
    print(f"    Ungrouped (singletons):   {stats[1]:,}")
    print(f"    With group info:          {stats[2]:,}")

    cur.close()
    conn.close()
    print("\nDone! mv_employer_search rebuilt with dedup.")


if __name__ == '__main__':
    main()
