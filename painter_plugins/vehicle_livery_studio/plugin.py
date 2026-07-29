from __future__ import annotations

import substance_painter.application
import substance_painter.logging
import substance_painter.ui

from . import state
from .qt import QtGui
from .ui import LiveryStudioWidget


PLUGIN_VERSION = "0.3.1"
_WIDGET = None
_DOCK = None
_ACTION = None


def _record_runtime(status: str, detail: str = "") -> None:
    root = state.find_project_root()
    if root is None:
        return
    try:
        state.write_runtime_status(
            root,
            status=status,
            version=PLUGIN_VERSION,
            detail=detail,
        )
    except Exception:
        pass


def start_plugin() -> None:
    global _ACTION, _DOCK, _WIDGET
    if _DOCK is not None:
        _DOCK.show()
        _DOCK.raise_()
        return

    try:
        _WIDGET = LiveryStudioWidget()
        _DOCK = substance_painter.ui.add_dock_widget(_WIDGET)
        _DOCK.setObjectName("CamoAutoGenVehicleLiveryDock")
        _DOCK.setWindowTitle("Vehicle Livery Agent")
        _WIDGET.set_dock_widget(_DOCK)

        _ACTION = QtGui.QAction("Vehicle Livery Agent", _DOCK)
        _ACTION.setObjectName("CamoAutoGenVehicleLiveryAction")
        _ACTION.triggered.connect(_DOCK.show)
        _ACTION.triggered.connect(_DOCK.raise_)
        substance_painter.ui.add_action(
            substance_painter.ui.ApplicationMenu.Window,
            _ACTION,
        )
        substance_painter.logging.info(
            f"Vehicle Livery Agent {PLUGIN_VERSION} loaded."
        )
        _record_runtime("started", substance_painter.application.version())
    except Exception as exc:
        _record_runtime("error", str(exc))
        substance_painter.logging.error(
            f"Vehicle Livery Agent failed to load: {exc}"
        )
        raise


def close_plugin() -> None:
    global _ACTION, _DOCK, _WIDGET
    if _WIDGET is not None:
        _WIDGET.shutdown()
    if _ACTION is not None:
        try:
            _ACTION.triggered.disconnect()
        except Exception:
            pass
        _ACTION.deleteLater()
    if _DOCK is not None:
        try:
            substance_painter.ui.delete_ui_element(_DOCK)
        except Exception:
            _DOCK.deleteLater()
    _ACTION = None
    _DOCK = None
    _WIDGET = None
    _record_runtime("closed")


def discard_plugin() -> bool:
    # Painter 10.1+ uses Qt 6 and provides the modern layer-stack API used here.
    return tuple(substance_painter.application.version_info()) < (10, 1, 0)
