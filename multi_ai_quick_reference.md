# Multi-AI Quick Reference Card
## Which AI Do I Use Right Now?

---

## Decision Flowchart

**Am I building, changing, or debugging something?** → **Claude**
**Am I checking if code is correct?** → **Codex**
**Am I looking something up or verifying a fact?** → **Gemini**

---

## Task Routing Table

| I need to... | Use | Why |
|-------------|-----|-----|
| Add a new data source to the platform | Claude | Needs full project context |
| Review code Claude just wrote | Codex | Fresh eyes catch bugs |
| Research what a government database contains | Gemini | Research strength |
| Fix a broken API endpoint | Claude | Needs to understand the codebase |
| Check if a SQL query will work correctly | Codex | Quick syntax/logic check |
| Summarize a long government report | Gemini | Document summarization |
| Match employers across databases | Claude | Complex multi-step work |
| Verify a claim about how NLRB filings work | Gemini | Fact-checking |
| Design a new feature | Claude | Architecture decisions |
| Double-check matching threshold logic | Codex | Code review |
| Find out if a bulk data download exists | Gemini | Web research |
| Run database updates on thousands of records | Claude | Needs checkpoint approach |
| Understand an error message | Codex or Claude | Either works |
| Compare two technical approaches | Gemini (research) then Claude (decision) | Two-step |

---

## Copy-Paste Templates

### Sending Claude's Code to Codex
```
Claude wrote the following code for my labor relations research platform. 
It's supposed to [WHAT IT DOES IN ONE SENTENCE].

The database is PostgreSQL with tables including [RELEVANT TABLES].
Key columns: [LIST IMPORTANT COLUMNS].

Can you review the logic and tell me:
1. Are there any bugs?
2. What edge cases might break this?
3. Any performance concerns for large datasets (1M+ rows)?

Here's the code:
[PASTE CODE]
```

### Asking Gemini to Fact-Check
```
I'm building a research platform that integrates U.S. government labor data
(OLMS, NLRB, OSHA, WHD, SEC EDGAR, USASpending, etc.).

Claude told me that [SPECIFIC CLAIM].

Is this accurate? Are there any important exceptions or nuances?
If possible, point me to the official documentation that confirms this.
```

### Reporting Codex Feedback to Claude
```
I had Codex review the [WHAT] code you wrote. Here's what it said:

[PASTE CODEX RESPONSE OR KEY POINTS]

Can you explain whether you agree with these points?
If there's a disagreement, can we test both approaches on a small sample?
```

### Reporting Gemini Research to Claude
```
I asked Gemini about [TOPIC] and here's what it found:

[PASTE KEY FINDINGS]

Does this change our approach? Should we adjust anything based on this?
```

### Asking Claude to Resolve a Disagreement
```
I got different answers from two sources:

Claude said: [WHAT CLAUDE SAID]
Codex/Gemini said: [WHAT THE OTHER SAID]

Can you explain the difference and which approach is better for our 
specific situation? If it's unclear, can we test both on a small dataset?
```

---

## Setup Checklist

Before first use, make sure each AI has its context document:

- [ ] **Codex** — Paste `codex_context_briefing.md` at the start of the session
- [ ] **Gemini** — Paste `gemini_context_briefing.md` at the start of the session  
- [ ] **Claude** — Has project context built in (through this Project); use `claude_session_starter.md` for new standalone conversations outside this project

---

## The Verification Rule

**For any change that affects more than 100 database records:**
1. Claude writes and explains the code
2. Copy the key logic to Codex for review
3. If it involves government data assumptions, check with Gemini
4. Report findings back to Claude
5. Claude adjusts if needed, then runs on a small test set
6. Review results → full run

**For quick tasks (< 100 records, no complex logic):**
Just use whichever AI fits — no verification loop needed.

---

## When Things Go Wrong

| Problem | What To Do |
|---------|-----------|
| Codex and Claude disagree on code logic | Ask Claude to test both approaches on 10-20 records |
| Gemini says a government database works differently than Claude assumed | Share the info with Claude — may need to adjust the integration approach |
| Code runs but results look wrong | Send the code AND sample output to Codex: "This returned X but I expected Y" |
| Not sure which AI to ask | Default to Claude — it can redirect you if another AI would be better |
| AI gives a confident but suspicious answer | Cross-check with a different AI — confidence ≠ accuracy |

---

*Keep this open during work sessions for quick reference.*
*Last updated: February 2026*
