"""
Idempotent schema migration for union web scraper tiered extraction.

Adds columns to web_union_profiles and web_union_employers,
creates web_union_pages and web_union_pdf_links tables.

Usage:
    py scripts/etl/migrate_scraper_schema.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


def migrate(conn):
    cur = conn.cursor()

    # ── 1a. Add columns to web_union_profiles ──
    profile_cols = [
        ("wp_api_available", "BOOLEAN DEFAULT FALSE"),
        ("wp_api_base", "TEXT"),
        ("sitemap_url", "TEXT"),
        ("sitemap_parsed", "BOOLEAN DEFAULT FALSE"),
        ("nav_links_parsed", "BOOLEAN DEFAULT FALSE"),
        ("extraction_tier_reached", "INTEGER DEFAULT 0"),
        ("gemini_used", "BOOLEAN DEFAULT FALSE"),
        ("page_inventory", "JSONB"),
    ]
    for col_name, col_def in profile_cols:
        cur.execute(f"""
            ALTER TABLE web_union_profiles
            ADD COLUMN IF NOT EXISTS {col_name} {col_def}
        """)
    print(f"web_union_profiles: ensured {len(profile_cols)} columns")

    # Backfill wp_api_available for known WordPress sites
    cur.execute("""
        UPDATE web_union_profiles
        SET wp_api_available = TRUE
        WHERE platform = 'WordPress' AND wp_api_available IS NOT TRUE
    """)
    backfilled = cur.rowcount
    if backfilled:
        print(f"  Backfilled wp_api_available=TRUE for {backfilled} WordPress profiles")

    # ── 1b. Add columns to web_union_employers ──
    employer_cols = [
        ("source_page_url", "TEXT"),
        ("source_element", "VARCHAR"),
        ("updated_at", "TIMESTAMP DEFAULT NOW()"),
    ]
    for col_name, col_def in employer_cols:
        cur.execute(f"""
            ALTER TABLE web_union_employers
            ADD COLUMN IF NOT EXISTS {col_name} {col_def}
        """)
    print(f"web_union_employers: ensured {len(employer_cols)} columns")

    # ── 1c. Unique constraint on web_union_employers ──
    cur.execute("""
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_web_employer_profile_name'
    """)
    if not cur.fetchone():
        cur.execute("""
            ALTER TABLE web_union_employers
            ADD CONSTRAINT uq_web_employer_profile_name
            UNIQUE (web_profile_id, employer_name_clean)
        """)
        print("Added unique constraint uq_web_employer_profile_name")
    else:
        print("Unique constraint uq_web_employer_profile_name already exists")

    # ── 1d. Create web_union_pages ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS web_union_pages (
            id SERIAL PRIMARY KEY,
            web_profile_id INTEGER REFERENCES web_union_profiles(id),
            page_url TEXT NOT NULL,
            final_url TEXT,
            page_type TEXT DEFAULT 'unknown',
            http_status INTEGER,
            content_hash TEXT,
            markdown_text TEXT,
            html_raw TEXT,
            discovered_from TEXT,
            last_scraped TIMESTAMP DEFAULT NOW(),
            UNIQUE(web_profile_id, page_url)
        )
    """)
    # Indexes
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_web_union_pages_profile
        ON web_union_pages(web_profile_id)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_web_union_pages_type
        ON web_union_pages(page_type)
    """)
    print("web_union_pages: table + indexes ensured")

    # ── 1e. Create web_union_pdf_links ──
    cur.execute("""
        CREATE TABLE IF NOT EXISTS web_union_pdf_links (
            id SERIAL PRIMARY KEY,
            profile_id INTEGER REFERENCES web_union_profiles(id),
            page_id INTEGER REFERENCES web_union_pages(id),
            pdf_url TEXT NOT NULL,
            link_text TEXT,
            page_context TEXT,
            pdf_type TEXT DEFAULT 'unknown',
            sent_to_cba_parser BOOLEAN DEFAULT FALSE,
            discovered_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(profile_id, pdf_url)
        )
    """)
    print("web_union_pdf_links: table ensured")

    conn.commit()
    print("\nMigration complete.")

    # ── Verify ──
    print("\n--- Verification ---")

    # Check new profile columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'web_union_profiles'
          AND column_name IN ('wp_api_available', 'wp_api_base', 'sitemap_url',
                              'sitemap_parsed', 'nav_links_parsed',
                              'extraction_tier_reached', 'gemini_used', 'page_inventory')
        ORDER BY column_name
    """)
    cols = [r[0] for r in cur.fetchall()]
    print(f"web_union_profiles new columns: {cols}")

    # Check new employer columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'web_union_employers'
          AND column_name IN ('source_page_url', 'source_element', 'updated_at')
        ORDER BY column_name
    """)
    cols = [r[0] for r in cur.fetchall()]
    print(f"web_union_employers new columns: {cols}")

    # Check new tables
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_name IN ('web_union_pages', 'web_union_pdf_links')
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print(f"New tables: {tables}")


if __name__ == '__main__':
    conn = get_connection()
    try:
        migrate(conn)
    finally:
        conn.close()
