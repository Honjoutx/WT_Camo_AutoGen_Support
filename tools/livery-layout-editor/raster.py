"""Resolution-independent SVG rasterization without a Node/browser dependency."""
import re
import resvg_py
from runtime import font_files

def svg_png(svg,width,height=None):
 return resvg_py.svg_to_bytes(svg_string=svg,width=width,height=height,
  font_files=font_files(),skip_system_fonts=False)
