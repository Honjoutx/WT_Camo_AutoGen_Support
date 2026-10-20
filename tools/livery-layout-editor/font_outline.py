"""Keep source text editable; compile exact local OTF glyphs for exported SVG."""
from pathlib import Path
import sys,copy,xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from functools import lru_cache
NS='http://www.w3.org/2000/svg'
@lru_cache(maxsize=4)
def font_data(path):
 f=TTFont(path);return f,f.getGlyphSet(),f.getBestCmap(),f['head'].unitsPerEm
def outline_text(root,path,family='Seldom Scene'):
 f,glyphs,cmap,units=font_data(str(path))
 for parent in list(root.iter()):
  for text in list(parent):
   if text.tag!=f'{{{NS}}}text' or family not in text.get('font-family',''):continue
   string=''.join(text.itertext());size=float(text.get('font-size','16'));scale=size/units;spacing=float(text.get('letter-spacing','0'));x=float(text.get('x','0'));y=float(text.get('y','0'));names=[cmap.get(ord(c),'.notdef') for c in string];advances=[f['hmtx'][n][0]*scale for n in names];width=sum(advances)+max(0,len(names)-1)*spacing
   if text.get('text-anchor')=='middle':x-=width/2
   elif text.get('text-anchor')=='end':x-=width
   attrs={k:v for k,v in text.attrib.items() if k not in ['x','y','font-family','font-size','letter-spacing','text-anchor']};attrs.update({'data-original-text':string,'data-outline-font':family});out=ET.Element(f'{{{NS}}}g',attrs)
   for name,advance in zip(names,advances):
    pen=SVGPathPen(glyphs);glyphs[name].draw(pen);d=pen.getCommands()
    if d:
     pa={'d':d,'transform':f'translate({x},{y}) scale({scale},{-scale})'}
     # Text stroke widths are in document units. Glyph paths are in font units;
     # compensate their local transform so outlined lettering retains its rim.
     if text.get('stroke') not in [None,'none'] and scale>0:pa['stroke-width']=str(float(text.get('stroke-width','1'))/scale)
     ET.SubElement(out,f'{{{NS}}}path',pa)
    x+=advance+spacing
   pos=list(parent).index(text);parent.remove(text);parent.insert(pos,out)
 return root
