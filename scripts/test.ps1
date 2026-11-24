# Runs the full automated test suite: backend Pytest, then frontend Vitest.
# Any non-zero exit aborts the run so a broken stage never looks green.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Invoke-Step {
    param([string]$Label, [scriptblock]$Action)
    Write-Host "=== $Label ===" -ForegroundColor Cyan
    # Merge native stderr into stdout: PowerShell 5.1 otherwise turns tool
    # warnings into error records and flips the script's exit code.
    & $Action 2>&1 | ForEach-Object { Write-Host $_ }
    return $LASTEXITCODE
}

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $py) {
    Push-Location (Join-Path $root "backend")
    $code = Invoke-Step "backend pytest" { & $py -m pytest -q }
    if ($code -ne 0) { $failed += "backend:pytest" }
    Pop-Location
} else {
    Write-Host "跳过后端测试：未找到虚拟环境" -ForegroundColor Yellow
    $failed += "backend:missing-venv"
}

Push-Location (Join-Path $root "frontend")
$code = Invoke-Step "frontend vitest" { & npm.cmd run test }
if ($code -ne 0) { $failed += "frontend:vitest" }
Pop-Location

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "测试失败：$($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "全部测试通过" -ForegroundColor Green
exit 0
