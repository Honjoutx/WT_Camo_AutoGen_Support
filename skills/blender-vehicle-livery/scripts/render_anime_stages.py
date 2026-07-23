import argparse
import copy
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bpy

import anime_livery_core as anime
import blender_livery_core as base


def blender_args():
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def safe_token(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-") or "layer"


def main():
    parser = argparse.ArgumentParser(description="Render progressive anime livery layer stages")
    parser.add_argument("--model", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(blender_args())

    model_path = Path(args.model).resolve()
    project_path = Path(args.project).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    project = anime.load_project(project_path)
    layers = project.get("layers", [])
    views = project.get("render", {}).get("views", [])
    stage_view = views[0] if views else {"name": "right_side", "azimuth": 0.0, "elevation": 10.0}
    render_config = {
        "resolution": int(project.get("render", {}).get("resolution", 768)),
        "views": [stage_view],
    }

    base.clear_scene()
    base.import_model(model_path)
    stage_outputs = []
    for layer_count in range(len(layers) + 1):
        stage_project = copy.deepcopy(project)
        for index, layer in enumerate(stage_project["layers"]):
            layer["enabled"] = bool(project["layers"][index].get("enabled", True)) and index < layer_count
        if layer_count == 0:
            stage_name = "00-base-color"
        else:
            stage_name = f"{layer_count:02d}-{safe_token(layers[layer_count - 1]['id'])}"
        result = anime.apply_project(
            project_path,
            reload_images=True,
            project_data=stage_project,
        )
        targets = [bpy.data.objects[name] for name in result["targets"]]
        preview = base.render_previews(output_dir / stage_name, render_config, targets)[0]
        stage_outputs.append(
            {
                "stage": stage_name,
                "enabled_layers": [
                    layer["id"] for layer in stage_project["layers"] if layer.get("enabled", True)
                ],
                "preview": preview,
            }
        )

    report = {
        "model": str(model_path),
        "project": str(project_path),
        "view": stage_view,
        "stages": stage_outputs,
    }
    report_path = output_dir / "stage-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ANIME_STAGE_PREVIEWS=" + json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
