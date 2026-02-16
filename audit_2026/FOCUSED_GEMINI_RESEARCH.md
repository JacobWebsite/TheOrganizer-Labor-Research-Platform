# FOCUSED TASK: Methodology & Research Validation — GEMINI
# Run AFTER the full audit is complete

You already completed a full audit. Now go deeper on methodology validation, external benchmarking, and future readiness.

## TASK 1: BLS Benchmark Verification
The platform claims its 14.5M deduplicated members matches BLS within 1.5%. Verify:
1. What is the CURRENT BLS union membership number? (Search for the latest BLS Union Members Summary — typically released in January each year)
2. Does 14.5M actually fall within 1.5% of the current BLS number?
3. Break it down: platform says Private=6.65M (BLS=7.2M), Federal=1.28M (BLS=1.1M), State/Local=6.9M (EPI=7.0M). Are these BLS/EPI numbers current?
4. The platform says coverage is 92% private, 116% federal, 98.3% state/local. Do these ratios make sense? Why would federal be OVER 100%?
Save to: docs/BLS_BENCHMARK_VERIFICATION.md

## TASK 2: Scoring Methodology Assessment
The platform uses a 9-factor scoring model (0-100 points) to prioritize organizing targets. Assess:
1. Are the right factors included? What does organizing research say about what predicts successful organizing?
2. Are the weights reasonable? (OSHA violations get 25 points — the most of any factor. Is safety the strongest predictor?)
3. What factors are MISSING that research suggests matter? (e.g., company profitability, employee turnover, recent layoffs, management anti-union spending)
4. The Gower distance approach (planned for Phase 5) — is this the right method for "find employers similar to unionized ones"? What are the alternatives?
5. The propensity model concept (also Phase 5) — what machine learning approaches are most appropriate for "predict which employers are most likely to organize"?
Save to: docs/SCORING_METHODOLOGY_ASSESSMENT.md

## TASK 3: Data Source Gap Analysis
The platform integrates ~14 data sources. For each one that's NOT yet integrated but planned:

**SEC EDGAR:**
- What specifically is available via edgartools? Is the claimed EIN matching capability real?
- How many public companies have EINs in their XBRL filings? (The platform claims this would connect 300K+ companies)
- Is Exhibit 21 parsing (subsidiary lists) straightforward or complex?

**IRS Business Master File:**
- How many records does it actually contain? Is 1.8M accurate?
- Would matching against BMF really double the 990 match rate?
- What fields does BMF have vs. actual 990 filings?

**CPS Microdata (IPUMS):**
- Can you actually calculate metro-level union density from CPS data? What are the sample size limitations?
- Is ipumspy a real, maintained library? When was it last updated?

**OEWS Staffing Patterns:**
- How granular is this data? Can you really get occupation mixes by 6-digit NAICS?
- Would this meaningfully improve the "comparable employers" feature?

**State PERB Data:**
- Is it true that no open-source tools exist for scraping state PERB data?
- What states have public PERB databases accessible online?
- How structured is the data (clean download vs. messy HTML)?

**Good Jobs First:**
- Does the Subsidy Tracker API still work? What format does it return?
- 722,000+ entries — is this number current?

Save to: docs/DATA_SOURCE_GAP_ANALYSIS.md

## TASK 4: Density Estimation Methodology Review
The platform estimates union density at county, ZIP, and census tract levels. The methodology:
- Uses BLS industry-level national rates
- Applies them to local employment counts from Census/ACS
- Uses a "calibration multiplier" (2.26x for NY) to adjust

Assess:
1. Is this approach statistically valid? What are the known weaknesses?
2. The 2.26x multiplier — does it make sense that actual density is 2.26x what you'd predict from national industry rates? Or is this overfitting to match a known answer?
3. Are there better methods for sub-state density estimation used in academic research?
4. The platform excludes edu/health and public admin from private calculations to avoid double-counting — is this the right approach?
5. For NY specifically: the range is 12.2% (Manhattan) to 26.5% (Hamilton County). Do these seem reasonable?
Save to: docs/DENSITY_METHODOLOGY_REVIEW.md

## TASK 5: Web Scraping Feasibility Check
The platform plans to scrape union websites. Verify the claims:
1. Do the major union websites (Teamsters, AFSCME, SEIU, CWA, UNITE HERE) still have the directory pages described?
2. Is the claim that "most union websites run on WordPress with REST APIs" accurate?
3. Does Crawl4AI actually work well for this use case? Check recent reviews/benchmarks
4. Firecrawl claims 87-94% accuracy — is this verified by independent sources?
5. For the union contract database idea (25,000+ contracts from public sources) — are SeeThroughNY, NJ PERC, Ohio SERB, and federal OPM still active with the claimed contract counts?
Save to: docs/SCRAPING_FEASIBILITY_CHECK.md

## TASK 6: Comparable Platform Landscape
Research whether similar platforms exist:
1. Are there other labor research platforms that integrate multiple federal databases this way?
2. What tools do unions currently use for organizing target identification?
3. Are there academic projects doing similar work?
4. How does this platform's approach compare to commercial labor relations databases (like Bloomberg Law Labor, LRI, etc.)?
5. What features do organizers actually want most? (If you can find any surveys or reports about organizing technology needs)
Save to: docs/COMPARABLE_PLATFORMS.md
