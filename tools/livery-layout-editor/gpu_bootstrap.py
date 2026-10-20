"""Per-process Cycles device selection. Never saves host preferences."""
import bpy,json,os
from pathlib import Path
from bpy.app.handlers import persistent

config_path=os.environ.get('LIVERY_RENDER_SETTINGS')
SETTINGS=json.loads(Path(config_path).read_text(encoding='utf8')) if config_path else {}

def configure(reason):
 prefs=bpy.context.preferences.addons['cycles'].preferences
 request=SETTINGS.get('device','AUTO');backend=SETTINGS.get('backend','AUTO')
 selected=[]
 if request!='CPU':
  for choice in (['OPTIX','CUDA','HIP','ONEAPI','METAL'] if backend=='AUTO' else [backend]):
   try:
    prefs.compute_device_type=choice;prefs.refresh_devices()
    for device in prefs.devices:
     device.use=device.type==choice and (not SETTINGS.get('device_name') or device.name==SETTINGS['device_name'])
     if device.use:selected.append(dict(name=device.name,type=device.type))
    if selected:break
   except (TypeError,RuntimeError):continue
 if request=='GPU' and not selected and not SETTINGS.get('silent_cpu_fallback',False):
  raise RuntimeError('Requested GPU is unavailable; CPU fallback disabled.')
 actual='GPU' if selected else 'CPU'
 for scene in bpy.data.scenes:
  scene.cycles.device=actual;scene.cycles.denoiser=SETTINGS.get('denoiser','OPENIMAGEDENOISE')
  scene.cycles.denoising_use_gpu=bool(selected and SETTINGS.get('denoising_use_gpu',False))
 report=dict(reason=reason,requested=request,actual=actual,devices=selected)
 print('LIVERY_RENDER_DEVICE',json.dumps(report),flush=True)
 output=os.environ.get('LIVERY_OUTPUT_DIR')
 if output:
  folder=Path(output)/'evidence';folder.mkdir(exist_ok=True)
  with (folder/'gpu-runtime.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(report)+'\n')
 return report

@persistent
def livery_device_load(_):configure('load_post')
@persistent
def livery_device_render(_):configure('render_pre')
for handlers,callback in [(bpy.app.handlers.load_post,livery_device_load),(bpy.app.handlers.render_pre,livery_device_render)]:
 for old in list(handlers):
  if old.__name__==callback.__name__:handlers.remove(old)
 handlers.append(callback)
configure('bootstrap')
