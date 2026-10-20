"""Background OBJ intake: preserve geometry/normals, correct proven UV phases."""
from pathlib import Path
from datetime import datetime
import hashlib,json,os,re,shutil,threading,uuid,zipfile
import numpy as np
from project import ROOT,read,write_json

INTAKE=ROOT/'projects/_intake'
MODULES=['body','turret','gun','components','detachable_armor']
def normal_name(name):return re.sub(r'_\d+$','',name.lower().split('#')[-1])
def phase(values):
 if not len(values):return (0.,0.)
 answer=[]
 for column in np.asarray(values,float).T:
  lo,hi,mid=float(column.min()),float(column.max()),float(np.median(column))
  answer.append(1. if lo>=-1.025 and hi<=.025 and mid<-.10 else -1. if lo>=.975 and hi<=2.025 and mid>1.10 else 0.)
 return tuple(answer)
def reference_rules(manager,pid):
 if not pid:return {}
 cfg=manager.config(pid);P=ROOT/cfg['directory'];c=read(P/cfg['surface_directory']/'contract.json');native=read(P/c['native_contract']);model=P/native['model'];r=read(P/native['repair_manifest']);result={}
 with np.load(model.parent/'source-bindings.npz') as b:
  for i,o in enumerate(r['original_objects']):
   ids=np.flatnonzero(b['source_object']==i)
   if not len(ids):continue
   owners,count=np.unique(b['owner'][ids],return_counts=True);owner=int(owners[count.argmax()])
   result[normal_name(o['name'])]={0:'body',1:'turret',2:'gun',3:'components',7:'detachable_armor',8:'detachable_armor',-1:'excluded_tracks'}.get(owner,'components')
 return result
def classify(name,points,rules,axis='y'):
 n=normal_name(name)
 if 'track_' in n:return 'excluded_tracks','track-name'
 if n in rules:return rules[n],'reference-semantic-name'
 if any(t in n for t in ['ex_era','reactive_armor','detachable','add_armor_kit']):return 'detachable_armor','detachable-name'
 if any(t in n for t in ['gun_barrel','gun_mask','bone_gun','barrel_']):return 'gun','gun-assembly'
 if any(t in n for t in ['mg_','ammo_box','optic','mirror','cupola','antenna','aps','radar','lantern','ex_decor','roll_','shield']):return 'components','equipment-name'
 if any(t in n for t in ['body','hull','wheel','suspension','root_']):return 'body','hull-assembly'
 if 'turret' in n:return 'turret','turret-assembly'
 if 'ex_armor' in n:
  height=np.median(np.asarray(points)[:,1 if axis=='y' else 2]) if points else 0
  return ('body' if height<1.8 else 'turret'),'armor-height-fallback'
 return 'components','unclassified-review'

def parse_obj(path):
 vertices=[];uv=[];normals=[];objects=[];current=None;material=None;libs=[]
 with Path(path).open(encoding='utf-8-sig',errors='replace') as f:
  for line in f:
   p=line.strip().split(maxsplit=1)
   if not p:continue
   tag=p[0];value=p[1] if len(p)>1 else ''
   if tag=='v':vertices.append(value)
   elif tag=='vt':uv.append(tuple(map(float,value.split()[:2])))
   elif tag=='vn':normals.append(value)
   elif tag=='mtllib':libs.append(value.strip('"'))
   elif tag=='usemtl':material=value
   elif tag=='o' or (tag=='g' and current is None):current={'name':value or 'unnamed','faces':[]};objects.append(current)
   elif tag=='f':
    if current is None:current={'name':'unnamed','faces':[]};objects.append(current)
    corners=[]
    for token in value.split():
     a=token.split('/');row=[]
     for i,total in enumerate([len(vertices),len(uv),len(normals)]):
      val=int(a[i]) if i<len(a) and a[i] else None;row.append((val if val>0 else total+val+1) if val is not None else None)
     if not 1<=row[0]<=len(vertices):raise ValueError('OBJ 顶点索引无效。')
     if row[1] is not None and not 1<=row[1]<=len(uv):raise ValueError('OBJ UV 索引无效。')
     if row[2] is not None and not 1<=row[2]<=len(normals):raise ValueError('OBJ 法线索引无效。')
     corners.append(row)
    if len(corners)<3:raise ValueError('OBJ 面少于三个顶点。')
    current['faces'].append({'material':material,'corners':corners})
 return vertices,uv,normals,objects,libs

def fill_missing_normals(objects,points,normals):
 """Area-weighted 45-degree corner normals, respecting object/material seams."""
 records=[];neighbors={};xyz=np.asarray(points,float)
 for oi,o in enumerate(objects):
  if o['module']=='excluded_tracks':continue
  for f in o['faces']:
   ids=np.asarray([c[0]-1 for c in f['corners']],int);p=xyz[ids];cross=sum((np.cross(p[j]-p[0],p[j+1]-p[0]) for j in range(1,len(p)-1)),start=np.zeros(3));length=np.linalg.norm(cross)
   normal=cross/max(length,1e-30);index=len(records);records.append((f,cross,normal))
   for key in {(oi,f['material'],*np.round(v,6)) for v in p}:neighbors.setdefault(key,[]).append(index)
 cache={};generated=0;cutoff=np.cos(np.pi/4)
 for oi,o in enumerate(objects):
  if o['module']=='excluded_tracks':continue
  for f in o['faces']:
   p=xyz[[c[0]-1 for c in f['corners']]];cross=sum((np.cross(p[j]-p[0],p[j+1]-p[0]) for j in range(1,len(p)-1)),start=np.zeros(3));fn=cross/max(np.linalg.norm(cross),1e-30)
   for c,v in zip(f['corners'],p):
    if c[2] is not None:continue
    key=(oi,f['material'],*np.round(v,6));ck=(key,*np.round(fn,6))
    if ck not in cache:
     n=sum((records[j][1] for j in neighbors[key] if records[j][2]@fn>=cutoff),start=np.zeros(3));n/=max(np.linalg.norm(n),1e-30)
     normals.append(' '.join(f'{x:.9g}' for x in n));cache[ck]=len(normals)
    c[2]=cache[ck];generated+=1
 return generated

def execute(source,out,settings,rules=None):
 source=Path(source).resolve();out=Path(out);out.mkdir(parents=True,exist_ok=True)
 vertices,uv,normals,objects,libs=parse_obj(source);points=[tuple(map(float,v.split()[:3])) for v in vertices]
 if not vertices or not any(o['faces'] for o in objects):raise ValueError('OBJ 没有可用网格。')
 warnings=[];samples={};rows=[];missing_uv=0;source_normal_count=len(normals)
 for o in objects:
  coords=[points[c[0]-1] for f in o['faces'] for c in f['corners']]
  module,reason=classify(o['name'],coords,rules or {},settings.get('up_axis','y'));o['module']=module
  for f in o['faces']:
   if module=='excluded_tracks':continue
   for c in f['corners']:
    if c[1]:samples.setdefault(f['material'],[]).append(uv[c[1]-1])
    else:missing_uv+=1
  rows.append({'source':o['name'],'module':module,'faces':len(o['faces']),'rule':reason,'review':reason.endswith('fallback') or reason=='unclassified-review'})
 generated=fill_missing_normals(objects,points,normals) if settings.get('generate_normals',True) and any(c[2] is None for o in objects if o['module']!='excluded_tracks' for f in o['faces'] for c in f['corners']) else 0
 shifts={}
 mode=settings.get('uv_mode','auto')
 if mode not in ['auto','keep','v-plus-one','v-minus-one']:raise ValueError('UV 修复模式无效。')
 for mat,s in samples.items():shifts[mat]=(0.,0.) if mode=='keep' else (0.,1.) if mode=='v-plus-one' else (0.,-1.) if mode=='v-minus-one' else phase(s)
 if missing_uv:warnings.append(f'{missing_uv} 个面角缺少 UV，保留并报告，需要人工补图；未自动展开。')
 unresolved=[r['source'] for r in rows if r['review']]
 if unresolved:warnings.append(f'{len(unresolved)} 个对象按通用规则归类，需核对清单。')
 # Keep all original vt rows. A translated corner references an appended vt row;
 # this also handles a UV index shared by materials with different integer phases.
 fixed=list(uv);index={};module_faces={k:[] for k in [*MODULES,'excluded_tracks']}
 for o in objects:
  for f in o['faces']:
   shift=shifts.get(f['material'],(0.,0.)) if o['module']!='excluded_tracks' else (0.,0.)
   corners=[]
   for vi,ti,ni in f['corners']:
    if ti and shift!=(0.,0.):
     key=(ti,*shift)
     if key not in index:fixed.append((uv[ti-1][0]+shift[0],uv[ti-1][1]+shift[1]));index[key]=len(fixed)
     ti=index[key]
    corners.append((vi,ti,ni))
   module_faces[o['module']].append((o['name'],f['material'],corners))
 mtl_lines=[];used={f['material'] for o in objects if o['module']!='excluded_tracks' for f in o['faces']};missing_textures=[];texture_count=0
 for lib in libs or [source.with_suffix('.mtl').name]:
  p=(source.parent/lib).resolve()
  if not p.is_file():warnings.append('MTL 不存在：'+str(p));continue
  current=None
  for line in p.read_text(encoding='utf-8-sig',errors='replace').splitlines():
   q=line.strip().split(maxsplit=1)
   if q and q[0]=='newmtl':current=q[1]
   if current not in used:continue
   if q and q[0].startswith(('map_','bump','norm')) and len(q)>1:
    val=q[1].strip('"');origin=(p.parent/val).resolve()
    if origin.is_file():
     dest=out/'textures'/origin.name
     if dest.exists() and hashlib.sha256(dest.read_bytes()).digest()!=hashlib.sha256(origin.read_bytes()).digest():dest=dest.with_name(hashlib.sha256(str(origin).encode()).hexdigest()[:8]+'-'+dest.name)
     dest.parent.mkdir(exist_ok=True);shutil.copy2(origin,dest);line=q[0]+' textures/'+dest.name;texture_count+=1
    else:missing_textures.append(str(origin))
   mtl_lines.append(line)
 (out/'repaired.mtl').write_text('\n'.join(mtl_lines)+'\n',encoding='utf-8')
 def write_obj(target,modules):
  with target.open('w',encoding='utf-8',newline='\n') as f:
   f.write('# Livery Studio: source geometry and corner normals retained; original UV plus documented integer phases\nmtllib repaired.mtl\n')
   for v in vertices:f.write('v '+v+'\n')
   for u,v in fixed:f.write(f'vt {u:.12g} {v:.12g}\n')
   for n in normals:f.write('vn '+n+'\n')
   for module in modules:
    if not module_faces[module]:continue
    f.write('o '+module+'\n');prior=None;prior_source=None
    for name,mat,corners in module_faces[module]:
     if name!=prior_source:f.write('g '+name+'\n');prior_source=name
     if mat!=prior and mat:f.write('usemtl '+mat+'\n');prior=mat
     tokens=[str(vi)+(('/'+(str(ti) if ti else '')+('/'+str(ni) if ni else '')) if ti or ni else '') for vi,ti,ni in corners]
     f.write('f '+' '.join(tokens)+'\n')
 write_obj(out/'repaired-merged.obj',MODULES)
 np.savez_compressed(out/'original-uv.npz',uv=np.asarray(uv,float))
 report={'schema':'livery-model-intake/v1','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'model':str(out/'repaired-merged.obj'),'mtl':str(out/'repaired.mtl'),'original_uv_backup':str(out/'original-uv.npz'),'geometry_policy':'Original vertex coordinates, face corner order, existing normal values; no weld, retopology, unwrap or UV repacking','uv_mode':mode,'uv_offsets':[{'material':mat,'offset':list(s),'sample_count':len(samples[mat])} for mat,s in shifts.items()],'source_vertices':len(vertices),'source_uv':len(uv),'fixed_uv_rows':len(fixed),'source_normals':source_normal_count,'output_normals':len(normals),'generated_normal_corners':generated,'normal_policy':'Keep supplied normals; optionally generate missing corners with area-weighted 45-degree smoothing respecting object/material seams','modules':{k:len(v) for k,v in module_faces.items()},'objects':rows,'missing_uv_corners':missing_uv,'missing_textures':sorted(set(missing_textures)),'texture_references':texture_count,'warnings':warnings,'design_project_status':'修复模型已准备；下一步由“平面分区”流程创建独立设计项目，不自动修改当前项目。'}
 write_json(out/'intake-manifest.json',report)
 return report

class IntakeService:
 def __init__(self,manager):self.manager=manager;self.lock=threading.Lock()
 def folder(self,ident):
  if not re.fullmatch(r'intake-\d{8}-\d{6}-[a-f0-9]{6}',ident or ''):raise ValueError('模型任务标识无效。')
  return INTAKE/ident
 def listing(self):
  rows=[]
  for p in sorted(INTAKE.glob('intake-*/job.json'),reverse=True)[:30] if INTAKE.exists() else []:
   j=read(p)
   if j.get('status')=='running' and not self.alive(j.get('pid')):
    j.update(status='failed',error='模型修复服务已中断；原文件未修改，可重新运行。');write_json(p,j)
   rows.append(j)
  return rows
 @staticmethod
 def alive(pid):
  if not pid:return False
  if os.name!='nt':
   try:os.kill(int(pid),0);return True
   except OSError:return False
  import ctypes
  from ctypes import wintypes
  k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE;k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];k.CloseHandle.argtypes=[wintypes.HANDLE]
  h=k.OpenProcess(0x1000,False,int(pid))
  if not h:return False
  try:code=wintypes.DWORD();return bool(k.GetExitCodeProcess(h,ctypes.byref(code))) and code.value==259
  finally:k.CloseHandle(h)
 def start(self,data):
  source=Path(str(data.get('source',''))).resolve()
  if not source.is_file() or source.suffix.lower()!='.obj':raise ValueError('请选择本机现有 OBJ 文件。')
  if data.get('up_axis','y') not in ['y','z']:raise ValueError('上轴无效。')
  with self.lock:
   if any(j['status']=='running' for j in self.listing()):raise ValueError('已有模型修复任务运行中。')
   ident='intake-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6];folder=self.folder(ident);folder.mkdir(parents=True)
   job={'id':ident,'status':'running','pid':os.getpid(),'source':str(source),'output_directory':str(folder),'created':datetime.now().isoformat(),'settings':data};write_json(folder/'job.json',job)
  def run():
   try:
    rules=reference_rules(self.manager,data.get('reference_project'));report=execute(source,folder,data,rules)
    with zipfile.ZipFile(folder/'repaired-model.zip','w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
     for p in folder.rglob('*'):
      if p.is_file() and p.name not in ['job.json','repaired-model.zip']:z.write(p,p.relative_to(folder))
    job.update(status='complete',report=report,download='/api/intake/file/'+ident+'/repaired-model.zip')
   except Exception as e:job.update(status='failed',error=str(e))
   write_json(folder/'job.json',job)
  threading.Thread(target=run,daemon=True).start();return job
