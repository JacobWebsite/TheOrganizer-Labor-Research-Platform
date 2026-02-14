
import sys
from pathlib import Path
import argparse

# Add project root to path to allow importing db_config
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from db_config import get_connection

def check_connection(password: str):
    """Attempts to connect to the database and prints the result."""
    try:
        # Override the password from the config
        from db_config import DB_CONFIG
        DB_CONFIG['password'] = password
        conn = get_connection()
        conn.close()
        print("Connection successful")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check database connection.')
    parser.add_argument('--password', type=str, required=True, help='Database password')
    args = parser.parse_args()
    check_connection(args.password)
