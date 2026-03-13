"""
Find locals where parent_fnum IS NULL but a matching intermediate exists.
Match by: same aff_abbr, intermediate's state = local's state.

Usage:
    py scripts/etl/relink_orphan_locals.py              # dry-run
    py scripts/etl/relink_orphan_locals.py --commit      # apply changes
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


INTERMEDIATE_CODES = ('DC', 'JC', 'CONF', 'D', 'C', 'SC', 'SA', 'BCTC')


def main():
    parser = argparse.ArgumentParser(description="Relink orphan locals to intermediates")
    parser.add_argument("--commit", action="store_true", help="Persist changes")
    args = parser.parse_args()

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Find orphan locals that could be linked to an intermediate
        # in the same affiliation and state
        cur.execute("""
            SELECT l.f_num AS local_fnum,
                   l.union_name AS local_name,
                   l.aff_abbr,
                   l.state,
                   i.f_num AS intermediate_fnum,
                   i.union_name AS intermediate_name,
                   TRIM(i.desig_name) AS inter_type
            FROM unions_master l
            JOIN unions_master i
              ON l.aff_abbr = i.aff_abbr
             AND l.state = i.state
             AND TRIM(i.desig_name) IN %s
            WHERE l.parent_fnum IS NULL
              AND TRIM(l.desig_name) NOT IN %s
              AND TRIM(l.desig_name) NOT IN ('NHQ', 'FED')
              AND l.aff_abbr IS NOT NULL
              AND l.state IS NOT NULL
            ORDER BY l.aff_abbr, l.state, l.f_num
        """, [INTERMEDIATE_CODES, INTERMEDIATE_CODES])
        candidates = cur.fetchall()

        # Deduplicate: if a local matches multiple intermediates in the same
        # state, prefer DC > JC > others (pick first by code priority)
        CODE_PRIORITY = {c: i for i, c in enumerate(INTERMEDIATE_CODES)}
        best = {}  # local_fnum -> (inter_fnum, inter_name, inter_type, priority)
        for row in candidates:
            lfnum = row[0]
            ifnum = row[4]
            iname = row[5]
            itype = row[6]
            prio = CODE_PRIORITY.get(itype, 99)
            if lfnum not in best or prio < best[lfnum][3]:
                best[lfnum] = (ifnum, iname, itype, prio)

        print("Orphan local relinking:")
        print("  Candidate links: %d" % len(best))

        if not best:
            print("  No orphan locals can be relinked.")
            return

        if not args.commit:
            # Show sample
            shown = 0
            for lfnum, (ifnum, iname, itype, _) in sorted(best.items()):
                if shown >= 20:
                    print("  ... and %d more" % (len(best) - 20))
                    break
                print("  %s -> %s (%s)" % (lfnum, ifnum, itype))
                shown += 1
            print("\n  [DRY-RUN] No changes made. Use --commit to persist.")
            return

        # Apply updates
        updates = [(ifnum, lfnum) for lfnum, (ifnum, _, _, _) in best.items()]
        cur.executemany(
            "UPDATE unions_master SET parent_fnum = %s WHERE f_num = %s",
            updates
        )
        conn.commit()
        print("  [COMMITTED] Relinked %d orphan locals." % len(updates))

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
