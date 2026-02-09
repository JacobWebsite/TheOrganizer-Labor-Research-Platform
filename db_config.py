"""
Shared database configuration for all scripts.
Reads credentials from .env file or environment variables.
"""
import os
from pathlib import Path

# Load .env from project root
_env_path = Path(__file__).resolve().parent / '.env'
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = int(os.environ.get('DB_PORT', '5432'))
DB_NAME = os.environ.get('DB_NAME', 'olms_multiyear')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

DB_CONFIG = {
    'host': DB_HOST,
    'port': DB_PORT,
    'database': DB_NAME,
    'user': DB_USER,
    'password': DB_PASSWORD,
}

def get_connection(cursor_factory=None):
    """Get a database connection using shared config."""
    import psycopg2
    kwargs = dict(DB_CONFIG)
    if cursor_factory:
        kwargs['cursor_factory'] = cursor_factory
    return psycopg2.connect(**kwargs)
