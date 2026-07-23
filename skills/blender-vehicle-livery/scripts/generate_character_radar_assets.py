"""Generate guide-aligned radar color blocks and original character-motif decals.

The assets remain deterministic and intentionally use only simple vector-like
geometry. They do not copy an online icon, logo, signature, or character art.
"""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


PALETTE = {
    "shadow": "#20353C",
    "secondary": "#55766F",
    "highlight": "#D4D6D1",
    "accent": "#D8B43C",
}


def rgba(value, alpha=255):
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def load_guide(path):
    path = Path(path).resolve()
    return path, json.loads(path.read_text(encoding="utf-8"))


def transform(point, guide, scale):
    width = int(guide["canvas"]["width"])
    height = int(guide["canvas"]["height"])
    size_x, size_y = guide["projector"]["size"]
    u, v = point
    return (
        round((u / size_x + 0.5) * width * scale),
        round((0.5 - v / size_y) * height * scale),
    )


def line_width(world_width, guide, scale):
    width = int(guide["canvas"]["width"])
    size_x = float(guide["projector"]["size"][0])
    return max(1, round(world_width * width / size_x * scale))


def render_shapes(guide, shapes, supersample=3):
    width = int(guide["canvas"]["width"])
    height = int(guide["canvas"]["height"])
    scale = max(1, int(supersample))
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    for shape in shapes:
        color = rgba(PALETTE[shape["color"]], shape.get("alpha", 255))
        points = [transform(point, guide, scale) for point in shape["points"]]
        if shape["type"] == "polygon":
            draw.polygon(points, fill=color)
        elif shape["type"] == "line":
            draw.line(
                points,
                fill=color,
                width=line_width(shape["width"], guide, scale),
                joint="curve",
            )
        else:
            raise ValueError(f"unsupported shape type: {shape['type']}")
    return image.resize((width, height), Image.Resampling.LANCZOS)


def mirror(points):
    return [(-u, v) for u, v in points]


def poly(color, points):
    return {"type": "polygon", "color": color, "points": points}


def stroke(color, width, points, alpha=255):
    return {
        "type": "line",
        "color": color,
        "width": width,
        "points": points,
        "alpha": alpha,
    }


def roof_radar_geometry():
    left_highlight = [
        (-0.56, 0.64),
        (-0.22, 0.64),
        (-0.10, -0.28),
        (-0.44, -0.34),
    ]
    return {
        "shadow": [
            poly(
                "shadow",
                [
                    (-0.73, 0.88),
                    (0.71, 0.88),
                    (0.71, -0.41),
                    (0.61, -0.53),
                    (-0.63, -0.53),
                    (-0.73, -0.41),
                ],
            ),
            poly(
                "shadow",
                [
                    (-0.70, -0.54),
                    (0.68, -0.54),
                    (0.68, -0.74),
                    (0.58, -0.82),
                    (-0.60, -0.82),
                    (-0.70, -0.74),
                ],
            ),
        ],
        "secondary": [
            poly(
                "secondary",
                [
                    (-0.64, 0.75),
                    (0.62, 0.75),
                    (0.62, -0.31),
                    (0.53, -0.42),
                    (-0.55, -0.42),
                    (-0.64, -0.31),
                ],
            ),
            poly(
                "secondary",
                [
                    (-0.61, -0.59),
                    (0.59, -0.59),
                    (0.59, -0.70),
                    (0.52, -0.76),
                    (-0.54, -0.76),
                    (-0.61, -0.70),
                ],
            ),
        ],
        "highlight": [
            poly("highlight", left_highlight),
            poly("highlight", mirror(left_highlight)),
            poly(
                "highlight",
                [
                    (-0.075, 0.61),
                    (0.075, 0.61),
                    (0.12, -0.23),
                    (0.0, -0.34),
                    (-0.12, -0.23),
                ],
            ),
            poly(
                "highlight",
                [(-0.38, -0.62), (-0.10, -0.62), (-0.04, -0.72), (-0.31, -0.72)],
            ),
            poly(
                "highlight",
                [(0.08, -0.62), (0.36, -0.62), (0.29, -0.72), (0.02, -0.72)],
            ),
        ],
        "accent": [
            poly("accent", [(-0.66, 0.79), (-0.52, 0.79), (-0.52, 0.64), (-0.66, 0.64)]),
            poly("accent", [(0.50, 0.79), (0.64, 0.79), (0.64, 0.64), (0.50, 0.64)]),
            poly("accent", [(-0.56, -0.34), (-0.45, -0.34), (-0.39, -0.42), (-0.52, -0.42)]),
            poly("accent", [(0.43, -0.34), (0.54, -0.34), (0.50, -0.42), (0.37, -0.42)]),
            poly("accent", [(-0.57, -0.60), (-0.48, -0.60), (-0.44, -0.72), (-0.54, -0.72)]),
            poly("accent", [(0.46, -0.60), (0.55, -0.60), (0.52, -0.72), (0.42, -0.72)]),
        ],
    }


def forward_radar_geometry():
    # The front radar is taller than the rear plate targeted during the rejected
    # R1 pass.  These coordinates fill the measured face (roughly u +/-0.66,
    # v -0.59..0.62) while the four highlight wedges leave readable diagonal
    # corridors for the physical X brace.
    upper_wedge = [(-0.53, 0.45), (-0.15, 0.45), (-0.02, 0.09), (-0.34, 0.20)]
    lower_wedge = [(-0.53, -0.43), (-0.34, -0.18), (-0.02, -0.08), (-0.15, -0.43)]
    return {
        "shadow": [
            poly(
                "shadow",
                [
                    (-0.62, 0.55),
                    (0.60, 0.55),
                    (0.62, 0.48),
                    (0.62, -0.45),
                    (0.54, -0.54),
                    (-0.55, -0.54),
                    (-0.62, -0.45),
                ],
            )
        ],
        "secondary": [
            poly(
                "secondary",
                [
                    (-0.54, 0.46),
                    (0.52, 0.46),
                    (0.54, 0.40),
                    (0.54, -0.38),
                    (0.47, -0.46),
                    (-0.48, -0.46),
                    (-0.54, -0.38),
                ],
            )
        ],
        "highlight": [
            poly("highlight", upper_wedge),
            poly("highlight", mirror(upper_wedge)),
            poly("highlight", lower_wedge),
            poly("highlight", mirror(lower_wedge)),
        ],
        "accent": [
            poly("accent", [(-0.57, 0.48), (-0.45, 0.48), (-0.45, 0.35), (-0.57, 0.35)]),
            poly("accent", [(0.43, 0.48), (0.55, 0.48), (0.55, 0.35), (0.43, 0.35)]),
            poly("accent", [(-0.57, -0.34), (-0.45, -0.34), (-0.45, -0.47), (-0.57, -0.47)]),
            poly("accent", [(0.43, -0.34), (0.55, -0.34), (0.55, -0.47), (0.43, -0.47)]),
            poly("accent", [(-0.08, -0.40), (0.08, -0.40), (0.04, -0.49), (-0.04, -0.49)]),
        ],
    }


def roof_frog_scan_decal():
    return [
        stroke("accent", 0.022, [(-0.31, 0.30), (-0.39, 0.19), (-0.37, -0.04), (-0.23, -0.19), (0.0, -0.26), (0.23, -0.19), (0.37, -0.04), (0.39, 0.19), (0.31, 0.30)]),
        stroke("highlight", 0.018, [(-0.31, 0.30), (-0.22, 0.40), (-0.10, 0.39), (-0.02, 0.28)]),
        stroke("highlight", 0.018, [(0.31, 0.30), (0.22, 0.40), (0.10, 0.39), (0.02, 0.28)]),
        stroke("highlight", 0.016, [(-0.23, 0.22), (-0.18, 0.28), (-0.10, 0.27), (-0.06, 0.20), (-0.11, 0.13), (-0.19, 0.13), (-0.23, 0.22)]),
        stroke("highlight", 0.016, [(0.23, 0.22), (0.18, 0.28), (0.10, 0.27), (0.06, 0.20), (0.11, 0.13), (0.19, 0.13), (0.23, 0.22)]),
        stroke("accent", 0.016, [(-0.12, 0.01), (0.0, -0.09), (0.12, 0.01)]),
        stroke("highlight", 0.012, [(-0.48, 0.08), (-0.40, 0.08)]),
        stroke("highlight", 0.012, [(0.40, 0.08), (0.48, 0.08)]),
    ]


def forward_snake_circuit_decal():
    return [
        stroke("accent", 0.022, [(-0.34, 0.18), (-0.18, 0.31), (0.14, 0.30), (0.34, 0.15), (0.29, -0.09), (0.09, -0.22), (-0.16, -0.19), (-0.31, -0.04), (-0.20, 0.09), (0.07, 0.08), (0.16, -0.02)]),
        poly("accent", [(0.34, 0.15), (0.42, 0.19), (0.37, 0.08)]),
        stroke("highlight", 0.018, [(-0.15, 0.14), (-0.09, 0.21), (-0.02, 0.20), (0.02, 0.13), (-0.03, 0.06), (-0.10, 0.06), (-0.15, 0.14)]),
        stroke("highlight", 0.018, [(0.15, 0.14), (0.09, 0.21), (0.02, 0.20), (-0.02, 0.13), (0.03, 0.06), (0.10, 0.06), (0.15, 0.14)]),
        stroke("highlight", 0.015, [(-0.08, -0.04), (0.0, -0.12), (0.08, -0.04)]),
    ]


def save_surface(output_dir, prefix, guide_path, guide, geometry, supersample):
    plan_shapes = []
    for color in ("shadow", "secondary", "highlight", "accent"):
        shapes = geometry[color]
        plan_shapes.extend(shapes)
        render_shapes(guide, shapes, supersample).save(output_dir / f"{prefix}-{color}.png")
    plan = render_shapes(guide, plan_shapes, supersample)
    plan_path = output_dir / f"{prefix}-geometry-plan.png"
    plan.save(plan_path)

    guide_image = Image.open(guide["output"]).convert("RGBA")
    overlay_tint = plan.copy()
    overlay_tint.putalpha(overlay_tint.getchannel("A").point(lambda value: round(value * 0.72)))
    Image.alpha_composite(guide_image, overlay_tint).save(output_dir / f"{prefix}-guide-overlay.png")

    return {
        "guide": str(guide_path),
        "geometry_plan": str(plan_path),
        "color_assets": {
            color: str(output_dir / f"{prefix}-{color}.png")
            for color in ("shadow", "secondary", "highlight", "accent")
        },
        "canvas": [int(guide["canvas"]["width"]), int(guide["canvas"]["height"])],
        "projector": guide["projector"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roof-guide", required=True)
    parser.add_argument("--forward-guide", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--supersample", type=int, default=3)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    roof_path, roof_guide = load_guide(args.roof_guide)
    forward_path, forward_guide = load_guide(args.forward_guide)

    surfaces = {
        "roof_radar_front": save_surface(
            output_dir,
            "roof-radar-front",
            roof_path,
            roof_guide,
            roof_radar_geometry(),
            args.supersample,
        ),
        "turret_forward_radar": save_surface(
            output_dir,
            "turret-forward-radar",
            forward_path,
            forward_guide,
            forward_radar_geometry(),
            args.supersample,
        ),
    }

    roof_decal = output_dir / "roof-radar-frog-scan-decal.png"
    render_shapes(roof_guide, roof_frog_scan_decal(), args.supersample).save(roof_decal)
    forward_decal = output_dir / "turret-forward-radar-snake-circuit-decal.png"
    render_shapes(forward_guide, forward_snake_circuit_decal(), args.supersample).save(forward_decal)

    metadata = {
        "version": 1,
        "kind": "deterministic-character-motif-radar-assets",
        "palette": PALETTE,
        "surfaces": surfaces,
        "decals": {
            "roof_frog_scan": str(roof_decal),
            "forward_snake_circuit": str(forward_decal),
        },
        "motif": {
            "character": "Sanae Kochiya",
            "local_reference": "assets/anime-liveries/pantsyr-mint-industrial-panel-v8-turret-geometry/miyase-mahiro-cutout.png",
            "abstracted_elements": ["frog hair clip", "snake hair ornament"],
            "research_urls": [
                "https://touhou.fandom.com/wiki/Sanae_Kochiya",
                "https://danmaku.jp/archive/character/c021/",
            ],
            "asset_provenance": "original deterministic geometry; no online bitmap, logo, signature, or text copied",
        },
    }
    metadata_path = output_dir / "radar-v9-assets.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
