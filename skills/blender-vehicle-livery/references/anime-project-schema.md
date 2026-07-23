# Anime livery project schema

Use a UTF-8 JSON project with `version: 1`. Resolve `base.preset` and layer image paths relative to the project file.

## Project fields

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer | Schema version; currently `1`. |
| `name` | string | Output-safe project identifier. |
| `style_id` | string | Optional style-library card used to derive the explicit project values. |
| `design_rules` | object | Optional enforceable composition, side-pair, face-direction, hero-stack, structure, and equipment requirements. |
| `base` | object | Flat paint values or a `preset` path to the procedural livery schema. |
| `target_groups` | object | Named groups of explicit, case-sensitive mesh-name patterns. |
| `layers` | array | Ordered bottom-to-top image projection layers. |
| `render` | object | Preview settings accepted by the normal livery pipeline. |

Use `base.color`, `base.roughness`, `base.metallic`, `base.coat_weight`, `base.coat_roughness`, `base.micro_bump_strength`, and `base.micro_bump_scale` for a flat anime base. Alternatively, set `base.preset` to a camouflage preset JSON.

Do not use a global `*` target pattern unless the user explicitly approves it and the project sets `allow_global_target: true`.

## Image layer

```json
{
  "id": "body-right-character",
  "name": "车体右侧角色",
  "type": "image_projection",
  "enabled": true,
  "side": "right",
  "semantic_role": "hero_art",
  "pair_id": "body-left-character",
  "face_toward": "front",
  "aspect_policy": "PRESERVE",
  "targets": ["body"],
  "image": "../../assets/anime-liveries/my-project/body-right.png",
  "source": {
    "kind": "generated",
    "prompt": "transparent-background production prompt"
  },
  "opacity": 1.0,
  "blend_mode": "MIX",
  "alpha_mode": "IMAGE",
  "surface": {
    "roughness": 0.48,
    "metallic": 0.0,
    "coat_weight": 0.38,
    "coat_roughness": 0.2
  },
  "projection": {
    "center": [1.58, 0.2, 1.45],
    "direction": [-1.0, 0.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "size": [5.0, 1.75],
    "depth": 0.9,
    "facing_threshold": 0.05,
    "flip_x": false,
    "flip_y": false
  }
}
```

Layer order is the compositing order. Later entries appear above earlier entries.

Optional semantic fields make visual intent machine-checkable:

- `side`: `left`, `right`, `top`, `front`, `rear`, or `center`.
- `semantic_role`: `underlay`, `decal`, `hero_art`, `character_name`, `text`, or `protective_effect`.
- `pair_id`: ID of the opposite-side layer. Paired layers must reference each other.
- `face_toward`: `front` or `rear`; side hero art should normally use `front`.
- `aspect_policy`: `PRESERVE`, `LIMIT`, or `FREE`. Use `PRESERVE` for hero art and character-name typography.
- `max_aspect_distortion`: optional per-layer fractional limit used by `LIMIT`, such as `0.08` for 8%.

Use these project rules for designs that require protected, symmetric side layouts:

```json
{
  "design_rules": {
    "paired_side_color_layers": true,
    "text_may_be_asymmetric": true,
    "hero_face_toward_vehicle_front": true,
    "only_character_name_above_hero_art": true,
    "hero_art_preserve_aspect": true,
    "max_other_aspect_distortion": 0.08,
    "record_iteration_in_skill": true,
    "surface_direction_contract": true,
    "front_rear_bilateral_graphics": true,
    "structure_guide_contract": true,
    "edge_continuity_contract": true,
    "macro_geometry_asset_contract": true
  }
}
```

With these rules enabled, every left/right non-text underlay needs a mirrored pair; side hero layers need front-facing metadata and mirrored placement; after the first hero layer, only additional hero layers and transparent `character_name` layers may follow.

`record_iteration_in_skill` also requires a project-level record:

```json
{
  "iteration_record": {
    "id": "v3-aspect-safe",
    "finding": "Hero art was stretched horizontally.",
    "change": "Matched projector size to the cropped bitmap ratio.",
    "validation": "Four exterior views and aspect audit passed.",
    "skill_updates": ["SKILL.md", "references/iteration-log.md"]
  }
}
```

Supported `blend_mode` values are `MIX`, `MULTIPLY`, `ADD`, `SCREEN`, `OVERLAY`, and `SOFT_LIGHT`.

Use `alpha_mode: "IMAGE"` for PNG/TIFF transparency. For white-background JPG artwork, use `alpha_mode: "WHITE_KEY"`, normal `MIX` blending, and optional `white_key_min`/`white_key_max` values such as `0.03` and `0.22`. The white-key range converts distance from pure white into a soft alpha mask while preserving colored artwork.

Set optional `image_region: [u0, v0, u1, v1]` to sample only part of a source image without modifying it. Coordinates are normalized from the image's bottom-left corner. Use this for portrait crops, removing source-page labels, or fitting a tall illustration onto a shallow vehicle panel.

The effective sampled aspect ratio is `(pixel_width × (u1-u0)) / (pixel_height × (v1-v0))`. Compare it with `projection.size[0] / projection.size[1]`. Distortion is `max(projected/source, source/projected) - 1`. `PRESERVE` allows at most 0.5% numeric mismatch; `LIMIT` uses the per-layer or project-wide limit. Crop or pad instead of scaling one projector axis independently.

## Per-layer material blocks

The optional `surface` object makes an image layer control material response as well as color. The exact same final mask—image alpha, opacity, facing, depth, and optional world-height clipping—blends these values over the previous surface:

- `roughness`: `0` is mirror-smooth; `1` is fully rough.
- `metallic`: `0` is dielectric paint or print; `1` is metallic.
- `coat_weight`: clear-coat intensity.
- `coat_roughness`: roughness of the clear-coat lobe.
- `enabled`: optional Boolean; set false to retain the settings without applying them.

All numeric surface values are in `[0, 1]`. Omitted channels inherit the accumulated material below the layer. To give several small texture blocks different finishes, split them into separate transparent masks/layers and assign a different `surface` object to each. One bitmap may contain multiple islands only when those islands deliberately share the same material response.

## Projection semantics

- `center`: world-space center of the projection volume.
- `direction`: world-space ray direction from the projector into the vehicle.
- `up`: image-up direction; it must not be parallel to `direction`.
- `size`: projected image width and height in Blender units.
- `depth`: total projection-volume depth. Keep it narrow enough to avoid the opposite side.
- `facing_threshold`: minimum surface-normal alignment. Increase it to suppress steep or rear-facing surfaces.
- `world_z_min`, `world_z_max`: optional world-height mask for excluding wheels, roof equipment, or other geometry that overlaps the same projection volume.
- `flip_x`, `flip_y`: mirror the bitmap inside the projection plane.

The Blender projector Empty uses local X for image width, local Y for image height, and local -Z for projection direction. Select it from the panel and use `G`, `R`, and `S` for live manual placement. Save the project to write all projector transforms back to JSON.

For orthogonal vehicle surfaces, use these world-direction contracts:

- `side: "top"`: projection direction `[0, 0, -1]`.
- `side: "front"`: the vehicle nose is world `-Y`, so project inward with `[0, 1, 0]`.
- `side: "rear"`: the vehicle tail is world `+Y`, so project inward with `[0, -1, 0]`.

When `surface_direction_contract` is enabled, the project must also render `top_check`, `front`, and/or `rear` for every active orthogonal surface. With `front_rear_bilateral_graphics`, non-text front/rear layer sources must declare `bilateral_symmetric: true`.

Direction validation does not prove volume intersection. For each layer, compare the projector interval with the target surface along its ray axis. A top projector at `center.z=4.6`, `depth=5.0` covers Z `2.1..7.1`; it will miss a body roof below Z 2.1 even though its direction and facing threshold are correct. Use actual model bounds or a first orthogonal render to lower/extend the volume without reaching unrelated opposite surfaces.

## Structure guides

When `structure_guide_contract` is enabled, declare every surface guide used by newly designed layers:

```json
{
  "structure_guides": [
    {
      "id": "front-body-v5",
      "side": "front",
      "targets": ["body"],
      "image": "../../assets/my-project/front-structure-guide.png",
      "metadata": "../../assets/my-project/front-structure-guide.json",
      "designed_layers": ["front-panel-modules"],
      "projection": {
        "center": [0, -3.6, 1.5],
        "direction": [0, 1, 0],
        "up": [0, 0, 1],
        "size": [3.2, 3.261662],
        "depth": 1.5,
        "facing_threshold": 0.08,
        "world_z_min": 0.65,
        "world_z_max": 2.55
      }
    }
  ]
}
```

Render the guide before generating the surface artwork. The guide PNG and metadata JSON are permanent design inputs, not disposable previews. A guided layer must set `source.guide_id` to the matching guide ID and reuse the exact guide projector frame. Compose the final alpha image on the guide canvas; retain transparent regions around selected surface patches instead of cropping and stretching the design across the projector.

`scripts/render_surface_structure_guide.py` extracts silhouette and hard feature edges while suppressing coplanar triangulation lines. Its metadata separates front-facing geometry into surface patches at the same feature-angle threshold. `scripts/compose_guided_livery_asset.py` can fit an alpha graphic to selected patch indices, preserve its crop aspect, and pad it back onto the full guide canvas.

## Four-edge roof continuity

Enable `edge_continuity_contract` when a body-top redesign must meet existing macro blocks on all four sides. At least one enabled body-targeted top layer must declare:

```json
{
  "source": {
    "guide_id": "top-body-v6",
    "edge_connections": ["left", "right", "front", "rear"],
    "turn_transition": "overlapping chamfered corner returns"
  }
}
```

The combined enabled body-top continuity layers must cover all four edge names. Every layer that declares edge connections also requires a non-empty `turn_transition`. The project must render `left_front_top`, `right_front_top`, `left_rear_top`, and `right_rear_top` in addition to `top_check`.

Use a full-body-roof structure guide, not a narrow central guide. Keep legacy generic top graphics on the turret target only when the body receives a new full-roof system. Prefer a broad main-color layer plus a separate highlight/accent layer so chamfer seams can use a different surface response. Preserve base-color negative space around the turret ring and do not solve continuity by flooding the entire roof.

## Isolated turret radar equipment

Enable `radar_isolation_contract` when a coarse turret mesh contains a radar that must be designed separately from the turret skirt and roof hardware. Declare a model-specific project block:

```json
{
  "radar_isolation": {
    "target_group": "turret",
    "minimum_world_z": 2.3,
    "required_sides": ["front", "rear", "top"],
    "required_equipment_zones": [
      "roof_antenna_front",
      "roof_antenna_rear",
      "roof_antenna_top",
      "turret_forward_radar"
    ],
    "equipment_zones": {
      "roof_antenna_front": {
        "minimum_world_z": 3.05,
        "required_depth_range": [-0.79, 0.13]
      },
      "roof_antenna_rear": {"minimum_world_z": 3.2},
      "roof_antenna_top": {"minimum_world_z": 4.7},
      "turret_forward_radar": {
        "minimum_world_z": 2.3,
        "required_depth_range": [-0.08, -0.02]
      }
    },
    "verification_views": [
      "radar_front_check",
      "radar_rear_check",
      "radar_top_check",
      "turret_forward_radar_check"
    ]
  }
}
```

Every enabled radar layer must target only the declared group, set `source.equipment_role: "radar"`, identify its structure guide with `source.guide_id`, and use `projection.world_z_min` at or above the applicable global or per-zone minimum. When `required_equipment_zones` is present, each layer also declares `source.equipment_zone`; the declared `equipment_zones` keys must match the required list exactly, and every required zone must have at least one enabled layer.

`required_depth_range` is optional and expressed in projector-local depth coordinates relative to `projection.center`. Use it for tilted screens, stepped pedestals, or other surfaces whose near/far extents are easy to clip. The validator requires `projection.depth / 2` to reach both ends of the range. Obtain the range from the structure-guide metadata or a face audit; do not infer it from the direct image alone.

Use independent guide/projector frames for the antenna front, rear service-door face, ribbed top, and any separate turret-forward square radar. Do not rotate one bitmap between them or treat two different front-facing devices as one zone. For richer material response, split each surface into a satin main-color layer and sparse metallic/detail layer on the same frame. Front/rear non-text radar layers still declare `source.bilateral_symmetric: true` when `front_rear_bilateral_graphics` is enabled.

Simple character-related equipment glyphs should be original abstractions rather than downloaded franchise marks. For example, a visible frog clip and snake ornament may become an angular frog scan glyph and serpent circuit loop. Keep them no-text/no-logo, below hero art, within the normal decal budget, and record local/reference research plus generated provenance.

The dedicated verification views are required even when the normal project already contains `front`, `rear`, and `top_check`: they document that the equipment-specific pass was inspected for radar readability, vent/seam clearance, high-Z isolation, and character-art spill.

## Macro coverage, per-color assets, and decal budget

Enable `macro_geometry_asset_contract` on projects with broad paintable planes. Read [macro-composition-and-decals.md](macro-composition-and-decals.md) before creating the assets.

```json
{
  "macro_composition": {
    "geometry_plan_id": "mint-body-side-v8",
    "large_planes": [
      {
        "id": "left-body-main-plane",
        "guide_id": "left-body-guide-v8",
        "geometry_plan_asset": "../../assets/anime-liveries/example/left-body-plan.png",
        "coverage_basis": "visible paintable guide patches excluding documented negative space",
        "coverage_layers": [
          "left-body-graphite",
          "left-body-mint",
          "left-body-warm-white"
        ],
        "target_coverage_min": 0.62,
        "target_coverage_max": 0.88,
        "intentional_negative_space": [
          "hero face safe zone",
          "panel seams and attached hardware"
        ],
        "verification_views": ["left_side", "left_front"]
      }
    ],
    "color_blocks": [
      {
        "id": "left-body-graphite-block",
        "color": "#20353C",
        "asset": "../../assets/anime-liveries/example/left-body-graphite.png",
        "layer_ids": ["left-body-graphite"]
      },
      {
        "id": "left-body-mint-block",
        "color": "#7FA79C",
        "asset": "../../assets/anime-liveries/example/left-body-mint.png",
        "layer_ids": ["left-body-mint"]
      },
      {
        "id": "left-body-warm-white-block",
        "color": "#D4D6D1",
        "asset": "../../assets/anime-liveries/example/left-body-warm-white.png",
        "layer_ids": ["left-body-warm-white"]
      }
    ],
    "decals": {
      "layer_ids": ["left-body-service-icon"],
      "max_total": 12,
      "max_per_surface": 4,
      "style_families": ["angular-industrial-outline"],
      "provenance_required": true
    }
  }
}
```

`geometry_plan_id` identifies the approved multicolor composition. Each large plane requires a structure-guide ID, a retained geometry-plan image, a non-empty `coverage_basis`, a 55-95% coverage target with `min < max`, named intentional negative space, and render views for visual confirmation. The coverage basis is the visible paintable guide patches after exclusions, not the full projector canvas. A practical starting range is 62-88%.

Every ID in `coverage_layers` must map exactly once to `color_blocks`. Each block requires its own unique single-color asset. Its consuming layer must use the same `image` path, `semantic_role: "underlay"`, and:

```json
{
  "source": {
    "geometry_plan_id": "mint-body-side-v8",
    "color_block_id": "left-body-graphite-block",
    "single_color_asset": true
  }
}
```

`decals` is optional when the project has no icon layers. When present, its `layer_ids` must exactly match all enabled `semantic_role: "decal"` layers. The validator allows at most twelve total layers, four per named surface, and three declared style families. Side decals remain subject to the normal mirrored-pair rule.

Each decal layer declares `source.decal_family`, `source.decal_surface_id`, and provenance. Online provenance requires `kind: "online"`, `url`, `license`, and `retrieved_at`; generated provenance requires a prompt; local or user-provided provenance requires `local_reference`.

## Asset rules

- Prefer transparent PNG or lossless TIFF for character art, logos, labels, and masks.
- Never fit character art by one-axis stretching. Use aspect-preserving projector size plus `image_region` cropping, transparent padding, or world-height clipping.
- Keep non-character assets within 8% aspect distortion unless the user explicitly accepts a different limit.
- Pair body/turret non-text side graphics across left and right. Keep glyphs readable from each exterior view instead of mirroring text blindly.
- Store provided or generated images under `assets/anime-liveries/<project>/`.
- Record generation prompts in the optional `source` object so variants are reproducible.
- Use an alpha-safe margin around artwork to avoid clipping at the projection boundary.
- Add base color first, mirrored macro patterns next, mirrored micro material blocks after that, both side hero artworks above all supporting texture, then glyph-only transparent character-name text. Keep color-bearing weathering and protective effects below hero art when hero protection is enabled.
- Place character-name typography away from the face, preserve its own aspect ratio, and validate size/readability from both side and three-quarter views. Style-specific font guidance belongs in the active style card.
- Use separate left/right text assets when the same readable canvas placement would put one side near the face. A declared safe zone must be verified against actual geometry occlusion in rendered views.
- Use distinct top/front/rear assets and projectors. Keep a body-roof layer on the body target group, use bilateral non-text front/rear masks, and verify narrow-depth localization in direct orthogonal renders.
- Before designing any new surface, generate and retain its projector-aligned structure guide. Prefer patch-contained graphics and keep physical seams and attached hardware clear.
- On large planes, document a coverage budget and all intentional negative space. Approve one overall geometry plan before deriving a unique transparent single-color asset for every production color block.
- Keep icon decals sparse and coherent: use no more than three normalized style families, assign every icon to a named surface/function, place it below hero art, and record source/license provenance for online assets.
- For a body roof that must meet four surrounding faces, declare all four edge connections, use overlapping chamfered returns, and validate the direct top plus four high corner views.
- For a turret-mounted radar, keep turret-skirt art out of the antenna and support hardware; guide the front, rear, and ribbed top independently and validate high-Z isolation with dedicated radar views.
- If the project uses a style card, set `style_id` and preserve all resolved base/layer values in the project; runtime rendering never depends on an implicit style lookup.

## Safety and export

Automatic reload accepts image, transform, opacity, blend, order, and layer-to-confirmed-group edits. If `target_groups` object patterns change, retain the last manually confirmed groups until **加载/重建** is clicked.

The projector graph is a Blender-native working master. Bake the final color and supporting channels to verified, non-overlapping UVs before claiming engine-ready delivery.
