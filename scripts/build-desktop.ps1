param([string]$PythonPath)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$Repo=Split-Path $PSScriptRoot -Parent
$BuildPython=Join-Path $Repo '.tools\desktop-build-env\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $BuildPython)) {
    if ($PythonPath) { & $PythonPath -m venv (Join-Path $Repo '.tools\desktop-build-env') }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv (Join-Path $Repo '.tools\desktop-build-env') }
    else { & python -m venv (Join-Path $Repo '.tools\desktop-build-env') }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the desktop build environment.' }
}
& $BuildPython -m pip install -r (Join-Path $Repo 'requirements-desktop.txt')
if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
& $BuildPython (Join-Path $PSScriptRoot 'build-desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
