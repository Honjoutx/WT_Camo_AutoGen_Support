"""Local Codex app-server transport; credentials stay in the existing CLI."""
from pathlib import Path
from datetime import datetime,timezone
import atexit,copy,json,os,queue,re,shutil,subprocess,threading,uuid
from external_process import popen as external_popen
from project import ROOT, HERE, read, write_json
from workflow import context,CORE_RULES

def stamp():return datetime.now(timezone.utc).isoformat()
def executable():
 from runtime import codex_executable
 return codex_executable()

class CodexProcess:
 def __init__(self,callback):
  self.callback=callback;self.process=None;self.pending={};self.next_id=0;self.write_lock=threading.Lock();self.start_lock=threading.RLock();self.generation=0;self.errors=[];self.mcp_args=[];self.binary=None
 def send(self,data):
  with self.write_lock:
   if not self.process or self.process.poll() is not None:raise RuntimeError('Codex 后台进程未运行。')
   self.process.stdin.write(json.dumps(data,ensure_ascii=False)+'\n');self.process.stdin.flush()
 def rpc(self,method,params=None,timeout=40):
  with self.write_lock:self.next_id+=1;ident=self.next_id
  q=queue.Queue(maxsize=1);self.pending[ident]=q
  try:
   self.send({'id':ident,'method':method,'params':params or {}})
   try:r=q.get(timeout=timeout)
   except queue.Empty:raise TimeoutError('Codex 请求超时：'+method)
   if 'error' in r:raise RuntimeError(r['error'].get('message',str(r['error'])))
   return r.get('result',{})
  finally:self.pending.pop(ident,None)
 def ensure(self):
  with self.start_lock:
   if self.process and self.process.poll() is None:return
   binary=executable();self.binary=binary;self.generation+=1;generation=self.generation
   from blender_connection import app_server_args
   self.mcp_args=app_server_args()
   self.process=external_popen([binary,'app-server','--listen','stdio://',*self.mcp_args],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
   proc=self.process
   def stdout():
    try:
     for line in proc.stdout:
      try:r=json.loads(line)
      except json.JSONDecodeError:continue
      if 'method' not in r and r.get('id') in self.pending:self.pending[r['id']].put(r)
      elif r.get('method'):self.callback(r,generation)
    finally:
     for q in list(self.pending.values()):
      try:q.put_nowait({'error':{'message':'Codex 进程已退出，请重新连接。'}})
      except queue.Full:pass
     self.callback({'method':'bridge/disconnected','params':{}},generation)
   def stderr():
    for line in proc.stderr:
     self.errors=(self.errors+[line.strip()])[-8:]
   threading.Thread(target=stdout,daemon=True).start();threading.Thread(target=stderr,daemon=True).start()
   self.rpc('initialize',{'clientInfo':{'name':'livery_studio','title':'Livery Studio','version':'2.0.0'}},25)
   self.send({'method':'initialized','params':{}})
 def close(self):
  if self.process and self.process.poll() is None:
   self.process.terminate()
   try:self.process.wait(timeout=4)
   except subprocess.TimeoutExpired:self.process.kill()

class ChatService:
 def __init__(self,manager):
  self.manager=manager;self.lock=threading.RLock();self.sessions={};self.process=CodexProcess(self.event);self.loaded={};atexit.register(self.process.close)
 def root(self,pid):
  p=ROOT/self.manager.config(pid)['directory']/'state/codex';p.mkdir(parents=True,exist_ok=True);return p
 def path(self,pid,cid):
  if not re.fullmatch(r'chat-[a-f0-9]{16}',cid or ''):raise ValueError('会话标识无效。')
  return self.root(pid)/(cid+'.json')
 def get(self,pid,cid):
  with self.lock:
   key=(pid,cid)
   if key not in self.sessions:
    value=read(self.path(pid,cid))
    if value['project_id']!=pid:raise ValueError('不能跨项目读取对话。')
    if value.get('busy'):value.update(busy=False,turn_id=None);value['events'].append({'seq':len(value['events'])+1,'method':'bridge/interrupted','params':{'message':'服务重启，上一轮已中断；可继续会话。'}})
    value['requests']={};self.sessions[key]=value
   return self.sessions[key]
 def persist(self,s):
  # Atomic replace prevents a server interruption from corrupting conversation history.
  path=self.path(s['project_id'],s['id']);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8');os.replace(tmp,path)
 def append(self,s,method,params):
  s['events'].append({'seq':len(s['events'])+1,'method':method,'params':params,'time':stamp()});s['updated']=stamp();self.persist(s)
 def listing(self,pid):
  out=[]
  for p in self.root(pid).glob('chat-*.json'):
   try:
    s=self.get(pid,p.stem)
    if not s.get('archived'):out.append({k:s.get(k) for k in ['id','title','updated','busy','thread_id','model']})
   except (ValueError,OSError,json.JSONDecodeError):continue
  return sorted(out,key=lambda s:s['updated'],reverse=True)
 def status(self,connect=False):
  result={'available':False,'connected':bool(self.process.process and self.process.process.poll() is None),'transport':'codex app-server / stdio','models':[]}
  from blender_connection import status as blender_status,codex_status
  result['blender_mcp']=blender_status()
  try:
   result['executable']=executable();result['available']=True
   if connect:
    from blender_connection import app_server_args
    with self.lock:
     if not any(s.get('busy') for s in self.sessions.values()) and (self.process.mcp_args!=app_server_args() or self.process.binary!=executable()):self.process.close()
    self.process.ensure();result['connected']=True
    account=self.process.rpc('account/read',{'refreshToken':False})
    a=account.get('account');result['signed_in']=bool(a);result['auth_type']=a.get('type') if a else None;result['requires_auth']=account.get('requiresOpenaiAuth',True)
    result['models']=self.process.rpc('model/list',{'limit':100}).get('data',[])
    if result['blender_mcp']['installed']:
     try:result['blender_mcp']['codex']=codex_status(self.process)
     except (RuntimeError,OSError,TimeoutError) as e:result['blender_mcp']['codex']={'ready':False,'error':str(e)}
  except (RuntimeError,OSError,TimeoutError) as e:result['error']=str(e)
  return result
 def create(self,pid,title='新对话'):
  self.manager.config(pid)
  s={'id':'chat-'+uuid.uuid4().hex[:16],'project_id':pid,'title':str(title)[:90],'created':stamp(),'updated':stamp(),'thread_id':None,'turn_id':None,'busy':False,'events':[],'requests':{},'model':None}
  with self.lock:self.sessions[(pid,s['id'])]=s;self.persist(s)
  return s
 def history(self,pid,cid,after=0):
  s=self.get(pid,cid)
  with self.lock:return {**{k:s.get(k) for k in ['id','title','busy','turn_id','thread_id','model','updated']},'events':[e for e in s['events'] if e['seq']>after],'cursor':len(s['events']),'requests':list(s['requests'].values())}
 def settings(self,permission):
  if permission not in ['read-only','workspace-write','danger-full-access']:raise ValueError('访问范围无效。')
  policy={'type':{'read-only':'readOnly','workspace-write':'workspaceWrite','danger-full-access':'dangerFullAccess'}[permission]}
  if permission=='workspace-write':policy.update(writableRoots=[str(ROOT)],networkAccess=True)
  return permission,policy,'never' if permission=='danger-full-access' else 'on-request'
 def submit(self,pid,cid,data):
  text=str(data.get('message','')).strip()
  if not text or len(text)>50000:raise ValueError('请输入消息（最多 50000 字符）。')
  s=self.get(pid,cid);permission,policy,approval=self.settings(data.get('permission','workspace-write'))
  model=data.get('model') or None;effort=data.get('effort') or None
  if effort not in [None,'none','minimal','low','medium','high','xhigh','max','ultra']:raise ValueError('推理强度无效。')
  attachments=[]
  for ident in data.get('attachments',[])[:6]:
   if not re.fullmatch(r'[a-f0-9]{24}\.(png|jpg|webp)',ident):raise ValueError('图片标识无效。')
   f=self.root(pid)/'attachments'/ident
   if not f.is_file():raise FileNotFoundError('附件不存在。')
   attachments.append(f)
  language=data.get('language','zh-CN')
  if language not in ('zh-CN','en'):raise ValueError('Unsupported language.')
  payload=context(self.manager,pid,data.get('region'),data.get('stage'),language=language)+'\n\nUser message:\n'+text
  with self.lock:
   if s['busy']:raise ValueError('当前会话正在执行，请先停止或等待完成。')
   s['busy']=True
   if not s['events']:s['title']=text[:40]
   self.append(s,'bridge/user',{'text':text,'attachments':[f.name for f in attachments],'stage':data.get('stage'),'permission':permission})
  def run():
   try:
    self.process.ensure();params={'cwd':str(ROOT),'sandbox':permission,'approvalPolicy':approval}
    if model:params['model']=model
    if not s['thread_id']:
     r=self.process.rpc('thread/start',{**params,'developerInstructions':CORE_RULES})
     with self.lock:s['thread_id']=r['thread']['id'];s['model']=r.get('model',model);self.persist(s)
     self.loaded[s['thread_id']]=self.process.generation
    elif self.loaded.get(s['thread_id'])!=self.process.generation:
     self.process.rpc('thread/resume',{**params,'threadId':s['thread_id'],'excludeTurns':True});self.loaded[s['thread_id']]=self.process.generation
    inputs=[{'type':'text','text':payload}]+[{'type':'localImage','path':str(f)} for f in attachments]
    r=self.process.rpc('turn/start',{'threadId':s['thread_id'],'input':inputs,'cwd':str(ROOT),'approvalPolicy':approval,'sandboxPolicy':policy,**({'model':model} if model else {}),**({'effort':effort} if effort else {})})
    with self.lock:
     if s['busy']:s['turn_id']=r['turn']['id']
     self.persist(s)
   except Exception as e:
    with self.lock:s.update(busy=False,turn_id=None);self.append(s,'bridge/error',{'message':str(e)})
  threading.Thread(target=run,daemon=True).start();return {'accepted':True,'chat_id':cid}
 def event(self,r,generation):
  if generation!=self.process.generation:return
  method=r['method'];p=r.get('params',{});tid=p.get('threadId') or p.get('thread',{}).get('id')
  if method.startswith('codex/event/'):return
  with self.lock:
   matches=[s for s in self.sessions.values() if s['thread_id']==tid] if tid else []
   if method=='bridge/disconnected':matches=[s for s in self.sessions.values() if s['busy']]
   for s in matches:
    if 'id' in r:
     request={'id':str(r['id']),'rpc_id':r['id'],'method':method,'params':p};s['requests'][str(r['id'])]=request
     self.append(s,'bridge/request',request)
    else:
     if method=='turn/started':s['turn_id']=p.get('turn',{}).get('id');s['busy']=True
     if method in ['turn/completed','bridge/disconnected']:s.update(busy=False,turn_id=None,requests={})
     if method=='serverRequest/resolved':s['requests'].pop(str(p.get('requestId')),None)
     self.append(s,method,p)
 def interrupt(self,pid,cid):
  s=self.get(pid,cid)
  if not s.get('busy'):return {'interrupted':False}
  if not s.get('turn_id'):raise ValueError('Codex 正在初始化；请稍后停止。')
  self.process.rpc('turn/interrupt',{'threadId':s['thread_id'],'turnId':s['turn_id']});return {'interrupted':True}
 def answer(self,pid,cid,request_id,result):
  s=self.get(pid,cid)
  with self.lock:
   request=s['requests'].get(str(request_id))
   if not request:raise ValueError('该请求已失效。')
   method=request['method']
   if method.endswith('/requestApproval') and ('commandExecution' in method or 'fileChange' in method):
    if result.get('decision') not in ['accept','acceptForSession','decline','cancel']:raise ValueError('确认选项无效。')
   elif method=='item/tool/requestUserInput':
    if not isinstance(result.get('answers'),dict):raise ValueError('回答格式无效。')
   else:raise ValueError('此请求类型需要使用 Codex CLI 处理：'+method)
   self.process.send({'id':request['rpc_id'],'result':result});s['requests'].pop(str(request_id),None);self.append(s,'bridge/answered',{'requestId':request_id})
  return {'answered':True}
 def archive(self,pid,cid):
  s=self.get(pid,cid)
  if s['busy']:raise ValueError('请先停止当前执行。')
  with self.lock:s['archived']=True;self.persist(s)
  return {'archived':True}
