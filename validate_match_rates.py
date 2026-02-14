
import sys
from pathlib import Path
import argparse

# Add project root to path to allow importing db_config
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from db_config import get_connection

def validate_rates(password: str):
    """Calculates and prints the match rates for key data sources."""
    try:
        from db_config import DB_CONFIG
        DB_CONFIG['password'] = password
        conn = get_connection()
        cur = conn.cursor()

        def get_count(table_name):
            cur.execute(f"SELECT COUNT(*) FROM {table_name};")
            return cur.fetchone()[0]

        # OSHA
        osha_total = get_count('osha_establishments')
        osha_matched = get_count('osha_f7_matches')
        osha_rate = (osha_matched / osha_total) * 100 if osha_total > 0 else 0

        # WHD
        whd_total = get_count('whd_cases')
        whd_matched = get_count('whd_f7_matches')
        whd_rate = (whd_matched / whd_total) * 100 if whd_total > 0 else 0

        # 990
        n990_total = get_count('national_990_filers')
        n990_matched = get_count('national_990_f7_matches')
        n990_rate = (n990_matched / n990_total) * 100 if n990_total > 0 else 0
        
        print("Match Rate Validation:")
        print(f"OSHA: {osha_matched:,} / {osha_total:,} = {osha_rate:.2f}%")
        print(f"WHD: {whd_matched:,} / {whd_total:,} = {whd_rate:.2f}%")
        print(f"990 National: {n990_matched:,} / {n990_total:,} = {n990_rate:.2f}%")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Validate data match rates.')
    parser.add_argument('--password', type=str, required=True, help='Database password')
    args = parser.parse_args()
    validate_rates(args.password)
