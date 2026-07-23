import fnmatch
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


SUPPORTED_EXTENSIONS = {".blend", ".obj", ".fbx", ".gltf", ".glb"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def import_model(path):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported model format: {extension}")
    if extension == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(path))
    elif extension == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif extension == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No mesh objects were imported from {path}")
    return meshes


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def scene_bounds(objects=None):
    objects = objects or mesh_objects()
    if not objects:
        raise RuntimeError("Scene contains no mesh objects")
    minimum = Vector((float("inf"),) * 3)
    maximum = Vector((float("-inf"),) * 3)
    for obj in objects:
        for corner in obj.bound_box:
            world_corner = obj.matrix_world @ Vector(corner)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], world_corner[axis])
                maximum[axis] = max(maximum[axis], world_corner[axis])
    return minimum, maximum


def audit_scene(objects=None):
    objects = list(objects) if objects is not None else mesh_objects()
    minimum, maximum = scene_bounds(objects)
    return {
        "mesh_count": len(objects),
        "scene_dimensions": [round(value, 5) for value in maximum - minimum],
        "scene_bounds": {
            "minimum": [round(value, 5) for value in minimum],
            "maximum": [round(value, 5) for value in maximum],
        },
        "objects": [
            {
                "name": obj.name,
                "vertices": len(obj.data.vertices),
                "polygons": len(obj.data.polygons),
                "uv_layers": [layer.name for layer in obj.data.uv_layers],
                "materials": [
                    slot.material.name if slot.material else None
                    for slot in obj.material_slots
                ],
            }
            for obj in objects
        ],
        "images": [image.name for image in bpy.data.images],
    }


def inspect_source_assets(model_path):
    model_path = Path(model_path).resolve()
    result = {"mtl_references": [], "missing_mtl": []}
    if model_path.suffix.lower() != ".obj":
        return result
    with model_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("mtllib "):
                reference = line[7:].strip().replace("./", "")
                result["mtl_references"].append(reference)
    for reference in result["mtl_references"]:
        candidate = (model_path.parent / reference).resolve()
        if not candidate.exists():
            result["missing_mtl"].append(str(candidate))
    return result


def _srgb_channel_to_linear(value):
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def hex_to_rgba(value):
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB color, got: {value}")
    channels = [int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4)]
    return tuple(_srgb_channel_to_linear(channel) for channel in channels) + (1.0,)


def _input(node, name):
    socket = node.inputs.get(name)
    if socket is None:
        raise RuntimeError(f"Node {node.bl_idname} has no input named {name}")
    return socket


def ensure_coordinate_empty():
    empty = bpy.data.objects.get("CAMO_Texture_Coordinates")
    if empty is None:
        empty = bpy.data.objects.new("CAMO_Texture_Coordinates", None)
        bpy.context.scene.collection.objects.link(empty)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.5
    empty.hide_render = True
    return empty


def _colors_and_thresholds(preset):
    colors = preset.get("colors", [])
    if len(colors) < 2:
        raise ValueError("A camouflage preset requires at least two colors")
    thresholds = preset.get("thresholds")
    if thresholds is None:
        thresholds = [index / len(colors) for index in range(len(colors))]
    if len(thresholds) != len(colors):
        raise ValueError("thresholds must contain one value per color")
    if any(float(b) < float(a) for a, b in zip(thresholds, thresholds[1:])):
        raise ValueError("thresholds must be in ascending order")
    return colors, thresholds


def _configure_color_ramp(ramp, colors, thresholds):
    ramp.interpolation = "CONSTANT"
    while len(ramp.elements) > 2:
        ramp.elements.remove(ramp.elements[1])
    ramp.elements[0].position = float(thresholds[0])
    ramp.elements[0].color = hex_to_rgba(colors[0])
    ramp.elements[1].position = float(thresholds[-1])
    ramp.elements[1].color = hex_to_rgba(colors[-1])
    for position, color in zip(thresholds[1:-1], colors[1:-1]):
        element = ramp.elements.new(float(position))
        element.color = hex_to_rgba(color)


def create_camo_material(preset):
    colors, thresholds = _colors_and_thresholds(preset)

    material_name = preset.get("material_name", f"CAMO_{preset['name']}")
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(material_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = "CAMO_Output"
    output.location = (620, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "CAMO_Principled"
    bsdf.location = (350, 0)
    texture_coordinate = nodes.new("ShaderNodeTexCoord")
    texture_coordinate.name = "CAMO_Coordinates"
    texture_coordinate.location = (-760, 20)
    texture_coordinate.object = ensure_coordinate_empty()
    noise = nodes.new("ShaderNodeTexNoise")
    noise.name = "CAMO_MainNoise"
    noise.location = (-500, 80)
    noise.noise_dimensions = "3D"
    _input(noise, "Scale").default_value = float(preset.get("pattern_scale", 0.8))
    _input(noise, "Detail").default_value = float(preset.get("noise_detail", 3.0))
    _input(noise, "Roughness").default_value = float(preset.get("noise_roughness", 0.65))
    _input(noise, "Distortion").default_value = float(preset.get("noise_distortion", 0.1))
    ramp_node = nodes.new("ShaderNodeValToRGB")
    ramp_node.name = "CAMO_ColorRamp"
    ramp_node.location = (-180, 120)
    ramp = ramp_node.color_ramp
    _configure_color_ramp(ramp, colors, thresholds)

    micro_noise = nodes.new("ShaderNodeTexNoise")
    micro_noise.name = "CAMO_MicroNoise"
    micro_noise.location = (-480, -240)
    micro_noise.noise_dimensions = "3D"
    _input(micro_noise, "Scale").default_value = float(preset.get("micro_bump_scale", 24.0))
    _input(micro_noise, "Detail").default_value = 2.0
    bump = nodes.new("ShaderNodeBump")
    bump.name = "CAMO_Bump"
    bump.location = (110, -180)
    _input(bump, "Strength").default_value = float(preset.get("micro_bump_strength", 0.08))
    _input(bump, "Distance").default_value = 0.035

    _input(bsdf, "Roughness").default_value = float(preset.get("roughness", 0.72))
    _input(bsdf, "Metallic").default_value = float(preset.get("metallic", 0.0))
    links.new(texture_coordinate.outputs["Object"], noise.inputs["Vector"])
    links.new(texture_coordinate.outputs["Object"], micro_noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp_node.inputs["Fac"])
    links.new(ramp_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(micro_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    material.diffuse_color = hex_to_rgba(colors[0])
    return material


def update_camo_material(preset, material=None):
    colors, thresholds = _colors_and_thresholds(preset)
    material_name = preset.get("material_name", f"CAMO_{preset['name']}")
    material = material or bpy.data.materials.get(material_name)
    required_nodes = {
        "CAMO_MainNoise",
        "CAMO_ColorRamp",
        "CAMO_MicroNoise",
        "CAMO_Bump",
        "CAMO_Principled",
    }
    if material is None or not material.use_nodes:
        return create_camo_material(preset)
    nodes = material.node_tree.nodes
    if any(nodes.get(name) is None for name in required_nodes):
        return create_camo_material(preset)

    noise = nodes["CAMO_MainNoise"]
    _input(noise, "Scale").default_value = float(preset.get("pattern_scale", 0.8))
    _input(noise, "Detail").default_value = float(preset.get("noise_detail", 3.0))
    _input(noise, "Roughness").default_value = float(preset.get("noise_roughness", 0.65))
    _input(noise, "Distortion").default_value = float(preset.get("noise_distortion", 0.1))
    _configure_color_ramp(nodes["CAMO_ColorRamp"].color_ramp, colors, thresholds)

    micro_noise = nodes["CAMO_MicroNoise"]
    _input(micro_noise, "Scale").default_value = float(preset.get("micro_bump_scale", 24.0))
    bump = nodes["CAMO_Bump"]
    _input(bump, "Strength").default_value = float(preset.get("micro_bump_strength", 0.08))
    bsdf = nodes["CAMO_Principled"]
    _input(bsdf, "Roughness").default_value = float(preset.get("roughness", 0.72))
    _input(bsdf, "Metallic").default_value = float(preset.get("metallic", 0.0))
    material.diffuse_color = hex_to_rgba(colors[0])
    material.update_tag()
    return material


def assign_material(material, patterns):
    if not patterns:
        raise ValueError("target_objects must contain explicit object-name patterns")
    targets = [
        obj
        for obj in mesh_objects()
        if any(fnmatch.fnmatchcase(obj.name, pattern) for pattern in patterns)
    ]
    if not targets:
        raise RuntimeError(f"No mesh objects matched target patterns: {patterns}")
    for obj in targets:
        already_assigned = len(obj.data.materials) == 1 and obj.data.materials[0] == material
        if not already_assigned:
            obj.data.materials.clear()
            obj.data.materials.append(material)
            for polygon in obj.data.polygons:
                polygon.material_index = 0
    return targets


def apply_preset_to_scene(preset):
    material = update_camo_material(preset)
    targets = assign_material(material, preset.get("target_objects", []))
    bpy.context.view_layer.update()
    return material, targets


def _create_principled_material(name, color, roughness):
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = next(
        (node for node in nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"),
        None,
    )
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        output = next(
            (node for node in nodes if node.bl_idname == "ShaderNodeOutputMaterial"),
            None,
        )
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return material


def _point_camera(camera, target):
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_preview_scene(vehicle_objects):
    for obj in list(bpy.context.scene.objects):
        if obj.type in {"CAMERA", "LIGHT"} or obj.name.startswith("CAMO_Ground"):
            bpy.data.objects.remove(obj, do_unlink=True)

    minimum, maximum = scene_bounds(vehicle_objects)
    center = (minimum + maximum) * 0.5
    span = maximum - minimum
    ground_size = max(span.x, span.y) * 3.0
    bpy.ops.mesh.primitive_plane_add(size=ground_size, location=(center.x, center.y, minimum.z - 0.025))
    ground = bpy.context.active_object
    ground.name = "CAMO_Ground"
    ground.data.materials.append(
        _create_principled_material("CAMO_Ground_Material", (0.055, 0.065, 0.075, 1.0), 0.82)
    )

    bpy.ops.object.camera_add()
    camera = bpy.context.active_object
    camera.name = "CAMO_Preview_Camera"
    camera.data.lens = 55
    bpy.context.scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(center.x + span.x, center.y - span.y, maximum.z + span.z))
    key = bpy.context.active_object
    key.name = "CAMO_Key"
    key.data.energy = 2600
    key.data.shape = "DISK"
    key.data.size = max(span.x, span.y) * 0.9
    _point_camera(key, center)

    bpy.ops.object.light_add(type="AREA", location=(center.x - span.x, center.y + span.y * 0.4, center.z + span.z * 0.5))
    fill = bpy.context.active_object
    fill.name = "CAMO_Fill"
    fill.data.energy = 1450
    fill.data.size = max(span.x, span.y) * 0.7
    _point_camera(fill, center)

    bpy.ops.object.light_add(type="SUN", location=(center.x, center.y, maximum.z + span.z))
    sun = bpy.context.active_object
    sun.name = "CAMO_Sun"
    sun.rotation_euler = (math.radians(25), math.radians(-20), math.radians(25))
    sun.data.energy = 1.2

    world = bpy.context.scene.world or bpy.data.worlds.new("CAMO_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = next(
        (
            node
            for node in world.node_tree.nodes
            if node.bl_idname == "ShaderNodeBackground"
        ),
        None,
    )
    if background is None:
        background = world.node_tree.nodes.new("ShaderNodeBackground")
        output = next(
            (
                node
                for node in world.node_tree.nodes
                if node.bl_idname == "ShaderNodeOutputWorld"
            ),
            None,
        )
        if output is None:
            output = world.node_tree.nodes.new("ShaderNodeOutputWorld")
        world.node_tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    background.inputs["Color"].default_value = (0.035, 0.045, 0.06, 1.0)
    background.inputs["Strength"].default_value = 0.65
    return camera, center, span


def render_previews(output_dir, render_config, vehicle_objects):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    camera, center, span = setup_preview_scene(vehicle_objects)
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    resolution = int(render_config.get("resolution", 768))
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False

    radius = max(span.x, span.y) * 1.65
    results = []
    views = render_config.get("views") or [
        {"name": "three_quarter", "azimuth": 35.0, "elevation": 20.0}
    ]
    for view in views:
        azimuth = math.radians(float(view.get("azimuth", 35.0)))
        elevation = math.radians(float(view.get("elevation", 20.0)))
        horizontal = radius * math.cos(elevation)
        camera.location = (
            center.x + horizontal * math.cos(azimuth),
            center.y + horizontal * math.sin(azimuth),
            center.z + radius * math.sin(elevation),
        )
        _point_camera(camera, center)
        filepath = output_dir / f"{view['name']}.png"
        scene.render.filepath = str(filepath)
        bpy.ops.render.render(write_still=True)
        results.append(str(filepath))
    return results


def export_glb(path, objects):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)
    return str(path)


def run_pipeline(model_path, preset_path, output_dir):
    model_path = Path(model_path).resolve()
    preset_path = Path(preset_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_assets = inspect_source_assets(model_path)
    clear_scene()
    import_model(model_path)
    before = audit_scene()
    preset = load_json(preset_path)
    material, targets = apply_preset_to_scene(preset)
    previews = render_previews(output_dir / "previews", preset.get("render", {}), targets)
    blend_path = output_dir / f"{preset['name']}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    glb_path = export_glb(output_dir / f"{preset['name']}.glb", targets)
    warnings = []
    if source_assets["missing_mtl"]:
        warnings.append("The OBJ references missing MTL files; original materials cannot be restored.")
    if any(len(obj.data.materials) <= 1 for obj in targets):
        warnings.append(
            "At least one paint target has a single material slot; tires, glass, lamps, or other surfaces may receive body paint."
        )
    warnings.append(
        "The GLB export is a convenience geometry export; validate or bake the Blender procedural material before engine delivery."
    )
    report = {
        "source_model": str(model_path),
        "source_assets": source_assets,
        "preset": str(preset_path),
        "material": material.name,
        "targets": [obj.name for obj in targets],
        "before": before,
        "after": audit_scene(targets),
        "warnings": warnings,
        "outputs": {
            "blend": str(blend_path),
            "glb": glb_path,
            "previews": previews,
        },
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
