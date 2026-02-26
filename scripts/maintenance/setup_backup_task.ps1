# Setup daily backup task for labor data database
# Run as: powershell -ExecutionPolicy Bypass -File scripts\maintenance\setup_backup_task.ps1

$taskName = "LaborDataDailyBackup"
$pythonExe = "C:\Users\jakew\AppData\Local\Programs\Python\Launcher\py.exe"
$scriptPath = "C:\Users\jakew\.local\bin\Labor Data Project_real\scripts\maintenance\backup_labor_data.py"
$workingDir = "C:\Users\jakew\.local\bin\Labor Data Project_real"
$logFile = "C:\Users\jakew\backups\labor_data\backup.log"

# Check if task already exists
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Task '$taskName' already exists (State: $($existing.State)). Removing..."
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create the action: run py backup_labor_data.py, append output to log
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$pythonExe`" `"$scriptPath`" >> `"$logFile`" 2>&1" `
    -WorkingDirectory $workingDir

# Trigger: daily at 3:00 AM
$trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM

# Settings: run whether user is logged in or not, don't stop if on battery
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Register the task (runs as current user)
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily pg_dump backup of olms_multiyear database (7-day retention)" `
    -RunLevel Highest

Write-Host ""
Write-Host "Scheduled task '$taskName' created successfully."
Write-Host "  Schedule: Daily at 3:00 AM"
Write-Host "  Script:   $scriptPath"
Write-Host "  Log:      $logFile"
Write-Host "  Backups:  C:\Users\jakew\backups\labor_data\"
Write-Host "  Retention: 7 days (auto-cleanup in backup script)"
Write-Host ""
Write-Host "To test manually: py scripts\maintenance\backup_labor_data.py"
Write-Host "To check status:  schtasks /query /tn $taskName /v"
