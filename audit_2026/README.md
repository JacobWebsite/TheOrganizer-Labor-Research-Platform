# Audit 2026 — How Everything Works
## February 16, 2026

---

## What's In This Folder

This folder contains everything needed to run a full platform audit using three different AI systems, then drill into specific areas with focused tasks.

### Files

| File | What It Is |
|------|-----------|
| **FULL_AUDIT_CLAUDE.md** | Complete audit prompt for Claude Code — all 10 sections, tailored to Claude's strengths (database queries, cross-system analysis) |
| **FULL_AUDIT_CODEX.md** | Complete audit prompt for Codex — all 10 sections, tailored to Codex's strengths (code quality, security, architecture) |
| **FULL_AUDIT_GEMINI.md** | Complete audit prompt for Gemini — all 10 sections, tailored to Gemini's strengths (methodology, research, benchmarks) |
| **FOCUSED_CLAUDE_DATABASE.md** | Deep-dive tasks for Claude: orphan chains, dedup verification, match sampling, scoring analysis, geographic gaps |
| **FOCUSED_CODEX_CODE.md** | Deep-dive tasks for Codex: API security line-by-line, credential scan, matching code review, frontend architecture, test coverage, dependencies |
| **FOCUSED_GEMINI_RESEARCH.md** | Deep-dive tasks for Gemini: BLS verification, scoring methodology, data source gaps, density methodology, scraping feasibility, comparable platforms |
| **run_full_audits.ps1** | PowerShell script that automatically sends prompts to each AI and saves the output |
| **README.md** | This file |
| **logs/** | Where the raw AI output gets saved during runs |

---

## How To Run The Audits

### Option 1: Run Everything Automatically (Easiest)

Open PowerShell, navigate to the project, and run:

```powershell
cd C:\Users\jakew\Downloads\labor-data-project
.\audit_2026\run_full_audits.ps1
```

This sends the full audit prompt to Gemini first, then Codex, then Claude Code. Each one reads the project files, connects to the database, and writes a report. Total time: roughly 30-60 minutes.

### Option 2: Run One AI At A Time

If you want to run them one by one (recommended for the first time, so you can check each result):

```powershell
# Run just Gemini
.\audit_2026\run_full_audits.ps1 -AuditTarget "gemini"

# Run just Codex
.\audit_2026\run_full_audits.ps1 -AuditTarget "codex"

# Run just Claude Code
.\audit_2026\run_full_audits.ps1 -AuditTarget "claude"
```

### Option 3: Run The Focused Deep-Dives (After Full Audits)

Once all three full audits are done, run the focused tasks:

```powershell
.\audit_2026\run_full_audits.ps1 -AuditTarget "focused"
```

This sends each AI their specialty deep-dive prompt.

### Option 4: Manual (Copy-Paste)

If the script doesn't work or you prefer manual control:

1. Open Gemini CLI: `gemini` then paste the contents of FULL_AUDIT_GEMINI.md
2. Open Codex: `codex` in the project directory, then paste FULL_AUDIT_CODEX.md
3. Open Claude Code: `claude` in the project directory, then paste FULL_AUDIT_CLAUDE.md

---

## What Each AI Is Best At

### Full Audits (Everyone Does All 10 Sections)

Every AI covers the same 10 sections so you get three independent opinions on the full system. But each AI has sections marked with ⭐ where they go deepest:

| Section | Claude Code ⭐ | Codex ⭐ | Gemini ⭐ |
|---------|--------------|---------|----------|
| 1. Database Inventory | ⭐ Runs actual queries | Checks schema | Verifies claims |
| 2. Data Quality | ⭐ Column-by-column analysis | Checks for code issues | Cross-references |
| 3. Views & Indexes | ⭐ Tests every view | Reviews SQL | Validates approach |
| 4. Cross-References | ⭐ Traces all connections | Checks code paths | Validates methodology |
| 5. API Endpoints | Tests responses | ⭐ Line-by-line code review | Checks documentation |
| 6. Scripts & Files | Reads database refs | ⭐ Architecture assessment | Checks for dead code |
| 7. Documentation | Verifies counts | Checks code matches docs | ⭐ Fact-checks everything |
| 8. Frontend | Checks API connections | ⭐ Code quality review | Checks UX claims |
| 9. Security | Tests auth | ⭐ Vulnerability scan | Checks best practices |
| 10. Summary | Data-backed recommendations | Code-focused recommendations | ⭐ Research-backed recommendations |

### Focused Tasks (Specialists Go Deep)

| AI | Focused Deep-Dive | Reports Created |
|----|-------------------|----------------|
| **Claude Code** | Database integrity: orphan mapping, dedup verification, match quality sampling, scoring distribution, geographic gaps | ORPHAN_MAP, MATCH_QUALITY_SAMPLE, FOCUSED_AUDIT_CLAUDE_DATABASE |
| **Codex** | Code quality: API security fixes, credential scan, matching code review, frontend architecture, test coverage, dependencies | API_SECURITY_FIXES, CREDENTIAL_SCAN, MATCHING_CODE_REVIEW, FRONTEND_CODE_REVIEW, TEST_COVERAGE_REVIEW, DEPENDENCY_REVIEW |
| **Gemini** | Research validation: BLS benchmarks, scoring methodology, data source gaps, density methodology, scraping feasibility, comparable platforms | BLS_BENCHMARK_VERIFICATION, SCORING_METHODOLOGY_ASSESSMENT, DATA_SOURCE_GAP_ANALYSIS, DENSITY_METHODOLOGY_REVIEW, SCRAPING_FEASIBILITY_CHECK, COMPARABLE_PLATFORMS |

---

## After The Audits: How To Compare

All three full audit reports use the same structure:
- **Severity labels:** CRITICAL / HIGH / MEDIUM / LOW
- **Numbered findings:** Finding 1.1, 1.2, etc.
- **Confidence levels:** Verified / Likely / Possible

To compare, look for:
1. **Things all three agree on** — these are almost certainly real issues
2. **Things two agree and one disagrees on** — investigate the disagreement
3. **Things only one found** — could be a real insight the others missed, or could be wrong
4. **Different numbers for the same thing** — check which population each measured (this happened last time with OSHA match rates)

---

## Troubleshooting

**"gemini: command not found"**
→ Run: `npm install -g @google/gemini-cli`

**"codex: command not found"**
→ Run: `npm install -g @openai/codex`

**"claude: command not found"**
→ Install from: https://docs.anthropic.com/en/docs/claude-code

**Script won't run (execution policy)**
→ Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**AI takes too long or hangs**
→ Press Ctrl+C to cancel, then run that AI individually

**AI doesn't write the report file**
→ Check the log file in audit_2026/logs/ — the full output is saved there regardless

**AI says it can't connect to database**
→ Make sure PostgreSQL is running. Check with: `pg_isready -U postgres`
