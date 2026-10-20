param(
    [int]$Port = 8766,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$serverPath = Join-Path $projectRoot "livery-workbench\server.py"

if (-not $PythonPath) { $PythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    $pythonCommand = Get-Command "python" -ErrorAction Stop
    $PythonPath = $pythonCommand.Source
}
if (-not (Test-Path -LiteralPath $serverPath -PathType Leaf)) {
    throw "Painter Agent service was not found: $serverPath"
}

$codexCommand = Get-Command "codex" -ErrorAction SilentlyContinue
$previousCodexPath = $env:CAMO_CODEX_PATH
try {
    if ($codexCommand -and $codexCommand.Source) {
        $env:CAMO_CODEX_PATH = $codexCommand.Source
    }
    $process = Start-Process `
        -FilePath $PythonPath `
        -ArgumentList @(('"' + $serverPath + '"'), "--port", "$Port", "--no-browser") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru
}
finally {
    $env:CAMO_CODEX_PATH = $previousCodexPath
}

Write-Output "Painter Agent service started: http://127.0.0.1:$Port"
Write-Output "PID: $($process.Id)"
