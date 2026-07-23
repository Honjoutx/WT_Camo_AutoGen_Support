# Livery preset schema

Use a UTF-8 JSON object with these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Output-safe preset identifier. |
| `material_name` | string | Blender material datablock name. |
| `target_objects` | string array | Case-sensitive glob patterns for paintable meshes. |
| `colors` | string array | Two or more `#RRGGBB` camouflage colors. |
| `thresholds` | number array | Color-ramp positions in ascending order, one per color. |
| `pattern_scale` | number | World-space noise scale; larger values create smaller patches. |
| `noise_detail` | number | Main camouflage noise detail. |
| `noise_roughness` | number | Main noise roughness in `[0, 1]`. |
| `noise_distortion` | number | Main noise distortion. |
| `roughness` | number | Principled BSDF roughness. |
| `metallic` | number | Principled BSDF metallic value. |
| `micro_bump_strength` | number | Fine paint-surface bump strength. |
| `micro_bump_scale` | number | Fine noise scale. |
| `render.resolution` | integer | Square preview resolution in pixels. |
| `render.views` | object array | View names with azimuth and elevation degrees. |

Keep `thresholds` aligned with `colors`. Use explicit target patterns and never use `*` without user approval.

The Blender live panel currently normalizes presets to three exposed colors. It preserves three-entry `thresholds`, `render`, and unknown JSON fields when saving; other threshold counts reset to the three-color defaults. External JSON saves are detected by file modification time at the configured interval. Visual material fields update automatically on the last successfully applied material. If an external save or a newly selected preset also changes `material_name` or `target_objects`, those scope fields remain at the values from the last successful **加载并应用** or **应用面板参数** action; the visual subset still hot-reloads. Merely editing the panel's scope text does not confirm it or redirect live preview.
