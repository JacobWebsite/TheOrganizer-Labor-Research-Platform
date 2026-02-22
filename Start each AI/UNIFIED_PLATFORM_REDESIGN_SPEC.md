# The Organizer — Complete Platform Redesign Specification
## Unified Reference Document | February 20, 2026
### For: Claude Code, Codex, Gemini — Multi-AI Implementation

**Purpose:** This is the single source of truth for all platform redesign decisions. It merges and reconciles the Platform Redesign Interview, Scoring Specification, React Implementation Plan, Platform Help Copy, and the Addendum into one document. When in doubt, this document governs.

**How this was built:** An extended interview process covered every aspect of the platform — scoring logic, data quality, tech stack, visual design, page layouts, copy, security, and future features. Earlier decisions from the interview were refined and sometimes superseded by later, more specific decisions. This document reflects the final state.

---

# TABLE OF CONTENTS

1. Foundational Decisions
2. Scoring System (8 Factors)
3. Data Quality Decisions
4. Master Employer List Architecture
5. React Implementation Plan
6. Visual Design
7. Specific Page Designs
8. Content, Copy & Help System
9. Edge Cases & Special Scenarios
10. Security & Authentication
11. OLMS Data on Union Profiles
12. Deep Dive Tool (Workforce Demographics + Web Scraper)
12B. Additional Data Features (Union Scraper, Employee Estimation)
13. IRS Business Master File
14. Public Sector Adaptation
15. Permission Levels & Roles
16. Claude Code Task List
17. Documents Produced

---

# 1. FOUNDATIONAL DECISIONS

| Topic | Decision |
|-------|----------|
| **Audience** | Mixed: field organizers, research/strategy staff, and union leadership |
| **Current Status** | Internal tool (solo user), multi-user planned. Start small, design for growth. |
| **North Star** | Finding the right employers to organize — the search → scorecard → profile flow |
| **Core Workflows** | 1) Research a specific employer, 2) Explore sector → non-union employers → deep dive → scorecard, 3) Check union trends/finances |
| **Platform Type** | Desktop only (no mobile) |
| **Visual Direction** | Professional/corporate + modern hybrid (Bloomberg meets Linear) |

**Interview completion status:** The original Platform Redesign Interview (PLATFORM_REDESIGN_INTERVIEW.md) listed 8 remaining topics at the end. ALL 8 have been fully resolved in subsequent sessions and are incorporated into this document: Visual Design (Section 6), Data Quality (Section 3), Scoring Logic (Section 2), React Implementation (Section 5), Remaining Roadmap Phases (Section 16), Specific Page Designs (Section 7), Edge Cases (Section 9), Content & Copy (Section 8). No outstanding interview topics remain.

---

# 2. SCORING SYSTEM

## Overview

Every employer gets a score from 0 to 10 that answers: **"How promising does this employer look as an organizing target?"**

The score is built from 8 separate factors. Each factor gives its own 0-10 rating. If a factor has no data for an employer, it gets skipped entirely — it doesn't count as zero. This is the "signal-strength" approach.

The final score is a **weighted average** of all factors that have data, with weights reflecting organizing strategy priorities.

## The 8 Factors

### Factor 1: Union Proximity (Weight: 3x)

| Relationship | Score |
|-------------|-------|
| 2+ unionized siblings (same parent company) | 10 |
| 1 unionized sibling OR corporate family connection | 5 |
| No relationship | 0 |

- Purely structural — either the connection exists or it doesn't
- Corporate family = related through ownership chain but not same company; treated same as 1 sibling
- No data → factor skipped entirely

**Rationale:** The most powerful organizing signal. Sibling unions mean proven templates, known playbooks, existing worker connections, and institutional knowledge. This is ranked #1 in importance.

### Factor 2: Employer Size (Weight: 3x)

| Employees | Score |
|-----------|-------|
| Under 15 | 0 |
| 15 → 500 | Ramps linearly from 0 to 10 |
| 500+ | 10 (plateaus) |

- Bigger is never worse
- Under 15 scored at 0 — not realistic targets
- No data → factor skipped entirely

**Rationale:** Size determines viability. Under 15 isn't worth the campaign cost. The sweet spot starts around 50 but bigger employers are never a downgrade — they represent larger potential membership gains.

### Factor 3: NLRB Activity (Weight: 3x)

| Element | Decision |
|---------|----------|
| **Split** | 70% nearby momentum / 30% own history |
| **Nearby Definition** | Within 25 miles AND similar industry |
| **Wins** | Score positive |
| **Losses** | Score NEGATIVE (penalty — a recent loss is a red flag) |
| **Time Decay** | 7-year half-life on all election data |
| **Latest Election** | Most recent election at the same employer dominates |
| **No Data** | Factor skipped entirely |

**Rationale:** What's happening around an employer — nearby wins at similar workplaces — is a better predictor of future success than the employer's own history. Own history is as likely to be negative (losses = cold shop) as positive. The "hot shop effect" is the main signal.

### Factor 4: Government Contracts (Weight: 2x)

| Contract Levels | Score |
|----------------|-------|
| No contracts | 0 |
| Federal only | 4 |
| State only | 6 |
| City/local only | 7 |
| Any two levels | 8 |
| All three levels | 10 |

- Dollar value = tiebreaker within tiers only (bigger contracts nudge up slightly, can't jump tiers)
- No time decay — a current contract is a current contract
- Data sources: USASpending (federal) + SAM.gov (federal registry) + NY Open Book (state) + NYC Open Data (city)
- No data → factor skipped entirely

**Rationale:** Government contracts give unions political leverage. State and local contracts weighted higher than federal because state/city officials are more responsive to labor pressure under current political conditions.

### Factor 5: Industry Growth (Weight: 2x)

| Element | Decision |
|---------|----------|
| **Method** | Linear mapping from BLS 10-year industry projections onto 0-10 |
| **Scale** | Fastest growing industry in dataset = 10, fastest shrinking = 0, everything else proportional |
| **Data Level** | Industry-level only (not individual employer financials) |
| **Future** | Blend in employer-specific revenue/employee data when estimation tool is built |
| **No NAICS Code** | Factor skipped entirely (~15% of employers) |

**Rationale:** Strategic resource allocation. Organizing in a growing industry means a growing membership base for years. A dying industry means a shrinking local even after a win.

### Factor 6: Statistical Similarity (Weight: 2x)

| Element | Decision |
|---------|----------|
| **Method** | Combination of how many comparable unionized employers are found AND how close the best matches are |
| **Scope** | Only applies to employers with NO corporate/sibling union connection (otherwise Factor 1 covers them) |
| **Engine** | Uses existing Gower distance comparables engine |
| **No Data** | Factor skipped entirely |

**Rationale:** Even without corporate connections, patterns matter. If every nursing home that looks like this one has a union, that's useful intelligence. Separated from Factor 1 because it's inference rather than known structural relationships.

### Factor 7: OSHA Safety Violations (Weight: 1x)

| Element | Decision |
|---------|----------|
| **Method** | Industry-normalized violation count (compared to peers in same sector) |
| **Time Decay** | 5-year half-life — a violation loses half its weight every 5 years |
| **Severity Bonus** | +1 point for willful or repeat violations (capped at 10) |
| **No Data** | Factor skipped entirely |

**Rationale:** Workers at dangerous workplaces have a concrete, personal reason to want a union. Safety is one of the strongest motivators — but it's ranked lower in weight because grievances alone don't make campaigns winnable.

### Factor 8: WHD Wage Theft (Weight: 1x)

| Cases | Score |
|-------|-------|
| 0 cases | 0 |
| 1 case | 5 |
| 2-3 cases | 7 |
| 4+ cases | 10 |

- Dollar amounts displayed on profile for context but do NOT affect the score
- 5-year half-life (same as OSHA)
- No data → factor skipped entirely (~84% of employers have no WHD data)

**Rationale:** Wage theft is near-binary — the signal is "they got caught" vs "no record." Repeat violations are the strongest signal. Dollar amounts are unreliable for comparison across industries.

## Factor Weight Summary

| Tier | Weight | Factors | Share of Final Score |
|------|--------|---------|---------------------|
| **Top (3x)** | 3x | Union Proximity, Employer Size, NLRB Activity | ~53% |
| **Middle (2x)** | 2x | Gov Contracts, Industry Growth, Statistical Similarity | ~35% |
| **Bottom (1x)** | 1x | OSHA Safety, WHD Wage Theft | ~12% |

**Admin-configurable:** All weights can be changed through the admin settings panel. No guardrails — full flexibility.

## Design Philosophy

The weight ranking reflects how experienced organizers actually prioritize:
1. **Strategic positioning** (Is this a smart target?) — Union Proximity, Employer Size, NLRB Activity
2. **Leverage** (Can we apply pressure?) — Gov Contracts, Industry Growth, Statistical Similarity
3. **Worker grievances** (Are workers motivated?) — OSHA Safety, WHD Wage Theft

Grievances make workers angry. Strategy makes campaigns winnable. The scoring system reflects that distinction.

## How the Final Score is Calculated

1. Calculate each factor's 0-10 score
2. Skip any factor with no data (signal-strength approach)
3. Multiply each score by its weight (1x, 2x, or 3x)
4. Sum all weighted scores
5. Divide by total weight of factors that had data
6. Result: weighted average from 0-10

**Example:** An employer has data for OSHA (score 6, weight 1x), NLRB (score 8, weight 3x), Gov Contracts (score 7, weight 2x), and Employer Size (score 10, weight 3x).
- Weighted scores: (6×1) + (8×3) + (7×2) + (10×3) = 6 + 24 + 14 + 30 = 74
- Total weight: 1 + 3 + 2 + 3 = 9
- Final score: 74 ÷ 9 = **8.2**

## Tier Labels (Percentile-Based)

| Tier | Percentile | Approx Count (of 146,863) |
|------|-----------|---------------------------|
| **Priority** | Top 3% | ~4,400 |
| **Strong** | Next 12% | ~17,600 |
| **Promising** | Next 25% | ~36,700 |
| **Moderate** | Next 35% | ~51,400 |
| **Low** | Bottom 25% | ~36,700 |

- Percentile-based: tiers recalculate on every data refresh
- No user notifications when tiers shift due to other employers' scores changing
- "Priority" is exclusive by design — only ~4,400 employers earn it

## Comparables Engine

The Gower distance engine shares the SAME employer universe as the scorecard. Comparables appear on employer profiles. When viewing a union employer, comparables help identify expansion targets. Comparables are display-only — they inform strategy but do not directly affect the score (that's what Factor 6 does).

---

# 3. DATA QUALITY DECISIONS

| Topic | Decision |
|-------|----------|
| **Search duplicates** | Database-level problem. UI merges into one result per canonical employer with source badges [F7] [OSHA] [NLRB] etc. |
| **Union linkage gaps** | Show match confidence per source on profiles. Investigate specific examples in Claude Code. |
| **Score validation** | After React frontend is built. Generate test set of 10-15 employers spanning tiers/industries/sizes. Validate on real profile pages. |
| **Wrong matches** | Show confidence dots on profiles. Users can flag "Something Looks Wrong" → admin review queue. No manual review gate before matches go live. |
| **Propensity Model B** | Hidden from users (accuracy 0.53 — barely better than a coin flip). Model A (0.72) is decent. Improve Model B over time with more non-union training data. |
| **GLEIF data** | Leave 12GB in place for now. Only `gleif_us_entities` and `gleif_ownership_links` are used. Full BODS dataset unused. |
| **Legacy table sync** | Already handled in Phase B. Rebuild script exists (`scripts/maintenance/rebuild_legacy_tables.py`). |
| **166 missing unions** | Covering 61,743 workers. Get top 10 by worker count from Claude Code. 29 already resolved via crosswalk remaps. Case 12590 (CWA District 7) deferred. |

### Pending MV Refresh Items
These are code-fixed but waiting on a materialized view refresh to take effect:
1. **NLRB time-decay** — 7-year half-life now implemented in `build_unified_scorecard.py`
2. **NLRB flag/score mismatch** — `has_nlrb` flag now uses canonical score path
3. **BLS financial scoring bug** — no-data no longer scores higher than confirmed stagnation

### Fixed Issues (For Reference)
- F-7 orphan problem (zero orphaned relationships confirmed)
- Scorecard coverage expanded to all 146,863 F-7 employers
- NLRB confidence scale normalized to 0.0-1.0
- Legacy scorecard detail 404 fixed
- Match quality dashboard inflated numbers fixed
- Corporate hierarchy endpoints fixed (7 bugs)
- PostgreSQL planner stats refreshed
- Splink name-similarity floor enforced (0.70)

---

# 4. MASTER EMPLOYER LIST ARCHITECTURE

## The Problem
F-7 list contains only employers with union contracts (current or historical). The platform's purpose is finding NON-union employers to organize. Without a master list, the best organizing targets — employers with OSHA violations + NLRB activity + government contracts but NO union — are invisible.

## The Solution
Build a living master list that grows as data connections accumulate:
- Start with 67,552 current F-7 employers (historical excluded from search/scoring)
- Add employers from government databases even if not in F-7
- Each new data source can connect to entries created by ANY previous source
- Employers surface as targets when enough data exists to score meaningfully

## Seeding Strategy

| Wave | Source | Records | Value |
|------|--------|---------|-------|
| **Wave 1** | SAM.gov + Mergent Intellect | 826K + 56K | Clean data, employee counts, NAICS, government contracts, revenue |
| **Wave 2** | NLRB participants | TBD | After data quality cleanup |
| **Wave 3** | OSHA establishments | Filtered | 2+ violations or serious violations only |

## Visibility Rules
- Minimum 2 scoring factors with data to surface as a target
- Confidence indicator: "Score based on X of 8 factors"
- Organizers can filter by confidence level
- Non-F-7 employers get "No Known Union" badge vs F-7 "Union Contract" badge

## Timing
Built in parallel with React frontend. F-7 employers work first, master list employers added as connections accumulate. Design schema now, populate later.

## Conflicting Data Across Sources
- Employee counts differ → profile shows a range (e.g. "150-300 employees"), scoring uses the average
- Address conflicts → show primary with "also found at" for alternates

---

# 5. REACT IMPLEMENTATION PLAN

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Framework** | React + Vite | Fresh build; Vite is fast and modern. Old JS files kept as API reference only. |
| **Styling** | Tailwind CSS + shadcn/ui | Utility-first CSS + pre-built professional components. Customizable to match brand. |
| **State Management** | Zustand | Lightweight, organized into stores per feature area. Simpler than Redux, more structured than Context. |
| **Data Fetching** | TanStack Query + thin API wrapper | Automatic caching, loading states, retry, background refresh. Wrapper handles auth tokens and error formatting. |
| **Tables** | TanStack Table + shadcn/ui styling | TanStack for behavior (sort, paginate, select, filter). shadcn/ui for visual styling. |
| **Routing** | React Router | Full URL state for searches — bookmarkable, shareable. `/search?q=hospital&state=NY&tier=priority` |
| **Testing** | Vitest + React Testing Library | Unit + integration tests. Written as each component is built. No E2E tests. |
| **Deployment** | Separate servers via Docker Compose | nginx serves React static files, proxies /api/ to FastAPI on port 8001. Frontend stays up even if API crashes. |

## API Strategy

| Choice | Decision |
|--------|----------|
| **Existing endpoints** | Keep all existing endpoints. Add new ones as needed. Do NOT remove. |
| **Profile pattern** | One big aggregated endpoint per page — returns ALL data for employer/union profile in one call |
| **API cleanup** | Consolidate where possible, preserve backward compatibility |

## State Management Stores (Zustand)

| Store | What It Tracks |
|-------|---------------|
| **Auth Store** | Login status, user role (viewer/researcher/admin), JWT token |
| **Search Store** | Current query, active filters, results, page number, sort order |
| **Profile Store** | Currently viewed employer or union |
| **Flags Store** | Flagged employers, notes, flag types |
| **Future stores** | Saved searches, campaign tracking, notifications |

## API Client Architecture

### Thin Wrapper Layer
- Base URL configuration
- Automatic auth token attachment to every request
- Consistent error formatting (API errors → user-friendly messages)
- Response parsing

### TanStack Query Layer
One query definition per data type:
- `useEmployerProfile(id)` — fetches and caches employer profile
- `useUnionProfile(fNum)` — fetches and caches union profile
- `useSearchResults(query, filters)` — fetches search results
- `useScorecardList(filters)` — fetches scored employers
- `useDataFreshness()` — fetches admin data freshness

Benefits: automatic loading states, error states, retry logic, cache (previously visited pages load instantly), background refresh (stale data updated silently).

## Code Structure

```
src/
├── features/
│   ├── search/           # Search bar, autocomplete, results page
│   ├── employer-profile/ # Employer profile page, all cards
│   ├── union-explorer/   # Union search, hierarchy, union profile
│   ├── scorecard/        # Targets view, bulk operations
│   └── admin/            # User mgmt, weights, freshness, review queue
├── shared/
│   ├── components/       # Score badge, source badges, nav bar, error states
│   ├── hooks/            # Shared custom hooks
│   ├── api/              # API wrapper + TanStack Query definitions
│   └── stores/           # Zustand stores
└── App.jsx               # Root component, routing, layout
```

## Build Order

| Phase | Feature | Description | Milestone |
|-------|---------|-------------|-----------|
| **1** | Layout shell | Nav bar, routing, login, error handling, loading states | App skeleton works |
| **2** | Search page | Search bar, autocomplete, results table/cards, filters, URL state | Users can find employers |
| **3** | Employer profile | Header, score breakdown, all collapsible cards, flag/report buttons | **Core product usable → Score validation here** |
| **4** | Targets/Scorecard | Tier dashboard cards, pre-filtered table, bulk CSV export | Organizers can browse targets |
| **5** | Union explorer | Union search, hierarchy tree, union profiles with OLMS data | Research staff feature complete |
| **6** | Admin panel | Weight config, data freshness, match review queue, user management, system health | Platform is manageable |

**Key milestone:** After Phase 3, the search → profile flow works end-to-end. This is where score validation happens — real scores on real profile pages, checked against organizing reality.

## Testing Strategy

| Type | Scope | Tools |
|------|-------|-------|
| **Unit tests** | Individual components render correctly | Vitest + React Testing Library |
| **Integration tests** | Components work together (search → results, profile loads all cards) | Vitest + React Testing Library |
| **Backend tests** | API endpoints return correct data | pytest (existing ~456 tests) |

Tests written alongside each component, not after the fact. Each feature folder contains its own `__tests__/` directory.

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

---

# 6. VISUAL DESIGN

| Decision | Choice |
|----------|--------|
| **Overall feel** | Professional/corporate + modern hybrid (Bloomberg meets Linear) |
| **Mode** | Light only |
| **Base colors** | Charcoal/warm gray scale (#1c1917 → #fafaf9) |
| **Accent color** | True red #dc2626 (buttons, links, active states) |
| **Font** | Inter (shadcn/ui default — zero config, excellent screen readability) |
| **Density** | Standard (comfortable scanning, tables slightly tighter than profiles) |
| **Cards** | Light border + subtle shadow, square corners (sharp, data-serious) |
| **Icons** | Lucide (built into shadcn/ui) |
| **Confidence indicators** | Filled/empty dots ●●●○ (4 max) |
| **Navigation** | Top nav bar (horizontal, full page width), auto-hide on scroll |
| **Breadcrumbs** | Always visible: `Search > Memorial Hospital > OSHA Violations` |

## Tier Color Scale (Red Intensity)

| Tier | Color | Text |
|------|-------|------|
| **Priority** | #dc2626 (deep red) | White |
| **Strong** | #ef4444 (red) | White |
| **Promising** | #f87171 (light red) | Dark |
| **Moderate** | #fecaca (pale pink) | Dark red |
| **Low** | #fef2f2 (barely pink) | Dark red |

## Source Badge Styles (by match confidence)

| Confidence | Badge Style |
|-----------|-------------|
| High | Dark background (#1c1917), white text |
| Medium | Mid-gray background (#44403c), white text |
| Low | Light background (#f5f5f4), dark text, gray border |

## Loading & Error States

| State | Behavior |
|-------|----------|
| **Profile loading** | Skeleton screens (shadcn/ui Skeleton + TanStack Query states) |
| **Cached pages** | Load instantly on revisit |
| **Search autocomplete** | 300ms debounce + 3 character minimum |
| **Errors** | Friendly message with retry button. Non-technical, actionable. |
| **Empty cards** | Hidden entirely if no data. Source badges tell the story. |

---

# 7. SPECIFIC PAGE DESIGNS

## 7.1 Search Page

### Search Architecture
One universal search bar + advanced filters. The system handles different query types (employer name, city, union name) through the same interface. No separate search modes. **Kill the existing basic/fuzzy/normalized search split** — one search to rule them all.

### Navigation Architecture
Full pages replace all 10+ existing modal types. Employer and union profiles get dedicated pages with real URLs. No modals for content — modals only for confirmations and quick actions (flag, report).

### Before Searching
- Search-first (Google style): big centered search bar dominates the page
- Just the search bar — clean page, no stats or dashboards
- Placeholder text: "Search Employers"

### Autocomplete Behavior
- Hybrid: categorized suggestions while typing, full results on Enter
- Suggestions grouped: "Employers (5 results) | Unions (2 results)"
- Enter navigates to dedicated results page with search bar in header

### After Searching
- Search bar moves to top, results fill below
- Collapsible "Advanced Filters" panel (hidden by default, toggle button to expand)
- Active filters shown as removable chips

### Advanced Filters
- **State:** Dropdown
- **Industry:** NAICS code (start typing to see options)
- **Employee size:** Range (min/max)
- **Score tier:** Priority / Strong / Promising / Moderate / Low
- **Data sources:** "Has OSHA," "Has NLRB," etc.
- **Union status:** Has union / No union

### Results Display
- **Toggle:** Table view ↔ Card view (user picks preference)
- **Table columns:** Employer name (clickable), Industry, Location, Employee count, Union (if applicable), Score tier badge, Source badges
- **Card content:** Name + location + score + source badges + employee count
- **Pagination:** 25 results per page
- **Sorting:** Click any column header to sort. Click again to reverse.
- **URL state:** Full URL state: `/search?q=hospital&state=NY&tier=priority`. Bookmarkable, shareable.
- **Duplicate handling:** One merged result per canonical employer with source badges
- **Deep Dive badge:** "Deep Dive Available" indicator on profiles that have been researched

## 7.2 Employer Profile

### Header Area (Always Visible — Not Collapsible)
- Employer name, location (city/state), industry, employee count (range if sources disagree)
- Score number (0-10) + tier badge (color-coded)
- Union status ("No Known Union" or "Represented by SEIU Local 32BJ")
- Source coverage badges ([F-7] [OSHA] [NLRB] [WHD] [SAM] [SEC])
- Confidence dots per source (●●●○)
- **Action buttons:** Flag as Target, Compare Employers, Export Data, Something Looks Wrong

### Score Factor Breakdown (Always Visible — Below Header)
- 8-factor horizontal bar chart
- Each bar: factor name, weight label (3x/2x/1x), score 0-10
- Grayed-out factor with dash = no data for that factor

### Collapsible Cards (In Order — Hidden If No Data)
All collapsed by default. Card headers show summary so users know what's inside before expanding.

| # | Card | Collapsed Summary Example | Expanded Content |
|---|------|--------------------------|------------------|
| 1 | **Union Relationships** | "Represented by SEIU Local 32BJ" | Full union details, contract dates, bargaining unit info |
| 2 | **Financial Data** | "Revenue: $45M | 230 employees" | Revenue, employee count sources, financial details |
| 3 | **Corporate Hierarchy** | "Parent: HCA Healthcare (47 subsidiaries) \| 12 have unions" | Corporate tree, subsidiary details, sibling union status |
| 4 | **Comparables** | "5 comparable employers found \| 3 are unionized \| Avg score: 6.5" | Full comparable employer list with comparison metrics |
| 5 | **NLRB Election History** | "2 elections: 1 won, 1 lost \| 3 wins within 25mi" | Own history + nearby momentum detail. Link to deep NLRB view. |
| 6 | **Government Contracts** | "$3.4M across 7 contracts [FEDERAL] [STATE] [CITY]" | Individual contract details by level |
| 7 | **OSHA Safety Violations** | "OSHA Safety — 12 violations (HIGH risk)" | Full violation list: date, type, penalty, description. Sortable. |
| 8 | **WHD Wage Theft Cases** | "Wage Violations: YES \| $234K in backwages" | Case details, dates, backwages per case, workers affected |
| 9 | **Research Notes** | Flag icon + note count | Free text + flag type (Hot Target / Needs Research / Active Campaign / Follow Up / Dead End) + priority (High/Medium/Low). **Future:** Add assigned user + status tracking when multi-user launches. |

### High-Volume Cards
- Show 5 most recent records by default
- "Show more" button loads next batch
- Most recent first (aligns with time-decay scoring)

### Contact / Location Card
- City/state from F7, full addresses from OSHA establishments and SAM.gov
- Merged from available sources

### Deep Dive Results Section (Below All Cards)
- Only visible on profiles where a deep dive has been run
- Shows "Last researched: [date]" with option to re-run
- See Section 12 for full Deep Dive specification

### Layout
- Single column, scrolling page
- No sidebar, no tabs — simple vertical flow

## 7.3 Targets Page

### Layout
- **Tier summary dashboard cards at top:** Clickable, showing count per tier
  - Priority: 4,400 | Strong: 17,600 | Promising: 36,700 | Moderate: 51,400 | Low: 36,700
- **Visual summary bar + filter controls** for navigating between tiers
- **Filtered table below** (reuses search results table component)
- Pre-filtered to non-union employers, sorted by score descending
- Same table/card toggle as search results

### Bulk Operations
- Checkboxes on table rows
- **Export Data:** Download selected employers as CSV
- **Flag all:** Mark selected as targets for follow-up
- **Compare:** Side-by-side comparison table with highlighted differences across selected employers (scores, factors, sources)

### Saved Searches (Future Feature)
- Saves filter parameters + result snapshot at time of saving
- Shows what changed when revisited
- Optional notification rules: "Notify when new employers match" or "when tracked employer score changes"
- In-app notification badge only (no email for now)

## 7.4 Union Explorer

### Search & Browse
- Search bar at top for finding unions by name
- Browseable hierarchy tree below: Affiliation → National/International → Local
- Both supported: browse by affiliation parent AND search by employer connection

### Union Profile Header (Always Visible)
- Union name, abbreviation, affiliation
- Dues-paying member count (default display)
- Covered workers available on hover or in detail
- Number of employers, number of locals

### Union Profile Content (Below Header)

| # | Section | Content |
|---|---------|---------|
| 1 | **Relationship Map** | Expandable indented list (file explorer style): National → Locals → Employers. Employer names clickable to their profiles. |
| 2 | **Membership Trends** (NEW) | Sparkline chart showing year-over-year trend + actual yearly numbers below + covered workers vs dues-paying breakdown |
| 3 | **Financial Health** (NEW) | **Collapsed:** Health badge — Healthy (green) / Stable (yellow) / Declining (red). Formula: membership trend + net asset change + receipts/disbursements ratio — all three must align for Healthy or Declining, mixed signals = Stable. **Expanded:** Full breakdown table: revenue by source, expenses by category (organizing, admin, representation, etc.) |
| 4 | **Employer Connections** | Two views: grouped by local ("Local 32BJ: 47 employers") OR filterable flat list by state/industry/size |
| 5 | **Expansion Targets** | "Potential targets — non-union employers similar to ones this union already represents" using Gower distance comparables |

### Affiliation Page
When selecting an affiliation: overview stats at top (total members, locals count, financial health) + flat filterable list of all locals with key metrics.

### Hierarchy View
Nested list with indentation: national → districts → councils → locals. Grouped by hierarchy level + filterable by state, size, and financial health.

## 7.5 Admin Panel (Settings)

### Layout
Single scrolling dashboard with section headers.

### Section Order

| # | Section | Description |
|---|---------|-------------|
| 1 | **Score Weight Configuration** | Sliders for each factor's weight. Changes recalculate all scores immediately. |
| 2 | **Data Freshness Dashboard** | Last updated date per source. Stale data (>6 months) highlighted. Refresh buttons trigger new data pull. |
| 3 | **Match Review Queue** | User-flagged "Something Looks Wrong" items. Shows employer + data source + current confidence. Admin approves (dismiss flag) or rejects (unlink source). Also catches suspected misclassifications — labor organizations incorrectly listed as employers. Note: small organizations tied to OPEIU, IATSE, etc. may be legitimate staff unions (union staff unionizing), not misclassifications. |
| 4 | **System Health** | Database size, API response times (>2s = problem), error rates (should be near zero). |
| 5 | **User Management** | Add/remove users, assign roles (viewer/researcher/admin), view activity. |
| 6 | **MV Refresh** | Refresh materialized views (already exists). |
| 7 | **Match Quality Reports** | Match quality metrics (already exists). |

---

# 8. CONTENT, COPY & HELP SYSTEM

## Tone & Language
- **Professional neutral throughout** — factual, no spin, let the data speak
- **Organizing terminology in Targets section only** ("organizing targets," "campaign potential," "leverage")
- **Neutral business language elsewhere** ("employers," "score," "analysis," "assessment")

## Help System
- Collapsible **"How to read this page"** section at the top of each page
- **Collapsed by default** — doesn't take space unless user wants it
- One sentence per item (expanded to 2-3 sentences for complex items)
- Full help copy drafted for all 5 pages — see complete text below

## Labels & Buttons

| Element | Text |
|---------|------|
| Nav tabs | **Employers** \| **Targets** \| **Unions** \| **Settings** |
| Search placeholder | "Search Employers" |
| Flag button | "Flag as Target" |
| Report button | "Something Looks Wrong" |
| Export button | "Export Data" |
| Compare button | "Compare Employers" |
| Deep dive button | "Run Deep Dive" (or "Last researched: [date]" + "Re-run") |

## Empty States

| Context | Message |
|---------|---------|
| Search (no results) | "No results found. Try broadening your search or adjusting your filters." |
| Flagged targets (empty) | "Your target list is empty. Start by flagging employers from search results or the Targets page." |
| Match review (empty) | "All clear — no reported issues." |
| Empty cards | Hidden entirely — source badges tell the story of what data exists |
| No OSHA data | Card hidden. If user wonders: explained in "How to read this page" |

## Complete Help Section Copy — All Pages

### EMPLOYER PROFILE PAGE — "How to read this page"

**Score (0-10):**
This employer's overall organizing potential, calculated from up to 8 different factors. The score only uses factors where we actually have data — if we're missing information on a factor, it's skipped rather than counted against the employer. A score of 8.0 based on 7 factors is more reliable than an 8.0 based on 3 factors. The number of factors used is shown below the score.

**Tiers — what they mean and what to do with them:**
- **Priority (top 3%):** The strongest organizing targets in the entire database. These employers have multiple strong signals across strategic position, leverage, and worker conditions. Action: prioritize for active campaign planning and resource allocation.
- **Strong (next 12%):** Very promising targets with solid data across several factors. Action: worth detailed research and preliminary outreach assessment.
- **Promising (next 25%):** Good potential but may be missing data or have mixed signals. Action: monitor and investigate further — additional data could push them higher.
- **Moderate (next 35%):** Some positive signals but not enough to stand out. Action: keep on the radar but don't prioritize over higher-tier targets.
- **Low (bottom 25%):** Few organizing signals in the available data. Action: unlikely to be a strong target based on current information, but new data could change this.

**Factor bars:**
Each bar shows how this employer scored on one of 8 factors, rated 0-10. Factors are weighted by importance — (3x) factors matter three times as much as (1x) factors in the final score. A grayed-out factor with a dash means we have no data for that factor.

- **Union Proximity (3x):** Whether companies in the same corporate family already have unions. This is the strongest predictor of organizing success because it means the corporate parent has already dealt with unions elsewhere, and there may be existing relationships and momentum to build on.
- **Employer Size (3x):** Larger employers offer more impact per organizing campaign — more workers covered, more resources justified. Employers under 15 employees score zero because they're generally not realistic organizing targets.
- **NLRB Activity (3x):** A combination of nearby union election momentum (within 25 miles and similar industry) and this employer's own election history. Nearby wins are a strong signal. This employer's own past losses actually count as a negative because they suggest harder-than-average organizing conditions.
- **Gov Contracts (2x):** Federal, state, or city government contracts. Contractors face public accountability and regulatory requirements that create organizing leverage. Having contracts at multiple levels (e.g. both federal and city) scores higher than just one.
- **Industry Growth (2x):** How fast this employer's industry is projected to grow over the next 10 years, based on Bureau of Labor Statistics data. Faster-growing industries mean more workers entering the field and more opportunity.
- **Statistical Similarity (2x):** How closely this employer resembles other employers that already have unions, based on size, industry, location, and other characteristics. A high score means "employers like this one tend to have unions."
- **OSHA Safety (1x):** Workplace safety violations from federal OSHA inspections. More violations and more serious violations (willful, repeat) score higher. Violations fade in importance over time — recent ones count more than old ones.
- **WHD Wage Theft (1x):** Wage and hour violations from Department of Labor Wage and Hour Division investigations. Includes back wages owed, overtime violations, and minimum wage violations. More cases score higher.

**Source badges — what each database is:**
- **F-7:** Department of Labor Form LM-10/F-7 filings. These are reports that employers with union contracts are required to file. If an employer has an F-7 badge, it means they have (or had) a union contract.
- **OSHA:** Occupational Safety and Health Administration inspection records. Federal workplace safety inspections, violations, and penalties.
- **NLRB:** National Labor Relations Board case records. Union election petitions, election results, and unfair labor practice complaints.
- **WHD:** Wage and Hour Division enforcement records. Department of Labor investigations into wage theft, overtime violations, and minimum wage violations.
- **SAM:** System for Award Management. The federal database of government contractors. Includes employer size, industry codes, and contract registration.
- **SEC:** Securities and Exchange Commission filings. Public company financial data, corporate structure, and subsidiary information from EDGAR database.

**Confidence dots (●●●○):**
How confident the system is that records from a data source were correctly matched to this employer. Matches are made by comparing names, addresses, EINs (tax IDs), and other identifiers across databases.
- **●●●● (4 dots):** Matched on a unique identifier like EIN or exact name + exact address. Very high confidence — almost certainly correct.
- **●●●○ (3 dots):** Matched on name + state or name + city. High confidence but small chance of a mix-up with similarly named employers.
- **●●○○ (2 dots):** Matched on fuzzy name similarity + location. Medium confidence — the data is probably right but worth verifying for critical decisions.
- **●○○○ (1 dot):** Matched on name similarity alone. Low confidence — treat this data with caution and verify independently. Use the "Something Looks Wrong" button if it looks wrong.

**Employee count range (e.g. 150-300):**
Different government databases collect employee counts at different times, using different definitions. OSHA counts workers at a specific facility on the day of an inspection. SAM.gov counts the entire company at the time of registration. Mergent Intellect uses their own research methodology. Rather than picking one number, the platform shows the range across all sources so you can see the spread. The scoring system uses the average.

### SEARCH PAGE — "How to read this page"

**Search bar:**
Search by employer name, city, or state. Results appear after you type at least 3 characters. The search looks across all employer names in the database, including alternate names and former names.

**Advanced Filters:**
Click to expand additional filters that narrow your results:
- **State:** Filter to employers in a specific state.
- **Industry:** Filter by industry classification (NAICS code). Start typing an industry name to see options.
- **Employee size:** Filter to employers within a size range (e.g. 100-500 employees).
- **Score tier:** Show only employers in a specific tier (Priority, Strong, etc.).
- **Data sources:** Show only employers that have records in specific databases (e.g. "only show employers with OSHA data").
- **Union status:** Show only employers with existing union contracts, or only employers without unions.

**Results table columns:**
- **Employer:** Company name. Click to open their full profile.
- **Industry:** Primary industry classification.
- **Location:** City and state of the employer (or primary location for multi-location companies).
- **Employees:** Reported employee count (range if sources disagree).
- **Union:** Name of the union representing workers, if any.
- **Score:** The employer's organizing potential tier.
- **Sources:** Which government databases have records for this employer. More badges generally means more complete data.

**Table/Card toggle:**
Switch between a compact table view (more results visible) and a card view (more detail per result). Both show the same data.

**Sorting:**
Click any column header to sort results by that column. Click again to reverse the sort order. The arrow (↕) indicates which column is currently sorted.

### TARGETS PAGE — "How to read this page"

**What this page is for:**
This page shows organizing targets — employers ranked by their potential for a successful organizing campaign. These are employers where the available data suggests favorable conditions for workers to organize.

**Tier summary cards:**
The cards at the top show how many employers fall into each tier. Click a tier card to filter the table below to only that tier.
- **Priority (top 3%):** Highest-value targets. Start here when planning campaigns.
- **Strong (next 12%):** Very promising. Worth detailed assessment.
- **Promising (next 25%):** Good potential. Investigate further.
- **Moderate (next 35%):** Some signals. Keep on the radar.
- **Low (bottom 25%):** Few signals in current data.

Tier counts update whenever new data is loaded into the system. The same employer may shift tiers over time as new information becomes available.

**Bulk actions:**
Select multiple employers using the checkboxes, then use the action bar to:
- **Export Data:** Download selected employers as a spreadsheet for offline analysis or sharing.
- **Flag all:** Mark selected employers as targets for follow-up.

### UNION EXPLORER PAGE — "How to read this page"

**What this page is for:**
Browse and research unions, their organizational structure, and the employers they represent. Use the search bar to find a specific union, or browse the hierarchy tree to explore how unions are organized.

**Hierarchy tree:**
Unions are organized in a parent-child structure. National and international unions are at the top, with regional bodies and local unions underneath. Click the arrow to expand any level and see what's inside.
- **Affiliation (e.g. AFL-CIO, Change to Win):** The largest groupings of unions.
- **International/National union (e.g. SEIU, IBEW):** Individual unions that operate across the country.
- **Local union (e.g. SEIU Local 1199):** The local chapter that directly represents workers at specific employers.

**Union profile header:**
- **Abbreviation:** The union's commonly used short name.
- **Affiliation:** Which federation the union belongs to, if any.
- **Member count:** Total reported membership across all locals (dues-paying members shown; covered workers available in detail).
- **Employers:** Number of employers where this union represents workers.
- **Locals:** Number of local union chapters.

**Relationship map:**
The expandable list below the header shows the full organizational tree — from the national union down through its locals and the specific employers each local represents. Click any employer name to open their employer profile.

### ADMIN PANEL — "How to read this page"

**This page is only visible to administrators.**

**Score weight configuration:**
Adjust how much each of the 8 scoring factors matters in the final score. Higher weight = more influence on the score. Changes take effect immediately and recalculate all employer scores. The current defaults are based on organizing strategy research: structural factors (union proximity, size, NLRB activity) at 3x, leverage factors (contracts, growth, similarity) at 2x, and grievance factors (OSHA, WHD) at 1x.

**Data freshness:**
Shows when each data source was last updated. Government databases are updated on different schedules — some monthly, some quarterly, some annually. Stale data (more than 6 months old) is highlighted. Refresh buttons trigger a new data pull from the source.

**Match review queue:**
When users click "Something Looks Wrong" on an employer profile, it appears here. Each item shows which employer and which data source the user flagged, along with the current match confidence. Admins can approve the match (dismiss the flag) or reject it (unlink the data source from that employer).

**System health:**
- **Database size:** Total size of the PostgreSQL database on disk.
- **API response times:** Average time to respond to common requests (search, profile load). Slower than 2 seconds may indicate a problem.
- **Error rates:** Percentage of API requests that failed. Should be near zero.

**User management:**
Add, remove, or change roles for platform users.
- **Viewer:** Can search and view everything but cannot flag, export, or report problems.
- **Researcher:** Can flag employers, export CSVs, and report bad matches.
- **Admin:** Full access including this admin panel, score weights, and user management.

---

# 9. EDGE CASES & SPECIAL SCENARIOS

## Historical Employers
- NOT shown in search results
- NOT scored
- Kept in database as reference data only
- Active universe: ~67,552 current F-7 employers + master list additions

## Manual Employer Entries
- Admin-only
- Full form: name, address, EIN, NAICS, employee count, revenue, website, etc.
- Gets [MANUAL] source badge
- Can later be matched to data from pipelines

## Name Changes, Mergers, Acquisitions
- Parent-child corporate hierarchy structure
- Each subsidiary keeps its own profile and score
- Parent shows aggregate view
- Automatic detection suggests links (SEC Exhibit 21, corporate crosswalk, name matching), admin confirms

## Multi-Location Employers
- Company-level profile shows big picture
- Individual locations have their own profiles underneath
- Both levels scored
- Location scores inherit company-wide factors (contracts, growth, size)
- Location-specific factors from OSHA, NLRB, union proximity
- Depends on master list expansion (SAM.gov, OSHA establishments provide location data)

## Public Sector Employers
- Appear in same search with [PUBLIC] badge
- Profile uses same card framework but adapts:
  - Bargaining Units replaces OSHA
  - Government Structure replaces Corporate Hierarchy
  - Budget/Funding replaces Contracts
- Scoring uses different factors appropriate for government employers
- Implementation: after core private sector features are complete

## Multi-Employer Agreements
- Building trades showing 15x inflation in association agreements vs individual locals
- Reconciliation methodology: group agreements, mark primary records, preserve relationship tracking
- Display: show association agreement context on employer profiles

## Sessions & User Data
- Sliding timeout: 1 hour of inactivity
- Flags, saved searches, notes stored in browser localStorage
- Data lost if user switches device or clears browser

## Minor Design Gaps (Not Blocking — Handle During Implementation)
- **Login page:** No specific UI mockup decided. Standard centered login form with invite-only messaging. Build Phase 1 handles this.
- **First-time onboarding:** No specific walkthrough or tutorial designed. The "How to read this page" help sections serve this purpose for now.
- **404/Not Found page:** No specific design. Standard friendly error page with navigation back to search.

---

# 10. SECURITY & AUTHENTICATION

| Decision | Choice |
|----------|--------|
| **Login method** | Invite-only (admin creates accounts, no self-registration) |
| **Password requirements** | Minimum 12 characters, must include number + special character |
| **Two-factor auth** | Not required (can add later) |
| **Session timeout** | 1 hour sliding |
| **Initial scale** | Start small, architecture supports growth |
| **Auth implementation** | Already built (JWT-based), currently disabled for development |

**CRITICAL deployment note:** The `.env` file currently has `DISABLE_AUTH=true` — this MUST be removed before any deployment. The API refuses to start without `LABOR_JWT_SECRET` when auth is enabled.

---

# 11. OLMS DATA ON UNION PROFILES

## What to Surface
- **Membership trends:** Year-over-year member counts with sparkline chart + actual numbers
- **Financial health:** Full breakdown — revenue by source, expenses by category (organizing, admin, representation)
- **NOT included for now:** Organizing spend, officer/leadership data

## Membership Display (Covered Workers vs Dues-Paying)
- Union profile header shows **dues-paying members** as the default number
- **Covered workers** available on hover or in membership trends detail card
- The gap between the two numbers shown inside the membership trends card only (not in header)
- Must use deduplicated counts (platform's 14.5M vs BLS 14.3M — 1.4% difference)

---

# 12. DEEP DIVE TOOL (Workforce Demographics + Web Scraper Combined)

## Architecture
A single "Run Deep Dive" button on employer profiles that runs two steps in sequence:

### Step 1: Government Workforce Data (Fast — Seconds)
Pulls from pre-loaded databases, matched by employer's industry code and location:
- **BLS Occupational Matrix** — "what kinds of jobs exist at employers like this"
- **ACS PUMS Demographics** — "who tends to work in this industry in this area" (age, race, education, income)
- **Revenue-to-Headcount Estimation** — estimate employee count when no official count exists
- **O*NET Job Characteristics** — "what these jobs are actually like" (skills, education, physical demands, automation risk)

### Step 2: Web Research (Slower — Runs in Background)
Uses Crawl4AI + LangExtract to scrape and extract structured data from:
- **Employer website** — about page, careers page, locations, leadership team
- **News articles** — recent coverage mentioning the employer
- **SEC filings** — executive compensation, risk factors, subsidiaries (public companies only)
- **Social media** — LinkedIn, Twitter presence and recent activity
- **Job postings** — open positions, roles, locations (signals growth or turnover)
- **NOT included:** Glassdoor/Indeed reviews

### Output Format
- **AI summary at top** with specific citations via LangExtract (each claim linked to source)
- **Raw sources below** for verification (links, dates, excerpts)

### Permissions
- **Trigger a deep dive:** Researcher + Admin only
- **View saved results:** All roles (Viewer, Researcher, Admin)

### Results Storage
- Saved permanently to the employer profile
- Future visitors see results without re-running
- Shows "Last researched: [date]" with option to re-run

### Display
- Results appear as a new "Deep Dive Results" section below all existing profile cards
- Only visible on profiles where a deep dive has been run
- "Deep Dive Available" badge shown on search results for researched employers
- While running: progress indicator showing Step 1 (workforce data) → Step 2 (web research)
- Step 1 results appear first while Step 2 loads in background

## Timing
Build after React frontend exists. Deep dives will likely run on a few hundred to a few thousand employers — the ones organizers actually investigate, not the full 146,863.

---

# 12B. ADDITIONAL DATA FEATURES

## AI Deep Research (Claude Skill — Available Now)
A Claude skill (in the `union-research` skill folder) that generates a research document for a flagged employer. Covers: news, worker sentiment, financial analysis, organizing intel. This is the precursor to the platform-integrated Deep Dive tool (Section 12). Output format is designed to be database-ingestible from day one, so research produced now can be imported into the platform later.

## Union Website Scraper Expansion
Currently scrapes AFSCME websites only. Plan: expand to SEIU, UAW, Teamsters, UFCW, USW. Scraper data goes into a separate research database for now. Helps verify and enrich union profiles. Employer data verified and added when caught. This is separate from the Deep Dive employer web scraper — this is about scraping union websites for data enrichment.

## Employee Estimation Tool
Revenue-per-employee model for employers that have financial data (from SEC, Mergent, etc.) but no employee count from any government source. Based on `REVENUE_PER_EMPLOYEE_RESEARCH.md`. Uses industry-specific revenue-per-employee ratios to estimate headcount.

- **On employer profiles:** Embedded in the Financial Data card as an estimated count when no official count exists
- **In Deep Dive Step 1:** Part of the Revenue-to-Headcount Estimation data pull
- **Future:** Standalone calculator page where researchers can input revenue + industry and get an estimate
- **Output format:** Designed to be database-ingestible from day one (estimates saved to employer record with [ESTIMATED] flag)

---

# 13. IRS BUSINESS MASTER FILE

| Decision | Choice |
|----------|--------|
| **Scope** | Load full 1.8 million rows (not just unions — includes all nonprofits) |
| **Timing** | Now — before frontend work begins |
| **Value for unions** | EIN-based matching/verification, help resolve 166 missing unions |
| **Value for employers** | Nonprofit employer data (hospitals, universities, social services) — financial classification, EINs, addresses |
| **Scoring impact** | Nonprofits are major organizing targets; BMF provides matching and verification data |
| **Current state** | Table `irs_bmf` has 25 test rows — needs full load |

---

# 14. PUBLIC SECTOR ADAPTATION

Public sector employers are merged into the main platform with a [PUBLIC] badge. They use the same card framework but with adapted content:

| Private Sector Card | Public Sector Equivalent |
|--------------------|-----------------------|
| OSHA Safety | Bargaining Units |
| Corporate Hierarchy | Government Structure |
| Government Contracts | Budget/Funding |

Public sector scoring uses different factors appropriate for government employers. Implementation is after the core private sector features are complete.

---

# 15. PERMISSION LEVELS & ROLES

Three roles with clear boundaries:

| Action | Viewer | Researcher | Admin |
|--------|--------|------------|-------|
| Search & view profiles | ✅ | ✅ | ✅ |
| View saved deep dive results | ✅ | ✅ | ✅ |
| Flag employers as targets | ❌ | ✅ | ✅ |
| Export data (CSV) | ❌ | ✅ | ✅ |
| Report bad matches ("Something Looks Wrong") | ❌ | ✅ | ✅ |
| Trigger deep dives | ❌ | ✅ | ✅ |
| Access Settings panel | ❌ | ❌ | ✅ |
| Adjust score weights | ❌ | ❌ | ✅ |
| Add manual employers | ❌ | ❌ | ✅ |
| Review flagged matches | ❌ | ❌ | ✅ |
| Manage users | ❌ | ❌ | ✅ |
| Create user accounts (invite-only) | ❌ | ❌ | ✅ |

---

# 16. CLAUDE CODE TASK LIST

## Immediate (Before Frontend)
1. Run materialized view refresh (NLRB decay, NLRB flag fix, BLS financial fix)
2. Query top 10 biggest missing unions by worker count
3. Verify legacy table alignment across sources
4. Investigate search duplicate scope
5. **Load full IRS Business Master File (1.8M rows)**
6. Design master employer table schema
7. Build SAM.gov → master list seeding pipeline
8. Build Mergent → master list matching pipeline
9. Deduplication across F-7 + SAM + Mergent + BMF

## Parallel with Frontend Build
10. Build Deep Dive tool infrastructure (government data lookup pipeline)
11. Build Deep Dive web scraper (Crawl4AI + LangExtract pipeline)
12. OLMS financial/membership data extraction for union profiles
13. NLRB xref coverage expansion (161,759 null links to fill — not broken links)

## After Frontend Launch
14. Generate score validation test set (10-15 employers spanning tiers/industries/sizes)
15. Diagnose specific missing union linkages (Jacob provides examples)
16. Wave 2 master list: NLRB participants
17. Wave 3 master list: OSHA establishments (filtered to 2+ violations or serious)
18. Public sector profile adaptation
19. Saved search + notification system

## Known Technical Debt (Not Blocking)
- Problem 9: Platform only runs on one laptop (Docker draft exists, CI/CD needed)
- Problem 12: Model B propensity score basically random (0.53 accuracy)
- Problem 13: Documentation drift (auto-generation of key metrics needed)
- Problem 15: GLEIF schema is 12.1 GB (64% of DB) — archive candidate
- Problem 22: Old scorecard row count declining (investigated, understood, not urgent)
- Problem 23: IRS BMF has 25 test rows (addressed by Task 5 above)
- OSHA dead tuple bloat needs VACUUM
- `.env` DISABLE_AUTH=true must be removed before deployment

---

# 17. DOCUMENTS PRODUCED

| Document | Contents | Status |
|----------|----------|--------|
| **This document** | Complete unified specification | Active — single source of truth |
| SCORING_SPECIFICATION.md | Standalone 8-factor scoring system detail | Incorporated into this document |
| REACT_IMPLEMENTATION_PLAN.md | Standalone tech stack and build order | Incorporated into this document |
| PLATFORM_HELP_COPY.md | Help section text for all 5 pages | Incorporated into this document |
| PLATFORM_REDESIGN_SPEC.md | Original spec (before addendum) | Superseded by this document |
| PLATFORM_REDESIGN_ADDENDUM.md | Remaining topics (security, OLMS, deep dive, BMF) | Superseded by this document |
| PLATFORM_REDESIGN_INTERVIEW.md | Raw interview decisions (earlier, sometimes superseded) | Superseded by this document |
| color_palette_mockup.html | Visual design reference with full palette | Active reference |
| color_comparison.html | Red accent color comparison options | Active reference |

---

# APPENDIX: RECONCILIATION NOTES

The following conflicts between earlier interview decisions and later spec decisions were resolved in favor of the later, more specific decision:

| Topic | Earlier Decision (Interview) | Final Decision (Spec) | Reason |
|-------|-----------------------------|-----------------------|--------|
| **Number of factors** | 7 factors | 8 factors (Statistical Similarity added as separate from Union Proximity) | Better separation of known connections vs statistical inference |
| **Typography** | Playfair Display + Source Sans Pro | Inter only | Consistent with shadcn/ui defaults, zero config, better screen readability |
| **Union Proximity scoring** | Layered 0-10 including Gower similarity | Binary 0/5/10 (Gower moved to Factor 8) | Cleaner separation of structural vs statistical signals |
| **Employer Size scoring** | Sliding scale, no hard cutoff, peaks at 50-500 | Under 15 = 0, linear ramp 15-500, plateau at 500+ | Clearer boundaries, easier to explain |
| **Nav sections** | Search \| Unions \| Targets \| Admin | Employers \| Targets \| Unions \| Settings | More user-friendly naming |
| **Search autocomplete** | Categorized (Employers/Unions/Sectors) | Categorized (Employers/Unions) — sectors dropped | Simplified; sector search not a core workflow |
| **Industry filter** | NAICS 2-digit dropdown + text-based sector classification | NAICS code with type-ahead only | Text-based sector system dropped; NAICS codes sufficient with type-ahead UX |
| **Profile card order** | Scorecard → OSHA → NLRB → WHD → Corporate → Contracts → Comparables → Contact → Notes | Score always visible → Union → Financial → Corporate → Comparables → NLRB → Contracts → OSHA → WHD | Strategic/structural cards above enforcement cards |
| **Loading states** | Spinner with labor movement quotes | Skeleton screens (shadcn/ui standard) | More professional, less novelty |
| **Geography filters** | State dropdown + City text input + Metro area dropdown | State dropdown only | City search handled by main search bar ("Search by employer name, city, or state"). Metro area dropped — not enough value for the complexity. |
| **Score filter** | "Minimum score" (continuous) | "Score tier" (categorical: Priority/Strong/etc.) | Tiers are the scoring unit throughout; continuous filtering adds complexity without benefit |

---

*This document was produced on February 20, 2026 and reflects every decision made during the complete Platform Redesign Interview. It is the single source of truth for implementation by Claude Code, Codex, and Gemini.*
