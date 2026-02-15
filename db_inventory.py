import psycopg2
import os
from dotenv import load_dotenv
import pandas as pd

def get_db_inventory():
    """
    Connects to the database and generates a detailed inventory of tables and views.
    """
    load_dotenv()
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "olms_multiyear"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD")
        )
        cur = conn.cursor()

        # Get all tables, views, and materialized views
        query = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """
        cur.execute(query)
        relations = cur.fetchall()

        inventory = []
        print(f"Found {len(relations)} relations. Analyzing each...")

        for i, (table_name, table_type) in enumerate(relations):
            print(f"  ({i+1}/{len(relations)}) Analyzing {table_name}...")
            
            # 1. Get row count
            try:
                cur.execute(f'SELECT count(*) FROM "{table_name}";')
                row_count = cur.fetchone()[0]
            except psycopg2.Error as e:
                # This can happen for certain table types or permissions issues
                print(f"      Could not get row count for {table_name}: {e}")
                row_count = -1 # Indicate error
                conn.rollback()


            # 2. Get size on disk
            cur.execute(f"SELECT pg_total_relation_size(%s);", (table_name,))
            size_bytes = cur.fetchone()[0]

            # 3. Get number of columns
            cur.execute("""
                SELECT count(*) 
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = %s;
            """, (table_name,))
            column_count = cur.fetchone()[0]

            # 4. Check for primary key
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints
                    WHERE constraint_type = 'PRIMARY KEY'
                    AND table_schema = 'public' AND table_name = %s
                );
            """, (table_name,))
            has_pk = cur.fetchone()[0]

            inventory.append({
                "name": table_name,
                "type": table_type.replace("BASE TABLE", "TABLE"),
                "rows": row_count,
                "size_bytes": size_bytes,
                "size_readable": f"{round(size_bytes / (1024*1024), 2)} MB",
                "columns": column_count,
                "has_pk": has_pk
            })

        return pd.DataFrame(inventory)

    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None
    finally:
        if conn:
            conn.close()

def categorize_table(name):
    name = name.lower()
    if 'nlrb' in name:
        return 'NLRB'
    if 'osha' in name:
        return 'OSHA'
    if 'union' in name or name.startswith('f7_') or name.startswith('form_') or 'lm2' in name or 'olms' in name:
        return 'Core'
    if 'gleif' in name or 'sec_' in name or 'crosswalk' in name or 'mergent' in name or 'duns' in name:
        return 'Corporate'
    if 'qcew' in name or 'bls' in name or 'density' in name or 'zip' in name or name.endswith('_geo'):
        return 'Geographic'
    if 'splink' in name or 'match' in name or 'fuzzy' in name:
        return 'Matching'
    if name.startswith('pg_') or name.startswith('sql_'):
        return 'Internal' # For postgres internal tables
    return 'Other/Unknown'


if __name__ == "__main__":
    df = get_db_inventory()

    if df is not None:
        print("\n--- Database Inventory Complete ---")

        # --- Overall Summary ---
        print("\n--- Overall Summary ---")
        total_tables = len(df[df['type'] == 'TABLE'])
        total_views = len(df[df['type'] == 'VIEW'])
        total_mat_views = len(df[df['type'] == 'MATERIALIZED VIEW'])
        total_size_gb = df['size_bytes'].sum() / (1024**3)

        print(f"Total Relations: {len(df)}")
        print(f"  - Tables: {total_tables}")
        print(f"  - Views: {total_views}")
        print(f"  - Materialized Views: {total_mat_views}")
        print(f"Total Database Size: {total_size_gb:.2f} GB")
        
        # --- Categorized Summary ---
        print("\n--- Categorized Summary ---")
        df['category'] = df['name'].apply(categorize_table)
        
        # Filter out internal tables for the summary stats
        summary_df = df[~df['category'].isin(['Internal'])]

        category_summary = summary_df.groupby('category').agg(
            table_count=('name', 'size'),
            total_rows=('rows', 'sum'),
            total_size_bytes=('size_bytes', 'sum')
        ).reset_index()
        
        category_summary['total_size'] = category_summary['total_size_bytes'].apply(lambda x: f"{x / (1024**3):.2f} GB")
        category_summary.loc['Total'] = category_summary.sum(numeric_only=True)
        
        # Format for markdown
        md_summary = "| Category | Table Count | Total Rows | Total Size |\n"
        md_summary += "|----------|-------------|------------|------------|\n"
        for _, row in category_summary.iterrows():
            category = row['category'] if pd.notna(row['category']) else '**TOTAL**'
            count = int(row['table_count'])
            rows = f"{int(row['total_rows']):,}"
            size = row['total_size'] if isinstance(row['total_size'], str) else f"{row['total_size_bytes'] / (1024**3):.2f} GB"
            md_summary += f"| {category} | {count} | {rows} | {size} |\n"

        print(md_summary)


        # --- Top 20 Tables by Size ---
        print("\n--- Top 20 Tables by Size ---")
        top_20_size = df.sort_values('size_bytes', ascending=False).head(20)
        print(top_20_size[['name', 'type', 'rows', 'size_readable', 'columns', 'has_pk']].to_markdown(index=False))

        # --- Suspicious Tables ---
        print("\n--- Empty or Suspicious Tables ---")
        zero_row_tables = df[(df['rows'] == 0) & (df['type'] == 'TABLE')]
        suspicious_names = df[df['name'].str.contains('temp|test|backup|old', case=False) & (df['type'] == 'TABLE')]
        
        print(f"\nFound {len(zero_row_tables)} tables with ZERO rows:")
        if not zero_row_tables.empty:
            print(zero_row_tables['name'].to_list())
        
        print(f"\nFound {len(suspicious_names)} tables with suspicious names:")
        if not suspicious_names.empty:
            print(suspicious_names['name'].to_list())
    
        # Save full inventory to CSV for later inspection
        output_path = 'db_inventory_full.csv'
        df.to_csv(output_path, index=False)
        print(f"Full inventory saved to {output_path}")
