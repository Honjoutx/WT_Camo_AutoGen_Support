# Project and surface contracts

All paths below are relative to the configured workspace unless stated otherwise. Use `project_cli.py` to create a fresh board project or register a validated existing model project. Registry entries are local data, not Git source.

```json
{
  "active_project": "vehicle-study",
  "projects": {
    "vehicle-study": {
      "id": "vehicle-study", "name": "Vehicle study",
      "type": "boards", "directory": "projects/vehicle-study",
      "shared_library": "common", "models": []
    }
  },
  "libraries": {"common": {"id": "common", "name": "Shared", "roots": [], "imports": "assets/shared/imported"}}
}
```

## Editable boards

`type=boards` uses `model-project.json` with a `regions` dictionary. Each region has `id`, `name`, `group`, `viewbox: [width,height]` and `pixels`. Its SVG is `sources/<id>-editable.svg`; optional guides and preview PNGs are `guides/<id>.svg`, `previews/<id>.png`. The first graphical child MUST have index 0: put the immutable reference rect before `<defs>`, or put definitions inside that child. Every SVG graphical child becomes a source layer `node-<actual-child-index>`. Use `data-layer-label` for UI labels. Sources must be self-contained SVGs.

The first layer is immutable and retained at the bottom. All original source layers must remain in a saved layout; hide instead of deleting. Imported assets may be deleted. `data-metallic`, `data-roughness`, `data-relief-mm` specify defaults on surface projects. Plain text layers with a single `<text>` can be edited; multiline artwork stays a shape. Board PNG/SVG exports are composition studies and have no claimed UV mapping.

Layout schema: `livery-layout/v2`, matching `project_id`, `project_signature` (contract file SHA-256), `active_region`, and all `regions`. Each layer records source/asset ID, uniform scale, tx/ty, rotation, flip flags, pivot, opacity, visibility, locking, text, material and shadow. Obtain an initial state from the project class rather than constructing these fields by hand. Save `state/current.json` atomically. Surface projects store layout at `state/surface-<surface-directory-basename>/current.json`.

## Original atlas documents

`type=native-uv` additionally requires `model`, `repair_manifest`, `source_sha256`, and per-region `color_map`, `texture_name`, `source_sha256`, `mask` in `model-project.json`. Native documents currently use square 2048 SVG coordinates. Per-region masks live at `masks/<id>.png`; reference image at `previews/assembled.png`. Regions are editing domains; multiple domains may refer to one original atlas.

Repair manifest `materials` maps original material names to recipes (`map_Kd`, optional `map_normal`). Keep original texture bytes under the model directory's `textures/`. Never infer game packed PBR channel semantics without a source contract.

## Physical-plane projects

`type=surface-planes`, config `surface_directory=surfaces/v1`. `<surface_directory>/contract.json` has `model`, `model_sha256`, `native_contract` (path from project root), `capture_session` and `capture_bindings` (paths from surface directory), and `regions`. `capture_session` JSON must contain matching `model_sha256`.

For each region, provide a self-contained `sources/<id>-editable.svg`, `masks/<id>.png`, `guides/<id>.svg`, `previews/<id>.png`, `capture/<id>-context.png`. Reference `viewbox`, optional `view_origin`, `pixels`, `world_plane {origin,u,v,normal}`, and `physical_size_m` in the region. SVG `<defs>` must define a luminance mask `surface-footprint` in art coordinates; place defs after the readonly reference so that its layer is `node-0`. Artwork is clipped to this footprint on export; reference art is removed.

Capture NPZ keys: `<id>_selected_face_ids` integer triangle indices and `<id>_art_uv` float `[triangle,3,2]`, normalized art coordinates matching those triangles. The model directory needs:

- `source-bindings.npz`: `vertices [V,3]`, `tri [T,3]`, `uv_fixed [UV,2]`, `tex [T,3]`, `material_index [T]`, `owner [T]`, `paint [T]`; optional `source_object [T]` for auditing. Triangle order is canonical across all these files.
- `face-material-domains.npy`: string domain per triangle, matching native contract region keys.
- Repaired `.blend` for model preview. Preserve original geometry, corner normals and UVs. Material custom properties `color_domain` and `source_mtl_recipe` plus texture node label `map_Kd` connect preview material updates.

Do not invent these files from approximate image-space rectangles. Use actual triangles and physical coordinate transforms; verify source mesh and UV hash, domain ownership, selected face counts, shared texel conflicts and slopes. See `surface_bake.py`, `native_atlas_export.py` for the executable contract and `docs/deployment.zh-CN.md` for deployment boundaries.
