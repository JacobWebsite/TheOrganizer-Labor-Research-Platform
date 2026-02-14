"""
Authentication endpoints: login, register, token refresh, current user.

Uses platform_users table with bcrypt-hashed passwords.
Registration is admin-only (requires existing admin token).
First user can self-register as admin (bootstrap mode, advisory-locked).
"""
import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

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
    password: str = Field(..., min_length=8)
    role: str = Field(default="read", pattern=r'^(admin|read)$')


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
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
            "SELECT password_hash, role FROM platform_users WHERE username = %s",
            (body.username,)
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(401, "Invalid credentials")

    password_hash, role = row["password_hash"], row["role"]
    if not _verify_password(body.password, password_hash):
        raise HTTPException(401, "Invalid credentials")

    token, expires_in = _create_token(body.username, role)
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
        try:
            password_hash = _hash_password(body.password)
            cur.execute(
                "INSERT INTO platform_users (username, password_hash, role) VALUES (%s, %s, %s)",
                (body.username, password_hash, body.role)
            )
        except psycopg2.errors.UniqueViolation:
            raise HTTPException(409, "Username already exists")

    log.info("Registered user %s (role=%s, bootstrap=%s)",
             body.username, body.role, user_count == 0)
    return UserInfo(username=body.username, role=body.role)


@router.post("/api/auth/refresh", response_model=TokenResponse)
def refresh_token(request: Request):
    """Refresh the current token (must be authenticated)."""
    if not JWT_SECRET:
        raise HTTPException(400, "Authentication is not configured")

    current = _get_current_user(request)
    if not current:
        raise HTTPException(401, "Authentication required")

    token, expires_in = _create_token(current["username"], current["role"])
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
