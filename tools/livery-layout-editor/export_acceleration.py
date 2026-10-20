"""Optional, job-local CUDA normal processing; CPU remains the default."""
from pathlib import Path
import functools,json,os,subprocess,sys,time,threading
import numpy as np

from runtime import ROOT
DEPENDENCIES=ROOT/'.tools/livery-gpu'
_backend=None
_output=None
_on_change=None
_report={'requested':'cpu','actual':'cpu','operations':{},'fallbacks':[]}
_dll_handles=[]
_backend_lock=threading.RLock()


def validate(value):
 if value not in ('cpu','gpu'):raise ValueError('贴图加速选项无效，请选择 CPU 或 GPU。')
 return value


def _load_cuda():
 if DEPENDENCIES.is_dir():
  sys.path.insert(0,str(DEPENDENCIES))
  cuda=DEPENDENCIES/'nvidia/cu13'
  if (cuda/'include/cuda_runtime.h').is_file():
   os.environ['CUDA_PATH']=str(cuda)
   if os.name=='nt':
    # NVIDIA wheels use x86_64; the CUDA pathfinder also expects bin/x64.
    compatible=cuda/'bin/x64';compatible.mkdir(exist_ok=True)
    for dll in (cuda/'bin/x86_64').glob('*.dll'):
     target=compatible/dll.name
     if not target.exists():
      try:os.link(dll,target)
      except FileExistsError:pass
    _dll_handles.append(os.add_dll_directory(str(compatible)))
 os.environ.setdefault('CUPY_CACHE_DIR',str(ROOT/'cache/cuda-kernels'))
 import cupy
 return cupy


def _write_report():
 if _output is not None:
  from project import write_json
  write_json(_output/'evidence/export-acceleration.json',_report)


def _notify():
 _write_report()
 if _on_change is not None:_on_change(dict(_report))


def configure(mode='cpu',output=None,on_change=None):
 global _backend,_output,_on_change,_report
 validate(mode)
 if _backend is not None:_backend.release()
 _backend=None;_output=Path(output) if output else None;_on_change=on_change
 _report={'schema':'livery-export-acceleration/v1','requested':mode,'actual':'cpu',
          'scope':['paint relief normals','normal composition','grain smoothing'],
          'operations':{},'fallbacks':[],'uv_unchanged':True,'resolution_unchanged':True}
 if mode=='gpu':
  try:
   _backend=CudaNormals()
   _report.update(actual='gpu',device=_backend.device,cupy=_backend.cp.__version__,
                  block_size=_backend.tile,device_pool_limit_bytes=_backend.pool_limit)
  except Exception as error:
   _backend=None;_report['fallbacks'].append({'operation':'initialization','reason':str(error)[:700]})
 _notify()
 return dict(_report)


def accelerate(operation,*args):
 # Independent UV domains share one CUDA backend/cache. Serialize its device
 # operations while CPU rasterization, decoding and PNG writes run in parallel.
 with _backend_lock:return _accelerate(operation,*args)


def _accelerate(operation,*args):
 global _backend
 if _backend is None:return None
 started=time.perf_counter()
 try:
  value=getattr(_backend,operation)(*args)
  row=_report['operations'].setdefault(operation,{'calls':0,'seconds':0})
  row['calls']+=1;row['seconds']+=time.perf_counter()-started
  if sum(r['calls'] for r in _report['operations'].values())%25==0:_write_report()
  return value
 except Exception as error:
  # Discard any partial result; the caller recomputes the entire operation on
  # CPU. Report the fallback explicitly rather than silently claiming GPU use.
  _report['fallbacks'].append({'operation':operation,'reason':str(error)[:700]})
  try:_backend.release()
  except Exception:pass
  _backend=None;_report['actual']='cpu';_notify();return None


def finalize():
 _write_report()
 if _backend is not None:_backend.release()
 return dict(_report)


@functools.lru_cache(maxsize=1)
def availability():
 # Probe in a short-lived process; the HTTP server never owns CUDA contexts.
 try:
  from runtime import HERE
  result=subprocess.run([sys.executable,str(HERE/'export_acceleration.py'),'--probe'],
       capture_output=True,text=True,encoding='utf8',timeout=30,
       creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  if result.returncode:raise RuntimeError(result.stderr[-700:] or 'GPU 检测失败')
  return json.loads(result.stdout)
 except Exception as error:return {'available':False,'reason':str(error)[:700]}


class CudaNormals:
 def __init__(self):
  self.cp=_load_cuda();cp=self.cp
  if cp.cuda.runtime.getDeviceCount()<1:raise RuntimeError('没有可用的 CUDA 显卡')
  properties=cp.cuda.runtime.getDeviceProperties(cp.cuda.runtime.getDevice())
  name=properties['name'];self.device=name.decode('utf8') if isinstance(name,bytes) else str(name)
  free,total=cp.cuda.runtime.memGetInfo();reserve=max(256*1024**2,int(total*.05));self.pool_limit=max(0,free-reserve)
  if self.pool_limit<256*1024**2:raise RuntimeError('可用显存不足 256 MB')
  cp.get_default_memory_pool().set_limit(size=self.pool_limit)
  self.tile=max(256,2**int(np.floor(np.log2(max(256,np.sqrt(self.pool_limit/320))))))
  self._metrics_ref=None;self._metrics=None;self._valid=None
  # Validate NVRTC, device kernels and the exact-distance-transform dependency.
  from cupyx.scipy.ndimage import distance_transform_edt,gaussian_filter
  a=cp.arange(64,dtype=cp.float32).reshape(8,8);mask=(a>10)&(a<40)
  check=gaussian_filter(distance_transform_edt(mask),1)
  if not bool(cp.isfinite(check).all()):raise RuntimeError('GPU 运算自检失败')
  cp.cuda.get_current_stream().synchronize()

 def release(self):
  self._metrics_ref=None;self._metrics=None;self._valid=None
  self.cp.get_default_memory_pool().free_all_blocks()

 def relief(self,height,faces,kinds,metrics,valid):
  from surface_relief import _work_windows,_relief_normal_window
  cp=self.cp;shape=height.shape
  result=np.empty((*shape,3),np.float32);result[:,:,:2]=0;result[:,:,2]=1
  if self._metrics_ref is not metrics:
   self._metrics_ref=metrics;self._metrics=cp.asarray(metrics);self._valid=cp.asarray(valid)
  for target,window in _work_windows(faces>=0,2,self.tile,force_tiles=True):
   value=_relief_normal_window(cp.asarray(height[window]),cp.asarray(faces[window]),cp.asarray(kinds[window]),self._metrics,self._valid,shape,cp)
   local=tuple(slice(t.start-s.start,t.stop-s.start) for t,s in zip(target,window))
   result[target]=cp.asnumpy(value[local])
  return result

 def combine(self,original,detail,coverage,strength,config):
  from surface_relief import _work_windows,_opposite_edges,_combine_normals_window
  from normal_finish import settings
  cp=self.cp;coverage=np.asarray(coverage,bool);result=original.copy()
  if not coverage.any():return result
  pad=0;distance=None;device_mask=None
  if config and config.get('enabled'):
   from cupyx.scipy.ndimage import distance_transform_edt
   config=settings(config);reference=config.get('reference_size') or max(coverage.shape)
   config={**config,'reference_size':reference}
   sigma=max(config['base_radius_px_at_2k'],config['detail_radius_px_at_2k'])*reference/2048
   pad=int(np.ceil(4*sigma)+np.ceil(sigma)+2)
   device_mask=cp.asarray(coverage)
   if coverage.all():
    # Match SciPy's implicit background for a completely foreground atlas.
    h,w=coverage.shape;y=cp.arange(h,dtype=cp.float64)[:,None]+1;x=cp.arange(w,dtype=cp.float64)[None,:]
    distance=cp.sqrt(y*y+x*x)
   else:distance=distance_transform_edt(device_mask)
  for target,window in _work_windows(coverage,pad,self.tile,force_tiles=True):
   neighbors=_opposite_edges(original,detail,coverage,window,strength) if pad else None
   value=_combine_normals_window(cp.asarray(original[window]),cp.asarray(detail[window]),
         device_mask[window] if device_mask is not None else cp.asarray(coverage[window]),
         strength,config,neighbors,cp,distance[window] if distance is not None else None)
   local=tuple(slice(t.start-s.start,t.stop-s.start) for t,s in zip(target,window))
   result[target]=cp.asnumpy(value[local])
  return result


if __name__=='__main__' and '--probe' in sys.argv:
 report=configure('gpu')
 print(json.dumps({'available':report['actual']=='gpu','device':report.get('device'),
                   'reason':report['fallbacks'][0]['reason'] if report['fallbacks'] else None},ensure_ascii=False))
 finalize()
