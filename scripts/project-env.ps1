function Resolve-CamoProjectPath {
    param(
        [AllowEmptyString()][string]$Path,
        [Parameter(Mandatory = $true)][string]$ProjectRoot,
        [AllowEmptyString()][string]$DefaultRelativePath = ""
    )

    $candidate = $Path
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $candidate = $DefaultRelativePath
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($candidate)) {
        return [System.IO.Path]::GetFullPath($candidate)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $candidate))
}

function Resolve-BlenderExecutable {
    param([AllowEmptyString()][string]$BlenderPath = "")

    foreach ($candidate in @($BlenderPath, $env:BLENDER_PATH)) {
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $resolved = [System.IO.Path]::GetFullPath($candidate)
            if (Test-Path -LiteralPath $resolved -PathType Leaf) {
                return $resolved
            }
        }
    }

    foreach ($commandName in @("blender", "blender.exe")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }

    throw "Blender was not found. Pass -BlenderPath or set the BLENDER_PATH environment variable."
}

function Initialize-CamoProjectEnvironment {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)

    $env:BLENDER_USER_CONFIG = Join-Path $ProjectRoot ".blender\config"
    $env:BLENDER_USER_SCRIPTS = Join-Path $ProjectRoot ".blender\scripts"
    $env:BLENDER_USER_EXTENSIONS = Join-Path $ProjectRoot ".blender\extensions"
    $env:BLENDER_USER_DATAFILES = Join-Path $ProjectRoot ".blender\datafiles"
    $env:DISABLE_TELEMETRY = "true"
    $env:CAMO_PROJECT_ROOT = $ProjectRoot
}
