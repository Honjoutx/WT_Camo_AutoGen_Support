from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union

import substance_painter.project
import substance_painter.resource

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
GROUP_NAME = "Camo Auto Gen"
UUID_NAMESPACE = uuid.UUID("e8d602b8-ef2a-4e8e-853b-6ba67ca043af")


def _resource_url(item) -> str:
    try:
        return item.identifier().url()
    except Exception:
        return ""


def _show_resources(items: List[Any]) -> None:
    valid = [item for item in items if item is not None]
    if not valid:
        return
    try:
        substance_painter.resource.show_resources_in_ui(valid)
        return
    except Exception:
        pass
    try:
        valid[0].show_in_ui()
    except Exception:
        pass


def import_texture_resource(
    project_root: Union[str, Path],
    image_path: Union[str, Path],
    *,
    asset_name: str = "",
    import_to_project: bool = True,
    import_to_shelf: bool = True,
    generated: bool = False,
) -> Dict[str, Any]:
    root = state.validated_project_root(project_root)
    source = Path(image_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"贴图文件不存在：{source}")
    if source.suffix.lower() not in SUPPORTED_IMAGES:
        raise ValueError(f"Painter 不支持该图片格式：{source.suffix}")
    if not import_to_project and not import_to_shelf:
        raise ValueError("至少选择当前工程或用户 Shelf 作为一个导入目标。")

    library_dir = root / "assets" / "painter-library" / "textures"
    slug = state.safe_slug(asset_name or source.stem)
    stored = state.versioned_path(library_dir, slug, source.suffix.lower())
    shutil.copy2(str(source), str(stored))
    display_name = asset_name.strip() or stored.stem

    imported = []
    warnings = []
    destinations = []
    if import_to_project:
        if substance_painter.project.is_open():
            try:
                item = substance_painter.resource.import_project_resource(
                    str(stored),
                    substance_painter.resource.Usage.TEXTURE,
                    name=display_name,
                    group=GROUP_NAME,
                )
                imported.append(item)
                destinations.append("project")
            except Exception as exc:
                warnings.append(f"当前工程导入失败：{exc}")
        else:
            warnings.append("当前没有打开 Painter 工程，已跳过工程内资源。")

    if import_to_shelf:
        try:
            shelf = substance_painter.resource.Shelves.user_shelf()
            if not shelf.can_import_resources():
                warnings.append(f"用户 Shelf 只读：{shelf.path()}")
            else:
                item = shelf.import_resource(
                    str(stored),
                    substance_painter.resource.Usage.TEXTURE,
                    name=display_name,
                    group=GROUP_NAME,
                    uuid=str(uuid.uuid5(UUID_NAMESPACE, str(stored).lower())),
                )
                imported.append(item)
                destinations.append("shelf")
                shelf.refresh()
        except Exception as exc:
            warnings.append(f"用户 Shelf 导入失败：{exc}")

    if not imported:
        details = "；".join(warnings) or "Painter 未返回资源"
        raise RuntimeError(f"资源导入失败：{details}")

    _show_resources(imported)
    record = {
        "name": display_name,
        "source": str(source),
        "stored": str(stored),
        "generated": bool(generated),
        "destinations": destinations,
        "resource_urls": [_resource_url(item) for item in imported],
        "warnings": warnings,
        "created_at": datetime.now().astimezone().isoformat(),
        "painter_project": (
            substance_painter.project.file_path()
            if substance_painter.project.is_open()
            else ""
        ),
    }
    state.append_library_record(root, record)
    return record


def show_record_resources(record: Dict[str, Any]) -> int:
    found = []
    for url in record.get("resource_urls") or []:
        if not url:
            continue
        try:
            identifier = substance_painter.resource.ResourceID.from_url(url)
            found.extend(substance_painter.resource.Resource.retrieve(identifier))
        except Exception:
            continue
    _show_resources(found)
    return len(found)
