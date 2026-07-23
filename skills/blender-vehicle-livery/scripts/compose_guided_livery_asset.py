"""Place an aspect-preserved alpha livery asset on a structure-guide canvas."""

import argparse
import json
from pathlib import Path

from PIL import Image


def _indices(value):
    try:
        return [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("patch indices must be comma-separated integers") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--guide", required=True)
    parser.add_argument("--patch-indices", type=_indices, required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--alpha-threshold", type=int, default=8)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metadata", required=True)
    args = parser.parse_args()

    guide_path = Path(args.guide).resolve()
    guide = json.loads(guide_path.read_text(encoding="utf-8"))
    patches = guide["structure"]["surface_patches"]
    selected = [patches[index] for index in args.patch_indices]
    u_min = min(patch["u_range"][0] for patch in selected)
    u_max = max(patch["u_range"][1] for patch in selected)
    v_min = min(patch["v_range"][0] for patch in selected)
    v_max = max(patch["v_range"][1] for patch in selected)
    center_u = (u_min + u_max) * 0.5
    center_v = (v_min + v_max) * 0.5

    source_path = Path(args.source).resolve()
    source = Image.open(source_path).convert("RGBA")
    alpha = source.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > args.alpha_threshold else 0).getbbox()
    if not bbox:
        raise ValueError("source has no non-transparent pixels")
    cropped = source.crop(bbox)
    source_aspect = cropped.width / cropped.height

    canvas_width = int(guide["canvas"]["width"])
    canvas_height = int(guide["canvas"]["height"])
    projector_width, projector_height = guide["projector"]["size"]
    pixels_per_world_x = canvas_width / projector_width
    pixels_per_world_y = canvas_height / projector_height

    # Width-fit the selected armor patches and derive height from the bitmap.
    # This preserves the generated graphic ratio without one-axis stretching.
    world_width = (u_max - u_min) * args.scale
    pixel_width = max(1, round(world_width * pixels_per_world_x))
    pixel_height = max(1, round(pixel_width / source_aspect))
    resized = cropped.resize((pixel_width, pixel_height), Image.Resampling.LANCZOS)

    center_x = (center_u / projector_width + 0.5) * canvas_width
    center_y = (0.5 - center_v / projector_height) * canvas_height
    left = round(center_x - pixel_width * 0.5)
    top = round(center_y - pixel_height * 0.5)
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    canvas.alpha_composite(resized, (left, top))

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    metadata_path = Path(args.metadata).resolve()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "version": 1,
        "kind": "structure-guided-livery-asset",
        "source": str(source_path),
        "guide": str(guide_path),
        "output": str(output),
        "selected_surface_patches": args.patch_indices,
        "selected_world_bounds": {
            "u": [u_min, u_max],
            "v": [v_min, v_max],
        },
        "placement": {
            "center_uv": [center_u, center_v],
            "world_width": world_width,
            "pixel_rect": [left, top, left + pixel_width, top + pixel_height],
            "canvas": [canvas_width, canvas_height],
        },
        "aspect": {
            "source_crop_pixels": [cropped.width, cropped.height],
            "source_crop_ratio": source_aspect,
            "placed_pixels": [pixel_width, pixel_height],
            "one_axis_stretch": False,
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
