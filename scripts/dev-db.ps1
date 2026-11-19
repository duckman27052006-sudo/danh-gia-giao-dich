<#
    Quan ly cluster PostgreSQL chay local cho FraudLens (khong can quyen admin).

    Cluster nam trong .pgdata/ cua repo, lang nghe 127.0.0.1:5433, user "postgres",
    database "fraudlens". Dung trust auth nen chi phu hop cho may dev ca nhan.

    Vi du:
        .\scripts\dev-db.ps1 start      # khoi tao (lan dau) + bat server + tao database
        .\scripts\dev-db.ps1 status
        .\scripts\dev-db.ps1 stop
        .\scripts\dev-db.ps1 reset      # xoa sach du lieu, tao lai database rong
#>
param(
    [ValidateSet("start", "stop", "status", "reset")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $Root ".pgdata"
$Port = 5433
$DbName = "fraudlens"

function Get-PgBin {
    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "bin\pg_ctl.exe") } |
    Sort-Object { [int]($_.Name -replace "\D", "") } -Descending
    if (-not $candidates) {
        throw "Khong tim thay PostgreSQL trong 'C:\Program Files\PostgreSQL'. Cai PostgreSQL 14+ roi chay lai."
    }
    return Join-Path $candidates[0].FullName "bin"
}

function Test-ServerRunning {
    param([string]$PgBin)
    & (Join-Path $PgBin "pg_isready.exe") -h 127.0.0.1 -p $Port -q 2>$null
    return $LASTEXITCODE -eq 0
}

function Initialize-Cluster {
    param([string]$PgBin)
    if (Test-Path (Join-Path $DataDir "PG_VERSION")) { return }
    Write-Host "Khoi tao cluster PostgreSQL tai .pgdata ..." -ForegroundColor Cyan
    & (Join-Path $PgBin "initdb.exe") -D $DataDir -U postgres --auth=trust --encoding=UTF8 --locale=C | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "initdb that bai" }
}

function Start-Db {
    param([string]$PgBin)
    Initialize-Cluster $PgBin
    if (-not (Test-ServerRunning $PgBin)) {
        Write-Host "Bat PostgreSQL (127.0.0.1:$Port) ..." -ForegroundColor Cyan
        & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -o "-p $Port -c listen_addresses=127.0.0.1" -l (Join-Path $DataDir "server.log") -w start | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Khong bat duoc PostgreSQL. Xem $DataDir\server.log" }
    }
    $exists = & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -tAc "select 1 from pg_database where datname='$DbName'" 2>$null
    if ($exists -notmatch "1") {
        Write-Host "Tao database '$DbName' ..." -ForegroundColor Cyan
        & (Join-Path $PgBin "createdb.exe") -h 127.0.0.1 -p $Port -U postgres $DbName
    }
    Write-Host "PostgreSQL san sang: postgresql+psycopg://postgres@127.0.0.1:$Port/$DbName" -ForegroundColor Green
}

function Stop-Db {
    param([string]$PgBin)
    if (Test-ServerRunning $PgBin) {
        & (Join-Path $PgBin "pg_ctl.exe") -D $DataDir -m fast stop | Out-Null
        Write-Host "Da dung PostgreSQL." -ForegroundColor Green
    }
    else {
        Write-Host "PostgreSQL dang khong chay."
    }
}

function Reset-Db {
    param([string]$PgBin)
    Start-Db $PgBin
    Write-Host "Xoa va tao lai database '$DbName' ..." -ForegroundColor Yellow
    & (Join-Path $PgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -d postgres -c "DROP DATABASE IF EXISTS $DbName WITH (FORCE)" | Out-Null
    & (Join-Path $PgBin "createdb.exe") -h 127.0.0.1 -p $Port -U postgres $DbName
    Write-Host "Database da trong. Lan chay app tiep theo se seed lai du lieu demo." -ForegroundColor Green
}

$pgBin = Get-PgBin
switch ($Action) {
    "start" { Start-Db $pgBin }
    "stop" { Stop-Db $pgBin }
    "reset" { Reset-Db $pgBin }
    "status" {
        if (Test-ServerRunning $pgBin) {
            & (Join-Path $pgBin "psql.exe") -h 127.0.0.1 -p $Port -U postgres -d $DbName -tAc "select version()" 2>$null
        }
        else {
            Write-Host "PostgreSQL dang khong chay. Bat bang: .\scripts\dev-db.ps1 start"
        }
    }
}
