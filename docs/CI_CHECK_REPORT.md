# CI Check Report

- Generated: 2026-02-15T13:17:18
- Passed: 6/6

## Steps
- **Phase1 Merge Validator**: PASS
  - `python scripts/analysis/phase1_merge_validator.py`
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\PHASE1_MERGE_VALIDATION_REPORT.md
Passed: 7/7
```
- **Frontend XSS Regressions**: PASS
  - `python -m pytest tests/test_frontend_xss_regressions.py -q`
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 6 items

tests\test_frontend_xss_regressions.py ......                            [100%]

============================== 6 passed in 0.04s ==============================
```
- **Scorecard Contract Parity**: PASS
  - `python -m pytest tests/test_scorecard_contract_field_parity.py -q`
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 2 items

tests\test_scorecard_contract_field_parity.py ..                         [100%]

============================== 2 passed in 0.41s ==============================
```
- **Normalization Tests**: PASS
  - `python -m pytest tests/test_name_normalization.py -q`
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 6 items

tests\test_name_normalization.py ......                                  [100%]

============================== 6 passed in 0.05s ==============================
```
- **Migration Guard Test**: PASS
  - `python -m pytest tests/test_db_config_migration_guard.py -q`
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 2 items

tests\test_db_config_migration_guard.py ..                               [100%]

============================== 2 passed in 0.32s ==============================
```
- **innerHTML Lint Check**: PASS
  - `python scripts/analysis/check_js_innerhtml_safety.py`
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\JS_INNERHTML_SAFETY_CHECK.md
Findings: 0
```
