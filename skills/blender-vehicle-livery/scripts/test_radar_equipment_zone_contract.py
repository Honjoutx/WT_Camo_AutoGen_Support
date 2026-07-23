import argparse
import copy
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import anime_livery_core as anime_core


def assert_rejected(project, project_path, expected_fragment):
    try:
        anime_core.validate_project(project, project_path)
    except ValueError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(
                f"Expected rejection containing {expected_fragment!r}, got {exc!r}"
            ) from exc
    else:
        raise AssertionError(f"Project should have been rejected: {expected_fragment}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    project_path = Path(args.project).resolve()
    project = json.loads(project_path.read_text(encoding="utf-8"))
    anime_core.validate_project(project, project_path)

    missing_zone = copy.deepcopy(project)
    layer = next(
        item for item in missing_zone["layers"] if item["id"] == "radar-front-shadow"
    )
    del layer["source"]["equipment_zone"]
    assert_rejected(missing_zone, project_path, "source.equipment_zone")

    clipped_depth = copy.deepcopy(project)
    for layer in clipped_depth["layers"]:
        if layer.get("source", {}).get("equipment_zone") == "roof_antenna_front":
            layer["projection"]["depth"] = 1.0
    guide = next(
        item
        for item in clipped_depth["structure_guides"]
        if item["id"] == "roof-radar-front-v9"
    )
    guide["projection"]["depth"] = 1.0
    assert_rejected(clipped_depth, project_path, "required_depth_range")

    missing_required_zone = copy.deepcopy(project)
    missing_required_zone["layers"] = [
        layer
        for layer in missing_required_zone["layers"]
        if layer.get("source", {}).get("equipment_zone") != "turret_forward_radar"
    ]
    missing_required_zone["structure_guides"] = [
        guide
        for guide in missing_required_zone["structure_guides"]
        if guide["id"] != "turret-forward-radar-v9"
    ]
    missing_required_zone["macro_composition"]["large_planes"] = [
        plane
        for plane in missing_required_zone["macro_composition"]["large_planes"]
        if plane["id"] != "turret-forward-radar-face"
    ]
    missing_required_zone["macro_composition"]["color_blocks"] = [
        block
        for block in missing_required_zone["macro_composition"]["color_blocks"]
        if not block["id"].startswith("turret-forward-radar-")
    ]
    missing_required_zone["macro_composition"]["decals"]["layer_ids"] = [
        layer_id
        for layer_id in missing_required_zone["macro_composition"]["decals"]["layer_ids"]
        if layer_id != "turret-forward-radar-character-decal"
    ]
    assert_rejected(missing_required_zone, project_path, "equipment zones; missing")

    print("RADAR_EQUIPMENT_ZONE_CONTRACT_TEST=PASS")


if __name__ == "__main__":
    main()
