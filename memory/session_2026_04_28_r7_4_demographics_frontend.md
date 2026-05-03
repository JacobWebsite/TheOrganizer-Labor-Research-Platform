# Session: R7-4 Demographics Vintage Frontend (2026-04-28 PM)

Closes the last open R7 demographics audit item. Companion to R7-1/R7-2/R7-3 (already shipped earlier today and on 2026-04-27).

## Changes Made

### `api/routers/profile.py`
- New module-level constants near top (line ~17):
  ```py
  ACS_PUMS_VINTAGE = "2022"   # mirrors api/routers/demographics.py
  LODES_VINTAGE = "2022"
  ```
- `_get_acs_demographics()` returns `"vintage_year": ACS_PUMS_VINTAGE` (line ~1106).
- `_get_lodes_demographics()` returns `"vintage_year": LODES_VINTAGE`; source string converted to f"LODES {LODES_VINTAGE} (Census Bureau)" (line ~1135-1136).
- Older `/workplace-demographics` endpoint at line ~847 also gets `vintage_year` and f-string source for consistency.

### `frontend/src/features/employer-profile/WorkforceDemographicsCard.jsx`
- Lines 361 and 366: replaced `\`ACS 2022\`` and `\`LODES 2022 county ...\`` template literals with reads from `data.acs?.vintage_year` and `data.lodes?.vintage_year`. Wrapped in `.trim()` to handle missing-vintage edge case.

### `frontend/vite.config.js`
- Proxy target moved `:8005` → `:8002` (third Windows zombie-socket pattern in 4 days). Comment block extended.

## Key Findings

- **R7-4 needed both backend + frontend, not "frontend-only" as the roadmap implied.** The `WorkforceDemographicsCard` reads from `/workforce-profile` (`profile.py:1652`), which is *separate* from the demographics endpoints (`demographics.py`) that c54da60 fixed yesterday. Two parallel demographics surfaces, two parallel sets of constants, easy to miss.
- **R7-1 already shipped via separate session today** (`session_2026_04_28_r7_1_demographics_etl_fix.md` exists; `Work Log/2026-04-28 - R7-1 Demographics ETL Deep Fix.md`). Verified live: NY hospitals state-fallback returns `total_workers=11.86M`, not 145M.
- **Windows zombie-socket pattern is now operational debt.** Third recurrence in 4 days. `Stop-Process` reports success, `Get-Process` returns gone, but `Get-NetTCPConnection -State Listen` still shows the dead PID owning the port. Reboot is the only known cure.

## Roadmap Updates

- **R7-4**: OPEN → DONE (live curl verified through Vite proxy, 21/21 frontend tests pass)
- R7-1, R7-2, R7-3: confirmed DONE (R7-1 verified live this session)
- Open R7 items now: R7-7, REG-2, REG-3, REG-4, REG-5, REG-6, REG-7, DISABLE_AUTH flip, PHONETIC_STATE deactivation
- 7 unpushed commits (yesterday's 6 + this R7-4)

## Debugging Notes

- uvicorn `--reload` on Windows uses `StatReload`. When you restart uvicorn while the file already has changes (vs. saving while uvicorn is running), the new worker SHOULD load the new code at startup. We hit a case where this seemed to fail — but the actual cause was the second uvicorn never bound :8005 (zombie holder), so curl on :8005 still hit the old original worker. Switch ports to verify clean.
- When verifying live API changes on Windows, confirm `Get-NetTCPConnection -LocalPort N -State Listen` returns the PID of your *new* uvicorn, not a zombie. PIDs that no longer exist as processes can still own listening sockets.
- ACS may return `null` for many F7 employers (NAICS 2-digit too short, state FIPS unknown). Test ACS verification with an employer that has `naics_detailed >= 4 chars`. LODES is more robust (county_fips + non-null `jobs_white`).

## Files Modified
- `api/routers/profile.py`
- `frontend/src/features/employer-profile/WorkforceDemographicsCard.jsx`
- `frontend/vite.config.js`
