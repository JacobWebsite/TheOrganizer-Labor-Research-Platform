"""
Build corporate_identifier_crosswalk table.
Links SEC, GLEIF, Mergent, CorpWatch, and F7 employers via multiple matching tiers:

Tier 1:  EIN exact match (SEC <-> Mergent)
Tier 2:  LEI exact match (SEC <-> GLEIF)
Tier 2b: EIN backfill (F7 via 990/CorpWatch EINs)
Tier 3:  Normalized name + state (all sources)

Creates:
  - corporate_identifier_crosswalk: unified ID mapping
  - corporate_hierarchy: parent->child from GLEIF ownership + Mergent parent_duns
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

conn = get_connection()
conn.autocommit = False
cur = conn.cursor()


def create_crosswalk_table():
    print('=== Creating crosswalk table ===')
    cur.execute('DROP TABLE IF EXISTS corporate_identifier_crosswalk CASCADE')
    cur.execute("""
        CREATE TABLE corporate_identifier_crosswalk (
            id SERIAL PRIMARY KEY,
            -- Canonical group ID (assigned after all matching)
            corporate_family_id INTEGER,
            -- Source identifiers (NULL if no match to that source)
            sec_id INTEGER,
            sec_cik INTEGER,
            gleif_id INTEGER,
            gleif_lei VARCHAR(20),
            mergent_duns VARCHAR(20),
            corpwatch_id INTEGER,
            f7_employer_id TEXT,
            -- Best name/metadata
            canonical_name TEXT,
            ein VARCHAR(20),
            ticker VARCHAR(20),
            is_public BOOLEAN DEFAULT FALSE,
            state VARCHAR(10),
            -- Federal contracting (populated by _match_usaspending.py)
            is_federal_contractor BOOLEAN DEFAULT FALSE,
            federal_obligations NUMERIC,
            federal_contract_count INTEGER,
            -- Match metadata
            match_tier TEXT,
            match_confidence TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    print('  Table created')


def tier1_ein_sec_mergent():
    """Tier 1: EIN exact match between SEC and Mergent."""
    print('\n=== Tier 1: SEC <-> Mergent via EIN ===')
    start = time.time()
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (sec_id, sec_cik, mergent_duns, canonical_name, ein, ticker, is_public, state,
             match_tier, match_confidence)
        SELECT DISTINCT ON (s.ein)
            s.id, s.cik, m.duns,
            COALESCE(s.company_name, m.company_name),
            s.ein,
            s.ticker,
            COALESCE(s.is_public, FALSE),
            COALESCE(m.state, s.state),
            'EIN_EXACT', 'HIGH'
        FROM sec_companies s
        JOIN mergent_employers m ON m.ein = s.ein
        WHERE s.ein IS NOT NULL AND m.ein IS NOT NULL
        ORDER BY s.ein, s.is_public DESC NULLS LAST, s.id
    """)
    count = cur.rowcount
    conn.commit()
    print(f'  Matched {count:,} via EIN in {time.time()-start:.1f}s')
    return count


def tier2_lei_sec_gleif():
    """Tier 2: LEI exact match between SEC and GLEIF."""
    print('\n=== Tier 2: SEC <-> GLEIF via LEI ===')
    start = time.time()
    # Only add new crosswalk rows for GLEIF entities not already matched
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (sec_id, sec_cik, gleif_id, gleif_lei, canonical_name, ein, ticker, is_public, state,
             match_tier, match_confidence)
        SELECT DISTINCT ON (s.lei)
            s.id, s.cik, g.id, g.lei,
            COALESCE(s.company_name, g.entity_name),
            s.ein, s.ticker,
            COALESCE(s.is_public, FALSE),
            COALESCE(s.state, g.address_state),
            'LEI_EXACT', 'HIGH'
        FROM sec_companies s
        JOIN gleif_us_entities g ON g.lei = s.lei
        WHERE s.lei IS NOT NULL AND g.lei IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.sec_id = s.id
          )
        ORDER BY s.lei, s.id
    """)
    new_rows = cur.rowcount
    conn.commit()

    # Also update existing crosswalk rows that matched SEC via EIN to add GLEIF
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET gleif_id = g.id, gleif_lei = g.lei
        FROM sec_companies s
        JOIN gleif_us_entities g ON g.lei = s.lei
        WHERE c.sec_id = s.id AND c.gleif_id IS NULL
          AND s.lei IS NOT NULL AND g.lei IS NOT NULL
    """)
    updated = cur.rowcount
    conn.commit()
    print(f'  New rows: {new_rows:,}, updated existing: {updated:,} in {time.time()-start:.1f}s')
    return new_rows


def tier2b_ein_f7_backfill():
    """Tier 2b: Bridge F7 employers to crosswalk via EINs from 990/CorpWatch matches."""
    print('\n=== Tier 2b: EIN backfill (F7 via 990/CorpWatch) ===')
    start = time.time()

    # Build CTE of F7 employers with known EINs (pick largest unit per EIN)
    f7_eins_cte = """
        WITH f7_eins AS (
            SELECT DISTINCT m.ein, m.f7_employer_id, f.latest_unit_size
            FROM national_990_f7_matches m
            JOIN f7_employers_deduped f ON f.employer_id = m.f7_employer_id
            WHERE m.ein IS NOT NULL AND LENGTH(m.ein) >= 8
            UNION
            SELECT DISTINCT cwc.ein, cfm.f7_employer_id, f.latest_unit_size
            FROM corpwatch_f7_matches cfm
            JOIN corpwatch_companies cwc ON cwc.cw_id = cfm.cw_id
            JOIN f7_employers_deduped f ON f.employer_id = cfm.f7_employer_id
            WHERE cwc.ein IS NOT NULL AND LENGTH(cwc.ein) >= 8
        ),
        best_f7_per_ein AS (
            SELECT DISTINCT ON (ein) ein, f7_employer_id
            FROM f7_eins ORDER BY ein, latest_unit_size DESC NULLS LAST
        )
    """

    # Step 1: UPDATE existing crosswalk rows that have an EIN but no F7 link
    cur.execute(f"""
        {f7_eins_cte}
        UPDATE corporate_identifier_crosswalk c
        SET f7_employer_id = b.f7_employer_id,
            match_tier = c.match_tier || '+EIN_F7_BACKFILL'
        FROM best_f7_per_ein b
        WHERE c.ein = b.ein AND c.f7_employer_id IS NULL
    """)
    updated = cur.rowcount
    conn.commit()
    print(f'  Step 1 - Updated existing rows with F7 link: {updated:,}')

    # Step 2: INSERT new rows for F7 employers with EINs not already in crosswalk
    cur.execute(f"""
        {f7_eins_cte}
        INSERT INTO corporate_identifier_crosswalk
            (f7_employer_id, ein, canonical_name, state,
             match_tier, match_confidence)
        SELECT DISTINCT ON (b.f7_employer_id)
            b.f7_employer_id, b.ein,
            f.employer_name, f.state,
            'EIN_F7_BACKFILL', 'MEDIUM'
        FROM best_f7_per_ein b
        JOIN f7_employers_deduped f ON f.employer_id = b.f7_employer_id
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.f7_employer_id = b.f7_employer_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM corporate_identifier_crosswalk c
            WHERE c.ein = b.ein
        )
        ORDER BY b.f7_employer_id, b.ein
    """)
    inserted = cur.rowcount
    conn.commit()
    print(f'  Step 2 - Inserted new F7 rows: {inserted:,}')

    # Step 3: Cross-link newly inserted rows to SEC/Mergent where EINs match
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET sec_id = s.id, sec_cik = s.cik,
            ticker = COALESCE(c.ticker, s.ticker),
            is_public = COALESCE(s.is_public, c.is_public),
            canonical_name = COALESCE(s.company_name, c.canonical_name)
        FROM sec_companies s
        WHERE c.ein = s.ein AND c.sec_id IS NULL
          AND c.match_tier = 'EIN_F7_BACKFILL'
          AND s.ein IS NOT NULL
    """)
    sec_linked = cur.rowcount
    conn.commit()

    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET mergent_duns = m.duns,
            canonical_name = COALESCE(c.canonical_name, m.company_name)
        FROM mergent_employers m
        WHERE c.ein = m.ein AND c.mergent_duns IS NULL
          AND c.match_tier = 'EIN_F7_BACKFILL'
          AND m.ein IS NOT NULL
    """)
    mergent_linked = cur.rowcount
    conn.commit()

    # Also link to CorpWatch
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET corpwatch_id = cwc.cw_id
        FROM corpwatch_companies cwc
        WHERE c.ein = cwc.ein AND c.corpwatch_id IS NULL
          AND c.match_tier = 'EIN_F7_BACKFILL'
          AND cwc.ein IS NOT NULL
    """)
    cw_linked = cur.rowcount
    conn.commit()

    elapsed = time.time() - start
    print(f'  Step 3 - Cross-linked: SEC={sec_linked:,}, Mergent={mergent_linked:,}, CorpWatch={cw_linked:,}')
    print(f'  Total: {updated + inserted:,} F7 links added in {elapsed:.1f}s')
    return updated + inserted


def tier3_name_state():
    """Tier 3: Normalized name + state matching across all sources."""
    print('\n=== Tier 3: Name + State matching ===')

    # 3a: SEC <-> F7 (name + state)
    print('  3a: SEC <-> F7...')
    start = time.time()
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (sec_id, sec_cik, f7_employer_id, canonical_name, ein, ticker, is_public, state,
             match_tier, match_confidence)
        SELECT DISTINCT ON (f.employer_id)
            s.id, s.cik, f.employer_id,
            s.company_name,
            s.ein, s.ticker,
            COALESCE(s.is_public, FALSE),
            f.state,
            'NAME_STATE', 'MEDIUM'
        FROM f7_employers_deduped f
        JOIN sec_companies s ON s.name_normalized = f.employer_name_aggressive AND s.state = f.state
        WHERE f.employer_name_aggressive IS NOT NULL
          AND LENGTH(f.employer_name_aggressive) > 3
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
          )
        ORDER BY f.employer_id, s.is_public DESC NULLS LAST, s.id
    """)
    sec_f7 = cur.rowcount
    conn.commit()
    print(f'    SEC<->F7: {sec_f7:,} in {time.time()-start:.1f}s')

    # 3b: GLEIF <-> F7 (name + state)
    print('  3b: GLEIF <-> F7...')
    start = time.time()
    # Update existing crosswalk rows that have F7 but no GLEIF
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET gleif_id = g.id, gleif_lei = g.lei
        FROM f7_employers_deduped f
        JOIN gleif_us_entities g ON g.name_normalized = f.employer_name_aggressive
            AND g.address_state = f.state
        WHERE c.f7_employer_id = f.employer_id AND c.gleif_id IS NULL
          AND f.employer_name_aggressive IS NOT NULL
          AND LENGTH(f.employer_name_aggressive) > 3
    """)
    gleif_f7_updated = cur.rowcount
    conn.commit()

    # New rows for F7<->GLEIF not yet in crosswalk
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (gleif_id, gleif_lei, f7_employer_id, canonical_name, state,
             match_tier, match_confidence)
        SELECT DISTINCT ON (f.employer_id)
            g.id, g.lei, f.employer_id,
            g.entity_name,
            f.state,
            'NAME_STATE', 'MEDIUM'
        FROM f7_employers_deduped f
        JOIN gleif_us_entities g ON g.name_normalized = f.employer_name_aggressive
            AND g.address_state = f.state
        WHERE f.employer_name_aggressive IS NOT NULL
          AND LENGTH(f.employer_name_aggressive) > 3
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.f7_employer_id = f.employer_id
          )
        ORDER BY f.employer_id, g.id
    """)
    gleif_f7_new = cur.rowcount
    conn.commit()
    print(f'    GLEIF<->F7: {gleif_f7_new:,} new, {gleif_f7_updated:,} updated in {time.time()-start:.1f}s')

    # 3c: GLEIF <-> Mergent (name + state)
    print('  3c: GLEIF <-> Mergent...')
    start = time.time()
    # Update existing rows that have Mergent but no GLEIF
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET gleif_id = g.id, gleif_lei = g.lei
        FROM mergent_employers m
        JOIN gleif_us_entities g ON g.name_normalized = m.company_name_normalized
            AND g.address_state = m.state
        WHERE c.mergent_duns = m.duns AND c.gleif_id IS NULL
          AND m.company_name_normalized IS NOT NULL
          AND LENGTH(m.company_name_normalized) > 3
    """)
    gleif_m_updated = cur.rowcount
    conn.commit()

    # New rows for Mergent<->GLEIF not yet in crosswalk
    cur.execute("""
        INSERT INTO corporate_identifier_crosswalk
            (gleif_id, gleif_lei, mergent_duns, canonical_name, ein, state,
             match_tier, match_confidence)
        SELECT DISTINCT ON (m.duns)
            g.id, g.lei, m.duns,
            COALESCE(g.entity_name, m.company_name),
            m.ein,
            m.state,
            'NAME_STATE', 'MEDIUM'
        FROM mergent_employers m
        JOIN gleif_us_entities g ON g.name_normalized = m.company_name_normalized
            AND g.address_state = m.state
        WHERE m.company_name_normalized IS NOT NULL
          AND LENGTH(m.company_name_normalized) > 3
          AND NOT EXISTS (
              SELECT 1 FROM corporate_identifier_crosswalk c WHERE c.mergent_duns = m.duns
          )
        ORDER BY m.duns, g.id
    """)
    gleif_m_new = cur.rowcount
    conn.commit()
    print(f'    GLEIF<->Mergent: {gleif_m_new:,} new, {gleif_m_updated:,} updated in {time.time()-start:.1f}s')

    # 3d: SEC <-> Mergent by name+state (ones missed by EIN)
    print('  3d: SEC <-> Mergent by name+state (missed by EIN)...')
    start = time.time()
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET sec_id = s.id, sec_cik = s.cik,
            ticker = COALESCE(c.ticker, s.ticker),
            is_public = COALESCE(s.is_public, c.is_public),
            ein = COALESCE(c.ein, s.ein)
        FROM mergent_employers m
        JOIN sec_companies s ON s.name_normalized = m.company_name_normalized AND s.state = m.state
        WHERE c.mergent_duns = m.duns AND c.sec_id IS NULL
          AND m.company_name_normalized IS NOT NULL
          AND LENGTH(m.company_name_normalized) > 3
    """)
    sec_m_updated = cur.rowcount
    conn.commit()
    print(f'    SEC<->Mergent name+state: {sec_m_updated:,} updated in {time.time()-start:.1f}s')

    # 3e: Mergent <-> F7 by name+state (backfill)
    print('  3e: Mergent <-> F7 backfill...')
    start = time.time()
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET mergent_duns = m.duns,
            ein = COALESCE(c.ein, m.ein)
        FROM f7_employers_deduped f
        JOIN mergent_employers m ON m.company_name_normalized = f.employer_name_aggressive
            AND m.state = f.state
        WHERE c.f7_employer_id = f.employer_id AND c.mergent_duns IS NULL
          AND f.employer_name_aggressive IS NOT NULL
          AND LENGTH(f.employer_name_aggressive) > 3
    """)
    m_f7_updated = cur.rowcount
    conn.commit()
    print(f'    Mergent<->F7 backfill: {m_f7_updated:,} updated in {time.time()-start:.1f}s')

    return sec_f7 + gleif_f7_new + gleif_m_new


def assign_family_ids():
    """Assign corporate_family_id using connected components."""
    print('\n=== Assigning corporate_family_id ===')
    start = time.time()
    # Simple approach: use row ID as family ID initially
    cur.execute('UPDATE corporate_identifier_crosswalk SET corporate_family_id = id')
    conn.commit()
    print(f'  Assigned in {time.time()-start:.1f}s')


def create_indexes():
    print('\n=== Creating indexes ===')
    start = time.time()
    indexes = [
        'CREATE INDEX idx_cic_sec ON corporate_identifier_crosswalk(sec_id) WHERE sec_id IS NOT NULL',
        'CREATE INDEX idx_cic_cik ON corporate_identifier_crosswalk(sec_cik) WHERE sec_cik IS NOT NULL',
        'CREATE INDEX idx_cic_gleif ON corporate_identifier_crosswalk(gleif_id) WHERE gleif_id IS NOT NULL',
        'CREATE INDEX idx_cic_lei ON corporate_identifier_crosswalk(gleif_lei) WHERE gleif_lei IS NOT NULL',
        'CREATE INDEX idx_cic_mergent ON corporate_identifier_crosswalk(mergent_duns) WHERE mergent_duns IS NOT NULL',
        'CREATE INDEX idx_cic_corpwatch ON corporate_identifier_crosswalk(corpwatch_id) WHERE corpwatch_id IS NOT NULL',
        'CREATE INDEX idx_cic_f7 ON corporate_identifier_crosswalk(f7_employer_id) WHERE f7_employer_id IS NOT NULL',
        'CREATE INDEX idx_cic_ein ON corporate_identifier_crosswalk(ein) WHERE ein IS NOT NULL',
        'CREATE INDEX idx_cic_family ON corporate_identifier_crosswalk(corporate_family_id)',
        'CREATE INDEX idx_cic_name ON corporate_identifier_crosswalk(canonical_name)',
    ]
    for idx in indexes:
        cur.execute(idx)
    conn.commit()
    print(f'  {len(indexes)} indexes in {time.time()-start:.1f}s')


def build_corporate_hierarchy():
    """Build hierarchy from GLEIF ownership links + Mergent parent_duns."""
    print('\n=== Building corporate_hierarchy ===')
    cur.execute('DROP TABLE IF EXISTS corporate_hierarchy CASCADE')
    cur.execute("""
        CREATE TABLE corporate_hierarchy (
            id SERIAL PRIMARY KEY,
            parent_name TEXT,
            parent_duns VARCHAR(20),
            parent_lei VARCHAR(20),
            parent_cik INTEGER,
            child_name TEXT,
            child_duns VARCHAR(20),
            child_f7_employer_id TEXT,
            relationship_type TEXT,
            is_direct BOOLEAN DEFAULT TRUE,
            source TEXT,
            confidence TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    # From GLEIF ownership (both-US links)
    print('  GLEIF ownership links...')
    start = time.time()
    cur.execute("""
        INSERT INTO corporate_hierarchy
            (parent_name, parent_lei, child_name, child_f7_employer_id, child_duns,
             relationship_type, is_direct, source, confidence)
        SELECT
            p.entity_name,
            p.lei,
            c.entity_name,
            cw_child.f7_employer_id,
            cw_child.mergent_duns,
            COALESCE(ol.interest_level, 'unknown'),
            (ol.interest_level = 'direct'),
            'GLEIF',
            CASE WHEN ol.interest_level = 'direct' THEN 'HIGH'
                 WHEN ol.interest_level = 'indirect' THEN 'MEDIUM'
                 ELSE 'LOW' END
        FROM gleif_ownership_links ol
        JOIN gleif_us_entities p ON p.id = ol.parent_entity_id
        JOIN gleif_us_entities c ON c.id = ol.child_entity_id
        LEFT JOIN corporate_identifier_crosswalk cw_child ON cw_child.gleif_id = c.id
        WHERE ol.parent_entity_id IS NOT NULL AND ol.child_entity_id IS NOT NULL
    """)
    gleif_count = cur.rowcount
    conn.commit()
    print(f'    {gleif_count:,} GLEIF links in {time.time()-start:.1f}s')

    # From Mergent parent_duns
    print('  Mergent parent->child links...')
    start = time.time()
    cur.execute("""
        INSERT INTO corporate_hierarchy
            (parent_name, parent_duns, child_name, child_duns, child_f7_employer_id,
             relationship_type, is_direct, source, confidence)
        SELECT
            parent.company_name,
            parent.duns,
            child.company_name,
            child.duns,
            cw.f7_employer_id,
            'ownership',
            TRUE,
            'MERGENT',
            'HIGH'
        FROM mergent_employers child
        JOIN mergent_employers parent ON parent.duns = child.parent_duns
        LEFT JOIN corporate_identifier_crosswalk cw ON cw.mergent_duns = child.duns
        WHERE child.parent_duns IS NOT NULL
          AND child.duns != child.parent_duns
    """)
    mergent_count = cur.rowcount
    conn.commit()
    print(f'    {mergent_count:,} Mergent links in {time.time()-start:.1f}s')

    # From Mergent domestic_parent_duns (if different from parent_duns)
    cur.execute("""
        INSERT INTO corporate_hierarchy
            (parent_name, parent_duns, child_name, child_duns, child_f7_employer_id,
             relationship_type, is_direct, source, confidence)
        SELECT
            parent.company_name,
            parent.duns,
            child.company_name,
            child.duns,
            cw.f7_employer_id,
            'domestic_parent',
            FALSE,
            'MERGENT',
            'MEDIUM'
        FROM mergent_employers child
        JOIN mergent_employers parent ON parent.duns = child.domestic_parent_duns
        LEFT JOIN corporate_identifier_crosswalk cw ON cw.mergent_duns = child.duns
        WHERE child.domestic_parent_duns IS NOT NULL
          AND child.duns != child.domestic_parent_duns
          AND (child.parent_duns IS NULL OR child.domestic_parent_duns != child.parent_duns)
    """)
    dom_count = cur.rowcount
    conn.commit()
    print(f'    {dom_count:,} Mergent domestic parent links')

    # Indexes
    cur.execute('CREATE INDEX idx_ch_parent_duns ON corporate_hierarchy(parent_duns) WHERE parent_duns IS NOT NULL')
    cur.execute('CREATE INDEX idx_ch_child_duns ON corporate_hierarchy(child_duns) WHERE child_duns IS NOT NULL')
    cur.execute('CREATE INDEX idx_ch_child_f7 ON corporate_hierarchy(child_f7_employer_id) WHERE child_f7_employer_id IS NOT NULL')
    cur.execute('CREATE INDEX idx_ch_parent_lei ON corporate_hierarchy(parent_lei) WHERE parent_lei IS NOT NULL')
    cur.execute('CREATE INDEX idx_ch_source ON corporate_hierarchy(source)')
    conn.commit()

    print(f'\n  Total hierarchy links: {gleif_count + mergent_count + dom_count:,}')
    return gleif_count + mergent_count + dom_count


def print_summary():
    print('\n' + '='*60)
    print('CROSSWALK SUMMARY')
    print('='*60)

    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk')
    total = cur.fetchone()[0]
    print(f'Total crosswalk rows: {total:,}')

    cur.execute('SELECT match_tier, match_confidence, COUNT(*) FROM corporate_identifier_crosswalk GROUP BY 1,2 ORDER BY 3 DESC')
    print('\nBy match tier:')
    for row in cur.fetchall():
        print(f'  {row[0]} ({row[1]}): {row[2]:,}')

    # Coverage
    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE sec_id IS NOT NULL')
    print(f'\nWith SEC link: {cur.fetchone()[0]:,}')
    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE gleif_id IS NOT NULL')
    print(f'With GLEIF link: {cur.fetchone()[0]:,}')
    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE mergent_duns IS NOT NULL')
    print(f'With Mergent link: {cur.fetchone()[0]:,}')
    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE f7_employer_id IS NOT NULL')
    f7_count = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM f7_employers_deduped')
    f7_total = cur.fetchone()[0]
    print(f'With F7 link: {f7_count:,} ({100*f7_count/f7_total:.1f}% of {f7_total:,})')
    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE corpwatch_id IS NOT NULL')
    print(f'With CorpWatch link: {cur.fetchone()[0]:,}')
    cur.execute('SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE is_public = TRUE')
    print(f'Public companies: {cur.fetchone()[0]:,}')

    # Multi-source matches
    cur.execute("""
        SELECT COUNT(*) FROM corporate_identifier_crosswalk
        WHERE (CASE WHEN sec_id IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN gleif_id IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN mergent_duns IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN corpwatch_id IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN f7_employer_id IS NOT NULL THEN 1 ELSE 0 END) >= 3
    """)
    print(f'Linked to 3+ sources: {cur.fetchone()[0]:,}')

    cur.execute("""
        SELECT COUNT(*) FROM corporate_identifier_crosswalk
        WHERE sec_id IS NOT NULL AND gleif_id IS NOT NULL
          AND mergent_duns IS NOT NULL AND f7_employer_id IS NOT NULL
    """)
    print(f'Linked to all 4+ sources: {cur.fetchone()[0]:,}')

    # Hierarchy
    cur.execute('SELECT COUNT(*) FROM corporate_hierarchy')
    print(f'\nHierarchy links: {cur.fetchone()[0]:,}')
    cur.execute('SELECT source, COUNT(*) FROM corporate_hierarchy GROUP BY source ORDER BY 2 DESC')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]:,}')

    # Sample richly-linked records
    print('\nSample multi-source matches:')
    cur.execute("""
        SELECT canonical_name, ein, ticker, state, match_tier,
               sec_id IS NOT NULL as has_sec,
               gleif_id IS NOT NULL as has_gleif,
               mergent_duns IS NOT NULL as has_mergent,
               corpwatch_id IS NOT NULL as has_cw,
               f7_employer_id IS NOT NULL as has_f7
        FROM corporate_identifier_crosswalk
        WHERE (CASE WHEN sec_id IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN gleif_id IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN mergent_duns IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN corpwatch_id IS NOT NULL THEN 1 ELSE 0 END +
               CASE WHEN f7_employer_id IS NOT NULL THEN 1 ELSE 0 END) >= 3
        ORDER BY canonical_name
        LIMIT 10
    """)
    for row in cur.fetchall():
        sources = []
        if row[5]: sources.append('SEC')
        if row[6]: sources.append('GLEIF')
        if row[7]: sources.append('MRGNT')
        if row[8]: sources.append('CW')
        if row[9]: sources.append('F7')
        print(f'  {row[0]} | EIN={row[1]} ticker={row[2]} state={row[3]} | {"+".join(sources)}')


if __name__ == '__main__':
    overall_start = time.time()

    create_crosswalk_table()
    tier1_ein_sec_mergent()
    tier2_lei_sec_gleif()
    tier2b_ein_f7_backfill()
    tier3_name_state()
    assign_family_ids()
    create_indexes()
    build_corporate_hierarchy()
    print_summary()

    print(f'\nTotal time: {time.time()-overall_start:.1f}s')
    conn.close()
