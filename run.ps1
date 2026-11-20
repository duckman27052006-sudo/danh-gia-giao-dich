$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Tao virtualenv..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Cai dependencies Python..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pip install -q --upgrade pip
.\.venv\Scripts\python.exe -m pip install -q -r requirements-dev.txt

if (-not $env:DATABASE_URL) {
    Write-Host "Khoi dong PostgreSQL cai tren Windows..." -ForegroundColor Cyan
    & "$PSScriptRoot\scripts\windows-db.ps1" start
    $env:DATABASE_URL = "postgresql+psycopg://fraudlens:fraudlens_dev_password@127.0.0.1:5432/fraudlens"
}

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Cai dependencies frontend..." -ForegroundColor Cyan
    Push-Location frontend
    npm install --no-audit --no-fund
    Pop-Location
}

if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "Build frontend..." -ForegroundColor Cyan
    Push-Location frontend
    npm run build
    Pop-Location
}

Write-Host "Khoi dong FraudLens tai http://127.0.0.1:8000" -ForegroundColor Green
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
