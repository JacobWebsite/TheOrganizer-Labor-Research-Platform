# Credential Scan 2026

## Scope
Scanned project files for passwords, secrets, tokens, API keys, and the known quoted-literal DB password bug pattern.

## Findings

### Finding C1 - Real credentials stored in local `.env`
- File: `.env`
- Risk: local DB password and JWT secret are present in plaintext. If this file is copied/shared/committed, attackers can access DB/API.
- Fix:
  1. Rotate DB password and JWT secret.
  2. Keep `.env` untracked.
  3. Use a secret manager for production.

### Finding C2 - Plaintext DB password appears in multiple docs/helper files
- Files (examples):
  - `BLIND_AUDIT_PROMPT.md:56`
  - `audit_2026/db_query.py:15`
  - `_audit_q.py:4`
  - `_audit_s2.py:4`
  - `_audit_s3.py:4`
  - `_audit_s4.py:4`
- Risk: anyone with repo access can read credentials.
- Fix:
  1. Replace plaintext password with environment lookup or placeholder text.
  2. Rotate password after cleanup.
  3. Purge leaked values from git history if this repo is shared externally.

### Finding C3 - `.env` is not tracked (good), `.env.example` is tracked (expected)
- Evidence: `git ls-files .env .env.example`
- Risk: low for current git state, but local secret file still needs strict handling.
- Fix: keep current ignore behavior and add pre-commit secret scanning.

### Finding C4 - Known quoted-literal password bug pattern appears in remediation tooling, not active runtime code
- Files:
  - `scripts/analysis/find_literal_password_bug.py`
  - `scripts/analysis/fix_literal_password_bug.py`
- Risk: these files intentionally contain the bad pattern as search/replace targets; this is expected.
- Fix: none for these tool files. Continue periodic scans to ensure runtime scripts do not reintroduce it.

### Finding C5 - Many scripts correctly use `os.environ.get('DB_PASSWORD', '')`
- Scope: widespread across `scripts/`.
- Risk: low by itself (this is preferred over hardcoded password).
- Fix: centralize DB config usage further (`db_config.py`) to reduce repetition.

## Recommended actions (priority order)
1. Rotate DB password and JWT secret immediately.
2. Remove plaintext credentials from markdown/helper audit files.
3. Add automated secret scanning in CI (for example, gitleaks/trufflehog).
4. Keep running the literal-password-bug scanner as part of release checks.
