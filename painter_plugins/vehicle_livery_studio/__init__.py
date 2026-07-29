"""Vehicle Livery Agent plug-in for Adobe Substance 3D Painter."""

from .plugin import (
    PLUGIN_VERSION,
    close_plugin,
    discard_plugin,
    start_plugin,
)


__version__ = PLUGIN_VERSION
__all__ = ("start_plugin", "close_plugin", "discard_plugin")
