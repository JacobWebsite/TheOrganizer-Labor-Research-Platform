"""
Cross-Check Events Against Database - Script 2 of 3

Reads the catalog CSV from Script 1 and checks each event against 5 database
tables to determine if it's genuinely NEW or already captured:

1. manual_employers (432 records)
2. f7_employers_deduped (63K - private sector CBAs)
3. nlrb_elections + nlrb_participants (33K elections)
4. nlrb_voluntary_recognition
5. mergent_employers (14K sector targets)

Match status codes:
  ALREADY_MANUAL - Already in manual_employers
  IN_F7          - Has union contract in F-7
  IN_NLRB        - Election recorded in NLRB data
  IN_VR          - In voluntary recognition table
  IN_MERGENT     - In sector targets (can update has_union flag)
  NEW            - Not found anywhere -> insert into manual_employers
  PARTIAL        - Fuzzy match found, needs review
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection as _get_connection
from scripts.matching.normalizer import normalize_employer_name

INPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "organizing_events_catalog.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "crosscheck_report.csv")


def get_connection():
    return _get_connection()


def load_catalog(path):
    """Load events from catalog CSV."""
    events = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert num_employees to int
            if row.get("num_employees"):
                try:
                    row["num_employees"] = int(row["num_employees"])
                except ValueError:
                    row["num_employees"] = None
            else:
                row["num_employees"] = None
            events.append(row)
    return events


def check_manual_employers(cur, event):
    """Check if event already exists in manual_employers."""
    name_norm = normalize_employer_name(event["employer_name"], "aggressive")
    state = event["state"]

    # Check by normalized name + state
    cur.execute("""
        SELECT id, employer_name, city, state, affiliation
        FROM manual_employers
        WHERE LOWER(employer_name_normalized) = LOWER(%s)
          AND state = %s
        LIMIT 1
    """, (name_norm, state))
    row = cur.fetchone()
    if row:
        return "ALREADY_MANUAL", f"manual_employers.id={row[0]}: {row[1]} ({row[3]})"

    # Also check partial name match
    if len(name_norm) > 5:
        search_term = f"%{name_norm[:20]}%"
        cur.execute("""
            SELECT id, employer_name, city, state
            FROM manual_employers
            WHERE LOWER(employer_name_normalized) LIKE LOWER(%s)
              AND state = %s
            LIMIT 1
        """, (search_term, state))
        row = cur.fetchone()
        if row:
            return "ALREADY_MANUAL", f"manual_employers.id={row[0]}: {row[1]} ({row[3]})"

    return None, None


def check_f7_employers(cur, event):
    """Check if event employer has a union contract in f7_employers_deduped."""
    name_agg = normalize_employer_name(event["employer_name"], "aggressive")
    state = event["state"]

    if state == "US":
        # Aggregate records - skip state filter
        cur.execute("""
            SELECT employer_id, employer_name_aggressive, city, state
            FROM f7_employers_deduped
            WHERE employer_name_aggressive = %s
            LIMIT 1
        """, (name_agg,))
    else:
        cur.execute("""
            SELECT employer_id, employer_name_aggressive, city, state
            FROM f7_employers_deduped
            WHERE employer_name_aggressive = %s AND state = %s
            LIMIT 1
        """, (name_agg, state))

    row = cur.fetchone()
    if row:
        return "IN_F7", f"f7.employer_id={row[0]}: {row[1]} ({row[2]}, {row[3]})"

    # Try partial match - but only if name is specific enough (>= 3 significant words)
    words = [w for w in name_agg.split() if len(w) > 2]
    if len(words) >= 3:
        search = " ".join(words[:4])
        if len(search) < 12:
            return None, None
        if state == "US":
            cur.execute("""
                SELECT employer_id, employer_name_aggressive, city, state
                FROM f7_employers_deduped
                WHERE employer_name_aggressive LIKE %s
                LIMIT 3
            """, (f"{search}%",))
        else:
            cur.execute("""
                SELECT employer_id, employer_name_aggressive, city, state
                FROM f7_employers_deduped
                WHERE employer_name_aggressive LIKE %s AND state = %s
                LIMIT 3
            """, (f"{search}%", state))

        rows = cur.fetchall()
        if rows:
            desc = "; ".join(f"{r[1]} ({r[2]}, {r[3]})" for r in rows)
            return "IN_F7", f"f7 partial: {desc}"

    return None, None


def check_nlrb_elections(cur, event):
    """Check if employer appears in NLRB election records."""
    name_norm = normalize_employer_name(event["employer_name"], "aggressive")
    state = event["state"]

    # Use first 3+ significant words for LIKE matching to reduce false positives
    search_words = [w for w in name_norm.split() if len(w) > 2][:4]
    if not search_words:
        return None, None
    search_term = " ".join(search_words)
    # Require at least 6 chars to avoid broad false positives like "farms"
    if len(search_term) < 6:
        return None, None

    # Check nlrb_participants (Employer type) joined with elections
    if state == "US":
        cur.execute("""
            SELECT p.case_number, p.participant_name, p.city, p.state, e.election_date
            FROM nlrb_participants p
            JOIN nlrb_elections e ON p.case_number = e.case_number
            WHERE p.participant_type = 'Employer'
              AND LOWER(p.participant_name) LIKE %s
            ORDER BY e.election_date DESC NULLS LAST
            LIMIT 3
        """, (f"%{search_term}%",))
    else:
        cur.execute("""
            SELECT p.case_number, p.participant_name, p.city, p.state, e.election_date
            FROM nlrb_participants p
            JOIN nlrb_elections e ON p.case_number = e.case_number
            WHERE p.participant_type = 'Employer'
              AND LOWER(p.participant_name) LIKE %s
              AND p.state = %s
            ORDER BY e.election_date DESC NULLS LAST
            LIMIT 3
        """, (f"%{search_term}%", state))

    rows = cur.fetchall()
    if rows:
        desc = "; ".join(f"case={r[0]}: {r[1][:40]} ({r[2]}, {r[3]}, {r[4]})" for r in rows)
        return "IN_NLRB", f"nlrb: {desc}"

    return None, None


def check_voluntary_recognition(cur, event):
    """Check if employer appears in voluntary recognition table."""
    name_norm = normalize_employer_name(event["employer_name"], "aggressive")
    state = event["state"]

    if state == "US":
        cur.execute("""
            SELECT vr_case_number, employer_name, unit_city, unit_state, date_voluntary_recognition
            FROM nlrb_voluntary_recognition
            WHERE LOWER(employer_name_normalized) LIKE %s
            ORDER BY date_voluntary_recognition DESC NULLS LAST
            LIMIT 3
        """, (f"%{name_norm[:25]}%",))
    else:
        cur.execute("""
            SELECT vr_case_number, employer_name, unit_city, unit_state, date_voluntary_recognition
            FROM nlrb_voluntary_recognition
            WHERE LOWER(employer_name_normalized) LIKE %s
              AND unit_state = %s
            ORDER BY date_voluntary_recognition DESC NULLS LAST
            LIMIT 3
        """, (f"%{name_norm[:25]}%", state))

    rows = cur.fetchall()
    if rows:
        desc = "; ".join(f"vr={r[0]}: {r[1][:40]} ({r[2]}, {r[3]}, {r[4]})" for r in rows)
        return "IN_VR", f"vr: {desc}"

    return None, None


def check_mergent_employers(cur, event):
    """Check if employer appears in mergent_employers sector targets."""
    name_norm = normalize_employer_name(event["employer_name"], "aggressive")
    state = event["state"]

    if state == "US":
        cur.execute("""
            SELECT duns, company_name, city, state, has_union, sector_category
            FROM mergent_employers
            WHERE company_name_normalized = %s
            LIMIT 3
        """, (name_norm,))
    else:
        cur.execute("""
            SELECT duns, company_name, city, state, has_union, sector_category
            FROM mergent_employers
            WHERE company_name_normalized = %s AND state = %s
            LIMIT 3
        """, (name_norm, state))

    rows = cur.fetchall()
    if rows:
        desc = "; ".join(f"duns={r[0]}: {r[1]} ({r[2]}, {r[3]}, union={r[4]}, sector={r[5]})" for r in rows)
        return "IN_MERGENT", f"mergent: {desc}"

    return None, None


def crosscheck_event(cur, event):
    """Run all cross-checks on a single event. Returns (status, details)."""

    # Check in priority order
    # 1. manual_employers (already manually added)
    status, detail = check_manual_employers(cur, event)
    if status:
        return status, detail

    # 2. f7_employers_deduped (has union contract)
    status, detail = check_f7_employers(cur, event)
    if status:
        return status, detail

    # 3. NLRB elections
    status, detail = check_nlrb_elections(cur, event)
    if status:
        return status, detail

    # 4. Voluntary recognition
    status, detail = check_voluntary_recognition(cur, event)
    if status:
        return status, detail

    # 5. Mergent employers
    status, detail = check_mergent_employers(cur, event)
    if status:
        return status, detail

    # No match found
    return "NEW", "Not found in any database table"


def main():
    print("=" * 60)
    print("CROSS-CHECK EVENTS - Script 2 of 3")
    print("=" * 60)

    # Load catalog
    events = load_catalog(INPUT_CSV)
    print(f"\nLoaded {len(events)} events from catalog")

    conn = get_connection()
    cur = conn.cursor()

    # Cross-check each event
    results = []
    status_counts = {}

    for i, event in enumerate(events):
        status, detail = crosscheck_event(cur, event)
        event["match_status"] = status
        event["match_detail"] = detail
        results.append(event)

        status_counts[status] = status_counts.get(status, 0) + 1

        if (i + 1) % 20 == 0:
            print(f"  Processed {i+1}/{len(events)}...")

    print(f"\nProcessed all {len(events)} events")

    # Write results
    output_fields = [
        "employer_name", "employer_name_normalized", "city", "state",
        "union_name", "affiliation_code", "local_number",
        "num_employees", "recognition_type", "recognition_date",
        "naics_sector", "source_description", "notes", "agent_source",
        "match_status", "match_detail"
    ]

    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # Summary
    print(f"\nCross-check Results:")
    print(f"{'Status':<20s} {'Count':>6s} {'Workers':>10s}")
    print("-" * 40)
    for status in ["NEW", "IN_NLRB", "IN_F7", "IN_VR", "IN_MERGENT", "ALREADY_MANUAL", "PARTIAL"]:
        count = status_counts.get(status, 0)
        workers = sum(r.get("num_employees") or 0 for r in results if r["match_status"] == status)
        if count > 0:
            print(f"  {status:<18s} {count:>6d} {workers:>10,d}")

    total_new = status_counts.get("NEW", 0)
    new_workers = sum(r.get("num_employees") or 0 for r in results if r["match_status"] == "NEW")
    print(f"\n** {total_new} NEW records ready for insertion ({new_workers:,} workers) **")

    # Show some examples of each status
    print("\n--- Sample NEW records ---")
    new_recs = [r for r in results if r["match_status"] == "NEW"]
    for r in new_recs[:10]:
        print(f"  {r['employer_name'][:50]:<52s} {r['city']:<15s} {r['state']:<3s} {r['affiliation_code']:<8s} {r.get('num_employees') or 0:>6,d}")

    print(f"\n--- Sample MATCHED records ---")
    matched = [r for r in results if r["match_status"] != "NEW"]
    for r in matched[:10]:
        print(f"  [{r['match_status']}] {r['employer_name'][:45]:<47s} -> {(r['match_detail'] or '')[:60]}")

    print(f"\nReport written to: {OUTPUT_CSV}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
