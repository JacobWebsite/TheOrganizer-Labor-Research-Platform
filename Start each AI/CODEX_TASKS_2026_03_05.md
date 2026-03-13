# Codex Task Batch - 2026-03-05

4 independent tasks. No dependencies between them. All can be implemented in parallel.

**Context files to read first:**
- `Start each AI/CLAUDE.md` -- technical reference, schema, gotchas
- `Start each AI/PROJECT_STATE.md` -- current status
- `frontend/src/features/research/DossierSection.jsx` -- existing component (248 lines)
- `frontend/src/features/research/ResearchResultPage.jsx` -- existing page (342 lines)
- `frontend/__tests__/ResearchResult.test.jsx` -- existing tests (230 lines)
- `scripts/research/agent.py` -- research agent (lines 42, 330-399, 618-627, 900-908 are key)

**Test commands:**
- Backend: `py -m pytest tests/ -x -q` (expect 1135 pass, 0 fail, 3 skip)
- Frontend: `cd frontend && npx vitest run` (expect ~249 pass)

---

## Task 1: R3-6 -- Add New Dossier Sections (Corporate Structure, Locations, Leadership)

**Goal:** Expand the dossier from 7 sections to 10 by adding Corporate Structure, Locations, and Leadership.

### Backend changes (`scripts/research/agent.py`)

1. **Line 42** -- Update `_DOSSIER_SECTIONS`:
```python
_DOSSIER_SECTIONS = ["identity", "corporate_structure", "locations", "leadership", "financial", "workforce", "labor", "workplace", "assessment", "sources"]
```

2. **Line 904** -- Update the local `_DOSSIER_SECTIONS` set (used for counting filled sections):
```python
_DOSSIER_SECTIONS = {"identity", "corporate_structure", "locations", "leadership", "labor", "assessment", "workforce", "workplace", "financial", "sources"}
```

3. **Lines 376-399** -- Update the JSON template in the system prompt to include new sections:
```json
{
  "dossier": {
    "identity": { ... },
    "corporate_structure": { ... },
    "locations": { ... },
    "leadership": { ... },
    "financial": { ... },
    "workforce": { ... },
    "labor": { ... },
    "workplace": { ... },
    "assessment": { ... },
    "sources": { ... }
  },
  "facts": [ ... ]
}
```

4. **Lines 334-374** -- Add instructions in the system prompt for populating new sections. After the existing instructions (step 4), add guidance:
```
6. **Populate the new dossier sections:**
   - **corporate_structure**: parent company, parent type (public/private/PE/nonprofit), known subsidiaries, investors, corporate family context. Use data from search_gleif_ownership, search_sec, search_mergent, search_solidarity_network. If no parent found, note "Appears to be an independent company."
   - **locations**: all known employer addresses from OSHA establishments, SAM entities, SOS filings, and web scrape. Group by city/state. Include establishment counts per location if available.
   - **leadership**: CEO/president, executive team, local management. Source from search_sos_filings (officers/directors), search_sec (for public companies), and web scrape of "about us" / "leadership" pages.
```

5. **Line 621** -- The filter `if sec not in _DOSSIER_SECTIONS: continue` will automatically accept facts for new sections once `_DOSSIER_SECTIONS` is updated. No change needed here.

### Frontend changes

**`frontend/src/features/research/DossierSection.jsx`:**

1. Add icons import -- add `MapPin, Crown, Network` (or similar) from `lucide-react`:
```javascript
import {
  Building2, Users, HardHat, DollarSign, Briefcase, ClipboardCheck, Database,
  CheckCircle, XCircle, MapPin, Crown, Network,
} from 'lucide-react'
```

2. Add new entries to `SECTION_META` (line 8):
```javascript
const SECTION_META = {
  identity:             { icon: Building2,      label: 'Company Identity',      defaultOpen: true },
  corporate_structure:  { icon: Network,        label: 'Corporate Structure',   defaultOpen: true },
  locations:            { icon: MapPin,         label: 'Locations',             defaultOpen: false },
  leadership:           { icon: Crown,          label: 'Leadership',            defaultOpen: false },
  labor:                { icon: Users,           label: 'Labor Relations',       defaultOpen: true },
  workforce:            { icon: Briefcase,       label: 'Workforce',             defaultOpen: false },
  workplace:            { icon: HardHat,         label: 'Workplace Safety',      defaultOpen: false },
  financial:            { icon: DollarSign,      label: 'Financial',             defaultOpen: false },
  assessment:           { icon: ClipboardCheck,  label: 'Overall Assessment',    defaultOpen: true },
  sources:              { icon: Database,         label: 'Data Sources',          defaultOpen: false },
}
```

3. Add new entries to `KEY_LABELS` (line 19):
```javascript
// Corporate Structure
parent_company: 'Parent Company', parent_type: 'Parent Type',
subsidiaries: 'Subsidiaries', investors: 'Investors',
corporate_family: 'Corporate Family', ownership_chain: 'Ownership Chain',
// Locations
locations: 'Known Locations', total_locations: 'Total Locations',
headquarters: 'Headquarters', location_states: 'States with Presence',
// Leadership
ceo: 'CEO/President', executives: 'Executive Team',
local_leadership: 'Local Management', board_of_directors: 'Board of Directors',
registered_agent: 'Registered Agent', company_officers: 'Company Officers',
```
Note: `registered_agent` and `company_officers` already exist in KEY_LABELS. Don't duplicate.

**`frontend/src/features/research/ResearchResultPage.jsx`:**

Update `SECTION_ORDER` (line 17):
```javascript
const SECTION_ORDER = [
  'identity',
  'corporate_structure',
  'locations',
  'leadership',
  'labor',
  'assessment',
  'workforce',
  'workplace',
  'financial',
  'sources',
]
```

### Test updates (`frontend/__tests__/ResearchResult.test.jsx`)

1. Update `MOCK_RESULT.dossier.dossier` to include new sections:
```javascript
dossier: {
  identity: { legal_name: 'Amazon.com Inc.', company_type: 'public' },
  corporate_structure: { parent_company: 'Amazon.com Inc.', parent_type: 'public' },
  locations: { total_locations: 5, headquarters: 'Seattle, WA' },
  leadership: { ceo: 'Andy Jassy' },
  labor: { union_names: ['Teamsters', 'ALU'], nlrb_election_count: 15 },
  assessment: { organizing_summary: 'Active NLRB cases and recent organizing campaigns.' },
  workplace: { osha_violation_count: 23 },
},
```

2. Update the `sections_filled: 7` values in `MOCK_STATUS_COMPLETED` and `MOCK_RESULT` -- keep at 7 since not all mock sections have data. The `7/7` assertion in the metadata grid test (line 167) should change to match the new section count. Since mock data fills 7 sections out of 10, update the assertion:
```javascript
expect(screen.getByText('7/10')).toBeInTheDocument()
```
Wait -- check the actual rendering logic. The `7/7` comes from `sections_filled` in the status response. The denominator is the total section count. Look at `DossierHeader.jsx` to see how it renders. If it uses `sections_filled` and hardcodes the denominator, update the denominator. If it computes it from `SECTION_ORDER`, it will auto-update.

3. Add a test for new section rendering:
```javascript
it('renders new dossier sections for completed run', () => {
  useResearchStatus.mockReturnValue({ data: MOCK_STATUS_COMPLETED, isLoading: false, isError: false })
  useResearchResult.mockReturnValue({ data: MOCK_RESULT, isLoading: false, isError: false })
  renderResultPage()
  expect(screen.getByText(/Corporate Structure/)).toBeInTheDocument()
  expect(screen.getByText(/Locations/)).toBeInTheDocument()
  expect(screen.getByText(/Leadership/)).toBeInTheDocument()
})
```

### Update hardcoded "/7" section denominators

The old 7-section count is hardcoded in several files. Update all to `/10`:

- `frontend/src/features/research/DossierHeader.jsx` line 104: `${status.sections_filled}/7` -> `${status.sections_filled}/10`
- `frontend/src/features/research/CompareRunsPage.jsx` line 53: `${run.sections_filled}/7` -> `${run.sections_filled}/10`
- `frontend/src/features/research/ResearchRunsTable.jsx` line 104: `${run.sections_filled}/7` -> `${run.sections_filled}/10`

### Verification
- `cd frontend && npx vitest run` -- all tests pass
- The test assertion `expect(screen.getByText('7/7'))` in `ResearchResult.test.jsx` must change to `expect(screen.getByText('7/10'))` (7 filled out of 10 total)
- The new sections render correctly in the dossier view (empty sections auto-hide via line 150 of DossierSection.jsx: `if (!narrative && factCount === 0) return null`)

---

## Task 2: 6-3 -- Employer Comparison View

**Goal:** New page at `/compare` that shows 2-3 employers side-by-side with a radar chart of scoring factors.

### New files

**`frontend/src/features/scorecard/CompareEmployersPage.jsx`** (new)

Core behavior:
1. URL params: `/compare?ids=ABC123,DEF456,GHI789` (comma-separated employer IDs, max 3)
2. Fetch scorecard data for each employer via `useScorecardDetail(id)` from `@/shared/api/profile`
3. Display a radar chart (use `recharts` -- already in package.json? If not, use a simple SVG radar) with these factors:
   - OSHA (factor: `score_osha`)
   - NLRB (factor: `score_nlrb`)
   - WHD (factor: `score_whd`)
   - Contracts (factor: `score_contracts`)
   - Financial (factor: `score_financial`)
   - Industry Growth (factor: `score_industry_growth`)
   - Union Proximity (factor: `score_union_proximity`)
   - Similarity (factor: `score_similarity`)
   - Size (factor: `score_size`)
4. Below the radar chart, show a comparison table with key metrics side-by-side:
   - Employer name, state, NAICS
   - Overall `weighted_score`
   - `score_tier`
   - Each factor score (0-10)
   - `factors_available` count
5. Entry point: Add "Compare" button to the targets page that opens the compare view with selected employers

### Routing (`frontend/src/App.jsx`)

Add a new route:
```javascript
const CompareEmployersPage = lazy(() => import('@/features/scorecard/CompareEmployersPage').then(m => ({ default: m.CompareEmployersPage })))
// ...
<Route path="compare" element={<Suspense fallback={<PageSkeleton />}><CompareEmployersPage /></Suspense>} />
```

### API data shape

The scorecard detail endpoint (`/api/scorecard/unified/{id}`) returns:
```json
{
  "employer_id": "...",
  "employer_name": "...",
  "state": "...",
  "naics": "...",
  "weighted_score": 4.5,
  "score_tier": "Strong",
  "factors_available": 5,
  "score_osha": 6.2,
  "score_nlrb": 8.0,
  "score_whd": null,
  "score_contracts": 3.0,
  "score_financial": null,
  "score_industry_growth": 5.5,
  "score_union_proximity": 4.0,
  "score_similarity": null,
  "score_size": 3.0,
  "has_research": false
}
```

### Design notes
- Use the "Aged Broadsheet" theme (see `UNIFIED_PLATFORM_REDESIGN_SPEC.md`)
- Colors: use the theme's palette from `frontend/src/index.css` (CSS variables)
- Radar chart colors: employer 1 = `#3a6b8c` (steel blue), employer 2 = `#c78c4e` (amber), employer 3 = `#3a7d44` (green)
- If only 1 employer is provided, show an empty slot with "Add employer to compare" placeholder
- If no IDs in URL, show a search/select interface

### Targets page integration

In `frontend/src/features/scorecard/TargetsPage.jsx`, add a way to select employers and navigate to compare:
- Add checkbox column to the targets table
- Add "Compare Selected" button (disabled until 2+ selected, max 3)
- Button navigates to `/compare?ids=id1,id2,id3`

### Tests

**`frontend/__tests__/CompareEmployers.test.jsx`** (new):
```javascript
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClientProvider, QueryClient } from '@tanstack/react-query'

// Test that:
// 1. Page renders with 2 employer IDs in URL
// 2. Shows employer names and scores
// 3. Shows comparison table with factor scores
// 4. Handles missing/loading state gracefully
// 5. Shows "Add employer" placeholder when fewer than 3 employers
```

### Charting library
No charting library is currently installed. Two options:
1. **Install recharts:** `cd frontend && npm install recharts` -- provides `RadarChart`, `PolarGrid`, `PolarAngleAxis`, `Radar` components out of the box
2. **Build a simple SVG radar manually** -- avoids a new dependency. A 9-axis radar is straightforward with `<polygon>` and trig.

Either approach is fine. If installing recharts, only use it in this component -- don't refactor existing code.

---

## Task 3: 6-6 -- Build Outcome Feedback Loop

**Goal:** Let users record campaign outcomes (Won/Lost/Abandoned/In Progress) for flagged employers. Eventually validates scoring.

### Database (`scripts/etl/create_campaign_outcomes.py` -- new)

```python
"""Create campaign_outcomes table."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

def main():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_outcomes (
            id SERIAL PRIMARY KEY,
            employer_id TEXT NOT NULL,
            employer_name TEXT,
            outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('won', 'lost', 'abandoned', 'in_progress')),
            notes TEXT,
            reported_by VARCHAR(100),
            outcome_date DATE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaign_outcomes_employer
        ON campaign_outcomes(employer_id)
    """)
    print("campaign_outcomes table created.")
    conn.close()

if __name__ == "__main__":
    main()
```

### API endpoint (`api/main.py`)

Add two endpoints:

```python
# GET /api/campaigns/outcomes/{employer_id}
# Returns: list of outcomes for this employer

# POST /api/campaigns/outcomes
# Body: { employer_id, employer_name, outcome, notes, reported_by, outcome_date }
# Returns: { id, created_at }
```

Look at existing endpoint patterns in `api/main.py` for style. Use `get_connection()`, `RealDictCursor`, and return JSON. The POST should INSERT and return the new row's id.

### Frontend

**`frontend/src/shared/api/campaigns.js`** (new):
```javascript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export function useCampaignOutcomes(employerId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['campaign-outcomes', employerId],
    queryFn: () => apiClient.get(`/api/campaigns/outcomes/${employerId}`),
    enabled: enabled && !!employerId,
  })
}

export function useRecordOutcome() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.post('/api/campaigns/outcomes', data),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['campaign-outcomes', variables.employer_id] })
    },
  })
}
```

**`frontend/src/features/employer-profile/CampaignOutcomeCard.jsx`** (new):

A collapsible card that:
1. Shows existing outcomes (if any) as a timeline/list
2. Has a "Record Outcome" button that opens a form:
   - Outcome dropdown: Won / Lost / Abandoned / In Progress
   - Notes textarea
   - Date picker (optional)
3. Submits via `useRecordOutcome()`
4. Uses the theme: icon from lucide (`Target` or `Flag`), CollapsibleCard pattern

**Wire into `EmployerProfilePage.jsx`:**
- Import `CampaignOutcomeCard`
- Add after `ResearchNotesCard` (line ~24 area)
- Pass `employerId` and `employerName`
- Add `{ id: 'outcomes', label: 'Outcomes' }` to `PROFILE_SECTIONS`

### Tests

**`frontend/__tests__/CampaignOutcome.test.jsx`** (new):
- Test that the card renders with no outcomes
- Test that existing outcomes display correctly
- Test that the form opens and submits
- Mock `useCampaignOutcomes` and `useRecordOutcome`

**`tests/test_campaign_outcomes.py`** (new):
- Test POST creates a record
- Test GET returns records
- Test outcome validation (only won/lost/abandoned/in_progress)
- Test employer_id is required
- Pattern: look at `tests/test_research_api.py` for API test patterns

---

## Task 4: 4-8 -- Tool Effectiveness Monitoring and Pruning

**Goal:** Monitor research tool performance (hit rates, latency, fact yield) and identify tools to skip or deprioritize.

### New file: `scripts/analysis/tool_effectiveness.py`

This is an analysis script (read-only, no DB writes). It queries `research_actions` to build a report.

### Database schema reference

```sql
-- research_actions stores every tool call from every research run
-- Columns (verified): id, run_id, tool_name, tool_params, execution_order,
--   data_found (bool), data_quality, facts_extracted (int), result_summary,
--   latency_ms, cost_cents, error_message, company_context, created_at
-- NOTE: no started_at/completed_at -- latency_ms is the timing column
```

### Script logic

```python
"""Analyze research tool effectiveness from research_actions table.

Reports:
1. Per-tool hit rate (% of calls where data_found=true)
2. Per-tool avg latency (ms)
3. Per-tool avg facts extracted (when data found)
4. Per-tool error rate
5. Recommendations: tools with <10% hit rate AND >500ms avg latency -> "consider skipping"
6. Time savings estimate: if we skip low-value tools, how much faster would runs be?

Usage:
    py scripts/analysis/tool_effectiveness.py
    py scripts/analysis/tool_effectiveness.py --min-runs 5  # only tools called 5+ times
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection

def main():
    parser = argparse.ArgumentParser(description="Analyze research tool effectiveness")
    parser.add_argument("--min-runs", type=int, default=3, help="Minimum calls to include tool (default 3)")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    # 1. Per-tool statistics
    cur.execute("""
        SELECT tool_name,
               COUNT(*) AS total_calls,
               COUNT(*) FILTER (WHERE data_found = true) AS hits,
               COUNT(*) FILTER (WHERE error_message IS NOT NULL AND error_message != '') AS errors,
               ROUND(AVG(latency_ms)) AS avg_latency_ms,
               ROUND(AVG(latency_ms) FILTER (WHERE data_found = true)) AS avg_latency_hit_ms,
               ROUND(AVG(facts_extracted) FILTER (WHERE data_found = true), 1) AS avg_facts_when_hit,
               SUM(latency_ms) AS total_time_ms
        FROM research_actions
        GROUP BY tool_name
        HAVING COUNT(*) >= %s
        ORDER BY COUNT(*) DESC
    """, (args.min_runs,))
    rows = cur.fetchall()
    # ... format and print report

    # Column indices: tool_name=0, total=1, hits=2, errors=3, avg_lat=4, avg_lat_hit=5, avg_facts=6, total_time=7

    print(f"{'Tool':<35} {'Calls':>6} {'Hits':>6} {'Hit%':>6} {'Err%':>6} {'AvgMs':>7} {'Facts':>6} {'TotalS':>8}")
    print("-" * 90)
    skip_candidates = []
    for row in rows:
        name, total, hits, errors, avg_lat, avg_lat_hit, avg_facts, total_time = row
        hit_pct = (hits / total * 100) if total else 0
        err_pct = (errors / total * 100) if total else 0
        avg_facts_str = f"{avg_facts:.1f}" if avg_facts else "-"
        print(f"{name:<35} {total:>6} {hits:>6} {hit_pct:>5.1f}% {err_pct:>5.1f}% {avg_lat or 0:>6.0f}ms {avg_facts_str:>6} {(total_time or 0)/1000:>7.1f}s")
        if hit_pct < 10 and (avg_lat or 0) > 500:
            skip_candidates.append((name, hit_pct, avg_lat))

    print()
    if skip_candidates:
        print("SKIP CANDIDATES (hit rate <10% AND avg latency >500ms):")
        for name, hit_pct, avg_lat in skip_candidates:
            print(f"  {name}: {hit_pct:.1f}% hit rate, {avg_lat:.0f}ms avg latency")
        total_skip_time = sum(
            row[7] for row in rows
            if row[0] in [s[0] for s in skip_candidates]
        )
        print(f"\n  Potential time savings: {total_skip_time/1000:.1f}s total across all runs")
        total_runs = None
        cur.execute("SELECT COUNT(DISTINCT run_id) FROM research_actions")
        total_runs = cur.fetchone()[0]
        if total_runs:
            print(f"  Average savings per run: {total_skip_time/1000/total_runs:.1f}s")

    conn.close()

if __name__ == "__main__":
    main()
```

### Verification
- Run: `py scripts/analysis/tool_effectiveness.py`
- Should produce a formatted table of tool performance
- No DB writes, safe to run anytime

---

## Important Reminders

- **Windows cp1252 encoding** -- use ASCII in print() statements, no Unicode arrows/symbols
- **Do NOT pipe Python through grep** on Windows (hangs)
- **`db_config.py` is at project root** -- 500+ imports, never move
- **Test after every change**: `py -m pytest tests/ -x -q` and `cd frontend && npx vitest run`
- **Do NOT commit** unless explicitly asked
- **Existing test count**: 1135 backend (0 fail, 3 skip), ~249 frontend
- **Font/theme**: "Aged Broadsheet" -- editorial serif headings (`font-editorial`), muted earth tones. See `UNIFIED_PLATFORM_REDESIGN_SPEC.md`.
- **Component patterns**: Use `CollapsibleCard` for new cards, `lucide-react` for icons, TanStack Query for data fetching
- **API patterns**: Use `get_connection()`, `psycopg2.extras.RealDictCursor`, return JSON dicts
