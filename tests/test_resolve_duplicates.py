from datetime import datetime

from scripts.maintenance.resolve_duplicate_matches import (
    METHOD_RANK,
    _winner_sort_key,
    choose_winner,
    supersede_losers,
)


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self.rowcount = len(params[-1]) if params and isinstance(params[-1], list) else 0


def test_choose_winner_prefers_tier_then_confidence_then_recency():
    rows = [
        {
            "id": 1,
            "match_method": "FUZZY_TRIGRAM",
            "confidence_score": 0.99,
            "event_ts": datetime(2026, 2, 1),
        },
        {
            "id": 2,
            "match_method": "NAME_STATE_EXACT",
            "confidence_score": 0.51,
            "event_ts": datetime(2026, 1, 1),
        },
        {
            "id": 3,
            "match_method": "NAME_STATE_EXACT",
            "confidence_score": 0.51,
            "event_ts": datetime(2026, 2, 10),
        },
    ]

    winner = choose_winner(rows)

    # NAME_STATE_EXACT outranks FUZZY_TRIGRAM, and newest timestamp wins tie.
    assert winner["id"] == 3


def test_winner_sort_key_uses_known_ranks():
    row = {
        "id": 10,
        "match_method": "EIN_EXACT",
        "confidence_score": 0.2,
        "event_ts": datetime(2026, 2, 1),
    }
    key = _winner_sort_key(row)

    assert key[0] == METHOD_RANK["EIN_EXACT"]


def test_supersede_losers_uses_evidence_fallback_when_columns_missing():
    cur = FakeCursor()

    updated = supersede_losers(cur, loser_ids=[11, 12], winner_id=9, uml_columns={"id", "status", "evidence"})

    assert updated == 2
    assert len(cur.calls) == 1
    sql, params = cur.calls[0]
    assert "status = 'superseded'" in sql
    assert "superseded_by = %s" not in sql
    assert "superseded_reason = %s" not in sql
    assert params[-1] == [11, 12]


def test_supersede_losers_sets_columns_when_present():
    cur = FakeCursor()

    updated = supersede_losers(
        cur,
        loser_ids=[21],
        winner_id=7,
        uml_columns={"id", "status", "evidence", "superseded_by", "superseded_reason"},
    )

    assert updated == 1
    sql, params = cur.calls[0]
    assert "superseded_by = %s" in sql
    assert "superseded_reason = %s" in sql
    assert params[-1] == [21]
