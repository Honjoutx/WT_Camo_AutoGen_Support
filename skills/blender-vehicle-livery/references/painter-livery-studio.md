# Substance 3D Painter Vehicle Livery Agent

Use this reference when the active host is Adobe Substance 3D Painter. The canonical plugin source is:

`painter_plugins/vehicle_livery_studio/`

The validated local host is Substance 3D Painter 11.0.1 at:

`C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe`

Painter 10.1 or newer is required because this plugin uses PySide6 and the modern Layer Stack API.

## Install and launch

From the repository root:

```powershell
.\scripts\install-painter-livery-plugin.ps1
.\scripts\start-painter-livery.ps1
```

The installer copies the package into:

`%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\vehicle_livery_studio`

The launcher sets `CAMO_PROJECT_ROOT`, adds Painter's user Python directory to the plugin search path, and requests `vehicle_livery_studio` as a startup plugin for that process only. For an ordinary Painter launch, enable `vehicle_livery_studio` from Painter's Python plugin manager, then open **Window > Vehicle Livery Agent**.

For service-only recovery or diagnostics:

```powershell
.\scripts\start-painter-agent-service.ps1 -Port 8766
.\scripts\stop-painter-agent-service.ps1 -Port 8766
```

Build a distributable ZIP with:

```powershell
.\scripts\build-painter-livery-plugin.ps1
```

## Native panel workflow

1. Open or create an `.spp` project and wait until it is editable.
2. Select the intended Texture Set, move the 3D camera to the desired design angle, then click **截图并框选设计区域**.
3. Frame the visible model surface. The plugin saves the complete Painter window, selected crop, pixel/normalized rectangle, Painter context, active stack, and source paths.
4. Use **参考素材库** to search project images, then drag or double-click chosen assets into the Agent reference tray. The tray also accepts image files from Windows Explorer and attempts to recognize Painter Assets whose drag payload exposes a `resource://` identifier. External files are copied as versioned project references under `assets/painter-library/references/`.
5. Enter broad art direction in **Agent + Skill** and send it. The local headless bridge reuses the existing Codex/ChatGPT login and attaches the project Skill; it does not require a new API key. Up to 16 tray records are sent as visual references; they are not automatically applied or substituted for the requested result.
6. The Agent must store its bitmap inside the repository and end with:

   `LIVERY_ASSET: <project-relative-path>`

7. With automatic import enabled, the panel copies a new version into `assets/painter-library/textures/`, imports it into the open project and optional user Shelf, and records URLs/provenance in `assets/painter-library/index.json`.
8. With automatic layer creation enabled, the panel creates and selects a native Fill layer on the active stack, limits it to Base Color, assigns the project resource, and sets the selected projection mode.
9. Adjust the projection gizmo, layer mask, opacity, blending, and material channels in Painter. Inspect the captured camera direction and at least two oblique views before approval.

## Agent reference asset tray

- The browsable project library indexes images under `assets/painter-library/`, `assets/livery-studio/generated/`, `assets/anime-liveries/`, and the current source-art roots `2s38/`, `SMSV/`, and `style1/`. Search narrows the displayed paths; thumbnails load incrementally so a large library does not block the Painter dock. Dragging or double-clicking adds a reference.
- The lower tray is persistent in `painter-livery-studio/state/settings.json`. It supports multi-select removal and clear-all, deduplicates records, and sends no more than 16 references per turn.
- A local image record includes an absolute readable path, project-relative path, size, provenance, and add time. The Agent may inspect its pixels when reasoning about character identity, palette, motifs, texture, or layout.
- Painter's public Python Resource API exposes identifiers and metadata but not a general bitmap-preview/export path. When a built-in Assets drag exposes `resource://`, retain its name/type/usages as metadata. Never claim pixel-level analysis unless a local image path is also available.
- Dropping a reference never creates a layer and never changes the current primary input image. Applying or reusing a reference still requires an explicit user instruction.
- Keep fallback icons independent of `QWidget.style()` during plug-in construction. Painter can delete a temporary `QCommonStyle` wrapper during hot reload; an owned empty icon plus project-image thumbnails remains reload-safe.

## Projection-mode routing

- **Planar**: the default for screenshot-guided character posters, logos, typography, and view-oriented composition. It preserves one intended facing direction but may affect occluding geometry in the same depth volume.
- **UV**: use when the image was authored against a known UV layout or when exact seam control matters more than the captured camera view.
- **Triplanar**: use for repeating materials, weathering fields, and large continuous texture language; do not use it for undistorted character faces or typography.
- **Spherical / Cylindrical**: use only for forms and images designed for those projection volumes.

The plugin intentionally leaves final projection-frame positioning and geometry masks editable in Painter. The Agent supplies a bounded flat asset; it does not pretend that a 2D screenshot uniquely identifies every covered polygon.

## Project records

- Captures: `painter-livery-studio/state/captures/`
- Settings: `painter-livery-studio/state/settings.json`
- Runtime probe: `painter-livery-studio/state/runtime.json`
- Versioned image library: `assets/painter-library/textures/`
- Resource index: `assets/painter-library/index.json`
- Generated Agent images: `assets/livery-studio/generated/`

Do not store API credentials in these records. Resource records may contain source paths and Painter resource URLs but must remain project-local.

## Failure routing

- If the panel does not appear, confirm Painter is 10.1+, the package is in the user `python/plugins` directory, and the plugin is enabled. Launching through `start-painter-livery.ps1` bypasses the remembered enable state by requesting it as a startup module.
- If startup reports `Internal C++ object (QCommonStyle) already deleted`, install plugin `0.3.1` or newer and reload once. This build no longer queries a transient style wrapper while constructing the reference tray.
- If Agent connection fails, validate `<repository>\livery-workbench\server.py` and the local Codex login. The panel starts the bridge headlessly at `http://127.0.0.1:8766`.
- A DCC host may start with a reduced `PATH`. Resolve Codex in this order: `CAMO_CODEX_PATH`, normal command lookup, then the newest `openai.chatgpt-*` VS Code/Cursor extension executable. Do not treat a generic `{"ok": true}` endpoint as compatible; require the project service ID and API version before enabling Send.
- Preserve JSON error details returned by the local service. Show “Codex CLI not found”, authentication, or App Server errors directly in the Painter panel instead of reducing them to an opaque HTTP 404/400 label.
- If resource import works but layer creation fails, confirm an `.spp` is open, Painter is in edition state, the correct Texture Set is active, and **嵌入当前 .spp 工程** was enabled.
- If the image hits unwanted parts, use a Painter mask, refine the Planar depth/orientation, or switch to a known UV workflow. Do not solve shared-geometry contamination by blindly stacking more projections.
- If characters or lettering distort, keep their bitmap aspect unchanged and adjust uniform projection scale, crop, padding, or UV layout.
