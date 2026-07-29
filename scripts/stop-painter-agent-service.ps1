param(
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$expectedServer = Join-Path $projectRoot "livery-workbench\server.py"
$listener = Get-NetTCPConnection `
    -LocalPort $Port `
    -State Listen `
    -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $listener) {
    Write-Output "No Painter Agent service is listening on port $Port."
    exit 0
}

$processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
if (-not $processInfo -or $processInfo.CommandLine -notlike "*$expectedServer*") {
    throw "Port $Port is not owned by this project's Painter Agent service."
}

Stop-Process -Id $listener.OwningProcess
Write-Output "Stopped Painter Agent service on port $Port (PID $($listener.OwningProcess))."
