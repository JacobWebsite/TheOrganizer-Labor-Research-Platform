"""
Phase 1 regression guards.

These tests are intentionally lightweight and mostly static to avoid
conflicts with in-flight implementation work.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_density_router_avoids_numeric_realdictrow_access():
    """
    Guard against RealDictRow index access regressions in density router.

    RealDictRow should be accessed by column name, not numeric index.
    """
    density_path = ROOT / "api" / "routers" / "density.py"
    text = density_path.read_text(encoding="utf-8")

    risky_patterns = [
        "stats[0]",
        "stats[1]",
        "stats[2]",
        "stats[3]",
        "stats[4]",
        "result[0]",
        "result[1]",
        "result[2]",
        "result[3]",
        "result[4]",
    ]

    matches = [pattern for pattern in risky_patterns if pattern in text]
    assert not matches, f"Found numeric row access patterns in density router: {matches}"


def test_auth_default_not_empty_secret_guard():
    """
    Guard for Phase 1 requirement: auth should be enabled by default.
    """
    config_path = ROOT / "api" / "config.py"
    text = config_path.read_text(encoding="utf-8")
    assert "LABOR_JWT_SECRET" in text
    assert 'os.environ.get("LABOR_JWT_SECRET", "")' not in text

