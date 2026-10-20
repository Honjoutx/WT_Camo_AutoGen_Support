param([string]$BlenderPath, [string]$ModelPath)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$Repo = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { & (Join-Path $PSScriptRoot 'setup-workbench.ps1') }
$Arguments = @((Join-Path $PSScriptRoot 'blender_mcp_manage.py'), 'start')
if ($BlenderPath) { $Arguments += @('--blender', $BlenderPath) }
if ($ModelPath) { $Arguments += @('--model', $ModelPath) }
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Blender MCP startup failed.' }
