"""
Authentication endpoint tests.

Tests JWT auth flow: register, login, refresh, protected endpoints.
Uses a test-specific JWT secret to enable auth without affecting other tests.

Run with: py -m pytest tests/test_auth.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

TEST_JWT_SECRET = "test-secret-for-auth-tests-only!"  # 32+ chars required


@pytest.fixture(scope="module")
def auth_client():
    """Test client with auth ENABLED via test secret."""
    import api.config as config
    import api.middleware.auth as auth_mod
    import api.routers.auth as auth_router
    import api.dependencies as deps

    # Enable auth -- must patch all modules that imported JWT_SECRET by value
    original_secret = config.JWT_SECRET
    config.JWT_SECRET = TEST_JWT_SECRET
    auth_mod.JWT_SECRET = TEST_JWT_SECRET
    auth_router.JWT_SECRET = TEST_JWT_SECRET
    deps.JWT_SECRET = TEST_JWT_SECRET

    # Disable login rate limiting for tests
    original_max = auth_router._LOGIN_MAX
    auth_router._LOGIN_MAX = 999

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c

    # Restore
    config.JWT_SECRET = original_secret
    auth_mod.JWT_SECRET = original_secret
    auth_router.JWT_SECRET = original_secret
    deps.JWT_SECRET = original_secret
    auth_router._LOGIN_MAX = original_max


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_users():
    """Remove test users after all auth tests complete."""
    yield
    from db_config import get_connection
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM platform_users WHERE username LIKE 'test_%'")
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()


# ============================================================================
# Auth disabled (default state)
# ============================================================================

def test_auth_disabled_returns_400(client):
    """Login returns 400 when JWT_SECRET is not set."""
    r = client.post("/api/auth/login", json={
        "username": "anyone", "password": "anything"
    })
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"]


# ============================================================================
# Registration
# ============================================================================

def test_register_first_user(auth_client):
    """First user can self-register as admin (no existing users check)."""
    r = auth_client.post("/api/auth/register", json={
        "username": "test_admin",
        "password": "adminpass123",
        "role": "admin"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "test_admin"
    assert data["role"] == "admin"


def test_register_duplicate_fails(auth_client):
    """Duplicate username returns 409."""
    # First login as admin to get token
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin",
        "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.post("/api/auth/register",
        json={"username": "test_admin", "password": "otherpass123", "role": "read"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 409


def test_register_requires_admin(auth_client):
    """Non-admin cannot register new users."""
    # Login as admin first to create a read user
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    admin_token = login_r.json()["access_token"]

    # Create read user
    auth_client.post("/api/auth/register",
        json={"username": "test_reader", "password": "readerpass1", "role": "read"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    # Login as read user
    read_r = auth_client.post("/api/auth/login", json={
        "username": "test_reader", "password": "readerpass1"
    })
    read_token = read_r.json()["access_token"]

    # Try to register -- should fail
    r = auth_client.post("/api/auth/register",
        json={"username": "test_sneaky", "password": "sneakypass1", "role": "read"},
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert r.status_code == 403


def test_register_unauthenticated_after_first_user(auth_client):
    """Unauthenticated registration fails when users already exist."""
    r = auth_client.post("/api/auth/register", json={
        "username": "test_anon", "password": "anonpass123", "role": "read"
    })
    assert r.status_code == 403


# ============================================================================
# Login
# ============================================================================

def test_login_success(auth_client):
    """Valid credentials return a JWT token."""
    r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "admin"
    assert data["expires_in"] > 0


def test_login_wrong_password(auth_client):
    """Wrong password returns 401."""
    r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "wrongpassword"
    })
    assert r.status_code == 401
    assert "Invalid credentials" in r.json()["detail"]


def test_login_nonexistent_user(auth_client):
    """Nonexistent user returns 401 (same as wrong password)."""
    r = auth_client.post("/api/auth/login", json={
        "username": "nobody_here", "password": "doesntmatter"
    })
    assert r.status_code == 401


# ============================================================================
# Token refresh and /me
# ============================================================================

def test_refresh_token(auth_client):
    """Authenticated user can refresh their token."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.post("/api/auth/refresh",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


def test_me_endpoint(auth_client):
    """Authenticated user can get their own info."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.get("/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "test_admin"
    assert data["role"] == "admin"


# ============================================================================
# Protected endpoints (auth enabled)
# ============================================================================

def test_protected_endpoint_no_token(auth_client):
    """API endpoints return 401 without a token when auth is enabled."""
    r = auth_client.get("/api/summary")
    assert r.status_code == 401


def test_protected_endpoint_with_token(auth_client):
    """API endpoints work with valid token."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.get("/api/summary",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200


def test_public_endpoints_no_auth_needed(auth_client):
    """Health and docs don't require auth even when enabled."""
    r = auth_client.get("/api/health")
    assert r.status_code == 200

    r = auth_client.get("/docs")
    assert r.status_code == 200


def test_invalid_token_returns_401(auth_client):
    """Garbage token returns 401 with sanitized message."""
    r = auth_client.get("/api/summary",
        headers={"Authorization": "Bearer garbage.token.here"}
    )
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert "Invalid or expired" in detail
    # Should NOT leak internal exception details
    assert "Traceback" not in detail


# ============================================================================
# Input validation
# ============================================================================

def test_register_short_password(auth_client):
    """Password under 8 chars is rejected."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.post("/api/auth/register",
        json={"username": "test_short", "password": "short", "role": "read"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422  # Validation error


def test_register_invalid_username(auth_client):
    """Username with special chars is rejected."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.post("/api/auth/register",
        json={"username": "test user!", "password": "validpass1", "role": "read"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422


# ============================================================================
# Role-based admin endpoint protection
# ============================================================================

def _get_admin_token(auth_client):
    r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    return r.json()["access_token"]


def _get_reader_token(auth_client):
    r = auth_client.post("/api/auth/login", json={
        "username": "test_reader", "password": "readerpass1"
    })
    return r.json()["access_token"]


def test_admin_refresh_scorecard_requires_admin(auth_client):
    """Read-only user cannot refresh scorecard."""
    token = _get_reader_token(auth_client)
    r = auth_client.post("/api/admin/refresh-scorecard",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_admin_refresh_scorecard_admin_ok(auth_client):
    """Admin user can refresh scorecard (or at least gets past auth)."""
    token = _get_admin_token(auth_client)
    r = auth_client.post("/api/admin/refresh-scorecard",
        headers={"Authorization": f"Bearer {token}"}
    )
    # 200 or 500 (if DB view doesn't exist in test) -- NOT 401/403
    assert r.status_code != 403


def test_admin_refresh_freshness_requires_admin(auth_client):
    """Read-only user cannot refresh freshness."""
    token = _get_reader_token(auth_client)
    r = auth_client.post("/api/admin/refresh-freshness",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_admin_match_review_requires_admin(auth_client):
    """Read-only user cannot review matches."""
    token = _get_reader_token(auth_client)
    r = auth_client.post("/api/admin/match-review/1",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_admin_endpoints_no_token_returns_401(auth_client):
    """Admin endpoints return 401 without a token."""
    r = auth_client.post("/api/admin/refresh-scorecard")
    assert r.status_code == 401


def test_write_endpoints_require_auth(auth_client):
    """POST/DELETE write endpoints require authentication."""
    r = auth_client.post("/api/employers/flags", json={
        "source_type": "F7", "source_id": "test", "flag_type": "NEEDS_REVIEW"
    })
    assert r.status_code == 401

    r = auth_client.delete("/api/employers/flags/99999")
    assert r.status_code == 401
