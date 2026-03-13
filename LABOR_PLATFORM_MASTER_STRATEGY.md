# Labor Relations Research Platform — Master Strategy & Data Roadmap
**Version:** 2.0 (Unified)
**Last Updated:** March 4, 2026

---

## 1. Executive Vision: The "OpenSecrets" of Labor
The goal of this platform is to solve the **entity resolution gap** in labor data. By connecting over a dozen disparate U.S. government databases through a 96%-accurate "Corporate Crosswalk," we have moved from "islands of data" to a **Unified Labor Graph**. 

This platform transforms raw regulatory filings into an actionable **Leverage Engine** for workers, organizers, journalists, and policymakers.

---

## 2. The Data Inventory (The Foundation)
The platform currently integrates the following sources, matched via a 6-tier deterministic cascade.

### A. Core Union & Organizing Data
*   **F7 Union Filings:** 146,863 employers with active union contracts. This is the "Gold Standard" training data.
*   **NLRB Elections:** 33K election records with win/loss outcomes and participant counts.
*   **CBA Contracts:** Full-text documents with AI-extracted provisions across 14 categories (wages, benefits, etc.).
*   **Public Sector:** Dedicated data for 24 parent unions and 7,900+ public employers.

### B. Enforcement & Workplace Conditions (The "Anger" Pillars)
*   **OSHA:** 1M establishments and 2.2M violation records ($3.5B in penalties).
*   **WHD Wage & Hour:** 363K wage theft/FLSA cases (2005–2025).
*   **SOII Injury Rates:** 5.7M data points on workplace injuries by industry.

### C. Economic & Workforce Benchmarks
*   **OES Wages:** Occupation-specific wage percentiles by area and industry.
*   **JOLTS/NCS:** Industry-level turnover (quits/hires) and benefit access data.
*   **ACS/CBP/LODES:** Demographic profiles, establishment counts, and commuting patterns.
*   **QCEW:** Quarterly employment and wage benchmarks by county/NAICS.

### D. Corporate Identity & Hierarchy (The "Rosetta Stone")
*   **GLEIF & CorpWatch:** 1.7M+ companies and 4M+ ownership links (parent-subsidiary chains).
*   **SEC EDGAR:** 517K public company filings (CIK, EIN, LEI).
*   **Mergent/D&B:** 56K employers with sales, DUNS, and employee counts.
*   **Crosswalk Table:** 17,111 rows linking all major IDs (CIK, LEI, DUNS, EIN, F7_ID).

### E. Federal & Tax Transparency
*   **Form 990/IRS BMF:** 587K nonprofits (hospitals, universities) with executive pay and assets.
*   **Form 5500:** 259K plan sponsors showing retirement and health benefit participation.
*   **USAspending/SAM.gov:** 900K+ federal contractors and recipient award data.
*   **PPP Loans:** 9.5M borrowers with loan amounts and reported jobs.

---

## 3. Strategic Applications: The Four Personas

### I. For Union Organizers: Strategic Campaigning & Leverage
*   **The "Anger & Ability" Matrix:** A targeting tool that identifies employers where workers are likely aggrieved (high OSHA/WHD violations) but the company has the "Ability to Pay" (high Mergent sales, 990 assets, or USAspending contracts).
*   **The "Poverty Claim Buster":** During bargaining, an organizer can instantly refute "we're broke" claims by showing the employer’s 990 asset growth, PPP loan forgiveness, and high Revenue-per-Employee (Census RPE).
*   **The "Corporate Family Split" Hunter:** Uses the GLEIF hierarchy to find "half-union" parents. Example: *"Parent Corp X has 6 union shops and 6 non-union. The non-union shops have 40% more safety violations."*
*   **Turnover Vulnerability Score:** Uses JOLTS (quit rates) and SOII (injury rates) to flag "Blitz Campaign" targets—places where you must organize quickly before the workforce turns over.

### II. For Researchers & Journalists: Investigative Lead Machine
*   **The "Subcontractor Shield" Investigation:** Uses the Crosswalk to unmask Fortune 500 companies that outsource dangerous work to obscure LLCs with massive OSHA violations.
*   **The "Subsidy-to-Violation" Tracker:** A live dashboard showing federal contractors (USAspending) who are actively being cited for wage theft (WHD) or safety abuses (OSHA).
*   **Non-Profit Enrichment Audit:** Cross-references 990 executive compensation with OES worker wage benchmarks to show the "Inequality Gap" at hospitals and universities.

### III. For Workers: The Employee's Knowledge Shield
*   **The "Know Your Worth" Calculator:** A mobile-first tool where a worker enters their job and location. It tells them: 
    1. The median pay for their job locally (OES).
    2. What union workers at "Lookalike" companies make (CBA data).
    3. Their employer's specific safety and wage violation record.
*   **The "Bad Boss Alert" Subscription:** An email/SMS alert system. If a worker's employer (or any subsidiary in their corporate tree) gets a new NLRB charge or OSHA fine anywhere in the U.S., the worker is notified.

### IV. For Policymakers: Enforceable High-Road Standards
*   **The "Procurement Veto" Screen:** A tool for city councils to audit bidders for government contracts. It rolls up the *entire* corporate family's violation history (not just the local bidding LLC) across all 50 states.
*   **Sectoral Standards Dashboard:** Aggregates CBA provisions to define what "Standard" benefits should look like for an industry (e.g., Home Care), providing the data needed for "Wage Boards" or "Prevailing Wage" legislation.

---

## 4. The AI & Automation Layer (Gemini-Powered)
*   **CBA "Plain English" Translator:** Ingests 200-page contracts and outputs bulleted "What You Get" flyers for workers.
*   **Automated Leaflet Generation:** Ingests a company dossier and generates 3-paragraph, high-impact organizing flyers tailored to that specific warehouse or hospital's violation history.
*   **Power Mapping:** An LLM that can answer: *"Who is the ultimate parent of this nursing home, what other homes do they own, and which ones have active labor disputes?"*

---

## 5. Future Roadmap & Missing Data
*   **Immediate Additions:**
    *   **Visa Data (H-1B/H-2A):** To track exploitation of captive guest workers.
    *   **WARN Act Notices:** To identify mass layoffs and plant closings.
    *   **Property Data:** To identify building owners for physical leverage in organizing.
*   **OpenSecrets Path:** Develop embeddable widgets for labor journalists (e.g., "Top 10 Wage Thieves in [City]") to ensure the platform’s data becomes the industry standard for reporting.

---
**Status:** Ready for implementation of the "Unified Scorecard" (mv_unified_scorecard) and "Target Scorecard" (mv_target_scorecard) UI layers.
