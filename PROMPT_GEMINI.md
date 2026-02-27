# Platform Audit — Gemini (Strategic & Data Coverage Analyst)
## February 25, 2026

---

## YOUR ROLE

You are auditing a labor relations research platform from a strategic and data coverage perspective. While the other two auditors check whether the code runs correctly (Codex) and whether the data is accurate (Claude Code), your job is to step back and ask: **Does this platform actually serve the people it's built for?**

The platform is built for organizers — people at unions and worker organizations who need to figure out where to focus their limited time and resources for organizing campaigns. They need to answer questions like: Which employers are most vulnerable to organizing? Where are there recent wins nearby? Which employers have the worst safety records? What does the corporate ownership structure look like?

**You are one of three auditors.** Claude Code has direct database access. Codex reviews code line by line. Your unique strength is strategic perspective — you ask whether the platform actually helps organizers make better decisions.

**Critical rules:**
1. **Think like an organizer, not an engineer.** Ask: "Would this help someone decide which employer to target?" "What would make an organizer stop trusting this?" "What information is missing?"
2. **Cross-reference claims.** Documentation makes many claims. For each major claim, check whether evidence supports it. "96.2% matching accuracy" — what does that mean? "7.93/10 research quality" — who's grading it?
3. **Identify what's NOT being measured.** The platform focuses on government data. What important dimensions of organizing potential does government data miss entirely?
4. **Be honest about what you can't verify.** You don't have direct database access. When working from documentation, say so.
5. **Be thorough.** It is much better to flag potential concerns and find they're fine than to miss something that becomes a real problem when organizers start using this.

**Context files you should have:**
- `PROJECT_STATE.md` — current platform state, known issues
- `UNIFIED_ROADMAP_2026_02_19.md` — current roadmap
- `SCORING_SPECIFICATION.md` — how scoring is supposed to work
- `FOUR_AUDIT_SYNTHESIS_v3.md` — previous audit findings (very detailed)
- `DOCUMENT_RECONCILIATION_ANALYSIS.md` — conflicts between documents
- `RESEARCH_AGENT_IMPLEMENTATION_PLAN.md` — research agent architecture

---

## WHAT CHANGED SINCE THE LAST AUDIT (Feb 19, 2026)

Your focus is the STRATEGIC implications of these changes:

1. **Research Agent Built** — Automatically researches companies. 96 runs, 7.93/10 quality. Does automated research actually help organizers, or is it a technical novelty?

2. **CorpWatch SEC EDGAR Import** — 14.7M rows of corporate ownership data. What strategic value does corporate ownership have for organizers? Is it being used effectively?

3. **Data Enrichment** — Geocoding 73.8%→83.3%, NAICS inference. Does better coverage make scoring more reliable? How much of the gap remains?

4. **NLRB Participant Cleanup** — 492K junk rows removed. The previous audit found 83.6% junk. Did removing data change conclusions about organizing success rates?

5. **React Frontend Completed** — All 6 phases. From a user experience perspective, would an organizer actually find this useful?

6. **Scoring Updates** — NLRB decay, financial fix, Priority minimum. Do these changes make the scoring more trustworthy from an organizer's perspective?

7. **Splink Hardening** — Threshold raised to 0.70. Is the tradeoff (fewer matches but hopefully more accurate) the right call for organizers?

8. **Source Re-runs Incomplete** — 990, WHD, SAM still have old matches. What does this mean strategically? Are organizers seeing data matched with different quality standards depending on which source it comes from?

---

# PART 1: SHARED OVERLAP ZONE

**You MUST answer all 10 of these questions.** Two other AI auditors (Claude Code and Codex) are answering the same questions independently. Your answers will be compared side by side. Label each answer clearly (OQ1, OQ2, etc.).

For questions requiring direct database access, do your best with the documentation you have and clearly note what you verified vs. estimated.

---

### OQ1: Priority Tier Spot Check (5 Employers)

Based on the documentation and audit findings, assess the Priority tier:
- What kinds of employers are ranked Priority? (Using data from previous audits and documentation)
- Are there likely still placeholder/junk records in the Priority tier?
- Would an organizer trust the Priority list?
- What should "Priority" actually mean from an organizer's perspective?

**Why:** Previous audit found 92.7% of Priority employers had zero enforcement activity. Only 125 election wins fell in Priority vs 392 in the Low tier.

---

### OQ2: Match Accuracy Assessment

Based on all available documentation about the matching system:
- What's your best estimate of the current false positive rate?
- Is the 0.70 threshold the right balance for organizers? (Wrong matches erode trust, missing matches hide information)
- What would you recommend?

---

### OQ3: React Frontend ↔ API Contract

Review the REACT_IMPLEMENTATION_PLAN.md and available frontend documentation:
- Does the planned architecture match what was actually built?
- Are there likely mismatches between frontend expectations and API reality given the rapid 6-phase build?
- What UX problems would an organizer most likely encounter?

---

### OQ4: Data Freshness

Based on documentation:
- How current is the data in each major source?
- Would an organizer know whether they're looking at 2024 data or 2020 data?
- How important is data recency for organizing decisions?
- What would a good data freshness display look like?

---

### OQ5: Incomplete Source Re-runs — Strategic Impact

990, WHD, and SAM still use old matching. From an organizer's perspective:
- Would organizers notice the quality difference between well-matched and poorly-matched data?
- Is it better to show possibly-wrong data or no data at all?
- How should the platform communicate match quality uncertainty to users?

---

### OQ6: The Scoring Factors — Strategic Assessment

For each of the 8 factors, assess from an organizer's perspective:
1. **OSHA Safety (1x):** Does safety record predict organizing potential? When would it mislead?
2. **NLRB Activity (3x):** Is 3x weight appropriate? Does nearby momentum actually predict success?
3. **WHD Wage Theft (1x):** Does wage theft correlate with organizing interest?
4. **Gov Contracts (2x):** Why do government contracts matter for organizing?
5. **Union Density (1x):** Does industry unionization rate predict new organizing?
6. **Employer Size (3x):** Is 3x weight right? Why is size so heavily weighted?
7. **Similarity (2x):** What's the theory here? Does similarity to unionized employers predict organizing success?
8. **Industry Growth (2x):** Growing industries = more organizing opportunity?

Also: What factors are MISSING that experienced organizers would want?

---

### OQ7: Test Suite Assessment

From a strategic perspective:
- What kinds of errors would tests catch vs. miss?
- If scoring tests only check "code doesn't crash" (not actual values), what's the risk?
- What's the most dangerous untested scenario?

---

### OQ8: Database Cleanup

From a strategic perspective:
- Does database complexity make the platform harder to maintain and deploy?
- Are there entire data sources loaded but never connected to anything useful?
- What's the priority: cleaning up or adding new data?

---

### OQ9: Single Biggest Problem

What is the single most important thing to fix before showing this to real organizers?
- Plain language description
- Impact on organizer trust and decision-making
- Your confidence level
- What happens if NOT fixed

---

### OQ10: Previous Audit Follow-Up

The previous audit (FOUR_AUDIT_SYNTHESIS_v3.md) identified major problems. Based on what you can see in the documentation:

**Which of these appear addressed?**
- Priority tier ghost employers
- 10-40% match false positive rate
- Score distribution being bimodal
- 125 wins in Priority vs 392 in Low (prediction failure)
- Missing backup strategy
- Documentation inconsistencies
- Legacy frontend still served
- Authentication untested with real users

**Which appear unaddressed?**
**Which may have gotten worse?**

---

# PART 2: YOUR SPECIFIC INVESTIGATION AREAS

---

## Area 1: Does the Scoring System Predict Organizing Potential?

### 1A: Factor Selection Critique

For EACH of the 8 factors:
- What's the theory of why this predicts organizing success?
- What research or evidence supports the connection?
- When would this factor be misleading?
- Would experienced organizers agree this matters?

Be specific. For example: OSHA violations predict worker discontent, which motivates organizing. But a company with no violations might just be in a low-inspection industry, or might be genuinely safe (meaning workers are less motivated to organize). The factor can't distinguish between these.

### 1B: What's Missing from the Score?

What actually drives successful organizing campaigns that this platform completely ignores?

Assess each of these potential missing factors:
- **Employer financial vulnerability** — SEC data exists but isn't in scoring. A struggling company may be more vulnerable to pressure. Or it may be more likely to close rather than negotiate.
- **Worker turnover** — High turnover often correlates with organizing interest. No data source.
- **Recent media/news** — Companies in the news for labor issues see more organizing. Not tracked.
- **Management anti-union history** — Beyond NLRB ULP cases: union-avoidance consultants, captive audience meetings, etc.
- **Community/political climate** — Local politics affects organizing success.
- **Workforce demographics** — Younger workers and workers of color organize at higher rates. BLS data exists.
- **Industry organizing momentum** — Sector-wide movements (Starbucks, Amazon, tech). Beyond individual elections.
- **Contract expiration dates** — When contracts expire at unionized employers, non-union competitors become targets.
- **Employer growth/contraction** — Growing vs shrinking workforce = different organizing dynamics.
- **Employer profitability** — Profitable companies can afford union contracts. Unprofitable ones resist harder.

### 1C: The Signal-Strength Dilemma

When a factor has no data, it's skipped. This means an employer with 1 factor (size = large) and a perfect size score ranks above an employer with 6 factors showing moderate scores across safety, wages, NLRB activity, etc.

- Is this the right design? What would organizers think?
- How should the platform communicate data completeness?
- Is the `factors_available >= 3` minimum for Priority enough?
- Should there be different minimums for different tiers?
- Should there be a "confidence" indicator separate from the score?

### 1D: Score Validation / Backtesting

Has anyone checked whether high-scoring employers actually turn out to be good organizing targets?

The previous audit found:
- Priority captured only 125 election wins
- Low captured 392 wins (3x more than Priority)
- The lowest tier had more real organizing success than the highest tier

This is a fundamental credibility problem. If the scoring system doesn't predict real organizing outcomes better than random chance, what's the point? Assess:
- Is there data available to backtest? (NLRB election outcomes + employer scores)
- What would a valid backtest look like?
- Has anyone addressed the 125-vs-392 finding?
- What would it take to improve prediction accuracy?

---

## Area 2: Data Coverage — Who's Invisible?

### 2A: The F7 Limitation (The "Targeting Paradox")

The platform only scores employers in the F7 database — employers that ALREADY have union contracts. But the entire point is finding NEW targets at NON-union employers.

- How many potential non-union targets exist in `master_employers`? (~2.7M documented)
- Are any scored? (Documentation says no)
- What's the plan for expansion? (Redesign Spec Section 4 discusses phased seeding)
- How urgent is this? Can the platform be useful to organizers if it only covers already-unionized employers?
- What's the realistic timeline for non-union scoring?

### 2B: Industry Gaps

Previous audit found:
- **Amazon:** Only 4 entries (studios, construction, masonry, painting). Zero warehouse/fulfillment.
- **Walmart:** Zero entries.
- **Cannabis:** Zero entries.
- **Finance/Insurance:** Only 418 employers vs 25,302 in Construction.

Assess:
- Have any gaps been addressed?
- What industries are most important for current organizing momentum? (Healthcare, logistics, tech, hospitality, education)
- For each hot industry: how well does the platform cover it?
- What new data sources could close the biggest gaps?

### 2C: Public Sector Gaps

- 7,987 public employers vs ~7 million public sector unionized workers
- What state PERB (Public Employment Relations Board) data is available?
- Which states have the largest gaps?
- How important is public sector coverage for the platform's target users?

### 2D: Geographic Gaps

- 26.2% of employers have no geocoding
- How does this affect the "within 25 miles" NLRB proximity calculation?
- Are gaps concentrated in certain states or regions?
- Does this create systematic bias in scoring? (Employers in well-geocoded areas score higher on NLRB proximity because the calculation works; employers in poorly-geocoded areas get no NLRB proximity score at all)

### 2E: Temporal Gaps

For each major data source:
- How old is the most recent data?
- How frequently is it updated?
- What's the lag between real-world events and platform visibility?
- If an organizer checks an employer today, how old could the data be?
- Are there data sources that update frequently enough to be genuinely current (monthly/quarterly) vs. essentially historical snapshots?

---

## Area 3: Research Agent Strategic Value

### 3A: What Does It Actually Do?

Review RESEARCH_AGENT_IMPLEMENTATION_PLAN.md:
- What questions does it try to answer about an employer?
- What sources does it check?
- How does output compare to 30 minutes of manual Google/LinkedIn/Glassdoor research?
- What information does it produce that the database alone can't provide?

### 3B: The "Self-Improving" Claim

- Is the learning mechanism built or theoretical?
- 96 runs with 7.93/10 quality — who or what grades it?
- How would you measure real improvement over time?
- Is the quality score meaningful, or could it be inflated self-assessment?

### 3C: Integration Value

- Can organizers trigger research from employer profiles?
- Are findings visible in the UI?
- Do findings feed back into scores?
- What would ideal integration look like?
- Is the research agent solving a real organizer pain point, or is it a solution looking for a problem?

### 3D: What Would Make the Research Agent Indispensable?

If you were an organizer, what would make you NEED this tool rather than just Googling?
- Real-time monitoring of employer news?
- Automatic alerts when something changes?
- Cross-referencing public records that are hard to find manually?
- Something else?

---

## Area 4: The Organizer's Experience

### 4A: User Journey Scenarios

Walk through 3 realistic scenarios:

**Scenario 1: "I'm an SEIU healthcare organizer in California. Show me my best targets."**
- Can the platform answer this?
- What would the organizer see?
- Would results be trustworthy?
- What could go wrong?
- What critical information is missing?

**Scenario 2: "We're considering organizing Amazon warehouse workers in New Jersey."**
- Can the platform help?
- What data exists about Amazon?
- What's missing?
- Would the organizer be better off just Googling?

**Scenario 3: "We just won an election at a hospital in Ohio. Who else nearby should we target next?"**
- Can the platform find nearby similar employers?
- Does "within 25 miles" work?
- Would the recommendations be trustworthy?
- What makes the organizer's next step clear?

### 4B: Trust Assessment

If an organizer discovers ONE piece of incorrect information (wrong OSHA data, wrong score, placeholder company ranked Priority):
- How would this affect their trust in the ENTIRE platform?
- Do organizers have the technical knowledge to evaluate data quality?
- Is there a mechanism for users to flag errors?
- How transparent is the platform about data uncertainty?
- What's the "trust recovery" path after an error?

### 4C: First Impressions

Write a paragraph as if you were an experienced organizer seeing this platform for the first time. What impresses you? What concerns you? What would you check to decide whether to trust it?

---

## Area 5: Competitor and Alternative Assessment

### 5A: What Organizers Currently Use

Research these tools and assess:
- **NLRB's own search** — What can it do that this platform can't?
- **OSHA's inspection search** — Same question
- **LaborAction Tracker** — Public tracking of labor actions
- **BLS/EPI union density data** — Publicly available analysis
- **Commercial databases** (Mergent, D&B, etc.) — What do organizers use?
- **Manual research** (Google, LinkedIn, Glassdoor, news archives) — What takes time?

### 5B: Competitive Advantage

What does THIS platform offer that the above tools don't?
- All-in-one integration (don't need to search 5 different government websites)
- Scoring/ranking (automated assessment of organizing potential)
- Geographic proximity analysis
- Corporate hierarchy mapping
- Historical tracking across multiple data sources

Is this advantage compelling enough that organizers would adopt a new tool?

### 5C: Competitive Gaps

What do existing tools offer that this platform doesn't?
- Official/authoritative status (NLRB, OSHA)
- Real-time data (news, social media)
- Worker-reported data (Glassdoor reviews, Indeed ratings)
- Union contract databases (BNA, Bloomberg Law)
- Campaign management tools

### 5D: Value Proposition

Given the current state (scoring accuracy issues, matching errors, incomplete coverage):
- Is the platform MORE useful than just searching NLRB + OSHA + Google yourself?
- Under what conditions would it become clearly more useful?
- What's the minimum viable product that would get an organizer to use this regularly?

---

## Area 6: Previous Audit Deep Follow-Up

The FOUR_AUDIT_SYNTHESIS_v3.md is extremely detailed (1,148 lines). For each major finding category, assess the strategic situation:

### 6A: Scoring Problems (Synthesis Parts 1.1-1.4)
- Priority tier "mostly ghost employers" — still true?
- Platform "can't see most organizing successes" — still true?
- 125 wins in Priority vs 392 in Low — addressed?
- Score distribution bimodal — improved?

### 6B: Match Accuracy (Synthesis Parts 1.2, 2.1-2.4)
- 10-40% false positive rates — current estimate?
- Splink geography overweighting — retuned?
- Legacy poisoned matches — cleaned?
- The tradeoff question: fewer matches vs better accuracy

### 6C: Data Quality (Synthesis Parts 3.1-3.6)
- Membership numbers paradox (DC 141,563%, HI 10.9%) — addressed?
- Data freshness tracking broken — fixed?
- NLRB participant 83.6% junk — cleaned? (492K removed, but was that enough?)
- Empty columns on f7_employers_deduped — removed?

### 6D: Infrastructure (Synthesis Parts 1.5, 3.7-3.10)
- No backup strategy — implemented?
- 19 hardcoded paths — fixed?
- Legacy frontend still served — archived?
- Auth never tested with real users — tested?
- Blocking MV refreshes — fixed?

### 6E: The 20 Investigation Questions (Synthesis Part 5)
How many were answered? Which are still open? Which are most critical?

### 6F: The 11 Decisions (Synthesis Part 6)
Which were made? Which are still pending? Which are blocking progress?

---

## Area 7: Documentation and Roadmap Assessment

### 7A: Document Conflicts

DOCUMENT_RECONCILIATION_ANALYSIS.md found:
- Different factor counts across documents (7 vs 8 vs 9)
- Different test counts (375, 439, 441, 456, 457)
- Conflicting information about what the frontend is built with
- No single source of truth

Assess:
- Have any conflicts been resolved?
- How much does this matter? (Does it confuse AI tools working on the project? Does it confuse humans?)
- What's the minimum documentation fix before the next development phase?

### 7B: Roadmap Reality Check

Review UNIFIED_ROADMAP_2026_02_19.md:
- Are priorities in the right order FOR ORGANIZERS?
- What's the most impactful thing NOT in the roadmap?
- How much fixes existing problems vs builds new features? Is the balance right?
- What's a realistic timeline to something organizers can use?

### 7C: Feature Prioritization

**If you could only build 3 things before showing this to real organizers, which 3?**

Consider:
- What creates the most trust
- What answers the most important organizer question
- What differentiates this from tools organizers already have
- What's feasible in a reasonable timeframe

Explain your reasoning for each choice and what you'd cut.

---

# OUTPUT FORMAT

Structure your report as:

1. **Executive Summary** (5-10 sentences — honest strategic assessment)
2. **Shared Overlap Zone Answers** (all 10, labeled OQ1-OQ10)
3. **Investigation Area Reports** (Areas 1-7)
4. **The Organizer's Verdict** (a paragraph as an experienced organizer seeing this for the first time)
5. **Strategic Blind Spots** (important things nobody seems to be thinking about)
6. **Competitor Gap Analysis** (what this offers vs what organizers already have)
7. **Previous Audit Reality Check** (addressed, unaddressed, gotten worse)
8. **Recommended Priority List** (top 10 things to fix/build, ordered by impact for organizers, with effort estimates)
