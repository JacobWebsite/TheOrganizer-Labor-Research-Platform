"""Check f7_union_employer_relations for duplicate rows and NULL notice_dates."""
import sys
sys.path.insert(0, r"C:\Users\jakew\Downloads\labor-data-project")
from db_config import get_connection

queries = [
    (
        "Query 1: Top 20 duplicate relations (same employer_id + union_file_number + notice_date)",
        """SELECT employer_id, union_file_number, notice_date, COUNT(*) as dupes
           FROM f7_union_employer_relations
           GROUP BY employer_id, union_file_number, notice_date
           HAVING COUNT(*) > 1
           ORDER BY dupes DESC
           LIMIT 20;"""
    ),
    (
        "Query 2: Top 20 NULL notice_date duplicates (same employer_id + union_file_number)",
        """SELECT employer_id, union_file_number, COUNT(*) as dupes
           FROM f7_union_employer_relations
           WHERE notice_date IS NULL
           GROUP BY employer_id, union_file_number
           HAVING COUNT(*) > 1
           LIMIT 20;"""
    ),
    (
        "Query 3: Total duplicate relation rows (excess count)",
        """SELECT SUM(cnt - 1) as total_duplicate_rows FROM (
               SELECT employer_id, union_file_number, notice_date, COUNT(*) as cnt
               FROM f7_union_employer_relations
               GROUP BY employer_id, union_file_number, notice_date
               HAVING COUNT(*) > 1
           ) sub;"""
    ),
    (
        "Query 6: Total relations with NULL notice_date",
        """SELECT COUNT(*) as null_notice_date_count
           FROM f7_union_employer_relations
           WHERE notice_date IS NULL;"""
    ),
]

with get_connection() as conn:
    cur = conn.cursor()
    for title, sql in queries:
        print("=" * 80)
        print(title)
        print("=" * 80)
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        if not rows:
            print("  (no rows returned)")
        else:
            header = "  " + " | ".join(f"{c:>30s}" for c in cols)
            print(header)
            print("  " + "-" * len(header.strip()))
            for row in rows:
                print("  " + " | ".join(f"{str(v):>30s}" for v in row))
        print(f"\n  Row count: {len(rows)}\n")
    cur.close()
