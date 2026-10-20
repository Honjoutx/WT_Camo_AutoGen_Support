"""Explicit project contexts; no mutable global model/UV binding on request paths."""
from pathlib import Path
import copy,json,math,re,threading,shutil,xml.etree.ElementTree as ET
from urllib.parse import quote
from project import Project,ROOT,HERE,STATE,read,write_json,sha,layer_info,graphics,defaults,NS
from assets import AssetLibrary
import layer_shadow
from types import SimpleNamespace

REGISTRY=ROOT/'projects/registry.json'

def scoped(url,ident):return url+('&' if '?' in url else '?')+'project='+quote(ident)

class NativeProject(Project):
 def __init__(self,config,library):
  self.config=config;self.root=ROOT/config['directory'];self.state_dir=self.root/'state';self.cache=self.root/'cache';self.base=self.root;self.library=library
  self.contract=read(self.root/'model-project.json');self.regions=copy.deepcopy(self.contract['regions']);self.top={};self.net={'regions':{}}
  self.signature=sha(self.root/'model-project.json');self.core_signature=self.signature
  self.compatible_signatures=set(self.contract.get('compatible_layout_signatures',[]))
  for key,meta in self.regions.items():
   meta['layers']=[layer_info(i,e) for i,e in graphics(self.source_root(key))]
   for l in meta['layers']:l.update(default_visible=l['index']==0,default_locked=l['index']==0)
   meta['layers'][0].update(label='原始纹理 · 只读',kind='base');meta['layers'][1].update(label='涂装底色',kind='base')
   meta.update(source_url=f'/source/{key}.svg',guide_url=f'/guide/{key}.svg',thumbnail_url=f'/thumb/{key}.png',reference_url=f'/reference/assembled.png',paint_mask_url=f'/native-mask/{key}.png',safe_rect=None,native_uv=True)
 def source_path(self,key):return self.root/'sources'/f'{key}-editable.svg'
 def source_root(self,key):return ET.parse(self.source_path(key)).getroot()
 def load_state(self):
  path=self.state_dir/'current.json'
  return self.validate(read(path)) if path.exists() else self.initial()
 def initial_region(self,key):
  return {'layers':[dict(id=l['id'],source_id=l['id'],transform=defaults(),opacity=l['opacity'],visible=l['default_visible'],locked=l['default_locked'],text=l['text'],material={'metallic':None,'roughness':None},shadow=layer_shadow.defaults()) for l in self.regions[key]['layers']]}
 def initial(self):return dict(schema='livery-layout/v2',project_id=self.config['id'],project_signature=self.signature,base_project=self.config['directory'],title=self.config['name'],active_region=next(iter(self.regions)),regions={k:self.initial_region(k) for k in self.regions})
 def validate(self,state):
  if not isinstance(state,dict) or state.get('schema')!='livery-layout/v2' or state.get('project_signature') not in {self.signature,*self.compatible_signatures} or state.get('project_id')!=self.config['id']:raise ValueError('布局不属于当前模型项目，不能交叉套用不同 UV。')
  if set(state.get('regions',{}))!=set(self.regions):raise ValueError('布局需包含当前模型全部区域。')
  out=self.initial();out['title']=str(state.get('title',out['title']))[:120];out['active_region']=state.get('active_region')
  if out['active_region'] not in self.regions:raise ValueError('未知分区。')
  for key,meta in self.regions.items():
   rows=state['regions'][key].get('layers');sources={l['id']:l for l in meta['layers']};ids=set();clean=[]
   if not isinstance(rows,list) or not 1<=len(rows)<=200:raise ValueError('分区图层数量无效。')
   for l in rows:
    ident=l.get('id');sid=l.get('source_id');asset=l.get('asset_id')
    if not isinstance(ident,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',ident) or ident in ids or (asset is not None and sid is not None) or (asset is None and sid not in sources):raise ValueError('图层标识无效。')
    if asset is not None:self.library.pin(asset)
    ids.add(ident);t={**defaults(),**l.get('transform',{})}
    for n in ['scale','tx','ty','rotation','pivot_x','pivot_y']:
     if isinstance(t[n],bool) or not isinstance(t[n],(float,int)) or not math.isfinite(t[n]):raise ValueError('图层变换应为有限数字。')
    if not .02<=t['scale']<=20 or max(abs(t[n]) for n in ['tx','ty','pivot_x','pivot_y'])>100000 or abs(t['rotation'])>360000:raise ValueError('图层变换超出范围。')
    if not all(isinstance(t[n],bool) for n in ['flip_x','flip_y']):raise ValueError('翻转设置无效。')
    t={n:t[n] for n in defaults()};t['rotation']=(t['rotation']+180)%360-180
    opacity=l.get('opacity',1)
    if isinstance(opacity,bool) or not isinstance(opacity,(int,float)) or not math.isfinite(opacity) or not 0<=opacity<=1:raise ValueError('不透明度无效。')
    text=l.get('text');is_text=asset is None and sources[sid]['text'] is not None
    if (not is_text and text is not None) or (is_text and (not isinstance(text,str) or len(text)>500)):raise ValueError('文字内容无效。')
    material=l.get('material',{});values={}
    if not isinstance(material,dict) or set(material)-{'metallic','roughness','relief_mm'}:raise ValueError('图层材质设置无效。')
    for n in ['metallic','roughness','relief_mm']:
     v=material.get(n)
     if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1):raise ValueError('金属度、粗糙度或浮雕高度无效。')
     if n!='relief_mm' or v is not None:values[n]=v
    row=dict(id=ident,source_id=sid,transform=t,opacity=opacity,visible=bool(l.get('visible',True)),locked=bool(l.get('locked',False)),text=text,material=values,shadow=layer_shadow.validate(l.get('shadow')))
    if asset is not None:row.update(asset_id=asset,clip_to_safe=False)
    clean.append(row)
   if {l['source_id'] for l in clean if l['source_id'] is not None}!=set(sources):raise ValueError('原始图层必须保留，可以隐藏。')
   # Original texture is the immutable bottom layer. User artwork is restricted to
   # UV paint coverage. Protected geometry retains the original atlas pixels.
   if clean[0]['source_id']!='node-0' or clean[0]['id']!='node-0' or any(l['source_id']=='node-0' for l in clean[1:]):raise ValueError('原始贴图必须保留在底层，不能复制到上层。')
   base=clean[0];initial=self.initial_region(key)['layers'][0]
   if base!=initial:raise ValueError('原始贴图底层不可修改，请使用上方图层设计。')
   out['regions'][key]={'layers':clean}
  return out
 def compose(self,state,key):
  root=ET.fromstring(super().compose(state,key));defs=next((e for e in root if e.tag.rsplit('}',1)[-1]=='defs'),None)
  if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
  mask=ET.SubElement(defs,f'{{{NS}}}mask',{'id':'native-paint-coverage','maskUnits':'userSpaceOnUse','x':'0','y':'0','width':'2048','height':'2048','style':'mask-type:luminance'})
  import base64
  data=(self.root/'masks'/f'{key}.png').read_bytes();ET.SubElement(mask,f'{{{NS}}}image',{'width':'2048','height':'2048','href':'data:image/png;base64,'+base64.b64encode(data).decode()})
  for e in list(root):
   if e.tag.rsplit('}',1)[-1] in ['defs','metadata','title','desc'] or e.get('id')=='layout-node-0':continue
   g=ET.Element(f'{{{NS}}}g',{'mask':'url(#native-paint-coverage)'});root.remove(e);g.append(e);root.append(g)
  return ET.tostring(root,encoding='unicode')

class ProjectManager:
 def __init__(self):
  self.lock=threading.RLock();self.cache={};self.registry=read(REGISTRY) if REGISTRY.exists() else __import__('bootstrap').initialize()
 def config(self,ident=None):
  ident=ident or self.registry['active_project']
  if ident not in self.registry['projects']:raise ValueError('项目不存在。')
  return self.registry['projects'][ident]
 def job_context(self,ident=None):
  """Task records and downloads do not require the model or design sources."""
  config=copy.deepcopy(self.config(ident));directory=ROOT/config['directory']
  return SimpleNamespace(id=config['id'],config=config,root=directory,jobs=directory/'outputs')
 def library(self,c):
  directory=ROOT/c['directory'];shared=c.get('shared_library');roots=[]
  for r in c.get('asset_roots',[]):roots.append((ROOT/r,'角色原图'))
  roots.append((directory/'assets/imported','自定义素材'))
  imports=directory/'assets/imported'
  if shared:
   lib=self.registry['libraries'][shared]
   for r in lib.get('roots',[]):roots.append((ROOT/r,'角色原图'))
   imports=ROOT/lib['imports'];roots.append((imports,'自定义素材'))
  return AssetLibrary(cache=directory/'cache/asset-library',imports=imports,roots=roots)
 def get(self,ident=None,snapshot=None):
  with self.lock:
   c=snapshot or self.config(ident);ident=c['id']
   if snapshot is None and ident in self.cache:return self.cache[ident]
   library=self.library(c);directory=ROOT/c['directory'];directory.joinpath('state/checkpoints').mkdir(parents=True,exist_ok=True)
   if c['type']=='surface-planes':
    from surface_project import SurfaceProject
    p=SurfaceProject(c,library)
   elif c['type']=='boards':
    from boards import BoardProject
    p=BoardProject(c,library)
   elif c['type']=='native-uv':p=NativeProject(c,library)
   else:raise ValueError('未知项目类型。')
   p.config=copy.deepcopy(c);p.id=ident;p.root=directory;p.cache=directory/'cache';p.base=directory;p.jobs=directory/'outputs'
   p.state_dir.mkdir(parents=True,exist_ok=True)
   if not (p.state_dir/'render-settings.json').exists():
    from runtime import render_settings
    write_json(p.state_dir/'render-settings.json',render_settings())
   p.jobs.mkdir(exist_ok=True);self.cache[ident]=p if snapshot is None else self.cache.get(ident,p)
   return p
 def listing(self):return dict(active_project=self.registry['active_project'],projects=list(self.registry['projects'].values()),libraries=list(self.registry['libraries'].values()))
 def switch(self,ident):
  with self.lock:self.get(ident);self.registry['active_project']=ident;write_json(REGISTRY,self.registry)
 def select_library(self,ident,library):
  with self.lock:
   if library is not None and library not in self.registry['libraries']:raise ValueError('共享素材库不存在。')
   old=self.get(ident);state=old.load_state()
   target=ROOT/self.config(ident)['directory']/'cache/asset-library';(target/'originals').mkdir(parents=True,exist_ok=True)
   archived=read(target/'index.json') if (target/'index.json').exists() else {}
   for r in state['regions'].values():
    for l in r['layers']:
     if l.get('asset_id'):
      aid=l['asset_id'];old.library.pin(aid)
      archived[aid]=copy.deepcopy(old.library.get(aid))
   write_json(target/'index.json',archived)
   c=self.config(ident);c['shared_library']=library;self.cache.pop(ident,None);write_json(REGISTRY,self.registry);return self.get(ident)
 def payload(self,p):
  regions=copy.deepcopy(list(p.regions.values()));assets=copy.deepcopy(p.library.list())
  for row in regions:
   if not row.get('description') and row.get('surface','').startswith('individual-real-component'):
    row['description']='按真实组件分面编辑；设计外壳，镜片与原 UV 保留。'
  if hasattr(p,'editing_assets'):assets=p.editing_assets(assets)
  for row in [*regions,*assets]:
   for k,v in row.items():
    if k.endswith('url') and isinstance(v,str):row[k]=scoped(v,p.id)
  c=p.config
  return dict(id=p.id,name=c['name'],regions=regions,assets=assets,state=p.load_state(),base_project=str(p.base.relative_to(ROOT)),output_root=str(p.jobs),project_directory=str(p.root),project_signature=p.signature,editor_version=19,combined_top=p.top,render_settings=read(p.state_dir/'render-settings.json'),project_type=c['type'],shared_library=c.get('shared_library'),models=c.get('models',[]),description=c.get('description',''),model_url=scoped('/api/model',p.id),manifest_url=scoped('/api/model-manifest',p.id))
