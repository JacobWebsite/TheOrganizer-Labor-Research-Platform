#!/usr/bin/env python3
"""
Resumable, batch-safe dedup for master_employers.

This file is the CLI orchestrator; the merge primitives live in
src/python/matching/master_dedup.py and are shared with the LLM-gold +
rule-engine apply scripts and the Pfizer bundled back-fill.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from psycopg2 import sql

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection
from src.python.matching.master_dedup import (
    MergeContext,
    ensure_dedup_tables,
    fetch_employers,
    merge_one,
    name_sim,
    set_timeouts,
    tnorm,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Dedup master_employers")
    p.add_argument("--phase", choices=["1", "2", "3", "4", "all"], default="all")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=1000)
    p.add_argument("--min-name-sim", type=float, default=0.85)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--max-seconds", type=int, default=None)
    p.add_argument("--statement-timeout-ms", type=int, default=120000)
    return p.parse_args()


def progress_get(cur, phase: str) -> Tuple[Optional[str], Optional[str], int, int, int]:
    cur.execute(
        """
        SELECT cursor_1, cursor_2, groups_processed, merges_executed, records_eliminated
        FROM master_employer_dedup_progress
        WHERE phase=%s
        """,
        (phase,),
    )
    r = cur.fetchone()
    if not r:
        return None, None, 0, 0, 0
    return r[0], r[1], int(r[2]), int(r[3]), int(r[4])


def progress_set(cur, phase: str, c1: Optional[str], c2: Optional[str], gp: int, me: int, re: int) -> None:
    cur.execute(
        """
        INSERT INTO master_employer_dedup_progress
          (phase, cursor_1, cursor_2, groups_processed, merges_executed, records_eliminated, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (phase) DO UPDATE
        SET cursor_1=EXCLUDED.cursor_1,
            cursor_2=EXCLUDED.cursor_2,
            groups_processed=EXCLUDED.groups_processed,
            merges_executed=EXCLUDED.merges_executed,
            records_eliminated=EXCLUDED.records_eliminated,
            updated_at=NOW()
        """,
        (phase, c1, c2, gp, me, re),
    )


def run_phase(conn, ctx: MergeContext, args: argparse.Namespace, phase: str) -> Dict[str, int]:
    phase_key = {"1": "phase_1_ein", "2": "phase_2_exact"}[phase]
    with conn.cursor() as cur:
        c1, c2, base_g, base_m, base_r = progress_get(cur, phase_key)
    conn.commit()
    c1 = c1 if args.resume else None
    c2 = c2 if args.resume else None
    gp, me, re = base_g, base_m, base_r
    found, pairs = 0, 0
    start = time.time()
    pk = sql.Identifier(ctx.pk_col)

    while True:
        if args.max_seconds and time.time() - start >= args.max_seconds:
            break
        with conn.cursor() as cur:
            set_timeouts(cur, args.statement_timeout_ms)
            if phase == "1":
                if c1:
                    cur.execute(
                        sql.SQL(
                            "SELECT ein, array_agg({pk} ORDER BY {pk}) ids FROM master_employers "
                            "WHERE ein IS NOT NULL AND btrim(ein)<>'' AND ein>%s "
                            "GROUP BY ein HAVING COUNT(*)>1 ORDER BY ein LIMIT %s"
                        ).format(pk=pk),
                        (c1, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT ein, array_agg({pk} ORDER BY {pk}) ids FROM master_employers "
                            "WHERE ein IS NOT NULL AND btrim(ein)<>'' "
                            "GROUP BY ein HAVING COUNT(*)>1 ORDER BY ein LIMIT %s"
                        ).format(pk=pk),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], None, list(r[1])) for r in cur.fetchall()]
            elif phase == "2":
                if c1 is not None and c2 is not None:
                    cur.execute(
                        sql.SQL(
                            "SELECT canonical_name, state::TEXT, array_agg({pk} ORDER BY {pk}) ids FROM master_employers "
                            "WHERE canonical_name IS NOT NULL AND btrim(canonical_name)<>'' AND state IS NOT NULL "
                            "AND (canonical_name,state::TEXT)>(%s,%s) "
                            "GROUP BY canonical_name, state::TEXT HAVING COUNT(*)>1 ORDER BY canonical_name, state::TEXT LIMIT %s"
                        ).format(pk=pk),
                        (c1, c2, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT canonical_name, state::TEXT, array_agg({pk} ORDER BY {pk}) ids FROM master_employers "
                            "WHERE canonical_name IS NOT NULL AND btrim(canonical_name)<>'' AND state IS NOT NULL "
                            "GROUP BY canonical_name, state::TEXT HAVING COUNT(*)>1 ORDER BY canonical_name, state::TEXT LIMIT %s"
                        ).format(pk=pk),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], r[1], list(r[2])) for r in cur.fetchall()]
        conn.commit()
        if not blocks:
            break

        found += len(blocks)
        for k1, k2, ids in blocks:
            if args.max_seconds and time.time() - start >= args.max_seconds:
                break
            c1, c2 = k1, k2
            gp += 1
            if len(ids) < 2:
                continue
            with conn.cursor() as cur:
                set_timeouts(cur, args.statement_timeout_ms)
                rows = fetch_employers(cur, ctx, ids)
            conn.commit()
            if len(rows) < 2:
                continue
            winner = sorted(rows, key=lambda x: x.rank())[0]
            for loser in [x for x in rows if x.mid != winner.mid]:
                if winner.has_f7 and loser.has_f7:
                    continue
                sim = name_sim(winner.canonical_name, loser.canonical_name)
                ok = False
                ev: Dict[str, object] = {}
                if phase == "1":
                    ok = sim >= 0.70 or (tnorm(winner.state) and tnorm(winner.state) == tnorm(loser.state))
                    ev = {"ein": k1, "name_sim": round(sim, 4), "rule": "ein_and_name_sim_or_state"}
                elif phase == "2":
                    ok = True
                    ev = {"canonical_name": k1, "state": k2, "name_sim": round(sim, 4), "rule": "name_state_exact"}
                if not ok:
                    continue
                if args.verbose:
                    print(f"[phase{phase}] merge winner={winner.mid} loser={loser.mid} sim={sim:.3f}")
                if not args.dry_run:
                    with conn.cursor() as cur:
                        set_timeouts(cur, args.statement_timeout_ms)
                        merge_one(
                            cur=cur,
                            ctx=ctx,
                            winner=winner,
                            loser=loser,
                            phase={"1": "ein", "2": "name_state_exact"}[phase],
                            conf=min(0.99, max(0.60, sim)),
                            ev=ev,
                        )
                    conn.commit()
                me += 1
                re += 1
                if not args.dry_run and me % args.batch_size == 0:
                    with conn.cursor() as cur:
                        progress_set(cur, phase_key, c1, c2, gp, me, re)
                    conn.commit()
            if args.limit and gp >= base_g + args.limit:
                break
        if args.limit and gp >= base_g + args.limit:
            break

    if not args.dry_run:
        with conn.cursor() as cur:
            progress_set(cur, phase_key, c1, c2, gp, me, re)
        conn.commit()
    return {
        "groups_found": found,
        "groups_processed": gp - base_g,
        "candidate_pairs": pairs,
        "merges_executed": me - base_m,
        "records_eliminated": re - base_r,
    }


def _run_phase3_substep(
    conn, ctx: MergeContext, args: argparse.Namespace,
    substep: str, threshold: float,
) -> Dict[str, int]:
    """Run one sub-step of the Phase 3 geographic cascade.

    substep: '3a' (ZIP), '3b' (city+state), '3c' (state-only fallback)
    """
    phase_key = f"phase_{substep}"
    with conn.cursor() as cur:
        c1, c2, base_g, base_m, base_r = progress_get(cur, phase_key)
    conn.commit()
    c1 = c1 if args.resume else None
    c2 = c2 if args.resume else None
    gp, me, re = base_g, base_m, base_r
    found, pairs = 0, 0
    start = time.time()
    pk = sql.Identifier(ctx.pk_col)

    while True:
        if args.max_seconds and time.time() - start >= args.max_seconds:
            break
        with conn.cursor() as cur:
            set_timeouts(cur, args.statement_timeout_ms)
            if substep == "3a":
                if c1 is not None:
                    cur.execute(
                        sql.SQL(
                            "SELECT left(zip,5), array_agg({pk} ORDER BY {pk}) ids "
                            "FROM master_employers "
                            "WHERE zip IS NOT NULL AND btrim(zip)<>'' "
                            "AND canonical_name IS NOT NULL AND btrim(canonical_name)<>'' "
                            "AND left(zip,5) > %s "
                            "GROUP BY left(zip,5) HAVING COUNT(*) BETWEEN 2 AND 500 "
                            "ORDER BY left(zip,5) LIMIT %s"
                        ).format(pk=pk),
                        (c1, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT left(zip,5), array_agg({pk} ORDER BY {pk}) ids "
                            "FROM master_employers "
                            "WHERE zip IS NOT NULL AND btrim(zip)<>'' "
                            "AND canonical_name IS NOT NULL AND btrim(canonical_name)<>'' "
                            "GROUP BY left(zip,5) HAVING COUNT(*) BETWEEN 2 AND 500 "
                            "ORDER BY left(zip,5) LIMIT %s"
                        ).format(pk=pk),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], None, list(r[1])) for r in cur.fetchall()]

            elif substep == "3b":
                if c1 is not None and c2 is not None:
                    cur.execute(
                        sql.SQL(
                            "SELECT city, state::TEXT, array_agg({pk} ORDER BY {pk}) ids "
                            "FROM master_employers "
                            "WHERE city IS NOT NULL AND btrim(city)<>'' "
                            "AND state IS NOT NULL "
                            "AND canonical_name IS NOT NULL AND btrim(canonical_name)<>'' "
                            "AND (city, state::TEXT) > (%s, %s) "
                            "GROUP BY city, state::TEXT HAVING COUNT(*) BETWEEN 2 AND 500 "
                            "ORDER BY city, state::TEXT LIMIT %s"
                        ).format(pk=pk),
                        (c1, c2, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT city, state::TEXT, array_agg({pk} ORDER BY {pk}) ids "
                            "FROM master_employers "
                            "WHERE city IS NOT NULL AND btrim(city)<>'' "
                            "AND state IS NOT NULL "
                            "AND canonical_name IS NOT NULL AND btrim(canonical_name)<>'' "
                            "GROUP BY city, state::TEXT HAVING COUNT(*) BETWEEN 2 AND 500 "
                            "ORDER BY city, state::TEXT LIMIT %s"
                        ).format(pk=pk),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], r[1], list(r[2])) for r in cur.fetchall()]

            else:  # 3c
                if c1 is not None and c2 is not None:
                    cur.execute(
                        sql.SQL(
                            "SELECT state::TEXT, left(canonical_name,8), array_agg({pk} ORDER BY {pk}) ids "
                            "FROM master_employers "
                            "WHERE state IS NOT NULL "
                            "AND canonical_name IS NOT NULL AND btrim(canonical_name)<>'' "
                            "AND (city IS NULL OR btrim(city)='') "
                            "AND (zip IS NULL OR btrim(zip)='') "
                            "AND (state::TEXT, left(canonical_name,8)) > (%s, %s) "
                            "GROUP BY state::TEXT, left(canonical_name,8) HAVING COUNT(*) BETWEEN 2 AND 200 "
                            "ORDER BY state::TEXT, left(canonical_name,8) LIMIT %s"
                        ).format(pk=pk),
                        (c1, c2, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT state::TEXT, left(canonical_name,8), array_agg({pk} ORDER BY {pk}) ids "
                            "FROM master_employers "
                            "WHERE state IS NOT NULL "
                            "AND canonical_name IS NOT NULL AND btrim(canonical_name)<>'' "
                            "AND (city IS NULL OR btrim(city)='') "
                            "AND (zip IS NULL OR btrim(zip)='') "
                            "GROUP BY state::TEXT, left(canonical_name,8) HAVING COUNT(*) BETWEEN 2 AND 200 "
                            "ORDER BY state::TEXT, left(canonical_name,8) LIMIT %s"
                        ).format(pk=pk),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], r[1], list(r[2])) for r in cur.fetchall()]
        conn.commit()
        if not blocks:
            break

        found += len(blocks)
        for k1, k2, ids in blocks:
            if args.max_seconds and time.time() - start >= args.max_seconds:
                break
            c1, c2 = k1, k2
            gp += 1
            if len(ids) < 2:
                continue
            with conn.cursor() as cur:
                set_timeouts(cur, args.statement_timeout_ms)
                rows = fetch_employers(cur, ctx, ids)
            conn.commit()
            if len(rows) < 2:
                continue
            winner = sorted(rows, key=lambda x: x.rank())[0]
            for loser in [x for x in rows if x.mid != winner.mid]:
                if winner.has_f7 and loser.has_f7:
                    continue
                sim = name_sim(winner.canonical_name, loser.canonical_name)
                pairs += 1
                if sim < threshold:
                    continue
                if substep == "3a":
                    ev = {"zip": k1, "name_sim": round(sim, 4), "rule": "zip_fuzzy"}
                elif substep == "3b":
                    ev = {"city": k1, "state": k2, "name_sim": round(sim, 4), "rule": "city_state_fuzzy"}
                else:
                    ev = {"state": k1, "name_block": k2, "name_sim": round(sim, 4), "rule": "state_only_fallback"}
                if args.verbose:
                    print(f"[phase{substep}] merge winner={winner.mid} loser={loser.mid} sim={sim:.3f}")
                if not args.dry_run:
                    with conn.cursor() as cur:
                        set_timeouts(cur, args.statement_timeout_ms)
                        merge_one(
                            cur=cur,
                            ctx=ctx,
                            winner=winner,
                            loser=loser,
                            phase=f"name_geo_{substep}",
                            conf=min(0.99, max(0.60, sim)),
                            ev=ev,
                        )
                    conn.commit()
                me += 1
                re += 1
                if not args.dry_run and me % args.batch_size == 0:
                    with conn.cursor() as cur:
                        progress_set(cur, phase_key, c1, c2, gp, me, re)
                    conn.commit()
            if args.limit and gp >= base_g + args.limit:
                break
        if args.limit and gp >= base_g + args.limit:
            break

    if not args.dry_run:
        with conn.cursor() as cur:
            progress_set(cur, phase_key, c1, c2, gp, me, re)
        conn.commit()
    return {
        "groups_found": found,
        "groups_processed": gp - base_g,
        "candidate_pairs": pairs,
        "merges_executed": me - base_m,
        "records_eliminated": re - base_r,
    }


def run_phase3_cascade(conn, ctx: MergeContext, args: argparse.Namespace) -> Dict[str, object]:
    """Phase 3: 3-step geographic cascade replacing old name+state fuzzy."""
    results = {}
    for substep, threshold, label in [
        ("3a", 0.82, "ZIP blocking"),
        ("3b", 0.85, "City+State blocking"),
        ("3c", 0.85, "State-only fallback"),
    ]:
        s = _run_phase3_substep(conn, ctx, args, substep, threshold)
        results[substep] = s
        print(f"  Phase {substep} ({label}, threshold={threshold}):")
        print(f"    Groups found: {s['groups_found']:,}")
        print(f"    Candidate pairs: {s['candidate_pairs']:,}")
        print(f"    Merges executed: {s['merges_executed']:,}")
        print(f"    Records eliminated: {s['records_eliminated']:,}")
    totals = {
        "candidate_pairs": sum(r["candidate_pairs"] for r in results.values()),
        "merges_executed": sum(r["merges_executed"] for r in results.values()),
        "records_eliminated": sum(r["records_eliminated"] for r in results.values()),
    }
    return {"substeps": results, "totals": totals}


def run_phase4(conn, ctx: MergeContext, args: argparse.Namespace) -> Dict[str, object]:
    phase_key = "phase_4_quality"
    with conn.cursor() as cur:
        c1, c2, base_g, base_m, base_r = progress_get(cur, phase_key)
    conn.commit()

    last_pk = int(c1) if (args.resume and c1) else 0
    chunk_size = max(1000, int(args.batch_size))
    rows_updated = 0
    batches = 0
    started = time.time()
    pk = sql.Identifier(ctx.pk_col)

    while True:
        if args.max_seconds and time.time() - started >= args.max_seconds:
            break
        with conn.cursor() as cur:
            set_timeouts(cur, args.statement_timeout_ms)
            cur.execute(
                sql.SQL(
                    """
                    WITH ids AS (
                      SELECT {pk} AS master_id
                      FROM master_employers
                      WHERE {pk} > %s
                      ORDER BY {pk}
                      LIMIT %s
                    ),
                    src AS (
                      SELECT sid.master_id, COUNT(DISTINCT sid.source_system)::INT AS source_cnt
                      FROM master_employer_source_ids sid
                      JOIN ids ON ids.master_id = sid.master_id
                      GROUP BY sid.master_id
                    )
                    UPDATE master_employers m
                    SET data_quality_score = CASE
                      WHEN COALESCE(src.source_cnt, 0) >= 5
                        OR (COALESCE(src.source_cnt, 0) >= 4
                            AND m.employee_count IS NOT NULL
                            AND m.naics IS NOT NULL
                            AND m.city IS NOT NULL AND btrim(m.city) <> ''
                            AND m.state IS NOT NULL AND btrim(m.state) <> '')
                        THEN 100
                      WHEN COALESCE(src.source_cnt, 0) >= 4
                        OR (COALESCE(src.source_cnt, 0) >= 3
                            AND m.employee_count IS NOT NULL
                            AND m.naics IS NOT NULL
                            AND m.city IS NOT NULL AND btrim(m.city) <> ''
                            AND m.state IS NOT NULL AND btrim(m.state) <> '')
                        THEN 80
                      WHEN COALESCE(src.source_cnt, 0) >= 3
                        OR (COALESCE(src.source_cnt, 0) >= 2
                            AND m.city IS NOT NULL AND btrim(m.city) <> ''
                            AND m.state IS NOT NULL AND btrim(m.state) <> ''
                            AND (m.employee_count IS NOT NULL OR m.naics IS NOT NULL))
                        THEN 60
                      WHEN m.city IS NOT NULL AND btrim(m.city) <> ''
                        AND m.state IS NOT NULL AND btrim(m.state) <> ''
                        AND (m.employee_count IS NOT NULL OR m.naics IS NOT NULL)
                        THEN 40
                      ELSE 20
                    END,
                    updated_at = NOW()
                    FROM ids
                    LEFT JOIN src ON src.master_id = ids.master_id
                    WHERE m.{pk} = ids.master_id
                    RETURNING m.{pk}
                    """
                ).format(pk=pk),
                (last_pk, chunk_size),
            )
            returned_ids = cur.fetchall()
            if not returned_ids:
                conn.commit()
                break
            last_pk = max(int(r[0]) for r in returned_ids)
            batch_rows = len(returned_ids)
            rows_updated += batch_rows
            batches += 1
            progress_set(cur, phase_key, str(last_pk), None, batches, rows_updated, rows_updated)
        conn.commit()

    with conn.cursor() as cur:
        set_timeouts(cur, args.statement_timeout_ms)
        cur.execute(
            """
            SELECT CASE
                WHEN data_quality_score <= 20 THEN '0-20'
                WHEN data_quality_score <= 40 THEN '21-40'
                WHEN data_quality_score <= 60 THEN '41-60'
                WHEN data_quality_score <= 80 THEN '61-80'
                ELSE '81-100'
              END AS tier,
              COUNT(*) AS cnt
            FROM master_employers
            GROUP BY 1 ORDER BY 1
            """
        )
        dist = {r[0]: int(r[1]) for r in cur.fetchall()}
    conn.commit()
    return {"updated": rows_updated, "distribution": dist, "batches": batches, "last_pk": last_pk}


def count_rows(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
        return int(cur.fetchone()[0])


def main() -> int:
    args = parse_args()
    if args.batch_size <= 0:
        print("batch-size must be > 0")
        return 2
    if not 0.0 <= args.min_name_sim <= 1.0:
        print("min-name-sim must be between 0 and 1")
        return 2

    conn = get_connection()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            ctx = MergeContext.detect(cur, label="dedup_master_employers.py")
            ensure_dedup_tables(cur, ctx)
        conn.commit()

        before = count_rows(conn, "master_employers")
        print(f"Starting master_employers row count: {before:,}")
        print(
            f"Options: phase={args.phase} dry_run={args.dry_run} resume={args.resume} "
            f"batch_size={args.batch_size} max_seconds={args.max_seconds}"
        )

        phases = ["1", "2", "3", "4"] if args.phase == "all" else [args.phase]

        if "1" in phases:
            s = run_phase(conn, ctx, args, "1")
            print("Phase 1 (EIN merge):")
            print(f"  Groups found: {s['groups_found']:,}")
            print(f"  Merges executed: {s['merges_executed']:,}")
            print(f"  Records eliminated: {s['records_eliminated']:,}")
        if "2" in phases:
            s = run_phase(conn, ctx, args, "2")
            print("Phase 2 (Name+State exact):")
            print(f"  Groups found: {s['groups_found']:,}")
            print(f"  Merges executed: {s['merges_executed']:,}")
            print(f"  Records eliminated: {s['records_eliminated']:,}")
        if "3" in phases:
            print("Phase 3 (Geographic cascade):")
            s3 = run_phase3_cascade(conn, ctx, args)
            t = s3["totals"]
            print(f"  Total candidate pairs: {t['candidate_pairs']:,}")
            print(f"  Total merges executed: {t['merges_executed']:,}")
            print(f"  Total records eliminated: {t['records_eliminated']:,}")
        if "4" in phases:
            s = run_phase4(conn, ctx, args)
            print("Phase 4 (Quality scores):")
            print(f"  Updated: {s['updated']:,} records")
            print(f"  Batches: {s['batches']:,}, Last PK: {s['last_pk']:,}")
            print("  Distribution: " + ", ".join(f"{k}: {v:,}" for k, v in sorted(s["distribution"].items())))

        after = count_rows(conn, "master_employers")
        diff = before - after
        pct = (100.0 * diff / before) if before else 0.0
        print(f"Final: master_employers went from {before:,} to {after:,} rows ({pct:.2f}% reduction)")
        if args.dry_run:
            print("Dry-run mode: no data changes committed.")
        return 0
    except KeyboardInterrupt:
        if not conn.closed:
            conn.rollback()
        print("Stopped by user. Progress up to last committed batch is saved.")
        return 130
    except Exception as exc:
        if not conn.closed:
            conn.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
