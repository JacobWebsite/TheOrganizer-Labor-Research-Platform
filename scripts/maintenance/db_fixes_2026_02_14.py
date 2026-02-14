"""
Database Fixes Script - 2026-02-14
Issues 4, 6, 7, 8, 9 from Audit Report

Issue 4: Add primary keys to f7_employers_deduped + match tables
Issue 6: Drop 17 duplicate indexes (~190 MB recovery)
Issue 7: Fix 3 views referencing raw f7_employers -> f7_employers_deduped
Issue 8: Drop 3 duplicate museum views (plural naming)
Issue 9: Drop 6 empty tables + ANALYZE 3 materialized views
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

# Track results
results = {
    'success': [],
    'skipped': [],
    'errors': [],
}

def log_ok(msg):
    results['success'].append(msg)
    print(f"  [OK] {msg}")

def log_skip(msg):
    results['skipped'].append(msg)
    print(f"  [SKIP] {msg}")

def log_err(msg):
    results['errors'].append(msg)
    print(f"  [ERROR] {msg}")


def issue_4_primary_keys(conn):
    """Issue 4: Add primary keys to f7_employers_deduped and match tables."""
    print("\n" + "=" * 70)
    print("ISSUE 4: Add Primary Keys")
    print("=" * 70)

    cur = conn.cursor()

    # --- f7_employers_deduped ---
    print("\n-- f7_employers_deduped --")

    # Check if PK already exists
    cur.execute("""
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE table_name = 'f7_employers_deduped' AND constraint_type = 'PRIMARY KEY'
    """)
    pk = cur.fetchone()
    if pk:
        log_skip(f"f7_employers_deduped already has PK: {pk[0]}")
    else:
        # Check for duplicate employer_id values
        cur.execute("""
            SELECT employer_id, COUNT(*) FROM f7_employers_deduped
            GROUP BY employer_id HAVING COUNT(*) > 1 LIMIT 5
        """)
        dupes = cur.fetchall()
        if dupes:
            log_err(f"f7_employers_deduped has {len(dupes)}+ duplicate employer_id values: {dupes}")
        else:
            # Check for NULLs
            cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE employer_id IS NULL")
            null_count = cur.fetchone()[0]
            if null_count > 0:
                log_err(f"f7_employers_deduped has {null_count} NULL employer_id values - cannot add PK")
            else:
                cur.execute("ALTER TABLE f7_employers_deduped ADD PRIMARY KEY (employer_id)")
                conn.commit()
                log_ok("Added PRIMARY KEY (employer_id) to f7_employers_deduped")

    # --- Match tables ---
    match_tables = ['whd_f7_matches', 'national_990_f7_matches', 'sam_f7_matches']

    for table in match_tables:
        print(f"\n-- {table} --")

        # Check if table exists
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = %s AND table_schema = 'public'
        """, (table,))
        if cur.fetchone()[0] == 0:
            log_skip(f"{table} does not exist")
            continue

        # Check if PK already exists
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = %s AND constraint_type = 'PRIMARY KEY'
        """, (table,))
        pk = cur.fetchone()
        if pk:
            log_skip(f"{table} already has PK: {pk[0]}")
            continue

        # Get column names
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table,))
        columns = [row[0] for row in cur.fetchall()]
        print(f"  Columns: {columns}")

        # Determine candidate key columns
        if table == 'whd_f7_matches':
            # WHD matches: case_id + f7_employer_id is the natural key
            candidate_cols = None
            if 'case_id' in columns and 'f7_employer_id' in columns:
                candidate_cols = ['case_id', 'f7_employer_id']
            elif 'whd_case_id' in columns and 'f7_employer_id' in columns:
                candidate_cols = ['whd_case_id', 'f7_employer_id']
            else:
                # Fall back: look for any ID-like columns
                id_cols = [c for c in columns if c.endswith('_id') or c == 'id']
                log_err(f"{table}: cannot determine key columns. ID columns found: {id_cols}")
                continue

        elif table == 'national_990_f7_matches':
            candidate_cols = None
            if 'ein' in columns and 'f7_employer_id' in columns:
                candidate_cols = ['ein', 'f7_employer_id']
            elif 'object_id' in columns and 'f7_employer_id' in columns:
                candidate_cols = ['object_id', 'f7_employer_id']
            else:
                id_cols = [c for c in columns if c.endswith('_id') or c == 'ein']
                log_err(f"{table}: cannot determine key columns. ID columns found: {id_cols}")
                continue

        elif table == 'sam_f7_matches':
            candidate_cols = None
            if 'uei' in columns and 'f7_employer_id' in columns:
                candidate_cols = ['uei', 'f7_employer_id']
            elif 'sam_uei' in columns and 'f7_employer_id' in columns:
                candidate_cols = ['sam_uei', 'f7_employer_id']
            else:
                id_cols = [c for c in columns if c.endswith('_id') or c == 'uei']
                log_err(f"{table}: cannot determine key columns. ID columns found: {id_cols}")
                continue

        key_str = ', '.join(candidate_cols)
        print(f"  Candidate key: ({key_str})")

        # Check for duplicates on candidate key
        where_nulls = ' AND '.join(f"{c} IS NOT NULL" for c in candidate_cols)
        group_by = ', '.join(candidate_cols)

        # Check for NULLs in key columns
        for col in candidate_cols:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
            null_count = cur.fetchone()[0]
            if null_count > 0:
                log_err(f"{table}.{col} has {null_count} NULL values - cannot use in PK")
                break
        else:
            # No NULLs found, check for duplicates
            cur.execute(f"""
                SELECT {group_by}, COUNT(*) FROM {table}
                GROUP BY {group_by} HAVING COUNT(*) > 1 LIMIT 5
            """)
            dupes = cur.fetchall()
            if dupes:
                dupe_count_query = f"""
                    SELECT COUNT(*) FROM (
                        SELECT {group_by} FROM {table}
                        GROUP BY {group_by} HAVING COUNT(*) > 1
                    ) sub
                """
                cur.execute(dupe_count_query)
                total_dupes = cur.fetchone()[0]
                print(f"  Found {total_dupes} duplicate key combinations. Deduplicating...")

                # Remove duplicates, keeping the one with the best match_tier or highest score
                # Find a ranking column
                rank_col = None
                for candidate in ['match_tier', 'match_score', 'similarity', 'score', 'confidence']:
                    if candidate in columns:
                        rank_col = candidate
                        break

                if rank_col:
                    # For match_tier, lower letter = better (A > B > C > D)
                    order = f"{rank_col} ASC" if rank_col == 'match_tier' else f"{rank_col} DESC"
                else:
                    # No ranking column; use ctid (physical row id) to keep first
                    rank_col = 'ctid'
                    order = 'ctid ASC'

                # Delete duplicates keeping the best row
                if rank_col == 'ctid':
                    delete_sql = f"""
                        DELETE FROM {table} a USING (
                            SELECT ctid, ROW_NUMBER() OVER (
                                PARTITION BY {group_by} ORDER BY ctid
                            ) rn FROM {table}
                        ) b
                        WHERE a.ctid = b.ctid AND b.rn > 1
                    """
                else:
                    delete_sql = f"""
                        DELETE FROM {table} a USING (
                            SELECT ctid, ROW_NUMBER() OVER (
                                PARTITION BY {group_by} ORDER BY {order}
                            ) rn FROM {table}
                        ) b
                        WHERE a.ctid = b.ctid AND b.rn > 1
                    """
                cur.execute(delete_sql)
                deleted = cur.rowcount
                conn.commit()
                print(f"  Deleted {deleted} duplicate rows (kept best by {rank_col})")

            # Now add the PK
            try:
                cur.execute(f"ALTER TABLE {table} ADD PRIMARY KEY ({key_str})")
                conn.commit()
                log_ok(f"Added PRIMARY KEY ({key_str}) to {table}")
            except Exception as e:
                conn.rollback()
                log_err(f"Failed to add PK to {table}: {e}")

    cur.close()


def issue_6_drop_duplicate_indexes(conn):
    """Issue 6: Drop 17 duplicate indexes (~190 MB recovery)."""
    print("\n" + "=" * 70)
    print("ISSUE 6: Drop Duplicate Indexes")
    print("=" * 70)

    cur = conn.cursor()

    indexes_to_drop = [
        ('idx_osha_est_name_norm_trgm', '53 MB', 'osha_establishments GIN trigram dup'),
        ('idx_sec_cik', '22 MB', 'sec_companies btree cik dup'),
        ('idx_f7_emp_trgm', '21 MB', 'f7_employers_deduped GIN trigram employer_name dup'),
        ('idx_f7_emp_agg_trgm', '20 MB', 'f7_employers_deduped GIN trigram employer_name_aggressive dup'),
        ('idx_osha_f7_est', '18 MB', 'osha_f7_matches btree establishment_id dup'),
        ('idx_employer_search_name', '13 MB', 'f7_employers btree lower(employer_name) dup'),
        ('idx_nlrb_part_employer', '13 MB', 'nlrb_participants btree matched_employer_id dup'),
        ('idx_nlrb_part_olms', '13 MB', 'nlrb_participants btree matched_union_fnum dup'),
        ('idx_ar_mem_rptid', '3 MB', 'ar_membership btree rpt_id dup'),
        ('idx_lm_fnum', '3 MB', 'lm_data btree f_num dup'),
        ('idx_employer_search_state', '2 MB', 'f7_employers btree state dup'),
        ('idx_lm_aff', '2 MB', 'lm_data btree aff_abbr dup'),
        ('idx_lm_year', '2 MB', 'lm_data btree year dup'),
        ('idx_f7_deduped_state', '2 MB', 'f7_employers_deduped btree state dup'),
        ('idx_f7_deduped_union_fnum', '2 MB', 'f7_employers_deduped btree union_file_number dup'),
        ('idx_fed_bu_agency', '<1 MB', 'federal_bargaining_units btree agency dup'),
        ('idx_fed_bu_union', '<1 MB', 'federal_bargaining_units btree union dup'),
    ]

    for idx_name, size, description in indexes_to_drop:
        # Check if index exists before dropping
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE indexname = %s AND schemaname = 'public'
        """, (idx_name,))
        exists = cur.fetchone()

        if not exists:
            log_skip(f"Index {idx_name} does not exist (already dropped?)")
        else:
            try:
                cur.execute(f"DROP INDEX IF EXISTS {idx_name}")
                conn.commit()
                log_ok(f"Dropped {idx_name} ({size}) -- {description}")
            except Exception as e:
                conn.rollback()
                log_err(f"Failed to drop {idx_name}: {e}")

    cur.close()


def issue_7_fix_views(conn):
    """Issue 7: Fix 3 views referencing raw f7_employers -> f7_employers_deduped."""
    print("\n" + "=" * 70)
    print("ISSUE 7: Fix Views Referencing Raw f7_employers")
    print("=" * 70)

    cur = conn.cursor()

    target_views = [
        'v_f7_employers_fully_adjusted',
        'v_f7_private_sector_reconciled',
        'v_state_overview',
    ]

    # Get current definitions
    cur.execute("""
        SELECT viewname, definition FROM pg_views
        WHERE viewname = ANY(%s) AND schemaname = 'public'
    """, (target_views,))
    view_defs = cur.fetchall()

    if not view_defs:
        log_skip("None of the 3 target views exist")
        cur.close()
        return

    # Check which columns exist in f7_employers vs f7_employers_deduped
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'f7_employers' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    f7_raw_cols = set(row[0] for row in cur.fetchall())

    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'f7_employers_deduped' AND table_schema = 'public'
        ORDER BY ordinal_position
    """)
    f7_dedup_cols = set(row[0] for row in cur.fetchall())

    print(f"\n  f7_employers columns ({len(f7_raw_cols)}): {sorted(f7_raw_cols)}")
    print(f"  f7_employers_deduped columns ({len(f7_dedup_cols)}): {sorted(f7_dedup_cols)}")

    missing_in_dedup = f7_raw_cols - f7_dedup_cols
    extra_in_dedup = f7_dedup_cols - f7_raw_cols
    if missing_in_dedup:
        print(f"  Columns in raw but NOT in deduped: {sorted(missing_in_dedup)}")
    if extra_in_dedup:
        print(f"  Columns in deduped but NOT in raw: {sorted(extra_in_dedup)}")

    # Process each view
    for viewname, definition in view_defs:
        print(f"\n-- {viewname} --")

        # Check if this view actually references f7_employers (not f7_employers_deduped)
        # We need to be careful to not replace f7_employers_deduped with f7_employers_deduped_deduped
        if 'f7_employers_deduped' in definition and 'f7_employers ' not in definition.replace('f7_employers_deduped', ''):
            log_skip(f"{viewname} already references f7_employers_deduped exclusively")
            continue

        print(f"  OLD definition:\n    {definition.strip()[:500]}")

        # Replace f7_employers TABLE references with f7_employers_deduped
        # Be careful not to:
        #   1. Double-replace f7_employers_deduped -> f7_employers_deduped_deduped
        #   2. Mangle column aliases like "AS f7_employers"
        # Strategy: use regex to only replace table references (preceded by FROM/JOIN/etc.)
        import re
        new_def = definition
        # Protect existing f7_employers_deduped references
        new_def = new_def.replace('f7_employers_deduped', '__PROTECTED_DEDUPED__')
        # Replace table references: FROM f7_employers, JOIN f7_employers, f7_employers.col
        # These patterns indicate table usage (not column aliases)
        new_def = re.sub(r'\bf7_employers\b(?=\s*\.|\s+WHERE|\s+GROUP|\s+ON|\s*\)|\s*$|\s+f7_employers)',
                         'f7_employers_deduped', new_def)
        # Also handle FROM/JOIN context
        new_def = re.sub(r'(FROM\s+)f7_employers\b', r'\1f7_employers_deduped', new_def)
        new_def = re.sub(r'(JOIN\s+)f7_employers\b', r'\1f7_employers_deduped', new_def)
        # Handle subquery references like "f7_employers.state"
        new_def = re.sub(r'\bf7_employers\.', 'f7_employers_deduped.', new_def)
        new_def = new_def.replace('__PROTECTED_DEDUPED__', 'f7_employers_deduped')

        print(f"  NEW definition:\n    {new_def.strip()[:500]}")

        # Check if definition actually changed
        if new_def == definition:
            log_skip(f"{viewname}: no f7_employers references found to replace")
            continue

        # Check for column references that exist in raw but not in deduped
        has_missing_col_issue = False
        for col in missing_in_dedup:
            if col in new_def:
                print(f"  WARNING: View references column '{col}' which is in f7_employers but not f7_employers_deduped")
                has_missing_col_issue = True

        if has_missing_col_issue:
            log_err(f"{viewname}: has column references missing from f7_employers_deduped - needs manual review")
            continue

        # Drop dependent views first, then recreate in order
        # Find views that depend on this one
        cur.execute("""
            SELECT DISTINCT dependent_view.relname AS view_name
            FROM pg_depend
            JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
            JOIN pg_class AS dependent_view ON pg_rewrite.ev_class = dependent_view.oid
            JOIN pg_class AS source_view ON pg_depend.refobjid = source_view.oid
            JOIN pg_namespace ON dependent_view.relnamespace = pg_namespace.oid
            WHERE source_view.relname = %s
            AND pg_namespace.nspname = 'public'
            AND dependent_view.relname != %s
        """, (viewname, viewname))
        dependents = [row[0] for row in cur.fetchall()]

        if dependents:
            print(f"  Dependent views: {dependents}")
            # Save dependent view definitions
            dependent_defs = {}
            for dep in dependents:
                cur.execute("SELECT definition FROM pg_views WHERE viewname = %s AND schemaname = 'public'", (dep,))
                dep_row = cur.fetchone()
                if dep_row:
                    dependent_defs[dep] = dep_row[0]

            # Drop dependents first (CASCADE would also work but is riskier)
            for dep in dependents:
                try:
                    cur.execute(f"DROP VIEW IF EXISTS {dep}")
                except Exception as e:
                    conn.rollback()
                    log_err(f"Failed to drop dependent view {dep}: {e}")
                    continue

        # Recreate the view
        try:
            cur.execute(f"DROP VIEW IF EXISTS {viewname}")
            create_sql = f"CREATE VIEW {viewname} AS {new_def}"
            cur.execute(create_sql)
            conn.commit()
            log_ok(f"Recreated {viewname} using f7_employers_deduped")

            # Recreate dependent views
            if dependents:
                for dep in dependents:
                    if dep in dependent_defs:
                        dep_def = dependent_defs[dep]
                        # Also fix references in dependent views (same careful regex approach)
                        dep_def_new = dep_def.replace('f7_employers_deduped', '__PROTECTED_DEDUPED__')
                        dep_def_new = re.sub(r'(FROM\s+)f7_employers\b', r'\1f7_employers_deduped', dep_def_new)
                        dep_def_new = re.sub(r'(JOIN\s+)f7_employers\b', r'\1f7_employers_deduped', dep_def_new)
                        dep_def_new = re.sub(r'\bf7_employers\.', 'f7_employers_deduped.', dep_def_new)
                        dep_def_new = dep_def_new.replace('__PROTECTED_DEDUPED__', 'f7_employers_deduped')
                        try:
                            cur.execute(f"CREATE VIEW {dep} AS {dep_def_new}")
                            conn.commit()
                            log_ok(f"Recreated dependent view {dep}")
                        except Exception as e:
                            conn.rollback()
                            log_err(f"Failed to recreate dependent view {dep}: {e}")
                            # Try with original definition as fallback
                            try:
                                cur.execute(f"CREATE VIEW {dep} AS {dep_def}")
                                conn.commit()
                                log_ok(f"Recreated dependent view {dep} (original definition, no f7 fix)")
                            except Exception as e2:
                                conn.rollback()
                                log_err(f"Failed to recreate dependent view {dep} even with original def: {e2}")

        except Exception as e:
            conn.rollback()
            log_err(f"Failed to recreate {viewname}: {e}")
            # Try to restore original
            try:
                cur.execute(f"CREATE VIEW {viewname} AS {definition}")
                conn.commit()
                log_err(f"Restored original {viewname} after failure")
            except Exception as e2:
                conn.rollback()
                log_err(f"CRITICAL: Could not restore {viewname}: {e2}")

    cur.close()


def issue_8_drop_museum_views(conn):
    """Issue 8: Drop 3 duplicate museum views (plural naming)."""
    print("\n" + "=" * 70)
    print("ISSUE 8: Drop Duplicate Museum Views")
    print("=" * 70)

    cur = conn.cursor()

    museum_views = [
        'v_museums_organizing_targets',
        'v_museums_target_stats',
        'v_museums_unionized',
    ]

    for vname in museum_views:
        # Check if it exists
        cur.execute("SELECT viewname FROM pg_views WHERE viewname = %s AND schemaname = 'public'", (vname,))
        exists = cur.fetchone()
        if not exists:
            log_skip(f"{vname} does not exist (already dropped?)")
        else:
            try:
                cur.execute(f"DROP VIEW IF EXISTS {vname}")
                conn.commit()
                log_ok(f"Dropped duplicate view {vname}")
            except Exception as e:
                conn.rollback()
                log_err(f"Failed to drop {vname}: {e}")

    # Verify singular versions still exist
    singular_views = ['v_museum_organizing_targets', 'v_museum_target_stats', 'v_museum_unionized']
    for vname in singular_views:
        cur.execute("SELECT viewname FROM pg_views WHERE viewname = %s AND schemaname = 'public'", (vname,))
        exists = cur.fetchone()
        if exists:
            print(f"  [VERIFY] Singular view {vname} exists (kept)")
        else:
            print(f"  [WARN] Singular view {vname} does NOT exist")

    cur.close()


def issue_9_drop_empty_tables(conn):
    """Issue 9: Drop 6 empty tables."""
    print("\n" + "=" * 70)
    print("ISSUE 9: Drop Empty Tables")
    print("=" * 70)

    cur = conn.cursor()

    empty_tables = [
        'employer_ein_crosswalk',
        'sic_naics_xwalk',
        'union_affiliation_naics',
        'union_employer_history',
        'vr_employer_match_staging',
        'vr_union_match_staging',
    ]

    for tname in empty_tables:
        # Verify table exists and is actually empty
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = %s AND table_schema = 'public'
        """, (tname,))
        exists = cur.fetchone()[0]

        if not exists:
            log_skip(f"{tname} does not exist (already dropped?)")
            continue

        # Double-check it's empty
        try:
            cur.execute(f"SELECT COUNT(*) FROM {tname}")
            row_count = cur.fetchone()[0]
        except Exception as e:
            conn.rollback()
            log_err(f"Cannot count rows in {tname}: {e}")
            continue

        if row_count > 0:
            log_err(f"{tname} has {row_count} rows - NOT EMPTY, skipping drop")
            continue

        # Check for dependent views
        cur.execute("""
            SELECT DISTINCT dependent_view.relname
            FROM pg_depend
            JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
            JOIN pg_class AS dependent_view ON pg_rewrite.ev_class = dependent_view.oid
            JOIN pg_class AS source_table ON pg_depend.refobjid = source_table.oid
            JOIN pg_namespace ON dependent_view.relnamespace = pg_namespace.oid
            WHERE source_table.relname = %s
            AND pg_namespace.nspname = 'public'
            AND dependent_view.relkind = 'v'
        """, (tname,))
        deps = [row[0] for row in cur.fetchall()]
        if deps:
            log_err(f"{tname} has dependent views {deps} - skipping drop")
            continue

        try:
            cur.execute(f"DROP TABLE IF EXISTS {tname}")
            conn.commit()
            log_ok(f"Dropped empty table {tname}")
        except Exception as e:
            conn.rollback()
            log_err(f"Failed to drop {tname}: {e}")

    cur.close()


def analyze_materialized_views(conn):
    """ANALYZE 3 materialized views."""
    print("\n" + "=" * 70)
    print("BONUS: ANALYZE Materialized Views")
    print("=" * 70)

    cur = conn.cursor()

    mat_views = ['mv_employer_features', 'mv_employer_search', 'mv_whd_employer_agg']

    for mv in mat_views:
        # Check if it exists
        cur.execute("""
            SELECT matviewname FROM pg_matviews
            WHERE matviewname = %s AND schemaname = 'public'
        """, (mv,))
        exists = cur.fetchone()
        if not exists:
            log_skip(f"Materialized view {mv} does not exist")
            continue

        try:
            cur.execute(f"ANALYZE {mv}")
            conn.commit()
            log_ok(f"ANALYZE {mv} completed")
        except Exception as e:
            conn.rollback()
            log_err(f"Failed to ANALYZE {mv}: {e}")

    cur.close()


def print_summary():
    """Print final summary."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\n  Successful operations: {len(results['success'])}")
    for msg in results['success']:
        print(f"    + {msg}")

    if results['skipped']:
        print(f"\n  Skipped (already done or N/A): {len(results['skipped'])}")
        for msg in results['skipped']:
            print(f"    ~ {msg}")

    if results['errors']:
        print(f"\n  ERRORS: {len(results['errors'])}")
        for msg in results['errors']:
            print(f"    ! {msg}")
    else:
        print("\n  No errors.")

    print(f"\n  Total: {len(results['success'])} ok, {len(results['skipped'])} skipped, {len(results['errors'])} errors")
    print("=" * 70)


def main():
    print("Database Fixes Script - 2026-02-14")
    print("Database: olms_multiyear (PostgreSQL)")
    print("Issues: 4, 6, 7, 8, 9 from Audit Report")

    conn = get_connection()
    conn.autocommit = False

    try:
        issue_4_primary_keys(conn)
        issue_6_drop_duplicate_indexes(conn)
        issue_7_fix_views(conn)
        issue_8_drop_museum_views(conn)
        issue_9_drop_empty_tables(conn)
        analyze_materialized_views(conn)
        print_summary()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    return len(results['errors'])


if __name__ == '__main__':
    sys.exit(main())
