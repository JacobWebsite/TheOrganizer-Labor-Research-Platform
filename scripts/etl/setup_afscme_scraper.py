"""
Checkpoint 1: AFSCME Web Scraper Setup
- Creates web_union_* tables
- Loads afscme_national_directory.csv into web_union_profiles
- Matches against unions_master (OLMS)
"""
import sys
import os
import csv
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


# ── Step 1: Create tables ─────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS web_union_profiles (
    id SERIAL PRIMARY KEY,
    f_num VARCHAR,
    union_name VARCHAR NOT NULL,
    local_number VARCHAR,
    parent_union VARCHAR DEFAULT 'AFSCME',
    state VARCHAR(50),
    website_url TEXT,
    platform VARCHAR,
    raw_text TEXT,
    raw_text_about TEXT,
    raw_text_contracts TEXT,
    raw_text_news TEXT,
    extra_data JSONB,
    last_scraped TIMESTAMP,
    scrape_status VARCHAR DEFAULT 'PENDING',
    match_status VARCHAR DEFAULT 'PENDING_REVIEW',
    section VARCHAR,
    source_directory_url TEXT,
    officers TEXT,
    address TEXT,
    phone VARCHAR,
    fax VARCHAR,
    email VARCHAR,
    facebook TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_union_employers (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    employer_name VARCHAR NOT NULL,
    employer_name_clean VARCHAR,
    state VARCHAR(2),
    sector VARCHAR,
    source_url TEXT,
    extraction_method VARCHAR,
    confidence_score DECIMAL,
    matched_employer_id INTEGER,
    match_status VARCHAR DEFAULT 'PENDING_REVIEW',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_union_contracts (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    contract_title VARCHAR,
    employer_name VARCHAR,
    contract_url TEXT,
    expiration_date DATE,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_union_news (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    headline VARCHAR,
    summary TEXT,
    news_type VARCHAR,
    date_published DATE,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS web_union_membership (
    id SERIAL PRIMARY KEY,
    web_profile_id INTEGER REFERENCES web_union_profiles(id),
    member_count INTEGER,
    member_count_source VARCHAR,
    count_type VARCHAR,
    as_of_date DATE,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_jobs (
    id SERIAL PRIMARY KEY,
    tool VARCHAR DEFAULT 'UNION_SCRAPER',
    target_url TEXT NOT NULL,
    target_entity_type VARCHAR,
    web_profile_id INTEGER,
    status VARCHAR DEFAULT 'QUEUED',
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    pages_scraped INTEGER DEFAULT 0,
    pages_found TEXT[],
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds DECIMAL,
    created_at TIMESTAMP DEFAULT NOW()
);
"""


def create_tables(conn):
    """Create all web_union_* tables."""
    cur = conn.cursor()
    cur.execute(CREATE_TABLES_SQL)
    conn.commit()
    print("[OK] Created 6 tables: web_union_profiles, web_union_employers, "
          "web_union_contracts, web_union_news, web_union_membership, scrape_jobs")


# ── Step 2: Load CSV ──────────────────────────────────────────────────────

def extract_local_number(name):
    """Extract local/council number from union name."""
    # Patterns: "Local 52", "Council 4", "Chapter 97", "Local 3299"
    # Also: "AFSCME Local 1644", "Council 61:", "Local 1000:"
    patterns = [
        r'Local\s+(\d+)',
        r'Council\s+(\d+)',
        r'Chapter\s+(\d+)',
        r'District Council\s+(\d+)',
        r'District\s+(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, name, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


# Map US state names to 2-letter abbreviations
STATE_ABBREVS = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
    'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
    'District Of Columbia': 'DC', 'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI',
    'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME',
    'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE',
    'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM',
    'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH',
    'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Puerto Rico': 'PR',
    'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT',
    'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV',
    'Wisconsin': 'WI', 'Wyoming': 'WY',
}


def load_csv(conn, csv_path):
    """Load afscme_national_directory.csv into web_union_profiles."""
    cur = conn.cursor()

    # Check if already loaded
    cur.execute("SELECT count(*) FROM web_union_profiles WHERE parent_union = 'AFSCME'")
    existing = cur.fetchone()[0]
    if existing > 0:
        print(f"[SKIP] web_union_profiles already has {existing} AFSCME rows. "
              "Drop table or truncate to reload.")
        return existing

    inserted = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            state_full = row['state'].strip()
            state_abbr = STATE_ABBREVS.get(state_full, state_full)
            name = row['name'].strip()
            local_num = extract_local_number(name)
            website = row.get('website', '').strip() or None
            section = row.get('section', '').strip() or None
            officers = row.get('officers', '').strip() or None
            address = row.get('address', '').strip() or None
            phone = row.get('phone', '').strip() or None
            fax = row.get('fax', '').strip() or None
            email = row.get('email', '').strip() or None
            facebook = row.get('facebook', '').strip() or None
            source_url = row.get('source_url', '').strip() or None

            # Set initial scrape_status
            scrape_status = 'PENDING' if website else 'NO_WEBSITE'

            cur.execute("""
                INSERT INTO web_union_profiles
                    (union_name, local_number, parent_union, state, website_url,
                     scrape_status, section, source_directory_url,
                     officers, address, phone, fax, email, facebook)
                VALUES (%s, %s, 'AFSCME', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (name, local_num, state_abbr, website, scrape_status,
                  section, source_url, officers, address, phone, fax, email, facebook))
            inserted += 1

    conn.commit()
    print(f"[OK] Loaded {inserted} rows into web_union_profiles")
    return inserted


# ── Step 3: OLMS Matching ─────────────────────────────────────────────────

def match_olms(conn):
    """Match web_union_profiles against unions_master on AFSCME + local_number + state."""
    cur = conn.cursor()

    # Get all web profiles with local numbers
    cur.execute("""
        SELECT id, union_name, local_number, state
        FROM web_union_profiles
        WHERE parent_union = 'AFSCME' AND local_number IS NOT NULL
    """)
    profiles = cur.fetchall()

    # Get all AFSCME unions from unions_master
    cur.execute("""
        SELECT f_num, union_name, local_number, state, members
        FROM unions_master
        WHERE aff_abbr = 'AFSCME'
    """)
    olms_unions = cur.fetchall()

    # Build lookup: (local_number, state) -> [(f_num, union_name, members)]
    olms_lookup = {}
    for f_num, uname, local_num, st, members in olms_unions:
        if local_num:
            key = (str(local_num).strip(), (st or '').strip().upper())
            olms_lookup.setdefault(key, []).append((f_num, uname, members))

    # Also build local-only lookup for cross-state matches
    olms_by_local = {}
    for f_num, uname, local_num, st, members in olms_unions:
        if local_num:
            olms_by_local.setdefault(str(local_num).strip(), []).append(
                (f_num, uname, st, members))

    matched = 0
    unmatched_with_local = 0
    no_local = 0
    multi_match = 0

    for pid, union_name, local_num, state in profiles:
        if not local_num:
            no_local += 1
            continue

        key = (str(local_num).strip(), (state or '').strip().upper())
        candidates = olms_lookup.get(key, [])

        if len(candidates) == 1:
            f_num, olms_name, members = candidates[0]
            cur.execute("""
                UPDATE web_union_profiles
                SET f_num = %s, match_status = 'MATCHED_OLMS'
                WHERE id = %s
            """, (f_num, pid))
            matched += 1
        elif len(candidates) > 1:
            # Pick the one with highest membership
            best = max(candidates, key=lambda x: x[2] or 0)
            f_num, olms_name, members = best
            cur.execute("""
                UPDATE web_union_profiles
                SET f_num = %s, match_status = 'MATCHED_OLMS'
                WHERE id = %s
            """, (f_num, pid))
            matched += 1
            multi_match += 1
        else:
            # Try local-only match (some entries have wrong state, e.g. Council 61
            # listed under Kansas but OLMS has it under Iowa)
            local_candidates = olms_by_local.get(str(local_num).strip(), [])
            if len(local_candidates) == 1:
                f_num, olms_name, olms_st, members = local_candidates[0]
                cur.execute("""
                    UPDATE web_union_profiles
                    SET f_num = %s, match_status = 'MATCHED_OLMS_CROSS_STATE'
                    WHERE id = %s
                """, (f_num, pid))
                matched += 1
            else:
                cur.execute("""
                    UPDATE web_union_profiles
                    SET match_status = 'UNMATCHED'
                    WHERE id = %s
                """, (pid,))
                unmatched_with_local += 1

    # Mark entries without local numbers
    cur.execute("""
        UPDATE web_union_profiles
        SET match_status = 'NO_LOCAL_NUMBER'
        WHERE local_number IS NULL AND match_status = 'PENDING_REVIEW'
    """)

    conn.commit()
    print(f"\n=== OLMS Matching Results ===")
    print(f"  Matched (state+local):       {matched - multi_match}")
    print(f"  Matched (multi, picked best): {multi_match}")
    print(f"  Unmatched (has local#):       {unmatched_with_local}")
    print(f"  No local number:              {no_local}")
    print(f"  Total with local numbers:     {len(profiles)}")


# ── Step 4: Summary ──────────────────────────────────────────────────────

def print_summary(conn):
    """Print Checkpoint 1 summary."""
    cur = conn.cursor()

    print("\n" + "=" * 60)
    print("CHECKPOINT 1 SUMMARY")
    print("=" * 60)

    # Total rows
    cur.execute("SELECT count(*) FROM web_union_profiles")
    total = cur.fetchone()[0]
    print(f"\nTotal profiles loaded: {total}")

    # By state (top 10)
    cur.execute("""
        SELECT state, count(*) FROM web_union_profiles
        GROUP BY state ORDER BY count(*) DESC LIMIT 10
    """)
    print("\nTop 10 states:")
    for st, cnt in cur.fetchall():
        print(f"  {st}: {cnt}")

    # By section
    cur.execute("""
        SELECT COALESCE(section, '(none)'), count(*)
        FROM web_union_profiles
        GROUP BY section ORDER BY count(*) DESC
    """)
    print("\nBy section:")
    for sec, cnt in cur.fetchall():
        print(f"  {sec}: {cnt}")

    # Website URLs
    cur.execute("SELECT count(*) FROM web_union_profiles WHERE website_url IS NOT NULL")
    with_url = cur.fetchone()[0]
    print(f"\nWith website URL: {with_url}")
    print(f"Without website:  {total - with_url}")

    # Scrape status
    cur.execute("""
        SELECT scrape_status, count(*)
        FROM web_union_profiles
        GROUP BY scrape_status ORDER BY count(*) DESC
    """)
    print("\nScrape status:")
    for status, cnt in cur.fetchall():
        print(f"  {status}: {cnt}")

    # Match status
    cur.execute("""
        SELECT match_status, count(*)
        FROM web_union_profiles
        GROUP BY match_status ORDER BY count(*) DESC
    """)
    print("\nOLMS match status:")
    for status, cnt in cur.fetchall():
        print(f"  {status}: {cnt}")

    # Sample matched entries
    cur.execute("""
        SELECT wp.id, wp.union_name, wp.local_number, wp.state, wp.f_num,
               wp.website_url, um.union_name as olms_name, um.members
        FROM web_union_profiles wp
        LEFT JOIN unions_master um ON wp.f_num = um.f_num
        WHERE wp.match_status LIKE 'MATCHED%%'
        ORDER BY um.members DESC NULLS LAST
        LIMIT 10
    """)
    print("\nTop 10 matched profiles (by OLMS membership):")
    print("-" * 90)
    for row in cur.fetchall():
        pid, name, local, st, fnum, url, olms_name, members = row
        print(f"  [{pid}] {name[:40]:<40} L{local or '?':<6} {st}  "
              f"f_num={fnum}  members={members or 0:,}  url={'Y' if url else 'N'}")

    # Sample unmatched with local number
    cur.execute("""
        SELECT id, union_name, local_number, state, website_url
        FROM web_union_profiles
        WHERE match_status = 'UNMATCHED'
        LIMIT 10
    """)
    unmatched = cur.fetchall()
    if unmatched:
        print(f"\nSample unmatched (with local#):")
        print("-" * 90)
        for pid, name, local, st, url in unmatched:
            print(f"  [{pid}] {name[:50]:<50} L{local:<6} {st}  url={'Y' if url else 'N'}")

    # Matched with website (the ones we'll scrape)
    cur.execute("""
        SELECT count(*) FROM web_union_profiles
        WHERE match_status LIKE 'MATCHED%%' AND website_url IS NOT NULL
    """)
    scrape_ready = cur.fetchone()[0]
    cur.execute("""
        SELECT count(*) FROM web_union_profiles
        WHERE website_url IS NOT NULL
    """)
    total_with_url = cur.fetchone()[0]
    print(f"\n>>> Ready for Phase 2 scraping: {total_with_url} sites "
          f"({scrape_ready} OLMS-matched, {total_with_url - scrape_ready} unmatched)")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    csv_path = os.path.join(os.path.dirname(__file__), '..', '..',
                            'afscme scrape', 'afscme_national_directory.csv')
    csv_path = os.path.normpath(csv_path)

    if not os.path.exists(csv_path):
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)

    print(f"CSV: {csv_path}")

    conn = get_connection()
    try:
        create_tables(conn)
        load_csv(conn, csv_path)
        match_olms(conn)
        print_summary(conn)
    finally:
        conn.close()
