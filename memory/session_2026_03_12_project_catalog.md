# Session: Project Catalog (2026-03-12)

## Changes Made

### New Files
- **`PROJECT_CATALOG.md`** (1,375 lines) — Comprehensive catalog of every file in the project (~785 code/config files + ~229 docs). 20 major sections with table-formatted listings. Demographics comparison section has full detail (88 scripts + 24 reports grouped by function: shared modules, version runners, holdout selectors, tuning, data builders, evaluation, gate training, report generators).
- **`scripts/maintenance/check_catalog_coverage.py`** — Drift detection script that parses catalog markdown tables and compares against `os.walk()` of active directories. Exit 0 if clean, 1 if drift. Excludes archive/, node_modules/, __pycache__, .git, dist, data/ (tracked as directory summaries).

### Modified Files
- **`PIPELINE_MANIFEST.md`** — Added superseded header pointing to PROJECT_CATALOG.md
- **`DOCUMENT_INDEX.md`** — Added PROJECT_CATALOG.md as ACTIVE, demoted PIPELINE_MANIFEST to REFERENCE
- **`CLAUDE.md` Section 11** — Added PROJECT_CATALOG.md to "Files That Matter > Documentation"
- **`CLAUDE.md` Section 13** — Added update trigger: `New script/file added -> PROJECT_CATALOG.md`

## Key Findings
- Project has 785 trackable code/config files across all active directories
- 3 CBA scripts (10, 11, audit_coverage) and 1 demographics script (floor_analysis) were discovered during catalog building — these were created after the plan's file count
- `data/` directories are tracked as summaries (14 top-level dirs), not individual files
- `archive/` contains 4,196 files — excluded from catalog
- Demographics comparison has 88 Python scripts + 24 reports + ~44 data files (JSON, CSV, PKL)
- Frontend has 126 source files + 38 test files

## Verification
- `check_catalog_coverage.py`: **CLEAN — 785/785, 0 drift**
- `py -m pytest tests/ -x -q`: **1,260 passed, 3 skipped, 0 failures**
