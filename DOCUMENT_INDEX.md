# Document Index

> **Last touched:** 2026-05-02 PM-late (**DeepSeek V4 A/B Test and Rule Mining** -- Costed V4-Pro 75% promo against deferred-API-spend backlog (ends 2026-05-31). Built reusable A/B harness `scripts/llm_dedup/deepseek_ab_test.py` (569 lines, NEW, untracked). Ran 200-pair A/B on V4-Flash and V4-Pro vs 39K Haiku v2.0 ground-truth. **V4-Flash: 77.5%/87.0% / $0.044 / $1,112 5M-pair extrapolation (3.1× cheaper than Haiku batch).** **V4-Pro promo: 80.5%/89.0% / $0.213 / $5,337 5M extrapolation (worse than Haiku batch).** Both below 92% confidence bar. V4-Pro fixes V4-Flash's PARENT_CHILD parse-fail bug (5/6→0/0 empty content) and returns BROKEN labels. DeepSeek prompt caching is automatic (no `cache_control` flag); cache hit 91.9%/91.4% on the 5,230-token system prompt. **Killer finding**: hand-verified Haiku ground truth on AWAKE.ORG / CRAWFORD CONTRACTING / UNIVERSAL MALL via direct DB lookups — Haiku had **hallucinated R1 EIN-conflict violations** (R1 requires BOTH records have EINs; only one EIN existed in 2 of 3 "false merge" cases). True V4-Flash false-merge rate is ~1.0% not 1.5-3.5%; in 4 of 8 disagreement cases DeepSeek was MORE correct than Haiku. Triple-convergence (Haiku+Flash+Pro all agree) = 146/200 pairs, usable cheap-ground-truth method. **Mined 39K Haiku set for rule candidates**: 4 hard rules at ≥95% concentration (12% of pairs at 99.79% accuracy); 6 strong at ≥90% (57% at 95%). Most signals already covered by H1-H16 in `rule_engine.py`. **4 new rule candidates drafted but NOT coded** (Jacob deferred to next session): (1) real-EIN-conflict guard hardening `has_ein_conflict()` to require BOTH records have non-empty EINs; (2) H17 cross_src_one_ein_same_zip → DUPLICATE/MEDIUM (catches AWAKE/CRAWFORD pattern); (3) H18 industry_mismatch hard rule (different 2-digit NAICS prefix → UNRELATED/HIGH); (4) H19 GLEIF person-name → BROKEN. Coverage math: tuned rule_engine + V4-Flash hybrid = ~$400/5M (vs V4-Flash alone $1,112 vs Haiku batch $3,500-4,200). **Recommendation**: skip V4 for dedup sweep (keep Haiku or build rule-engine + V4-Flash hybrid); use V4-Flash for cheap deferred items (10-K employee extraction $48 vs $140 Gemini, union scraper distillation $1.50 vs $30 Sonnet, dossier search $15/100 vs $100 Gemini). DeepSeek `.env` line `DeepSeek API=sk-...` has space in var name — trips python-dotenv; built regex fallback. OpenAI SDK 2.20.0 fully compatible with `base_url="https://api.deepseek.com"`. V4 thinking-mode reasoning tokens consumed initial 300-token budget — bumped max_tokens to 3000. **Earlier "CSV verdict bug" audit chip filed at start of session was duplicate of the same-day fix** (CSV is now correct on disk). Total API spend this session $0.26. No DB changes. No code edits to existing files. No git commits. New session memory at `memory/session_2026_05_02_deepseek_v4_ab_test.md` + vault `Work Log/2026-05-02 - DeepSeek V4 A_B Test and Rule Mining.md`.)
>
> **Earlier 2026-05-02 PM:** (**Validation CSV Verdict Parser Bug Fix** -- 30-min hot-fix on top of earlier work today. Patched silent-corruption bug in scripts/llm_dedup/submit_anthropic_batch.py:280 + submit_validation_batch.py:285 (v2.0 prompt returns label+reasoning, fetcher hardcoded verdict+reason). Regenerated anthropic_validation_batch_results.csv (39,127 rows from 2026-04-21 batch, previously all verdict=UNKNOWN). New distribution matches raw JSONL exactly: SIBLING 13,076 / UNRELATED 9,346 / DUPLICATE 8,419 / RELATED 7,484 / PARENT_CHILD 790 / BROKEN 11. Downstream consumers audited clean. Codex crosscheck: no findings. New: `memory/session_2026_05_02_validation_csv_verdict_fix.md` + vault `Work Log/2026-05-02 - Validation CSV Verdict Parser Bug Fix.md` + vault `Open Problems/Validation CSV Verdict Parser Bug.md` (status: resolved). EARLIER (same day): **24Q Cards Sprint -- 3 cards shipped on master profile in one session**. **24Q-31 EnvironmentalCard** Q21 Weak->Strong: new `scripts/maintenance/cleanup_epa_echo_duplicates.py` (removed 2,277 dup masters + 4,384 over-linked registry_ids -> 0; closed [[EPA Master Duplicates from 2026-04-30 Seed]]); MV refresh; new `api/routers/epa.py` (`GET /api/employers/master/{id}/epa-echo`); new `frontend/src/features/employer-profile/EnvironmentalCard.jsx`; new `tests/test_epa_echo_endpoint.py` (5 tests) + `frontend/__tests__/EnvironmentalCard.test.jsx` (7 tests); all green. **24Q-7 ExecutivesCard** Q8 Medium->Strong: new `api/routers/executives.py` with title-rank heuristic (Board Chair->CEO->President->CFO/COO->C-Suite->EVP/SVP/VP->Manager); new `frontend/src/features/employer-profile/ExecutivesCard.jsx` (UX correction: dropped rank chrome, names + titles only); new `tests/test_executives_endpoint.py` (6 tests incl. Vice Chairman regression guard) + `frontend/__tests__/ExecutivesCard.test.jsx` (7 tests); all green; corrected stale 57K MEMORY figure (actual 334,082 rows). **24Q-9 SEC 13F** Q9 Missing->Strong: new `scripts/etl/load_sec_13f.py` (handles root + nested-subdir ZIP variants via `_resolve_tsv_path`); new `scripts/etl/match_sec_13f_to_masters.py` (exact + trigram >= 0.85); new `api/routers/institutional_owners.py`; new `frontend/src/features/employer-profile/InstitutionalOwnersCard.jsx` (minimal chrome: matched-vs-not-matched panels, top 10 with show-all expand); new `tests/test_institutional_owners_endpoint.py` (5 tests written, NOT yet run) + `frontend/__tests__/InstitutionalOwnersCard.test.jsx` (8 tests, all green). **DB**: new `sec_13f_submissions` (43,358 rows), `sec_13f_holdings` (13,540,605 rows), `sec_13f_issuer_master_map` (12,706 rows = 9.2% issuer coverage matched to 9,230 distinct masters); MVs `mv_target_data_sources` + `mv_target_scorecard` rebuilt post-EPA-cleanup. **Edited**: `api/main.py` (3 new router registrations; reformatter dropped imports 3x — workaround: re-add then verify with grep), `frontend/src/shared/api/profile.js` (3 new hooks: useMasterEpaEcho, useMasterExecutives, useMasterInstitutionalOwners), `frontend/src/features/employer-profile/EmployerProfilePage.jsx` (wired 3 new cards into master path). **Vault updates**: [[Open Problems/EPA Master Duplicates from 2026-04-30 Seed]] -> resolved; [[Data Sources/Enforcement and Workplace Conditions/EPA ECHO]] partially-integrated -> fully-integrated; [[Systems/24 Questions Framework]] Q8 + Q21 + Q9 status updated; coverage scorecard 8/6/5/5 -> 10/6/4/4 strong/medium/weak/missing. **Background**: FEC indiv24.zip downloaded to 4.0 GB (loader not yet run). **LDA API key now available** (Jacob has it in .env per session 2026-05-02 message). **Test totals**: 19/19 backend + 308/308 frontend on the components that ran; 5 institutional-owners backend tests written but not yet run. **18 new files, 3 modified**. New session memory `memory/session_2026_05_02_24q_cards_sprint.md` + vault `Work Log/2026-05-02 - 24Q Cards Sprint - EPA + Mergent Execs + SEC 13F.md`. No git commits.)
>
> **Earlier:** 2026-04-30 (**Beta Hardening + 24Q EPA + FEC partial — 10-hr marathon**.
> **Discovered + fixed `mv_target_scorecard` regression** silently missing 5 days; rebuilt 5,382,051 rows in 225s; underlying tables intact (no data loss). Patched `_check_mv` cache to self-heal future MV drops. **Two new release-checklist gates:** `scripts/maintenance/check_critical_routes.py` + `config/critical_routes.txt` (13 routes) and `scripts/maintenance/check_critical_mvs.py` + `config/critical_mvs.txt` (6 MVs/tables) — both wired into new `RELEASE_CHECKLIST.md`. **New `api/services/demographics_bounds.py`** + `tests/test_demographics_bounds.py` (16 tests, R7-1 reproduction at 145M NY caught) wired into 4 demographics endpoints. **PHONETIC_STATE deactivated** via new `scripts/maintenance/deactivate_phonetic_state.py` — 7,671 superseded across 8 sources (90% FP per R7); _RESOLVED variants left intact. **NLRB search dedup**: modified `scripts/scoring/rebuild_search_mv.py` DISTINCT ON to drop election_date; `mv_employer_search` 86,153 NLRB rows → 55,531 (-36%); Starbucks 183 → 86. **New frontend `SourceFreshnessFooter.jsx`** wired into Osha/Nlrb/WhdCard. **24Q-29/30 EPA ECHO closed**: new `scripts/etl/load_epa_echo.py` loaded 3,090,831 facilities in 211s (index-deferred); new `scripts/etl/seed_master_epa_echo.py` matched 286,284 source links; +209,022 new master rows; updated TWO CHECK constraints (chk_master_source_system + chk_master_source_origin); new `scripts/maintenance/verify_epa_echo_signal.py` confirmed top match Cummins Inc $1.67B; `mv_target_data_sources` refreshed (+209K) and `mv_target_scorecard` rebuilt (37,397 existing masters gained EPA cross-source enrichment). **Identity-grafting alias-collision layer** added to `scripts/research/tools.py:search_company_enrich` using `config/employer_aliases.json` exclude_terms; catches Cleveland Clinic → Cleveland-Cliffs (partial=83 slips fuzzy guard) + NYC Hospitals → NYU Langone; new `tests/test_company_enrich_guard.py` (13 tests). **24Q-38 FEC partial**: new `scripts/etl/load_fec.py` (4-file loader) loaded 3 of 4 (cm 20,941 + cn 9,804 + pas2 703,597; indiv24 deferred at 4+ GB); new `scripts/etl/seed_master_fec.py` matched 116 corporate PACs to 115 masters (Abbott, Amedisys, Auto Care, BancFirst). **Plan B doc sweep**: `CLAUDE.md` (5 fixes: tier counts off 5x, crosswalk 28K→39,827, Priority count 2,891→1,052, test counts, MV chain note); `.claude/agents/scoring.md` + `matching.md`; `.claude/specs/scoring-system.md` + `unified-scorecard-guide.md` + `roadmap.md` (D11/D12/D13 marked CLOSED; formula updated to dynamic-denominator). **6 new vault notes**: `Data Sources/Enforcement and Workplace Conditions/EPA ECHO.md`, `Data Sources/Federal Contracting and Tax/FEC Campaign Finance.md`, `Open Problems/mv_target_scorecard MV Missing.md` (resolved same day), `Open Problems/F7 Orphan Rate Regression.md` (root cause = Splink retirement, not today's PHONETIC), `Open Problems/FEC indiv24 Load Deferred.md`, `Open Problems/LDA Lobbying ETL Not Yet Built.md`. **Test status**: 16/16 demographics_bounds + 13/13 company_enrich_guard + 14/14 ProfileCards frontend pass; 1 pre-existing `test_data_freshness_endpoint` 403-vs-503 failure (auth middleware, not session). **38 files modified (24 new, 17 modified)**. New session summary at `memory/session_2026_04_30_beta_hardening_24q_epa_fec.md` + vault `Work Log/2026-04-30 - Beta Hardening + 24Q EPA + FEC.md`. 4th Windows zombie-socket recurrence on :8001 — reboot needed for live UI verification. **Codex crosscheck not run yet** — deferred to /ship. No git commits.)
>
> **Earlier:** 2026-04-28 PM, parallel session (**R7-7 Search Ranking + Alias Dictionary** — closed R7-7 in MERGED_ROADMAP_2026_04_25 while another Claude Code session simultaneously closed R7-4. Stayed clear of `WorkforceDemographicsCard.jsx`, demographics hook in `profile.js`, and `api/routers/demographics.py` to avoid cross-session conflict. **Two commits**: `5a6037b` (tiebreak ORDER BY in `unified_employer_search` now `similarity DESC, canonical_group_id NULL last, COALESCE(consolidated_workers, unit_size, 0) DESC, unit_size DESC` — F7 grouped canonicals outrank ungrouped/MASTER fragments + parent `consolidated_workers` beats per-store `unit_size`; **new file** `config/employer_aliases.json` with 5-entry seed: Cleveland Clinic Foundation, NYC Health and Hospitals Corporation, HCSC, Walmart Inc, Amazon.com Inc, with `exclude_terms` per entry; module-level `_load_aliases()` loader in `api/routers/employers.py` lazy-loads + caches the JSON, wired into `unified_employer_search` so query containing an alias adds `LOWER(search_name) NOT LIKE %excl%` WHERE clauses) and `cf4e24f` (Codex follow-up: harden loader against malformed JSON top-level — was catching FileNotFoundError/JSONDecodeError/OSError but would AttributeError on non-dict root or non-dict entries; now type-checks the parsed root + array + each entry; 7 fail-open scenarios verified). **Verified by direct SQL** (uvicorn zombies on :8001/:8005 prevent reliable HTTP testing): "cleveland clinic" pre-fix top hit was Cleveland Cliffs OH (sim=0.579 steel/mining); post-fix Cleveland-Cliffs filtered out and THE CLEVELAND CLINIC FOUNDATION OH (us=89,188) appears in top 5. "Cleveland-Cliffs" still findable normally on its own name. "Starbucks" query now ranks F7 grouped canonical (consolidated_workers=119) above flat MASTER per-store rows. **Limitation documented**: Walmart/Amazon flat-MASTER cases — multiple MASTER source_type rows for the same logical company, all with NULL canonical_group_id and NULL consolidated_workers, so the new tiebreak keys can't separate them; query falls through to unit_size DESC → per-store fragment with sim=1.0 still beats canonical Walmart Inc TX (us=10M, sim<1.0). Fixing this needs the heavier 4-8hr alias-name-expansion lift the audit estimated. **Codex CLI worked** despite the documented gpt-5.5 error from prior sessions — found a real bug, gave useful verifications. **New session memory**: `memory/session_2026_04_28_r7_7_search_ranking_and_alias_dict.md`. **New vault Work Log**: `Work Log/2026-04-28 - R7-7 Search Ranking and Alias Dictionary.md`. **One new file in repo**: `config/employer_aliases.json`. Pending Jacob: REG-3 postgres listen_addresses, REG-7 NLRB cron install. Tests: none run.)
>
> **Earlier 2026-04-28 LATE:** (**R7-1 Demographics ETL Deep Fix** — closed R7-1 BL-BLOCK in MERGED_ROADMAP_2026_04_25 by fixing two compounding bugs in `scripts/etl/newsrc_curate_all.py::build_acs()`: (1) `GROUP BY 1..10` collapsed across 9 IPUMS ACS sample-years (5×1yr + 4×5yr 2020-2024) inflating totals 9× — that's exactly the audit's "145M for NY" number; (2) sentinel filter mismatch — build script searched for `OCCSOC in {"","000000","0000"}` but the actual IPUMS not-in-LF sentinel is single-char `"0"`, leaking 4-5M not-in-labor-force adults per state into a phantom "all-zeros" rollup row. Fixed at curate step with `WHERE sample = '202303' AND indnaics <> '0' AND occsoc <> '0' AND classwkr <> '0'`. **DB changes**: `cur_acs_workforce_demographics` rebuilt 11,478,933 → 6,356,288 rows in 86 sec via `py scripts/etl/newsrc_curate_all.py --only acs` (drop + create + 3 indexes). No MV refresh needed (no downstream MVs depend). **Validated against BLS QCEW 2024**: NY 11,863,969 vs QCEW 9,705,821 (ratio 1.22 = expected gap from self-employed + uncovered workers); CA/TX/FL/IL all in 1.22-1.28 band. NY 65+ age share 55.8% → 10.2% (matches BLS workforce); NY 6111 education 7.0M → 874K (matches K-12 + higher-ed reality). Insurance rates ≤0.1pp drift (ratios cancel multiplicative bias). **Files modified**: `scripts/etl/newsrc_curate_all.py` (build_acs filter), `api/routers/demographics.py` (`_build_demographics` simplified — reverted morning's grain-filter workaround now unnecessary), `api/routers/profile.py` (`_get_acs_demographics` simplified), `scripts/research/tools.py` (`search_acs_workforce` simplified), `tests/test_demographics_wiring.py` (TestPlausibilityBounds tightened with QCEW-anchored bounds [0.8, 1.5] + new test_age_distribution_is_workforce_shaped). 67/67 tests pass. **New session memory**: `memory/session_2026_04_28_r7_1_demographics_etl_fix.md`. **New vault Work Log entry**: `Work Log/2026-04-28 - R7-1 Demographics ETL Deep Fix.md`. **Vault Open Problem** `Demographics ACS Total Workers Inconsistent Across Grains.md` — created mid-session, marked resolved with full diagnosis preserved as documentation. Codex CLI still broken (gpt-5.5 model error per prior 4 sessions) — no crosscheck. Backlog: `scripts/etl/newsrc_build_acs_profiles.py:185` still has the broken sentinel filter; non-blocking since curate-step filter catches the same rows now. No git commits.) (Earlier 2026-04-28 NIGHT: **Enigma API enrichment pilot** — evaluated whether Enigma's GraphQL business-data API can fill firmographic gaps on private state contractors absent from Mergent/SEC. Sample: 50 Tier A `state_local_contracts_master_matches` masters in NY/VA/OH (pool=4,171). **84% hit rate (42/50)** with strong firmographic fill (82% NAICS, 84% address, 80% website, 78% legal-entity-type). Card-transaction revenue is industry-biased noise: coherent for consumer-payment biz (Rumpke $138M, plausible) but useless for B2B (Colonial Scientific $45K, real ~$10-50M); treat as binary tag, not revenue signal. Affiliated-brands signal dead at 2% — keep using Mergent+SEC Ex21+CorpWatch+GLEIF for parent/sub. Schema lesson: search by `BRAND` not `OPERATING_LOCATION` (Rumpke/OST/Optimal Solutions all 0→matches when switched). Coverage gap: 8/8 misses were Virginia (NY+OH 0 misses) — name normalization or VA gap, not diagnosed. Plugin detour: Enigma's `/plugin marketplace add ...` repo is skill-only (4 markdown prompts, no MCP server) and `/plugin` is unavailable in Claude Code 2.1.113 / Agent SDK — skipped, raw GraphQL script does the same job. **1 new code file**: `scripts/etl/enigma_pilot/enrich_thin_contractors.py` (~430 lines, untracked, pilot-only) — reads `Enigma API Key` from `.env` (literal name has spaces, parsed manually like `IPUMS API Key`), POSTs GraphQL `search` BRAND queries to `https://api.enigma.com/graphql`, parses Brand-shaped responses, writes JSONL+CSV to `scripts/etl/enigma_pilot/output/` (also untracked, raw API responses). **1 vault Work Log entry**: `Work Log/2026-04-28 - Enigma API Pilot 50 Thin-Data State Contractors.md`. **1 session memory**: `memory/session_2026_04_28_enigma_pilot.md`. DB changes: none. MV refresh: none. Tests: none. Git commits: none. Account state after pilot: `pricingPlan: TRIAL`, `creditsAvailable: true` (~150-300 of 600 trial credits estimated burned; no API for exact balance). Codex CLI still broken (gpt-5.5 model error per prior sessions) — no crosscheck this session. For 3,000-seed pilot scaling: ~15,000 credits = ~$750 retail; firmographic-only; skip card revenue; skip affiliated brands.) (Earlier 2026-04-28 EVENING: **IPUMS double-track session**: ACS insurance columns + CPS ORG microdata acquired. **3 new code files** in `scripts/etl/`: `cps_pull_org_extract.py` (228 lines, IPUMS REST API submit/poll/download), `cps_load_org.py` (149 lines, DDI XML parser + fixed-width loader), `cps_curate_density.py` (~270 lines, 8 GROUPING SETS aggregations into `cur_cps_density_*` tables). **1 modified code file**: `scripts/etl/newsrc_build_acs_profiles.py` — added `--spill-keys` mode (chunked disk-spill aggregator for memory-constrained re-runs) + `maintenance_work_mem` cap fix. **3 vault notes**: new `Data Sources/BLS Labor Statistics/CPS ORG Microdata.md`; `Data Sources/Census and Demographics/ACS Workforce Demographics.md` updated with 6 new insurance columns; `Data Sources/Not Yet Acquired/CPS Microdata.md` converted to redirect stub. **2 Work Log entries**: `Work Log/2026-04-28 - ACS Insurance Columns Backfilled.md`, `Work Log/2026-04-28 - CPS ORG Microdata Acquired.md`. **1 session memory**: `memory/session_2026_04_28_ipums_acs_cps.md`. DB changes: 8 new tables (`cps_org_raw` + 7 `cur_cps_density_*`); `newsrc_acs_occ_demo_profiles` rebuilt with 6 insurance cols carried into `cur_acs_workforce_demographics`; `data_refresh_log` rows 4-14 inserted. Validation: national 2024 union rate CPS=9.98% vs BLS=9.9% (exact); 51-state mean delta vs `bls_state_density` 0.90pp; sub-state spot checks match real-world unions. Codex CLI still broken (gpt-5.5 error) — no crosscheck this session. No git commits, no MV refresh, no test run.) (Earlier 2026-04-28 AFTERNOON: 24 Questions Framework adoption — pure documentation session, no code changes. **Three new vault documents:** `Decisions/2026-04-28 - Adopt 24 Questions Corporate Research Framework.md` (adoption rationale, scope, alternatives), `Systems/24 Questions Framework.md` (canonical reference: 24 questions + 3 organizational levels + 4 Sources of Power + 5 deliverable artifacts + coverage scorecard 8 strong / 6 medium / 5 weak / 5 missing), and `ROADMAP_24Q_ADDENDUM_2026_04_28.md` (every existing roadmap item mapped to question(s) it answers + 46 new items 24Q-1 through 24Q-46 in P0/P1/P2 bands, sequenced post-beta). **Vault CLAUDE.md modified:** new "Organizing Principle" section after Critical Rules + Related wikilinks updated to all three new docs + active-roadmap link corrected from obsolete `MERGED_ROADMAP_2026_04_07` to `MERGED_ROADMAP_2026_04_25` + frontmatter date 2026-04-28. **New session summary:** `memory/session_2026_04_28_24q_framework.md`. **New vault Work Log entry:** `Work Log/2026-04-28 - 24 Questions Framework Adoption.md`. **Auto-memory:** `project_24q_framework_adopted.md` + MEMORY.md pointer. No DB changes, no MV refresh, no tests run, no code edits, no git commits.) (Earlier 2026-04-27: R7 audit cleanup — Tracks A/B'/D/E/G/H, 21 items closed across 6 commits. **One new file added to repo:** `frontend/__tests__/ComparablesCard.test.jsx` (5 vitest tests locking the `comparable_type` API contract for R7-13). All other changes were edits to existing files. New session summary: `memory/session_2026_04_27_r7_audit_tracks_a_through_h.md`. New vault Work Log entry: `Work Log/2026-04-27 - R7 Audit Tracks A-H 21 items closed.md`. Vault `.claude/skills/ship/SKILL.md` got a new step 4 "Deploy hygiene check (M-1)". No DOCUMENT_INDEX category-level structural changes.)
>
> **Last rebuilt:** 2026-04-23 EVENING (Starbucks flagship dossier + corporate-family rollup end-to-end. **New files in `scripts/managed_agents/`**: `build_starbucks_supplement.py` (270+ line aggregator that ILIKE-matches across participant_name/estab_name/legal_name for 380 Starbucks-named masters, writes `_starbucks_national_supplement` block into an existing per-employer JSON export; extensible pattern for other large employers), `run_log_v4.json` (slot 39 metadata with headline findings + identity caveat + queries_tried summary), `dossiers/39_starbucks_corporation_national.md` (**10,266-word flagship dossier**, 11/11 sections, 301 `[S#]` citations, 60 distinct sources, 19 WebSearch calls of 20 budget, 48 specific NLRB case numbers cited; ingested as research_runs id=231 with is_gold_standard=TRUE). **New backend service**: `api/services/corporate_family_rollup.py` (260+ lines; canonical-stem extraction + aggregated DB queries for NLRB/OSHA/WHD/F-7 across all name-variant siblings of a master_id). **New backend test**: `tests/test_corporate_family_rollup.py` (28 DB-free unit tests locking down the stem extractor, all pass in 0.27s, regression guard on 13 Starbucks respondent-name variants). **New frontend component**: `frontend/src/features/employer-profile/FamilyRollupSection.jsx` (320 lines, renders banner + 4 stat tiles + elections-by-year + elections-by-state + allegation chips + recent elections table + respondent-name-variants table + WHD summary; self-gates on `master_count > 5 OR nlrb_cases > 20`). **New API endpoint**: `GET /api/employers/master/{master_id}/family-rollup?limit_recent_elections=N` added to `api/routers/employers.py` with function-local import + `log.exception` + generic 500 error (fixed a Codex-flagged exception-text leak). **New frontend hook**: `useEmployerFamilyRollup` in `frontend/src/shared/api/profile.js` (TanStack Query, 10-min staleTime). **Edited**: `frontend/src/features/employer-profile/EmployerProfilePage.jsx` (wired `FamilyRollupSection` into the `isMaster && data` early-return branch above `BasicProfileView` after Codex caught that the original F-7-branch wire-in was unreachable for master profiles), `scripts/managed_agents/ingest_dossiers.py` (added `run_log_v4.json` to RUN_LOG_FILES). **DB changes**: `research_runs` 230 -> 231 (+1 Starbucks ingestion). **Verified live on port 8002**: Starbucks family_stem=starbucks, master_count=380, 2,351 NLRB cases, 791 elections (669 wins = 84.6% win rate), 234 F-7 locals in 44 states, 139 OSHA establishments in 31 states. Lowe's master 6978389 verified (family_stem=`lowes home`, 211 masters). Codex crosscheck on session diff: 1 HIGH + 2 MEDIUM — all session-scope issues fixed; 1 pre-existing `union_name` field drift in comparables card flagged for backlog. Windows port 8001 orphan-socket issue blocked auto-reload; UI needs user-side server restart (documented). **New session summary at `memory/session_2026_04_23_starbucks_and_family_rollup.md`** + vault `Work Log/2026-04-23 - Starbucks Flagship Dossier and Corporate Family Rollup.md`. No git commits.) (Earlier 2026-04-23 AFTERNOON: P2 #82 rebuild — added missing **Section 6.5 Scripts (Code-side)** for `scripts/managed_agents/` (8 files), `scripts/llm_dedup/` (28 files), `scripts/scraper/` (16 files), `scripts/etl/contracts/` (15 files), and 6 new `scripts/etl/scrape_*.py` directory scrapers. Updated **Section 4 Specs** (+`union-website-cms-fingerprints.md`), **Section 5 Skills** (codebase 7 → vault 22 split), **Section 8 Systems** (+`Agent and Skill Infrastructure.md`), **Section 9 Decisions** (+D16), **Section 10 Research** (+5 notes incl. State/Municipal Contracts Scouting Report, EEO-1 HQ Rollup, Gold Standard Targets), **Section 12 Work Log** (+30 entries through 2026-04-22), **Section 11 Open Problems** (marked closed: D12/D13, Gower pipeline, SEC XBRL dates, Vite proxy, Stability pillar, Docker JWT, Weak DB password). For session-by-session history see vault `Work Log/` entries; for current platform state see `Start each AI/PROJECT_STATE.md`.)
>
> **Codebase:** `C:\Users\jakew\.local\bin\Labor Data Project_real\`
> **Vault:** `C:\Users\jakew\LaborDataTerminal\LaborDataTerminal_real\`
> **Status key:** **ACTIVE** (in use) | **REFERENCE** (useful background) | **ARCHIVE** (superseded)

---

## 1. Root Documents

| File | Status | Description |
|------|--------|-------------|
| `CLAUDE.md` | ACTIVE | Constitution -- auto-loaded every session. Technical conventions, gotchas, agent triggers. |
| `MEMORY.md` | ACTIVE | Session memory index with pointers to topic-specific memory files. |
| `README.md` | ACTIVE | Project overview (v7.1, Phase 5 complete). |
| `DOCUMENT_INDEX.md` | ACTIVE | This file -- master catalog of all project documentation. |
| `PROJECT_CATALOG.md` | ACTIVE | Comprehensive file catalog (~755 code/config files + ~229 docs). |
| `PIPELINE_MANIFEST.md` | REFERENCE | Script inventory with run order (superseded by PROJECT_CATALOG). |
| `PLATFORM_HELP_COPY.md` | ACTIVE | UI help text for all frontend pages. |
| `Platform_Data_Sources.md` | REFERENCE | Data source inventory and brainstorming prompt (verify counts against DB). |
| `FRONTEND_REDESIGN_INSTRUCTIONS.md` | ACTIVE | Aged Broadsheet design reference for frontend styling. |
| `CBA_DATABASE_BUILD_PLAN.md` | ACTIVE | CBA pipeline design: extraction, categorization, and research system. |
| `CBA_PROVISION_TAXONOMY.md` | ACTIVE | 14-category taxonomy for automated CBA contract extraction. |
| `CODEX_INVESTIGATION_REPORT_2026_03.md` | REFERENCE | Codex investigation report (Mar 2026): scoring, security, documentation drift. |
| `ROUND_6_FULL_SYSTEM_AUDIT_PROMPT.md` | ACTIVE | Round 6 audit prompt: 10 Focus Areas, AI-agnostic, triple-pass confidence. |
| `ROUND_5_AUDIT_PROMPT.md` | ARCHIVE | Superseded by Round 6 audit prompt. |
| `COMPREHENSIVE_PROJECT_AUDIT_2026_03_13.md` | REFERENCE | 7-agent audit with 71 verification markers, live DB stats. |
| `COMPREHENSIVE_PROJECT_AUDIT_2026_03_12.md` | REFERENCE | Earlier draft of comprehensive audit (1,370 lines). |
| `CONSOLIDATED_ROADMAP_2026_03_13.md` | REFERENCE | Technical roadmap with verification steps (prioritization superseded by vault MERGED_ROADMAP). |
| `STRATEGIC_LAUNCH_ROADMAP.md` | REFERENCE | 3-tier launch roadmap (Mar 24) -- superseded by vault MERGED_ROADMAP_2026_04_07. |
| `TWO_MONTH_SCHEDULE_2026_03_11.md` | ARCHIVE | Two-month schedule estimate. |
| `deep-research-report.md` | REFERENCE | Foundational deep research: estimating workforce size and composition. |
| `deep-research-report_RPE.md` | REFERENCE | Revenue-per-employee specific deep research. |
| `V10_CLAUDE_CODE_PROMPT.md` | REFERENCE | V10 demographics implementation spec (6 phases, acceptance criteria). |
| `audit_findings.md` | REFERENCE | Collected audit findings. |

### Start each AI/ (shared context for all AI tools)

| File | Status | Description |
|------|--------|-------------|
| `Start each AI/PROJECT_STATE.md` | ACTIVE | Shared project context for Claude Code, Codex, Gemini. Current status and active decisions. |
| `Start each AI/CLAUDE.md` | ACTIVE | Claude Code-specific project context (loaded at session start). |
| `Start each AI/UNIFIED_PLATFORM_REDESIGN_SPEC.md` | REFERENCE | Complete platform redesign spec (Feb 2026, Phase 5). Core decisions still apply. |
| `Start each AI/CODEX_TASKS_2026_03_05.md` | REFERENCE | Codex task assignments from Mar 5. |

---

## 2. Architecture & Design

### docs/architecture/

| File | Status | Description |
|------|--------|-------------|
| `sql/schema/cba_pgvector_migration.sql` | ACTIVE | pgvector extension, halfvec(3072) column, HNSW index on cba_embeddings, provision embedding support. |
| `docs/architecture/MASTER_EMPLOYER_SCHEMA.md` | REFERENCE | Schema documentation for master_employers table and related tables. |
| `docs/architecture/MATCHING_PIPELINE_ARCHITECTURE.md` | REFERENCE | Matching pipeline architecture documentation. |
| `docs/architecture/NLRB_Propensity_Model_Design.md` | REFERENCE | NLRB propensity model design document. |
| `docs/architecture/PHASE4_ARCHITECTURE_REVIEW.md` | REFERENCE | Phase 4 architecture review. |
| `docs/architecture/PUBLIC_SECTOR_SCHEMA_DOCS.md` | REFERENCE | Public sector schema documentation. |
| `docs/architecture/SCORING_INTEGRATION_DESIGN.md` | REFERENCE | Scoring integration design. |
| `docs/architecture/SCORING_SYSTEM_ARCHITECTURE.md` | REFERENCE | Scoring system architecture documentation. |

### docs/ (top-level)

| File | Status | Description |
|------|--------|-------------|
| `docs/README.md` | REFERENCE | Documentation folder overview. |
| `docs/DATA_QUALITY_FRAMEWORK.md` | REFERENCE | Data quality and confidence framework (Feb 2026). |
| `docs/DEMOGRAPHICS_ESTIMATION_SUMMARY.md` | REFERENCE | Demographics estimation methodology summary. |
| `docs/DEMOGRAPHICS_METHODOLOGY_COMPARISON.md` | REFERENCE | Initial 200-company demographics comparison (6 methods, superseded by V5+). |
| `docs/DEPENDENCY_REVIEW.md` | REFERENCE | Dependency and environment review. |
| `docs/MV_UNIFIED_SCORECARD_GUIDE.md` | ACTIVE | Complete reference guide for mv_unified_scorecard materialized view. |
| `docs/PLATFORM_STATUS.md` | ACTIVE | Auto-generated platform status summary. |
| `docs/PROJECT_METRICS.md` | ACTIVE | Auto-generated DB stats, MV freshness, score distribution. |
| `docs/RESEARCH_AGENT_ARCHITECTURE.md` | ACTIVE | Research agent architecture: 24-tool async-parallel orchestration loop. |
| `docs/RESEARCH_AGENT_REFERENCE.md` | ACTIVE | Research agent comprehensive reference: 24 tools, async core, leverage signals. |
| `docs/UNION_WEB_SCRAPER.md` | ACTIVE | Consolidated scraper docs (pipeline, schema, extraction, expansion). |
| `docs/db_inventory_latest.md` | REFERENCE | Latest database inventory snapshot. |
| `docs/rpe_methodology_summary.md` | REFERENCE | Revenue-per-employee methodology summary. |

### docs/plans/

| File | Status | Description |
|------|--------|-------------|
| `docs/plans/CHECKPOINT_PARALLEL_CODEX_PHASE1_2026-02-15.md` | ARCHIVE | Phase 1 Codex parallel checkpoint. |
| `docs/plans/EXTENDED_ROADMAP.md` | ARCHIVE | Extended roadmap (superseded). |
| `docs/plans/LABOR_PLATFORM_ROADMAP_v10.md` | ARCHIVE | Roadmap v10 (superseded). |
| `docs/plans/LABOR_PLATFORM_ROADMAP_v12.md` | ARCHIVE | Roadmap v12 (superseded). |
| `docs/plans/MERGENT_SCORECARD_PIPELINE.md` | REFERENCE | Mergent scorecard pipeline plan. |
| `docs/plans/MULTI_AI_TASK_PLAN.md` | ARCHIVE | Multi-AI task coordination plan. |
| `docs/plans/PHASE5_EXECUTION_PLAN.md` | ARCHIVE | Phase 5 execution plan (completed). |
| `docs/plans/PROJECT_4_DEEP_DIVE_RESEARCH.md` | REFERENCE | Project 4 deep dive research plan. |
| `docs/plans/WAVE2_CODEX_PROMPT.md` | ARCHIVE | Wave 2 Codex prompt. |

### docs/data-sources/

| File | Status | Description |
|------|--------|-------------|
| `docs/data-sources/ACS_PUMS_FEASIBILITY_RESEARCH.md` | REFERENCE | ACS PUMS feasibility research. |
| `docs/data-sources/BLS_CPS_DENSITY_RESEARCH.md` | REFERENCE | BLS CPS union density research. |
| `docs/data-sources/BLS_OEWS_DATA_RESEARCH.md` | REFERENCE | BLS OES wage data research. |
| `docs/data-sources/CALIBRATION_ENGINE_FEASIBILITY.md` | REFERENCE | Demographics calibration engine feasibility. |
| `docs/data-sources/CORPORATE_HIERARCHY_RESEARCH.md` | REFERENCE | Corporate hierarchy research (CorpWatch, SEC, etc.). |
| `docs/data-sources/CORPWATCH_IMPORT_PLAN.md` | REFERENCE | CorpWatch import plan. |
| `docs/data-sources/COSINE_SIMILARITY_RESEARCH.md` | REFERENCE | Cosine similarity research for matching. |
| `docs/data-sources/DATABASE_SOURCES_REFERENCE.md` | REFERENCE | Database sources reference listing. |
| `docs/data-sources/EDGARTOOLS_EVALUATION.md` | REFERENCE | edgartools library evaluation for SEC data. |
| `docs/data-sources/EPI_BENCHMARK_METHODOLOGY.md` | REFERENCE | EPI union density benchmark methodology. |
| `docs/data-sources/EXHIBIT_21_PARSING_RESEARCH.md` | REFERENCE | LLM-based SEC Exhibit 21 subsidiary extraction. |
| `docs/data-sources/FORM_990_FINAL_RESULTS.md` | REFERENCE | Form 990 integration final results. |
| `docs/data-sources/HUMAN_CAPITAL_DISCLOSURE_RESEARCH.md` | REFERENCE | SEC human capital disclosure research. |
| `docs/data-sources/IRS_BMF_ETL_COMPLETION.md` | REFERENCE | IRS BMF ETL completion report. |
| `docs/data-sources/IRS_BMF_RESEARCH.md` | REFERENCE | IRS Business Master File research. |
| `docs/data-sources/NEW_SOURCES_INGESTION_CONTEXT_2026-02-28.md` | REFERENCE | New data sources ingestion context. |
| `docs/data-sources/ONET_INTEGRATION_RESEARCH.md` | REFERENCE | O*NET integration research. |
| `docs/data-sources/ORPHAN_MAP_2026.md` | REFERENCE | Orphan data mapping (2026). |
| `docs/data-sources/REVENUE_PER_EMPLOYEE_RESEARCH.md` | REFERENCE | Revenue per employee research. |
| `docs/data-sources/SEC_EDGAR_RESEARCH.md` | REFERENCE | Phase 4 Block A bulk submissions strategy. |
| `docs/data-sources/SEC_ETL_COMPLETION.md` | REFERENCE | SEC metadata ETL completion report (Feb 2026). |
| `docs/data-sources/STATE_PERB_RESEARCH.md` | REFERENCE | State PERB data research. |
| `docs/data-sources/STATE_PERB_RESEARCH_PART1.md` | REFERENCE | State PERB data research (Part 1). |
| `docs/data-sources/TEAMSTERS_COMPARISON_REPORT.md` | REFERENCE | Teamsters data comparison report. |

### docs/frontend/

| File | Status | Description |
|------|--------|-------------|
| `docs/frontend/FRONTEND_CATALOG.md` | REFERENCE | Frontend component catalog. |
| `docs/frontend/FRONTEND_CODE_REVIEW.md` | REFERENCE | Frontend code review. |
| `docs/frontend/MATCHING_CODE_REVIEW.md` | REFERENCE | Matching-related frontend code review. |
| `docs/frontend/PHASE4_CODE_REVIEW.md` | REFERENCE | Phase 4 frontend code review. |
| `docs/frontend/PHASE5_DETAILED_PLAN.md` | ARCHIVE | Phase 5 detailed plan (completed). |
| `docs/frontend/PROJECT_5_FRONTEND_RESEARCH.md` | REFERENCE | Project 5 frontend research. |

### docs/analysis/

| File | Status | Description |
|------|--------|-------------|
| `docs/analysis/AFSCME_NY_CASE_STUDY.md` | REFERENCE | AFSCME NY case study. |
| `docs/analysis/HISTORICAL_EMPLOYER_ANALYSIS.md` | REFERENCE | Historical employer analysis. |
| `docs/analysis/MATCH_QUALITY_REPORT.md` | REFERENCE | Match quality report. |
| `docs/analysis/MATCH_QUALITY_SAMPLE_2026.md` | REFERENCE | Match quality sample analysis (2026). |
| `docs/analysis/METHODOLOGY_SUMMARY_v8.md` | REFERENCE | Methodology summary v8. |
| `docs/analysis/MISSING_UNIONS_ANALYSIS.md` | REFERENCE | Missing unions analysis. |
| `docs/analysis/NLRB_ULP_MATCHING_GAP.md` | REFERENCE | NLRB ULP matching gap analysis. |
| `docs/analysis/NY_DENSITY_MAP_METHODOLOGY.md` | REFERENCE | NY density map methodology. |
| `docs/analysis/NY_EXPORT_METHODOLOGY.md` | REFERENCE | NY export methodology. |
| `docs/analysis/SCORECARD_SHRINKAGE_INVESTIGATION.md` | REFERENCE | Scorecard shrinkage investigation. |

### docs/investigations/

| File | Status | Description |
|------|--------|-------------|
| `docs/investigations/API_PERFORMANCE_AUDIT.md` | REFERENCE | API performance audit. |
| `docs/investigations/I1_nlrb_proximity_junk_data.md` | REFERENCE | I1: NLRB proximity junk data investigation. |
| `docs/investigations/I2_similarity_pipeline_coverage.md` | REFERENCE | I2: Similarity pipeline coverage. |
| `docs/investigations/I3_dangling_uml_missing_f7_targets.md` | REFERENCE | I3: Dangling UML / missing F7 targets. |
| `docs/investigations/I4_junk_placeholder_counts.md` | REFERENCE | I4: Junk placeholder counts. |
| `docs/investigations/I5_name_similarity_floor_validation.md` | REFERENCE | I5: Name similarity floor validation. |
| `docs/investigations/I6_membership_view.md` | REFERENCE | I6: Membership view investigation. |
| `docs/investigations/I7_orphaned_superseded.md` | REFERENCE | I7: Orphaned/superseded records. |
| `docs/investigations/I8_employer_grouping.md` | REFERENCE | I8: Employer grouping investigation. |
| `docs/investigations/I8_employer_grouping_quality.md` | REFERENCE | I8: Employer grouping quality. |
| `docs/investigations/I9_naics_inference.md` | REFERENCE | I9: NAICS inference investigation. |
| `docs/investigations/I10_multi_employer_agreements.md` | REFERENCE | I10: Multi-employer agreements. |
| `docs/investigations/I11_geocoding_gap_by_tier.md` | REFERENCE | I11: Geocoding gap by tier. |
| `docs/investigations/I11_priority_composition.md` | REFERENCE | I11: Priority composition. |
| `docs/investigations/I11_trigram_quality_audit.md` | REFERENCE | I11: Trigram quality audit. |
| `docs/investigations/I12_duplicate_match_audit.md` | REFERENCE | I12: Duplicate match audit. |
| `docs/investigations/I12_geographic_enforcement_bias.md` | REFERENCE | I12: Geographic enforcement bias. |
| `docs/investigations/I12_propensity_model_verification.md` | REFERENCE | I12: Propensity model verification. |
| `docs/investigations/I13_match_coverage_gaps.md` | REFERENCE | I13: Match coverage gaps. |
| `docs/investigations/I13_misclassification_edge_cases.md` | REFERENCE | I13: Misclassification edge cases. |
| `docs/investigations/I14_geographic_gaps.md` | REFERENCE | I14: Geographic gaps. |
| `docs/investigations/I14_legacy_poisoned_matches.md` | REFERENCE | I14: Legacy poisoned matches. |
| `docs/investigations/I14_sam_matching_quality.md` | REFERENCE | I14: SAM matching quality. |
| `docs/investigations/I15_missing_source_id_linkages.md` | REFERENCE | I15: Missing source ID linkages. |
| `docs/investigations/I15_whd_matching_quality.md` | REFERENCE | I15: WHD matching quality. |
| `docs/investigations/I16_990_matching_quality.md` | REFERENCE | I16: Form 990 matching quality. |
| `docs/investigations/I17_score_distribution_phase1.md` | REFERENCE | I17: Score distribution (Phase 1). |
| `docs/investigations/I17_state_coverage_heatmap.md` | REFERENCE | I17: State coverage heatmap. |
| `docs/investigations/I18_active_unions.md` | REFERENCE | I18: Active unions investigation. |
| `docs/investigations/I19_mel_ro_spot_check.md` | REFERENCE | I19: MEL/RO spot check. |
| `docs/investigations/I20_corporate_hierarchy_coverage.md` | REFERENCE | I20: Corporate hierarchy coverage. |
| `docs/investigations/PHASE_1B_SUMMARY.md` | REFERENCE | Phase 1B investigation summary. |
| `docs/investigations/TEST_COVERAGE_GAPS.md` | REFERENCE | Test coverage gaps. |
| `docs/investigations/VERIFICATION_PASS.md` | REFERENCE | Verification pass results. |

### docs/audits/

| File | Status | Description |
|------|--------|-------------|
| `docs/audits/AUDIT_REPORT_2026.md` | ARCHIVE | 2026 audit report. |
| `docs/audits/AUDIT_REPORT_CLAUDE_2026_R3.md` | ARCHIVE | Round 3 Claude audit. |
| `docs/audits/AUDIT_REPORT_CLAUDE_2026_R4.md` | ARCHIVE | Round 4 Claude audit. |
| `docs/audits/AUDIT_REPORT_CODEX_2026_R3.md` | ARCHIVE | Round 3 Codex audit. |
| `docs/audits/AUDIT_REPORT_CODEX_2026_R4.md` | ARCHIVE | Round 4 Codex audit. |
| `docs/audits/AUDIT_REPORT_CODEX_2026_R4_FINAL.md` | ARCHIVE | Round 4 Codex audit (final). |
| `docs/audits/AUDIT_REPORT_CODEX_2026_R4_WORKING.md` | ARCHIVE | Round 4 Codex audit (working draft). |
| `docs/audits/AUDIT_REPORT_GEMINI_2026_R3.md` | ARCHIVE | Round 3 Gemini audit. |
| `docs/audits/AUDIT_REPORT_GEMINI_2026_R4.md` | ARCHIVE | Round 4 Gemini audit. |
| `docs/audits/AUDIT_REPORT_ROUND2_CLAUDE.md` | ARCHIVE | Round 2 Claude audit. |
| `docs/audits/AUDIT_REPORT_ROUND2_CODEX.md` | ARCHIVE | Round 2 Codex audit. |
| `docs/audits/API_SECURITY_FIXES.md` | REFERENCE | API security fixes documentation. |
| `docs/audits/CI_CHECK_REPORT.md` | REFERENCE | CI check report. |
| `docs/audits/CREDENTIAL_SCAN_2026.md` | REFERENCE | Credential scan results (2026). |
| `docs/audits/FOCUSED_AUDIT_CLAUDE_DATABASE.md` | ARCHIVE | Focused Claude database audit. |
| `docs/audits/FULL_AUDIT_PROMPT_2026.md` | ARCHIVE | 2026 full audit prompt. |
| `docs/audits/JS_INNERHTML_SAFETY_CHECK.md` | REFERENCE | JavaScript innerHTML safety check. |
| `docs/audits/OLMS_ANNUAL_REPORT_CATALOG.md` | REFERENCE | OLMS annual report catalog. |
| `docs/audits/PARALLEL_DB_CONFIG_MIGRATION_REPORT.md` | REFERENCE | Parallel DB config migration report. |
| `docs/audits/PARALLEL_FRONTEND_API_AUDIT.md` | REFERENCE | Parallel frontend API audit. |
| `docs/audits/PARALLEL_INNERHTML_API_RISK_PRIORITY.md` | REFERENCE | innerHTML API risk priority. |
| `docs/audits/PARALLEL_PASSWORD_AUTOFIX_REPORT.md` | REFERENCE | Password autofix report. |
| `docs/audits/PARALLEL_PHASE1_PASSWORD_AUDIT.md` | REFERENCE | Phase 1 password audit. |
| `docs/audits/PARALLEL_PR_BUNDLE_PLAN.md` | REFERENCE | PR bundle plan. |
| `docs/audits/PARALLEL_QUERY_PLAN_BASELINE.md` | REFERENCE | Query plan baseline. |
| `docs/audits/PARALLEL_ROUTER_DOCS_DRIFT.md` | REFERENCE | Router documentation drift report. |
| `docs/audits/PERFORMANCE_PROFILE.md` | REFERENCE | Performance profiling results. |
| `docs/audits/PROJECT_METRICS.md` | REFERENCE | Audit-generated project metrics. |
| `docs/audits/TEST_COVERAGE_REVIEW.md` | REFERENCE | Test coverage review. |
| `docs/audits/review_codex.md` | ARCHIVE | Codex review notes. |
| `docs/audits/review_gemini.md` | ARCHIVE | Gemini review notes. |
| `docs/audits/round3/r2_dynamic_sql_risk_inventory.md` | REFERENCE | Round 3 dynamic SQL risk inventory. |

### docs/prompts/

| File | Status | Description |
|------|--------|-------------|
| `docs/prompts/CODEX_PARALLEL_TASKS_2026_02_18.md` | ARCHIVE | Codex parallel tasks prompt. |
| `docs/prompts/PROMPT_FOR_CLAUDE_ALL_WORK_2026-02-15.md` | ARCHIVE | Claude all-work prompt (Feb 15). |
| `docs/prompts/PR_STAGING_CHUNKS_2026-02-15.md` | ARCHIVE | PR staging chunks prompt. |
| `docs/prompts/RELEASE_GATE_SUMMARY.md` | ARCHIVE | Release gate summary. |
| `docs/prompts/WAVE2_GEMINI_PROMPT.md` | ARCHIVE | Wave 2 Gemini prompt. |

### docs/reviews/

| File | Status | Description |
|------|--------|-------------|
| `docs/reviews/deterministic_matching_pipeline_review_2026-02-17.md` | REFERENCE | Deterministic matching pipeline review. |
| `docs/reviews/phase-b-matching-tests-splink-review-2026-02-17.md` | REFERENCE | Phase B matching tests / Splink review. |

### docs/session-logs/ and docs/session-summaries/

| Folder | Status | Description |
|--------|--------|-------------|
| `docs/session-logs/` (7 files) | ARCHIVE | Pre-vault session logs (Feb 2026). |
| `docs/session-summaries/` (28 files) | ARCHIVE | Pre-vault session summaries (Jan-Mar 2026). Superseded by vault Work Log. |

---

## 3. Agent Specs (.claude/agents/)

| File | Description |
|------|-------------|
| `.claude/agents/api.md` | FastAPI endpoints, response shapes, auth middleware, router organization. |
| `.claude/agents/cba.md` | CBA provision extraction, 14-category rule engine, article detection. |
| `.claude/agents/database.md` | PostgreSQL schema, MVs, constraints, indexes, migrations. |
| `.claude/agents/etl.md` | Data source loading, COPY patterns, seed scripts, CHECK constraints. |
| `.claude/agents/frontend.md` | React 19 frontend, Tailwind 4 theme, TanStack, Vitest. |
| `.claude/agents/maintenance.md` | MV refresh, dedup, backup, Docker, metrics. |
| `.claude/agents/matching.md` | 12-tier deterministic matching V2, RapidFuzz, in-memory trigram. |
| `.claude/agents/research.md` | Gemini research agent, dossiers, auto-grading, strategy learning. |
| `.claude/agents/scoring.md` | 10-factor scorecard, target scorecard, MVs, Gower similarity, pillars. |

---

## 4. Reference Specs (.claude/specs/)

| File | Description |
|------|-------------|
| `.claude/specs/api-endpoints.md` | API endpoint reference (209 lines). |
| `.claude/specs/audit-findings.md` | Audit findings from Feb 25-26, 2026 (130 lines). |
| `.claude/specs/corporate-crosswalk.md` | Corporate identifier crosswalk spec (103 lines). |
| `.claude/specs/data-reconciliation.md` | LM2 vs F7 data reconciliation (82 lines). |
| `.claude/specs/database-schema.md` | Database schema reference (174 lines). |
| `.claude/specs/density-methodology.md` | Union density methodology (98 lines). |
| `.claude/specs/matching-pipeline.md` | Matching pipeline architecture spec (290 lines). |
| `.claude/specs/pipeline-manifest.md` | Pipeline manifest: script inventory and run order (117 lines). |
| `.claude/specs/redesign-spec.md` | Platform redesign specification (240 lines). |
| `.claude/specs/roadmap.md` | Unified platform roadmap (218 lines). |
| `.claude/specs/scoring-system.md` | Scoring system architecture spec (308 lines). |
| `.claude/specs/unified-scorecard-guide.md` | Unified scorecard MV guide (158 lines). |
| `.claude/specs/union-website-cms-fingerprints.md` | 6 CMS families (UnionActive-IIS, WP REST, Elementor, Drupal Views, iframe-app, static-HTML) with detection + bypass strategies. (added 2026-04-21) |

---

## 5. Skills

The codebase ships **7 code-side skills** in `.claude/skills/`. The vault carries the full **22-skill** set (a superset including session-management, knowledge-management, data-source, experiment, and cross-agent-handoff skills). See `Systems/Agent and Skill Infrastructure.md` for the full taxonomy.

### Codebase skills (`.claude/skills/`)

| Skill | Description |
|-------|-------------|
| `.claude/skills/debug/SKILL.md` | Debug data issues step by step (join keys, sample rows, nulls). |
| `.claude/skills/rebuild-mvs/SKILL.md` | Rebuild all materialized views in dependency order. |
| `.claude/skills/schema-check/SKILL.md` | Introspect database schema before writing queries. |
| `.claude/skills/ship/SKILL.md` | Run tests, commit, push, update MEMORY.md/PROJECT_STATE.md. |
| `.claude/skills/start/SKILL.md` | Start work session: read state, start servers, report status. |
| `.claude/skills/union-research/SKILL.md` | Independent web research for discovering new unions and organizing campaigns. |
| `.claude/skills/wrapup/SKILL.md` | End-of-session: session summary, update PROJECT_STATE.md, MEMORY.md, DOCUMENT_INDEX.md. |

### Vault skills (`<vault>/.claude/skills/`) — superset of 22

Session management: `start`, `wrapup`, `ship`. Database/infra: `schema-check`, `rebuild-mvs`, `pipeline-status`, `debug`. Knowledge: `decision-log`, `audit-finding`, `resolve-problem`, `roadmap-update`, `context-load`, `compare-docs`, `research-capture`, `prompt-archive`. Data source: `verify-data-source`, `source-evaluation`. Experiment: `demographics-experiment`, `matching-report`. Handoffs: `codex-handoff`, `gemini-handoff`, `union-research`.

### union-research references (`.claude/skills/union-research/references/`)

| File | Description |
|------|-------------|
| `employer-research.md` | Employer research reference data. |
| `federal-sector.md` | Federal sector union reference. |
| `industry-research.md` | Industry research reference. |
| `news-sources.md` | Labor news sources. |
| `nlrb-research.md` | NLRB research reference. |
| `public-sector-sources.md` | Public sector data sources. |
| `verification-queries.md` | Verification SQL queries. |
| `worker-centers.md` | Worker center reference data. |

---

## 6. Demographics Model (scripts/analysis/demographics_comparison/)

| File | Status | Description |
|------|--------|-------------|
| `V5_COMPLETE_RESULTS.md` | REFERENCE | V5: 30 methods, 997 training + 208 holdout, Gate v1 pipeline. |
| `V5_FINAL_REPORT.md` | REFERENCE | V5 final validation summary (acceptance criteria). |
| `V5_PROPOSAL.md` | ARCHIVE | V5 proposal. |
| `V5_REVISION_PLAN.md` | ARCHIVE | V5 revision plan. |
| `Version 5 revision suggestions_codex.md` | ARCHIVE | Codex revision suggestions for V5. |
| `V6_ABLATION_REPORT.md` | REFERENCE | V6 ablation study report. |
| `V6_FINAL_REPORT.md` | REFERENCE | V6 final report. |
| `V6_RUN1_CHECKPOINT.md` | ARCHIVE | V6 Run 1 checkpoint. |
| `V6_RUN2_CHECKPOINT.md` | ARCHIVE | V6 Run 2 checkpoint. |
| `V7_ERROR_DISTRIBUTION.md` | REFERENCE | V7 error distribution analysis. |
| `V7_RECOMMENDATIONS.md` | REFERENCE | V7 recommendations. |
| `V8_FULL_SUMMARY.md` | REFERENCE | V8 full summary. |
| `V8.5_ARCHITECTURE_ANALYSIS.md` | REFERENCE | V8.5 architecture analysis. |
| `V9_1_METHODOLOGY_AND_RESULTS.md` | REFERENCE | V9.1 full methodology, results, tail analysis. |
| `V9_2_FULL_REPORT.md` | REFERENCE | V9.2 full report. |
| `V9_BEST_OF_IPF_RESULTS.md` | ARCHIVE | V9 Best-of-IPF results. |
| `V9_TWO_MODEL_PROPOSAL.md` | ARCHIVE | V9 two-model proposal. |
| `V10_ERROR_DISTRIBUTION.md` | REFERENCE | V10 full error analysis with per-dimension breakdowns. |
| `GATE_V0_EVALUATION.md` | REFERENCE | Gate v0 evaluation (rejected, M8 retained). |
| `CODEX_V9_BEST_OF_IPF_SUMMARY.md` | ARCHIVE | Codex V9 Best-of-IPF summary. |
| `DEMOGRAPHICS_MODEL_HANDOFF.md` | REFERENCE | Demographics model handoff document. |
| `HOLDOUT_VALIDATION_REPORT.md` | REFERENCE | Holdout validation report. |
| `METHODOLOGY_REPORT_V2.md` | REFERENCE | Methodology report V2. |
| `METHODOLOGY_REPORT_V3.md` | REFERENCE | Methodology report V3. |
| `METHODOLOGY_REPORT_V4.md` | REFERENCE | Methodology report V4. |

---

## 6.5 Scripts (Code-side)

Code lives in `scripts/`. Each subdirectory has a clear purpose; files below are not exhaustive but cover the main entrypoints.

### scripts/managed_agents/ (Gold Standard dossier pipeline)

| File | Status | Description |
|------|--------|-------------|
| `RUN_DOSSIERS.md` | ACTIVE | 4-batch runbook for the Claude Code subagent pipeline (Max 20x, $0 out-of-pocket). |
| `export_employer_data.py` | ACTIVE | 1,561-line per-employer JSON exporter with schema introspection. CLI: `--master-id`/`--all`/`--dry-run`, atomic writes. |
| `seed_corporate_parents.py` | ACTIVE | Idempotent corporate-hierarchy seeder for dossier-discovered parents. Tags rows `source='DOSSIER_RESEARCH_2026_04'`. ASCII-safe console output. |
| `ingest_dossiers.py` | ACTIVE | Parses YAML frontmatter + markdown body of finished dossiers, cross-refs `run_log*.json`, UPSERTs into `research_runs` with dedup key `(employer_id, triggered_by)`. |
| `build_starbucks_supplement.py` | REFERENCE | Auxiliary supplement builder used during Starbucks dossier dev. |
| `targets.json`, `targets_v2.json` | REFERENCE | Locked target lists (20 + 18 employers). |
| `run_log.json`, `run_log_v2.json`, `run_log_v3.json` | REFERENCE | Per-slot dossier metrics across 38 runs. |
| `dossiers/` | REFERENCE | 38 finished gold-standard dossiers (2026-04-21 through 2026-04-22). |
| `exports/` | REFERENCE | 38 per-employer JSON exports backing the dossiers. |

### scripts/llm_dedup/ (LLM-judged dedup + rule engine)

| File | Status | Description |
|------|--------|-------------|
| `01_blocking.py`, `01b_blocking_singletons.py` | ACTIVE | Initial blocking pass on master_employers (full + singletons-only). |
| `02_prep_batches.py` | ACTIVE | Prep candidate pairs into LLM batches. |
| `03_run_ensemble.py`, `04_generate_report.py` | REFERENCE | Original 5-method ensemble experiment (~25% accuracy, superseded). |
| `extract_singletons_ny_25k.py`, `extract_ny_sample.py` | ACTIVE | Sample extraction for NY pilots. |
| `dedup_judge_prompt.py`, `validation_judge_prompt.py` | ACTIVE | Cache-padded Haiku 4.5 prompts (5,620 tok). v2 has 6-verdict taxonomy + 37-signal enum + 17 worked examples. |
| `prep_anthropic_batch.py`, `submit_anthropic_batch.py` | ACTIVE | Batch API JSONL writer + rate-limit-tolerant submitter. |
| `prep_validation_batch.py`, `submit_validation_batch.py` | ACTIVE | Validation-job variants with 30s inter-chunk pauses + 6-retry exponential backoff. |
| `calibrate_judge_live.py`, `calibrate_validation_prompt.py` | ACTIVE | Live-API token/cost calibration. |
| `build_review_csv.py`, `build_validation_sample.py` | ACTIVE | Stratified samplers + reviewer CSV builders. |
| `analyze_small_clusters.py`, `analyze_validation_results.py` | ACTIVE | Rule-candidate mining, matching gap analysis, hierarchy filter generation. |
| `validate_heuristic_rules.py`, `validate_rule_engine.py` | ACTIVE | Validate H1-H16 rules against Haiku gold labels. |
| `rule_engine.py` | ACTIVE | Production classifier (H1-H16 rules + person-name + EIN-conflict blockers). Tier A 96.1% precision. |
| `apply_llm_gold_merges.py`, `apply_rule_merges.py` | ACTIVE | Union-find appliers for LLM gold and rule-engine merges. |
| `extract_hierarchy.py`, `write_hierarchy.py` | ACTIVE | Hierarchy edge extractor + loader (`--reject-parents` filter). 400,967 rows. |
| `national_dry_run.py` | ACTIVE | Per-state dry-run + tier_B/C/D residual + hierarchy CSV export. |
| `create_dev_sample.py`, `show_50_dupes.py` | REFERENCE | Dev/inspection helpers. |

### scripts/scraper/ (Union web scraper rule engine + pilots)

| File | Status | Description |
|------|--------|-------------|
| `rules_engine.py` | ACTIVE | Rule application module with `RuleEngine` + `Candidate` dataclass + `extract_from_page` entry. Confidence-weighted intra-text dedup. |
| `pilot_extract_zerocost.py` | ACTIVE | Zero-cost extraction pilot (requests + BeautifulSoup + trafilatura + extruct). `--sample` flag. |
| `build_pilot_sample.py`, `compare_pilots.py` | ACTIVE | Stratified pilot sample builder (seed=42 with ORDER BY) + v1/v2 reporter. |
| `pilot_sample_v2.json` | REFERENCE | 70-site stratified sample. |
| `pilot_results/`, `pilot_results_v2/` | REFERENCE | Per-site JSON outputs and summary.md (v2 = 6.04 candidates/site, 3.2x lift). |
| `extract_wordpress.py`, `clean_wp_employers.py`, `extract_union_data.py` | ACTIVE | WP REST extraction pipeline. |
| `extract_gemini_fallback.py` | REFERENCE | Gemini-fallback extractor (older vintage). |
| `extract_ex21.py` | ACTIVE | SEC 10-K Exhibit 21 subsidiary extractor. |
| `discover_pages.py`, `fetch_union_sites.py`, `fetch_summary.py` | ACTIVE | Page discovery and fetch utilities. |
| `parse_structured.py`, `extraction_report.py` | ACTIVE | Structured-data parsing + reporting. |
| `match_web_employers.py` | ACTIVE | Match scraped employers to f7_employers via trigram. |
| `ai_employers_batch1.json`, `ai_employers_batch2.json`, `manual_employers*.json` | REFERENCE | Manual seed lists. |
| `read_profiles.py`, `run_extraction_pipeline.py`, `fix_extraction.py`, `export_html.py` | REFERENCE | Pipeline runners and post-processing. |

### scripts/etl/contracts/ (State/local contracts loaders — 2026-04-22)

| File | Status | Description |
|------|--------|-------------|
| `_city_common.py`, `_nyc_common.py` | ACTIVE | Shared utilities for city/NYC contract loaders. |
| `load_ny_abo.py` | ACTIVE | NY State ABO loader (371K rows). |
| `load_nyc_passport_vendors.py`, `load_nyc_contracts_master.py`, `load_nyc_recent_awards.py`, `load_nyc_transactions.py` | ACTIVE | NYC PASSPort + Checkbook bundle (4 loaders, ~336K total rows). |
| `load_va_eva.py` | ACTIVE | VA eVA statewide loader (1.34M rows). |
| `load_richmond_contracts.py` | ACTIVE | Richmond city contracts. |
| `load_oh_checkbook.py` | ACTIVE | OH Checkbook statewide loader (2.8M rows). |
| `load_columbus.py`, `load_cincinnati_payments.py` | ACTIVE | Columbus + Cincinnati city loaders. |
| `build_unified_view.py` | ACTIVE | Builds `state_local_contracts_unified` VIEW (6.1M rows) + `state_local_vendors_unique` MV (346K vendors). |
| `match_state_local_contracts.py` | ACTIVE | Deterministic name+state matching against f7_employers (4,790 1:1 matches). |
| `match_state_local_contracts_to_masters.py` | ACTIVE | Same exact-block name+state matching against master_employers (5.5M) with `scripts.llm_dedup.rule_engine.classify_pair_v2` H1-H16 post-filter. **46,814 1:1 master matches (~10x f7 lift), 30,218 Tier A; 30,692 in beta states.** Wires into `mv_target_data_sources.is_state_local_contractor` (Tier A+B only). Added 2026-04-23. |
| `integrate_state_local_into_crosswalk.py` | ACTIVE | Adds 3 columns to corporate_identifier_crosswalk + UPDATE/INSERT (f7-side only). |

### scripts/etl/ (Union directory scrapers — 2026-04-19 through 2026-04-21)

| File | Status | Description |
|------|--------|-------------|
| `scrape_teamsters_directory.py` | ACTIVE | IBT WP REST + state-HTML scraper (330 profiles). |
| `scrape_seiu_directory.py` | ACTIVE | SEIU XML feed scraper (88 profiles, 53 OLMS-matched). |
| `scrape_apwu_directory.py` | ACTIVE | APWU static HTML scraper (97 profiles, 48 OLMS-matched). |
| `scrape_cwa_directory.py` | ACTIVE | CWA Drupal Views pagination scraper (697 profiles, 80% OLMS match). |
| `scrape_ibew_directory.py` | ACTIVE | IBEW iframe → ibewapp.org JSON API scraper (764 profiles, 87% match, 100% officer coverage). |
| `scrape_usw_directory.py` | ACTIVE | USW district chain-scraper (56 profiles, 91% match). |
| `setup_afscme_scraper.py` | ACTIVE | AFSCME setup + scraper (157 profiles after dedup). |
| `audit_ny_contracts.py` | REFERENCE | Auditor for NY contract data quality. |

### config/scraper_rules/ (Rule engine config — 2026-04-19)

| File | Description |
|------|-------------|
| `trigger_phrases.json` | 14 news-headline + prose patterns with HIGH/MEDIUM/LOW bands. |
| `pdf_filename_patterns.json` | 7 contract-PDF naming heuristics. |
| `cms_bypass.json` | 4 CMS bypass profiles (UnionActive-IIS, WP REST, Elementor, Drupal Views). |
| `employer_blocklist.json` | 45 stopwords + 14 substring + 7 regex patterns (US state names + "X HQ"). |

### Research agent + hierarchy arc (2026-04-24 — 7-session plan-mode arc)

| File | Status | Description |
|------|--------|-------------|
| `scripts/etl/nlrb_nightly_pull.py` | ACTIVE | Last-24-hours NLRB case pull from `nlrb.gov/search/case.json`. Rate-limited, retry-budgeted per page (Codex #1 fix), advisory-xact-lock serialized writers (Codex #2 fix). Emits handoff JSON for matcher. |
| `scripts/matching/match_nlrb_nightly_to_masters.py` | ACTIVE | Reads handoff → exact-block name+state against `master_employers` → `classify_pair_v2` H1-H16 post-filter → UML with `source_system='nlrb_participants'`, `source_id=participant.id` (Codex #3 fix). |
| `scripts/maintenance/setup_nlrb_nightly_task.ps1` | READY | Windows Task Scheduler registration, 2 AM daily chain pull+match. Not yet installed (admin required). |
| `scripts/etl/load_sec_exhibit21.py` | ACTIVE | SEC EDGAR 10-K Exhibit 21 scraper. Fetches submissions JSON → latest 10-K → /Archives index.json → Ex21 file, parses HTML-table-first with header-row filter. Writes to `corporate_ultimate_parents source='SEC_EXHIBIT_21'`. Outer-loop `conn.rollback()` on filer error (Codex #4 fix). Requires `USER_AGENT="Labor Data Terminal email@..."`. Verified on Starbucks: 6 subs. |
| `scripts/research/ab_test_critique_loop.py` | READY | 5 employers × 2 arms (RESEARCH_CRITIQUE_ROUNDS=1 vs 3) via subprocess. `usable` boolean gates averages (Codex #5 fix). Writes vault markdown report. Dry-run verified; not yet fired (~$5-10 spend). |
| `scripts/managed_agents/build_starbucks_supplement.py` | ACTIVE | Aggregates NLRB/OSHA/WHD/SEC XBRL/F-7/master counts across all Starbucks-named entities via participant_name/estab_name/legal_name ILIKE matching. Writes `_starbucks_national_supplement` block into JSON export. |
| `sql/schema/research_runs_critique_and_tokens_migration.sql` | APPLIED | ADD COLUMN IF NOT EXISTS: critique_result JSONB, total_input_tokens, total_output_tokens, retry_count + `idx_research_runs_completed_at` partial index. |
| `sql/schema/nlrb_participants_case_docket_url_migration.sql` | APPLIED | ADD COLUMN case_docket_url + UPDATE backfill (1,906,542 rows) + BEFORE INSERT OR UPDATE trigger. |
| `tests/test_research_queries.py` | ACTIVE | 3 regression tests: agent.py + tools.py free of dead site: patterns + DB test on research_query_effectiveness. |
| `frontend/__tests__/FamilyRollupSection.test.jsx` | ACTIVE | 8 tests: null/loading/error states, self-gate, banner + 4 tiles, docket URL hyperlink, respondent-variants expand/collapse, F-7 prop path. |
| `frontend/__tests__/ComparablesCard.test.jsx` | ACTIVE | 5 tests: comparable_type rendering, "N unionized" count correctness, click-to-expand body content. |

---

## 7. Vault: Data Sources

### Core Union Reference

| File | Description |
|------|-------------|
| `Data Sources/Core Union Reference/F-7 Union Filings.md` | F-7 employer reports: 1.09M filings, fully integrated, core union-employer link. |
| `Data Sources/Core Union Reference/LM Filings.md` | LM-2/LM-3/LM-4 union financial filings from OLMS. |
| `Data Sources/Core Union Reference/NLRB Cases and Docket.md` | NLRB case data and docket entries. |
| `Data Sources/Core Union Reference/NLRB Elections.md` | NLRB union representation elections. |
| `Data Sources/Core Union Reference/EPI Union Density.md` | EPI union density estimates by state/industry. |
| `Data Sources/Core Union Reference/Union Financial Disbursements.md` | Union financial disbursement data from LM filings. |

### Enforcement and Workplace Conditions

| File | Description |
|------|-------------|
| `Data Sources/Enforcement and Workplace Conditions/OSHA.md` | OSHA inspection and violation data. |
| `Data Sources/Enforcement and Workplace Conditions/WHD Wage and Hour.md` | WHD wage and hour violation data. |
| `Data Sources/Enforcement and Workplace Conditions/NLRB Unfair Labor Practices.md` | NLRB ULP case data. |

### BLS Labor Statistics

| File | Description |
|------|-------------|
| `Data Sources/BLS Labor Statistics/BLS JOLTS Turnover.md` | BLS JOLTS job openings, hires, separations. |
| `Data Sources/BLS Labor Statistics/BLS NCS Benefits.md` | BLS National Compensation Survey benefits data. |
| `Data Sources/BLS Labor Statistics/BLS OES Wages.md` | BLS Occupational Employment and Wage Statistics. |
| `Data Sources/BLS Labor Statistics/BLS QCEW.md` | BLS Quarterly Census of Employment and Wages. |
| `Data Sources/BLS Labor Statistics/BLS SOII Injury Rates.md` | BLS Survey of Occupational Injuries and Illnesses. |
| `Data Sources/BLS Labor Statistics/BLS Staffing Patterns.md` | BLS industry-occupation staffing patterns. |
| `Data Sources/BLS Labor Statistics/BLS Union Density.md` | BLS union membership and density by state/industry. |

### Corporate Identity and Hierarchy

| File | Description |
|------|-------------|
| `Data Sources/Corporate Identity and Hierarchy/CorpWatch.md` | CorpWatch corporate hierarchy data (773K edges). |
| `Data Sources/Corporate Identity and Hierarchy/GLEIF Corporate Ownership.md` | GLEIF LEI corporate ownership data (378K records). |
| `Data Sources/Corporate Identity and Hierarchy/Mergent Intellect.md` | Mergent Intellect: 126K employers, 670K financials, 57K executives. |
| `Data Sources/Corporate Identity and Hierarchy/SEC EDGAR.md` | SEC EDGAR company filings and submissions (517K companies). |
| `Data Sources/Corporate Identity and Hierarchy/SEC XBRL Financials.md` | SEC XBRL structured financial data (249K records). |

### Federal Contracting and Tax

| File | Description |
|------|-------------|
| `Data Sources/Federal Contracting and Tax/Form 5500 Benefit Plans.md` | Form 5500 employee benefit plan filings. |
| `Data Sources/Federal Contracting and Tax/IRS BMF.md` | IRS Business Master File: nonprofit registry. |
| `Data Sources/Federal Contracting and Tax/IRS Form 990.md` | IRS Form 990 nonprofit financial filings (587K records). |
| `Data Sources/Federal Contracting and Tax/PPP Loans.md` | PPP loan data with employee counts. |
| `Data Sources/Federal Contracting and Tax/SAM.gov.md` | SAM.gov federal contractor registry. |
| `Data Sources/Federal Contracting and Tax/USASpending Federal Contracts.md` | USASpending federal contract awards. |

### Census and Demographics

| File | Description |
|------|-------------|
| `Data Sources/Census and Demographics/ACS Workforce Demographics.md` | American Community Survey workforce demographics. |
| `Data Sources/Census and Demographics/Census ABS.md` | Census Annual Business Survey. |
| `Data Sources/Census and Demographics/Census CBP.md` | Census County Business Patterns. |
| `Data Sources/Census and Demographics/Census Tract Demographics.md` | Census tract-level demographic data. |
| `Data Sources/Census and Demographics/EEO-1 FOIA Data.md` | EEO-1 employer demographic data (FOIA). |
| `Data Sources/Census and Demographics/LODES Commuting Data.md` | LODES origin-destination commuting data. |
| `Data Sources/Census and Demographics/QWI.md` | Quarterly Workforce Indicators (county x NAICS4 demographics). |
| `Data Sources/Census and Demographics/ZIP-Tract Crosswalk.md` | HUD ZIP-to-Census-Tract crosswalk. |

### Matching Infrastructure

| File | Description |
|------|-------------|
| `Data Sources/Matching Infrastructure/Corporate Crosswalk.md` | Corporate crosswalk linking identifiers across sources. |
| `Data Sources/Matching Infrastructure/Employer Comparables.md` | Gower-based employer comparable peers. |
| `Data Sources/Matching Infrastructure/Splink Match Results.md` | Legacy Splink probabilistic match results. |
| `Data Sources/Matching Infrastructure/Unified Match Log.md` | Unified match log audit trail for all matching. |

### Scoring Pipeline

| File | Description |
|------|-------------|
| `Data Sources/Scoring Pipeline/Occupation Similarity.md` | SOC-based occupation similarity scoring. |
| `Data Sources/Scoring Pipeline/Unified Scorecard.md` | Unified scorecard materialized view. |

### Not Yet Acquired

| File | Description |
|------|-------------|
| `Data Sources/Not Yet Acquired/CPS Microdata.md` | CPS microdata (planned). |
| `Data Sources/Not Yet Acquired/State OSHA Plans.md` | State OSHA plan data (planned). |
| `Data Sources/Not Yet Acquired/State PERB Data.md` | State PERB data (planned). |
| `Data Sources/Not Yet Acquired/State and Municipal Contracts.md` | State and municipal contract data (planned). |
| `Data Sources/Not Yet Acquired/WARN Act Layoff Notices.md` | WARN Act layoff notices (planned). |

### Data Sources README

| File | Description |
|------|-------------|
| `Data Sources/_README - Data Sources.md` | Guide to the Data Sources folder structure. |

---

## 8. Vault: Systems

| File | Description |
|------|-------------|
| `Systems/API Backend.md` | FastAPI backend system reference. |
| `Systems/Agent and Skill Infrastructure.md` | 9 agents + 22 skills + 12 specs. 3-tier loading hierarchy. (added 2026-04-08) |
| `Systems/Authentication and Authorization.md` | Auth system: JWT, middleware, role-based access. |
| `Systems/CBA Pipeline.md` | CBA extraction and analysis pipeline. |
| `Systems/Campaign Tracking.md` | Campaign tracking system. |
| `Systems/Corporate Identity System.md` | Corporate identity resolution and hierarchy. |
| `Systems/Database Schema.md` | PostgreSQL database schema reference. |
| `Systems/Demographics Model.md` | Demographics estimation model (V10/V12). |
| `Systems/ETL Pipeline.md` | ETL pipeline system reference. |
| `Systems/Employer Profile and Organizing Intelligence.md` | Employer profile and organizing intelligence system. |
| `Systems/Frontend.md` | React 19 frontend system reference. |
| `Systems/Maintenance and Operations.md` | Maintenance, backup, and operational procedures. |
| `Systems/Matching Pipeline.md` | Matching pipeline system reference (V2 engine). |
| `Systems/Research Agent.md` | Gemini-powered research agent system. |
| `Systems/Research Agent Roadmap.md` | Research agent development roadmap. |
| `Systems/Scoring System.md` | 10-factor scoring system with pillar-based final scores. |
| `Systems/Web Scraper.md` | Union web scraper system. |
| `Systems/_README - Systems.md` | Guide to the Systems folder. |

---

## 9. Vault: Decisions

| File | Description |
|------|-------------|
| `Decisions/2026-02-17 - Gower Distance for Comparables Only.md` | Use Gower distance only for finding comparable employers. |
| `Decisions/2026-02-20 - Corporate Identity and Crosswalk Strategy.md` | Corporate identity resolution and crosswalk approach. |
| `Decisions/2026-02-20 - Data Source Loading Decisions.md` | Which data sources to load and how. |
| `Decisions/2026-02-20 - Master Employer and Two-Track Strategy.md` | Master employer table and two-track (union/non-union) strategy. |
| `Decisions/2026-02-20 - Matching Pipeline Architecture.md` | Matching pipeline architecture decisions. |
| `Decisions/2026-02-20 - Platform UX Foundations.md` | Platform UX foundation decisions. |
| `Decisions/2026-02-20 - Public Sector Strategy.md` | Public sector data strategy. |
| `Decisions/2026-02-20 - Research Agent and Deep Dive Design.md` | Research agent and deep dive feature design. |
| `Decisions/2026-02-20 - Scoring Factor Design and Weight Evolution.md` | Scoring factor design and weight evolution decisions. |
| `Decisions/2026-02-20 - Security Auth and Launch Strategy.md` | Security, authentication, and launch strategy. |
| `Decisions/2026-02-20 - Visual Theme Evolution.md` | Visual theme evolution (Aged Broadsheet). |
| `Decisions/2026-02-22 - CBA Pipeline Design.md` | CBA pipeline design decisions. |
| `Decisions/2026-02-26 - Score Validation and Predictive Power.md` | Score validation and predictive power analysis. |
| `Decisions/2026-02-26 - Scoring Tier System.md` | Scoring tier system design. |
| `Decisions/2026-03-01 - Removed and Killed Features.md` | Features removed or killed and why. |
| `Decisions/2026-03-12 - Demographics Model V10 Final.md` | Demographics V10 model finalized. |
| `Decisions/2026-03-18 - Open Scoring Questions.md` | Open scoring questions and pending decisions. |
| `Decisions/2026-03-19 - CBA Article-Level Parsing Over Provision-Level Classification.md` | Article-level parsing chosen over provision-level classification. |
| `Decisions/2026-04-11 - D16 Shelf Wage Outlier Reframe Wages as Area Benchmarks.md` | D16 — drop wage outlier scoring entirely, reframe OES wages as MSA-first area benchmarks. |
| `Decisions/_README - Decisions.md` | Guide to the Decisions folder. |

---

## 10. Vault: Research

| File | Description |
|------|-------------|
| `Research/2026-04-15 - Entity Context Summary Implementation Plan.md` | Plan for #44 — distinguish unit / group / corporate-family size on profiles. 6-hour frontend fix; 4 product decisions surfaced. (2026-04-15) |
| `Research/2026-04-24 - State Local Contracts Pilot Plan Weeks 1-3.md` | Day-by-day 3-week plan (2026-04-28 → 2026-05-15) hardening the state/local contracts pipeline for June 5 beta. Week 1: V2 fuzzy + rule-engine post-filter on F7 + master. Week 2: Public Money section in employer profile. Week 3: family-rollup tile extension. Scope decisions locked. (2026-04-24) |
| `Research/CBA Provision Taxonomy.md` | CBA provision taxonomy research. |
| `Research/Codex Review - Demographics Model Next Steps.md` | Codex review of demographics model next steps. |
| `Research/Deep Research Pipeline Gap Analysis.md` | Gap analysis of deep research pipeline vs reference design. |
| `Research/Demographics Estimation Methodology.md` | Demographics estimation methodology overview. |
| `Research/Demographics Floor Analysis.md` | Analysis of the demographics model accuracy floor. |
| `Research/Demographics Model Development Report.md` | Full development report for demographics model V3-V12. |
| `Research/EEO-1 HQ Rollup Effect on Demographics MAE.md` | HQ-rollup partition (2026-04-18): Race/Hispanic floors NOT driven by rollup artifact; gender IS (+2.54pp penalty). V13 direction = gender-specific fix using operating NAICS. |
| `Research/Gold Standard Dossier Template.md` | 11-section template spec; Bottom Line bullets expanded 4→7 (added PPP, SAM-registered, 990-revenue) on 2026-04-21. |
| `Research/Gold Standard Dossier Targets.md` | Locked list of 20 single-location employers for Managed Agents pipeline (2026-04-10). |
| `Research/State and Municipal Contracts Scouting Report.md` | Pre-pipeline scouting that informed the 2026-04-22 state/local contracts loader work (NY/VA/OH beta). |
| `Research/Gower Distance for Comparables.md` | Gower distance methodology for employer comparables. |
| `Research/Match Quality Empirical Validation.md` | Empirical validation of match quality across sources. |
| `Research/Matching Algorithm Comparison.md` | Comparison of matching algorithms (deterministic vs probabilistic). |
| `Research/Name Normalization Algorithm.md` | Name normalization algorithm design and rules. |
| `Research/OCR Tool Comparison for CBA Processing.md` | OCR tool comparison for scanned CBA processing. |
| `Research/Research Agent Grading Rubric.md` | Grading rubric for research agent dossier quality. |
| `Research/Research Agent Tool Classification.md` | Classification of 24 research agent tools. |
| `Research/Revenue Per Employee Size Estimation.md` | RPE-based employer size estimation methodology. |
| `Research/Scoring Factor Weights and Pillar Formula.md` | Scoring factor weights and pillar formula research. |
| `Research/Union Density Geographic Analysis.md` | Union density geographic analysis. |
| `Research/_README - Research.md` | Guide to the Research folder. |

---

## 11. Vault: Open Problems

Many notes still live here that have been **resolved** but not yet renamed to closed-status. Cross-reference the resolution column below.

| File | Description | Resolution |
|------|-------------|------------|
| `Open Problems/138 Unresolved Union File Numbers.md` | 138 union file numbers that cannot be resolved to employers. | **CLOSED** P6-2 (2026-03-19). |
| `Open Problems/Auth Implementation Gaps vs Spec.md` | Auth implementation gaps compared to specification. | OPEN. |
| `Open Problems/CBA Rule Config Possibly Relocated.md` | CBA rule config files. | RENAMED — coverage is the issue, not relocation. |
| `Open Problems/CBA Rule Coverage Gaps.md` | CBA rule coverage gaps in extraction. | OPEN. |
| `Open Problems/CLAUDE.md Stale Counts.md` | CLAUDE.md contains stale row counts. | PARTIALLY FIXED (most counts refreshed; recurring task). |
| `Open Problems/Dead Code UnifiedScorecardPage.md` | Dead code in UnifiedScorecardPage component. | **CLOSED** archived 2026-04-14. |
| `Open Problems/Demographics API Serves Raw ACS Not V10.md` | Demographics API serves raw ACS. | PARTIALLY FIXED — employer endpoint uses V12; generics still raw. |
| `Open Problems/Docker JWT Default Secret.md` | Docker config uses default JWT secret. | **CLOSED** P0-2 (2026-03-18). |
| `Open Problems/Frontend No-Data Cards Inconsistent.md` | Frontend no-data cards render inconsistently. | **CLOSED** P2-1 (2026-03-18). |
| `Open Problems/Frontend Test Failure DataFreshness.md` | Frontend test failure in DataFreshness component. | **CLOSED** P2-2 (2026-03-18). |
| `Open Problems/Gender Model County-Level Occupation Rates.md` | Gender model needs county-level occupation rates. | OPEN — V13 direction (per EEO-1 HQ Rollup research). |
| `Open Problems/Gower Similarity Pipeline Produces Nothing.md` | Gower similarity pipeline produces zero results. | **CLOSED** P1-2 (2026-04-01). 15.5M rows now, 80.4% coverage. |
| `Open Problems/Matching FP Rates in Fuzzy Bands.md` | False positive rates in fuzzy matching confidence bands. | PARTIALLY FIXED — V2 engine raised floor 0.80→0.90 (2026-04-03). |
| `Open Problems/No Data Freshness Tracking.md` | No automated data freshness tracking. | PARTIALLY FIXED — table has 2 rows, ~80 loaders still uninstrumented. |
| `Open Problems/No Off-Site Backup.md` | No off-site backup for database. | **CLOSED** P0-3 (2026-04-03, local-only accepted). |
| `Open Problems/Phase 2 Source Re-Runs Not Complete.md` | Phase 2 source re-runs not completed. | PARTIALLY FIXED — SAM/990/SEC done; only WHD legacy remains. |
| `Open Problems/Research Agent Human Review Near Zero.md` | Research agent human review rate near zero. | OPEN. |
| `Open Problems/Research Agent Missing Pipeline Phases.md` | Research agent missing pipeline phases. | **CLOSED** R0-R3 15-item roadmap (2026-03-23). |
| `Open Problems/SEC XBRL Erroneous Future Dates.md` | SEC XBRL data contains erroneous future dates. | **CLOSED** P1-3 (2026-03-18). |
| `Open Problems/Scoring Weights Ignore Predictive Power.md` | Scoring weights not validated against predictive power. | **CLOSED** D12 (2026-04-03). |
| `Open Problems/Stability Pillar Near-Zero Coverage.md` | Stability pillar has near-zero data coverage. | **CLOSED** D13 (demoted to flags, 2026-04-03). |
| `Open Problems/Vite Proxy Port Mismatch.md` | Vite proxy targets wrong port. | **CLOSED** (port aligned). |
| `Open Problems/Weak Database Password.md` | Database password is weak. | **CLOSED** P0-1 rotated (2026-03-18). |
| `Open Problems/_README - Open Problems.md` | Guide to the Open Problems folder. | — |

---

## 12. Vault: Work Log

| File | Description |
|------|-------------|
| `Work Log/2026-03-09 - EEO-1 Data Inventory and V6 Demographics.md` | EEO-1 data inventory, V6 demographics model. |
| `Work Log/2026-03-11 - Demographics V8 V8.5 V9.1 Architecture Analysis.md` | Demographics model architecture analysis (V8-V9.1). |
| `Work Log/2026-03-12 - CBA Progressive Decomposition.md` | CBA progressive decomposition pipeline. |
| `Work Log/2026-03-12 - SEC XBRL Financial Data Phase 1.md` | SEC XBRL financial data Phase 1. |
| `Work Log/2026-03-12 - V11 Signal Testing and Floor Analysis.md` | V11 signal testing and accuracy floor analysis. |
| `Work Log/2026-03-12 - V9.2 Demographics Breakthrough.md` | V9.2 demographics model breakthrough. |
| `Work Log/2026-03-12 - V9.2 and V10 Demographics Model Final.md` | V9.2 and V10 model finalization. |
| `Work Log/2026-03-13 - CBA Rule Review and OPDR Batch Load.md` | CBA rule review and OPDR batch load. |
| `Work Log/2026-03-13 - Comprehensive Audit and Consolidated Roadmap.md` | Comprehensive audit and roadmap consolidation. |
| `Work Log/2026-03-13 - V11 K-Fold Cross-Validation.md` | V11 K-fold cross-validation. |
| `Work Log/2026-03-16 - Free Company Dataset Enrichment.md` | Free company dataset enrichment (2.48M companies). |
| `Work Log/2026-03-16 - Quick Wins and Test Fixes.md` | Quick wins and test fixes. |
| `Work Log/2026-03-17 - Obsidian Data Source Notes Core Union Reference.md` | Created Obsidian data source notes for Core Union Reference. |
| `Work Log/2026-03-18 - Insights Review and Obsidian Enforcement Notes.md` | Insights review and enforcement data source notes. |
| `Work Log/2026-03-18 - P0-2 P1-3 P2-1 Quick Fixes.md` | P0-2, P1-3, P2-1 quick fixes. |
| `Work Log/2026-03-18 - Security and Scoring Roadmap Items.md` | Security and scoring roadmap items. |
| `Work Log/2026-03-18 - Vault Population Open Problems Research Work Log.md` | Vault population: open problems, research, work log. |
| `Work Log/2026-03-18 - Vault Wikilink Cleanup.md` | Vault wikilink cleanup and cross-referencing. |
| `Work Log/2026-03-19 - CBA Article-Level Parsing and Frontend.md` | CBA article-level parsing and frontend view. |
| `Work Log/2026-03-19 - CBA Heading-First Classification and Fragment Fix.md` | CBA heading-first classification and fragment fix. |
| `Work Log/2026-03-19 - P6-1 P6-2 Union Data Quality Closure.md` | P6-1, P6-2 union data quality closure. |
| `Work Log/2026-03-19 - Vault Cleanup and Obsidian Path Fix.md` | Vault cleanup and Obsidian path fix. |
| `Work Log/2026-03-20 - CBA Article Extraction All 24 Contracts.md` | CBA article extraction for all 24 contracts. |
| `Work Log/2026-03-20 - NYC Property Intel Map Build.md` | NYC property intelligence map build. |
| `Work Log/2026-03-21 - CBA Rule Expansion and 150 New Contracts.md` | CBA rule expansion and 150 new contracts. |
| `Work Log/2026-03-21 - Gold Standard Dossier Pipeline and Q&A Redesign.md` | Gold standard dossier pipeline and Q&A redesign. |
| `Work Log/2026-03-22 - CBA Embeddings and Sub-Field Extraction.md` | CBA embeddings and sub-field extraction. |
| `Work Log/2026-03-22 - Research Intelligence Layer Complete.md` | Research intelligence layer completed (6 features). |
| `Work Log/2026-03-22 - Vault Data Integration Audit and Fixes.md` | Vault data integration audit and fixes. |
| `Work Log/2026-03-23 - LODES OD Labor Shed and Race Weight Reoptimization.md` | LODES OD labor shed and race weight reoptimization. |
| `Work Log/2026-03-23 - Research Agent Full Roadmap Implementation.md` | Research agent full 15-item roadmap implementation. |
| `Work Log/2026-03-24 - Strategic Launch Roadmap.md` | Strategic Launch Roadmap published. |
| `Work Log/2026-03-24 - Union Explorer Overhaul.md` | Union Explorer overhaul (P6-3). |
| `Work Log/2026-03-24 - Wage Profile Feature.md` | Wage profile feature (OES wages + QCEW benchmarks). |
| `Work Log/2026-03-26 - Demographics Model Development Report.md` | Demographics model development report write-up. |
| `Work Log/2026-03-27 - V12 QWI Demographics Model.md` | V12 QWI demographics model (broke V10 floor). |
| `Work Log/2026-03-29 - Mergent Full Pipeline and ZIP Matching.md` | Mergent full pipeline and ZIP matching. |
| `Work Log/2026-03-29 - Mergent Universal Loader and 500K Load.md` | Mergent universal loader (126K employers, 670K financials). |
| `Work Log/2026-03-29 - SEC Financial Integration P4-1 Through P4-4.md` | SEC XBRL financials API + research agent + frontend + employee count extraction. |
| `Work Log/2026-03-30 - CorpWatch Hierarchy and NLRB Investigation.md` | CorpWatch hierarchy and NLRB investigation. |
| `Work Log/2026-04-01 - Gower Similarity Overhaul.md` | Gower similarity pipeline rewrite (15.5M rows). |
| `Work Log/2026-04-03 - D12 D13 Scoring Decisions and Matching V2.md` | D12/D13 scoring decisions and matching V2. |
| `Work Log/2026-04-03 - Matching Engine V2 and Mergent Pipeline.md` | Matching Engine V2 + Mergent V2 matching. |
| `Work Log/2026-04-03 - Roadmap Audit and Scraper Investigation.md` | Roadmap audit and scraper investigation. |
| `Work Log/2026-04-04 - CBA Accuracy Audit and Searchability Overhaul.md` | CBA accuracy audit and searchability overhaul. |
| `Work Log/2026-04-04 - Full Pipeline Completion and LLM Dedup Planning.md` | Full pipeline completion + LLM dedup planning. |
| `Work Log/2026-04-05 - SEC 990 GLEIF Master Seeding and Mergent Matching.md` | SEC/990/GLEIF seeded into master, Mergent V2 matching. |
| `Work Log/2026-04-06 - LLM Dedup Experiment.md` | LLM dedup experiment (5 ensemble methods, ~25% accuracy). |
| `Work Log/2026-04-07 - OpenDataLoader-PDF OCR Evaluation.md` | OCR evaluation: quality excellent, CPU impractical (170s/page), needs GPU. |
| `Work Log/2026-04-07 - P0 Bug Sweep and Beta Strategy.md` | P0 bug sweep + beta strategy decisions. |
| `Work Log/2026-04-07 - Round 6 Full System Audit.md` | Round 6 full system audit. |
| `Work Log/2026-04-08 - Documentation Reconciliation and P0 Bug Sweep.md` | Doc reconciliation + remaining P0 bug fixes (26/27 done). |
| `Work Log/2026-04-10 - Managed Agents Dossier Planning.md` | Managed Agents dossier pipeline planning (single-location focus). |
| `Work Log/2026-04-10 - P1 Trust Quick Wins.md` | P1 quick wins: demographics 2022 label, freshness refresh, stale threshold 90→180. |
| `Work Log/2026-04-11 - D16 Wage Outlier Removal and OES MSA Upgrade.md` | D16 closed: wage outlier scoring removed, OES upgraded to MSA-first. |
| `Work Log/2026-04-11 - Mergent Batch Pipeline Prep.md` | Mergent batch pipeline prep work. |
| `Work Log/2026-04-11 - P1 Similarity Distance and Thin Data Warnings.md` | P1 #35/#36/#37: distance-based similarity, direct/indirect split, thin-data flag. |
| `Work Log/2026-04-14 - Five Small-Lift Cleanups.md` | 5-task cleanup: closed 2 stuck research runs, refreshed 8 docs, archived 40+ files, dropped MVs/indexes (3GB reclaim). |
| `Work Log/2026-04-14 - P1 Trust and Polish Eleven Items.md` | P1 11-item sweep: vintage labels, freshness, tier rule, demographics uncertainty. |
| `Work Log/2026-04-14 - V12 Demographics API Wire-In and Narrative Update.md` | V12 wired into `/api/demographics/employer/{master_id}`. |
| `Work Log/2026-04-15 - Claude Code Environment Unification.md` | Claude Code environment unification (codebase ↔ vault paths). |
| `Work Log/2026-04-15 - P2 Documentation Sweep and Entity Context Plan.md` | P2 doc sweep + #44 entity-context plan. 4 parallel agents. |
| `Work Log/2026-04-16 - CBA Semantic Search and Party Name Fixes.md` | pgvector HNSW semantic search + party name re-extraction (145/147 clean). |
| `Work Log/2026-04-16 - Entity Context Summary Implementation.md` | #44 entity-context shipped end-to-end. New table `corporate_ultimate_parents` (39,092 rows). |
| `Work Log/2026-04-16 - LLM Dedup Batch Run NY Singletons.md` | LLM Dedup Batch v2 — 25K NY singletons → 31,532 pairs → Haiku 4.5 → 258 DUPs. $29 actual. |
| `Work Log/2026-04-16 - QCEW 2024 and ACS 2024 Refresh Plus data_refresh_log Instrumentation.md` | QCEW 2024 (484K new rows) + ACS 2024 5-year refresh. data_refresh_log first 2 rows. |
| `Work Log/2026-04-17 - Rule Engine for LLM-Free Dedup.md` | 12 heuristic rules H1-H12 validated against 31,532 Haiku-labeled pairs. Tier A 96.1% precision. |
| `Work Log/2026-04-17 - RunPod OCR Infrastructure Built and Production Run Aborted.md` | RunPod OCR infra built; production run aborted ($28 / 10hr / <1% progress). |
| `Work Log/2026-04-17 - Union Scraper Expansion Kickoff.md` | Teamsters scraper (330 IBT profiles). Zero-cost extraction pilot. |
| `Work Log/2026-04-19 - Rule Engine Hierarchy Extraction + Spot Checks.md` | 200,599 hierarchy edges generated. CA/TX/FL spot-checks 100/100 each approved. |
| `Work Log/2026-04-19 - Union Scraper Plan Phase 0-2.1 Execution.md` | Phase 0-2.1: rule engine + SEIU + APWU scrapers. 3.75x lift on IBT pilot. |
| `Work Log/2026-04-21 - Gold Standard Dossier Pipeline End-to-End.md` | Iterative critique loop + 20 dossiers via Claude Code subagents under Max 20x ($0). |
| `Work Log/2026-04-21 - LLM Validation Batch v2 + Rule Engine H13-H16 + Hierarchy Load.md` | Biggest single-day dedup + hierarchy event. 65K masters merged, 401K hierarchy rows. |
| `Work Log/2026-04-21 - Union Scraper Plan Phases 2.2 through 5 Execution.md` | CWA/IBEW/USW scrapers + Phase 5 dedup. web_union_profiles 810→2,189. |
| `Work Log/2026-04-22 - Critique Loop Fixes + 18 Dossiers + Corp Parents Seed + Ingestion Loader.md` | 3 Codex bug fixes + 18 new dossiers + 9 corp hierarchy seeds + ingestion loader. |
| `Work Log/2026-04-22 - Project Atlas Dashboard.md` | Project Atlas Dashboard shipped — 181 roadmap tasks tracked with deps + history timeline. |
| `Work Log/2026-04-22 - State Local Contracts Pipeline End-to-End.md` | 11 contract loaders / 6.34M rows / 4,790 f7 matches; closes T1-contracts-pilot-3-states. |
| `Work Log/_README - Work Log.md` | Guide to the Work Log folder. |

---

## 13. Vault: Prompts

| File | Description |
|------|-------------|
| `Prompts/_README - Prompts.md` | Guide to the Prompts folder. |

---

## 14. Vault: Root Documents

| File | Status | Description |
|------|--------|-------------|
| *(Vault)* `CLAUDE.md` | ACTIVE | Vault instructions -- conventions, structure, database access, agent triggers. |
| *(Vault)* `MERGED_ROADMAP_2026_04_07.md` | ACTIVE | Authoritative roadmap -- 156 items, P0/P1/P2 + Tiers 1-3. |
| *(Vault)* `Claude Audit 4_7.md` | ACTIVE | Round 6 Claude audit report (Apr 7): 13 focus areas, 8 critical findings. |
| *(Vault)* `Round 6 Combined Audit Recommendations.md` | ACTIVE | 135 merged recommendations from Claude + Codex Round 6 audits. |
| *(Vault)* `_Index.md` | ACTIVE | Vault-level index page (Obsidian home). |
| *(Vault)* `project_atlas.html` | ACTIVE | Interactive roadmap dashboard (2026-04-22). 181 tasks, tree sidebar + card grid + modal with dep list + history timeline. Self-contained, no deps. Regenerated by `/wrapup` Part D. |
| *(Vault)* `project_atlas_state.json` | ACTIVE | Append-only task ledger backing `project_atlas.html`. Each task has `history[]`, `first_seen`, `last_seen`, `archived`. Never deletes; removed tasks → `archived=true`. |

---

## 15. Archived Documents

### archive/docs_superseded_2026_03/ (moved from root)

All files in this folder are **ARCHIVE** status -- superseded by newer documents or absorbed into the consolidated roadmap/vault.

Key files: `SCORECARD_REVISION.md`, `SCORING_SPECIFICATION.md`, `PROJECT_STATE.md`, `PLATFORM_REDESIGN_SPEC.md`, `REACT_IMPLEMENTATION_PLAN.md`, `RESEARCH_AGENT_*.md` (7 files), audit prompts and reports (Rounds 1-4), `PROMPT_*.md` (6 files), `GEMINI_*.md` (4 files), compass artifacts, and one-time fix logs.

### archive/old_roadmaps/ (22 files)

All superseded roadmaps from v8 through March 2026. Includes `COMPLETE_PROJECT_ROADMAP_2026_03.md`, `UNION_SCRAPER_UPGRADE_ROADMAP.md`, `SEC_FINANCIAL_DATA_ROADMAP.md`, `RESEARCH_AGENT_ROADMAP.md`, and many more.

### archive/docs_consolidated_2026-02/ (58 files)

Pre-consolidation documents from February 2026: session summaries, status reports, reconciliation analyses, public sector expansion, and more.

### archive/old_docs/ (33 files)

Oldest documents: audit prompts and reports (pre-Round 1), compass artifacts, misc analyses, multi-AI workflow docs.

### Other archive folders

| Folder | Files | Description |
|--------|-------|-------------|
| `archive/Claude Ai union project/` | 5 .md | Early union project session summaries. |
| `archive/NLTB_APIfiles/` | 1 .md | NLRB integration plan. |
| `archive/cba_ai_extraction/` | 1 .md | CBA system prompt. |
| `archive/imported_data/` | 4 .md | Imported data documentation. |
| `archive/nlrb_integration/` | 1 .md | NLRB integration README. |
| `archive/old_scripts/` | 1 .md | Old script READMEs. |
| `archive/start_each_ai_stale/` | 5 .md | Stale AI context files. |

### Older audits (not in archive/)

| Folder | Files | Description |
|--------|-------|-------------|
| `audits 2_22/` | 4 .md | Round 4 full audits (Feb 22). |
| `audits 2_25_2_26/` | 7 .md | Round 5 audits and synthesis (Feb 25-26). |

---

## 16. Miscellaneous Root Files

| File | Status | Description |
|------|--------|-------------|
| `BENCHMARK_EMPLOYER_GUIDE.md` | REFERENCE | Benchmark employer guide. |
| `CLAUDE_CODE_MARKER_SURYA_INVESTIGATION.md` | ARCHIVE | Marker/Surya OCR investigation for Claude Code. |
| `MARKER_SURYA_INVESTIGATION_REPORT.md` | ARCHIVE | Marker/Surya investigation report. |
| `CLAUDE_CODE_V3_PLAN.md` | ARCHIVE | Demographics V3 implementation plan. |
| `CLAUDE_CODE_V4_PLAN.md` | ARCHIVE | Demographics V4 implementation plan. |
| `CLAUDE_CODE_V5_PLAN.md` | ARCHIVE | Demographics V5 implementation plan. |
| `Complete Roadmap with commentary.md` | ARCHIVE | Annotated roadmap (superseded). |
| `DEMOGRAPHICS_ESTIMATION_SUMMARY.md` | REFERENCE | Demographics estimation summary (root copy). |
| `DEMOGRAPHICS_ESTIMATION_SUMMARY_running.md` | ARCHIVE | Running demographics estimation notes. |
| `DEMOGRAPHICS_SYNTHESIS_2026_03_08.md` | REFERENCE | Demographics synthesis (Mar 8). |
| `Demographics Methodology Enhancement Roadmap_gemini.md` | ARCHIVE | Gemini demographics roadmap. |
| `Deep_Research_Pipeline_Analysis_and_Integration_Map.md` | REFERENCE | Deep research pipeline analysis. |
| `EEO1_BDSHC_DATA_INTEGRATION_GUIDE.md` | REFERENCE | EEO-1 and BDSHC data integration guide. |
| `FULL_REMATCH_PROMPT.md` | ARCHIVE | Full rematch prompt. |
| `IPF_WORKFORCE_ESTIMATION_GUIDE.md` | REFERENCE | IPF workforce estimation guide. |
| `LABOR_PLATFORM_BRAINSTORM_REPORT.md` | ARCHIVE | Platform brainstorm report. |
| `LABOR_PLATFORM_MASTER_STRATEGY.md` | REFERENCE | Platform master strategy. |
| `Platform_Brainstorm_Response_claude.md` | ARCHIVE | Claude brainstorm response. |
| `V6_MODEL_PLAN.md` | ARCHIVE | Demographics V6 model plan. |
| `V7_CLAUDE_CODE_PROMPT.md` | ARCHIVE | Demographics V7 Claude Code prompt. |
| `V7_PLAN.md` | ARCHIVE | Demographics V7 plan. |
| `V7_PREPARATION.md` | ARCHIVE | Demographics V7 preparation. |
| `V8_CLAUDE_CODE_PROMPT.md` | ARCHIVE | Demographics V8 Claude Code prompt. |
| `V9_2_IMPROVEMENT_PROMPT.md` | ARCHIVE | Demographics V9.2 improvement prompt. |
| `V9_BEST_OF_IPF_TEST_PROMPT.md` | ARCHIVE | V9 Best-of-IPF test prompt. |
| `V9_TWO_PLUS_CLAMP_TEST_PROMPT.md` | ARCHIVE | V9 two-plus-clamp test prompt. |
| `academic-mcp-setup-guide.md` | REFERENCE | Academic MCP setup guide. |
| `analysis_results.md` | ARCHIVE | Analysis results. |
| `batch_2026_03_03.md` | ARCHIVE | Batch processing notes (Mar 3). |
| `batch_details_2026_03.md` | ARCHIVE | Batch details (Mar). |
| `cba_tool.md` | ARCHIVE | CBA tool notes (superseded by vault). |
| `chatgpt_resources_report.md` | ARCHIVE | ChatGPT resources report. |
| `claude_code_demographics_improvements.md` | ARCHIVE | Demographics improvement notes. |
| `conceptual_model.md` | ARCHIVE | Conceptual model notes (superseded by vault). |
| `config/cba_system_prompt.md` | ACTIVE | CBA system prompt for Gemini extraction. |
| `data_lessons.md` | ARCHIVE | Data lessons learned (superseded by vault). |
| `data_sources_chunks_3_through_9.md` | ARCHIVE | Data sources chunks 3-9. |
| `demographic_model_improvements_gpt.md` | ARCHIVE | GPT demographics improvement suggestions. |
| `demographics_methodology_improvements_claude.md` | ARCHIVE | Claude demographics methodology improvements. |
| `employer_pipeline.md` | ARCHIVE | Employer pipeline notes (superseded by vault). |
| `frontend.md` | ARCHIVE | Frontend notes (superseded by vault). |
| `lm2_vs_f7_analysis.md` | ARCHIVE | LM2 vs F7 analysis (superseded by vault). |
| `new_data_sources.md` | ARCHIVE | New data sources notes (superseded by vault). |
| `obsidian_vault_setup.md` | ARCHIVE | Obsidian vault setup instructions. |
| `phase3_batch5_details.md` | ARCHIVE | Phase 3 batch 5 details. |
| `phase4_matching_details.md` | ARCHIVE | Phase 4 matching details. |
| `r3_actionlog.md` | ARCHIVE | Round 3 action log. |
| `technical_lessons.md` | ARCHIVE | Technical lessons (superseded by vault). |

### Root session logs (pre-vault, to be moved to archive)

| File | Status | Description |
|------|--------|-------------|
| `session_2026_03_02_mergent_import.md` | ARCHIVE | Mergent import session. |
| `session_2026_03_04_bls_datasets.md` | ARCHIVE | BLS datasets session. |
| `session_2026_03_05_bls_research_gap.md` | ARCHIVE | BLS research gap session. |
| `session_2026_03_05_frontend_fixes.md` | ARCHIVE | Frontend fixes session. |
| `session_2026_03_05_quick_wins.md` | ARCHIVE | Quick wins session. |
| `session_2026_03_05_r3_tools.md` | ARCHIVE | R3 tools session. |
| `session_2026_03_06_news_monitoring.md` | ARCHIVE | News monitoring session. |
| `session_2026_03_06_union_fixes.md` | ARCHIVE | Union fixes session. |
| `session_2026_03_07_cba_tool.md` | ARCHIVE | CBA tool session. |
| `session_2026_03_08_demographics_comparison.md` | ARCHIVE | Demographics comparison session. |

### memory/ folder (session memories, 22 files)

Internal session memory files used by Claude Code. Not documentation -- auto-generated context.

### Other non-documentation .md files

| File | Status | Description |
|------|--------|-------------|
| `New Data sources 2_27/CATALOG_2026-02-27.md` | ARCHIVE | New data sources catalog (Feb 27). |
| `files/PROMPT_CLAUDE_CODE_R2.md` | ARCHIVE | R2 Claude Code prompt (duplicate). |
| `files/PROMPT_CODEX_R2.md` | ARCHIVE | R2 Codex prompt (duplicate). |
| `files/PROMPT_GEMINI_R2.md` | ARCHIVE | R2 Gemini prompt (duplicate). |
| `frontend/README.md` | ACTIVE | Frontend README (Vite + React). |
| `demographic estimate model/HOLDOUT_VALIDATION_REPORT.md` | REFERENCE | Holdout validation report (old location). |
| `demographic estimate model/METHODOLOGY_REPORT_V2.md` | REFERENCE | Methodology report V2 (old location). |
| `scripts/tools/transcription/whisper/README.md` | REFERENCE | Whisper transcription tool README. |
| `scripts/tools/transcription/whisper/CHANGELOG.md` | REFERENCE | Whisper transcription changelog. |
| `scripts/tools/transcription/whisper/model-card.md` | REFERENCE | Whisper model card. |
| `scripts/tools/transcription/whisper/data/README.md` | REFERENCE | Whisper data README. |
| `.claude/napkin.md` | ACTIVE | Per-repo napkin file tracking mistakes and corrections. |

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Root Documents | 23 |
| Start each AI/ | 4 |
| docs/ (all subfolders) | ~120 |
| .claude/agents/ | 9 |
| .claude/specs/ | 13 |
| .claude/skills/ (codebase) | 7 |
| .claude/skills/ (vault) | 22 |
| scripts/ (managed_agents/llm_dedup/scraper/etl-contracts/etl-scrapers) | ~80 .py + configs |
| Demographics model reports | 25 |
| Vault: Data Sources | 48 |
| Vault: Systems | 18 |
| Vault: Decisions | 20 |
| Vault: Research | 22 |
| Vault: Open Problems | 24 (10 still open, 14 closed/partial) |
| Vault: Work Log | 75 |
| Vault: Root Documents | 7 |
| Archive (all) | ~180+ |
| Misc root files | ~50 |
| **Total .md files tracked** | **~700+** |
