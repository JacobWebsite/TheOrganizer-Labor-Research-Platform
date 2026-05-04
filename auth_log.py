"""Shared auth audit logging utility. Writes to auth_audit_log via a
separate autocommit connection so it never couples to the caller's
transaction (mirrors the etl_log.py pattern).

Caller pattern in auth.py / dependencies.py / endpoints:

    from auth_log import log_auth_event
    log_auth_event(
        user_id=user.id,
        action="login_success",
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        metadata={"login_method": "password"},
    )

For action="register" or other pre-user-id events, pass user_id=None.

Action vocabulary (loose enum; see sql/schema/auth_audit_log.sql for
the canonical list).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from db_config import get_connection

_log = logging.getLogger("auth_audit")


def log_auth_event(
    *,
    action: str,
    user_id: int | None = None,
    target_resource: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write a single auth event. Best-effort — never raises into caller.

    Failure modes:
      - DB unreachable -> log a warning, swallow the exception. Auth
        flow MUST NOT break because the audit log is down.
      - Bad SQL -> same swallow + log.
    Both are wrong-direction tradeoffs only when the audit log itself
    is what's being investigated, in which case the caller will see
    the warning in the API logs.
    """
    try:
        conn = get_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO auth_audit_log
              (user_id, action, target_resource, ip_address, user_agent, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                user_id,
                action,
                target_resource,
                ip_address,
                user_agent,
                json.dumps(metadata) if metadata is not None else None,
            ),
        )
        cur.close()
        conn.close()
    except Exception as exc:  # noqa: BLE001 — see docstring
        _log.warning("auth_audit_log write failed: %s", exc)
