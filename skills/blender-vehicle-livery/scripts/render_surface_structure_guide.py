"""Render a projector-aligned hard-surface structure guide from Blender geometry.

Run inside Blender, opening the source .blend before this script. The output PNG
uses the same center, direction, up vector, size, and depth as an image projector,
so artwork composed over the guide can be used without guessing its placement.
"""

import argparse
import json
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def _vec3(value):
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three comma-separated numbers")
    return Vector(parts)


def _vec2(value):
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected two comma-separated numbers")
    return parts


def _argv():
    import sys

    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def _material(name, color):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*color, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _curve_object(name, segments, radius, material):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 0
    curve.resolution_u = 1
    for start, end in segments:
        spline = curve.splines.new("POLY")
        spline.points.add(1)
        spline.points[0].co = (*start, 1.0)
        spline.points[1].co = (*end, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def _frame_segments(center, right, up, direction, size, depth, world_z_clip):
    # Put the frame just in front of the projection volume so geometry cannot hide it.
    frame_center = center - direction * (depth * 0.5 + 0.025)
    half_w, half_h = size[0] * 0.5, size[1] * 0.5
    corners = [
        frame_center - right * half_w - up * half_h,
        frame_center + right * half_w - up * half_h,
        frame_center + right * half_w + up * half_h,
        frame_center - right * half_w + up * half_h,
    ]
    segments = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    if world_z_clip and abs(up.z) > 0.9:
        for z in world_z_clip:
            v = (z - center.z) / up.z
            if -half_h <= v <= half_h:
                line_center = frame_center + up * v
                segments.append((line_center - right * half_w, line_center + right * half_w))
    return segments


def render_guide(args):
    obj = bpy.data.objects.get(args.object)
    if obj is None or obj.type != "MESH":
        raise ValueError(f"mesh object not found: {args.object}")

    center = args.center
    direction = args.direction.normalized()
    up = (args.up - direction * args.up.dot(direction)).normalized()
    if up.length < 0.99:
        raise ValueError("up vector must not be parallel to direction")
    right = direction.cross(up).normalized()
    size = args.size
    half_w, half_h, half_d = size[0] * 0.5, size[1] * 0.5, args.depth * 0.5

    # Work on a copy so the opened livery scene is never saved or mutated on disk.
    guide_obj = obj.copy()
    guide_obj.data = obj.data.copy()
    guide_obj.name = "LIVERY_STRUCTURE_GUIDE_BODY"
    bpy.context.scene.collection.objects.link(guide_obj)
    obj.hide_render = True
    for candidate in bpy.context.scene.objects:
        if candidate not in {guide_obj} and candidate.type not in {"CAMERA"}:
            candidate.hide_render = True

    fill_material = _material("LIVERY_GUIDE_FILL", (0.94, 0.95, 0.95))
    guide_obj.data.materials.clear()
    guide_obj.data.materials.append(fill_material)

    bm = bmesh.new()
    bm.from_mesh(guide_obj.data)
    bm.edges.ensure_lookup_table()
    matrix = guide_obj.matrix_world
    angle_limit = math.radians(args.feature_angle)
    segments = []
    angle_samples = []
    surface_polygons = 0
    front_facing_polygons = 0
    guide_faces = set()

    for face in bm.faces:
        world_center = matrix @ face.calc_center_median()
        relative = world_center - center
        if (
            abs(relative.dot(right)) <= half_w
            and abs(relative.dot(up)) <= half_h
            and abs(relative.dot(direction)) <= half_d
        ):
            surface_polygons += 1
            world_normal = (matrix.to_3x3() @ face.normal).normalized()
            if world_normal.dot(-direction) >= args.facing_threshold:
                front_facing_polygons += 1
                guide_faces.add(face)

    for edge in bm.edges:
        start = matrix @ edge.verts[0].co
        end = matrix @ edge.verts[1].co
        midpoint = (start + end) * 0.5
        relative = midpoint - center
        if (
            abs(relative.dot(right)) > half_w + args.edge_margin
            or abs(relative.dot(up)) > half_h + args.edge_margin
            or abs(relative.dot(direction)) > half_d + args.edge_margin
        ):
            continue
        if len(edge.link_faces) < 2:
            angle = math.pi
        else:
            angle = edge.calc_face_angle(0.0)
        angle_samples.append(math.degrees(angle))
        if angle >= angle_limit and (start - end).length >= args.min_edge_length:
            segments.append((start, end))

    # Split the visible surface at hard edges. These patches expose the real flat
    # armor regions a designer can fill without crossing a seam or chamfer.
    patches = []
    remaining_faces = set(guide_faces)
    while remaining_faces:
        seed = remaining_faces.pop()
        stack = [seed]
        patch_faces = [seed]
        while stack:
            face = stack.pop()
            for edge in face.edges:
                if len(edge.link_faces) > 1 and edge.calc_face_angle(0.0) >= angle_limit:
                    continue
                for neighbor in edge.link_faces:
                    if neighbor in remaining_faces:
                        remaining_faces.remove(neighbor)
                        patch_faces.append(neighbor)
                        stack.append(neighbor)
        vertices = {
            vertex
            for face in patch_faces
            for vertex in face.verts
        }
        world_vertices = [matrix @ vertex.co for vertex in vertices]
        u_values = [(vertex - center).dot(right) for vertex in world_vertices]
        v_values = [(vertex - center).dot(up) for vertex in world_vertices]
        d_values = [(vertex - center).dot(direction) for vertex in world_vertices]
        area = 0.0
        normal_sum = Vector((0.0, 0.0, 0.0))
        for face in patch_faces:
            points = [matrix @ vertex.co for vertex in face.verts]
            face_area = 0.0
            if len(points) >= 3:
                origin = points[0]
                for index in range(1, len(points) - 1):
                    face_area += (
                        (points[index] - origin).cross(points[index + 1] - origin).length
                        * 0.5
                    )
            area += face_area
            normal_sum += (matrix.to_3x3() @ face.normal).normalized() * face_area
        if area < args.min_patch_area:
            continue
        patch_normal = normal_sum.normalized() if normal_sum.length else Vector()
        patches.append(
            {
                "area": area,
                "faces": len(patch_faces),
                "u_range": [min(u_values), max(u_values)],
                "v_range": [min(v_values), max(v_values)],
                "depth_range": [min(d_values), max(d_values)],
                "normal": list(patch_normal),
            }
        )
    patches.sort(key=lambda item: item["area"], reverse=True)
    bm.free()

    line_material = _material("LIVERY_GUIDE_FEATURE_LINES", (0.025, 0.035, 0.04))
    line_obj = _curve_object(
        "LIVERY_STRUCTURE_FEATURE_LINES", segments, args.line_radius, line_material
    )
    line_obj.hide_render = False

    frame_material = _material("LIVERY_GUIDE_PROJECTOR_FRAME", (0.18, 0.38, 0.40))
    frame = _curve_object(
        "LIVERY_STRUCTURE_PROJECTOR_FRAME",
        _frame_segments(
            center,
            right,
            up,
            direction,
            size,
            args.depth,
            args.world_z_clip,
        ),
        args.frame_radius,
        frame_material,
    )
    frame.hide_render = False

    camera_data = bpy.data.cameras.new("LIVERY_STRUCTURE_GUIDE_CAMERA")
    camera = bpy.data.objects.new("LIVERY_STRUCTURE_GUIDE_CAMERA", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = size[1]
    camera.data.lens = 50
    camera.data.clip_start = 0.01
    camera.data.clip_end = max(50.0, args.camera_distance * 4.0)
    camera.location = center - direction * args.camera_distance
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = Path(args.metadata).resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    engine_items = scene.bl_rna.properties["render"].fixed_type.properties[
        "engine"
    ].enum_items
    engine_ids = {item.identifier for item in engine_items}
    scene.render.engine = (
        "BLENDER_EEVEE_NEXT"
        if "BLENDER_EEVEE_NEXT" in engine_ids
        else "BLENDER_EEVEE"
    )
    scene.render.resolution_x = args.resolution_width
    scene.render.resolution_y = max(
        1, round(args.resolution_width * size[1] / size[0])
    )
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.filepath = str(output)
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    look_items = scene.view_settings.bl_rna.properties["look"].enum_items
    look_ids = {item.identifier for item in look_items}
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        if look in look_ids:
            scene.view_settings.look = look
            break
    bpy.ops.render.render(write_still=True)

    world_vertices = [guide_obj.matrix_world @ vertex.co for vertex in guide_obj.data.vertices]
    bounds_min = [min(vertex[i] for vertex in world_vertices) for i in range(3)]
    bounds_max = [max(vertex[i] for vertex in world_vertices) for i in range(3)]
    metadata = {
        "version": 1,
        "kind": "projector-aligned-surface-structure-guide",
        "source_blend": bpy.data.filepath,
        "object": args.object,
        "output": str(output),
        "projector": {
            "center": list(center),
            "direction": list(direction),
            "up": list(up),
            "right": list(right),
            "size": size,
            "depth": args.depth,
            "facing_threshold": args.facing_threshold,
            "world_z_clip": args.world_z_clip,
        },
        "canvas": {
            "width": scene.render.resolution_x,
            "height": scene.render.resolution_y,
            "world_units_per_pixel": size[0] / scene.render.resolution_x,
            "u_axis": "projector right",
            "v_axis": "projector up",
        },
        "mesh_bounds": {"min": bounds_min, "max": bounds_max},
        "structure": {
            "feature_angle_degrees": args.feature_angle,
            "min_edge_length": args.min_edge_length,
            "feature_edges": len(segments),
            "candidate_edge_angle_min": min(angle_samples) if angle_samples else None,
            "candidate_edge_angle_max": max(angle_samples) if angle_samples else None,
            "polygons_in_projection_volume": surface_polygons,
            "front_facing_polygons": front_facing_polygons,
            "surface_patches": patches[: args.max_patches],
        },
        "design_use": [
            "compose artwork at the same pixel dimensions",
            "follow black feature lines and avoid crossing protruding hardware",
            "treat teal frame and horizontal clip lines as projector/safe boundaries",
            "keep the final bitmap aspect equal to projector.size width/height",
        ],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object", required=True)
    parser.add_argument("--center", type=_vec3, required=True)
    parser.add_argument("--direction", type=_vec3, required=True)
    parser.add_argument("--up", type=_vec3, required=True)
    parser.add_argument("--size", type=_vec2, required=True)
    parser.add_argument("--depth", type=float, required=True)
    parser.add_argument("--facing-threshold", type=float, default=0.08)
    parser.add_argument("--world-z-clip", type=_vec2)
    parser.add_argument("--feature-angle", type=float, default=16.0)
    parser.add_argument("--min-edge-length", type=float, default=0.018)
    parser.add_argument("--min-patch-area", type=float, default=0.003)
    parser.add_argument("--max-patches", type=int, default=40)
    parser.add_argument("--edge-margin", type=float, default=0.05)
    parser.add_argument("--line-radius", type=float, default=0.0032)
    parser.add_argument("--frame-radius", type=float, default=0.0022)
    parser.add_argument("--camera-distance", type=float, default=8.0)
    parser.add_argument("--resolution-width", type=int, default=1600)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    render_guide(parser.parse_args(_argv()))


if __name__ == "__main__":
    main()
