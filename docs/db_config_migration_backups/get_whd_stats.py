import psycopg2
import os
from dotenv import load_dotenv
import sys

def get_whd_match_stats():
    """
    Fetches WHD match statistics from the database.
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
            password=password # Explicitly pass the fetched password
        )
        cur = conn.cursor()

        # 1. Total WHD cases
        cur.execute("SELECT COUNT(*) FROM whd_cases")
        total_whd_cases = cur.fetchone()[0]

        # 2. F7 employers with WHD data (assuming whd_violation_count is indicator of match)
        cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL")
        f7_matched_count = cur.fetchone()[0]

        # 3. Mergent employers with WHD data
        cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE whd_violation_count IS NOT NULL")
        mergent_matched_count = cur.fetchone()[0]

        # Calculate percentages
        f7_match_rate = (f7_matched_count / total_whd_cases * 100) if total_whd_cases > 0 else 0
        mergent_match_rate = (mergent_matched_count / total_whd_cases * 100) if total_whd_cases > 0 else 0

        print("--- WHD Match Statistics ---")
        print(f"Total WHD Cases: {total_whd_cases:,}")
        print(f"F7 Employers with WHD data: {f7_matched_count:,} ({f7_match_rate:.2f}%)")
        print(f"Mergent Employers with WHD data: {mergent_matched_count:,} ({mergent_match_rate:.2f}%)")

        return {
            "total_whd_cases": total_whd_cases,
            "f7_matched_count": f7_matched_count,
            "f7_match_rate_pct": round(f7_match_rate, 2),
            "mergent_matched_count": mergent_matched_count,
            "mergent_match_rate_pct": round(mergent_match_rate, 2)
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
    get_whd_match_stats()
