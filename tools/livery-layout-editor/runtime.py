"""Portable paths and optional executables. Never reads another project's state."""
from pathlib import Path
import json,os,shutil,sys

FROZEN=bool(getattr(sys,'frozen',False))
HERE=Path(sys._MEIPASS)/'tools/livery-layout-editor' if FROZEN else Path(__file__).resolve().parent
APP=HERE.parents[1]
APP_DATA=Path(os.environ.get('WT_CAMO_APP_DATA') or (Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'WT Camo Workbench' if FROZEN else APP/'data')).expanduser().resolve()
CONFIG=Path(os.environ.get('WT_CAMO_CONFIG') or (APP_DATA if FROZEN else APP)/'config/runtime.local.json')
SETTINGS=json.loads(CONFIG.read_text(encoding='utf-8-sig')) if CONFIG.exists() else {}
def configured(key,env):return os.environ.get(env) or SETTINGS.get(key)
ROOT=Path(configured('workspace','WT_CAMO_WORKSPACE') or APP_DATA/'workspace').expanduser()
if not ROOT.is_absolute():ROOT=APP/ROOT
ROOT=ROOT.resolve();ROOT.mkdir(parents=True,exist_ok=True)

def codex_executable():
 explicit=configured('codex','WT_CAMO_CODEX') or os.environ.get('LIVERY_CODEX_EXE')
 candidate=explicit or shutil.which('codex.exe') or shutil.which('codex')
 if candidate and Path(candidate).suffix.lower() in ['.cmd','.bat','.ps1']:
  # npm's shim is not executed through a shell. Resolve its native CLI package.
  base=Path(candidate).parent
  patterns=['node_modules/@openai/codex/vendor/*/codex/codex.exe',
   'node_modules/@openai/codex/node_modules/@openai/codex-*/vendor/*/codex/codex.exe',
   'node_modules/@openai/codex-*/vendor/*/codex/codex.exe']
  for pattern in patterns:
   found=list(base.glob(pattern))
   if found:return str(found[0])
  raise FileNotFoundError('找到了 npm shim，但未找到 native codex.exe；请设置 WT_CAMO_CODEX 为实际可执行文件路径。')
 if candidate and Path(candidate).is_file():return str(Path(candidate).resolve())
 if explicit:raise FileNotFoundError('配置的 Codex CLI 不存在。')
 extensions=Path(os.environ.get('USERPROFILE',str(Path.home())))/'.vscode/extensions'
 found=sorted(extensions.glob('openai.chatgpt-*/bin/windows-*/codex.exe'),reverse=True)
 if found:return str(found[0])
 raise FileNotFoundError('未找到 Codex CLI。请先安装并登录，或设置 WT_CAMO_CODEX。')

def blender_executable():
 value=configured('blender','WT_CAMO_BLENDER') or os.environ.get('BLENDER_PATH') or shutil.which('blender')
 if value and Path(value).is_file():return str(Path(value).resolve())
 if os.name=='nt':
  bases=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Blender Foundation']
  for base in bases:
   found=sorted(base.glob('Blender */blender.exe'),reverse=True)
   if found:return str(found[0])
 raise FileNotFoundError('未找到 Blender；请在 config/runtime.local.json 中配置 blender，或设置 WT_CAMO_BLENDER。')

def font_files():return [str(Path(p).resolve()) for p in SETTINGS.get('fonts',[]) if Path(p).is_file()]

def render_settings():
 return dict(dict(device='AUTO',backend='AUTO',device_name=None,use_cpu=False,
  silent_cpu_fallback=True,denoiser='OPENIMAGEDENOISE',denoising_use_gpu=False,
  samples=64,resolution=[1600,1200]),**SETTINGS.get('render',{}))
