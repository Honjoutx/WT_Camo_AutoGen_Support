param([int]$Port=18188)
$ErrorActionPreference = 'Stop'
$Repo=Split-Path $PSScriptRoot -Parent
$PidFile=Join-Path $Repo "data\logs\workbench-$Port.pid"
if (-not (Test-Path -LiteralPath $PidFile)) { Write-Host 'No launcher PID record.'; exit 0 }
$ServerPid=[int](Get-Content -LiteralPath $PidFile -Raw)
$ProcessInfo=Get-CimInstance Win32_Process -Filter "ProcessId=$ServerPid"
$ServerPath=Join-Path $Repo 'tools\livery-layout-editor\server.py'
if ($ProcessInfo -and $ProcessInfo.CommandLine.Contains($ServerPath) -and $ProcessInfo.CommandLine.Contains("--port $Port")) {
    # This process tree belongs to this launcher, including its CLI/workers.
    & taskkill.exe /PID $ServerPid /T /F | Out-Null
} elseif ($ProcessInfo) { throw 'PID has been reused; refusing to stop an unrelated process.' }
Remove-Item -LiteralPath $PidFile
Write-Host 'Workbench stopped.'
