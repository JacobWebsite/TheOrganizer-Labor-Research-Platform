# 2026-04-28 (parallel session) — R7-7 Search Ranking + Alias Dictionary

Closed R7-7 from the R7 audit. Parallel-safe session: another Claude Code
session simultaneously working R7-4 (frontend demographics vintage). Stayed
clear of `WorkforceDemographicsCard.jsx`, demographics hook in
`profile.js`, and `api/routers/demographics.py`.

## Commits

```
cf4e24f  backend: harden _load_aliases against malformed alias config (Codex finding)
5a6037b  backend: R7-7 search ranking tiebreak + alias dictionary for collision exclusions
```

Both unpushed.

## Changes Made

### Part 1 — ORDER BY tiebreak in `api/routers/employers.py:378,383`

Replaced `unit_size DESC NULLS LAST` tiebreak with:

```sql
similarity(search_name, %s) DESC,
CASE WHEN canonical_group_id IS NOT NULL THEN 0 ELSE 1 END,
COALESCE(consolidated_workers, unit_size, 0) DESC,
unit_size DESC NULLS LAST
```

(Default order without name uses the same secondary keys, no similarity prefix.)

Effect: F7 canonical group leaders outrank ungrouped/MASTER fragments;
parent `consolidated_workers` beats per-store `unit_size`. Verified by direct
SQL — Starbucks query now ranks the F7 grouped canonical (consolidated_workers
=119) above flat MASTER per-store rows.

**Limitation:** MASTER source_type rows are flat (no canonical_group_id, no
consolidated_workers). Walmart and Amazon queries return all-MASTER results
where the new keys all evaluate equal, so the query still falls through to
`unit_size DESC`. The Walmart HI store (us=25,000) still ranks above Walmart
Inc TX (us=10,000,000) because the latter has lower trigram similarity
(0.95 vs 1.000). Fixing this needs the alias-name-expansion lift the audit
estimated at 4-8 hrs.

### Part 2 — Alias dictionary

New file: `config/employer_aliases.json` with 5 seed entries:

| Canonical | Aliases | Excludes |
|---|---|---|
| Cleveland Clinic Foundation | cleveland clinic, ccf | cleveland-cliffs, cleveland cliffs |
| New York City Health and Hospitals Corporation | nyc health and hospitals, nyc health + hospitals, nyc hhc, h+h | nyu langone, nyu hospital, nyu medical |
| Health Care Service Corporation | hcsc | (documentation only) |
| Walmart Inc | walmart, wal-mart, walmart stores | (documentation only) |
| Amazon.com Inc | amazon | (documentation only) |

Module-level loader in `employers.py` (added near imports). Lazy-loaded,
process-cached. Wired into `unified_employer_search`: when the user's query
contains an entry's alias, each `exclude_terms` substring becomes a
`LOWER(search_name) NOT LIKE %s%%` WHERE clause.

### Codex follow-up — fail-open hardening

Original loader caught `FileNotFoundError` / `JSONDecodeError` / `OSError` but
would `AttributeError` if the JSON parsed to a non-dict top-level (`[]`, `null`,
string), or if entries weren't dicts. Hardened to type-check the root + array
+ each entry. Verified across 7 malformed-input scenarios — all return `[]`
without crashing.

## Key Findings

### Codex CLI worked despite documented gpt-5.5 error

`codex exec` (still version 0.125.0, Jacob hasn't run the upgrade) produced
a coherent review of the 121-line diff and caught a real bug. Some shell
sub-tool calls inside codex got "blocked by policy" but the model output
was usable. The gpt-5.5 error from prior sessions may have been transient
or scoped to specific request sizes.

### Walmart-style "flat MASTER" canonical-resolution gap

Multiple `MASTER` source_type rows for the same logical company exist in
`mv_employer_search` (e.g. ~140 'WALMART' MASTER rows, one per state).
None has `canonical_group_id` or `consolidated_workers` populated — those
are F7-specific. The "real" Walmart Inc parent (MASTER-7347982 with
`unit_size=10,000,000`) is differentiable only by size, but its trigram
score against "walmart" is lower than per-store rows, so it doesn't tie
in the ORDER BY's primary key.

This is a deeper schema/ETL gap, not a query-time fix. Note for future:
mass-canonicalize MASTER rows (assign a `master_canonical_id` representing
the corporate parent) before further search-ranking work.

### The alias `exclude_terms` semantic is conservative-by-design

Filters rows when they contain a known collision term. Doesn't BOOST the
canonical entity. So:
- Cleveland Clinic case ✓ (Cleveland-Cliffs filtered → Cleveland Clinic
  Foundation surfaces in top 5)
- NYC Hospitals case ⚠️ (NYU filtered → but canonical NYC HHC has too-low
  trigram score to surface; would need alias-name expansion to OR-search
  on the canonical name)

## Roadmap Updates

- **R7-7 closed** (search ranking tiebreak + alias dictionary). Limitation
  documented: flat-MASTER cases (Walmart/Amazon) still need the 4-8 hr
  alias-name-expansion lift.
- Operational items prepared for Jacob — commands listed in summary report:
  - REG-3 (postgres listen_addresses)
  - REG-7 (NLRB nightly cron install)
  - Codex CLI upgrade
- Two items dropped from yesterday's "small wins" list (verified resolved):
  - `build_target_data_sources` rc=1 (script now succeeds, 5.39M rows)
  - `vite.config.js` proxy revert (already at `:8001`)

## Debugging Notes

- **Verification done via direct SQL, not HTTP.** The running uvicorns on
  `:8001` and `:8005` have multiple LISTENING entries from zombie processes
  (PIDs 27536, 42256, 35008, 8912). Connections may route to zombies with
  stale code. Direct DB query bypasses this entirely. Pattern documented in
  yesterday's session memo (Windows kernel-zombie-socket).
- **`Path(__file__).resolve().parents[2]`** in `employers.py` correctly
  resolves to the project root — `parents[0]=routers`, `parents[1]=api`,
  `parents[2]=project_root`. Codex confirmed.
- **Loader cache uses `_ALIAS_CACHE = None` sentinel.** First call lazily
  loads. Subsequent calls return the cached list. Module reload (uvicorn
  --reload) resets the cache. No invalidation needed for in-process state.

## Files Modified

```
api/routers/employers.py        (53 + 11 = 64 net lines added; tiebreak + loader + filter + Codex fix)
config/employer_aliases.json    (new file, 5 entries)
```

## Pending Operational (Jacob runs)

```sql
-- REG-3: postgres listen_addresses
ALTER SYSTEM SET listen_addresses = 'localhost';
-- Then: Restart-Service postgresql-x64-17  (elevated PowerShell)
```

```powershell
# REG-7: NLRB nightly cron
powershell -ExecutionPolicy Bypass -File "C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\maintenance\setup_nlrb_nightly_task.ps1"
# Then: py scripts/maintenance/create_data_freshness.py --refresh
```

```bash
# Codex CLI upgrade
npm install -g @openai/codex@latest
```
