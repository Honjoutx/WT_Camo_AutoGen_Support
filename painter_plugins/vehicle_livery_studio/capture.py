from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from . import state
from .qt import (
    BUTTON_CANCEL,
    BUTTON_OK,
    CROSS_CURSOR,
    DIALOG_ACCEPTED,
    IMAGE_ARGB32,
    KEEP_ASPECT_RATIO,
    LEFT_BUTTON,
    QtCore,
    QtGui,
    QtWidgets,
    exec_dialog,
)


class CropCanvas(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(bool)

    def __init__(self, image: QtGui.QImage, parent=None):
        super().__init__(parent)
        self._image = image
        self._origin = QtCore.QPoint()
        self._selection = QtCore.QRect()
        self._dragging = False
        self.setMinimumSize(640, 420)
        self.setMouseTracking(True)
        self.setCursor(CROSS_CURSOR)

    def _image_rect(self) -> QtCore.QRect:
        available = self.rect().adjusted(12, 12, -12, -12)
        size = self._image.size()
        size.scale(available.size(), KEEP_ASPECT_RATIO)
        left = available.left() + (available.width() - size.width()) // 2
        top = available.top() + (available.height() - size.height()) // 2
        return QtCore.QRect(QtCore.QPoint(left, top), size)

    def selected_source_rect(self) -> QtCore.QRect:
        image_rect = self._image_rect()
        selected = self._selection.normalized().intersected(image_rect)
        if selected.width() < 4 or selected.height() < 4:
            return QtCore.QRect()
        scale_x = self._image.width() / max(1.0, float(image_rect.width()))
        scale_y = self._image.height() / max(1.0, float(image_rect.height()))
        x = int(round((selected.left() - image_rect.left()) * scale_x))
        y = int(round((selected.top() - image_rect.top()) * scale_y))
        width = int(round(selected.width() * scale_x))
        height = int(round(selected.height() * scale_y))
        return QtCore.QRect(x, y, width, height).intersected(self._image.rect())

    def mousePressEvent(self, event):
        if (
            event.button() == LEFT_BUTTON
            and self._image_rect().contains(event.position().toPoint())
        ):
            self._origin = event.position().toPoint()
            self._selection = QtCore.QRect(self._origin, self._origin)
            self._dragging = True
            self.selection_changed.emit(False)
            self.update()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        point = event.position().toPoint()
        image_rect = self._image_rect()
        point.setX(max(image_rect.left(), min(point.x(), image_rect.right())))
        point.setY(max(image_rect.top(), min(point.y(), image_rect.bottom())))
        self._selection = QtCore.QRect(self._origin, point).normalized()
        self.selection_changed.emit(not self.selected_source_rect().isEmpty())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == LEFT_BUTTON and self._dragging:
            self._dragging = False
            self.selection_changed.emit(not self.selected_source_rect().isEmpty())
            self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(22, 24, 28))
        image_rect = self._image_rect()
        painter.drawImage(image_rect, self._image)
        painter.fillRect(image_rect, QtGui.QColor(0, 0, 0, 118))
        selected = self._selection.normalized().intersected(image_rect)
        if selected.width() > 2 and selected.height() > 2:
            painter.save()
            painter.setClipRect(selected)
            painter.drawImage(image_rect, self._image)
            painter.restore()
            painter.setPen(QtGui.QPen(QtGui.QColor(68, 205, 255), 2))
            painter.drawRect(selected)
        painter.end()


class CaptureDialog(QtWidgets.QDialog):
    def __init__(self, image: QtGui.QImage, parent=None):
        super().__init__(parent)
        self.setWindowTitle("框选 Painter 视口设计区域")
        self.setModal(True)
        self.resize(1180, 760)
        layout = QtWidgets.QVBoxLayout(self)
        instruction = QtWidgets.QLabel(
            "拖动框选需要 Agent 分析或生成贴图的模型区域。"
            "尽量只包含 3D 视口和目标表面。"
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        self.canvas = CropCanvas(image, self)
        layout.addWidget(self.canvas, 1)
        buttons = QtWidgets.QDialogButtonBox(BUTTON_OK | BUTTON_CANCEL, parent=self)
        self.ok_button = buttons.button(BUTTON_OK)
        self.ok_button.setText("使用该区域")
        self.ok_button.setEnabled(False)
        buttons.button(BUTTON_CANCEL).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.canvas.selection_changed.connect(self.ok_button.setEnabled)
        layout.addWidget(buttons)

    def source_rect(self) -> QtCore.QRect:
        return self.canvas.selected_source_rect()


def grab_main_window(main_window: QtWidgets.QMainWindow) -> QtGui.QImage:
    pixmap = main_window.grab()
    image = pixmap.toImage().convertToFormat(IMAGE_ARGB32)
    image.setDevicePixelRatio(1.0)
    return image


def select_image_and_save(
    image: QtGui.QImage,
    parent: QtWidgets.QWidget,
    project_root: Union[str, Path],
    painter_context: dict,
) -> Optional[dict]:
    dialog = CaptureDialog(image, parent)
    if exec_dialog(dialog) != DIALOG_ACCEPTED:
        return None
    rect = dialog.source_rect()
    if rect.isEmpty():
        return None

    capture_id = state.timestamp_id("painter")
    full_path, crop_path, _ = state.capture_paths(project_root, capture_id)
    if not image.save(str(full_path), "PNG"):
        raise RuntimeError(f"无法保存 Painter 截图：{full_path}")
    if not image.copy(rect).save(str(crop_path), "PNG"):
        raise RuntimeError(f"无法保存 Painter 框选图：{crop_path}")

    width = max(1, image.width())
    height = max(1, image.height())
    payload = {
        "id": capture_id,
        "source": "substance-painter",
        "full_capture": str(full_path),
        "selected_capture": str(crop_path),
        "window_size_px": [width, height],
        "selection_rect_px": [
            rect.left(),
            rect.top(),
            rect.right() + 1,
            rect.bottom() + 1,
        ],
        "selection_rect_normalized": [
            rect.left() / width,
            rect.top() / height,
            (rect.right() + 1) / width,
            (rect.bottom() + 1) / height,
        ],
        "selection_size_px": [rect.width(), rect.height()],
        "painter_context": painter_context,
    }
    session_path = state.write_capture(project_root, payload)
    payload["session_path"] = str(session_path)
    return payload
