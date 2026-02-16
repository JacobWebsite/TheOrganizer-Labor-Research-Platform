# ============================================================
# AUDIT LAUNCHER — Runs Full Audits via Claude Code, Codex, and Gemini
# Labor Relations Research Platform
# February 2026
#
# WHAT THIS DOES:
# Sends the full audit prompt to each AI one at a time.
# Each AI reads the prompt file, audits the project, and
# writes its report to the docs/ folder.
#
# HOW TO USE:
# 1. Open PowerShell
# 2. cd C:\Users\jakew\Downloads\labor-data-project
# 3. .\audit_2026\run_full_audits.ps1
#
# Or run individual AIs:
#   .\audit_2026\run_full_audits.ps1 -AuditTarget "gemini"
#   .\audit_2026\run_full_audits.ps1 -AuditTarget "codex"
#   .\audit_2026\run_full_audits.ps1 -AuditTarget "claude"
# ============================================================

param(
    [string]$AuditTarget = "all"
)

$ProjectDir = "C:\Users\jakew\Downloads\labor-data-project"
$AuditDir = "$ProjectDir\audit_2026"
$LogDir = "$AuditDir\logs"

# Create log directory
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LABOR PLATFORM AUDIT LAUNCHER" -ForegroundColor Cyan
Write-Host "  $timestamp" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------
# GEMINI — Full Audit
# -----------------------------------------------------------
function Run-GeminiAudit {
    Write-Host "[GEMINI] Starting full audit..." -ForegroundColor Yellow
    Write-Host "[GEMINI] Reading prompt from: $AuditDir\FULL_AUDIT_GEMINI.md" -ForegroundColor Gray
    Write-Host "[GEMINI] This may take 5-15 minutes..." -ForegroundColor Gray
    Write-Host ""

    $promptContent = Get-Content "$AuditDir\FULL_AUDIT_GEMINI.md" -Raw

    $logFile = "$LogDir\gemini_full_audit_$timestamp.log"

    # Gemini CLI: -p for non-interactive, -y to auto-approve file reads, -o text for plain output
    gemini -p $promptContent -y -o text 2>&1 | Tee-Object -FilePath $logFile

    Write-Host ""
    Write-Host "[GEMINI] Audit complete. Log saved to: $logFile" -ForegroundColor Green
    Write-Host "[GEMINI] Report should be at: $ProjectDir\docs\AUDIT_REPORT_GEMINI_2026_R3.md" -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------
# CODEX — Full Audit
# -----------------------------------------------------------
function Run-CodexAudit {
    Write-Host "[CODEX] Starting full audit..." -ForegroundColor Yellow
    Write-Host "[CODEX] Reading prompt from: $AuditDir\FULL_AUDIT_CODEX.md" -ForegroundColor Gray
    Write-Host "[CODEX] This may take 10-30 minutes..." -ForegroundColor Gray
    Write-Host ""

    $promptContent = Get-Content "$AuditDir\FULL_AUDIT_CODEX.md" -Raw

    $logFile = "$LogDir\codex_full_audit_$timestamp.log"

    # Codex CLI: exec for non-interactive, --full-auto for sandboxed auto-approval, -C for project dir
    codex exec $promptContent --full-auto -C $ProjectDir --skip-git-repo-check 2>&1 | Tee-Object -FilePath $logFile

    Write-Host ""
    Write-Host "[CODEX] Audit complete. Log saved to: $logFile" -ForegroundColor Green
    Write-Host "[CODEX] Report should be at: $ProjectDir\docs\AUDIT_REPORT_CODEX_2026_R3.md" -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------
# CLAUDE CODE — Full Audit
# -----------------------------------------------------------
function Run-ClaudeAudit {
    Write-Host "[CLAUDE] Starting full audit..." -ForegroundColor Yellow
    Write-Host "[CLAUDE] Reading prompt from: $AuditDir\FULL_AUDIT_CLAUDE.md" -ForegroundColor Gray
    Write-Host "[CLAUDE] This may take 10-30 minutes..." -ForegroundColor Gray
    Write-Host ""

    $promptContent = Get-Content "$AuditDir\FULL_AUDIT_CLAUDE.md" -Raw

    $logFile = "$LogDir\claude_full_audit_$timestamp.log"

    # Claude Code: -p for non-interactive print mode
    claude -p $promptContent --dangerously-skip-permissions 2>&1 | Tee-Object -FilePath $logFile

    Write-Host ""
    Write-Host "[CLAUDE] Audit complete. Log saved to: $logFile" -ForegroundColor Green
    Write-Host "[CLAUDE] Report should be at: $ProjectDir\docs\AUDIT_REPORT_CLAUDE_2026_R3.md" -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------
# FOCUSED TASKS (run after full audits)
# -----------------------------------------------------------
function Run-FocusedAudits {
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host "  FOCUSED TASK AUDITS" -ForegroundColor Magenta
    Write-Host "========================================" -ForegroundColor Magenta
    Write-Host ""

    # Claude: Database Deep Dive
    Write-Host "[CLAUDE] Starting focused database audit..." -ForegroundColor Yellow
    $prompt = Get-Content "$AuditDir\FOCUSED_CLAUDE_DATABASE.md" -Raw
    $logFile = "$LogDir\claude_focused_db_$timestamp.log"
    claude -p $prompt --dangerously-skip-permissions 2>&1 | Tee-Object -FilePath $logFile
    Write-Host "[CLAUDE] Focused audit complete." -ForegroundColor Green
    Write-Host ""

    # Codex: Code & Security Deep Dive
    Write-Host "[CODEX] Starting focused code audit..." -ForegroundColor Yellow
    $prompt = Get-Content "$AuditDir\FOCUSED_CODEX_CODE.md" -Raw
    $logFile = "$LogDir\codex_focused_code_$timestamp.log"
    codex exec $prompt --full-auto -C $ProjectDir --skip-git-repo-check 2>&1 | Tee-Object -FilePath $logFile
    Write-Host "[CODEX] Focused audit complete." -ForegroundColor Green
    Write-Host ""

    # Gemini: Research & Methodology Validation
    Write-Host "[GEMINI] Starting focused research audit..." -ForegroundColor Yellow
    $prompt = Get-Content "$AuditDir\FOCUSED_GEMINI_RESEARCH.md" -Raw
    $logFile = "$LogDir\gemini_focused_research_$timestamp.log"
    gemini -p $prompt -y -o text 2>&1 | Tee-Object -FilePath $logFile
    Write-Host "[GEMINI] Focused audit complete." -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------
# MAIN EXECUTION
# -----------------------------------------------------------
switch ($AuditTarget.ToLower()) {
    "gemini"  { Run-GeminiAudit }
    "codex"   { Run-CodexAudit }
    "claude"  { Run-ClaudeAudit }
    "focused" { Run-FocusedAudits }
    "all" {
        Write-Host "Running all three full audits sequentially..." -ForegroundColor Cyan
        Write-Host "Estimated total time: 30-60 minutes" -ForegroundColor Gray
        Write-Host ""

        Run-GeminiAudit
        Run-CodexAudit
        Run-ClaudeAudit

        Write-Host "========================================" -ForegroundColor Green
        Write-Host "  ALL FULL AUDITS COMPLETE" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Reports should be at:" -ForegroundColor White
        Write-Host "  docs\AUDIT_REPORT_GEMINI_2026_R3.md" -ForegroundColor White
        Write-Host "  docs\AUDIT_REPORT_CODEX_2026_R3.md" -ForegroundColor White
        Write-Host "  docs\AUDIT_REPORT_CLAUDE_2026_R3.md" -ForegroundColor White
        Write-Host ""
        Write-Host "Logs saved to: $LogDir" -ForegroundColor Gray
        Write-Host ""
        Write-Host "NEXT STEP: Run focused audits with:" -ForegroundColor Yellow
        Write-Host "  .\audit_2026\run_full_audits.ps1 -AuditTarget focused" -ForegroundColor Yellow
    }
    default {
        Write-Host "Unknown target: $AuditTarget" -ForegroundColor Red
        Write-Host "Valid options: all, gemini, codex, claude, focused" -ForegroundColor Gray
    }
}
