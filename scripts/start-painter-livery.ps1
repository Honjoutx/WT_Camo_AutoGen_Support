param(
    [string]$PainterPath = "C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$documents = [Environment]::GetFolderPath("MyDocuments")
$painterPythonRoot = Join-Path $documents "Adobe\Adobe Substance 3D Painter\python"

if (-not (Test-Path -LiteralPath $PainterPath -PathType Leaf)) {
    throw "Substance 3D Painter was not found: $PainterPath"
}

$previousProjectRoot = $env:CAMO_PROJECT_ROOT
$previousCodexPath = $env:CAMO_CODEX_PATH
$previousPluginPath = $env:SUBSTANCE_PAINTER_PLUGINS_PATH
$previousStartupPlugins = $env:SUBSTANCE_PAINTER_STARTUP_PLUGINS
try {
    $env:CAMO_PROJECT_ROOT = $projectRoot
    $codexCommand = Get-Command "codex" -ErrorAction SilentlyContinue
    if ($codexCommand -and $codexCommand.Source) {
        $env:CAMO_CODEX_PATH = $codexCommand.Source
    }
    $env:SUBSTANCE_PAINTER_PLUGINS_PATH = $painterPythonRoot
    $startupPlugins = @()
    if ($previousStartupPlugins) {
        $startupPlugins += $previousStartupPlugins.Split(":")
    }
    if ($startupPlugins -notcontains "vehicle_livery_studio") {
        $startupPlugins += "vehicle_livery_studio"
    }
    $env:SUBSTANCE_PAINTER_STARTUP_PLUGINS = $startupPlugins -join ":"
    Start-Process -FilePath $PainterPath -WorkingDirectory $projectRoot
}
finally {
    $env:CAMO_PROJECT_ROOT = $previousProjectRoot
    $env:CAMO_CODEX_PATH = $previousCodexPath
    $env:SUBSTANCE_PAINTER_PLUGINS_PATH = $previousPluginPath
    $env:SUBSTANCE_PAINTER_STARTUP_PLUGINS = $previousStartupPlugins
}
