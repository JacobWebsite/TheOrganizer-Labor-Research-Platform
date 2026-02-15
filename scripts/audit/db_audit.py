import os
"""
Comprehensive Database Audit for olms_multiyear
================================================
Audits all tables, views, indexes, crosswalk coverage, and scoring stats.
"""

import psycopg2
import psycopg2.extras
import sys

DB_CONFIG = {
    "dbname": "olms_multiyear",
    "user": "postgres",
    "password": os.environ.get('DB_PASSWORD', ''),
    "host": "localhost",
}

KEY_TABLES = [
    "f7_enhanced",
    "corporate_identifier_crosswalk",
    "corporate_hierarchy",
    "gleif_entities",
    "gleif_ownership_links",
    "mergent_intellect",
    "sec_registrants",
    "whd_cases",
    "usaspending_recipients",
    "qcew_data",
]

# NYC tables discovered dynamically
NYC_PREFIX = "nyc_"

SEPARATOR = "=" * 90
SUB_SEP = "-" * 90


def connect():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_client_encoding("UTF8")
        return conn
    except Exception as e:
        print(f"ERROR connecting to database: {e}")
        sys.exit(1)


def section(title):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def subsection(title):
    print(f"\n{SUB_SEP}")
    print(f"  {title}")
    print(SUB_SEP)


# -------------------------------------------------------------------------
# 1. ALL TABLES WITH ROW COUNTS
# -------------------------------------------------------------------------
def audit_all_tables(cur):
    section("1. ALL TABLES WITH ROW COUNTS")

    cur.execute("""
        SELECT schemaname, tablename
        FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, tablename
    """)
    tables = cur.fetchall()

    results = []
    for schema, table in tables:
        full_name = f"{schema}.{table}" if schema != "public" else table
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            count = cur.fetchone()[0]
        except Exception as e:
            count = f"ERROR: {e}"
            cur.connection.rollback()
        results.append((full_name, count))

    # Sort by row count descending (errors at bottom)
    def sort_key(x):
        return x[1] if isinstance(x[1], int) else -1

    results.sort(key=sort_key, reverse=True)

    print(f"\n{'Table':<55} {'Row Count':>15}")
    print(f"{'-'*55} {'-'*15}")
    total_rows = 0
    for name, count in results:
        if isinstance(count, int):
            print(f"{name:<55} {count:>15,}")
            total_rows += count
        else:
            print(f"{name:<55} {str(count):>15}")
    print(f"{'-'*55} {'-'*15}")
    print(f"{'TOTAL (' + str(len(results)) + ' tables)':<55} {total_rows:>15,}")


# -------------------------------------------------------------------------
# 2. KEY TABLE DETAILS (columns, types, NULLs)
# -------------------------------------------------------------------------
def audit_key_tables(cur):
    section("2. KEY TABLE DETAILS")

    # Discover NYC tables
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'nyc_%%'
        ORDER BY tablename
    """)
    nyc_tables = [r[0] for r in cur.fetchall()]

    all_key = KEY_TABLES + [t for t in nyc_tables if t not in KEY_TABLES]

    for table in all_key:
        # Check existence
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'public' AND tablename = %s
            )
        """, (table,))
        if not cur.fetchone()[0]:
            subsection(f"TABLE: {table}  -- DOES NOT EXIST")
            continue

        # Row count
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        row_count = cur.fetchone()[0]

        subsection(f"TABLE: {table}  ({row_count:,} rows)")

        # Columns and types
        cur.execute("""
            SELECT column_name, data_type, character_maximum_length,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        columns = cur.fetchall()

        print(f"\n  {'Column':<40} {'Type':<25} {'Nullable':<10} {'Default':<20}")
        print(f"  {'-'*40} {'-'*25} {'-'*10} {'-'*20}")

        col_names = []
        for col_name, data_type, max_len, nullable, default in columns:
            type_str = data_type
            if max_len:
                type_str += f"({max_len})"
            default_str = str(default)[:18] if default else ""
            print(f"  {col_name:<40} {type_str:<25} {nullable:<10} {default_str:<20}")
            col_names.append(col_name)

        # NULL counts for all columns (for tables under 10M rows)
        if row_count > 0 and row_count < 10_000_000:
            null_parts = ", ".join(
                f'SUM(CASE WHEN "{c}" IS NULL THEN 1 ELSE 0 END) AS "{c}_nulls"'
                for c in col_names
            )
            try:
                cur.execute(f'SELECT {null_parts} FROM "{table}"')
                null_counts = cur.fetchone()

                print(f"\n  NULL COUNTS:")
                print(f"  {'Column':<40} {'NULLs':>12} {'% NULL':>10}")
                print(f"  {'-'*40} {'-'*12} {'-'*10}")
                for i, col_name in enumerate(col_names):
                    nc = null_counts[i]
                    pct = (nc / row_count * 100) if row_count > 0 else 0
                    # Only show columns with some NULLs or important columns
                    if nc > 0 or row_count == 0:
                        print(f"  {col_name:<40} {nc:>12,} {pct:>9.1f}%")
            except Exception as e:
                print(f"  ERROR computing NULLs: {e}")
                cur.connection.rollback()


# -------------------------------------------------------------------------
# 3. VIEWS AND MATERIALIZED VIEWS
# -------------------------------------------------------------------------
def audit_views(cur):
    section("3. VIEWS AND MATERIALIZED VIEWS")

    # Regular views
    cur.execute("""
        SELECT schemaname, viewname
        FROM pg_views
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, viewname
    """)
    views = cur.fetchall()

    if views:
        print(f"\n  Regular Views ({len(views)}):")
        for schema, view in views:
            full_name = f"{schema}.{view}" if schema != "public" else view
            # Try to get row count
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{view}"')
                count = cur.fetchone()[0]
                print(f"    {full_name:<55} {count:>12,} rows")
            except Exception as e:
                print(f"    {full_name:<55} (error: {e})")
                cur.connection.rollback()
    else:
        print("\n  No regular views found.")

    # Materialized views
    cur.execute("""
        SELECT schemaname, matviewname
        FROM pg_matviews
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY schemaname, matviewname
    """)
    matviews = cur.fetchall()

    if matviews:
        print(f"\n  Materialized Views ({len(matviews)}):")
        for schema, mv in matviews:
            full_name = f"{schema}.{mv}" if schema != "public" else mv
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{mv}"')
                count = cur.fetchone()[0]
                print(f"    {full_name:<55} {count:>12,} rows")
            except Exception as e:
                print(f"    {full_name:<55} (error: {e})")
                cur.connection.rollback()
    else:
        print("\n  No materialized views found.")


# -------------------------------------------------------------------------
# 4. INDEXES
# -------------------------------------------------------------------------
def audit_indexes(cur):
    section("4. INDEXES")

    cur.execute("""
        SELECT
            t.relname AS table_name,
            i.relname AS index_name,
            ix.indisunique AS is_unique,
            ix.indisprimary AS is_primary,
            pg_get_indexdef(ix.indexrelid) AS index_def
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY t.relname, i.relname
    """)
    indexes = cur.fetchall()

    if indexes:
        current_table = None
        for table_name, index_name, is_unique, is_primary, index_def in indexes:
            if table_name != current_table:
                print(f"\n  Table: {table_name}")
                current_table = table_name
            flags = []
            if is_primary:
                flags.append("PK")
            elif is_unique:
                flags.append("UNIQUE")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            # Truncate long index defs
            if len(index_def) > 100:
                index_def = index_def[:97] + "..."
            print(f"    {index_name}{flag_str}")
            print(f"      {index_def}")
        print(f"\n  Total indexes: {len(indexes)}")
    else:
        print("\n  No indexes found.")


# -------------------------------------------------------------------------
# 5. CROSSWALK COVERAGE STATS
# -------------------------------------------------------------------------
def audit_crosswalk(cur):
    section("5. CROSSWALK COVERAGE")

    # Check if tables exist
    for tbl in ["corporate_identifier_crosswalk", "f7_enhanced"]:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'public' AND tablename = %s
            )
        """, (tbl,))
        if not cur.fetchone()[0]:
            print(f"\n  Table '{tbl}' does not exist - skipping crosswalk audit.")
            return

    # Total F7 employers
    cur.execute("SELECT COUNT(*) FROM f7_enhanced")
    total_f7 = cur.fetchone()[0]

    # Total crosswalk rows
    cur.execute("SELECT COUNT(*) FROM corporate_identifier_crosswalk")
    total_xwalk = cur.fetchone()[0]

    print(f"\n  Total F7 employers:          {total_f7:>12,}")
    print(f"  Total crosswalk rows:        {total_xwalk:>12,}")

    # Get crosswalk columns to check which identifier columns exist
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'corporate_identifier_crosswalk'
    """)
    xwalk_cols = [r[0] for r in cur.fetchall()]

    # Coverage for each identifier type
    id_columns = {
        "gleif_lei": "LEI (GLEIF)",
        "mergent_duns": "DUNS (Mergent)",
        "sec_cik": "CIK (SEC)",
        "ein": "EIN",
        "is_federal_contractor": "Federal Contractor Flag",
        "federal_obligations": "Federal Obligations",
        "federal_contract_count": "Federal Contract Count",
        "usaspending_uei": "UEI (USASpending)",
    }

    print(f"\n  {'Identifier':<30} {'Non-NULL':>12} {'% of Xwalk':>12} {'% of F7':>10}")
    print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*10}")

    for col, label in id_columns.items():
        if col not in xwalk_cols:
            print(f"  {label:<30} {'(col missing)':>12}")
            continue

        if col == "is_federal_contractor":
            # Boolean - count TRUE
            cur.execute(f"""
                SELECT COUNT(*) FROM corporate_identifier_crosswalk
                WHERE {col} = TRUE
            """)
        else:
            cur.execute(f"""
                SELECT COUNT(*) FROM corporate_identifier_crosswalk
                WHERE {col} IS NOT NULL
            """)
        count = cur.fetchone()[0]
        pct_xwalk = (count / total_xwalk * 100) if total_xwalk > 0 else 0
        pct_f7 = (count / total_f7 * 100) if total_f7 > 0 else 0
        print(f"  {label:<30} {count:>12,} {pct_xwalk:>11.1f}% {pct_f7:>9.1f}%")

    # Distinct F7 employers in crosswalk
    # Check what the F7 join column is called
    f7_join_candidates = ["f7_employer_id", "employer_id", "f7_id", "id"]
    f7_join_col = None
    for c in f7_join_candidates:
        if c in xwalk_cols:
            f7_join_col = c
            break

    if f7_join_col:
        cur.execute(f"""
            SELECT COUNT(DISTINCT {f7_join_col})
            FROM corporate_identifier_crosswalk
        """)
        distinct_f7 = cur.fetchone()[0]
        pct = (distinct_f7 / total_f7 * 100) if total_f7 > 0 else 0
        print(f"\n  Distinct F7 employers in crosswalk: {distinct_f7:,} / {total_f7:,} ({pct:.1f}%)")
        print(f"  F7 join column: {f7_join_col}")

    # Multi-source coverage
    subsection("Multi-Source Coverage (employers with 2+ identifier types)")
    coverage_parts = []
    for col in ["gleif_lei", "mergent_duns", "sec_cik", "ein"]:
        if col in xwalk_cols:
            coverage_parts.append(f"(CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END)")
    if coverage_parts and f7_join_col:
        sum_expr = " + ".join(coverage_parts)
        cur.execute(f"""
            SELECT
                source_count,
                COUNT(*) AS employers
            FROM (
                SELECT {f7_join_col}, ({sum_expr}) AS source_count
                FROM corporate_identifier_crosswalk
            ) sub
            GROUP BY source_count
            ORDER BY source_count
        """)
        rows = cur.fetchall()
        print(f"\n  {'# ID Types':>12} {'Employers':>12}")
        print(f"  {'-'*12} {'-'*12}")
        for sc, emp in rows:
            print(f"  {sc:>12} {emp:>12,}")


# -------------------------------------------------------------------------
# 6. MATCHING / SCORING TABLES
# -------------------------------------------------------------------------
def audit_matching_scoring(cur):
    section("6. MATCHING / SCORING TABLES")

    # Find tables related to matching/scoring
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND (
            tablename LIKE '%%match%%'
            OR tablename LIKE '%%score%%'
            OR tablename LIKE '%%splink%%'
            OR tablename LIKE '%%dedup%%'
            OR tablename LIKE '%%merge%%'
            OR tablename LIKE '%%link%%'
            OR tablename LIKE '%%pair%%'
            OR tablename LIKE '%%candidate%%'
          )
        ORDER BY tablename
    """)
    tables = cur.fetchall()

    if not tables:
        print("\n  No matching/scoring tables found.")
        return

    print(f"\n  Found {len(tables)} matching/scoring related tables:\n")

    for (table,) in tables:
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]
        except Exception as e:
            count = f"ERROR: {e}"
            cur.connection.rollback()

        count_str = f"{count:,}" if isinstance(count, int) else str(count)
        print(f"  {table:<50} {count_str:>12} rows")

        # Get columns
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        cols = cur.fetchall()
        col_list = ", ".join(f"{c[0]} ({c[1]})" for c in cols[:10])
        if len(cols) > 10:
            col_list += f", ... (+{len(cols)-10} more)"
        print(f"    Columns: {col_list}")

        # If it has a score/match_score column, show distribution
        score_cols = [c[0] for c in cols if "score" in c[0].lower() or "probability" in c[0].lower()]
        if score_cols and isinstance(count, int) and count > 0:
            for sc in score_cols[:2]:
                try:
                    cur.execute(f"""
                        SELECT MIN("{sc}"), AVG("{sc}"), MAX("{sc}"),
                               PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY "{sc}")
                        FROM "{table}"
                        WHERE "{sc}" IS NOT NULL
                    """)
                    mn, avg, mx, med = cur.fetchone()
                    if mn is not None:
                        print(f"    {sc}: min={mn:.3f}, avg={avg:.3f}, median={med:.3f}, max={mx:.3f}")
                except Exception:
                    cur.connection.rollback()

        # If it has match_type/source_type column, show distribution
        type_cols = [c[0] for c in cols if c[0] in (
            "match_type", "source_type", "match_source", "source", "tier", "method"
        )]
        if type_cols and isinstance(count, int) and count > 0:
            for tc in type_cols[:2]:
                try:
                    cur.execute(f"""
                        SELECT "{tc}", COUNT(*) FROM "{table}"
                        GROUP BY "{tc}" ORDER BY COUNT(*) DESC LIMIT 10
                    """)
                    dist = cur.fetchall()
                    if dist:
                        print(f"    {tc} distribution:")
                        for val, cnt in dist:
                            print(f"      {str(val):<35} {cnt:>10,}")
                except Exception:
                    cur.connection.rollback()

        print()


# -------------------------------------------------------------------------
# 7. CORPORATE HIERARCHY STATS
# -------------------------------------------------------------------------
def audit_hierarchy(cur):
    section("7. CORPORATE HIERARCHY STATS")

    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = 'corporate_hierarchy'
        )
    """)
    if not cur.fetchone()[0]:
        print("\n  corporate_hierarchy table does not exist.")
        return

    cur.execute("SELECT COUNT(*) FROM corporate_hierarchy")
    total = cur.fetchone()[0]
    print(f"\n  Total hierarchy links: {total:,}")

    # Check columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'corporate_hierarchy'
    """)
    cols = [r[0] for r in cur.fetchall()]

    if "relationship_type" in cols:
        cur.execute("""
            SELECT relationship_type, COUNT(*)
            FROM corporate_hierarchy
            GROUP BY relationship_type
            ORDER BY COUNT(*) DESC
        """)
        rows = cur.fetchall()
        if rows:
            print(f"\n  Relationship types:")
            for rt, cnt in rows:
                print(f"    {str(rt):<40} {cnt:>10,}")

    if "source" in cols:
        cur.execute("""
            SELECT source, COUNT(*)
            FROM corporate_hierarchy
            GROUP BY source
            ORDER BY COUNT(*) DESC
        """)
        rows = cur.fetchall()
        if rows:
            print(f"\n  Sources:")
            for src, cnt in rows:
                print(f"    {str(src):<40} {cnt:>10,}")


# -------------------------------------------------------------------------
# 8. F7 ENHANCED QUICK STATS
# -------------------------------------------------------------------------
def audit_f7_stats(cur):
    section("8. F7_ENHANCED QUICK STATS")

    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM pg_tables
            WHERE schemaname = 'public' AND tablename = 'f7_enhanced'
        )
    """)
    if not cur.fetchone()[0]:
        print("\n  f7_enhanced does not exist.")
        return

    # Get columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'f7_enhanced'
    """)
    cols = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT COUNT(*) FROM f7_enhanced")
    total = cur.fetchone()[0]
    print(f"\n  Total employers: {total:,}")

    # State distribution (top 15)
    if "state" in cols:
        cur.execute("""
            SELECT state, COUNT(*) FROM f7_enhanced
            GROUP BY state ORDER BY COUNT(*) DESC LIMIT 15
        """)
        rows = cur.fetchall()
        print(f"\n  Top 15 states:")
        for st, cnt in rows:
            print(f"    {str(st):<10} {cnt:>8,}")

    # NAICS coverage
    naics_col = None
    for c in cols:
        if "naics" in c.lower():
            naics_col = c
            break
    if naics_col:
        cur.execute(f"""
            SELECT COUNT(*) FROM f7_enhanced WHERE "{naics_col}" IS NOT NULL
        """)
        naics_count = cur.fetchone()[0]
        pct = (naics_count / total * 100) if total > 0 else 0
        print(f"\n  NAICS coverage ({naics_col}): {naics_count:,} / {total:,} ({pct:.1f}%)")

    # corporate_parent_id coverage
    if "corporate_parent_id" in cols:
        cur.execute("""
            SELECT COUNT(*) FROM f7_enhanced WHERE corporate_parent_id IS NOT NULL
        """)
        cp_count = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(DISTINCT corporate_parent_id) FROM f7_enhanced
            WHERE corporate_parent_id IS NOT NULL
        """)
        cp_groups = cur.fetchone()[0]
        print(f"\n  Corporate parent linkage: {cp_count:,} employers in {cp_groups:,} groups")

    # merged_into coverage
    if "merged_into" in cols:
        cur.execute("""
            SELECT COUNT(*) FROM f7_enhanced WHERE merged_into IS NOT NULL
        """)
        merged = cur.fetchone()[0]
        print(f"  Merged records: {merged:,}")


# -------------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------------
def main():
    print(SEPARATOR)
    print("  COMPREHENSIVE DATABASE AUDIT: olms_multiyear")
    print(f"  Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEPARATOR)

    conn = connect()
    cur = conn.cursor()

    try:
        audit_all_tables(cur)
        audit_key_tables(cur)
        audit_views(cur)
        audit_indexes(cur)
        audit_crosswalk(cur)
        audit_matching_scoring(cur)
        audit_hierarchy(cur)
        audit_f7_stats(cur)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

    print(f"\n{SEPARATOR}")
    print("  AUDIT COMPLETE")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
