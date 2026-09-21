<#
.SYNOPSIS
    Automated Setup and Launch Script for Local InfluxDB v2 on Windows.
.DESCRIPTION
    Subsystem: IoT + Backend + Dashboard (Member 3)
    Phase: Phase 3 Implementation
    Classification: [IMPLEMENTATION DECISION]

    Downloads and extracts the official portable InfluxDB v2.7.12 standalone binary,
    optionally starts the server process on localhost:8086, and executes initialization.
.PARAMETER Start
    Starts the influxd.exe server process in the background.
.PARAMETER Init
    Runs python scripts/init_influxdb.py after starting the server.
.EXAMPLE
    .\scripts\setup_influxdb_windows.ps1 -Start -Init
#>

param (
    [switch]$Start,
    [switch]$Init
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$BinDir = Join-Path $ProjectRoot "bin\influxdb"
$InfluxdExe = Join-Path $BinDir "influxd.exe"
$DownloadUrl = "https://dl.influxdata.com/influxdb/releases/v2.7.12/influxdb2-2.7.12-windows.zip"
$ZipFile = Join-Path $BinDir "influxdb2.zip"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Edge-IoT Predictive Maintenance - InfluxDB Windows Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check if influxd is already available
$ExistingCommand = Get-Command influxd.exe -ErrorAction SilentlyContinue
if ($ExistingCommand) {
    Write-Host "[OK] influxd.exe found on system PATH: $($ExistingCommand.Source)" -ForegroundColor Green
    $InfluxdExe = $ExistingCommand.Source
} elseif (Test-Path $InfluxdExe) {
    Write-Host "[OK] influxd.exe found at: $InfluxdExe" -ForegroundColor Green
} else {
    Write-Host "[INFO] Downloading InfluxDB v2.7.12 portable release..." -ForegroundColor Yellow
    if (-not (Test-Path $BinDir)) {
        New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    }

    Write-Host "Fetching from: $DownloadUrl"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipFile -UseBasicParsing

    Write-Host "[INFO] Extracting archive to $BinDir..." -ForegroundColor Yellow
    Expand-Archive -Path $ZipFile -DestinationPath $BinDir -Force
    Remove-Item $ZipFile -Force

    # Check extracted contents (sometimes extracted into subfolder)
    $NestedExe = Get-ChildItem -Path $BinDir -Filter "influxd.exe" -Recurse | Select-Object -First 1
    if ($NestedExe) {
        $InfluxdExe = $NestedExe.FullName
        Write-Host "[SUCCESS] InfluxDB binary ready at: $InfluxdExe" -ForegroundColor Green
    } else {
        Write-Error "Failed to locate influxd.exe after archive extraction."
        exit 1
    }
}

# 2. Start server if requested
if ($Start) {
    # Check if already listening on port 8086
    $PortCheck = Test-NetConnection -ComputerName 127.0.0.1 -Port 8086 -WarningAction SilentlyContinue
    if ($PortCheck.TcpTestSucceeded) {
        Write-Host "[OK] InfluxDB is already listening on port 8086." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Starting InfluxDB server ($InfluxdExe)..." -ForegroundColor Yellow
        Start-Process -FilePath $InfluxdExe -ArgumentList "--bolt-path `"$BinDir\influxd.bolt`" --engine-path `"$BinDir\engine`"" -WindowStyle Hidden
        
        # Wait up to 10 seconds for service to listen
        $Ready = $false
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Milliseconds 500
            $Check = Test-NetConnection -ComputerName 127.0.0.1 -Port 8086 -WarningAction SilentlyContinue
            if ($Check.TcpTestSucceeded) {
                $Ready = $true
                break
            }
        }

        if ($Ready) {
            Write-Host "[SUCCESS] InfluxDB server is running and listening on http://localhost:8086" -ForegroundColor Green
        } else {
            Write-Error "InfluxDB failed to start or did not open port 8086 within 10 seconds."
            exit 1
        }
    }
}

# 3. Initialize if requested
if ($Init) {
    Write-Host "[INFO] Running Python initialization script..." -ForegroundColor Yellow
    python "$ProjectRoot\scripts\init_influxdb.py"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Setup Completed Successfully." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
