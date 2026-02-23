# GEMINI RESEARCH TASK: Union Contract (CBA) Source Mapping & LangExtract Extraction Plan

## Context for Gemini

You are conducting foundational research for a Labor Relations Research Platform. The platform already has a PostgreSQL database with 207+ tables, 13.5+ million records, and tracks relationships between ~100,000 employers and ~26,665 unions covering 14.5 million members. It integrates 18+ government databases (OLMS, NLRB, OSHA, DOL wage data, etc.).

The next major project is building a **searchable union contract database** — a system that collects thousands of Collective Bargaining Agreements (CBAs), reads them with AI, extracts the important parts (wages, grievance procedures, benefits, seniority rules, management rights), and makes them searchable. An organizer could type "show me grievance procedures in healthcare contracts in New York" and get back actual contract language from dozens of agreements, with every extracted piece linked back to the exact page and paragraph it came from.

**Your job in this task is the research and reconnaissance phase** — mapping out exactly where contracts live, how to get them, what format they're in, and what obstacles exist. This research will be handed to a development team (Claude + Codex) who will build the actual scraping and extraction tools.

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

## PART 2: LangExtract Integration Plan

LangExtract is a Python library by Google (Apache 2.0 license, GitHub: google/langextract) that extracts structured information from unstructured text using AI models. Its key feature for our purposes is **precise source grounding** — every piece of extracted information gets mapped back to its exact character position in the original text. This means when we extract a wage provision from page 47 of a contract, we can show the user exactly where in the document that language appears.

### How LangExtract works (so you understand what to design for):

1. **You define "extraction classes"** — categories of information you want to pull out (like "wage_provision," "grievance_procedure," "seniority_clause")
2. **You provide a few examples** (called "few-shot examples") — you show it 3-5 real examples of each clause type from actual contracts, and it learns the pattern
3. **It chunks long documents** — since contracts can be 50-300 pages, LangExtract breaks them into manageable pieces, processes each piece, and merges the results
4. **It runs multiple passes** — to catch things it might miss on the first read
5. **Every extraction includes source grounding** — exact character offsets mapping back to the source text, so you can highlight exactly where something came from
6. **Output is structured JSONL** — each extraction is a clean data record with the extracted content, its type, confidence indicators, and source location

### What I need you to research and design:

**A. Define the extraction classes for CBA analysis**

Based on your research into actual contract structure, define 12-20 extraction classes that cover the most important and commonly-searched provisions in union contracts. For each class, provide:

- **Class name** (machine-readable, like `wage_base_rate`)
- **Plain English description** of what this captures
- **Why organizers care** about this specific provision
- **How it typically appears** in contracts (what section headings, what kind of language)
- **Complexity rating** (Simple = usually one sentence or number, Medium = a paragraph or short section, Complex = multi-page with sub-provisions)
- **Expected extraction accuracy** based on complexity (Simple provisions like dates and dollar amounts will be high accuracy; complex multi-clause grievance procedures will be lower)

Suggested starting categories (expand, modify, or reorganize as your research suggests):

1. Contract parties (employer name, union name, local number)
2. Effective and expiration dates
3. Wage/salary base rates and scales
4. Wage increase schedules (annual raises, step increases)
5. Health insurance provisions
6. Pension/retirement provisions
7. Grievance procedure (number of steps, binding arbitration yes/no, time limits)
8. Management rights clause
9. Union security clause (union shop, agency shop, right-to-work provisions)
10. Seniority provisions
11. Just cause / discipline and discharge language
12. No-strike clause
13. Overtime provisions
14. Hours of work / scheduling
15. Leave provisions (sick, vacation, personal, family)
16. Subcontracting / outsourcing restrictions
17. Layoff and recall procedures
18. Duration and reopener provisions

**B. Create few-shot example specifications**

For EACH extraction class you define, describe what ideal few-shot examples should look like. You don't need to write the actual examples yet (that requires real contract text), but describe:

- What a "perfect" example of this clause type looks like
- What a "tricky" example looks like (edge cases the AI might struggle with)
- What a "negative" example looks like (text that LOOKS like this clause type but isn't)
- How many examples you'd recommend (minimum 3, some complex types may need 5-8)

**C. Source grounding citation design**

This is critical — when a user sees an extracted provision, they need to be able to trace it back to the exact source. Design the citation schema that should accompany every extraction:

- Source contract identifier (which contract)
- Page number(s) in the original PDF
- Section/Article reference (e.g., "Article 12, Section 3")
- Character offsets in the extracted text (LangExtract provides these automatically)
- Confidence score
- Extraction model and version used
- Date of extraction

**D. Document quality classification system**

Before running LangExtract on a contract, the system needs to know what it's working with. Design a classification system for contract document quality:

- How to detect if a PDF is native digital text vs. scanned images
- How to handle mixed documents (some pages scanned, some digital)
- How to detect contract structure quality (well-organized with clear headings vs. poorly formatted)
- How to estimate processing cost before committing resources
- Recommended OCR strategy for different document types (the research shows PyMuPDF for digital PDFs is free, while scanned documents need cloud OCR services like Mistral OCR at ~$1/1,000 pages)

---

## PART 3: Processing Pipeline Design

Design the end-to-end flow from "we found a contract on a website" to "it's searchable in our database with every clause tagged and citable." The development team will implement this, but they need a clear blueprint.

### Pipeline stages to design:

1. **Discovery & Download**
   - How does a contract get from a source website into our system?
   - What metadata do we capture at download time?
   - How do we avoid downloading duplicates?
   - How do we track provenance (which source, when downloaded, what URL)?

2. **Document Assessment**
   - Automatic detection: Is this actually a CBA? (Some files on these sites might be memoranda of understanding, arbitration awards, or other non-CBA documents)
   - Format classification: Digital PDF, scanned PDF, DOCX, HTML
   - Quality assessment: Readable? Corrupted? Password-protected?
   - Structure assessment: Well-organized with headings? Or wall of text?

3. **Text Extraction**
   - Digital PDFs → PyMuPDF (free, instant)
   - Scanned PDFs → OCR service (Mistral OCR recommended, ~$1/1,000 pages)
   - Tables (wage schedules, benefit tables) → Enhanced table extraction (IBM's Docling, 97.9% accuracy, free to self-host)
   - Output: Normalized text with page references preserved

4. **LangExtract Clause Extraction**
   - Chunking strategy (respect article/section boundaries in contracts)
   - Multi-pass extraction for higher recall
   - Confidence scoring on each extraction
   - Source grounding preservation (every extraction links back to exact text)

5. **Quality Control**
   - High-confidence extractions (>0.85) auto-approved with spot-checking
   - Low-confidence extractions flagged for review
   - Cross-validation: Do extracted dates make sense? Are wage rates plausible?
   - How to handle contracts that span multiple PDFs or have amendments

6. **Storage & Search**
   - How extracted clauses get stored (PostgreSQL with full-text search)
   - How to make them searchable by type, geography, industry, union, date
   - How to enable "find similar clauses across contracts" (this is where vector embeddings come in later)

---

## PART 4: Cost Estimation

Based on your source research, estimate:

1. **Total contracts available** across all sources (realistic count, not aspirational)
2. **Estimated total pages** (based on average contract length from your sample inspections)
3. **Cost to process** at three scales:
   - Pilot (500 contracts)
   - Medium (5,000 contracts)
   - Full (25,000 contracts)
4. **Cost breakdown by stage**: OCR, LangExtract/LLM API calls, storage, compute
5. **Monthly ongoing costs** for maintaining the database (new contracts, reprocessing)

---

## PART 5: Priority Sequencing

Based on everything you've found, recommend:

1. **Which 3 sources to start with** and why (considering: volume, quality, accessibility, and relevance to organizers)
2. **Which 5 extraction classes to build first** and why (considering: frequency in contracts, organizer value, and extraction difficulty)
3. **What the "minimum viable contract database" looks like** — the smallest version that would be genuinely useful to a union organizer
4. **Key risks and unknowns** that could derail the project
5. **What you couldn't verify** and what follow-up research is needed

---

## PART 6: Reference Materials

### Academic foundation
- Arold, Ash, MacLeod, and Naidu, "Worker Rights in Collective Bargaining" (NBER Working Paper 33605, March 2025) — analyzed 32,402 contracts using dependency parsing of modal verbs (shall/may/shall not) to assess legal force of contract language. Their code is publicly available.
- Savelka (2023) — tested GPT-4 zero-shot on CUAD contract clauses, achieved F1=0.86 matching supervised models
- CUAD dataset — 510 contracts, 13,101 labeled clauses, 41 categories, DeBERTa-xlarge achieved 44% precision at 80% recall
- Harvey AI Contract Intelligence Benchmark (Nov 2025) — out-of-box LLMs get 65-70% on deal points, specialized systems do much better
- UC Berkeley Labor Center "Negotiating Tech" — reviewed 500+ contracts, curated provisions from 175+ agreements on technology-related contract language

### Key tools
- **LangExtract**: github.com/google/langextract — few-shot structured extraction with source grounding
- **PyMuPDF**: Free PDF text extraction for digital PDFs
- **Docling (IBM)**: 97.9% table extraction accuracy, handles PDF/DOCX/HTML through one interface
- **Mistral OCR**: ~$1/1,000 pages for scanned document OCR
- **voyage-law-2**: Legal domain embedding model, outperforms OpenAI embeddings by 6-10% on legal retrieval
- **labordata/opdr**: GitHub project with code for building a database from OLMS Public Disclosure Room data
- **ContractNLI**: Define hypotheses about contract provisions and classify whether each contract entails, contradicts, or doesn't mention them

### Existing platform infrastructure
- PostgreSQL database (olms_multiyear) with 207+ tables
- FastAPI backend with 38+ endpoints
- Crawl4AI already integrated for web scraping
- Full-text search via PostgreSQL GIN indexes
- pgvector extension available for semantic search

---

## OUTPUT FORMAT

Please organize your research as a single comprehensive document with clear sections matching the parts above. Use tables for comparing sources side-by-side. For each source, clearly mark what you verified firsthand vs. what you're reporting from secondary sources.

**Critical**: For every factual claim about a source (contract count, access method, format), include:
- The URL you checked
- The date you checked it
- Whether you were able to actually access/download a sample
- Any discrepancies from previously reported numbers

This research will be used directly to plan development work, so accuracy matters more than comprehensiveness. It's better to say "I couldn't verify this" than to report an unverified number.

---

*End of research task. This prompt was generated February 2026 for the Labor Relations Research Platform project.*
