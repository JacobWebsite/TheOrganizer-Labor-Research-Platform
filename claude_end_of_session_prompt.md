# Claude End-of-Session Update Prompt
## Paste this to Claude at the end of each work session

---

## Prompt (copy everything below this line):

```
SESSION WRAP-UP — Please do the following:

1. **Session Summary:** Write a brief plain-language summary of what we accomplished 
   this session. Include:
   - What we built, changed, or fixed
   - Any new tables, columns, or API endpoints created
   - Any data sources added or matching processes run
   - Any known issues introduced or discovered
   - Current record counts for anything that changed

2. **Update the Codex Briefing:** Based on what changed this session, tell me what 
   lines in the Codex context briefing need to be added, changed, or removed. 
   Specifically:
   - Any new tables Codex should know about
   - Any changed table structures or row counts
   - Any new code patterns being used
   - Any new known issues or broken endpoints
   - Any resolved issues that can be removed
   
   Write out the specific updated sections so I can paste them in.

3. **Update the Gemini Briefing:** Based on what changed this session, tell me what 
   lines in the Gemini research briefing need to be added, changed, or removed. 
   Specifically:
   - Any new data sources integrated or explored
   - Any changes to how we understand a government database
   - Any new platform numbers (member counts, match rates, etc.)
   - Any new research questions that came up but weren't answered
   
   Write out the specific updated sections so I can paste them in.

4. **Flag anything for next session:** List any tasks we started but didn't finish, 
   decisions that are pending, or things I should verify with Codex or Gemini before 
   we continue.

Format everything in plain language. Keep it concise — bullet points are fine here.
```

---

## How This Works

At the end of each work session with Claude, paste the prompt above. Claude will:

1. Summarize what happened (your session log)
2. Tell you exactly what to update in the Codex briefing (copy-paste ready)
3. Tell you exactly what to update in the Gemini briefing (copy-paste ready)
4. Flag anything for next time

**Time cost:** ~2 minutes of your time to paste and review.
**Benefit:** Codex and Gemini always have current project info the next time you use them.

---

## Tips

- You don't need to do this after every tiny conversation — just after sessions where 
  something meaningful changed (new data, new code, fixed bugs, new tables, etc.)
- If Claude says "no changes needed" for one of the briefings, trust that — not every 
  session affects both AIs
- Save the updated briefing files in the same place you keep the originals so you 
  always paste the latest version

---

*Last updated: February 2026*
