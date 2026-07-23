param(
    [string]$BlenderPath = "",
    [string]$ModelPath = "",
    [string]$ProjectPath = "config\anime-liveries\pantsyr-anime-template.json",
    [string]$OutputDir = "outputs\pantsyr-anime-template"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "project-env.ps1")

$blender = Resolve-BlenderExecutable -BlenderPath $BlenderPath
$ModelPath = Resolve-CamoProjectPath -Path $ModelPath -ProjectRoot $projectRoot -DefaultRelativePath "SMSV\pantsyr_sm_sv_fix.obj"
$ProjectPath = Resolve-CamoProjectPath -Path $ProjectPath -ProjectRoot $projectRoot
$OutputDir = Resolve-CamoProjectPath -Path $OutputDir -ProjectRoot $projectRoot
$pipeline = Join-Path $projectRoot "skills\blender-vehicle-livery\scripts\anime_pipeline.py"

foreach ($path in @($blender, $ModelPath, $ProjectPath, $pipeline)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path not found: $path"
    }
}

Initialize-CamoProjectEnvironment -ProjectRoot $projectRoot

& $blender --background --factory-startup --python-exit-code 1 --python $pipeline -- `
    --model $ModelPath `
    --project $ProjectPath `
    --output $OutputDir

if ($LASTEXITCODE -ne 0) {
    throw "Blender anime livery pipeline failed with exit code $LASTEXITCODE"
}
