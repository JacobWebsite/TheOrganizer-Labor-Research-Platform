# Gemini End-of-Task Summary Prompt
## Paste this at the end of any Gemini research or fact-checking session

---

## Prompt (copy everything below this line):

```
RESEARCH SUMMARY — Before we wrap up, please give me a structured summary I can
bring back to my primary AI (Claude) who is building the platform.

CURRENT PLATFORM STATE (for context on what we've already built):
- 113,713 employers tracked (61K current + 53K historical), 26,665 unions, 14.5M members
- Data sources integrated: OLMS LM filings, F-7 employer notices, NLRB elections,
  OSHA enforcement, WHD wage theft, BLS/EPI, SEC EDGAR, USASpending, SAM.gov,
  QCEW, IRS Form 990, Mergent Intellect, GLEIF
- Match rates (employer matching across databases): OSHA 13.7%, WHD 6.8%, 990 2.4%
- Key data gaps: SEC EDGAR full index (300K+), IRS BMF (all nonprofits),
  SEC 10-K Exhibit 21 (subsidiary lists), state labor board data
- Sprints 1-3 complete. Currently planning Sprint 4 (test coverage).

Use this exact format:

## Gemini Research Summary

**Topic researched:** [One sentence describing what I asked about]

**Key findings:**
- [Most important facts, in plain language]
- [Include specific data formats, URLs, or identifiers when relevant]

**What was confirmed:**
- [Claims or assumptions I asked you to verify that turned out correct]

**What was wrong or needs correction:**
- [Claims that turned out inaccurate, with the correct information]
- [If everything checked out: "All claims verified as accurate"]

**Important nuances:**
- [Exceptions, edge cases, or "it depends" situations]
- [Things that are technically true but misleading without context]

**Gaps in my knowledge:**
- [Things I wasn't sure about and you should verify directly]
- [Information that may have changed since my training data]

**Actionable for the platform:**
- [Specific things Claude should know that affect how the platform is built]
- [New data sources discovered, API endpoints found, format details, etc.]
- [Could this improve our match rates? (Currently: OSHA 13.7%, WHD 6.8%, 990 2.4%)]

**Sources:**
- [Links to official documentation, government pages, or authoritative references]

Keep it concise and factual. I'll paste this directly to Claude so it can 
adjust the platform based on your findings.
```

---

## How This Works

After Gemini finishes a research or fact-checking task, paste this prompt. It produces 
a clean summary that:

1. Confirms or corrects what Claude told you
2. Highlights nuances that could affect the build
3. Admits what Gemini isn't sure about (so you can verify independently)
4. Gives Claude actionable information to work with

**Then take the output and paste it into Claude using this template:**

```
I asked Gemini to research [TOPIC]. Here's what it found:

[PASTE GEMINI SUMMARY]

Does this change our approach? Should we adjust anything?
```

---

## Common Uses

**Verifying a data source:** "Gemini, Claude says the SEC EDGAR full-text search API
is at efts.sec.gov and returns results by CIK number. Confirm this and tell me what
other search parameters are available."

**Researching a new integration:** "Gemini, I'm thinking about adding FLRA data to my
platform. What data does FLRA publish? Is it available for bulk download? What format
is it in?"

**Fact-checking a methodology:** "Gemini, Claude says we can match companies between
databases using EIN (Employer Identification Number). How reliable is EIN as a matching
key? Do companies have multiple EINs? Do EINs ever change?"

**Understanding a government process:** "Gemini, when does an NLRB election petition
get filed versus when does the actual election happen? What's the typical timeline?
Are there steps in between that generate data we could capture?"

**Improving match rates:** "Gemini, we currently match OSHA establishments to our
employer list at 13.7%. What additional identifiers or data sources could help us
improve this? Does OSHA publish EINs or DUNS numbers anywhere?"

**Evaluating data gaps:** "Gemini, we want to ingest the IRS Business Master File
to get all nonprofit EINs. How is the BMF structured? What fields does it include?
How often is it updated? Where can we download it?"

---

*Last updated: February 14, 2026 (after Sprint 3 completion)*
