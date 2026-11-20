<#
    Dam bao PostgreSQL cai tren Windows (mac dinh 127.0.0.1:5432) dang chay.

    Script uu tien bat Windows service (postgresql-x64-*). Neu service bi Disabled
    hoac khong co quyen admin, script khoi dong truc tiep bang pg_ctl tren data dir
    cua ban cai PostgreSQL trong "C:\Program Files\PostgreSQL\<version>".

    Vi du:
        .\scripts\windows-db.ps1 start
        .\scripts\windows-db.ps1 status
        .\scripts\windows-db.ps1 stop
#>
param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "start",
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"

function Get-PgInstall {
    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
    Where-Object {
        (Test-Path (Join-Path $_.FullName "bin\pg_ctl.exe")) -and
        (Test-Path (Join-Path $_.FullName "data\PG_VERSION"))
    } |
    Sort-Object { [int]($_.Name -replace "\D", "") } -Descending
    if (-not $candidates) {
        throw "Khong tim thay PostgreSQL cai tren Windows trong 'C:\Program Files\PostgreSQL'. Cai PostgreSQL 14+ hoac dung .\scripts\dev-db.ps1."
    }
    return $candidates[0].FullName
}

$install = Get-PgInstall
$bin = Join-Path $install "bin"
$data = Join-Path $install "data"

function Test-ServerRunning {
    & (Join-Path $bin "pg_isready.exe") -h 127.0.0.1 -p $Port -q 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-PgService {
    return Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Start-Db {
    if (Test-ServerRunning) {
        Write-Host "PostgreSQL da chay san tai 127.0.0.1:$Port." -ForegroundColor Green
        return
    }

    $started = $false
    $service = Get-PgService
    if ($service -and $service.StartType -ne "Disabled") {
        try {
            Write-Host "Bat Windows service '$($service.Name)' ..." -ForegroundColor Cyan
            Start-Service -Name $service.Name -ErrorAction Stop
            $started = $true
        }
        catch {
            Write-Host "Khong bat duoc service ($($_.Exception.Message.Trim()))." -ForegroundColor Yellow
        }
    }
    elseif ($service) {
        Write-Host "Windows service '$($service.Name)' dang Disabled; bo qua service." -ForegroundColor Yellow
    }
    if (-not $started) {
        Write-Host "Bat PostgreSQL ($install) tren 127.0.0.1:$Port ..." -ForegroundColor Cyan
        $log = Join-Path $env:TEMP "fraudlens-pg.log"
        $stdout = Join-Path $env:TEMP "fraudlens-pg-start.out"
        $stderr = Join-Path $env:TEMP "fraudlens-pg-start.err"
        $arguments = '-D "' + $data + '" -l "' + $log + '" -w start'
        # Khong dung -Wait: pg_ctl giu console handle cua postmaster.
        Start-Process -FilePath (Join-Path $bin "pg_ctl.exe") -ArgumentList $arguments `
            -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
    }

    for ($i = 0; $i -lt 40; $i++) {
        if (Test-ServerRunning) {
            Write-Host "PostgreSQL san sang: 127.0.0.1:$Port (database fraudlens)" -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Khong bat duoc PostgreSQL tren cong $Port. Xem log: $(Join-Path $env:TEMP 'fraudlens-pg.log')"
}

function Stop-Db {
    if (-not (Test-ServerRunning)) {
        Write-Host "PostgreSQL dang khong chay."
        return
    }

    $service = Get-PgService
    if ($service -and $service.Status -eq "Running") {
        try {
            Stop-Service -Name $service.Name -ErrorAction Stop
            Write-Host "Da dung Windows service '$($service.Name)'." -ForegroundColor Green
            return
        }
        catch {
            Write-Host "Khong dung duoc service, thu pg_ctl ..." -ForegroundColor Yellow
        }
    }

    & (Join-Path $bin "pg_ctl.exe") -D $data -m fast stop | Out-Null
    Write-Host "Da dung PostgreSQL." -ForegroundColor Green
}

switch ($Action) {
    "start" { Start-Db }
    "stop" { Stop-Db }
    "status" {
        if (Test-ServerRunning) {
            Write-Host "PostgreSQL Windows dang chay tai 127.0.0.1:$Port." -ForegroundColor Green
            Write-Host "Ban cai: $install"
            Write-Host "Ket noi: postgresql+psycopg://fraudlens:fraudlens_dev_password@127.0.0.1:$Port/fraudlens"
        }
        else {
            Write-Host "PostgreSQL dang khong chay. Bat bang: .\scripts\windows-db.ps1 start"
        }
    }
}
