"""Reuse only unchanged face domains, layouts, UVs and sufficient PNG resolution."""
import copy,os,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
from project import read,sha
from project_dependencies import cache_inputs_exist

def registered_domains(project):
 """Use the same paintable face ownership as the final original-atlas plan."""
 model=project.root/project.native_contract['model']
 with np.load(model.parent/'source-bindings.npz') as bindings:
  eligible=(bindings['owner']>=0)&bindings['paint']
 assignment=np.load(model.parent/'face-material-domains.npy',allow_pickle=True)
 active=set(assignment[eligible])
 return {key:meta for key,meta in project.native_contract['regions'].items()
         if key in active and not meta.get('compatibility_only')}

def link_copy(source,target):
 source=Path(source);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 try:os.link(source,target)
 except OSError:
  import shutil;shutil.copy2(source,target)

def unchanged_domains(project,state,size):
 cfg=project.contract.get('incremental_native_exports')
 if not cfg:return {},{},None
 manifest_path=project.root/cfg['manifest'];contract_path=project.root/cfg['surface_contract']
 if not cache_inputs_exist(manifest_path,contract_path):
  print('旧原 UV 缓存已清理，按当前项目重新生成。',flush=True);return {},{},None
 base=read(manifest_path);root=manifest_path.parent;layout=read(root/'layout.json');oldc=read(contract_path)
 if not (project.root/oldc['native_contract']).is_file():
  print('旧原 UV 缓存的配置已清理，按当前项目重新生成。',flush=True);return {},{},None
 oldnative=read(project.root/oldc['native_contract']);oldmodel=project.root/oldnative['model'];newmodel=project.root/project.native_contract['model']
 if not all(p.is_file() for p in [oldmodel.parent/'source-bindings.npz',contract_path.parent/oldc['capture_bindings'],oldmodel.parent/'repair-manifest.json']):
  print('旧原 UV 缓存的模型数据已清理，按当前项目重新生成。',flush=True);return {},{},None
 if project.contract.get('automatic_material',{})!=oldc.get('automatic_material',{}) or project.contract.get('fallback_fill')!=oldc.get('fallback_fill'):
  return {},{},root
 if project.contract.get('normal_finish',{})!=base.get('normal_finish',oldc.get('normal_finish',{})):
  return {},{},root
 def arrays(path):
  with np.load(path) as f:return {k:f[k] for k in f.files}
 old=arrays(oldmodel.parent/'source-bindings.npz');new=arrays(newmodel.parent/'source-bindings.npz');oldf=arrays((project.root/cfg['surface_contract']).parent/oldc['capture_bindings']);newf=arrays(project.surface_root/project.contract['capture_bindings']);newrepair=read(newmodel.parent/'repair-manifest.json');oldrepair=read(oldmodel.parent/'repair-manifest.json');proof={};reuse={}
 for key,meta in project.native_contract['regions'].items():
  prior=base['regions'].get(key);om=oldnative['regions'].get(key)
  if not prior or not om or meta.get('native_uv_board') or meta.get('atlas_authority') or prior.get('size',0)<max(size,meta.get('minimum_export_size',0)):continue
  if any(meta.get(k)!=om.get(k) for k in ['color_map','texture_name','repeat','fallback_fill','surface_alpha_floor','material_reference']):continue
  if om.get('source_face_ids') and not (project.root/om['source_face_ids']).is_file():continue
  ids=np.load(project.root/meta['source_face_ids']) if meta.get('source_face_ids') else np.flatnonzero((new['owner']>=0)&new['paint']&np.isin(new['material_index'],[i for i,v in enumerate(newrepair['materials'].values()) if v.get('map_Kd')==meta['color_map']]))
  oldids=np.load(project.root/om['source_face_ids']) if om.get('source_face_ids') else np.flatnonzero((old['owner']>=0)&old['paint']&np.isin(old['material_index'],[i for i,v in enumerate(oldrepair['materials'].values()) if v.get('map_Kd')==om['color_map']]))
  if not np.isin(ids,oldids).all():continue
  if not np.array_equal(new['vertices'][new['tri'][ids]],old['vertices'][old['tri'][ids]]) or not np.array_equal(new['uv_fixed'][new['tex'][ids]],old['uv_fixed'][old['tex'][ids]]):continue
  regions=set();ok=True
  for board in project.regions:
   hit=np.intersect1d(ids,newf[board+'_selected_face_ids'])
   if not len(hit):continue
   regions.add(board)
   if board not in oldc['regions'] or state['regions'][board]!=layout['regions'].get(board) or project.regions[board]['source_sha256']!=oldc['regions'][board]['source_sha256']:ok=False;break
   a=newf[board+'_selected_face_ids'];b=oldf[board+'_selected_face_ids'];ai={int(v):j for j,v in enumerate(a)};bi={int(v):j for j,v in enumerate(b)}
   if not all(int(v) in bi for v in hit) or not np.array_equal(newf[board+'_art_uv'][[ai[int(v)] for v in hit]],oldf[board+'_art_uv'][[bi[int(v)] for v in hit]]):ok=False;break
  if not ok:continue
  channels=[k for k in ['color','metallic','roughness','smoothness','normal','height'] if prior.get(k)]
  if not all((root/prior[ch]).is_file() for ch in channels):continue
  reuse[key]=copy.deepcopy(prior);proof[key]=dict(unchanged_face_uv_and_geometry=True,unchanged_artwork=True,contributing_regions=sorted(regions),resolution=prior['size'],source_manifest=cfg['manifest'])
 return reuse,proof,root
