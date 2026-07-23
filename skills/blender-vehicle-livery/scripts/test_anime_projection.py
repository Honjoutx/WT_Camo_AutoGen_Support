import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bpy

import anime_livery_core as anime_core
import anime_livery_panel as anime_panel
import blender_livery_core as base


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def create_test_decal(path):
    width, height = 64, 32
    image = bpy.data.images.new("ANIME_Test_Decal", width=width, height=height, alpha=True)
    pixels = []
    for y in range(height):
        for x in range(width):
            inside = 3 <= x < width - 3 and 3 <= y < height - 3
            stripe = ((x // 8) + (y // 8)) % 2 == 0
            if inside and stripe:
                pixels.extend((1.0, 0.02, 0.35, 1.0))
            elif inside:
                pixels.extend((0.0, 0.85, 1.0, 1.0))
            else:
                pixels.extend((0.0, 0.0, 0.0, 0.0))
    image.pixels = pixels
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    return path


def test_project(image_name):
    return {
        "version": 1,
        "name": "pantsyr-anime-projection-test",
        "base": {
            "color": "#202735",
            "roughness": 0.62,
            "micro_bump_strength": 0.02,
            "micro_bump_scale": 32.0,
        },
        "target_groups": {
            "body": ["pantsyr_sm_sv_body_c"],
            "turret": ["pantsyr_sm_sv_turret_c"],
        },
        "layers": [
            {
                "id": "body-right-test",
                "name": "车体右侧测试图层",
                "type": "image_projection",
                "enabled": True,
                "targets": ["body"],
                "image": image_name,
                "opacity": 0.75,
                "blend_mode": "MIX",
                "surface": {
                    "roughness": 0.36,
                    "metallic": 0.64,
                    "coat_weight": 0.42,
                    "coat_roughness": 0.18,
                },
                "projection": {
                    "center": [1.58, 0.2, 1.45],
                    "direction": [-1.0, 0.0, 0.0],
                    "up": [0.0, 0.0, 1.0],
                    "size": [5.0, 1.75],
                    "depth": 0.9,
                    "facing_threshold": 0.05,
                    "flip_x": False,
                    "flip_y": False,
                },
            }
        ],
        "render": {
            "resolution": 512,
            "views": [{"name": "right_side", "azimuth": 0.0, "elevation": 12.0}],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Test layered anime projection and panel reload")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(blender_args())

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    decal_path = create_test_decal(output_dir / "test-decal.png")
    project_path = output_dir / "anime-test-project.json"
    project_path.write_text(
        json.dumps(test_project(decal_path.name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    base.clear_scene()
    base.import_model(args.model)
    scene = bpy.context.scene
    settings = scene.anime_livery
    settings.auto_reload = False
    settings.project_path = str(project_path)
    if bpy.ops.anime_livery.load_project() != {"FINISHED"}:
        raise RuntimeError(settings.status)

    body = bpy.data.objects["pantsyr_sm_sv_body_c"]
    turret = bpy.data.objects["pantsyr_sm_sv_turret_c"]
    body_material = body.data.materials[0]
    turret_material = turret.data.materials[0]
    opacity_name = anime_core.layer_node_name("body-right-test", "Opacity")
    image_name = anime_core.layer_node_name("body-right-test", "Image")
    metallic_name = anime_core.layer_node_name(
        "body-right-test", "SurfaceMetallicValue"
    )
    roughness_name = anime_core.layer_node_name(
        "body-right-test", "SurfaceRoughnessValue"
    )
    if body_material.node_tree.nodes.get(image_name) is None:
        raise AssertionError("Body material is missing the image projection layer")
    if turret_material.node_tree.nodes.get(image_name) is not None:
        raise AssertionError("Body-only layer leaked into the turret material")
    if body_material.node_tree.nodes.get(metallic_name) is None:
        raise AssertionError("Body material is missing the per-layer surface graph")
    bsdf = body_material.node_tree.nodes["CAMO_Principled"]
    for socket_name in ("Roughness", "Metallic", "Coat Weight", "Coat Roughness"):
        if not bsdf.inputs[socket_name].is_linked:
            raise AssertionError(f"Surface channel is not driven: {socket_name}")

    settings.layer_opacity = 0.33
    opacity_node = body_material.node_tree.nodes[opacity_name]
    if abs(float(opacity_node.inputs[1].default_value) - 0.33) > 1e-6:
        raise AssertionError("Panel opacity did not update the live layer node")

    settings.layer_metallic = 0.88
    metallic_node = body_material.node_tree.nodes[metallic_name]
    if abs(float(metallic_node.outputs[0].default_value) - 0.88) > 1e-6:
        raise AssertionError("Panel metallic control did not update the live layer node")

    settings.layer_surface_enabled = False
    body_material = body.data.materials[0]
    if body_material.node_tree.nodes.get(metallic_name) is not None:
        raise AssertionError("Disabling a surface block did not rebuild the graph")
    settings.layer_surface_enabled = True
    body_material = body.data.materials[0]
    if body_material.node_tree.nodes.get(metallic_name) is None:
        raise AssertionError("Re-enabling a surface block did not rebuild the graph")

    external = anime_core.load_project(project_path)
    external["layers"][0]["opacity"] = 0.42
    external["layers"][0]["surface"]["roughness"] = 0.24
    project_path.write_text(
        json.dumps(external, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.dependency_snapshot = ""
    settings.auto_reload = True
    anime_panel._watch_projects()
    body_material = body.data.materials[0]
    opacity_node = body_material.node_tree.nodes[opacity_name]
    if abs(float(opacity_node.inputs[1].default_value) - 0.42) > 1e-6:
        raise AssertionError("Project JSON hot reload did not update layer opacity")
    roughness_node = body_material.node_tree.nodes[roughness_name]
    if abs(float(roughness_node.outputs[0].default_value) - 0.24) > 1e-6:
        raise AssertionError("Project JSON hot reload did not update layer roughness")

    external["target_groups"]["body"] = ["unsafe_target_change"]
    external["layers"][0]["opacity"] = 0.55
    project_path.write_text(
        json.dumps(external, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.dependency_snapshot = ""
    anime_panel._watch_projects()
    if "加载/重建" not in settings.status:
        raise AssertionError("Target-group change did not require explicit confirmation")
    body_material = body.data.materials[0]
    opacity_node = body_material.node_tree.nodes[opacity_name]
    if abs(float(opacity_node.inputs[1].default_value) - 0.55) > 1e-6:
        raise AssertionError("Visual fields did not reload while target groups were preserved")

    projector = bpy.data.objects[
        anime_core.projector_name("pantsyr-anime-projection-test", "body-right-test")
    ]
    projector.location.y += 0.25
    projector.scale.x = 4.4
    if bpy.ops.anime_livery.save_project() != {"FINISHED"}:
        raise RuntimeError(settings.status)
    saved = anime_core.load_project(project_path)
    saved_projection = saved["layers"][0]["projection"]
    if abs(float(saved_projection["center"][1]) - 0.45) > 1e-5:
        raise AssertionError("Projector location was not saved to JSON")
    if abs(float(saved_projection["size"][0]) - 4.4) > 1e-5:
        raise AssertionError("Projector scale was not saved to JSON")
    if saved["target_groups"]["body"] != ["pantsyr_sm_sv_body_c"]:
        raise AssertionError("Unconfirmed target groups were written as confirmed scope")

    previews = base.render_previews(
        output_dir / "previews",
        saved.get("render", {}),
        [body, turret],
    )
    report = {
        "panel_registered": hasattr(bpy.types.Scene, "anime_livery"),
        "body_material": body.data.materials[0].name,
        "turret_material": turret.data.materials[0].name,
        "body_layer_present": True,
        "turret_layer_absent": True,
        "live_opacity": 0.33,
        "live_metallic": 0.88,
        "surface_toggle": True,
        "hot_reload_opacity": 0.42,
        "hot_reload_roughness": 0.24,
        "scope_blocked_visual_opacity": 0.55,
        "projector_saved": True,
        "preview": previews[0],
        "status": settings.status,
    }
    report_path = output_dir / "anime-panel-test.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ANIME_PANEL_TEST=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
