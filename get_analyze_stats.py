
import psycopg2
import os
from dotenv import load_dotenv

def get_analyze_stats():
    """
    Fetches the last analyze and autoanalyze times for specified tables.
    """
    load_dotenv()
    conn = None
    try:
        password = os.environ.get("DB_PASSWORD")
        if not password:
            print("Database password not found in environment variables.")
            return None

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "olms_multiyear"),
            user=os.getenv("DB_USER", "postgres"),
            password=password
        )
        cur = conn.cursor()

        tables_to_check = [
            'sam_entities', 'osha_establishments', 'nlrb_participants',
            'mergent_employers', 'f7_employers_deduped', 'corporate_identifier_crosswalk',
            'unions_master', 'nlrb_elections', 'whd_cases', 'gleif_us_entities',
            'f7_union_employer_relations', 'ps_union_locals', 'ps_employers',
            'ps_parent_unions', 'ps_bargaining_units', 'union_sector', 'union_match_status',
            'nlrb_cases', 'nlrb_case_types', 'nlrb_allegations', 'nlrb_voluntary_recognition',
            'employer_990_matches', 'employers_990', 'sec_companies', 'apple_tokens',
            'mv_employer_search', 'mv_organizing_scorecard', 'v_naics_union_density',
            'v_state_density_latest', 'county_union_density_estimates', 'state_industry_density_comparison'
        ]

        print("--- Last Analyze Times ---")
        
        # Construct the IN clause string manually, ensuring each table name is quoted
        quoted_tables_for_in = ", ".join(f"'{t}'" for t in tables_to_check)
        in_clause = f"({quoted_tables_for_in})"

        query = f"""
            SELECT relname, last_analyze, last_autoanalyze 
            FROM pg_stat_user_tables 
            WHERE relname IN {in_clause}
        """
        
        cur.execute(query)
        analyze_stats = cur.fetchall()

        found_tables = set()
        if analyze_stats:
            for row in analyze_stats:
                relname = row[0]
                last_analyze = row[1] # index 1 is last_analyze
                last_autoanalyze = row[2] # index 2 is last_autoanalyze
                print(f'Table: {relname}')
                print(f'  Last Analyze: {last_analyze if last_analyze else "Never"}')
                print(f'  Last Autoanalyze: {last_autoanalyze if last_autoanalyze else "Never"}')
                found_tables.add(relname)

        # Check for tables specified but not found in stats
        missing_stats = [t for t in tables_to_check if t not in found_tables]
        if missing_stats:
            print("\n--- Tables not found in statistics ---")
            for table_name in missing_stats:
                print(f"- {table_name}")

        return {
            "stats_found_count": len(analyze_stats) if analyze_stats else 0,
            "analyze_times": [
                {
                    "table": row[0],
                    "last_analyze": str(row[1]) if row[1] else "Never",
                    "last_autoanalyze": str(row[2]) if row[2] else "Never"
                } for row in analyze_stats
            ] if analyze_stats else [],
            "tables_missing_stats": missing_stats
        }

    except psycopg2.OperationalError as e:
        print(f"Database connection error: {e}")
        return None
    except psycopg2.errors.UndefinedTable as e:
        print(f"Table error: {e}") # Handle cases where a table might truly not exist
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    get_analyze_stats()
