---
name: blender-vehicle-livery
description: Inspect, design, apply, live-preview, and export vehicle liveries through Blender MCP and the native Adobe Substance 3D Painter Vehicle Livery Agent plugin. Use for anime wraps, character decals, camouflage, paint, screenshot-framed Painter design, native Fill/Planar/UV/Triplanar projection layers, Agent-assisted asset generation, material tuning, and .spp, .blend, .obj, .fbx, .gltf, or .glb work.
---

# Vehicle Livery for Blender and Substance 3D Painter

Use Blender MCP for live scene access and the bundled scripts for deterministic vehicle processing. Preserve source assets and write every generated file to a new output directory.

For the browser-based physical-plane editor, use `.agents/skills/wt-camo-workflow/SKILL.md` and its current project contract. The sections below cover the optional older Blender/Painter pipelines. Apply profile-specific symmetry, hero protection and continuity gates only when enabled in the current project; do not inherit a past theme or force an old profile onto a new brief. Save iteration evidence inside the selected local project, not in this shared skill or a public case history.

## Workflow

1. Confirm the `blender` MCP server is available. If the current session predates MCP registration, ask the user to restart the session after configuration.
2. Inspect the model before editing. Use `get_scene_info` and `get_object_info`, or run `scripts/audit_vehicle.py` in Blender.
3. Read [references/model-contract.md](references/model-contract.md) when object/material separation or UV suitability is unclear.
4. Create or select a JSON preset following [references/preset-schema.md](references/preset-schema.md).
5. Match paint targets by explicit object-name patterns. Never assign paint to every mesh unless the user explicitly requests it.
6. Apply the material with `scripts/pipeline.py` or import `scripts/blender_livery_core.py` from a bounded `execute_blender_code` call.
7. Render at least two preview angles. Inspect the previews before reporting success.
8. Save a new `.blend`, export a `.glb`, and retain `report.json` with the exact targets and preset.

When the user is already texturing in Adobe Substance 3D Painter, or wants native Painter layers and projection gizmos, use the Painter workflow below.

## Native Substance 3D Painter workflow

1. Read [references/painter-livery-studio.md](references/painter-livery-studio.md). Use Painter 10.1+; the project implementation is validated against Painter 11.0.1, Python 3.11, PySide6, and the Layer Stack API.
2. Install with `scripts/install-painter-livery-plugin.ps1`, then launch with `scripts/start-painter-livery.ps1`. The launcher sets the project root and requests `vehicle_livery_studio` as a startup plugin for that Painter process; it does not alter the global registry.
3. Work only in the native **Window > Vehicle Livery Agent** dock. Keep the Agent bridge headless; do not open the legacy browser workbench for a Painter task.
4. Rotate the Painter 3D viewport to the intended projection view, click **截图并框选设计区域**, and frame the actual target surface. Treat the screenshot rectangle as a visual-generation boundary and composition reference, not as proof of face ownership or UV coverage.
5. Before sending, optionally drag up to 16 existing project images, external image files, or exposed Painter Asset records into **参考素材库**. Stage external images under `assets/painter-library/references/`, send them as `reference_assets`, and treat them only as visual inputs—not automatic output or applied texture. Then send the saved full screenshot, selected crop, normalized frame, Painter version, project/mesh path, texture-set summary, active stack, optional primary input image, projection mode, and output contract through the local Agent bridge. Explicitly attach this Skill on every turn.
6. Require the Agent result to end with `LIVERY_ASSET: <project-relative-path>`. Keep generated files under `assets/livery-studio/generated/`, then copy/import a versioned source into `assets/painter-library/textures/`. Never overwrite an earlier result.
7. Import the result into the open `.spp` project and optionally the user Shelf. For an editable applied result, create a native Fill layer on the active texture-set stack, activate only Base Color, assign the imported project texture, set the chosen projection mode, and select the new layer.
8. Use **Planar** for view-oriented character posters and framed decals, **UV** for artwork authored against a known UV layout, and **Triplanar** for repeating/continuous material texture. Use Spherical or Cylindrical only when the physical form and artwork genuinely require them.
9. After layer creation, manually adjust Painter's projection gizmo and masks while inspecting direct and oblique views. A screenshot-framed generation still needs Painter-side geometry masking or hand cleanup when occluding parts share the same texture set.
10. Store capture sessions under `painter-livery-studio/state/captures/`, resource provenance in `assets/painter-library/index.json`, and plugin runtime evidence in `painter-livery-studio/state/runtime.json`.

For anime artwork, character decals, logos, text, or manual-style directional image placement, use the ordered projector workflow below instead of assigning more material slots.

## Anime image-layer workflow

1. Read [references/anime-project-schema.md](references/anime-project-schema.md). When the user asks to follow a visual style or supplies references, also read [references/style-library.md](references/style-library.md). For broad flat surfaces or icon decals, read [references/macro-composition-and-decals.md](references/macro-composition-and-decals.md).
2. Define coarse explicit `target_groups` such as body and turret. Treat small attached parts inside those meshes as geometry to avoid spatially, not as separate materials.
3. Store provided images under `assets/anime-liveries/<project>/`. When artwork must be generated, create a transparent-background raster asset first, retain its prompt in `source.prompt`, and then reference the saved file from the project JSON. Record its pixel dimensions and check the effective aspect ratio after `image_region` cropping.
4. Add layers bottom-to-top: base, separate single-color macro blocks derived from one approved geometry plan, bounded decals and micro texture/material blocks, paired hero art, then transparent character-name text. Give blocks independent `surface` values when they need different roughness, metallic, or clear-coat response. Do not place solid color blocks, stripes, contour lines, decals, signage, dirt, or protective-effect color above hero art unless the user explicitly overrides the hero-protection rule.
5. Load the project in **二次元分层投射**, select a layer projector, and use Blender `G`, `R`, and uniform `S` controls to place it. Never use one-axis scaling on `hero_art`; change `image_region`, transparent padding, or projector position to crop/fit it. Keep `depth` narrow and raise `facing_threshold` when an image reaches the opposite side or attached parts.
6. Save the project to capture projector transforms. Keep hot reload enabled while replacing or editing image files.
7. Run `scripts/anime_pipeline.py` for deterministic previews and a new `.blend` working master.
   Use `scripts/render_anime_stages.py` when the user needs comparable base/large-pattern/fine-pattern/artwork progression renders.
8. Bake only after verifying non-overlapping UVs; do not claim that the layered working material is engine-ready before baking.

### Side symmetry and protected hero art

- Treat the vehicle front as a world-space design direction. On both body and turret, create non-text side graphics as explicit left/right pairs with mirrored X centers and projection directions, matching size, depth, height clips, targets, and surface parameters.
- Text may use independent readable layouts. Do not mirror glyphs; verify each side from its own exterior camera.
- For a shared character image, use opposite horizontal sampling on the two side projectors so the face is toward the vehicle front on both sides. Confirm this in left-front and right-front renders rather than relying only on metadata.
- Mark layers with `side`, `semantic_role`, `pair_id`, and, for side hero art, `face_toward: "front"`. Enable the matching `design_rules` checks in the project.
- Place all supporting color blocks and patterns below both `hero_art` layers. Above the first hero-art entry, only transparent `character_name` layers are allowed; the name bitmap itself must contain glyphs only, with no opaque panel, stripe, arrow, dot, or decorative color block.
- Render left side, right side, left front, and right front before approval. Compare body and turret placements as pairs, confirm both faces point forward, and inspect the character silhouette for overprinting.

### Image proportion and typography

- Set `aspect_policy: "PRESERVE"` on every `hero_art` layer. Its projector width/height must match the sampled bitmap ratio after `image_region`; the validator permits only 0.5% numeric tolerance. Do not make a character fit a shallow armor panel by scaling X or Y alone.
- Use `aspect_policy: "LIMIT"` on patterns, masks, and ordinary graphics. Default to no visible distortion and keep the maximum aspect distortion at or below 8%; prefer cropping, tiling, transparent padding, or a larger projection volume with world-height clipping over stretching.
- Keep character-name images aspect-safe too. Use transparent glyph-only assets and place them in an intentional body zone away from the character face. Check that the primary name is readable without dominating the face and that secondary text survives both side and three-quarter views.
- Treat a text safe zone as a rendered visibility region, not just projector coordinates. Turret skirts, cages, tools, and other real geometry can occlude the upper body band. If both sides need the name toward the rear, build separate left/right glyph-only layouts instead of mirroring glyphs or reusing one canvas placement.
- For the mint industrial style, prefer angular, condensed industrial glyphs such as Agency/Bahnschrift-like forms. Preserve readability and use outline/fill contrast as part of the glyph; do not add panels, arrows, dots, stripes, or other non-text blocks above the hero layer.
- Treat `projection.size` as the image frame, not a free deformation control. The report's `aspect_layers` section must pass before visual approval.

### Structure-first surface design

- Before drawing or generating artwork for a newly designed vehicle surface, render a projector-aligned structure guide from the real target mesh. Use `scripts/render_surface_structure_guide.py` with the intended center, direction, up vector, size, depth, facing threshold, and world-height clip. Do not begin surface artwork from an unverified blank canvas.
- The guide must isolate the explicit target mesh, remove coplanar triangulation noise, retain silhouette and hard feature edges, and write both a transparent PNG and metadata JSON. The metadata must include the projector frame, canvas-to-world scale, visible polygon counts, and hard-edge-separated surface patches.
- Select intentional surface patches before composing the design. Keep panel seams, hinges, lamps, vents, cables, tow points, latches, and protruding hardware transparent unless the design explicitly treats that hardware as its own separate mask.
- Use `scripts/compose_guided_livery_asset.py` to place generated alpha graphics on the guide canvas. Preserve the source crop aspect ratio; fit by width or height and pad the shared canvas instead of stretching one axis.
- Keep the consuming image layer on the same projector frame as its guide. Enable `structure_guide_contract`, declare `structure_guides`, and make every newly guided layer identify its guide with `source.guide_id`.
- For bilateral front/rear surfaces, prefer paired modules fitted to paired armor patches over a single large motif crossing the center seam. Verify the direct orthogonal view first, then both three-quarter views for edge bleed and hardware interference.

### Macro coverage, per-color assets, and decals

- Treat unexplained empty space on a large flat armor plane as a design defect. Declare a target graphic-coverage range, name every intentional negative-space zone, and verify it in one direct surface view plus at least one three-quarter view. Set `coverage_basis` to the visible paintable structure-guide patches after excluding those named zones; never calculate coverage against the full projector canvas, which may contain empty background and unrelated hardware. Start around 62-88% coverage; preserve explicit face, hardware, seam, hatch, vent, and turret-ring clearances instead of flooding the surface.
- Complete and approve one multicolor geometry plan on the projector-aligned structure-guide canvas before generating production masks. The plan must resolve polygon boundaries, shared edges, symmetry, cross-surface returns, color assignment, and negative space as one composition.
- Derive a separate transparent single-color asset from that same plan for every color block. Keep all assets on the shared guide canvas, give each block its own layer and `surface` values, and record `source.geometry_plan_id`, `source.color_block_id`, and `source.single_color_asset: true`.
- Add icons only after the macro geometry reads correctly. Use `semantic_role: "decal"`, one to three normalized style families, no more than four decals per large surface, and no more than twelve enabled decal layers by default. Place them in named functional zones and keep them below hero art.
- Online icon search is allowed when it materially supports the chosen style. Inspect the current official source and license page, prefer transparent/openly licensed assets, and record URL, license, and retrieval date. Do not use restricted logos, insignia, signatures, or source-specific identity without authorization.
- Enable `macro_geometry_asset_contract` and declare `macro_composition`. The validator checks plan/guide records, coverage budgets, exact per-color asset mappings, decal density/style-family limits, and provenance. Render review still determines whether the visible coverage and hierarchy are successful.

### Roof, front, and rear surfaces

- Design the body roof/deck, front, and rear as independent compositions. Do not rotate a side graphic onto another surface. Keep all three below hero-art layers unless the user explicitly requests focal artwork there.
- Mark layers with `side: "top"`, `"front"`, or `"rear"`. Top projectors point world `-Z`; front projectors enter from the vehicle nose toward world `+Y`; rear projectors enter from the tail toward world `-Y`.
- For a body-roof request, target only the body group and localize the projector over the intended deck so it does not paint the turret/radar. Use a narrow projection depth and facing threshold for front/rear faces to avoid dragging the pattern along side panels.
- Derive projection depth from the actual target surface, not the scene maximum. Before rendering, verify that the intended world-space surface lies inside `center ± depth/2` along the projection axis; for a downward roof projector, its lowest Z must be below the roof polygons. A correctly oriented projector can still produce no paint when its volume floats above the geometry.
- Front and rear non-text graphics should be bilaterally symmetric around world X. Use distinct assets: a forward-converging grammar may suit the nose, while the rear should terminate or anchor the visual flow instead of repeating the same arrow.
- Add direct `top_check`, `front`, and `rear` render views, then retain the side and three-quarter views to catch edge bleed. Enable `surface_direction_contract` and `front_rear_bilateral_graphics` in the project.

### Cross-surface edge continuity

- When a roof must connect to existing left, right, front, and rear macro blocks, inventory the colors and visual flow arriving at all four perimeter edges before drawing. Record them as `source.edge_connections` on the guided body-top layers and enable `edge_continuity_contract`.
- Use a body-only full-roof structure guide whose frame reaches the real body bounds. Restrict older generic top layers to the turret when they would otherwise compete with the redesigned body roof.
- Build continuity as overlapping returns: a rear terminal band enters paired longitudinal shoulder rails through chamfered rear corners, and those rails split into paired front shoulders through chamfered front corners. Do not terminate both adjacent color blocks on the same straight edge or meet them with an isolated 90-degree corner.
- Keep a large base-color negative space around the turret ring and the centers of major service hatches. A perimeter wrap should read as one controlled route rather than covering every top-facing polygon.
- Split broad main colors and transition highlights into separate image layers when they need different roughness, metallic, or clear-coat response. Both layers must reuse the same full-roof guide frame without one-axis stretching.
- Add `left_front_top`, `right_front_top`, `left_rear_top`, and `right_rear_top` views in addition to `top_check`. Inspect all four high corner views for abrupt terminations, side-art intrusion, and projector spill.

### Turret and radar equipment surfaces

- Treat a coarse turret mesh as several visual zones even when Blender exposes only one object: paired left/right turret skirts, turret roof hardware, radar front antenna face, radar rear service doors, and radar ribbed top. Render a separate projector-aligned structure guide for every newly designed zone.
- Keep turret-side non-text layers in explicit mirrored pairs. Use identical world Y/Z placement, size, depth, height clips, and surface values with X-mirrored centers and opposite directions. Keep side character faces toward world `-Y` on both sides by using opposite horizontal sampling, never one-axis scaling.
- Do not let a turret-skirt projector reach the radar, weapons, optical dome, support frame, or cage. Use the side surface depth and facing threshold to select the outer skirt, then use world-height clipping as a secondary safety boundary.
- Do not reuse a whole-turret guide frame for focal character placement when the paintable skirt occupies only a thin edge of that canvas. Render a second panel-local hero guide around the real flat armor patch; position the face inside visible guide geometry, and let transparent hair/shoulder edges crop naturally outside the panel.
- Treat air-defense radar graphics as equipment-specific layers. The radar front, rear, and top require independent images and projectors: emphasize a centered detection/scan hierarchy on the clean front face, organize the rear around paired service doors while leaving the center seam, vents, hinges, and pods clear, and use the top reinforcing ribs as the rhythm grid.
- Split a roof antenna's front assembly into its real visible zones. A tilted main screen and a lower forward subpanel/pedestal may occupy different projector depths even when they look like one rectangle in a direct render. Derive a model-space required depth range from the guide metadata or face audit, and require every consuming layer's half-depth to cover that entire range; a guide image alone does not prove volume intersection.
- Treat any separate turret-forward square radar or sensor panel as its own equipment zone. Give it a dedicated tight structure guide, geometry plan, single-color layers, projector volume, and verification view; never assume the roof antenna's `front` layer satisfies another front-facing radar surface.
- When the user asks for character-related equipment icons, abstract a small number of visible motifs from the provided artwork or verified character description, then create an original no-text/no-logo functional glyph. Prefer deterministic vector-like geometry for simple frog, snake, flower, ribbon, or sensor symbols; record the local reference, research URLs, prompt/design intent, and that no online bitmap was copied.
- Split each radar surface into a main-color layer and sparse metallic/detail islands when they need different roughness, metallic, or coat response. Keep both layers on the same guide frame for that surface.
- Enable `radar_isolation_contract`, declare project-level `radar_isolation`, mark radar layer sources with `equipment_role: "radar"` and a specific `equipment_zone`, and set model-derived global/per-zone minimum Z values. When `required_equipment_zones` is present, the validator requires every zone, its guide ID, its dedicated view, and any declared `required_depth_range` to be covered by the projector depth.
- Remove or disable earlier generic turret-top layers when they paint both turret structures and the radar. Never rotate one radar bitmap across the other two radar surfaces.
- Render `radar_front_check`, `radar_rear_check`, and `radar_top_check` in addition to the normal paired side and three-quarter views. Verify that the radar remains readable, service hardware stays visible, and no character art reaches the radar.

### Iteration feedback loop

Every visual trial must leave reusable knowledge in the Skill during the same iteration:

1. Record the observed problem, likely cause, applied change, and validation result in the current project's local iteration record. Use [references/iteration-log.md](references/iteration-log.md) only as a generic template.
2. Update the durable rule in this `SKILL.md` and, when machine-checkable, in the project schema and `anime_livery_core.py` validator. Update the active versioned style card when the finding is style-specific.
3. Add an `iteration_record` to the trial project, list the Skill files updated, and enable `design_rules.record_iteration_in_skill`.
4. Render a new output directory; never rewrite a previously approved trial. A trial is not complete when only its JSON or bitmap was tweaked.

## Style selection and reference decomposition

Use `scripts/style_catalog.py list` to discover built-in cards and `show <style-id>` to inspect one. Style cards live in `assets/styles/`; each card captures palette roles, composition hierarchy, motif grammar, hero-art treatment, surface language, generation prompts, avoid rules, and provenance.

When given an excellent reference design, abstract its reusable visual grammar instead of copying source-specific logos, text, signatures, or character assets. Create a versioned style card, validate the catalog, set `style_id` in the project, and copy the selected values into explicit base/layer fields so the project remains deterministic. Split micro-texture islands into separate projection layers whenever they require different surface parameters.

## Live Blender controls

Start Blender with `scripts/start-blender-mcp.ps1`, open the 3D View sidebar with `N`, and select the **Vehicle Livery** tab.

- Use **加载并应用** to load the selected JSON and assign it to explicit targets.
- Keep **面板参数实时更新** enabled to update colors, noise, roughness, metallic, and micro-bump nodes on the last successfully applied material while dragging controls.
- Keep **自动重载 JSON** enabled to detect preset saves from an external editor and update visual material parameters without restarting Blender.
- Require **加载并应用** confirmation when external JSON or a newly selected preset changes `material_name` or `target_objects`. Apply the incoming visual parameters immediately, but retain the material and targets from the last successful **加载并应用** or **应用面板参数** action until that click.
- Use **保存 JSON** to atomically persist the current controls.
- Click **应用面板参数** after changing material name or target object patterns; never hot-apply target changes silently.
- Use **材质预览** for fast interaction and **渲染预览** for scene-lighting accuracy.
- Use **二次元分层投射** for image projects. **加载/重建** confirms target groups, **选择投射器** exposes manual placement, and **保存工程** writes transforms back to JSON.
- In **图层材质块**, enable independent surface control and drag roughness, metallic, clear-coat intensity, and clear-coat roughness live. Toggling the block rebuilds the graph; value sliders update existing nodes immediately.
- Loading an anime project pauses the base-preset auto-reloader so it cannot overwrite per-object layered materials.

## MCP tool mapping

- Use `get_scene_info` to inventory the active scene.
- Use `get_object_info` to verify candidate paint targets.
- Use `get_viewport_screenshot` for quick visual feedback.
- Use `execute_blender_code` only to invoke bundled, reviewed scripts or short read-only inspection code.
- Avoid asset-download and arbitrary external-code features unless the user explicitly requests them.

To invoke a bundled script from Blender MCP, resolve the skill directory first and use a small loader such as:

```python
import runpy
module = runpy.run_path(r"<skill-dir>\scripts\blender_livery_core.py")
result = module["audit_scene"]()
```

## Local execution

Run the complete default pipeline from the project root:

```powershell
.\scripts\run-livery.ps1
```

Start the portable Blender instance with its MCP add-on:

```powershell
.\scripts\start-blender-mcp.ps1
```

Pass a different preset when needed:

```powershell
.\scripts\start-blender-mcp.ps1 -PresetPath .\config\liveries\alternate.json
```

Pass or batch-build an anime layer project:

```powershell
.\scripts\start-blender-mcp.ps1 -AnimeProjectPath .\config\anime-liveries\my-project.json
.\scripts\run-anime-livery.ps1 -ProjectPath .\config\anime-liveries\my-project.json
```

Inspect or validate the reusable style library:

```powershell
python .\skills\blender-vehicle-livery\scripts\style_catalog.py list
python .\skills\blender-vehicle-livery\scripts\style_catalog.py validate
```

## Safety and quality gates

- Never overwrite the input model or its source textures.
- Reject Painter projection-layer creation when no `.spp` project is open, the project is not in edition state, no active texture-set stack exists, or the texture was not imported as a retrievable Painter resource.
- For Painter's headless Agent service, resolve Codex outside the DCC process PATH when necessary, require the livery service ID/API version, and surface returned JSON error details.
- Stage external reference images inside the project, deduplicate them, limit the tray to 16 records, and never claim pixel inspection of a metadata-only Painter `resource://` record.
- During Painter startup or hot reload, do not obtain fallback icons through a transient `QWidget.style()`/`QCommonStyle` wrapper; use an owned `QIcon` or image thumbnail.
- Treat Painter screenshot selection as an art-direction boundary only. Verify direct and oblique views, and use Painter masks or known UVs for unwanted geometry coverage.
- Keep Painter imports versioned under the project library and embed production textures into the `.spp`; a Shelf-only copy does not make the project portable.
- Reject an empty target match instead of silently painting unrelated meshes.
- Record missing MTL files, missing images, absent UV layers, and shared-material risks.
- When a project enables side-symmetry and hero-protection rules, reject missing mirror pairs, rear-facing hero metadata, or non-name layers stacked above hero art.
- Reject aspect-protected projects when hero art is non-uniformly stretched or other image layers exceed their declared distortion limit.
- Reject top/front/rear projects when projector direction conflicts with the declared surface, direct orthogonal verification views are missing, or non-text front/rear graphics lack bilateral-symmetry intent.
- Reject structure-guided projects when the guide PNG/metadata is missing, the guided layer does not declare its guide, or its projector frame differs from the frame used to render the guide.
- Reject macro-contract projects when a large plane lacks a coverage budget or documented negative space, production background layers do not map one-to-one to separate single-color assets derived from the approved geometry plan, or decal layers exceed their density/style-family budget or omit provenance.
- Reject radar projects that collapse multiple physical front-facing devices into one generic `front` zone, omit a required equipment zone, or use a projection half-depth smaller than the declared model-derived depth range.
- Reject four-edge roof-continuity projects unless body-top sources declare left/right/front/rear connections, a non-empty turn-transition strategy, and all four high corner verification views.
- Do not close a visual trial until its `iteration_record`, Skill rule, and iteration log agree with the rendered correction.
- Keep the Blender add-on and Python environment project-local.
- Resolve default Blender shader nodes by `bl_idname`, not localized UI names such as `Principled BSDF` or `Background`; non-English Blender builds translate those names and otherwise break deterministic preview setup.
- Disable Blender MCP telemetry for project runs.
- Treat procedural materials as Blender-native deliverables; bake textures before claiming compatibility with engines that cannot reproduce the node graph.
- Report when glass, tires, lights, and body panels are not separated enough for selective painting.
