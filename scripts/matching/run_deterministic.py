"""
CLI for running deterministic matching against F7 employers.

Usage:
    py scripts/matching/run_deterministic.py osha
    py scripts/matching/run_deterministic.py whd --limit 1000
    py scripts/matching/run_deterministic.py all --dry-run
    py scripts/matching/run_deterministic.py osha --unmatched-only

Batched re-run (25% at a time with checkpointing):
    py scripts/matching/run_deterministic.py osha --rematch-all --batch 1/4
    py scripts/matching/run_deterministic.py osha --rematch-all --batch 2/4
    py scripts/matching/run_deterministic.py osha --rematch-all --batch 3/4
    py scripts/matching/run_deterministic.py osha --rematch-all --batch 4/4

Check batch progress:
    py scripts/matching/run_deterministic.py osha --batch-status
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from scripts.matching.deterministic_matcher import DeterministicMatcher
from scripts.matching.adapters import osha_adapter, whd_adapter, n990_adapter, sam_adapter, sec_adapter_module, bmf_adapter_module

ADAPTERS = {
    "osha": osha_adapter,
    "whd": whd_adapter,
    "990": n990_adapter,
    "sam": sam_adapter,
    "sec": sec_adapter_module,
    "bmf": bmf_adapter_module,
}

CHECKPOINT_DIR = Path(__file__).resolve().parent.parent.parent / "checkpoints"


def _checkpoint_path(source_name):
    """Path to checkpoint JSON for a source."""
    return CHECKPOINT_DIR / f"{source_name}_rerun.json"


def _load_checkpoint(source_name):
    """Load checkpoint file, or return empty dict."""
    cp = _checkpoint_path(source_name)
    if cp.exists():
        return json.loads(cp.read_text())
    return {}


def _save_checkpoint(source_name, data):
    """Save checkpoint data to JSON."""
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    cp = _checkpoint_path(source_name)
    cp.write_text(json.dumps(data, indent=2, default=str))
    print(f"  Checkpoint saved: {cp}")


def _print_batch_status(source_name):
    """Print current batch progress for a source."""
    cp = _load_checkpoint(source_name)
    if not cp:
        print(f"No checkpoint found for {source_name}.")
        print(f"  Start with: py scripts/matching/run_deterministic.py {source_name} --rematch-all --batch 1/4")
        return

    total_records = cp.get("total_records", 0)
    total_batches = cp.get("total_batches", 0)
    batches = cp.get("batches", {})

    print(f"\n{'='*60}")
    print(f"Batch Status: {source_name.upper()}")
    print(f"{'='*60}")
    print(f"Total records: {total_records:,}")
    print(f"Total batches: {total_batches}")
    print()

    cumulative = {"matched": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "records": 0}

    for i in range(1, total_batches + 1):
        key = str(i)
        if key in batches:
            b = batches[key]
            cumulative["records"] += b["records_in_batch"]
            cumulative["matched"] += b["matched"]
            cumulative["HIGH"] += b["by_band"]["HIGH"]
            cumulative["MEDIUM"] += b["by_band"]["MEDIUM"]
            cumulative["LOW"] += b["by_band"]["LOW"]
            rate = b["matched"] / max(b["records_in_batch"], 1) * 100
            print(f"  Batch {i}/{total_batches}: DONE  "
                  f"{b['records_in_batch']:>8,} records, "
                  f"{b['matched']:>7,} matched ({rate:.1f}%) "
                  f"[H:{b['by_band']['HIGH']:,} M:{b['by_band']['MEDIUM']:,} L:{b['by_band']['LOW']:,}]")
        else:
            print(f"  Batch {i}/{total_batches}: PENDING")

    if cumulative["records"]:
        print()
        rate = cumulative["matched"] / max(cumulative["records"], 1) * 100
        print(f"  Cumulative: {cumulative['records']:,} processed, "
              f"{cumulative['matched']:,} matched ({rate:.1f}%)")
        print(f"  Bands: HIGH={cumulative['HIGH']:,}, "
              f"MEDIUM={cumulative['MEDIUM']:,}, LOW={cumulative['LOW']:,}")
        remaining = total_records - cumulative["records"]
        if remaining > 0:
            print(f"  Remaining: {remaining:,} records in {total_batches - len(batches)} batch(es)")
    print()


def _parse_batch_arg(batch_str):
    """Parse '1/4' into (batch_num, total_batches)."""
    parts = batch_str.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid --batch format '{batch_str}'. Use N/M, e.g. '1/4'")
    batch_num = int(parts[0])
    total_batches = int(parts[1])
    if batch_num < 1 or batch_num > total_batches:
        raise ValueError(f"Batch {batch_num} out of range 1..{total_batches}")
    if total_batches < 2:
        raise ValueError("Total batches must be >= 2")
    return batch_num, total_batches


def _supersede_batch(conn, source_name, source_ids, dry_run=False):
    """
    Supersede old active matches for a specific set of source IDs.

    Unlike the old approach (supersede ALL at once), this only touches
    the current batch's records so unprocessed batches keep their old matches.
    """
    if dry_run or not source_ids:
        return 0

    # Batch the supersede in chunks of 5000 to avoid huge IN clauses
    total_superseded = 0
    chunk_size = 5000
    with conn.cursor() as cur:
        for i in range(0, len(source_ids), chunk_size):
            chunk = source_ids[i:i + chunk_size]
            cur.execute("""
                UPDATE unified_match_log
                SET status = 'superseded'
                WHERE source_system = %s
                  AND status = 'active'
                  AND source_id = ANY(%s)
            """, [source_name, chunk])
            total_superseded += cur.rowcount
    conn.commit()
    return total_superseded


def run_source(conn, source_name, adapter, args):
    """Run matching for a single source."""
    batch_num = getattr(args, '_batch_num', None)
    total_batches = getattr(args, '_total_batches', None)
    is_batched = batch_num is not None

    batch_label = f" (batch {batch_num}/{total_batches})" if is_batched else ""
    run_id = f"det-{source_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if is_batched:
        run_id += f"-b{batch_num}of{total_batches}"

    print(f"\n{'='*60}")
    print(f"Source: {source_name.upper()}{batch_label}")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}")

    # Register run
    if not args.dry_run:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO match_runs (run_id, scenario, started_at, source_system, method_type)
                VALUES (%s, %s, NOW(), %s, %s)
                ON CONFLICT (run_id) DO NOTHING
            """, [run_id, f"deterministic_{source_name}", source_name, "deterministic_v2"])
            conn.commit()

    # Load source records
    if args.unmatched_only:
        print("Loading unmatched records...")
        records = adapter.load_unmatched(conn, limit=args.limit)
    else:
        print("Loading all records...")
        records = adapter.load_all(conn, limit=args.limit)

    print(f"Loaded {len(records):,} total source records")

    if not records:
        print("No records to match.")
        return

    # -- Batch slicing --
    total_before_slice = len(records)  # save for checkpoint
    if is_batched:
        # Sort deterministically by ID so each batch is always the same slice
        records.sort(key=lambda r: str(r["id"]))
        total = len(records)

        # Check checkpoint for consistency
        cp = _load_checkpoint(source_name)
        if cp and cp.get("total_records", 0) > 0 and cp["total_records"] != total:
            print(f"  WARNING: Record count changed ({cp['total_records']:,} -> {total:,}).")
            print(f"  Previous checkpoint was for a different dataset. Starting fresh.")
            cp = {}

        # Calculate batch boundaries
        batch_size = total // total_batches
        start = (batch_num - 1) * batch_size
        end = total if batch_num == total_batches else start + batch_size
        batch_records = records[start:end]

        print(f"  Batch {batch_num}/{total_batches}: records [{start:,}..{end:,}) "
              f"= {len(batch_records):,} records")

        # Supersede only this batch's old active matches
        if not args.unmatched_only and not args.dry_run:
            batch_ids = [str(r["id"]) for r in batch_records]
            superseded = _supersede_batch(conn, source_name, batch_ids, args.dry_run)
            if superseded:
                print(f"  Superseded {superseded:,} old active matches for this batch")

        records = batch_records
    else:
        # Non-batched: supersede all at once (original behavior)
        if not args.unmatched_only and not args.dry_run:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE unified_match_log
                    SET status = 'superseded'
                    WHERE source_system = %s AND status = 'active'
                """, [source_name])
                superseded = cur.rowcount
                if superseded:
                    print(f"Superseded {superseded:,} old active matches in unified_match_log")
                conn.commit()

    # Run matching
    matcher = DeterministicMatcher(conn, run_id, source_name, dry_run=args.dry_run,
                                   skip_fuzzy=args.skip_fuzzy)
    matches = matcher.match_batch(records)
    matcher.print_stats()

    # Write to legacy tables (HIGH + MEDIUM only, skip LOW/rejected)
    if not args.dry_run and matches and not args.skip_legacy:
        quality_matches = [m for m in matches if m["band"] != "LOW"]
        if quality_matches:
            print(f"\nWriting {len(quality_matches):,} HIGH/MEDIUM matches to legacy table "
                  f"(skipping {len(matches) - len(quality_matches):,} LOW)...")
            adapter.write_legacy(conn, quality_matches)
        else:
            print("\nNo HIGH/MEDIUM matches to write to legacy table.")

    # Update run stats
    if not args.dry_run:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE match_runs
                SET completed_at = NOW(),
                    total_source = %s,
                    total_matched = %s,
                    match_rate = %s,
                    high_count = %s,
                    medium_count = %s,
                    low_count = %s
                WHERE run_id = %s
            """, [
                len(records), len(matches),
                round(len(matches) / max(len(records), 1) * 100, 2),
                matcher.stats["by_band"]["HIGH"],
                matcher.stats["by_band"]["MEDIUM"],
                matcher.stats["by_band"]["LOW"],
                run_id,
            ])
            conn.commit()

    # -- Save checkpoint --
    if is_batched:
        cp = _load_checkpoint(source_name)
        if not cp:
            cp = {
                "source": source_name,
                "total_records": total_before_slice,
                "total_batches": total_batches,
                "started_at": datetime.now().isoformat(),
                "batches": {},
            }
        # Always update total from actual load (pre-slice count)
        cp["total_records"] = total_before_slice

        cp["batches"][str(batch_num)] = {
            "run_id": run_id,
            "completed_at": datetime.now().isoformat(),
            "records_in_batch": len(records),
            "matched": len(matches),
            "match_rate_pct": round(len(matches) / max(len(records), 1) * 100, 2),
            "by_band": {
                "HIGH": matcher.stats["by_band"]["HIGH"],
                "MEDIUM": matcher.stats["by_band"]["MEDIUM"],
                "LOW": matcher.stats["by_band"]["LOW"],
            },
            "by_method": dict(matcher.stats["by_method"]),
        }
        _save_checkpoint(source_name, cp)

        # Print quality comparison across batches
        _print_quality_report(source_name, batch_num, total_batches, matcher, matches)

    return matches


def _print_quality_report(source_name, batch_num, total_batches, matcher, matches):
    """Print a quality report after each batch to help decide whether to continue."""
    cp = _load_checkpoint(source_name)
    batches = cp.get("batches", {})

    print(f"\n{'='*60}")
    print(f"QUALITY REPORT: {source_name.upper()} batch {batch_num}/{total_batches}")
    print(f"{'='*60}")

    # Current batch stats
    total = matcher.stats["total"]
    matched = matcher.stats["matched"]
    rate = matched / max(total, 1) * 100
    high = matcher.stats["by_band"]["HIGH"]
    medium = matcher.stats["by_band"]["MEDIUM"]
    low = matcher.stats["by_band"]["LOW"]
    quality = high + medium
    quality_rate = quality / max(total, 1) * 100

    print(f"\n  This batch:")
    print(f"    Records:        {total:>10,}")
    print(f"    Total matched:  {matched:>10,} ({rate:.1f}%)")
    print(f"    HIGH+MEDIUM:    {quality:>10,} ({quality_rate:.1f}%)")
    print(f"    LOW (rejected): {low:>10,}")
    print(f"    No match:       {total - matched:>10,}")

    # Sanity checks
    warnings = []
    if rate > 60:
        warnings.append(f"Match rate {rate:.1f}% seems HIGH -- check for geography-only Splink matches")
    if low > matched * 0.3:
        warnings.append(f"LOW band is {low/max(matched,1)*100:.0f}% of matches -- many weak matches")
    if quality_rate < 2:
        warnings.append(f"Only {quality_rate:.1f}% quality match rate -- very low")

    if warnings:
        print(f"\n  WARNINGS:")
        for w in warnings:
            print(f"    ** {w}")

    # Method breakdown
    if matcher.stats["by_method"]:
        print(f"\n  Method breakdown:")
        for method, count in sorted(matcher.stats["by_method"].items(), key=lambda x: -x[1]):
            pct = count / max(matched, 1) * 100
            print(f"    {method:40s} {count:>8,} ({pct:5.1f}%)")

    # Cross-batch comparison
    if len(batches) > 1:
        print(f"\n  Cross-batch comparison:")
        print(f"    {'Batch':<10} {'Records':>10} {'Matched':>10} {'Rate':>8} {'H+M':>10} {'LOW':>10}")
        print(f"    {'-'*8:<10} {'-'*10:>10} {'-'*10:>10} {'-'*8:>8} {'-'*10:>10} {'-'*10:>10}")
        for i in range(1, total_batches + 1):
            key = str(i)
            if key in batches:
                b = batches[key]
                r = b["records_in_batch"]
                m = b["matched"]
                rt = m / max(r, 1) * 100
                hm = b["by_band"]["HIGH"] + b["by_band"]["MEDIUM"]
                lo = b["by_band"]["LOW"]
                marker = " <-- current" if i == batch_num else ""
                print(f"    {i:<10} {r:>10,} {m:>10,} {rt:>7.1f}% {hm:>10,} {lo:>10,}{marker}")

    # Next step
    if batch_num < total_batches:
        next_cmd = (f"py scripts/matching/run_deterministic.py {source_name} "
                    f"--rematch-all --batch {batch_num+1}/{total_batches}")
        print(f"\n  Next batch: {next_cmd}")
        print(f"  Or check status: py scripts/matching/run_deterministic.py {source_name} --batch-status")
    else:
        print(f"\n  All {total_batches} batches complete!")
        print(f"  Check status: py scripts/matching/run_deterministic.py {source_name} --batch-status")

    print()


def main():
    parser = argparse.ArgumentParser(description="Run deterministic matching")
    parser.add_argument("source", choices=["osha", "whd", "990", "sam", "sec", "bmf", "all"],
                        help="Source system to match")
    parser.add_argument("--limit", type=int, help="Limit number of source records")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    parser.add_argument("--unmatched-only", action="store_true", default=True,
                        help="Only match unmatched records (default)")
    parser.add_argument("--rematch-all", action="store_true",
                        help="Re-match all records, not just unmatched")
    parser.add_argument("--skip-legacy", action="store_true",
                        help="Skip writing to legacy match tables")
    parser.add_argument("--skip-fuzzy", action="store_true",
                        help="Skip tier 5 fuzzy matching (fast exact-only mode)")
    parser.add_argument("--batch", type=str, default=None,
                        help="Run a specific batch, e.g. '1/4' for batch 1 of 4")
    parser.add_argument("--batch-status", action="store_true",
                        help="Show batch progress for source (no matching)")
    args = parser.parse_args()

    if args.batch_status:
        if args.source == "all":
            for name in ADAPTERS:
                _print_batch_status(name)
        else:
            _print_batch_status(args.source)
        return

    if args.rematch_all:
        args.unmatched_only = False

    # Parse batch argument
    if args.batch:
        batch_num, total_batches = _parse_batch_arg(args.batch)
        args._batch_num = batch_num
        args._total_batches = total_batches
    else:
        args._batch_num = None
        args._total_batches = None

    conn = get_connection()
    try:
        if args.source == "all":
            for name in ["osha", "whd", "990", "sam", "sec", "bmf"]:
                run_source(conn, name, ADAPTERS[name], args)
        else:
            run_source(conn, args.source, ADAPTERS[args.source], args)
    finally:
        conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
