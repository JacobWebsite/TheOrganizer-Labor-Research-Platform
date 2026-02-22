# The Organizer — Platform Redesign Interview
## Decisions & Specifications | February 2026

**Status:** In progress — approximately 60% complete. Remaining topics listed at the end.

---

## 1. Foundational Decisions

| Topic | Decision |
|-------|----------|
| **Audience** | Mixed: field organizers, research/strategy staff, and union leadership |
| **Current Status** | Internal tool (solo user), multi-user planned |
| **North Star** | Finding the right employers to organize — the search → scorecard → profile flow |
| **Navigation Model** | Current Territory/Search model needs complete rethinking |
| **Top Concerns** | UI/UX rough, data quality issues, missing key features (all three) |
| **Core Workflows** | 1) Research specific employer, 2) Explore sector → non-union employers → deep dive → scorecard, 3) Check union trends/finances |
| **Visual Direction** | Balance of professional/corporate/database and editorial warmth. **Mockups needed to decide palette.** |
| **Typography** | Keep Playfair Display (serif headlines) + Source Sans Pro (sans-serif body) |
| **Mobile** | Desktop only |

---

## 2. Technical Architecture

### Frontend Stack

| Choice | Decision |
|--------|----------|
| **Framework** | React with Vite — fresh build, reference old JS for API patterns |
| **CSS** | Tailwind CSS + shadcn/ui component library |
| **Code Structure** | Feature-based with shared layer: `/src/features/{search,employer-profile,union-explorer,scorecard,admin}/` + `/src/shared/{components,hooks,api}/` |
| **Routing** | React Router. Full URL state for searches (bookmarkable, shareable). |
| **Code Reuse** | Start fresh in React. Old 19 JS files kept as reference for API call patterns only. |

### API Strategy

| Choice | Decision |
|--------|----------|
| **Existing Endpoints** | Keep all existing endpoints. Add new ones as needed. Do NOT remove. |
| **Profile Pattern** | One big aggregated endpoint per page — returns ALL data for employer/union profile in one call |
| **API Cleanup** | Clean up: consolidate where possible, but preserve backward compatibility |

### Navigation & Layout

| Element | Decision |
|---------|----------|
| **Nav Type** | Horizontal top bar (not sidebar). Title + nav links + user account. |
| **Main Sections** | Search (home) \| Unions \| Targets \| Admin |
| **Pages vs Modals** | Full pages replace all 10+ modal types. Employer/union profiles get dedicated pages with URLs. |
| **Breadcrumbs** | Always visible: `Search > Memorial Hospital > OSHA Violations` |
| **Loading States** | Spinner with loading message. Future: rotating labor movement quotes + progress indicator. |
| **Error States** | Friendly error message with retry button. Non-technical, actionable. |
| **Empty States** | Show card with explanation: "No OSHA data — this could mean no violations OR no inspection of this location" |

---

## 3. Search Experience

### Search Home Page

| Element | Decision |
|---------|----------|
| **Landing View** | Search bar front and center on a clean page. Google-style minimalism. |
| **Before Typing** | Just the search bar — clean page, no stats or dashboards |
| **Typing Behavior** | Hybrid: autocomplete suggestions while typing, full results on Enter |
| **Autocomplete** | Categorized suggestions: "Employers (5 results) \| Unions (2 results) \| Sectors (1 result)" |
| **Enter Key** | Navigates to a dedicated results page with search bar in header |

### Search Results Page

| Element | Decision |
|---------|----------|
| **Layout** | Toggle between table view and card view |
| **Table Features** | Column sorting + pagination (25 per page) |
| **Card Content** | Name + location + score + key signal icons: [OSHA] [NLRB] [WHD] [CONTRACT] |
| **Default Sort** | User-selectable sort (relevance default, click headers for score/size/state) |
| **Visible Columns** | Name, City, State, Score tier, Industry/Sector, source badges |
| **Duplicate Handling** | One merged result per canonical employer with source badges: [F7] [NLRB] [VR] |
| **URL State** | Full URL state: `/search?q=hospital&state=NY&min_score=5`. Bookmarkable, shareable. |

### Advanced Filters

- **Geography:** State dropdown, City text input, Metro area dropdown
- **Industry:** NAICS 2-digit dropdown + text-based sector classification
- **Size:** Employee count range (min/max inputs)
- **Score/Signals:** Minimum score, "Has OSHA violations", "Has NLRB activity", "Has government contracts"

*Filters hidden by default behind a "Filters" toggle button. Active filters shown as removable chips.*

### Search Architecture

One universal search bar + advanced filters. System handles different query types (employer name, location, union name) through the same interface. No separate search modes. Kill the existing basic/fuzzy/normalized search split.

---

## 4. Unified Scoring System

### Score Architecture

| Element | Decision |
|---------|----------|
| **Approach** | Signal-strength scoring: only score on factors where data exists. Missing = excluded, not zero. |
| **Scale** | Each factor 0-10, averaged across available factors |
| **Tiers (5)** | Priority / Strong / Promising / Moderate / Low |
| **Confidence** | Both coverage % (how many factors have data) AND match quality flags (confidence of data linkages) |
| **Weights** | Admin-configurable factor weights (not user-adjustable) |
| **Current Status** | mv_unified_scorecard exists with 7 factors. Factors are right but scoring LOGIC needs work. |

### Scoring Factors (7 total)

#### 1. OSHA Safety Violations (Graded 0-10)
Industry-normalized, recency-weighted, severity bonus for willful/repeat. Current logic is acceptable.

#### 2. NLRB Activity (Graded 0-10)
NLRB activity at THIS employer AND wins at similar employers in the area. Both own history and nearby momentum contribute.

#### 3. WHD Wage Theft (Near-Binary)
Repeat violations dominate the score. Near-binary: major signal when present, minimal gradation. Repeat violator is the strongest signal.

#### 4. Government Contracts (Graded by Type)
State/local contracts weighted HIGHER than federal (more leverageable under current political conditions). Contract type matters more than dollar amount. All sources combined: USASpending + SAM.gov + NY/NYC state and city contracts.

#### 5. Union Proximity (Layered 0-10)
- **8-10:** Direct sibling union (same parent company has unionized locations)
- **5-7:** Corporate family union (related company in hierarchy)
- **3-6:** High Gower similarity to unionized employers (no corporate connection but statistically similar)
- **0-2:** No relationship, no similarity

#### 6. Industry Growth / Financial (Graded 0-10)
Replaces sparse Financial factor. Based on BLS 10-year industry projections. Revenue/sales data incorporated when available via the employee estimation tool.

#### 7. Employer Size (Sliding Scale 0-10)
Sliding scale with no hard cutoff. Sweet spot peaks around 50-500 employees. Smaller employers get proportionally lower scores but are not excluded.

### Comparables Engine
Gower distance engine shares the SAME employer universe as the scorecard. Comparables appear on employer profiles. When viewing a union employer, comparables help identify expansion targets.

---

## 5. Employer Profile Page

### Profile Header
All of the following at a glance:
- **Name, Location** (city/state), **Industry, Employee Count**
- **Score + Tier Badge** (color-coded)
- **Union Status** ("No union" or "Represented by SEIU Local 32BJ")
- **Source Coverage Badges** ([OSHA] [NLRB] [WHD] [SAM] [SEC])

### Card Layout (Priority Order)
Card-based with drill-down. Cards are collapsed by default showing summaries; click to expand for full detail.

#### Card 1: Scorecard
- **Collapsed:** Overall score number + tier badge (color-coded) + mini horizontal bar chart showing each factor's score
- **Expanded:** Factor-by-factor breakdown with plain-English explanations + 3-5 comparable employers with their scores

#### Card 2: OSHA Safety
- **Collapsed:** Color-coded risk badge (HIGH/MEDIUM/LOW) + single most important stat
- **Expanded:** Full violation list with details: date, type, penalty, description. Sortable table.

#### Card 3: NLRB Labor Relations
- **Collapsed:** Own NLRB history ("2 elections: 1 won, 1 lost") + nearby momentum indicator ("3 wins within 25mi in 3 years")
- **Expanded:** Summary on profile, link to separate deep NLRB page for full detail

#### Card 4: WHD Wage Theft
- **Collapsed:** "Wage Violations: YES" badge + total backwages amount. Or "No known wage violations".
- **Expanded:** Case details, dates, backwages per case, workers affected

#### Card 5: Corporate
- **Collapsed:** Parent company name + total subsidiary count + union sibling count: "Parent: HCA Healthcare (47 subsidiaries) | 12 have union contracts"
- **Expanded:** Corporate tree, subsidiary details, sibling locations with union status

#### Card 6: Government Contracts
- **Collapsed:** Total value + contract count + level badges: "$3.4M total across 7 contracts [FEDERAL] [STATE] [CITY]"
- **Expanded:** Individual contract details by level

#### Card 7: Comparables
- **Collapsed:** Similarity summary: "5 comparable employers found | 3 are unionized | Average score: 6.5"
- **Expanded:** Full comparable employer list with comparison metrics

#### Card 8: Contact / Location
- **Data Sources:** City/state from F7, full addresses from OSHA establishments and SAM.gov. Merged from available sources.

#### Card 9: Research Notes
- **Location:** Dedicated card on profile + inline flag icon in header for quick flagging
- **Note Fields:** Free text + flag type (Hot Target / Needs Research / Active Campaign / Follow Up / Dead End) + priority (High/Medium/Low)
- **Future:** Add assigned user + status tracking when multi-user launches

### Public Sector Adaptation
Public sector employers appear in same search with [PUBLIC] badge. Profile uses same card framework but adapts: Bargaining Units replaces OSHA, Government Structure replaces Corporate, Budget/Funding replaces Contracts. Scoring uses different factors appropriate for government employers.

---

## 6. Union Explorer

### Union Search
Primary search methods: **by affiliation parent** (select SEIU, see all SEIU locals) and **by employer connection** (start from employer, find unions). Both supported.

### Affiliation Page
When you select an affiliation: overview stats at top (total members, locals count, financial health) + flat filterable list of all locals with key metrics. Not a dashboard — an overview + list.

### Union Profile Header
Name, affiliation, member count. Sectors are NOT important for union profiles. Simple, not overloaded.

### Union Profile Cards

#### Membership Trend Card
- **Collapsed:** Current count + trend direction + sparkline: "163,000 members ↑ 12% since 2020" with tiny 5-year line chart. MUST use deduplicated counts.

#### Financial Health Card
- **Collapsed:** Simple health badge: Healthy (green) / Stable (yellow) / Declining (red)
- **Formula:** Multi-factor: membership trend + net asset change + receipts/disbursements ratio. All three must align for Healthy or Declining. Mixed = Stable.

#### Employer Connections Card
Two toggle views:
1. **Grouped by local:** "Local 32BJ: 47 employers" with expandable lists
2. **Filterable flat list** of all connected employers by state/industry/size

Bidirectional links: click any employer to go to their profile.

### Expansion Targets Section
Separate section below current employers: "Potential targets — non-union employers similar to ones this union already represents" using Gower distance comparables.

### Hierarchy View
Nested list with indentation: national → districts → councils → locals. Grouped by hierarchy level + filterable by state, size, and financial health.

---

## 7. Scorecard / Targets Section

Targets = filtered scorecard view. Same search mechanics but pre-filtered to non-union employers with scores, sortable by score. Not a separate workflow — it's search with scorecard mode on.

### Bulk Operations
- Checkboxes on table rows
- Primary bulk action: **Export selected to CSV**
- Comparison view: table with highlighted differences across selected employers

### Saved Searches
- Saves filter parameters + result snapshot at time of saving
- Shows what changed when re-visited
- Optional notification rules: "Notify when new employers match" or "when tracked employer score changes"
- **In-app notification badge only** (no email for now)

---

## 8. Admin Section

| Feature | Decision |
|---------|----------|
| **User Management** | Add/remove users, set roles (admin/read), view activity |
| **Score Weights** | Admin-configurable factor weight panel |
| **Data Freshness** | Dashboard showing when each source was last updated, stale flags |
| **MV Refresh** | Refresh materialized views (already used) |
| **Match Quality** | Match quality reports (already used) |
| **System Health** | API health, database size, performance metrics |
| **Review Queue** | Suspected misclassifications (labor orgs as employers). Note: small orgs tied to OPEIU etc. may be legitimate staff unions. |

---

## 9. Additional Features & Data

### AI Deep Research
- **Phase 1 (Now):** Claude skill that generates a research document for a flagged employer. Covers: news, worker sentiment (Glassdoor/Indeed), financial analysis, organizing intel.
- **Phase 2 (Future):** Evolve to trigger from platform UI → store findings in DB → display on employer profile.
- **Design:** Output format designed to be database-ingestible from day one.

### Web Scraper Expansion
Expand beyond AFSCME to SEIU, UAW, Teamsters, UFCW, USW. Scraper data goes into a separate research database for now. Helps verify and enrich union profiles. Employer data verified and added when caught.

### Employee Estimation Tool
Revenue-per-employee model for employers with financial data but no employee count. Based on `REVENUE_PER_EMPLOYEE_RESEARCH.md`. Embedded on employer profile as a card. Standalone calculator as a future feature.

### Public Sector Integration
Merged into main search with [PUBLIC] badge. Adaptive profile pages. Public-sector-specific scoring factors. Not a separate module.

---

## 10. Remaining Interview Topics

**The following areas need further drilling in a future session.**

### Visual Design (Needs Mockups)
- Color palette: 3 options proposed (warm current, dark professional, hybrid warm-professional). User wants real mockups before deciding.
- Card design: exact spacing, shadows, border radius, hover states
- Score tier badge design: colors for each of 5 tiers
- Signal icon design: OSHA, NLRB, WHD, CONTRACT, SEC icons
- Dark mode: yes/no, scope

### Data Quality Deep Dive
- Orphan fix verification: Phase A supposedly done but needs re-checking
- Specific examples of wrong matches to diagnose
- Search duplicate investigation: DB-level or display-level?
- Union linkage gap: which specific employers aren't showing their union connections?
- Score validation: run the unified scorecard against known employers and verify outputs feel right

### Scoring Logic Deep Dive
- Exact formulas for each factor's 0-10 calculation
- Temporal decay curves: how fast should old violations lose weight?
- Gower distance dimensions: which attributes to compare on
- Admin weight configuration UI design
- Score tier breakpoints: what score ranges map to Priority/Strong/Promising/Moderate/Low?

### React Implementation Planning
- Component library inventory: which shadcn/ui components to use for each feature
- State management: React Context vs Zustand vs Redux for auth, search state, flags
- API client design: fetch wrapper, error handling, caching strategy
- Build and deployment: how will the React app be served alongside the FastAPI backend?
- Testing strategy: unit tests, integration tests, E2E tests

### Remaining Roadmap Phases
- Phase C status: missing union investigation (195 unions / 92,627 workers)
- Phase D status: security hardening, cleanup, project organization
- Phase E: scorecard rebuild — master employer table design, new scoring formula implementation
- Phase F: Docker, CI/CD, hosting, beta testers
- Sequencing: which frontend features can be built in parallel with data work?

### Specific Page Designs
- Employer profile: exact card grid layout (1-column, 2-column, responsive?)
- Union profile: hierarchy interaction design (expand/collapse behavior)
- Admin pages: layout for each admin feature
- Login/auth flow: login page design, session management UX
- 404 / not found page design

### Edge Cases & Special Scenarios
- What happens when an employer exists in NLRB but not F7? Display? Scoring?
- Manual employer entries: who creates them, what fields are required?
- Historical vs current employers: should historical employers be searchable? Scored?
- Multi-employer agreements (SAG-AFTRA, etc.): how to display these?
- Sector classification: how to build the text-based sector system alongside NAICS?

### Content & Copy
- Empty state messages for each card type
- Tooltip content for technical terms (contextual help replacing glossary)
- Score explanations: plain English for each factor
- Onboarding: first-time user experience
