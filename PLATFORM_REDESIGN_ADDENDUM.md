# Platform Redesign Specification — Addendum
## Remaining Topics Covered | February 20, 2026
## Append to PLATFORM_REDESIGN_SPEC.md

---

# 9. SECURITY & AUTHENTICATION

| Decision | Choice |
|----------|--------|
| Login method | Invite-only (admin creates accounts, no self-registration) |
| Password requirements | Minimum 12 characters, must include number + special character |
| Two-factor auth | Not required (can add later) |
| Session timeout | 1 hour sliding (already decided) |
| Initial scale | Start small, architecture supports growth |
| Auth implementation | Already built (JWT-based), currently disabled for development |

**Deployment note:** The `.env` file currently has `DISABLE_AUTH=true` — this MUST be removed before any deployment.

---

# 10. OLMS DATA ON UNION PROFILES

## What to Surface
- **Membership trends:** Year-over-year member counts
- **Financial health:** Full breakdown — revenue by source, expenses by category
- **NOT included:** Organizing spend, officer/leadership data

## Display
- Both appear as new collapsible cards on the union profile page
- Membership trends: sparkline chart showing the trend + actual yearly numbers below the chart
- Financial health: full breakdown table (revenue sources, expense categories like organizing, admin, representation)

## Membership Display (Covered Workers vs Dues-Paying)
- Union profile header shows **dues-paying members** as the default number
- **Covered workers** available on hover or in the membership trends detail card
- The gap between the two numbers shown inside the membership trends card only (not in header)

## Updated Union Profile Structure
**Header (always visible):**
- Union name, abbreviation, affiliation, dues-paying member count, employer count, local count

**Below header:**
1. Relationship map (expandable indented list — already decided)
2. Membership Trends (NEW — sparkline chart + yearly numbers + covered vs dues breakdown)
3. Financial Health (NEW — full revenue/expense breakdown by category)

---

# 11. DEEP DIVE TOOL (Workforce Demographics + Web Scraper Combined)

## Architecture
The Deep Dive is a single button on employer profiles that runs two steps in sequence:

### Step 1: Government Workforce Data (fast — seconds)
Pulls from pre-loaded databases, matched by employer's industry code and location:
- **BLS Occupational Matrix** — "what kinds of jobs exist at employers like this"
- **ACS PUMS Demographics** — "who tends to work in this industry in this area" (age, race, education, income)
- **Revenue-to-Headcount Estimation** — estimate employee count when no official count exists
- **O*NET Job Characteristics** — "what these jobs are actually like" (skills, education, physical demands, automation risk)

### Step 2: Web Research (slower — runs in background)
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
- Example: "Walmart has 14 open warehouse positions in your target region, suggesting expansion or high turnover. Recent news coverage includes a wage theft lawsuit filed in January 2026 (Source: Reuters¹)..."

## Permissions
- **Trigger a deep dive:** Researcher + Admin only
- **View saved results:** All roles (Viewer, Researcher, Admin)

## Results Storage
- Saved permanently to the employer profile
- Future visitors see results without re-running
- Shows "Last researched: [date]" with option to re-run

## Display
- Results appear as a new "Deep Dive Results" section below all existing profile cards
- Only visible on profiles where a deep dive has been run
- "Deep Dive Available" badge shown on search results for researched employers

## Button Behavior
- On profiles with no deep dive: shows "Run Deep Dive" button (Researcher/Admin only)
- On profiles with existing results: shows "Last researched: [date]" + "Re-run" option
- While running: progress indicator showing Step 1 (workforce data) → Step 2 (web research)
- Step 1 results appear first while Step 2 loads in background

---

# 12. IRS BUSINESS MASTER FILE

| Decision | Choice |
|----------|--------|
| Scope | Load full 1.8 million rows (not just unions) |
| Timing | Now — before frontend work begins |
| Value for unions | EIN-based matching/verification, help resolve 166 missing unions |
| Value for employers | Nonprofit employer data (hospitals, universities, social services) — financial classification, EINs, addresses |
| Scoring impact | Nonprofits are major organizing targets; BMF provides matching and verification data |

---

# UPDATED CLAUDE CODE TASK LIST

## Immediate (Before Frontend)
1. Run materialized view refresh (NLRB decay, NLRB flag fix, BLS financial fix)
2. Query top 10 biggest missing unions by worker count
3. Verify legacy table alignment across sources
4. Investigate search duplicate scope
5. **Load full IRS Business Master File (1.8M rows)** ← NEW
6. Design master employer table schema
7. Build SAM.gov → master list seeding pipeline
8. Build Mergent → master list matching pipeline
9. Deduplication across F-7 + SAM + Mergent + BMF

## Parallel with Frontend
10. Build Deep Dive tool infrastructure (government data lookup pipeline)
11. Build Deep Dive web scraper (Crawl4AI + LangExtract pipeline)
12. OLMS financial/membership data extraction for union profiles

## After Frontend Launch
13. Generate score validation test set (10-15 employers)
14. Diagnose specific missing union linkages (Jacob provides examples)
15. Wave 2 master list: NLRB participants
16. Wave 3 master list: OSHA establishments (filtered)
