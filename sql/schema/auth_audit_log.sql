-- Auth audit log — captures every meaningful auth event so a future
-- multi-user beta has a tamper-evident trail of who did what.
-- Mirrors the data_refresh_log pattern (write via separate autocommit
-- connection in auth_log.py so the caller's transaction is never coupled
-- to the audit write).
--
-- Created 2026-05-04 as Week 1 prep (B.1.4 in launch roadmap). NOT yet
-- wired into auth.py / dependencies.py — the wiring is the remaining
-- Week 1 task.

CREATE TABLE IF NOT EXISTS auth_audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES platform_users(id) ON DELETE SET NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Action vocabulary (loose enum; not a CHECK constraint so we can
    -- evolve without a migration):
    --   login_success, login_fail, logout
    --   token_refresh_success, token_refresh_fail
    --   register, password_change, password_reset
    --   role_change, deactivate, reactivate
    --   flag_employer, csv_export, research_trigger, gold_standard_mark
    --   admin_user_create, admin_user_delete, admin_mv_refresh
    action VARCHAR(50) NOT NULL,
    -- Optional pointer to the resource the action targeted (e.g. a
    -- master_id, a user_id of the target of a role change, an export
    -- query string). Free-form text to avoid joining headaches.
    target_resource TEXT,
    -- Network context. NULL when the request didn't carry it (e.g. a
    -- bg job logging a research_trigger).
    ip_address INET,
    user_agent TEXT,
    -- Anything action-specific that doesn't fit a column. Examples:
    --   {"role_from": "read", "role_to": "researcher"}
    --   {"export_size_rows": 25000, "filters": {"state": "NY"}}
    --   {"login_method": "password" | "refresh"}
    metadata JSONB
);

-- "What did user X do recently?" — the most common admin query.
CREATE INDEX IF NOT EXISTS idx_auth_audit_user_recent
    ON auth_audit_log(user_id, occurred_at DESC);

-- "Show every failed login in the last 24h" — security incident response.
CREATE INDEX IF NOT EXISTS idx_auth_audit_action_recent
    ON auth_audit_log(action, occurred_at DESC);

-- "All actions on master X" — investigative path when a row was changed
-- and we want to find who touched it.
CREATE INDEX IF NOT EXISTS idx_auth_audit_target_resource
    ON auth_audit_log(target_resource)
    WHERE target_resource IS NOT NULL;
