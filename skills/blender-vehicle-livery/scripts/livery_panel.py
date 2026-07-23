import json
import os
from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

import blender_livery_core as core


_SYNCING = False
_PRESET_CACHE = {}
_PENDING_PRESET_PATHS = set()


def _project_root():
    configured = os.environ.get("CAMO_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def _default_preset_path():
    configured = os.environ.get("CAMO_DEFAULT_PRESET")
    if configured:
        return configured
    return str(_project_root() / "config" / "liveries" / "pantsyr-woodland-v1.json")


def _scene_key(scene):
    return int(scene.as_pointer())


def _preset_path(settings):
    return Path(bpy.path.abspath(settings.preset_path)).resolve()


def _linear_to_srgb(value):
    value = max(0.0, min(1.0, float(value)))
    if value <= 0.0031308:
        return value * 12.92
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def _color_to_hex(color):
    channels = [round(_linear_to_srgb(value) * 255.0) for value in color[:3]]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def _tag_viewports():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _settings_to_preset(scene):
    settings = scene.camo_livery
    preset = dict(_PRESET_CACHE.get(_scene_key(scene), {}))
    targets = [item.strip() for item in settings.target_objects.split(",") if item.strip()]
    thresholds = preset.get("thresholds", [0.0, 0.38, 0.62])
    if len(thresholds) != 3:
        thresholds = [0.0, 0.38, 0.62]
    preset.update(
        {
            "name": preset.get("name", "live-livery"),
            "material_name": settings.material_name,
            "target_objects": targets,
            "colors": [
                _color_to_hex(settings.color_1),
                _color_to_hex(settings.color_2),
                _color_to_hex(settings.color_3),
            ],
            "thresholds": thresholds,
            "pattern_scale": settings.pattern_scale,
            "noise_detail": settings.noise_detail,
            "noise_roughness": settings.noise_roughness,
            "noise_distortion": settings.noise_distortion,
            "roughness": settings.roughness,
            "metallic": settings.metallic,
            "micro_bump_strength": settings.micro_bump_strength,
            "micro_bump_scale": settings.micro_bump_scale,
        }
    )
    return preset


def _sync_settings_from_preset(scene, preset):
    global _SYNCING
    settings = scene.camo_livery
    colors = list(preset.get("colors", []))
    if len(colors) < 2:
        raise ValueError("预设至少需要两种颜色")
    while len(colors) < 3:
        colors.append(colors[-1])
    _SYNCING = True
    try:
        settings.material_name = preset.get("material_name", f"CAMO_{preset.get('name', 'Livery')}")
        settings.target_objects = ", ".join(preset.get("target_objects", []))
        settings.color_1 = core.hex_to_rgba(colors[0])[:3]
        settings.color_2 = core.hex_to_rgba(colors[1])[:3]
        settings.color_3 = core.hex_to_rgba(colors[2])[:3]
        settings.pattern_scale = float(preset.get("pattern_scale", 0.8))
        settings.noise_detail = float(preset.get("noise_detail", 3.0))
        settings.noise_roughness = float(preset.get("noise_roughness", 0.65))
        settings.noise_distortion = float(preset.get("noise_distortion", 0.1))
        settings.roughness = float(preset.get("roughness", 0.72))
        settings.metallic = float(preset.get("metallic", 0.0))
        settings.micro_bump_strength = float(preset.get("micro_bump_strength", 0.08))
        settings.micro_bump_scale = float(preset.get("micro_bump_scale", 24.0))
    finally:
        _SYNCING = False


def _set_confirmed_scope(settings, material_name, target_objects):
    settings.confirmed_material_name = material_name
    settings.confirmed_target_objects = ", ".join(target_objects)


def _confirmed_scope(settings):
    targets = [item.strip() for item in settings.confirmed_target_objects.split(",") if item.strip()]
    return settings.confirmed_material_name, targets


def _load_and_apply(scene, reason="手动重载"):
    path = _preset_path(scene.camo_livery)
    if not path.exists():
        raise FileNotFoundError(f"预设不存在: {path}")
    preset = core.load_json(path)
    _sync_settings_from_preset(scene, preset)
    material, targets = core.apply_preset_to_scene(preset)
    _set_confirmed_scope(scene.camo_livery, material.name, preset.get("target_objects", []))
    _PRESET_CACHE[_scene_key(scene)] = preset
    _PENDING_PRESET_PATHS.discard(_scene_key(scene))
    scene.camo_livery.last_mtime = path.stat().st_mtime
    scene.camo_livery.status = f"{reason}: {material.name} → {', '.join(obj.name for obj in targets)}"
    _tag_viewports()
    return material, targets


def _hot_reload(scene):
    settings = scene.camo_livery
    path = _preset_path(settings)
    if not path.exists():
        raise FileNotFoundError(f"预设不存在: {path}")
    preset = core.load_json(path)
    scene_key = _scene_key(scene)
    cached = _PRESET_CACHE.get(scene_key)
    path_change_pending = scene_key in _PENDING_PRESET_PATHS
    if cached is None and not path_change_pending:
        return _load_and_apply(scene, "热重载")

    confirmed_material, confirmed_targets = _confirmed_scope(settings)
    incoming_targets = list(preset.get("target_objects", []))
    incoming_material = preset.get("material_name", f"CAMO_{preset.get('name', 'Livery')}")
    scope_changed = incoming_targets != confirmed_targets or incoming_material != confirmed_material
    applied_preset = dict(preset)
    applied_preset["material_name"] = confirmed_material
    applied_preset["target_objects"] = confirmed_targets
    _sync_settings_from_preset(scene, applied_preset)
    material = core.update_camo_material(applied_preset)
    _PRESET_CACHE[scene_key] = applied_preset
    _PENDING_PRESET_PATHS.discard(scene_key)
    settings.last_mtime = path.stat().st_mtime
    if scope_changed:
        settings.status = "已热重载视觉参数；材质名称或目标对象变化需点击“加载并应用”确认"
    else:
        settings.status = f"热重载材质参数: {material.name}"
    _tag_viewports()
    return material, []


def _live_update(settings, context):
    if _SYNCING or not settings.live_preview or context is None or context.scene is None:
        return
    try:
        preset = _settings_to_preset(context.scene)
        confirmed_material, confirmed_targets = _confirmed_scope(settings)
        scope_pending = (
            preset.get("material_name") != confirmed_material
            or preset.get("target_objects", []) != confirmed_targets
        )
        preset["material_name"] = confirmed_material
        preset["target_objects"] = confirmed_targets
        material = core.update_camo_material(preset)
        if scope_pending:
            settings.status = f"实时视觉参数已更新: {material.name}（范围改动尚未应用）"
        else:
            settings.status = f"实时参数已更新: {material.name}（尚未写入 JSON）"
        _tag_viewports()
    except Exception as exc:
        settings.status = f"实时更新失败: {exc}"


def _preset_path_changed(settings, context):
    settings.last_mtime = 0.0
    settings.status = "预设路径已更改，等待加载"
    if context is not None and context.scene is not None:
        scene_key = _scene_key(context.scene)
        _PRESET_CACHE.pop(scene_key, None)
        _PENDING_PRESET_PATHS.add(scene_key)


class CAMO_PG_LiverySettings(PropertyGroup):
    preset_path: StringProperty(
        name="预设文件",
        subtype="FILE_PATH",
        default=_default_preset_path(),
        update=_preset_path_changed,
    )
    material_name: StringProperty(name="材质名称", default="CAMO_Pantsyr_Woodland_V1")
    target_objects: StringProperty(
        name="目标对象",
        description="以英文逗号分隔的精确对象名或 glob 模式",
        default="pantsyr_sm_sv_body_c, pantsyr_sm_sv_turret_c",
    )
    confirmed_material_name: StringProperty(
        default="CAMO_Pantsyr_Woodland_V1",
        options={"HIDDEN"},
    )
    confirmed_target_objects: StringProperty(
        default="pantsyr_sm_sv_body_c, pantsyr_sm_sv_turret_c",
        options={"HIDDEN"},
    )
    color_1: FloatVectorProperty(
        name="颜色 1",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.27, 0.23, 0.10),
        update=_live_update,
    )
    color_2: FloatVectorProperty(
        name="颜色 2",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.10, 0.13, 0.05),
        update=_live_update,
    )
    color_3: FloatVectorProperty(
        name="颜色 3",
        subtype="COLOR",
        size=3,
        min=0.0,
        max=1.0,
        default=(0.02, 0.03, 0.02),
        update=_live_update,
    )
    pattern_scale: FloatProperty(
        name="图案密度",
        min=0.02,
        max=20.0,
        default=1.45,
        update=_live_update,
    )
    noise_detail: FloatProperty(
        name="图案细节",
        min=0.0,
        max=15.0,
        default=3.0,
        update=_live_update,
    )
    noise_roughness: FloatProperty(
        name="边缘粗糙度",
        min=0.0,
        max=1.0,
        default=0.68,
        update=_live_update,
    )
    noise_distortion: FloatProperty(
        name="形状扭曲",
        min=0.0,
        max=10.0,
        default=0.12,
        update=_live_update,
    )
    roughness: FloatProperty(
        name="漆面粗糙度",
        min=0.0,
        max=1.0,
        default=0.74,
        update=_live_update,
    )
    metallic: FloatProperty(
        name="金属度",
        min=0.0,
        max=1.0,
        default=0.0,
        update=_live_update,
    )
    micro_bump_strength: FloatProperty(
        name="漆面颗粒强度",
        min=0.0,
        max=1.0,
        default=0.08,
        update=_live_update,
    )
    micro_bump_scale: FloatProperty(
        name="漆面颗粒密度",
        min=1.0,
        max=200.0,
        default=24.0,
        update=_live_update,
    )
    live_preview: BoolProperty(name="面板参数实时更新", default=True)
    auto_reload: BoolProperty(name="自动重载 JSON", default=True)
    reload_interval: FloatProperty(name="检测间隔（秒）", min=0.2, max=10.0, default=1.0)
    last_mtime: FloatProperty(default=0.0, options={"HIDDEN"})
    status: StringProperty(name="状态", default="等待预设加载")


class CAMO_OT_LoadPreset(Operator):
    bl_idname = "camo_livery.load_preset"
    bl_label = "加载并应用"
    bl_description = "从 JSON 读取参数、匹配目标对象并应用材质"

    def execute(self, context):
        try:
            _load_and_apply(context.scene, "已加载")
            return {"FINISHED"}
        except Exception as exc:
            context.scene.camo_livery.status = f"加载失败: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class CAMO_OT_ApplyControls(Operator):
    bl_idname = "camo_livery.apply_controls"
    bl_label = "应用面板参数"
    bl_description = "使用当前面板参数重新匹配目标并应用材质，不写入 JSON"

    def execute(self, context):
        try:
            preset = _settings_to_preset(context.scene)
            material, targets = core.apply_preset_to_scene(preset)
            _set_confirmed_scope(
                context.scene.camo_livery,
                material.name,
                preset.get("target_objects", []),
            )
            context.scene.camo_livery.status = (
                f"已应用: {material.name} → {', '.join(obj.name for obj in targets)}"
            )
            _tag_viewports()
            return {"FINISHED"}
        except Exception as exc:
            context.scene.camo_livery.status = f"应用失败: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class CAMO_OT_SavePreset(Operator):
    bl_idname = "camo_livery.save_preset"
    bl_label = "保存 JSON"
    bl_description = "将当前面板参数原子写回预设文件"

    def execute(self, context):
        settings = context.scene.camo_livery
        try:
            path = _preset_path(settings)
            path.parent.mkdir(parents=True, exist_ok=True)
            preset = _settings_to_preset(context.scene)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(preset, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
            _PRESET_CACHE[_scene_key(context.scene)] = preset
            settings.last_mtime = path.stat().st_mtime
            settings.status = f"已保存: {path.name}"
            return {"FINISHED"}
        except Exception as exc:
            settings.status = f"保存失败: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class CAMO_OT_SetPreviewMode(Operator):
    bl_idname = "camo_livery.set_preview_mode"
    bl_label = "切换预览模式"

    mode: StringProperty(default="MATERIAL")

    def execute(self, context):
        changed = 0
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.spaces.active.shading.type = self.mode
                    changed += 1
        context.scene.camo_livery.status = f"已切换 {changed} 个视口到 {self.mode}"
        return {"FINISHED"}


class CAMO_PT_LiveryPanel(Panel):
    bl_label = "实时车辆涂装"
    bl_idname = "CAMO_PT_vehicle_livery"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vehicle Livery"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.camo_livery

        preset_box = layout.box()
        preset_box.label(text="预设与热重载", icon="FILE_REFRESH")
        preset_box.prop(settings, "preset_path")
        row = preset_box.row(align=True)
        row.operator("camo_livery.load_preset", icon="FILE_REFRESH")
        row.operator("camo_livery.save_preset", icon="FILE_TICK")
        preset_box.prop(settings, "auto_reload")
        sub = preset_box.row()
        sub.enabled = settings.auto_reload
        sub.prop(settings, "reload_interval")

        target_box = layout.box()
        target_box.label(text="作用范围", icon="OBJECT_DATA")
        target_box.prop(settings, "material_name")
        target_box.prop(settings, "target_objects")
        target_box.operator("camo_livery.apply_controls", icon="CHECKMARK")

        color_box = layout.box()
        color_box.label(text="迷彩颜色", icon="COLOR")
        color_box.prop(settings, "color_1")
        color_box.prop(settings, "color_2")
        color_box.prop(settings, "color_3")
        color_box.prop(settings, "live_preview")

        pattern_box = layout.box()
        pattern_box.label(text="图案与漆面", icon="MATERIAL")
        pattern_box.prop(settings, "pattern_scale")
        pattern_box.prop(settings, "noise_detail")
        pattern_box.prop(settings, "noise_roughness")
        pattern_box.prop(settings, "noise_distortion")
        pattern_box.prop(settings, "roughness")
        pattern_box.prop(settings, "metallic")
        pattern_box.prop(settings, "micro_bump_strength")
        pattern_box.prop(settings, "micro_bump_scale")

        preview_box = layout.box()
        preview_box.label(text="视口", icon="SHADING_RENDERED")
        row = preview_box.row(align=True)
        material = row.operator("camo_livery.set_preview_mode", text="材质预览")
        material.mode = "MATERIAL"
        rendered = row.operator("camo_livery.set_preview_mode", text="渲染预览")
        rendered.mode = "RENDERED"

        layout.separator()
        layout.label(text=settings.status, icon="INFO")
        if len([item for item in settings.target_objects.split(",") if item.strip()]) <= 2:
            layout.label(text="注意：当前模型可能会连同轮胎/玻璃一起上色", icon="ERROR")


def _watch_presets():
    intervals = []
    for scene in bpy.data.scenes:
        settings = getattr(scene, "camo_livery", None)
        if settings is None:
            continue
        intervals.append(max(0.2, settings.reload_interval))
        if not settings.auto_reload or not settings.preset_path:
            continue
        try:
            path = _preset_path(settings)
            if not path.exists():
                settings.status = f"等待预设文件: {path.name}"
                continue
            modified = path.stat().st_mtime
            if settings.last_mtime <= 0.0 or modified > settings.last_mtime + 1e-6:
                _hot_reload(scene)
        except Exception as exc:
            settings.status = f"热重载等待中: {exc}"
    return min(intervals) if intervals else 1.0


CLASSES = (
    CAMO_PG_LiverySettings,
    CAMO_OT_LoadPreset,
    CAMO_OT_ApplyControls,
    CAMO_OT_SavePreset,
    CAMO_OT_SetPreviewMode,
    CAMO_PT_LiveryPanel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.camo_livery = PointerProperty(type=CAMO_PG_LiverySettings)
    if not bpy.app.timers.is_registered(_watch_presets):
        bpy.app.timers.register(_watch_presets, first_interval=0.5, persistent=True)
    print("Vehicle Livery panel registered")


def unregister():
    if bpy.app.timers.is_registered(_watch_presets):
        bpy.app.timers.unregister(_watch_presets)
    if hasattr(bpy.types.Scene, "camo_livery"):
        del bpy.types.Scene.camo_livery
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    _PRESET_CACHE.clear()
    _PENDING_PRESET_PATHS.clear()
    print("Vehicle Livery panel unregistered")
