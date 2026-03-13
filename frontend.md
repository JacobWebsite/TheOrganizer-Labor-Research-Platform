# Frontend Architecture (React)

## Stack
- React 19, Vite 7, TanStack Query/Table, Zustand, Tailwind 4, Lucide icons, Vitest
- Location: `frontend/` with `@` alias to `src/`
- API proxy: Vite proxies `/api` to `localhost:8001`
- Auth: Zustand store + JWT decode + `VITE_DISABLE_AUTH=true` bypass
- Toast: `sonner` (`<Toaster />` in App.jsx)

## Dev Commands
- Start: `cd frontend && VITE_DISABLE_AUTH=true npx vite` (ports 5173+ auto-increment)
- Test: `cd frontend && npx vitest run` (180 tests, 26 files)
- API must be running on port 8001

## Component Pattern
- Named exports only (no default exports)
- Tailwind CSS, no inline styles
- `lucide-react` for icons
- `@/components/ui/` for shadcn-style primitives (card, button, badge, input, select, skeleton)
- Number formatting: `.toLocaleString()`, em-dash `\u2014` for null

## API Hook Pattern
- `@tanstack/react-query` useQuery for reads, useMutation for writes
- `apiClient.get(url)` / `apiClient.post(url, body)` from `src/shared/api/client.js`
- Query keys: descriptive arrays like `['union-search', { ...params }]`
- Mutations invalidate related queries on success

## URL State Pattern
- `useSearchParams()` from react-router-dom
- Filter keys stored in URL, page resets on filter change
- Pattern in `useTargetsState.js`, `useUnionsState.js`

## Phases (ALL COMPLETE)
1. **Auth:** LoginPage, ProtectedRoute, NavBar, Layout, Breadcrumbs
2. **Search:** SearchPage, SearchBar, SearchFilters, ResultsTable, SourceBadge, SearchResultCard (card view)
3. **Profile:** EmployerProfilePage, ProfileHeader, ScorecardSection, OshaSection, NlrbSection, CrossReferencesSection, BasicProfileView, ProfileActionButtons, FlagModal, UnionRelationshipsCard, FinancialDataCard, GovernmentContractsCard, WhdCard, ComparablesCard, CorporateHierarchyCard, ResearchNotesCard
4. **Targets:** TargetsPage, TargetStats, TargetsFilters, TargetsTable, QualityIndicator
5. **Union Explorer:** UnionsPage, UnionFilters, NationalUnionsSummary, UnionResultsTable, UnionProfilePage, UnionProfileHeader, MembershipSection, OrganizingCapacitySection, UnionEmployersTable, UnionElectionsSection, UnionFinancialsSection, SisterLocalsSection, ExpansionTargetsSection, AffiliationTree
6. **Admin:** SettingsPage, HealthStatusCard, PlatformStatsCard, DataFreshnessCard, MatchQualityCard, MatchReviewCard, UserRegistrationCard, RefreshActionsCard

## Spec Gap Closure (2026-02-22)
- **Search enhancements:** Employee size filter (min/max workers inputs), score tier filter (Priority/Strong/Promising/Moderate/Low dropdown), table/card view toggle (localStorage-persisted). API: 3 new query params on `/api/employers/unified-search` (min_workers, max_workers, score_tier).
- **Profile cards (7 new):** UnionRelationshipsCard, FinancialDataCard, GovernmentContractsCard, WhdCard, ComparablesCard, CorporateHierarchyCard, ResearchNotesCard. All use CollapsibleCard pattern. WHD/Comparables/Corporate/ResearchNotes fetch own data via hooks (lazy load).
- **Profile actions:** ProfileActionButtons (Flag as Target, Export CSV, Something Looks Wrong), FlagModal (6 flag types, useMutation POST).
- **Union explorer:** ExpansionTargetsSection (analyzes union's employer base, links to Targets page), AffiliationTree (3-level lazy: Affiliation>State>Local with chevron expand).
- **API hooks added:** profile.js: useEmployerComparables, useEmployerWhd, useEmployerCorporate, useEmployerDataSources, useEmployerFlags, useFlagEmployer. unions.js: useNationalUnionDetail.

## API Response Shape Lessons (2026-02-22)
These caused bugs during initial integration — always verify actual API responses:
- `/api/health` returns `{ status, db: true/false }` not `{ database: 'ok' }`
- `/api/stats` returns `{ total_scorecard_rows, match_counts_by_source: [{source_system, match_count}] }` not `total_scorecard`/`total_matches`
- `/api/system/data-freshness` returns `{ sources: [{source_name, row_count, latest_record_date, stale}] }` not flat array with `is_stale`
- `/api/admin/match-quality` uses `total_match_rows`, `source_system`, `total_rows`, `confidence_band` not `total_matches`/`source`/`count`/`confidence`
- `/api/admin/match-review` matches have `evidence.target_name`, `source_system`, `confidence_score`
- `/api/unions/national` returns `{ national_unions: [...] }` not a flat array
- `/api/unions/{fnum}/employers` returns `{ employers: [...] }` not a flat array
- `/api/unions/search` unions have `display_name` (includes local number), `f7_employer_count`, `f7_total_workers`
- `/api/lookups/sectors` returns `{ sectors: [{sector_code, sector_name, union_count}] }` not `sector`/`count`
- Sister locals have `union_name` + `local_number` (separate fields, no `display_name`)

## Visual Theme: "Aged Broadsheet" (2026-02-27)
Warm editorial aesthetic inspired by NYT/ProPublica data journalism. 26 files modified.

### Core Palette (`@theme inline` in `src/index.css`)
| Token | Value | Name |
|-------|-------|------|
| background | `#f5f0e8` | Warm parchment |
| foreground | `#2c2418` | Espresso ink |
| card | `#faf6ef` | Cream stock |
| primary | `#1a6b5a` | Editorial teal |
| secondary | `#ede7db` | Warm linen |
| muted-fg | `#8a7e6b` | Warm gray-brown |
| accent | `#e8dfd2` | Hover tint |
| destructive | `#c23a22` | Brick red |
| border | `#d9cebb` | Parchment edge |
| ring | `#1a6b5a` | Teal focus |
| radius | `0.375rem` | Soft corners |

### Extended Palette (used directly in components)
- Nav masthead: `#2c2418` (espresso)
- Copper accent: `#c78c4e` (active nav, gold tiers, highlights)
- Lake blue: `#3a6b8c` (info states, NLRB badges)
- Forest green: `#3a7d44` (success, fresh, high quality)
- Saddle brown: `#8b5e3c` (WHD badges)
- Dusty purple: `#6b5b8a` (SEC badges)

### Typography
- Headlines: Source Serif 4 (Google Fonts) via `.font-editorial` utility class
- Body: Inter (unchanged)
- Page titles: `font-editorial text-3xl font-bold`
- Card titles: `font-editorial text-xl font-semibold`
- Table headers: `text-xs font-medium uppercase tracking-wider`

### Score/Signal Colors
- High (7+ or 80+): Brick red `#c23a22`
- Medium (4-6 or 50-79): Copper `#c78c4e`
- Low (<4 or <50): Warm stone `#d9cebb`

### Tier Colors (ProfileHeader)
- Priority: Dark ink bg `#2c2418`, cream text, copper left-border
- Strong: Teal bg `#1a6b5a`, cream text
- Promising: Copper tint `#c78c4e/20`, dark text
- Moderate: Linen bg `#ede7db`, dark text
- Low: Parchment bg `#f5f0e8`, muted text

### Source Badge Colors (SourceBadge)
F7=`#2c2418`, OSHA=`#c23a22`, NLRB=`#3a6b8c`, WHD=`#8b5e3c`, SAM=`#1a6b5a`, SEC=`#6b5b8a`, BMF=`#c78c4e`, VR=`#3a7d44`

### Table Styling
- Headers: uppercase tracking-wider on `bg-[#ede7db]`
- Zebra striping: `bg-[#f5f0e8]/50` on odd rows
- Rounded containers: `rounded-lg overflow-hidden`

## Test Pattern
- Vitest + RTL + jsdom
- `__tests__/setup.js` loads `@testing-library/jest-dom`
- Mock API hooks with `vi.mock('@/shared/api/...')`
- Wrap in `QueryClientProvider` + `MemoryRouter`
- Mock auth store for admin tests: `useAuthStore.mockImplementation((selector) => selector(state))`
- **Color assertions:** Use `container.innerHTML.includes('bg-[#hex]')` not `querySelectorAll('.bg-[#hex]')` (jsdom bracket escaping issues)
- **Text changes break tests:** Always grep `__tests__/` for old text strings when changing UI copy
