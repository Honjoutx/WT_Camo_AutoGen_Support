param(
    [string]$PainterUserDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $projectRoot "painter_plugins\vehicle_livery_studio"

if (-not $PainterUserDirectory) {
    $documents = [Environment]::GetFolderPath("MyDocuments")
    $PainterUserDirectory = Join-Path $documents "Adobe\Adobe Substance 3D Painter"
}

$pluginRoot = Join-Path $PainterUserDirectory "python\plugins"
$target = Join-Path $pluginRoot "vehicle_livery_studio"

if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Painter plug-in source not found: $source"
}

New-Item -ItemType Directory -Force -Path $target | Out-Null
Get-ChildItem -LiteralPath $source -File -Filter "*.py" |
    Copy-Item -Destination $target -Force

Write-Output "Installed Painter plug-in: $target"
Write-Output "Painter 10.1+：可在 Python 插件管理器启用 vehicle_livery_studio。"
Write-Output "也可运行 scripts\start-painter-livery.ps1 自动加载，然后在 Window > Vehicle Livery Agent 打开面板。"
