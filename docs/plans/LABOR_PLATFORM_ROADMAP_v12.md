# Labor Relations Research Platform — Roadmap v12

**Date:** February 8, 2026
**Audience:** Union leadership making strategic decisions
**Time commitment:** 15+ hours/week
**Approach:** Plain language throughout — every step explains *what*, *why*, and *how*

---

## How to Read This Roadmap

This document is organized into four phases that build on each other like floors of a building. You can't put furniture in a room that doesn't have walls yet, so the order matters. Each phase has a clear goal, a list of tasks explained in plain English, and a "you'll know it's working when..." check at the end.

**The four phases:**

1. **Clean the Foundation** (Weeks 1–3) — Fix known data problems so everything built on top is trustworthy
2. **Add New Intelligence** (Weeks 4–8) — Bring in new data sources that make the platform smarter
3. **Upgrade the Scorecard** (Weeks 6–10) — Make the "which employers should we organize?" tool significantly better
4. **Rebuild the Interface** (Weeks 8–14) — Redesign what people actually see and use, optimized for leadership decisions

Phases 2 and 3 overlap intentionally — some scorecard improvements depend on new data arriving from Phase 2.

---

## What You Have Right Now (The Starting Point)

Before diving into what's next, here's an honest snapshot of where the platform stands today:

### What's working well

- **Membership tracking is accurate.** The platform counts 14.5 million union members nationally. The government's official number (from the Bureau of Labor Statistics) is 14.3 million. That's a 1.4% difference — extremely close.

- **You can look up almost any unionized employer in the country.** The database has 63,118 employers with union contracts, and 96.2% of them are successfully linked to the union that represents their workers.

- **Workplace safety violations are connected.** Over 2.2 million OSHA violation records are in the system, covering $3.5 billion in penalties.

- **Corporate ownership is mapped.** A new layer connects SEC filings, a global business registry (GLEIF), and commercial business data to show who owns whom.

- **The organizing scorecard exists and works.** It scores non-union employers on a 0-62 point scale across six factors.

### What needs improvement

- **About 11,800 employer records are likely duplicates.**
- **The scorecard is basic** — it doesn't ask "Does this non-union employer look like employers that already have unions?"
- **The web interface was built for testing, not for decision-making.**
- **Some data gaps remain:** 16,000 employers without map coordinates, 8,000 without industry codes.

---

## PHASE 1: Clean the Foundation

**Goal:** Make the existing data trustworthy enough that leadership can cite it with confidence
**Timeline:** Weeks 1–3
**Effort:** ~35–50 hours

### Why this comes first

If someone asks "How do you know that number is right?" you need a good answer. Fixing known issues first means everything built afterward rests on solid ground.

### Task 1.1: Merge duplicate employers (4–6 hours)
Combine 11,815 pairs of employer records that are almost certainly the same company under slightly different names.

### Task 1.2: Audit 234 complex duplicates (8–12 hours)
Review ambiguous cases requiring human judgment.

### Task 1.3: Fill missing industry codes for ~8,000 employers (4–6 hours)
Cross-reference against OSHA and BLS data to fill in missing NAICS codes.

### Task 1.4: Geocode 16,000 employers (4–6 hours)
Turn street addresses into map coordinates using the Census Bureau's free service.

### Task 1.5: Validate union hierarchy (6–8 hours)
Fix parent/child union relationships — orphaned locals, disbanded locals, wrong affiliations.

### Task 1.6: Cross-check sector classifications (3–4 hours)
Verify that every employer is correctly tagged as private, federal, or state/local public.

### Task 1.7: Build automated validation (4–6 hours)
Create automated checks that flag when data quality drifts outside acceptable ranges.

### Phase 1 Checkpoint
Re-check all numbers against BLS benchmarks. All sectors within 90–110%.

---

## PHASE 2: Add New Intelligence

**Goal:** Bring in new data sources that answer questions leadership actually asks
**Timeline:** Weeks 4–8
**Effort:** ~40–60 hours

### Task 2.1: Load national wage theft data (8–10 hours)
363,000 WHD wage violation records — unpaid overtime, minimum wage violations, misclassification.

### Task 2.2: Improve OSHA matching (6–8 hours)
Push the match rate from 45% above 50% using address-based matching.

### Task 2.3: Expand Mergent business data nationally (15–20 hours)
Go from 14,240 employers to 50,000+ with revenue, corporate structure, and accurate industry codes.

### Task 2.4: Expand IRS Form 990 nonprofit data nationally (10–14 hours)
Executive compensation, revenue, and program data for hospitals, universities, and nonprofits.

### Task 2.5: Integrate QCEW establishment counts (4–6 hours)
Add "how many total businesses exist in this industry" — the denominator for organizing opportunity.

### Phase 2 Checkpoint
Re-run BLS validation. Check that new data sources link to existing employers at 30%+ rates.

---

## PHASE 3: Upgrade the Scorecard

**Goal:** Move from a checklist to a comparison engine — "which non-union employers look most like employers that already have unions?"
**Timeline:** Weeks 6–10
**Effort:** ~30–45 hours

### Task 3.1: Implement employer similarity scoring (12–16 hours)
Gower Distance method — measures how similar any two employers are across all known characteristics.

### Task 3.2: Add historical organizing success patterns (8–12 hours)
Analyze 33,096 NLRB elections to learn which employer types are most likely to vote yes.

### Task 3.3: Build the "comparables" display (6–8 hours)
For every target, show the most similar unionized employers and why the comparison makes sense.

### Task 3.4: Refresh and re-score all targets (4–6 hours)
Run the new scoring across every employer and regenerate priority tiers.

### Phase 3 Checkpoint
Compare new top targets against old ones. Test with real organizers if possible.

---

## PHASE 4: Rebuild the Interface for Leadership

**Goal:** Create a decision-ready interface a union president can use directly
**Timeline:** Weeks 8–14
**Effort:** ~35–50 hours

### Task 4.1: Territory Dashboard (8–10 hours)
Landing page showing organized vs. non-organized workers, top targets, recent activity, industry breakdown.

### Task 4.2: Employer Deep Dive profile (8–10 hours)
Single-page profile showing everything the platform knows about one employer.

### Task 4.3: Board Report export (6–8 hours)
One-click PDF/CSV exports for presentations and board meetings.

### Task 4.4: Union-first navigation (6–8 hours)
Start with "Select your union" instead of making users search.

### Task 4.5: Mobile-responsive design (6–8 hours)
Make it work on phones and tablets.

### Phase 4 Checkpoint
Can a union organizing director find their top targets and export a board summary in 5 minutes?

---

## Summary Timeline

| Weeks | Phase | Key deliverable |
|-------|-------|-----------------|
| 1–3 | Clean the Foundation | All data passes BLS benchmark check |
| 4–8 | Add New Intelligence | 4+ new data sources in employer profiles |
| 6–10 | Upgrade the Scorecard | Similarity-based target identification |
| 8–14 | Rebuild the Interface | Leadership-ready dashboard and exports |

**Total estimated effort:** 140–205 hours over 14 weeks

---

*This roadmap is a living document updated after each work session.*
