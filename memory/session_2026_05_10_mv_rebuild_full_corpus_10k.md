# 2026-05-10 / 2026-05-11 -- MV Rebuild + Full-Corpus 10-K Entity Extraction + Stop-List Cleanup

## Changes Made

Three-step session driven by the user (`/start` → "MV rebuild" → "do 10k filling" → "do all 3 in order"). No new agents dispatched; all work direct.

### Step 1 -- MV rebuild (closes critical Open Problem)

`py scripts/scoring/refresh_all.py --skip-gower` -- 660s (~11 min). Rebuilt all 6 critical MVs/tables incl. the 2 that had silently vanished post-2026-05-08:

| MV | Floor | Rebuilt rows | Step duration |
|---|---|---|---|
| `mv_organizing_scorecard` (v275) | -- | 211,357 | 26.7s |
| `mv_employer_data_sources` | -- | 146,863 | 10.5s |
| `mv_unified_scorecard` | -- | 146,863 | 59.3s |
| `mv_target_data_sources` | -- | 5,790,584 | 101.4s |
| **`mv_target_scorecard`** | >= 1,000,000 | **5,502,684** | 432.5s |
| **`mv_employer_search`** | >= 100,000 | **449,949** | 29.6s |

Score v275 timestamp 2026-05-10 11:40 ET. Scores: min=11, avg=31.6, max=56.

Smoke-tested previously-broken endpoints on Abbott (master 4036186):

- `/api/employers/master/4036186/board` -> HTTP 200, 12 directors (was silently 500-erroring on 95% of populated masters per 5/9 BoardCard QA agent)
- `/director-network` -> HTTP 200
- `/executives` -> HTTP 200
- Unified-search `walmart` -> 547 results (was 0 -- mv_employer_search dependency)

Tier distribution post-rebuild: Priority 0.7% / Strong 1.9% / Promising 5.2% / Moderate 54.2% / Low 25.8% / Speculative 12.3% (5/6 P0 #5 split still in effect).

Closed `[[Open Problems/Critical MVs Missing After 2026-05-08]]` (critical).

### Step 2 -- Full-corpus 10-K entity extraction + matching

Discovered the 5/9 6-agent sprint had already staged W2 + most of W3 of the launch roadmap; only W4 (entity extraction at scale) remained. Pipeline state at session start vs after today's drive:

| Stage | Was | Now |
|---|---|---|
| Queue (`sec_10k_filings_to_download`) | 1,501 | 1,501 + 2 new 2026 filings detected |
| Downloads (`load_sec_10k_progress`) | 1,484 / 1,501 | **1,486 / 1,501** (5.2 GB on disk) |
| Sections (`sec_10k_sections`) | 4,233 from 1,363 filings | **4,235 from 1,364 filings** |
| Entities (`sec_10k_extracted_entities`) | 25 (5/9 sample) | **1,491** then **1,362** post-stop-list |
| Matched links (`sec_10k_relationship_links`) | 25 (5/9 sample) | **1,362 / 479 matched (35.2%)** |

Drained 2 pending downloads (AT&T's 2026-02-09 10-K + Cognizant's 2026-02-12 10-K -- newer than 5/8 queue). Both auto-detected by re-running `identify_recent_10k.py --limit 5` (idempotent; UPSERTs new accessions on the same CIK).

Section breakdown of 4,235 parsed rows: business 1,331 + risk_factors 1,322 + customers 566 + distribution 498 + suppliers 350 + partners 168.

Match rates by relationship type (post stop-list): customer 37.6%, supplier 31.8%, distribution 30.7% -- close to the 5/9 sample's 32%.

CSVs: `docs/scratch/sec_10k_matches_full_2026_05_10.csv` (pre stop-list, 1,491 rows) + `_v2.csv` (post stop-list, 1,362 rows).

### Step 3 -- Stop-list expansion + regression tests

Added 32 entries to `_STOP_EXACT` frozenset in `scripts/etl/sec_10k/extract_relationship_entities.py`:

- **10-K boilerplate** (sentence-boundary captures of "Part II, Item 8" etc.): `item`, `form`, `part ii`, `part iii`, `part iv`, `part v`, `form 10-q`, `form 8-k`, `risk factors`
- **Tech-industry abbreviations** (sentence-cap'd OEMs/MSPs that the regex picks up as proper nouns): `oem(s)`, `msp(s)`, `isp(s)`, `var(s)`, `ems`, `odm(s)`, `osat(s)`, `diy`, `sis`
- **Sentence-starters / pronouns** (capitalized at sentence start): `sales`, `net sales`, `internet`, `while`, `while the company`, `two`, `fortune`, `canadian`, `company's`
- **Sentence-boundary bug** (parser splice): `raw materials the company`

Added 5 regression tests in `tests/etl/test_sec_10k_extract_entities.py` (file went 14 -> 19 tests, all pass):

- `test_is_acceptable_entity_rejects_10k_boilerplate` (8 cases)
- `test_is_acceptable_entity_rejects_tech_jargon_acronyms` (15 cases)
- `test_is_acceptable_entity_rejects_sentence_starters_and_pronouns` (9 cases)
- `test_is_acceptable_entity_rejects_sentence_boundary_bug` (1 case)
- `test_is_acceptable_entity_does_not_overreach` (4 cases) -- guards Salesforce / Salesforce.com Inc / Fortune Brands Innovations / Canadian Pacific Railway still extract correctly. **Critical** -- without this overreach-guard test, future stop-list expansions would risk vetoing real companies whose names contain a stopped substring.

Re-ran extract + match on full corpus. `sec_10k_relationship_links` FK has `ON DELETE CASCADE` to `sec_10k_extracted_entities.id`, so extract's per-filing DELETE auto-cleaned stale links -- no manual cleanup needed.

Outcome:

| Metric | Pre-stop-list | Post-stop-list | Delta |
|---|---|---|---|
| Total entities | 1,491 | 1,362 | -129 (-8.7%) |
| Matched links | 513 | 479 | -34 |
| Match rate | 34.4% | **35.2%** | +0.8pp |
| Customer entities | 757 | 694 | -63 |
| Supplier entities | 242 | 216 | -26 |
| Distribution entities | 492 | 452 | -40 |
| Empty-result sections | 951 | 999 | +48 |
| Distinct entity_text | 1,267 | 1,243 | -24 |

Headline match-rate lift was small (+0.8pp) but the real win is **34 spurious matches eliminated**: "Item" had 17 fake links to a master called "Item Corp" (or similar trigram match), "Part II" 7 fakes, "ODMs" 3, "Form" 7, "Canadian" 3. All now 0.

Top-matched entities post-cleanup all look like real companies: Amazon ×8, Walmart ×7 + Walmart Inc ×6, McKesson Corporation ×5, Google ×4, Ford ×4, Microsoft ×4, Salesforce ×3, Apple ×3, Cardinal Health ×3, Facebook ×3, General Motors ×3, Target ×3, Lockheed Martin ×2, AutoZone ×2, Verizon ×2, Broadcom ×2, Arrow Electronics ×2, Honda ×2, Illumina ×2, AT&T ×2.

Fortinet (the smoke-test canary) unchanged: 1/1 customer matched, 3/3 distribution matched, 13/32 suppliers matched.

### Frontend smoke

Re-launched Vite preview on :5173 + uvicorn on :8001 (canonical, zombie socket from earlier session had released). Vite proxy `frontend/vite.config.js` left unchanged at :8001. Navigated Claude_Preview to `/employers/MASTER-4245176` (Fortinet) and confirmed via DOM query:

- All 3 new cards render with summary stats: Suppliers "13 matched | 32 mentioned", Customers "1 / 1", Distribution Partners "3 / 3"
- API calls hit (verified via `performance.getEntriesByType('resource')`): `/4245176/suppliers`, `/customers`, `/distribution-partners`
- 14 working cards on Fortinet's profile (Suppliers, Customers, Distribution Partners are the new ones from the 5/9 sprint)

`preview_screenshot` timed out after 30s (transport limit; page itself rendered fine -- `document.readyState === 'complete'`, `bodyLen === 1580` chars). Used `preview_eval` DOM queries instead.

## Key Findings

- **5/9 6-agent sprint had already done much of W2 + W3**: 1,501 filings queued + 1,484 downloaded + 4,233 sections parsed on 5/8. Only W4 (entity extraction at scale) and W4 (matching at scale) remained as actual work. Re-running W2 (`identify_recent_10k.py --limit 5`) at session start was wasted effort -- a `SELECT COUNT(*) FROM sec_10k_filings_to_download` would have shown 1,501 rows already there.

- **ETL scripts default to sample-mode for dev safety**: `extract_relationship_entities.py` defaults to `--limit 50`, `match_extracted_entities.py` defaults to `--limit 100` + `--commit=False` (dry-run). First full-corpus invocation needs `--limit 0 --commit` (0 in `if args.limit > 0 else None` becomes "no LIMIT clause"). Without this, the first run looks like the script is broken.

- **Windows zombie socket self-releases**: 5th recurrence. Killed PID 26968 on :8001, netstat showed socket bound 5 min after kill, but a curl 3 min later succeeded -- socket had released on its own. CLAUDE.md's "reboot to free" guidance is the worst case, not the default. **Retry netstat after 3-5 min before deciding to switch ports.**

- **`/api/employers/search` is F-7 only** (deprecated): my first smoke test against this endpoint with `name=walmart` returned 0 results (correct -- Walmart has no F-7 unions). The right endpoint for master_employers search is `/api/employers/unified-search?name=walmart` which returned 547 rows. Searched the wrong endpoint for 2 cycles before noticing.

- **Background processes from prior sessions die silently**: at session start, `netstat` showed :8001 + :5173 listening. By mid-session both servers were dead (curl returned 000). "Process listed by netstat" != "responsive process" -- always `curl /api/health` alongside netstat.

- **`Claude_Preview` `screenshot` times out at 30s** even when the page renders fine. Use `preview_eval` DOM queries as the verification primitive instead. The eval responses are fast and explicit.

- **Vite + uvicorn launched from a Bash session die when that session ends**, even though the tool said "running in background." For long-running dev servers, use `Claude_Preview` `preview_start` (which spawns via a daemon) rather than `Bash run_in_background`.

## Roadmap Updates

Closed/Done (versus `ROADMAP_2026_05_04_to_2026_07_05_LAUNCH.md`):
- **Week 1 B.1.1-B.1.4** -- already done 5/5
- **Week 2 10-K filing identification** -- already done 5/8 (1,501 filings queued)
- **Week 3 10-K bulk download** -- 99% done 5/8 (1,486/1,501 on disk)
- **Week 3 10-K parser foundation** -- already done 5/8 (4,235 sections from 1,364 filings)
- **Week 4 10-K extracted-entity matcher** -- done today (1,362 entities, 479 matched, 35.2% rate, top-mentioned all real companies)
- **Critical MV regression** -- closed today

Still need:
- **B.1.5** DISABLE_AUTH flip + JWT rotation -- needs Jacob
- **REG-3** Postgres listen_addresses -- needs Jacob
- **REG-7** NLRB cron install -- needs Jacob
- **A.2 FacilitiesMapCard** -- partially done (FacilitiesMapCard.jsx + FacilitiesLeafletMap.jsx + api/routers/facilities.py already in working tree from 5/9 sprint; need to verify completeness)
- **C.5 Power Profile PDF** -- partially done (api/routers/power_profile.py + api/services/power_profile_renderer.py + scripts/etl/contracts/... already in working tree)
- **B.4 FP-rate adjudication** -- W7 deliverable
- **Beta tester onboarding** -- W7 deliverable

## Debugging Notes

- `git status` in project repo showed 20 modified + ~150 untracked files. Last commit on master is `86ca1ed` (2026-05-08). Everything since (5/9 6-agent sprint + today's work) is uncommitted. The 5/9 sprint files in `scripts/etl/sec_10k/`, `api/routers/relationships.py`, `tests/etl/`, `tests/test_relationships_router.py`, and the Suppliers/Customers/Distribution/Comparables/FacilitiesMap/Competitors cards are all sitting untracked on master.

- The `_STOP_EXACT` frozenset uses lowercased exact-match against the cleaned entity text. So adding `"oem"` blocks "OEM", "OEMs", "oem" all the same. Adding `"sales"` does NOT block "Salesforce" (the multi-token mention bypasses exact-match). Verified via the overreach test.

- `sec_10k_relationship_links.source_entity_id` FK has `ON DELETE CASCADE` to `sec_10k_extracted_entities.id`. So `extract_relationship_entities.py`'s per-filing DELETE auto-cleans stale links. No manual TRUNCATE needed between extract + match re-runs.

- `match_extracted_entities.py`'s ON CONFLICT key is `(source_entity_id, relationship_type)` UNIQUE NULLS NOT DISTINCT (from 5/9 fix). So if you DON'T re-extract before re-matching, you'd get duplicate link rows for the same source entity (unmatched + matched coexisting). Re-extract is the correct flow.

- Default `--limit 50` (extract) and `--limit 100` (match) plus `--commit=False` are dev-safety guardrails. Production invocation needs `--limit 0 --commit` for the matcher.

## Files Modified

**Project code (git-trackable, in `C:\Users\jakew\.local\bin\Labor Data Project_real`):**
- `scripts/etl/sec_10k/extract_relationship_entities.py` -- +32 lines to `_STOP_EXACT` frozenset. File is untracked from 5/9 sprint; this commit will be its first commit.
- `tests/etl/test_sec_10k_extract_entities.py` -- +5 test functions (~70 lines), 37 cases total. File is untracked from 5/9 sprint; this commit will be its first.
- `Start each AI/PROJECT_STATE.md` -- new "Latest session (2026-05-10 / 2026-05-11)" paragraph + heading date bumped.
- `memory/session_2026_05_10_mv_rebuild_full_corpus_10k.md` -- this file.

**Vault (not git-tracked):**
- `Open Problems/Critical MVs Missing After 2026-05-08.md` -- status: open -> resolved
- `.claude/napkin.md` -- 7 new corrections rows + 4 new patterns
- `Work Log/2026-05-10 - MV Rebuild + Full Corpus 10-K Entity Extraction.md` -- new
- `.claude/launch.json` -- added `labor-frontend` preview config on :5173

**Output artifacts (gitignored scratch):**
- `docs/scratch/sec_10k_matches_full_2026_05_10.csv` (v1, 1,491 rows)
- `docs/scratch/sec_10k_matches_full_2026_05_10_v2.csv` (post-stop-list, 1,362 rows)
