#!/usr/bin/env python3
"""
Resumable, batch-safe dedup for master_employers.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from psycopg2 import sql
from rapidfuzz import fuzz

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db_config import get_connection

SOURCE_PRIORITY = {"f7": 0, "sam": 1, "mergent": 2, "bmf": 3, "sec": 4, "990": 5, "gleif": 6}
EMP_COUNT_PRIORITY = {"f7": 0, "mergent": 1, "sam": 2, "bmf": 3, "990": 4}


@dataclass
class Employer:
    mid: int
    canonical_name: Optional[str]
    display_name: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    naics: Optional[str]
    employee_count: Optional[int]
    employee_count_source: Optional[str]
    ein: Optional[str]
    is_union: bool
    is_public: bool
    is_federal_contractor: bool
    is_nonprofit: bool
    source_origin: str
    has_f7: bool
    is_labor_org: Optional[bool]

    def rank(self) -> Tuple[int, int, int]:
        return (
            0 if self.has_f7 else 1,
            SOURCE_PRIORITY.get((self.source_origin or "").lower(), 99),
            self.mid,
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


def tnorm(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = v.strip()
    return s or None


def name_sim(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_sort_ratio(a, b) / 100.0


def pref(a: Optional[str], b: Optional[str]) -> Optional[str]:
    a1, b1 = tnorm(a), tnorm(b)
    if a1 and b1:
        return a1 if len(a1) >= len(b1) else b1
    return a1 or b1


def has_confirming_signal(a: Employer, b: Employer) -> bool:
    if tnorm(a.city) and tnorm(a.city) == tnorm(b.city):
        return True
    az = "".join(ch for ch in (a.zip_code or "") if ch.isdigit())[:3]
    bz = "".join(ch for ch in (b.zip_code or "") if ch.isdigit())[:3]
    if az and az == bz:
        return True
    an = "".join(ch for ch in (a.naics or "") if ch.isdigit())[:2]
    bn = "".join(ch for ch in (b.naics or "") if ch.isdigit())[:2]
    return bool(an and an == bn)


def set_timeouts(cur, ms: int) -> None:
    cur.execute("SET lock_timeout = '5s'")
    cur.execute("SET statement_timeout = %s", (int(ms),))
    cur.execute("SET idle_in_transaction_session_timeout = '15min'")


def table_col(cur, table: str, col: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_schema='public' AND table_name=%s AND column_name=%s
        ) AS e
        """,
        (table, col),
    )
    return bool(cur.fetchone()[0])


def get_pk_col(cur) -> str:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='master_employers'
          AND column_name IN ('master_id', 'id')
        ORDER BY CASE WHEN column_name='master_id' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("No master_employers PK found")
    return row[0]


def ensure_tables(cur, pk_col: str) -> None:
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS master_employer_dedup_progress (
          phase TEXT PRIMARY KEY,
          cursor_1 TEXT,
          cursor_2 TEXT,
          groups_processed BIGINT NOT NULL DEFAULT 0,
          merges_executed BIGINT NOT NULL DEFAULT 0,
          records_eliminated BIGINT NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS master_employer_merge_log (
          merge_id BIGSERIAL PRIMARY KEY,
          winner_master_id BIGINT NOT NULL,
          loser_master_id BIGINT NOT NULL,
          merge_phase TEXT NOT NULL,
          merge_confidence NUMERIC(5,4),
          merge_evidence JSONB,
          merged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        SELECT conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname='public'
          AND t.relname='master_employer_merge_log'
          AND c.contype='f'
        """
    )
    for (conname,) in cur.fetchall():
        cur.execute(
            sql.SQL("ALTER TABLE master_employer_merge_log DROP CONSTRAINT IF EXISTS {}").format(
                sql.Identifier(conname)
            )
        )
    for ddl in [
        "ALTER TABLE master_employer_merge_log ADD COLUMN IF NOT EXISTS merge_phase TEXT",
        "ALTER TABLE master_employer_merge_log ADD COLUMN IF NOT EXISTS merge_confidence NUMERIC(5,4)",
        "ALTER TABLE master_employer_merge_log ADD COLUMN IF NOT EXISTS merge_evidence JSONB",
    ]:
        cur.execute(ddl)
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_ein ON master_employers (ein, {pk}) "
            "WHERE ein IS NOT NULL AND btrim(ein)<>''"
        ).format(pk=sql.Identifier(pk_col))
    )
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_name_state ON master_employers (canonical_name, state, {pk})"
        ).format(pk=sql.Identifier(pk_col))
    )
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_zip ON master_employers (zip, {pk}) "
            "WHERE zip IS NOT NULL AND btrim(zip)<>''"
        ).format(pk=sql.Identifier(pk_col))
    )
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_city_state ON master_employers (city, state, {pk}) "
            "WHERE city IS NOT NULL AND btrim(city)<>''"
        ).format(pk=sql.Identifier(pk_col))
    )


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


def fetch_employers(cur, pk_col: str, ids: Sequence[int], include_labor_org: bool) -> List[Employer]:
    labor_col = sql.SQL(", COALESCE(m.is_labor_org,FALSE) AS is_labor_org") if include_labor_org else sql.SQL("")
    q = sql.SQL(
        """
        SELECT
          m.{pk},
          m.canonical_name, m.display_name, m.city, m.state::TEXT, m.zip,
          m.naics::TEXT, m.employee_count, m.employee_count_source, m.ein,
          m.is_union, m.is_public, m.is_federal_contractor, m.is_nonprofit,
          m.source_origin,
          EXISTS (
            SELECT 1 FROM master_employer_source_ids sid
            WHERE sid.master_id = m.{pk} AND sid.source_system='f7'
          ) AS has_f7
          {labor_col}
        FROM master_employers m
        WHERE m.{pk} = ANY(%s)
        """
    ).format(pk=sql.Identifier(pk_col), labor_col=labor_col)
    cur.execute(q, (list(ids),))
    out: List[Employer] = []
    for r in cur.fetchall():
        out.append(
            Employer(
                mid=r[0],
                canonical_name=r[1],
                display_name=r[2],
                city=r[3],
                state=r[4],
                zip_code=r[5],
                naics=r[6],
                employee_count=r[7],
                employee_count_source=r[8],
                ein=r[9],
                is_union=bool(r[10]),
                is_public=bool(r[11]),
                is_federal_contractor=bool(r[12]),
                is_nonprofit=bool(r[13]),
                source_origin=r[14] or "",
                has_f7=bool(r[15]),
                is_labor_org=(bool(r[16]) if include_labor_org else None),
            )
        )
    return out


def merge_one(cur, pk_col: str, include_labor_org: bool, winner: Employer, loser: Employer, phase: str, conf: float, ev: Dict[str, object]) -> None:
    # Move source IDs first.
    cur.execute(
        """
        INSERT INTO master_employer_source_ids (master_id, source_system, source_id, match_confidence, matched_at)
        SELECT %s, source_system, source_id, match_confidence, NOW()
        FROM master_employer_source_ids
        WHERE master_id=%s
        ON CONFLICT (master_id, source_system, source_id) DO UPDATE
          SET match_confidence = GREATEST(master_employer_source_ids.match_confidence, EXCLUDED.match_confidence),
              matched_at = NOW()
        """,
        (winner.mid, loser.mid),
    )
    cur.execute("DELETE FROM master_employer_source_ids WHERE master_id=%s", (loser.mid,))

    w_emp_rank = EMP_COUNT_PRIORITY.get((winner.employee_count_source or winner.source_origin or "").lower(), 99)
    l_emp_rank = EMP_COUNT_PRIORITY.get((loser.employee_count_source or loser.source_origin or "").lower(), 99)
    emp_count = winner.employee_count
    emp_src = winner.employee_count_source
    if winner.employee_count is None and loser.employee_count is not None:
        emp_count, emp_src = loser.employee_count, loser.employee_count_source or loser.source_origin
    elif winner.employee_count is not None and loser.employee_count is not None and l_emp_rank < w_emp_rank:
        emp_count, emp_src = loser.employee_count, loser.employee_count_source or loser.source_origin

    set_fields = [
        "canonical_name=%s", "display_name=%s", "city=%s", "state=%s", "zip=%s", "naics=%s", "ein=%s",
        "employee_count=%s", "employee_count_source=%s", "is_union=%s", "is_public=%s",
        "is_federal_contractor=%s", "is_nonprofit=%s", "updated_at=NOW()",
    ]
    params: List[object] = [
        pref(winner.canonical_name, loser.canonical_name),
        pref(winner.display_name, loser.display_name),
        pref(winner.city, loser.city),
        pref(winner.state, loser.state),
        pref(winner.zip_code, loser.zip_code),
        pref(winner.naics, loser.naics),
        pref(winner.ein, loser.ein),
        emp_count,
        emp_src,
        bool(winner.is_union or loser.is_union),
        bool(winner.is_public or loser.is_public),
        bool(winner.is_federal_contractor or loser.is_federal_contractor),
        bool(winner.is_nonprofit or loser.is_nonprofit),
    ]
    if include_labor_org:
        set_fields.insert(-1, "is_labor_org=%s")
        params.append(bool((winner.is_labor_org or False) or (loser.is_labor_org or False)))

    uq = sql.SQL("UPDATE master_employers SET {} WHERE {}=%s").format(
        sql.SQL(", ").join(sql.SQL(x) for x in set_fields), sql.Identifier(pk_col)
    )
    params.append(winner.mid)
    cur.execute(uq, params)

    insert_cols = ["winner_master_id", "loser_master_id", "merge_phase", "merge_confidence", "merge_evidence"]
    insert_vals: List[object] = [winner.mid, loser.mid, phase, conf, json.dumps(ev)]
    if MERGE_LOG_HAS_REASON:
        insert_cols.append("merge_reason")
        insert_vals.append(phase)
    if MERGE_LOG_HAS_MERGED_BY:
        insert_cols.append("merged_by")
        insert_vals.append("dedup_master_employers.py")
    cur.execute(
        sql.SQL("INSERT INTO master_employer_merge_log ({}) VALUES ({})").format(
            sql.SQL(", ").join(sql.Identifier(c) for c in insert_cols),
            sql.SQL(", ").join(sql.Placeholder() for _ in insert_cols),
        ),
        insert_vals,
    )
    cur.execute(sql.SQL("DELETE FROM master_employers WHERE {}=%s").format(sql.Identifier(pk_col)), (loser.mid,))


def run_phase(conn, pk_col: str, include_labor_org: bool, args: argparse.Namespace, phase: str) -> Dict[str, int]:
    phase_key = {"1": "phase_1_ein", "2": "phase_2_exact"}[phase]
    with conn.cursor() as cur:
        c1, c2, base_g, base_m, base_r = progress_get(cur, phase_key)
    conn.commit()
    c1 = c1 if args.resume else None
    c2 = c2 if args.resume else None
    gp, me, re = base_g, base_m, base_r
    found, pairs = 0, 0
    start = time.time()

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
                        ).format(pk=sql.Identifier(pk_col)),
                        (c1, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT ein, array_agg({pk} ORDER BY {pk}) ids FROM master_employers "
                            "WHERE ein IS NOT NULL AND btrim(ein)<>'' "
                            "GROUP BY ein HAVING COUNT(*)>1 ORDER BY ein LIMIT %s"
                        ).format(pk=sql.Identifier(pk_col)),
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
                        ).format(pk=sql.Identifier(pk_col)),
                        (c1, c2, args.limit or 5000),
                    )
                else:
                    cur.execute(
                        sql.SQL(
                            "SELECT canonical_name, state::TEXT, array_agg({pk} ORDER BY {pk}) ids FROM master_employers "
                            "WHERE canonical_name IS NOT NULL AND btrim(canonical_name)<>'' AND state IS NOT NULL "
                            "GROUP BY canonical_name, state::TEXT HAVING COUNT(*)>1 ORDER BY canonical_name, state::TEXT LIMIT %s"
                        ).format(pk=sql.Identifier(pk_col)),
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
                rows = fetch_employers(cur, pk_col, ids, include_labor_org)
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
                            pk_col=pk_col,
                            include_labor_org=include_labor_org,
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
    conn, pk_col: str, include_labor_org: bool, args: argparse.Namespace,
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

    while True:
        if args.max_seconds and time.time() - start >= args.max_seconds:
            break
        with conn.cursor() as cur:
            set_timeouts(cur, args.statement_timeout_ms)
            if substep == "3a":
                # ZIP blocking: group by zip (first 5 digits)
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
                        ).format(pk=sql.Identifier(pk_col)),
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
                        ).format(pk=sql.Identifier(pk_col)),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], None, list(r[1])) for r in cur.fetchall()]

            elif substep == "3b":
                # City+State blocking
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
                        ).format(pk=sql.Identifier(pk_col)),
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
                        ).format(pk=sql.Identifier(pk_col)),
                        (args.limit or 5000,),
                    )
                blocks = [(r[0], r[1], list(r[2])) for r in cur.fetchall()]

            else:  # 3c: state-only fallback for records missing city AND zip
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
                        ).format(pk=sql.Identifier(pk_col)),
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
                        ).format(pk=sql.Identifier(pk_col)),
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
                rows = fetch_employers(cur, pk_col, ids, include_labor_org)
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
                # Build evidence and merge rule per sub-step
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
                            pk_col=pk_col,
                            include_labor_org=include_labor_org,
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


def run_phase3_cascade(
    conn, pk_col: str, include_labor_org: bool, args: argparse.Namespace,
) -> Dict[str, object]:
    """Phase 3: 3-step geographic cascade replacing old name+state fuzzy."""
    results = {}
    for substep, threshold, label in [
        ("3a", 0.82, "ZIP blocking"),
        ("3b", 0.85, "City+State blocking"),
        ("3c", 0.85, "State-only fallback"),
    ]:
        s = _run_phase3_substep(conn, pk_col, include_labor_org, args, substep, threshold)
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


def run_phase4(conn, pk_col: str, args: argparse.Namespace) -> Dict[str, object]:
    phase_key = "phase_4_quality"
    with conn.cursor() as cur:
        c1, c2, base_g, base_m, base_r = progress_get(cur, phase_key)
    conn.commit()

    last_pk = int(c1) if (args.resume and c1) else 0
    chunk_size = max(1000, int(args.batch_size))
    rows_updated = 0
    batches = 0
    started = time.time()

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
                      /* 81-100: 5+ sources, OR 4 sources + fully complete */
                      WHEN COALESCE(src.source_cnt, 0) >= 5
                        OR (COALESCE(src.source_cnt, 0) >= 4
                            AND m.employee_count IS NOT NULL
                            AND m.naics IS NOT NULL
                            AND m.city IS NOT NULL AND btrim(m.city) <> ''
                            AND m.state IS NOT NULL AND btrim(m.state) <> '')
                        THEN 100
                      /* 61-80: 4+ sources, OR 3 sources + fully complete */
                      WHEN COALESCE(src.source_cnt, 0) >= 4
                        OR (COALESCE(src.source_cnt, 0) >= 3
                            AND m.employee_count IS NOT NULL
                            AND m.naics IS NOT NULL
                            AND m.city IS NOT NULL AND btrim(m.city) <> ''
                            AND m.state IS NOT NULL AND btrim(m.state) <> '')
                        THEN 80
                      /* 41-60: 3+ sources, OR 2 sources + structurally useful */
                      WHEN COALESCE(src.source_cnt, 0) >= 3
                        OR (COALESCE(src.source_cnt, 0) >= 2
                            AND m.city IS NOT NULL AND btrim(m.city) <> ''
                            AND m.state IS NOT NULL AND btrim(m.state) <> ''
                            AND (m.employee_count IS NOT NULL OR m.naics IS NOT NULL))
                        THEN 60
                      /* 21-40: structurally useful -- location + (emp OR naics) */
                      WHEN m.city IS NOT NULL AND btrim(m.city) <> ''
                        AND m.state IS NOT NULL AND btrim(m.state) <> ''
                        AND (m.employee_count IS NOT NULL OR m.naics IS NOT NULL)
                        THEN 40
                      /* 0-20: sparse -- missing key structural fields */
                      ELSE 20
                    END,
                    updated_at = NOW()
                    FROM ids
                    LEFT JOIN src ON src.master_id = ids.master_id
                    WHERE m.{pk} = ids.master_id
                    RETURNING m.{pk}
                    """
                ).format(pk=sql.Identifier(pk_col)),
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
    global MERGE_LOG_HAS_REASON, MERGE_LOG_HAS_MERGED_BY
    MERGE_LOG_HAS_REASON = False
    MERGE_LOG_HAS_MERGED_BY = False
    try:
        with conn.cursor() as cur:
            pk_col = get_pk_col(cur)
            include_labor_org = table_col(cur, "master_employers", "is_labor_org")
            ensure_tables(cur, pk_col)
            MERGE_LOG_HAS_REASON = table_col(cur, "master_employer_merge_log", "merge_reason")
            MERGE_LOG_HAS_MERGED_BY = table_col(cur, "master_employer_merge_log", "merged_by")
        conn.commit()

        before = count_rows(conn, "master_employers")
        print(f"Starting master_employers row count: {before:,}")
        print(
            f"Options: phase={args.phase} dry_run={args.dry_run} resume={args.resume} "
            f"batch_size={args.batch_size} max_seconds={args.max_seconds}"
        )

        phases = ["1", "2", "3", "4"] if args.phase == "all" else [args.phase]

        if "1" in phases:
            s = run_phase(conn, pk_col, include_labor_org, args, "1")
            print("Phase 1 (EIN merge):")
            print(f"  Groups found: {s['groups_found']:,}")
            print(f"  Merges executed: {s['merges_executed']:,}")
            print(f"  Records eliminated: {s['records_eliminated']:,}")
        if "2" in phases:
            s = run_phase(conn, pk_col, include_labor_org, args, "2")
            print("Phase 2 (Name+State exact):")
            print(f"  Groups found: {s['groups_found']:,}")
            print(f"  Merges executed: {s['merges_executed']:,}")
            print(f"  Records eliminated: {s['records_eliminated']:,}")
        if "3" in phases:
            print("Phase 3 (Geographic cascade):")
            s3 = run_phase3_cascade(conn, pk_col, include_labor_org, args)
            t = s3["totals"]
            print(f"  Total candidate pairs: {t['candidate_pairs']:,}")
            print(f"  Total merges executed: {t['merges_executed']:,}")
            print(f"  Total records eliminated: {t['records_eliminated']:,}")
        if "4" in phases:
            s = run_phase4(conn, pk_col, args)
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
