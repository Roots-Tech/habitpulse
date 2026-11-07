# ==============================================================================
# HabitPulse 1-Click Backup Script (Windows PowerShell)
# Dumps the PostgreSQL database from Docker and archives media files.
# ==============================================================================
param (
    [string]$DbUser = "habit_user",
    [string]$DbName = "habit_tracker"
)

$ErrorActionPreference = "Stop"

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path -Path $PSScriptRoot -ChildPath "..\backups"
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$DbBackupFile = Join-Path $BackupDir "habitpulse_db_${Timestamp}.sql"
$DbBackupGz = Join-Path $BackupDir "habitpulse_db_${Timestamp}.sql.gz"
$MediaBackupZip = Join-Path $BackupDir "habitpulse_media_${Timestamp}.zip"

Write-Host "==> [1/2] Backing up PostgreSQL database from habitpulse_db container..." -ForegroundColor Cyan
docker exec habitpulse_db pg_dump -U $DbUser -d $DbName --no-owner --no-acl > $DbBackupFile

if (Test-Path $DbBackupFile) {
    Write-Host "    Compressing database dump..." -ForegroundColor Gray
    # Compress using gzip via python or keep .sql
    $pyCompress = "import gzip, shutil; shutil.copyfileobj(open(r'$DbBackupFile', 'rb'), gzip.open(r'$DbBackupGz', 'wb'))"
    & python -c $pyCompress
    Remove-Item $DbBackupFile
    Write-Host "    Database backup saved: $DbBackupGz" -ForegroundColor Green
}

Write-Host "==> [2/2] Backing up media files..." -ForegroundColor Cyan
$MediaDir = Join-Path -Path $PSScriptRoot -ChildPath "..\media"
if (Test-Path $MediaDir) {
    Compress-Archive -Path "$MediaDir\*" -DestinationPath $MediaBackupZip -Force
    Write-Host "    Media backup saved: $MediaBackupZip" -ForegroundColor Green
} else {
    Write-Host "    No media directory found, skipping." -ForegroundColor Yellow
}

Write-Host "==> [SUCCESS] Snapshot complete! Backups saved to $BackupDir" -ForegroundColor Green
