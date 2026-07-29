param(
    [string]$OutputPath = "dist\vehicle-livery-painter-plugin-0.3.1.zip"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $projectRoot "painter_plugins\vehicle_livery_studio"
$output = [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputPath))

if (-not (Test-Path -LiteralPath $source -PathType Container)) {
    throw "Painter plug-in source not found: $source"
}

$outputParent = Split-Path -Parent $output
New-Item -ItemType Directory -Force -Path $outputParent | Out-Null

$stageRoot = Join-Path ([IO.Path]::GetTempPath()) ("vehicle-livery-painter-" + [Guid]::NewGuid().ToString("N"))
$stagePackage = Join-Path $stageRoot "vehicle_livery_studio"
try {
    New-Item -ItemType Directory -Force -Path $stagePackage | Out-Null
    Get-ChildItem -LiteralPath $source -File -Filter "*.py" |
        Copy-Item -Destination $stagePackage -Force
    Compress-Archive -LiteralPath $stagePackage -DestinationPath $output -CompressionLevel Optimal -Force
}
finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $output
Write-Output "Built: $output"
Write-Output "SHA256: $($hash.Hash)"
