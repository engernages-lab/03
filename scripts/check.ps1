# Static analysis: Ruff (backend) + TypeScript (frontend).

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $py) {
    Write-Host "=== Ruff ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root "backend")
    & $py -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { $failed += "backend:ruff" }
    Pop-Location
}

Write-Host "=== TypeScript ===" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
& npm.cmd run typecheck
if ($LASTEXITCODE -ne 0) { $failed += "frontend:tsc" }
Pop-Location

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "静态检查失败：$($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "静态检查通过" -ForegroundColor Green
