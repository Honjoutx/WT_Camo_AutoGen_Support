"""Actual module/plane documents. Native UV charts are export data only."""
import copy,xml.etree.ElementTree as ET
from pathlib import Path
from project import Project,ROOT,NS,read,sha,layer_info,graphics
from projects import NativeProject

class SurfaceProject(NativeProject):
 def __init__(self,config,library):
  self.config=config;self.root=ROOT/config['directory'];self.surface_root=self.root/config.get('surface_directory','surfaces/v1');self.state_dir=self.root/'state'/('surface-'+self.surface_root.name);self.cache=self.root/'cache';self.base=self.root;self.library=library
  self.contract=read(self.surface_root/'contract.json');self.native_contract=read(self.root/self.contract['native_contract']);self.regions=copy.deepcopy(self.contract['regions']);self.top={};self.net={'regions':{}};self.signature=sha(self.surface_root/'contract.json');self.core_signature=self.signature;self.compatible_signatures=set(self.contract.get('compatible_layout_signatures',[]))
  for key,meta in self.regions.items():
   ls=[]
   for i,node in graphics(self.source_root(key)):
    info=layer_info(i,node);identity=node.get('id','');text_nodes=[e for e in node.iter() if e.tag.rsplit('}',1)[-1]=='text']
    if len(text_nodes)>1:info.update(text=None,kind='shape')
    info.update(default_visible=node.get('data-visible','true')!='false',default_locked=i==0,default_material={'metallic':.06,'roughness':.4} if identity.startswith('character-') else {'metallic':None,'roughness':None})
    for ch,attr in [('metallic','data-metallic'),('roughness','data-roughness'),('relief_mm','data-relief-mm')]:
     if node.get(attr) is not None:info['default_material'][ch]=float(node.get(attr))
    if i==0:info.update(label='模块结构参考 · 只读 · 不导出',kind='base',text=None)
    elif i==1:info.update(label='涂装底色',kind='base',text=None)
    elif identity.startswith('character-'):info.update(label='角色立绘 · 原图像素',kind='portrait',text=None,art_clip=node.get('clip-path'))
    elif identity.startswith('title-'):info.update(label='文字 · '+(text_nodes[0].text or '')[:28],kind='text')
    elif node.tag.rsplit('}',1)[-1]=='text':info.update(label='文字 · '+(node.text or '')[:28],kind='text')
    if node.get('data-layer-label'):info['label']=node.get('data-layer-label')
    ls.append(info)
   shared=bool(meta.get('shared_uv_template'))
   meta.update(layers=ls,source_url=f'/source/{key}.svg',guide_url=f'/guide/{key}.svg',thumbnail_url=f'/thumb/{key}.png',reference_url=f'/reference/{key}-context.png',paint_mask_url=f'/surface-mask/{key}.png',native_uv=shared,physical_surface=not shared)
 def source_path(self,key):return self.surface_root/'sources'/f'{key}-editable.svg'
 def editing_assets(self,rows):return rows
 def initial_region(self,key):
  row=super().initial_region(key)
  for layer,info in zip(row['layers'],self.regions[key]['layers']):layer['material']=copy.deepcopy(info['default_material'])
  return row
 def compose(self,state,key,for_export=False):
  # Only artwork is exported: the visible gray structure reference must never
  # become a layer of the paint or a scalar material map.
  out=copy.deepcopy(state)
  if for_export:out['regions'][key]['layers'][0]['visible']=False
  root=ET.fromstring(Project.compose(self,out,key))
  # A reference-finish text coating still follows the editable layer controls.
  # Embedded inscriptions have their own values; single text layers opt in
  # explicitly so an artist can subsequently change or clear their finish.
  layers={l['id']:l for l in out['regions'][key]['layers']}
  for group in root.iter():
   if not group.get('id','').startswith('layout-'):continue
   layer=layers.get(group.get('id').removeprefix('layout-'))
   if layer is None:continue
   for text in group.iter():
    if text.get('data-material-use-layer')!='true':continue
    for ch in ['metallic','roughness']:
     attr='data-material-'+ch;value=layer.get('material',{}).get(ch)
     if value is None:text.attrib.pop(attr,None)
     else:text.set(attr,str(value))
  if for_export:
   for node in list(root):
    if node.get('id')=='layout-node-0':root.remove(node)
  for node in list(root):
   if node.tag.rsplit('}',1)[-1] in ['defs','metadata','title','desc'] or node.get('id')=='layout-node-0':continue
   wrap=ET.Element('{'+NS+'}g',{'mask':'url(#surface-footprint)'});root.remove(node);wrap.append(node);root.append(wrap)
  if for_export and self.contract.get('typography',{}).get('outline_on_export'):
   from font_outline import outline_text
   outline_text(root,self.root/self.contract['typography']['font'],self.contract['typography']['family'])
  return ET.tostring(root,encoding='unicode')
