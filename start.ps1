param([switch]$NoBrowser,[switch]$SkipInstall)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
  if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
  elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv .venv }
  else { throw "Python was not found. Install Python 3.11+ and add it to PATH." }
}
if (-not $SkipInstall) { & $Python -m pip install -r requirements.txt }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "npm was not found. Install Node.js LTS first." }
Push-Location web
try {
  if (-not (Test-Path -LiteralPath "node_modules")) { npm install }
  npm run build
}
finally { Pop-Location }
$RunArguments = @("run.py")
if (-not $NoBrowser) { $RunArguments += "--open-browser" }
Write-Host "Starting MyGraphWar at http://127.0.0.1:8000"
Write-Host "Press Ctrl+C to stop the server."
& $Python @RunArguments
