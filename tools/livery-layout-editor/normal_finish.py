"""Separate source surface grain from printed relief; soften tangent vectors.

RGB normal maps are linear data, not photographs. Filtering normalized slopes
with a coverage guard avoids color blur, UV-island bleed and flattened seams.
"""
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter,distance_transform_edt,maximum_filter

DEFAULTS={'enabled':False,'base_radius_px_at_2k':1.15,'base_strength':.85,
 'detail_radius_px_at_2k':.35,'detail_strength':.92,'crease_threshold':.18}

def unit(n,xp=np):
 n=xp.asarray(n,xp.float32)
 return n/xp.maximum(xp.linalg.norm(n,axis=2,keepdims=True),1e-8)

def decode(rgb):return unit(np.asarray(rgb,np.float32)/127.5-1)

def soften(vectors,coverage,radius,strength,threshold,reference_size=None,edge_neighbors=None,xp=np,distance_field=None):
 if xp is np:gauss,edt,maximum=gaussian_filter,distance_transform_edt,maximum_filter
 else:
  from cupyx.scipy.ndimage import gaussian_filter as gauss,distance_transform_edt as edt,maximum_filter as maximum
 n=unit(vectors,xp);mask=xp.asarray(coverage,bool);sigma=float(radius)*(reference_size or max(mask.shape))/2048
 if not mask.any() or (sigma<=0 and strength==1):return n
 # Large rotations are bolts/seams; tiny alternating rotations are grain.
 slopes=n[:,:,:2]/xp.maximum(n[:,:,2:3],.08);edge=xp.zeros(mask.shape,xp.float32)
 for sy,sx in [(0,-1),(0,1),(-1,0),(1,0)]:
  delta=xp.linalg.norm(slopes-xp.roll(slopes,(sy,sx),(0,1)),axis=2)
  neighbor=xp.roll(mask,(sy,sx),(0,1))
  # A cropped window at an atlas edge still uses the original opposite edge
  # for this one-pixel roll. Gaussian/maximum filters retain nearest edges.
  if edge_neighbors and (sy,sx) in edge_neighbors:
   vectors_at_edge,mask_at_edge=edge_neighbors[(sy,sx)];other=unit(vectors_at_edge,xp)
   other_slopes=other[:,:,:2]/xp.maximum(other[:,:,2:3],.08)
   boundary=(slice(None),-1 if sx<0 else 0) if sx else (-1 if sy<0 else 0,slice(None))
   delta[boundary]=xp.linalg.norm(slopes[boundary]-other_slopes.reshape(-1,2),axis=1)
   neighbor[boundary]=xp.asarray(mask_at_edge).reshape(-1)
  edge=xp.maximum(edge,xp.where(neighbor,delta,0))
 edge=maximum(edge,size=2*max(1,int(np.ceil(sigma)))+1,mode='nearest')
 retention=1/(1+(edge/max(float(threshold),1e-6))**4)
 if distance_field is not None:distance=distance_field
 elif xp is not np and bool(mask.all()):
  # SciPy's all-foreground EDT uses the implicit zero at (-1, 0).
  yy,xx=xp.indices(mask.shape,dtype=xp.float64);distance=xp.sqrt((yy+1)**2+xx**2)
 else:distance=edt(mask)
 boundary=xp.clip((distance-1)/max(3*sigma,1),0,1).astype(xp.float32)
 weight=retention*boundary;result=slopes.copy()
 if sigma>0:
  support=gauss(mask.astype(xp.float32),sigma,mode='nearest')
  for axis in [0,1]:
   smooth=gauss(slopes[:,:,axis]*mask,sigma,mode='nearest')/xp.maximum(support,1e-6)
   result[:,:,axis]+=weight*(smooth-slopes[:,:,axis])
 result*=1-(1-float(strength))*weight[:,:,None]
 out=unit(xp.dstack([result,xp.ones(mask.shape,xp.float32)]),xp);out[~mask]=vectors[~mask]
 return out

def settings(config):return {**DEFAULTS,**(config or {})}

def eligible(key,meta):
 if meta.get('material_reference') or Path(meta.get('texture_name','')).stem.startswith(('net_','chain_')):return False
 return not any(word in meta.get('name','') for word in ['织物','织纹','织带','橡胶','木质','原木','镜片','玻璃'])

def domain_config(project,key,meta):
 c=project.contract.get('normal_finish',{})
 return c if eligible(key,meta) else {**c,'enabled':False}

def finish_pair(base,detail,coverage,config,edge_neighbors=None,xp=np,distance_field=None):
 c=settings(config)
 if not c['enabled']:return base,detail
 neighbors=edge_neighbors or {}
 return (soften(base,coverage,c['base_radius_px_at_2k'],c['base_strength'],c['crease_threshold'],c.get('reference_size'),neighbors.get('base'),xp,distance_field),
         soften(detail,coverage,c['detail_radius_px_at_2k'],c['detail_strength'],c['crease_threshold'],c.get('reference_size'),neighbors.get('detail'),xp,distance_field))

def extract_detail(composed,base):
 """Inverse orthogonal RNM rotation. The Z-up detail is preserved separately."""
 n=decode(composed);b=unit(base);bx,by,bz=np.moveaxis(b,2,0);nx,ny,nz=np.moveaxis(n,2,0);den=np.maximum(1+bz,1e-6)
 return unit(np.dstack([(1-bx*bx/den)*nx-bx*by/den*ny-bx*nz,
   -bx*by/den*nx+(1-by*by/den)*ny-by*nz,bx*nx+by*ny+bz*nz]))

def finish_composed(composed,original,coverage,original_strength,config,target_strength=None):
 from surface_relief import combine_normals
 # Component UV islands occupy a small part of their atlas. Restrict math to
 # that island's padded bounds, retaining the full-atlas physical pixel radius.
 ys=np.flatnonzero(coverage.any(axis=1));xs=np.flatnonzero(coverage.any(axis=0))
 if not len(ys):return composed.copy()
 c=settings(config);reference=config.get('reference_size',max(coverage.shape));sigma=max(c['base_radius_px_at_2k'],c['detail_radius_px_at_2k'])*reference/2048;pad=int(np.ceil(4*sigma)+np.ceil(sigma)+2)
 y0=max(0,int(ys[0])-pad);y1=min(coverage.shape[0],int(ys[-1])+pad+1);x0=max(0,int(xs[0])-pad);x1=min(coverage.shape[1],int(xs[-1])+pad+1)
 if (y1-y0,x1-x0)!=coverage.shape:
  cropped=finish_composed(composed[y0:y1,x0:x1],original[y0:y1,x0:x1],coverage[y0:y1,x0:x1],original_strength,{**config,'reference_size':config.get('reference_size',reference)},target_strength)
  result=composed.copy();result[y0:y1,x0:x1]=cropped;return result
 config={**config,'reference_size':config.get('reference_size',reference)}
 base=np.asarray(original,np.float32)/127.5-1;base=base.copy();base[coverage,:2]*=original_strength;base=unit(base)
 detail=extract_detail(composed,base)
 result=combine_normals(original,detail,coverage,original_strength if target_strength is None else target_strength,config)
 result[~coverage]=composed[~coverage]
 return result
