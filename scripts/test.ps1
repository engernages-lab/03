# Runs the full automated test suite: backend Pytest, then frontend Vitest.
# Any non-zero exit aborts the run so a broken stage never looks green.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $py) {
    Write-Host "=== 后端 Pytest ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root "backend")
    & $py -m pytest
    if ($LASTEXITCODE -ne 0) { $failed += "backend:pytest" }
    Pop-Location
} else {
    Write-Host "跳过后端测试：未找到虚拟环境" -ForegroundColor Yellow
    $failed += "backend:missing-venv"
}

Write-Host "=== 前端 Vitest ===" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
& npm.cmd run test
if ($LASTEXITCODE -ne 0) { $failed += "frontend:vitest" }
Pop-Location

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "测试失败：$($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "全部测试通过" -ForegroundColor Green
