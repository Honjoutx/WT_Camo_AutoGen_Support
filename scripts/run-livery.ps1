param(
    [string]$BlenderPath = "",
    [string]$ModelPath = "",
    [string]$PresetPath = "config\liveries\pantsyr-woodland-v1.json",
    [string]$OutputDir = "outputs\pantsyr-woodland-v1"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "project-env.ps1")

$blender = Resolve-BlenderExecutable -BlenderPath $BlenderPath
$ModelPath = Resolve-CamoProjectPath -Path $ModelPath -ProjectRoot $projectRoot -DefaultRelativePath "SMSV\pantsyr_sm_sv_fix.obj"
$PresetPath = Resolve-CamoProjectPath -Path $PresetPath -ProjectRoot $projectRoot
$OutputDir = Resolve-CamoProjectPath -Path $OutputDir -ProjectRoot $projectRoot
$pipeline = Join-Path $projectRoot "skills\blender-vehicle-livery\scripts\pipeline.py"

foreach ($path in @($blender, $ModelPath, $PresetPath, $pipeline)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path not found: $path"
    }
}

Initialize-CamoProjectEnvironment -ProjectRoot $projectRoot

& $blender --background --factory-startup --python-exit-code 1 --python $pipeline -- `
    --model $ModelPath `
    --preset $PresetPath `
    --output $OutputDir

if ($LASTEXITCODE -ne 0) {
    throw "Blender livery pipeline failed with exit code $LASTEXITCODE"
}
