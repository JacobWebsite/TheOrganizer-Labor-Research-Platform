"""
Shared FastAPI dependencies for authentication and authorization.

Usage in routers:
    from ..dependencies import require_auth, require_admin

    @router.get("/api/some/endpoint")
    def some_endpoint(user=Depends(require_auth)):
        ...

    @router.post("/api/admin/something")
    def admin_endpoint(user=Depends(require_admin)):
        ...
"""
from fastapi import HTTPException, Request

from .config import ALLOW_INSECURE_ADMIN, JWT_SECRET


def require_auth(request: Request) -> dict:
    """Require a valid authenticated user. Returns {"username": ..., "role": ...}.

    When auth is disabled (JWT_SECRET empty), returns a synthetic dev user.
    """
    if not JWT_SECRET:
        return {"username": "dev", "role": "admin"}

    user = getattr(request.state, "user", None)
    role = getattr(request.state, "role", None)
    if not user or user == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"username": user, "role": role}


def require_admin(request: Request) -> dict:
    """Require an authenticated user with admin role.

    When auth is disabled, fail closed by default to prevent anonymous admin
    access unless ALLOW_INSECURE_ADMIN=true is explicitly set for local dev.
    """
    if not JWT_SECRET:
        if ALLOW_INSECURE_ADMIN:
            return {"username": "dev", "role": "admin"}
        # 403 Forbidden, not 503 -- the service is up; the caller is
        # forbidden from this admin endpoint while DISABLE_AUTH=true.
        # 503 implies "service unavailable" which is misleading here.
        raise HTTPException(
            status_code=403,
            detail="Admin endpoints are disabled while DISABLE_AUTH=true. "
                   "Set ALLOW_INSECURE_ADMIN=true for local development only.",
        )

    user = getattr(request.state, "user", None)
    role = getattr(request.state, "role", None)
    if not user or user == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return {"username": user, "role": role}
