# Multi-AI Workflow Guide
## How to Route Tasks Between Claude, Codex, and Gemini

---

## The Basic Idea

Think of this like a team:

- **Claude** = Your general contractor. Does the heavy lifting, builds things, solves complex problems.
- **Codex & Gemini** = Your inspectors and second opinions. They check Claude's work and handle quick side jobs.

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

**Why Claude for these:** These tasks need context about your whole project — what's already built, how the pieces connect, what's been tried before. Claude carries that context across conversations.

---

### Codex (Verification & Code Tasks)

Use Codex when you want a second opinion on code, or for quick standalone coding tasks:

- **Verify Claude's code** — Paste code Claude wrote and ask: "Does this logic make sense? Any bugs?"
- **Quick scripts** — Small, self-contained tasks like "write a script that converts this CSV to JSON"
- **Code explanations** — If Claude explained something and you want a simpler take, ask Codex
- **Syntax checks** — "Is this SQL query correct?"

**Why Codex for these:** Codex is built specifically for code. It's a strong second set of eyes for catching logic errors or suggesting cleaner approaches. But it doesn't know your project's full context the way Claude does.

---

### Gemini (Research, Summarization & Quick Questions)

Use Gemini for information gathering, document analysis, and quick factual lookups:

- **Summarize documents** — "Summarize this 50-page PDF about NLRB filing procedures"
- **Research questions** — "What data does the SEC EDGAR system actually contain?"
- **Fact-checking** — "Is it true that FLRA covers federal employees differently than NLRA?"
- **Compare options** — "What are the pros and cons of PostgreSQL vs. MySQL for this kind of project?"
- **Verify Claude's claims** — If Claude says something about how a government database works, ask Gemini to confirm

**Why Gemini for these:** Gemini is strong at pulling together information from many sources and giving clear summaries. It's great for the research side of your work.

---

## The Standard Workflow (Step by Step)

### For Big Tasks (New Features, Data Integrations, Complex Analysis)

**Step 1: Plan with Claude**
Describe what you want. Claude will break it into steps, explain the approach in plain language, and ask for your approval before doing anything.

> Example: "I want to start pulling SEC EDGAR data for the top 500 employers in our database."

**Step 2: Claude builds it**
Claude writes the code, explains what each piece does, and tests it on a small sample first.

**Step 3: Verify with Codex or Gemini**
Copy the key parts of what Claude built and ask one of the others to review:

> To Codex: "Claude wrote this Python script to match SEC filings to our employer list. Does the matching logic look correct? Any edge cases it might miss?"

> To Gemini: "Claude says SEC EDGAR organizes companies by CIK number and we can match by EIN. Is that accurate? Are there other identifiers we should use?"

**Step 4: Report back to Claude**
Tell Claude what the others said. If there's a disagreement, Claude will explain its reasoning so you can decide.

**Step 5: Claude makes adjustments and runs it**
After any needed fixes, Claude runs the final version and validates the results.

---

### For Quick Tasks (Lookups, Summaries, Small Fixes)

Just go directly to whichever AI fits best:

| Task | Go To |
|------|-------|
| "Summarize this report" | Gemini |
| "Fix this small bug in my script" | Codex |
| "What does this error message mean?" | Codex or Claude |
| "What government database tracks federal contracts?" | Gemini |
| "Add a new column to my database table" | Claude |
| "Is this SQL query doing what I think it does?" | Codex |
| "Explain what an API is" | Any of them |

---

## Handling Disagreements Between AIs

This will happen. Here's what to do:

**1. Don't just go with whoever sounds more confident.**
AIs can be very confident and very wrong at the same time.

**2. Bring the disagreement back to Claude.**
Say something like: "Codex says we should use fuzzy matching with a 0.8 threshold, but you used 0.85. Why did you choose that?"

**3. Look for the reasoning, not just the answer.**
The AI that can explain *why* its approach is better — with specifics about your project — is usually right.

**4. When in doubt, test both approaches on a small sample.**
Claude can run both versions on a handful of records so you can see which one actually works better with your data.

---

## What NOT to Do

- **Don't give Codex or Gemini long multi-step projects.** They don't have the context of your full platform. That's Claude's job.

- **Don't skip verification on important changes.** If Claude is about to modify thousands of records in your database, spend the 5 minutes to have Codex or Gemini double-check the logic.

- **Don't copy-paste between AIs without context.** When you send Claude's code to Codex for review, include a sentence about what it's supposed to do. "This script matches OSHA establishments to our employer table using name and address" is enough.

- **Don't assume all three will give the same answer.** They won't. That's the whole point — different perspectives catch different problems.

---

## Quick Reference: Copy-Paste Prompts

### When verifying Claude's code with Codex:
> "Claude wrote the following code for my labor relations research platform. It's supposed to [describe what it does]. Can you review the logic and tell me if there are any bugs, edge cases, or improvements? Here's the code: [paste code]"

### When fact-checking with Gemini:
> "I'm building a research platform that integrates government labor data. Claude told me that [claim]. Is this accurate? Are there any nuances or exceptions I should know about?"

### When reporting back to Claude:
> "I had Codex review the matching script you wrote. It flagged [issue]. Can you explain your reasoning and whether we should change anything?"

---

*Last updated: February 2026*
