# 本地运行脚本（无热重载；有 frontend/dist 时由后端同源提供静态前端）
# 用法（在 backend 目录下）： .\scripts\start.ps1 [-Port 8000]

param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $backend
$dist = Join-Path $repo "frontend\dist"
$env:PYTHONPATH = "$backend;$repo\tech"

$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Error "端口 $Port 已被占用（PID: $($inUse.OwningProcess)），请先关闭或改用 -Port。"
    exit 1
}

if (Test-Path $dist) {
    $env:FLOWSTUDIO_FRONTEND_DIST = $dist
    Write-Host "检测到前端产物，将由后端同源提供：$dist"
} else {
    Write-Host "未检测到 frontend/dist，仅提供 API（开发期请用 dev.ps1 + Vite）。"
}

Set-Location $backend
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "请先运行 .\scripts\dev.ps1 初始化虚拟环境与依赖。"
    exit 1
}

$env:FLOWSTUDIO_WORKER_MODE = "thread"
Write-Host "FlowStudio 后端： http://127.0.0.1:$Port"
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
