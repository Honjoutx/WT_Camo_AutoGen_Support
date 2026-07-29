"""Project-local reference asset discovery and staging."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Union

from . import state


SUPPORTED_IMAGES = {
    ".bmp",
    ".exr",
    ".jpeg",
    ".jpg",
    ".png",
    ".psd",
    ".tga",
    ".tif",
    ".tiff",
}
DISCOVERY_ROOTS = (
    Path("assets") / "painter-library",
    Path("assets") / "livery-studio" / "generated",
    Path("assets") / "anime-liveries",
    Path("2s38"),
    Path("SMSV"),
    Path("style1"),
)
MAX_REFERENCES = 16


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def discover_images(
    project_root: Union[str, Path],
    *,
    query: str = "",
    limit: int = 500,
) -> list[Path]:
    root = state.validated_project_root(project_root)
    needle = query.strip().casefold()
    found: dict[str, Path] = {}
    for relative_root in DISCOVERY_ROOTS:
        directory = root / relative_root
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGES:
                continue
            relative = str(path.relative_to(root))
            if needle and needle not in relative.casefold():
                continue
            found[str(path.resolve()).casefold()] = path.resolve()
    ordered = sorted(
        found.values(),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return ordered[: max(1, min(int(limit), 1000))]


def stage_image_reference(
    project_root: Union[str, Path],
    source_path: Union[str, Path],
) -> Dict[str, Any]:
    root = state.validated_project_root(project_root)
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"参考素材不存在：{source}")
    if source.suffix.lower() not in SUPPORTED_IMAGES:
        raise ValueError(f"不支持的参考图片格式：{source.suffix}")

    stored = source
    imported_from = ""
    if not _inside(source, root):
        destination = root / "assets" / "painter-library" / "references"
        stored = state.versioned_path(
            destination,
            state.safe_slug(source.stem, "reference"),
            source.suffix.lower(),
        )
        shutil.copy2(str(source), str(stored))
        imported_from = str(source)

    return {
        "kind": "image",
        "name": stored.stem,
        "path": str(stored),
        "project_relative_path": str(stored.relative_to(root)),
        "imported_from": imported_from,
        "size_bytes": stored.stat().st_size,
        "added_at": datetime.now().astimezone().isoformat(),
    }


def painter_resource_reference(resource_url: str) -> Dict[str, Any]:
    # Keep discovery/staging testable outside Painter; only this adapter needs
    # the host's native resource module.
    import substance_painter.resource

    identifier = substance_painter.resource.ResourceID.from_url(resource_url)
    matches = substance_painter.resource.Resource.retrieve(identifier)
    if not matches:
        raise RuntimeError(f"Painter 中找不到资源：{resource_url}")
    resource = matches[0]
    return {
        "kind": "painter_resource",
        "name": resource.gui_name(),
        "resource_url": resource.identifier().url(),
        "resource_type": resource.type().name,
        "usages": [usage.name for usage in resource.usages()],
        "added_at": datetime.now().astimezone().isoformat(),
    }


def normalized_references(records: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in records:
        if not isinstance(candidate, dict):
            continue
        kind = str(candidate.get("kind") or "")
        if kind == "image":
            path = Path(str(candidate.get("path") or "")).expanduser()
            if not path.is_file():
                continue
            key = f"image:{str(path.resolve()).casefold()}"
            record = dict(candidate)
            record["path"] = str(path.resolve())
        elif kind == "painter_resource":
            url = str(candidate.get("resource_url") or "")
            if not url:
                continue
            key = f"resource:{url}"
            record = dict(candidate)
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        normalized.append(record)
        if len(normalized) >= MAX_REFERENCES:
            break
    return normalized
