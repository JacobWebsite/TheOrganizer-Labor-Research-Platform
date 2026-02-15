
import psycopg2
import os
from dotenv import load_dotenv

def get_gleif_match_stats():
    """
    Fetches statistics on GLEIF matches from the corporate_identifier_crosswalk table.
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

        print("--- GLEIF Match Statistics ---")

        # 1. Total GLEIF entities in the crosswalk table (linked to F7 employers)
        cur.execute("""
            SELECT COUNT(DISTINCT gleif_lei)
            FROM corporate_identifier_crosswalk
            WHERE gleif_lei IS NOT NULL AND gleif_lei != ''
        """)
        gleif_matched_to_f7 = cur.fetchone()[0]

        # 2. Total entries in corporate_identifier_crosswalk linked to F7 employers
        cur.execute("""
            SELECT COUNT(DISTINCT f7_employer_id)
            FROM corporate_identifier_crosswalk
            WHERE f7_employer_id IS NOT NULL AND f7_employer_id != ''
        """)
        total_f7_linked_in_crosswalk = cur.fetchone()[0]

        # 3. Total entries in corporate_identifier_crosswalk with GLEIF_LEI
        cur.execute("""
            SELECT COUNT(*) FROM corporate_identifier_crosswalk
            WHERE gleif_lei IS NOT NULL AND gleif_lei != ''
        """)
        total_crosswalk_with_gleif = cur.fetchone()[0]

        print(f"Total GLEIF LEIs linked in crosswalk: {gleif_matched_to_f7:,}")
        print(f"Total F7 employers linked in crosswalk: {total_f7_linked_in_crosswalk:,}")
        print(f"Total crosswalk entries with GLEIF LEI: {total_crosswalk_with_gleif:,}")

        # Calculate percentages based on total F7 employers from Section 1 (approx. 113K)
        # Note: This assumes total_f7_employers is known contextually or fetched.
        # For now, we report counts and direct matches.

        return {
            "gleif_matched_to_f7_count": gleif_matched_to_f7,
            "total_f7_linked_in_crosswalk": total_f7_linked_in_crosswalk,
            "total_crosswalk_entries_with_gleif": total_crosswalk_with_gleif
        }

    except psycopg2.OperationalError as e:
        print(f"Database connection error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    get_gleif_match_stats()
