"""Content-addressed immutable resources and download-time ZIP recipes.

User-editable sources, models and final export/ files are never hard-linked.
Only generated cache images share blocks; a retry detaches them before writing.
"""
from pathlib import Path
import hashlib,json,os,re,shutil,threading,uuid,zipfile

from runtime import ROOT
STORE=ROOT/'projects/_shared/content-store/v1'
IMAGE_SUFFIXES={'.png','.jpg','.jpeg','.webp','.exr','.tga','.dds','.svg'}
CACHE_DIRS=('planes','textures','materials','assets','previews')
_lock=threading.RLock()

def digest(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def write_json(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with tmp.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)

def validate_mode(value):
 if value not in ('compact','portable'):raise ValueError('存档方式应为轻量存档或独立副本。')
 return value

def is_compact(folder):
 try:return json.loads((Path(folder)/'job.json').read_text(encoding='utf-8')).get('storage_mode')=='compact'
 except FileNotFoundError:return False  # Historical jobs keep their original policy.

class ContentStore:
 def __init__(self,root=None):self.root=Path(root) if root else STORE
 def path(self,sha,suffix):
  if not re.fullmatch(r'[0-9a-f]{64}',sha) or not re.fullmatch(r'\.[a-z0-9]{1,10}',suffix.lower()):raise ValueError('资源摘要或扩展名无效。')
  return self.root/'blobs'/sha[:2]/(sha+suffix.lower())
 def put_file(self,source,expected=None,adopt=False):
  source=Path(source);sha=digest(source)
  if expected and sha!=expected:raise ValueError('资源已变化，不能覆盖已有存档：'+str(source))
  target=self.path(sha,source.suffix);target.parent.mkdir(parents=True,exist_ok=True)
  with _lock:
   if target.exists():
    if not os.path.samefile(source,target) and digest(target)!=sha:raise ValueError('共享资源校验失败：'+str(target))
    return target,sha,False
   tmp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
   try:
    if adopt and source.stat().st_nlink==1:
     try:os.link(source,tmp)
     except OSError:shutil.copy2(source,tmp)
    else:shutil.copy2(source,tmp)
    if digest(tmp)!=sha:raise ValueError('保存期间源资源发生变化：'+str(source))
    os.replace(tmp,target)
   finally:tmp.unlink(missing_ok=True)
  return target,sha,True
 def put_bytes(self,data,suffix):
  sha=hashlib.sha256(data).hexdigest();target=self.path(sha,suffix);target.parent.mkdir(parents=True,exist_ok=True)
  with _lock:
   if target.exists():
    if digest(target)!=sha:raise ValueError('共享资源校验失败：'+str(target))
   else:
    tmp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
     with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
     os.replace(tmp,target)
    finally:tmp.unlink(missing_ok=True)
  return target,sha

def private_copy(path):
 """Break a shared inode before a managed writer edits an existing cache."""
 path=Path(path)
 if not path.is_file() or path.stat().st_nlink<2:return False
 tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.private')
 try:shutil.copy2(path,tmp);os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)
 return True

def cache_files(folder):
 for name in CACHE_DIRS:
  for p in (Path(folder)/name).rglob('*'):
   if p.is_file() and not p.is_symlink() and p.suffix.lower() in IMAGE_SUFFIXES:yield p

def prepare_job(folder):
 for p in cache_files(folder):private_copy(p)

def reuse_file(source,target,folder,allow_link=True):
 """Atomic reuse; a portable task receives a private copy, never a shared inode."""
 source=Path(source);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 if source.resolve()==target.resolve():return
 tmp=target.with_name(target.name+'.'+uuid.uuid4().hex+'.reuse')
 try:
  if allow_link and is_compact(folder):
   try:os.link(source,tmp)
   except OSError:shutil.copy2(source,tmp)
  else:shutil.copy2(source,tmp)
  os.replace(tmp,target)
 finally:tmp.unlink(missing_ok=True)

def compact_job(folder):
 folder=Path(folder)
 if not is_compact(folder):return None
 store=ContentStore();rows=[];reclaimed=0;fallbacks=0
 for p in cache_files(folder):
  before=p.stat();blob,sha,created=store.put_file(p,adopt=True);shared=os.path.samefile(p,blob)
  if not shared:
   tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.link')
   try:os.link(blob,tmp);os.replace(tmp,p);shared=True
   except OSError:fallbacks+=1
   finally:tmp.unlink(missing_ok=True)
   if shared and before.st_nlink==1 and not created:reclaimed+=before.st_size
  rows.append({'file':p.relative_to(folder).as_posix(),'sha256':sha,'bytes':before.st_size,'blob':str(blob),'shared':shared})
 report={'schema':'livery-storage/v1','mode':'compact','policy':'Immutable generated cache images share content-addressed blobs; editable sources, models and export PNGs remain private','files':rows,'shared_file_count':sum(r['shared'] for r in rows),'shared_logical_bytes':sum(r['bytes'] for r in rows if r['shared']),'reclaimed_duplicate_bytes':reclaimed,'link_fallbacks':fallbacks,'archives':'Built only while downloading; no persistent ZIP copy'}
 write_json(folder/'evidence/storage.json',report);return report

def archive_recipe(folder,name):
 if Path(name).name!=name or not name.lower().endswith('.zip'):raise ValueError('压缩包名称无效。')
 return Path(folder)/'.archives'/(name+'.json')

def register_archive(folder,name,entries,compression=zipfile.ZIP_DEFLATED):
 """entries: [(source path, archive member name)]. Keep portable ZIPs on disk."""
 folder=Path(folder).resolve();rows=[];names=set()
 for source,member in entries:
  source=Path(source).resolve();member=str(member).replace('\\','/');parts=member.split('/')
  if not source.is_relative_to(folder) or not source.is_file() or not member or any(p in ('','..','.') for p in parts) or ':' in member or member.casefold() in names:raise ValueError('压缩包文件路径无效：'+member)
  names.add(member.casefold());rows.append({'file':source.relative_to(folder).as_posix(),'member':member,'bytes':source.stat().st_size})
 dest=folder/name
 if is_compact(folder):
  write_json(archive_recipe(folder,name),{'schema':'livery-archive/v1','compression':compression,'entries':rows})
  # Only a regenerated recipe in this same task supersedes an old physical ZIP.
  dest.unlink(missing_ok=True)
 else:
  tmp=dest.with_name(dest.name+'.'+uuid.uuid4().hex+'.tmp')
  try:
   with zipfile.ZipFile(tmp,'w',compression,compresslevel=1) as z:
    for row in rows:z.write(folder/row['file'],row['member'])
   os.replace(tmp,dest)
  finally:tmp.unlink(missing_ok=True)
 return dest

def archive_entries(folder,name):
 folder=Path(folder).resolve();data=json.loads(archive_recipe(folder,name).read_text(encoding='utf-8'));rows=[];names=set()
 if data.get('schema')!='livery-archive/v1' or data.get('compression') not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):raise ValueError('压缩包记录无效。')
 for row in data['entries']:
  p=(folder/row['file']).resolve();member=row['member'];parts=member.split('/')
  if not p.is_relative_to(folder) or not p.is_file():raise ValueError('存档依赖缺失：'+row['file'])
  if not member or any(v in ('','..','.') for v in parts) or '\\' in member or ':' in member or member.casefold() in names:raise ValueError('压缩包路径无效。')
  if p.stat().st_size!=row['bytes']:raise ValueError('存档文件已变化，请重新生成：'+row['file'])
  names.add(member.casefold());rows.append((p,member))
 return data['compression'],rows

def stream_archive(handle,compression,entries):
 """ZipFile supports non-seekable HTTP streams and writes ZIP64 when needed."""
 with zipfile.ZipFile(handle,'w',compression,compresslevel=1,allowZip64=True) as z:
  for p,member in entries:z.write(p,member)

def save_layout(project,state,checkpoint,stamp):
 """Parameter-only checkpoints. An identical save reuses the same revision."""
 current=project.state_dir/'current.json';changed=True;ident=None;reused=False
 try:changed=json.loads(current.read_text(encoding='utf-8'))!=state
 except (FileNotFoundError,json.JSONDecodeError):pass
 if changed:write_json(current,state)
 if checkpoint:
  directory=project.state_dir/'checkpoints';directory.mkdir(parents=True,exist_ok=True)
  for f in sorted(directory.glob('*.json'),reverse=True):
   try:
    if json.loads(f.read_text(encoding='utf-8'))==state:ident=f.stem;reused=True;break
   except (OSError,json.JSONDecodeError):continue
  if ident is None:ident=stamp+'-'+uuid.uuid4().hex[:6];write_json(directory/(ident+'.json'),state)
 return {'checkpoint':ident,'reused':reused,'changed':changed}
