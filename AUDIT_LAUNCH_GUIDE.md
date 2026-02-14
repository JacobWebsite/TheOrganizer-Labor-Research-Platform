# How to Launch the Blind Audit on Each Tool

All three tools will read the same `BLIND_AUDIT_PROMPT.md` file, ensuring a fair comparison.

---

## 1. Gemini CLI (Google)

Open a terminal and run:

```powershell
cd C:\Users\jakew\Downloads\labor-data-project
gemini
```

Once inside, paste this:

```
Read BLIND_AUDIT_PROMPT.md and follow all instructions. Start by reading README.md, CLAUDE.md, SESSION_LOG_2026.md, LABOR_PLATFORM_ROADMAP_v13.md, and docs/METHODOLOGY_SUMMARY_v8.md. Then systematically explore the code in api/, scripts/, sql/, frontend/, files/, and tests/. If you can connect to the database, run the exploration queries. Complete all 10 audit areas, the prioritized improvements, and the union usability section. Save your report as gemini_audit_report.md
```

---

## 2. OpenAI Codex CLI

Open a terminal and run:

```powershell
cd C:\Users\jakew\Downloads\labor-data-project
codex
```

Sign in with your ChatGPT Pro account when prompted. Once inside, paste this:

```
Read BLIND_AUDIT_PROMPT.md and follow all instructions. Start by reading README.md, CLAUDE.md, SESSION_LOG_2026.md, LABOR_PLATFORM_ROADMAP_v13.md, and docs/METHODOLOGY_SUMMARY_v8.md. Then systematically explore the code in api/, scripts/, sql/, frontend/, files/, and tests/. If you can connect to the database, run the exploration queries. Complete all 10 audit areas, the prioritized improvements, and the union usability section. Save your report as codex_audit_report.md
```

---

## 3. Claude Code

Open a terminal and run:

```powershell
cd C:\Users\jakew\Downloads\labor-data-project
claude
```

Once inside, paste this:

```
Read BLIND_AUDIT_PROMPT.md and follow all instructions. Start by reading README.md, CLAUDE.md, SESSION_LOG_2026.md, LABOR_PLATFORM_ROADMAP_v13.md, and docs/METHODOLOGY_SUMMARY_v8.md. Then systematically explore the code in api/, scripts/, sql/, frontend/, files/, and tests/. If you can connect to the database, run the exploration queries. Complete all 10 audit areas, the prioritized improvements, and the union usability section. Save your report as claude_audit_report.md
```

---

## After All Three Finish

You'll have three files in your project folder:
- `gemini_audit_report.md`
- `codex_audit_report.md`  
- `claude_audit_report.md`

Bring them back here and I'll create a side-by-side comparison showing:
- Where all three **agree** (high-confidence findings)
- Where they **disagree** (needs investigation)
- **Unique catches** each tool found that the others missed
- A unified priority list combining the best recommendations from all three
