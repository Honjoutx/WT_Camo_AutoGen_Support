"""Drag/drop widgets used by the Painter reference-asset tray."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable

from .qt import (
    KEEP_ASPECT_RATIO,
    SMOOTH_TRANSFORMATION,
    QtCore,
    QtGui,
    QtWidgets,
)


RESOURCE_URL_PATTERN = re.compile(r"resource://[^\s\x00\"'<>]+")


def _record_key(record: Dict[str, Any]) -> str:
    if record.get("kind") == "image":
        return f"image:{str(record.get('path') or '').casefold()}"
    return f"resource:{record.get('resource_url') or ''}"


def _thumbnail_icon(path: Path, size: QtCore.QSize) -> QtGui.QIcon:
    reader = QtGui.QImageReader(str(path))
    source_size = reader.size()
    if source_size.isValid():
        source_size.scale(size, KEEP_ASPECT_RATIO)
        reader.setScaledSize(source_size)
    image = reader.read()
    if image.isNull():
        return QtGui.QIcon()
    pixmap = QtGui.QPixmap.fromImage(image)
    canvas = QtGui.QPixmap(size)
    canvas.fill(QtCore.Qt.GlobalColor.transparent)
    scaled = pixmap.scaled(
        size,
        KEEP_ASPECT_RATIO,
        SMOOTH_TRANSFORMATION,
    )
    painter = QtGui.QPainter(canvas)
    left = (size.width() - scaled.width()) // 2
    top = (size.height() - scaled.height()) // 2
    painter.drawPixmap(left, top, scaled)
    painter.end()
    return QtGui.QIcon(canvas)


class AssetLibraryList(QtWidgets.QListWidget):
    activated_path = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending_paths: list[Path] = []
        self._project_root = Path()
        self._load_generation = 0
        self.setObjectName("CamoAutoGenReferenceAssetLibrary")
        self.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setMovement(QtWidgets.QListView.Movement.Static)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setDragEnabled(True)
        self.setIconSize(QtCore.QSize(96, 72))
        self.setGridSize(QtCore.QSize(116, 110))
        self.setMinimumHeight(150)
        self.itemDoubleClicked.connect(self._activate_item)

    def set_paths(self, paths: Iterable[Path], project_root: Path) -> None:
        self.clear()
        self._pending_paths = list(paths)
        self._project_root = project_root
        self._load_generation += 1
        generation = self._load_generation
        QtCore.QTimer.singleShot(
            0,
            lambda: self._load_next_batch(generation),
        )

    def _load_next_batch(self, generation: int) -> None:
        if generation != self._load_generation:
            return
        batch = self._pending_paths[:24]
        del self._pending_paths[:24]
        for path in batch:
            item = QtWidgets.QListWidgetItem(
                _thumbnail_icon(path, self.iconSize()),
                path.stem,
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
            try:
                item.setToolTip(str(path.relative_to(self._project_root)))
            except ValueError:
                item.setToolTip(str(path))
            self.addItem(item)
        if self._pending_paths:
            QtCore.QTimer.singleShot(
                0,
                lambda: self._load_next_batch(generation),
            )

    def startDrag(self, supported_actions) -> None:
        paths = [
            Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
            for item in self.selectedItems()
        ]
        paths = [path for path in paths if path.is_file()]
        if not paths:
            return
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(path)) for path in paths])
        mime.setText("\n".join(str(path) for path in paths))
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        first = QtGui.QPixmap(str(paths[0]))
        if not first.isNull():
            drag.setPixmap(
                first.scaled(
                    96,
                    72,
                    KEEP_ASPECT_RATIO,
                    SMOOTH_TRANSFORMATION,
                )
            )
        drag.exec(QtCore.Qt.DropAction.CopyAction)

    def _activate_item(self, item) -> None:
        path = str(item.data(QtCore.Qt.ItemDataRole.UserRole) or "")
        if path:
            self.activated_path.emit(path)


class ReferenceDropList(QtWidgets.QListWidget):
    files_dropped = QtCore.Signal(object)
    resources_dropped = QtCore.Signal(object)
    drop_diagnostic = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CamoAutoGenAgentReferenceTray")
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setMovement(QtWidgets.QListView.Movement.Static)
        self.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setIconSize(QtCore.QSize(88, 66))
        self.setGridSize(QtCore.QSize(112, 104))
        self.setMinimumHeight(125)
        self.setToolTip(
            "从上方项目素材库、Windows 资源管理器或 Painter Assets 拖入。"
        )

    @staticmethod
    def _decode_payloads(mime: QtCore.QMimeData) -> list[str]:
        texts: list[str] = []
        if mime.hasText():
            texts.append(mime.text())
        for mime_format in mime.formats():
            raw = bytes(mime.data(mime_format))
            if not raw:
                continue
            for encoding in ("utf-8", "utf-16-le", "utf-16-be", "latin-1"):
                try:
                    value = raw.decode(encoding, errors="ignore")
                except Exception:
                    continue
                if value:
                    texts.append(value)
        return texts

    @classmethod
    def extract_payload(
        cls,
        mime: QtCore.QMimeData,
    ) -> tuple[list[str], list[str]]:
        paths: list[str] = []
        resource_urls: list[str] = []
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    candidate = Path(url.toLocalFile())
                    if candidate.is_file():
                        paths.append(str(candidate.resolve()))
                else:
                    resource_urls.extend(RESOURCE_URL_PATTERN.findall(url.toString()))

        for text in cls._decode_payloads(mime):
            resource_urls.extend(RESOURCE_URL_PATTERN.findall(text))
            for line in text.replace("\x00", "").splitlines():
                candidate_text = line.strip().strip("\"'")
                if not candidate_text or candidate_text.startswith("resource://"):
                    continue
                try:
                    candidate = Path(candidate_text).expanduser()
                    if candidate.is_file():
                        paths.append(str(candidate.resolve()))
                except (OSError, ValueError):
                    continue

        return list(dict.fromkeys(paths)), list(dict.fromkeys(resource_urls))

    def dragEnterEvent(self, event) -> None:
        paths, urls = self.extract_payload(event.mimeData())
        if paths or urls or event.mimeData().formats():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths, resource_urls = self.extract_payload(event.mimeData())
        if paths:
            self.files_dropped.emit(paths)
        if resource_urls:
            self.resources_dropped.emit(resource_urls)
        if not paths and not resource_urls:
            formats = ", ".join(event.mimeData().formats()) or "unknown"
            self.drop_diagnostic.emit(
                f"未识别该 Painter 拖拽数据；MIME：{formats}"
            )
        event.acceptProposedAction()

    def set_records(self, records: Iterable[Dict[str, Any]]) -> None:
        self.clear()
        for record in records:
            name = str(record.get("name") or "reference")
            # Painter may invalidate the temporary QCommonStyle wrapper while a
            # Python plug-in is being reloaded. Keep the fallback icon owned by
            # Python instead of calling self.style().standardIcon() here.
            icon = QtGui.QIcon()
            if record.get("kind") == "image":
                path = Path(str(record.get("path") or ""))
                if path.is_file():
                    icon = _thumbnail_icon(path, self.iconSize())
            item = QtWidgets.QListWidgetItem(icon, name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, _record_key(record))
            item.setToolTip(
                str(record.get("path") or record.get("resource_url") or name)
            )
            self.addItem(item)

    def selected_record_keys(self) -> set[str]:
        return {
            str(item.data(QtCore.Qt.ItemDataRole.UserRole))
            for item in self.selectedItems()
        }
