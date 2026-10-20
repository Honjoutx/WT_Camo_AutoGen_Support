param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$Repo = Split-Path $PSScriptRoot -Parent
$VenvPython = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    if ($PythonPath) { & $PythonPath -m venv (Join-Path $Repo '.venv') }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv (Join-Path $Repo '.venv') }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m venv (Join-Path $Repo '.venv') }
    else { throw 'Python 3.11-3.13 is required. Install Python, then run start.cmd again.' }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
}
& $VenvPython -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14), "Use Python 3.11-3.13"'
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python version.' }
& $VenvPython -m pip install -r (Join-Path $Repo 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your pip network configuration.' }
& $VenvPython (Join-Path $Repo 'tools\livery-layout-editor\bootstrap.py')
if ($LASTEXITCODE -ne 0) { throw 'Workspace initialization failed.' }
(Get-FileHash -LiteralPath (Join-Path $Repo 'requirements.txt') -Algorithm SHA256).Hash | Set-Content -LiteralPath (Join-Path $Repo '.venv\workbench-requirements.sha256') -Encoding ASCII
Write-Host 'Setup complete. Existing Codex CLI login will be reused.'
