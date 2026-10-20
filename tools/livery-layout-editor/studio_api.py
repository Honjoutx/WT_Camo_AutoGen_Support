"""Narrow HTTP surface for the local design chat, playbook, and model intake."""
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import hashlib,json,re,uuid
from datetime import datetime,timezone
from codex_bridge import ChatService
from model_intake import IntakeService
from workflow import catalogue
from project import ROOT,HERE,read,write_json
from live_projects import LiveProjects
import app_settings

class StudioAPI:
 def __init__(self,manager):self.manager=manager;self.chat=ChatService(manager);self.intake=IntakeService(manager);self.live=LiveProjects(manager);self.blender=app_settings.BlenderManager()
 def guard(self,h):
  hostname=urlparse('http://'+h.headers.get('Host','')).hostname
  if hostname not in ['127.0.0.1','localhost','::1']:raise ValueError('工作台仅允许本机访问。')
  origin=h.headers.get('Origin')
  if origin and urlparse(origin).netloc!=h.headers.get('Host'):raise ValueError('仅允许同源工作台请求。')
 def pid(self,h):return parse_qs(urlparse(h.path).query).get('project',[self.manager.registry['active_project']])[0]
 def get(self,h,path):
  if not path.startswith(('/api/codex','/api/workflow','/api/intake','/api/studio')):return False
  self.guard(h);q=parse_qs(urlparse(h.path).query);pid=self.pid(h)
  if path=='/api/studio/health':h.respond({'application':'wt-camo-workbench','version':19,'codex_chat':True,'model_intake':True,'compact_storage':True,'live_refresh':True});return True
  if path=='/api/studio/preferences':h.respond(app_settings.preferences());return True
  if path=='/api/studio/settings':h.respond(app_settings.view());return True
  if path=='/api/studio/blender':h.respond(self.blender.status());return True
  if path=='/api/studio/revision':h.respond(self.live.revision(pid));return True
  self.manager.config(pid)
  if path=='/api/workflow':h.respond(catalogue(q.get('language',['zh-CN'])[0]));return True
  if path=='/api/studio/artifact':
   f=Path(q.get('path',[''])[0]).resolve()
   if not f.is_relative_to(ROOT.resolve()) or not f.is_file():raise ValueError('仅能打开工作目录中的现有文件。')
   h.file(f,download=f.name);return True
  if path=='/api/codex/status':h.respond(self.chat.status(q.get('connect')==['1']));return True
  if path=='/api/codex/chats':h.respond({'chats':self.chat.listing(pid)});return True
  if path=='/api/codex/events':h.respond(self.chat.history(pid,q.get('chat',[''])[0],max(0,int(q.get('after',['0'])[0]))));return True
  if path.startswith('/api/codex/attachment/'):
   name=path.rsplit('/',1)[-1]
   if not re.fullmatch(r'[a-f0-9]{24}\.(png|jpg|webp)',name):raise ValueError('附件路径无效。')
   h.file(self.chat.root(pid)/'attachments'/name);return True
  if path=='/api/intake/jobs':h.respond({'jobs':self.intake.listing()});return True
  if path.startswith('/api/intake/file/'):
   tail=path.removeprefix('/api/intake/file/').split('/',1)
   if len(tail)!=2:raise ValueError('文件路径无效。')
   folder=self.intake.folder(tail[0]).resolve();f=(folder/tail[1]).resolve()
   if not f.is_relative_to(folder):raise ValueError('不能访问任务目录外的文件。')
   h.file(f,download=f.name);return True
  h.respond({'error':'接口不存在。'},404);return True
 def post(self,h,path):
  if not path.startswith(('/api/codex','/api/intake','/api/studio')):return False
  self.guard(h);pid=self.pid(h);self.manager.config(pid);length=int(h.headers.get('Content-Length','0'))
  if path=='/api/codex/attachments':
   if not 0<length<=16*1024*1024:raise ValueError('聊天附件每张不超过 16MB。')
   payload=h.rfile.read(length)
   from PIL import Image
   import io
   with Image.open(io.BytesIO(payload)) as im:
    if im.format not in ['PNG','JPEG','WEBP']:raise ValueError('聊天附件支持 PNG、JPEG、WebP。')
    if im.width*im.height>50000000:raise ValueError('图片像素过大，请使用局部参考图。')
    suffix={'PNG':'png','JPEG':'jpg','WEBP':'webp'}[im.format];im.verify()
   name=hashlib.sha256(payload).hexdigest()[:24]+'.'+suffix;folder=self.chat.root(pid)/'attachments';folder.mkdir(exist_ok=True);(folder/name).write_bytes(payload)
   h.respond({'id':name,'url':'/api/codex/attachment/'+name+'?project='+pid},201);return True
  if h.headers.get('Content-Type','').split(';')[0]!='application/json' or not 0<length<2000000:raise ValueError('请求应为有效 JSON。')
  data=json.loads(h.rfile.read(length));cid=data.get('chat_id')
  if path=='/api/studio/preferences':h.respond(app_settings.save_preferences(data))
  elif path=='/api/studio/settings':h.respond(app_settings.save(data))
  elif path=='/api/studio/blender':h.respond(self.blender.start(data.get('action')),202)
  elif path=='/api/codex/chats':h.respond(self.chat.create(pid,title='New chat' if data.get('language')=='en' else '新对话'),201)
  elif path=='/api/codex/send':h.respond(self.chat.submit(pid,cid,data),202)
  elif path=='/api/codex/interrupt':h.respond(self.chat.interrupt(pid,cid))
  elif path=='/api/codex/answer':h.respond(self.chat.answer(pid,cid,data['request_id'],data['result']))
  elif path=='/api/codex/archive':h.respond(self.chat.archive(pid,cid))
  elif path=='/api/intake/jobs':h.respond(self.intake.start(data),202)
  elif path=='/api/studio/reload-project':
   h.respond(self.live.payload(pid))
  elif path=='/api/studio/backup-draft':
   state=data.get('state')
   if not isinstance(state,dict) or state.get('schema')!='livery-layout/v2' or state.get('project_id',pid)!=pid:raise ValueError('本地布局副本不属于当前项目。')
   name='live-local-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json'
   target=self.live.root/self.manager.config(pid)['directory']/'state/recovery'/name;write_json(target,state)
   h.respond({'saved':True,'path':str(target),'project_id':pid})
  else:h.respond({'error':'接口不存在。'},404)
  return True
