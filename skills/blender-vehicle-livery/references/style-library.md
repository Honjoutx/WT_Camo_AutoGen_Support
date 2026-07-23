# Vehicle livery style library

Use a style card to translate visual references into reusable design decisions. A style card is not a finished decal and must not be treated as permission to copy logos, signatures, text, or character assets from a reference.

## Select a style

The machine-readable cards live in `assets/styles/*.json`.

```powershell
python scripts/style_catalog.py list
python scripts/style_catalog.py show sage-ribbon-anime-v1
python scripts/style_catalog.py validate
```

Set the selected card ID in the project as `style_id`. Copy its `base` values into the project base, then translate each ordered role into one or more explicit image layers. The runtime does not silently override project values from a style card: project JSON remains the reproducible source of truth.

## Decompose a supplied reference

When the user supplies one or more strong style references, inspect them and record the following abstract design grammar:

1. Palette roles: base, shadow, secondary, accent, and highlight. Sample relationships, not just isolated colors.
2. Spatial hierarchy: what is readable from far away, what appears at medium range, and what is reserved for close detail.
3. Motif grammar: curves, shards, panels, stripes, halftone, botanical elements, typography, emblems, and their repetition rules.
4. Focal art: subject scale, crop, placement, edge treatment, negative space, and interaction with the underlying pattern.
5. Material language: matte paint, satin graphics, metallic micro-blocks, gloss clear coat, weathering, and which masks receive each finish.
6. Projection constraints: target side, safe height, facing threshold, depth, and areas that must stay clear.
7. Asset geometry: source/crop aspect ratio, acceptable distortion, and whether the design uses cropping, tiling, or transparent padding.
8. Typography: font geometry, weight, scale hierarchy, side-readable orientation, safe placement, and interaction with the hero face.
9. Avoid list: features that would destroy the style or improperly copy source-specific identity.
10. Large-plane coverage: intended graphic-coverage range, protected negative-space zones, and direct/three-quarter verification views.
11. Color-block construction: the complete geometry plan, per-color asset split, shared-edge rules, and which blocks need independent material response.
12. Decal system: permitted icon families, functional zones, stroke/corner language, total and per-surface density budget, and source/license provenance.
13. Provenance: local reference paths or source identifiers and a note describing what was abstracted.

Create a new versioned card in `assets/styles/`, run `style_catalog.py validate`, then instantiate a project. Keep design principles and generated asset prompts in the card; keep model-specific coordinates and image paths in the project.

## Map style roles to layers

Layer order remains bottom-to-top. Split a visual texture into several small layers when different regions need distinct surface response.

| Style role | Typical layer strategy | Typical material response |
| --- | --- | --- |
| Base | Project `base` | Matte or satin body paint |
| Macro pattern | One approved geometry plan split into separate single-color projection assets | Independent satin, metallic, and coat response per block |
| Micro accents | Several sparse projection masks | Mixed metallic/gloss values by block |
| Icon decals | A bounded set of normalized, provenance-recorded masks below hero art | Usually printed/satin; occasional metallic functional mark |
| Hero art | Dedicated character projection | Non-metallic print with controlled clear coat |
| Protective/weather layer | Optional final masks | Rough dust or glossy protective patches |

For independent surface control, give every block its own layer and `surface` object. Multiple blocks may share one bitmap only when their material response is intentionally identical.

Style cards must not solve composition by distorting source assets. Mark hero art as proportion-preserving, keep ordinary masks within the project's distortion budget, and describe text placement/font character explicitly enough that a new project can reproduce it.

For broad flat surfaces, do not leave coverage to improvisation. Record the large-plane target range and intentional negative space, freeze the overall multicolor geometry on the structure guide, then derive a separate transparent asset for each color block. Add icon decals only after the macro composition succeeds; keep one to three related families, a strict per-surface/total count budget, and current source/license records for online material.

Treat explicit user finish intent as higher priority than a style-card default. Use these starting ranges, then judge them under the actual preview lighting:

- Matte printed character: `roughness` 0.55–0.75, `metallic` 0, `coat_weight` 0–0.15.
- Satin graphic: `roughness` 0.32–0.55, `metallic` 0–0.2, `coat_weight` 0.1–0.35.
- Metallic accent island: `roughness` 0.12–0.32, `metallic` 0.55–0.9, `coat_weight` 0.25–0.6.
- Gloss protective patch: `roughness` 0.18–0.38, `metallic` 0, `coat_weight` 0.45–0.8, with low `coat_roughness`.

## Seed catalog

- `sage-ribbon-anime-v1`: low-saturation sage base, navy ribbon flow, coral micro accents, asymmetric hero art, and metallic detail islands. Derived from the verified Pantsyr side-livery project.
- `mint-industrial-panel-anime-v1`: mint/graphite/warm-white hard-edged armor panels, diagonal speed stripes, topographic micro-lines, generic industrial signage, oversized condensed typography, and separate side/top hero-art compositions. Abstracted from the user-provided `style1` references without copying their names, characters, logos, serials, or signatures.
- `mint-industrial-panel-anime-v2-symmetric`: corrected mint industrial variant with mirrored non-text body/turret side layers, forward-facing hero art on both sides, and a protected hero stack that permits only glyph-only transparent character names above the artwork.
- `mint-industrial-panel-anime-v3-aspect-safe`: v2 composition with aspect-preserved hero art, low-distortion support graphics, rear-upper safe-zone typography, and condensed angular industrial letterforms.
- `mint-industrial-panel-anime-v4-multisurface`: v3 side composition extended with a body-only longitudinal roof spine, a forward-converging symmetric nose, a distinct broad rear termination graphic, correct world-direction projectors, and direct top/front/rear approval views.
- `mint-industrial-panel-anime-v5-structure-fit`: v4 composition with a mandatory projector-aligned hard-surface guide, feature-edge surface-patch segmentation, aspect-preserved guide-canvas composition, and a front treatment contained inside the real paired access panels while leaving seams and hardware clear.
- `mint-industrial-panel-anime-v6-roof-wrap`: v5 composition with a body-only full-roof structure guide, a graphite/mint perimeter flow connecting rear terminal, side shoulder rails, and paired front returns through chamfered overlaps, separate metallic highlight accents, and direct top plus four high-corner continuity checks.
- `mint-industrial-panel-anime-v7-turret-radar`: v6 body composition extended with structure-guided paired turret skirts, separate satin/metallic turret blocks, aspect-preserved forward-facing turret character art, isolated air-defense radar front, rear-service, and ribbed-top projector stacks with high-Z validation, plus a forward policy for coverage-budgeted geometry plans, per-color production assets, and bounded provenance-recorded icon decals.

The V7 turret/radar grammar also treats a roof antenna's tilted main screen and lower forward subpanel as a depth-complete front system, while any separate turret-forward square radar remains its own equipment zone. Character-related sensor decals may abstract verified motifs from the provided art into original deterministic glyphs, but must not copy a franchise logo, existing icon bitmap, signature, or text.
