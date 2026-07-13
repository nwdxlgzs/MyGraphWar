$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $Root "mygraphwar.db"
if (-not (Test-Path -LiteralPath $Source)) { throw "mygraphwar.db was not found. Start the server once before backup." }
$BackupRoot = Join-Path $Root "backups"
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Target = Join-Path $BackupRoot "mygraphwar-$Stamp.db"
Copy-Item -LiteralPath $Source -Destination $Target
Write-Host "Backup complete: $Target"
