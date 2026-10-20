"""Native atlas composition. Uses only current project face IDs and material bindings."""
from pathlib import Path
import argparse,os,sys,shutil,json,zipfile,traceback,subprocess
sys.stdout.reconfigure(encoding='utf8',errors='replace')
from project import ROOT,HERE,read,write_json,sha
from projects import ProjectManager
from layer_material import compose_material
from texture_bundle import FINAL_MODES,pack
from native_atlas_export import original_atlas_images
from export_selection import select_images
from storage import prepare_job,compact_job,register_archive
import resvg_py,numpy as np
from PIL import Image
parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);args=parser.parse_args();O=Path(args.job).resolve();job=read(O/'job.json');project=ProjectManager().get(snapshot=read(O/'project-config.json'));state=project.validate(read(O/'layout.json'))
def update(stage,progress,**extra):job.update(stage=stage,progress=progress,**extra);write_json(O/'job.json',job);print(stage,flush=True)
def link(p,label):return dict(label=label,url=f'/job/{job["id"]}/{p}')
def raster(svg,size):return resvg_py.svg_to_bytes(svg_string=svg,width=size,height=size,font_files=__import__('runtime').font_files(),skip_system_fonts=False)
try:
 prepare_job(O)
 job.pop('error',None);job['log']=[]
 update('读取当前模型原 UV 图集',2,status='running',pid=os.getpid())
 for name in ['textures','surface-sources','materials','assets','previews']:(O/name).mkdir(exist_ok=True)
 model=project.root/project.contract['model'];contract=read(project.root/project.contract['repair_manifest']);size=8192 if job['mode']=='8k' else 4096 if job['mode']=='4k' else 2048;rows={}
 used=sorted({l['asset_id'] for r in state['regions'].values() for l in r['layers'] if l.get('asset_id')})
 for aid in used:shutil.copy2(project.library.pin(aid),O/'assets'/project.library.pin(aid).name)
 for i,(key,meta) in enumerate(project.regions.items()):
  update('合成 '+meta['name'],5+int(i/len(project.regions)*60));assert sha(project.source_path(key))==meta['source_sha256'];svg=project.compose(state,key);(O/'surface-sources'/f'{key}.svg').write_text(svg,encoding='utf8');out=O/'textures'/f'{key}-basecolor.png';out.write_bytes(raster(svg,size))
  with Image.open(out) as image:
   thumb=image.convert('RGB');thumb.thumbnail((450,300));thumb.save(O/'previews'/f'{key}.jpg',quality=90)
  scalar={}
  for channel,default in [('metallic',0),('roughness',.6)]:
   mat_svg=compose_material(svg,state,key,channel,meta);target=O/'materials'/f'{key}-{channel}.png'
   if mat_svg:
    import io
    with Image.open(io.BytesIO(raster(mat_svg,size))) as image:
     # Compose R numerator + inherited*(1-G). Evaluate row blocks to bound memory.
     rgb=image.convert('RGB');scalar_image=Image.new('L',(size,size))
     for y in range(0,size,512):
      chunk=np.asarray(rgb.crop((0,y,size,min(y+512,size))),dtype=np.float32)/255;value=np.clip(chunk[:,:,0]+default*(1-chunk[:,:,1]),0,1);scalar_image.paste(Image.fromarray(np.uint8(np.rint(value*255))),(0,y))
     scalar_image.save(target)
   else:Image.new('L',(size,size),round(default*255)).save(target)
   scalar[channel]=target.relative_to(O).as_posix()
  # Normal maps retain the existing texture content and channel convention. No
  # guessed conversion of game packed specular files into roughness/metalness.
  mids=[mid for mid,r in contract['materials'].items() if r.get('map_Kd')==meta['color_map']];normal=next((contract['materials'][mid].get('map_normal') for mid in mids if contract['materials'][mid].get('map_normal')),None)
  normal_path=None
  if normal:
   original=model.parent/'textures'/Path(normal).name;normal_path=f'textures/{key}-normal.png'
   with Image.open(original) as im:im.convert('RGB').resize((size,size),Image.Resampling.LANCZOS).save(O/normal_path)
  rows[key]=dict(color=out.relative_to(O).as_posix(),original_texture=meta['texture_name'],metallic=scalar['metallic'],roughness=scalar['roughness'],normal=normal_path,size=size,changed=project.changed(state,key),sha256=sha(out))
 write_json(O/'manifest.json',dict(schema='native-uv-export/v1',project_id=project.id,project_signature=project.signature,source_model=str(model),source_model_sha256=sha(model),source_obj_sha256=project.contract['source_sha256'],regions=rows,uv_policy='UVMap unchanged from repaired model; native atlas direct composition',render_settings=read(O/'evidence/render-settings.json'),material_policy='Generic PBR defaults metallic 0 / roughness .6 plus per-layer overrides; source packed game maps retained with model, not reinterpreted',assets=[dict(project.library.get(aid),snapshot=str(project.library.pin(aid).name)) for aid in used]))
 if job['mode']=='preview':
  update('将当前图集应用到独立模型版本',70)
  blender=Path(__import__('runtime').blender_executable());cmd=[str(blender),'--background','--python-exit-code','1','--python',str(HERE/'gpu_bootstrap.py'),'--python',str(HERE/'native_preview.py'),'--',str(O),str(model),job['mode']]
  with (O/'pipeline.log').open('w',encoding='utf8') as log:
   result=subprocess.run(cmd,cwd=ROOT,env={**os.environ,'LIVERY_OUTPUT_DIR':str(O),'LIVERY_RENDER_SETTINGS':str(O/'evidence/render-settings.json')},stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  if result.returncode:raise RuntimeError('模型应用或 GPU 预览失败，请查看 pipeline.log。')
  job['files'].append(link('Layout_Working.blend','当前模型 · 新布局场景'))
  if job['mode']=='preview':job['previews'].append(link('previews/model.png','当前模型 GPU 预览'))
 if job['mode'] in FINAL_MODES:
  preset=job.get('export_channels','color');images,audit=original_atlas_images(project,rows,O,preset,size,update);images=select_images(images,job.get('export_files'),O,audit);bundle=pack(O,project.id+'-'+job['mode']+'-original-atlases.zip',images,audit);job['files']=[link(bundle.name,'原始图集贴图 · '+job['mode'].upper()+' PNG')];job['previews']=[]
  if audit['shared_uv_conflict_pixels']:job['warnings']=['存在共用 UV 的不同设计，导出按主体版面优先统一纹样；原 UV 保持不变。']
  compact_job(O)
  update('导出完成 · '+str(len(images))+' 张原图集贴图',100,status='complete',export_policy='original-atlases-only',export_channels=preset,export_dir=str(O/'export'),original_color_atlas_count=audit['original_color_atlas_count'],texture_count=len(images));sys.exit(0)
 update('打包原 UV 图集与布局参数',95)
 bundle=O/(project.id+'-'+job['mode']+'.zip')
 entries=[(f,f.relative_to(O).as_posix()) for sub in ['textures','materials','surface-sources','assets'] for f in (O/sub).iterdir() if f.is_file()]
 entries.extend((O/name,name) for name in ['manifest.json','layout.json','project-config.json'])
 register_archive(O,bundle.name,entries)
 job['files'].extend([link(bundle.name,'分区贴图 / 材质 / SVG / 布局'),link('manifest.json','原 UV 版本记录')]);job['previews'].append(link('previews/'+job['region']+'.jpg','当前原 UV 版面'))
 compact_job(O)
 update('生成完成 · 当前项目新版本已保存',100,status='complete')
except Exception as e:traceback.print_exc();update('生成失败',job.get('progress',0),status='failed',error=str(e));sys.exit(1)
