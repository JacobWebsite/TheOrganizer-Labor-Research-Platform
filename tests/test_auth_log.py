"""Tests for auth_log.log_auth_event.

Smoke tests against the live `auth_audit_log` table. Uses negative
IDs / sentinel actions so test rows are easy to identify and clean up.
"""
from __future__ import annotations

import json
from db_config import get_connection
from auth_log import log_auth_event

# Sentinel marker so test rows don't get confused with real events
_TEST_ACTION_PREFIX = "_test_"


def _cleanup():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM auth_audit_log WHERE action LIKE %s",
        [f"{_TEST_ACTION_PREFIX}%"],
    )
    conn.commit()
    cur.close()
    conn.close()


def setup_function(_):
    _cleanup()


def teardown_function(_):
    _cleanup()


def _count(action: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM auth_audit_log WHERE action = %s", [action])
    row = cur.fetchone()
    conn.close()
    return int(row[0] if isinstance(row, tuple) else row.get("count"))


def test_log_minimal_event_writes_a_row():
    log_auth_event(action=f"{_TEST_ACTION_PREFIX}minimal")
    assert _count(f"{_TEST_ACTION_PREFIX}minimal") == 1


def test_log_full_event_round_trips_metadata():
    log_auth_event(
        action=f"{_TEST_ACTION_PREFIX}full",
        user_id=None,
        target_resource="MASTER-1234",
        ip_address="10.0.0.42",
        user_agent="pytest/1.0",
        metadata={"role_from": "read", "role_to": "researcher"},
    )
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT target_resource, ip_address, user_agent, metadata "
        "FROM auth_audit_log WHERE action = %s",
        [f"{_TEST_ACTION_PREFIX}full"],
    )
    row = cur.fetchone()
    conn.close()
    if isinstance(row, tuple):
        target, ip, ua, meta = row
    else:
        target, ip, ua, meta = row["target_resource"], row["ip_address"], row["user_agent"], row["metadata"]
    assert target == "MASTER-1234"
    assert str(ip) == "10.0.0.42"
    assert ua == "pytest/1.0"
    # psycopg2 returns JSONB as a parsed dict
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta == {"role_from": "read", "role_to": "researcher"}


def test_log_swallows_db_errors_does_not_raise():
    # Trigger by passing an action longer than the VARCHAR(50) limit.
    # The DB will raise; log_auth_event must catch and swallow.
    too_long = f"{_TEST_ACTION_PREFIX}" + "x" * 100
    # No assertion — pass condition is "did not raise"
    log_auth_event(action=too_long)


def test_multiple_events_have_distinct_ids_and_timestamps():
    log_auth_event(action=f"{_TEST_ACTION_PREFIX}seq1")
    log_auth_event(action=f"{_TEST_ACTION_PREFIX}seq2")
    log_auth_event(action=f"{_TEST_ACTION_PREFIX}seq3")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, occurred_at FROM auth_audit_log "
        "WHERE action LIKE %s ORDER BY id",
        [f"{_TEST_ACTION_PREFIX}seq%"],
    )
    rows = cur.fetchall()
    conn.close()
    assert len(rows) == 3
    ids = [r[0] if isinstance(r, tuple) else r["id"] for r in rows]
    timestamps = [r[1] if isinstance(r, tuple) else r["occurred_at"] for r in rows]
    # Distinct + monotonic ids
    assert len(set(ids)) == 3
    assert ids == sorted(ids)
    # Timestamps non-decreasing
    assert timestamps == sorted(timestamps)
