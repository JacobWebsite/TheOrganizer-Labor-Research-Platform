# Session Summary: 2026-02-22 - Claude Code - Spec Gap Closure (Search, Profile Cards, Affiliation Tree)

## Scope
Closed remaining gaps between the React frontend and UNIFIED_PLATFORM_REDESIGN_SPEC. Implemented search enhancements, 7 profile cards, profile action buttons, union explorer expansion targets, and affiliation hierarchy tree. 15 new files + 11 modified. 27 new tests. Executed via 5 parallel agents.

## Approach
Created a detailed plan with 5 independent work streams, then used TeamCreate to run 4 implementation agents in parallel (no file conflicts by design), followed by a sequential test agent:

| Agent | Scope | Files |
|-------|-------|-------|
| 1 - Search | Employee size filter, score tier filter, table/card toggle | 6 modified + 1 new |
| 2 - Profile Header | Union status label, action buttons, flag modal | 1 modified + 2 new |
| 3 - Profile Cards | 7 collapsible cards + API hooks + wiring | 2 modified + 7 new |
| 4 - Union Explorer | Expansion targets, affiliation tree | 3 modified + 2 new |
| 5 - Tests | Tests for all new components | 3 new test files |

## 1. Search Enhancements

### Employee Size Filter
- Added `min_workers` and `max_workers` to URL state (`useSearchState.js`)
- Two number `<Input>` fields in `SearchFilters.jsx` with "Min workers" / "Max workers" labels
- Filter chip: "Workers: 50-500" (clears both min and max on dismiss)
- API: `min_workers`/`max_workers` params on `GET /api/employers/unified-search`
- SQL: `COALESCE(m.consolidated_workers, m.unit_size, 0) >= %s` / `<= %s`

### Score Tier Filter
- Added `score_tier` to URL state
- `<Select>` dropdown: All tiers, Priority, Strong, Promising, Moderate, Low
- Filter chip: "Tier: Priority"
- API: `score_tier` param with regex validation `^(Priority|Strong|Promising|Moderate|Low)$`
- SQL: `EXISTS (SELECT 1 FROM mv_unified_scorecard usc WHERE usc.employer_id = m.canonical_id AND usc.score_tier = %s)`

### Table/Card View Toggle
- `viewMode` state in `SearchPage.jsx`, persisted to `localStorage` key `search-view-mode`
- Toggle buttons: LayoutList (table) / LayoutGrid (card) from lucide-react
- Card view: grid of `SearchResultCard` (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`)
- **New file: `SearchResultCard.jsx`** — card showing employer name, group count badge, source badge, location, workers, union. Click navigates to `/employers/{canonical_id}`
- Pagination shared between both views

### API Changes (`api/routers/employers.py`)
3 new query params added to `unified_employer_search()`:
```python
min_workers: int = Query(None, ge=0)
max_workers: int = Query(None, ge=0)
score_tier: str = Query(None, pattern="^(Priority|Strong|Promising|Moderate|Low)$")
```

## 2. Profile Header Enhancements

### Union Status Label
- In `ProfileHeader.jsx`, below metadata row
- Union present: green badge with Landmark icon — "Represented by {unionName}"
- No union: gray muted badge — "No Known Union"

### Action Buttons (`ProfileActionButtons.jsx`)
Three buttons rendered in ProfileHeader:
- **Flag as Target** (Flag icon) — opens FlagModal
- **Export Data** (Download icon) — generates CSV blob from employer/scorecard props, triggers download via hidden `<a>` element
- **Something Looks Wrong** (AlertTriangle icon) — opens FlagModal with `DATA_QUALITY` pre-selected

### Flag Modal (`FlagModal.jsx`)
- Fixed overlay with Card-based form
- 6 flag types: ALREADY_UNION, DUPLICATE, LABOR_ORG_NOT_EMPLOYER, DEFUNCT, DATA_QUALITY, NEEDS_REVIEW
- Notes textarea
- `useMutation` POST to `/api/employers/flags` with `{ source_type, source_id, flag_type, notes }`
- Invalidates `employer-flags` query on success

## 3. Profile Cards (7 New)

All use `CollapsibleCard` pattern with collapsed summary and expanded detail.

| Card | Data Source | Self-Fetching | Icon |
|------|------------|---------------|------|
| UnionRelationshipsCard | `employer` prop | No | Landmark |
| FinancialDataCard | `scorecard` + `dataSources` props | No | TrendingUp |
| GovernmentContractsCard | `dataSources` prop | No | FileText |
| WhdCard | `useEmployerWhd(id)` | Yes | Scale |
| ComparablesCard | `useEmployerComparables(id)` | Yes | Users |
| CorporateHierarchyCard | `useEmployerCorporate(id)` | Yes | Building2 |
| ResearchNotesCard | `useEmployerFlags(id)` | Yes | StickyNote |

### Card Details
- **UnionRelationshipsCard:** Union name (links to `/unions/{fnum}`), affiliation badge, unit size, notice date. Returns null if no union.
- **FinancialDataCard:** BLS growth %, public company (yes/no + ticker), federal contractor, nonprofit (has_990), financial score bar. Returns null if no data.
- **GovernmentContractsCard:** Total obligations (formatted currency), contract count, federal contractor badge. Returns null if not a contractor.
- **WhdCard:** Summary stats grid (violations, backwages, penalties, employees affected, repeat violator badge) + cases table (first 5, "Show all" button). Returns null if no data.
- **ComparablesCard:** Table of comparable employers: rank, name (linked to profile), similarity %, match reasons badges, union status. Returns null if no comparables.
- **CorporateHierarchyCard:** Ultimate parent (name, ticker, SEC badge), parent chain (indented arrows), subsidiaries table (first 5, expandable), family stats (total members, workers, states, unionized). Returns null if no corporate data.
- **ResearchNotesCard:** Existing flags list with type badges (color-coded) + notes + timestamps. "Add Note" inline form with flag type select + textarea. Always renders (even with 0 notes).

### Wiring in EmployerProfilePage.jsx
Cards added in spec order after existing sections:
1. ProfileHeader (existing)
2. ScorecardSection (existing)
3. UnionRelationshipsCard
4. FinancialDataCard
5. CorporateHierarchyCard
6. ComparablesCard
7. NlrbSection (existing)
8. GovernmentContractsCard
9. OshaSection (existing)
10. WhdCard
11. CrossReferencesSection (existing)
12. ResearchNotesCard

`useEmployerDataSources(id)` fetched once in orchestrator, passed to Financial + GovContracts. Self-fetching cards use their own hooks.

### New API Hooks (profile.js)
```
useEmployerComparables(id)    → GET /api/employers/{id}/comparables
useEmployerWhd(id)            → GET /api/whd/employer/{id}
useEmployerCorporate(id)      → GET /api/corporate/hierarchy/{id}
useEmployerDataSources(id)    → GET /api/employers/{id}/data-sources
useEmployerFlags(id)          → GET /api/employers/flags/by-employer/{id}
useFlagEmployer()             → POST /api/employers/flags (mutation)
```

## 4. Union Explorer Enhancements

### Expansion Targets Section (`ExpansionTargetsSection.jsx`)
- Placed on `UnionProfilePage.jsx` after SisterLocalsSection
- Analyzes union's employer base for primary states and NAICS codes
- Shows summary of primary industry and geographic concentration
- "Browse non-union targets" button navigates to `/targets?naics={naics}&state={state}`
- Uses CollapsibleCard with Target icon

### Affiliation Hierarchy Tree (`AffiliationTree.jsx`)
- Added as alternate view on `UnionsPage.jsx` with List/Tree toggle tabs
- 3-level lazy-loading expandable tree (file-explorer style):
  - **Level 0:** Affiliations (from existing `useNationalUnions` data) — aff_abbr, name, total_members, local_count
  - **Level 1:** States (fetched on expand via `useNationalUnionDetail(aff_abbr)`) — state, local_count, total_members
  - **Level 2:** Locals (fetched on expand via `useUnionSearch({ aff_abbr, state })`) — union_name, members, city. Click navigates to `/unions/{f_num}`
- Chevron toggle icons, padding-left for depth indentation
- Auto-falls back to list view when filters are active

### New API Hook (unions.js)
```
useNationalUnionDetail(affAbbr) → GET /api/unions/national/{affAbbr}
```

## 5. Tests

### New Test Files (27 tests total)

**SearchEnhancements.test.jsx (8 tests):**
- Score tier dropdown renders and triggers filter
- Employee size inputs render and trigger filter
- Tier chip shows in active filters
- Workers chip shows in active filters
- SearchResultCard renders employer info
- View toggle renders both buttons
- Card view switch works
- Toggle persists view mode

**ProfileCards.test.jsx (14 tests):**
- UnionRelationshipsCard: shows union name, shows "no known union"
- FinancialDataCard: shows growth %, shows public badge
- GovernmentContractsCard: shows obligations, hidden when not contractor
- WhdCard: shows cases table, shows summary stats
- ComparablesCard: shows top-5 with similarity %
- CorporateHierarchyCard: shows parent chain, shows family size
- ResearchNotesCard: shows flags list, shows add form
- ProfileActionButtons: flag button opens modal, export triggers download
- Union status label: "Represented by" / "No Known Union"

**AffiliationTree.test.jsx (5 tests):**
- Tree renders affiliations at top level
- Expanding affiliation shows states
- Expanding state shows locals
- Empty state message
- UnionsPage toggle buttons render

## Build & Test Results
- **Vite build:** 1877 modules, 0 errors, 1 chunk size warning (522 KB > 500 KB limit — cosmetic)
- **Frontend tests:** 134 total (21 files), all passing (was 107/18 before this session)
- **Zero regressions** — all existing 107 tests continued passing throughout

## Files Changed

### New Files (15)
| File | Purpose |
|------|---------|
| `frontend/src/features/search/SearchResultCard.jsx` | Card view for search results |
| `frontend/src/features/employer-profile/ProfileActionButtons.jsx` | Flag/Export/Report buttons |
| `frontend/src/features/employer-profile/FlagModal.jsx` | Flag submission modal |
| `frontend/src/features/employer-profile/UnionRelationshipsCard.jsx` | Union info card |
| `frontend/src/features/employer-profile/FinancialDataCard.jsx` | Financial data card |
| `frontend/src/features/employer-profile/GovernmentContractsCard.jsx` | Federal contracts card |
| `frontend/src/features/employer-profile/WhdCard.jsx` | WHD wage theft card |
| `frontend/src/features/employer-profile/ComparablesCard.jsx` | Similar employers card |
| `frontend/src/features/employer-profile/CorporateHierarchyCard.jsx` | Corporate hierarchy card |
| `frontend/src/features/employer-profile/ResearchNotesCard.jsx` | Research notes/flags card |
| `frontend/src/features/union-explorer/ExpansionTargetsSection.jsx` | Expansion targets on union profile |
| `frontend/src/features/union-explorer/AffiliationTree.jsx` | 3-level hierarchy tree |
| `frontend/__tests__/SearchEnhancements.test.jsx` | 8 tests |
| `frontend/__tests__/ProfileCards.test.jsx` | 14 tests |
| `frontend/__tests__/AffiliationTree.test.jsx` | 5 tests |

### Modified Files (11)
| File | Changes |
|------|---------|
| `api/routers/employers.py` | 3 new query params (min_workers, max_workers, score_tier) |
| `frontend/src/features/search/useSearchState.js` | Added min_workers, max_workers, score_tier to PARAM_KEYS and filters |
| `frontend/src/shared/api/employers.js` | Pass new params in useEmployerSearch |
| `frontend/src/features/search/SearchFilters.jsx` | Tier dropdown, worker inputs, new filter chips |
| `frontend/src/features/search/SearchPage.jsx` | View toggle, card view, new filter params |
| `frontend/src/features/employer-profile/ProfileHeader.jsx` | Union status label, action buttons |
| `frontend/src/features/employer-profile/EmployerProfilePage.jsx` | Wire 7 cards + useEmployerDataSources |
| `frontend/src/shared/api/profile.js` | 6 new hooks (comparables, whd, corporate, data-sources, flags, flag mutation) |
| `frontend/src/shared/api/unions.js` | useNationalUnionDetail hook |
| `frontend/src/features/union-explorer/UnionProfilePage.jsx` | Added ExpansionTargetsSection |
| `frontend/src/features/union-explorer/UnionsPage.jsx` | List/Tree toggle, AffiliationTree integration |

## Git
- **Commit:** `a3a9cd5` — "Add spec gap closure: search enhancements, profile cards, affiliation tree"
- **Pushed** to `master` on GitHub

## What's Next
- **Phase F:** Docker, CI/CD, hosting
- **Master dedup Phase 3 (fuzzy):** Codex rollout plan ready
- **194 LOW-confidence misclassification records:** BMF-only signals, needs manual review
- **Remaining uncommitted changes:** Codex deliverables (scorecard.py, build_unified_scorecard.py, master.py, CBA extraction) still unstaged
