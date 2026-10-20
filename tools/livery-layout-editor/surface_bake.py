"""Actual-face barycentric mapping from editable planes to unchanged native UVs."""
import json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
from project import read,write_json,sha
from surface_relief import uv_metrics,relief_normal,combine_normals
from normal_finish import domain_config

def sample(image,u,v):
 h,w=image.shape[:2];x=np.clip(u*(w-1),0,w-1);y=np.clip((1-v)*(h-1),0,h-1);xi=x.astype(np.int32);yi=y.astype(np.int32);xf=(x-xi)[:,None];yf=(y-yi)[:,None];xj=np.minimum(xi+1,w-1);yj=np.minimum(yi+1,h-1)
 return np.uint8(np.rint((image[yi,xi]*(1-xf)+image[yi,xj]*xf)*(1-yf)+(image[yj,xi]*(1-xf)+image[yj,xj]*xf)*yf))

def bake(project,planes,out,size,update=None):
 if any(meta.get('atlas_authority') for meta in project.native_contract['regions'].values()):
  from atlas_authority_bake import bake_authorities
  return bake_authorities(project,planes,out,size,update,bake)
 native=project.native_contract;model=project.root/native['model'];repair=read(project.root/native['repair_manifest']);capture=read(project.surface_root/project.contract['capture_session']);assert sha(model)==capture['model_sha256']
 with np.load(model.parent/'source-bindings.npz') as a:binding={k:a[k] for k in a.files}
 with np.load(project.surface_root/project.contract['capture_bindings']) as a:surfaces={k:a[k] for k in a.files}
 keys=list(project.regions);kind=np.full(len(binding['tri']),255,np.uint8);art_uv=np.zeros((len(kind),3,2),np.float32)
 for i,key in enumerate(keys):
  ids=surfaces[key+'_selected_face_ids'];assert np.all(kind[ids]==255),('Face owned by more than one plane',key)
  # An intentionally hidden planning board must not claim shared native pixels.
  if not planes[key].get('has_art',True):continue
  kind[ids]=i;art_uv[ids]=surfaces[key+'_art_uv']
 relief=project.contract.get('relief_material',{}).get('enabled',False)
 domain_filters={key:sha(project.root/meta['source_face_ids']) for key,meta in native['regions'].items() if meta.get('source_face_ids')}
 domain_filters.update({key+'::mapping-order':sha(project.root/meta['mapping_face_ids']) for key,meta in native['regions'].items() if meta.get('mapping_face_ids')})
 domain_filters.update({key+'::mapping-mask':meta['mapping_mask_sha256'] for key,meta in native['regions'].items() if meta.get('mapping_mask_sha256')})
 domain_filters.update({key+'::coordinated-gradient':json.dumps(meta['coordinated_gradient']['world_y_interval'])+'-v1' for key,meta in native['regions'].items() if meta.get('coordinated_gradient')})
 cache_signature=hashlib.sha256((capture['model_sha256']+sha(project.surface_root/project.contract['capture_bindings'])+str(size)+json.dumps(keys)+json.dumps(domain_filters,sort_keys=True)+str([planes[k].get('has_art',True) for k in keys])+('surface-bake-v4-material-face-domains' if relief else 'surface-bake-v4-material-face-domains-flat')).encode()).hexdigest()[:20]
 cache=project.root/'cache/surface-native-mapping'/cache_signature;cache.mkdir(parents=True,exist_ok=True)
 source_mats=list(repair['materials']);rows={};audit={};loaded={}
 guard=project.contract.get('native_uv_guard');reference=None;protected_faces=None
 if guard:
  reference_path=project.root/guard['reference_manifest'];reference=read(reference_path);reference_root=reference_path.parent
  assert reference['source_model_sha256']==capture['model_sha256'],'UV guard reference belongs to a different model'
  protected_faces=np.load(project.surface_root/guard['protected_faces'])
 if relief:metrics,valid_faces=uv_metrics(binding)
 def plane(k):
  if k in loaded:return loaded[k]
  row=planes[k];a=np.asarray(Image.open(out/row['color']).convert('RGBA'));m=np.asarray(Image.open(out/row['metallic']).convert('L'));r=np.asarray(Image.open(out/row['roughness']).convert('L'));assert a.shape[:2]==m.shape==r.shape
  loaded.clear();channels=[a,m,r]
  if relief:channels.append(np.asarray(Image.open(out/row['relief_mm']).convert('L')))
  loaded[k]=np.dstack(channels);return loaded[k]
 requested_size=size
 for j,(key,meta) in enumerate(native['regions'].items()):
  gradient=meta.get('coordinated_gradient');need_face=relief or bool(gradient)
  size=max(requested_size,int(meta.get('minimum_export_size',0)))
  if update:update('映射原 UV · '+meta['name'],45+int(j/len(native['regions'])*35))
  if meta.get('native_uv_board'):
   from shared_uv_bake import bake_shared
   rows[key],audit[key]=bake_shared(project,key,meta,planes,out,size,binding,repair)
   continue
  saved=cache/(key+(('-'+str(size)) if size!=requested_size else '')+'.npz');ids=np.flatnonzero(np.isin(binding['material_index'],[i for i,mid in enumerate(source_mats) if repair['materials'][mid].get('map_Kd')==meta['color_map']])&(binding['owner']>=0)&binding['paint']);mask=np.asarray(Image.open(project.root/meta['mask']).resize((size,size),Image.Resampling.NEAREST))>0
  domain_faces=None
  if meta.get('source_face_ids'):
   domain_faces=np.load(project.root/meta['source_face_ids']);ids=np.intersect1d(ids,domain_faces)
  if meta.get('mapping_face_ids'):
   # Ordered canonical panels win shared original texels. All aliases subsequently
   # sample this same image rather than independent conflicting domain images.
   order=np.load(project.root/meta['mapping_face_ids']);ids=order[np.isin(order,ids)]
  if saved.exists():
   with np.load(saved) as a:
    map_u=a['u'];map_v=a['v'];map_kind=a['kind']
    if need_face:map_face=a['face']
   cache_hit=True
  else:
   map_u=np.zeros((size,size),np.float32);map_v=np.zeros((size,size),np.float32);map_kind=np.full((size,size),255,np.uint8)
   if need_face:map_face=np.full((size,size),-1,np.int32)
   def triangle(fi,uv):
    points=uv*np.array([size,-size])+[0,size];xmin=max(0,int(np.floor(points[:,0].min())));xmax=min(size,int(np.ceil(points[:,0].max())));ymin=max(0,int(np.floor(points[:,1].min())));ymax=min(size,int(np.ceil(points[:,1].max())))
    if xmin>=xmax or ymin>=ymax:return
    (ax,ay),(bx,by),(cx,cy)=points;den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
    if abs(den)<1e-8:return
    for y0 in range(ymin,ymax,128):
     y1=min(ymax,y0+128);xx,yy=np.meshgrid(np.arange(xmin,xmax,dtype=np.float32)+.5,np.arange(y0,y1,dtype=np.float32)+.5);wa=((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den;wb=((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den;wc=1-wa-wb;ok=(wa>=-1e-6)&(wb>=-1e-6)&(wc>=-1e-6)&mask[y0:y1,xmin:xmax]
     if not ok.any():continue
     coordinates=art_uv[fi]
     if gradient:
      start,end=gradient['world_y_interval'];physical_y=-binding['vertices'][binding['tri'][fi],2]
      coordinates=np.stack([np.zeros(3),(physical_y-start)/(end-start)],axis=1)
     a,b,c=coordinates;map_kind[y0:y1,xmin:xmax][ok]=kind[fi];map_u[y0:y1,xmin:xmax][ok]=(wa*a[0]+wb*b[0]+wc*c[0])[ok];map_v[y0:y1,xmin:xmax][ok]=(wa*a[1]+wb*b[1]+wc*c[1])[ok]
     if need_face:map_face[y0:y1,xmin:xmax][ok]=fi
   for fi in ids:
    if kind[fi]==255 and not gradient:continue
    uv=binding['uv_fixed'][binding['tex'][fi]]
    if meta.get('repeat'):
     # Rasterize actual triangles in every intersecting UV tile. The source
     # mesh UVs stay untouched; repeated pixels necessarily share their ink.
     for dx in range(int(np.ceil(-uv[:,0].max())),int(np.floor(1-uv[:,0].min()))+1):
      for dy in range(int(np.ceil(-uv[:,1].max())),int(np.floor(1-uv[:,1].min()))+1):triangle(fi,uv+[dx,dy])
    else:triangle(fi,uv)
   # Intentional whole-atlas UV repeat surfaces receive only unobstructed
   # geometry-registered candidates, never one common stretched background.
   for _ in range(2):
    missing=mask&((map_face<0) if gradient else (map_kind==255))
    for dy,dx in [(0,1),(0,-1),(1,0),(-1,0)]:
     neighbor=np.roll(map_kind,(dy,dx),(0,1));ok=missing&((np.roll(map_face,(dy,dx),(0,1))>=0) if gradient else (neighbor!=255));ok[0]=False;ok[-1]=False;ok[:,0]=False;ok[:,-1]=False
     map_kind[ok]=neighbor[ok];map_u[ok]=np.roll(map_u,(dy,dx),(0,1))[ok];map_v[ok]=np.roll(map_v,(dy,dx),(0,1))[ok]
     if need_face:map_face[ok]=np.roll(map_face,(dy,dx),(0,1))[ok]
     missing[ok]=False
   np.savez_compressed(saved,u=map_u,v=map_v,kind=map_kind,**({'face':map_face} if need_face else {}));cache_hit=False
  original=np.asarray(Image.open(model.parent/'textures'/meta['texture_name']).convert('RGB').resize((size,size),Image.Resampling.LANCZOS));color=original.copy();metal=np.zeros((size,size),np.uint8);rough=np.full((size,size),153,np.uint8);painted=0
  preserve=None;preserved_pixels=0
  if guard:
   held=protected_faces[np.isin(binding['material_index'][protected_faces],[i for i,mid in enumerate(source_mats) if repair['materials'][mid].get('map_Kd')==meta['color_map']])]
   if domain_faces is not None:held=np.intersect1d(held,domain_faces)
   if len(held):
    im=Image.new('L',(size,size));pen=ImageDraw.Draw(im)
    for uv in binding['uv_fixed'][binding['tex'][held]]:
     tiles=[(0,0)]
     if meta.get('repeat'):tiles=[(dx,dy) for dx in range(int(np.ceil(-uv[:,0].max())),int(np.floor(1-uv[:,0].min()))+1) for dy in range(int(np.ceil(-uv[:,1].max())),int(np.floor(1-uv[:,1].min()))+1)]
     for dx,dy in tiles:pen.polygon([(float((u+dx)*size),float((1-v-dy)*size)) for u,v in uv],fill=255)
    padding=max(1,round(size/2048*guard.get('padding_pixels_at_2k',2)));preserve=(np.asarray(im.filter(ImageFilter.MaxFilter(padding*2+1)))>0)&mask;preserved_pixels=int(preserve.sum())
    def previous(channel,mode):
     row=reference['regions'][key];image=Image.open(reference_root/row[channel]);image=image.convert(mode) if mode else image
     return np.asarray(image.resize((size,size),Image.Resampling.LANCZOS))
  if relief:height=np.zeros((size,size),np.float32)
  fallback=meta.get('fallback_fill',project.contract.get('fallback_fill'))
  if fallback:
   color[mask]=fallback['rgb'];metal[mask]=round(fallback['metallic']*255);rough[mask]=round(fallback['roughness']*255)
   if relief:height[mask]=fallback.get('relief_mm',0)
  if gradient:
   start=np.asarray(gradient['front_rgb'],np.float32);end=np.asarray(gradient['rear_rgb'],np.float32)
   registered=mask&(map_face>=0);color[registered]=np.uint8(np.rint(start+(end-start)*np.clip(map_v[registered],0,1)[:,None]));painted=int(registered.sum())
  for i,k in enumerate(keys):
   if not (map_kind==i).any():continue
   im=plane(k)
   for y in range(0,size,256):
    end=min(size,y+256);u=map_u[y:end];v=map_v[y:end]
    if project.regions[k].get('wrap_v'):v=np.mod(v,1)
    ok=(map_kind[y:end]==i)&(u>=0)&(u<=1)&(v>=0)&(v<=1)
    if not ok.any():continue
    pixels=sample(im,u[ok],v[ok]);alpha=pixels[:,3:4].astype(np.float32)/255
    if meta.get('surface_alpha_floor'):alpha[pixels[:,3]<meta['surface_alpha_floor']]=0
    dst=color[y:end];dst[ok]=np.uint8(np.rint(dst[ok]*(1-alpha)+pixels[:,:3]*alpha));metal[y:end][ok]=np.uint8(np.rint(metal[y:end][ok]*(1-alpha[:,0])+pixels[:,4]*alpha[:,0]));rough[y:end][ok]=np.uint8(np.rint(rough[y:end][ok]*(1-alpha[:,0])+pixels[:,5]*alpha[:,0]));painted+=int((alpha[:,0]>0).sum())
    if relief:height[y:end][ok]=height[y:end][ok]*(1-alpha[:,0])+pixels[:,6]/255*alpha[:,0]
  if preserved_pixels:
   color[preserve]=previous('color','RGB')[preserve];metal[preserve]=previous('metallic','L')[preserve];rough[preserve]=previous('roughness','L')[preserve]
   if relief:height[preserve]=previous('height',None)[preserve].astype(np.float32)/65535
  # Pure net/chain domains are physical materials, outside a paint-finish
  # revision. They can share editing-board background texels with painted
  # hardware; explicit accepted scalar references prevent that background from
  # turning cloth or bare chain into the new base coating.
  for channel,target in [('metallic',metal),('roughness',rough)]:
   reference_path=meta.get('material_reference',{}).get(channel)
   if reference_path:
    with Image.open(project.root/reference_path) as image:
     target[:]=np.asarray(image.convert('L').resize((size,size),Image.Resampling.LANCZOS))
  assert np.array_equal(color[~mask],original[~mask]),key
  cp=out/'textures'/f'{key}-basecolor.png';mp=out/'materials'/f'{key}-metallic.png';rp=out/'materials'/f'{key}-roughness.png';Image.fromarray(color).save(cp);Image.fromarray(metal).save(mp);Image.fromarray(rough).save(rp)
  rows[key]=dict(color=cp.relative_to(out).as_posix(),metallic=mp.relative_to(out).as_posix(),roughness=rp.relative_to(out).as_posix(),normal=None,original_texture=meta['texture_name'],size=size,sha256=sha(cp),compatibility_only=bool(meta.get('compatibility_only')),source_face_ids=meta.get('source_face_ids'));audit[key]=dict(protected_pixels_exact=True,source_faces=len(ids),registered_native_pixels=int(((map_face>=0) if gradient else (map_kind!=255)).sum()),artwork_pixels=painted,cache_hit=cache_hit,overlap_policy='Stable original face order within material face domain; mirrored/shared pixels inside a domain necessarily share output',repeating_uv_spans_preserved=True)
  if gradient:audit[key]['coordinated_physical_y_gradient']=gradient
  if guard:audit[key].update(deferred_uv_guard=True,deferred_pixels_preserved=preserved_pixels,deferred_reference_manifest=guard['reference_manifest'])
  if relief:
   normal_name=next((r.get('map_normal') for r in repair['materials'].values() if r.get('map_Kd')==meta['color_map'] and r.get('map_normal')),None);normal_path=model.parent/'textures'/Path(normal_name).name if normal_name else None
   original_normal=np.asarray(Image.open(normal_path).convert('RGB').resize((size,size),Image.Resampling.LANCZOS)) if normal_path and normal_path.exists() else np.broadcast_to(np.uint8([128,128,255]),(size,size,3)).copy();detail=relief_normal(height,map_face,map_kind,metrics,valid_faces);normal=combine_normals(original_normal,detail,mask,project.contract['relief_material'].get('original_normal_strength',1),domain_config(project,key,meta));assert np.array_equal(normal[~mask],original_normal[~mask]),key
   if preserved_pixels:normal[preserve]=previous('normal','RGB')[preserve]
   npth=out/'materials'/f'{key}-normal.png';hp=out/'materials'/f'{key}-height-mm.png';sp=out/'materials'/f'{key}-smoothness.png';Image.fromarray(normal).save(npth);Image.fromarray(np.uint16(np.rint(height*65535))).save(hp);Image.fromarray(255-rough).save(sp);rows[key].update(normal=npth.relative_to(out).as_posix(),height=hp.relative_to(out).as_posix(),smoothness=sp.relative_to(out).as_posix(),height_encoding='16-bit linear; 0 = 0 mm, 65535 = 1 mm',normal_convention='OpenGL +Y, source UV physical metric',original_normal=Path(normal_name).name if normal_name else None);audit[key].update(protected_normal_pixels_exact=True,relief_max_mm=float(height.max()),source_uv_metric_used=True);del height,detail,normal,original_normal,map_face
  elif need_face:del map_face
  del original,color,metal,rough,map_u,map_v,map_kind,mask
 write_json(out/'evidence/surface-bake-audit.json',audit)
 return rows
