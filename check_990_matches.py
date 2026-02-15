
import psycopg2
import os
from dotenv import load_dotenv

from db_config import get_connection
def check_990_matches():
    """
    Checks the count of matched 990 employers to F7 and PS employers.
    """
    load_dotenv()
    conn = None
    try:
        password = os.environ.get("DB_PASSWORD")
        if not password:
            print("Database password not found in environment variables.")
            return None

        conn = get_connection()
        cur = conn.cursor()

        print("--- 990 Match Statistics ---")

        # 1. Total 990 employers
        cur.execute("SELECT COUNT(*) FROM employers_990")
        total_990_employers = cur.fetchone()[0]
        print(f"Total 990 Employers: {total_990_employers:,}")

        # 2. Total employer_990_matches entries
        cur.execute("SELECT COUNT(*) FROM employer_990_matches")
        total_matches = cur.fetchone()[0]
        print(f"Total 990-F7/PS Matches: {total_matches:,}")

        # 3. Matches to F7 employers
        cur.execute("SELECT COUNT(DISTINCT employer_990_id) FROM employer_990_matches WHERE f7_employer_id IS NOT NULL")
        f7_linked_990 = cur.fetchone()[0]
        f7_match_rate = (f7_linked_990 / total_990_employers * 100) if total_990_employers > 0 else 0
        print(f"990 Employers matched to F7: {f7_linked_990:,} ({f7_match_rate:.2f}%)")

        # 4. Matches to PS employers
        cur.execute("SELECT COUNT(DISTINCT employer_990_id) FROM employer_990_matches WHERE ps_employer_id IS NOT NULL")
        ps_linked_990 = cur.fetchone()[0]
        ps_match_rate = (ps_linked_990 / total_990_employers * 100) if total_990_employers > 0 else 0
        print(f"990 Employers matched to PS: {ps_linked_990:,} ({ps_match_rate:.2f}%)")

        return {
            "total_990_employers": total_990_employers,
            "total_990_matches": total_matches,
            "f7_linked_990_count": f7_linked_990,
            "f7_match_rate_pct": round(f7_match_rate, 2),
            "ps_linked_990_count": ps_linked_990,
            "ps_match_rate_pct": round(ps_match_rate, 2)
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
    check_990_matches()
