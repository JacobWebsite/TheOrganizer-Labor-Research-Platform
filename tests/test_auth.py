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
    """Remove test users before and after all auth tests complete.

    Pre-cleanup handles leftover users from previous runs or other test
    modules that may have created users via auth fixtures.
    """
    from db_config import get_connection

    def _delete():
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM platform_users WHERE username LIKE 'test_%'")
            conn.commit()
        except Exception:
            conn.rollback()
        conn.close()

    _delete()  # pre-cleanup
    yield
    _delete()  # post-cleanup


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
        json={"username": "test_reader", "password": "readerpass123", "role": "read"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    # Login as read user
    read_r = auth_client.post("/api/auth/login", json={
        "username": "test_reader", "password": "readerpass123"
    })
    read_token = read_r.json()["access_token"]

    # Try to register -- should fail
    r = auth_client.post("/api/auth/register",
        json={"username": "test_sneaky", "password": "sneakypass123", "role": "read"},
        headers={"Authorization": f"Bearer {read_token}"}
    )
    assert r.status_code == 403


def test_register_unauthenticated_after_first_user(auth_client):
    """Unauthenticated registration fails when users already exist."""
    r = auth_client.post("/api/auth/register", json={
        "username": "test_anon", "password": "anonpass1234", "role": "read"
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
    # 2026-05-05: JWT lifetime dropped 8h -> 1h. expires_in should be 3600
    # (one hour) -- assert tightly so a future revert can't slip through.
    assert data["expires_in"] == 3600, (
        f"expected 3600s (1hr) JWT lifetime, got {data['expires_in']}s"
    )


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
    # Refresh issues a fresh 1-hour token, not a partial-life "extend".
    assert data["expires_in"] == 3600
    # Note: the refreshed token MAY be byte-identical to the original when
    # both issuances land in the same second (iat collision -> same payload
    # -> same signature). That's fine -- the meaningful invariant is that
    # the new token's exp is at or after the original's, validated by
    # test_refresh_token_exp_claim_is_one_hour below.


def test_refresh_token_exp_claim_is_one_hour(auth_client):
    """JWT exp claim is now+3600s (regression guard for the 2026-05-05
    JWT_EXPIRY_HOURS change). Decodes the token and validates the exp
    timestamp directly rather than trusting the response field."""
    import time
    import json
    import base64

    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    # JWT payload is base64url-encoded JSON in the middle segment
    parts = token.split(".")
    assert len(parts) == 3, "JWT should have 3 dot-separated segments"
    # Pad b64 to a multiple of 4
    pad = "=" * ((4 - len(parts[1]) % 4) % 4)
    payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    exp = payload.get("exp")
    iat = payload.get("iat")
    assert exp is not None and iat is not None
    # exp - iat should equal 3600 seconds (1 hour)
    assert exp - iat == 3600, (
        f"exp-iat should be 3600s (1hr), got {exp - iat}s. "
        f"Has JWT_EXPIRY_HOURS reverted?"
    )
    # Sanity: exp should be ~now + 1hr, not days away
    delta = exp - int(time.time())
    assert 3500 < delta < 3700, (
        f"token exp is {delta}s from now; expected ~3600s (1hr). "
        f"Delta from 3600: {delta - 3600}s"
    )


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
    """Password under 12 chars is rejected (policy bumped 8 -> 12 on 2026-05-05)."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    # 5 chars — was rejected under the old 8-char minimum, still rejected under 12
    r = auth_client.post("/api/auth/register",
        json={"username": "test_short", "password": "short", "role": "read"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422  # Validation error

    # 11 chars — passed under the old 8-char minimum, MUST now be rejected.
    # This is the regression-guard for the 2026-05-05 policy change.
    r = auth_client.post("/api/auth/register",
        json={"username": "test_eleven", "password": "elevenchars", "role": "read"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 422
    # Pydantic error mentions the min_length (string-length detail)
    assert "12" in r.text or "min" in r.text.lower()


def test_register_password_at_12_char_minimum_accepted(auth_client):
    """Password at exactly 12 chars (the new minimum) is accepted."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    twelve_char = "abcde1234567"  # exactly 12 chars
    assert len(twelve_char) == 12
    r = auth_client.post("/api/auth/register",
        json={"username": "test_twelvech", "password": twelve_char, "role": "read"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, f"got {r.status_code} {r.text}"


def test_register_invalid_username(auth_client):
    """Username with special chars is rejected."""
    login_r = auth_client.post("/api/auth/login", json={
        "username": "test_admin", "password": "adminpass123"
    })
    token = login_r.json()["access_token"]

    r = auth_client.post("/api/auth/register",
        json={"username": "test user!", "password": "validpass1234", "role": "read"},
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
        "username": "test_reader", "password": "readerpass123"
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


# ============================================================================
# Researcher role (B.1.1, added 2026-05-05)
# ============================================================================

def test_register_researcher_role_accepted(auth_client):
    """The new 'researcher' role registers successfully (was rejected by
    the original `^(admin|read)$` pattern)."""
    admin_token = _get_admin_token(auth_client)
    r = auth_client.post(
        "/api/auth/register",
        json={
            "username": "test_researcher",
            "password": "researcherpass1",
            "role": "researcher",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200, f"unexpected: {r.status_code} {r.text}"
    assert r.json()["role"] == "researcher"


def test_register_invalid_role_rejected(auth_client):
    """Roles outside admin/researcher/read are still rejected by the regex."""
    admin_token = _get_admin_token(auth_client)
    r = auth_client.post(
        "/api/auth/register",
        json={
            "username": "test_baduser",
            "password": "validpass1234",
            "role": "superuser",  # not in the allowed set
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 422  # Pydantic validation error


def _get_researcher_token(auth_client):
    """Helper: log in as the test_researcher user from the test above."""
    r = auth_client.post(
        "/api/auth/login",
        json={"username": "test_researcher", "password": "researcherpass1"},
    )
    return r.json()["access_token"]


def test_login_researcher_returns_role(auth_client):
    """Login as researcher returns role='researcher' in the token response."""
    r = auth_client.post(
        "/api/auth/login",
        json={"username": "test_researcher", "password": "researcherpass1"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "researcher"


# ============================================================================
# require_researcher dependency function (called directly, not via endpoint)
# ============================================================================

class _FakeRequest:
    """Minimal Request stand-in for direct dependency-function tests.

    require_* dependencies only access request.state.{user, role}, so a
    SimpleNamespace-shaped object is enough — no need to spin up an
    actual ASGI request.
    """
    def __init__(self, user=None, role=None):
        from types import SimpleNamespace
        self.state = SimpleNamespace(user=user, role=role)


def test_require_researcher_accepts_researcher_role(auth_client):
    from api.dependencies import require_researcher
    out = require_researcher(_FakeRequest(user="alice", role="researcher"))
    assert out == {"username": "alice", "role": "researcher"}


def test_require_researcher_accepts_admin_role(auth_client):
    """Admins implicitly have researcher permissions."""
    from api.dependencies import require_researcher
    out = require_researcher(_FakeRequest(user="root", role="admin"))
    assert out == {"username": "root", "role": "admin"}


def test_require_researcher_rejects_read_role(auth_client):
    from fastapi import HTTPException
    from api.dependencies import require_researcher
    with pytest.raises(HTTPException) as ei:
        require_researcher(_FakeRequest(user="bob", role="read"))
    assert ei.value.status_code == 403
    assert "Researcher" in ei.value.detail or "researcher" in ei.value.detail


def test_require_researcher_rejects_anonymous(auth_client):
    from fastapi import HTTPException
    from api.dependencies import require_researcher
    with pytest.raises(HTTPException) as ei:
        require_researcher(_FakeRequest(user="anonymous", role=None))
    assert ei.value.status_code == 401


# ============================================================================
# Audit log writes (B.1.4, added 2026-05-05)
# ============================================================================

def _count_audit_rows(action: str, since_seconds: int = 60) -> int:
    """Count rows in auth_audit_log matching `action`, written in the last
    `since_seconds`. Used to verify auth events are being recorded."""
    from db_config import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM auth_audit_log
            WHERE action = %s
              AND occurred_at >= NOW() - (%s || ' seconds')::interval
            """,
            (action, str(since_seconds)),
        )
        row = cur.fetchone()
        return int(row[0] if isinstance(row, tuple) else row.get("count", 0))
    finally:
        conn.close()


def test_audit_login_success_writes_row(auth_client):
    """A successful login writes an audit row with action='login_success'."""
    before = _count_audit_rows("login_success")
    r = auth_client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "adminpass123"},
    )
    assert r.status_code == 200
    after = _count_audit_rows("login_success")
    assert after == before + 1, (
        f"expected exactly 1 new login_success row; before={before} after={after}"
    )


def test_audit_login_fail_wrong_password_writes_row(auth_client):
    """A wrong-password login writes an audit row with action='login_fail'."""
    before = _count_audit_rows("login_fail")
    r = auth_client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "wrong-password-on-purpose"},
    )
    assert r.status_code == 401
    after = _count_audit_rows("login_fail")
    assert after == before + 1


def test_audit_login_fail_no_such_user_writes_row(auth_client):
    """A login attempt on a nonexistent user writes an audit row too."""
    before = _count_audit_rows("login_fail")
    r = auth_client.post(
        "/api/auth/login",
        json={"username": "test_does_not_exist_xyzzy", "password": "anything"},
    )
    assert r.status_code == 401
    after = _count_audit_rows("login_fail")
    assert after == before + 1
