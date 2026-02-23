# GEMINI RESEARCH TASK: Union Contract (CBA) Source Mapping, Provision Taxonomy & LangExtract Extraction Plan

## Context for Gemini

You are conducting foundational research for a Labor Relations Research Platform. The platform already has a PostgreSQL database with 207+ tables, 13.5+ million records, and tracks relationships between ~100,000 employers and ~26,665 unions covering 14.5 million members. It integrates 18+ government databases (OLMS, NLRB, OSHA, DOL wage data, etc.).

The next major project is building a **searchable union contract database** — a system that collects thousands of Collective Bargaining Agreements (CBAs), reads them with AI, extracts the important parts (wages, grievance procedures, benefits, seniority rules, management rights), and makes them searchable. An organizer could type "show me grievance procedures in healthcare contracts in New York" and get back actual contract language from dozens of agreements, with every extracted piece linked back to the exact page and paragraph it came from.

**This document contains three interconnected tasks:**

1. **Source Mapping (Part 1)** — Find out exactly where union contracts live online, how to get them, what format they're in, and what obstacles exist. This is the reconnaissance work.
2. **Provision Taxonomy (Part 2)** — A comprehensive catalog of every provision type that appears in American CBAs, organized as extraction classes for the AI system. This is the "what to look for" blueprint. Your job is to validate, refine, and expand this taxonomy based on what you find when you actually inspect real contracts from the sources in Part 1.
3. **LangExtract Integration Plan (Part 3)** — Design the specific extraction system using Google's LangExtract library, including citation schemas, few-shot example specifications, and document quality classification. This is the "how to extract it" blueprint.

Parts 4-7 cover the processing pipeline, costs, priorities, and reference materials.

This research will be handed to a development team (Claude + Codex) who will build the actual scraping and extraction tools.

---

## PART 1: Source-by-Source Deep Dive

For EACH of the contract sources listed below, I need you to investigate and document the following. Be extremely specific — URLs, exact counts, file formats, access methods. Don't guess. If you can't verify something, say so.

### What to document for each source:

1. **Exact URL** of the contract database/search page
2. **Current count** of available contracts (verify — don't use old numbers)
3. **File format** of the contracts (PDF, DOCX, HTML, scanned image PDFs vs. digital text PDFs)
4. **How contracts are organized** (by employer? by union? by date? by sector?)
5. **Access method**: Can you search and browse freely? Is there a login required? Is there an API? Do you need to submit a public records request?
6. **Download method**: Can you download individual files via direct URL? Is there bulk download? Do you need to click through multiple pages to get one contract?
7. **Metadata available with each contract**: What information comes WITH the contract file — employer name, union name, effective dates, expiration date, number of employees covered, industry/sector, geographic location?
8. **Rate limiting or anti-bot protections**: Any CAPTCHAs, login walls, session tokens, or download limits?
9. **Legal/terms of use**: Any restrictions on automated access or redistribution?
10. **Sample contract inspection**: Actually look at 2-3 sample contracts from each source. Are they:
    - Native digital PDFs (text is selectable/copyable)?
    - Scanned image PDFs (just pictures of pages, text not selectable)?
    - A mix of both?
    - How many pages is a typical contract?
    - Are they well-structured (clear headings like "Article 12 - Grievance Procedure") or unstructured blobs of text?

### Sources to investigate:

#### Tier 1 — Largest public collections (investigate these most thoroughly)

**A. SeeThroughNY (Empire Center)**
- Reported to have ~17,000 New York public-sector contracts
- URL: seethroughny.net (or wherever the contracts actually live)
- This is potentially the single largest freely available source
- Key questions: How are contracts organized? What metadata is available? What's the actual current count? Can they be downloaded programmatically?

**B. New Jersey PERC (Public Employment Relations Commission)**
- Reported ~6,366 contracts
- URL: nj.gov/perc/ or their contract database
- Key questions: Is there a searchable interface? What sectors are covered? Are these all current or do they include historical?

**C. Ohio SERB (State Employment Relations Board)**
- Reported 3,000-5,000+ contracts with ~1,000+ new filings per year
- Key questions: How far back does the archive go? What's the actual download mechanism?

**D. OPM Federal CBA Database**
- Reported 1,000-2,000 federal-sector contracts
- URL: opm.gov — there may be an API endpoint at opm.gov/cba/api/
- Key questions: Does the API actually work? What format does it return? What agencies are covered?

**E. DOL/OLMS CBA File (Public Disclosure Room)**
- Reported 1,500-2,500 contracts for agreements covering 1,000+ employees
- This is the federal Department of Labor's own collection
- Key questions: What's the online vs. paper-only split? The labordata/opdr GitHub project reportedly has code for this — find that repo and assess it

#### Tier 2 — Significant supplementary sources

**F. Cornell Kheel Center / ILR eCommons**
- Historical BLS/OLMS collection, 685 linear feet spanning 1887-2003
- Estimated 3,000-5,000 digitized contracts
- Reportedly accessible via DSpace OAI-PMH harvesting protocol
- Key questions: What's actually digitized vs. paper-only? Is the OAI-PMH endpoint active? What format are digitized contracts in?

**G. WageIndicator Foundation**
- Reported 3,600+ coded CBAs from 76 countries
- Key questions: Are these full contracts or just extracted data? What coding scheme do they use? Is this useful as a training reference for our extraction?

**H. California CalHR State Employee Contracts**
- State-level public employee contracts
- Key questions: How many? What format? How accessible?

**I. Individual union contract pages**
- UFCW 3000 reportedly lists 100+ contracts
- APWU, NALC (postal unions) publish their national agreements
- Key questions: Which major unions publish contracts on their websites? How standardized are the formats?

#### Tier 3 — Potential sources requiring further investigation

**J. Municipal/county websites**
- Major cities (NYC, Chicago, LA, etc.) may publish employee contracts
- Key questions: Identify 5-10 major cities that publish contracts online with direct links

**K. University systems**
- Many public university systems have faculty/staff union contracts online
- Key questions: Identify 5-10 large university systems with contracts available

**L. Bloomberg Law Labor PLUS / BNA**
- The most comprehensive private-sector source but subscription-required
- Key questions: What does CUNY library access provide? Is there any institutional access pathway? What would it cost independently?

---

## PART 2: CBA Provision Taxonomy

This section catalogs every major provision type that appears in American Collective Bargaining Agreements. It serves as the blueprint for what the AI extraction system needs to identify, classify, and extract.

**Your task with this taxonomy:** Validate it against real contracts you examine during your Part 1 source research. When you look at actual contracts from SeeThroughNY, NJ PERC, Ohio SERB, etc., check whether:
- Any provision types are MISSING from this taxonomy that you see in real contracts
- Any provision types described here don't match how they actually appear in practice
- The complexity ratings and prevalence estimates seem accurate
- The sector-specific provisions match what you see in contracts from those sectors
- Any emerging provisions (AI, DEI, climate, remote work) appear more or less frequently than estimated

Add, modify, or flag issues as needed. The taxonomy should reflect reality, not theory.

### How to read this taxonomy

Each provision entry includes:
- **What it is** in plain English
- **How to find it** — headings, keywords, and language patterns that signal this provision
- **What to extract** — specific structured data points
- **How common it is** — prevalence estimate across contracts
- **Complexity rating:**
  - 🟢 **Simple** — Short, clear data points. Expected AI accuracy: 85-95%.
  - 🟡 **Medium** — Multi-part sections. Expected AI accuracy: 75-85%.
  - 🔴 **Complex** — Multi-page nested provisions. Expected AI accuracy: 60-75%.

---

### 2.0 Contract Structure (Extract First)

Before extracting individual provisions, the system needs to understand how each contract is organized.

**Standard article numbering:** Contracts are divided into numbered "Articles" (sometimes "Sections" or "Chapters"). A typical 50-page contract has 25-40 articles. Common ordering:

1. Preamble / Purpose
2. Recognition
3. Union Security / Dues
4. Management Rights
5. Grievance Procedure
6. Arbitration
7. No Strike / No Lockout
8. Seniority
9. Hours of Work
10. Overtime
11. Wages
12. Holidays
13. Vacations
14. Sick Leave
15. Leaves of Absence
16. Insurance / Benefits
17. Pension / Retirement
18. Safety and Health
19. Discipline and Discharge
20. Miscellaneous
21. Duration

Article order varies, but topics remain consistent. The extraction system should recognize topics by content, not position.

**What to extract from structure:**
- Total number of articles
- Article titles and numbering scheme
- Presence of table of contents
- Whether appendices, side letters, or MOUs are attached
- Total page count
- Single-employer vs. multi-employer agreement

### 2.1 Preamble / Purpose Statement

**What it is:** Opening paragraph(s) naming the parties and stating intent.

**How to find it:** First text after the title. "This Agreement is entered into by and between..."

**What to extract:** Full legal name of employer; full legal name of union (international/national); local union number; AFL-CIO affiliation; execution date; general purpose statement.

**Prevalence:** ~99%. **Complexity:** 🟢 Simple

---

### CATEGORY A: CORE ECONOMIC PROVISIONS

#### 2.2 Wage Rates and Wage Schedules

**What it is:** Base pay rates for covered employees — can range from a single hourly rate to complex multi-page tables with rates for dozens of classifications, each with multiple steps by years of service.

**How to find it:** "Wages," "Compensation," "Pay Rates," "Salary Schedule," "Wage Scale." Often appears as a table or appendix.

**What to extract:** Base hourly rate(s) or annual salaries; job classification titles with rates; step/longevity increases; effective dates per rate (Year 1, 2, 3); rate type (hourly/daily/weekly/annual); minimum and maximum rates; lump-sum payments in lieu of raises.

**Prevalence:** ~100%. **Complexity:** 🔴 Complex — Format varies enormously. Healthcare contracts may have 200+ job titles with 15 steps each. Construction specifies rates by trade. Education uses degree-level × experience matrices. Manufacturing uses labor grade systems.

#### 2.3 Shift Differentials and Premium Pay

**What it is:** Extra pay for nights, weekends, hazardous duty, bilingual work, or lead worker responsibilities.

**How to find it:** Within Wages article or "Premium Pay," "Shift Differential," "Special Pay."

**What to extract:** Dollar amount or percentage per differential; which shifts/conditions trigger it; whether added to base rate or paid separately; eligibility requirements.

**Prevalence:** ~60-70%. **Complexity:** 🟡 Medium

#### 2.4 Overtime Provisions

**What it is:** When overtime kicks in, how it's calculated, and how it's distributed.

**How to find it:** "Overtime" or within "Hours of Work" or "Compensation."

**What to extract:** Overtime trigger (after 8 hrs/day? 40 hrs/week? both?); overtime rate (1.5x, 2x); double-time triggers; distribution method (seniority? rotation? volunteers first?); mandatory overtime rules; pyramiding rules; callback/call-in pay minimums.

**Prevalence:** ~85-90%. **Complexity:** 🟡 Medium

#### 2.5 Holiday Pay and Schedule

**What it is:** Recognized paid holidays and premium pay for working on holidays.

**How to find it:** "Holidays" or "Holiday Pay." Usually an enumerated list.

**What to extract:** List of holidays; total number per year; holiday pay rate; floating holidays; eligibility rules (must work day before/after); weekend fallback rules.

**Prevalence:** ~95%. **Complexity:** 🟢 Simple

#### 2.6 Vacation / Paid Time Off (PTO)

**What it is:** Paid time away accruing by length of service.

**How to find it:** "Vacations," "Paid Time Off," "Annual Leave."

**What to extract:** Accrual schedule by service years; max accumulation/carryover; cash-out provisions; scheduling procedures and seniority priority; payout at termination.

**Prevalence:** ~95%. **Complexity:** 🟡 Medium

#### 2.7 Sick Leave

**What it is:** Paid time for illness, injury, or medical appointments.

**How to find it:** "Sick Leave" or "Illness and Injury."

**What to extract:** Accrual rate; max accumulation; cash-out at retirement; documentation requirements; family use allowed; sick leave bank/donation programs.

**Prevalence:** ~80-90%. **Complexity:** 🟢 Simple

#### 2.8 Personal Leave and Bereavement Leave

**What it is:** Paid days for personal business and family deaths.

**How to find it:** Own article or within "Leaves of Absence."

**What to extract:** Personal days per year; bereavement days; qualifying family relationships; travel day provisions; rollover rules.

**Prevalence:** ~75-85%. **Complexity:** 🟢 Simple

#### 2.9 Family and Medical Leave (FMLA-Related)

**What it is:** Extended leave for serious health conditions, childbirth, adoption, or caregiving. May exceed federal FMLA minimums.

**How to find it:** "Family and Medical Leave," "FMLA," "Parental Leave," or within "Leaves of Absence."

**What to extract:** Whether it merely references FMLA or enhances it; leave duration; paid portions; job protection beyond FMLA; parental-specific provisions; concurrent PTO/sick usage requirement.

**Prevalence:** ~50-70%. **Complexity:** 🟡 Medium

#### 2.10 Health Insurance and Medical Benefits

**What it is:** Employer-provided health coverage — often the most expensive and most-fought-over economic provision.

**How to find it:** "Insurance," "Health Benefits," "Medical Benefits," "Health and Welfare." Sometimes detailed in appendix rather than body text.

**What to extract:** Plan types (HMO, PPO, HDHP); employer vs. employee premium shares ($ or %); shares by tier (employee-only, family); deductibles; copays; out-of-pocket max; waiting period; retiree coverage; opt-out payments; FSA/HSA provisions; cost-increase reopener triggers.

**Prevalence:** ~90%. **Complexity:** 🔴 Complex — Can be extremely detailed or extremely vague (sometimes just "the employer shall continue to provide health insurance" with details in a separate plan document).

#### 2.11 Dental and Vision Benefits

**What it is:** Separate dental and eye care coverage.

**How to find it:** Within Insurance/Benefits article.

**What to extract:** Dental provided (yes/no); vision provided (yes/no); coverage levels; employer cost share; orthodontia; glasses/contacts allowance.

**Prevalence:** ~60-75%. **Complexity:** 🟢 Simple

#### 2.12 Pension and Retirement Benefits

**What it is:** Retirement plan contributions. Key distinction: "defined benefit" (traditional pension — guaranteed monthly payment) vs. "defined contribution" (401k/403b — employer contributes but amount depends on investments).

**How to find it:** "Pension," "Retirement," "401(k)," "Defined Benefit Plan."

**What to extract:** Plan type (DB, DC, or both); benefit formula for DB; contribution rate for DC; employee contribution requirement; vesting schedule; retirement eligibility (age + service); single-employer vs. multi-employer (Taft-Hartley); early retirement provisions.

**Prevalence:** ~70-80%. **Complexity:** 🟡 Medium

#### 2.13 Life Insurance and Disability Benefits

**What it is:** Employer-provided life insurance, short-term and long-term disability.

**How to find it:** Within Insurance/Benefits article.

**What to extract:** Life coverage amount; AD&D; STD duration/percentage/waiting period; LTD duration/percentage/definition; employer-paid vs. cost-sharing.

**Prevalence:** ~50-65%. **Complexity:** 🟢 Simple

#### 2.14 Wage Reopener Clause

**What it is:** Right to reopen negotiations on wages during a multi-year contract.

**How to find it:** Within Wages or Duration article. "Reopener," "wage review."

**What to extract:** Trigger date; subjects that can be reopened; notice requirements; strike/lockout rights during reopener.

**Prevalence:** ~25-40%. **Complexity:** 🟢 Simple

#### 2.15 Other Economic Provisions

These appear less frequently but are important when present. Extract each as a yes/no flag plus relevant details:

- **Severance pay** — Formula (weeks per year of service), eligibility, caps. Prevalence: ~20-30%.
- **Tuition reimbursement** — Annual dollar cap, eligible programs, grade requirements, service commitment. Prevalence: ~30-40%.
- **Uniform and tool allowances** — Dollar amount, frequency, what's covered. Prevalence: ~35-50%.
- **Travel/mileage reimbursement** — Per-mile rate, meal per diems. Prevalence: ~30-45%.
- **Signing/ratification bonus** — Dollar amount, eligibility, payment date. Prevalence: ~20-35%.
- **Jury duty pay** — Duration, full pay vs. differential. Prevalence: ~50-60%.
- **Military leave** — Supplemental pay beyond USERRA, job protections. Prevalence: ~30-40%.

**Complexity for all:** 🟢 Simple

---

### CATEGORY B: WORKPLACE RULES AND CONDITIONS

#### 2.16 Hours of Work and Scheduling

**What it is:** Standard workday/workweek, shift times, schedule posting, and change procedures.

**How to find it:** "Hours of Work," "Work Schedules," "Working Conditions."

**What to extract:** Standard day length; standard week; shift start/end times; advance schedule posting requirement; schedule change notice; flexible scheduling; split shift rules; reporting/show-up pay (minimum guaranteed if sent home).

**Prevalence:** ~90-95%. **Complexity:** 🟡 Medium

**Sector variations:** Healthcare has rotating schedules and 12-hour shifts; public safety has 24-hour Kelly schedules; education ties to school calendar; retail has predictive scheduling.

#### 2.17 Safety and Health

**What it is:** Requirements beyond OSHA minimums, joint safety committees, right to refuse unsafe work.

**How to find it:** "Safety and Health," "Health and Safety," "Working Conditions."

**What to extract:** Joint safety committee (yes/no); meeting frequency; right to refuse unsafe work; PPE provisions; specific safety standards; accident reporting; right to accompany OSHA inspectors; hazard pay cross-references.

**Prevalence:** ~65-80%. **Complexity:** 🟡 Medium

#### 2.18 Drug and Alcohol Testing

**What it is:** When/how employees are tested, consequences, rehabilitation provisions.

**How to find it:** Own article or within "Working Conditions" or "Rules of Conduct."

**What to extract:** Testing types (pre-employment, random, reasonable suspicion, post-accident); consequences of positive test; EAP referral; confirmation testing requirements; DOT applicability.

**Prevalence:** ~45-60%. **Complexity:** 🟡 Medium

#### 2.19 Technology, Electronic Monitoring, and Surveillance

**What it is:** Rules about cameras, GPS, email monitoring, keystroke logging, personal devices, social media.

**How to find it:** "Technology," "Electronic Monitoring," "Privacy," "Use of Electronics." Newer provision — may not exist in older contracts.

**What to extract:** Notification requirements before monitoring; monitoring types addressed; restrictions on using monitoring for discipline; BYOD policies; social media policies; AI/algorithmic management provisions.

**Prevalence:** ~20-35% overall, higher in newer contracts. **Complexity:** 🟡 Medium

**Special note:** This is one of the fastest-evolving areas. The UC Berkeley "Negotiating Tech" project identified 6 categories across 175+ agreements. AI provisions are appearing since ~2023. Flag any technology language for special attention.

#### 2.20 Remote Work / Telework

**What it is:** Working from home provisions. Very rare before 2020, widespread after COVID.

**How to find it:** "Telework," "Remote Work," "Work from Home."

**What to extract:** Eligibility criteria; right vs. management discretion; equipment provisions; availability expectations; home office stipends; return-to-office rules.

**Prevalence:** ~15-30% (much higher in newer office-worker contracts). **Complexity:** 🟢 Simple

#### 2.21 Workplace Violence Prevention

**What it is:** Policies on threats, intimidation, physical violence — reporting and response.

**How to find it:** Within "Safety and Health" or own article. More common in healthcare and public-facing workplaces.

**What to extract:** Definition used; reporting procedures; employer response obligations; employee protections; training requirements.

**Prevalence:** ~25-40%. **Complexity:** 🟢 Simple

---

### CATEGORY C: UNION RIGHTS AND SECURITY

#### 2.22 Recognition Clause

**What it is:** Identifies the union as exclusive bargaining representative and defines exactly which employees are in the bargaining unit.

**How to find it:** Almost always Article 1 or 2. "Recognition" or "Recognition and Scope."

**What to extract:** Full union name; exact bargaining unit description (who's in); excluded categories (who's out); NLRB certification case number if certified; geographic scope; included job titles.

**Prevalence:** ~100%. **Complexity:** 🟡 Medium

#### 2.23 Union Security Clause

**What it is:** Whether employees must join or financially support the union. Varies dramatically by state (right-to-work laws).

**How to find it:** "Union Security," "Union Membership," "Agency Shop."

**What to extract:** Type: union shop / agency shop (fair share) / maintenance of membership / open shop; time period for new hires to comply; religious objection provisions; right-to-work acknowledgment.

**Prevalence:** ~85-90%. **Complexity:** 🟡 Medium

#### 2.24 Dues Checkoff

**What it is:** Employer deducts union dues from paychecks and sends them to the union.

**How to find it:** "Dues Checkoff" or "Deduction of Dues," usually within Union Security.

**What to extract:** Checkoff provided (yes/no); what's deducted (dues, initiation fees, assessments, PAC); frequency; authorization requirements; revocation procedures.

**Prevalence:** ~95%. **Complexity:** 🟢 Simple

#### 2.25 Union Access and Communication

**What it is:** Union's right to enter the workplace, use bulletin boards, communicate with members.

**How to find it:** "Union Rights," "Union Activity," "Union Business."

**What to extract:** Workplace access rights; notice requirements; bulletin board rights (physical/electronic); email/intranet access; meeting space; literature distribution.

**Prevalence:** ~75-85%. **Complexity:** 🟢 Simple

#### 2.26 Union Steward / Release Time

**What it is:** Union representatives can conduct union business during work hours with pay.

**How to find it:** "Union Representatives," "Stewards," or within Grievance Procedure.

**What to extract:** Number of stewards; compensation for steward time; hours allocated; supervisor permission requirement; release for negotiations; release for conventions; full-time union officer provisions.

**Prevalence:** ~80-90%. **Complexity:** 🟡 Medium

#### 2.27 Information Rights

**What it is:** Employer's obligation to provide the union with employee data needed for bargaining and contract administration.

**How to find it:** Own article or scattered. "Provide the union with," "employer shall furnish."

**What to extract:** Required information (seniority lists, new hires, wage data, etc.); update frequency; format requirements; response timeline.

**Prevalence:** ~40-60% as explicit language. **Complexity:** 🟢 Simple

#### 2.28 No-Strike / No-Lockout Clause

**What it is:** Union won't strike, employer won't lock out, during the contract term. The trade-off for the arbitration system.

**How to find it:** "No Strike / No Lockout," "Strikes and Lockouts," "Work Stoppages."

**What to extract:** Whether absolute or conditional; sympathy strike prohibition; consequences for violation; employer lockout waiver; ULP strike exception.

**Prevalence:** ~85-95% (private sector). **Complexity:** 🟢 Simple

#### 2.29 Successor and Assigns Clause

**What it is:** Requires buyer/successor company to honor the existing contract if the company is sold.

**How to find it:** Own short article or within "Duration" or "General Provisions."

**What to extract:** Successorship provision exists (yes/no); buyer must assume contract; union notification before sale; covers partial sales.

**Prevalence:** ~30-50%. **Complexity:** 🟢 Simple

---

### CATEGORY D: MANAGEMENT RIGHTS

#### 2.30 Management Rights Clause

**What it is:** Reserves decisions to management's sole discretion. Defines the power balance of the entire contract.

**How to find it:** Own article, usually early (Articles 3-5). "Management Rights" or "Employer Rights."

**What to extract:** Exists (yes/no — absence is significant); type: broad/residual ("all rights except as limited") vs. narrow/specific (enumerated list); specific rights listed; whether rights are subject to grievance procedure; explicit limitations.

**Prevalence:** ~80-90%. **Complexity:** 🟡 Medium

#### 2.31 Subcontracting and Outsourcing

**What it is:** Restrictions on sending bargaining unit work to outside contractors.

**How to find it:** Own article or within Management Rights. "Subcontracting," "contracting out," "outsourcing."

**What to extract:** Restriction exists (yes/no); type: prohibition / prohibition if causes layoffs / notice required / must bargain / must pay prevailing wage; information rights; exceptions.

**Prevalence:** ~40-55%. **Complexity:** 🟡 Medium

#### 2.32 Technological Change

**What it is:** Requirements when employer introduces new technology that changes or eliminates jobs.

**How to find it:** Own article or within Management Rights. "Technological change," "automation," "new methods."

**What to extract:** Notice requirement; advance notice period; retraining obligation; impact bargaining right; transfer rights; anti-job-loss protections; AI/algorithmic provisions.

**Prevalence:** ~20-35%. **Complexity:** 🟡 Medium

#### 2.33 Plant Closure / Relocation

**What it is:** Notice and protections before closing a facility or relocating operations.

**How to find it:** Own article or within Management Rights or "Job Security."

**What to extract:** Advance notice (beyond WARN Act); bargaining obligation; transfer rights; severance triggered by closure; retraining/placement assistance; community impact provisions.

**Prevalence:** ~15-30%. **Complexity:** 🟡 Medium

---

### CATEGORY E: EMPLOYEE RIGHTS AND PROTECTIONS

#### 2.34 Just Cause Standard

**What it is:** Employer can only discipline/fire for a fair, documented reason — not "at will." Widely considered the single most important union contract protection.

**How to find it:** "Discipline and Discharge," "Corrective Action," "Just Cause."

**What to extract:** Just cause standard exists (yes/no); exact language ("just cause" / "proper cause" / "cause" / "good cause" — these have different legal weight); applies to all discipline or only termination; probationary exclusion.

**Prevalence:** ~95%. **Complexity:** 🟢 Simple

#### 2.35 Progressive Discipline

**What it is:** Escalating discipline steps — verbal warning → written warning → suspension → termination.

**How to find it:** Within "Discipline and Discharge."

**What to extract:** Number of steps; what each step is; must steps be followed in order; exceptions for serious offenses; how long records remain in file; right to union presence (Weingarten); last chance agreements.

**Prevalence:** ~70-80%. **Complexity:** 🟡 Medium

#### 2.36 Seniority

**What it is:** Priority system based on length of service. One of the most fundamental organizing principles.

**How to find it:** Own article titled "Seniority." Often one of the longest articles.

**What to extract:** How seniority is defined (hire date? bargaining unit entry? classification-specific?); accrual during leave/layoff; applications (job bidding, shift preference, vacation scheduling, overtime distribution, layoff order, recall order, transfers); loss-of-seniority events; seniority list posting; super seniority for stewards; probationary period before seniority begins.

**Prevalence:** ~90-95%. **Complexity:** 🔴 Complex

#### 2.37 Layoff and Recall

**What it is:** How layoffs are ordered, bumping rights, how long recall rights last, recall order.

**How to find it:** Own article or within "Seniority."

**What to extract:** Layoff order (inverse seniority); bumping rights (yes/no); bumping scope (plant-wide, department, classification); recall order (most senior first); recall period duration; notice requirements; severance; obligation to offer available work first.

**Prevalence:** ~75-85%. **Complexity:** 🔴 Complex

#### 2.38 Job Posting and Bidding

**What it is:** When jobs open, employer must post them and allow employees to bid based on seniority/qualifications.

**How to find it:** "Job Posting," "Promotions and Transfers," "Vacancies."

**What to extract:** Posting required (yes/no); posting duration; required posting content; selection criteria (pure seniority / qualifications first / hybrid); trial period; right to return to former position.

**Prevalence:** ~70-80%. **Complexity:** 🟡 Medium

#### 2.39 Non-Discrimination

**What it is:** Prohibits discrimination. May mirror or exceed federal/state law.

**How to find it:** "Non-Discrimination" or "Equal Employment Opportunity."

**What to extract:** Protected categories listed; whether it exceeds existing law; whether claims can be grieved; disability accommodation provisions.

**Prevalence:** ~80-90%. **Complexity:** 🟢 Simple

#### 2.40 Probationary Period

**What it is:** Initial employment period with limited contract protections.

**How to find it:** Within "Seniority" or "New Employees."

**What to extract:** Length (30/60/90/120/180 days); which provisions apply during probation; extension allowed; when seniority begins; whether termination can be grieved.

**Prevalence:** ~80-90%. **Complexity:** 🟢 Simple

#### 2.41 Personnel File Access

**What it is:** Right to review and copy contents of personnel file; right to respond to materials.

**How to find it:** "Employee Rights," "Personnel Records," "Discipline."

**What to extract:** Inspection right; frequency; copy right; response right; restrictions on file contents; old record removal timeline.

**Prevalence:** ~40-55%. **Complexity:** 🟢 Simple

#### 2.42 Past Practice / Maintenance of Standards

**What it is:** Preserves existing working conditions even if not spelled out in the contract.

**How to find it:** "Past Practice," "Maintenance of Standards," "Existing Conditions." May be in "General Provisions."

**What to extract:** Exists (yes/no); exact language; scope (mandatory subjects only or all conditions); limitations.

**Prevalence:** ~35-50%. **Complexity:** 🟢 Simple (to extract; legal implications are vast)

---

### CATEGORY F: DISPUTE RESOLUTION

#### 2.43 Grievance Procedure

**What it is:** Multi-step process for resolving contract disputes. The enforcement mechanism for everything else in the contract.

**How to find it:** Own article, usually one of the longest. "Grievance Procedure" or "Complaint Procedure."

**What to extract — FOR EACH STEP:** Who participates (union side); who participates (management side); time limit to file (calendar or business days); time limit for response; meeting required or optional; written response required.

**Also extract:** Number of steps (typically 2-4); who can file (individual, union, group, employer); definition of "grievance"; class action grievances allowed; different procedure for discipline cases; consequence of missed time limits.

**Prevalence:** ~99%. **Complexity:** 🔴 Complex

#### 2.44 Arbitration

**What it is:** Independent neutral third party decides grievances as the final step. Replaces courts for contract disputes.

**How to find it:** Own article or final section of Grievance Procedure.

**What to extract:** Binding vs. advisory; arbitrator selection method (permanent, AAA, FMCS, state agency, mutual); arbitrator's authority scope (can they add to/modify contract?); back pay authority; excluded subjects; cost sharing; timeline; expedited arbitration provisions.

**Prevalence:** ~95%. **Complexity:** 🟡 Medium

#### 2.45 Mediation

**What it is:** Optional step between grievance and arbitration — mediator helps parties settle (cannot impose decision).

**How to find it:** Within Grievance or Arbitration articles.

**What to extract:** Available (yes/no); mandatory or optional; provider (FMCS, state agency, private); cost sharing; binding or non-binding.

**Prevalence:** ~15-25%. **Complexity:** 🟢 Simple

---

### CATEGORY G: CONTRACT ADMINISTRATION

#### 2.46 Duration

**What it is:** Effective and expiration dates.

**How to find it:** Usually last article. "Duration" or "Term of Agreement."

**What to extract:** Effective date; expiration date; total duration; automatic renewal/evergreen clause; termination notice period (typically 60-90 days before expiration).

**Prevalence:** ~100%. **Complexity:** 🟢 Simple

#### 2.47 Separability / Savings Clause

**What it is:** If one provision is struck down, the rest survives.

**How to find it:** Near end of contract or "General Provisions."

**What to extract:** Exists (yes/no); renegotiation obligation for invalid provision.

**Prevalence:** ~75-85%. **Complexity:** 🟢 Simple

#### 2.48 Entire Agreement / Zipper Clause

**What it is:** The written contract is the complete agreement — nothing outside it is enforceable. Waives mid-term bargaining duty.

**How to find it:** "General Provisions." "Entire agreement," "complete agreement," "zipper."

**What to extract:** Exists (yes/no); exact language; explicit mid-term bargaining waiver; exceptions.

**Prevalence:** ~50-65%. **Complexity:** 🟢 Simple

#### 2.49 Side Letters and MOUs

**What it is:** Supplementary documents addressing specific issues — temporary arrangements, implementation details, items that don't fit the main structure.

**How to find it:** Appendices or attachments at end. "Side Letter," "Letter of Agreement," "Memorandum of Understanding," "MOU."

**What to extract:** Number of side letters/MOUs; subject of each; incorporated into contract or separate; effective/expiration dates; signing parties.

**Prevalence:** ~60-75%. **Complexity:** 🟡 Medium

#### 2.50 Printing and Distribution

**What it is:** Who prints contract copies and distributes them.

**How to find it:** Short clause in "General Provisions."

**What to extract:** Who pays (employer/union/shared); distribution method; electronic distribution; timeline.

**Prevalence:** ~40-55%. **Complexity:** 🟢 Simple

---

### CATEGORY H: SECTOR-SPECIFIC PROVISIONS

The extraction system should recognize these when present. They appear primarily in contracts from specific industries.

#### 2.51 Construction Industry Provisions

- **Hiring hall** — Union referral system. Extract: exclusive or non-exclusive; referral order; employer rejection rights. Prevalence in construction: ~80%.
- **Apprenticeship** — Joint training programs. Extract: apprentice-to-journeyworker ratio; training requirements; wage progression. Prevalence: ~70%.
- **Travel pay and subsistence** — Compensation for traveling to job sites. Extract: mileage radius; per diem rates; zone pay. Prevalence: ~75%.
- **Show-up/reporting pay** — Minimum pay if work canceled after reporting. Extract: guaranteed minimum hours (typically 2-4). Prevalence: ~80%.
- **Jurisdictional clauses** — Which trade does which work. Extract: work descriptions; jurisdictional boundaries. Prevalence: ~60%.

#### 2.52 Healthcare Provisions

- **Staffing ratios** — Minimum nurse-to-patient ratios. Extract: ratios by unit type (ICU, med-surg, ER); enforcement mechanisms. Prevalence in healthcare: ~30-40%.
- **Float pool** — Reassignment to other units. Extract: frequency limits; pay premiums; orientation requirements. Prevalence: ~50%.
- **Mandatory overtime restrictions** — Limits on forced overtime beyond shift. Extract: prohibited (yes/no); emergency exceptions; penalty pay. Prevalence: ~45%.
- **Professional practice** — Protecting clinical judgment. Extract: right to refuse beyond-competency assignments; professional development time; CE support. Prevalence: ~35%.

#### 2.53 Education Provisions

- **Class size** — Maximum students per class. Extract: limits by grade; consequences if exceeded. Prevalence in education: ~50%.
- **Academic freedom** — Teaching method protections. Extract: scope; limitations. Prevalence: ~40%.
- **Tenure** — Job security after probation (distinct from seniority). Extract: probation length; criteria; review process. Prevalence: ~55%.
- **Evaluation procedures** — How teachers are evaluated. Extract: frequency; evaluator; criteria; consequences; union role. Prevalence: ~65%.
- **Preparation time** — Guaranteed planning time during workday. Extract: minutes per day; meeting restrictions. Prevalence: ~60%.

#### 2.54 Public Safety Provisions

- **Officer bill of rights** — Internal investigation protections. Extract: interrogation rules; representation; notice; cooling-off periods. Prevalence in public safety: ~60%.
- **Use of force** — Rules on force application. Extract: contract incorporation; review procedures. Prevalence: ~30%.
- **Fitness for duty** — Physical testing requirements. Extract: standards; failure consequences; accommodations. Prevalence: ~40%.
- **Equipment/vehicles** — Body cameras, take-home vehicles. Extract: what's provided; camera activation rules. Prevalence: ~50%.

#### 2.55 Transportation Provisions

- **Hours of service** — Beyond DOT requirements. Extract: max driving hours; rest periods; sleeper provisions. Prevalence in transportation: ~55%.
- **Route bidding** — Seniority-based route selection. Extract: bidding frequency; bump procedures. Prevalence: ~65%.
- **Equipment standards** — Vehicle safety/comfort. Extract: age limits; maintenance; AC/heat; technology. Prevalence: ~50%.

---

### CATEGORY I: EMERGING AND EVOLVING PROVISIONS

These are relatively new, growing in prevalence, and may not appear in older classification systems. Flag any occurrence.

#### 2.56 Artificial Intelligence and Algorithmic Management

**What it is:** Employer use of AI for hiring, scheduling, performance evaluation, discipline, workforce management.

**How to find it:** "Technology," "Working Conditions," or side letters. "Artificial intelligence," "AI," "algorithm," "automated decision."

**What to extract:** AI addressed (yes/no — flag if yes); restrictions on AI-based discipline; transparency requirements; human review requirements; bargaining rights over AI.

**Prevalence:** ~5-10% but growing rapidly. Most date from 2023+.

#### 2.57 Diversity, Equity, and Inclusion (DEI)

**What it is:** Beyond non-discrimination — affirmative equity goals, anti-racism training, pay equity audits.

**How to find it:** Own article or side letter. "Diversity," "equity," "inclusion," "DEI," "pay equity."

**What to extract:** DEI provisions exist; joint committees; pay equity audits; diversity training; affirmative action.

**Prevalence:** ~15-25% of newer contracts.

#### 2.58 Climate / Environmental Provisions

**What it is:** Extreme heat, air quality, just transition for workers displaced by clean energy shifts.

**How to find it:** "Safety," "Working Conditions," or side letters. "Climate," "extreme heat," "just transition."

**What to extract:** Heat protections; air quality provisions; green jobs training; transition protections.

**Prevalence:** ~5% but a frontier area.

#### 2.59 Pandemic / Public Health Emergency

**What it is:** Workplace protocols during pandemics. Many added during/after COVID-19.

**How to find it:** Own article or side letter. "Pandemic," "public health emergency," "infectious disease."

**What to extract:** Remote work triggers; PPE requirements; hazard pay; quarantine leave; vaccination policies.

**Prevalence:** ~20-30% of contracts negotiated since 2020.

---

### 2.60 Language Patterns for Extraction

The AI extraction system should use these keywords and phrases as recognition triggers.

**Modal verb significance** (from Arold et al. NBER research): The legal force of a provision depends on the modal verb:
- **"shall"** = mandatory obligation
- **"will"** = strong commitment, slightly less formal
- **"may"** = permissive/discretionary
- **"shall not"** = prohibition
- **"must"** = mandatory, often for employee obligations

The extraction system should record which modal verb is used for each provision.

**Common trigger phrases by provision type:**

| Provision | Key Phrases |
|-----------|------------|
| Wages | "base rate," "hourly rate," "wage scale," "salary schedule," "step increase," "longevity," "COLA" |
| Grievance | "grievance shall be filed," "within [X] working days," "Step 1/2/3," "referred to arbitration" |
| Seniority | "seniority shall be defined as," "departmental seniority," "plant-wide seniority," "loss of seniority" |
| Mgmt rights | "employer retains the right," "sole and exclusive right," "management prerogative," "direct the workforce" |
| Just cause | "just cause," "proper cause," "discharged or disciplined," "without just and sufficient cause" |
| Union security | "condition of employment," "agency fee," "fair share," "union shop," "maintenance of membership" |
| No-strike | "no strike," "no work stoppage," "no slowdown," "sympathy strike," "no lockout" |
| Arbitration | "binding arbitration," "arbitrator's decision shall be final," "AAA," "FMCS," "selection of arbitrator" |
| Health ins. | "health plan," "premium contribution," "employer shall pay [X]%," "PPO," "HMO," "deductible," "copay" |
| Duration | "shall be effective," "shall remain in force," "expire on," "automatically renew," "evergreen" |

---

## PART 3: LangExtract Integration Plan

LangExtract is a Python library by Google (Apache 2.0 license, GitHub: google/langextract) that extracts structured information from unstructured text using AI models. Its key feature is **precise source grounding** — every extraction maps back to its exact character position in the original text.

### How LangExtract works:

1. **You define "extraction classes"** — the provision types from Part 2 above
2. **You provide a few examples** ("few-shot examples") — 3-5 real examples of each provision type from actual contracts
3. **It chunks long documents** — contracts can be 50-300 pages, so LangExtract breaks them into pieces, processes each, and merges results
4. **It runs multiple passes** — catching things missed on the first read
5. **Every extraction includes source grounding** — exact character offsets back to source text
6. **Output is structured JSONL** — each extraction is a clean record with content, type, confidence, and source location

### What I need you to design:

**A. Few-shot example specifications**

Using the taxonomy in Part 2 and the real contracts you examined in Part 1, describe what ideal few-shot examples should look like for EACH extraction class. You don't need to write the actual examples yet, but describe:

- What a "perfect" example of this provision type looks like
- What a "tricky" example looks like (edge cases the AI might struggle with)
- What a "negative" example looks like (text that LOOKS like this type but isn't)
- How many examples you'd recommend (minimum 3; complex types may need 5-8)
- Where in the sources from Part 1 you'd find the best training examples

**B. Source grounding citation design**

When a user sees an extracted provision, they need to trace it back to the exact source. Design the citation schema:

- Source contract identifier (which contract)
- Page number(s) in the original PDF
- Section/Article reference (e.g., "Article 12, Section 3")
- Character offsets in the extracted text (LangExtract provides these)
- Confidence score
- Extraction model and version used
- Date of extraction
- Modal verb classification (shall/may/shall not — per Arold et al.)

**C. Document quality classification system**

Before running LangExtract on a contract, the system needs to know what it's working with:

- How to detect if a PDF is native digital text vs. scanned images
- How to handle mixed documents (some pages scanned, some digital)
- How to detect contract structure quality (well-organized with clear headings vs. wall of text)
- How to estimate processing cost before committing resources
- Recommended OCR strategy: PyMuPDF for digital PDFs (free), Mistral OCR for scanned (~$1/1,000 pages), IBM Docling for tables (97.9% accuracy, free self-hosted)

**D. Extraction class priority mapping**

Using the taxonomy's complexity ratings and prevalence data, recommend the build order for LangExtract extraction classes:

| Priority | Criteria |
|----------|----------|
| Build First | 🟢 Simple + high prevalence + high organizer value |
| Build Next | 🟡 Medium + high prevalence |
| Build Later | 🔴 Complex or low prevalence |
| Build When Ready | Emerging provisions, sector-specific |

Map each of the ~60 provision types from Part 2 into one of these priority tiers.

---

## PART 4: Processing Pipeline Design

Design the end-to-end flow from "we found a contract on a website" to "it's searchable in our database with every clause tagged and citable."

### Pipeline stages:

1. **Discovery & Download**
   - How does a contract get from a source website into our system?
   - What metadata do we capture at download time?
   - How do we avoid downloading duplicates?
   - How do we track provenance (which source, when downloaded, what URL)?

2. **Document Assessment**
   - Is this actually a CBA? (some sites include MOUs, arbitration awards, or non-CBA documents)
   - Format classification: Digital PDF, scanned PDF, DOCX, HTML
   - Quality: Readable? Corrupted? Password-protected?
   - Structure: Well-organized with headings? Or wall of text?

3. **Text Extraction**
   - Digital PDFs → PyMuPDF (free, instant)
   - Scanned PDFs → Mistral OCR (~$1/1,000 pages)
   - Tables (wage schedules, benefit tables) → IBM Docling (97.9% accuracy, free self-hosted)
   - Output: Normalized text with page references preserved

4. **LangExtract Clause Extraction**
   - Chunking strategy (respect article/section boundaries)
   - Multi-pass extraction for higher recall
   - Confidence scoring on each extraction
   - Source grounding preservation
   - Modal verb classification per Arold et al.

5. **Quality Control**
   - High-confidence extractions (>0.85) auto-approved with 10% spot-check
   - Low-confidence flagged for review
   - Cross-validation: dates make sense? wage rates plausible?
   - Contracts spanning multiple PDFs or with amendments

6. **Storage & Search**
   - PostgreSQL with full-text search (GIN indexes)
   - Searchable by provision type, geography, industry, union, date
   - Future: vector embeddings (pgvector + voyage-law-2) for "find similar clauses"

---

## PART 5: Cost Estimation

Based on your source research, estimate:

1. **Total contracts available** across all sources (realistic, verified count)
2. **Estimated total pages** (based on average contract length from sample inspections)
3. **Cost to process** at three scales:
   - Pilot (500 contracts)
   - Medium (5,000 contracts)
   - Full (25,000 contracts)
4. **Cost breakdown by stage**: OCR, LangExtract/LLM API calls, storage, compute
5. **Monthly ongoing costs** for new contracts and reprocessing

---

## PART 6: Priority Sequencing

Based on everything you've found, recommend:

1. **Which 3 sources to start with** and why (volume, quality, accessibility, organizer relevance)
2. **Which 5 extraction classes to build first** and why (frequency, organizer value, extraction difficulty)
3. **What the "minimum viable contract database" looks like** — smallest version genuinely useful to an organizer
4. **Key risks and unknowns** that could derail the project
5. **What you couldn't verify** and what follow-up research is needed

---

## PART 7: Reference Materials

### Existing classification systems to check against
- **BLS/OLMS Clause Coding System** — Historical BLS taxonomy for CBA provisions
- **WageIndicator CBA Coding Scheme** — 12 major categories with dozens of sub-categories, 3,600+ coded CBAs
- **CUAD dataset** — 510 contracts, 13,101 labeled clauses, 41 categories (commercial, not CBA, but overlapping)
- **Arold, Ash, MacLeod, Naidu (NBER 2025)** — Modal verb dependency parsing for legal force assessment
- **UC Berkeley Labor Center "Negotiating Tech"** — 6 categories of technology provisions across 175+ agreements
- **Harvey AI Contract Intelligence Benchmark (Nov 2025)** — Out-of-box LLMs get 65-70% accuracy; specialized systems much higher
- **Savelka (2023)** — GPT-4 zero-shot on CUAD clauses achieved F1=0.86

### Key tools
- **LangExtract**: github.com/google/langextract — few-shot structured extraction with source grounding
- **PyMuPDF**: Free PDF text extraction for digital PDFs
- **Docling (IBM)**: 97.9% table extraction accuracy, handles PDF/DOCX/HTML
- **Mistral OCR**: ~$1/1,000 pages for scanned document OCR
- **voyage-law-2**: Legal embedding model, outperforms OpenAI by 6-10% on legal retrieval
- **labordata/opdr**: GitHub project for OLMS Public Disclosure Room data
- **ContractNLI**: Hypothesis-based contract provision classification
- **LexNLP (LexPredict)**: Entity extraction for dates, durations, monetary amounts, party names
- **Legal-BERT / Contracts-BERT**: Pre-trained on 12GB legal text including 76K contracts

### Existing platform infrastructure
- PostgreSQL database (olms_multiyear) with 207+ tables
- FastAPI backend with 38+ endpoints
- Crawl4AI already integrated for web scraping
- Full-text search via PostgreSQL GIN indexes
- pgvector extension available for semantic search

---

## OUTPUT FORMAT

Organize your research as a single comprehensive document with sections matching the parts above. Use tables for source comparisons.

**For Part 1 (Sources):** Mark what you verified firsthand vs. secondary sources. Include URLs, dates checked, sample access results, and discrepancies from reported numbers.

**For Part 2 (Taxonomy validation):** Note any provisions you found in real contracts that are missing, any described here that don't match reality, and any prevalence/complexity estimates that seem wrong.

**For Part 3 (LangExtract):** Be specific enough that a developer can start building extraction classes immediately.

Accuracy matters more than comprehensiveness. Say "I couldn't verify this" rather than reporting unverified numbers.

---

*End of unified research task. Generated February 2026 for the Labor Relations Research Platform.*
