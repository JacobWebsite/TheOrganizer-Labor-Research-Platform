# Gemini Deep Research Report: Round 2
**Date:** February 26, 2026
**Analyst:** Gemini (Strategic & Data Coverage Analyst)
**Status:** COMPLETE

---

## Executive Summary

This research round bridges the gap between the platform's technical capabilities and the strategic realities of labor organizing. By synthesizing academic literature, union manuals, and data availability assessments, we have identified a clear path to transform the platform from a "database of the past" into a "targeting engine for the future."

The most critical strategic shift is moving away from a single, heuristic-based "Propensity Score" toward a **multidimensional "Strategic Scorecard"** that weights **Anger (Violations)**, **Stability (Turnover)**, and **Leverage (Jurisdictional Proximity)**.

---

## 1. Research Topic: How Do Organizers Actually Pick Targets?

**The Question:** How do major unions (SEIU, UAW, Teamsters) decide where to run their next campaign, and is the current scoring model aligned with their workflow?

### Findings
*   **Workflow Bifurcation:** Modern organizing is a mix of **Strategic Targeting (Top-Down)** and **Momentum-Based (Bottom-Up)**.
    *   **UAW (Momentum-Based):** Uses a **30-50-70 workflow**: 30% card-signings to go public, 50% for rallies, 70% to file for an election (uaw.org, 2024).
    *   **Teamsters (Strategic-Based):** Prioritizes "core industries" to build market density, rarely filing without a **65% support threshold** (teamster.org).
    *   **SEIU (Market-Based):** Focuses on regional "market density" rather than individual shops (CUNY, 2023).
*   **The Information Need:** Experienced organizers follow the **"Strategic Corporate Research"** framework (Bronfenbrenner, Cornell ILR), looking for jurisdictional alignment, corporate vulnerability, and demographic factors (majority women/POC units have higher win rates).
*   **The Bottleneck:** The bottleneck is not *finding* targets, but **prioritizing** them based on "organizability." Current research is a manual, multi-week process.

### Strategic Recommendations
*   **Pivot from "Finding" to "Vetting":** Provide a "Strategic Dossier" that highlights jurisdictional alignment (e.g., "This warehouse is 10 miles from your strongest local").
*   **Elevate Union Proximity:** Move this from a score factor to a core "Strategic Map" feature.

---

## 2. Research Topic: What Predicts Successful Organizing Campaigns?

**The Question:** Which factors in our current scoring system actually correlate with winning an NLRB election according to academic research?

### Findings
*   **The Strategy Predictor:** Bronfenbrenner’s meta-analysis shows that **comprehensive strategy** (representative committees, one-on-one contact) is a better predictor than any single data point like wages or safety (Bronfenbrenner & Juravich, 1998).
*   **The "Exit-Voice" Paradox:** High turnover (Exit) is a sign of dissatisfaction but an **organizing killer**. Stability is required for building a committee (Freeman & Medoff, 1984).
*   **Factor Analysis:**
    *   **OSHA/WHD Violations:** Strong indicators of **worker anger**, but not "winnability" without stability.
    *   **Demographics:** Majority women and workers of color are the strongest demographic predictors of a win (Bronfenbrenner, 2004).
    *   **Size:** Smaller units (<50) have higher win rates; larger units (>500) provide more strategic power.

### Strategic Recommendations
*   **Adopt a "Checklist Model":** Show a "Readiness Index" (e.g., "High Anger, Low Turnover, High Density") rather than a single number.
*   **Downgrade "Size":** Reduce the 3x weight on Size, which currently buries winnable small shops.

---

## 3. Research Topic: State PERB Data Inventory

**The Question:** Where can we get data for the 7 million public sector workers currently missing from the platform?

### Inventory Table
| State | Agency | Machine-Readable? | Fields Available | Ingestion Difficulty |
|-------|--------|-------------------|------------------|----------------------|
| **WA** | PERC | Yes (Searchable) | Employer, Union, Date, Case Num | Medium |
| **MN** | BMS | **Yes (Web Table)** | Tally, Date, Unit Size, Union | **Easy** |
| **OH** | SERB | Yes (Clearinghouse) | Contracts, Fact-finding, Units | Medium |
| **NY** | PERB | No (PDF-Heavy) | Certifications in PDF only | Hard |
| **CA** | PERB | No (PDF-Heavy) | Decisions/Orders in PDF | Hard |

### Strategic Recommendations
*   **Prioritize MN and WA:** Their data is structured and can be used to prove the public sector concept immediately.
*   **New Table Required:** Create a `public_sector_elections` table to handle PERB-specific schemas.

---

## 4. Research Topic: Job Posting Data as an Organizing Signal

**The Question:** Can we use job posting frequency as a proxy for turnover/organizing potential?

### Findings
*   **Feasibility:** Highly feasible for **macro-trends**, difficult for **employer-level microdata**.
*   **The Signal:** Spikes in postings can indicate a "Trigger Event" (mass quits), but high actual churn makes it harder to organize.
*   **Data Sources:** Indeed Hiring Lab (data.indeed.com) and FRED provide free aggregated indices by industry/city.

### Strategic Recommendations
*   **Use as "Regional Context":** If a region has high job posting growth, workers have more "Exit" options, which may *lower* organizing propensity.
*   **Integrate FRED/Indeed API:** Show "Local Labor Market Heat" on the employer dossier to tell organizers if workers feel safe taking a risk.

---

## 5. Research Topic: How Do Organizers Build Trust in Data Tools?

**The Question:** Why do organizers trust tools like the "Labor Action Tracker" (LAT), and how can we replicate that trust?

### Findings
*   **Trust Factors:** LAT is trusted because it fills a specific gap (small strikes) and uses a **Tiered Verification** system (Official vs. News vs. Social Media).
*   **The Hallucination Risk:** Organizers have zero tolerance for incorrect union-status data. One bad match can destroy the platform's credibility.

### Strategic Recommendations
*   **Replace "Propensity Score" with "Confidence Score":** Always show the 3 specific government filings that generated a match.
*   **Enable User Feedback:** Allow organizers to flag and correct "bad matches" in the UI.

---

## 6. Research Topic: Contract Expiration Data Sources

**The Question:** Where does contract expiration data live, and how valuable is it for targeting?

### Findings
*   **The Source:** **FMCS Form F-7** (Notice to Mediation Agency). Unions must file this at least 30 days before a contract expires (FMCS.gov).
*   **Data Availability:** FMCS publishes monthly Excel exports of these filings.
*   **Strategic Value:** 30 days is perfect for **Competitive Intelligence**. If a competitor's contract is expiring, non-union workers in the same industry are more "organizable."

### Strategic Recommendations
*   **Ingest FMCS Monthly Exports:** Create an `upcoming_expirations` table.
*   **Alert Feature:** Add "Contract Expirations Nearby" to the targeting map.

---

## 7. Research Topic: Proxy Metrics for Turnover and Employee Anger

**The Question:** Is there an open-source way to measure "hidden" metrics like turnover and employee dissatisfaction without proprietary data?

### 1. Measuring Turnover (The "Stability" Signal)
While individual "Quit Rates" are private, we can measure **Replacement Rate** and **Mass Departure** signals:
*   **WARN Act Notices (Mass Turnover):** Mandatory filings for layoffs of 50+ workers. Available via state DOL websites (NY, CA, NJ) and aggregators like `warntracker.com`. This is the most reliable "Mass Turnover" signal.
*   **Job Posting Velocity (Replacement Rate):** Spikes in job postings relative to company size are a direct proxy for churn. We can use the **FRED (Federal Reserve) Indeed Job Postings Index** to "normalize" an employer's churn against their industry average.
*   **H-1B / LCA Filings (Hiring Intent):** The **DOL Foreign Labor Certification (OFLC)** performance data is machine-readable and includes employer names. A sudden stop in LCA filings combined with a WARN notice is a "Strategic Red Flag."

### 2. Measuring Employee Anger (The "Friction" Signal)
Anger leaves a paper trail *before* it becomes a union card:
*   **Review Velocity (Glassdoor/Indeed/Google Maps):** It is not just the rating; it is the **frequency**. A sudden spike in reviews (especially 1-star reviews) is a leading indicator of a "Trigger Event" (e.g., a change in management or benefit cuts).
*   **The "ULP per Employee" Ratio:** Instead of a binary "Has ULP?" flag, we should calculate **ULPs per 100 Employees**. This highlights smaller, "angrier" shops that are currently buried by raw volume from giants like Amazon.
*   **The "Wage/Cost Gap":** Using **BLS QCEW (Quarterly Census of Employment and Wages)** data, we can calculate if an employer is a "Low-Wage Outlier" in their specific county/industry. `(Average Industry Wage in County) - (Estimated Employer Wage) = Structural Anger`.
*   **Community Monitoring:** Mention counts of specific company names in "worker hubs" (e.g., `r/AmazonFC`, `r/StarbucksBaristas`) can be tracked as a proxy for rising discontent.

---

## 8. Research Topic: Revenue-per-Employee (RPE) as a Strategic Signal

**The Question:** How does the existing research on Revenue-per-Employee (RPE) ratios (from the 2022 Economic Census) fit into the "Strategic Scorecard"?

### 1. Estimating Workforce Size (Closing the Data Gap)
The previous research identified **Table EC2200BASIC** from the 2022 Economic Census as the "gold standard" for RPE ratios. 
*   **The Application:** We can use these ratios to estimate the **number of employees** for the 2.5 million employers who currently lack size data but have revenue data (from 990s or corporate filings). This is the key to solving the **"Targeting Paradox"** and making the entire database visible.

### 2. Measuring "Strategic Leverage" (Marshall’s Laws)
According to **Marshall’s Third Law of Derived Demand**, unions are more likely to succeed when labor costs are a **small fraction of total production costs**.
*   **The Signal:** **High RPE = Low Labor Cost Share.** Employers with very high revenue-per-employee can "afford" significant wage increases with minimal impact on their total cost structure. These are **"High-Leverage Targets"** where a union can win substantial gains without triggering mass layoffs or employer insolvency.

### 3. The "Exploitation Index" (RPE vs. Wage Gap)
By comparing an employer’s estimated RPE to the local average wage for that NAICS code, we can calculate an **"Exploitation Index"**:
*   **Formula:** `(Employer RPE) / (Local Average Wage)`.
*   **The Signal:** A high index suggests the employer is capturing a massive surplus from workers. This is a primary driver of **"Structural Anger"** and a high-value talking point for organizers.

---

## Overall Strategic Recommendations

1.  **Kill the "ML" Lie:** Stop labeling the hardcoded heuristic as "ML." Transition to a transparent **"Strategic Scorecard"** that weights Anger, Stability, and Leverage.
2.  **Solve the "Targeting Paradox" with RPE:** Use the 2022 Economic Census RPE ratios to estimate workforce size for the 2.5 million "invisible" employers. This makes the entire database searchable by size.
3.  **MN/WA Public Sector Pilot:** Ingest Minnesota and Washington data immediately to bring millions of workers into the platform.
4.  **The "Competitive Intelligence" Pivot:** Ingest FMCS F-7 data to show organizers when their competitors' contracts expire.
5.  **Implement the "Vulnerability Pulse":** Add a section to the Employer Dossier that combines **WARN Status**, **Review Heat**, and the **"Exploitation Index"** (RPE/Wage Gap).
6.  **Demographics are Essential:** Integrate Census-tract level demographics (race/gender) into the scoring; research confirms this is the strongest predictor of win rates.
