# CorpWatch API Data Import -- Implementation Plan & Code

**Created:** 2026-02-23
**Status:** Ready for implementation
**Estimated time:** ~10-13 hours (dev + execution)

---

## Table of Contents

1. [Overview](#overview)
2. [What to Import vs Skip](#what-to-import-vs-skip)
3. [File 1: scripts/etl/load_corpwatch.py](#file-1-scriptsetlload_corpwatchpy) (CREATE)
4. [File 2: scripts/matching/adapters/corpwatch_adapter.py](#file-2-scriptsmatchingadapterscorpwatch_adapterpy) (CREATE)
5. [File 3: scripts/matching/run_deterministic.py](#file-3-scriptsmatchingrun_deterministicpy) (MODIFY)
6. [File 4: scripts/scoring/build_employer_data_sources.py](#file-4-scriptsscoringbuild_employer_data_sourcespy) (MODIFY)
7. [File 5: scripts/etl/build_crosswalk.py](#file-5-scriptsetlbuild_crosswalkpy) (MODIFY)
8. [Execution Runbook](#execution-runbook)
9. [Verification Queries](#verification-queries)

---

## Overview

CorpWatch provides parsed SEC EDGAR data (2003-2025): 1.43M companies, 3.5M parent-child relationships, 4.8M raw subsidiary disclosures from 10-K Exhibit 21 filings.

**CSV location:** `C:\Users\jakew\Downloads\corpwatch_api_tables_csv\corpwatch_api_tables_csv\` (~8.5GB, 19 tab-delimited CSVs)

**Why import:** (1) Corporate hierarchy data -- 8,180 corporate family trees and a 293K-company EIN<->CIK cross-reference. Massively expands our current `corporate_identifier_crosswalk` (3,313 employers) and `corporate_hierarchy` (GLEIF+Mergent only). (2) Seeds ~361K SEC-filing companies into `master_employers` as potential organizing targets (public, mostly non-union).

**CSV format notes:**
- Tab-delimited (NOT comma)
- NULL values represented as literal string `NULL`
- UTF-8 encoding (international subsidiary names)
- `most_recent` column = 0 or 1 for temporal filtering

---

## What to Import vs Skip

### IMPORT (~2.1GB raw -> ~1.5GB in DB)

| File | Raw Size | Rows | Filter | DB Rows | Table |
|------|----------|------|--------|---------|-------|
| `company_info.csv` | 642MB | 5.2M | `most_recent=1` | ~361K | `corpwatch_companies` |
| `company_locations.csv` | 334MB | 2.6M | `most_recent=1`, US | ~400K | `corpwatch_locations` |
| `company_relations.csv` | 176MB | 3.5M | All (temporal) | 3.5M | `corpwatch_relationships` |
| `relationships.csv` | 721MB | 4.8M | US-related parents | ~2M | `corpwatch_subsidiaries` |
| `company_names.csv` | 239MB | 2.4M | `most_recent=1`, US | ~500K | `corpwatch_names` |
| `company_filings.csv` | 31MB | 208K | All | 208K | `corpwatch_filing_index` |

### SKIP (~6.4GB) -- zero labor-research value

| File | Size | Why Skip |
|------|------|----------|
| `filers.csv` | 2.5GB | Redundant with `company_info.csv` + existing `sec_companies` |
| `filings.csv` | 3.0GB | Zero financial data. 39% Form 4, 0% extracted tables |
| `filings_lookup.csv` | 67MB | Companion to filings.csv |
| `cik_name_lookup.csv` | 72MB | Redundant with company_info |
| `companies.csv` | 87MB | Subset of company_info (fewer columns) |
| `cw_id_lookup.csv` | 192MB | Redundant master lookup |
| Reference tables | 85KB | Country/SIC tables -- not needed |

---

## File 1: scripts/etl/load_corpwatch.py (CREATE)

Main ETL script -- creates all tables and loads all 6 CSVs.

```python
"""
Load CorpWatch API data (parsed SEC EDGAR, 2003-2025).

Creates 6 tables from tab-delimited CSV exports:
  - corpwatch_companies      (company_info.csv, most_recent=1)
  - corpwatch_locations      (company_locations.csv, most_recent=1, US)
  - corpwatch_names          (company_names.csv, most_recent=1, US)
  - corpwatch_relationships  (company_relations.csv, all years)
  - corpwatch_subsidiaries   (relationships.csv, US-linked parents)
  - corpwatch_filing_index   (company_filings.csv, all)

Also:
  - Applies name normalization (standard + aggressive)
  - Creates pg_trgm indexes for fuzzy matching
  - Extends corporate_identifier_crosswalk with corpwatch_id
  - Runs CIK bridge matching
  - Inserts corporate hierarchy edges

Usage:
    py scripts/etl/load_corpwatch.py                    # Full run (all steps)
    py scripts/etl/load_corpwatch.py --step schema      # Create tables only
    py scripts/etl/load_corpwatch.py --step companies   # Load companies only
    py scripts/etl/load_corpwatch.py --step locations    # Load locations only
    py scripts/etl/load_corpwatch.py --step names        # Load names only
    py scripts/etl/load_corpwatch.py --step relations    # Load relationships only
    py scripts/etl/load_corpwatch.py --step subsidiaries # Load subsidiaries only
    py scripts/etl/load_corpwatch.py --step filings      # Load filing index only
    py scripts/etl/load_corpwatch.py --step indexes      # Create indexes only
    py scripts/etl/load_corpwatch.py --step crosswalk    # CIK bridge + crosswalk
    py scripts/etl/load_corpwatch.py --step hierarchy    # Corporate hierarchy
"""
import argparse
import csv
import io
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection

# Try to import name normalization
try:
    from src.python.matching.name_normalization import (
        normalize_name_standard,
        normalize_name_aggressive,
    )
except ImportError:
    print("WARNING: name_normalization not found, using basic fallback")
    def normalize_name_standard(name):
        return name.lower().strip() if name else None
    def normalize_name_aggressive(name):
        return name.lower().strip() if name else None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CSV_DIR = Path(r"C:\Users\jakew\Downloads\corpwatch_api_tables_csv\corpwatch_api_tables_csv")

BATCH_SIZE = 10_000
COPY_BATCH_SIZE = 50_000  # For COPY-based bulk loads


def _clean(val):
    """Return None for NULL/empty, else stripped string."""
    if val is None:
        return None
    val = str(val).strip()
    if val in ('', 'NULL', 'null', 'None', 'N/A', 'NA'):
        return None
    return val


def _clean_int(val):
    """Parse integer, return None on failure."""
    val = _clean(val)
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _clean_float(val):
    """Parse float, return None on failure."""
    val = _clean(val)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _tsv_reader(filepath):
    """Yield rows from a tab-delimited CSV with UTF-8 encoding."""
    with open(filepath, encoding='utf-8', errors='replace', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            yield row


def _copy_tsv(cur, table, columns, rows_iter, batch_size=COPY_BATCH_SIZE):
    """
    Bulk-load rows into a table using COPY (10-50x faster than execute_values).

    rows_iter: iterable of tuples, one per row, matching columns order.
    Values of None become \\N (PostgreSQL NULL marker).
    """
    total = 0
    batch = []

    for row in rows_iter:
        batch.append(row)
        if len(batch) >= batch_size:
            _flush_copy(cur, table, columns, batch)
            total += len(batch)
            batch = []

    if batch:
        _flush_copy(cur, table, columns, batch)
        total += len(batch)

    return total


def _flush_copy(cur, table, columns, batch):
    """Write a batch to PostgreSQL via COPY."""
    buf = io.StringIO()
    for row in batch:
        line = '\t'.join(
            '\\N' if v is None else str(v).replace('\t', ' ').replace('\n', ' ').replace('\\', '\\\\')
            for v in row
        )
        buf.write(line + '\n')
    buf.seek(0)
    cols = ', '.join(columns)
    cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT text, NULL '\\N')", buf)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def create_schema(conn):
    """Create all CorpWatch tables (DROP + CREATE)."""
    print("=" * 60)
    print("CREATING CORPWATCH SCHEMA")
    print("=" * 60)

    cur = conn.cursor()

    tables = [
        'corpwatch_filing_index',
        'corpwatch_subsidiaries',
        'corpwatch_relationships',
        'corpwatch_names',
        'corpwatch_locations',
        'corpwatch_companies',
    ]
    for t in tables:
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    conn.commit()
    print("  Dropped existing tables")

    # 1. corpwatch_companies
    cur.execute("""
        CREATE TABLE corpwatch_companies (
            cw_id INTEGER PRIMARY KEY,
            cik INTEGER,
            irs_number TEXT,
            company_name TEXT NOT NULL,
            name_normalized TEXT,
            name_aggressive TEXT,
            sic_code INTEGER,
            industry_name TEXT,
            num_parents INTEGER DEFAULT 0,
            num_children INTEGER DEFAULT 0,
            top_parent_id INTEGER,
            state VARCHAR(10),
            city TEXT,
            zip TEXT,
            country_code VARCHAR(5) DEFAULT 'US',
            is_us BOOLEAN DEFAULT TRUE,
            min_year INTEGER,
            max_year INTEGER
        )
    """)
    print("  Created corpwatch_companies")

    # 2. corpwatch_locations
    cur.execute("""
        CREATE TABLE corpwatch_locations (
            location_id INTEGER PRIMARY KEY,
            cw_id INTEGER NOT NULL REFERENCES corpwatch_companies(cw_id),
            type TEXT,
            street_1 TEXT,
            street_2 TEXT,
            city TEXT,
            state VARCHAR(10),
            postal_code TEXT,
            country_code VARCHAR(5),
            min_year INTEGER,
            max_year INTEGER
        )
    """)
    print("  Created corpwatch_locations")

    # 3. corpwatch_names
    cur.execute("""
        CREATE TABLE corpwatch_names (
            name_id INTEGER PRIMARY KEY,
            cw_id INTEGER NOT NULL REFERENCES corpwatch_companies(cw_id),
            company_name TEXT,
            name_normalized TEXT,
            date DATE,
            source TEXT,
            country_code VARCHAR(5),
            min_year INTEGER,
            max_year INTEGER
        )
    """)
    print("  Created corpwatch_names")

    # 4. corpwatch_relationships (parent -> child, all years)
    cur.execute("""
        CREATE TABLE corpwatch_relationships (
            relation_id INTEGER PRIMARY KEY,
            source_cw_id INTEGER NOT NULL,
            target_cw_id INTEGER NOT NULL,
            relation_origin TEXT,
            year INTEGER
        )
    """)
    print("  Created corpwatch_relationships")

    # 5. corpwatch_subsidiaries (from Exhibit 21 raw disclosures)
    cur.execute("""
        CREATE TABLE corpwatch_subsidiaries (
            relationship_id INTEGER PRIMARY KEY,
            parent_cw_id INTEGER,
            cw_id INTEGER,
            company_name TEXT,
            clean_company TEXT,
            name_normalized TEXT,
            country_code VARCHAR(5),
            hierarchy INTEGER,
            percent NUMERIC(5,2),
            year INTEGER,
            quarter INTEGER,
            parse_method TEXT
        )
    """)
    print("  Created corpwatch_subsidiaries")

    # 6. corpwatch_filing_index (10-K + Exhibit 21 URLs)
    cur.execute("""
        CREATE TABLE corpwatch_filing_index (
            filing_id INTEGER PRIMARY KEY,
            cik INTEGER,
            year INTEGER,
            quarter INTEGER,
            period_of_report TEXT,
            filing_date DATE,
            form_10k_url TEXT,
            sec_21_url TEXT
        )
    """)
    print("  Created corpwatch_filing_index")

    # Legacy match table for deterministic matcher
    cur.execute("DROP TABLE IF EXISTS corpwatch_f7_matches CASCADE")
    cur.execute("""
        CREATE TABLE corpwatch_f7_matches (
            cw_id INTEGER PRIMARY KEY,
            f7_employer_id TEXT NOT NULL,
            match_method TEXT,
            match_confidence NUMERIC(5,3),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    print("  Created corpwatch_f7_matches")

    conn.commit()
    print("  Schema creation complete\n")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_companies(conn):
    """Load company_info.csv -> corpwatch_companies (most_recent=1 only)."""
    print("=" * 60)
    print("LOADING corpwatch_companies (company_info.csv)")
    print("=" * 60)

    filepath = CSV_DIR / "company_info.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return 0

    cur = conn.cursor()
    t0 = time.time()

    loaded = 0
    skipped = 0
    state_counts = Counter()
    has_ein = 0
    has_cik = 0

    columns = [
        'cw_id', 'cik', 'irs_number', 'company_name', 'name_normalized',
        'name_aggressive', 'sic_code', 'industry_name', 'num_parents',
        'num_children', 'top_parent_id', 'state', 'city', 'zip',
        'country_code', 'is_us', 'min_year', 'max_year',
    ]

    def row_generator():
        nonlocal skipped, has_ein, has_cik
        for row in _tsv_reader(filepath):
            # Filter: most_recent=1 only
            if _clean(row.get('most_recent')) != '1':
                skipped += 1
                continue

            cw_id = _clean_int(row.get('cw_id'))
            if cw_id is None:
                skipped += 1
                continue

            name = _clean(row.get('company_name'))
            if not name:
                skipped += 1
                continue

            cik = _clean_int(row.get('cik'))
            irs = _clean(row.get('irs_number'))
            sic = _clean_int(row.get('sic_code'))
            industry = _clean(row.get('industry_name'))
            n_parents = _clean_int(row.get('num_parents')) or 0
            n_children = _clean_int(row.get('num_children')) or 0
            top_parent = _clean_int(row.get('top_parent_id'))
            min_yr = _clean_int(row.get('min_year'))
            max_yr = _clean_int(row.get('max_year'))

            # Country comes from best_location or source -- default US assumption
            # We'll update state/city/zip from locations table later
            country = 'US'  # default; will be refined
            is_us = True

            name_std = normalize_name_standard(name) if name else None
            name_agg = normalize_name_aggressive(name) if name else None

            if cik and cik > 0:
                has_cik += 1
            if irs:
                has_ein += 1

            yield (
                cw_id, cik, irs, name, name_std, name_agg,
                sic, industry, n_parents, n_children, top_parent,
                None, None, None,  # state, city, zip -- filled by locations step
                country, is_us, min_yr, max_yr,
            )

    loaded = _copy_tsv(cur, 'corpwatch_companies', columns, row_generator())
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Loaded: {loaded:,} rows in {elapsed:.1f}s")
    print(f"  Skipped: {skipped:,} (non-most_recent or missing data)")
    print(f"  With CIK: {has_cik:,} ({100*has_cik/max(loaded,1):.1f}%)")
    print(f"  With EIN/IRS: {has_ein:,} ({100*has_ein/max(loaded,1):.1f}%)")

    return loaded


def load_locations(conn):
    """Load company_locations.csv -> corpwatch_locations, then update companies with best location."""
    print("\n" + "=" * 60)
    print("LOADING corpwatch_locations (company_locations.csv)")
    print("=" * 60)

    filepath = CSV_DIR / "company_locations.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return 0

    cur = conn.cursor()
    t0 = time.time()

    # Pre-load set of valid cw_ids for FK filtering
    cur.execute("SELECT cw_id FROM corpwatch_companies")
    valid_ids = {r[0] for r in cur.fetchall()}
    print(f"  Valid company IDs: {len(valid_ids):,}")

    loaded = 0
    skipped = 0

    columns = [
        'location_id', 'cw_id', 'type', 'street_1', 'street_2',
        'city', 'state', 'postal_code', 'country_code', 'min_year', 'max_year',
    ]

    def row_generator():
        nonlocal skipped
        for row in _tsv_reader(filepath):
            if _clean(row.get('most_recent')) != '1':
                skipped += 1
                continue

            cw_id = _clean_int(row.get('cw_id'))
            if cw_id is None or cw_id not in valid_ids:
                skipped += 1
                continue

            cc = _clean(row.get('country_code'))
            if cc and cc != 'US':
                skipped += 1
                continue

            loc_id = _clean_int(row.get('location_id'))
            if loc_id is None:
                skipped += 1
                continue

            yield (
                loc_id, cw_id,
                _clean(row.get('type')),
                _clean(row.get('street_1')),
                _clean(row.get('street_2')),
                _clean(row.get('city')),
                _clean(row.get('state')),
                _clean(row.get('postal_code')),
                cc or 'US',
                _clean_int(row.get('min_year')),
                _clean_int(row.get('max_year')),
            )

    loaded = _copy_tsv(cur, 'corpwatch_locations', columns, row_generator())
    conn.commit()

    # Update companies with best location (business address preferred)
    print("  Updating companies with best location data...")
    cur.execute("""
        UPDATE corpwatch_companies c
        SET state = loc.state,
            city = loc.city,
            zip = loc.postal_code,
            country_code = loc.country_code,
            is_us = (loc.country_code = 'US')
        FROM (
            SELECT DISTINCT ON (cw_id)
                cw_id, state, city, postal_code, country_code
            FROM corpwatch_locations
            WHERE state IS NOT NULL
            ORDER BY cw_id,
                     CASE WHEN type = 'business' THEN 0 ELSE 1 END,
                     max_year DESC NULLS LAST,
                     location_id DESC
        ) loc
        WHERE c.cw_id = loc.cw_id
    """)
    updated = cur.rowcount
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Loaded: {loaded:,} locations in {elapsed:.1f}s")
    print(f"  Skipped: {skipped:,}")
    print(f"  Updated {updated:,} companies with state/city/zip")

    # State distribution
    cur.execute("""
        SELECT state, COUNT(*) AS cnt
        FROM corpwatch_companies
        WHERE state IS NOT NULL
        GROUP BY state ORDER BY cnt DESC LIMIT 10
    """)
    print("  Top states:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]:,}")

    return loaded


def load_names(conn):
    """Load company_names.csv -> corpwatch_names (most_recent=1, US)."""
    print("\n" + "=" * 60)
    print("LOADING corpwatch_names (company_names.csv)")
    print("=" * 60)

    filepath = CSV_DIR / "company_names.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return 0

    cur = conn.cursor()
    t0 = time.time()

    valid_ids = set()
    cur.execute("SELECT cw_id FROM corpwatch_companies")
    valid_ids = {r[0] for r in cur.fetchall()}

    loaded = 0
    skipped = 0

    columns = [
        'name_id', 'cw_id', 'company_name', 'name_normalized',
        'date', 'source', 'country_code', 'min_year', 'max_year',
    ]

    def row_generator():
        nonlocal skipped
        for row in _tsv_reader(filepath):
            if _clean(row.get('most_recent')) != '1':
                skipped += 1
                continue

            cw_id = _clean_int(row.get('cw_id'))
            if cw_id is None or cw_id not in valid_ids:
                skipped += 1
                continue

            cc = _clean(row.get('country_code'))
            if cc and cc != 'US':
                skipped += 1
                continue

            name_id = _clean_int(row.get('name_id'))
            name = _clean(row.get('company_name'))
            if name_id is None or not name:
                skipped += 1
                continue

            name_std = normalize_name_standard(name) if name else None
            date_val = _clean(row.get('date'))

            yield (
                name_id, cw_id, name, name_std,
                date_val, _clean(row.get('source')),
                cc or 'US',
                _clean_int(row.get('min_year')),
                _clean_int(row.get('max_year')),
            )

    loaded = _copy_tsv(cur, 'corpwatch_names', columns, row_generator())
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Loaded: {loaded:,} name records in {elapsed:.1f}s")
    print(f"  Skipped: {skipped:,}")

    return loaded


def load_relationships(conn):
    """Load company_relations.csv -> corpwatch_relationships (all years, COPY bulk)."""
    print("\n" + "=" * 60)
    print("LOADING corpwatch_relationships (company_relations.csv)")
    print("=" * 60)

    filepath = CSV_DIR / "company_relations.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return 0

    cur = conn.cursor()
    t0 = time.time()

    loaded = 0
    skipped = 0

    columns = ['relation_id', 'source_cw_id', 'target_cw_id', 'relation_origin', 'year']

    def row_generator():
        nonlocal skipped
        for row in _tsv_reader(filepath):
            rel_id = _clean_int(row.get('relation_id'))
            src = _clean_int(row.get('source_cw_id'))
            tgt = _clean_int(row.get('target_cw_id'))

            if rel_id is None or src is None or tgt is None:
                skipped += 1
                continue

            yield (
                rel_id, src, tgt,
                _clean(row.get('relation_origin')),
                _clean_int(row.get('year')),
            )

    loaded = _copy_tsv(cur, 'corpwatch_relationships', columns, row_generator(),
                       batch_size=COPY_BATCH_SIZE)
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Loaded: {loaded:,} relationship records in {elapsed:.1f}s")
    print(f"  Skipped: {skipped:,}")

    return loaded


def load_subsidiaries(conn):
    """Load relationships.csv -> corpwatch_subsidiaries (US-linked parents, skip ignore_record=1)."""
    print("\n" + "=" * 60)
    print("LOADING corpwatch_subsidiaries (relationships.csv)")
    print("=" * 60)

    filepath = CSV_DIR / "relationships.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return 0

    cur = conn.cursor()
    t0 = time.time()

    # Pre-load US cw_ids for O(1) parent filtering
    cur.execute("SELECT cw_id FROM corpwatch_companies WHERE is_us = TRUE")
    us_ids = {r[0] for r in cur.fetchall()}
    print(f"  US parent IDs for filtering: {len(us_ids):,}")

    loaded = 0
    skipped = 0
    skipped_ignore = 0
    skipped_non_us = 0

    columns = [
        'relationship_id', 'parent_cw_id', 'cw_id', 'company_name',
        'clean_company', 'name_normalized', 'country_code',
        'hierarchy', 'percent', 'year', 'quarter', 'parse_method',
    ]

    def row_generator():
        nonlocal skipped, skipped_ignore, skipped_non_us
        for row in _tsv_reader(filepath):
            # Skip ignored records
            if _clean(row.get('ignore_record')) == '1':
                skipped_ignore += 1
                skipped += 1
                continue

            rel_id = _clean_int(row.get('relationship_id'))
            parent = _clean_int(row.get('parent_cw_id'))

            if rel_id is None:
                skipped += 1
                continue

            # Filter: parent must be a US company
            if parent is not None and parent not in us_ids:
                skipped_non_us += 1
                skipped += 1
                continue

            name = _clean(row.get('company_name'))
            clean_name = _clean(row.get('clean_company'))
            name_std = normalize_name_standard(clean_name or name) if (clean_name or name) else None

            yield (
                rel_id, parent,
                _clean_int(row.get('cw_id')),
                name, clean_name, name_std,
                _clean(row.get('country_code')),
                _clean_int(row.get('hierarchy')),
                _clean_float(row.get('percent')),
                _clean_int(row.get('year')),
                _clean_int(row.get('quarter')),
                _clean(row.get('parse_method')),
            )

    loaded = _copy_tsv(cur, 'corpwatch_subsidiaries', columns, row_generator(),
                       batch_size=COPY_BATCH_SIZE)
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Loaded: {loaded:,} subsidiary records in {elapsed:.1f}s")
    print(f"  Skipped total: {skipped:,} (ignore_record={skipped_ignore:,}, non-US parent={skipped_non_us:,})")

    return loaded


def load_filings(conn):
    """Load company_filings.csv -> corpwatch_filing_index."""
    print("\n" + "=" * 60)
    print("LOADING corpwatch_filing_index (company_filings.csv)")
    print("=" * 60)

    filepath = CSV_DIR / "company_filings.csv"
    if not filepath.exists():
        print(f"  ERROR: {filepath} not found")
        return 0

    cur = conn.cursor()
    t0 = time.time()

    loaded = 0
    skipped = 0

    columns = [
        'filing_id', 'cik', 'year', 'quarter',
        'period_of_report', 'filing_date', 'form_10k_url', 'sec_21_url',
    ]

    def row_generator():
        nonlocal skipped
        for row in _tsv_reader(filepath):
            fid = _clean_int(row.get('filing_id'))
            if fid is None:
                skipped += 1
                continue

            filing_date = _clean(row.get('filing_date'))

            yield (
                fid,
                _clean_int(row.get('cik')),
                _clean_int(row.get('year')),
                _clean_int(row.get('quarter')),
                _clean(row.get('period_of_report')),
                filing_date,
                _clean(row.get('form_10k_url')),
                _clean(row.get('sec_21_url')),
            )

    loaded = _copy_tsv(cur, 'corpwatch_filing_index', columns, row_generator())
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Loaded: {loaded:,} filing records in {elapsed:.1f}s")
    print(f"  Skipped: {skipped:,}")

    return loaded


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

def create_indexes(conn):
    """Create all indexes (after bulk loading)."""
    print("\n" + "=" * 60)
    print("CREATING INDEXES")
    print("=" * 60)

    cur = conn.cursor()
    t0 = time.time()

    indexes = [
        # corpwatch_companies
        "CREATE INDEX IF NOT EXISTS idx_cwc_cik ON corpwatch_companies(cik) WHERE cik IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cwc_irs ON corpwatch_companies(irs_number) WHERE irs_number IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cwc_name_norm ON corpwatch_companies(name_normalized) WHERE name_normalized IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cwc_name_agg ON corpwatch_companies(name_aggressive) WHERE name_aggressive IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cwc_state ON corpwatch_companies(state) WHERE state IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cwc_top_parent ON corpwatch_companies(top_parent_id) WHERE top_parent_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cwc_is_us ON corpwatch_companies(is_us) WHERE is_us = TRUE",
        # corpwatch_locations
        "CREATE INDEX IF NOT EXISTS idx_cwl_cwid ON corpwatch_locations(cw_id)",
        "CREATE INDEX IF NOT EXISTS idx_cwl_state ON corpwatch_locations(state) WHERE state IS NOT NULL",
        # corpwatch_names
        "CREATE INDEX IF NOT EXISTS idx_cwn_cwid ON corpwatch_names(cw_id)",
        "CREATE INDEX IF NOT EXISTS idx_cwn_name_norm ON corpwatch_names(name_normalized) WHERE name_normalized IS NOT NULL",
        # corpwatch_relationships
        "CREATE INDEX IF NOT EXISTS idx_cwr_source ON corpwatch_relationships(source_cw_id)",
        "CREATE INDEX IF NOT EXISTS idx_cwr_target ON corpwatch_relationships(target_cw_id)",
        "CREATE INDEX IF NOT EXISTS idx_cwr_year ON corpwatch_relationships(year)",
        # corpwatch_subsidiaries
        "CREATE INDEX IF NOT EXISTS idx_cws_parent ON corpwatch_subsidiaries(parent_cw_id) WHERE parent_cw_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cws_cwid ON corpwatch_subsidiaries(cw_id) WHERE cw_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_cws_name_norm ON corpwatch_subsidiaries(name_normalized) WHERE name_normalized IS NOT NULL",
        # corpwatch_filing_index
        "CREATE INDEX IF NOT EXISTS idx_cwfi_cik ON corpwatch_filing_index(cik) WHERE cik IS NOT NULL",
        # corpwatch_f7_matches
        "CREATE INDEX IF NOT EXISTS idx_cwfm_f7 ON corpwatch_f7_matches(f7_employer_id)",
    ]

    for i, sql in enumerate(indexes, 1):
        idx_name = sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
        print(f"  [{i}/{len(indexes)}] {idx_name}...")
        cur.execute(sql)
    conn.commit()

    # pg_trgm index (slower, create separately)
    print("  Creating pg_trgm index on name_normalized (may take 2-5 min)...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    conn.commit()

    trgm_t0 = time.time()
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cwc_name_trgm
        ON corpwatch_companies USING gin (name_normalized gin_trgm_ops)
        WHERE name_normalized IS NOT NULL
    """)
    conn.commit()
    print(f"  pg_trgm index created in {time.time() - trgm_t0:.1f}s")

    elapsed = time.time() - t0
    print(f"  All {len(indexes) + 1} indexes created in {elapsed:.1f}s\n")


# ---------------------------------------------------------------------------
# Crosswalk Extension (Step 3-4)
# ---------------------------------------------------------------------------

def extend_crosswalk(conn):
    """Add corpwatch_id column and do CIK bridge matching."""
    print("\n" + "=" * 60)
    print("EXTENDING CROSSWALK + CIK BRIDGE MATCHING")
    print("=" * 60)

    cur = conn.cursor()
    t0 = time.time()

    # Add column
    cur.execute("""
        ALTER TABLE corporate_identifier_crosswalk
        ADD COLUMN IF NOT EXISTS corpwatch_id INTEGER
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cic_corpwatch
        ON corporate_identifier_crosswalk(corpwatch_id)
        WHERE corpwatch_id IS NOT NULL
    """)
    conn.commit()
    print("  Added corpwatch_id column to crosswalk")

    # CIK bridge: CorpWatch CIK -> existing crosswalk sec_cik -> f7_employer_id
    print("  CIK bridge matching...")
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET corpwatch_id = cw.cw_id
        FROM corpwatch_companies cw
        WHERE cw.cik = c.sec_cik
          AND cw.cik IS NOT NULL
          AND c.sec_cik IS NOT NULL
          AND c.corpwatch_id IS NULL
    """)
    cik_matched = cur.rowcount
    conn.commit()
    print(f"  CIK bridge: {cik_matched:,} crosswalk rows updated")

    # Also try EIN bridge: CorpWatch irs_number -> crosswalk ein
    print("  EIN bridge matching...")
    cur.execute("""
        UPDATE corporate_identifier_crosswalk c
        SET corpwatch_id = cw.cw_id
        FROM corpwatch_companies cw
        WHERE cw.irs_number = c.ein
          AND cw.irs_number IS NOT NULL
          AND c.ein IS NOT NULL
          AND c.corpwatch_id IS NULL
    """)
    ein_matched = cur.rowcount
    conn.commit()
    print(f"  EIN bridge: {ein_matched:,} crosswalk rows updated")

    # Write to unified_match_log for CIK bridge matches
    print("  Writing CIK bridge matches to unified_match_log...")
    cur.execute("""
        INSERT INTO unified_match_log (
            source_system, source_id, target_id, match_method,
            match_tier, confidence_score, status, evidence
        )
        SELECT
            'corpwatch',
            cw.cw_id::text,
            c.f7_employer_id,
            'CIK_BRIDGE',
            10,
            1.0,
            'active',
            jsonb_build_object(
                'bridge_type', 'CIK',
                'cik', cw.cik,
                'crosswalk_id', c.id
            )
        FROM corporate_identifier_crosswalk c
        JOIN corpwatch_companies cw ON cw.cw_id = c.corpwatch_id
        WHERE c.corpwatch_id IS NOT NULL
          AND c.f7_employer_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM unified_match_log u
              WHERE u.source_system = 'corpwatch'
                AND u.source_id = cw.cw_id::text
                AND u.status = 'active'
          )
    """)
    uml_count = cur.rowcount
    conn.commit()

    # Also write to corpwatch_f7_matches legacy table
    cur.execute("""
        INSERT INTO corpwatch_f7_matches (cw_id, f7_employer_id, match_method, match_confidence)
        SELECT c.corpwatch_id, c.f7_employer_id, 'CIK_BRIDGE', 1.0
        FROM corporate_identifier_crosswalk c
        WHERE c.corpwatch_id IS NOT NULL
          AND c.f7_employer_id IS NOT NULL
        ON CONFLICT (cw_id) DO UPDATE SET
            f7_employer_id = EXCLUDED.f7_employer_id,
            match_method = EXCLUDED.match_method,
            match_confidence = EXCLUDED.match_confidence
    """)
    legacy_count = cur.rowcount
    conn.commit()

    elapsed = time.time() - t0
    print(f"\n  Summary:")
    print(f"    CIK bridge matches: {cik_matched:,}")
    print(f"    EIN bridge matches: {ein_matched:,}")
    print(f"    unified_match_log entries: {uml_count:,}")
    print(f"    Legacy table entries: {legacy_count:,}")
    print(f"    Completed in {elapsed:.1f}s\n")


# ---------------------------------------------------------------------------
# Corporate Hierarchy Enrichment (Step 6)
# ---------------------------------------------------------------------------

def enrich_hierarchy(conn):
    """Insert CorpWatch parent-child edges into corporate_hierarchy."""
    print("\n" + "=" * 60)
    print("ENRICHING CORPORATE HIERARCHY")
    print("=" * 60)

    cur = conn.cursor()
    t0 = time.time()

    # Add corpwatch columns to corporate_hierarchy if missing
    for col, dtype in [('parent_corpwatch_id', 'INTEGER'), ('child_corpwatch_id', 'INTEGER')]:
        cur.execute(f"""
            ALTER TABLE corporate_hierarchy
            ADD COLUMN IF NOT EXISTS {col} {dtype}
        """)
    conn.commit()

    # Insert latest-year edges where at least one side has an F7 match
    # Uses corpwatch_relationships (parent->child) joined with corpwatch_f7_matches
    print("  Inserting CorpWatch hierarchy edges...")
    cur.execute("""
        INSERT INTO corporate_hierarchy (
            parent_name, parent_cik, parent_corpwatch_id,
            child_name, child_corpwatch_id, child_f7_employer_id,
            relationship_type, is_direct, source, confidence
        )
        SELECT DISTINCT ON (r.source_cw_id, r.target_cw_id)
            p.company_name,
            p.cik,
            r.source_cw_id,
            c.company_name,
            r.target_cw_id,
            COALESCE(cm_child.f7_employer_id, cm_parent.f7_employer_id),
            'subsidiary',
            TRUE,
            'CORPWATCH',
            'HIGH'
        FROM corpwatch_relationships r
        JOIN corpwatch_companies p ON p.cw_id = r.source_cw_id
        JOIN corpwatch_companies c ON c.cw_id = r.target_cw_id
        LEFT JOIN corpwatch_f7_matches cm_child ON cm_child.cw_id = r.target_cw_id
        LEFT JOIN corpwatch_f7_matches cm_parent ON cm_parent.cw_id = r.source_cw_id
        WHERE (cm_child.cw_id IS NOT NULL OR cm_parent.cw_id IS NOT NULL)
        ORDER BY r.source_cw_id, r.target_cw_id, r.year DESC
    """)
    inserted = cur.rowcount
    conn.commit()

    # Create index on new columns
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ch_parent_cw
        ON corporate_hierarchy(parent_corpwatch_id)
        WHERE parent_corpwatch_id IS NOT NULL
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ch_child_cw
        ON corporate_hierarchy(child_corpwatch_id)
        WHERE child_corpwatch_id IS NOT NULL
    """)
    conn.commit()

    elapsed = time.time() - t0
    print(f"  Inserted {inserted:,} CORPWATCH hierarchy edges in {elapsed:.1f}s")

    # Summary
    cur.execute("SELECT source, COUNT(*) FROM corporate_hierarchy GROUP BY source ORDER BY 2 DESC")
    print("  Hierarchy by source:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]:,}")

    return inserted


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(conn):
    """Print verification stats."""
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    cur = conn.cursor()

    tables = [
        'corpwatch_companies', 'corpwatch_locations', 'corpwatch_names',
        'corpwatch_relationships', 'corpwatch_subsidiaries', 'corpwatch_filing_index',
        'corpwatch_f7_matches',
    ]

    for t in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = cur.fetchone()[0]
            print(f"  {t:35s}: {cnt:>12,} rows")
        except Exception:
            conn.rollback()
            print(f"  {t:35s}: TABLE NOT FOUND")

    # EIN coverage
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies WHERE irs_number IS NOT NULL")
    ein_cnt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM corpwatch_companies")
    total = cur.fetchone()[0]
    print(f"\n  EIN coverage: {ein_cnt:,} / {total:,} ({100*ein_cnt/max(total,1):.1f}%)")

    # State distribution
    cur.execute("""
        SELECT state, COUNT(*) AS cnt
        FROM corpwatch_companies
        WHERE state IS NOT NULL
        GROUP BY state ORDER BY cnt DESC LIMIT 10
    """)
    print("  Top states:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]:,}")

    # Match coverage
    cur.execute("SELECT COUNT(*) FROM corpwatch_f7_matches")
    match_cnt = cur.fetchone()[0]
    print(f"\n  F7 matches (legacy): {match_cnt:,}")

    cur.execute("""
        SELECT match_method, COUNT(*) FROM unified_match_log
        WHERE source_system = 'corpwatch' AND status = 'active'
        GROUP BY match_method ORDER BY 2 DESC
    """)
    print("  unified_match_log (corpwatch):")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]:,}")

    # Spot-check known companies
    print("\n  Spot checks:")
    for name in ['WALMART', 'COMCAST', 'CITIGROUP', 'UPS', 'AMAZON']:
        cur.execute("""
            SELECT c.cw_id, c.company_name, c.cik, c.num_children,
                   m.f7_employer_id IS NOT NULL AS matched
            FROM corpwatch_companies c
            LEFT JOIN corpwatch_f7_matches m ON m.cw_id = c.cw_id
            WHERE c.name_normalized LIKE %s
            LIMIT 1
        """, (f'%{name.lower()}%',))
        r = cur.fetchone()
        if r:
            print(f"    {r[1]}: cw_id={r[0]}, cik={r[2]}, children={r[3]}, matched={r[4]}")
        else:
            print(f"    {name}: NOT FOUND")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Load CorpWatch data into PostgreSQL")
    parser.add_argument('--step', choices=[
        'schema', 'companies', 'locations', 'names', 'relations',
        'subsidiaries', 'filings', 'indexes', 'crosswalk', 'hierarchy',
        'verify',
    ], help="Run a single step (default: all)")
    args = parser.parse_args()

    conn = get_connection()
    conn.autocommit = False

    overall_start = time.time()

    try:
        if args.step:
            steps = [args.step]
        else:
            steps = [
                'schema', 'companies', 'locations', 'names', 'relations',
                'subsidiaries', 'filings', 'indexes', 'crosswalk', 'hierarchy',
                'verify',
            ]

        step_map = {
            'schema': lambda: create_schema(conn),
            'companies': lambda: load_companies(conn),
            'locations': lambda: load_locations(conn),
            'names': lambda: load_names(conn),
            'relations': lambda: load_relationships(conn),
            'subsidiaries': lambda: load_subsidiaries(conn),
            'filings': lambda: load_filings(conn),
            'indexes': lambda: create_indexes(conn),
            'crosswalk': lambda: extend_crosswalk(conn),
            'hierarchy': lambda: enrich_hierarchy(conn),
            'verify': lambda: verify(conn),
        }

        for step in steps:
            step_map[step]()

        print("\n" + "=" * 60)
        print(f"ALL DONE in {time.time() - overall_start:.1f}s")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
```

---

## File 2: scripts/matching/adapters/corpwatch_adapter.py (CREATE)

Matching adapter following the SEC adapter pattern exactly.

```python
"""
CorpWatch adapter for deterministic matching.

Provides load_unmatched(), load_all(), and write_legacy() functions
compatible with run_deterministic.py CLI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from db_config import get_connection

SOURCE_SYSTEM = "corpwatch"


def load_unmatched(conn, limit=None):
    """
    Load CorpWatch companies not yet matched in unified_match_log.

    Returns list of dicts with: id, name, state, city, zip, naics, ein, address
    """
    sql = """
        SELECT
            c.cw_id::text,
            c.company_name,
            c.irs_number,
            c.state,
            c.city,
            c.zip,
            c.sic_code
        FROM corpwatch_companies c
        LEFT JOIN unified_match_log uml
            ON uml.source_system = 'corpwatch'
            AND uml.source_id = c.cw_id::text
            AND uml.status = 'active'
        WHERE uml.id IS NULL
          AND c.company_name IS NOT NULL
          AND c.is_us = TRUE
    """

    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],           # cw_id as text
            "name": r[1],         # company_name
            "state": r[3],        # state
            "city": r[4],         # city
            "zip": r[5],          # zip
            "naics": None,        # CorpWatch has SIC, not NAICS
            "ein": r[2],          # irs_number (EIN)
            "address": None,      # No full address field
        }
        for r in rows
    ]


def load_all(conn, limit=None):
    """Load ALL US CorpWatch companies (for re-matching)."""
    sql = """
        SELECT
            c.cw_id::text,
            c.company_name,
            c.irs_number,
            c.state,
            c.city,
            c.zip,
            c.sic_code
        FROM corpwatch_companies c
        WHERE c.company_name IS NOT NULL
          AND c.is_us = TRUE
    """

    if limit:
        sql += f" LIMIT {int(limit)}"

    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "name": r[1],
            "state": r[3],
            "city": r[4],
            "zip": r[5],
            "naics": None,    # CorpWatch has SIC, not NAICS
            "ein": r[2],
            "address": None,
        }
        for r in rows
    ]


def write_legacy(conn, matches):
    """
    Write CorpWatch matches to corpwatch_f7_matches legacy table.
    Uses ON CONFLICT DO UPDATE for idempotent re-runs.
    """
    if not matches:
        return 0

    from psycopg2.extras import execute_batch

    print(f"  Writing {len(matches):,} matches to corpwatch_f7_matches...")

    sql = """
        INSERT INTO corpwatch_f7_matches (cw_id, f7_employer_id, match_method, match_confidence)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (cw_id) DO UPDATE SET
            f7_employer_id = EXCLUDED.f7_employer_id,
            match_method = EXCLUDED.match_method,
            match_confidence = EXCLUDED.match_confidence
    """

    rows = [
        (int(m["source_id"]), m["target_id"], m["method"], m["score"])
        for m in matches
    ]

    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=1000)
    conn.commit()

    print(f"  Wrote {len(rows):,} legacy match rows")
    return len(rows)
```

---

## File 3: scripts/matching/run_deterministic.py (MODIFY)

**Change:** Add 1 import + 1 dict entry.

**Line 28** -- add to the import line:
```python
# BEFORE:
from scripts.matching.adapters import osha_adapter, whd_adapter, n990_adapter, sam_adapter, sec_adapter_module, bmf_adapter_module

# AFTER:
from scripts.matching.adapters import osha_adapter, whd_adapter, n990_adapter, sam_adapter, sec_adapter_module, bmf_adapter_module, corpwatch_adapter
```

**Lines 30-37** -- add to ADAPTERS dict:
```python
# BEFORE:
ADAPTERS = {
    "osha": osha_adapter,
    "whd": whd_adapter,
    "990": n990_adapter,
    "sam": sam_adapter,
    "sec": sec_adapter_module,
    "bmf": bmf_adapter_module,
}

# AFTER:
ADAPTERS = {
    "osha": osha_adapter,
    "whd": whd_adapter,
    "990": n990_adapter,
    "sam": sam_adapter,
    "sec": sec_adapter_module,
    "bmf": bmf_adapter_module,
    "corpwatch": corpwatch_adapter,
}
```

---

## File 4: scripts/scoring/build_employer_data_sources.py (MODIFY)

**Change:** Add `has_corpwatch` flag to MV SQL.

### 4a. Add CTE (after line 45, the `sam_matched` CTE):

```sql
corpwatch_matched AS (
    SELECT DISTINCT f7_employer_id FROM corpwatch_f7_matches
),
```

### 4b. Add to uml_sources CTE (line 28):

```sql
-- BEFORE:
           bool_or(source_system = 'mergent') AS has_mergent
    FROM unified_match_log
    WHERE status = 'active'
      AND source_system IN ('sec', 'gleif', 'mergent')

-- AFTER:
           bool_or(source_system = 'mergent') AS has_mergent,
           bool_or(source_system = 'corpwatch') AS has_corpwatch
    FROM unified_match_log
    WHERE status = 'active'
      AND source_system IN ('sec', 'gleif', 'mergent', 'corpwatch')
```

### 4c. Add flag to SELECT (after line 84):

```sql
    COALESCE(u.has_corpwatch, FALSE) AS has_corpwatch,
```

### 4d. Add to source_count (after line 94, the has_mergent line):

```sql
     + CASE WHEN COALESCE(u.has_corpwatch, FALSE) THEN 1 ELSE 0 END
```

### 4e. Add corpwatch_id to LATERAL subquery (line 120):

```sql
    SELECT corporate_family_id, sec_cik, gleif_lei, mergent_duns,
           ein, ticker, is_public, is_federal_contractor,
           federal_obligations, federal_contract_count,
           corpwatch_id
```

### 4f. Add to _print_stats (line 155-156, the col list):

```python
    for col in ['has_osha', 'has_nlrb', 'has_whd', 'has_990', 'has_sam',
                'has_sec', 'has_gleif', 'has_mergent', 'has_corpwatch']:
```

---

## File 5: scripts/etl/build_crosswalk.py (MODIFY)

**Change:** Add `corpwatch_id` column to schema.

### 5a. Add to CREATE TABLE (line 52, after `is_public`):

```sql
            corpwatch_id INTEGER,
```

### 5b. Add index (in `create_indexes()`, line 309 area):

```python
        'CREATE INDEX idx_cic_corpwatch ON corporate_identifier_crosswalk(corpwatch_id) WHERE corpwatch_id IS NOT NULL',
```

---

## Execution Runbook

Run these commands in order from the project root.

### Phase 1: ETL (~20 min)

```bash
# Full ETL (schema + all CSV loads + indexes + crosswalk + hierarchy)
py scripts/etl/load_corpwatch.py

# OR step by step:
py scripts/etl/load_corpwatch.py --step schema
py scripts/etl/load_corpwatch.py --step companies
py scripts/etl/load_corpwatch.py --step locations
py scripts/etl/load_corpwatch.py --step names
py scripts/etl/load_corpwatch.py --step relations
py scripts/etl/load_corpwatch.py --step subsidiaries
py scripts/etl/load_corpwatch.py --step filings
py scripts/etl/load_corpwatch.py --step indexes
py scripts/etl/load_corpwatch.py --step seed_master    # Seed into master_employers (6-stage)
py scripts/etl/load_corpwatch.py --step crosswalk
py scripts/etl/load_corpwatch.py --step hierarchy
py scripts/etl/load_corpwatch.py --step verify
```

### Phase 2: Deterministic Matching (~2-3 hrs)

Run in 4 sequential batches. Do NOT run in parallel (OSHA contention lesson).

```bash
py scripts/matching/run_deterministic.py corpwatch --rematch-all --batch 1/4
py scripts/matching/run_deterministic.py corpwatch --rematch-all --batch 2/4
py scripts/matching/run_deterministic.py corpwatch --rematch-all --batch 3/4
py scripts/matching/run_deterministic.py corpwatch --rematch-all --batch 4/4
```

Check progress:
```bash
py scripts/matching/run_deterministic.py corpwatch --batch-status
```

### Phase 3: Rebuild MVs

After matching completes, must DROP+CREATE (not just REFRESH) because MV SQL changed:

```bash
py scripts/scoring/build_employer_data_sources.py
py scripts/scoring/build_unified_scorecard.py
py scripts/scoring/rebuild_search_mv.py
py scripts/scoring/create_scorecard_mv.py --refresh
```

### Phase 4: Run Tests

```bash
pytest tests/ -x
```

All 518+ existing tests should still pass.

---

## Verification Queries

Run these after everything completes:

```sql
-- Table row counts
SELECT 'corpwatch_companies' AS tbl, COUNT(*) FROM corpwatch_companies
UNION ALL SELECT 'corpwatch_locations', COUNT(*) FROM corpwatch_locations
UNION ALL SELECT 'corpwatch_names', COUNT(*) FROM corpwatch_names
UNION ALL SELECT 'corpwatch_relationships', COUNT(*) FROM corpwatch_relationships
UNION ALL SELECT 'corpwatch_subsidiaries', COUNT(*) FROM corpwatch_subsidiaries
UNION ALL SELECT 'corpwatch_filing_index', COUNT(*) FROM corpwatch_filing_index
UNION ALL SELECT 'corpwatch_f7_matches', COUNT(*) FROM corpwatch_f7_matches;

-- EIN coverage
SELECT COUNT(*) FILTER (WHERE irs_number IS NOT NULL) AS has_ein,
       COUNT(*) AS total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE irs_number IS NOT NULL) / COUNT(*), 1) AS pct
FROM corpwatch_companies;

-- State distribution (sanity: CA, NY, TX, FL at top)
SELECT state, COUNT(*) AS cnt
FROM corpwatch_companies WHERE state IS NOT NULL
GROUP BY state ORDER BY cnt DESC LIMIT 10;

-- Match rate by method/tier
SELECT match_method, COUNT(*) AS cnt
FROM unified_match_log
WHERE source_system = 'corpwatch' AND status = 'active'
GROUP BY match_method ORDER BY cnt DESC;

-- Match rate by tier
SELECT match_tier, COUNT(*) AS cnt
FROM unified_match_log
WHERE source_system = 'corpwatch' AND status = 'active'
GROUP BY match_tier ORDER BY match_tier;

-- Spot-check known companies
SELECT c.company_name, c.cw_id, c.cik, c.num_children,
       m.f7_employer_id, m.match_method
FROM corpwatch_companies c
LEFT JOIN corpwatch_f7_matches m ON m.cw_id = c.cw_id
WHERE c.name_normalized IN ('walmart', 'comcast', 'citigroup', 'ups', 'amazon');

-- Corporate tree coverage
SELECT COUNT(DISTINCT c.top_parent_id) AS trees_with_f7_match
FROM corpwatch_companies c
JOIN corpwatch_f7_matches m ON m.cw_id = c.cw_id
WHERE c.top_parent_id IS NOT NULL;

-- New hierarchy edges
SELECT source, COUNT(*) FROM corporate_hierarchy GROUP BY source ORDER BY 2 DESC;

-- Master employers seeding
SELECT COUNT(*) AS corpwatch_source_ids
FROM master_employer_source_ids WHERE source_system = 'corpwatch';

SELECT COUNT(*) AS new_corpwatch_masters
FROM master_employers WHERE source_origin = 'corpwatch';

SELECT COUNT(*) AS existing_masters_linked
FROM master_employers m
JOIN master_employer_source_ids s ON s.master_id = m.master_id
WHERE s.source_system = 'corpwatch' AND m.source_origin != 'corpwatch';

-- Updated data sources MV
SELECT COUNT(*) FILTER (WHERE has_corpwatch) AS has_corpwatch,
       COUNT(*) AS total
FROM mv_employer_data_sources;
```

---

## Bottlenecks & Known Issues

| Issue | Risk | Mitigation |
|---|---|---|
| Windows cp1252 encoding | HIGH | `open(f, encoding='utf-8', errors='replace')` on all reads |
| relationships.csv 721MB | MEDIUM | Stream line-by-line, pre-load US cw_id set for O(1) filter |
| company_relations 3.5M inserts | MEDIUM | `COPY` via StringIO (10-50x faster than execute_values) |
| pg_trgm index on 361K rows | LOW | Created AFTER bulk load (~2-5 min) |
| Matching 361K against 147K F7 | MEDIUM | 4 sequential batches, DO NOT run in parallel |
| Tab-delimited parsing | LOW | Consistent `delimiter='\t'` on all DictReader calls |
| NULL literal in CSVs | LOW | `_clean()` function handles 'NULL' string -> None |

---

## Expected Outcomes

- **corpwatch_companies:** ~361K rows (most_recent=1)
- **corpwatch_locations:** ~400K rows (US, most_recent=1)
- **corpwatch_names:** ~500K rows (US, most_recent=1)
- **corpwatch_relationships:** ~3.5M rows (all years)
- **corpwatch_subsidiaries:** ~2M rows (US-linked parents)
- **corpwatch_filing_index:** ~208K rows
- **CIK bridge matches:** ~3-5K (limited by existing SEC match count of 2,924)
- **Total matches after deterministic:** ~15-30K (4-8% of 361K)
- **New hierarchy edges:** thousands (dramatically expanding current 3,313)
- **has_corpwatch flag:** will appear on mv_employer_data_sources after MV rebuild
- **master_employers seeded:** ~361K US companies (many will match existing masters via EIN/name+state)
- **master_employer_source_ids:** corpwatch source_system entries linking to master rows
