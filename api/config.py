"""
Application configuration loaded from environment / .env file.
"""
import os
import sys
from pathlib import Path

# Add project root for db_config import
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from db_config import DB_CONFIG  # noqa: E402

PROJECT_ROOT = _project_root
FILES_DIR = _project_root / "files"

# JWT auth (disabled when empty)
JWT_SECRET = os.environ.get("LABOR_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8

# Rate limiting
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
