"""
Backfill `master_employers.naics` from linked source systems.

Why this exists: 60.9% of all masters and **98.1% of SEC-linked masters**
have `naics IS NULL`. The V12 demographics service requires NAICS for its
county x NAICS4 lookups; without it, V12 silently falls back to raw ACS
state averages. So most public-company profiles that LOOK like they
should get the V12 treatment instead get the lowest-quality (RED tier)
ACS fallback.

Two backfill paths, applied in order. Each only fills rows where the
existing `naics` is NULL, so re-runs are safe and the script is
idempotent.

  1. Mergent path: master has a `mergent` source link AND mergent_employers
     has a non-NULL `naics_primary` for that linked record. ~34K masters
     recoverable via this path.

  2. SEC SIC -> NAICS path: master has a `sec` source link AND
     sec_companies.sic_code is non-NULL AND naics_sic_crosswalk has a
     mapping for that SIC. When a SIC maps to multiple NAICS in the
     crosswalk, picks MIN(naics_2002_code) deterministically (the most-
     generic / parent NAICS). ~500K masters recoverable via this path.

Usage:
    py scripts/maintenance/backfill_master_naics.py            # do it
    py scripts/maintenance/backfill_master_naics.py --dry-run  # measure only

Exit codes:
    0  Success.
    2  DB unreachable.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from db_config import get_connection
except Exception as exc:  # pragma: no cover
    print(f"ERROR: cannot import db_config: {exc}", file=sys.stderr)
    sys.exit(2)


def measure_coverage(cur) -> tuple[int, int, int]:
    """Returns (total_masters, with_naics, sec_with_naics)."""
    cur.execute("SELECT COUNT(*) FILTER (WHERE naics IS NOT NULL), COUNT(*) FROM master_employers")
    row = cur.fetchone()
    if isinstance(row, dict):
        with_naics, total = int(row.get("count") or 0), int(row.get("count_1") or 0)
    else:
        with_naics, total = int(row[0] or 0), int(row[1] or 0)
    cur.execute(
        """
        SELECT COUNT(*) FROM master_employers m
        WHERE m.naics IS NOT NULL
          AND EXISTS (SELECT 1 FROM master_employer_source_ids s
                      WHERE s.master_id = m.master_id AND s.source_system = 'sec')
        """
    )
    row = cur.fetchone()
    sec_with = int((row[0] if isinstance(row, tuple) else row.get("count")) or 0)
    return total, with_naics, sec_with


# ---- Path 1: Mergent ----

PATH_MERGENT_SQL = """
WITH mergent_naics AS (
    SELECT
        s.master_id,
        -- A small number of Mergent rows hold a comma-separated list of
        -- multiple NAICS codes (e.g. '335121, 335122'). Take just the
        -- first one and trim. master_employers.naics is VARCHAR(10) so
        -- a 6-digit code fits cleanly; longer concatenations would
        -- truncate the column on UPDATE.
        MIN(TRIM(SPLIT_PART(
            COALESCE(me.naics_primary, me.naics_secondary), ',', 1))) AS naics
    FROM master_employer_source_ids s
    JOIN mergent_employers me
        ON me.id::text = s.source_id OR me.duns = s.source_id
    WHERE s.source_system = 'mergent'
      AND COALESCE(me.naics_primary, me.naics_secondary) IS NOT NULL
    GROUP BY s.master_id
)
UPDATE master_employers m
SET naics = mn.naics, updated_at = NOW()
FROM mergent_naics mn
WHERE m.master_id = mn.master_id
  AND m.naics IS NULL
  AND mn.naics IS NOT NULL
  AND LENGTH(mn.naics) <= 10
"""


# ---- Path 2: SEC SIC -> NAICS crosswalk ----

PATH_SEC_SIC_SQL = """
WITH sec_naics AS (
    SELECT
        s.master_id,
        -- Pick the most-generic NAICS for this SIC (MIN gives the
        -- alphabetically/numerically first when a SIC maps to multiple).
        MIN(x.naics_2002_code) AS naics
    FROM master_employer_source_ids s
    JOIN sec_companies sc ON sc.cik::text = s.source_id
    JOIN naics_sic_crosswalk x ON x.sic_code = sc.sic_code
    WHERE s.source_system = 'sec'
      AND sc.sic_code IS NOT NULL
      AND sc.sic_code <> '0000'  -- "no SIC" sentinel
      AND x.naics_2002_code IS NOT NULL
    GROUP BY s.master_id
)
UPDATE master_employers m
SET naics = sn.naics, updated_at = NOW()
FROM sec_naics sn
WHERE m.master_id = sn.master_id
  AND m.naics IS NULL
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Measure recoverable counts without writing.",
    )
    args = parser.parse_args()

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"ERROR: db connect: {exc}", file=sys.stderr)
        return 2

    cur = conn.cursor()

    total, with_naics, sec_with = measure_coverage(cur)
    pct = 100.0 * with_naics / total if total else 0
    sec_pct = 0
    cur.execute(
        "SELECT COUNT(DISTINCT master_id) FROM master_employer_source_ids "
        "WHERE source_system = 'sec'"
    )
    row = cur.fetchone()
    sec_total = int((row[0] if isinstance(row, tuple) else row.get("count")) or 0)
    sec_pct = 100.0 * sec_with / sec_total if sec_total else 0

    print("Before backfill:")
    print(f"  master_employers total: {total:,}")
    print(f"  with NAICS:             {with_naics:,} ({pct:.1f}%)")
    print(f"  SEC-linked with NAICS:  {sec_with:,} of {sec_total:,} ({sec_pct:.1f}%)")
    print()

    if args.dry_run:
        # Measure-only: count rows that WOULD be filled
        cur.execute(
            """
            SELECT COUNT(DISTINCT s.master_id)
            FROM master_employer_source_ids s
            JOIN mergent_employers me
                ON me.id::text = s.source_id OR me.duns = s.source_id
            JOIN master_employers m ON m.master_id = s.master_id
            WHERE s.source_system = 'mergent'
              AND COALESCE(me.naics_primary, me.naics_secondary) IS NOT NULL
              AND m.naics IS NULL
            """
        )
        row = cur.fetchone()
        merg_n = int((row[0] if isinstance(row, tuple) else row.get("count")) or 0)
        cur.execute(
            """
            SELECT COUNT(DISTINCT s.master_id)
            FROM master_employer_source_ids s
            JOIN sec_companies sc ON sc.cik::text = s.source_id
            JOIN naics_sic_crosswalk x ON x.sic_code = sc.sic_code
            JOIN master_employers m ON m.master_id = s.master_id
            WHERE s.source_system = 'sec'
              AND sc.sic_code IS NOT NULL AND sc.sic_code <> '0000'
              AND x.naics_2002_code IS NOT NULL
              AND m.naics IS NULL
            """
        )
        row = cur.fetchone()
        sec_n = int((row[0] if isinstance(row, tuple) else row.get("count")) or 0)
        print(f"Dry-run: would fill {merg_n:,} via Mergent, then up to {sec_n:,} via SEC SIC")
        print("(SEC count overlaps with Mergent — the second path only runs on rows still NULL)")
        conn.close()
        return 0

    # Path 1: Mergent
    print("Path 1: Mergent backfill...")
    t0 = time.time()
    cur.execute(PATH_MERGENT_SQL)
    merg_updated = cur.rowcount
    conn.commit()
    print(f"  -> {merg_updated:,} rows updated in {time.time() - t0:.1f}s")

    # Path 2: SEC SIC
    print("Path 2: SEC SIC -> NAICS backfill...")
    t0 = time.time()
    cur.execute(PATH_SEC_SIC_SQL)
    sec_updated = cur.rowcount
    conn.commit()
    print(f"  -> {sec_updated:,} rows updated in {time.time() - t0:.1f}s")

    total2, with_naics2, sec_with2 = measure_coverage(cur)
    pct2 = 100.0 * with_naics2 / total2 if total2 else 0
    sec_pct2 = 100.0 * sec_with2 / sec_total if sec_total else 0
    print()
    print("After backfill:")
    print(f"  with NAICS:             {with_naics2:,} ({pct2:.1f}%)  +{with_naics2 - with_naics:,}")
    print(f"  SEC-linked with NAICS:  {sec_with2:,} of {sec_total:,} ({sec_pct2:.1f}%)  +{sec_with2 - sec_with:,}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
