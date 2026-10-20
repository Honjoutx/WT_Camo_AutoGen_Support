"""Approved image resources of this model project, with immutable snapshots on use."""
from pathlib import Path
import base64,hashlib,io,json,math,mimetypes,re,shutil,sys,threading,uuid,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from runtime import ROOT,font_files
CACHE=ROOT/'cache/asset-library'
IMPORTS=ROOT/'assets/imported'
UPLOAD_LIMIT=64*1024*1024
UPLOAD_SUFFIXES={'.png','.jpg','.jpeg','.webp','.svg'}
from PIL import Image,ImageOps
import resvg_py
from storage import ContentStore
def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def svg_size(root):
 vb=re.split(r'[,\s]+',root.get('viewBox','').strip());size=[]
 units={'':1,'px':1,'pt':96/72,'pc':16,'in':96,'cm':96/2.54,'mm':96/25.4}
 for name,index in [('width',2),('height',3)]:
  match=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]*)?|\.[0-9]+)\s*(px|pt|pc|in|cm|mm)?\s*',root.get(name,''))
  value=float(match[1])*units[match[2] or ''] if match else float(vb[index]) if len(vb)==4 else 0
  if not math.isfinite(value) or not 0<value<=32768:raise ValueError('SVG 需要有效的宽高或 viewBox。')
  size.append(max(1,round(value)))
 return size
class AssetLibrary:
 def __init__(self,cache=None,imports=None,roots=None):
  self.cache=Path(cache) if cache else CACHE;self.imports=Path(imports) if imports else IMPORTS;self.roots=roots or []
  self.cache.mkdir(parents=True,exist_ok=True);(self.cache/'originals').mkdir(exist_ok=True);(self.cache/'thumbnails').mkdir(exist_ok=True);self.lock=threading.RLock();self.index={};self.store=ContentStore();self.refresh()
 def refresh(self):
  with self.lock:
   prior=json.loads((self.cache/'index.json').read_text(encoding='utf8')) if (self.cache/'index.json').exists() else {}
   rows={};candidates=[]
   for source_root,category in self.roots:
    for p in sorted(Path(source_root).rglob("*")):
     if p.is_file() and p.suffix.lower() in UPLOAD_SUFFIXES:candidates.append((p,category,p.stem))
   for p in sorted(self.imports.glob("*")):
    if p.is_file() and p.suffix.lower() in UPLOAD_SUFFIXES:candidates.append((p,"自定义素材",p.stem.split("_",1)[-1]))
   for p,category,label in candidates:
    if not p.is_file():continue
    sha=digest(p);ident=sha[:24]
    if ident in rows:rows[ident]['aliases'].append(p.relative_to(ROOT).as_posix());rows[ident]['alias_names'].append(label);continue
    if p.suffix.lower()=='.svg':
     root=ET.parse(p).getroot();size=svg_size(root);alpha=True
    else:
     with Image.open(p) as im:size=list(im.size);alpha=im.getchannel('A').getextrema()[0]<255 if 'A' in im.getbands() else 'transparency' in im.info
    rows[ident]={'id':ident,'sha256':sha,'name':label,'category':category,'size':size,'transparent':alpha,'suffix':p.suffix.lower(),'mime':mimetypes.guess_type(str(p))[0],'source':p.relative_to(ROOT).as_posix(),'aliases':[],'alias_names':[],'url':f'/asset/{ident}','canvas_url':f'/asset-display/{ident}' if p.suffix.lower()=='.svg' else f'/asset/{ident}','thumbnail_url':f'/asset-thumb/{ident}.png'}
   # Used assets remain addressable even if their original source is later replaced.
   for ident,row in prior.items():
    if ident not in rows and ((self.cache/'originals'/f"{ident}{row['suffix']}").is_file() or self.store.path(row['sha256'],row['suffix']).is_file()):rows[ident]=dict(row,archived=True)
   self.index=rows;self._save();return self.list()
 def _save(self):
  tmp=self.cache/('index-'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(self.index,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(self.cache/'index.json')
 def import_file(self,filename,data):
  name=re.split(r'[\\/]',filename)[-1];suffix=Path(name).suffix.lower()
  if suffix not in UPLOAD_SUFFIXES:raise ValueError('支持 PNG、JPG、WebP 和 SVG 素材。')
  if not data or len(data)>UPLOAD_LIMIT:raise ValueError('单张素材不能超过 64 MB。')
  if suffix=='.svg':
   if re.search(br'<!\s*(DOCTYPE|ENTITY)',data,re.I):raise ValueError('SVG 不能包含外部实体。')
   try:
    root=ET.fromstring(data)
    if root.tag.split('}')[-1]!='svg':raise ValueError('文件不是 SVG 图片。')
    for element in root.iter():
     if element.tag.split('}')[-1].lower() in {'script','foreignobject'}:raise ValueError('SVG 含不支持的脚本或嵌入页面。')
     for attr,value in element.attrib.items():
      local=attr.split('}')[-1].lower()
      if local.startswith('on'):raise ValueError('SVG 含不支持的脚本事件。')
      if local=='href' and value and not (value.startswith('#') or re.match(r'^data:image/(png|jpeg|webp);base64,',value,re.I)):raise ValueError('SVG 图片需内嵌素材，不能引用外部文件。')
    text=data.decode('utf-8-sig')
    if re.search(r'@import',text,re.I) or any(not value.strip(' \"\'').startswith('#') for value in re.findall(r'url\(([^)]*)\)',text,re.I)):raise ValueError('SVG 不能引用外部样式或资源。')
    svg_size(root)
   except (ET.ParseError,UnicodeError,TypeError) as error:raise ValueError('无法读取 SVG 图片。') from error
  else:
   try:
    with Image.open(io.BytesIO(data)) as image:
     if image.format!={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.webp':'WEBP'}[suffix]:raise ValueError('素材内容与文件扩展名不一致。')
     image.verify()
   except (OSError,Image.DecompressionBombError) as error:raise ValueError('无法读取图片，文件可能损坏或尺寸过大。') from error
  sha=hashlib.sha256(data).hexdigest();ident=sha[:24]
  with self.lock:
   if ident in self.index:
    self.pin(ident);return {'asset':dict(self.get(ident)),'reused':True}
   self.imports.mkdir(parents=True,exist_ok=True)
   stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',Path(name).stem).strip(' .')[:100] or 'material'
   path=self.imports/f'{ident}_{stem}{suffix}';tmp=self.imports/(uuid.uuid4().hex+'.tmp')
   try:
    with tmp.open('wb') as stream:stream.write(data);stream.flush();__import__('os').fsync(stream.fileno())
    tmp.replace(path)
   finally:
    if tmp.exists():tmp.unlink()
   self.refresh();self.pin(ident)
   with (self.cache/'imports.jsonl').open('a',encoding='utf8') as log:log.write(json.dumps({'time':datetime.now(timezone.utc).isoformat(),'original_filename':name,'source':path.relative_to(ROOT).as_posix(),'sha256':sha,'bytes':len(data),'asset_id':ident},ensure_ascii=False)+'\n')
   return {'asset':dict(self.get(ident)),'reused':False}
 def list(self):return list(self.index.values())
 def get(self,ident):
  if not isinstance(ident,str) or ident not in self.index:raise ValueError('素材不在当前模型项目的素材库中，请刷新素材库。')
  return self.index[ident]
 def path(self,ident):
  row=self.get(ident);p=self.cache/'originals'/f"{ident}{row['suffix']}"
  shared=self.store.path(row['sha256'],row['suffix'])
  return shared if shared.is_file() else p if p.is_file() else ROOT/row['source']
 def pin(self,ident):
  with self.lock:
   row=self.get(ident);p=self.cache/'originals'/f"{ident}{row['suffix']}"
   shared=self.store.path(row['sha256'],row['suffix'])
   if shared.is_file():
    if digest(shared)!=row['sha256']:raise ValueError('素材缓存校验失败。')
   else:
    source=p if p.is_file() else ROOT/row['source'];assert source.resolve().is_relative_to(ROOT.resolve())
    shared,_,_=self.store.put_file(source,expected=row['sha256'],adopt=source==p)
   # Project indexes and layout asset IDs stay unchanged. Only the redundant
   # legacy cache entry goes away after the shared byte-exact snapshot exists.
   if p.is_file():
    if digest(p)!=row['sha256']:raise ValueError('旧素材缓存校验失败。')
    p.unlink()
   return shared
 def thumbnail(self,ident):
  row=self.get(ident);p=self.cache/'thumbnails'/f'{ident}.png'
  with self.lock:
   if not p.exists():
    source=self.path(ident)
    if row['suffix']=='.svg':
     w,h=row['size'];ratio=min(300/w,210/h);p.write_bytes(resvg_py.svg_to_bytes(svg_path=str(source),width=max(1,round(w*ratio)),height=max(1,round(h*ratio)),font_files=font_files(),skip_system_fonts=False))
    else:
     with Image.open(source) as im:
      thumb=ImageOps.exif_transpose(im);thumb.thumbnail((300,210),Image.Resampling.LANCZOS);thumb.save(p,format='PNG')
   return p
 def display_svg(self,ident):
  row=self.get(ident)
  if row['suffix']!='.svg':raise ValueError('该素材不是矢量图。')
  return self.path(ident).read_bytes()
