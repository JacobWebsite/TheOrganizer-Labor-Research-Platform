# 2026-04-28 — Enigma API Pilot Session

## Context
User asked whether Enigma (https://www.enigma.com) could fill firmographic gaps on private state contractors that don't appear in Mergent or SEC. Goal: test their 600 free trial credits against 50 thin-data Tier A state-local contractor masters in NY/VA/OH.

## Changes Made

### New Files
- **`scripts/etl/enigma_pilot/enrich_thin_contractors.py`** (~430 lines) — Pilot script. Reads Enigma API key from `.env` (literal var name `Enigma API Key=...` with spaces, parsed manually like `IPUMS API Key`). Pulls 50 candidates from `mv_target_scorecard` JOIN `state_local_contracts_master_matches` filtered to NY/VA/OH, Tier A (`tier_A_auto_merge`), `effective_employee_count IS NULL`, no Mergent, no SEC, city-required. POSTs GraphQL `search` queries with `entityType: BRAND` to `https://api.enigma.com/graphql`, parses Brand-shaped responses, writes JSONL + summary CSV to `scripts/etl/enigma_pilot/output/`.
- **`scripts/etl/enigma_pilot/output/`** (gitignored eventually) — `candidates_*.csv`, `results_full_*.jsonl`, `summary_full_*.csv` from this session's runs.

### Modified Files
None. Project source unchanged outside the new directory.

### Database Changes
None. Pilot is read-only on existing tables, writes only to local files.

## Key Findings

### Hit Rate
- **42/50 = 84% match rate** (combined across 5-record dry test + 45-record main batch)
- Coverage on matched records: 82% NAICS, 84% address, ~80% phone, 80% website, 78% legal-entity-type. Strong firmographic fill on a population our DB has nothing for.

### Critical Schema Discovery
**`OPERATING_LOCATION` entity type has terrible recall vs. `BRAND` for state contractors.** Diagnostic on Rumpke (a $500M Ohio waste mgmt company): OL search → 0 matches; Brand search → 1 match every time. OST INC: 0 → 5. Lesson for any future Enigma work: search by BRAND first.

### Card-Revenue Industry Bias
Enigma's `cardTransactions` (Plus tier, supposedly the unique value prop) only produces meaningful revenue numbers for businesses with consumer/residential payment streams:
- Coherent: Rumpke (waste/residential billing) → $138M card-not-present revenue, 3,343 daily customers
- Noise: Colonial Scientific (B2B chemical distributor) → $45K/yr (real revenue ~$10-50M)
- Zero: most construction, transportation, info-tech, education, public admin contractors

**Treat card-transaction data as binary "has consumer payment activity," NOT a revenue signal.** Use Mergent + employee-count proxies for sizing.

### Geographic Coverage Gap
**8/8 misses were Virginia.** Spread across 8 different VA cities (Petersburg, McLean, Vienna, Roanoke, Partlow, Fredericksburg, Virginia Beach, Gum Spring). NY and OH had 0 misses. Likely either name-suffix normalization differences or genuine Enigma coverage weakness in VA. Did NOT diagnose root cause this session.

### Affiliated Brands Signal Is Dead
Only 1/50 records returned any `affiliatedBrands` data (2%). Enigma is **not** a useful source for parent/subsidiary linkage on this population. Continue using Mergent + SEC Ex21 + CorpWatch + GLEIF for corporate family trees.

### Pricing Mechanics
- Tier system: Free (LegalEntityName/Type), Core (1c/entity — names/addresses/websites/industries), Plus (3c/entity — card transactions), Premium (5c/entity — bankruptcy/watchlist/TIN/registrations).
- Billing rule: charged once per entity at the most expensive tier requested.
- `Account.creditsAvailable` is **Boolean only** — no exact balance via API. Must check console.enigma.com.
- GraphQL introspection appears to be free (4 introspection queries this session, all returned 200 with no credit-block warnings).

### Plugin Detour
User invoked `/plugin marketplace add https://github.com/enigma-io/enigma-claude-plugins.git` — got "/plugin isn't available in this environment" because Claude Code v2.1.113 (or the Agent SDK harness) doesn't expose `/plugin`. Investigated the repo: it's a **skill-only plugin** (4 markdown skill files: enigma-graphql, enigma-kyb, enigma-screen, enigma-gov-archive) with no MCP server. Skills are just prompt templates — they don't unlock new capabilities beyond what our raw GraphQL script already does. Decision: skip the plugin entirely.

## Roadmap Updates

No formal roadmap items closed or added. This was an evaluation session, not a build session. Findings should inform the post-beta enrichment strategy decision (likely Q3 2026).

## Debugging Notes

1. **`Address.postalCode` doesn't exist** — it's `Address.zip`. Caught on first dry-test (HTTP 400, 0 credits).
2. **`OperatingStatus` type doesn't exist** — the connection edge node is something else (`OperatingLocationOperatingStatus`, untested). Dropped the field.
3. **`BrandCardTransaction` has no `rawQuantity`** — only `projectedQuantity`. `OperatingLocationCardTransaction` has both. Not interchangeable.
4. **GraphQL `search` returns `[SearchUnion]`** (LIST of UNION over Brand|LegalEntity|OperatingLocation|Person|Address). Parser must handle list shape and use `... on TypeName` fragments per requested entityType.
5. **`creditsAvailable: false` initially blocked all queries** with HTTP 200 + `{"errors": ["Insufficient credits..."]}`. User had to manually claim trial credits at console.enigma.com/billing → `pricingPlan: null` → `pricingPlan: TRIAL`.
6. **City-required filter** boosted hit rate. With `city: null` ("Prosource, Inc." in OH), search returned `[]` immediately — too generic to disambiguate.

## Cost
~150-300 of 600 trial credits estimated burned. Hard to confirm without console access. Trial budget still has headroom for follow-up tests.

## Next Steps (User-Driven)

1. Decide whether to commit `scripts/etl/enigma_pilot/` (with a `.gitignore` for `output/`).
2. Optional: re-run 8 VA misses with name-normalization variants.
3. Optional: Premium-tier bankruptcy pass on 42 matched records (~150 credits).
4. If scaling to 3,000-seed pilot: estimate ~15,000 credits = $750 retail. Pull only firmographic fields. Skip card data. Skip affiliated brands.

## Files Affected
- `scripts/etl/enigma_pilot/enrich_thin_contractors.py` (NEW, untracked)
- `scripts/etl/enigma_pilot/output/*.csv`, `*.jsonl` (NEW, untracked, raw API responses)

No git commits this session.
