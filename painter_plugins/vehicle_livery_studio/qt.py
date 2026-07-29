"""Qt compatibility helpers for Substance 3D Painter."""

from PySide6 import QtCore, QtGui, QtWidgets


KEEP_ASPECT_RATIO = QtCore.Qt.AspectRatioMode.KeepAspectRatio
SMOOTH_TRANSFORMATION = QtCore.Qt.TransformationMode.SmoothTransformation
ALIGN_CENTER = QtCore.Qt.AlignmentFlag.AlignCenter
CROSS_CURSOR = QtCore.Qt.CursorShape.CrossCursor
LEFT_BUTTON = QtCore.Qt.MouseButton.LeftButton
IMAGE_ARGB32 = QtGui.QImage.Format.Format_ARGB32
DIALOG_ACCEPTED = QtWidgets.QDialog.DialogCode.Accepted
BUTTON_OK = QtWidgets.QDialogButtonBox.StandardButton.Ok
BUTTON_CANCEL = QtWidgets.QDialogButtonBox.StandardButton.Cancel


def exec_dialog(dialog: QtWidgets.QDialog) -> int:
    return dialog.exec()
