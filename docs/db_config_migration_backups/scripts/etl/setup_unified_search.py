import os
"""
Setup unified employer search: review flags table + materialized view.

Creates:
  - employer_review_flags table for manual review flagging
  - mv_employer_search materialized view combining F7, NLRB, VR, manual sources
  - GIN trigram + B-tree indexes for fast search

Run: py scripts/etl/setup_unified_search.py
"""

import psycopg2

def main():
    conn = psycopg2.connect(
        host='localhost', dbname='olms_multiyear',
        user='postgres', password=os.environ.get('DB_PASSWORD', '')
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Step 1: Create review flags table
    print("Step 1: Creating employer_review_flags table...")
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
    cur.execute("SELECT COUNT(*) FROM employer_review_flags")
    print(f"  employer_review_flags: {cur.fetchone()[0]} existing rows")

    # Step 2: Drop old MV if exists, create new one
    print("Step 2: Creating mv_employer_search materialized view...")
    cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_employer_search CASCADE")

    # NLRB employers: deduplicate by name+city+state, pick the row with the most
    # recent election (via case_number sort) and aggregate election info.
    # VR employers: unmatched only, with employee count.
    # Manual employers: all 509 research discoveries.
    cur.execute("""
        CREATE MATERIALIZED VIEW mv_employer_search AS

        -- Source 1: F7 employers (63K, all have union)
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
            LOWER(e.employer_name) AS search_name
        FROM f7_employers_deduped e

        UNION ALL

        -- Source 2: NLRB employer participants (unmatched to F7)
        -- Deduplicate: one row per distinct name+city+state, prefer cases with union wins
        -- Join to elections/tallies for union win status, unit size, and union name
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
            LOWER(sub.participant_name) AS search_name
        FROM (
            SELECT DISTINCT ON (UPPER(p.participant_name), UPPER(COALESCE(p.city,'')), UPPER(COALESCE(p.state,'')))
                p.id, p.participant_name, p.city, p.state, p.address_1, p.zip, p.case_number,
                e.union_won, e.eligible_voters,
                t.labor_org_name, t.matched_olms_fnum
            FROM nlrb_participants p
            LEFT JOIN nlrb_elections e ON p.case_number = e.case_number
            LEFT JOIN nlrb_tallies t ON e.case_number = t.case_number AND t.tally_type = 'For'
            WHERE p.participant_type = 'Employer'
              AND p.matched_employer_id IS NULL
              AND p.participant_name IS NOT NULL
              AND LENGTH(TRIM(p.participant_name)) > 1
            ORDER BY UPPER(p.participant_name), UPPER(COALESCE(p.city,'')), UPPER(COALESCE(p.state,'')),
                     e.union_won DESC NULLS LAST, e.election_date DESC NULLS LAST
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
            LOWER(vr.employer_name) AS search_name
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
            LOWER(m.employer_name) AS search_name
        FROM manual_employers m
    """)

    # Step 3: Create indexes
    print("Step 3: Creating indexes...")
    cur.execute("CREATE INDEX idx_mv_employer_search_trgm ON mv_employer_search USING GIN (search_name gin_trgm_ops)")
    cur.execute("CREATE INDEX idx_mv_employer_search_state ON mv_employer_search (state)")
    cur.execute("CREATE INDEX idx_mv_employer_search_city ON mv_employer_search (UPPER(city))")
    cur.execute("CREATE INDEX idx_mv_employer_search_id ON mv_employer_search (canonical_id)")
    cur.execute("CREATE INDEX idx_mv_employer_search_source ON mv_employer_search (source_type)")

    # Step 4: Verify
    print("\nStep 4: Verifying...")
    cur.execute("SELECT source_type, COUNT(*), SUM(CASE WHEN has_union THEN 1 ELSE 0 END) as with_union FROM mv_employer_search GROUP BY source_type ORDER BY COUNT(*) DESC")
    rows = cur.fetchall()
    total = 0
    for r in rows:
        print(f"  {r[0]}: {r[1]:,} records ({r[2]:,} with union)")
        total += r[1]
    print(f"  TOTAL: {total:,} records")

    cur.execute("SELECT COUNT(*) FROM employer_review_flags")
    print(f"\n  Review flags: {cur.fetchone()[0]}")

    cur.close()
    conn.close()
    print("\nDone! Materialized view mv_employer_search is ready.")


if __name__ == '__main__':
    main()
