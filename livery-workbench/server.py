from __future__ import annotations

import argparse
from array import array
import base64
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import threading
import time
import traceback
import urllib.parse
import webbrowser
from copy import deepcopy
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageOps

from agent_bridge import AgentBridge


APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent.resolve()
PUBLIC_ROOT = APP_ROOT / "public"
STATE_ROOT = APP_ROOT / "state"
PROJECT_STATE_ROOT = STATE_ROOT / "projects"
CACHE_ROOT = APP_ROOT / "cache"
UPLOAD_ROOT = PROJECT_ROOT / "assets" / "anime-liveries" / "workbench" / "uploads"
EXPORT_ASSET_ROOT = PROJECT_ROOT / "assets" / "anime-liveries" / "workbench"
EXPORT_CONFIG_ROOT = PROJECT_ROOT / "config" / "anime-liveries"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "livery-workbench"
SETTINGS_PATH = APP_ROOT / "settings.json"
LIVERY_SKILL_ROOT = PROJECT_ROOT / "skills" / "blender-vehicle-livery"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MODEL_EXTENSIONS = {".obj"}
MAX_JSON_BODY = 64 * 1024 * 1024
DEFAULT_BLENDER = Path(r"E:\SteamLibrary\steamapps\common\Blender\blender.exe")
SURFACE_FACES = ("left", "right", "front", "rear", "top", "bottom")
SURFACE_FACE_LABELS = {
    "left": "左面",
    "right": "右面",
    "front": "前面",
    "rear": "后面",
    "top": "上面",
    "bottom": "下面",
}

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
MESH_BUILD_LOCK = threading.Lock()
AUTO_GUIDES: dict[str, dict[str, Any]] = {}
AGENT_BRIDGE = AgentBridge(PROJECT_ROOT, LIVERY_SKILL_ROOT)
SERVICE_ID = "camo-auto-gen-livery-agent"
SERVICE_API_VERSION = 2


def ensure_directories() -> None:
    for directory in (
        STATE_ROOT,
        PROJECT_STATE_ROOT,
        CACHE_ROOT,
        UPLOAD_ROOT,
        EXPORT_ASSET_ROOT,
        EXPORT_CONFIG_ROOT,
        OUTPUT_ROOT,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def json_load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_settings() -> dict[str, Any]:
    defaults = {
        "blender_path": str(DEFAULT_BLENDER),
        "port": 8765,
        "asset_roots": [
            "assets/anime-liveries",
            "SMSV/body_image",
            "SMSV/turrent_image",
            "2s38",
            "style1",
        ],
    }
    saved = json_load(SETTINGS_PATH, {})
    if isinstance(saved, dict):
        defaults.update(saved)
    return defaults


def safe_project_path(value: str | Path, *, must_exist: bool = True) -> Path:
    raw = Path(str(value))
    candidate = raw if raw.is_absolute() else PROJECT_ROOT / raw
    candidate = candidate.resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("路径必须位于当前项目目录内") from exc
    if must_exist and not candidate.exists():
        raise FileNotFoundError(str(candidate))
    return candidate


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def api_file_url(path: Path) -> str:
    return "/api/file?" + urllib.parse.urlencode({"path": relative_path(path)})


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-_")
    return value[:72] or "livery-project"


def resolve_config_reference(config_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    raw = Path(value)
    candidate = raw if raw.is_absolute() else config_path.parent / raw
    try:
        return candidate.resolve()
    except OSError:
        return None


def infer_model_path(project_name: str) -> Path | None:
    lowered = project_name.lower()
    candidates: list[Path]
    if "j15" in lowered:
        candidates = [PROJECT_ROOT / "J-15Tdixz.obj"]
    elif "strv" in lowered:
        candidates = [PROJECT_ROOT / "Strv_122B+_fix.obj"]
    elif "2s38" in lowered:
        candidates = [PROJECT_ROOT / "2s38" / "2S38x.obj"]
    elif "pantsyr" in lowered:
        candidates = [PROJECT_ROOT / "SMSV" / "pantsyr_sm_sv_fix.obj"]
    else:
        candidates = []
    return next((path for path in candidates if path.exists()), None)


def scan_projects() -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    if not EXPORT_CONFIG_ROOT.exists():
        return projects
    for path in sorted(EXPORT_CONFIG_ROOT.glob("*.json")):
        data = json_load(path)
        if not isinstance(data, dict) or "layers" not in data:
            continue
        guides = data.get("structure_guides") or []
        projects.append(
            {
                "name": data.get("name") or path.stem,
                "path": relative_path(path),
                "styleId": data.get("style_id", ""),
                "guideCount": len(guides),
                "layerCount": len(data.get("layers") or []),
            }
        )
    return projects


def find_boundary_mask(config_path: Path, project: dict[str, Any], guide_id: str) -> Path | None:
    for layer in project.get("layers") or []:
        source = layer.get("source") or {}
        if source.get("guide_id") != guide_id:
            continue
        candidate = resolve_config_reference(config_path, source.get("boundary_mask"))
        if candidate and candidate.exists():
            return candidate
    for guide in project.get("structure_guides") or []:
        if guide.get("id") != guide_id:
            continue
        image_path = resolve_config_reference(config_path, guide.get("image"))
        if image_path:
            inferred = image_path.with_name(image_path.name.replace("structure-guide", "boundary-mask"))
            if inferred.exists():
                return inferred
    return None


def scan_guides() -> list[dict[str, Any]]:
    guides: list[dict[str, Any]] = []
    for config_path in sorted(EXPORT_CONFIG_ROOT.glob("*.json")):
        project = json_load(config_path)
        if not isinstance(project, dict):
            continue
        model_path = infer_model_path(str(project.get("name") or config_path.stem))
        for guide in project.get("structure_guides") or []:
            image_path = resolve_config_reference(config_path, guide.get("image"))
            metadata_path = resolve_config_reference(config_path, guide.get("metadata"))
            if not image_path or not image_path.exists():
                continue
            metadata = json_load(metadata_path, {}) if metadata_path and metadata_path.exists() else {}
            canvas = metadata.get("canvas") or {}
            projection = deepcopy(guide.get("projection") or metadata.get("projector") or {})
            if "world_z_clip" in projection:
                world_clip = projection.pop("world_z_clip")
                if isinstance(world_clip, list) and len(world_clip) == 2:
                    projection["world_z_min"], projection["world_z_max"] = world_clip
            mask_path = find_boundary_mask(config_path, project, str(guide.get("id") or ""))
            width = int(canvas.get("width") or 0)
            height = int(canvas.get("height") or 0)
            if not width or not height:
                try:
                    width, height = Image.open(image_path).size
                except OSError:
                    width, height = 1600, 1600
            guide_id = str(guide.get("id") or f"{config_path.stem}-{guide.get('side', 'surface')}")
            guides.append(
                {
                    "key": f"{config_path.stem}:{guide_id}",
                    "id": guide_id,
                    "label": f"{project.get('name', config_path.stem)} · {guide.get('side', 'surface')}",
                    "side": guide.get("side", "surface"),
                    "targets": guide.get("targets") or [],
                    "projectPath": relative_path(config_path),
                    "projectName": project.get("name") or config_path.stem,
                    "imagePath": relative_path(image_path),
                    "imageUrl": api_file_url(image_path),
                    "maskPath": relative_path(mask_path) if mask_path else "",
                    "maskUrl": api_file_url(mask_path) if mask_path else "",
                    "metadataPath": relative_path(metadata_path) if metadata_path and metadata_path.exists() else "",
                    "modelPath": relative_path(model_path) if model_path else "",
                    "canvas": {"width": width, "height": height},
                    "projection": projection,
                    "base": deepcopy(project.get("base") or {}),
                }
            )
    guides.sort(
        key=lambda item: (
            0 if "j15-avant-tech-reference-layout-v2-r4" in item["projectName"] else 1,
            item["label"],
        )
    )
    return guides


def classify_asset(path: Path) -> tuple[str, str]:
    lowered = relative_path(path).lower()
    filename = path.stem.replace("-", " ").replace("_", " ")
    if "structure-guide" in lowered or "boundary-brief" in lowered or "boundary-mask" in lowered:
        return "guide", filename
    if any(token in lowered for token in ("character-name", "poster-title", "lettering", "decal", "icon")):
        return "decal", filename
    if any(token in lowered for token in ("poster", "generated", "master", "geometry-plan")):
        return "composition", filename
    if any(token in lowered for token in ("body_image", "turrent_image", "identity", "source-top", "hero")):
        return "portrait", filename
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "portrait", filename
    return "texture", filename


def scan_assets(settings: dict[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for configured_root in settings.get("asset_roots") or []:
        try:
            root = safe_project_path(configured_root)
        except (ValueError, FileNotFoundError):
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            category, label = classify_asset(resolved)
            assets.append(
                {
                    "id": hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:14],
                    "name": label,
                    "filename": resolved.name,
                    "path": relative_path(resolved),
                    "url": api_file_url(resolved),
                    "category": category,
                    "modified": int(resolved.stat().st_mtime),
                }
            )
    assets.sort(key=lambda item: (-item["modified"], item["name"]))
    return assets


def scan_models() -> list[dict[str, Any]]:
    preferred = [
        PROJECT_ROOT / "J-15Tdixz.obj",
        PROJECT_ROOT / "Strv_122B+_fix.obj",
        PROJECT_ROOT / "2s38" / "2S38x.obj",
        PROJECT_ROOT / "SMSV" / "pantsyr_sm_sv_fix.obj",
    ]


def canonical_surface_face(value: Any) -> str:
    lowered = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "left": ("left", "port"),
        "right": ("right", "starboard"),
        "front": ("front", "nose", "forward"),
        "rear": ("rear", "back", "tail", "aft"),
        "top": ("top", "roof", "upper"),
        "bottom": ("bottom", "under", "underside", "lower"),
    }
    for face, tokens in aliases.items():
        if any(token in lowered for token in tokens):
            return face
    return ""
    found: list[Path] = []
    seen: set[Path] = set()
    for path in preferred:
        if path.exists():
            found.append(path.resolve())
            seen.add(path.resolve())
    for path in PROJECT_ROOT.glob("*.obj"):
        if path.resolve() not in seen:
            found.append(path.resolve())
            seen.add(path.resolve())
    for folder in ("2s38", "SMSV"):
        root = PROJECT_ROOT / folder
        if root.exists():
            for path in root.glob("*.obj"):
                if path.resolve() not in seen:
                    found.append(path.resolve())
                    seen.add(path.resolve())
    return [
        {
            "name": path.stem,
            "path": relative_path(path),
            "size": path.stat().st_size,
            "meshUrl": "/api/mesh?"
            + urllib.parse.urlencode({"path": relative_path(path), "max": 70000}),
        }
        for path in found
    ]


def load_workbench_projects() -> list[dict[str, Any]]:
    projects = []
    for path in sorted(PROJECT_STATE_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        data = json_load(path, {})
        faces = data.get("faces")
        layer_count = (
            sum(len(face.get("layers") or []) for face in faces if isinstance(face, dict))
            if isinstance(faces, list)
            else len(data.get("layers") or [])
        )
        projects.append(
            {
                "name": data.get("name") or path.stem,
                "path": relative_path(path),
                "updatedAt": data.get("updatedAt") or "",
                "layerCount": layer_count,
            }
        )
    return projects


def make_bootstrap() -> dict[str, Any]:
    settings = load_settings()
    blender_path = Path(str(settings.get("blender_path") or DEFAULT_BLENDER))
    guides = scan_guides()
    models = scan_models()
    return {
        "app": {
            "name": "Vehicle Livery Workbench",
            "version": "1.0.0",
            "projectRoot": str(PROJECT_ROOT),
        },
        "settings": {
            "blenderPath": str(blender_path),
            "blenderAvailable": blender_path.exists(),
        },
        "agent": AGENT_BRIDGE.capabilities(),
        "assets": scan_assets(settings),
        "guides": guides,
        "models": models,
        "sourceProjects": scan_projects(),
        "workbenchProjects": load_workbench_projects(),
        "defaultGuideKey": guides[0]["key"] if guides else "",
    }


def save_uploaded_asset(payload: dict[str, Any]) -> dict[str, Any]:
    filename = Path(str(payload.get("filename") or "upload.png")).name
    data_url = str(payload.get("dataUrl") or "")
    match = re.match(r"^data:([\w/+.-]+);base64,(.+)$", data_url, flags=re.DOTALL)
    if not match:
        raise ValueError("上传内容不是有效的图片 Data URL")
    extension = Path(filename).suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        mime_extension = mimetypes.guess_extension(match.group(1)) or ".png"
        extension = mime_extension if mime_extension in IMAGE_EXTENSIONS else ".png"
        filename = Path(filename).stem + extension
    binary = base64.b64decode(match.group(2), validate=True)
    if len(binary) > 32 * 1024 * 1024:
        raise ValueError("单个素材不得超过 32 MB")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", filename, flags=re.UNICODE)
    target = UPLOAD_ROOT / f"{datetime.now():%Y%m%d-%H%M%S-%f}-{safe_name}"
    target.write_bytes(binary)
    try:
        with Image.open(target) as image:
            image.verify()
    except Exception:
        target.unlink(missing_ok=True)
        raise ValueError("上传文件无法识别为图片")
    category, label = classify_asset(target)
    return {
        "id": hashlib.sha1(str(target).encode("utf-8")).hexdigest()[:14],
        "name": label,
        "filename": target.name,
        "path": relative_path(target),
        "url": api_file_url(target),
        "category": category if category != "texture" else "uploaded",
        "modified": int(target.stat().st_mtime),
    }


def normalize_crop(crop: Any) -> tuple[float, float, float, float]:
    crop = crop if isinstance(crop, dict) else {}
    left = max(0.0, min(0.9, float(crop.get("left", 0.0))))
    top = max(0.0, min(0.9, float(crop.get("top", 0.0))))
    right = max(0.0, min(0.9, float(crop.get("right", 0.0))))
    bottom = max(0.0, min(0.9, float(crop.get("bottom", 0.0))))
    if left + right >= 0.95:
        right = max(0.0, 0.95 - left)
    if top + bottom >= 0.95:
        bottom = max(0.0, 0.95 - top)
    return left, top, right, bottom


def resolve_font(font_family: str, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = {
        "art": [
            Path(r"C:\Windows\Fonts\STXINGKA.TTF"),
            Path(r"C:\Windows\Fonts\simkai.ttf"),
            Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        ],
        "sans": [
            Path(r"C:\Windows\Fonts\msyhbd.ttc"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ],
        "serif": [
            Path(r"C:\Windows\Fonts\STSONG.TTF"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
        ],
    }
    for candidate in candidates.get(font_family, candidates["art"]):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), max(8, font_size))
    return ImageFont.load_default()


def layer_source_image(layer: dict[str, Any], canvas_size: tuple[int, int]) -> Image.Image:
    if layer.get("type") == "text":
        font_size = max(16, int(float(layer.get("fontSize", 120))))
        text = str(layer.get("text") or "TITLE")
        font = resolve_font(str(layer.get("fontFamily") or "art"), font_size)
        stroke = max(0, int(float(layer.get("strokeWidth", 2))))
        temporary = Image.new("RGBA", (canvas_size[0], max(font_size * 4, 256)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temporary)
        bounds = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        width = max(8, bounds[2] - bounds[0] + stroke * 4)
        height = max(8, bounds[3] - bounds[1] + stroke * 4)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text(
            (stroke * 2 - bounds[0], stroke * 2 - bounds[1]),
            text,
            font=font,
            fill=ImageColor.getcolor(str(layer.get("fill") or "#18252D"), "RGBA"),
            stroke_width=stroke,
            stroke_fill=ImageColor.getcolor(str(layer.get("stroke") or "#E8F7F5"), "RGBA"),
        )
        return image
    path = safe_project_path(str(layer.get("path") or ""))
    return Image.open(path).convert("RGBA")


def transformed_layer(layer: dict[str, Any], canvas_size: tuple[int, int]) -> Image.Image:
    canvas_width, canvas_height = canvas_size
    source = layer_source_image(layer, canvas_size)
    left, top, right, bottom = normalize_crop(layer.get("crop"))
    crop_box = (
        int(source.width * left),
        int(source.height * top),
        max(int(source.width * left) + 1, int(source.width * (1.0 - right))),
        max(int(source.height * top) + 1, int(source.height * (1.0 - bottom))),
    )
    source = source.crop(crop_box)
    if bool(layer.get("flipX")):
        source = ImageOps.mirror(source)
    if bool(layer.get("flipY")):
        source = ImageOps.flip(source)
    scale = max(0.005, min(4.0, float(layer.get("scale", 0.4))))
    target_width = max(1, int(canvas_width * scale))
    target_height = max(1, int(target_width * source.height / max(1, source.width)))
    source = source.resize((target_width, target_height), Image.Resampling.LANCZOS)
    rotation = float(layer.get("rotation", 0.0))
    if abs(rotation) > 0.001:
        source = source.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
    opacity = max(0.0, min(1.0, float(layer.get("opacity", 1.0))))
    if opacity < 0.999:
        alpha = source.getchannel("A").point(lambda value: int(value * opacity))
        source.putalpha(alpha)
    positioned = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    center_x = float(layer.get("x", 0.5)) * canvas_width
    center_y = float(layer.get("y", 0.5)) * canvas_height
    position = (round(center_x - source.width / 2), round(center_y - source.height / 2))
    positioned.alpha_composite(source, position)
    return positioned


def blend_rgba(base: Image.Image, overlay: Image.Image, mode: str) -> Image.Image:
    mode = mode.lower()
    if mode == "normal":
        return Image.alpha_composite(base, overlay)
    base_rgb = base.convert("RGB")
    overlay_rgb = overlay.convert("RGB")
    if mode == "multiply":
        blended = ImageChops.multiply(base_rgb, overlay_rgb)
    elif mode == "screen":
        blended = ImageChops.screen(base_rgb, overlay_rgb)
    elif mode in {"add", "linear-dodge"}:
        blended = ImageChops.add(base_rgb, overlay_rgb, scale=1.0, offset=0)
    elif mode == "overlay":
        multiplied = ImageChops.multiply(base_rgb, overlay_rgb)
        screened = ImageChops.screen(base_rgb, overlay_rgb)
        luminance = base_rgb.convert("L")
        blended = Image.composite(screened, multiplied, luminance)
    else:
        return Image.alpha_composite(base, overlay)
    candidate_rgb = Image.composite(blended, overlay_rgb, base.getchannel("A"))
    candidate = candidate_rgb.convert("RGBA")
    candidate.putalpha(overlay.getchannel("A"))
    return Image.alpha_composite(base, candidate)


def find_guide(payload: dict[str, Any]) -> dict[str, Any]:
    key = str(payload.get("guideKey") or "")
    if key in AUTO_GUIDES:
        return deepcopy(AUTO_GUIDES[key])
    for guide in scan_guides():
        if guide["key"] == key:
            return guide
    raise ValueError("找不到所选结构导引")


def compose_state(payload: dict[str, Any], output_path: Path) -> tuple[dict[str, Any], Image.Image]:
    guide = find_guide(payload)
    canvas = guide["canvas"]
    size = (int(canvas["width"]), int(canvas["height"]))
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    for layer in payload.get("layers") or []:
        if not layer.get("visible", True):
            continue
        overlay = transformed_layer(layer, size)
        result = blend_rgba(result, overlay, str(layer.get("blendMode") or "normal"))
    if payload.get("clipToBoundary", True) and guide.get("maskPath"):
        mask_path = safe_project_path(guide["maskPath"])
        mask = Image.open(mask_path).convert("L")
        if mask.size != size:
            mask = mask.resize(size, Image.Resampling.LANCZOS)
        result.putalpha(ImageChops.multiply(result.getchannel("A"), mask))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, format="PNG", optimize=True)
    return guide, result


def save_workbench_project(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "Untitled livery").strip()
    payload = deepcopy(payload)
    payload["name"] = name
    payload["updatedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    payload["format"] = "vehicle-livery-workbench"
    payload["version"] = 2
    state_path = PROJECT_STATE_ROOT / f"{slugify(name)}.json"
    atomic_json_write(state_path, payload)
    return {"path": relative_path(state_path), "updatedAt": payload["updatedAt"]}


def next_revision(slug: str) -> tuple[str, int]:
    revision = 1
    while (EXPORT_CONFIG_ROOT / f"{slug}-r{revision}.json").exists():
        revision += 1
    return f"{slug}-r{revision}", revision


def relative_reference(from_path: Path, target: Path) -> str:
    return os.path.relpath(target.resolve(), from_path.parent.resolve()).replace("/", "\\")


def export_workbench_project(payload: dict[str, Any]) -> dict[str, Any]:
    save_result = save_workbench_project(payload)
    name = str(payload.get("name") or "livery-project")
    export_name, revision = next_revision(slugify(name))
    asset_dir = EXPORT_ASSET_ROOT / export_name
    config_path = EXPORT_CONFIG_ROOT / f"{export_name}.json"
    requested_faces = payload.get("faces")
    surface_payloads: list[dict[str, Any]] = []
    if isinstance(requested_faces, list):
        for record in requested_faces:
            if not isinstance(record, dict):
                continue
            layers = record.get("layers") or []
            if not any(layer.get("visible", True) for layer in layers if isinstance(layer, dict)):
                continue
            surface_payload = deepcopy(payload)
            surface_payload.update(deepcopy(record))
            surface_payloads.append(surface_payload)
    if not surface_payloads:
        surface_payloads = [deepcopy(payload)]

    generated_layers: list[dict[str, Any]] = []
    generated_guides: list[dict[str, Any]] = []
    surface_manifests: list[dict[str, Any]] = []
    source_projects: list[tuple[Path, dict[str, Any]]] = []
    target_groups: dict[str, Any] = {}
    total_editable_layers = 0
    last_image: Image.Image | None = None
    for index, surface_payload in enumerate(surface_payloads):
        face = canonical_surface_face(surface_payload.get("face")) or "surface"
        filename = "workbench-composite.png" if len(surface_payloads) == 1 else f"workbench-{face}.png"
        composite_path = asset_dir / filename
        guide, image = compose_state(surface_payload, composite_path)
        last_image = image
        source_config_path = safe_project_path(guide["projectPath"])
        source_project = json_load(source_config_path)
        if not isinstance(source_project, dict):
            raise ValueError("结构导引对应的源项目无法读取")
        source_projects.append((source_config_path, source_project))
        target_groups.update(deepcopy(source_project.get("target_groups") or {}))
        layer_id = f"workbench-{face}" if len(surface_payloads) > 1 else "workbench-composite"
        projection = deepcopy(guide.get("projection") or {})
        surface = deepcopy(surface_payload.get("surface") or {})
        source_mask = safe_project_path(guide["maskPath"]) if guide.get("maskPath") else None
        source_guide_image = safe_project_path(guide["imagePath"])
        source_guide_metadata = (
            safe_project_path(guide["metadataPath"]) if guide.get("metadataPath") else None
        )
        if guide.get("autoGenerated"):
            asset_dir.mkdir(parents=True, exist_ok=True)
            durable_guide = asset_dir / f"{face}-structure-guide.png"
            durable_mask = asset_dir / f"{face}-boundary-mask.png"
            durable_metadata = asset_dir / f"{face}-structure-guide.json"
            shutil.copy2(source_guide_image, durable_guide)
            if source_mask:
                shutil.copy2(source_mask, durable_mask)
            if source_guide_metadata:
                shutil.copy2(source_guide_metadata, durable_metadata)
            source_guide_image = durable_guide
            source_mask = durable_mask if source_mask else None
            source_guide_metadata = durable_metadata if source_guide_metadata else None
        visible_layers = [
            layer
            for layer in surface_payload.get("layers") or []
            if isinstance(layer, dict) and layer.get("visible", True)
        ]
        total_editable_layers += len(visible_layers)
        targets = guide.get("targets") or list((source_project.get("target_groups") or {}).keys())[:1]
        generated_layer = {
            "id": layer_id,
            "name": f"Workbench {SURFACE_FACE_LABELS.get(face, face)} composition",
            "type": "image_projection",
            "enabled": True,
            "side": face,
            "semantic_role": "hero_art",
            "aspect_policy": "PRESERVE",
            "targets": targets,
            "image": relative_reference(config_path, composite_path),
            "source": {
                "kind": "manual-workbench-composite",
                "guide_id": guide["id"],
                "workbench_state": relative_reference(
                    config_path, safe_project_path(save_result["path"])
                ),
                "boundary_mask": relative_reference(config_path, source_mask) if source_mask else "",
                "aspect_preserved": True,
                "one_axis_stretch": False,
                "six_face_surface": face,
                "source_layers": [
                    {
                        "id": layer.get("id"),
                        "name": layer.get("name"),
                        "path": layer.get("path", ""),
                        "type": layer.get("type", "image"),
                    }
                    for layer in visible_layers
                ],
            },
            "opacity": 1.0,
            "blend_mode": "MIX",
            "alpha_mode": "IMAGE",
            "surface": {
                "roughness": float(surface.get("roughness", 0.3)),
                "metallic": float(surface.get("metallic", 0.12)),
                "coat_weight": float(surface.get("coatWeight", 0.5)),
                "coat_roughness": float(surface.get("coatRoughness", 0.12)),
            },
            "projection": projection,
        }
        generated_layers.append(generated_layer)
        generated_guides.append(
            {
                "id": guide["id"],
                "side": face,
                "targets": targets,
                "image": relative_reference(config_path, source_guide_image),
                "metadata": (
                    relative_reference(config_path, source_guide_metadata)
                    if source_guide_metadata
                    else ""
                ),
                "designed_layers": [layer_id],
                "projection": deepcopy(projection),
            }
        )
        surface_manifests.append(
            {
                "face": face,
                "guide": guide["key"],
                "composite": relative_path(composite_path),
                "canvas": deepcopy(guide["canvas"]),
                "layers": deepcopy(surface_payload.get("layers") or []),
            }
        )

    source_config_path, source_project = source_projects[0]
    first_surface = surface_payloads[0]
    first_guide = find_guide(first_surface)
    base = deepcopy(source_project.get("base") or {})
    base["color"] = str(first_surface.get("baseColor") or base.get("color") or "#DDE5E8")
    render = deepcopy(
        source_project.get("render")
        or {
            "resolution": 768,
            "views": [
                {"name": "top_check", "azimuth": 180.0, "elevation": 82.0},
                {"name": "left_front_top", "azimuth": 208.0, "elevation": 36.0},
                {"name": "right_front_top", "azimuth": -28.0, "elevation": 36.0},
            ],
        }
    )
    views = render.setdefault("views", [])
    existing_view_names = {str(view.get("name") or "") for view in views}
    direct_views = {
        "top": {"name": "top_check", "azimuth": 180.0, "elevation": 82.0},
        "bottom": {"name": "bottom_check", "azimuth": 0.0, "elevation": -82.0},
        "front": {"name": "front", "azimuth": 180.0, "elevation": 8.0},
        "rear": {"name": "rear", "azimuth": 0.0, "elevation": 8.0},
        "left": {"name": "left_side", "azimuth": 90.0, "elevation": 8.0},
        "right": {"name": "right_side", "azimuth": -90.0, "elevation": 8.0},
    }
    for layer in generated_layers:
        view = direct_views.get(layer["side"])
        if view and view["name"] not in existing_view_names:
            views.append(view)
            existing_view_names.add(view["name"])
    generated_project = {
        "version": 1,
        "name": export_name,
        "style_id": source_project.get("style_id", "manual-workbench"),
        "design_rules": {
            "hero_art_preserve_aspect": True,
            "max_other_aspect_distortion": 0.02,
            "record_iteration_in_skill": True,
            "surface_direction_contract": bool(
                (source_project.get("design_rules") or {}).get("surface_direction_contract", True)
            ),
            "structure_guide_contract": True,
            "poster_art_quality_contract": False,
        },
        "iteration_record": {
            "id": export_name,
            "finding": "Manual compositions assembled across projector-aligned vehicle faces.",
            "change": f"Flattened {total_editable_layers} editable layers across {len(generated_layers)} physical surface projectors and clipped each result with its own boundary mask.",
            "validation": "Pending Blender projection review; every workbench surface preserves its guide projector and uniform layer scaling.",
            "skill_updates": ["livery-workbench", "references/iteration-log.md"],
        },
        "base": base,
        "target_groups": target_groups,
        "layers": generated_layers,
        "structure_guides": generated_guides,
        "art_direction": {
            "theme": "manual-six-face-structure-guided-composition",
            "source_project": source_project.get("name") or source_config_path.stem,
            "workbench": {
                "surface_count": len(generated_layers),
                "layer_count": total_editable_layers,
                "active_face": payload.get("activeFace") or first_surface.get("face") or "",
            },
        },
        "render": render,
    }
    atomic_json_write(config_path, generated_project)
    manifest = {
        "version": 1,
        "name": export_name,
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "workbenchState": save_result["path"],
        "sourceProject": first_guide["projectPath"],
        "guide": first_guide["key"],
        "modelPath": payload.get("modelPath") or first_guide.get("modelPath"),
        "composite": surface_manifests[0]["composite"],
        "surfaces": surface_manifests,
        "config": relative_path(config_path),
        "canvas": surface_manifests[0]["canvas"],
        "layers": deepcopy(first_surface.get("layers") or []),
    }
    manifest_path = asset_dir / "manifest.json"
    atomic_json_write(manifest_path, manifest)
    return {
        "name": export_name,
        "revision": revision,
        "configPath": relative_path(config_path),
        "compositePath": surface_manifests[0]["composite"],
        "compositeUrl": api_file_url(safe_project_path(surface_manifests[0]["composite"]))
        + f"&v={int(time.time())}",
        "surfaces": surface_manifests,
        "manifestPath": relative_path(manifest_path),
        "modelPath": payload.get("modelPath") or first_guide.get("modelPath"),
        "width": last_image.width if last_image else 0,
        "height": last_image.height if last_image else 0,
    }


def next_output_directory(project_stem: str) -> Path:
    base = OUTPUT_ROOT / project_stem
    if not base.exists():
        return base
    run = 2
    while (OUTPUT_ROOT / f"{project_stem}-run{run}").exists():
        run += 1
    return OUTPUT_ROOT / f"{project_stem}-run{run}"


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in job.items() if key not in {"process"}}
    output = job.get("outputPath")
    if output:
        output_path = safe_project_path(output, must_exist=False)
        if output_path.exists():
            previews = sorted(
                output_path.rglob("*.png"),
                key=lambda path: (0 if "check" in path.name.lower() else 1, path.name),
            )
            result["previews"] = [
                {"name": path.stem, "path": relative_path(path), "url": api_file_url(path)}
                for path in previews[:18]
            ]
            blends = sorted(output_path.glob("*.blend"))
            glbs = sorted(output_path.glob("*.glb"))
            result["blendPath"] = relative_path(blends[0]) if blends else ""
            result["glbPath"] = relative_path(glbs[0]) if glbs else ""
    return result


def run_blender_job(job_id: str, command: list[str], env: dict[str, str]) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["startedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        with JOBS_LOCK:
            JOBS[job_id]["process"] = process
        lines: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line.rstrip())
            if len(lines) > 300:
                lines = lines[-300:]
            with JOBS_LOCK:
                JOBS[job_id]["logTail"] = lines[-80:]
        return_code = process.wait()
        with JOBS_LOCK:
            JOBS[job_id]["returnCode"] = return_code
            JOBS[job_id]["status"] = "completed" if return_code == 0 else "failed"
            JOBS[job_id]["finishedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
            JOBS[job_id]["logTail"] = lines[-120:]
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "failed"
            JOBS[job_id]["error"] = str(exc)
            JOBS[job_id]["finishedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")


def start_blender_job(payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    blender = Path(str(settings.get("blender_path") or DEFAULT_BLENDER))
    if not blender.exists():
        raise FileNotFoundError(f"Blender 不存在：{blender}")
    project_path = safe_project_path(str(payload.get("configPath") or ""))
    model_path = safe_project_path(str(payload.get("modelPath") or ""))
    pipeline = PROJECT_ROOT / "skills" / "blender-vehicle-livery" / "scripts" / "anime_pipeline.py"
    if not pipeline.exists():
        raise FileNotFoundError(str(pipeline))
    output_path = next_output_directory(project_path.stem)
    command = [
        str(blender),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(pipeline),
        "--",
        "--model",
        str(model_path),
        "--project",
        str(project_path),
        "--output",
        str(output_path),
    ]
    job_id = f"blend-{datetime.now():%Y%m%d-%H%M%S}-{hashlib.sha1(str(time.time()).encode()).hexdigest()[:6]}"
    job = {
        "id": job_id,
        "kind": "blender-render",
        "status": "queued",
        "projectPath": relative_path(project_path),
        "modelPath": relative_path(model_path),
        "outputPath": relative_path(output_path),
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "logTail": [],
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    env = os.environ.copy()
    env["DISABLE_TELEMETRY"] = "1"
    env["BLENDER_MCP_TELEMETRY"] = "0"
    thread = threading.Thread(target=run_blender_job, args=(job_id, command, env), daemon=True)
    thread.start()
    return public_job(job)


def open_blend_file(payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    blender = Path(str(settings.get("blender_path") or DEFAULT_BLENDER))
    blend_path = safe_project_path(str(payload.get("blendPath") or ""))
    if blend_path.suffix.lower() != ".blend":
        raise ValueError("只能打开 .blend 文件")
    subprocess.Popen(
        [str(blender), str(blend_path)],
        cwd=str(PROJECT_ROOT),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    return {"opened": relative_path(blend_path)}


def generate_mesh_binary_fallback(model_path: Path, max_triangles: int) -> bytes:
    stat = model_path.stat()
    cache_key = hashlib.sha1(
        f"fallback-v2:{model_path}:{stat.st_size}:{stat.st_mtime_ns}:{max_triangles}".encode("utf-8")
    ).hexdigest()
    cache_path = CACHE_ROOT / f"{cache_key}.mesh"
    if cache_path.exists():
        return cache_path.read_bytes()
    face_count = 0
    with model_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("f "):
                face_count += 1
    stride = max(1, math.ceil(face_count / max(1, max_triangles)))
    vertices: list[tuple[float, float, float]] = []
    positions = array("f")
    normals = array("f")
    face_index = 0
    triangle_count = 0
    with model_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                take_face = face_index % stride == 0
                face_index += 1
                if not take_face:
                    continue
                indices: list[int] = []
                for token in line.split()[1:]:
                    raw_index = int(token.split("/")[0])
                    indices.append(raw_index - 1 if raw_index > 0 else len(vertices) + raw_index)
                for offset in range(1, len(indices) - 1):
                    if triangle_count >= max_triangles:
                        break
                    try:
                        a, b, c = vertices[indices[0]], vertices[indices[offset]], vertices[indices[offset + 1]]
                    except (IndexError, ValueError):
                        continue
                    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                    nx = ab[1] * ac[2] - ab[2] * ac[1]
                    ny = ab[2] * ac[0] - ab[0] * ac[2]
                    nz = ab[0] * ac[1] - ab[1] * ac[0]
                    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                    normal = (nx / length, ny / length, nz / length)
                    for point in (a, b, c):
                        positions.extend(point)
                        normals.extend(normal)
                    triangle_count += 1
                if triangle_count >= max_triangles:
                    break
    vertex_count = len(positions) // 3
    header = struct.pack("<4sII", b"LVR1", vertex_count, triangle_count)
    binary = header + positions.tobytes() + normals.tobytes()
    cache_path.write_bytes(binary)
    return binary


def generate_mesh_binary(model_path: Path, max_triangles: int) -> bytes:
    stat = model_path.stat()
    cache_key = hashlib.sha1(
        f"blender-decimate-v2:{model_path}:{stat.st_size}:{stat.st_mtime_ns}:{max_triangles}".encode(
            "utf-8"
        )
    ).hexdigest()
    cache_path = CACHE_ROOT / f"{cache_key}.mesh"
    if cache_path.exists():
        return cache_path.read_bytes()
    with MESH_BUILD_LOCK:
        if cache_path.exists():
            return cache_path.read_bytes()
        settings = load_settings()
        blender = Path(str(settings.get("blender_path") or DEFAULT_BLENDER))
        builder = APP_ROOT / "build_preview_mesh.py"
        if blender.exists() and builder.exists():
            environment = os.environ.copy()
            environment["DISABLE_TELEMETRY"] = "1"
            environment["BLENDER_MCP_TELEMETRY"] = "0"
            command = [
                str(blender),
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(builder),
                "--",
                "--model",
                str(model_path),
                "--output",
                str(cache_path),
                "--max-triangles",
                str(max_triangles),
            ]
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if completed.returncode == 0 and cache_path.exists():
                binary = cache_path.read_bytes()
                if binary[:4] == b"LVR1" and len(binary) >= 12:
                    return binary
            cache_path.unlink(missing_ok=True)
            print(
                "[workbench] Blender preview decimation failed; using sampled fallback.\n"
                + (completed.stdout or "")[-2000:]
            )
        return generate_mesh_binary_fallback(model_path, max_triangles)


def _mesh_arrays(binary: bytes) -> tuple[array, array, int]:
    if len(binary) < 12 or binary[:4] != b"LVR1":
        raise ValueError("轻量网格缓存格式无效")
    vertex_count = struct.unpack_from("<I", binary, 4)[0]
    position_bytes = vertex_count * 3 * 4
    normal_offset = 12 + position_bytes
    if len(binary) < normal_offset + position_bytes:
        raise ValueError("轻量网格缓存数据不完整")
    positions = array("f")
    positions.frombytes(binary[12:normal_offset])
    normals = array("f")
    normals.frombytes(binary[normal_offset : normal_offset + position_bytes])
    if os.sys.byteorder != "little":
        positions.byteswap()
        normals.byteswap()
    return positions, normals, vertex_count


def _dot3(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _auto_face_basis(
    face: str,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return {
        "left": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        "right": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        "front": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        "rear": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
        "top": ((0.0, 0.0, -1.0), (0.0, -1.0, 0.0)),
        "bottom": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    }[face]


def _auto_face_frame(
    positions: array, face: str
) -> tuple[dict[str, Any], tuple[int, int], tuple[float, float, float], tuple[float, float, float]]:
    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    for index in range(0, len(positions), 3):
        for axis in range(3):
            value = float(positions[index + axis])
            minimum[axis] = min(minimum[axis], value)
            maximum[axis] = max(maximum[axis], value)
    center = tuple((minimum[axis] + maximum[axis]) * 0.5 for axis in range(3))
    spans = tuple(max(0.001, maximum[axis] - minimum[axis]) for axis in range(3))
    direction, up = _auto_face_basis(face)
    right = _cross3(direction, up)
    if face in {"left", "right"}:
        size = (spans[1] * 1.06, spans[2] * 1.06)
        depth = spans[0] * 1.08
    elif face in {"front", "rear"}:
        size = (spans[0] * 1.06, spans[2] * 1.06)
        depth = spans[1] * 1.08
    else:
        size = (spans[0] * 1.06, spans[1] * 1.06)
        depth = spans[2] * 1.08
    longest = max(size)
    canvas = (
        max(64, round(1200 * size[0] / longest)),
        max(64, round(1200 * size[1] / longest)),
    )
    projection = {
        "center": [round(value, 6) for value in center],
        "direction": list(direction),
        "up": list(up),
        "size": [round(size[0], 6), round(size[1], 6)],
        "depth": round(depth, 6),
        "facing_threshold": 0.02,
    }
    return projection, canvas, right, up


def _ensure_auto_face_assets(
    model_path: Path,
    face: str,
    positions: array,
    normals: array,
    template: dict[str, Any],
) -> dict[str, Any]:
    stat = model_path.stat()
    cache_key = hashlib.sha1(
        f"auto-six-face-v2:{model_path}:{stat.st_size}:{stat.st_mtime_ns}:{face}".encode("utf-8")
    ).hexdigest()[:20]
    image_path = CACHE_ROOT / f"{cache_key}-{face}-structure-guide.png"
    mask_path = CACHE_ROOT / f"{cache_key}-{face}-boundary-mask.png"
    metadata_path = CACHE_ROOT / f"{cache_key}-{face}-structure-guide.json"
    projection, canvas, right, up = _auto_face_frame(positions, face)
    if not image_path.exists() or not mask_path.exists() or not metadata_path.exists():
        width, height = canvas
        mask = Image.new("L", canvas, 0)
        guide = Image.new("RGBA", canvas, (0, 0, 0, 0))
        mask_draw = ImageDraw.Draw(mask)
        guide_draw = ImageDraw.Draw(guide, "RGBA")
        center = tuple(float(value) for value in projection["center"])
        size_x, size_y = (float(value) for value in projection["size"])
        direction = tuple(float(value) for value in projection["direction"])
        outward = tuple(-value for value in direction)
        triangle_count = len(positions) // 9
        for triangle in range(triangle_count):
            start = triangle * 9
            points = []
            for offset in (0, 3, 6):
                point = tuple(float(positions[start + offset + axis]) for axis in range(3))
                relative = tuple(point[axis] - center[axis] for axis in range(3))
                u = _dot3(relative, right) / size_x + 0.5
                v = _dot3(relative, up) / size_y + 0.5
                points.append((round(u * (width - 1)), round((1.0 - v) * (height - 1))))
            mask_draw.polygon(points, fill=255)
            if triangle % 4 == 0:
                normal = tuple(float(normals[start + axis]) for axis in range(3))
                facing = abs(_dot3(normal, outward))
                shade = round(18 + min(1.0, facing) * 38)
                guide_draw.polygon(points, fill=(188, 206, 207, shade))
                guide_draw.line(points + [points[0]], fill=(26, 45, 48, 72), width=1)
        guide.putalpha(ImageChops.lighter(guide.getchannel("A"), mask.point(lambda value: value // 7)))
        image_path.parent.mkdir(parents=True, exist_ok=True)
        guide.save(image_path, "PNG", optimize=True)
        mask.save(mask_path, "PNG", optimize=True)
        atomic_json_write(
            metadata_path,
            {
                "version": 1,
                "kind": "projector-aligned-surface-structure-guide",
                "generation_method": "auto-six-face-orthographic-preview-mesh",
                "model": relative_path(model_path),
                "face": face,
                "canvas": {"width": width, "height": height},
                "projector": projection,
                "source_triangles": triangle_count,
            },
        )
    guide_id = f"auto-{slugify(model_path.stem)}-{face}"
    record = {
        "key": f"auto-six-face:{slugify(model_path.stem)}:{face}",
        "id": guide_id,
        "label": f"{model_path.stem} · 自动{SURFACE_FACE_LABELS[face]}",
        "side": face,
        "targets": deepcopy(template.get("targets") or []),
        "projectPath": template["projectPath"],
        "projectName": template.get("projectName") or "auto-six-face",
        "imagePath": relative_path(image_path),
        "imageUrl": api_file_url(image_path),
        "maskPath": relative_path(mask_path),
        "maskUrl": api_file_url(mask_path),
        "metadataPath": relative_path(metadata_path),
        "modelPath": relative_path(model_path),
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "projection": projection,
        "base": deepcopy(template.get("base") or {}),
        "autoGenerated": True,
    }
    AUTO_GUIDES[record["key"]] = deepcopy(record)
    return record


def six_face_guides(model_reference: str) -> dict[str, Any]:
    model_path = safe_project_path(model_reference)
    if model_path.suffix.lower() not in MODEL_EXTENSIONS:
        raise ValueError("六面视图仅支持项目内 OBJ 模型")
    model_relative = relative_path(model_path)
    all_guides = scan_guides()
    model_guides = [guide for guide in all_guides if guide.get("modelPath") == model_relative]
    if not model_guides:
        raise ValueError("该模型尚无可用于确定目标网格的结构导引")
    by_face: dict[str, dict[str, Any]] = {}
    for guide in model_guides:
        face = canonical_surface_face(guide.get("side"))
        if face and face not in by_face:
            by_face[face] = deepcopy(guide)
            by_face[face]["autoGenerated"] = False
    missing = [face for face in SURFACE_FACES if face not in by_face]
    if missing:
        binary = generate_mesh_binary(model_path, 70000)
        positions, normals, _ = _mesh_arrays(binary)
        template = model_guides[0]
        for face in missing:
            by_face[face] = _ensure_auto_face_assets(
                model_path,
                face,
                positions,
                normals,
                template,
            )
    return {
        "modelPath": model_relative,
        "faces": [by_face[face] for face in SURFACE_FACES],
    }


class WorkbenchHandler(SimpleHTTPRequestHandler):
    server_version = "LiveryWorkbench/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[workbench] {self.address_string()} - {format % args}")

    def send_json(self, data: Any, status: int = 200) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def send_error_json(self, exc: Exception, status: int = 400) -> None:
        self.send_json({"error": str(exc), "type": type(exc).__name__}, status)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_JSON_BODY:
            raise ValueError("请求内容大小无效")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求必须为 JSON 对象")
        return payload

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/bootstrap":
                self.send_json(make_bootstrap())
                return
            if parsed.path == "/api/six-faces":
                query = urllib.parse.parse_qs(parsed.query)
                self.send_json(six_face_guides(query.get("modelPath", [""])[0]))
                return
            if parsed.path == "/api/file":
                query = urllib.parse.parse_qs(parsed.query)
                path = safe_project_path(query.get("path", [""])[0])
                if not path.is_file():
                    raise FileNotFoundError(str(path))
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(path.stat().st_size))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 512):
                        self.wfile.write(chunk)
                return
            if parsed.path == "/api/mesh":
                query = urllib.parse.parse_qs(parsed.query)
                path = safe_project_path(query.get("path", [""])[0])
                maximum = max(5000, min(150000, int(query.get("max", ["70000"])[0])))
                binary = generate_mesh_binary(path, maximum)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(binary)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(binary)
                return
            if parsed.path.startswith("/api/jobs/"):
                job_id = parsed.path.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(job_id)
                    if not job:
                        raise KeyError("任务不存在")
                    result = public_job(job)
                self.send_json(result)
                return
            if parsed.path == "/api/agent/events":
                query = urllib.parse.parse_qs(parsed.query)
                since = max(0, int(query.get("since", ["0"])[0]))
                self.send_json(AGENT_BRIDGE.get_status(since))
                return
            if parsed.path == "/api/health":
                self.send_json(
                    {
                        "ok": True,
                        "service": SERVICE_ID,
                        "apiVersion": SERVICE_API_VERSION,
                        "agentAvailable": bool(AGENT_BRIDGE.codex_path),
                        "time": datetime.now().isoformat(),
                    }
                )
                return
            self.serve_static(parsed.path)
        except FileNotFoundError as exc:
            self.send_error_json(exc, 404)
        except KeyError as exc:
            self.send_error_json(exc, 404)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(exc, 400)

    def serve_static(self, url_path: str) -> None:
        relative = url_path.lstrip("/") or "index.html"
        path = (PUBLIC_ROOT / relative).resolve()
        try:
            path.relative_to(PUBLIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if path.is_dir():
            path = path / "index.html"
        if not path.exists():
            path = PUBLIC_ROOT / "index.html"
        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/upload":
                self.send_json(save_uploaded_asset(payload), 201)
                return
            if parsed.path == "/api/projects/save":
                self.send_json(save_workbench_project(payload), 201)
                return
            if parsed.path == "/api/projects/load":
                path = safe_project_path(str(payload.get("path") or ""))
                self.send_json(json_load(path, {}))
                return
            if parsed.path == "/api/projects/export":
                self.send_json(export_workbench_project(payload), 201)
                return
            if parsed.path == "/api/blender/run":
                self.send_json(start_blender_job(payload), 202)
                return
            if parsed.path == "/api/blender/open":
                self.send_json(open_blend_file(payload))
                return
            if parsed.path == "/api/agent/message":
                self.send_json(
                    AGENT_BRIDGE.send_message(
                        str(payload.get("message") or ""),
                        payload.get("context") if isinstance(payload.get("context"), dict) else {},
                    ),
                    202,
                )
                return
            if parsed.path == "/api/agent/interrupt":
                self.send_json(AGENT_BRIDGE.interrupt())
                return
            if parsed.path == "/api/agent/reset":
                self.send_json(AGENT_BRIDGE.reset())
                return
            if parsed.path == "/api/agent/approval":
                self.send_json(
                    AGENT_BRIDGE.respond_approval(
                        str(payload.get("approvalId") or ""),
                        str(payload.get("decision") or "decline"),
                    )
                )
                return
            if parsed.path == "/api/agent/proposal":
                self.send_json(
                    AGENT_BRIDGE.resolve_proposal(
                        str(payload.get("proposalId") or ""),
                        bool(payload.get("accepted")),
                    )
                )
                return
            self.send_json({"error": "API 路径不存在"}, 404)
        except FileNotFoundError as exc:
            self.send_error_json(exc, 404)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_json(exc, 400)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local vehicle livery editing workbench")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(load_settings().get("port", 8765)))
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    ensure_directories()
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), WorkbenchHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"LIVERY_WORKBENCH_URL={url}", flush=True)
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        AGENT_BRIDGE.shutdown()


if __name__ == "__main__":
    main()
