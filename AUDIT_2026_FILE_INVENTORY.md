# Audit 2026 — Complete File Inventory

## Location: C:\Users\jakew\Downloads\labor-data-project\audit_2026\

### Full Audit Prompts (Each AI Does All 10 Sections)
| File | AI | Pages | Focus |
|------|----|-------|-------|
| FULL_AUDIT_CLAUDE.md | Claude Code | 144 lines | Database queries, cross-references, data integrity |
| FULL_AUDIT_CODEX.md | Codex | 189 lines | Code quality, security, architecture |
| FULL_AUDIT_GEMINI.md | Gemini | 176 lines | Methodology, benchmarks, research validation |

### Focused Deep-Dive Prompts (Specialty Tasks After Full Audits)
| File | AI | Tasks |
|------|----|-------|
| FOCUSED_CLAUDE_DATABASE.md | Claude Code | Orphan mapping, dedup verification, match sampling, scoring analysis, geographic gaps |
| FOCUSED_CODEX_CODE.md | Codex | API security fixes, credential scan, matching code review, frontend review, test coverage, dependencies |
| FOCUSED_GEMINI_RESEARCH.md | Gemini | BLS benchmarks, scoring methodology, data source gaps, density methodology, scraping feasibility, comparable platforms |

### Infrastructure
| File | Purpose |
|------|---------|
| run_full_audits.ps1 | PowerShell launcher — runs audits automatically |
| README.md | Complete guide on how to use everything |
| logs/ | Where raw AI output gets saved |

### Expected Output Reports (Created BY the AIs)
| Report | Created By |
|--------|-----------|
| docs/AUDIT_REPORT_CLAUDE_2026_R3.md | Claude Code full audit |
| docs/AUDIT_REPORT_CODEX_2026_R3.md | Codex full audit |
| docs/AUDIT_REPORT_GEMINI_2026_R3.md | Gemini full audit |
| docs/ORPHAN_MAP_2026.md | Claude focused task |
| docs/MATCH_QUALITY_SAMPLE_2026.md | Claude focused task |
| docs/FOCUSED_AUDIT_CLAUDE_DATABASE.md | Claude focused task |
| docs/API_SECURITY_FIXES.md | Codex focused task |
| docs/CREDENTIAL_SCAN_2026.md | Codex focused task |
| docs/MATCHING_CODE_REVIEW.md | Codex focused task |
| docs/FRONTEND_CODE_REVIEW.md | Codex focused task |
| docs/TEST_COVERAGE_REVIEW.md | Codex focused task |
| docs/DEPENDENCY_REVIEW.md | Codex focused task |
| docs/BLS_BENCHMARK_VERIFICATION.md | Gemini focused task |
| docs/SCORING_METHODOLOGY_ASSESSMENT.md | Gemini focused task |
| docs/DATA_SOURCE_GAP_ANALYSIS.md | Gemini focused task |
| docs/DENSITY_METHODOLOGY_REVIEW.md | Gemini focused task |
| docs/SCRAPING_FEASIBILITY_CHECK.md | Gemini focused task |
| docs/COMPARABLE_PLATFORMS.md | Gemini focused task |

### Total Reports Expected: 18
