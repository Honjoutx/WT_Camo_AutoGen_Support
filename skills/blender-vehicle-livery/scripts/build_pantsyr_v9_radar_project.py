"""Build the corrected Pantsyr V9 R2 complete-radar project from V8."""

import argparse
import copy
import json
from pathlib import Path


ASSET_ROOT = "../../assets/anime-liveries/pantsyr-mint-industrial-panel-v9-radar-complete-r2"
GEOMETRY_PLAN_ID = "pantsyr-turret-radar-v9-r2"


SURFACE_VALUES = {
    "shadow": {
        "roughness": 0.30,
        "metallic": 0.34,
        "coat_weight": 0.42,
        "coat_roughness": 0.15,
    },
    "secondary": {
        "roughness": 0.40,
        "metallic": 0.16,
        "coat_weight": 0.30,
        "coat_roughness": 0.20,
    },
    "highlight": {
        "roughness": 0.24,
        "metallic": 0.52,
        "coat_weight": 0.50,
        "coat_roughness": 0.11,
    },
    "accent": {
        "roughness": 0.16,
        "metallic": 0.80,
        "coat_weight": 0.60,
        "coat_roughness": 0.08,
    },
}


def roof_projection():
    return {
        "center": [0.0, 1.0, 4.15],
        "direction": [0.0, 1.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "size": [1.9, 2.2],
        "depth": 1.65,
        "facing_threshold": 0.12,
        "flip_x": False,
        "flip_y": False,
        "world_z_min": 3.05,
        "world_z_max": 5.18,
    }


def forward_projection():
    return {
        "center": [0.0, -2.75, 2.55],
        "direction": [0.0, 1.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "size": [1.5, 1.3],
        "depth": 0.85,
        "facing_threshold": 0.60,
        "flip_x": False,
        "flip_y": False,
        "world_z_min": 1.90,
        "world_z_max": 3.20,
    }


def new_guide(guide_id, side, image, metadata, projection):
    return {
        "id": guide_id,
        "side": side,
        "targets": ["turret"],
        "image": f"{ASSET_ROOT}/{image}",
        "metadata": f"{ASSET_ROOT}/{metadata}",
        "designed_layers": [],
        "projection": projection,
    }


def underlay(color):
    layer_id = f"turret-forward-radar-{color}"
    return {
        "id": layer_id,
        "name": f"V9 turret forward radar {color}",
        "type": "image_projection",
        "enabled": True,
        "side": "front",
        "semantic_role": "underlay",
        "aspect_policy": "LIMIT",
        "max_aspect_distortion": 0.08,
        "targets": ["turret"],
        "image": f"{ASSET_ROOT}/turret-forward-radar-{color}.png",
        "source": {
            "kind": "generated-original-vector",
            "guide_id": "turret-forward-radar-v9",
            "geometry_plan_id": GEOMETRY_PLAN_ID,
            "color_block_id": f"turret-forward-radar-{color}-block",
            "single_color_asset": True,
            "equipment_role": "radar",
            "equipment_zone": "turret_forward_radar",
            "bilateral_symmetric": True,
            "prompt": "guide-aligned complete forward square radar color block, angular symmetric industrial geometry, no text, no logo, no character",
        },
        "opacity": 1.0,
        "blend_mode": "MIX",
        "alpha_mode": "IMAGE",
        "surface": copy.deepcopy(SURFACE_VALUES[color]),
        "projection": forward_projection(),
    }


def forward_decal():
    return {
        "id": "turret-forward-radar-character-decal",
        "name": "V9 forward radar frog and snake circuit emblem",
        "type": "image_projection",
        "enabled": True,
        "side": "front",
        "semantic_role": "decal",
        "aspect_policy": "LIMIT",
        "max_aspect_distortion": 0.08,
        "targets": ["turret"],
        "image": f"{ASSET_ROOT}/turret-forward-radar-snake-circuit-decal.png",
        "source": {
            "kind": "generated-original-vector",
            "guide_id": "turret-forward-radar-v9",
            "equipment_role": "radar",
            "equipment_zone": "turret_forward_radar",
            "bilateral_symmetric": True,
            "decal_family": "character-sensor-glyph",
            "decal_surface_id": "turret-forward-radar-face",
            "prompt": "original angular serpent-loop sensor circuit surrounding a small frog-eye pair, abstracted from the provided Sanae artwork, no copied logo, no text, transparent background",
            "provenance": {
                "kind": "generated",
                "prompt": "original deterministic frog-and-snake sensor glyph; no online bitmap copied",
                "local_reference": "../../assets/anime-liveries/pantsyr-mint-industrial-panel-v8-turret-geometry/miyase-mahiro-cutout.png",
                "research_urls": [
                    "https://touhou.fandom.com/wiki/Sanae_Kochiya",
                    "https://danmaku.jp/archive/character/c021/",
                ],
            },
        },
        "opacity": 0.92,
        "blend_mode": "MIX",
        "alpha_mode": "IMAGE",
        "surface": {
            "roughness": 0.28,
            "metallic": 0.34,
            "coat_weight": 0.40,
            "coat_roughness": 0.14,
        },
        "projection": forward_projection(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    base_path = Path(args.base_project).resolve()
    output_path = Path(args.output).resolve()
    project = json.loads(base_path.read_text(encoding="utf-8"))
    project["name"] = "pantsyr-mint-industrial-panel-v9-radar-complete-r2"

    guides = [
        guide
        for guide in project.get("structure_guides", [])
        if guide.get("id") != "radar-front-v8"
    ]
    roof_guide = new_guide(
        "roof-radar-front-v9",
        "front",
        "roof-radar-front-guide-v9-r2.png",
        "roof-radar-front-guide-v9-r2.json",
        roof_projection(),
    )
    forward_guide = new_guide(
        "turret-forward-radar-v9",
        "front",
        "turret-forward-radar-guide-v9-r2.png",
        "turret-forward-radar-guide-v9-r2.json",
        forward_projection(),
    )
    guides.extend([roof_guide, forward_guide])
    project["structure_guides"] = guides

    layers = project["layers"]
    for layer in layers:
        layer_id = layer["id"]
        source = layer.setdefault("source", {})
        if layer_id.startswith("radar-front-"):
            source["guide_id"] = "roof-radar-front-v9"
            source["equipment_role"] = "radar"
            source["equipment_zone"] = "roof_antenna_front"
            layer["projection"] = roof_projection()
            if layer_id == "radar-front-scan-decal":
                layer["image"] = f"{ASSET_ROOT}/roof-radar-frog-scan-decal.png"
                source["kind"] = "generated-original-vector"
                source["decal_family"] = "character-sensor-glyph"
                source["decal_surface_id"] = "roof-radar-front-face"
                source["prompt"] = "original angular frog-head scan emblem abstracted from the provided Sanae artwork, no copied logo, no text, transparent background"
                source["provenance"] = {
                    "kind": "generated",
                    "prompt": "original deterministic frog scan glyph; no online bitmap copied",
                    "local_reference": "../../assets/anime-liveries/pantsyr-mint-industrial-panel-v8-turret-geometry/miyase-mahiro-cutout.png",
                    "research_urls": [
                        "https://touhou.fandom.com/wiki/Sanae_Kochiya",
                        "https://danmaku.jp/archive/character/c021/",
                    ],
                }
            else:
                color = layer_id.removeprefix("radar-front-")
                layer["image"] = f"{ASSET_ROOT}/roof-radar-front-{color}.png"
                source["geometry_plan_id"] = GEOMETRY_PLAN_ID
        elif layer_id.startswith("radar-rear-"):
            source["equipment_zone"] = "roof_antenna_rear"
        elif layer_id.startswith("radar-top-"):
            source["equipment_zone"] = "roof_antenna_top"

    insertion_index = next(
        index
        for index, layer in enumerate(layers)
        if layer["id"] == "left-turret-side-service-decal"
    )
    forward_layers = [underlay(color) for color in ("shadow", "secondary", "highlight", "accent")]
    layers[insertion_index:insertion_index] = forward_layers
    decal_index = next(
        index
        for index, layer in enumerate(layers)
        if layer["id"] == "radar-front-scan-decal"
    )
    layers.insert(decal_index + 1, forward_decal())

    roof_guide["designed_layers"] = [
        "radar-front-shadow",
        "radar-front-secondary",
        "radar-front-highlight",
        "radar-front-accent",
        "radar-front-scan-decal",
    ]
    forward_guide["designed_layers"] = [
        *(layer["id"] for layer in forward_layers),
        "turret-forward-radar-character-decal",
    ]

    macro = project["macro_composition"]
    macro["geometry_plan_id"] = GEOMETRY_PLAN_ID
    for plane in macro["large_planes"]:
        if plane["id"] == "radar-front-face":
            plane["id"] = "roof-radar-front-face"
            plane["guide_id"] = "roof-radar-front-v9"
            plane["geometry_plan_asset"] = f"{ASSET_ROOT}/roof-radar-front-geometry-plan.png"
            plane["coverage_basis"] = "visible roof-antenna main screen and lower forward subpanel, excluding the top lip, side pods, outer seams, and support hardware"
            plane["target_coverage_min"] = 0.78
            plane["target_coverage_max"] = 0.94
            plane["intentional_negative_space"] = [
                "top antenna lip",
                "side cooling pods and outer seams",
                "main-screen to lower-subpanel physical seam",
                "bottom support and mounting hardware",
            ]
            plane["verification_views"] = ["radar_front_check", "front"]
    macro["large_planes"].append(
        {
            "id": "turret-forward-radar-face",
            "guide_id": "turret-forward-radar-v9",
            "geometry_plan_asset": f"{ASSET_ROOT}/turret-forward-radar-geometry-plan.png",
            "coverage_basis": "visible forward square radar panel inside its perimeter frame, excluding the physical X brace and outer corner seams",
            "coverage_layers": [layer["id"] for layer in forward_layers],
            "target_coverage_min": 0.72,
            "target_coverage_max": 0.90,
            "intentional_negative_space": [
                "physical X-brace corridors",
                "outer frame and corner seams",
                "central sensor-icon breathing room",
            ],
            "verification_views": ["turret_forward_radar_check", "front"],
        }
    )

    block_by_id = {block["id"]: block for block in macro["color_blocks"]}
    for color in ("shadow", "secondary", "highlight", "accent"):
        block = block_by_id[f"radar-front-{color}-block"]
        block["asset"] = f"{ASSET_ROOT}/roof-radar-front-{color}.png"
        macro["color_blocks"].append(
            {
                "id": f"turret-forward-radar-{color}-block",
                "color": {
                    "shadow": "#20353C",
                    "secondary": "#55766F",
                    "highlight": "#D4D6D1",
                    "accent": "#D8B43C",
                }[color],
                "asset": f"{ASSET_ROOT}/turret-forward-radar-{color}.png",
                "layer_ids": [f"turret-forward-radar-{color}"],
            }
        )

    coverage_ids = {
        layer_id
        for plane in macro["large_planes"]
        for layer_id in plane["coverage_layers"]
    }
    for layer in layers:
        if layer["id"] in coverage_ids:
            layer.setdefault("source", {})["geometry_plan_id"] = GEOMETRY_PLAN_ID

    decals = macro["decals"]
    decals["layer_ids"].append("turret-forward-radar-character-decal")
    decals["style_families"] = [
        "angular-industrial-outline",
        "character-sensor-glyph",
    ]

    project["radar_isolation"] = {
        "target_group": "turret",
        "minimum_world_z": 1.90,
        "required_sides": ["front", "rear", "top"],
        "required_equipment_zones": [
            "roof_antenna_front",
            "roof_antenna_rear",
            "roof_antenna_top",
            "turret_forward_radar",
        ],
        "equipment_zones": {
            "roof_antenna_front": {
                "minimum_world_z": 3.05,
                "required_depth_range": [-0.79, 0.13],
            },
            "roof_antenna_rear": {"minimum_world_z": 3.20},
            "roof_antenna_top": {"minimum_world_z": 4.70},
            "turret_forward_radar": {
                "minimum_world_z": 1.90,
                "required_depth_range": [-0.381, 0.332],
            },
        },
        "verification_views": [
            "radar_front_check",
            "radar_rear_check",
            "radar_top_check",
            "turret_forward_radar_check",
        ],
        "rule": "Treat the roof antenna front/rear/top and the lower forward square radar as separate equipment zones. Every zone uses its own guide, coverage plan, projector volume, and verification view; projector half-depth must cover the declared model-derived depth range.",
    }

    if not any(
        view.get("name") == "turret_forward_radar_check"
        for view in project["render"]["views"]
    ):
        project["render"]["views"].append(
            {
                "name": "turret_forward_radar_check",
                "azimuth": -90.0,
                "elevation": 14.0,
            }
        )

    project["iteration_record"] = {
        "id": "v9-radar-complete-r2",
        "finding": "The roof-radar front was clipped by the V8 depth volume. The first V9 attempt fixed that volume but targeted a rear plate near Y=-1.07 instead of the visible X-braced forward radar near Y=-2.75.",
        "change": "Kept the complete roof-radar volume, re-guided the actual X-braced forward panel, expanded its geometry to the measured face, and added sparse original frog-scan and snake-circuit decals derived from the provided character motifs.",
        "validation": "Accepted in R2: all 49 layers and aspect audits passed, all 17 views rendered, the roof main screen and lower subpanel are complete, and the corrected Y=-2.75 projector visibly lands on the X-braced forward radar without material side spill.",
        "skill_updates": [
            "SKILL.md",
            "references/anime-project-schema.md",
            "references/style-library.md",
            "references/iteration-log.md",
            "scripts/anime_livery_core.py",
            "scripts/generate_character_radar_assets.py",
            "assets/styles/mint-industrial-panel-anime-v7-turret-radar.json",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output_path)


if __name__ == "__main__":
    main()
