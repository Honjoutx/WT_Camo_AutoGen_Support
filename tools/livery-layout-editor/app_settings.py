"""Small persistent UI preferences and explicit local executable settings."""
from pathlib import Path
import importlib.util
import json
import threading
from runtime import APP,APP_DATA,CONFIG,ROOT,SETTINGS,codex_executable,blender_executable
from project import write_json

LOCK=threading.RLock()
PREFERENCES=APP_DATA/'ui-preferences.json'


def preferences():
    try:
        value=json.loads(PREFERENCES.read_text(encoding='utf-8'))
        return {'language':value.get('language') if value.get('language') in ('zh-CN','en') else None}
    except (OSError,ValueError):return {'language':None}


def save_preferences(data):
    if data.get('language') not in ('zh-CN','en'):raise ValueError('Unsupported language.')
    with LOCK:write_json(PREFERENCES,{'language':data['language']})
    return preferences()


def view():
    result={'codex':SETTINGS.get('codex') or '', 'blender':SETTINGS.get('blender') or '',
            'workspace':str(ROOT),'data_directory':str(APP_DATA),'config_path':str(CONFIG)}
    for name,resolve in [('resolved_codex',codex_executable),('resolved_blender',blender_executable)]:
        try:result[name]=resolve()
        except OSError:result[name]=None
    return result


def save(data):
    with LOCK:
        value=json.loads(CONFIG.read_text(encoding='utf-8-sig')) if CONFIG.exists() else dict(SETTINGS)
        for key in ('codex','blender'):
            path=str(data.get(key,'')).strip()
            if path and not Path(path).expanduser().is_file():raise ValueError('Executable not found: '+path)
            value[key]=str(Path(path).expanduser().resolve()) if path else None
        workspace=str(data.get('workspace','')).strip()
        if workspace:
            path=Path(workspace).expanduser().resolve()
            if not path.is_dir():raise ValueError('Workspace directory does not exist.')
            value['workspace']=str(path)
        write_json(CONFIG,value);SETTINGS.clear();SETTINGS.update(value)
    return {**view(),'restart_required':bool(workspace and Path(workspace).resolve()!=ROOT)}


class BlenderManager:
    def __init__(self):self.lock=threading.Lock();self.busy=False;self.error=None
    def status(self):
        from blender_connection import status
        return {'busy':self.busy,'error':self.error,'connection':status()}
    def start(self,action):
        if action not in ('start','stop'):raise ValueError('Unsupported Blender action.')
        with self.lock:
            if self.busy:raise ValueError('Blender MCP operation is already running.')
            self.busy=True;self.error=None
        def execute():
            try:
                path=APP/'scripts/blender_mcp_manage.py'
                spec=importlib.util.spec_from_file_location('workbench_blender_manage',path)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                with module.management_lock():
                    if action=='start':module.setup();module.start()
                    else:module.stop()
            except Exception as exc:self.error=str(exc)
            finally:self.busy=False
        threading.Thread(target=execute,daemon=True).start()
        return {'busy':True,'action':action}
