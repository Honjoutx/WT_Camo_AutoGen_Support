param([int]$Port=18188,[string]$PythonPath,[switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Repo = Split-Path $PSScriptRoot -Parent
$VenvPython = Join-Path $Repo '.venv\Scripts\python.exe'
$Stamp = Join-Path $Repo '.venv\workbench-requirements.sha256'
$Expected = (Get-FileHash -LiteralPath (Join-Path $Repo 'requirements.txt') -Algorithm SHA256).Hash
if (-not (Test-Path -LiteralPath $VenvPython) -or -not (Test-Path -LiteralPath $Stamp) -or (Get-Content -LiteralPath $Stamp -Raw).Trim() -ne $Expected) {
    & (Join-Path $PSScriptRoot 'setup-workbench.ps1') -PythonPath $PythonPath
}
$Server = Join-Path $Repo 'tools\livery-layout-editor\server.py'
$Url = "http://127.0.0.1:$Port"
try {
    $Health = Invoke-RestMethod "$Url/api/studio/health" -TimeoutSec 2
    if ($Health.application -eq 'wt-camo-workbench') {
        if (-not $NoBrowser) { Start-Process $Url }
        Write-Host "Workbench already running: $Url"
        exit 0
    }
    throw "Port $Port is already used by another service. Choose -Port 18190."
} catch {
    if ($_.Exception.Message -like 'Port *') { throw }
}
& $VenvPython (Join-Path $Repo 'tools\livery-layout-editor\bootstrap.py')
if ($LASTEXITCODE -ne 0) { throw 'Workspace initialization failed.' }
$LogDir = Join-Path $Repo 'data\logs'
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Args = @('"' + $Server + '"', '--port', "$Port")
$Process = Start-Process -FilePath $VenvPython -ArgumentList $Args -WorkingDirectory $Repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogDir "workbench-$Port.out.log") -RedirectStandardError (Join-Path $LogDir "workbench-$Port.err.log")
$Process.Id | Set-Content -LiteralPath (Join-Path $LogDir "workbench-$Port.pid")
$Ready=$false
for ($Attempt=0; $Attempt -lt 40; $Attempt++) {
    Start-Sleep -Milliseconds 300
    try { $Health=Invoke-RestMethod "$Url/api/studio/health" -TimeoutSec 2; if ($Health.application -eq 'wt-camo-workbench') { $Ready=$true; break } } catch {}
    if ($Process.HasExited) { break }
}
if (-not $Ready) { throw "Workbench did not start. See data\logs\workbench-$Port.err.log" }
if (-not $NoBrowser) { Start-Process $Url }
Write-Host "Workbench started: $Url"
Write-Host "Stop: powershell -File scripts\stop-workbench.ps1 -Port $Port"
