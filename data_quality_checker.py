
import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd

from db_config import get_connection
def get_table_columns(cur, table_name):
    """Gets a list of column names for a given table."""
    try:
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = %s;
        """, (table_name,))
        return [row[0] for row in cur.fetchall()]
    except psycopg2.Error as e:
        print(f"  ERROR fetching columns for {table_name}: {e}")
        return []

def run_quality_checks():
    """
    Connects to the database and runs a series of data quality checks.
    """
    load_dotenv()
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 1. Column Completeness Checks
        print("--- 1. Column Completeness ---")
        completeness_checks = {
            'f7_employers_deduped': ['employer_name', 'city', 'state', 'naics', 'latitude', 'longitude', 'latest_unit_size'],
            'unions_master': ['union_name', 'aff_abbr', 'members', 'city', 'state'],
            'osha_establishments': ['estab_name', 'site_city', 'site_state', 'sic_code', 'naics_code'],
            'nlrb_elections': ['case_number', 'eligible_voters', 'total_votes', 'union_won'], # Using corrected columns
            'mergent_employers': ['company_name', 'duns', 'ein', 'employees_site', 'naics_primary']
        }

        for table, desired_columns in completeness_checks.items():
            print(f"\nAnalyzing table: {table}")
            actual_columns = get_table_columns(cur, table)
            if not actual_columns:
                continue

            columns_to_check = [col for col in desired_columns if col in actual_columns]
            
            try:
                cur.execute(f'SELECT count(*) FROM "{table}";')
                total_rows = cur.fetchone()[0]
                if total_rows == 0:
                    print("  Table is empty, skipping.")
                    continue
                
                print(f"  Total rows: {total_rows:,}")
                results = []
                for col in columns_to_check:
                    cur.execute(f'SELECT count(*) FROM "{table}" WHERE "{col}" IS NULL;')
                    null_count = cur.fetchone()[0]
                    
                    empty_count = 0
                    cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, col))
                    dtype = cur.fetchone()[0]
                    if 'char' in dtype or 'text' in dtype:
                        cur.execute(f'SELECT count(*) FROM "{table}" WHERE trim(CAST("{col}" AS text)) = \'\';')
                        empty_count = cur.fetchone()[0]

                    total_missing = null_count + empty_count
                    percent_filled = ((total_rows - total_missing) / total_rows) * 100 if total_rows > 0 else 0
                    results.append({
                        "Column": col,
                        "Total Rows": total_rows,
                        "Null Count": null_count,
                        "Empty String Count": empty_count,
                        "Total Missing": total_missing,
                        "% Filled": f"{percent_filled:.2f}%"
                    })
                if results:
                    print(pd.DataFrame(results).to_markdown(index=False))
                else:
                    print("  No columns to check.")

            except psycopg2.Error as e:
                print(f"  ERROR checking table {table}: {e}")
                conn.rollback()


        # 2. Duplicate Checks
        print("\n\n--- 2. Duplicate Record Checks ---")
        duplicate_checks = {
            'f7_employers_deduped': ['employer_name', 'state'],
            'osha_establishments': ['estab_name', 'site_city', 'site_state'],
            'nlrb_elections': ['case_number']
        }
        for table, columns in duplicate_checks.items():
            print(f"\nChecking for duplicates in: {table} (on columns: {', '.join(columns)})")
            actual_columns = get_table_columns(cur, table)
            if not all(c in actual_columns for c in columns):
                print(f"  SKIPPING: Not all columns {columns} found in table {table}.")
                continue
            
            try:
                cols_str = '", "'.join(columns)
                query = f'SELECT "{cols_str}", COUNT(*) FROM "{table}" GROUP BY "{cols_str}" HAVING COUNT(*) > 1;'
                cur.execute(query)
                duplicates = cur.fetchall()
                if duplicates:
                    print(f"  Found {len(duplicates)} duplicate groups.")
                    df_dups = pd.DataFrame(duplicates, columns=columns + ['count'])
                    print(df_dups.head().to_markdown(index=False))
                else:
                    print("  No duplicates found.")
            except psycopg2.Error as e:
                print(f"  ERROR checking duplicates in {table}: {e}")
                conn.rollback()

        # 3. Orphan Record Checks
        print("\n\n--- 3. Orphan Record Checks ---")
        
        orphan_relations = [
            ("f7_relations → employers", "f7_union_employer_relations", "employer_id", "f7_employers_deduped", "employer_id"),
            ("f7_relations → unions", "f7_union_employer_relations", "union_file_number", "unions_master", "f_num"),
            ("nlrb_participants → elections", "nlrb_participants", "case_number", "nlrb_elections", "case_number"),
            ("osha_matches → employers", "osha_f7_matches", "f7_employer_id", "f7_employers_deduped", "employer_id"),
            ("osha_matches → establishments", "osha_f7_matches", "establishment_id", "osha_establishments", "establishment_id")
        ]
        
        results = []
        for name, left_table, left_col, right_table, right_col in orphan_relations:
            try:
                left_cols = get_table_columns(cur, left_table)
                right_cols = get_table_columns(cur, right_table)

                if not (left_cols and right_cols and left_col in left_cols and right_col in right_cols):
                    results.append({"Relationship": name, "Total Records": "SKIPPED", "Orphaned": "SKIPPED", "Orphan Rate": "SKIPPED"})
                    continue

                cur.execute(f"SELECT count(*) FROM {left_table};")
                total_records = cur.fetchone()[0]

                query = f"""
                    SELECT count(*) FROM {left_table} r
                    LEFT JOIN {right_table} e ON r."{left_col}"::text = e."{right_col}"::text
                    WHERE e."{right_col}" IS NULL;
                """
                cur.execute(query)
                orphaned_count = cur.fetchone()[0]
                
                orphan_rate = (orphaned_count / total_records) * 100 if total_records > 0 else 0
                
                results.append({
                    "Relationship": name,
                    "Total Records": f"{total_records:,}",
                    "Orphaned": f"{orphaned_count:,}",
                    "Orphan Rate": f"{orphan_rate:.2f}%"
                })
            except psycopg2.Error as e:
                print(f"  ERROR checking orphans for '{name}': {e}")
                conn.rollback()
                results.append({"Relationship": name, "Total Records": "ERROR", "Orphaned": "ERROR", "Orphan Rate": "ERROR"})
        
        print("\n--- Orphan Summary ---")
        if results:
            print(pd.DataFrame(results).to_markdown(index=False))

    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_quality_checks()
