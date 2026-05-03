import os
import time
import subprocess
from datetime import datetime
import sys

# Add root to path to import db_config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
try:
    from db_config import DB_CONFIG
except ImportError:
    # Fallback if run from root
    from db_config import DB_CONFIG

def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = r"C:\Users\jakew\backups\labor_data"

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        print(f"Created backup directory: {backup_dir}")

    backup_file = os.path.join(backup_dir, f"labor_data_{timestamp}.dump")

    print(f"Starting backup of {DB_CONFIG['database']} at {datetime.now()}")

    # Set PGPASSWORD environment variable for the subprocess
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_CONFIG["password"]

    # Use full path to pg_dump so scheduled tasks work without PATH
    pg_dump = r"C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
    if not os.path.isfile(pg_dump):
        pg_dump = "pg_dump"  # fallback to PATH

    command = [
        pg_dump,
        "-U", DB_CONFIG["user"],
        "-h", DB_CONFIG.get("host", "localhost"),
        "-p", str(DB_CONFIG.get("port", 5432)),
        "-Fc", # Custom format (compressed)
        "-f", backup_file,
        DB_CONFIG["database"]
    ]

    try:
        subprocess.run(command, env=env, check=True)
        size = os.path.getsize(backup_file)
        print(f"Backup complete: {backup_file} ({size / (1024*1024):.1f} MB)")

        # Cleanup old backups (older than 7 days)
        now = time.time()
        for f in os.listdir(backup_dir):
            fpath = os.path.join(backup_dir, f)
            if os.path.isfile(fpath) and os.stat(fpath).st_mtime < now - (7 * 86400):
                if f.startswith("labor_data_") and f.endswith(".dump"):
                    os.remove(fpath)
                    print(f"Deleted old backup: {f}")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: pg_dump failed with exit code {e.returncode}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    backup_database()
