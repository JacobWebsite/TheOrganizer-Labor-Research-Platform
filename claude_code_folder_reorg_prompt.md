# Claude Code Task: Project Folder Reorganization

## Context

This is the labor-data-project at `C:\Users\jakew\Downloads\labor-data-project`. Read CLAUDE.md and UNIFIED_ROADMAP_2026_02_17.md first to understand the project.

The project has grown organically over months and the folder structure is messy. There are 778 Python files, 102 SQL files, and ~9.3 GB of data files that have already been imported into the database and serve no purpose on disk. There's no way to tell which scripts are part of the active pipeline vs one-time experiments vs dead code.

## What I Need You To Do

Reorganize the project folder so it's clean, navigable, and easy for AI tools (Claude Code, Codex, Gemini) to understand quickly. Do NOT delete anything permanently — move things to clearly labeled archive folders.

Work in checkpoints. Complete each checkpoint, show me the results, and wait for my approval before moving to the next one.

---

## Checkpoint 1: Survey and Inventory

Before moving anything, build a complete picture of what exists.

1. List every top-level directory and its size
2. Count Python files by directory (scripts/etl, scripts/matching, scripts/scoring, scripts/analysis, scripts/cleanup, api/, tests/, archive/, etc.)
3. Identify the ~45 critical pipeline scripts listed in the audit (the ones in CLAUDE.md under ETL loaders, matching pipelines, and scoring/enrichment). Confirm they all exist.
4. Identify dead code: scripts referencing nonexistent tables, the 3 dead API monoliths in api/, the 5 stale .pyc files
5. Identify large data files in the project root or non-archive directories that are already imported into PostgreSQL (SQLite databases, SQL dumps, CSV exports, PostgreSQL installers)
6. Check how many scripts use the broken credential pattern (`password='os.environ.get(...)' ` as a string literal) vs the correct `db_config` import

Show me the full inventory before proceeding.

---

## Checkpoint 2: Create the Target Folder Structure

Create (but don't move anything yet) the new folder structure:

```
labor-data-project/
├── api/                        # Keep as-is (FastAPI backend — already modular)
│   └── routers/                # Keep as-is (17 router files)
├── frontend/                   # Keep as-is (HTML/JS interfaces)
├── scripts/
│   ├── pipeline/               # NEW — only active pipeline scripts go here
│   │   ├── etl/                # Data loading scripts (load_f7_data.py, load_sam.py, etc.)
│   │   ├── matching/           # Matching pipeline (osha_match_phase5.py, splink_pipeline.py, etc.)
│   │   └── scoring/            # Score computation (compute_gower_similarity.py, etc.)
│   ├── maintenance/            # NEW — scripts that run periodically (refresh views, health checks)
│   ├── analysis/               # Keep — ad-hoc analysis scripts (useful as templates)
│   └── archive/                # NEW — one-time scripts that already ran, superseded versions
├── sql/                        # Keep as-is
├── tests/                      # Keep as-is
├── docs/                       # Keep as-is
├── config/                     # NEW — .env, db_config.py, any config files
├── data/                       # Keep — only small reference files (EPI benchmarks, etc.)
├── archive/                    # Keep — historical documentation + dead code
│   ├── old_scripts/            # Dead/superseded scripts
│   ├── old_api/                # Dead API monoliths
│   ├── old_roadmaps/           # Superseded roadmap versions
│   └── imported_data/          # Data files already in PostgreSQL (keep compressed backups only)
└── PIPELINE_MANIFEST.md        # NEW — the script manifest (see Checkpoint 5)
```

Show me the proposed structure and confirm no naming conflicts before proceeding.

---

## Checkpoint 3: Move Dead Code and Redundant Data

This is the safe, non-controversial stuff:

1. Move the 3 dead API monoliths from `api/` to `archive/old_api/`
2. Delete the 5 stale `.pyc` files from `__pycache__/`
3. Move scripts that reference nonexistent tables to `archive/old_scripts/` (like `build_corporate_hierarchy.py` → `corporate_ultimate_parents`, `fetch_usaspending.py` → `federal_contracts`)
4. Move all superseded roadmap documents to `archive/old_roadmaps/`. These include: LABOR_PLATFORM_ROADMAP_v10.md through v13.md, ROADMAP_TO_DEPLOYMENT.md, Roadmap_TRUE_02_15.md, UNIFIED_ROADMAP_2026_02_16.md, SCORECARD_IMPROVEMENT_ROADMAP.md. Add a note file in that folder: "All roadmaps superseded by UNIFIED_ROADMAP_2026_02_17.md"
5. Identify all data files in the project that are already imported into PostgreSQL and are over 10 MB. List them with sizes. DO NOT delete yet — just list them for my review.

Show me what was moved, what's flagged for deletion, and wait for approval.

---

## Checkpoint 4: Organize Active Scripts

Move the confirmed active/critical scripts into the new `scripts/pipeline/` structure:

1. Copy (not move yet) each critical pipeline script to its new location under `scripts/pipeline/etl/`, `scripts/pipeline/matching/`, or `scripts/pipeline/scoring/`
2. Verify each copied script matches the original (same file size, same content)
3. Check that imports still work — if any script imports from another script, make sure the paths still resolve
4. Show me the before/after mapping (old path → new path) for every moved script

IMPORTANT: Do NOT break any imports. If scripts reference each other with relative imports, those need to be updated. If a script has hardcoded file paths, flag it but don't change the path yet.

Wait for approval before removing the old copies.

---

## Checkpoint 5: Build the Pipeline Manifest

Create `PIPELINE_MANIFEST.md` at the project root. This is the document that any AI tool or human reads to understand "what runs, and in what order."

Structure it like this:

```markdown
# Pipeline Manifest — Labor Relations Research Platform
Last updated: [date]

## How to Use This Document
This lists every active script in the platform's data pipeline.
Scripts are organized by stage. Within each stage, run order matters where noted.

## Stage 1: ETL — Loading Raw Data
| Script | What It Does | Source Data | Run When |
|--------|-------------|-------------|----------|
| scripts/pipeline/etl/load_f7_data.py | Loads F-7 employer filings | DOL OLMS | New F-7 data available |
| ... | ... | ... | ... |

## Stage 2: Matching — Connecting Data Sources
| Script | What It Does | Depends On | Run When |
|--------|-------------|------------|----------|
| ... | ... | ... | ... |

## Stage 3: Scoring — Computing Scores
| Script | What It Does | Depends On | Run When |
|--------|-------------|------------|----------|
| ... | ... | ... | ... |

## Stage 4: Maintenance — Periodic Tasks
| Script | What It Does | Schedule |
|--------|-------------|----------|
| ... | ... | ... |
```

Populate it by reading each active script's docstring and code to understand what it does. If a script has no docstring, add a brief description based on what the code actually does.

Show me the completed manifest for review.

---

## Checkpoint 6: Fix the Credential Pattern

The audit found 259 scripts using a broken credential pattern where the migration wrapped `os.environ.get(...)` in quotes, turning it into a string literal instead of a function call. These scripts can't connect to the database.

1. First, identify which of these 259 scripts are in the active pipeline (moved to `scripts/pipeline/`). Fix those first — change them to use the correct `from db_config import get_connection` pattern.
2. For scripts now in `scripts/analysis/` — fix them too if it's a simple find-and-replace.
3. For scripts in `archive/` — leave them as-is. They're archived and won't be run.
4. Remove the hardcoded password fallback from `scripts/scoring/nlrb_win_rates.py`.

Show me a count of: fixed, left alone (archived), and any that couldn't be automatically fixed.

---

## Checkpoint 7: Create PROJECT_STATE.md

Create a `PROJECT_STATE.md` file at the project root. This is the shared context document that all AI tools read at the start of any session. It replaces the need for each AI to figure out the project from scratch.

Include these sections:

### Section 1: Quick Start
- Database connection info (reference .env, don't include actual credentials)
- How to start the API server (the CORRECT command)
- How to run tests

### Section 2: Database Inventory (auto-generatable)
- Write a small Python script (`scripts/maintenance/generate_db_inventory.py`) that connects to the database and outputs:
  - Total table count
  - List of all tables with row counts
  - Total view count  
  - Materialized view list with row counts
  - Database size
- Run it and paste the output into this section
- Note at the top: "Auto-generated by scripts/maintenance/generate_db_inventory.py on [date]. Re-run to refresh."

### Section 3: Active Pipeline
- Point to PIPELINE_MANIFEST.md

### Section 4: Current Status and Known Issues
- Pull from UNIFIED_ROADMAP_2026_02_17.md Part 2 (What's Wrong)
- Summarize: what's broken, what's being worked on, what's next

### Section 5: Recent Decisions
- Pull from UNIFIED_ROADMAP_2026_02_17.md Appendix B (the 25 decisions table)
- This section gets manually updated after each work session

### Section 6: Key Design Rationale
- Why signal-strength scoring instead of penalizing missing data
- Why Splink over trigram for fuzzy matching
- Why F-7 is the foundation (not OSHA or NLRB)
- Why master employer key is deferred

---

## Rules

- **Never delete files permanently.** Move to archive.
- **Never break imports.** If moving a script would break another script's import, fix the import or flag it for me.
- **Show before/after at every checkpoint.** I need to see what changed.
- **Don't modify any database tables.** This is file organization only.
- **Don't modify any script logic.** Only move files, fix import paths, and fix the credential pattern. No refactoring.
- **If anything is ambiguous, ask.** Don't guess whether a script is active or dead — if you can't tell, flag it for me to decide.
