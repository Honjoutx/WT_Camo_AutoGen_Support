param(
    [string]$BlenderPath = "",
    [string]$ModelPath = "",
    [string]$PresetPath = "config\liveries\pantsyr-woodland-v1.json",
    [string]$AnimeProjectPath = "config\anime-liveries\pantsyr-anime-template.json"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "project-env.ps1")

$blender = Resolve-BlenderExecutable -BlenderPath $BlenderPath
$ModelPath = Resolve-CamoProjectPath -Path $ModelPath -ProjectRoot $projectRoot -DefaultRelativePath "SMSV\pantsyr_sm_sv_fix.obj"
$PresetPath = Resolve-CamoProjectPath -Path $PresetPath -ProjectRoot $projectRoot
$AnimeProjectPath = Resolve-CamoProjectPath -Path $AnimeProjectPath -ProjectRoot $projectRoot
$openScript = Join-Path $projectRoot "skills\blender-vehicle-livery\scripts\open_vehicle.py"

if (-not (Test-Path -LiteralPath $blender)) {
    throw "Blender executable not found: $blender"
}
if (-not (Test-Path -LiteralPath $ModelPath)) {
    throw "Vehicle model not found: $ModelPath"
}
if (-not (Test-Path -LiteralPath $PresetPath)) {
    throw "Livery preset not found: $PresetPath"
}
if (-not (Test-Path -LiteralPath $AnimeProjectPath)) {
    throw "Anime livery project not found: $AnimeProjectPath"
}

Initialize-CamoProjectEnvironment -ProjectRoot $projectRoot
$env:BLENDER_HOST = "localhost"
$env:BLENDER_PORT = "9876"
$env:CAMO_DEFAULT_PRESET = $PresetPath
$env:CAMO_DEFAULT_ANIME_PROJECT = $AnimeProjectPath

& $blender --addons blender_mcp,vehicle_livery_panel --python-exit-code 1 --python $openScript -- --model $ModelPath
