"""
Load CorpWatch API CSV data into PostgreSQL.

CorpWatch provides parsed SEC EDGAR data (2003-2025) covering 1.43M companies,
3.5M parent-child corporate relationships, and 4.8M raw subsidiary disclosures.

Data source: https://corpwatch.org/  (tab-delimited CSVs, ~8.5GB total)

Usage:
    py scripts/etl/load_corpwatch.py                          # Full load (schema + all CSVs)
    py scripts/etl/load_corpwatch.py --step schema            # Create tables only
    py scripts/etl/load_corpwatch.py --step companies         # Load company_info.csv
    py scripts/etl/load_corpwatch.py --step locations         # Load company_locations.csv
    py scripts/etl/load_corpwatch.py --step names             # Load company_names.csv
    py scripts/etl/load_corpwatch.py --step relations         # Load company_relations.csv
    py scripts/etl/load_corpwatch.py --step subsidiaries      # Load relationships.csv
    py scripts/etl/load_corpwatch.py --step filings           # Load company_filings.csv
    py scripts/etl/load_corpwatch.py --step indexes           # Create indexes (after bulk load)
    py scripts/etl/load_corpwatch.py --step seed_master       # Seed into master_employers
    py scripts/etl/load_corpwatch.py --step crosswalk         # Extend crosswalk + CIK bridge
    py scripts/etl/load_corpwatch.py --step hierarchy         # Enrich corporate_hierarchy
    py scripts/etl/load_corpwatch.py --step verify            # Run verification checks
    py scripts/etl/load_corpwatch.py --data-dir /path/to/csvs # Override CSV directory

Tables created:
    corpwatch_companies      ~361K rows (most_recent=1 from company_info.csv)
    corpwatch_locations      ~400K rows (most_recent=1, US from company_locations.csv)
    corpwatch_relationships  ~3.5M rows (all years from company_relations.csv)
    corpwatch_subsidiaries   ~2M rows (US-related from relationships.csv)
    corpwatch_names          ~500K rows (most_recent=1 from company_names.csv)
    corpwatch_filing_index   ~208K rows (company_filings.csv)
    corpwatch_f7_matches     legacy match table for adapter
"""
import argparse
import csv
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
)

# Default data directory
DEFAULT_DATA_DIR = Path(r"C:\Users\jakew\Downloads\corpwatch_api_tables_csv\corpwatch_api_tables_csv")

BATCH_SIZE = 10_000
US_COUNTRY_CODES = {"US", "USA", "us", "usa", ""}


def _null(val):
    """Convert 'NULL' string to None."""
    if val is None or val == "NULL" or val == "":
        return None
    return val


def _int(val):
    """Safe int conversion."""
    val = _null(val)
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _float(val):
    """Safe float conversion."""
    val = _null(val)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalize(name):
    """Normalize company name, returning (standard, aggressive) or (None, None)."""
    if not name:
        return None, None
    try:
        std = normalize_name_standard(name)
        agg = normalize_name_aggressive(name)
        return std or None, agg or None
    except Exception:
        return None, None


# ============================================================================
# Schema DDL
# ============================================================================

def create_schema(conn):
    """Create all CorpWatch tables."""
    cur = conn.cursor()

    print("=== Creating CorpWatch schema ===")

    # --- corpwatch_companies ---
    cur.execute("DROP TABLE IF EXISTS corpwatch_f7_matches CASCADE")
    cur.execute("DROP TABLE IF EXISTS corpwatch_names CASCADE")
    cur.execute("DROP TABLE IF EXISTS corpwatch_locations CASCADE")
    cur.execute("DROP TABLE IF EXISTS corpwatch_subsidiaries CASCADE")
    cur.execute("DROP TABLE IF EXISTS corpwatch_relationships CASCADE")
    cur.execute("DROP TABLE IF EXISTS corpwatch_filing_index CASCADE")
    cur.execute("DROP TABLE IF EXISTS corpwatch_companies CASCADE")
    conn.commit()

    cur.execute("""
        CREATE TABLE corpwatch_companies (
            cw_id           INTEGER PRIMARY KEY,
            cik             INTEGER,
            ein             VARCHAR(20),
            company_name    TEXT,
            name_normalized TEXT,
            name_aggressive TEXT,
            sic_code        VARCHAR(10),
            industry_name   TEXT,
            sic_sector      VARCHAR(10),
            sector_name     TEXT,
            num_parents     INTEGER DEFAULT 0,
            num_children    INTEGER DEFAULT 0,
            top_parent_id   INTEGER,
            source_type     TEXT,
            -- Location (backfilled from corpwatch_locations)
            state           VARCHAR(10),
            city            TEXT,
            zip             VARCHAR(20),
            country_code    VARCHAR(5),
            is_us           BOOLEAN DEFAULT FALSE,
            -- Temporal
            min_year        INTEGER,
            max_year        INTEGER
        )
    """)
    print("  Created corpwatch_companies")

    # --- corpwatch_locations ---
    cur.execute("""
        CREATE TABLE corpwatch_locations (
            location_id     INTEGER PRIMARY KEY,
            cw_id           INTEGER NOT NULL,
            type            TEXT,
            street_1        TEXT,
            street_2        TEXT,
            city            TEXT,
            state           VARCHAR(10),
            postal_code     VARCHAR(20),
            country_code    VARCHAR(5),
            subdiv_code     VARCHAR(10),
            min_year        INTEGER,
            max_year        INTEGER
        )
    """)
    print("  Created corpwatch_locations")

    # --- corpwatch_relationships (parent-child from company_relations.csv) ---
    cur.execute("""
        CREATE TABLE corpwatch_relationships (
            relation_id     INTEGER PRIMARY KEY,
            source_cw_id    INTEGER NOT NULL,
            target_cw_id    INTEGER NOT NULL,
            relation_type   TEXT,
            relation_origin TEXT,
            origin_id       INTEGER,
            year            INTEGER
        )
    """)
    print("  Created corpwatch_relationships")

    # --- corpwatch_subsidiaries (raw Exhibit 21 from relationships.csv) ---
    cur.execute("""
        CREATE TABLE corpwatch_subsidiaries (
            relationship_id INTEGER PRIMARY KEY,
            parent_cw_id    INTEGER,
            cw_id           INTEGER,
            filer_cik       INTEGER,
            company_name    TEXT,
            clean_company   TEXT,
            name_normalized TEXT,
            country_code    VARCHAR(5),
            subdiv_code     VARCHAR(10),
            hierarchy       INTEGER,
            percent         TEXT,
            parse_method    TEXT,
            year            INTEGER,
            quarter         INTEGER
        )
    """)
    print("  Created corpwatch_subsidiaries")

    # --- corpwatch_names ---
    cur.execute("""
        CREATE TABLE corpwatch_names (
            name_id         INTEGER PRIMARY KEY,
            cw_id           INTEGER NOT NULL,
            company_name    TEXT,
            name_normalized TEXT,
            date            TEXT,
            source          TEXT,
            min_year        INTEGER,
            max_year        INTEGER
        )
    """)
    print("  Created corpwatch_names")

    # --- corpwatch_filing_index ---
    cur.execute("""
        CREATE TABLE corpwatch_filing_index (
            filing_id       INTEGER PRIMARY KEY,
            cik             INTEGER,
            year            INTEGER,
            quarter         INTEGER,
            period_of_report TEXT,
            filing_date     TEXT,
            form_10k_url    TEXT,
            sec_21_url      TEXT
        )
    """)
    print("  Created corpwatch_filing_index")

    # --- corpwatch_f7_matches (legacy match table for adapter) ---
    cur.execute("""
        CREATE TABLE corpwatch_f7_matches (
            cw_id           INTEGER PRIMARY KEY,
            f7_employer_id  TEXT NOT NULL,
            match_method    TEXT,
            match_confidence NUMERIC(5,3),
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)
    print("  Created corpwatch_f7_matches")

    conn.commit()
    print("  Schema creation complete.\n")


# ============================================================================
# CSV Loaders
# ============================================================================

def load_companies(conn, data_dir):
    """Load company_info.csv -> corpwatch_companies (most_recent=1 only)."""
    print("=== Loading corpwatch_companies from company_info.csv ===")
    filepath = data_dir / "company_info.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return

    cur = conn.cursor()
    t0 = time.time()
    loaded = 0
    skipped = 0
    batch = []

    sql = """
        INSERT INTO corpwatch_companies
            (cw_id, cik, ein, company_name, name_normalized, name_aggressive,
             sic_code, industry_name, sic_sector, sector_name,
             num_parents, num_children, top_parent_id, source_type,
             min_year, max_year)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (cw_id) DO UPDATE SET
            cik = EXCLUDED.cik,
            ein = EXCLUDED.ein,
            company_name = EXCLUDED.company_name,
            name_normalized = EXCLUDED.name_normalized,
            name_aggressive = EXCLUDED.name_aggressive,
            sic_code = EXCLUDED.sic_code,
            industry_name = EXCLUDED.industry_name,
            num_parents = EXCLUDED.num_parents,
            num_children = EXCLUDED.num_children,
            top_parent_id = EXCLUDED.top_parent_id,
            min_year = EXCLUDED.min_year,
            max_year = EXCLUDED.max_year
    """

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            # Filter: most_recent=1 only
            if row.get("most_recent") != "1":
                skipped += 1
                continue

            cw_id = _int(row.get("cw_id"))
            if cw_id is None:
                skipped += 1
                continue

            name = _null(row.get("company_name"))
            std, agg = _normalize(name)

            # EIN: CorpWatch calls it irs_number
            ein_raw = _null(row.get("irs_number"))
            # Clean EIN: strip non-digits, keep if 9 digits
            ein = None
            if ein_raw:
                digits = "".join(c for c in ein_raw if c.isdigit())
                if len(digits) == 9:
                    ein = digits

            batch.append((
                cw_id,
                _int(row.get("cik")),
                ein,
                name,
                std,
                agg,
                _null(row.get("sic_code")),
                _null(row.get("industry_name")),
                _null(row.get("sic_sector")),
                _null(row.get("sector_name")),
                _int(row.get("num_parents")) or 0,
                _int(row.get("num_children")) or 0,
                _int(row.get("top_parent_id")),
                _null(row.get("source_type")),
                _int(row.get("min_year")),
                _int(row.get("max_year")),
            ))

            if len(batch) >= BATCH_SIZE:
                from psycopg2.extras import execute_batch
                execute_batch(cur, sql, batch, page_size=1000)
                loaded += len(batch)
                batch = []
                if loaded % 50_000 == 0:
                    conn.commit()
                    elapsed = time.time() - t0
                    print(f"  {loaded:>10,} loaded ({elapsed:.1f}s)")

    if batch:
        from psycopg2.extras import execute_batch
        execute_batch(cur, sql, batch, page_size=1000)
        loaded += len(batch)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {loaded:,} loaded, {skipped:,} skipped in {elapsed:.1f}s")

    # Stats
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies")
    print(f"  Table count: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies WHERE ein IS NOT NULL")
    print(f"  With EIN: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(DISTINCT cik) FROM corpwatch_companies WHERE cik IS NOT NULL")
    print(f"  Distinct CIKs: {cur.fetchone()[0]:,}")


def load_locations(conn, data_dir):
    """Load company_locations.csv -> corpwatch_locations (most_recent=1 only).
    Then backfill state/city/zip onto corpwatch_companies from best location.
    """
    print("\n=== Loading corpwatch_locations from company_locations.csv ===")
    filepath = data_dir / "company_locations.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return

    cur = conn.cursor()
    t0 = time.time()
    loaded = 0
    skipped = 0
    batch = []

    sql = """
        INSERT INTO corpwatch_locations
            (location_id, cw_id, type, street_1, street_2, city, state,
             postal_code, country_code, subdiv_code, min_year, max_year)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (location_id) DO NOTHING
    """

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("most_recent") != "1":
                skipped += 1
                continue

            loc_id = _int(row.get("location_id"))
            if loc_id is None:
                skipped += 1
                continue

            batch.append((
                loc_id,
                _int(row.get("cw_id")),
                _null(row.get("type")),
                _null(row.get("street_1")),
                _null(row.get("street_2")),
                _null(row.get("city")),
                _null(row.get("state")),
                _null(row.get("postal_code")),
                _null(row.get("country_code")),
                _null(row.get("subdiv_code")),
                _int(row.get("min_year")),
                _int(row.get("max_year")),
            ))

            if len(batch) >= BATCH_SIZE:
                from psycopg2.extras import execute_batch
                execute_batch(cur, sql, batch, page_size=1000)
                loaded += len(batch)
                batch = []
                if loaded % 100_000 == 0:
                    conn.commit()
                    elapsed = time.time() - t0
                    print(f"  {loaded:>10,} loaded ({elapsed:.1f}s)")

    if batch:
        from psycopg2.extras import execute_batch
        execute_batch(cur, sql, batch, page_size=1000)
        loaded += len(batch)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {loaded:,} loaded, {skipped:,} skipped in {elapsed:.1f}s")

    # Backfill location onto companies (prefer business address > mailing)
    print("\n  Backfilling state/city/zip onto corpwatch_companies...")
    cur.execute("""
        UPDATE corpwatch_companies c SET
            state = loc.state,
            city = loc.city,
            zip = loc.postal_code,
            country_code = loc.country_code,
            is_us = (loc.country_code IN ('US', 'USA') OR loc.subdiv_code LIKE 'US-%%')
        FROM (
            SELECT DISTINCT ON (cw_id)
                cw_id, state, city, postal_code, country_code, subdiv_code
            FROM corpwatch_locations
            WHERE state IS NOT NULL
            ORDER BY cw_id,
                     CASE WHEN type = 'business' THEN 0
                          WHEN type = 'mailing' THEN 1
                          ELSE 2 END,
                     max_year DESC NULLS LAST
        ) loc
        WHERE c.cw_id = loc.cw_id
    """)
    backfilled = cur.rowcount
    conn.commit()
    print(f"  Backfilled location for {backfilled:,} companies")

    # Also mark is_us for companies with US subdiv_code in locations but no direct country match
    cur.execute("""
        UPDATE corpwatch_companies c SET is_us = TRUE
        WHERE is_us = FALSE
          AND EXISTS (
              SELECT 1 FROM corpwatch_locations l
              WHERE l.cw_id = c.cw_id AND l.subdiv_code LIKE 'US-%%'
          )
    """)
    extra_us = cur.rowcount
    conn.commit()
    if extra_us > 0:
        print(f"  Additional US flags via subdiv_code: {extra_us:,}")

    cur.execute("SELECT COUNT(*) FROM corpwatch_companies WHERE is_us")
    print(f"  US companies: {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies WHERE state IS NOT NULL")
    print(f"  With state: {cur.fetchone()[0]:,}")


def load_names(conn, data_dir):
    """Load company_names.csv -> corpwatch_names (most_recent=1 only)."""
    print("\n=== Loading corpwatch_names from company_names.csv ===")
    filepath = data_dir / "company_names.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return

    cur = conn.cursor()
    t0 = time.time()
    loaded = 0
    skipped = 0
    batch = []

    sql = """
        INSERT INTO corpwatch_names
            (name_id, cw_id, company_name, name_normalized, date, source,
             min_year, max_year)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (name_id) DO NOTHING
    """

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("most_recent") != "1":
                skipped += 1
                continue

            name_id = _int(row.get("name_id"))
            if name_id is None:
                skipped += 1
                continue

            name = _null(row.get("company_name"))
            std, _ = _normalize(name)

            batch.append((
                name_id,
                _int(row.get("cw_id")),
                name,
                std,
                _null(row.get("date")),
                _null(row.get("source")),
                _int(row.get("min_year")),
                _int(row.get("max_year")),
            ))

            if len(batch) >= BATCH_SIZE:
                from psycopg2.extras import execute_batch
                execute_batch(cur, sql, batch, page_size=1000)
                loaded += len(batch)
                batch = []
                if loaded % 100_000 == 0:
                    conn.commit()
                    elapsed = time.time() - t0
                    print(f"  {loaded:>10,} loaded ({elapsed:.1f}s)")

    if batch:
        from psycopg2.extras import execute_batch
        execute_batch(cur, sql, batch, page_size=1000)
        loaded += len(batch)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {loaded:,} loaded, {skipped:,} skipped in {elapsed:.1f}s")


def load_relations(conn, data_dir):
    """Load company_relations.csv -> corpwatch_relationships using COPY for speed."""
    print("\n=== Loading corpwatch_relationships from company_relations.csv ===")
    filepath = data_dir / "company_relations.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return

    cur = conn.cursor()
    t0 = time.time()
    loaded = 0
    buf = io.StringIO()
    buf_rows = 0

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rel_id = _int(row.get("relation_id"))
            if rel_id is None:
                continue

            # Write tab-delimited line for COPY
            vals = [
                str(rel_id),
                str(_int(row.get("source_cw_id")) or "\\N"),
                str(_int(row.get("target_cw_id")) or "\\N"),
                (_null(row.get("relation_type")) or "\\N").replace("\t", " ").replace("\n", " "),
                (_null(row.get("relation_origin")) or "\\N").replace("\t", " ").replace("\n", " "),
                str(_int(row.get("origin_id")) or "\\N"),
                str(_int(row.get("year")) or "\\N"),
            ]
            buf.write("\t".join(vals) + "\n")
            buf_rows += 1

            if buf_rows >= 100_000:
                buf.seek(0)
                cur.copy_from(buf, "corpwatch_relationships",
                              columns=("relation_id", "source_cw_id", "target_cw_id",
                                       "relation_type", "relation_origin", "origin_id", "year"))
                loaded += buf_rows
                buf = io.StringIO()
                buf_rows = 0
                conn.commit()
                elapsed = time.time() - t0
                print(f"  {loaded:>10,} loaded ({elapsed:.1f}s)")

    if buf_rows > 0:
        buf.seek(0)
        cur.copy_from(buf, "corpwatch_relationships",
                      columns=("relation_id", "source_cw_id", "target_cw_id",
                               "relation_type", "relation_origin", "origin_id", "year"))
        loaded += buf_rows

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {loaded:,} loaded in {elapsed:.1f}s")


def load_subsidiaries(conn, data_dir):
    """Load relationships.csv -> corpwatch_subsidiaries.

    Pre-loads US cw_ids into a set for O(1) filtering.
    Skips rows with ignore_record=1.
    """
    print("\n=== Loading corpwatch_subsidiaries from relationships.csv ===")
    filepath = data_dir / "relationships.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return

    cur = conn.cursor()

    # Pre-load US company cw_ids for filtering
    print("  Loading US cw_id set for filtering...")
    cur.execute("SELECT cw_id FROM corpwatch_companies WHERE is_us = TRUE")
    us_cw_ids = {r[0] for r in cur.fetchall()}
    print(f"  {len(us_cw_ids):,} US companies loaded for filter")

    # Also include all cw_ids that are in companies table (for parent linkage)
    cur.execute("SELECT cw_id FROM corpwatch_companies")
    all_cw_ids = {r[0] for r in cur.fetchall()}

    t0 = time.time()
    loaded = 0
    skipped = 0
    batch = []

    sql = """
        INSERT INTO corpwatch_subsidiaries
            (relationship_id, parent_cw_id, cw_id, filer_cik, company_name,
             clean_company, name_normalized, country_code, subdiv_code,
             hierarchy, percent, parse_method, year, quarter)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (relationship_id) DO NOTHING
    """

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            # Skip ignored records
            if row.get("ignore_record") == "1":
                skipped += 1
                continue

            rel_id = _int(row.get("relationship_id"))
            if rel_id is None:
                skipped += 1
                continue

            parent_cw = _int(row.get("parent_cw_id"))
            child_cw = _int(row.get("cw_id"))

            # Keep if parent OR child is a US company
            if parent_cw not in us_cw_ids and child_cw not in us_cw_ids:
                # Also check if parent is in all_cw_ids (could be non-US parent of US sub)
                # But we want US-related: at least one side US
                cc = _null(row.get("country_code"))
                sc = _null(row.get("subdiv_code"))
                is_us_sub = (cc in ("US", "USA") or (sc and sc.startswith("US-")))
                if not is_us_sub and parent_cw not in us_cw_ids:
                    skipped += 1
                    continue

            name = _null(row.get("company_name"))
            clean = _null(row.get("clean_company"))
            std, _ = _normalize(clean or name)

            batch.append((
                rel_id,
                parent_cw,
                child_cw,
                _int(row.get("filer_cik")),
                name,
                clean,
                std,
                _null(row.get("country_code")),
                _null(row.get("subdiv_code")),
                _int(row.get("hierarchy")),
                _null(row.get("percent")),
                _null(row.get("parse_method")),
                _int(row.get("year")),
                _int(row.get("quarter")),
            ))

            if len(batch) >= BATCH_SIZE:
                from psycopg2.extras import execute_batch
                execute_batch(cur, sql, batch, page_size=1000)
                loaded += len(batch)
                batch = []
                if loaded % 100_000 == 0:
                    conn.commit()
                    elapsed = time.time() - t0
                    print(f"  {loaded:>10,} loaded, {skipped:,} skipped ({elapsed:.1f}s)")

    if batch:
        from psycopg2.extras import execute_batch
        execute_batch(cur, sql, batch, page_size=1000)
        loaded += len(batch)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {loaded:,} loaded, {skipped:,} skipped in {elapsed:.1f}s")


def load_filings(conn, data_dir):
    """Load company_filings.csv -> corpwatch_filing_index."""
    print("\n=== Loading corpwatch_filing_index from company_filings.csv ===")
    filepath = data_dir / "company_filings.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return

    cur = conn.cursor()
    t0 = time.time()
    loaded = 0
    batch = []

    sql = """
        INSERT INTO corpwatch_filing_index
            (filing_id, cik, year, quarter, period_of_report, filing_date,
             form_10k_url, sec_21_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (filing_id) DO NOTHING
    """

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            fid = _int(row.get("filing_id"))
            if fid is None:
                continue

            batch.append((
                fid,
                _int(row.get("cik")),
                _int(row.get("year")),
                _int(row.get("quarter")),
                _null(row.get("period_of_report")),
                _null(row.get("filing_date")),
                _null(row.get("form_10k_url")),
                _null(row.get("sec_21_url")),
            ))

            if len(batch) >= BATCH_SIZE:
                from psycopg2.extras import execute_batch
                execute_batch(cur, sql, batch, page_size=1000)
                loaded += len(batch)
                batch = []
                if loaded % 50_000 == 0:
                    conn.commit()

    if batch:
        from psycopg2.extras import execute_batch
        execute_batch(cur, sql, batch, page_size=1000)
        loaded += len(batch)

    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done: {loaded:,} loaded in {elapsed:.1f}s")


# ============================================================================
# Indexes (create AFTER bulk load)
# ============================================================================

def create_indexes(conn):
    """Create all indexes on CorpWatch tables."""
    print("\n=== Creating indexes ===")
    cur = conn.cursor()
    conn.autocommit = True  # CREATE INDEX can't run in transaction

    indexes = [
        # corpwatch_companies
        ("idx_cwc_cik", "CREATE INDEX IF NOT EXISTS idx_cwc_cik ON corpwatch_companies(cik) WHERE cik IS NOT NULL"),
        ("idx_cwc_ein", "CREATE INDEX IF NOT EXISTS idx_cwc_ein ON corpwatch_companies(ein) WHERE ein IS NOT NULL"),
        ("idx_cwc_name_norm", "CREATE INDEX IF NOT EXISTS idx_cwc_name_norm ON corpwatch_companies(name_normalized) WHERE name_normalized IS NOT NULL"),
        ("idx_cwc_name_agg", "CREATE INDEX IF NOT EXISTS idx_cwc_name_agg ON corpwatch_companies(name_aggressive) WHERE name_aggressive IS NOT NULL"),
        ("idx_cwc_state", "CREATE INDEX IF NOT EXISTS idx_cwc_state ON corpwatch_companies(state) WHERE state IS NOT NULL"),
        ("idx_cwc_top_parent", "CREATE INDEX IF NOT EXISTS idx_cwc_top_parent ON corpwatch_companies(top_parent_id) WHERE top_parent_id IS NOT NULL"),
        ("idx_cwc_is_us", "CREATE INDEX IF NOT EXISTS idx_cwc_is_us ON corpwatch_companies(cw_id) WHERE is_us = TRUE"),
        ("idx_cwc_trgm", "CREATE INDEX IF NOT EXISTS idx_cwc_trgm ON corpwatch_companies USING gin(name_normalized gin_trgm_ops) WHERE name_normalized IS NOT NULL"),

        # corpwatch_locations
        ("idx_cwl_cwid", "CREATE INDEX IF NOT EXISTS idx_cwl_cwid ON corpwatch_locations(cw_id)"),

        # corpwatch_relationships
        ("idx_cwr_source", "CREATE INDEX IF NOT EXISTS idx_cwr_source ON corpwatch_relationships(source_cw_id)"),
        ("idx_cwr_target", "CREATE INDEX IF NOT EXISTS idx_cwr_target ON corpwatch_relationships(target_cw_id)"),
        ("idx_cwr_year", "CREATE INDEX IF NOT EXISTS idx_cwr_year ON corpwatch_relationships(year)"),

        # corpwatch_subsidiaries
        ("idx_cws_parent", "CREATE INDEX IF NOT EXISTS idx_cws_parent ON corpwatch_subsidiaries(parent_cw_id) WHERE parent_cw_id IS NOT NULL"),
        ("idx_cws_cwid", "CREATE INDEX IF NOT EXISTS idx_cws_cwid ON corpwatch_subsidiaries(cw_id) WHERE cw_id IS NOT NULL"),
        ("idx_cws_filer_cik", "CREATE INDEX IF NOT EXISTS idx_cws_filer_cik ON corpwatch_subsidiaries(filer_cik) WHERE filer_cik IS NOT NULL"),

        # corpwatch_names
        ("idx_cwn_cwid", "CREATE INDEX IF NOT EXISTS idx_cwn_cwid ON corpwatch_names(cw_id)"),
        ("idx_cwn_name_norm", "CREATE INDEX IF NOT EXISTS idx_cwn_name_norm ON corpwatch_names(name_normalized) WHERE name_normalized IS NOT NULL"),

        # corpwatch_filing_index
        ("idx_cwfi_cik", "CREATE INDEX IF NOT EXISTS idx_cwfi_cik ON corpwatch_filing_index(cik)"),

        # corpwatch_f7_matches
        ("idx_cwfm_f7", "CREATE INDEX IF NOT EXISTS idx_cwfm_f7 ON corpwatch_f7_matches(f7_employer_id)"),
    ]

    for name, sql in indexes:
        t0 = time.time()
        try:
            cur.execute(sql)
            elapsed = time.time() - t0
            print(f"  {name}: {elapsed:.1f}s")
        except Exception as e:
            print(f"  {name}: ERROR - {e}")

    conn.autocommit = False
    print("  Indexing complete.")


# ============================================================================
# Crosswalk Extension + CIK Bridge
# ============================================================================

def extend_crosswalk(conn):
    """Add corpwatch_id column to crosswalk + CIK bridge matching."""
    print("\n=== Extending corporate_identifier_crosswalk ===")
    cur = conn.cursor()

    # Add corpwatch_id column if not exists
    cur.execute("""
        ALTER TABLE corporate_identifier_crosswalk
        ADD COLUMN IF NOT EXISTS corpwatch_id INTEGER
    """)
    conn.commit()
    print("  Added corpwatch_id column (if not already present)")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cic_corpwatch
        ON corporate_identifier_crosswalk(corpwatch_id)
        WHERE corpwatch_id IS NOT NULL
    """)
    conn.commit()
    print("  Created index on corpwatch_id")

    # CIK Bridge: CorpWatch CIK -> existing crosswalk sec_cik -> f7_employer_id
    print("\n  CIK Bridge matching...")
    cur.execute("""
        UPDATE corporate_identifier_crosswalk cw
        SET corpwatch_id = cwc.cw_id
        FROM corpwatch_companies cwc
        WHERE cwc.cik = cw.sec_cik
          AND cw.sec_cik IS NOT NULL
          AND cwc.cik IS NOT NULL
          AND cw.corpwatch_id IS NULL
    """)
    cik_bridge_count = cur.rowcount
    conn.commit()
    print(f"  CIK bridge: linked {cik_bridge_count:,} crosswalk rows to CorpWatch")

    # EIN Bridge: CorpWatch EIN -> crosswalk EIN
    print("\n  EIN Bridge matching...")
    cur.execute("""
        UPDATE corporate_identifier_crosswalk cw
        SET corpwatch_id = cwc.cw_id
        FROM corpwatch_companies cwc
        WHERE cwc.ein = cw.ein
          AND cw.ein IS NOT NULL
          AND cwc.ein IS NOT NULL
          AND cw.corpwatch_id IS NULL
    """)
    ein_bridge_count = cur.rowcount
    conn.commit()
    print(f"  EIN bridge: linked {ein_bridge_count:,} additional crosswalk rows")

    # Write CIK bridge matches to unified_match_log
    print("\n  Writing CIK bridge matches to unified_match_log...")
    import uuid
    run_id = str(uuid.uuid4())[:12]
    cur.execute("""
        INSERT INTO unified_match_log
            (run_id, source_system, source_id, target_system, target_id,
             match_method, match_tier, confidence_band, confidence_score,
             evidence, status)
        SELECT DISTINCT ON (cwc.cw_id, cw.f7_employer_id)
            %s,
            'corpwatch',
            cwc.cw_id::text,
            'f7',
            cw.f7_employer_id,
            'CIK_BRIDGE',
            1,
            'HIGH',
            0.90,
            jsonb_build_object(
                'match_method', 'CIK_BRIDGE',
                'cik', cwc.cik,
                'corpwatch_name', cwc.company_name,
                'crosswalk_name', cw.canonical_name
            ),
            'active'
        FROM corporate_identifier_crosswalk cw
        JOIN corpwatch_companies cwc ON cwc.cw_id = cw.corpwatch_id
        WHERE cw.f7_employer_id IS NOT NULL
          AND cw.corpwatch_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_match_log uml
              WHERE uml.source_system = 'corpwatch'
                AND uml.source_id = cwc.cw_id::text
                AND uml.status = 'active'
          )
        ON CONFLICT (run_id, source_system, source_id, target_id) DO NOTHING
    """, (run_id,))
    uml_count = cur.rowcount
    conn.commit()
    print(f"  Wrote {uml_count:,} matches to unified_match_log")

    # Also write to legacy table
    print("  Writing CIK bridge matches to corpwatch_f7_matches...")
    cur.execute("""
        INSERT INTO corpwatch_f7_matches (cw_id, f7_employer_id, match_method, match_confidence)
        SELECT
            cw.corpwatch_id,
            cw.f7_employer_id,
            'CIK_BRIDGE',
            0.90
        FROM corporate_identifier_crosswalk cw
        WHERE cw.f7_employer_id IS NOT NULL
          AND cw.corpwatch_id IS NOT NULL
        ON CONFLICT (cw_id) DO NOTHING
    """)
    legacy_count = cur.rowcount
    conn.commit()
    print(f"  Wrote {legacy_count:,} to corpwatch_f7_matches")

    # Summary
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE corpwatch_id IS NOT NULL")
    total_linked = cur.fetchone()[0]
    print(f"\n  Total crosswalk rows with corpwatch_id: {total_linked:,}")


# ============================================================================
# Corporate Hierarchy Enrichment
# ============================================================================

def enrich_hierarchy(conn):
    """Insert CorpWatch parent-child edges into corporate_hierarchy.

    Uses master_employer_source_ids to match CorpWatch companies to master
    employers (673K matches), replacing the old approach that only used
    corpwatch_f7_matches (3K matches). When a CorpWatch company also maps
    to an F7 employer through the master bridge, child_f7_employer_id is
    populated.
    """
    print("\n=== Enriching corporate_hierarchy with CorpWatch data ===")
    cur = conn.cursor()

    # Clean out any old CORPWATCH rows (re-runnable)
    cur.execute("DELETE FROM corporate_hierarchy WHERE source = 'CORPWATCH'")
    deleted = cur.rowcount
    if deleted:
        print(f"  Removed {deleted:,} old CORPWATCH rows")
    conn.commit()

    # Insert edges from corpwatch_relationships where at least one side
    # has a master_employer link (via master_employer_source_ids).
    # Get F7 employer_id through the master bridge when available.
    cur.execute("""
        INSERT INTO corporate_hierarchy
            (parent_name, parent_cik, child_name, child_f7_employer_id,
             child_duns, relationship_type, is_direct, source, confidence,
             created_at)
        SELECT
            pc.company_name AS parent_name,
            pc.cik AS parent_cik,
            cc.company_name AS child_name,
            -- Get F7 employer_id for child via master bridge
            cf7.source_id AS child_f7_employer_id,
            -- Get DUNS for child via Mergent if available
            NULL AS child_duns,
            'subsidiary' AS relationship_type,
            TRUE AS is_direct,
            'CORPWATCH' AS source,
            CASE
                WHEN cf7.source_id IS NOT NULL THEN 'HIGH'
                WHEN cm.master_id IS NOT NULL THEN 'MEDIUM'
                ELSE 'LOW'
            END AS confidence,
            NOW() AS created_at
        FROM (
            -- Deduplicate: latest year per edge
            SELECT DISTINCT ON (source_cw_id, target_cw_id)
                source_cw_id, target_cw_id
            FROM corpwatch_relationships
            ORDER BY source_cw_id, target_cw_id, year DESC
        ) edges
        -- Parent and child company details
        JOIN corpwatch_companies pc ON pc.cw_id = edges.source_cw_id
        JOIN corpwatch_companies cc ON cc.cw_id = edges.target_cw_id
        -- Match to master_employers via source_ids
        LEFT JOIN master_employer_source_ids pm
            ON pm.source_system = 'corpwatch'
            AND pm.source_id = edges.source_cw_id::text
        LEFT JOIN master_employer_source_ids cm
            ON cm.source_system = 'corpwatch'
            AND cm.source_id = edges.target_cw_id::text
        -- Get F7 employer_id for child through master bridge
        LEFT JOIN master_employer_source_ids cf7
            ON cf7.master_id = cm.master_id
            AND cf7.source_system = 'f7'
        -- At least one side must have a master_employer link
        WHERE pm.master_id IS NOT NULL OR cm.master_id IS NOT NULL
    """)
    new_edges = cur.rowcount
    conn.commit()
    print(f"  Added {new_edges:,} new hierarchy edges from CorpWatch")

    # Stats
    cur.execute("""
        SELECT confidence, COUNT(*)
        FROM corporate_hierarchy WHERE source = 'CORPWATCH'
        GROUP BY 1 ORDER BY 2 DESC
    """)
    print("  By confidence:")
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]:,}")

    cur.execute("""
        SELECT COUNT(*) FROM corporate_hierarchy
        WHERE source = 'CORPWATCH' AND child_f7_employer_id IS NOT NULL
    """)
    f7_linked = cur.fetchone()[0]
    print(f"  With F7 employer link: {f7_linked:,}")

    cur.execute("SELECT COUNT(*) FROM corporate_hierarchy")
    total = cur.fetchone()[0]
    print(f"  Total hierarchy edges (all sources): {total:,}")


# ============================================================================
# Master Employers Seeding
# ============================================================================

def _run_sql(cur, sql):
    """Execute SQL and return rowcount."""
    cur.execute(sql)
    return cur.rowcount if cur.rowcount is not None else 0


def seed_master(conn):
    """Seed CorpWatch companies into master_employers.

    CorpWatch companies are SEC-filing companies — potential organizing targets.
    They belong in master_employers alongside SAM, Mergent, and BMF.

    6 stages following the pattern from seed_master_from_sources.py:
      1) Link via existing F7 matches
      2) Match by EIN to existing masters
      3) Match by canonical_name + state
      4) Insert unmatched as new master rows
      5) Backfill source IDs for new rows
      6) Enrich existing masters (is_public, EIN)
    """
    print("\n=== Seeding CorpWatch into master_employers ===")
    cur = conn.cursor()
    stats = {}

    # Ensure 'corpwatch' is in the check constraints for both tables
    for tbl, col, con_name, allowed in [
        ('master_employer_source_ids', 'source_system', 'chk_master_source_system',
         "('f7','sam','mergent','osha','bmf','nlrb','sec','gleif','990','manual','corpwatch')"),
        ('master_employers', 'source_origin', 'chk_master_source_origin',
         "('f7','sam','mergent','osha','bmf','nlrb','sec','manual','corpwatch')"),
    ]:
        cur.execute("""
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = %s::regclass AND conname = %s
        """, (tbl, con_name))
        row = cur.fetchone()
        if row and 'corpwatch' not in row[0]:
            print(f"  Adding 'corpwatch' to {tbl}.{con_name}...")
            cur.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT {con_name}")
            cur.execute(f"ALTER TABLE {tbl} ADD CONSTRAINT {con_name} CHECK ({col} IN {allowed})")
            conn.commit()
            print(f"  Constraint {con_name} updated.")

    # 1) Link CorpWatch companies that already matched to F7 (via CIK/EIN bridge
    #    or deterministic matching) to the same master_id.
    stats["source_ids_from_f7_matches"] = _run_sql(cur, """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            f7sid.master_id,
            'corpwatch',
            cfm.cw_id::text,
            1.0,
            NOW()
        FROM corpwatch_f7_matches cfm
        JOIN master_employer_source_ids f7sid
          ON f7sid.source_system = 'f7'
         AND f7sid.source_id = cfm.f7_employer_id
        WHERE NOT EXISTS (
            SELECT 1 FROM master_employer_source_ids sid
            WHERE sid.source_system = 'corpwatch'
              AND sid.source_id = cfm.cw_id::text
        )
    """)
    conn.commit()
    print(f"  Stage 1 (F7 bridge): {stats['source_ids_from_f7_matches']:,} linked")

    # 2) Match by EIN to existing masters.
    stats["source_ids_ein"] = _run_sql(cur, """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'corpwatch',
            cwc.cw_id::text,
            0.95,
            NOW()
        FROM corpwatch_companies cwc
        JOIN master_employers m ON m.ein = cwc.ein
        WHERE cwc.ein IS NOT NULL
          AND cwc.is_us = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'corpwatch'
                AND sid.source_id = cwc.cw_id::text
          )
    """)
    conn.commit()
    print(f"  Stage 2 (EIN match): {stats['source_ids_ein']:,} linked")

    # 3) Match by canonical_name + state.
    stats["source_ids_name_state"] = _run_sql(cur, """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'corpwatch',
            cwc.cw_id::text,
            0.90,
            NOW()
        FROM corpwatch_companies cwc
        JOIN master_employers m
          ON m.canonical_name = COALESCE(NULLIF(cwc.name_aggressive, ''), cwc.name_normalized)
         AND COALESCE(m.state, '') = COALESCE(cwc.state, '')
        WHERE cwc.is_us = TRUE
          AND cwc.name_normalized IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'corpwatch'
                AND sid.source_id = cwc.cw_id::text
          )
    """)
    conn.commit()
    print(f"  Stage 3 (name+state): {stats['source_ids_name_state']:,} linked")

    # 4) Insert truly unmatched US CorpWatch companies as new master rows.
    stats["new_master_rows"] = _run_sql(cur, """
        INSERT INTO master_employers (
            canonical_name, display_name, city, state, zip, naics,
            employee_count, employee_count_source, ein,
            is_union, is_public, is_federal_contractor, is_nonprofit,
            source_origin, data_quality_score
        )
        SELECT
            COALESCE(NULLIF(cwc.name_normalized, ''), 'unknown_corpwatch_' || cwc.cw_id),
            cwc.company_name,
            cwc.city,
            cwc.state,
            cwc.zip,
            NULL,
            NULL,
            NULL,
            cwc.ein,
            FALSE,
            TRUE,
            FALSE,
            FALSE,
            'corpwatch',
            50.00
        FROM corpwatch_companies cwc
        WHERE cwc.is_us = TRUE
          AND cwc.company_name IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'corpwatch'
                AND sid.source_id = cwc.cw_id::text
          )
          AND NOT EXISTS (
              SELECT 1 FROM master_employers m
              WHERE m.canonical_name = COALESCE(NULLIF(cwc.name_normalized, ''),
                                                'unknown_corpwatch_' || cwc.cw_id)
                AND COALESCE(m.state, '') = COALESCE(cwc.state, '')
                AND COALESCE(m.city, '') = COALESCE(cwc.city, '')
                AND COALESCE(m.zip, '') = COALESCE(cwc.zip, '')
          )
    """)
    conn.commit()
    print(f"  Stage 4 (new rows): {stats['new_master_rows']:,} inserted")

    # 5) Backfill source IDs for new corpwatch-origin rows.
    stats["source_ids_for_new_rows"] = _run_sql(cur, """
        INSERT INTO master_employer_source_ids
            (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT
            m.master_id,
            'corpwatch',
            cwc.cw_id::text,
            0.70,
            NOW()
        FROM corpwatch_companies cwc
        JOIN master_employers m
          ON m.source_origin = 'corpwatch'
         AND m.display_name = cwc.company_name
         AND COALESCE(m.state, '') = COALESCE(cwc.state, '')
         AND COALESCE(m.city, '') = COALESCE(cwc.city, '')
        WHERE cwc.is_us = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.source_system = 'corpwatch'
                AND sid.source_id = cwc.cw_id::text
          )
    """)
    conn.commit()
    print(f"  Stage 5 (backfill source IDs): {stats['source_ids_for_new_rows']:,} linked")

    # 6) Enrich: mark matched masters as public + backfill EIN.
    stats["is_public_updates"] = _run_sql(cur, """
        UPDATE master_employers m
        SET is_public = TRUE,
            updated_at = NOW()
        WHERE NOT m.is_public
          AND EXISTS (
              SELECT 1 FROM master_employer_source_ids sid
              WHERE sid.master_id = m.master_id
                AND sid.source_system = 'corpwatch'
          )
    """)
    conn.commit()
    print(f"  Stage 6a (is_public): {stats['is_public_updates']:,} updated")

    stats["ein_backfill"] = _run_sql(cur, """
        UPDATE master_employers m
        SET ein = cwc.ein,
            updated_at = NOW()
        FROM master_employer_source_ids sid
        JOIN corpwatch_companies cwc ON cwc.cw_id::text = sid.source_id
        WHERE sid.master_id = m.master_id
          AND sid.source_system = 'corpwatch'
          AND m.ein IS NULL
          AND cwc.ein IS NOT NULL
    """)
    conn.commit()
    print(f"  Stage 6b (EIN backfill): {stats['ein_backfill']:,} updated")

    # Summary
    total_linked = stats["source_ids_from_f7_matches"] + stats["source_ids_ein"] \
        + stats["source_ids_name_state"] + stats["source_ids_for_new_rows"]
    print("\n  Summary:")
    print(f"    Total source IDs linked: {total_linked:,}")
    print(f"    New master rows: {stats['new_master_rows']:,}")
    print(f"    Public flag updates: {stats['is_public_updates']:,}")
    print(f"    EIN backfills: {stats['ein_backfill']:,}")

    return stats


# ============================================================================
# Verification
# ============================================================================

def verify(conn):
    """Run post-load verification checks."""
    print("\n=== Verification ===")
    cur = conn.cursor()

    tables = [
        "corpwatch_companies",
        "corpwatch_locations",
        "corpwatch_relationships",
        "corpwatch_subsidiaries",
        "corpwatch_names",
        "corpwatch_filing_index",
        "corpwatch_f7_matches",
    ]

    print("\n  Row counts:")
    for tbl in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            cnt = cur.fetchone()[0]
            print(f"    {tbl:35s}: {cnt:>10,}")
        except Exception as e:
            print(f"    {tbl:35s}: ERROR - {e}")
            conn.rollback()

    # EIN coverage
    print("\n  EIN coverage:")
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies WHERE ein IS NOT NULL")
    ein_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies")
    total = cur.fetchone()[0]
    pct = 100 * ein_cnt / total if total else 0
    print(f"    {ein_cnt:,} / {total:,} ({pct:.1f}%)")

    # US companies
    print("\n  US companies:")
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies WHERE is_us = TRUE")
    us_cnt = cur.fetchone()[0]
    print(f"    {us_cnt:,} US companies")

    # State distribution (top 10)
    print("\n  Top 10 states:")
    cur.execute("""
        SELECT state, COUNT(*) AS cnt
        FROM corpwatch_companies
        WHERE state IS NOT NULL AND is_us = TRUE
        GROUP BY state ORDER BY cnt DESC LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"    {row[0]:5s}: {row[1]:>8,}")

    # FK integrity: locations
    print("\n  FK integrity (locations -> companies):")
    cur.execute("""
        SELECT COUNT(*) FROM corpwatch_locations l
        WHERE NOT EXISTS (SELECT 1 FROM corpwatch_companies c WHERE c.cw_id = l.cw_id)
    """)
    orphans = cur.fetchone()[0]
    print(f"    Orphan locations (no matching company): {orphans:,}")

    # Match stats
    print("\n  Matching stats:")
    cur.execute("SELECT COUNT(*) FROM corpwatch_f7_matches")
    match_cnt = cur.fetchone()[0]
    print(f"    corpwatch_f7_matches: {match_cnt:,}")

    cur.execute("""
        SELECT match_method, COUNT(*) AS cnt
        FROM unified_match_log
        WHERE source_system = 'corpwatch' AND status = 'active'
        GROUP BY match_method ORDER BY cnt DESC
    """)
    rows = cur.fetchall()
    if rows:
        print("    unified_match_log (corpwatch, active):")
        for row in rows:
            print(f"      {row[0]:30s}: {row[1]:>8,}")

    # Crosswalk coverage
    print("\n  Crosswalk coverage:")
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk WHERE corpwatch_id IS NOT NULL")
    cw_linked = cur.fetchone()[0]
    print(f"    Crosswalk rows with corpwatch_id: {cw_linked:,}")

    # Hierarchy
    print("\n  Hierarchy:")
    cur.execute("SELECT source, COUNT(*) FROM corporate_hierarchy GROUP BY source ORDER BY COUNT(*) DESC")
    for row in cur.fetchall():
        print(f"    {row[0]:15s}: {row[1]:>8,}")

    # Master employers
    print("\n  Master employers seeding:")
    try:
        cur.execute("SELECT COUNT(*) FROM master_employer_source_ids WHERE source_system = 'corpwatch'")
        master_linked = cur.fetchone()[0]
        print(f"    master_employer_source_ids (corpwatch): {master_linked:,}")
    except Exception:
        print("    master_employer_source_ids: not yet seeded")
        conn.rollback()
    try:
        cur.execute("SELECT COUNT(*) FROM master_employers WHERE source_origin = 'corpwatch'")
        master_new = cur.fetchone()[0]
        print(f"    master_employers (source_origin=corpwatch): {master_new:,}")
    except Exception:
        print("    master_employers (corpwatch): not yet seeded")
        conn.rollback()

    # Spot checks
    print("\n  Spot checks (known companies):")
    spot_checks = ["WALMART", "CITIGROUP", "COMCAST", "UNITED PARCEL SERVICE"]
    for name in spot_checks:
        cur.execute("""
            SELECT cw_id, company_name, cik, ein, state
            FROM corpwatch_companies
            WHERE name_normalized LIKE %s
            LIMIT 3
        """, (f"%{name.lower()}%",))
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"    {r[1]}: cw_id={r[0]}, cik={r[2]}, ein={r[3]}, state={r[4]}")
        else:
            print(f"    {name}: NOT FOUND")

    print("\n  Verification complete.")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Load CorpWatch API data into PostgreSQL")
    parser.add_argument("--step", choices=[
        "schema", "companies", "locations", "names", "relations",
        "subsidiaries", "filings", "indexes", "seed_master",
        "crosswalk", "hierarchy", "verify", "all"
    ], default="all", help="Which step to run (default: all)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Path to CorpWatch CSV directory")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    if not data_dir.exists():
        print(f"ERROR: Data directory not found: {data_dir}")
        sys.exit(1)

    conn = get_connection()
    conn.autocommit = False

    t_total = time.time()

    try:
        if args.step in ("all", "schema"):
            create_schema(conn)

        if args.step in ("all", "companies"):
            load_companies(conn, data_dir)

        if args.step in ("all", "locations"):
            load_locations(conn, data_dir)

        if args.step in ("all", "names"):
            load_names(conn, data_dir)

        if args.step in ("all", "relations"):
            load_relations(conn, data_dir)

        if args.step in ("all", "subsidiaries"):
            load_subsidiaries(conn, data_dir)

        if args.step in ("all", "filings"):
            load_filings(conn, data_dir)

        if args.step in ("all", "indexes"):
            create_indexes(conn)

        if args.step in ("all", "seed_master"):
            seed_master(conn)

        if args.step in ("all", "crosswalk"):
            extend_crosswalk(conn)

        if args.step in ("all", "hierarchy"):
            enrich_hierarchy(conn)

        if args.step in ("all", "verify"):
            verify(conn)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

    elapsed = time.time() - t_total
    print(f"\n=== Total time: {elapsed:.1f}s ===")


if __name__ == "__main__":
    main()
