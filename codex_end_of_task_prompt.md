# Codex End-of-Task Summary Prompt
## Paste this at the end of any Codex code review session

---

## Prompt (copy everything below this line):

```
TASK SUMMARY — Before we wrap up, please give me a structured summary I can
bring back to my primary AI (Claude) who built this code.

CURRENT PLATFORM STATE (for context):
- API v7.0: 16 routers under api/routers/, entry point api/main.py
- JWT auth available (disabled by default, enabled via LABOR_JWT_SECRET env var)
- Organizing scorecard is a materialized view (mv_organizing_scorecard) with 9
  scoring factors computed in SQL. Wrapper view v_organizing_scorecard adds total score.
  Admin refresh via POST /api/admin/refresh-scorecard (uses REFRESH CONCURRENTLY).
- 113,713 employers in f7_employers_deduped (61K current + 53K historical)
- 63 tests passing (47 API + 16 auth). Run: py -m pytest tests/
- Match rates: OSHA 13.7%, WHD 6.8%, 990 2.4%
- Sprints 1-3 complete. Sprint 4 (test coverage) is next.

Use this exact format:

## Codex Review Summary

**What I reviewed:** [One sentence describing the code/task]

**Verdict:** [LOOKS GOOD / MINOR ISSUES / SIGNIFICANT CONCERNS]

**Issues found:**
- [List each issue with: what's wrong, why it matters, suggested fix]
- [If no issues: "No issues found"]

**Edge cases to watch:**
- [List inputs or situations that could break this code]
- [If none: "No obvious edge cases"]

**Performance notes:**
- [Will this be slow on large tables? Missing indexes? Unnecessary queries?]
- [Key table sizes: osha_violations 2.2M, osha_establishments 1M, f7_employers 114K, scorecard MV 25K]
- [If fine: "No performance concerns for the described data sizes"]

**Things I couldn't verify:**
- [Anything that depends on project context I don't have]
- [Assumptions I had to make about the database or data]

**Test impact:**
- [Does this change require new tests? Do existing tests need updating?]
- [Are there edge cases that should be tested?]

**Recommended action:** [SHIP AS-IS / FIX THEN SHIP / NEEDS RETHINK]

Keep it concise. I'll paste this directly to Claude so it can address your points.
```

---

## How This Works

After Codex finishes reviewing code, paste this prompt. It produces a clean summary 
in a consistent format that:

1. Tells Claude exactly what Codex thought (verdict + details)
2. Lists specific issues Claude needs to address
3. Flags things Codex couldn't check (because it doesn't have full context)
4. Gives a clear recommendation

**Then take the output and paste it into Claude using this template:**

```
I had Codex review the [WHAT] code. Here's its summary:

[PASTE CODEX SUMMARY]

Can you address each point? For any disagreements, explain your reasoning.
```

---

## Why This Format Matters

Without a structured summary, you'd get a wall of text from Codex that's hard to 
act on. This format gives you:

- A quick verdict at the top (so you know if it's urgent)
- Specific issues (so Claude can fix them one by one)
- Honest limitations (Codex admitting what it can't check)
- Test impact (so new code stays covered by the test suite)
- A clear recommendation (so you know what to do next)

Think of it like getting a home inspection report — you want specific findings 
in a standard format, not a rambling description of the house.

---

*Last updated: February 14, 2026 (after Sprint 3 completion)*
