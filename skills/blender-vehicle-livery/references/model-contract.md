# Vehicle model contract

## Input

- Accept `.blend`, `.obj`, `.fbx`, `.gltf`, and `.glb` files.
- Treat the source file and adjacent textures as immutable.
- Resolve OBJ `mtllib` references relative to the OBJ directory and report missing files.

## Paint-target requirements

- Prefer separate mesh objects or material slots for body panels, turret panels, glass, tires, lamps, weapons, and interior parts.
- Match paintable objects with explicit `target_objects` patterns from the preset.
- Stop when no pattern matches.
- Warn when a target object contains visually distinct surfaces under one material; procedural paint will affect all of them.

## UV and export

- Do not require UVs for the Blender procedural material because it uses shared object coordinates.
- Do not require UVs for directional anime image layers; projector volumes localize images by position, direction, depth, and surface facing.
- Require non-overlapping UVs before baking engine-ready textures.
- Treat `.blend` as the authoritative procedural result and `.glb` as a convenience export until baked textures are validated.

## Known Pantsyr sample

`SMSV/pantsyr_sm_sv_fix.obj` imports as two meshes:

- `pantsyr_sm_sv_body_c`: 77,125 vertices and 130,178 polygons.
- `pantsyr_sm_sv_turret_c`: 51,660 vertices and 82,044 polygons.

Both meshes contain `UVMap`, but the referenced `pantsyr_sm_sv_fix.mtl` is absent and only one material slot exists per mesh. Preserve this warning in reports.

Treat the body and turret as coarse target groups. Localize character art, emblems, stripes, and labels with separate directional projectors instead of requiring additional material slots. Small attached geometry inside either mesh remains part of that coarse group; use narrow projection depth, facing thresholds, and transparent image masks to keep artwork off unrelated surfaces.
