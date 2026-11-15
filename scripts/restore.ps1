# ==============================================================================
# HabitPulse 1-Click Restore Script (Windows PowerShell)
# Restores the PostgreSQL database into Docker and unpacks media files.
# ==============================================================================
param (
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,
    [string]$DbUser = "habit_user",
    [string]$DbName = "habit_tracker"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupFile)) {
    # Check if relative to backups directory
    $BackupDir = Join-Path -Path $PSScriptRoot -ChildPath "..\backups"
    $Candidate = Join-Path $BackupDir $BackupFile
    if (Test-Path $Candidate) {
        $BackupFile = $Candidate
    } else {
        Write-Error "Backup file not found at: $BackupFile"
        exit 1
    }
}

Write-Host "==> [1/2] Restoring PostgreSQL database into habitpulse_db container..." -ForegroundColor Cyan

# Check if .sql or .sql.gz
if ($BackupFile.EndsWith(".gz")) {
    $tempSql = [System.IO.Path]::GetTempFileName() + ".sql"
    $pyDecompress = "import gzip, shutil; shutil.copyfileobj(gzip.open(r'$BackupFile', 'rb'), open(r'$tempSql', 'wb'))"
    & python -c $pyDecompress
    Get-Content $tempSql | docker exec -i habitpulse_db psql -U $DbUser -d $DbName
    Remove-Item $tempSql -Force
} else {
    Get-Content $BackupFile | docker exec -i habitpulse_db psql -U $DbUser -d $DbName
}
Write-Host "    Database restoration completed." -ForegroundColor Green

# Restore media if matching archive found
$timestampMatch = [regex]::Match($BackupFile, "habitpulse_db_(\d{8}_\d{6})")
if ($timestampMatch.Success) {
    $ts = $timestampMatch.Groups[1].Value
    $zipMedia = Join-Path (Split-Path $BackupFile) "habitpulse_media_${ts}.zip"
    $tarMedia = Join-Path (Split-Path $BackupFile) "habitpulse_media_${ts}.tar.gz"
    $MediaDir = Join-Path -Path $PSScriptRoot -ChildPath "..\media"

    if (Test-Path $zipMedia) {
        Write-Host "==> [2/2] Restoring media files from $zipMedia..." -ForegroundColor Cyan
        Expand-Archive -Path $zipMedia -DestinationPath $MediaDir -Force
        Write-Host "    Media restoration completed." -ForegroundColor Green
    } elseif (Test-Path $tarMedia) {
        Write-Host "==> [2/2] Restoring media files from $tarMedia..." -ForegroundColor Cyan
        tar -xzf $tarMedia -C $MediaDir
        Write-Host "    Media restoration completed." -ForegroundColor Green
    }
}

Write-Host "==> [SUCCESS] Full system restoration complete! Application state restored." -ForegroundColor Green
