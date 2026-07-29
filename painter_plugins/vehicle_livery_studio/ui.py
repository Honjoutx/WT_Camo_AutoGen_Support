from __future__ import annotations

import html
from pathlib import Path
from typing import Dict, Optional

import substance_painter.application
import substance_painter.project
import substance_painter.textureset
import substance_painter.ui

from . import capture, layerstack_tools, reference_assets, resources, state
from .agent_client import AgentController, find_asset_marker
from .reference_widgets import AssetLibraryList, ReferenceDropList
from .qt import (
    ALIGN_CENTER,
    KEEP_ASPECT_RATIO,
    SMOOTH_TRANSFORMATION,
    QtCore,
    QtGui,
    QtWidgets,
)


DEFAULT_PROMPT = (
    "根据当前 Painter 截图与框选区域，分析模型表面结构并生成适合该边界的二次元涂装素材。"
    "主体和文字不得越出安全边界；构图应适合从当前视角进行 Planar Projection。"
)


def _resolution_pair(value) -> list[int]:
    if hasattr(value, "width") and hasattr(value, "height"):
        width = value.width() if callable(value.width) else value.width
        height = value.height() if callable(value.height) else value.height
        return [int(width), int(height)]
    try:
        return [int(value[0]), int(value[1])]
    except Exception:
        return []


def painter_context() -> Dict:
    result = {
        "application": "Adobe Substance 3D Painter",
        "version": substance_painter.application.version(),
        "version_info": list(substance_painter.application.version_info()),
        "project_open": False,
        "project_path": "",
        "mesh_path": "",
        "texture_sets": [],
        "active_stack": "",
        "layerstack_api": True,
    }
    try:
        result["project_open"] = bool(substance_painter.project.is_open())
    except Exception:
        return result
    if not result["project_open"]:
        return result
    try:
        result["project_path"] = substance_painter.project.file_path()
    except Exception:
        pass
    try:
        result["mesh_path"] = substance_painter.project.last_imported_mesh_path()
    except Exception:
        pass
    try:
        for texture_set in substance_painter.textureset.all_texture_sets():
            result["texture_sets"].append(
                {
                    "name": texture_set.name(),
                    "resolution": _resolution_pair(texture_set.get_resolution()),
                    "uv_tiles": bool(texture_set.has_uv_tiles()),
                }
            )
    except Exception:
        pass
    try:
        result["active_stack"] = str(
            substance_painter.textureset.get_active_stack()
        )
    except Exception:
        pass
    return result


class LiveryStudioWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vehicle Livery Agent")
        self.setObjectName("CamoAutoGenVehicleLiveryWidget")
        self._dock = None
        self._capture_session: Optional[Dict] = None
        self._pending_approval = ""
        self._last_resource: Dict = {}
        self._reference_assets: list[Dict] = []

        discovered = state.find_project_root()
        if discovered is None:
            raise FileNotFoundError("未找到 Camo_Auto_Gen 项目目录。")
        self._settings = state.load_settings(discovered)
        self._agent = AgentController(
            discovered,
            str(self._settings.get("agent_url") or "http://127.0.0.1:8766"),
            self,
        )
        self._agent.event.connect(self._on_agent_event)
        self._build_ui()
        self._load_values()
        QtCore.QTimer.singleShot(650, self._connect_agent)

    def set_dock_widget(self, dock) -> None:
        self._dock = dock

    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QtWidgets.QWidget(scroll)
        self.body_layout = QtWidgets.QVBoxLayout(body)
        self.body_layout.setContentsMargins(6, 6, 6, 8)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        header = QtWidgets.QLabel("Painter 原生 Agent · 截图框选 · 投影图层")
        header_font = header.font()
        header_font.setBold(True)
        header_font.setPointSize(header_font.pointSize() + 1)
        header.setFont(header_font)
        self.body_layout.addWidget(header)
        version = substance_painter.application.version()
        self.body_layout.addWidget(
            QtWidgets.QLabel(f"当前 Painter：{version} / PySide6 / Layer Stack API")
        )

        self._build_project_group()
        self._build_capture_group()
        self._build_reference_group()
        self._build_agent_group()
        self._build_resource_group()
        self.body_layout.addStretch(1)

    def _build_project_group(self) -> None:
        group = QtWidgets.QGroupBox("项目与 Agent 服务")
        layout = QtWidgets.QGridLayout(group)
        self.project_root_edit = QtWidgets.QLineEdit()
        layout.addWidget(self.project_root_edit, 0, 0, 1, 2)
        detect_button = QtWidgets.QPushButton("自动定位")
        detect_button.clicked.connect(self._detect_root)
        browse_button = QtWidgets.QPushButton("选择目录")
        browse_button.clicked.connect(self._browse_root)
        layout.addWidget(detect_button, 1, 0)
        layout.addWidget(browse_button, 1, 1)
        self.agent_url_edit = QtWidgets.QLineEdit()
        layout.addWidget(QtWidgets.QLabel("Agent 地址"), 2, 0)
        layout.addWidget(self.agent_url_edit, 2, 1)
        connect_button = QtWidgets.QPushButton("连接 Agent")
        connect_button.clicked.connect(self._connect_agent)
        stop_button = QtWidgets.QPushButton("停止本插件服务")
        stop_button.clicked.connect(self._stop_service)
        layout.addWidget(connect_button, 3, 0)
        layout.addWidget(stop_button, 3, 1)
        self.body_layout.addWidget(group)

    def _build_capture_group(self) -> None:
        group = QtWidgets.QGroupBox("1. 截图并框选模型表面")
        layout = QtWidgets.QVBoxLayout(group)
        info = QtWidgets.QLabel(
            "先在 3D 视口转到目标角度，再框选需要设计的表面。"
            "框选截图将作为 Agent 的结构与边界参考。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        button = QtWidgets.QPushButton("截图并框选设计区域")
        button.clicked.connect(self._capture_region)
        layout.addWidget(button)
        self.capture_preview = QtWidgets.QLabel("尚未框选")
        self.capture_preview.setAlignment(ALIGN_CENTER)
        self.capture_preview.setMinimumHeight(120)
        self.capture_preview.setStyleSheet("border: 1px solid #555;")
        layout.addWidget(self.capture_preview)
        self.capture_path_label = QtWidgets.QLabel("")
        self.capture_path_label.setWordWrap(True)
        layout.addWidget(self.capture_path_label)
        self.body_layout.addWidget(group)

    def _build_reference_group(self) -> None:
        group = QtWidgets.QGroupBox("2. 参考素材库（拖拽给 Agent）")
        layout = QtWidgets.QVBoxLayout(group)

        info = QtWidgets.QLabel(
            "从项目素材库拖到下方参考区。参考素材只帮助 Agent 理解角色、"
            "色彩、纹理和版式，不会自动覆盖当前贴图。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        search_row = QtWidgets.QHBoxLayout()
        self.reference_search_edit = QtWidgets.QLineEdit()
        self.reference_search_edit.setPlaceholderText("搜索项目图片素材")
        self.reference_search_edit.returnPressed.connect(
            self._refresh_reference_library
        )
        refresh_button = QtWidgets.QPushButton("刷新素材库")
        refresh_button.clicked.connect(self._refresh_reference_library)
        search_row.addWidget(self.reference_search_edit, 1)
        search_row.addWidget(refresh_button)
        layout.addLayout(search_row)

        self.asset_library_list = AssetLibraryList(self)
        self.asset_library_list.activated_path.connect(
            lambda path: self._add_reference_files([path])
        )
        layout.addWidget(self.asset_library_list)

        drop_label = QtWidgets.QLabel(
            "拖到这里作为 Agent 参考（最多 16 项，也接受资源管理器图片和 Painter Assets）"
        )
        drop_label.setWordWrap(True)
        layout.addWidget(drop_label)
        self.reference_drop_list = ReferenceDropList(self)
        self.reference_drop_list.files_dropped.connect(
            self._add_reference_files
        )
        self.reference_drop_list.resources_dropped.connect(
            self._add_reference_resources
        )
        self.reference_drop_list.drop_diagnostic.connect(
            self._reference_drop_diagnostic
        )
        layout.addWidget(self.reference_drop_list)

        action_row = QtWidgets.QHBoxLayout()
        add_button = QtWidgets.QPushButton("添加图片")
        add_button.clicked.connect(self._browse_reference_files)
        remove_button = QtWidgets.QPushButton("移除所选")
        remove_button.clicked.connect(self._remove_selected_references)
        clear_button = QtWidgets.QPushButton("清空参考")
        clear_button.clicked.connect(self._clear_references)
        action_row.addWidget(add_button)
        action_row.addWidget(remove_button)
        action_row.addWidget(clear_button)
        layout.addLayout(action_row)

        self.reference_status = QtWidgets.QLabel("尚未添加参考素材")
        self.reference_status.setWordWrap(True)
        layout.addWidget(self.reference_status)
        self.body_layout.addWidget(group)

    def _build_agent_group(self) -> None:
        group = QtWidgets.QGroupBox("3. Agent + Skill")
        layout = QtWidgets.QVBoxLayout(group)
        self.prompt_edit = QtWidgets.QPlainTextEdit()
        self.prompt_edit.setMinimumHeight(90)
        layout.addWidget(self.prompt_edit)
        actions = QtWidgets.QHBoxLayout()
        send_button = QtWidgets.QPushButton("发送")
        send_button.clicked.connect(self._send_agent)
        interrupt_button = QtWidgets.QPushButton("停止任务")
        interrupt_button.clicked.connect(self._interrupt_agent)
        reset_button = QtWidgets.QPushButton("新会话")
        reset_button.clicked.connect(self._reset_agent)
        actions.addWidget(send_button)
        actions.addWidget(interrupt_button)
        actions.addWidget(reset_button)
        layout.addLayout(actions)
        self.agent_status = QtWidgets.QLabel("正在等待本地 Agent")
        self.agent_status.setWordWrap(True)
        layout.addWidget(self.agent_status)

        self.approval_group = QtWidgets.QGroupBox("Agent 请求审批")
        approval_layout = QtWidgets.QVBoxLayout(self.approval_group)
        self.approval_title = QtWidgets.QLabel("")
        self.approval_title.setWordWrap(True)
        self.approval_reason = QtWidgets.QLabel("")
        self.approval_reason.setWordWrap(True)
        self.approval_command = QtWidgets.QPlainTextEdit()
        self.approval_command.setReadOnly(True)
        self.approval_command.setMaximumHeight(100)
        approval_layout.addWidget(self.approval_title)
        approval_layout.addWidget(self.approval_reason)
        approval_layout.addWidget(self.approval_command)
        approval_actions = QtWidgets.QHBoxLayout()
        approve_button = QtWidgets.QPushButton("允许本次")
        approve_button.clicked.connect(
            lambda: self._respond_approval("accept")
        )
        decline_button = QtWidgets.QPushButton("拒绝")
        decline_button.clicked.connect(
            lambda: self._respond_approval("decline")
        )
        approval_actions.addWidget(approve_button)
        approval_actions.addWidget(decline_button)
        approval_layout.addLayout(approval_actions)
        self.approval_group.setVisible(False)
        layout.addWidget(self.approval_group)

        self.transcript = QtWidgets.QTextBrowser()
        self.transcript.setMinimumHeight(180)
        self.transcript.setOpenExternalLinks(False)
        layout.addWidget(self.transcript)
        self.body_layout.addWidget(group)

    def _build_resource_group(self) -> None:
        group = QtWidgets.QGroupBox("4. 资源入库与 Painter 投影图层")
        layout = QtWidgets.QGridLayout(group)
        self.image_path_edit = QtWidgets.QLineEdit()
        browse_button = QtWidgets.QPushButton("选择贴图")
        browse_button.clicked.connect(self._browse_image)
        layout.addWidget(self.image_path_edit, 0, 0)
        layout.addWidget(browse_button, 0, 1)
        self.asset_name_edit = QtWidgets.QLineEdit()
        self.asset_name_edit.setPlaceholderText("图层/资源名称（留空使用文件名）")
        layout.addWidget(self.asset_name_edit, 1, 0, 1, 2)

        self.import_project_check = QtWidgets.QCheckBox("嵌入当前 .spp 工程")
        self.import_shelf_check = QtWidgets.QCheckBox("加入用户 Assets / Shelf")
        self.auto_import_check = QtWidgets.QCheckBox("Agent 完成后自动入库")
        self.auto_layer_check = QtWidgets.QCheckBox("入库后自动创建投影 Fill 图层")
        layout.addWidget(self.import_project_check, 2, 0, 1, 2)
        layout.addWidget(self.import_shelf_check, 3, 0, 1, 2)
        layout.addWidget(self.auto_import_check, 4, 0, 1, 2)
        layout.addWidget(self.auto_layer_check, 5, 0, 1, 2)

        layout.addWidget(QtWidgets.QLabel("投影模式"), 6, 0)
        self.projection_combo = QtWidgets.QComboBox()
        self.projection_combo.addItems(list(layerstack_tools.PROJECTION_MODES))
        layout.addWidget(self.projection_combo, 6, 1)

        import_button = QtWidgets.QPushButton("导入当前图片")
        import_button.clicked.connect(self._import_current_image)
        create_button = QtWidgets.QPushButton("为当前资源创建投影图层")
        create_button.clicked.connect(self._create_layer)
        reveal_button = QtWidgets.QPushButton("在 Assets 中显示最近资源")
        reveal_button.clicked.connect(self._reveal_last_resource)
        layout.addWidget(import_button, 7, 0, 1, 2)
        layout.addWidget(create_button, 8, 0, 1, 2)
        layout.addWidget(reveal_button, 9, 0, 1, 2)

        self.resource_status = QtWidgets.QLabel("")
        self.resource_status.setWordWrap(True)
        layout.addWidget(self.resource_status, 10, 0, 1, 2)
        note = QtWidgets.QLabel(
            "Planar 适合按当前视角贴角色海报；UV 适合已有明确 UV 版面；"
            "Triplanar 适合连续材质纹理。创建后可在 Painter 属性面板继续调整投影框。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #9fc7d8;")
        layout.addWidget(note, 11, 0, 1, 2)
        self.body_layout.addWidget(group)

    def _load_values(self) -> None:
        values = self._settings
        self.project_root_edit.setText(str(values.get("project_root") or ""))
        self.agent_url_edit.setText(
            str(values.get("agent_url") or "http://127.0.0.1:8766")
        )
        self.prompt_edit.setPlainText(str(values.get("prompt") or DEFAULT_PROMPT))
        self.image_path_edit.setText(str(values.get("image_path") or ""))
        self.asset_name_edit.setText(str(values.get("asset_name") or ""))
        self.auto_import_check.setChecked(bool(values.get("auto_import", True)))
        self.auto_layer_check.setChecked(
            bool(values.get("auto_create_layer", True))
        )
        self.import_project_check.setChecked(
            bool(values.get("import_project", True))
        )
        self.import_shelf_check.setChecked(bool(values.get("import_shelf", True)))
        mode = str(values.get("projection_mode") or "Planar")
        index = self.projection_combo.findText(mode)
        self.projection_combo.setCurrentIndex(max(0, index))
        self._last_resource = dict(values.get("last_resource") or {})
        self._reference_assets = reference_assets.normalized_references(
            values.get("reference_assets") or []
        )
        self._render_reference_assets()
        self._refresh_reference_library()
        capture_path = str(values.get("last_capture") or "")
        if capture_path and Path(capture_path).is_file():
            self._set_capture_preview(Path(capture_path))

    def _current_settings(self) -> Dict:
        return {
            "project_root": self.project_root_edit.text().strip(),
            "agent_url": self.agent_url_edit.text().strip(),
            "prompt": self.prompt_edit.toPlainText(),
            "image_path": self.image_path_edit.text().strip(),
            "asset_name": self.asset_name_edit.text().strip(),
            "auto_import": self.auto_import_check.isChecked(),
            "auto_create_layer": self.auto_layer_check.isChecked(),
            "projection_mode": self.projection_combo.currentText(),
            "import_project": self.import_project_check.isChecked(),
            "import_shelf": self.import_shelf_check.isChecked(),
            "last_capture": (
                str(self._capture_session.get("selected_capture"))
                if self._capture_session
                else str(self._settings.get("last_capture") or "")
            ),
            "last_resource": self._last_resource,
            "reference_assets": self._reference_assets,
        }

    def _root(self) -> Path:
        return state.validated_project_root(self.project_root_edit.text().strip())

    def _save(self) -> None:
        self._settings = self._current_settings()
        state.save_settings(self._root(), self._settings)

    def _configure_agent(self) -> None:
        self._agent.configure(
            self._root(),
            self.agent_url_edit.text().strip(),
        )

    def _detect_root(self) -> None:
        discovered = state.find_project_root()
        if discovered is None:
            self._error("未自动找到 Camo_Auto_Gen 项目。")
            return
        self.project_root_edit.setText(str(discovered))
        self._set_status(f"项目目录：{discovered}")
        self._refresh_reference_library()
        self._save()

    def _browse_root(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "选择 Camo_Auto_Gen 项目目录",
            self.project_root_edit.text(),
        )
        if not selected:
            return
        try:
            root = state.validated_project_root(selected)
        except Exception as exc:
            self._error(str(exc))
            return
        self.project_root_edit.setText(str(root))
        self._refresh_reference_library()
        self._save()

    def _connect_agent(self) -> None:
        try:
            self._configure_agent()
            self._save()
            self._agent.start_service()
        except Exception as exc:
            self._error(str(exc))

    def _stop_service(self) -> None:
        if not self._agent.stop_service():
            self._set_status("当前服务不是由本插件启动，未停止外部 Agent 服务。")

    def _capture_region(self) -> None:
        try:
            root = self._root()
            main_window = substance_painter.ui.get_main_window()
            dock_was_visible = bool(self._dock and self._dock.isVisible())
            if dock_was_visible:
                self._dock.hide()
                QtWidgets.QApplication.processEvents()
            image = capture.grab_main_window(main_window)
            if dock_was_visible:
                self._dock.show()
                QtWidgets.QApplication.processEvents()
            session = capture.select_image_and_save(
                image,
                main_window,
                root,
                painter_context(),
            )
            if not session:
                return
            self._capture_session = session
            selected = Path(session["selected_capture"])
            self._set_capture_preview(selected)
            self.capture_path_label.setText(str(selected))
            self._settings["last_capture"] = str(selected)
            self._save()
            self._set_status(
                f"已框选 {session['selection_size_px'][0]} × "
                f"{session['selection_size_px'][1]} px"
            )
        except Exception as exc:
            if self._dock:
                self._dock.show()
            self._error(str(exc))

    def _set_capture_preview(self, path: Path) -> None:
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            return
        self.capture_preview.setPixmap(
            pixmap.scaled(
                430,
                210,
                KEEP_ASPECT_RATIO,
                SMOOTH_TRANSFORMATION,
            )
        )
        self.capture_preview.setText("")

    @staticmethod
    def _reference_key(record: Dict) -> str:
        if record.get("kind") == "image":
            return f"image:{str(record.get('path') or '').casefold()}"
        return f"resource:{record.get('resource_url') or ''}"

    def _refresh_reference_library(self) -> None:
        try:
            paths = reference_assets.discover_images(
                self._root(),
                query=self.reference_search_edit.text(),
                limit=500,
            )
            self.asset_library_list.set_paths(paths, self._root())
            self.reference_status.setText(
                f"素材库显示 {len(paths)} 项；Agent 参考 "
                f"{len(self._reference_assets)}/{reference_assets.MAX_REFERENCES} 项"
            )
        except Exception as exc:
            self.reference_status.setText(f"素材库刷新失败：{exc}")

    def _render_reference_assets(self) -> None:
        self._reference_assets = reference_assets.normalized_references(
            self._reference_assets
        )
        self.reference_drop_list.set_records(self._reference_assets)
        self.reference_status.setText(
            f"Agent 参考 {len(self._reference_assets)}/"
            f"{reference_assets.MAX_REFERENCES} 项"
        )

    def _browse_reference_files(self) -> None:
        selected, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择 Agent 参考图片",
            str(self._root()),
            "图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.tga *.exr *.psd)",
        )
        if selected:
            self._add_reference_files(selected)

    def _add_reference_files(self, paths) -> None:
        existing = {
            self._reference_key(record) for record in self._reference_assets
        }
        added = 0
        errors: list[str] = []
        for path in paths:
            if len(self._reference_assets) >= reference_assets.MAX_REFERENCES:
                errors.append(
                    f"参考素材最多 {reference_assets.MAX_REFERENCES} 项"
                )
                break
            try:
                record = reference_assets.stage_image_reference(
                    self._root(),
                    path,
                )
            except Exception as exc:
                errors.append(str(exc))
                continue
            key = self._reference_key(record)
            if key in existing:
                continue
            existing.add(key)
            self._reference_assets.append(record)
            added += 1
        self._render_reference_assets()
        self._refresh_reference_library()
        self._save()
        if errors:
            self.reference_status.setText(
                f"已添加 {added} 项；" + "；".join(errors[:3])
            )
        elif added:
            self.reference_status.setText(
                f"已添加 {added} 项；发送时会作为视觉参考交给 Agent"
            )
        else:
            self.reference_status.setText("所选素材已在参考区中")

    def _add_reference_resources(self, resource_urls) -> None:
        existing = {
            self._reference_key(record) for record in self._reference_assets
        }
        added = 0
        errors: list[str] = []
        for resource_url in resource_urls:
            if len(self._reference_assets) >= reference_assets.MAX_REFERENCES:
                errors.append(
                    f"参考素材最多 {reference_assets.MAX_REFERENCES} 项"
                )
                break
            try:
                record = reference_assets.painter_resource_reference(
                    str(resource_url)
                )
            except Exception as exc:
                errors.append(str(exc))
                continue
            key = self._reference_key(record)
            if key in existing:
                continue
            existing.add(key)
            self._reference_assets.append(record)
            added += 1
        self._render_reference_assets()
        self._save()
        if errors:
            self.reference_status.setText(
                f"已添加 {added} 项 Painter 资源；" + "；".join(errors[:3])
            )
        elif added:
            self.reference_status.setText(
                f"已添加 {added} 项 Painter 资源元数据参考"
            )
        else:
            self.reference_status.setText("该 Painter 资源已在参考区中")

    def _reference_drop_diagnostic(self, message: str) -> None:
        self.reference_status.setText(message)

    def _remove_selected_references(self) -> None:
        selected = self.reference_drop_list.selected_record_keys()
        if not selected:
            self.reference_status.setText("请先选择要移除的参考素材")
            return
        before = len(self._reference_assets)
        self._reference_assets = [
            record
            for record in self._reference_assets
            if self._reference_key(record) not in selected
        ]
        self._render_reference_assets()
        self._save()
        self.reference_status.setText(
            f"已移除 {before - len(self._reference_assets)} 项参考素材"
        )

    def _clear_references(self) -> None:
        removed = len(self._reference_assets)
        self._reference_assets = []
        self._render_reference_assets()
        self._save()
        self.reference_status.setText(f"已清空 {removed} 项参考素材")

    def _agent_context(self) -> Dict:
        root = self._root()
        current = painter_context()
        capture_record = self._capture_session or {}
        input_path = Path(self.image_path_edit.text()).expanduser()
        input_asset = str(input_path.resolve()) if input_path.is_file() else ""
        request_id = capture_record.get("id") or state.timestamp_id("painter-asset")
        selection_size = capture_record.get("selection_size_px") or [1, 1]
        aspect = max(1.0, float(selection_size[0])) / max(
            1.0,
            float(selection_size[1]),
        )
        return {
            "source": "substance-painter-livery-studio",
            "project_root": str(root),
            "painter": current,
            "capture_session": capture_record,
            "input_asset": input_asset,
            "reference_assets": [
                dict(record) for record in self._reference_assets
            ],
            "reference_asset_policy": {
                "purpose": "visual-style-and-content-reference",
                "count": len(self._reference_assets),
                "instructions": [
                    (
                        "Inspect accessible image paths for identity, palette, "
                        "motifs, texture language, and composition."
                    ),
                    (
                        "Treat these records as references only; do not use one "
                        "as the output or apply it unless the user explicitly asks."
                    ),
                    (
                        "A painter_resource record exposes metadata only unless "
                        "a project-local image path is also present."
                    ),
                ],
            },
            "resource_targets": {
                "project": self.import_project_check.isChecked(),
                "user_shelf": self.import_shelf_check.isChecked(),
                "auto_import": self.auto_import_check.isChecked(),
                "auto_create_layer": self.auto_layer_check.isChecked(),
            },
            "output_contract": {
                "kind": (
                    "painter-framed-projection-texture"
                    if capture_record
                    else "painter-reusable-texture"
                ),
                "aspect_ratio": aspect,
                "project_directory": (
                    f"assets/livery-studio/generated/{request_id}"
                ),
                "mapping": self.projection_combo.currentText(),
                "final_response_marker": (
                    "LIVERY_ASSET: <project-relative-path>"
                ),
                "note": (
                    "Use the selected Painter screenshot as the structural and "
                    "visual boundary. Keep important subjects and lettering inside "
                    "the selected region. Use reference_assets as visual inputs, "
                    "not automatic output. Return one flat raster asset. The plugin "
                    "can import it and create a native editable Painter Fill layer."
                ),
            },
        }

    def _send_agent(self) -> None:
        message = self.prompt_edit.toPlainText().strip()
        try:
            self._configure_agent()
            self._save()
            self.transcript.append(
                f"<b>你</b><br>{html.escape(message)}"
            )
            self._agent.send(message, self._agent_context())
        except Exception as exc:
            self._error(str(exc))

    def _interrupt_agent(self) -> None:
        try:
            self._agent.interrupt()
        except Exception as exc:
            self._error(str(exc))

    def _reset_agent(self) -> None:
        try:
            self._agent.reset()
        except Exception as exc:
            self._error(str(exc))

    def _respond_approval(self, decision: str) -> None:
        try:
            self._agent.respond_approval(self._pending_approval, decision)
            self._set_status("正在提交审批。")
        except Exception as exc:
            self._error(str(exc))

    def _clear_approval(self) -> None:
        self._pending_approval = ""
        self.approval_group.setVisible(False)
        self.approval_title.setText("")
        self.approval_reason.setText("")
        self.approval_command.setPlainText("")

    def _on_agent_event(self, event: Dict) -> None:
        kind = event.get("kind")
        if kind == "service_connecting":
            self._set_status("正在连接本地 Agent 服务。")
        elif kind == "service_ready":
            self._set_status("Painter 内 Agent + Skill 已连接，无需额外 API Key。")
        elif kind == "service_stopped":
            self._set_status("本插件启动的 Agent 服务已停止。")
        elif kind == "agent_started":
            self._set_status("Agent 正在分析截图、边界与素材。")
        elif kind == "agent_progress":
            self._set_status("Agent 正在生成或处理资源。")
        elif kind == "agent_activity":
            self._set_status(f"Agent：{event.get('message', '')}")
        elif kind == "agent_approval":
            approval = event.get("approval") or {}
            self._pending_approval = str(approval.get("id") or "")
            self.approval_title.setText(
                str(approval.get("title") or "Agent 请求审批")
            )
            self.approval_reason.setText(str(approval.get("reason") or ""))
            self.approval_command.setPlainText(
                str(approval.get("command") or "")
            )
            self.approval_group.setVisible(True)
            self._set_status("Agent 正在等待 Painter 内审批。")
        elif kind in {"approval_cleared", "approval_sent"}:
            self._clear_approval()
            self._set_status("审批已提交，Agent 继续工作。")
        elif kind == "agent_interrupted":
            self._set_status("已请求停止当前 Agent 任务。")
        elif kind == "agent_reset":
            self.transcript.clear()
            self._clear_approval()
            self._set_status("新的 Agent 会话已就绪。")
        elif kind == "agent_done":
            self._clear_approval()
            response = str(event.get("message") or "")
            self.transcript.append(
                f"<b>Agent</b><br>{html.escape(response).replace(chr(10), '<br>')}"
            )
            status = str(event.get("status") or "completed")
            if status in {"interrupted", "cancelled", "canceled"}:
                self._set_status("Agent 已停止。")
                return
            self._set_status("Agent 已完成。")
            candidate = find_asset_marker(response)
            if candidate:
                try:
                    path = state.resolve_project_path(self._root(), candidate)
                    if path.is_file():
                        self.image_path_edit.setText(str(path))
                        if self.auto_import_check.isChecked():
                            self._import_image(path, generated=True)
                except Exception as exc:
                    self._error(f"Agent 资源处理失败：{exc}")
        elif kind == "error":
            self._error(str(event.get("message") or "Agent 错误"))

    def _browse_image(self) -> None:
        selected, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择 Painter 贴图资源",
            self.image_path_edit.text(),
            "Images (*.png *.jpg *.jpeg *.tga *.tif *.tiff *.bmp *.exr *.psd)",
        )
        if selected:
            self.image_path_edit.setText(selected)
            self._save()

    def _import_current_image(self) -> None:
        try:
            self._import_image(
                Path(self.image_path_edit.text()).expanduser(),
                generated=False,
            )
        except Exception as exc:
            self._error(str(exc))

    def _import_image(self, path: Path, *, generated: bool) -> None:
        record = resources.import_texture_resource(
            self._root(),
            path,
            asset_name=self.asset_name_edit.text().strip(),
            import_to_project=self.import_project_check.isChecked(),
            import_to_shelf=self.import_shelf_check.isChecked(),
            generated=generated,
        )
        self._last_resource = record
        self.image_path_edit.setText(record["stored"])
        targets = " + ".join(record["destinations"])
        warning = "；".join(record.get("warnings") or [])
        message = f"已加入 Painter 资源：{record['name']} → {targets}"
        if warning:
            message += f"\n{warning}"
        self.resource_status.setText(message)
        self._save()
        if self.auto_layer_check.isChecked():
            self._create_layer()

    def _create_layer(self) -> None:
        try:
            if not self._last_resource:
                raise RuntimeError("没有可用于创建图层的最近资源。")
            result = layerstack_tools.create_projection_layer(
                self._last_resource,
                projection_mode=self.projection_combo.currentText(),
                layer_name=self.asset_name_edit.text().strip(),
            )
            self.resource_status.setText(
                f"已创建 {result['projection_mode']} Fill 图层：{result['name']}。"
                "请在 Properties 中调整投影框位置、旋转和缩放。"
            )
            self._save()
        except Exception as exc:
            self._error(str(exc))

    def _reveal_last_resource(self) -> None:
        try:
            count = resources.show_record_resources(self._last_resource)
            if count:
                self.resource_status.setText(
                    f"已在 Assets 中显示 {count} 个资源版本。"
                )
            else:
                self.resource_status.setText(
                    "没有找到最近资源，可重新导入当前贴图。"
                )
        except Exception as exc:
            self._error(str(exc))

    def _set_status(self, message: str) -> None:
        self.agent_status.setText(message)

    def _error(self, message: str) -> None:
        self.agent_status.setText(f"错误：{message}")
        QtWidgets.QMessageBox.warning(self, "Vehicle Livery Agent", message)

    def shutdown(self) -> None:
        try:
            self._save()
        except Exception:
            pass
        self._agent.close()
