# PostgreSQL local para dev (conda). Uso: .\scripts\start-postgres-dev.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$DataDir = Join-Path $Root "data\postgres"
$LogFile = Join-Path $DataDir "server.log"
$PgCtl = Join-Path $env:CONDA_PREFIX "Library\bin\pg_ctl.exe"
$InitDb = Join-Path $env:CONDA_PREFIX "Library\bin\initdb.exe"
$Psql = Join-Path $env:CONDA_PREFIX "Library\bin\psql.exe"

if (-not (Test-Path $PgCtl)) {
    $PgCtl = "C:\Users\Paulo\miniconda3\Library\bin\pg_ctl.exe"
    $InitDb = "C:\Users\Paulo\miniconda3\Library\bin\initdb.exe"
    $Psql = "C:\Users\Paulo\miniconda3\Library\bin\psql.exe"
}

if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    & $InitDb -D $DataDir -U postgres -A trust -E UTF8 --locale=C
    & $PgCtl -D $DataDir -l $LogFile start
    Start-Sleep -Seconds 2
    $env:PGHOST = "localhost"
    $env:PGPORT = "5432"
    $env:PGUSER = "postgres"
    & $Psql -d postgres -c "ALTER USER postgres WITH PASSWORD 'postgres';"
    & $Psql -d postgres -c "CREATE DATABASE forensicauth;"
    Write-Host "PostgreSQL inicializado em $DataDir"
} else {
    & $PgCtl -D $DataDir -l $LogFile status 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $PgCtl -D $DataDir -l $LogFile start
        Write-Host "PostgreSQL iniciado."
    } else {
        Write-Host "PostgreSQL ja esta em execucao."
    }
}
