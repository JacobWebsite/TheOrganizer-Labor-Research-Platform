"""
Application configuration loaded from environment / .env file.
"""
import os
import sys
from pathlib import Path

# Add project root for db_config import
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

# Re-export DB_CONFIG from the canonical project-root db_config module so
# api/database.py's `from .config import DB_CONFIG` resolves. Use an
# explicit rebind (rather than `from db_config import DB_CONFIG`) so that
# autoflake/ruff --remove-unused-imports does NOT silently drop the line --
# this regression broke the audit harness on 2026-05-05.
import db_config as _root_db_config  # noqa: E402

DB_CONFIG = _root_db_config.DB_CONFIG

PROJECT_ROOT = _project_root
FILES_DIR = _project_root / "files"

# JWT auth -- requires LABOR_JWT_SECRET in .env (32+ chars).
# Set DISABLE_AUTH=true to explicitly bypass auth in development.
AUTH_DISABLED = os.environ.get("DISABLE_AUTH", "").lower() == "true"
_jwt_from_env = os.environ.get("LABOR_JWT_SECRET") or ""
JWT_SECRET = "" if AUTH_DISABLED else _jwt_from_env
# Safety valve for local development only. When false (default), admin endpoints
# are blocked if auth is disabled to avoid anonymous administrative access.
ALLOW_INSECURE_ADMIN = os.environ.get("ALLOW_INSECURE_ADMIN", "").lower() == "true"
JWT_ALGORITHM = "HS256"
# Token lifetime. 1 hour per the platform spec; the frontend's auto-refresh
# in useAuth.js silently rotates the token at the ~50-minute mark so the
# session keeps living as long as the user is active. A short token life
# limits damage from a stolen JWT (browser extension, shared computer,
# bad WiFi, hypothetical XSS). 2026-05-05: was 8.
JWT_EXPIRY_HOURS = 1
# Auto-refresh window. The frontend should call /api/auth/refresh when the
# token has fewer than this many seconds left. Chosen so a stable network
# always has time to retry; on intermittent connections the user notices
# at most one missed click before the next refresh succeeds.
JWT_REFRESH_BEFORE_EXPIRY_SECONDS = 10 * 60  # 10 min

# CORS allowed origins (comma-separated in env, or default for local dev)
_origins_raw = os.environ.get("ALLOWED_ORIGINS", "")
if _origins_raw:
    ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = [
        "http://localhost:8001",
        "http://localhost:8080",
        "http://localhost:5173",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
        "null",  # file:// origin for standalone HTML tools
    ]

# Rate limiting
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
