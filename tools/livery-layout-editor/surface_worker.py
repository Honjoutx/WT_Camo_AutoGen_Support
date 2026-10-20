"""Compose separate physical planes, then register their pixels into original UVs."""
from pathlib import Path
from external_process import run as external_run
import sys,argparse,json,os,copy,subprocess,traceback,zipfile,shutil
import numpy as np
from PIL import Image
from project import ROOT,HERE,read,write_json,sha
from projects import ProjectManager
from layer_material import compose_material
from surface_bake import bake
from incremental_native import unchanged_domains,link_copy,registered_domains
from texture_bundle import FINAL_MODES,pack
from native_atlas_export import original_atlas_images
from export_selection import select_images
from export_acceleration import configure as configure_acceleration,finalize as finalize_acceleration
from game_atlas_manifest import write_manifest as write_game_atlas_manifest
from project_dependencies import cache_inputs_exist
from storage import prepare_job,compact_job,register_archive,reuse_file
sys.stdout.reconfigure(encoding='utf8',errors='replace')
parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);parser.add_argument('--reuse-job');parser.add_argument('--reuse-plane-job');args=parser.parse_args();O=Path(args.job).resolve();job=read(O/'job.json');p=ProjectManager().get(snapshot=read(O/'project-config.json'));state=p.validate(read(O/'layout.json'))
def update(stage,progress,**extra):job.update(stage=stage,progress=progress,**extra);write_json(O/'job.json',job);print(stage,flush=True)
def acceleration_changed(report):
 job['export_backend']=report['actual']
 if report['fallbacks']:
  job['acceleration_warning']='GPU 贴图加速已回退 CPU：'+report['fallbacks'][-1]['reason']
  print(job['acceleration_warning'],flush=True)
 else:job.pop('acceleration_warning',None)
 write_json(O/'job.json',job)
def link(name,label):return dict(label=label,url=f'/job/{job["id"]}/{name}')
def raster(svg,width,out):
 from raster import svg_png
 out.write_bytes(svg_png(svg,width))
try:
 prepare_job(O)
 job.pop('error',None)
 configure_acceleration(job.get('export_acceleration','cpu'),O,acceleration_changed)
 if args.reuse_plane_job:
  # A failed native bake can still have fully completed physical-plane PNGs.
  # Per-plane source, layout, material and resolution checks below remain
  # mandatory. No partially baked native image is accepted as a cache.
  cached_root=Path(args.reuse_plane_job).resolve()
  if not cached_root.is_relative_to(p.jobs.resolve()):raise ValueError('平面缓存必须属于当前模型项目。')
  cached=read(cached_root/'surface-manifest.json')
  if cached.get('project_id')!=p.id or cached.get('model_sha256')!=p.contract['model_sha256']:raise ValueError('平面缓存不属于同一模型。')
  p.contract=copy.deepcopy(p.contract);p.contract['reuse_surface_exports']=str(cached_root/'surface-manifest.json');write_json(O/'evidence/retry-plane-cache.json',dict(reference=str(cached_root),native_partial_outputs_not_reused=True,individual_plane_validation_required=True))
 if args.reuse_job:
  # A retry may use a newer completed cache. Existing reuse checks still prove
  # each plane/domain's layout, source artwork, geometry, UVs and resolution.
  cached_root=Path(args.reuse_job).resolve()
  if not cached_root.is_relative_to(p.jobs.resolve()):raise ValueError('复用缓存必须属于当前模型项目。')
  cached_job=read(cached_root/'job.json');cached_project=ProjectManager().get(snapshot=read(cached_root/'project-config.json'))
  if cached_job['status']!='complete' or cached_project.id!=p.id or cached_project.contract['model_sha256']!=p.contract['model_sha256']:raise ValueError('复用缓存不是同一模型的已完成任务。')
  p.contract=copy.deepcopy(p.contract);p.contract['reuse_surface_exports']=str(cached_root/'surface-manifest.json');p.contract['incremental_native_exports']=dict(manifest=str(cached_root/'manifest.json'),surface_contract=str(cached_project.surface_root/'contract.json'),source_model_sha256=cached_project.contract['model_sha256'])
  write_json(O/'evidence/retry-cache.json',dict(reference=str(cached_root),project_id=p.id,source_model_sha256_exact=True,individual_plane_and_domain_checks_required=True))
 update('合成独立模块平面',1,status='running',pid=os.getpid());size=8192 if job['mode']=='8k' else 4096 if job['mode']=='4k' else 2048;planes={}
 if any(l.get('material',{}).get('relief_mm') is not None for region in state['regions'].values() for l in region['layers']):p.contract.setdefault('relief_material',{})['enabled']=True
 for name in ['planes','surface-sources','textures','materials','assets','previews','evidence']:(O/name).mkdir(exist_ok=True)
 reuse_path=p.contract.get('reuse_surface_exports');reuse=None;reuse_state=None;reuse_audit={};cached_finish=None
 if reuse_path and not cache_inputs_exist(p.root/reuse_path):
  print('旧平面缓存已清理，按当前矢量设计重新生成。',flush=True);reuse_path=None
 if reuse_path:
  reuse_root=(p.root/reuse_path).parent;reuse=read(p.root/reuse_path);reuse_state=read(reuse_root/'layout.json')
  assert reuse['project_id']==p.id
  assert reuse['model_sha256']==p.contract['model_sha256'] or p.contract.get('incremental_native_exports',{}).get('source_model_sha256')==reuse['model_sha256']
  cached_finish=reuse.get('automatic_material')
  if cached_finish is None and (reuse_root/'project-config.json').is_file():
   try:cached_finish=ProjectManager().get(snapshot=read(reuse_root/'project-config.json')).contract.get('automatic_material',{})
   except FileNotFoundError:
    print('旧平面缓存的版本配置已清理，将重新生成对应平面。',flush=True);cached_finish=None
 for i,(key,meta) in enumerate(p.regions.items()):
  update('独立平面 · '+meta['name'],2+int(i/len(p.regions)*40));w,h=meta['viewbox'];width=round(size*min(1,w/h));height=round(width*h/w);svg=p.compose(state,key,for_export=True);(O/'surface-sources'/f'{key}.svg').write_text(svg,encoding='utf8');cp=O/'planes'/f'{key}-color.png';has_art=any(l['visible'] and l['opacity']>0 for l in state['regions'][key]['layers'][1:])
  prior=reuse.get('regions',{}).get(key) if reuse else None
  required=['color','metallic','roughness']+(['relief_mm'] if p.contract.get('relief_material',{}).get('enabled') else [])
  if prior and cached_finish==p.contract.get('automatic_material',{}) and prior['source_sha256']==meta['source_sha256'] and prior['pixels'][0]>=width and prior['pixels'][1]>=height and state['regions'][key]==reuse_state['regions'][key] and all(prior.get(ch) and (reuse_root/prior[ch]).is_file() for ch in required):
   # Original vectors, layout and resolution match. Reuse approved Skia pixels
   # rather than needlessly re-rasterize unchanged art on another GPU/session.
   scalar={}
   for ch in required:
    target=O/'planes'/(f'{key}-color.png' if ch=='color' else f'{key}-{ch}.png')
    reuse_file(reuse_root/prior[ch],target,O)
    if ch!='color':scalar[ch]=target.relative_to(O).as_posix()
   cached_preview=reuse_root/'previews'/f'{key}.jpg';target_preview=O/'previews'/f'{key}.jpg'
   if cached_preview.is_file():reuse_file(cached_preview,target_preview,O)
   else:
    # Thumbnails are optional cache artifacts. Rebuild from the approved color
    # PNG without changing artwork or forcing another vector raster/bake.
    with Image.open(cp) as image:thumb=image.convert('RGBA')
    thumb.thumbnail((450,300));back=Image.new('RGB',thumb.size,'#183148');back.paste(thumb,mask=thumb.getchannel('A'));back.save(target_preview,quality=92)
   planes[key]=dict(color=cp.relative_to(O).as_posix(),**scalar,pixels=prior['pixels'],camera=meta['surface'],source_svg=f'surface-sources/{key}.svg',source_sha256=meta['source_sha256'],changed=p.changed(state,key),has_art=has_art,role='Approved unchanged physical-plane artwork reused at original resolution')
   reuse_audit[key]=dict(reused=True,reference=p.contract['reuse_surface_exports'],source_sha256_exact=True,layout_exact=True,pixels_exact=True,preview_regenerated=not cached_preview.is_file())
   continue
  if has_art:raster(svg,width,cp)
  else:Image.new('RGBA',(width,height)).save(cp)
  color=Image.open(cp).convert('RGBA');rgb=np.asarray(color.convert('RGB'),np.float32)/255;foil=np.clip((rgb[:,:,0]-rgb[:,:,2]-.03)*5,0,1)
  scalar={};finish=p.contract.get('automatic_material',{});base_m=finish.get('base_metallic',.06);foil_m=finish.get('foil_metallic',.72);base_r=finish.get('base_roughness',.40);foil_r=finish.get('foil_roughness',.26);channels=[('metallic',base_m+(foil_m-base_m)*foil),('roughness',base_r+(foil_r-base_r)*foil)]
  if p.contract.get('relief_material',{}).get('enabled'):channels.append(('relief_mm',np.zeros_like(foil)))
  for channel,automatic in channels:
   mat_svg=compose_material(svg,state,key,channel,meta);target=O/'planes'/f'{key}-{channel}.png'
   if mat_svg and has_art:
    tmp=O/'planes'/f'{key}-{channel}-weights.png';raster(mat_svg,width,tmp);im=np.asarray(Image.open(tmp).convert('RGB'),np.float32)/255;value=np.clip(im[:,:,0]+automatic*(1-im[:,:,1]),0,1);tmp.unlink()
   else:value=automatic
   Image.fromarray(np.uint8(np.rint(value*255))).save(target);scalar[channel]=target.relative_to(O).as_posix()
  thumb=color.copy();thumb.thumbnail((450,300));back=Image.new('RGB',thumb.size,'#183148');back.paste(thumb,mask=thumb.getchannel('A'));back.save(O/'previews'/f'{key}.jpg',quality=92)
  planes[key]=dict(color=cp.relative_to(O).as_posix(),**scalar,pixels=list(color.size),camera=p.regions[key]['surface'],source_svg=f'surface-sources/{key}.svg',source_sha256=meta['source_sha256'],changed=p.changed(state,key),has_art=has_art,role='Independent actual module surface artwork; no UV atlas on the editing canvas')
 write_json(O/'surface-manifest.json',dict(schema='physical-surface-export/v1',project_id=p.id,project_signature=p.signature,regions=planes,model_sha256=p.contract['model_sha256'],capture_bindings_sha256=sha(p.surface_root/p.contract['capture_bindings']),automatic_material=p.contract.get('automatic_material',{})))
 if reuse_path:write_json(O/'evidence/surface-reuse-audit.json',reuse_audit)
 if job['mode']!='boards':
  full_domains=p.native_contract['regions']
  if p.contract.get('bake_active_domains_only') and p.contract.get('preview_original_atlases'):
   p.native_contract['regions']=registered_domains(p)
   write_json(O/'evidence/active-domain-pruning.json',dict(policy='Same paintable-face ownership and compatibility exclusions as final original-atlas export',retained=list(p.native_contract['regions']),excluded=sorted(set(full_domains)-set(p.native_contract['regions']))))
  reused,proof,reuse_root=unchanged_domains(p,state,size);domains=p.native_contract['regions'];p.native_contract['regions']={k:v for k,v in domains.items() if k not in reused};rows=bake(p,planes,O,size,update);p.native_contract['regions']=domains
  for key,row in reused.items():
   for ch in ['color','metallic','roughness','smoothness','normal','height']:
    if row.get(ch):reuse_file(reuse_root/row[ch],O/row[ch],O)
   rows[key]=row
  p.native_contract['regions']=full_domains
  write_json(O/'evidence/incremental-native-reuse.json',dict(reused_domains=proof,baked_domains=len(domains)-len(reused)));model=p.root/p.contract['model'];write_json(O/'manifest.json',dict(schema='native-uv-export/v1',project_id=p.id,project_signature=p.signature,source_model=str(model),source_model_sha256=sha(model),source_obj_sha256=p.contract['source_sha256'],regions=rows,surfaces=planes,uv_policy='Separate physical-plane layouts -> registered real-face barycentrics -> unmodified native UV atlases',original_normal_maps_preserved=True,normal_finish=p.contract.get('normal_finish',{})))
  if job['mode']=='preview':
   if p.contract.get('preview_original_atlases'):
    _,preview_audit=original_atlas_images(p,rows,O,'pbr',size,lambda stage,progress:update(stage,80+int((progress-84)/13*2)))
    write_game_atlas_manifest(p,O,preview_audit)
   update('应用原 UV 贴图 · GPU 模型预览',83);cmd=[__import__('runtime').blender_executable(),'--background','--python-exit-code','1','--python',str(HERE/'gpu_bootstrap.py'),'--python',str(HERE/'native_preview.py'),'--',str(O),str(model),job['mode']]
   with (O/'pipeline.log').open('w',encoding='utf8') as log:r=external_run(cmd,cwd=ROOT,env={**os.environ,'LIVERY_OUTPUT_DIR':str(O),'LIVERY_RENDER_SETTINGS':str(O/'evidence/render-settings.json')},stdout=log,stderr=subprocess.STDOUT)
   if r.returncode:raise RuntimeError('原 UV 模型应用或 GPU 预览失败：pipeline.log')
   job['files'].append(link('Layout_Working.blend','当前平面布局 · 原 UV 模型'));job['previews'].append(link('previews/model.png','平面编辑结果 · GPU 模型预览'))
 if job['mode'] in FINAL_MODES:
  preset=job.get('export_channels','color');images,audit=original_atlas_images(p,rows,O,preset,size,update);images=select_images(images,job.get('export_files'),O,audit)
  if p.contract.get('preview_original_atlases'):write_game_atlas_manifest(p,O,audit)
  bundle=pack(O,p.id+'-'+job['mode']+'-original-atlases.zip',images,audit);job['files']=[link(bundle.name,'原始图集贴图 · '+job['mode'].upper()+' PNG')];job['previews']=[]
  if audit['shared_uv_conflict_pixels']:job['warnings']=['存在共用 UV 的不同设计，导出按主体版面优先统一纹样；原 UV 保持不变。']
  compact_job(O)
  update('导出完成 · '+str(len(images))+' 张原图集贴图',100,status='complete',export_policy='original-atlases-only',export_channels=preset,export_dir=str(O/'export'),original_color_atlas_count=audit['original_color_atlas_count'],texture_count=len(images));sys.exit(0)
 update('保存平面稿与原 UV 导出包',95);bundle=O/(p.id+'-'+job['mode']+'.zip')
 entries=[(f,f.relative_to(O).as_posix()) for folder in ['planes','surface-sources','textures','materials','evidence'] for f in (O/folder).iterdir() if f.is_file()]
 entries.extend((O/name,name) for name in ['layout.json','project-config.json','surface-manifest.json','manifest.json'] if (O/name).exists())
 register_archive(O,bundle.name,entries)
 job['files'].append(link(bundle.name,'独立模块平面 / SVG / 材质 / 原 UV 导出'));job['previews'].append(link('previews/'+job['region']+'.jpg','当前模块平面'))
 compact_job(O)
 update('生成完成 · 平面编辑与原 UV 导出已保存',100,status='complete')
except Exception as e:traceback.print_exc();update('生成失败',job.get('progress',0),status='failed',error=str(e));sys.exit(1)
finally:finalize_acceleration()
