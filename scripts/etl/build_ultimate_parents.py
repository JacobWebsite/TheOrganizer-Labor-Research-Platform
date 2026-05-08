"""
Build corporate_ultimate_parents table.

Resolves the topmost ancestor for each child entity in corporate_hierarchy
via a recursive CTE (depth <= 10, cycle-safe). Supports the #44
entity-context feature: profile pages need "Starbucks Corp" totals for a
single Starbucks store, not just the store's own headcount.

Input:  corporate_hierarchy  (parent_duns -> child_duns edges from Mergent
        + GLEIF ownership links resolved to DUNS via crosswalk)
Output: corporate_ultimate_parents  (one row per resolvable child,
        populated with ultimate_parent_{name,duns,lei,cik} + chain_depth)

Adapted from archived script
`archive/db_config_migration_backups/scripts/etl/build_corporate_hierarchy.py:292-424`.
Current corporate_hierarchy schema is narrower (no child_ein / child_cik /
child_lei / parent_ein), so the archived LEI-based chain is dropped.
LEI and CIK are backfilled onto resolved entities from
corporate_identifier_crosswalk after the DUNS walk.

Run:  py scripts/etl/build_ultimate_parents.py
"""
import time

from db_config import get_connection


def drop_and_create(conn):
    print('=== Creating corporate_ultimate_parents ===')
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS corporate_ultimate_parents CASCADE')
    cur.execute("""
        CREATE TABLE corporate_ultimate_parents (
            id SERIAL PRIMARY KEY,
            entity_name TEXT,
            entity_duns VARCHAR(20),
            entity_lei VARCHAR(20),
            entity_cik INTEGER,
            entity_f7_employer_id TEXT,
            ultimate_parent_name TEXT,
            ultimate_parent_duns VARCHAR(20),
            ultimate_parent_lei VARCHAR(20),
            ultimate_parent_cik INTEGER,
            chain_depth INT,
            source TEXT,
            built_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()


def resolve_duns_chains(conn):
    """Walk child_duns -> parent_duns up the hierarchy. Insert topmost ancestor per child."""
    print('\n--- Resolving DUNS-based ultimate parents ---')
    cur = conn.cursor()
    start = time.time()

    # Current corporate_hierarchy relationship_type values in use:
    #   'ownership', 'domestic_parent' (from Mergent)
    #   'direct', 'indirect', 'unknown' (from GLEIF)
    # All represent valid parent/child relationships for corporate-family
    # rollups, so we don't filter on type -- we only require both sides to
    # have DUNS (naturally excludes GLEIF rows the crosswalk couldn't resolve).
    #
    # Cycle safety: carry the full visited path as an array. At each step we
    # refuse to re-visit any ancestor already seen for this entity. A bare
    # `parent <> entity` check would only catch immediate self-loops and
    # would allow longer rings (A->B->C->A) to run to the depth cap with an
    # arbitrary node recorded as the "ultimate parent". The path-array guard
    # is the standard PostgreSQL recursive-CTE pattern for true cycle safety.
    cur.execute("""
        WITH RECURSIVE chain AS (
            -- Base: every direct edge where both sides have DUNS
            SELECT
                child_duns        AS entity_duns,
                child_name        AS entity_name,
                child_f7_employer_id AS entity_f7_id,
                parent_duns,
                parent_name,
                parent_cik,
                parent_lei,
                1 AS depth,
                source,
                ARRAY[child_duns, parent_duns]::TEXT[] AS path
            FROM corporate_hierarchy
            WHERE child_duns IS NOT NULL
              AND parent_duns IS NOT NULL
              AND child_duns <> parent_duns

            UNION ALL

            -- Recursive: walk up. Stop at depth 10; refuse any DUNS already
            -- in the path (true cycle detection, not just immediate self).
            SELECT
                c.entity_duns,
                c.entity_name,
                c.entity_f7_id,
                h.parent_duns,
                h.parent_name,
                h.parent_cik,
                h.parent_lei,
                c.depth + 1,
                c.source,
                c.path || h.parent_duns
            FROM chain c
            JOIN corporate_hierarchy h ON c.parent_duns = h.child_duns
            WHERE c.depth < 10
              AND h.parent_duns IS NOT NULL
              AND h.parent_duns <> h.child_duns
              AND h.parent_duns <> ALL(c.path)
        ),
        ultimate AS (
            SELECT DISTINCT ON (entity_duns)
                entity_duns,
                entity_name,
                entity_f7_id,
                parent_duns AS ultimate_parent_duns,
                parent_name AS ultimate_parent_name,
                parent_cik  AS ultimate_parent_cik,
                parent_lei  AS ultimate_parent_lei,
                depth AS chain_depth,
                source
            FROM chain
            ORDER BY entity_duns, depth DESC
        )
        INSERT INTO corporate_ultimate_parents
            (entity_name, entity_duns, entity_f7_employer_id,
             ultimate_parent_name, ultimate_parent_duns,
             ultimate_parent_cik, ultimate_parent_lei,
             chain_depth, source)
        SELECT
            entity_name, entity_duns, entity_f7_id,
            ultimate_parent_name, ultimate_parent_duns,
            ultimate_parent_cik, ultimate_parent_lei,
            chain_depth, source
        FROM ultimate
    """)
    inserted = cur.rowcount
    conn.commit()
    print(f'  Inserted {inserted:,} ultimate-parent rows ({time.time()-start:.1f}s)')


def backfill_lei_cik(conn):
    """Backfill entity_lei / entity_cik from crosswalk by DUNS match."""
    print('\n--- Backfilling entity_lei / entity_cik from crosswalk ---')
    cur = conn.cursor()
    start = time.time()

    cur.execute("""
        UPDATE corporate_ultimate_parents cup
        SET entity_lei = cw.gleif_lei,
            entity_cik = cw.sec_cik
        FROM corporate_identifier_crosswalk cw
        WHERE cup.entity_duns = cw.mergent_duns
          AND cup.entity_duns IS NOT NULL
    """)
    updated = cur.rowcount
    conn.commit()
    print(f'  Updated {updated:,} rows with LEI/CIK ({time.time()-start:.1f}s)')


def create_indexes(conn):
    print('\n--- Creating indexes ---')
    cur = conn.cursor()
    start = time.time()
    indexes = [
        'CREATE INDEX idx_cup_entity_duns ON corporate_ultimate_parents(entity_duns) WHERE entity_duns IS NOT NULL',
        'CREATE INDEX idx_cup_entity_lei  ON corporate_ultimate_parents(entity_lei)  WHERE entity_lei IS NOT NULL',
        'CREATE INDEX idx_cup_entity_cik  ON corporate_ultimate_parents(entity_cik)  WHERE entity_cik IS NOT NULL',
        'CREATE INDEX idx_cup_entity_f7   ON corporate_ultimate_parents(entity_f7_employer_id) WHERE entity_f7_employer_id IS NOT NULL',
        'CREATE INDEX idx_cup_parent_duns ON corporate_ultimate_parents(ultimate_parent_duns) WHERE ultimate_parent_duns IS NOT NULL',
        'CREATE INDEX idx_cup_parent_cik  ON corporate_ultimate_parents(ultimate_parent_cik)  WHERE ultimate_parent_cik IS NOT NULL',
    ]
    for idx in indexes:
        cur.execute(idx)
    conn.commit()
    print(f'  {len(indexes)} indexes in {time.time()-start:.1f}s')


def sanity_checks(conn):
    print('\n--- Sanity checks ---')
    cur = conn.cursor()

    cur.execute('SELECT COUNT(*) FROM corporate_ultimate_parents')
    total = cur.fetchone()[0]
    print(f'  Total rows: {total:,}')

    # DISTINCT ON should guarantee uniqueness per entity_duns. Verify.
    cur.execute("""
        SELECT entity_duns, COUNT(*) AS c
        FROM corporate_ultimate_parents
        WHERE entity_duns IS NOT NULL
        GROUP BY entity_duns
        HAVING COUNT(*) > 1
        LIMIT 5
    """)
    dups = cur.fetchall()
    if dups:
        print(f'  [WARN] {len(dups)} entity_duns have multiple rows (should be 0):')
        for row in dups:
            print(f'    {row[0]}: {row[1]}')
    else:
        print('  OK: every entity_duns has exactly one ultimate-parent row')

    cur.execute("""
        SELECT chain_depth, COUNT(*)
        FROM corporate_ultimate_parents
        GROUP BY chain_depth ORDER BY chain_depth
    """)
    print('  Chain-depth distribution:')
    for depth, count in cur.fetchall():
        print(f'    depth {depth}: {count:,}')

    cur.execute("""
        SELECT COUNT(*) FROM corporate_ultimate_parents
        WHERE entity_lei IS NOT NULL
    """)
    lei_count = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM corporate_ultimate_parents
        WHERE entity_cik IS NOT NULL
    """)
    cik_count = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM corporate_ultimate_parents
        WHERE entity_f7_employer_id IS NOT NULL
    """)
    f7_count = cur.fetchone()[0]
    print(f'  Backfill coverage: LEI={lei_count:,}  CIK={cik_count:,}  F7={f7_count:,}')


def spot_check(conn):
    print('\n--- Spot-check (Starbucks / Whole Foods / Kroger / Walmart) ---')
    cur = conn.cursor()
    cur.execute("""
        SELECT entity_name, ultimate_parent_name, chain_depth, source
        FROM corporate_ultimate_parents
        WHERE entity_name ILIKE 'starbucks%'
           OR entity_name ILIKE 'whole foods%'
           OR entity_name ILIKE 'kroger%'
           OR entity_name ILIKE 'walmart%'
        ORDER BY chain_depth DESC, entity_name
        LIMIT 20
    """)
    rows = cur.fetchall()
    if not rows:
        print('  [WARN] no spot-check rows matched -- verify corporate_hierarchy has Mergent data loaded')
        return
    for entity, parent, depth, source in rows:
        print(f'  [{source} d{depth}] {entity[:50]:50s} -> {parent}')


if __name__ == '__main__':
    overall_start = time.time()
    conn = get_connection()
    conn.autocommit = False
    try:
        drop_and_create(conn)
        resolve_duns_chains(conn)
        backfill_lei_cik(conn)
        create_indexes(conn)
        sanity_checks(conn)
        spot_check(conn)
    finally:
        conn.close()
    print(f'\nTotal time: {time.time()-overall_start:.1f}s')
