"""
Phase 4: Build corporate hierarchy from GLEIF ownership + Mergent parent DUNS.

Steps:
- 4A: GLEIF ownership links -> corporate_hierarchy (direct + indirect)
- 4B: Mergent parent_duns / domestic_parent_duns -> corporate_hierarchy
- 4C: Cross-enrich hierarchy records with crosswalk identifiers
- 4D: Resolve ultimate parents via recursive CTE

Usage:
    py scripts/etl/build_corporate_hierarchy.py
"""

import sys
import time

import psycopg2
import psycopg2.extras
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def create_tables(conn):
    """Create hierarchy tables."""
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS corporate_ultimate_parents CASCADE")
    cur.execute("DROP TABLE IF EXISTS corporate_hierarchy CASCADE")

    cur.execute("""
        CREATE TABLE corporate_hierarchy (
            id SERIAL PRIMARY KEY,
            parent_name TEXT,
            parent_ein VARCHAR(20),
            parent_cik INTEGER,
            parent_lei VARCHAR(20),
            parent_duns VARCHAR(20),
            child_name TEXT,
            child_ein VARCHAR(20),
            child_cik INTEGER,
            child_lei VARCHAR(20),
            child_duns VARCHAR(20),
            relationship_type VARCHAR(30),
            is_direct BOOLEAN DEFAULT TRUE,
            source TEXT NOT NULL,
            confidence VARCHAR(20) NOT NULL,
            parent_f7_employer_id TEXT,
            parent_mergent_duns VARCHAR(20),
            child_f7_employer_id TEXT,
            child_mergent_duns VARCHAR(20),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE corporate_ultimate_parents (
            id SERIAL PRIMARY KEY,
            entity_name TEXT,
            entity_ein VARCHAR(20),
            entity_duns VARCHAR(20),
            entity_cik INTEGER,
            entity_lei VARCHAR(20),
            entity_f7_id TEXT,
            ultimate_parent_name TEXT,
            ultimate_parent_ein VARCHAR(20),
            ultimate_parent_duns VARCHAR(20),
            ultimate_parent_cik INTEGER,
            ultimate_parent_lei VARCHAR(20),
            chain_depth INTEGER,
            source TEXT
        )
    """)
    conn.commit()
    print("  Created corporate_hierarchy and corporate_ultimate_parents tables")


def step_4a_gleif_hierarchy(conn):
    """4A: GLEIF ownership links -> hierarchy."""
    print("\n--- Step 4A: GLEIF ownership -> hierarchy ---")
    cur = conn.cursor()
    start = time.time()

    cur.execute("""
        INSERT INTO corporate_hierarchy (parent_name, parent_lei, child_name, child_lei,
            relationship_type, is_direct, source, confidence)
        SELECT
            p.entity_name,
            p.lei,
            c.entity_name,
            c.lei,
            CASE ol.interest_level
                WHEN 'direct' THEN 'PARENT_SUBSIDIARY'
                WHEN 'indirect' THEN 'ULTIMATE_PARENT'
                ELSE 'RELATED'
            END,
            ol.interest_level = 'direct',
            'GLEIF',
            CASE ol.interest_level
                WHEN 'direct' THEN 'HIGH'
                WHEN 'indirect' THEN 'MEDIUM'
                ELSE 'LOW'
            END
        FROM gleif_ownership_links ol
        JOIN gleif_us_entities p ON ol.parent_entity_id = p.id
        JOIN gleif_us_entities c ON ol.child_entity_id = c.id
        WHERE ol.parent_entity_id IS NOT NULL
          AND ol.child_entity_id IS NOT NULL
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  GLEIF both-US links: {count:,} ({elapsed:.1f}s)")
    return count


def step_4b_mergent_hierarchy(conn):
    """4B: Mergent parent_duns -> hierarchy."""
    print("\n--- Step 4B: Mergent parent DUNS -> hierarchy ---")
    cur = conn.cursor()
    start = time.time()

    # Direct parent
    cur.execute("""
        INSERT INTO corporate_hierarchy (parent_name, parent_duns, child_name, child_duns,
            parent_mergent_duns, child_mergent_duns,
            relationship_type, is_direct, source, confidence)
        SELECT
            COALESCE(mp.company_name, m.parent_name),
            m.parent_duns,
            m.company_name,
            m.duns,
            m.parent_duns,
            m.duns,
            'PARENT_SUBSIDIARY',
            TRUE,
            'MERGENT',
            'HIGH'
        FROM mergent_employers m
        LEFT JOIN mergent_employers mp ON m.parent_duns = mp.duns
        WHERE m.parent_duns IS NOT NULL
          AND m.parent_duns != m.duns
          AND m.parent_duns != ''
    """)
    parent_count = cur.rowcount
    conn.commit()
    print(f"  Mergent direct parent links: {parent_count:,}")

    # Domestic ultimate parent (if different from direct parent)
    cur.execute("""
        INSERT INTO corporate_hierarchy (parent_name, parent_duns, child_name, child_duns,
            parent_mergent_duns, child_mergent_duns,
            relationship_type, is_direct, source, confidence)
        SELECT
            COALESCE(dp.company_name, m.domestic_parent_name),
            m.domestic_parent_duns,
            m.company_name,
            m.duns,
            m.domestic_parent_duns,
            m.duns,
            'ULTIMATE_PARENT',
            FALSE,
            'MERGENT',
            'MEDIUM'
        FROM mergent_employers m
        LEFT JOIN mergent_employers dp ON m.domestic_parent_duns = dp.duns
        WHERE m.domestic_parent_duns IS NOT NULL
          AND m.domestic_parent_duns != m.duns
          AND m.domestic_parent_duns != ''
          AND m.domestic_parent_duns != COALESCE(m.parent_duns, '')
    """)
    domestic_count = cur.rowcount
    conn.commit()

    elapsed = time.time() - start
    print(f"  Mergent domestic parent links: {domestic_count:,}")
    print(f"  Total Mergent: {parent_count + domestic_count:,} ({elapsed:.1f}s)")
    return parent_count + domestic_count


def step_4c_cross_enrich(conn):
    """4C: Enrich hierarchy records with crosswalk identifiers."""
    print("\n--- Step 4C: Cross-enrich via crosswalk ---")
    cur = conn.cursor()
    start = time.time()

    # Enrich parent identifiers via crosswalk (by DUNS)
    cur.execute("""
        UPDATE corporate_hierarchy h
        SET parent_cik = x.cik,
            parent_ein = COALESCE(h.parent_ein, x.ein)
        FROM corporate_identifier_crosswalk x
        WHERE h.parent_duns = x.duns
          AND x.cik IS NOT NULL
          AND h.parent_cik IS NULL
    """)
    parent_duns_enriched = cur.rowcount
    conn.commit()

    # Enrich child identifiers via crosswalk (by DUNS)
    cur.execute("""
        UPDATE corporate_hierarchy h
        SET child_cik = x.cik,
            child_ein = COALESCE(h.child_ein, x.ein)
        FROM corporate_identifier_crosswalk x
        WHERE h.child_duns = x.duns
          AND x.cik IS NOT NULL
          AND h.child_cik IS NULL
    """)
    child_duns_enriched = cur.rowcount
    conn.commit()

    # Enrich via LEI
    cur.execute("""
        UPDATE corporate_hierarchy h
        SET parent_cik = x.cik,
            parent_ein = COALESCE(h.parent_ein, x.ein),
            parent_duns = COALESCE(h.parent_duns, x.duns)
        FROM corporate_identifier_crosswalk x
        WHERE h.parent_lei = x.lei
          AND x.lei IS NOT NULL
          AND h.parent_cik IS NULL
    """)
    parent_lei_enriched = cur.rowcount
    conn.commit()

    cur.execute("""
        UPDATE corporate_hierarchy h
        SET child_cik = x.cik,
            child_ein = COALESCE(h.child_ein, x.ein),
            child_duns = COALESCE(h.child_duns, x.duns)
        FROM corporate_identifier_crosswalk x
        WHERE h.child_lei = x.lei
          AND x.lei IS NOT NULL
          AND h.child_cik IS NULL
    """)
    child_lei_enriched = cur.rowcount
    conn.commit()

    # Link F7 employer IDs
    cur.execute("""
        UPDATE corporate_hierarchy h
        SET child_f7_employer_id = m.matched_f7_employer_id
        FROM mergent_employers m
        WHERE h.child_duns = m.duns
          AND h.child_f7_employer_id IS NULL
          AND m.matched_f7_employer_id IS NOT NULL
    """)
    f7_linked = cur.rowcount
    conn.commit()

    cur.execute("""
        UPDATE corporate_hierarchy h
        SET parent_f7_employer_id = m.matched_f7_employer_id
        FROM mergent_employers m
        WHERE h.parent_duns = m.duns
          AND h.parent_f7_employer_id IS NULL
          AND m.matched_f7_employer_id IS NOT NULL
    """)
    f7_parent_linked = cur.rowcount
    conn.commit()

    # Also link via crosswalk F7 IDs
    cur.execute("""
        UPDATE corporate_hierarchy h
        SET child_f7_employer_id = x.f7_employer_id
        FROM corporate_identifier_crosswalk x
        WHERE (h.child_duns = x.duns OR h.child_lei = x.lei OR h.child_cik = x.cik)
          AND h.child_f7_employer_id IS NULL
          AND x.f7_employer_id IS NOT NULL
    """)
    f7_xwalk = cur.rowcount
    conn.commit()

    elapsed = time.time() - start
    print(f"  Enriched parent DUNS->CIK: {parent_duns_enriched:,}")
    print(f"  Enriched child DUNS->CIK: {child_duns_enriched:,}")
    print(f"  Enriched parent LEI->CIK: {parent_lei_enriched:,}")
    print(f"  Enriched child LEI->CIK: {child_lei_enriched:,}")
    print(f"  F7 child linked: {f7_linked:,}")
    print(f"  F7 parent linked: {f7_parent_linked:,}")
    print(f"  F7 via crosswalk: {f7_xwalk:,}")
    print(f"  ({elapsed:.1f}s)")


def step_4d_ultimate_parents(conn):
    """4D: Resolve ultimate parents via recursive walk."""
    print("\n--- Step 4D: Resolving ultimate parents ---")
    cur = conn.cursor()
    start = time.time()

    # Use DUNS-based chain resolution (Mergent has the best DUNS coverage)
    cur.execute("""
        WITH RECURSIVE chain AS (
            -- Base: all direct parent-subsidiary links
            SELECT
                child_duns as entity_duns,
                child_name as entity_name,
                child_ein as entity_ein,
                child_cik as entity_cik,
                child_lei as entity_lei,
                child_f7_employer_id as entity_f7_id,
                parent_duns,
                parent_name,
                parent_ein,
                parent_cik,
                parent_lei,
                1 as depth,
                source
            FROM corporate_hierarchy
            WHERE child_duns IS NOT NULL
              AND parent_duns IS NOT NULL
              AND relationship_type = 'PARENT_SUBSIDIARY'

            UNION ALL

            -- Recursive: walk up the chain
            SELECT
                c.entity_duns,
                c.entity_name,
                c.entity_ein,
                c.entity_cik,
                c.entity_lei,
                c.entity_f7_id,
                h.parent_duns,
                h.parent_name,
                h.parent_ein,
                h.parent_cik,
                h.parent_lei,
                c.depth + 1,
                c.source
            FROM chain c
            JOIN corporate_hierarchy h ON c.parent_duns = h.child_duns
            WHERE c.depth < 10
              AND h.relationship_type = 'PARENT_SUBSIDIARY'
              AND h.parent_duns IS NOT NULL
              AND h.parent_duns != c.entity_duns  -- prevent cycles
        ),
        -- Find the ultimate parent (no one above them)
        ultimate AS (
            SELECT DISTINCT ON (entity_duns)
                entity_duns, entity_name, entity_ein, entity_cik, entity_lei, entity_f7_id,
                parent_duns as ultimate_parent_duns,
                parent_name as ultimate_parent_name,
                parent_ein as ultimate_parent_ein,
                parent_cik as ultimate_parent_cik,
                parent_lei as ultimate_parent_lei,
                depth as chain_depth,
                source
            FROM chain
            ORDER BY entity_duns, depth DESC
        )
        INSERT INTO corporate_ultimate_parents
            (entity_name, entity_ein, entity_duns, entity_cik, entity_lei, entity_f7_id,
             ultimate_parent_name, ultimate_parent_ein, ultimate_parent_duns,
             ultimate_parent_cik, ultimate_parent_lei, chain_depth, source)
        SELECT
            entity_name, entity_ein, entity_duns, entity_cik, entity_lei, entity_f7_id,
            ultimate_parent_name, ultimate_parent_ein, ultimate_parent_duns,
            ultimate_parent_cik, ultimate_parent_lei, chain_depth, source
        FROM ultimate
    """)
    duns_count = cur.rowcount
    conn.commit()

    # Also do LEI-based chain resolution for GLEIF records
    cur.execute("""
        WITH RECURSIVE chain AS (
            SELECT
                child_lei as entity_lei,
                child_name as entity_name,
                parent_lei,
                parent_name,
                1 as depth
            FROM corporate_hierarchy
            WHERE child_lei IS NOT NULL
              AND parent_lei IS NOT NULL
              AND source = 'GLEIF'

            UNION ALL

            SELECT
                c.entity_lei,
                c.entity_name,
                h.parent_lei,
                h.parent_name,
                c.depth + 1
            FROM chain c
            JOIN corporate_hierarchy h ON c.parent_lei = h.child_lei
            WHERE c.depth < 10
              AND h.source = 'GLEIF'
              AND h.parent_lei IS NOT NULL
              AND h.parent_lei != c.entity_lei
        ),
        ultimate AS (
            SELECT DISTINCT ON (entity_lei)
                entity_lei, entity_name,
                parent_lei as ultimate_parent_lei,
                parent_name as ultimate_parent_name,
                depth as chain_depth
            FROM chain
            ORDER BY entity_lei, depth DESC
        )
        INSERT INTO corporate_ultimate_parents
            (entity_name, entity_lei, ultimate_parent_name, ultimate_parent_lei, chain_depth, source)
        SELECT entity_name, entity_lei, ultimate_parent_name, ultimate_parent_lei, chain_depth, 'GLEIF'
        FROM ultimate
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_ultimate_parents cup WHERE cup.entity_lei = ultimate.entity_lei
        )
    """)
    lei_count = cur.rowcount
    conn.commit()

    elapsed = time.time() - start
    print(f"  DUNS-based chains: {duns_count:,}")
    print(f"  LEI-based chains: {lei_count:,}")
    print(f"  Total ultimate parents resolved: {duns_count + lei_count:,} ({elapsed:.1f}s)")

    # Chain depth stats
    cur.execute("""
        SELECT chain_depth, COUNT(*)
        FROM corporate_ultimate_parents
        GROUP BY chain_depth ORDER BY chain_depth
    """)
    print("  Chain depth distribution:")
    for row in cur.fetchall():
        print(f"    Depth {row[0]}: {row[1]:,}")


def create_indexes(conn):
    """Create indexes on hierarchy tables."""
    print("\n  Creating hierarchy indexes...")
    cur = conn.cursor()

    # corporate_hierarchy
    cur.execute("CREATE INDEX idx_hier_parent_duns ON corporate_hierarchy(parent_duns) WHERE parent_duns IS NOT NULL")
    cur.execute("CREATE INDEX idx_hier_child_duns ON corporate_hierarchy(child_duns) WHERE child_duns IS NOT NULL")
    cur.execute("CREATE INDEX idx_hier_parent_lei ON corporate_hierarchy(parent_lei) WHERE parent_lei IS NOT NULL")
    cur.execute("CREATE INDEX idx_hier_child_lei ON corporate_hierarchy(child_lei) WHERE child_lei IS NOT NULL")
    cur.execute("CREATE INDEX idx_hier_parent_f7 ON corporate_hierarchy(parent_f7_employer_id) WHERE parent_f7_employer_id IS NOT NULL")
    cur.execute("CREATE INDEX idx_hier_child_f7 ON corporate_hierarchy(child_f7_employer_id) WHERE child_f7_employer_id IS NOT NULL")
    cur.execute("CREATE INDEX idx_hier_source ON corporate_hierarchy(source)")

    # corporate_ultimate_parents
    cur.execute("CREATE INDEX idx_cup_entity_duns ON corporate_ultimate_parents(entity_duns) WHERE entity_duns IS NOT NULL")
    cur.execute("CREATE INDEX idx_cup_entity_lei ON corporate_ultimate_parents(entity_lei) WHERE entity_lei IS NOT NULL")
    cur.execute("CREATE INDEX idx_cup_entity_f7 ON corporate_ultimate_parents(entity_f7_id) WHERE entity_f7_id IS NOT NULL")
    cur.execute("CREATE INDEX idx_cup_parent_duns ON corporate_ultimate_parents(ultimate_parent_duns) WHERE ultimate_parent_duns IS NOT NULL")

    conn.commit()
    print("  Done")


def print_stats(conn):
    """Print hierarchy summary."""
    print("\n=== Corporate Hierarchy Summary ===")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM corporate_hierarchy")
    print(f"Total hierarchy links: {cur.fetchone()[0]:,}")

    cur.execute("SELECT source, relationship_type, confidence, COUNT(*) FROM corporate_hierarchy GROUP BY source, relationship_type, confidence ORDER BY source, COUNT(*) DESC")
    print("\nBy source/type:")
    for row in cur.fetchall():
        print(f"  {row[0]} / {row[1]} ({row[2]}): {row[3]:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_hierarchy WHERE child_f7_employer_id IS NOT NULL")
    print(f"\nLinks with F7 child: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corporate_hierarchy WHERE parent_f7_employer_id IS NOT NULL")
    print(f"Links with F7 parent: {cur.fetchone()[0]:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_ultimate_parents")
    print(f"\nUltimate parent entries: {cur.fetchone()[0]:,}")

    cur.execute("SELECT COUNT(DISTINCT ultimate_parent_duns) FROM corporate_ultimate_parents WHERE ultimate_parent_duns IS NOT NULL")
    print(f"Distinct ultimate parents (DUNS): {cur.fetchone()[0]:,}")

    cur.execute("SELECT COUNT(DISTINCT entity_f7_id) FROM corporate_ultimate_parents WHERE entity_f7_id IS NOT NULL")
    print(f"F7 employers with ultimate parent: {cur.fetchone()[0]:,}")


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        create_tables(conn)
        step_4a_gleif_hierarchy(conn)
        step_4b_mergent_hierarchy(conn)
        step_4c_cross_enrich(conn)
        step_4d_ultimate_parents(conn)
        create_indexes(conn)
        print_stats(conn)
        print("\n=== Phase 4 Complete ===")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
