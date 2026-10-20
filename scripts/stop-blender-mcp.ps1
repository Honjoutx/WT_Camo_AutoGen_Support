$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$Repo = Split-Path $PSScriptRoot -Parent
& (Join-Path $Repo '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'blender_mcp_manage.py') stop
if ($LASTEXITCODE -ne 0) { throw 'Blender MCP stop failed. No unrelated process was stopped.' }
