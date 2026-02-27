# CBA Database Build Plan
## Collective Bargaining Agreement Extraction, Categorization & Research System

**Purpose:** Build a structured database that reads union contracts, tags every clause by topic, and lets organizers search and compare language across unions, employers, and time.

**Approach:** One contract at a time, one category at a time. Get each step right before adding the next. Build scripts that eventually run on their own — no AI required at runtime.

---

## The Big Picture

A finished version of this system lets someone ask:
- *"Show me every healthcare clause from retail contracts in New York after 2018"*
- *"How do different unions handle subcontracting language?"*
- *"What's the strongest grievance procedure language we have on file?"*

To get there, we build four scripts in sequence, test each one thoroughly on a single contract, and only move forward when it's accurate.

---

## How AI Fits Into This (And Doesn't)

This is important to understand before building anything.

### Claude Code is a development partner, not a permanent part of the system

Claude Code writes and refines the Python scripts. Once a script works, it works forever — on its own, with no AI involved. Claude Code's job is to help build and fix the tools, not to be one of them permanently.

The workflow looks like this:
1. Open Claude Code, describe what you want
2. Claude writes a Python script
3. You run it on a real contract
4. You see what worked and what didn't, take notes
5. Tell Claude Code what to fix
6. Repeat until the script is reliable
7. Save that script — it now runs forever, independently

### Which parts never need AI at all

Some steps are purely mechanical — no AI, no internet, no cost, ever:

- **PDF to text** — PyMuPDF is a Python library that reads PDFs and outputs text. Runs instantly, completely free, always will be.
- **Finding article headings** — Contracts follow predictable patterns. "ARTICLE 12" or "Section 3.4" look the same in almost every contract. Simple pattern-matching rules find these reliably.
- **Extracting dates and party names** — These follow patterns too. Dates look like dates. Union names appear in the first two pages near phrases like "hereinafter referred to as." A well-written script handles this without any AI.

### The one place AI helps — and how it phases out

Categorization — deciding whether a paragraph is about healthcare versus wages versus job security — is the only step that genuinely benefits from AI. But you only need AI to help *build the rules*, not to run them forever.

The process: run a script on a contract, Claude Code helps identify what good healthcare language looks like, and over time you build up a list of patterns and signals that reliably identify each category. Eventually that list is good enough that the script runs entirely on its own — no API, no cost, just Python checking whether a paragraph matches known patterns.

Think of it like having a smart colleague help you write a checklist. Once the checklist is written and tested, anyone can use it — including a dumb script.

### What "no AI required" looks like at scale

After enough iteration, loading a new contract works like this:

```
1. Drop PDF into a folder
2. Run: python process_contract.py filename.pdf
3. Script automatically:
   - Extracts text (PyMuPDF — free, instant)
   - Finds article structure (pattern matching — free, instant)
   - Identifies parties and dates (pattern matching — free, instant)
   - Tags each section by category (rule-based matching built from prior work — free, instant)
   - Writes results to the database
4. You review anything flagged as low-confidence
5. Done
```

No API. No internet connection required. No cost per contract. Runs in seconds.

### The realistic path to get there

After processing 20–30 contracts iteratively with Claude Code, the scripts will be robust enough to handle new contracts automatically. The work put in early pays off on every contract processed afterward.

---

## Database Structure

Four tables that link together. Think of them as connected spreadsheets.

### Table 1: `contracts`
One row per agreement. The master list.

| Field | What It Stores | Example |
|---|---|---|
| contract_id | Unique ID we assign | 001 |
| employer_name | The company | Acme Building Services |
| union_name | The union | SEIU Local 32BJ |
| effective_date | When it started | 2022-01-01 |
| expiration_date | When it ends | 2025-12-31 |
| industry | Sector | Building Services |
| state | Coverage area | New York |
| source_file | Path to original PDF | /contracts/seiu_acme_2022.pdf |
| full_text | Entire contract text | [raw extracted text] |
| page_count | How many pages | 84 |
| doc_type | Digital or scanned PDF | digital |
| date_added | When we processed it | 2026-03-01 |

### Table 2: `provisions`
One row per tagged clause. A single contract generates hundreds of rows here.

| Field | What It Stores | Example |
|---|---|---|
| provision_id | Unique ID | 4421 |
| contract_id | Links to Table 1 | 001 |
| category | Topic bucket | Healthcare |
| subcategory | More specific | Employer Contribution |
| extracted_text | The actual language | "Employer shall contribute $450/mo..." |
| article_reference | Location in contract | Article 14, Section 3 |
| page_number | Physical page | 27 |
| confidence_score | How sure the script was (0–1) | 0.94 |
| human_reviewed | Has a person checked this? | False |

### Table 3: `categories`
The master list of valid topic buckets. Prevents typos and inconsistency.

| category_id | category_name | subcategories |
|---|---|---|
| 1 | Healthcare | Premiums, Coverage, Dental, Vision, Mental Health |
| 2 | Wages | Base Rate, COLA, Differentials, Overtime |
| 3 | Grievance | Steps, Arbitration, Timelines |
| 4 | Pension | Defined Benefit, 401k, Employer Match |
| 5 | Seniority | Layoff Order, Bidding, Recall |
| 6 | Management Rights | — |
| 7 | Union Security | Dues Checkoff, Agency Shop, Steward Rights |
| 8 | Leave | Vacation, Sick, Parental, Bereavement, Union Leave |
| 9 | Scheduling | Hours, Overtime Rights, Shift Assignments |
| 10 | Childcare | — |
| 11 | Job Security | Just Cause, Probation, Subcontracting |
| 12 | Training | — |
| 13 | Technology | Surveillance, AI, Remote Work |
| 14 | Other | — |

### Table 4: `reviews`
Log of every human correction. This is how accuracy improves over time and how the rules get smarter.

| Field | What It Stores | Example |
|---|---|---|
| review_id | Unique ID | 1 |
| provision_id | Which clause was corrected | 4421 |
| original_category | What the script said | Wages |
| corrected_category | What it should be | Healthcare |
| reviewer | Who fixed it | Jacob |
| date | When | 2026-03-01 |
| notes | Why it was wrong | "Contribution language, not wage" |

Each correction is a signal. Patterns in what gets corrected feed back into improving the categorization rules in Script 4 — no AI needed, just better pattern definitions.

---

## The Four Scripts

### Script 1: PDF Text Extractor
**What it does:** Converts a PDF into clean, readable text. Nothing more.

**AI required:** Never. This is pure Python.

**Why this comes first:** Everything downstream depends on clean text. A bad extraction poisons every step after it.

**Two cases to handle:**
- **Digital PDFs** (text is selectable/copyable): Use `PyMuPDF` — free, fast, accurate, always
- **Scanned PDFs** (photos of paper): Use `pytesseract` locally for free — accuracy depends on scan quality

**Output:** A `.txt` file with the full contract text, plus a note on which method was used and page count.

**Verification checkpoint:** Open the original PDF and the extracted `.txt` file side by side. Ask:
- Are there broken words or garbled characters?
- Are tables and wage schedules readable or mangled?
- Did any pages get skipped?
- Are headers and article titles preserved?

Do not move to Script 2 until the text looks clean.

---

### Script 2: Party & Metadata Extractor
**What it does:** Reads the first 5–10 pages and pulls out structured metadata.

**AI required:** Only during development. Once the patterns are refined, pure Python.

**Fields to extract:**
- Union name and local number
- Employer / company name
- Effective date
- Expiration date
- Geographic coverage (city, state, region)
- Bargaining unit description (who the contract covers)
- Industry/sector

**How it works:** Party names and dates always appear in the first few pages using predictable phrases — "between [UNION] and [EMPLOYER]," "effective as of," "hereinafter referred to as." The script learns these patterns across contracts until it reliably finds them without assistance.

**Output:** One row in the `contracts` table with all fields populated.

**Verification checkpoint:** Compare every extracted field against the actual PDF cover pages by eye. It's just 6–8 fields — fast to check. Fix any mistakes before continuing.

---

### Script 3: Article/Section Finder
**What it does:** Identifies every article heading and section title, and breaks the contract into labeled chunks.

**AI required:** Never. This is pattern matching.

**Why this step exists:** Contracts are organized into Articles (e.g., "Article 12: Grievance Procedure"). Knowing where each article starts and ends means later scripts work on small, focused chunks instead of 500 pages at once. Smaller chunks = more accurate categorization.

**How it works:** The script scans for patterns that look like article headings — all-caps lines, lines starting with "Article" or "Section," numbered headers. It builds a structural map of the whole contract.

**Output:** A structured outline like:
```
Article 1: Recognition — Pages 1-2
Article 2: Management Rights — Pages 3-4
Article 3: Union Security — Pages 5-7
Article 4: Wages — Pages 8-15
Article 5: Healthcare — Pages 16-22
...
```

**Verification checkpoint:** Compare the extracted outline to the actual table of contents in the PDF. Do all articles appear? Are page numbers right? Fix any missed headings before moving to Script 4.

---

### Script 4: Category Tagger
**What it does:** For ONE category at a time, reads each article chunk and identifies relevant language.

**AI required:** During development only. The goal is to build rules good enough to run standalone.

**This script runs multiple times — once per category.**

**How the rules get built:** During development with Claude Code, you run the script, check what it found against the real contract, and note what it missed or got wrong. Each correction becomes a new rule or pattern. Over 20–30 contracts, the rules become comprehensive enough that new contracts get categorized automatically — no AI call needed.

**Why one category at a time:**
- Fewer things can go wrong in a single pass
- Errors are easier to find and fix
- Rules for each category can be tuned independently
- Some categories (wages) are simple; others (management rights) are nuanced — they need different logic

**The iterative process for each category:**

1. Run the script on the test contract
2. Open the original PDF
3. Check for **misses** — language that belongs here but wasn't found
4. Check for **false positives** — language grabbed that doesn't belong
5. Check for **truncation** — text cut off mid-sentence
6. Note what went wrong and why
7. Tell Claude Code what needs fixing — it updates the script
8. Re-run and repeat until accurate
9. Only then move to the next category

**Order to build categories (easiest → hardest):**

| Order | Category | Why This Difficulty |
|---|---|---|
| 1 | Healthcare | Usually its own clearly labeled article |
| 2 | Wages | Usually a table — easy to spot but formatting is tricky |
| 3 | Grievance | Clear procedural steps, usually well-labeled |
| 4 | Vacation / Leave | Relatively contained sections |
| 5 | Pension / 401k | Usually clear article, but benefit math is complex |
| 6 | Seniority | Often scattered across multiple articles |
| 7 | Management Rights | Often just one clause but heavy in implications |
| 8 | Union Security | Short but legally specific |
| 9 | Childcare | May not exist — script must handle "not found" gracefully |
| 10 | Job Security | Often overlaps with seniority and discipline |
| 11 | Scheduling | Can be buried inside wages or hours articles |
| 12 | Training | Often a short, standalone article |
| 13 | Technology | May not exist in older contracts |
| 14 | Other | Catch-all for everything that doesn't fit |

---

## Development Phases

### Phase 1: One Contract, Get It Right
- [ ] Choose one test contract — preferably a digital PDF, not scanned
- [ ] Run Script 1: extract and clean the text
- [ ] Verify text quality manually
- [ ] Run Script 2: extract parties and metadata
- [ ] Verify all fields are correct
- [ ] Run Script 3: build article outline
- [ ] Verify outline matches table of contents
- [ ] Run Script 4 for Healthcare only — iterate until accurate
- [ ] Run Script 4 for each remaining category, one at a time
- [ ] Full review: read through all extracted provisions vs. original

**Goal:** 90%+ accuracy on this one contract before moving on.

---

### Phase 2: Five Contracts, Find the Gaps
- [ ] Run the full pipeline on 4 more contracts (mix of unions, industries, states)
- [ ] Do the scripts handle different formatting styles?
- [ ] Fix any new failure modes discovered
- [ ] Build the review workflow: a simple way to flag and correct wrong categorizations
- [ ] Start logging corrections in the `reviews` table
- [ ] Feed corrections back into Script 4 rules

**Goal:** Scripts work reliably across different contract formats without manual tuning per contract.

---

### Phase 3: Scale to 50 Contracts — Scripts Run Standalone
- [ ] Process the full pilot batch with no AI assistance
- [ ] Spot-check 10% of extractions manually
- [ ] Measure accuracy: what % of provisions are correctly categorized?
- [ ] Identify any categories still needing improvement
- [ ] Build basic search: filter by category, union, employer, date range

**Goal:** A fully standalone pipeline. Drop in a PDF, get a categorized database entry. No AI, no API, no cost per contract.

---

### Phase 4: Connect to Main Platform
- [ ] Link `contracts.employer_name` to existing `employers` table via employer_id
- [ ] Link `contracts.union_name` to existing `unions` table via union_id
- [ ] Surface contract data on employer and union profile pages
- [ ] Add contract expiration date tracking and alerts

---

## Technical Stack

| Component | Tool | AI Required? | Cost |
|---|---|---|---|
| PDF text extraction (digital) | PyMuPDF | Never | Free |
| PDF text extraction (scanned) | pytesseract | Never | Free |
| Article structure detection | Python regex/pattern matching | Never | Free |
| Party & date extraction | Python pattern matching | Dev only | Free at runtime |
| Category tagging | Python rule engine (built iteratively) | Dev only | Free at runtime |
| Database | PostgreSQL | Never | Already running |
| Script language | Python | Never | Free |
| Output format (interim) | CSV / JSON | Never | Free |

---

## Key Principles

**Claude Code is a tool for building, not running.** It writes and refines scripts. Once a script is accurate, it runs forever on its own. The goal is always to move each step toward pure Python with no dependencies.

**Wrong beats missing.** A miscategorized provision poisons search results. Better to have fewer provisions with high confidence than many with unknown accuracy.

**Store the full text always.** Keep the raw full_text in the contracts table even after categorizing everything. Rules improve over time — you'll want to re-run categorization on old contracts without re-processing PDFs.

**Corrections are data.** Every time a human fixes a wrong categorization, that's a signal about what the rules are missing. Log every correction and use them to improve Script 4.

**One thing at a time.** One contract, one category, one script at a time. Resist the urge to process everything at once until each step is verified.

---

## Next Immediate Steps in Claude Code

1. Install dependencies: `pip install pymupdf pytesseract pandas`
2. Create folder structure:
   ```
   /cba_database/
     /contracts/          ← PDF files go here
     /extracted_text/     ← Script 1 output
     /provisions/         ← Script 4 output (JSON per category)
     /scripts/
       01_extract_text.py
       02_extract_parties.py
       03_find_sections.py
       04_tag_category.py
     /data/
       contracts.csv      ← Interim before DB write
       provisions.csv
     /rules/
       healthcare.json    ← Category rules built over time
       wages.json
       grievance.json
       ...
   ```
3. Pick the test contract and drop it in `/contracts/`
4. Run Script 1

---

*Last updated: February 2026*
*Status: Phase 1 — Not started*
