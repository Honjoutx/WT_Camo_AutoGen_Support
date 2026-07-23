import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bpy

import blender_livery_core as core
import livery_panel


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def main():
    parser = argparse.ArgumentParser(description="Test the Blender livery live panel")
    parser.add_argument("--model", required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(blender_args())

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    test_preset_path = output_dir / "hot-reload-preset.json"
    preset = core.load_json(args.preset)
    test_preset_path.write_text(
        json.dumps(preset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    core.clear_scene()
    core.import_model(args.model)
    settings = bpy.context.scene.camo_livery
    settings.auto_reload = False
    settings.preset_path = str(test_preset_path)
    if bpy.ops.camo_livery.load_preset() != {"FINISHED"}:
        raise RuntimeError(settings.status)

    material = bpy.data.materials[preset["material_name"]]
    noise = material.node_tree.nodes["CAMO_MainNoise"]
    loaded_scale = float(noise.inputs["Scale"].default_value)
    settings.pattern_scale = loaded_scale + 0.25
    live_scale = float(noise.inputs["Scale"].default_value)
    if abs(live_scale - settings.pattern_scale) > 1e-6:
        raise AssertionError("Live panel update did not reach the material node")

    settings.material_name = "UNCONFIRMED_LIVE_MATERIAL"
    settings.target_objects = "unconfirmed_live_target"
    settings.pattern_scale = loaded_scale + 0.35
    if abs(float(noise.inputs["Scale"].default_value) - settings.pattern_scale) > 1e-6:
        raise AssertionError("Live preview did not update the confirmed material")
    if bpy.data.materials.get("UNCONFIRMED_LIVE_MATERIAL") is not None:
        raise AssertionError("Live preview created a material from unconfirmed scope text")
    live_scope_blocked = True
    settings.material_name = preset["material_name"]
    settings.target_objects = ", ".join(preset["target_objects"])

    external_preset = core.load_json(test_preset_path)
    external_preset["pattern_scale"] = loaded_scale + 0.75
    test_preset_path.write_text(
        json.dumps(external_preset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.last_mtime = 0.0
    settings.auto_reload = True
    livery_panel._watch_presets()
    hot_scale = float(noise.inputs["Scale"].default_value)
    if abs(hot_scale - external_preset["pattern_scale"]) > 1e-6:
        raise AssertionError("JSON hot reload did not update the material node")

    pending_panel_preset = dict(external_preset)
    pending_panel_preset["material_name"] = "UNCONFIRMED_PANEL_MATERIAL"
    pending_panel_preset["target_objects"] = ["unconfirmed_panel_target"]
    pending_panel_preset["pattern_scale"] = loaded_scale + 0.85
    settings.material_name = pending_panel_preset["material_name"]
    settings.target_objects = pending_panel_preset["target_objects"][0]
    test_preset_path.write_text(
        json.dumps(pending_panel_preset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.last_mtime = 0.0
    livery_panel._watch_presets()
    if settings.material_name != preset["material_name"]:
        raise AssertionError("Unapplied panel material text was treated as confirmed scope")
    if settings.target_objects != "pantsyr_sm_sv_body_c, pantsyr_sm_sv_turret_c":
        raise AssertionError("Unapplied panel target text was treated as confirmed scope")
    if abs(float(noise.inputs["Scale"].default_value) - pending_panel_preset["pattern_scale"]) > 1e-6:
        raise AssertionError("Visual fields did not reload while unapplied panel scope was blocked")
    panel_scope_reload_blocked = True

    blocked_preset = dict(external_preset)
    blocked_preset["target_objects"] = ["unsafe_target_change"]
    blocked_preset["pattern_scale"] = loaded_scale + 0.95
    test_preset_path.write_text(
        json.dumps(blocked_preset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.last_mtime = 0.0
    livery_panel._watch_presets()
    if "加载并应用" not in settings.status or "已热重载视觉参数" not in settings.status:
        raise AssertionError("Target changes were not blocked for explicit confirmation")
    if settings.target_objects != "pantsyr_sm_sv_body_c, pantsyr_sm_sv_turret_c":
        raise AssertionError("Hot reload silently changed target objects")
    if abs(float(noise.inputs["Scale"].default_value) - blocked_preset["pattern_scale"]) > 1e-6:
        raise AssertionError("Visual fields did not hot-reload alongside a blocked target change")
    target_reload_blocked = True

    alternate_preset_path = output_dir / "alternate-scope-preset.json"
    alternate_preset = dict(blocked_preset)
    alternate_preset["material_name"] = "UNCONFIRMED_MATERIAL"
    alternate_preset["pattern_scale"] = loaded_scale + 1.05
    alternate_preset_path.write_text(
        json.dumps(alternate_preset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings.preset_path = str(alternate_preset_path)
    livery_panel._watch_presets()
    if settings.material_name != preset["material_name"]:
        raise AssertionError("Changing preset path silently changed the material scope")
    if settings.target_objects != "pantsyr_sm_sv_body_c, pantsyr_sm_sv_turret_c":
        raise AssertionError("Changing preset path silently changed target objects")
    if abs(float(noise.inputs["Scale"].default_value) - alternate_preset["pattern_scale"]) > 1e-6:
        raise AssertionError("Visual fields did not hot-reload after changing preset path")
    path_scope_reload_blocked = True

    settings.pattern_scale = loaded_scale + 1.0
    if bpy.ops.camo_livery.save_preset() != {"FINISHED"}:
        raise RuntimeError(settings.status)
    saved = core.load_json(alternate_preset_path)
    if abs(float(saved["pattern_scale"]) - settings.pattern_scale) > 1e-6:
        raise AssertionError("Panel save did not persist the current controls")

    report = {
        "panel_registered": hasattr(bpy.types.Scene, "camo_livery"),
        "targets": [obj.name for obj in core.mesh_objects() if obj.name.startswith("pantsyr")],
        "loaded_scale": loaded_scale,
        "live_scale": live_scale,
        "live_scope_blocked": live_scope_blocked,
        "hot_reload_scale": hot_scale,
        "panel_scope_reload_blocked": panel_scope_reload_blocked,
        "target_reload_blocked": target_reload_blocked,
        "path_scope_reload_blocked": path_scope_reload_blocked,
        "saved_scale": saved["pattern_scale"],
        "status": settings.status,
    }
    report_path = output_dir / "panel-test.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CAMO_PANEL_TEST=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
