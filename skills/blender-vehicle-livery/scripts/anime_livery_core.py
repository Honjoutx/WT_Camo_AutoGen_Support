import copy
import fnmatch
import json
import re
import struct
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

import blender_livery_core as base


PROJECT_VERSION = 1
PROJECTOR_COLLECTION = "ANIME_Livery_Projectors"
SUPPORTED_BLEND_MODES = {"MIX", "MULTIPLY", "ADD", "SCREEN", "OVERLAY", "SOFT_LIGHT"}
SUPPORTED_ALPHA_MODES = {"IMAGE", "WHITE_KEY"}
SUPPORTED_ASPECT_POLICIES = {"FREE", "LIMIT", "PRESERVE"}
SUPPORTED_LAYER_SIDES = {"left", "right", "top", "front", "rear", "center"}
SUPPORTED_SEMANTIC_ROLES = {
    "underlay",
    "decal",
    "hero_art",
    "character_name",
    "text",
    "protective_effect",
}
SURFACE_CHANNELS = {
    "roughness": {"socket": "Roughness", "suffix": "Roughness", "default": 0.68},
    "metallic": {"socket": "Metallic", "suffix": "Metallic", "default": 0.0},
    "coat_weight": {"socket": "Coat Weight", "suffix": "CoatWeight", "default": 0.0},
    "coat_roughness": {
        "socket": "Coat Roughness",
        "suffix": "CoatRoughness",
        "default": 0.03,
    },
}


def _safe_token(value):
    token = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    return token or "layer"


def load_project(path):
    path = Path(path).resolve()
    project = json.loads(path.read_text(encoding="utf-8"))
    validate_project(project, path)
    return project


def validate_project(project, project_path=None):
    if int(project.get("version", 0)) != PROJECT_VERSION:
        raise ValueError(f"anime livery project version must be {PROJECT_VERSION}")
    if not str(project.get("name", "")).strip():
        raise ValueError("anime livery project requires a name")
    groups = project.get("target_groups")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("target_groups must be a non-empty object")
    allow_global = bool(project.get("allow_global_target", False))
    for group_name, patterns in groups.items():
        if not str(group_name).strip() or not isinstance(patterns, list) or not patterns:
            raise ValueError("each target group requires a name and at least one object pattern")
        if not allow_global and any(pattern == "*" for pattern in patterns):
            raise ValueError("global '*' target patterns require allow_global_target=true")

    layers = project.get("layers", [])
    if not isinstance(layers, list):
        raise ValueError("layers must be an array")
    layer_ids = set()
    for layer in layers:
        layer_id = str(layer.get("id", "")).strip()
        if not layer_id or layer_id in layer_ids:
            raise ValueError("every layer requires a unique non-empty id")
        layer_ids.add(layer_id)
        if layer.get("type", "image_projection") != "image_projection":
            raise ValueError(f"unsupported layer type for {layer_id}")
        targets = layer.get("targets", [])
        if not targets or not all(target in groups for target in targets):
            raise ValueError(f"layer {layer_id} must reference known target_groups")
        blend_mode = str(layer.get("blend_mode", "MIX")).upper()
        if blend_mode not in SUPPORTED_BLEND_MODES:
            raise ValueError(f"unsupported blend_mode for {layer_id}: {blend_mode}")
        alpha_mode = str(layer.get("alpha_mode", "IMAGE")).upper()
        if alpha_mode not in SUPPORTED_ALPHA_MODES:
            raise ValueError(f"unsupported alpha_mode for {layer_id}: {alpha_mode}")
        if alpha_mode == "WHITE_KEY":
            white_key_min = float(layer.get("white_key_min", 0.03))
            white_key_max = float(layer.get("white_key_max", 0.22))
            if not 0.0 <= white_key_min < white_key_max:
                raise ValueError(f"layer {layer_id} white-key range is invalid")
        image_region = layer.get("image_region")
        if image_region is not None:
            if not isinstance(image_region, list) or len(image_region) != 4:
                raise ValueError(f"layer {layer_id} image_region requires [u0, v0, u1, v1]")
            u0, v0, u1, v1 = (float(value) for value in image_region)
            if not (0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0):
                raise ValueError(f"layer {layer_id} image_region must be ordered inside [0, 1]")
        opacity = float(layer.get("opacity", 1.0))
        if not 0.0 <= opacity <= 1.0:
            raise ValueError(f"layer {layer_id} opacity must be in [0, 1]")
        surface = layer.get("surface")
        if surface is not None:
            if not isinstance(surface, dict):
                raise ValueError(f"layer {layer_id} surface must be an object")
            for channel in SURFACE_CHANNELS:
                if channel not in surface:
                    continue
                value = float(surface[channel])
                if not 0.0 <= value <= 1.0:
                    raise ValueError(
                        f"layer {layer_id} surface.{channel} must be in [0, 1]"
                    )
        side = layer.get("side")
        if side is not None and side not in SUPPORTED_LAYER_SIDES:
            raise ValueError(f"unsupported side for {layer_id}: {side}")
        semantic_role = layer.get("semantic_role")
        if semantic_role is not None and semantic_role not in SUPPORTED_SEMANTIC_ROLES:
            raise ValueError(
                f"unsupported semantic_role for {layer_id}: {semantic_role}"
            )
        pair_id = layer.get("pair_id")
        if pair_id is not None and not str(pair_id).strip():
            raise ValueError(f"layer {layer_id} pair_id cannot be empty")
        face_toward = layer.get("face_toward")
        if face_toward is not None and face_toward not in {"front", "rear"}:
            raise ValueError(f"unsupported face_toward for {layer_id}: {face_toward}")
        aspect_policy = str(layer.get("aspect_policy", "FREE")).upper()
        if aspect_policy not in SUPPORTED_ASPECT_POLICIES:
            raise ValueError(
                f"unsupported aspect_policy for {layer_id}: {aspect_policy}"
            )
        if layer.get("max_aspect_distortion") is not None:
            max_distortion = float(layer["max_aspect_distortion"])
            if not 0.0 <= max_distortion <= 1.0:
                raise ValueError(
                    f"layer {layer_id} max_aspect_distortion must be in [0, 1]"
                )
        _validate_projection(layer_id, layer.get("projection", {}))
    _validate_design_rules(project, layers, project_path)
    if project_path is not None:
        failures = [
            item
            for item in aspect_audit(project, project_path)
            if not item["passes"]
        ]
        if failures:
            details = "; ".join(
                f"{item['layer']}: {item['distortion']:.2%} > "
                f"{item['allowed_distortion']:.2%}"
                for item in failures
            )
            raise ValueError(f"image aspect distortion exceeds policy: {details}")
    return project


def _validate_projection(layer_id, projection):
    for field, count in (("center", 3), ("direction", 3), ("up", 3), ("size", 2)):
        value = projection.get(field)
        if not isinstance(value, list) or len(value) != count:
            raise ValueError(f"layer {layer_id} projection.{field} requires {count} numbers")
    if Vector(projection["direction"]).length < 1e-8:
        raise ValueError(f"layer {layer_id} projection.direction cannot be zero")
    if Vector(projection["up"]).length < 1e-8:
        raise ValueError(f"layer {layer_id} projection.up cannot be zero")
    if min(float(value) for value in projection["size"]) <= 0.0:
        raise ValueError(f"layer {layer_id} projection.size must be positive")
    if float(projection.get("depth", 1.0)) <= 0.0:
        raise ValueError(f"layer {layer_id} projection.depth must be positive")
    world_z_min = projection.get("world_z_min")
    world_z_max = projection.get("world_z_max")
    if world_z_min is not None and world_z_max is not None:
        if float(world_z_min) >= float(world_z_max):
            raise ValueError(f"layer {layer_id} projection world-Z range is invalid")


def _nearly_equal(left, right, tolerance=1e-4):
    return abs(float(left) - float(right)) <= tolerance


def _validate_mirrored_projection(left_layer, right_layer):
    left = left_layer["projection"]
    right = right_layer["projection"]
    left_center = left["center"]
    right_center = right["center"]
    if not (
        _nearly_equal(left_center[0], -right_center[0])
        and _nearly_equal(left_center[1], right_center[1])
        and _nearly_equal(left_center[2], right_center[2])
    ):
        raise ValueError(
            f"paired side layers {left_layer['id']} and {right_layer['id']} "
            "must use X-mirrored centers"
        )
    left_direction = left["direction"]
    right_direction = right["direction"]
    if not (
        _nearly_equal(left_direction[0], -right_direction[0])
        and _nearly_equal(left_direction[1], right_direction[1])
        and _nearly_equal(left_direction[2], right_direction[2])
    ):
        raise ValueError(
            f"paired side layers {left_layer['id']} and {right_layer['id']} "
            "must use X-mirrored directions"
        )
    if any(
        not _nearly_equal(left_value, right_value)
        for left_value, right_value in zip(left["size"], right["size"])
    ):
        raise ValueError(
            f"paired side layers {left_layer['id']} and {right_layer['id']} "
            "must use matching projection sizes"
        )
    for field in ("depth", "world_z_min", "world_z_max"):
        left_value = left.get(field)
        right_value = right.get(field)
        if (left_value is None) != (right_value is None) or (
            left_value is not None and not _nearly_equal(left_value, right_value)
        ):
            raise ValueError(
                f"paired side layers {left_layer['id']} and {right_layer['id']} "
                f"must use matching projection.{field}"
            )


def _validate_design_rules(project, layers, project_path=None):
    rules = project.get("design_rules", {})
    if not isinstance(rules, dict):
        raise ValueError("design_rules must be an object")
    if not rules:
        return

    by_id = {layer["id"]: layer for layer in layers}
    for layer in layers:
        pair_id = layer.get("pair_id")
        if pair_id is None:
            continue
        pair = by_id.get(pair_id)
        if pair is None:
            raise ValueError(f"layer {layer['id']} references missing pair_id {pair_id}")
        if pair.get("pair_id") != layer["id"]:
            raise ValueError(
                f"paired layers {layer['id']} and {pair_id} must reference each other"
            )

    if rules.get("paired_side_color_layers"):
        for layer in layers:
            if not layer.get("enabled", True):
                continue
            side = layer.get("side")
            role = layer.get("semantic_role")
            if side not in {"left", "right"} or role in {
                "hero_art",
                "character_name",
                "text",
            }:
                continue
            if role is None:
                raise ValueError(
                    f"paired side layer {layer['id']} requires semantic_role"
                )
            pair_id = layer.get("pair_id")
            if not pair_id:
                raise ValueError(
                    f"non-text side layer {layer['id']} requires a mirrored pair_id"
                )
            pair = by_id[pair_id]
            if {side, pair.get("side")} != {"left", "right"}:
                raise ValueError(
                    f"paired side layers {layer['id']} and {pair_id} must be left/right"
                )
            if pair.get("semantic_role") != role:
                raise ValueError(
                    f"paired side layers {layer['id']} and {pair_id} "
                    "must have the same semantic_role"
                )
            if pair.get("targets") != layer.get("targets"):
                raise ValueError(
                    f"paired side layers {layer['id']} and {pair_id} "
                    "must target the same groups"
                )
            left_layer = layer if side == "left" else pair
            right_layer = pair if side == "left" else layer
            _validate_mirrored_projection(left_layer, right_layer)

    if rules.get("hero_face_toward_vehicle_front"):
        hero_layers = [
            layer
            for layer in layers
            if layer.get("enabled", True)
            and layer.get("semantic_role") == "hero_art"
            and layer.get("side") in {"left", "right"}
        ]
        if not hero_layers:
            raise ValueError(
                "hero_face_toward_vehicle_front requires left/right hero_art layers"
            )
        for layer in hero_layers:
            if layer.get("face_toward") != "front":
                raise ValueError(
                    f"hero layer {layer['id']} must set face_toward='front'"
                )
            pair_id = layer.get("pair_id")
            if not pair_id:
                raise ValueError(f"hero layer {layer['id']} requires pair_id")
            pair = by_id[pair_id]
            if pair.get("semantic_role") != "hero_art" or {
                layer.get("side"),
                pair.get("side"),
            } != {"left", "right"}:
                raise ValueError(
                    f"hero pair {layer['id']} and {pair_id} must be left/right hero_art"
                )
            if layer.get("image") == pair.get("image"):
                layer_flip = bool(layer["projection"].get("flip_x", False))
                pair_flip = bool(pair["projection"].get("flip_x", False))
                if layer_flip == pair_flip:
                    raise ValueError(
                        f"hero pair {layer['id']} and {pair_id} reuses one image; "
                        "opposite flip_x values are required to keep both faces forward"
                    )
            left_layer = layer if layer.get("side") == "left" else pair
            right_layer = pair if layer.get("side") == "left" else layer
            _validate_mirrored_projection(left_layer, right_layer)

    if rules.get("only_character_name_above_hero_art"):
        hero_indices = [
            index
            for index, layer in enumerate(layers)
            if layer.get("enabled", True)
            and layer.get("semantic_role") == "hero_art"
        ]
        if not hero_indices:
            raise ValueError(
                "only_character_name_above_hero_art requires hero_art layers"
            )
        for layer in layers[min(hero_indices) + 1 :]:
            if not layer.get("enabled", True):
                continue
            if layer.get("semantic_role") not in {"hero_art", "character_name"}:
                raise ValueError(
                    f"layer {layer['id']} is above hero art; only character_name is allowed"
                )
        for layer in layers:
            if layer.get("semantic_role") != "character_name":
                continue
            if str(layer.get("alpha_mode", "IMAGE")).upper() != "IMAGE":
                raise ValueError(
                    f"character-name layer {layer['id']} must use alpha_mode='IMAGE'"
                )

    if rules.get("hero_art_preserve_aspect"):
        hero_layers = [
            layer
            for layer in layers
            if layer.get("enabled", True)
            and layer.get("semantic_role") == "hero_art"
        ]
        if not hero_layers:
            raise ValueError("hero_art_preserve_aspect requires hero_art layers")
        for layer in hero_layers:
            if str(layer.get("aspect_policy", "FREE")).upper() != "PRESERVE":
                raise ValueError(
                    f"hero layer {layer['id']} must set aspect_policy='PRESERVE'"
                )

    max_other_distortion = rules.get("max_other_aspect_distortion")
    if max_other_distortion is not None:
        max_other_distortion = float(max_other_distortion)
        if not 0.0 <= max_other_distortion <= 1.0:
            raise ValueError("max_other_aspect_distortion must be in [0, 1]")

    if rules.get("record_iteration_in_skill"):
        record = project.get("iteration_record")
        if not isinstance(record, dict):
            raise ValueError("record_iteration_in_skill requires iteration_record")
        for field in ("id", "finding", "change", "validation"):
            if not str(record.get(field, "")).strip():
                raise ValueError(f"iteration_record requires {field}")
        skill_updates = record.get("skill_updates")
        if not isinstance(skill_updates, list) or not skill_updates:
            raise ValueError("iteration_record requires non-empty skill_updates")

    if rules.get("surface_direction_contract"):
        active_sides = set()
        for layer in layers:
            if not layer.get("enabled", True):
                continue
            side = layer.get("side")
            if side not in {"top", "front", "rear"}:
                continue
            active_sides.add(side)
            direction = Vector(layer["projection"]["direction"]).normalized()
            valid_direction = (
                side == "top" and direction.z <= -0.9
                or side == "front" and direction.y >= 0.9
                or side == "rear" and direction.y <= -0.9
            )
            if not valid_direction:
                raise ValueError(
                    f"layer {layer['id']} side={side} uses an incompatible "
                    f"projection direction {list(layer['projection']['direction'])}"
                )
        render_names = {
            str(view.get("name", ""))
            for view in project.get("render", {}).get("views", [])
        }
        required_views = {
            "top": "top_check",
            "front": "front",
            "rear": "rear",
        }
        for side in active_sides:
            required_view = required_views[side]
            if required_view not in render_names:
                raise ValueError(
                    f"surface_direction_contract requires render view {required_view}"
                )

    if rules.get("front_rear_bilateral_graphics"):
        for layer in layers:
            if not layer.get("enabled", True):
                continue
            if layer.get("side") not in {"front", "rear"}:
                continue
            if layer.get("semantic_role") in {"text", "character_name"}:
                continue
            source = layer.get("source", {})
            if not isinstance(source, dict) or not source.get("bilateral_symmetric"):
                raise ValueError(
                    f"front/rear graphic {layer['id']} must declare "
                    "source.bilateral_symmetric=true"
                )

    if rules.get("structure_guide_contract"):
        guides = project.get("structure_guides")
        if not isinstance(guides, list) or not guides:
            raise ValueError(
                "structure_guide_contract requires non-empty structure_guides"
            )
        guide_ids = set()
        guided_layers = set()
        groups = project.get("target_groups", {})
        for guide in guides:
            if not isinstance(guide, dict):
                raise ValueError("every structure guide must be an object")
            guide_id = str(guide.get("id", "")).strip()
            if not guide_id or guide_id in guide_ids:
                raise ValueError("every structure guide requires a unique id")
            guide_ids.add(guide_id)
            side = guide.get("side")
            if side not in SUPPORTED_LAYER_SIDES - {"center"}:
                raise ValueError(
                    f"structure guide {guide_id} requires a supported surface side"
                )
            targets = guide.get("targets")
            if (
                not isinstance(targets, list)
                or not targets
                or not all(target in groups for target in targets)
            ):
                raise ValueError(
                    f"structure guide {guide_id} must reference known target_groups"
                )
            projection = guide.get("projection")
            if not isinstance(projection, dict):
                raise ValueError(f"structure guide {guide_id} requires projection")
            _validate_projection(f"structure guide {guide_id}", projection)
            designed_layers = guide.get("designed_layers")
            if not isinstance(designed_layers, list) or not designed_layers:
                raise ValueError(
                    f"structure guide {guide_id} requires designed_layers"
                )
            for layer_id in designed_layers:
                if layer_id in guided_layers:
                    raise ValueError(
                        f"layer {layer_id} is assigned to more than one structure guide"
                    )
                layer = by_id.get(layer_id)
                if layer is None:
                    raise ValueError(
                        f"structure guide {guide_id} references missing layer {layer_id}"
                    )
                guided_layers.add(layer_id)
                if layer.get("side") != side or layer.get("targets") != targets:
                    raise ValueError(
                        f"structure-guided layer {layer_id} must match guide {guide_id} "
                        "side and targets"
                    )
                if layer.get("source", {}).get("guide_id") != guide_id:
                    raise ValueError(
                        f"structure-guided layer {layer_id} must declare "
                        f"source.guide_id={guide_id}"
                    )
                layer_projection = layer.get("projection", {})
                for field in ("center", "direction", "up", "size"):
                    left = projection.get(field, [])
                    right_value = layer_projection.get(field, [])
                    if len(left) != len(right_value) or any(
                        not _nearly_equal(a, b) for a, b in zip(left, right_value)
                    ):
                        raise ValueError(
                            f"structure-guided layer {layer_id} projection.{field} "
                            f"must match guide {guide_id}"
                        )
                for field in ("depth", "world_z_min", "world_z_max"):
                    guide_value = projection.get(field)
                    layer_value = layer_projection.get(field)
                    if (guide_value is None) != (layer_value is None) or (
                        guide_value is not None
                        and not _nearly_equal(guide_value, layer_value)
                    ):
                        raise ValueError(
                            f"structure-guided layer {layer_id} projection.{field} "
                            f"must match guide {guide_id}"
                        )
            for field in ("image", "metadata"):
                if not str(guide.get(field, "")).strip():
                    raise ValueError(f"structure guide {guide_id} requires {field}")
            if project_path is not None:
                image_path = resolve_path(guide["image"], project_path)
                metadata_path = resolve_path(guide["metadata"], project_path)
                if not image_path.is_file() or not metadata_path.is_file():
                    raise ValueError(
                        f"structure guide {guide_id} image/metadata files must exist"
                    )
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("kind") != "projector-aligned-surface-structure-guide":
                    raise ValueError(
                        f"structure guide {guide_id} metadata kind is invalid"
                    )

    if rules.get("macro_geometry_asset_contract"):
        macro = project.get("macro_composition")
        if not isinstance(macro, dict):
            raise ValueError(
                "macro_geometry_asset_contract requires a macro_composition object"
            )
        geometry_plan_id = str(macro.get("geometry_plan_id", "")).strip()
        if not geometry_plan_id:
            raise ValueError("macro_composition requires geometry_plan_id")

        large_planes = macro.get("large_planes")
        if not isinstance(large_planes, list) or not large_planes:
            raise ValueError("macro_composition requires non-empty large_planes")
        declared_guide_ids = {
            str(guide.get("id", "")).strip()
            for guide in project.get("structure_guides", [])
            if isinstance(guide, dict)
        }
        render_names = {
            str(view.get("name", ""))
            for view in project.get("render", {}).get("views", [])
        }
        plane_ids = set()
        coverage_layer_ids = set()
        for plane in large_planes:
            if not isinstance(plane, dict):
                raise ValueError("every macro large plane must be an object")
            plane_id = str(plane.get("id", "")).strip()
            if not plane_id or plane_id in plane_ids:
                raise ValueError("every macro large plane requires a unique id")
            plane_ids.add(plane_id)
            guide_id = str(plane.get("guide_id", "")).strip()
            if not guide_id:
                raise ValueError(f"macro large plane {plane_id} requires guide_id")
            if declared_guide_ids and guide_id not in declared_guide_ids:
                raise ValueError(
                    f"macro large plane {plane_id} references unknown guide_id {guide_id}"
                )
            geometry_plan_asset = str(
                plane.get("geometry_plan_asset", "")
            ).strip()
            if not geometry_plan_asset:
                raise ValueError(
                    f"macro large plane {plane_id} requires geometry_plan_asset"
                )
            if project_path is not None and not resolve_path(
                geometry_plan_asset, project_path
            ).is_file():
                raise ValueError(
                    f"macro large plane {plane_id} geometry plan asset must exist"
                )
            if not str(plane.get("coverage_basis", "")).strip():
                raise ValueError(
                    f"macro large plane {plane_id} requires coverage_basis"
                )
            plane_layers = plane.get("coverage_layers")
            if (
                not isinstance(plane_layers, list)
                or not plane_layers
                or len(plane_layers) != len(set(plane_layers))
            ):
                raise ValueError(
                    f"macro large plane {plane_id} requires unique coverage_layers"
                )
            for layer_id in plane_layers:
                layer = by_id.get(layer_id)
                if layer is None or not layer.get("enabled", True):
                    raise ValueError(
                        f"macro large plane {plane_id} references missing or disabled "
                        f"coverage layer {layer_id}"
                    )
                if layer.get("semantic_role") != "underlay":
                    raise ValueError(
                        f"macro coverage layer {layer_id} must use semantic_role=underlay"
                    )
                if layer_id in coverage_layer_ids:
                    raise ValueError(
                        f"macro coverage layer {layer_id} is assigned to multiple planes"
                    )
                coverage_layer_ids.add(layer_id)
            target_min = float(plane.get("target_coverage_min", -1.0))
            target_max = float(plane.get("target_coverage_max", -1.0))
            if not 0.55 <= target_min < target_max <= 0.95:
                raise ValueError(
                    f"macro large plane {plane_id} coverage target must satisfy "
                    "0.55 <= min < max <= 0.95"
                )
            negative_space = plane.get("intentional_negative_space")
            if (
                not isinstance(negative_space, list)
                or not negative_space
                or not all(str(item).strip() for item in negative_space)
            ):
                raise ValueError(
                    f"macro large plane {plane_id} must document intentional_negative_space"
                )
            verification_views = plane.get("verification_views")
            if (
                not isinstance(verification_views, list)
                or not verification_views
                or not all(str(item).strip() for item in verification_views)
            ):
                raise ValueError(
                    f"macro large plane {plane_id} requires verification_views"
                )
            missing_views = sorted(set(verification_views) - render_names)
            if missing_views:
                raise ValueError(
                    f"macro large plane {plane_id} requires render views {missing_views}"
                )

        color_blocks = macro.get("color_blocks")
        if not isinstance(color_blocks, list) or not color_blocks:
            raise ValueError("macro_composition requires non-empty color_blocks")
        color_block_ids = set()
        color_block_assets = set()
        assigned_layer_ids = set()
        for block in color_blocks:
            if not isinstance(block, dict):
                raise ValueError("every macro color block must be an object")
            block_id = str(block.get("id", "")).strip()
            if not block_id or block_id in color_block_ids:
                raise ValueError("every macro color block requires a unique id")
            color_block_ids.add(block_id)
            color = str(block.get("color", "")).strip()
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise ValueError(
                    f"macro color block {block_id} color must be #RRGGBB"
                )
            asset = str(block.get("asset", "")).strip()
            if not asset or asset in color_block_assets:
                raise ValueError(
                    f"macro color block {block_id} requires its own unique asset"
                )
            color_block_assets.add(asset)
            block_layers = block.get("layer_ids")
            if (
                not isinstance(block_layers, list)
                or not block_layers
                or len(block_layers) != len(set(block_layers))
            ):
                raise ValueError(
                    f"macro color block {block_id} requires unique layer_ids"
                )
            for layer_id in block_layers:
                layer = by_id.get(layer_id)
                if layer is None or not layer.get("enabled", True):
                    raise ValueError(
                        f"macro color block {block_id} references missing or disabled "
                        f"layer {layer_id}"
                    )
                if layer_id in assigned_layer_ids:
                    raise ValueError(
                        f"macro layer {layer_id} is assigned to multiple color blocks"
                    )
                assigned_layer_ids.add(layer_id)
                if layer.get("semantic_role") != "underlay":
                    raise ValueError(
                        f"macro color-block layer {layer_id} must use "
                        "semantic_role=underlay"
                    )
                if str(layer.get("image", "")).strip() != asset:
                    raise ValueError(
                        f"macro color-block layer {layer_id} must use asset {asset}"
                    )
                source = layer.get("source")
                if not isinstance(source, dict):
                    raise ValueError(
                        f"macro color-block layer {layer_id} requires source metadata"
                    )
                if source.get("geometry_plan_id") != geometry_plan_id:
                    raise ValueError(
                        f"macro color-block layer {layer_id} must declare "
                        f"source.geometry_plan_id={geometry_plan_id}"
                    )
                if source.get("color_block_id") != block_id:
                    raise ValueError(
                        f"macro color-block layer {layer_id} must declare "
                        f"source.color_block_id={block_id}"
                    )
                if source.get("single_color_asset") is not True:
                    raise ValueError(
                        f"macro color-block layer {layer_id} must declare "
                        "source.single_color_asset=true"
                    )
        if assigned_layer_ids != coverage_layer_ids:
            missing = sorted(coverage_layer_ids - assigned_layer_ids)
            extra = sorted(assigned_layer_ids - coverage_layer_ids)
            raise ValueError(
                "macro color blocks must map exactly to large-plane coverage layers; "
                f"missing={missing}, extra={extra}"
            )

        decal_layers = {
            layer["id"]
            for layer in layers
            if layer.get("enabled", True)
            and layer.get("semantic_role") == "decal"
        }
        decals = macro.get("decals")
        if decals is None:
            if decal_layers:
                raise ValueError(
                    "macro_composition.decals must declare every enabled decal layer"
                )
        else:
            if not isinstance(decals, dict):
                raise ValueError("macro_composition.decals must be an object")
            declared_decal_layers = decals.get("layer_ids")
            if (
                not isinstance(declared_decal_layers, list)
                or len(declared_decal_layers) != len(set(declared_decal_layers))
            ):
                raise ValueError("macro decals require unique layer_ids")
            if set(declared_decal_layers) != decal_layers:
                raise ValueError(
                    "macro decal layer_ids must match all enabled semantic_role=decal layers"
                )
            max_total = int(decals.get("max_total", -1))
            max_per_surface = int(decals.get("max_per_surface", -1))
            if not 0 <= max_total <= 12:
                raise ValueError("macro decals max_total must be in [0, 12]")
            if not 1 <= max_per_surface <= 4:
                raise ValueError("macro decals max_per_surface must be in [1, 4]")
            if len(declared_decal_layers) > max_total:
                raise ValueError("macro decal layer count exceeds max_total")
            style_families = decals.get("style_families")
            if declared_decal_layers and (
                not isinstance(style_families, list)
                or not 1 <= len(style_families) <= 3
                or len(style_families) != len(set(style_families))
                or not all(str(item).strip() for item in style_families)
            ):
                raise ValueError(
                    "macro decals require one to three unique style_families"
                )
            if decals.get("provenance_required") is not True:
                raise ValueError("macro decals require provenance_required=true")
            surface_counts = {}
            for layer_id in declared_decal_layers:
                layer = by_id[layer_id]
                source = layer.get("source")
                if not isinstance(source, dict):
                    raise ValueError(f"decal layer {layer_id} requires source metadata")
                family = str(source.get("decal_family", "")).strip()
                if family not in style_families:
                    raise ValueError(
                        f"decal layer {layer_id} uses undeclared decal_family {family}"
                    )
                surface_id = str(source.get("decal_surface_id", "")).strip()
                if not surface_id:
                    raise ValueError(
                        f"decal layer {layer_id} requires source.decal_surface_id"
                    )
                surface_counts[surface_id] = surface_counts.get(surface_id, 0) + 1
                provenance = source.get("provenance")
                if not isinstance(provenance, dict):
                    raise ValueError(f"decal layer {layer_id} requires provenance")
                provenance_kind = str(provenance.get("kind", "")).strip()
                if provenance_kind == "online":
                    for field in ("url", "license", "retrieved_at"):
                        if not str(provenance.get(field, "")).strip():
                            raise ValueError(
                                f"online decal layer {layer_id} provenance requires {field}"
                            )
                elif provenance_kind == "generated":
                    if not str(source.get("prompt", provenance.get("prompt", ""))).strip():
                        raise ValueError(
                            f"generated decal layer {layer_id} requires a prompt"
                        )
                elif provenance_kind in {"user-provided", "local"}:
                    if not str(provenance.get("local_reference", "")).strip():
                        raise ValueError(
                            f"local decal layer {layer_id} requires local_reference"
                        )
                else:
                    raise ValueError(
                        f"decal layer {layer_id} provenance.kind must be online, "
                        "generated, user-provided, or local"
                    )
            crowded_surfaces = sorted(
                surface_id
                for surface_id, count in surface_counts.items()
                if count > max_per_surface
            )
            if crowded_surfaces:
                raise ValueError(
                    "macro decal count exceeds max_per_surface on "
                    f"{crowded_surfaces}"
                )

    if rules.get("edge_continuity_contract"):
        required_edges = {"left", "right", "front", "rear"}
        connected_edges = set()
        continuity_layers = []
        for layer in layers:
            if (
                not layer.get("enabled", True)
                or layer.get("side") != "top"
                or "body" not in layer.get("targets", [])
            ):
                continue
            source = layer.get("source", {})
            if not isinstance(source, dict):
                continue
            edge_connections = source.get("edge_connections", [])
            if edge_connections:
                if not isinstance(edge_connections, list) or not all(
                    edge in required_edges for edge in edge_connections
                ):
                    raise ValueError(
                        f"top continuity layer {layer['id']} uses invalid "
                        "source.edge_connections"
                    )
                if not str(source.get("turn_transition", "")).strip():
                    raise ValueError(
                        f"top continuity layer {layer['id']} requires "
                        "source.turn_transition"
                    )
                connected_edges.update(edge_connections)
                continuity_layers.append(layer["id"])
        if connected_edges != required_edges:
            missing = sorted(required_edges - connected_edges)
            raise ValueError(
                "edge_continuity_contract requires body-top layers connected to "
                f"left/right/front/rear; missing {missing}"
            )
        render_names = {
            str(view.get("name", ""))
            for view in project.get("render", {}).get("views", [])
        }
        required_views = {
            "left_front_top",
            "right_front_top",
            "left_rear_top",
            "right_rear_top",
        }
        missing_views = sorted(required_views - render_names)
        if missing_views:
            raise ValueError(
                "edge_continuity_contract requires high three-quarter views; "
                f"missing {missing_views}"
            )

    if rules.get("radar_isolation_contract"):
        isolation = project.get("radar_isolation")
        if not isinstance(isolation, dict):
            raise ValueError(
                "radar_isolation_contract requires a radar_isolation object"
            )
        target_group = str(isolation.get("target_group", "")).strip()
        if target_group not in project.get("target_groups", {}):
            raise ValueError(
                "radar_isolation.target_group must reference a known target group"
            )
        required_sides = set(isolation.get("required_sides", []))
        if not required_sides or not required_sides <= {"front", "rear", "top"}:
            raise ValueError(
                "radar_isolation.required_sides must use front/rear/top"
            )
        minimum_world_z = isolation.get("minimum_world_z")
        if minimum_world_z is None:
            raise ValueError("radar_isolation requires minimum_world_z")
        minimum_world_z = float(minimum_world_z)
        required_equipment_zones_raw = isolation.get(
            "required_equipment_zones", []
        )
        if (
            not isinstance(required_equipment_zones_raw, list)
            or len(required_equipment_zones_raw)
            != len(set(required_equipment_zones_raw))
            or not all(str(item).strip() for item in required_equipment_zones_raw)
        ):
            raise ValueError(
                "radar_isolation.required_equipment_zones must be a unique "
                "non-empty-string list"
            )
        required_equipment_zones = set(required_equipment_zones_raw)
        equipment_zones = isolation.get("equipment_zones", {})
        if required_equipment_zones:
            if not isinstance(equipment_zones, dict):
                raise ValueError(
                    "radar_isolation equipment_zones must be an object"
                )
            declared_zones = {
                str(zone_id).strip() for zone_id in equipment_zones
            }
            if declared_zones != required_equipment_zones:
                raise ValueError(
                    "radar_isolation equipment_zones must exactly match "
                    "required_equipment_zones"
                )
            for zone_id, zone in equipment_zones.items():
                if not isinstance(zone, dict):
                    raise ValueError(
                        f"radar equipment zone {zone_id} must be an object"
                    )
                zone_minimum_world_z = float(
                    zone.get("minimum_world_z", minimum_world_z)
                )
                if zone_minimum_world_z < minimum_world_z - 1e-4:
                    raise ValueError(
                        f"radar equipment zone {zone_id} minimum_world_z "
                        f"must be at or above {minimum_world_z}"
                    )
                required_depth_range = zone.get("required_depth_range")
                if required_depth_range is not None:
                    if (
                        not isinstance(required_depth_range, list)
                        or len(required_depth_range) != 2
                    ):
                        raise ValueError(
                            f"radar equipment zone {zone_id} "
                            "required_depth_range must contain two numbers"
                        )
                    depth_min, depth_max = map(float, required_depth_range)
                    if depth_min > depth_max:
                        raise ValueError(
                            f"radar equipment zone {zone_id} "
                            "required_depth_range must be ordered"
                        )
        radar_layers = [
            layer
            for layer in layers
            if layer.get("enabled", True)
            and isinstance(layer.get("source"), dict)
            and layer["source"].get("equipment_role") == "radar"
        ]
        if not radar_layers:
            raise ValueError(
                "radar_isolation_contract requires enabled radar equipment layers"
            )
        active_sides = set()
        active_equipment_zones = set()
        for layer in radar_layers:
            side = layer.get("side")
            active_sides.add(side)
            source = layer.get("source", {})
            equipment_zone = str(source.get("equipment_zone", "")).strip()
            if required_equipment_zones:
                if equipment_zone not in required_equipment_zones:
                    raise ValueError(
                        f"radar layer {layer['id']} must declare a known "
                        "source.equipment_zone"
                    )
                active_equipment_zones.add(equipment_zone)
            if layer.get("targets") != [target_group]:
                raise ValueError(
                    f"radar layer {layer['id']} must target only {target_group}"
                )
            if side not in required_sides:
                raise ValueError(
                    f"radar layer {layer['id']} uses undeclared side {side}"
                )
            projection = layer.get("projection", {})
            world_z_min = projection.get("world_z_min")
            zone = equipment_zones.get(equipment_zone, {})
            layer_minimum_world_z = float(
                zone.get("minimum_world_z", minimum_world_z)
            )
            if (
                world_z_min is None
                or float(world_z_min) < layer_minimum_world_z - 1e-4
            ):
                raise ValueError(
                    f"radar layer {layer['id']} must set projection.world_z_min "
                    f"at or above {layer_minimum_world_z}"
                )
            required_depth_range = zone.get("required_depth_range")
            if required_depth_range is not None:
                depth = float(projection.get("depth", 0.0))
                required_half_depth = max(
                    abs(float(required_depth_range[0])),
                    abs(float(required_depth_range[1])),
                )
                if depth * 0.5 < required_half_depth - 1e-4:
                    raise ValueError(
                        f"radar layer {layer['id']} projection.depth does not "
                        f"cover equipment zone {equipment_zone} required_depth_range"
                    )
            if not str(layer.get("source", {}).get("guide_id", "")).strip():
                raise ValueError(
                    f"radar layer {layer['id']} must declare source.guide_id"
                )
        if not required_sides <= active_sides:
            missing_sides = sorted(required_sides - active_sides)
            raise ValueError(
                "radar_isolation_contract requires radar layers for all declared "
                f"surfaces; missing {missing_sides}"
            )
        if required_equipment_zones and not (
            required_equipment_zones <= active_equipment_zones
        ):
            missing_zones = sorted(
                required_equipment_zones - active_equipment_zones
            )
            raise ValueError(
                "radar_isolation_contract requires layers for all declared "
                f"equipment zones; missing {missing_zones}"
            )
        required_views = set(isolation.get("verification_views", []))
        if not required_views:
            raise ValueError(
                "radar_isolation requires non-empty verification_views"
            )
        render_names = {
            str(view.get("name", ""))
            for view in project.get("render", {}).get("views", [])
        }
        missing_views = sorted(required_views - render_names)
        if missing_views:
            raise ValueError(
                "radar_isolation_contract requires dedicated radar verification "
                f"views; missing {missing_views}"
            )


def _jpeg_dimensions(stream):
    if stream.read(2) != b"\xff\xd8":
        raise ValueError("not a JPEG file")
    start_of_frame = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while True:
        prefix = stream.read(1)
        if not prefix:
            break
        if prefix != b"\xff":
            continue
        marker_byte = stream.read(1)
        while marker_byte == b"\xff":
            marker_byte = stream.read(1)
        if not marker_byte:
            break
        marker = marker_byte[0]
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        length_data = stream.read(2)
        if len(length_data) != 2:
            break
        segment_length = struct.unpack(">H", length_data)[0]
        if segment_length < 2:
            break
        if marker in start_of_frame:
            payload = stream.read(5)
            if len(payload) != 5:
                break
            height, width = struct.unpack(">HH", payload[1:])
            return width, height
        stream.seek(segment_length - 2, 1)
    raise ValueError("JPEG dimensions were not found")


def image_dimensions(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        signature = stream.read(24)
        if signature.startswith(b"\x89PNG\r\n\x1a\n") and len(signature) >= 24:
            return struct.unpack(">II", signature[16:24])
        stream.seek(0)
        if signature.startswith(b"\xff\xd8"):
            return _jpeg_dimensions(stream)
    image = bpy.data.images.load(str(path), check_existing=True)
    return int(image.size[0]), int(image.size[1])


def aspect_audit(project, project_path):
    project_path = Path(project_path).resolve()
    rules = project.get("design_rules", {})
    global_other_limit = rules.get("max_other_aspect_distortion")
    if global_other_limit is not None:
        global_other_limit = float(global_other_limit)
    results = []
    for layer in project.get("layers", []):
        if not layer.get("enabled", True) or not layer.get("image"):
            continue
        image_path = resolve_path(layer["image"], project_path)
        width, height = image_dimensions(image_path)
        image_region = layer.get("image_region", [0.0, 0.0, 1.0, 1.0])
        u0, v0, u1, v1 = (float(value) for value in image_region)
        source_aspect = (width * (u1 - u0)) / (height * (v1 - v0))
        size = layer["projection"]["size"]
        projected_aspect = float(size[0]) / float(size[1])
        ratio = projected_aspect / source_aspect
        distortion = max(ratio, 1.0 / ratio) - 1.0
        policy = str(layer.get("aspect_policy", "FREE")).upper()
        if policy == "PRESERVE":
            allowed = 0.005
        elif layer.get("max_aspect_distortion") is not None:
            allowed = float(layer["max_aspect_distortion"])
        elif (
            global_other_limit is not None
            and layer.get("semantic_role") != "hero_art"
        ):
            allowed = global_other_limit
        elif policy == "LIMIT":
            allowed = 0.15
        else:
            allowed = None
        results.append(
            {
                "layer": layer["id"],
                "image": str(image_path),
                "pixel_size": [width, height],
                "sampled_aspect": round(source_aspect, 6),
                "projected_aspect": round(projected_aspect, 6),
                "distortion": round(distortion, 6),
                "aspect_policy": policy,
                "allowed_distortion": allowed,
                "passes": allowed is None or distortion <= allowed + 1e-6,
            }
        )
    return results


def resolve_path(value, project_path):
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path(project_path).resolve().parent / candidate
    return candidate.resolve()


def _base_preset(project, project_path):
    base_spec = project.get("base", {})
    if base_spec.get("preset"):
        preset_path = resolve_path(base_spec["preset"], project_path)
        preset = base.load_json(preset_path)
        return preset, preset_path
    color = base_spec.get("color", "#E8E8E8")
    preset = {
        "name": f"{project['name']}-base",
        "colors": [color, color],
        "thresholds": [0.0, 1.0],
        "pattern_scale": 1.0,
        "noise_detail": 0.0,
        "noise_roughness": 0.0,
        "noise_distortion": 0.0,
        "roughness": float(base_spec.get("roughness", 0.68)),
        "metallic": float(base_spec.get("metallic", 0.0)),
        "coat_weight": float(base_spec.get("coat_weight", 0.0)),
        "coat_roughness": float(base_spec.get("coat_roughness", 0.03)),
        "micro_bump_strength": float(base_spec.get("micro_bump_strength", 0.03)),
        "micro_bump_scale": float(base_spec.get("micro_bump_scale", 32.0)),
    }
    return preset, None


def dependency_snapshot(project_path, project=None):
    project_path = Path(project_path).resolve()
    project = project or load_project(project_path)
    paths = [project_path]
    base_spec = project.get("base", {})
    if base_spec.get("preset"):
        paths.append(resolve_path(base_spec["preset"], project_path))
    for layer in project.get("layers", []):
        if layer.get("image"):
            paths.append(resolve_path(layer["image"], project_path))
    return {
        str(path): path.stat().st_mtime_ns if path.exists() else None
        for path in paths
    }


def _projector_collection():
    collection = bpy.data.collections.get(PROJECTOR_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(PROJECTOR_COLLECTION)
        bpy.context.scene.collection.children.link(collection)
    return collection


def projector_name(project_name, layer_id):
    return f"ANIME_Projector_{_safe_token(project_name)}_{_safe_token(layer_id)}"


def layer_node_name(layer_id, suffix):
    return f"ANIME_{_safe_token(layer_id)}_{suffix}"


def _projection_axes(projection):
    direction = Vector(projection["direction"]).normalized()
    z_axis = -direction
    up = Vector(projection["up"]).normalized()
    y_axis = up - z_axis * up.dot(z_axis)
    if y_axis.length < 1e-6:
        raise ValueError("projection.up cannot be parallel to projection.direction")
    y_axis.normalize()
    x_axis = y_axis.cross(z_axis).normalized()
    y_axis = z_axis.cross(x_axis).normalized()
    return x_axis, y_axis, z_axis


def ensure_projector(project_name, layer):
    name = projector_name(project_name, layer["id"])
    projector = bpy.data.objects.get(name)
    if projector is None:
        projector = bpy.data.objects.new(name, None)
        _projector_collection().objects.link(projector)
    projection = layer["projection"]
    x_axis, y_axis, z_axis = _projection_axes(projection)
    basis = Matrix((x_axis, y_axis, z_axis)).transposed()
    projector.location = tuple(float(value) for value in projection["center"])
    projector.rotation_mode = "QUATERNION"
    projector.rotation_quaternion = basis.to_quaternion()
    size = projection["size"]
    projector.scale = (
        float(size[0]),
        float(size[1]),
        float(projection.get("depth", 1.0)),
    )
    projector.empty_display_type = "CUBE"
    projector.empty_display_size = 0.5
    projector.show_in_front = True
    projector.hide_render = True
    projector.color = (0.12, 0.55, 1.0, 0.8)
    projector["anime_project"] = project_name
    projector["anime_layer_id"] = layer["id"]
    return projector


def projection_from_projector(projector):
    basis = projector.matrix_world.to_3x3().normalized()
    y_axis = basis.col[1].normalized()
    z_axis = basis.col[2].normalized()
    direction = -z_axis
    return {
        "center": [round(float(value), 6) for value in projector.matrix_world.translation],
        "direction": [round(float(value), 6) for value in direction],
        "up": [round(float(value), 6) for value in y_axis],
        "size": [abs(float(projector.scale.x)), abs(float(projector.scale.y))],
        "depth": abs(float(projector.scale.z)),
    }


def sync_projectors_to_project(project):
    for layer in project.get("layers", []):
        projector = bpy.data.objects.get(projector_name(project["name"], layer["id"]))
        if projector is not None:
            projection = projection_from_projector(projector)
            projection["facing_threshold"] = float(
                layer.get("projection", {}).get("facing_threshold", 0.05)
            )
            projection["flip_x"] = bool(layer.get("projection", {}).get("flip_x", False))
            projection["flip_y"] = bool(layer.get("projection", {}).get("flip_y", False))
            if "world_z_min" in layer.get("projection", {}):
                projection["world_z_min"] = float(layer["projection"]["world_z_min"])
            if "world_z_max" in layer.get("projection", {}):
                projection["world_z_max"] = float(layer["projection"]["world_z_max"])
            layer["projection"] = projection
    return project


def save_project(path, project):
    path = Path(path).resolve()
    validate_project(project, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _load_image(path, color_space="sRGB", reload_image=False):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"livery image not found: {path}")
    image = bpy.data.images.load(str(path), check_existing=True)
    if reload_image:
        image.reload()
    image.colorspace_settings.name = color_space
    image.alpha_mode = "STRAIGHT"
    return image


def _math_node(nodes, operation, name, location):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    node.name = name
    node.label = name
    node.location = location
    return node


def _value_node(nodes, name, value, location):
    node = nodes.new("ShaderNodeValue")
    node.name = name
    node.label = name
    node.location = location
    node.outputs[0].default_value = float(value)
    return node


def _surface_spec(layer):
    surface = layer.get("surface")
    if not isinstance(surface, dict) or not surface.get("enabled", True):
        return None
    return surface


def _blend_surface_channel(material, current_value, mask, layer, channel, index):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    token = _safe_token(layer["id"])
    suffix = SURFACE_CHANNELS[channel]["suffix"]
    x = 900 + index * 40
    y = -1880 - index * 310 - list(SURFACE_CHANNELS).index(channel) * 70

    inverse = _math_node(
        nodes,
        "SUBTRACT",
        layer_node_name(token, f"Surface{suffix}InverseMask"),
        (x, y),
    )
    inverse.inputs[0].default_value = 1.0
    previous_part = _math_node(
        nodes,
        "MULTIPLY",
        layer_node_name(token, f"Surface{suffix}Previous"),
        (x + 180, y),
    )
    layer_value = _value_node(
        nodes,
        layer_node_name(token, f"Surface{suffix}Value"),
        layer["surface"][channel],
        (x, y - 55),
    )
    layer_part = _math_node(
        nodes,
        "MULTIPLY",
        layer_node_name(token, f"Surface{suffix}Layer"),
        (x + 180, y - 90),
    )
    combined = _math_node(
        nodes,
        "ADD",
        layer_node_name(token, f"Surface{suffix}Mix"),
        (x + 370, y - 35),
    )
    combined.use_clamp = True

    links.new(mask, inverse.inputs[1])
    links.new(current_value, previous_part.inputs[0])
    links.new(inverse.outputs[0], previous_part.inputs[1])
    links.new(layer_value.outputs[0], layer_part.inputs[0])
    links.new(mask, layer_part.inputs[1])
    links.new(previous_part.outputs[0], combined.inputs[0])
    links.new(layer_part.outputs[0], combined.inputs[1])
    return combined.outputs[0]


def _build_image_layer(material, current_color, project, project_path, layer, index, reload_images):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    token = _safe_token(layer["id"])
    x = -900 + index * 40
    y = -480 - index * 420
    projector = ensure_projector(project["name"], layer)
    projection = layer["projection"]

    coordinate = nodes.new("ShaderNodeTexCoord")
    coordinate.name = layer_node_name(token, "Coordinates")
    coordinate.label = layer.get("name", layer["id"])
    coordinate.object = projector
    coordinate.location = (x, y)

    flip = nodes.new("ShaderNodeVectorMath")
    flip.operation = "MULTIPLY"
    flip.name = layer_node_name(token, "Flip")
    flip.location = (x + 190, y)
    flip.inputs[1].default_value = (
        -1.0 if projection.get("flip_x", False) else 1.0,
        -1.0 if projection.get("flip_y", False) else 1.0,
        1.0,
    )
    offset = nodes.new("ShaderNodeVectorMath")
    offset.operation = "ADD"
    offset.name = layer_node_name(token, "Offset")
    offset.location = (x + 380, y)
    offset.inputs[1].default_value = (0.5, 0.5, 0.0)

    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = layer_node_name(token, "Image")
    image_node.label = layer.get("name", layer["id"])
    image_node.location = (x + 570, y)
    image_node.extension = "CLIP"
    image_node.interpolation = "Linear"
    image_path = resolve_path(layer["image"], project_path)
    image_node.image = _load_image(
        image_path,
        layer.get("color_space", "sRGB"),
        reload_image=reload_images,
    )

    image_vector_output = offset.outputs["Vector"]
    image_region = layer.get("image_region")
    if image_region is not None:
        u0, v0, u1, v1 = (float(value) for value in image_region)
        region_scale = nodes.new("ShaderNodeVectorMath")
        region_scale.operation = "MULTIPLY"
        region_scale.name = layer_node_name(token, "RegionScale")
        region_scale.location = (x + 550, y + 110)
        region_scale.inputs[1].default_value = (u1 - u0, v1 - v0, 1.0)
        region_offset = nodes.new("ShaderNodeVectorMath")
        region_offset.operation = "ADD"
        region_offset.name = layer_node_name(token, "RegionOffset")
        region_offset.location = (x + 730, y + 110)
        region_offset.inputs[1].default_value = (u0, v0, 0.0)
        links.new(image_vector_output, region_scale.inputs[0])
        links.new(region_scale.outputs["Vector"], region_offset.inputs[0])
        image_vector_output = region_offset.outputs["Vector"]

    alpha_output = image_node.outputs["Alpha"]
    if str(layer.get("alpha_mode", "IMAGE")).upper() == "WHITE_KEY":
        white_distance = nodes.new("ShaderNodeVectorMath")
        white_distance.operation = "DISTANCE"
        white_distance.name = layer_node_name(token, "WhiteDistance")
        white_distance.location = (x + 760, y + 130)
        white_distance.inputs[1].default_value = (1.0, 1.0, 1.0)
        white_subtract = _math_node(
            nodes,
            "SUBTRACT",
            layer_node_name(token, "WhiteKeySubtract"),
            (x + 950, y + 130),
        )
        white_key_min = float(layer.get("white_key_min", 0.03))
        white_key_max = float(layer.get("white_key_max", 0.22))
        white_subtract.inputs[1].default_value = white_key_min
        white_scale = _math_node(
            nodes,
            "MULTIPLY",
            layer_node_name(token, "WhiteKeyScale"),
            (x + 1130, y + 130),
        )
        white_scale.inputs[1].default_value = 1.0 / (white_key_max - white_key_min)
        white_clamp = nodes.new("ShaderNodeClamp")
        white_clamp.name = layer_node_name(token, "WhiteKeyClamp")
        white_clamp.location = (x + 1310, y + 130)
        white_clamp.inputs["Min"].default_value = 0.0
        white_clamp.inputs["Max"].default_value = 1.0
        keyed_alpha = _math_node(
            nodes,
            "MULTIPLY",
            layer_node_name(token, "WhiteKeyAlpha"),
            (x + 1490, y + 130),
        )
        links.new(image_node.outputs["Color"], white_distance.inputs[0])
        links.new(white_distance.outputs["Value"], white_subtract.inputs[0])
        links.new(white_subtract.outputs[0], white_scale.inputs[0])
        links.new(white_scale.outputs[0], white_clamp.inputs["Value"])
        links.new(white_clamp.outputs["Result"], keyed_alpha.inputs[0])
        links.new(image_node.outputs["Alpha"], keyed_alpha.inputs[1])
        alpha_output = keyed_alpha.outputs[0]

    geometry = nodes.new("ShaderNodeNewGeometry")
    geometry.name = layer_node_name(token, "Geometry")
    geometry.location = (x + 190, y - 170)
    facing = nodes.new("ShaderNodeVectorMath")
    facing.operation = "DOT_PRODUCT"
    facing.name = layer_node_name(token, "FacingDot")
    facing.location = (x + 380, y - 170)
    _, _, z_axis = _projection_axes(projection)
    facing.inputs[1].default_value = (*z_axis,)
    facing_mask = _math_node(
        nodes,
        "GREATER_THAN",
        layer_node_name(token, "FacingMask"),
        (x + 570, y - 170),
    )
    facing_mask.inputs[1].default_value = float(projection.get("facing_threshold", 0.05))

    separate = nodes.new("ShaderNodeSeparateXYZ")
    separate.name = layer_node_name(token, "DepthXYZ")
    separate.location = (x + 190, y - 310)
    depth_absolute = _math_node(
        nodes,
        "ABSOLUTE",
        layer_node_name(token, "DepthAbsolute"),
        (x + 380, y - 310),
    )
    depth_mask = _math_node(
        nodes,
        "LESS_THAN",
        layer_node_name(token, "DepthMask"),
        (x + 570, y - 310),
    )
    depth_mask.inputs[1].default_value = 0.5

    opacity = _math_node(
        nodes,
        "MULTIPLY",
        layer_node_name(token, "Opacity"),
        (x + 770, y - 90),
    )
    opacity.inputs[1].default_value = float(layer.get("opacity", 1.0))
    alpha_facing = _math_node(
        nodes,
        "MULTIPLY",
        layer_node_name(token, "AlphaFacing"),
        (x + 950, y - 90),
    )
    alpha_depth = _math_node(
        nodes,
        "MULTIPLY",
        layer_node_name(token, "AlphaDepth"),
        (x + 1130, y - 90),
    )
    alpha_mask_output = alpha_depth.outputs[0]
    if projection.get("world_z_min") is not None or projection.get("world_z_max") is not None:
        position_xyz = nodes.new("ShaderNodeSeparateXYZ")
        position_xyz.name = layer_node_name(token, "WorldPositionXYZ")
        position_xyz.location = (x + 760, y - 430)
        links.new(geometry.outputs["Position"], position_xyz.inputs[0])
        if projection.get("world_z_min") is not None:
            world_z_min = _math_node(
                nodes,
                "GREATER_THAN",
                layer_node_name(token, "WorldZMin"),
                (x + 950, y - 430),
            )
            world_z_min.inputs[1].default_value = float(projection["world_z_min"])
            world_z_min_alpha = _math_node(
                nodes,
                "MULTIPLY",
                layer_node_name(token, "WorldZMinAlpha"),
                (x + 1320, y - 290),
            )
            links.new(position_xyz.outputs["Z"], world_z_min.inputs[0])
            links.new(alpha_mask_output, world_z_min_alpha.inputs[0])
            links.new(world_z_min.outputs[0], world_z_min_alpha.inputs[1])
            alpha_mask_output = world_z_min_alpha.outputs[0]
        if projection.get("world_z_max") is not None:
            world_z_max = _math_node(
                nodes,
                "LESS_THAN",
                layer_node_name(token, "WorldZMax"),
                (x + 1130, y - 430),
            )
            world_z_max.inputs[1].default_value = float(projection["world_z_max"])
            world_z_max_alpha = _math_node(
                nodes,
                "MULTIPLY",
                layer_node_name(token, "WorldZMaxAlpha"),
                (x + 1500, y - 290),
            )
            links.new(position_xyz.outputs["Z"], world_z_max.inputs[0])
            links.new(alpha_mask_output, world_z_max_alpha.inputs[0])
            links.new(world_z_max.outputs[0], world_z_max_alpha.inputs[1])
            alpha_mask_output = world_z_max_alpha.outputs[0]
    mix = nodes.new("ShaderNodeMixRGB")
    mix.name = layer_node_name(token, "Mix")
    mix.label = f"{index + 1:02d} · {layer.get('name', layer['id'])}"
    mix.location = (x + 1320, y)
    mix.blend_type = str(layer.get("blend_mode", "MIX")).upper()
    mix.use_clamp = True

    links.new(coordinate.outputs["Object"], flip.inputs[0])
    links.new(flip.outputs["Vector"], offset.inputs[0])
    links.new(image_vector_output, image_node.inputs["Vector"])
    links.new(geometry.outputs["Normal"], facing.inputs[0])
    links.new(facing.outputs["Value"], facing_mask.inputs[0])
    links.new(coordinate.outputs["Object"], separate.inputs[0])
    links.new(separate.outputs["Z"], depth_absolute.inputs[0])
    links.new(depth_absolute.outputs[0], depth_mask.inputs[0])
    links.new(alpha_output, opacity.inputs[0])
    links.new(opacity.outputs[0], alpha_facing.inputs[0])
    links.new(facing_mask.outputs[0], alpha_facing.inputs[1])
    links.new(alpha_facing.outputs[0], alpha_depth.inputs[0])
    links.new(depth_mask.outputs[0], alpha_depth.inputs[1])
    links.new(alpha_mask_output, mix.inputs[0])
    links.new(current_color, mix.inputs[1])
    links.new(image_node.outputs["Color"], mix.inputs[2])
    return mix.outputs["Color"], alpha_mask_output, projector, image_path


def _object_groups(objects, target_groups):
    mapping = {obj.name: [] for obj in objects}
    unmatched = []
    for group_name, patterns in target_groups.items():
        matches = [
            obj
            for obj in objects
            if any(fnmatch.fnmatchcase(obj.name, pattern) for pattern in patterns)
        ]
        if not matches:
            unmatched.append(group_name)
        for obj in matches:
            mapping[obj.name].append(group_name)
    return mapping, unmatched


def _assign_object_material(obj, material):
    already_assigned = len(obj.data.materials) == 1 and obj.data.materials[0] == material
    if already_assigned:
        return
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0


def _remove_stale_projectors(project_name, expected_names):
    prefix = f"ANIME_Projector_{_safe_token(project_name)}_"
    for obj in list(bpy.data.objects):
        if obj.name.startswith(prefix) and obj.name not in expected_names:
            bpy.data.objects.remove(obj, do_unlink=True)


def remove_projectors(project_name):
    _remove_stale_projectors(project_name, set())


def apply_project(
    project_path,
    target_groups_override=None,
    reload_images=False,
    project_data=None,
):
    project_path = Path(project_path).resolve()
    source_project = copy.deepcopy(project_data) if project_data is not None else load_project(project_path)
    validate_project(source_project, project_path)
    project = copy.deepcopy(source_project)
    if target_groups_override is not None:
        project["target_groups"] = copy.deepcopy(target_groups_override)

    objects = base.mesh_objects()
    if not objects:
        raise RuntimeError("scene contains no mesh objects")
    groups_by_object, unmatched_groups = _object_groups(objects, project["target_groups"])
    targets = [obj for obj in objects if groups_by_object[obj.name]]
    if not targets:
        raise RuntimeError("anime livery target_groups matched no mesh objects")

    expected_projectors = {
        projector_name(project["name"], layer["id"])
        for layer in project.get("layers", [])
        if layer.get("enabled", True) and layer.get("image")
    }
    _remove_stale_projectors(project["name"], expected_projectors)
    base_preset, base_preset_path = _base_preset(project, project_path)
    materials = []
    applied_layers = set()
    images = set()
    for obj in targets:
        object_preset = copy.deepcopy(base_preset)
        object_preset["material_name"] = (
            f"ANIME_{_safe_token(project['name'])}_{_safe_token(obj.name)}"
        )
        material = base.create_camo_material(object_preset)
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        bsdf = nodes["CAMO_Principled"]
        base_color = nodes["CAMO_ColorRamp"].outputs["Color"]
        for link in list(bsdf.inputs["Base Color"].links):
            links.remove(link)
        current_color = base_color
        current_surface = {}
        for channel, channel_spec in SURFACE_CHANNELS.items():
            socket = bsdf.inputs.get(channel_spec["socket"])
            if socket is None:
                continue
            for link in list(socket.links):
                links.remove(link)
            value = float(base_preset.get(channel, channel_spec["default"]))
            current_surface[channel] = _value_node(
                nodes,
                f"ANIME_Base_Surface_{channel_spec['suffix']}",
                value,
                (-20, -1180 - len(current_surface) * 90),
            ).outputs[0]
        for index, layer in enumerate(project.get("layers", [])):
            if not layer.get("enabled", True) or not layer.get("image"):
                continue
            if not any(group in groups_by_object[obj.name] for group in layer.get("targets", [])):
                continue
            current_color, layer_mask, _, image_path = _build_image_layer(
                material,
                current_color,
                project,
                project_path,
                layer,
                index,
                reload_images,
            )
            surface = _surface_spec(layer)
            if surface:
                for channel in current_surface:
                    if channel in surface:
                        current_surface[channel] = _blend_surface_channel(
                            material,
                            current_surface[channel],
                            layer_mask,
                            layer,
                            channel,
                            index,
                        )
            applied_layers.add(layer["id"])
            images.add(str(image_path))
        links.new(current_color, bsdf.inputs["Base Color"])
        for channel, value_output in current_surface.items():
            links.new(value_output, bsdf.inputs[SURFACE_CHANNELS[channel]["socket"]])
        _assign_object_material(obj, material)
        materials.append(material)

    bpy.context.view_layer.update()
    warnings = []
    if unmatched_groups:
        warnings.append(f"Unmatched target groups: {', '.join(unmatched_groups)}")
    if any(len(obj.data.materials) <= 1 for obj in targets):
        warnings.append(
            "Target meshes are not surface-separated; use projector position, depth, facing, and transparent masks to localize artwork."
        )
    return {
        "project_path": str(project_path),
        "project": project,
        "source_project": source_project,
        "target_groups": copy.deepcopy(project["target_groups"]),
        "targets": [obj.name for obj in targets],
        "materials": [material.name for material in materials],
        "layers": [layer["id"] for layer in project.get("layers", [])],
        "applied_layers": sorted(applied_layers),
        "images": sorted(images),
        "base_preset": str(base_preset_path) if base_preset_path else None,
        "warnings": warnings,
        "aspect_layers": aspect_audit(project, project_path),
        "dependencies": dependency_snapshot(project_path, source_project),
    }


def update_layer_controls(project, layer_index, enabled=None, opacity=None):
    layers = project.get("layers", [])
    if not layers:
        raise RuntimeError("project contains no layers")
    index = max(0, min(int(layer_index), len(layers) - 1))
    layer = layers[index]
    if enabled is not None:
        layer["enabled"] = bool(enabled)
    if opacity is not None:
        layer["opacity"] = max(0.0, min(1.0, float(opacity)))
    node_name = layer_node_name(layer["id"], "Opacity")
    value = float(layer.get("opacity", 1.0)) if layer.get("enabled", True) else 0.0
    updated = []
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        node = material.node_tree.nodes.get(node_name)
        if node is not None:
            node.inputs[1].default_value = value
            material.update_tag()
            updated.append(material.name)
    return layer, updated


def update_layer_surface_controls(
    project,
    layer_index,
    surface_enabled=None,
    roughness=None,
    metallic=None,
    coat_weight=None,
    coat_roughness=None,
):
    layers = project.get("layers", [])
    if not layers:
        raise RuntimeError("project contains no layers")
    index = max(0, min(int(layer_index), len(layers) - 1))
    layer = layers[index]
    surface = layer.get("surface")
    if not isinstance(surface, dict):
        surface = {
            channel: channel_spec["default"]
            for channel, channel_spec in SURFACE_CHANNELS.items()
        }
        layer["surface"] = surface
    if surface_enabled is not None:
        surface["enabled"] = bool(surface_enabled)

    incoming = {
        "roughness": roughness,
        "metallic": metallic,
        "coat_weight": coat_weight,
        "coat_roughness": coat_roughness,
    }
    for channel, value in incoming.items():
        if value is not None:
            surface[channel] = max(0.0, min(1.0, float(value)))

    updated = []
    token = _safe_token(layer["id"])
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        changed = False
        for channel, value in incoming.items():
            if value is None:
                continue
            suffix = SURFACE_CHANNELS[channel]["suffix"]
            node = material.node_tree.nodes.get(
                layer_node_name(token, f"Surface{suffix}Value")
            )
            if node is not None:
                node.outputs[0].default_value = surface[channel]
                changed = True
        if changed:
            material.update_tag()
            updated.append(material.name)
    return layer, updated


def run_anime_pipeline(model_path, project_path, output_dir):
    model_path = Path(model_path).resolve()
    project_path = Path(project_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_assets = base.inspect_source_assets(model_path)
    base.clear_scene()
    base.import_model(model_path)
    before = base.audit_scene()
    result = apply_project(project_path, reload_images=True)
    project = result["project"]
    targets = [bpy.data.objects[name] for name in result["targets"]]
    previews = base.render_previews(output_dir / "previews", project.get("render", {}), targets)
    blend_path = output_dir / f"{_safe_token(project['name'])}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    warnings = list(result["warnings"])
    if source_assets["missing_mtl"]:
        warnings.append("The OBJ references missing MTL files; original materials cannot be restored.")
    warnings.append(
        "The layered projector material is Blender-native. Bake validated UV textures before engine delivery."
    )
    report = {
        "source_model": str(model_path),
        "source_assets": source_assets,
        "project": str(project_path),
        "style_id": project.get("style_id"),
        "before": before,
        "after": base.audit_scene(targets),
        "targets": result["targets"],
        "materials": result["materials"],
        "layers": result["layers"],
        "applied_layers": result["applied_layers"],
        "surface_layers": {
            layer["id"]: layer["surface"]
            for layer in project.get("layers", [])
            if isinstance(layer.get("surface"), dict)
        },
        "aspect_layers": result["aspect_layers"],
        "images": result["images"],
        "warnings": warnings,
        "outputs": {"blend": str(blend_path), "previews": previews},
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
