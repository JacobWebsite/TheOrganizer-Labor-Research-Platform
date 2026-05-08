"""
Shared FastAPI dependencies for authentication and authorization.

Three role tiers (per spec):
  admin       — user management, MV refreshes, scorecard rebuilds
  researcher  — flag employers, CSV export, trigger research runs,
                mark gold-standard dossiers (NEW 2026-05-05)
  read        — search, profile views, scorecard reads (default)

Usage in routers:
    from ..dependencies import require_auth, require_admin, require_researcher

    @router.get("/api/some/endpoint")
    def some_endpoint(user=Depends(require_auth)):
        ...

    @router.post("/api/admin/something")
    def admin_endpoint(user=Depends(require_admin)):
        ...

    @router.post("/api/employers/flags")
    def flag_employer(user=Depends(require_researcher)):
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


def require_researcher(request: Request) -> dict:
    """Require an authenticated user with researcher OR admin role.

    The "researcher" tier is the spec's middle role: can flag employers,
    export CSVs, trigger research runs, mark gold-standard dossiers --
    things a power-user analyst needs but should NOT require giving them
    full admin (user management, MV refreshes, scorecard rebuilds).

    Admins implicitly have researcher permissions, hence the role check
    accepts BOTH `admin` and `researcher`.

    When auth is disabled, mirror require_admin's fail-closed default --
    researcher endpoints can mutate state (flag employers, kick research
    runs that cost API tokens), so anonymous access while
    DISABLE_AUTH=true is the wrong default.
    """
    if not JWT_SECRET:
        if ALLOW_INSECURE_ADMIN:
            return {"username": "dev", "role": "admin"}
        raise HTTPException(
            status_code=403,
            detail="Researcher endpoints are disabled while DISABLE_AUTH=true. "
                   "Set ALLOW_INSECURE_ADMIN=true for local development only.",
        )

    user = getattr(request.state, "user", None)
    role = getattr(request.state, "role", None)
    if not user or user == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    if role not in ("admin", "researcher"):
        raise HTTPException(
            status_code=403,
            detail="Researcher or admin role required",
        )
    return {"username": user, "role": role}
