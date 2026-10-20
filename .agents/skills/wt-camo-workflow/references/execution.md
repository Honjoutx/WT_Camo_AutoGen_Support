# Design execution and traceability

Use a short project-local `brief` containing accepted requirements and latest changes. Preserve original assets and prompts. Maintain records for source hashes, assembly names, face/domain ownership, UV correction per material, shared-UV authority and output naming. Do not store repeated complete models or embedded copies of all maps in chat/checkpoint JSON.

Work in this order: evidence → macro sketch → real surface registration → independent plane compositions → layered details → material tuning → focused assembled preview → selected original atlas exports → separate poster assets. A stage is done only when its output exists. If a dependency is unavailable, clearly record it and continue independent work.

Typography and technical decoration should be deterministic SVG. Keep minimum meaningful line widths relative to export texel density. Use large color transitions and few dominant directions before dense secondary grids or ticks. Keep filled areas, fine line textures and bright highlights at distinct value levels. Imported raster characters retain aspect ratio, attire and accessories. Shadows follow the same physical clip, transparency and layer order.

Text, logos and decorative highlights can share a controlled finish when requested. Smooth normals with a structure-preserving filter, renormalize vectors and preserve channel convention. Tangent-space normals are not ordinary RGB images: avoid naive color blur that changes vector length. Use `normal_finish.py` with a verified source convention.

For an error, capture one reproducible part/face example and follow it through binding → surface coordinates → mask → material atlas → downloaded file. Confirm both left and right independently. Source UV overlap limits what can be unique; do not conceal it with one successful camera view.

The UI watches source documents, masks, assets, config and layout. Browser refresh is automatic only when safe. Unsaved manual changes require backup/rebase after a conflict; never replace the user's draft behind their back. Deleted cache outputs are not authoritative sources. Explicitly missing inputs should be repaired/rebuilt from original source or reported, not silently pulled from an unrelated project's old output.

Use PNG/SVG as editable intermediate deliverables. PBR and game-packed channels are separate contracts. For publishing, inspect current game contribution terms and asset permissions when asked; the tool does not automatically publish or guarantee acceptance.
