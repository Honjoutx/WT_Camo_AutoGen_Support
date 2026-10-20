"""Source-preserving SVG layers for independent model projects."""
from pathlib import Path
import base64,copy,hashlib,json,math,os,re,tempfile,time,xml.etree.ElementTree as ET
from affine import svg_matrix
import layer_shadow
from runtime import ROOT,HERE
STATE=ROOT/'state';STATE.mkdir(parents=True,exist_ok=True)
NS='http://www.w3.org/2000/svg';ET.register_namespace('',NS)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def write_json(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 payload=json.dumps(value,ensure_ascii=False,indent=2);tmp=None
 try:
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=p.parent,prefix=p.name+'.',suffix='.tmp',delete=False) as f:
   tmp=Path(f.name);f.write(payload);f.flush();os.fsync(f.fileno())
  # Windows readers and antivirus can briefly hold a destination without
  # delete sharing. Keep the old complete JSON in place and retry the atomic
  # rename; never fall back to truncating the live file.
  for attempt in range(9):
   try:
    os.replace(tmp,p);break
   except PermissionError:
    if attempt==8:raise
    time.sleep(min(.01*(2**attempt),.4))
 finally:
  if tmp is not None and tmp.exists():tmp.unlink()

def tag(e):return e.tag.rsplit('}',1)[-1]

def defaults():return {'scale':1,'tx':0,'ty':0,'rotation':0,'flip_x':False,'flip_y':False,'pivot_x':0,'pivot_y':0}

def graphics(root):return [(i,e) for i,e in enumerate(root) if tag(e) not in ['metadata','defs','title','desc']]

def bound_embedded_vectors(root):
 # resvg's SVG-image renderer may paint beyond an image's intrinsic rectangle.
 # Match browser image semantics explicitly, before the image's own transform.
 defs=next((e for e in root if tag(e)=='defs'),None)
 if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
 images=[(parent,e) for parent in root.iter() for e in list(parent) if tag(e)=='image' and e.get('href','').startswith('data:image/svg')]
 for i,(parent,e) in enumerate(images):
  cid='editor-embedded-vector-bounds-'+str(i);clip=ET.SubElement(defs,f'{{{NS}}}clipPath',{'id':cid,'clipPathUnits':'userSpaceOnUse'})
  ET.SubElement(clip,f'{{{NS}}}rect',{n:e.get(n,'0' if n in ['x','y'] else '1') for n in ['x','y','width','height']})
  attrs={'clip-path':'url(#'+cid+')'}
  if e.get('transform'):attrs['transform']=e.attrib.pop('transform')
  wrapper=ET.Element(f'{{{NS}}}g',attrs);idx=list(parent).index(e);parent.remove(e);wrapper.append(e);parent.insert(idx,wrapper)

def layer_info(index,e):
 identity=e.get('id',f'shape-{index}')
 texts=[n.text or '' for n in e.iter() if tag(n)=='text']
 text=texts[0] if len(texts)==1 else None
 kind='text' if text is not None else 'base' if tag(e)=='rect' else 'shape'
 return dict(id=f'node-{index}',source_id=f'node-{index}',index=index,identity=identity,
  label=e.get('data-layer-label') or (('文字 · '+text[:28]) if text is not None else identity),
  kind=kind,opacity=float(e.get('opacity','1')),text=text,fixed_clip=e.get('clip-path') is not None,default_locked=index==0)

class Project:
 def changed(self,state,key):
  a=copy.deepcopy(state['regions'][key]);b=self.initial_region(key)
  for r in [a,b]:
   for l in r['layers']:
    l.pop('locked',None)
    for name,default in [('rotation',0),('flip_x',False),('flip_y',False),('pivot_x',0),('pivot_y',0)]:l['transform'].setdefault(name,default)
  return a!=b
 def compose(self,state,key):
  root=copy.deepcopy(self.source_root(key));sources={l['id']:l for l in self.regions[key]['layers']};nodes={f'node-{i}':e for i,e in graphics(root)}
  for _,e in graphics(root):root.remove(e)
  if self.regions[key].get('safe_rect'):
   defs=next((e for e in root if tag(e)=='defs'),None)
   if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
   clip=ET.SubElement(defs,f'{{{NS}}}clipPath',{'id':'editor-added-asset-safe','clipPathUnits':'userSpaceOnUse'});x,y,w,h=self.regions[key]['safe_rect'];ET.SubElement(clip,f'{{{NS}}}rect',dict(zip(['x','y','width','height'],map(str,[x,y,w,h]))))
  for layer in state['regions'][key]['layers']:
   if layer.get('asset_id'):
    asset=self.library.get(layer['asset_id']);data=self.library.pin(asset['id']).read_bytes();image=ET.Element(f'{{{NS}}}image',{'x':'0','y':'0','width':str(asset['size'][0]),'height':str(asset['size'][1]),'href':'data:'+asset['mime']+';base64,'+base64.b64encode(data).decode(),'preserveAspectRatio':'xMidYMid meet'})
    if asset['suffix']=='.svg':
     defs=next((e for e in root if tag(e)=='defs'),None)
     if defs is None:defs=ET.SubElement(root,f'{{{NS}}}defs')
     cid='editor-asset-bounds-'+layer['id'];clip=ET.SubElement(defs,f'{{{NS}}}clipPath',{'id':cid,'clipPathUnits':'userSpaceOnUse'});ET.SubElement(clip,f'{{{NS}}}rect',{'x':'0','y':'0','width':str(asset['size'][0]),'height':str(asset['size'][1])})
     bounded=ET.Element(f'{{{NS}}}g',{'clip-path':'url(#'+cid+')'});bounded.append(image);image=bounded
    if layer.get('clip_to_safe'):
     cid='editor-added-asset-safe'
     original=ET.Element(f'{{{NS}}}g',{'clip-path':'url(#'+cid+')'});original.append(image)
    else:
     original=ET.Element(f'{{{NS}}}g');original.append(image)
   else:
    original=copy.deepcopy(nodes[layer['source_id']])
   if not layer.get('asset_id') and layer['id']!=layer['source_id']:
    mapping={e.get('id'):'copy-'+layer['id']+'-'+e.get('id') for e in original.iter() if e.get('id')}
    for e in original.iter():
     if e.get('id') in mapping:e.set('id',mapping[e.get('id')])
     for name,value in list(e.attrib.items()):
      for old,new in mapping.items():value=value.replace('url(#'+old+')','url(#'+new+')')
      if value.startswith('#') and value[1:] in mapping:value='#'+mapping[value[1:]]
      e.set(name,value)
   # Both shadow/ink texts retain the same edited content. XML serialisation escapes user input.
   if layer['text'] is not None:
    for e in original.iter():
     if tag(e)=='text':e.text=layer['text']
   original.set('opacity','1');wrapper=ET.Element(f'{{{NS}}}g',{'id':'layout-'+layer['id'],'transform':svg_matrix(layer['transform']),'opacity':str(layer['opacity'])})
   if not layer['visible']:wrapper.set('display','none')
   if original.get('clip-path'):
    # Fixed model-area clip stays in surface space. Only artwork inside it moves.
    children=list(original)
    for c in children:original.remove(c);wrapper.append(c)
    clip=original.get('clip-path')
    # Consecutive layers with one fixed physical mask share its rasterisation.
    # This reduces whole-top composition from ~70 full-size mask passes to five.
    effect=layer_shadow.apply(root,wrapper,layer,self.regions[key])
    if len(root) and root[-1].get('data-shared-fixed-clip')==clip:root[-1].append(effect)
    else:original.set('data-shared-fixed-clip',clip);original.append(effect);root.append(original)
   else:wrapper.append(original);root.append(layer_shadow.apply(root,wrapper,layer,self.regions[key]))
  bound_embedded_vectors(root)
  return ET.tostring(root,encoding='unicode')
 def source_png_hashes(self,key):
  return sorted(hashlib.sha256(base64.b64decode(e.get('href').split(',',1)[1])).hexdigest() for e in self.source_root(key).iter() if tag(e)=='image' and (e.get('href') or '').startswith('data:image/png;base64,'))
