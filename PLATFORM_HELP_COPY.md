# Platform Help Section Copy
## All Pages — Ready for Claude Code Implementation
### Decided in Platform Redesign Interview | February 20, 2026

Each page has a collapsible "How to read this page" section at the top.
Collapsed by default. One click to expand.

---

## EMPLOYER PROFILE PAGE

### How to read this page

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
- **●○○○ (1 dot):** Matched on name similarity alone. Low confidence — treat this data with caution and verify independently. Use the "Report a problem" button if it looks wrong.

**Employee count range (e.g. 150-300):**
Different government databases collect employee counts at different times, using different definitions. OSHA counts workers at a specific facility on the day of an inspection. SAM.gov counts the entire company at the time of registration. Mergent Intellect uses their own research methodology. Rather than picking one number, the platform shows the range across all sources so you can see the spread. The scoring system uses the average.

---

## SEARCH PAGE

### How to read this page

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

---

## TARGETS PAGE

### How to read this page

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
- **Export CSV:** Download selected employers as a spreadsheet for offline analysis or sharing.
- **Flag all:** Mark selected employers as targets for follow-up.

---

## UNION EXPLORER PAGE

### How to read this page

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
- **Member count:** Total reported membership across all locals.
- **Employers:** Number of employers where this union represents workers.
- **Locals:** Number of local union chapters.

**Relationship map:**
The expandable list below the header shows the full organizational tree — from the national union down through its locals and the specific employers each local represents. Click any employer name to open their employer profile.

---

## ADMIN PANEL

### How to read this page

**This page is only visible to administrators.**

**Score weight configuration:**
Adjust how much each of the 8 scoring factors matters in the final score. Higher weight = more influence on the score. Changes take effect immediately and recalculate all employer scores. The current defaults are based on organizing strategy research: structural factors (union proximity, size, NLRB activity) at 3x, leverage factors (contracts, growth, similarity) at 2x, and grievance factors (OSHA, WHD) at 1x.

**Data freshness:**
Shows when each data source was last updated. Government databases are updated on different schedules — some monthly, some quarterly, some annually. Stale data (more than 6 months old) is highlighted. Refresh buttons trigger a new data pull from the source.

**Match review queue:**
When users click "Report a problem" on an employer profile, it appears here. Each item shows which employer and which data source the user flagged, along with the current match confidence. Admins can approve the match (dismiss the flag) or reject it (unlink the data source from that employer).

**System health:**
- **Database size:** Total size of the PostgreSQL database on disk.
- **API response times:** Average time to respond to common requests (search, profile load). Slower than 2 seconds may indicate a problem.
- **Error rates:** Percentage of API requests that failed. Should be near zero.

**User management:**
Add, remove, or change roles for platform users.
- **Viewer:** Can search and view everything but cannot flag, export, or report problems.
- **Researcher:** Can flag employers, export CSVs, and report bad matches.
- **Admin:** Full access including this admin panel, score weights, and user management.
