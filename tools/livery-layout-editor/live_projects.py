"""Cheap revision polling, fresh project payloads and optimistic save tokens."""
from pathlib import Path
import copy,hashlib,json,os,threading,xml.etree.ElementTree as ET
from urllib.parse import quote

from runtime import ROOT,HERE
WEB=HERE/'web'
IMAGES={'.svg','.png','.jpg','.jpeg','.webp','.avif'}

def fingerprint(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()

def state_revision(path):
 try:return hashlib.sha256(Path(path).read_bytes()).hexdigest()
 except FileNotFoundError:return 'missing'

def stat_row(path):
 path=Path(path)
 try:
  s=path.stat();return [str(path),s.st_size,s.st_mtime_ns,s.st_ino]
 except FileNotFoundError:return [str(path),'missing']

def tree_rows(folder,suffixes=None):
 folder=Path(folder);rows=[]
 if not folder.is_dir():return [stat_row(folder)]
 for directory,dirs,files in os.walk(folder,followlinks=False):
  dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in ('node_modules','__pycache__'))
  for name in sorted(files):
   p=Path(directory)/name
   if suffixes is None or p.suffix.lower() in suffixes:rows.append(stat_row(p))
 return rows

def index_revision(path):
 try:return fingerprint(json.loads(Path(path).read_text(encoding='utf-8')))
 except FileNotFoundError:return 'missing'

class LiveProjects:
 def __init__(self,manager,root=None,web=None):
  self.manager=manager;self.root=Path(root) if root else ROOT;self.web=Path(web) if web else WEB;self.loaded={};self.lock=threading.RLock()
 def registry(self):
  path=self.root/'projects/registry.json'
  if path.is_file():
   data=json.loads(path.read_text(encoding='utf-8'))
   with self.manager.lock:self.manager.registry=data
  return copy.deepcopy(self.manager.registry)
 def revision(self,pid):
  registry=self.registry()
  if pid not in registry['projects']:raise ValueError('项目不存在或已移除。')
  config=registry['projects'][pid];folder=self.root/config['directory'];surface=folder/config.get('surface_directory','surfaces/v1')
  state_dir=folder/'state'/('surface-'+surface.name) if config['type']=='surface-planes' else folder/'state'
  sources=[config,stat_row(state_dir/'render-settings.json')]
  if config['type']=='surface-planes':
   sources.extend([stat_row(surface/'contract.json'),tree_rows(surface/'sources'),tree_rows(surface/'masks'),tree_rows(surface/'guides'),tree_rows(surface/'previews'),tree_rows(surface/'capture',IMAGES)])
   if (surface/'contract.json').is_file():
    contract=json.loads((surface/'contract.json').read_text(encoding='utf-8'))
    for key in ('native_contract','capture_bindings'):
     if contract.get(key):sources.append(stat_row((surface if key=='capture_bindings' else folder)/contract[key]))
  elif config['type'] in ['native-uv','boards']:
   sources.extend([stat_row(folder/'model-project.json'),tree_rows(folder/'sources'),tree_rows(folder/'masks'),tree_rows(folder/'guides'),tree_rows(folder/'previews',IMAGES)])
  else:
   cached=getattr(self.manager,'cache',{}).get(pid)
   if cached:
    sources.extend(stat_row(cached.source_path(key)) for key in cached.regions)
   cache=self.root/'tools/livery-layout-editor/cache'
   sources.extend(stat_row(p) for p in sorted(cache.glob('*/contract.json')))
  roots=list(config.get('asset_roots',[]))+[str(folder/'assets/imported')]
  library=registry.get('libraries',{}).get(config.get('shared_library'),{})
  roots.extend(library.get('roots',[]))
  if library.get('imports'):roots.append(library['imports'])
  for r in sorted(set(roots)):sources.append(tree_rows(self.root/r,IMAGES))
  # AssetLibrary writes this index after a scan. Hash its JSON content, so an
  # identical scan cannot trigger an endless reload loop via a changed mtime.
  sources.append(index_revision(folder/'cache/asset-library/index.json'))
  result={'project_id':pid,'design_revision':fingerprint(sources),'state_revision':state_revision(state_dir/'current.json'),'registry_revision':fingerprint(registry),'ui_revision':fingerprint(tree_rows(self.web,{'.js','.html'})),'style_revision':fingerprint(tree_rows(self.web,{'.css'}))}
  result['revision']=fingerprint(result);return result
 def payload(self,pid):
  with self.lock:
   for attempt in range(2):
    before=self.revision(pid)
    with self.manager.lock:
     if self.loaded.get(pid)!=before['design_revision']:self.manager.cache.pop(pid,None)
     try:project=self.manager.get(pid);data=self.manager.payload(project)
     except ET.ParseError as e:raise ValueError('后台源稿尚未写入完整，请稍后同步。') from e
    after=self.revision(pid);stable=all(before[k]==after[k] for k in ('design_revision','state_revision'))
    self.loaded[pid]=after['design_revision']
    if stable:break
    self.loaded.pop(pid,None)
   data['live']={**after,'stable':stable}
   for row in [*data.get('regions',[]),*data.get('assets',[])]:
    for key,value in list(row.items()):
     if key.endswith('_url') or key=='url':
      if isinstance(value,str) and value.startswith('/'):row[key]=value+('&' if '?' in value else '?')+'v='+quote(after['design_revision'])
   return data

def save_conflict(data,current):
 return any(data.get(field) is not None and data[field]!=current[revision]
            for field,revision in [('base_state_revision','state_revision'),('base_design_revision','design_revision')])
