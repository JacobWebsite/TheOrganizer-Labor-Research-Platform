import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

METHOD_RANK = {
    "EIN_EXACT": 100,
    "NAME_CITY_STATE_EXACT": 90,
    "NAME_STATE_EXACT": 80,
    "NAME_AGGRESSIVE_STATE": 60,
    "FUZZY_SPLINK_ADAPTIVE": 45,
    "FUZZY_TRIGRAM": 40,
}


def _table_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    return {r["column_name"] for r in cur.fetchall()}


def _timestamp_column(cols: set[str]) -> str:
    if "matched_at" in cols:
        return "matched_at"
    if "created_at" in cols:
        return "created_at"
    return "NULL::timestamp"


def fetch_duplicate_keys(cur):
    cur.execute(
        """
        SELECT source_system,
               source_id,
               COUNT(DISTINCT target_id) AS target_count
        FROM unified_match_log
        WHERE status = 'active'
        GROUP BY source_system, source_id
        HAVING COUNT(DISTINCT target_id) > 1
        ORDER BY target_count DESC, source_system, source_id
        """
    )
    return cur.fetchall()


def fetch_active_rows(cur, source_system: str, source_id: str, ts_expr: str):
    cur.execute(
        f"""
        SELECT id,
               source_system,
               source_id,
               target_id,
               match_method,
               confidence_score,
               {ts_expr} AS event_ts
        FROM unified_match_log
        WHERE status = 'active'
          AND source_system = %s
          AND source_id = %s
        """,
        (source_system, source_id),
    )
    return cur.fetchall()


def _to_float(value: Any) -> float:
    if value is None:
        return -1.0
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return -1.0


def _winner_sort_key(row: dict[str, Any]):
    method = (row.get("match_method") or "").upper()
    method_rank = METHOD_RANK.get(method, 0)
    conf = _to_float(row.get("confidence_score"))
    event_ts = row.get("event_ts") or datetime.min
    row_id = int(row.get("id") or 0)
    return (method_rank, conf, event_ts, row_id)


def choose_winner(rows: list[dict[str, Any]]):
    if not rows:
        return None
    return max(rows, key=_winner_sort_key)


def _supersede_sql(columns: set[str]) -> str:
    sets = ["status = 'superseded'"]
    if "superseded_by" in columns:
        sets.append("superseded_by = %s")
    if "superseded_reason" in columns:
        sets.append("superseded_reason = %s")
    sets.append(
        """evidence = COALESCE(evidence, '{}'::jsonb)
        || jsonb_build_object(
            'superseded_by_id', %s,
            'superseded_reason', %s,
            'superseded_at', NOW()::text
        )"""
    )
    return "UPDATE unified_match_log SET " + ", ".join(sets) + " WHERE id = ANY(%s)"


def supersede_losers(cur, loser_ids: list[int], winner_id: int, uml_columns: set[str]):
    if not loser_ids:
        return 0
    reason = "duplicate_source_best_match_wins"
    params: list[Any] = []
    if "superseded_by" in uml_columns:
        params.append(winner_id)
    if "superseded_reason" in uml_columns:
        params.append(reason)
    params.extend([winner_id, reason, loser_ids])
    cur.execute(_supersede_sql(uml_columns), params)
    return cur.rowcount


def run(commit: bool):
    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        uml_cols = _table_columns(cur, "unified_match_log")
        ts_expr = _timestamp_column(uml_cols)

        dup_keys = fetch_duplicate_keys(cur)
        duplicates_resolved = 0
        rows_superseded = 0
        by_source = Counter()
        by_method = Counter()

        for key in dup_keys:
            rows = fetch_active_rows(cur, key["source_system"], key["source_id"], ts_expr)
            winner = choose_winner(rows)
            if winner is None:
                continue
            winner_id = int(winner["id"])
            losers = [r for r in rows if int(r["id"]) != winner_id]
            loser_ids = [int(r["id"]) for r in losers]
            if not loser_ids:
                continue

            duplicates_resolved += 1
            by_source[key["source_system"]] += 1
            for loser in losers:
                by_method[(key["source_system"], loser.get("match_method") or "UNKNOWN")] += 1

            if commit:
                rows_superseded += supersede_losers(cur, loser_ids, winner_id, uml_cols)
            else:
                rows_superseded += len(loser_ids)

        print(f"Duplicate source keys found: {len(dup_keys):,}")
        print(f"Duplicate sets resolved: {duplicates_resolved:,}")
        print(f"Rows to supersede: {rows_superseded:,}")

        print("\nResolved sets by source_system:")
        for source, cnt in sorted(by_source.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {source}: {cnt:,}")

        print("\nSuperseded rows by source_system + method:")
        for (source, method), cnt in sorted(by_method.items(), key=lambda x: (-x[1], x[0][0], x[0][1])):
            print(f"  {source} | {method}: {cnt:,}")

        if commit:
            conn.commit()
            print("\nCommitted.")
        else:
            conn.rollback()
            print("\nDry-run complete (rolled back). Use --commit to persist.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Resolve duplicate active matches by best-match-wins")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run flag (default)")
    args = parser.parse_args()
    run(commit=args.commit)


if __name__ == "__main__":
    main()
