# WT_Camo_Auto_Gen

Blender Vehicle Livery Skill and structure-aware anime/itasha design pipeline.

A project-local Blender pipeline and Codex skill for procedural vehicle paint,
directional image projection, anime/itasha wraps, structure-aware radar and
panel design, material controls, hot-reloadable JSON projects, preview renders,
and `.blend`/GLB delivery.

The repository contains the reusable implementation only. Source vehicle
models, character artwork, reference images, generated textures, `.blend`
masters, and render outputs are intentionally excluded from Git.

## Included modules

- `skills/blender-vehicle-livery/`: Codex skill, Blender Python implementation,
  control panels, tests, schemas, iteration rules, and reusable style cards.
- `scripts/`: portable PowerShell launchers for procedural and layered anime
  pipelines, plus the project-local Blender MCP launcher.
- `config/`: reusable JSON project templates and a procedural paint example.
- `requirements-mcp.txt`: pinned Blender MCP Python dependency.

## Requirements

- Blender 4.x or 5.x; the current pipeline was validated with Blender 5.2 LTS.
- Python 3.11+ for project-side asset helpers.
- PowerShell 7 or Windows PowerShell 5.1 for the included launchers.
- `blender-mcp==1.6.4` when MCP live control is required.

Set Blender once per shell, or pass `-BlenderPath` to a launcher:

```powershell
$env:BLENDER_PATH = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
```

## Run the layered livery pipeline

Keep user-owned files outside Git (for example under `SMSV/` and `assets/`),
then run:

```powershell
.\scripts\run-anime-livery.ps1 `
  -ModelPath ".\SMSV\vehicle.obj" `
  -ProjectPath ".\config\anime-liveries\pantsyr-anime-template.json" `
  -OutputDir ".\outputs\anime-test"
```

The authoritative output is the generated layered `.blend`; previews and
`report.json` are written beside it.

## Start Blender with MCP and live panels

Create a project-local environment and install the MCP dependency:

```powershell
python -m venv .tools\blender-mcp-env
.\.tools\blender-mcp-env\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

Then launch Blender with a model and the default project templates:

```powershell
.\scripts\start-blender-mcp.ps1 -ModelPath ".\SMSV\vehicle.obj"
```

The launcher keeps Blender configuration, scripts, extensions, and MCP state
inside the repository's ignored local directories.

## Asset and privacy boundary

Do not commit licensed models, character art, private reference packs, generated
renders, or credentials. The supplied `.gitignore` excludes the current local
asset/output directories and common 3D binary formats. Review `git status`
before every push when introducing a new asset location.
