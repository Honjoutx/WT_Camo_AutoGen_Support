"""Render anti-aliased vector-like livery shapes on a structure-guide canvas."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def _hex_rgba(value, opacity=1.0):
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"invalid #RRGGBB color: {value}")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4)) + (
        round(255 * float(opacity)),
    )


def _mirror(points):
    return [[-float(u), float(v)] for u, v in points]


def _transform(point, width, height, projector_size, scale):
    u, v = point
    pixel_x = (float(u) / projector_size[0] + 0.5) * width
    pixel_y = (0.5 - float(v) / projector_size[1]) * height
    return round(pixel_x * scale), round(pixel_y * scale)


def _draw_shape(draw, shape, palette, width, height, projector_size, scale):
    color_key = shape.get("fill") or shape.get("stroke")
    color = palette.get(color_key, color_key)
    rgba = _hex_rgba(color, shape.get("opacity", 1.0))
    shape_type = shape["type"]
    point_sets = [shape.get("points", [])]
    if shape.get("mirror_x"):
        point_sets.append(_mirror(point_sets[0]))
    for points in point_sets:
        pixels = [
            _transform(point, width, height, projector_size, scale)
            for point in points
        ]
        if shape_type == "polygon":
            draw.polygon(pixels, fill=rgba)
        elif shape_type == "line":
            line_width = max(
                1,
                round(
                    float(shape["width"])
                    * width
                    / projector_size[0]
                    * scale
                ),
            )
            draw.line(
                pixels,
                fill=rgba,
                width=line_width,
                joint=shape.get("joint", "curve"),
            )
        else:
            raise ValueError(f"unsupported shape type: {shape_type}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--overlay-output")
    parser.add_argument("--supersample", type=int, default=3)
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    guide_path = (spec_path.parent / spec["guide"]).resolve()
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    width = int(guide["canvas"]["width"])
    height = int(guide["canvas"]["height"])
    projector_size = guide["projector"]["size"]
    scale = max(1, args.supersample)
    canvas = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas, "RGBA")
    palette = spec["palette"]
    for shape in spec["shapes"]:
        _draw_shape(draw, shape, palette, width, height, projector_size, scale)
    canvas = canvas.resize((width, height), Image.Resampling.LANCZOS)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)

    overlay_output = None
    if args.overlay_output:
        guide_image_path = Path(guide["output"])
        if not guide_image_path.is_absolute():
            guide_image_path = (guide_path.parent / guide_image_path).resolve()
        guide_image = Image.open(guide_image_path).convert("RGBA")
        tint = canvas.copy()
        tint.putalpha(tint.getchannel("A").point(lambda value: round(value * 0.72)))
        overlay = Image.alpha_composite(guide_image, tint)
        overlay_output = Path(args.overlay_output).resolve()
        overlay_output.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(overlay_output)

    metadata_path = Path(args.metadata).resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "version": 1,
        "kind": "structure-guided-vector-livery-asset",
        "spec": str(spec_path),
        "guide": str(guide_path),
        "output": str(output),
        "overlay_output": str(overlay_output) if overlay_output else None,
        "canvas": [width, height],
        "projector_size": projector_size,
        "shape_count": len(spec["shapes"]),
        "palette": palette,
        "one_axis_stretch": False,
        "edge_connections": spec.get("edge_connections", []),
        "turn_transition": spec.get("turn_transition"),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
