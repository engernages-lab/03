# Starts the PocketScore AI backend and frontend dev servers.
# Logs are written to .run/*.log so the console stays readable.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runDir = Join-Path $root ".run"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "未找到后端虚拟环境：$py。请先执行 backend 的 pip install。"
}

Write-Host "启动后端 API http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backend = Start-Process -FilePath $py `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload" `
    -WorkingDirectory (Join-Path $root "backend") `
    -RedirectStandardOutput (Join-Path $runDir "backend.out.log") `
    -RedirectStandardError (Join-Path $runDir "backend.err.log") `
    -PassThru

Write-Host "启动前端 Vite http://127.0.0.1:5173 ..." -ForegroundColor Cyan
$frontend = Start-Process -FilePath "npm.cmd" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory (Join-Path $root "frontend") `
    -RedirectStandardOutput (Join-Path $runDir "frontend.out.log") `
    -RedirectStandardError (Join-Path $runDir "frontend.err.log") `
    -PassThru

Write-Host ""
Write-Host "  前端  http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  后端  http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "  日志  $runDir" -ForegroundColor DarkGray
Write-Host ""
Write-Host "按 Ctrl+C 结束本次前台等待（服务进程需手动停止：Stop-Process -Id $($backend.Id),$($frontend.Id))" -ForegroundColor DarkGray
