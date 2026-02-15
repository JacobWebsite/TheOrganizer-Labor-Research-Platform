# Phase 1 Merge Validation Report

- Generated: 2026-02-15T12:50:51
- Passed: 7/7

## Check Results
- **Regression Guards**: PASS
  - Command: `python -m pytest tests/test_phase1_regression_guards.py -q`
  - Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 2 items
tests\test_phase1_regression_guards.py ..                                [100%]
============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
... (1 more lines)
```
- **Name Normalization Tests**: PASS
  - Command: `python -m pytest tests/test_name_normalization.py -q`
  - Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 6 items
tests\test_name_normalization.py ......                                  [100%]
============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
... (1 more lines)
```
- **Contract Field Parity Tests**: PASS
  - Command: `python -m pytest tests/test_scorecard_contract_field_parity.py -q`
  - Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.0.2, pluggy-1.6.0
rootdir: C:\Users\jakew\Downloads\labor-data-project
configfile: pyproject.toml
plugins: anyio-4.12.1
collected 2 items
tests\test_scorecard_contract_field_parity.py ..                         [100%]
============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
... (1 more lines)
```
- **Frontend/API Audit**: PASS
  - Command: `python scripts/analysis/check_frontend_api_alignment.py`
  - Output:
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\PARALLEL_FRONTEND_API_AUDIT.md
```
- **Password Bug Scanner**: PASS
  - Command: `python scripts/analysis/find_literal_password_bug.py`
  - Output:
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\PARALLEL_PHASE1_PASSWORD_AUDIT.md
Findings: 0
```
- **InnerHTML Risk Priority**: PASS
  - Command: `python scripts/analysis/prioritize_innerhtml_api_risk.py`
  - Output:
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\PARALLEL_INNERHTML_API_RISK_PRIORITY.md
Findings: 1
```
- **Router Docs Drift**: PASS
  - Command: `python scripts/analysis/check_router_docs_drift.py`
  - Output:
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\PARALLEL_ROUTER_DOCS_DRIFT.md
```
