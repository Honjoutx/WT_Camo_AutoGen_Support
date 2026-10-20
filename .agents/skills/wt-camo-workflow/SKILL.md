---
name: wt-camo-workflow
description: Design and edit vehicle liveries in the local WT Camo workbench. Use for OBJ/MTL intake and UV phase repair, coarse assembly grouping, sketch-first physical-surface design, vector layers, character placement, PBR finishes, same-family model migration, original-atlas PNG export, or separated poster rendering assets. Preserves original UVs and editable project state.
---

# Vehicle livery workbench

Use the repository's background tools and the user's current project. Do not import old project themes, characters, palettes, or conversation history unless asked.

## Start and identify the project

1. Read the workspace `projects/registry.json`, then only the selected project's config, brief, contract and layout. The workspace defaults to `data/workspace` and may be overridden by `WT_CAMO_WORKSPACE` or `config/runtime.local.json`. Resolve executable paths from `tools/livery-layout-editor/runtime.py`.
2. Read `tools/livery-layout-editor/docs/workflow-guide.zh-CN.txt` once per session or when it changes. Use [project-contract.md](references/project-contract.md) when creating or registering a project. Use [execution.md](references/execution.md) for design and handoff decisions.
3. Report actual capabilities. A local Codex CLI does not inherit ImageGen, Blender MCP or Photoshop MCP from a separate chat application. Use configured CLI MCP servers when present; otherwise continue file, vector, layout and background Blender work. Do not fabricate generated assets.
4. For this repository's managed Blender connection, read `docs/blender-mcp.zh-CN.md` in the tool repository (`runtime.APP`) when needed. `start.cmd -WithBlenderMcp` installs the pinned addon/server and starts a separate headless session; `scripts/doctor-workbench.py --blender-mcp` checks both the host and Codex tool discovery. Use `wt_camo_blender` tools for that session, not another open Blender. Render previews to files: headless mode has no viewport screenshot. No model is loaded unless supplied; save intended scene changes before explicitly stopping or replacing the session.

## Ordered workflow

1. **Intake:** inspect OBJ/MTL, texture paths, UV ranges, overlap and normals. Use `model_intake.execute` or the UI intake endpoint. Keep original source and UV evidence. Integer UV translation is per proven material/object domain; never modulo individual vertices, repack UVs or silently alter geometry. Review automatic assembly guesses. Merge body, turret main structure, barrel, equipment and detachable armor into coarse assemblies; tracks may be excluded from painting, retained for rendering.
2. **Brief:** record theme, palette, typography, character references, surface placement/orientation, cropping, material goals, resolution and delivery filenames. Preserve source images. Removing a background must not change the character itself.
3. **Sketch:** save a viewable independent sketch before detail design. Establish large color areas, flow, contrast, density, focal point and character safe zones. Separate body and turret compositions, check their assembled continuity. Do not substitute a high-detail texture for a macro composition.
4. **Physical surfaces:** group actual principal contiguous faces, not every face visible from a direction. Combine coplanar plates; handle slopes by geometry. Isolate protrusions, mirrors and hatches when they would cut through an illustration. Keep a face-ID ledger, art UVs, physical footprints and original-atlas coverage. Preview guides are structural evidence, never paint.
5. **Design:** author each large plane individually. Prefer editable SVG for typography, grids, dots, line work and color edges. Use raster artwork only where requested. Maintain silhouette proportions and reference consistency. Keep exact text. Connect gradients in common physical coordinates across assemblies; background design should remain complete without characters. Density needs hierarchy, not equal visual weight everywhere.
6. **Materials:** assign per-layer metallic, roughness and optional relief/shadow. Distinguish metal, rubber, cloth, glass and paint. Smooth fine normal noise while preserving seams, bolts and structural edges. Validate reflected light in an actual render. Do not assume a game-packed normal/specular texture is ordinary PBR.
7. **Migration:** transfer physical layout by anchors; register each model's own UV. Crop missing front length instead of squeezing the full layout. Inventory different equipment. Shared texels cannot show independent designs: declare a deterministic authority and record compromises.
8. **Mapping fixes:** trace the reported physical part to source object and face IDs, owner/paint flags, material domain, art UV, masks, merge priority, final atlas and game file binding. Fix the affected domain. Do not move an entire image to compensate for a local registration error.
9. **Export:** keep original UVs. Offer 2K or higher as specified; the current model export UI provides 4K/8K. Export only changed original atlases and selected channels, flat in one directory, using `_Basecolor`, `_Metallic`, `_Roughness`, `_Smoothness`, `_Normal`, `_Height`. Preserve source naming stems after removing `_c`/`_n` suffix tails. Record file aliases/collisions. Game packing and `.blk` are separate tasks.
10. **Poster:** retain accepted model and camera edits, restore unpainted source tracks when needed. Clarify transparent sky versus floor, props and contact shadows from the current brief. Render cleanly and denoise. Deliver model render, character art, shadows, background, text and border separately if requested. Never regenerate/distort the finished vehicle render to compose a poster.

## State and validation

- Default to compact storage: immutable content-addressed assets, parameter-only checkpoints, lazy ZIP downloads. Do not copy models and all textures into every revision. Use portable mode for independent handoff. Never delete the shared store while projects reference it.
- Before editing layout, retain the user's existing `state/current.json`. Use atomic writes. Preserve layer IDs and manual transforms; update contract signatures and source layer inventories coherently. The UI detects revisions and will pause overwriting unsaved local edits on conflict.
- Keep inputs, hashes, prompts, operations, layout, material parameters and export evidence under the active project. Publish code and generic instructions only, not personal artwork, chats or auth files.
- Run focused validation for changed bindings and export logic. Never report an unbound board as a valid original-UV texture. A completed intake does not automatically provide semantic planar registration.
- Finish authorized work without repetitive confirmations. Ask only for genuinely missing dependencies or material design choices. Respect explicit requests to skip redundant visual verification.
