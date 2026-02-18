"""
JWT authentication middleware.

Enabled by default. Set DISABLE_AUTH=true in .env to bypass for development.
Token format: {"sub": "username", "role": "admin|read", "iat": ..., "exp": ...}

CLI token generator:
    py -m api.middleware.auth --user admin --role admin
"""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS

# Paths that never require auth
PUBLIC_PATHS = frozenset({
    "/",
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/docs",
    "/openapi.json",
    "/redoc",
})

PUBLIC_PREFIXES = ("/files/",)


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT auth middleware. No-op when JWT_SECRET is empty."""

    async def dispatch(self, request: Request, call_next):
        if not JWT_SECRET:
            return await call_next(request)

        is_public = _is_public(request.url.path)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                import jwt
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                request.state.user = payload.get("sub", "anonymous")
                request.state.role = payload.get("role", "read")
            except Exception:
                if not is_public:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or expired token"},
                    )
        elif not is_public:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )

        return await call_next(request)


def generate_token(user: str, role: str = "read") -> str:
    """Generate a JWT token (CLI utility)."""
    import jwt

    now = int(time.time())
    payload = {
        "sub": user,
        "role": role,
        "iat": now,
        "exp": now + JWT_EXPIRY_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


if __name__ == "__main__":
    import argparse
    import sys
    import os

    # Ensure config is loaded
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    parser = argparse.ArgumentParser(description="Generate JWT token for API auth")
    parser.add_argument("--user", required=True, help="Username (sub claim)")
    parser.add_argument("--role", default="admin", choices=["admin", "read"], help="Role")
    args = parser.parse_args()

    if not JWT_SECRET:
        print("ERROR: LABOR_JWT_SECRET not set in .env. Auth is disabled.")
        sys.exit(1)

    token = generate_token(args.user, args.role)
    print(f"Token for {args.user} ({args.role}):")
    print(token)
