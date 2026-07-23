import copy
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import anime_livery_core as anime_core


def projection():
    return {
        "center": [1.0, 0.0, 1.0],
        "direction": [-1.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "size": [4.0, 2.0],
        "depth": 0.5,
    }


def valid_project():
    return {
        "version": 1,
        "name": "macro-composition-contract-test",
        "target_groups": {"body": ["test_body"]},
        "design_rules": {"macro_geometry_asset_contract": True},
        "layers": [
            {
                "id": "body-graphite",
                "type": "image_projection",
                "enabled": True,
                "side": "left",
                "semantic_role": "underlay",
                "targets": ["body"],
                "image": "body-graphite.png",
                "source": {
                    "geometry_plan_id": "body-side-v1",
                    "color_block_id": "body-graphite-block",
                    "single_color_asset": True,
                },
                "projection": projection(),
            },
            {
                "id": "body-mint",
                "type": "image_projection",
                "enabled": True,
                "side": "left",
                "semantic_role": "underlay",
                "targets": ["body"],
                "image": "body-mint.png",
                "source": {
                    "geometry_plan_id": "body-side-v1",
                    "color_block_id": "body-mint-block",
                    "single_color_asset": True,
                },
                "projection": projection(),
            },
            {
                "id": "body-sensor-icon",
                "type": "image_projection",
                "enabled": True,
                "side": "left",
                "semantic_role": "decal",
                "targets": ["body"],
                "image": "body-sensor-icon.png",
                "source": {
                    "decal_family": "angular-industrial-outline",
                    "decal_surface_id": "left-body-main-plane",
                    "provenance": {
                        "kind": "online",
                        "url": "https://official-source.example/icon",
                        "license": "verified-test-license",
                        "retrieved_at": "2026-07-23",
                    },
                },
                "projection": projection(),
            },
        ],
        "macro_composition": {
            "geometry_plan_id": "body-side-v1",
            "large_planes": [
                {
                    "id": "left-body-main-plane",
                    "guide_id": "left-body-guide-v1",
                    "geometry_plan_asset": "left-body-plan.png",
                    "coverage_basis": "visible paintable guide patches excluding documented negative space",
                    "coverage_layers": ["body-graphite", "body-mint"],
                    "target_coverage_min": 0.62,
                    "target_coverage_max": 0.88,
                    "intentional_negative_space": [
                        "hero face safe zone",
                        "panel seams and hardware",
                    ],
                    "verification_views": ["left_side", "left_front"],
                }
            ],
            "color_blocks": [
                {
                    "id": "body-graphite-block",
                    "color": "#20353C",
                    "asset": "body-graphite.png",
                    "layer_ids": ["body-graphite"],
                },
                {
                    "id": "body-mint-block",
                    "color": "#7FA79C",
                    "asset": "body-mint.png",
                    "layer_ids": ["body-mint"],
                },
            ],
            "decals": {
                "layer_ids": ["body-sensor-icon"],
                "max_total": 1,
                "max_per_surface": 1,
                "style_families": ["angular-industrial-outline"],
                "provenance_required": True,
            },
        },
        "render": {
            "views": [
                {"name": "left_side"},
                {"name": "left_front"},
            ]
        },
    }


def assert_rejected(project, expected_fragment):
    try:
        anime_core.validate_project(project)
    except ValueError as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(
                f"Expected rejection containing {expected_fragment!r}, got {exc!r}"
            ) from exc
    else:
        raise AssertionError(f"Project should have been rejected: {expected_fragment}")


def main():
    project = valid_project()
    anime_core.validate_project(project)

    low_coverage = copy.deepcopy(project)
    low_coverage["macro_composition"]["large_planes"][0][
        "target_coverage_min"
    ] = 0.4
    assert_rejected(low_coverage, "0.55 <= min < max <= 0.95")

    missing_basis = copy.deepcopy(project)
    del missing_basis["macro_composition"]["large_planes"][0]["coverage_basis"]
    assert_rejected(missing_basis, "requires coverage_basis")

    combined_asset = copy.deepcopy(project)
    combined_asset["macro_composition"]["color_blocks"][1][
        "asset"
    ] = "body-graphite.png"
    assert_rejected(combined_asset, "own unique asset")

    unmarked_asset = copy.deepcopy(project)
    unmarked_asset["layers"][0]["source"]["single_color_asset"] = False
    assert_rejected(unmarked_asset, "single_color_asset=true")

    crowded = copy.deepcopy(project)
    crowded["macro_composition"]["decals"]["max_total"] = 0
    assert_rejected(crowded, "exceeds max_total")

    missing_license = copy.deepcopy(project)
    del missing_license["layers"][2]["source"]["provenance"]["license"]
    assert_rejected(missing_license, "provenance requires license")

    print("MACRO_COMPOSITION_CONTRACT_TEST=PASS")


if __name__ == "__main__":
    main()
