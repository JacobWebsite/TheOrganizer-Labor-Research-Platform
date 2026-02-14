"""
Shared test fixtures for the labor research platform test suite.
"""
import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Ensure auth is disabled for general API tests (no JWT_SECRET = middleware no-op)
# Auth-specific tests set their own secret via monkeypatch
os.environ.pop("LABOR_JWT_SECRET", None)

from starlette.testclient import TestClient
from api.main import app


@pytest.fixture(scope="session")
def client():
    """Create a test client with auth disabled (default)."""
    with TestClient(app) as c:
        yield c
