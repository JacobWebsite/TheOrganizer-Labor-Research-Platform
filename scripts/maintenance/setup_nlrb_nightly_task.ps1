# Setup daily NLRB nightly pull task.
# Run as: powershell -ExecutionPolicy Bypass -File scripts\maintenance\setup_nlrb_nightly_task.ps1
#
# Mirrors the setup_backup_task.ps1 pattern -- creates a Windows Task Scheduler
# job that runs `nlrb_nightly_pull.py` daily at 2:00 AM (1 hour before the
# backup job). Pulls cases filed in the last 24 hours and rule-engine-matches
# participants to master_employers.

$taskName     = "LaborDataNLRBNightly"
$pythonExe    = "C:\Users\jakew\AppData\Local\Programs\Python\Launcher\py.exe"
$pullScript   = "C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\etl\nlrb_nightly_pull.py"
$matchScript  = "C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\matching\match_nlrb_nightly_to_masters.py"
$workingDir   = "C:\Users\jakew\.local\bin\Labor Data Project_real"
$logFile      = "C:\Users\jakew\backups\labor_data\nlrb_nightly.log"

# Check if task already exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task '$taskName' already exists (State: $($existing.State)). Removing..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Chained command: pull then match (both write to the same log)
$cmd = "cmd.exe"
$args = "/c `"$pythonExe`" `"$pullScript`" --hours-back 24 --commit >> `"$logFile`" 2>&1 && `"$pythonExe`" `"$matchScript`" --latest-handoff --commit >> `"$logFile`" 2>&1"

$action = New-ScheduledTaskAction `
    -Execute $cmd `
    -Argument $args `
    -WorkingDirectory $workingDir

# Trigger: daily at 2:00 AM (1 hour before the backup job)
$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM

# Settings: run whether user is logged in or not, don't stop if on battery
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

# Register the task (runs as current user)
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily NLRB case pull (24h delta) + rule-engine match to masters" `
    -RunLevel Highest

Write-Host ""
Write-Host "Task '$taskName' registered. Will run daily at 2:00 AM."
Write-Host "Log file: $logFile"
Write-Host "To trigger manually:   Start-ScheduledTask -TaskName $taskName"
Write-Host "To disable temporarily: Disable-ScheduledTask -TaskName $taskName"
Write-Host "To remove:             Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
