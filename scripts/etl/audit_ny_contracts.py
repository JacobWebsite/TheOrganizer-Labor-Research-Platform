"""Audit ny_state_contracts and nyc_contracts tables: schema, provenance, coverage, match quality."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

TABLES = ["ny_state_contracts", "nyc_contracts"]


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def exists(cur, table):
    cur.execute(
        "SELECT to_regclass(%s) IS NOT NULL",
        (f"public.{table}",),
    )
    return cur.fetchone()[0]


def columns(cur, table):
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return cur.fetchall()


def row_count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


def date_range(cur, table, col):
    cur.execute(f"SELECT MIN({col}), MAX({col}) FROM {table}")
    return cur.fetchone()


def sample(cur, table, n=3):
    cur.execute(f"SELECT * FROM {table} LIMIT {n}")
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def freshness(cur, table):
    # schema-agnostic: return all columns for any row that mentions this table
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='data_source_freshness'
        ORDER BY ordinal_position
        """
    )
    cols = [r[0] for r in cur.fetchall()]
    if not cols:
        return [("[no data_source_freshness table]",)]
    col_list = ", ".join(cols)
    # search any text-ish column for the table name
    where_parts = [f"{c}::text ILIKE %s" for c in cols]
    where = " OR ".join(where_parts)
    params = tuple([f"%{table}%"] * len(cols))
    cur.execute(f"SELECT {col_list} FROM data_source_freshness WHERE {where}", params)
    rows = cur.fetchall()
    return [("columns: " + col_list,)] + rows


def match_coverage(cur, table, match_col):
    cur.execute(
        f"""
        SELECT
          COUNT(*) AS total,
          COUNT({match_col}) AS matched,
          ROUND(100.0 * COUNT({match_col}) / NULLIF(COUNT(*), 0), 2) AS pct
        FROM {table}
        """
    )
    return cur.fetchone()


def uml_coverage(cur, table):
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='unified_match_log'
        """
    )
    cols = {r[0] for r in cur.fetchall()}
    if not cols:
        return [("[no unified_match_log table]",)]
    src_col = "source_system" if "source_system" in cols else ("source" if "source" in cols else None)
    active_pred = "AND is_active = TRUE" if "is_active" in cols else ""
    if not src_col:
        return [("[no source_system column]",)]
    cur.execute(
        f"""
        SELECT {src_col}, COUNT(*)
        FROM unified_match_log
        WHERE {src_col} ILIKE %s {active_pred}
        GROUP BY {src_col}
        """,
        (f"%{table}%",),
    )
    return cur.fetchall()


def distinct_vendors(cur, table, col):
    cur.execute(f"SELECT COUNT(DISTINCT {col}) FROM {table}")
    return cur.fetchone()[0]


def top_vendors(cur, table, col, n=5):
    cur.execute(
        f"""
        SELECT {col}, COUNT(*) AS n
        FROM {table}
        GROUP BY {col}
        ORDER BY n DESC
        LIMIT {n}
        """
    )
    return cur.fetchall()


def main():
    conn = get_connection()
    cur = conn.cursor()

    for table in TABLES:
        section(f"TABLE: {table}")

        if not exists(cur, table):
            print("  [MISSING] table does not exist")
            continue

        cols = columns(cur, table)
        print(f"\n-- schema ({len(cols)} columns) --")
        for c in cols:
            print(f"  {c[0]:<30} {c[1]:<20} null={c[2]}")

        n = row_count(cur, table)
        print(f"\n-- row count: {n:,}")

        print("\n-- freshness log --")
        fr = freshness(cur, table)
        if not fr:
            print("  [NONE] no entry in data_source_freshness")
        else:
            for row in fr:
                print(f"  {row}")

        # Try to find any date-ish column
        date_cols = [c[0] for c in cols if "date" in c[0].lower() or "year" in c[0].lower() or "loaded" in c[0].lower()]
        if date_cols:
            print("\n-- date ranges --")
            for dc in date_cols:
                try:
                    mn, mx = date_range(cur, table, dc)
                    print(f"  {dc}: {mn} .. {mx}")
                except Exception as e:
                    print(f"  {dc}: [err: {e}]")
                    conn.rollback()

        # Vendor name column guessing
        name_cols = [c[0] for c in cols if any(k in c[0].lower() for k in ["vendor", "payee", "supplier", "contractor", "name", "employer"])]
        if name_cols:
            print("\n-- vendor columns --")
            for nc in name_cols[:3]:
                try:
                    dv = distinct_vendors(cur, table, nc)
                    print(f"  {nc}: {dv:,} distinct values")
                except Exception as e:
                    print(f"  {nc}: [err: {e}]")
                    conn.rollback()
            for nc in name_cols[:1]:
                try:
                    print(f"\n-- top 5 by {nc} --")
                    for v in top_vendors(cur, table, nc):
                        print(f"  {v[1]:>6}  {v[0]}")
                except Exception as e:
                    print(f"  [err: {e}]")
                    conn.rollback()

        # Check for master_id / f7_employer_id linkage column
        link_cols = [c[0] for c in cols if c[0] in ("master_id", "f7_employer_id", "employer_id", "matched_master_id")]
        if link_cols:
            print("\n-- inline match coverage --")
            for lc in link_cols:
                try:
                    tot, mat, pct = match_coverage(cur, table, lc)
                    print(f"  {lc}: {mat:,}/{tot:,} ({pct}%)")
                except Exception as e:
                    print(f"  {lc}: [err: {e}]")
                    conn.rollback()
        else:
            print("\n-- inline match coverage: [NONE] no master_id/f7_employer_id/employer_id column")

        # Check unified_match_log for this source
        print(f"\n-- unified_match_log entries (ILIKE '%{table}%') --")
        uml = uml_coverage(cur, table)
        if not uml:
            print("  [NONE] not present in unified_match_log")
        else:
            for row in uml:
                print(f"  {row}")

        # Sample
        print("\n-- first 2 rows --")
        try:
            colnames, rows = sample(cur, table, 2)
            for i, r in enumerate(rows):
                print(f"  row {i}:")
                for cn, val in zip(colnames, r):
                    s = str(val)
                    if len(s) > 80:
                        s = s[:77] + "..."
                    print(f"    {cn}: {s}")
        except Exception as e:
            print(f"  [err: {e}]")
            conn.rollback()

    section("CROSS-CHECK: matching pipeline source adapters")
    cur.execute(
        """
        SELECT source_system, COUNT(*) AS n
        FROM unified_match_log
        WHERE source_system ILIKE '%contract%'
          OR source_system ILIKE '%ny_%'
          OR source_system ILIKE '%nyc_%'
        GROUP BY source_system
        ORDER BY n DESC
        """
    )
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]:<40} {r[1]:>10,}")
    else:
        print("  [NONE]")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
