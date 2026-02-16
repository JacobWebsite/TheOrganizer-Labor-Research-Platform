# Dependency and Environment Review (Focused Task 6)

Files reviewed:
- `requirements.txt`
- `pyproject.toml`

## 1) Are all dependencies pinned?

No.

All listed dependencies use `>=` ranges, not exact pins.
Examples:
- `fastapi>=0.128.0`
- `requests>=2.32.0`
- `pytest>=8.0.0`

Why this matters:
- Two fresh installs on different days can resolve to different versions.
- Harder to reproduce bugs.
- Harder to guarantee the same security posture.

## 2) Outdated or known-vulnerable dependencies

I checked package versions against current PyPI pages (as of February 16, 2026) and found mixed status:

- Current/near-current minimums:
- `psycopg2-binary>=2.9.11` (current series)
- `openpyxl>=3.1.5` (current)
- `beautifulsoup4>=4.14.0` (close to current)
- `numpy>=2.4.0`, `pandas>=2.3.0`, `scikit-learn>=1.6.0` (modern baselines)

- Potentially stale minimums (may allow older builds than current):
- `fastapi>=0.128.0` (PyPI currently shows newer than this)
- `uvicorn[standard]>=0.40.0` (PyPI currently shows newer than this)
- `rapidfuzz>=3.14.0` (newer patch releases exist)
- `requests>=2.32.0` (newer patch releases exist)

Vulnerability check status:
- I could not run `pip-audit` here because the tool is not installed (`pip-audit` command not found).
- Without a resolved lockfile and installed environment, this review cannot prove there are zero known CVEs.
- Current risk is mostly from unpinned ranges and missing lockfile, not from one confirmed vulnerable direct dependency in these files.

## 3) Anything installed that is not used?

Likely unused or weakly justified:
- `httpx` is listed but no direct `httpx` imports were found in `api/`, `scripts/`, `src/`, or `tests/`.
- `pydantic-settings` is listed but no direct imports found.
- `pytest-asyncio` is listed in dev extras but no async pytest markers/usage found.

Missing direct declarations:
- `python-dotenv` appears used in `scripts/scoring/check_naics_detail.py:2` but is not listed.
- `joblib` is imported in `scripts/ml/train_propensity_model.py:109` and `scripts/ml/train_propensity_model.py:155`; it may come transitively from scikit-learn, but direct declaration is safer.

## 4) Would this build cleanly from a fresh clone?

Not reliably today, for four reasons:

1) No lockfile
- Only lower bounds are defined, so dependency resolution can drift.

2) Missing tooling in environment
- In this environment, `pytest` and `pip-audit` were not available to validate install + test flow.

3) Likely undeclared dependencies
- `python-dotenv` usage is present but not declared.
- `joblib` is used directly but not declared explicitly.

4) Heavy runtime prerequisites
- App/test success requires PostgreSQL with specific schema/data, plus env variables (DB credentials, JWT settings).

## Recommended fixes

1) Pin direct dependencies to exact versions (or generate a lockfile with hashes).
2) Add `python-dotenv` and `joblib` explicitly if they are required at runtime.
3) Remove or justify unused entries (`httpx`, `pydantic-settings`, `pytest-asyncio` if truly unused).
4) Add a reproducible bootstrap doc:
- exact Python version,
- install command,
- required env vars,
- DB init/migration steps,
- smoke test command.
5) Add CI steps for `pip-audit`, `pytest`, and dependency-resolution checks.
