# 开发启动脚本（Windows PowerShell 5.1+）
# 用法（在 backend 目录下）： .\scripts\dev.ps1 [-Port 8000]

param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $backend
$env:PYTHONPATH = "$backend;$repo\tech"

# 端口占用检查
$inUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Error "端口 $Port 已被占用（PID: $($inUse.OwningProcess)），请先关闭或改用 -Port。"
    exit 1
}

Set-Location $backend
if (-not (Test-Path ".venv")) {
    Write-Host "创建虚拟环境 .venv ..."
    python -m venv .venv
}
$python = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境解释器：$python"
    exit 1
}

Write-Host "安装依赖（首次较慢）..."
& $python -m pip install --quiet --disable-pip-version-check -r (Join-Path $backend "requirements.txt")

$env:FLOWSTUDIO_WORKER_MODE = "thread"
Write-Host "启动后端： http://127.0.0.1:$Port/docs"
Write-Host "前端开发请另开终端在 frontend 目录执行 npm run dev（/api 代理到 $Port）"
& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port --reload
