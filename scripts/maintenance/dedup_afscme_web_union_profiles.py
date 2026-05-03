"""
Dedup AFSCME legacy rows in web_union_profiles.

The AFSCME scraper shipped before the upsert pattern was dedup-aware, so it
created 58 groups of (parent_union='AFSCME', local_number, state) triples
with 2-3 rows each (138 extras total). All newer scrapers (IBT, CWA, IBEW,
USW, APWU, SEIU) use SELECT-then-UPDATE pattern and don't create duplicates.

Strategy per dup group: keep the row with the latest `last_scraped`
(falling back to `created_at`, then highest `id`). Merge non-NULL fields
from the losers into the winner. Merge `extra_data` as a JSON object union
(winner's keys win on conflict). Delete losers.

Usage:
    py -u scripts/maintenance/dedup_afscme_web_union_profiles.py --dry-run
    py -u scripts/maintenance/dedup_afscme_web_union_profiles.py --commit
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

PARENT = "AFSCME"

# Columns we try to backfill from losers into the winner when winner is NULL.
BACKFILL_COLS = [
    "website_url", "phone", "fax", "email", "address", "officers",
    "facebook", "source_directory_url", "f_num", "match_status",
    "scrape_status", "last_scraped", "raw_text", "raw_text_about",
    "raw_text_contracts", "raw_text_news",
]


def find_duplicate_groups(cur) -> list[tuple]:
    """Return list of (local_number, state) dup keys for AFSCME."""
    cur.execute(
        """SELECT local_number, state FROM web_union_profiles
             WHERE parent_union = %s
             GROUP BY local_number, state
             HAVING COUNT(*) > 1
             ORDER BY local_number, state""",
        (PARENT,),
    )
    return cur.fetchall()


def merge_group(cur, local_number, state, dry_run: bool) -> dict:
    """Pick a winner, backfill its nulls from losers, delete losers. Returns counts."""
    # All rows for this group, newest winner-first
    cur.execute(
        """SELECT id, """ + ", ".join(BACKFILL_COLS) + """, extra_data,
                  last_scraped, created_at
           FROM web_union_profiles
           WHERE parent_union = %s AND local_number IS NOT DISTINCT FROM %s
             AND state IS NOT DISTINCT FROM %s
           ORDER BY last_scraped DESC NULLS LAST, created_at DESC NULLS LAST, id DESC""",
        (PARENT, local_number, state),
    )
    rows = cur.fetchall()
    if len(rows) <= 1:
        return {"action": "skip"}

    winner = rows[0]
    loser_ids = [r[0] for r in rows[1:]]
    winner_id = winner[0]

    # Build backfill updates: take winner's NULLs and fill from first loser with a non-NULL
    updates: dict[str, object] = {}
    for idx, col in enumerate(BACKFILL_COLS, start=1):
        if winner[idx] in (None, ""):
            for loser in rows[1:]:
                if loser[idx] not in (None, ""):
                    updates[col] = loser[idx]
                    break

    # Merge extra_data: union of JSON objects (winner wins on key conflict)
    winner_extra = winner[len(BACKFILL_COLS) + 1] or {}
    merged_extra = dict(winner_extra) if isinstance(winner_extra, dict) else {}
    for loser in rows[1:]:
        lextra = loser[len(BACKFILL_COLS) + 1] or {}
        if isinstance(lextra, dict):
            for k, v in lextra.items():
                merged_extra.setdefault(k, v)

    if merged_extra != (winner_extra if isinstance(winner_extra, dict) else {}):
        updates["extra_data"] = merged_extra

    if dry_run:
        return {
            "action": "dry",
            "winner_id": winner_id,
            "loser_ids": loser_ids,
            "backfill_cols": list(updates.keys()),
        }

    # Apply backfill
    if updates:
        set_clauses = []
        params = []
        for col, val in updates.items():
            if col == "extra_data":
                set_clauses.append(f"{col} = %s::jsonb")
                params.append(json.dumps(val))
            else:
                set_clauses.append(f"{col} = %s")
                params.append(val)
        params.append(winner_id)
        cur.execute(
            f"UPDATE web_union_profiles SET {', '.join(set_clauses)} WHERE id = %s",
            params,
        )

    # Reparent child rows in all FK tables (winner gets the union of children).
    # Some child tables have UNIQUE constraints like (profile_id, name) that
    # collide if the winner already has the same row — in those cases we
    # simply delete the loser's duplicate child rather than reparent it.
    # Process FK tables in topological order (leaves first, then parents).
    # web_union_pdf_links.page_id -> web_union_pages.id, so pdf_links must be
    # handled before we can delete/reparent rows in pages.
    for table, fk_col, uniq_cols in [
        ("web_union_contracts", "web_profile_id", None),
        ("web_union_employers", "web_profile_id", ["employer_name_clean"]),
        ("web_union_membership", "web_profile_id", None),
        ("web_union_news", "web_profile_id", None),
        ("web_union_pdf_links", "profile_id", ["pdf_url"]),
        ("web_union_pages", "web_profile_id", ["page_url"]),
    ]:
        if uniq_cols:
            # If deleting a loser's page would orphan pdf_links.page_id, cascade
            # those pdf_link rows first — they point to a page that's about to
            # be collapsed into the winner's equivalent page anyway.
            if table == "web_union_pages":
                cur.execute(
                    """DELETE FROM web_union_pdf_links
                       WHERE page_id IN (
                           SELECT id FROM web_union_pages
                           WHERE web_profile_id = ANY(%s)
                             AND page_url IN (
                                 SELECT page_url FROM web_union_pages
                                 WHERE web_profile_id = %s
                             )
                       )""",
                    (loser_ids, winner_id),
                )
            uniq_sel = ", ".join(uniq_cols)
            cur.execute(
                f"DELETE FROM {table} "
                f"WHERE {fk_col} = ANY(%s) "
                f"  AND ({uniq_sel}) IN ("
                f"      SELECT {uniq_sel} FROM {table} WHERE {fk_col} = %s"
                f"  )",
                (loser_ids, winner_id),
            )
        cur.execute(
            f"UPDATE {table} SET {fk_col} = %s "
            f"WHERE {fk_col} = ANY(%s)",
            (winner_id, loser_ids),
        )

    # Delete losers
    cur.execute(
        "DELETE FROM web_union_profiles WHERE id = ANY(%s)", (loser_ids,),
    )
    return {
        "action": "merged",
        "winner_id": winner_id,
        "loser_ids": loser_ids,
        "backfill_cols": list(updates.keys()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--commit", action="store_true",
                    help="Actually delete losers (opposite of --dry-run)")
    args = ap.parse_args()
    dry = not args.commit

    conn = get_connection()
    cur = conn.cursor()

    groups = find_duplicate_groups(cur)
    print(f"[INFO] {len(groups)} duplicate groups for {PARENT}")
    if not groups:
        conn.close()
        return 0

    total_losers = 0
    backfill_totals: dict[str, int] = {}
    for local_number, state in groups:
        result = merge_group(cur, local_number, state, dry_run=dry)
        if result["action"] in ("dry", "merged"):
            total_losers += len(result["loser_ids"])
            for col in result["backfill_cols"]:
                backfill_totals[col] = backfill_totals.get(col, 0) + 1
        if result["action"] == "merged":
            pass  # side effects applied

    print(f"[RESULT] {'would remove' if dry else 'removed'} "
          f"{total_losers} loser rows across {len(groups)} groups")
    if backfill_totals:
        print("[BACKFILL] columns filled from losers:")
        for col, n in sorted(backfill_totals.items(), key=lambda x: -x[1]):
            print(f"  {col:25s} {n} groups")

    if dry:
        print("\n[DRY] Use --commit to apply.")
        conn.rollback()
    else:
        conn.commit()
        print("[COMMIT] Applied.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
