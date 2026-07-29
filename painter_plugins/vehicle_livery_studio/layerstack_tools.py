"""Create editable Painter fill layers from imported livery textures."""

from __future__ import annotations

from typing import Any, Dict, Iterable

import substance_painter.layerstack
import substance_painter.project
import substance_painter.resource
import substance_painter.textureset


PROJECTION_MODES = {
    "UV": substance_painter.layerstack.ProjectionMode.UV,
    "Planar": substance_painter.layerstack.ProjectionMode.Planar,
    "Triplanar": substance_painter.layerstack.ProjectionMode.Triplanar,
    "Spherical": substance_painter.layerstack.ProjectionMode.Spherical,
    "Cylindrical": substance_painter.layerstack.ProjectionMode.Cylindrical,
}


def layerstack_available() -> bool:
    try:
        return bool(
            substance_painter.project.is_open()
            and substance_painter.project.is_in_edition_state()
        )
    except Exception:
        return False


def _resource_ids(record: Dict[str, Any]) -> Iterable:
    urls = list(record.get("resource_urls") or [])
    # Prefer the resource embedded in the project; it remains portable with the .spp.
    urls.sort(key=lambda value: 0 if "resource://project/" in str(value) else 1)
    for url in urls:
        if not url:
            continue
        try:
            yield substance_painter.resource.ResourceID.from_url(str(url))
        except Exception:
            continue


def project_texture_identifier(record: Dict[str, Any]):
    for identifier in _resource_ids(record):
        try:
            resources = substance_painter.resource.Resource.retrieve(identifier)
        except Exception:
            resources = []
        if resources:
            return resources[0].identifier()
    raise RuntimeError("找不到已导入的 Painter 贴图资源，请先重新导入当前图片。")


def create_projection_layer(
    record: Dict[str, Any],
    *,
    projection_mode: str = "Planar",
    layer_name: str = "",
) -> Dict[str, Any]:
    if not substance_painter.project.is_open():
        raise RuntimeError("请先打开一个 Painter 工程。")
    if not substance_painter.project.is_in_edition_state():
        raise RuntimeError("Painter 工程尚未进入可编辑状态，请稍后重试。")

    mode = PROJECTION_MODES.get(projection_mode)
    if mode is None:
        raise ValueError(f"不支持的投影模式：{projection_mode}")

    texture_id = project_texture_identifier(record)
    active_stack = substance_painter.textureset.get_active_stack()
    base_color = substance_painter.textureset.ChannelType.BaseColor
    display_name = layer_name.strip() or str(record.get("name") or "Livery Projection")

    with substance_painter.layerstack.ScopedModification("Create livery projection layer"):
        position = substance_painter.layerstack.InsertPosition.from_textureset_stack(
            active_stack
        )
        layer = substance_painter.layerstack.insert_fill(position)
        layer.set_name(display_name)
        layer.active_channels = {base_color}
        layer.set_source(base_color, texture_id)
        layer.set_projection_mode(mode)

    substance_painter.layerstack.set_selected_nodes([layer])
    return {
        "name": display_name,
        "projection_mode": projection_mode,
        "resource_url": texture_id.url(),
        "node_uid": layer.uid(),
        "texture_set": str(active_stack),
    }
