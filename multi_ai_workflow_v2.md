# Multi-AI Workflow Guide v2
## How to Route Tasks Between Claude, Codex, and Gemini — With Feedback Loops

---

## The Basic Idea

Think of this like a team:

- **Claude** = Your general contractor. Does the heavy lifting, builds things, solves complex problems.
- **Codex** = Your code inspector. Reviews Claude's work and catches bugs.
- **Gemini** = Your research analyst. Verifies facts and finds new information.

What makes this work isn't just using three AIs — it's the **feedback loop**. Each AI's output feeds into the others, so the whole system gets smarter over time.

---

## The Files You Need

You should have these 7 files saved somewhere easy to access:

| File | What It Does | When You Use It |
|------|-------------|-----------------|
| `codex_context_briefing.md` | Tells Codex about your project | Paste at the START of any Codex session |
| `gemini_context_briefing.md` | Tells Gemini about your project | Paste at the START of any Gemini session |
| `claude_session_starter.md` | Tells Claude about your project | Paste when starting a NEW Claude conversation (not needed in the Project) |
| `multi_ai_quick_reference.md` | Which AI to use for what | Keep open during work sessions |
| `claude_end_of_session_prompt.md` | Gets Claude to update the other briefings | Paste at the END of Claude sessions |
| `codex_end_of_task_prompt.md` | Gets Codex to write a summary for Claude | Paste at the END of Codex sessions |
| `gemini_end_of_task_prompt.md` | Gets Gemini to write a summary for Claude | Paste at the END of Gemini sessions |

---

## How the Feedback Loop Works

Here's the cycle, explained simply:

```
    ┌──────────────────────────────────────────────┐
    │                                              │
    │   1. CLAUDE builds something                 │
    │      ↓                                       │
    │   2. You send the code to CODEX              │
    │      ↓                                       │
    │   3. CODEX reviews it → writes a summary     │
    │      ↓                                       │
    │   4. You paste that summary back to CLAUDE    │
    │      ↓                                       │
    │   5. CLAUDE addresses the feedback            │
    │      ↓                                       │
    │   6. At end of session, CLAUDE updates        │
    │      the Codex and Gemini briefings           │
    │      ↓                                       │
    │   7. Next time you use Codex or Gemini,       │
    │      they have current project info           │
    │                                              │
    └──────────────────────────────────────────────┘
```

The same cycle works with Gemini for research:

```
    ┌──────────────────────────────────────────────┐
    │                                              │
    │   1. CLAUDE makes a claim about a data source│
    │      ↓                                       │
    │   2. You ask GEMINI to verify it             │
    │      ↓                                       │
    │   3. GEMINI researches → writes a summary    │
    │      ↓                                       │
    │   4. You paste that summary back to CLAUDE   │
    │      ↓                                       │
    │   5. CLAUDE adjusts the approach if needed   │
    │      ↓                                       │
    │   6. At end of session, CLAUDE updates       │
    │      the briefings with new knowledge        │
    │                                              │
    └──────────────────────────────────────────────┘
```

**Why this matters:** Without the feedback loop, each AI starts from scratch every time. With it, the briefing documents act like a shared team notebook that gets better with each session.

---

## When to Use Each AI

### Claude (Primary — The Workhorse)

Use Claude for anything that requires building, designing, or thinking through multi-step problems:

- Writing code for database updates, data processing, or new features
- Designing how to integrate a new data source (like OSHA, SEC, NLRB)
- Matching employers across different government databases
- Running complex queries or building reports
- Strategic planning — figuring out *what* to build and *why*
- Writing documentation or workflow guides
- Debugging problems when something breaks
- Any task that requires back-and-forth conversation to get right

**Why Claude for these:** These tasks need context about your whole project — what's already built, how the pieces connect, what's been tried before.

---

### Codex (Verification & Code Tasks)

Use Codex when you want a second opinion on code, or for quick standalone coding tasks:

- **Verify Claude's code** — Paste code Claude wrote and ask: "Does this logic make sense? Any bugs?"
- **Quick scripts** — Small, self-contained tasks like "write a script that converts this CSV to JSON"
- **Code explanations** — If Claude explained something and you want a simpler take, ask Codex
- **Syntax checks** — "Is this SQL query correct?"

**Why Codex for these:** It's a strong second set of eyes for catching logic errors. But it doesn't know your project's full context the way Claude does.

**Always paste `codex_context_briefing.md` first** so it knows your database structure and code patterns.

---

### Gemini (Research, Summarization & Quick Questions)

Use Gemini for information gathering, document analysis, and quick factual lookups:

- **Summarize documents** — "Summarize this 50-page PDF about NLRB filing procedures"
- **Research questions** — "What data does the SEC EDGAR system actually contain?"
- **Fact-checking** — "Is it true that FLRA covers federal employees differently than NLRA?"
- **Compare options** — "What are the pros and cons of matching by EIN vs. DUNS?"
- **Verify Claude's claims** — If Claude says something about a government database, ask Gemini to confirm

**Why Gemini for these:** Strong at pulling together information from many sources and giving clear summaries.

**Always paste `gemini_context_briefing.md` first** so it knows your data sources and terminology.

---

## Standard Workflows

### Big Task (New Feature or Data Integration)

1. **Plan with Claude** — Describe what you want. Claude breaks it into steps.
2. **Claude builds it** — Code gets written, explained, tested on small sample.
3. **Send key code to Codex** — Paste the logic with context. Use the copy-paste template.
4. **Ask Gemini if needed** — If the task involves assumptions about government data, verify them.
5. **Paste summaries back to Claude** — Use Codex/Gemini end-of-task summaries.
6. **Claude adjusts and runs** — Fixes any issues, runs the final version.
7. **End-of-session update** — Paste the Claude end-of-session prompt. Claude updates briefings.
8. **Save updated briefings** — Replace your saved copies with the new versions.

### Quick Task (Lookup, Small Fix, Fact Check)

Just go to the right AI directly — no feedback loop needed for small stuff:

| Task | Go To |
|------|-------|
| "Summarize this report" | Gemini |
| "Fix this small bug" | Codex |
| "What does this error mean?" | Codex or Claude |
| "What database tracks federal contracts?" | Gemini |
| "Add a new column to my table" | Claude |
| "Is this SQL query correct?" | Codex |

---

## Handling Disagreements

1. **Don't just go with whoever sounds more confident.** AIs can be very confident and very wrong.
2. **Bring the disagreement back to Claude** with specifics from the other AI's summary.
3. **Look for the reasoning, not just the answer.** The AI that explains *why* with project-specific details is usually right.
4. **When in doubt, test both approaches** on a small sample. Claude can run both and show you results.

---

## End-of-Session Checklist

At the end of a meaningful work session (not every tiny conversation):

- [ ] Paste the **Claude end-of-session prompt**
- [ ] Review Claude's session summary
- [ ] Copy the updated Codex briefing sections → update your saved `codex_context_briefing.md`
- [ ] Copy the updated Gemini briefing sections → update your saved `gemini_context_briefing.md`
- [ ] Note any pending items for next session

At the end of a Codex or Gemini task:

- [ ] Paste the appropriate **end-of-task prompt** (Codex or Gemini version)
- [ ] Copy the structured summary
- [ ] Paste it to Claude in your next session (or immediately if the session is still active)

---

## What NOT to Do

- **Don't give Codex or Gemini long multi-step projects.** They don't have full context. That's Claude's job.
- **Don't skip verification on important changes.** If Claude is about to modify thousands of records, spend 5 minutes getting Codex to review the logic.
- **Don't copy-paste between AIs without context.** Always include a sentence about what the code is supposed to do.
- **Don't forget the end-of-session updates.** The briefings get stale fast if you skip this.
- **Don't assume all three will agree.** They won't. That's the whole point.

---

*Last updated: February 2026*
