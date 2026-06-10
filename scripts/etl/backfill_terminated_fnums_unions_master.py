"""
Backfill terminated OLMS f_nums into unions_master as inactive entries.

Background
----------
138 f_nums are referenced by `f7_union_employer_relations` (344 rows / 325
employers / 19,155 BU workers) but have no row in `unions_master`. The
2026-05-12 investigation
(docs/scratch/138_unresolved_f_nums_investigation_2026_05_12.md) confirmed
all 138 are present in the OLMS public-filer list as `terminated:'T'` with
termDates between 2000 and 2011.

This script INSERTs them into unions_master with `is_likely_inactive=TRUE`
and the OLMS-provided affiliation/designation/term_date, so the legacy F-7
references resolve cleanly without falsely inflating any parent federation's
employer counts.

Recommendation source: T5 from 2026-05-12 morning parallel sweep.

Source data
-----------
- docs/scratch/olms_fnum_lookup.json (35,268 records, dict keyed by f_num str)
  Each record carries: fNum, affAbbr, affOrgName, designation, desigNum,
  desigName, city, state, terminated, termDate (ms-since-epoch), yrCovered,
  formFiled, members, etc.

Usage
-----
    py scripts/etl/backfill_terminated_fnums_unions_master.py            # commit (default)
    py scripts/etl/backfill_terminated_fnums_unions_master.py --dry-run  # no writes

Idempotency
-----------
INSERT ... ON CONFLICT (f_num) DO NOTHING. Re-runs produce 0 new rows.

# [plumbing]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOOKUP = PROJECT_ROOT / "docs" / "scratch" / "olms_fnum_lookup.json"


def _ms_to_date(ms: Any) -> date | None:
    """Convert OLMS millis-since-epoch to a Python date (UTC)."""
    if ms is None or ms == "":
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc).date()
    except (TypeError, ValueError):
        return None


def _clean_designation(designation: str | None) -> str | None:
    """OLMS designation strings are often padded with trailing spaces."""
    if designation is None:
        return None
    s = designation.strip()
    return s or None


# unions_master column-length ceilings (matches the live DB schema; see the
# investigation doc + information_schema). Anything longer is truncated
# rather than rejected — the lossy chars are always trailing whitespace or
# common-noun text (e.g. "JOINT PROTECTIVE BOARD" -> "JOINT PROTECTIVE BOA").
COL_MAX = {
    "union_name": 500,
    "aff_abbr": 50,
    "city": 100,
    "local_number": 50,
    "desig_name": 20,
}


def _trunc(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    limit = COL_MAX.get(key)
    if limit and len(value) > limit:
        return value[:limit]
    return value


def _safe_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _build_union_name(rec: dict[str, Any]) -> str:
    """Compose a human-readable union_name from OLMS affOrgName + designation.

    e.g. "TEAMSTERS LU 478", "NURSES ASN, AMERICAN, IND LU 296".
    """
    org = (rec.get("affOrgName") or "").strip()
    desig = _clean_designation(rec.get("designation")) or ""
    parts = [p for p in (org, desig) if p]
    return " ".join(parts).strip() or rec.get("affAbbr", "") or f"UNION {rec['fNum']}"


def fetch_current_orphans(conn) -> set[int]:
    """Return the set of f_nums referenced by f7_union_employer_relations
    but absent from unions_master.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT r.union_file_number AS fnum
            FROM f7_union_employer_relations r
            LEFT JOIN unions_master um ON um.f_num::int = r.union_file_number
            WHERE r.union_file_number IS NOT NULL AND um.f_num IS NULL
            """
        )
        return {row[0] for row in cur.fetchall()}


def ensure_columns(conn) -> None:
    """Make sure is_likely_inactive + term_date exist on unions_master."""
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE unions_master "
            "ADD COLUMN IF NOT EXISTS is_likely_inactive BOOLEAN DEFAULT FALSE"
        )
        cur.execute(
            "ALTER TABLE unions_master ADD COLUMN IF NOT EXISTS term_date DATE"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_unions_master_inactive "
            "ON unions_master (is_likely_inactive) "
            "WHERE is_likely_inactive = TRUE"
        )
    conn.commit()


def load_olms_lookup(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"OLMS lookup not found at {path}. "
            "See docs/scratch/138_unresolved_f_nums_investigation_2026_05_12.md."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_rows(
    orphans: set[int], olms: dict[str, dict[str, Any]]
) -> tuple[list[tuple], list[int]]:
    """Return (rows_to_insert, fnums_missing_from_olms)."""
    rows: list[tuple] = []
    missing: list[int] = []
    for fnum in sorted(orphans):
        rec = olms.get(str(fnum))
        if not rec:
            missing.append(fnum)
            continue
        rows.append(
            (
                str(fnum),                              # f_num (varchar)
                _trunc(_build_union_name(rec), "union_name"),  # union_name
                _trunc((rec.get("affAbbr") or "").strip() or None, "aff_abbr"),
                _safe_int(rec.get("members")),           # members
                _safe_int(rec.get("yrCovered")),         # yr_covered
                _trunc((rec.get("city") or "").strip() or None, "city"),
                (rec.get("state") or "").strip() or None,  # state (CHAR)
                _safe_int(rec.get("yrCovered")),         # source_year
                _trunc(_clean_designation(rec.get("desigNum")), "local_number"),
                _trunc(_clean_designation(rec.get("desigName")), "desig_name"),
                True,                                     # is_likely_inactive
                _ms_to_date(rec.get("termDate")),         # term_date
            )
        )
    return rows, missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill the 138 OLMS-terminated f_nums into unions_master as "
            "is_likely_inactive=TRUE entries."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the insert and report counts; do not write to the DB.",
    )
    parser.add_argument(
        "--lookup",
        type=Path,
        default=DEFAULT_LOOKUP,
        help="Path to OLMS lookup JSON (default: docs/scratch/olms_fnum_lookup.json)",
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        # Step 1: schema
        if not args.dry_run:
            ensure_columns(conn)

        # Step 2: load OLMS lookup
        olms = load_olms_lookup(args.lookup)
        print("Loaded OLMS lookup: %d records" % len(olms))

        # Step 3: current orphan set
        orphans = fetch_current_orphans(conn)
        print("Current orphan f_nums (not in unions_master): %d" % len(orphans))

        # Step 4: counts before
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM unions_master")
            before_total = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM unions_master WHERE is_likely_inactive = TRUE"
            )
            before_inactive = cur.fetchone()[0]
            cur.execute(
                """
                SELECT COUNT(*) FROM f7_union_employer_relations r
                LEFT JOIN unions_master um ON um.f_num::int = r.union_file_number
                WHERE r.union_file_number IS NOT NULL AND um.f_num IS NULL
                """
            )
            before_orphan_rows = cur.fetchone()[0]

        print("Before:")
        print("  unions_master total:                 %d" % before_total)
        print("  unions_master is_likely_inactive:    %d" % before_inactive)
        print("  f7_union_employer_relations orphans: %d rows" % before_orphan_rows)

        # Step 5: build INSERT rows
        rows, missing = build_rows(orphans, olms)
        print("Rows to insert: %d  (missing from OLMS: %d)" % (len(rows), len(missing)))
        if missing:
            print("  WARNING: missing fnums =>", missing)

        if args.dry_run:
            print("\n[DRY-RUN] No DB changes. Would insert %d rows." % len(rows))
            # Show a sample
            for r in rows[:5]:
                print("  sample:", r)
            return 0

        # Step 6: INSERT idempotently
        # f_num is the PK, so ON CONFLICT (f_num) DO NOTHING is safe.
        inserted = 0
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO unions_master (
                    f_num, union_name, aff_abbr, members, yr_covered,
                    city, state, source_year,
                    local_number, desig_name,
                    is_likely_inactive, term_date
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s
                )
                ON CONFLICT (f_num) DO NOTHING
                """,
                rows,
            )
            inserted = cur.rowcount
        conn.commit()

        # Step 7: counts after
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM unions_master")
            after_total = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM unions_master WHERE is_likely_inactive = TRUE"
            )
            after_inactive = cur.fetchone()[0]
            cur.execute(
                """
                SELECT COUNT(*) FROM f7_union_employer_relations r
                LEFT JOIN unions_master um ON um.f_num::int = r.union_file_number
                WHERE r.union_file_number IS NOT NULL AND um.f_num IS NULL
                """
            )
            after_orphan_rows = cur.fetchone()[0]

        print("After:")
        print(
            "  unions_master total:                 %d  (+%d)"
            % (after_total, after_total - before_total)
        )
        print(
            "  unions_master is_likely_inactive:    %d  (+%d)"
            % (after_inactive, after_inactive - before_inactive)
        )
        print(
            "  f7_union_employer_relations orphans: %d rows  (-%d)"
            % (after_orphan_rows, before_orphan_rows - after_orphan_rows)
        )
        print("Rows newly inserted (cursor rowcount): %d" % inserted)

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
