"""
Sync NLRB data from SQLite database to PostgreSQL.

The SQLite database (nlrb.db) contains fresh NLRB data through 2026-03-02
across 14 tables. This script performs a diff-based sync: it identifies rows
present in SQLite but missing from PostgreSQL, and inserts only the delta.

For filings/cases, it also updates status fields on existing rows.

Usage:
    py scripts/etl/sync_nlrb_sqlite.py C:\\Users\\jakew\\Downloads\\nlrb.db
    py scripts/etl/sync_nlrb_sqlite.py C:\\Users\\jakew\\Downloads\\nlrb.db --commit
    py scripts/etl/sync_nlrb_sqlite.py C:\\Users\\jakew\\Downloads\\nlrb.db --commit --phase elections
"""
import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count(cur, table):
    cur.execute("SELECT COUNT(*) FROM %s" % table)
    return cur.fetchone()[0]


def _pg_case_numbers(pg_cur, table, col="case_number"):
    """Return set of existing case_numbers from a PG table."""
    pg_cur.execute("SELECT DISTINCT %s FROM %s" % (col, table))
    return {r[0] for r in pg_cur.fetchall()}


# ---------------------------------------------------------------------------
# Phase: cases (filing -> nlrb_cases)
# ---------------------------------------------------------------------------

def sync_cases(sqlite_cur, pg_conn, commit):
    """Sync filing table -> nlrb_cases. Dedup key: case_number (PK)."""
    pg_cur = pg_conn.cursor()

    existing = _pg_case_numbers(pg_cur, "nlrb_cases")
    print("  PG nlrb_cases: %d rows" % len(existing))

    sqlite_cur.execute("""
        SELECT case_number, region_assigned, case_type,
               date_filed, date_closed, status,
               date_filed, date_closed
        FROM filing
    """)
    rows = sqlite_cur.fetchall()
    print("  SQLite filing: %d rows" % len(rows))

    # Build new rows and update candidates
    new_rows = []
    seen_case_numbers = set()
    for r in rows:
        cn = r["case_number"]
        if cn in seen_case_numbers:
            continue
        seen_case_numbers.add(cn)
        if cn not in existing:
            # Parse region number from "Region 01, ..." or use NULL
            region_str = r["region_assigned"] or ""
            region_num = None
            if region_str.startswith("Region "):
                try:
                    region_num = int(region_str.split(",")[0].replace("Region ", "").strip())
                except (ValueError, IndexError):
                    pass
            # Parse case_year and case_seq from case_number (e.g. 01-RC-020966)
            parts = cn.split("-") if cn else []
            case_year = None
            case_seq = None
            if len(parts) == 3:
                try:
                    case_seq = int(parts[2])
                except ValueError:
                    pass
            case_type = r["case_type"]
            earliest = r["date_filed"]
            latest = r["date_closed"]
            new_rows.append((cn, region_num, case_type, case_year, case_seq,
                             earliest, latest))

    print("  New cases: %d" % len(new_rows))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_cases (case_number, region, case_type, case_year,
                                    case_seq, earliest_date, latest_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (case_number) DO NOTHING
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new cases inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new cases" % len(new_rows))

    # Update status: update latest_date for existing cases where SQLite has newer date
    update_count = 0
    if commit:
        for r in rows:
            cn = r["case_number"]
            latest = r["date_closed"]
            if cn in existing and latest:
                pg_cur.execute("""
                    UPDATE nlrb_cases SET latest_date = %s
                    WHERE case_number = %s
                      AND (latest_date IS NULL OR latest_date < %s)
                """, (latest, cn, latest))
                update_count += pg_cur.rowcount
        pg_conn.commit()
        print("  [COMMITTED] %d cases updated with newer latest_date" % update_count)
    else:
        print("  [DRY-RUN] Would check existing cases for status updates")

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: elections (election -> nlrb_elections)
# ---------------------------------------------------------------------------

def sync_elections(sqlite_cur, pg_conn, commit):
    """Sync election table -> nlrb_elections.

    SQLite election has election_id + case_number. PG nlrb_elections has a
    serial id PK. PG ballot_type is NULL for all existing rows, so dedup
    uses (case_number, election_date) only. We also backfill ballot_type
    on existing rows.
    """
    pg_cur = pg_conn.cursor()

    # Dedup key: (case_number, election_date) -- ballot_type is NULL in PG
    pg_cur.execute("SELECT case_number, election_date FROM nlrb_elections")
    existing = {(r[0], str(r[1]) if r[1] else None) for r in pg_cur.fetchall()}
    print("  PG nlrb_elections: %d rows (%d unique keys)" % (
        _count(pg_cur, "nlrb_elections"), len(existing)))

    sqlite_cur.execute("""
        SELECT case_number, date, ballot_type, unit_size, tally_type
        FROM election
    """)
    rows = sqlite_cur.fetchall()
    print("  SQLite election: %d rows" % len(rows))

    new_rows = []
    update_ballot_types = []  # (ballot_type, case_number, date) for backfill
    for r in rows:
        cn = r["case_number"]
        dt = r["date"]
        key = (cn, dt)
        if key not in existing:
            new_rows.append((
                cn,
                r["tally_type"],  # election_type (Initial/Runoff)
                dt,               # election_date
                r["ballot_type"],
                r["unit_size"],   # eligible_voters
                None,             # void_ballots
                None,             # challenges
                None,             # runoff_required
            ))
            existing.add(key)
        elif r["ballot_type"]:
            update_ballot_types.append((r["ballot_type"], cn, dt))

    print("  New elections: %d" % len(new_rows))
    print("  Existing elections with ballot_type backfill: %d" % len(update_ballot_types))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_elections (case_number, election_type, election_date,
                                        ballot_type, eligible_voters, void_ballots,
                                        challenges, runoff_required)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new elections inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new elections" % len(new_rows))

    # Backfill ballot_type on existing rows where it is NULL
    if update_ballot_types and commit:
        updated = 0
        for bt, cn, dt in update_ballot_types:
            pg_cur.execute("""
                UPDATE nlrb_elections SET ballot_type = %s
                WHERE case_number = %s AND election_date = %s
                  AND ballot_type IS NULL
            """, (bt, cn, dt))
            updated += pg_cur.rowcount
        pg_conn.commit()
        print("  [COMMITTED] %d elections updated with ballot_type" % updated)
    elif update_ballot_types and not commit:
        print("  [DRY-RUN] Would backfill ballot_type on %d elections" % len(update_ballot_types))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: participants (participant -> nlrb_participants)
# ---------------------------------------------------------------------------

def _clean_city(city):
    """Normalize city for dedup: treat known junk values as empty."""
    if not city or city == 'Charged Party Address City':
        return ''
    return city


def _clean_state(state):
    """Normalize state for dedup: treat known junk values as empty."""
    if not state or state == 'Charged Party Address State':
        return ''
    return state


def sync_participants(sqlite_cur, pg_conn, commit):
    """Sync participant -> nlrb_participants.

    Dedup by (case_number, participant_name, participant_type, city, state).
    PG had junk city/state values NULLed by clean_nlrb_participants.py, so
    we normalize junk values to empty for comparison.
    """
    pg_cur = pg_conn.cursor()

    # Build existing key set
    pg_cur.execute("""
        SELECT case_number, participant_name, participant_type,
               COALESCE(city, ''), COALESCE(state, '')
        FROM nlrb_participants
    """)
    existing = {(r[0], r[1], r[2], r[3], r[4]) for r in pg_cur.fetchall()}
    print("  PG nlrb_participants: %d unique keys" % len(existing))

    sqlite_cur.execute("""
        SELECT case_number, participant, type, subtype,
               address, address_1, address_2,
               city, state, zip, phone_number
        FROM participant
    """)
    rows = sqlite_cur.fetchall()
    print("  SQLite participant: %d rows" % len(rows))

    new_rows = []
    for r in rows:
        cn = r["case_number"]
        name = r["participant"]
        ptype = r["type"]
        if ptype == "None":
            ptype = ""
        city = _clean_city(r["city"])
        state = _clean_state(r["state"])
        key = (cn, name, ptype, city, state)
        if key not in existing:
            # Insert with cleaned values (NULL junk city/state like PG does)
            insert_city = r["city"] if r["city"] != 'Charged Party Address City' else None
            insert_state = r["state"] if r["state"] != 'Charged Party Address State' else None
            new_rows.append((
                cn, name, ptype if ptype else None, r["subtype"],
                r["address"], r["address_1"], r["address_2"],
                insert_city, insert_state, r["zip"], r["phone_number"],
            ))
            existing.add(key)

    print("  New participants: %d" % len(new_rows))

    if new_rows and commit:
        batch_size = 5000
        total_inserted = 0
        for i in range(0, len(new_rows), batch_size):
            batch = new_rows[i:i + batch_size]
            pg_cur.executemany("""
                INSERT INTO nlrb_participants (case_number, participant_name,
                    participant_type, participant_subtype,
                    address, address_1, address_2,
                    city, state, zip, phone_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, batch)
            total_inserted += len(batch)
            if i % 50000 == 0 and i > 0:
                print("    ... inserted %d / %d" % (total_inserted, len(new_rows)))
        pg_conn.commit()
        print("  [COMMITTED] %d new participants inserted" % total_inserted)
    elif not commit:
        print("  [DRY-RUN] Would insert %d new participants" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: tallies (tally -> nlrb_tallies)
# ---------------------------------------------------------------------------

def sync_tallies(sqlite_cur, pg_conn, commit):
    """Sync tally -> nlrb_tallies.

    SQLite tallies reference election_id, PG tallies reference case_number.
    We join through SQLite election table to get case_number.

    PG tally_type = "For"/"Against" (vote direction).
    SQLite tally_type = "Initial"/"Runoff" (election round).
    SQLite option = org name or "No union".

    Dedup by (case_number, labor_org_name, votes_for). PG stores tally_type
    as vote direction; SQLite "No union" -> "Against", org names -> "For".
    """
    pg_cur = pg_conn.cursor()

    # Build existing key set: (case_number, org_name, votes)
    pg_cur.execute("""
        SELECT case_number, COALESCE(labor_org_name, ''),
               COALESCE(votes_for, -1)
        FROM nlrb_tallies
    """)
    existing = {(r[0], r[1], r[2]) for r in pg_cur.fetchall()}
    print("  PG nlrb_tallies: %d unique keys" % len(existing))

    # Join SQLite tally with election to get case_number
    sqlite_cur.execute("""
        SELECT e.case_number, t.option AS labor_org_name, t.votes
        FROM tally t
        JOIN election e ON e.election_id = t.election_id
    """)
    rows = sqlite_cur.fetchall()
    print("  SQLite tally (joined): %d rows" % len(rows))

    new_rows = []
    for r in rows:
        cn = r["case_number"]
        org = r["labor_org_name"] or ""
        votes = r["votes"]
        key = (cn, org, votes if votes is not None else -1)
        if key not in existing:
            # Map direction: "No union" -> Against, everything else -> For
            if org.lower() == "no union":
                tally_type = "Against"
            else:
                tally_type = "For"
            is_winner = None
            new_rows.append((
                cn, r["labor_org_name"], None,  # labor_org_number
                votes, tally_type, is_winner,
            ))
            existing.add(key)

    print("  New tallies: %d" % len(new_rows))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_tallies (case_number, labor_org_name,
                labor_org_number, votes_for, tally_type, is_winner)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new tallies inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new tallies" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: docket (docket -> nlrb_docket)
# ---------------------------------------------------------------------------

def sync_docket(sqlite_cur, pg_conn, commit):
    """Sync docket -> nlrb_docket.

    Dedup by (case_number, docket_date, LEFT(docket_entry, 200)).
    """
    pg_cur = pg_conn.cursor()

    # Build existing key set -- truncate entry to 200 chars for matching
    pg_cur.execute("""
        SELECT case_number, docket_date, LEFT(docket_entry, 200)
        FROM nlrb_docket
    """)
    existing = {(r[0], str(r[1]) if r[1] else None, r[2]) for r in pg_cur.fetchall()}
    print("  PG nlrb_docket: %d unique keys" % len(existing))

    sqlite_cur.execute("""
        SELECT case_number, date, document, url
        FROM docket
    """)
    rows = sqlite_cur.fetchall()
    print("  SQLite docket: %d rows" % len(rows))

    new_rows = []
    for r in rows:
        cn = r["case_number"]
        dt = r["date"]
        entry = r["document"]
        entry_trunc = (entry or "")[:200]
        key = (cn, dt, entry_trunc)
        if key not in existing:
            new_rows.append((cn, entry, dt, r["url"]))
            existing.add(key)

    print("  New docket entries: %d" % len(new_rows))

    if new_rows and commit:
        batch_size = 5000
        total_inserted = 0
        for i in range(0, len(new_rows), batch_size):
            batch = new_rows[i:i + batch_size]
            pg_cur.executemany("""
                INSERT INTO nlrb_docket (case_number, docket_entry,
                    docket_date, document_id)
                VALUES (%s, %s, %s, %s)
            """, batch)
            total_inserted += len(batch)
            if i % 50000 == 0 and i > 0:
                print("    ... inserted %d / %d" % (total_inserted, len(new_rows)))
        pg_conn.commit()
        print("  [COMMITTED] %d new docket entries inserted" % total_inserted)
    elif not commit:
        print("  [DRY-RUN] Would insert %d new docket entries" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: allegations (allegation -> nlrb_allegations)
# ---------------------------------------------------------------------------

def sync_allegations(sqlite_cur, pg_conn, commit):
    """Sync allegation -> nlrb_allegations.

    SQLite allegation has (case_number, allegation) as text.
    PG has (case_number, allegation_number, section, allegation_text, allegation_status).
    The SQLite allegation text contains both section and text combined.

    Dedup by (case_number, allegation_text).
    """
    pg_cur = pg_conn.cursor()

    # Build existing key set
    pg_cur.execute("""
        SELECT case_number, COALESCE(allegation_text, '')
        FROM nlrb_allegations
    """)
    existing = {(r[0], r[1]) for r in pg_cur.fetchall()}
    print("  PG nlrb_allegations: %d unique keys" % len(existing))

    sqlite_cur.execute("SELECT case_number, allegation FROM allegation")
    rows = sqlite_cur.fetchall()
    print("  SQLite allegation: %d rows" % len(rows))

    new_rows = []
    # Track per-case allegation numbers for new rows
    case_alleg_counts = {}
    for r in rows:
        cn = r["case_number"]
        allg = r["allegation"] or ""
        key = (cn, allg)
        if key not in existing:
            # Parse section from allegation text (e.g. "8(a)(3) Changes in ...")
            section = None
            text = allg
            if allg and allg[0].isdigit():
                parts = allg.split(" ", 1)
                if len(parts) == 2:
                    section = parts[0]
                    text = parts[1]

            if cn not in case_alleg_counts:
                # Get max existing allegation_number for this case
                pg_cur.execute(
                    "SELECT COALESCE(MAX(allegation_number), 0) FROM nlrb_allegations WHERE case_number = %s",
                    (cn,)
                )
                case_alleg_counts[cn] = pg_cur.fetchone()[0]
            case_alleg_counts[cn] += 1

            new_rows.append((cn, case_alleg_counts[cn], section, text, None))
            existing.add(key)

    print("  New allegations: %d" % len(new_rows))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_allegations (case_number, allegation_number,
                section, allegation_text, allegation_status)
            VALUES (%s, %s, %s, %s, %s)
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new allegations inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new allegations" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: filings (filing -> nlrb_filings)
# ---------------------------------------------------------------------------

def sync_filings(sqlite_cur, pg_conn, commit):
    """Sync filing -> nlrb_filings.

    PG nlrb_filings has: case_number, filing_type, filing_date, filed_by,
    filing_description. SQLite filing has richer data. We map:
      case_type -> filing_type
      date_filed -> filing_date
      name -> filed_by
      status + reason_closed -> filing_description

    Dedup by (case_number, filing_date, filing_type).
    """
    pg_cur = pg_conn.cursor()

    pg_cur.execute("""
        SELECT case_number, COALESCE(filing_date::text, ''), COALESCE(filing_type, '')
        FROM nlrb_filings
    """)
    existing = {(r[0], r[1], r[2]) for r in pg_cur.fetchall()}
    print("  PG nlrb_filings: %d unique keys" % len(existing))

    sqlite_cur.execute("""
        SELECT case_number, case_type, date_filed, name,
               status, reason_closed
        FROM filing
    """)
    rows = sqlite_cur.fetchall()
    print("  SQLite filing: %d rows" % len(rows))

    new_rows = []
    for r in rows:
        cn = r["case_number"]
        ftype = r["case_type"] or ""
        fdate = r["date_filed"] or ""
        key = (cn, fdate, ftype)
        if key not in existing:
            desc_parts = []
            if r["status"]:
                desc_parts.append("Status: %s" % r["status"])
            if r["reason_closed"]:
                desc_parts.append("Reason closed: %s" % r["reason_closed"])
            desc = "; ".join(desc_parts) if desc_parts else None
            new_rows.append((cn, ftype, fdate or None, r["name"], desc))
            existing.add(key)

    print("  New filings: %d" % len(new_rows))

    if new_rows and commit:
        batch_size = 5000
        total_inserted = 0
        for i in range(0, len(new_rows), batch_size):
            batch = new_rows[i:i + batch_size]
            pg_cur.executemany("""
                INSERT INTO nlrb_filings (case_number, filing_type, filing_date,
                    filed_by, filing_description)
                VALUES (%s, %s, %s, %s, %s)
            """, batch)
            total_inserted += len(batch)
        pg_conn.commit()
        print("  [COMMITTED] %d new filings inserted" % total_inserted)
    elif not commit:
        print("  [DRY-RUN] Would insert %d new filings" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: election_results (election_result -> nlrb_election_results)
# ---------------------------------------------------------------------------

def sync_election_results(sqlite_cur, pg_conn, commit):
    """Sync election_result -> nlrb_election_results.

    PG election_results uses election_id as FK to nlrb_elections, but PG
    election IDs are auto-serial (starting ~66K) while existing result rows
    reference original SQLite IDs (1-33K). We track existing results by
    both PG ID and original SQLite ID ranges.

    For new elections (inserted by sync_elections), we map via case_number+date.
    """
    pg_cur = pg_conn.cursor()

    # Existing results by election_id
    pg_cur.execute("SELECT election_id FROM nlrb_election_results")
    existing_result_ids = {r[0] for r in pg_cur.fetchall()}
    print("  PG nlrb_election_results: %d rows" % len(existing_result_ids))

    # Build mapping: (case_number, date) -> PG election id
    pg_cur.execute("SELECT id, case_number, election_date FROM nlrb_elections")
    pg_elections_by_key = {}
    for r in pg_cur.fetchall():
        key = (r[1], str(r[2]) if r[2] else None)
        pg_elections_by_key[key] = r[0]

    # Also track which (case_number, date) combos already have results
    # by mapping existing result IDs back to case_number+date
    pg_cur.execute("""
        SELECT e.case_number, e.election_date
        FROM nlrb_election_results er
        JOIN nlrb_elections e ON e.id = er.election_id
    """)
    has_result_by_key = {(r[0], str(r[1]) if r[1] else None) for r in pg_cur.fetchall()}
    # Also include results that reference old-style IDs (SQLite election_id)
    # These won't join above but represent existing data
    existing_coverage = len(has_result_by_key)

    # If the FK join found nothing, it means results use original SQLite IDs.
    # In that case, build coverage from SQLite side.
    if existing_coverage == 0 and len(existing_result_ids) > 0:
        sqlite_cur.execute("SELECT election_id, case_number, date FROM election")
        sqlite_id_to_key = {r["election_id"]: (r["case_number"], r["date"])
                            for r in sqlite_cur.fetchall()}
        for eid in existing_result_ids:
            if eid in sqlite_id_to_key:
                has_result_by_key.add(sqlite_id_to_key[eid])

    print("  Elections with existing results: %d" % len(has_result_by_key))

    # SQLite election -> id mapping
    sqlite_cur.execute("SELECT election_id, case_number, date FROM election")
    sqlite_elections = {r["election_id"]: (r["case_number"], r["date"])
                        for r in sqlite_cur.fetchall()}

    sqlite_cur.execute("SELECT * FROM election_result")
    rows = sqlite_cur.fetchall()
    print("  SQLite election_result: %d rows" % len(rows))

    new_rows = []
    skipped = 0
    for r in rows:
        sid = r["election_id"]
        if sid not in sqlite_elections:
            skipped += 1
            continue
        cn, dt = sqlite_elections[sid]
        key = (cn, dt)
        # Skip if this election already has a result
        if key in has_result_by_key:
            skipped += 1
            continue
        # Find the PG election ID for this case_number+date
        pg_id = pg_elections_by_key.get(key)
        if pg_id is None:
            skipped += 1
            continue
        new_rows.append((
            pg_id,
            r["total_ballots_counted"],
            r["void_ballots"],
            r["challenged_ballots"],
            r["challenges_are_determinative"],
            r["runoff_required"],
            r["union_to_certify"],
        ))
        has_result_by_key.add(key)

    print("  New election results: %d (skipped %d)" % (len(new_rows), skipped))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_election_results (election_id, total_ballots_counted,
                void_ballots, challenged_ballots, challenges_determinative,
                runoff_required, certified_union)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (election_id) DO NOTHING
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new election results inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new election results" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: voting_units (voting_unit -> nlrb_voting_units)
# ---------------------------------------------------------------------------

def sync_voting_units(sqlite_cur, pg_conn, commit):
    """Sync voting_unit -> nlrb_voting_units.

    Dedup by (case_number, unit_id text match on unit_description).
    """
    pg_cur = pg_conn.cursor()

    pg_cur.execute("""
        SELECT case_number, COALESCE(unit_description, '')
        FROM nlrb_voting_units
    """)
    existing = {(r[0], r[1]) for r in pg_cur.fetchall()}
    print("  PG nlrb_voting_units: %d unique keys" % len(existing))

    sqlite_cur.execute("SELECT case_number, unit_id, description FROM voting_unit")
    rows = sqlite_cur.fetchall()
    print("  SQLite voting_unit: %d rows" % len(rows))

    new_rows = []
    for r in rows:
        cn = r["case_number"]
        desc = r["description"] or ""
        key = (cn, desc)
        if key not in existing:
            new_rows.append((cn, desc, None, None, None))
            existing.add(key)

    print("  New voting units: %d" % len(new_rows))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_voting_units (case_number, unit_description,
                included_job_classifications, excluded_job_classifications,
                unit_size)
            VALUES (%s, %s, %s, %s, %s)
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new voting units inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new voting units" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Phase: sought_units (sought_unit -> nlrb_sought_units)
# ---------------------------------------------------------------------------

def sync_sought_units(sqlite_cur, pg_conn, commit):
    """Sync sought_unit -> nlrb_sought_units.

    Dedup by (case_number, LEFT(unit_description, 200)).
    """
    pg_cur = pg_conn.cursor()

    pg_cur.execute("""
        SELECT case_number, LEFT(COALESCE(unit_description, ''), 200)
        FROM nlrb_sought_units
    """)
    existing = {(r[0], r[1]) for r in pg_cur.fetchall()}
    print("  PG nlrb_sought_units: %d unique keys" % len(existing))

    sqlite_cur.execute("SELECT case_number, unit_sought FROM sought_unit")
    rows = sqlite_cur.fetchall()
    print("  SQLite sought_unit: %d rows" % len(rows))

    new_rows = []
    for r in rows:
        cn = r["case_number"]
        desc = r["unit_sought"] or ""
        key = (cn, desc[:200])
        if key not in existing:
            new_rows.append((cn, desc, None, None, None))
            existing.add(key)

    print("  New sought units: %d" % len(new_rows))

    if new_rows and commit:
        pg_cur.executemany("""
            INSERT INTO nlrb_sought_units (case_number, unit_description,
                included_classifications, excluded_classifications,
                num_employees)
            VALUES (%s, %s, %s, %s, %s)
        """, new_rows)
        pg_conn.commit()
        print("  [COMMITTED] %d new sought units inserted" % len(new_rows))
    elif not commit:
        print("  [DRY-RUN] Would insert %d new sought units" % len(new_rows))

    pg_cur.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sync NLRB data from SQLite to PostgreSQL"
    )
    parser.add_argument("sqlite_path", help="Path to nlrb.db SQLite file")
    parser.add_argument("--commit", action="store_true",
                        help="Persist changes (default is dry-run)")
    parser.add_argument("--phase", default="all",
                        choices=["cases", "elections", "participants", "tallies",
                                 "docket", "allegations", "filings",
                                 "election_results", "voting_units",
                                 "sought_units", "all"],
                        help="Run specific phase only (default: all)")
    args = parser.parse_args()

    if not os.path.exists(args.sqlite_path):
        print("ERROR: SQLite file not found: %s" % args.sqlite_path)
        sys.exit(1)

    sqlite_conn = sqlite3.connect(args.sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = get_connection()

    _start = time.time()
    try:
        print("=" * 70)
        print("NLRB SQLite -> PostgreSQL Sync")
        print("Mode: %s" % ("COMMIT" if args.commit else "DRY-RUN"))
        print("SQLite: %s" % args.sqlite_path)
        print("=" * 70)

        phases = [
            ("cases", sync_cases),
            ("filings", sync_filings),
            ("elections", sync_elections),
            ("election_results", sync_election_results),
            ("participants", sync_participants),
            ("tallies", sync_tallies),
            ("docket", sync_docket),
            ("allegations", sync_allegations),
            ("voting_units", sync_voting_units),
            ("sought_units", sync_sought_units),
        ]

        if args.phase == "all":
            for name, func in phases:
                print("\n--- Phase: %s ---" % name)
                func(sqlite_cur, pg_conn, args.commit)
        else:
            for name, func in phases:
                if name == args.phase:
                    print("\n--- Phase: %s ---" % name)
                    func(sqlite_cur, pg_conn, args.commit)
                    break

        print("\n" + "=" * 70)
        print("Sync complete.")
        print("=" * 70)

        try:
            from etl_log import log_etl_run
            log_etl_run('nlrb', 'multiple', None, 'success',
                         'scripts/etl/sync_nlrb_sqlite.py',
                         duration_seconds=round(time.time() - _start, 2))
        except Exception as log_err:
            print("WARNING: ETL log failed: %s" % log_err)

    except Exception as e:
        pg_conn.rollback()
        try:
            from etl_log import log_etl_run
            log_etl_run('nlrb', 'multiple', None, 'error',
                         'scripts/etl/sync_nlrb_sqlite.py',
                         error_message=str(e),
                         duration_seconds=round(time.time() - _start, 2))
        except Exception:
            pass
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
