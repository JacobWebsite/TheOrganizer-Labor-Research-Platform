# American Collective Bargaining Agreement (CBA) Provision Taxonomy

## A Complete Framework for Automated Contract Extraction

*Created February 2026 for the Labor Relations Research Platform*
*Purpose: Define every provision type that LangExtract and Gemini should identify, classify, and extract when reading union contracts*

---

## How This Document Works

Every union contract (CBA) is built from a set of standard building blocks — provisions that address wages, rights, procedures, and working conditions. Not every contract has every provision, but there's a recognizable pattern to how they're organized and what language they use.

This document maps out **every major provision type** that appears in American CBAs. For each one, it explains:

- **What it is** in plain English
- **How to find it** — the headings, keywords, and language patterns that signal this provision
- **What to extract** — the specific structured data points an AI system should pull out
- **How common it is** — whether it appears in nearly all contracts or only certain sectors
- **How complex it is** — whether extraction is straightforward or requires sophisticated logic
- **Sector variations** — how this provision differs between public/private sector, healthcare, construction, education, etc.

Complexity ratings use a simple scale:
- 🟢 **Simple** — Usually a sentence, paragraph, or short list. Contains clear, extractable data points (dates, dollar amounts, yes/no). Expected AI accuracy: 85-95%.
- 🟡 **Medium** — A section or article with multiple related provisions. Requires understanding relationships between sub-provisions. Expected AI accuracy: 75-85%.
- 🔴 **Complex** — Multi-page provisions with nested rules, exceptions, and cross-references. Requires multi-pass extraction and may need human review. Expected AI accuracy: 60-75%.

---

## PART 1: HOW CBAs ARE STRUCTURED

Before extracting individual provisions, the system needs to understand how contracts are organized. This section describes the "container" that holds everything else.

### 1.1 Typical CBA Organization

Most American CBAs follow a recognizable pattern:

**Standard article numbering:** Contracts are divided into numbered "Articles" (sometimes called "Sections" or "Chapters"), each covering a distinct topic. A typical 50-page contract might have 25-40 articles. Common ordering:

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

This ordering isn't universal — some contracts put wages first, some bury grievance procedures in the middle — but the AI should recognize that article order varies while topics remain consistent.

**What to extract from the structure itself:**
- Total number of articles
- Article titles and numbering scheme
- Presence or absence of a table of contents
- Whether the contract includes appendices, side letters, or memoranda of understanding (MOUs)
- Total page count
- Whether the contract covers a single employer or multiple employers (multi-employer agreement)

### 1.2 Preamble / Purpose Statement

**What it is:** The opening paragraph(s) of the contract, establishing the intent of the agreement and naming the parties.

**How to find it:** Almost always the very first text after the title. Look for language like "This Agreement is entered into by and between..." or "The purpose of this Agreement is to promote harmonious relations..."

**What to extract:**
- Full legal name of the employer
- Full legal name of the union (international/national)
- Local union number or chapter designation
- AFL-CIO affiliation if stated
- Date the agreement was executed
- General statement of purpose (if present)

**How common:** Virtually every CBA has this. Prevalence: ~99%.

**Complexity:** 🟢 Simple

---

## PART 2: CORE ECONOMIC PROVISIONS

These are the "money" provisions — what workers get paid and what benefits they receive. These are typically the most important provisions for organizers because they're what workers care about most during organizing conversations.

### 2.1 Wage Rates and Wage Schedules

**What it is:** The base pay rates for covered employees. This can range from a single hourly rate for all workers to complex multi-page tables with different rates for dozens of job classifications, each with multiple steps based on years of service.

**How to find it:** Article titles like "Wages," "Compensation," "Pay Rates," "Salary Schedule," "Wage Scale." Often appears as a table or appendix rather than in the body text.

**What to extract:**
- Base hourly rate(s) or annual salary/salaries
- Job classification titles and their corresponding rates
- Step/longevity increases (pay raises based on years of service)
- Effective dates for each rate (contracts often have different rates for Year 1, Year 2, Year 3)
- Whether rates are hourly, daily, weekly, biweekly, monthly, or annual
- Minimum and maximum rates if a range is specified
- Any lump-sum payments in lieu of base rate increases

**How common:** Universal — every CBA addresses compensation in some form. However, the format varies enormously.

**Complexity:** 🔴 Complex — Wage schedules are often the most structurally complex part of a contract. A healthcare contract might have 200+ job titles each with 15 steps. Construction contracts specify rates by trade and sometimes by project type. The AI needs to handle tables, appendices, and cross-references.

**Sector variations:**
- *Construction:* Rates specified by trade (electrician, plumber, laborer) with separate journeyman and apprentice scales
- *Healthcare:* Dozens to hundreds of job classifications with step progressions
- *Education:* Salary schedules based on degree level (BA, MA, PhD) crossed with years of experience
- *Public sector:* Often tied to civil service grade/step systems
- *Manufacturing:* May use job classification systems with labor grades

### 2.2 Shift Differentials and Premium Pay

**What it is:** Extra pay for working less desirable shifts (nights, weekends) or under special conditions (hazardous duty, bilingual requirements, lead worker responsibilities).

**How to find it:** Often within the Wages article, or in a separate article titled "Premium Pay," "Shift Differential," or "Special Pay." Look for language like "Employees assigned to the second shift shall receive..." or "A premium of $X per hour shall be paid for..."

**What to extract:**
- Dollar amount or percentage for each differential
- Which shifts or conditions trigger the premium
- Whether the premium is added to the base rate or paid separately
- Any eligibility requirements

**How common:** Very common in 24/7 operations (healthcare, manufacturing, public safety). Less common in standard Monday-Friday workplaces. Prevalence: ~60-70%.

**Complexity:** 🟡 Medium

### 2.3 Overtime Provisions

**What it is:** Rules governing when overtime kicks in, how it's calculated, and how overtime work is distributed among employees.

**How to find it:** Article titled "Overtime," or within "Hours of Work" or "Compensation." Look for "time and one-half," "double time," "overtime shall be distributed..."

**What to extract:**
- When overtime begins (after 8 hours/day? after 40 hours/week? both?)
- Overtime rate (typically 1.5x, but sometimes 2x for certain conditions)
- Double-time triggers (7th consecutive day, holidays, etc.)
- How overtime is distributed (by seniority? rotation? volunteers first?)
- Whether overtime can be mandatory ("compulsory overtime" or "mandatory overtime")
- Pyramiding rules (whether overtime premiums can stack)
- Callback/call-in pay minimums (guaranteed minimum hours if called back to work)

**How common:** Nearly universal in hourly-worker contracts. Less relevant for salaried/exempt positions. Prevalence: ~85-90%.

**Complexity:** 🟡 Medium

### 2.4 Holiday Pay and Holiday Schedule

**What it is:** Which days are recognized as paid holidays, and what premium pay applies for employees who work on holidays.

**How to find it:** Article titled "Holidays" or "Holiday Pay." Often includes an enumerated list of specific dates.

**What to extract:**
- List of recognized holidays (specific dates and names)
- Total number of paid holidays per year
- Holiday pay rate (typically 1.5x or 2x base rate for hours worked)
- Whether employees get the holiday off with pay or just the premium for working
- "Floating holiday" provisions (employee chooses the date)
- Eligibility requirements (must work day before and after to qualify)
- Special rules for holidays falling on weekends

**How common:** Nearly universal. Prevalence: ~95%.

**Complexity:** 🟢 Simple — Usually a straightforward list with clear rates.

### 2.5 Vacation / Paid Time Off (PTO)

**What it is:** Paid time away from work that accrues based on length of service. Some contracts use traditional vacation schedules, others use combined PTO banks.

**How to find it:** Article titled "Vacations," "Paid Time Off," "Annual Leave." Look for tables or lists showing accrual rates by years of service.

**What to extract:**
- Accrual schedule (how many days/hours per year at each service milestone)
- Maximum accrual / carryover limits
- When vacation can be taken (scheduling procedures, blackout periods)
- Cash-out provisions (can unused vacation be paid out?)
- How vacation is paid upon termination
- Seniority-based scheduling priority

**How common:** Nearly universal. Prevalence: ~95%.

**Complexity:** 🟡 Medium — The accrual tables can be detailed.

### 2.6 Sick Leave

**What it is:** Paid time off specifically for illness, injury, or medical appointments. Separate from vacation in traditional systems, sometimes combined in PTO systems.

**How to find it:** Article titled "Sick Leave" or "Illness and Injury." May be combined with other leave provisions.

**What to extract:**
- Accrual rate (days or hours per month/year)
- Maximum accumulation
- Whether unused sick leave can be cashed out (at retirement or termination)
- Documentation requirements (when is a doctor's note required?)
- Whether sick leave can be used for family member illness
- Sick leave bank or donation programs

**How common:** Very common, especially in public sector. Prevalence: ~80-90%.

**Complexity:** 🟢 Simple

### 2.7 Personal Leave and Bereavement Leave

**What it is:** Paid days off for personal business (personal days) and for family deaths (bereavement/funeral leave).

**How to find it:** May be its own article or bundled into a general "Leaves of Absence" article. Look for "personal day," "bereavement," "funeral leave."

**What to extract:**
- Number of personal days per year
- Number of bereavement days
- Which family relationships qualify for bereavement (spouse, parent, sibling, in-law, etc.)
- Whether travel days are included for distant funerals
- Whether unused personal days roll over or are forfeited

**How common:** Very common. Prevalence: ~75-85%.

**Complexity:** 🟢 Simple

### 2.8 Family and Medical Leave (FMLA-Related)

**What it is:** Provisions related to extended leave for serious health conditions, childbirth, adoption, or family caregiving. May go beyond the federal FMLA minimums.

**How to find it:** Article titled "Family and Medical Leave," "FMLA," "Parental Leave," or within a broader "Leaves of Absence" article.

**What to extract:**
- Whether the contract merely references FMLA or provides enhanced benefits beyond it
- Duration of leave available
- Whether any portion is paid (FMLA itself is unpaid; contracts may add paid weeks)
- Job protection guarantees beyond FMLA requirements
- Parental leave specific provisions (maternity, paternity, adoption)
- Whether employees must use accrued PTO/sick time concurrently

**How common:** Increasingly common, especially in public sector and healthcare. Prevalence: ~50-70%.

**Complexity:** 🟡 Medium

### 2.9 Health Insurance and Medical Benefits

**What it is:** Employer-provided health insurance coverage — often the most expensive and most-fought-over economic provision in a contract.

**How to find it:** Article titled "Insurance," "Health Benefits," "Medical Benefits," "Health and Welfare." Sometimes detailed in an appendix or summary plan description rather than the contract body itself.

**What to extract:**
- Types of plans offered (HMO, PPO, high-deductible, etc.)
- Employer vs. employee premium cost sharing (dollar amounts or percentages)
- Premium shares for different coverage tiers (employee-only, employee+spouse, family)
- Deductible amounts
- Copay amounts for office visits, prescriptions, emergency room
- Out-of-pocket maximums
- Whether coverage begins immediately or after a waiting period
- Retiree health coverage provisions
- Opt-out payments (cash in lieu of coverage)
- Health care spending accounts (FSA, HSA)
- Any reopener triggered by cost increases exceeding a threshold

**How common:** Nearly universal in contracts for full-time workers. Prevalence: ~90%.

**Complexity:** 🔴 Complex — Health insurance provisions can be extremely detailed or extremely vague (sometimes the contract just says "the employer shall continue to provide health insurance" with details in a separate plan document).

### 2.10 Dental and Vision Benefits

**What it is:** Separate coverage for dental care and eye care, often provided as standalone plans.

**How to find it:** Usually within the Insurance/Benefits article, sometimes in a sub-section.

**What to extract:**
- Whether dental is provided (yes/no)
- Whether vision is provided (yes/no)
- Coverage levels and employer cost share
- Any orthodontia coverage
- Vision allowances for glasses/contacts

**How common:** Common but not universal. Prevalence: ~60-75%.

**Complexity:** 🟢 Simple

### 2.11 Pension and Retirement Benefits

**What it is:** Employer contributions to retirement plans. The key distinction is between "defined benefit" plans (traditional pension — employer guarantees a specific monthly payment in retirement based on a formula) and "defined contribution" plans (401k/403b — employer contributes to an account, but the retirement amount depends on investment performance).

**How to find it:** Article titled "Pension," "Retirement," "401(k)," "Defined Benefit Plan," or within the general benefits section.

**What to extract:**
- Plan type: defined benefit, defined contribution, or both
- For defined benefit: benefit formula (e.g., 2% of final average salary per year of service)
- For defined contribution: employer contribution rate (percentage of pay or flat dollar amount)
- Employee contribution requirements
- Vesting schedule (how long before employer contributions are fully owned by the employee)
- Retirement eligibility (age and service requirements)
- Whether the plan is single-employer or multi-employer (Taft-Hartley fund)
- Early retirement provisions

**How common:** Very common, though the type varies significantly. Prevalence: ~70-80%.

**Complexity:** 🟡 Medium — Defined benefit formulas can be complex.

### 2.12 Life Insurance and Disability Benefits

**What it is:** Employer-provided life insurance coverage and short-term/long-term disability insurance.

**How to find it:** Within the Insurance/Benefits article, sometimes in its own sub-section.

**What to extract:**
- Life insurance coverage amount (flat dollar or multiple of salary)
- Whether accidental death & dismemberment (AD&D) is included
- Short-term disability: duration, percentage of pay covered, waiting period
- Long-term disability: duration, percentage of pay, definition of disability
- Whether these are fully employer-paid or have employee cost sharing

**How common:** Common in larger bargaining units. Prevalence: ~50-65%.

**Complexity:** 🟢 Simple

### 2.13 Wage Reopener Clause

**What it is:** A provision allowing either party to reopen negotiations on wages (and sometimes benefits) during the life of a multi-year contract, usually at a specified date.

**How to find it:** Often within the Wages article or the Duration article. Look for "reopener," "wage review," "reopen negotiations."

**What to extract:**
- When the reopener can be triggered (specific date or anniversary)
- What subjects can be reopened (wages only? wages and benefits? all economic terms?)
- Notice requirements for triggering the reopener
- Whether there's a strike/lockout right during a reopener

**How common:** Moderately common, especially in longer-term contracts (3+ years). Prevalence: ~25-40%.

**Complexity:** 🟢 Simple

### 2.14 Other Economic Provisions

These appear less frequently but are important when present:

**Severance pay:** Lump sum or continued pay upon layoff. Extract: formula (weeks per year of service), eligibility, caps.

**Tuition reimbursement / education benefits:** Employer pays for courses or degrees. Extract: annual dollar cap, eligible programs, grade requirements, service commitment.

**Uniform and tool allowances:** Employer provides or reimburses work clothing/tools. Extract: dollar amount, frequency, what's covered.

**Travel and mileage reimbursement:** Compensation for work-related travel. Extract: per-mile rate, whether it matches IRS rate, meal per diems.

**Signing/ratification bonus:** One-time payment upon contract ratification. Extract: dollar amount, who's eligible, payment date.

**Jury duty pay:** Continued pay while serving on a jury. Extract: duration, whether full pay or difference between jury pay and regular pay.

**Military leave:** Provisions beyond USERRA requirements. Extract: duration of supplemental pay, job protections.

**Prevalence:** Each of these individually: 20-50%. **Complexity:** 🟢 Simple for each.

---

## PART 3: WORKPLACE RULES AND CONDITIONS

These provisions govern the day-to-day experience of work — when you work, how you work, and what protections exist beyond pay.

### 3.1 Hours of Work and Scheduling

**What it is:** Defines the standard workday and workweek, when shifts start and end, and how schedules are set and changed.

**How to find it:** Article titled "Hours of Work," "Work Schedules," "Working Conditions."

**What to extract:**
- Standard workday length (8 hours is most common)
- Standard workweek (40 hours, Monday-Friday is most common)
- Shift start and end times
- How far in advance schedules must be posted
- How schedule changes are handled (notice requirements)
- Flexible scheduling provisions
- Split shift rules
- Reporting/show-up pay (minimum guaranteed pay if called in but sent home)

**How common:** Nearly universal. Prevalence: ~90-95%.

**Complexity:** 🟡 Medium

**Sector variations:**
- *Healthcare:* Complex rotating schedules, 12-hour shifts, weekend rotation requirements
- *Public safety:* 24-hour shift cycles, Kelly schedules, platoon systems
- *Retail/hospitality:* Predictive scheduling requirements, minimum hours guarantees
- *Education:* School calendar-based scheduling, preparation periods

### 3.2 Safety and Health

**What it is:** Provisions requiring the employer to maintain safe working conditions, often going beyond federal OSHA minimums. May include joint safety committees, right to refuse unsafe work, and specific safety equipment requirements.

**How to find it:** Article titled "Safety and Health," "Health and Safety," "Working Conditions." Sometimes bundled with other workplace conditions.

**What to extract:**
- Whether a joint labor-management safety committee exists
- Frequency of safety committee meetings
- Right to refuse unsafe work (and any protections for doing so)
- Employer obligation to provide safety equipment/PPE
- Specific safety standards beyond OSHA (industry-specific)
- Accident reporting procedures
- Right to accompany OSHA inspectors
- Hazard pay provisions (may cross-reference with premium pay)

**How common:** Very common in manufacturing, construction, healthcare. Less detailed in office/clerical settings. Prevalence: ~65-80%.

**Complexity:** 🟡 Medium

### 3.3 Drug and Alcohol Testing

**What it is:** Rules governing when and how employees can be tested for drugs and alcohol, what happens if they test positive, and what protections exist.

**How to find it:** May be its own article or within "Working Conditions" or "Rules of Conduct." Sometimes in an appendix.

**What to extract:**
- Types of testing allowed (pre-employment, random, reasonable suspicion, post-accident)
- Substances tested for
- Consequences of a positive test (immediate termination vs. rehabilitation opportunity)
- Employee assistance program (EAP) referral provisions
- Chain of custody and confirmation testing requirements
- Whether DOT testing regulations apply (transportation sector)

**How common:** Increasingly common, especially in safety-sensitive industries. Prevalence: ~45-60%.

**Complexity:** 🟡 Medium

### 3.4 Technology, Electronic Monitoring, and Surveillance

**What it is:** Rules about employer use of cameras, GPS tracking, email monitoring, keystroke logging, and other electronic surveillance of employees. Also covers use of personal devices for work.

**How to find it:** This is a newer provision — may be titled "Technology," "Electronic Monitoring," "Privacy," "Use of Electronics," or may appear within "Working Conditions." In older contracts, may not exist at all.

**What to extract:**
- Whether employer must notify employees before monitoring
- Types of monitoring addressed (video, GPS, email, phone, computer activity)
- Restrictions on using monitoring data for discipline
- Personal device policies (BYOD)
- Social media policies
- AI and algorithmic management provisions (very new — emerging in contracts since ~2023)

**How common:** Growing rapidly but still uncommon in older contracts. Prevalence: ~20-35% overall, higher in newer contracts.

**Complexity:** 🟡 Medium

**Important note for extraction:** This is one of the fastest-evolving areas of contract language. The UC Berkeley Labor Center's "Negotiating Tech" project identified 6 categories of technology provisions across 175+ agreements, and AI/algorithmic management provisions are appearing in contracts for the first time. The extraction system should flag any technology-related language for special attention.

### 3.5 Remote Work / Telework

**What it is:** Provisions governing whether and how employees can work from home or other remote locations.

**How to find it:** Article titled "Telework," "Remote Work," "Work from Home," or within "Working Conditions." Very rare before 2020; became widespread during and after the COVID-19 pandemic.

**What to extract:**
- Eligibility criteria for remote work
- Whether remote work is a right or at management discretion
- Equipment/technology provisions for remote workers
- Expectations around availability and responsiveness
- Home office stipends or reimbursements
- Return-to-office provisions

**How common:** Growing rapidly since 2020. Prevalence: ~15-30% (much higher in newer contracts for office-based workers).

**Complexity:** 🟢 Simple

### 3.6 Workplace Violence Prevention

**What it is:** Policies addressing threats, intimidation, and physical violence in the workplace, including protocols for reporting and responding.

**How to find it:** Within "Safety and Health," "Working Conditions," or occasionally its own article. More common in healthcare and public-facing workplaces.

**What to extract:**
- Definition of workplace violence used
- Reporting procedures
- Employer response obligations
- Employee protections for reporting
- Training requirements

**How common:** More common in healthcare, social services, and public sector. Prevalence: ~25-40%.

**Complexity:** 🟢 Simple

---

## PART 4: UNION RIGHTS AND SECURITY

These provisions define the union's institutional standing — its right to exist, collect dues, access the workplace, and represent members.

### 4.1 Recognition Clause

**What it is:** The foundational clause identifying the union as the exclusive bargaining representative and defining exactly which employees are covered ("bargaining unit") and which are excluded (supervisors, managers, confidential employees).

**How to find it:** Almost always Article 1 or Article 2. Titled "Recognition" or "Recognition and Scope." Look for "The Employer hereby recognizes the Union as the sole and exclusive bargaining representative..."

**What to extract:**
- Full name of the recognized union
- Exact description of the bargaining unit (who's in)
- Excluded categories (who's out — supervisors, temps, etc.)
- Whether the unit is certified by the NLRB (includes case number) or voluntarily recognized
- Geographic scope (single facility, multiple facilities, statewide, etc.)
- Job titles or classifications included

**How common:** Universal — this is the legal foundation of the entire contract. Prevalence: ~100%.

**Complexity:** 🟡 Medium — The bargaining unit description can be very specific and sometimes complex.

### 4.2 Union Security Clause

**What it is:** Determines whether employees must join or financially support the union as a condition of employment. This is one of the most legally sensitive provisions because it varies dramatically based on state law (right-to-work states prohibit mandatory union membership).

**How to find it:** Article titled "Union Security," "Union Membership," "Agency Shop," or within the Recognition article.

**What to extract:**
- Type of union security:
  - **Union shop:** All employees must join the union after hiring
  - **Agency shop / fair share:** Non-members must pay a fee equivalent to dues
  - **Maintenance of membership:** Members who join must stay members for the contract's duration
  - **Open shop:** No requirement to join or pay (typical in right-to-work states)
- Time period for new employees to join/pay (usually 30-60 days after hire)
- Any religious objection provisions
- Whether the contract acknowledges right-to-work law applicability

**How common:** Present in most contracts, but the TYPE varies based on state law. Prevalence: ~85-90%.

**Complexity:** 🟡 Medium — Legal nuances matter here.

### 4.3 Dues Checkoff

**What it is:** The employer agrees to deduct union dues directly from employee paychecks and remit them to the union. This is the financial lifeblood of the union's operations.

**How to find it:** Usually within "Union Security" or its own short article titled "Dues Checkoff" or "Deduction of Dues."

**What to extract:**
- Whether dues checkoff is provided (almost always yes)
- What is deducted (regular dues, initiation fees, assessments, PAC/COPE contributions)
- Frequency of deductions (per paycheck, monthly)
- Authorization card requirements
- Revocation procedures and windows

**How common:** Nearly universal. Prevalence: ~95%.

**Complexity:** 🟢 Simple

### 4.4 Union Access and Communication

**What it is:** The union's right to access the workplace, use bulletin boards, communicate with members, and conduct union business on employer premises.

**How to find it:** Article titled "Union Rights," "Union Activity," "Union Business," or scattered across multiple provisions.

**What to extract:**
- Union representative access to the workplace (when and with what notice)
- Bulletin board rights (physical and/or electronic)
- Email/intranet access for union communications
- Right to hold meetings on employer property (before/after shifts)
- Right to distribute literature
- Employer obligation to provide meeting space

**How common:** Very common. Prevalence: ~75-85%.

**Complexity:** 🟢 Simple

### 4.5 Union Steward / Release Time

**What it is:** Provisions allowing designated union representatives (stewards) to conduct union business — investigating grievances, attending meetings, representing members in discipline — during work hours without loss of pay.

**How to find it:** Article titled "Union Representatives," "Stewards," "Union Time," or within the Grievance Procedure article.

**What to extract:**
- Number of stewards authorized
- How steward time is compensated (full pay, partial pay, unpaid)
- Hours allocated per week/month for union business
- Whether stewards need supervisor permission to leave their work area
- Release time for contract negotiations
- Release time for union conventions/conferences
- Any paid release time for union officers (full-time union reps on employer's payroll)

**How common:** Very common. Prevalence: ~80-90%.

**Complexity:** 🟡 Medium

### 4.6 Information Rights

**What it is:** The employer's obligation to provide the union with information needed for bargaining and contract administration — employee lists, wage data, disciplinary records, financial information.

**How to find it:** May be its own article or scattered. Look for "information," "provide the union with," "employer shall furnish."

**What to extract:**
- What information the employer must provide (seniority lists, new hire notifications, wage data, etc.)
- How often information must be updated
- Format requirements (electronic vs. paper)
- Timeline for employer response to information requests

**How common:** Moderately common as an explicit provision; the legal obligation exists regardless under NLRA. Prevalence as explicit contract language: ~40-60%.

**Complexity:** 🟢 Simple

### 4.7 No-Strike / No-Lockout Clause

**What it is:** The union agrees not to strike and the employer agrees not to lock out employees for the duration of the contract. This is the quid pro quo for the grievance/arbitration system — instead of striking over disputes, they go to arbitration.

**How to find it:** Its own article titled "No Strike / No Lockout," "Strikes and Lockouts," or "Work Stoppages."

**What to extract:**
- Whether the no-strike pledge is absolute or conditional (some contracts allow strikes over safety issues or if the employer violates arbitration awards)
- Whether sympathy strikes are prohibited (honoring another union's picket line)
- Consequences for violating the no-strike clause
- Whether the employer waives the right to lockout
- Any exceptions (unfair labor practice strikes may be excluded)

**How common:** Nearly universal in private sector contracts. Less common in public sector where strikes may already be illegal by state law. Prevalence: ~85-95%.

**Complexity:** 🟢 Simple

### 4.8 Successor and Assigns Clause

**What it is:** Requires the employer to make any buyer, merger partner, or successor company honor the existing union contract. This protects workers when companies are sold.

**How to find it:** May be its own short article or within "Duration" or "General Provisions." Look for "successor," "assigns," "sale of business," "merger."

**What to extract:**
- Whether a successorship provision exists (yes/no)
- Whether the employer must require the buyer to assume the contract
- Whether the employer must notify the union before a sale
- Whether the provision covers partial sales (selling one facility)

**How common:** Moderately common. Prevalence: ~30-50%.

**Complexity:** 🟢 Simple

---

## PART 5: MANAGEMENT RIGHTS

### 5.1 Management Rights Clause

**What it is:** Explicitly reserves certain decisions to management's sole discretion — things the employer can do without bargaining with the union. This is one of the most important clauses for understanding the overall power balance in the contract.

**How to find it:** Almost always its own article titled "Management Rights" or "Employer Rights." Typically appears early in the contract (Articles 3-5).

**What to extract:**
- Whether the clause exists (yes/no — its absence is significant)
- Whether it's a "broad" or "narrow" rights clause:
  - **Broad/residual rights:** "Management retains all rights except as specifically limited by this Agreement" — gives management wide latitude
  - **Narrow/specific rights:** Lists specific management rights one by one — limits management more
- Specific rights enumerated (hire, fire, direct workforce, determine methods of operation, set production standards, etc.)
- Whether any reserved rights are subject to the grievance procedure
- Any explicit limitations on management rights within the clause itself

**How common:** Very common. Prevalence: ~80-90%.

**Complexity:** 🟡 Medium — The distinction between broad and narrow rights clauses matters significantly for legal interpretation.

### 5.2 Subcontracting and Outsourcing

**What it is:** Restrictions on the employer's ability to send bargaining unit work to outside contractors or to non-union operations.

**How to find it:** May be its own article or within "Management Rights." Look for "subcontracting," "contracting out," "outsourcing," "work preservation."

**What to extract:**
- Whether any restriction exists (yes/no)
- Type of restriction:
  - Complete prohibition
  - Prohibition if it results in layoffs of bargaining unit members
  - Requirement to notify the union before subcontracting
  - Requirement to bargain over the decision to subcontract
  - Requirement that subcontractors pay prevailing wages or union-scale wages
- Right to information about subcontracting decisions
- Exceptions (emergency work, specialized work beyond employee capability)

**How common:** Common in manufacturing, construction, and public sector. Prevalence: ~40-55%.

**Complexity:** 🟡 Medium

### 5.3 Technological Change

**What it is:** Provisions addressing what happens when the employer introduces new technology that changes or eliminates jobs. May include retraining obligations, advance notice requirements, or bargaining rights over the impact of technological change.

**How to find it:** May be its own article, within "Management Rights," or within newer "Technology" provisions. Look for "technological change," "automation," "new equipment," "new methods."

**What to extract:**
- Whether the employer must notify the union before introducing new technology
- Advance notice period required
- Obligation to retrain affected employees
- Obligation to bargain over the impact (even if not required to bargain over the decision itself)
- Whether affected employees have transfer rights
- Any protections against job loss due to technology
- AI and algorithmic decision-making provisions (very new, emerging since ~2023)

**How common:** Less common than many other provisions but growing. Prevalence: ~20-35%.

**Complexity:** 🟡 Medium

### 5.4 Plant Closure / Relocation

**What it is:** Provisions requiring advance notice and/or bargaining before an employer closes a facility or relocates operations. May provide severance, transfer rights, or other protections.

**How to find it:** May be its own article, within "Management Rights," or within "Job Security." Look for "plant closure," "relocation," "shutdown," "transfer of operations."

**What to extract:**
- Advance notice requirements (beyond WARN Act minimums)
- Obligation to bargain over closure/relocation decisions
- Transfer rights to other employer facilities
- Severance pay provisions triggered by closure
- Retraining or placement assistance obligations
- Community impact provisions

**How common:** Less common but significant when present. Prevalence: ~15-30%.

**Complexity:** 🟡 Medium

---

## PART 6: EMPLOYEE RIGHTS AND PROTECTIONS

### 6.1 Just Cause Standard

**What it is:** The employer can only discipline or fire employees for "just cause" — a fair, documented reason — rather than "at will." This is widely considered the single most important protection a union contract provides. Without a union contract, most American workers are "at will," meaning they can be fired for any reason or no reason.

**How to find it:** Article titled "Discipline and Discharge," "Corrective Action," "Just Cause." The key phrase is "No employee shall be disciplined or discharged except for just cause."

**What to extract:**
- Whether "just cause" standard exists (yes/no — almost always yes)
- Exact language used ("just cause," "proper cause," "cause," "good cause" — these have slightly different legal meanings)
- Whether there's a specific definition of what constitutes just cause
- Whether the standard applies to all discipline or only to termination
- Probationary employee exclusion (just cause often doesn't apply during probation)

**How common:** Nearly universal. This is the cornerstone of union representation. Prevalence: ~95%.

**Complexity:** 🟢 Simple — The provision itself is usually short. Its interpretation is complex, but extraction is straightforward.

### 6.2 Progressive Discipline

**What it is:** A structured sequence of escalating disciplinary steps — typically verbal warning → written warning → suspension → termination — giving employees a chance to correct behavior before facing the most severe consequences.

**How to find it:** Within "Discipline and Discharge" article. Look for "progressive discipline," "corrective action steps," or enumerated discipline sequences.

**What to extract:**
- Number of steps in the discipline procedure
- What each step consists of (verbal, written, suspension, termination)
- Whether steps must be followed in order or can be skipped for serious offenses
- How long disciplinary records remain in the employee's file
- Whether the employee has the right to have the union present during disciplinary meetings (Weingarten rights — may be explicit or implicit)
- Whether "last chance agreements" are referenced

**How common:** Very common. Prevalence: ~70-80%.

**Complexity:** 🟡 Medium

### 6.3 Seniority

**What it is:** The system that gives employees with longer service priority in job bidding, shift selection, vacation scheduling, layoff order, recall, and other workplace decisions. Seniority is one of the fundamental organizing principles of unionized workplaces.

**How to find it:** Usually its own article titled "Seniority." May be one of the longest articles in the contract.

**What to extract:**
- How seniority is defined (date of hire? date of entry into the bargaining unit? classification seniority vs. plant-wide seniority?)
- Accrual rules (does seniority accrue during leaves of absence? layoff?)
- Where seniority applies:
  - Job bidding/promotion
  - Shift preference
  - Vacation scheduling
  - Overtime distribution
  - Layoff order
  - Recall order
  - Transfer rights
- Loss of seniority events (resignation, termination, failure to return from leave, etc.)
- Whether seniority lists are posted and how often
- "Super seniority" for union stewards (protection from layoff to ensure union representation)
- Probationary period length before seniority rights begin

**How common:** Nearly universal. Prevalence: ~90-95%.

**Complexity:** 🔴 Complex — Seniority provisions are often among the most detailed and nuanced in the entire contract, with different rules applying to different situations.

### 6.4 Layoff and Recall

**What it is:** Procedures governing how layoffs are conducted (who goes first), how long laid-off workers retain recall rights, and in what order they're brought back.

**How to find it:** May be its own article or within "Seniority." Look for "layoff," "reduction in force," "recall," "bumping."

**What to extract:**
- Order of layoff (inverse seniority — least senior go first — is most common)
- Bumping rights (can a senior employee "bump" a less-senior employee in another classification?)
- Scope of bumping (plant-wide? department-only? classification-only?)
- Recall order (most senior laid-off employee called back first)
- Recall period (how long recall rights last — typically 1-3 years)
- Notice requirements before layoff
- Severance provisions triggered by layoff
- Obligation to offer available work before laying off

**How common:** Very common. Prevalence: ~75-85%.

**Complexity:** 🔴 Complex — Bumping rights in particular can create elaborate chains of displacement.

### 6.5 Job Posting and Bidding

**What it is:** When a job opens up, the employer must post it and allow employees to bid (apply) for it, with selection based on seniority, qualifications, or a combination.

**How to find it:** Article titled "Job Posting," "Promotions and Transfers," "Vacancies," or within "Seniority."

**What to extract:**
- Whether job posting is required
- How long postings must remain up
- What information must be in the posting (job title, pay rate, qualifications, shift, location)
- Selection criteria:
  - Pure seniority ("most senior qualified bidder gets the job")
  - Qualifications first, seniority as tiebreaker ("among equally qualified, most senior gets the job")
  - Hybrid formulas
- Trial period for the new position
- Right to return to former position if the new job doesn't work out

**How common:** Very common. Prevalence: ~70-80%.

**Complexity:** 🟡 Medium

### 6.6 Non-Discrimination

**What it is:** Prohibits discrimination based on protected characteristics. May simply mirror federal/state law or may add additional protected categories (such as sexual orientation or gender identity in jurisdictions where these weren't yet legally protected, or union activity as an explicit protected category).

**How to find it:** Often its own short article titled "Non-Discrimination" or "Equal Employment Opportunity." May appear early in the contract.

**What to extract:**
- Protected categories listed (race, sex, age, religion, disability, national origin, sexual orientation, gender identity, veteran status, union activity, political affiliation, etc.)
- Whether the provision goes beyond existing law in the protected categories it lists
- Whether discrimination claims can be grieved under the contract's grievance procedure or must go to external agencies (EEOC, state agency)
- Whether there are specific accommodations provisions for disabilities

**How common:** Very common. Prevalence: ~80-90%.

**Complexity:** 🟢 Simple

### 6.7 Probationary Period

**What it is:** A defined initial employment period during which new hires have limited contractual protections — typically no seniority, limited grievance rights, and can be terminated more easily.

**How to find it:** Within "Seniority," "New Employees," or "Probationary Employees."

**What to extract:**
- Length of probationary period (commonly 30, 60, 90, 120, or 180 days)
- Which contract provisions apply during probation and which don't
- Whether probation can be extended
- When seniority begins (retroactive to hire date after completing probation?)
- Whether probationary employees can grieve a termination

**How common:** Very common. Prevalence: ~80-90%.

**Complexity:** 🟢 Simple

### 6.8 Personnel File Access

**What it is:** The employee's right to review and copy the contents of their personnel file, and to respond to or challenge materials in it.

**How to find it:** Within "Employee Rights," "Personnel Records," or "Discipline."

**What to extract:**
- Right to inspect personnel file (yes/no)
- Frequency allowed (once per year? anytime upon request?)
- Right to copy documents
- Right to submit a written response to any document in the file
- Restrictions on what can be in the file
- Requirements to remove old disciplinary records after a period of time

**How common:** Moderately common. Prevalence: ~40-55%.

**Complexity:** 🟢 Simple

### 6.9 Past Practice / Maintenance of Standards

**What it is:** A provision preserving existing working conditions and practices that have been in effect, even if they're not explicitly spelled out in the contract. This prevents the employer from eliminating established benefits by arguing "it's not in the contract."

**How to find it:** May be its own article or a clause within "General Provisions." Look for "past practice," "maintenance of standards," "existing conditions," "established practice."

**What to extract:**
- Whether a past practice clause exists (yes/no)
- Exact language used (important for arbitration interpretation)
- Whether it covers only mandatory subjects of bargaining or all working conditions
- Any limitations or exceptions

**How common:** Moderately common. Prevalence: ~35-50%.

**Complexity:** 🟢 Simple (to extract — the clause itself is usually short, though its legal implications are vast)

---

## PART 7: DISPUTE RESOLUTION

These provisions are the "justice system" of the workplace — how disagreements between the employer and the union get resolved without strikes.

### 7.1 Grievance Procedure

**What it is:** A formal, multi-step process for resolving disputes about contract interpretation and application. Typically starts with a conversation between the employee, steward, and supervisor, and escalates through increasingly senior management and union representatives. This is the enforcement mechanism for the entire contract.

**How to find it:** Almost always its own article, usually one of the longest in the contract. Titled "Grievance Procedure" or "Complaint Procedure."

**What to extract:**
- Number of steps (typically 2-4 steps)
- For EACH step:
  - Who participates from the union side
  - Who participates from the management side
  - Time limit to file at this step (in days — calendar or business days)
  - Time limit for management to respond
  - Whether the meeting/hearing is required or optional
  - Whether the response must be in writing
- Who can file a grievance (individual employee, union, group of employees, employer)
- Definition of "grievance" used in the contract
- Whether "class action" grievances are allowed (grievances on behalf of all employees)
- Whether the procedure applies to discipline cases differently than contract interpretation cases
- What happens if a time limit is missed (waived? grievance denied?)

**How common:** Universal. Prevalence: ~99%.

**Complexity:** 🔴 Complex — Multi-step procedures with specific time limits and participant requirements at each level. The details matter enormously for enforcement.

### 7.2 Arbitration

**What it is:** The final step of the grievance procedure — an independent neutral third party (the arbitrator) hears the case and issues a binding decision. This replaces the court system for contract disputes.

**How to find it:** Usually its own article or the final section of the Grievance Procedure article. Titled "Arbitration" or "Grievance Arbitration."

**What to extract:**
- Whether arbitration is binding or advisory (almost always binding)
- How the arbitrator is selected:
  - Permanent arbitrator (named individual or panel)
  - Ad hoc selection through AAA (American Arbitration Association)
  - Ad hoc selection through FMCS (Federal Mediation and Conciliation Service)
  - Ad hoc selection through state mediation agency
  - Mutual selection from a list
- Scope of the arbitrator's authority:
  - Can the arbitrator add to, subtract from, or modify the contract?
  - Can the arbitrator award back pay?
  - Are there any subjects excluded from arbitration?
- Cost sharing (typically split 50/50 between employer and union)
- Timeline requirements (how quickly the hearing must be scheduled)
- Expedited arbitration for certain types of cases

**How common:** Nearly universal in contracts with grievance procedures. Prevalence: ~95%.

**Complexity:** 🟡 Medium

### 7.3 Mediation

**What it is:** A voluntary step between the grievance procedure and arbitration where a neutral mediator helps the parties reach a settlement. Unlike an arbitrator, a mediator cannot impose a decision.

**How to find it:** Within the Grievance or Arbitration article, or referenced as an optional step. Look for "mediation," "grievance mediation," "med-arb."

**What to extract:**
- Whether mediation is available (yes/no)
- Whether it's mandatory or optional before arbitration
- Who provides mediation services (FMCS, state agency, private mediator)
- Cost sharing
- Whether mediation is binding or non-binding

**How common:** Less common as a formal contract provision, but growing. Prevalence: ~15-25%.

**Complexity:** 🟢 Simple

---

## PART 8: CONTRACT ADMINISTRATION

These are the "meta" provisions — clauses about the contract itself rather than about specific working conditions.

### 8.1 Duration

**What it is:** The effective date and expiration date of the contract, and whether it automatically renews.

**How to find it:** Usually the last article. Titled "Duration" or "Term of Agreement."

**What to extract:**
- Effective date
- Expiration date
- Total duration (1 year, 2 years, 3 years, etc.)
- Automatic renewal / evergreen clause (does the contract continue past expiration if no new agreement is reached?)
- Notice period required to terminate or modify (typically 60-90 days before expiration)

**How common:** Universal. Prevalence: ~100%.

**Complexity:** 🟢 Simple

### 8.2 Separability / Savings Clause

**What it is:** If any provision of the contract is found to be illegal or unenforceable by a court, the rest of the contract survives.

**How to find it:** Short clause, usually near the end of the contract or in "General Provisions." Look for "separability," "savings clause," "severability," "if any provision is found invalid..."

**What to extract:**
- Whether a separability clause exists (yes/no)
- Whether the parties agree to renegotiate the invalid provision

**How common:** Very common. Prevalence: ~75-85%.

**Complexity:** 🟢 Simple

### 8.3 Entire Agreement / Zipper Clause

**What it is:** States that the written contract represents the complete agreement between the parties, and that neither side is obligated to bargain on any subject during the contract's term. This "zips up" the contract — nothing outside it is enforceable.

**How to find it:** Near the end of the contract in "General Provisions." Look for "entire agreement," "complete agreement," "zipper," "waiver of bargaining."

**What to extract:**
- Whether a zipper clause exists (yes/no)
- Exact language (important for determining scope)
- Whether it explicitly waives the duty to bargain during the contract term
- Any exceptions or carve-outs

**How common:** Common. Prevalence: ~50-65%.

**Complexity:** 🟢 Simple

### 8.4 Side Letters and Memoranda of Understanding (MOUs)

**What it is:** Supplementary documents attached to or associated with the main contract that address specific issues — often items resolved during bargaining that don't fit neatly into the contract structure, temporary arrangements, or agreements about how specific provisions will be implemented.

**How to find it:** Usually appear as appendices or attachments at the end of the contract. May be titled "Side Letter," "Letter of Agreement," "Letter of Understanding," "Memorandum of Understanding," "MOU," "Appendix."

**What to extract:**
- Number of side letters/MOUs
- Subject of each
- Whether each is incorporated into the contract (has the force of the contract) or is a separate understanding
- Effective date and expiration of each (some expire before the main contract)
- Parties who signed each

**How common:** Very common — most contracts of any significant length have at least a few. Prevalence: ~60-75%.

**Complexity:** 🟡 Medium — The challenge is identifying and categorizing supplementary documents that may cover any topic.

### 8.5 Printing and Distribution

**What it is:** Requires the employer to print copies of the contract and distribute them to all employees, or provides for joint printing and cost-sharing.

**How to find it:** Usually a short clause in "General Provisions" or near the Duration article.

**What to extract:**
- Who pays for printing (employer, union, shared)
- How copies are distributed
- Whether electronic distribution is permitted
- Timeline for distribution after ratification

**How common:** Moderately common. Prevalence: ~40-55%.

**Complexity:** 🟢 Simple

---

## PART 9: SECTOR-SPECIFIC PROVISIONS

Some provisions appear primarily or exclusively in contracts covering specific industries. The extraction system should recognize these when present.

### 9.1 Construction Industry

**Hiring hall:** Union operates a referral system where employers request workers through the union rather than hiring directly. Extract: whether exclusive or non-exclusive, referral order (seniority, rotation, etc.), employer's right to reject referrals.

**Apprenticeship:** Joint apprenticeship and training programs. Extract: ratio of apprentices to journeyworkers, training requirements, wage progression during apprenticeship.

**Travel pay and subsistence:** Compensation for traveling to job sites. Extract: mileage radius triggering travel pay, per diem rates, zone pay.

**Show-up time / reporting pay:** Guaranteed minimum pay when a worker reports to a job site and work is canceled. Extract: minimum hours guaranteed (typically 2-4 hours).

**Work preservation / jurisdictional clauses:** Defining which trade performs which work. Extract: work descriptions, jurisdictional boundaries between trades.

### 9.2 Healthcare

**Staffing ratios / patient care:** Minimum nurse-to-patient ratios or other staffing standards. Extract: specific ratios by unit type (ICU, med-surg, ER), enforcement mechanisms.

**Float pool:** Rules about reassigning nurses or other staff to units other than their home unit. Extract: frequency limitations, pay premiums for floating, orientation requirements.

**Mandatory overtime restrictions:** Limits on requiring healthcare workers to stay beyond their scheduled shift. Extract: whether mandatory overtime is prohibited, exceptions for emergencies, penalty pay for mandatory overtime.

**Professional practice:** Provisions protecting clinical judgment and professional standards. Extract: right to refuse assignments beyond competency, professional development time, continuing education support.

### 9.3 Education

**Class size:** Maximum number of students per class. Extract: specific limits by grade level, consequences if limits are exceeded, how overages are handled.

**Academic freedom:** Protection for teaching methods, curriculum input, and intellectual freedom. Extract: scope of protections, limitations.

**Tenure provisions:** Job security protections after completing a probationary period (distinct from seniority). Extract: probationary period length, tenure criteria, tenure review process.

**Evaluation procedures:** How teachers or faculty are evaluated. Extract: frequency of evaluations, who evaluates, criteria used, consequences of poor evaluations, role of the union in the evaluation process.

**Preparation time:** Guaranteed time during the workday for class preparation. Extract: minutes per day, whether it can be used for meetings.

### 9.4 Public Safety (Law Enforcement / Fire)

**Bill of rights / officer protections:** Specific protections during internal investigations. Extract: interrogation procedures, representation rights, notice requirements, cooling-off periods.

**Use of force policies:** Rules governing when and how force can be used. Extract: whether these are incorporated into the contract, review procedures after force incidents.

**Fitness for duty:** Physical fitness requirements and testing. Extract: testing standards, consequences of failure, accommodation provisions.

**Equipment and vehicle provisions:** Personal equipment, body cameras, vehicle take-home policies. Extract: what's provided, maintenance responsibilities, body camera activation rules.

### 9.5 Transportation

**Hours of service:** Rules beyond federal DOT requirements governing driving time and rest periods. Extract: maximum driving hours, minimum rest periods, split sleeper provisions.

**Route bidding:** How routes or assignments are selected. Extract: seniority-based bidding frequency, bid periods, bump procedures.

**Equipment standards:** Vehicle safety and comfort requirements. Extract: vehicle age limits, maintenance standards, AC/heat requirements, technology in vehicles.

---

## PART 10: EMERGING AND EVOLVING PROVISIONS

These are provision types that are relatively new, growing in prevalence, and may not appear in older classification systems. The extraction system should be particularly attentive to these.

### 10.1 Artificial Intelligence and Algorithmic Management

**What it is:** Provisions addressing employer use of AI for hiring, scheduling, performance evaluation, discipline, and workforce management decisions.

**How to find it:** Very new — may appear in "Technology," "Working Conditions," or as a side letter/MOU. Look for "artificial intelligence," "AI," "algorithm," "automated decision," "machine learning."

**What to extract:**
- Whether AI/algorithmic management is addressed at all (flag if yes)
- Restrictions on AI-based discipline or termination decisions
- Transparency requirements (employer must disclose AI use)
- Human review requirements for AI-generated decisions
- Bargaining rights over AI implementation

**Prevalence:** Very low (~5-10%) but growing rapidly. Most provisions date from 2023 or later.

### 10.2 Diversity, Equity, and Inclusion (DEI)

**What it is:** Provisions going beyond traditional non-discrimination to address affirmative equity goals, diverse hiring practices, anti-racism training, or pay equity audits.

**How to find it:** May be its own article, within "Non-Discrimination," or as a side letter. Look for "diversity," "equity," "inclusion," "DEI," "pay equity," "anti-racism."

**What to extract:**
- Whether DEI provisions exist
- Joint labor-management DEI committees
- Pay equity audit requirements
- Diversity training requirements
- Affirmative action provisions

**Prevalence:** Growing — ~15-25% of newer contracts.

### 10.3 Climate / Environmental Provisions

**What it is:** Provisions addressing workplace impacts of climate change (extreme heat, air quality), environmental sustainability, or "just transition" protections for workers affected by clean energy transitions.

**How to find it:** Very new. May appear in "Safety," "Working Conditions," or side letters. Look for "climate," "extreme heat," "air quality," "just transition," "environmental."

**What to extract:**
- Heat stress protections
- Air quality provisions (wildfire smoke, etc.)
- Green jobs training
- Just transition provisions for workers displaced by decarbonization

**Prevalence:** Very low (~5%) but a frontier area of bargaining.

### 10.4 Pandemic / Public Health Emergency Provisions

**What it is:** Provisions addressing workplace protocols during pandemics or public health emergencies. Many contracts added these during or after the COVID-19 pandemic.

**How to find it:** May be its own article, a side letter, or within "Safety and Health." Look for "pandemic," "public health emergency," "COVID," "infectious disease."

**What to extract:**
- Remote work triggers during emergencies
- PPE and safety protocol requirements
- Hazard pay provisions
- Leave provisions for quarantine/isolation
- Vaccination policies and exemptions

**Prevalence:** ~20-30% of contracts negotiated since 2020.

---

## PART 11: EXISTING CLASSIFICATION SYSTEMS

Several academic and institutional frameworks have already attempted to classify CBA provisions. The extraction system should be aware of these:

### BLS/OLMS Clause Coding System
The Bureau of Labor Statistics historically coded CBA provisions when collecting contracts for the OLMS collection. Their system categorized clauses into major groups (wages, fringe benefits, institutional issues, administration) with sub-codes.

### WageIndicator CBA Coding Scheme
The WageIndicator Foundation codes 3,600+ CBAs from 76 countries using a standardized taxonomy covering 12 major categories with dozens of sub-categories.

### CUAD (Contract Understanding Atticus Dataset)
An academic dataset of 510 contracts with 13,101 labeled clauses across 41 categories. While focused on commercial contracts rather than CBAs, several categories overlap (termination, assignment, non-compete, etc.).

### Arold, Ash, MacLeod, and Naidu (NBER 2025)
Analyzed 32,000+ contracts using dependency parsing of modal verbs (shall/may/shall not) to assess the legal force of contract language. Their key insight: the same provision can have vastly different legal weight depending on whether it says "the employer SHALL" (mandatory) vs. "the employer MAY" (discretionary).

### UC Berkeley Labor Center "Negotiating Tech"
Reviewed 500+ contracts to identify 6 categories of technology-related provisions across 175+ agreements, creating the most current framework for tech/surveillance/AI contract language.

---

## PART 12: EXTRACTION PRIORITY MATRIX

For building the system, not all provisions are equally important or equally easy to extract. This matrix recommends a build order:

### Priority 1 — Build First (High value, easier extraction)
| Provision | Why First |
|-----------|-----------|
| Contract parties (Recognition) | Needed to link contracts to database entities |
| Duration (dates) | Critical for identifying current vs. expired contracts |
| Just cause | Single most important substantive provision |
| No-strike clause | Key indicator of contract type |
| Grievance procedure steps | Core enforcement mechanism |
| Arbitration clause | Essential dispute resolution info |
| Union security type | Major institutional provision |

### Priority 2 — Build Next (High value, medium extraction difficulty)
| Provision | Why Next |
|-----------|----------|
| Wage rates/schedules | Highest organizer interest, but complex formats |
| Health insurance | Major economic provision |
| Seniority system | Core workplace organizing principle |
| Overtime rules | Directly affects take-home pay |
| Holiday schedule | Easy to verify, high interest |
| Vacation accrual | Directly comparable across contracts |

### Priority 3 — Build Later (Medium value or high difficulty)
| Provision | Why Later |
|-----------|-----------|
| Management rights (broad vs. narrow) | Requires nuanced interpretation |
| Subcontracting restrictions | Variable format |
| Layoff/recall/bumping | Complex nested rules |
| Progressive discipline | Moderate complexity |
| All leave types | Many sub-categories |
| Pension/retirement details | Complex formulas |
| Sector-specific provisions | Require specialized training examples |

### Priority 4 — Build When Ready (Emerging or specialized)
| Provision | Why Last |
|-----------|----------|
| Technology/AI provisions | Sparse data, evolving language |
| DEI provisions | New and variable |
| Climate provisions | Very rare currently |
| Side letters/MOUs | Unpredictable format and content |
| Past practice clauses | Short but legally complex |

---

## PART 13: LANGUAGE PATTERNS FOR EXTRACTION

This section provides the specific keywords, phrases, and patterns that signal each provision type. The AI extraction system should use these as recognition triggers.

### Modal Verb Significance (from Arold et al.)
The legal force of a provision depends heavily on the modal verb used:
- **"shall"** = mandatory obligation ("The employer SHALL provide...")
- **"will"** = strong commitment, slightly less formal than shall
- **"may"** = permissive/discretionary ("The employer MAY provide...")
- **"shall not"** = prohibition ("The employer SHALL NOT subcontract...")
- **"must"** = mandatory, often for employee obligations
- **"should"** = advisory, rarely used in binding provisions

The extraction system should record which modal verb is used for each provision, as this dramatically affects its legal meaning.

### Common Trigger Phrases by Provision Type

**Wages:** "base rate," "hourly rate," "wage scale," "salary schedule," "step increase," "longevity," "across-the-board increase," "cost of living adjustment," "COLA"

**Grievance:** "grievance shall be filed," "within [X] working days," "Step 1," "Step 2," "referred to arbitration," "grievance committee," "shop steward shall"

**Seniority:** "seniority shall be defined as," "departmental seniority," "plant-wide seniority," "classification seniority," "seniority list shall be posted," "loss of seniority"

**Management rights:** "the employer retains the right," "sole and exclusive right," "management prerogative," "reserved to management," "direct the workforce"

**Just cause:** "just cause," "proper cause," "discharged or disciplined," "without just and sufficient cause," "cause for dismissal"

**Union security:** "condition of employment," "as a condition of continued employment," "agency fee," "fair share," "union shop," "maintenance of membership," "dues checkoff"

**No-strike:** "no strike," "no work stoppage," "no slowdown," "sympathy strike," "honor picket line," "no lockout"

**Arbitration:** "binding arbitration," "arbitrator's decision shall be final," "American Arbitration Association," "Federal Mediation and Conciliation Service," "selection of arbitrator"

**Health insurance:** "health plan," "medical coverage," "premium contribution," "employer shall pay [X]% of the premium," "PPO," "HMO," "deductible," "copay"

**Duration:** "this Agreement shall be effective," "shall remain in force," "expire on," "automatically renew," "evergreen"

---

*End of CBA Provision Taxonomy — Version 1.0, February 2026*
*For use with the Labor Relations Research Platform CBA extraction system*
*This document should be updated as new provision types are identified during contract processing*
