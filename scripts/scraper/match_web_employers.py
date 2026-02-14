"""
Checkpoint 4: Match web-extracted employers against existing database tables.

Matching tiers:
  1. Exact name+state against f7_employers_deduped
  2. Exact name+state against osha_establishments
  3. Fuzzy name+state against f7_employers_deduped (pg_trgm >= 0.55)
  4. Fuzzy name+state against osha_establishments (pg_trgm >= 0.55)
  5. Fuzzy name only (cross-state) against f7 (pg_trgm >= 0.70)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection


def run_matching(conn):
    cur = conn.cursor()

    # Get all unmatched web employers
    cur.execute("""
        SELECT we.id, we.employer_name, we.state, we.sector, we.web_profile_id
        FROM web_union_employers we
        WHERE we.match_status = 'PENDING_REVIEW'
        ORDER BY we.id
    """)
    employers = cur.fetchall()
    print(f"Matching {len(employers)} web employers...\n")

    stats = {
        'exact_f7': 0,
        'exact_osha': 0,
        'fuzzy_f7': 0,
        'fuzzy_osha': 0,
        'cross_state_f7': 0,
        'unmatched': 0,
    }

    for we_id, emp_name, state, sector, profile_id in employers:
        matched = False

        # ── Tier 1: Exact name+state against f7_employers_deduped ──
        cur.execute("""
            SELECT employer_id, employer_name, state
            FROM f7_employers_deduped
            WHERE UPPER(TRIM(employer_name)) = UPPER(TRIM(%s))
              AND state = %s
            LIMIT 1
        """, (emp_name, state))
        row = cur.fetchone()
        if row:
            update_match(cur, we_id, int(row[0]) if row[0] and row[0].isdigit() else None,
                        'MATCHED_F7_EXACT', row[1])
            stats['exact_f7'] += 1
            print(f"  [{we_id}] {emp_name[:40]:<40} -> F7 EXACT: {row[1][:35]} ({row[2]})")
            matched = True

        # ── Tier 1b: Also try employer_name_aggressive ──
        if not matched:
            cur.execute("""
                SELECT employer_id, employer_name, state
                FROM f7_employers_deduped
                WHERE UPPER(TRIM(employer_name_aggressive)) = UPPER(TRIM(%s))
                  AND state = %s
                LIMIT 1
            """, (emp_name, state))
            row = cur.fetchone()
            if row:
                update_match(cur, we_id, int(row[0]) if row[0] and row[0].isdigit() else None,
                            'MATCHED_F7_EXACT', row[1])
                stats['exact_f7'] += 1
                print(f"  [{we_id}] {emp_name[:40]:<40} -> F7 EXACT(agg): {row[1][:35]} ({row[2]})")
                matched = True

        # ── Tier 2: Exact name+state against osha_establishments ──
        if not matched:
            cur.execute("""
                SELECT establishment_id, estab_name, site_state
                FROM osha_establishments
                WHERE UPPER(TRIM(estab_name)) = UPPER(TRIM(%s))
                  AND site_state = %s
                LIMIT 1
            """, (emp_name, state))
            row = cur.fetchone()
            if row:
                update_match(cur, we_id, None, 'MATCHED_OSHA_EXACT', row[1],
                            osha_id=row[0])
                stats['exact_osha'] += 1
                print(f"  [{we_id}] {emp_name[:40]:<40} -> OSHA EXACT: {row[1][:35]} ({row[2]})")
                matched = True

        # ── Tier 3: Fuzzy name+state against f7 (pg_trgm) ──
        if not matched and state:
            cur.execute("""
                SELECT employer_id, employer_name, state,
                       similarity(UPPER(employer_name), UPPER(%%s)) as sim
                FROM f7_employers_deduped
                WHERE state = %%s
                  AND UPPER(employer_name) %%%% UPPER(%%s)
                ORDER BY sim DESC
                LIMIT 1
            """.replace('%%s', '%s').replace('%%%%', '%%'), (emp_name, state, emp_name))
            row = cur.fetchone()
            if row and row[3] >= 0.55:
                update_match(cur, we_id, int(row[0]) if row[0] and row[0].isdigit() else None,
                            'MATCHED_F7_FUZZY', row[1])
                stats['fuzzy_f7'] += 1
                print(f"  [{we_id}] {emp_name[:40]:<40} -> F7 FUZZY({row[3]:.2f}): {row[1][:35]} ({row[2]})")
                matched = True

        # ── Tier 4: Fuzzy name+state against osha ──
        if not matched and state:
            cur.execute("""
                SELECT establishment_id, estab_name, site_state,
                       similarity(UPPER(estab_name), UPPER(%%s)) as sim
                FROM osha_establishments
                WHERE site_state = %%s
                  AND UPPER(estab_name) %%%% UPPER(%%s)
                ORDER BY sim DESC
                LIMIT 1
            """.replace('%%s', '%s').replace('%%%%', '%%'), (emp_name, state, emp_name))
            row = cur.fetchone()
            if row and row[3] >= 0.55:
                update_match(cur, we_id, None, 'MATCHED_OSHA_FUZZY', row[1],
                            osha_id=row[0])
                stats['fuzzy_osha'] += 1
                print(f"  [{we_id}] {emp_name[:40]:<40} -> OSHA FUZZY({row[3]:.2f}): {row[1][:35]} ({row[2]})")
                matched = True

        # ── Tier 5: Cross-state fuzzy against f7 (higher threshold) ──
        if not matched:
            cur.execute("""
                SELECT employer_id, employer_name, state,
                       similarity(UPPER(employer_name), UPPER(%%s)) as sim
                FROM f7_employers_deduped
                WHERE UPPER(employer_name) %%%% UPPER(%%s)
                ORDER BY sim DESC
                LIMIT 1
            """.replace('%%s', '%s').replace('%%%%', '%%'), (emp_name, emp_name))
            row = cur.fetchone()
            if row and row[3] >= 0.70:
                update_match(cur, we_id, int(row[0]) if row[0] and row[0].isdigit() else None,
                            'MATCHED_F7_CROSS_STATE', row[1])
                stats['cross_state_f7'] += 1
                print(f"  [{we_id}] {emp_name[:40]:<40} -> F7 X-STATE({row[3]:.2f}): {row[1][:35]} ({row[2]})")
                matched = True

        if not matched:
            cur.execute("""
                UPDATE web_union_employers SET match_status = 'UNMATCHED' WHERE id = %s
            """, (we_id,))
            stats['unmatched'] += 1
            print(f"  [{we_id}] {emp_name[:40]:<40} -> UNMATCHED")

    conn.commit()
    return stats


def update_match(cur, we_id, matched_id, status, matched_name, osha_id=None):
    """Update web_union_employers with match result."""
    cur.execute("""
        UPDATE web_union_employers
        SET match_status = %s, matched_employer_id = %s
        WHERE id = %s
    """, (status, matched_id, we_id))


def print_summary(conn, stats):
    """Print Checkpoint 4 summary."""
    cur = conn.cursor()

    print(f"\n{'='*70}")
    print(f"CHECKPOINT 4: MATCH & SUMMARY")
    print(f"{'='*70}")

    print(f"\n--- EMPLOYER MATCHING ---")
    total_matched = sum(v for k, v in stats.items() if k != 'unmatched')
    total = sum(stats.values())
    for tier, count in stats.items():
        print(f"  {tier:<25} {count:>4}")
    print(f"  {'TOTAL MATCHED':<25} {total_matched:>4} / {total} ({100*total_matched/max(total,1):.0f}%)")

    print(f"\n--- UNION PROFILE MATCHING (from Checkpoint 1) ---")
    cur.execute("""
        SELECT match_status, count(*)
        FROM web_union_profiles
        GROUP BY match_status ORDER BY count(*) DESC
    """)
    for status, cnt in cur.fetchall():
        print(f"  {status:<30} {cnt:>4}")

    print(f"\n--- FULL DATA INVENTORY ---")
    tables = [
        ('web_union_profiles', 'Union profiles'),
        ('web_union_employers', 'Employers extracted'),
        ('web_union_contracts', 'Contracts/CBAs'),
        ('web_union_membership', 'Membership counts'),
        ('web_union_news', 'News items'),
        ('scrape_jobs', 'Scrape job logs'),
    ]
    for table, label in tables:
        cur.execute(f"SELECT count(*) FROM {table}")
        cnt = cur.fetchone()[0]
        print(f"  {label:<25} {cnt:>6}")

    # Show matched employers with their F7 union connections
    print(f"\n--- MATCHED EMPLOYERS WITH UNION LINKS ---")
    cur.execute("""
        SELECT we.employer_name, we.state, we.match_status,
               wp.union_name, wp.f_num,
               f7.latest_union_name
        FROM web_union_employers we
        JOIN web_union_profiles wp ON we.web_profile_id = wp.id
        LEFT JOIN f7_employers_deduped f7 ON f7.employer_id = we.matched_employer_id::text
        WHERE we.match_status LIKE 'MATCHED%%'
        ORDER BY we.employer_name
        LIMIT 25
    """)
    rows = cur.fetchall()
    if rows:
        for emp, st, status, union, fnum, f7_union in rows:
            link = f"f7_union={f7_union[:25]}" if f7_union else "no f7 link"
            print(f"  {emp[:35]:<35} {st:<4} {status:<25} <- {union[:25]} [{link}]")

    # Unmatched employers (potential new discoveries)
    print(f"\n--- UNMATCHED EMPLOYERS (potential new discoveries) ---")
    cur.execute("""
        SELECT we.employer_name, we.state, we.sector,
               wp.union_name
        FROM web_union_employers we
        JOIN web_union_profiles wp ON we.web_profile_id = wp.id
        WHERE we.match_status = 'UNMATCHED'
        ORDER BY we.employer_name
    """)
    rows = cur.fetchall()
    for emp, st, sector, union in rows:
        print(f"  {emp[:40]:<40} {st:<4} {sector or '-':<18} <- {union[:30]}")


if __name__ == '__main__':
    conn = get_connection()
    try:
        stats = run_matching(conn)
        print_summary(conn, stats)
    finally:
        conn.close()
