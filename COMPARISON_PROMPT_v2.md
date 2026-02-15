# Three-Audit Comparison Prompt (Round 2)

## Instructions

I'm attaching three independent audit reports of my labor relations research platform. Each was produced by a different AI system (Claude Code, Gemini, and OpenAI Codex) using the exact same audit prompt. None of them saw each other's work.

Your job is to compare all three reports and produce a unified comparison document. Think of yourself as the senior reviewer looking at three independent inspectors' reports on the same building — your job is to figure out where they agree (high confidence), where they disagree (needs judgment), what each one uniquely caught that the others missed, and most importantly: what I should actually DO based on the combined picture.

---

## Context You Need

This is **Round 2** of this process. Round 1 happened on February 13, 2026. In Round 1:
- Claude was the most detailed (32 findings), strongest on data integrity issues and union-use perspective
- Gemini was the most strategic/forward-looking, best on new data sources and architecture — but completely missed the orphaned data problem (the biggest issue)
- Codex was the most security-focused and concise, best on systematic risk reduction — but had fewer unique analytical insights

The Round 2 audit prompt explicitly asked each auditor to check whether Round 1 issues were fixed (Section 6 of each report). So part of your comparison should cover: did they agree on what's fixed vs. still broken?

---

## What to Produce

Create TWO outputs:

### Output 1: Comparison Report (Markdown)
Save as a markdown file. Use this exact structure — don't reorganize:

---

**Part 1: How to Read This Document**
- Brief explanation of the three-blind-audit methodology
- Quick glossary of technical terms used in the reports (like "orphaned rows," "CORS," "match rate," "foreign key," "materialized view," "NAICS codes," etc.) — define every term a non-technical reader would need
- Note any limitations (e.g., if one auditor couldn't access something the others could)

**Part 2: Numbers at a Glance**
A side-by-side comparison table of the raw numbers each auditor reported:

```
| Metric | Claude | Gemini | Codex | Agreement? |
|--------|--------|--------|-------|------------|
| Total tables | ? | ? | ? | Yes/No |
| Total database size | ? | ? | ? | Yes/No |
| Total row count | ? | ? | ? | Yes/No |
| F7→OSHA match rate | ? | ? | ? | Yes/No |
| F7→NLRB match rate | ? | ? | ? | Yes/No |
| Orphaned records count | ? | ? | ? | Yes/No |
| API endpoints (total) | ? | ? | ? | Yes/No |
| Broken endpoints | ? | ? | ? | Yes/No |
| Security issues found | ? | ? | ? | Yes/No |
| Total findings | ? | ? | ? | — |
```

Where numbers disagree, note WHY (different counting method? different scope? one is wrong?).

**Part 3: Where All Three Agree (Highest Confidence)**
List every issue that all three auditors independently flagged. For each one:
- What the issue is (plain English, one paragraph)
- How each auditor described it (brief quote or paraphrase from each)
- Severity consensus (do they agree on how bad it is?)
- What it means for an organizer using the platform
- Recommended action

**Part 4: Where Two Out of Three Agree**
Same format as Part 3, but for issues flagged by exactly two auditors. Note which auditor missed it and speculate on why (did they not check that area? did they define the problem differently?).

**Part 5: Where They Disagree**
Issues where the auditors reached different conclusions about the same thing. For each:
- What the disagreement is
- Each auditor's position
- Who's probably right (and why)
- What I should do

**Part 6: Unique Catches (Only One Found It)**
Split into three sections: "Only Claude Found," "Only Gemini Found," "Only Codex Found." For each unique finding:
- What it is
- Why the others likely missed it
- How important is it really? (Sometimes a unique catch is brilliant; sometimes it's a stretch)

**Part 7: Round 1 Issue Resolution — Did They Fix Things?**
Compare what each auditor said about the 15 Round 1 issues from Section 6 of each report:

```
| Round 1 Issue | Claude Says | Gemini Says | Codex Says | Consensus |
|--------------|-------------|-------------|------------|-----------|
| Password in code | Fixed/Not | Fixed/Not | Fixed/Not | ? |
| Auth disabled | Fixed/Not | Fixed/Not | Fixed/Not | ? |
| ... | ... | ... | ... | ... |
```

Highlight any disagreements on whether something is actually fixed.

**Part 8: Delta Since Round 1**
What changed between the two audit rounds? Combine findings from all three Section 7s:
- New tables or removed tables
- Size changes
- New features or endpoints
- New problems introduced

**Part 9: Methodology Comparison**
How each auditor did their work:

```
| Aspect | Claude | Gemini | Codex |
|--------|--------|--------|-------|
| Approach (how they structured the work) | ? | ? | ? |
| Database access method | ? | ? | ? |
| Total findings | ? | ? | ? |
| Time taken (if reported) | ? | ? | ? |
| Live verification (did they run queries?) | ? | ? | ? |
| Strengths | ? | ? | ? |
| Weaknesses / blind spots | ? | ? | ? |
```

**Part 10: Unified Priority List**
This is the most important section. Combine ALL findings from all three auditors into a single ranked action plan, organized by severity:

🔴 CRITICAL — Do these first (numbered, with: issue, who flagged it, effort estimate, why it matters)
🟡 HIGH — Do before anyone else uses it
🔵 MEDIUM — Should fix but not urgent
⚪ LOW — Nice to have

Weight consensus findings higher than single-auditor findings. If all three flagged something, it goes higher than something only one caught.

**Part 11: One-Week Action Plan**
If I had 5 focused work days to address the most impactful issues, what should each day look like? Be specific:

```
Day 1: [Specific tasks] — addresses findings #X, #Y
Day 2: [Specific tasks] — addresses findings #X, #Y
...
Day 5: [Specific tasks] — addresses findings #X, #Y
```

**Part 12: What's Working Well**
Combine the positive findings from all three reports. What did each auditor call out as genuinely impressive? Where all three praised the same thing, emphasize it.

**Part 13: Key Takeaways**
5-7 bullet points summarizing the most important conclusions from the entire comparison. Write these for someone who won't read the full document.

---

### Output 2: Interactive HTML Version
After the markdown is complete, also create a polished, professional HTML version with:
- Collapsible sidebar navigation (like the Round 1 HTML comparison had)
- Color-coded badges for each auditor (Claude = blue, Gemini = green, Codex = orange)
- Severity labels styled with the emoji colors
- Clean typography, readable on mobile
- A print-friendly version (hide sidebar, remove shadows)
- Clickable section navigation
- The "Numbers at a Glance" table should be visually prominent at the top

---

## Important Rules

1. **Write everything in plain English.** When you use a technical term, explain it in parentheses the first time. Imagine the reader is a union organizer, not a software engineer.

2. **Don't just list — analyze.** The point isn't to repeat what each auditor said. It's to figure out what the TRUTH is when you combine all three perspectives.

3. **Be honest about confidence levels.** All-three-agree = very high confidence. Two-of-three = high confidence. Only-one = interesting but verify. Say this explicitly.

4. **When auditors disagree, take a position.** Don't just say "Claude says X, Gemini says Y." Say which one is probably right and why.

5. **Compare Round 1 to Round 2.** This is the second time we've done this. Note whether the same problems keep showing up, and whether the platform is trending in the right direction overall.

6. **The action plan matters most.** Parts 10 and 11 are what I'll actually use day-to-day. Make them specific and actionable.

---

## The Three Reports

[PASTE ALL THREE AUDIT REPORTS BELOW THIS LINE]
