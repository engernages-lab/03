# Static analysis: Ruff (backend) + TypeScript (frontend).

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Invoke-Step {
    param([string]$Label, [scriptblock]$Action)
    Write-Host "=== $Label ===" -ForegroundColor Cyan
    & $Action 2>&1 | ForEach-Object { Write-Host $_ }
    return $LASTEXITCODE
}

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $py) {
    Push-Location (Join-Path $root "backend")
    $code = Invoke-Step "Ruff" { & $py -m ruff check app tests }
    if ($code -ne 0) { $failed += "backend:ruff" }
    Pop-Location
}

Push-Location (Join-Path $root "frontend")
$code = Invoke-Step "TypeScript" { & npm.cmd run typecheck }
if ($code -ne 0) { $failed += "frontend:tsc" }
Pop-Location

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "静态检查失败：$($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "静态检查通过" -ForegroundColor Green
exit 0
