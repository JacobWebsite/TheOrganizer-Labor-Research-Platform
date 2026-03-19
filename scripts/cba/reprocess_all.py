"""Batch reprocess all CBA contracts with updated rule engine.

Re-runs the article structure (step 3) and provision tagging (step 4)
for all or selected contracts, using the heading-first classification
and fragment merge-up logic.

Usage:
    py scripts/cba/reprocess_all.py --dry-run           # count-only for all contracts
    py scripts/cba/reprocess_all.py --cba-id 5 --dry-run # single contract dry run
    py scripts/cba/reprocess_all.py                      # full reprocess all
    py scripts/cba/reprocess_all.py --cba-id 5           # single contract
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db_config import get_connection
from scripts.cba.rule_engine import match_text_all_categories, populate_context


def get_all_cba_ids() -> list[int]:
    """Return all cba_ids that have full_text and structure_json."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cba_id FROM cba_documents "
                "WHERE full_text IS NOT NULL AND structure_json IS NOT NULL "
                "ORDER BY cba_id"
            )
            return [row[0] for row in cur.fetchall()]


def get_old_provision_count(cba_id: int) -> int:
    """Count existing provisions for a contract."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM cba_provisions WHERE cba_id = %s",
                [cba_id],
            )
            return cur.fetchone()[0]


def get_old_provision_breakdown(cba_id: int) -> dict[str, int]:
    """Get provision count by category for a contract."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, COUNT(*) FROM cba_provisions "
                "WHERE cba_id = %s GROUP BY category ORDER BY count DESC",
                [cba_id],
            )
            return {row[0]: row[1] for row in cur.fetchall()}


def reprocess_one(cba_id: int, dry_run: bool = False) -> dict:
    """Reprocess a single contract. Returns before/after stats."""
    # Module name starts with a digit, so use importlib
    import importlib
    _tag_mod = importlib.import_module("scripts.cba.04_tag_category")
    get_chunks_and_spans = _tag_mod.get_chunks_and_spans
    insert_provisions = _tag_mod.insert_provisions

    old_count = get_old_provision_count(cba_id)
    old_breakdown = get_old_provision_breakdown(cba_id)

    chunks, spans, text = get_chunks_and_spans(cba_id)
    if not chunks:
        return {
            "cba_id": cba_id,
            "old_count": old_count,
            "new_count": 0,
            "error": "No article structure found",
        }

    # Get page count for TOC/Index filter
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT page_count FROM cba_documents WHERE cba_id = %s",
                [cba_id],
            )
            row = cur.fetchone()
            total_pages = row[0] if row else None

    # Run rule engine with new heading-first logic
    matches = match_text_all_categories(
        chunks, min_confidence=0.50, total_pages=total_pages
    )
    populate_context(matches, text)

    new_count = len(matches)

    # Build new breakdown
    from collections import Counter
    new_breakdown = dict(Counter(m.category for m in matches))

    result = {
        "cba_id": cba_id,
        "old_count": old_count,
        "new_count": new_count,
        "delta": new_count - old_count,
        "old_breakdown": old_breakdown,
        "new_breakdown": new_breakdown,
        "chunks": len(chunks),
    }

    if not dry_run:
        # Delete existing provisions (reviews survive via ON DELETE SET NULL)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM cba_provisions WHERE cba_id = %s",
                    [cba_id],
                )
                conn.commit()

        # Insert new provisions
        inserted = insert_provisions(cba_id, matches, spans)
        result["inserted"] = inserted

        # Update document status
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cba_documents SET extraction_status = 'completed', "
                    "updated_at = NOW() WHERE cba_id = %s",
                    [cba_id],
                )
                conn.commit()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch reprocess CBA contracts with updated rule engine"
    )
    parser.add_argument(
        "--cba-id", type=int, help="Process a single contract (default: all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Count-only mode -- no database changes"
    )
    args = parser.parse_args()

    if args.cba_id:
        cba_ids = [args.cba_id]
    else:
        cba_ids = get_all_cba_ids()

    if not cba_ids:
        print("No contracts found with full_text and structure_json.")
        sys.exit(1)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"Reprocessing {len(cba_ids)} contract(s) [{mode}]")
    print("=" * 70)

    total_old = 0
    total_new = 0
    results = []

    for cba_id in cba_ids:
        print(f"\n  CBA {cba_id}...", end=" ", flush=True)
        try:
            result = reprocess_one(cba_id, dry_run=args.dry_run)
            results.append(result)
            total_old += result["old_count"]
            total_new += result["new_count"]

            delta = result.get("delta", 0)
            sign = "+" if delta >= 0 else ""
            print(f"{result['old_count']} -> {result['new_count']} ({sign}{delta})")

            if result.get("error"):
                print(f"    ERROR: {result['error']}")
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"cba_id": cba_id, "error": str(e), "old_count": 0, "new_count": 0})

    # Summary table
    print("\n" + "=" * 70)
    print(f"{'CBA':>6} | {'Old':>6} | {'New':>6} | {'Delta':>7} | Notes")
    print("-" * 70)
    for r in results:
        delta = r.get("delta", 0)
        sign = "+" if delta >= 0 else ""
        notes = r.get("error", "")
        print(f"{r['cba_id']:>6} | {r['old_count']:>6} | {r['new_count']:>6} | {sign}{delta:>6} | {notes}")

    print("-" * 70)
    total_delta = total_new - total_old
    sign = "+" if total_delta >= 0 else ""
    print(f"{'TOTAL':>6} | {total_old:>6} | {total_new:>6} | {sign}{total_delta:>6} |")

    if args.dry_run:
        print("\n  DRY RUN -- no database changes made.")
    else:
        print(f"\n  LIVE -- {total_new} provisions inserted across {len(cba_ids)} contracts.")


if __name__ == "__main__":
    main()
