# Research Agent — Evaluation Scorecard Template

**Instructions:** Complete one of these for each test run. Takes ~10-15 minutes.
Save completed scorecards in this file, appending below the template.

---

## Run Evaluation

| Field | Value |
|-------|-------|
| **Company** | |
| **Run ID** | |
| **Date** | |
| **Duration (seconds)** | |
| **Industry (NAICS)** | |
| **Company type** | public / private / nonprofit |
| **Size bucket** | small / medium / large |

### Section A: Tool Performance

Rate each tool that ran. "Found data" = auto-logged. "Usefulness" = your judgment.

| Tool | Found Data? | Usefulness (H/M/L) | Notes |
|------|-------------|---------------------|-------|
| search_osha | | | |
| search_nlrb | | | |
| search_whd | | | |
| search_sec | | | |
| search_sam | | | |
| search_990 | | | |
| search_contracts | | | |
| search_mergent | | | |
| get_industry_profile | | | |
| get_similar_employers | | | |
| web_search (Gemini grounding) | | | |

**Tools correctly skipped?** (Did the agent skip tools that don't apply — e.g., SEC for nonprofits, 990 for for-profits?)
> 

**Tools that SHOULD have been skipped but weren't?**
> 

**Tools that SHOULD have run but didn't?**
> 

### Section B: Fact Accuracy

Check 5-6 key facts. Focus on surprising claims, web-sourced data, and name-matched results.

| # | Fact from Dossier | Section | Source Tool | Correct? | Issue |
|---|-------------------|---------|-------------|----------|-------|
| 1 | | | | ✅ / ❌ / ⚠️ | |
| 2 | | | | ✅ / ❌ / ⚠️ | |
| 3 | | | | ✅ / ❌ / ⚠️ | |
| 4 | | | | ✅ / ❌ / ⚠️ | |
| 5 | | | | ✅ / ❌ / ⚠️ | |
| 6 | | | | ✅ / ❌ / ⚠️ | |

**Accuracy rate:** ___ of 6 correct

**Pattern of errors (if any):**
> (e.g., "Name matching pulled in wrong company's OSHA data," or "Web search facts were outdated")

### Section C: Assessment Quality

| Dimension | Score (1-5) | Notes |
|-----------|-------------|-------|
| **Actionability** — could an organizer use this? | | |
| **Accuracy** — does the assessment match the data? | | |
| **Completeness** — are the key questions answered? | | |

**Assessment average:** ___ / 5

**Biggest gap in the dossier — what's the one thing an organizer would want that's missing?**
> 

### Section D: Overall Judgment

| Question | Answer |
|----------|--------|
| **Overall quality (1-10)** | |
| **Would you give this to an organizer as-is?** | Yes / Yes with caveats / No |
| **Prompt change needed?** | Yes / No |
| **If yes, what should change?** | |
| **Name matching issues?** | Yes / No |
| **If yes, describe:** | |

### Section E: Comparison Notes (fill in after Wave 2+)

**How does this compare to similar runs?**
> (e.g., "Much better than the Montefiore run — 990 tool worked well here but missed revenue there")

**Emerging patterns across runs:**
> (e.g., "Web search consistently adds the most value for recent organizing activity that's not in NLRB yet")

---
