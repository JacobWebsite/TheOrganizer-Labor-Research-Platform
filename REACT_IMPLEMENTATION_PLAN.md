# React Implementation Plan — The Organizer Platform
## Decided in Platform Redesign Interview | February 20, 2026

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Framework** | React + Vite | Fresh build; Vite is fast and modern. Old JS files kept as API reference only. |
| **Styling** | Tailwind CSS + shadcn/ui | Utility-first CSS + pre-built professional components. Customizable to match brand. |
| **State Management** | Zustand | Lightweight, organized into stores per feature area. Simpler than Redux, more structured than Context. |
| **Data Fetching** | TanStack Query + thin API wrapper | Automatic caching, loading states, retry, background refresh. Wrapper handles auth tokens and error formatting. |
| **Tables** | TanStack Table + shadcn/ui styling | TanStack for behavior (sort, paginate, select, filter). shadcn/ui for visual styling. |
| **Routing** | React Router | Full URL state for searches — bookmarkable, shareable. |
| **Testing** | Vitest + React Testing Library | Unit + integration tests. Written as each component is built. No E2E tests. |
| **Deployment** | Separate servers via Docker Compose | nginx serves React static files, proxies /api/ to FastAPI on port 8001. Frontend stays up even if API crashes. |

---

## State Management Stores (Zustand)

| Store | What It Tracks |
|-------|---------------|
| **Auth Store** | Login status, user role (admin/read), JWT token |
| **Search Store** | Current query, active filters, results, page number, sort order |
| **Profile Store** | Currently viewed employer or union |
| **Flags Store** | Flagged employers, notes, flag types |
| **Future stores** | Saved searches, campaign tracking, notifications |

---

## API Client Architecture

### Thin Wrapper Layer
- Base URL configuration
- Automatic auth token attachment to every request
- Consistent error formatting (API errors → user-friendly messages)
- Response parsing

### TanStack Query Layer
- One query definition per data type:
  - `useEmployerProfile(id)` — fetches and caches employer profile
  - `useUnionProfile(fNum)` — fetches and caches union profile
  - `useSearchResults(query, filters)` — fetches search results
  - `useScorecardList(filters)` — fetches scored employers
  - `useDataFreshness()` — fetches admin data freshness
- Automatic loading states, error states, retry logic
- Cache: previously visited pages load instantly
- Background refresh: stale data gets updated silently

---

## Code Structure

```
src/
├── features/
│   ├── search/           # Search bar, autocomplete, results page
│   ├── employer-profile/ # Employer profile page, all 9 cards
│   ├── union-explorer/   # Union search, affiliation, union profile
│   ├── scorecard/        # Targets view, bulk operations
│   └── admin/            # User mgmt, weights, freshness, review queue
├── shared/
│   ├── components/       # Score badge, source badges, nav bar, error states
│   ├── hooks/            # Shared custom hooks
│   ├── api/              # API wrapper + TanStack Query definitions
│   └── stores/           # Zustand stores
└── App.jsx               # Root component, routing, layout
```

---

## Build Order

| Phase | Feature | Description | Milestone |
|-------|---------|-------------|-----------|
| **1** | Layout shell | Nav bar, routing, login, error handling, loading states | App skeleton works |
| **2** | Search page | Search bar, autocomplete, results table/cards, filters, URL state | Users can find employers |
| **3** | Employer profile | Header, 9 collapsible cards, score display, match confidence, flag button, report bad match | **Core product is usable** → Score validation happens here |
| **4** | Targets/Scorecard | Pre-filtered search (non-union, scored), bulk CSV export, comparison view | Organizers can browse targets |
| **5** | Union explorer | Union search, affiliation page, union profile, hierarchy view, expansion targets | Research staff feature complete |
| **6** | Admin panel | Weight config, data freshness, match review queue, user management, system health | Platform is manageable |

**Key milestone:** After Phase 3, the search → profile flow works end-to-end. This is where score validation happens — real scores on real profile pages, checked against organizing reality.

---

## Testing Strategy

| Type | Scope | Tools |
|------|-------|-------|
| **Unit tests** | Individual components render correctly | Vitest + React Testing Library |
| **Integration tests** | Components work together (search → results, profile loads all cards) | Vitest + React Testing Library |
| **Backend tests** | API endpoints return correct data | pytest (existing 456 tests) |

Tests written alongside each component, not after the fact. Each feature folder contains its own `__tests__/` directory.

---

## Deployment Architecture

### Development
```
Terminal 1: py -m uvicorn api.main:app --reload --port 8001  (FastAPI)
Terminal 2: npm run dev                                       (React on port 5173)
```
React dev server proxies /api/ calls to port 8001 automatically.

### Production (Docker Compose)
```
┌─────────────────────────────────────────┐
│  nginx (port 8080)                       │
│  ├── /          → serves React static    │
│  └── /api/*     → proxies to FastAPI     │
├─────────────────────────────────────────┤
│  FastAPI (port 8001)                     │
│  └── connects to PostgreSQL              │
├─────────────────────────────────────────┤
│  PostgreSQL 17 (port 5432)               │
│  └── olms_multiyear database             │
└─────────────────────────────────────────┘
```

---

## Key shadcn/ui Components to Use

| Feature | Components |
|---------|-----------|
| **Navigation** | NavigationMenu, Breadcrumb |
| **Search** | Input, Command (for autocomplete), Badge (source badges) |
| **Tables** | Table (styling), combined with TanStack Table (behavior) |
| **Employer Profile** | Card, Collapsible, Badge, Tabs, Tooltip |
| **Score Display** | Badge (tier colors), Progress (factor bars) |
| **Forms/Filters** | Select, Input, Checkbox, Popover, Slider |
| **Feedback** | Alert, Toast (notifications), Dialog (confirmations) |
| **Admin** | Table, Card, Switch, Label, Separator |
