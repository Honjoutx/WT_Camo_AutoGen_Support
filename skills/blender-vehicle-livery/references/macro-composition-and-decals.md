# Macro composition, per-color assets, and decals

Use this contract for broad body, roof, turret, radar, front, or rear planes. It makes empty space intentional, preserves a coherent large-scale composition, and prevents small decals from becoming visual clutter.

## Cover large planes deliberately

1. Render the projector-aligned structure guide before drawing.
2. Mark the paintable large plane, hardware exclusions, hero-art safe zone, seams, vents, hatches, and cross-surface connection edges.
3. Set `coverage_basis` to the visible paintable structure-guide patches after excluding the named hero, seam, hatch, vent, and hardware clearances. Never use the full projector canvas as the denominator because it may contain empty background or unrelated geometry.
4. Set a target graphic-coverage range. Start at 62-88% for broad armor planes; the validator permits 55-95% so unusual structures remain possible.
5. Name every retained blank region in `intentional_negative_space`. Blank base paint is valid around a face, turret ring, service hatch, hardware, or structural seam; unexplained empty corners are not.
6. Verify the target in one direct surface view and at least one three-quarter view. The numeric target is a design budget, not a measured result; rendered review remains mandatory.

Do not solve coverage by flooding every polygon. Increase the scale or extend the route of the macro geometry while preserving hardware, focal art, and service-access clearances.

## Design geometry before generating color assets

Build one complete, multicolor geometry plan on the structure-guide canvas first. The plan defines all polygon boundaries, shared edges, color assignments, symmetry, corner returns, and negative space. Freeze this plan before generating production masks.

After approval, derive one transparent, single-color asset for each color block:

- Keep every derived asset on the original guide canvas; do not crop each color to a different frame.
- Derive shared boundaries from the same geometry plan so adjacent colors do not leave gaps or create accidental overlaps.
- Give every block a unique `color_block_id`, asset path, and one or more consuming layers. A single asset may be reused by a deliberate mirrored layer pair.
- Set `source.geometry_plan_id`, `source.color_block_id`, and `source.single_color_asset: true` on every consuming layer.
- Use a separate layer and `surface` block for each color block so roughness, metallic, coat, and opacity can be tuned independently.
- Keep these layers at `semantic_role: "underlay"` and below hero art.

Do not use a finished multicolor background image as the only production layer. It prevents independent material response and makes later edge corrections destructive.

## Add decals as a bounded tertiary system

Add icons only after the macro geometry reads correctly without them. Decals support function and rhythm; they do not repair an unresolved composition.

- Use one to three related style families. Normalize stroke weight, corner language, palette, outline/fill treatment, and orientation before placing them.
- Default to no more than four decals on one large surface and twelve enabled decal layers in the full project. Mirrored left/right placements count as two layers.
- Assign each decal to a named functional zone such as sensor, service, access, warning, cooling, or unit mark. Avoid random scatter, arbitrary rotation, repeated scale jumps, and overlapping icon clusters.
- Keep decals below hero art and outside face, name, seam, hardware, vent, and inspection-door safe zones.
- Pair non-text side decals. Do not mirror readable lettering or direction-sensitive symbols blindly.
- Prefer transparent SVG or PNG obtained from the icon creator's official repository or license page. When online search is requested, verify the current source and license on the web rather than relying on memory.
- Record `url`, `license`, and `retrieved_at` for online assets. Record a prompt for generated icons, or `local_reference` for user-provided/local assets.
- Do not copy a brand logo, military insignia, signature, or restricted mark unless the user confirms authorization.

Use `semantic_role: "decal"` and declare the bounded system in `macro_composition.decals`. The validator rejects undeclared decal layers, more than three style families, excessive per-surface density, and missing provenance.

## Project contract example

```json
{
  "design_rules": {
    "macro_geometry_asset_contract": true
  },
  "macro_composition": {
    "geometry_plan_id": "mint-turret-side-v8",
    "large_planes": [
      {
        "id": "left-turret-skirt",
        "guide_id": "left-turret-skirt-guide-v8",
        "geometry_plan_asset": "../../assets/anime-liveries/example/left-turret-plan.png",
        "coverage_basis": "visible paintable skirt patches excluding the hero and hardware safe zones",
        "coverage_layers": [
          "left-turret-graphite",
          "left-turret-mint",
          "left-turret-warm-white"
        ],
        "target_coverage_min": 0.62,
        "target_coverage_max": 0.88,
        "intentional_negative_space": [
          "hero face safe zone",
          "panel seams",
          "weapon and radar support hardware"
        ],
        "verification_views": ["left_side", "left_front"]
      }
    ],
    "color_blocks": [
      {
        "id": "left-turret-graphite-block",
        "color": "#20353C",
        "asset": "../../assets/anime-liveries/example/left-turret-graphite.png",
        "layer_ids": ["left-turret-graphite"]
      },
      {
        "id": "left-turret-mint-block",
        "color": "#7FA79C",
        "asset": "../../assets/anime-liveries/example/left-turret-mint.png",
        "layer_ids": ["left-turret-mint"]
      },
      {
        "id": "left-turret-warm-white-block",
        "color": "#D4D6D1",
        "asset": "../../assets/anime-liveries/example/left-turret-warm-white.png",
        "layer_ids": ["left-turret-warm-white"]
      }
    ],
    "decals": {
      "layer_ids": ["left-turret-sensor-icon"],
      "max_total": 12,
      "max_per_surface": 4,
      "style_families": ["angular-industrial-outline"],
      "provenance_required": true
    }
  }
}
```

A color-block layer adds:

```json
{
  "id": "left-turret-graphite",
  "semantic_role": "underlay",
  "image": "../../assets/anime-liveries/example/left-turret-graphite.png",
  "source": {
    "guide_id": "left-turret-skirt-guide-v8",
    "geometry_plan_id": "mint-turret-side-v8",
    "color_block_id": "left-turret-graphite-block",
    "single_color_asset": true
  }
}
```

An online decal layer adds:

```json
{
  "id": "left-turret-sensor-icon",
  "semantic_role": "decal",
  "source": {
    "decal_family": "angular-industrial-outline",
    "decal_surface_id": "left-turret-skirt",
    "provenance": {
      "kind": "online",
      "url": "https://official-source.example/icon",
      "license": "verified license identifier",
      "retrieved_at": "YYYY-MM-DD"
    }
  }
}
```
