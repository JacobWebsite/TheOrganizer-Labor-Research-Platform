"""
Authentication endpoints: login, register, token refresh, current user.

Uses platform_users table with bcrypt-hashed passwords.
Registration is admin-only (requires existing admin token).
First user can self-register as admin (bootstrap mode, advisory-locked).

Every meaningful auth event writes a row to `auth_audit_log` via
`auth_log.log_auth_event()`. The audit writer uses a separate autocommit
connection and swallows errors so an audit-log outage cannot break
the auth flow itself.
"""
import time
import logging
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

# auth_log.py lives at the project root, not under api/. Add the project
# root to sys.path so we can import it without a package rename.
# A module-level `from auth_log import log_auth_event` here is repeatedly
# eaten by the project's formatter (same pattern as api/main.py — formatter
# treats the post-sys.path import as out-of-order and removes it). Wrap
# it in a lazy helper instead so the import survives.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def log_auth_event(**kwargs):
    """Lazy wrapper around auth_log.log_auth_event() — see docstring there.

    Imported lazily because the formatter eats module-level imports of
    sibling project-root modules. Best-effort: if the wrapped writer
    itself raises, swallow it (auth flow MUST NOT break on audit-log
    failure).
    """
    try:
        from auth_log import log_auth_event as _impl
        _impl(**kwargs)
    except Exception:  # noqa: BLE001 — see docstring above
        pass


from ..config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS
from ..database import get_db

router = APIRouter()
log = logging.getLogger("labor_api.auth")

# Advisory lock ID for first-user bootstrap (arbitrary constant)
_BOOTSTRAP_LOCK_ID = 900_001

# Auth-specific rate limiting (login attempts per IP)
_login_attempts: dict[str, list[float]] = {}
_LOGIN_WINDOW = 300  # 5 minutes
_LOGIN_MAX = 10  # max attempts per window


# ---------- Pydantic models ----------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    # 12-char minimum (2026-05-05; was 8). Industry guidance for any
    # multi-user platform with admin tier; brings us in line with NIST
    # recommendations and significantly reduces the attack surface for
    # offline brute force should the password_hash table ever leak.
    # LoginRequest still accepts min_length=1 so existing accounts with
    # shorter passwords from the pre-policy era can still authenticate
    # — they only hit the new rule on next reset.
    password: str = Field(..., min_length=12)
    # Three-tier role hierarchy per spec:
    #   admin       — user management, MV refreshes, scorecard rebuilds
    #   researcher  — flag employers, CSV export, trigger research runs
    #   read        — search, profile views, scorecard reads (default)
    role: str = Field(default="read", pattern=r'^(admin|researcher|read)$')


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class UserInfo(BaseModel):
    username: str
    role: str


# ---------- Helpers ----------

def _ensure_users_table():
    """Create platform_users table if it doesn't exist."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS platform_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'read',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)


def _hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    import bcrypt
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _check_secret_strength():
    """Reject secrets shorter than 32 characters."""
    if JWT_SECRET and len(JWT_SECRET) < 32:
        raise HTTPException(500, "JWT secret must be at least 32 characters")


def _create_token(username: str, role: str) -> tuple[str, int]:
    """Create JWT token. Returns (token, expires_in_seconds)."""
    import jwt
    now = int(time.time())
    expires_in = JWT_EXPIRY_HOURS * 3600
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_in


def _get_current_user(request: Request) -> Optional[dict]:
    """Extract user info from request (set by AuthMiddleware)."""
    user = getattr(request.state, "user", None)
    role = getattr(request.state, "role", None)
    if user and user != "anonymous":
        return {"username": user, "role": role}
    return None


def _client_ip(request: Request) -> str:
    """Return raw client-IP string — may not be a valid IP address (proxy
    misconfig, test client, etc.). Use _client_ip_for_audit() when
    storing into the INET-typed audit log."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _client_ip_for_audit(request: Request) -> Optional[str]:
    """Return the client IP if it's a valid IPv4/IPv6 literal; else None.

    The audit log's `ip_address` column is INET, so passing a stringy
    sentinel like 'testclient' (from Starlette's TestClient) or 'unknown'
    (from a request with no client info) raises a Postgres syntax error
    and trips auth_log.py's swallow path -- the audit row is silently
    dropped. Validating here means real IPs flow through cleanly and
    invalid-IP traffic still produces an audit row, just with NULL
    ip_address.
    """
    raw = _client_ip(request)
    if not raw or raw == "unknown":
        return None
    import ipaddress
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        return None


def _check_login_rate(request: Request):
    """Enforce stricter rate limiting on login attempts (10 per 5 min)."""
    now = time.time()
    ip = _client_ip(request)
    cutoff = now - _LOGIN_WINDOW
    attempts = [t for t in _login_attempts.get(ip, []) if t > cutoff]
    _login_attempts[ip] = attempts

    if len(attempts) >= _LOGIN_MAX:
        raise HTTPException(429, "Too many login attempts. Try again later.")
    attempts.append(now)


# ---------- Endpoints ----------

@router.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request):
    """Authenticate and receive a JWT token."""
    if not JWT_SECRET:
        raise HTTPException(400, "Authentication is not configured")

    _check_secret_strength()
    _check_login_rate(request)
    _ensure_users_table()

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, password_hash, role FROM platform_users WHERE username = %s",
            (body.username,)
        )
        row = cur.fetchone()

    # Validated IP for the audit log (None if proxy/test gives a non-IP);
    # raw IP is fine for rate-limit dict keys but must NOT go into INET.
    ip = _client_ip_for_audit(request)
    ua = request.headers.get("user-agent")

    if not row:
        log_auth_event(
            action="login_fail",
            ip_address=ip,
            user_agent=ua,
            metadata={"reason": "no_such_user", "username_attempted": body.username},
        )
        raise HTTPException(401, "Invalid credentials")

    user_id, password_hash, role = row["id"], row["password_hash"], row["role"]
    if not _verify_password(body.password, password_hash):
        log_auth_event(
            user_id=user_id,
            action="login_fail",
            ip_address=ip,
            user_agent=ua,
            metadata={"reason": "wrong_password", "username_attempted": body.username},
        )
        raise HTTPException(401, "Invalid credentials")

    token, expires_in = _create_token(body.username, role)
    log_auth_event(
        user_id=user_id,
        action="login_success",
        ip_address=ip,
        user_agent=ua,
        metadata={"role": role},
    )
    return TokenResponse(access_token=token, expires_in=expires_in, role=role)


@router.post("/api/auth/register", response_model=UserInfo)
def register(body: RegisterRequest, request: Request):
    """Create a new user. First user bootstraps as admin; subsequent require admin token."""
    if not JWT_SECRET:
        raise HTTPException(400, "Authentication is not configured")

    _check_secret_strength()
    _ensure_users_table()

    import psycopg2

    with get_db() as conn:
        cur = conn.cursor()

        # Advisory lock prevents concurrent first-user bootstrap race (Codex #1)
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_BOOTSTRAP_LOCK_ID,))

        # Check if any users exist -- first user can self-register as admin
        cur.execute("SELECT COUNT(*) FROM platform_users")
        user_count = cur.fetchone()["count"]

        if user_count > 0:
            # Require admin role for subsequent registrations
            current = _get_current_user(request)
            if not current or current["role"] != "admin":
                raise HTTPException(403, "Only admins can register new users")

        # INSERT with unique constraint as final guard (Codex #5)
        new_user_id: Optional[int] = None
        try:
            password_hash = _hash_password(body.password)
            cur.execute(
                "INSERT INTO platform_users (username, password_hash, role) "
                "VALUES (%s, %s, %s) RETURNING id",
                (body.username, password_hash, body.role)
            )
            inserted = cur.fetchone()
            if inserted is not None:
                new_user_id = inserted["id"] if isinstance(inserted, dict) else inserted[0]
        except psycopg2.errors.UniqueViolation:
            log_auth_event(
                action="register_fail",
                ip_address=_client_ip_for_audit(request),
                user_agent=request.headers.get("user-agent"),
                metadata={"reason": "username_exists", "username_attempted": body.username},
            )
            raise HTTPException(409, "Username already exists")

    log.info("Registered user %s (role=%s, bootstrap=%s)",
             body.username, body.role, user_count == 0)
    log_auth_event(
        user_id=new_user_id,
        action="register",
        ip_address=_client_ip_for_audit(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"role": body.role, "bootstrap": user_count == 0},
    )
    return UserInfo(username=body.username, role=body.role)


@router.post("/api/auth/refresh", response_model=TokenResponse)
def refresh_token(request: Request):
    """Refresh the current token (must be authenticated)."""
    if not JWT_SECRET:
        raise HTTPException(400, "Authentication is not configured")

    current = _get_current_user(request)
    if not current:
        log_auth_event(
            action="token_refresh_fail",
            ip_address=_client_ip_for_audit(request),
            user_agent=request.headers.get("user-agent"),
            metadata={"reason": "not_authenticated"},
        )
        raise HTTPException(401, "Authentication required")

    token, expires_in = _create_token(current["username"], current["role"])
    # Look up user_id by username for the audit row. Cheap; refresh
    # is much rarer than login.
    user_id: Optional[int] = None
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM platform_users WHERE username = %s",
                (current["username"],),
            )
            row = cur.fetchone()
            if row:
                user_id = row["id"] if isinstance(row, dict) else row[0]
    except Exception:  # noqa: BLE001 — audit logging must never break auth
        pass
    log_auth_event(
        user_id=user_id,
        action="token_refresh_success",
        ip_address=_client_ip_for_audit(request),
        user_agent=request.headers.get("user-agent"),
        metadata={"role": current["role"]},
    )
    return TokenResponse(
        access_token=token, expires_in=expires_in, role=current["role"]
    )


@router.get("/api/auth/me", response_model=UserInfo)
def current_user(request: Request):
    """Get the current authenticated user."""
    if not JWT_SECRET:
        raise HTTPException(400, "Authentication is not configured")

    current = _get_current_user(request)
    if not current:
        raise HTTPException(401, "Authentication required")

    return UserInfo(**current)
