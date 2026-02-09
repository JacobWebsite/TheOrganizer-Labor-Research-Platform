"""
Phase 3: Build corporate identifier crosswalk.

Bridges identifiers across data sources:
- Step 3A: Mergent EIN -> SEC CIK (exact EIN match)
- Step 3B: SEC LEI -> GLEIF entities (direct LEI match)
- Step 3C: SEC EIN -> GLEIF via crosswalk enrichment
- Step 3D: 990 EIN -> SEC CIK
- Step 3E: F7 -> SEC (name+state match, F7 has no EIN)

Usage:
    py scripts/etl/build_corporate_crosswalk.py
    py scripts/etl/build_corporate_crosswalk.py --step 3A    # run single step
"""

import sys
import os
import re
import time

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}


def create_table(conn):
    """Create crosswalk table."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS corporate_identifier_crosswalk CASCADE")
    cur.execute("""
        CREATE TABLE corporate_identifier_crosswalk (
            id SERIAL PRIMARY KEY,
            ein VARCHAR(20),
            cik INTEGER,
            lei VARCHAR(20),
            duns VARCHAR(20),
            f7_employer_id TEXT,
            mergent_duns VARCHAR(20),
            source TEXT NOT NULL,
            match_method TEXT NOT NULL,
            match_confidence VARCHAR(20) NOT NULL,
            canonical_name TEXT,
            state VARCHAR(10),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    print("  Created corporate_identifier_crosswalk table")


def step_3a_mergent_sec(conn):
    """3A: Match Mergent employers to SEC companies via EIN."""
    print("\n--- Step 3A: Mergent EIN -> SEC CIK ---")
    cur = conn.cursor()
    start = time.time()

    # Clean EIN format: strip dashes for comparison
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (ein, cik, duns, mergent_duns, source, match_method, match_confidence, canonical_name, state)
        SELECT DISTINCT ON (m.duns)
            REPLACE(m.ein, '-', '') as ein,
            s.cik,
            m.duns,
            m.duns,
            'MERGENT_SEC',
            'EIN_EXACT',
            'HIGH',
            m.company_name,
            m.state
        FROM mergent_employers m
        JOIN sec_companies s ON REPLACE(m.ein, '-', '') = s.ein
        WHERE m.ein IS NOT NULL AND m.ein != ''
          AND s.ein IS NOT NULL
        ORDER BY m.duns, s.is_public DESC, s.cik
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  Matched: {count:,} Mergent -> SEC via EIN ({elapsed:.1f}s)")
    return count


def step_3b_sec_gleif_lei(conn):
    """3B: Match SEC companies to GLEIF entities via LEI."""
    print("\n--- Step 3B: SEC LEI -> GLEIF LEI ---")
    cur = conn.cursor()
    start = time.time()

    # SEC has LEI field directly
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (ein, cik, lei, source, match_method, match_confidence, canonical_name, state)
        SELECT DISTINCT ON (s.cik)
            s.ein,
            s.cik,
            g.lei,
            'SEC_GLEIF',
            'LEI_EXACT',
            'HIGH',
            s.company_name,
            s.state
        FROM sec_companies s
        JOIN gleif_us_entities g ON s.lei = g.lei
        WHERE s.lei IS NOT NULL
          AND g.lei IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk x WHERE x.cik = s.cik AND x.lei IS NOT NULL
          )
        ORDER BY s.cik
    """)
    direct_count = cur.rowcount
    conn.commit()
    print(f"  SEC->GLEIF direct LEI match: {direct_count:,}")

    # Also enrich existing crosswalk records with LEI
    cur.execute("""
        UPDATE corporate_identifier_crosswalk x
        SET lei = g.lei
        FROM sec_companies s
        JOIN gleif_us_entities g ON s.lei = g.lei
        WHERE x.cik = s.cik
          AND x.lei IS NULL
          AND s.lei IS NOT NULL
          AND g.lei IS NOT NULL
    """)
    enriched = cur.rowcount
    conn.commit()

    elapsed = time.time() - start
    print(f"  Enriched existing records with LEI: {enriched:,} ({elapsed:.1f}s)")
    return direct_count + enriched


def step_3c_sec_gleif_ein(conn):
    """3C: Match SEC -> GLEIF where SEC has EIN, try to find GLEIF entity by name+state."""
    print("\n--- Step 3C: Additional SEC->GLEIF via name+state ---")
    cur = conn.cursor()
    start = time.time()

    # For SEC companies not yet in crosswalk with LEI, try name+state match to GLEIF
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (ein, cik, lei, source, match_method, match_confidence, canonical_name, state)
        SELECT DISTINCT ON (s.cik)
            s.ein,
            s.cik,
            g.lei,
            'SEC_GLEIF',
            'NAME_STATE',
            'MEDIUM',
            s.company_name,
            s.state
        FROM sec_companies s
        JOIN gleif_us_entities g ON s.name_normalized = g.name_normalized
            AND s.state = g.address_state
        WHERE g.lei IS NOT NULL
          AND s.name_normalized != ''
          AND s.state IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk x WHERE x.cik = s.cik
          )
        ORDER BY s.cik
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  SEC->GLEIF name+state match: {count:,} ({elapsed:.1f}s)")
    return count


def step_3d_990_sec(conn):
    """3D: Match 990 filers to SEC via EIN."""
    print("\n--- Step 3D: 990 EIN -> SEC CIK ---")
    cur = conn.cursor()
    start = time.time()

    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (ein, cik, source, match_method, match_confidence, canonical_name, state)
        SELECT DISTINCT ON (n.ein)
            REPLACE(n.ein, '-', ''),
            s.cik,
            'N990_SEC',
            'EIN_EXACT',
            'HIGH',
            n.business_name,
            n.state
        FROM national_990_filers n
        JOIN sec_companies s ON REPLACE(n.ein, '-', '') = s.ein
        WHERE n.ein IS NOT NULL AND n.ein != ''
          AND s.ein IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk x
              WHERE x.ein = REPLACE(n.ein, '-', '') AND x.cik = s.cik
          )
        ORDER BY n.ein, s.is_public DESC
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  990->SEC via EIN: {count:,} ({elapsed:.1f}s)")
    return count


def step_3e_f7_sec(conn):
    """3E: Match F7 employers to SEC via name+state (F7 has no EIN)."""
    print("\n--- Step 3E: F7 -> SEC (name+state) ---")
    cur = conn.cursor()
    start = time.time()

    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (ein, cik, f7_employer_id, source, match_method, match_confidence, canonical_name, state)
        SELECT DISTINCT ON (f.employer_id)
            s.ein,
            s.cik,
            f.employer_id,
            'F7_SEC',
            'NAME_STATE',
            'MEDIUM',
            f.employer_name,
            f.state
        FROM f7_employers_deduped f
        JOIN sec_companies s ON f.employer_name_aggressive = s.name_normalized
            AND f.state = s.state
        WHERE f.employer_name_aggressive != ''
          AND f.state IS NOT NULL
          AND s.name_normalized != ''
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk x WHERE x.f7_employer_id = f.employer_id
          )
        ORDER BY f.employer_id, s.is_public DESC, s.cik
    """)
    count = cur.rowcount
    conn.commit()
    elapsed = time.time() - start
    print(f"  F7->SEC name+state: {count:,} ({elapsed:.1f}s)")

    # Also link F7 to crosswalk entries via Mergent bridge
    cur.execute("""
        UPDATE corporate_identifier_crosswalk x
        SET f7_employer_id = m.matched_f7_employer_id
        FROM mergent_employers m
        WHERE x.mergent_duns = m.duns
          AND x.f7_employer_id IS NULL
          AND m.matched_f7_employer_id IS NOT NULL
    """)
    bridge = cur.rowcount
    conn.commit()
    print(f"  Linked F7 via Mergent bridge: {bridge:,}")

    return count + bridge


def create_indexes(conn):
    """Create indexes on crosswalk table."""
    print("\n  Creating crosswalk indexes...")
    cur = conn.cursor()
    cur.execute("CREATE INDEX idx_xwalk_ein ON corporate_identifier_crosswalk(ein) WHERE ein IS NOT NULL")
    cur.execute("CREATE INDEX idx_xwalk_cik ON corporate_identifier_crosswalk(cik) WHERE cik IS NOT NULL")
    cur.execute("CREATE INDEX idx_xwalk_lei ON corporate_identifier_crosswalk(lei) WHERE lei IS NOT NULL")
    cur.execute("CREATE INDEX idx_xwalk_duns ON corporate_identifier_crosswalk(duns) WHERE duns IS NOT NULL")
    cur.execute("CREATE INDEX idx_xwalk_f7 ON corporate_identifier_crosswalk(f7_employer_id) WHERE f7_employer_id IS NOT NULL")
    cur.execute("CREATE INDEX idx_xwalk_mergent ON corporate_identifier_crosswalk(mergent_duns) WHERE mergent_duns IS NOT NULL")
    conn.commit()
    print("  Done")


def print_stats(conn):
    """Print crosswalk summary."""
    print("\n=== Crosswalk Summary ===")
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    print(f"Total crosswalk entries: {cur.fetchone()[0]:,}")

    cur.execute("SELECT source, match_method, match_confidence, COUNT(*) FROM corporate_identifier_crosswalk GROUP BY source, match_method, match_confidence ORDER BY COUNT(*) DESC")
    print("\nBy source/method:")
    for row in cur.fetchall():
        print(f"  {row[0]} / {row[1]} ({row[2]}): {row[3]:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE ein IS NOT NULL")
    print(f"\nWith EIN: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE cik IS NOT NULL")
    print(f"With CIK: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE lei IS NOT NULL")
    print(f"With LEI: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE duns IS NOT NULL")
    print(f"With DUNS: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE f7_employer_id IS NOT NULL")
    print(f"With F7 ID: {cur.fetchone()[0]:,}")

    # Companies with all 3 identifiers
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE ein IS NOT NULL AND cik IS NOT NULL AND lei IS NOT NULL")
    print(f"With EIN+CIK+LEI: {cur.fetchone()[0]:,}")


def main():
    step_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith('--step'):
            if '=' in arg:
                step_filter = arg.split('=')[1].upper()
            else:
                idx = sys.argv.index(arg)
                if idx + 1 < len(sys.argv):
                    step_filter = sys.argv[idx + 1].upper()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        if not step_filter:
            create_table(conn)

        steps = {
            '3A': step_3a_mergent_sec,
            '3B': step_3b_sec_gleif_lei,
            '3C': step_3c_sec_gleif_ein,
            '3D': step_3d_990_sec,
            '3E': step_3e_f7_sec,
        }

        for step_name, step_fn in steps.items():
            if step_filter and step_filter != step_name:
                continue
            step_fn(conn)

        if not step_filter:
            create_indexes(conn)

        print_stats(conn)
        print("\n=== Phase 3 Complete ===")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
