import json
import os
from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

import anime_livery_core as core


_SYNCING = False
_PROJECT_CACHE = {}
_PENDING_PATHS = set()


def _project_root():
    configured = os.environ.get("CAMO_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def _default_project_path():
    configured = os.environ.get("CAMO_DEFAULT_ANIME_PROJECT")
    if configured:
        return configured
    return str(_project_root() / "config" / "anime-liveries" / "pantsyr-anime-template.json")


def _scene_key(scene):
    return int(scene.as_pointer())


def _project_path(settings):
    return Path(bpy.path.abspath(settings.project_path)).resolve()


def _snapshot_text(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True)


def _tag_viewports():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _pause_base_preset_reload(scene):
    settings = getattr(scene, "camo_livery", None)
    if settings is not None:
        settings.auto_reload = False


def _cache(scene):
    return _PROJECT_CACHE.get(_scene_key(scene))


def _remove_replaced_projectors(cached, incoming):
    if cached is None:
        return
    previous_name = cached["project"].get("name")
    incoming_name = incoming.get("name")
    if previous_name and previous_name != incoming_name:
        core.remove_projectors(previous_name)


def _layers(scene):
    cached = _cache(scene)
    return cached["project"].get("layers", []) if cached else []


def _active_layer(scene):
    layers = _layers(scene)
    if not layers:
        return None
    index = max(0, min(scene.anime_livery.active_layer_index, len(layers) - 1))
    return layers[index]


def _sync_active_layer(scene, preferred_id=None):
    global _SYNCING
    settings = scene.anime_livery
    layers = _layers(scene)
    _SYNCING = True
    try:
        if not layers:
            settings.active_layer_index = 0
            settings.active_layer_name = "无图层"
            settings.layer_enabled = False
            settings.layer_opacity = 1.0
            settings.layer_surface_enabled = False
            settings.layer_roughness = 0.68
            settings.layer_metallic = 0.0
            settings.layer_coat_weight = 0.0
            settings.layer_coat_roughness = 0.03
            return
        index = max(0, min(settings.active_layer_index, len(layers) - 1))
        if preferred_id:
            index = next(
                (candidate for candidate, layer in enumerate(layers) if layer["id"] == preferred_id),
                index,
            )
        layer = layers[index]
        settings.active_layer_index = index
        settings.active_layer_name = layer.get("name", layer["id"])
        settings.layer_enabled = bool(layer.get("enabled", True))
        settings.layer_opacity = float(layer.get("opacity", 1.0))
        surface = layer.get("surface") if isinstance(layer.get("surface"), dict) else {}
        settings.layer_surface_enabled = bool(surface) and bool(surface.get("enabled", True))
        settings.layer_roughness = float(surface.get("roughness", 0.68))
        settings.layer_metallic = float(surface.get("metallic", 0.0))
        settings.layer_coat_weight = float(surface.get("coat_weight", 0.0))
        settings.layer_coat_roughness = float(surface.get("coat_roughness", 0.03))
    finally:
        _SYNCING = False


def _load_and_apply(scene, reason="已加载"):
    settings = scene.anime_livery
    path = _project_path(settings)
    incoming = core.load_project(path)
    _remove_replaced_projectors(_cache(scene), incoming)
    _pause_base_preset_reload(scene)
    result = core.apply_project(path, reload_images=True, project_data=incoming)
    _PROJECT_CACHE[_scene_key(scene)] = result
    _PENDING_PATHS.discard(_scene_key(scene))
    settings.dependency_snapshot = _snapshot_text(result["dependencies"])
    _sync_active_layer(scene)
    settings.status = (
        f"{reason}: {len(result['applied_layers'])}/{len(result['layers'])} 层 → "
        f"{', '.join(result['targets'])}"
    )
    _tag_viewports()
    return result


def _hot_reload(scene, incoming, snapshot):
    settings = scene.anime_livery
    scene_key = _scene_key(scene)
    cached = _PROJECT_CACHE.get(scene_key)
    if cached is None:
        if scene_key in _PENDING_PATHS:
            settings.status = "分层工程路径已更改；请点击“加载/重建”确认目标组"
            return None
        return _load_and_apply(scene, "初始加载")

    _pause_base_preset_reload(scene)
    active = _active_layer(scene)
    active_id = active["id"] if active else None
    confirmed_groups = cached["target_groups"]
    scope_changed = incoming.get("target_groups") != confirmed_groups
    _remove_replaced_projectors(cached, incoming)
    result = core.apply_project(
        _project_path(settings),
        target_groups_override=confirmed_groups,
        reload_images=True,
        project_data=incoming,
    )
    _PROJECT_CACHE[scene_key] = result
    settings.dependency_snapshot = _snapshot_text(snapshot)
    _sync_active_layer(scene, active_id)
    if scope_changed:
        settings.status = "已热重载图层；目标组变化需点击“加载/重建”确认"
    else:
        settings.status = f"已热重载 {len(result['applied_layers'])} 个有效图层"
    _tag_viewports()
    return result


def _rebuild_cached(scene, reason):
    settings = scene.anime_livery
    cached = _cache(scene)
    if cached is None:
        return _load_and_apply(scene, reason)
    active = _active_layer(scene)
    active_id = active["id"] if active else None
    result = core.apply_project(
        _project_path(settings),
        target_groups_override=cached["target_groups"],
        reload_images=False,
        project_data=cached["project"],
    )
    _PROJECT_CACHE[_scene_key(scene)] = result
    _sync_active_layer(scene, active_id)
    settings.status = reason
    _tag_viewports()
    return result


def _project_path_changed(settings, context):
    settings.dependency_snapshot = ""
    settings.status = "分层工程路径已更改，等待确认"
    if context is not None and context.scene is not None:
        _PENDING_PATHS.add(_scene_key(context.scene))


def _active_layer_changed(settings, context):
    if _SYNCING or context is None or context.scene is None:
        return
    _sync_active_layer(context.scene)


def _layer_opacity_changed(settings, context):
    if _SYNCING or context is None or context.scene is None:
        return
    cached = _cache(context.scene)
    if cached is None:
        return
    layer, materials = core.update_layer_controls(
        cached["project"],
        settings.active_layer_index,
        opacity=settings.layer_opacity,
    )
    settings.status = f"实时透明度: {layer.get('name', layer['id'])} → {len(materials)} 个材质"
    _tag_viewports()


def _layer_enabled_changed(settings, context):
    if _SYNCING or context is None or context.scene is None:
        return
    cached = _cache(context.scene)
    if cached is None:
        return
    core.update_layer_controls(
        cached["project"],
        settings.active_layer_index,
        enabled=settings.layer_enabled,
    )
    try:
        _rebuild_cached(context.scene, "已更新图层启用状态（尚未保存 JSON）")
    except Exception as exc:
        settings.status = f"图层重建失败: {exc}"


def _layer_surface_values_changed(settings, context):
    if _SYNCING or context is None or context.scene is None:
        return
    cached = _cache(context.scene)
    if cached is None or not settings.layer_surface_enabled:
        return
    layer, materials = core.update_layer_surface_controls(
        cached["project"],
        settings.active_layer_index,
        roughness=settings.layer_roughness,
        metallic=settings.layer_metallic,
        coat_weight=settings.layer_coat_weight,
        coat_roughness=settings.layer_coat_roughness,
    )
    settings.status = f"实时材质参数: {layer.get('name', layer['id'])} → {len(materials)} 个材质"
    _tag_viewports()


def _layer_surface_enabled_changed(settings, context):
    if _SYNCING or context is None or context.scene is None:
        return
    cached = _cache(context.scene)
    if cached is None:
        return
    core.update_layer_surface_controls(
        cached["project"],
        settings.active_layer_index,
        surface_enabled=settings.layer_surface_enabled,
        roughness=settings.layer_roughness,
        metallic=settings.layer_metallic,
        coat_weight=settings.layer_coat_weight,
        coat_roughness=settings.layer_coat_roughness,
    )
    try:
        state = "启用" if settings.layer_surface_enabled else "停用"
        _rebuild_cached(context.scene, f"已{state}当前图层材质块（尚未保存 JSON）")
    except Exception as exc:
        settings.status = f"材质块重建失败: {exc}"


class ANIME_PG_LiverySettings(PropertyGroup):
    project_path: StringProperty(
        name="分层工程",
        subtype="FILE_PATH",
        default=_default_project_path(),
        update=_project_path_changed,
    )
    auto_reload: BoolProperty(name="自动热重载工程与图片", default=True)
    reload_interval: FloatProperty(name="检测间隔（秒）", min=0.2, max=10.0, default=1.0)
    active_layer_index: IntProperty(
        name="活动图层",
        min=0,
        default=0,
        update=_active_layer_changed,
    )
    active_layer_name: StringProperty(default="无图层", options={"HIDDEN"})
    layer_enabled: BoolProperty(name="启用当前图层", default=True, update=_layer_enabled_changed)
    layer_opacity: FloatProperty(
        name="图层透明度",
        min=0.0,
        max=1.0,
        default=1.0,
        update=_layer_opacity_changed,
    )
    layer_surface_enabled: BoolProperty(
        name="启用独立材质块",
        default=False,
        update=_layer_surface_enabled_changed,
    )
    layer_roughness: FloatProperty(
        name="粗糙度",
        min=0.0,
        max=1.0,
        default=0.68,
        update=_layer_surface_values_changed,
    )
    layer_metallic: FloatProperty(
        name="金属度",
        min=0.0,
        max=1.0,
        default=0.0,
        update=_layer_surface_values_changed,
    )
    layer_coat_weight: FloatProperty(
        name="清漆强度",
        min=0.0,
        max=1.0,
        default=0.0,
        update=_layer_surface_values_changed,
    )
    layer_coat_roughness: FloatProperty(
        name="清漆粗糙度",
        min=0.0,
        max=1.0,
        default=0.03,
        update=_layer_surface_values_changed,
    )
    dependency_snapshot: StringProperty(default="", options={"HIDDEN"})
    status: StringProperty(name="状态", default="等待分层工程加载")


class ANIME_OT_LoadProject(Operator):
    bl_idname = "anime_livery.load_project"
    bl_label = "加载/重建"
    bl_description = "确认目标组并从 JSON 重建全部分层投射材质"

    def execute(self, context):
        try:
            _load_and_apply(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.anime_livery.status = f"加载失败: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class ANIME_OT_SaveProject(Operator):
    bl_idname = "anime_livery.save_project"
    bl_label = "保存工程"
    bl_description = "采集全部投射器变换并原子写回分层 JSON"

    def execute(self, context):
        settings = context.scene.anime_livery
        cached = _cache(context.scene)
        if cached is None:
            self.report({"ERROR"}, "请先加载分层工程")
            return {"CANCELLED"}
        try:
            project = core.sync_projectors_to_project(cached["project"])
            path = core.save_project(_project_path(settings), project)
            cached["dependencies"] = core.dependency_snapshot(path, project)
            settings.dependency_snapshot = _snapshot_text(cached["dependencies"])
            _PENDING_PATHS.discard(_scene_key(context.scene))
            settings.status = f"已保存工程与投射器: {path.name}"
            return {"FINISHED"}
        except Exception as exc:
            settings.status = f"保存失败: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class ANIME_OT_StepLayer(Operator):
    bl_idname = "anime_livery.step_layer"
    bl_label = "切换图层"

    delta: IntProperty(default=1)

    def execute(self, context):
        layers = _layers(context.scene)
        if not layers:
            return {"CANCELLED"}
        settings = context.scene.anime_livery
        settings.active_layer_index = (settings.active_layer_index + self.delta) % len(layers)
        return {"FINISHED"}


class ANIME_OT_SelectProjector(Operator):
    bl_idname = "anime_livery.select_projector"
    bl_label = "选择投射器"
    bl_description = "选择当前图层的投射器；使用 G/R/S 可实时移动、旋转和缩放贴图"

    def execute(self, context):
        cached = _cache(context.scene)
        layer = _active_layer(context.scene)
        if cached is None or layer is None:
            return {"CANCELLED"}
        projector = bpy.data.objects.get(core.projector_name(cached["project"]["name"], layer["id"]))
        if projector is None:
            context.scene.anime_livery.status = "当前图层未启用或尚未生成投射器"
            return {"CANCELLED"}
        bpy.ops.object.select_all(action="DESELECT")
        projector.hide_set(False)
        projector.select_set(True)
        context.view_layer.objects.active = projector
        context.scene.anime_livery.status = f"已选择投射器: {projector.name}；使用 G/R/S 调整"
        return {"FINISHED"}


class ANIME_PT_LayerPanel(Panel):
    bl_label = "二次元分层投射"
    bl_idname = "ANIME_PT_vehicle_livery_layers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vehicle Livery"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.anime_livery
        cached = _cache(context.scene)
        layers = _layers(context.scene)

        project_box = layout.box()
        project_box.label(text="涂装工程", icon="NODETREE")
        project_box.prop(settings, "project_path")
        row = project_box.row(align=True)
        row.operator("anime_livery.load_project", icon="FILE_REFRESH")
        row.operator("anime_livery.save_project", icon="FILE_TICK")
        project_box.prop(settings, "auto_reload")
        interval = project_box.row()
        interval.enabled = settings.auto_reload
        interval.prop(settings, "reload_interval")

        layer_box = layout.box()
        layer_box.label(text="逐层设计", icon="RENDERLAYERS")
        if layers:
            row = layer_box.row(align=True)
            previous = row.operator("anime_livery.step_layer", text="上一层", icon="TRIA_LEFT")
            previous.delta = -1
            row.label(text=f"{settings.active_layer_index + 1}/{len(layers)}")
            following = row.operator("anime_livery.step_layer", text="下一层", icon="TRIA_RIGHT")
            following.delta = 1
            layer_box.label(text=settings.active_layer_name)
            layer_box.prop(settings, "layer_enabled")
            layer_box.prop(settings, "layer_opacity")
            surface_box = layer_box.box()
            surface_box.label(text="图层材质块", icon="MATERIAL")
            surface_box.prop(settings, "layer_surface_enabled")
            surface_controls = surface_box.column(align=True)
            surface_controls.enabled = settings.layer_surface_enabled
            surface_controls.prop(settings, "layer_roughness", slider=True)
            surface_controls.prop(settings, "layer_metallic", slider=True)
            surface_controls.prop(settings, "layer_coat_weight", slider=True)
            surface_controls.prop(settings, "layer_coat_roughness", slider=True)
            layer_box.operator("anime_livery.select_projector", icon="EMPTY_AXIS")
            layer = _active_layer(context.scene)
            if layer:
                layer_box.label(text="目标: " + ", ".join(layer.get("targets", [])))
                layer_box.label(text=Path(layer.get("image", "")).name or "未指定图片")
        else:
            layer_box.label(text="请先加载分层工程")

        help_box = layout.box()
        help_box.label(text="定向贴图操作", icon="INFO")
        help_box.label(text="1. 选择图层与投射器")
        help_box.label(text="2. 用 G/R/S 调整位置、方向、尺寸")
        help_box.label(text="3. 满意后保存工程")
        if cached and cached.get("warnings"):
            help_box.label(text=cached["warnings"][0], icon="ERROR")

        layout.separator()
        layout.label(text=settings.status, icon="INFO")


def _watch_projects():
    intervals = []
    for scene in bpy.data.scenes:
        settings = getattr(scene, "anime_livery", None)
        if settings is None:
            continue
        intervals.append(max(0.2, settings.reload_interval))
        if not settings.auto_reload or not settings.project_path:
            continue
        try:
            path = _project_path(settings)
            if not path.exists():
                settings.status = f"等待分层工程: {path.name}"
                continue
            incoming = core.load_project(path)
            snapshot = core.dependency_snapshot(path, incoming)
            if _snapshot_text(snapshot) != settings.dependency_snapshot:
                _hot_reload(scene, incoming, snapshot)
        except Exception as exc:
            settings.status = f"分层热重载等待中: {exc}"
    return min(intervals) if intervals else 1.0


CLASSES = (
    ANIME_PG_LiverySettings,
    ANIME_OT_LoadProject,
    ANIME_OT_SaveProject,
    ANIME_OT_StepLayer,
    ANIME_OT_SelectProjector,
    ANIME_PT_LayerPanel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.anime_livery = PointerProperty(type=ANIME_PG_LiverySettings)
    if not bpy.app.timers.is_registered(_watch_projects):
        bpy.app.timers.register(_watch_projects, first_interval=0.75, persistent=True)
    print("Anime livery layer panel registered")


def unregister():
    if bpy.app.timers.is_registered(_watch_projects):
        bpy.app.timers.unregister(_watch_projects)
    if hasattr(bpy.types.Scene, "anime_livery"):
        del bpy.types.Scene.anime_livery
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _PROJECT_CACHE.clear()
    _PENDING_PATHS.clear()
    print("Anime livery layer panel unregistered")
