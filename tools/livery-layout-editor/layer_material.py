"""Alpha- and occlusion-correct per-layer scalar PBR overrides.

RGB data: R=override numerator, G=override weight, B=0.
Final scalar = automatic*(1-G)+R. Inherited opaque layers restore automatic.
The exact layout SVG supplies all masks, transforms, image alpha and text.
"""
import copy,xml.etree.ElementTree as ET
from project import NS,tag
def has_override(state,key,channel):
 return any(l['visible'] and l['opacity']>0 and l.get('material',{}).get(channel) is not None for l in state['regions'][key]['layers'])
def _compose_legacy_material(color_svg,state,key,channel,meta):
 if not has_override(state,key,channel):return None
 root=ET.fromstring(color_svg);defs=next((e for e in root if tag(e)=='defs'),None)
 if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
 extracted={}
 def walk(e,ancestors):
  ident=e.get('id','')
  if ident.startswith('layout-'):
   out=copy.deepcopy(e)
   for parent in reversed(ancestors):
    wrapper=ET.Element(parent.tag,{k:v for k,v in parent.attrib.items() if k not in ['id','data-shared-fixed-clip']});wrapper.append(out);out=wrapper
   extracted[ident.removeprefix('layout-')]=out;return
  if tag(e) not in ['defs','metadata','title','desc']:
   for child in e:walk(child,[*ancestors,e])
 for e in list(root):walk(e,[])
 for e in list(root):
  if tag(e) not in ['defs','metadata','title','desc']:root.remove(e)
 x,y=meta.get('view_origin',[0,0]);w,h=meta['viewbox']
 ET.SubElement(root,f'{{{NS}}}rect',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'fill':'black'})
 pending=[];active=False;serial=0
 def flush(value):
  nonlocal serial,pending
  if not pending:return
  ident=f'layer-material-{channel}-{serial}';serial+=1
  f=ET.SubElement(defs,f'{{{NS}}}filter',{'id':ident,'filterUnits':'userSpaceOnUse','x':str(x),'y':str(y),'width':str(w),'height':str(h),'color-interpolation-filters':'sRGB'})
  v=0 if value is None else value;weight=0 if value is None else 1
  ET.SubElement(f,f'{{{NS}}}feColorMatrix',{'type':'matrix','values':f'0 0 0 0 {v} 0 0 0 0 {weight} 0 0 0 0 0 0 0 0 1 0'})
  group=ET.SubElement(root,f'{{{NS}}}g',{'filter':f'url(#{ident})'})
  for e in pending:group.append(e)
  pending=[]
 for layer in state['regions'][key]['layers']:
  if not layer['visible'] or layer['opacity']==0:continue
  value=layer.get('material',{}).get(channel)
  if value is not None:
   flush(None);active=True;pending=[extracted[layer['id']]];flush(value)
  elif active:pending.append(extracted[layer['id']])
 flush(None)
 return ET.tostring(root,encoding='unicode')

# Per-element annotations are opt-in. Unannotated projects keep the original
# compositor byte-for-byte, while annotated coatings get independent opaque
# material coverage instead of inheriting the subdued ink opacity.
_ELEMENT_CHANNELS={'metallic':'data-material-metallic','roughness':'data-material-roughness',
                   'relief_mm':'data-material-relief-mm'}
_NO_PAINT={'defs','metadata','title','desc','mask','clipPath','filter','linearGradient','radialGradient'}

def _remove_attenuation(e,leaf=False):
 for attr in ['opacity','fill-opacity','stroke-opacity','filter']:
  e.attrib.pop(attr,None)
 if e.get('style'):
  remove={'opacity','fill-opacity','stroke-opacity','filter'}
  if leaf:remove|={'fill','stroke'}
  styles=[]
  for piece in e.get('style').split(';'):
   if ':' in piece and piece.split(':',1)[0].strip() not in remove:styles.append(piece)
  if styles:e.set('style',';'.join(styles))
  else:e.attrib.pop('style',None)

def _coverage_branch(leaf,ancestors):
 out=copy.deepcopy(leaf);_remove_attenuation(out,True)
 paint=leaf.get('data-material-paint')
 if paint is None:
  paint='stroke' if leaf.get('fill')=='none' and leaf.get('stroke') not in [None,'none'] else 'both' if leaf.get('stroke') not in [None,'none'] else 'fill'
 out.set('fill','white' if paint in ['fill','both'] else 'none')
 out.set('stroke','white' if paint in ['stroke','both'] else 'none')
 for parent in reversed(ancestors):
  attrs={k:v for k,v in parent.attrib.items() if k not in ['id','data-shared-fixed-clip']}
  wrapper=ET.Element(parent.tag,attrs);_remove_attenuation(wrapper)
  wrapper.append(out);out=wrapper
 # Annotation domain is a fixed physical-board clip, outside all user art
 # transforms. Thus moved stars cannot turn the adjacent white paint to foil.
 domain=leaf.get('data-material-clip')
 if domain:
  wrapper=ET.Element(f'{{{NS}}}g',{'clip-path':'url(#'+domain+')'});wrapper.append(out);out=wrapper
 return out

def _compose_element_material(color_svg,state,key,channel,meta):
 root=ET.fromstring(color_svg);defs=next((e for e in root if tag(e)=='defs'),None)
 if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
 extracted={}
 def walk(e,ancestors):
  ident=e.get('id','')
  if ident.startswith('layout-'):
   out=copy.deepcopy(e)
   for parent in reversed(ancestors):
    wrapper=ET.Element(parent.tag,{k:v for k,v in parent.attrib.items() if k not in ['id','data-shared-fixed-clip']});wrapper.append(out);out=wrapper
   extracted[ident.removeprefix('layout-')]=out;return
  if tag(e) not in _NO_PAINT:
   for child in e:walk(child,[*ancestors,e])
 for e in list(root):walk(e,[])
 rows=[];active=False;attr=_ELEMENT_CHANNELS[channel]
 for layer in state['regions'][key]['layers']:
  if not layer['visible'] or layer['opacity']==0:continue
  drawing=extracted.get(layer['id'])
  if drawing is None:continue
  elements=[]
  def collect(e,ancestors):
   if tag(e) in _NO_PAINT:return
   value=e.get(attr)
   # Outlining retains annotations on the text's group, whose children are
   # exact glyph paths. Treat that group as a single ink footprint, never as
   # a coating over the surrounding constellation/line artwork.
   is_glyph=tag(e)=='g' and e.get('data-original-text') is not None
   if value is not None and (tag(e) in ['path','circle','rect','ellipse','line','polyline','polygon','text'] or is_glyph):
    parsed=float(value)
    if not 0<=parsed<=1:raise ValueError('Per-element material value outside 0..1')
    elements.append((parsed,_coverage_branch(e,ancestors)));return
   for child in e:collect(child,[*ancestors,e])
  collect(drawing,[])
  value=layer.get('material',{}).get(channel)
  active|=value is not None or bool(elements)
  rows.append((drawing,value,elements))
 if not active:return None
 for e in list(root):
  if tag(e) not in ['defs','metadata','title','desc']:root.remove(e)
 x,y=meta.get('view_origin',[0,0]);w,h=meta['viewbox']
 ET.SubElement(root,f'{{{NS}}}rect',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'fill':'black'})
 filters={}
 def paint(draw,value):
  encoded=(0,0) if value is None else (value,1)
  if encoded not in filters:
   ident=f'element-material-{channel}-{len(filters)}';filters[encoded]=ident
   f=ET.SubElement(defs,f'{{{NS}}}filter',{'id':ident,'filterUnits':'userSpaceOnUse','x':str(x),'y':str(y),'width':str(w),'height':str(h),'color-interpolation-filters':'sRGB'})
   v,weight=encoded
   ET.SubElement(f,f'{{{NS}}}feColorMatrix',{'type':'matrix','values':f'0 0 0 0 {v} 0 0 0 0 {weight} 0 0 0 0 0 0 0 0 1 0'})
  group=ET.SubElement(root,f'{{{NS}}}g',{'filter':'url(#'+filters[encoded]+')'});group.append(draw)
 def coalesce(branches):
  # Identical ancestor masks/transforms need one raster pass. Keep sequential
  # paint order; only adjacent equal-valued coatings are batched together.
  out=ET.Element(f'{{{NS}}}g')
  def append(parent,branch):
   last=parent[-1] if len(parent) else None
   if last is not None and tag(last)=='g' and tag(branch)=='g' and last.attrib==branch.attrib:
    for child in list(branch):append(last,child)
   else:parent.append(branch)
  for branch in branches:append(out,branch)
  return out
 for drawing,value,elements in rows:
  # The layer default supplies ordinary ink. Explicit children are a later
  # coating pass, so a whole-layer state value cannot wash out their finish.
  paint(drawing,value)
  pending=[];previous=None
  for override,coverage in elements:
   if pending and override!=previous:paint(coalesce(pending),previous);pending=[]
   pending.append(coverage);previous=override
  if pending:paint(coalesce(pending),previous)
 return ET.tostring(root,encoding='unicode')

def compose_material(color_svg,state,key,channel,meta):
 attr=_ELEMENT_CHANNELS.get(channel)
 if attr and attr in color_svg:
  return _compose_element_material(color_svg,state,key,channel,meta)
 return _compose_legacy_material(color_svg,state,key,channel,meta)
