"""Mandatory pre-impl FK enumeration for Phase B (per plan §B.2).

Lists:
  1. All declared FKs on master_employers.master_id
  2. Un-FK'd columns that LOOK like master_id refs (master_id, employer_id,
     comparable_employer_id, child_master_id, parent_master_id,
     winner_master_id, loser_master_id)
  3. Whether each candidate table has a UNIQUE constraint involving the
     master_id-like column (so REPOINT_TARGETS knows which need DELETE+UPDATE).

Read-only; safe to run anytime.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from db_config import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("1. Declared FKs on master_employers")
    print("=" * 70)
    cur.execute(
        """
        SELECT c.conrelid::regclass AS table_name,
               a.attname AS column_name,
               c.confdeltype AS on_delete,
               c.conname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.contype = 'f' AND c.confrelid = 'master_employers'::regclass
        ORDER BY 1, 2
        """
    )
    rows = cur.fetchall()
    print(f"  {len(rows)} declared FK columns")
    for r in rows:
        print(f"    {r[0]:<40s} {r[1]:<25s} on_delete={r[2]} ({r[3]})")

    print()
    print("=" * 70)
    print("2. Un-FK'd master_id-like columns (manual review needed)")
    print("=" * 70)
    cur.execute(
        """
        SELECT t.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema = 'public'
          AND c.column_name IN ('master_id', 'employer_id', 'comparable_employer_id',
                                'child_master_id', 'parent_master_id',
                                'winner_master_id', 'loser_master_id')
          AND t.table_type = 'BASE TABLE'
        ORDER BY 1, 2
        """
    )
    cols = cur.fetchall()

    fk_set = {(str(r[0]).strip('"').split('.')[-1], r[1]) for r in rows}
    for table, col in cols:
        is_fk = (table, col) in fk_set
        marker = "FK" if is_fk else "  "
        print(f"    [{marker}] {table:<40s} {col}")

    print()
    print("=" * 70)
    print("3. UNIQUE constraints involving master_id-like columns")
    print("=" * 70)
    cur.execute(
        """
        SELECT n.nspname || '.' || t.relname AS table_name,
               i.relname AS index_name,
               pg_get_indexdef(ix.indexrelid) AS definition
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND ix.indisunique
          AND (
            pg_get_indexdef(ix.indexrelid) ~* '\\bmaster_id\\b'
            OR pg_get_indexdef(ix.indexrelid) ~* '\\bemployer_id\\b'
            OR pg_get_indexdef(ix.indexrelid) ~* '\\bcomparable_employer_id\\b'
            OR pg_get_indexdef(ix.indexrelid) ~* '\\bchild_master_id\\b'
            OR pg_get_indexdef(ix.indexrelid) ~* '\\bparent_master_id\\b'
          )
        ORDER BY 1, 2
        """
    )
    uq_rows = cur.fetchall()
    print(f"  {len(uq_rows)} unique-index hits")
    for r in uq_rows:
        print(f"    {r[0]}")
        print(f"      {r[2]}")

    print()
    print("=" * 70)
    print("4. PRIMARY KEY columns matching master_id-like names")
    print("=" * 70)
    cur.execute(
        """
        SELECT c.conrelid::regclass AS table_name,
               a.attname AS column_name,
               c.conname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.contype = 'p'
          AND a.attname IN ('master_id', 'employer_id', 'comparable_employer_id',
                            'child_master_id', 'parent_master_id',
                            'winner_master_id', 'loser_master_id')
        ORDER BY 1, 2
        """
    )
    for r in cur.fetchall():
        print(f"    PK  {str(r[0]):<40s} {r[1]:<25s} ({r[2]})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
