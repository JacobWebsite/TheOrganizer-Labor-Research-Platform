import argparse
import os
import sys
from collections import Counter

from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


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


def extract_similarity(evidence):
    if not isinstance(evidence, dict):
        return None
    for key in ("name_similarity", "trigram_sim", "similarity"):
        val = evidence.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Supersede low-quality FUZZY_TRIGRAM matches")
    parser.add_argument("--floor", type=float, default=0.75, help="Minimum allowed trigram similarity")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run flag (default)")
    args = parser.parse_args()

    conn = get_connection(cursor_factory=RealDictCursor)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        uml_cols = _table_columns(cur, "unified_match_log")

        cur.execute(
            """
            SELECT id, source_system, evidence
            FROM unified_match_log
            WHERE status = 'active'
              AND match_method = 'FUZZY_TRIGRAM'
            """
        )
        candidates = cur.fetchall()

        loser_ids = []
        by_source = Counter()
        for row in candidates:
            sim = extract_similarity(row.get("evidence"))
            if sim is None:
                continue
            if sim < args.floor:
                loser_ids.append(int(row["id"]))
                by_source[row["source_system"]] += 1

        print(f"Active FUZZY_TRIGRAM rows scanned: {len(candidates):,}")
        print(f"Rows below floor {args.floor:.2f}: {len(loser_ids):,}")
        print("By source_system:")
        for source, cnt in sorted(by_source.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {source}: {cnt:,}")

        if loser_ids:
            sets = ["status = 'superseded'"]
            params = []
            if "superseded_reason" in uml_cols:
                sets.append("superseded_reason = %s")
                params.append(f"below_trigram_floor_{args.floor:.2f}")
            sets.append(
                """evidence = COALESCE(evidence, '{}'::jsonb)
                || jsonb_build_object(
                    'superseded_reason', %s,
                    'superseded_at', NOW()::text
                )"""
            )
            params.append(f"below_trigram_floor_{args.floor:.2f}")
            params.append(loser_ids)

            cur.execute(
                f"UPDATE unified_match_log SET {', '.join(sets)} WHERE id = ANY(%s)",
                params,
            )
            affected = cur.rowcount
        else:
            affected = 0

        print(f"Rows updated in transaction: {affected:,}")

        if args.commit:
            conn.commit()
            print("Committed.")
        else:
            conn.rollback()
            print("Dry-run complete (rolled back). Use --commit to persist.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
