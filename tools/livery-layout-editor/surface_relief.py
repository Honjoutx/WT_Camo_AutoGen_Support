"""Millimeter paint relief -> tangent-space normals in the source UV metric."""
import numpy as np
from PIL import Image,ImageFilter

def _work_windows(mask,pad,tile=128,force_tiles=False):
 """Disjoint write windows with enough source pixels for local operations.

 Sparse component islands can be scattered over a whole atlas. Bounding each
 occupied tile avoids running vector math over the intervening empty texels.
 Dense maps and very broad filters use one window to avoid redundant work.
 """
 h,w=mask.shape
 if not mask.any():return
 step=tile if force_tiles or (min(h,w)>=512 and pad<tile//2 and np.count_nonzero(mask)<mask.size*.35) else max(h,w)
 for y in range(0,h,step):
  for x in range(0,w,step):
   block=mask[y:min(y+step,h),x:min(x+step,w)]
   ys=np.flatnonzero(block.any(axis=1));xs=np.flatnonzero(block.any(axis=0))
   if not len(ys):continue
   y0=y+int(ys[0]);y1=y+int(ys[-1])+1;x0=x+int(xs[0]);x1=x+int(xs[-1])+1
   yield (slice(y0,y1),slice(x0,x1)),(slice(max(0,y0-pad),min(h,y1+pad)),slice(max(0,x0-pad),min(w,x1+pad)))

def uv_metrics(binding):
 p=binding['vertices'][binding['tri']];uv=binding['uv_fixed'][binding['tex']];e1=p[:,1]-p[:,0];e2=p[:,2]-p[:,0];a=uv[:,1]-uv[:,0];b=uv[:,2]-uv[:,0];det=a[:,0]*b[:,1]-a[:,1]*b[:,0];valid=np.abs(det)>1e-12;safe=np.where(valid,det,1)
 du=(e1*b[:,1,None]-e2*a[:,1,None])/safe[:,None];dv=(-e1*b[:,0,None]+e2*a[:,0,None])/safe[:,None];length=np.linalg.norm(du,axis=1);t=du/np.maximum(length[:,None],1e-15);skew=(t*dv).sum(1);height=np.linalg.norm(dv-skew[:,None]*t,axis=1);valid&=(length>1e-9)&(height>1e-9)
 return np.stack([length,skew,height],axis=1).astype(np.float32),valid
def relief_normal(height_mm,face_ids,kinds,metrics,valid_faces):
 """OpenGL +Y normal; image rows increase toward -V. No UV-island rim bump."""
 from export_acceleration import accelerate
 accelerated=accelerate('relief',height_mm,face_ids,kinds,metrics,valid_faces)
 if accelerated is not None:return accelerated
 shape=height_mm.shape;mask=face_ids>=0;out=np.empty((*shape,3),np.float32);out[:,:,:2]=0;out[:,:,2]=1
 for target,window in _work_windows(mask,2):
  value=_relief_normal_window(height_mm[window],face_ids[window],kinds[window],metrics,valid_faces,shape)
  local=tuple(slice(t.start-s.start,t.stop-s.start) for t,s in zip(target,window));out[target]=value[local]
 return out

def _relief_normal_window(height_mm,face_ids,kinds,metrics,valid_faces,atlas_shape,xp=np):
 # Derivatives use the full atlas dimensions, never the cropped dimensions.
 h=xp.asarray(height_mm,xp.float32)*.001;size_y,size_x=atlas_shape;dh_u=xp.gradient(h,axis=1)*size_x;dh_v=-xp.gradient(h,axis=0)*size_y;fid=xp.maximum(face_ids,0);a,b,c=metrics[fid].transpose(2,0,1);valid=(face_ids>=0)&valid_faces[fid];safe_a=xp.maximum(a,1e-9);safe_c=xp.maximum(c,1e-9);dx=dh_u/safe_a;dy=(dh_v-b*dx)/safe_c
 for sy,sx in [(0,-1),(0,1),(-1,0),(1,0)]:valid&=(xp.roll(kinds,(sy,sx),(0,1))==kinds)&(xp.roll(face_ids,(sy,sx),(0,1))>=0)
 valid[[0,-1]]=False;valid[:,[0,-1]]=False;dx[~valid]=0;dy[~valid]=0;dx=xp.clip(dx,-.30,.30);dy=xp.clip(dy,-.30,.30);n=xp.dstack([-dx,-dy,xp.ones_like(dx)]);return n/xp.maximum(xp.linalg.norm(n,axis=2,keepdims=True),1e-8)
def _normal_base(original_rgb,coverage,original_strength,xp=np):
 base=xp.asarray(original_rgb,xp.float32)/127.5-1;base=base.copy();base[coverage,:2]*=original_strength;base/=xp.maximum(xp.linalg.norm(base,axis=2,keepdims=True),1e-8)
 return base

def _opposite_edges(original_rgb,detail,coverage,window,original_strength):
 """Preserve the original normal smoother's atlas-border roll semantics."""
 y,x=window;h,w=coverage.shape;edges={}
 if x.start==0:edges[(0,1)]=(y,slice(w-1,w))
 if x.stop==w:edges[(0,-1)]=(y,slice(0,1))
 if y.start==0:edges[(1,0)]=(slice(h-1,h),x)
 if y.stop==h:edges[(-1,0)]=(slice(0,1),x)
 return {'base':{k:(_normal_base(original_rgb[s],coverage[s],original_strength),coverage[s]) for k,s in edges.items()},
         'detail':{k:(detail[s],coverage[s]) for k,s in edges.items()}}

def combine_normals(original_rgb,detail,coverage,original_strength=1,normal_finish=None):
 """RNM and grain finishing only in occupied UV windows, at atlas scale."""
 from export_acceleration import accelerate
 accelerated=accelerate('combine',original_rgb,detail,coverage,original_strength,normal_finish)
 if accelerated is not None:return accelerated
 coverage=np.asarray(coverage,bool);config=normal_finish
 pad=0
 if config and config.get('enabled'):
  from normal_finish import settings
  config=settings(config);reference=config.get('reference_size') or max(coverage.shape)
  config={**config,'reference_size':reference};sigma=max(config['base_radius_px_at_2k'],config['detail_radius_px_at_2k'])*reference/2048
  # Gaussian support, crease guard and one-pixel source neighbors.
  pad=int(np.ceil(4*sigma)+np.ceil(sigma)+2)
 result=original_rgb.copy()
 for target,window in _work_windows(coverage,pad):
  neighbors=_opposite_edges(original_rgb,detail,coverage,window,original_strength) if pad else None
  value=_combine_normals_window(original_rgb[window],detail[window],coverage[window],original_strength,config,neighbors)
  local=tuple(slice(t.start-s.start,t.stop-s.start) for t,s in zip(target,window));result[target]=value[local]
 return result

def _combine_normals_window(original_rgb,detail,coverage,original_strength=1,normal_finish=None,edge_neighbors=None,xp=np,distance_field=None):
 base=_normal_base(original_rgb,coverage,original_strength,xp)
 if normal_finish and normal_finish.get('enabled'):
  from normal_finish import finish_pair
  base,detail=finish_pair(base,detail,coverage,normal_finish,edge_neighbors,xp,distance_field)
 t=base+xp.array([0,0,1],xp.float32);u=detail*xp.array([-1,-1,1],xp.float32);dot=(t*u).sum(2,keepdims=True);normal=t*dot/xp.maximum(t[:,:,2:3],1e-7)-u;normal/=xp.maximum(xp.linalg.norm(normal,axis=2,keepdims=True),1e-8);rgb=xp.rint(xp.clip((normal+1)*127.5,0,255)).astype(xp.uint8);rgb[~coverage]=original_rgb[~coverage];return rgb
