# Platform Redesign Specification — Complete
## Decided in Platform Redesign Interview | February 20, 2026

---

# TABLE OF CONTENTS

1. Scoring System (8 Factors)
2. Data Quality Decisions
3. React Implementation Plan
4. Edge Cases & Special Scenarios
5. Visual Design
6. Specific Page Designs
7. Content & Copy
8. Claude Code Task List

---

# 1. SCORING SYSTEM

## 8-Factor Model

| Factor | Weight | Logic |
|--------|--------|-------|
| Union Proximity | 3x | 2+ unionized siblings = 10, 1 sibling or corporate family = 5, none = 0 |
| Employer Size | 3x | Under 15 = 0, ramps 15-500, plateaus at 10 from 500+ |
| NLRB Activity | 3x | 70% nearby momentum / 30% own history. Losses score negative. 7-year half-life. |
| Gov Contracts | 2x | Federal=4, state=6, city=7, any two=8, all three=10. Dollar value tiebreaker only. |
| Industry Growth | 2x | Linear mapping from BLS 10-year projections to 0-10. |
| Statistical Similarity | 2x | Match count + closeness. Only for employers with no corporate union connection. |
| OSHA Safety | 1x | Industry-normalized violation count. 5-year half-life. +1 bonus for willful/repeat. |
| WHD Wage Theft | 1x | 0 cases=0, 1=5, 2-3=7, 4+=10. 5-year half-life. Dollar amounts display only. |

## Calculation Method
1. Calculate each factor 0-10
2. Skip factors with no data (signal-strength)
3. Multiply by weight (1x/2x/3x)
4. Sum weighted scores / total weight of available factors
5. Map to percentile tier

## Tier Breakpoints (Percentile-Based)
- Priority: top 3% (~4,400 employers)
- Strong: next 12% (~17,600)
- Promising: next 25% (~36,700)
- Moderate: next 35% (~51,400)
- Low: bottom 25% (~36,700)

Recalculates on every data refresh. Admin-configurable weights with no guardrails.

---

# 2. DATA QUALITY DECISIONS

| Topic | Decision |
|-------|----------|
| Search duplicates | Database-level problem; UI merges into one result with source badges |
| Union linkage gaps | Show match confidence per source; investigate specific examples |
| Score validation | After frontend is built; generate test set of 10-15 employers |
| Wrong matches | Show confidence on profiles; users can flag → admin review queue |
| Propensity Model B | Hidden from users; improve over time |
| GLEIF data | Leave 12GB in place for now |
| Legacy table sync | Already handled in Phase B |
| 166 missing unions | Get top 10 by worker count; address in future session |

---

# 3. REACT IMPLEMENTATION PLAN

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | React + Vite (fresh build) |
| Styling | Tailwind CSS + shadcn/ui |
| State Management | Zustand (auth, search, profile, flags stores) |
| Data Fetching | TanStack Query + thin API wrapper |
| Tables | TanStack Table + shadcn/ui styling |
| Routing | React Router (full URL state) |
| Testing | Vitest + React Testing Library (unit + integration, written alongside components) |
| Deployment | Separate servers: nginx serves React, proxies /api/ to FastAPI |

## Build Order
1. Layout shell (nav, routing, auth, error handling)
2. Search page (search bar, autocomplete, results table/cards)
3. Employer profile (header, score breakdown, all cards)
4. Targets/Scorecard (tier dashboard, filtered table, bulk export)
5. Union explorer (search, hierarchy tree, union profiles)
6. Admin panel (weights, freshness, review queue, health, users)

**Milestone:** After steps 1-3, the core product is usable. Score validation happens here.

---

# 4. EDGE CASES & SPECIAL SCENARIOS

## Master Employer List
- F-7 employers are the reference library (employers with unions)
- Non-F-7 employers are the prospect pool (organizing targets)
- Master list grows as data connections accumulate across sources
- Non-F-7 employers surface as targets when 2+ scoring factors have data
- Confidence indicator shown: "Score based on X of 8 factors"
- Built in parallel with React frontend

## Master List Seeding (Wave Plan)
- **Wave 1:** SAM.gov (826K) + Mergent Intellect (56K) — clean data, immediate scoring value
- **Wave 2:** NLRB participants (after data quality cleanup)
- **Wave 3:** OSHA establishments (filtered to 2+ violations or serious violations)

## Historical Employers
- Not shown in search results
- Not scored
- Kept in database as reference data only
- Active universe: ~67,552 current F-7 employers + master list additions

## Manual Employer Entries
- Admin-only
- Full form (name, address, EIN, NAICS, employee count, revenue, website, etc.)
- Gets [MANUAL] source badge
- Can later be matched to data from pipelines

## Name Changes, Mergers, Acquisitions
- Parent-child corporate hierarchy structure
- Each subsidiary keeps its own profile and score
- Parent shows aggregate view
- Automatic detection suggests links, admin confirms

## Multi-Location Employers
- Company-level profile shows big picture
- Individual locations have their own profiles underneath
- Both levels scored
- Location scores inherit company-wide factors (contracts, growth, size)
- Location-specific factors from OSHA, NLRB, union proximity

## Empty States
- Cards with no data are hidden entirely
- Source badges tell the story of what data exists
- No summary line of checked sources

## High-Volume Cards
- Show 5 most recent records by default
- "Show more" loads next batch
- Most recent first

## Conflicting Data
- Profile shows a range (e.g. "150-300 employees")
- Scoring uses the average across sources

## Loading & Performance
- Skeleton screens for profile loading
- TanStack Query caching for instant revisits
- Search autocomplete: 300ms debounce + 3 character minimum

## Sessions
- Sliding timeout: 1 hour of inactivity
- Flags, saved searches, notes stored in browser (localStorage)

## Permission Levels (Three Roles)

| Action | Viewer | Researcher | Admin |
|--------|--------|------------|-------|
| Search & view | ✅ | ✅ | ✅ |
| Flag employers | ❌ | ✅ | ✅ |
| Export data | ❌ | ✅ | ✅ |
| Report bad matches | ❌ | ✅ | ✅ |
| Settings panel | ❌ | ❌ | ✅ |
| Adjust weights | ❌ | ❌ | ✅ |
| Add manual employers | ❌ | ❌ | ✅ |
| Review flagged matches | ❌ | ❌ | ✅ |
| Manage users | ❌ | ❌ | ✅ |

---

# 5. VISUAL DESIGN

| Decision | Choice |
|----------|--------|
| Overall feel | Professional/corporate + modern hybrid |
| Mode | Light only |
| Base colors | Charcoal/warm gray (#1c1917 → #fafaf9) |
| Accent color | True red #dc2626 |
| Score tiers | Red intensity: #fef2f2 (Low) → #dc2626 (Priority) |
| Font | Inter (shadcn/ui default) |
| Density | Standard (tables slightly tighter) |
| Cards | Light border + subtle shadow, square corners |
| Icons | Lucide (built into shadcn/ui) |
| Confidence indicators | Filled/empty dots ●●●○ (4 max) |
| Navigation | Top nav bar, auto-hide on scroll |

## Tier Color Scale
- Priority: #dc2626 (deep red) — white text
- Strong: #ef4444 (red) — white text
- Promising: #f87171 (light red) — dark text
- Moderate: #fecaca (pale pink) — dark red text
- Low: #fef2f2 (barely pink) — dark red text

## Source Badge Styles
- High confidence match: dark background (#1c1917), white text
- Medium confidence: mid-gray background (#44403c), white text
- Low confidence: light background (#f5f5f4), dark text, gray border

---

# 6. SPECIFIC PAGE DESIGNS

## Search Page
- Search-first (Google style): big centered search bar before searching
- After searching: search bar moves to top, results fill below
- Collapsible "Advanced Filters" panel
- Filters: State, Industry, Employee size, Score tier, Data sources, Union status
- Table/card toggle for results
- Table columns: Employer name, Industry, Location, Employee count, Union, Score tier, Source badges
- 25 results per page

## Employer Profile
- **Header area (always visible):**
  - Employer name, location, industry, employee count, tier badge, source badges
  - Action buttons: Flag as Target, Compare Employers, Export Data, Something Looks Wrong
  - Score factor breakdown (8-factor bar chart)
- **Collapsible cards (in order, hidden if no data):**
  1. Union Relationships
  2. Financial Data
  3. Corporate Hierarchy
  4. Comparables
  5. NLRB Election History
  6. Government Contracts
  7. OSHA Safety Violations
  8. WHD Wage Theft Cases
- Single column, scrolling page
- All cards collapsed by default
- Card headers show summary (e.g. "OSHA Safety — 12 violations")

## Targets Page
- Tier summary dashboard cards at top (clickable, showing count per tier)
- Visual summary bar + filter controls
- Filtered table below (reuses search table component)
- Pre-filtered to non-union employers, sorted by score descending
- Bulk export and flagging available

## Union Explorer
- Search bar at top for finding unions by name
- Browseable hierarchy tree below (Affiliation → National → Local)
- Union Profile: header with key stats (name, abbreviation, affiliation, member count, employers, locals)
- Relationship visualization: expandable indented list (file explorer style)
- Employer names clickable to their profiles

## Admin Panel (Settings)
- Single scrolling dashboard with section headers
- Section order:
  1. Score weight configuration (sliders)
  2. Data freshness dashboard (last updated per source)
  3. Match review queue (user-flagged issues)
  4. System health (DB size, API times, error rates)
  5. User management (roles: viewer, researcher, admin)

---

# 7. CONTENT & COPY

## Tone & Language
- Professional neutral throughout — factual, no spin
- Organizing terminology in Targets section only
- Neutral business language elsewhere

## Help System
- Collapsible "How to read this page" at top of each page
- Collapsed by default
- One sentence per item (expanded to 2-3 sentences for: score, tiers, source badges, confidence dots, employee range)
- Full copy drafted for all 5 pages — see PLATFORM_HELP_COPY.md

## Labels & Buttons
- Nav tabs: Employers | Targets | Unions | Settings
- Search placeholder: "Search Employers"
- Flag button: "Flag as Target"
- Report button: "Something Looks Wrong"
- Export button: "Export Data"
- Compare button: "Compare Employers"

## Empty States
- Search (no results): "No results found. Try broadening your search or adjusting your filters."
- Flagged targets (empty): "Your target list is empty. Start by flagging employers from search results or the Targets page."
- Match review (empty): "All clear — no reported issues."

---

# 8. CLAUDE CODE TASK LIST

## Immediate (Before Frontend)
1. Run materialized view refresh (NLRB decay, flag fix, BLS fix)
2. Query top 10 biggest missing unions by worker count
3. Verify legacy table alignment across sources (quick check)
4. Investigate search duplicate scope

## Parallel with Frontend
5. Design master employer table schema
6. Build SAM.gov → master list seeding pipeline
7. Build Mergent → master list matching pipeline
8. Deduplication across F-7 + SAM + Mergent

## After Frontend Launch
9. Generate score validation test set (10-15 employers)
10. Diagnose specific missing union linkages (Jacob provides examples)
11. Wave 2 master list: NLRB participants (after cleanup)
12. Wave 3 master list: OSHA establishments (filtered)

---

# DOCUMENTS PRODUCED

| Document | Contents |
|----------|----------|
| SCORING_SPECIFICATION.md | Complete 8-factor scoring system |
| REACT_IMPLEMENTATION_PLAN.md | Full tech stack and build order |
| PLATFORM_HELP_COPY.md | Help section text for all 5 pages |
| color_palette_mockup.html | Visual reference for original palette |
| color_comparison.html | Red-shifted accent color options |
| PLATFORM_REDESIGN_SPEC.md | This document — everything combined |
