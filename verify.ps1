param([switch]$E2E)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Python = "python"
if (Test-Path -LiteralPath ".venv\Scripts\python.exe") { $Python = ".venv\Scripts\python.exe" }
Write-Host "Running Python tests..."
& $Python -m pytest -q
Push-Location web
try {
  Write-Host "Building browser client..."
  npm run build
  if ($E2E) {
    Write-Host "Running Chromium end-to-end tests..."
    npm run test:e2e
  }
}
finally { Pop-Location }
Write-Host "Verification complete."
