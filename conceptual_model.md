# Platform Conceptual Model (updated 2026-02-26)

## Core Principle: Non-Union Employers Are the Targets

**The platform exists to help organizers identify and evaluate non-union employers as organizing targets.** Union employers are NOT targets — they are a reference dataset that makes targeting better.

Think of it like a recommendation engine: union employers are the "training data" (what does an organized workplace look like?), and non-union employers are the "candidates" (which unorganized workplaces share those characteristics?).

## Two Pools of Employers

The platform has two fundamental categories: **union employers** (reference data) and **non-union employers** (targets). Both go into the master employer database, flagged accordingly.

### Union Employers — The Reference Dataset

**Role:** Union employers are NOT organizing targets. They are a repository of data about what organized workplaces look like — their industries, sizes, violation histories, financial profiles, geographic patterns, and corporate structures. This data is used to identify and evaluate non-union employers.

**Why they matter:**
- They define what "similar to an organized workplace" means (Gower similarity, industry density baselines)
- They provide comparison benchmarks: how do non-union employers' violation rates, sizes, and industries compare to employers that already have unions?
- They establish structural patterns: "this company has a union at Location A" tells you something about organizing potential at Location B
- The better the union employer dataset, the better the comparative analysis against non-union employers
- Example: sibling union / hierarchy union relationships tell you that the same store in a different location has a union, or the parent company has a union in another company

**The key question about union employers is NOT "should we organize here" — it's "what can we learn from here to find targets elsewhere."**

**Sources:**
- **F7 filings** (primary) — bargaining units, not individual members. Nationally the count is higher than membership; closer to BLS "represented by union" figure. Not exhaustive — many unions don't file F7s.
- **Voluntary Recognition** (NLRB VR cases)
- **Manual research** — manually entered employers
- **Union website scraping** — mentions of employers, contracts, parties
- **OSHA flags** — establishments with `union_status = 'Y'`
- **NLRB employers** — from election cases (the union-won side)

**Reconciling national numbers:** Multi-pronged approach:
1. F7 are bargaining units per state, so nationwide multi-employer agreements can double-count across states
2. OLMS membership data (deduplicated: remove retirees, hierarchy dedup, active members only) gives real membership
3. Categorize by state, cross-check against BLS and EPI data on public/private union membership by state
4. **Don't obsess over matching "real" union membership counts** — what matters is being able to say "this company has a union here"

### Non-Union Employers — The Actual Targets

**Role:** Every employer that isn't flagged as having a union. These are the organizing targets — the employers the platform is built to help organizers find, evaluate, and prioritize.

**Sources:**
- IRS 990 (nonprofits)
- IRS BMF (tax-exempt entities)
- WHD (wage & hour cases)
- SAM.gov (federal contractors)
- OSHA establishments (without union flag)
- Failed NLRB elections (union lost)
- Mergent employers (commercial database)
- Manual input (though manual entries from union website scraping are usually union)

### Scoring and Targeting

**Establishing targets** means looking at non-union employers and evaluating:
- **Structural signals:** OSHA violations, NLRB activity, WHD violations, federal contracts (these are conditions that indicate organizing potential)
- **Comparative metrics via Gower similarity:** how similar is this non-union employer to union employers? Requires improved knowledge of the union reference dataset
- **Filtering dimensions:** Size and industry are preconditions an organizer uses to narrow the search ("show me shops over 100 people in healthcare"), NOT scoring factors that inflate/deflate a target's rank

**Key implications:**
1. Improving union employer data quality directly improves targeting quality — the two pools are not independent
2. Size is a filter, not a signal — an organizer already knows what size shop they're looking for
3. The scorecard evaluates non-union employers, not union employers. When a union employer appears in the scorecard, it's because it's being used as reference data, not because it's a target
