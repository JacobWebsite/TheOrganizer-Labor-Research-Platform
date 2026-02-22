"""Show detailed info for each one-to-many crosswalk case."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

one_to_many_fnums = [12590, 18001, 23547, 49490, 56148, 65266]

for old_fnum in one_to_many_fnums:
    # Get the old union name from crosswalk
    cur.execute('SELECT DISTINCT f7_union_name FROM f7_fnum_crosswalk WHERE f7_fnum = %s', (old_fnum,))
    old_names = [r[0] for r in cur.fetchall()]
    old_label = old_names[0] if old_names else "?"

    # Get employer relations info
    cur.execute('''
        SELECT COUNT(*) AS rels,
               SUM(bargaining_unit_size) AS workers,
               MIN(notice_date) AS earliest,
               MAX(notice_date) AS latest
        FROM f7_union_employer_relations
        WHERE union_file_number = %s
    ''', (old_fnum,))
    rel_info = cur.fetchone()

    print("=" * 105)
    print("OLD FNUM %s: %s" % (old_fnum, old_label))
    print("  Relations: %s, Workers: %s, Date range: %s to %s" % (
        rel_info[0], rel_info[1], rel_info[2], rel_info[3]))

    # Sample employers under this old fnum
    cur.execute('''
        SELECT e.employer_name_aggressive, e.state, e.city, r.bargaining_unit_size, r.notice_date
        FROM f7_union_employer_relations r
        JOIN f7_employers_deduped e ON e.employer_id = r.employer_id
        WHERE r.union_file_number = %s
        ORDER BY r.bargaining_unit_size DESC NULLS LAST
        LIMIT 5
    ''', (old_fnum,))
    print("  Sample employers (top 5 by size):")
    for emp in cur.fetchall():
        name = (emp[0] or "")[:40]
        city = emp[2] or ""
        state = emp[1] or ""
        size = emp[3] or 0
        date = emp[4] or ""
        print("    %-40s %15s, %-3s  %6d wkrs  %s" % (name, city, state, size, date))

    # Now show each target with existing relations
    cur.execute('''
        SELECT c.matched_fnum, c.match_method, c.confidence,
               u.union_name, u.aff_abbr,
               (SELECT COUNT(*) FROM f7_union_employer_relations r2
                WHERE r2.union_file_number::text = u.f_num) AS existing_rels,
               (SELECT COALESCE(SUM(r2.bargaining_unit_size), 0) FROM f7_union_employer_relations r2
                WHERE r2.union_file_number::text = u.f_num) AS existing_workers
        FROM f7_fnum_crosswalk c
        JOIN unions_master u ON u.f_num = c.matched_fnum::text
        WHERE c.f7_fnum = %s
        ORDER BY c.confidence DESC NULLS LAST, c.matched_fnum
    ''', (old_fnum,))
    targets = cur.fetchall()
    print("\n  TARGETS (%d):" % len(targets))
    print("    %-8s %-10s %-42s %-15s %5s %10s %10s" % (
        "Fnum", "Aff", "Name", "Method", "Conf", "Exist.Rels", "Exist.Wkrs"))
    print("    %s %s %s %s %s %s %s" % (
        "-"*8, "-"*10, "-"*42, "-"*15, "-"*5, "-"*10, "-"*10))
    for t in targets:
        fnum, method, conf, uname, uabbr, erels, ewkrs = t
        print("    %-8s %-10s %-42s %-15s %5.2f %10d %10d" % (
            fnum, uabbr or "", (uname or "")[:42],
            method or "", conf or 0, erels or 0, ewkrs or 0))
    print()

cur.close()
conn.close()
