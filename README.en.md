# WT Camo Auto Gen

[简体中文](README.md) · English

A vehicle livery workbench with original-UV texture export, editable surface layouts, vector artwork, per-layer PBR materials, local Codex CLI chat and background Blender integration.

The repository contains code and reusable workflow instructions. Models, character art, projects, generated files, chat history and credentials stay local.

## Windows desktop app

[Download the latest Windows app and SHA-256 checksum](https://github.com/Honjoutx/WT_Camo_Auto_Gen/releases/latest). Choose the `WT-Camo-Workbench-Windows-x64.zip` release asset; GitHub's automatically generated Source code archives do not contain the application.

Extract `WT-Camo-Workbench-Windows-x64.zip` and run **WT Camo Workbench.exe**. Keep the adjacent `_internal` folder. Python and the workbench dependencies are included.

Requires Windows 10/11 x64 and [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). Local Codex CLI and Blender are optional external programs; use Application settings to specify their paths. Codex reuses its existing sign-in.

Use the top toolbar to choose **English** or **简体中文**. The selection persists. Controls, status messages and the workflow guide are translated; artwork, project/layer names, asset filenames and conversation history remain original. New Codex requests include the selected reply language.

Projects and settings live in `%LOCALAPPDATA%/WT Camo Workbench/`, outside the application directory. Replace the application folder to upgrade while preserving this data. Choose an existing workspace in Settings and restart to reuse projects.

## Source / browser mode

Install Python 3.11–3.13, then run:

```powershell
git clone https://github.com/Honjoutx/WT_Camo_Auto_Gen.git
cd WT_Camo_Auto_Gen
.\start.cmd
```

The launcher creates an isolated environment and opens the local editor. Use `-Port 18190` if the default port is occupied. English is available in browser mode too.

```powershell
# Optional background Blender MCP, with automatic addon setup and CLI registration
.\start.cmd -WithBlenderMcp -BlenderPath "D:\Blender\blender.exe"
```

Desktop mode uses a separate MCP name and port. Its Settings button starts an isolated headless Blender session. Render previews to files; a headless session has no viewport screenshot.

## Workflow

1. Inspect source OBJ/MTL, UVs and normals. Repair proven integer UV offsets and group coarse physical assemblies without repacking UVs.
2. Record a brief and create a viewable sketch before detail design.
3. Register principal physical surfaces and original-atlas bindings; design each surface separately.
4. Adjust assets, scale, rotation, flips, clipping, opacity, shadows, metallic, roughness and relief.
5. Preview the assembled model, migrate layouts using physical anchors, and inspect mapping coverage.
6. Export only changed original atlases and selected channels, flat in one directory. 4K/8K and optional GPU computation are supported. Unbound sketches export surface PNG/SVG, not game UV textures.

Compact storage shares immutable resources and builds ZIPs on download. Use portable copies for independent handoff; do not delete assets still referenced by a project.

## Build and verify

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
.\.tools\desktop-build-env\Scripts\python.exe scripts/test-desktop.py
.\.venv\Scripts\python.exe -m unittest discover -s tools/livery-layout-editor -p "test_*.py"
```

The build produces a Windows application folder, ZIP and SHA-256 file under `dist/`. It excludes user workspaces, local settings, models and artwork. A tiny synthetic workspace is used for packaged-app tests.

See the [desktop deployment guide](docs/desktop.zh-CN.md), the English workflow guide inside the app, and the repository's [wt-camo-workflow skill](.agents/skills/wt-camo-workflow/SKILL.md). A local CLI does not inherit ImageGen or Photoshop MCP from another chat application; configure those capabilities separately.


## Export performance

The generation bar defaults to **Full speed**, with Balanced and serial Compatibility modes. Independent planes, native UV domains and original-atlas merges are scheduled against available logical CPUs and live free RAM, reserving roughly 2.5% of physical RAM (at least 256 MiB). There is no fixed thread-count cap; a single oversized task still requires its own working set to fit physical memory.

Fast PNG/NPZ writing reduces lossless compression effort, preserving pixels, bit depth, resolution and original UVs; files may be larger. Decoded planes use a memory-bounded cache. Shared-texel priorities, original face order and shared-normal grouping remain deterministic. Selecting individual output files prunes unrelated UV domains and unselected final channel merges while retaining PBR ownership dependencies.

The optional GPU path accelerates relief normals, normal composition and grain smoothing, not PNG compression. Its pool/tile size follows free VRAM at initialization rather than a fixed 4 GiB cap. Device operations share a serialized cache while CPU work continues across other domains. Missing CUDA/CuPy or device failures are reported with CPU fallback. The desktop package does not bundle the large CUDA runtime.

Each job writes resource budgets, stage timings, peak concurrency and cache counters to `evidence/export-performance.json`; GPU details remain in `export-acceleration.json`. Performance mode does not change the output naming or file-selection contract.
