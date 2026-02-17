"""Regression tests for deterministic matching Phase B fixes."""
import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.matching import deterministic_matcher as dm


class _FakeCursor:
    def __init__(self, parent):
        self.parent = parent

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.parent.last_sql = sql

    def fetchall(self):
        self.parent.calls += 1
        if self.parent.calls == 1:
            # employer_id, employer_name, name_standard, name_aggressive, state, city
            return [
                ("F7-1", "Acme Holdings", "acme", "acme", "CA", "LOS ANGELES"),
                ("F7-2", "Acme Logistics", "acme", "acme", "CA", "SAN DIEGO"),
            ]
        return []


class _FakeConn:
    def __init__(self):
        self.calls = 0
        self.last_sql = ""

    def cursor(self):
        return _FakeCursor(self)

    def rollback(self):
        return None


@pytest.fixture()
def matcher(monkeypatch):
    monkeypatch.setattr(dm, "normalize_name_standard", lambda n: (n or "").strip().lower())
    monkeypatch.setattr(dm, "normalize_name_aggressive", lambda n: (n or "").strip().lower())

    m = dm.DeterministicMatcher(
        conn=_FakeConn(),
        run_id="test-run",
        source_system="osha",
        dry_run=True,
    )
    m._indexes_loaded = True
    return m


def test_tier3_city_state_wins_over_tier2_state_only(matcher):
    matcher._name_state_idx[("acme", "CA")] = [("F7-STATE", "Acme State", "SAN FRANCISCO")]
    matcher._name_city_state_idx[("acme", "SAN FRANCISCO", "CA")] = [
        ("F7-CITY", "Acme City")
    ]

    result = matcher._match_best(
        {"id": "S1", "name": "acme", "state": "ca", "city": "san francisco", "ein": None}
    )

    assert result is not None
    assert result["method"] == "NAME_CITY_STATE_EXACT"
    assert result["target_id"] == "F7-CITY"


def test_name_state_collisions_are_retained_in_index_build(monkeypatch):
    monkeypatch.setattr(dm, "normalize_name_standard", lambda n: (n or "").strip().lower())
    monkeypatch.setattr(dm, "normalize_name_aggressive", lambda n: (n or "").strip().lower())

    m = dm.DeterministicMatcher(
        conn=_FakeConn(),
        run_id="test-run",
        source_system="osha",
        dry_run=True,
    )
    m._build_indexes()

    key = ("acme", "CA")
    assert key in m._name_state_idx
    assert len(m._name_state_idx[key]) == 2
    ids = {row[0] for row in m._name_state_idx[key]}
    assert ids == {"F7-1", "F7-2"}


def test_ambiguous_exact_matches_are_flagged_not_auto_selected(matcher):
    matcher._name_state_idx[("acme", "CA")] = [
        ("F7-1", "Acme One", "LOS ANGELES"),
        ("F7-2", "Acme Two", "SAN DIEGO"),
    ]

    result = matcher._match_best(
        {"id": "S2", "name": "acme", "state": "CA", "city": "", "ein": None}
    )

    assert result is not None
    assert result["method"] == "AMBIGUOUS_NAME_STATE_EXACT"
    assert result["band"] == "LOW"
    assert result["target_id"] == "AMBIGUOUS"
    assert result["evidence"]["candidate_count"] == 2


def test_match_tier_ordering_ein_city_state_state_aggressive_then_fuzzy(matcher, monkeypatch):
    matcher._ein_idx["123456789"] = "F7-EIN"
    matcher._name_city_state_idx[("acme", "SAN JOSE", "CA")] = [("F7-CITY", "Acme City")]
    matcher._name_state_idx[("acme", "CA")] = [("F7-STATE", "Acme State", "SAN JOSE")]
    matcher._agg_state_idx[("acme", "CA")] = [("F7-AGG", "Acme Agg", "SAN JOSE")]

    ein_result = matcher._match_best(
        {"id": "S3", "name": "acme", "state": "CA", "city": "SAN JOSE", "ein": "123456789"}
    )
    assert ein_result["method"] == "EIN_EXACT"

    city_result = matcher._match_best(
        {"id": "S4", "name": "acme", "state": "CA", "city": "SAN JOSE", "ein": ""}
    )
    assert city_result["method"] == "NAME_CITY_STATE_EXACT"

    del matcher._name_city_state_idx[("acme", "SAN JOSE", "CA")]
    state_result = matcher._match_best(
        {"id": "S5", "name": "acme", "state": "CA", "city": "SAN JOSE", "ein": ""}
    )
    assert state_result["method"].startswith("NAME_STATE_EXACT")

    matcher._name_state_idx.clear()
    agg_result = matcher._match_best(
        {"id": "S6", "name": "acme", "state": "CA", "city": "SAN JOSE", "ein": ""}
    )
    assert agg_result["method"].startswith("NAME_AGGRESSIVE_STATE")

    fuzzy_called = {"value": False}

    def _fake_fuzzy(unmatched):
        fuzzy_called["value"] = True
        assert len(unmatched) == 1
        assert str(unmatched[0]["id"]) == "S8"
        return [matcher._make_result("S8", "F7-FUZZY", "FUZZY_SPLINK_ADAPTIVE", "probabilistic", "MEDIUM", 0.72, {})]

    monkeypatch.setattr(matcher, "_fuzzy_batch", _fake_fuzzy)

    out = matcher.match_batch([
        {"id": "S7", "name": "acme", "state": "CA", "city": "SAN JOSE", "ein": ""},
        {"id": "S8", "name": "unknown", "state": "CA", "city": "", "ein": ""},
    ])
    methods = [r["method"] for r in out]

    assert fuzzy_called["value"] is True
    assert "FUZZY_SPLINK_ADAPTIVE" in methods


@pytest.fixture(scope="module")
def db_conn():
    from db_config import get_connection

    conn = get_connection()
    conn.autocommit = True
    yield conn
    conn.close()


def _query_one(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return row[0] if row else None


def test_regression_guard_osha_match_rate_baseline(db_conn):
    total = _query_one(db_conn, "SELECT COUNT(*) FROM osha_establishments")
    matched = _query_one(db_conn, "SELECT COUNT(DISTINCT establishment_id) FROM osha_f7_matches")
    if not total:
        pytest.skip("osha_establishments empty")

    rate = matched / total
    assert rate >= 0.13, f"OSHA match rate {rate:.1%} below 13% baseline"


def test_confidence_band_thresholds(matcher):
    assert matcher._band_for_score(0.85) == "HIGH"
    assert matcher._band_for_score(0.84) == "MEDIUM"
    assert matcher._band_for_score(0.70) == "MEDIUM"
    assert matcher._band_for_score(0.69) == "LOW"
