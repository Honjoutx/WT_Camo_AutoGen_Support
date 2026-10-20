"""Direct, sharp export of a deliberately shared native-UV vector document."""
from pathlib import Path
import numpy as np
from PIL import Image
from export_runtime import save_png
from project import sha
from surface_relief import uv_metrics,combine_normals
from normal_finish import domain_config

def bake_shared(project,key,meta,planes,out,size,binding,repair):
 board=meta['native_uv_board'];row=planes[board];model=project.root/project.native_contract['model'];mask=np.asarray(Image.open(project.root/meta['mask']).convert('L').resize((size,size),Image.Resampling.NEAREST))>0
 original=np.asarray(Image.open(model.parent/'textures'/meta['texture_name']).convert('RGB').resize((size,size),Image.Resampling.LANCZOS));art=Image.open(out/row['color']).convert('RGBA')
 if art.size!=(size,size):art=art.resize((size,size),Image.Resampling.LANCZOS)
 pixels=np.asarray(art);alpha=pixels[:,:,3:4].astype(np.float32)/255;color=np.uint8(np.rint(original*(1-alpha)+pixels[:,:,:3]*alpha));color[~mask]=original[~mask]
 def scalar(ch,base):
  im=Image.open(out/row[ch]).convert('L')
  if im.size!=(size,size):im=im.resize((size,size),Image.Resampling.LANCZOS)
  a=np.asarray(im).copy();a[~mask]=round(base*255);return a
 metal=scalar('metallic',0);rough=scalar('roughness',.6);height=scalar('relief_mm',0).astype(np.float32)/255 if row.get('relief_mm') else np.zeros((size,size),np.float32)
 original_normal_name=next((v.get('map_normal') for v in repair['materials'].values() if v.get('map_Kd')==meta['color_map'] and v.get('map_normal')),None);npth=model.parent/'textures'/Path(original_normal_name).name if original_normal_name else None
 normal=np.asarray(Image.open(npth).convert('RGB').resize((size,size),Image.Resampling.LANCZOS)) if npth and npth.exists() else np.broadcast_to(np.uint8([128,128,255]),(size,size,3)).copy()
 # Shared texels can belong to many faces with different physical metrics.
 # Median footprint keeps the relief subtle and coherent across aliases.
 ids=np.load(project.root/meta['source_face_ids']);metrics,valid=uv_metrics(binding);sel=ids[valid[ids]];scale=np.maximum(np.median(metrics[sel][:,[0,2]],axis=0),.25) if len(sel) else [2,2]
 dx=np.gradient(height*.001,axis=1)*size/scale[0];dy=-np.gradient(height*.001,axis=0)*size/scale[1];dx=np.clip(dx,-.08,.08);dy=np.clip(dy,-.08,.08);dx[~mask]=0;dy[~mask]=0;detail=np.dstack([-dx,-dy,np.ones_like(dx)]);detail/=np.linalg.norm(detail,axis=2,keepdims=True);normal=combine_normals(normal,detail,mask,project.contract.get('relief_material',{}).get('original_normal_strength',1),domain_config(project,key,meta))
 paths={ch:out/('textures' if ch=='color' else 'materials')/f'{key}-{suffix}.png' for ch,suffix in [('color','basecolor'),('metallic','metallic'),('roughness','roughness'),('smoothness','smoothness'),('normal','normal'),('height','height-mm')]}
 for ch,array in [('color',color),('metallic',metal),('roughness',rough),('smoothness',255-rough),('normal',normal),('height',np.uint16(np.rint(height*65535)))]:save_png(Image.fromarray(array),paths[ch])
 result={ch:path.relative_to(out).as_posix() for ch,path in paths.items()};result.update(original_texture=meta['texture_name'],original_normal=Path(original_normal_name).name if original_normal_name else None,size=size,sha256=sha(paths['color']),compatibility_only=False,source_face_ids=meta['source_face_ids'],height_encoding='16-bit linear; 65535 = 1 mm',normal_convention='OpenGL +Y',shared_uv_board=board)
 audit=dict(source_faces=len(ids),direct_uv_pixels=True,no_projection_resampling=True,all_aliases_same_artwork=True,protected_pixels_exact=bool(np.array_equal(color[~mask],original[~mask])),shared_relief_metric='Median native-UV physical footprint, maximum slope 0.08')
 return result,audit
