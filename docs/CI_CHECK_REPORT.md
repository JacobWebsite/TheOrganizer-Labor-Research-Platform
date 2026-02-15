# CI Check Report

- Generated: 2026-02-15T12:50:59
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

============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 6 passed, 1 warning in 0.04s =========================
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

============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 2 passed, 1 warning in 0.50s =========================
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

============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 6 passed, 1 warning in 0.05s =========================
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

============================== warnings summary ===============================
..\..\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475
  C:\Users\jakew\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\_pytest\cacheprovider.py:475: PytestCacheWarning: could not create cache path C:\Users\jakew\Downloads\labor-data-project\.pytest_cache\v\cache\nodeids: [WinError 183] Cannot create a file when that file already exists: 'C:\\Users\\jakew\\Downloads\\labor-data-project\\.pytest_cache\\v\\cache'
    config.cache.set("cache/nodeids", sorted(self.cached_nodeids))

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 2 passed, 1 warning in 0.32s =========================
```
- **innerHTML Lint Check**: PASS
  - `python scripts/analysis/check_js_innerhtml_safety.py`
```text
Wrote: C:\Users\jakew\Downloads\labor-data-project\docs\JS_INNERHTML_SAFETY_CHECK.md
Findings: 0
```
