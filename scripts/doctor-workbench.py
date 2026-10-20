"""Read-only local deployment diagnostics (never prints credentials)."""
from pathlib import Path
import importlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/livery-layout-editor'))
from runtime import ROOT,codex_executable,blender_executable,CONFIG

def main():
 result={'python':sys.version.split()[0],'workspace':str(ROOT),'local_config':CONFIG.exists(),'packages':{}}
 failed=False
 for name in ['numpy','PIL','scipy','fontTools','resvg_py']:
  try:result['packages'][name]=getattr(importlib.import_module(name),'__version__','OK')
  except ImportError:result['packages'][name]='MISSING';failed=True
 for name,fn in [('codex',codex_executable),('blender_optional',blender_executable)]:
  try:result[name]=fn()
  except OSError as e:result[name]=str(e)
 if '--connect' in sys.argv:
  from codex_bridge import CodexProcess
  bridge=CodexProcess(lambda *args:None)
  try:
   bridge.ensure();account=bridge.rpc('account/read',{'refreshToken':False})
   result['cli_connection']={'initialized':True,'signed_in':bool(account.get('account')),
    'models':[m.get('id') for m in bridge.rpc('model/list',{'limit':100}).get('data',[])]}
  except Exception as e:result['cli_connection']={'error':str(e)};failed=True
  finally:bridge.close()
 if '--blender-mcp' in sys.argv:
  from blender_connection import status,codex_status
  from codex_bridge import CodexProcess
  result['blender_mcp']=status()
  if not result['blender_mcp']['connected']:failed=True
  if result['blender_mcp']['installed']:
   bridge=CodexProcess(lambda *args:None)
   try:
    bridge.ensure();result['blender_mcp']['codex']=codex_status(bridge)
    if not result['blender_mcp']['codex']['ready']:failed=True
   except Exception as e:result['blender_mcp']['codex']={'error':str(e),'ready':False};failed=True
   finally:bridge.close()
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return int(failed)

if __name__=='__main__':raise SystemExit(main())
