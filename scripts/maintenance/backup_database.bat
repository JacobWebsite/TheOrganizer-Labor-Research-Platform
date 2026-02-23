@echo off
REM Database backup script for olms_multiyear (Windows)
REM Run via Task Scheduler: Daily at 2:00 AM
REM Action: This .bat file
REM
REM Restore command:
REM   gunzip olms_YYYYMMDD_HHMMSS.dump.gz
REM   pg_restore -U postgres -d olms_multiyear --clean --if-exists olms_YYYYMMDD_HHMMSS.dump

setlocal enabledelayedexpansion

set DB_NAME=olms_multiyear
set DB_USER=postgres
set BACKUP_DIR=C:\Users\jakew\backups\olms
set RETAIN_DAYS=7

REM Create backup directory
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Generate timestamp
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set TIMESTAMP=%datetime:~0,8%_%datetime:~8,6%
set BACKUP_FILE=%BACKUP_DIR%\olms_%TIMESTAMP%.dump

echo Starting backup of %DB_NAME% at %date% %time%

REM Run pg_dump with custom format (includes compression)
pg_dump -U %DB_USER% -Fc -f "%BACKUP_FILE%" %DB_NAME%

if errorlevel 1 (
    echo ERROR: pg_dump failed!
    exit /b 1
)

echo Backup complete: %BACKUP_FILE%

REM Show backup size
for %%A in ("%BACKUP_FILE%") do echo Size: %%~zA bytes

REM Clean old backups (older than RETAIN_DAYS)
forfiles /p "%BACKUP_DIR%" /m "olms_*.dump" /d -%RETAIN_DAYS% /c "cmd /c del @path" 2>nul

echo Remaining backups:
dir /b "%BACKUP_DIR%\olms_*.dump" 2>nul

echo Done at %date% %time%
