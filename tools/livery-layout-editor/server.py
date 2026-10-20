"""Local editor: each request and background job carries an explicit project."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote,parse_qs,quote
from datetime import datetime,timezone,timedelta
import argparse,gzip,json,mimetypes,re,subprocess,sys,threading,uuid,os,ctypes,copy,shutil
os.environ['PYTHONUTF8']='1';os.environ['PYTHONIOENCODING']='utf-8'
if sys.stdout:sys.stdout.reconfigure(encoding='utf8',errors='replace')
if sys.stderr:sys.stderr.reconfigure(encoding='utf8',errors='replace')
from project import HERE,ROOT,STATE,read,write_json
from projects import ProjectManager,scoped
from assets import UPLOAD_LIMIT
from export_selection import catalogue,validate_selection
from export_acceleration import validate as validate_acceleration,availability as acceleration_availability
from storage import validate_mode,save_layout,archive_recipe,archive_entries,stream_archive
from live_projects import save_conflict,state_revision
from PIL import Image
MANAGER=ProjectManager();LOCK=threading.RLock()
from studio_api import StudioAPI
STUDIO=StudioAPI(MANAGER)
def now():return datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
def within(path,root):
 path=Path(path).resolve()
 if not path.is_relative_to(Path(root).resolve()):raise ValueError('路径不属于当前项目目录。')
 return path
def job_path(p,job):
 if not re.fullmatch(r'job-[0-9]{8}-[0-9]{6}-[a-z0-9][a-z0-9_-]{2,80}',job):raise ValueError('生成记录不存在。')
 target=within(p.jobs/job,p.jobs)
 if not target.exists() and p.config.get('legacy_jobs'):target=within(ROOT/p.config['legacy_jobs']/job,ROOT/p.config['legacy_jobs'])
 return target
def process_alive(pid):
 if not pid:return False
 if os.name=='nt':
  from ctypes import wintypes
  k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=wintypes.HANDLE;k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];k.CloseHandle.argtypes=[wintypes.HANDLE];h=k.OpenProcess(0x1000,False,int(pid))
  if not h:return False
  try:code=wintypes.DWORD();return bool(k.GetExitCodeProcess(h,ctypes.byref(code))) and code.value==259
  finally:k.CloseHandle(h)
 try:os.kill(int(pid),0);return True
 except OSError:return False
def display_job(p,job):
 job=copy.deepcopy(job);job['project_id']=p.id
 for row in [*job.get('files',[]),*job.get('previews',[])]:
  if row.get('url') and 'project=' not in row['url']:row['url']=scoped(row['url'],p.id)
 return job
def job_list(p):
 roots=[p.jobs]+([ROOT/p.config['legacy_jobs']] if p.config.get('legacy_jobs') else []);out=[]
 for f in sorted([f for root in roots for f in root.glob('job-*/job.json')],key=lambda f:f.parent.name,reverse=True)[:40]:
  try:
   job=read(f)
   if job['status'] in ['queued','running']:
    age=(datetime.now(timezone(timedelta(hours=8)))-datetime.strptime(job['created'],'%Y%m%d-%H%M%S').replace(tzinfo=timezone(timedelta(hours=8)))).total_seconds()
    if age>60 and not process_alive(job.get('pid')):job.update(status='failed',stage='后台任务已中断',error='后台进程已退出，可重新生成；已有文件仍保留。');write_json(f,job)
   out.append(display_job(p,job))
  except (OSError,json.JSONDecodeError,KeyError):continue
 return out
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def project(self,metadata_only=False):
  ident=parse_qs(urlparse(self.path).query).get('project',[None])[0]
  return MANAGER.job_context(ident) if metadata_only else MANAGER.get(ident)
 def respond(self,data,status=200,mime='application/json; charset=utf-8',download=None):
  if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False).encode('utf8')
  elif isinstance(data,str):data=data.encode('utf8')
  compressed=len(data)>20000 and ('json' in mime or 'svg' in mime) and 'gzip' in self.headers.get('Accept-Encoding','')
  if compressed:data=gzip.compress(data,compresslevel=1)
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff')
  if compressed:self.send_header('Content-Encoding','gzip')
  if download:self.send_header('Content-Disposition',f'attachment; filename="{download}"')
  self.end_headers()
  try:self.wfile.write(data)
  except (BrokenPipeError,ConnectionAbortedError,ConnectionResetError):pass
 def file(self,p,download=None):
  if not p.is_file():return self.respond({'error':'文件尚未生成。'},404)
  with p.open('rb') as source:
   self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(p))[0] or 'application/octet-stream');self.send_header('Content-Length',str(os.fstat(source.fileno()).st_size));self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff')
   if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(download))
   self.end_headers()
   try:shutil.copyfileobj(source,self.wfile,1024*1024)
   except (BrokenPipeError,ConnectionAbortedError,ConnectionResetError):pass
 def archive(self,folder,name):
  compression,entries=archive_entries(folder,name)
  self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(name));self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.close_connection=True
  try:stream_archive(self.wfile,compression,entries)
  except (OSError,BrokenPipeError,ConnectionAbortedError,ConnectionResetError):pass
 def do_GET(self):
  try:
   STUDIO.guard(self)
   path=unquote(urlparse(self.path).path)
   if STUDIO.get(self,path):return
   if path in ['/studio.js','/studio.css','/storage-ui.js','/live-refresh.js','/i18n.js','/locales/en.js','/settings-ui.js']:return self.file(HERE/'web'/path[1:])
   if path in ['/','/index.html','/app.js','/style.css','/fonts.css','/extras.css','/transform.js','/shadow.js','/export-files.js','/export-gpu.js']:return self.file(HERE/'web'/('index.html' if path=='/' else path[1:]))
   if path=='/api/projects':return self.respond(MANAGER.listing())
   if path=='/api/project':return self.respond(STUDIO.live.payload(parse_qs(urlparse(self.path).query).get('project',[MANAGER.registry['active_project']])[0]))
   if path=='/api/export-acceleration':return self.respond(acceleration_availability())
   p=self.project(metadata_only=path=='/api/jobs' or path.startswith(('/api/jobs/','/job/')))
   if path=='/api/project':return self.respond(MANAGER.payload(p))
   if path=='/api/export-files':
    preset=parse_qs(urlparse(self.path).query).get('channels',['color'])[0]
    return self.respond({'project_id':p.id,'preset':preset,'files':catalogue(p,preset)})
   if path=='/api/assets':
    rows=copy.deepcopy(p.library.refresh() if parse_qs(urlparse(self.path).query).get('refresh')==['1'] else p.library.list())
    if hasattr(p,'editing_assets'):rows=p.editing_assets(rows)
    for row in rows:
     for k in ['url','canvas_url','thumbnail_url']:row[k]=scoped(row[k],p.id)
    return self.respond({'assets':rows})
   if path.startswith('/asset/'):return self.file(p.library.path(path.rsplit('/',1)[-1]))
   if path.startswith('/asset-display/'):return self.respond(p.library.display_svg(path.rsplit('/',1)[-1]),mime='image/svg+xml')
   if path.startswith('/asset-thumb/'):return self.file(p.library.thumbnail(path.rsplit('/',1)[-1].removesuffix('.png')))
   if path=='/api/jobs':return self.respond(job_list(p))
   if path=='/api/draft':return self.respond(p.load_state(),download=p.id+'-layout.json')
   if path=='/api/model':
    ext=parse_qs(urlparse(self.path).query).get('format',['blend'])[0];target=next((ROOT/m for m in p.config.get('models',[]) if Path(m).suffix=='.'+ext),None)
    if target is None:raise ValueError('当前项目没有该格式模型。')
    return self.file(target,download=target.name)
   if path=='/api/model-manifest':return self.file(p.root/p.contract['repair_manifest'],download=p.id+'-repair-manifest.json') if p.config['type'] in ['native-uv','surface-planes'] else self.respond({'project':p.config})
   if path.startswith('/surface-mask/'):
    key=path.rsplit('/',1)[-1].removesuffix('.png')
    if p.config['type']!='surface-planes' or key not in p.regions:raise ValueError('未知模块平面遮罩。')
    return self.file(p.surface_root/'masks'/f'{key}.png')
   if path.startswith('/native-mask/'):
    key=path.rsplit('/',1)[-1].removesuffix('.png')
    if p.config['type']!='native-uv' or key not in p.regions:raise ValueError('未知原 UV 遮罩。')
    return self.file(p.root/'masks'/f'{key}.png')
   if path=='/api/checkpoints':return self.respond([dict(id=f.stem,title=read(f).get('title',f.stem)) for f in sorted((p.state_dir/'checkpoints').glob('*.json'),reverse=True)][:60])
   if path.startswith('/api/checkpoint/'):
    ident=path.rsplit('/',1)[-1]
    if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{6}',ident):raise ValueError('存档标识无效。')
    return self.respond(p.validate(read(p.state_dir/'checkpoints'/f'{ident}.json')))
   if path.startswith('/api/jobs/'):return self.respond(display_job(p,read(job_path(p,path.rsplit('/',1)[-1])/'job.json')))
   for prefix,suffix in [('/source/','.svg'),('/guide/','.svg'),('/thumb/','.png')]:
    if path.startswith(prefix):
     key=path[len(prefix):].removesuffix(suffix)
     if key not in p.regions or path!=prefix+key+suffix:raise ValueError('未知分区。')
     if prefix=='/source/':return self.file(p.source_path(key))
     return self.file((p.surface_root if p.config['type']=='surface-planes' else p.root)/('guides' if prefix=='/guide/' else 'previews')/f'{key}{suffix}')
   if path.startswith('/reference/'):
    name=path.rsplit('/',1)[-1]
    if p.config['type']=='surface-planes':
     if name not in {Path(r['reference_url']).name for r in p.regions.values()}:raise ValueError('未知模块平面参考。')
     return self.file(p.surface_root/'capture'/name)
    if p.config['type']=='native-uv':
     if name!='assembled.png':raise ValueError('未知模型参考。')
     return self.file(p.root/'previews'/name)
    if name not in {Path(r['reference_url']).name for r in p.regions.values()}:raise ValueError('参考图不存在。')
    return self.file(p.root/'previews'/name)
   if path.startswith('/job/'):
    pieces=path.split('/',3);folder=job_path(p,pieces[2]);target=within(folder/pieces[3],folder)
    if target.parent==folder and target.suffix.lower()=='.zip' and archive_recipe(folder,target.name).is_file():return self.archive(folder,target.name)
    return self.file(target,download=target.name if target.suffix=='.zip' else None)
   return self.respond({'error':'未找到。'},404)
  except (ValueError,KeyError,OSError,TypeError,RuntimeError,TimeoutError,json.JSONDecodeError) as e:self.respond({'error':str(e)},400)
 def do_POST(self):
  try:
   STUDIO.guard(self)
   origin=self.headers.get('Origin');host=self.headers.get('Host')
   if origin and urlparse(origin).netloc!=host:return self.respond({'error':'只允许本地编辑器提交。'},403)
   path=urlparse(self.path).path
   if STUDIO.post(self,path):return
   p=self.project()
   if path=='/api/assets/import':
    name=parse_qs(urlparse(self.path).query).get('filename',[''])[0];n=int(self.headers.get('Content-Length','0'))
    if not name or not 0<n<=UPLOAD_LIMIT:raise ValueError('请选择素材文件，最大 64 MB。')
    payload=self.rfile.read(n)
    if len(payload)!=n:raise ValueError('素材上传不完整。')
    result=p.library.import_file(name,payload);result['asset']=copy.deepcopy(result['asset'])
    for k in ['url','canvas_url','thumbnail_url']:result['asset'][k]=scoped(result['asset'][k],p.id)
    return self.respond(result,201)
   if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('请求应为 JSON。')
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<2_000_000:raise ValueError('布局数据大小无效。')
   data=json.loads(self.rfile.read(n))
   if path=='/api/projects/switch':MANAGER.switch(data['project_id']);return self.respond(STUDIO.live.payload(data['project_id']))
   if path=='/api/projects/library':MANAGER.select_library(p.id,data.get('library_id'));return self.respond(STUDIO.live.payload(p.id))
   if path=='/api/save':
    with LOCK:
     current=STUDIO.live.revision(p.id) if 'base_state_revision' in data or 'base_design_revision' in data else None
     if current and save_conflict(data,current):return self.respond({'error':'后台设计已更新，已保留本地修改；请先备份并读取新版本。','conflict':True,'live':current},409)
     state=p.validate(data['state'])
     if current and save_conflict(data,STUDIO.live.revision(p.id)):return self.respond({'error':'后台设计在保存期间更新，已保留本地修改；请先备份并刷新。','conflict':True,'live':STUDIO.live.revision(p.id)},409)
     result=save_layout(p,state,data.get('checkpoint'),now());ident=result['checkpoint']
     if result['changed'] or (ident and not result['reused']):
      with (p.state_dir/'operations.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(time=now(),project_id=p.id,action='checkpoint' if ident else 'autosave',checkpoint=ident,changed_regions=[k for k in p.regions if p.changed(state,k)]),ensure_ascii=False)+'\n')
    return self.respond(dict(saved=True,**result,time=now(),project_id=p.id,state_revision=state_revision(p.state_dir/'current.json'),**({'design_revision':current['design_revision']} if current else {})))
   state=p.validate(data['state'])
   if path=='/api/jobs':
    mode=data.get('mode');region=data.get('region',state['active_region']);preset=data.get('export_channels','color')
    if mode not in ['boards','preview','4k','8k'] or region not in p.regions:raise ValueError('生成选项无效。')
    if p.config['type']=='boards' and mode!='boards':raise ValueError('草图项目只支持平面输出。请先建立模型绑定项目。')
    if preset not in ['color','color-normal','pbr']:raise ValueError('贴图通道选项无效。')
    acceleration=validate_acceleration(data.get('export_acceleration','cpu'))
    storage_mode=validate_mode(data.get('storage_mode','compact'))
    if acceleration=='gpu' and (p.config['type']!='surface-planes' or mode=='boards'):raise ValueError('GPU 贴图加速适用于平面设计项目的模型预览或原 UV 图集导出。')
    export_files=validate_selection(data.get('export_files'),catalogue(p,preset)) if mode in ['4k','8k'] and data.get('export_files') is not None else None
    with LOCK:
     if any(j['status'] in ['queued','running'] for c in MANAGER.registry['projects'] for j in job_list(MANAGER.job_context(c))):return self.respond({'error':'已有后台任务正在运行，切换项目不会影响它。'},409)
     ident='job-'+now()+'-'+uuid.uuid4().hex[:6];folder=p.jobs/ident;folder.mkdir();write_json(folder/'layout.json',state);write_json(folder/'project-config.json',p.config);write_json(p.state_dir/'current.json',state);(folder/'evidence').mkdir();shutil.copy2(p.state_dir/'render-settings.json',folder/'evidence/render-settings.json')
     job=dict(id=ident,project_id=p.id,mode=mode,region=region,export_channels=preset,export_files=export_files,export_acceleration=acceleration,storage_mode=storage_mode,status='queued',progress=0,stage='准备生成',output_dir=str(folder),created=now(),files=[],previews=[],log=[]);write_json(folder/'job.json',job)
     script='boards_worker.py' if p.config['type']=='boards' else 'surface_worker.py' if p.config['type']=='surface-planes' else 'native_worker.py'
     with (folder/'worker.log').open('wb') as log:subprocess.Popen([sys.executable,str(HERE/script),'--job',str(folder)],cwd=str(ROOT),stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    return self.respond(display_job(p,job),202)
   return self.respond({'error':'接口不存在。'},404)
  except (ValueError,KeyError,TypeError,OSError,RuntimeError,TimeoutError,json.JSONDecodeError) as e:self.respond({'error':str(e)},400)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18188);args=parser.parse_args();server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
 write_json(STATE/('server.json' if args.port==18188 else f'server-{args.port}.json'),dict(pid=os.getpid(),port=args.port,url=f'http://127.0.0.1:{args.port}',editor_version=19));print(f'布局编辑器: http://127.0.0.1:{args.port}',flush=True);server.serve_forever()
