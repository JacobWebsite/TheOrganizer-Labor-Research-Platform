"""Master-employer dedup library.

Extracted from scripts/etl/dedup_master_employers.py so multiple callers
(the standalone dedup CLI, the rule-engine apply script, the LLM-gold
apply script, and the Pfizer back-fill bundled migration) can share one
merge primitive without each duplicating winner selection, FK re-pointing,
or merge_log construction.

API contract:
    merge_one() does NOT own transaction boundaries. The caller owns
    BEGIN/COMMIT/ROLLBACK.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from psycopg2 import sql
from rapidfuzz import fuzz


SOURCE_PRIORITY: Dict[str, int] = {
    "f7": 0, "sam": 1, "mergent": 2, "bmf": 3, "sec": 4, "990": 5, "gleif": 6,
}

EMP_COUNT_PRIORITY: Dict[str, int] = {
    "f7": 0, "mergent": 1, "sam": 2, "bmf": 3, "990": 4,
}


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


@dataclass(frozen=True)
class MergeContext:
    """DB schema feature-flags + caller identity for merge_one().

    Replaces module-level globals MERGE_LOG_HAS_REASON / MERGE_LOG_HAS_MERGED_BY
    + pk_col / include_labor_org args. Build once per script run via
    MergeContext.detect(cur) and pass to merge_one / fetch_employers.
    """
    pk_col: str
    include_labor_org: bool
    merge_log_has_reason: bool
    merge_log_has_merged_by: bool
    merged_by_label: str = "dedup_master_employers.py"

    @classmethod
    def detect(cls, cur, label: str = "dedup_master_employers.py") -> "MergeContext":
        return cls(
            pk_col=_get_pk_col(cur),
            include_labor_org=_table_col(cur, "master_employers", "is_labor_org"),
            merge_log_has_reason=_table_col(cur, "master_employer_merge_log", "merge_reason"),
            merge_log_has_merged_by=_table_col(cur, "master_employer_merge_log", "merged_by"),
            merged_by_label=label,
        )


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


def set_timeouts(cur, statement_ms: int = 120000, lock: str = "5s", idle_in_txn: str = "15min") -> None:
    cur.execute("SET lock_timeout = %s", (lock,))
    cur.execute("SET statement_timeout = %s", (int(statement_ms),))
    cur.execute("SET idle_in_transaction_session_timeout = %s", (idle_in_txn,))


def _table_col(cur, table: str, col: str) -> bool:
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


def _get_pk_col(cur) -> str:
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


def ensure_dedup_tables(cur, ctx: MergeContext) -> None:
    """Ensure progress + merge_log tables + dedup indexes exist. Idempotent."""
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
    pk = sql.Identifier(ctx.pk_col)
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_ein ON master_employers (ein, {pk}) "
            "WHERE ein IS NOT NULL AND btrim(ein)<>''"
        ).format(pk=pk)
    )
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_name_state "
            "ON master_employers (canonical_name, state, {pk})"
        ).format(pk=pk)
    )
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_zip ON master_employers (zip, {pk}) "
            "WHERE zip IS NOT NULL AND btrim(zip)<>''"
        ).format(pk=pk)
    )
    cur.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS idx_master_employers_dedup_city_state "
            "ON master_employers (city, state, {pk}) "
            "WHERE city IS NOT NULL AND btrim(city)<>''"
        ).format(pk=pk)
    )


def fetch_employers(cur, ctx: MergeContext, ids: Sequence[int]) -> List[Employer]:
    """Batch-load Employer dataclasses by master_id. Order of results is not guaranteed."""
    labor_col = sql.SQL(", COALESCE(m.is_labor_org,FALSE) AS is_labor_org") if ctx.include_labor_org else sql.SQL("")
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
    ).format(pk=sql.Identifier(ctx.pk_col), labor_col=labor_col)
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
                is_labor_org=(bool(r[16]) if ctx.include_labor_org else None),
            )
        )
    return out


def merge_one(
    cur,
    ctx: MergeContext,
    winner: Employer,
    loser: Employer,
    phase: str,
    conf: float,
    ev: Dict[str, object],
) -> None:
    """Merge `loser` into `winner` in one DB unit.

    Sequence:
      1. Move source_ids from loser to winner (ON CONFLICT update match_confidence).
      2. Delete loser's source_ids rows.
      3. Blend winner fields (longer-string-wins for text, OR-merge bools,
         source-priority for employee_count).
      4. Insert merge_log row with phase + confidence + evidence JSON.
      5. DELETE loser from master_employers.

    Does NOT commit. Caller owns the transaction.
    """
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
    if ctx.include_labor_org:
        set_fields.insert(-1, "is_labor_org=%s")
        params.append(bool((winner.is_labor_org or False) or (loser.is_labor_org or False)))

    uq = sql.SQL("UPDATE master_employers SET {} WHERE {}=%s").format(
        sql.SQL(", ").join(sql.SQL(x) for x in set_fields), sql.Identifier(ctx.pk_col)
    )
    params.append(winner.mid)
    cur.execute(uq, params)

    insert_cols = ["winner_master_id", "loser_master_id", "merge_phase", "merge_confidence", "merge_evidence"]
    insert_vals: List[object] = [winner.mid, loser.mid, phase, conf, json.dumps(ev)]
    if ctx.merge_log_has_reason:
        insert_cols.append("merge_reason")
        insert_vals.append(phase)
    if ctx.merge_log_has_merged_by:
        insert_cols.append("merged_by")
        insert_vals.append(ctx.merged_by_label)
    cur.execute(
        sql.SQL("INSERT INTO master_employer_merge_log ({}) VALUES ({})").format(
            sql.SQL(", ").join(sql.Identifier(c) for c in insert_cols),
            sql.SQL(", ").join(sql.Placeholder() for _ in insert_cols),
        ),
        insert_vals,
    )
    cur.execute(
        sql.SQL("DELETE FROM master_employers WHERE {}=%s").format(sql.Identifier(ctx.pk_col)),
        (loser.mid,),
    )
