# Frontend Architecture & Feature Catalog

## Stack

**React 19** | **Vite 7** | **TanStack Query & Table** | **Zustand** | **Tailwind 4** | **Lucide Icons** | **Vitest + RTL**

- Dev: `cd frontend && VITE_DISABLE_AUTH=true npx vite` (port 5173+, proxies `/api` to 8001)
- Tests: `cd frontend && npx vitest run` — **172 tests, 26 files, 0 failures**

---

## Routing (9 pages, all lazy-loaded)

| Route | Component | Purpose |
|-------|-----------|---------|
| `/login` | `LoginPage` | Auth (only unprotected route) |
| `/search` | `SearchPage` | Employer search with filters, table/card toggle |
| `/employers/:id` | `EmployerProfilePage` | Detailed employer profile (3 tabs) |
| `/targets` | `TargetsPage` | Non-union organizing targets (signal inventory) |
| `/unions` | `UnionsPage` | Union explorer with affiliation tree |
| `/unions/:fnum` | `UnionProfilePage` | Union detail (membership, elections, financials) |
| `/research` | `ResearchPage` | Browse/start AI research deep dives |
| `/research/:runId` | `ResearchResultPage` | View completed research dossier |
| `/settings` | `SettingsPage` | Admin dashboard (admin-only) |

All protected routes wrapped in `ProtectedRoute` + `Layout` (NavBar + Breadcrumbs). Pages use `lazy()` + `Suspense` with `PageSkeleton` fallbacks.

---

## Feature Areas (7 modules, ~80+ components)

### 1. Auth (`features/auth/`)

- **LoginPage** — username/password form, error display, redirect to referrer
- **authStore** (Zustand) — JWT token, user object, login/logout, activity tracking, admin check
- Dev bypass: `VITE_DISABLE_AUTH=true` sets `{ username: 'dev', role: 'admin' }`

### 2. Search (`features/search/`, 8 files)

| Component | Role |
|-----------|------|
| `SearchPage` | Hero state (no query) + results, table/card toggle (localStorage) |
| `SearchBar` | Text input with autocomplete (debounced, min 2 chars) |
| `SearchFilters` | State, NAICS, source type, has_union, employee size range, score tier |
| `ResultsTable` | TanStack Table with sortable columns |
| `SearchResultCard` | Grid card view alternative |
| `SourceBadge` | Color-coded data source tag (F7/NLRB/VR/MANUAL/OSHA/WHD/SAM/SEC/BMF) |
| `EmptyState` | No results message |
| `useSearchState` | URL-synced filters via `useSearchParams()` |

### 3. Employer Profile (`features/employer-profile/`, 20 files)

The most complex feature. Routes by ID type: F7 (hex) hits `/api/profile/employers/{id}`, prefixed IDs (NLRB-, VR-, MANUAL-, MASTER-) hit `/api/employers/unified-detail/{id}`.

**Three tabs:** Basic, Scorecard, Deep Research

| Component | Role |
|-----------|------|
| `ProfileHeader` | Name, location, workers, tier badge with color coding |
| `ScorecardSection` | 9 scoring factors (0-10 bars), weights, explanations |
| `SignalInventory` | Target signals for non-union employers |
| `OshaSection` | Violations, citations, temporal data |
| `NlrbSection` | Election results, ULP charges |
| `CrossReferencesSection` | Linked sources with match confidence dots |
| `BasicProfileView` | Container for detail cards |
| `UnionRelationshipsCard` | Union reference data |
| `FinancialDataCard` | 990 form financials |
| `GovernmentContractsCard` | USAspending/federal contract data |
| `WhdCard` | Wage & hour violations (lazy-loaded) |
| `ComparablesCard` | Peer comparison via Gower similarity (lazy-loaded) |
| `CorporateHierarchyCard` | Parent/subsidiary tree (lazy-loaded) |
| `DataProvenanceCard` | Match metadata, source quality |
| `ResearchInsightsCard` | AI research enhancements |
| `ResearchNotesCard` | User-added notes with edit modal |
| `ProfileActionButtons` | Flag as Target, Export CSV, Something Looks Wrong |
| `FlagModal` | Report bad match dialog (6 flag types, POST mutation) |

### 4. Targets / Scorecard (`features/scorecard/`, 6 files)

Non-union employer organizing targets with signal-based scoring.

| Component | Role |
|-----------|------|
| `TargetsPage` | Main listing (50/page), sortable by quality/employees/name |
| `TargetStats` | Tier distribution cards (Priority/Strong/Promising/Moderate/Low) |
| `TargetsFilters` | Name, state, NAICS, employee range, federal contractor, nonprofit, quality threshold |
| `TargetsTable` | TanStack Table with signal counts |
| `QualityIndicator` | Visual signal strength meter |
| `useTargetsState` | URL-synced filters |

### 5. Union Explorer (`features/union-explorer/`, 14 files)

Two sub-pages: union search/browse and individual union profiles.

**Search page:**

| Component | Role |
|-----------|------|
| `UnionsPage` | Search + list/tree toggle (tree shows when no filters active) |
| `NationalUnionsSummary` | Top affiliations (AFL-CIO, Change to Win) with member counts |
| `UnionFilters` | Name, affiliation, sector, state, min members, has employers |
| `UnionResultsTable` | Tabular results |
| `AffiliationTree` | 3-level lazy expand: Affiliation > State > Local (chevron toggle) |
| `useUnionsState` | URL-synced filters |

**Profile page:**

| Component | Role |
|-----------|------|
| `UnionProfilePage` | Detail view by `fnum` |
| `UnionProfileHeader` | Name, affiliation abbreviation, member/local counts |
| `MembershipSection` | Membership trends |
| `OrganizingCapacitySection` | Organizing staff/resources |
| `UnionElectionsSection` | Recent NLRB election results |
| `UnionFinancialsSection` | LM form financial data |
| `SisterLocalsSection` | Affiliated local unions |
| `ExpansionTargetsSection` | Potential organizing targets (links to Targets page) |
| `UnionEmployersTable` | Employers under contract |

### 6. Research (`features/research/`, 10 files)

AI-powered deep research on individual employers.

| Component | Role |
|-----------|------|
| `ResearchPage` | Browse past runs with status/name filters (20/page) |
| `ResearchResultPage` | View completed dossier, polls status every 2s while running |
| `ResearchFilters` | Status (pending/running/completed/failed), employer search |
| `ResearchRunsTable` | Past runs with timestamps, status, cost |
| `NewResearchModal` | Form to start new research (employer_id or name) |
| `DossierHeader` | Run metadata header |
| `DossierSection` | 7-section organized fact display |
| `FactRow` | Individual fact with source + confidence |
| `ActionLog` | Timeline of research agent steps |
| `useResearchState` | URL-synced filters |

### 7. Admin (`features/admin/`, 8 files)

Admin-only dashboard (role-gated).

| Component | Role |
|-----------|------|
| `SettingsPage` | Dashboard entry point |
| `HealthStatusCard` | API/DB status, response times (polls every 30s) |
| `PlatformStatsCard` | Employer counts, total sources |
| `DataFreshnessCard` | Source update dates, staleness flags |
| `MatchQualityCard` | Confidence distributions |
| `MatchReviewCard` | Pending user-submitted flags |
| `RefreshActionsCard` | Trigger MV/data refreshes |
| `UserRegistrationCard` | Add/remove users, manage roles |

---

## Shared Components (`shared/components/`)

| Component | Purpose |
|-----------|---------|
| `Layout` | Root layout: NavBar + Breadcrumbs + `<Outlet />` |
| `NavBar` | Dark espresso masthead, links + logout |
| `ProtectedRoute` | Auth guard, redirects to `/login` |
| `Breadcrumbs` | Navigation trail (hidden on search hero) |
| `ErrorBoundary` | Class component catching render errors |
| `ErrorPage` | Error fallback with retry button |
| `NotFound` | 404 page |
| `PageSkeleton` | Loading skeletons (5 variants: search, profile, targets, unions, research) |
| `CollapsibleCard` | Reusable expandable card |
| `ConfidenceDots` | Visual match confidence indicator |
| `HelpSection` | Collapsible help text |

## UI Primitives (`components/ui/`, shadcn-style)

`Card` | `Button` | `Input` | `Label` | `Badge` | `Select` | `Skeleton`

Built with `class-variance-authority` + Tailwind.

---

## API Layer (`shared/api/`, 30+ hooks)

**Client** (`client.js`): fetch wrapper with JWT injection, auto-logout on 401. Methods: `.get()`, `.post()`, `.put()`, `.delete()`.

| File | Key Hooks |
|------|-----------|
| `employers.js` | `useEmployerSearch`, `useEmployerAutocomplete` |
| `profile.js` | `useEmployerProfile`, `useEmployerUnifiedDetail`, `useScorecardDetail`, `useEmployerComparables`, `useEmployerWhd`, `useEmployerCorporate`, `useEmployerDataSources`, `useEmployerMatches`, `useEmployerFlags`, `useFlagEmployer` |
| `targets.js` | `useNonUnionTargets`, `useTargetStats`, `useTargetDetail`, `useTargetScorecard`, `useTargetScorecardDetail` |
| `unions.js` | `useUnionSearch`, `useNationalUnions`, `useUnionDetail`, `useUnionEmployers`, `useNationalUnionDetail` |
| `research.js` | `useStartResearch`, `useResearchStatus`, `useResearchResult`, `useResearchRuns` |
| `lookups.js` | `useStates`, `useNaicsSectors` (staleTime: Infinity) |
| `admin.js` | `useSystemHealth`, `usePlatformStats`, `useDataFreshness`, `useScoreVersions`, `useMatchQuality`, `useMatchReview` |

---

## State Management

**1 Zustand store** (`authStore`) for auth state (token, user, isAuthenticated, isAdmin).

**4 URL-synced state hooks** (all use `useSearchParams()`, reset page on filter change):

- `useSearchState` — search page filters
- `useTargetsState` — targets page filters + sort/order
- `useUnionsState` — unions page filters
- `useResearchState` — research page filters

---

## Visual Theme: "Aged Broadsheet"

Warm editorial aesthetic inspired by NYT/ProPublica data journalism.

### Core Palette

| Element | Value | Name |
|---------|-------|------|
| Background | `#f5f0e8` | Warm parchment |
| Cards | `#faf6ef` | Cream stock |
| Nav masthead | `#2c2418` | Dark espresso |
| Primary accent | `#1a6b5a` | Editorial teal |
| Secondary | `#ede7db` | Warm linen |
| Copper highlights | `#c78c4e` | Active nav, gold tiers |
| Destructive | `#c23a22` | Brick red |
| Border | `#d9cebb` | Parchment edge |

### Extended Palette

- Lake blue: `#3a6b8c` (info states, NLRB badges)
- Forest green: `#3a7d44` (success, fresh, high quality)
- Saddle brown: `#8b5e3c` (WHD badges)
- Dusty purple: `#6b5b8a` (SEC badges)

### Typography

- Headlines: Source Serif 4 (Google Fonts) via `.font-editorial`
- Body: Inter
- Page titles: `font-editorial text-3xl font-bold`
- Card titles: `font-editorial text-xl font-semibold`
- Table headers: `text-xs font-medium uppercase tracking-wider`

### Tier Badge Colors

| Tier | Style |
|------|-------|
| Priority | Dark espresso bg `#2c2418`, cream text, copper left-border |
| Strong | Teal bg `#1a6b5a`, cream text |
| Promising | Copper tint `#c78c4e/20`, dark text |
| Moderate | Linen bg `#ede7db`, dark text |
| Low | Parchment bg `#f5f0e8`, muted text |

### Source Badge Colors

| Source | Color |
|--------|-------|
| F7 | `#2c2418` (espresso) |
| OSHA | `#c23a22` (brick red) |
| NLRB | `#3a6b8c` (lake blue) |
| WHD | `#8b5e3c` (saddle brown) |
| SAM | `#1a6b5a` (teal) |
| SEC | `#6b5b8a` (dusty purple) |
| BMF | `#c78c4e` (copper) |
| VR | `#3a7d44` (forest green) |

### Score/Signal Colors

- High (7+ or 80+): Brick red `#c23a22`
- Medium (4-6 or 50-79): Copper `#c78c4e`
- Low (<4 or <50): Warm stone `#d9cebb`

---

## Component Tree

```
App
└── ProtectedRoute -> Layout
    ├── NavBar (dark espresso masthead)
    ├── Breadcrumbs
    └── <Outlet>
        ├── SearchPage
        │   ├── SearchBar + SearchFilters
        │   └── ResultsTable | SearchResultCard[]
        ├── EmployerProfilePage
        │   ├── ProfileHeader (tier badge)
        │   ├── Tabs: Basic | Scorecard | Research
        │   └── [20 detail cards/sections]
        ├── TargetsPage
        │   ├── TargetStats (tier distribution)
        │   └── TargetsFilters + TargetsTable
        ├── UnionsPage
        │   ├── NationalUnionsSummary
        │   └── UnionResultsTable | AffiliationTree
        ├── UnionProfilePage
        │   └── [8 detail sections]
        ├── ResearchPage / ResearchResultPage
        │   └── DossierSection + FactRow + ActionLog
        └── SettingsPage
            └── [8 admin cards]
```

---

## Key Patterns

- **URL-synced state**: All list pages store filters in URL query params (bookmarkable, shareable, back-button friendly)
- **Lazy loading**: All pages use `React.lazy()` + `Suspense` with skeleton fallbacks
- **Conditional queries**: Hooks accept `enabled` param to defer API calls until dependencies load
- **Dual ID routing**: F7 hex IDs vs prefixed IDs (NLRB-, VR-, etc.) route to different API endpoints
- **Named exports only**: No default exports anywhere
- **CollapsibleCard pattern**: Profile detail cards expand/collapse independently
- **Pagination**: Page resets to 1 on filter change, `placeholderData` keeps previous results during transitions
- **Number formatting**: `.toLocaleString()` for numbers, em-dash for null values

---

## API Response Shape Reference

These shapes caused bugs during initial integration -- always verify actual API responses:

| Endpoint | Shape |
|----------|-------|
| `/api/health` | `{ status, db: true/false }` |
| `/api/stats` | `{ total_scorecard_rows, match_counts_by_source: [{source_system, match_count}] }` |
| `/api/system/data-freshness` | `{ sources: [{source_name, row_count, latest_record_date, stale}] }` |
| `/api/admin/match-quality` | Uses `total_match_rows`, `source_system`, `total_rows`, `confidence_band` |
| `/api/admin/match-review` | Matches have `evidence.target_name`, `source_system`, `confidence_score` |
| `/api/unions/national` | `{ national_unions: [...] }` (not flat array) |
| `/api/unions/{fnum}/employers` | `{ employers: [...] }` (not flat array) |
| `/api/unions/search` | Unions have `display_name`, `f7_employer_count`, `f7_total_workers` |
| `/api/lookups/sectors` | `{ sectors: [{sector_code, sector_name, union_count}] }` |

Sister locals have `union_name` + `local_number` (separate fields, no `display_name`).

---

## Test Structure

**172 tests across 26 files, all passing.**

- Framework: Vitest + React Testing Library + jsdom
- Setup: `__tests__/setup.js` loads `@testing-library/jest-dom`
- Mocking: `vi.mock('@/shared/api/...')` for API hooks
- Wrapping: `QueryClientProvider` + `MemoryRouter` for all component tests
- Auth mocking: `useAuthStore.mockImplementation((selector) => selector(state))`
- Color assertions: Use `container.innerHTML.includes('bg-[#hex]')` (jsdom bracket escaping issues)

| Test File | Coverage |
|-----------|----------|
| `LoginPage.test.jsx` | Login form, error handling |
| `SearchPage.test.jsx` | Search, filters, pagination, view toggle |
| `SearchBar.test.jsx` | Search input, autocomplete |
| `SearchFilters.test.jsx` | Filter sidebar, state sync |
| `ResultsTable.test.jsx` | Table rendering, sorting |
| `SearchEnhancements.test.jsx` | Search feature suite |
| `EmployerProfilePage.test.jsx` | Profile routing (F7 vs non-F7) |
| `ProfileCards.test.jsx` | Individual profile card components |
| `DataProvenanceCard.test.jsx` | Data source metadata |
| `ResearchInsightsCard.test.jsx` | Research enhancements |
| `ScorecardSection.test.jsx` | Scorecard factors |
| `TargetsPage.test.jsx` | Targets listing, stats |
| `TargetsTable.test.jsx` | Target table rendering |
| `UnionsPage.test.jsx` | Union search, tree toggle |
| `UnionProfilePage.test.jsx` | Union detail page |
| `AffiliationTree.test.jsx` | Hierarchy tree expansion |
| `ResearchPage.test.jsx` | Research runs list |
| `ResearchResult.test.jsx` | Dossier rendering |
| `SettingsPage.test.jsx` | Admin access control |
| `MatchReviewCard.test.jsx` | Pending flags |
| `NavBar.test.jsx` | Navigation, logout |
| `Layout.test.jsx` | Layout structure |
| `ProtectedRoute.test.jsx` | Auth guard |
| `ErrorBoundary.test.jsx` | Error handling |
| `profile-hooks.test.js` | API hook integration |

---

## Summary

- **~80+ components** across 7 feature modules
- **30+ API hooks** (TanStack Query)
- **9 pages** (1 public, 8 protected)
- **172 tests** (26 files, 0 failures)
- **7 UI primitives** (shadcn-style)
- **1 Zustand store** + **4 URL-synced state hooks**
