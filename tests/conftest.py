"""
Shared test fixtures for the labor research platform test suite.
"""
import sys
import os
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from httpx import Client, ASGITransport
from api.main import app


@pytest.fixture(scope="session")
def client():
    """Create a test client that talks to the API without starting a server."""
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        yield c
