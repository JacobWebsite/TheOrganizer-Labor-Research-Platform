



























# Frontend Redesign — Claude Code Instructions

**What this document is:** A step-by-step guide for upgrading the Labor Relations Research Platform's frontend. Each section describes what to change, why it matters, and gives Claude Code a ready-to-use prompt. Work through these in order — later steps depend on earlier ones.

**Reference:** The interactive prototype is in `prototype.jsx`. Use it as the visual target for every change described here. The existing codebase is documented in `FRONTEND_CATALOG.md`.

**Important rules for every step:**
- Run existing tests after each change: `cd frontend && npx vitest run`
- If a test breaks, fix it before moving on
- Commit after each numbered step so you can roll back if something goes wrong
- Keep the existing color palette and font choices — we're changing layout and interaction patterns, not the brand

---

## PHASE 1: New Shared Components

These are reusable building blocks that multiple pages will need. Build them first so the page updates go smoothly.

---

### Step 1.1 — ScoreGauge Component

**What it is:** A half-circle dial (like a speedometer) that shows a score from 0-10. The needle fills up more for higher scores, and the color shifts from warm stone (low) to copper (medium) to brick red (high).

**Why it's better than the current bars:** A gauge is more instantly readable — your eye can judge "how full is the dial?" faster than "how long is this bar compared to that bar?" It also looks more polished and takes up less horizontal space, which matters when you're showing 9 scores in a grid.

**Where it goes:** `frontend/src/shared/components/ScoreGauge.jsx`

**What it replaces:** The 0-10 progress bars currently inside `ScorecardSection`

**Claude Code prompt:**
```
Create a new shared component at frontend/src/shared/components/ScoreGauge.jsx

It should be a half-circle SVG gauge that displays a score value from 0 to 10.

Props:
- value (number, required): the score to display (0-10)
- max (number, default 10): maximum value
- label (string, optional): text below the gauge like "Safety" or "Wage Theft"
- size (number, default 54): width in pixels

Visual design:
- Draw a half-circle arc using SVG <path> elements
- Background arc: use the linen color #ede7db
- Filled arc: color based on value — #c23a22 (brick red) if value >= 7, #c78c4e (copper) if >= 4, #d9cebb (warm stone) if < 4
- The score number centered inside the arc in Source Serif 4 font, bold
- Label text below in 10px muted color #8a7e6d
- The filled arc should animate in with a CSS transition on stroke-dasharray (0.8s ease)

Export as named export. Add to the shared components barrel file if one exists.
Reference the prototype.jsx ScoreGauge component for exact implementation.
```

---

### Step 1.2 — MiniStat Component

**What it is:** A small card that shows one key number with a label, like "Workers: 21,400" or "OSHA Violations: 437." It has a colored top border to visually categorize it.

**Why we need it:** Right now, stats are scattered inside various cards and sections. These compact stat cards create a "dashboard row" at the top of a page so a user can scan key numbers in 2 seconds without reading anything else. Think of them like the stats bar at the top of a stock trading app.

**Where it goes:** `frontend/src/shared/components/MiniStat.jsx`

**Claude Code prompt:**
```
Create a new shared component at frontend/src/shared/components/MiniStat.jsx

A compact stat card that displays a single key metric.

Props:
- label (string): uppercase small text like "WORKERS" or "OSHA VIOLATIONS"
- value (string/number): the big displayed number like "21,400" or "$2.1B"
- sub (string, optional): smaller context line like "Est. from BLS" or "23 serious"
- accent (string, optional): hex color for a 3px top border. If not provided, no top border.

Visual design:
- Background: card cream #faf6ef
- Border: 1px solid #d9cebb, border-radius 4px
- If accent provided, add a 3px top border in that color
- Label: 10px uppercase, letter-spacing 1px, muted color #8a7e6d
- Value: 22px bold Source Serif 4 font, dark text #2c2418
- Sub text: 11px muted color, 2px margin top
- Padding: 12px 16px
- flex: 1 and min-width: 120px so they flow in a row

Use Tailwind classes matching the existing theme. Named export only.
Reference prototype.jsx MiniStat for exact styling.
```

---

### Step 1.3 — SidebarTOC Component (Table of Contents)

**What it is:** A slim sidebar that shows a list of section names (like "Overview," "OSHA Violations," "NLRB Activity"). The currently visible section is highlighted. Clicking a section name scrolls you straight to it.

**Why it matters:** The employer profile page has 20+ cards. Right now, finding specific information means scrolling through everything. This sidebar acts like a table of contents in a long document — you always know where you are and can jump to exactly what you need. It's a pattern used by documentation sites (like Stripe's docs or MDN) because it solves the "I'm lost on a long page" problem.

**How it works technically:** It uses `position: sticky` which means it "sticks" to the side of the screen as you scroll, always staying visible. When you click a section name, it uses `scrollIntoView` to smoothly scroll the page to that section's HTML element.

**Where it goes:** `frontend/src/shared/components/SidebarTOC.jsx`

**Claude Code prompt:**
```
Create a new shared component at frontend/src/shared/components/SidebarTOC.jsx

A sticky sidebar table-of-contents for long pages.

Props:
- sections (array of { id: string, label: string }): the sections to list
- activeSection (string): the id of the currently visible section

Visual design:
- Position: sticky, top: 80px (below the navbar)
- Width: 180px, flex-shrink: 0
- Right border: 1px solid #d9cebb
- Header text: "On this page" in 10px uppercase, letter-spacing 1.5px, muted color
- Each section item:
  - Padding 6px 10px, font size 12px, cursor pointer, border-radius 3px
  - Default: color #8a7e6d, transparent background, 2px left border transparent
  - Active: color #1a6b5a (teal), background rgba(26,107,90,0.08), 2px left border #1a6b5a, font-weight 600
  - Transition 0.15s on all properties

On click: call document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth' })

The parent page is responsible for detecting which section is active (using IntersectionObserver) and passing it as the activeSection prop. The SidebarTOC just renders and handles clicks.

Named export only. Use Tailwind classes matching the existing theme.
```

---

### Step 1.4 — CommandPalette Component (Quick Jump)

**What it is:** A search popup that appears when you press Ctrl+K (or Cmd+K on Mac). It's a floating box in the center of the screen with a search input. As you type, it shows matching employers, unions, and pages you can jump to instantly.

**Why it matters:** Power users — the organizers and researchers who use this platform daily — need to move fast. Instead of clicking through the navbar, going to search, typing a name, and clicking a result, they can press one keyboard shortcut and type a name to jump directly to any page. Apps like Slack, Notion, and VS Code all use this pattern because it's dramatically faster for people who use the tool often.

**How it works technically:** It listens for a keyboard shortcut globally (on the whole page). When triggered, it renders a "modal" (a box floating over the page with a dark overlay behind it). The search input calls the existing autocomplete API endpoint. Selecting a result navigates to that page using React Router.

**Where it goes:** `frontend/src/shared/components/CommandPalette.jsx`

**Claude Code prompt:**
```
Create a new shared component at frontend/src/shared/components/CommandPalette.jsx

A Cmd+K / Ctrl+K command palette for quick navigation.

Props:
- isOpen (boolean): whether the palette is visible
- onClose (function): called to close the palette

Behavior:
1. Render a full-screen semi-transparent overlay (rgba(0,0,0,0.5))
2. Centered container: background cream #faf6ef, border-radius 10px, width 520px, max-height 400px, big shadow
3. Auto-focused search input at top with placeholder "Search employers, unions, or jump to a page…"
4. Input styled in Source Serif 4 font, 15px, no border, bottom border 1px #d9cebb
5. Results list below the input
6. Pressing Escape or clicking the overlay calls onClose

For the search results:
- Use the existing useEmployerAutocomplete hook for employer matches
- Add hardcoded quick-links for pages: "Search", "Targets", "Unions", "Research", "Admin"
- Show icons: 🏢 for employers, 🏛 for unions, 📄 for pages
- First result should have a subtle highlight background
- Clicking a result navigates using React Router's useNavigate() and calls onClose

The parent (Layout component) should:
- Add a useEffect that listens for Ctrl+K / Cmd+K keydown and toggles isOpen
- Render <CommandPalette> conditionally

Also update the NavBar to include a "Quick Jump… ⌘K" button on the right side that opens the palette on click.

Named export. Reference prototype.jsx command palette section for visual styling.
```

---

### Step 1.5 — Enhanced Breadcrumbs

**What it is:** An upgrade to the existing `Breadcrumbs` component that shows the user's full navigation path (like "Search › Walmart › OSHA Violations") with clickable links to go back to any step.

**Why it matters:** Right now breadcrumbs exist but are basic. When an organizer is deep in a research workflow — they searched, opened a profile, drilled into OSHA data — they need to be able to jump back to any previous step without hitting the browser back button multiple times. Clickable breadcrumbs preserve their mental model of "where did I come from?"

**Where it goes:** Update existing `frontend/src/shared/components/Breadcrumbs.jsx`

**Claude Code prompt:**
```
Update the existing Breadcrumbs component at frontend/src/shared/components/Breadcrumbs.jsx

Current behavior: basic navigation trail.
New behavior: richer path display with clickable steps.

Changes:
- Each breadcrumb item should accept an optional onClick handler or route path
- Items WITH a click handler: show in muted color #8a7e6d with subtle underline (color #d9cebb), cursor pointer
- The LAST item (current page): show in dark text #2c2418, font-weight 600, no underline, not clickable
- Separator: use › character with 4px horizontal margin
- Container: padding 10px 28px (matching page content padding), font size 12px
- Hide breadcrumbs when on the search page hero state (before a search has been made)

Each page component will pass its own breadcrumb items. For example, EmployerProfilePage would pass:
[
  { label: "Search", onClick: () => navigate('/search') },
  { label: "\"Walmart\"", onClick: () => navigate('/search?name=Walmart') },
  { label: "Walmart Inc." }  // no onClick = current page
]

Make sure existing tests still pass after this change.
```

---

## PHASE 2: Page-by-Page Updates

Now that the building blocks are ready, update each page. These are ordered by impact — the biggest improvements first.

---

### Step 2.1 — Employer Profile Page (Biggest Change)

**What's changing and why:**

This is the most data-heavy page and the one organizers spend the most time on. Right now it's a flat stack of cards organized into 3 tabs. The redesign introduces three "layers" of information:

- **Layer 1 (the "Glance"):** A dark hero banner at the top that immediately tells the story — company name, tier, composite score, and a one-line summary like "437 OSHA violations · 12 wage theft cases · $2.1B federal contracts · Non-union." This answers "should I care?" in 2 seconds.

- **Layer 2 (the "Scan"):** A row of MiniStat cards showing key numbers — workers, OSHA violations, wage cases, contract value. An organizer can scan all of these in 30 seconds.

- **Layer 3 (the "Deep Dive"):** Collapsible sections for each data area (OSHA, NLRB, Wage & Hour, etc.) that start collapsed with just a title and count. Click to expand and see full details.

The sidebar table of contents stays visible as you scroll, letting you jump between sections.

**What files are affected:**
- `frontend/src/features/employer-profile/EmployerProfilePage.jsx` — main layout restructure
- `frontend/src/features/employer-profile/ProfileHeader.jsx` — replace with hero banner
- `frontend/src/features/employer-profile/ScorecardSection.jsx` — replace bars with ScoreGauge grid
- All the detail card components stay but get wrapped in CollapsibleSection

**Claude Code prompt:**
```
Redesign the EmployerProfilePage. This is a major layout change. Reference prototype.jsx EmployerProfilePage for the target design.

STEP A — New Hero Banner (replaces ProfileHeader):
Replace the current ProfileHeader with a full-width dark hero banner.
- Background: linear-gradient(135deg, #2c2418 0%, #3d3225 100%)
- White/cream text
- Left side: company name in Source Serif 4 30px bold, TierBadge next to it, location/industry/NAICS/workers line below in 14px at 70% opacity
- Below that: a one-line summary box with left border in brick red (#c23a22), background rgba(250,246,239,0.08), containing key stats like "437 OSHA violations · 12 wage theft cases · $2.1B federal contracts · Non-union"
  - Build this summary from actual API data: count OSHA violations, WHD cases, SAM contract values, union status
- Right side: large composite score number (48px Source Serif 4 bold) with "COMPOSITE SCORE" label below
- Bottom row: source badges for all data sources present

STEP B — Layout with Sidebar:
Replace the tab-based layout with a two-column layout:
- Left column: SidebarTOC component (180px wide, sticky)
- Right column: main content (flex: 1, max-width ~820px)
- Use flexbox with gap 24px, padding 0 28px

Add IntersectionObserver logic to detect which section is currently in view and pass that as activeSection to SidebarTOC. Each section div needs an id attribute matching the sidebar section ids.

STEP C — MiniStat Row (Layer 2):
Below the hero, add a flex row of MiniStat cards:
- Workers (accent: teal) — from profile data
- OSHA Violations (accent: brick red) — from OSHA data, sub text showing serious count
- Wage Cases (accent: copper) — from WHD data, sub text showing back wages total
- Fed Contracts (accent: lake blue) — from SAM data

STEP D — Scorecard Section Update:
Replace the current bar-based ScorecardSection with a grid of ScoreGauge components.
- Wrap in a card with title "Scorecard Breakdown"
- Display all 9 scoring factors as ScoreGauge dials in a flex-wrap layout
- Each gauge shows the factor value and label

STEP E — Collapsible Detail Sections (Layer 3):
Wrap each existing detail section in CollapsibleSection (the existing CollapsibleCard may work, or create a new wrapper):
- OSHA section: default OPEN (most important for organizers), accent brick red, show count in title
- NLRB section: default collapsed, accent lake blue
- WHD section: default collapsed, accent saddle brown
- Government Contracts: default collapsed, accent lake blue
- Corporate Hierarchy: default collapsed, accent dusty purple
- Comparables: default collapsed
- Research Notes: default collapsed

Keep ALL the existing data-fetching and display logic inside each section. We're only changing the wrapper and default expanded/collapsed state.

STEP F — Action Buttons:
Move the action buttons (Flag as Target, Export, Something Looks Wrong) to the bottom of the main content area. Add a "Start Research" button that links to creating a new research run.
Style: flex row with gap, primary action (Flag) in brick red, others in card background with border.

IMPORTANT: Do NOT delete or break any existing API hooks or data fetching logic. The internal content of each section stays the same — we're reorganizing the LAYOUT around it.

Run tests after: cd frontend && npx vitest run
```

---

### Step 2.2 — Search Page

**What's changing:**

The search page already has a hero state (big centered search bar when no query) and a results state. The main improvements are:

1. **Platform stats under the hero search bar** — showing "107,025 Employers · 26,665 Unions · 6.8M Records · 18 Data Sources" so the user immediately understands the platform's scope
2. **Cleaner results header** — showing result count more prominently
3. **Filter button** instead of always-visible sidebar (filters slide out when you click the button)

**What files are affected:**
- `frontend/src/features/search/SearchPage.jsx`
- `frontend/src/features/search/SearchFilters.jsx`

**Claude Code prompt:**
```
Update the SearchPage with these improvements. Reference prototype.jsx SearchPage.

Change 1 — Hero State Enhancement:
In the hero state (before any search), add platform stats below the search bar:
- 4 stats in a flex row with gap 20px, centered, margin-top 40px
- Each stat: large number in Source Serif 4 22px bold teal color, small label below in 11px uppercase muted
- Stats: "107,025 Employers" | "26,665 Unions" | "6.8M+ Records" | "18 Data Sources"
- These can be hardcoded for now, or pulled from the usePlatformStats hook if available

Change 2 — Results State Header:
When results are showing:
- Add a result count line: "<strong>7 results</strong> for "walmart"" in 13px
- Add a compact "Filters" toggle button next to the search bar
- Move SearchFilters into a collapsible panel that slides down when the Filters button is clicked (instead of always visible as a sidebar)
- This gives more horizontal space to the results table

Change 3 — Improved Card View:
In card view mode, add a colored left border to each card based on tier:
- Priority: brick red left border
- Strong: teal left border  
- Promising: copper left border
- Others: default border

Keep all existing search logic, URL-synced state, pagination, and API hooks unchanged.
Run tests after.
```

---

### Step 2.3 — Targets Page

**What's changing:**

The targets page currently shows a table immediately. The redesign adds three layers:

1. **Glance:** A big headline with the Priority target count
2. **Tier distribution bar:** A horizontal stacked bar showing how many targets are in each tier — so you can visually see the distribution at a glance
3. **Top picks grid:** Cards for the top 5 Priority targets with their key signals
4. **Full table below** for detailed browsing

**What files are affected:**
- `frontend/src/features/scorecard/TargetsPage.jsx`
- `frontend/src/features/scorecard/TargetStats.jsx`

**Claude Code prompt:**
```
Redesign the TargetsPage with layered information. Reference prototype.jsx TargetsPage.

Change 1 — Page Header (Layer 1 — the Glance):
- Title "Organizing Targets" in Source Serif 4 32px bold
- Subtitle: "<strong red 22px>316</strong> Priority targets identified across 3,736 non-union employers"
- The "316" number should come from the useTargetStats hook data for the Priority tier count

Change 2 — Tier Distribution Bar:
Add a horizontal stacked bar chart below the header:
- Full width, 32px tall, border-radius 6px, border 1px #d9cebb
- 5 segments (Priority/Strong/Promising/Moderate/Low) proportional to their counts
- Each segment colored with its tier background color
- Show tier name and count as text inside segments (only if segment is wide enough — over ~12%)
- Data comes from useTargetStats hook

Change 3 — Top Priority Cards (Layer 2 — the Scan):
Add a grid of cards showing the top 5 Priority targets:
- Title: "Top Priority Targets" in Source Serif 4 18px
- Grid: auto-fill, min 260px columns, gap 14px
- Each card: cream background, brick red left border, padding 18px
- Inside: employer name (bold), score (large Source Serif 4 in brick red), industry + worker count, signal tags
- Cards are clickable — navigate to employer profile
- Hover effect: shadow increases
- Data: use the existing useNonUnionTargets hook, filtered/sorted to show Priority tier first

Change 4 — Full Table (Layer 3):
Keep the existing TargetsTable below, with a section header "All Targets" and a Filters button.
Add a rank number (#1, #2, #3...) as the first column.

Keep all existing filter logic, URL-synced state, and pagination.
Run tests after.
```

---

### Step 2.4 — Unions Page

**What's changing:**

Adding affiliation summary cards at the top (AFL-CIO, Change to Win, Independent) that show member counts at a glance, and making the tree view more visually polished with indentation lines and expand animations.

**What files are affected:**
- `frontend/src/features/union-explorer/UnionsPage.jsx`
- `frontend/src/features/union-explorer/NationalUnionsSummary.jsx`
- `frontend/src/features/union-explorer/AffiliationTree.jsx`

**Claude Code prompt:**
```
Update the UnionsPage with improvements. Reference prototype.jsx UnionsPage.

Change 1 — Page Header:
- Title "Union Explorer" in Source Serif 4 32px bold
- Subtitle: "26,665 organizations · 14.5M members" in muted text
- Tree/List toggle buttons on the right side of the header row

Change 2 — Affiliation Summary Cards:
Replace or enhance NationalUnionsSummary with 3 large cards in a flex row:
- AFL-CIO card: teal top border, name in Source Serif 4 18px, member count in large teal 24px font, local count below
- Change to Win card: copper top border, same layout
- Independent card: lake blue top border, same layout
- Data from useNationalUnions hook

Change 3 — Tree View Polish:
In AffiliationTree, improve the visual hierarchy:
- Parent level (AFL-CIO etc): slightly larger text, Source Serif 4 16px semibold, expand arrow that rotates 90° on open
- When expanded, children connected by a left border line (2px solid #d9cebb) with padding-left 16px
- Child items: clickable rows that navigate to the union profile, with hover highlight
- Show member count on the right side of each row in teal font

Keep all existing data fetching and expand/collapse logic.
Run tests after.
```

---

### Step 2.5 — Union Profile Page

**What's changing:**

Adding a colored hero banner (teal gradient, matching the union theme) with key stats prominently displayed, and MiniStat cards below for a quick scan.

**What files are affected:**
- `frontend/src/features/union-explorer/UnionProfilePage.jsx`
- `frontend/src/features/union-explorer/UnionProfileHeader.jsx`

**Claude Code prompt:**
```
Update the UnionProfilePage. Reference prototype.jsx UnionProfilePage.

Change 1 — Hero Banner:
Replace UnionProfileHeader with a teal gradient banner:
- Background: linear-gradient(135deg, #1a6b5a 0%, #2a8a74 100%)
- White/cream text
- Top line: affiliation path in small uppercase (e.g., "AFL-CIO › SEIU") at 70% opacity
- Union name: Source Serif 4 28px bold
- Stats row: 4 large numbers side by side (Members, Election Win Rate, States Active, Annual Revenue)
  - Each: large number in Source Serif 4 28px bold, small label below at 70% opacity

Change 2 — MiniStat Row:
Add a row of MiniStat cards below the hero:
- Organizing Staff (accent teal)
- Recent Elections (accent lake blue)
- Avg Contract Length (accent copper)
- Growth Rate (accent forest green) — show as percentage with +/- sign
- Pull data from useUnionDetail hook

Change 3 — Collapsible Sections:
Wrap existing sections in CollapsibleSection:
- Membership Trends: default open, teal accent. If you have year-over-year data, show a simple bar chart (vertical bars for each year)
- NLRB Elections: default collapsed, lake blue accent
- Employers Under Contract: default collapsed, copper accent. Make employer names clickable (navigate to their profile)
- Expansion Targets: default collapsed
- Financials: default collapsed, dusty purple accent

Keep all existing API hooks and data display logic inside sections.
Run tests after.
```

---

### Step 2.6 — Research Page

**What's changing:**

Adding summary stats at the top, and improving the status indicators to be more visual (colored dots with labels, animated pulse for running jobs).

**What files are affected:**
- `frontend/src/features/research/ResearchPage.jsx`
- `frontend/src/features/research/ResearchRunsTable.jsx`

**Claude Code prompt:**
```
Update the ResearchPage. Reference prototype.jsx ResearchPage.

Change 1 — Page Header:
- Title and subtitle on the left
- "+ New Research" button on the right in teal background, white text

Change 2 — Stats Row:
Add MiniStat cards:
- Total Runs (accent teal)
- Completed (accent forest green)
- Total Facts (accent copper)
- Avg Cost (accent lake blue)
- Data from useResearchRuns hook (aggregate the counts)

Change 3 — Status Indicators:
In the ResearchRunsTable, upgrade status display:
- Each status gets a pill-shaped badge with a small colored dot + text
- "completed": forest green dot + green-tinted background
- "running": copper dot with CSS pulse animation + copper-tinted background
- "failed": brick red dot + red-tinted background
- "pending": muted gray dot + gray-tinted background
- The pulse animation: @keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.4 } } applied to the dot element

Keep all existing data fetching and filter logic.
Run tests after.
```

---

### Step 2.7 — Research Result Page (Dossier)

**What's changing:**

Better visual hierarchy for the dossier — a header card with run metadata, then collapsible sections per research category, with each fact styled as a card with confidence-colored left border.

**What files are affected:**
- `frontend/src/features/research/ResearchResultPage.jsx`
- `frontend/src/features/research/DossierSection.jsx`
- `frontend/src/features/research/FactRow.jsx`

**Claude Code prompt:**
```
Update the ResearchResultPage. Reference prototype.jsx ResearchResultPage.

Change 1 — Dossier Header:
- Card with company name + "Research Dossier" in Source Serif 4 26px
- Metadata line: "Completed [date] · [duration] · [fact count] facts discovered · [cost]"
- Export button on the right

Change 2 — Dossier Sections:
Wrap each DossierSection in CollapsibleSection:
- First 2 sections default open, rest collapsed
- Show fact count in the title: "Company Overview (3 facts)"

Change 3 — Fact Rows:
Style each fact with:
- Left border colored by confidence: forest green (#3a7d44) for high, copper (#c78c4e) for medium, warm stone (#d9cebb) for low
- Background: parchment #f5f0e8
- Fact text in 13px
- Source and confidence metadata below in 11px muted text
- Confidence text colored to match the left border

Keep all existing polling logic and API hooks.
Run tests after.
```

---

### Step 2.8 — Admin/Settings Page

**What's changing:**

Adding a health status indicator with a green dot, stat cards at the top, and making the data freshness table show stale warnings more prominently.

**What files are affected:**
- `frontend/src/features/admin/SettingsPage.jsx`
- `frontend/src/features/admin/HealthStatusCard.jsx`
- `frontend/src/features/admin/DataFreshnessCard.jsx`

**Claude Code prompt:**
```
Update the SettingsPage. Reference prototype.jsx SettingsPage.

Change 1 — Health + Stats Row:
Replace the current card grid top row with:
- System Health card: green/red dot + "All Systems Operational" or error message, API/DB response times below
- 3 MiniStat cards: Total Employers, Data Sources (record count), Pending Flags
- All in one flex row

Change 2 — Data Freshness:
In DataFreshnessCard, update the display:
- Each data source on its own row with: source badge, record count, last update date, refresh button
- If stale (flag from API), show a ⚠ warning icon before the date in brick red color
- Refresh buttons on the right side of each row

Change 3 — Collapsible Sections:
Wrap the other admin cards in CollapsibleSection:
- Data Freshness: default open, teal accent
- Match Quality: default collapsed, lake blue accent
- Pending Flags: default collapsed, brick red accent (show count in title)
- User Management: default collapsed, dusty purple accent

Keep all existing admin API hooks and polling logic.
Run tests after.
```

---

### Step 2.9 — Login Page Polish

**What's changing:** Minor visual upgrade — adding a warm gradient background and centering the card with a bigger shadow for a more polished first impression.

**What files are affected:**
- `frontend/src/features/auth/LoginPage.jsx`

**Claude Code prompt:**
```
Polish the LoginPage. Reference prototype.jsx LoginPage.

- Center the login card vertically and horizontally (flexbox, min-height 85vh)
- Background: subtle gradient from parchment to linen
- Card: cream background, 1px border, border-radius 10px, padding 40px, width 380px
- Big box shadow: 0 8px 40px rgba(0,0,0,0.08)
- Logo/title at top: "LABOR INTEL" in Source Serif 4 24px bold with copper gear icon
- Subtitle: "Sign in to your account" in 13px muted
- Input styling: parchment background, border #d9cebb, border-radius 6px
- Sign In button: full width, teal background, white text, border-radius 6px

Keep all existing auth logic, error handling, and redirect behavior.
Run tests after.
```

---

## PHASE 3: NavBar Update

### Step 3.1 — NavBar Enhancements

**Claude Code prompt:**
```
Update the NavBar at frontend/src/shared/components/NavBar.jsx

Changes:
1. Add the "Quick Jump… ⌘K" button on the right side of the nav bar
   - Style: semi-transparent background, subtle border, muted text, small "⌘K" keyboard hint badge
   - On click: opens the CommandPalette
   
2. Add active state styling to nav links:
   - Current page link: copper color (#c78c4e), font-weight 600, 2px bottom border in copper
   - Other links: white at 70% opacity, no bottom border
   
3. Integrate CommandPalette:
   - Import and render CommandPalette in the Layout component
   - Add useEffect for Ctrl+K / Cmd+K keyboard shortcut
   - State: isCommandPaletteOpen, managed in Layout

Run tests after.
```

---

## PHASE 4: Cross-Cutting Improvements

These are smaller improvements that affect multiple pages.

### Step 4.1 — Cross-Linking Between Pages

**What this means:** When data on one page mentions something that exists on another page, it should be a clickable link. For example: a union name on an employer profile should link to that union's profile. An employer name on a union's "Employers Under Contract" list should link to that employer's profile.

**Claude Code prompt:**
```
Add cross-linking between pages:

1. EmployerProfilePage — UnionRelationshipsCard:
   Any union name displayed should be a clickable link that navigates to /unions/{fnum}
   Style: teal color, underline on hover

2. UnionProfilePage — UnionEmployersTable:
   Any employer name should be a clickable link to /employers/{id}
   Style: teal color, underline on hover

3. TargetsPage — TargetsTable:
   Employer names in the table should link to /employers/{id}
   (They may already be clickable via row click — make sure the name specifically is styled as a link)

4. ResearchPage — ResearchRunsTable:
   Employer names should link to /employers/{id}

5. ComparablesCard:
   Comparable employer names should link to /employers/{id}

Use React Router's Link component or useNavigate for all navigation.
Run tests after.
```

---

### Step 4.2 — Collapsible State Persistence

**What this means:** When a user expands or collapses a section on the employer profile page, that preference should be remembered. So if they always want OSHA expanded and Contracts collapsed, it stays that way as they browse between different employers.

**How it works:** Save the expanded/collapsed state of each section in the browser's local storage (localStorage). When the page loads, check localStorage for saved preferences. If none exist, use the defaults (OSHA open, everything else collapsed).

**Claude Code prompt:**
```
Add collapsible section state persistence using localStorage.

Create a custom hook: frontend/src/shared/hooks/useCollapsibleState.js

const useCollapsibleState = (pageKey, sectionId, defaultOpen = false) => {
  // Read initial state from localStorage key like "collapse:employer:osha"
  // Return [isOpen, toggle] similar to useState
  // When toggled, save new state to localStorage
}

Update all CollapsibleSection usages on EmployerProfilePage and UnionProfilePage to use this hook.
The pageKey differentiates between pages (e.g., "employer" vs "union").
The sectionId identifies which section (e.g., "osha", "nlrb", "whd").

This way, if a user always expands OSHA, it stays expanded on every employer they visit.

Run tests after.
```

---

## PHASE 5: Run Full Test Suite & Fix

After all changes, run the full test suite and fix any failures.

**Claude Code prompt:**
```
Run the full test suite:
cd frontend && npx vitest run

If any tests fail:
1. Read the error message carefully
2. Determine if the test needs updating (because we changed the component's structure) or if there's an actual bug
3. For structural changes (e.g., ProfileHeader no longer exists as a separate component), update the test to match the new structure
4. For actual bugs, fix the component code
5. Re-run until all tests pass

Also check that the dev server starts cleanly:
cd frontend && VITE_DISABLE_AUTH=true npx vite

Open in browser and verify each page loads without console errors.
```

---

## Summary: Order of Work

| Step | What | Estimated Effort |
|------|------|-----------------|
| 1.1-1.5 | Build shared components | Small per component |
| 2.1 | Employer Profile redesign | Large — most complex page |
| 2.2 | Search page updates | Medium |
| 2.3 | Targets page layers | Medium |
| 2.4 | Unions page improvements | Medium |
| 2.5 | Union Profile hero + sections | Medium |
| 2.6 | Research page stats + status | Small |
| 2.7 | Research Result dossier styling | Small |
| 2.8 | Admin page polish | Small |
| 2.9 | Login page polish | Small |
| 3.1 | NavBar + CommandPalette | Medium |
| 4.1 | Cross-linking | Small |
| 4.2 | Collapsible persistence | Small |
| 5 | Test suite fix-up | Depends on breakage |

**Total: ~15 distinct work sessions with Claude Code, roughly 2-3 days of work.**

---

## Reference: Prototype File

The `prototype.jsx` file contains a complete interactive mockup of all pages. When Claude Code needs to see the target design for any component, point it to this file. The prototype uses inline styles for simplicity, but your actual implementation should use Tailwind classes matching the existing theme system.
