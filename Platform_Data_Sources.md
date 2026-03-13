# Labor Relations Research Platform — Data Sources & Brainstorming Prompt

**Last Updated:** March 4, 2026

---

## Your Task

I have built a database that pulls together information from over a dozen U.S. government sources about employers, unions, workplace safety, wage theft, corporate ownership, and more. The database covers roughly 147,000 employers that currently have or once had union contracts, plus millions of additional employer records from safety inspections, wage theft cases, and corporate filings.

I want you to **theorize and brainstorm** about how this data could be used to build a genuinely useful labor research platform. Don't worry about what I've already built or how the database is actually structured. Instead, think creatively about:

- What questions would union organizers, researchers, journalists, workers, and policymakers want to answer with this data?
- What would the most useful version of this platform actually look like to someone sitting down to use it?
- What patterns, correlations, and stories are hiding in the connections between these different data sources?
- What would make this platform something people actually come back to and rely on, rather than a one-time novelty?
- What are the most important things this data can reveal that aren't currently easy to find anywhere else?

Think big. Think practical. Think about both the 30,000-foot view and the person sitting at a desk trying to decide which employer to focus their organizing campaign on next.

---

## What Data Is Available

Below is a description of every major data source in the platform — what it contains, how many records there are, and what it tells us about employers and workers. All of this information comes from publicly available U.S. government databases.

---

### Core Union Reference Data

**F7 Union Filings** — `unions_master`, `f7_employers_deduped`, `f7_union_employer_relations`  
Department of Labor union financial disclosure filings. 146,863 employers with active union contracts/bargaining units.  
The "training data" — what does an organized workplace look like? All scoring and matching starts here.

**NLRB Elections** — `nlrb_elections`, `nlrb_participants`  
National Labor Relations Board election records — 33K elections with win/loss outcomes.  
Used for scoring validation (win rates by tier), NLRB factor in scorecard, and identifying active organizing.

**LM Filings** — `lm_data`  
Historical union LM financial reports (2010–2024), 331K rows.  
Supplements F7 data with longitudinal filing history for union activity trends.

---

### Enforcement & Workplace Conditions

**OSHA** — `osha_establishments`, `osha_violations_detail`  
1M establishments + 2.2M violation records with $3.5B in penalties.  
Primary signal in the "Anger" pillar — workplace safety violations indicate worker grievances. Matched to F7 employers at ~8.3% rate.

**WHD Wage & Hour** — `whd_cases`, `mv_whd_employer_agg`  
363K Department of Labor wage theft/FLSA cases (2005–2025) with backwages and civil penalties.  
Second Anger pillar signal — wage violations correlate with organizing potential. Matched to F7 at ~4.7%.

---

### BLS Labor Statistics (NEW — loaded 2026-03-04)

**OES Wages** — `oes_occupation_wages`, `mv_oes_area_wages`  
414K rows of occupation × area × industry wage data (2024) — percentiles, means, employment counts.  
Shows what workers earn at a given employer type/location. Nursing assistants median $39K, RNs $82K, etc.

**SOII Injury Rates** — `bls_soii_series`, `bls_soii_data`, `mv_soii_industry_rates`  
891K series + 5.7M data points on workplace injuries/illnesses by industry (2014–2024).  
National injury rates per 100 FTE by industry. Nursing homes: 6.3/100 (2024), spiked to 13.1 during COVID.

**JOLTS Turnover** — `bls_jolts_series`, `bls_jolts_data`, `mv_jolts_industry_rates`  
2K series + 370K data points on hires, quits, separations, job openings by industry.  
Turnover signals — healthcare quit rate 2.2%, job opening rate 6.5%. High turnover = organizing opportunity.

**NCS Benefits** — `bls_ncs_series`, `bls_ncs_data`, `mv_ncs_benefits_access`  
100K series + 768K data points on employee benefit access/participation by industry.  
What benefits workers get (or don't). Healthcare industry: only 64% have medical + retirement access.

**QCEW** — `qcew_annual`  
1.9M rows of quarterly employment & wages by industry × geography (county-level).  
Contextual benchmark — average wages and employment levels for an industry in a specific area.

**BLS Union Density** — `bls_industry_density`, `bls_state_density`, `state_sector_union_density`  
Union membership rates by industry, state, and sector (1978–2025).  
Feeds the Union Proximity scoring factor. Used to estimate how unionized a given industry/area is.

**BLS Staffing Patterns** — `bls_industry_occupation_matrix`  
67K rows mapping NAICS industries to SOC occupations with employment shares.  
Used for occupation similarity scoring (Gower distance) and industry profiling.

---

### Corporate Identity & Hierarchy

**SEC EDGAR** — `sec_companies`  
517K companies from SEC filings with CIK, EIN, LEI, SIC codes.  
Links public companies to F7 employers via the corporate crosswalk. Provides EIN for exact matching.

**GLEIF** — `gleif_us_entities`, `gleif_ownership_links`  
379K legal entities + 499K ownership links via Legal Entity Identifiers.  
Maps corporate parent-subsidiary relationships. Used in crosswalk for LEI-based exact matching.

**CorpWatch** — `corpwatch_companies`, `corpwatch_relationships`, etc.  
1.4M companies + 3.5M relationships parsed from SEC filings by CorpWatch.  
Deepest corporate genealogy data — parent/subsidiary chains, name history, filing index.

**Mergent/D&B** — `mergent_employers`  
56K companies with DUNS numbers, EINs (55% coverage), sales, and employee counts.  
Financial signal source — annual sales and employee counts feed the Financial scoring factor.

**Corporate Crosswalk** — `corporate_identifier_crosswalk`  
17,111 rows linking SEC CIK, GLEIF LEI, Mergent DUNS, CorpWatch ID, and F7 employer_id.  
The Rosetta Stone — connects disparate corporate identifiers so we can link financial data to union employers.

---

### Federal Contracting & Tax Data

**SAM.gov** — `sam_entities`  
826K federal contractors with UEI, CAGE codes, NAICS, entity structure.  
Identifies government contractors (relevant for prevailing wage, Davis-Bacon). Very low F7 overlap (~0%).

**Form 990** — `national_990_filers`, `national_990_f7_matches`  
587K tax-exempt organizations matched to 20K F7 employers.  
Identifies nonprofit employers (hospitals, universities) — their tax filings reveal compensation and governance.

**IRS BMF** — `irs_bmf`  
~300K tax-exempt organizations from the IRS Business Master File.  
Supplements 990 data with org classification, ruling dates, and deductibility status.

**Form 5500** — `cur_form5500_sponsor_rollup`  
259K plan sponsors aggregated by EIN — pension/welfare plan data, participant counts.  
Shows whether employers offer retirement/health benefits and whether plans are collectively bargained.

**PPP Loans** — `cur_ppp_employer_rollup`  
9.5M borrowers with loan amounts, forgiveness, and jobs reported.  
COVID-era employer size/financial signal. Reveals actual employee counts and federal aid received.

**USAspending** — `cur_usaspending_recipient_rollup`  
94K federal contract recipients with obligated amounts and fiscal years.  
Federal contract dependency — employers reliant on government contracts face different organizing dynamics.

---

### Census & Demographics

**ACS Workforce** — `newsrc_acs_occ_demo_profiles`, `cur_acs_workforce_demographics`  
11.5M rows: workforce demographics by state × metro × industry × occupation × gender × race × age × education.  
Who works where — 77% female in NJ healthcare, age distribution, education levels. Insurance columns pending re-run.

**CBP County Business Patterns** — `cur_cbp_geo_naics`  
1.5M rows: establishment counts and employment by county × NAICS.  
Local market context — how many nursing homes in Passaic County, how many employees, avg payroll.

**LODES** — `cur_lodes_geo_metrics`  
3K county-level workforce metrics from Census commuting data (origin-destination, workplace, residence).  
Commuting patterns, earnings tiers, industry mix by county. Passaic: 707K jobs, 15.7% healthcare.

**ABS** — `cur_abs_geo_naics`  
112K rows: firm demographics by state × NAICS — owner race, sex, veteran status.  
Business ownership diversity data. Used for contextual research on employer demographics.

**Census RPE** — `census_rpe_ratios`  
Revenue-per-employee ratios by NAICS × geography from Economic Census.  
Benchmarking tool — is an employer's revenue/employee ratio abnormal for its industry?

---

### Master Employer & Matching Infrastructure

**Master Employers** — `master_employers`, `master_employer_source_ids`  
4.4M unified employer records linked to 13+ source systems via source IDs.  
The canonical employer registry — every employer from every source deduplicated and linked.

**Match Tables** — `osha_f7_matches`, `whd_f7_matches`, `sam_f7_matches`, `nlrb_employer_xref`, `unified_match_log`  
2.2M match audit trail linking source records to F7 employers via 6-tier deterministic cascade.  
How sources connect to union employers — EIN exact, name+city+state, fuzzy, with confidence scores.

**Similarity** — `employer_comparables`, `mv_employer_features`  
270K Gower-distance comparable pairs (top-5 per employer).  
"Employers like this one" — feeds the Similarity scoring factor for finding lookalike workplaces.

---

### Scoring Pipeline (Materialized Views)

- **Organizing Scorecard** (`mv_organizing_scorecard`) — 212K OSHA establishments scored
- **Unified Scorecard** (`mv_unified_scorecard`) — 146,863 F7 union employers, 10 factors, 3 pillars
- **Target Scorecard** (`mv_target_scorecard`) — 4.4M non-union targets, 8 signals, gold standard tiers
- **Search Index** (`mv_employer_search`) — 107K searchable employers for the API/frontend

---

### Research & CBA

**Research Agent** — `research_runs`, `research_facts`, `research_score_enhancements`  
AI research sessions with extracted facts, human validation, and score feedback loop.  
Gemini-powered dossier generation with quality gates (>=7.0 enhances scores, <5.0 rejected).

**CBA Contracts** — `cba_documents`, `cba_provisions`, `cba_categories`  
Collective bargaining agreement full texts with extracted provisions across 14 categories.  
What's in actual union contracts — wages, grievance procedures, seniority rules, benefits.

---

### Specialized / Regional

**Public Sector** — `ps_parent_unions`, `ps_union_locals`, `ps_employers`, `ps_bargaining_units`  
24 parent unions, 1,520 locals, 7,987 public employers, 438 bargaining units.  
Government/municipal union data separate from private-sector F7 pipeline.

**NYC Labor** — `nyc_wage_theft_*`, `nyc_ulp_*`, `nyc_debarment_list`, `nyc_osha_violations`  
~8,600 NYC-specific violation records across wage theft, ULP, debarment, and OSHA.  
Hyperlocal enforcement data for New York City organizing research.

**Web Scraping** — `web_union_profiles`, `web_union_employers`, `web_union_news`  
~800 scraped records from union websites — profiles, employer mentions, contract excerpts, news.  
Supplements structured data with qualitative intelligence from union web presence.

---

## How These Sources Connect

The real power of this platform isn't any single data source — it's the connections between them. The database has a matching system that links the same employer across different government databases using names, addresses, and tax ID numbers. This means we can build a complete picture:

- An employer with a union contract (F-7) that also has serious OSHA violations and a pending unfair labor practice charge (NLRB) and receives $50 million in federal contracts (SAM/USASpending) and is owned by a private equity firm (GLEIF) — all of that can now be seen on one screen.

- A nonprofit hospital (990 data) where a union election failed by 3 votes two years ago (NLRB) and that has since been cited for 12 safety violations (OSHA) and caught stealing $200,000 in wages (WHD) — that's a compelling story for a second organizing attempt.

- A corporate parent (GLEIF/SEC) that owns 15 subsidiaries where 8 already have unions and 7 don't — and the 7 non-union ones all have worse safety records than the unionized ones. That pattern tells a powerful story.

The matching system currently links records at about 96% accuracy across sources. About 1.16 million cross-references have been created connecting the same employer across different databases.

---

## What I Want You to Think About

Given everything described above, I'd like you to explore the following areas. Be specific and creative. Don't just list features — think about who would use each thing, what decision it helps them make, and why the combination of data sources makes it possible.

### For Union Organizers

- How would you design a system that helps an organizer decide which employer to target next? What factors matter most? How should different signals be weighted or combined?
- What would a "company research dossier" look like that gives an organizer everything they need to know before starting a campaign? What story should the data tell?
- How could this data help during an active organizing campaign, not just in choosing where to start one?

### For Researchers and Journalists

- What publishable research questions could be answered by combining these data sources in ways that haven't been done before?
- What investigative stories are hiding in the patterns between safety violations, wage theft, corporate ownership, and union presence (or absence)?
- How could this platform make it easy for a journalist with no data skills to find and tell compelling labor stories?

### For Workers

- How could individual workers use this data to understand their own employer better? What would a 'report card' on your employer look like?
- Could this data power a tool that helps workers compare their employer to similar companies? What comparisons would be most useful?
- What would it take to make this data accessible and meaningful to someone who isn't a researcher or organizer — just a worker curious about their rights and their employer's track record?

### For Policymakers and Advocates

- What policy-relevant analyses become possible when you can see safety violations, wage theft, union presence, and government contracts for the same employer? What arguments could be made?
- How could this data help make the case for or track the impact of labor policies — like right-to-work laws, prevailing wage requirements, or NLRB rule changes?
- Could this platform serve as an early warning system for labor market problems in specific industries or regions? What would that look like?

### Big-Picture Platform Design

1. What's the single most valuable thing this platform could do that nobody else is doing right now?
2. What data is missing that would dramatically increase the platform's usefulness? What additional sources would you want to add?
3. How should AI be integrated into this platform? What role should language models play in helping users understand and act on the data?
4. What are the biggest risks of building a platform like this? What could go wrong ethically, practically, or strategically?
5. How should the platform handle the difference between correlation and causation? (For example: employers with more OSHA violations might also have more union elections — but does that mean violations cause organizing, or that organized workplaces are better at reporting violations?)
6. What would make this platform become the go-to resource for understanding labor relations in America, the way that OpenSecrets became the go-to for understanding money in politics?

---

## Ground Rules for Your Response

1. **Don't hold back.** I want ambitious, creative ideas alongside practical ones. Tell me things I haven't thought of.
2. **Be specific.** Don't say 'the platform could help identify organizing targets.' Tell me exactly what data points you'd combine, what the output would look like, and who specifically would use it.
3. **Think about the human experience.** Who is the person sitting at the computer? What are they trying to do? What are they worried about? How does the platform fit into their actual workday?
4. **Consider what makes data actionable vs. just interesting.** A chart showing national union density trends is interesting. A list of 50 specific employers in your industry within driving distance that have safety violations and no union — that's actionable.
5. **Don't worry about technical feasibility.** I have a development team that can figure out the how. I need you to focus on the what and the why.
6. **Think about what's unique.** Anyone can look up OSHA violations on OSHA's website. What becomes possible only when you can see OSHA violations AND wage theft AND NLRB history AND corporate ownership AND government contracts AND union presence all together for the same employer?

*Take your time. Be thorough. I'd rather have a long, detailed response that gives me genuinely new ideas than a short list of obvious suggestions.*
