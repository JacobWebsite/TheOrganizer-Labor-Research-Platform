"""
Insert New Events into Database - Script 3 of 3

Reads the crosscheck report and inserts records with match_status='NEW'
into manual_employers with union linkage from unions_master.

Union linkage strategy:
  1. Match by aff_abbr + local_number + state (exact local)
  2. Fallback: aff_abbr + state ordered by members DESC
  3. Fallback: aff_abbr only, ordered by members DESC
  4. Independent/new unions: linked_union_file_number = NULL
"""

import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection as _get_connection
from scripts.matching.normalizer import normalize_employer_name

INPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "crosscheck_report.csv")


def get_connection():
    return _get_connection()


def load_new_records(path):
    """Load only NEW records from crosscheck report."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("match_status") == "NEW":
                if row.get("num_employees"):
                    try:
                        row["num_employees"] = int(row["num_employees"])
                    except ValueError:
                        row["num_employees"] = None
                else:
                    row["num_employees"] = None
                records.append(row)
    return records


def find_union_link(cur, affiliation_code, local_number, state):
    """
    Find the best matching union in unions_master.
    Returns (f_num, union_name, aff_abbr, local_number) or (None, None, None, None).
    """
    # Skip for unaffiliated/independent
    if affiliation_code in ("UNAFF", None, ""):
        return None, None, None, None

    # Strategy 1: Exact match on aff_abbr + local_number + state
    if local_number:
        cur.execute("""
            SELECT f_num, union_name, aff_abbr, local_number
            FROM unions_master
            WHERE aff_abbr = %s AND local_number = %s AND state = %s
            ORDER BY members DESC NULLS LAST
            LIMIT 1
        """, (affiliation_code, str(local_number), state))
        row = cur.fetchone()
        if row:
            return row

    # Strategy 2: aff_abbr + state (largest local in state)
    if state and state != "US":
        cur.execute("""
            SELECT f_num, union_name, aff_abbr, local_number
            FROM unions_master
            WHERE aff_abbr = %s AND state = %s
            ORDER BY members DESC NULLS LAST
            LIMIT 1
        """, (affiliation_code, state))
        row = cur.fetchone()
        if row:
            return row

    # Strategy 3: aff_abbr only (largest national/international)
    cur.execute("""
        SELECT f_num, union_name, aff_abbr, local_number
        FROM unions_master
        WHERE aff_abbr = %s
        ORDER BY members DESC NULLS LAST
        LIMIT 1
    """, (affiliation_code,))
    row = cur.fetchone()
    if row:
        return row

    return None, None, None, None


def determine_source_type(record):
    """Determine source_type based on record characteristics."""
    notes = (record.get("notes") or "").lower()
    source = (record.get("source_description") or "").lower()

    if "perb" in notes or "perb" in source:
        return "STATE_PERB"
    if "voluntary" in source or "voluntarily" in source:
        return "UNION_WEBSITE"
    if "news" in source or "press" in source:
        return "NEWS_SCRAPE"
    return "WEB_RESEARCH"


def insert_records(conn, records):
    """Insert NEW records into manual_employers with union linkage."""
    cur = conn.cursor()

    # Get current max id
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM manual_employers")
    next_id = cur.fetchone()[0] + 1

    inserted = 0
    skipped = 0
    union_linked = 0

    for record in records:
        employer_name = record["employer_name"]
        name_normalized = normalize_employer_name(employer_name, "aggressive")
        city = record.get("city") or ""
        state = record.get("state") or ""
        union_name = record.get("union_name") or ""
        affiliation = record.get("affiliation_code") or ""
        local_number = record.get("local_number") or None
        num_employees = record.get("num_employees")
        recognition_type = record.get("recognition_type") or ""
        recognition_date = record.get("recognition_date") or None
        naics_sector = record.get("naics_sector") or ""
        source_description = record.get("source_description") or ""
        notes = record.get("notes") or ""
        source_type = determine_source_type(record)

        # Check for duplicates by normalized name + state
        cur.execute("""
            SELECT id FROM manual_employers
            WHERE employer_name_normalized = %s AND state = %s
            LIMIT 1
        """, (name_normalized, state))
        if cur.fetchone():
            skipped += 1
            continue

        # Find union link
        f_num, linked_union_name, linked_aff, linked_local = find_union_link(
            cur, affiliation, local_number, state
        )
        if f_num:
            union_linked += 1

        # Parse recognition_date
        rec_date = None
        if recognition_date:
            try:
                rec_date = datetime.strptime(recognition_date, "%Y-%m-%d").date()
            except ValueError:
                rec_date = None

        # Build notes with union linkage info
        full_notes = notes
        if f_num:
            full_notes += f" | Linked to unions_master f_num={f_num} ({linked_union_name})"

        cur.execute("""
            INSERT INTO manual_employers (
                id, employer_name, employer_name_normalized, city, state,
                union_name, affiliation, local_number, num_employees,
                recognition_type, recognition_date, naics_sector,
                source_url, source_type, verification_status, notes,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                NOW(), NOW()
            )
        """, (
            next_id, employer_name, name_normalized, city, state,
            union_name, affiliation, local_number, num_employees,
            recognition_type, rec_date, naics_sector,
            source_description, source_type, "auto_verified", full_notes,
        ))

        next_id += 1
        inserted += 1

    conn.commit()
    return inserted, skipped, union_linked


def print_post_summary(conn):
    """Print summary after insertion."""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM manual_employers")
    total = cur.fetchone()[0]

    print(f"\nTotal manual_employers records: {total}")

    # By source_type (new records)
    cur.execute("""
        SELECT source_type, COUNT(*), SUM(COALESCE(num_employees, 0))
        FROM manual_employers
        WHERE source_type IN ('NEWS_SCRAPE', 'WEB_RESEARCH', 'UNION_WEBSITE', 'STATE_PERB')
        GROUP BY source_type
        ORDER BY COUNT(*) DESC
    """)
    print("\nNew records by source type:")
    for r in cur.fetchall():
        print(f"  {r[0]:<20s} {r[1]:>5d} records, {r[2]:>10,d} workers")

    # By affiliation (new records)
    cur.execute("""
        SELECT affiliation, COUNT(*), SUM(COALESCE(num_employees, 0))
        FROM manual_employers
        WHERE created_at > NOW() - INTERVAL '1 hour'
        GROUP BY affiliation
        ORDER BY COUNT(*) DESC
        LIMIT 15
    """)
    print("\nJust-inserted records by affiliation:")
    for r in cur.fetchall():
        print(f"  {r[0] or 'NULL':<15s} {r[1]:>5d} records, {r[2]:>10,d} workers")

    # By state (new records)
    cur.execute("""
        SELECT state, COUNT(*), SUM(COALESCE(num_employees, 0))
        FROM manual_employers
        WHERE created_at > NOW() - INTERVAL '1 hour'
        GROUP BY state
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    print("\nJust-inserted records by state:")
    for r in cur.fetchall():
        print(f"  {r[0] or 'NULL':<5s} {r[1]:>5d} records, {r[2]:>10,d} workers")

    # By recognition_type (new records)
    cur.execute("""
        SELECT recognition_type, COUNT(*)
        FROM manual_employers
        WHERE created_at > NOW() - INTERVAL '1 hour'
        GROUP BY recognition_type
        ORDER BY COUNT(*) DESC
    """)
    print("\nJust-inserted records by recognition type:")
    for r in cur.fetchall():
        print(f"  {r[0] or 'NULL':<25s} {r[1]:>5d}")


def main():
    print("=" * 60)
    print("INSERT NEW EVENTS - Script 3 of 3")
    print("=" * 60)

    records = load_new_records(INPUT_CSV)
    print(f"\nLoaded {len(records)} NEW records from crosscheck report")

    if not records:
        print("No new records to insert. Done.")
        return

    conn = get_connection()

    # Get current count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM manual_employers")
    before_count = cur.fetchone()[0]
    print(f"Current manual_employers count: {before_count}")

    # Insert
    inserted, skipped, union_linked = insert_records(conn, records)

    print(f"\nInsertion Results:")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (duplicate): {skipped}")
    print(f"  Union-linked: {union_linked} of {inserted} ({100*union_linked//max(inserted,1)}%)")

    # Post-insert summary
    print_post_summary(conn)

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
